"""Withhold the names of private people in sensitive matters, and nothing else.

This is the rule in docs/privacy.md, the Canadian rule (BC FIPPA ss. 22 and 33): every decision, motion and page link is
published. A record 100 years old or more is completely open. In a newer record one thing is masked: the name of a
private person, and only when the record is about that person's sensitive matter. There are seven such matters: health;
social or income assistance; a police or criminal matter, or an enforcement order at someone's home; personal finances
(debts, tax arrears, bankruptcy, a damage or injury claim, a lawsuit against the city); a discrimination or harassment
complaint; a child; and the discipline or dismissal of an employee. A land-use, permit, licence, contract, grant,
appointment or honour record is never one of them, even when a sensitive word appears in it.

Never masked: councillors, aldermen, the mayor and staff in their role; delegations, speakers, petitioners and letter
writers; businesses and organisations; contractors and payees; people honoured; places named after people. A payee is
withheld only when the payment settles the sensitive matter itself, which makes the payee the claimant.

Who counts as an official is read from the record: the mover and seconder, the roll call, and anyone the page names next
to a role ("Ald. Linnell", "Mayor Phillips"). A name the record shows in a public role anywhere (after "letter from",
before "Ltd.") is public in all of the record.
"""

from __future__ import annotations

import datetime as dt
import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass, field
from importlib import resources

from qipu_records.read.schema import ModelItem

WITHHELD = "[name withheld]"

_PATTERNS = tomllib.loads(resources.files(__package__).joinpath("privacy_patterns.toml").read_text("utf-8"))
"""The rule's regular expressions, from privacy_patterns.toml beside this file: one pattern per sensitive matter, the
public functions, and the words before and after a name that make it public. Each is a list of pieces joined as is."""


def _pattern(pieces: list[str]) -> str:
    return "".join(pieces)


MATTER_PATTERNS = {name: _pattern(pieces) for name, pieces in _PATTERNS["matters"].items()}
_PUBLIC_FUNCTION = _pattern(_PATTERNS["public"]["function"])
_KEEP_BEFORE = _pattern(_PATTERNS["names"]["keep_before"])
_KEEP_AFTER = _pattern(_PATTERNS["names"]["keep_after"])

MATTERS = {name: re.compile(pattern, re.I) for name, pattern in MATTER_PATTERNS.items()}
PUBLIC_FUNCTION = re.compile(_PUBLIC_FUNCTION, re.I)
PUBLIC_KINDS = {"permit", "license", "contract", "appointment"}
"""Kinds of record that are public functions whatever words they contain."""
CLAIM_KINDS = {"claim"}
"""A claim against the city is a damage or injury claim: a personal-finances matter."""
SUBJECT_ROLES = {"claimant"}
PUBLIC_ROLES = {"contractor", "appointee", "applicant", "payee", "grantee", "grantor", "petitioner", "sponsor"}
"""Party roles that are public by what the person does in the record."""
SETTLEMENT = re.compile(r"\b(?:claims?|settle\w*|damages?|compensation|injur\w*|ex\s+gratia)\b", re.I)
"""A payment whose purpose says this settles the matter itself: its payee is the claimant."""
KEEP_BEFORE = re.compile(_KEEP_BEFORE)
"""Text right before a name that makes it public: a title, a delegation, a letter writer, a payee, a firm, a
namesake.
"""
KEEP_AFTER = re.compile(_KEEP_AFTER)
"""Text right after a name that makes it public: a firm, an organisation, a place, a role."""
PAYEE_BEFORE = re.compile(
    r"(?:paid\s+to|payment\s+to|payable\s+to|services\s+rendered\s+by|account\s+of)\W{0,4}"
    r"(?:(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+)?(?:[A-Z]\.\s*){0,3}$"
)
"""The payee words of KEEP_BEFORE. A payee is public, unless the payment settles the claim the record is about."""

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


def matter_of(text: str) -> str | None:
    """The sensitive matter a text is about (a key of MATTERS), or None. A public-function text is never sensitive."""
    flat = " ".join(text.split())
    if not flat or PUBLIC_FUNCTION.search(flat):
        return None
    return next((name for name, pattern in MATTERS.items() if pattern.search(flat)), None)


def is_organisation(name: str) -> bool:
    """True for names of firms, groups and public bodies: a telling word, or a joining word no person's name has.

    "Estate of John Smith" and "John and Mary Smith" are people, not organisations: see `people_in`.
    """
    if _ESTATE_OF.match(name):
        return False
    return bool(_ORGANISATION.search(name) or re.search(r"\s(?:of|for|the)\s", name, re.I))


def people_in(name: str) -> list[str]:
    """The private people a printed name stands for: none for an organisation, both people of a couple, the person
    behind "Estate of the late John Smith".
    """
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


def in_public_role(before: str) -> bool:
    """The text right before a name shows the person in a public role: a title, a delegation, a letter, a firm. Payee
    words do not count here, because the payee of a settled claim is the claimant.
    """
    return bool(KEEP_BEFORE.search(before)) and not PAYEE_BEFORE.search(before)


