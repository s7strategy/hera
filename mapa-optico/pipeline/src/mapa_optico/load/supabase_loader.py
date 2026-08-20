"""Carga no Supabase com upsert por chave natural.

Idempotencia (requisito nao-funcional): rodar o pipeline duas vezes nao pode
duplicar linha nem quebrar. Toda escrita aqui e upsert com on_conflict
explicito na chave natural da tabela.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from ..logs import etapa, log
from ..settings import get_settings

LOTE = 500


class SupabaseIndisponivel(RuntimeError):
    pass


def _cliente() -> Any:
    s = get_settings()
    if not s.tem_supabase:
        raise SupabaseIndisponivel(
            "SUPABASE_URL/SUPABASE_SERVICE_KEY ausentes no .env. "
            "O pipeline segue exportando CSV e snapshot local."
        )
    try:
        from supabase import create_client  # type: ignore
    except ImportError as exc:  # pragma: no cover - depende do extra
        raise SupabaseIndisponivel(
            "biblioteca supabase nao instalada. Rode `uv sync --extra supabase`."
        ) from exc
    return create_client(s.supabase_url, s.supabase_service_key)


def _lotes(registros: list[dict[str, Any]], tamanho: int = LOTE) -> Iterable[list[dict[str, Any]]]:
    for i in range(0, len(registros), tamanho):
        yield registros[i : i + tamanho]


def _ponto(lat: float | None, lon: float | None) -> str | None:
    if lat is None or lon is None or pd.isna(lat) or pd.isna(lon):
        return None
    return f"SRID=4326;POINT({lon} {lat})"


def _valor(v: Any) -> Any:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (dict, list)):
        return v
    if hasattr(v, "item"):
        try:
            return v.item()
        except (ValueError, AttributeError):
            return v
    return v


def _upsert(cliente: Any, tabela: str, registros: list[dict[str, Any]], on_conflict: str) -> int:
    total = 0
    for lote in _lotes(registros):
        limpo = [{k: _valor(v) for k, v in r.items()} for r in lote]
        cliente.table(tabela).upsert(limpo, on_conflict=on_conflict).execute()
        total += len(limpo)
    return total


def carregar_tudo(
    municipios: pd.DataFrame,
    oferta: pd.DataFrame,
    distancias: pd.DataFrame,
    oticas: pd.DataFrame,
    scores: pd.DataFrame,
) -> dict[str, int]:
    """Sobe as cinco tabelas na ordem das chaves estrangeiras."""
    cliente = _cliente()
    resumo: dict[str, int] = {}

    with etapa("load.supabase") as c:
        c.entrada = len(municipios)
        regs_mun = []
        for r in municipios.to_dict("records"):
            regs_mun.append(
                {
                    "codigo_ibge": r["codigo_ibge"],
                    "nome": r.get("nome"),
                    "uf": r.get("uf"),
                    "microrregiao": r.get("microrregiao"),
                    "mesorregiao": r.get("mesorregiao"),
                    "populacao_total": r.get("populacao_total"),
                    "populacao_40mais": r.get("populacao_40mais"),
                    "area_km2": r.get("area_km2"),
                    "renda_mediana": r.get("renda_mediana"),
                    "centroide": _ponto(r.get("lat"), r.get("lon")),
                    "fonte_por_campo": r.get("fonte_por_campo") or {},
                }
            )
        resumo["municipios"] = _upsert(cliente, "municipios", regs_mun, "codigo_ibge")

        if not oferta.empty:
            regs = [
                {
                    "codigo_ibge": r["codigo_ibge"],
                    "qtd_oftalmologistas": int(r.get("qtd_oftalmologistas") or 0),
                    "horas_semanais_total": r.get("horas_semanais_total"),
                    "oftalmo_equivalente": r.get("oftalmo_equivalente"),
                    "competencia_cnes": str(r.get("competencia_cnes") or "manual")[:6],
                    "origem": r.get("origem"),
                }
                for r in oferta.to_dict("records")
            ]
            resumo["oferta_oftalmo"] = _upsert(
                cliente, "oferta_oftalmo", regs, "codigo_ibge,competencia_cnes"
            )

        if not distancias.empty:
            regs = [
                {
                    "codigo_ibge": r["codigo_ibge"],
                    "polo_codigo_ibge": r.get("polo_codigo_ibge"),
                    "polo_nome": r.get("polo_nome"),
                    "distancia_km": r.get("distancia_km"),
                    "tempo_minutos": r.get("tempo_minutos"),
                }
                for r in distancias.to_dict("records")
            ]
            resumo["distancia_polo"] = _upsert(cliente, "distancia_polo", regs, "codigo_ibge")

        if not oticas.empty:
            regs = [
                {
                    "codigo_ibge": r.get("codigo_ibge"),
                    "place_id": r.get("place_id"),
                    "nome": r.get("nome"),
                    "endereco": r.get("endereco"),
                    "rating": r.get("rating"),
                    "total_ratings": r.get("total_ratings"),
                    "localizacao": _ponto(r.get("lat"), r.get("lon")),
                }
                for r in oticas.to_dict("records")
            ]
            resumo["oticas"] = _upsert(cliente, "oticas", regs, "place_id")

        if not scores.empty:
            regs = [
                {
                    "codigo_ibge": r["codigo_ibge"],
                    "versao_modelo": r.get("versao_modelo"),
                    "score_total": r.get("score_total"),
                    "confianca": r.get("confianca"),
                    "ranqueavel": bool(r.get("ranqueavel")),
                    "posicao": r.get("posicao"),
                    "circuito": None if pd.isna(r.get("circuito")) else r.get("circuito"),
                    "componentes": r.get("componentes"),
                }
                for r in scores.to_dict("records")
            ]
            resumo["scores"] = _upsert(cliente, "scores", regs, "codigo_ibge,versao_modelo")

        c.saida = resumo.get("municipios", 0)
        log("carga concluida", **resumo)
    return resumo
