"""Leitura de criativos: o que está escrito, onde, e com que cara.

Este módulo é o único do projeto que "olha" para uma imagem e devolve
:class:`CreativeAnalysis`. Ele tem duas trilhas independentes:

* **Trilha IA** (:func:`analyze_creative` com ``OPENAI_API_KEY``): manda uma
  versão reduzida da imagem para o modelo de visão e exige JSON estruturado —
  blocos de texto com caixa NORMALIZADA, texto exato, papel e estilo aparente,
  paleta, tipo de fundo, arquétipo de layout e áreas seguras.
* **Trilha offline** (:func:`heuristic_analysis`): 100% determinística, sem
  rede. Encontra *onde* há texto com gradiente morfológico + fechamento
  horizontal + componentes conexas, agrupa em linhas/blocos e chuta o papel
  pela posição. O texto fica vazio (não há OCR aqui) — o que basta para
  **localizar e apagar**, que é o caso de uso crítico offline.

Por que as caixas voltam sempre em pixels da imagem ORIGINAL: reduzimos a
imagem só para baratear o token de visão, mas o pipeline de edição trabalha no
master nativo. Pedir caixa normalizada ao modelo resolve isso sem nenhuma
conversão sujeita a erro de arredondamento acumulado.

O cache é obrigatório na prática: reanalisar 30 criativos a cada rodada custa
dinheiro e tempo. A chave é o SHA do CONTEÚDO em pixels (não do arquivo), então
recomprimir a mesma imagem não invalida nada. Só resultado de IA vai para o
cache — resultado heurístico é barato e seria uma pena servi-lo depois que o
usuário finalmente configurou a chave.
"""
from __future__ import annotations

import base64
import difflib
import hashlib
import io
import json
import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable, Sequence

import cv2
import numpy as np
from PIL import Image

from . import ocr as _ocr
from .config import Settings, load_settings
from .imageio_util import dominant_colors, image_sha, load_image
from .models import (
    BackgroundKind,
    Box,
    CreativeAnalysis,
    CreativeDNA,
    FontSpec,
    TextBlock,
    TextRole,
    color_to_hex,
    parse_color,
)

log = logging.getLogger("s7editor.vision")

__all__ = [
    "analyze_creative",
    "analyze_batch",
    "extract_dna",
    "heuristic_analysis",
    "find_text_block",
    "VISION_MAX_SIDE",
    "PROMPT_VERSION",
]

# Lado maior enviado ao modelo de visão. 1280 é o ponto onde o texto de um
# criativo 1080x1920 ainda é legível e o custo por imagem fica razoável.
VISION_MAX_SIDE = 1280

# Muda quando o prompt/esquema muda: entra na chave de cache para que análises
# antigas não sejam servidas com um contrato diferente do atual.
PROMPT_VERSION = "v1"

# Limiar de similaridade do casamento difuso de texto em find_text_block.
FUZZY_THRESHOLD = 0.62

# Teto de blocos devolvidos pela trilha offline (ordenados por área).
MAX_BLOCKS = 18

_WEIGHTS = ("thin", "light", "regular", "medium", "semibold", "bold", "black")


# --------------------------------------------------------------------------- #
# Utilidades de texto (normalização e casamento difuso)
# --------------------------------------------------------------------------- #
def _norm_text(s: Any) -> str:
    """'GARANTA O SEU!' e 'garanta  o seu' viram a mesma string.

    Tira acento, caixa, pontuação e espaço repetido. É a forma canônica usada
    para casar o que o usuário digitou com o que está no criativo.
    """
    if s is None:
        return ""
    txt = unicodedata.normalize("NFD", str(s))
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    txt = txt.casefold()
    txt = re.sub(r"[^0-9a-z\s]+", " ", txt)
    return re.sub(r"\s+", " ", txt).strip()


def _text_score(needle: str, hay: str) -> float:
    """Quão bem ``needle`` casa com ``hay`` (0–1). 1.0 = idêntico normalizado."""
    a, b = _norm_text(needle), _norm_text(hay)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b:
        # Quanto maior a fatia que o pedido cobre, melhor: evita que "o" case
        # com qualquer bloco que contenha a letra o.
        return 0.90 + 0.09 * (len(a) / len(b))
    if b in a:
        return 0.85 * (len(b) / len(a))
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    # Bônus por palavras em comum: "compre agora" x "agora compre já".
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    return max(ratio, 0.5 * ratio + 0.5 * jac)


def _coerce_role(role: Any) -> TextRole | None:
    if role is None:
        return None
    if isinstance(role, TextRole):
        return role
    try:
        return TextRole(str(role).strip().lower())
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Medidas de pixel (versão local, compacta, do classificador de fundo)
# --------------------------------------------------------------------------- #
def _rgb_array(img: Image.Image) -> np.ndarray:
    """``np.uint8 (H, W, 3)`` — alfa achatado em branco, que é o que se vê."""
    if img.mode == "RGB":
        return np.asarray(img, dtype=np.uint8)
    if img.mode == "RGBA":
        flat = Image.new("RGB", img.size, (255, 255, 255))
        flat.paste(img, mask=img.split()[3])
        return np.asarray(flat, dtype=np.uint8)
    return np.asarray(img.convert("RGB"), dtype=np.uint8)


def _noise_sigma(gray: np.ndarray, mask: np.ndarray | None = None) -> float:
    """Estimador de Immerkær: σ do ruído da própria imagem (JPEG, grão).

    Existe para que nenhum limiar do classificador seja um número mágico fixo:
    todos viram ``max(constante, múltiplo·σ)``. É isso que faz o mesmo código
    funcionar em PNG chapado e em JPEG q=70.
    """
    if gray.size < 9:
        return 0.0
    m = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    resp = np.abs(cv2.filter2D(gray.astype(np.float32), -1, m))
    vals = resp[mask] if (mask is not None and mask.any()) else resp.ravel()
    if vals.size == 0:
        return 0.0
    return float(np.sqrt(np.pi / 2.0) * float(vals.mean()) / 6.0)


def _basis(hh: int, ww: int, quad: bool) -> np.ndarray:
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    u = 2.0 * (xx / max(ww - 1, 1)) - 1.0
    v = 2.0 * (yy / max(hh - 1, 1)) - 1.0
    one = np.ones_like(u)
    if quad:
        return np.stack([one, u, v, u * u, u * v, v * v], -1)
    return np.stack([one, u, v], -1)


def _fit_plane(patch: np.ndarray, mask: np.ndarray, *, quad: bool = False
               ) -> tuple[np.ndarray, list[np.ndarray], list[float]]:
    """Ajuste robusto (2 iterações de rejeição por MAD) de um plano por canal.

    Devolve ``(PHI, betas, rms_por_canal)``. Robusto porque o resíduo bruto é
    envenenado pelo anti-aliasing do texto; sem a rejeição, um fundo chapado
    com uma headline em cima seria classificado como foto.
    """
    hh, ww = patch.shape[:2]
    phi = _basis(hh, ww, quad)
    k = phi.shape[2]
    a_all = phi.reshape(-1, k)[mask.ravel()]
    betas: list[np.ndarray] = []
    rmss: list[float] = []
    for c in range(3):
        y = patch[..., c].astype(np.float32).ravel()[mask.ravel()]
        if a_all.shape[0] < k + 2:
            betas.append(np.zeros(k, np.float32))
            rmss.append(float("inf"))
            continue
        beta, *_ = np.linalg.lstsq(a_all, y, rcond=None)
        r = y - a_all @ beta
        keep = np.ones_like(r, dtype=bool)
        for _ in range(2):
            s = 1.4826 * float(np.median(np.abs(r - np.median(r)))) + 1e-6
            cand = np.abs(r) <= 2.5 * s
            if int(cand.sum()) < k + 2:
                break
            keep = cand
            beta, *_ = np.linalg.lstsq(a_all[keep], y[keep], rcond=None)
            r = y - a_all @ beta
        betas.append(beta.astype(np.float32))
        rmss.append(float(np.sqrt(float((r[keep] ** 2).mean()))) if keep.any() else float("inf"))
    return phi, betas, rmss


