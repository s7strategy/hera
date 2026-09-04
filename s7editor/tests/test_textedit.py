"""O caso central do produto: trocar o CTA sem mexer em mais nada.

A afirmação testada aqui é a mais forte do projeto: depois de
``replace_text``, todo pixel fora da caixa devolvida é **byte a byte** igual ao
do original — em fundo chapado, em degradê e sobre foto.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

import make_fixtures as mf
from helpers import (arr, assert_sem_drift, box_of, contido_em, erro_medio,
                     path_of, region_std, text_block_of)
from s7editor import protect, textedit
from s7editor.imageio_util import load_image
from s7editor.models import Box, FontSpec, TextBlock, TextRole

NOVO_CTA = "ULTIMAS VAGAS"


def _tres_fundos(creatives):
    """Um criativo de cada tipo de fundo (chapado, degradê, foto)."""
    escolhidos: dict[str, dict] = {}
    for e in creatives:
        escolhidos.setdefault(e["background_kind"], e)
    return [escolhidos[k] for k in ("solid", "gradient", "photo") if k in escolhidos]


@pytest.fixture(scope="session")
def amostra(creatives):
    return _tres_fundos(creatives)


# --------------------------------------------------------------------------- #
# replace_text
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("i", [0, 1, 2])
def test_trocar_cta_nao_altera_um_pixel_fora_da_caixa(fixtures_dir, amostra, i):
    entrada = amostra[i]
    img = load_image(path_of(fixtures_dir, entrada))
    bloco = text_block_of(entrada, "cta")

    out, mudada = textedit.replace_text(img, bloco, NOVO_CTA)

    assert out.size == img.size, "trocar texto não pode mudar a dimensão"
    assert_sem_drift(img, out, [mudada],
                     contexto=f"replace_text em fundo {entrada['background_kind']}")
    detalhe = protect.drift_details(img, out, [mudada])
    assert detalhe["changed_inside"] > 0, "nada mudou: a operação foi um no-op silencioso"
    assert contido_em(mudada, bloco.box, folga=2), (
        "a caixa devolvida escapou da caixa declarada sem registrar crescimento")


@pytest.mark.parametrize("caso", [0, 1, 2])
def test_trocar_cta_nos_casos_dificeis(fixtures_dir, hard_cases, caso):
    """Foto texturizada, degradê e claro-sobre-claro: os três continuam confinados."""
    entrada = hard_cases[caso]
    img = load_image(path_of(fixtures_dir, entrada))
    bloco = text_block_of(entrada, "cta")

    out, mudada = textedit.replace_text(img, bloco, NOVO_CTA)
    assert_sem_drift(img, out, [mudada], contexto=f"replace_text em {entrada['file']}")
    assert protect.drift_details(img, out, [mudada])["changed_inside"] > 0


def test_trocar_cta_e_deterministico(fixtures_dir, amostra):
    img = load_image(path_of(fixtures_dir, amostra[0]))
    bloco = text_block_of(amostra[0], "cta")
    a, _ = textedit.replace_text(img, bloco, NOVO_CTA)
    b, _ = textedit.replace_text(img, bloco, NOVO_CTA)
    assert np.array_equal(arr(a), arr(b)), "duas rodadas iguais têm que dar o mesmo arquivo"


def test_trocar_cta_funciona_sem_chave_de_api(fixtures_dir, amostra, settings_offline):
    """A trilha determinística não pode nem tocar em `settings.openai_api_key`."""
    assert settings_offline.openai_api_key is None
    img = load_image(path_of(fixtures_dir, amostra[0]))
    out, mudada = textedit.replace_text(img, text_block_of(amostra[0], "cta"),
                                        "COMPRE AGORA", settings=settings_offline)
    assert_sem_drift(img, out, [mudada], contexto="replace_text offline")


def test_texto_novo_muito_longo_continua_confinado(fixtures_dir, amostra):
    """Copy grande demais reduz o corpo (escada E.3) — nunca vaza a caixa."""
    entrada = amostra[0]
    img = load_image(path_of(fixtures_dir, entrada))
    bloco = text_block_of(entrada, "cta")
    longo = "GARANTA JA O SEU LUGAR NA PROXIMA TURMA COM CONDICAO ESPECIAL DE LANCAMENTO"

    rep: dict = {}
    out, mudada = textedit.replace_text(img, bloco, longo, report=rep)
    assert_sem_drift(img, out, [mudada], contexto="replace_text com copy longa")
    assert protect.drift_details(img, out, [mudada])["changed_inside"] > 0


def test_style_override_muda_a_cor_do_texto(fixtures_dir, amostra):
    entrada = amostra[0]
    img = load_image(path_of(fixtures_dir, entrada))
    bloco = text_block_of(entrada, "cta")
    alvo = (12, 12, 12)

    out, mudada = textedit.replace_text(img, bloco, NOVO_CTA,
                                        style_override={"color": alvo})
    assert_sem_drift(img, out, [mudada], contexto="replace_text com style_override")
    medido = textedit.infer_style_from_pixels(out, bloco.box).color
    assert max(abs(int(a) - int(b)) for a, b in zip(medido, alvo)) <= 12, (
        f"a cor pedida {alvo} não apareceu nos pixels (medido {medido})")


def test_caixa_vazia_da_erro_explicativo(fixtures_dir, amostra):
    img = load_image(path_of(fixtures_dir, amostra[0]))
    bloco = TextBlock(box=Box(5000, 5000, 100, 40), text="x", role=TextRole.CTA)
    with pytest.raises(ValueError) as exc:
        textedit.replace_text(img, bloco, "y")
    assert "caixa" in str(exc.value).lower()


# --------------------------------------------------------------------------- #
# Medida de estilo (item D)
# --------------------------------------------------------------------------- #
def test_infer_style_le_cor_e_corpo_dos_pixels(fixtures_dir, amostra):
    entrada = amostra[0]
    img = load_image(path_of(fixtures_dir, entrada))
    cta = next(b for b in entrada["blocks"] if b["role"] == "cta")
    spec = textedit.infer_style_from_pixels(img, Box(**cta["box"]))

    assert isinstance(spec, FontSpec)
    esperada = tuple(cta["color"])
    assert max(abs(int(a) - int(b)) for a, b in zip(spec.color, esperada)) <= 10, (
        f"cor medida {spec.color} longe da desenhada {esperada} — o anti-aliasing "
        "contaminou a medida")
    razao = spec.size_px / float(cta["size_px"])
    assert 0.8 <= razao <= 1.25, f"corpo medido {spec.size_px} vs desenhado {cta['size_px']}"
    assert spec.align == "center"
    assert spec.uppercase is True
    assert spec.italic is False


# --------------------------------------------------------------------------- #
# remove_text / add_text
# --------------------------------------------------------------------------- #
def test_remove_text_limpa_a_faixa_sem_drift(fixtures_dir, amostra):
    entrada = amostra[0]
    img = load_image(path_of(fixtures_dir, entrada))
    bloco = text_block_of(entrada, "cta")

    out, mudada = textedit.remove_text(img, bloco)
    assert_sem_drift(img, out, [mudada], contexto="remove_text")
    assert region_std(out, bloco.box) < region_std(img, bloco.box) / 2, (
        "a faixa continua com a mesma variação: o texto não saiu")


def test_add_text_so_escreve_dentro_da_caixa():
    fundo = Image.fromarray(mf._solid(600, 300, (20, 22, 34)), "RGB")
    caixa = Box(80, 90, 440, 110)
    spec = FontSpec(family="DejaVuSans", weight="bold", size_px=56,
                    color=(255, 255, 255), align="center")

    out, mudada = textedit.add_text(fundo, caixa, "GARANTA O SEU", spec)
    assert_sem_drift(fundo, out, [caixa], contexto="add_text")
    assert contido_em(mudada, caixa, folga=1)
    assert erro_medio(fundo, out, caixa) > 1.0, "nada foi desenhado"
