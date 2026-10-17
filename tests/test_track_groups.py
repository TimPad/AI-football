"""Склейка треков в кандидатов-игроков и проверка групп в пакете результата."""
import numpy as np
import polars as pl
import pytest
from test_analysis_exchange import result_zip

from aifootball.analytics.track_groups import track_groups

FPS = 10


def piece(tid, team, t0, t1, start, end, role='player'):
    """Трек, идущий по прямой от start до end за [t0, t1]."""
    ts = np.arange(t0, t1 + 1e-9, 1 / FPS)
    k = (ts - t0) / max(t1 - t0, 1e-9)
    return [{'track_id': tid, 'ts': float(t), 'team': team, 'role': role,
             'x_m': start[0] + (end[0] - start[0]) * f, 'y_m': start[1] + (end[1] - start[1]) * f} for t, f in zip(ts, k)]


def state(*pieces):
    return pl.DataFrame([row for p in pieces for row in p])


def chains(rows, width=20.0):
    return [g['track_ids'] for g in track_groups(state(*rows), width)]


def test_a_lost_player_is_picked_up_by_the_next_track_nearby():
    rows = [piece(1, 'A', 0, 10, (5, 5), (10, 5)), piece(2, 'A', 12, 20, (11, 5), (15, 8)),
            piece(3, 'A', 0, 20, (30, 15), (30, 15))]  # другой игрок всё время на месте
    assert chains(rows) == [[1, 2]]


def test_impossible_or_simultaneous_continuations_are_not_joined():
    # 20 м за 1 с — быстрее любого игрока; одновременно видимые треки в разных местах — разные люди.
    assert chains([piece(1, 'A', 0, 10, (5, 5), (10, 5)), piece(2, 'A', 11, 20, (30, 5), (32, 5))]) == []
    assert chains([piece(1, 'A', 0, 10, (5, 5), (10, 5)), piece(2, 'A', 8, 20, (10, 12), (12, 12))]) == []
    # Короткий дубль трекера в той же точке — один человек.
    assert chains([piece(1, 'A', 0, 10, (5, 5), (10, 5)), piece(2, 'A', 9.6, 20, (10, 5.5), (12, 6))]) == [[1, 2]]


def test_other_team_and_bench_exchanges_stay_apart():
    assert chains([piece(1, 'A', 0, 10, (5, 5), (10, 5)), piece(2, 'B', 11, 20, (10, 6), (12, 6))]) == []
    # Один ушёл к скамейке, через 3 с рядом вышел другой — это замена.
    assert chains([piece(1, 'A', 0, 10, (20, 5), (25, 0.2)), piece(2, 'A', 13, 20, (26, 0.3), (20, 6))]) == []


def test_an_ambiguous_end_is_left_to_the_admin():
    # Два почти одинаково близких продолжения: угадывать нельзя.
    rows = [piece(1, 'A', 0, 10, (10, 10), (10, 10)), piece(2, 'A', 11, 20, (11, 10), (15, 10)),
            piece(3, 'A', 11, 20, (9, 10), (5, 10))]
    assert chains(rows) == []


def test_a_long_chain_survives_several_breaks():
    rows = [piece(1, 'A', 0, 10, (5, 5), (10, 5)), piece(2, 'A', 11, 20, (10.5, 5), (14, 9)),
            piece(3, 'A', 22, 30, (14.5, 9.5), (20, 10)), piece(4, 'A', 31, 40, (20.5, 10), (25, 12), role='goalkeeper')]
    assert chains(rows) == [[1, 2, 3, 4]]


@pytest.mark.parametrize('groups,message', [
    ([{'track_ids': [1, 3]}], 'смешивает'),
    ([{'track_ids': [2, 1]}], 'одновременно'),
    ([{'track_ids': [1, 1]}], 'повторный'),
    ([{'track_ids': [1, 99]}], 'неизвестный'),
    ([{'track_ids': [1]}], 'Неверная группа'),
    ([{'track_ids': [1, 2]}, {'track_ids': [2, 1]}], 'повторный'),
    ([{'track_ids': [1, 2], 'links': [{'from': 1, 'to': 5, 'cost': 1}]}], 'связи'),
])
def test_package_groups_are_validated(groups, message):
    from aifootball.analytics.exchange import ExchangeError, validate_result
    with pytest.raises(ExchangeError, match=message):
        validate_result(result_zip(mutate=lambda m, r, t, c: t.update(groups=groups)))


def test_package_groups_allow_a_short_handoff():
    from aifootball.analytics.exchange import ExchangeError, validate_result
    def handoff(overlap):
        def mutate(m, r, t, c):
            t['tracks'][1]['intervals'] = [[60 - overlap, 240]]
            t['groups'] = [{'track_ids': [1, 2], 'links': [{'from': 1, 'to': 2, 'cost': 0.4}]}]
        return mutate
    assert validate_result(result_zip(mutate=handoff(0.8))).tracks['groups'][0]['track_ids'] == [1, 2]
    with pytest.raises(ExchangeError, match='одновременно'):
        validate_result(result_zip(mutate=handoff(5)))
