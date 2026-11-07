"""Scientific checks for the small D2IC_GUI VIS/TH example generator."""

import subprocess
import sys
from pathlib import Path

import numpy as np
import tifffile

SCRIPT = Path(__file__).parents[1] / "examples" / "generate_synthetic_study.py"


def _generate(output_dir):
    subprocess.run([sys.executable, str(SCRIPT), str(output_dir)], check=True, capture_output=True, text=True)


def test_generated_vis_translation_and_th_missing_frame(tmp_path):
    _generate(tmp_path)
    import json

    expected = json.loads((tmp_path / "expected.json").read_text(encoding="utf-8"))
    vis_paths = sorted((tmp_path / "VIS").glob("*.tif"))
    th_paths = sorted((tmp_path / "TH").glob("*.tif"))

    assert len(vis_paths) == 4
    assert len(th_paths) == 5
    reference = tifffile.imread(vis_paths[0])
    shifted = tifffile.imread(vis_paths[1])
    dx, dy = expected["vis"]["translations_xy_px"][1]
    assert np.array_equal(shifted[dy:, dx:], reference[:-dy, :-dx])
    assert [int(path.name.split("_")[1]) for path in th_paths] == [0, 1, 2, 4, 5]


def test_generated_thermal_frames_have_expected_linear_temperature(tmp_path):
    _generate(tmp_path)
    at_02 = tifffile.imread(tmp_path / "TH" / "th_0002_t0.20s.tif")
    at_04 = tifffile.imread(tmp_path / "TH" / "th_0004_t0.40s.tif")

    assert at_02.shape == (48, 64)
    assert np.all(at_02 == np.float32(20.4))
    assert np.all(at_04 == np.float32(20.8))
    # The 0.2–0.4 s pair skips TH frame 3 and must not bracket VIS 0.35 s.
    # The complete 0.1–0.2 s pair can interpolate VIS 0.15 s to 20.3 °C.
    at_01 = tifffile.imread(tmp_path / "TH" / "th_0001_t0.10s.tif")
    assert np.allclose(0.5 * at_01 + 0.5 * at_02, 20.3)
