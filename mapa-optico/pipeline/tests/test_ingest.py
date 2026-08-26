"""Testes das partes puras da ingestao (parsing e agregacao), sem tocar a rede."""

import pandas as pd
import pytest

from mapa_optico.geo import UF_CODIGO, area_km2, centroide, haversine_km
from mapa_optico.ingest.cnes import CnesIndisponivel, _preparar, agregar_por_municipio
from mapa_optico.ingest import ibge
from mapa_optico.ingest.ibge import _mapa_colunas, _num, idade_inicial
from mapa_optico.ingest.places import raio_metros
from mapa_optico.logs import Contador
from mapa_optico.transform import normalize


class _CabecalhoSidra(dict):
    pass


def test_cabecalho_sidra_reconhecido():
    cabecalho = {
        "NC": "Nível Territorial (Código)",
        "V": "Valor",
        "D1C": "Município (Código)",
        "D1N": "Município",
        "D3C": "Idade (Código)",
        "D3N": "Idade",
    }
    mapa = _mapa_colunas(cabecalho)
    assert mapa["codigo"] == "D1C"
    assert mapa["valor"] == "V"
    assert mapa["idade"] == "D3N"


@pytest.mark.parametrize(
    "rotulo,esperado",
    [
        ("Total", None),
        ("Menos de 1 ano", 0),
        ("35 a 39 anos", 35),
        ("40 a 44 anos", 40),
        ("100 anos ou mais", 100),
    ],
)
def test_faixa_etaria_lida_pelo_rotulo(rotulo, esperado):
    """Somamos 40+ pelo rotulo justamente para nao depender do codigo da classificacao."""
    assert idade_inicial(rotulo) == esperado


@pytest.mark.parametrize(
    "bruto,esperado",
    [("1.234,56", 1234.56), ("1234.56", 1234.56), ("12345", 12345.0), ("-", None), ("..", None)],
)
def test_valores_sidra(bruto, esperado):
    assert _num(bruto) == esperado


def test_cnes_filtra_cbo_e_normaliza_codigo():
    bruto = pd.DataFrame(
        {
            "CODUFMUN": ["420540", "420540", "420910", "420910"],
            "CBO": ["225265", "225125", "225265", "225265"],
            "CPF_PROF": ["111", "999", "111", "222"],
            "HORA_AMB": ["20", "40", "10", "30"],
        }
    )
    c = Contador("teste")
    vinculos = _preparar(bruto, ["225265"], c)
    assert len(vinculos) == 3  # o CBO 225125 caiu fora
    assert set(vinculos["codigo_ibge"]) == {"4205407", "4209102"}
    assert c.motivos["CBO diferente de oftalmologista"] == 1


def test_cnes_agrega_profissionais_unicos_e_equivalente():
    bruto = pd.DataFrame(
        {
            "CODUFMUN": ["420540", "420540", "420540"],
            "CBO": ["225265"] * 3,
            "CPF_PROF": ["111", "111", "222"],  # mesmo medico em dois estabelecimentos
            "HORA_AMB": ["20", "20", "40"],
        }
    )
    agregado = agregar_por_municipio(_preparar(bruto, ["225265"], Contador("t")), "202401")
    linha = agregado.iloc[0]
    assert linha["codigo_ibge"] == "4205407"
    assert linha["qtd_oftalmologistas"] == 2  # profissionais, nao vinculos
    assert linha["horas_semanais_total"] == 80.0
    assert linha["oftalmo_equivalente"] == 2.0  # 80h / 40h
    assert linha["competencia_cnes"] == "202401"


def test_cnes_layout_desconhecido_falha_alto():
    """Melhor quebrar do que devolver zero oftalmologista para o estado inteiro."""
    with pytest.raises(CnesIndisponivel):
        _preparar(pd.DataFrame({"coluna_estranha": [1]}), ["225265"], Contador("t"))


def test_raio_do_places_e_proporcional_a_area():
    cfg = {"raio_min_m": 3000, "raio_max_m": 25000}
    assert raio_metros(None, cfg) == 3000
    pequeno = raio_metros(50, cfg)
    grande = raio_metros(2000, cfg)
    assert pequeno < grande <= 25000
    assert raio_metros(1_000_000, cfg) == 25000  # teto respeitado


def test_haversine_confere_com_distancia_conhecida():
    # Florianopolis -> Joinville, ~146 km em linha reta
    d = haversine_km(-27.5954, -48.5480, -26.3044, -48.8456)
    assert 140 < d < 152


def test_centroide_e_area_de_um_quadrado():
    geom = {
        "type": "Polygon",
        "coordinates": [[[-49.0, -27.0], [-48.9, -27.0], [-48.9, -26.9], [-49.0, -26.9], [-49.0, -27.0]]],
    }
    lat, lon = centroide(geom)
    assert lat == pytest.approx(-26.95, abs=0.01)
    assert lon == pytest.approx(-48.95, abs=0.01)
    area = area_km2(geom)
    assert 90 < area < 130  # ~0,1 grau x 0,1 grau nessa latitude


