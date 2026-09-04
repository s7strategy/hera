"""A receita é a interface do usuário. Errar nela tem que doer pouco.

Regra do projeto: erro de receita vira mensagem em português explicando como
corrigir — nunca um traceback.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from s7editor.models import Engine, OpKind
from s7editor.recipe import (EXAMPLE_RECIPES, Recipe, RecipeError, load_recipe,
                             matches_scope, validate_recipe)

RECEITA_OK = """\
job: trocar-cta-setembro
input: entrada
output: saida/lote
engine: deterministic

operations:
  - type: replace_text
    find: "GARANTA O SEU"
    replace: "ULTIMAS VAGAS"
    match: fuzzy
  - type: replace_text
    box: {x: 0.18, y: 0.83, w: 0.63, h: 0.05, norm: true}
    replace: "FRETE GRATIS"
    scope: "*.png"
    engine: deterministic

deliver:
  zip: true
  report: true
"""


@pytest.fixture
def projeto(tmp_path: Path, settings_offline):
    """Uma raiz de projeto com pasta de entrada, para os caminhos resolverem."""
    (tmp_path / "entrada").mkdir(exist_ok=True)
    return settings_offline


def _escreve(tmp_path: Path, texto: str, nome: str = "receita.yaml") -> Path:
    p = tmp_path / nome
    p.write_text(texto, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# Receita válida
# --------------------------------------------------------------------------- #
def test_receita_valida_carrega(tmp_path: Path, projeto):
    r = load_recipe(_escreve(tmp_path, RECEITA_OK), projeto)

    assert isinstance(r, Recipe)
    assert r.job == "trocar-cta-setembro"
    assert r.engine is Engine.DETERMINISTIC
    assert r.input_dir == (tmp_path / "entrada"), "caminho relativo parte da raiz do projeto"
    assert r.output_dir == (tmp_path / "saida" / "lote")
    assert [op.kind for op in r.operations] == [OpKind.REPLACE_TEXT, OpKind.REPLACE_TEXT]
    assert r.operations[0].params["find"] == "GARANTA O SEU"
    assert r.operations[1].scope == "*.png"
    assert r.deliver["zip"] is True and r.deliver["report"] is True
    assert r.has_operations is True


def test_ops_for_filtra_pelo_escopo(tmp_path: Path, projeto):
    r = load_recipe(_escreve(tmp_path, RECEITA_OK), projeto)
    png = r.ops_for(Path("criativo-01.png"), 0, 2)
    jpg = r.ops_for(Path("criativo-02.jpg"), 1, 2)
    assert len(png) == 2
    assert len(jpg) == 1, "a segunda operação é só para *.png"


def test_target_e_reenquadramento(tmp_path: Path, projeto):
    texto = ("job: wide\ninput: entrada\noutput: saida\n"
             "target: \"16:9\"\nreframe_mode: pad\nlong_edge: 1920\n")
    r = load_recipe(_escreve(tmp_path, texto), projeto)
    assert r.target is not None and r.target.label == "16:9"
    assert r.target.resolve(r.long_edge) == (1920, 1080)
    assert r.reframe_mode == "pad"


def test_todas_as_receitas_de_exemplo_sao_validas():
    assert EXAMPLE_RECIPES, "os exemplos são a documentação viva do formato"
    for nome, texto in EXAMPLE_RECIPES.items():
        erros = validate_recipe(yaml.safe_load(texto))
        assert erros == [], f"o exemplo {nome!r} não valida: {erros}"


# --------------------------------------------------------------------------- #
# Receita inválida: mensagem em português, sem traceback
# --------------------------------------------------------------------------- #
def test_operacao_desconhecida_explica_as_validas(tmp_path: Path, projeto):
    texto = "job: x\ninput: entrada\noutput: saida\noperations:\n  - type: trocar_texto\n"
    with pytest.raises(RecipeError) as exc:
        load_recipe(_escreve(tmp_path, texto), projeto)
    msg = str(exc.value)
    assert "operação desconhecida" in msg
    assert "replace_text" in msg, "tem que listar as opções válidas"
    assert "linha" in msg, "e apontar onde está o erro"


def test_receita_vazia_manda_rodar_o_init(tmp_path: Path, projeto):
    with pytest.raises(RecipeError) as exc:
        load_recipe(_escreve(tmp_path, "\n\n"), projeto)
    assert "vazia" in str(exc.value)


def test_receita_inexistente_nao_solta_traceback(tmp_path: Path, projeto):
    with pytest.raises(RecipeError):
        load_recipe(tmp_path / "nao-existe.yaml", projeto)


def test_yaml_quebrado_vira_recipe_error(tmp_path: Path, projeto):
    ruim = "job: x\ninput: entrada\noperations:\n  - type: [replace_text\n"
    with pytest.raises(RecipeError):
        load_recipe(_escreve(tmp_path, ruim), projeto)


def test_validate_recipe_devolve_lista_em_portugues():
    erros = validate_recipe({"job": "x", "operations": [{"type": "replace_text"}]})
    assert erros and all(isinstance(e, str) for e in erros)
    assert any("input" in e for e in erros), f"faltou reclamar do 'input': {erros}"


def test_validate_recipe_receita_que_nao_faz_nada():
    erros = validate_recipe({"job": "x", "input": "a", "output": "b"})
    assert any("não faz nada" in e or "operations" in e for e in erros)


def test_validate_recipe_receita_boa_nao_reclama():
    assert validate_recipe({
        "job": "x", "input": "entrada", "output": "saida",
        "operations": [{"type": "replace_text", "role": "cta", "replace": "OI"}],
    }) == []


# --------------------------------------------------------------------------- #
# matches_scope
# --------------------------------------------------------------------------- #
NOMES = [f"criativo-{i:02d}.png" for i in range(1, 11)]


def _quais(scope: str, nomes=None) -> list[int]:
    """Índices humanos (1-based) que entram no escopo."""
    nomes = nomes or NOMES
    return [i + 1 for i, n in enumerate(nomes) if matches_scope(scope, n, i, len(nomes))]


def test_escopo_all_pega_tudo():
    assert _quais("all") == list(range(1, 11))
    assert _quais("") == list(range(1, 11))
    assert matches_scope(None, "a.png", 0, 1) is True


def test_escopo_glob():
    mistos = ["a.png", "b.jpg", "campanha-01.png", "campanha-02.jpg"]
    assert _quais("*.png", mistos) == [1, 3]
    assert _quais("campanha-*", mistos) == [3, 4]


def test_escopo_indices_e_intervalos():
    assert _quais("1,3,5") == [1, 3, 5]
    assert _quais("2-4") == [2, 3, 4]
    assert _quais("8-") == [8, 9, 10], "'8-' é da oitava até o fim"
    assert _quais("-3") == [1, 2, 3], "'-3' é até a terceira"


def test_escopo_exclusao():
    assert _quais("all,!1-5") == [6, 7, 8, 9, 10]
    mistos = ["a.png", "b.jpg", "c.png"]
    assert _quais("!*.jpg", mistos) == [1, 3]


def test_escopo_e_1_based_para_humano():
    """A receita fala em '1' para a primeira imagem; o código enumera de 0."""
    assert matches_scope("1", "a.png", 0, 3) is True
    assert matches_scope("1", "a.png", 1, 3) is False
    assert matches_scope("1", "a.png", 1, 3, one_based=True) is True


def test_escopo_combina_glob_e_indice():
    mistos = ["a.png", "b.jpg", "c.png", "d.jpg"]
    assert _quais("*.png,4", mistos) == [1, 3, 4]
