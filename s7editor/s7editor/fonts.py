"""Tipografia do S7 Editor: achar a fonte certa, medir e redesenhar texto.

Este módulo é a metade "escrever" da substituição de texto pixel-safe. A metade
"apagar" mora em `inpaint.py`. Duas garantias que o resto do pipeline assume:

1. **Confinamento.** `draw_text_block` só escreve dentro da `Box` pedida. A camada
   de texto é montada com folga (para sombra/contorno terem borrão correto) e
   depois recortada na caixa. Quem chama pode alargar a caixa antes (`Box.pad`)
   se quiser a sombra inteira — mas quem decide é o chamador, nunca este módulo.
2. **Sem drift.** A composição é feita em numpy: onde a cobertura do texto é zero,
   o pixel de destino é copiado byte a byte, não recomposto. Rodar duas vezes dá
   o mesmo arquivo.

Nunca falhamos por falta de fonte. Se a família da marca não existe na máquina,
caímos numa equivalente e **registramos um aviso** (`font_warnings()`), que o
pipeline joga em `ImageResult.warnings`.
"""
from __future__ import annotations

import logging
import math
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .models import Box, FontSpec

__all__ = [
    "resolve_font", "measure_line", "wrap_text", "fit_font_size",
    "draw_text_block", "text_mask",
    # extras úteis para textedit.py / pipeline.py
    "TextLayout", "plan_text_layout", "font_warnings", "clear_font_warnings",
    "clear_font_cache", "list_available_families", "fonts_dir",
    "CAP_EM", "XH_EM", "SUPERSAMPLE",
]

log = logging.getLogger("s7editor.fonts")

# --------------------------------------------------------------------------- #
# Constantes (espelham o projeto técnico)
# --------------------------------------------------------------------------- #
CAP_EM = 0.715          # cap-height / em, grotescas típicas
XH_EM = 0.52            # x-height / em
SUPERSAMPLE = 4         # E.6: renderiza em 4x e reduz com LANCZOS
MAX_SUPERSAMPLED_PX = 48_000_000   # teto de memória: reduz o fator se estourar
SHADOW_ALPHA = 0.75     # FontSpec não tem opacidade de sombra; este é o default
FONT_EXTS = (".ttf", ".otf", ".ttc", ".otc", ".woff")  # woff só se o freetype aceitar

# Pesos em escala CSS — a distância numérica é o critério de fallback.
WEIGHT_SCALE: dict[str, int] = {
    "thin": 100, "extralight": 200, "light": 300, "regular": 400,
    "medium": 500, "semibold": 600, "bold": 700, "extrabold": 800, "black": 900,
}
# Sinônimos aceitos na entrada (receita, FontSpec, análise de visão).
WEIGHT_ALIASES: dict[str, str] = {
    "hairline": "thin", "ultralight": "extralight", "ultra light": "extralight",
    "book": "regular", "normal": "regular", "roman": "regular", "text": "regular",
    "demi": "semibold", "demibold": "semibold", "semi bold": "semibold",
    "ultrabold": "extrabold", "heavy": "black", "ultra": "black", "extra black": "black",
    "ultrablack": "black", "fat": "black", "poster": "black",
}

_STYLE_TOKENS: dict[str, str] = {
    "thin": "thin", "hairline": "thin",
    "extralight": "extralight", "ultralight": "extralight",
    "light": "light",
    "regular": "regular", "normal": "regular", "book": "regular", "roman": "regular",
    "medium": "medium",
    "semibold": "semibold", "demibold": "semibold", "demi": "semibold",
    "bold": "bold",
    "extrabold": "extrabold", "ultrabold": "extrabold",
    "black": "black", "heavy": "black", "ultra": "black",
}
_MODIFIER_TOKENS = {"semi", "demi", "extra", "ultra", "super"}
_ITALIC_TOKENS = {"italic", "italics", "oblique", "slanted"}
# Ruído de nome de arquivo do Google Fonts / exportadores.
_NOISE_TOKENS = {
    "variablefont", "variable", "font", "vf", "wght", "slnt", "opsz", "wdth",
    "ital", "static", "webfont", "web", "desktop", "hinted", "unhinted", "ttf", "otf",
}

# Nomes legados do Windows/macOS que não seguem <Família>-<Peso>.
_LEGACY_NAMES: dict[str, tuple[str, str, bool]] = {
    "arial": ("arial", "regular", False), "arialbd": ("arial", "bold", False),
    "ariali": ("arial", "regular", True), "arialbi": ("arial", "bold", True),
    "ariblk": ("arial", "black", False), "arialn": ("arialnarrow", "regular", False),
    "tahoma": ("tahoma", "regular", False), "tahomabd": ("tahoma", "bold", False),
    "verdana": ("verdana", "regular", False), "verdanab": ("verdana", "bold", False),
    "verdanai": ("verdana", "regular", True), "verdanaz": ("verdana", "bold", True),
    "times": ("timesnewroman", "regular", False), "timesbd": ("timesnewroman", "bold", False),
    "timesi": ("timesnewroman", "regular", True), "timesbi": ("timesnewroman", "bold", True),
    "cour": ("couriernew", "regular", False), "courbd": ("couriernew", "bold", False),
    "calibri": ("calibri", "regular", False), "calibrib": ("calibri", "bold", False),
    "calibrii": ("calibri", "regular", True), "calibriz": ("calibri", "bold", True),
    "georgia": ("georgia", "regular", False), "georgiab": ("georgia", "bold", False),
    "impact": ("impact", "regular", False),
    "segoeui": ("segoeui", "regular", False), "segoeuib": ("segoeui", "bold", False),
    "segoeuii": ("segoeui", "regular", True), "segoeuiz": ("segoeui", "bold", True),
    "segoeuil": ("segoeui", "light", False), "seguisb": ("segoeui", "semibold", False),
    "helvetica": ("helvetica", "regular", False),
    "helveticaneue": ("helveticaneue", "regular", False),
}

