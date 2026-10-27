"""When a run may go ahead: not paused, not already running, and due.

The schedule itself is the CI's (a cron in .github/workflows/updates.yml); this module holds what the cron cannot know.

Pause has two levels: "publish" keeps building and checking but publishes nothing, "all" skips runs. A rollback pauses
publishing, so the next scheduled run does not publish the same content again before someone looks.

The lock is a marker in the store with an expiry, shared by runs and rollbacks: a rollback takes it too, and is refused
while a run holds it. GitHub's concurrency group is what keeps two scheduled runs apart; the lock also stops a run or a
rollback started by hand from another machine. It is not atomic on object stores, so the publish also checks, just
before moving latest.json, that its run still holds the lock, that nothing is paused, and that latest.json is where the
run found it (publish/releases.py).

A source checked less often than the cron runs (a weekly collection on a daily cron) is skipped until it is due.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass

from qipu_updates.publish import Store, releases
from qipu_updates.publish.releases import record_event

PAUSE = releases.PAUSE
LOCK = releases.LOCK

LAST_CHECK = "control/last_check.json"
SCOPES = ("publish", "all")
SLACK = dt.timedelta(minutes=30)
"""A daily cron that starts a little early is still on time."""


class BusyError(RuntimeError):
    """Another run holds the lock."""


@dataclass(frozen=True)
class Pause:
    """A pause marker: its scope ("publish" or "all"), the reason, and since when."""

    scope: str
    reason: str
    since: str


def paused(store: Store) -> Pause | None:
    data = store.read(PAUSE)
    return Pause(**json.loads(data)) if data else None


def pause(store: Store, scope: str, reason: str, now: dt.datetime) -> Pause:
    """Write a pause marker and record it in the history."""
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}")
    marker = Pause(scope, reason, now.isoformat())
    store.write(PAUSE, json.dumps(asdict(marker)).encode("utf-8"))
    record_event(store, {"event": "pause", "scope": scope, "reason": reason, "at": now.isoformat()})
    return marker


def resume(store: Store, now: dt.datetime) -> None:
    """Remove the pause marker and record it in the history."""
    store.delete(PAUSE)
    record_event(store, {"event": "resume", "at": now.isoformat()})


def acquire(store: Store, run_id: str, now: dt.datetime, ttl: dt.timedelta = dt.timedelta(hours=3)) -> None:
    """Take the run lock for `ttl`, or raise BusyError when another run holds it."""
    data = store.read(LOCK)
    if data:
        held = json.loads(data)
        if held["run_id"] != run_id and dt.datetime.fromisoformat(held["until"]) > now:
            raise BusyError(f"run {held['run_id']} holds the lock until {held['until']}")
    lock = {"run_id": run_id, "since": now.isoformat(), "until": (now + ttl).isoformat()}
    store.write(LOCK, json.dumps(lock).encode("utf-8"))


@contextmanager
def locked(store: Store, holder: str, now: dt.datetime) -> Iterator[None]:
    """Hold the lock for the block (re-entrant for its holder); raises BusyError when someone else holds it."""
    already = lock_holder_is(store, holder)
    acquire(store, holder, now)
    try:
        yield
    finally:
        if not already:
            unlock(store, holder)


def lock_holder_is(store: Store, holder: str) -> bool:
    data = store.read(LOCK)
    return data is not None and json.loads(data)["run_id"] == holder


def unlock(store: Store, run_id: str) -> None:
    """Release the lock if this run holds it."""
    data = store.read(LOCK)
    if data and json.loads(data)["run_id"] == run_id:
        store.delete(LOCK)


def last_check(store: Store) -> dt.datetime | None:
    """When the source was last checked, or None if never."""
    data = store.read(LAST_CHECK)
    return dt.datetime.fromisoformat(json.loads(data)["at"]) if data else None


def mark_checked(store: Store, now: dt.datetime) -> None:
    store.write(LAST_CHECK, json.dumps({"at": now.isoformat()}).encode("utf-8"))


def due(last: dt.datetime | None, every: dt.timedelta, now: dt.datetime) -> bool:
    """True when the source is due: never checked, or the interval has passed (less slack for an early cron)."""
    return last is None or now - last >= every - SLACK
