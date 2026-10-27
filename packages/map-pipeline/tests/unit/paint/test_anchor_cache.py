from pathlib import Path

import numpy as np
import pytest

from qipu_map.paint.anchor import Anchor, AnchorLayer, anchors_for, core_weight, join_layer
from qipu_map.paint.backends import Identity, Replay, Request, make_painter, model_recipe
from qipu_map.paint.grid import Tile
from qipu_map.paint.tilecache import TileCache


def test_core_weight_matches_the_live_ramp() -> None:
    w = core_weight(1024)[..., 0]
    assert w[512, 512] == 1.0
    assert w[512, 223] == 0.0
    assert w[512, 800] == 0.0
    assert w[512, 300] == 1.0
    assert 0 < w[512, 250] < 1


def test_anchors_cover_every_tile() -> None:
    tiles = [Tile(x, y) for x in (0, 512, 1024) for y in (-512, 0)]
    anchors = anchors_for(tiles, 1024)
    assert anchors == sorted(anchors, key=lambda a: (a.y, a.x))
    assert all(a.x % 1024 == 0 and a.y % 1024 == 0 for a in anchors)
    flat = {a: np.full((1024, 1024, 3), 9 * i, np.uint8) for i, a in enumerate(anchors)}
    layer = join_layer(flat, 1024)
    for t in tiles:
        assert layer.context(t, 1024).shape == (1024, 1024, 3)
    a = Anchor(1024, 2048)
    assert a.window(1024) == (512, 1536, 2048)
    assert a.half_res_origin(1024) == (256, 768)


def test_the_layer_is_seamless_for_a_smooth_world() -> None:
    world = np.repeat((np.add.outer(np.arange(400), np.arange(400)) % 255)[..., None], 3, 2).astype(np.float32)
    tiles = [Tile(x, y) for x in (0, 32) for y in (0, 32)]
    painted = {}
    for a in anchors_for(tiles, 64):
        ox, oy = a.half_res_origin(64)
        painted[a] = world[oy + 100 : oy + 164, ox + 100 : ox + 164].astype(np.uint8)
    layer = join_layer(painted, 64)
    ox, oy = layer.origin
    expect = world[oy + 100 : oy + 100 + layer.image.shape[0], ox + 100 : ox + 100 + layer.image.shape[1]]
    inside = layer.image[16:-16, 16:-16].astype(int) - expect[16:-16, 16:-16]
    assert np.abs(inside).max() <= 1


def test_context_outside_the_layer_is_an_error() -> None:
    layer = AnchorLayer(np.zeros((10, 10, 3), np.uint8), (0, 0))
    with pytest.raises(ValueError, match="outside"):
        layer.context(Tile(1024, 0), 64)


def request(level: int = 9, key: str = "nfC", prompt: str = "p") -> Request:
    img = np.arange(64 * 64 * 3, dtype=np.uint32).reshape(64, 64, 3).astype(np.uint8)
    return Request((img,), prompt, 5, key, level, 0, 0, 64)


def test_digest_changes_with_every_input() -> None:
    base = request().digest("r")
    assert base == request().digest("r")
    assert (
        len({base, request(level=8).digest("r"), request(key="nfR1").digest("r"), request(prompt="q").digest("r")}) == 4
    )
    assert request().digest("other model") != base
    changed = request()
    changed.images[0][0, 0, 0] ^= 1
    assert changed.digest("r") != base


def test_cache_hit_miss_and_other_years(tmp_path: Path) -> None:
    img = np.full((8, 8, 3), 77, np.uint8)
    today = TileCache(tmp_path / "2026")
    assert today.get("abc") is None
    assert today.misses == 1
    today.put("abc", img)
    got = today.get("abc")
    assert got is not None
    assert np.array_equal(got, img)
    assert today.hits == 1
    assert not list((tmp_path / "2026").glob(".*"))
    past = TileCache(tmp_path / "1950", also=[tmp_path / "2026"])
    got = past.get("abc")
    assert got is not None
    assert np.array_equal(got, img)
    assert (tmp_path / "1950" / "abc.png").is_file()


def test_identity_and_replay(tmp_path: Path) -> None:
    req = request()
    out = Identity().paint(req)
    assert np.array_equal(out, req.images[-1])
    big = Request(req.images, "p", 1, "k", 9, 0, 0, 128)
    assert Identity().paint(big).shape == (128, 128, 3)
    recipe = model_recipe("m", 4, 1.0)
    TileCache(tmp_path).put(req.digest(recipe), out)
    replay = make_painter("replay", "m", 4, 1.0, tmp_path)
    assert isinstance(replay, Replay)
    assert np.array_equal(replay.paint(req), out)
    with pytest.raises(FileNotFoundError):
        replay.paint(request(prompt="never painted"))
    with pytest.raises(ValueError, match="folder"):
        make_painter("replay", "m", 4, 1.0)
    with pytest.raises(ValueError, match="unknown"):
        make_painter("gan", "m", 4, 1.0)
    assert make_painter("identity", "m", 4, 1.0).recipe == "identity"


def test_the_real_painter_needs_torch() -> None:
    pytest.importorskip("torch", reason="the paint extra is not installed")
    pytest.skip("needs a CUDA GPU")
