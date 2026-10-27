"""The files a run reads and writes, all in one folder.

    items.json        the archive.org items read, with their catalogue metadata
    pages.jsonl       one OCR page per line: {"page_id", "item", "n", "text"}
    pagemaps.json     {item: [viewer page or null per OCR page]}
    readings.jsonl    the model's answer for each page: {"page_id", "model", "prompt_version", "items"}

`build` writes its output next to them: decisions.jsonl, decisions.geojson, rejected.jsonl and summary.json. Every file
is plain JSON, so it can be read without this package.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from qipu_records.fetch.archive import Item
from qipu_records.link.pagemap import PageMap
from qipu_records.read.readers import Reading, load_readings


@dataclass(frozen=True)
class Page:
    page_id: str
    item: str
    n: int
    """The OCR page index within the item, from 0."""
    text: str


def make_page_id(item: str, n: int) -> str:
    return f"{item}:{n}"


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            if line.strip():
                yield json.loads(line)


def write_jsonl(path: Path, rows: Iterable[Mapping[str, object]]) -> int:
    count = 0
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    tmp.replace(path)
    return count


def write_json(path: Path, data: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


class Collection:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.folder / name

    def items(self) -> dict[str, Item]:
        rows = json.loads(self.path("items.json").read_text(encoding="utf-8"))
        return {row["identifier"]: Item(**row) for row in rows}

    def save_items(self, items: Iterable[Item]) -> None:
        write_json(self.path("items.json"), [asdict(item) for item in items])

    def pages(self) -> list[Page]:
        pages = [Page(**row) for row in read_jsonl(self.path("pages.jsonl"))]
        return sorted(pages, key=lambda p: (p.item, p.n))

    def save_pages(self, pages: Iterable[Page]) -> int:
        return write_jsonl(self.path("pages.jsonl"), (asdict(page) for page in pages))

    def page_maps(self) -> dict[str, PageMap | None]:
        path = self.path("pagemaps.json")
        maps: dict[str, PageMap | None] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return maps

    def save_page_maps(self, maps: dict[str, PageMap | None]) -> None:
        write_json(self.path("pagemaps.json"), maps)

    def readings(self) -> dict[str, Reading]:
        path = self.path("readings.jsonl")
        if not path.exists():
            return {}
        return load_readings(path)

    def append_reading(self, reading: Reading) -> None:
        row = {
            "page_id": reading.page_id,
            "model": reading.model,
            "prompt_version": reading.prompt_version,
            "items": reading.items,
        }
        with self.path("readings.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
