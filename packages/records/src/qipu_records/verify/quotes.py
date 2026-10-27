"""Find the quote a model gave as evidence on the page it was read from.

Every decision the model lists carries a quote: the first words of the item's heading, copied from the OCR. A decision
is only as good as that quote, so each one is looked up again in the page text before it is published. OCR text is noisy
and models tidy it up a little, so the lookup ignores case and runs of whitespace, and falls back to a fuzzy match of
the whole quote.

A quote may run over a page break: the model glues the "(Cont'd.)" heading at the top of a page to the words that
opened the item on the page before ("Capilano Stadium: Future Uses (Cont'd.) Subsequent to the last meeting of the
Sub-Committee the Board", 19700609 scan pages 9-10). Such a quote is found only when both pages are at hand: the heading
on the cited page and the rest on the page before it. On one page alone it is not found.
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
FUZZY_MAX_CHARS = 300
"""A fuzzy match is scored over the whole quote, up to this length, not just its opening words."""

_CONTINUED = re.compile(r"\(\s*cont(?:'|’)?(?:inue)?d\.?\s*\)\.?", re.I)


class QuoteStatus(StrEnum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class QuoteMatch:
    """Where, and how well, a quote was found in a page's text."""

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


def continuation(quote: str) -> tuple[str, str] | None:
    """A quote that glues a "(Cont'd.)" heading to more words, split into (heading, rest); else None."""
    marker = _CONTINUED.search(quote)
    if marker is None:
        return None
    rest = quote[marker.end() :].strip()
    if len(rest) < MIN_QUOTE_CHARS:
        return None
    return quote[: marker.end()], rest


def locate(quote: str, text: str) -> QuoteMatch:
    """Where the quote is on the page: an exact match after normalising, else a fuzzy match of the whole quote.

    A quote that runs on past a "(Cont'd.)" heading is found only if the words after the heading are on the page too.
    """
    match = _locate(quote, text)
    split = continuation(quote)
    if match.found and split is not None and match.status is not QuoteStatus.EXACT:
        rest = _locate(split[1], text)
        if not rest.found or (rest.offset or 0) < (match.offset or 0):
            return NOT_FOUND
    return match


def locate_across(quote: str, text: str, previous: str | None) -> QuoteMatch:
    """Where the quote is on the page; a "(Cont'd.)" quote may have its heading here and the rest on the page before."""
    match = locate(quote, text)
    split = continuation(quote)
    if match.found or split is None or previous is None:
        return match
    heading, rest = _locate(split[0], text), _locate(split[1], previous)
    if not (heading.found and rest.found):
        return NOT_FOUND
    status = QuoteStatus.EXACT if heading.status is rest.status is QuoteStatus.EXACT else QuoteStatus.FUZZY
    return QuoteMatch(status, heading.offset, min(heading.score, rest.score))


def _locate(quote: str, text: str) -> QuoteMatch:
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
    block = difflib.SequenceMatcher(None, haystack, head, autojunk=False).find_longest_match(
        0, len(haystack), 0, len(head)
    )
    if block.size < FUZZY_MIN_BLOCK:
        return NOT_FOUND
    whole = needle[:FUZZY_MAX_CHARS]
    start = max(0, block.a - block.b)
    window = haystack[start : start + len(whole)]
    ratio = difflib.SequenceMatcher(None, window, whole).ratio()
    if ratio < FUZZY_MIN_RATIO:
        return NOT_FOUND
    return QuoteMatch(QuoteStatus.FUZZY, offsets[start], round(ratio, 3))
