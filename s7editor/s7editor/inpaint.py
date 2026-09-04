"""Reconstrução de fundo: apagar texto sem tocar no resto da imagem.

Este é o coração da trilha determinística. Tudo aqui obedece a uma regra só:

    ``erase_region`` escreve pixels **exclusivamente** dentro do recorte
    ``img[box.y:box.y1, box.x:box.x1]``.

A regra é estrutural, não uma promessa: nenhuma função aplica filtro na imagem
inteira. Todo processamento acontece em cópias de recorte e a única escrita é a
atribuição no slice da caixa (``_commit``). O contexto ao redor da caixa é
*lido* (o inpaint precisa dele para não produzir listras na borda), mas nunca
escrito.

Pipeline, na ordem:

A. classificar o fundo dentro da caixa (sólido / degradê / foto / padrão);
B. segmentar os glifos sem OCR (modelo de fundo por pixel + limiar de Otsu);
C. apagar reconstruindo o fundo (moda robusta, mínimos quadrados ou inpaint).

Os limiares não são constantes mágicas: quase todos são
``max(constante, múltiplo · σ_ruído)``, com σ estimado da própria imagem pelo
estimador de Immerkær. É isso que faz o classificador continuar funcionando em
criativo salvo em JPEG, onde um fundo genuinamente chapado tem desvio de 4–6
níveis por canal.

``cv2`` é usado quando existe (inpaint TELEA, componentes conexas), mas o
módulo funciona inteiro sem ele — com qualidade menor no inpaint, que cai para
uma difusão multi-escala em numpy puro.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image

from .models import BackgroundKind, Box

try:  # opcional: acelera e melhora o inpaint, mas nada aqui depende dele
    import cv2  # type: ignore
except Exception:  # pragma: no cover - só acontece em ambiente sem opencv
    cv2 = None  # type: ignore[assignment]

HAS_CV2: bool = cv2 is not None

__all__ = [
    "classify_region",
    "reconstruct_solid",
    "reconstruct_gradient",
    "inpaint_telea",
    "erase_region",
    "analyze_region",
    "glyph_mask",
    "delta_e",
    "RegionModel",
    "HAS_CV2",
]


# --------------------------------------------------------------------------- #
# Constantes (todas viram configuração se um dia precisar)
# --------------------------------------------------------------------------- #
NOISE_MULT_SOLID = 2.5      # T_solid = max(1.5, 2.5 * sigma_n)
NOISE_MULT_RAMP = 4.0       # T_ramp  = max(3.0, 4.0 * sigma_n)
NOISE_MULT_GRAD = 3.0       # T_grad  = max(3.0, 3.0 * sigma_n)
RESID_QUAD_MAX = 8.0        # acima disso nem tenta o ajuste quadrático
PERIOD_MIN = 0.30           # autocorrelação: separa pattern de photo
EDGE_MIN = 0.030
INK_FRAC_RANGE = (0.02, 0.60)
ALPHA_CORE = 0.90
ALPHA_HALO = 0.02
LSQ_MIN_BG_PIXELS = 50
LSQ_MIN_BG_FRAC = 0.25
LSQ_RESID_ACCEPT = 2.5
LSQ_COND_MAX = 1e6
MIN_REGION_AREA = 400       # abaixo disso não dá pra classificar nada
NOISE_REINJECT_MIN = 1.2    # abaixo disso o fundo é liso demais pra valer ruído
DELTA_E_DISTINCT = 25.0     # duas cores "diferentes" em Lab
FLAT_CLUSTER_SPREAD = 6.0   # dispersão interna de um grupo genuinamente chapado


def _erase_dilate(sw: float) -> int:
    """Quantos pixels dilatar a máscara de tinta para comer o anti-aliasing.

    Sub-dilatar deixa um fantasma cinza do contorno — o defeito mais visível de
    todos. Super-dilatar come textura e o resultado vira um borrão retangular.
    """
    return int(np.clip(round(0.5 * sw) + 1, 2, 6))


def _inpaint_radius(sw: float) -> int:
    return int(np.clip(round(1.2 * sw), 3, 10))


def _inpaint_context(sw: float) -> int:
    return int(max(8, round(3 * sw)))


# --------------------------------------------------------------------------- #
# Primitivas de array (funcionam com e sem cv2, sempre com o mesmo resultado)
# --------------------------------------------------------------------------- #
def _split_rgb(img: Image.Image) -> tuple[np.ndarray, np.ndarray | None]:
    """Separa RGB (uint8, gravável) do canal alfa, que segue intocado."""
    if img.mode == "RGBA":
        arr = np.array(img, dtype=np.uint8)
        return np.ascontiguousarray(arr[..., :3]), arr[..., 3].copy()
    if img.mode != "RGB":
        img = img.convert("RGB")
    return np.array(img, dtype=np.uint8), None


def _merge_rgb(rgb: np.ndarray, alpha: np.ndarray | None) -> Image.Image:
    rgb = np.ascontiguousarray(np.clip(rgb, 0, 255).astype(np.uint8))
    if alpha is None:
        return Image.fromarray(rgb, "RGB")
    return Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8), "RGBA")


def _max_filter_1d(a: np.ndarray, k: int, axis: int) -> np.ndarray:
    r = k // 2
    if r <= 0:
        return a
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r, r)
    p = np.pad(a, pad, mode="edge")
    n = a.shape[axis]
    out = None
    for i in range(k):
        sl: list[Any] = [slice(None)] * a.ndim
        sl[axis] = slice(i, i + n)
        v = p[tuple(sl)]
        out = v if out is None else np.maximum(out, v)
    return out  # type: ignore[return-value]


def _max_filter(a: np.ndarray, k: int) -> np.ndarray:
    """Filtro de máximo com kernel retangular k×k (separável, O(k·N))."""
    if k <= 1:
        return a
    return _max_filter_1d(_max_filter_1d(a, k, 0), k, 1)


def _min_filter(a: np.ndarray, k: int) -> np.ndarray:
    if k <= 1:
        return a
    return -_max_filter(-a.astype(np.float32), k)


def _box_blur(a: np.ndarray, k: int) -> np.ndarray:
    """Média móvel k×k separável (bordas replicadas)."""
    if k <= 1:
        return a.astype(np.float32)
    r = k // 2
    out = a.astype(np.float32)
    for axis in (0, 1):
        pad = [(0, 0)] * out.ndim
        pad[axis] = (r, r)
        p = np.pad(out, pad, mode="edge")
        n = out.shape[axis]
        acc = np.zeros_like(out)
        for i in range(k):
            sl: list[Any] = [slice(None)] * out.ndim
            sl[axis] = slice(i, i + n)
            acc += p[tuple(sl)]
        out = acc / float(k)
    return out


def _dilate(mask: np.ndarray, iters: int = 1) -> np.ndarray:
    """Dilatação binária 3×3 aplicada ``iters`` vezes (= kernel 2·iters+1)."""
    if iters <= 0:
        return mask.astype(bool)
    return _max_filter(mask.astype(np.uint8), 2 * int(iters) + 1) > 0


def _erode(mask: np.ndarray, iters: int = 1) -> np.ndarray:
    if iters <= 0:
        return mask.astype(bool)
    return _min_filter(mask.astype(np.float32), 2 * int(iters) + 1) > 0.5


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB -> CIELab na convenção de 8 bits do OpenCV (L·255/100, a+128, b+128).

    Implementado em numpy mesmo quando o cv2 existe: assim os limiares de ΔE
    valem exatamente igual nos dois caminhos, e o classificador não muda de
    resposta por causa do ambiente.
    """
    c = np.clip(np.asarray(rgb, dtype=np.float32), 0, 255) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array(
        [[0.4124564, 0.3575761, 0.1804375],
         [0.2126729, 0.7151522, 0.0721750],
         [0.0193339, 0.1191920, 0.9503041]], dtype=np.float32)
    xyz = lin @ m.T
    white = np.array([0.950456, 1.0, 1.088754], dtype=np.float32)
    t = xyz / white
    f = np.where(t > 0.008856, np.cbrt(np.maximum(t, 1e-9)), 7.787 * t + 16.0 / 116.0)
    lum = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([lum * 2.55, a + 128.0, b + 128.0], axis=-1).astype(np.float32)


