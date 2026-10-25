import numpy as np
import polars as pl
from aifootball.analytics.events import extract_events, stoppages

L, W, DT = 40.0, 20.0, 0.1


def frames(n, t0=0.0):
    return [round(t0 + i * DT, 3) for i in range(n)]


def player(track_id, team, path, role='player'):
    ts = [p[0] for p in path]
    return pl.DataFrame({'frame_id': [round(t / DT) for t in ts], 'ts': ts, 'track_id': [track_id] * len(ts), 'role': [role] * len(ts),
                         'team': [team] * len(ts), 'x_m': [float(p[1]) for p in path], 'y_m': [float(p[2]) for p in path]})


def ball(path):
    return pl.DataFrame({'frame_id': [round(p[0] / DT) for p in path], 'ts': [p[0] for p in path],
                         'x_m': [float(p[1]) for p in path], 'y_m': [float(p[2]) for p in path]})


def still(t0, t1, x, y):
    return [(t, x, y) for t in frames(round((t1 - t0) / DT) + 1, t0)]


def test_completed_pass_and_carry_between_teammates():
    a1 = player(1, 'A', still(0, 1.0, 10, 10) + [(t, 10 + (t - 1.0) * 5, 10) for t in frames(10, 1.1)] + still(2.1, 4.0, 15, 10))
    a2 = player(2, 'A', still(0, 4.0, 24, 10))
    path = still(0, 1.0, 10.3, 10) + [(t, 10.3 + (t - 1.0) * 5, 10) for t in frames(10, 1.1)] + \
        [(t, 15.3 + (t - 2.0) * 8, 10) for t in frames(10, 2.1)] + still(3.1, 4.0, 24.2, 10)
    found = extract_events(ball(path), pl.concat([a1, a2]), L, W, {'A': L, 'B': 0.0})
    kinds = [e['kind'] for e in found]
    assert 'pass' in kinds and 'carry' in kinds
    passed = next(e for e in found if e['kind'] == 'pass')
    assert passed['success'] is True and passed['track_id'] == 1 and passed['recipient_track_id'] == 2


def test_fast_ball_into_the_goal_mouth_is_an_on_target_shot():
    a1 = player(1, 'A', still(0, 2.0, 30, 10))
    path = still(0, 1.0, 30.2, 10) + [(t, 30.2 + (t - 1.0) * 15, 10.2) for t in frames(6, 1.1)]
    found = extract_events(ball(path), a1, L, W, {'A': L, 'B': 0.0})
    shot = next(e for e in found if e['kind'] == 'shot')
    assert shot['on_target'] is True and shot['team'] == 'A' and shot['speed_ms'] >= 9


def test_slow_ball_or_ball_away_from_goal_is_not_a_shot():
    a1 = player(1, 'A', still(0, 2.0, 30, 10))
    slow = still(0, 1.0, 30.2, 10) + [(t, 30.2 + (t - 1.0) * 4, 10) for t in frames(6, 1.1)]
    wide = still(0, 1.0, 30.2, 10) + [(t, 30.2 + (t - 1.0) * 4, 10 + (t - 1.0) * 14) for t in frames(6, 1.1)]
    for path in (slow, wide):
        assert all(e['kind'] != 'shot' for e in extract_events(ball(path), a1, L, W, {'A': L, 'B': 0.0}))


def test_close_shot_rebounding_off_the_keeper_is_a_shot():
    # Удар с 5 м: мяч у ворот через 0,3 с, а потом отскакивает от вратаря в сторону и дальше точки удара
    a1 = player(1, 'A', still(0, 2.5, 34.8, 10))
    path = still(0, 1.0, 35.0, 10) + [(1.1, 36.7, 10.05), (1.2, 38.4, 10.1), (1.3, 39.6, 10.2)] + \
        [(t, 39.6 - (t - 1.3) * 8, 10.2 + (t - 1.3) * 5) for t in frames(10, 1.4)]
    shot = next(e for e in extract_events(ball(path), a1, L, W, {'A': L, 'B': 0.0}) if e['kind'] == 'shot')
    assert shot['team'] == 'A' and shot['on_target'] is True