# Cadeias de substituição. A primeira entrada é a própria família; o resto é a
# ordem de preferência quando ela não existe na máquina.
_SANS = ("inter", "helveticaneue", "helvetica", "arial", "roboto", "notosans",
         "opensans", "lato", "sourcesans3", "sourcesanspro", "arimo", "nimbussans",
         "segoeui", "liberationsans", "dejavusans", "freesans")
_SERIF = ("playfairdisplay", "georgia", "timesnewroman", "notoserif", "merriweather",
          "tinos", "liberationserif", "dejavuserif", "freeserif")
_MONO = ("jetbrainsmono", "firacode", "sourcecodepro", "consolas", "menlo",
         "liberationmono", "dejavusansmono", "freemono")
_CONDENSED = ("bebasneue", "oswald", "anton", "archivonarrow", "robotocondensed",
              "fjallaone", "teko", "arialnarrow", "liberationsansnarrow",
              "dejavusanscondensed") + _SANS

FAMILY_ALIASES: dict[str, tuple[str, ...]] = {
    "inter": ("intertight", "interdisplay") + _SANS,
    "intertight": ("inter",) + _SANS,
    "montserrat": ("montserratalternates", "poppins", "raleway", "gothica1") + _SANS,
    "poppins": ("montserrat", "nunitosans", "nunito", "urbanist", "futura", "centurygothic") + _SANS,
    "roboto": ("robotoflex", "notosans", "arimo") + _SANS,
    "helvetica": ("helveticaneue", "arial", "nimbussans", "inter") + _SANS,
    "helveticaneue": ("helvetica", "arial", "inter") + _SANS,
    "arial": ("liberationsans", "arimo", "helvetica") + _SANS,
    "bebasneue": _CONDENSED,
    "bebas": _CONDENSED,
    "oswald": ("bebasneue", "anton") + _CONDENSED,
    "anton": ("archivoblack", "bebasneue", "oswald") + _CONDENSED,
    "opensans": ("notosans", "roboto", "lato") + _SANS,
    "lato": ("opensans", "roboto") + _SANS,
    "nunito": ("nunitosans", "poppins", "quicksand") + _SANS,
    "raleway": ("montserrat", "poppins") + _SANS,
    "worksans": ("inter", "roboto") + _SANS,
    "playfairdisplay": _SERIF,
    "georgia": _SERIF,
    "timesnewroman": _SERIF,
    "times": _SERIF,
    "impact": ("anton", "archivoblack") + _CONDENSED,
}


# --------------------------------------------------------------------------- #
# Avisos (nunca falhar silenciosamente)
# --------------------------------------------------------------------------- #
_warn_lock = threading.Lock()
_warnings: list[str] = []
_warned_once: set[str] = set()


def _warn(msg: str, *, once_key: str | None = None) -> None:
    """Registra um aviso legível em português; deduplica pelo `once_key`."""
    key = once_key or msg
    with _warn_lock:
        if key in _warned_once:
            return
        _warned_once.add(key)
        _warnings.append(msg)
    log.warning(msg)


def font_warnings() -> list[str]:
    """Avisos acumulados (fonte não encontrada, peso aproximado, itálico sintético)."""
    with _warn_lock:
        return list(_warnings)


def clear_font_warnings() -> None:
    with _warn_lock:
        _warnings.clear()
        _warned_once.clear()


# --------------------------------------------------------------------------- #
# Descoberta de arquivos de fonte
# --------------------------------------------------------------------------- #
def fonts_dir() -> Path:
    """Diretório principal de fontes da marca — onde o usuário joga os .ttf.

    Import tardio de `config` de propósito: ele pode não existir ainda e não
    queremos ciclo de import nem chamada na hora do import deste módulo.
    """
    env = os.environ.get("S7EDITOR_FONTS_DIR") or os.environ.get("S7EDITOR_FONTS")
    if env:
        return Path(env).expanduser()
    try:  # pragma: no cover - depende de config.py estar pronto
        from .config import load_settings  # type: ignore

        d = getattr(load_settings(), "fonts_dir", None)
        if d:
            return Path(d)
    except Exception:
        pass
    return _package_root() / "fonts"


def _package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _user_font_dirs() -> list[Path]:
    """Diretórios do usuário, em ordem de prioridade, antes das fontes do sistema.

    Varremos tanto `<root>/fonts` (o que `config.Settings.fonts_dir` aponta) quanto
    `<root>/assets/fonts` — os dois nomes circulam na documentação e não custa nada
    aceitar os dois em vez de o usuário descobrir do jeito difícil que errou a pasta.
    """
    root = _package_root()
    out: list[Path] = []
    for d in (fonts_dir(), root / "fonts", root / "assets" / "fonts"):
        d = Path(d)
        if d not in out:
            out.append(d)
    return out


_README_ASSETS = """# Fontes da marca

Jogue aqui os .ttf / .otf / .ttc das fontes usadas pelos criativos. Esta pasta tem
prioridade sobre as fontes do sistema.

Nomeie como veio da fundição: `Inter-Bold.ttf`, `Montserrat-SemiBold.ttf`,
`BebasNeue-Regular.ttf`. Separador `-`, `_`, espaço ou CamelCase dá no mesmo.
Subpastas são varridas normalmente.

Se a fonte não estiver aqui o editor NÃO falha: usa uma equivalente do sistema e
registra um aviso no manifesto do lote.
"""


