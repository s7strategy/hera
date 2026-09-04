"""Contrato de dados: geometria, formatos de saída e parsing de operações.

``models.py`` está congelado — todo o resto do projeto depende destas conversões
darem sempre o mesmo resultado.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from s7editor.models import (
    AspectSpec, Box, EditOp, Engine, FontSpec, ImageResult, JobManifest, OpKind,
    TextBlock, TextRole, color_to_hex, parse_color,
)


# --------------------------------------------------------------------------- #
# Box: normalizada x pixel
# --------------------------------------------------------------------------- #
def test_box_from_norm_converte_para_pixel():
    b = Box.from_norm(0.1, 0.2, 0.5, 0.25, 1000, 2000)
    assert b.to_dict() == {"x": 100, "y": 400, "w": 500, "h": 500}
    assert b.xyxy == (100, 400, 600, 900)
    assert b.area == 250_000
    assert b.center == (350, 650)


def test_box_from_norm_arredonda_e_faz_clamp():
    # 0.999 + 0.5 estouraria a borda: o clamp corta na imagem, nunca vaza.
    b = Box.from_norm(0.9, 0.9, 0.5, 0.5, 100, 100)
    assert (b.x, b.y) == (90, 90)
    assert b.x1 == 100 and b.y1 == 100


def test_box_from_any_distingue_normalizado_de_pixel():
    norm = Box.from_any({"x": 0.1, "y": 0.2, "w": 0.5, "h": 0.25}, 1000, 2000)
    px = Box.from_any({"x": 100, "y": 400, "w": 500, "h": 500}, 1000, 2000)
    assert norm == px, "os dois jeitos de escrever a mesma caixa têm que coincidir"

    # 'norm' explícito manda, mesmo quando os números parecem pixels
    forcado = Box.from_any({"x": 0, "y": 0, "w": 1, "h": 1, "norm": False}, 1000, 2000)
    assert forcado.to_dict() == {"x": 0, "y": 0, "w": 1, "h": 1}


def test_box_from_any_aceita_lista_e_box():
    b = Box.from_any([10, 20, 30, 40], 100, 100)
    assert b == Box(10, 20, 30, 40)
    assert Box.from_any(b, 100, 100) == b
    with pytest.raises(ValueError, match="caixa inválida"):
        Box.from_any("meia caixa", 100, 100)


def test_box_geometria_basica():
    a, b = Box(0, 0, 100, 100), Box(50, 50, 100, 100)
    assert a.intersects(b) and not a.intersects(Box(200, 200, 10, 10))
    assert a.union(b) == Box(0, 0, 150, 150)
    assert a.iou(b) == pytest.approx(2500 / (10000 + 10000 - 2500))
    assert a.pad(10) == Box(-10, -10, 120, 120)
    assert a.pad(10, 100, 100) == Box(0, 0, 100, 100)   # pad com clamp
    assert a.scale(2.0) == Box(0, 0, 200, 200)
    assert Box.from_xyxy(30, 40, 10, 20) == Box(10, 20, 20, 20)


def test_box_to_norm_volta_ao_mesmo_lugar():
    b = Box(100, 400, 500, 500)
    d = b.to_norm(1000, 2000)
    assert d["norm"] is True
    assert Box.from_any(d, 1000, 2000) == b


# --------------------------------------------------------------------------- #
# AspectSpec: os três formatos aceitos
# --------------------------------------------------------------------------- #
def test_aspect_parse_razao():
    a = AspectSpec.parse("16:9")
    assert (a.ratio_w, a.ratio_h) == (16, 9)
    assert a.width is None and a.height is None
    assert a.label == "16:9"
    assert a.ratio == pytest.approx(16 / 9)
    assert a.resolve(long_edge=1920) == (1920, 1080)


def test_aspect_parse_dimensoes():
    a = AspectSpec.parse("1080x1920")
    assert a.resolve() == (1080, 1920), "largura/altura explícitas mandam no resolve"
    assert (a.ratio_w, a.ratio_h) == (9, 16), "a razão é reduzida pelo mdc"


def test_aspect_parse_razao_com_largura():
    a = AspectSpec.parse("9:16@1080")
    assert (a.ratio_w, a.ratio_h) == (9, 16)
    assert a.resolve() == (1080, 1920)


def test_aspect_resolve_9x16_sem_dimensao_usa_long_edge():
    # razão < 1 => long_edge é a ALTURA, senão a peça sairia deitada
    assert AspectSpec.parse("9:16").resolve(long_edge=1920) == (1080, 1920)


def test_aspect_parse_invalido_explica_o_formato():
    with pytest.raises(ValueError) as exc:
        AspectSpec.parse("dezesseis por nove")
    msg = str(exc.value)
    assert "formato inválido" in msg and "16:9" in msg


# --------------------------------------------------------------------------- #
# EditOp
# --------------------------------------------------------------------------- #
def test_editop_from_dict_valido():
    op = EditOp.from_dict({"type": "replace_text", "find": "GARANTA O SEU",
                           "replace": "ULTIMAS VAGAS", "engine": "deterministic",
                           "scope": "*.png"})
    assert op.kind is OpKind.REPLACE_TEXT
    assert op.engine is Engine.DETERMINISTIC
    assert op.scope == "*.png"
    assert op.params == {"find": "GARANTA O SEU", "replace": "ULTIMAS VAGAS"}
    assert op.enabled is True
    # to_dict achata os params de volta no mesmo formato da receita
    assert op.to_dict()["type"] == "replace_text"
    assert op.to_dict()["replace"] == "ULTIMAS VAGAS"


def test_editop_from_dict_tipo_invalido_erro_em_portugues():
    with pytest.raises(ValueError) as exc:
        EditOp.from_dict({"type": "trocar_texto", "replace": "x"})
    msg = str(exc.value)
    assert "operação desconhecida" in msg
    assert "'trocar_texto'" in msg
    assert "replace_text" in msg, "a mensagem tem que listar as operações válidas"


def test_editop_from_dict_engine_invalida_erro_em_portugues():
    with pytest.raises(ValueError) as exc:
        EditOp.from_dict({"type": "replace_text", "engine": "magica"})
    assert "engine inválida" in str(exc.value)


def test_editop_aceita_kind_como_apelido_de_type():
    assert EditOp.from_dict({"kind": "reframe"}).kind is OpKind.REFRAME


# --------------------------------------------------------------------------- #
# Cores, blocos e manifesto
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("entrada,esperado", [
    ("#ff0044", (255, 0, 68)),
    ("ff0044", (255, 0, 68)),
    ("#f04", (255, 0, 68)),
    ([255, 0, 68], (255, 0, 68)),
    ((255, 0, 68), (255, 0, 68)),
])
def test_parse_color(entrada, esperado):
    assert parse_color(entrada) == esperado
    assert color_to_hex(esperado) == "#ff0044"


def test_textblock_roundtrip():
    tb = TextBlock(box=Box(10, 20, 30, 40), text="GARANTA O SEU", role=TextRole.CTA,
                   style=FontSpec(family="Inter", weight="bold", size_px=64,
                                  color=(255, 255, 255)),
                   background_color=(255, 46, 136), on_solid_background=True)
    volta = TextBlock.from_dict(tb.to_dict(), 1080, 1920)
    assert volta.box == tb.box
    assert volta.role is TextRole.CTA
    assert volta.style.color == (255, 255, 255)
    assert volta.on_solid_background is True


def test_textblock_papel_desconhecido_vira_other():
    tb = TextBlock.from_dict({"box": [0, 0, 10, 10], "role": "chamariz"}, 100, 100)
    assert tb.role is TextRole.OTHER


def test_job_manifest_conta_e_grava(tmp_path: Path):
    m = JobManifest(job="lote", results=[
        ImageResult(source=Path("a.png"), ok=True, untouched_pixels_verified=True),
        ImageResult(source=Path("b.png"), ok=False, error="falhou"),
        ImageResult(source=Path("c.png"), ok=False, skipped=True),
    ])
    assert m.ok_count == 1
    assert m.fail_count == 1, "pulado não conta como falha"

    destino = m.write(tmp_path / "sub" / "manifest.json")
    dados = json.loads(destino.read_text(encoding="utf-8"))
    assert dados["ok"] == 1 and dados["failed"] == 1
    assert dados["results"][0]["untouched_pixels_verified"] is True
