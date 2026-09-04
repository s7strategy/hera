"""Entrada/saída de imagem e utilidades de pixel do S7 Editor.

Todo o resto do projeto passa por aqui para abrir e salvar arquivos, por dois
motivos que valem a pena serem explícitos:

* **Orientação**: uma foto de celular vem com EXIF de rotação. Se cada módulo
  abrisse com ``Image.open`` direto, a mesma imagem teria dimensões diferentes
  em pontos diferentes do pipeline e a garantia de "zero drift" (que compara
  arrays pixel a pixel) quebraria com um erro incompreensível.
* **Formato de saída**: a garantia de integridade só é verificável em formato
  sem perdas. ``save_image`` deixa o PNG realmente sem perdas, força JPEG em
  4:4:4 (subsampling=0) quando não há escolha, e preserva o perfil ICC — sem o
  ICC os pixels batem mas a imagem "parece diferente" no navegador.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
from PIL import Image, ImageOps

from .models import Box

__all__ = [
    "SUPPORTED_EXT",
    "load_image",
    "save_image",
    "list_images",
    "image_sha",
    "to_png_bytes",
    "from_png_bytes",
    "resize_contain",
    "resize_cover",
    "dominant_colors",
    "average_color",
    "is_mostly_uniform",
    "to_array",
    "from_array",
    "crop_box",
]

# Extensões que aceitamos na inbox. Ordem = preferência ao desempatar.
SUPPORTED_EXT: tuple[str, ...] = (
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
)

# Arquivos/pastas que nunca são criativo do usuário.
_IGNORED_NAMES = {".gitkeep", ".ds_store", "thumbs.db", "desktop.ini"}
_IGNORED_DIRS = {"outbox", ".cache", "__pycache__", ".git", ".ipynb_checkpoints"}

# Onde guardamos o formato de origem depois do convert() (que zera img.format).
_FMT_KEY = "s7_source_format"
_PATH_KEY = "s7_source_path"

LANCZOS = Image.Resampling.LANCZOS


# --------------------------------------------------------------------------- #
# Abrir / salvar
# --------------------------------------------------------------------------- #
def load_image(path: str | Path) -> Image.Image:
    """Abre um arquivo em RGB (ou RGBA, se houver transparência de verdade).

    O EXIF de orientação já vem aplicado. Perfil ICC, EXIF e o formato de
    origem ficam guardados em ``img.info`` para que ``save_image`` consiga
    devolver o arquivo no mesmo formato, sem perder metadado pelo caminho.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"imagem não encontrada: {p}\n"
            "  Confira o caminho ou coloque os arquivos na pasta de entrada (inbox)."
        )
    try:
        with Image.open(p) as raw:
            raw.load()
            src_format = (raw.format or "").upper()
            info = dict(raw.info)
            img = ImageOps.exif_transpose(raw) or raw
            img = img.copy()
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise OSError(
            f"não consegui abrir a imagem {p.name}: {exc}\n"
            f"  Formatos aceitos: {', '.join(SUPPORTED_EXT)}."
        ) from exc

    has_alpha = img.mode in ("RGBA", "LA", "PA") or "transparency" in info
    target = "RGBA" if has_alpha else "RGB"
    if img.mode != target:
        img = img.convert(target)

    # convert()/copy() descartam parte do info; recolocamos o que interessa.
    for key in ("icc_profile", "exif", "dpi"):
        if not img.info.get(key) and info.get(key):
            img.info[key] = info[key]
    img.info[_FMT_KEY] = src_format or _format_from_suffix(p) or "PNG"
    img.info[_PATH_KEY] = str(p)
    return img


def _format_from_suffix(path: Path) -> str | None:
    ext = path.suffix.lower()
    return {
        ".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP",
        ".bmp": "BMP", ".tif": "TIFF", ".tiff": "TIFF",
    }.get(ext)


