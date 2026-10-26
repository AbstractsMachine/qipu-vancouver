from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import pytest

from qipu_records.map import gazetteer
from qipu_records.map.gazetteer import Gazetteer, Precision, intersection_key, split_intersection, street_key, write_gazetteer
from qipu_records.read.schema import ModelPlace


@pytest.mark.parametrize(
    ("printed", "key"),
    [
        ("East 5th Avenue", "e 5th av"),
        ("E 5TH AV", "e 5th av"),
        ("East Fifth Avenue", "e 5th av"),
        ("Fifth Avenue East", "e 5th av"),
        ("Point Grey Road", "point grey rd"),
        ("KNIGHT ST", "knight st"),
    ],
)
def test_street_key(printed: str, key: str) -> None:
    assert street_key(printed) == key


def test_split_intersection_shares_the_plural_type() -> None:
    assert split_intersection("Alberni and Bidwell Streets") == ("Alberni Street", "Bidwell Street")
    assert split_intersection("Main Street at Hastings Street") == ("Main Street", "Hastings Street")
    assert split_intersection("Strathcona") is None
    assert intersection_key("BIDWELL ST", "ALBERNI ST") == intersection_key("Alberni Street", "Bidwell Street")


@pytest.fixture
def places(tmp_path: Path) -> Gazetteer:
    rows = [
        (Precision.ADDRESS, "680 e 5th av", 49.2658, -123.0896),
        (Precision.ADDRESS, "23 renfrew st", 49.2843, -123.0445),
        (Precision.INTERSECTION, intersection_key("ALBERNI ST", "BIDWELL ST"), 49.2911, -123.1328),
        (Precision.AREA, "strathcona", 49.2782, -123.0882),
        (Precision.ADDRESS, "680 e 5th av", 0.0, 0.0),
    ]
    path = tmp_path / "gazetteer.csv"
    assert write_gazetteer(iter(rows), path) == 4
    return Gazetteer.load(path)


def test_locate_address_with_a_hash_sign(places: Gazetteer) -> None:
    found = places.locate({"text": "#680 East 5th Avenue", "street": "East 5th Avenue", "number": "680", "precision": "address"})
    assert found is not None
    assert (found.lat, found.precision) == (49.2658, Precision.ADDRESS)


def test_locate_address_whose_direction_was_dropped(places: Gazetteer) -> None:
    place: ModelPlace = {
        "text": "23 South Renfrew Street",
        "street": "South Renfrew Street",
        "number": "23",
        "precision": "address",
    }
    assert places.locate(place) is not None


def test_locate_intersection_and_area(places: Gazetteer) -> None:
    assert places.locate({"text": "Alberni and Bidwell Streets", "precision": "intersection"}) is not None
    assert places.locate({"text": "Strathcona Linear Park", "area": "Strathcona", "precision": "area"}) is not None


def test_a_street_alone_is_not_placed(places: Gazetteer) -> None:
    assert places.locate({"text": "Renfrew Street", "street": "Renfrew Street", "precision": "street"}) is None
    assert (
        places.locate({"text": "4885 Boundary Road", "street": "Boundary Road", "number": "4885", "precision": "address"}) is None
    )


OPEN_DATA = {
    "property-addresses": [
        {"civic_number": "1139", "std_street": "PENDRELL ST", "geo_point_2d": "49.28194677675412, -123.13087501201407"},
        {"civic_number": "", "std_street": "PENDRELL ST", "geo_point_2d": "49.28, -123.13"},
    ],
    "street-intersections": [
        {"xstreet": "BIDWELL ST AND ALBERNI ST", "geo_point_2d": "49.29116224852154, -123.13279902221464"},
    ],
    "local-area-boundary": [{"name": "Strathcona", "geo_point_2d": "49.27822, -123.088235"}],
}


def test_vancouver_open_data_becomes_gazetteer_rows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(gazetteer, "_open_data_rows", lambda dataset: iter(OPEN_DATA[dataset]))
    path = tmp_path / "vancouver.csv"
    assert gazetteer.write_gazetteer(gazetteer.vancouver_rows(), path) == 3
    loaded = Gazetteer.load(path)
    assert len(loaded) == 3
    assert loaded.locate({"text": "1139 Pendrell Street", "precision": "address"}) is not None
    assert loaded.locate({"text": "Alberni and Bidwell Streets", "precision": "intersection"}) is not None


def test_open_data_export_is_read_as_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    body = '﻿name,geo_point_2d\nStrathcona,"49.27822, -123.088235"\n'.encode()

    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: Response(body))
    assert list(gazetteer._open_data_rows("local-area-boundary")) == [
        {"name": "Strathcona", "geo_point_2d": "49.27822, -123.088235"}
    ]
