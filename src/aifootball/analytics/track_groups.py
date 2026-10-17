"""Склейка треков в кандидатов-игроков для сопоставления с составом.

Трекер рвёт игрока на куски: толпа, выход за край кадра, замена. Первая сшивка в CLI соединяет
короткие обрывы; здесь — глобальная задача по всему фрагменту: каждому концу трека подбирается
не больше одного продолжения той же команды (венгерский алгоритм с вариантом «продолжения нет»).

Жёсткие правила: продолжение начинается после конца (дубль трекера допускает перекрытие до
OVERLAP_S в той же точке), переход физически возможен, через линию скамейки с паузой не склеиваем —
там уходит один игрок и выходит другой. Цвет формы не используется: внутри команды он одинаковый,
а у коротких треков в толпе подмешивается цвет соседа — по разметке Ярославля он только вредил.

Замер (scripts/eval_identity.py, разметка обрывов data/gt/*/links.json): 60–240 — точность 1,0 при
полноте 0,88 (14 из 16 связок); независимый 600–780 — 0,91 и 0,83 (10 из 12), единственная ошибка —
трек с неверной командой в данных. Пропуски — перекрытия длиннее OVERLAP_S, где хвост трека уже
перескочил на другого человека: такие куски администратор объединяет вручную.
"""
from dataclasses import dataclass

import numpy as np
import polars as pl
from scipy.optimize import linear_sum_assignment

MAX_GAP_S = 20.0        # дольше игрок не пропадает, пока остаётся на площадке
OVERLAP_S = 1.0         # дубль трекера при передаче игрока между треками
DUP_NEAR_S = 0.6        # короткое перекрытие — до DUP_M (дальняя бровка: пиксель ≈ 0,17 м)
DUP_M = 3.5
SLACK_M = 1.5           # шум точки ног на концах трека
VMAX_MS = 9.0           # с запасом к спринту: концы треков в толпе неточны
TOUCHLINE_M = 0.6       # концы у боковой линии
CUT = 12.0              # дороже — «продолжения нет»
MARGIN = 2.0            # второй кандидат почти так же хорош — не склеиваем
EDGE_S = 0.5            # конец/начало — медиана позиции за полсекунды: одиночный кадр шумный


@dataclass(frozen=True)
class Track:
    track_id: int
    team: str
    role: str
    t0: float
    t1: float
    p0: np.ndarray
    p1: np.ndarray


def track_ends(state: pl.DataFrame) -> dict[int, Track]:
    """Треки игроков и вратарей с известной командой: время и точка начала и конца."""
    out = {}
    for (tid,), g in state.filter(pl.col('role').is_in(['player', 'goalkeeper'])).group_by('track_id'):
        g = g.sort('ts')
        team = g['team'].drop_nulls().mode()
        if len(g) < 3 or team.is_empty() or team[0] not in ('A', 'B'):
            continue
        head = g.filter(pl.col('ts') <= g['ts'][0] + EDGE_S)
        tail = g.filter(pl.col('ts') >= g['ts'][-1] - EDGE_S)
        out[int(tid)] = Track(int(tid), team[0], g['role'].mode()[0], float(g['ts'][0]), float(g['ts'][-1]),
                              np.array([head['x_m'].median(), head['y_m'].median()]),
                              np.array([tail['x_m'].median(), tail['y_m'].median()]))
    return out


def link_cost(a: Track, b: Track, width_m: float) -> float | None:
    """Стоимость «b продолжает a» или None, если это невозможно."""
    if a.track_id == b.track_id or a.team != b.team:
        return None
    gap = b.t0 - a.t1
    if gap < -OVERLAP_S or gap > MAX_GAP_S:
        return None
    d = float(np.linalg.norm(b.p0 - a.p1))
    if gap < 0 and d > (DUP_M if gap > -DUP_NEAR_S else SLACK_M):
        return None
    if max(0.0, d - SLACK_M) / max(gap, 0.2) > VMAX_MS:
        return None
    ys = (a.p1[1], b.p0[1])
    if gap > 1 and (max(ys) <= TOUCHLINE_M or min(ys) >= width_m - TOUCHLINE_M):
        return None  # у линии скамейки с паузой: замена, а не тот же игрок
    return d + 0.4 * max(gap, 0.0)


def link_tracks(tracks: dict[int, Track], width_m: float) -> dict[int, tuple[int, float]]:
    """Конец трека -> (продолжение, стоимость) по всему фрагменту сразу."""
    ids = sorted(tracks)
    n = len(ids)
    if n < 2:
        return {}
    cost = np.full((n, n), np.inf)
    for i, a in enumerate(ids):
        for j, b in enumerate(ids):
            c = link_cost(tracks[a], tracks[b], width_m)
            if c is not None and c < CUT:
                cost[i, j] = c
    big = np.where(np.isfinite(cost), cost, 1e6)
    rows, cols = linear_sum_assignment(np.hstack([big, np.full((n, n), CUT)]))
    links = {}
    for i, j in zip(rows, cols):
        if j >= n or not np.isfinite(cost[i, j]):
            continue
        rivals = np.concatenate([np.delete(cost[i], j), np.delete(cost[:, j], i)])
        rivals = rivals[np.isfinite(rivals)]
        if rivals.size and rivals.min() - cost[i, j] < MARGIN:
            continue
        links[ids[i]] = (ids[j], round(float(cost[i, j]), 2))
    return links


def track_groups(state: pl.DataFrame, width_m: float, known: set[int] | None = None) -> list[dict]:
    """Кандидаты-игроки: цепочки треков одного человека (только из known, если задан)."""
    tracks = track_ends(state)
    if known is not None:
        tracks = {t: v for t, v in tracks.items() if t in known}
    links = link_tracks(tracks, width_m)
    has_prev = {nxt for nxt, _ in links.values()}
    groups = []
    for start in sorted(t for t in tracks if t not in has_prev):
        chain, joins, tid = [start], [], start
        while tid in links:
            nxt, c = links[tid]
            joins.append({'from': tid, 'to': nxt, 'cost': c})
            chain.append(nxt)
            tid = nxt
        if len(chain) > 1:
            groups.append({'track_ids': chain, 'links': joins})
    return groups