def test_tabela_de_ufs_completa():
    assert len(UF_CODIGO) == 27
    assert UF_CODIGO["SC"] == 42


# --------------------------------------------------------------------- UF
def test_uf_sai_do_codigo_do_municipio():
    assert normalize.uf_do_codigo("4200200") == "SC"
    assert normalize.uf_do_codigo(4209102) == "SC"
    assert normalize.uf_do_codigo("355030") == "SP"  # 6 digitos tambem
    assert normalize.uf_do_codigo("lixo") is None


def test_municipio_sem_microrregiao_aninhada_nao_some(monkeypatch):
    """Regressao: o payload do IBGE nem sempre traz o bloco aninhado.

    Confiar nele para descobrir a UF fez 171 dos 295 municipios de SC sumirem
    no filtro de UF — sem erro, sem aviso, so um ranking pela metade.
    """
    payload = [
        {"id": 4200051, "nome": "Abdon Batista"},  # sem microrregiao nenhuma
        {
            "id": 4200200,
            "nome": "Agrolândia",
            "microrregiao": {"nome": "Ituporanga", "mesorregiao": {"UF": {"sigla": "SC"}}},
        },
        {"id": 3550308, "nome": "São Paulo"},  # outra UF: tem que sair
    ]
    monkeypatch.setattr(ibge, "get_or_set", lambda *a, **k: payload)
    df = ibge.municipios(["SC"])
    assert sorted(df["nome"]) == ["Abdon Batista", "Agrolândia"]
    assert set(df["uf"]) == {"SC"}


def test_populacao_vai_ao_sidra_em_lotes_de_codigo(monkeypatch):
    """Regressão: pedir 'todos os municípios da UF' devolve resposta truncada.

    Em SC vieram 171 dos 295 e o SIDRA não avisou. Os 124 que faltaram entraram
    no ranking com população nula e escaparam do filtro de faixa populacional —
    o ranking saiu pela metade parecendo completo.
    """
    pedidos: list[str] = []

    def _falso(fonte, chave, buscar, refresh=False):
        return buscar()

    def _json(fonte, url):
        pedidos.append(url)
        # Devolve uma linha "Total" para cada código que o lote pediu.
        codigos_do_lote = url.split("/n6/", 1)[1].split("/", 1)[0].split(",")
        return [
            {"D1C": "Município (Código)", "V": "Valor", "D2N": "Grupo de idade"},
            *({"D1C": c, "V": "2500", "D2N": "Total"} for c in codigos_do_lote),
        ]

    monkeypatch.setattr(ibge, "get_or_set", _falso)
    monkeypatch.setattr(ibge, "get_json", _json)
    monkeypatch.setattr(ibge, "MUNICIPIOS_POR_LOTE", 2)
    # A descoberta da classificação de idade é outra história; aqui ela sai do
    # caminho para o teste falar só sobre o lote.
    monkeypatch.setattr(ibge, "_classificacao_de_idade", lambda *a, **k: "c287")

    codigos = ["4200051", "4200200", "4200309", "4200408", "4200507"]
    ibge.populacao_por_idade(["SC"], codigos=codigos)

    assert len(pedidos) == 3, "5 municípios em lotes de 2 são 3 chamadas"
    assert all("in n3" not in url for url in pedidos), "nenhum lote pode pedir a UF inteira"
    pedidos_juntos = " ".join(pedidos)
    for codigo in codigos:
        assert codigo in pedidos_juntos, f"{codigo} ficou de fora dos lotes"


def test_coluna_de_idade_nao_e_a_forma_de_declaracao():
    """Regressão: a tabela 9514 traz duas colunas com a palavra "idade".

    "Forma de declaração da idade" sobrescrevia "Idade" e o pipeline passava a
    ler uma coluna que vale "Total" em toda linha — população 40+ zerada em
    todos os municípios, sem erro nenhum.
    """
    cabecalho = {
        "V": "Valor",
        "D1C": "Município (Código)",
        "D1N": "Município",
        "D4C": "Idade (Código)",
        "D4N": "Idade",
        "D6C": "Forma de declaração da idade (Código)",
        "D6N": "Forma de declaração da idade",
    }
    assert _mapa_colunas(cabecalho)["idade"] == "D4N"


@pytest.mark.parametrize("rotulo", ["2 meses", "27 dias", "3 semanas"])
def test_bebe_nao_vira_adulto_pelo_numero_do_rotulo(rotulo):
    """"2 meses" tem um 2 no rótulo, mas não é alguém de 2 anos."""
    assert idade_inicial(rotulo) == 0
