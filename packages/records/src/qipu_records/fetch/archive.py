"""Read items from the Internet Archive: metadata and the OCR text of each page.

Every download is cached on disk and made at most once, about one request a second, with a User-Agent that says who is
asking. archive.org publishes the OCR of a scanned item as two files: the plain text of the whole item and an index of
where each page starts in it. Splitting the text at those offsets gives one text per OCR page, in scan order.
"""

from __future__ import annotations

import gzip
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qipu_records.fetch import http

USER_AGENT = (
    "qipu-records/0.1 (+https://github.com/AbstractsMachine/qipu-vancouver; cached, about one request a second)"
)
PAUSE_SECONDS = 1.0
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")
"""What archive.org accepts as an item identifier. Anything else is refused before it reaches a URL or a file name."""


def check_identifier(identifier: str) -> str:
    """The identifier, if archive.org could have issued it; ValueError otherwise."""
    if not IDENTIFIER.fullmatch(identifier):
        raise ValueError(f"not an archive.org identifier: {identifier!r}")
    return identifier


@dataclass(frozen=True)
class Item:
    """An archive.org item: one volume or one meeting's minutes."""

    identifier: str
    title: str
    date: str | None
    licence: str | None
    rights: str | None
    creator: str | None

    @property
    def url(self) -> str:
        return f"https://archive.org/details/{self.identifier}"

    @classmethod
    def from_metadata(cls, identifier: str, metadata: dict[str, Any]) -> Item:
        def first(key: str) -> str | None:
            value = metadata.get(key)
            if isinstance(value, list):
                value = value[0] if value else None
            return str(value) if value is not None else None

        return cls(
            identifier,
            first("title") or identifier,
            first("date"),
            first("licenseurl"),
            first("rights"),
            first("creator"),
        )


class ArchiveClient:
    """Cached, polite HTTP reads from archive.org."""

    def __init__(self, cache_dir: Path, pause: float = PAUSE_SECONDS) -> None:
        self.cache_dir = cache_dir
        self.pause = pause
        cache_dir.mkdir(parents=True, exist_ok=True)

    def get_bytes(self, url: str, cache_name: str) -> bytes:
        """The body at `url`, from the cache when it has been fetched before."""
        path = self.cache_dir / (cache_name + ".gz")
        if path.exists():
            return gzip.decompress(path.read_bytes())
        body = self._download(url)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(body))
        tmp.replace(path)
        return body

    def get_text(self, url: str, cache_name: str) -> str:
        return self.get_bytes(url, cache_name).decode("utf-8", errors="replace")

    def _download(self, url: str) -> bytes:
        body = http.get(url, user_agent=USER_AGENT, timeout=300)
        time.sleep(self.pause)
        return body


def fetch_metadata(client: ArchiveClient, identifier: str) -> dict[str, Any]:
    """The item's full metadata record: catalogue fields, file list, and the server that holds it."""
    check_identifier(identifier)
    record: dict[str, Any] = json.loads(
        client.get_text(f"https://archive.org/metadata/{identifier}", f"{identifier}.meta.json")
    )
    return record


def fetch_item(client: ArchiveClient, identifier: str) -> Item:
    return Item.from_metadata(identifier, fetch_metadata(client, identifier).get("metadata", {}))


def book_prefix(record: dict[str, Any]) -> str:
    """The name the item's scan files start with. Often the identifier, but not always ("1970-06-09_jp2.zip" in
    "19700609")."""
    for suffix in ("_hocr_searchtext.txt.gz", "_jp2.zip"):
        for entry in record.get("files", []):
            if entry["name"].endswith(suffix):
                return str(entry["name"][: -len(suffix)])
    return str(record.get("metadata", {}).get("identifier", ""))


def split_pages(text: str, page_starts: list[int]) -> list[str]:
    """Cut an item's OCR text into pages at the offsets of its page index."""
    ends = [*page_starts[1:], len(text)]
    return [text[start:end] for start, end in zip(page_starts, ends, strict=True)]


def fetch_page_texts(client: ArchiveClient, identifier: str) -> list[str]:
    """The OCR text of every page of an item, in scan order."""
    prefix = book_prefix(fetch_metadata(client, identifier))
    base = f"https://archive.org/download/{identifier}/{prefix}"
    raw_text = client.get_bytes(base + "_hocr_searchtext.txt.gz", f"{identifier}_hocr_searchtext.txt")
    raw_index = client.get_bytes(base + "_hocr_pageindex.json.gz", f"{identifier}_hocr_pageindex.json")
    text = gzip.decompress(raw_text).decode("utf-8", errors="replace")
    return split_pages(text, [entry[0] for entry in json.loads(gzip.decompress(raw_index))])
