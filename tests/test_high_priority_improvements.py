import numpy as np
import polars as pl
import pytest

from aifootball import schemas
from aifootball.analytics.metrics import _heatmap
from aifootball.perception.track import _compute_robust_foot_points
from aifootball.state.smooth import _clip_kinematic_outliers, smooth_tracks


def test_robust_foot_points_restores_clipped_boxes():
    # Создаём синтетический трек, где на 5-м кадре бокс обрезан по пояс (h = 40 вместо 100)
    df = pl.DataFrame({
        "track_id": [1] * 10,
        "x1": [10.0] * 10,
        "y1": [100.0] * 10,  # верх головы стабилен
        "x2": [30.0] * 10,
        "y2": [200.0, 200.0, 200.0, 200.0, 140.0, 200.0, 200.0, 200.0, 200.0, 200.0],
    })

    foot_x, foot_y = _compute_robust_foot_points(df)

    # На 5-м кадре (индекс 4) y2 было 140, медианная высота h_med = 100.
    # Должно восстановиться до y1 + h_med = 100 + 100 = 200.
    assert foot_x[4] == pytest.approx(20.0)
    assert foot_y[4] == pytest.approx(200.0)


def test_kinematic_outlier_filtering_removes_impossible_jumps():
    ts = np.arange(10) / 10.0
    x = 3.0 * ts
    y = np.zeros(10)

    # Скачок на 15 метров на 5-м кадре (150 м/с!)
    x[5] += 15.0

    xc, yc = _clip_kinematic_outliers(x, y, ts)

    # На 5-м кадре скачок должен быть интерполирован по соседним точкам (индексы 4 и 6)
    assert xc[5] == pytest.approx(1.5)


def test_smooth_tracks_caps_speed_at_physical_limit():
    # Создаём скачок позиции, дающий 30 м/с
    ts = np.arange(10) / 10.0
    df = pl.DataFrame({
        "frame_id": np.arange(10, dtype=np.int32),
        "ts": ts,
        "track_id": [1] * 10,
        "role": ["player"] * 10,
        "team": ["A"] * 10,
        "x_m": [0.0, 3.0, 6.0, 9.0, 25.0, 28.0, 31.0, 34.0, 37.0, 40.0],
        "y_m": np.zeros(10),
    })

    smoothed = smooth_tracks(df)

    assert smoothed["speed"].max() <= 10.0


def test_heatmap_clips_boundary_points():
    # Игрок стоял слегка за линией поля (x_m = -0.2)
    state = pl.DataFrame({
        "x_m": [-0.2, 40.1, 10.0],
        "y_m": [5.0, 15.2, 5.0],
    })

    heatmap = _heatmap(state, length_m=40.0, width_m=15.0, sample_s=0.1)

    # Все 3 точки должны попасть в сетку 40x15, сумма секунд равна 0.3
    total_seconds = float(np.sum(heatmap))
    assert total_seconds == pytest.approx(0.3)
