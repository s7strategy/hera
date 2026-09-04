"""Infra comum da suíte do S7 Editor.

Duas garantias valem para TODOS os testes daqui:

1. **Nada de rede.** Um fixture autouse derruba socket/DNS. Se algum caminho
   tentar falar com a OpenAI, o teste quebra com mensagem clara em vez de
   pendurar ou gastar dinheiro. O produto tem que provar a trilha determinística
   offline — é isso que a suíte mede.
2. **Nada de chave.** ``OPENAI_API_KEY`` é apagada do ambiente e os
   :class:`Settings` dos testes saem com ``openai_api_key=None``.

Os fixtures de imagem são gerados por ``tools/make_fixtures.py`` (determinístico)
e ficam em ``tests/fixtures/``, reaproveitados entre execuções.
"""
from __future__ import annotations

import os
import socket
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent

# O pacote s7editor e o tools/make_fixtures.py precisam estar importáveis mesmo
# quando o pytest é chamado de outro diretório.
for _p in (str(PROJECT_ROOT), str(PROJECT_ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import make_fixtures as mf  # noqa: E402  (depende do sys.path acima)

FIXTURES_DIR = Path(os.environ.get("S7EDITOR_TEST_FIXTURES") or (TESTS_DIR / "fixtures"))
FIXTURE_COUNT = int(os.environ.get("S7EDITOR_TEST_COUNT") or mf.DEFAULT_COUNT)


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "slow: lote completo de 30 imagens (dezenas de segundos)")
    config.addinivalue_line("markers", "needs_api: exige OPENAI_API_KEY de verdade; pulado por padrão")


class RedeBloqueadaError(RuntimeError):
    """Um teste tentou usar a rede. A suíte é 100% offline, por definição."""


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch: pytest.MonkeyPatch) -> None:
    """Derruba qualquer tentativa de rede e apaga a chave do ambiente."""
    # Loopback é liberado: o que esta guarda protege é a suíte não depender de
    # API externa, e o painel roda em 127.0.0.1. Bloquear localhost também
    # impediria testar a subida do próprio servidor, que é código nosso.
    locais = {"127.0.0.1", "::1", "localhost", "0.0.0.0", ""}

    def _eh_local(alvo: Any) -> bool:
        if isinstance(alvo, (tuple, list)) and alvo:
            host = alvo[0]
            return isinstance(host, str) and host in locais
        return False

    connect_real = socket.socket.connect
    connect_ex_real = socket.socket.connect_ex
    create_real = socket.create_connection
    getaddrinfo_real = socket.getaddrinfo

    def _erro() -> RedeBloqueadaError:
        return RedeBloqueadaError(
            "teste tentou acessar a rede: a suíte roda offline e a trilha "
            "determinística não pode depender de API."
        )

    def _connect(self: Any, alvo: Any, *a: Any, **k: Any):
        if not _eh_local(alvo):
            raise _erro()
        return connect_real(self, alvo, *a, **k)

    def _connect_ex(self: Any, alvo: Any, *a: Any, **k: Any):
        if not _eh_local(alvo):
            raise _erro()
        return connect_ex_real(self, alvo, *a, **k)

    def _create(alvo: Any, *a: Any, **k: Any):
        if not _eh_local(alvo):
            raise _erro()
        return create_real(alvo, *a, **k)

    def _getaddrinfo(host: Any, *a: Any, **k: Any):
        if not (isinstance(host, str) and host in locais):
            raise _erro()
        return getaddrinfo_real(host, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", _connect, raising=False)
    monkeypatch.setattr(socket.socket, "connect_ex", _connect_ex, raising=False)
    monkeypatch.setattr(socket, "create_connection", _create, raising=False)
    monkeypatch.setattr(socket, "getaddrinfo", _getaddrinfo, raising=False)
    for var in ("OPENAI_API_KEY", "S7EDITOR_ROOT", "S7EDITOR_INBOX", "S7EDITOR_OUTBOX",
                "S7EDITOR_CACHE", "S7EDITOR_FONTS", "S7EDITOR_DRY_RUN"):
        monkeypatch.delenv(var, raising=False)


# --------------------------------------------------------------------------- #
# Fixtures de imagem (gerados uma vez por sessão e cacheados em disco)
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def fixtures_manifest() -> dict[str, Any]:
    """Manifesto do lote sintético, gerando os PNGs se ainda não existirem."""
    return mf.ensure_fixtures(FIXTURES_DIR, count=FIXTURE_COUNT)


@pytest.fixture(scope="session")
def fixtures_dir(fixtures_manifest: dict[str, Any]) -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def creatives(fixtures_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """As entradas do lote padrão (30 criativos), na ordem."""
    return list(fixtures_manifest["creatives"])


@pytest.fixture(scope="session")
def hard_cases(fixtures_manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Os três casos difíceis: CTA sobre foto, sobre degradê e claro/claro."""
    return list(fixtures_manifest["hard_cases"])


@pytest.fixture(scope="session")
def creative_paths(fixtures_dir: Path, creatives: list[dict[str, Any]]) -> list[Path]:
    return [fixtures_dir / e["relpath"] for e in creatives]


@pytest.fixture
def settings_offline(tmp_path: Path):
    """:class:`Settings` sem chave, com todas as pastas dentro do tmp do teste."""
    from s7editor.config import load_settings

    st = load_settings(root=tmp_path, inbox=tmp_path / "inbox", outbox=tmp_path / "outbox",
                       cache_dir=tmp_path / ".cache", fonts_dir=PROJECT_ROOT / "fonts",
                       max_concurrency=4)
    # load_settings ainda pode achar uma chave num .env do usuário; para o teste,
    # a ausência de chave é parte do contrato.
    return replace(st, openai_api_key=None, key_source="teste offline")
