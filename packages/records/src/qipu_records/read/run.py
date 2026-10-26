"""Have a model read the pages of a collection.

Reading is the only step that costs money. It reads at most ``max_pages`` pages per call, so a mistake costs a few cents, not
a whole run, and pages already read are skipped, so it can be run again to continue.
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
    """Have the model read pages not read yet, up to `max_pages`. Returns the number read."""
    system_prompt = city.system_prompt()
    items = collection.items()
    done = collection.readings()
    pages = collection.pages()
    count = 0
    for index, page in enumerate(pages):
        if count >= max_pages:
            break
        if page.page_id in done or len(page.text.strip()) < MIN_PAGE_CHARS:
            continue
        previous = pages[index - 1].text if index and pages[index - 1].item == page.item else ""
        year = _year(items[page.item].date)
        try:
            reading = reader.read(page.page_id, system_prompt, schema.user_message(previous, page.text, year))
        except ReaderError as error:
            log.warning("%s", error)
            continue
        collection.append_reading(reading)
        count += 1
        log.info("%s: %d items", page.page_id, len(reading.items))
    return count


def _year(date: str | None) -> int | None:
    return int(date[:4]) if date and date[:4].isdigit() else None
