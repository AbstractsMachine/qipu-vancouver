from __future__ import annotations

import math

import numpy as np
import pytest
import shapely

from qipu_map.model import Raster, RoofForm
from qipu_map.scene.roofs import classify
from tests.unit.scene import synth

HOUSE = shapely.box(*synth.HOUSE)


def test_flat_roof() -> None:
    fit = classify(HOUSE, synth.flat())
    assert fit is not None
    assert fit.form is RoofForm.FLAT


def test_gable_along_the_long_side() -> None:
    fit = classify(HOUSE, synth.gable(slope=0.9))
    assert fit is not None
    assert fit.form is RoofForm.GABLE
    assert not fit.ridge_across
    assert fit.pitch_deg == pytest.approx(math.degrees(math.atan(0.9)), abs=3)


def test_gable_across_the_long_side() -> None:
    fit = classify(HOUSE, synth.gable(slope=0.7, along_y=False))
    assert fit is not None
    assert fit.form is RoofForm.GABLE
    assert fit.ridge_across


def test_hip_roof() -> None:
    fit = classify(HOUSE, synth.hip(slope=0.9))
    assert fit is not None
    assert fit.form is RoofForm.HIP


def test_low_pitch_reads_as_pitched_when_a_roof_model_fits_it() -> None:
    """A 1970s house's 10 degree roof: neither level nor steep by the slope rule, but the gable fits it."""
    fit = classify(HOUSE, synth.gable(slope=math.tan(math.radians(10))))
    assert fit is not None
    assert fit.form is RoofForm.GABLE


def test_a_single_sloping_plane_is_left_to_the_type() -> None:
    shed = synth.with_roof(synth.HOUSE, lambda x, _y: 4.0 + 0.6 * (x - 10.0))
    assert classify(HOUSE, shed) is None


def test_too_small_to_read() -> None:
    assert classify(shapely.box(10, 10, 14, 14), synth.flat()) is None


def test_mostly_void_is_unknown() -> None:
    dsm = synth.flat()
    data = dsm.data.copy()
    data[14:30, 10:20] = np.nan
    assert classify(HOUSE, Raster(dsm.x0, dsm.y0, dsm.cell, data)) is None


def test_outside_the_raster_is_unknown() -> None:
    assert classify(shapely.box(100, 100, 120, 120), synth.flat()) is None


def test_a_rough_surface_is_unknown() -> None:
    rng = np.random.default_rng(1)
    dsm = synth.with_roof(synth.HOUSE, lambda x, _y: 8.0 + rng.uniform(-3, 3, size=x.shape))
    assert classify(HOUSE, dsm) is None
