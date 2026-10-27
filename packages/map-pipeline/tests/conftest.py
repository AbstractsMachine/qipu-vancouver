"""Shared test setup: every test runs offline unless it is marked `network`."""

from __future__ import annotations

import socket
from typing import Any

import pytest

LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})


@pytest.fixture(autouse=True)
def _offline(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that reaches past this machine, so the suite gives the same answer offline and in CI.

    A RuntimeError, not an OSError, so retry loops that expect network errors do not swallow it. Tests marked
    `network` are exempt.
    """
    if request.node.get_closest_marker("network"):
        return
    real_getaddrinfo = socket.getaddrinfo
    real_connect = socket.socket.connect

    def getaddrinfo(host: object, *args: Any, **kwargs: Any) -> Any:
        if host is not None and str(host) not in LOOPBACK:
            raise RuntimeError(f"tests run offline; this one tried to look up {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)  # type: ignore[arg-type]

    def connect(sock: socket.socket, address: Any) -> None:
        if sock.family in (socket.AF_INET, socket.AF_INET6) and str(address[0]) not in LOOPBACK:
            raise RuntimeError(f"tests run offline; this one tried to connect to {address!r}")
        real_connect(sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", connect)
