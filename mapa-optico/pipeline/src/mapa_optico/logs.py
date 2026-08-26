"""Logs estruturados por etapa.

Regra do briefing: toda queda de volume entre etapas tem que ser explicavel.
Por isso o helper `etapa()` obriga a declarar quantos registros entraram e
quantos sairam, e avisa quando a diferenca nao tem motivo declarado.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_LOGGER_NAME = "mapa_optico"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "nivel": record.levelname,
            "msg": record.getMessage(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            payload.update(extra)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configurar(nivel: int = logging.INFO, json_output: bool = False) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(nivel)
    logger.handlers.clear()
    h = logging.StreamHandler(sys.stderr)
    if json_output:
        h.setFormatter(_JsonFormatter())
    else:
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(message)s", "%H:%M:%S"))
    logger.addHandler(h)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        configurar()
    return logger


def _fmt(campos: dict[str, Any]) -> str:
    return " ".join(f"{k}={json.dumps(v, ensure_ascii=False, default=str)}" for k, v in campos.items())


def log(msg: str, **campos: Any) -> None:
    texto = f"{msg} {_fmt(campos)}" if campos else msg
    get_logger().info(texto, extra={"extra_fields": campos})


def aviso(msg: str, **campos: Any) -> None:
    texto = f"{msg} {_fmt(campos)}" if campos else msg
    get_logger().warning(texto, extra={"extra_fields": campos})


class Contador:
    """Acumulador de volume de uma etapa."""

    def __init__(self, nome: str) -> None:
        self.nome = nome
        self.entrada = 0
        self.saida = 0
        self.motivos: dict[str, int] = {}

    def descartar(self, motivo: str, n: int = 1) -> None:
        self.motivos[motivo] = self.motivos.get(motivo, 0) + n

    @property
    def perda(self) -> int:
        return max(self.entrada - self.saida, 0)


@contextmanager
def etapa(nome: str, alerta_perda_pct: float = 5.0) -> Iterator[Contador]:
    """Envolve uma etapa e loga entrada/saida/duracao ao final."""
    c = Contador(nome)
    t0 = time.perf_counter()
    log(f"[{nome}] inicio")
    try:
        yield c
    except Exception as exc:
        aviso(f"[{nome}] FALHOU", erro=str(exc), duracao_s=round(time.perf_counter() - t0, 2))
        raise
    dur = round(time.perf_counter() - t0, 2)
    pct = (c.perda / c.entrada * 100) if c.entrada else 0.0
    campos: dict[str, Any] = {
        "entrada": c.entrada,
        "saida": c.saida,
        "perda": c.perda,
        "perda_pct": round(pct, 2),
        "duracao_s": dur,
    }
    if c.motivos:
        campos["descartes"] = c.motivos
    if c.entrada and pct > alerta_perda_pct and not c.motivos:
        aviso(f"[{nome}] queda de volume nao explicada", **campos)
    else:
        log(f"[{nome}] fim", **campos)
