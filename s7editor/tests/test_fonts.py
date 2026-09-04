"""Tipografia: caber na caixa e nunca vazar dela.

O desenho de texto é o único lugar do projeto que escreve pixel novo. Se ele
respeitar a caixa, a garantia de zero drift do pipeline inteiro se sustenta.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageFont

from helpers import arr, changed_bbox, contido_em
from s7editor import fonts
from s7editor.models import Box, FontSpec

FAMILIA = "DejaVuSans"          # existe nas imagens Linux; se faltar, cai no fallback
CAIXA = Box(100, 120, 600, 160)


def _spec(**kw) -> FontSpec:
    base = dict(family=FAMILIA, weight="bold", size_px=64, color=(255, 255, 255),
                align="center", valign="middle")
    base.update(kw)
    return FontSpec(**base)


@pytest.fixture
def tela() -> Image.Image:
    return Image.new("RGB", (800, 400), (18, 20, 32))


# --------------------------------------------------------------------------- #
# resolve_font / measure_line / wrap_text
# --------------------------------------------------------------------------- #
def test_resolve_font_devolve_fonte_utilizavel():
    f = fonts.resolve_font(FAMILIA, "bold", False, 48)
    assert isinstance(f, ImageFont.FreeTypeFont)
    assert f.getlength("GARANTA O SEU") > 0


def test_resolve_font_nao_quebra_com_familia_inexistente():
    """Fonte que falta vira aviso, nunca exceção — o lote de 30 não pode parar."""
    f = fonts.resolve_font("FonteQueNaoExiste2026", "black", True, 40)
    assert isinstance(f, ImageFont.FreeTypeFont)
    assert any("FonteQueNaoExiste2026".lower() in w.lower() or "não encontrada" in w
               for w in fonts.font_warnings())


def test_measure_line_cresce_com_tracking():
    f = fonts.resolve_font(FAMILIA, "bold", False, 48)
    w0, h0 = fonts.measure_line("GARANTA O SEU", f)
    w1, h1 = fonts.measure_line("GARANTA O SEU", f, letter_spacing=4.0)
    assert w0 > 0 and h0 > 0
    assert w1 > w0, "tracking positivo tem que alargar a linha"


def test_wrap_text_respeita_a_largura():
    f = fonts.resolve_font(FAMILIA, "regular", False, 40)
    texto = "Edicao em lote com garantia de pixel intacto e zero retrabalho"
    linhas = fonts.wrap_text(texto, f, 300)
    assert len(linhas) > 1
    for linha in linhas:
        assert f.getlength(linha) <= 300 + 1, f"a linha {linha!r} estourou a largura"
    assert " ".join(linhas).split() == texto.split(), "nenhuma palavra pode sumir"


# --------------------------------------------------------------------------- #
# fit_font_size
# --------------------------------------------------------------------------- #
def test_fit_font_size_encontra_corpo_que_cabe():
    texto = "GARANTA O SEU"
    size = fonts.fit_font_size(texto, CAIXA, _spec(size_px=400), max_lines=1)
    assert 8 <= size <= CAIXA.h

    f = fonts.resolve_font(FAMILIA, "bold", False, size)
    largura, _ = fonts.measure_line(texto, f)
    assert largura <= CAIXA.w, "o corpo escolhido não cabe na largura"

    # e o corpo seguinte já NÃO caberia (a busca binária para no maior que cabe)
    maior = fonts.resolve_font(FAMILIA, "bold", False, size + 6)
    assert fonts.measure_line(texto, maior)[0] > CAIXA.w or size + 6 > CAIXA.h


def test_fit_font_size_desenhado_cabe_de_fato(tela: Image.Image):
    texto = "GARANTA O SEU"
    size = fonts.fit_font_size(texto, CAIXA, _spec(size_px=400), max_lines=1)
    out = fonts.draw_text_block(tela, texto, CAIXA, _spec(size_px=size))
    tinta = changed_bbox(tela, out)
    assert tinta is not None and contido_em(tinta, CAIXA)


def test_fit_font_size_texto_gigantesco_devolve_o_minimo():
    size = fonts.fit_font_size("A" * 600, CAIXA, _spec(), max_lines=3, min_px=10)
    assert size == 10, "sem caber nem no mínimo, o contrato manda devolver min_px"


# --------------------------------------------------------------------------- #
# draw_text_block: confinamento
# --------------------------------------------------------------------------- #
def test_desenho_nao_muta_a_imagem_de_entrada(tela: Image.Image):
    antes = arr(tela).copy()
    fonts.draw_text_block(tela, "GARANTA O SEU", CAIXA, _spec())
    assert np.array_equal(arr(tela), antes), "draw_text_block tem que devolver imagem NOVA"


def test_texto_muito_longo_nao_vaza_da_caixa(tela: Image.Image):
    """Corpo absurdo + copy absurda: o excesso é recortado, não invade o layout."""
    texto = "GARANTA O SEU LUGAR AGORA MESMO " * 12
    out = fonts.draw_text_block(tela, texto, CAIXA, _spec(size_px=180))
    tinta = changed_bbox(tela, out)
    assert tinta is not None, "não desenhou nada"
    assert contido_em(tinta, CAIXA), f"a tinta {tinta.to_dict()} saiu de {CAIXA.to_dict()}"


def test_sombra_e_contorno_tambem_sao_recortados(tela: Image.Image):
    spec = _spec(size_px=120, stroke_width=8, stroke_color=(255, 0, 0),
                 shadow=True, shadow_color=(0, 0, 0), shadow_offset=(30, 30),
                 shadow_blur=20)
    out = fonts.draw_text_block(tela, "GARANTA", CAIXA, spec)
    tinta = changed_bbox(tela, out)
    assert tinta is not None and contido_em(tinta, CAIXA)


@pytest.mark.parametrize("align,valign", [("left", "top"), ("center", "middle"),
                                          ("right", "bottom")])
def test_alinhamentos_ficam_dentro(tela: Image.Image, align: str, valign: str):
    out = fonts.draw_text_block(tela, "GARANTA O SEU", CAIXA,
                                _spec(align=align, valign=valign))
    tinta = changed_bbox(tela, out)
    assert tinta is not None and contido_em(tinta, CAIXA)


def test_text_mask_so_marca_dentro_da_caixa(tela: Image.Image):
    mask = fonts.text_mask("GARANTA O SEU", CAIXA, _spec(), tela.size)
    assert mask.size == tela.size and mask.mode == "L"
    m = np.asarray(mask)
    assert m.max() > 0
    fora = m.copy()
    fora[CAIXA.y:CAIXA.y1, CAIXA.x:CAIXA.x1] = 0
    assert fora.max() == 0


def test_uppercase_do_spec_e_aplicado(tela: Image.Image):
    baixa = fonts.draw_text_block(tela, "garanta o seu", CAIXA, _spec(uppercase=True))
    alta = fonts.draw_text_block(tela, "GARANTA O SEU", CAIXA, _spec(uppercase=True))
    assert np.array_equal(arr(baixa), arr(alta))
