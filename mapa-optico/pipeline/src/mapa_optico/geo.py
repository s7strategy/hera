"""Utilitarios geograficos sem dependencia pesada.

Nao usamos shapely/geopandas/sklearn aqui de proposito: sao tres funcoes
(haversine, centroide/area de poligono e um DBSCAN sobre 295 pontos) e nenhuma
justifica arrastar as dependencias binarias para o pipeline. Se um dia rodarmos
analise geometrica de verdade, PostGIS ja esta no banco.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

RAIO_TERRA_KM = 6371.0088

UF_CODIGO = {
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17,
    "MA": 21, "PI": 22, "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27,
    "SE": 28, "BA": 29, "MG": 31, "ES": 32, "RJ": 33, "SP": 35, "PR": 41,
    "SC": 42, "RS": 43, "MS": 50, "MT": 51, "GO": 52, "DF": 53,
}
CODIGO_UF = {v: k for k, v in UF_CODIGO.items()}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_KM * math.asin(min(1.0, math.sqrt(a)))


def _aneis(geometry: dict[str, Any]) -> list[list[Sequence[float]]]:
    tipo = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if tipo == "Polygon":
        return [anel for anel in coords]
    if tipo == "MultiPolygon":
        return [anel for poligono in coords for anel in poligono]
    return []


def centroide(geometry: dict[str, Any]) -> tuple[float, float] | None:
    """Centroide por area (formula do poligono), com fallback para media dos vertices.

    Devolve (lat, lon). Suficiente para roteamento: o OSRM encaixa o ponto na via
    mais proxima de qualquer jeito.
    """
    melhor: tuple[float, float, float] | None = None  # (area, cx, cy)
    for anel in _aneis(geometry):
        if len(anel) < 3:
            continue
        a = cx = cy = 0.0
        for i in range(len(anel) - 1):
            x0, y0 = float(anel[i][0]), float(anel[i][1])
            x1, y1 = float(anel[i + 1][0]), float(anel[i + 1][1])
            cross = x0 * y1 - x1 * y0
            a += cross
            cx += (x0 + x1) * cross
            cy += (y0 + y1) * cross
        if abs(a) < 1e-12:
            continue
        a *= 0.5
        cand = (abs(a), cx / (6 * a), cy / (6 * a))
        if melhor is None or cand[0] > melhor[0]:
            melhor = cand
    if melhor:
        return (melhor[2], melhor[1])
    pontos = [p for anel in _aneis(geometry) for p in anel]
    if not pontos:
        return None
    return (
        sum(float(p[1]) for p in pontos) / len(pontos),
        sum(float(p[0]) for p in pontos) / len(pontos),
    )


def area_km2(geometry: dict[str, Any]) -> float | None:
    """Area esferica aproximada. Usada so para dimensionar o raio de busca do Places."""
    total = 0.0
    for anel in _aneis(geometry):
        if len(anel) < 4:
            continue
        soma = 0.0
        for i in range(len(anel) - 1):
            lon1, lat1 = math.radians(float(anel[i][0])), math.radians(float(anel[i][1]))
            lon2, lat2 = math.radians(float(anel[i + 1][0])), math.radians(float(anel[i + 1][1]))
            soma += (lon2 - lon1) * (2 + math.sin(lat1) + math.sin(lat2))
        total += abs(soma * RAIO_TERRA_KM**2 / 2.0)
    return round(total, 2) if total else None


def dbscan_geo(
    pontos: Sequence[tuple[str, float, float]],
    eps_km: float,
    min_amostras: int = 2,
) -> dict[str, int]:
    """DBSCAN sobre coordenadas, distancia em km. Devolve {id: cluster} (-1 = ruido).

    Implementacao direta: O(n^2) e irrelevante para 295 municipios de SC e
    aceitavel para 5.570 do Brasil (~15M comparacoes, poucos segundos).
    """
    n = len(pontos)
    vizinhos: list[list[int]] = [[] for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if haversine_km(pontos[i][1], pontos[i][2], pontos[j][1], pontos[j][2]) <= eps_km:
                vizinhos[i].append(j)
                vizinhos[j].append(i)

    rotulos = [-1] * n
    visitado = [False] * n
    cluster = 0
    for i in range(n):
        if visitado[i]:
            continue
        visitado[i] = True
        if len(vizinhos[i]) + 1 < min_amostras:
            continue
        rotulos[i] = cluster
        fila = list(vizinhos[i])
        while fila:
            k = fila.pop()
            if not visitado[k]:
                visitado[k] = True
                if len(vizinhos[k]) + 1 >= min_amostras:
                    fila.extend(v for v in vizinhos[k] if not visitado[v])
            if rotulos[k] == -1:
                rotulos[k] = cluster
        cluster += 1
    return {pontos[i][0]: rotulos[i] for i in range(n)}


def pares_proximos(
    pontos: Iterable[tuple[str, float, float]], raio_km: float
) -> list[tuple[str, str, float]]:
    """Pares a menos de `raio_km` — base do alerta de canibalizacao."""
    lista = list(pontos)
    saida: list[tuple[str, str, float]] = []
    for i in range(len(lista)):
        for j in range(i + 1, len(lista)):
            d = haversine_km(lista[i][1], lista[i][2], lista[j][1], lista[j][2])
            if d <= raio_km:
                saida.append((lista[i][0], lista[j][0], round(d, 1)))
    return sorted(saida, key=lambda t: t[2])
