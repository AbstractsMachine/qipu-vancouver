"""Find the quote a model gave as evidence on the page it was read from.

Every decision the model lists carries a quote: the first words of the item's heading, copied from the OCR. A decision is only as
good as that quote, so each one is looked up again in the page text before it is published. OCR text is noisy and models tidy
it up a little, so the lookup ignores case and runs of whitespace, and falls back to a fuzzy match of the quote's opening words.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from enum import StrEnum

_WHITESPACE = re.compile(r"\s+")

MIN_QUOTE_CHARS = 8
"""Shorter quotes match too easily to count as evidence."""

FUZZY_PREFIX_CHARS = 60
FUZZY_MIN_BLOCK = 20
FUZZY_MIN_RATIO = 0.6


class QuoteStatus(StrEnum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class QuoteMatch:
    status: QuoteStatus
    offset: int | None
    """Character offset of the match in the original page text."""
    score: float

    @property
    def found(self) -> bool:
        return self.status is not QuoteStatus.NOT_FOUND


NOT_FOUND = QuoteMatch(QuoteStatus.NOT_FOUND, None, 0.0)


def normalise(text: str) -> tuple[str, list[int]]:
    """Lower-case the text and collapse whitespace; return it with each character's offset in the original."""
    out: list[str] = []
    offsets: list[int] = []
    in_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if in_space:
                continue
            out.append(" ")
            in_space = True
        else:
            out.append(ch.lower())
            in_space = False
        offsets.append(i)
    return "".join(out), offsets


def locate(quote: str, text: str) -> QuoteMatch:
    """Where the quote is on the page: an exact match after normalising, else a fuzzy match of its opening words."""
    needle = _WHITESPACE.sub(" ", quote.strip().lower())
    if len(needle) < MIN_QUOTE_CHARS:
        return NOT_FOUND
    haystack, offsets = normalise(text)
    for candidate in (needle, needle[:80]):
        at = haystack.find(candidate)
        if at >= 0:
            return QuoteMatch(QuoteStatus.EXACT, offsets[at], 1.0)
    return _fuzzy(needle, haystack, offsets)


def _fuzzy(needle: str, haystack: str, offsets: list[int]) -> QuoteMatch:
    head = needle[:FUZZY_PREFIX_CHARS]
    block = difflib.SequenceMatcher(None, haystack, head, autojunk=False).find_longest_match(0, len(haystack), 0, len(head))
    if block.size < FUZZY_MIN_BLOCK:
        return NOT_FOUND
    start = max(0, block.a - block.b)
    window = haystack[start : start + len(needle[:80])]
    ratio = difflib.SequenceMatcher(None, window, needle[:80]).ratio()
    if ratio < FUZZY_MIN_RATIO:
        return NOT_FOUND
    return QuoteMatch(QuoteStatus.FUZZY, offsets[start], round(ratio, 3))
