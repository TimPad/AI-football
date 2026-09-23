"""Сглаживание траекторий, заполнение коротких пропусков и скорости.

Фаза 1 — простая и предсказуемая версия: скользящая медиана убирает единичные
выбросы детектора, скользящее среднее — дрожание бокса. Фильтр Калмана — в фазе 4.
"""

import numpy as np
import polars as pl
from numpy.lib.stride_tricks import sliding_window_view

from aifootball import schemas

# Пропуск короче этого заполняется линейно: игрок за секунду не исчезает.
# Длиннее — трек режется на куски, и дистанция через разрыв не считается.
MAX_GAP_S = 1.0
# Окно сглаживания в отсчётах: при 10 fps это полсекунды.
WINDOW = 5


def smooth_tracks(positions: pl.DataFrame) -> pl.DataFrame:
    """positions: frame_id, ts, track_id, role, team, x_m, y_m -> таблица схемы STATE."""
    if positions.is_empty():
        return schemas.empty("state")
    parts = [
        _smooth_track(group)
        for _, group in positions.sort("track_id", "ts").group_by("track_id", maintain_order=True)
    ]
    return pl.concat(parts).sort("frame_id", "track_id")


def _smooth_track(g: pl.DataFrame) -> pl.DataFrame:
    ts = g["ts"].to_numpy().astype(np.float64)
    x = g["x_m"].to_numpy().astype(np.float64)
    y = g["y_m"].to_numpy().astype(np.float64)
    frame_id = g["frame_id"].to_numpy().astype(np.int64)

    ts, x, y, frame_id, interpolated = _fill_short_gaps(ts, x, y, frame_id)

    xs, ys = x.copy(), y.copy()
    vx, vy = np.zeros_like(x), np.zeros_like(y)
    for seg in _segments(ts):
        xs[seg] = _rolling_mean(_rolling_median(x[seg]))
        ys[seg] = _rolling_mean(_rolling_median(y[seg]))
        vx[seg] = _velocity(xs[seg], ts[seg])
        vy[seg] = _velocity(ys[seg], ts[seg])

    n = len(ts)
    return pl.DataFrame(
        {
            "frame_id": frame_id,
            "ts": ts,
            "track_id": np.full(n, g["track_id"][0]),
            "role": [g["role"][0]] * n,
            "team": [g["team"][0]] * n,
            "x_m": xs,
            "y_m": ys,
            "vx": vx,
            "vy": vy,
            "speed": np.hypot(vx, vy),
            "interpolated": interpolated,
        },
        schema=schemas.STATE,
    )


def _fill_short_gaps(ts, x, y, frame_id):
    interpolated = np.zeros(len(ts), dtype=bool)
    if len(ts) < 2:
        return ts, x, y, frame_id, interpolated
    step = float(np.median(np.diff(ts)))
    out = {"ts": [ts[0]], "x": [x[0]], "y": [y[0]], "f": [frame_id[0]], "i": [False]}
    for i in range(1, len(ts)):
        dt = ts[i] - ts[i - 1]
        if 1.5 * step < dt <= MAX_GAP_S:
            missing = int(round(dt / step)) - 1
            for k in range(1, missing + 1):
                w = k / (missing + 1)
                out["ts"].append(ts[i - 1] + w * dt)
                out["x"].append(x[i - 1] + w * (x[i] - x[i - 1]))
                out["y"].append(y[i - 1] + w * (y[i] - y[i - 1]))
                out["f"].append(int(round(frame_id[i - 1] + w * (frame_id[i] - frame_id[i - 1]))))
                out["i"].append(True)
        out["ts"].append(ts[i])
        out["x"].append(x[i])
        out["y"].append(y[i])
        out["f"].append(frame_id[i])
        out["i"].append(False)
    return (
        np.array(out["ts"]), np.array(out["x"]), np.array(out["y"]),
        np.array(out["f"], dtype=np.int64), np.array(out["i"], dtype=bool),
    )


def _segments(ts: np.ndarray) -> list[slice]:
    """Куски трека без разрывов длиннее MAX_GAP_S."""
    cuts = np.flatnonzero(np.diff(ts) > MAX_GAP_S) + 1
    bounds = [0, *cuts.tolist(), len(ts)]
    return [slice(a, b) for a, b in zip(bounds[:-1], bounds[1:])]


def _pad(v: np.ndarray) -> np.ndarray:
    # «Нечётное» отражение сохраняет линейный тренд на краях: иначе края
    # траектории тянутся к первой точке и скорость на них занижается.
    return np.pad(v, WINDOW // 2, mode="reflect", reflect_type="odd")


def _rolling_median(v: np.ndarray) -> np.ndarray:
    if len(v) < WINDOW:
        return v.copy()
    return np.median(sliding_window_view(_pad(v), WINDOW), axis=1)


def _rolling_mean(v: np.ndarray) -> np.ndarray:
    if len(v) < WINDOW:
        return v.copy()
    return sliding_window_view(_pad(v), WINDOW).mean(axis=1)


def _velocity(v: np.ndarray, ts: np.ndarray) -> np.ndarray:
    if len(v) < 2:
        return np.zeros_like(v)
    return np.gradient(v, ts)
