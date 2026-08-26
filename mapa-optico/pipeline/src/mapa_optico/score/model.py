"""Modelo de score — rastreavel ate os componentes, nunca caixa preta.

Decisoes que valem explicacao:

1. NORMALIZACAO POR PERCENTIL, nao min-max. Um municipio a 900 km do polo
   destruiria a escala inteira num min-max. O percentil e calculado dentro do
   universo ja filtrado (as UFs e faixas de populacao do weights.yaml), porque
   "longe" em SC nao e "longe" no Amazonas.

2. DADO AUSENTE NAO VIRA ZERO. Se falta o CNES de um municipio, o fator sai da
   conta e os pesos dos fatores restantes sao renormalizados — o municipio nao
   e punido por um buraco na nossa coleta. Em troca, a CONFIANCA cai, e a
   confianca aparece na interface junto do score.

3. RENDA NAO E PERCENTIL. Ela e uma curva de faixa otima em valores absolutos:
   renda baixa demais derruba o ticket medio, renda alta demais significa que a
   pessoa compra na otica da cidade grande. Percentil aqui inverteria o sentido.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from ..geo import haversine_km
from ..logs import aviso, etapa, log

# Colunas de entrada esperadas por fator do weights.yaml
COLUNA_POR_FATOR = {
    "distancia_polo": "distancia_km",
    "ausencia_oftalmo": "oftalmo_equivalente",
    "populacao_40mais": "populacao_40mais",
    "concorrencia_oticas": "qtd_oticas",
    "renda": "renda_mediana",
}

FONTE_POR_FATOR = {
    "distancia_polo": "distancia_polo",
    "ausencia_oftalmo": "cnes",
    "populacao_40mais": "ibge_populacao",
    "concorrencia_oticas": "places",
    "renda": "ibge_populacao",
}


def percentil(serie: pd.Series) -> pd.Series:
    """Rank percentual 0-100 ignorando nulos. Empates recebem a media do rank."""
    validos = serie.dropna()
    if validos.empty:
        return pd.Series([np.nan] * len(serie), index=serie.index, dtype="float64")
    if validos.nunique() == 1:
        base = pd.Series([50.0] * len(serie), index=serie.index)
        return base.where(serie.notna())
    return serie.rank(pct=True, na_option="keep") * 100.0


def curva_faixa_otima(valor: float | None, minimo: float, maximo: float, decaimento: float) -> float | None:
    """100 dentro da faixa; queda linear proporcional a quanto ficou de fora.

    Com decaimento=0.6 e faixa 1200-3500, uma renda de R$ 800 pontua ~90 e uma de
    R$ 5.000 pontua ~61. Escolha deliberadamente simples: o usuario precisa
    conseguir prever o efeito de mexer no numero.
    """
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return None
    largura = max(maximo - minimo, 1e-9)
    if valor < minimo:
        fora = minimo - valor
    elif valor > maximo:
        fora = valor - maximo
    else:
        return 100.0
    return float(max(0.0, 100.0 * (1.0 - decaimento * (fora / largura))))


def aplicar_filtros(df: pd.DataFrame, filtros: dict[str, Any]) -> pd.DataFrame:
    """Universo do modelo. Municipio sem populacao conhecida NAO e descartado.

    Descartar por dado ausente enviesaria o ranking: some justamente quem tem
    coleta pior. Ele fica, com confianca baixa e um aviso.
    """
    saida = df.copy()
    ufs = filtros.get("ufs") or []
    if ufs:
        saida = saida[saida["uf"].isin([u.upper() for u in ufs])]
    pop_min, pop_max = filtros.get("populacao_min"), filtros.get("populacao_max")
    pop = pd.to_numeric(saida.get("populacao_total"), errors="coerce")
    dentro = pd.Series(True, index=saida.index)
    if pop_min is not None:
        dentro &= (pop >= pop_min) | pop.isna()
    if pop_max is not None:
        dentro &= (pop <= pop_max) | pop.isna()
    return saida[dentro]


def _valores_normalizados(df: pd.DataFrame, nome: str, cfg: dict[str, Any]) -> pd.Series:
    coluna = COLUNA_POR_FATOR[nome]
    if coluna not in df.columns:
        return pd.Series([np.nan] * len(df), index=df.index, dtype="float64")
    bruto = pd.to_numeric(df[coluna], errors="coerce")

    if nome == "ausencia_oftalmo" and not cfg.get("usar_equivalente", True):
        bruto = pd.to_numeric(df.get("qtd_oftalmologistas"), errors="coerce")
    if nome == "ausencia_oftalmo":
        # Sem CNES o valor e nulo; COM CNES e sem oftalmologista o valor e zero.
        # Sao coisas diferentes e o pipeline preserva a diferenca.
        alternativa = pd.to_numeric(df.get("qtd_oftalmologistas"), errors="coerce")
        bruto = bruto.fillna(alternativa) if alternativa is not None else bruto

    if nome == "concorrencia_oticas" and cfg.get("per_capita"):
        pop = pd.to_numeric(df.get("populacao_total"), errors="coerce")
        bruto = (bruto / pop.replace(0, np.nan)) * 10_000

    tipo = cfg.get("tipo", "crescente")
    if tipo == "faixa_otima":
        return bruto.map(
            lambda v: curva_faixa_otima(
                v, float(cfg["faixa_min"]), float(cfg["faixa_max"]), float(cfg.get("decaimento", 0.6))
            )
        )

    if nome == "distancia_polo" and cfg.get("saturacao_km"):
        bruto = bruto.clip(upper=float(cfg["saturacao_km"]))

    pct = percentil(bruto)
    if tipo == "inverso":
        pct = 100.0 - pct

    if nome == "ausencia_oftalmo" and cfg.get("bonus_zero"):
        zerados = bruto.fillna(-1) == 0
        pct = (pct + zerados * float(cfg["bonus_zero"])).clip(upper=100.0)
    return pct


def _confianca(linha: pd.Series, cfg_conf: dict[str, Any], disponivel: dict[str, bool]) -> float:
    pesos = cfg_conf.get("peso_por_fonte", {})
    total = sum(pesos.values()) or 1.0
    obtido = 0.0
    for fonte, peso in pesos.items():
        if disponivel.get(fonte):
            obtido += peso
    return round(obtido / total, 3)


def calcular_score(df: pd.DataFrame, pesos: dict[str, Any]) -> pd.DataFrame:
    """Entrada: um DataFrame por municipio com os campos brutos das 4 fontes.

    Saida: o mesmo DataFrame + score_total, confianca, ranqueavel e a coluna
    `componentes` (dict) com valor bruto, normalizado, peso e contribuicao de
    cada fator. `componentes` vira o JSONB da tabela `scores` e alimenta o
    breakdown da ficha do municipio.
    """
    fatores = pesos["fatores"]
    cfg_conf = pesos.get("confianca", {})
    versao = pesos.get("versao", "v1")

    with etapa("score.calcular") as c:
        universo = aplicar_filtros(df, pesos.get("filtros", {}))
        c.entrada = len(df)
        c.descartar("fora dos filtros de UF/populacao", len(df) - len(universo))
        if universo.empty:
            aviso("nenhum municipio sobrou apos os filtros")
            c.saida = 0
            return universo.assign(score_total=[], confianca=[], componentes=[], versao_modelo=[])

        normalizados = {nome: _valores_normalizados(universo, nome, cfg) for nome, cfg in fatores.items()}

        linhas_componentes: list[dict[str, Any]] = []
        scores: list[float] = []
        confiancas: list[float] = []

        for idx in universo.index:
            componentes: dict[str, Any] = {}
            peso_disponivel = 0.0
            soma = 0.0
            fontes_ok: dict[str, bool] = {}

            for nome, cfg in fatores.items():
                peso = float(cfg["peso"])
                valor_norm = normalizados[nome].get(idx)
                coluna = COLUNA_POR_FATOR[nome]
                bruto = universo.at[idx, coluna] if coluna in universo.columns else None
                tem = valor_norm is not None and not pd.isna(valor_norm)
                fontes_ok[FONTE_POR_FATOR[nome]] = fontes_ok.get(FONTE_POR_FATOR[nome], False) or tem
                componentes[nome] = {
                    "valor_bruto": None if bruto is None or pd.isna(bruto) else float(bruto),
                    "normalizado": round(float(valor_norm), 2) if tem else None,
                    "peso": peso,
                    "tipo": cfg.get("tipo"),
                    "disponivel": bool(tem),
                    "contribuicao": 0.0,
                }
                if tem:
                    peso_disponivel += peso
                    soma += peso * float(valor_norm)

            if peso_disponivel > 0:
                score = soma / peso_disponivel
                for nome, cfg in fatores.items():
                    comp = componentes[nome]
                    if comp["disponivel"]:
                        # Contribuicao em pontos do score final (soma = score_total).
                        comp["contribuicao"] = round(
                            comp["normalizado"] * comp["peso"] / peso_disponivel, 2
                        )
                        comp["peso_efetivo"] = round(comp["peso"] / peso_disponivel * 100, 1)
            else:
                score = float("nan")

            conf = _confianca(universo.loc[idx], cfg_conf, fontes_ok)
            componentes["_meta"] = {
                "peso_disponivel": peso_disponivel,
                "peso_total": sum(float(f["peso"]) for f in fatores.values()),
                "fontes": fontes_ok,
            }
            linhas_componentes.append(componentes)
            scores.append(None if math.isnan(score) else round(score, 2))
            confiancas.append(conf)

        saida = universo.copy()
        saida["score_total"] = scores
        saida["confianca"] = confiancas
        saida["componentes"] = linhas_componentes
        saida["versao_modelo"] = versao
        minimo = float(cfg_conf.get("minimo_para_ranquear", 0))
        saida["ranqueavel"] = (saida["confianca"] >= minimo) & saida["score_total"].notna()
        saida = saida.sort_values("score_total", ascending=False, na_position="last")
        saida["posicao"] = range(1, len(saida) + 1)
        c.saida = len(saida)
        log(
            "score calculado",
            versao=versao,
            municipios=len(saida),
            ranqueaveis=int(saida["ranqueavel"].sum()),
            confianca_media=round(float(saida["confianca"].mean()), 3),
        )
    return saida


def pares_canibalizacao(df: pd.DataFrame, pesos: dict[str, Any]) -> list[dict[str, Any]]:
    """Municipios do topo perto demais um do outro: provavelmente um circuito so."""
    cfg = pesos.get("canibalizacao", {})
    raio = float(cfg.get("raio_km", 30))
    top_n = int(cfg.get("top_n", 20))
    topo = df[df["ranqueavel"]].head(top_n).dropna(subset=["lat", "lon"])
    saida = []
    registros = topo.to_dict("records")
    for i in range(len(registros)):
        for j in range(i + 1, len(registros)):
            a, b = registros[i], registros[j]
            d = haversine_km(a["lat"], a["lon"], b["lat"], b["lon"])
            if d <= raio:
                saida.append(
                    {
                        "a": a["codigo_ibge"],
                        "a_nome": a["nome"],
                        "b": b["codigo_ibge"],
                        "b_nome": b["nome"],
                        "distancia_km": round(d, 1),
                    }
                )
    if saida:
        log("alerta de canibalizacao", pares=len(saida), raio_km=raio)
    return sorted(saida, key=lambda p: p["distancia_km"])


def circuitos(df: pd.DataFrame, pesos: dict[str, Any]) -> pd.DataFrame:
    """Agrupa municipios vizinhos de score alto em circuitos de 3-4 cidades.

    POR QUE NAO E DBSCAN. O briefing sugeria DBSCAN com eps de 60 km, e foi assim
    que comecou — mas DBSCAN agrupa por alcancabilidade transitiva: A perto de B,
    B perto de C, e o cluster cresce em cadeia. Rodando em SC com 60 km, o estado
    inteiro virou UM circuito de 186 municipios. Isso e verdade geografica e
    inutil como roteiro: ninguem leva o medico a 186 cidades numa viagem.

    O que a operacao precisa e outra coisa — uma sequencia de 3 a 4 cidades que
    caibam numa saida. Entao: pega o municipio de melhor score ainda sem
    circuito, junta os melhores vizinhos dentro do raio ate fechar o tamanho,
    tira todos da lista e repete. Circuito com menos que o minimo e desfeito, e
    seus municipios voltam a valer sozinhos (circuito = -1).

    O resultado e guloso, nao otimo. E deliberado: o usuario vai reordenar o
    roteiro na mao de qualquer jeito, e um agrupamento que ele entende vale mais
    que um que ele teria de aceitar no escuro.
    """
    cfg = pesos.get("circuitos", {})
    raio = float(cfg.get("eps_km", 60))
    minimo = int(cfg.get("min_municipios", 2))
    tamanho = cfg.get("tamanho_sugerido") or [3, 4]
    maximo = int(max(tamanho))

    base = df[df["ranqueavel"]].dropna(subset=["lat", "lon"])
    if base.empty:
        return pd.DataFrame(columns=["codigo_ibge", "circuito"])

    # Melhor score primeiro: o circuito nasce ancorado na cidade que puxa a viagem.
    candidatos = base.sort_values("score_total", ascending=False).to_dict("records")
    restantes = {r["codigo_ibge"]: r for r in candidatos}
    rotulos: dict[str, int] = {codigo: -1 for codigo in restantes}
    proximo = 0

    for ancora in candidatos:
        codigo = ancora["codigo_ibge"]
        if codigo not in restantes:
            continue
        del restantes[codigo]

        vizinhos = [
            (haversine_km(ancora["lat"], ancora["lon"], r["lat"], r["lon"]), r)
            for r in restantes.values()
        ]
        # Dentro do raio, os de melhor score entram primeiro; a distancia so desempata.
        dentro = sorted(
            [(d, r) for d, r in vizinhos if d <= raio],
            key=lambda par: (-(par[1].get("score_total") or 0), par[0]),
        )[: maximo - 1]

        grupo = [codigo] + [r["codigo_ibge"] for _, r in dentro]
        if len(grupo) < minimo:
            continue  # sozinho demais para virar roteiro; segue como municipio avulso
        for c in grupo:
            rotulos[c] = proximo
            restantes.pop(c, None)
        proximo += 1

    saida = pd.DataFrame({"codigo_ibge": list(rotulos.keys()), "circuito": list(rotulos.values())})
    agrupados = sum(1 for v in rotulos.values() if v >= 0)
    log(
        "circuitos sugeridos",
        circuitos=proximo,
        municipios_agrupados=agrupados,
        avulsos=len(rotulos) - agrupados,
        raio_km=raio,
        tamanho_maximo=maximo,
    )
    return saida
