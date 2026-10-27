from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

from qipu_records.fetch.archive import ArchiveClient
from qipu_updates.sources import Document, SourceError, archive, legistar, mirror
from qipu_updates.sources.http import Polite
from tests.conftest import EXAMPLE

FIXTURES = Path(__file__).parents[1] / "fixtures"
DAY = dt.date(2026, 10, 26)


class FakeGet:
    """Answers by URL substring; records each request."""

    def __init__(self, answers: dict[str, bytes]) -> None:
        self.answers = answers
        self.urls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]) -> bytes:
        self.urls.append(url)
        for key, body in self.answers.items():
            if key in url:
                return body
        raise urllib.error.URLError(f"no answer for {url}")


def polite(answers: dict[str, bytes]) -> tuple[Polite, FakeGet]:
    fake = FakeGet(answers)
    return Polite(fake, pause=0, sleep=lambda s: None), fake


def test_polite_retries_then_gives_up() -> None:
    sleeps: list[float] = []
    http = Polite(FakeGet({}), pause=1.0, retries=2, sleep=sleeps.append)
    with pytest.raises(SourceError, match="no answer"):
        http.get("https://example.org/x")
    assert http.requests == 3
    assert sleeps == [2.0, 4.0]


def test_an_archive_item_is_fingerprinted_by_its_last_update() -> None:
    doc = archive.document(
        {
            "identifier": "19740219",
            "date": "1974-02-19T00:00:00Z",
            "oai_updatedate": ["2014-03-27T23:19:12Z", "2024-02-27T15:30:14Z"],
        }
    )
    assert doc == Document("19740219", "1974-02-19", "2024-02-27T15:30:14Z", "https://archive.org/details/19740219")
    assert archive.document({"identifier": "x", "publicdate": "2014-01-01"}).fingerprint == "2014-01-01"


def test_the_archive_listing_follows_the_cursor_and_stops_at_as_of(tmp_path: Path) -> None:
    page1 = {"items": [{"identifier": "b", "publicdate": "2014-03-27T00:00:00Z"}], "cursor": "c2"}
    page2 = {
        "items": [
            {"identifier": "a", "publicdate": "2014-03-27T00:00:00Z"},
            {"identifier": "z", "publicdate": "2030-01-01"},
        ]
    }
    http, fake = polite({"cursor=c2": json.dumps(page2).encode(), "scrape": json.dumps(page1).encode()})
    source = archive.ArchiveSource("cityofvancouvercouncilminutes", tmp_path, http)
    assert [d.doc_id for d in source.discover(DAY)] == ["a", "b"]
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(fake.urls[0]).query)
    assert query["q"] == ["collection:cityofvancouvercouncilminutes"]


def test_a_broken_archive_listing_is_an_error(tmp_path: Path) -> None:
    http, _ = polite({"scrape": b'{"error": "busy"}'})
    with pytest.raises(SourceError, match="busy"):
        archive.ArchiveSource("c", tmp_path, http).discover(DAY)


def test_archive_content_uses_one_cache_folder_per_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Path] = []

    def fetch_item(client: ArchiveClient, identifier: str) -> str:
        seen.append(client.cache_dir)
        return "item"

    monkeypatch.setattr(archive, "fetch_item", fetch_item)
    monkeypatch.setattr(archive, "fetch_page_texts", lambda client, i: ["page"])
    monkeypatch.setattr(archive, "fetch_map", lambda client, i: None)
    source = archive.ArchiveSource("c", tmp_path)
    source.content(Document("m1", None, "v1", "u"))
    content = source.content(Document("m1", None, "v2", "u"))
    assert content.pages == ["page"]
    assert seen[0] != seen[1]
    assert [p.name for p in (tmp_path / "m1").iterdir()] == [seen[1].name]


def test_the_legistar_calendar_lists_meetings_and_their_minutes() -> None:
    meetings = legistar.parse_calendar((FIXTURES / "legistar_calendar.html").read_text(encoding="utf-8"))
    assert [(m["body"], m["date"], m["minutes_url"] is not None) for m in meetings] == [
        ("Public Safety and Neighborhood Services Committee", "2026-10-22", True),
        ("Budget and Finance Committee", "2026-10-21", True),
        ("Public Safety and Neighborhood Services Committee", "2026-10-29", False),
    ]
    assert meetings[0]["minutes_url"].startswith("https://sfgov.legistar.com/View.ashx?M=M&ID=")
    assert legistar.mdy("9/29/26") == "2026-09-29"
    assert legistar.mdy("soon") is None


def test_legistar_minutes_become_documents_fingerprinted_by_their_pdf() -> None:
    calendar = (FIXTURES / "legistar_calendar.html").read_bytes()
    http, fake = polite({"Calendar.aspx": calendar, "View.ashx?M=M": b"%PDF-1.7 minutes"})
    source = legistar.LegistarSource(months=("This Month",), http=http, to_text=lambda pdf: ["page one", "page two"])
    docs = source.discover(DAY)
    assert [d.doc_id.split("-", 3)[3].rsplit("-", 1)[0] for d in docs] == [
        "budget-and-finance-committee",
        "public-safety-and-neighborhood-services-committee",
    ]
    assert len({d.fingerprint for d in docs}) == 1
    assert len(docs[0].fingerprint) == 64
    content = source.content(docs[0])
    assert content.pages == ["page one", "page two"]
    assert content.item.title == "Budget and Finance Committee, minutes of 2026-10-21"
    assert sum("View.ashx" in u for u in fake.urls) == 2


def test_legistar_refuses_minutes_that_are_not_a_pdf() -> None:
    http, _ = polite({"Calendar.aspx": (FIXTURES / "legistar_calendar.html").read_bytes(), "View.ashx": b"<html>"})
    with pytest.raises(SourceError, match="not a PDF"):
        legistar.LegistarSource(months=("This Month",), http=http).discover(DAY)


def test_the_mirror_shows_the_collection_as_it_was_on_a_day() -> None:
    source = mirror.MirrorSource(EXAMPLE, EXAMPLE / "updates" / "arrivals.json")
    assert [d.doc_id for d in source.discover(dt.date(2026, 10, 18))] == []
    assert [d.doc_id for d in source.discover(dt.date(2026, 10, 19))] == ["19700609"]
    docs = source.discover(DAY)
    assert [(d.doc_id, d.date) for d in docs] == [("19700609", "1970-06-09"), ("19740219", "1974-02-19")]
    content = source.content(docs[0])
    assert len(content.pages) == 13
    assert content.pages[0] == ""
    assert content.pages[10]
    assert content.page_map is not None
    assert content.item.title.startswith("Council Meeting Minutes")


def test_the_mirror_needs_a_listing_first_and_a_readable_index(tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="discover first"):
        mirror.MirrorSource(EXAMPLE, EXAMPLE / "updates" / "arrivals.json").content(
            Document("19700609", None, "f", "u")
        )
    with pytest.raises(SourceError, match=r"missing\.json"):
        mirror.MirrorSource(EXAMPLE, tmp_path / "missing.json").discover(DAY)


def test_a_pdf_that_pdftotext_cannot_read_is_a_source_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fails(command: list[str], **kwargs: object) -> object:
        assert kwargs["timeout"] == legistar.PDFTOTEXT_TIMEOUT_S
        raise subprocess.TimeoutExpired(command, legistar.PDFTOTEXT_TIMEOUT_S)

    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/pdftotext")
    monkeypatch.setattr(subprocess, "run", fails)
    with pytest.raises(SourceError, match="could not read the minutes PDF"):
        legistar.pdftotext(b"%PDF-1.7")
