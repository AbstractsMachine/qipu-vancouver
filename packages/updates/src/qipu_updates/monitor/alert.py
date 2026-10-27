"""Open a GitHub issue when a scheduled run fails, or comment on the one already open.

One open issue per config, labelled `workflow-failure` (the label the other scheduled jobs use), so a source that fails
every day makes one issue with a comment a day, not thirty issues. Close the issue once the run is green again. Uses the
`gh` CLI with the workflow's own GITHUB_TOKEN; no other secret.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
from collections.abc import Callable
from typing import Any, Protocol

LABEL = "workflow-failure"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class Issues(Protocol):
    def find_open(self, title: str) -> int | None: ...

    def create(self, title: str, body: str) -> int: ...

    def comment(self, number: int, body: str) -> None: ...


class GhIssues:
    def __init__(self, repo: str, runner: Runner | None = None) -> None:
        self.repo = repo
        self._run = runner or subprocess.run

    def _gh(self, *args: str) -> str:
        done = self._run(["gh", *args, "--repo", self.repo], capture_output=True, text=True, check=True)
        return done.stdout

    def find_open(self, title: str) -> int | None:
        rows: list[dict[str, Any]] = json.loads(
            self._gh("issue", "list", "--label", LABEL, "--state", "open", "--limit", "100", "--json", "number,title")
        )
        return next((int(r["number"]) for r in rows if r["title"] == title), None)

    def create(self, title: str, body: str) -> int:
        with contextlib.suppress(subprocess.CalledProcessError):  # the label exists already
            self._gh("label", "create", LABEL, "--color", "B60205", "--description", "A scheduled job failed")
        url = self._gh("issue", "create", "--title", title, "--label", LABEL, "--body", body).strip()
        return int(url.rsplit("/", 1)[-1])

    def comment(self, number: int, body: str) -> None:
        self._gh("issue", "comment", str(number), "--body", body)


def title_for(config: str) -> str:
    return f"Scheduled update failed: {config}"


def raise_alert(issues: Issues, config: str, summary: str, run_url: str) -> str:
    """Open or update the config's failure issue. Returns what was done, for the log."""
    title = title_for(config)
    body = (
        f"{summary}\n\nRun: {run_url}\n\nClose this issue once the scheduled run is green again. See docs/updates.md."
    )
    number = issues.find_open(title)
    if number is None:
        return f"opened #{issues.create(title, body)}"
    issues.comment(number, body)
    return f"commented on #{number}"
