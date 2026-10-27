"""Where documents come from.

A source answers two questions: what documents exist today (`discover`) and what one of them says (`content`, the page
texts). A document's fingerprint changes whenever its text may have changed; the run compares
fingerprints with the last release to decide what to process.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Protocol

from qipu_records.fetch.archive import Item
from qipu_records.link.pagemap import PageMap


@dataclass(frozen=True)
class Document:
    """One unit of work: an archive.org item, or one meeting's minutes."""

    doc_id: str
    date: str | None
    fingerprint: str
    url: str


@dataclass(frozen=True)
class Content:
    item: Item
    pages: list[str]
    page_map: PageMap | None


class SourceError(RuntimeError):
    pass


class Source(Protocol):
    complete: bool
    """True when `discover` lists everything the source holds; False when it shows a window, such as the last two
    months. Only a complete listing is compared with the last release to catch a listing that came back short.
    """

    def discover(self, as_of: dt.date) -> list[Document]: ...

    def content(self, doc: Document) -> Content: ...
