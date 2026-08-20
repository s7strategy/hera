"""Testes da projecao financeira.

O que estes testes protegem, em ordem de importancia:

1. A IDENTIDADE DO POTENCIAL. `potencial_pct` tem que ser exatamente o produto
   dos tres fatores que a interface mostra na ficha. Se essa identidade quebrar,
   a explicacao na tela vira mentira — que e o pior defeito possivel num modelo
   que existe para ser discutido.
2. DADO AUSENTE NAO VIRA ZERO. Cidade sem CNES nao pode aparecer como cidade
   sem oftalmologista; cidade sem consulta ao Places nao pode virar cidade sem
   concorrencia.
3. A ARITMETICA DO DINHEIRO, com os numeros reais da operacao (vende 1800 e paga
   600; vende 1200 e paga 400).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mapa_optico.score.projecao import (
    atrito_deslocamento,
    capacidade_local_anual,
    cmv_fracao,
    custo_do_evento,
    forca_concorrencia,
    projecao_de_circuito,
    projetar,
    teto_faturamento,
    ticket_da_cidade,
)

NEGOCIO = {
    "versao": "teste",
    "venda": {
        "ticket_medio": 1500,
        "custo_produto": 500,
        "renda_referencia": 2200,
        "elasticidade_renda": 0.35,
        "ticket_min": 700,
        "ticket_max": 2600,
    },
    "evento": {
        "dias": 3,
        "consultas_por_dia": 45,
        "custo_medico_dia": 1200,
        "custo_estrutura_dia": 500,
        "custo_deslocamento": 900,
        "investimento_midia": 3000,
        "cidades_por_circuito": 3,
    },
    "demanda": {
        "prevalencia_40mais": 0.85,
        "renovacao_anual": 0.22,
        "consultas_refracao_por_hora": 2.5,
        "fracao_tempo_em_refracao": 0.45,
        "semanas_por_ano": 44,
        "horas_semanais_fallback": 20,
        "atrito_saturacao_km": 120,
        "atrito_minimo": 0.15,
        "backlog_anos": 3.0,
    },
    "captacao": {
        "alcance_por_mil_reais": 0.09,
        "alcance_maximo": 0.55,
        "taxa_agendamento": 0.14,
        "taxa_comparecimento": 0.72,
    },
    "conversao": {
        "base": 0.42,
        "peso_saturacao": 0.30,
        "saturacao_referencia": 4.0,
        "peso_reputacao": 0.20,
        "nota_neutra": 4.0,
        "peso_presenca": 0.15,
        "avaliacoes_referencia": 40,
        "minimo": 0.12,
        "maximo": 0.70,
    },
}


def municipio(**campos):
    padrao = {
        "codigo_ibge": "4200051",
        "nome": "Teste",
        "uf": "SC",
        "populacao_total": 12_000,
        "populacao_40mais": 4_500,
        "renda_mediana": 2200,
        "qtd_oftalmologistas": 0,
        "oftalmo_equivalente": 0.0,
        "horas_semanais_total": 0.0,
        "distancia_km": 120.0,
        "qtd_oticas": 3,
        "oticas_nota_media": 4.0,
        "oticas_avaliacoes": 120,
        "circuito": -1,
    }
    padrao.update(campos)
    return padrao


# --------------------------------------------------------------- venda e CMV
def test_cmv_e_o_mesmo_nos_dois_pares_informados():
    """1800/600 e 1200/400 dao a mesma fracao — por isso o modelo guarda a fracao."""
    assert cmv_fracao({"ticket_medio": 1800, "custo_produto": 600}) == pytest.approx(1 / 3)
    assert cmv_fracao({"ticket_medio": 1200, "custo_produto": 400}) == pytest.approx(1 / 3)


def test_ticket_sobe_e_desce_com_a_renda_dentro_dos_limites():
    venda = NEGOCIO["venda"]
    na_referencia, imputado = ticket_da_cidade(2200, venda)
    assert na_referencia == pytest.approx(1500)
    assert imputado is False

    rico, _ = ticket_da_cidade(4400, venda)  # o dobro da referencia
    assert rico == pytest.approx(1500 * 1.35)

    pobre, _ = ticket_da_cidade(1100, venda)  # metade da referencia
    assert pobre == pytest.approx(1500 * 0.825)

    # Com elasticidade 0,35 o ticket so anda 35% para cada lado, entao o piso e o
    # teto do YAML nao chegam a morder — a elasticidade e que limita.
    assert ticket_da_cidade(1, venda)[0] == pytest.approx(1500 * 0.65, rel=1e-3)

    # Com elasticidade alta eles mordem, e e isso que impede ticket absurdo.
    agressivo = {**venda, "elasticidade_renda": 3.0}
    assert ticket_da_cidade(200, agressivo)[0] == 700
    assert ticket_da_cidade(9_000, agressivo)[0] == 2600


def test_sem_renda_o_ticket_e_o_medio_e_o_campo_fica_marcado():
    ticket, imputado = ticket_da_cidade(None, NEGOCIO["venda"])
    assert ticket == 1500
    assert imputado is True


# ------------------------------------------------------- capacidade e atrito
def test_carga_horaria_do_cnes_manda_na_capacidade_local():
    """Um oftalmo de 40h nao pode valer o mesmo que um de 4h."""
    magro = capacidade_local_anual(4, 1, NEGOCIO["demanda"])
    cheio = capacidade_local_anual(40, 1, NEGOCIO["demanda"])
    assert cheio == pytest.approx(magro * 10)
    assert cheio == pytest.approx(40 * 44 * 2.5 * 0.45)


def test_sem_carga_horaria_cai_para_o_padrao_por_profissional():
    assert capacidade_local_anual(None, 2, NEGOCIO["demanda"]) == pytest.approx(
        2 * 20 * 44 * 2.5 * 0.45
    )


def test_atrito_cresce_com_a_distancia_e_satura():
    d = NEGOCIO["demanda"]
    assert atrito_deslocamento(0, d) == pytest.approx(0.15)
    assert atrito_deslocamento(60, d) == pytest.approx(0.15 + 0.85 * 0.5)
    assert atrito_deslocamento(120, d) == pytest.approx(1.0)
    assert atrito_deslocamento(900, d) == pytest.approx(1.0)  # satura, nao explode
    assert atrito_deslocamento(None, d) is None


# ------------------------------------------------------------- concorrencia
def test_concorrente_mal_avaliado_nao_e_penalidade_e_bem_avaliado_e():
    cfg = NEGOCIO["conversao"]
    fraco, _ = forca_concorrencia(2.0, 3.0, 20.0, cfg)
    forte, _ = forca_concorrencia(2.0, 5.0, 20.0, cfg)
    assert fraco > forte, "otica com nota 3 e oportunidade, nao ameaca"


def test_mais_oticas_e_mais_avaliacoes_derrubam_a_conversao():
    cfg = NEGOCIO["conversao"]
    virgem, _ = forca_concorrencia(0.0, None, 0.0, cfg)
    saturada, _ = forca_concorrencia(8.0, 4.6, 200.0, cfg)
    assert virgem == pytest.approx(0.42)
    assert saturada < virgem
    assert saturada >= cfg["minimo"]


def test_conversao_respeita_piso_e_teto():
    cfg = {**NEGOCIO["conversao"], "base": 0.95}
    valor, _ = forca_concorrencia(0.0, None, 0.0, cfg)
    assert valor == cfg["maximo"]


# ------------------------------------------------------------------ dinheiro
def test_custo_do_evento_dilui_o_deslocamento_entre_as_cidades():
    custos = custo_do_evento(NEGOCIO["evento"])
    assert custos["medico"] == 3600
    assert custos["estrutura"] == 1500
    assert custos["deslocamento"] == 300  # 900 divididos por 3 cidades
    assert custos["total"] == 3600 + 1500 + 300 + 3000


def test_faturamento_bate_com_a_conta_feita_na_mao():
    df = pd.DataFrame([municipio()])
    saida = projetar(df, NEGOCIO)
    linha = saida.iloc[0]

    demanda = 4500 * 0.85 * 0.22
    represada = demanda * 1.0 * 3.0  # 120 km satura o atrito; 3 anos de backlog
    alcance = min(0.55, 0.09 * 3)
    comparecimentos = represada * alcance * 0.14 * 0.72
    consultas = min(comparecimentos, 3 * 45)

    assert linha["demanda_anual"] == pytest.approx(demanda, rel=1e-3)
    assert linha["consultas_esperadas"] == pytest.approx(consultas, rel=1e-3)
    assert linha["faturamento_estimado"] == pytest.approx(
        consultas * linha["conversao"] * linha["ticket_estimado"], rel=1e-3
    )
    # margem bruta e faturamento menos o CMV (1/3 do ticket)
    assert linha["margem_bruta"] == pytest.approx(linha["faturamento_estimado"] * (2 / 3), rel=1e-3)
    assert linha["lucro_estimado"] == pytest.approx(
        linha["margem_bruta"] - linha["custo_evento"], rel=1e-3
    )


def test_ponto_de_equilibrio_e_quantos_pares_pagam_o_evento():
    df = pd.DataFrame([municipio()])
    linha = projetar(df, NEGOCIO).iloc[0]
    pares = linha["ponto_equilibrio_vendas"]
    margem_por_par = linha["ticket_estimado"] * (2 / 3)
    assert pares * margem_por_par == pytest.approx(linha["custo_evento"], rel=1e-3)


# ------------------------------------------------- a identidade do potencial
def test_potencial_e_exatamente_o_produto_dos_tres_fatores_mostrados_na_ficha():
    """O numero da tela precisa ser reconstruivel a partir da explicacao da tela."""
    df = pd.DataFrame(
        [
            municipio(codigo_ibge="4200051", populacao_40mais=2_000, qtd_oticas=1),
            municipio(codigo_ibge="4200101", populacao_40mais=9_000, qtd_oticas=9, renda_mediana=3800),
            municipio(codigo_ibge="4200200", populacao_40mais=5_000, distancia_km=15.0),
        ]
    )
    saida = projetar(df, NEGOCIO)
    for _, linha in saida.iterrows():
        f = linha["projecao"]["fatores"]
        reconstruido = 100 * f["ocupacao_agenda"] * f["forca_conversao"] * f["nivel_ticket"]
        assert linha["potencial_pct"] == pytest.approx(reconstruido, abs=0.05)


def test_potencial_nunca_passa_de_cem():
    df = pd.DataFrame([municipio(populacao_40mais=500_000, qtd_oticas=0, renda_mediana=9_000)])
    assert projetar(df, NEGOCIO).iloc[0]["potencial_pct"] <= 100


# ---------------------------------------------------------- dado ausente
def test_sem_populacao_40mais_nao_ha_projecao_e_o_motivo_fica_registrado():
    df = pd.DataFrame([municipio(populacao_40mais=None)])
    linha = projetar(df, NEGOCIO).iloc[0]
    assert linha["faturamento_estimado"] is None
    assert linha["projecao"]["disponivel"] is False
    assert "populacao_40mais" in linha["projecao"]["faltando"]


def test_sem_cnes_nao_ha_projecao__zero_oftalmo_e_coisa_diferente_de_desconhecido():
    sem_cnes = projetar(
        pd.DataFrame([municipio(qtd_oftalmologistas=None, oftalmo_equivalente=None)]), NEGOCIO
    ).iloc[0]
    assert sem_cnes["faturamento_estimado"] is None
    assert "cnes" in sem_cnes["projecao"]["faltando"]

    com_cnes_zerado = projetar(pd.DataFrame([municipio(qtd_oftalmologistas=0)]), NEGOCIO).iloc[0]
    assert com_cnes_zerado["faturamento_estimado"] is not None


def test_places_ausente_vira_imputacao_marcada_e_derruba_a_confianca():
    df = pd.DataFrame(
        [
            municipio(codigo_ibge="4200051", qtd_oticas=6, oticas_nota_media=4.2, oticas_avaliacoes=300),
            municipio(codigo_ibge="4200101", qtd_oticas=None, oticas_nota_media=None, oticas_avaliacoes=None),
        ]
    )
    saida = projetar(df, NEGOCIO)
    conhecido, ausente = saida.iloc[0], saida.iloc[1]

    assert conhecido["projecao_confianca"] == 1.0
    assert ausente["projecao_confianca"] < conhecido["projecao_confianca"]
    assert "qtd_oticas" in ausente["projecao"]["imputados"]
    # imputado, mas ainda assim projetado: o municipio nao some do ranking
    assert ausente["faturamento_estimado"] is not None


def test_distancia_ausente_e_imputada_pela_mediana_do_universo():
    df = pd.DataFrame(
        [
            municipio(codigo_ibge="4200051", distancia_km=40.0),
            municipio(codigo_ibge="4200101", distancia_km=80.0),
            municipio(codigo_ibge="4200200", distancia_km=None),
        ]
    )
    saida = projetar(df, NEGOCIO)
    imputado = saida[saida["codigo_ibge"] == "4200200"].iloc[0]
    esperado = atrito_deslocamento(60.0, NEGOCIO["demanda"])  # mediana de 40 e 80
    assert imputado["projecao"]["funil"]["atrito_deslocamento"] == pytest.approx(esperado, abs=1e-3)
    assert "distancia_km" in imputado["projecao"]["imputados"]


# -------------------------------------------------------- agenda e circuito
def test_demanda_acima_da_agenda_vira_dias_sugeridos_em_vez_de_sumir():
    grande = projetar(pd.DataFrame([municipio(populacao_40mais=40_000)]), NEGOCIO).iloc[0]
    assert grande["consultas_esperadas"] == 135  # 3 dias x 45
    assert grande["demanda_nao_capturada"] > 0
    assert grande["dias_sugeridos"] > 3


def test_circuito_paga_o_deslocamento_uma_vez_so():
    df = pd.DataFrame(
        [
            municipio(codigo_ibge="4200051", circuito=0),
            municipio(codigo_ibge="4200101", circuito=0),
            municipio(codigo_ibge="4200200", circuito=0),
        ]
    )
    projetado = projetar(df, NEGOCIO)
    circuitos = projecao_de_circuito(projetado, NEGOCIO)
    assert len(circuitos) == 1

    linha = circuitos.iloc[0]
    soma_municipios = float(projetado["lucro_estimado"].sum())
    # Com 3 cidades e cidades_por_circuito=3, a diluicao ja estava certa.
    assert linha["lucro"] == pytest.approx(soma_municipios, abs=0.01)
    assert linha["municipios"] == 3


def test_circuito_menor_que_o_configurado_perde_a_diluicao_otimista():
    """Duas cidades dividindo um deslocamento orcado para tres pagam mais cada."""
    df = pd.DataFrame(
        [municipio(codigo_ibge="4200051", circuito=0), municipio(codigo_ibge="4200101", circuito=0)]
    )
    projetado = projetar(df, NEGOCIO)
    circuitos = projecao_de_circuito(projetado, NEGOCIO)
    soma_municipios = float(projetado["lucro_estimado"].sum())
    # 2 cidades pagaram 900/3 cada = 600; o deslocamento real e 900 → 300 a menos de lucro
    assert circuitos.iloc[0]["lucro"] == pytest.approx(soma_municipios - 300, abs=0.01)


def test_dataframe_vazio_nao_quebra():
    vazio = pd.DataFrame(columns=["codigo_ibge", "populacao_40mais", "qtd_oftalmologistas"])
    saida = projetar(vazio, NEGOCIO)
    assert saida.empty
    assert "faturamento_estimado" in saida.columns


def test_teto_de_faturamento_e_agenda_cheia_vezes_conversao_e_ticket_maximos():
    assert teto_faturamento(NEGOCIO) == pytest.approx(3 * 45 * 0.70 * 2600)


def test_nan_do_pandas_nao_passa_por_numero():
    """NaN vindo de merge nao pode ser tratado como valor — vira ausencia."""
    df = pd.DataFrame([municipio(renda_mediana=np.nan, oticas_nota_media=np.nan)])
    linha = projetar(df, NEGOCIO).iloc[0]
    assert linha["ticket_estimado"] == 1500
    assert "renda_mediana" in linha["projecao"]["imputados"]


def test_cidade_sem_otica_nao_herda_a_reputacao_mediana_do_estado():
    """Zero óticas é ausência de concorrente, não dado faltando.

    Antes desta regra, o município mais virgem do estado levava a nota média da
    concorrência por imputação — e era penalizado justamente por não ter nenhuma.
    """
    df = pd.DataFrame(
        [
            municipio(codigo_ibge="4200051", qtd_oticas=6, oticas_nota_media=4.6, oticas_avaliacoes=400),
            municipio(codigo_ibge="4200101", qtd_oticas=0, oticas_nota_media=None, oticas_avaliacoes=0),
        ]
    )
    saida = projetar(df, NEGOCIO)
    virgem = saida[saida["codigo_ibge"] == "4200101"].iloc[0]

    assert virgem["conversao"] == pytest.approx(NEGOCIO["conversao"]["base"])
    assert "reputacao_oticas" not in (virgem["projecao"]["imputados"] or [])
    assert virgem["projecao_confianca"] == 1.0
    assert virgem["projecao"]["concorrencia"]["reputacao"]["fator"] == 0.0
