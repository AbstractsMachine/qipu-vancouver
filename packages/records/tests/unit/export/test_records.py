import datetime as dt
from pathlib import Path
from typing import Unpack

import pytest

from qipu_records.cities import VANCOUVER
from qipu_records.collection import Page
from qipu_records.export.geojson import feature_collection
from qipu_records.export.records import Context, DecisionRecord, PageContext, decision_record
from qipu_records.fetch.archive import Item
from qipu_records.map.gazetteer import Gazetteer, Precision, write_gazetteer
from qipu_records.read.readers import Reading
from qipu_records.read.schema import ModelItem
from qipu_records.verify.dates import DateSource, PageDates
from qipu_records.verify.privacy import WITHHELD, Embargo
from qipu_records.verify.quotes import QuoteMatch, QuoteStatus

FIELDS = {
    "id", "city", "body", "date", "date_source", "kind", "number", "file", "action", "stage", "outcome", "amended",
    "zoning", "summary", "quote", "quote_check", "vote", "mover", "seconder", "money", "parties", "places", "topics",
    "names_withheld", "checks", "source", "reading",
}  # fmt: skip

ITEM = Item("19700609", "Council Meeting Minutes : June 9, 1970", "1970-06-09", None, None, "City of Vancouver, B.C.")
PAGE = Page("19700609:12", "19700609", 12, "Regular Council, June 9, 1970\n...")


def _entry(**fields: Unpack[ModelItem]) -> ModelItem:
    entry: ModelItem = {
        "quote": "Booth - City Hall", "kind": "permit", "action": "failed", "number": "", "file": "", "amended": False,
        "ayes": None, "noes": None, "absent": None, "ayes_names": [], "noes_names": [], "absent_names": [],
        "mover": "Bird",
        "seconder": "", "parties": [{"name": "Playhouse Theatre Company", "role": "applicant"}],
        "money": [{"amount": 400, "purpose": "rental", "payee": ""}],
        "places": [{"text": "1139 Pendrell Street", "precision": "address"}],
        "zoning_from": "", "zoning_to": "", "topics": [], "summary": "Council refused the booth.",
    }  # fmt: skip
    return {**entry, **fields}


@pytest.fixture
def context(tmp_path: Path) -> Context:
    path = tmp_path / "gazetteer.csv"
    write_gazetteer(iter([(Precision.ADDRESS, "1139 pendrell st", 49.2819, -123.1309)]), path)
    return Context(VANCOUVER, Embargo(100, today=dt.date(2026, 10, 26)), Gazetteer.load(path))


def _record(context: Context, entry: ModelItem) -> DecisionRecord:
    dates = PageDates(dt.date(1970, 6, 9), DateSource.RUNNING_HEAD)
    page = PageContext(ITEM, PAGE, None, dates, list(range(20)), Reading(PAGE.page_id, [entry], "m", "v"), {"bird"})
    return decision_record(context, page, 3, entry, match=QuoteMatch(QuoteStatus.EXACT, 40, 1.0), on_this_page=True)


def test_record_has_the_documented_fields(context: Context) -> None:
    record = _record(context, _entry())
    assert set(record) == FIELDS
    assert record["id"] == "19700609:12/3"
    assert (record["date"], record["date_source"]) == ("1970-06-09", "running head")
    assert (record["stage"], record["outcome"]) == ("failed", "refused")
    assert record["number"] is None
    assert record["vote"] is None
    assert record["money"] == [{"amount": 400, "currency": "CAD", "purpose": "rental", "payee": None}]
    assert record["source"]["page_url"] == "https://archive.org/details/19700609/page/n12"
    assert record["reading"] == {"model": "m", "prompt_version": "v"}


def test_vote_is_kept_when_a_roll_call_is_printed(context: Context) -> None:
    record = _record(context, _entry(ayes=8, noes=1, ayes_names=["Bird"], noes_names=["Adams"]))
    vote = record["vote"]
    assert vote is not None
    assert vote["ayes"] == 8
    assert vote["noes_names"] == ["Adams"]


def test_sensitive_item_inside_the_embargo_has_names_withheld(context: Context) -> None:
    entry = _entry(kind="claim", quote="Claim of Mrs. Mary Roe", summary="Claim of Mrs. Mary Roe deferred.",
                   parties=[{"name": "Mrs. Mary Roe", "role": "claimant"}])  # fmt: skip
    record = _record(context, entry)
    assert record["names_withheld"] is True
    assert record["parties"] == [{"name": WITHHELD, "role": "claimant"}]
    assert "Roe" not in str(record)


def test_placed_places_become_map_points(context: Context) -> None:
    record = _record(context, _entry())
    assert record["places"][0]["placed_as"] == "address"
    [feature] = feature_collection([record])["features"]
    assert feature["geometry"] == {"type": "Point", "coordinates": [-123.1309, 49.2819]}
    assert feature["properties"]["amounts"] == [400]
    assert feature["properties"]["page_url"] == record["source"]["page_url"]


def test_unplaced_records_are_not_on_the_map(context: Context) -> None:
    record = _record(context, _entry(places=[{"text": "City Hall", "precision": "address"}]))
    assert feature_collection([record])["features"] == []
