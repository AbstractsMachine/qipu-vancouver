"""The network edge: one small interface so the fetchers can be tested without it.

The retry rule matches qipu-records' `fetch/http.py` (this package does not depend on it): a dropped connection, a
timeout, a 5xx, a 408 or a 429 is retried; any other 4xx is an answer and is raised at once. `HTTPError` is a subclass
of `OSError`, so it is told apart first.
"""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Protocol

log = logging.getLogger(__name__)

USER_AGENT = "qipu-map/0.1 (+https://github.com/AbstractsMachine/qipu-vancouver)"
RETRIED_CLIENT_ERRORS = frozenset({408, 429})


def retryable(exc: OSError) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500 or exc.code in RETRIED_CLIENT_ERRORS
    return True


class Http(Protocol):
    """The network edge the fetchers use: a GET with query parameters and a form POST, each returning the body."""

    def get(self, url: str, params: Mapping[str, str] | None = None) -> bytes: ...

    def post(self, url: str, form: Mapping[str, str]) -> bytes: ...


class UrllibHttp:
    """Plain urllib with a few retries and a growing pause: the open-data portals and Overpass drop requests now and
    then."""

    def __init__(self, tries: int = 4, timeout_s: float = 180.0, pause_s: float = 4.0) -> None:
        self.tries = tries
        self.timeout_s = timeout_s
        self.pause_s = pause_s

    def get(self, url: str, params: Mapping[str, str] | None = None) -> bytes:
        full = f"{url}?{urllib.parse.urlencode(params)}" if params else url
        return self._send(full)

    def post(self, url: str, form: Mapping[str, str]) -> bytes:
        return self._send(url, urllib.parse.urlencode(form).encode())

    def _send(self, url: str, body: bytes | None = None) -> bytes:
        if urllib.parse.urlsplit(url).scheme != "https":
            raise ValueError(f"only https sources are fetched: {url}")
        req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})  # noqa: S310 (https checked above)
        for attempt in range(self.tries):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:  # noqa: S310 (https checked above)
                    data: bytes = resp.read()
                    return data
            except OSError as exc:
                if not retryable(exc) or attempt == self.tries - 1:
                    raise
                log.warning("retrying %s after %s", req.full_url[:120], exc)
                time.sleep(self.pause_s * (attempt + 1))
        raise AssertionError("unreachable")


def post_first(http: Http, urls: Sequence[str], form: Mapping[str, str]) -> bytes:
    """POST to each mirror in turn until one answers."""
    last: Exception | None = None
    for url in urls:
        try:
            return http.post(url, form)
        except OSError as exc:
            log.warning("%s failed: %s", url, exc)
            last = exc
    raise RuntimeError(f"every mirror failed: {', '.join(urls)}") from last