def _periodicity(gray: np.ndarray) -> float:
    """Pico da autocorrelação fora do centro: separa `pattern` de `photo`."""
    hh, ww = gray.shape[:2]
    if hh < 16 or ww < 16:
        return 0.0
    z = gray.astype(np.float32) - float(gray.mean())
    power = np.abs(np.fft.rfft2(z)) ** 2
    ac = np.fft.irfft2(power, s=z.shape)
    denom = float(ac[0, 0]) + 1e-9
    ac = ac / denom
    lag = ac.copy()
    lag[:4, :4] = 0.0
    return float(lag[: hh // 2, : ww // 2].max())


def _region_kind(patch: np.ndarray) -> tuple[BackgroundKind, tuple[int, int, int] | None, float]:
    """Classifica o fundo de um recorte e devolve ``(tipo, cor_sólida, σ_ruído)``.

    Implementa a versão compacta da árvore de decisão do projeto técnico: anel
    de borda -> tinta provisória -> σ de ruído -> ajuste linear robusto ->
    (quadrático) -> periodicidade. `inpaint.classify_region` faz a versão
    completa; aqui só precisamos do rótulo e da cor para preencher
    ``TextBlock.on_solid_background`` e ``background_color``, então mantemos
    uma cópia local e independente para não criar ciclo de import.
    """
    hh, ww = patch.shape[:2]
    if hh < 4 or ww < 4 or hh * ww < 400:
        return BackgroundKind.MIXED, None, 0.0

    k = int(np.clip(round(0.08 * hh), 2, 6))
    ring = np.zeros((hh, ww), bool)
    ring[:k, :] = ring[-k:, :] = True
    ring[:, :k] = ring[:, -k:] = True

    lab = cv2.cvtColor(patch, cv2.COLOR_RGB2LAB).astype(np.float32)
    bg0 = np.median(lab[ring], axis=0)
    d0 = np.linalg.norm(lab - bg0, axis=2)
    ink0 = d0 > 15.0
    bgm = ~cv2.dilate(ink0.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=3).astype(bool)
    if bgm.mean() < 0.20 or int(bgm.sum()) < 200:
        return BackgroundKind.MIXED, None, 0.0

    gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
    sig_n = _noise_sigma(gray, bgm)

    phi, betas, rmss = _fit_plane(patch, bgm, quad=False)
    r_lin = max(rmss)
    ramp = 0.0
    for beta in betas:
        ramp = max(ramp, float(np.ptp(phi.reshape(-1, phi.shape[2]) @ beta)))

    t_solid = max(1.5, 2.5 * sig_n)
    t_ramp = max(3.0, 4.0 * sig_n)
    t_grad = max(3.0, 3.0 * sig_n)

    if r_lin <= t_solid and ramp <= t_ramp:
        far = ~cv2.dilate(ink0.astype(np.uint8), np.ones((3, 3), np.uint8),
                          iterations=5).astype(bool)
        src = patch[far] if far.sum() >= 50 else patch[bgm]
        color = tuple(int(v) for v in np.median(src.reshape(-1, 3), axis=0))
        return BackgroundKind.SOLID, color, sig_n  # type: ignore[return-value]

    if r_lin <= t_solid:
        return BackgroundKind.GRADIENT, None, sig_n
    if r_lin <= 8.0:
        _, _, rq = _fit_plane(patch, bgm, quad=True)
        if max(rq) <= t_grad:
            return BackgroundKind.GRADIENT, None, sig_n

    edge = float((cv2.Canny(gray, 50, 150) > 0)[bgm].mean())
    if _periodicity(gray) >= 0.30 and edge >= 0.030:
        return BackgroundKind.PATTERN, None, sig_n
    return BackgroundKind.PHOTO, None, sig_n


def _delta_e(a: Sequence[float], b: Sequence[float]) -> float:
    """ΔE aproximado em Lab, a partir de duas cores RGB."""
    pa = np.array([[list(a)[:3]]], np.uint8)
    pb = np.array([[list(b)[:3]]], np.uint8)
    la = cv2.cvtColor(pa, cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
    lb = cv2.cvtColor(pb, cv2.COLOR_RGB2LAB).astype(np.float32)[0, 0]
    return float(np.linalg.norm(la - lb))


def _ring_stats(arr: np.ndarray, box: Box) -> tuple[tuple[int, int, int], float]:
    """Cor e espalhamento do anel ao redor da caixa — a "pastilha" do botão.

    O espalhamento é robusto (MAD, não desvio padrão) porque o anel quase
    sempre encosta em outra coisa num canto; um desvio padrão bruto seria
    dominado por esses poucos pixels e a pastilha nunca seria reconhecida.
    """
    h, w = arr.shape[:2]
    t = max(3, int(round(0.30 * box.h)))
    outer = box.pad(t, w, h)
    if outer.area <= box.area:
        return (0, 0, 0), 255.0
    sel = np.zeros((h, w), bool)
    sel[outer.y:outer.y1, outer.x:outer.x1] = True
    sel[box.y:box.y1, box.x:box.x1] = False
    px = arr[sel].reshape(-1, 3).astype(np.float32)
    if px.shape[0] < 20:
        return (0, 0, 0), 255.0
    med = np.median(px, axis=0)
    mad = 1.4826 * float(np.median(np.abs(px - med).max(axis=1)))
    return tuple(int(v) for v in med), mad  # type: ignore[return-value]


def _inner_bg(arr: np.ndarray, box: Box) -> tuple[BackgroundKind, tuple[int, int, int] | None]:
    """Classifica o fundo *dentro* da caixa, encolhida para não pegar a borda.

    A caixa detectada costuma incluir a borda da pastilha do CTA (o contorno
    arredondado é um gradiente forte e entra na componente conexa). Encolher
    ~8% garante que estamos medindo a cor do botão, não a transição para o
    fundo — que é o que decide se dá para apagar o texto de forma exata.
    """
    h, w = arr.shape[:2]
    b = box.clamp(w, h)
    shrink = max(2, int(round(0.08 * min(b.w, b.h))))
    inner = Box(b.x + shrink, b.y + shrink, b.w - 2 * shrink, b.h - 2 * shrink).clamp(w, h)
    if inner.area < 400:
        inner = b
    if inner.area < 16:
        return BackgroundKind.MIXED, None
    kind, color, _ = _region_kind(arr[inner.y:inner.y1, inner.x:inner.x1])
    return kind, color


def _measure_block(arr: np.ndarray, block: TextBlock) -> TextBlock:
    """Preenche ``background_color`` / ``on_solid_background`` a partir dos pixels.

    O motor de edição escolhe trilha determinística vs IA olhando para isto, e
    o modelo de visão não é confiável para dizer "é chapado" — pixel é.
    """
    h, w = arr.shape[:2]
    b = block.box.clamp(w, h)
    if b.area < 16:
        return block
    kind, color, sig_n = _region_kind(arr[b.y:b.y1, b.x:b.x1])
    if kind is not BackgroundKind.SOLID:
        kind, color = _inner_bg(arr, b)
    if kind is BackgroundKind.SOLID and color is not None:
        block.background_color = color
        block.on_solid_background = True
        return block

    # Caixa justa demais para medir o fundo por dentro (é o caso normal quando
    # o modelo devolve a caixa colada nos glifos): olhamos o anel em volta, que
    # é justamente o interior do botão/faixa.
    ring_color, ring_spread = _ring_stats(arr, b)
    if ring_spread <= max(4.0, 3.0 * sig_n):
        block.background_color = ring_color
        block.on_solid_background = True
    elif block.background_color is None and ring_spread <= 10.0:
        block.background_color = ring_color
    return block


def _image_background_kind(arr: np.ndarray, blocks: Iterable[TextBlock]) -> BackgroundKind:
    """Tipo de fundo do criativo inteiro, ignorando as áreas de texto.

    Amostra em escala reduzida: a decisão é sobre o *caráter* do fundo, não
    sobre detalhe, e reduzir corta o custo em ~10x.
    """
    h, w = arr.shape[:2]
    scale = 512.0 / max(h, w, 1)
    if scale < 1.0:
        small = cv2.resize(arr, (max(8, int(w * scale)), max(8, int(h * scale))),
                           interpolation=cv2.INTER_AREA)
    else:
        small = arr
        scale = 1.0

    kinds: list[BackgroundKind] = []
    sh, sw = small.shape[:2]
    covered = np.zeros((sh, sw), bool)
    for blk in blocks:
        b = blk.box.scale(scale).clamp(sw, sh)
        covered[b.y:b.y1, b.x:b.x1] = True

    # Quatro janelas nos cantos + centro; a moda dos rótulos ganha.
    win = max(24, min(sh, sw) // 3)
    spots = [(0, 0), (sw - win, 0), (0, sh - win), (sw - win, sh - win),
             ((sw - win) // 2, (sh - win) // 2)]
    for x0, y0 in spots:
        x0, y0 = max(0, x0), max(0, y0)
        patch = small[y0:y0 + win, x0:x0 + win]
        if patch.shape[0] < 8 or patch.shape[1] < 8:
            continue
        if covered[y0:y0 + win, x0:x0 + win].mean() > 0.6:
            continue
        kinds.append(_region_kind(patch)[0])

    if not kinds:
        return BackgroundKind.MIXED
    uniq = set(kinds)
    if len(uniq) == 1:
        return kinds[0]
    if uniq <= {BackgroundKind.SOLID, BackgroundKind.GRADIENT}:
        return BackgroundKind.GRADIENT
    if BackgroundKind.PHOTO in uniq or BackgroundKind.PATTERN in uniq:
        # Foto em parte da tela + faixa chapada é o arquétipo mais comum de
        # criativo de performance: "mixed" é a resposta honesta.
        return BackgroundKind.MIXED if len(uniq) > 1 else BackgroundKind.PHOTO
    return BackgroundKind.MIXED


# --------------------------------------------------------------------------- #
# Trilha offline: onde há texto
# --------------------------------------------------------------------------- #
def _stroke_stats(gray_patch: np.ndarray) -> tuple[float, float, float]:
    """``(largura_de_traço_máxima, coef_de_variação, contraste)`` de um recorte.

    Largura de traço e sua dispersão são o discriminador clássico de texto (SWT
    simplificado): letras têm traço quase constante, enquanto folhagem, textura
    de foto e ruído dão larguras muito dispersas. O contraste completa o par —
    texto de anúncio é feito para ser lido, então a diferença entre tinta e
    fundo é grande por construção; textura raramente passa dos 20 níveis.
    Sem estes dois filtros o detector morfológico enche a análise de falso
    positivo em criativo com foto.
    """
    if gray_patch.size < 64:
        return 0.0, 9.0, 0.0
    _, m = cv2.threshold(gray_patch, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    ink = (m > 0)
    if ink.mean() > 0.5:
        ink = ~ink          # polaridade: tinta é sempre a minoria
    if int(ink.sum()) < 24 or int((~ink).sum()) < 24:
        return 0.0, 9.0, 0.0
    g = gray_patch.astype(np.float32)
    contrast = abs(float(np.median(g[ink])) - float(np.median(g[~ink])))
    # Borda de zeros antes da transformada: o recorte é justo nos glifos, e sem
    # essa moldura a distância de um pixel colado na borda é medida contra
    # nada, inflando a largura de traço e derrubando palavras legítimas.
    padded = cv2.copyMakeBorder(ink.astype(np.uint8), 2, 2, 2, 2,
                                cv2.BORDER_CONSTANT, value=0)
    dt = cv2.distanceTransform(padded, cv2.DIST_L2, 3)[2:-2, 2:-2]
    vals = dt[ink]
    vals = vals[vals > 0.5]
    if vals.size < 12:
        return 0.0, 9.0, contrast
    mean = float(vals.mean())
    # Percentil 99 em vez do máximo: um único ponto gordo (um "@", um ícone
    # colado no texto) não deve condenar a linha inteira.
    return 2.0 * float(np.percentile(vals, 99)), float(vals.std() / max(mean, 1e-6)), contrast


def _detect_text_lines(arr: np.ndarray) -> list[Box]:
    """Linhas candidatas a texto, em pixels da imagem recebida.

    Gradiente morfológico realça a borda dos glifos (funciona com texto claro
    sobre escuro E o contrário, ao contrário de um threshold simples), Otsu
    binariza, e um fechamento horizontal com kernel do tamanho de ~1,5
    caractere cola as letras numa linha só.
    """
    h, w = arr.shape[:2]
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    grad = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    _, bw = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    kx = int(np.clip(round(0.016 * w), 5, 45))
    closed = cv2.morphologyEx(bw, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (kx, 1)))
    closed = cv2.morphologyEx(closed, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    # Piso de contraste ancorado no ruído da própria imagem: em JPEG ruim o
    # limiar sobe sozinho, em PNG chapado ele fica no mínimo de 18 níveis.
    min_contrast = max(18.0, 6.0 * _noise_sigma(gray))

    n, lbl, st, _ = cv2.connectedComponentsWithStats(closed, 8)
    out: list[Box] = []
    for i in range(1, n):
        x, y, bw_, bh, area = (int(st[i, cv2.CC_STAT_LEFT]), int(st[i, cv2.CC_STAT_TOP]),
                               int(st[i, cv2.CC_STAT_WIDTH]), int(st[i, cv2.CC_STAT_HEIGHT]),
                               int(st[i, cv2.CC_STAT_AREA]))
        if bh < max(6, 0.008 * h) or bh > 0.30 * h:
            continue
        if bw_ < 0.30 * bh or bw_ > 0.985 * w:
            continue
        if bw_ / max(bh, 1) > 60:
            continue
        fill = area / max(bw_ * bh, 1)
        if not (0.12 <= fill <= 0.99):
            continue
        # Densidade de traço: texto tem de 5% a 65% de tinta dentro da caixa.
        dens = float((bw[y:y + bh, x:x + bw_] > 0).mean())
        if not (0.05 <= dens <= 0.70):
            continue
        # Assinatura de texto: traço fino em relação à altura, largura de traço
        # consistente e contraste de leitura. Corta a maior parte do falso
        # positivo em foto.
        sw, cv_, contrast = _stroke_stats(gray[y:y + bh, x:x + bw_])
        if sw > 0.45 * bh or cv_ > 0.75 or contrast < min_contrast:
            continue
        out.append(Box(x, y, bw_, bh))
    return out


def _merge_while(boxes: list[Box], should_merge: Any, *, min_fill: float = 0.0
                 ) -> list[Box]:
    """Une pares de caixas repetidamente enquanto ``should_merge(a, b)`` for True.

    Aglomeração até o ponto fixo (não em uma passada só): "FRETE" + "GRÁTIS"
    viram uma linha, e só então essa linha pode se juntar à linha de baixo. Com
    n na casa das dezenas, o custo quadrático é irrelevante.

    ``min_fill`` é a trava contra o efeito dominó: guardamos a área realmente
    ocupada pelas partes e recusamos a união quando ela ficaria vazia demais.
    Duas linhas de um parágrafo preenchem ~75% da união; uma linha de texto e
    uma mancha de textura três linhas abaixo preenchem bem menos — e é esse
    encadeamento que fazia a headline engolir meia imagem.
    """
    items = [(b, float(b.area)) for b in boxes]
    merged = True
    while merged and len(items) > 1:
        merged = False
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (ba, ia), (bb, ib) = items[i], items[j]
                if not should_merge(ba, bb):
                    continue
                union = ba.union(bb)
                if min_fill > 0.0 and (ia + ib) < min_fill * max(union.area, 1):
                    continue
                items[i] = (union, ia + ib)
                del items[j]
                merged = True
                break
            if merged:
                break
    return [b for b, _ in items]


def _same_line(a: Box, b: Box) -> bool:
    """Palavras da mesma linha: mesma faixa vertical e separadas por um espaço."""
    ov_y = min(a.y1, b.y1) - max(a.y, b.y)
    if ov_y < 0.55 * min(a.h, b.h):
        return False
    if max(a.h, b.h) / max(min(a.h, b.h), 1) > 1.7:
        return False
    gap_x = max(a.x, b.x) - min(a.x1, b.x1)
    # 2.5x e não 1.1x. A altura da caixa é a de caixa alta, menor que o corpo da
    # fonte, e CTA costuma vir com letter-spacing; pior, um glifo redondo e fino
    # como o "O" às vezes não sobrevive à detecção e o buraco dele entra na
    # conta do espaço. Com 1.1x um "GARANTA O SEU" voltava partido em "GARANTA"
    # + "SEU" e a troca de texto pegava só um pedaço. Duas colunas distintas na
    # MESMA linha de base, com a MESMA altura, são raras em criativo de
    # performance — as travas de sobreposição vertical e de razão de altura
    # acima é que seguram a fusão indevida, não este limiar.
    return gap_x <= 2.5 * max(a.h, b.h)


def _stacked(a: Box, b: Box) -> bool:
    """Linhas empilhadas do mesmo bloco: alinhadas e coladas verticalmente."""
    ov_x = min(a.x1, b.x1) - max(a.x, b.x)
    if ov_x <= 0.30 * min(a.w, b.w):
        return False
    if max(a.h, b.h) / max(min(a.h, b.h), 1) > 1.9:
        return False
    gap_y = max(a.y, b.y) - min(a.y1, b.y1)
    return gap_y <= 0.85 * max(a.h, b.h)


def _overlapping(a: Box, b: Box) -> bool:
    """Sobreposição relevante: sobrou duplicata das etapas anteriores."""
    if not a.intersects(b):
        return False
    ix = min(a.x1, b.x1) - max(a.x, b.x)
    iy = min(a.y1, b.y1) - max(a.y, b.y)
    return (ix * iy) >= 0.25 * min(a.area, b.area)


def _group_lines(lines: list[Box], img_w: int, img_h: int) -> list[Box]:
    """Agrupa componentes em blocos: palavras -> linhas -> parágrafo.

    Três passadas em ordem fixa. O fechamento horizontal do detector usa um
    kernel proporcional à LARGURA DA IMAGEM, mas o espaço entre palavras é
    proporcional ao CORPO DA FONTE — então uma headline grande sempre volta
    quebrada em palavras, e é aqui que ela se reconstitui.
    """
    if not lines:
        return []
    boxes = sorted(lines, key=lambda b: (b.y, b.x))
    # Trava de segurança: um "bloco de texto" mais alto que um terço da peça é
    # quase sempre encadeamento de textura, e a caixa é a LICENÇA para
    # sobrescrever pixel — errar para o grande é destrutivo.
    max_h = 0.35 * img_h

    def stacked_limited(a: Box, b: Box) -> bool:
        return _stacked(a, b) and a.union(b).h <= max_h

    boxes = _merge_while(boxes, _same_line, min_fill=0.50)
    boxes = _merge_while(boxes, stacked_limited, min_fill=0.42)
    boxes = _merge_while(boxes, _overlapping)

    # Caixa "folgada": o pipeline de apagar prefere sobrar a faltar.
    out = [b.pad(max(2, int(round(0.045 * b.h))), img_w, img_h) for b in boxes]
    # Teto de blocos: dezenas de caixas numa peça é sintoma de textura
    # confundida com texto. Ficamos com as maiores, que são as que importam.
    out.sort(key=lambda b: -b.area)
    return sorted(out[:MAX_BLOCKS], key=lambda b: (b.y, b.x))


def _detect_faces(arr: np.ndarray) -> list[Box]:
    """Rostos, para virarem ``safe_areas``. Haar vem no wheel do opencv."""
    try:
        path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        if not path.is_file():
            return []
        clf = cv2.CascadeClassifier(str(path))
        if clf.empty():
            return []
    except Exception:  # noqa: BLE001 - detector é opcional, nunca derruba a análise
        return []
    h, w = arr.shape[:2]
    scale = 640.0 / max(h, w, 1)
    small = (cv2.resize(arr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
             if scale < 1.0 else arr)
    inv = 1.0 / scale if scale < 1.0 else 1.0
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    try:
        found = clf.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6,
                                     minSize=(24, 24))
    except cv2.error:
        return []
    out: list[Box] = []
    for (x, y, fw, fh) in found:
        b = Box(int(x * inv), int(y * inv), int(fw * inv), int(fh * inv))
        out.append(b.pad(int(0.25 * b.h), w, h))
    return out


def _classify_roles(arr: np.ndarray, boxes: list[Box]) -> list[TextBlock]:
    """Chuta o papel de cada bloco pela posição, tamanho e "pastilha" ao redor.

    Sem OCR não dá para ler "COMPRE AGORA"; o que dá para ver é que existe um
    bloco pequeno, no rodapé, dentro de um retângulo de cor chapada diferente
    do resto — e isso é um CTA em praticamente todo criativo de performance.
    """
    h, w = arr.shape[:2]
    if not boxes:
        return []

    global_bg = tuple(int(v) for v in np.median(arr.reshape(-1, 3), axis=0))
    infos: list[dict[str, Any]] = []
    for b in boxes:
        ring_color, ring_std = _ring_stats(arr, b)
        kind_in, color_in = _inner_bg(arr, b)
        # Duas assinaturas diferentes, e a diferença entre elas é o que separa
        # um BOTÃO de uma FAIXA: no botão a cor chapada acaba perto do texto;
        # na faixa ela atravessa o criativo de ponta a ponta. Sem essa
        # distinção, uma headline dentro da tarja inferior vira "CTA".
        row = int(np.clip(b.y + b.h // 2, 0, h - 1))
        edge_l = arr[row, max(0, int(0.02 * w))]
        edge_r = arr[row, min(w - 1, int(0.98 * w))]
        # A comparação é contra a cor SOB o texto: se ela vai até as bordas da
        # imagem, é faixa; se acaba antes, é botão.
        under = color_in if color_in is not None else ring_color
        full_width = (_delta_e(edge_l, under) < 12.0
                      and _delta_e(edge_r, under) < 12.0)
        on_pill = (color_in is not None and _delta_e(color_in, ring_color) >= 20.0
                   and not full_width)
        on_band = ring_std <= 8.0 and _delta_e(ring_color, global_bg) >= 22.0
        infos.append({
            "box": b,
            "cy": (b.y + b.h / 2.0) / max(h, 1),
            "hn": b.h / max(h, 1),
            "wn": b.w / max(w, 1),
            "on_pill": on_pill,
            "boxed": bool(on_pill or on_band),
            "ring": ring_color,
            "ring_std": ring_std,
            "kind_in": kind_in,
        })

    h_max = max(d["hn"] for d in infos)
    roles: list[TextRole] = []
    for d in infos:
        cy, hn, wn, boxed = d["cy"], d["hn"], d["wn"], d["boxed"]
        # CTA, selo e logo NUNCA são o maior texto da peça — é o que os separa
        # de uma headline que por acaso está sobre uma cor chapada.
        small = hn <= 0.65 * h_max or hn <= 0.045
        if hn <= 0.018 and cy >= 0.84:
            role = TextRole.LEGAL
        elif d["on_pill"] and cy >= 0.45 and small:
            role = TextRole.CTA
        elif boxed and cy >= 0.55 and hn <= 0.10 and small:
            role = TextRole.CTA
        elif cy >= 0.74 and hn <= 0.055 and wn <= 0.75 and small:
            role = TextRole.CTA
        elif boxed and cy <= 0.30 and hn <= 0.07 and small:
            role = TextRole.BADGE
        elif cy <= 0.12 and wn <= 0.32 and hn <= 0.06 and small:
            role = TextRole.LOGO
        else:
            role = TextRole.OTHER
        roles.append(role)

    # Headline = o maior bloco que sobrou. Determinar isto DEPOIS de marcar
    # CTA/selo/legal é o que faz o caso comum "headline dentro da faixa
    # inferior" funcionar — antes, qualquer coisa abaixo de 75% da altura era
    # descartada como candidata e o criativo voltava sem headline.
    livres = [i for i, r in enumerate(roles) if r is TextRole.OTHER]
    if livres:
        hi = max(livres, key=lambda i: (infos[i]["hn"], infos[i]["wn"]))
        if infos[hi]["hn"] >= 0.02:
            roles[hi] = TextRole.HEADLINE

    # Subhead = bloco logo abaixo da headline, menor que ela.
    if TextRole.HEADLINE in roles:
        hi = roles.index(TextRole.HEADLINE)
        head = infos[hi]
        for i, d in enumerate(infos):
            if roles[i] is not TextRole.OTHER or i == hi:
                continue
            below = 0 <= (d["box"].y - head["box"].y1) <= 1.6 * head["box"].h
            smaller = 0.25 <= d["hn"] / max(head["hn"], 1e-6) <= 0.92
            # Precisa estar debaixo da headline, não em qualquer lugar da faixa:
            # sem isso um respingo de textura da foto virava "subhead".
            ov = min(d["box"].x1, head["box"].x1) - max(d["box"].x, head["box"].x)
            aligned = ov > 0.35 * min(d["box"].w, head["box"].w) and d["wn"] >= 0.12
            if below and smaller and aligned:
                roles[i] = TextRole.SUBHEAD
                break

    blocks: list[TextBlock] = []
    for d, role in zip(infos, roles):
        b: Box = d["box"]
        style = FontSpec(
            size_px=max(6, int(round(b.h * 0.78))),
            align="center" if role in (TextRole.HEADLINE, TextRole.CTA, TextRole.BADGE) else "left",
            weight="bold" if role in (TextRole.HEADLINE, TextRole.CTA) else "regular",
            uppercase=role in (TextRole.CTA, TextRole.BADGE),
        )
        blk = TextBlock(box=b, text="", role=role, style=style,
                        confidence=0.55 if role is not TextRole.OTHER else 0.35)
        blocks.append(_measure_block(arr, blk))
    return blocks


# Verbos que abrem chamada para ação em criativo brasileiro. Serve para separar
# o CTA de verdade de um selo de preço quando os dois estão sobre cor chapada.
_CTA_VERBS = (
    "garanta", "compre", "quero", "saiba", "clique", "baixe", "agende", "assine",
    "aproveite", "peca", "peça", "fale", "chame", "veja", "acesse", "cadastre",
    "inscreva", "solicite", "reserve", "participe", "comprar", "adquira",
    "conheca", "conheça", "descubra", "experimente", "teste", "comece", "vagas",
    "ultimas", "últimas", "agora", "ja", "já",
)

_PRICE_RE = re.compile(
    r"(r\$|us\$|\$|€|£)\s*\d|"          # R$ 97, $19
    r"^\s*\d+([.,]\d+)?\s*(reais|off|%)?\s*$|"   # 97, 19,90, 30%
    r"\d+\s*x\s*(de\s*)?(r\$)?\s*\d",         # 12x de R$ 97
    re.IGNORECASE,
)


def _fill_text_with_ocr(arr: np.ndarray, blocks: list[TextBlock]) -> bool:
    """Lê o texto de cada bloco com o Tesseract e ajusta os papéis.

    Devolve True se o OCR rodou. Sem Tesseract não é erro: os blocos ficam com
    ``text`` vazio, exatamente como antes, e quem chama cai para --papel/--caixa.
    """
    if not blocks or not _ocr.ocr_available():
        return False
    # Duas chamadas ao Tesseract para a peça toda, e não uma por bloco: ler a
    # página inteira e distribuir as palavras por geometria é ~10x mais rápido
    # num lote, com a mesma leitura.
    try:
        lidos = _ocr.ocr_page_by_blocks(arr, [b.box for b in blocks])
    except Exception as exc:  # noqa: BLE001 - OCR é auxiliar, nunca derruba a análise
        log.debug("OCR da página falhou: %s", exc)
        return False

    # Bloco que a leitura da página não cobriu ganha uma segunda chance com o
    # recorte isolado, que às vezes salva texto de baixo contraste.
    # No máximo 2 blocos e em modo `quick`: a repescagem é rede de segurança
    # para texto de baixo contraste, e sem esse teto ela custava mais tempo do
    # que a leitura da página inteira.
    faltando = [i for i, (t, _) in enumerate(lidos) if not t][:2]
    if faltando:
        def _reler(i: int) -> tuple[int, tuple[str, float]]:
            try:
                return (i, _ocr.ocr_box(arr, blocks[i].box, quick=True))
            except Exception:  # noqa: BLE001
                return (i, ("", -1.0))
        with ThreadPoolExecutor(max_workers=min(2, len(faltando))) as pool:
            for i, res in pool.map(_reler, faltando):
                if res[0]:
                    lidos[i] = res

    for blk, (texto, conf) in zip(blocks, lidos):
        if texto and conf >= 45:
            blk.text = texto
            # A confiança do bloco passa a valer alguma coisa: sabemos o que está escrito.
            blk.confidence = max(blk.confidence, min(0.95, conf / 100.0))
    _refine_roles_with_text(blocks)
    return True


def _refine_roles_with_text(blocks: list[TextBlock]) -> None:
    """Corrige os papéis agora que sabemos o que cada bloco diz.

    Sem texto, um selo de preço amarelo e uma faixa de CTA rosa são a mesma
    coisa para a heurística — bloco pequeno sobre cor chapada na metade de
    baixo. Lendo "R$ 97" a diferença fica óbvia.
    """
    for blk in blocks:
        if not blk.text:
            continue
        txt = blk.text.strip()
        if blk.role in (TextRole.CTA, TextRole.BADGE, TextRole.OTHER) and _PRICE_RE.search(txt):
            blk.role = TextRole.PRICE

    ctas = [b for b in blocks if b.role is TextRole.CTA]
    if len(ctas) <= 1:
        return
    # Mais de um candidato: fica o que fala como CTA; empatou, fica o de baixo,
    # que é onde o botão vive em criativo de performance.
    def pontua(b: TextBlock) -> tuple[int, int]:
        norm = _ocr.normalize(b.text)
        verbo = any(v in norm.split() or norm.startswith(v) for v in _CTA_VERBS)
        return (1 if verbo else 0, b.box.y)

    vencedor = max(ctas, key=pontua)
    for b in ctas:
        if b is not vencedor:
            b.role = TextRole.BADGE


def heuristic_analysis(path: str | Path) -> CreativeAnalysis:
    """Análise 100% offline: onde há texto, paleta, tipo de fundo, rostos.

    ``TextBlock.text`` fica **vazio** de propósito — não há OCR aqui. Isso é
    suficiente para localizar e apagar (o caso crítico sem chave) e para
    ``find_text_block`` por papel ou por caixa; casar por texto exige a trilha
    de IA.
    """
    p = Path(path)
    img = load_image(p)
    arr = _rgb_array(img)
    h, w = arr.shape[:2]

    lines = _detect_text_lines(arr)
    boxes = _group_lines(lines, w, h)
    blocks = _classify_roles(arr, boxes)
    ocr_usado = _fill_text_with_ocr(arr, blocks)

    safe = _detect_faces(arr)
    for blk in blocks:
        if blk.role is TextRole.LOGO:
            safe.append(blk.box)

    kind = _image_background_kind(arr, blocks)
    palette = dominant_colors(img, k=5)

    if ocr_usado:
        notes = ("Análise offline (sem IA): caixas detectadas por pixel e texto lido "
                 "pelo Tesseract. Casar por texto (--de) funciona; para papéis e "
                 "estilo mais finos, configure OPENAI_API_KEY.")
    else:
        notes = ("Análise offline (sem IA e sem OCR): as caixas foram detectadas por "
                 "pixel e o texto não foi lido — use --papel ou --caixa. Instale o "
                 "Tesseract para casar por texto, ou configure OPENAI_API_KEY.")
    return CreativeAnalysis(
        path=p,
        width=w,
        height=h,
        text_blocks=blocks,
        palette=palette,
        background_kind=kind,
        layout_archetype=_guess_archetype(arr, blocks, kind),
        subject_description="",
        safe_areas=safe,
        notes=notes,
        source="heuristic",
    )


def _guess_archetype(arr: np.ndarray, blocks: Sequence[TextBlock],
                    kind: BackgroundKind) -> str:
    """Rótulo curto e legível do layout, útil no relatório e no DNA."""
    h = arr.shape[0]
    if not blocks:
        return "sem texto detectado"
    bottom = [b for b in blocks if (b.box.y + b.box.h / 2) / h >= 0.66]
    top = [b for b in blocks if (b.box.y + b.box.h / 2) / h <= 0.34]
    band = any(b.on_solid_background for b in bottom)
    base = {
        BackgroundKind.SOLID: "fundo chapado",
        BackgroundKind.GRADIENT: "fundo em degradê",
        BackgroundKind.PHOTO: "foto full-bleed",
        BackgroundKind.PATTERN: "fundo com padrão",
        BackgroundKind.MIXED: "foto + área chapada",
    }[kind]
    if band and bottom:
        return f"{base} + faixa inferior com texto"
    if top and bottom:
        return f"{base} + texto no topo e no rodapé"
    if top:
        return f"{base} + texto no topo"
    if bottom:
        return f"{base} + texto no rodapé"
    return f"{base} + texto centralizado"


# --------------------------------------------------------------------------- #
# Trilha IA
# --------------------------------------------------------------------------- #
_ROLE_VALUES = [r.value for r in TextRole]

_BOX_SCHEMA: dict[str, Any] = {
    "type": "object",
    "description": "Caixa NORMALIZADA (0.0-1.0) relativa à largura/altura da imagem.",
    "properties": {
        "x": {"type": "number"},
        "y": {"type": "number"},
        "w": {"type": "number"},
        "h": {"type": "number"},
    },
    "required": ["x", "y", "w", "h"],
    "additionalProperties": False,
}

_STYLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "family": {"type": "string", "description": "Família aparente, ex.: Inter, Montserrat, Poppins."},
        "weight": {"type": "string", "enum": list(_WEIGHTS)},
        "italic": {"type": "boolean"},
        "color": {"type": "string", "description": "Cor do texto em hex, ex.: #ffffff"},
        "align": {"type": "string", "enum": ["left", "center", "right"]},
        "uppercase": {"type": "boolean"},
        "stroke_width": {"type": "integer"},
        "stroke_color": {"type": ["string", "null"]},
        "shadow": {"type": "boolean"},
        "line_height": {"type": "number"},
    },
    "required": ["family", "weight", "italic", "color", "align", "uppercase",
                 "stroke_width", "stroke_color", "shadow", "line_height"],
    "additionalProperties": False,
}

_ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text_blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "role": {"type": "string", "enum": _ROLE_VALUES},
                    "box": _BOX_SCHEMA,
                    "lines": {"type": "integer"},
                    "style": _STYLE_SCHEMA,
                    "background_color": {"type": ["string", "null"]},
                    "on_solid_background": {"type": "boolean"},
                    "confidence": {"type": "number"},
                },
                "required": ["text", "role", "box", "lines", "style",
                             "background_color", "on_solid_background", "confidence"],
                "additionalProperties": False,
            },
        },
        "palette": {"type": "array", "items": {"type": "string"}},
        "background_kind": {"type": "string", "enum": [k.value for k in BackgroundKind]},
        "layout_archetype": {"type": "string"},
        "subject_description": {"type": "string"},
        "safe_areas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "box": _BOX_SCHEMA},
                "required": ["label", "box"],
                "additionalProperties": False,
            },
        },
        "notes": {"type": "string"},
    },
    "required": ["text_blocks", "palette", "background_kind", "layout_archetype",
                 "subject_description", "safe_areas", "notes"],
    "additionalProperties": False,
}

