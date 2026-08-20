"""Configuracao central: caminhos, segredos (.env) e leitura de weights.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

PIPELINE_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = PIPELINE_DIR.parent
DATA_DIR = PIPELINE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
OUT_DIR = PIPELINE_DIR / "out"
CONFIG_DIR = PIPELINE_DIR / "config"
WEB_DATA_DIR = REPO_DIR / "web" / "public" / "data"

load_dotenv(PIPELINE_DIR / ".env")


def _int_env(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, "") or padrao)
    except ValueError:
        return padrao


def _float_env(nome: str, padrao: float) -> float:
    try:
        return float(os.getenv(nome, "") or padrao)
    except ValueError:
        return padrao


@dataclass(frozen=True)
class Settings:
    google_places_api_key: str | None
    supabase_url: str | None
    supabase_service_key: str | None
    osrm_base_url: str
    ttl_horas: dict[str, int]
    rps: dict[str, float]

    @property
    def tem_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_key)

    @property
    def tem_places(self) -> bool:
        return bool(self.google_places_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        google_places_api_key=os.getenv("GOOGLE_PLACES_API_KEY") or None,
        supabase_url=os.getenv("SUPABASE_URL") or None,
        supabase_service_key=os.getenv("SUPABASE_SERVICE_KEY") or None,
        osrm_base_url=(os.getenv("OSRM_BASE_URL") or "https://router.project-osrm.org").rstrip("/"),
        ttl_horas={
            "ibge": _int_env("CACHE_TTL_HORAS_IBGE", 720),
            "cnes": _int_env("CACHE_TTL_HORAS_CNES", 720),
            "osrm": _int_env("CACHE_TTL_HORAS_OSRM", 0),
            "places": _int_env("CACHE_TTL_HORAS_PLACES", 0),
            "mirror": _int_env("CACHE_TTL_HORAS_IBGE", 720),
        },
        rps={
            "ibge": _float_env("RPS_IBGE", 5),
            "osrm": _float_env("RPS_OSRM", 2),
            "places": _float_env("RPS_PLACES", 5),
            "mirror": _float_env("RPS_IBGE", 5),
            "cnes": 1.0,
        },
    )


@lru_cache(maxsize=8)
def carregar_pesos(caminho: str | None = None) -> dict[str, Any]:
    """Le o weights.yaml. Sem fallback silencioso: se o arquivo sumir, quebra alto."""
    p = Path(caminho) if caminho else CONFIG_DIR / "weights.yaml"
    if not p.exists():
        raise FileNotFoundError(
            f"weights.yaml nao encontrado em {p}. O modelo nao roda sem configuracao de pesos."
        )
    with p.open(encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict) or "fatores" not in cfg:
        raise ValueError(f"{p} nao parece um weights.yaml valido (falta a chave 'fatores').")
    return cfg


def garantir_dirs() -> None:
    for d in (DATA_DIR, CACHE_DIR, OUT_DIR, WEB_DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)
