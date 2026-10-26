from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from qipu_updates.monitor import alert, metrics
from qipu_updates.monitor.metrics import RunReport
from qipu_updates.publish.local import LocalStore


def report(**fields: Any) -> RunReport:
    base = RunReport("r1", "vancouver", "2026-10-26", "2026-10-26T14:17:00+00:00")
    for key, value in fields.items():
        setattr(base, key, value)
    return base


def test_each_run_is_saved_and_appended_to_the_metrics(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    metrics.save(store, report(status="published"))
    metrics.save(store, report(run_id="r2", status="no-change"))
    assert json.loads(store.read("runs/r2.json") or b"")["status"] == "no-change"
    lines = (store.read(metrics.METRICS) or b"").decode().splitlines()
    assert [json.loads(line)["run_id"] for line in lines] == ["r1", "r2"]


def test_the_summary_shows_failed_gates_with_their_first_findings() -> None:
    gate = {
        "passed": False,
        "findings": 1,
        "limit": 0,
        "checked": 3,
        "examples": [{"record_id": "m:0/1", "why": "no date", "text": ""}],
    }
    text = metrics.markdown(
        report(status="refused", plan={"new": 1}, documents_left=["m2"], gates={"date_from_header": gate})
    )
    assert "### vancouver: refused" in text
    assert "| date_from_header | **FAIL** | 1 (limit 0) | 3 |" in text
    assert "- `m:0/1`: no date" in text
    assert "| left for the next run | m2 |" in text
    assert report(status="refused").failed
    assert not report(status="no-change").failed


class FakeIssues:
    def __init__(self, open_number: int | None) -> None:
        self.open_number = open_number
        self.created: list[str] = []
        self.comments: list[int] = []

    def find_open(self, title: str) -> int | None:
        return self.open_number

    def create(self, title: str, body: str) -> int:
        self.created.append(title)
        return 7

    def comment(self, number: int, body: str) -> None:
        self.comments.append(number)


def test_a_failure_opens_one_issue_then_comments_on_it() -> None:
    first = FakeIssues(None)
    assert alert.raise_alert(first, "vancouver", "summary", "https://run") == "opened #7"
    assert first.created == ["Scheduled update failed: vancouver"]
    again = FakeIssues(7)
    assert alert.raise_alert(again, "vancouver", "summary", "https://run") == "commented on #7"
    assert again.comments == [7]


def test_gh_issues_uses_the_gh_cli() -> None:
    calls: list[list[str]] = []

    def gh(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args[1:3] == ["label", "create"]:
            raise subprocess.CalledProcessError(1, args)
        out = {
            "list": json.dumps([{"number": 3, "title": "Scheduled update failed: x"}]),
            "create": "https://github.com/o/r/issues/12\n",
        }
        return subprocess.CompletedProcess(args, 0, out.get(args[2], ""), "")

    issues = alert.GhIssues("o/r", runner=gh)
    assert issues.find_open("Scheduled update failed: x") == 3
    assert issues.find_open("other") is None
    assert issues.create("t", "b") == 12
    issues.comment(3, "b")
    assert calls[-1] == ["gh", "issue", "comment", "3", "--body", "b", "--repo", "o/r"]
