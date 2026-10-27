"""One TOML file per city: where its documents come from, who reads them, what the gates allow and where releases go.

Relative paths in the file are read from the file's own folder, so a config and its fixtures can move together.
See examples/vancouver/updates.toml for a full example.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_EVERY = re.compile(r"^(\d+)([hd])$")
PATH_KEYS = {"path", "index", "readings"}
"""Options that name files; they are read from the config's folder."""


class ConfigError(ValueError):
    """The config file is malformed or incomplete."""


def parse_every(text: str) -> dt.timedelta:
    """'6h' or '1d' as a timedelta."""
    match = _EVERY.match(text.strip())
    if not match:
        raise ConfigError(f"'every' must look like 6h or 1d, not {text!r}")
    n = int(match.group(1))
    if n < 1:
        raise ConfigError(f"'every' must be at least 1h, not {text!r}")
    return dt.timedelta(hours=n) if match.group(2) == "h" else dt.timedelta(days=n)


def format_every(every: dt.timedelta) -> str:
    """A check interval as it is written in a config: "6h", or "1d" for whole days."""
    hours = int(every.total_seconds() // 3600)
    return f"{hours // 24}d" if hours % 24 == 0 else f"{hours}h"


@dataclass(frozen=True)
class SourceConfig:
    """The [source] section: what kind of source, how often to check it, and its own options."""

    kind: str
    """archive (an archive.org collection), mirror (a local copy of one) or legistar (a Legistar calendar)."""
    every: dt.timedelta
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReaderConfig:
    """The [reader] section: which kind of reader and model, and how many pages one run may read."""

    kind: str
    """replay (recorded answers), anthropic or openai (any OpenAI-compatible endpoint)."""
    model: str
    max_pages_per_run: int
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PublishConfig:
    """The [publish] section: the kind of store releases go to, and where it is."""

    backend: str
    """local (a folder) or rclone (any rclone remote: S3, R2, GCS ...)."""
    target: str


@dataclass(frozen=True)
class Config:
    """A city's checked config file. `load` makes one."""

    name: str
    city: str
    source: SourceConfig
    reader: ReaderConfig
    publish: PublishConfig
    gate_limits: dict[str, int]
    gazetteer: Path | None
    corrections: Path | None
    path: Path
    digest: str
    """sha256 of the config file, recorded in every release it made."""


def _path(base: Path, value: Any) -> Path | None:
    return (base / str(value)).resolve() if value else None


def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"missing [{key}] section")
    return dict(value)


def _gate_limits(data: dict[str, Any]) -> dict[str, int]:
    gates = data.get("gates", {})
    if not isinstance(gates, dict) or not all(isinstance(v, int) and v >= 0 for v in gates.values()):
        raise ConfigError("[gates] must map each gate to a whole number of failures it allows")
    return {str(k): int(v) for k, v in gates.items()}


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    """An optional table; absent is empty."""
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{key} must be a [{key}] table")
    return value


def load(path: Path) -> Config:
    """Read and check a config. Raises `ConfigError` for anything malformed, `OSError` if the file cannot be read."""
    raw = path.read_bytes()
    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"{path}: not valid TOML: {error}") from error
    base = path.parent.resolve()
    source = _section(data, "source")
    reader = _section(data, "reader")
    publish = _section(data, "publish")
    for section in (source, reader):
        for key in PATH_KEYS & section.keys():
            section[key] = str(_path(base, section[key]))
    target = str(publish.get("target", ""))
    if publish.get("backend", "local") == "local":
        target = str(_path(base, target or "published"))
    return Config(
        name=str(data.get("name") or path.stem),
        city=str(_section(data, "city").get("key", "")),
        source=SourceConfig(str(source.pop("kind", "")), parse_every(str(source.pop("every", "1d"))), source),
        reader=ReaderConfig(
            str(reader.pop("kind", "")), str(reader.pop("model", "")), int(reader.pop("max_pages_per_run", 50)), reader
        ),
        publish=PublishConfig(str(publish.get("backend", "local")), target),
        gate_limits=_gate_limits(data),
        gazetteer=_path(base, _table(data, "city").get("gazetteer")),
        corrections=_path(base, _table(data, "corrections").get("path")),
        path=path.resolve(),
        digest=hashlib.sha256(raw).hexdigest(),
    )
