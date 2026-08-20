"""Cache em disco de toda requisicao externa.

Desenvolvimento nao pode depender de rede a cada execucao (requisito nao-funcional),
e Places custa dinheiro por chamada: nunca reconsultar sem refresh explicito.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .logs import log
from .settings import CACHE_DIR, get_settings


def _slug(chave: str) -> str:
    limpo = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in chave)[:80]
    h = hashlib.sha1(chave.encode("utf-8")).hexdigest()[:10]
    return f"{limpo}-{h}"


def caminho(fonte: str, chave: str, ext: str = "json") -> Path:
    d = CACHE_DIR / fonte
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{_slug(chave)}.{ext}"


def _expirou(p: Path, ttl_horas: int) -> bool:
    if ttl_horas <= 0:
        return False
    return (time.time() - p.stat().st_mtime) > ttl_horas * 3600


def get_or_set(
    fonte: str,
    chave: str,
    produtor: Callable[[], Any],
    *,
    refresh: bool = False,
    ttl_horas: int | None = None,
) -> Any:
    """Devolve o valor cacheado ou chama `produtor()` e grava o resultado (JSON)."""
    ttl = get_settings().ttl_horas.get(fonte, 720) if ttl_horas is None else ttl_horas
    p = caminho(fonte, chave)
    if p.exists() and not refresh and not _expirou(p, ttl):
        with p.open(encoding="utf-8") as fh:
            return json.load(fh)
    valor = produtor()
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(valor, fh, ensure_ascii=False)
    tmp.replace(p)
    log("cache gravado", fonte=fonte, chave=chave[:60], bytes=p.stat().st_size)
    return valor


def get_or_set_bytes(
    fonte: str,
    chave: str,
    produtor: Callable[[], bytes],
    *,
    ext: str = "bin",
    refresh: bool = False,
    ttl_horas: int | None = None,
) -> Path:
    """Versao binaria: devolve o caminho do arquivo em cache (para .DBC, geojson grande...)."""
    ttl = get_settings().ttl_horas.get(fonte, 720) if ttl_horas is None else ttl_horas
    p = caminho(fonte, chave, ext=ext)
    if p.exists() and p.stat().st_size > 0 and not refresh and not _expirou(p, ttl):
        return p
    dados = produtor()
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(dados)
    tmp.replace(p)
    log("cache gravado", fonte=fonte, chave=chave[:60], bytes=p.stat().st_size)
    return p


def existe(fonte: str, chave: str, ext: str = "json") -> bool:
    return caminho(fonte, chave, ext).exists()
