"""Сглаживание траекторий, заполнение коротких пропусков и скорости.

Фаза 1 — простая и предсказуемая версия: скользящая медиана убирает единичные
выбросы детектора, скользящее среднее — дрожание бокса. Фильтр Калмана — в фазе 4.
"""

import math

import numpy as np
import polars as pl
from numpy.lib.stride_tricks import sliding_window_view

from aifootball import schemas

# Пропуск короче этого заполняется линейно: игрок за секунду не исчезает.
# Длиннее — трек режется на куски, и дистанция через разрыв не считается.
MAX_GAP_S = 1.0
# Окно сглаживания в секундах: 5 отсчётов при 15 fps — на такой записи подобраны пороги владения и обучен
# классификатор остановок, для неё ничего не меняется. Раньше окно было 5 отсчётов при любой частоте, и запись
# 25 fps сглаживалась в 1,7 раза слабее: дрожание бокса превращалось в метры и скорость. При прореживании одних
# и тех же треков пяти отрезков метры в минуту расходились на 12%, быстрый бег — на 44%; теперь на 3% и 19%.
# Окно 0,5 с выравнивает быстрый бег чуть лучше (16%), но теряет передачи: F1 0,649 → 0,602 против 0,641.
WINDOW_S = 1 / 3
MIN_WINDOW = 3  # меньше трёх отсчётов медиана не убирает одиночный выброс
# Максимальная физически возможная скорость игрока в футзале (м/с).
MAX_PHYSICAL_SPEED = 10.0


def smooth_tracks(positions: pl.DataFrame) -> pl.DataFrame:
    """positions: frame_id, ts, track_id, role, team, x_m, y_m -> таблица схемы STATE."""
    if positions.is_empty():
        return schemas.empty('state')
    window = window_samples(_sample_step(positions['ts'].to_numpy()))
    parts = [
        _smooth_track(group, window)
        for _, group in positions.sort('track_id', 'ts').group_by('track_id', maintain_order=True)
    ]
    return pl.concat(parts).sort('frame_id', 'track_id')


def window_samples(step_s: float) -> int:
    """Нечётное число отсчётов, ближайшее к WINDOW_S при шаге записи step_s.

    Посередине между двумя нечётными берётся меньшее: 30 и 29,97 fps получают одно и то же окно.
    """
    if step_s <= 0:
        return MIN_WINDOW
    return max(MIN_WINDOW, 2 * math.floor((WINDOW_S / step_s - 1) / 2 + 0.5 - 1e-6) + 1)


def _sample_step(ts: np.ndarray) -> float:
    """Шаг записи — медиана между соседними кадрами всей таблицы; 0, если кадр один."""
    steps = np.diff(np.unique(ts))
    return float(np.median(steps)) if len(steps) else 0.0


def _smooth_track(g: pl.DataFrame, window: int) -> pl.DataFrame:
    ts = g['ts'].to_numpy().astype(np.float64)
    x = g['x_m'].to_numpy().astype(np.float64)
    y = g['y_m'].to_numpy().astype(np.float64)
    frame_id = g['frame_id'].to_numpy().astype(np.int64)

    ts, x, y, frame_id, interpolated = _fill_short_gaps(ts, x, y, frame_id)

    xs, ys = x.copy(), y.copy()
    vx, vy = np.zeros_like(x), np.zeros_like(y)
    for seg in _segments(ts):
        xc_seg, yc_seg = _clip_kinematic_outliers(xs[seg], ys[seg], ts[seg])
        xs[seg] = _rolling_mean(_rolling_median(xc_seg, window), window)
        ys[seg] = _rolling_mean(_rolling_median(yc_seg, window), window)
        vx[seg] = _velocity(xs[seg], ts[seg])
        vy[seg] = _velocity(ys[seg], ts[seg])

        speed_seg = np.hypot(vx[seg], vy[seg])
        too_fast = speed_seg > MAX_PHYSICAL_SPEED
        if np.any(too_fast):
            scale = np.ones_like(speed_seg)
            scale[too_fast] = MAX_PHYSICAL_SPEED / speed_seg[too_fast]
            vx[seg] *= scale
            vy[seg] *= scale

    n = len(ts)
    speed = np.hypot(vx, vy)
    return pl.DataFrame(
        {
            'frame_id': frame_id,
            'ts': ts,
            'track_id': np.full(n, g['track_id'][0]),
            'role': [g['role'][0]] * n,
            'team': [g['team'][0]] * n,
            'x_m': xs,
            'y_m': ys,
            'vx': vx,
            'vy': vy,
            'speed': speed,
            'interpolated': interpolated,
        },
        schema=schemas.STATE,
    )


