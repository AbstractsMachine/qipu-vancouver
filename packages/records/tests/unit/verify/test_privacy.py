import datetime as dt
import tomllib
from importlib import resources
from typing import Unpack

import pytest

from qipu_records.read.schema import ModelItem
from qipu_records.verify import privacy
from qipu_records.verify.privacy import (
    KEEP_AFTER,
    KEEP_BEFORE,
    MATTERS,
    PUBLIC_FUNCTION,
    WITHHELD,
    Embargo,
    is_organisation,
    item_is_sensitive,
    mask,
    mask_item,
    matter,
    matter_of,
    officials_on_page,
    people_in,
    private_names,
)


def _item(**fields: Unpack[ModelItem]) -> ModelItem:
    return {
        "kind": "motion",
        "quote": "",
        "summary": "",
        "parties": [],
        "money": [],
        "places": [],
        "mover": "",
        **fields,
    }


def test_a_record_100_years_old_or_more_is_open() -> None:
    vancouver = Embargo(100, today=dt.date(2026, 10, 26))
    assert vancouver.cutoff_year == 1926
    assert not vancouver.applies(1926)
    assert vancouver.applies(1927)
    assert vancouver.applies(None)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Application for relief on compassionate grounds by reason of her medical condition", "health"),
        ("Appeal of a social assistance recipient against the reduction of her allowance", "social_assistance"),
        ("That the premises at 2300 Oak Street be declared a nuisance", "police_criminal"),
        ("Claim of Mrs. Smith for damages to her car", "personal_finances"),
        ("Writ of summons: Jones v. City of Vancouver", "personal_finances"),
        ("Complaint of discrimination against the Parks Board", "discrimination_harassment"),
        ("Placement of a child in foster care", "children"),
        ("Dismissal of a labourer in the Engineering Department", "employment_discipline"),
    ],
)
def test_the_seven_sensitive_matters(text: str, expected: str) -> None:
    assert matter_of(text) == expected


def test_public_functions_and_ordinary_words_are_not_sensitive() -> None:
    assert matter_of("Rezoning of 2300 Oak Street; neighbours say the vacant lot is a nuisance") is None
    assert matter_of("Comments on Mr. C. Campbell's Minority Report on False Creek") is None
    assert matter_of("Cl. 2: T.V. Inspection of Sewers") is None
    assert matter(_item(kind="permit", summary="Permit refused after a claim for damages")) is None


def test_organisations_are_recognised() -> None:
    for name in (
        "Glenfield Holdings Ltd.",
        "International Woodworkers of America",
        "B.C. Civil Liberties Association",
        "CKNW Orphans Fund",
    ):
        assert is_organisation(name), name
    assert not is_organisation("Jessie I. Hendry")


def test_officials_are_read_from_role_words() -> None:
    page = "PRESENT : Mayor Phillips\nAldermen Bowers, Gibson, Harcourt and Volrich\nMOVED by Ald. Linnell,"
    assert {"phillips", "bowers", "gibson", "harcourt", "volrich", "linnell"} <= officials_on_page(page)


def test_mask_replaces_every_printed_form_with_its_title() -> None:
    text = "Claim of Miss Jessie I. Hendry, 3891 Arbutus Street. Miss Hendry's claim was deferred."
    assert mask(text, {"Miss Jessie I. Hendry"}) == (
        f"Claim of {WITHHELD}, 3891 Arbutus Street. {WITHHELD}'s claim was deferred."
    )


def test_mask_leaves_longer_words_alone() -> None:
    assert mask("Hendryson Street", {"Jessie Hendry"}) == "Hendryson Street"


def test_claimant_in_a_claim_is_withheld_but_the_place_and_outcome_stay() -> None:
    item = _item(
        kind="claim",
        quote="Claim of Mrs. Mary Roe 12 Oak Street",
        summary="Council paid $300 on Mrs. Mary Roe's claim for damage at 12 Oak Street.",
        parties=[{"name": "Mrs. Mary Roe", "role": "claimant"}],
        money=[{"amount": 300, "purpose": "claim", "payee": "Mrs. Mary Roe"}],
        places=[{"text": "12 Oak Street", "precision": "address"}],
        action="adopted",
    )
    assert item_is_sensitive(item)
    masked, names = mask_item(item, officials=set())
    assert names == {"Mrs. Mary Roe"}
    assert "Roe" not in str(masked)
    assert masked["parties"] == [{"name": WITHHELD, "role": "claimant"}]
    assert masked["places"][0]["text"] == "12 Oak Street"
    assert masked["action"] == "adopted"


