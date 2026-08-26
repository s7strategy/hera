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

from mapa_optico.score import projecao
from mapa_optico.score.projecao import (
    atrito_deslocamento,
    capacidade_local_anual,
    cmv_fracao,
    custo_do_evento,
    custo_do_par,
    forca_concorrencia,
    margem_por_par,
    projecao_de_circuito,
    projetar,
    teto_faturamento,
    ticket_da_cidade,
)

NEGOCIO = {
    "versao": "teste",
    "venda": {
        "ticket_medio": 750,
        "ticket_min": 400,
        "ticket_max": 1200,
        "custo_par": {
            "ticket_baixo": 400,
            "custo_baixo": 40,
            "ticket_alto": 1200,
            "custo_alto": 180,
            "custo_maximo": 220,
        },
        "renda_referencia": 2200,
        "elasticidade_renda": 0.35,
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


# ------------------------------------------------------- venda e custo do par
def test_custo_do_par_bate_nos_dois_pontos_informados():
    venda = NEGOCIO["venda"]
    assert custo_do_par(400, venda) == pytest.approx(40)
    assert custo_do_par(1200, venda) == pytest.approx(180)


def test_custo_do_par_nao_e_fracao_fixa_do_ticket():
    """A correcao que motivou refazer o modelo.

    Par de R$ 400 custa 10% do preco; par de R$ 1.200 custa 15%. Uma fracao unica
    erraria os dois extremos ao mesmo tempo. A fracao tem que SUBIR com o ticket.
    """
    venda = NEGOCIO["venda"]
    barato = cmv_fracao(400, venda)
    caro = cmv_fracao(1200, venda)
    assert barato == pytest.approx(0.10)
    assert caro == pytest.approx(0.15)
    assert caro > barato, "lente melhor custa proporcionalmente mais"


def test_custo_do_par_interpola_no_meio_da_faixa():
    venda = NEGOCIO["venda"]
    # 800 esta na metade entre 400 e 1200 → custo na metade entre 40 e 180
    assert custo_do_par(800, venda) == pytest.approx(110)


def test_custo_do_par_respeita_o_teto_absoluto():
    venda = {**NEGOCIO["venda"], "custo_par": {**NEGOCIO["venda"]["custo_par"], "custo_alto": 900}}
    assert custo_do_par(1200, venda) == 220


def test_margem_por_par_e_o_que_sobra_de_verdade():
    venda = NEGOCIO["venda"]
    assert margem_por_par(400, venda) == pytest.approx(360)  # 90% do preco
    assert margem_por_par(1200, venda) == pytest.approx(1020)  # 85% do preco


def test_sem_curva_de_custo_cai_para_o_valor_unico_e_nao_para_zero():
    """Config antiga ou incompleta nao pode virar 'custo zero', que inflaria o lucro."""
    venda = {"ticket_medio": 750, "custo_produto": 120}
    assert custo_do_par(750, venda) == pytest.approx(120)


def test_ticket_sobe_e_desce_com_a_renda_dentro_dos_limites():
    venda = NEGOCIO["venda"]
    na_referencia, imputado = ticket_da_cidade(2200, venda)
    assert na_referencia == pytest.approx(750)
    assert imputado is False

    rico, _ = ticket_da_cidade(4400, venda)  # o dobro da referencia
    assert rico == pytest.approx(750 * 1.35)

    pobre, _ = ticket_da_cidade(1100, venda)  # metade da referencia
    assert pobre == pytest.approx(750 * 0.825)

    # Com elasticidade 0,35 o ticket so anda 35% para cada lado, entao o piso e o
    # teto do YAML nao chegam a morder — a elasticidade e que limita.
    assert ticket_da_cidade(1, venda)[0] == pytest.approx(750 * 0.65, rel=1e-3)

    # Com elasticidade alta eles mordem, e e isso que impede ticket fora da faixa.
    agressivo = {**venda, "elasticidade_renda": 3.0}
    assert ticket_da_cidade(200, agressivo)[0] == 400
    assert ticket_da_cidade(9_000, agressivo)[0] == 1200


def test_sem_renda_o_ticket_e_o_medio_e_o_campo_fica_marcado():
    ticket, imputado = ticket_da_cidade(None, NEGOCIO["venda"])
    assert ticket == 750
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
    # A margem sai do custo DAQUELE ticket, nao de uma fracao fixa.
    unitario = margem_por_par(linha["ticket_estimado"], NEGOCIO["venda"])
    assert linha["margem_bruta"] == pytest.approx(linha["vendas_esperadas"] * unitario, rel=1e-3)
    assert linha["lucro_estimado"] == pytest.approx(
        linha["margem_bruta"] - linha["custo_evento"], rel=1e-3
    )


def test_ponto_de_equilibrio_e_quantos_pares_pagam_o_evento():
    df = pd.DataFrame([municipio()])
    linha = projetar(df, NEGOCIO).iloc[0]
    unitario = margem_por_par(linha["ticket_estimado"], NEGOCIO["venda"])
    # O campo e arredondado para uma casa, entao a conferencia e sobre os pares,
    # nao sobre o produto: 0,05 par de folga vale dezenas de reais.
    assert linha["ponto_equilibrio_vendas"] == pytest.approx(
        linha["custo_evento"] / unitario, abs=0.05
    )


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
    assert teto_faturamento(NEGOCIO) == pytest.approx(3 * 45 * 0.70 * 1200)


def test_nan_do_pandas_nao_passa_por_numero():
    """NaN vindo de merge nao pode ser tratado como valor — vira ausencia."""
    df = pd.DataFrame([municipio(renda_mediana=np.nan, oticas_nota_media=np.nan)])
    linha = projetar(df, NEGOCIO).iloc[0]
    assert linha["ticket_estimado"] == 750
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


# --------------------------------------------------------------- médicos
def test_dois_medicos_dobram_a_agenda():
    """Dois médicos atendendo juntos atendem o dobro no mesmo evento."""
    um = dict(NEGOCIO["evento"], medicos=1)
    dois = dict(NEGOCIO["evento"], medicos=2)
    assert projecao.capacidade_da_agenda(dois) == 2 * projecao.capacidade_da_agenda(um)


def test_medico_a_mais_custa_a_mais_mas_estrutura_nao_dobra():
    """Só o médico escala com quantos vão; sala e mídia são as mesmas."""
    um = projecao.custo_do_evento(dict(NEGOCIO["evento"], medicos=1))
    dois = projecao.custo_do_evento(dict(NEGOCIO["evento"], medicos=2))
    assert dois["medico"] == 2 * um["medico"]
    assert dois["estrutura"] == um["estrutura"]
    assert dois["midia"] == um["midia"]
    assert dois["total"] < 2 * um["total"], "dobrar médico não dobra o custo do evento"


def test_medicos_ausente_ou_zero_vale_um():
    assert projecao.medicos_no_evento({}) == 1.0
    assert projecao.medicos_no_evento({"medicos": 0}) == 1.0


# -------------------------------------------------------------- crediário
def test_crediario_solta_o_ticket_da_renda_local():
    """É para isso que o crediário serve: a decisão vira a parcela, não o preço."""
    renda_baixa = 700.0
    sem = dict(NEGOCIO["venda"], alcance_crediario=0.0)
    com = dict(NEGOCIO["venda"], alcance_crediario=1.0, elasticidade_residual_crediario=0.25)

    ticket_sem, _ = projecao.ticket_da_cidade(renda_baixa, sem)
    ticket_com, _ = projecao.ticket_da_cidade(renda_baixa, com)

    assert ticket_com > ticket_sem, "com crediário a renda baixa derruba menos o ticket"
    # E não anula: renda baixa ainda pesa alguma coisa.
    assert ticket_com < NEGOCIO["venda"]["ticket_medio"]


def test_crediario_nao_inventa_ticket_em_cidade_rica():
    """Onde a renda já é alta, o crediário não deveria mudar quase nada."""
    sem = dict(NEGOCIO["venda"], alcance_crediario=0.0)
    com = dict(NEGOCIO["venda"], alcance_crediario=1.0)
    t_sem, _ = projecao.ticket_da_cidade(NEGOCIO["venda"]["renda_referencia"], sem)
    t_com, _ = projecao.ticket_da_cidade(NEGOCIO["venda"]["renda_referencia"], com)
    assert t_sem == pytest.approx(t_com), "na renda de referência o ajuste é nulo dos dois jeitos"


def test_alcance_do_crediario_e_monotonico():
    renda = 700.0
    tickets = [
        projecao.ticket_da_cidade(renda, dict(NEGOCIO["venda"], alcance_crediario=a))[0]
        for a in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]
    assert tickets == sorted(tickets), "mais crediário nunca pode reduzir o ticket"
