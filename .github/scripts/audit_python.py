"""Audit a pinned requirements file with pip-audit and fail only on high or critical advisories.

pip-audit reports every known advisory and no severity. Each advisory is looked up on OSV for its severity: HIGH and
CRITICAL fail the run, anything lower is printed, and an advisory whose severity cannot be found is printed as a
warning, so a new low-severity advisory or an OSV outage never blocks a pull request.

    python .github/scripts/audit_python.py packages/records/requirements-dev.txt
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request

FAIL_ON = {"HIGH", "CRITICAL"}


def severity(advisory_ids: list[str]) -> str:
    """The first severity OSV gives for any of the advisory's ids, or UNKNOWN."""
    for advisory_id in advisory_ids:
        try:
            with urllib.request.urlopen(f"https://api.osv.dev/v1/vulns/{advisory_id}", timeout=30) as reply:
                found = json.load(reply).get("database_specific", {}).get("severity")
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
        if found:
            return str(found).upper()
    return "UNKNOWN"


def main(requirements: str) -> int:
    run = subprocess.run(  # noqa: S603 - fixed argument list; the requirements path comes from our own workflow
        ["pip-audit", "--require-hashes", "--disable-pip", "--format", "json", "-r", requirements],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        report = json.loads(run.stdout)
    except ValueError:
        # pip-audit itself failed (for example the vulnerability service was unreachable): a warning, not a verdict.
        print(f"::warning::pip-audit gave no report for {requirements}: {run.stderr.strip()[-300:]}")
        return 0
    failing = 0
    for dependency in report.get("dependencies", []):
        for vuln in dependency.get("vulns", []):
            ids = [vuln["id"], *vuln.get("aliases", [])]
            level = severity(ids)
            fixed = vuln.get("fix_versions")
            line = f"{dependency['name']} {dependency['version']}: {vuln['id']} ({level}), fixed in {fixed}"
            if level in FAIL_ON:
                print(f"::error::{line}")
                failing += 1
            else:
                print(f"::warning::{line}")
    print(f"{requirements}: {failing} high or critical advisories")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