def test_officials_and_organisations_stay_named_in_sensitive_items() -> None:
    item = _item(
        kind="claim",
        summary="Ald. Linnell moved that the claim of Acme Motors Ltd. be referred to the Corporation Counsel.",
        parties=[{"name": "Acme Motors Ltd.", "role": "claimant"}],
        mover="Linnell",
    )
    assert private_names(item, officials={"linnell"}) == set()
    masked, names = mask_item(item, officials={"linnell"})
    assert names == set()
    assert masked == item


def test_an_official_named_with_a_title_is_kept() -> None:
    item = _item(kind="claim", summary="Report of Mr. Little, City Clerk, on the claim.", parties=[])
    assert private_names(item, officials={"little"}) == set()


def test_masking_is_idempotent() -> None:
    item = _item(kind="claim", parties=[{"name": WITHHELD, "role": "claimant"}], summary=f"{WITHHELD}'s claim")
    assert private_names(item, set()) == set()


def test_an_estate_and_a_couple_are_people_not_organisations() -> None:
    assert not is_organisation("Estate of the late John Smith")
    assert people_in("Estate of the late John Smith") == ["John Smith"]
    assert people_in("John Smith and Mary Smith") == ["John Smith", "Mary Smith"]
    assert people_in("Mr. and Mrs. J. Smith") == ["Mrs. J. Smith"]
    assert people_in("Smith & Sons Ltd.") == []
    assert people_in("Friends of the Library") == []


def test_claim_by_an_estate_withholds_the_person_and_keeps_the_word_estate() -> None:
    item = _item(
        kind="claim",
        summary="Council paid the claim of the Estate of John Smith for wrongful death.",
        parties=[{"name": "Estate of John Smith", "role": "claimant"}],
    )
    masked, _ = mask_item(item, officials=set())
    assert masked["summary"] == f"Council paid the claim of the Estate of {WITHHELD} for wrongful death."
    assert "Smith" not in str(masked)


def test_both_people_of_a_couple_are_withheld() -> None:
    item = _item(
        kind="claim",
        quote="Claim of John Smith and Mary Smith",
        summary="Claim of John Smith and Mary Smith for damage to their car; Mary Smith was injured.",
        parties=[{"name": "John Smith and Mary Smith", "role": "claimant"}],
    )
    masked, _ = mask_item(item, officials=set())
    assert "Smith" not in str(masked)
    assert masked["parties"] == [{"name": WITHHELD, "role": "claimant"}]


def test_the_payee_of_an_injury_settlement_is_the_claimant_and_is_withheld() -> None:
    item = _item(
        summary="Payment for injuries suffered on a city sidewalk.",
        money=[{"amount": 250, "purpose": "injury settlement", "payee": "Tom Wu"}],
    )
    assert matter(item) == "personal_finances"
    masked, names = mask_item(item, officials=set())
    assert names == {"Tom Wu"}
    assert masked["money"][0]["payee"] == WITHHELD


def test_a_settlement_payee_listed_as_a_payee_party_is_withheld_everywhere() -> None:
    item = _item(
        summary="Payment to Tom Wu for injuries suffered on a city sidewalk.",
        money=[{"amount": 250, "purpose": "injury settlement", "payee": "Tom Wu"}],
        parties=[{"name": "Tom Wu", "role": "payee"}, {"name": "Acme Paving Ltd.", "role": "contractor"}],
    )
    masked, names = mask_item(item, officials=set())
    assert names == {"Tom Wu"}
    assert masked["parties"] == [
        {"name": WITHHELD, "role": "payee"},
        {"name": "Acme Paving Ltd.", "role": "contractor"},
    ]
    assert masked["money"][0]["payee"] == WITHHELD
    assert "Wu" not in masked["summary"]


def test_a_claimant_paid_by_name_is_withheld_after_paid_to_as_well() -> None:
    item = _item(
        kind="claim",
        summary="Claim of Mrs. Ada Brown for damages; $120 to be paid to Mrs. Ada Brown.",
        parties=[{"name": "Mrs. Ada Brown", "role": "claimant"}],
    )
    masked, _ = mask_item(item, officials=set())
    assert "Brown" not in masked["summary"]


def test_an_owner_named_in_a_nuisance_order_is_withheld() -> None:
    item = _item(summary="That the premises of Mrs. Jane Roe, 2300 Oak Street, be declared a nuisance.")
    assert matter(item) == "police_criminal"
    masked, _ = mask_item(item, officials=set())
    assert masked["summary"] == f"That the premises of {WITHHELD}, 2300 Oak Street, be declared a nuisance."


def test_a_sensitive_policy_record_that_names_nobody_masks_nothing() -> None:
    item = _item(summary="Report on the interest rate charged on property tax arrears.")
    assert matter(item) == "personal_finances"
    assert mask_item(item, officials=set()) == (item, set())


