"""Reenquadramento: levar um criativo de um formato para outro sem distorcer.

Este módulo implementa o item **G** do projeto técnico. A regra que manda em
tudo aqui é a mesma da trilha determinística:

    **o conteúdo original nunca é esticado.** Ele é reescalado por um único
    fator uniforme (Lanczos) e colado inteiro; o que muda de formato é a
    *moldura*, não a peça.

Ir de 9:16 para 16:9 muda a razão em 3,16×: o original ocupa apenas
``(9/16)/(16/9) = 81/256 = 31,6%`` da largura final. Ou seja, dois terços da
tela de destino são área **nova**. Como preenchê-la é a decisão inteira do
módulo, e por isso existem quatro modos:

``pad`` (padrão)
    Canvas do tamanho alvo, original centralizado por ``resize_contain`` e as
    sobras preenchidas por fundo borrado / espelhado / cor chapada.
    Determinístico, gratuito, instantâneo. Zero risco.

``crop``
    Recorta o alvo de dentro do original, escolhendo o deslocamento que
    preserva o máximo de área segura e de texto. Não inventa pixel nenhum —
    mas corta, e o resultado diz exatamente o que foi cortado.

``outpaint``
    Estende a cena com ``aigen.outpaint`` e **recola o original por cima** com
    :func:`protect.protected_composite`. O conteúdo original fica intacto por
    construção, não por sorte: a checagem de drift roda em memória e o número
    vai para ``info["drift_pixels"]``.

``relayout``
    O modo "responsivo" de verdade, e o único que reorganiza a peça: apaga os
    blocos de texto do original (``textedit.remove_text``), estende só o
    **fundo** para o novo formato e **redesenha** o texto nas posições do novo
    enquadramento, com o corpo de fonte reescalado. Apagar o texto antes do
    outpaint também elimina o pior modo de falha dos modelos de imagem —
    texto ilegível gerado — porque o modelo nunca vê texto para continuar.

Sem ``OPENAI_API_KEY`` os modos ``pad``, ``crop`` e ``relayout`` continuam
funcionando 100% offline; ``outpaint`` degrada para ``pad`` com um aviso claro
em vez de explodir no meio de um lote de 30 imagens.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Iterable, Sequence

import numpy as np
from PIL import Image, ImageFilter

from . import imageio_util as _io
from . import protect as _protect
from .models import (
    AspectSpec,
    Box,
    CreativeAnalysis,
    FontSpec,
    TextBlock,
    TextRole,
    parse_color,
)

try:  # opcional: só as verificações de qualidade do outpaint dependem dele
    import cv2  # type: ignore
except Exception:  # pragma: no cover - ambiente sem opencv
    cv2 = None  # type: ignore[assignment]

HAS_CV2: bool = cv2 is not None

__all__ = [
    "plan_placement",
    "reframe",
    # extras úteis para pipeline.py / cli.py / webui.py
    "resolve_target",
    "generated_bands",
    "build_background",
    "pad_canvas",
    "plan_crop",
    "plan_relayout",
    "BlockPlan",
    "MODES",
    "FILLS",
    "POLICY_KEEP",
    "HAS_CV2",
]

log = logging.getLogger("s7editor.reframe")

MODES: tuple[str, ...] = ("pad", "crop", "outpaint", "relayout")
FILLS: tuple[str, ...] = ("blur", "mirror", "color", "white", "black")

# --- constantes do preenchimento borrado (G.1, passo 3) --------------------- #
BLUR_SIGMA_FRAC = 0.03      # σ = 3% da maior dimensão -> 32 px em 1920
BLUR_DIM = 0.85             # escurece: o fundo não pode competir com a peça
BLUR_DESAT = 0.30           # dessatura 30% pelo mesmo motivo

# --- verificação do outpaint (G.5) ------------------------------------------ #
SEAM_DELTA_MAX = 8.0        # ΔE máximo aceitável na costura, depois da correção
SEAM_RAMP_FRAC = 0.15       # a correção decai em 15% da faixa gerada
SEAM_PROBE = 4              # colunas/linhas amostradas de cada lado da costura
HIST_BHATTACHARYYA_MAX = 0.35
TEXT_ARTIFACT_MIN_COMPONENTS = 6
OUTPAINT_MAX_ATTEMPTS = 2

# --- relayout ---------------------------------------------------------------- #
SAFE_MARGIN_FRAC = 0.05     # margem de segurança: 5% da MENOR dimensão do alvo
MIN_BAND_FRAC = 0.18        # faixa lateral menor que isso não comporta uma coluna
WIDE_RATIO = 1.5            # a partir daqui o alvo é "wide" e ganha coluna lateral
STACK_GAP_FRAC = 0.30       # respiro entre blocos, em frações da altura média
MIN_FONT_PX = 8
# Política em que os blocos NÃO são reempilhados, só reescalados no lugar.
POLICY_KEEP = "posições proporcionais mantidas"

# Ordem de leitura da pilha de texto. Não é a ordem original na peça: é a ordem
# que faz sentido depois de remontar (título -> apoio -> preço -> CTA -> legal).
_ROLE_RANK: dict[TextRole, int] = {
    TextRole.LOGO: 0,
    TextRole.BADGE: 1,
    TextRole.HEADLINE: 2,
    TextRole.SUBHEAD: 3,
    TextRole.PRICE: 4,
    TextRole.OTHER: 5,
    TextRole.CTA: 6,
    TextRole.LEGAL: 7,
}

# Peso de cada coisa que vale a pena preservar num recorte (modo `crop`).
_INTEREST_WEIGHT: dict[TextRole, float] = {
    TextRole.LOGO: 3.0,
    TextRole.CTA: 2.5,
    TextRole.HEADLINE: 2.0,
    TextRole.PRICE: 1.8,
    TextRole.SUBHEAD: 1.2,
    TextRole.BADGE: 1.0,
    TextRole.OTHER: 0.8,
    TextRole.LEGAL: 0.4,
}
SAFE_AREA_WEIGHT = 3.0


# --------------------------------------------------------------------------- #
# Alvo e geometria
# --------------------------------------------------------------------------- #
def resolve_target(target: Any, src_w: int, src_h: int) -> tuple[int, int, str]:
    """``target`` -> ``(largura, altura, rótulo)`` em pixels pares.

    Aceita :class:`AspectSpec`, ``"16:9"``, ``"1080x1920"``, ``"9:16@1080"`` ou
    ``(w, h)``. Quando a spec não traz pixels explícitos, a resolução é
    derivada do **maior lado da origem** — reenquadrar não é hora de mudar a
    resolução de entrega, e um 1080x1920 vira 1920x1080, não 1440x810.
    """
    if isinstance(target, AspectSpec):
        spec = target
    elif isinstance(target, (tuple, list)) and len(target) == 2:
        w, h = int(target[0]), int(target[1])
        if w <= 0 or h <= 0:
            raise ValueError(f"tamanho alvo inválido: {w}x{h} (precisa ser positivo)")
        return (w - w % 2, h - h % 2, AspectSpec.parse(f"{w}x{h}").label)
    elif isinstance(target, str):
        try:
            spec = AspectSpec.parse(target)
        except ValueError as exc:
            raise ValueError(
                f"formato de destino inválido: {target!r}.\n"
                "  Use '16:9', '1:1', '1080x1920' ou '9:16@1080'."
            ) from exc
    else:
        raise ValueError(
            f"formato de destino inválido: {target!r}.\n"
            "  Use uma AspectSpec, uma string como '16:9' ou uma tupla (largura, altura)."
        )
    # Piso de 64 px: uma miniatura de 1 px faria `resolve` arredondar o lado
    # curto para zero e o erro sairia longe daqui.
    long_edge = max(64, int(src_w), int(src_h))
    w, h = spec.resolve(long_edge=long_edge)
    if w <= 0 or h <= 0:
        raise ValueError(f"formato de destino resolveu para {w}x{h}, o que é impossível.")
    return (w, h, spec.label)


def plan_placement(src_w: int, src_h: int, dst_w: int, dst_h: int) -> tuple[Box, float]:
    """Onde o original cabe inteiro dentro do alvo, e por qual fator.

    É a matemática do "cabe sem distorcer", isolada num lugar só para que todo
    modo use exatamente a mesma conta: um **único** fator de escala
    ``s = min(dst_w/src_w, dst_h/src_h)`` aplicado aos dois eixos, e a caixa
    resultante centralizada.

    Devolve ``(caixa_do_conteúdo, escala)``. A razão da caixa devolvida é igual
    à da origem a menos do arredondamento para pixel inteiro (≤ 1 px por lado).
    """
    src_w, src_h, dst_w, dst_h = int(src_w), int(src_h), int(dst_w), int(dst_h)
    if src_w <= 0 or src_h <= 0:
        raise ValueError("imagem de origem com dimensão zero")
    if dst_w <= 0 or dst_h <= 0:
        raise ValueError(f"tamanho alvo inválido: {dst_w}x{dst_h}")
    scale = min(dst_w / src_w, dst_h / src_h)
    nw = max(1, min(dst_w, int(round(src_w * scale))))
    nh = max(1, min(dst_h, int(round(src_h * scale))))
    return (Box((dst_w - nw) // 2, (dst_h - nh) // 2, nw, nh), scale)


def generated_bands(content: Box, dst_w: int, dst_h: int) -> list[Box]:
    """As faixas do canvas que NÃO são o original — ou seja, o que foi inventado.

    São no máximo quatro retângulos disjuntos (esquerda, direita, topo, base),
    e é essa lista que vai para ``protect.drift_report`` como "região onde é
    permitido mudar". Faixas vazias são omitidas.
    """
    b = content.clamp(dst_w, dst_h)
    out: list[Box] = []
    if b.x > 0:
        out.append(Box(0, 0, b.x, dst_h))
    if b.x1 < dst_w:
        out.append(Box(b.x1, 0, dst_w - b.x1, dst_h))
    if b.y > 0:
        out.append(Box(b.x, 0, b.w, b.y))
    if b.y1 < dst_h:
        out.append(Box(b.x, b.y1, b.w, dst_h - b.y1))
    return [x for x in out if x.area > 0]


# --------------------------------------------------------------------------- #
# Preenchimento do fundo
# --------------------------------------------------------------------------- #
def _reflect_pad(arr: np.ndarray, top: int, bottom: int, left: int, right: int) -> np.ndarray:
    """Espelha as bordas até cobrir a extensão pedida.

    ``np.pad(mode="reflect")`` não aceita padding maior que ``dim-1``; aqui a
    reflexão é aplicada em rodadas até chegar ao tamanho, o que produz o efeito
    de "sanfona" esperado quando a faixa nova é maior que a imagem.
    """
    out = arr
    top, bottom, left, right = max(0, top), max(0, bottom), max(0, left), max(0, right)
    while top or bottom or left or right:
        h, w = out.shape[:2]
        t, b = min(top, h - 1), min(bottom, h - 1)
        l, r = min(left, w - 1), min(right, w - 1)
        if not (t or b or l or r):   # imagem de 1 px num eixo: replica a borda
            return np.pad(out, ((top, bottom), (left, right), (0, 0)), mode="edge")
        out = np.pad(out, ((t, b), (l, r), (0, 0)), mode="reflect")
        top -= t
        bottom -= b
        left -= l
        right -= r
    return out


def _blur_fill(img: Image.Image, w: int, h: int) -> Image.Image:
    """A própria imagem em ``cover``, borrada, escurecida e dessaturada.

    Escurecer e dessaturar não é gosto: sem isso o fundo tem o mesmo contraste
    da peça e a leitura vira "vídeo vertical num player wide". Com isso vira
    moldura.
    """
    base = _io.resize_cover(img, w, h).convert("RGB")
    radius = max(4.0, BLUR_SIGMA_FRAC * max(w, h))
    arr = np.asarray(base.filter(ImageFilter.GaussianBlur(radius=radius)), dtype=np.float32)
    gray = arr @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    arr = arr * (1.0 - BLUR_DESAT) + gray[..., None] * BLUR_DESAT
    arr *= BLUR_DIM
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _mirror_fill(img: Image.Image, w: int, h: int, content: Box) -> Image.Image:
    """Canvas preenchido pelo espelhamento das bordas do conteúdo.

    Só vale a pena quando as faixas laterais são textura ou cor chapada: com
    rosto, logo ou produto perto da borda o espelhamento duplica um objeto
    reconhecível e a simetria denuncia na hora. Quem chama decide.
    """
    scaled = img.convert("RGB").resize((content.w, content.h), Image.Resampling.LANCZOS)
    arr = np.asarray(scaled, dtype=np.uint8)
    padded = _reflect_pad(arr, content.y, h - content.y1, content.x, w - content.x1)
    return Image.fromarray(np.ascontiguousarray(padded[:h, :w]), "RGB")


def _fill_color(fill: Any, img: Image.Image, palette: Sequence[Any] | None) -> tuple[int, int, int]:
    """Resolve a cor de um preenchimento chapado."""
    if isinstance(fill, (tuple, list)) and len(fill) >= 3:
        return parse_color(fill)
    key = str(fill or "color").strip().lower()
    if key in ("white", "branco"):
        return (255, 255, 255)
    if key in ("black", "preto"):
        return (0, 0, 0)
    if key.startswith("#") or (len(key) in (3, 6) and all(c in "0123456789abcdef" for c in key)):
        return parse_color(key)
    if palette:
        return parse_color(palette[0])
    dom = _io.dominant_colors(img, k=3)
    return dom[0] if dom else (0, 0, 0)


def build_background(img: Image.Image, w: int, h: int, *, fill: Any = "blur",
                     content: Box | None = None,
                     palette: Sequence[Any] | None = None) -> tuple[Image.Image, str]:
    """Canvas ``w x h`` já preenchido, pronto para receber o original por cima.

    Devolve ``(canvas, rótulo_do_preenchimento)`` — o rótulo entra no ``info``
    porque "que fundo foi usado" é a primeira pergunta de quem revisa o lote.
    """
    key = fill if isinstance(fill, str) else "color"
    key = str(key or "blur").strip().lower()
    if key in ("mirror", "espelho", "espelhado"):
        box = content or plan_placement(img.width, img.height, w, h)[0]
        return (_mirror_fill(img, w, h, box), "mirror")
    if key in ("blur", "borrado", "desfoque"):
        return (_blur_fill(img, w, h), "blur")
    color = _fill_color(fill, img, palette)
    label = "white" if color == (255, 255, 255) else "black" if color == (0, 0, 0) else "color"
    return (Image.new("RGB", (w, h), color), label)


def pad_canvas(img: Image.Image, dst_w: int, dst_h: int, *, fill: Any = "blur",
               palette: Sequence[Any] | None = None) -> tuple[Image.Image, Box, float]:
    """Original centralizado num canvas ``dst_w x dst_h``, sem distorção.

    Devolve ``(canvas, caixa_do_conteúdo, escala)``. O conteúdo é reescalado uma
    única vez, com um único fator, e colado — nada de ``resize`` por eixo.
    """
    content, scale = plan_placement(img.width, img.height, dst_w, dst_h)
    canvas, _ = build_background(img, dst_w, dst_h, fill=fill, content=content, palette=palette)
    scaled = img.convert("RGB").resize((content.w, content.h), Image.Resampling.LANCZOS)
    canvas.paste(scaled, (content.x, content.y))
    return (canvas, content, scale)


# --------------------------------------------------------------------------- #
# Modo crop
# --------------------------------------------------------------------------- #
def _interest_boxes(analysis: CreativeAnalysis | None, src_w: int, src_h: int) -> list[tuple[Box, float, str]]:
    """``(caixa, peso, rótulo)`` de tudo que o recorte deve tentar preservar."""
    out: list[tuple[Box, float, str]] = []
    if analysis is None:
        return out
    for i, sa in enumerate(analysis.safe_areas or []):
        b = sa.clamp(src_w, src_h)
        if b.area > 0:
            out.append((b, SAFE_AREA_WEIGHT, f"área segura #{i + 1}"))
    for blk in analysis.text_blocks or []:
        b = blk.box.clamp(src_w, src_h)
        if b.area <= 0:
            continue
        role = blk.role if isinstance(blk.role, TextRole) else TextRole.OTHER
        rotulo = role.value if not blk.text else f"{role.value} “{blk.text[:24]}”"
        out.append((b, _INTEREST_WEIGHT.get(role, 0.8), rotulo))
    return out


def plan_crop(src_w: int, src_h: int, dst_w: int, dst_h: int, *,
              interest: Sequence[tuple[Box, float, str]] | None = None) -> Box:
    """Maior recorte com a razão do alvo, posicionado onde preserva mais.

    O recorte tem sempre a razão exata do destino (então a reescala final é
    uniforme). Sobra um grau de liberdade — deslizar no eixo mais longo — e ele
    é resolvido maximizando a soma ponderada da fração coberta de cada caixa de
    interesse. Sem análise, o recorte é centralizado.
    """
    ratio = dst_w / dst_h
    cw = min(src_w, int(round(src_h * ratio)))
    ch = min(src_h, int(round(cw / ratio)))
    cw = min(src_w, int(round(ch * ratio)))
    cw, ch = max(1, cw), max(1, ch)

    free_x, free_y = src_w - cw, src_h - ch
    if free_x <= 0 and free_y <= 0:
        return Box(0, 0, cw, ch)

    boxes = list(interest or [])
    cx0, cy0 = free_x // 2, free_y // 2
    if not boxes:
        return Box(cx0, cy0, cw, ch)

    def score(ox: int, oy: int) -> float:
        crop = Box(ox, oy, cw, ch)
        total = 0.0
        for b, wgt, _ in boxes:
            if b.area <= 0:
                continue
            ix = min(crop.x1, b.x1) - max(crop.x, b.x)
            iy = min(crop.y1, b.y1) - max(crop.y, b.y)
            if ix <= 0 or iy <= 0:
                continue
            total += wgt * (ix * iy) / b.area
        # desempate suave em direção ao centro: recorte centralizado é o que o
        # olho espera quando nada mais diferencia duas posições.
        drift = abs(ox - cx0) / max(1, free_x) + abs(oy - cy0) / max(1, free_y)
        return total - 0.001 * drift

    def candidates(free: int, center: int, lo_edges: Iterable[int]) -> list[int]:
        if free <= 0:
            return [0]
        step = max(1, free // 48)
        vals = set(range(0, free + 1, step))
        vals.update({0, free, center})
        for e in lo_edges:                      # alinhar o recorte às caixas importa
            vals.add(max(0, min(free, int(e))))
        return sorted(vals)

    xs = candidates(free_x, cx0, [b.x for b, _, _ in boxes] + [b.x1 - cw for b, _, _ in boxes]
                    + [b.center[0] - cw // 2 for b, _, _ in boxes])
    ys = candidates(free_y, cy0, [b.y for b, _, _ in boxes] + [b.y1 - ch for b, _, _ in boxes]
                    + [b.center[1] - ch // 2 for b, _, _ in boxes])

    best, best_s = (cx0, cy0), float("-inf")
    for ox in xs:
        for oy in ys:
            s = score(ox, oy)
            if s > best_s:
                best_s, best = s, (ox, oy)
    return Box(best[0], best[1], cw, ch)


def _crop_losses(crop: Box, interest: Sequence[tuple[Box, float, str]]) -> list[dict[str, Any]]:
    """O que o recorte deixou de fora, para o usuário poder discordar."""
    perdas: list[dict[str, Any]] = []
    for b, _, rotulo in interest:
        if b.area <= 0:
            continue
        ix = max(0, min(crop.x1, b.x1) - max(crop.x, b.x))
        iy = max(0, min(crop.y1, b.y1) - max(crop.y, b.y))
        keep = (ix * iy) / b.area
        if keep >= 0.995:
            continue
        perdas.append({"o_que": rotulo, "preservado": round(keep, 3),
                       "cortado": round(1.0 - keep, 3), "box": b.to_dict()})
    perdas.sort(key=lambda d: d["cortado"], reverse=True)
    return perdas


# --------------------------------------------------------------------------- #
# Verificação de qualidade do outpaint (G.5)
# --------------------------------------------------------------------------- #
def _delta_e(a: np.ndarray, b: np.ndarray) -> float:
    """ΔE aproximado (norma L2 em RGB). Barato e suficiente para costura."""
    return float(np.linalg.norm(np.asarray(a, np.float32) - np.asarray(b, np.float32)))


def _seam_deltas(arr: np.ndarray, content: Box) -> dict[str, float]:
    """ΔE em cada uma das quatro costuras entre o original e o gerado."""
    h, w = arr.shape[:2]
    p = SEAM_PROBE
    out: dict[str, float] = {}
    if content.x > 0:
        inner = arr[:, content.x:content.x + p].reshape(-1, 3).mean(0)
        outer = arr[:, max(0, content.x - p):content.x].reshape(-1, 3).mean(0)
        out["esquerda"] = _delta_e(inner, outer)
    if content.x1 < w:
        inner = arr[:, max(0, content.x1 - p):content.x1].reshape(-1, 3).mean(0)
        outer = arr[:, content.x1:content.x1 + p].reshape(-1, 3).mean(0)
        out["direita"] = _delta_e(inner, outer)
    if content.y > 0:
        inner = arr[content.y:content.y + p, content.x:content.x1].reshape(-1, 3).mean(0)
        outer = arr[max(0, content.y - p):content.y, content.x:content.x1].reshape(-1, 3).mean(0)
        out["topo"] = _delta_e(inner, outer)
    if content.y1 < h:
        inner = arr[max(0, content.y1 - p):content.y1, content.x:content.x1].reshape(-1, 3).mean(0)
        outer = arr[content.y1:content.y1 + p, content.x:content.x1].reshape(-1, 3).mean(0)
        out["base"] = _delta_e(inner, outer)
    return out


def _correct_seams(arr: np.ndarray, content: Box) -> list[str]:
    """Ganho por canal com rampa, aplicado SÓ do lado gerado da costura.

    Muta ``arr`` in-place e devolve os lados corrigidos. Nenhuma escrita cai
    dentro de ``content``: os índices são todos estritamente fora dela.
    """
    h, w = arr.shape[:2]
    p = SEAM_PROBE
    fixed: list[str] = []
    f = arr.astype(np.float32)

    def ramp(n: int) -> np.ndarray:
        """Expoente do ganho: 1 na costura, 0 no fim da rampa.

        Smoothstep, não linear: com rampa linear a derivada salta no fim da
        correção e aparece uma segunda "costura" mais fraca justamente onde a
        correção acaba. Com derivada zero nas duas pontas isso some.
        """
        t = np.linspace(0.0, 1.0, max(1, n), dtype=np.float32)
        return 1.0 - (3.0 * t ** 2 - 2.0 * t ** 3)

    if content.x > 0:
        band = content.x
        inner = f[:, content.x:content.x + p].reshape(-1, 3).mean(0)
        outer = f[:, max(0, band - p):band].reshape(-1, 3).mean(0)
        if _delta_e(inner, outer) > SEAM_DELTA_MAX:
            L = max(1, int(SEAM_RAMP_FRAC * band))
            g = inner / np.maximum(outer, 1e-3)
            cols = np.arange(band - 1, band - 1 - L, -1)
            fac = np.power(g[None, :], ramp(L)[:, None])           # (L, 3)
            f[:, cols, :] = np.clip(f[:, cols, :] * fac[None, :, :], 0, 255)
            fixed.append("esquerda")
    if content.x1 < w:
        band = w - content.x1
        inner = f[:, max(0, content.x1 - p):content.x1].reshape(-1, 3).mean(0)
        outer = f[:, content.x1:content.x1 + p].reshape(-1, 3).mean(0)
        if _delta_e(inner, outer) > SEAM_DELTA_MAX:
            L = max(1, int(SEAM_RAMP_FRAC * band))
            g = inner / np.maximum(outer, 1e-3)
            cols = np.arange(content.x1, content.x1 + L)
            fac = np.power(g[None, :], ramp(L)[:, None])
            f[:, cols, :] = np.clip(f[:, cols, :] * fac[None, :, :], 0, 255)
            fixed.append("direita")
    if content.y > 0:
        band = content.y
        inner = f[content.y:content.y + p, content.x:content.x1].reshape(-1, 3).mean(0)
        outer = f[max(0, band - p):band, content.x:content.x1].reshape(-1, 3).mean(0)
        if _delta_e(inner, outer) > SEAM_DELTA_MAX:
            L = max(1, int(SEAM_RAMP_FRAC * band))
            g = inner / np.maximum(outer, 1e-3)
            rows = np.arange(band - 1, band - 1 - L, -1)
            fac = np.power(g[None, :], ramp(L)[:, None])
            f[rows, :, :] = np.clip(f[rows, :, :] * fac[:, None, :], 0, 255)
            fixed.append("topo")
    if content.y1 < h:
        band = h - content.y1
        inner = f[max(0, content.y1 - p):content.y1, content.x:content.x1].reshape(-1, 3).mean(0)
        outer = f[content.y1:content.y1 + p, content.x:content.x1].reshape(-1, 3).mean(0)
        if _delta_e(inner, outer) > SEAM_DELTA_MAX:
            L = max(1, int(SEAM_RAMP_FRAC * band))
            g = inner / np.maximum(outer, 1e-3)
            rows = np.arange(content.y1, content.y1 + L)
            fac = np.power(g[None, :], ramp(L)[:, None])
            f[rows, :, :] = np.clip(f[rows, :, :] * fac[:, None, :], 0, 255)
            fixed.append("base")

    if fixed:
        arr[:] = np.rint(f).astype(np.uint8)
    return fixed


def _looks_like_text(region: np.ndarray) -> bool:
    """Heurística barata para "o modelo escreveu alguma coisa aqui".

    Texto gerado por modelo de imagem é o defeito mais caro do outpaint (sai
    ilegível e ninguém aceita). A assinatura procurada é a de uma linha de
    texto: vários componentes de borda com altura parecida, alinhados
    horizontalmente.
    """
    if not HAS_CV2 or region.size == 0 or min(region.shape[:2]) < 12:
        return False
    try:
        g = cv2.cvtColor(np.ascontiguousarray(region), cv2.COLOR_RGB2GRAY)
        edges = cv2.Canny(g, 50, 150)
        edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)
        n, _lbl, st, _cen = cv2.connectedComponentsWithStats(edges, 8)
    except Exception:  # pragma: no cover - defensivo
        return False
    cands: list[tuple[float, float]] = []
    for i in range(1, n):
        x, y, w, h, _a = st[i][:5]
        if not (8 <= h <= 60) or w <= 0:
            continue
        if 0.2 <= h / w <= 3.0:
            cands.append((y + h / 2.0, float(h)))
    for cy, ch in cands:
        grupo = [c for c in cands
                 if abs(c[0] - cy) <= 0.5 * ch and abs(c[1] - ch) <= 0.10 * ch + 1.0]
        if len(grupo) >= TEXT_ARTIFACT_MIN_COMPONENTS:
            return True
    return False


def _hist_distance(a: np.ndarray, b: np.ndarray) -> float | None:
    """Bhattacharyya entre histogramas HSV — detecta color grade trocado."""
    if not HAS_CV2 or a.size == 0 or b.size == 0:
        return None
    try:
        ha = cv2.calcHist([cv2.cvtColor(np.ascontiguousarray(a), cv2.COLOR_RGB2HSV)],
                          [0, 1], None, [32, 32], [0, 180, 0, 256])
        hb = cv2.calcHist([cv2.cvtColor(np.ascontiguousarray(b), cv2.COLOR_RGB2HSV)],
                          [0, 1], None, [32, 32], [0, 180, 0, 256])
        cv2.normalize(ha, ha)
        cv2.normalize(hb, hb)
        return float(cv2.compareHist(ha, hb, cv2.HISTCMP_BHATTACHARYYA))
    except Exception:  # pragma: no cover - defensivo
        return None


def _has_face(region: np.ndarray) -> bool:
    """Rosto na faixa gerada = sujeito duplicado. Silencioso se não houver cascata."""
    if not HAS_CV2 or region.size == 0 or min(region.shape[:2]) < 60:
        return False
    try:
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"  # type: ignore[attr-defined]
        clf = cv2.CascadeClassifier(path)
        if clf.empty():
            return False
        g = cv2.cvtColor(np.ascontiguousarray(region), cv2.COLOR_RGB2GRAY)
        faces = clf.detectMultiScale(g, scaleFactor=1.2, minNeighbors=6, minSize=(40, 40))
        return len(faces) > 0
    except Exception:  # pragma: no cover - defensivo
        return False


def _validate_generated(arr: np.ndarray, content: Box, bands: Sequence[Box]) -> list[str]:
    """Motivos para rejeitar o resultado do outpaint (vazio = aprovado)."""
    motivos: list[str] = []
    seams = _seam_deltas(arr, content)
    ruins = {k: round(v, 1) for k, v in seams.items() if v > SEAM_DELTA_MAX}
    if ruins:
        motivos.append(f"costura visível mesmo após correção: {ruins}")

    ref = arr[content.y:content.y1, content.x:content.x1]
    for b in bands:
        if b.area < 400:
            continue
        faixa = arr[b.y:b.y1, b.x:b.x1]
        if _looks_like_text(faixa):
            motivos.append("a IA desenhou algo com aparência de texto na área gerada")
            break
    for b in bands:
        if b.area < 4000:
            continue
        d = _hist_distance(arr[b.y:b.y1, b.x:b.x1], ref)
        if d is not None and d > HIST_BHATTACHARYYA_MAX:
            motivos.append(f"a IA mudou o tratamento de cor da cena (Bhattacharyya {d:.2f})")
            break
    ref_face = _has_face(ref)
    if not ref_face:
        for b in bands:
            if b.area >= 40000 and _has_face(arr[b.y:b.y1, b.x:b.x1]):
                motivos.append("apareceu um rosto na área gerada (sujeito duplicado)")
                break
    return motivos


# --------------------------------------------------------------------------- #
# Modo relayout
# --------------------------------------------------------------------------- #
@dataclass
class BlockPlan:
    """Para onde um bloco de texto vai no novo enquadramento."""

    block: TextBlock
    old_box: Box
    new_box: Box
    size_px: int
    spec: FontSpec
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        role = self.block.role
        return {
            "role": role.value if isinstance(role, TextRole) else str(role),
            "text": self.block.text,
            "de": self.old_box.to_dict(),
            "para": self.new_box.to_dict(),
            "size_px": self.size_px,
            "nota": self.note,
        }


def _map_box(b: Box, content: Box, scale: float, dst_w: int, dst_h: int) -> Box:
    """Caixa da origem -> caixa equivalente dentro do conteúdo já reposicionado."""
    return Box(content.x + int(round(b.x * scale)),
               content.y + int(round(b.y * scale)),
               max(1, int(round(b.w * scale))),
               max(1, int(round(b.h * scale)))).clamp(dst_w, dst_h)


def _shift_inside(b: Box, frame: Box) -> Box:
    """Empurra ``b`` para dentro de ``frame`` sem mudar o tamanho (se couber)."""
    w = min(b.w, frame.w) if frame.w > 0 else b.w
    h = min(b.h, frame.h) if frame.h > 0 else b.h
    x = max(frame.x, min(b.x, frame.x1 - w))
    y = max(frame.y, min(b.y, frame.y1 - h))
    return Box(x, y, max(1, w), max(1, h))


def _stack_region(dst_w: int, dst_h: int, content: Box, margin: int,
                  safe: Sequence[Box]) -> tuple[Box, str]:
    """Onde a pilha de texto cabe no novo formato, e por qual política.

    Alvo largo (≥ 1,5): coluna na faixa lateral gerada — é a faixa que existe
    justamente porque o formato ficou largo, e é onde o texto respira sem tapar
    o sujeito. Alvo quadrado/vertical: pilha central sobre o conteúdo, que é
    como esses formatos são lidos.
    """
    ratio = dst_w / dst_h
    left = Box(0, 0, content.x, dst_h)
    right = Box(content.x1, 0, dst_w - content.x1, dst_h)
    bottom = Box(content.x, content.y1, content.w, dst_h - content.y1)

    def usable(b: Box) -> Box:
        return Box(b.x + margin, b.y + margin,
                   max(0, b.w - 2 * margin), max(0, b.h - 2 * margin)).clamp(dst_w, dst_h)

    def livre(b: Box) -> bool:
        return b.area > 0 and not any(b.intersects(s) for s in safe)

    if ratio >= WIDE_RATIO:
        cands = sorted([left, right], key=lambda b: -b.w)
        for c in cands:
            if c.w >= MIN_BAND_FRAC * dst_w:
                reg = usable(c)
                if livre(reg):
                    lado = "esquerda" if c.x == 0 else "direita"
                    return (reg, f"coluna lateral ({lado})")
    if bottom.h >= 0.18 * dst_h:
        reg = usable(bottom)
        if livre(reg):
            return (reg, "faixa inferior gerada")
    # Não sobrou faixa livre: nada de reempilhar. Mantemos a pilha onde ela
    # está, só reescalada — é o que "manter a pilha central" quer dizer em 1:1
    # e 4:5, onde o formato mudou pouco e mexer no layout só piora.
    inner = Box(content.x + margin, content.y + margin,
                max(1, content.w - 2 * margin), max(1, content.h - 2 * margin))
    return (inner.clamp(dst_w, dst_h), POLICY_KEEP)


def plan_relayout(analysis: CreativeAnalysis, dst_w: int, dst_h: int, *,
                  content: Box | None = None,
                  scale: float | None = None) -> tuple[list[BlockPlan], Box, str, list[str]]:
    """Novas posições dos blocos de texto no formato alvo.

    Devolve ``(planos, região_da_pilha, política, avisos)``. Só entram blocos
    com texto conhecido: sem OCR (análise offline) o texto vem vazio e
    reposicionar significaria apagar sem conseguir redesenhar — nesse caso o
    bloco é deixado como está, viajando junto com o fundo.
    """
    warns: list[str] = []
    src_w, src_h = analysis.width or dst_w, analysis.height or dst_h
    if content is None or scale is None:
        content, scale = plan_placement(src_w, src_h, dst_w, dst_h)

    margin = max(4, int(round(SAFE_MARGIN_FRAC * min(dst_w, dst_h))))
    safe_mapped = [_map_box(s, content, scale, dst_w, dst_h) for s in (analysis.safe_areas or [])]

    usaveis = [b for b in (analysis.text_blocks or []) if str(b.text or "").strip()]
    mudos = len(analysis.text_blocks or []) - len(usaveis)
    if mudos:
        warns.append(
            f"{mudos} bloco(s) de texto sem conteúdo conhecido não foram reposicionados "
            "(a análise offline não faz OCR; rode com OPENAI_API_KEY para reposicioná-los)"
        )
    if not usaveis:
        return ([], Box(0, 0, 0, 0), "sem texto reposicionável", warns)

    region, politica = _stack_region(dst_w, dst_h, content, margin, safe_mapped)
    if region.area <= 0:
        warns.append("não sobrou área livre para a pilha de texto; o layout foi mantido")
        return ([], region, "sem espaço", warns)

    if politica == POLICY_KEEP:
        frame = Box(margin, margin, dst_w - 2 * margin, dst_h - 2 * margin)
        planos_map: list[BlockPlan] = []
        for blk in usaveis:
            nb = _shift_inside(_map_box(blk.box, content, scale, dst_w, dst_h), frame)
            size = max(MIN_FONT_PX, int(round((blk.style.size_px or 48) * scale)))
            planos_map.append(BlockPlan(block=blk, old_box=blk.box, new_box=nb, size_px=size,
                                        spec=replace(blk.style, size_px=size)))
        return (planos_map, region, politica, warns)

    ordenados = sorted(
        usaveis,
        key=lambda b: (_ROLE_RANK.get(b.role if isinstance(b.role, TextRole) else TextRole.OTHER, 5),
                       b.box.y),
    )

    # Alturas naturais: o mesmo fator uniforme do conteúdo. Se a pilha não
    # couber na região, todos encolhem pelo MESMO k — encolher só um quebra a
    # hierarquia tipográfica da peça.
    alturas = [max(1, int(round(b.box.h * scale))) for b in ordenados]
    media = sum(alturas) / len(alturas)
    gap = max(4, int(round(STACK_GAP_FRAC * media)))
    total = sum(alturas) + gap * (len(alturas) - 1)
    k = 1.0
    if total > region.h:
        util = max(1, region.h - gap * (len(alturas) - 1))
        k = max(0.35, util / max(1, sum(alturas)))
        if k < 0.6:
            warns.append(
                f"a pilha de texto precisou encolher para {int(k * 100)}% para caber no formato alvo"
            )
    alturas = [max(MIN_FONT_PX, int(round(h * k))) for h in alturas]
    total = sum(alturas) + gap * (len(alturas) - 1)

    y = region.y + max(0, (region.h - total) // 2)
    planos: list[BlockPlan] = []
    for blk, alt in zip(ordenados, alturas):
        largura_nat = max(1, int(round(blk.box.w * scale * k)))
        nw = min(region.w, max(int(0.35 * region.w), largura_nat))
        align = (blk.style.align or "center").lower()
        if align == "left":
            x = region.x
        elif align == "right":
            x = region.x + region.w - nw
        else:
            x = region.x + (region.w - nw) // 2
        nb = Box(x, y, nw, alt).clamp(dst_w, dst_h)
        fator = alt / max(1, blk.box.h)
        size = max(MIN_FONT_PX, int(round((blk.style.size_px or 48) * fator)))
        nota = ""
        if blk.on_solid_background or blk.background_color:
            # A pastilha é fundo, não texto: ela fica onde estava e o texto vai
            # embora. Quem revisa precisa saber disso antes de aprovar o lote.
            nota = "a pastilha de fundo não veio junto"
            warns.append(
                f"o bloco {getattr(blk.role, 'value', blk.role)} tinha uma pastilha de fundo "
                "que não foi reposicionada com o texto"
            )
        for s in safe_mapped:
            if nb.intersects(s):
                nota = (nota + "; " if nota else "") + "encosta numa área segura"
                warns.append(
                    f"o bloco {getattr(blk.role, 'value', blk.role)} ficou sobre uma área segura; "
                    "revise a posição"
                )
                break
        planos.append(BlockPlan(block=blk, old_box=blk.box, new_box=nb, size_px=size,
                                spec=replace(blk.style, size_px=size), note=nota))
        y += alt + gap
    return (planos, region, politica, warns)


# --------------------------------------------------------------------------- #
# reframe
# --------------------------------------------------------------------------- #
def _base_info(mode: str, requested: str, img: Image.Image,
               dst_w: int, dst_h: int, label: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "requested_mode": requested,
        "target": {"w": dst_w, "h": dst_h, "label": label,
                   "aspect": round(dst_w / dst_h, 6)},
        "source": {"w": img.width, "h": img.height,
                   "aspect": round(img.width / img.height, 6) if img.height else 0.0},
        "scale": 1.0,
        "content_box": None,
        "source_crop": None,
        "generated_boxes": [],
        "generated_fraction": 0.0,
        "fill": None,
        "engine": "deterministic",
        "cost_usd": 0.0,
        "aspect_preserved": True,
        "content_aspect": None,
        "drift_pixels": None,
        "content_intact": None,
        "cut": [],
        "text_blocks": [],
        "warnings": [],
        "notes": "",
    }


def _finish(out: Image.Image, src: Image.Image, info: dict[str, Any],
            content: Box | None) -> tuple[Image.Image, dict[str, Any]]:
    """Fecha o ``info``: razão preservada, área gerada, metadados de cor."""
    if content is not None:
        info["content_box"] = content.to_dict()
        ca = content.w / content.h if content.h else 0.0
        sa = src.width / src.height if src.height else 0.0
        info["content_aspect"] = round(ca, 6)
        # Tolerância de 1 px por lado: o arredondamento para pixel inteiro é a
        # única fonte de diferença admitida. Acima disso alguém esticou algo.
        tol = max(1.0 / max(1, content.h), 1.0 / max(1, content.w)) * max(sa, 1.0) + 1e-6
        info["aspect_preserved"] = bool(abs(ca - sa) <= tol * 1.5)
        if not info["aspect_preserved"]:
            info["warnings"].append(
                f"a razão do conteúdo mudou ({sa:.4f} -> {ca:.4f}); isso é um bug, reporte"
            )
        bands = generated_bands(content, out.width, out.height)
        info["generated_boxes"] = [b.to_dict() for b in bands]
        info["generated_fraction"] = round(
            sum(b.area for b in bands) / max(1, out.width * out.height), 4)
    icc = src.info.get("icc_profile")
    if icc:
        out.info["icc_profile"] = icc
    return (out, info)


def reframe(img: Image.Image, target: Any, *, mode: str = "pad", settings: Any = None,
            analysis: CreativeAnalysis | None = None, fill: Any = "blur",
            prompt: str | None = None) -> tuple[Image.Image, dict[str, Any]]:
    """Reenquadra ``img`` para ``target`` e conta o que fez.

    Parâmetros
    ----------
    target:
        :class:`AspectSpec`, ``"16:9"``, ``"1080x1920"``, ``"9:16@1080"`` ou
        ``(largura, altura)``.
    mode:
        ``pad`` (padrão) | ``crop`` | ``outpaint`` | ``relayout``.
    analysis:
        Necessária para ``relayout`` e muito útil em ``crop`` (é ela que diz o
        que não pode ser cortado). Opcional nos demais.
    fill:
        Preenchimento das sobras em ``pad``/``relayout``: ``blur`` (padrão),
        ``mirror``, ``color``, ``white``, ``black``, ou uma cor (``"#ff0044"``,
        ``(255, 0, 68)``).

    Devolve ``(imagem, info)``. O ``info`` traz ``mode``, ``scale``,
    ``content_box`` (onde o original ficou), ``generated_boxes`` (o que é
    pixel novo), ``engine``, ``cost_usd``, ``drift_pixels`` e ``warnings``.

    Os modos ``pad``, ``crop`` e ``relayout``-sem-chave são determinísticos e
    funcionam offline. ``outpaint`` sem chave **não falha**: avisa e cai para
    ``pad`` — num lote de 30 imagens, abortar tudo por causa de uma variável de
    ambiente é pior que entregar a moldura determinística.
    """
    if not isinstance(img, Image.Image):
        raise ValueError("reframe espera uma imagem PIL já carregada (use imageio_util.load_image).")
    alpha_descartado = False
    if img.mode == "RGBA":
        # Achata sobre branco (mesmo padrão de imageio_util.save_image): o
        # entregável é RGB e um canvas RGB com alpha solto vira pixel preto.
        flat = Image.new("RGB", img.size, (255, 255, 255))
        flat.paste(img, mask=img.split()[-1])
        flat.info.update(img.info)
        src, alpha_descartado = flat, True
    elif img.mode != "RGB":
        src = img.convert("RGB")
        src.info.update(img.info)
    else:
        src = img
    if src.width <= 0 or src.height <= 0:
        raise ValueError("imagem de origem com dimensão zero.")

    requested = str(mode or "pad").strip().lower()
    aliases = {"padding": "pad", "letterbox": "pad", "recorte": "crop", "cortar": "crop",
               "estender": "outpaint", "expand": "outpaint", "responsivo": "relayout",
               "reflow": "relayout"}
    use_mode = aliases.get(requested, requested)
    if use_mode not in MODES:
        raise ValueError(
            f"modo de reenquadramento desconhecido: {mode!r}.\n"
            f"  Use um de: {', '.join(MODES)}."
        )

    dst_w, dst_h, label = resolve_target(target, src.width, src.height)
    info = _base_info(use_mode, requested, src, dst_w, dst_h, label)
    palette = list(analysis.palette) if (analysis and analysis.palette) else None
    if alpha_descartado:
        info["warnings"].append(
            "a transparência do original foi achatada sobre branco: a entrega do reframe é RGB"
        )

    if use_mode == "crop":
        return _do_crop(src, dst_w, dst_h, analysis, info)
    if use_mode == "outpaint":
        return _do_outpaint(src, dst_w, dst_h, settings, prompt, fill, palette, info)
    if use_mode == "relayout":
        return _do_relayout(src, dst_w, dst_h, settings, analysis, prompt, fill, palette, info)
    return _do_pad(src, dst_w, dst_h, fill, palette, info)


# --------------------------------------------------------------------------- #
def _do_pad(src: Image.Image, dst_w: int, dst_h: int, fill: Any,
            palette: Sequence[Any] | None, info: dict[str, Any]) -> tuple[Image.Image, dict[str, Any]]:
    content, scale = plan_placement(src.width, src.height, dst_w, dst_h)
    canvas, fill_label = build_background(src, dst_w, dst_h, fill=fill,
                                          content=content, palette=palette)
    scaled = src.resize((content.w, content.h), Image.Resampling.LANCZOS)
    canvas.paste(scaled, (content.x, content.y))

    info["scale"] = round(scale, 6)
    info["fill"] = fill_label
    info["engine"] = "deterministic"
    if fill_label == "mirror":
        info["warnings"].append(
            "preenchimento espelhado: confira se não duplicou rosto, logo ou produto na borda"
        )
    if content.w == dst_w and content.h == dst_h:
        info["notes"] = "o formato já era o alvo: só houve reescala uniforme"
    else:
        info["notes"] = (f"original reduzido a {scale * 100:.1f}% e centralizado; "
                         f"sobras preenchidas por '{fill_label}'")
    return _finish(canvas, src, info, content)


# --------------------------------------------------------------------------- #
def _do_crop(src: Image.Image, dst_w: int, dst_h: int,
             analysis: CreativeAnalysis | None,
             info: dict[str, Any]) -> tuple[Image.Image, dict[str, Any]]:
    interest = _interest_boxes(analysis, src.width, src.height)
    if analysis is None:
        info["warnings"].append(
            "recorte sem análise: o corte é centralizado e pode cortar texto ou sujeito. "
            "Rode `s7 inspect` (ou passe analysis=) para um corte consciente."
        )
    crop = plan_crop(src.width, src.height, dst_w, dst_h, interest=interest)
    piece = src.crop(crop.xyxy)
    out = piece.resize((dst_w, dst_h), Image.Resampling.LANCZOS)

    scale = dst_w / crop.w if crop.w else 1.0
    info["scale"] = round(scale, 6)
    info["source_crop"] = crop.to_dict()
    info["fill"] = None
    info["engine"] = "deterministic"
    # No crop o "conteúdo" é a tela inteira: nada foi gerado, só descartado.
    content = Box(0, 0, dst_w, dst_h)
    info["cut"] = _crop_losses(crop, interest)
    perdido = 1.0 - (crop.area / max(1, src.width * src.height))
    info["discarded_fraction"] = round(perdido, 4)
    if info["cut"]:
        piores = ", ".join(f"{c['o_que']} (-{int(c['cortado'] * 100)}%)" for c in info["cut"][:3])
        info["warnings"].append(f"o recorte cortou: {piores}")
    info["notes"] = (f"recorte de {crop.w}x{crop.h} em ({crop.x},{crop.y}) "
                     f"descartando {perdido * 100:.1f}% da área original")
    # A razão preservada aqui é a do RECORTE, não a da imagem inteira — o
    # recorte já nasce com a razão do alvo, então a reescala é uniforme.
    info["content_aspect"] = round(dst_w / dst_h, 6)
    info["aspect_preserved"] = bool(abs((crop.w / crop.h) - (dst_w / dst_h)) <= 0.01)
    info["content_box"] = content.to_dict()
    info["generated_boxes"] = []
    info["generated_fraction"] = 0.0
    if not info["aspect_preserved"]:
        info["warnings"].append("o recorte não tem a razão do alvo; isso é um bug, reporte")
    icc = src.info.get("icc_profile")
    if icc:
        out.info["icc_profile"] = icc
    return (out, info)


# --------------------------------------------------------------------------- #
def _ai_available(settings: Any, info: dict[str, Any], *, motivo: str) -> bool:
    """Há chave para chamar a IA? Sem ela, avisa e deixa o chamador degradar."""
    from . import config as _config

    if settings is None:
        info["warnings"].append(
            f"{motivo} exige IA e nenhuma configuração foi passada; "
            "usando a moldura determinística."
        )
        return False
    if getattr(settings, "dry_run", False):
        return True   # aigen.outpaint devolve preview sem gastar crédito
    if not _config.has_openai(settings):
        info["warnings"].append(
            f"{motivo} exige OPENAI_API_KEY e ela não foi encontrada; "
            "caí para o preenchimento determinístico. "
            "Configure com `export OPENAI_API_KEY=sk-...` ou no arquivo .env do projeto "
            "e rode `s7 doctor` para conferir."
        )
        return False
    return True


def _outpaint_background(base: Image.Image, source_for_ai: Image.Image,
                         content: Box, dst_w: int, dst_h: int,
                         settings: Any, prompt: str | None,
                         info: dict[str, Any]) -> Image.Image | None:
    """Estende o fundo por IA e recola o original. ``None`` = reprovado/falhou.

    ``base`` é o canvas determinístico (original já colado em ``content``); é
    ele que entra em :func:`protect.protected_composite` como "original", o que
    torna a preservação do conteúdo uma propriedade da composição, não uma
    esperança sobre o modelo.
    """
    from . import aigen as _aigen

    bands = generated_bands(content, dst_w, dst_h)
    if not bands:
        return base

    custo = 0.0
    for tentativa in range(1, OUTPAINT_MAX_ATTEMPTS + 1):
        try:
            gen = _aigen.outpaint(source_for_ai, dst_w, dst_h, prompt,
                                  settings=settings, placement="center")
        except Exception as exc:      # ImageAPIError e qualquer falha de rede
            info["warnings"].append(f"a extensão por IA falhou ({exc}); usei o fundo determinístico.")
            info["cost_usd"] = round(custo, 4)
            return None
        custo += float(gen.info.get("s7_cost_usd", 0.0) or 0.0)
        if gen.size != (dst_w, dst_h):
            gen = gen.resize((dst_w, dst_h), Image.Resampling.LANCZOS)

        # Recolagem: o resultado começa como o canvas determinístico e recebe
        # escrita SÓ nas faixas geradas.
        out = _protect.protected_composite(base, gen.convert("RGB"), bands)
        preview = bool(gen.info.get("s7_preview"))
        if preview:
            # dry-run: a faixa lateral é um marcador, não uma cena. Validar isso
            # só gastaria duas tentativas para rejeitar o que já sabemos que é falso.
            info["warnings"].append(
                "preview (dry-run): as faixas laterais são um marcador, não a cena estendida"
            )
            motivos: list[str] = []
        else:
            arr = np.array(out.convert("RGB"), dtype=np.uint8, copy=True)
            corrigidas = _correct_seams(arr, content)
            if corrigidas:
                out = Image.fromarray(arr, "RGB")
                info.setdefault("seams_fixed", []).extend(corrigidas)
            motivos = _validate_generated(np.asarray(out.convert("RGB")), content, bands)
        if not motivos:
            n, _bbox = _protect.drift_report(base, out, bands)
            info["drift_pixels"] = int(n)
            info["content_intact"] = bool(n == 0)
            info["engine"] = str(gen.info.get("s7_engine") or "ai")
            info["cost_usd"] = round(custo, 4)
            info["attempts"] = tentativa
            if n:      # não deveria acontecer: protected_composite garante 0
                info["warnings"].append(
                    f"{n} pixel(s) mudaram fora das faixas geradas; isso é um bug, reporte"
                )
            return out
        info["warnings"].append(
            f"tentativa {tentativa} de extensão rejeitada: " + "; ".join(motivos)
        )
    info["cost_usd"] = round(custo, 4)
    info["attempts"] = OUTPAINT_MAX_ATTEMPTS
    return None


def _do_outpaint(src: Image.Image, dst_w: int, dst_h: int, settings: Any,
                 prompt: str | None, fill: Any, palette: Sequence[Any] | None,
                 info: dict[str, Any]) -> tuple[Image.Image, dict[str, Any]]:
    content, scale = plan_placement(src.width, src.height, dst_w, dst_h)
    info["scale"] = round(scale, 6)

    base, fill_label = build_background(src, dst_w, dst_h, fill=fill,
                                        content=content, palette=palette)
    base.paste(src.resize((content.w, content.h), Image.Resampling.LANCZOS),
               (content.x, content.y))
    info["fill"] = fill_label

    if content.w == dst_w and content.h == dst_h:
        info["mode"] = "pad"
        info["engine"] = "deterministic"
        info["notes"] = "não havia área nova para estender: só reescala uniforme"
        return _finish(base, src, info, content)

    if _ai_available(settings, info, motivo="o modo outpaint"):
        out = _outpaint_background(base, src, content, dst_w, dst_h, settings, prompt, info)
        if out is not None:
            info["notes"] = (f"cena estendida por IA nas faixas laterais; original recolado "
                             f"em {content.w}x{content.h} (drift {info['drift_pixels']})")
            return _finish(out, src, info, content)

    info["mode"] = "pad"
    info["engine"] = "deterministic"
    info["notes"] = f"extensão por IA indisponível/reprovada; moldura '{fill_label}' aplicada"
    return _finish(base, src, info, content)


# --------------------------------------------------------------------------- #
def _erase_blocks(src: Image.Image, planos: Sequence[BlockPlan],
                  settings: Any, info: dict[str, Any]) -> Image.Image:
    """Apaga do original os blocos que serão redesenhados no novo formato."""
    from . import textedit as _textedit

    limpo = src
    for p in planos:
        rep: dict[str, Any] = {}
        try:
            limpo, _changed = _textedit.remove_text(limpo, p.block, settings=settings, report=rep)
        except Exception as exc:
            info["warnings"].append(
                f"não consegui apagar o bloco {getattr(p.block.role, 'value', '?')}: {exc}"
            )
            continue
        for w in rep.get("warnings", []):
            if w not in info["warnings"]:
                info["warnings"].append(w)
    return limpo


def _in_container(block: Any, analysis: CreativeAnalysis) -> bool:
    """O texto está dentro de uma faixa/selo de cor própria, e não sobre o fundo?

    O critério é a cor: o fundo local do bloco destoar do fundo geral da peça
    significa que existe um retângulo colorido em volta dele. ``on_solid_background``
    sozinho não serve — ele é True também para texto sobre um fundo chapado
    comum, que é justamente o que PODE ser reposicionado.
    """
    cor = getattr(block, "background_color", None)
    if cor is None:
        return False
    fundos = [b.background_color for b in analysis.text_blocks if b.background_color]
    if not fundos:
        return False
    # Fundo da peça = a cor de fundo mais repetida entre os blocos.
    contagem: dict[tuple[int, int, int], int] = {}
    for c in fundos:
        chave = tuple(int(v) for v in c[:3])
        contagem[chave] = contagem.get(chave, 0) + 1
    pagina = max(contagem.items(), key=lambda kv: kv[1])[0]
    return _delta_rgb(tuple(int(v) for v in cor[:3]), pagina) >= 40.0


def _delta_rgb(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """Distância euclidiana simples em RGB — basta para separar rosa de quase-preto."""
    return float(sum((int(x) - int(y)) ** 2 for x, y in zip(a, b)) ** 0.5)


def _do_relayout(src: Image.Image, dst_w: int, dst_h: int, settings: Any,
                 analysis: CreativeAnalysis | None, prompt: str | None, fill: Any,
                 palette: Sequence[Any] | None,
                 info: dict[str, Any]) -> tuple[Image.Image, dict[str, Any]]:
    if analysis is None:
        info["warnings"].append(
            "o modo relayout precisa de uma análise do criativo (onde está cada texto) e "
            "nenhuma foi passada; caí para o modo pad. "
            "Rode `s7 inspect` antes, ou passe analysis=vision.analyze_creative(...)."
        )
        img_out, info = _do_pad(src, dst_w, dst_h, fill, palette, info)
        info["mode"] = "pad"
        return (img_out, info)

    content, scale = plan_placement(src.width, src.height, dst_w, dst_h)
    info["scale"] = round(scale, 6)

    if (content.w, content.h) == (dst_w, dst_h) and abs(scale - 1.0) < 1e-9:
        # Mesmo formato e mesma resolução: apagar e redesenhar o texto só
        # degradaria a peça de graça.
        info["notes"] = "o formato já era o alvo: nada a reposicionar"
        info["engine"] = "deterministic"
        info["mode"] = "pad"
        return _finish(src.copy(), src, info, content)

    # Texto que mora dentro de um contêiner gráfico (faixa de CTA, selo de
    # preço) NÃO pode ser reposicionado: o contêiner é fundo, ele acompanha o
    # reenquadramento, e mover só a letra separa uma da outra — a peça sai com
    # uma tarja rosa vazia no meio e o "GARANTA O SEU" solto num canto.
    # Reposicionamos apenas o texto que flutua sobre o fundo da própria peça.
    presos = [b for b in analysis.text_blocks if _in_container(b, analysis)]
    if presos:
        livres = [b for b in analysis.text_blocks if b not in presos]
        analysis = replace(analysis, text_blocks=livres)
        info["warnings"].append(
            f"{len(presos)} bloco(s) ficaram onde estavam por viverem dentro de faixa/selo "
            "colorido (mover o texto sem mover o contêiner quebraria a peça)")

    planos, region, politica, warns = plan_relayout(analysis, dst_w, dst_h,
                                                    content=content, scale=scale)
    info["warnings"].extend(warns)
    info["layout_policy"] = politica
    info["stack_region"] = region.to_dict() if region.area else None

    if not planos:
        info["warnings"].append("nenhum bloco de texto pôde ser reposicionado; entreguei o modo pad")
        img_out, info = _do_pad(src, dst_w, dst_h, fill, palette, info)
        info["mode"] = "pad"
        info["layout_policy"] = politica
        return (img_out, info)

    # 1) apagar o texto AINDA no original (fundo em resolução nativa)
    limpo = _erase_blocks(src, planos, settings, info)

    # 2) estender só o fundo para o novo formato
    base, fill_label = build_background(limpo, dst_w, dst_h, fill=fill,
                                        content=content, palette=palette)
    base.paste(limpo.resize((content.w, content.h), Image.Resampling.LANCZOS),
               (content.x, content.y))
    info["fill"] = fill_label
    canvas = base
    if generated_bands(content, dst_w, dst_h) and _ai_available(
            settings, info, motivo="a extensão de fundo do relayout"):
        out = _outpaint_background(base, limpo, content, dst_w, dst_h, settings, prompt, info)
        if out is not None:
            canvas = out
    if canvas is base:
        info["engine"] = "deterministic"

    # 3) redesenhar o texto nas posições novas
    from . import textedit as _textedit

    desenhados = 0
    for p in planos:
        rep: dict[str, Any] = {}
        try:
            canvas, changed = _textedit.add_text(canvas, p.new_box, p.block.text, p.spec,
                                                 autofit=True, report=rep)
        except Exception as exc:
            info["warnings"].append(
                f"não consegui redesenhar o bloco {getattr(p.block.role, 'value', '?')}: {exc}"
            )
            continue
        for w in rep.get("warnings", []):
            if w not in info["warnings"]:
                info["warnings"].append(w)
        if changed.area > 0:
            desenhados += 1
        else:
            p.note = (p.note + "; " if p.note else "") + "não coube"

    info["text_blocks"] = [p.to_dict() for p in planos]
    info["notes"] = (f"relayout {politica}: {desenhados}/{len(planos)} blocos reposicionados, "
                     f"corpo de fonte reescalado por {scale:.2f}")
    if desenhados < len(planos):
        info["warnings"].append(
            f"{len(planos) - desenhados} bloco(s) não couberam na nova posição; "
            "aumente a região da pilha ou encurte a copy"
        )
    # O drift medido antes do texto não vale mais: o texto foi desenhado por cima
    # de propósito, inclusive dentro do conteúdo.
    info["drift_pixels"] = None
    info["content_intact"] = None
    return _finish(canvas, src, info, content)


# --------------------------------------------------------------------------- #
# Teste de fumaça — `python -m s7editor.reframe`
# --------------------------------------------------------------------------- #
def _demo(w: int = 1080, h: int = 1920) -> tuple[Image.Image, CreativeAnalysis]:
    """Criativo sintético 9:16: degradê, faixa de CTA e um 'produto'."""
    from PIL import ImageDraw

    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None]
    xx = np.linspace(0, 1, w, dtype=np.float32)[None, :]
    arr = np.dstack([
        (30 + 180 * yy + 20 * xx) * np.ones((h, w), np.float32),
        (40 + 60 * yy) * np.ones((h, w), np.float32),
        (120 - 40 * yy + 40 * xx) * np.ones((h, w), np.float32),
    ])
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    d.ellipse((340, 700, 740, 1100), fill=(240, 230, 200))          # "produto"
    d.rectangle((140, 1500, 940, 1640), fill=(255, 60, 90))          # pastilha do CTA
    d.text((300, 1550), "COMPRE AGORA", fill=(255, 255, 255))
    d.text((160, 300), "OFERTA DO DIA", fill=(255, 255, 255))

    analysis = CreativeAnalysis(
        path=__import__("pathlib").Path("demo.png"), width=w, height=h,
        text_blocks=[
            TextBlock(box=Box(140, 260, 800, 120), text="OFERTA DO DIA",
                      role=TextRole.HEADLINE,
                      style=FontSpec(size_px=96, color=(255, 255, 255), align="left")),
            TextBlock(box=Box(140, 1500, 800, 140), text="COMPRE AGORA", role=TextRole.CTA,
                      style=FontSpec(size_px=72, color=(255, 255, 255), align="center"),
                      background_color=(255, 60, 90), on_solid_background=True),
        ],
        palette=[(255, 60, 90), (30, 40, 120)],
        safe_areas=[Box(340, 700, 400, 400)],
        source="manual",
    )
    return (img, analysis)


def _smoke_test() -> int:
    """Prova a promessa central: 9:16 -> 16:9 sem esticar nada."""
    falhas: list[str] = []
    img, analysis = _demo()

    out, info = reframe(img, "16:9", mode="pad", fill="blur")
    if out.size != (1920, 1080):
        falhas.append(f"tamanho de saída {out.size}, esperado (1920, 1080)")
    cb = Box(**{k: info["content_box"][k] for k in ("x", "y", "w", "h")})
    if abs(cb.w / cb.h - 1080 / 1920) > 0.002:
        falhas.append(f"razão do conteúdo {cb.w / cb.h:.5f}, esperado {1080 / 1920:.5f}")
    if (cb.w, cb.h) != (608, 1080):
        falhas.append(f"caixa do conteúdo {cb.w}x{cb.h}, esperado 608x1080")
    if not info["aspect_preserved"]:
        falhas.append("aspect_preserved=False no modo pad")
    # o conteúdo colado tem que ser exatamente o resize_contain do original
    esperado = np.asarray(img.resize((cb.w, cb.h), Image.Resampling.LANCZOS), dtype=np.uint8)
    obtido = np.asarray(out.convert("RGB"))[cb.y:cb.y1, cb.x:cb.x1]
    if not np.array_equal(esperado, obtido):
        falhas.append("o conteúdo colado não é o original reescalado uniformemente")
    if info["generated_fraction"] < 0.6:
        falhas.append(f"fração gerada {info['generated_fraction']} — esperado ~0.68")

    # determinismo: rodar duas vezes dá o mesmo arquivo
    out2, _ = reframe(img, "16:9", mode="pad", fill="blur")
    if not np.array_equal(np.asarray(out.convert("RGB")), np.asarray(out2.convert("RGB"))):
        falhas.append("modo pad não é determinístico")

    for f in ("mirror", "color", "white", "black", "#112233"):
        o, i = reframe(img, "16:9", mode="pad", fill=f)
        if o.size != (1920, 1080):
            falhas.append(f"fill={f}: tamanho {o.size}")

    # 1:1 e 4:5 (alvo mais alto que largo continua sendo contain)
    o11, i11 = reframe(img, "1:1", mode="pad")
    if o11.size != (1920, 1920):
        falhas.append(f"1:1 deu {o11.size}")

    # crop consciente: o recorte tem que preservar CTA e área segura melhor que o centro
    oc, ic = reframe(img, "16:9", mode="crop", analysis=analysis)
    if oc.size != (1920, 1080):
        falhas.append(f"crop deu {oc.size}")
    sc = ic["source_crop"]
    if sc["w"] != 1080 or abs(sc["h"] - 608) > 1:
        falhas.append(f"recorte {sc} — esperado 1080x608")
    if not ic["cut"]:
        falhas.append("crop de 9:16 para 16:9 deveria reportar o que cortou")

    # outpaint sem chave: degrada para pad com aviso, não explode
    from . import config as _config
    st = replace(_config.load_settings(), openai_api_key=None, dry_run=False)
    oo, io = reframe(img, "16:9", mode="outpaint", settings=st)
    if oo.size != (1920, 1080) or io["mode"] != "pad":
        falhas.append(f"outpaint sem chave deveria cair para pad, veio {io['mode']}")
    if not any("OPENAI_API_KEY" in w for w in io["warnings"]):
        falhas.append("outpaint sem chave não explicou como configurar a chave")

    # as faixas geradas têm que particionar exatamente o complemento do conteúdo
    bands = generated_bands(cb, 1920, 1080)
    if sum(b.area for b in bands) != 1920 * 1080 - cb.area:
        falhas.append("generated_bands não cobre exatamente o complemento do conteúdo")
    for i_, a in enumerate(bands):
        for b in bands[i_ + 1:]:
            if a.intersects(b):
                falhas.append("generated_bands devolveu faixas sobrepostas")

    # outpaint em dry-run: exercita a recolagem protegida sem gastar crédito
    st_dry = replace(_config.load_settings(), openai_api_key=None, dry_run=True)
    od, iod = reframe(img, "16:9", mode="outpaint", settings=st_dry)
    if od.size != (1920, 1080):
        falhas.append(f"outpaint dry-run deu {od.size}")
    if iod["drift_pixels"] != 0 or iod["content_intact"] is not True:
        falhas.append(f"outpaint dry-run mexeu fora das faixas geradas: {iod['drift_pixels']}")
    if iod["cost_usd"] != 0.0:
        falhas.append("dry-run não pode custar nada")
    dcb = Box(**{k: iod["content_box"][k] for k in ("x", "y", "w", "h")})
    esperado_d = np.asarray(img.resize((dcb.w, dcb.h), Image.Resampling.LANCZOS), dtype=np.uint8)
    if not np.array_equal(esperado_d, np.asarray(od.convert("RGB"))[dcb.y:dcb.y1, dcb.x:dcb.x1]):
        falhas.append("o outpaint não recolou o original nativo no centro")

    # relayout offline: apaga, estende por pad e redesenha
    orl, irl = reframe(img, "16:9", mode="relayout", settings=st, analysis=analysis)
    if orl.size != (1920, 1080):
        falhas.append(f"relayout deu {orl.size}")
    if irl["mode"] != "relayout" or not irl["text_blocks"]:
        falhas.append("relayout não reposicionou bloco nenhum")
    else:
        for tb in irl["text_blocks"]:
            nb = tb["para"]
            if nb["x"] < 0 or nb["y"] < 0 or nb["x"] + nb["w"] > 1920 or nb["y"] + nb["h"] > 1080:
                falhas.append(f"bloco reposicionado para fora da tela: {nb}")

    # relayout sem análise: avisa e cai para pad
    _, irl2 = reframe(img, "16:9", mode="relayout", settings=st)
    if irl2["mode"] != "pad":
        falhas.append("relayout sem análise deveria cair para pad")

    # erros de uso: mensagem em português, não traceback
    try:
        reframe(img, "16:9", mode="banana")
        falhas.append("modo inválido não levantou erro")
    except ValueError as exc:
        if "banana" not in str(exc):
            falhas.append("mensagem de modo inválido não cita o modo")
    try:
        reframe(img, "dezesseis por nove")
        falhas.append("formato inválido não levantou erro")
    except ValueError:
        pass

    if falhas:
        print("FALHOU:")
        for f in falhas:
            print("  -", f)
        return 1
    print(f"reframe ok — 9:16 {img.size} -> 16:9 {out.size}, conteúdo em "
          f"{cb.w}x{cb.h} (razão {cb.w / cb.h:.5f}), {info['generated_fraction'] * 100:.0f}% gerado, "
          f"cv2={'sim' if HAS_CV2 else 'não'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(_smoke_test())
