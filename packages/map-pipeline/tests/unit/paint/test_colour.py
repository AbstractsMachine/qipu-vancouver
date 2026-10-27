import numpy as np

from qipu_map.paint.colour import chroma, lab_to_rgb, restore, rgb_to_lab


def test_lab_round_trip() -> None:
    rgb = np.random.default_rng(0).integers(0, 256, (16, 16, 3), dtype=np.uint8)
    assert np.abs(lab_to_rgb(rgb_to_lab(rgb)).astype(int) - rgb).max() <= 1
    grey = np.full((2, 2, 3), 128, np.uint8)
    assert float(np.max(chroma(rgb_to_lab(grey)))) < 0.5


def test_restore_gives_back_saturation_and_contrast() -> None:
    rng = np.random.default_rng(1)
    render = rng.integers(20, 236, (96, 96, 3), dtype=np.uint8)
    render = np.repeat(np.repeat(render[::8, ::8], 8, 0), 8, 1)  # blocks, so the low frequencies carry the colour
    mean = render.astype(np.float32).mean(-1, keepdims=True)
    washed = np.clip(mean + 0.7 * (render - mean), 0, 255)
    washed = np.clip(128 + 0.75 * (washed - 128), 0, 255).astype(np.uint8)
    out = restore(washed, render)

    def sat(a: np.ndarray) -> float:
        return float(chroma(rgb_to_lab(a)).mean())

    assert sat(out) > sat(washed) * 1.15
    assert out.astype(np.float32).std() > washed.astype(np.float32).std() * 1.15
    same = restore(render, render)
    assert np.abs(same.astype(int) - render).mean() < 3
