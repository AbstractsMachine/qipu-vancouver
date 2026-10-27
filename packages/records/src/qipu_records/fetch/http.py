"""One HTTPS GET with a timeout and a few retries, shared by every download in this package and by qipu-updates.

A dropped connection, a timeout, a 5xx, a 408 or a 429 from archive.org, Legistar or the city's open-data portal is
usually gone a few seconds later, so those are retried with a growing pause. Any other 4xx (a 403, a 404, a 410) is an
answer, not an outage, and is raised at once. `HTTPError` is a subclass of `URLError` and `OSError`, so it has to be
told apart before the broad network errors are.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import TypeVar

RETRIES = 4
BACKOFF_SECONDS = 4.0
RETRIED_CLIENT_ERRORS = frozenset({408, 429})

T = TypeVar("T")


def retryable(error: BaseException) -> bool:
    if isinstance(error, urllib.error.HTTPError):
        return error.code >= 500 or error.code in RETRIED_CLIENT_ERRORS
    return isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError))


def with_retries(
    attempt: Callable[[], T],
    *,
    retries: int = RETRIES,
    backoff: float = BACKOFF_SECONDS,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Call `attempt` up to `retries` times, pausing `backoff`, then twice that, ... after each transient failure."""
    for n in range(retries):
        try:
            return attempt()
        except Exception as error:
            if not retryable(error) or n == retries - 1:
                raise
        (sleep or time.sleep)(backoff * (n + 1))
    raise ValueError(f"retries must be at least 1, got {retries}")


def get(
    url: str,
    *,
    user_agent: str,
    timeout: float,
    retries: int = RETRIES,
    headers: dict[str, str] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> bytes:
    """The body at `url`. Raises `ValueError` for a non-https URL and the last error once the retries are used up."""
    if not url.startswith("https://"):
        raise ValueError(f"only https URLs are fetched, not {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, **(headers or {})})  # noqa: S310 - https checked above

    def attempt() -> bytes:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - https checked above
            body: bytes = response.read()
        return body

    return with_retries(attempt, retries=retries, sleep=sleep)