def _ensure_assets_dir(path: Path) -> None:
    """Cria `assets/fonts` com um README na primeira vez. Falha em silêncio se o FS for read-only."""
    try:
        if path.is_dir():
            readme = path / "README.md"
            if not readme.exists():
                readme.write_text(_README_ASSETS, encoding="utf-8")
            return
        path.mkdir(parents=True, exist_ok=True)
        (path / "README.md").write_text(_README_ASSETS, encoding="utf-8")
        log.info("criei %s — coloque os .ttf da marca aí", path)
    except OSError:
        pass


def _system_font_dirs() -> list[Path]:
    home = Path.home()
    return [
        Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
        home / ".fonts", home / ".local/share/fonts",
        home / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("C:/Windows/Fonts"), home / "AppData/Local/Microsoft/Windows/Fonts",
    ]


_TOKEN_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z]+|[0-9]+")


def _tokens(stem: str) -> list[str]:
    """Quebra 'LiberationSans-BoldItalic' em ['liberation','sans','bold','italic']."""
    out: list[str] = []
    for part in re.split(r"[\s_\-.,()\[\]]+", stem):
        out.extend(m.group(0).lower() for m in _TOKEN_RE.finditer(part))
    return [t for t in out if t]


def _parse_font_name(stem: str) -> tuple[str, str, bool]:
    """Nome de arquivo -> (family_key, weight, italic).

    Só descasca tokens de estilo do FIM do nome, respeitando fronteira de token —
    é o que impede 'Highlight' de virar família 'High' com peso 'light'.
    """
    low = re.sub(r"[^a-z0-9]+", "", stem.lower())
    if low in _LEGACY_NAMES:
        return _LEGACY_NAMES[low]

    toks = _tokens(stem)
    weight: str | None = None
    italic = False
    style_tail: list[str] = []
    while len(toks) > 1:
        t = toks[-1]
        if t in _NOISE_TOKENS or t in _ITALIC_TOKENS or t in _STYLE_TOKENS or t in _MODIFIER_TOKENS:
            style_tail.insert(0, toks.pop())
            continue
        break

    i = 0
    while i < len(style_tail):
        t = style_tail[i]
        if t in _MODIFIER_TOKENS and i + 1 < len(style_tail):
            joined = t + style_tail[i + 1]
            if joined in _STYLE_TOKENS:
                weight = weight or _STYLE_TOKENS[joined]
                i += 2
                continue
        if t in _ITALIC_TOKENS:
            italic = True
        elif t in _STYLE_TOKENS:
            weight = weight or _STYLE_TOKENS[t]
        elif t in _MODIFIER_TOKENS:
            weight = weight or ("semibold" if t in ("semi", "demi") else "extrabold")
        i += 1

    family = "".join(toks) or low
    return (family, weight or "regular", italic)


@dataclass
class _FontFile:
    path: Path
    family: str
    weight: str
    italic: bool
    priority: int          # menor = melhor (assets/fonts vem antes do sistema)
    variable: bool


_index_lock = threading.Lock()
_index: dict[str, list[_FontFile]] | None = None


def _is_variable(stem: str) -> bool:
    low = stem.lower()
    return "variablefont" in low.replace("_", "").replace("-", "") or "[" in stem or "vf" == low[-2:]


def _build_index(force: bool = False) -> dict[str, list[_FontFile]]:
    """Varre os diretórios uma vez e monta family_key -> arquivos."""
    global _index
    with _index_lock:
        if _index is not None and not force:
            return _index
        user_dirs = _user_font_dirs()
        _ensure_assets_dir(user_dirs[0])
        idx: dict[str, list[_FontFile]] = {}
        seen: set[Path] = set()
        roots: list[Path] = user_dirs + _system_font_dirs()
        for prio, root in enumerate(roots):
            try:
                if not root.is_dir():
                    continue
                entries = sorted(root.rglob("*"))
            except OSError:
                continue
            for p in entries:
                if p.suffix.lower() not in FONT_EXTS or not p.is_file():
                    continue
                rp = p.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                fam, weight, italic = _parse_font_name(p.stem)
                idx.setdefault(fam, []).append(
                    _FontFile(p, fam, weight, italic, prio, _is_variable(p.stem))
                )
        _index = idx
        if not idx:
            _warn(f"nenhuma fonte encontrada no sistema nem em {user_dirs[0]}; "
                  "vou usar a fonte embutida do Pillow (métrica ruim). "
                  "Instale fontes ou coloque .ttf em assets/fonts.")
        return idx


def list_available_families() -> list[str]:
    """Famílias detectadas, em ordem alfabética. Útil para `doctor` na CLI."""
    return sorted(_build_index().keys())


def clear_font_cache() -> None:
    """Esquece índice e objetos de fonte — chame depois de copiar .ttf novos."""
    global _index
    with _index_lock:
        _index = None
    _tls.__dict__.pop("fonts", None)


# --------------------------------------------------------------------------- #
# Resolução família/peso -> arquivo
# --------------------------------------------------------------------------- #
def _norm_family(family: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(family or "").lower())


def _norm_weight(weight: Any) -> str:
    if isinstance(weight, (int, float)) and not isinstance(weight, bool):
        num = int(weight)
        return min(WEIGHT_SCALE, key=lambda k: abs(WEIGHT_SCALE[k] - num))
    w = str(weight or "regular").strip().lower()
    w = WEIGHT_ALIASES.get(w, w)
    w = re.sub(r"[^a-z]+", "", w)
    w = WEIGHT_ALIASES.get(w, w)
    if w in WEIGHT_SCALE:
        return w
    if w.isdigit():  # "700"
        return _norm_weight(int(w))
    return "regular"


