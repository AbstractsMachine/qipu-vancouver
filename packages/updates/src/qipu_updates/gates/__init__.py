"""Checks a release must pass before it is published.

Each gate reads the release as it will be published, not the extractor's own flags, and re-derives what it checks from the
page text: the quote is on the page, the date is the one the page's header gives, a proposal is not shown as decided, no
private name is shown where the privacy rule hides it, and nothing is hidden that the rule keeps. A gate fails when its
findings exceed its limit (0 unless the config says otherwise); one failed gate stops the publish.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

EXAMPLES = 20


@dataclass(frozen=True)
class Finding:
    record_id: str
    why: str
    text: str = ""


@dataclass
class GateResult:
    name: str
    checked: int = 0
    skipped: int = 0
    """Records carried over from an earlier release whose pages are not in the working copy; they passed when built."""
    findings: list[Finding] = field(default_factory=list)
    limit: int = 0

    @property
    def passed(self) -> bool:
        return len(self.findings) <= self.limit

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checked": self.checked,
            "skipped": self.skipped,
            "findings": len(self.findings),
            "limit": self.limit,
            "examples": [vars(f) for f in self.findings[:EXAMPLES]],
        }


class PageTexts(Protocol):
    def text(self, page_id: str) -> str | None: ...

    def document(self, doc_id: str) -> tuple[list[str], str | None] | None:
        """All page texts of a document and its catalogue date, or None when they are not at hand."""
        ...


def page_id_of(record: dict[str, Any]) -> str:
    return str(record["id"]).rsplit("/", 1)[0]


def previous_page_id(page_id: str) -> str:
    item, _, n = page_id.rpartition(":")
    return f"{item}:{int(n) - 1}"
