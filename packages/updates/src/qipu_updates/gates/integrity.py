"""Gates on the release as a whole: it did not shrink by half, no file is empty or zero-filled, every correction
applied.

A broken listing must not empty the published data, and a disk that drops mid-write leaves files of zero bytes that look
fine to everything but a byte check.
"""

from __future__ import annotations

from pathlib import Path

from qipu_updates.gates import Finding, GateResult
from qipu_updates.release.corrections import Applied

TEXT_SUFFIXES = (".json", ".jsonl", ".geojson", ".html", ".csv")


def shrink(records_now: int, records_before: int | None, limit: int = 0) -> GateResult:
    """Fail when the release has fewer than half the records of the one before: a broken listing, not a real drop."""
    result = GateResult("no_shrink", checked=1, limit=limit)
    if records_before and records_now < records_before / 2:
        result.findings.append(Finding("release", f"records fell from {records_before} to {records_now}"))
    return result


def zero_filled(path: Path) -> bool:
    """True for a file that is empty, all zero bytes, or a text file with a run of zero bytes in it."""
    data = path.read_bytes()
    return not data or not data.strip(b"\0") or (path.suffix in TEXT_SUFFIXES and b"\0" * 16 in data)


def files(folder: Path, limit: int = 0) -> GateResult:
    """Fail every empty or zero-filled file in the release folder."""
    result = GateResult("files_intact", limit=limit)
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        result.checked += 1
        if zero_filled(path):
            result.findings.append(Finding(path.relative_to(folder).as_posix(), "empty or zero-filled file"))
    return result


def corrections(applied: list[Applied], limit: int = 0) -> GateResult:
    """Fail every correction rule that did not apply cleanly (too many matches, or stale)."""
    result = GateResult("corrections_applied", checked=len(applied), limit=limit)
    result.findings = [Finding(a.rule_id, a.problem) for a in applied if a.problem]
    return result
