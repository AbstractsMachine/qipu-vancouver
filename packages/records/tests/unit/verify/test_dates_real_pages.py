"""verify/dates.py on lines of real Vancouver minutes pages; the sources are named in tests/fixtures/real_pages.py."""

import datetime as dt

from qipu_records.verify.dates import DateSource, date_pages, meeting_openings, running_head
from tests.fixtures import real_pages as pages


def test_running_head_with_doubled_spaces() -> None:
    assert running_head(pages.RUNNING_HEAD_1974) == dt.date(1974, 10, 22)


def test_meeting_opening_at_the_top_of_the_page() -> None:
    [(_, opened)] = meeting_openings(pages.MEETING_OPENING_1974)
    assert opened == dt.date(1974, 10, 22)
    [page] = date_pages([pages.MEETING_OPENING_1974])
    assert (page.at_start, page.source) == (dt.date(1974, 10, 22), DateSource.MEETING_OPENS)


def test_page_that_opens_a_new_meeting_after_the_old_one_closes() -> None:
    before, after = date_pages([pages.CHANGE_BEFORE_1967, pages.CHANGE_AFTER_1967])
    assert (before.at_start, before.source) == (dt.date(1967, 5, 30), DateSource.RUNNING_HEAD)
    assert (after.at_start, after.source) == (dt.date(1967, 6, 1), DateSource.MEETING_OPENS)


def test_ocr_that_garbles_the_day_dates_nothing_and_the_meeting_carries_on() -> None:
    assert running_head(pages.GARBLED_HEAD_1967) is None
    clean, garbled = date_pages([pages.CLEAN_HEAD_1967, pages.GARBLED_HEAD_1967])
    assert (clean.at_start, clean.source) == (dt.date(1967, 5, 30), DateSource.RUNNING_HEAD)
    assert (garbled.at_start, garbled.source) == (dt.date(1967, 5, 30), DateSource.CARRIED)


def test_a_received_stamp_does_not_override_the_meeting_in_progress() -> None:
    opened, stamped = date_pages([pages.CHANGE_AFTER_1967, pages.STAMP_OVER_GARBLED_HEAD_1967])
    assert opened.at_start == dt.date(1967, 6, 1)
    assert (stamped.at_start, stamped.source) == (dt.date(1967, 6, 1), DateSource.CARRIED)


def test_a_council_head_wins_over_the_stamp_beside_it() -> None:
    assert running_head(pages.STAMP_BESIDE_COUNCIL_HEAD_1967) == dt.date(1967, 6, 1)
    [page] = date_pages([pages.STAMP_BESIDE_COUNCIL_HEAD_1967])
    assert (page.at_start, page.source) == (dt.date(1967, 6, 1), DateSource.RUNNING_HEAD)


def test_on_a_bound_report_the_stamp_names_the_meeting() -> None:
    [page] = date_pages([pages.STAMP_OVER_REPORT_HEAD_1970], item_date=dt.date(1970, 6, 9))
    assert (page.at_start, page.source) == (dt.date(1970, 6, 9), DateSource.RUNNING_HEAD)
