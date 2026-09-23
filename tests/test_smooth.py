import numpy as np
import polars as pl
import pytest

from aifootball import schemas
from aifootball.state.smooth import smooth_tracks


def _positions(ts, x, y=None, track_id=1):
    n = len(ts)
    return pl.DataFrame({
        "frame_id": (np.asarray(ts) * 25).round().astype(np.int32),
        "ts": np.asarray(ts, dtype=float),
        "track_id": [track_id] * n,
        "role": ["player"] * n,
        "team": ["A"] * n,
        "x_m": np.asarray(x, dtype=float),
        "y_m": np.zeros(n) if y is None else np.asarray(y, dtype=float),
    })


def _run(ts, x):
    """3 м/с вдоль x с частотой 10 Гц."""
    return smooth_tracks(_positions(ts, x))


def test_straight_run_keeps_speed_everywhere():
    ts = np.arange(30) / 10
    state = _run(ts, 3 * ts)

    assert state["speed"].to_numpy() == pytest.approx(np.full(30, 3.0), abs=1e-6)
    assert state["x_m"].to_numpy() == pytest.approx(3 * ts, abs=1e-6)
    assert state.schema == pl.Schema(schemas.STATE)


def test_single_detector_glitch_is_removed():
    ts = np.arange(30) / 10
    x = 3 * ts
    x[10] += 5.0  # детектор на один кадр «прыгнул» на 5 м

    assert _run(ts, x)["speed"].max() < 4.5


def test_short_gap_is_filled():
    ts = np.delete(np.arange(30) / 10, [11, 12, 13, 14])  # пропуск 0.5 с

    state = _run(ts, 3 * ts)

    assert len(state) == 30
    assert state["interpolated"].sum() == 4
    assert state["speed"].to_numpy() == pytest.approx(np.full(30, 3.0), abs=1e-6)


def test_long_gap_splits_track_instead_of_teleporting():
    before = np.arange(10) / 10
    after = np.arange(40, 50) / 10  # 3 секунды вне кадра
    ts = np.concatenate([before, after])
    x = np.concatenate([3 * before, 20 + 3 * after])  # вернулся в другом месте

    state = _run(ts, x)

    assert len(state) == 20 and state["interpolated"].sum() == 0
    assert state["speed"].max() == pytest.approx(3.0, abs=1e-6)


def test_single_point_track():
    state = _run([0.0], [5.0])

    assert state["speed"].to_list() == [0.0]


def test_empty_input():
    assert smooth_tracks(_positions([], []).clear()).is_empty()
