from __future__ import annotations

import datetime as dt
from pathlib import Path

from qipu_records.verify.privacy import WITHHELD
from qipu_updates.gates import dates, integrity, outcomes, privacy, quotes
from qipu_updates.release.corrections import Applied
from tests.conftest import Pages, record

PAGE = (
    "A Regular meeting of the Council of the City of Vancouver was held on Tuesday, February 19, 1974. "
    "MOVED by Ald. Rankin that the claim of Mrs. Ada Brown for damages to her car be paid in the amount of $120."
)
QUOTE = "the claim of Mrs. Ada Brown for damages to her car be paid"
MASKED = f"the claim of {WITHHELD} for damages to her car be paid"
AS_OF = dt.date(2026, 10, 26)


def test_pieces_of_a_masked_quote_are_the_runs_between_masks() -> None:
    assert quotes.pieces(MASKED) == ["the claim of", "for damages to her car be paid"]
    assert quotes.pieces("  ") == []


def test_the_quote_must_be_on_its_page_or_the_page_before() -> None:
    pages = Pages({"m1:0": PAGE, "m1:1": "Next page."})
    result = quotes.check(
        [
            record("m1:0/1", quote=MASKED),
            record("m1:1/1", quote=QUOTE),
            record("m1:0/2", quote="the Council granted a licence to the Orpheum"),
            record("m1:0/3", quote=""),
            record("m9:0/1", quote=QUOTE),
        ],
        pages,
    )
    assert (result.checked, result.skipped) == (4, 1)
    assert [f.record_id for f in result.findings] == ["m1:0/2", "m1:0/3"]
    assert not result.passed and result.to_dict()["findings"] == 2


def test_the_date_is_the_one_the_page_prints() -> None:
    pages = Pages({"m1:0": PAGE}, {"m1": "1974-02-19"})
    good = record("m1:0/1", quote=QUOTE)
    wrong = record("m1:0/2", quote=QUOTE, date="1974-02-12")
    undated = record("m1:0/3", quote=QUOTE, date=None)
    result = dates.check([good, wrong, undated, record("m9:0/1")], pages)
    assert (result.checked, result.skipped) == (3, 1)
    assert [(f.record_id, f.why) for f in result.findings] == [
        ("m1:0/2", "published 1974-02-12, the page gives 1974-02-19"),
        ("m1:0/3", "no date"),
    ]


def test_a_step_is_never_published_as_a_decision() -> None:
    result = outcomes.check(
        [
            record("m:0/1"),
            record("m:0/2", action="passed_first_reading", stage="first reading", outcome="passed"),
            record("m:0/3", kind="by-law", action="referred", stage="referred", outcome="pending", zoning="rezoned"),
            record("m:0/4", kind="resolution", zoning="rezoned"),
        ]
    )
    assert [f.record_id for f in result.findings] == ["m:0/2", "m:0/3"]
    assert "does not follow from action 'passed_first_reading'" in result.findings[0].why


def test_a_private_name_left_in_a_sensitive_record_is_a_leak() -> None:
    pages = Pages({"m1:0": PAGE})
    shown = record("m1:0/1", quote=QUOTE, kind="claim")
    masked = record("m1:0/2", quote=MASKED, kind="claim")
    old = record("m1:0/3", quote=QUOTE, kind="claim", date="1920-01-06")
    result = privacy.leaks([shown, masked, old, record("m9:0/1", quote=QUOTE, kind="claim")], pages, AS_OF, 92)
    assert (result.checked, result.skipped) == (2, 1)
    assert [(f.record_id, f.text) for f in result.findings] == [("m1:0/1", "Mrs. Ada Brown")]


def test_a_mask_where_the_rule_keeps_the_name_is_over_redaction() -> None:
    cases = {
        "ok": record("m:0/1", kind="claim", quote=MASKED),
        "not-sensitive": record("m:0/2", quote=f"lease to {WITHHELD} approved"),
        "open-record": record("m:0/3", kind="claim", date="1920-01-06", quote=MASKED),
        "after-title": record("m:0/4", kind="claim", quote=f"claim for damages moved by Ald. {WITHHELD}"),
        "before-firm": record("m:0/5", kind="claim", quote=f"claim for damages against {WITHHELD} Construction Ltd."),
        "in-source": record("m:0/6", kind="claim", quote=MASKED, mover=WITHHELD),
        "in-a-party": record("m:0/7", quote="lease approved", parties=[{"name": WITHHELD, "role": "lessee"}]),
    }
    result = privacy.over_redaction(list(cases.values()), AS_OF, 92)
    found = {f.record_id: f.why for f in result.findings}
    assert set(found) == {"m:0/2", "m:0/3", "m:0/4", "m:0/5", "m:0/6", "m:0/7"}
    assert found["m:0/4"].startswith("mask right after an official title")
    assert found["m:0/5"].startswith("mask right before a firm")
    assert found["m:0/6"] == "mask in mover"
    assert found["m:0/7"] == "mask in a record that is not a sensitive matter (parties[0])"


def test_release_gates_catch_a_halved_release_a_zero_filled_file_and_a_bad_correction(tmp_path: Path) -> None:
    assert not integrity.shrink(4, 10).passed and integrity.shrink(5, 10).passed and integrity.shrink(0, None).passed
    (tmp_path / "ok.json").write_text("{}", encoding="utf-8")
    (tmp_path / "zero.jsonl").write_bytes(b"\0" * 64)
    (tmp_path / "torn.json").write_bytes(b'{"a": 1' + b"\0" * 32)
    (tmp_path / "empty.geojson").write_bytes(b"")
    result = integrity.files(tmp_path)
    assert sorted(f.record_id for f in result.findings) == ["empty.geojson", "torn.json", "zero.jsonl"]
    gate = integrity.corrections([Applied("c0", 1), Applied("c1", 3, "matches 3 records, more than max_rows 1: not applied")])
    assert (gate.passed, gate.findings[0].record_id) == (False, "c1")
