"""Ponta a ponta: pasta com 30 criativos -> troca de CTA -> ZIP pronto.

Este é o teste que representa o produto. Ele não confia no que o pipeline diz
sobre si mesmo: depois de rodar, relê cada PNG gravado em disco e refaz a conta
de drift contra o arquivo original.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

import make_fixtures as mf
from helpers import block_entry, path_of
from s7editor import deliver, pipeline, protect
from s7editor.config import MissingAPIKeyError
from s7editor.imageio_util import list_images, load_image
from s7editor.models import Box, Engine, OpKind
from s7editor.pipeline import PipelineError
from s7editor.recipe import load_recipe

NOVO_CTA = "ULTIMAS VAGAS"

RECEITA = """\
job: troca-de-cta
input: {entrada}
output: {saida}
engine: deterministic

operations:
  - type: replace_text
    box: {{x: {x}, y: {y}, w: {w}, h: {h}, norm: true}}
    replace: "{novo}"

deliver:
  zip: true
  report: true
  contact_sheet: false
"""


@pytest.fixture(scope="module")
def lote(tmp_path_factory, fixtures_dir, creatives) -> dict:
    """Roda o lote UMA vez por módulo e devolve tudo que os testes conferem.

    Rodar 30 imagens é caro; os asserts sobre o mesmo lote são vários. Por isso
    o escopo é de módulo, e os testes só leem o resultado.
    """
    tmp = Path(tmp_path_factory.mktemp("lote"))

    from dataclasses import replace as _replace

    from s7editor.config import load_settings
    settings = _replace(load_settings(root=tmp, outbox=tmp / "outbox",
                                      cache_dir=tmp / ".cache"),
                        openai_api_key=None, key_source="teste offline")

    cta = block_entry(creatives[0], "cta")["box_norm"]
    saida = tmp / "saida"
    receita = tmp / "receita.yaml"
    receita.write_text(RECEITA.format(entrada=fixtures_dir, saida=saida, novo=NOVO_CTA,
                                      x=cta["x"], y=cta["y"], w=cta["w"], h=cta["h"]),
                       encoding="utf-8")

    passos: list[tuple[int, int, str]] = []
    r = load_recipe(receita, settings)
    manifest = pipeline.run_recipe(r, settings,
                                   progress=lambda i, t, n: passos.append((i, t, n)))
    pacote = deliver.package(manifest, saida, make_zip=True, make_report=True)
    return {"manifest": manifest, "pacote": pacote, "saida": saida, "passos": passos,
            "entradas": [path_of(fixtures_dir, e) for e in creatives],
            "cta_norm": cta, "recipe": r}


# --------------------------------------------------------------------------- #
# O lote
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_lote_inteiro_termina_sem_falha(lote):
    m = lote["manifest"]
    esperado = len(lote["entradas"])
    assert esperado >= 3
    assert m.ok_count == esperado, [r.error for r in m.results if not r.ok]
    assert m.fail_count == 0
    assert m.total_cost_usd == 0.0, "a trilha determinística não pode custar nada"
    assert m.started_at and m.finished_at


@pytest.mark.slow
def test_manifesto_reporta_drift_zero_em_todas(lote):
    for r in lote["manifest"].results:
        assert r.ok, r.error
        assert r.engine_used == Engine.DETERMINISTIC.value
        assert r.drift_pixels == 0, f"{r.source}: {r.drift_pixels} pixels fora da caixa"
        assert r.untouched_pixels_verified is True
        assert r.changed_boxes, "sem caixa registrada não há o que verificar"
        assert r.operations and OpKind.REPLACE_TEXT.value in r.operations[0]


@pytest.mark.slow
def test_reverificacao_independente_dos_arquivos_gravados(lote):
    """A prova final: comparar o PNG entregue com o original, byte a byte."""
    for r in lote["manifest"].results:
        origem = load_image(r.source)
        saida = load_image(r.output)
        assert saida.size == origem.size

        caixas = [Box(**b.to_dict()) if isinstance(b, Box) else Box(**b) for b in r.changed_boxes]
        detalhe = protect.drift_details(origem, saida, caixas)
        assert detalhe["drift_pixels"] == 0, (
            f"{Path(r.source).name}: {detalhe['drift_pixels']} pixels mudaram fora de "
            f"{[b.to_dict() for b in caixas]} (amostra {detalhe['sample'][:3]})")
        assert detalhe["changed_inside"] > 0, f"{Path(r.source).name}: nada mudou dentro da caixa"


@pytest.mark.slow
def test_saida_e_png_lossless(lote):
    for r in lote["manifest"].results:
        p = Path(r.output)
        assert p.suffix.lower() == ".png", "o master tem que ser lossless: JPEG destrói a garantia"
        assert p.stat().st_size > 0


@pytest.mark.slow
def test_zip_relatorio_e_manifesto_saem_prontos(lote):
    pacote = lote["pacote"]
    esperado = len(lote["entradas"])

    assert pacote["count"] == esperado
    assert pacote["drift_pixels"] == 0
    assert pacote["verified"] is True

    zip_path = Path(pacote["zip"])
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as z:
        nomes = z.namelist()
        assert z.testzip() is None
        # Só as imagens entregues contam: o ZIP também leva a folha de contato
        # e o relatório, que não são criativos do lote.
        pngs = [n for n in nomes
                if n.lower().endswith(".png") and n.startswith("imagens/")]
        assert len(pngs) == esperado
        assert any(n.endswith("manifest.json") for n in nomes)

    relatorio = Path(pacote["report"])
    assert relatorio.is_file()
    html = relatorio.read_text(encoding="utf-8")
    assert "<html" in html.lower()
    assert "drift" in html.lower() or "intacto" in html.lower()

    dados = json.loads(Path(pacote["manifest"]).read_text(encoding="utf-8"))
    assert dados["ok"] == esperado and dados["failed"] == 0
    assert all(r["drift_pixels"] == 0 for r in dados["results"])


@pytest.mark.slow
def test_progresso_e_reportado(lote):
    assert lote["passos"], "o callback de progresso nunca foi chamado"
    _, total, _ = lote["passos"][-1]
    assert total == len(lote["entradas"])


@pytest.mark.slow
def test_o_cta_realmente_mudou(lote):
    """Sanidade: a caixa do CTA saiu diferente em todas as peças."""
    caixa_norm = lote["cta_norm"]
    for r in lote["manifest"].results[:5]:
        origem, saida = load_image(r.source), load_image(r.output)
        b = Box.from_any(caixa_norm, origem.width, origem.height)
        a1 = np.asarray(origem)[b.y:b.y1, b.x:b.x1]
        a2 = np.asarray(saida)[b.y:b.y1, b.x:b.x1]
        assert not np.array_equal(a1, a2)


# --------------------------------------------------------------------------- #
# Atalhos e erros de uso
# --------------------------------------------------------------------------- #
def test_atalho_de_troca_de_texto_por_caixa(fixtures_dir, creatives, settings_offline, tmp_path):
    paths = [fixtures_dir / e["relpath"] for e in creatives[:3]]
    caixa = block_entry(creatives[0], "cta")["box_norm"]
    m = pipeline.run_replace_text_batch(paths, None, "COMPRE AGORA", settings_offline,
                                        tmp_path / "out", box=caixa)
    assert m.ok_count == 3
    assert all(r.drift_pixels == 0 and r.untouched_pixels_verified for r in m.results)


def test_troca_sem_dizer_o_que_trocar_da_erro_util(fixtures_dir, creatives, settings_offline,
                                                   tmp_path):
    with pytest.raises(PipelineError) as exc:
        pipeline.run_replace_text_batch([fixtures_dir / creatives[0]["relpath"]], None,
                                        "X", settings_offline, tmp_path / "out")
    msg = str(exc.value)
    assert "find" in msg and "role" in msg and "box" in msg


def test_reframe_em_lote(fixtures_dir, creatives, settings_offline, tmp_path):
    paths = [fixtures_dir / e["relpath"] for e in creatives[:3]]
    m = pipeline.run_reframe_batch(paths, "16:9", settings_offline, tmp_path / "wide",
                                   mode="pad")
    assert m.ok_count == 3
    for r in m.results:
        assert load_image(r.output).size == (1920, 1080)


def test_pasta_vazia_nao_solta_traceback(settings_offline, tmp_path):
    vazia = tmp_path / "vazia"
    vazia.mkdir()
    receita = tmp_path / "r.yaml"
    receita.write_text(
        f"job: nada\ninput: {vazia}\noutput: {tmp_path / 'saida'}\n"
        "operations:\n  - type: replace_text\n    role: cta\n    replace: OI\n",
        encoding="utf-8")
    r = load_recipe(receita, settings_offline)
    with pytest.raises(PipelineError) as exc:
        pipeline.run_recipe(r, settings_offline)
    msg = str(exc.value)
    assert "não achei nenhuma imagem" in msg
    assert str(vazia) in msg


def test_variacoes_sem_chave_explicam_como_configurar(fixtures_dir, creatives,
                                                      settings_offline, tmp_path):
    """Sem chave, a trilha de IA falha rápido e com instrução — não tenta a rede."""
    with pytest.raises(MissingAPIKeyError) as exc:
        pipeline.run_variations_batch([fixtures_dir / creatives[0]["relpath"]], 2,
                                      settings_offline, tmp_path / "var")
    assert "OPENAI_API_KEY" in str(exc.value)


def test_lista_de_imagens_ignora_o_manifesto_e_as_subpastas(fixtures_dir, creatives):
    achadas = list_images(fixtures_dir)
    assert len(achadas) == len(creatives)
    assert all(p.suffix.lower() == ".png" for p in achadas)
    assert all(mf.HARD_SUBDIR not in p.parts for p in achadas), (
        "os casos difíceis moram numa subpasta justamente para não entrar no lote")


@pytest.mark.needs_api
@pytest.mark.skipif(True, reason="exige OPENAI_API_KEY de verdade; a suíte roda offline")
def test_variacoes_com_chave_de_verdade():  # pragma: no cover
    """Placeholder do caminho pago: só roda na mão, com chave e orçamento."""
