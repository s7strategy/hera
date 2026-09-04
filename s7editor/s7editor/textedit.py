"""Substituição de texto pixel-safe: medir o estilo nos pixels e redesenhar.

Este módulo é o coração do produto — "trocar o CTA de 30 imagens sem mudar mais
nada". Ele implementa os itens **D** (inferir o estilo a partir dos pixels) e
**E** (redesenhar o texto novo na mesma caixa) do projeto técnico. O item C
(apagar reconstruindo o fundo) mora em :mod:`inpaint`; a renderização em
:mod:`fonts`.

Três garantias que o resto do pipeline pode assumir:

1. **Confinamento.** Nenhuma função daqui escreve um pixel fora da ``Box``
   pedida. O apagamento é feito por :func:`inpaint.erase_region` (que só
   escreve dentro da caixa) e o desenho por :func:`fonts.draw_text_block`
   (idem); por segurança, o resultado ainda é recortado na caixa declarada
   antes de sair — cinto e suspensório.
2. **Caixa honesta.** A ``Box`` devolvida não é a caixa pedida: é a *bounding
   box dos pixels que realmente mudaram*. Ela é sempre ⊆ caixa declarada, e é
   ela que vira a região permitida na verificação de drift
   (:func:`protect.drift_report`). Assim a garantia fica mais forte, não mais
   frouxa.
3. **Determinismo.** Rodar duas vezes na mesma imagem dá o mesmo arquivo: não
   há RNG sem semente aqui nem chamada de rede. Funciona 100% offline, sem
   ``OPENAI_API_KEY``.

Sobre a mistura com a análise de visão (``hint``): a visão acerta *família* e
*peso* (ela leu o briefing da marca, nós não); os *pixels* acertam cor e
tamanho (a visão chuta tamanho com frequência e a média de cor mente por causa
do anti-aliasing). :func:`infer_style_from_pixels` combina exatamente nessa
proporção.
"""
from __future__ import annotations

import contextlib
import logging
import math
import threading
from dataclasses import dataclass, field, replace
from typing import Any, Sequence

import numpy as np
from PIL import Image

from . import fonts as _fonts
from . import inpaint as _inpaint
from .models import BackgroundKind, Box, FontSpec, TextBlock, TextRole

try:  # opcional: acelera componentes conexas; há fallback numpy para tudo
    import cv2  # type: ignore
except Exception:  # pragma: no cover - ambiente sem opencv
    cv2 = None  # type: ignore

__all__ = [
    "infer_style_from_pixels", "replace_text", "remove_text", "add_text",
    # extras úteis para pipeline.py / cli.py
    "StyleMeasurement", "measure_style", "plan_fit",
    "edit_warnings", "clear_edit_warnings",
]

log = logging.getLogger("s7editor.textedit")

# --------------------------------------------------------------------------- #
# Constantes (espelham o projeto técnico; ver "Resumo das constantes")
# --------------------------------------------------------------------------- #
CAP_EM = _fonts.CAP_EM              # 0.715 — cap-height / em em grotescas
XH_EM = _fonts.XH_EM                # 0.52  — x-height / em
ITALIC_MIN_DEG = 4.0                # abaixo disso é ruído de segmentação
ITALIC_MIN_GAIN = 1.04              # medido: 1.000 em texto reto, 1.06-1.12 em itálico
SIZE_TARGET_MIN = 0.85              # escada E.3: alvo confortável
SIZE_WARN_MIN = 0.75
SIZE_HARD_MIN = 0.55                # abaixo disso a peça descaracteriza
LS_FLOOR_EM = -0.05                 # piso absoluto de tracking negativo
LS_MIN_SIZE_PX = 14                 # não aperta tracking em texto miúdo
LINE_HEIGHT_FLOOR = 1.02
MIN_CORE_PIXELS = 40                # menos que isso e a medida vira chute
SHADOW_PEAK_FRAC = 0.25             # medido: <=0.02 sem sombra, >=0.34 com sombra
SHADOW_AREA_FRAC = 0.20             # área da "tinta fraca" sobre a área do núcleo
STROKE_DELTA_E = 25.0
STROKE_OFF_LINE = 20.0              # ΔE fora do segmento fundo→texto (mata o falso positivo do AA)
MIN_DRAW_PX = 6

# Peso por largura de haste normalizada (ρ = sw / cap). Só é usada quando a
# auto-calibração por renderização falha — ver `_weight_from_render`.
_WEIGHT_TABLE: tuple[tuple[float, str], ...] = (
    (0.095, "light"),
    (0.135, "regular"),
    (0.155, "medium"),
    (0.180, "semibold"),
    (0.225, "bold"),
    (9.999, "black"),
)
_WEIGHT_CANDIDATES = ("light", "regular", "medium", "semibold", "bold", "black")
# Escala CSS dos pesos, só para desempatar a calibração (a de `fonts` é a fonte da verdade).
_WEIGHT_SCALE: dict[str, int] = getattr(_fonts, "WEIGHT_SCALE", {
    "thin": 100, "extralight": 200, "light": 300, "regular": 400, "medium": 500,
    "semibold": 600, "bold": 700, "extrabold": 800, "black": 900,
})

# Famílias que tentamos quando ninguém disse qual usar, em ordem de preferência.
_FAMILY_PREFERENCE = ("inter", "helveticaneue", "helvetica", "arial", "roboto",
                      "montserrat", "liberationsans", "dejavusans", "freesans")

# --------------------------------------------------------------------------- #
# Avisos (mesmo padrão de fonts.font_warnings: o pipeline drena para o manifesto)
# --------------------------------------------------------------------------- #
_warn_lock = threading.Lock()
_warnings: list[str] = []


def _warn(msg: str) -> str:
    with _warn_lock:
        if msg not in _warnings:
            _warnings.append(msg)
    log.warning(msg)
    return msg


def edit_warnings() -> list[str]:
    """Avisos acumulados desde o último :func:`clear_edit_warnings`."""
    with _warn_lock:
        return list(_warnings)


def clear_edit_warnings() -> None:
    with _warn_lock:
        _warnings.clear()


# --------------------------------------------------------------------------- #
# Helpers de numpy (locais de propósito: dependem só de numpy, nunca de cv2)
# --------------------------------------------------------------------------- #
def _dilate(mask: np.ndarray, iters: int = 1) -> np.ndarray:
    """Dilatação 3x3 (8-conexa) sem cv2."""
    m = mask
    for _ in range(max(0, int(iters))):
        h, w = m.shape
        p = np.pad(m, 1, mode="constant", constant_values=False)
        m = (p[0:h, 0:w] | p[0:h, 1:w + 1] | p[0:h, 2:w + 2] |
             p[1:h + 1, 0:w] | p[1:h + 1, 1:w + 1] | p[1:h + 1, 2:w + 2] |
             p[2:h + 2, 0:w] | p[2:h + 2, 1:w + 1] | p[2:h + 2, 2:w + 2])
    return m


def _erode(mask: np.ndarray, iters: int = 1) -> np.ndarray:
    return ~_dilate(~mask, iters)


def _stroke_width(core: np.ndarray) -> float:
    """Largura de traço pela identidade da fita: A ≈ w·L, P ≈ 2·L ⇒ w ≈ 2A/P.

    Precisa ser *o mesmo estimador* aplicado à tinta medida e ao texto
    renderizado na auto-calibração de peso — é isso que cancela o viés.
    """
    n = int(core.sum())
    if n == 0:
        return 0.0
    h, w = core.shape
    p = np.pad(core, 1, mode="constant", constant_values=False)
    inner = (p[0:h, 1:w + 1] & p[2:h + 2, 1:w + 1] &
             p[1:h + 1, 0:w] & p[1:h + 1, 2:w + 2])
    perim = float((core & ~inner).sum())
    if perim <= 0:
        return float(min(core.shape))
    return float(np.clip(2.0 * n / perim, 0.5, 64.0))


def _components(mask: np.ndarray) -> list[dict[str, int]]:
    """[{x,y,w,h,area}] das componentes conexas (8-conexas), fundo excluído."""
    if not mask.any():
        return []
    if cv2 is not None:
        n, _lbl, st, _cen = cv2.connectedComponentsWithStats(
            np.ascontiguousarray(mask.astype(np.uint8)), 8)
        return [{"x": int(st[i, 0]), "y": int(st[i, 1]), "w": int(st[i, 2]),
                 "h": int(st[i, 3]), "area": int(st[i, 4])} for i in range(1, n)]
    return _components_numpy(mask)


def _components_numpy(mask: np.ndarray) -> list[dict[str, int]]:
    """Rotulagem por propagação de máximo — vetorizada, sem loop por pixel."""
    hh, ww = mask.shape
    cur = np.zeros((hh, ww), dtype=np.float64)
    cur[mask] = np.arange(1, int(mask.sum()) + 1, dtype=np.float64)
    for _ in range(min(4 * (hh + ww), 2000)):
        p = np.pad(cur, 1, mode="constant", constant_values=0.0)
        nxt = np.max(np.stack([
            p[0:hh, 0:ww], p[0:hh, 1:ww + 1], p[0:hh, 2:ww + 2],
            p[1:hh + 1, 0:ww], p[1:hh + 1, 1:ww + 1], p[1:hh + 1, 2:ww + 2],
            p[2:hh + 2, 0:ww], p[2:hh + 2, 1:ww + 1], p[2:hh + 2, 2:ww + 2],
        ]), axis=0)
        nxt = np.where(mask, nxt, 0.0)
        if np.array_equal(nxt, cur):
            break
        cur = nxt
    out: list[dict[str, int]] = []
    ys, xs = np.nonzero(mask)
    ids = cur[ys, xs]
    for label in np.unique(ids):
        sel = ids == label
        yy, xx = ys[sel], xs[sel]
        out.append({"x": int(xx.min()), "y": int(yy.min()),
                    "w": int(xx.max() - xx.min() + 1),
                    "h": int(yy.max() - yy.min() + 1), "area": int(sel.sum())})
    return out


