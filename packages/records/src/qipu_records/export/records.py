"""Shape one decision the model listed into the record that is published.

The checks that decide whether a record is published at all run before this, in ``pipeline``. Here the item is dated, its
outcome named, its private names withheld when the privacy rule applies, its places matched and its page linked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qipu_records.cities import City
from qipu_records.collection import Page
from qipu_records.fetch.archive import Item
from qipu_records.link.pagemap import PageMap, page_url
from qipu_records.map.gazetteer import Gazetteer
from qipu_records.read.readers import Reading
from qipu_records.verify import outcomes, privacy
from qipu_records.verify.dates import PageDates
from qipu_records.verify.quotes import QuoteMatch


@dataclass(frozen=True)
class Context:
    """What every record of a run shares."""

    city: City
    embargo: privacy.Embargo
    gazetteer: Gazetteer | None


@dataclass(frozen=True)
class PageContext:
    """What every decision on one page shares."""

    item: Item
    page: Page
    previous: Page | None
    dates: PageDates
    page_map: PageMap | None
    reading: Reading
    officials: set[str]


def _blank_to_none(value: Any) -> Any:
    return None if value == "" else value


def _vote(entry: dict[str, Any]) -> dict[str, Any] | None:
    if entry.get("ayes") is None and not entry.get("ayes_names"):
        return None
    return {
        "ayes": entry.get("ayes"),
        "noes": entry.get("noes"),
        "absent": entry.get("absent"),
        "ayes_names": entry.get("ayes_names") or [],
        "noes_names": entry.get("noes_names") or [],
        "absent_names": entry.get("absent_names") or [],
    }


def _places(entry: dict[str, Any], gazetteer: Gazetteer | None) -> list[dict[str, Any]]:
    out = []
    for place in entry.get("places") or []:
        row: dict[str, Any] = {"text": place.get("text") or "", "precision": place.get("precision")}
        location = gazetteer.locate(place) if gazetteer else None
        if location:
            row.update(lat=round(location.lat, 6), lon=round(location.lon, 6), placed_as=location.precision.value)
        out.append(row)
    return out


def _money(entry: dict[str, Any], currency: str) -> list[dict[str, Any]]:
    return [
        {
            "amount": m.get("amount"),
            "currency": currency,
            "purpose": _blank_to_none(m.get("purpose")),
            "payee": _blank_to_none(m.get("payee")),
        }
        for m in entry.get("money") or []
    ]


def _source(ctx: Context, pc: PageContext) -> dict[str, Any]:
    return {
        "item": pc.item.identifier,
        "title": pc.item.title,
        "ocr_page": pc.page.n,
        "page_url": page_url(pc.item.identifier, pc.page.n, pc.page_map),
        "item_url": pc.item.url,
        "licence": pc.item.licence,
        "archive": ctx.city.archive,
    }


def decision_record(
    ctx: Context, pc: PageContext, seq: int, entry: dict[str, Any], *, match: QuoteMatch, on_this_page: bool
) -> dict[str, Any]:
    """One published decision record."""
    date, date_source = pc.dates.at(match.offset if on_this_page else None)
    withheld: set[str] = set()
    if ctx.embargo.applies(date.year if date else None) and privacy.item_is_sensitive(entry):
        entry, withheld = privacy.mask_item(entry, pc.officials)
    stage, outcome = outcomes.stage_and_outcome(entry.get("action") or "other")
    kind, action = entry.get("kind") or "", entry.get("action") or ""
    shown = f"{entry.get('quote')} {entry.get('summary')} {entry.get('parties')}"
    return {
        "id": f"{pc.page.page_id}/{seq}",
        "city": ctx.city.key,
        "body": ctx.city.body,
        "date": date.isoformat() if date else None,
        "date_source": date_source.value,
        "kind": kind,
        "number": _blank_to_none(entry.get("number")),
        "file": _blank_to_none(entry.get("file")),
        "action": action,
        "stage": stage,
        "outcome": outcome.value,
        "amended": bool(entry.get("amended")),
        "zoning": outcomes.zoning_status(kind, action, entry.get("zoning_from") or "", entry.get("zoning_to") or ""),
        "summary": entry.get("summary") or "",
        "quote": entry.get("quote") or "",
        "quote_check": match.status.value,
        "vote": _vote(entry),
        "mover": _blank_to_none(entry.get("mover")),
        "seconder": _blank_to_none(entry.get("seconder")),
        "money": _money(entry, ctx.city.currency),
        "parties": [{"name": p.get("name"), "role": p.get("role")} for p in entry.get("parties") or []],
        "places": _places(entry, ctx.gazetteer),
        "topics": entry.get("topics") or [],
        "names_withheld": bool(withheld) or privacy.WITHHELD in shown,
        "source": _source(ctx, pc),
        "reading": {"model": pc.reading.model, "prompt_version": pc.reading.prompt_version},
    }