def _clip_kinematic_outliers(x: np.ndarray, y: np.ndarray, ts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Убирает кинематически невозможные скачки позиции до сглаживания."""
    n = len(ts)
    if n < 3:
        return x.copy(), y.copy()

    xc, yc = x.copy(), y.copy()
    for i in range(1, n - 1):
        dt_prev = ts[i] - ts[i - 1]
        dt_next = ts[i + 1] - ts[i]
        if dt_prev <= 0 or dt_next <= 0:
            continue

        step_prev = float(np.hypot(xc[i] - xc[i - 1], yc[i] - yc[i - 1]))
        v_prev = step_prev / dt_prev

        if v_prev > MAX_PHYSICAL_SPEED:
            step_return = float(np.hypot(xc[i + 1] - xc[i - 1], yc[i + 1] - yc[i - 1]))
            dt_total = ts[i + 1] - ts[i - 1]
            if dt_total > 0 and (step_return / dt_total) <= MAX_PHYSICAL_SPEED:
                w = dt_prev / dt_total
                xc[i] = xc[i - 1] + w * (xc[i + 1] - xc[i - 1])
                yc[i] = yc[i - 1] + w * (yc[i + 1] - yc[i - 1])

    return xc, yc


def _fill_short_gaps(ts, x, y, frame_id):
    interpolated = np.zeros(len(ts), dtype=bool)
    if len(ts) < 2:
        return ts, x, y, frame_id, interpolated
    step = float(np.median(np.diff(ts)))
    out = {'ts': [ts[0]], 'x': [x[0]], 'y': [y[0]], 'f': [frame_id[0]], 'i': [False]}
    for i in range(1, len(ts)):
        dt = ts[i] - ts[i - 1]
        if 1.5 * step < dt <= MAX_GAP_S:
            missing = int(round(dt / step)) - 1
            for k in range(1, missing + 1):
                w = k / (missing + 1)
                out['ts'].append(ts[i - 1] + w * dt)
                out['x'].append(x[i - 1] + w * (x[i] - x[i - 1]))
                out['y'].append(y[i - 1] + w * (y[i] - y[i - 1]))
                out['f'].append(int(round(frame_id[i - 1] + w * (frame_id[i] - frame_id[i - 1]))))
                out['i'].append(True)
        out['ts'].append(ts[i])
        out['x'].append(x[i])
        out['y'].append(y[i])
        out['f'].append(frame_id[i])
        out['i'].append(False)
    return (
        np.array(out['ts']),
        np.array(out['x']),
        np.array(out['y']),
        np.array(out['f'], dtype=np.int64),
        np.array(out['i'], dtype=bool),
    )


def _segments(ts: np.ndarray) -> list[slice]:
    """Куски трека без разрывов длиннее MAX_GAP_S."""
    cuts = np.flatnonzero(np.diff(ts) > MAX_GAP_S) + 1
    bounds = [0, *cuts.tolist(), len(ts)]
    return [slice(a, b) for a, b in zip(bounds[:-1], bounds[1:])]


def _pad(v: np.ndarray, window: int) -> np.ndarray:
    # «Нечётное» отражение сохраняет линейный тренд на краях: иначе края
    # траектории тянутся к первой точке и скорость на них занижается.
    return np.pad(v, window // 2, mode='reflect', reflect_type='odd')


def _rolling_median(v: np.ndarray, window: int) -> np.ndarray:
    if len(v) < window:
        return v.copy()
    return np.median(sliding_window_view(_pad(v, window), window), axis=1)


def _rolling_mean(v: np.ndarray, window: int) -> np.ndarray:
    if len(v) < window:
        return v.copy()
    return sliding_window_view(_pad(v, window), window).mean(axis=1)


def _velocity(v: np.ndarray, ts: np.ndarray) -> np.ndarray:
    if len(v) < 2:
        return np.zeros_like(v)
    return np.gradient(v, ts)
