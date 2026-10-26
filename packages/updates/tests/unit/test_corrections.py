from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from qipu_updates.release import corrections as corr
from tests.conftest import record


def records() -> list[dict[str, Any]]:
    return [
        record("m1:0/1", summary="Grandvlew park lease"),
        record("m1:0/2", summary="Grandvlew school"),
        record("m2:3/1", summary="Kitsilano pool"),
    ]


def rule(**row: Any) -> corr.Rule:
    return corr.Rule.from_row({"rule_id": "r", "reason": "why", **row})


def test_drop_withdraws_the_matching_record_with_its_reason() -> None:
    out = corr.apply(records(), [rule(action="drop", where={"source.item": "m2"})], set(), "v1")
    assert [r["id"] for r in out.records] == ["m1:0/1", "m1:0/2"]
    assert out.withdrawn == [{"id": "m2:3/1", "rule_id": "r", "reason": "why", "release": "v1"}]
    assert out.applied[0].matched == 1 and not out.problems


def test_replace_text_fixes_only_the_named_fields_of_the_records_it_selects() -> None:
    fix = rule(action="replace_text", find="Grandvlew", replace="Grandview", fields=["summary"], max_rows=5)
    out = corr.apply(records(), [fix], set(), "v1")
    assert [r["summary"] for r in out.records][:2] == ["Grandview park lease", "Grandview school"]
    assert out.applied[0].matched == 2


def test_a_rule_matching_more_than_max_rows_changes_nothing_and_is_a_problem() -> None:
    out = corr.apply(records(), [rule(action="drop", where={"city": "vancouver"}, max_rows=2)], set(), "v1")
    assert len(out.records) == 3 and not out.withdrawn
    assert out.problems == ["r: matches 3 records, more than max_rows 2: not applied"]


def test_a_rule_matching_too_few_is_stale_unless_an_earlier_release_applied_it() -> None:
    gone = rule(action="drop", where={"id": "nope"}, min_rows=1)
    assert corr.apply(records(), [gone], set(), "v1").problems == ["r: matches 0 records, fewer than min_rows 1: stale"]
    assert corr.apply(records(), [gone], {"r"}, "v2").problems == []


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ({"action": "delete"}, "action must be"),
        ({"action": "drop"}, "needs 'where'"),
        ({"action": "replace_text"}, "needs 'find'"),
    ],
)
def test_malformed_rules_are_refused(row: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        corr.Rule.from_row({"rule_id": "r", **row})


def test_rules_load_from_jsonl_and_the_file_has_a_digest(tmp_path: Path) -> None:
    path = tmp_path / "corrections.jsonl"
    path.write_text('{"rule_id": "a", "action": "drop", "where": {"id": "x"}}\n\n', encoding="utf-8")
    assert [r.rule_id for r in corr.load(path)] == ["a"]
    assert corr.load(None) == [] and corr.load(tmp_path / "missing.jsonl") == []
    assert len(corr.digest(path)) == 64 and corr.digest(None) == "none"
