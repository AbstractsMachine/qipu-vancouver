"""Polite GETs for listings: a User-Agent that says who is asking, a pause between requests, a few retries.

The GET and its retry rule are qipu-records' (`qipu_records.fetch.http`): only a dropped connection, a timeout, a 5xx,
a 408 or a 429 is retried; a 404 is an answer. Listings are never cached (they are what changes); page texts are cached
by qipu-records' ArchiveClient.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from qipu_records.fetch import http
from qipu_updates.sources import SourceError

USER_AGENT = "qipu-updates/0.1 (+https://github.com/AbstractsMachine/qipu-vancouver; scheduled, one request at a time)"

Get = Callable[[str, dict[str, str]], bytes]


def urlopen_get(url: str, headers: dict[str, str]) -> bytes:
    """One attempt; `Polite` does the retrying. Raises SourceError for anything but https."""
    if not url.startswith("https://"):
        raise SourceError(f"only https is fetched: {url}")
    return http.get(url, user_agent=USER_AGENT, timeout=120, retries=1, headers=headers)


class Polite:
    """GETs that pause between requests and retry transient failures; SourceError when the source does not answer."""

    def __init__(
        self, get: Get = urlopen_get, pause: float = 1.0, retries: int = 3, sleep: Callable[[float], None] = time.sleep
    ):
        self._get, self.pause, self.retries, self._sleep = get, pause, retries, sleep
        self.requests = 0

    def get(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        if self.requests:
            self._sleep(self.pause)

        def attempt() -> bytes:
            self.requests += 1
            return self._get(url, headers or {})

        try:
            return http.with_retries(attempt, retries=self.retries + 1, backoff=2 * self.pause, sleep=self._sleep)
        except (OSError, TimeoutError) as error:
            raise SourceError(f"{url}: {error}") from error
