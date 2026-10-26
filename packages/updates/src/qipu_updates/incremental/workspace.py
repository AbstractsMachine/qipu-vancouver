"""The working copy of every document, kept between runs: one qipu-records collection folder per document.

When a document changes, its folder is replaced by one made from the new pages, and each earlier reading is carried over when
its page's text is the same and it was made with the same prompt and model. A re-scan that changes two pages of a forty-page
meeting costs two model calls, not forty.
"""

from __future__ import annotations

import hashlib
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from qipu_records.collection import Collection, Page, make_page_id
from qipu_records.read.readers import Reading
from qipu_records.read.run import MIN_PAGE_CHARS
from qipu_updates.sources import Content


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def safe_name(doc_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", doc_id)


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "docs").mkdir(parents=True, exist_ok=True)

    def folder(self, doc_id: str) -> Path:
        return self.root / "docs" / safe_name(doc_id)

    def has(self, doc_id: str) -> bool:
        return (self.folder(doc_id) / "pages.jsonl").exists()

    def collection(self, doc_id: str) -> Collection:
        return Collection(self.folder(doc_id))

    def refresh(self, doc_id: str, content: Content, keep: Callable[[Reading], bool]) -> int:
        """Replace the document's folder with its new pages. Returns the number of readings carried over."""
        fresh = self.folder(doc_id).with_name(self.folder(doc_id).name + ".new")
        shutil.rmtree(fresh, ignore_errors=True)
        collection = Collection(fresh)
        collection.save_items([content.item])
        pages = [Page(make_page_id(doc_id, n), doc_id, n, text) for n, text in enumerate(content.pages)]
        collection.save_pages(pages)
        collection.save_page_maps({doc_id: content.page_map})
        carried = 0
        if self.has(doc_id):
            old = self.collection(doc_id)
            old_hashes = {p.page_id: text_hash(p.text) for p in old.pages()}
            new_hashes = {p.page_id: text_hash(p.text) for p in pages}
            for page_id, reading in sorted(old.readings().items()):
                if old_hashes.get(page_id) == new_hashes.get(page_id) and keep(reading):
                    collection.append_reading(reading)
                    carried += 1
        self._swap(fresh, self.folder(doc_id))
        return carried

    @staticmethod
    def _swap(fresh: Path, target: Path) -> None:
        stale = target.with_name(target.name + ".old")
        shutil.rmtree(stale, ignore_errors=True)
        if target.exists():
            target.rename(stale)
        fresh.rename(target)
        shutil.rmtree(stale, ignore_errors=True)

    def unread(self, doc_id: str) -> int:
        """Pages with enough text to read that have no reading yet."""
        collection = self.collection(doc_id)
        done = collection.readings()
        return sum(1 for p in collection.pages() if p.page_id not in done and len(p.text.strip()) >= MIN_PAGE_CHARS)

    def page_hashes(self, doc_id: str) -> dict[str, str]:
        return {p.page_id: text_hash(p.text) for p in self.collection(doc_id).pages()}