_SYSTEM_PROMPT = (
    "Você analisa criativos publicitários para um motor de edição em lote. "
    "Sua saída é lida por um programa: devolva SOMENTE JSON válido, sem markdown, "
    "sem comentário e sem texto fora do objeto."
)

_USER_PROMPT = """Analise este criativo e devolva o JSON descrito abaixo.

REGRAS DAS CAIXAS (isto é o mais importante):
- Todas as caixas são NORMALIZADAS de 0.0 a 1.0: x e w em fração da LARGURA,
  y e h em fração da ALTURA. Origem no canto superior esquerdo.
- A caixa deve envolver TODO o texto do bloco, com uma folga pequena
  (uns 3% da altura do bloco em cada lado). É melhor sobrar do que faltar:
  quem apaga o texto usa esta caixa como licença para mexer em pixel.
- Um bloco = um agrupamento visual (uma headline de duas linhas é UM bloco).
  Não devolva um bloco por palavra.
- "lines" = quantas linhas de texto o bloco tem.

TEXTO:
- "text" é o texto EXATO como aparece, com acento, pontuação e a mesma caixa
  (se está em CAIXA ALTA, escreva em CAIXA ALTA). Quebras de linha viram \\n.

PAPÉIS (role):
- headline: a mensagem principal, o maior texto.
- subhead: apoio da headline.
- cta: chamada para ação (COMPRE AGORA, SAIBA MAIS, GARANTA O SEU) — quase
  sempre pequeno, no terço inferior, muitas vezes dentro de um botão/pastilha.
- price: preço ou desconto. badge: selo (NOVO, -50%, FRETE GRÁTIS).
- legal: letra miúda, termos. logo: marca. other: o resto.

ESTILO: família aparente (nome de fonte real ou o parecido mais próximo),
peso, itálico, cor do texto em hex, alinhamento, se está em caixa alta,
contorno (stroke) e sombra. Se o bloco está sobre uma cor chapada, informe
background_color em hex e on_solid_background=true.

ÁREAS SEGURAS (safe_areas): regiões que NUNCA podem ser alteradas — logo,
rosto de pessoa, produto, selo de patrocínio. Uma caixa por elemento, com
label curto em português.

PALETA: até 6 cores em hex, da mais presente para a menos.
background_kind: solid | gradient | photo | pattern | mixed.
layout_archetype: frase curta, ex.: "foto full-bleed + faixa inferior".
subject_description: uma frase sobre o que a imagem mostra.
notes: qualquer coisa que atrapalhe editar este criativo (texto sobre rosto,
degradê atrás do CTA, etc.).
"""


