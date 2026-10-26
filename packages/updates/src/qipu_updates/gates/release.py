"""Gates on the release as a whole: it did not shrink by half, no file is empty or zero-filled, every correction applied.

The first two come from the daily agenda publish: a broken listing must not empty the site, and a disk that drops mid-write
leaves files of zero bytes that look fine to everything but a byte check.
"""

from __future__ import annotations

from pathlib import Path

from qipu_updates.gates import Finding, GateResult

TEXT_SUFFIXES = (".json", ".jsonl", ".geojson", ".html", ".csv")


def shrink(records_now: int, records_before: int | None, limit: int = 0) -> GateResult:
    result = GateResult("no_shrink", checked=1, limit=limit)
    if records_before and records_now < records_before / 2:
        result.findings.append(Finding("release", f"records fell from {records_before} to {records_now}"))
    return result


def zero_filled(path: Path) -> bool:
    data = path.read_bytes()
    return not data or not data.strip(b"\0") or (path.suffix in TEXT_SUFFIXES and b"\0" * 16 in data)


def files(folder: Path, limit: int = 0) -> GateResult:
    result = GateResult("files_intact", limit=limit)
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        result.checked += 1
        if zero_filled(path):
            result.findings.append(Finding(path.relative_to(folder).as_posix(), "empty or zero-filled file"))
    return result


def corrections(problems: list[str], applied: int, limit: int = 0) -> GateResult:
    result = GateResult("corrections_applied", checked=applied, limit=limit)
    result.findings = [Finding(p.split(":", 1)[0], p.split(":", 1)[1].strip()) for p in problems]
    return result
