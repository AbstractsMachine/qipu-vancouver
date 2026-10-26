from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path
from typing import Any

import pytest

from qipu_updates.publish import releases as rel
from qipu_updates.publish.local import LocalStore
from qipu_updates.publish.rclone import RcloneStore, StoreError
from qipu_updates.release.manifest import MANIFEST, Manifest, hash_files

NOW = dt.datetime(2026, 10, 26, 14, 17, tzinfo=dt.UTC)


def release_folder(tmp: Path, version: str) -> tuple[Path, Manifest]:
    folder = tmp / "drafts" / version
    (folder / "records").mkdir(parents=True)
    (folder / "records" / "m1.jsonl").write_text('{"id": "m1:0/1"}\n', encoding="utf-8")
    manifest = Manifest(version, None, NOW.isoformat(), "run", "vancouver", "mirror", "c", "k", "none")
    manifest.gates = {"quote_on_page": {"passed": True}}
    manifest.files = hash_files(folder)
    (folder / MANIFEST).write_text(manifest.to_json(), encoding="utf-8")
    return folder, manifest


def test_the_local_store_reads_writes_lists_and_deletes(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "s")
    store.write("a/b.json", b"1")
    assert store.read("a/b.json") == b"1"
    assert store.read("nope") is None
    assert store.list("a") == ["b.json"]
    assert store.list("nowhere") == []
    store.delete("a/b.json")
    assert store.list("") == []
    with pytest.raises(ValueError, match="outside the store"):
        store.read("../escape")


def test_publish_uploads_then_moves_the_pointer_and_never_overwrites(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "s")
    folder, manifest = release_folder(tmp_path, "2026-10-26.1")
    pointer = rel.publish(store, folder, manifest, NOW, "run-1")
    assert (pointer.version, pointer.previous) == ("2026-10-26.1", None)
    assert rel.current(store) == pointer
    assert rel.versions(store) == ["2026-10-26.1"]
    assert rel.history(store)[0]["event"] == "publish"
    with pytest.raises(rel.PublishError, match="never overwritten"):
        rel.publish(store, folder, manifest, NOW, "run-2")


def test_publish_refuses_to_move_the_pointer_when_files_are_missing(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "s")
    folder, manifest = release_folder(tmp_path, "2026-10-26.1")
    manifest.files["records/lost.jsonl"] = "0" * 64
    with pytest.raises(rel.PublishError, match="1 files missing"):
        rel.publish(store, folder, manifest, NOW, "run")
    assert rel.current(store) is None


def test_rollback_goes_to_the_newest_earlier_release_that_was_published(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "s")
    with pytest.raises(rel.PublishError, match="nothing is published"):
        rel.rollback(store, NOW, "r")
    for version in ("2026-10-19.1", "2026-10-26.1"):
        rel.publish(store, *release_folder(tmp_path, version), NOW, "run")
    orphan, _ = release_folder(tmp_path, "2026-10-25.1")
    store.upload(orphan, "releases/2026-10-25.1")  # uploaded, but the run stopped before publishing it

    pointer = rel.rollback(store, NOW, "wrong dates")
    assert (pointer.version, pointer.previous) == ("2026-10-19.1", "2026-10-26.1")
    assert rel.history(store)[-1] == {
        "event": "rollback",
        "version": "2026-10-19.1",
        "from": "2026-10-26.1",
        "at": NOW.isoformat(),
        "reason": "wrong dates",
    }
    with pytest.raises(rel.PublishError, match="no earlier release"):
        rel.rollback(store, NOW, "again")
    with pytest.raises(rel.PublishError, match="never published"):
        rel.rollback(store, NOW, "r", to="2026-10-25.1")
    assert rel.rollback(store, NOW, "forward again", to="2026-10-26.1").version == "2026-10-26.1"


def test_versions_sort_by_day_then_number() -> None:
    assert sorted(["2026-10-26.10", "2026-10-26.9", "2026-10-25.3"], key=rel.version_key) == [
        "2026-10-25.3",
        "2026-10-26.9",
        "2026-10-26.10",
    ]


class FakeRclone:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append(args)
        out = {"cat": b"data", "lsf": b"a.json\nb/c.json\n"}.get(args[1], b"")
        code = 3 if "missing" in args[-1] else 1 if "broken" in args[-1] else 0
        return subprocess.CompletedProcess(args, code, out, b"network down")


def test_the_rclone_store_speaks_rclone(tmp_path: Path) -> None:
    fake = FakeRclone()
    store = RcloneStore("r2:bucket/van/", runner=fake)
    assert store.read("latest.json") == b"data"
    assert store.read("missing.json") is None
    store.write("latest.json", b"{}")
    store.delete("control/lock.json")
    store.upload(tmp_path, "releases/v1")
    assert store.list("releases") == ["a.json", "b/c.json"]
    assert store.list("missing") == []
    store.delete("missing.json")
    with pytest.raises(StoreError, match="network down"):
        store.read("broken.json")
    assert [c[1] for c in fake.calls][:7] == ["cat", "cat", "rcat", "deletefile", "copy", "lsf", "lsf"]
    assert fake.calls[4][2:4] == [str(tmp_path), "r2:bucket/van/releases/v1"]
    assert "--checksum" in fake.calls[4]