def _jpeg_data_url(img: Image.Image, max_side: int = VISION_MAX_SIDE) -> str:
    """Reduz para ``max_side`` e devolve data URL JPEG (q=88).

    Reduzir é o que baratea a chamada; como pedimos caixa normalizada, a
    redução não afeta a precisão em pixels da imagem original.
    """
    work = img.convert("RGB") if img.mode != "RGB" else img
    if max(work.size) > max_side:
        s = max_side / max(work.size)
        work = work.resize((max(1, int(work.width * s)), max(1, int(work.height * s))),
                           Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    work.save(buf, "JPEG", quality=88, optimize=True)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _parse_json(raw: str) -> dict[str, Any]:
    """Parse tolerante: JSON puro, cercado por ```json, ou embutido em prosa.

    O último recurso extrai o MAIOR objeto balanceado do texto — é o padrão que
    o ORION Studio já usa e que salva a análise quando o modelo resolve
    escrever "Aqui está o JSON:" antes do objeto.
    """
    text = (raw or "").strip()
    if not text:
        return {}
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass

    # Varredura balanceada: pega o maior objeto de nível superior.
    best: dict[str, Any] = {}
    depth = 0
    start = -1
    in_str = False
    esc = False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                chunk = text[start:i + 1]
                try:
                    cand = json.loads(chunk)
                except json.JSONDecodeError:
                    cand = None
                if isinstance(cand, dict) and len(chunk) > len(json.dumps(best)):
                    best = cand
                start = -1
    return best


def _retry_next(exc: Exception) -> bool:
    """True quando vale tentar outro formato de resposta (parâmetro recusado)."""
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    if isinstance(exc, TypeError):
        return True
    if "badrequest" in name or "unprocessable" in name or "notfound" in name:
        return True
    return any(t in msg for t in ("response_format", "json_schema", "unsupported",
                                 "not supported", "invalid_request", "temperature",
                                 "max_tokens"))


def _chat_json(client: Any, model: str, messages: list[dict[str, Any]],
               schema: dict[str, Any] | None, schema_name: str,
               max_tokens: int = 3000) -> dict[str, Any]:
    """Pede JSON ao modelo, degradando o mecanismo de forçar formato.

    Ordem: ``json_schema`` estrito (o mais confiável quando o modelo suporta)
    -> ``json_object`` -> nada + extração do maior objeto do texto. Assim o
    módulo continua funcionando se o usuário apontar ``vision_model`` para um
    modelo antigo que não conhece structured outputs.
    """
    variants: list[dict[str, Any]] = []
    if schema:
        variants.append({
            "response_format": {"type": "json_schema",
                                "json_schema": {"name": schema_name, "strict": True,
                                                "schema": schema}},
            "temperature": 0.1,
        })
    variants.append({"response_format": {"type": "json_object"}, "temperature": 0.1})
    variants.append({"response_format": {"type": "json_object"}})
    variants.append({})

    last_exc: Exception | None = None
    for extra in variants:
        for token_key in ("max_tokens", "max_completion_tokens"):
            kw = dict(extra)
            kw[token_key] = max_tokens
            try:
                resp = client.chat.completions.create(model=model, messages=messages, **kw)
            except Exception as exc:  # noqa: BLE001 - degradamos de propósito
                last_exc = exc
                if _retry_next(exc):
                    continue
                raise
            data = _parse_json(resp.choices[0].message.content or "")
            if data:
                return data
            last_exc = ValueError("o modelo respondeu sem JSON utilizável")
            break
    if last_exc is not None:
        raise last_exc
    return {}


def _openai_client(settings: Settings) -> Any:
    """Cliente da OpenAI. Import tardio: ``import s7editor.vision`` é barato."""
    from openai import OpenAI  # import local de propósito

    return OpenAI(api_key=settings.openai_api_key, max_retries=2, timeout=90.0)


def _size_from_box(box: Box, lines: int, line_height: float) -> int:
    """Corpo de fonte aproximado a partir da altura da caixa e do nº de linhas.

    Serve de *semente* para ``textedit.infer_style_from_pixels`` e para a busca
    binária de corpo — o valor final sempre vem da medida em pixel.
    """
    n = max(1, int(lines))
    lh = float(line_height) if line_height and line_height > 0.5 else 1.2
    denom = (n - 1) * lh + 1.18
    return max(6, int(round(box.h / max(denom, 0.5))))


def _blocks_from_payload(payload: dict[str, Any], width: int, height: int) -> list[TextBlock]:
    out: list[TextBlock] = []
    for raw in payload.get("text_blocks") or []:
        if not isinstance(raw, dict):
            continue
        raw_box = raw.get("box") or raw.get("bbox")
        if not isinstance(raw_box, dict):
            continue
        d = dict(raw)
        # "norm": True remove qualquer ambiguidade em Box.from_any — sempre
        # pedimos caixa normalizada, mesmo que ela pareça pixel por acidente.
        d["box"] = {**raw_box, "norm": True}
        style = dict(raw.get("style") or {})
        if str(style.get("weight", "")).lower() not in _WEIGHTS:
            style["weight"] = "bold"
        d["style"] = style
        try:
            blk = TextBlock.from_dict(d, width, height)
        except Exception:  # noqa: BLE001 - bloco malformado não derruba a análise
            continue
        if blk.box.area < 16:
            continue
        blk.style.size_px = _size_from_box(blk.box, raw.get("lines") or 1,
                                           blk.style.line_height)
        if not blk.style.family:
            blk.style.family = "Inter"
        if blk.style.uppercase and blk.text:
            # O modelo às vezes marca uppercase e devolve o texto normalizado.
            blk.style.uppercase = blk.text.upper() == blk.text and any(c.isalpha() for c in blk.text)
        out.append(blk)
    return out


def _analysis_from_payload(payload: dict[str, Any], path: Path, img: Image.Image,
                           arr: np.ndarray) -> CreativeAnalysis:
    w, h = img.width, img.height
    blocks = [_measure_block(arr, b) for b in _blocks_from_payload(payload, w, h)]

    palette = [parse_color(c) for c in (payload.get("palette") or []) if c]
    if not palette:
        palette = dominant_colors(img, k=5)

    try:
        kind = BackgroundKind(str(payload.get("background_kind") or "").lower())
    except ValueError:
        kind = _image_background_kind(arr, blocks)

    safe: list[Box] = []
    for raw in payload.get("safe_areas") or []:
        rb = raw.get("box") if isinstance(raw, dict) else raw
        if not isinstance(rb, dict):
            continue
        try:
            b = Box.from_any({**rb, "norm": True}, w, h)
        except ValueError:
            continue
        if b.area > 0:
            safe.append(b)

    return CreativeAnalysis(
        path=path,
        width=w,
        height=h,
        text_blocks=blocks,
        palette=palette[:6],
        background_kind=kind,
        layout_archetype=str(payload.get("layout_archetype") or ""),
        subject_description=str(payload.get("subject_description") or ""),
        safe_areas=safe,
        notes=str(payload.get("notes") or ""),
        source="vision",
    )


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #
def _cache_path(settings: Settings, img: Image.Image, model: str) -> Path:
    """Chave = SHA do conteúdo em pixels + modelo + versão do prompt."""
    key = hashlib.sha256(
        f"{image_sha(img)}|{model}|{PROMPT_VERSION}".encode("ascii")
    ).hexdigest()[:40]
    return Path(settings.cache_dir) / "vision" / f"{key}.json"


def _cache_read(path: Path, target: Path) -> CreativeAnalysis | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        analysis = CreativeAnalysis.from_dict(data)
    except Exception:  # noqa: BLE001 - cache corrompido é só cache
        return None
    analysis.path = target       # o cache é por conteúdo; o caminho é do agora
    analysis.source = "cache"
    return analysis


def _cache_write(path: Path, analysis: CreativeAnalysis) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(analysis.to_dict(), indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(path)        # escrita atômica: dois workers não se atropelam
    except OSError:
        pass                     # cache é otimização, nunca motivo de falha


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def analyze_creative(path: str | Path, settings: Settings | None = None, *,
                     cache: bool = True) -> CreativeAnalysis:
    """Analisa um criativo e devolve :class:`CreativeAnalysis`.

    Com chave configurada usa o modelo de visão; sem chave (ou se a chamada
    falhar) cai para :func:`heuristic_analysis` e registra o motivo em
    ``notes``. Nunca levanta por causa de rede — quem chama está quase sempre
    no meio de um lote de 30 imagens e uma falha não pode derrubar as outras.
    """
    p = Path(path)
    settings = settings or load_settings()
    img = load_image(p)
    arr = _rgb_array(img)

    if not settings.openai_api_key:
        # Cacheia igual ao caminho com IA: a análise offline agora roda OCR, que
        # é barato em dinheiro e caro em tempo. A chave do cache inclui se havia
        # OCR, senão instalar o Tesseract depois não invalidaria nada.
        marca = "heuristic+ocr" if _ocr.ocr_available() else "heuristic"
        cpath = _cache_path(settings, img, marca)
        if cache:
            hit = _cache_read(cpath, p)
            if hit is not None:
                return hit
        analysis = heuristic_analysis(p)
        if cache:
            _cache_write(cpath, analysis)
        return analysis

    cpath = _cache_path(settings, img, settings.vision_model)
    if cache:
        hit = _cache_read(cpath, p)
        if hit is not None:
            return hit

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": _USER_PROMPT},
            {"type": "image_url",
             "image_url": {"url": _jpeg_data_url(img), "detail": "high"}},
        ]},
    ]

    try:
        client = _openai_client(settings)
        payload = _chat_json(client, settings.vision_model, messages,
                             _ANALYSIS_SCHEMA, "creative_analysis")
    except Exception as exc:  # noqa: BLE001 - degradação elegante é o contrato
        analysis = heuristic_analysis(p)
        analysis.notes = (
            f"A análise por IA falhou ({type(exc).__name__}: {str(exc)[:160]}); "
            "usei a detecção offline. Rode `s7editor doctor` para checar a chave "
            "e a conexão."
        )
        return analysis

    analysis = _analysis_from_payload(payload, p, img, arr)
    if not analysis.text_blocks:
        # O modelo não achou texto: pode ser verdade, mas checamos com pixel
        # antes de devolver um criativo "sem texto" para o pipeline.
        fallback = heuristic_analysis(p)
        if fallback.text_blocks:
            analysis.text_blocks = fallback.text_blocks
            analysis.notes = ((analysis.notes + " ") if analysis.notes else "") + (
                "O modelo não retornou blocos de texto; usei as caixas detectadas "
                "por pixel (sem o texto lido)."
            )
    if not analysis.safe_areas:
        analysis.safe_areas = _detect_faces(arr)

    if cache and analysis.source == "vision":
        _cache_write(cpath, analysis)
    return analysis


