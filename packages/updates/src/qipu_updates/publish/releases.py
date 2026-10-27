"""Publish a release, see what is published, and roll back.

A publish uploads the release folder, checks that every file the manifest lists arrived, then moves latest.json to it. A
rollback moves latest.json back to an earlier release; nothing is deleted, so a rollback can itself be undone the same
way.

Runs, publishes and rollbacks share one lock (control/lock.json), and both a publish and a rollback refuse unless the
caller holds it. The pause marker (control/pause.json) is authoritative: a publish refuses while it is there, checked
just before latest.json moves, and also refuses when latest.json no longer points at the release it was built on (a
rollback came in since the run started). So a rollback can never be published over by a run already in flight.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from qipu_updates.publish import Store
from qipu_updates.release.manifest import MANIFEST, Manifest

POINTER = "latest.json"
PAUSE = "control/pause.json"
LOCK = "control/lock.json"
HISTORY = "history.jsonl"
RELEASES = "releases"


class PublishError(RuntimeError):
    """A publish or rollback could not be done, and nothing was moved."""


@dataclass(frozen=True)
class Pointer:
    """What latest.json says: the published version, the hash of its manifest, when, and the version before."""

    version: str
    manifest_sha256: str
    published: str
    previous: str | None


def version_key(version: str) -> tuple[str, int]:
    """A sort key for versions such as "2026-10-26.2": by day, then by the number after the dot."""
    day, _, n = version.rpartition(".")
    return (day, int(n)) if n.isdigit() else (version, 0)


def current(store: Store) -> Pointer | None:
    """The published pointer, or None before the first publish."""
    data = store.read(POINTER)
    return Pointer(**json.loads(data)) if data else None


def manifest(store: Store, version: str) -> Manifest | None:
    """The manifest of a release in the store, or None when it is not there."""
    data = store.read(f"{RELEASES}/{version}/{MANIFEST}")
    return Manifest.from_json(data.decode("utf-8")) if data else None


def versions(store: Store) -> list[str]:
    """Release folders in the store, published or not, oldest first."""
    return sorted(store.folders(RELEASES), key=version_key)


def history(store: Store) -> list[dict[str, Any]]:
    data = store.read(HISTORY) or b""
    return [json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]


def record_event(store: Store, event: dict[str, Any]) -> None:
    """Append one line to history.jsonl (read and rewrite: object stores have no append; runs hold the lock)."""
    old = store.read(HISTORY) or b""
    store.write(HISTORY, old + (json.dumps(event, sort_keys=True) + "\n").encode("utf-8"))


def lock_holder(store: Store) -> str | None:
    """The run id that holds the lock, or None."""
    data = store.read(LOCK)
    return str(json.loads(data)["run_id"]) if data else None


def _require_lock(store: Store, holder: str, what: str) -> None:
    held = lock_holder(store)
    if held != holder:
        raise PublishError(
            f"{what} needs the run lock, held by {held or 'no one'}, not {holder}; latest.json not moved"
        )


def _move_pointer(store: Store, version: str, now: dt.datetime) -> Pointer:
    data = store.read(f"{RELEASES}/{version}/{MANIFEST}")
    if data is None:
        raise PublishError(f"release {version} is not in the store")
    before = current(store)
    pointer = Pointer(version, hashlib.sha256(data).hexdigest(), now.isoformat(), before.version if before else None)
    store.write(POINTER, (json.dumps(asdict(pointer), indent=1) + "\n").encode("utf-8"))
    return pointer


def _may_publish(store: Store, release: Manifest, run_id: str) -> None:
    """Refuse unless `run_id` holds the lock, nothing is paused, and latest.json is still the release's parent."""
    _require_lock(store, run_id, f"publishing {release.version}")
    if store.read(PAUSE) is not None:
        raise PublishError(f"publishing is paused; {release.version} not published, latest.json not moved")
    here = current(store)
    if (here.version if here else None) != release.parent:
        now_at = here.version if here else "nothing"
        raise PublishError(
            f"latest.json moved to {now_at} since {release.version} was built on {release.parent}; "
            "not published over it"
        )


def publish(store: Store, folder: Path, release: Manifest, now: dt.datetime, run_id: str) -> Pointer:
    """Upload a release folder, check that every file arrived, then move latest.json to it. Raises PublishError if the
    version exists or files are missing."""
    prefix = f"{RELEASES}/{release.version}"
    if store.read(f"{prefix}/{MANIFEST}") is not None:
        raise PublishError(f"release {release.version} already exists; releases are never overwritten")
    _may_publish(store, release, run_id)
    store.upload(folder, prefix)
    arrived = set(store.list(prefix))
    missing = sorted((set(release.files) | {MANIFEST}) - arrived)
    if missing:
        raise PublishError(f"{len(missing)} files missing after upload, e.g. {missing[:3]}; latest.json not moved")
    _may_publish(store, release, run_id)  # again: a rollback or pause may have come in during the upload
    pointer = _move_pointer(store, release.version, now)
    event = {
        "event": "publish",
        "version": release.version,
        "previous": pointer.previous,
        "at": now.isoformat(),
        "run_id": run_id,
    }
    record_event(store, event)
    return pointer


def gates_passed(release: Manifest) -> bool:
    """True when the release recorded gates and every one passed."""
    return bool(release.gates) and all(g.get("passed") for g in release.gates.values())


def rollback(store: Store, now: dt.datetime, reason: str, to: str | None = None, *, holder: str) -> Pointer:
    """Point latest.json at `to`, or at the newest earlier release that was published. `holder` must hold the lock.

    Only releases that were once published qualify: a folder whose upload was cut short is in the store but never was.
    """
    _require_lock(store, holder, "a rollback")
    here = current(store)
    if here is None:
        raise PublishError("nothing is published")
    published = {e["version"] for e in history(store) if e["event"] == "publish"}
    if to is None:
        older = sorted((v for v in published if version_key(v) < version_key(here.version)), key=version_key)
        if not older:
            raise PublishError(f"no earlier release to roll back to from {here.version}")
        to = older[-1]
    target = manifest(store, to)
    if to not in published or target is None or not gates_passed(target):
        raise PublishError(f"release {to} was never published or did not pass its gates")
    pointer = _move_pointer(store, to, now)
    record_event(
        store, {"event": "rollback", "version": to, "from": here.version, "at": now.isoformat(), "reason": reason}
    )
    return pointer
