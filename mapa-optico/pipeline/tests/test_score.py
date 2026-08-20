"""Score com fixtures conhecidas: se o modelo mudar de comportamento, aqui quebra."""

import math

import pandas as pd
import pytest

from mapa_optico.score.model import (
    aplicar_filtros,
    calcular_score,
    circuitos,
    curva_faixa_otima,
    pares_canibalizacao,
    percentil,
)

PESOS = {
    "versao": "teste",
    "filtros": {"populacao_min": 5000, "populacao_max": 40000, "ufs": ["SC"]},
    "fatores": {
        "distancia_polo": {"peso": 30, "tipo": "crescente", "saturacao_km": 150},
        "ausencia_oftalmo": {"peso": 25, "tipo": "inverso", "bonus_zero": 15, "usar_equivalente": True},
        "populacao_40mais": {"peso": 20, "tipo": "crescente"},
        "concorrencia_oticas": {"peso": 15, "tipo": "inverso", "per_capita": False},
        "renda": {"peso": 10, "tipo": "faixa_otima", "faixa_min": 1200, "faixa_max": 3500, "decaimento": 0.6},
    },
    "confianca": {
        "peso_por_fonte": {"cnes": 0.35, "ibge_populacao": 0.25, "distancia_polo": 0.25, "places": 0.15},
        "minimo_para_ranquear": 0.5,
    },
    "circuitos": {"eps_km": 60, "min_municipios": 2},
    "canibalizacao": {"raio_km": 30, "top_n": 20},
}


def base() -> pd.DataFrame:
    """Quatro municipios sinteticos, desenhados para ter ordem esperada obvia."""
    return pd.DataFrame(
        [
            # longe do polo, sem oftalmo, populacao alta, sem otica, renda na faixa
            dict(codigo_ibge="4200001", nome="Ideal", uf="SC", populacao_total=20000,
                 populacao_40mais=9000, oftalmo_equivalente=0.0, qtd_oftalmologistas=0,
                 qtd_oticas=0, renda_mediana=2000, distancia_km=140, lat=-26.5, lon=-53.0),
            # perto do polo, com oftalmo, populacao baixa, muitas oticas, renda alta
            dict(codigo_ibge="4200002", nome="Ruim", uf="SC", populacao_total=20000,
                 populacao_40mais=3000, oftalmo_equivalente=2.0, qtd_oftalmologistas=2,
                 qtd_oticas=8, renda_mediana=6000, distancia_km=10, lat=-26.6, lon=-52.9),
            dict(codigo_ibge="4200003", nome="Medio", uf="SC", populacao_total=20000,
                 populacao_40mais=6000, oftalmo_equivalente=1.0, qtd_oftalmologistas=1,
                 qtd_oticas=3, renda_mediana=2500, distancia_km=70, lat=-27.5, lon=-50.0),
            dict(codigo_ibge="4200004", nome="Medio2", uf="SC", populacao_total=20000,
                 populacao_40mais=5000, oftalmo_equivalente=1.5, qtd_oftalmologistas=2,
                 qtd_oticas=4, renda_mediana=1500, distancia_km=50, lat=-27.6, lon=-50.1),
        ]
    )


def test_ordem_esperada():
    r = calcular_score(base(), PESOS)
    assert r["nome"].iloc[0] == "Ideal"
    assert r["nome"].iloc[-1] == "Ruim"


def test_contribuicoes_somam_o_score():
    r = calcular_score(base(), PESOS).set_index("codigo_ibge")
    for codigo in r.index:
        comps = r.at[codigo, "componentes"]
        soma = sum(c["contribuicao"] for k, c in comps.items() if k != "_meta")
        assert math.isclose(soma, r.at[codigo, "score_total"], abs_tol=0.1), codigo


def test_score_fica_entre_0_e_100():
    r = calcular_score(base(), PESOS)
    assert r["score_total"].between(0, 100).all()


