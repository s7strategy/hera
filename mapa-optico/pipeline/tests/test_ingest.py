"""Testes das partes puras da ingestao (parsing e agregacao), sem tocar a rede."""

import pandas as pd
import pytest

from mapa_optico.geo import UF_CODIGO, area_km2, centroide, haversine_km
from mapa_optico.ingest.cnes import CnesIndisponivel, _preparar, agregar_por_municipio
from mapa_optico.ingest.ibge import _mapa_colunas, _num, idade_inicial
from mapa_optico.ingest.places import raio_metros
from mapa_optico.logs import Contador


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
