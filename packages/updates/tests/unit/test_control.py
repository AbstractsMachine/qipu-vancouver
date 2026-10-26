from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from qipu_updates.publish.local import LocalStore
from qipu_updates.schedule import control

NOW = dt.datetime(2026, 10, 26, 14, 0, tzinfo=dt.UTC)


def test_pause_and_resume_are_markers_and_history_lines(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    assert control.paused(store) is None
    control.pause(store, "publish", "checking a complaint", NOW)
    marker = control.paused(store)
    assert marker is not None and (marker.scope, marker.reason) == ("publish", "checking a complaint")
    control.resume(store, NOW)
    assert control.paused(store) is None
    with pytest.raises(ValueError, match="scope"):
        control.pause(store, "everything", "x", NOW)


def test_the_lock_keeps_out_another_run_until_it_expires(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    control.acquire(store, "a", NOW)
    control.acquire(store, "a", NOW)  # the same run may take it again
    with pytest.raises(control.BusyError, match="run a holds the lock"):
        control.acquire(store, "b", NOW + dt.timedelta(hours=1))
    control.acquire(store, "b", NOW + dt.timedelta(hours=4))  # expired
    control.release(store, "a")  # not a's any more: stays
    assert store.read(control.LOCK) is not None
    control.release(store, "b")
    assert store.read(control.LOCK) is None


def test_a_source_is_due_once_its_interval_has_passed(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    day = dt.timedelta(days=1)
    assert control.last_check(store) is None and control.due(None, day, NOW)
    control.mark_checked(store, NOW)
    assert control.last_check(store) == NOW
    assert not control.due(NOW, day, NOW + dt.timedelta(hours=20))
    assert control.due(NOW, day, NOW + dt.timedelta(hours=23, minutes=40))
