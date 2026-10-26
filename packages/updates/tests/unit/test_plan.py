from __future__ import annotations

from qipu_updates.incremental.plan import Built, listing_looks_short, make_plan
from qipu_updates.sources import Document


def doc(doc_id: str, fingerprint: str = "f1") -> Document:
    return Document(doc_id, None, fingerprint, f"https://archive.org/details/{doc_id}")


def test_documents_are_new_changed_unchanged_or_missing() -> None:
    previous = {"a": Built("f1", "k1"), "b": Built("f1", "k1"), "gone": Built("f1", "k1")}
    plan = make_plan([doc("a"), doc("b", "f2"), doc("c")], previous, "k1")
    assert [d.doc_id for d in plan.new] == ["c"]
    assert [d.doc_id for d in plan.changed] == ["b"]
    assert [d.doc_id for d in plan.unchanged] == ["a"]
    assert plan.missing == ("gone",)
    assert [d.doc_id for d in plan.work] == ["c", "b"]
    assert plan.counts() == {"new": 1, "changed": 1, "unchanged": 1, "missing": 1}


def test_a_new_build_key_makes_every_document_changed() -> None:
    plan = make_plan([doc("a"), doc("b")], {"a": Built("f1", "old"), "b": Built("f1", "old")}, "new")
    assert len(plan.changed) == 2 and not plan.unchanged


def test_a_listing_with_less_than_half_the_known_documents_looks_short() -> None:
    assert listing_looks_short(4, 10)
    assert not listing_looks_short(5, 10)
    assert not listing_looks_short(0, 0)
