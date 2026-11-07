#!/usr/bin/env python3
"""Generate a small VIS/TH study for exercising the D2IC_GUI import path.

Requires NumPy and tifffile. Images are written in camera pixel coordinates:
arrays are indexed ``(y, x)``, while coordinates and translations are ``(x, y)``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import tifffile


VIS_SHAPE = (96, 128)  # (height, width), VIS pixels
TH_SHAPE = (48, 64)  # (height, width), TH pixels; same field of view
VIS_TIMES_S = (0.0, 0.15, 0.35, 0.45)
VIS_TRANSLATIONS_PX = ((0, 0), (2, 1), (4, 2), (6, 3))
TH_FRAME_IDS = (0, 1, 2, 4, 5)  # frame 3 (t=0.3 s) intentionally missing
TH_RATE_HZ = 10.0
TH_BASE_C = 20.0
TH_SLOPE_C_PER_S = 2.0


def _reference_texture(shape: tuple[int, int], seed: int = 27) -> np.ndarray:
    """Return deterministic textured uint8 VIS image, with no extra dependencies."""
    rng = np.random.default_rng(seed)
    h, w = shape
    # Coarse random speckles expanded to blocks create texture at several scales.
    coarse = rng.integers(0, 256, size=(h // 4 + 1, w // 4 + 1), dtype=np.uint8)
    image = np.repeat(np.repeat(coarse, 4, axis=0), 4, axis=1)[:h, :w]
    fine = rng.integers(0, 48, size=shape, dtype=np.uint8)
    return np.clip(image.astype(np.int16) // 2 + fine, 0, 255).astype(np.uint8)


def _translate(image: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """Translate an image by integer VIS pixels; exposed edges are zero-filled."""
    out = np.zeros_like(image)
    h, w = image.shape
    src_x0, src_x1 = max(0, -dx), min(w, w - dx)
    src_y0, src_y1 = max(0, -dy), min(h, h - dy)
    if src_x0 < src_x1 and src_y0 < src_y1:
        out[src_y0 + dy:src_y1 + dy, src_x0 + dx:src_x1 + dx] = image[
            src_y0:src_y1, src_x0:src_x1
        ]
    return out


def generate_study(output_dir: str | Path) -> dict:
    """Write deterministic VIS/TH TIFF sequences and return their expected truth.

    VIS is a known rigid translation in original VIS pixels. TH pixels span the
    same field of view at half the VIS resolution. Every TH image is spatially
    constant, with temperature ``20 + 2 t`` °C. TH frame number 3 is absent.
    """
    root = Path(output_dir)
    vis_dir, th_dir = root / "VIS", root / "TH"
    vis_dir.mkdir(parents=True, exist_ok=True)
    th_dir.mkdir(parents=True, exist_ok=True)

    reference = _reference_texture(VIS_SHAPE)
    for index, ((dx, dy), time_s) in enumerate(zip(VIS_TRANSLATIONS_PX, VIS_TIMES_S)):
        tifffile.imwrite(vis_dir / f"vis_{index:04d}_tick{round(100 * time_s):04d}.tif", _translate(reference, dx, dy))

    th_times = []
    for frame_id in TH_FRAME_IDS:
        time_s = frame_id / TH_RATE_HZ
        th_times.append(time_s)
        temperature = TH_BASE_C + TH_SLOPE_C_PER_S * time_s
        image = np.full(TH_SHAPE, temperature, dtype=np.float32)
        tifffile.imwrite(th_dir / f"th_{frame_id:04d}_t{time_s:.2f}s.tif", image)

    expected = {
        "vis": {
            "shape_yx_px": list(VIS_SHAPE),
            "times_s": list(VIS_TIMES_S),
            "translations_xy_px": [list(v) for v in VIS_TRANSLATIONS_PX],
            "reference_translation_xy_px": [0, 0],
        },
        "th": {
            "shape_yx_px": list(TH_SHAPE),
            "times_s": th_times,
            "missing_frame_id": 3,
            "nominal_rate_hz": TH_RATE_HZ,
            "temperature_unit": "degC",
            "temperature_C": "20 + 2 * time_s",
            "spatial_field": "constant",
            "same_field_of_view_as_vis": True,
        },
        "mapping": "x_th = (W_th - 1)/(W_vis - 1) * x_vis; y_th = (H_th - 1)/(H_vis - 1) * y_vis",
    }
    (root / "expected.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", nargs="?", type=Path, default=Path("synthetic_study"))
    args = parser.parse_args()
    generate_study(args.output_dir)
    print(f"Synthetic VIS/TH study written to {args.output_dir}")


if __name__ == "__main__":
    main()