def _classify(family_key: str) -> tuple[str, ...]:
    """Cadeia genérica quando a família pedida é desconhecida."""
    if "mono" in family_key or "code" in family_key or "courier" in family_key:
        return _MONO
    if "serif" in family_key and "sans" not in family_key:
        return _SERIF
    if any(t in family_key for t in ("condensed", "narrow", "compressed", "display", "bebas")):
        return _CONDENSED
    return _SANS


def _pick_in_family(files: Sequence[_FontFile], weight: str, italic: bool) -> tuple[_FontFile, bool, bool]:
    """Melhor arquivo da família. Devolve (arquivo, peso_exato, italico_exato)."""
    target = WEIGHT_SCALE[weight]

    def cost(f: _FontFile) -> tuple[int, int, int, int]:
        # itálico errado dói mais que peso errado: a inclinação salta aos olhos.
        return (0 if f.italic == italic else 1,
                abs(WEIGHT_SCALE.get(f.weight, 400) - target),
                # empate de distância: prefere o mais pesado (texto de CTA some se afinar)
                -WEIGHT_SCALE.get(f.weight, 400) if WEIGHT_SCALE.get(f.weight, 400) > target else 0,
                f.priority)

    best = min(files, key=cost)
    return best, best.weight == weight, best.italic == italic


def _resolve_path(family: str, weight: str, italic: bool) -> tuple[_FontFile | None, str]:
    """Acha o arquivo e devolve também o motivo do fallback (string vazia = achou)."""
    idx = _build_index()
    want = _norm_family(family)
    chain: list[str] = [want] if want else []
    chain += [c for c in FAMILY_ALIASES.get(want, _classify(want)) if c != want]

    exact_family = None
    for key in chain:
        files = idx.get(key)
        if not files:
            continue
        picked, w_ok, i_ok = _pick_in_family(files, weight, italic)
        reason = ""
        if key != want:
            reason = (f"fonte '{family}' não encontrada; usando '{key}' no lugar. "
                      f"Coloque o .ttf em {fonts_dir()} para o texto sair fiel.")
        elif not w_ok:
            reason = (f"'{family}' não tem o peso '{weight}'; usando '{picked.weight}'.")
        if w_ok and not i_ok and italic:
            reason = f"'{family}' não tem itálico; vou inclinar sinteticamente."
        exact_family = picked
        return exact_family, reason
    return None, (f"nenhuma fonte compatível com '{family}' foi encontrada; "
                  f"usando a fonte embutida do Pillow. Coloque um .ttf em {fonts_dir()}.")


# --------------------------------------------------------------------------- #
# Cache de objetos de fonte (thread-local: FreeTypeFont não é thread-safe)
# --------------------------------------------------------------------------- #
_tls = threading.local()
_synthetic_italic: dict[int, bool] = {}   # id(font) -> precisa cisalhar


def _font_cache() -> dict[tuple, ImageFont.FreeTypeFont]:
    d = getattr(_tls, "fonts", None)
    if d is None:
        d = {}
        _tls.fonts = d
    return d


_VARIATION_NAMES: dict[str, tuple[str, ...]] = {
    "thin": ("Thin", "Hairline"),
    "extralight": ("ExtraLight", "Extra Light", "UltraLight", "Light"),
    "light": ("Light", "ExtraLight"),
    "regular": ("Regular", "Normal", "Book"),
    "medium": ("Medium", "Regular"),
    "semibold": ("SemiBold", "Semi Bold", "DemiBold", "Medium"),
    "bold": ("Bold",),
    "extrabold": ("ExtraBold", "Extra Bold", "UltraBold", "Bold"),
    "black": ("Black", "Heavy", "ExtraBold"),
}


def _apply_variation(font: ImageFont.FreeTypeFont, weight: str, italic: bool) -> str | None:
    """Fonte variável: tenta selecionar a instância nomeada do peso pedido."""
    try:
        names = [n.decode("utf-8", "ignore") if isinstance(n, bytes) else str(n)
                 for n in font.get_variation_names()]
    except Exception:
        return None
    if not names:
        return None
    wanted = _VARIATION_NAMES.get(weight, ("Regular",))
    for w in wanted:
        for suffix in ((" Italic", "") if italic else ("",)):
            target = (w + suffix).replace(" ", "").lower()
            for n in names:
                if n.replace(" ", "").lower() == target:
                    try:
                        font.set_variation_by_name(n)
                        return n
                    except Exception:
                        return None
    return None


def resolve_font(family: str, weight: str = "regular", italic: bool = False,
                 size_px: int = 48) -> ImageFont.FreeTypeFont:
    """Objeto de fonte para (família, peso, itálico, tamanho).

    Nunca levanta exceção por fonte ausente: degrada para a equivalente mais
    próxima e registra o motivo em `font_warnings()`. O objeto é cacheado por
    thread — resolver a cada linha custa caro num lote de 30 imagens.
    """
    size = max(1, int(round(size_px)))
    w = _norm_weight(weight)
    key = (_norm_family(family), w, bool(italic), size)
    cache = _font_cache()
    hit = cache.get(key)
    if hit is not None:
        return hit

    ff, reason = _resolve_path(family, w, bool(italic))
    font: ImageFont.FreeTypeFont
    synth_italic = False
    if ff is None:
        if reason:
            _warn(reason, once_key=f"missing:{_norm_family(family)}")
        try:
            font = ImageFont.load_default(size=size)  # type: ignore[arg-type]
        except TypeError:  # Pillow antigo
            font = ImageFont.load_default()  # type: ignore[assignment]
        synth_italic = bool(italic)
    else:
        try:
            font = ImageFont.truetype(str(ff.path), size)
        except OSError as exc:
            _warn(f"não consegui abrir a fonte {ff.path}: {exc}. Usando a embutida do Pillow.",
                  once_key=f"open:{ff.path}")
            try:
                font = ImageFont.load_default(size=size)  # type: ignore[arg-type]
            except TypeError:
                font = ImageFont.load_default()  # type: ignore[assignment]
        else:
            if ff.variable or ff.weight != w or ff.italic != bool(italic):
                applied = _apply_variation(font, w, bool(italic))
                if applied and reason and "não tem o peso" in reason:
                    reason = ""   # a fonte variável resolveu o peso; sem aviso
            synth_italic = bool(italic) and not ff.italic
        if reason:
            _warn(reason, once_key=f"{_norm_family(family)}:{w}:{int(bool(italic))}")

    _synthetic_italic[id(font)] = synth_italic
    cache[key] = font
    return font