def _runs(flags: np.ndarray, min_len: int = 3, join_gap: int = 1) -> list[tuple[int, int]]:
    """Faixas contíguas de True em `flags` -> [(início, fim_exclusivo)]."""
    idx = np.flatnonzero(flags)
    if idx.size == 0:
        return []
    cuts = np.flatnonzero(np.diff(idx) > join_gap + 1)
    starts = np.concatenate(([idx[0]], idx[cuts + 1]))
    ends = np.concatenate((idx[cuts], [idx[-1]])) + 1
    return [(int(a), int(b)) for a, b in zip(starts, ends) if b - a >= min_len]


def _median_rgb(patch: np.ndarray, mask: np.ndarray) -> tuple[int, int, int] | None:
    if mask is None or not mask.any():
        return None
    med = np.median(patch[mask].reshape(-1, 3), axis=0)
    return (int(round(med[0])), int(round(med[1])), int(round(med[2])))


def _delta_e(a: Sequence[float] | None, b: Sequence[float] | None) -> float:
    """ΔE aproximado (norma L2 em Lab 0..255). Reusa o conversor do inpaint."""
    if a is None or b is None:
        return 0.0
    try:
        return float(_inpaint.delta_e(a, b))
    except Exception:  # pragma: no cover - conversor indisponível
        return float(np.linalg.norm(np.asarray(a, float) - np.asarray(b, float)))


def _norm_family(name: str) -> str:
    fn = getattr(_fonts, "_norm_family", None)
    return fn(name) if callable(fn) else "".join(
        c for c in str(name).lower() if c.isalnum())


def _norm_weight(name: str) -> str:
    fn = getattr(_fonts, "_norm_weight", None)
    return fn(name) if callable(fn) else str(name or "regular").lower()


@contextlib.contextmanager
def _quiet_font_warnings():
    """Silencia os avisos que a *sondagem* de pesos gera em :mod:`fonts`.

    Renderizar "HNIE" em seis pesos para calibrar ρ faz o resolvedor reclamar de
    pesos que a família não tem — ruído sobre fontes que nem vamos usar. O aviso
    que importa é o do desenho final, e esse continua saindo.
    """
    lock = getattr(_fonts, "_warn_lock", None)
    lst = getattr(_fonts, "_warnings", None)
    once = getattr(_fonts, "_warned_once", None)
    if lock is None or lst is None or once is None:  # pragma: no cover
        yield
        return
    with lock:
        snap_list, snap_once = list(lst), set(once)
    try:
        yield
    finally:
        with lock:
            lst[:] = snap_list
            once.clear()
            once.update(snap_once)


def _new_font_warnings(before: list[str]) -> list[str]:
    """Só os avisos de fonte surgidos nesta operação (o lote acumula os antigos)."""
    seen = set(before)
    return [w for w in _fonts.font_warnings() if w not in seen]


def _as_box(box: Any, img_w: int, img_h: int) -> Box:
    b = box if isinstance(box, Box) else Box.from_any(box, img_w, img_h)
    return b.clamp(img_w, img_h)


def _rgb_view(img: Image.Image) -> np.ndarray:
    """Array (h,w,3) uint8 só para comparação — nunca para escrever."""
    return np.asarray(img.convert("RGB"), dtype=np.uint8)


def _normalize_mode(img: Image.Image, warnings: list[str]) -> Image.Image:
    """Garante RGB/RGBA. Modo P/L viraria comparação de paleta, não de pixel."""
    if img.mode in ("RGB", "RGBA"):
        return img
    warnings.append(f"imagem em modo {img.mode} convertida para RGB antes de editar")
    return img.convert("RGBA" if "A" in img.getbands() else "RGB")


def _changed_box(before: np.ndarray, after: np.ndarray, box: Box) -> Box | None:
    """Bounding box dos pixels que de fato mudaram, restrita a `box`.

    Devolver isto em vez da caixa declarada deixa a garantia de zero drift mais
    apertada: a região "permitida" passa a ser só o que a operação encostou.
    """
    if box.area <= 0:
        return None
    a = before[box.y:box.y1, box.x:box.x1]
    b = after[box.y:box.y1, box.x:box.x1]
    if a.shape != b.shape:
        return box
    diff = np.any(a != b, axis=2)
    if not diff.any():
        return None
    ys = np.flatnonzero(diff.any(axis=1))
    xs = np.flatnonzero(diff.any(axis=0))
    return Box(box.x + int(xs[0]), box.y + int(ys[0]),
               int(xs[-1] - xs[0]) + 1, int(ys[-1] - ys[0]) + 1)


def _default_family() -> str:
    """Uma família de verdade instalada, para quando ninguém disse qual usar."""
    try:
        have = set(_fonts.list_available_families())
    except Exception:  # pragma: no cover
        return "Inter"
    for name in _FAMILY_PREFERENCE:
        if name in have:
            return name
    return "Inter"


# --------------------------------------------------------------------------- #
# D — medição do estilo a partir dos pixels
# --------------------------------------------------------------------------- #
@dataclass
class StyleMeasurement:
    """O que os pixels da caixa disseram sobre o texto que estava lá.

    ``spec`` já vem combinado com o ``hint`` (quando houve). Os campos de
    geometria (``baseline``, ``cap_px``, ``ink``) servem para ancorar o texto
    novo na mesma posição — é isso que preserva a sensação de layout.
    """

    spec: FontSpec
    box: Box
    kind: BackgroundKind = BackgroundKind.MIXED
    n_lines: int = 1
    baseline: float | None = None          # y da baseline da 1ª linha (local à caixa)
    cap_px: float = 0.0
    x_px: float | None = None
    stroke_px: float = 0.0                 # largura de haste medida
    ink: Box | None = None                 # bounding box da tinta original (local)
    ink_fraction: float = 0.0
    text_color: tuple[int, int, int] | None = None
    background_color: tuple[int, int, int] | None = None
    confidence: float = 0.0
    measured: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "box": self.box.to_dict(),
            "kind": self.kind.value,
            "n_lines": self.n_lines,
            "baseline": round(self.baseline, 2) if self.baseline is not None else None,
            "cap_px": round(self.cap_px, 2),
            "x_px": round(self.x_px, 2) if self.x_px else None,
            "stroke_px": round(self.stroke_px, 2),
            "ink": self.ink.to_dict() if self.ink else None,
            "ink_fraction": round(self.ink_fraction, 4),
            "text_color": list(self.text_color) if self.text_color else None,
            "background_color": list(self.background_color) if self.background_color else None,
            "confidence": round(self.confidence, 3),
            "style": self.spec.to_dict(),
            "measured": self.measured,
            "warnings": list(self.warnings),
        }


def _text_color(patch: np.ndarray, core: np.ndarray, halo: np.ndarray,
                alpha: np.ndarray, bg: Sequence[float] | None) -> tuple[int, int, int] | None:
    """D.1 — cor do texto sem a contaminação do anti-aliasing.

    Numa haste de largura ``sw`` a fração de pixels de borda é ≈ ``2/sw``: para
    ``sw=3`` **dois terços** da tinta é mistura com o fundo. Média sobre "tudo
    que é tinta" devolve branco puro como cinza 168. Por isso: mediana do
    núcleo erodido; e, quando nem núcleo existe, extrapolação na direção
    fundo→texto pelo percentil 95 da projeção.
    """
    core_e = _erode(core, 1)
    if int(core_e.sum()) >= MIN_CORE_PIXELS:
        return _median_rgb(patch, core_e)
    if int(core.sum()) >= 8 and bg is not None:
        bgv = np.asarray(bg, dtype=np.float32)
        dirv = np.median(patch[core].reshape(-1, 3), axis=0).astype(np.float32) - bgv
        norm = float(np.linalg.norm(dirv))
        if norm > 1e-6:
            dirv /= norm
            band = halo if halo.any() else core
            proj = (patch[band].reshape(-1, 3).astype(np.float32) - bgv) @ dirv
            if proj.size:
                tip = bgv + float(np.percentile(proj, 95)) * dirv
                return tuple(int(v) for v in np.clip(np.rint(tip), 0, 255))  # type: ignore[return-value]
    return _median_rgb(patch, core)


def _line_metrics(core: np.ndarray, comps: list[dict[str, int]]) -> dict[str, Any]:
    """D.2 — linhas, baseline, cap-height, x-height e detecção de caixa alta.

    O erro clássico aqui é classificar por **altura** de componente: em
    "Assine agora" o ``g`` (x-height + descendente) é *mais alto* que o ``A``,
    então ele entra no grupo dos "altos", puxa a mediana dos topos para baixo e
    a cap-height sai 20% menor — corpo errado, texto novo pequeno demais.
    Classificamos por **topo**: maiúsculas e ascendentes compartilham uma linha
    de topo, minúsculas (com ou sem descendente) compartilham outra. A baseline
    sai da mediana dos fundos, que descendentes em minoria não movem.
    """
    rows = core.sum(axis=1)
    if not rows.any():
        return {"lines": [], "baseline": None, "cap_px": 0.0, "x_px": None,
                "uppercase": None, "line_gap": None, "n_x": 0, "n_cap": 0}
    onl = rows > max(1.0, 0.02 * float(rows.max()))
    spans = _runs(onl, min_len=2, join_gap=1)
    if not spans:
        spans = [(int(np.flatnonzero(onl)[0]), int(np.flatnonzero(onl)[-1]) + 1)]

    baselines: list[float] = []
    caps: list[float] = []
    xhs: list[float] = []
    n_x = n_cap = glyph_total = 0
    cap_spread: list[float] = []
    line_info: list[dict[str, Any]] = []

    for (y0, y1) in spans:
        here = [c for c in comps if y0 <= (c["y"] + c["h"] / 2.0) < y1]
        if not here:
            continue
        hs = np.array([c["h"] for c in here], dtype=np.float32)
        tops = np.array([c["y"] for c in here], dtype=np.float32)
        bots = tops + hs
        h_max = float(np.percentile(hs, 90))
        if h_max <= 0:
            continue
        real = hs >= 0.35 * h_max          # ignora pingos, acentos e pontuação
        if not real.any():
            real = np.ones_like(hs, dtype=bool)
        base = float(np.median(bots[real]))

        t_min = float(tops[real].min())
        upper = real & (tops <= t_min + 0.15 * h_max)          # caixa alta/ascendentes
        cap = base - float(np.median(tops[upper])) if upper.any() else float(h_max)
        # x-height: topo claramente abaixo da linha alta E fundo na baseline
        lower = real & (tops > t_min + 0.20 * h_max) & (np.abs(bots - base) <= 0.12 * h_max)
        xh = base - float(np.median(tops[lower])) if int(lower.sum()) >= 2 else None

        baselines.append(base)
        caps.append(max(1.0, cap))
        if xh and xh > 1:
            xhs.append(xh)
        n_x += int(lower.sum())
        n_cap += int(upper.sum())
        glyph_total += int(real.sum())
        if int(upper.sum()) >= 2:
            cap_spread.append(float(np.ptp(hs[upper])) / h_max)
        line_info.append({"y0": y0, "y1": y1, "baseline": base, "cap": cap})

    if not baselines:
        return {"lines": [], "baseline": None, "cap_px": 0.0, "x_px": None,
                "uppercase": None, "line_gap": None, "n_x": 0, "n_cap": 0}

    gap = float(np.median(np.diff(np.array(baselines)))) if len(baselines) >= 2 else None
    uppercase: bool | None = None
    if glyph_total >= 3:
        # Caixa alta = ninguém na linha de x-height e alturas parelhas entre os altos.
        spread_ok = (not cap_spread) or (float(np.median(cap_spread)) <= 0.12)
        uppercase = bool(n_x < max(1, 0.12 * glyph_total) and spread_ok)
    return {
        "lines": line_info,
        "baseline": baselines[0],
        "cap_px": float(np.median(caps)),
        "x_px": float(np.median(xhs)) if xhs else None,
        "uppercase": uppercase,
        "line_gap": gap,
        "n_x": n_x,
        "n_cap": n_cap,
    }


