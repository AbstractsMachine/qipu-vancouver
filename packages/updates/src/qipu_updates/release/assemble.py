"""Put a release folder together from the documents built in this run and the ones carried over from the last release.

Every record built in this run gets a provenance block: the run, the document's address and fingerprint, and the sha256 of
the page text it was read from. With the record's own `reading` (model, prompt version) and `source` (item, page, viewer
link), each published fact can be traced to one page of one scan, one prompt and one run.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from qipu_records.collection import write_json, write_jsonl
from qipu_records.export.geojson import feature_collection
from qipu_records.export.records import DecisionRecord
from qipu_updates.incremental.workspace import safe_name
from qipu_updates.release import corrections
from qipu_updates.release.manifest import MANIFEST, DocEntry, Manifest, hash_files
from qipu_updates.sources import Document

ReadPrevious = Callable[[str], bytes]


@dataclass
class Draft:
    folder: Path
    manifest: Manifest
    records: list[dict[str, Any]]
    problems: list[str]
    """Corrections that could not be applied cleanly; the release gate fails on any."""

    def write_manifest(self) -> None:
        self.manifest.files = hash_files(self.folder)
        (self.folder / MANIFEST).write_text(self.manifest.to_json(), encoding="utf-8")


def stamp(records: Iterable[dict[str, Any]], doc: Document, run_id: str, page_hashes: dict[str, str]) -> None:
    for record in records:
        page_id = str(record["id"]).rsplit("/", 1)[0]
        record["provenance"] = {
            "run_id": run_id,
            "document": doc.url,
            "fingerprint": doc.fingerprint,
            "page_sha256": page_hashes.get(page_id),
        }


def _jsonl(data: bytes) -> list[dict[str, Any]]:
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def assemble(
    folder: Path,
    manifest: Manifest,
    *,
    built: dict[str, tuple[Document, list[dict[str, Any]]]],
    previous: Manifest | None,
    read_previous: ReadPrevious,
    rules: list[corrections.Rule],
) -> Draft:
    """Write records/, decisions.*, withdrawn.jsonl into `folder`; `manifest` comes in with its header filled."""
    folder.mkdir(parents=True, exist_ok=True)
    documents: dict[str, DocEntry] = {}
    everything: list[dict[str, Any]] = []
    for doc_id, (doc, records) in built.items():
        documents[doc_id] = DocEntry(doc.fingerprint, manifest.build_key, doc.date, doc.url, "", 0, manifest.run_id)
        everything += records
    for doc_id, entry in (previous.documents if previous else {}).items():
        if doc_id not in built:
            documents[doc_id] = entry
            everything += _jsonl(read_previous(entry.file)) if entry.file else []

    applied_before = previous.applied_rules() if previous else set()
    fixed = corrections.apply(everything, rules, applied_before, manifest.version)
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in fixed.records:
        by_doc[str(record["source"]["item"])].append(record)

    for doc_id, entry in sorted(documents.items()):
        records = sorted(by_doc.get(doc_id, []), key=lambda r: str(r["id"]))
        name = f"records/{safe_name(doc_id)}.jsonl" if records else ""
        if records:
            (folder / "records").mkdir(exist_ok=True)
            write_jsonl(folder / name, records)
        documents[doc_id] = DocEntry(entry.fingerprint, entry.build_key, entry.date, entry.url, name, len(records), entry.run_id)

    published = sorted(fixed.records, key=lambda r: str(r["id"]))
    write_jsonl(folder / "decisions.jsonl", published)
    write_json(folder / "decisions.geojson", feature_collection(cast(list[DecisionRecord], published)))
    withdrawn = _jsonl(read_previous("withdrawn.jsonl")) if previous and "withdrawn.jsonl" in previous.files else []
    withdrawn += fixed.withdrawn
    if withdrawn:
        write_jsonl(folder / "withdrawn.jsonl", withdrawn)

    manifest.documents = dict(sorted(documents.items()))
    manifest.counts = {"documents": len(documents), "records": len(published), "withdrawn": len(withdrawn)}
    manifest.corrections = [{"rule_id": a.rule_id, "matched": a.matched, "problem": a.problem} for a in fixed.applied]
    return Draft(folder, manifest, published, fixed.problems)
