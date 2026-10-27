from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from qipu_records.read.readers import AnthropicReader, OpenAICompatibleReader, ReplayReader
from qipu_updates import wiring
from qipu_updates.config import ConfigError, PublishConfig, ReaderConfig, SourceConfig
from qipu_updates.publish.local import LocalStore
from qipu_updates.publish.rclone import RcloneStore
from qipu_updates.sources.archive import ArchiveSource
from qipu_updates.sources.legistar import LegistarSource
from tests.conftest import EXAMPLE

DAY = dt.timedelta(days=1)


def test_each_kind_of_source_reader_and_store_is_built(tmp_path: Path) -> None:
    assert isinstance(wiring.make_source(SourceConfig("archive", DAY, {"collection": "c"}), tmp_path), ArchiveSource)
    assert isinstance(wiring.make_source(SourceConfig("legistar", DAY, {}), tmp_path), LegistarSource)
    assert isinstance(
        wiring.make_reader(ReaderConfig("replay", "m", 5, {"readings": str(EXAMPLE / "readings.jsonl")})), ReplayReader
    )
    assert isinstance(wiring.make_reader(ReaderConfig("anthropic", "claude-haiku-5-5", 5)), AnthropicReader)
    openai = wiring.make_reader(ReaderConfig("openai", "qwen", 5, {"base_url": "http://localhost:8000/v1"}))
    assert isinstance(openai, OpenAICompatibleReader)
    assert openai.api_key_env == "OPENAI_API_KEY"
    assert isinstance(wiring.make_store(PublishConfig("rclone", "r2:b")), RcloneStore)
    assert isinstance(wiring.make_store(PublishConfig("local", str(tmp_path / "a"))), LocalStore)
    override = wiring.make_store(PublishConfig("rclone", "r2:b"), tmp_path / "ci")
    assert isinstance(override, LocalStore)
    assert override.root == tmp_path / "ci"


def test_unknown_kinds_are_config_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="source kind"):
        wiring.make_source(SourceConfig("ftp", DAY), tmp_path)
    with pytest.raises(ConfigError, match="reader kind"):
        wiring.make_reader(ReaderConfig("oracle", "m", 1))
    with pytest.raises(ConfigError, match="publish backend"):
        wiring.make_store(PublishConfig("s3", "x"))