# --------------------------------------------------------------------------- #
# Medição
# --------------------------------------------------------------------------- #
def _safe_bbox(font: ImageFont.FreeTypeFont, s: str) -> tuple[float, float, float, float]:
    """bbox da tinta relativo à origem left-baseline. Fallback para fontes bitmap."""
    try:
        return tuple(float(v) for v in font.getbbox(s, anchor="ls"))  # type: ignore[return-value]
    except Exception:
        try:
            x0, y0, x1, y1 = font.getbbox(s)
            asc = _metrics(font)[0]
            return (float(x0), float(y0) - asc, float(x1), float(y1) - asc)
        except Exception:
            return (0.0, 0.0, 0.0, 0.0)


def _metrics(font: ImageFont.FreeTypeFont) -> tuple[float, float]:
    try:
        asc, desc = font.getmetrics()
        return (float(asc), float(desc))
    except Exception:
        sz = float(getattr(font, "size", 16) or 16)
        return (sz * 0.8, sz * 0.2)


def _length(font: ImageFont.FreeTypeFont, s: str) -> float:
    if not s:
        return 0.0
    try:
        return float(font.getlength(s))
    except Exception:
        return float(_safe_bbox(font, s)[2])


@dataclass
class _LineGeom:
    """Geometria de uma linha, em coordenadas locais com origem na left-baseline."""
    text: str
    offsets: list[float]                        # x de cada caractere (só se ls != 0)
    advance: float                              # largura de avanço, com tracking
    ink: tuple[float, float, float, float]      # x0,y0,x1,y1 da tinta (y negativo = acima)

    @property
    def ink_w(self) -> float:
        return max(0.0, self.ink[2] - self.ink[0])


def _line_geom(font: ImageFont.FreeTypeFont, s: str, ls: float) -> _LineGeom:
    """Mede uma linha. Com tracking, o avanço é por prefixo (mantém o kerning exato)."""
    if not s:
        return _LineGeom(s, [], 0.0, (0.0, 0.0, 0.0, 0.0))
    if abs(ls) < 1e-6:
        bb = _safe_bbox(font, s)
        return _LineGeom(s, [], _length(font, s), bb)
    offs: list[float] = []
    x0 = y0 = math.inf
    x1 = y1 = -math.inf
    for i, ch in enumerate(s):
        # getlength(prefixo) telescopa: preserva kerning de pares sem O(n^2) de bbox
        x = _length(font, s[:i]) + i * ls
        offs.append(x)
        if ch.isspace():
            continue
        b = _safe_bbox(font, ch)
        x0, y0 = min(x0, x + b[0]), min(y0, b[1])
        x1, y1 = max(x1, x + b[2]), max(y1, b[3])
    if x0 is math.inf or x0 == math.inf:
        x0 = y0 = x1 = y1 = 0.0
    advance = _length(font, s) + ls * (len(s) - 1)
    return _LineGeom(s, offs, advance, (float(x0), float(y0), float(x1), float(y1)))


def measure_line(text: str, font: ImageFont.FreeTypeFont,
                 letter_spacing: float = 0.0) -> tuple[int, int]:
    """(largura, altura) da TINTA de uma linha, com tracking entre caracteres.

    O tracking entra `n-1` vezes (nunca depois do último caractere) — somar `n`
    vezes é o erro que faz o texto centralizado ficar deslocado meio espaço.
    Devolve extensão da tinta, não o avanço: é isso que precisa caber na caixa.
    """
    if not text:
        return (0, 0)
    g = _line_geom(font, text, float(letter_spacing))
    return (int(math.ceil(g.ink[2] - g.ink[0])), int(math.ceil(g.ink[3] - g.ink[1])))


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_w: float,
              letter_spacing: float = 0.0) -> list[str]:
    """Quebra gulosa por palavras respeitando `max_w` (largura de tinta).

    `\\n` explícito é respeitado. Palavra sozinha maior que a caixa é quebrada por
    caractere — melhor cortar a palavra do que estourar a caixa e violar a licença.
    """
    max_w = float(max_w)
    if not text:
        return []
    ls = float(letter_spacing)
    out: list[str] = []
    for para in str(text).split("\n"):
        words = para.split()
        if not words:
            out.append("")
            continue
        cur = ""
        for word in words:
            cand = f"{cur} {word}" if cur else word
            if not cur or measure_line(cand, font, ls)[0] <= max_w:
                cur = cand
                continue
            out.append(cur)
            cur = word
        # palavra isolada estourando a caixa: parte por caractere
        pending = [cur] if cur else []
        for piece in pending:
            if measure_line(piece, font, ls)[0] <= max_w or len(piece) <= 1:
                out.append(piece)
                continue
            chunk = ""
            for ch in piece:
                if chunk and measure_line(chunk + ch, font, ls)[0] > max_w:
                    out.append(chunk)
                    chunk = ch
                else:
                    chunk += ch
            if chunk:
                out.append(chunk)
    # a mesma quebra por caractere vale para linhas intermediárias já emitidas
    fixed: list[str] = []
    for line in out:
        if not line or measure_line(line, font, ls)[0] <= max_w or " " in line:
            fixed.append(line)
            continue
        chunk = ""
        for ch in line:
            if chunk and measure_line(chunk + ch, font, ls)[0] > max_w:
                fixed.append(chunk)
                chunk = ch
            else:
                chunk += ch
        if chunk:
            fixed.append(chunk)
    return fixed


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
@dataclass
class TextLayout:
    """Onde cada linha vai, em coordenadas locais da caixa (px, origem no topo-esq.)."""

    lines: list[str]
    font: ImageFont.FreeTypeFont
    size_px: int
    line_advance: int
    baselines: list[float]
    draw_x: list[float]                       # x de origem do desenho (bearing compensado)
    geoms: list[_LineGeom] = field(default_factory=list)
    ink: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    fits: bool = True
    letter_spacing: float = 0.0

    @property
    def ink_box(self) -> Box:
        x0, y0, x1, y1 = self.ink
        return Box(int(math.floor(x0)), int(math.floor(y0)),
                   int(math.ceil(x1 - x0)), int(math.ceil(y1 - y0)))


