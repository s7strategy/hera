"""Distancia rodoviaria ate o polo oftalmologico mais proximo.

Provavelmente o preditor mais forte do modelo: nossa receita vem da venda de
oculos, entao o que importa nao e "ter oftalmologista", e o CUSTO DE ACESSO a
uma receita.

Polo = municipio com pelo menos N oftalmologistas (N em weights.yaml).

Custo computacional: 5.570 x 5.570 seria produto cartesiano. Pre-filtramos os
candidatos por distancia em linha reta (haversine, de graca) e so mandamos os
mais proximos para o roteador — exatamente a otimizacao pedida no briefing.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from ..cache import get_or_set
from ..geo import haversine_km
from ..http import FonteIndisponivel, get_json
from ..logs import aviso, etapa, log
from ..settings import get_settings
from .fontes import carregar

FONTE = "osrm"


def _url_table(perfil: str, origem: tuple[float, float], destinos: list[tuple[float, float]]) -> str:
    base = get_settings().osrm_base_url
    coords = ";".join(f"{lon},{lat}" for lat, lon in [origem, *destinos])
    destinos_idx = ";".join(str(i) for i in range(1, len(destinos) + 1))
    return (
        f"{base}/table/v1/{perfil}/{coords}"
        f"?sources=0&destinations={destinos_idx}&annotations=distance,duration"
    )


def _candidatos(
    origem: dict[str, Any], polos: list[dict[str, Any]], raio_km: float, maximo: int
) -> list[dict[str, Any]]:
    com_distancia = []
    for p in polos:
        if p["codigo_ibge"] == origem["codigo_ibge"]:
            continue
        d = haversine_km(origem["lat"], origem["lon"], p["lat"], p["lon"])
        if d <= raio_km:
            com_distancia.append({**p, "_reta_km": d})
    com_distancia.sort(key=lambda p: p["_reta_km"])
    return com_distancia[:maximo]


def calcular(
    municipios: pd.DataFrame,
    polos: pd.DataFrame,
    *,
    refresh: bool = False,
) -> pd.DataFrame:
    """municipios e polos precisam ter codigo_ibge, nome, lat, lon.

    Devolve uma linha por municipio com polo_codigo_ibge, distancia_km e
    tempo_minutos. Municipio que ja e polo recebe distancia 0 (ele mesmo).
    Quando o roteador falha, os campos ficam NULOS e a confianca cai — nunca
    preenchemos com a distancia em linha reta fingindo ser estrada.
    """
    cfg = carregar()["osrm"]
    perfil = cfg["perfil"]
    raio = float(cfg["raio_candidatos_km"])
    maximo = int(cfg["max_candidatos"])

    lista_polos = polos.dropna(subset=["lat", "lon"]).to_dict("records")
    codigos_polo = {p["codigo_ibge"] for p in lista_polos}
    saida: list[dict[str, Any]] = []

    with etapa("ingest.osrm.distancia_polo") as c:
        registros = municipios.dropna(subset=["lat", "lon"]).to_dict("records")
        c.entrada = len(municipios)
        if not lista_polos:
            aviso("nenhum polo definido: sem CNES nao da para calcular distancia ao polo")
            c.descartar("sem polos conhecidos", len(municipios))
            return pd.DataFrame(
                columns=["codigo_ibge", "polo_codigo_ibge", "polo_nome", "distancia_km", "tempo_minutos"]
            )

        for reg in registros:
            if reg["codigo_ibge"] in codigos_polo:
                saida.append(
                    {
                        "codigo_ibge": reg["codigo_ibge"],
                        "polo_codigo_ibge": reg["codigo_ibge"],
                        "polo_nome": reg.get("nome"),
                        "distancia_km": 0.0,
                        "tempo_minutos": 0.0,
                    }
                )
                continue

            cands = _candidatos(reg, lista_polos, raio, maximo)
            if not cands:
                aviso("sem polo dentro do raio de busca", municipio=reg["codigo_ibge"], raio_km=raio)
                saida.append(
                    {
                        "codigo_ibge": reg["codigo_ibge"],
                        "polo_codigo_ibge": None,
                        "polo_nome": None,
                        "distancia_km": None,
                        "tempo_minutos": None,
                    }
                )
                continue

            chave = reg["codigo_ibge"] + "-" + ",".join(p["codigo_ibge"] for p in cands)
            url = _url_table(perfil, (reg["lat"], reg["lon"]), [(p["lat"], p["lon"]) for p in cands])
            try:
                resposta = get_or_set(
                    FONTE, chave, lambda u=url: get_json(FONTE, u), refresh=refresh
                )
            except FonteIndisponivel as exc:
                aviso("OSRM indisponivel para municipio", municipio=reg["codigo_ibge"], erro=str(exc))
                saida.append(
                    {
                        "codigo_ibge": reg["codigo_ibge"],
                        "polo_codigo_ibge": None,
                        "polo_nome": None,
                        "distancia_km": None,
                        "tempo_minutos": None,
                    }
                )
                continue

            distancias = (resposta.get("distances") or [[]])[0]
            duracoes = (resposta.get("durations") or [[]])[0]
            melhor_i, melhor_d = None, None
            for i, d in enumerate(distancias):
                if d is None:
                    continue
                if melhor_d is None or d < melhor_d:
                    melhor_i, melhor_d = i, d
            if melhor_i is None:
                saida.append(
                    {
                        "codigo_ibge": reg["codigo_ibge"],
                        "polo_codigo_ibge": None,
                        "polo_nome": None,
                        "distancia_km": None,
                        "tempo_minutos": None,
                    }
                )
                continue
            polo = cands[melhor_i]
            duracao = duracoes[melhor_i] if melhor_i < len(duracoes) else None
            saida.append(
                {
                    "codigo_ibge": reg["codigo_ibge"],
                    "polo_codigo_ibge": polo["codigo_ibge"],
                    "polo_nome": polo.get("nome"),
                    "distancia_km": round(melhor_d / 1000.0, 1),
                    "tempo_minutos": round(duracao / 60.0, 1) if duracao is not None else None,
                }
            )
        df = pd.DataFrame(saida)
        c.saida = len(df)
        sem_rota = int(df["distancia_km"].isna().sum()) if not df.empty else 0
        if sem_rota:
            c.descartar("sem rota calculada", sem_rota)
        log("distancia ao polo", municipios=len(df), sem_rota=sem_rota, polos=len(lista_polos))
    return df
