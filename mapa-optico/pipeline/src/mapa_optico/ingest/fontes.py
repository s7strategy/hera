"""Leitura do config/fontes.yaml (ids externos que precisam ser conferidos)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..settings import CONFIG_DIR


@lru_cache(maxsize=4)
def carregar(caminho: str | None = None) -> dict[str, Any]:
    p = Path(caminho) if caminho else CONFIG_DIR / "fontes.yaml"
    if not p.exists():
        raise FileNotFoundError(f"fontes.yaml nao encontrado em {p}")
    with p.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)
