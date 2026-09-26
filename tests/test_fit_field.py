import numpy as np
import pytest

from aifootball.geometry.homography import apply_homography
from aifootball.tools.fit_field import FIELD_POINTS, fit_field, field_xy

TRUE_H = np.array([[0.02, 0.004, -3.0], [0.001, 0.05, -12.0], [0.00001, 0.0006, 1.0]])


def _clicks(L, W, skip=(), noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    names = [n for n in FIELD_POINTS if n not in skip]
    meters = np.array([field_xy(n, L, W) for n in names])
    px = apply_homography(np.linalg.inv(TRUE_H), meters) + rng.normal(0, noise, (len(names), 2))
    return dict(zip(names, map(tuple, px)))


def test_recovers_field_size_and_homography():
    res = fit_field(_clicks(38.0, 19.0), calib=None)

    assert res["length_m"] == pytest.approx(38.0, abs=0.01)
    assert res["width_m"] == pytest.approx(19.0, abs=0.01)
    assert max(res["errors_m"].values()) < 0.01


def test_works_with_skipped_points():
    skipped = ("near_stands", "far_pen10", "near_post_stands", "circle_stands")
    res = fit_field(_clicks(40.0, 20.0, skip=skipped), calib=None)

    assert res["length_m"] == pytest.approx(40.0, abs=0.01)
    assert set(res["errors_m"]).isdisjoint(skipped)


def test_wrong_point_stands_out():
    clicks = _clicks(40.0, 20.0, noise=0.3)
    x, y = clicks["far_stands"]
    clicks["far_stands"] = (x + 40.0, y)  # клик мимо угла

    res = fit_field(clicks, calib=None)

    worst = max(res["errors_m"], key=res["errors_m"].get)
    assert worst == "far_stands"


def test_court_overlay_draws_on_frame():
    from aifootball.tools.fit_field import overlay_court

    frame = np.full((1000, 1400, 3), 60, np.uint8)
    res = fit_field(_clicks(40.0, 20.0), calib=None)

    out = overlay_court(frame, res["H"], None, 40.0, 20.0)

    assert out.shape == frame.shape and (out != frame).any()
    assert (frame == 60).all()  # исходный кадр не тронут
