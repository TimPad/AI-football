"""Подсчёт scripts/eval_pass_accuracy.py на синтетических передачах: сопоставление и виды красных."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import eval_pass_accuracy as E  # noqa: E402


def truth(team, ts, completed=True):
    return {'team': team, 'ts_receive': ts, 'completed': completed}


def pred(team, end, success=True, kind='pass'):
    return {'kind': kind, 'team': team, 'start_s': end - 1, 'end_s': end, 'success': success}


def test_pairs_take_the_nearest_reception_of_the_same_team():
    t = [truth('A', 10.0), truth('A', 11.0), truth('B', 20.0)]
    p = [pred('A', 10.8), pred('A', 10.1), pred('A', 20.0)]
    assert sorted(E.pairs(t, p)) == [(0, 1), (1, 0)]


def test_score_splits_red_passes_into_true_false_and_extra():
    t = [truth('A', 10.0), truth('A', 20.0, completed=False), truth('B', 30.0)]
    p = [pred('A', 10.2, success=False), pred('A', 20.3, success=False), pred('B', 30.1), pred('B', 45.0, False)]
    s = E.score(t, p)
    assert (s['truth'], s['pred'], s['hit'], s['truth_ok'], s['pred_ok']) == (3, 4, 3, 2, 1)
    assert (s['red'], s['red_true'], s['red_false'], s['red_extra']) == (3, 1, 1, 1)


def test_missed_failures_say_where_inaccurate_passes_went():
    t = [truth('A', 10.0, False), truth('A', 20.0, False), truth('A', 30.0, False), truth('B', 40.0, False)]
    kept = [pred('A', 10.2, success=True)]
    raw = [*kept, pred('A', 20.1, success=False), {'kind': 'duel', 'team': 'B', 'start_s': 30.2}]
    assert E.missed_failures(t, kept, raw) == {
        'найдена точной': 1,
        'срезана фильтром остановок': 1,
        'единоборство': 1,
        'не найдена': 1,
    }