def _apply_case(text: str, spec: FontSpec) -> str:
    return str(text).upper() if getattr(spec, "uppercase", False) else str(text)


def _layout(text: str, font: ImageFont.FreeTypeFont, spec: FontSpec,
            box_w: float, box_h: float, *, size_px: int, letter_spacing: float,
            max_lines: int | None) -> TextLayout:
    """Calcula linhas, baselines e x de desenho. Tudo em pixels da escala do `font`."""
    ls = float(letter_spacing)
    lines = wrap_text(text, font, box_w, ls)
    line_adv = max(1, int(round(size_px * float(getattr(spec, "line_height", 1.2) or 1.2))))
    geoms = [_line_geom(font, s, ls) for s in lines]

    # Extensão vertical da tinta do bloco (baseline da 1ª linha em y=0).
    tops: list[float] = []
    bots: list[float] = []
    for i, g in enumerate(geoms):
        if not g.text.strip():
            continue
        tops.append(i * line_adv + g.ink[1])
        bots.append(i * line_adv + g.ink[3])
    if tops:
        t, b = min(tops), max(bots)
    else:
        asc, desc = _metrics(font)
        t, b = -asc, desc
    block_h = b - t
    block_w = max((g.ink_w for g in geoms), default=0.0)

    valign = str(getattr(spec, "valign", "middle") or "middle").lower()
    if valign == "top":
        y_ink = 0.0
    elif valign == "bottom":
        y_ink = box_h - block_h
    else:
        y_ink = (box_h - block_h) / 2.0
    b0 = y_ink - t          # baseline da primeira linha

    align = str(getattr(spec, "align", "center") or "center").lower()
    draw_x: list[float] = []
    baselines: list[float] = []
    x0_all, x1_all = math.inf, -math.inf
    for i, g in enumerate(geoms):
        if align == "left":
            tx = 0.0
        elif align == "right":
            tx = box_w - g.ink_w
        else:
            tx = (box_w - g.ink_w) / 2.0
        draw_x.append(tx - g.ink[0])       # compensa o bearing esquerdo
        baselines.append(b0 + i * line_adv)
        if g.text.strip():
            x0_all = min(x0_all, tx)
            x1_all = max(x1_all, tx + g.ink_w)
    if x0_all is math.inf or x0_all == math.inf:
        x0_all = x1_all = 0.0

    fits = (block_w <= box_w + 0.5 and block_h <= box_h + 0.5
            and (max_lines is None or len([l for l in lines if l.strip()]) <= max_lines))
    return TextLayout(lines=lines, font=font, size_px=size_px, line_advance=line_adv,
                      baselines=baselines, draw_x=draw_x, geoms=geoms,
                      ink=(x0_all, y_ink, x1_all, y_ink + block_h),
                      fits=fits, letter_spacing=ls)


def plan_text_layout(text: str, box: Box, spec: FontSpec, *,
                     size_px: int | None = None, max_lines: int | None = None) -> TextLayout:
    """Layout em escala 1x, sem desenhar. `textedit` usa para a escada de degradação."""
    txt = _apply_case(text, spec)
    size = int(size_px or getattr(spec, "size_px", 48) or 48)
    font = resolve_font(spec.family, spec.weight, bool(spec.italic), size)
    return _layout(txt, font, spec, float(box.w), float(box.h), size_px=size,
                   letter_spacing=float(getattr(spec, "letter_spacing", 0.0) or 0.0),
                   max_lines=max_lines)


