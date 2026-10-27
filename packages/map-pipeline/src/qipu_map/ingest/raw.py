"""The raw folder: what each source answered, kept as it came so a run can be repeated offline.

Every fetched file is written once. A file already there is the cache: the fetcher is not called again. The date each
source was fetched goes into `retrieved.json`, so `sources.json` can say it without putting today's date into outputs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

from qipu_map.files import read_json, write_atomic, write_json

log = logging.getLogger(__name__)

RETRIEVED = "retrieved.json"


class RawStore:
    """The raw folder of one run: each source's answer kept as fetched, with the date it was retrieved."""

    def __init__(self, root: Path, today: Callable[[], date] = date.today) -> None:
        self.root = root
        self._today = today

    def path(self, name: str) -> Path:
        return self.root / name

    def has(self, name: str) -> bool:
        return self.path(name).is_file()

    def fetch_once(self, source_id: str, name: str, produce: Callable[[], bytes]) -> bool:
        """Write `produce()` to `name` unless it is already there. True when it fetched."""
        if self.has(name):
            log.info("raw %s: cached", name)
            return False
        data = produce()
        write_atomic(self.path(name), data)
        self.mark_retrieved(source_id)
        log.info("raw %s: %d bytes", name, len(data))
        return True

    def read_json(self, name: str) -> Any:
        return read_json(self.path(name))

    def retrieved(self) -> dict[str, str]:
        p = self.path(RETRIEVED)
        data: dict[str, str] = read_json(p) if p.is_file() else {}
        return data

    def mark_retrieved(self, source_id: str) -> None:
        dates = self.retrieved()
        dates[source_id] = self._today().isoformat()
        write_json(self.path(RETRIEVED), dates)
