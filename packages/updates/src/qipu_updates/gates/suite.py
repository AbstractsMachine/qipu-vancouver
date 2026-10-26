"""All gates over one release draft, in the order a reader would check them."""

from __future__ import annotations

import datetime as dt

from qipu_updates.gates import GateResult, PageTexts, dates, outcomes, privacy, quotes, release
from qipu_updates.release.assemble import Draft


def run_all(
    draft: Draft,
    pages: PageTexts,
    *,
    as_of: dt.date,
    embargo_years: int,
    records_before: int | None,
    limits: dict[str, int] | None = None,
) -> list[GateResult]:
    limit = (limits or {}).get
    records = draft.records
    return [
        quotes.check(records, pages, limit("quote_on_page", 0)),
        dates.check(records, pages, limit("date_from_header", 0)),
        outcomes.check(records, limit("proposed_vs_decided", 0)),
        privacy.leaks(records, pages, as_of, embargo_years, limit("privacy_leak", 0)),
        privacy.over_redaction(records, as_of, embargo_years, limit("over_redaction", 0)),
        release.shrink(len(records), records_before, limit("no_shrink", 0)),
        release.files(draft.folder, limit("files_intact", 0)),
        release.corrections(draft.problems, len(draft.manifest.corrections), limit("corrections_applied", 0)),
    ]
