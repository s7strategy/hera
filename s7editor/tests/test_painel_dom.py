"""O contrato entre o HTML e o JS do painel.

Existe porque um único id ausente deixou o painel inteiro inutilizável sem
mostrar erro nenhum: `enviar()` escrevia em `#dz-titulo` ANTES do fetch, o
TypeError abortava a função, e o usuário via a tela voltar ao normal como se
nada tivesse acontecido — nenhum upload, nenhuma mensagem.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ESTATICO = Path(__file__).resolve().parent.parent / "s7editor" / "static"
HTML = ESTATICO / "index.html"
JS = ESTATICO / "app.js"


@pytest.fixture(scope="module")
def html() -> str:
    return HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js() -> str:
    return JS.read_text(encoding="utf-8")


def test_todo_id_usado_pelo_js_existe_no_html(html: str, js: str):
    ids = set(re.findall(r'id="([^"]+)"', html))
    usados = set(re.findall(r'\$\("([^"]+)"\)', js))
    faltando = sorted(usados - ids)
    assert not faltando, (
        "o JS busca elementos que não existem no HTML: "
        + ", ".join("#" + i for i in faltando)
    )


def test_dollar_devolve_alvo_inerte_em_vez_de_null(js: str):
    """Segunda linha de defesa: nem todo id sumido pode derrubar o fluxo.

    Mesmo com o teste acima, um id pode sumir num refactor de HTML. O `$()`
    devolve um objeto inofensivo e grita no console, para que um elemento
    cosmético ausente nunca mais aborte um lote inteiro.
    """
    corpo = js[js.index("function $("):]
    corpo = corpo[:corpo.index("\n}") + 2]
    assert "console.error" in corpo, "$() precisa avisar quando o id não existe"
    for membro in ("textContent", "classList", "addEventListener", "value"):
        assert membro in corpo, f"o alvo inerte de $() não cobre .{membro}"


def test_campos_do_fluxo_principal_existem(html: str):
    """Os campos que o fluxo de troca de texto usa de ponta a ponta."""
    for campo in ("file-input", "dropzone", "dz-titulo", "tt-find", "tt-replace",
                  "tt-role", "tt-else", "passo-2", "upload-erro"):
        assert f'id="{campo}"' in html, f"faltou #{campo} no painel"


def test_seletor_de_fallback_oferece_o_preco(html: str):
    """"Se não achar o texto -> escreve abaixo do preço" é o caso do usuário."""
    bloco = html[html.index('id="tt-else"'):]
    bloco = bloco[:bloco.index("</select>")]
    assert 'value="price"' in bloco
    assert "preço" in bloco.lower()
