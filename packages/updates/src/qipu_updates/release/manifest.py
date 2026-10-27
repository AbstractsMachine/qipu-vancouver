"""A release: an immutable folder of records with a manifest saying where every one came from.

    manifest.json           version, parent, run, extractor, prompt, model, config, per-document fingerprints, file
    hashes,
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
    """What a release knows about one document: its fingerprint, build key, file and record count."""

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
    """The manifest of a release: where it came from, its documents, file hashes, corrections and gate results."""

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
        """The manifest as JSON text."""
        return json.dumps(asdict(self), indent=1, sort_keys=True, ensure_ascii=False) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Manifest:
        """A manifest read back from its JSON text."""
        data = json.loads(text)
        data["documents"] = {k: DocEntry(**v) for k, v in data.get("documents", {}).items()}
        return cls(**data)

    def applied_rules(self) -> set[str]:
        """The ids of the correction rules that applied without a problem."""
        return {str(c["rule_id"]) for c in self.corrections if not c.get("problem")}


def next_version(existing: list[str], day: dt.date) -> str:
    """The next version for the day: "2026-10-26.1", then .2 and so on, after those in `existing`."""
    prefix = day.isoformat() + "."
    used = [int(v[len(prefix) :]) for v in existing if v.startswith(prefix) and v[len(prefix) :].isdigit()]
    return f"{prefix}{max(used, default=0) + 1}"


def sha256_file(path: Path) -> str:
    """The sha256 of a file, read in blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_files(folder: Path) -> dict[str, str]:
    """sha256 of every file in the release folder except the manifest itself."""
    return {
        p.relative_to(folder).as_posix(): sha256_file(p)
        for p in sorted(folder.rglob("*"))
        if p.is_file() and p.name != MANIFEST
    }
