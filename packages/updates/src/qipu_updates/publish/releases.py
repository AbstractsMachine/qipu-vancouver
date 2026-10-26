"""Publish a release, see what is published, and roll back.

A publish uploads the release folder, checks that every file the manifest lists arrived, then moves latest.json to it. A
rollback moves latest.json back to an earlier release; nothing is deleted, so a rollback can itself be undone the same way.
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
HISTORY = "history.jsonl"
RELEASES = "releases"


class PublishError(RuntimeError):
    pass


@dataclass(frozen=True)
class Pointer:
    version: str
    manifest_sha256: str
    published: str
    previous: str | None


def version_key(version: str) -> tuple[str, int]:
    day, _, n = version.rpartition(".")
    return (day, int(n)) if n.isdigit() else (version, 0)


def current(store: Store) -> Pointer | None:
    data = store.read(POINTER)
    return Pointer(**json.loads(data)) if data else None


def manifest(store: Store, version: str) -> Manifest | None:
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


def _move_pointer(store: Store, version: str, now: dt.datetime) -> Pointer:
    data = store.read(f"{RELEASES}/{version}/{MANIFEST}")
    if data is None:
        raise PublishError(f"release {version} is not in the store")
    before = current(store)
    pointer = Pointer(version, hashlib.sha256(data).hexdigest(), now.isoformat(), before.version if before else None)
    store.write(POINTER, (json.dumps(asdict(pointer), indent=1) + "\n").encode("utf-8"))
    return pointer


def publish(store: Store, folder: Path, release: Manifest, now: dt.datetime, run_id: str) -> Pointer:
    prefix = f"{RELEASES}/{release.version}"
    if store.read(f"{prefix}/{MANIFEST}") is not None:
        raise PublishError(f"release {release.version} already exists; releases are never overwritten")
    store.upload(folder, prefix)
    arrived = set(store.list(prefix))
    missing = sorted((set(release.files) | {MANIFEST}) - arrived)
    if missing:
        raise PublishError(f"{len(missing)} files missing after upload, e.g. {missing[:3]}; latest.json not moved")
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
    return bool(release.gates) and all(g.get("passed") for g in release.gates.values())


def rollback(store: Store, now: dt.datetime, reason: str, to: str | None = None) -> Pointer:
    """Point latest.json at `to`, or at the newest earlier release that was published.

    Only releases that were once published qualify: a folder whose upload was cut short is in the store but never was.
    """
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
    record_event(store, {"event": "rollback", "version": to, "from": here.version, "at": now.isoformat(), "reason": reason})
    return pointer
