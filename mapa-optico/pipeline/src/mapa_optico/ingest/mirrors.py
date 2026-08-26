"""Espelhos de dados publicos do IBGE, para quando a API oficial esta inacessivel.

Quando usar: rede que bloqueia servicodados.ibge.gov.br, apagao do IBGE, ou
ambiente sem egress liberado. NAO substitui a fonte oficial — o pipeline
registra a origem de cada campo em `fonte_por_campo` e o dashboard mostra
"espelho" na ficha do municipio.

O que os espelhos cobrem: codigo, nome, UF, centroide e geometria.
O que eles NAO cobrem: populacao, renda e CNES. Esses campos ficam NULOS
(nunca zero) e derrubam a confianca do municipio.
"""

from __future__ import annotations

import csv
import io
from typing import Any

import pandas as pd

from ..cache import get_or_set
from ..geo import CODIGO_UF, UF_CODIGO
from ..http import get_bytes, get_json
from ..logs import aviso, etapa
from ..transform.normalize import para_codigo7
from .fontes import carregar

FONTE = "mirror"


def municipios(ufs: list[str] | None = None, *, refresh: bool = False) -> pd.DataFrame:
    """Dimensao municipio a partir do espelho: codigo, nome, UF e centroide."""
    url = carregar()["espelhos"]["municipios_csv"]

    def _buscar() -> Any:
        texto = get_bytes(FONTE, url).decode("utf-8")
        return list(csv.DictReader(io.StringIO(texto)))

    with etapa("ingest.espelho.municipios") as c:
        linhas = get_or_set(FONTE, "espelho-municipios", _buscar, refresh=refresh)
        c.entrada = len(linhas)
        alvo = {u.upper() for u in ufs} if ufs else None
        saida = []
        for linha in linhas:
            uf = CODIGO_UF.get(int(linha["codigo_uf"]))
            if alvo and uf not in alvo:
                c.descartar("fora das UFs pedidas")
                continue
            codigo = para_codigo7(linha["codigo_ibge"])
            if not codigo:
                c.descartar("codigo invalido")
                continue
            saida.append(
                {
                    "codigo_ibge": codigo,
                    "nome": linha["nome"],
                    "uf": uf,
                    "microrregiao": None,
                    "mesorregiao": None,
                    "lat": float(linha["latitude"]),
                    "lon": float(linha["longitude"]),
                }
            )
        df = pd.DataFrame(saida)
        c.saida = len(df)
    aviso(
        "usando espelho para a dimensao municipio",
        detalhe="populacao, renda e CNES nao vem daqui e ficarao nulos",
    )
    return df


def malha(uf: str, *, refresh: bool = False) -> dict[str, Any]:
    """GeoJSON dos municipios de uma UF pelo espelho. Devolve {codigo_ibge: feature}."""
    url = carregar()["espelhos"]["malha_uf_geojson"].format(uf_codigo=UF_CODIGO[uf.upper()])

    with etapa(f"ingest.espelho.malha.{uf}") as c:
        geojson = get_or_set(FONTE, f"espelho-malha-{uf}", lambda: get_json(FONTE, url), refresh=refresh)
        feicoes = geojson.get("features", [])
        c.entrada = len(feicoes)
        saida: dict[str, Any] = {}
        for f in feicoes:
            props = f.get("properties") or {}
            codigo = para_codigo7(props.get("id") or props.get("codarea"))
            if not codigo:
                c.descartar("feicao sem codigo")
                continue
            saida[codigo] = f
        c.saida = len(saida)
    return saida
