"""OCR pages and readings in, checked records and map data out, on the bundled sample."""

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest

from qipu_records.cities import VANCOUVER
from qipu_records.collection import Collection
from qipu_records.export.records import Context
from qipu_records.map.gazetteer import Gazetteer
from qipu_records.pipeline import build
from qipu_records.verify.privacy import Embargo
from tests.conftest import SAMPLE


def _context() -> Context:
    return Context(VANCOUVER, Embargo(VANCOUVER.embargo_years), Gazetteer.load(SAMPLE / "gazetteer.csv"))


def _records(folder: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (folder / "decisions.jsonl").read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def built(sample_copy: Path) -> Path:
    shutil.copy(SAMPLE / "readings.jsonl", sample_copy / "readings.jsonl")
    build(_context(), Collection(sample_copy))
    return sample_copy


def test_every_decision_is_quoted_dated_and_linked(built: Path) -> None:
    records = _records(built)
    assert len(records) == 32
    for record in records:
        assert record["quote_check"] in ("exact", "fuzzy")
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", record["date"])
        assert (
            record["source"]["page_url"]
            == f"https://archive.org/details/{record['source']['item']}/page/n{record['source']['ocr_page']}"
        )


def test_dates_come_from_the_meeting_headers(built: Path) -> None:
    dates = {(r["source"]["item"], r["date"], r["date_source"]) for r in _records(built)}
    assert dates == {
        ("19700609", "1970-06-09", "running head"),
        ("19740219", "1974-02-19", "running head"),
        ("19740219", "1974-02-19", "meeting opens on the page"),
    }


def test_outcomes_on_the_sample(built: Path) -> None:
    records = {r["id"]: r for r in _records(built)}
    booth = next(r for r in records.values() if "Playhouse" in r["summary"])
    assert (booth["action"], booth["outcome"]) == ("failed", "refused")
    assert records["19700609:12/1"]["outcome"] == "pending"
    assert records["19740219:4/6"]["outcome"] == "passed"


def test_the_private_claim_stays_withheld(built: Path) -> None:
    claim = next(r for r in _records(built) if r["id"] == "19700609:12/1")
    assert claim["names_withheld"] is True
    assert claim["parties"] == [{"name": "[name withheld]", "role": "claimant"}]
    assert claim["places"] == [{"text": "3891 Arbutus Street", "precision": "address"}]


def test_map_data_matches_the_records(built: Path) -> None:
    layer = json.loads((built / "decisions.geojson").read_text(encoding="utf-8"))
    placed = {f["properties"]["place"] for f in layer["features"]}
    assert {"1139 Pendrell Street", "Alberni and Bidwell Streets", "#680 East 5th Avenue", "Strathcona"} <= placed
    ids = {r["id"] for r in _records(built)}
    for feature in layer["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        assert 49.19 < lat < 49.32
        assert -123.23 < lon < -123.02
        assert feature["properties"]["id"] in ids


def test_summary_counts_each_check(built: Path) -> None:
    summary = json.loads((built / "summary.json").read_text(encoding="utf-8"))
    assert summary == {
        "pages": 9, "pages_read": 9, "decisions": 32, "rejected": 1, "dated": 32, "linked_to_page": 32, "placed": 9,
        "quote_exact": 31, "quote_fuzzy": 1, "with_names_withheld": 1, "fields_corrected": 2, "fields_in_conflict": 0,
    }  # fmt: skip


def test_an_invented_item_is_rejected_not_published(sample_copy: Path) -> None:
    rows = [json.loads(line) for line in (SAMPLE / "readings.jsonl").read_text(encoding="utf-8").splitlines()]
    invented = dict(
        rows[0]["items"][0], quote="Council approved a monorail along Granville Street", summary="Invented."
    )
    rows[0]["items"].append(invented)
    (sample_copy / "readings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    summary = build(_context(), Collection(sample_copy))
    assert (summary.decisions, summary.rejected) == (32, 2)
    [rejected] = [
        row
        for row in map(json.loads, (sample_copy / "rejected.jsonl").read_text(encoding="utf-8").splitlines())
        if "monorail" in row["quote"]
    ]
    assert rejected["reason"] == "quote not found on the page"
    assert all("monorail" not in r["quote"] for r in _records(sample_copy))


def test_a_heading_on_the_previous_page_is_found_there(sample_copy: Path) -> None:
    rows = [json.loads(line) for line in (SAMPLE / "readings.jsonl").read_text(encoding="utf-8").splitlines()]
    by_page = {r["page_id"]: r for r in rows}
    carried = dict(by_page["19740219:2"]["items"][0], quote="Birks Building (cont'd)", heading_on_prev=True)
    by_page["19740219:2"]["items"] = [carried]
    (sample_copy / "readings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    build(_context(), Collection(sample_copy))
    record = next(r for r in _records(sample_copy) if r["id"] == "19740219:2/1")
    assert record["quote_check"] == "exact"
    assert record["date_source"] == "running head"


def test_a_rejected_item_keeps_the_privacy_rule(sample_copy: Path) -> None:
    rows = [json.loads(line) for line in (SAMPLE / "readings.jsonl").read_text(encoding="utf-8").splitlines()]
    invented = dict(
        rows[0]["items"][0],
        kind="claim",
        quote="Claim of Mrs. Ada Quill for injuries",
        parties=[{"name": "Mrs. Ada Quill", "role": "claimant"}],
    )
    rows[0]["items"].append(invented)
    (sample_copy / "readings.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    build(_context(), Collection(sample_copy))
    rejected = (sample_copy / "rejected.jsonl").read_text(encoding="utf-8")
    assert "Quill" not in rejected
    assert "Claim of [name withheld] for injuries" in rejected


def test_the_model_fields_a_review_found_wrong_are_corrected_or_held_back(built: Path) -> None:
    """Four records a review checked against the archive.org pages (19700609 scan pages 10-11, 19740219 scan page 1)."""
    records = {r["id"]: r for r in _records(built)}
    # The quote glues the "(Cont'd.)" heading of scan page 10 to words printed on scan page 9, which is not in the
    # sample: it cannot be checked on the pages at hand, so the item is not published (its summary also said "2019").
    assert "19700609:10/1" not in records
    rejected = [json.loads(line) for line in (built / "rejected.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in rejected] == ["19700609:10/1"]
    # "THAT no further action be taken on this development permit application ... - CARRIED"
    ymca = records["19700609:10/2"]
    assert (ymca["outcome"], ymca["checks"][0]["was"]) == ("refused", "unknown")
    # "MOVED by Ald. Phillips, in Amendment, ... - LOST"; the main motion was then put and CARRIED.
    iwa = records["19700609:11/2"]
    assert (iwa["outcome"], iwa["amended"]) == ("passed", False)
    assert iwa["checks"] == [
        {"field": "amended", "result": "corrected", "why": "the amendment moved was LOST", "was": True}
    ]
    # "- CARRIED (Alderman Massey voted against the motion)"
    birks = records["19740219:1/1"]
    assert birks["vote"] is not None
    assert birks["vote"]["noes_names"] == ["Massey"]
