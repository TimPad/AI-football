import numpy as np
import polars as pl

from aifootball import schemas
from aifootball.analytics.checks import phase1_checks


def _state(x, speed):
    n = len(x)
    return pl.DataFrame({
        "frame_id": np.arange(n, dtype=np.int32), "ts": np.arange(n) / 10,
        "track_id": np.arange(n, dtype=np.int32) % 2, "role": ["player"] * n, "team": ["A"] * n,
        "x_m": np.asarray(x, float), "y_m": np.full(n, 10.0),
        "vx": np.asarray(speed, float), "vy": np.zeros(n), "speed": np.asarray(speed, float),
        "interpolated": [False] * n,
    }, schema=schemas.STATE)


def test_plausible_state_passes():
    result = phase1_checks(_state(x=np.linspace(0, 40, 100), speed=np.full(100, 5.0)), 40, 20)
    assert result["passed"] and result["inside_share"] == 1.0


def test_too_fast_fails():
    speed = np.full(100, 5.0)
    speed[42] = 14.0
    result = phase1_checks(_state(x=np.full(100, 20.0), speed=speed), 40, 20)

    assert not result["passed"] and not result["speed_ok"]
    assert result["fastest_track"] == 0


def test_points_outside_pitch_fail():
    x = np.full(100, 20.0)
    x[:10] = 45.0  # 10% точек за лицевой линией
    result = phase1_checks(_state(x=x, speed=np.full(100, 5.0)), 40, 20)

    assert not result["inside_ok"] and result["inside_share"] == 0.9


def test_empty_state_fails():
    assert phase1_checks(schemas.empty("state"), 40, 20)["passed"] is False
