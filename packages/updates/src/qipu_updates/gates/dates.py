"""Date from header: a record's date is the meeting date its page prints, read again from the pages of its document.

Minutes print the meeting date in a running head or in the opening line of each meeting ("A Regular meeting of the
Council ... was held on Tuesday, February 19, 1974"). The date is read again here with qipu-records' date reader and
compared with the published one. A mismatch means the record was dated some other way, for example by an older date
reader in a record carried over from an earlier release.

A second, independent check: the published date must be a day the item shows a meeting being held (an opening line, a
council running head, or the item's catalogue date). The date of a report bound into the minutes is the day it was
written, not a meeting, so a record dated by it fails here even if the page reader were to agree with it.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any

from qipu_records.verify.dates import date_pages, item_meetings
from qipu_records.verify.quotes import locate
from qipu_updates.gates import Finding, GateResult, PageTexts
from qipu_updates.gates.quotes import pieces


def _date(text: str | None) -> dt.date | None:
    try:
        return dt.date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def check(records: list[dict[str, Any]], pages: PageTexts, limit: int = 0) -> GateResult:
    """Fail a record whose date is not the one the minutes' own header gives for its document."""
    result = GateResult("date_from_header", limit=limit)
    by_doc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_doc[str(record["source"]["item"])].append(record)
    for doc_id, doc_records in sorted(by_doc.items()):
        document = pages.document(doc_id)
        if document is None:
            result.skipped += len(doc_records)
            continue
        texts, item_date = document
        dates = date_pages(texts, _date(item_date))
        held = {meeting.isoformat() for meeting in item_meetings(texts, _date(item_date))}
        for record in doc_records:
            result.checked += 1
            n = int(record["source"]["ocr_page"])
            parts = pieces(str(record.get("quote") or ""))
            match = locate(parts[0], texts[n]) if parts and 0 <= n < len(texts) else None
            expected, _ = (
                dates[n].at(match.offset if match and match.found else None) if 0 <= n < len(dates) else (None, None)
            )
            published = record.get("date")
            if not published:
                result.findings.append(Finding(str(record["id"]), "no date"))
            elif expected is None or expected.isoformat() != published:
                why = f"published {published}, the page gives {expected.isoformat() if expected else 'no date'}"
                result.findings.append(Finding(str(record["id"]), why))
            elif held and published not in held:
                shows = ", ".join(sorted(held))
                why = f"published {published}, but the item shows no meeting held that day (it shows {shows})"
                result.findings.append(Finding(str(record["id"]), why))
    return result