def analyze_batch(paths: Sequence[str | Path], settings: Settings | None = None, *,
                  max_workers: int = 4) -> list[CreativeAnalysis]:
    """Analisa várias imagens em paralelo, preservando a ordem de entrada.

    ``settings.max_concurrency`` é o TETO: passar ``max_workers`` maior não
    aumenta a paralelização (a conta da OpenAI é do usuário e ele configura o
    limite num lugar só). Uma falha individual vira uma análise offline ou, no
    pior caso, uma análise vazia com o erro em ``notes`` — o lote nunca cai.
    """
    settings = settings or load_settings()
    items = [Path(p) for p in paths]
    if not items:
        return []

    workers = max(1, min(int(max_workers or 1), int(settings.max_concurrency or 1)))

    def one(p: Path) -> CreativeAnalysis:
        try:
            return analyze_creative(p, settings)
        except Exception as exc:  # noqa: BLE001 - isolamos a falha na imagem
            return CreativeAnalysis(
                path=p, width=0, height=0,
                notes=f"não consegui analisar {p.name}: {type(exc).__name__}: {str(exc)[:200]}",
                source="error",
            )

    if workers == 1 or len(items) == 1:
        return [one(p) for p in items]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, items))


def find_text_block(analysis: CreativeAnalysis, *, find: str | None = None,
                    role: Any = None, box: Any = None,
                    fuzzy: bool = True) -> TextBlock | None:
    """Acha o bloco que o usuário quis dizer, por papel, caixa e/ou texto.

    O casamento por texto ignora acento, caixa e pontuação: o usuário digita
    ``"garanta o seu"`` e encontramos ``"GARANTA O SEU!"``. Com ``fuzzy=False``
    exige igualdade dessa forma normalizada (ainda ignora acento/caixa —
    exigir byte a byte só geraria frustração).

    Os critérios se combinam: ``role`` filtra, ``box`` restringe às caixas que
    de fato encostam na região pedida, e ``find`` desempata.
    """
    blocks = list(analysis.text_blocks or [])
    if not blocks:
        return None

    wanted = _coerce_role(role)
    if wanted is not None:
        by_role = [b for b in blocks if b.role == wanted]
        if by_role:
            blocks = by_role
        elif find is None and box is None:
            return None

    if box is not None:
        try:
            target = box if isinstance(box, Box) else Box.from_any(
                box, analysis.width or 1, analysis.height or 1)
        except ValueError:
            target = None
        if target is not None and target.area > 0:
            scored = sorted(((b.box.iou(target), b) for b in blocks),
                            key=lambda t: -t[0])
            overlapping = [b for s, b in scored if s > 0.0]
            if not overlapping:
                # Nenhuma sobreposição: aceita o bloco cujo centro esteja dentro
                # da caixa pedida (usuário costuma marcar um ponto, não a área).
                cx, cy = target.center
                inside = [b for b in blocks
                          if b.box.x <= cx <= b.box.x1 and b.box.y <= cy <= b.box.y1]
                if not inside:
                    return None
                overlapping = inside
            if find is None:
                return overlapping[0]
            blocks = overlapping

    if find is not None:
        best: TextBlock | None = None
        best_score = 0.0
        for b in blocks:
            s = _text_score(find, b.text)
            if s > best_score:
                best, best_score = b, s
        threshold = FUZZY_THRESHOLD if fuzzy else 0.999
        return best if best_score >= threshold else None

    return blocks[0] if (wanted is not None or box is not None) else None


