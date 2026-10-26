"""The working copy of every document, kept between runs: one qipu-records collection folder per document.

A new or changed document is staged next to its current folder (`<doc>.next`) and replaces it only once all its pages are
read. Until then the current folder keeps the pages that the published records were read from, so the gates still check
those records against the right text. Staging carries over every earlier reading whose page text is unchanged and that was
made with the same prompt and model, so only new or changed pages go to the model.
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


def _hashes(collection: Collection) -> dict[str, str]:
    return {p.page_id: text_hash(p.text) for p in collection.pages()}


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "docs").mkdir(parents=True, exist_ok=True)

    def folder(self, doc_id: str, staged: bool = False) -> Path:
        return self.root / "docs" / (safe_name(doc_id) + (".next" if staged else ""))

    def has(self, doc_id: str, staged: bool = False) -> bool:
        return (self.folder(doc_id, staged) / "pages.jsonl").exists()

    def collection(self, doc_id: str, staged: bool = False) -> Collection:
        return Collection(self.folder(doc_id, staged))

    def stage(self, doc_id: str, content: Content, keep: Callable[[Reading], bool]) -> int:
        """Write the document's new pages to its staging folder. Returns the number of readings carried over."""
        earlier = [self.collection(doc_id, staged) for staged in (False, True) if self.has(doc_id, staged)]
        target = self.folder(doc_id, staged=True)
        fresh = target.with_name(target.name + ".tmp")
        shutil.rmtree(fresh, ignore_errors=True)
        collection = Collection(fresh)
        collection.save_items([content.item])
        pages = [Page(make_page_id(doc_id, n), doc_id, n, text) for n, text in enumerate(content.pages)]
        collection.save_pages(pages)
        collection.save_page_maps({doc_id: content.page_map})
        new_hashes = {p.page_id: text_hash(p.text) for p in pages}
        kept: dict[str, Reading] = {}
        for old in earlier:
            old_hashes = _hashes(old)
            for page_id, reading in old.readings().items():
                if old_hashes.get(page_id) == new_hashes.get(page_id) and keep(reading):
                    kept[page_id] = reading
        for page_id in sorted(kept):
            collection.append_reading(kept[page_id])
        self._replace(fresh, target)
        return len(kept)

    def current_content(self, doc_id: str) -> Content:
        """The document as it is in the current copy, to rebuild it without downloading it again."""
        collection = self.collection(doc_id)
        pages = collection.pages()
        texts = [""] * (max((p.n for p in pages), default=-1) + 1)
        for page in pages:
            texts[page.n] = page.text
        return Content(collection.items()[doc_id], texts, collection.page_maps().get(doc_id))

    def promote(self, doc_id: str) -> None:
        """The staged document becomes the current one."""
        if self.has(doc_id, staged=True):
            self._replace(self.folder(doc_id, staged=True), self.folder(doc_id))

    @staticmethod
    def _replace(fresh: Path, target: Path) -> None:
        stale = target.with_name(target.name + ".old")
        shutil.rmtree(stale, ignore_errors=True)
        if target.exists():
            target.rename(stale)
        fresh.rename(target)
        shutil.rmtree(stale, ignore_errors=True)

    def unread(self, doc_id: str, staged: bool = False) -> int:
        """Pages with enough text to read that have no reading yet."""
        collection = self.collection(doc_id, staged)
        done = collection.readings()
        return sum(1 for p in collection.pages() if p.page_id not in done and len(p.text.strip()) >= MIN_PAGE_CHARS)

    def page_hashes(self, doc_id: str) -> dict[str, str]:
        return _hashes(self.collection(doc_id))


class WorkspacePages:
    """Page texts for the gates: the current (not staged) copy of each document."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self._docs: dict[str, tuple[list[str], str | None] | None] = {}

    def document(self, doc_id: str) -> tuple[list[str], str | None] | None:
        if doc_id not in self._docs:
            found = None
            if self.workspace.has(doc_id):
                collection = self.workspace.collection(doc_id)
                found = ([p.text for p in collection.pages()], collection.items()[doc_id].date)
            self._docs[doc_id] = found
        return self._docs[doc_id]

    def text(self, page_id: str) -> str | None:
        doc_id, _, n = page_id.rpartition(":")
        document = self.document(doc_id)
        if document is None or not n.isdigit() or int(n) >= len(document[0]):
            return None
        return document[0][int(n)]
