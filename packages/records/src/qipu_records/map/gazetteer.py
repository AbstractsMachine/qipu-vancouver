"""Put decisions on the map from the places they name.

The model reports places as printed ("#680 East 5th Avenue", "Alberni and Bidwell Streets", "Strathcona"). They are matched
against a gazetteer of present-day civic addresses, street intersections and neighbourhoods published by the city as open data.
Only exact matches are placed: an address, a corner, or a neighbourhood's centre. A street name alone is not placed, because a
point in the middle of a long street would mislead. Old addresses that no longer exist stay unplaced.

The gazetteer is a CSV of ``kind,name,lat,lon`` rows, where ``name`` is already normalised by ``street_key``.
"""

from __future__ import annotations

import csv
import io
import re
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from qipu_records.read.schema import ModelPlace

ORDINALS = {
    "first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th", "sixth": "6th", "seventh": "7th",
    "eighth": "8th", "ninth": "9th", "tenth": "10th", "eleventh": "11th", "twelfth": "12th", "thirteenth": "13th",
    "fourteenth": "14th", "fifteenth": "15th", "sixteenth": "16th", "seventeenth": "17th", "eighteenth": "18th",
    "nineteenth": "19th", "twentieth": "20th",
}  # fmt: skip
STREET_TYPES = {
    "street": "st", "st": "st", "avenue": "av", "ave": "av", "av": "av", "road": "rd", "rd": "rd", "drive": "dr", "dr": "dr",
    "crescent": "cres", "cres": "cres", "place": "pl", "pl": "pl", "boulevard": "blvd", "blvd": "blvd", "court": "ct",
    "lane": "ln", "highway": "hwy", "square": "sq", "mews": "mews", "way": "way", "walk": "walk", "parade": "parade",
}  # fmt: skip
PLURAL_TYPES = {"streets": "street", "avenues": "avenue", "roads": "road", "drives": "drive"}
DIRECTIONS = {"east": "e", "e": "e", "west": "w", "w": "w", "north": "n", "n": "n", "south": "s", "s": "s"}


class Precision(StrEnum):
    ADDRESS = "address"
    INTERSECTION = "intersection"
    AREA = "area"


@dataclass(frozen=True)
class Location:
    lat: float
    lon: float
    precision: Precision
    matched: str


def street_key(name: str) -> str:
    """A street name reduced to one spelling: "East Fifth Avenue" and "E 5TH AV" both become "e 5th av"."""
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    words = [ORDINALS.get(w, w) for w in words]
    if len(words) > 1 and words[-1] in DIRECTIONS and words[-2] in STREET_TYPES:
        words = [words[-1], *words[:-1]]
    if words and words[0] in DIRECTIONS and len(words) > 1:
        words[0] = DIRECTIONS[words[0]]
    if words and words[-1] in STREET_TYPES:
        words[-1] = STREET_TYPES[words[-1]]
    return " ".join(words)


def address_key(number: str, street: str) -> str:
    digits = re.sub(r"\D", "", number)
    return f"{digits} {street_key(street)}" if digits and street else ""


def intersection_key(street_a: str, street_b: str) -> str:
    return " & ".join(sorted((street_key(street_a), street_key(street_b))))


def split_intersection(text: str) -> tuple[str, str] | None:
    """The two streets of "Alberni and Bidwell Streets" or "Main Street at Hastings Street"."""
    match = re.match(r"^\s*(.+?)\s+(?:and|&|at)\s+(.+?)\s*$", text, re.I)
    if not match:
        return None
    first, second = match.groups()
    tail = second.split()[-1].lower()
    if tail in PLURAL_TYPES:
        singular = PLURAL_TYPES[tail].capitalize()
        second = " ".join([*second.split()[:-1], singular])
        if first.split()[-1].lower() not in STREET_TYPES:
            first = f"{first} {singular}"
    return first, second


class Gazetteer:
    def __init__(self, rows: dict[tuple[str, str], tuple[float, float]]) -> None:
        self._rows = rows

    @classmethod
    def load(cls, path: Path) -> Gazetteer:
        with path.open(encoding="utf-8", newline="") as handle:
            return cls({(r["kind"], r["name"]): (float(r["lat"]), float(r["lon"])) for r in csv.DictReader(handle)})

    def __len__(self) -> int:
        return len(self._rows)

    def _get(self, kind: Precision, name: str) -> Location | None:
        point = self._rows.get((kind.value, name))
        return Location(point[0], point[1], kind, name) if point else None

    def locate(self, place: ModelPlace) -> Location | None:
        """The point for one place as the model reported it, or None when nothing matches exactly."""
        text = place.get("text") or ""
        precision = place.get("precision")
        if precision == "address":
            number = place.get("number") or text.split()[0] if text.split() else ""
            street = place.get("street") or " ".join(text.split()[1:])
            for candidate in _without_direction(street):
                found = self._get(Precision.ADDRESS, address_key(number, candidate))
                if found:
                    return found
        if precision == "intersection":
            pair = split_intersection(text)
            if pair:
                return self._get(Precision.INTERSECTION, intersection_key(*pair))
        if precision == "area":
            return self._get(Precision.AREA, (place.get("area") or text).strip().lower())
        return None


def _without_direction(street: str) -> Iterator[str]:
    """The street as printed, then without a leading direction ("South Renfrew Street" is "Renfrew St" today)."""
    yield street
    words = street.split()
    if len(words) > 2 and words[0].lower() in DIRECTIONS:
        yield " ".join(words[1:])


VANCOUVER_DATASETS = "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/{}/exports/csv?delimiter=%2C"


def _open_data_rows(dataset: str) -> Iterator[dict[str, str]]:
    request = urllib.request.Request(VANCOUVER_DATASETS.format(dataset), headers={"User-Agent": "qipu-records/0.1"})
    with urllib.request.urlopen(request, timeout=600) as response:
        yield from csv.DictReader(io.StringIO(response.read().decode("utf-8-sig")))


def _point(row: dict[str, str]) -> tuple[float, float]:
    lat, lon = (float(x) for x in row["geo_point_2d"].split(","))
    return lat, lon


def vancouver_rows() -> Iterator[tuple[str, str, float, float]]:
    """Gazetteer rows from the City of Vancouver's open data (Open Government Licence – Vancouver)."""
    for row in _open_data_rows("property-addresses"):
        if row["civic_number"] and row["std_street"] and row["geo_point_2d"]:
            yield (Precision.ADDRESS, address_key(row["civic_number"], row["std_street"]), *_point(row))
    for row in _open_data_rows("street-intersections"):
        streets = row["xstreet"].split(" AND ")
        if len(streets) == 2 and row["geo_point_2d"]:
            yield (Precision.INTERSECTION, intersection_key(*streets), *_point(row))
    for row in _open_data_rows("local-area-boundary"):
        if row["geo_point_2d"]:
            yield (Precision.AREA, row["name"].strip().lower(), *_point(row))


def write_gazetteer(rows: Iterator[tuple[str, str, float, float]], path: Path) -> int:
    """Write rows to `path` as CSV, the first row winning when a name repeats. Returns the number written."""
    seen: set[tuple[str, str]] = set()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["kind", "name", "lat", "lon"])
        for kind, name, lat, lon in rows:
            if name and (kind, name) not in seen:
                seen.add((kind, name))
                writer.writerow([kind, name, f"{lat:.6f}", f"{lon:.6f}"])
    return len(seen)
