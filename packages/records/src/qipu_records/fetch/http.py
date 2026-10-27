"""One HTTPS GET with a timeout and a few retries, shared by every download in this package.

A dropped connection or a 5xx from archive.org or the city's open-data portal is usually gone a few seconds later, so
those are retried with a growing pause. A 403 or 404 is an answer, not an outage, and is raised at once.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request

RETRIES = 4
BACKOFF_SECONDS = 4.0


def get(url: str, *, user_agent: str, timeout: float, retries: int = RETRIES) -> bytes:
    """The body at `url`. Raises `ValueError` for a non-https URL and the last error once the retries are used up."""
    if not url.startswith("https://"):
        raise ValueError(f"only https URLs are fetched, not {url!r}")
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})  # noqa: S310 - https checked above
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - https checked above
                body: bytes = response.read()
            return body
        except urllib.error.HTTPError as error:
            if error.code in (403, 404) or attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == retries - 1:
                raise
        time.sleep(BACKOFF_SECONDS * (attempt + 1))
    raise AssertionError("unreachable")
