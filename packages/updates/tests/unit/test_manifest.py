from __future__ import annotations

import datetime as dt
from pathlib import Path

from qipu_updates.release.manifest import DocEntry, Manifest, hash_files, next_version


def test_versions_count_up_within_a_day() -> None:
    day = dt.date(2026, 10, 26)
    assert next_version([], day) == "2026-10-26.1"
    assert next_version(["2026-10-25.4", "2026-10-26.1", "2026-10-26.9"], day) == "2026-10-26.10"


def test_a_manifest_reads_back_what_it_wrote() -> None:
    manifest = Manifest("v1", None, "now", "run", "vancouver", "mirror", "c", "k", "none")
    manifest.documents = {"m1": DocEntry("f", "k", "1974-02-19", "u", "records/m1.jsonl", 3, "run")}
    manifest.corrections = [
        {"rule_id": "a", "matched": 1, "problem": None},
        {"rule_id": "b", "matched": 9, "problem": "too many"},
    ]
    again = Manifest.from_json(manifest.to_json())
    assert again == manifest
    assert again.applied_rules() == {"a"}


def test_file_hashes_cover_everything_but_the_manifest(tmp_path: Path) -> None:
    (tmp_path / "records").mkdir()
    (tmp_path / "records" / "m1.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    assert list(hash_files(tmp_path)) == ["records/m1.jsonl"]
