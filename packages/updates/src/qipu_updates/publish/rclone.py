"""A store on any rclone remote ("r2:bucket", "s3:bucket/prefix"). The remote is configured by rclone's own environment
variables (RCLONE_CONFIG_<NAME>_TYPE, ..._ACCESS_KEY_ID, ...), so no credential passes through this code.

Uploads use --checksum, so a re-run after an interrupted publish sends only what is missing.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]


NOT_FOUND = (3, 4)
"""rclone's exit codes for a missing directory and a missing file. Any other failure raises: a network or credential
error must never read as "no pause marker" or "nothing published yet".
"""


TIMEOUT_S = 3600.0
"""A wall-clock limit on one rclone call. rclone retries a dropped connection itself (--retries, --low-level-retries);
this only stops a run that hangs, so the scheduled job fails and alerts instead of holding the runner until GitHub
kills it.
"""


class StoreError(RuntimeError):
    """rclone failed for a reason other than a missing file."""


class RcloneStore:
    """A store on an rclone remote. Anything but "not found" from rclone raises StoreError."""

    def __init__(self, remote: str, runner: Runner = subprocess.run, timeout_s: float = TIMEOUT_S) -> None:
        self.remote = remote.rstrip("/")
        self._run = runner
        self._timeout_s = timeout_s

    def _rclone(
        self, args: Sequence[str], missing_ok: bool = False, **kwargs: Any
    ) -> subprocess.CompletedProcess[bytes] | None:
        try:
            done = self._run(["rclone", *args], capture_output=True, timeout=self._timeout_s, **kwargs)
        except subprocess.TimeoutExpired as e:
            raise StoreError(f"rclone {args[0]} {args[1]}: no answer after {self._timeout_s:.0f} s") from e
        if done.returncode == 0:
            return done
        if missing_ok and done.returncode in NOT_FOUND:
            return None
        raise StoreError(
            f"rclone {args[0]} {args[1]}: exit {done.returncode}: {done.stderr.decode('utf-8', 'replace')[-300:]}"
        )

    def _url(self, key: str) -> str:
        return f"{self.remote}/{key.lstrip('/')}"

    def _lines(self, args: Sequence[str]) -> list[str]:
        done = self._rclone(args, missing_ok=True)
        return sorted(line.rstrip("/") for line in done.stdout.decode("utf-8").splitlines() if line) if done else []

    def read(self, key: str) -> bytes | None:
        done = self._rclone(["cat", self._url(key)], missing_ok=True)
        return done.stdout if done else None

    def write(self, key: str, data: bytes) -> None:
        self._rclone(["rcat", self._url(key)], input=data)

    def delete(self, key: str) -> None:
        self._rclone(["deletefile", self._url(key)], missing_ok=True)

    def upload(self, folder: Path, prefix: str) -> None:
        self._rclone(["copy", str(folder), self._url(prefix), "--checksum", "--transfers", "16"])

    def folders(self, prefix: str) -> list[str]:
        return self._lines(["lsf", "--dirs-only", self._url(prefix)])

    def list(self, prefix: str) -> list[str]:
        return self._lines(["lsf", "-R", "--files-only", self._url(prefix)])
