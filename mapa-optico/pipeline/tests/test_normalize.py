"""O join CNES x IBGE e o ponto onde o pipeline falha em silencio. Estes testes existem para isso."""

import pandas as pd
import pytest

from mapa_optico.transform.normalize import (
    deduplicar_profissionais,
    digito_verificador_ibge,
    para_codigo6,
    para_codigo7,
    slug_nome,
    validar_join,
)

# Casos oficiais conferidos na tabela do IBGE
CASOS = [
    ("420540", "4205407"),  # Florianopolis
    ("420910", "4209102"),  # Joinville
    ("355030", "3550308"),  # Sao Paulo
    ("330455", "3304557"),  # Rio de Janeiro
    ("431490", "4314902"),  # Porto Alegre
]


@pytest.mark.parametrize("codigo6,codigo7", CASOS)
def test_digito_verificador(codigo6, codigo7):
    assert codigo6 + digito_verificador_ibge(codigo6) == codigo7


@pytest.mark.parametrize("codigo6,codigo7", CASOS)
def test_para_codigo7_a_partir_de_6(codigo6, codigo7):
    assert para_codigo7(codigo6) == codigo7
    assert para_codigo7(int(codigo6)) == codigo7


def test_para_codigo7_idempotente():
    assert para_codigo7("4205407") == "4205407"
    assert para_codigo7(4205407) == "4205407"


def test_para_codigo7_aceita_ruido_e_recusa_lixo():
    assert para_codigo7(" 42-05-40 ") == "4205407"
    assert para_codigo7("abc") is None
    assert para_codigo7("") is None
    assert para_codigo7(None) is None
    assert para_codigo7("12345") is None  # tamanho invalido nao vira chute


def test_para_codigo6_volta_ao_formato_cnes():
    assert para_codigo6("4205407") == "420540"


def test_join_cnes_ibge_nao_deixa_orfao():
    """O caso real: CNES com 6 digitos, IBGE com 7. Sem normalizar, 100% de orfaos."""
    ibge = pd.DataFrame({"codigo_ibge": ["4205407", "4209102", "4202404"]})
    cnes_bruto = pd.DataFrame({"codufmun": ["420540", "420910", "420240"]})

    sem_normalizar = cnes_bruto.rename(columns={"codufmun": "codigo_ibge"})
    assert len(validar_join(ibge, sem_normalizar)) == 3  # quebra silenciosa

    cnes_bruto["codigo_ibge"] = cnes_bruto["codufmun"].map(para_codigo7)
    assert validar_join(ibge, cnes_bruto) == []


def test_deduplicar_conta_profissional_e_nao_vinculo():
    """Mesmo medico em 3 estabelecimentos do mesmo municipio = 1 oftalmologista."""
    vinculos = pd.DataFrame(
        {
            "codigo_ibge": ["4205407"] * 3 + ["4209102"],
            "id_profissional": ["111", "111", "222", "111"],
            "horas_ambulatorial": [20.0, 10.0, 40.0, 8.0],
        }
    )
    dedup = deduplicar_profissionais(vinculos)
    floripa = dedup[dedup["codigo_ibge"] == "4205407"]
    assert floripa["id_profissional"].nunique() == 2
    assert float(floripa[floripa["id_profissional"] == "111"]["horas_ambulatorial"].iloc[0]) == 30.0
    # o mesmo medico tambem atende em Joinville: conta nos dois municipios
    assert len(dedup[dedup["codigo_ibge"] == "4209102"]) == 1


def test_deduplicar_limita_carga_horaria_absurda():
    vinculos = pd.DataFrame(
        {
            "codigo_ibge": ["4205407"] * 4,
            "id_profissional": ["111"] * 4,
            "horas_ambulatorial": [40.0, 40.0, 40.0, 40.0],
        }
    )
    dedup = deduplicar_profissionais(vinculos)
    assert float(dedup["horas_ambulatorial"].iloc[0]) == 60.0  # teto, nao 160h


def test_slug_nome():
    assert slug_nome("São Miguel do Oeste") == "sao miguel do oeste"
    assert slug_nome("Balneário Camboriú") == "balneario camboriu"
