"""Have a model read the pages of a collection.

Reading is the only step that costs money. Each call sends at most ``max_pages`` pages to the model, whether or not their
answers turn out usable, so a mistake costs a few cents, not a whole run. Pages already read are skipped, so it can be run
again to continue.
"""

from __future__ import annotations

import logging

from qipu_records.cities import City
from qipu_records.collection import Collection
from qipu_records.read import schema
from qipu_records.read.readers import Reader, ReaderError

log = logging.getLogger(__name__)

MIN_PAGE_CHARS = 300
"""Pages with less text are covers, blank leaves or plates; they are not sent to the model."""


def read_pages(collection: Collection, reader: Reader, city: City, max_pages: int) -> int:
    """Send up to `max_pages` pages not read yet to the model and store the usable answers. Returns the number stored.

    A page whose answer is unusable is logged and left for the next run; it still counts towards `max_pages`. A reader that
    cannot work at all raises ReaderConfigError on the first page, before any request is made.
    """
    system_prompt = city.system_prompt()
    items = collection.items()
    done = collection.readings()
    pages = collection.pages()
    sent = stored = 0
    for index, page in enumerate(pages):
        if sent >= max_pages:
            break
        if page.page_id in done or len(page.text.strip()) < MIN_PAGE_CHARS:
            continue
        before = pages[index - 1] if index else None
        previous = before.text if before and before.item == page.item and before.n == page.n - 1 else ""
        year = _year(items[page.item].date)
        sent += 1
        try:
            reading = reader.read(page.page_id, system_prompt, schema.user_message(previous, page.text, year))
        except ReaderError as error:
            log.warning("%s", error)
            continue
        collection.append_reading(reading)
        stored += 1
        log.info("%s: %d items", page.page_id, len(reading.items))
    if sent > stored:
        log.warning("%d of %d pages gave no usable answer and will be sent again on the next run", sent - stored, sent)
    return stored


def _year(date: str | None) -> int | None:
    return int(date[:4]) if date and date[:4].isdigit() else None
