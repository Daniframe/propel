import socket

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No test may make a network call (CLAUDE.md §12); fail loudly if one tries."""

    def refuse(*args, **kwargs):
        raise RuntimeError("tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
