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