def test_payees_in_ordinary_payments_stay_named() -> None:
    item = _item(
        summary="Payment of $400 to Mr. John Doe for snow clearing on Main Street.",
        money=[{"amount": 400, "purpose": "snow clearing", "payee": "Mr. John Doe"}],
        parties=[{"name": "Mr. John Doe", "role": "payee"}],
    )
    assert matter(item) is None
    claim = _item(
        kind="claim",
        summary="Claim of Mrs. Ada Brown for damages; legal fees paid to Mr. Paul Low, Barrister.",
        parties=[{"name": "Mrs. Ada Brown", "role": "claimant"}],
        money=[{"amount": 90, "purpose": "legal fees", "payee": "Mr. Paul Low"}],
    )
    assert private_names(claim, officials=set()) == {"Mrs. Ada Brown"}


def test_letter_writers_firms_and_places_stay_named_in_a_sensitive_record() -> None:
    item = _item(
        kind="claim",
        summary=(
            "Claim of Mr. Ross Gibson for damages at Gibson Street; Gibson Construction Ltd. to repair; "
            "letter from Mr. Ian Hay supporting the claim."
        ),
        parties=[{"name": "Mr. Ross Gibson", "role": "claimant"}],
    )
    masked, names = mask_item(item, officials=set())
    assert names == {"Mr. Ross Gibson"}
    assert masked["summary"] == (
        f"Claim of {WITHHELD} for damages at Gibson Street; Gibson Construction Ltd. to repair; "
        "letter from Mr. Ian Hay supporting the claim."
    )


def test_a_claimant_who_shares_a_surname_with_an_alderman_is_still_withheld() -> None:
    item = _item(
        kind="claim",
        summary="Claim of Mr. Peter Gibson for damages, referred on the motion of Ald. Gibson.",
        parties=[{"name": "Peter Gibson", "role": "claimant"}],
        mover="Gibson",
    )
    masked, _ = mask_item(item, officials={"gibson"})
    assert masked["summary"] == f"Claim of {WITHHELD} for damages, referred on the motion of Ald. Gibson."


# One sample the pattern must match and one it must not, for every pattern in privacy_patterns.toml.
MATTER_SAMPLES = {
    "health": ("a letter on medical grounds for the clerk", "a letter on the grounds of the park"),
    "social_assistance": ("an appeal on income assistance", "assistance with the parade"),
    "police_criminal": ("Mr. Gray was charged with theft", "the charge for parking meters"),
    "personal_finances": ("tax arrears on the lot", "arrears in the report schedule"),
    "discrimination_harassment": ("a complaint of harassment", "a complaint about noise"),
    "children": ("custody of a child", "a children's playground"),
    "employment_discipline": ("disciplinary action against a clerk", "a well run schedule"),
}


def test_the_patterns_load_from_the_toml_file() -> None:
    patterns = tomllib.loads((resources.files("qipu_records.verify") / "privacy_patterns.toml").read_text("utf-8"))
    assert set(patterns["matters"]) == set(MATTERS) == set(MATTER_SAMPLES)
    assert {name: "".join(pieces) for name, pieces in patterns["matters"].items()} == privacy.MATTER_PATTERNS
    assert privacy.PUBLIC_FUNCTION.pattern == "".join(patterns["public"]["function"])
    assert privacy.KEEP_BEFORE.pattern == "".join(patterns["names"]["keep_before"])
    assert privacy.KEEP_AFTER.pattern == "".join(patterns["names"]["keep_after"])


@pytest.mark.parametrize("name", sorted(MATTER_SAMPLES))
def test_each_matter_pattern_matches_its_matter_only(name: str) -> None:
    hit, miss = MATTER_SAMPLES[name]
    assert MATTERS[name].search(hit)
    assert not MATTERS[name].search(miss)


def test_the_public_function_pattern_matches_a_rezoning_and_not_a_claim() -> None:
    assert PUBLIC_FUNCTION.search("an application for rezoning")
    assert not PUBLIC_FUNCTION.search("a claim for damages")


def test_the_keep_before_pattern_matches_a_title_before_a_name_and_not_a_plain_word() -> None:
    assert KEEP_BEFORE.search("moved by Ald. ")
    assert KEEP_BEFORE.search("a letter from ")
    assert not KEEP_BEFORE.search("the lot of ")


def test_the_keep_after_pattern_matches_a_firm_or_street_after_a_name_and_not_a_plain_word() -> None:
    assert KEEP_AFTER.match(" Construction Ltd. built")
    assert KEEP_AFTER.match(" Street")
    assert not KEEP_AFTER.match(" was ill")
