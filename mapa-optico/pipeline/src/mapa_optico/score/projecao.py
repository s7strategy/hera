"""Projecao financeira por municipio: de habitante a lucro, sem caixa preta.

O score de weights.yaml responde ONDE ha demanda reprimida — e um ranking
relativo, adimensional. Este modulo responde QUANTO isso vira dinheiro, em
reais, e por que.

A cadeia inteira:

    populacao 40+
      x prevalencia de necessidade de correcao
      x renovacao anual de receita              = demanda anual da cidade
      - capacidade instalada dos oftalmos locais (CNES: carga horaria real)
                                                = demanda nao atendida
      x atrito de deslocamento ate o polo       = demanda represada AQUI
      x anos de backlog acumulado               = publico de um primeiro evento
      x alcance da midia
      x taxa de agendamento
      x comparecimento                          = quem senta na cadeira
      LIMITADO PELA AGENDA FISICA DO MEDICO     = consultas
      x conversao em venda (derrubada pelas oticas locais)
                                                = pares vendidos
      x ticket (modulado pela renda)            = faturamento
      - CMV - custo do evento - midia           = lucro

Duas decisoes que sustentam o resto:

1. TETO FISICO. Um medico faz N refracoes por dia; um evento de 3 dias tem um
   teto de consultas que nenhuma cidade grande ultrapassa. Sem esse teto, o
   ranking viraria "ordene por populacao" — que e exatamente o chute que este
   sistema existe para substituir.

2. O "% de possibilidade" E O FATURAMENTO CONTRA O TETO TEORICO, e por
   construcao se decompoe em tres fatores multiplicativos:

       potencial = ocupacao_da_agenda x (conversao / conversao_max) x (ticket / ticket_max)

   ocupacao vem dos MEDICOS e da distancia; conversao vem das OTICAS, suas
   NOTAS e o volume de AVALIACOES; ticket vem da renda. Os tres aparecem
   separados na ficha do municipio: da para discordar de um sem descartar o
   resto.

Dado ausente nao vira zero. Vira imputacao pela mediana do universo, marcada
como imputada em `componentes` e descontada de `projecao_confianca`.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ..logs import etapa, log

# Entradas sem as quais nao existe projecao — nao ha o que imputar.
OBRIGATORIAS = ("populacao_40mais", "cnes")

# Quanto cada imputacao custa de confianca na projecao.
PENALIDADE = {
    "distancia_km": 0.30,
    "qtd_oticas": 0.30,
    "reputacao_oticas": 0.10,
    "renda_mediana": 0.10,
}

COLUNAS_PROJECAO = [
    "demanda_anual",
    "capacidade_local_ano",
    "demanda_nao_atendida",
    "demanda_represada",
    "publico_evento",
    "agendamentos_esperados",
    "consultas_esperadas",
    "capacidade_evento",
    "ocupacao_agenda",
    "conversao",
    "vendas_esperadas",
    "ticket_estimado",
    "faturamento_estimado",
    "margem_bruta",
    "custo_evento",
    "lucro_estimado",
    "retorno_sobre_custo",
    "ponto_equilibrio_vendas",
    "dias_sugeridos",
    "demanda_nao_capturada",
    "potencial_pct",
    "projecao_confianca",
]


def _num(valor: Any) -> float | None:
    """None para qualquer coisa que nao seja numero finito. NaN nao passa."""
    if valor is None:
        return None
    try:
        f = float(valor)
    except (TypeError, ValueError):
        return None
    return None if not np.isfinite(f) else f


def _clamp(v: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, v))


def _mediana(serie: pd.Series) -> float | None:
    validos = pd.to_numeric(serie, errors="coerce").dropna()
    return float(validos.median()) if len(validos) else None


def custo_do_par(ticket: float, venda: dict[str, Any]) -> float:
    """Quanto o par custa do fornecedor, para um ticket de venda.

    NAO E FRACAO FIXA DO TICKET, e essa foi a correcao mais importante do modelo.
    Com par de R$ 400 custando R$ 40 (10%) e par de R$ 1.200 custando R$ 180
    (15%), a fracao SOBE com o preco: lente melhor custa proporcionalmente mais.
    Uma fracao unica erraria os dois extremos ao mesmo tempo — subestimaria o
    custo da linha de cima e superestimaria o da linha de baixo.

    Interpola linearmente entre os dois pontos informados. O ticket ja chega aqui
    limitado a faixa praticada, entao nunca extrapolamos para fora do que a
    operacao de fato conhece. O teto absoluto ainda vale como trava.
    """
    cfg = venda.get("custo_par") or {}
    t_baixo = _num(cfg.get("ticket_baixo"))
    c_baixo = _num(cfg.get("custo_baixo"))
    t_alto = _num(cfg.get("ticket_alto"))
    c_alto = _num(cfg.get("custo_alto"))
    teto = _num(cfg.get("custo_maximo"))

    if None in (t_baixo, c_baixo, t_alto, c_alto) or t_alto == t_baixo:
        # Sem os dois pontos nao ha curva. Cai para o par informado no ticket
        # medio, que e o melhor que resta — nunca para zero.
        base = _num(venda.get("custo_produto"))
        if base is None:
            return 0.0
        return _clamp(base, 0.0, teto if teto is not None else base)

    fatia = (ticket - t_baixo) / (t_alto - t_baixo)
    custo = c_baixo + (c_alto - c_baixo) * fatia
    piso = 0.0
    return _clamp(custo, piso, teto if teto is not None else float("inf"))


def cmv_fracao(ticket: float, venda: dict[str, Any]) -> float:
    """Fracao do ticket que vai para o fornecedor NAQUELE ticket. So para exibir."""
    if ticket <= 0:
        return 0.0
    return _clamp(custo_do_par(ticket, venda) / ticket, 0.0, 0.95)


def elasticidade_efetiva(venda: dict[str, Any]) -> float:
    """Quanto a renda local ainda puxa o ticket, depois do crediario.

    Sem crediario, quem ganha pouco compra o par barato: a renda do mes decide
    a compra. O crediario existe justamente para quebrar esse vinculo — a
    decisao passa a ser sobre a parcela, nao sobre o preco. Nao anula o efeito
    (renda baixa ainda limita), mas reduz muito.

    `alcance_crediario` vai de 0 (nao vendo a prazo) a 1 (praticamente todo
    mundo leva no crediario).
    """
    elasticidade = _num(venda.get("elasticidade_renda")) or 0.0
    alcance = _clamp(_num(venda.get("alcance_crediario")) or 0.0, 0.0, 1.0)
    residual = _clamp(_num(venda.get("elasticidade_residual_crediario")) or 0.25, 0.0, 1.0)
    # Com alcance total, sobra so a fracao residual da sensibilidade a renda.
    return elasticidade * (1.0 - alcance * (1.0 - residual))


def ticket_da_cidade(renda: float | None, venda: dict[str, Any]) -> tuple[float, bool]:
    """Ticket modulado pela renda mediana. Retorna (ticket, foi_imputado)."""
    base = _num(venda.get("ticket_medio")) or 0.0
    if renda is None:
        return base, True
    referencia = _num(venda.get("renda_referencia")) or 0.0
    if referencia <= 0:
        return base, False
    elasticidade = elasticidade_efetiva(venda)
    ajustado = base * (1.0 + elasticidade * (renda / referencia - 1.0))
    piso = _num(venda.get("ticket_min")) or 0.0
    teto = _num(venda.get("ticket_max")) or base
    return _clamp(ajustado, piso, teto), False


def capacidade_local_anual(
    horas_semanais: float | None, oftalmo_equivalente: float | None, demanda: dict[str, Any]
) -> float:
    """Consultas de refracao que os oftalmologistas da propria cidade dao por ano.

    Vem da carga horaria ambulatorial do CNES — e o que separa "cidade com um
    oftalmo de 4h por semana" de "cidade com tres de 40h". Sem esse campo, cai
    para uma carga horaria padrao por profissional, marcada no componente.
    """
    semanas = _num(demanda.get("semanas_por_ano")) or 44.0
    por_hora = _num(demanda.get("consultas_refracao_por_hora")) or 2.5
    fracao = _num(demanda.get("fracao_tempo_em_refracao")) or 0.45
    if horas_semanais is None or horas_semanais <= 0:
        equivalentes = oftalmo_equivalente or 0.0
        horas_semanais = equivalentes * (_num(demanda.get("horas_semanais_fallback")) or 20.0)
    return max(0.0, horas_semanais * semanas * por_hora * fracao)


def atrito_deslocamento(distancia_km: float | None, demanda: dict[str, Any]) -> float | None:
    """Fracao da demanda nao atendida que NAO se resolve viajando ate o polo.

    Colado no polo, quase todo mundo resolve la (atrito baixo). A 120 km, quase
    ninguem viaja de rotina para consultar (atrito ~1). O piso existe porque
    mesmo ao lado do polo ha quem nao va: custo, transporte, idoso sozinho.
    """
    if distancia_km is None:
        return None
    saturacao = _num(demanda.get("atrito_saturacao_km")) or 120.0
    minimo = _num(demanda.get("atrito_minimo")) or 0.0
    if saturacao <= 0:
        return 1.0
    return minimo + (1.0 - minimo) * _clamp(distancia_km / saturacao, 0.0, 1.0)


def forca_concorrencia(
    oticas_por_10k: float | None,
    nota_media: float | None,
    avaliacoes_por_mil: float | None,
    cfg: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """Conversao em venda, derrubada pela concorrencia local.

    Tres sinais independentes, e os tres saem do Google Places:

      QUANTIDADE  oticas por 10 mil habitantes — mercado saturado converte menos.
      NOTA        media das avaliacoes — concorrente bem avaliado segura o cliente;
                  concorrente com nota 3 e oportunidade, nao ameaca.
      VOLUME      avaliacoes por mil habitantes — proxy de quanto comercio otico
                  a cidade realmente movimenta. Trinta oticas sem avaliacao
                  nenhuma pesam menos que tres oticas com 400 avaliacoes.
    """
    base = _num(cfg.get("base")) or 0.4
    detalhe: dict[str, Any] = {}

    f_sat = 0.0
    if oticas_por_10k is not None:
        referencia = _num(cfg.get("saturacao_referencia")) or 4.0
        f_sat = _clamp(oticas_por_10k / referencia, 0.0, 1.0) if referencia > 0 else 0.0
    detalhe["saturacao"] = {"valor": oticas_por_10k, "fator": round(f_sat, 3)}

    f_rep = 0.0
    if nota_media is not None:
        neutra = _num(cfg.get("nota_neutra")) or 4.0
        # nota (neutra-1) -> 0 (concorrente fraco, sem penalidade)
        # nota (neutra+1) -> 1 (concorrente forte, penalidade cheia)
        f_rep = _clamp((nota_media - (neutra - 1.0)) / 2.0, 0.0, 1.0)
    detalhe["reputacao"] = {"valor": nota_media, "fator": round(f_rep, 3)}

    f_pres = 0.0
    if avaliacoes_por_mil is not None:
        referencia = _num(cfg.get("avaliacoes_referencia")) or 40.0
        f_pres = _clamp(avaliacoes_por_mil / referencia, 0.0, 1.0) if referencia > 0 else 0.0
    detalhe["presenca"] = {"valor": avaliacoes_por_mil, "fator": round(f_pres, 3)}

    conversao = base
    conversao *= 1.0 - (_num(cfg.get("peso_saturacao")) or 0.0) * f_sat
    conversao *= 1.0 - (_num(cfg.get("peso_reputacao")) or 0.0) * f_rep
    conversao *= 1.0 - (_num(cfg.get("peso_presenca")) or 0.0) * f_pres
    conversao = _clamp(
        conversao, _num(cfg.get("minimo")) or 0.0, _num(cfg.get("maximo")) or 1.0
    )
    detalhe["conversao"] = round(conversao, 4)
    return conversao, detalhe


def medicos_no_evento(evento: dict[str, Any]) -> float:
    """Quantos medicos atendem ao mesmo tempo. Dobra a agenda e dobra o custo."""
    return max(1.0, _num(evento.get("medicos")) or 1.0)


def capacidade_da_agenda(evento: dict[str, Any]) -> float:
    """Teto fisico de consultas do evento: dias x consultas por dia x medicos.

    E o que impede o ranking de virar "ordene por populacao": por maior que
    seja a cidade, ninguem atende mais do que cabe na agenda.
    """
    dias = _num(evento.get("dias")) or 1.0
    por_dia = _num(evento.get("consultas_por_dia")) or 1.0
    return dias * por_dia * medicos_no_evento(evento)


def custo_do_evento(evento: dict[str, Any]) -> dict[str, float]:
    """Custo de rodar o evento numa cidade, com o deslocamento diluido no circuito."""
    dias = _num(evento.get("dias")) or 1.0
    # O medico e o unico custo que escala com quantos vao: estrutura e midia
    # sao os mesmos para um ou para tres.
    medico = (_num(evento.get("custo_medico_dia")) or 0.0) * dias * medicos_no_evento(evento)
    estrutura = (_num(evento.get("custo_estrutura_dia")) or 0.0) * dias
    cidades = max(1.0, _num(evento.get("cidades_por_circuito")) or 1.0)
    deslocamento = (_num(evento.get("custo_deslocamento")) or 0.0) / cidades
    midia = _num(evento.get("investimento_midia")) or 0.0
    return {
        "medico": medico,
        "estrutura": estrutura,
        "deslocamento": deslocamento,
        "midia": midia,
        "total": medico + estrutura + deslocamento + midia,
    }


def teto_faturamento(negocio: dict[str, Any]) -> float:
    """Faturamento de uma cidade perfeita: agenda cheia, conversao maxima, ticket maximo.

    E o denominador do "% de possibilidade". Como e o mesmo para todos os
    municipios, o percentual e comparavel entre cidades.
    """
    evento = negocio.get("evento", {})
    capacidade = capacidade_da_agenda(evento)
    conv_max = _num(negocio.get("conversao", {}).get("maximo")) or 1.0
    ticket_max = _num(negocio.get("venda", {}).get("ticket_max")) or 1.0
    return max(1e-9, capacidade * conv_max * ticket_max)


def margem_por_par(ticket: float, venda: dict[str, Any]) -> float:
    """Quanto sobra em cada par vendido, depois do fornecedor."""
    return max(0.0, ticket - custo_do_par(ticket, venda))


def projetar(df: pd.DataFrame, negocio: dict[str, Any]) -> pd.DataFrame:
    """Adiciona as colunas de projecao financeira ao ranking.

    Espera as colunas ja montadas pelo pipeline (populacao_40mais, CNES, oticas,
    distancia ao polo, renda). Devolve o mesmo DataFrame com COLUNAS_PROJECAO e
    a coluna `projecao` (dict) que vira o JSONB e alimenta a ficha.
    """
    venda = negocio.get("venda", {})
    evento = negocio.get("evento", {})
    demanda_cfg = negocio.get("demanda", {})
    captacao = negocio.get("captacao", {})
    conversao_cfg = negocio.get("conversao", {})

    with etapa("projecao.calcular") as c:
        c.entrada = len(df)
        saida = df.copy()
        if saida.empty:
            for col in COLUNAS_PROJECAO:
                saida[col] = []
            saida["projecao"] = []
            c.saida = 0
            return saida

        # Medianas do universo para imputar o que faltar — nunca zero silencioso.
        pop_total = pd.to_numeric(saida.get("populacao_total"), errors="coerce")
        qtd_oticas = pd.to_numeric(saida.get("qtd_oticas"), errors="coerce")
        oticas_10k = (qtd_oticas / pop_total.replace(0, np.nan)) * 10_000
        avaliacoes = pd.to_numeric(saida.get("oticas_avaliacoes"), errors="coerce")
        avaliacoes_mil = (avaliacoes / pop_total.replace(0, np.nan)) * 1_000
        mediana_oticas = _mediana(oticas_10k)
        mediana_avaliacoes = _mediana(avaliacoes_mil)
        mediana_nota = _mediana(saida.get("oticas_nota_media", pd.Series(dtype="float64")))
        mediana_distancia = _mediana(saida.get("distancia_km", pd.Series(dtype="float64")))

        custos = custo_do_evento(evento)
        capacidade_evento = capacidade_da_agenda(evento)
        midia = _num(evento.get("investimento_midia")) or 0.0
        alcance = min(
            _num(captacao.get("alcance_maximo")) or 1.0,
            (_num(captacao.get("alcance_por_mil_reais")) or 0.0) * (midia / 1000.0),
        )
        teto = teto_faturamento(negocio)
        conv_max = _num(conversao_cfg.get("maximo")) or 1.0
        ticket_max = _num(venda.get("ticket_max")) or 1.0

        linhas: list[dict[str, Any]] = []
        colunas: dict[str, list[Any]] = {col: [] for col in COLUNAS_PROJECAO}

        for idx in saida.index:
            imputados: list[str] = []
            pop40 = _num(saida.at[idx, "populacao_40mais"]) if "populacao_40mais" in saida else None
            qtd_oft = _num(saida.at[idx, "qtd_oftalmologistas"]) if "qtd_oftalmologistas" in saida else None
            oft_eq = _num(saida.at[idx, "oftalmo_equivalente"]) if "oftalmo_equivalente" in saida else None
            horas = _num(saida.at[idx, "horas_semanais_total"]) if "horas_semanais_total" in saida else None

            # Sem mercado ou sem oferta conhecida nao ha projecao. Nada de imputar
            # o essencial: a linha fica nula e a interface diz por que.
            falta = []
            if pop40 is None:
                falta.append("populacao_40mais")
            if qtd_oft is None and oft_eq is None:
                falta.append("cnes")
            if falta:
                for col in COLUNAS_PROJECAO:
                    colunas[col].append(None)
                linhas.append({"disponivel": False, "faltando": falta})
                continue

            # ------------------------------------------------------ demanda
            demanda_anual = (
                pop40
                * (_num(demanda_cfg.get("prevalencia_40mais")) or 0.0)
                * (_num(demanda_cfg.get("renovacao_anual")) or 0.0)
            )
            capacidade_local = capacidade_local_anual(horas, oft_eq if oft_eq is not None else qtd_oft, demanda_cfg)
            nao_atendida = max(0.0, demanda_anual - capacidade_local)

            distancia = _num(saida.at[idx, "distancia_km"]) if "distancia_km" in saida else None
            if distancia is None and mediana_distancia is not None:
                distancia = mediana_distancia
                imputados.append("distancia_km")
            atrito = atrito_deslocamento(distancia, demanda_cfg)
            if atrito is None:
                atrito = 1.0
                if "distancia_km" not in imputados:
                    imputados.append("distancia_km")

            represada = nao_atendida * atrito
            backlog = _num(demanda_cfg.get("backlog_anos")) or 1.0
            publico = represada * backlog

            # ------------------------------------------------------ captacao
            alcancados = publico * alcance
            agendamentos = alcancados * (_num(captacao.get("taxa_agendamento")) or 0.0)
            comparecimentos = agendamentos * (_num(captacao.get("taxa_comparecimento")) or 0.0)
            consultas = min(comparecimentos, capacidade_evento)
            ocupacao = _clamp(comparecimentos / capacidade_evento, 0.0, 1.0) if capacidade_evento else 0.0

            # Quando a procura passa do que o medico consegue atender, o excedente
            # nao some: vira dia a mais de evento ou uma segunda visita. Sem isto o
            # modelo diria que uma cidade de 12 mil e uma de 35 mil rendem igual,
            # o que so e verdade se ninguem esticar a agenda.
            por_dia = _num(evento.get("consultas_por_dia")) or 1.0
            dias_cfg = _num(evento.get("dias")) or 1.0
            dias_sugeridos = max(dias_cfg, np.ceil(comparecimentos / por_dia)) if por_dia > 0 else dias_cfg
            nao_capturada = max(0.0, comparecimentos - capacidade_evento)

            # ----------------------------------------------------- conversao
            o10k = _num(oticas_10k.get(idx))
            if o10k is None and mediana_oticas is not None:
                o10k = mediana_oticas
                imputados.append("qtd_oticas")
            nota = _num(saida.at[idx, "oticas_nota_media"]) if "oticas_nota_media" in saida else None
            aval_mil = _num(avaliacoes_mil.get(idx))

            # Cidade SEM otica nao tem reputacao de concorrente para imputar — e a
            # ausencia aqui e informacao, nao buraco: nao ha quem segure o cliente.
            # Imputar a mediana puniria justamente a cidade mais virgem do estado.
            sem_concorrente = o10k is not None and o10k == 0 and "qtd_oticas" not in imputados
            if not sem_concorrente:
                if nota is None and mediana_nota is not None and "qtd_oticas" not in imputados:
                    nota = mediana_nota
                    imputados.append("reputacao_oticas")
                if aval_mil is None and mediana_avaliacoes is not None and "qtd_oticas" not in imputados:
                    aval_mil = mediana_avaliacoes
                    if "reputacao_oticas" not in imputados:
                        imputados.append("reputacao_oticas")
            conversao, detalhe_conv = forca_concorrencia(o10k, nota, aval_mil, conversao_cfg)
            vendas = consultas * conversao

            # -------------------------------------------------------- dinheiro
            renda = _num(saida.at[idx, "renda_mediana"]) if "renda_mediana" in saida else None
            ticket, ticket_imputado = ticket_da_cidade(renda, venda)
            if ticket_imputado:
                imputados.append("renda_mediana")
            faturamento = vendas * ticket
            custo_unitario = custo_do_par(ticket, venda)
            margem_unitaria = ticket - custo_unitario
            margem = vendas * margem_unitaria
            lucro = margem - custos["total"]
            retorno = lucro / custos["total"] if custos["total"] > 0 else None
            equilibrio = custos["total"] / margem_unitaria if margem_unitaria > 0 else None
            cmv = custo_unitario / ticket if ticket > 0 else 0.0

            potencial = _clamp(100.0 * faturamento / teto, 0.0, 100.0)
            confianca = round(max(0.0, 1.0 - sum(PENALIDADE.get(i, 0.0) for i in imputados)), 3)

            valores = {
                "demanda_anual": round(demanda_anual, 1),
                "capacidade_local_ano": round(capacidade_local, 1),
                "demanda_nao_atendida": round(nao_atendida, 1),
                "demanda_represada": round(represada, 1),
                "publico_evento": round(publico, 1),
                "agendamentos_esperados": round(agendamentos, 1),
                "consultas_esperadas": round(consultas, 1),
                "capacidade_evento": round(capacidade_evento, 1),
                "ocupacao_agenda": round(ocupacao, 4),
                "conversao": round(conversao, 4),
                "vendas_esperadas": round(vendas, 1),
                "ticket_estimado": round(ticket, 2),
                "faturamento_estimado": round(faturamento, 2),
                "margem_bruta": round(margem, 2),
                "custo_evento": round(custos["total"], 2),
                "lucro_estimado": round(lucro, 2),
                "retorno_sobre_custo": None if retorno is None else round(retorno, 4),
                "ponto_equilibrio_vendas": None if equilibrio is None else round(equilibrio, 1),
                "dias_sugeridos": int(dias_sugeridos),
                "demanda_nao_capturada": round(nao_capturada, 1),
                "potencial_pct": round(potencial, 2),
                "projecao_confianca": confianca,
            }
            for col in COLUNAS_PROJECAO:
                colunas[col].append(valores[col])

            linhas.append(
                {
                    "disponivel": True,
                    "imputados": imputados,
                    # Os tres fatores multiplicativos do potencial. Multiplicados
                    # entre si e por 100 dao exatamente potencial_pct.
                    "fatores": {
                        "ocupacao_agenda": round(ocupacao, 4),
                        "forca_conversao": round(conversao / conv_max, 4) if conv_max else None,
                        "nivel_ticket": round(ticket / ticket_max, 4) if ticket_max else None,
                    },
                    "funil": {
                        "populacao_40mais": pop40,
                        "demanda_anual": round(demanda_anual, 1),
                        "capacidade_local_ano": round(capacidade_local, 1),
                        "demanda_nao_atendida": round(nao_atendida, 1),
                        "atrito_deslocamento": round(atrito, 3),
                        "demanda_represada": round(represada, 1),
                        "backlog_anos": backlog,
                        "publico_evento": round(publico, 1),
                        "alcance_midia": round(alcance, 4),
                        "alcancados": round(alcancados, 1),
                        "agendamentos": round(agendamentos, 1),
                        "comparecimentos": round(comparecimentos, 1),
                        "capacidade_evento": capacidade_evento,
                        "consultas": round(consultas, 1),
                        "limitado_pela_agenda": comparecimentos > capacidade_evento,
                        "demanda_nao_capturada": round(nao_capturada, 1),
                        "dias_sugeridos": int(dias_sugeridos),
                    },
                    "concorrencia": detalhe_conv,
                    "dinheiro": {
                        "vendas": round(vendas, 1),
                        "ticket": round(ticket, 2),
                        "faturamento": round(faturamento, 2),
                        "custo_por_par": round(custo_unitario, 2),
                        "margem_por_par": round(margem_unitaria, 2),
                        "cmv_fracao": round(cmv, 4),
                        "margem_bruta": round(margem, 2),
                        "custos": {k: round(v, 2) for k, v in custos.items()},
                        "lucro": round(lucro, 2),
                        "ponto_equilibrio_vendas": None if equilibrio is None else round(equilibrio, 1),
                    },
                    "teto_faturamento": round(teto, 2),
                    "confianca": confianca,
                }
            )

        for col in COLUNAS_PROJECAO:
            saida[col] = colunas[col]
        saida["projecao"] = linhas
        c.saida = len(saida)
        com_projecao = int(saida["faturamento_estimado"].notna().sum())
        lucrativos = int((pd.to_numeric(saida["lucro_estimado"], errors="coerce") > 0).sum())
        log(
            "projecao calculada",
            versao_negocio=negocio.get("versao", "n1"),
            municipios=len(saida),
            com_projecao=com_projecao,
            sem_dado_suficiente=len(saida) - com_projecao,
            lucrativos=lucrativos,
            teto_faturamento=round(teto),
        )
    return saida


def projecao_de_circuito(df: pd.DataFrame, negocio: dict[str, Any]) -> pd.DataFrame:
    """Soma a projecao das cidades de cada circuito, diluindo o deslocamento uma vez so.

    Uma cidade sozinha pode nao fechar a conta e o circuito fechar: o medico e o
    deslocamento sao pagos uma vez para tres ou quatro cidades. E assim que a
    operacao acontece de verdade, entao e assim que o ranking precisa saber somar.
    """
    if df.empty or "circuito" not in df.columns:
        return pd.DataFrame(
            columns=["circuito", "municipios", "nomes", "faturamento", "lucro", "consultas", "potencial_medio"]
        )
    evento = negocio.get("evento", {})
    deslocamento = _num(evento.get("custo_deslocamento")) or 0.0
    cidades_cfg = max(1.0, _num(evento.get("cidades_por_circuito")) or 1.0)

    base = df[pd.to_numeric(df["circuito"], errors="coerce").fillna(-1) >= 0].copy()
    if base.empty:
        return pd.DataFrame(
            columns=["circuito", "municipios", "nomes", "faturamento", "lucro", "consultas", "potencial_medio"]
        )

    grupos = []
    for circuito, grupo in base.groupby("circuito"):
        n = len(grupo)
        # No municipio, o deslocamento foi diluido por `cidades_por_circuito`.
        # No circuito real ele e pago uma vez so — corrige a diferenca.
        diluido_no_municipio = (deslocamento / cidades_cfg) * n
        correcao = diluido_no_municipio - deslocamento
        lucro = float(pd.to_numeric(grupo["lucro_estimado"], errors="coerce").sum()) + correcao
        grupos.append(
            {
                "circuito": int(circuito),
                "municipios": n,
                "nomes": list(grupo["nome"]),
                "codigos": list(grupo["codigo_ibge"]),
                "faturamento": round(float(pd.to_numeric(grupo["faturamento_estimado"], errors="coerce").sum()), 2),
                "lucro": round(lucro, 2),
                "consultas": round(float(pd.to_numeric(grupo["consultas_esperadas"], errors="coerce").sum()), 1),
                "potencial_medio": round(float(pd.to_numeric(grupo["potencial_pct"], errors="coerce").mean()), 2),
            }
        )
    saida = pd.DataFrame(grupos).sort_values("lucro", ascending=False)
    log("projecao de circuitos", circuitos=len(saida))
    return saida
