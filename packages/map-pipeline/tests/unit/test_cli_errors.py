"""Mistakes on the command line or in a city file end in one line on stderr and exit 2, not a traceback."""

from __future__ import annotations

from pathlib import Path

import pytest

from qipu_map import cli
from qipu_map.config import load_city
from qipu_map.errors import StageError


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["ingest", "--city", "atlantis"], "no city file"),
        (["ingest", "--area", "nowhere"], "has no area 'nowhere'"),
        (["ingest", "--raw", "no-such-folder"], "no such folder"),
    ],
)
def test_a_bad_option_is_one_line_and_exit_2(
    argv: list[str], message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main([*argv, "--work", str(tmp_path)]) == 2
    assert message in capsys.readouterr().err


def test_a_negative_margin_is_refused_by_the_parser(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as stop:
        cli.main(["ingest", "--margin", "-5", "--work", str(tmp_path)])
    assert stop.value.code == 2


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("[city\n", "not valid TOML"),
        ('[city]\nid = "x"\nname = "X"\n', "missing 'projection'"),
    ],
)
def test_a_malformed_city_file_is_a_stage_error(tmp_path: Path, text: str, message: str) -> None:
    path = tmp_path / "x.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(StageError, match=message):
        load_city(path)