def names_a_firm_or_place(after: str) -> bool:
    """The text right after a name makes it part of a firm's, organisation's or place's name ("Gibson Construction
    Ltd.", "Gibson Street"), or a role. "Gibson of Main Street" is a person and an address, not a place name.
    """
    return bool(KEEP_AFTER.match(after)) and not re.match(r"\W*(?:of|for|and)\b", after)


def _settlement_payees(item: ModelItem) -> list[str]:
    """Payees of the payments that settle the claim itself: they are the claimants."""
    claim = item.get("kind") in CLAIM_KINDS
    return [
        m.get("payee") or ""
        for m in item.get("money") or []
        if SETTLEMENT.search(m.get("purpose") or "") or (claim and not m.get("purpose"))
    ]


def _settles(item: ModelItem) -> bool:
    """The item is a claim, or pays one: a payment whose purpose names the claim, the damages or the injury."""
    return item.get("kind") in CLAIM_KINDS or any(
        SETTLEMENT.search(m.get("purpose") or "") for m in item.get("money") or []
    )


def matter(item: ModelItem) -> str | None:
    """The sensitive matter an item is about, or None."""
    if item.get("kind") in PUBLIC_KINDS:
        return None
    text = " ".join([item.get("quote") or "", item.get("summary") or "", item.get("why") or ""])
    if PUBLIC_FUNCTION.search(" ".join(text.split())):
        return None
    roles = {party.get("role") for party in item.get("parties") or []}
    if _settles(item) or roles & SUBJECT_ROLES:
        return "personal_finances"
    return matter_of(text)


def item_is_sensitive(item: ModelItem) -> bool:
    """True when the item is about a sensitive matter, so private people's names in it fall under the embargo."""
    return matter(item) is not None


def _public_in(texts: Iterable[str], name: str) -> bool:
    """The record shows this name in a public role somewhere: after a title, a delegation or a payee word, or before a
    firm, organisation, place or role word.
    """
    printed = re.compile(r"(?<![\w])" + r"\s+".join(re.escape(w) for w in name.split()) + r"(?![\w])")
    for text in texts:
        for match in printed.finditer(text):
            before, after = text[max(0, match.start() - 60) : match.start()], text[match.end() : match.end() + 80]
            if KEEP_BEFORE.search(before) or KEEP_AFTER.match(after):
                return True
    return False


def private_names(item: ModelItem, officials: set[str]) -> set[str]:
    """Names of private people in an item, as printed, for `mask` to withhold.

    Candidates are the parties (except those in a public role: contractor, applicant, payee, ...) and every name after
    an honorific in the item's text. The people the matter is about, its claimants and, when the item settles a claim,
    its payees, are always withheld. Anyone else is kept when they are an official, an organisation, or shown in a
    public role somewhere in the record.
    """
    parties = item.get("parties") or []
    texts = [item.get("quote") or "", item.get("summary") or "", item.get("why") or ""]
    texts += [p.get("text") or "" for p in item.get("places") or []]
    subjects = [party.get("name") or "" for party in parties if party.get("role") in SUBJECT_ROLES]
    if _settles(item):
        subjects += _settlement_payees(item)
    subject_surnames = {surname(person) for name in subjects for person in people_in(name)}
    candidates = subjects + [party.get("name") or "" for party in parties if party.get("role") not in PUBLIC_ROLES]
    for text in texts:
        candidates.extend(match.group(0) for match in _HONORIFIC_NAME.finditer(text))
    names: set[str] = set()
    for candidate in candidates:
        printed = re.sub(r"['’]s$", "", candidate.strip())
        if not printed or WITHHELD in printed:
            continue
        people = [
            p
            for p in people_in(printed)
            if surname(p) in subject_surnames
            or (surname(p) not in officials and not _public_in(texts, _HONORIFIC.sub("", p)))
        ]
        names.update(people)
        if len(people) > 1:
            names.add(printed)  # a couple is withheld as printed, in one piece
    return names


def name_variants(name: str) -> list[str]:
    """The ways a name may be printed, longest first: "Miss Jessie I. Hendry", "Jessie I. Hendry", "Jessie Hendry",
    "Hendry".
    """
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
    person, and stays; so does one printed before a firm or place word ("Gibson Construction Ltd.", "Gibson Street").
    """
    if not text:
        return text

    def withhold(match: re.Match[str]) -> str:
        kept = _AFTER_ROLE.search(text[: match.start()]) or names_a_firm_or_place(text[match.end() : match.end() + 80])
        return match.group(0) if kept else WITHHELD

    variants = sorted({v for name in names for v in name_variants(name)}, key=len, reverse=True)
    for variant in variants:
        pattern = (
            r"(?:\b(?:Mr|Mrs|Ms|Miss|Dr)\.?\s+)?" + r"\s+".join(re.escape(w) for w in variant.split()) + r"(?![\w])"
        )
        text = re.sub(r"(?<![\w])" + pattern, withhold, text)
    return text


def mask_item(item: ModelItem, officials: set[str]) -> tuple[ModelItem, set[str]]:
    """The item with private people's names withheld, and the names withheld. The caller decides whether the rule
    applies.
    """
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
