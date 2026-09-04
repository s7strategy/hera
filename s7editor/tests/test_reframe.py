"""Reenquadrar 9:16 -> 16:9 sem esticar nada.

"Sem modificar o conteúdo e sem alterar proporções" tem um teste exato: a
região do conteúdo no canvas novo é IDÊNTICA ao original redimensionado por um
único fator em x e y (Lanczos). Se algum eixo fosse esticado, a comparação
falharia.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from helpers import arr, path_of
from s7editor import reframe as rf
from s7editor.imageio_util import load_image
from s7editor.models import AspectSpec, Box

SRC_W, SRC_H = 1080, 1920


@pytest.fixture
def criativo(fixtures_dir, creatives) -> Image.Image:
    return load_image(path_of(fixtures_dir, creatives[0]))


# --------------------------------------------------------------------------- #
# plan_placement: a matemática do "cabe sem distorcer"
# --------------------------------------------------------------------------- #
def test_plan_placement_um_unico_fator_de_escala():
    caixa, escala = rf.plan_placement(SRC_W, SRC_H, 1920, 1080)
    assert escala == pytest.approx(1080 / 1920)
    assert (caixa.w, caixa.h) == (round(SRC_W * escala), 1080)
    assert caixa.x == (1920 - caixa.w) // 2 and caixa.y == 0
    assert caixa.w / caixa.h == pytest.approx(SRC_W / SRC_H, abs=0.002)


def test_plan_placement_rejeita_alvo_invalido():
    with pytest.raises(ValueError):
        rf.plan_placement(SRC_W, SRC_H, 0, 100)
    with pytest.raises(ValueError):
        rf.plan_placement(0, 0, 100, 100)


# --------------------------------------------------------------------------- #
# reframe pad
# --------------------------------------------------------------------------- #
def test_9x16_para_16x9_tamanho_exato(criativo: Image.Image, settings_offline):
    out, info = rf.reframe(criativo, "16:9", mode="pad", settings=settings_offline)
    assert out.size == (1920, 1080)
    assert out.width / out.height == pytest.approx(16 / 9, abs=0.001)
    assert info["mode"] == "pad"
    assert info["engine"] == "deterministic"
    assert float(info.get("cost_usd") or 0.0) == 0.0


def test_9x16_para_16x9_nao_distorce_o_conteudo(criativo: Image.Image, settings_offline):
    out, info = rf.reframe(criativo, "16:9", mode="pad", settings=settings_offline)
    caixa = Box(**info["content_box"])

    # razão preservada (a menos de 1 px de arredondamento)
    assert caixa.w / caixa.h == pytest.approx(SRC_W / SRC_H, abs=0.002)

    # e o conteúdo é exatamente o original reduzido pelo MESMO fator nos dois eixos
    esperado = arr(criativo.resize((caixa.w, caixa.h), Image.Resampling.LANCZOS))
    obtido = arr(out)[caixa.y:caixa.y1, caixa.x:caixa.x1]
    assert np.array_equal(obtido, esperado), (
        "a região do conteúdo não bate com um redimensionamento uniforme: "
        "algum eixo foi esticado")


@pytest.mark.parametrize("alvo,esperado", [
    ("16:9", (1920, 1080)),
    ("1:1", (1920, 1920)),
    ("1920x1080", (1920, 1080)),
    ("16:9@1280", (1280, 720)),
])
def test_alvos_resolvem_para_o_tamanho_pedido(criativo, settings_offline, alvo, esperado):
    out, info = rf.reframe(criativo, alvo, mode="pad", settings=settings_offline)
    assert out.size == esperado
    caixa = Box(**info["content_box"])
    assert caixa.w / caixa.h == pytest.approx(SRC_W / SRC_H, abs=0.005)


def test_aceita_aspectspec_e_tupla(criativo: Image.Image, settings_offline):
    a, _ = rf.reframe(criativo, AspectSpec.parse("16:9"), mode="pad", settings=settings_offline)
    b, _ = rf.reframe(criativo, (1920, 1080), mode="pad", settings=settings_offline)
    assert a.size == b.size == (1920, 1080)


def test_faixas_geradas_cobrem_exatamente_a_sobra(criativo: Image.Image, settings_offline):
    out, info = rf.reframe(criativo, "16:9", mode="pad", settings=settings_offline)
    caixa = Box(**info["content_box"])
    faixas = rf.generated_bands(caixa, out.width, out.height)

    cobertura = np.zeros((out.height, out.width), bool)
    for b in faixas:
        cobertura[b.y:b.y1, b.x:b.x1] = True
    conteudo = np.zeros_like(cobertura)
    conteudo[caixa.y:caixa.y1, caixa.x:caixa.x1] = True

    assert not (cobertura & conteudo).any(), "faixa gerada invadindo o conteúdo"
    assert (cobertura | conteudo).all(), "sobrou canvas que não é nem conteúdo nem faixa"


@pytest.mark.parametrize("fill", ["blur", "mirror", "black", "#101020"])
def test_preenchimentos_nao_mexem_no_conteudo(criativo, settings_offline, fill):
    out, info = rf.reframe(criativo, "16:9", mode="pad", fill=fill, settings=settings_offline)
    caixa = Box(**info["content_box"])
    esperado = arr(criativo.resize((caixa.w, caixa.h), Image.Resampling.LANCZOS))
    assert np.array_equal(arr(out)[caixa.y:caixa.y1, caixa.x:caixa.x1], esperado)


# --------------------------------------------------------------------------- #
# Modos que dependem de IA degradam com elegância
# --------------------------------------------------------------------------- #
def test_outpaint_sem_chave_cai_para_pad_com_aviso(criativo: Image.Image, settings_offline):
    """Num lote de 30, abortar tudo por falta de variável de ambiente é pior."""
    out, info = rf.reframe(criativo, "16:9", mode="outpaint", settings=settings_offline)
    assert out.size == (1920, 1080)
    assert info["engine"] == "deterministic"
    assert float(info.get("cost_usd") or 0.0) == 0.0
    assert any("OPENAI_API_KEY" in w for w in info.get("warnings") or []), (
        "o usuário precisa saber por que não usou IA")


def test_crop_devolve_o_tamanho_pedido(criativo: Image.Image, settings_offline):
    out, info = rf.reframe(criativo, "16:9", mode="crop", settings=settings_offline)
    assert out.size == (1920, 1080)
    assert info["mode"] == "crop"


def test_entrada_invalida_da_mensagem_em_portugues(settings_offline):
    with pytest.raises(ValueError) as exc:
        rf.reframe("caminho/para/arquivo.png", "16:9", settings=settings_offline)
    assert "imagem" in str(exc.value).lower()