def test_shot_just_wide_of_the_post_is_an_off_target_shot():
    # Мимо штанги на 2,5 м — удар мимо створа, а не передача
    a1 = player(1, 'A', still(0, 2.5, 30, 10))
    path = still(0, 1.0, 30.2, 10) + [(t, 30.2 + (t - 1.0) * 15, 10 + (t - 1.0) * 6.3) for t in frames(7, 1.1)]
    shot = next(e for e in extract_events(ball(path), a1, L, W, {'A': L, 'B': 0.0}) if e['kind'] == 'shot')
    assert shot['on_target'] is False and shot['outcome'] == 'off_target'


def test_shot_inside_a_found_stoppage_is_kept(monkeypatch):
    # Классификатор остановок смотрит на секунду вперёд и помечает остановкой сам удар, после которого игра встала
    import aifootball.analytics.events as events
    a1 = player(1, 'A', still(0, 2.0, 30, 10))
    path = still(0, 1.0, 30.2, 10) + [(t, 30.2 + (t - 1.0) * 15, 10.2) for t in frames(6, 1.1)]
    monkeypatch.setattr(events, 'stoppages', lambda *a, **k: [(0.5, 5.0)])
    assert any(e['kind'] == 'shot' for e in events.extract_events(ball(path), a1, L, W, {'A': L, 'B': 0.0}))


def test_flicker_shorter_than_minimum_run_is_not_a_turnover():
    a1 = player(1, 'A', still(0, 3.0, 10, 10))
    b1 = player(9, 'B', still(0, 3.0, 12.5, 10))
    # Мяч на долю секунды ближе к сопернику и обратно: это не потеря.
    path = still(0, 1.0, 10.2, 10) + still(1.1, 1.3, 12.3, 10) + still(1.4, 3.0, 10.2, 10)
    found = extract_events(ball(path), pl.concat([a1, b1]), L, W, {'A': L, 'B': 0.0})
    assert all(e['kind'] not in ('turnover', 'recovery') for e in found)


def test_instant_owner_change_is_not_a_pass():
    # Трек владельца пропал в толкучке, и мяч сразу у соседа: мяч не летел — это не передача
    a1 = player(1, 'A', still(0, 1.0, 10, 10))
    path = still(0, 3.0, 10.3, 10)
    teammate = extract_events(ball(path), pl.concat([a1, player(2, 'A', still(0, 3.0, 10.8, 10))]), L, W, {'A': L, 'B': 0.0})
    assert all(e['kind'] != 'pass' for e in teammate)
    # у соперника — единоборство, а не неточная передача
    opponent = extract_events(ball(path), pl.concat([a1, player(9, 'B', still(0, 3.0, 10.8, 10))]), L, W, {'A': L, 'B': 0.0})
    assert all(e['kind'] != 'pass' for e in opponent) and any(e['kind'] == 'duel' for e in opponent)


def moving(track_id, team, t0, t1, x0, y, speed, role='player'):
    """Игрок ходит туда-обратно со скоростью speed; колонка speed как в state."""
    ts = frames(round((t1 - t0) / DT) + 1, t0)
    xs = [x0 + (speed * (t - t0)) % 4.0 for t in ts]
    return pl.DataFrame({'frame_id': [round(t / DT) for t in ts], 'ts': ts, 'track_id': [track_id] * len(ts), 'role': [role] * len(ts),
                         'team': [team] * len(ts), 'x_m': xs, 'y_m': [float(y)] * len(ts), 'speed': [float(speed)] * len(ts)})


def test_stoppage_is_found_by_team_tempo():
    # 0–20 с игра (2.5 м/с), 20–35 с все стоят (0.3 м/с), 35–50 с снова игра
    def team(track, side, y):
        return pl.concat([moving(track, side, 0, 19.9, 10, y, 2.5), moving(track, side, 20, 34.9, 10, y, 0.3),
                          moving(track, side, 35, 50, 10, y, 2.5)])
    players = pl.concat([team(t, 'A' if t < 4 else 'B', 2 + 2 * t) for t in range(1, 7)])
    spans = stoppages(players, L, W)
    assert len(spans) == 1 and 19 <= spans[0][0] <= 21 and 34 <= spans[0][1] <= 36
    assert not stoppages(players.drop('speed'), L, W)
