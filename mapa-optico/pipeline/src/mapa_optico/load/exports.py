"""Saidas do pipeline: CSV/XLSX para uso comercial e snapshot JSON para o dashboard.

O snapshot existe para que o dashboard funcione sem Supabase configurado
(e sem rede): o front le o Supabase quando ha credencial e cai para o arquivo
estatico quando nao ha. Mesmo formato nos dois casos.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ..logs import log
from ..settings import OUT_DIR, WEB_DATA_DIR, garantir_dirs

COLUNAS_COMERCIAIS = [
    "posicao",
    "codigo_ibge",
    "nome",
    "uf",
    "potencial_pct",
    "faturamento_estimado",
    "lucro_estimado",
    "retorno_sobre_custo",
    "consultas_esperadas",
    "vendas_esperadas",
    "ocupacao_agenda",
    "conversao",
    "ticket_estimado",
    "custo_evento",
    "ponto_equilibrio_vendas",
    "projecao_confianca",
    "score_total",
    "confianca",
    "populacao_total",
    "populacao_40mais",
    "qtd_oftalmologistas",
    "oftalmo_equivalente",
    "distancia_km",
    "tempo_minutos",
    "polo_nome",
    "qtd_oticas",
    "oticas_nota_media",
    "oticas_avaliacoes",
    "renda_mediana",
    "circuito",
    "microrregiao",
]


def _agora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def exportar_planilhas(df: pd.DataFrame, prefixo: str = "ranking") -> dict[str, Path]:
    """CSV e XLSX do conjunto, na ordem do ranking."""
    garantir_dirs()
    colunas = [c for c in COLUNAS_COMERCIAIS if c in df.columns]
    tabela = df[colunas].copy()
    csv_path = OUT_DIR / f"{prefixo}.csv"
    xlsx_path = OUT_DIR / f"{prefixo}.xlsx"
    tabela.to_csv(csv_path, index=False, encoding="utf-8-sig")
    try:
        tabela.to_excel(xlsx_path, index=False, sheet_name="ranking")
    except Exception as exc:  # noqa: BLE001 - xlsx e conveniencia, csv e o essencial
        log("xlsx nao gerado", erro=str(exc))
        xlsx_path = csv_path
    log("planilhas exportadas", csv=str(csv_path), xlsx=str(xlsx_path), linhas=len(tabela))
    return {"csv": csv_path, "xlsx": xlsx_path}


def _limpar(valor: Any) -> Any:
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    if isinstance(valor, (pd.Timestamp, datetime)):
        return valor.isoformat()
    if hasattr(valor, "item"):
        try:
            return valor.item()
        except (ValueError, AttributeError):
            return valor
    return valor


def snapshot_para_web(
    df: pd.DataFrame,
    pesos: dict[str, Any],
    *,
    negocio: dict[str, Any] | None = None,
    canibalizacao: list[dict[str, Any]] | None = None,
    circuitos: list[dict[str, Any]] | None = None,
    oticas: list[dict[str, Any]] | None = None,
    proveniencia: dict[str, Any] | None = None,
    avisos: list[str] | None = None,
    destino: Path | None = None,
) -> Path:
    """Grava web/public/data/snapshot.json — o que o dashboard le quando nao ha Supabase."""
    garantir_dirs()
    destino = destino or (WEB_DATA_DIR / "snapshot.json")
    registros = []
    for reg in df.to_dict("records"):
        registros.append({k: _limpar(v) for k, v in reg.items()})
    # O custo por chamada do Places vive em fontes.yaml. Levar essa informacao ao
    # snapshot deixa a tela de sincronizacao estimar a conta ANTES de gastar, sem
    # duplicar o numero no codigo do front.
    try:
        from ..ingest.fontes import carregar as _carregar_fontes

        cfg_places = _carregar_fontes().get("places", {})
        fontes_cfg = {
            "places": {
                "termos": cfg_places.get("termos", []),
                "custo_por_chamada_usd": cfg_places.get("custo_estimado_usd_por_chamada"),
            }
        }
    except Exception as exc:  # noqa: BLE001 - a estimativa e conveniencia, nao pode derrubar a exportacao
        log("config de fontes nao embutida no snapshot", erro=str(exc))
        fontes_cfg = {}

    payload = {
        "gerado_em": _agora(),
        "fontes_config": fontes_cfg,
        "versao_modelo": pesos.get("versao", "v1"),
        "versao_negocio": (negocio or {}).get("versao", "n1"),
        "pesos": pesos,
        "negocio": negocio or {},
        "proveniencia": proveniencia or {},
        "avisos": avisos or [],
        "canibalizacao": canibalizacao or [],
        "circuitos": circuitos or [],
        "oticas": oticas or [],
        "municipios": registros,
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    log("snapshot gravado", arquivo=str(destino), municipios=len(registros), kb=round(destino.stat().st_size / 1024))
    return destino


def malha_para_web(malha: dict[str, Any], uf: str, destino: Path | None = None) -> Path:
    """GeoJSON enxuto para o mapa: so a geometria e o codigo, o resto vem do snapshot."""
    garantir_dirs()
    destino = destino or (WEB_DATA_DIR / f"malha-{uf.upper()}.geojson")
    feicoes = [
        {
            "type": "Feature",
            "id": codigo,
            "properties": {"codigo_ibge": codigo},
            "geometry": f.get("geometry"),
        }
        for codigo, f in malha.items()
    ]
    destino.write_text(
        json.dumps({"type": "FeatureCollection", "features": feicoes}, ensure_ascii=False),
        encoding="utf-8",
    )
    log("malha gravada", arquivo=str(destino), feicoes=len(feicoes), kb=round(destino.stat().st_size / 1024))
    return destino