# --------------------------------------------------------------------------- #
# DNA de um conjunto de referências
# --------------------------------------------------------------------------- #
def _merge_palette(analyses: Sequence[CreativeAnalysis], k: int = 6
                   ) -> list[tuple[int, int, int]]:
    """Junta as paletas de N criativos agrupando cores próximas em Lab.

    Agrupamento guloso com ΔE ≤ 18: é o suficiente para dizer que o "azul da
    marca" que aparece com 2 níveis de compressão diferentes é a mesma cor.
    """
    clusters: list[list[tuple[int, int, int]]] = []
    weights: list[float] = []
    for a in analyses:
        for rank, c in enumerate(a.palette or []):
            w = 1.0 / (1.0 + rank)     # a primeira cor da paleta pesa mais
            for i, cl in enumerate(clusters):
                if _delta_e(cl[0], c) <= 18.0:
                    cl.append(c)
                    weights[i] += w
                    break
            else:
                clusters.append([c])
                weights.append(w)
    order = sorted(range(len(clusters)), key=lambda i: -weights[i])
    out: list[tuple[int, int, int]] = []
    for i in order[:k]:
        arr = np.array(clusters[i], np.float32)
        out.append(tuple(int(round(v)) for v in arr.mean(axis=0)))  # type: ignore[arg-type]
    return out


