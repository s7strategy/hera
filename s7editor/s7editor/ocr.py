"""OCR offline via Tesseract — opcional, mas muda muito o que dá para fazer sem chave.

Sem OCR o motor offline sabe **onde** há texto, mas não **qual** texto. Isso
basta para apagar e para casar por papel ou por caixa, e não basta para o
pedido mais natural do usuário: "troca 'GARANTA O SEU' por 'ÚLTIMAS VAGAS' nas
30". Com o Tesseract instalado esse caminho passa a funcionar sem gastar um
centavo de API.

Falamos com o binário ``tesseract`` por subprocess de propósito: é uma
dependência a menos no requirements (o wrapper ``pytesseract`` não agrega nada
aqui) e o pacote do sistema já traz os dados de português.

Instalação::

    sudo apt install tesseract-ocr tesseract-ocr-por    # Debian/Ubuntu/VPS
    brew install tesseract tesseract-lang               # macOS
"""
from __future__ import annotations

import csv
import io
import logging
import os
import shutil
import subprocess
import tempfile
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image

from .models import Box

log = logging.getLogger("s7editor.ocr")

__all__ = [
    "ocr_available", "tesseract_langs", "ocr_box", "ocr_blocks", "ocr_page", "ocr_page_by_blocks",
    "assign_words_to_boxes", "normalize", "fuzzy_equal", "OCR_INSTALL_HINT",
]

OCR_INSTALL_HINT = (
    "OCR indisponível. Para casar texto sem chave de API, instale o Tesseract:\n"
    "  Ubuntu/VPS: sudo apt install tesseract-ocr tesseract-ocr-por\n"
    "  macOS:      brew install tesseract tesseract-lang\n"
    "Sem ele, use --papel (ex.: --papel cta) ou --caixa para escolher o bloco."
)

# Tesseract fica lento e impreciso em recortes minúsculos; abaixo disso a gente
# amplia antes de mandar.
_MIN_HEIGHT_PX = 40
_MAX_UPSCALE = 4.0


@lru_cache(maxsize=1)
def _binary() -> str | None:
    """Caminho do binário, ou None. Cacheado — isto roda por bloco de texto."""
    env = (os.environ.get("S7EDITOR_TESSERACT") or "").strip()
    if env:
        return env if Path(env).is_file() else None
    return shutil.which("tesseract")


def _env() -> dict[str, str]:
    """Ambiente para o subprocess do Tesseract.

    ``OMP_THREAD_LIMIT=1`` é obrigatório aqui. O Tesseract usa OpenMP e, por
    padrão, tenta ocupar todos os núcleos; como o lote já roda várias imagens em
    paralelo, cada instância briga com as outras e o tempo de parede explode
    (medimos 36 min de CPU para 10 min de relógio, com as imagens saindo a ~40 s
    em vez de ~0,6 s). Com uma thread por processo, o paralelismo fica onde ele
    deve ficar: no nosso pool.
    """
    env = dict(os.environ)
    env["OMP_THREAD_LIMIT"] = "1"
    return env


def ocr_available() -> bool:
    """True quando dá para ler texto offline."""
    return _binary() is not None


@lru_cache(maxsize=1)
def tesseract_langs() -> tuple[str, ...]:
    """Idiomas instalados, para não pedir 'por' onde só existe 'eng'."""
    exe = _binary()
    if not exe:
        return ()
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True,
                             timeout=20, check=False, env=_env()).stdout
    except (OSError, subprocess.SubprocessError):
        return ()
    langs = [ln.strip() for ln in out.splitlines()[1:] if ln.strip()]
    return tuple(langs)


def _best_lang(preferred: str | None = None) -> str:
    if preferred:
        return preferred
    have = set(tesseract_langs())
    if "por" in have and "eng" in have:
        return "por+eng"
    if "por" in have:
        return "por"
    return "eng"


# --------------------------------------------------------------------------- #
# Preparo da imagem
# --------------------------------------------------------------------------- #
def _prepare(crop: np.ndarray) -> list[Image.Image]:
    """Duas versões do recorte: como está e invertida.

    Criativo é metade texto claro sobre fundo escuro, e o Tesseract foi treinado
    em texto escuro sobre claro. Em vez de adivinhar a polaridade pelos pixels,
    mandamos as duas e ficamos com a de maior confiança — sai mais barato do que
    errar e mais simples do que estimar.
    """
    if crop.ndim == 3:
        gray = (0.299 * crop[:, :, 0] + 0.587 * crop[:, :, 1]
                + 0.114 * crop[:, :, 2]).astype(np.uint8)
    else:
        gray = crop.astype(np.uint8)

    h = max(1, gray.shape[0])
    if h < _MIN_HEIGHT_PX:
        factor = min(_MAX_UPSCALE, _MIN_HEIGHT_PX / h)
        img = Image.fromarray(gray).resize(
            (max(1, int(gray.shape[1] * factor)), max(1, int(h * factor))),
            Image.LANCZOS)
        gray = np.asarray(img)

    # Uma margem clara ajuda o Tesseract a achar a linha de base.
    padded = np.pad(gray, 12, mode="edge")
    return [Image.fromarray(padded), Image.fromarray(255 - padded)]


