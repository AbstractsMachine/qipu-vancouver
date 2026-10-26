"""Turn a config into the objects a run uses: its source, its reader, its store."""

from __future__ import annotations

from pathlib import Path

from qipu_records.read.readers import AnthropicReader, OpenAICompatibleReader, Reader, ReplayReader
from qipu_updates.config import ConfigError, PublishConfig, ReaderConfig, SourceConfig
from qipu_updates.publish import Store
from qipu_updates.publish.local import LocalStore
from qipu_updates.publish.rclone import RcloneStore
from qipu_updates.sources import Source
from qipu_updates.sources.archive import ArchiveSource
from qipu_updates.sources.legistar import SF_BASE, LegistarSource
from qipu_updates.sources.mirror import MirrorSource


def make_source(config: SourceConfig, cache: Path) -> Source:
    options = config.options
    if config.kind == "archive":
        return ArchiveSource(str(options["collection"]), cache / "archive")
    if config.kind == "mirror":
        return MirrorSource(Path(str(options["path"])), Path(str(options["index"])))
    if config.kind == "legistar":
        return LegistarSource(base=str(options.get("base", SF_BASE)))
    raise ConfigError(f"unknown source kind {config.kind!r} (archive, mirror or legistar)")


def make_reader(config: ReaderConfig) -> Reader:
    if config.kind == "replay":
        return ReplayReader(Path(str(config.options["readings"])))
    if config.kind == "anthropic":
        return AnthropicReader(model=config.model)
    if config.kind == "openai":
        return OpenAICompatibleReader(
            model=config.model,
            base_url=str(config.options["base_url"]),
            api_key_env=str(config.options.get("api_key_env", "OPENAI_API_KEY")),
        )
    raise ConfigError(f"unknown reader kind {config.kind!r} (replay, anthropic or openai)")


def make_store(config: PublishConfig, override: Path | None = None) -> Store:
    if override is not None:
        return LocalStore(override)
    if config.backend == "local":
        return LocalStore(Path(config.target))
    if config.backend == "rclone":
        return RcloneStore(config.target)
    raise ConfigError(f"unknown publish backend {config.backend!r} (local or rclone)")
