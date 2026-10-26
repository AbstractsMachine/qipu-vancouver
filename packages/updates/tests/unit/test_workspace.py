from __future__ import annotations

from pathlib import Path

from qipu_records.fetch.archive import Item
from qipu_records.read.readers import Reading
from qipu_updates.incremental.workspace import Workspace, WorkspacePages, safe_name
from qipu_updates.sources import Content

ITEM = Item("m1", "Minutes", "1974-02-19", None, None, None)
LONG = "x" * 400


def content(*texts: str) -> Content:
    return Content(ITEM, list(texts), None)


def reading(page_id: str, prompt: str = "p1") -> Reading:
    return Reading(page_id, [{"quote": "q"}], "model", prompt)


def test_staging_keeps_readings_of_pages_whose_text_is_the_same(tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    assert space.stage("m1", content(LONG + "a", LONG + "b", LONG + "c"), lambda r: True) == 0
    for n in range(3):
        space.collection("m1", staged=True).append_reading(reading(f"m1:{n}", "p1" if n else "p0"))
    space.promote("m1")
    assert space.unread("m1") == 0
    assert not space.has("m1", staged=True)

    kept = space.stage("m1", content(LONG + "a", LONG + "b changed", LONG + "c"), lambda r: r.prompt_version == "p1")
    assert kept == 1  # page 0: another prompt; page 1: new text; page 2: kept
    assert set(space.collection("m1", staged=True).readings()) == {"m1:2"}
    assert space.unread("m1", staged=True) == 2
    assert space.unread("m1") == 0, "the current copy is untouched until the staged one is promoted"


def test_a_second_staging_keeps_what_the_first_one_read(tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    space.stage("m1", content(LONG + "a", LONG + "b"), lambda r: True)
    space.collection("m1", staged=True).append_reading(reading("m1:0"))
    assert space.stage("m1", content(LONG + "a", LONG + "b"), lambda r: True) == 1


def test_the_current_copy_can_be_staged_again_without_downloading(tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    space.stage("m1", content("", LONG), lambda r: True)
    space.promote("m1")
    again = space.current_content("m1")
    assert again.pages == ["", LONG]
    assert again.item == ITEM


def test_gates_read_the_current_copy(tmp_path: Path) -> None:
    space = Workspace(tmp_path)
    space.stage("m1", content("cover", LONG), lambda r: True)
    pages = WorkspacePages(space)
    assert pages.document("m1") is None  # staged only
    space.promote("m1")
    assert WorkspacePages(space).document("m1") == (["cover", LONG], "1974-02-19")
    assert WorkspacePages(space).text("m1:1") == LONG
    assert WorkspacePages(space).text("m1:7") is None
    assert WorkspacePages(space).text("m2:0") is None
    assert space.unread("m1") == 1
    assert set(space.page_hashes("m1")) == {"m1:0", "m1:1"}


def test_document_ids_become_safe_folder_names() -> None:
    assert safe_name("2026-10-21-budget/finance 1:2") == "2026-10-21-budget_finance_1_2"
