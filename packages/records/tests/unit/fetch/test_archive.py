from __future__ import annotations

import io
import time
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path

import pytest

from qipu_records.fetch.archive import ArchiveClient, Item, fetch_item, fetch_page_texts, split_pages
from tests.conftest import SavedArchive


def test_split_pages_at_the_page_index() -> None:
    assert split_pages("aaabbc", [0, 3, 5]) == ["aaa", "bb", "c"]


def test_item_from_catalogue_metadata() -> None:
    item = Item.from_metadata(
        "19740219",
        {"title": "Council Meeting Minutes : Feb. 19, 1974", "date": "1974-02-19", "creator": ["City of Vancouver, B.C."]},
    )
    assert item.creator == "City of Vancouver, B.C."
    assert item.licence is None
    assert item.url == "https://archive.org/details/19740219"


def test_page_texts_are_cut_at_the_page_index(saved_archive: SavedArchive) -> None:
    pages = fetch_page_texts(saved_archive, "19700609")
    assert len(pages) == 5
    assert "A  Regular  Meeting  of  the  Council" in pages[0]
    assert "Regular  Council,   June  9" in pages[4][:40]


def test_files_are_named_by_the_book_prefix_not_the_identifier(saved_archive: SavedArchive) -> None:
    fetch_page_texts(saved_archive, "19700609")
    assert "https://archive.org/download/19700609/1970-06-09_hocr_searchtext.txt.gz" in saved_archive.requested


def test_each_url_is_downloaded_once(saved_archive: SavedArchive) -> None:
    first = fetch_item(saved_archive, "19700609")
    second = fetch_item(saved_archive, "19700609")
    assert first == second
    assert first.licence == "http://creativecommons.org/publicdomain/zero/1.0/"
    assert saved_archive.requested.count("https://archive.org/metadata/19700609") == 1


class _Response(io.BytesIO):
    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_download_retries_server_errors_but_not_missing_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> _Response:
        calls.append(request.full_url)
        if request.full_url.endswith("missing"):
            raise urllib.error.HTTPError(request.full_url, 404, "Not Found", Message(), None)
        if len(calls) == 1:
            raise urllib.error.HTTPError(request.full_url, 503, "Busy", Message(), None)
        assert "qipu-records" in (request.get_header("User-agent") or "")
        return _Response(b"ok")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    client = ArchiveClient(tmp_path, pause=0)
    assert client.get_text("https://archive.org/x", "x") == "ok"
    assert len(calls) == 2
    with pytest.raises(urllib.error.HTTPError):
        client.get_bytes("https://archive.org/missing", "missing")
    assert len(calls) == 3
