from pathlib import Path

import pytest

from qipu_map.eras.rules import RULES_DIR, Basis, load_rules, rules_for_city, rules_from_dict


def test_vancouver_rules_load_and_every_rule_says_its_kind() -> None:
    rules = rules_for_city("ca/vancouver")
    assert rules.city == "ca/vancouver"
    assert rules.undated.radii_m == (60.0, 120.0, 250.0)
    assert rules.undated.cap_year == 2015
    assert not rules.undated_rail_in_past
    assert rules.dated
    assert all(d.basis in (Basis.SOURCED, Basis.CONVENTION) and d.source for d in rules.dated)
    assert {d.layer for d in rules.dated} == {"streets"}


def test_vancouver_bridge_dates() -> None:
    by_name = {n: d.opened for d in rules_for_city("ca/vancouver").dated for n in d.names}
    assert by_name["Burrard Bridge"] == 1932
    assert by_name["Cambie Bridge"] == 1985
    assert by_name["Georgia Viaduct"] == 1971


def test_evidence_windows() -> None:
    rules = load_rules(RULES_DIR / "vancouver.toml")
    first = rules.evidence_for(1930)
    assert first is not None
    assert first.name == "napl1950"
    later = rules.evidence_for(1955)
    assert later is not None
    assert later.name == "napl1959"
    assert rules.evidence_for(1972) is None


def test_an_explicit_rules_file_wins(tmp_path: Path) -> None:
    text = (RULES_DIR / "vancouver.toml").read_text().replace('city = "ca/vancouver"', 'city = "elsewhere"')
    path = tmp_path / "x.toml"
    path.write_text(text)
    assert rules_for_city("ca/vancouver", path).city == "elsewhere"


def _raw() -> dict[str, object]:
    return {
        "city": "c",
        "undated": {"radii_m": [60], "cap_year": 2015, "fallback_year": 1950, "tall_m": 30, "tall_floor_year": 1960},
        "improved": {"basis": "sourced", "tall_m": 30},
        "standins": {
            "basis": "convention",
            "radius_m": 80.0,
            "min_neighbours": 6,
            "old_share": 0.6,
            "gap_years": 25,
            "fallback_year": 1910,
            "default_height_m": 9.0,
            "early_year": 1930,
            "early_max_height_m": 14.0,
            "evidence_threshold": 0.3,
            "evidence_margin_years": 5,
            "max_overlap": 0.3,
        },
    }


def test_areas_and_dated_buildings_parse() -> None:
    raw = _raw()
    raw["areas"] = [
        {
            "name": "flats",
            "polygon": [[0, 0], [1, 0], [1, 1]],
            "to_year": 1985,
            "basis": "convention",
            "source": "s",
            "water": True,
        }
    ]
    raw["dated"] = [
        {"what": "fix", "layer": "buildings", "basis": "sourced", "source": "s", "ids": [7], "opened": 1975}
    ]
    rules = rules_from_dict(raw)
    area = rules.areas[0]
    assert area.water
    assert area.holds(1950)
    assert not area.holds(1985)
    assert rules.dated[0].matches("7", None)
    assert rules.undated_rail_in_past


def test_a_dated_feature_needs_a_known_layer() -> None:
    raw = _raw()
    raw["dated"] = [{"what": "x", "layer": "trees", "basis": "sourced", "source": "s"}]
    with pytest.raises(ValueError, match="layer"):
        rules_from_dict(raw)
