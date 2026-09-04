#!/usr/bin/env python3
"""Gera criativos sintéticos 1080x1920 (9:16) para os testes do S7 Editor.

Por que existir
---------------
A suíte tem que provar a "garantia de zero drift" OFFLINE, sem chave de API e
sem depender de material do cliente. Estes fixtures parecem anúncio de verdade
(headline, subhead, selo de preço, CTA em faixa colorida) e — mais importante —
vêm com um **manifesto** (``fixtures.json``) que diz a caixa exata de cada
bloco de texto. Assim o teste sabe onde é o CTA sem precisar de OCR nem de IA,
e pode afirmar "fora desta caixa nada mudou".

Determinismo
------------
Tudo sai de ``numpy.random.default_rng(seed + índice)``: rodar duas vezes com a
mesma semente gera arquivos byte a byte idênticos. Isso é o que permite cachear
os fixtures entre execuções do pytest.

Uso
---
    python tools/make_fixtures.py                    # -> tests/fixtures/
    python tools/make_fixtures.py --out /tmp/f --count 10 --seed 3
    python tools/make_fixtures.py --force            # regera mesmo se já existe

Saída
-----
    <out>/criativo-01.png ... criativo-30.png    (lote padrão, layout fixo)
    <out>/dificeis/dificil-1-cta-sobre-foto.png  (CTA sobre textura)
    <out>/dificeis/dificil-2-cta-degrade.png     (CTA sobre degradê)
    <out>/dificeis/dificil-3-claro-sobre-claro.png (texto claro em fundo claro)
    <out>/fixtures.json                          (manifesto com as caixas)

Os casos difíceis ficam numa subpasta de propósito: assim ``list_images`` sem
``recursive`` devolve exatamente os 30 do lote padrão.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
from PIL import Image, ImageDraw, ImageFont

__all__ = [
    "FIXTURE_VERSION", "WIDTH", "HEIGHT", "DEFAULT_COUNT", "DEFAULT_SEED",
    "LAYOUT", "CTA_TEXT", "build_fixtures", "ensure_fixtures", "load_manifest",
    "main",
]

# --------------------------------------------------------------------------- #
# Constantes do lote
# --------------------------------------------------------------------------- #
FIXTURE_VERSION = 3          # mude quando o desenho mudar: invalida o cache
WIDTH, HEIGHT = 1080, 1920
DEFAULT_COUNT = 30
DEFAULT_SEED = 7
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
HARD_SUBDIR = "dificeis"
MANIFEST_NAME = "fixtures.json"

#: Todos os 30 criativos do lote padrão usam o MESMO CTA — é o caso central do
#: produto ("trocar o CTA de 30 imagens"), e deixa o teste por `find` viável.
CTA_TEXT = "GARANTA O SEU"

#: Caixas fixas do layout (pixels, 1080x1920). O layout é o mesmo nos 30 para
#: que a caixa normalizada do CTA seja idêntica em todos.
LAYOUT: dict[str, tuple[int, int, int, int]] = {
    "logo":     (96, 150, 520, 54),
    "headline": (96, 320, 888, 340),
    "subhead":  (96, 700, 888, 190),
    "price":    (664, 1140, 320, 168),
    "cta":      (200, 1606, 680, 96),
    "legal":    (96, 1806, 888, 44),
}
#: Faixa colorida do rodapé onde o CTA mora (nos 30 padrão).
CTA_BAR = (0, 1544, WIDTH, 220)
#: Folga mínima entre a tinta e a borda da caixa declarada, em px. É essa folga
#: que garante que apagar/redesenhar dentro da caixa não corta glifo.
INK_PAD = 10


# --------------------------------------------------------------------------- #
# Fontes — resolvidas por caminho explícito para não depender de fontconfig
# --------------------------------------------------------------------------- #
_FONT_DIRS = (
    Path(__file__).resolve().parent.parent / "assets" / "fonts",
    Path(__file__).resolve().parent.parent / "fonts",
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype/freefont"),
    Path("/usr/share/fonts/truetype"),
    Path("/usr/share/fonts"),
    Path("/Library/Fonts"),
    Path("C:/Windows/Fonts"),
)
_FONT_CANDIDATES: dict[str, tuple[str, ...]] = {
    "bold": ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "FreeSansBold.ttf",
             "Arial Bold.ttf", "arialbd.ttf"),
    "regular": ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf",
                "Arial.ttf", "arial.ttf"),
}
_font_path_cache: dict[str, Path | None] = {}
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font_path(weight: str) -> Path | None:
    """Primeiro arquivo existente da lista de candidatos, em ordem de preferência."""
    if weight in _font_path_cache:
        return _font_path_cache[weight]
    achado: Path | None = None
    for nome in _FONT_CANDIDATES[weight]:
        for d in _FONT_DIRS:
            p = d / nome
            if p.is_file():
                achado = p
                break
            # varredura rasa em subpastas (o Debian espalha por família)
            if d.is_dir():
                for sub in sorted(d.glob(f"*/{nome}")):
                    achado = sub
                    break
            if achado:
                break
        if achado:
            break
    _font_path_cache[weight] = achado
    return achado


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    """Fonte TrueType no corpo pedido; cai na embutida do Pillow se não achar nada."""
    size = max(6, int(size))
    key = (weight, size)
    if key not in _font_cache:
        p = _font_path(weight)
        if p is not None:
            _font_cache[key] = ImageFont.truetype(str(p), size)
        else:  # pragma: no cover - só em máquina sem nenhuma fonte instalada
            _font_cache[key] = ImageFont.load_default(size=size)
    return _font_cache[key]


def font_family_name(weight: str = "bold") -> str:
    """Nome da família usada, no formato que ``s7editor.fonts`` entende."""
    p = _font_path(weight)
    if p is None:  # pragma: no cover
        return "Inter"
    return p.stem.split("-")[0]


# --------------------------------------------------------------------------- #
# Paletas e copy (pt-BR)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Palette:
    name: str
    bg_top: tuple[int, int, int]
    bg_bottom: tuple[int, int, int]
    ink: tuple[int, int, int]
    accent: tuple[int, int, int]
    accent_ink: tuple[int, int, int]
    badge: tuple[int, int, int]
    badge_ink: tuple[int, int, int]


PALETTES: tuple[Palette, ...] = (
    Palette("noite",    (18, 20, 32),    (10, 12, 22),   (245, 246, 250),
            (255, 46, 136), (255, 255, 255), (255, 214, 64), (24, 20, 10)),
    Palette("oceano",   (14, 58, 92),    (7, 30, 52),    (238, 246, 252),
            (0, 200, 180),  (6, 32, 40),     (255, 255, 255), (14, 58, 92)),
    Palette("areia",    (240, 233, 220), (222, 210, 190), (38, 33, 28),
            (198, 60, 40),  (255, 248, 240), (38, 33, 28),   (240, 233, 220)),
    Palette("floresta", (22, 60, 44),    (11, 34, 26),   (236, 246, 238),
            (168, 224, 96), (14, 38, 18),    (255, 255, 255), (22, 60, 44)),
    Palette("uva",      (52, 24, 84),    (28, 12, 48),   (243, 236, 252),
            (255, 122, 46), (26, 12, 4),     (255, 255, 255), (52, 24, 84)),
    Palette("carvao",   (32, 32, 34),    (18, 18, 20),   (250, 250, 250),
            (0, 122, 255),  (255, 255, 255), (255, 255, 255), (24, 24, 26)),
)

HEADLINES: tuple[str, ...] = (
    "SUA MARCA NO TOPO DO FEED",
    "30 CRIATIVOS EM 5 MINUTOS",
    "PARE DE REFAZER ANUNCIO NA MAO",
    "O MESMO LAYOUT EM TODO FORMATO",
    "TROQUE O CTA DE 30 PECAS",
    "LOTE PRONTO PARA SUBIR HOJE",
    "MAIS TESTE, MENOS RETRABALHO",
    "SEU TIME CRIATIVO NO PILOTO",
    "DO 9:16 AO 16:9 SEM DISTORCER",
    "VARIACOES QUE MANTEM A MARCA",
)
SUBHEADS: tuple[str, ...] = (
    "Edicao em lote com garantia de pixel intacto",
    "Voce muda o texto, o resto continua igual",
    "Adaptacao de formato sem esticar nada",
    "Trinta pecas, uma receita, zero retrabalho",
    "Aprovado pelo time de performance",
)
PRICES: tuple[str, ...] = ("R$ 97", "R$ 149", "12x R$ 39", "R$ 249", "R$ 47")
LEGAL: tuple[str, ...] = (
    "Oferta valida enquanto durarem as vagas.",
    "Consulte condicoes no site oficial.",
    "Imagens meramente ilustrativas.",
)
BRANDS: tuple[str, ...] = ("S7 STRATEGY", "S7 STUDIO", "S7 PERFORMANCE")


# --------------------------------------------------------------------------- #
# Fundos
# --------------------------------------------------------------------------- #
def _solid(w: int, h: int, color: tuple[int, int, int]) -> np.ndarray:
    return np.full((h, w, 3), np.array(color, np.uint8), np.uint8)


def _gradient(w: int, h: int, top: tuple[int, int, int],
              bottom: tuple[int, int, int]) -> np.ndarray:
    """Degradê vertical linear puro — reconstrutível por mínimos quadrados."""
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    a = np.array(top, np.float32)[None, :]
    b = np.array(bottom, np.float32)[None, :]
    col = a + (b - a) * t                      # (h, 3)
    return np.repeat(col[:, None, :], w, axis=1).round().clip(0, 255).astype(np.uint8)


def _photo(w: int, h: int, pal: Palette, rng: np.random.Generator) -> np.ndarray:
    """'Foto' sintética: degradê + blobs radiais + faixas + grão.

    Não é fotografia, mas tem o que importa para o classificador: sem cor
    dominante, resíduo alto no ajuste de plano e ruído de alta frequência.
    """
    base = _gradient(w, h, pal.bg_top, pal.bg_bottom).astype(np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)

    for _ in range(5):
        cx = rng.uniform(0.0, w)
        cy = rng.uniform(0.0, h)
        r = rng.uniform(0.18, 0.55) * max(w, h)
        cor = np.array([rng.uniform(30, 235) for _ in range(3)], np.float32)
        peso = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * r * r)))
        base += (cor[None, None, :] - base) * (peso[..., None] * rng.uniform(0.25, 0.6))

    # Detalhe pequeno e denso: é ISTO que separa "foto" de "degradê" no
    # classificador — o resíduo do ajuste quadrático sobe acima do piso de
    # ruído. Com poucos blobs grandes o patch continua sendo um degradê.
    for _ in range(90):
        cx, cy = rng.uniform(0.0, w), rng.uniform(0.0, h)
        r = rng.uniform(0.01, 0.05) * max(w, h)
        cor = np.array([rng.uniform(20, 245) for _ in range(3)], np.float32)
        peso = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2.0 * r * r)))
        base += (cor[None, None, :] - base) * (peso[..., None] * rng.uniform(0.35, 0.8))

    # faixas diagonais suaves: dão estrutura sem virar padrão periódico forte
    ang = rng.uniform(0.3, 1.2)
    faixa = np.sin((xx * np.cos(ang) + yy * np.sin(ang)) / rng.uniform(20.0, 60.0))
    base += faixa[..., None] * rng.uniform(6.0, 14.0)

    base += rng.normal(0.0, 7.0, base.shape)   # grão
    return base.clip(0, 255).astype(np.uint8)


def _texture_overlay(img: Image.Image, rng: np.random.Generator, *, amp: float = 20.0,
                     cell: int = 14) -> None:
    """Soma textura coerente de escala ~``cell`` px sobre a imagem inteira.

    Ruído branco não vira "foto" para o classificador (ele estima o piso de
    ruído e o desconta). Textura com estrutura, sim: é ela que faz o resíduo do
    ajuste de superfície subir e a caixa ser classificada como PHOTO.
    """
    w, h = img.size
    gh, gw = max(2, h // cell), max(2, w // cell)
    # ruído sobretudo de luminância (como grão de filme), com pouca crominância
    luz = rng.normal(0.0, 1.0, (gh, gw, 1))
    pequeno = luz + 0.3 * rng.normal(0.0, 1.0, (gh, gw, 3))
    campo = np.asarray(
        Image.fromarray(((pequeno * 40 + 128).clip(0, 255)).astype(np.uint8), "RGB")
        .resize((w, h), Image.Resampling.BICUBIC), np.float32) - 128.0
    arr = np.asarray(img).astype(np.float32) + campo * (amp / 40.0)
    img.paste(Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGB"), (0, 0))


def _scrim(img: Image.Image, until: float = 0.58, strength: float = 0.55) -> None:
    """Escurece o topo da imagem em rampa — é como todo anúncio real garante
    leitura de headline sobre foto. Aplicado in-place."""
    arr = np.asarray(img).astype(np.float32)
    h = arr.shape[0]
    t = np.clip(1.0 - np.arange(h, dtype=np.float32) / (until * h), 0.0, 1.0)
    arr *= (1.0 - strength * t)[:, None, None]
    img.paste(Image.fromarray(arr.clip(0, 255).astype(np.uint8), "RGB"), (0, 0))


# --------------------------------------------------------------------------- #
# Texto
# --------------------------------------------------------------------------- #
def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: float) -> list[str]:
    """Quebra gulosa por palavras (first-fit)."""
    palavras = text.split()
    linhas: list[str] = []
    atual = ""
    for p in palavras:
        cand = f"{atual} {p}".strip()
        if atual and font.getlength(cand) > max_w:
            linhas.append(atual)
            atual = p
        else:
            atual = cand
    if atual:
        linhas.append(atual)
    return linhas or [""]


def _ink_mask(text: str, weight: str, size: int, max_w: int,
              align: str, line_gap: float) -> tuple[Image.Image, tuple[int, int, int, int]] | None:
    """Máscara 'L' recortada na tinta + (l, t, r, b) dentro dela.

    Renderiza numa folha com folga e recorta pela bbox real dos glifos: é o
    jeito de garantir que a tinta cabe na caixa declarada (nada de estimar por
    métricas da fonte, que erram em acentos e descendentes).
    """
    font = _font(weight, size)
    linhas = _wrap(text, font, max_w)
    pad = size * 2 + 40
    largura = int(max(max_w, max(font.getlength(l) for l in linhas)) + 2 * pad)
    altura = int(len(linhas) * (size * line_gap) + 2 * pad)
    folha = Image.new("L", (largura, altura), 0)
    d = ImageDraw.Draw(folha)
    passo = size * line_gap
    for i, linha in enumerate(linhas):
        y = pad + i * passo
        if align == "center":
            x = pad + max_w / 2.0
            anchor = "ma"
        elif align == "right":
            x = pad + max_w
            anchor = "ra"
        else:
            x = pad
            anchor = "la"
        d.text((x, y), linha, font=font, fill=255, anchor=anchor)
    bbox = folha.getbbox()
    if bbox is None:
        return None
    return folha.crop(bbox), bbox


def draw_text_in_box(img: Image.Image, box: tuple[int, int, int, int], text: str, *,
                     weight: str = "bold", size: int = 64,
                     color: tuple[int, int, int] = (255, 255, 255),
                     align: str = "center", line_gap: float = 1.18,
                     pad: int = INK_PAD) -> dict[str, Any]:
    """Desenha ``text`` centralizado na caixa, reduzindo o corpo até a tinta caber.

    Devolve os metadados do bloco (corpo final, caixa da tinta) para o manifesto.
    A tinta fica garantidamente a ``pad`` px das bordas da caixa — quem for
    apagar essa caixa depois não corta glifo nenhum.
    """
    bx, by, bw, bh = box
    livre_w, livre_h = bw - 2 * pad, bh - 2 * pad
    if livre_w <= 0 or livre_h <= 0:
        raise ValueError(f"caixa pequena demais para texto: {box}")

    corpo = int(size)
    recorte = None
    while corpo >= 8:
        r = _ink_mask(text, weight, corpo, livre_w, align, line_gap)
        if r is not None:
            mask, _ = r
            if mask.width <= livre_w and mask.height <= livre_h:
                recorte = mask
                break
        corpo = max(8, int(corpo * 0.94)) if corpo > 8 else corpo - 1
    if recorte is None:  # pragma: no cover - só com caixa absurda
        raise ValueError(f"não consegui encaixar {text!r} em {box}")

    ox = bx + (bw - recorte.width) // 2
    oy = by + (bh - recorte.height) // 2
    img.paste(Image.new("RGB", recorte.size, color), (ox, oy), recorte)
    return {
        "size_px": corpo,
        "ink_box": {"x": int(ox), "y": int(oy), "w": int(recorte.width), "h": int(recorte.height)},
        "weight": weight,
        "align": align,
    }


# --------------------------------------------------------------------------- #
# Montagem de um criativo
# --------------------------------------------------------------------------- #
@dataclass
class BlockSpec:
    """Um bloco escrito num criativo, do jeito que o manifesto guarda."""

    role: str
    box: tuple[int, int, int, int]
    text: str
    color: tuple[int, int, int]
    background_color: tuple[int, int, int] | None
    on_solid_background: bool
    background_kind: str
    size_px: int = 0
    weight: str = "bold"
    align: str = "center"
    ink_box: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        x, y, w, h = self.box
        return {
            "role": self.role,
            "box": {"x": x, "y": y, "w": w, "h": h},
            "box_norm": {"x": round(x / WIDTH, 6), "y": round(y / HEIGHT, 6),
                         "w": round(w / WIDTH, 6), "h": round(h / HEIGHT, 6), "norm": True},
            "text": self.text,
            "color": list(self.color),
            "background_color": list(self.background_color) if self.background_color else None,
            "on_solid_background": self.on_solid_background,
            "background_kind": self.background_kind,
            "size_px": self.size_px,
            "weight": self.weight,
            "align": self.align,
            "ink_box": self.ink_box,
        }


def _pick(seq: Sequence[Any], i: int) -> Any:
    return seq[i % len(seq)]


def _bg_kind_for(index: int) -> str:
    """Cicla os três fundos: chapado, degradê, foto."""
    return ("solid", "gradient", "photo")[index % 3]


def _canvas(kind: str, pal: Palette, rng: np.random.Generator) -> Image.Image:
    if kind == "solid":
        arr = _solid(WIDTH, HEIGHT, pal.bg_top)
    elif kind == "gradient":
        arr = _gradient(WIDTH, HEIGHT, pal.bg_top, pal.bg_bottom)
    else:
        arr = _photo(WIDTH, HEIGHT, pal, rng)
    return Image.fromarray(arr, "RGB")


def _bar(img: Image.Image, rect: tuple[int, int, int, int],
         color: tuple[int, int, int], radius: int = 0) -> None:
    d = ImageDraw.Draw(img)
    x, y, w, h = rect
    if radius:
        d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=radius, fill=color)
    else:
        d.rectangle([x, y, x + w - 1, y + h - 1], fill=color)


def build_creative(index: int, seed: int = DEFAULT_SEED) -> tuple[Image.Image, list[BlockSpec], dict[str, Any]]:
    """Monta o criativo ``index`` do lote padrão.

    Layout fixo (as caixas de LAYOUT), fundo e copy variando por índice. O CTA
    fica sempre numa faixa chapada no rodapé: é o caso que o produto promete
    resolver com precisão de pixel.
    """
    rng = np.random.default_rng(seed * 1000 + index)
    pal = _pick(PALETTES, index)
    kind = _bg_kind_for(index)
    img = _canvas(kind, pal, rng)
    # Sobre foto o texto de marca é sempre claro, com scrim por baixo: é assim
    # que o criativo real garante leitura, e é o caso que exige inpaint.
    ink = pal.ink
    if kind == "photo":
        _scrim(img)
        ink = (255, 255, 255)

    blocos: list[BlockSpec] = []

    # faixa do CTA (sempre chapada) + selo de preço (pastilha chapada)
    _bar(img, CTA_BAR, pal.accent)
    price_box = LAYOUT["price"]
    pill = (price_box[0] - 24, price_box[1] - 20, price_box[2] + 48, price_box[3] + 40)
    _bar(img, pill, pal.badge, radius=28)

    # ---- logo / eyebrow -------------------------------------------------- #
    meta = draw_text_in_box(img, LAYOUT["logo"], _pick(BRANDS, index),
                            weight="bold", size=40, color=ink, align="left")
    blocos.append(BlockSpec("logo", LAYOUT["logo"], _pick(BRANDS, index), ink,
                            pal.bg_top if kind == "solid" else None,
                            kind == "solid", kind, meta["size_px"], "bold", "left", meta["ink_box"]))

    # ---- headline --------------------------------------------------------- #
    head = _pick(HEADLINES, index)
    meta = draw_text_in_box(img, LAYOUT["headline"], head, weight="bold", size=96,
                            color=ink, align="left", line_gap=1.1)
    blocos.append(BlockSpec("headline", LAYOUT["headline"], head, ink,
                            pal.bg_top if kind == "solid" else None,
                            kind == "solid", kind, meta["size_px"], "bold", "left", meta["ink_box"]))

    # ---- subhead ---------------------------------------------------------- #
    sub = _pick(SUBHEADS, index)
    meta = draw_text_in_box(img, LAYOUT["subhead"], sub, weight="regular", size=48,
                            color=ink, align="left", line_gap=1.25)
    blocos.append(BlockSpec("subhead", LAYOUT["subhead"], sub, ink,
                            pal.bg_top if kind == "solid" else None,
                            kind == "solid", kind, meta["size_px"], "regular", "left", meta["ink_box"]))

    # ---- preço (sobre pastilha chapada) ----------------------------------- #
    preco = _pick(PRICES, index)
    meta = draw_text_in_box(img, price_box, preco, weight="bold", size=64,
                            color=pal.badge_ink, align="center")
    blocos.append(BlockSpec("price", price_box, preco, pal.badge_ink, pal.badge,
                            True, "solid", meta["size_px"], "bold", "center", meta["ink_box"]))

    # ---- CTA (sobre faixa chapada) — o bloco que os testes editam ---------- #
    meta = draw_text_in_box(img, LAYOUT["cta"], CTA_TEXT, weight="bold", size=64,
                            color=pal.accent_ink, align="center")
    blocos.append(BlockSpec("cta", LAYOUT["cta"], CTA_TEXT, pal.accent_ink, pal.accent,
                            True, "solid", meta["size_px"], "bold", "center", meta["ink_box"]))

    # ---- legal ------------------------------------------------------------ #
    legal = _pick(LEGAL, index)
    meta = draw_text_in_box(img, LAYOUT["legal"], legal, weight="regular", size=30,
                            color=pal.accent_ink, align="center")
    blocos.append(BlockSpec("legal", LAYOUT["legal"], legal, pal.accent_ink, pal.accent,
                            True, "solid", meta["size_px"], "regular", "center", meta["ink_box"]))

    info = {"palette": pal.name, "background_kind": kind, "index": index}
    return img, blocos, info


# --------------------------------------------------------------------------- #
# Casos difíceis
# --------------------------------------------------------------------------- #
def build_hard(case: int, seed: int = DEFAULT_SEED) -> tuple[str, Image.Image, list[BlockSpec], dict[str, Any]]:
    """Os três casos que quebram implementação ingênua.

    1. CTA direto sobre textura (exige inpaint, não dá pra achar "a" cor);
    2. CTA sobre degradê (exige reconstrução por mínimos quadrados);
    3. texto claro sobre fundo claro (ΔE baixo: quebra limiar fixo de segmentação).
    """
    rng = np.random.default_rng(seed * 9000 + case)
    box = (140, 1500, 800, 130)     # caixa do CTA, folgada, longe das bordas
    blocos: list[BlockSpec] = []

    if case == 1:
        pal = PALETTES[0]
        img = _canvas("photo", pal, rng)
        _texture_overlay(img, rng)
        _scrim(img, until=0.45, strength=0.45)
        nome = "dificil-1-cta-sobre-foto"
        kind, cor, fundo = "photo", (255, 255, 255), None
        head = "TEXTO SOBRE TEXTURA"
    elif case == 2:
        pal = PALETTES[1]
        img = Image.fromarray(_gradient(WIDTH, HEIGHT, (10, 90, 150), (250, 120, 30)), "RGB")
        nome = "dificil-2-cta-degrade"
        kind, cor, fundo = "gradient", (255, 255, 255), None
        head = "TEXTO SOBRE DEGRADE"
    else:
        pal = PALETTES[2]
        img = Image.fromarray(_solid(WIDTH, HEIGHT, (239, 236, 228)), "RGB")
        nome = "dificil-3-claro-sobre-claro"
        kind, cor, fundo = "solid", (246, 244, 238), (239, 236, 228)
        head = "CLARO SOBRE CLARO"

    meta = draw_text_in_box(img, LAYOUT["headline"], head, weight="bold", size=88,
                            color=cor, align="left", line_gap=1.1)
    blocos.append(BlockSpec("headline", LAYOUT["headline"], head, cor, fundo,
                            case == 3, kind, meta["size_px"], "bold", "left", meta["ink_box"]))

    meta = draw_text_in_box(img, box, CTA_TEXT, weight="bold", size=72,
                            color=cor, align="center")
    blocos.append(BlockSpec("cta", box, CTA_TEXT, cor, fundo, case == 3, kind,
                            meta["size_px"], "bold", "center", meta["ink_box"]))

    info = {"case": case, "background_kind": kind, "palette": pal.name, "hard": True}
    return nome, img, blocos, info


# --------------------------------------------------------------------------- #
# Gravação
# --------------------------------------------------------------------------- #
def _entry(path: Path, blocos: Iterable[BlockSpec], info: dict[str, Any],
           base: Path) -> dict[str, Any]:
    return {
        "file": path.name,
        "relpath": path.relative_to(base).as_posix(),
        "width": WIDTH,
        "height": HEIGHT,
        "blocks": [b.to_dict() for b in blocos],
        **info,
    }


def build_fixtures(out_dir: str | Path = DEFAULT_OUT, *, count: int = DEFAULT_COUNT,
                   seed: int = DEFAULT_SEED, hard: bool = True,
                   quiet: bool = True) -> dict[str, Any]:
    """Gera o lote inteiro e devolve (e grava) o manifesto.

    Sempre PNG: JPEG destruiria a garantia de zero drift já na origem.
    """
    base = Path(out_dir).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)

    criativos: list[dict[str, Any]] = []
    for i in range(int(count)):
        img, blocos, info = build_creative(i, seed=seed)
        p = base / f"criativo-{i + 1:02d}.png"
        img.save(p, "PNG", optimize=True)
        criativos.append(_entry(p, blocos, info, base))
        if not quiet:
            print(f"  {p.name}  ({info['background_kind']}, {info['palette']})")

    dificeis: list[dict[str, Any]] = []
    if hard:
        hdir = base / HARD_SUBDIR
        hdir.mkdir(parents=True, exist_ok=True)
        for case in (1, 2, 3):
            nome, img, blocos, info = build_hard(case, seed=seed)
            p = hdir / f"{nome}.png"
            img.save(p, "PNG", optimize=True)
            dificeis.append(_entry(p, blocos, info, base))
            if not quiet:
                print(f"  {HARD_SUBDIR}/{p.name}  ({info['background_kind']})")

    manifest = {
        "version": FIXTURE_VERSION,
        "seed": int(seed),
        "count": int(count),
        "width": WIDTH,
        "height": HEIGHT,
        "cta_text": CTA_TEXT,
        "font_family": font_family_name("bold"),
        "font_path": str(_font_path("bold") or ""),
        "layout": {k: {"x": v[0], "y": v[1], "w": v[2], "h": v[3]} for k, v in LAYOUT.items()},
        "cta_bar": {"x": CTA_BAR[0], "y": CTA_BAR[1], "w": CTA_BAR[2], "h": CTA_BAR[3]},
        "ink_pad": INK_PAD,
        "creatives": criativos,
        "hard_cases": dificeis,
    }
    (base / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest


def load_manifest(out_dir: str | Path = DEFAULT_OUT) -> dict[str, Any] | None:
    """Manifesto já gravado, ou ``None`` se não existe / está ilegível."""
    p = Path(out_dir) / MANIFEST_NAME
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _manifest_ok(man: dict[str, Any] | None, base: Path, count: int, seed: int) -> bool:
    if not man:
        return False
    if (man.get("version"), man.get("count"), man.get("seed")) != (FIXTURE_VERSION, count, seed):
        return False
    todos = list(man.get("creatives") or []) + list(man.get("hard_cases") or [])
    return bool(todos) and all((base / e["relpath"]).is_file() for e in todos)


def ensure_fixtures(out_dir: str | Path = DEFAULT_OUT, *, count: int = DEFAULT_COUNT,
                    seed: int = DEFAULT_SEED, force: bool = False) -> dict[str, Any]:
    """Gera os fixtures só se faltarem (ou se ``force``). Devolve o manifesto.

    É o ponto de entrada dos testes: rodar o pytest duas vezes seguidas não
    paga o custo de redesenhar 33 imagens de 1080x1920.
    """
    base = Path(out_dir).expanduser().resolve()
    man = load_manifest(base)
    if not force and _manifest_ok(man, base, count, seed):
        return man                                     # type: ignore[return-value]
    return build_fixtures(base, count=count, seed=seed)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="make_fixtures",
        description="Gera criativos sintéticos 1080x1920 para os testes do S7 Editor.")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="pasta de saída (padrão: tests/fixtures)")
    p.add_argument("--count", type=int, default=DEFAULT_COUNT, help="quantos criativos do lote padrão")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help="semente (mesma semente = mesmos bytes)")
    p.add_argument("--no-hard", action="store_true", help="não gerar os 3 casos difíceis")
    p.add_argument("--force", action="store_true", help="regerar mesmo se já existirem")
    args = p.parse_args(argv)

    base = Path(args.out).expanduser().resolve()
    if args.count < 1:
        print("erro: --count precisa ser pelo menos 1", file=sys.stderr)
        return 2

    if args.force or not _manifest_ok(load_manifest(base), base, args.count, args.seed):
        print(f"Gerando fixtures em {base} ...")
        man = build_fixtures(base, count=args.count, seed=args.seed,
                             hard=not args.no_hard, quiet=False)
    else:
        man = load_manifest(base) or {}
        print(f"Fixtures já estavam prontos em {base} (use --force para regerar).")

    print(f"OK: {len(man.get('creatives') or [])} criativos + "
          f"{len(man.get('hard_cases') or [])} casos difíceis. "
          f"Fonte: {man.get('font_family')}. Manifesto: {base / MANIFEST_NAME}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
