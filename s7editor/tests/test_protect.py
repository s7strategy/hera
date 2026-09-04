"""A garantia de zero drift, medida no módulo que a implementa.

Se estes testes passam, "os pixels fora da caixa são os do original" deixa de
ser promessa e vira aritmética verificada.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from s7editor import protect
from s7editor.models import Box

W, H = 240, 160


@pytest.fixture
def original() -> Image.Image:
    """Imagem de ruído: qualquer alteração acidental aparece."""
    rng = np.random.default_rng(11)
    return Image.fromarray(rng.integers(0, 256, (H, W, 3), dtype=np.uint8), "RGB")


@pytest.fixture
def editada() -> Image.Image:
    """Uma imagem COMPLETAMENTE diferente da original."""
    rng = np.random.default_rng(22)
    return Image.fromarray(rng.integers(0, 256, (H, W, 3), dtype=np.uint8), "RGB")


CAIXA = Box(40, 30, 100, 60)


# --------------------------------------------------------------------------- #
# build_mask
# --------------------------------------------------------------------------- #
def test_build_mask_feather_zero_e_binaria_e_exata():
    mask = np.asarray(protect.build_mask((W, H), [CAIXA], feather=0))
    assert mask.shape == (H, W)
    assert set(np.unique(mask)) <= {0, 255}, "sem feather a máscara é binária"
    assert mask[CAIXA.y:CAIXA.y1, CAIXA.x:CAIXA.x1].min() == 255
    fora = mask.copy()
    fora[CAIXA.y:CAIXA.y1, CAIXA.x:CAIXA.x1] = 0
    assert fora.max() == 0, "nenhum pixel fora da caixa pode estar liberado"


def test_build_mask_feather_nao_vaza_da_caixa():
    """A rampa cresce para DENTRO: `mask > 0` continua contido na caixa."""
    mask = np.asarray(protect.build_mask((W, H), [CAIXA], feather=6))
    fora = mask.copy()
    fora[CAIXA.y:CAIXA.y1, CAIXA.x:CAIXA.x1] = 0
    assert fora.max() == 0
    assert mask.max() == 255, "o núcleo da caixa continua totalmente liberado"
    assert 0 < mask[CAIXA.y + 1, CAIXA.x + 1] < 255, "a borda tem que ser rampa"


def test_build_mask_invert_protege_a_caixa():
    mask = np.asarray(protect.build_mask((W, H), [CAIXA], invert=True))
    assert mask[CAIXA.y + 5, CAIXA.x + 5] == 0
    assert mask[0, 0] == 255


def test_build_mask_aceita_caixa_normalizada():
    a = np.asarray(protect.build_mask((W, H), [{"x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5}]))
    b = np.asarray(protect.build_mask((W, H), [Box(0, 0, W // 2, H // 2)]))
    assert np.array_equal(a, b)


# --------------------------------------------------------------------------- #
# protected_composite
# --------------------------------------------------------------------------- #
def test_composicao_protegida_tem_drift_zero(original: Image.Image, editada: Image.Image):
    allow = protect.build_mask(original.size, [CAIXA], feather=0)
    out = protect.protected_composite(original, editada, allow)

    n, bbox = protect.drift_report(original, out, [CAIXA])
    assert (n, bbox) == (0, None)
    assert protect.assert_untouched(original, out, [CAIXA]) is True

    a, b, o = (np.asarray(x) for x in (original, editada, out))
    dentro = np.s_[CAIXA.y:CAIXA.y1, CAIXA.x:CAIXA.x1]
    assert np.array_equal(o[dentro], b[dentro]), "dentro da caixa vale a versão editada"
    fora = np.ones((H, W), bool)
    fora[dentro] = False
    assert np.array_equal(o[fora], a[fora]), "fora, os bytes do original"


def test_composicao_com_feather_continua_sem_drift(original: Image.Image, editada: Image.Image):
    allow = protect.build_mask(original.size, [CAIXA], feather=8)
    out = protect.protected_composite(original, editada, allow)
    assert protect.drift_report(original, out, [CAIXA])[0] == 0


# --------------------------------------------------------------------------- #
# drift_report / assert_untouched
# --------------------------------------------------------------------------- #
def test_drift_report_pega_um_unico_pixel_fora(original: Image.Image):
    a = np.asarray(original).copy()
    a[5, 7] = (a[5, 7].astype(int) + 40) % 256      # um pixel, bem longe da caixa
    ruim = Image.fromarray(a, "RGB")

    n, bbox = protect.drift_report(original, ruim, [CAIXA])
    assert n == 1
    assert bbox is not None and (bbox.x, bbox.y) == (7, 5)
    assert protect.assert_untouched(original, ruim, [CAIXA]) is False


def test_drift_report_ignora_mudanca_dentro_da_caixa(original: Image.Image):
    a = np.asarray(original).copy()
    a[CAIXA.y + 3, CAIXA.x + 3] = (0, 0, 0)
    ok = Image.fromarray(a, "RGB")
    assert protect.drift_report(original, ok, [CAIXA])[0] == 0


def test_drift_de_1_bit_e_detectado_com_tol_zero(original: Image.Image):
    """Delta de 1 (o que um JPEG q=95 produz) NÃO passa como 'sem alteração'."""
    a = np.asarray(original).astype(np.int16)
    a[100:110, 200:210, 0] += 1
    quase = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
    assert protect.drift_report(original, quase, [CAIXA])[0] == 100
    assert protect.drift_report(original, quase, [CAIXA], tol=2)[0] == 0, (
        "com tolerância 2 o mesmo delta é ignorado — é o modo JPEG, que não prova nada"
    )


def test_assert_untouched_levanta_com_mensagem_em_portugues(original: Image.Image):
    a = np.asarray(original).copy()
    a[0, 0] = (255, 255, 255) if tuple(a[0, 0]) != (255, 255, 255) else (0, 0, 0)
    ruim = Image.fromarray(a, "RGB")
    with pytest.raises(AssertionError) as exc:
        protect.assert_untouched(original, ruim, [CAIXA], raise_on_fail=True)
    assert "drift detectado" in str(exc.value)


def test_drift_details_denuncia_operacao_que_nao_fez_nada(original: Image.Image):
    d = protect.drift_details(original, original.copy(), [CAIXA])
    assert d["drift_pixels"] == 0
    assert d["changed_inside"] == 0, "nada mudou nem dentro: seria um bug silencioso"
    assert d["verified"] is True


def test_drift_details_denuncia_caixa_inteira_repintada(original: Image.Image, editada: Image.Image):
    allow = protect.build_mask(original.size, [CAIXA], feather=0)
    out = protect.protected_composite(original, editada, allow)
    d = protect.drift_details(original, out, [CAIXA])
    assert d["drift_pixels"] == 0
    assert d["changed_inside_frac"] > 0.9, (
        "colar um retângulo inteiro é legítimo aqui, mas o relatório precisa mostrar isso"
    )


def test_tamanhos_diferentes_nao_passam_calados(original: Image.Image):
    outra = original.resize((W // 2, H // 2))
    with pytest.raises((AssertionError, ValueError)):
        protect.drift_report(original, outra, [CAIXA])
