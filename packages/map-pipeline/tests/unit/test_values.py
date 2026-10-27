import pytest

from qipu_map.model import RoofForm
from qipu_map.values import as_float, as_int, as_positive, as_text, most_common, year_in


@pytest.mark.parametrize(
    ("raw", "want"),
    [(1951, 1951), (" 1951 ", 1951), (1951.0, 1951), (1951.5, None), ("", None), (None, None), (True, None)],
)
def test_as_int(raw: object, want: int | None) -> None:
    assert as_int(raw) == want


def test_as_float_and_positive() -> None:
    assert as_float("2.5") == 2.5
    assert as_float("nan") is None
    assert as_float([1]) is None
    assert as_positive("0") is None
    assert as_positive(3) == 3.0


def test_as_text() -> None:
    assert as_text("  Pendrell ") == "Pendrell"
    assert as_text("  ") is None
    assert as_text(None) is None


@pytest.mark.parametrize(
    ("text", "want"),
    [("1925", 1925), ("c. 1925", 1925), ("1925-06-01", 1925), ("1920s", 1920), ("early", None), (None, None)],
)
def test_year_in(text: str | None, want: int | None) -> None:
    assert year_in(text) == want


def test_most_common_breaks_ties_to_the_smallest() -> None:
    assert most_common([2021, 1951, 2021]) == 2021
    assert most_common([1960, 1951]) == 1951
    assert most_common([RoofForm.HIP, RoofForm.GABLE]) is RoofForm.GABLE
    assert most_common([]) is None
