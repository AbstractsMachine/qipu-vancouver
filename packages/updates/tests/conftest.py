"""Shared test helpers: the Vancouver example, copied so a test can change it, and small hand-made records."""

from __future__ import annotations

import shutil
import socket
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "examples" / "vancouver"


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


@pytest.fixture
def example(tmp_path: Path) -> Path:
    """A copy of examples/vancouver; its updates config is at updates/updates.toml."""
    copy = tmp_path / "vancouver"
    shutil.copytree(EXAMPLE, copy, ignore=shutil.ignore_patterns("README.md"))
    return copy


class Pages:
    """Page texts for the gates, from a dict: {"item:n": text}, with catalogue dates per item."""

    def __init__(self, texts: dict[str, str], dates: dict[str, str] | None = None) -> None:
        self.texts, self.dates = texts, dates or {}

    def text(self, page_id: str) -> str | None:
        return self.texts.get(page_id)

    def document(self, doc_id: str) -> tuple[list[str], str | None] | None:
        numbered = {int(k.rpartition(":")[2]): v for k, v in self.texts.items() if k.rpartition(":")[0] == doc_id}
        if not numbered:
            return None
        return [numbered.get(n, "") for n in range(max(numbered) + 1)], self.dates.get(doc_id)


def record(rid: str = "m1:0/1", **fields: Any) -> dict[str, Any]:
    """A decision record with the fields the gates read; override any of them."""
    item, _, rest = rid.partition(":")
    base: dict[str, Any] = {
        "id": rid,
        "city": "vancouver",
        "body": "Vancouver City Council",
        "date": "1974-02-19",
        "kind": "resolution",
        "action": "adopted",
        "stage": "adopted",
        "outcome": "passed",
        "zoning": None,
        "summary": "",
        "quote": "",
        "vote": None,
        "mover": None,
        "seconder": None,
        "money": [],
        "parties": [],
        "places": [],
        "source": {"item": item, "ocr_page": int(rest.split("/")[0]), "page_url": None},
    }
    base.update(fields)
    return base
