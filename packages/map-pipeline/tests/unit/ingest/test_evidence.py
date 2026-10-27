from pathlib import Path

import numpy as np

from qipu_map.ingest.normalise.evidence import write_evidence
from qipu_map.ingest.raw import RawStore
from qipu_map.model import Raster
from qipu_map.sample import SAMPLE_RAW


def test_masks_become_rasters_of_shares(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    share = np.array([[0, 255], [153, 51]], np.uint8)
    np.savez_compressed(raw / "photo1950_built.npz", share=share, x0=-10.0, y0=20.0, cell=4.0)
    assert write_evidence(RawStore(raw), tmp_path / "out") == ["photo1950"]
    r = Raster.load(tmp_path / "out" / "evidence" / "photo1950.npz")
    assert (r.x0, r.y0, r.cell) == (-10.0, 20.0, 4.0)
    assert np.allclose(r.data, [[0.0, 1.0], [0.6, 0.2]])


def test_no_masks_no_folder(tmp_path: Path) -> None:
    assert write_evidence(RawStore(tmp_path), tmp_path / "out") == []
    assert not (tmp_path / "out" / "evidence").exists()


def test_the_sample_masks_cover_the_west_end() -> None:
    names = sorted(p.name for p in SAMPLE_RAW.glob("*_built.npz"))
    assert names == ["napl1950_built.npz", "napl1959_built.npz"]
    with np.load(SAMPLE_RAW / names[0]) as z:
        built = z["share"] / 255.0
    assert 0.4 < float(np.mean(built)) < 0.7  # a built-up district with English Bay in one corner
