"""Кандидаты стандартных положений из координат CV, без обращений к VLM.

Ввод мяча из аута и угловой в футзале выполняются с линии: игрок стоит на ней,
остальные отходят. Кандидат — полевой игрок команды, который неподвижен у линии
не меньше заданного времени. Это подсказка для проверки, а не событие протокола.
"""
import numpy as np
import polars as pl

MARGIN_M = 1.0        # расстояние до линии поля
MAX_SPEED_MS = 1.0    # «стоит» — медленнее этого
MIN_DURATION_S = 1.5  # сколько стоит у линии
MERGE_GAP_S = 3.0     # соседние отрезки одной остановки объединяются
MAX_GAP_S = 0.5       # разрыв трека дольше этого прерывает отрезок
CORNER_M = 2.5        # ближе к углу — подсказка «угловой»


def _segments(ts: np.ndarray, ok: np.ndarray, min_duration: float):
    start = prev = None
    for t, flag in zip(ts, ok):
        if prev is not None and t - prev > MAX_GAP_S:
            if start is not None and prev - start >= min_duration:
                yield start, prev
            start = None
        if flag and start is None:
            start = t
        if not flag and start is not None:
            if prev - start >= min_duration:
                yield start, prev
            start = None
        prev = t
    if start is not None and prev - start >= min_duration:
        yield start, prev


def _edge(x: float, y: float, length_m: float, width_m: float) -> str:
    near_end = min(x, length_m - x) <= CORNER_M
    near_side = min(y, width_m - y) <= CORNER_M
    if near_end and near_side:
        return 'corner'
    return 'endline' if min(x, length_m - x) < min(y, width_m - y) else 'sideline'


def restart_candidates(state: pl.DataFrame, length_m: float, width_m: float, *, margin_m: float = MARGIN_M,
                       max_speed: float = MAX_SPEED_MS, min_duration_s: float = MIN_DURATION_S,
                       merge_gap_s: float = MERGE_GAP_S) -> list[dict]:
    players = state.filter(pl.col('team').is_in(['A', 'B']) & (pl.col('role') == 'player')).sort('track_id', 'ts')
    found = []
    for (track_id,), g in players.group_by('track_id', maintain_order=True):
        ts = g['ts'].to_numpy(); x = g['x_m'].to_numpy(); y = g['y_m'].to_numpy(); v = g['speed'].to_numpy()
        edge = np.minimum.reduce([x, length_m - x, y, width_m - y])
        ok = (edge <= margin_m) & (v <= max_speed)
        for start, end in _segments(ts, ok, min_duration_s):
            inside = (ts >= start) & (ts <= end)
            mx, my = float(np.median(x[inside])), float(np.median(y[inside]))
            found.append({'start_s': float(start), 'end_s': float(end), 'track_id': int(track_id), 'team': g['team'][0],
                          'x_m': round(mx, 2), 'y_m': round(my, 2), 'edge': _edge(mx, my, length_m, width_m)})
    found.sort(key=lambda c: (c['start_s'], c['track_id']))
    merged: list[dict] = []
    for c in found:
        # Одна остановка — один кандидат: берём самого раннего игрока у линии.
        if merged and c['start_s'] - merged[-1]['end_s'] <= merge_gap_s:
            merged[-1]['end_s'] = max(merged[-1]['end_s'], c['end_s'])
            continue
        merged.append(dict(c, kind='restart_candidate'))
    return merged


def evaluate(candidates: list[dict], dead_s: list[float], *, before_s: float = 1.0, after_s: float = 7.0) -> dict:
    """Точность и полнота против моментов «мяч вне игры» из ручной разметки."""
    dead = sorted({round(d) for d in dead_s})
    match = lambda c, d: d - before_s <= c['start_s'] <= d + after_s
    tp = sum(any(match(c, d) for d in dead) for c in candidates)
    hit = sum(any(match(c, d) for c in candidates) for d in dead)
    return {'candidates': len(candidates), 'true_positive': tp, 'dead': len(dead), 'found': hit,
            'precision': round(tp / len(candidates), 3) if candidates else None,
            'recall': round(hit / len(dead), 3) if dead else None}
