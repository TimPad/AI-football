import numpy as np
import polars as pl
import pytest

from aifootball.analytics import stoppage_model as sm
from aifootball.analytics.events import stoppages

L, W, DT = 40.0, 20.0, 0.1


def field(t0, t1, speed, *, tracks=range(1, 7), y=None):
    ts = [round(t0 + i * DT, 3) for i in range(round((t1 - t0) / DT))]
    rows = []
    for tid in tracks:
        for t in ts:
            rows.append({'frame_id': round(t / DT), 'ts': t, 'track_id': tid, 'role': 'player', 'team': 'A' if tid < 4 else 'B',
                         'x_m': 10.0 + (speed * t) % 4.0, 'y_m': float(y if y is not None else 2 + 2 * tid), 'speed': float(speed)})
    return pl.DataFrame(rows)


def ball_seen(t0, t1, every=1, x=20.0, y=10.0, speed=3.0):
    ts = [round(t0 + i * DT, 3) for i in range(round((t1 - t0) / DT))]
    return pl.DataFrame({'frame_id': [round(t / DT) for t in ts], 'ts': ts, 'x_m': [x] * len(ts), 'y_m': [y] * len(ts),
                         'speed': [speed] * len(ts), 'interpolated': [i % every != 0 for i in range(len(ts))]})


def test_second_features_are_relative_to_the_match_and_count_seen_ball():
    players = field(0, 10, 2.0)
    feats = sm.second_features(players, ball_seen(0, 10, every=2), L, W, viterbi=[])
    row = dict(zip(sm.FEATURES, feats[5]))
    assert row['speed_p50'] == pytest.approx(1.0)       # скорость в долях медианы матча
    assert row['speed_spread'] == pytest.approx(0.0)
    assert row['player_edge_m'] == pytest.approx(4.0)   # ближайший к линии игрок — y = 4 м
    assert row['ball_seen'] == pytest.approx(0.5, abs=0.05)
    assert row['ball_speed'] == pytest.approx(3.0)
    assert row['ball_edge_m'] == pytest.approx(10.0)
    assert row['viterbi'] == 0.0


def test_second_without_ball_uses_neutral_ball_features():
    feats = sm.second_features(field(0, 10, 2.0), None, L, W, viterbi=[(4.0, 7.0)])
    row = dict(zip(sm.FEATURES, feats[5]))
    assert row['ball_seen'] == 0.0 and row['ball_edge_m'] == sm.NO_BALL_EDGE_M
    assert row['viterbi'] == 1.0


def test_spans_merge_consecutive_stoppage_seconds():
    # Модель, которая верит только Витерби: отрезки должны совпасть с его секундами и склеиться.
    only_viterbi = {'features': sm.FEATURES, 'mean': [0.0] * len(sm.FEATURES), 'std': [1.0] * len(sm.FEATURES),
                    'weights': [0.0] * (len(sm.FEATURES) - 1) + [10.0], 'bias': -5.0}
    spans = sm.stoppage_spans(field(0, 20, 2.0), None, L, W, viterbi=[(5.0, 8.0), (12.0, 13.0)], model=only_viterbi)
    assert spans == [(5.0, 8.0), (12.0, 13.0)]


@pytest.mark.parametrize('with_ball', [True, False])
def test_shipped_models_find_a_team_wide_pause(with_ball):
    # 0–20 с игра (2.5 м/с), 20–35 с все стоят (0.3 м/с), 35–50 с снова игра
    players = pl.concat([field(0, 20, 2.5), field(20, 35, 0.3), field(35, 50, 2.5)])
    ball = pl.concat([ball_seen(0, 20, speed=6.0), ball_seen(20, 35, every=5, speed=0.5), ball_seen(35, 50, speed=6.0)]) if with_ball else None
    spans = stoppages(players, L, W, ball)
    assert len(spans) == 1 and 19 <= spans[0][0] <= 22 and 33 <= spans[0][1] <= 36


def test_shipped_models_have_matching_shapes():
    for model in (sm.WITH_BALL, sm.NO_BALL):
        n = len(model['features'])
        assert set(model['features']) <= set(sm.FEATURES)
        assert len(model['mean']) == len(model['std']) == len(model['weights']) == n
        assert all(s > 0 for s in model['std'])
    assert np.isfinite(sm.WITH_BALL['bias']) and np.isfinite(sm.NO_BALL['bias'])
