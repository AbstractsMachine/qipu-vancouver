"""An archive.org collection: Vancouver's council minutes (cityofvancouvercouncilminutes), one item per meeting.

The listing comes from the scrape API, 1,000 items a request. An item's fingerprint is its last update time on archive.org
(the newest `oai_updatedate`), so a re-scan or a new OCR makes it "changed". Its pages are read with qipu-records, into a cache
folder per fingerprint: a changed item is downloaded again, an unchanged one never is.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import urllib.parse
from pathlib import Path
from typing import Any

from qipu_records.fetch.archive import ArchiveClient, fetch_item, fetch_page_texts
from qipu_records.link.pagemap import fetch_map
from qipu_updates.sources import Content, Document, SourceError
from qipu_updates.sources.http import Polite

SCRAPE = "https://archive.org/services/search/v1/scrape"
FIELDS = "identifier,date,publicdate,oai_updatedate"


def _newest(value: Any) -> str:
    values = value if isinstance(value, list) else [value]
    return max((str(v) for v in values if v), default="")


def document(row: dict[str, Any]) -> Document:
    identifier = str(row["identifier"])
    stamp = _newest(row.get("oai_updatedate")) or str(row.get("publicdate") or "")
    date = str(row.get("date") or "")[:10] or None
    return Document(identifier, date, stamp, f"https://archive.org/details/{identifier}")


class ArchiveSource:
    complete = True

    def __init__(self, collection: str, cache_dir: Path, http: Polite | None = None) -> None:
        self.collection = collection
        self.cache_dir = cache_dir
        self.http = http or Polite()

    def _listing(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            query = {"q": f"collection:{self.collection}", "fields": FIELDS, "count": "1000"}
            if cursor:
                query["cursor"] = cursor
            page = json.loads(self.http.get(f"{SCRAPE}?{urllib.parse.urlencode(query)}"))
            if "items" not in page:
                raise SourceError(f"archive.org listing of {self.collection}: {str(page)[:200]}")
            rows.extend(page["items"])
            cursor = page.get("cursor")
            if not cursor:
                return rows

    def discover(self, as_of: dt.date) -> list[Document]:
        """Items made public on or before `as_of`."""
        day = as_of.isoformat()
        return sorted(
            (document(row) for row in self._listing() if str(row.get("publicdate") or "")[:10] <= day),
            key=lambda d: d.doc_id,
        )

    def content(self, doc: Document) -> Content:
        version = hashlib.sha1(doc.fingerprint.encode()).hexdigest()[:12]
        folder = self.cache_dir / doc.doc_id
        client = ArchiveClient(folder / version)
        content = Content(fetch_item(client, doc.doc_id), fetch_page_texts(client, doc.doc_id), fetch_map(client, doc.doc_id))
        for old in folder.iterdir():
            if old.name != version:
                shutil.rmtree(old, ignore_errors=True)
        return content
