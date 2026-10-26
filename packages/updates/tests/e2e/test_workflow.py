"""The scheduled workflow, end to end: its run step is executed as GitHub would, on the Vancouver sample, offline.

The step is taken from .github/workflows/updates.yml itself, so the test breaks when the workflow and the package drift
apart. It runs in dry-run first (nothing written), then for real twice, as two scheduled days would.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.conftest import ROOT

WORKFLOW = ROOT / ".github" / "workflows" / "updates.yml"
PACKAGE = ROOT / "packages" / "updates"

pytestmark = pytest.mark.e2e


def workflow() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return data


def job() -> dict[str, Any]:
    jobs: dict[str, Any] = workflow()["jobs"]
    return dict(jobs["vancouver"])


def step(step_id: str) -> dict[str, Any]:
    return next(s for s in job()["steps"] if s.get("id") == step_id)


def run_step(tmp: Path, as_of: str | None = None, **env: str) -> subprocess.CompletedProcess[str]:
    """The workflow's run step under bash, with the job's environment pointed at a temporary state folder."""
    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    real = shutil.which("qipu-updates", path=str(Path(sys.executable).parent))
    assert real, "qipu-updates is not installed next to this Python"
    # The step calls .venv/bin/qipu-updates; give it this interpreter's, with --as-of added for the replay.
    shim = bin_dir / "qipu-updates"
    shim.write_text(f'#!/bin/sh\nexec "{real}" "$@"{" --as-of " + as_of if as_of else ""}\n', encoding="utf-8")
    shim.chmod(0o755)
    script = step("run")["run"].replace(".venv/bin/qipu-updates", str(shim))
    state = tmp / "updates-state"
    environment = {
        **os.environ,
        "CONFIG": "../../examples/vancouver/updates/updates.toml",
        "STORE": str(state / "store"),
        "WORK": str(state / "work"),
        "RUNNER_TEMP": str(tmp),
        "GITHUB_STEP_SUMMARY": str(tmp / "summary.md"),
        "GITHUB_RUN_ID": env.pop("RUN_ID", "1"),
        "DRY_RUN": "",
        "PUBLISH": "on",
        **env,
    }
    return subprocess.run(["bash", "-c", script], cwd=PACKAGE, env=environment, capture_output=True, text=True, check=False)


def test_the_workflow_is_scheduled_needs_no_secret_and_alerts_on_failure() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "${{ secrets." not in text
    triggers = workflow().get("on") or workflow()[True]  # type: ignore[index]  # YAML 1.1 reads the key `on` as True
    assert triggers["schedule"][0]["cron"] and "workflow_dispatch" in triggers
    assert job()["permissions"] == {"contents": "read", "issues": "write"}
    alert = next(s for s in job()["steps"] if "alert" in str(s.get("run", "")))
    assert alert["if"] == "failure() && github.event_name == 'schedule'"
    assert all("@" in s["uses"] and len(s["uses"].split("@")[1]) == 40 for s in job()["steps"] if "uses" in s)


def test_a_dry_run_builds_and_checks_but_writes_nothing(tmp_path: Path) -> None:
    done = run_step(tmp_path, DRY_RUN="1")
    assert done.returncode == 0, done.stdout + done.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert (report["status"], report["plan"]["new"], report["records"]) == ("dry-run", 2, 33)
    assert all(g["passed"] for g in report["gates"].values())
    assert not (tmp_path / "updates-state" / "store").exists() or not any((tmp_path / "updates-state" / "store").rglob("*"))
    assert "### vancouver: dry-run" in (tmp_path / "summary.md").read_text(encoding="utf-8")


def test_two_scheduled_days_publish_then_add_only_the_new_meeting(tmp_path: Path) -> None:
    first = run_step(tmp_path, "2026-10-19", RUN_ID="101")
    assert first.returncode == 0, first.stdout + first.stderr
    second = run_step(tmp_path, "2026-10-26", RUN_ID="102")
    assert second.returncode == 0, second.stdout + second.stderr
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert (report["status"], report["documents_built"], report["release"]) == ("published", ["19740219"], "2026-10-26.1")
    latest = json.loads((tmp_path / "updates-state" / "store" / "latest.json").read_text(encoding="utf-8"))
    assert latest["version"] == "2026-10-26.1"


def test_publishing_switched_off_still_builds_and_checks(tmp_path: Path) -> None:
    done = run_step(tmp_path, "2026-10-26", PUBLISH="off")
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["status"] == "publish-paused"
