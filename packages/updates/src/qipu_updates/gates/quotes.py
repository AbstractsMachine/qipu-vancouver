"""Quote on page: every published record's quote is printed on its page (or the page before, where its heading starts).

A quote with a withheld name is checked piece by piece around the mask.
"""

from __future__ import annotations

from typing import Any

from qipu_records.verify.privacy import WITHHELD
from qipu_records.verify.quotes import locate
from qipu_updates.gates import Finding, GateResult, PageTexts, page_id_of, previous_page_id

MIN_PIECE = 12


def pieces(quote: str) -> list[str]:
    """The parts of a quote to look for: the whole of it, or the runs of text between masks long enough to be
    telling.
    """
    if WITHHELD not in quote:
        return [quote.strip()] if quote.strip() else []
    return [p.strip(" ,.;:") for p in quote.split(WITHHELD) if len(p.strip(" ,.;:")) >= MIN_PIECE]


def on_page(piece: str, page: str, previous: str | None) -> bool:
    return locate(piece, page).found or (previous is not None and locate(piece, previous).found)


def check(records: list[dict[str, Any]], pages: PageTexts, limit: int = 0) -> GateResult:
    result = GateResult("quote_on_page", limit=limit)
    for record in records:
        page_id = page_id_of(record)
        page = pages.text(page_id)
        if page is None:
            result.skipped += 1
            continue
        result.checked += 1
        quote = str(record.get("quote") or "")
        parts = pieces(quote)
        if not parts:
            result.findings.append(Finding(str(record["id"]), "no quote to check", quote[:120]))
            continue
        previous = pages.text(previous_page_id(page_id))
        missing = [p for p in parts if not on_page(p, page, previous)]
        if missing:
            result.findings.append(Finding(str(record["id"]), "quote not found on its page", missing[0][:120]))
    return result