def _most_common(values: Iterable[str], n: int = 1) -> list[str]:
    counts: dict[str, int] = {}
    for v in values:
        s = str(v or "").strip()
        if s:
            counts[s] = counts.get(s, 0) + 1
    return [k for k, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def _aspect_label(w: int, h: int) -> str:
    if not w or not h:
        return "9:16"
    r = w / h
    known = {"9:16": 9 / 16, "4:5": 4 / 5, "1:1": 1.0, "16:9": 16 / 9,
             "3:4": 3 / 4, "2:3": 2 / 3, "3:2": 3 / 2}
    return min(known.items(), key=lambda kv: abs(kv[1] - r))[0]


_DNA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject_matter": {"type": "string"},
        "mood": {"type": "string"},
        "layout_archetype": {"type": "string"},
        "logo_placement": {"type": "string"},
        "copy_patterns": {"type": "array", "items": {"type": "string"}},
        "cta_patterns": {"type": "array", "items": {"type": "string"}},
        "do_not": {"type": "array", "items": {"type": "string"}},
        "prompt_seed": {"type": "string"},
    },
    "required": ["subject_matter", "mood", "layout_archetype", "logo_placement",
                 "copy_patterns", "cta_patterns", "do_not", "prompt_seed"],
    "additionalProperties": False,
}


