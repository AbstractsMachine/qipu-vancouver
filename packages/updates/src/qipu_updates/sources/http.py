"""Polite GETs for listings: a User-Agent that says who is asking, a pause between requests, a few retries.

Listings are never cached (they are what changes); page texts are cached by qipu-records' ArchiveClient.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable

from qipu_updates.sources import SourceError

USER_AGENT = "qipu-updates/0.1 (+https://github.com/AbstractsMachine/qipu-open; scheduled, one request at a time)"

Get = Callable[[str, dict[str, str]], bytes]


def urlopen_get(url: str, headers: dict[str, str]) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    with urllib.request.urlopen(request, timeout=120) as response:
        body: bytes = response.read()
        return body


class Polite:
    def __init__(self, get: Get = urlopen_get, pause: float = 1.0, retries: int = 3, sleep: Callable[[float], None] = time.sleep):
        self._get, self.pause, self.retries, self._sleep = get, pause, retries, sleep
        self.requests = 0

    def get(self, url: str, headers: dict[str, str] | None = None) -> bytes:
        for attempt in range(self.retries + 1):
            if self.requests:
                self._sleep(self.pause * (2**attempt))
            self.requests += 1
            try:
                return self._get(url, headers or {})
            except (urllib.error.URLError, TimeoutError) as error:
                last = error
        raise SourceError(f"{url}: {last}")