def _italic_angle(core: np.ndarray, baseline: float) -> tuple[float, float]:
    """D.4 — cisalhamento que maximiza a energia da projeção vertical.

    Quando o ângulo está certo as hastes se empilham em poucas colunas, o que
    concentra a projeção. A pontuação é normalizada pela massa de tinta, senão
    ângulos que "encolhem" a silhueta ganhariam de graça.
    """
    hh, ww = core.shape
    if int(core.sum()) < 30 or hh < 6 or ww < 6:
        return 0.0, 1.0
    rows = np.arange(hh, dtype=np.float32) - float(baseline)
    cols = np.arange(ww)
    best_deg, best_score, zero_score = 0.0, -1.0, 1.0
    for deg in np.arange(-24.0, 24.001, 1.0):
        s = math.tan(math.radians(float(deg)))
        dx = np.rint(s * rows).astype(np.int64)
        idx = (cols[None, :] + dx[:, None]) % ww
        sh = np.take_along_axis(core, idx, axis=1)
        p = sh.sum(axis=0).astype(np.float64)
        total = p.sum()
        if total <= 0:
            continue
        score = float((p ** 2).sum() / (total ** 2))
        if abs(deg) < 1e-9:
            zero_score = score
        if score > best_score:
            best_deg, best_score = float(deg), score
    gain = best_score / zero_score if zero_score > 0 else 1.0
    return best_deg, gain


def _alignment(mid: np.ndarray, lines: list[dict[str, Any]], box_w: int,
               role: TextRole | None) -> tuple[str, Box | None, float]:
    """D.5 — alinhamento pelo desvio das bordas de tinta, com margem de decisão.

    Mede na máscara de **meia cobertura** (alpha ≥ 0,5), não no núcleo: a borda
    de uma letra redonda ("G", "O") só chega a alpha 0,9 uns 3 px adentro, e
    ancorar por ela empurraria o texto novo 3 px para a direita — o suficiente
    para o "trocar pelo mesmo texto" não voltar igual. Alpha 0,5 é justamente
    onde fica a borda geométrica que o PIL usa para posicionar.
    """
    edges: list[tuple[int, int]] = []
    for ln in lines:
        band = mid[int(ln["y0"]):int(ln["y1"])]
        cols = np.flatnonzero(band.any(axis=0))
        if cols.size:
            edges.append((int(cols[0]), int(cols[-1])))
    if not edges:
        return ("center", None, 0.0)
    left = np.array([a for a, _ in edges], dtype=np.float32)
    right = np.array([b for _, b in edges], dtype=np.float32)
    ys = [int(l["y0"]) for l in lines] or [0]
    ye = [int(l["y1"]) for l in lines] or [mid.shape[0]]
    ink = Box(int(left.min()), min(ys), int(right.max() - left.min()) + 1,
              max(ye) - min(ys))

    default = "left" if role in (TextRole.LEGAL, TextRole.SUBHEAD) else "center"
    if float(right.max() - left.min()) >= 0.92 * box_w:
        return (default, ink, 0.2)   # ocupa tudo: alinhamento inobservável
    if len(edges) >= 2:
        devs = [float(left.std()), float(right.std()), float(((left + right) / 2).std())]
        order = int(np.argmin(devs))
        srt = sorted(devs)
        margin = 1.0 if srt[1] <= 1e-6 else 1.0 - srt[0] / srt[1]
        if margin < 0.15:
            return (default, ink, 0.3)
        return (["left", "right", "center"][order], ink, min(1.0, 0.4 + margin))
    gl = float(left[0])
    gr = float(box_w - 1 - right[0])
    if abs(gl - gr) <= 0.04 * box_w:
        return ("center", ink, 0.7)
    return ("left" if gl < gr else "right", ink, 0.6)


def _valign(ink: Box | None, box_h: int) -> str:
    if ink is None or box_h <= 0:
        return "middle"
    top, bottom = ink.y, box_h - ink.y1
    if abs(top - bottom) <= max(2.0, 0.12 * box_h):
        return "middle"
    return "top" if top < bottom else "bottom"


def _mix_distance(c: Sequence[int] | None, a: Sequence[int] | None,
                  b: Sequence[int] | None) -> float:
    """Distância (em Lab) da cor `c` até o segmento que liga `a` e `b`.

    É o discriminador certo para contorno: todo pixel de anti-aliasing é uma
    mistura ``t·texto + (1−t)·fundo`` e portanto cai *em cima* do segmento
    (distância ~1–7). Um contorno de verdade é uma terceira cor e sai do
    segmento (medimos 76 num contorno azul). Comparar só ΔE com as pontas
    acusaria contorno em todo texto anti-aliased.
    """
    if c is None or a is None or b is None:
        return 0.0
    try:
        lab = _inpaint._rgb_to_lab
        pts = [lab(np.asarray(v, dtype=np.uint8).reshape(1, 1, 3))[0, 0].astype(np.float32)
               for v in (c, a, b)]
    except Exception:  # pragma: no cover
        pts = [np.asarray(v, dtype=np.float32) for v in (c, a, b)]
    cc, aa, bb = pts
    v = bb - aa
    den = float(np.dot(v, v))
    if den < 1e-6:
        return float(np.linalg.norm(cc - aa))
    t = float(np.clip(np.dot(cc - aa, v) / den, 0.0, 1.0))
    return float(np.linalg.norm(cc - (aa + t * v)))


def _stroke(patch: np.ndarray, core: np.ndarray, halo: np.ndarray, alpha: np.ndarray,
            sw: float, text_rgb: Sequence[int] | None,
            bg_rgb: Sequence[int] | None) -> tuple[int, tuple[int, int, int] | None]:
    """D.7 — contorno: um anel de cor que **não** é mistura de texto com fundo."""
    ring = _dilate(core, 2) & ~core & (alpha > 0.5)
    if int(ring.sum()) < 12 or text_rgb is None:
        return 0, None
    c_ring = _median_rgb(patch, ring)
    if c_ring is None:
        return 0, None
    if _delta_e(c_ring, text_rgb) <= STROKE_DELTA_E:
        return 0, None
    if bg_rgb is not None and _delta_e(c_ring, bg_rgb) <= STROKE_DELTA_E:
        return 0, None
    if _mix_distance(c_ring, bg_rgb, text_rgb) < STROKE_OFF_LINE:
        return 0, None      # é só o anti-aliasing
    band = (halo | ring) & ~core
    perim = float((core & ~_erode(core, 1)).sum())
    width = 1.0 if perim <= 0 else float(band.sum()) / perim
    hi = max(1, int(round(0.35 * max(sw, 1.0))))
    return int(np.clip(round(width), 1, hi)), c_ring


