"""A release: an immutable folder of records with a manifest saying where every one came from.

    manifest.json           version, parent, run, extractor, prompt, model, config, per-document fingerprints, file hashes,
                            corrections applied, gate results
    records/<doc>.jsonl     the records of one document (one archive.org item, one meeting)
    decisions.jsonl         all records, in the qipu-records format
    decisions.geojson       the records that have a place, for the map
    withdrawn.jsonl         records taken out by a correction, with the rule and reason, kept across releases

Versions are the date of the run and a counter: 2026-10-26.1, 2026-10-26.2, ...
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

MANIFEST = "manifest.json"


@dataclass(frozen=True)
class DocEntry:
    fingerprint: str
    build_key: str
    date: str | None
    url: str
    file: str
    records: int
    run_id: str
    """The run that built this document's records; later releases carry them over unchanged."""


@dataclass
class Manifest:
    version: str
    parent: str | None
    created: str
    run_id: str
    city: str
    source: str
    config_sha256: str
    build_key: str
    corrections_sha256: str
    documents: dict[str, DocEntry] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    corrections: list[dict[str, Any]] = field(default_factory=list)
    gates: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, sort_keys=True, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Manifest:
        data = json.loads(text)
        data["documents"] = {k: DocEntry(**v) for k, v in data.get("documents", {}).items()}
        return cls(**data)

    def applied_rules(self) -> set[str]:
        return {str(c["rule_id"]) for c in self.corrections if not c.get("problem")}


def next_version(existing: list[str], day: dt.date) -> str:
    prefix = day.isoformat() + "."
    used = [int(v[len(prefix) :]) for v in existing if v.startswith(prefix) and v[len(prefix) :].isdigit()]
    return f"{prefix}{max(used, default=0) + 1}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_files(folder: Path) -> dict[str, str]:
    """sha256 of every file in the release folder except the manifest itself."""
    return {
        p.relative_to(folder).as_posix(): sha256_file(p) for p in sorted(folder.rglob("*")) if p.is_file() and p.name != MANIFEST
    }