def _run(img: Image.Image, lang: str, psm: int) -> tuple[str, float]:
    """Roda o Tesseract e devolve (texto, confiança média 0-100)."""
    exe = _binary()
    if not exe:
        return ("", -1.0)
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.png"
        img.save(src, "PNG")
        cmd = [exe, str(src), "stdout", "-l", lang, "--psm", str(psm), "tsv"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=60, check=False, env=_env())
        except (OSError, subprocess.SubprocessError) as exc:
            log.debug("tesseract falhou: %s", exc)
            return ("", -1.0)
        if proc.returncode != 0:
            return ("", -1.0)

    words: list[str] = []
    confs: list[float] = []
    reader = csv.DictReader(io.StringIO(proc.stdout), delimiter="\t",
                            quoting=csv.QUOTE_NONE)
    for row in reader:
        txt = (row.get("text") or "").strip()
        if not txt:
            continue
        try:
            conf = float(row.get("conf") or -1)
        except ValueError:
            conf = -1.0
        if conf < 0:
            continue
        words.append(txt)
        confs.append(conf)
    if not words:
        return ("", -1.0)
    return (" ".join(words), float(np.mean(confs)))


def ocr_box(arr: np.ndarray, box: Box | None = None, *, lang: str | None = None,
            single_line: bool | None = None, quick: bool = False) -> tuple[str, float]:
    """Lê o texto dentro de ``box``. Devolve ``(texto, confiança)``.

    Confiança < 0 significa "não li nada" — quem chama decide se isso é um bloco
    sem texto ou um bloco que o OCR não deu conta.
    """
    if not ocr_available():
        return ("", -1.0)
    if arr.size == 0:
        return ("", -1.0)
    h, w = arr.shape[:2]
    if box is not None:
        b = box.pad(4, w, h)
        if b.w < 4 or b.h < 4:
            return ("", -1.0)
        crop = arr[b.y:b.y1, b.x:b.x1]
    else:
        crop = arr
    if crop.size == 0:
        return ("", -1.0)

    if single_line is None:
        single_line = crop.shape[0] > 0 and (crop.shape[1] / max(crop.shape[0], 1)) > 3.5
    psm = 7 if single_line else 6

    lang = _best_lang(lang)
    best_txt, best_conf = "", -1.0
    for cand in _prepare(crop):
        txt, conf = _run(cand, lang, psm)
        if txt and conf > best_conf:
            best_txt, best_conf = txt, conf
    # Um bloco largo lido como linha única às vezes perde a segunda linha.
    # `quick` pula essa repescagem: ela dobra o custo e só compensa quando
    # este recorte é a única fonte de texto, não quando é rede de segurança.
    if not quick and best_conf < 60 and psm == 7:
        for cand in _prepare(crop):
            txt, conf = _run(cand, lang, 6)
            if txt and conf > best_conf:
                best_txt, best_conf = txt, conf
    return (best_txt.strip(), best_conf)


def ocr_blocks(arr: np.ndarray, boxes: Sequence[Box], *,
               lang: str | None = None) -> list[tuple[str, float]]:
    """``ocr_box`` para vários blocos, na mesma ordem."""
    return [ocr_box(arr, b, lang=lang) for b in boxes]


# --------------------------------------------------------------------------- #
# Comparação tolerante
# --------------------------------------------------------------------------- #
def normalize(text: str) -> str:
    """Minúscula, sem acento, sem pontuação, espaços colapsados.

    O usuário digita "garanta o seu"; o criativo diz "GARANTA O SEU!" e o OCR
    devolve "GARANTA 0 SEU" — as três precisam casar.
    """
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = "".join(c if c.isalnum() or c.isspace() else " " for c in s.lower())
    return " ".join(s.split())


def _confusions(s: str) -> str:
    """Achata as trocas clássicas do OCR (0/O, 1/I/l, 5/S, 8/B)."""
    table = str.maketrans({"0": "o", "1": "i", "l": "i", "5": "s", "8": "b", "2": "z"})
    return s.translate(table)


