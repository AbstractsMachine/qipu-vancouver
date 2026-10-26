"""Withhold the names of private people in sensitive matters, and nothing else.

Council minutes are public records, and most names in them belong to officials, firms and groups acting in public: they
stay. The rule protects private people where the record could hurt them: a claim for damages, an injury, an illness,
welfare, an eviction, a crime. In those items, for records younger than the city's embargo (75 years in San Francisco,
92 in Vancouver), a private person's name is replaced by "[name withheld]" in everything published: the quote, the
summary and the parties. The decision itself, its place, amount and outcome stay visible.

Who counts as an official is read from the record: the mover and seconder, the people in its roll call, and anyone the
page names next to a role ("Ald. Linnell", "Mayor Phillips", "Supervisor Kopp"). Organisations are recognised by the
words in their names. When in doubt the name is withheld: a withheld official costs a little readability, a leaked
private name cannot be taken back.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from qipu_records.read.schema import ModelItem

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
_HONORIFIC_NAME = re.compile(
    rf"\b(?:Mr|Mrs|Ms|Miss|Messrs|Dr)\.?\s+((?:[A-Z]\.\s*){{0,3}}{_NAME}(?:\s+(?:[A-Z]\.\s*)?{_NAME})?)"
)
_AFTER_ROLE = re.compile(rf"\b(?:{ROLE_WORDS})\s*$")
_HONORIFIC = re.compile(r"^(?:Mr|Mrs|Ms|Miss|Messrs|Dr)\.?\s+")
_ORGANISATION = re.compile(
    r"\b(?:ltd|limited|inc|incorporated|co|company|corp|corporation|society|association|council|committee|club|union|league|fund"
    r"|foundation|hospital|church|bank|board|department|city|province|government|ministry|minister|school|college|university"
    r"|trust|holdings|enterprises|industries|services|group|centre|center|theatre|theater|federation|institute|agency"
    r"|commission|authority|partners|partnership|brothers|bros|estate|cooperative|co-operative|developments?|properties"
    r"|realty|construction|contractors?|motors|hotel|press|promotions|productions|sons)\b\.?",
    re.I,
)
_ESTATE_OF = re.compile(r"^(?:the\s+)?estate\s+of\s+(?:the\s+late\s+)?", re.I)
_JOINED = re.compile(r"\s*(?:\band\b|&)\s*", re.I)
_TITLE_ONLY = re.compile(r"^(?:Mr|Mrs|Ms|Miss|Messrs|Dr)\.?$")


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
    """True for names of firms, groups and public bodies: a telling word, or a joining word no person's name has.

    "Estate of John Smith" and "John and Mary Smith" are people, not organisations: see `people_in`.
    """
    if _ESTATE_OF.match(name):
        return False
    return bool(_ORGANISATION.search(name) or re.search(r"\s(?:of|for|the)\s", name, re.I))


def people_in(name: str) -> list[str]:
    """The private people a printed name stands for: none for an organisation, both people of a couple, the person
    behind "Estate of the late John Smith"."""
    bare = _ESTATE_OF.sub("", name.strip())
    if not bare or is_organisation(bare):
        return []
    parts = [part.strip(" ,") for part in _JOINED.split(bare)]
    return [part for part in parts if part and not _TITLE_ONLY.match(part)]


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


def officials_of_item(item: ModelItem) -> set[str]:
    """Surnames of the people who moved, seconded or voted on the item."""
    names = [item.get("mover") or "", item.get("seconder") or ""]
    names += item.get("ayes_names") or []
    names += item.get("noes_names") or []
    names += item.get("absent_names") or []
    return {surname(n) for n in names if n}


def item_is_sensitive(item: ModelItem) -> bool:
    text = " ".join([item.get("quote") or "", item.get("summary") or ""])
    roles = {party.get("role") for party in item.get("parties") or []}
    return item.get("kind") in SENSITIVE_KINDS or bool(roles & SENSITIVE_ROLES) or is_sensitive(text)


def private_names(item: ModelItem, officials: set[str]) -> set[str]:
    """Names of private people in an item, as printed, for `mask` to withhold.

    Candidates are the item's parties, the payees of its amounts, and every name after an honorific in its text. A name
    is kept when it belongs to an organisation or to an official, except that a claimant is never taken for an official
    just because an alderman on the page shares the surname.
    """
    parties = item.get("parties") or []
    candidates = [party.get("name") or "" for party in parties]
    candidates += [money.get("payee") or "" for money in item.get("money") or []]
    texts = [item.get("quote"), item.get("summary"), item.get("why")] + [
        p.get("text") for p in item.get("places") or []
    ]
    for text in texts:
        candidates.extend(match.group(0) for match in _HONORIFIC_NAME.finditer(text or ""))
    claimants = {
        surname(person)
        for party in parties
        if party.get("role") in SENSITIVE_ROLES
        for person in people_in(party.get("name") or "")
    }
    names: set[str] = set()
    for candidate in candidates:
        printed = re.sub(r"['’]s$", "", candidate.strip())
        if not printed or WITHHELD in printed:
            continue
        people = [p for p in people_in(printed) if surname(p) in claimants or surname(p) not in officials]
        names.update(people)
        if len(people) > 1:
            names.add(printed)  # a couple is withheld as printed, in one piece
    return names


def name_variants(name: str) -> list[str]:
    """The ways a name may be printed, longest first: "Miss Jessie I. Hendry", "Jessie I. Hendry", "Jessie Hendry",
    "Hendry"."""
    bare = _HONORIFIC.sub("", name).strip()
    if _JOINED.search(bare):
        return [name.strip()]
    words = bare.split()
    variants = {name.strip(), bare}
    if len(words) >= 2:
        variants.add(f"{words[0]} {words[-1]}")
    last = words[-1].strip(".,") if words else ""
    if len(last) > 2:
        variants.add(last)
    return sorted((v for v in variants if v), key=len, reverse=True)


def mask(text: str, names: Iterable[str]) -> str:
    """Replace every printed form of the names with WITHHELD, together with any title in front of it.

    A name printed right after a public role ("Ald. Gibson") is an official who shares a surname with the private
    person, and stays.
    """
    if not text:
        return text

    def withhold(match: re.Match[str]) -> str:
        return match.group(0) if _AFTER_ROLE.search(text[: match.start()]) else WITHHELD

    variants = sorted({v for name in names for v in name_variants(name)}, key=len, reverse=True)
    for variant in variants:
        pattern = (
            r"(?:\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+)?" + r"\s+".join(re.escape(w) for w in variant.split()) + r"(?![\w])"
        )
        text = re.sub(r"(?<![\w])" + pattern, withhold, text)
    return text


def mask_item(item: ModelItem, officials: set[str]) -> tuple[ModelItem, set[str]]:
    """The item with private people's names withheld, and the names withheld. The caller decides whether the rule
    applies."""
    names = private_names(item, officials | officials_of_item(item))
    if not names:
        return item, set()
    masked = item.copy()
    masked["quote"] = mask(item.get("quote") or "", names)
    masked["summary"] = mask(item.get("summary") or "", names)
    masked["why"] = mask(item.get("why") or "", names)
    masked["parties"] = [
        {**party, "name": WITHHELD if party.get("name") in names else mask(party.get("name") or "", names)}
        for party in item.get("parties") or []
    ]
    masked["money"] = [{**m, "payee": mask(m.get("payee") or "", names)} for m in item.get("money") or []]
    masked["places"] = [{**p, "text": mask(p.get("text") or "", names)} for p in item.get("places") or []]
    return masked, names
