"""The command line, as an operator uses it: run, look, pause, roll back, raise the alert."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from qipu_updates import cli


def main(example: Path, tmp: Path, *args: str) -> int:
    return cli.main(
        [args[0], "--config", str(example / "updates" / "updates.toml"), "--store", str(tmp / "store"), *args[1:]]
    )


def test_two_runs_a_rollback_and_a_resume(example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    work = str(tmp_path / "work")
    summary = tmp_path / "summary.md"
    assert (
        main(
            example,
            tmp_path,
            "run",
            "--work",
            work,
            "--as-of",
            "2026-10-19",
            "--run-id",
            "a",
            "--summary",
            str(summary),
        )
        == 0
    )
    assert (
        main(
            example,
            tmp_path,
            "run",
            "--work",
            work,
            "--as-of",
            "2026-10-26",
            "--run-id",
            "b",
            "--report",
            str(tmp_path / "r.json"),
        )
        == 0
    )
    assert json.loads((tmp_path / "r.json").read_text())["documents_built"] == ["19740219"]
    assert "### vancouver: published" in summary.read_text()

    capsys.readouterr()
    main(example, tmp_path, "releases")
    assert capsys.readouterr().out.splitlines() == [
        "  2026-10-19.1       10 records  gates passed  run a",
        "* 2026-10-26.1       32 records  gates passed  run b",
    ]
    assert main(example, tmp_path, "rollback", "--reason", "a wrong date") == 0
    assert "latest is now 2026-10-19.1 (was 2026-10-26.1)" in capsys.readouterr().out
    main(example, tmp_path, "status")
    status = capsys.readouterr().out
    assert "published: 2026-10-19.1" in status
    assert "paused: publish" in status
    assert "rolled back from 2026-10-26.1" in status

    assert main(example, tmp_path, "resume") == 0
    assert main(example, tmp_path, "pause", "--scope", "all", "--reason", "moving the bucket") == 0
    assert main(example, tmp_path, "run", "--work", work, "--as-of", "2026-10-27", "--run-id", "c") == 0
    assert "vancouver: paused" in capsys.readouterr().out


def test_a_refused_run_exits_3(example: Path, tmp_path: Path) -> None:
    (example / "updates" / "corrections.jsonl").write_text(
        '{"rule_id": "x", "action": "replace_text", "find": "Council", "replace": "Kouncil", "max_rows": 0}\n',
        encoding="utf-8",
    )
    assert main(example, tmp_path, "run", "--work", str(tmp_path / "w"), "--as-of", "2026-10-26", "--run-id", "r") == 3


def test_alert_reads_the_report_or_says_there_was_none(
    example: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bodies: list[str] = []

    def gh(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        bodies.extend(a for a in args if a.startswith("###"))
        out = "[]" if args[2] == "list" else "https://github.com/o/r/issues/5\n"
        return subprocess.CompletedProcess(args, 0, out, "")

    monkeypatch.setattr(subprocess, "run", gh)
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"run_id": "r", "config": "vancouver", "as_of": "2026-10-26", "started": "t", "status": "failed"})
    )
    for path in (report, tmp_path / "none.json"):
        main(example, tmp_path, "alert", "--report", str(path), "--run-url", "https://run", "--repo", "o/r")
    assert capsys.readouterr().out.count("opened #5") == 2
    assert bodies[0].startswith("### vancouver: failed")
    assert "stopped before it wrote a report" in bodies[-1]


def test_a_bad_config_or_argument_is_a_message_not_a_traceback(
    example: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nowhere.toml"
    assert cli.main(["status", "--config", str(missing)]) == 2
    assert "no such file" in capsys.readouterr().err
    config = example / "updates" / "updates.toml"
    config.write_text(config.read_text(encoding="utf-8").replace('key = "vancouver"', 'key = "atlantis"'), "utf-8")
    assert main(example, tmp_path, "run", "--as-of", "2026-10-19") == 2
    assert "unknown city 'atlantis'" in capsys.readouterr().err
    for bad in (["run", "--as-of", "2026/10/19"], ["status", "--last", "0"], ["status", "--last", "-3"]):
        with pytest.raises(SystemExit) as stop:
            main(example, tmp_path, *bad)
        assert stop.value.code == 2