def fuzzy_equal(a: str, b: str, *, threshold: float = 0.82) -> bool:
    """Casa dois textos tolerando acento, caixa, pontuação e erro de OCR."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return False
    if na == nb or na in nb or nb in na:
        return True
    ca, cb = _confusions(na), _confusions(nb)
    if ca == cb or ca in cb or cb in ca:
        return True
    from difflib import SequenceMatcher
    return SequenceMatcher(None, ca, cb).ratio() >= threshold


# --------------------------------------------------------------------------- #
# Leitura da página inteira (o caminho rápido)
# --------------------------------------------------------------------------- #
def _run_words(img: Image.Image, lang: str, psm: int,
               scale: float = 1.0) -> list[dict[str, Any]]:
    """Roda o Tesseract e devolve uma palavra por item, com caixa em pixel da origem."""
    exe = _binary()
    if not exe:
        return []
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.png"
        img.save(src, "PNG")
        cmd = [exe, str(src), "stdout", "-l", lang, "--psm", str(psm), "tsv"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=180, check=False, env=_env())
        except (OSError, subprocess.SubprocessError) as exc:
            log.debug("tesseract (página) falhou: %s", exc)
            return []
        if proc.returncode != 0:
            return []

    out: list[dict[str, Any]] = []
    reader = csv.DictReader(io.StringIO(proc.stdout), delimiter="\t",
                            quoting=csv.QUOTE_NONE)
    for row in reader:
        txt = (row.get("text") or "").strip()
        if not txt:
            continue
        try:
            conf = float(row.get("conf") or -1)
            left, top = int(row["left"]), int(row["top"])
            width, height = int(row["width"]), int(row["height"])
        except (ValueError, KeyError, TypeError):
            continue
        if conf < 0:
            continue
        out.append({
            "text": txt,
            "conf": conf,
            "box": Box(int(left / scale), int(top / scale),
                       max(1, int(width / scale)), max(1, int(height / scale))),
        })
    return out


def ocr_page(arr: np.ndarray, *, lang: str | None = None) -> list[dict[str, Any]]:
    """Lê a página inteira de uma vez e devolve as palavras com posição.

    Por que não ler bloco a bloco: cada chamada ao Tesseract é um subprocess, e
    uma peça com sete blocos custava ~28 spawns (blocos x polaridades x modos).
    Aqui são **duas** chamadas por imagem — normal e invertida — e as palavras
    vão para os blocos por geometria depois. Num lote de 30 imagens isso é a
    diferença entre minutos e segundos.

    As duas polaridades existem porque criativo mistura texto claro sobre fundo
    escuro (a faixa de CTA) com escuro sobre claro (o selo de preço) na MESMA
    peça — nenhuma inversão global serve para as duas.
    """
    if not ocr_available() or arr.size == 0:
        return []
    lang = _best_lang(lang)

    if arr.ndim == 3:
        gray = (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1]
                + 0.114 * arr[:, :, 2]).astype(np.uint8)
    else:
        gray = arr.astype(np.uint8)

    # Teto de resolução: acima disso o Tesseract fica lento sem ficar melhor.
    h, w = gray.shape[:2]
    scale = min(1.0, 2000.0 / max(h, w, 1))
    if scale < 1.0:
        gray = np.asarray(Image.fromarray(gray).resize(
            (max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS))

    palavras: list[dict[str, Any]] = []
    for variante in (gray, 255 - gray):
        # psm 11 = texto esparso: é o que descreve um criativo — blocos soltos
        # espalhados pelo quadro, não uma página de livro.
        palavras.extend(_run_words(Image.fromarray(variante), lang, 11, scale=scale))
    return palavras


def assign_words_to_boxes(words: Sequence[dict[str, Any]], boxes: Sequence[Box],
                          *, min_conf: float = 45.0) -> list[tuple[str, float]]:
    """Distribui as palavras lidas nos blocos, por contenção de área.

    Como rodamos duas polaridades, a mesma palavra costuma voltar duas vezes;
    ficamos com a leitura de maior confiança em cada posição. Devolve
    ``(texto, confiança)`` por bloco, na ordem de ``boxes``.
    """
    saida: list[tuple[str, float]] = []
    for b in boxes:
        dentro: list[dict[str, Any]] = []
        for wd in words:
            wb: Box = wd["box"]
            if wb.area <= 0 or wd["conf"] < min_conf or not wb.intersects(b):
                continue
            # IoU puniria palavra pequena dentro de bloco grande; o que importa
            # é a fração da PALAVRA que cai dentro do bloco.
            ix = min(wb.x1, b.x1) - max(wb.x, b.x)
            iy = min(wb.y1, b.y1) - max(wb.y, b.y)
            if (ix * iy) / wb.area < 0.6:
                continue
            dentro.append(wd)

        if not dentro:
            saida.append(("", -1.0))
            continue

        # Remove a duplicata vinda da outra polaridade: mesma posição aproximada.
        dentro.sort(key=lambda d: -d["conf"])
        escolhidas: list[dict[str, Any]] = []
        for wd in dentro:
            if not any(wd["box"].iou(e["box"]) > 0.5 for e in escolhidas):
                escolhidas.append(wd)

        # Ordem de leitura. Agrupar por faixa fixa (y // tol) quebra quando uma
        # linha cai em cima da fronteira do bucket e as palavras se misturam
        # entre linhas — foi o que embaralhou "Edicao em lote com garantia".
        # Aqui as linhas são formadas por proximidade real do centro vertical.
        escolhidas.sort(key=lambda e: e["box"].y + e["box"].h / 2.0)
        linhas: list[list[dict[str, Any]]] = []
        for wd in escolhidas:
            cy = wd["box"].y + wd["box"].h / 2.0
            if linhas:
                ult = linhas[-1]
                ref = sum(w["box"].y + w["box"].h / 2.0 for w in ult) / len(ult)
                altura = sum(w["box"].h for w in ult) / len(ult)
                if abs(cy - ref) <= 0.6 * max(altura, 1):
                    ult.append(wd)
                    continue
            linhas.append([wd])
        ordenadas = [wd for linha in linhas
                     for wd in sorted(linha, key=lambda e: e["box"].x)]
        conf = float(np.mean([e["conf"] for e in ordenadas]))
        saida.append((" ".join(e["text"] for e in ordenadas).strip(), conf))
    return saida


def _binarize(crop: np.ndarray) -> np.ndarray:
    """Recorte -> texto PRETO sobre fundo BRANCO, via Otsu local.

    A polaridade é decidida por contagem: dentro de uma caixa de texto folgada,
    os pixels de glifo são sempre a minoria. Isso resolve, sem heurística de
    cor, o fato de um mesmo criativo ter texto branco sobre faixa rosa e texto
    escuro sobre selo amarelo.
    """
    if crop.ndim == 3:
        gray = (0.299 * crop[:, :, 0] + 0.587 * crop[:, :, 1]
                + 0.114 * crop[:, :, 2]).astype(np.uint8)
    else:
        gray = crop.astype(np.uint8)
    if gray.size == 0:
        return gray

    try:
        import cv2
        _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    except Exception:  # noqa: BLE001 - sem cv2, Otsu na mão
        hist = np.bincount(gray.ravel(), minlength=256).astype(np.float64)
        total = hist.sum() or 1.0
        omega = np.cumsum(hist) / total
        mu = np.cumsum(hist * np.arange(256)) / total
        mu_t = mu[-1]
        denom = omega * (1.0 - omega)
        denom[denom == 0] = 1e-9
        sigma_b = (mu_t * omega - mu) ** 2 / denom
        thr = int(np.argmax(sigma_b))
        bw = np.where(gray > thr, 255, 0).astype(np.uint8)

    # Minoria = texto. Queremos o texto preto.
    if int((bw == 255).sum()) < int((bw == 0).sum()):
        bw = 255 - bw
    return bw


def ocr_page_by_blocks(arr: np.ndarray, boxes: Sequence[Box], *,
                       lang: str | None = None) -> list[tuple[str, float]]:
    """Lê todos os blocos com UMA chamada ao Tesseract.

    Monta uma "página limpa" branca e cola nela cada bloco já binarizado com a
    polaridade certa; então lê essa página de uma vez. É o melhor dos dois
    mundos: contraste resolvido bloco a bloco (o que a leitura global da página
    não consegue num criativo colorido) com o custo de uma única chamada.
    """
    if not ocr_available() or arr.size == 0 or not boxes:
        return [("", -1.0) for _ in boxes]

    h, w = arr.shape[:2]
    pagina = np.full((h, w), 255, dtype=np.uint8)
    usadas: list[Box] = []
    for b in boxes:
        bb = b.pad(6, w, h)
        if bb.w < 4 or bb.h < 4:
            usadas.append(bb)
            continue
        pagina[bb.y:bb.y1, bb.x:bb.x1] = _binarize(arr[bb.y:bb.y1, bb.x:bb.x1])
        usadas.append(bb)

    lang = _best_lang(lang)
    # psm 11 (texto esparso): é o que a página montada é — ilhas de texto
    # separadas por branco, sem fluxo de parágrafo.
    palavras = _run_words(Image.fromarray(pagina), lang, 11)
    if not palavras:
        return [("", -1.0) for _ in boxes]
    return assign_words_to_boxes(palavras, list(boxes), min_conf=30.0)
