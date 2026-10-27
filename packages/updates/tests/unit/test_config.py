from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from qipu_updates import config as cfg
from tests.conftest import EXAMPLE


def test_the_example_config_reads_its_files_from_its_own_folder() -> None:
    config = cfg.load(EXAMPLE / "updates" / "updates.toml")
    assert (config.name, config.city, config.source.kind, config.reader.kind) == (
        "vancouver",
        "vancouver",
        "mirror",
        "replay",
    )
    assert Path(config.source.options["index"]) == EXAMPLE / "updates" / "arrivals.json"
    assert Path(config.reader.options["readings"]) == EXAMPLE / "readings.jsonl"
    assert config.gazetteer == EXAMPLE / "gazetteer.csv"
    assert config.source.every == dt.timedelta(days=1)
    assert len(config.digest) == 64


@pytest.mark.parametrize(("text", "hours"), [("6h", 6), ("1d", 24), (" 7d ", 168)])
def test_every_reads_hours_and_days(text: str, hours: int) -> None:
    assert cfg.parse_every(text) == dt.timedelta(hours=hours)


@pytest.mark.parametrize(("hours", "text"), [(6, "6h"), (24, "1d"), (48, "2d"), (36, "36h")])
def test_every_is_shown_as_written(hours: int, text: str) -> None:
    assert cfg.format_every(dt.timedelta(hours=hours)) == text


def test_a_bad_every_or_a_missing_section_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(cfg.ConfigError, match="6h or 1d"):
        cfg.parse_every("weekly")
    path = tmp_path / "c.toml"
    path.write_text('[city]\nkey = "vancouver"\n', encoding="utf-8")
    with pytest.raises(cfg.ConfigError, match=r"\[source\]"):
        cfg.load(path)


def test_an_rclone_target_is_kept_as_written(tmp_path: Path) -> None:
    path = tmp_path / "c.toml"
    path.write_text(
        '[city]\nkey = "x"\n[source]\nkind = "archive"\ncollection = "c"\n[reader]\nkind = "anthropic"\nmodel = "m"\n'
        '[publish]\nbackend = "rclone"\ntarget = "r2:bucket/x"\n[gates]\nquote_on_page = 2\n',
        encoding="utf-8",
    )
    config = cfg.load(path)
    assert (config.publish.target, config.gate_limits, config.corrections, config.gazetteer) == (
        "r2:bucket/x",
        {"quote_on_page": 2},
        None,
        None,
    )
    assert config.reader.max_pages_per_run == 50


def test_the_san_francisco_config_reads_legistar_with_a_live_model() -> None:
    config = cfg.load(EXAMPLE.parent / "san_francisco" / "updates" / "updates.toml")
    assert (config.city, config.source.kind, config.reader.kind, config.publish.backend) == (
        "san_francisco",
        "legistar",
        "anthropic",
        "rclone",
    )


BASE = '[city]\nkey = "x"\n[source]\nkind = "archive"\n[reader]\nkind = "replay"\n[publish]\n'


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ('[source]\nkind = "archive"\nevery = "0h"\n', "at least 1h"),
        ("[gates]\nquote_on_page = 1.5\n", "whole number"),
        ("[gates]\nquote_on_page = -1\n", "whole number"),
        ('corrections = "x"\n', r"\[corrections\] table"),
        ("[city\n", "not valid TOML"),
    ],
)
def test_a_malformed_config_is_a_config_error(tmp_path: Path, extra: str, message: str) -> None:
    path = tmp_path / "c.toml"
    text = BASE.replace('[source]\nkind = "archive"\n', extra) if extra.startswith("[source]") else extra + BASE
    path.write_text(text, encoding="utf-8")
    with pytest.raises(cfg.ConfigError, match=message):
        cfg.load(path)
