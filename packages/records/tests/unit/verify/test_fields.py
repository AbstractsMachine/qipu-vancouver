"""verify/fields.py on real minutes; the passages and their sources are in tests/fixtures/real_decisions.py."""

import datetime as dt

from qipu_records.verify.fields import Verdict, check_fields, motions
from tests.fixtures import real_decisions as pages

JUNE_9_1970 = dt.date(1970, 6, 9)


def test_an_unknown_outcome_is_read_from_the_verdict() -> None:
    out = check_fields(pages.NO_FURTHER_ACTION_1970, "", JUNE_9_1970, outcome="unknown", amended=False, vote=None,
                       summary="")  # fmt: skip
    assert out.outcome == "refused"
    assert [(c.field, c.result, c.was) for c in out.checks] == [("outcome", "corrected", "unknown")]


def test_an_unknown_outcome_of_a_plain_motion_that_carried_is_passed() -> None:
    out = check_fields(pages.VOTED_AGAINST_1974, "", JUNE_9_1970, outcome="unknown", amended=False, vote=None,
                       summary="")  # fmt: skip
    assert out.outcome == "passed"


def test_passed_when_every_motion_was_lost_is_refused() -> None:
    span = pages.NO_FURTHER_ACTION_1970.replace("- CARRIED", "- LOST")
    out = check_fields(span, "", JUNE_9_1970, outcome="passed", amended=False, vote=None, summary="")
    assert out.outcome == "refused"


def test_a_lost_amendment_is_not_an_amendment_and_the_main_motion_still_carried() -> None:
    moved = motions(pages.AMENDMENT_LOST_1970)
    assert [(m.amendment, m.verdict) for m in moved] == [
        (False, Verdict.CARRIED),
        (True, Verdict.LOST),
        (False, Verdict.CARRIED),
    ]
    out = check_fields(pages.AMENDMENT_LOST_1970, "", JUNE_9_1970, outcome="passed", amended=True, vote=None,
                       summary="")  # fmt: skip
    assert (out.outcome, out.amended) == ("passed", False)
    assert [(c.field, c.why) for c in out.checks] == [("amended", "the amendment moved was LOST")]


def test_a_carried_amendment_sets_amended() -> None:
    span = pages.AMENDMENT_LOST_1970.replace("- LOST", "- CARRIED")
    out = check_fields(span, "", JUNE_9_1970, outcome="passed", amended=False, vote=None, summary="")
    assert out.amended is True


def test_a_dissent_printed_under_the_motion_is_a_vote() -> None:
    out = check_fields(pages.VOTED_AGAINST_1974, "", JUNE_9_1970, outcome="pending", amended=False, vote=None,
                       summary="")  # fmt: skip
    assert out.vote is not None
    assert (out.vote["noes"], out.vote["noes_names"]) == (1, ["Massey"])
    assert [(c.field, c.result) for c in out.checks] == [("vote", "corrected")]


def test_a_dissent_the_model_already_read_is_left_alone() -> None:
    vote: dict[str, object] = {"ayes": None, "noes": 1, "absent": None, "ayes_names": [], "noes_names": ["Massey"]}
    out = check_fields(pages.VOTED_AGAINST_1974, "", JUNE_9_1970, outcome="pending", amended=False, vote=vote,
                       summary="")  # fmt: skip
    assert (out.vote, out.checks) == (vote, [])


def test_a_year_the_meeting_cannot_name_is_flagged() -> None:
    page = pages.CONTINUED_HEADING_1970
    out = check_fields(page, page, JUNE_9_1970, outcome="passed", amended=False, vote=None,
                       summary=pages.CONTINUED_SUMMARY_1970)  # fmt: skip
    assert [(c.field, c.result) for c in out.checks] == [("summary", "conflict")]
    assert "2019" in out.checks[0].why


def test_a_year_printed_on_the_page_or_soon_after_the_meeting_is_plausible() -> None:
    page = pages.NO_FURTHER_ACTION_1970  # prints "19 70"
    for summary in ("Report dated June 5, 1970.", "To be finished by 1975.", "First built in 1912."):
        out = check_fields(page, page, JUNE_9_1970, outcome="refused", amended=False, vote=None, summary=summary)
        assert out.checks == [], summary
