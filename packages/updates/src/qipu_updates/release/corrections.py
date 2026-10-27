"""Corrections as data: a fix found by a person is a line in a file, applied to every release from then on.

`corrections.jsonl`, append-only, one rule a line:

    {"rule_id": "c1", "action": "drop", "where": {"id": "19740219:3/2"}, "reason": "...", "author": "...", "at":
    "2026-10-26",
     "evidence": "https://archive.org/details/19740219/page/n5", "min_rows": 1, "max_rows": 1}
    {"rule_id": "c2", "action": "replace_text", "find": "Grandvlew", "replace": "Grandview", "fields": ["summary",
    "quote"]}

`where` matches records whose fields equal the given values (dotted names reach inside: "source.item"). `drop` removes
the records and lists them in withdrawn.jsonl with the rule and reason; `replace_text` replaces a string in the named
fields of the records `where` selects (all records when it is absent).

A rule that matches more than `max_rows` changes nothing and fails the release (a typo in `where` must not drop
thousands). A rule that matches fewer than `min_rows` fails as stale, unless an earlier release already applied it:
published records already carry their corrections, so a rule applied once matches nothing afterwards.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ACTIONS = ("drop", "replace_text")


@dataclass(frozen=True)
class Rule:
    rule_id: str
    action: str
    reason: str
    where: dict[str, Any] = field(default_factory=dict)
    find: str = ""
    replace: str = ""
    fields: tuple[str, ...] = ("summary", "quote")
    min_rows: int = 0
    max_rows: int = 1

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Rule:
        if row.get("action") not in ACTIONS:
            raise ValueError(f"correction {row.get('rule_id')!r}: action must be one of {ACTIONS}")
        if row["action"] == "drop" and not row.get("where"):
            raise ValueError(f"correction {row['rule_id']!r}: a drop needs 'where'")
        if row["action"] == "replace_text" and not row.get("find"):
            raise ValueError(f"correction {row['rule_id']!r}: replace_text needs 'find'")
        return cls(
            rule_id=str(row["rule_id"]),
            action=str(row["action"]),
            reason=str(row.get("reason") or ""),
            where=dict(row.get("where") or {}),
            find=str(row.get("find") or ""),
            replace=str(row.get("replace") or ""),
            fields=tuple(row.get("fields") or ("summary", "quote")),
            min_rows=int(row.get("min_rows", 0)),
            max_rows=int(row.get("max_rows", 1)),
        )


@dataclass(frozen=True)
class Applied:
    """What one correction rule did: how many records it matched, and the problem if it went wrong."""

    rule_id: str
    matched: int
    problem: str | None = None


@dataclass
class Outcome:
    records: list[dict[str, Any]]
    withdrawn: list[dict[str, Any]]
    applied: list[Applied]


def load(path: Path | None) -> list[Rule]:
    if path is None or not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Rule.from_row(json.loads(line)) for line in lines if line.strip()]


def digest(path: Path | None) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path and path.exists() else "none"


def _get(record: dict[str, Any], dotted: str) -> Any:
    value: Any = record
    for part in dotted.split("."):
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _matches(rule: Rule, record: dict[str, Any]) -> bool:
    if rule.action == "replace_text" and not any(rule.find in str(record.get(f) or "") for f in rule.fields):
        return False
    return all(_get(record, key) == value for key, value in rule.where.items())


def apply(records: list[dict[str, Any]], rules: Iterable[Rule], applied_before: set[str], release: str) -> Outcome:
    out = Outcome(list(records), [], [])
    for rule in rules:
        hits = [r for r in out.records if _matches(rule, r)]
        problem = None
        if len(hits) > rule.max_rows:
            problem = f"matches {len(hits)} records, more than max_rows {rule.max_rows}: not applied"
            hits = []
        elif len(hits) < rule.min_rows and rule.rule_id not in applied_before:
            problem = f"matches {len(hits)} records, fewer than min_rows {rule.min_rows}: stale"
        out.applied.append(Applied(rule.rule_id, len(hits), problem))
        if rule.action == "drop" and hits:
            gone = {id(r) for r in hits}
            out.records = [r for r in out.records if id(r) not in gone]
            out.withdrawn += [
                {"id": r["id"], "rule_id": rule.rule_id, "reason": rule.reason, "release": release} for r in hits
            ]
        elif hits:
            for record in hits:
                for name in rule.fields:
                    if isinstance(record.get(name), str):
                        record[name] = record[name].replace(rule.find, rule.replace)
    return out
