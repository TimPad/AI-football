import numpy as np
import polars as pl
from aifootball.processor.candidates import evaluate, restart_candidates


def track(track_id, team, xs, ys, speeds, t0=0.0, dt=0.1, role='player'):
    n = len(xs)
    return pl.DataFrame({'frame_id': list(range(n)), 'ts': [t0 + i * dt for i in range(n)], 'track_id': [track_id] * n,
                         'role': [role] * n, 'team': [team] * n, 'x_m': xs, 'y_m': ys, 'speed': speeds})


def test_player_standing_on_the_sideline_is_one_candidate_with_team_and_edge():
    standing = track(1, 'B', [20.0] * 25, [0.4] * 25, [0.2] * 25, t0=10.0)
    teammate = track(2, 'B', [21.0] * 25, [0.6] * 25, [0.3] * 25, t0=10.5)
    running = track(3, 'A', list(np.linspace(5, 30, 40)), [0.5] * 40, [6.0] * 40)
    found = restart_candidates(pl.concat([standing, teammate, running]), 40.0, 20.0)
    assert len(found) == 1
    assert found[0]['team'] == 'B' and found[0]['edge'] == 'sideline' and found[0]['track_id'] == 1
    assert found[0]['kind'] == 'restart_candidate' and found[0]['start_s'] == 10.0


def test_corner_short_stops_goalkeepers_and_gaps_are_not_candidates():
    corner = track(1, 'A', [39.5] * 20, [19.4] * 20, [0.1] * 20)
    short = track(2, 'A', [10.0] * 10, [0.3] * 10, [0.1] * 10, t0=20.0)
    keeper = track(3, 'B', [0.3] * 30, [10.0] * 30, [0.1] * 30, t0=40.0, role='goalkeeper')
    gap = pl.concat([track(4, 'B', [15.0] * 8, [19.8] * 8, [0.1] * 8, t0=60.0), track(4, 'B', [15.0] * 8, [19.8] * 8, [0.1] * 8, t0=61.5)])
    found = restart_candidates(pl.concat([corner, short, keeper, gap]), 40.0, 20.0)
    assert [c['edge'] for c in found] == ['corner']


def test_evaluate_counts_matches_once_per_dead_ball():
    candidates = [{'start_s': 30.0}, {'start_s': 31.0}, {'start_s': 90.0}]
    result = evaluate(candidates, [27.0, 27.2, 60.0])
    assert result == {'candidates': 3, 'true_positive': 2, 'dead': 2, 'found': 1, 'precision': 0.667, 'recall': 0.5}
