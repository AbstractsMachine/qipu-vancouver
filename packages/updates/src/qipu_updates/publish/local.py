"""A store in a local folder. Writes go to a temporary name and are renamed into place, so a reader never sees half a
file.
"""

from __future__ import annotations

import shutil
from pathlib import Path


class LocalStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError(f"key outside the store: {key}")
        return path

    def read(self, key: str) -> bytes | None:
        path = self._path(key)
        return path.read_bytes() if path.is_file() else None

    def write(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def upload(self, folder: Path, prefix: str) -> None:
        target = self._path(prefix)
        staging = target.with_name(target.name + ".uploading")
        shutil.rmtree(staging, ignore_errors=True)
        shutil.copytree(folder, staging)
        shutil.rmtree(target, ignore_errors=True)
        staging.rename(target)

    def folders(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.is_dir():
            return []
        return sorted(p.name for p in base.iterdir() if p.is_dir() and not p.name.endswith(".uploading"))

    def list(self, prefix: str) -> list[str]:
        base = self._path(prefix)
        if not base.is_dir():
            return []
        return sorted(
            p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file() and not p.name.endswith(".tmp")
        )
