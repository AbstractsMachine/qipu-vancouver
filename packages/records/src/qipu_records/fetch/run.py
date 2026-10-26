"""Fetch archive.org items into a collection: catalogue metadata, the OCR text of each page and the page map.

Items already in the collection are skipped, and the collection is saved after each item, so the step can be stopped and
started again. An item archive.org has no OCR for is skipped with a warning.
"""

from __future__ import annotations

import logging
import urllib.error
from collections.abc import Iterable

from qipu_records.collection import Collection, Page, make_page_id
from qipu_records.fetch.archive import ArchiveClient, fetch_item, fetch_page_texts
from qipu_records.link.pagemap import fetch_map

log = logging.getLogger(__name__)


def fetch_items(collection: Collection, client: ArchiveClient, identifiers: Iterable[str]) -> int:
    """Add items and their OCR pages and page maps to the collection. Returns the number of pages added."""
    items = collection.items() if collection.path("items.json").exists() else {}
    pages = collection.pages() if collection.path("pages.jsonl").exists() else []
    maps = collection.page_maps()
    added = 0
    for identifier in identifiers:
        if identifier in items:
            continue
        item = fetch_item(client, identifier)
        try:
            texts = fetch_page_texts(client, identifier)
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            log.warning("%s: skipped, archive.org has no OCR text for it (or no such item)", identifier)
            continue
        items[identifier] = item
        pages.extend(Page(make_page_id(identifier, n), identifier, n, text) for n, text in enumerate(texts))
        maps[identifier] = fetch_map(client, identifier)
        added += len(texts)
        log.info("%s: %d pages, page map %s", identifier, len(texts), "found" if maps[identifier] else "missing")
        collection.save_items(items.values())
        collection.save_pages(pages)
        collection.save_page_maps(maps)
    return added