def delta_e(c1: Any, c2: Any) -> float:
    """ΔE aproximado entre duas cores RGB (norma L2 no Lab de 8 bits).

    Público de propósito: quem precisa comparar cor de fundo (crescimento de
    caixa, detecção de contorno) deve usar a mesma métrica que o classificador.
    """
    l1 = _rgb_to_lab(np.asarray(c1, dtype=np.float32).reshape(1, 1, 3))[0, 0]
    l2 = _rgb_to_lab(np.asarray(c2, dtype=np.float32).reshape(1, 1, 3))[0, 0]
    return float(np.linalg.norm(l1 - l2))


def _gray(rgb: np.ndarray) -> np.ndarray:
    a = np.asarray(rgb, dtype=np.float32)
    return 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]


def _ring_mask(hh: int, ww: int, k: int) -> np.ndarray:
    """Anel de ``k`` px na borda do recorte — a amostra mais provável de fundo."""
    ring = np.zeros((hh, ww), dtype=bool)
    k = max(1, min(int(k), max(1, min(hh, ww) // 2)))
    ring[:k, :] = ring[-k:, :] = True
    ring[:, :k] = ring[:, -k:] = True
    return ring


def _noise_sigma(gray: np.ndarray, mask: np.ndarray | None = None) -> float:
    """σ do ruído pelo estimador de Immerkær (laplaciano duplo).

    Mede o grão real da imagem (JPEG, dithering, film grain) para que os
    limiares de "chapado" não sejam um chute fixo.
    """
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], dtype=np.float32)
    conv = _convolve3(gray, k)
    if mask is not None and mask.any():
        vals = np.abs(conv)[mask]
    else:
        vals = np.abs(conv).ravel()
    if vals.size == 0:
        return 0.0
    return float(np.sqrt(np.pi / 2.0) * vals.mean() / 6.0)


def _convolve3(a: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Convolução 3×3 em numpy puro (bordas replicadas)."""
    p = np.pad(a.astype(np.float32), 1, mode="edge")
    out = np.zeros_like(a, dtype=np.float32)
    h, w = a.shape[:2]
    for dy in range(3):
        for dx in range(3):
            kv = float(kernel[dy, dx])
            if kv:
                out += kv * p[dy:dy + h, dx:dx + w]
    return out


def _edge_fraction(gray: np.ndarray, mask: np.ndarray | None = None) -> float:
    """Fração de pixels com gradiente forte (proxy barato de Canny)."""
    sx = _convolve3(gray, np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32))
    sy = _convolve3(gray, np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32))
    mag = np.hypot(sx, sy)
    strong = mag > 60.0
    if mask is not None and mask.any():
        return float(strong[mask].mean())
    return float(strong.mean())


def _otsu(values: np.ndarray) -> int:
    """Limiar de Otsu sobre um array uint8 já quantizado em 0..255."""
    hist = np.bincount(values.ravel(), minlength=256).astype(np.float64)
    total = hist.sum()
    if total <= 0:
        return 128
    p = hist / total
    omega = np.cumsum(p)
    mu = np.cumsum(p * np.arange(256))
    mu_t = mu[-1]
    denom = omega * (1.0 - omega)
    with np.errstate(invalid="ignore", divide="ignore"):
        sigma_b = (mu_t * omega - mu) ** 2 / denom
    sigma_b = np.nan_to_num(sigma_b, nan=0.0, posinf=0.0, neginf=0.0)
    return int(np.argmax(sigma_b))


def _rng_for(box: Box) -> np.random.Generator:
    """RNG determinístico derivado da caixa: rodar duas vezes dá o mesmo arquivo."""
    seed = (box.x * 73856093) ^ (box.y * 19349663) ^ (box.w * 83492791) ^ (box.h * 2654435761)
    return np.random.default_rng(abs(seed) % (2 ** 32))


# --------------------------------------------------------------------------- #
# Componentes conexas (cv2 quando existe; propagação de rótulo quando não)
# --------------------------------------------------------------------------- #
def _components(mask: np.ndarray) -> tuple[np.ndarray, list[dict[str, int]]]:
    """(labels, stats) com stats = [{label,x,y,w,h,area}, ...], fundo excluído."""
    if not mask.any():
        return np.zeros(mask.shape, dtype=np.int32), []
    if cv2 is not None:
        n, lbl, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
        stats = [
            {"label": i, "x": int(st[i, 0]), "y": int(st[i, 1]),
             "w": int(st[i, 2]), "h": int(st[i, 3]), "area": int(st[i, 4])}
            for i in range(1, n)
        ]
        return lbl.astype(np.int32), stats
    return _components_numpy(mask)


def _components_numpy(mask: np.ndarray) -> tuple[np.ndarray, list[dict[str, int]]]:
    """Rotulagem por propagação de máximo — vetorizada, sem loop por pixel."""
    hh, ww = mask.shape
    cur = np.zeros((hh, ww), dtype=np.float32)
    cur[mask] = np.arange(1, int(mask.sum()) + 1, dtype=np.float32)
    limit = min(4 * (hh + ww), 2000)
    for _ in range(limit):
        nxt = _max_filter(cur, 3)
        nxt = np.where(mask, nxt, 0.0)
        if np.array_equal(nxt, cur):
            break
        cur = nxt
    raw = cur.astype(np.int64)
    uniq = np.unique(raw[mask])
    remap = np.zeros(int(raw.max()) + 1, dtype=np.int32)
    remap[uniq] = np.arange(1, len(uniq) + 1, dtype=np.int32)
    lbl = remap[raw]
    lbl[~mask] = 0

    ys, xs = np.nonzero(mask)
    ids = lbl[ys, xs]
    stats: list[dict[str, int]] = []
    order = np.argsort(ids, kind="stable")
    ids_s, ys_s, xs_s = ids[order], ys[order], xs[order]
    bounds = np.searchsorted(ids_s, np.arange(1, len(uniq) + 1), side="left")
    bounds = np.append(bounds, len(ids_s))
    for i in range(len(uniq)):
        a, b = bounds[i], bounds[i + 1]
        if b <= a:
            continue
        yy, xx = ys_s[a:b], xs_s[a:b]
        stats.append({
            "label": i + 1, "x": int(xx.min()), "y": int(yy.min()),
            "w": int(xx.max() - xx.min() + 1), "h": int(yy.max() - yy.min() + 1),
            "area": int(b - a),
        })
    return lbl, stats


def _stroke_width(core: np.ndarray) -> float:
    """Largura de traço pela identidade da fita: A ≈ w·L, P ≈ 2·L => w ≈ 2A/P.

    O perímetro é contado como nº de pixels de tinta com vizinho de fundo
    (4-conexo) — mesma ordem de grandeza do ``arcLength`` do contorno, mas sem
    depender do cv2 e sem oscilar quando a letra tem buraco.
    """
    n = int(core.sum())
    if n == 0:
        return 0.0
    p = np.pad(core, 1, mode="constant", constant_values=False)
    h, w = core.shape
    border = core & ~(
        p[0:h, 1:w + 1] & p[2:h + 2, 1:w + 1] & p[1:h + 1, 0:w] & p[1:h + 1, 2:w + 2]
    )
    perim = float(border.sum())
    if perim <= 0:
        return float(min(core.shape))
    return float(np.clip(2.0 * n / perim, 0.5, 64.0))


# --------------------------------------------------------------------------- #
# Ajuste de superfície (plano / quadrática) por canal
# --------------------------------------------------------------------------- #
def _basis(hh: int, ww: int, order: int) -> np.ndarray:
    """Base polinomial em coordenadas normalizadas [-1, 1] (condicionamento)."""
    yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
    u = 2.0 * (xx / max(ww - 1, 1)) - 1.0
    v = 2.0 * (yy / max(hh - 1, 1)) - 1.0
    one = np.ones_like(u)
    if order == 1:
        return np.stack([one, u, v], axis=-1)
    return np.stack([one, u, v, u * u, u * v, v * v], axis=-1)


def _fit_surface(phi: np.ndarray, patch: np.ndarray,
                 mask: np.ndarray) -> tuple[list[np.ndarray], list[float], float]:
    """Mínimos quadrados robustos por canal. Devolve (betas, rms por canal, cond).

    Duas iterações de rejeição de outlier (Huber grosseiro por MAD): sem isso
    a cauda de anti-aliasing que sobrou no fundo puxa o plano.
    """
    a = phi[mask]
    betas: list[np.ndarray] = []
    rmss: list[float] = []
    try:
        cond = float(np.linalg.cond(a))
    except Exception:
        cond = float("inf")
    for c in range(3):
        y = patch[..., c].astype(np.float32)[mask]
        beta, *_ = np.linalg.lstsq(a, y, rcond=None)
        r = y - a @ beta
        keep = np.ones(y.shape, dtype=bool)
        for _ in range(2):
            s = 1.4826 * float(np.median(np.abs(r - np.median(r)))) + 1e-6
            cand = np.abs(r) <= 2.5 * s
            if int(cand.sum()) < a.shape[1] + 2:
                break
            keep = cand
            beta, *_ = np.linalg.lstsq(a[keep], y[keep], rcond=None)
            r = y - a @ beta
        betas.append(beta)
        rmss.append(float(np.sqrt(float((r[keep] ** 2).mean()))) if keep.any() else 0.0)
    return betas, rmss, cond


def _eval_surface(phi: np.ndarray, betas: list[np.ndarray]) -> np.ndarray:
    return np.stack([phi @ b for b in betas], axis=-1).astype(np.float32)


# --------------------------------------------------------------------------- #
# A) Classificação do fundo
# --------------------------------------------------------------------------- #
def _periodicity(gray_filled: np.ndarray) -> float:
    """Pico da autocorrelação normalizada (Wiener–Khinchin), fora do centro.

    Foto natural fica em 0,05–0,18; xadrez/listra/halftone dá 0,35–0,9.
    """
    hh, ww = gray_filled.shape
    if hh < 8 or ww < 8:
        return 0.0
    # Passa-alta antes da autocorrelação: sem isso qualquer imagem suave dá
    # correlação ~0,99 nos lags pequenos (a energia está toda em baixa
    # frequência) e o teste não separa nada. O que interessa é se a *textura*
    # se repete, não se o fundo varia devagar.
    low = _box_blur(gray_filled, 9)
    z = gray_filled - low
    z = z - z.mean()
    power = np.abs(np.fft.rfft2(z)) ** 2
    ac = np.fft.irfft2(power, s=z.shape)
    denom = float(ac[0, 0])
    if denom <= 1e-9:
        return 0.0
    ac = ac / denom
    lag = ac.copy()
    lag[:4, :4] = 0.0
    return float(lag[: hh // 2, : ww // 2].max())


def _two_color_split(lab: np.ndarray, mask: np.ndarray) -> bool:
    """k-means k=2 no Lab: True se a caixa tem **dois fundos chapados** (MIXED).

    O caso real é a caixa que cai metade sobre uma faixa de cor chapada e
    metade sobre a foto. Não basta achar dois grupos distantes — qualquer foto
    ou degradê tem isso. O que caracteriza o caso é **um dos grupos ser
    chapado**: medido, a faixa dá dispersão interna ~2 ΔE, enquanto num
    degradê radial os dois grupos ficam em ~8 e numa foto em ~32.
    """
    pts = lab[mask].reshape(-1, 3)
    if pts.shape[0] < 100:
        return False
    lum = pts[:, 0]
    c0 = pts[lum <= np.percentile(lum, 15)].mean(axis=0)
    c1 = pts[lum >= np.percentile(lum, 85)].mean(axis=0)
    g0 = np.zeros(pts.shape[0], dtype=bool)
    for _ in range(8):
        d0 = np.linalg.norm(pts - c0, axis=1)
        d1 = np.linalg.norm(pts - c1, axis=1)
        g0 = d0 <= d1
        if not g0.any() or g0.all():
            return False
        c0, c1 = pts[g0].mean(axis=0), pts[~g0].mean(axis=0)
    share = float(g0.mean())
    sep = float(np.linalg.norm(c0 - c1))
    flat = min(float(np.linalg.norm(pts[g0] - c0, axis=1).mean()),
               float(np.linalg.norm(pts[~g0] - c1, axis=1).mean()))
    return bool(sep >= DELTA_E_DISTINCT and 0.25 <= share <= 0.75
                and flat <= FLAT_CLUSTER_SPREAD)


def _classify(patch: np.ndarray, bgm: np.ndarray, sig_n: float,
              notes: list[str]) -> tuple[BackgroundKind, float, list[np.ndarray] | None]:
    """Árvore de decisão do item A. Devolve (kind, resíduo linear, betas)."""
    hh, ww = patch.shape[:2]
    if hh * ww < MIN_REGION_AREA or int(bgm.sum()) < 200:
        notes.append("caixa pequena demais para classificar: tratada como mista")
        return BackgroundKind.MIXED, 99.0, None

    t_solid = max(1.5, NOISE_MULT_SOLID * sig_n)
    t_ramp = max(3.0, NOISE_MULT_RAMP * sig_n)
    t_grad = max(3.0, NOISE_MULT_GRAD * sig_n)

    phi1 = _basis(hh, ww, 1)
    betas1, rms1, _ = _fit_surface(phi1, patch, bgm)
    r_lin = max(rms1)
    ramp = max(float(np.ptp(phi1 @ b)) for b in betas1)

    gray = _gray(patch)
    edge = _edge_fraction(gray, bgm)

    if r_lin <= t_solid and ramp <= t_ramp:
        return BackgroundKind.SOLID, r_lin, betas1
    if r_lin <= t_solid:
        return BackgroundKind.GRADIENT, r_lin, betas1

    # Degradê com banding de 8 bits: resíduo médio, imagem lisa e sem período.
    filled = np.where(bgm, gray, (phi1 @ betas1[1]))
    per = _periodicity(filled)
    if 2.0 <= r_lin <= 4.0 and edge < 0.005 and per < 0.15:
        notes.append("degradê com banding de 8 bits")
        return BackgroundKind.GRADIENT, r_lin, betas1

    # Vale tentar a base quadrática (cobre radial, porque u²+v² está no span)
    # quando o resíduo linear ainda é pequeno OU quando a região é lisa — um
    # degradê radial forte tem resíduo linear alto e mesmo assim é analítico.
    if (r_lin <= RESID_QUAD_MAX or edge < 0.01) and int(bgm.sum()) >= 200:
        phi2 = _basis(hh, ww, 2)
        betas2, rms2, cond2 = _fit_surface(phi2, patch, bgm)
        if max(rms2) <= t_grad and cond2 <= LSQ_COND_MAX:
            return BackgroundKind.GRADIENT, float(max(rms2)), betas2

    # Textura: padrão periódico primeiro (xadrez, listra, halftone, malha),
    # depois duas cores chapadas, e o resto é foto.
    if per >= PERIOD_MIN and edge >= EDGE_MIN:
        return BackgroundKind.PATTERN, r_lin, None
    if _two_color_split(_rgb_to_lab(patch), bgm):
        notes.append("duas cores de fundo distintas na caixa")
        return BackgroundKind.MIXED, r_lin, None
    return BackgroundKind.PHOTO, r_lin, None


# --------------------------------------------------------------------------- #
# Modelo da região (A + B + C reunidos)
# --------------------------------------------------------------------------- #
@dataclass
class RegionModel:
    """Tudo o que sabemos sobre uma caixa: fundo, tinta e como apagá-la.

    ``background`` já é o preenchimento pronto para a caixa inteira; ``erase``
    diz quais pixels dela realmente devem ser trocados. Quem escreve é só o
    ``_commit``.
    """

    box: Box
    kind: BackgroundKind
    patch: np.ndarray                       # uint8 (hh, ww, 3), recorte original
    background: np.ndarray                  # uint8 (hh, ww, 3), fundo reconstruído
    alpha: np.ndarray                       # float32 0..1, cobertura de tinta
    core: np.ndarray                        # bool, núcleo dos glifos
    halo: np.ndarray                        # bool, glifo + anti-aliasing
    erase: np.ndarray                       # bool, o que será sobrescrito
    stroke_width: float = 0.0
    noise_sigma: float = 0.0
    residual: float = 0.0
    ink_fraction: float = 0.0
    text_color: tuple[int, int, int] | None = None
    background_color: tuple[int, int, int] | None = None
    technique: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "box": self.box.to_dict(),
            "kind": self.kind.value,
            "technique": self.technique,
            "stroke_width": round(self.stroke_width, 2),
            "noise_sigma": round(self.noise_sigma, 2),
            "residual": round(self.residual, 2),
            "ink_fraction": round(self.ink_fraction, 4),
            "text_color": list(self.text_color) if self.text_color else None,
            "background_color": list(self.background_color) if self.background_color else None,
            "warnings": list(self.warnings),
        }


def _as_box(box: Any, img_w: int, img_h: int) -> Box:
    b = box if isinstance(box, Box) else Box.from_any(box, img_w, img_h)
    return b.clamp(img_w, img_h)


def _presegment(patch: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Passada 1, barata: acha "o que certamente não é glifo" (item A.0).

    Duas correções em relação à versão ingênua (mediana do anel + ΔE > 15):

    * o fundo provisório é um **plano** ajustado no anel, não uma cor só. Num
      degradê forte a mediana do anel fica a 40 ΔE do outro canto da caixa e
      *tudo* seria classificado como tinta;
    * o limiar sobe com a dispersão do próprio anel. Em foto/textura o anel já
      varia 25 ΔE sozinho, então um limiar fixo marcaria a textura inteira
      como glifo.
    """
    hh, ww = patch.shape[:2]
    k = int(np.clip(round(0.08 * hh), 2, 6))
    ring = _ring_mask(hh, ww, k)
    lab = _rgb_to_lab(patch)

    if int(ring.sum()) >= 30 and hh >= 4 and ww >= 4:
        phi = _basis(hh, ww, 1)
        betas, _rms, cond = _fit_surface(phi, patch, ring)
        bg0 = _eval_surface(phi, betas) if cond <= LSQ_COND_MAX else None
    else:
        bg0 = None
    if bg0 is None:
        med = np.median(patch[ring].reshape(-1, 3), axis=0)
        bg0 = np.broadcast_to(med.astype(np.float32), (hh, ww, 3))

    d0 = np.linalg.norm(lab - _rgb_to_lab(bg0), axis=2)
    ring_d = d0[ring]
    spread = float(np.median(ring_d) + 3.0 * 1.4826 * np.median(np.abs(ring_d - np.median(ring_d))))
    t0 = max(15.0, spread)
    ink0 = d0 > t0
    bgm = ~_dilate(ink0, 3)
    return ring, ink0, bgm


def _background_model(patch: np.ndarray, kind: BackgroundKind,
                      betas: list[np.ndarray] | None, bgm: np.ndarray,
                      ink0: np.ndarray) -> np.ndarray:
    """Fundo estimado **por pixel** — nunca uma cor média para a caixa toda."""
    hh, ww = patch.shape[:2]
    if kind is BackgroundKind.SOLID:
        src = bgm if int(bgm.sum()) >= 20 else np.ones((hh, ww), dtype=bool)
        color = np.median(patch[src].reshape(-1, 3), axis=0)
        return np.broadcast_to(color.astype(np.float32), (hh, ww, 3)).copy()
    if kind is BackgroundKind.GRADIENT and betas is not None:
        order = 1 if len(betas[0]) == 3 else 2
        return _eval_surface(_basis(hh, ww, order), betas)
    # Foto / padrão / misto: fundo morfológico ("rolling ball"). Um close/open
    # com kernel maior que o traço apaga o texto e preserva a foto — é o único
    # jeito barato de segmentar texto sobre foto sem modelo.
    if float(ink0.mean()) < 0.005:
        # A pré-segmentação não achou tinta (fundo muito texturizado). Sem uma
        # medida de traço, estime pela altura da caixa: corpo de texto costuma
        # ter haste ≈ 6% da altura da linha.
        sw0 = float(np.clip(0.06 * hh, 1.0, 12.0))
    else:
        sw0 = max(1.0, _stroke_width(ink0))
    ksz = int(2 * np.ceil(1.6 * sw0) + 1)
    ksz = int(np.clip(ksz, 3, max(3, min(hh, ww) // 2 * 2 + 1)))
    lum = _gray(patch)
    if ink0.any() and (~ink0).any():
        dark_text = lum[ink0].mean() < lum[~ink0].mean()
    else:
        dark_text = True
    p = patch.astype(np.float32)
    if dark_text:  # texto escuro: close (dilata e depois erode) engole o traço
        est = _min_filter(_max_filter(p, ksz), ksz)
    else:
        est = _max_filter(_min_filter(p, ksz), ksz)
    return est.astype(np.float32)


def _clean_components(core: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Tira sujeira e vizinhos colados na borda, mas preserva pingo de 'i'."""
    hh, ww = core.shape
    lbl, stats = _components(core)
    if not stats:
        return core
    a_min = max(6, int(0.00025 * hh * ww))
    comps = [s for s in stats if s["area"] >= a_min]
    if not comps:
        return core
    heights = np.array([s["h"] for s in comps], dtype=np.float32)
    tall = heights[heights >= 0.5 * heights.max()]
    h_ref = float(np.median(tall)) if tall.size else float(heights.max())

    keep: list[int] = []
    small: list[dict[str, int]] = []
    for s in comps:
        in_ring = float(ring[s["y"]:s["y"] + s["h"], s["x"]:s["x"] + s["w"]].mean())
        if in_ring > 0.70:      # colado na borda em toda a extensão: é vizinho
            continue
        if s["h"] >= 0.25 * h_ref:
            keep.append(s["label"])
        else:
            small.append(s)

    kept = [s for s in comps if s["label"] in keep]
    for s in small:            # regra do pingo do "i" / acento
        for t in kept:
            ov = min(s["x"] + s["w"], t["x"] + t["w"]) - max(s["x"], t["x"])
            if ov <= 0.40 * s["w"]:
                continue
            gap = t["y"] - (s["y"] + s["h"])
            if -0.2 * h_ref <= gap <= 1.2 * h_ref:
                keep.append(s["label"])
                break
    if not keep:
        return core
    return np.isin(lbl, keep)


def _segment(patch: np.ndarray, bg_est: np.ndarray, sig_n: float,
             ring: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """Item B: alpha suave dos glifos a partir da distância ao fundo modelado."""
    lab_p = _rgb_to_lab(patch)
    lab_b = _rgb_to_lab(bg_est)
    d = np.linalg.norm(lab_p - lab_b, axis=2)

    scale = max(float(np.percentile(d, 99.5)), 1e-6)
    d8 = np.clip(d / scale * 255.0, 0, 255).astype(np.uint8)
    t = _otsu(d8) / 255.0 * scale
    frac = float((d > t).mean())
    if not (INK_FRAC_RANGE[0] <= frac <= INK_FRAC_RANGE[1]):
        # Otsu degenerou (caixa vazia, ou ele inverteu e pegou o fundo).
        t = max(12.0, 4.0 * sig_n * 1.7)

    t_lo, t_hi = 0.35 * t, 1.15 * t
    alpha = np.clip((d - t_lo) / max(t_hi - t_lo, 1e-6), 0.0, 1.0).astype(np.float32)
    core = alpha >= ALPHA_CORE
    halo = alpha > ALPHA_HALO
    core = _clean_components(core, ring)
    halo = halo & _dilate(core, 3)       # halo órfão (sem núcleo) é ruído
    sw = _stroke_width(core) if core.any() else _stroke_width(halo)
    return alpha, core, halo, float(sw)


def _solid_color(patch: np.ndarray, far: np.ndarray) -> tuple[np.ndarray, float]:
    """Cor exata do fundo pela **moda**, medida só longe da tinta.

    Média e mediana sobre "tudo que não é tinta" incluem a cauda de
    anti-aliasing e puxam a cor: numa haste de 3 px, 2/3 dos pixels de tinta
    são borda. A moda ignora essa cauda inteira; a mediana entra só quando o
    ruído espalha demais os valores para haver moda estável.
    """
    px = patch[far].reshape(-1, 3).astype(np.uint32)
    if px.shape[0] == 0:
        return np.array([0, 0, 0], dtype=np.float32), 0.0
    key = (px[:, 0] << 16) | (px[:, 1] << 8) | px[:, 2]
    vals, counts = np.unique(key, return_counts=True)
    top = int(vals[int(np.argmax(counts))])
    share = float(counts.max()) / float(len(key))
    if share >= 0.30:
        color = np.array([(top >> 16) & 255, (top >> 8) & 255, top & 255], dtype=np.float32)
    else:
        color = np.median(px.astype(np.float32), axis=0)
    dev = px.astype(np.float32) - np.median(px.astype(np.float32), axis=0)
    sigma_bg = float(np.mean(1.4826 * np.median(np.abs(dev), axis=0)))
    return color, sigma_bg


def _inpaint_fill(rgb_ctx: np.ndarray, mask_ctx: np.ndarray, radius: int) -> np.ndarray:
    """Inpaint dentro de ``mask_ctx``; pixels conhecidos voltam byte a byte.

    TELEA e não Navier–Stokes: a máscara de texto é fina, longa e ramificada.
    O NS lê cada haste como uma estrutura e a *prolonga*, deixando riscos na
    direção das letras; o TELEA é uma interpolação ponderada da vizinhança e
    atravessa buraco estreito sem inventar estrutura.
    """
    if not mask_ctx.any():
        return rgb_ctx.copy()
    if cv2 is not None:
        bgr = cv2.cvtColor(np.ascontiguousarray(rgb_ctx), cv2.COLOR_RGB2BGR)
        m = np.ascontiguousarray((mask_ctx.astype(np.uint8) * 255))
        res = cv2.inpaint(bgr, m, float(max(1, radius)), cv2.INPAINT_TELEA)
        out = cv2.cvtColor(res, cv2.COLOR_BGR2RGB)
    else:
        out = _inpaint_numpy(rgb_ctx.astype(np.float32), mask_ctx)
        out = np.clip(np.rint(out), 0, 255).astype(np.uint8)
    return np.where(mask_ctx[..., None], out, rgb_ctx).astype(np.uint8)


def _inpaint_numpy(rgb: np.ndarray, mask: np.ndarray, levels: int = 4,
                   iters: tuple[int, ...] = (120, 80, 60, 40)) -> np.ndarray:
    """Difusão de Laplace multi-escala (Jacobi) — fallback sem cv2.

    Coarse-to-fine porque Jacobi sozinho leva O(n²) iterações para atravessar
    um buraco; com 4 níveis, ~300 iterações resolvem uma máscara de texto.
    Qualidade: comparável ao TELEA em fundo liso, mais suave (pior) em textura.
    """
    pyr_i: list[np.ndarray] = [rgb.astype(np.float32)]
    pyr_m: list[np.ndarray] = [mask.astype(bool)]

    def down(a: np.ndarray) -> np.ndarray:
        return (a[0:-1:2, 0:-1:2] + a[1::2, 0:-1:2] + a[0:-1:2, 1::2] + a[1::2, 1::2]) / 4.0

    def downm(m: np.ndarray) -> np.ndarray:
        return m[0:-1:2, 0:-1:2] & m[1::2, 0:-1:2] & m[0:-1:2, 1::2] & m[1::2, 1::2]

    def up(a: np.ndarray, shape: tuple[int, ...]) -> np.ndarray:
        o = np.repeat(np.repeat(a, 2, axis=0), 2, axis=1)
        # Nível ímpar: 2*floor(n/2) fica 1 px curto. Replica a borda em vez de
        # deixar o índice booleano estourar.
        dy, dx = shape[0] - o.shape[0], shape[1] - o.shape[1]
        if dy > 0 or dx > 0:
            pad = [(0, max(0, dy)), (0, max(0, dx))] + [(0, 0)] * (o.ndim - 2)
            o = np.pad(o, pad, mode="edge")
        return o[: shape[0], : shape[1]]

    while len(pyr_i) < levels and min(pyr_i[-1].shape[:2]) > 16:
        pyr_i.append(down(pyr_i[-1]))
        pyr_m.append(downm(pyr_m[-1]))

    cur: np.ndarray | None = None
    for lv in range(len(pyr_i) - 1, -1, -1):
        img_l, m_l = pyr_i[lv].copy(), pyr_m[lv]
        known = ~m_l
        if not m_l.any():
            cur = img_l
            continue
        if cur is None:
            for c in range(3):
                seed = float(img_l[..., c][known].mean()) if known.any() else 128.0
                img_l[..., c][m_l] = seed
        else:
            img_l[m_l] = up(cur, img_l.shape)[m_l]
        n_it = iters[min(lv, len(iters) - 1)]
        for _ in range(n_it):
            p = np.pad(img_l, ((1, 1), (1, 1), (0, 0)), mode="edge")
            avg = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) * 0.25
            img_l = np.where(m_l[..., None], avg, img_l)
        img_l[known] = pyr_i[lv][known]     # conhecido nunca é reescrito
        cur = img_l
    return np.clip(cur if cur is not None else rgb, 0, 255)


def _build_fill(rgb: np.ndarray, box: Box, model_kind: BackgroundKind,
                patch: np.ndarray, erase: np.ndarray, halo: np.ndarray,
                sw: float, sig_n: float, warnings: list[str],
                betas: list[np.ndarray] | None) -> tuple[np.ndarray, str, tuple[int, int, int] | None, float]:
    """Item C: produz o preenchimento da caixa inteira e diz qual técnica usou."""
    hh, ww = patch.shape[:2]
    d = _erase_dilate(sw)
    far = ~_dilate(halo, d + 2)
    if int(far.sum()) < 20:
        far = ~halo
    rng = _rng_for(box)

    if model_kind is BackgroundKind.SOLID:
        color, sigma_bg = _solid_color(patch, far)
        fill = np.broadcast_to(color, (hh, ww, 3)).astype(np.float32).copy()
        if sigma_bg > NOISE_REINJECT_MIN:
            # Sem isso a região reconstruída fica "limpa demais" e o retângulo
            # aparece contra o grão do JPEG ao redor.
            fill = fill + rng.normal(0.0, sigma_bg, fill.shape)
        out = np.clip(np.rint(fill), 0, 255).astype(np.uint8)
        return out, "solid", tuple(int(v) for v in np.rint(color)), sigma_bg  # type: ignore[return-value]

    if model_kind is BackgroundKind.GRADIENT:
        n_bg = int(far.sum())
        ok = n_bg >= LSQ_MIN_BG_PIXELS and n_bg / float(hh * ww) >= LSQ_MIN_BG_FRAC
        if ok:
            phi1 = _basis(hh, ww, 1)
            b1, r1, cond1 = _fit_surface(phi1, patch, far)
            best, resid, phi = b1, max(r1), phi1
            if cond1 > LSQ_COND_MAX:
                ok = False
                warnings.append("degradê mal condicionado (fundo visível é uma faixa fina)")
            elif resid > max(LSQ_RESID_ACCEPT, NOISE_MULT_GRAD * sig_n) and n_bg >= 200:
                phi2 = _basis(hh, ww, 2)
                b2, r2, cond2 = _fit_surface(phi2, patch, far)
                if cond2 <= LSQ_COND_MAX and max(r2) < resid:
                    best, resid, phi = b2, max(r2), phi2
            if ok and resid <= max(LSQ_RESID_ACCEPT, NOISE_MULT_GRAD * sig_n) * 2.0:
                fill = _eval_surface(phi, best)
                # Dither de ±0,5 nível: sem ele o banding reconstruído cai em
                # posição diferente do original e aparece uma costura.
                fill = fill + rng.uniform(-0.5, 0.5, fill.shape)
                out = np.clip(np.rint(fill), 0, 255).astype(np.uint8)
                return out, "gradient", None, resid
            ok = False
        if not ok:
            warnings.append("degradê não convergiu na caixa: usando inpaint")

    # Foto / padrão / misto / degradê recusado -> inpaint com contexto.
    margin = _inpaint_context(sw)
    h_img, w_img = rgb.shape[:2]
    ctx = Box(box.x - margin, box.y - margin,
              box.w + 2 * margin, box.h + 2 * margin).clamp(w_img, h_img)
    sub = rgb[ctx.y:ctx.y1, ctx.x:ctx.x1].copy()
    mctx = np.zeros(sub.shape[:2], dtype=bool)
    oy, ox = box.y - ctx.y, box.x - ctx.x
    mctx[oy:oy + hh, ox:ox + ww] = erase
    filled = _inpaint_fill(sub, mctx, _inpaint_radius(sw))
    out = filled[oy:oy + hh, ox:ox + ww].astype(np.float32)
    if sig_n > 1.0:
        # Devolve um pouco do grão: inpaint entrega região suave demais e o
        # retângulo liso denuncia a edição em foto com ruído.
        noise = np.where(erase[..., None], rng.normal(0.0, sig_n, out.shape), 0.0)
        out = out + noise
    return np.clip(np.rint(out), 0, 255).astype(np.uint8), "inpaint", None, 0.0


def analyze_region(img: Image.Image, box: Any, *,
                   kind: BackgroundKind | str | None = None) -> RegionModel:
    """Roda A + B + C numa caixa e devolve o modelo completo, sem escrever nada.

    ``kind`` força a classificação (útil quando a análise de visão já sabe que o
    fundo é chapado, ou quando o usuário mandou uma técnica na receita).
    """
    rgb, _ = _split_rgb(img)
    h_img, w_img = rgb.shape[:2]
    b = _as_box(box, w_img, h_img)
    warnings: list[str] = []
    if b.area <= 0:
        raise ValueError(
            f"caixa vazia depois do clamp: {b.to_dict()}\n"
            "  Verifique as coordenadas da caixa na receita (podem estar fora da imagem)."
        )

    patch = rgb[b.y:b.y1, b.x:b.x1].copy()
    hh, ww = patch.shape[:2]
    forced: BackgroundKind | None = None
    if kind is not None:
        forced = kind if isinstance(kind, BackgroundKind) else BackgroundKind(str(kind).lower())

    if hh < 3 or ww < 3:
        # Faixa de 1–2 px: não há o que segmentar, apaga tudo por difusão.
        all_true = np.ones((hh, ww), dtype=bool)
        fill, tech, bgc, _ = _build_fill(rgb, b, BackgroundKind.PHOTO, patch,
                                         all_true, all_true, 1.0, 0.0, warnings, None)
        return RegionModel(box=b, kind=forced or BackgroundKind.MIXED, patch=patch,
                           background=fill, alpha=all_true.astype(np.float32),
                           core=all_true, halo=all_true, erase=all_true,
                           stroke_width=1.0, technique=tech, background_color=bgc,
                           warnings=warnings + ["caixa com menos de 3 px: apagada inteira"])

    ring, ink0, bgm = _presegment(patch)
    gray = _gray(patch)
    sig_n = _noise_sigma(gray, bgm if bgm.any() else None)

    if float(bgm.mean()) < 0.20:
        warnings.append("caixa quase toda coberta de tinta: tratada como mista")
        auto_kind, residual, betas = BackgroundKind.MIXED, 99.0, None
    else:
        auto_kind, residual, betas = _classify(patch, bgm, sig_n, warnings)
    kind_final = forced or auto_kind

    if forced is BackgroundKind.GRADIENT and betas is None:
        phi1 = _basis(hh, ww, 1)
        betas, _r, _c = _fit_surface(phi1, patch, bgm if bgm.any() else np.ones((hh, ww), bool))

    bg_est = _background_model(patch, kind_final, betas, bgm, ink0)
    alpha, core, halo, sw = _segment(patch, bg_est, sig_n, ring)

    ink_fraction = float(halo.mean())
    text_color: tuple[int, int, int] | None = None
    core_e = _erode(core, 1)
    if int(core_e.sum()) >= 40:
        med = np.median(patch[core_e].reshape(-1, 3), axis=0)
        text_color = tuple(int(v) for v in np.rint(med))  # type: ignore[assignment]
    elif core.any():
        med = np.median(patch[core].reshape(-1, 3), axis=0)
        text_color = tuple(int(v) for v in np.rint(med))  # type: ignore[assignment]

    d = _erase_dilate(sw if sw > 0 else 2.0)
    erase = _dilate(halo, d) if halo.any() else np.zeros((hh, ww), dtype=bool)
    if erase.any() and _ring_mask(hh, ww, 1)[erase].any():
        warnings.append(
            "a tinta encosta na borda da caixa: pode sobrar 1 px de halo "
            "(aumente a caixa em 2-3 px se aparecer)"
        )

    fill, tech, bg_color, _sig_bg = _build_fill(rgb, b, kind_final, patch, erase, halo,
                                                sw if sw > 0 else 2.0, sig_n, warnings, betas)

    return RegionModel(
        box=b, kind=kind_final, patch=patch, background=fill, alpha=alpha,
        core=core, halo=halo, erase=erase, stroke_width=sw, noise_sigma=sig_n,
        residual=residual, ink_fraction=ink_fraction, text_color=text_color,
        background_color=bg_color, technique=tech, warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# Escrita — a ÚNICA função que altera pixels
# --------------------------------------------------------------------------- #
def _commit(rgb: np.ndarray, box: Box, fill: np.ndarray,
            mask: np.ndarray | None, feather: int = 0) -> np.ndarray:
    """Escreve ``fill`` dentro de ``box``, só onde ``mask`` é verdadeiro.

    O slice já confina a escrita: não existe nenhuma outra atribuição de pixel
    neste módulo. Onde a máscara é falsa os bytes originais são *copiados*, não
    recompostos — é isso que zera o drift também dentro da caixa e faz o
    resultado não parecer "um retângulo mais limpo".
    """
    out = rgb.copy()
    sub = out[box.y:box.y1, box.x:box.x1]
    if mask is None:
        sub[:] = np.clip(fill, 0, 255).astype(np.uint8)
        return out
    if not mask.any():
        return out
    if feather and feather > 0:
        # Dilata e borra: a rampa cai *fora* da máscara de tinta, onde o
        # preenchimento já é o próprio fundo estimado. Assim a transição some
        # em vez de virar um degrau de 1 px.
        soft = _box_blur(_dilate(mask, int(feather)).astype(np.float32), 2 * int(feather) + 1)
        a = np.clip(np.maximum(soft, mask.astype(np.float32)), 0.0, 1.0)[..., None]
        blended = a * np.clip(fill, 0, 255).astype(np.float32) + (1.0 - a) * sub.astype(np.float32)
        sub[:] = np.rint(blended).astype(np.uint8)
        return out
    sub[:] = np.where(mask[..., None], np.clip(fill, 0, 255).astype(np.uint8), sub)
    return out


# --------------------------------------------------------------------------- #
# API pública
# --------------------------------------------------------------------------- #
def classify_region(img: Image.Image, box: Any) -> BackgroundKind:
    """Que tipo de fundo existe dentro da caixa.

    ``SOLID``/``GRADIENT`` significam que dá para apagar texto de forma
    analítica e exata; ``PHOTO``/``PATTERN``/``MIXED`` exigem inpaint (ou IA
    com composição protegida).
    """
    rgb, _ = _split_rgb(img)
    h_img, w_img = rgb.shape[:2]
    b = _as_box(box, w_img, h_img)
    if b.area < MIN_REGION_AREA or b.w < 3 or b.h < 3:
        return BackgroundKind.MIXED
    patch = rgb[b.y:b.y1, b.x:b.x1]
    _ring, _ink0, bgm = _presegment(patch)
    if float(bgm.mean()) < 0.20:
        return BackgroundKind.MIXED
    sig_n = _noise_sigma(_gray(patch), bgm)
    kind, _resid, _betas = _classify(patch, bgm, sig_n, [])
    return kind


def reconstruct_solid(img: Image.Image, box: Any) -> Image.Image:
    """Preenche a caixa inteira com a cor chapada do fundo.

    A cor sai da moda dos pixels comprovadamente longe da tinta (ver
    ``_solid_color``), não da média — média inclui o anti-aliasing e some com
    a cor real. Se o fundo tem grão, o grão é reinjetado com semente derivada
    da caixa (mesma entrada => mesmo arquivo).
    """
    rgb, alpha_ch = _split_rgb(img)
    model = analyze_region(img, box, kind=BackgroundKind.SOLID)
    return _merge_rgb(_commit(rgb, model.box, model.background, None), alpha_ch)


def reconstruct_gradient(img: Image.Image, box: Any) -> Image.Image:
    """Preenche a caixa com o degradê ajustado por mínimos quadrados robustos.

    Ajusta um plano em (x, y) por canal usando **só** os pixels de fundo; se
    o resíduo continuar alto tenta a base quadrática (que cobre radial). Se
    nem isso convergir, degrada para inpaint — nesse caso apenas os glifos são
    trocados, porque encher a caixa com um plano ruim seria pior que o texto.
    """
    rgb, alpha_ch = _split_rgb(img)
    model = analyze_region(img, box, kind=BackgroundKind.GRADIENT)
    # No caminho degradado (technique == "inpaint") o preenchimento já é igual
    # ao original fora da máscara, então colar a caixa inteira é seguro.
    return _merge_rgb(_commit(rgb, model.box, model.background, None), alpha_ch)


def inpaint_telea(img: Image.Image, mask: Any, radius: int = 3, *,
                  dilate: int | None = None) -> Image.Image:
    """Reconstrói a região marcada em ``mask`` por Fast Marching (TELEA).

    ``mask``: PIL "L"/"1" do tamanho da imagem ou array booleano — 255/True =
    região a reconstruir. A máscara é **dilatada** antes (padrão: metade do
    raio, no mínimo 1 px) porque o anti-aliasing dos glifos vaza alguns pixels
    além da silhueta e, sem essa folga, sobra um fantasma cinza do contorno.

    Sem ``cv2`` cai para difusão multi-escala em numpy: funciona, é mais suave
    em textura, e a diferença aparece em ``RegionModel.warnings`` de quem usa
    ``erase_region``.
    """
    rgb, alpha_ch = _split_rgb(img)
    h_img, w_img = rgb.shape[:2]
    m = _mask_to_bool(mask, w_img, h_img)
    n_dil = int(dilate) if dilate is not None else int(np.clip(round(radius / 2.0), 1, 6))
    m = _dilate(m, n_dil)
    if not m.any():
        return _merge_rgb(rgb, alpha_ch)

    ys, xs = np.nonzero(m)
    margin = max(8, int(3 * radius))
    b = Box(int(xs.min()) - margin, int(ys.min()) - margin,
            int(xs.max() - xs.min()) + 1 + 2 * margin,
            int(ys.max() - ys.min()) + 1 + 2 * margin).clamp(w_img, h_img)
    sub = rgb[b.y:b.y1, b.x:b.x1].copy()
    msub = m[b.y:b.y1, b.x:b.x1]
    filled = _inpaint_fill(sub, msub, int(max(1, radius)))
    out = rgb.copy()
    region = out[b.y:b.y1, b.x:b.x1]
    region[:] = np.where(msub[..., None], filled, region)
    return _merge_rgb(out, alpha_ch)


def _mask_to_bool(mask: Any, w: int, h: int) -> np.ndarray:
    if isinstance(mask, Image.Image):
        m = mask if mask.mode in ("L", "1") else mask.convert("L")
        arr = np.array(m)
        m_bool = arr > 127 if arr.dtype != bool else arr
    elif isinstance(mask, np.ndarray):
        m_bool = mask > 127 if mask.dtype != bool else mask
        if m_bool.ndim == 3:
            m_bool = m_bool.any(axis=2)
    else:
        raise TypeError("máscara inválida: use uma imagem PIL 'L' ou um array numpy booleano")
    if m_bool.shape[:2] != (h, w):
        raise ValueError(
            f"a máscara tem {m_bool.shape[1]}x{m_bool.shape[0]} e a imagem {w}x{h}.\n"
            "  A máscara precisa ter exatamente o tamanho da imagem."
        )
    return np.ascontiguousarray(m_bool.astype(bool))


def glyph_mask(img: Image.Image, box: Any, *, dilate: int = 0) -> Image.Image:
    """Máscara "L" do tamanho da imagem com os glifos detectados na caixa.

    Serve para quem precisa da silhueta do texto (composição protegida com IA,
    depuração visual). Fora da caixa é sempre 0.
    """
    model = analyze_region(img, box)
    out = np.zeros((img.height, img.width), dtype=np.uint8)
    m = _dilate(model.erase, dilate) if dilate else model.erase
    out[model.box.y:model.box.y1, model.box.x:model.box.x1] = m.astype(np.uint8) * 255
    return Image.fromarray(out, "L")


def erase_region(img: Image.Image, box: Any, *, kind: BackgroundKind | str | None = None,
                 feather: int = 1, report: dict[str, Any] | None = None) -> Image.Image:
    """Apaga o conteúdo (texto) da caixa reconstruindo o fundo por baixo.

    Escolhe sozinho a melhor técnica: cor chapada (moda robusta), degradê
    (mínimos quadrados por canal) ou inpaint com contexto. **Nenhum pixel fora
    de ``box`` é alterado** — o contexto ao redor é lido pelo inpaint, nunca
    escrito.

    ``feather`` suaviza a transição na borda da máscara em N px (dentro da
    caixa). ``feather=0`` mantém a troca binária, que é a mais conservadora.
    Passe um dicionário em ``report`` para receber o diagnóstico (técnica,
    tipo de fundo, largura de traço, avisos).
    """
    rgb, alpha_ch = _split_rgb(img)
    model = analyze_region(img, box, kind=kind)
    if report is not None:
        report.update(model.to_dict())
        report["has_cv2"] = HAS_CV2
        if not HAS_CV2 and model.technique == "inpaint":
            report.setdefault("warnings", []).append(
                "cv2 indisponível: inpaint feito por difusão em numpy (mais suave)"
            )
    if not model.erase.any():
        if report is not None:
            report.setdefault("warnings", []).append("nenhuma tinta detectada na caixa")
        return _merge_rgb(rgb, alpha_ch)
    out = _commit(rgb, model.box, model.background, model.erase, feather=int(feather))
    return _merge_rgb(out, alpha_ch)


# --------------------------------------------------------------------------- #
# Teste de fumaça
# --------------------------------------------------------------------------- #
def _draw_demo(kind: str, w: int = 640, h: int = 220) -> tuple[Image.Image, Image.Image, Box]:
    """(imagem com texto, fundo limpo de referência, caixa do texto)."""
    from PIL import ImageDraw, ImageFont

    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    if kind == "gradient":
        base = np.stack([
            30 + 180 * xx / w + 20 * yy / h,
            60 + 90 * yy / h,
            200 - 120 * xx / w,
        ], axis=-1)
    elif kind == "solid":
        base = np.zeros((h, w, 3), dtype=np.float32)
        base[..., :] = np.array([18, 122, 205], dtype=np.float32)
    else:  # foto sintética: senoides + ruído
        base = np.stack([
            128 + 60 * np.sin(xx / 17.0) + 30 * np.cos(yy / 11.0),
            120 + 50 * np.sin((xx + yy) / 23.0),
            140 + 40 * np.cos(xx / 9.0) * np.sin(yy / 13.0),
        ], axis=-1)
        base += np.random.default_rng(7).normal(0, 3.0, base.shape)
    clean = Image.fromarray(np.clip(np.rint(base), 0, 255).astype(np.uint8), "RGB")

    img = clean.copy()
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=46)
    except TypeError:  # Pillow antigo
        font = ImageFont.load_default()
    draw.text((70, 85), "COMPRE AGORA", font=font, fill=(255, 255, 255))
    box = Box(40, 60, 560, 100)
    return img, clean, box


def _smoke_test() -> int:
    print(f"cv2 disponível: {HAS_CV2}")
    falhas = 0

    for kind in ("gradient", "solid", "photo"):
        img, clean, box = _draw_demo(kind)
        detected = classify_region(img, box)
        report: dict[str, Any] = {}
        out = erase_region(img, box, report=report)

        a = np.array(img, dtype=np.uint8)
        b = np.array(out, dtype=np.uint8)
        ref = np.array(clean, dtype=np.uint8)

        # 1) zero drift: fora da caixa tem que ser idêntico byte a byte
        mask_out = np.ones(a.shape[:2], dtype=bool)
        mask_out[box.y:box.y1, box.x:box.x1] = False
        drift = int(np.count_nonzero(np.any(a != b, axis=2) & mask_out))

        # 2) dentro da caixa: o resíduo contra o fundo limpo tem que ser baixo
        inside = (slice(box.y, box.y1), slice(box.x, box.x1))
        resid = float(np.abs(b[inside].astype(np.int16) - ref[inside].astype(np.int16)).mean())
        antes = float(np.abs(a[inside].astype(np.int16) - ref[inside].astype(np.int16)).mean())
        mudou = int(np.count_nonzero(np.any(a != b, axis=2)))

        limite = 2.0 if kind in ("solid", "gradient") else 12.0
        ok = drift == 0 and resid < limite and 0 < mudou <= 0.9 * box.area
        falhas += 0 if ok else 1
        print(
            f"[{kind:8s}] classificado={detected.value:8s} técnica={report.get('technique',''):8s} "
            f"drift_fora={drift} resíduo={resid:5.2f} (antes {antes:5.2f}) "
            f"pixels_mudados={mudou} sw={report.get('stroke_width')} -> {'OK' if ok else 'FALHOU'}"
        )
        if report.get("warnings"):
            print(f"           avisos: {report['warnings']}")

    # inpaint_telea direto, com máscara explícita
    img, clean, box = _draw_demo("photo")
    m = np.array(glyph_mask(img, box))
    out = inpaint_telea(img, Image.fromarray(m, "L"), radius=4)
    a, b = np.array(img), np.array(out)
    allowed = _dilate(m > 127, 2)
    drift = int(np.count_nonzero(np.any(a != b, axis=2) & ~allowed))
    print(f"[telea   ] drift fora da máscara dilatada={drift} -> {'OK' if drift == 0 else 'FALHOU'}")
    falhas += 0 if drift == 0 else 1

    # idempotência da semente: rodar duas vezes dá o mesmo arquivo
    i1 = np.array(erase_region(*_draw_demo("solid")[0:1], box=box))
    i2 = np.array(erase_region(*_draw_demo("solid")[0:1], box=box))
    same = bool(np.array_equal(i1, i2))
    print(f"[semente ] duas execuções idênticas={same} -> {'OK' if same else 'FALHOU'}")
    falhas += 0 if same else 1

    print("TUDO OK" if falhas == 0 else f"{falhas} verificação(ões) falharam")
    return 0 if falhas == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_smoke_test())