def fit_font_size(text: str, box: Box, spec: FontSpec, *,
                  max_lines: int = 3, min_px: int = 8, max_px: int | None = None) -> int:
    """Maior corpo (px) em que `text` cabe em `box` com no máximo `max_lines` linhas.

    `fits(size)` é monotonicamente decrescente (mais corpo => mais largura e mais
    linhas, nunca volta a caber), então busca binária é válida. O teto é a altura
    da caixa: acima disso nem uma linha de caixa-alta caberia com folga.
    Devolve `min_px` se nem o mínimo couber — quem chama decide se rejeita.
    """
    txt = _apply_case(text, spec)
    if not txt.strip():
        return int(max(1, min_px))
    lo = max(1, int(min_px))
    hi = int(max_px) if max_px else max(lo, int(box.h))
    hi = max(lo, hi)
    ls_em = float(getattr(spec, "letter_spacing", 0.0) or 0.0) / max(1.0, float(getattr(spec, "size_px", 48) or 48))

    cache: dict[int, bool] = {}

    def ok(size: int) -> bool:
        if size in cache:
            return cache[size]
        font = resolve_font(spec.family, spec.weight, bool(spec.italic), size)
        lay = _layout(txt, font, spec, float(box.w), float(box.h), size_px=size,
                      letter_spacing=ls_em * size, max_lines=max_lines)
        cache[size] = lay.fits
        return lay.fits

    if not ok(lo):
        return lo
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if ok(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo


# --------------------------------------------------------------------------- #
# Renderização
# --------------------------------------------------------------------------- #
def _shear_layer(mask: Image.Image, degrees: float, baseline_y: float) -> Image.Image:
    """Itálico sintético: cisalha em torno da baseline (senão o texto 'anda' pra cima)."""
    s = math.tan(math.radians(degrees))
    # x' = x + s*(baseline - y)  =>  matriz inversa para Image.transform
    return mask.transform(mask.size, Image.AFFINE, (1, s, -s * baseline_y, 0, 1, 0),
                          resample=Image.BICUBIC)


def _draw_masks(layout: TextLayout, canvas: tuple[int, int], origin: tuple[int, int],
                *, stroke_width: int, synth_italic: float) -> tuple[Image.Image, Image.Image | None]:
    """Desenha os glifos em máscaras 'L' — sem cor, para não haver franja no downscale.

    Devolve (máscara do preenchimento, máscara com contorno) — a segunda é None se
    não há contorno.
    """
    fill = Image.new("L", canvas, 0)
    d_fill = ImageDraw.Draw(fill)
    stroked: Image.Image | None = None
    d_stroke: ImageDraw.ImageDraw | None = None
    if stroke_width > 0:
        stroked = Image.new("L", canvas, 0)
        d_stroke = ImageDraw.Draw(stroked)

    ox, oy = origin
    for g, bx, by in zip(layout.geoms, layout.draw_x, layout.baselines):
        if not g.text.strip():
            continue
        x = ox + bx
        y = oy + by
        if g.offsets:   # tracking != 0: caractere a caractere
            for ch, dx in zip(g.text, g.offsets):
                if ch.isspace():
                    continue
                d_fill.text((x + dx, y), ch, font=layout.font, fill=255, anchor="ls")
                if d_stroke is not None:
                    d_stroke.text((x + dx, y), ch, font=layout.font, fill=255, anchor="ls",
                                  stroke_width=stroke_width, stroke_fill=255)
        else:
            d_fill.text((x, y), g.text, font=layout.font, fill=255, anchor="ls")
            if d_stroke is not None:
                d_stroke.text((x, y), g.text, font=layout.font, fill=255, anchor="ls",
                              stroke_width=stroke_width, stroke_fill=255)

    if abs(synth_italic) >= 0.5 and layout.baselines:
        # uma linha só: cisalha em torno da própria baseline; várias: em torno da média
        base = oy + sum(layout.baselines) / len(layout.baselines)
        fill = _shear_layer(fill, synth_italic, base)
        if stroked is not None:
            stroked = _shear_layer(stroked, synth_italic, base)
    return fill, stroked


def _colorize(mask: Image.Image, rgb: tuple[int, int, int], alpha: float) -> Image.Image:
    layer = Image.new("RGBA", mask.size, (int(rgb[0]), int(rgb[1]), int(rgb[2]), 0))
    if alpha >= 0.999:
        layer.putalpha(mask)
    else:
        layer.putalpha(mask.point(lambda v: int(v * max(0.0, min(1.0, alpha)) + 0.5)))
    return layer


def _composite_over(dst: Image.Image, layer: Image.Image, at: tuple[int, int]) -> Image.Image:
    """'Source over' em numpy, escrevendo SÓ no retângulo de `layer`.

    Onde a cobertura é zero o pixel de destino é copiado byte a byte (não
    recomposto): é isso que garante drift zero dentro da própria caixa.
    """
    x, y = at
    w, h = layer.size
    out = dst.copy()
    if w <= 0 or h <= 0:
        return out
    region = out.crop((x, y, x + w, y + h))
    src = np.asarray(layer, dtype=np.float32)
    sa = src[..., 3:4] / 255.0
    has_alpha = region.mode in ("RGBA", "LA")
    base = np.asarray(region.convert("RGBA"), dtype=np.float32)
    da = base[..., 3:4] / 255.0

    oa = sa + da * (1.0 - sa)
    num = src[..., :3] * sa + base[..., :3] * da * (1.0 - sa)
    rgb = np.where(oa > 1e-6, num / np.maximum(oa, 1e-6), base[..., :3])
    rgb = np.rint(rgb)
    a8 = np.rint(oa * 255.0)

    opaque = sa[..., 0] <= 0.0
    rgb[opaque] = base[..., :3][opaque]          # cobertura zero => cópia exata
    a8[opaque, 0] = base[..., 3][opaque]

    merged = np.clip(np.concatenate([rgb, a8], axis=-1), 0, 255).astype(np.uint8)
    new_region = Image.fromarray(merged, "RGBA")
    if not has_alpha:
        new_region = new_region.convert(region.mode)
    out.paste(new_region, (x, y))
    return out


def _supersample_factor(box: Box, requested: int) -> int:
    s = max(1, int(requested))
    while s > 1 and box.w * box.h * s * s > MAX_SUPERSAMPLED_PX:
        s -= 1
    return s


def _build_text_layer(text: str, box: Box, spec: FontSpec, *, supersample: int,
                      with_stroke: bool, with_shadow: bool,
                      size_px: int | None = None,
                      max_lines: int | None = None) -> tuple[Image.Image | None, TextLayout | None]:
    """Monta a camada RGBA do tamanho exato da caixa (sombra + contorno + preenchimento)."""
    txt = _apply_case(text, spec)
    if not txt.strip() or box.w <= 0 or box.h <= 0:
        return None, None

    S = _supersample_factor(box, supersample)
    size = int(size_px or getattr(spec, "size_px", 48) or 48)
    size_s = max(1, int(round(size * S)))
    font = resolve_font(spec.family, spec.weight, bool(spec.italic), size_s)
    synth = 12.0 if _synthetic_italic.get(id(font)) else 0.0

    ls_px = float(getattr(spec, "letter_spacing", 0.0) or 0.0)
    layout = _layout(txt, font, spec, box.w * S, box.h * S, size_px=size_s,
                     letter_spacing=ls_px * S, max_lines=max_lines)

    stroke_w = int(round(max(0, int(getattr(spec, "stroke_width", 0) or 0)) * S)) if with_stroke else 0
    sh_on = bool(with_shadow and getattr(spec, "shadow", False))
    sh_dx, sh_dy = (int(v) for v in (getattr(spec, "shadow_offset", (0, 2)) or (0, 2)))
    sh_blur = float(getattr(spec, "shadow_blur", 4) or 0)
    # folga: o borrão precisa de canvas, senão a sombra bate na parede e vira barra
    pad = int(stroke_w + (abs(sh_dx) + abs(sh_dy) + 3 * sh_blur) * S * (1 if sh_on else 0)
              + 2 * S + 4)
    canvas = (box.w * S + 2 * pad, box.h * S + 2 * pad)

    fill_mask, stroke_mask = _draw_masks(layout, canvas, (pad, pad),
                                         stroke_width=stroke_w, synth_italic=synth)
    silhouette = stroke_mask if stroke_mask is not None else fill_mask

    layer_s = Image.new("RGBA", canvas, (0, 0, 0, 0))
    if sh_on:
        sh = silhouette
        if sh_dx or sh_dy:
            sh = Image.new("L", canvas, 0)
            sh.paste(silhouette, (int(sh_dx * S), int(sh_dy * S)))
        if sh_blur > 0:
            sh = sh.filter(ImageFilter.GaussianBlur(sh_blur * S))
        sh_alpha = float(getattr(spec, "shadow_opacity", SHADOW_ALPHA))
        layer_s = Image.alpha_composite(
            layer_s, _colorize(sh, tuple(getattr(spec, "shadow_color", (0, 0, 0))), sh_alpha))
    if stroke_mask is not None:
        sc = getattr(spec, "stroke_color", None) or (0, 0, 0)
        layer_s = Image.alpha_composite(layer_s, _colorize(stroke_mask, tuple(sc), 1.0))
    layer_s = Image.alpha_composite(layer_s, _colorize(fill_mask, tuple(spec.color), 1.0))

    # Recorta na caixa e só então reduz: o que sai da caixa é descartado de propósito.
    layer_s = layer_s.crop((pad, pad, pad + box.w * S, pad + box.h * S))
    layer = layer_s.resize((box.w, box.h), Image.LANCZOS) if S > 1 else layer_s

    op = float(getattr(spec, "opacity", 1.0) or 1.0)
    if op < 0.999:
        a = layer.getchannel("A").point(lambda v: int(v * max(0.0, min(1.0, op)) + 0.5))
        layer.putalpha(a)
    return layer, layout


def draw_text_block(img: Image.Image, text: str, box: Box, spec: FontSpec, *,
                    supersample: int = SUPERSAMPLE, size_px: int | None = None,
                    max_lines: int | None = None) -> Image.Image:
    """Desenha `text` dentro de `box` e devolve uma NOVA imagem (não muta a entrada).

    Multilinha com wrap, align left/center/right, valign top/middle/bottom,
    uppercase, contorno, sombra borrada, opacidade e tracking. O desenho é
    sempre numa camada RGBA (anti-aliasing correto) renderizada em `supersample`x
    e reduzida com LANCZOS.

    **Nenhum pixel fora de `box` é tocado.** Sombra e contorno que vazariam da
    caixa são recortados — se o efeito precisa transbordar, alargue a caixa antes
    (`Box.pad`) e registre a caixa maior em `ImageResult.changed_boxes`.
    """
    box = box.clamp(img.width, img.height)
    if box.w <= 0 or box.h <= 0:
        return img.copy()
    layer, _ = _build_text_layer(text, box, spec, supersample=supersample,
                                 with_stroke=True, with_shadow=True,
                                 size_px=size_px, max_lines=max_lines)
    if layer is None:
        return img.copy()
    return _composite_over(img, layer, (box.x, box.y))


def text_mask(text: str, box: Box, spec: FontSpec, size: tuple[int, int], *,
              include_stroke: bool = False, supersample: int = SUPERSAMPLE) -> Image.Image:
    """Máscara 'L' do tamanho `size` com 255 só onde há glifo.

    Sem contorno e sem sombra por padrão: serve para medir cobertura de tinta
    (comparar com a máscara medida na imagem original) e para montar máscaras de
    proteção. `size` é o tamanho da IMAGEM, não da caixa.
    """
    w, h = int(size[0]), int(size[1])
    mask = Image.new("L", (w, h), 0)
    box = box.clamp(w, h)
    if box.w <= 0 or box.h <= 0:
        return mask
    layer, _ = _build_text_layer(text, box, spec, supersample=supersample,
                                 with_stroke=include_stroke, with_shadow=False)
    if layer is None:
        return mask
    mask.paste(layer.getchannel("A"), (box.x, box.y))
    return mask