def extract_dna(analyses: Sequence[CreativeAnalysis],
                settings: Settings | None = None) -> CreativeDNA:
    """Destila o padrão comum de um conjunto de referências.

    A parte estrutural (paleta, fontes, aspecto, textos de headline/CTA) é
    agregada de forma determinística — dá o mesmo resultado offline e online.
    Com chave, um passo de texto (sem imagem, portanto barato) escreve a parte
    subjetiva: assunto, mood e o ``prompt_seed`` que ``variations.py`` usa.
    """
    settings = settings or load_settings()
    valid = [a for a in analyses if a and a.width and a.height]
    if not valid:
        return CreativeDNA(sample_count=0)

    fonts = _most_common(
        (b.style.family for a in valid for b in a.text_blocks if b.style.family), 4)
    headlines: list[str] = []
    ctas: list[str] = []
    for a in valid:
        for b in a.text_blocks:
            t = (b.text or "").strip()
            if not t:
                continue
            if b.role in (TextRole.HEADLINE, TextRole.SUBHEAD):
                headlines.append(t)
            elif b.role in (TextRole.CTA, TextRole.BADGE):
                ctas.append(t)

    aspect = _most_common([_aspect_label(a.width, a.height) for a in valid], 1)
    archetype = _most_common([a.layout_archetype for a in valid], 1)
    logo_place = ""
    for a in valid:
        blk = a.block_by_role(TextRole.LOGO)
        if blk:
            cy = (blk.box.y + blk.box.h / 2) / max(a.height, 1)
            cx = (blk.box.x + blk.box.w / 2) / max(a.width, 1)
            vert = "topo" if cy < 0.34 else ("rodapé" if cy > 0.66 else "meio")
            horz = "esquerda" if cx < 0.34 else ("direita" if cx > 0.66 else "centro")
            logo_place = f"{vert} {horz}"
            break

    dna = CreativeDNA(
        palette=_merge_palette(valid),
        fonts=fonts,
        layout_archetype=archetype[0] if archetype else "",
        subject_matter=_most_common([a.subject_description for a in valid], 1)[0]
        if any(a.subject_description for a in valid) else "",
        mood="",
        copy_patterns=list(dict.fromkeys(headlines))[:12],
        cta_patterns=list(dict.fromkeys(ctas))[:12],
        logo_placement=logo_place,
        aspect=aspect[0] if aspect else "9:16",
        do_not=[
            "não alterar logo, rosto ou produto",
            "não gerar texto ilegível ou marca d'água",
            "não mudar a paleta da marca",
        ],
        prompt_seed="",
        sample_count=len(valid),
    )

    # Semente determinística: já é utilizável sem IA nenhuma.
    hexes = ", ".join(color_to_hex(c) for c in dna.palette[:4])
    dna.prompt_seed = (
        f"Criativo publicitário {dna.aspect}. {dna.layout_archetype or 'layout limpo'}. "
        f"Paleta: {hexes}. "
        f"{('Assunto: ' + dna.subject_matter + '. ') if dna.subject_matter else ''}"
        "Sem texto, sem logo, sem marca d'água."
    ).strip()

    if not settings.openai_api_key:
        return dna

    resumo = json.dumps({
        "aspecto": dna.aspect,
        "paleta": [color_to_hex(c) for c in dna.palette],
        "fontes": dna.fonts,
        "arquetipos": _most_common([a.layout_archetype for a in valid], 5),
        "assuntos": [a.subject_description for a in valid if a.subject_description][:10],
        "headlines": dna.copy_patterns,
        "ctas": dna.cta_patterns,
        "observacoes": [a.notes for a in valid if a.notes][:5],
    }, ensure_ascii=False)[:6000]

    messages = [
        {"role": "system", "content":
            "Você destila o padrão visual de uma marca a partir da análise de vários "
            "criativos. Responda SOMENTE com JSON válido, em português do Brasil."},
        {"role": "user", "content":
            "Estes são os dados extraídos de "
            f"{len(valid)} criativos de referência da mesma marca:\n\n{resumo}\n\n"
            "Devolva o JSON com: subject_matter (o que os criativos mostram), "
            "mood (2 a 4 adjetivos), layout_archetype (frase curta), logo_placement, "
            "copy_patterns (o PADRÃO das headlines: estrutura, tom, tamanho — não "
            "copie as frases), cta_patterns (padrão dos CTAs), do_not (o que jamais "
            "fazer ao gerar um criativo novo desta marca) e prompt_seed (um prompt "
            "em INGLÊS para gerar o FUNDO de um criativo novo desta marca, sem "
            "nenhum texto, sem logo e sem marca d'água)."},
    ]
    try:
        client = _openai_client(settings)
        payload = _chat_json(client, settings.vision_model, messages,
                             _DNA_SCHEMA, "creative_dna", max_tokens=1200)
    except Exception:  # noqa: BLE001 - a versão determinística já é válida
        return dna

    dna.subject_matter = str(payload.get("subject_matter") or dna.subject_matter)
    dna.mood = str(payload.get("mood") or "")
    dna.layout_archetype = str(payload.get("layout_archetype") or dna.layout_archetype)
    dna.logo_placement = str(payload.get("logo_placement") or dna.logo_placement)
    for key, current in (("copy_patterns", dna.copy_patterns),
                         ("cta_patterns", dna.cta_patterns),
                         ("do_not", dna.do_not)):
        vals = [str(v).strip() for v in (payload.get(key) or []) if str(v).strip()]
        if vals:
            setattr(dna, key, list(dict.fromkeys(vals))[:12])
    seed = str(payload.get("prompt_seed") or "").strip()
    if seed:
        dna.prompt_seed = seed
    return dna
