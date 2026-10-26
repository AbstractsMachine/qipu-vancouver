"""The fetch and read stages writing into a real collection folder."""

import json
import logging
from pathlib import Path

import pytest

from qipu_records.cities import VANCOUVER
from qipu_records.collection import Collection
from qipu_records.fetch.run import fetch_items
from qipu_records.read.readers import ReaderError, Reading, ReplayReader
from qipu_records.read.run import read_pages
from tests.conftest import SAMPLE, SavedArchive


def test_fetch_writes_items_pages_and_page_maps(tmp_path: Path, saved_archive: SavedArchive) -> None:
    collection = Collection(tmp_path / "van")
    assert fetch_items(collection, saved_archive, ["19700609"]) == 5
    assert collection.items()["19700609"].title == "Council Meeting Minutes : June 9, 1970"
    assert [p.page_id for p in collection.pages()] == [f"19700609:{n}" for n in range(5)]
    assert collection.page_maps() == {"19700609": [0, 1, 2, 3, 4]}
    requests = len(saved_archive.requested)
    assert fetch_items(collection, saved_archive, ["19700609"]) == 0
    assert len(saved_archive.requested) == requests


def test_read_skips_pages_already_read_and_stops_at_the_cap(sample_copy: Path) -> None:
    collection = Collection(sample_copy)
    reader = ReplayReader(SAMPLE / "readings.jsonl")
    assert read_pages(collection, reader, VANCOUVER, max_pages=4) == 4
    assert read_pages(collection, reader, VANCOUVER, max_pages=100) == 5
    assert read_pages(collection, reader, VANCOUVER, max_pages=100) == 0
    assert len(collection.readings()) == 9


class _Flaky:
    model = "flaky"

    def __init__(self) -> None:
        self.messages: list[str] = []

    def read(self, page_id: str, system_prompt: str, user_message: str) -> Reading:
        self.messages.append(user_message)
        if page_id.endswith(":1"):
            raise ReaderError(f"{page_id}: the answer is not the expected JSON")
        return Reading(page_id, [], self.model, "v")


def test_a_failed_page_is_logged_and_left_for_the_next_run(sample_copy: Path, caplog: pytest.LogCaptureFixture) -> None:
    collection = Collection(sample_copy)
    reader = _Flaky()
    with caplog.at_level(logging.WARNING):
        read_pages(collection, reader, VANCOUVER, max_pages=100)
    assert "19740219:1" not in collection.readings()
    assert "not the expected JSON" in caplog.text
    first_of_meeting = next(m for m in reader.messages if "A Regular meeting of the Council" in m)
    assert "PREVIOUS PAGE (context only):\n<<<\n\n>>>" in first_of_meeting
    assert "volume year 1974" in first_of_meeting


def test_short_pages_are_not_sent(sample_copy: Path) -> None:
    pages = [json.loads(line) for line in (sample_copy / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    pages[0]["text"] = "PLATE"
    (sample_copy / "pages.jsonl").write_text("".join(json.dumps(p) + "\n" for p in pages), encoding="utf-8")
    reader = _Flaky()
    read_pages(Collection(sample_copy), reader, VANCOUVER, max_pages=100)
    assert len(reader.messages) == 8
