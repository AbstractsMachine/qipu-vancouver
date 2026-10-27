"""A local copy of a collection, in qipu-records' collection format: for tests, demos and offline runs.

The copy is a collection folder (items.json, pages.jsonl, pagemaps.json, as in examples/vancouver) plus an index that
says
when each item appeared and, for an item scanned again, which pages file holds each version:

    [{"identifier": "19740219", "published": "2026-10-26",
      "versions": [{"updated": "2026-10-26", "pages": "../pages.jsonl"}]}]

Pages files are paths from the index's folder, in pages.jsonl's format; only the item's own lines are read. Run with an
earlier `as_of` and the mirror shows the collection as it was that day, so a test can play "a new meeting appeared" or
"an item was re-scanned" without the network.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from qipu_records.collection import read_jsonl
from qipu_records.fetch.archive import Item
from qipu_updates.sources import Content, Document, SourceError


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SourceError(f"mirror: {path.name}: {error}") from error


class MirrorSource:
    """A local copy of a collection, for tests and offline runs. The listing is complete."""

    complete = True

    def __init__(self, collection: Path, index: Path) -> None:
        self.collection = collection
        self.index = index
        self._pages: dict[str, list[str]] = {}

    def _version_pages(self, identifier: str, pages_file: str) -> list[str]:
        """The item's page texts in that version, by OCR page number; pages the file leaves out are blank."""
        rows = [row for row in read_jsonl(self.index.parent / pages_file) if row["item"] == identifier]
        pages = [""] * (max((int(r["n"]) for r in rows), default=-1) + 1)
        for row in rows:
            pages[int(row["n"])] = str(row["text"])
        return pages

    def discover(self, as_of: dt.date) -> list[Document]:
        day = as_of.isoformat()
        items = {row["identifier"]: row for row in _load(self.collection / "items.json")}
        found = []
        for entry in _load(self.index):
            identifier = entry["identifier"]
            versions = [v for v in entry["versions"] if v["updated"] <= day]
            if entry["published"] > day or not versions:
                continue
            latest = max(versions, key=lambda v: str(v["updated"]))
            pages = self._version_pages(identifier, latest["pages"])
            self._pages[identifier] = pages
            fingerprint = hashlib.sha256(json.dumps(pages).encode("utf-8")).hexdigest()
            date = items.get(identifier, {}).get("date")
            found.append(Document(identifier, date, fingerprint, f"https://archive.org/details/{identifier}"))
        return sorted(found, key=lambda d: d.doc_id)

    def content(self, doc: Document) -> Content:
        if doc.doc_id not in self._pages:
            raise SourceError(f"{doc.doc_id}: not in the mirror's listing (discover first)")
        items = {row["identifier"]: row for row in _load(self.collection / "items.json")}
        maps_path = self.collection / "pagemaps.json"
        maps = _load(maps_path) if maps_path.exists() else {}
        return Content(Item(**items[doc.doc_id]), self._pages[doc.doc_id], maps.get(doc.doc_id))
