"""Google Places (New): oticas concorrentes por municipio.

Unica fonte que custa dinheiro. Regras deste modulo, todas do briefing:
  - cache agressivo em disco, TTL infinito por padrao. Municipio ja consultado
    NUNCA e reconsultado sem `--refresh` explicito;
  - o custo e estimado e logado ANTES de rodar em lote, com confirmacao;
  - o raio e proporcional a area do municipio, nao fixo;
  - deduplicacao por place_id, e cada otica e atribuida ao municipio cujo
    centroide esta mais perto — senao a mesma otica conta em dois vizinhos.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any

import pandas as pd

from ..cache import caminho as caminho_cache
from ..cache import get_or_set
from ..geo import haversine_km
from ..http import FonteIndisponivel, requisitar
from ..logs import aviso, etapa, log
from ..settings import get_settings
from .fontes import carregar

FONTE = "places"


def raio_metros(area_km2: float | None, cfg: dict[str, Any]) -> int:
    """Raio da busca proporcional a area: raio do circulo de mesma area, com teto."""
    rmin, rmax = int(cfg["raio_min_m"]), int(cfg["raio_max_m"])
    if not area_km2 or area_km2 <= 0:
        return rmin
    raio = math.sqrt(area_km2 / math.pi) * 1000.0
    return int(max(rmin, min(rmax, raio)))


def municipios_ja_consultados(codigos: Iterable[str], termos: list[str]) -> set[str]:
    consultados = set()
    for codigo in codigos:
        if all(caminho_cache(FONTE, f"{codigo}-{t}").exists() for t in termos):
            consultados.add(codigo)
    return consultados


def estimar_custo(municipios: pd.DataFrame, *, refresh: bool = False) -> dict[str, Any]:
    """Quantas chamadas novas seriam feitas e quanto isso custa, antes de gastar."""
    cfg = carregar()["places"]
    termos = cfg["termos"]
    codigos = list(municipios["codigo_ibge"])
    ja = set() if refresh else municipios_ja_consultados(codigos, termos)
    novas = (len(codigos) - len(ja)) * len(termos)
    custo = novas * float(cfg["custo_estimado_usd_por_chamada"])
    return {
        "municipios": len(codigos),
        "em_cache": len(ja),
        "chamadas_novas": novas,
        "custo_estimado_usd": round(custo, 2),
        "termos": termos,
    }


def _buscar_termo(termo: str, lat: float, lon: float, raio: int, cfg: dict[str, Any]) -> Any:
    chave = get_settings().google_places_api_key
    if not chave:
        raise FonteIndisponivel(FONTE, "GOOGLE_PLACES_API_KEY ausente no .env")
    corpo = {
        "textQuery": termo,
        "languageCode": "pt-BR",
        "regionCode": "BR",
        "maxResultCount": 20,
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lon}, "radius": raio}},
    }
    resp = requisitar(
        FONTE,
        cfg["endpoint"],
        metodo="POST",
        json=corpo,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": chave,
            "X-Goog-FieldMask": cfg["campos"],
        },
    )
    return resp.json()


def coletar(
    municipios: pd.DataFrame,
    *,
    refresh: bool = False,
    confirmar: bool = True,
    limite_chamadas: int | None = None,
) -> pd.DataFrame:
    """municipios precisa ter codigo_ibge, nome, lat, lon e area_km2.

    Devolve uma linha por otica encontrada, ja deduplicada e atribuida ao
    municipio mais proximo.
    """
    cfg = carregar()["places"]
    termos = cfg["termos"]
    estimativa = estimar_custo(municipios, refresh=refresh)
    log("estimativa de custo do Places", **estimativa)
    if confirmar and estimativa["chamadas_novas"] > 0:
        aviso(
            "Places vai gastar dinheiro",
            chamadas=estimativa["chamadas_novas"],
            usd=estimativa["custo_estimado_usd"],
        )
    if limite_chamadas is not None and estimativa["chamadas_novas"] > limite_chamadas:
        raise RuntimeError(
            f"{estimativa['chamadas_novas']} chamadas passam do limite de {limite_chamadas}. "
            "Aumente --limite-chamadas se for intencional."
        )

    centroides = [
        (r["codigo_ibge"], r["lat"], r["lon"])
        for r in municipios.dropna(subset=["lat", "lon"]).to_dict("records")
    ]
    por_place: dict[str, dict[str, Any]] = {}
    chamadas = 0

    with etapa("ingest.places") as c:
        c.entrada = len(municipios)
        for reg in municipios.dropna(subset=["lat", "lon"]).to_dict("records"):
            raio = raio_metros(reg.get("area_km2"), cfg)
            for termo in termos:
                chave = f"{reg['codigo_ibge']}-{termo}"
                try:
                    dados = get_or_set(
                        FONTE,
                        chave,
                        lambda t=termo, la=reg["lat"], lo=reg["lon"], r=raio: _buscar_termo(
                            t, la, lo, r, cfg
                        ),
                        refresh=refresh,
                    )
                    chamadas += 1
                except FonteIndisponivel as exc:
                    aviso("Places indisponivel", municipio=reg["codigo_ibge"], erro=str(exc))
                    c.descartar("places indisponivel")
                    continue
                for lugar in dados.get("places", []) or []:
                    place_id = lugar.get("id")
                    loc = lugar.get("location") or {}
                    lat, lon = loc.get("latitude"), loc.get("longitude")
                    if not place_id or lat is None or lon is None:
                        continue
                    # Atribui ao municipio cujo centroide esta mais proximo.
                    dono = min(centroides, key=lambda t: haversine_km(lat, lon, t[1], t[2]))
                    por_place[place_id] = {
                        "place_id": place_id,
                        "codigo_ibge": dono[0],
                        "nome": (lugar.get("displayName") or {}).get("text"),
                        "endereco": lugar.get("formattedAddress"),
                        "rating": lugar.get("rating"),
                        "total_ratings": lugar.get("userRatingCount"),
                        "lat": lat,
                        "lon": lon,
                    }
        df = pd.DataFrame(list(por_place.values()))
        c.saida = len(df)
        log("oticas coletadas", unicas=len(df), chamadas=chamadas)
    return df


def contar_por_municipio(oticas: pd.DataFrame, municipios: pd.DataFrame) -> pd.DataFrame:
    """Contagem de oticas por municipio, com zero explicito so onde houve consulta."""
    if oticas.empty:
        base = municipios[["codigo_ibge"]].copy()
        base["qtd_oticas"] = pd.NA
        return base
    contagem = oticas.groupby("codigo_ibge").size().rename("qtd_oticas").reset_index()
    consultados = municipios_ja_consultados(
        list(municipios["codigo_ibge"]), carregar()["places"]["termos"]
    )
    base = municipios[["codigo_ibge"]].merge(contagem, on="codigo_ibge", how="left")
    # Municipio consultado e sem resultado = zero de verdade.
    # Municipio nao consultado = NULO, e a confianca cai.
    base["qtd_oticas"] = [
        (0 if pd.isna(q) and cod in consultados else q)
        for cod, q in zip(base["codigo_ibge"], base["qtd_oticas"])
    ]
    return base
