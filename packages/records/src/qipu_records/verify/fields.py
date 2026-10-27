"""Check the fields a model filled in against the words of the page it cites, and correct or flag them.

The model reads a page and says what happened to each item: its outcome, whether it was amended, how the vote went, and
a one-sentence summary. Each of these is checked here against the text of the item on the cited page (from its quote to
the next item's quote), using only the words the minutes use for them:

* outcome: the verdict printed after each motion ("- CARRIED", "(Carried)", "- LOST", "DEFEATED"). A motion moved "in
  amendment" has its own verdict, and "the motion was put and - CARRIED" is the main motion's. An outcome of `unknown`
  is corrected from the verdicts; `passed` when every main motion was LOST is corrected to `refused`.
* amended: true only when an amendment CARRIED (or the item was adopted "as amended"). An amendment that was LOST does
  not amend anything.
* vote: a dissent printed under the main motion ("(Alderman Massey voted against the motion)", "Aldermen Bird and Rankin
  opposed") is a vote, and its names are added to `noes_names`.
* summary: a year the summary names must be plausible for the meeting: printed on the page, or no later than ten years
  after it. A summary that says "2019" on a page of 1970 is flagged; it cannot be corrected without a model.

Every correction and every conflict that cannot be corrected is listed in the record's `checks`, so a reader sees what
was changed from the model's reading and what is in doubt. These checks came from a review of published records against
the archive.org pages (19700609 scan pages 10-11, 19740219 scan page 1).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from enum import StrEnum

from qipu_records.verify.outcomes import Outcome

# A verdict: at the start of a line, after a dash, a parenthesis or an asterisk, or in "was put and - CARRIED".
_VERDICT = re.compile(
    r"(?:^|[-–(*]\s*|\bput\s+and\s*-?\s*)(carried|lost|defeated)\b(?!\s+(?:out|over|on|forward|into)\b)",
    re.I | re.M,
)
_MOVED = re.compile(r"\bmoved\s+by\b", re.I)
_IN_AMENDMENT = re.compile(r"\bin\s+amendment\b|\bamendment\s+(?:moved|that)\b", re.I)
_PUT = re.compile(r"\bput\s+and\s*-?\s*$", re.I)
_AS_AMENDED = re.compile(r"\bas\s+amended\b", re.I)
_REFUSAL = re.compile(
    r"\b(?:be\s+refused|be\s+not\s+approved|not\s+be\s+approved|no\s+further\s+action|be\s+denied|be\s+rejected"
    r"|be\s+not\s+granted|not\s+be\s+granted)\b",
    re.I,
)
_TITLE = r"(?:alderm[ae]n|ald\.|aid\.|councill?ors?|supervisors?|mayor)"
_NAME = r"[A-Z][A-Za-z'\-]+"
_NAMES = rf"{_NAME}(?:(?:\s*,\s*|\s+and\s+|\s*,\s*and\s+){_NAME})*"
_DISSENT = re.compile(
    rf"(?:{_TITLE}\s+)?({_NAMES})\s+(?:(?:having\s+)?voted\s+against|(?:being\s+|was\s+|were\s+)?opposed)"
)
_NOT_NAMES = {"The", "That", "This", "It", "Council", "Motion", "Members", "All", "Those", "Others"}
_YEAR = re.compile(r"\b(1[6-9]\d\d|20\d\d)\b")
LATEST_PLAUSIBLE_YEARS = 10
"""A summary may name a year this far after the meeting (a plan "to be completed by 1975") without it being printed."""


class Verdict(StrEnum):
    CARRIED = "carried"
    LOST = "lost"


@dataclass(frozen=True)
class Motion:
    """One motion moved in an item, with its verdict and the dissents printed under it."""

    text: str
    amendment: bool
    verdict: Verdict | None
    dissent: tuple[str, ...] = ()


@dataclass(frozen=True)
class Check:
    """One field checked against the page: corrected to what the page prints, or in conflict with it."""

    field: str
    result: str
    """'corrected' or 'conflict'"""
    why: str
    was: object = None

    def as_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"field": self.field, "result": self.result, "why": self.why}
        if self.result == "corrected":
            out["was"] = self.was
        return out


@dataclass
class Fields:
    """The fields the checks may correct, as they will be published."""

    outcome: str
    amended: bool
    vote: dict[str, object] | None
    summary: str
    checks: list[Check] = field(default_factory=list)


def _verdict(word: str) -> Verdict:
    return Verdict.CARRIED if word.lower() == "carried" else Verdict.LOST


def _names(text: str) -> list[str]:
    out = [n for n in re.split(r"\s*,\s*and\s+|\s*,\s*|\s+and\s+", text) if n]
    return [n for n in out if n not in _NOT_NAMES]


def motions(span: str) -> list[Motion]:
    """The motions moved in an item's text, in order. "Put and - CARRIED" after an amendment is the main motion's."""
    starts = [m.start() for m in _MOVED.finditer(span)]
    out: list[Motion] = []
    for i, start in enumerate(starts):
        block = span[start : starts[i + 1] if i + 1 < len(starts) else len(span)]
        amendment = bool(_IN_AMENDMENT.search(block[:80]))
        verdicts = list(_VERDICT.finditer(block))
        own = verdicts[0] if verdicts else None
        if own is not None and amendment and _PUT.search(block[: own.start(1)]):
            own = None
        cut = own.end() if own else len(block)
        put = [v for v in verdicts if v is not own and _PUT.search(block[: v.start(1)])]
        after_own = block[cut : put[0].start() if put else len(block)]
        out.append(
            Motion(block[:cut], amendment, _verdict(own.group(1)) if own else None, _dissent(after_own) if own else ())
        )
        for main in put:
            rest = block[main.end() :]
            out.append(Motion("", False, _verdict(main.group(1)), _dissent(rest)))
    return out


def _dissent(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for match in _DISSENT.finditer(text[:300]):
        found.extend(n for n in _names(match.group(1)) if n not in found)
    return tuple(found)


def check_fields(
    span: str, page_text: str, date: dt.date | None, *, outcome: str, amended: bool, vote: dict[str, object] | None,
    summary: str,
) -> Fields:  # fmt: skip
    """The fields corrected against the item's text on the page (`span`), and the checks that were made."""
    out = Fields(outcome, amended, vote, summary)
    moved = motions(span)
    _check_outcome(out, moved)
    _check_amended(out, moved, span)
    _check_vote(out, moved)
    _check_years(out, page_text, date)
    return out


