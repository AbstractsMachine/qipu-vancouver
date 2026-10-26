"""Turn an OCR page number into the page the archive.org viewer shows.

Two numberings meet in every link to a scanned page:

* the OCR page: archive.org makes one OCR page per image in the item's page-image zip, in file order, hidden images
  included;
* the viewer page: the ``n`` in ``https://archive.org/details/<item>/page/n<n>``. The viewer lists only the images its
  manifest shows. A colour card, a blank cover or a calibration target is hidden, and every later page shifts.

So the viewer page of OCR page ``k`` is the position, among the shown images, of the image OCR page ``k`` was made from.
Both lists come from archive.org itself. When they do not fit together the item gets no map, and its decisions get no
page link rather than a wrong one.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from collections.abc import Sequence
from typing import Any

from qipu_records.fetch.archive import ArchiveClient, book_prefix, fetch_metadata

PageMap = list[int | None]
"""For each OCR page, its viewer page, or None when the viewer hides that image."""

_IMAGE = re.compile(r"\.(?:jp2|tif|tiff|jpg|jpeg|png)$", re.I)


def zip_images(listing_html: str) -> list[str]:
    """Image file names in a page-image zip, from archive.org's HTML listing of the zip."""
    names: set[str] = set()
    for href in re.findall(r'href="([^"]+)"', listing_html):
        name = urllib.parse.unquote(href).split("/")[-1]
        if _IMAGE.search(name) and "_" in name:
            names.add(name)
    return sorted(names)


def _manifest_pages(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    data = manifest["data"]["brOptions"]["data"] if "data" in manifest else manifest["brOptions"]["data"]
    return [page for spread in data for page in spread]


def _query_value(uri: str, key: str) -> str | None:
    match = re.search(rf"[?&]{key}=([^&]+)", uri)
    return urllib.parse.unquote(match.group(1)).split("/")[-1] if match else None


def shown_images(manifest: dict[str, Any]) -> list[str | None]:
    """Image file names the viewer shows, in viewer order, from its BookReader manifest."""
    return [_query_value(page.get("uri", ""), "file") for page in _manifest_pages(manifest)]


def manifest_zip(manifest: dict[str, Any]) -> str | None:
    """The page-image zip the viewer reads its images from."""
    for page in _manifest_pages(manifest):
        name = _query_value(page.get("uri", ""), "zip")
        if name:
            return name
    return None


def build_map(images: Sequence[str], shown: Sequence[str | None]) -> PageMap | None:
    """The viewer page of each OCR page, or None when the two lists do not fit together."""
    position = {name: n for n, name in enumerate(shown) if name}
    if not images or not position or any(name not in set(images) for name in position):
        return None
    return [position.get(name) for name in images]


def page_url(item: str, ocr_page: int, page_map: PageMap | None) -> str | None:
    """The archive.org viewer link of an OCR page, or None when it cannot be placed exactly."""
    if page_map is None or not 0 <= ocr_page < len(page_map):
        return None
    viewer_page = page_map[ocr_page]
    if viewer_page is None:
        return None
    return f"https://archive.org/details/{item}/page/n{viewer_page}"


def fetch_map(client: ArchiveClient, item: str) -> PageMap | None:
    """Build an item's page map from archive.org's metadata, viewer manifest and zip listing (cached by the client)."""
    metadata = fetch_metadata(client, item)
    if "server" not in metadata:
        return None
    query = urllib.parse.urlencode(
        {
            "id": item,
            "itemPath": metadata["dir"],
            "server": metadata["server"],
            "format": "jsonp",
            "subPrefix": book_prefix(metadata),
        }
    )
    manifest = json.loads(
        client.get_text(f"https://{metadata['server']}/BookReader/BookReaderJSIA.php?{query}", f"{item}.br.json")
    )
    names = [f["name"] for f in metadata.get("files", [])]
    zip_name = manifest_zip(manifest)
    if zip_name not in names:
        zip_name = _fallback_zip(names)
    if zip_name is None:
        return None
    listing = client.get_text(
        f"https://archive.org/download/{item}/{urllib.parse.quote(zip_name)}/", f"{item}.zip.html"
    )
    return build_map(zip_images(listing), shown_images(manifest))


def _fallback_zip(names: Sequence[str]) -> str | None:
    """The item's JP2 zip, else any page-image zip that is not the original upload."""
    zips = [n for n in names if re.search(r"_(jp2|tif|jpg)\.zip$", n)]
    zips.sort(key=lambda n: (not n.endswith("_jp2.zip"), "_orig_" in n, n))
    return zips[0] if zips else None
