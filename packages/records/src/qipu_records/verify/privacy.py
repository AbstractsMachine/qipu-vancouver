"""Withhold the names of private people in sensitive matters, and nothing else.

Council minutes are public records, and most names in them belong to officials, firms and groups acting in public: they stay.
The rule protects private people where the record could hurt them: a claim for damages, an injury, an illness, welfare, an
eviction, a crime. In those items, for records younger than the city's embargo (75 years in San Francisco, 92 in Vancouver),
a private person's name is replaced by "[name withheld]" in everything published: the quote, the summary and the parties.
The decision itself, its place, amount and outcome stay visible.

Who counts as an official is read from the record: the mover and seconder, the people in its roll call, and anyone the page
names next to a role ("Ald. Linnell", "Mayor Phillips", "Supervisor Kopp"). Organisations are recognised by the words in their
names. When in doubt the name is withheld: a withheld official costs a little readability, a leaked private name cannot be
taken back.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

WITHHELD = "[name withheld]"

SENSITIVE = re.compile(
    r"\b(?:welfare|social\s+assistance|public\s+assistance|indigent|hospitali[sz]\w*|patients?|medical\s+(?:care|treatment|bills?)"
    r"|mental(?:ly)?\s+ill\w*|psychiatric|disabilit\w*|injur\w*|damages?|accidents?|collision|wrongful\s+death|death\s+of"
    r"|claims?\s+(?:of|by|for|against)|claimants?|lawsuits?|litigation|plaintiffs?|defendants?|false\s+arrest|evict\w*|nuisance"
    r"|crim\w*|arrest\w*|victims?|assault\w*|robber\w*|burglar\w*|homicide|murder\w*|probation|parole|jail|inmates?|prisoners?"
    r"|juvenile|minors|child\s+welfare|foster)\b"
    r"|(?-i:\w\s+v\.\s+[A-Z])",
    re.I,
)
SENSITIVE_KINDS = {"claim"}
SENSITIVE_ROLES = {"claimant"}

ROLE_WORDS = (
    r"Ald(?:erm[ae]n)?\.?|Mayor|Deputy\s+Mayor|Supervisors?|Councill?ors?|Councilm[ae]n|Councilwoman|Commissioners?|Director|"
    r"Clerk|Chairman|Chairperson|Chair|Engineer|Manager|Solicitor|Corporation\s+Counsel|City\s+Attorney|Controller|Treasurer|"
    r"Assessor|Comptroller|Superintendent|Chief|Inspector|Judge|Senator|M\.P\.|M\.L\.A\.|Reeve|Administrator|Secretary"
)
_NAME = r"[A-Z][a-zA-Z'’-]+"
_ROLE_THEN_NAMES = re.compile(rf"\b(?:{ROLE_WORDS})\s+((?:{_NAME}(?:,\s*|\s+and\s+|\s+)){{0,12}}{_NAME})")
_HONORIFIC_NAME = re.compile(rf"\b(?:Mr|Mrs|Ms|Miss|Messrs|Dr)\.?\s+((?:[A-Z]\.\s*){{0,3}}{_NAME}(?:\s+(?:[A-Z]\.\s*)?{_NAME})?)")
_HONORIFIC = re.compile(r"^(?:Mr|Mrs|Ms|Miss|Messrs|Dr)\.?\s+")
_ORGANISATION = re.compile(
    r"\b(?:ltd|limited|inc|incorporated|co|company|corp|corporation|society|association|council|committee|club|union|league|fund"
    r"|foundation|hospital|church|bank|board|department|city|province|government|ministry|minister|school|college|university"
    r"|trust|holdings|enterprises|industries|services|group|centre|center|theatre|theater|federation|institute|agency"
    r"|commission|authority|partners|partnership|brothers|bros|estate|cooperative|co-operative|developments?|properties"
    r"|realty|construction|contractors?|motors|hotel|press|promotions|productions)\b\.?",
    re.I,
)


@dataclass(frozen=True)
class Embargo:
    """Records from after `cutoff_year` are under the embargo."""

    years: int
    today: dt.date = field(default_factory=dt.date.today)

    @property
    def cutoff_year(self) -> int:
        return self.today.year - self.years

    def applies(self, year: int | None) -> bool:
        """Undated records are treated as recent."""
        return year is None or year > self.cutoff_year


def is_sensitive(text: str) -> bool:
    return bool(SENSITIVE.search(text))


def is_organisation(name: str) -> bool:
    """True for names of firms, groups and public bodies: a telling word, or a joining word no person's name has."""
    return bool(_ORGANISATION.search(name) or re.search(r"\s(?:of|for|the|and|&)\s", name, re.I))


