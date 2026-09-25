import numpy as np
import polars as pl
import pytest

from aifootball import schemas
from aifootball.perception.ball import (
    compute_possession,
    process_ball_trajectory,
)


def test_process_ball_trajectory_filters_spikes_and_interpolates(venue):
    # Создаём детекции мяча со скачком на 50 м/с и с пропуском 0.5 с
    rows = [
        {"frame_id": 1, "ts": 0.1, "cls": "ball", "x1": 100.0, "y1": 100.0, "x2": 110.0, "y2": 110.0, "conf": 0.5, "torso_l": np.nan, "torso_a": np.nan, "torso_b": np.nan},
        {"frame_id": 2, "ts": 0.2, "cls": "ball", "x1": 105.0, "y1": 100.0, "x2": 115.0, "y2": 110.0, "conf": 0.5, "torso_l": np.nan, "torso_a": np.nan, "torso_b": np.nan},
        # Пропуск 0.5 с
        {"frame_id": 7, "ts": 0.7, "cls": "ball", "x1": 130.0, "y1": 100.0, "x2": 140.0, "y2": 110.0, "conf": 0.5, "torso_l": np.nan, "torso_a": np.nan, "torso_b": np.nan},
    ]

    detections = pl.DataFrame(rows, schema=schemas.DETECTIONS)
    ball_state = process_ball_trajectory(detections, venue)

    assert not ball_state.is_empty()
    assert ball_state["interpolated"].sum() > 0  # Пропуск был интерполирован


def test_compute_possession_team_assignment():
    ball_state = pl.DataFrame({
        "frame_id": [1, 2, 3, 4],
        "ts": [0.1, 0.2, 0.3, 0.4],
        "x_m": [10.0, 10.0, 30.0, 30.0],
        "y_m": [5.0, 5.0, 5.0, 5.0],
        "speed": [0.0, 0.0, 0.0, 0.0],
        "interpolated": [False, False, False, False],
    })

    # Игрок команды А у мяча в кадрах 1 и 2; игрок команды Б — в кадрах 3 и 4
    player_state = pl.DataFrame({
        "frame_id": [1, 2, 3, 4],
        "ts": [0.1, 0.2, 0.3, 0.4],
        "track_id": [1, 1, 2, 2],
        "role": ["player", "player", "player", "player"],
        "team": ["A", "A", "B", "B"],
        "x_m": [10.2, 10.1, 30.1, 30.2],
        "y_m": [5.0, 5.0, 5.0, 5.0],
        "vx": [0.0, 0.0, 0.0, 0.0],
        "vy": [0.0, 0.0, 0.0, 0.0],
        "speed": [0.0, 0.0, 0.0, 0.0],
        "interpolated": [False, False, False, False],
    })

    poss = compute_possession(ball_state, player_state, possession_radius_m=1.8)

    assert poss["possession_pct"]["A"] == 50.0
    assert poss["possession_pct"]["B"] == 50.0
