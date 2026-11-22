"""Средние позиции игроков по видео и направление атаки для сети передач (ratings.team_stats)."""

from types import SimpleNamespace

import pytest

pytest.importorskip('sqlalchemy')

from aifootball.service.ratings.team_stats import _centroid, _cv_attack, _cv_positions  # noqa: E402

L, W = 40, 20


def heat(*cells):
    """Тепловая карта 40 × 20 клеток по 1 м: (x, y, секунды)."""
    grid = [[0.0] * W for _ in range(L)]
    for x, y, s in cells:
        grid[x][y] += s
    return grid


def period(key, players, a_x, b_x):
    """Тайм: игроки (трек, команда, клетки) и центры команд A и B по x."""
    return {
        'key': key,
        'players': [{'track_id': t, 'team': team, 'heatmap_s': heat(*cells)} for t, team, cells in players],
        'teams': {'A': {'heatmap_s': heat((a_x, 10, 100))}, 'B': {'heatmap_s': heat((b_x, 10, 100))}},
    }


def run(periods, side_map=None):
    return SimpleNamespace(
        report={'pitch': {'length_m': L, 'width_m': W, 'cell_m': 1}, 'periods': periods},
        manifest={'primary_period_key': 'all'},
        side_map=side_map or {'A': 'home', 'B': 'away'},
    )


PEOPLE = ({1: 'h1', 2: 'a1'}, {'h1': 'home', 'a1': 'away'})


def test_centroid_weights_cells_by_seconds():
    assert _centroid(heat((10, 5, 30), (20, 8, 60)), 1, L, W) == pytest.approx((17.1667, 7.5, 90), abs=1e-3)
    assert _centroid(heat(), 1, L, W) is None


def test_attack_direction_from_team_centres_and_unknown_when_close():
    r = run([period('h1', [], 12, 28), period('h2', [], 30, 10), period('h3', [], 20, 20)])
    attack = _cv_attack(r)
    assert attack['h1'] == {'A': 'right', 'B': 'left'} and attack['h2'] == {'A': 'left', 'B': 'right'}
    assert 'h3' not in attack


def test_positions_put_home_attack_right_across_halves():
    # В первом тайме хозяева (A) у левых ворот, во втором — у правых: игрок держится своей половины.
    r = run(
        [
            {**period('all', [], 20, 20), 'key': 'all'},
            period('h1', [(1, 'A', [(9, 9, 60)]), (2, 'B', [(29, 9, 60)])], 12, 28),
            period('h2', [(1, 'A', [(29, 9, 60)]), (2, 'B', [(9, 9, 60)])], 28, 12),
        ]
    )
    positions, orientation = _cv_positions(r, 'all', PEOPLE)
    assert orientation == 'attack'
    home = next(p for p in positions if p['side'] == 'home')
    away = next(p for p in positions if p['side'] == 'away')
    # Второй тайм повёрнут на 180° (и по ширине): (29.5, 9.5) -> (10.5, 10.5); в среднем своя половина слева.
    assert (home['x'], home['y'], home['observed_s']) == (10.0, 10.0, 120.0)
    assert (away['x'], away['y']) == (30.0, 10.0)  # гости атакуют влево: своя половина справа
    # Тайм отдельно — тот же разворот.
    second, _ = _cv_positions(r, '2', PEOPLE)
    assert next(p for p in second if p['side'] == 'home')['x'] == 10.5


def test_positions_turn_the_second_half_when_direction_is_unknown():
    r = run(
        [
            period('h1', [(1, 'A', [(9, 9, 60)])], 20, 20),
            period('h2', [(1, 'A', [(29, 9, 60)])], 20, 20),
        ]
    )
    positions, orientation = _cv_positions(r, 'all', PEOPLE)
    assert orientation == 'halves'
    # Второй тайм повёрнут на 180°: 29.5 -> 10.5, 9.5 -> 10.5.
    assert [(p['x'], p['y']) for p in positions] == [(10.0, 10.0)]


def test_positions_skip_foreign_and_unassigned_tracks_and_missing_periods():
    r = run([period('all', [(1, 'B', [(9, 9, 60)]), (7, 'A', [(9, 9, 60)])], 12, 28)])
    assert _cv_positions(r, 'all', PEOPLE) == ([], 'attack')
    assert _cv_positions(r, '1', PEOPLE) == ([], None)
