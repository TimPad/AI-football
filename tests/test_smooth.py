import numpy as np
import polars as pl
import pytest

from aifootball import schemas
from aifootball.state.smooth import smooth_tracks


def _positions(ts, x, y=None, track_id=1):
    n = len(ts)
    return pl.DataFrame(
        {
            'frame_id': (np.asarray(ts) * 25).round().astype(np.int32),
            'ts': np.asarray(ts, dtype=float),
            'track_id': [track_id] * n,
            'role': ['player'] * n,
            'team': ['A'] * n,
            'x_m': np.asarray(x, dtype=float),
            'y_m': np.zeros(n) if y is None else np.asarray(y, dtype=float),
        }
    )


def _run(ts, x):
    """3 м/с вдоль x с частотой 10 Гц."""
    return smooth_tracks(_positions(ts, x))


def test_straight_run_keeps_speed_everywhere():
    ts = np.arange(30) / 10
    state = _run(ts, 3 * ts)

    assert state['speed'].to_numpy() == pytest.approx(np.full(30, 3.0), abs=1e-6)
    assert state['x_m'].to_numpy() == pytest.approx(3 * ts, abs=1e-6)
    assert state.schema == pl.Schema(schemas.STATE)


def test_single_detector_glitch_is_removed():
    ts = np.arange(30) / 10
    x = 3 * ts
    x[10] += 5.0  # детектор на один кадр «прыгнул» на 5 м

    assert _run(ts, x)['speed'].max() < 4.5


def test_short_gap_is_filled():
    ts = np.delete(np.arange(30) / 10, [11, 12, 13, 14])  # пропуск 0.5 с

    state = _run(ts, 3 * ts)

    assert len(state) == 30
    assert state['interpolated'].sum() == 4
    assert state['speed'].to_numpy() == pytest.approx(np.full(30, 3.0), abs=1e-6)


def test_long_gap_splits_track_instead_of_teleporting():
    before = np.arange(10) / 10
    after = np.arange(40, 50) / 10  # 3 секунды вне кадра
    ts = np.concatenate([before, after])
    x = np.concatenate([3 * before, 20 + 3 * after])  # вернулся в другом месте

    state = _run(ts, x)

    assert len(state) == 20 and state['interpolated'].sum() == 0
    assert state['speed'].max() == pytest.approx(3.0, abs=1e-6)


def test_single_point_track():
    state = _run([0.0], [5.0])

    assert state['speed'].to_list() == [0.0]


def test_empty_input():
    assert smooth_tracks(_positions([], []).clear()).is_empty()


def _standing_jitter_distance(fps):
    """Путь «стоящего» игрока за 20 с: детектор дрожит на 10 см в каждом кадре."""
    rng = np.random.default_rng(0)
    ts = np.arange(20 * fps) / fps
    state = smooth_tracks(_positions(ts, 5 + rng.normal(0, 0.1, len(ts)), 5 + rng.normal(0, 0.1, len(ts))))
    return float(np.hypot(np.diff(state['x_m'].to_numpy()), np.diff(state['y_m'].to_numpy())).sum())


def test_detector_jitter_does_not_add_distance_at_higher_frame_rate():
    # Независимый шум в каждом кадре: за то же окно 25 fps даёт больше отсчётов, поэтому путь может быть
    # только меньше. С окном в отсчётах было наоборот: 9,2 м против 3,7 м при 10 fps.
    at_10, at_25 = _standing_jitter_distance(10), _standing_jitter_distance(25)

    assert 0.5 * at_10 < at_25 <= at_10


def test_position_step_is_smoothed_over_same_time_at_any_frame_rate():
    def peak_speed(fps):
        ts = np.arange(4 * fps) / fps
        return smooth_tracks(_positions(ts, np.where(ts < 2, 0.0, 0.3)))['speed'].max()

    assert peak_speed(25) == pytest.approx(peak_speed(10), rel=0.25)


@pytest.mark.parametrize(
    ('fps', 'samples'), [(5, 3), (10, 3), (14.9, 5), (15, 5), (25, 9), (29.97, 9), (30, 9), (60, 19)]
)
def test_window_covers_third_of_second_at_any_frame_rate(fps, samples):
    from aifootball.state.smooth import window_samples

    assert window_samples(1 / fps) == samples
