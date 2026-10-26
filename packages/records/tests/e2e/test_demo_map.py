"""`make demo`, then the map page in a headless browser: the expected decisions are listed and placed, and their links work.

Needs a Chromium for Playwright (`playwright install chromium`) and the network: MapLibre and the basemap load from the web,
and two of the archive.org page links are requested to check they resolve.
"""

from __future__ import annotations

import functools
import json
import re
import subprocess
import sys
import threading
import urllib.request
from collections.abc import Iterator
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

import pytest

from tests.conftest import ROOT

if TYPE_CHECKING:
    from playwright.sync_api import Page

sync_api = pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.e2e

EXPECTED_PLACES = ["1139 Pendrell Street", "Alberni and Bidwell Streets", "2777 Oak Street", "#680 East 5th Avenue", "Strathcona"]


@pytest.fixture(scope="module")
def demo() -> list[dict[str, object]]:
    subprocess.run(["make", "demo", f"PYTHON={sys.executable}"], cwd=ROOT, check=True, capture_output=True)
    layer = json.loads((ROOT / "build" / "demo" / "decisions.geojson").read_text(encoding="utf-8"))
    features: list[dict[str, object]] = layer["features"]
    return features


@pytest.fixture(scope="module")
def site() -> Iterator[str]:
    handler = functools.partial(_QuietHandler, directory=str(ROOT))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="module")
def page(demo: list[dict[str, object]], site: str) -> Iterator[Page]:
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        tab = browser.new_page(viewport={"width": 1280, "height": 800})
        errors: list[str] = []
        tab.on("pageerror", lambda error: errors.append(str(error)))
        tab.goto(f"{site}/map-preview/")
        tab.wait_for_selector("#list li")
        tab.wait_for_function("() => window.mapReady === true", timeout=30_000)
        yield tab
        assert errors == []
        browser.close()


def test_every_placed_decision_is_listed(page: Page, demo: list[dict[str, object]]) -> None:
    assert page.text_content("#caption") == f"{len(demo)} of {len(demo)} placed decisions"
    listed = page.inner_text("#list")
    for place in EXPECTED_PLACES:
        assert place in listed


def test_the_map_draws_one_point_per_placed_decision(page: Page, demo: list[dict[str, object]]) -> None:
    drawn = page.evaluate("() => map.queryRenderedFeatures({ layers: ['decisions'] }).length")
    assert drawn == len(demo)


def test_clicking_a_decision_opens_its_card(page: Page) -> None:
    page.get_by_text("Council approved acquiring 1139 Pendrell Street as a park site.").first.click()
    popup = page.wait_for_selector(".maplibregl-popup-content")
    assert popup is not None
    assert "Acquisition for Park Site - 1139 Pendrell Street" in popup.inner_text()


def test_the_year_slider_filters_the_list(page: Page) -> None:
    page.fill("#year", "1970")
    page.dispatch_event("#year", "input")
    assert page.text_content("#caption") == "1 of 9 placed decisions"
    page.fill("#year", "1974")
    page.dispatch_event("#year", "input")
    assert page.text_content("#caption") == "9 of 9 placed decisions"


def test_a_data_file_cannot_smuggle_in_a_script_link(page: Page) -> None:
    href = page.evaluate("() => archiveLink('javascript:alert(1)')")
    assert href is None
    assert page.evaluate("() => archiveLink('https://archive.org/details/19740219/page/n4')") is not None


def test_page_links_point_at_the_right_scan(page: Page, demo: list[dict[str, object]]) -> None:
    links = page.eval_on_selector_all("#list a", "nodes => nodes.map(n => n.href)")
    assert len(links) == len(demo)
    assert all(re.fullmatch(r"https://archive\.org/details/(19700609|19740219)/page/n\d+", link) for link in links)
    for link in sorted(set(links))[:2]:
        request = urllib.request.Request(link, method="HEAD", headers={"User-Agent": "qipu-records-tests/0.1"})
        with urllib.request.urlopen(request, timeout=60) as response:
            assert response.status == 200
