"""Two privacy gates, both on the published text: no leak, and no over-redaction.

The rule (qipu-records' verify.privacy): in a record younger than the city's embargo, about a sensitive matter, the name of a
private person is replaced by "[name withheld]". Nothing else is hidden: not the page, not the decision, not officials,
firms, places or the record's source.

Leak: in every sensitive record under the embargo, the rule finds no private name still shown. The topic is read again from
the published text rather than trusted from the extractor.

Over-redaction: a mask fails when it is in a record that is not sensitive or is older than the embargo; in the record's
source, date, action or outcome, or on a mover, seconder or voter (officials); right after an official title, a delegation
or petitioner word, or a contract award; or right before a word that makes the name a firm, an organisation, a place or a
role. A payee is not on the list: in a damage claim the payee is the claimant, whom the rule withholds.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterator
from typing import Any, cast

from qipu_records.read.schema import ModelItem
from qipu_records.verify.privacy import (
    ROLE_WORDS,
    WITHHELD,
    Embargo,
    item_is_sensitive,
    officials_of_item,
    officials_on_page,
    private_names,
)
from qipu_updates.gates import Finding, GateResult, PageTexts, page_id_of

MASKABLE = ("quote", "summary")
NEVER_MASKED = (
    "id",
    "body",
    "date",
    "kind",
    "number",
    "file",
    "action",
    "stage",
    "outcome",
    "mover",
    "seconder",
    "source",
    "vote",
)

KEEP_BEFORE = re.compile(
    rf"(?:\b(?:{ROLE_WORDS})|\bdelegations?|\bspeakers?|\bpetition(?:ers?)?\s+(?:from|of|by)|\bsubmitted\s+by|\bon\s+behalf\s+of"
    r"|\brepresenting|\bcontract(?:\s+awarded)?\s+to|\bin\s+honou?r\s+of|\bnamed\s+(?:after|for)"
    r"|\bmemorial\s+to|\bFreedom\s+of\s+the\s+City)\W{0,4}$",
    re.I,
)
KEEP_AFTER = re.compile(
    r"^\W{0,3}(?:the\s+)?(?:Ltd|Limited|Inc|Incorporated|Corp|Corporation|Company|Co\b|Society|Association|Foundation|Holdings"
    r"|Enterprises|Investments|Developments|Properties|Construction|Contracting|Club|Church|Hospital|Centre|Center|Council|Union"
    r"|Board|Bank|Hotel|Restaurant|Architects|Engineers|Consultants|Partnership|& Sons|Bros|Street|St\b|Avenue|Ave\b|Road|Rd\b"
    r"|Drive|Park|Bridge|Building|School|Hall|Square|Way|Crescent|Place|Boulevard|Lane|Day|Award)\b"
)


def _year(record: dict[str, Any]) -> int | None:
    date = str(record.get("date") or "")
    return int(date[:4]) if date[:4].isdigit() else None


def _as_item(record: dict[str, Any]) -> ModelItem:
    """The record in the shape qipu-records' privacy rule reads (a model item): vote names at the top level."""
    return cast(ModelItem, {**record, **(record.get("vote") or {})})


def _masked_texts(record: dict[str, Any]) -> Iterator[tuple[str, str]]:
    for name in MASKABLE:
        yield name, str(record.get(name) or "")
    for n, party in enumerate(record.get("parties") or []):
        yield f"parties[{n}]", str(party.get("name") or "")
    for n, place in enumerate(record.get("places") or []):
        yield f"places[{n}]", str(place.get("text") or "")
    for n, money in enumerate(record.get("money") or []):
        yield f"money[{n}]", str(money.get("payee") or "")


def _context(text: str, at: int) -> str:
    return text[max(0, at - 60) : at + len(WITHHELD) + 60]


def leaks(records: list[dict[str, Any]], pages: PageTexts, as_of: dt.date, embargo_years: int, limit: int = 0) -> GateResult:
    result = GateResult("privacy_leak", limit=limit)
    embargo = Embargo(embargo_years, today=as_of)
    for record in records:
        item = _as_item(record)
        if not embargo.applies(_year(record)) or not item_is_sensitive(item):
            continue
        page = pages.text(page_id_of(record))
        if page is None:
            result.skipped += 1
            continue
        result.checked += 1
        for name in sorted(private_names(item, officials_on_page(page) | officials_of_item(item))):
            result.findings.append(Finding(str(record["id"]), "private name shown in a sensitive record", name))
    return result


def _over(record: dict[str, Any], text: str, at: int, embargo: Embargo) -> str | None:
    if not embargo.applies(_year(record)):
        return f"mask in an open record (year {_year(record)} is not after {embargo.cutoff_year})"
    if not item_is_sensitive(_as_item(record)):
        return "mask in a record that is not a sensitive matter"
    if KEEP_BEFORE.search(text[max(0, at - 60) : at]):
        return "mask right after an official title, a delegation or a contract award"
    if KEEP_AFTER.match(text[at + len(WITHHELD) : at + len(WITHHELD) + 80]):
        return "mask right before a firm, organisation, place or role word"
    return None


def over_redaction(records: list[dict[str, Any]], as_of: dt.date, embargo_years: int, limit: int = 0) -> GateResult:
    result = GateResult("over_redaction", limit=limit)
    embargo = Embargo(embargo_years, today=as_of)
    for record in records:
        result.checked += 1
        rid = str(record["id"])
        for name in NEVER_MASKED:
            if WITHHELD in str(record.get(name) or ""):
                result.findings.append(Finding(rid, f"mask in {name}", str(record.get(name))[:120]))
        for name, text in _masked_texts(record):
            for match in re.finditer(re.escape(WITHHELD), text):
                why = _over(record, text, match.start(), embargo)
                if why:
                    result.findings.append(Finding(rid, f"{why} ({name})", _context(text, match.start())))
    return result
