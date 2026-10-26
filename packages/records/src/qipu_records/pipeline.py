"""Run the checks over a collection and write the published records.

Everything here is deterministic: the same pages, readings and gazetteer give the same records on the same day. (The
privacy embargo counts back from today, so a record can come out of it as years pass.) An item the model listed is
published only if its quote is found on the page (or on the previous page, when the item's heading starts there);
otherwise it goes to rejected.jsonl. Published items are shaped into records by ``export.records``.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TypedDict

from qipu_records.collection import Collection, Page, write_json, write_jsonl
from qipu_records.export.geojson import feature_collection
from qipu_records.export.records import Context, DecisionRecord, PageContext, decision_record
from qipu_records.fetch.archive import Item
from qipu_records.read.schema import ModelItem
from qipu_records.verify import privacy, quotes
from qipu_records.verify.dates import date_pages


class Rejected(TypedDict):
    id: str
    reason: str
    quote: str | None


@dataclass
class Summary:
    pages: int = 0
    pages_read: int = 0
    decisions: int = 0
    rejected: int = 0
    counts: Counter[str] = field(default_factory=Counter)

    def as_dict(self) -> dict[str, int]:
        return {
            "pages": self.pages,
            "pages_read": self.pages_read,
            "decisions": self.decisions,
            "rejected": self.rejected,
            **dict(sorted(self.counts.items())),
        }


def _item_date(item: Item) -> dt.date | None:
    try:
        return dt.date.fromisoformat((item.date or "")[:10])
    except ValueError:
        return None


def _find_quote(entry: ModelItem, page: Page, previous: Page | None) -> tuple[quotes.QuoteMatch, bool]:
    """Where the item's quote is, on this page or the previous one, and whether it was found on this page."""
    quote = entry.get("quote") or ""
    order = [(previous, False), (page, True)] if entry.get("heading_on_prev") else [(page, True), (previous, False)]
    for candidate, on_this_page in order:
        if candidate is not None:
            match = quotes.locate(quote, candidate.text)
            if match.found:
                return match, on_this_page
    return quotes.NOT_FOUND, True


def _pages_by_item(pages: list[Page]) -> dict[str, list[Page]]:
    grouped: dict[str, list[Page]] = defaultdict(list)
    for page in pages:
        grouped[page.item].append(page)
    return grouped


def _page_contexts(collection: Collection) -> Iterator[PageContext | Page]:
    """A context for every page that was read; pages not read are yielded bare, to be counted."""
    items, readings, maps = collection.items(), collection.readings(), collection.page_maps()
    for identifier, pages in _pages_by_item(collection.pages()).items():
        item = items[identifier]
        dates = date_pages([p.text for p in pages], _item_date(item))
        for index, page in enumerate(pages):
            reading = readings.get(page.page_id)
            if reading is None:
                yield page
                continue
            previous = pages[index - 1] if index and pages[index - 1].n == page.n - 1 else None
            officials = privacy.officials_on_page(page.text)
            yield PageContext(item, page, previous, dates[index], maps.get(identifier), reading, officials)


def build_records(ctx: Context, collection: Collection) -> tuple[list[DecisionRecord], list[Rejected], Summary]:
    """All decision records of a collection, the items rejected, and the counts."""
    summary = Summary()
    records: list[DecisionRecord] = []
    rejected: list[Rejected] = []
    for pc in _page_contexts(collection):
        summary.pages += 1
        if isinstance(pc, Page):
            continue
        summary.pages_read += 1
        for seq, entry in enumerate(pc.reading.items, start=1):
            match, on_this_page = _find_quote(entry, pc.page, pc.previous)
            if not match.found:
                rejected.append(_rejected(ctx, pc, seq, entry))
                continue
            record = decision_record(ctx, pc, seq, entry, match=match, on_this_page=on_this_page)
            records.append(record)
            _count(summary.counts, record)
    summary.decisions, summary.rejected = len(records), len(rejected)
    return records, rejected, summary


def _rejected(ctx: Context, pc: PageContext, seq: int, entry: ModelItem) -> Rejected:
    """The rejected item as written to rejected.jsonl, under the same privacy rule as a published record."""
    date, _ = pc.dates.at(None)
    if ctx.embargo.applies(date.year if date else None) and privacy.item_is_sensitive(entry):
        entry, _ = privacy.mask_item(entry, pc.officials)
    return {"id": f"{pc.page.page_id}/{seq}", "reason": "quote not found on the page", "quote": entry.get("quote")}


def _count(counts: Counter[str], record: DecisionRecord) -> None:
    counts[f"quote_{record['quote_check']}"] += 1
    counts["linked_to_page"] += record["source"]["page_url"] is not None
    counts["dated"] += record["date"] is not None
    counts["placed"] += any("lat" in place for place in record["places"])
    counts["with_names_withheld"] += record["names_withheld"]


def build(ctx: Context, collection: Collection) -> Summary:
    """Write decisions.jsonl, rejected.jsonl, decisions.geojson and summary.json into the collection folder."""
    records, rejected, summary = build_records(ctx, collection)
    write_jsonl(collection.path("decisions.jsonl"), records)
    write_jsonl(collection.path("rejected.jsonl"), rejected)
    write_json(collection.path("decisions.geojson"), feature_collection(records))
    write_json(collection.path("summary.json"), summary.as_dict())
    return summary
