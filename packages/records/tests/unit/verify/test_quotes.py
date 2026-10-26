from qipu_records.verify.quotes import QuoteStatus, locate

PAGE = "Regular Council, February 19, 1974 3\nCOMMUNICATIONS OR PETITIONS (cont'd)\nMotor Vehicle   Inspection\nStation (cont'd)"


def test_exact_match_ignores_case_and_line_breaks() -> None:
    match = locate("motor vehicle inspection station", PAGE)
    assert match.status is QuoteStatus.EXACT
    assert match.offset == PAGE.index("Motor")


def test_fuzzy_match_survives_ocr_slips() -> None:
    page = "Claim of Mrs. W. Barr re damage to property at 1234 Main Street was received"
    match = locate("Claim of Mrs. W. Barr re damaqe to properly at 1234 Main Street", page)
    assert match.status is QuoteStatus.FUZZY
    assert match.offset == 0
    assert 0.6 <= match.score < 1


def test_quote_from_another_page_is_not_found() -> None:
    assert not locate("Sunday Sports By-law amendment to include wrestling", PAGE).found


def test_short_quotes_are_not_evidence() -> None:
    assert not locate("Station", PAGE).found
