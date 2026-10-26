"""Where releases are published: a store of files addressed by key ("releases/2026-10-26.1/decisions.jsonl").

Two stores: a local folder (the demo, CI, and a mirror served by any web server), and any rclone remote (S3, R2, GCS, ...).
The layout in a store:

    latest.json                  the published version: {"version", "manifest_sha256", "published", "previous"}
    history.jsonl                every publish, rollback, pause and resume, one line each
    releases/<version>/...       one immutable folder per release (see qipu_updates.release.manifest)
    runs/<run id>.json           what each run did (qipu_updates.monitor.metrics)
    control/...                  pause and lock markers (qipu_updates.schedule.control)

Readers follow latest.json, so a publish or a rollback is one small write after the release folder is complete.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Store(Protocol):
    def read(self, key: str) -> bytes | None: ...

    def write(self, key: str, data: bytes) -> None: ...

    def delete(self, key: str) -> None: ...

    def upload(self, folder: Path, prefix: str) -> None: ...

    def folders(self, prefix: str) -> list[str]:
        """Names of the folders directly under `prefix`."""
        ...

    def list(self, prefix: str) -> list[str]:
        """Keys under `prefix`, relative to it."""
        ...
