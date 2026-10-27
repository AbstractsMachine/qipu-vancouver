"""The JSON the model must answer with, and the message it gets for one page.

The model reads one page at a time and returns ``{"items": [...]}``: one entry per decision on the page, each with the
quote that shows where it is. The schema is strict (every field required, nothing extra) so it can be enforced by the
model API's structured output mode. Fields the page does not print come back as "" or [] and are dropped later.
"""

from __future__ import annotations

import hashlib
from typing import Any, TypedDict

SCHEMA_VERSION = "v2.1"
PAGE_TEXT_LIMIT = 9000
CONTEXT_CHARS = 2500
"""How much of the previous page goes with each request, so an item that starts there can be read."""

TOPICS = [
    "homelessness-shelter", "landmarks-old-buildings", "housing", "whats-being-built", "schools", "fire",
    "redevelopment", "libraries", "police", "health", "water-sewers", "transit", "parks",
]  # fmt: skip
ACTIONS = [
    "adopted", "passed_final", "passed_first_reading", "ordered_submitted_to_voters", "amended", "referred",
    "continued", "tabled", "failed", "vetoed", "veto_overridden", "withdrawn", "hearing_held", "continues_next_page",
    "other",
]  # fmt: skip
KINDS = [
    "ordinance", "resolution", "motion", "claim", "appointment", "permit", "license", "contract", "hearing", "appeal",
    "charter_amendment", "ballot_measure", "other",
]  # fmt: skip
PARTY_ROLES = [
    "claimant", "contractor", "appointee", "owner", "applicant", "payee", "grantee", "grantor", "petitioner",
    "employee", "sponsor", "other",
]  # fmt: skip
PLACE_PRECISIONS = ["address", "segment", "intersection", "block_lot", "street", "area", "city"]
DATE_ROLES = ["effective", "continued_to", "hearing", "deadline", "other"]

_STRING: dict[str, Any] = {"type": "string"}
_BOOLEAN: dict[str, Any] = {"type": "boolean"}
_COUNT: dict[str, Any] = {"type": ["integer", "null"]}


def _array(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def _enum(values: list[str]) -> dict[str, Any]:
    return {"type": "string", "enum": values}


def _object(**properties: dict[str, Any]) -> dict[str, Any]:
    """An object whose every property is required and that allows nothing else, as structured outputs need."""
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


ITEM = _object(
    quote=_STRING,
    heading_on_prev=_BOOLEAN,
    kind=_enum(KINDS),
    number=_STRING,
    file=_STRING,
    action=_enum(ACTIONS),
    amended=_BOOLEAN,
    continued_to=_STRING,
    ayes=_COUNT,
    noes=_COUNT,
    absent=_COUNT,
    ayes_names=_array(_STRING),
    noes_names=_array(_STRING),
    absent_names=_array(_STRING),
    mover=_STRING,
    seconder=_STRING,
    department=_STRING,
    parties=_array(_object(name=_STRING, role=_enum(PARTY_ROLES))),
    money=_array(_object(amount={"type": "number"}, purpose=_STRING, payee=_STRING)),
    places=_array(
        _object(
            text=_STRING,
            street=_STRING,
            number=_STRING,
            from_street=_STRING,
            to_street=_STRING,
            block=_STRING,
            lot=_STRING,
            area=_STRING,
            precision=_enum(PLACE_PRECISIONS),
        )
    ),
    zoning_from=_STRING,
    zoning_to=_STRING,
    related=_array(_STRING),
    dates=_array(_object(date=_STRING, role=_enum(DATE_ROLES))),
    topics=_array(_enum(TOPICS)),
    interest={"type": "integer"},
    why=_STRING,
    summary=_STRING,
)
RESPONSE = _object(items=_array(ITEM))


# The same shapes as Python types. The schema above is what the model API enforces; these let the type checker follow
# the
# fields through the checks. Answers replayed from a file or read by a model without strict structured output can lack
# fields, so every field is optional here and the code reads them with .get(). A test keeps the two in step.


class ModelParty(TypedDict, total=False):
    name: str
    role: str


class ModelMoney(TypedDict, total=False):
    amount: float
    purpose: str
    payee: str


class ModelPlace(TypedDict, total=False):
    """One place as the model reported it, with whichever parts of the address it found."""

    text: str
    street: str
    number: str
    from_street: str
    to_street: str
    block: str
    lot: str
    area: str
    precision: str


class ModelDate(TypedDict, total=False):
    date: str
    role: str


class ModelItem(TypedDict, total=False):
    """One decision as the model listed it."""

    quote: str
    heading_on_prev: bool
    kind: str
    number: str
    file: str
    action: str
    amended: bool
    continued_to: str
    ayes: int | None
    noes: int | None
    absent: int | None
    ayes_names: list[str]
    noes_names: list[str]
    absent_names: list[str]
    mover: str
    seconder: str
    department: str
    parties: list[ModelParty]
    money: list[ModelMoney]
    places: list[ModelPlace]
    zoning_from: str
    zoning_to: str
    related: list[str]
    dates: list[ModelDate]
    topics: list[str]
    interest: int
    why: str
    summary: str


def prompt_version(system_prompt: str) -> str:
    """A short hash of the system prompt, recorded with every response so a run can be traced to its exact prompt."""
    return "v21-" + hashlib.sha1(system_prompt.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]


def user_message(previous_page: str, page: str, year: int | None) -> str:
    """The message for one page: the end of the previous page as context, then the page itself."""
    return (
        f"PREVIOUS PAGE (context only):\n<<<\n{previous_page[-CONTEXT_CHARS:]}\n>>>\n\n"
        f"THIS PAGE (volume year {year or '?'}):\n<<<\n{page[:PAGE_TEXT_LIMIT]}\n>>>"
    )
