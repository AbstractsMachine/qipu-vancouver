"""The command line, run in-process."""

import json
import shutil
import urllib.error
from pathlib import Path

import pytest

from qipu_records import cli
from qipu_records.map import gazetteer
from tests.conftest import SAMPLE, SavedArchive


def test_demo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["demo", "--out", str(tmp_path), "--sample", str(SAMPLE)]) == 0
    assert '"decisions": 33' in capsys.readouterr().out
    assert (tmp_path / "decisions.geojson").exists()


def test_fetch_read_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(cli, "ArchiveClient", SavedArchive)
    out = tmp_path / "van"
    assert cli.main(["fetch", "--out", str(out), "--cache", str(tmp_path / "cache"), "19700609"]) == 0
    replay = tmp_path / "answers.jsonl"
    replay.write_text(json.dumps({"page_id": "19700609:2", "model": "m", "prompt_version": "v", "items": []}) + "\n")
    assert cli.main(["read", "--out", str(out), "--replay", str(replay), "--max-pages", "5"]) == 0
    assert cli.main(["build", "--out", str(out)]) == 0
    output = capsys.readouterr().out
    assert "pages added to" in output and ": 5" in output
    assert "pages read: 1" in output
    assert '"pages_read": 1' in output


def test_readers_are_chosen_from_the_options() -> None:
    parser = cli.parser()
    anthropic = cli._reader(parser.parse_args(["read", "--out", "x"]))
    assert type(anthropic).__name__ == "AnthropicReader"
    open_model = cli._reader(parser.parse_args(["read", "--out", "x", "--model", "m", "--base-url", "http://localhost:8000/v1"]))
    assert type(open_model).__name__ == "OpenAICompatibleReader"


def test_gazetteer_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gazetteer, "vancouver_rows", lambda: iter([("area", "strathcona", 49.27, -123.08)]))
    assert cli.main(["gazetteer", "--out", str(tmp_path / "g.csv")]) == 0
    assert cli.main(["gazetteer", "--city", "san_francisco", "--out", str(tmp_path / "sf.csv")]) == 2


def test_build_with_a_gazetteer(tmp_path: Path) -> None:
    for name in ("items.json", "pages.jsonl", "pagemaps.json", "readings.jsonl"):
        shutil.copy(SAMPLE / name, tmp_path / name)
    assert cli.main(["-v", "build", "--out", str(tmp_path), "--gazetteer", str(SAMPLE / "gazetteer.csv")]) == 0
    assert json.loads((tmp_path / "summary.json").read_text())["placed"] == 9


def test_read_without_a_key_explains_and_fails(
    sample_copy: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert cli.main(["read", "--out", str(sample_copy)]) == 2
    assert "set ANTHROPIC_API_KEY in the environment" in capsys.readouterr().err


def test_a_bad_identifier_is_refused_by_the_command_line(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as stopped:
        cli.main(["fetch", "--out", "unused", "../../etc"])
    assert stopped.value.code == 2
    assert "not an archive.org identifier" in capsys.readouterr().err


def test_a_network_failure_is_one_line_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def offline(*args: object, **kwargs: object) -> int:
        raise urllib.error.URLError("nodename nor servname provided")

    monkeypatch.setattr(cli, "fetch_items", offline)
    assert cli.main(["fetch", "--out", str(tmp_path), "19740219"]) == 1
    assert "network error, nothing lost" in capsys.readouterr().err


def test_build_before_fetch_names_the_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["build", "--out", str(tmp_path)]) == 1
    assert "no such file" in capsys.readouterr().err
