"""Decide what a run has to do: compare what the source lists today with what the last release was built from.

A document is new when the last release does not have it, changed when its fingerprint or its build key differs (the
build key names the extractor version, prompt and model, so upgrading any of them rebuilds), and unchanged otherwise. A
document the source no longer lists is kept in the release and reported: a listing that comes back short must never
delete records.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from qipu_updates.sources import Document


@dataclass(frozen=True)
class Built:
    """What the last release knows about a document."""

    fingerprint: str
    build_key: str


@dataclass(frozen=True)
class Plan:
    new: tuple[Document, ...]
    changed: tuple[Document, ...]
    unchanged: tuple[Document, ...]
    missing: tuple[str, ...]
    """In the last release, not in today's listing."""

    @property
    def work(self) -> tuple[Document, ...]:
        return self.new + self.changed

    def counts(self) -> dict[str, int]:
        return {
            "new": len(self.new),
            "changed": len(self.changed),
            "unchanged": len(self.unchanged),
            "missing": len(self.missing),
        }


def make_plan(found: Sequence[Document], previous: Mapping[str, Built], build_key: str) -> Plan:
    new, changed, unchanged = [], [], []
    for doc in found:
        before = previous.get(doc.doc_id)
        if before is None:
            new.append(doc)
        elif before.fingerprint != doc.fingerprint or before.build_key != build_key:
            changed.append(doc)
        else:
            unchanged.append(doc)
    listed = {doc.doc_id for doc in found}
    missing = sorted(doc_id for doc_id in previous if doc_id not in listed)
    return Plan(tuple(new), tuple(changed), tuple(unchanged), tuple(missing))


def listing_looks_short(found: int, known: int) -> bool:
    """True when the source lists fewer than half the documents the last release had: a broken listing, not a purge."""
    return known > 0 and found < known / 2
