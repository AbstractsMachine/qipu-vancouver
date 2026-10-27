from __future__ import annotations

import numpy as np
import pytest

from qipu_map.model import Raster, Tree, TreeForm
from qipu_map.scene.trees import Listed, canopy, crown_width, form_of, street_tree
from tests.unit.scene import synth


@pytest.mark.parametrize(
    ("genus", "form"),
    [
        ("ACER", TreeForm.BROADLEAF),
        ("Thuja", TreeForm.CONIFER),
        ("PSEUDOTSUGA", TreeForm.CONIFER),
        ("Trachycarpus", TreeForm.PALM),
        (None, TreeForm.BROADLEAF),
    ],
)
def test_form_from_genus(genus: str | None, form: TreeForm) -> None:
    assert form_of(genus) is form


def test_crown_from_the_trunk_capped() -> None:
    assert crown_width(TreeForm.BROADLEAF, 25.4, 10.0) == pytest.approx(2.0 + 0.38 * 10)
    assert crown_width(TreeForm.BROADLEAF, 300.0, 10.0) == 16.0
    assert crown_width(TreeForm.CONIFER, None, 20.0) == pytest.approx(7.0)


def test_street_tree_without_a_height_takes_the_default() -> None:
    t = street_tree(Listed("t1", 1.0, 2.0, "Prunus", None, 30.0, 1990))
    assert t.height_m == 8.0
    assert t.form is TreeForm.BROADLEAF
    assert t.year_planted == 1990


def crowns_field(*tops: tuple[float, float, float]) -> Raster:
    """Height above ground with a cone-shaped crown at each (x, y, height)."""
    r = synth.grid(0.0)
    x, y = synth.centres(r)
    h = np.zeros_like(x)
    for cx, cy, top in tops:
        h = np.maximum(h, top - 1.6 * np.hypot(x - cx, y - cy))
    return Raster(r.x0, r.y0, r.cell, h.astype(np.float32))


def test_canopy_finds_each_crown() -> None:
    field = crowns_field((10.5, 10.5, 12.0), (28.5, 27.5, 9.0))
    found = canopy(field, np.zeros(field.data.shape, dtype=bool), [])
    assert len(found) == 2
    tall = max(found, key=lambda t: t.height_m)
    assert (tall.x, tall.y, tall.height_m) == (10.5, 10.5, 12.0)
    assert 4.0 < tall.crown_m < 16.0


def test_canopy_skips_buildings_and_register_trees() -> None:
    field = crowns_field((10.0, 10.0, 12.0), (28.0, 28.0, 9.0))
    roofs = np.zeros(field.data.shape, dtype=bool)
    roofs[:20, 20:] = True  # the north-east quarter is a building
    listed = [Tree("st-1", 10.0, 10.0, 12.0, 8.0, TreeForm.BROADLEAF)]
    assert canopy(field, roofs, listed) == []


def test_no_canopy_on_low_ground() -> None:
    assert canopy(synth.grid(1.0), np.zeros((synth.SIZE, synth.SIZE), dtype=bool), []) == []
