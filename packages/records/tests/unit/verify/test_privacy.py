import datetime as dt
from typing import Any

from qipu_records.verify.privacy import (
    WITHHELD,
    Embargo,
    is_organisation,
    is_sensitive,
    item_is_sensitive,
    mask,
    mask_item,
    officials_on_page,
    people_in,
    private_names,
)


def _item(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"kind": "motion", "quote": "", "summary": "", "parties": [], "money": [], "places": [], "mover": ""}
    return base | fields


def test_embargo_counts_back_from_today() -> None:
    vancouver = Embargo(92, today=dt.date(2026, 10, 26))
    assert vancouver.cutoff_year == 1934
    assert not vancouver.applies(1934)
    assert vancouver.applies(1935)
    assert vancouver.applies(None)


def test_sensitive_matters() -> None:
    assert is_sensitive("claim of Mrs. Smith for damages to her car")
    assert is_sensitive("social assistance for persons laid off work")
    assert is_sensitive("Jones v. City and County")


def test_words_that_only_look_sensitive() -> None:
    assert not is_sensitive("Comments on Mr. C. Campbell's Minority Report on False Creek")
    assert not is_sensitive("Cl. 2: T.V. Inspection of Sewers")


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


def test_a_payee_in_a_sensitive_payment_is_withheld() -> None:
    item = _item(
        summary="Payment for injuries suffered on a city sidewalk.",
        money=[{"amount": 250, "purpose": "injury settlement", "payee": "Tom Wu"}],
    )
    assert item_is_sensitive(item)
    masked, names = mask_item(item, officials=set())
    assert names == {"Tom Wu"}
    assert masked["money"][0]["payee"] == WITHHELD


def test_a_claimant_who_shares_a_surname_with_an_alderman_is_still_withheld() -> None:
    item = _item(
        kind="claim",
        summary="Claim of Mr. Peter Gibson for damages, referred on the motion of Ald. Gibson.",
        parties=[{"name": "Peter Gibson", "role": "claimant"}],
        mover="Gibson",
    )
    masked, _ = mask_item(item, officials={"gibson"})
    assert masked["summary"] == f"Claim of {WITHHELD} for damages, referred on the motion of Ald. Gibson."
