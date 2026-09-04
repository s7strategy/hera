"""Apagar texto reconstruindo o fundo — sem tocar em nada fora da caixa.

Os casos sintéticos (fundo chapado e degradê desenhados aqui) permitem comparar
o resultado com o fundo ORIGINAL LIMPO, que é a única prova real de que a
reconstrução acertou a cor, e não só de que ficou "parecido".
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

import make_fixtures as mf
from helpers import arr, assert_sem_drift, box_of, erro_medio, path_of, region_std
from s7editor import inpaint, protect
from s7editor.imageio_util import load_image
from s7editor.models import BackgroundKind, Box

CAIXA = Box(60, 60, 500, 120)


def _com_texto(fundo: Image.Image, texto: str = "GARANTA O SEU",
               cor=(255, 255, 255)) -> Image.Image:
    img = fundo.copy()
    mf.draw_text_in_box(img, (CAIXA.x, CAIXA.y, CAIXA.w, CAIXA.h), texto,
                        weight="bold", size=72, color=cor)
    return img


@pytest.fixture
def fundo_solido() -> Image.Image:
    return Image.fromarray(mf._solid(640, 260, (198, 60, 40)), "RGB")


@pytest.fixture
def fundo_degrade() -> Image.Image:
    return Image.fromarray(mf._gradient(640, 260, (10, 90, 150), (250, 120, 30)), "RGB")


# --------------------------------------------------------------------------- #
# Classificação
# --------------------------------------------------------------------------- #
def test_classify_region_reconhece_chapado(fundo_solido: Image.Image):
    assert inpaint.classify_region(_com_texto(fundo_solido), CAIXA) is BackgroundKind.SOLID


def test_classify_region_reconhece_degrade(fundo_degrade: Image.Image):
    assert inpaint.classify_region(_com_texto(fundo_degrade), CAIXA) is BackgroundKind.GRADIENT


def test_classify_region_reconhece_textura(fixtures_dir, hard_cases):
    """O caso difícil 1 é CTA sobre foto texturizada: tem que cair em PHOTO/PATTERN."""
    entrada = hard_cases[0]
    img = load_image(path_of(fixtures_dir, entrada))
    kind = inpaint.classify_region(img, box_of(entrada, "cta"))
    assert kind in (BackgroundKind.PHOTO, BackgroundKind.PATTERN, BackgroundKind.MIXED)


def test_classify_caixa_minuscula_nao_chuta():
    img = Image.new("RGB", (50, 50), (10, 10, 10))
    assert inpaint.classify_region(img, Box(0, 0, 4, 4)) is BackgroundKind.MIXED


# --------------------------------------------------------------------------- #
# erase_region: o contrato de confinamento
# --------------------------------------------------------------------------- #
def test_apagar_em_fundo_solido_nao_toca_fora_da_caixa(fundo_solido: Image.Image):
    img = _com_texto(fundo_solido)
    rep: dict = {}
    out = inpaint.erase_region(img, CAIXA, report=rep)

    assert_sem_drift(img, out, [CAIXA], contexto="erase_region em fundo chapado")
    assert rep.get("kind") == BackgroundKind.SOLID.value
    # o texto sumiu: a caixa volta a ser praticamente uniforme...
    assert region_std(out, CAIXA) < 3.0 < region_std(img, CAIXA)
    # ...e a cor reconstruída é a cor real do fundo, não uma média puxada pelo AA
    assert erro_medio(out, fundo_solido, CAIXA) < 1.0


def test_apagar_em_degrade_nao_toca_fora_da_caixa(fundo_degrade: Image.Image):
    img = _com_texto(fundo_degrade)
    rep: dict = {}
    out = inpaint.erase_region(img, CAIXA, report=rep)

    assert_sem_drift(img, out, [CAIXA], contexto="erase_region em degradê")
    assert rep.get("kind") == BackgroundKind.GRADIENT.value
    # o degradê reconstruído tem que bater com o original limpo, não só "ficar liso"
    assert erro_medio(out, fundo_degrade, CAIXA) < 3.0
    assert erro_medio(img, fundo_degrade, CAIXA) > 5.0, "sanidade: havia texto ali"


def test_apagar_sobre_textura_fica_confinado(fixtures_dir, hard_cases):
    entrada = hard_cases[0]
    img = load_image(path_of(fixtures_dir, entrada))
    caixa = box_of(entrada, "cta")
    out = inpaint.erase_region(img, caixa)
    assert_sem_drift(img, out, [caixa], contexto="erase_region sobre foto")
    assert region_std(out, caixa) < region_std(img, caixa)


@pytest.mark.parametrize("feather", [0, 1, 3])
def test_feather_nao_vaza_da_caixa(fundo_degrade: Image.Image, feather: int):
    img = _com_texto(fundo_degrade)
    out = inpaint.erase_region(img, CAIXA, feather=feather)
    assert protect.drift_report(img, out, [CAIXA])[0] == 0


def test_caixa_encostada_na_borda_nao_quebra(fundo_solido: Image.Image):
    img = fundo_solido.copy()
    mf.draw_text_in_box(img, (0, 0, 300, 90), "BORDA", weight="bold", size=60,
                        color=(255, 255, 255))
    caixa = Box(0, 0, 300, 90)
    out = inpaint.erase_region(img, caixa)
    assert_sem_drift(img, out, [caixa], contexto="caixa colada na borda")


def test_caixa_sem_tinta_e_no_op(fundo_solido: Image.Image):
    """Apagar uma região que já está limpa não pode inventar diferença."""
    rep: dict = {}
    out = inpaint.erase_region(fundo_solido, Box(300, 200, 200, 50), report=rep)
    assert np.array_equal(arr(out), arr(fundo_solido))


# --------------------------------------------------------------------------- #
# Reconstrutores diretos
# --------------------------------------------------------------------------- #
def test_reconstruct_solid_preenche_a_caixa_inteira(fundo_solido: Image.Image):
    img = _com_texto(fundo_solido)
    out = inpaint.reconstruct_solid(img, CAIXA)
    assert_sem_drift(img, out, [CAIXA], contexto="reconstruct_solid")
    assert region_std(out, CAIXA) < 2.0
    assert erro_medio(out, fundo_solido, CAIXA) < 1.0


def test_reconstruct_gradient_segue_a_rampa(fundo_degrade: Image.Image):
    img = _com_texto(fundo_degrade)
    out = inpaint.reconstruct_gradient(img, CAIXA)
    assert_sem_drift(img, out, [CAIXA], contexto="reconstruct_gradient")
    assert erro_medio(out, fundo_degrade, CAIXA) < 3.0

    # a rampa continua subindo dentro da caixa (não virou cor chapada)
    faixa = arr(out)[CAIXA.y:CAIXA.y1, CAIXA.x:CAIXA.x1].mean(axis=(1, 2))
    assert abs(faixa[-1] - faixa[0]) > 2.0


def test_inpaint_telea_respeita_a_mascara(fundo_degrade: Image.Image):
    img = _com_texto(fundo_degrade)
    mask = np.zeros((img.height, img.width), np.uint8)
    mask[CAIXA.y:CAIXA.y1, CAIXA.x:CAIXA.x1] = 255
    out = inpaint.inpaint_telea(img, mask, radius=3)
    # a dilatação da máscara é interna ao algoritmo, mas o resultado tem que
    # continuar confinado na região marcada (com a folga da dilatação)
    assert protect.drift_report(img, out, [CAIXA.pad(4, img.width, img.height)])[0] == 0