def _shift(mask: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Translada sem dar a volta (np.roll traria o outro lado da caixa)."""
    out = np.zeros_like(mask)
    h, w = mask.shape
    y0, y1 = max(0, dy), min(h, h + dy)
    x0, x1 = max(0, dx), min(w, w + dx)
    if y0 >= y1 or x0 >= x1:
        return out
    out[y0:y1, x0:x1] = mask[y0 - dy:y1 - dy, x0 - dx:x1 - dx]
    return out


def _shadow(patch: np.ndarray, background: np.ndarray, core: np.ndarray,
            erase: np.ndarray, sig_n: float, cap_px: float,
            bg_rgb: Sequence[int] | None, *, kind: BackgroundKind,
            residual: float) -> dict[str, Any] | None:
    """D.8 — sombra: correlação cruzada núcleo × "tinta fraca", depois refino.

    O mapa de alpha do :mod:`inpaint` satura em 0 abaixo do limiar de tinta, e a
    sombra vive justamente ali — então medimos a distância ao **fundo
    reconstruído**, que é analítico em fundo chapado/degradê.

    O pico da correlação dá a direção, mas vem enviesado para fora: a máscara
    exclui a vizinhança do glifo e sobra só o lado distante da sombra (medimos
    (8,8) para uma sombra real de (3,4)). O refino corrige isso aplicando **o
    mesmo mascaramento ao modelo** — aí o viés cancela e o erro cai para ±2 px.
    """
    # Só onde o fundo é *explicado* por um modelo analítico. Em foto/textura a
    # diferença para o fundo reconstruído é a própria textura, e o detector
    # acusaria sombra em toda imagem com grão — testado, acontecia.
    if kind not in (BackgroundKind.SOLID, BackgroundKind.GRADIENT):
        return None
    if residual > max(3.0, 3.0 * sig_n):
        return None
    hh, ww = core.shape
    n_core = int(core.sum())
    if n_core < 60 or hh < 8 or ww < 8:
        return None
    lab_p = _inpaint._rgb_to_lab(patch).astype(np.float32)
    lab_b = _inpaint._rgb_to_lab(background).astype(np.float32)
    d = np.linalg.norm(lab_p - lab_b, axis=2)
    d_core = float(np.median(d[core]))
    if d_core < 12:
        return None
    excl = _dilate(core, 2)
    weak = (d > max(3.0, 2.0 * sig_n)) & (d < 0.45 * d_core) & ~excl
    n_weak = int(weak.sum())
    if n_weak < max(30, SHADOW_AREA_FRAC * n_core):
        return None

    A = np.fft.rfft2(core.astype(np.float32))
    B = np.fft.rfft2(weak.astype(np.float32))
    cc = np.fft.irfft2(np.conj(A) * B, s=core.shape)
    cc[0, 0] = 0.0
    shifted = np.fft.fftshift(cc)
    R = int(np.clip(round(0.5 * max(cap_px, 8.0)), 3, min(hh, ww) // 2 - 1))
    if R < 3:
        return None
    win = shifted[hh // 2 - R:hh // 2 + R + 1, ww // 2 - R:ww // 2 + R + 1]
    if win.size == 0 or float(win.max()) < SHADOW_PEAK_FRAC * n_core:
        return None
    sy, sx = np.unravel_index(int(win.argmax()), win.shape)
    sy, sx = int(sy) - R, int(sx) - R

    # Refino por IoU em meia resolução (~20 ms): mesmo mascaramento nos dois lados.
    c2, w2, e2 = core[::2, ::2], weak[::2, ::2], excl[::2, ::2]
    best = (-1.0, 0, 0, 1)
    def _span(seed: int) -> range:
        half = int(round(seed / 2.0))
        return range(min(0, half) - 2, max(0, half) + 3)
    for r in (1, 2, 3, 4):
        dil = _dilate(c2, r)
        for dy in _span(sy):
            for dx in _span(sx):
                pred = _shift(dil, dx, dy) & ~e2
                inter = int(np.count_nonzero(pred & w2))
                if inter == 0:
                    continue
                iou = inter / max(int(np.count_nonzero(pred | w2)), 1)
                if iou > best[0]:
                    best = (iou, dx * 2, dy * 2, r)
    if best[0] < 0.35:
        return None
    _iou, dx, dy, r = best
    color = _shadow_color(patch, weak, bg_rgb) or (0, 0, 0)
    opacity = 1.0
    if bg_rgb is not None:
        m_bg = float(np.mean(np.asarray(bg_rgb, dtype=np.float32)))
        m_sh = float(np.mean(np.asarray(color, dtype=np.float32)))
        if m_bg > 1e-3:
            opacity = float(np.clip(1.0 - m_sh / m_bg, 0.15, 1.0))
    # Quanto da sombra o apagamento não alcançou: é o que pode sobrar na peça.
    residual = float(np.count_nonzero(weak & ~erase)) / max(n_weak, 1)
    return {
        "offset": (int(dx), int(dy)),
        "color": color,
        "blur": int(np.clip(round(1.8 * r), 2, 14)),
        "opacity": round(opacity, 3),
        "glow": abs(dx) <= 1 and abs(dy) <= 1,
        "iou": round(float(_iou), 3),
        "residual": round(residual, 3),
    }


def _rendered_ink_width(text: str, family: str, weight: str, italic: bool,
                        size_px: int) -> float | None:
    """Largura da **tinta** de `text` renderizado com tracking zero.

    Precisa ser um raster, não ``measure_line``: o bbox que o Pillow devolve
    para uma string é a caixa de avanço, uns 7 px mais larga que a tinta num
    corpo de 70px — erro que o estimador de tracking interpretaria como
    tracking negativo de 0,6 px por letra.
    """
    n = len(text)
    if n < 2 or size_px < 6:
        return None
    w = int(size_px * (n + 4))
    h = int(size_px * 3)
    if w * h > 40_000_000:
        return None
    spec = FontSpec(family=family, weight=weight, italic=italic, size_px=size_px,
                    color=(255, 255, 255), align="left", valign="middle",
                    letter_spacing=0.0, uppercase=False, stroke_width=0, shadow=False)
    try:
        with _quiet_font_warnings():
            mask = _fonts.text_mask(text, Box(0, 0, w, h), spec, (w, h), supersample=1)
    except Exception:  # pragma: no cover
        return None
    ink = np.asarray(mask, dtype=np.uint8) >= 128
    if not ink.any():
        return None
    cols = np.flatnonzero(ink.any(axis=0))
    return float(cols[-1] - cols[0] + 1)


def _shadow_color(patch: np.ndarray, weak: np.ndarray,
                  bg_rgb: Sequence[int] | None) -> tuple[int, int, int] | None:
    """Cor representativa da sombra: o miolo dela, não a franja que morre no fundo.

    A mediana sobre a banda inteira devolve algo quase igual ao fundo (a maior
    parte da área de uma sombra borrada é franja). Pegamos o terço mais afastado
    do fundo — é o que o olho lê como "a cor da sombra".
    """
    px = patch[weak].reshape(-1, 3).astype(np.float32)
    if px.shape[0] < 8:
        return None
    ref = np.asarray(bg_rgb if bg_rgb is not None else px.mean(axis=0), dtype=np.float32)
    dist = np.linalg.norm(px - ref, axis=1)
    keep = px[dist >= np.percentile(dist, 67)]
    if keep.shape[0] < 4:
        keep = px
    med = np.median(keep, axis=0)
    return tuple(int(v) for v in np.clip(np.rint(med), 0, 255))  # type: ignore[return-value]


def _letter_spacing(core: np.ndarray, lines: list[dict[str, Any]], known_text: str,
                    family: str, weight: str, italic: bool, size_px: int) -> float:
    """D.6 — tracking por comparação de avanço total, só quando dá para confiar.

    Sem OCR não sabemos o texto original; se a visão nos deu (``known_text``) e
    o bloco tem **uma linha**, a medida é direta: largura de tinta medida menos
    largura renderizada com ``ls=0``, dividida pelo nº de gaps. Fora disso o
    chute erra mais do que acerta, então devolvemos 0.
    """
    txt = (known_text or "").strip()
    if len(lines) != 1 or len(txt) < 2 or "\n" in txt or size_px < 6:
        return 0.0
    band = core[int(lines[0]["y0"]):int(lines[0]["y1"])]
    cols = np.flatnonzero(band.any(axis=0))
    if cols.size < 2:
        return 0.0
    measured_w = float(cols[-1] - cols[0] + 1)
    base_w = _rendered_ink_width(txt, family, weight, italic, size_px)
    if not base_w or base_w <= 0:
        return 0.0
    ls = (measured_w - base_w) / max(len(txt) - 1, 1)
    if abs(ls) < 0.015 * size_px:
        return 0.0
    return float(np.clip(ls, LS_FLOOR_EM * size_px, 0.5 * size_px))


# --- auto-calibração de peso (D.3) ----------------------------------------- #
_rho_cache: dict[tuple[str, bool, int, str], float] = {}
_CAP_TEXT = "HNIE"        # só caixa alta: a altura da tinta É a cap-height
_XH_TEXT = "xnosea"       # sem ascendente nem descendente: a altura é a x-height
_CALIB_TEXT = _CAP_TEXT


def _rho_of_render(family: str, weight: str, italic: bool, size_px: int) -> float | None:
    """ρ = sw/cap do texto renderizado — mesma medida feita nos pixels reais."""
    key = (_norm_family(family), bool(italic), int(size_px), weight)
    hit = _rho_cache.get(key)
    if hit is not None:
        return hit if hit > 0 else None
    size = int(np.clip(size_px, 24, 160))    # amostra grande: quantização atrapalha
    w = int(size * (len(_CALIB_TEXT) + 2))
    h = int(size * 3)
    spec = FontSpec(family=family, weight=weight, italic=italic, size_px=size,
                    color=(255, 255, 255), align="left", valign="middle",
                    letter_spacing=0.0, stroke_width=0, shadow=False)
    try:
        mask = _fonts.text_mask(_CALIB_TEXT, Box(0, 0, w, h), spec, (w, h))
    except Exception:  # pragma: no cover
        _rho_cache[key] = -1.0
        return None
    arr = np.asarray(mask, dtype=np.uint8)
    ink = arr >= 230
    if int(ink.sum()) < 50:
        _rho_cache[key] = -1.0
        return None
    ys = np.flatnonzero(ink.any(axis=1))
    cap = float(ys[-1] - ys[0] + 1)
    # Se a fonte real não abriu (bitmap embutido do Pillow), a cap não bate com
    # o corpo pedido e a calibração viraria ruído.
    if cap <= 0 or not (0.45 <= cap / size <= 0.95):
        _rho_cache[key] = -1.0
        return None
    rho = _stroke_width(ink) / cap
    _rho_cache[key] = rho
    return rho


_cap_cache: dict[tuple[str, str, bool, str], float] = {}


def _metric_ratio(family: str, weight: str, italic: bool, sample: str,
                  lo: float, hi: float) -> float | None:
    """Altura de tinta / corpo, **medida** renderizando `sample` na família.

    Substitui as constantes tabeladas (0,715 e 0,52): elas erram 4–6% entre
    grotescas (Liberation Sans tem cap 0,688), e 5% num CTA de 60px são 3px —
    o suficiente para o texto novo não bater com o que estava lá. Uma
    renderização por família/peso/amostra, cacheada, resolve de vez.
    """
    key = (_norm_family(family), _norm_weight(weight), bool(italic), sample)
    hit = _cap_cache.get(key)
    if hit is not None:
        return hit if hit > 0 else None
    size = 96
    w, h = size * (len(sample) + 2), size * 3
    spec = FontSpec(family=family, weight=weight, italic=italic, size_px=size,
                    color=(255, 255, 255), align="left", valign="middle",
                    letter_spacing=0.0, stroke_width=0, shadow=False)
    try:
        with _quiet_font_warnings():
            mask = _fonts.text_mask(sample, Box(0, 0, w, h), spec, (w, h))
    except Exception:  # pragma: no cover
        _cap_cache[key] = -1.0
        return None
    ink = np.asarray(mask, dtype=np.uint8) >= 230      # mesmo nível do `core` (alpha 0.9)
    if int(ink.sum()) < 50:
        _cap_cache[key] = -1.0
        return None
    ys = np.flatnonzero(ink.any(axis=1))
    ratio = float(ys[-1] - ys[0] + 1) / size
    if not (lo <= ratio <= hi):         # fonte bitmap embutida: medida inútil
        _cap_cache[key] = -1.0
        return None
    _cap_cache[key] = ratio
    return ratio


def _cap_ratio(family: str, weight: str, italic: bool) -> float | None:
    return _metric_ratio(family, weight, italic, _CAP_TEXT, 0.45, 0.95)


def _xh_ratio(family: str, weight: str, italic: bool) -> float | None:
    return _metric_ratio(family, weight, italic, _XH_TEXT, 0.30, 0.72)


def _weight_from_rho(rho: float, family: str, italic: bool, size_px: int, *,
                     calibrate: bool = True) -> tuple[str, bool]:
    """Peso mais próximo por auto-calibração; cai na tabela se não der.

    Devolve (peso, calibrado). Renderizar a mesma amostra em cada peso e medir ρ
    com **o mesmo estimador** cancela o viés e adapta a medida a qualquer
    família; a tabela de ρ só vale para grotescas. Com ``calibrate=False`` fica
    só a tabela — é o que usamos quando o peso já vem do hint e a sondagem seria
    trabalho jogado fora.
    """
    table = "black"
    for limit, name in _WEIGHT_TABLE:
        if rho <= limit:
            table = name
            break
    if calibrate:
        scores: list[tuple[float, int, str]] = []
        with _quiet_font_warnings():
            for w in _WEIGHT_CANDIDATES:
                r = _rho_of_render(family, w, italic, size_px)
                if r is None or r <= 0:
                    continue
                # Desempate: famílias com poucos arquivos mapeiam vários pesos no
                # mesmo desenho (semibold->bold). Empatado, vale o nome da tabela.
                tie = abs(_WEIGHT_SCALE.get(w, 400) - _WEIGHT_SCALE.get(table, 400))
                scores.append((round(abs(r - rho), 4), tie, w))
        if scores:
            scores.sort()
            return scores[0][2], True
    return table, False


# --- medição completa ------------------------------------------------------ #
def measure_style(img: Image.Image, box: Any, *, hint: FontSpec | None = None,
                  known_text: str = "", role: TextRole | None = None,
                  kind: BackgroundKind | str | None = None,
                  model: Any = None) -> StyleMeasurement:
    """Roda o item D inteiro numa caixa e devolve a medida + o estilo combinado.

    ``model`` aceita um :class:`inpaint.RegionModel` já calculado (evita
    reprocessar a caixa quando quem chama já rodou a análise).
    """
    w_img, h_img = img.size
    b = _as_box(box, w_img, h_img)
    warnings: list[str] = []
    if b.area <= 0:
        raise ValueError(
            "caixa vazia depois do clamp nos limites da imagem.\n"
            "  Confira as coordenadas do bloco de texto na receita."
        )
    if model is None:
        model = _inpaint.analyze_region(img, b, kind=kind)

    patch = model.patch
    core = model.core
    halo = model.halo
    alpha = model.alpha
    hh, ww = patch.shape[:2]
    bg_rgb = model.background_color
    if bg_rgb is None:
        far = ~_dilate(halo, 3)
        bg_rgb = _median_rgb(patch, far) if far.any() else _median_rgb(patch, np.ones_like(core))

    base = replace(hint) if isinstance(hint, FontSpec) else FontSpec()
    if not isinstance(hint, FontSpec) or not str(base.family or "").strip():
        base.family = _default_family()

    n_core = int(core.sum())
    if n_core < 12:
        warnings.append(
            "quase não há tinta detectável na caixa: o estilo veio do hint/padrão, "
            "não dos pixels (confira se a caixa está no lugar certo)"
        )
        spec = replace(base)
        if bg_rgb is not None:
            spec.color = _contrast_color(bg_rgb)
        return StyleMeasurement(spec=spec, box=b, kind=model.kind, n_lines=1,
                                stroke_px=float(model.stroke_width),
                                ink_fraction=float(model.ink_fraction),
                                background_color=bg_rgb, confidence=0.05,
                                warnings=warnings)

    comps = [c for c in _components(core) if c["area"] >= max(4, int(0.00025 * hh * ww))]
    if not comps:
        comps = _components(core)
    metrics = _line_metrics(core, comps)
    sw = _stroke_width(core)

    cap_px = float(metrics["cap_px"] or 0.0)
    x_px = metrics["x_px"]
    if cap_px >= 2:
        size_px = cap_px / CAP_EM
    elif x_px:
        size_px = float(x_px) / XH_EM
    else:
        size_px = float(base.size_px or 48)
    size_px = float(np.clip(size_px, 6.0, 4.0 * max(hh, 1)))

    text_rgb = _text_color(patch, core, halo, alpha, bg_rgb) or model.text_color
    mid_mask = (alpha >= 0.5) & _dilate(core, 3)
    align, ink_box, align_conf = _alignment(
        mid_mask if mid_mask.any() else core, metrics["lines"], ww, role)
    valign = _valign(ink_box, hh)
    baseline = metrics["baseline"]
    n_lines = max(1, len(metrics["lines"]))

    line_height = float(base.line_height or 1.2)
    if metrics["line_gap"] and size_px > 0:
        line_height = float(np.clip(float(metrics["line_gap"]) / size_px, 1.0, 2.2))

    deg, gain = _italic_angle(core, baseline if baseline is not None else hh * 0.8)
    italic_measured = bool(abs(deg) >= ITALIC_MIN_DEG and gain >= ITALIC_MIN_GAIN)

    rho = sw / cap_px if cap_px >= 2 else 0.0
    weight_measured, calibrated = ("regular", False)
    if rho > 0:
        # Com hint, o peso é do hint (a visão leu a marca): a sondagem só serviria
        # para o diagnóstico, então fica na tabela, que é grátis.
        weight_measured, calibrated = _weight_from_rho(
            rho, base.family, italic_measured, int(round(size_px)),
            calibrate=hint is None)

    # Refino do corpo com as métricas reais da família/peso que vamos desenhar.
    # A x-height é a medida preferida quando há minúsculas: são muitas letras
    # sobre a mesma linha, enquanto o grupo "alto" pode ser ascendente (0,73 em)
    # em vez de maiúscula (0,69 em) e não há como distinguir sem OCR.
    weight_final = base.weight if hint is not None else weight_measured
    fam = base.family
    size_source = "tabela"
    if x_px and int(metrics.get("n_x", 0)) >= 3:
        r = _xh_ratio(fam, weight_final, italic_measured)
        if r:
            size_px, size_source = float(x_px) / r, "x-height"
    if size_source == "tabela" and cap_px >= 2:
        r = _cap_ratio(fam, weight_final, italic_measured)
        if r:
            size_px, size_source = cap_px / r, "cap-height"
    size_px = float(np.clip(size_px, 6.0, 4.0 * max(hh, 1)))
    if metrics["line_gap"]:
        line_height = float(np.clip(float(metrics["line_gap"]) / size_px, 1.0, 2.2))

    stroke_w, stroke_rgb = _stroke(patch, core, halo, alpha, sw, text_rgb, bg_rgb)
    shadow = _shadow(patch, model.background, core, model.erase,
                     float(getattr(model, "noise_sigma", 0.0)),
                     cap_px if cap_px >= 2 else size_px * CAP_EM, bg_rgb,
                     kind=model.kind, residual=float(getattr(model, "residual", 99.0)))
    ls = _letter_spacing(mid_mask if mid_mask.any() else core, metrics["lines"],
                         known_text, fam, weight_final, italic_measured,
                         int(round(size_px)))

    uppercase = metrics["uppercase"]
    confidence = float(np.clip(
        0.25 + 0.35 * min(1.0, n_core / 600.0) + 0.2 * min(1.0, cap_px / 24.0) + 0.2 * align_conf,
        0.0, 1.0))

    # --- combinação com o hint (a regra do produto) ------------------------ #
    # A visão manda em família e peso; os pixels mandam em cor e tamanho.
    spec = replace(base)
    spec.size_px = int(max(MIN_DRAW_PX, round(size_px)))
    if text_rgb is not None:
        spec.color = tuple(int(v) for v in text_rgb)  # type: ignore[assignment]
    if hint is None:
        spec.weight = weight_measured
    spec.italic = italic_measured if confidence >= 0.4 else bool(base.italic)
    spec.align = align
    spec.valign = valign
    spec.line_height = round(line_height, 3)
    spec.letter_spacing = round(ls, 2)
    if uppercase is not None:
        spec.uppercase = bool(uppercase)
    spec.stroke_width = stroke_w
    spec.stroke_color = stroke_rgb if stroke_w else None
    if shadow:
        spec.shadow = True
        spec.shadow_color = shadow["color"]
        spec.shadow_offset = shadow["offset"]
        spec.shadow_blur = shadow["blur"]
        if shadow["residual"] > 0.15:
            reach = abs(shadow["offset"][0]) + abs(shadow["offset"][1]) + shadow["blur"]
            warnings.append(
                f"a sombra do texto original ficou {int(round(shadow['residual'] * 100))}% "
                "fora da máscara de apagamento e pode continuar visível; aumente a caixa "
                f"em ~{int(reach)} px ou use engine=ai nesta imagem"
            )
    else:
        spec.shadow = False

    if (hint is not None and hint.size_px and size_px > 0
            and int(hint.size_px) != FontSpec().size_px):
        ratio = float(hint.size_px) / size_px
        if ratio < 0.6 or ratio > 1.7:
            warnings.append(
                f"a visão estimou corpo {int(hint.size_px)}px e os pixels dizem "
                f"{spec.size_px}px; usando a medida dos pixels"
            )

    measured = {
        "rho": round(rho, 4),
        "weight_measured": weight_measured,
        "weight_calibrated": calibrated,
        "italic_deg": round(deg, 2),
        "italic_gain": round(gain, 3),
        "align_confidence": round(align_conf, 2),
        "size_source": size_source,
        "technique": getattr(model, "technique", ""),
        "residual": round(float(getattr(model, "residual", 0.0)), 2),
        "noise_sigma": round(float(getattr(model, "noise_sigma", 0.0)), 2),
        "shadow": shadow,
    }
    warnings.extend(w for w in getattr(model, "warnings", []) if w not in warnings)

    return StyleMeasurement(
        spec=spec, box=b, kind=model.kind, n_lines=n_lines, baseline=baseline,
        cap_px=cap_px, x_px=float(x_px) if x_px else None, stroke_px=sw,
        ink=ink_box, ink_fraction=float(model.ink_fraction), text_color=text_rgb,
        background_color=bg_rgb, confidence=confidence, measured=measured,
        warnings=warnings,
    )


def _contrast_color(bg: Sequence[int]) -> tuple[int, int, int]:
    """Preto ou branco — o que tiver contraste sobre `bg` (só como último recurso)."""
    r, g, b = (float(v) for v in list(bg)[:3])
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (17, 17, 17) if lum > 140 else (255, 255, 255)


def infer_style_from_pixels(img: Image.Image, box: Any, *,
                            hint: FontSpec | None = None) -> FontSpec:
    """Deduz o :class:`FontSpec` do texto que está dentro de ``box``.

    Mede cor, corpo, peso, itálico, alinhamento, entrelinha, tracking, contorno
    e sombra direto dos pixels (item D do projeto técnico). Com ``hint`` (o que
    a visão achou) a combinação é: **família e peso vêm do hint**, **cor e
    tamanho vêm dos pixels** — a visão erra tamanho com frequência e a cor
    "aparente" do texto é sempre puxada para o fundo pelo anti-aliasing.
    """
    return measure_style(img, box, hint=hint).spec


# --------------------------------------------------------------------------- #
# E — redesenhar na mesma caixa
# --------------------------------------------------------------------------- #
@dataclass
class FitPlan:
    """Resultado da escada de degradação (E.3)."""

    spec: FontSpec
    size_px: int
    layout: Any                      # fonts.TextLayout
    step: str = ""
    ratio: float = 1.0               # size_px / size original
    ok: bool = True
    warnings: list[str] = field(default_factory=list)


def _materialize(spec: FontSpec, size: int, ls_em: float) -> FontSpec:
    """Congela o spec num corpo concreto.

    ``fonts.draw_text_block``/``plan_text_layout`` usam ``letter_spacing`` em
    **pixels absolutos**, enquanto ``fit_font_size`` o trata proporcionalmente
    ao corpo. Materializar aqui é o que mantém os três de acordo.
    """
    out = replace(spec)
    out.size_px = int(size)
    out.letter_spacing = round(ls_em * size, 3)
    return out


def _try_fit(text: str, box: Box, spec: FontSpec, *, ls_em: float, max_lines: int,
             floor_px: int, max_px: int) -> tuple[int, FontSpec, Any] | None:
    """Maior corpo que cabe com esses parâmetros, ou None se não chegar ao piso."""
    probe = _materialize(spec, max(MIN_DRAW_PX, int(round(max_px))), ls_em)
    size = _fonts.fit_font_size(text, box, probe, max_lines=max_lines,
                                min_px=MIN_DRAW_PX, max_px=int(max_px))
    if size < floor_px:
        return None
    final = _materialize(spec, size, ls_em)
    layout = _fonts.plan_text_layout(text, box, final, size_px=size, max_lines=max_lines)
    if not layout.fits:
        # `fit_font_size` devolve `min_px` quando nada cabe; confirmar é barato.
        return None
    return size, final, layout


def _condensed_family(family: str) -> str | None:
    """Variante condensada instalada da mesma família, se existir."""
    try:
        have = set(_fonts.list_available_families())
    except Exception:  # pragma: no cover
        return None
    stem = "".join(ch for ch in str(family).lower() if ch.isalnum())
    for suffix in ("condensed", "tight", "narrow", "cond"):
        cand = stem + suffix
        if cand in have:
            return cand
    return None


def plan_fit(text: str, box: Box, spec: FontSpec, *, size_hint: int | None = None,
             n_lines: int = 1) -> FitPlan:
    """Escada de degradação do item E.3 — para no primeiro degrau que couber.

    Ordem: corpo livre perto do original → mais uma linha → entrelinha menor →
    tracking levemente negativo → variante condensada → mais duas linhas →
    corpo até 55% → falha explícita. Nunca estoura a caixa: se nada couber, a
    função devolve ``ok=False`` com um aviso em português e quem chama decide.
    """
    warnings: list[str] = []
    s0 = int(size_hint or spec.size_px or 48)
    s0 = max(MIN_DRAW_PX, s0)
    n0 = max(1, int(n_lines))
    ls_em0 = float(spec.letter_spacing or 0.0) / max(1.0, float(spec.size_px or s0))
    lh0 = float(spec.line_height or 1.2)
    # E.5: o corpo original é **teto**, não alvo. O projeto técnico permite até
    # 1,15·s0, mas inflar 15% num CTA é visível a olho nu e o erro da medida de
    # cap-height é de ~3% — não compensa. Copy mais curta fica no corpo de antes.
    max_px = s0
    small = s0 <= LS_MIN_SIZE_PX

    steps: list[tuple[str, dict[str, Any], float]] = [
        ("corpo original", {"ls_em": ls_em0, "lh": lh0, "ml": n0}, SIZE_TARGET_MIN),
        ("mais uma linha", {"ls_em": ls_em0, "lh": lh0, "ml": n0 + 1}, SIZE_TARGET_MIN),
        ("entrelinha menor", {"ls_em": ls_em0, "lh": max(LINE_HEIGHT_FLOOR, min(lh0, 1.08)),
                              "ml": n0 + 1}, SIZE_TARGET_MIN),
    ]
    if not small:
        steps += [
            ("tracking -1,5%", {"ls_em": ls_em0 - 0.015, "lh": max(LINE_HEIGHT_FLOOR, min(lh0, 1.10)),
                                "ml": n0 + 1}, SIZE_TARGET_MIN),
            ("tracking -3,5%", {"ls_em": max(LS_FLOOR_EM, ls_em0 - 0.035),
                                "lh": max(LINE_HEIGHT_FLOOR, min(lh0, 1.08)),
                                "ml": n0 + 1}, SIZE_TARGET_MIN),
        ]
    cond = _condensed_family(spec.family)
    if cond:
        steps.append(("família condensada", {"ls_em": ls_em0, "lh": lh0, "ml": n0 + 1,
                                             "family": cond}, SIZE_TARGET_MIN))
    steps += [
        ("mais duas linhas", {"ls_em": ls_em0, "lh": max(LINE_HEIGHT_FLOOR, min(lh0, 1.12)),
                              "ml": n0 + 2}, SIZE_WARN_MIN),
        ("corpo reduzido", {"ls_em": max(LS_FLOOR_EM, ls_em0 - 0.02) if not small else ls_em0,
                            "lh": max(LINE_HEIGHT_FLOOR, min(lh0, 1.08)),
                            "ml": n0 + 2}, SIZE_HARD_MIN),
    ]

    for name, kw, floor in steps:
        cand = replace(spec)
        if kw.get("family"):
            cand.family = str(kw["family"])
        cand.line_height = float(kw["lh"])
        got = _try_fit(text, box, cand, ls_em=float(kw["ls_em"]), max_lines=int(kw["ml"]),
                       floor_px=int(math.floor(floor * s0)), max_px=max_px)
        if got is None:
            continue
        size, final, layout = got
        ratio = size / float(s0)
        if ratio < SIZE_WARN_MIN:
            warnings.append(
                f"texto reduzido para {int(round(ratio * 100))}% do corpo original "
                f"({size}px em vez de {s0}px) para caber na caixa"
            )
        elif ratio < SIZE_TARGET_MIN:
            warnings.append(
                f"corpo ajustado para {size}px (original {s0}px) para caber na caixa"
            )
        if int(kw["ml"]) > n0 and len([l for l in layout.lines if l.strip()]) > n0:
            warnings.append(
                f"o texto novo ocupa {len([l for l in layout.lines if l.strip()])} linhas "
                f"(o original tinha {n0})"
            )
        return FitPlan(spec=final, size_px=size, layout=layout, step=name,
                       ratio=ratio, ok=True, warnings=warnings)

    # Último recurso: qualquer corpo legível, com aviso forte.
    cand = replace(spec)
    cand.line_height = max(LINE_HEIGHT_FLOOR, min(lh0, 1.05))
    got = _try_fit(text, box, cand, ls_em=ls_em0 if small else max(LS_FLOOR_EM, ls_em0 - 0.02),
                   max_lines=max(4, n0 + 3), floor_px=MIN_DRAW_PX, max_px=max_px)
    if got is not None:
        size, final, layout = got
        warnings.append(
            f"a copy nova é longa demais para a caixa: o corpo caiu para {size}px "
            f"({int(round(100 * size / s0))}% do original). Encurte o texto ou "
            f"aumente a caixa na receita."
        )
        return FitPlan(spec=final, size_px=size, layout=layout, step="último recurso",
                       ratio=size / float(s0), ok=True, warnings=warnings)

    warnings.append(
        "o texto novo não cabe na caixa nem no menor corpo aceitável "
        f"({MIN_DRAW_PX}px). Nada foi desenhado — encurte a copy ou aumente a caixa."
    )
    return FitPlan(spec=_materialize(cand, MIN_DRAW_PX, ls_em0), size_px=MIN_DRAW_PX,
                   layout=None, step="não coube", ratio=0.0, ok=False, warnings=warnings)


def _probe_ink(text: str, box: Box, spec: FontSpec, size_px: int,
               img_size: tuple[int, int]) -> Box | None:
    """Onde a tinta do texto novo *de fato* cai dentro da caixa.

    Não dá para usar a geometria prevista pelo layout: ``getbbox`` de uma string
    devolve a caixa de **avanço** (0..advance), não a extensão da tinta — medimos
    3 px de diferença à esquerda e 5 à direita num CTA de 70px. Ancorar por ela
    empurraria o texto. Um raster sem supersampling (a geometria é a mesma) custa
    poucos milissegundos e dá a resposta exata.
    """
    try:
        mask = _fonts.text_mask(text, box, spec, img_size, include_stroke=True,
                                supersample=1)
    except Exception:  # pragma: no cover
        return None
    arr = np.asarray(mask, dtype=np.uint8)[box.y:box.y1, box.x:box.x1] >= 128
    if not arr.any():
        return None
    ys = np.flatnonzero(arr.any(axis=1))
    xs = np.flatnonzero(arr.any(axis=0))
    return Box(int(xs[0]), int(ys[0]), int(xs[-1] - xs[0]) + 1, int(ys[-1] - ys[0]) + 1)


def _anchor_box(box: Box, layout: Any, meas: StyleMeasurement | None,
                ink_pred: Box | None) -> Box:
    """Translada a caixa de desenho para a tinta cair onde ela estava (E.5).

    Preserva **largura e altura** — mexer nelas mudaria a quebra de linha e o
    valign, ou seja, um layout diferente do que foi medido. Só transladamos, e
    só o quanto mantém a tinta inteira dentro da caixa declarada.
    """
    if meas is None or layout is None or ink_pred is None or not layout.baselines:
        return box
    dy = 0
    if meas.baseline is not None:
        # distância do topo da tinta até a primeira baseline (geometria vertical
        # prevista bate com a real; só a horizontal é que não)
        to_baseline = float(layout.baselines[0]) - float(layout.ink[1])
        desired_top = float(meas.baseline) - to_baseline
        dy = int(round(desired_top - ink_pred.y))
        lo, hi = -ink_pred.y, box.h - ink_pred.y1
        dy = int(np.clip(dy, lo, hi)) if lo <= hi else 0

    dx = 0
    if meas.ink is not None and ink_pred.w > 0:
        align = str(meas.spec.align or "center").lower()
        if align == "left":
            desired = float(meas.ink.x)
        elif align == "right":
            desired = float(meas.ink.x1 - ink_pred.w)
        else:
            desired = float(meas.ink.center[0]) - ink_pred.w / 2.0
        dx = int(round(desired - ink_pred.x))
        lo, hi = -ink_pred.x, box.w - ink_pred.x1
        dx = int(np.clip(dx, lo, hi)) if lo <= hi else 0

    return Box(box.x + dx, box.y + dy, box.w, box.h)


def _erase(img: Image.Image, box: Box, *, kind: BackgroundKind | str | None,
           feather: int, report: dict[str, Any], model: Any = None) -> Image.Image:
    """Apaga a região usando o motor determinístico do :mod:`inpaint`.

    Com ``model`` (o :class:`inpaint.RegionModel` que a medição já calculou)
    reaproveitamos a escrita em vez de reanalisar a caixa: além de cortar ~40%
    do tempo por imagem, garante que o que foi apagado é exatamente a tinta que
    foi medida. Se essa porta interna não existir na versão do `inpaint`
    instalada, caímos na API pública sem mudar o resultado.
    """
    sub: dict[str, Any] = {}
    out: Image.Image | None = None
    commit = getattr(_inpaint, "_commit", None)
    if model is not None and callable(commit):
        try:
            rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
            arr = commit(rgb, model.box, model.background, model.erase, int(feather))
            out = Image.fromarray(arr, "RGB")
            if img.mode == "RGBA":
                out.putalpha(img.getchannel("A"))
            sub = model.to_dict()
            if not model.erase.any():
                sub.setdefault("warnings", []).append("nenhuma tinta detectada na caixa")
        except Exception as exc:  # pragma: no cover - contrato do inpaint mudou
            log.debug("commit direto falhou (%s); usando erase_region", exc)
            out = None
    if out is None:
        sub = {}
        out = _inpaint.erase_region(img, box, kind=kind, feather=feather, report=sub)
    report["erase"] = sub
    for w in sub.get("warnings", []) or []:
        if w not in report.setdefault("warnings", []):
            report["warnings"].append(w)
    if out.mode != img.mode and img.mode in ("RGB", "RGBA"):
        out = out.convert(img.mode)
    return out


def _confine(base: Image.Image, drawn: Image.Image, box: Box) -> Image.Image:
    """Devolve `base` com **apenas** a região `box` vinda de `drawn`.

    Cinto e suspensório: ``fonts.draw_text_block`` já promete não sair da caixa,
    mas é aqui que o confinamento vira aritmética em vez de confiança.
    """
    if box.area <= 0:
        return base
    out = base.copy()
    out.paste(drawn.crop(box.xyxy), (box.x, box.y))
    return out


def replace_text(img: Image.Image, block: TextBlock, new_text: str, *,
                 settings: Any = None, style_override: Any = None,
                 autofit: bool = True, feather: int = 1,
                 report: dict[str, Any] | None = None) -> tuple[Image.Image, Box]:
    """Troca o texto de ``block`` por ``new_text`` sem tocar no resto da imagem.

    O caminho é sempre o determinístico: mede o estilo nos pixels (D), apaga a
    região reconstruindo o fundo (:func:`inpaint.erase_region`, item C), acha o
    corpo que cabe (escada E.3) e redesenha (:func:`fonts.draw_text_block`, E.6).

    Devolve ``(imagem_nova, caixa_alterada)``. A caixa é a **união do que foi
    apagado com a tinta nova** — na prática, a bounding box exata dos pixels que
    mudaram — e é ela que deve ir para ``ImageResult.changed_boxes`` e para a
    verificação de drift. Fora dela, garantidamente, nada mudou.

    ``style_override`` aceita ``dict`` (sobrescreve só as chaves informadas — o
    modo recomendado) ou ``FontSpec`` (substitui o estilo inteiro, exceto o
    corpo quando ``autofit=True``). ``settings`` é aceito por contrato; esta
    trilha é 100% offline e não usa a chave de API.
    """
    rep: dict[str, Any] = report if report is not None else {}
    rep.setdefault("warnings", [])
    rep["operation"] = "replace_text"
    rep["engine"] = "deterministic"

    img = _normalize_mode(img, rep["warnings"])
    box = _as_box(block.box, img.width, img.height)
    if box.area <= 0:
        raise ValueError(
            "a caixa do bloco de texto ficou vazia dentro da imagem.\n"
            "  Verifique as coordenadas na receita (x/y/w/h ou normalizadas 0–1)."
        )
    text = str(new_text if new_text is not None else "")

    fw_before = _fonts.font_warnings()
    forced_kind: BackgroundKind | str | None = None
    if block.on_solid_background:
        forced_kind = BackgroundKind.SOLID
    model = _inpaint.analyze_region(img, box, kind=forced_kind)

    meas = measure_style(img, box, hint=block.style, known_text=block.text or "",
                         role=block.role if isinstance(block.role, TextRole) else None,
                         kind=forced_kind, model=model)
    spec = _apply_override(meas.spec, style_override)
    rep["style"] = meas.to_dict()

    before = _rgb_view(img)
    erased = _erase(img, box, kind=model.kind, feather=feather, report=rep, model=model)

    if not text.strip():
        rep["warnings"].append(
            "texto novo vazio: a região foi apagada e nada foi escrito "
            "(use a operação remove_text se essa era a intenção)"
        )
        changed = _changed_box(before, _rgb_view(erased), box)
        rep["fits"] = True
        rep["changed_box"] = changed.to_dict() if changed else None
        return erased, changed or box

    if autofit:
        plan = plan_fit(text, box, spec, size_hint=spec.size_px, n_lines=meas.n_lines)
    else:
        layout = _fonts.plan_text_layout(text, box, spec, size_px=spec.size_px)
        plan = FitPlan(spec=spec, size_px=int(spec.size_px), layout=layout,
                       step="corpo fixo", ratio=1.0, ok=bool(layout.fits))
        if not layout.fits:
            plan.warnings.append(
                f"com autofit desligado o texto não cabe na caixa no corpo {spec.size_px}px; "
                "o excedente seria cortado"
            )
    for w in plan.warnings:
        if w not in rep["warnings"]:
            rep["warnings"].append(_warn(w))
    for w in meas.warnings:
        if w not in rep["warnings"]:
            rep["warnings"].append(w)
    rep["fit"] = {"step": plan.step, "size_px": plan.size_px,
                  "ratio": round(plan.ratio, 3), "ok": plan.ok,
                  "lines": len([l for l in (plan.layout.lines if plan.layout else []) if l.strip()])}
    rep["fits"] = bool(plan.ok)
    rep["ok"] = bool(plan.ok)

    if not plan.ok:
        # Aviso claro em vez de estourar a caixa — e devolvemos a imagem
        # **intacta**: entregar a peça com o CTA apagado e vazio seria pior do
        # que entregá-la como estava e falhar alto no manifesto.
        rep["changed_box"] = None
        rep["ok"] = False
        return img.copy(), Box(box.x, box.y, 0, 0)

    ink_pred = _probe_ink(text, box, plan.spec, plan.size_px, img.size)
    draw_box = _anchor_box(box, plan.layout, meas, ink_pred)
    if (draw_box.x < 0 or draw_box.y < 0
            or draw_box.x1 > img.width or draw_box.y1 > img.height):
        draw_box = box      # a translação sairia da imagem: melhor não ancorar
    rep["anchor"] = {"dx": draw_box.x - box.x, "dy": draw_box.y - box.y}

    drawn = _fonts.draw_text_block(erased, text, draw_box, plan.spec,
                                   size_px=plan.size_px)
    out = _confine(erased, drawn, box)

    after = _rgb_view(out)
    changed = _changed_box(before, after, box)
    if changed is None:
        rep["warnings"].append(
            "nada mudou na imagem: o texto novo é idêntico ao que já estava lá?"
        )
        rep["changed_box"] = None
        return out, box
    if _touches_border(changed, box):
        rep["warnings"].append(
            "a tinta nova encosta na borda da caixa: aumente a caixa em 2–3 px "
            "se aparecer corte no contorno ou na sombra"
        )
    rep["changed_box"] = changed.to_dict()
    rep["changed_fraction"] = round(changed.area / max(1, box.area), 4)
    for w in _new_font_warnings(fw_before):
        if w not in rep["warnings"]:
            rep["warnings"].append(w)
    return out, changed


def _touches_border(inner: Box, outer: Box) -> bool:
    return (inner.x <= outer.x or inner.y <= outer.y
            or inner.x1 >= outer.x1 or inner.y1 >= outer.y1)


def _apply_override(spec: FontSpec, override: Any) -> FontSpec:
    """`dict` sobrescreve só as chaves dadas; `FontSpec` substitui tudo."""
    if override is None:
        return spec
    if isinstance(override, FontSpec):
        return replace(override)
    if isinstance(override, dict):
        merged = spec.to_dict()
        merged.update(override)
        return FontSpec.from_dict(merged)
    raise ValueError(
        f"style_override inválido: {type(override).__name__}.\n"
        "  Use um dicionário com as chaves que quer forçar (ex.: {'color': '#ffffff'}) "
        "ou um FontSpec completo."
    )


def remove_text(img: Image.Image, block: TextBlock, *, settings: Any = None,
                feather: int = 1,
                report: dict[str, Any] | None = None) -> tuple[Image.Image, Box]:
    """Apaga o texto do bloco reconstruindo o fundo. Não escreve nada por cima.

    Devolve ``(imagem_nova, caixa_alterada)`` com a caixa igual à bounding box
    dos pixels efetivamente apagados.
    """
    rep: dict[str, Any] = report if report is not None else {}
    rep.setdefault("warnings", [])
    rep["operation"] = "remove_text"
    rep["engine"] = "deterministic"

    img = _normalize_mode(img, rep["warnings"])
    box = _as_box(block.box, img.width, img.height)
    if box.area <= 0:
        raise ValueError(
            "a caixa do bloco de texto ficou vazia dentro da imagem.\n"
            "  Verifique as coordenadas na receita (x/y/w/h ou normalizadas 0–1)."
        )
    forced = BackgroundKind.SOLID if block.on_solid_background else None
    before = _rgb_view(img)
    out = _erase(img, box, kind=forced, feather=feather, report=rep)
    changed = _changed_box(before, _rgb_view(out), box)
    if changed is None:
        rep["warnings"].append(
            "nenhuma tinta foi encontrada na caixa: nada foi apagado "
            "(a caixa pode estar no lugar errado)"
        )
    rep["changed_box"] = changed.to_dict() if changed else None
    return out, changed or box


def add_text(img: Image.Image, box: Any, text: str, spec: FontSpec, *,
             autofit: bool = True,
             report: dict[str, Any] | None = None) -> tuple[Image.Image, Box]:
    """Desenha ``text`` dentro de ``box`` sem apagar nada antes.

    Com ``autofit`` (padrão) o corpo desce pela escada E.3 até caber; sem ele o
    corpo de ``spec`` é respeitado e o que não couber seria cortado — nesse caso
    registramos um aviso.
    """
    rep: dict[str, Any] = report if report is not None else {}
    rep.setdefault("warnings", [])
    rep["operation"] = "add_text"
    rep["engine"] = "deterministic"

    img = _normalize_mode(img, rep["warnings"])
    b = _as_box(box, img.width, img.height)
    if b.area <= 0:
        raise ValueError(
            "a caixa pedida ficou vazia dentro da imagem.\n"
            "  Verifique as coordenadas (x/y/w/h ou normalizadas 0–1)."
        )
    txt = str(text or "")
    if not txt.strip():
        rep["warnings"].append("texto vazio: nada foi desenhado")
        return img.copy(), Box(b.x, b.y, 0, 0)

    fw_before = _fonts.font_warnings()
    use = replace(spec)
    if not str(use.family or "").strip():
        use.family = _default_family()
    if autofit:
        plan = plan_fit(txt, b, use, size_hint=use.size_px, n_lines=1)
        for w in plan.warnings:
            if w not in rep["warnings"]:
                rep["warnings"].append(_warn(w))
        rep["fits"] = bool(plan.ok)
        if not plan.ok:
            rep["changed_box"] = None
            return img.copy(), Box(b.x, b.y, 0, 0)
        use, size = plan.spec, plan.size_px
    else:
        size = int(use.size_px or 48)
        layout = _fonts.plan_text_layout(txt, b, use, size_px=size)
        rep["fits"] = bool(layout.fits)
        if not layout.fits:
            rep["warnings"].append(
                f"o texto não cabe em {b.w}x{b.h}px no corpo {size}px e será cortado; "
                "ligue o autofit ou aumente a caixa"
            )

    before = _rgb_view(img)
    drawn = _fonts.draw_text_block(img, txt, b, use, size_px=size)
    out = _confine(img, drawn, b)
    changed = _changed_box(before, _rgb_view(out), b)
    rep["changed_box"] = changed.to_dict() if changed else None
    if changed is None:
        rep["warnings"].append("o texto desenhado ficou idêntico ao fundo: nada mudou")
    for w in _new_font_warnings(fw_before):
        if w not in rep["warnings"]:
            rep["warnings"].append(w)
    return out, changed or Box(b.x, b.y, 0, 0)


# --------------------------------------------------------------------------- #
# Teste de fumaça (offline): python -m s7editor.textedit
# --------------------------------------------------------------------------- #
def _demo_creative(w: int = 1080, h: int = 1350) -> tuple[Image.Image, Box]:
    """Criativo sintético: foto falsa em cima, faixa chapada e CTA embaixo."""
    from PIL import ImageDraw

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = (40 + 120 * yy / h + 40 * np.sin(xx / 90.0)).clip(0, 255)
    g = (70 + 90 * xx / w).clip(0, 255)
    b = (150 - 60 * yy / h).clip(0, 255)
    arr = np.stack([r, g, b], -1).astype(np.uint8)
    img = Image.fromarray(arr, "RGB")

    d = ImageDraw.Draw(img)
    cta = Box(int(0.12 * w), int(0.74 * h), int(0.76 * w), int(0.10 * h))
    d.rectangle(cta.xyxy, fill=(240, 62, 44))          # pastilha do CTA
    spec = FontSpec(family=_default_family(), weight="bold", size_px=int(cta.h * 0.46),
                    color=(255, 255, 255), align="center", valign="middle",
                    uppercase=True)
    img = _fonts.draw_text_block(img, "COMPRE AGORA", cta, spec)
    return img, cta


def _smoke_test() -> int:
    import time

    clear_edit_warnings()
    img, cta = _demo_creative()
    block = TextBlock(box=cta, text="COMPRE AGORA", role=TextRole.CTA,
                      style=FontSpec(family=_default_family(), weight="bold"),
                      on_solid_background=True)

    print("== estilo medido nos pixels ==")
    meas = measure_style(img, cta, hint=block.style, known_text=block.text,
                         role=TextRole.CTA)
    print(f"  cor={meas.spec.color} corpo={meas.spec.size_px}px peso={meas.spec.weight} "
          f"align={meas.spec.align} caixa-alta={meas.spec.uppercase} "
          f"italico={meas.spec.italic} conf={meas.confidence:.2f}")
    print(f"  fundo={meas.kind.value} bg={meas.background_color} cap={meas.cap_px:.1f}px "
          f"stroke={meas.stroke_px:.2f}px rho={meas.measured.get('rho')}")

    falhas = 0
    if meas.spec.color != (255, 255, 255):
        de = _delta_e(meas.spec.color, (255, 255, 255))
        print(f"  ! cor medida {meas.spec.color} (ΔE={de:.1f} do branco)")
        if de > 20:
            falhas += 1
    if not meas.spec.uppercase:
        print("  ! não detectou caixa alta")
        falhas += 1

    for novo in ("GARANTA O SEU", "QUERO AGORA", "APROVEITE ESTA OFERTA POR TEMPO LIMITADO"):
        rep: dict[str, Any] = {}
        t0 = time.time()
        out, changed = replace_text(img, block, novo, report=rep)
        dt = time.time() - t0

        a, b = _rgb_view(img), _rgb_view(out)
        assert a.shape == b.shape, "as dimensões mudaram: drift indefinido"
        diff = np.any(a != b, axis=2)
        allowed = np.zeros(diff.shape, bool)
        allowed[changed.y:changed.y1, changed.x:changed.x1] = True
        fora = int(np.count_nonzero(diff & ~allowed))
        dentro = int(np.count_nonzero(diff & allowed))
        print(f"\n== '{novo[:32]}' == {dt*1000:.0f} ms")
        print(f"  caixa alterada {changed.to_dict()} (declarada {cta.to_dict()})")
        print(f"  drift fora={fora}  mudou dentro={dentro}  "
              f"passo={rep['fit']['step']} corpo={rep['fit']['size_px']}px "
              f"linhas={rep['fit']['lines']}")
        for w in rep.get("warnings", []):
            print(f"  aviso: {w}")
        if fora != 0:
            print("  !! DRIFT FORA DA CAIXA")
            falhas += 1
        if dentro == 0:
            print("  !! nada mudou dentro da caixa")
            falhas += 1
        if not (changed.x >= cta.x and changed.y >= cta.y
                and changed.x1 <= cta.x1 and changed.y1 <= cta.y1):
            print("  !! a caixa alterada saiu da caixa declarada")
            falhas += 1
        # determinismo: rodar de novo tem que dar o mesmo arquivo
        out2, changed2 = replace_text(img, block, novo)
        if not np.array_equal(_rgb_view(out2), b) or changed2 != changed:
            print("  !! resultado não determinístico")
            falhas += 1

    # remove_text e add_text
    rep = {}
    out, changed = remove_text(img, block, report=rep)
    diff = np.any(_rgb_view(img) != _rgb_view(out), axis=2)
    allowed = np.zeros(diff.shape, bool)
    allowed[changed.y:changed.y1, changed.x:changed.x1] = True
    fora = int(np.count_nonzero(diff & ~allowed))
    print(f"\n== remove_text == caixa={changed.to_dict()} drift fora={fora}")
    if fora:
        falhas += 1
    out2, ch2 = add_text(out, cta, "NOVO CTA", meas.spec)
    diff2 = np.any(_rgb_view(out) != _rgb_view(out2), axis=2)
    allowed2 = np.zeros(diff2.shape, bool)
    allowed2[ch2.y:ch2.y1, ch2.x:ch2.x1] = True
    fora2 = int(np.count_nonzero(diff2 & ~allowed2))
    print(f"== add_text == caixa={ch2.to_dict()} drift fora={fora2}")
    if fora2:
        falhas += 1

    print("\nOK" if not falhas else f"\nFALHAS: {falhas}")
    return 0 if not falhas else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_smoke_test())
