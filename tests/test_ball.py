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



def _ball(xs, dt=0.1):
    n = len(xs)
    return pl.DataFrame({
        "frame_id": list(range(1, n + 1)),
        "ts": [dt * (i + 1) for i in range(n)],
        "x_m": [float(x) for x in xs],
        "y_m": [5.0] * n,
        "speed": [0.0] * n,
        "interpolated": [False] * n,
    })


def _players(owners, xs, dt=0.1):
    """owners[i] — (track_id, role, team) игрока в кадре i+1, стоящего в точке xs[i]."""
    n = len(owners)
    return pl.DataFrame({
        "frame_id": list(range(1, n + 1)),
        "ts": [dt * (i + 1) for i in range(n)],
        "track_id": [o[0] for o in owners],
        "role": [o[1] for o in owners],
        "team": [o[2] for o in owners],
        "x_m": [float(x) + 0.1 for x in xs],
        "y_m": [5.0] * n,
        "vx": [0.0] * n,
        "vy": [0.0] * n,
        "speed": [0.0] * n,
        "interpolated": [False] * n,
    }, schema_overrides={"team": pl.Utf8})


A1 = (1, "player", "A")
A2 = (2, "player", "A")
B1 = (3, "player", "B")
REF = (9, "referee", None)


def test_detect_passes_between_teammates():
    from aifootball.perception.ball import detect_passes

    xs = [10] * 4 + [20] * 4
    passes = detect_passes(_ball(xs), _players([A1] * 4 + [A2] * 4, xs))

    assert passes["passes_total"] == {"A": 1, "B": 0}
    assert passes["passes_completed"] == {"A": 1, "B": 0}
    assert passes["pass_accuracy_pct"]["A"] == 100.0


def test_detect_passes_interception_is_incomplete():
    from aifootball.perception.ball import detect_passes

    xs = [10] * 4 + [20] * 4
    passes = detect_passes(_ball(xs), _players([A1] * 4 + [B1] * 4, xs))

    assert passes["passes_total"] == {"A": 1, "B": 0}
    assert passes["passes_completed"] == {"A": 0, "B": 0}
    assert passes["pass_accuracy_pct"]["A"] == 0.0


def test_detect_passes_ignores_flicker_between_neighbours():
    # Мяч между двумя соседями: ближайший меняется каждый кадр — это не пасы
    from aifootball.perception.ball import detect_passes

    xs = [10] * 10
    owners = [A1, A2] * 5
    passes = detect_passes(_ball(xs), _players(owners, xs))

    assert passes["passes_total"] == {"A": 0, "B": 0}


def test_detect_passes_short_touch_does_not_break_possession():
    # Соперник на кадр оказался ближе к мячу, но владение не сменилось
    from aifootball.perception.ball import detect_passes

    xs = [10] * 9
    owners = [A1] * 4 + [B1] + [A1] * 4
    passes = detect_passes(_ball(xs), _players(owners, xs))

    assert passes["passes_total"] == {"A": 0, "B": 0}


def test_detect_passes_ignores_referee_near_ball():
    # Мяч прошёл мимо судьи по пути от A1 к A2 — это один точный пас A
    from aifootball.perception.ball import detect_passes

    xs = [10] * 4 + [15] * 4 + [20] * 4
    owners = [A1] * 4 + [REF] * 4 + [A2] * 4
    passes = detect_passes(_ball(xs), _players(owners, xs))

    assert passes["passes_total"] == {"A": 1, "B": 0}
    assert passes["passes_completed"] == {"A": 1, "B": 0}


def test_detect_passes_ignores_owner_change_after_long_gap():
    # Мяч 4 с вне досягаемости игроков: что случилось между владениями, неизвестно
    from aifootball.perception.ball import detect_passes

    ball_xs = [10] * 4 + [30] * 40 + [20] * 4
    player_xs = [10] * 4 + [10] * 40 + [20] * 4
    owners = [A1] * 44 + [A2] * 4
    passes = detect_passes(_ball(ball_xs), _players(owners, player_xs))

    assert passes["passes_total"] == {"A": 0, "B": 0}
