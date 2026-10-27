"""What a run did, as numbers: written to runs/<run id>.json and appended to metrics.jsonl in the store.

The same report becomes the job summary in GitHub Actions and the body of the failure issue.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from qipu_updates.publish import Store

METRICS = "metrics.jsonl"
FAILED = ("refused", "failed")
"""refused: a gate stopped the publish. failed: the run itself broke."""


@dataclass
class RunReport:
    """What one run did, as numbers and a status."""

    run_id: str
    config: str
    as_of: str
    started: str
    status: str = "running"
    detail: str = ""
    finished: str = ""
    dry_run: bool = False
    plan: dict[str, int] = field(default_factory=dict)
    pages_read: int = 0
    readings_reused: int = 0
    documents_built: list[str] = field(default_factory=list)
    documents_left: list[str] = field(default_factory=list)
    """Not finished this run (page budget spent); the next run continues them."""
    records: int = 0
    records_before: int = 0
    rejected: int = 0
    release: str | None = None
    published: bool = False
    gates: dict[str, Any] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return self.status in FAILED

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, sort_keys=True) + "\n"


def save(store: Store, report: RunReport) -> None:
    store.write(f"runs/{report.run_id}.json", report.to_json().encode("utf-8"))
    line = json.dumps(asdict(report), sort_keys=True) + "\n"
    store.write(METRICS, (store.read(METRICS) or b"") + line.encode("utf-8"))


def markdown(report: RunReport) -> str:
    lines = [
        f"### {report.config}: {report.status}",
        "",
        report.detail,
        "",
        "| | |",
        "|---|---|",
        f"| run | `{report.run_id}` (as of {report.as_of}{', dry run' if report.dry_run else ''}) |",
        f"| documents | {', '.join(f'{v} {k}' for k, v in report.plan.items()) or 'none listed'} |",
        f"| built | {len(report.documents_built)} ({', '.join(report.documents_built[:10])}) |",
        f"| pages read by the model | {report.pages_read} (readings reused: {report.readings_reused}) |",
        f"| records | {report.records} (before: {report.records_before}; rejected this run: {report.rejected}) |",
        f"| release | {report.release or '-'} ({'published' if report.published else 'not published'}) |",
    ]
    if report.documents_left:
        lines.append(f"| left for the next run | {', '.join(report.documents_left[:10])} |")
    if report.gates:
        lines += ["", "| gate | result | findings | checked |", "|---|---|---|---|"]
        for name, gate in report.gates.items():
            mark = "pass" if gate["passed"] else "**FAIL**"
            lines.append(f"| {name} | {mark} | {gate['findings']} (limit {gate['limit']}) | {gate['checked']} |")
        for name, gate in report.gates.items():
            if not gate["passed"]:
                lines += ["", f"{name}, first findings:"]
                lines += [f"- `{e['record_id']}`: {e['why']} {e['text'][:80]!r}" for e in gate["examples"][:5]]
    return "\n".join(lines).replace("\n\n\n", "\n\n") + "\n"
