"""A store on any rclone remote ("r2:qipu-data", "s3:bucket/prefix"). The remote is configured by rclone's own environment
variables (RCLONE_CONFIG_<NAME>_TYPE, ..._ACCESS_KEY_ID, ...), so no credential passes through this code.

Uploads use --checksum, so a re-run after an interrupted publish sends only what is missing.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


class RcloneStore:
    def __init__(self, remote: str, runner: Runner = subprocess.run) -> None:
        self.remote = remote.rstrip("/")
        self._run = runner

    def _rclone(self, args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        return self._run(["rclone", *args], capture_output=True, **kwargs)

    def _url(self, key: str) -> str:
        return f"{self.remote}/{key.lstrip('/')}"

    def read(self, key: str) -> bytes | None:
        done = self._rclone(["cat", self._url(key)])
        return done.stdout if done.returncode == 0 else None

    def write(self, key: str, data: bytes) -> None:
        self._rclone(["rcat", self._url(key)], input=data, check=True)

    def delete(self, key: str) -> None:
        self._rclone(["deletefile", self._url(key)])

    def upload(self, folder: Path, prefix: str) -> None:
        self._rclone(["copy", str(folder), self._url(prefix), "--checksum", "--transfers", "16"], check=True)

    def list(self, prefix: str) -> list[str]:
        done = self._rclone(["lsf", "-R", "--files-only", self._url(prefix)])
        if done.returncode != 0:
            return []
        return sorted(line for line in done.stdout.decode("utf-8").splitlines() if line)
