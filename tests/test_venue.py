import numpy as np
import pytest

from aifootball.venue import load_venue
from conftest import SCALE_H, make_venue_dir


def test_loads_yaml_and_optional_files(tmp_path):
    root = make_venue_dir(tmp_path / "v", polygon=[[0, 0], [10, 0], [10, 10]], H=SCALE_H)

    venue = load_venue(root)

    assert venue.venue_id == "test"
    assert (venue.length_m, venue.width_m) == (40.0, 20.0)
    assert venue.target_fps == 10.0
    assert venue.pitch_polygon_px.shape == (3, 2)
    np.testing.assert_allclose(venue.H, SCALE_H)
    assert venue.calib is None


def test_missing_markup_is_none_until_required(tmp_path):
    venue = load_venue(make_venue_dir(tmp_path / "v"))

    assert venue.pitch_polygon_px is None and venue.H is None
    with pytest.raises(FileNotFoundError, match="mark_points polygon"):
        venue.require_polygon()
    with pytest.raises(FileNotFoundError, match="mark_points homography"):
        venue.require_homography()
