import pytest

from qipu_records.verify.outcomes import Outcome, is_zoning_change, stage_and_outcome, zoning_status


def test_only_final_acts_are_passed() -> None:
    assert stage_and_outcome("passed_final") == ("final passage", Outcome.PASSED)
    assert stage_and_outcome("passed_first_reading") == ("first reading", Outcome.PENDING)
    assert stage_and_outcome("failed") == ("failed", Outcome.REFUSED)
    assert stage_and_outcome("something new") == (None, Outcome.UNKNOWN)


@pytest.mark.parametrize(
    ("kind", "action", "expected"),
    [
        ("ordinance", "passed_final", "rezoned"),
        ("resolution", "adopted", "rezoned"),
        ("ordinance", "passed_first_reading", "rezoning proposed"),
        ("ordinance", "referred", "rezoning proposed"),
        ("appeal", "continued", "rezoning proposed"),
        ("motion", "adopted", "rezoning proposed"),
        ("ordinance", "failed", "rezoning proposed"),
    ],
)
def test_rezoned_only_on_final_passage(kind: str, action: str, expected: str) -> None:
    assert zoning_status(kind, action, "RS-1", "RM-3") == expected


def test_renamed_streets_and_dates_are_not_zoning() -> None:
    assert not is_zoning_change("Cleveland Street", "Washington Street")
    assert not is_zoning_change("", "September 18, 1967")
    assert not is_zoning_change("", "")
    assert is_zoning_change("R-4", "R-5")
    assert zoning_status("ordinance", "passed_final", "Elm Street", "Oak Street") is None
