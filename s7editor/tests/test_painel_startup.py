"""Subida do painel: porta ocupada e a corrida com o navegador.

Os dois bugs que faziam o painel "não abrir" na máquina do usuário sem nenhuma
mensagem útil.
"""
from __future__ import annotations

import socket
import threading
import time

import pytest

from s7editor import webui


def _porta_ocupada() -> tuple[socket.socket, int]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    return s, s.getsockname()[1]


def test_porta_ocupada_cai_para_a_proxima():
    """Uma janela antiga do painel de pé não pode derrubar a nova com traceback."""
    sock, porta = _porta_ocupada()
    try:
        escolhida = webui._escolhe_porta("127.0.0.1", porta)
        assert escolhida != porta, "devia ter trocado de porta"
        assert escolhida > porta
        assert webui._porta_livre("127.0.0.1", escolhida)
    finally:
        sock.close()


def test_porta_livre_reconhece_livre_e_ocupada():
    sock, porta = _porta_ocupada()
    try:
        assert webui._porta_livre("127.0.0.1", porta) is False
    finally:
        sock.close()


def test_todas_ocupadas_da_erro_em_portugues():
    socks = []
    try:
        base = None
        for _ in range(3):
            s, p = _porta_ocupada()
            socks.append(s)
            base = p if base is None else base
        with pytest.raises(RuntimeError) as exc:
            webui._escolhe_porta("127.0.0.1", socks[0].getsockname()[1], tentativas=1)
        assert "ocupada" in str(exc.value).lower()
    finally:
        for s in socks:
            s.close()


def test_navegador_so_abre_depois_que_o_servidor_responde(monkeypatch):
    """Abrir junto com o comando era corrida perdida: o navegador chegava antes.

    O usuário via "não foi possível acessar este site" e concluía que o
    programa não funciona.
    """
    import webbrowser

    aberto_em: list[float] = []
    monkeypatch.setattr(webbrowser, "open",
                        lambda *_a, **_k: aberto_em.append(time.monotonic()))

    porta = _porta_livre_qualquer()
    webui._abre_quando_subir(f"http://127.0.0.1:{porta}", "127.0.0.1", porta, timeout=10)

    # Ninguém escutando ainda: o navegador não pode ter sido aberto.
    time.sleep(0.6)
    assert not aberto_em, "abriu o navegador antes de o servidor existir"

    servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    servidor.bind(("127.0.0.1", porta))
    servidor.listen(1)
    subiu_em = time.monotonic()
    try:
        prazo = time.monotonic() + 6
        while not aberto_em and time.monotonic() < prazo:
            time.sleep(0.1)
        assert aberto_em, "não abriu o navegador depois que o servidor subiu"
        assert aberto_em[0] >= subiu_em, "abriu antes de o servidor aceitar conexão"
    finally:
        servidor.close()


def _porta_livre_qualquer() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    porta = s.getsockname()[1]
    s.close()
    return porta


def test_espera_desiste_sem_travar(monkeypatch):
    """Se o servidor nunca subir, a thread morre sozinha e não abre nada."""
    import webbrowser
    chamou: list[int] = []
    monkeypatch.setattr(webbrowser, "open", lambda *_a, **_k: chamou.append(1))
    porta = _porta_livre_qualquer()
    webui._abre_quando_subir(f"http://127.0.0.1:{porta}", "127.0.0.1", porta, timeout=0.8)
    time.sleep(1.6)
    assert not chamou
    assert all(not t.name.startswith("esperar") for t in threading.enumerate())


def test_guarda_de_rede_ainda_barra_o_mundo_externo():
    """Liberar loopback não pode ter aberto a porteira para API externa."""
    from conftest import RedeBloqueadaError

    with pytest.raises(RedeBloqueadaError):
        socket.create_connection(("api.openai.com", 443), timeout=1)
    with pytest.raises(RedeBloqueadaError):
        socket.getaddrinfo("api.openai.com", 443)
