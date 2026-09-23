import numpy as np
import pytest

from aifootball.geometry.homography import apply_homography
from aifootball.tools.marking import save_homography, save_polygon, topdown_preview
from aifootball.venue import load_venue
from conftest import make_venue_dir

PIXELS = [[100, 400], [1100, 420], [900, 250], [300, 240], [640, 330]]
TRUE_H = np.array([[0.05, 0.01, -3.0], [0.002, 0.08, -10.0], [0.0001, 0.0009, 1.0]])


def test_polygon_saved_and_loaded(tmp_path):
    root = make_venue_dir(tmp_path / "v")

    save_polygon(root, [(0, 0), (10, 0), (10, 10)])

    assert load_venue(root).pitch_polygon_px.tolist() == [[0, 0], [10, 0], [10, 10]]


def test_polygon_needs_three_points(tmp_path):
    with pytest.raises(ValueError, match="минимум 3"):
        save_polygon(make_venue_dir(tmp_path / "v"), [(0, 0), (1, 1)])


def test_homography_saved_with_honest_error(tmp_path):
    root = make_venue_dir(tmp_path / "v")
    meters = apply_homography(TRUE_H, np.array(PIXELS, float))

    info = save_homography(root, PIXELS, meters, calib=None)

    assert info["reprojection_error_m"] < 1e-3
    assert info["leave_one_out_error_m"] < 1e-3
    np.testing.assert_allclose(apply_homography(load_venue(root).H, np.array(PIXELS, float)), meters, atol=1e-4)


def test_preview_has_canvas_size():
    frame = np.full((720, 1280, 3), 90, np.uint8)
    scale = np.array([[0.1, 0, 0], [0, 0.1, 0], [0, 0, 1.0]])

    assert topdown_preview(frame, scale, 40, 20).shape == (480, 880, 3)