def _check_outcome(out: Fields, moved: list[Motion]) -> None:
    main = [m for m in moved if not m.amendment and m.verdict is not None]
    if not main:
        return
    carried = [m for m in main if m.verdict is Verdict.CARRIED]
    if out.outcome == Outcome.UNKNOWN:
        if carried:
            last = carried[-1]
            refusal = bool(_REFUSAL.search(last.text))
            new = Outcome.REFUSED if refusal else Outcome.PASSED
            why = "the motion " + ("not to proceed " if refusal else "") + "was CARRIED"
        else:
            new, why = Outcome.REFUSED, "every motion on the item was LOST"
        out.checks.append(Check("outcome", "corrected", why, out.outcome))
        out.outcome = new.value
    elif out.outcome == Outcome.PASSED and not carried:
        out.checks.append(Check("outcome", "corrected", "every motion on the item was LOST", out.outcome))
        out.outcome = Outcome.REFUSED.value


def _check_amended(out: Fields, moved: list[Motion], span: str) -> None:
    amendments = [m for m in moved if m.amendment]
    carried = any(m.verdict is Verdict.CARRIED for m in amendments) or bool(_AS_AMENDED.search(span))
    if out.amended and amendments and not carried:
        out.checks.append(Check("amended", "corrected", "the amendment moved was LOST", True))
        out.amended = False
    elif not out.amended and carried:
        out.checks.append(Check("amended", "corrected", "an amendment was CARRIED", False))
        out.amended = True


def _check_vote(out: Fields, moved: list[Motion]) -> None:
    dissent = [n for m in moved if not m.amendment for n in m.dissent]
    if not dissent:
        return
    vote = dict(out.vote) if out.vote else {}
    noes_names = [str(n) for n in vote.get("noes_names") or []]  # type: ignore[attr-defined]
    missing = [n for n in dissent if n.lower() not in {x.lower() for x in noes_names}]
    if not missing:
        return
    was = out.vote
    noes_names += missing
    noes = vote.get("noes")
    out.vote = {
        "ayes": vote.get("ayes"),
        "noes": max(int(noes), len(noes_names)) if isinstance(noes, int) else len(noes_names),
        "absent": vote.get("absent"),
        "ayes_names": vote.get("ayes_names") or [],
        "noes_names": noes_names,
        "absent_names": vote.get("absent_names") or [],
    }
    out.checks.append(Check("vote", "corrected", f"the page prints {', '.join(missing)} voting against", was))


def _check_years(out: Fields, page_text: str, date: dt.date | None) -> None:
    if date is None:
        return
    printed = re.sub(r"(?<=\d)\s+(?=\d)", "", page_text)
    for year in dict.fromkeys(int(y) for y in _YEAR.findall(out.summary)):
        if year <= date.year + LATEST_PLAUSIBLE_YEARS or str(year) in printed:
            continue
        why = f"the summary names {year}, which the page does not print, for a meeting of {date.year}"
        out.checks.append(Check("summary", "conflict", why))
