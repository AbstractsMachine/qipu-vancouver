"""Colour helpers: sRGB to CIELAB and back, and the pooled colour restore.

FLUX hands back tiles with 20-30 % less saturation and contrast than its input. The pooled restore gives the painted
canvas back the render's global contrast and saturation while keeping the painted detail. It is one transform computed
over the whole canvas, so it is the same everywhere and makes no step at tile joins:

- luminance: the painted canvas's low frequencies are histogram-matched to the render's, and the painted detail is
  added back with a gain (capped at 1.5) that brings its detail contrast to the render's;
- chroma: per hue range (12 bins of the CbCr angle), a gain of render mean chroma over painted mean chroma, clipped to
  1.0-1.8 and smoothed across neighbouring bins.

It is off by default: a global pull toward the render's colour takes away the painted look. It is kept for renders whose
lighting is far from the model's.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from qipu_map.imageops import gaussian

RGB = NDArray[np.uint8]
Floats = NDArray[np.float32]

_XYZ = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]], np.float32)
_WHITE = np.array([0.95047, 1.0, 1.08883], np.float32)
_YCC = np.array([[0.299, 0.587, 0.114], [-0.168736, -0.331264, 0.5], [0.5, -0.418688, -0.081312]], np.float32)


def rgb_to_lab(rgb: RGB) -> Floats:
    """8-bit sRGB pixels to CIELAB (D65), L from 0 to 100."""
    c = rgb.astype(np.float32) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = c @ _XYZ.T / _WHITE
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    lab = np.stack([116.0 * f[..., 1] - 16.0, 500.0 * (f[..., 0] - f[..., 1]), 200.0 * (f[..., 1] - f[..., 2])], -1)
    return lab.astype(np.float32)


def lab_to_rgb(lab: Floats) -> RGB:
    """Lab pixels (D65) to 8-bit sRGB, clipped to the gamut."""
    fy = (lab[..., 0] + 16.0) / 116.0
    f = np.stack([fy + lab[..., 1] / 500.0, fy, fy - lab[..., 2] / 200.0], -1)
    xyz = np.where(f > 0.206893, f**3, (f - 16.0 / 116.0) / 7.787) * _WHITE
    c = np.clip(xyz @ np.linalg.inv(_XYZ).T, 0.0, 1.0)
    c = np.where(c > 0.0031308, 1.055 * c ** (1.0 / 2.4) - 0.055, 12.92 * c)
    out: RGB = np.clip(c * 255.0 + 0.5, 0, 255).astype(np.uint8)
    return out


def chroma(lab: Floats) -> Floats:
    """Chroma (distance from grey in the a-b plane) of each Lab pixel."""
    out: Floats = np.hypot(lab[..., 1], lab[..., 2]).astype(np.float32)
    return out


def _ycc(rgb: RGB) -> Floats:
    out: Floats = (rgb.astype(np.float32) @ _YCC.T).astype(np.float32)
    return out


def _lowpass(y: Floats) -> Floats:
    return gaussian(y, 8.0)


def restore(painted: RGB, render: RGB, bins: int = 12) -> RGB:
    """The pooled colour restore of the module docstring. Both images cover the same canvas."""
    a, r = _ycc(painted), _ycc(render)
    la, lr = _lowpass(a[..., 0]), _lowpass(r[..., 0])
    qs = np.linspace(0, 100, 257)
    qa, qr = np.percentile(la[::2, ::2], qs), np.percentile(lr[::2, ::2], qs)
    detail_a = float((a[..., 0] - la).std())
    detail_r = float((r[..., 0] - lr).std())
    gd = float(np.clip(detail_r / max(detail_a, 1e-3), 1.0, 1.5))

    ca, cr = np.hypot(a[..., 1], a[..., 2]), np.hypot(r[..., 1], r[..., 2])
    ha, hr = np.arctan2(a[..., 2], a[..., 1]), np.arctan2(r[..., 2], r[..., 1])
    edges = np.linspace(-np.pi, np.pi, bins + 1)
    gain = np.ones(bins)
    for k in range(bins):
        ma = (ha >= edges[k]) & (ha < edges[k + 1]) & (ca > 4)
        mr = (hr >= edges[k]) & (hr < edges[k + 1]) & (cr > 4)
        if ma.sum() > 500 and mr.sum() > 500:
            gain[k] = np.clip(cr[mr].mean() / max(float(ca[ma].mean()), 1e-3), 1.0, 1.8)
    gain = (np.roll(gain, 1) + 2 * gain + np.roll(gain, -1)) / 4
    centres = (edges[:-1] + edges[1:]) / 2

    out = a.copy()
    out[..., 0] = np.interp(la, qa, qr) + gd * (a[..., 0] - la)
    g = np.interp(ha, centres, gain, period=2 * np.pi).astype(np.float32)
    out[..., 1:] *= g[..., None]
    rgb: RGB = np.clip(out @ np.linalg.inv(_YCC).T + 0.5, 0, 255).astype(np.uint8)
    return rgb
