"""Shared test helpers: the bundled sample, and an archive.org client that answers from small saved responses."""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path
from typing import ClassVar

import pytest

from qipu_records.fetch.archive import ArchiveClient

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT.parents[1] / "examples" / "vancouver"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


class SavedArchive(ArchiveClient):
    """Serves archive.org URLs from tests/fixtures/archive, trimmed copies of real responses for item 19700609."""

    ROUTES: ClassVar[dict[str, str]] = {
        "https://archive.org/metadata/19700609": "19700609.metadata.json",
        "/BookReader/BookReaderJSIA.php": "19700609.bookreader.json",
        "/1970-06-09_jp2.zip/": "19700609_jp2.zip.html",
        "_hocr_searchtext.txt.gz": "19700609_hocr_searchtext.txt",
        "_hocr_pageindex.json.gz": "19700609_hocr_pageindex.json",
    }

    def __init__(self, cache_dir: Path) -> None:
        super().__init__(cache_dir, pause=0)
        self.requested: list[str] = []

    def _download(self, url: str) -> bytes:
        self.requested.append(url)
        for marker, name in self.ROUTES.items():
            if marker in url:
                body = (FIXTURES / "archive" / name).read_bytes()
                return gzip.compress(body) if url.endswith(".gz") else body
        raise AssertionError(f"no saved response for {url}")


@pytest.fixture
def saved_archive(tmp_path: Path) -> SavedArchive:
    return SavedArchive(tmp_path / "cache")


@pytest.fixture
def sample_copy(tmp_path: Path) -> Path:
    """A writable copy of the sample collection, without its readings."""
    folder = tmp_path / "collection"
    folder.mkdir()
    for name in ("items.json", "pages.jsonl", "pagemaps.json"):
        shutil.copy(SAMPLE / name, folder / name)
    return folder
