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
