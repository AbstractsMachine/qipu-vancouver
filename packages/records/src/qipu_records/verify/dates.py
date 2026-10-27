"""The meeting date of each decision, read from the minutes themselves.

A decision is dated by the meeting it was taken at, never by the year on the volume's cover: a volume can run across a
new year, and one page can close one meeting and open the next. Dates come from three places, in this order:

* a meeting that opens on the page ("A Regular meeting of the Council ... was held on Tuesday, February 19, 1974", "In
  Board of Supervisors, Monday, February 4th, 1907") dates everything printed after the opening;
* the running head at the top of the page ("Regular Council, February 19, 1974", "MONDAY, JANUARY 21, 1924") dates the
  page;
* a page without either carries the meeting in progress from the page before.

The Vancouver scans also carry a clerk's date stamp at the top ("JUN 9 1970"). On a report bound into the minutes
("Board of Administration, June 5, 1970") the stamp names the council meeting it came to, so it dates the page. It never
overrides the head of a council meeting, and a stamp alone never overrides the meeting in progress: on scan page 21 of
CVAN_1967-05-30 a "JUN 14 1967" stamp sits over the garbled head of the June 1 meeting.

A printed weekday must agree with the date. When OCR has garbled a digit ("Monday, July 21, 1989" for the 24th) the line
dates nothing, which is better than a wrong date. Dates of other events mentioned in the text ("adjourned to meet on
Monday, February 18") sit in the body of the page and are not mistaken for headers.

In a random sample of published facts, wrong dates were the most common flaw before this rule; see docs/accuracy.md.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
WEEKDAYS = {"mon": 0, "tues": 1, "wednes": 2, "thurs": 3, "fri": 4, "satur": 5, "sun": 6}

HEADER_ZONE = 200
"""Characters at the top of a page where a running head may sit."""

_WEEKDAY = r"(?:(mon|tues|wednes|thurs|fri|satur|sun)day\W{1,4})?"
_MONTH = r"(jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)"
_DAY = r"(\d{1,2})\s?(?:st|nd|rd|th|d)?"
_YEAR = r"((?:18|19|20)[\dOo]{2})"
DATE_LINE = re.compile(_WEEKDAY + _MONTH + r"\.?\s{0,3}" + _DAY + r"\s{0,3},?\s{0,3}" + _YEAR, re.I)

_OPENING_WORDS = re.compile(
    r"(?:meeting\s+of\s+the\s+(?:council|board)[^.]{0,80}?\s+(?:was\s+)?held\s+(?:on\s+)?"
    r"|in\s+(?:the\s+)?board\s+of\s+supervisors\W{1,30}"
    r"|journal\s+of\s+proceed\w*.{0,60})$",
    re.I,
)
OPENING_LOOKBEHIND = 140


class DateSource(StrEnum):
    MEETING_OPENS = "meeting opens on the page"
    RUNNING_HEAD = "running head"
    CARRIED = "carried from the meeting in progress"
    ITEM = "archive.org item date"
    NONE = "none"


@dataclass(frozen=True)
class PageDates:
    """The meeting in progress at the top of a page, and the meetings that open further down it."""

    at_start: dt.date | None
    source: DateSource
    openings: tuple[tuple[int, dt.date], ...] = ()

    def at(self, offset: int | None) -> tuple[dt.date | None, DateSource]:
        """The meeting date of something printed at character `offset` of the page."""
        date, source = self.at_start, self.source
        for position, opened in self.openings:
            if offset is not None and position <= offset:
                date, source = opened, DateSource.MEETING_OPENS
        return date, source


def _year(text: str) -> int:
    return int(text.replace("O", "0").replace("o", "0"))


def parse_date(match: re.Match[str]) -> dt.date | None:
    """The date a DATE_LINE match prints, or None when it is impossible or its weekday disagrees."""
    weekday, month, day, year = match.groups()
    try:
        date = dt.date(_year(year), MONTHS.index(month[:3].lower()) + 1, int(day))
    except ValueError:
        return None
    if weekday and WEEKDAYS[weekday.lower()] != date.weekday():
        return None
    return date


# "JUN 14 1967": a three-letter month in capitals and no comma before the year, as the clerk's stamp prints it.
_STAMP = re.compile(r"[A-Z]{3}\.?\s{0,3}\d{1,2}\s{1,3}(?:18|19|20)[\dOo]{2}")
_REPORT_HEAD = re.compile(r"board\s+of\s+admin|report", re.I)


@dataclass(frozen=True)
class _Head:
    date: dt.date
    report: bool
    """the head of a report bound into the minutes, whose date is the report's, not the meeting's"""


def _heads(text: str) -> tuple[_Head | None, dt.date | None]:
    """The first running head at the top of a page and the first date stamp, either None where there is none."""
    zone = text[:HEADER_ZONE]
    head: _Head | None = None
    stamp: dt.date | None = None
    for match in DATE_LINE.finditer(zone):
        date = parse_date(match)
        if date is None:
            continue
        if _STAMP.fullmatch(match.group(0)):
            stamp = stamp or date
        elif head is None:
            before = _STAMP.sub(" ", zone[: match.start()])
            head = _Head(date, bool(_REPORT_HEAD.search(before)))
    return head, stamp


def running_head(text: str) -> dt.date | None:
    """The date in the running head at the top of a page, if there is one. A date stamp is not a running head."""
    head, _ = _heads(text)
    return head.date if head else None


def _page_date(text: str, meeting_in_progress: bool) -> dt.date | None:
    head, stamp = _heads(text)
    if head is not None and not head.report:
        return head.date
    if stamp is not None and (head is not None or not meeting_in_progress):
        return stamp
    return head.date if head else None


def meeting_openings(text: str) -> list[tuple[int, dt.date]]:
    """(offset, date) of every meeting that opens on the page, in page order."""
    found: list[tuple[int, dt.date]] = []
    for match in DATE_LINE.finditer(text):
        before = " ".join(text[max(0, match.start() - OPENING_LOOKBEHIND) : match.start()].split()) + " "
        if not _OPENING_WORDS.search(before):
            continue
        date = parse_date(match)
        if date is not None and date not in (seen for _, seen in found):
            found.append((match.start(), date))
    return found


def date_pages(texts: Sequence[str], item_date: dt.date | None = None) -> list[PageDates]:
    """Date every page of one archive.org item, in scan order.

    Pages before the first header or opening fall back to the item's catalogue date, when it has one.
    """
    in_progress = item_date
    read_from_pages = False
    out: list[PageDates] = []
    for text in texts:
        openings = tuple(meeting_openings(text))
        head = _page_date(text, read_from_pages)
        if openings and openings[0][0] < HEADER_ZONE:
            out.append(PageDates(openings[0][1], DateSource.MEETING_OPENS, openings))
        elif head is not None:
            out.append(PageDates(head, DateSource.RUNNING_HEAD, openings))
        elif in_progress is None:
            out.append(PageDates(None, DateSource.NONE, openings))
        else:
            out.append(PageDates(in_progress, DateSource.CARRIED if read_from_pages else DateSource.ITEM, openings))
        if openings or head is not None:
            in_progress = openings[-1][1] if openings else head
            read_from_pages = True
    return out
