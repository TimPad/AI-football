"""Сборка фрагментов в людей по внешности: запрет одновременных, порог, ключи, сомнительные, неразобранные."""

import numpy as np
import pytest

from aifootball.analytics.people import Unit, assemble, cluster, conflicts, max_overlap, units_from_index


def v(*xs):
    a = np.array(xs, float)
    return a / np.linalg.norm(a)


def unit(tids, team, start, end, feature):
    return Unit(tuple(tids), team, ((float(start), float(end)),), feature)


def groups_of(units, threshold):
    return sorted(sorted(g) for g in cluster(units, threshold, conflicts(units)))


def test_max_overlap_is_the_longest_shared_interval():
    assert max_overlap(((0, 10),), ((9.5, 20),)) == pytest.approx(0.5)
    assert max_overlap(((0, 10), (30, 40)), ((35, 50),)) == pytest.approx(5)
    assert max_overlap(((0, 10),), ((11, 20),)) <= 0


def test_simultaneous_or_other_team_units_never_merge():
    same_time = [unit([1], 'A', 0, 30, v(1, 0)), unit([2], 'A', 10, 40, v(1, 0))]
    other_team = [unit([1], 'A', 0, 10, v(1, 0)), unit([2], 'B', 20, 30, v(1, 0))]
    assert groups_of(same_time, 0.5) == [[0], [1]]
    assert groups_of(other_team, 0.5) == [[0], [1]]


def test_merging_stops_at_threshold_and_blocks_add_up():
    # 0 и 1 склеиваются первыми; 2 похож на обоих, но виден одновременно с 1 — к их человеку не присоединяется.
    units = [
        unit([1], 'A', 0, 10, v(1, 0)),
        unit([2], 'A', 20, 30, v(1, 0.05)),
        unit([3], 'A', 25, 35, v(1, 0.1)),
        unit([4], 'A', 50, 60, v(0, 1)),
    ]
    assert groups_of(units, 0.9) == [[0, 1], [2], [3]]


def test_units_without_features_stay_alone():
    units = [unit([1], 'A', 0, 10, None), unit([2], 'A', 20, 30, v(1, 0)), unit([3], 'A', 40, 50, v(1, 0))]
    assert groups_of(units, 0.5) == [[0], [1, 2]]


def test_people_keys_doubtful_and_unsorted():
    units = [
        unit([1], 'A', 0, 40, v(1, 0, 0)),
        Unit((2, 3), 'A', ((50.0, 75.0), (75.0, 100.0)), v(1, 0.1, 0)),  # цепочка по движению
        unit([4], 'A', 0, 30, v(0, 1, 0)),  # второй человек, виден вместе с первым
        unit([5], 'A', 120, 125, v(0.7, 0.7, 0)),  # между ними: склеится с первым, но сомнительно
        unit([6], 'A', 200, 203, None),  # без кадров
        unit([7], 'A', 300, 310, v(0, 0, 1)),  # один, 10 с — короче человека
    ]
    people = assemble(units, threshold=0.6, margin=0.1)
    assert [(p.key, p.track_ids) for p in people.persons] == [('A1', [1, 2, 3, 5]), ('A2', [4])]
    first = people.persons[0]
    assert first.doubtful == [5] and first.seconds == pytest.approx(95)
    assert first.scores[0] == pytest.approx(0.851, abs=1e-3)  # среднее похожести на 2–3 и 5
    assert people.persons[1].scores == [1.0]  # единственная единица человека
    assert [u['track_id'] for u in people.unsorted] == [6, 7]
    assert people.unsorted[0]['suggestions'] == []
    assert [s['key'] for s in people.unsorted[1]['suggestions']] == ['A1', 'A2']


def test_units_follow_motion_chains_and_weight_features_by_time():
    index = {
        'tracks': [
            {'track_id': 1, 'team': 'A', 'role': 'player', 'intervals': [[0, 10]]},
            {'track_id': 2, 'team': 'A', 'role': 'player', 'intervals': [[11, 30]]},
            {'track_id': 3, 'team': 'B', 'role': 'goalkeeper', 'intervals': [[0, 5]]},
            {'track_id': 4, 'team': None, 'role': 'referee', 'intervals': [[0, 50]]},
        ],
        'groups': [{'track_ids': [1, 2], 'links': []}],
    }
    units = units_from_index(index, {1: v(1, 0), 2: v(0, 1)})
    assert [(u.track_ids, u.team) for u in units] == [((1, 2), 'A'), ((3,), 'B')]
    assert units[0].feature == pytest.approx(v(10, 19))
    assert units[1].feature is None