def test_bonus_zero_premia_ausencia_total_de_oftalmo():
    df = base()
    sem_bonus = dict(PESOS)
    sem_bonus["fatores"] = {**PESOS["fatores"]}
    sem_bonus["fatores"]["ausencia_oftalmo"] = {**PESOS["fatores"]["ausencia_oftalmo"], "bonus_zero": 0}
    com = calcular_score(df, PESOS).set_index("codigo_ibge")
    sem = calcular_score(df, sem_bonus).set_index("codigo_ibge")
    fator_com = com.at["4200001", "componentes"]["ausencia_oftalmo"]["normalizado"]
    fator_sem = sem.at["4200001", "componentes"]["ausencia_oftalmo"]["normalizado"]
    assert fator_com >= fator_sem


def test_dado_ausente_nao_vira_zero_e_derruba_confianca():
    df = base()
    df.loc[df["codigo_ibge"] == "4200001", ["oftalmo_equivalente", "qtd_oftalmologistas"]] = None
    r = calcular_score(df, PESOS).set_index("codigo_ibge")
    comp = r.at["4200001", "componentes"]["ausencia_oftalmo"]
    assert comp["disponivel"] is False
    assert comp["contribuicao"] == 0.0
    assert r.at["4200001", "confianca"] < r.at["4200002", "confianca"]
    # e o score continua existindo, calculado sobre os fatores que temos
    assert r.at["4200001", "score_total"] is not None


def test_municipio_sem_nenhuma_fonte_sai_do_ranking_mas_nao_some():
    df = base()
    vazio = dict(codigo_ibge="4200005", nome="Sem dado", uf="SC", populacao_total=20000,
                 populacao_40mais=None, oftalmo_equivalente=None, qtd_oftalmologistas=None,
                 qtd_oticas=None, renda_mediana=None, distancia_km=None, lat=-27.0, lon=-51.0)
    df = pd.concat([df, pd.DataFrame([vazio])], ignore_index=True)
    r = calcular_score(df, PESOS).set_index("codigo_ibge")
    assert "4200005" in r.index  # continua na tabela
    assert bool(r.at["4200005", "ranqueavel"]) is False
    assert r.at["4200005", "confianca"] == 0.0


def test_filtro_de_populacao_mantem_municipio_sem_populacao_conhecida():
    df = base()
    df.loc[0, "populacao_total"] = None
    df.loc[1, "populacao_total"] = 500_000  # fora da faixa
    filtrado = aplicar_filtros(df, PESOS["filtros"])
    assert "4200001" in set(filtrado["codigo_ibge"])
    assert "4200002" not in set(filtrado["codigo_ibge"])


def test_percentil_ignora_nulo_e_nao_quebra_com_valor_unico():
    s = pd.Series([10.0, None, 10.0])
    p = percentil(s)
    assert p.isna().sum() == 1
    assert p.dropna().tolist() == [50.0, 50.0]


@pytest.mark.parametrize(
    "valor,esperado",
    [(1200, 100.0), (2000, 100.0), (3500, 100.0), (800, 89.6), (5000, 60.9), (0, 68.7)],
)
def test_curva_de_renda(valor, esperado):
    assert curva_faixa_otima(valor, 1200, 3500, 0.6) == pytest.approx(esperado, abs=0.2)


def test_renda_nula_nao_pontua():
    assert curva_faixa_otima(None, 1200, 3500, 0.6) is None


def test_saturacao_de_distancia():
    """Acima da saturacao, 200km e 900km valem a mesma coisa — outlier nao quebra a escala."""
    df = base()
    df.loc[df["codigo_ibge"] == "4200001", "distancia_km"] = 900
    r = calcular_score(df, PESOS).set_index("codigo_ibge")
    assert r.at["4200001", "componentes"]["distancia_polo"]["normalizado"] == 100.0


def test_canibalizacao_sinaliza_vizinhos_do_topo():
    r = calcular_score(base(), PESOS)
    pares = pares_canibalizacao(r, PESOS)
    chaves = {tuple(sorted((p["a"], p["b"]))) for p in pares}
    assert ("4200001", "4200002") in chaves  # ~13 km um do outro
    assert ("4200001", "4200003") not in chaves


def test_circuitos_agrupam_vizinhos():
    r = calcular_score(base(), PESOS)
    cl = circuitos(r, PESOS).set_index("codigo_ibge")
    assert cl.at["4200001", "circuito"] == cl.at["4200002", "circuito"]
    assert cl.at["4200003", "circuito"] == cl.at["4200004", "circuito"]
    assert cl.at["4200001", "circuito"] != cl.at["4200003", "circuito"]
