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
        "x_m": np.asarray(x, dtype=np.float32), "y_m": np.full(n, y, dtype=np.float32),
        "vx": np.full(n, speed, dtype=np.float32), "vy": np.zeros(n, dtype=np.float32),
        "speed": np.full(n, speed, dtype=np.float32),
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
    assert teams["B"] == {
        "tracks": [],
        "observed_s": 0,
        "distance_m": 0,
        "sprints_count": 0,
        "compactness_m2": 0.0,
        "heatmap_s": np.zeros((40, 20)).tolist(),
    }


def test_sprint_counting_and_compactness():
    # Создаем 3 игроков для проверки площади треугольника (компактности)
    # Площадь прямоугольного треугольника с катетами 10 м и 10 м = 50 м^2
    ts = np.arange(20) / 10.0  # 2 секунды
    speeds = np.full(20, 1.0, dtype=np.float32)
    speeds[5:18] = 6.0  # 1.3 секунды со скоростью 6 м/с (спринт!)

    df1 = _state(1, "A", ts, np.zeros(20), y=0.0, speed=1.0)
    df1 = df1.with_columns(speed=pl.Series(speeds, dtype=pl.Float32))

    df2 = _state(2, "A", ts, np.full(20, 10.0), y=0.0, speed=1.0)
    df3 = _state(3, "A", ts, np.zeros(20), y=10.0, speed=1.0)

    state = pl.concat([df1, df2, df3])
    m = compute_metrics(state, 40.0, 20.0)

    assert m["tracks"]["1"]["sprints_count"] == 1
    assert m["teams"]["A"]["sprints_count"] == 1
    assert m["teams"]["A"]["compactness_m2"] == pytest.approx(50.0)



def test_long_gap_cannot_complete_sprint():
    state = _state(1, 'A', np.array([0., .2, 10., 10.2]), np.array([0., 1., 2., 3.]), speed=6.)
    result = compute_metrics(state, 40., 20.)
    assert result['tracks']['1']['sprints_count'] == 0


def _shot_saved_by_keeper():
    """A1 бьёт с 30 м по центру ворот x=40 на 15 м/с, мяч забирает вратарь B."""
    ts = np.round(np.arange(76) * 0.04, 2)
    ball_x = np.where(ts <= 1.0, 30.2, np.minimum(30.2 + (ts - 1.0) * 15, 39.4))
    ball = pl.DataFrame({"frame_id": (ts * 25).round().astype(np.int32), "ts": ts, "x_m": ball_x, "y_m": np.full(len(ts), 10.0),
                         "speed": np.zeros(len(ts)), "interpolated": [False] * len(ts)})
    keeper = _state(9, "B", ts, np.full(len(ts), 39.6), y=10.0, speed=0.5).with_columns(role=pl.lit("goalkeeper"))
    return ball, pl.concat([_state(1, "A", ts, np.full(len(ts), 30.0), y=10.0), keeper])


def test_saved_shot_is_not_a_pass_in_metrics_or_report():
    # передачи отчёта — те же события, что публикует сервис: удар, который взял вратарь, — не неточный пас
    from aifootball.analytics.report_data import ball_summary

    ball, state = _shot_saved_by_keeper()
    assert compute_metrics(state, 40.0, 20.0, ball_state=ball)["passes"]["passes_total"] == {"A": 0, "B": 0}
    assert ball_summary(ball, state, 40.0, 20.0)["passes"]["passes_total"] == {"A": 0, "B": 0}
