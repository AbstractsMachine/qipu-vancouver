from __future__ import annotations

from pathlib import Path

from qipu_records.fetch.archive import Item
from qipu_records.read.readers import Reading
from qipu_updates.incremental.workspace import Workspace, safe_name
from qipu_updates.sources import Content

ITEM = Item("m1", "Minutes", "1974-02-19", None, None, None)
LONG = "x" * 400


def content(*texts: str) -> Content:
    return Content(ITEM, list(texts), None)


def reading(page_id: str, prompt: str = "p1") -> Reading:
    return Reading(page_id, [{"quote": "q"}], "model", prompt)


def test_a_refresh_keeps_readings_of_pages_whose_text_is_the_same(tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    assert space.refresh("m1", content(LONG + "a", LONG + "b", LONG + "c"), lambda r: True) == 0
    for n in range(3):
        space.collection("m1").append_reading(reading(f"m1:{n}", "p1" if n else "p0"))
    assert space.unread("m1") == 0

    kept = space.refresh("m1", content(LONG + "a", LONG + "b changed", LONG + "c"), lambda r: r.prompt_version == "p1")
    assert kept == 1  # page 0: other prompt; page 1: new text; page 2: kept
    assert set(space.collection("m1").readings()) == {"m1:2"}
    assert space.unread("m1") == 2
    assert not (tmp_path / "docs" / "m1.new").exists() and not (tmp_path / "docs" / "m1.old").exists()


def test_short_pages_are_never_waiting_to_be_read(tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    space.refresh("m1", content("cover", LONG), lambda r: True)
    assert space.unread("m1") == 1
    assert set(space.page_hashes("m1")) == {"m1:0", "m1:1"}


def test_document_ids_become_safe_folder_names() -> None:
    assert safe_name("2026-10-21-budget/finance 1:2") == "2026-10-21-budget_finance_1_2"
