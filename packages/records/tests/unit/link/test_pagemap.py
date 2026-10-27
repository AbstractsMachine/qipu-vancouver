import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from qipu_records.fetch.archive import book_prefix
from qipu_records.link.pagemap import build_map, fetch_map, manifest_zip, page_url, shown_images, zip_images
from tests.conftest import SavedArchive

LISTING = """<a href="/download/x/x_jp2.zip/x_jp2%2Fx_0000.jp2">x_0000.jp2</a>
<a href="/download/x/x_jp2.zip/x_jp2%2Fx_0001.jp2">x_0001.jp2</a>
<a href="/download/x/x_jp2.zip/x_jp2%2Fx_0002.jp2">x_0002.jp2</a>
<a href="/download/x/x_jp2.zip/x_jp2%2Fx_0003.jp2">x_0003.jp2</a>"""


def _manifest(files: list[str]) -> dict[str, object]:
    pages = [
        {"uri": f"https://ia.example/BookReader/BookReaderImages.php?zip=/x/x_jp2.zip&file=x_jp2/{f}"} for f in files
    ]
    return {"data": {"brOptions": {"data": [[page] for page in pages]}}}


def test_zip_listing_gives_image_names_in_order() -> None:
    assert zip_images(LISTING) == ["x_0000.jp2", "x_0001.jp2", "x_0002.jp2", "x_0003.jp2"]


def test_hidden_cover_shifts_every_later_page() -> None:
    manifest = _manifest(["x_0001.jp2", "x_0002.jp2", "x_0003.jp2"])
    assert manifest_zip(manifest) == "x_jp2.zip"
    page_map = build_map(zip_images(LISTING), shown_images(manifest))
    assert page_map == [None, 0, 1, 2]
    assert page_url("x", 2, page_map) == "https://archive.org/details/x/page/n1"
    assert page_url("x", 0, page_map) is None


def test_hidden_leaf_in_the_middle() -> None:
    page_map = build_map(zip_images(LISTING), shown_images(_manifest(["x_0000.jp2", "x_0001.jp2", "x_0003.jp2"])))
    assert page_map == [0, 1, None, 2]


def test_lists_that_disagree_give_no_map_and_no_link() -> None:
    page_map = build_map(zip_images(LISTING), shown_images(_manifest(["y_0001.jp2"])))
    assert page_map is None
    assert page_url("x", 1, page_map) is None


def test_page_outside_the_map_has_no_link() -> None:
    assert page_url("x", 9, [0, 1]) is None


def test_book_prefix_is_read_from_the_file_list() -> None:
    record = {
        "metadata": {"identifier": "19700609"},
        "files": [{"name": "1970-06-09_jp2.zip"}, {"name": "1970-06-09.pdf"}],
    }
    assert book_prefix(record) == "1970-06-09"
    assert book_prefix({"metadata": {"identifier": "abc"}, "files": []}) == "abc"


def test_map_of_a_real_item_from_its_saved_responses(saved_archive: SavedArchive) -> None:
    assert fetch_map(saved_archive, "19700609") == [0, 1, 2, 3, 4]


class _OddArchive(SavedArchive):
    """The saved item, with archive.org's metadata changed by `edit`."""

    def __init__(self, cache_dir: Path, edit: Callable[[dict[str, Any]], None]) -> None:
        super().__init__(cache_dir)
        self.edit = edit

    def get_text(self, url: str, cache_name: str) -> str:
        text = super().get_text(url, cache_name)
        if url.startswith("https://archive.org/metadata/"):
            record = json.loads(text)
            self.edit(record)
            text = json.dumps(record)
        return text


@pytest.mark.parametrize(
    "edit",
    [
        lambda r: r.update(server="evil.example.com"),  # never build a URL on a host that is not archive.org's
        lambda r: r.pop("dir"),  # an unexpected shape is no page map, not a failed fetch
    ],
)
def test_odd_metadata_gives_no_page_map(tmp_path: Path, edit: Callable[[dict[str, Any]], None]) -> None:
    assert fetch_map(_OddArchive(tmp_path, edit), "19700609") is None
