"""A Legistar calendar: San Francisco's Board of Supervisors and its committees (sfgov.legistar.com).

The calendar page lists each meeting with links to its agenda and, once approved, its minutes (a PDF). Only meetings with
minutes are documents here: minutes record what was decided. The month shown is chosen with a cookie, as the site's own
filter does. A document's fingerprint is the sha256 of its minutes PDF, so a corrected PDF is processed again; this means
`discover` downloads every posted minutes PDF in the window (a few dozen a month, one request at a time). The calendar
shows two months, so the listing is a window (`complete = False`). Page texts come from `pdftotext -layout`, one string per
PDF page.

The calendar parser is the one behind qipu's San Francisco agenda pages.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import re
import subprocess
import tempfile
from collections.abc import Callable
from typing import Any

from qipu_records.fetch.archive import Item
from qipu_updates.sources import Content, Document, SourceError
from qipu_updates.sources.http import Polite

SF_BASE = "https://sfgov.legistar.com/"
CALENDAR_COOKIE = "Setting-60-Calendar Year={}; Setting-60-Calendar Body=All; Setting-60-Calendar Options=info|"
_ROW = re.compile(r'<tr[^>]*class="rg(?:Alt)?Row"[^>]*>(.*?)</tr>', re.S)
_CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_HREF = re.compile(r'href="([^"]+)"')
_MDY = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*$")
_IDS = re.compile(r"ID=(\d+)&(?:amp;)?GUID=([0-9A-Fa-f-]+)")

PdfToText = Callable[[bytes], list[str]]


def visible_text(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).replace("\xa0", " ").strip()


def mdy(text: str) -> str | None:
    """'10/27/2026' or '9/29/26' as '2026-10-27'."""
    match = _MDY.match(text)
    if not match:
        return None
    year = int(match.group(3))
    return dt.date(year + 2000 if year < 100 else year, int(match.group(1)), int(match.group(2))).isoformat()


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_calendar(page: str, base: str = SF_BASE) -> list[dict[str, Any]]:
    """Each meeting on a calendar page: body, date, meeting id, and its minutes link when posted."""
    meetings = []
    for row in _ROW.findall(page):
        cells = _CELL.findall(row)
        date = mdy(visible_text(cells[1])) if len(cells) >= 7 else None
        if not date:
            continue
        links = [html.unescape(h) for h in _HREF.findall(row)]
        links = [u if u.startswith("http") else base + u.lstrip("/") for u in links]
        minutes = next((u for u in links if "M=M&" in u), None)
        ids = next((m for m in (_IDS.search(u) for u in links) if m), None)
        meetings.append(
            {"body": visible_text(cells[0]), "date": date, "meeting_id": ids.group(1) if ids else None, "minutes_url": minutes}
        )
    return meetings


def pdftotext(data: bytes) -> list[str]:
    with tempfile.NamedTemporaryFile(suffix=".pdf") as pdf:
        pdf.write(data)
        pdf.flush()
        out = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", pdf.name, "-"], capture_output=True, check=True).stdout
    pages = out.decode("utf-8", errors="replace").split("\f")
    return pages[:-1] if pages and not pages[-1].strip() else pages


class LegistarSource:
    complete = False

    def __init__(
        self,
        base: str = SF_BASE,
        months: tuple[str, ...] = ("Last Month", "This Month"),
        http: Polite | None = None,
        to_text: PdfToText = pdftotext,
    ) -> None:
        self.base, self.months = base, months
        self.http = http or Polite(pause=1.5)
        self.to_text = to_text
        self._pdfs: dict[str, bytes] = {}
        self._meetings: dict[str, dict[str, Any]] = {}

    def discover(self, as_of: dt.date) -> list[Document]:
        """Meetings held on or before `as_of` whose minutes are posted."""
        found: dict[str, Document] = {}
        for month in self.months:
            page = self.http.get(self.base + "Calendar.aspx", {"Cookie": CALENDAR_COOKIE.format(month)})
            for meeting in parse_calendar(page.decode("utf-8", errors="replace"), self.base):
                url = meeting["minutes_url"]
                if not url or not meeting["meeting_id"] or meeting["date"] > as_of.isoformat():
                    continue
                doc_id = f"{meeting['date']}-{slug(meeting['body'])}-{meeting['meeting_id']}"
                if doc_id in found:
                    continue
                pdf = self.http.get(url)
                if pdf[:5] != b"%PDF-":
                    raise SourceError(f"{url}: not a PDF")
                self._pdfs[doc_id], self._meetings[doc_id] = pdf, meeting
                found[doc_id] = Document(doc_id, meeting["date"], hashlib.sha256(pdf).hexdigest(), url)
        return sorted(found.values(), key=lambda d: d.doc_id)

    def content(self, doc: Document) -> Content:
        pdf = self._pdfs.get(doc.doc_id) or self.http.get(doc.url)
        meeting = self._meetings.get(doc.doc_id, {"body": "", "date": doc.date})
        title = f"{meeting['body']}, minutes of {meeting['date']}".strip(", ")
        item = Item(doc.doc_id, title, doc.date, None, "Public record", meeting["body"] or None)
        return Content(item, self.to_text(pdf), None)
