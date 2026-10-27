from pathlib import Path

import numpy as np
import pytest

from qipu_map.classes import CLASS_COLOURS, SurfaceClass
from qipu_map.render.passes import (
    class_colours,
    classes_from_rgb,
    decode_ids,
    encode_ids,
    id_colour,
    read_png,
    write_png,
)


def test_ids_round_trip_through_rgb() -> None:
    ids = np.array([[0, 1, 255], [256, 65_536, (1 << 24) - 1]], dtype=np.uint32)
    assert (decode_ids(encode_ids(ids)) == ids).all()


def test_ids_beyond_24_bits_are_refused() -> None:
    with pytest.raises(ValueError, match="24 bits"):
        encode_ids(np.array([1 << 24], dtype=np.uint32))


def test_id_colour_is_one_plus_the_index() -> None:
    assert id_colour(0) == (0, 0, 1)
    assert id_colour(70_000) == (1, 17, 113)
    assert decode_ids(np.array([[id_colour(70_000)]], dtype=np.uint8))[0, 0] == 70_001


def test_flat_colours_map_back_to_classes_even_when_a_little_off() -> None:
    order = list(SurfaceClass)
    rgb = np.array([[CLASS_COLOURS[c] for c in order]], dtype=np.int32)
    rgb[0, 1] += (3, -2, 1)
    got = classes_from_rgb(np.clip(rgb, 0, 255).astype(np.uint8))
    assert got.tolist() == [[int(c) for c in order]]


def test_class_colours_paint_ids() -> None:
    a = np.array([[int(SurfaceClass.WATER), int(SurfaceClass.ROOF)]], dtype=np.uint8)
    assert class_colours(a).tolist() == [
        [list(CLASS_COLOURS[SurfaceClass.WATER]), list(CLASS_COLOURS[SurfaceClass.ROOF])]
    ]


def test_png_round_trip_is_byte_stable(tmp_path: Path) -> None:
    a = np.arange(64, dtype=np.uint8).reshape(8, 8)
    write_png(tmp_path / "a.png", a)
    write_png(tmp_path / "b.png", a)
    assert (tmp_path / "a.png").read_bytes() == (tmp_path / "b.png").read_bytes()
    assert (read_png(tmp_path / "a.png") == a).all()
