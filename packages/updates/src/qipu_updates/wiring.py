"""Turn a config into the objects a run uses: its source, its reader, its store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from qipu_records.read.readers import AnthropicReader, OpenAICompatibleReader, Reader, ReplayReader
from qipu_updates.config import ConfigError, PublishConfig, ReaderConfig, SourceConfig
from qipu_updates.publish import Store
from qipu_updates.publish.local import LocalStore
from qipu_updates.publish.rclone import RcloneStore
from qipu_updates.sources import Source
from qipu_updates.sources.archive import ArchiveSource
from qipu_updates.sources.legistar import SF_BASE, LegistarSource
from qipu_updates.sources.mirror import MirrorSource


def _required(options: dict[str, Any], key: str, section: str) -> str:
    value = options.get(key)
    if not value:
        raise ConfigError(f"[{section}] needs {key}")
    return str(value)


def make_source(config: SourceConfig, cache: Path) -> Source:
    """The source a config names, caching under `cache`; ConfigError for an unknown kind or a missing option."""
    options = config.options
    if config.kind == "archive":
        return ArchiveSource(_required(options, "collection", "source"), cache / "archive")
    if config.kind == "mirror":
        return MirrorSource(Path(_required(options, "path", "source")), Path(_required(options, "index", "source")))
    if config.kind == "legistar":
        return LegistarSource(base=str(options.get("base", SF_BASE)))
    raise ConfigError(f"unknown source kind {config.kind!r} (archive, mirror or legistar)")


def make_reader(config: ReaderConfig) -> Reader:
    """The reader a config names; ConfigError for an unknown kind or a missing option."""
    if config.kind == "replay":
        return ReplayReader(Path(_required(config.options, "readings", "reader")))
    if config.kind == "anthropic":
        return AnthropicReader(model=config.model)
    if config.kind == "openai":
        return OpenAICompatibleReader(
            model=config.model,
            base_url=_required(config.options, "base_url", "reader"),
            api_key_env=str(config.options.get("api_key_env", "OPENAI_API_KEY")),
        )
    raise ConfigError(f"unknown reader kind {config.kind!r} (replay, anthropic or openai)")


def make_store(config: PublishConfig, override: Path | None = None) -> Store:
    """The store a config names, or a local folder when `override` is given; ConfigError for an unknown backend."""
    if override is not None:
        return LocalStore(override)
    if config.backend == "local":
        return LocalStore(Path(config.target))
    if config.backend == "rclone":
        return RcloneStore(config.target)
    raise ConfigError(f"unknown publish backend {config.backend!r} (local or rclone)")
