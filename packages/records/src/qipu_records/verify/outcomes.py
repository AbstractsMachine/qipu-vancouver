"""What happened to an item, in words a reader can trust.

The model reports the last action taken on an item on the page ("passed_first_reading", "referred", ...). Two rules turn
that into the published outcome. Both come from errors found when published facts were checked against the pages:

* Only a final act is an outcome of "passed". A first reading, a referral or a hearing is a step, and is published as
  one.
* A zoning change is "rezoned" only when a by-law or resolution was finally passed or adopted. A proposal, a referral, a
  continued appeal or a refusal is "rezoning proposed". A street renaming or a bare date in the zoning fields is no
  zoning change. Before this rule, 16 of 17 sampled rezoning errors were proposals stored as done.
"""

from __future__ import annotations

import re
from enum import StrEnum


class Outcome(StrEnum):
    PASSED = "passed"
    SUBMITTED_TO_VOTERS = "submitted to voters"
    REFUSED = "refused"
    VETOED = "vetoed"
    VETO_OVERRIDDEN = "veto overridden"
    WITHDRAWN = "withdrawn"
    PENDING = "pending"
    """Referred, continued, tabled, read a first time or heard: still open on this page."""
    UNKNOWN = "unknown"


ACTIONS: dict[str, tuple[str | None, Outcome]] = {
    "adopted": ("adopted", Outcome.PASSED),
    "passed_final": ("final passage", Outcome.PASSED),
    "passed_first_reading": ("first reading", Outcome.PENDING),
    "ordered_submitted_to_voters": ("final passage", Outcome.SUBMITTED_TO_VOTERS),
    "amended": ("amended", Outcome.PENDING),
    "referred": ("referred", Outcome.PENDING),
    "continued": ("continued", Outcome.PENDING),
    "tabled": ("tabled", Outcome.PENDING),
    "failed": ("failed", Outcome.REFUSED),
    "vetoed": ("vetoed", Outcome.VETOED),
    "veto_overridden": ("veto overridden", Outcome.VETO_OVERRIDDEN),
    "withdrawn": ("withdrawn", Outcome.WITHDRAWN),
    "hearing_held": ("hearing", Outcome.PENDING),
    "continues_next_page": (None, Outcome.UNKNOWN),
    "other": (None, Outcome.UNKNOWN),
}

FINAL_KINDS = {"ordinance", "resolution"}

_ZONING_WORD = re.compile(r"zon|district|\bsud\b|\bncd\b|s\.u\.d|special use|height|bulk|classif|\b[a-z]{1,4}-\d", re.I)
_STREET_END = re.compile(
    r"(street|avenue|terrace|place|court|way|lane|alley|road|boulevard|drive|crescent|\bst|\bave?|\brd)\.?\s*$", re.I
)
_MONTH_DATE = re.compile(
    r"^\s*(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d", re.I
)


def stage_and_outcome(action: str) -> tuple[str | None, Outcome]:
    """The procedural stage an action marks, and the outcome it amounts to."""
    return ACTIONS.get(action, (None, Outcome.UNKNOWN))


def is_zoning_change(zoning_from: str, zoning_to: str) -> bool:
    """False for a renamed street or a bare date that the model put in the zoning fields."""
    both = f"{zoning_from} {zoning_to}"
    if not zoning_from and not zoning_to:
        return False
    if _MONTH_DATE.search(zoning_to):
        return False
    return not (_STREET_END.search(zoning_to) and not _ZONING_WORD.search(both))


def zoning_status(kind: str, action: str, zoning_from: str, zoning_to: str) -> str | None:
    """'rezoned', 'rezoning proposed', or None when the item changes no zoning."""
    if not is_zoning_change(zoning_from, zoning_to):
        return None
    _, outcome = stage_and_outcome(action)
    final = kind in FINAL_KINDS and outcome in (Outcome.PASSED, Outcome.VETO_OVERRIDDEN)
    return "rezoned" if final else "rezoning proposed"