def surname(name: str) -> str:
    words = [w.strip(".,") for w in _HONORIFIC.sub("", name).split()]
    words = [w for w in words if len(w) > 1]
    return words[-1].lower() if words else ""


def officials_on_page(page_text: str) -> set[str]:
    """Surnames the page prints next to a public role."""
    found: set[str] = set()
    for match in _ROLE_THEN_NAMES.finditer(page_text):
        for name in re.split(r",\s*|\s+and\s+|\s+", match.group(1)):
            if name and name[0].isupper():
                found.add(name.lower())
    return found


def officials_of_item(item: dict[str, Any]) -> set[str]:
    """Surnames of the people who moved, seconded or voted on the item."""
    names = [item.get("mover") or "", item.get("seconder") or ""]
    for key in ("ayes_names", "noes_names", "absent_names"):
        names.extend(item.get(key) or [])
    return {surname(n) for n in names if n}


def item_is_sensitive(item: dict[str, Any]) -> bool:
    text = " ".join([item.get("quote") or "", item.get("summary") or ""])
    roles = {party.get("role") for party in item.get("parties") or []}
    return item.get("kind") in SENSITIVE_KINDS or bool(roles & SENSITIVE_ROLES) or is_sensitive(text)


def private_names(item: dict[str, Any], officials: set[str]) -> set[str]:
    """Names of private people in an item: its parties and honorific names that are neither officials nor organisations."""
    candidates = [party.get("name") or "" for party in item.get("parties") or []]
    for key in ("quote", "summary"):
        candidates.extend(match.group(0) for match in _HONORIFIC_NAME.finditer(item.get(key) or ""))
    names = {re.sub(r"['’]s$", "", name.strip()) for name in candidates}
    return {
        name for name in names if name and WITHHELD not in name and not is_organisation(name) and surname(name) not in officials
    }


def name_variants(name: str) -> list[str]:
    """The ways a name may be printed, longest first: "Miss Jessie I. Hendry", "Jessie I. Hendry", "Jessie Hendry", "Hendry"."""
    bare = _HONORIFIC.sub("", name).strip()
    words = bare.split()
    variants = {name.strip(), bare}
    if len(words) >= 2:
        variants.add(f"{words[0]} {words[-1]}")
    last = words[-1].strip(".,") if words else ""
    if len(last) > 2:
        variants.add(last)
    return sorted((v for v in variants if v), key=len, reverse=True)


def mask(text: str, names: Iterable[str]) -> str:
    """Replace every printed form of the names with WITHHELD, together with any title in front of it."""
    if not text:
        return text
    variants = sorted({v for name in names for v in name_variants(name)}, key=len, reverse=True)
    for variant in variants:
        pattern = r"(?:\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+)?" + r"\s+".join(re.escape(w) for w in variant.split()) + r"(?![\w])"
        text = re.sub(r"(?<![\w])" + pattern, WITHHELD, text)
    return text


def mask_item(item: dict[str, Any], officials: set[str]) -> tuple[dict[str, Any], set[str]]:
    """The item with private people's names withheld, and the names withheld. The caller decides whether the rule applies."""
    names = private_names(item, officials | officials_of_item(item))
    if not names:
        return item, set()
    masked = dict(item)
    for key in ("quote", "summary", "why"):
        masked[key] = mask(item.get(key) or "", names)
    masked["parties"] = [
        {**party, "name": WITHHELD if party.get("name") in names else mask(party.get("name") or "", names)}
        for party in item.get("parties") or []
    ]
    masked["money"] = [{**m, "payee": mask(m.get("payee") or "", names)} for m in item.get("money") or []]
    masked["places"] = [{**p, "text": mask(p.get("text") or "", names)} for p in item.get("places") or []]
    return masked, names
