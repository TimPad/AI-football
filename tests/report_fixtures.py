"""Синтетический матч для тестов отчёта: state и tracks с известными цифрами."""

import numpy as np
import polars as pl

from aifootball import schemas

FPS = 2.0
SECONDS = 200
LENGTH, WIDTH = 40.0, 20.0


def _player(track_id, team, role, x0, y0, amp, phase, ts):
    """Траектория: колебание вдоль x вокруг x0 (амплитуда amp м, период 20 с)."""
    x = x0 + amp * np.sin(2 * np.pi * ts / 20 + phase)
    y = np.full_like(ts, y0)
    return track_id, team, role, x, y


def synthetic_match(seconds: int = SECONDS, sprint: bool = True) -> tuple[pl.DataFrame, pl.DataFrame]:
    ts = np.arange(0, seconds, 1 / FPS)
    people = []
    for i in range(4):
        people.append(_player(1 + i, "B", "player", 11.0, 4.0 + 4 * i, 3.0, i, ts))
        people.append(_player(11 + i, "A", "player", 29.0, 4.0 + 4 * i, 3.0, i, ts))
    people.append(_player(9, "B", "goalkeeper", 1.5, 10.0, 0.5, 0.0, ts))
    people.append(_player(19, "A", "goalkeeper", 38.5, 10.0, 0.5, 0.0, ts))

    state_rows, track_rows = [], []
    for track_id, team, role, x, y in people:
        if sprint and track_id == 11:  # A1: стоит, спринт 6 м/с с 20 по 24 с, снова стоит
            x = np.where(ts < 20, 30.0, np.where(ts < 24, 30.0 - 6.0 * (ts - 20), 6.0))
        vx = np.gradient(x, ts)
        vy = np.gradient(y, ts)
        speed = np.hypot(vx, vy)
        for k in range(len(ts)):
            frame_id = int(round(ts[k] * FPS))
            state_rows.append({"frame_id": frame_id, "ts": float(ts[k]), "track_id": track_id, "role": role,
                               "team": team, "x_m": x[k], "y_m": y[k], "vx": vx[k], "vy": vy[k],
                               "speed": speed[k], "interpolated": False})
            px, py = x[k] * 10, y[k] * 10
            track_rows.append({"frame_id": frame_id, "ts": float(ts[k]), "cls": "person",
                               "x1": px - 5, "y1": py - 30, "x2": px + 5, "y2": py, "conf": 0.9,
                               "torso_l": 120.0, "torso_a": 100.0 if team == "A" else 180.0, "torso_b": 150.0,
                               "track_id": track_id, "foot_x": px, "foot_y": py, "in_pitch": True,
                               "role": role, "team": team})
    state = pl.DataFrame(state_rows, schema=schemas.STATE).sort("frame_id", "track_id")
    tracks = pl.DataFrame(track_rows, schema=schemas.TRACKS).sort("frame_id", "track_id")
    return state, tracks
