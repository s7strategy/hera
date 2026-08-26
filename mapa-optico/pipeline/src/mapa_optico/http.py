"""Cliente HTTP unico: rate limit por fonte + retry com backoff exponencial.

Toda chamada externa do pipeline passa por aqui. Nenhum modulo de ingestao
deve criar seu proprio httpx.Client.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Any

import httpx

from .logs import aviso, log
from .settings import get_settings

_TIMEOUT = httpx.Timeout(connect=15.0, read=120.0, write=30.0, pool=15.0)
_UA = "mapa-optico/0.1 (pipeline de pesquisa de mercado; contato via repositorio)"

_CLIENTE: httpx.Client | None = None
_LOCK = threading.Lock()
_ULTIMA_CHAMADA: dict[str, float] = {}


class FonteIndisponivel(RuntimeError):
    """A fonte externa nao respondeu. NUNCA inventar dado: propagar e sinalizar."""

    def __init__(self, fonte: str, detalhe: str) -> None:
        super().__init__(f"{fonte}: {detalhe}")
        self.fonte = fonte
        self.detalhe = detalhe


def cliente() -> httpx.Client:
    global _CLIENTE
    if _CLIENTE is None:
        _CLIENTE = httpx.Client(
            timeout=_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": _UA},
        )
    return _CLIENTE


def _respeitar_rate_limit(fonte: str) -> None:
    rps = get_settings().rps.get(fonte, 5.0)
    if rps <= 0:
        return
    intervalo = 1.0 / rps
    with _LOCK:
        agora = time.monotonic()
        anterior = _ULTIMA_CHAMADA.get(fonte, 0.0)
        espera = intervalo - (agora - anterior)
        if espera > 0:
            time.sleep(espera)
        _ULTIMA_CHAMADA[fonte] = time.monotonic()


def requisitar(
    fonte: str,
    url: str,
    *,
    metodo: str = "GET",
    tentativas: int = 5,
    espera_base: float = 2.0,
    **kwargs: Any,
) -> httpx.Response:
    """GET/POST com backoff exponencial (2s, 4s, 8s, 16s) e jitter.

    Levanta FonteIndisponivel depois de esgotar as tentativas — o chamador
    decide se marca o campo como nulo, mas nunca preenche com chute.
    """
    ultimo_erro = ""
    for tentativa in range(1, tentativas + 1):
        _respeitar_rate_limit(fonte)
        try:
            resp = cliente().request(metodo, url, **kwargs)
        except httpx.HTTPError as exc:
            ultimo_erro = f"{type(exc).__name__}: {exc}"
        else:
            if resp.status_code < 400:
                return resp
            # 4xx que nao seja 408/429 nao adianta repetir
            if resp.status_code not in (408, 425, 429) and resp.status_code < 500:
                raise FonteIndisponivel(fonte, f"HTTP {resp.status_code} em {url}: {resp.text[:200]}")
            ultimo_erro = f"HTTP {resp.status_code}"
        if tentativa < tentativas:
            espera = espera_base * (2 ** (tentativa - 1)) + random.uniform(0, 0.5)
            aviso(
                "retry",
                fonte=fonte,
                tentativa=tentativa,
                de=tentativas,
                espera_s=round(espera, 1),
                erro=ultimo_erro,
                url=url[:120],
            )
            time.sleep(espera)
    raise FonteIndisponivel(fonte, f"{tentativas} tentativas falharam ({ultimo_erro}) em {url}")


def get_json(fonte: str, url: str, **kwargs: Any) -> Any:
    resp = requisitar(fonte, url, **kwargs)
    try:
        return resp.json()
    except ValueError as exc:
        raise FonteIndisponivel(fonte, f"resposta nao e JSON: {exc}") from exc


def get_bytes(fonte: str, url: str, **kwargs: Any) -> bytes:
    resp = requisitar(fonte, url, **kwargs)
    log("download", fonte=fonte, bytes=len(resp.content), url=url[:120])
    return resp.content


def fechar() -> None:
    global _CLIENTE
    if _CLIENTE is not None:
        _CLIENTE.close()
        _CLIENTE = None
