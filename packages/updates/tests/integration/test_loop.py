"""Full runs on the Vancouver sample: a meeting arrives, an item is re-scanned, a gate fails, a run is paused or rolled
back.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from qipu_records.cities import get_city
from qipu_updates import config as cfg
from qipu_updates.incremental.extract import Extractor
from qipu_updates.incremental.workspace import Workspace
from qipu_updates.loop import Options, Run
from qipu_updates.monitor.metrics import RunReport
from qipu_updates.publish import releases as rel
from qipu_updates.publish.local import LocalStore
from qipu_updates.schedule import control
from qipu_updates.wiring import make_reader, make_source

DAY1, DAY2, DAY3 = dt.date(2026, 10, 19), dt.date(2026, 10, 26), dt.date(2026, 10, 27)
PAGES_1970, PAGES_1974 = 3, 6
"""Pages of each sample meeting with enough text to be read."""


def run(example: Path, tmp: Path, day: dt.date, run_id: str, windowed: bool = False, **options: bool) -> RunReport:
    config = cfg.load(example / "updates" / "updates.toml")
    work = tmp / "work"
    extractor = Extractor(get_city(config.city), make_reader(config.reader), config.reader.model, day, config.gazetteer)
    source = make_source(config.source, work / "cache")
    source.complete = not windowed
    loop = Run(config, LocalStore(tmp / "store"), Workspace(work), source, extractor)
    now = dt.datetime.combine(day, dt.time(14, 17), dt.UTC)
    return loop(Options(run_id, day, now, **{"force": True, **options}))


def store(tmp: Path) -> LocalStore:
    return LocalStore(tmp / "store")


def published_records(tmp: Path, version: str) -> list[dict[str, object]]:
    lines = (tmp / "store" / "releases" / version / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def rescan(example: Path, day: str, page: int, extra: str, replace: bool = False) -> None:
    """Add a new version of 19700609 in which one page has more text, or other text."""
    rows = [json.loads(line) for line in (example / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    for row in rows:
        if row["item"] == "19700609" and row["n"] == page:
            row["text"] = extra if replace else row["text"] + extra
    (example / "updates" / "pages-v2.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    index_path = example / "updates" / "arrivals.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index[0]["versions"].append({"updated": day, "pages": "pages-v2.jsonl"})
    index_path.write_text(json.dumps(index), encoding="utf-8")


def set_rules(example: Path, *rules: dict[str, object]) -> None:
    (example / "updates" / "corrections.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rules), encoding="utf-8"
    )


def test_a_new_meeting_is_the_only_thing_processed(example: Path, tmp_path: Path) -> None:
    first = run(example, tmp_path, DAY1, "day1")
    assert (first.status, first.release, first.records, first.pages_read) == (
        "published",
        "2026-10-19.1",
        11,
        PAGES_1970,
    )

    second = run(example, tmp_path, DAY2, "day2")
    assert second.status == "published"
    assert second.plan == {"new": 1, "changed": 0, "unchanged": 1, "missing": 0}
    assert second.documents_built == ["19740219"]
    assert second.pages_read == PAGES_1974
    assert (second.release, second.records, second.records_before) == ("2026-10-26.1", 33, 11)

    releases = tmp_path / "store" / "releases"
    old = (releases / "2026-10-19.1" / "records" / "19700609.jsonl").read_bytes()
    assert (releases / "2026-10-26.1" / "records" / "19700609.jsonl").read_bytes() == old
    runs = {r["source"]["item"]: r["provenance"]["run_id"] for r in published_records(tmp_path, "2026-10-26.1")}  # type: ignore[index]
    assert runs == {"19700609": "day1", "19740219": "day2"}
    pointer = rel.current(store(tmp_path))
    assert pointer is not None
    assert (pointer.version, pointer.previous) == ("2026-10-26.1", "2026-10-19.1")


def test_every_record_traces_to_a_page_a_prompt_and_a_run(example: Path, tmp_path: Path) -> None:
    run(example, tmp_path, DAY2, "day2")
    manifest = rel.manifest(store(tmp_path), "2026-10-26.1")
    assert manifest is not None
    assert manifest.counts == {"documents": 2, "records": 33, "withdrawn": 0}
    for record in published_records(tmp_path, "2026-10-26.1"):
        assert record["reading"] == {"model": "claude-haiku-5-5", "prompt_version": manifest.build_key.split("|")[1]}
        provenance = record["provenance"]
        assert isinstance(provenance, dict)
        assert provenance["run_id"] == "day2"
        assert len(provenance["page_sha256"]) == 64
        assert str(provenance["document"]).startswith("https://archive.org/details/")


def test_a_rerun_with_nothing_new_publishes_nothing(example: Path, tmp_path: Path) -> None:
    run(example, tmp_path, DAY2, "day2")
    again = run(example, tmp_path, DAY2, "day2-again")
    assert (again.status, again.pages_read, again.records) == ("no-change", 0, 33)
    assert rel.versions(store(tmp_path)) == ["2026-10-26.1"]


def test_a_rescanned_item_rereads_only_the_changed_page(example: Path, tmp_path: Path) -> None:
    run(example, tmp_path, DAY2, "day2")
    rescan(example, "2026-10-27", 11, "\nThe Council adjourned.")
    third = run(example, tmp_path, DAY3, "day3")
    assert third.plan == {"new": 0, "changed": 1, "unchanged": 1, "missing": 0}
    assert (third.pages_read, third.readings_reused) == (1, PAGES_1970 - 1)
    assert (third.status, third.release) == ("published", "2026-10-27.1")


def test_a_new_gazetteer_rebuilds_without_reading_again(example: Path, tmp_path: Path) -> None:
    run(example, tmp_path, DAY2, "day2")
    with (example / "gazetteer.csv").open("a", encoding="utf-8") as rows:
        rows.write("street,TEST STREET,49.25,-123.1\n")
    rebuilt = run(example, tmp_path, DAY3, "day3")
    assert rebuilt.plan["changed"] == 2
    assert (rebuilt.pages_read, rebuilt.readings_reused) == (0, PAGES_1970 + PAGES_1974)
    assert rebuilt.status == "published"


def test_a_correction_withdraws_a_record_in_every_later_release(example: Path, tmp_path: Path) -> None:
    run(example, tmp_path, DAY1, "day1")
    target = published_records(tmp_path, "2026-10-19.1")[0]["id"]
    set_rules(
        example, {"rule_id": "c1", "action": "drop", "where": {"id": target}, "reason": "not a decision", "min_rows": 1}
    )
    second = run(example, tmp_path, DAY2, "day2")
    assert (second.status, second.records) == ("published", 32)
    withdrawn = (tmp_path / "store" / "releases" / "2026-10-26.1" / "withdrawn.jsonl").read_text(encoding="utf-8")
    assert json.loads(withdrawn)["id"] == target

    rescan(example, "2026-10-27", 10, "\n")
    third = run(example, tmp_path, DAY3, "day3")
    assert third.status == "published", third.detail
    assert third.gates["corrections_applied"]["passed"]
    assert target not in {r["id"] for r in published_records(tmp_path, "2026-10-27.1")}
    withdrawn_now = (tmp_path / "store" / "releases" / "2026-10-27.1" / "withdrawn.jsonl").read_text(encoding="utf-8")
    assert len(withdrawn_now.splitlines()) == 1  # dropped again from the rebuilt meeting, listed once


def test_a_failed_gate_stops_the_publish(example: Path, tmp_path: Path) -> None:
    run(example, tmp_path, DAY1, "day1")
    quote = str(published_records(tmp_path, "2026-10-19.1")[0]["quote"])
    set_rules(
        example, {"rule_id": "bad", "action": "replace_text", "find": quote[:20], "replace": "Something else entirely"}
    )
    refused = run(example, tmp_path, DAY2, "day2")
    assert refused.status == "refused"
    assert not refused.gates["quote_on_page"]["passed"]
    assert not refused.published
    pointer = rel.current(store(tmp_path))
    assert pointer is not None
    assert pointer.version == "2026-10-19.1"


def test_the_page_budget_carries_work_to_the_next_run(example: Path, tmp_path: Path) -> None:
    config = example / "updates" / "updates.toml"
    config.write_text(config.read_text(encoding="utf-8").replace("max_pages_per_run = 50", "max_pages_per_run = 4"))
    run(example, tmp_path, DAY1, "day1")
    partial = run(example, tmp_path, DAY2, "day2")
    assert (partial.status, partial.pages_read, partial.documents_left) == ("no-change", 4, ["19740219"])
    assert "left for the next run: 19740219" in partial.detail
    rest = run(example, tmp_path, DAY2, "day2-later")
    assert (rest.status, rest.pages_read, rest.readings_reused, rest.records) == ("published", 2, 4, 33)


def test_a_short_listing_fails_the_run_instead_of_dropping_records(example: Path, tmp_path: Path) -> None:
    run(example, tmp_path, DAY2, "day2")
    (example / "updates" / "arrivals.json").write_text("[]", encoding="utf-8")
    broken = run(example, tmp_path, DAY3, "day3")
    assert broken.status == "failed"
    assert "lists 0 documents, the last release had 2" in broken.detail
    assert rel.versions(store(tmp_path)) == ["2026-10-26.1"]


def test_rollback_pauses_publishing_until_resumed(example: Path, tmp_path: Path) -> None:
    run(example, tmp_path, DAY1, "day1")
    run(example, tmp_path, DAY2, "day2")
    now = dt.datetime(2026, 10, 26, 18, 0, tzinfo=dt.UTC)
    pointer = rel.rollback(store(tmp_path), now, "bad dates")
    control.pause(store(tmp_path), "publish", "rolled back", now)
    assert (pointer.version, pointer.previous) == ("2026-10-19.1", "2026-10-26.1")

    rescan(example, "2026-10-27", 11, "\nAdjourned.")
    held = run(example, tmp_path, DAY3, "day3")
    assert held.status == "publish-paused"
    control.resume(store(tmp_path), now)
    resumed = run(example, tmp_path, DAY3, "day3-resumed")
    assert (resumed.status, resumed.release) == ("published", "2026-10-27.1")
    events = [e["event"] for e in rel.history(store(tmp_path))]
    assert events == ["publish", "publish", "rollback", "pause", "resume", "publish"]


def test_a_dry_run_writes_nothing_to_the_store(example: Path, tmp_path: Path) -> None:
    report = run(example, tmp_path, DAY2, "dry", dry_run=True)
    assert (report.status, report.release, report.records) == ("dry-run", "2026-10-26.1", 33)
    assert store(tmp_path).list("") == []


def test_pause_lock_and_schedule_skip_a_run(example: Path, tmp_path: Path) -> None:
    now = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.UTC)
    control.pause(store(tmp_path), "all", "maintenance", now)
    assert run(example, tmp_path, DAY2, "paused").status == "paused"
    control.resume(store(tmp_path), now)

    control.acquire(store(tmp_path), "someone-else", dt.datetime(2026, 10, 26, 13, 0, tzinfo=dt.UTC))
    assert run(example, tmp_path, DAY2, "busy").status == "busy"
    store(tmp_path).delete(control.LOCK)

    assert run(example, tmp_path, DAY2, "first").status == "published"
    assert run(example, tmp_path, DAY2, "too-soon", force=False).status == "not-due"


def test_a_windowed_source_may_list_fewer_documents_than_the_release_holds(example: Path, tmp_path: Path) -> None:
    run(example, tmp_path, DAY2, "day2")
    (example / "updates" / "arrivals.json").write_text("[]", encoding="utf-8")
    later = run(example, tmp_path, DAY3, "day3", windowed=True)
    assert (later.status, later.plan["missing"], later.records) == ("no-change", 2, 33)


def test_records_of_an_unfinished_rescan_are_still_checked_against_their_own_pages(
    example: Path, tmp_path: Path
) -> None:
    config = example / "updates" / "updates.toml"
    config.write_text(
        config.read_text(encoding="utf-8").replace("max_pages_per_run = 50", f"max_pages_per_run = {PAGES_1974}")
    )
    run(example, tmp_path, DAY1, "day1")
    rescan(example, "2026-10-26", 11, "A page scanned again, now showing other text entirely. " * 8, replace=True)
    second = run(example, tmp_path, DAY2, "day2")  # the new meeting takes the whole budget; the re-scan waits
    assert (second.documents_built, second.documents_left) == (["19740219"], ["19700609"])
    assert second.status == "published", second.detail
    third = run(example, tmp_path, DAY2, "day2-later")
    assert (third.documents_built, third.pages_read, third.status) == (["19700609"], 1, "published")
    assert third.rejected > 0  # the recorded answers for page 11 no longer match its text


def test_a_first_run_with_nothing_listed_publishes_nothing(example: Path, tmp_path: Path) -> None:
    report = run(example, tmp_path, dt.date(2026, 10, 18), "early")
    assert (report.status, report.detail) == ("no-change", "nothing to publish yet")
    assert rel.versions(store(tmp_path)) == []
