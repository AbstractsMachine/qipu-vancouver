import datetime as dt

from qipu_records.verify.dates import DateSource, date_pages, meeting_openings, running_head

VANCOUVER_OPENING = (
    "CITY OF VANCOUVER\nREGULAR COUNCIL MEETING\nA Regular meeting of the Council of the City of Vancouver was\n"
    "held on Tuesday, February 19, 1974, in the Council Chamber at\napproximately 2:00 p.m.\nPRESENT : Mayor Phillips"
)


def test_vancouver_running_head() -> None:
    assert running_head("2^3\nRegular Council, February 19, 1974 3\nCOMMUNICATIONS") == dt.date(1974, 2, 19)
    assert running_head("Council Meeting, January 7,1970 , 3\n") == dt.date(1970, 1, 7)


def test_san_francisco_running_head_with_weekday() -> None:
    assert running_head("MONDAY, JANUARY 21, 1924\nJOURNAL OF PROCEEDINGS") == dt.date(1924, 1, 21)


def test_weekday_that_disagrees_with_the_date_dates_nothing() -> None:
    assert running_head("Monday, July 21, 1989\n") is None


def test_dates_in_the_body_are_not_headers() -> None:
    body = "x" * 300 + "adjourned to meet on Monday, February 18, 1907"
    assert running_head(body) is None
    assert meeting_openings(body) == []


def test_meeting_opening_is_found_where_it_is() -> None:
    page = "end of the last meeting.\n" * 10 + "In Board of Supervisors, Monday, February 4th, 1907. Roll call."
    [(offset, date)] = meeting_openings(page)
    assert date == dt.date(1907, 2, 4)
    assert page[offset:].startswith("Monday")


def test_items_after_an_opening_take_the_new_meeting() -> None:
    first = "MONDAY, JANUARY 28, 1907\nold business " + "x" * 400
    second = "more old business " + "y" * 300 + " JOURNAL OF PROCEEDINGS BOARD OF SUPERVISORS MONDAY, FEBRUARY 4, 1907 new"
    pages = date_pages([first, second])
    assert pages[1].at(10) == (dt.date(1907, 1, 28), DateSource.CARRIED)
    assert pages[1].at(len(second) - 2) == (dt.date(1907, 2, 4), DateSource.MEETING_OPENS)


def test_opening_at_the_top_dates_the_page() -> None:
    [page] = date_pages([VANCOUVER_OPENING])
    assert (page.at_start, page.source) == (dt.date(1974, 2, 19), DateSource.MEETING_OPENS)


def test_pages_before_any_header_fall_back_to_the_item_date() -> None:
    pages = date_pages(["no header here", "Regular Council, June 9, 1970\nbody", "still June 9"], dt.date(1970, 6, 1))
    assert [(p.at_start, p.source) for p in pages] == [
        (dt.date(1970, 6, 1), DateSource.ITEM),
        (dt.date(1970, 6, 9), DateSource.RUNNING_HEAD),
        (dt.date(1970, 6, 9), DateSource.CARRIED),
    ]


def test_no_date_at_all() -> None:
    assert date_pages(["nothing"])[0].source is DateSource.NONE
