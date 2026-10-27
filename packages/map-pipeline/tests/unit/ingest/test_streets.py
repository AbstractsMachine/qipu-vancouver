from __future__ import annotations

import pytest
import shapely

from qipu_map.ingest.normalise import streets as s
from tests.unit.ingest.helpers import fc, line, pt, way

SCALE = (111_320.0 * 0.6526738, 111_320.0)


@pytest.mark.parametrize(
    ("hblock", "name"),
    [
        ("1100-1200 PENDRELL ST", "PENDRELL ST"),
        ("900 BURRARD ST", "BURRARD ST"),
        ("BEACH AV", "BEACH AV"),
        (None, None),
        ("", None),
    ],
)
def test_street_name_drops_the_block_range(hblock: str | None, name: str | None) -> None:
    assert s.street_name(hblock) == name


def test_city_streets_kind_name_and_width() -> None:
    streets = fc(
        (line((0, 0), (20, 0)), {"hblock": "1100 DAVIE ST", "streetuse": "Arterial"}),
        (line((0, 10), (20, 10)), {"hblock": "1100 PENDRELL ST", "streetuse": "Residential"}),
        (line((0, 50), (20, 50)), {"hblock": "1100 X ST", "streetuse": "Recreational"}),
        (line((0, 10), (20, 10)), {"hblock": "1100 PENDRELL ST", "streetuse": "Residential"}),  # published twice
    )
    lanes = fc((line((0, 5), (20, 5)), {"std_street": "LANE A"}))
    rows = s.RowWidths(
        fc((pt(10, 0.2), {"width": "66"}), (pt(10, 10.5), {"width": "33"}), (pt(10, 5), {"width": "?"})), SCALE
    )
    got = sorted((f.props["kind"], f.props["name"], f.props["width_m"]) for f in s.city_streets(streets, lanes, rows))
    assert got == [
        ("arterial", "DAVIE ST", 20.12),  # 66 ft
        ("lane", "LANE A", None),  # 55 m from the nearest label, past the 20 m reach
        ("path", "X ST", None),
        ("residential", "PENDRELL ST", 10.06),  # 33 ft
    ]


def test_no_row_labels_means_no_width() -> None:
    rows = s.RowWidths(fc(), SCALE)
    assert rows.near(line((0, 0), (1, 0))) is None


def test_multilines_get_one_id_per_part() -> None:
    g = shapely.MultiLineString([line((0, 0), (5, 0)), line((10, 0), (15, 0))])
    out = s.city_streets(fc((g, {"hblock": "1 A ST", "streetuse": "Collector"})), fc(), s.RowWidths(fc(), SCALE))
    assert len({f.id for f in out}) == 2
    assert all(f.id.startswith("arterial-") and "#" in f.id for f in out)


def test_osm_adds_paths_and_rail_only() -> None:
    raw = {
        "elements": [
            way(1, line((0, 0), (5, 0)), highway="footway", width="3 m", name="Seawall"),
            way(2, line((0, 1), (5, 1)), highway="footway", footway="sidewalk"),
            way(3, line((0, 2), (5, 2)), highway="residential"),
            way(4, line((0, 3), (5, 3)), railway="tram"),
            way(5, line((0, 4), (5, 4)), railway="rail", tunnel="yes"),
            way(6, line((0, 5), (5, 5)), highway="pedestrian", area="yes"),
            way(7, line((0, 6), (5, 6)), railway="abandoned"),
            {"type": "way", "id": 8, "tags": {"highway": "steps"}, "geometry": [{"lon": 0, "lat": 0}]},
        ]
    }
    got = [(f.id, f.props["kind"], f.props["width_m"], f.props["name"]) for f in s.osm_paths_and_rail(raw)]
    assert got == [("osm-w1", "path", 3.0, "Seawall"), ("osm-w4", "rail", None, None)]
