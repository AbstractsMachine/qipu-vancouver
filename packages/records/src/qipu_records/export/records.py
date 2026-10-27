"""Shape one decision the model listed into the record that is published.

The checks that decide whether a record is published at all run before this, in ``pipeline``. Here the item is dated,
its outcome named, its private names withheld when the privacy rule applies, its places matched and its page linked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, TypedDict

from qipu_records.cities import City
from qipu_records.collection import Page
from qipu_records.fetch.archive import Item
from qipu_records.link.pagemap import PageMap, page_url
from qipu_records.map.gazetteer import Gazetteer
from qipu_records.read.readers import Reading
from qipu_records.read.schema import ModelItem
from qipu_records.verify import outcomes, privacy
from qipu_records.verify.dates import PageDates
from qipu_records.verify.fields import check_fields
from qipu_records.verify.quotes import QuoteMatch


class Vote(TypedDict):
    ayes: int | None
    noes: int | None
    absent: int | None
    ayes_names: list[str]
    noes_names: list[str]
    absent_names: list[str]


class Money(TypedDict):
    amount: float | None
    currency: str
    purpose: str | None
    payee: str | None


class Party(TypedDict):
    name: str | None
    role: str | None


class Place(TypedDict):
    text: str
    precision: str | None
    lat: NotRequired[float]
    lon: NotRequired[float]
    placed_as: NotRequired[str]


class Source(TypedDict):
    item: str
    title: str
    ocr_page: int
    page_url: str | None
    item_url: str
    licence: str | None
    archive: str


class ReadBy(TypedDict):
    model: str
    prompt_version: str


class FieldCheck(TypedDict):
    field: str
    result: str
    why: str
    was: NotRequired[object]


class DecisionRecord(TypedDict):
    """One published decision. docs/data-model.md describes each field."""

    id: str
    city: str
    body: str
    date: str | None
    date_source: str
    kind: str
    number: str | None
    file: str | None
    action: str
    stage: str | None
    outcome: str
    amended: bool
    zoning: str | None
    summary: str
    quote: str
    quote_check: str
    vote: Vote | None
    mover: str | None
    seconder: str | None
    money: list[Money]
    parties: list[Party]
    places: list[Place]
    topics: list[str]
    names_withheld: bool
    checks: list[FieldCheck]
    source: Source
    reading: ReadBy


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


def _blank_to_none(value: str | None) -> str | None:
    return value or None


def _vote(entry: ModelItem) -> Vote | None:
    counts = (entry.get("ayes"), entry.get("noes"), entry.get("absent"))
    names = (entry.get("ayes_names"), entry.get("noes_names"), entry.get("absent_names"))
    if all(c is None for c in counts) and not any(names):
        return None
    return {
        "ayes": entry.get("ayes"),
        "noes": entry.get("noes"),
        "absent": entry.get("absent"),
        "ayes_names": entry.get("ayes_names") or [],
        "noes_names": entry.get("noes_names") or [],
        "absent_names": entry.get("absent_names") or [],
    }


def _places(entry: ModelItem, gazetteer: Gazetteer | None) -> list[Place]:
    out: list[Place] = []
    for place in entry.get("places") or []:
        row: Place = {"text": place.get("text") or "", "precision": place.get("precision")}
        location = gazetteer.locate(place) if gazetteer else None
        if location:
            row["lat"], row["lon"] = round(location.lat, 6), round(location.lon, 6)
            row["placed_as"] = location.precision.value
        out.append(row)
    return out


def _money(entry: ModelItem, currency: str) -> list[Money]:
    return [
        {
            "amount": m.get("amount"),
            "currency": currency,
            "purpose": _blank_to_none(m.get("purpose")),
            "payee": _blank_to_none(m.get("payee")),
        }
        for m in entry.get("money") or []
    ]


def _source(ctx: Context, pc: PageContext) -> Source:
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
    ctx: Context,
    pc: PageContext,
    seq: int,
    entry: ModelItem,
    *,
    match: QuoteMatch,
    on_this_page: bool,
    span: str | None = None,
) -> DecisionRecord:
    """One published decision record. `span` is the item's text on the page; its model fields are checked against it."""
    date, date_source = pc.dates.at(match.offset if on_this_page else None)
    withheld: set[str] = set()
    if ctx.embargo.applies(date.year if date else None) and privacy.item_is_sensitive(entry):
        entry, withheld = privacy.mask_item(entry, pc.officials)
    stage, outcome = outcomes.stage_and_outcome(entry.get("action") or "other")
    kind, action = entry.get("kind") or "", entry.get("action") or ""
    shown = f"{entry.get('quote')} {entry.get('summary')} {entry.get('parties')}"
    fields = check_fields(
        span if span is not None else pc.page.text,
        pc.page.text if on_this_page or pc.previous is None else f"{pc.previous.text}\n{pc.page.text}",
        date,
        outcome=outcome.value,
        amended=bool(entry.get("amended")),
        vote=dict(_vote(entry) or {}) or None,
        summary=entry.get("summary") or "",
    )
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
        "outcome": fields.outcome,
        "amended": fields.amended,
        "zoning": outcomes.zoning_status(kind, action, entry.get("zoning_from") or "", entry.get("zoning_to") or ""),
        "summary": entry.get("summary") or "",
        "quote": entry.get("quote") or "",
        "quote_check": match.status.value,
        "vote": fields.vote,  # type: ignore[typeddict-item]
        "mover": _blank_to_none(entry.get("mover")),
        "seconder": _blank_to_none(entry.get("seconder")),
        "money": _money(entry, ctx.city.currency),
        "parties": [{"name": p.get("name"), "role": p.get("role")} for p in entry.get("parties") or []],
        "places": _places(entry, ctx.gazetteer),
        "topics": entry.get("topics") or [],
        "names_withheld": bool(withheld) or privacy.WITHHELD in shown,
        "checks": [check.as_dict() for check in fields.checks],  # type: ignore[misc]
        "source": _source(ctx, pc),
        "reading": {"model": pc.reading.model, "prompt_version": pc.reading.prompt_version},
    }
