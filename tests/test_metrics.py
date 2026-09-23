import numpy as np
import polars as pl
import pytest

from aifootball import schemas
from aifootball.analytics.metrics import compute_metrics


def _state(track_id, team, ts, x, y=5.0, speed=1.0):
    n = len(ts)
    return pl.DataFrame({
        "frame_id": (np.asarray(ts) * 25).round().astype(np.int32),
        "ts": np.asarray(ts, dtype=float),
        "track_id": [track_id] * n, "role": ["player"] * n, "team": [team] * n,
        "x_m": np.asarray(x, dtype=float), "y_m": np.full(n, y),
        "vx": np.full(n, speed), "vy": np.zeros(n), "speed": np.full(n, speed),
        "interpolated": [False] * n,
    }, schema=schemas.STATE)


def _metrics():
    ts = np.arange(101) / 10  # 10 секунд, 1 м/с вдоль x
    gap_ts = np.concatenate([np.arange(21) / 10, 7 + np.arange(21) / 10])  # 5 секунд вне кадра
    state = pl.concat([
        _state(1, "A", ts, 5 + ts),
        _state(2, "A", gap_ts, 5 + gap_ts),
    ])
    return compute_metrics(state, 40.0, 20.0)


def test_track_distance_and_observed_time():
    track = _metrics()["tracks"]["1"]

    assert track["distance_m"] == pytest.approx(10.0)
    assert track["observed_s"] == pytest.approx(10.0)
    assert track["distance_per_min"] == pytest.approx(60.0)
    assert track["max_speed_ms"] == pytest.approx(1.0)


def test_long_gap_not_counted():
    track = _metrics()["tracks"]["2"]

    assert track["observed_s"] == pytest.approx(4.0)
    assert track["distance_m"] == pytest.approx(4.0)


def test_team_totals_and_heatmap():
    teams = _metrics()["teams"]
    heat = np.array(teams["A"]["heatmap_s"])

    assert teams["A"]["tracks"] == ["1", "2"]
    assert teams["A"]["distance_m"] == pytest.approx(14.0)
    assert heat.shape == (40, 20)
    assert heat.sum() == pytest.approx((101 + 42) * 0.1)
    assert heat[:, 5].sum() == pytest.approx(heat.sum())  # все бегали по y=5
    assert teams["B"] == {"tracks": [], "observed_s": 0, "distance_m": 0, "heatmap_s": np.zeros((40, 20)).tolist()}
