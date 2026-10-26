"""Proposed vs decided: a step (a first reading, a referral, a hearing) is never published as a decision.

The published stage and outcome must be what qipu-records' rule gives for the recorded action, and a rezoning is "rezoned"
only when a by-law or resolution was finally passed. Before this rule, 16 of 17 sampled rezoning errors in San Francisco
were proposals stored as done. A correction or a carried-over record from an older extractor can break it; this catches both.
"""

from __future__ import annotations

from typing import Any

from qipu_records.verify.outcomes import FINAL_KINDS, Outcome, stage_and_outcome
from qipu_updates.gates import Finding, GateResult

FINAL_OUTCOMES = {Outcome.PASSED.value, Outcome.VETO_OVERRIDDEN.value}


def check(records: list[dict[str, Any]], limit: int = 0) -> GateResult:
    result = GateResult("proposed_vs_decided", limit=limit)
    for record in records:
        result.checked += 1
        action = str(record.get("action") or "other")
        stage, outcome = stage_and_outcome(action)
        rid = str(record["id"])
        if record.get("outcome") != outcome.value or record.get("stage") != stage:
            why = f"outcome '{record.get('outcome')}' / stage '{record.get('stage')}' does not follow from action '{action}'"
            result.findings.append(Finding(rid, why))
        elif record.get("zoning") == "rezoned" and not (record.get("kind") in FINAL_KINDS and outcome.value in FINAL_OUTCOMES):
            result.findings.append(Finding(rid, f"shown as rezoned, but the {record.get('kind')} was only {action}"))
    return result