def _flatten(img: Image.Image, background: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """RGBA -> RGB sobre fundo sólido (JPEG não tem canal alfa)."""
    if img.mode != "RGBA":
        return img.convert("RGB")
    flat = Image.new("RGB", img.size, background)
    flat.paste(img, mask=img.split()[3])
    return flat


def save_image(img: Image.Image, path: str | Path, *, fmt: str | None = None,
               quality: int = 95) -> Path:
    """Salva preservando o formato de origem por padrão.

    Regras que existem por causa da garantia de zero drift:

    * **PNG/WEBP/TIFF**: sem perdas. É o formato do *master* — só nele o
      ``drift_pixels == 0`` é verificável byte a byte.
    * **JPEG**: ``subsampling=0`` (4:4:4) e ``optimize=True``. Ainda assim é
      derivado com perdas; quem exige JPEG tem que reportar drift com
      tolerância (ver ``protect.drift_report``).

    A extensão explícita do caminho manda sobre o formato de origem — se o
    usuário pediu ``.png``, ele recebe PNG.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    out_fmt = (fmt or _format_from_suffix(p) or img.info.get(_FMT_KEY) or "PNG").upper()
    if out_fmt in ("JPG", "MPO"):
        out_fmt = "JPEG"

    params: dict[str, Any] = {}
    icc = img.info.get("icc_profile")
    if icc:
        params["icc_profile"] = icc

    if out_fmt == "PNG":
        data = img if img.mode in ("RGB", "RGBA", "L", "P") else img.convert("RGB")
        params.update(optimize=True, compress_level=6)
    elif out_fmt == "JPEG":
        data = _flatten(img)
        params.update(quality=int(quality), subsampling=0, optimize=True, progressive=True)
        if img.info.get("exif"):
            params["exif"] = img.info["exif"]
    elif out_fmt == "WEBP":
        data = img
        # quality>=95 => tratamos como pedido de master: WEBP lossless mantém a
        # garantia e costuma ficar menor que PNG.
        if int(quality) >= 95:
            params.update(lossless=True, quality=100, method=4)
        else:
            params.update(lossless=False, quality=int(quality), method=4)
    elif out_fmt == "TIFF":
        data = img
        params.update(compression="tiff_lzw")
    else:
        data = _flatten(img) if img.mode == "RGBA" and out_fmt in ("BMP",) else img

    try:
        data.save(p, out_fmt, **params)
    except OSError as exc:
        raise OSError(f"não consegui salvar {p}: {exc}") from exc
    return p


def list_images(folder: str | Path, *, recursive: bool = False) -> list[Path]:
    """Lista os criativos de uma pasta, em ordem alfabética estável.

    Ignora arquivos ocultos, ``.gitkeep``, lixo de sistema operacional e
    qualquer coisa dentro de ``outbox``/``.cache`` — senão o segundo lote
    reprocessaria a saída do primeiro.
    """
    d = Path(folder)
    if not d.exists():
        raise FileNotFoundError(
            f"pasta de entrada não existe: {d}\n"
            "  Crie a pasta e coloque as imagens dentro (ex.: s7editor/inbox)."
        )
    if not d.is_dir():
        raise NotADirectoryError(f"esperava uma pasta, veio um arquivo: {d}")

    it: Iterable[Path] = d.rglob("*") if recursive else d.glob("*")
    out: list[Path] = []
    for p in it:
        if not p.is_file():
            continue
        if p.name.startswith(".") or p.name.lower() in _IGNORED_NAMES:
            continue
        if p.suffix.lower() not in SUPPORTED_EXT:
            continue
        rel_parts = p.relative_to(d).parts[:-1]
        if any(part.lower() in _IGNORED_DIRS or part.startswith(".") for part in rel_parts):
            continue
        out.append(p)
    return sorted(out, key=lambda q: (str(q.parent).lower(), q.name.lower()))


# --------------------------------------------------------------------------- #
# Bytes / hash
# --------------------------------------------------------------------------- #
def image_sha(img: Image.Image) -> str:
    """SHA-256 do CONTEÚDO em pixels (modo + tamanho + bytes crus).

    Independe de compressão: duas codificações do mesmo pixel dão o mesmo
    hash. É por isso que serve de chave de cache da análise de visão.
    """
    h = hashlib.sha256()
    h.update(f"{img.mode}:{img.size[0]}x{img.size[1]}:".encode("ascii"))
    h.update(img.tobytes())
    return h.hexdigest()


def to_png_bytes(img: Image.Image) -> bytes:
    """PNG sem perdas em memória — formato que a API de imagem aceita."""
    buf = io.BytesIO()
    data = img if img.mode in ("RGB", "RGBA", "L") else img.convert("RGBA")
    data.save(buf, "PNG", optimize=False, compress_level=3)
    return buf.getvalue()


def from_png_bytes(b: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(b))
    img.load()
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    return img


def to_array(img: Image.Image) -> np.ndarray:
    """``np.uint8 (H, W, 3|4)`` — o formato que inpaint/protect esperam."""
    return np.asarray(img, dtype=np.uint8)


def from_array(arr: np.ndarray) -> Image.Image:
    a = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(a, "RGBA" if a.ndim == 3 and a.shape[2] == 4 else "RGB")


# --------------------------------------------------------------------------- #
# Redimensionamento — nunca distorce
# --------------------------------------------------------------------------- #
def _fit_scale(src_w: int, src_h: int, w: int, h: int, *, cover: bool) -> float:
    if src_w <= 0 or src_h <= 0:
        raise ValueError("imagem de origem com dimensão zero")
    fx, fy = w / src_w, h / src_h
    return max(fx, fy) if cover else min(fx, fy)


def resize_contain(img: Image.Image, w: int, h: int, *, pad: bool = True,
                   fill: tuple[int, ...] | None = None) -> Image.Image:
    """Encaixa a imagem inteira em ``w x h`` SEM distorcer (letterbox).

    ``pad=True`` (padrão) devolve exatamente ``w x h`` com a imagem centralizada
    e o resto preenchido por ``fill``. ``pad=False`` devolve só a imagem
    redimensionada (dimensões ≤ w, h), útil quando quem chama vai colar o
    resultado num canvas próprio — é o caso do reframe com fundo borrado.
    """
    w, h = int(w), int(h)
    if w <= 0 or h <= 0:
        raise ValueError(f"tamanho alvo inválido: {w}x{h}")
    s = _fit_scale(img.width, img.height, w, h, cover=False)
    nw = max(1, int(round(img.width * s)))
    nh = max(1, int(round(img.height * s)))
    scaled = img.resize((nw, nh), LANCZOS)
    if not pad:
        return scaled
    mode = img.mode if img.mode in ("RGB", "RGBA") else "RGB"
    if fill is None:
        fill = (0, 0, 0, 0) if mode == "RGBA" else (0, 0, 0)
    canvas = Image.new(mode, (w, h), tuple(fill))
    canvas.paste(scaled, ((w - nw) // 2, (h - nh) // 2))
    canvas.info.update({k: v for k, v in img.info.items() if k in ("icc_profile", _FMT_KEY)})
    return canvas


def resize_cover(img: Image.Image, w: int, h: int, *,
                 anchor: tuple[float, float] = (0.5, 0.5)) -> Image.Image:
    """Preenche ``w x h`` SEM distorcer, cortando o excedente.

    ``anchor`` é a fração (0–1) do ponto que fica centralizado no recorte;
    (0.5, 0.5) = centro. Quem sabe onde está o sujeito (análise de visão) pode
    passar outro ponto para não decapitar ninguém.
    """
    w, h = int(w), int(h)
    if w <= 0 or h <= 0:
        raise ValueError(f"tamanho alvo inválido: {w}x{h}")
    s = _fit_scale(img.width, img.height, w, h, cover=True)
    nw = max(w, int(round(img.width * s)))
    nh = max(h, int(round(img.height * s)))
    scaled = img.resize((nw, nh), LANCZOS)
    ax = min(max(float(anchor[0]), 0.0), 1.0)
    ay = min(max(float(anchor[1]), 0.0), 1.0)
    left = int(round((nw - w) * ax))
    top = int(round((nh - h) * ay))
    out = scaled.crop((left, top, left + w, top + h))
    out.info.update({k: v for k, v in img.info.items() if k in ("icc_profile", _FMT_KEY)})
    return out


# --------------------------------------------------------------------------- #
# Medidas de cor
# --------------------------------------------------------------------------- #
def _as_box(box: Any, img_w: int, img_h: int) -> Box:
    return box if isinstance(box, Box) else Box.from_any(box, img_w, img_h)


def crop_box(img: Image.Image, box: Any) -> Image.Image:
    """Recorta pela ``Box`` (ou dict/tupla equivalente), já com clamp."""
    b = _as_box(box, img.width, img.height).clamp(img.width, img.height)
    if b.area <= 0:
        raise ValueError(f"caixa vazia após clamp: {b.to_dict()}")
    return img.crop(b.xyxy)


def _rgb_region(img: Image.Image, box: Any | None, *, max_side: int | None = None) -> Image.Image:
    region = crop_box(img, box) if box is not None else img
    if region.mode != "RGB":
        region = _flatten(region) if region.mode == "RGBA" else region.convert("RGB")
    if max_side and max(region.size) > max_side:
        s = max_side / max(region.size)
        region = region.resize(
            (max(1, int(region.width * s)), max(1, int(region.height * s))),
            Image.Resampling.BILINEAR,   # só medimos cor: bilinear basta e é rápido
        )
    return region


def dominant_colors(img: Image.Image, k: int = 5, box: Any | None = None) -> list[tuple[int, int, int]]:
    """As ``k`` cores mais presentes, da mais frequente para a menos.

    Usa a quantização mediana da própria PIL (sem sklearn) sobre uma versão
    reduzida — em 1080x1920 isso é ~30x mais rápido e a paleta não muda de
    forma perceptível, porque estamos atrás de cor de marca, não de detalhe.
    """
    k = max(1, int(k))
    region = _rgb_region(img, box, max_side=256)
    if region.width * region.height == 0:
        return []
    try:
        q = region.quantize(colors=k, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    except ValueError:
        q = region.quantize(colors=k)
    palette = q.getpalette() or []
    counts = q.getcolors(region.width * region.height) or []
    counts.sort(key=lambda c: -c[0])
    out: list[tuple[int, int, int]] = []
    for _, idx in counts[:k]:
        base = idx * 3
        if base + 2 < len(palette):
            out.append((palette[base], palette[base + 1], palette[base + 2]))
    return out


def average_color(img: Image.Image, box: Any | None = None) -> tuple[int, int, int]:
    """Média aritmética por canal, arredondada. Cuidado: média é sensível a
    outlier — para cor de fundo com texto por cima prefira mediana/moda."""
    region = _rgb_region(img, box, max_side=512)
    arr = np.asarray(region, dtype=np.float32).reshape(-1, 3)
    if arr.size == 0:
        return (0, 0, 0)
    m = arr.mean(axis=0)
    return (int(round(m[0])), int(round(m[1])), int(round(m[2])))


def is_mostly_uniform(img: Image.Image, box: Any, tol: float = 8) -> bool:
    """True se a região é praticamente chapada (desvio padrão ≤ ``tol`` em
    TODOS os canais).

    Sem redução de escala: reamostrar suavizaria justamente a variação que
    estamos tentando medir. ``tol=8`` tolera ruído de JPEG q≈80 mas rejeita
    degradê visível.
    """
    region = _rgb_region(img, box)
    arr = np.asarray(region, dtype=np.float32).reshape(-1, 3)
    if arr.shape[0] < 2:
        return True
    return bool((arr.std(axis=0) <= float(tol)).all())
