"""Оценка автоматических событий по ручной разметке (локальные данные, вне Git).

Передачи, потери и возвраты — по журналу касаний data/gt/*/touches.parquet; удары — по data/gt/*/shots.parquet
(размечены по раскадровкам кандидатов, проверена только часть кандидатов, поэтому полнота ударов — оценка сверху).
Остановки игры — по отметкам «мяч вне игры» того же журнала.
Позиции игроков пересчитываются из tracks.parquet текущим кодом (точка ног, проекция), вратари — по воротам.

python scripts/eval_events.py
"""
from pathlib import Path
import polars as pl
from aifootball import schemas
from aifootball.venue import load_venue
from aifootball.perception.ball import process_ball_trajectory
from aifootball.perception.teams import defending_sides
from aifootball.analytics.events import extract_events, stoppages
from aifootball.analytics.report_data import assign_goalkeeper_teams
from aifootball.analytics.validation import truth_from_touches
from aifootball.perception.track import _compute_robust_foot_points
from aifootball.state.project import project_tracks

FRAGMENTS = [('yaroslavl-60-240', 'data/matches/yaroslavl-60-240-v2'), ('yaroslavl-600-780', 'data/matches/yaroslavl-600-780-v2')]
TOL_S = 1.0


def match(truth, found, tol=TOL_S):
    used, hit = set(), 0
    for t in truth:
        best = min((i for i, f in enumerate(found) if i not in used and f['team'] == t['team'] and abs(f['ts'] - t['ts']) <= tol),
                   key=lambda i: abs(found[i]['ts'] - t['ts']), default=None)
        if best is not None:
            used.add(best); hit += 1
    return hit


def main():
    venue = load_venue(Path('configs/venues/yaroslavl'))
    total = {}
    for name, folder in FRAGMENTS:
        tracks = schemas.read(Path(folder) / 'tracks.parquet', 'tracks')
        tracks = tracks.with_columns(foot_y=pl.Series(_compute_robust_foot_points(tracks)[1]))
        state = project_tracks(tracks, venue)
        state = assign_goalkeeper_teams(state, [(state['ts'].min(), state['ts'].max() + 1)], venue.length_m)
        ball = process_ball_trajectory(schemas.read(Path(folder) / 'detections.parquet', 'detections'), venue)
        sides = defending_sides(state)
        attack = {sides[0]: venue.length_m, sides[1]: 0.0} if sides else None
        events = extract_events(ball, state, venue.length_m, venue.width_m, attack)
        touches = pl.read_parquet(f'data/gt/{name}/touches.parquet')
        t0, t1 = touches['ts'].min(), touches['ts'].max()
        events = [e for e in events if t0 <= e['start_s'] <= t1 + 1]
        intervals, truth_passes = truth_from_touches(touches)
        dead = [(a, b) for a, b, team in intervals if team is None]
        found_stops = stoppages(state, venue.length_m, venue.width_m)
        overlap = lambda xs, ys: sum(max(0.0, min(b, d) - max(a, c)) for a, b in xs for c, d in ys)
        clip = [(max(a, t0), min(b, t1)) for a, b in found_stops if b > t0 and a < t1]
        dead_s, found_s, both_s = sum(b - a for a, b in dead), sum(b - a for a, b in clip), overlap(dead, clip)
        total.setdefault('остановки, с', [0, 0, 0, 0])
        for i, v in enumerate((both_s, dead_s, both_s, found_s)): total['остановки, с'][i] += v
        print(f"{name} · остановки: по журналу {dead_s:.0f} с, найдено {found_s:.0f} с, из них верно {both_s:.0f} с")
        cases = {
            'передачи (все)': ([{'team': p['team'], 'ts': p['ts_receive']} for p in truth_passes],
                               [{'team': e['team'], 'ts': e['end_s']} for e in events if e['kind'] == 'pass']),
            'точные передачи': ([{'team': p['team'], 'ts': p['ts_receive']} for p in truth_passes if p['completed']],
                                [{'team': e['team'], 'ts': e['end_s']} for e in events if e['kind'] == 'pass' and e['success']]),
            'возвраты мяча': ([{'team': 'B' if p['team'] == 'A' else 'A', 'ts': p['ts_receive']} for p in truth_passes if not p['completed']],
                              [{'team': e['team'], 'ts': e['start_s']} for e in events if e['kind'] == 'recovery']),
        }
        shots_path = Path(f'data/gt/{name}/shots.parquet')
        if shots_path.exists():
            shots = pl.read_parquet(shots_path)
            found = [e for e in events if e['kind'] == 'shot']
            truth = [{'team': None, 'ts': t} for t in shots['ts'].to_list()]
            hit = sum(any(abs(e['start_s'] - t['ts']) <= TOL_S for e in found) for t in truth)
            tp = sum(any(abs(e['start_s'] - t['ts']) <= TOL_S for t in truth) for e in found)
            cases['удары'] = None
            total.setdefault('удары', [0, 0, 0, 0])
            for i, v in enumerate((hit, len(truth), tp, len(found))): total['удары'][i] += v
            print(f"{name} · удары: найдено верных {tp}/{len(found)}, пойманных из размеченных {hit}/{len(truth)}")
        for label, value in cases.items():
            if value is None: continue
            truth, found = value
            hit = match(truth, found); tp = match(found, truth)
            total.setdefault(label, [0, 0, 0, 0])
            for i, v in enumerate((hit, len(truth), tp, len(found))): total[label][i] += v
            print(f"{name} · {label}: полнота {hit}/{len(truth)}, точность {tp}/{len(found)}")
    print('ИТОГО')
    for label, (hit, n_truth, tp, n_found) in total.items():
        fmt = (lambda v: f'{v:.0f}') if label == 'остановки, с' else str
        print(f"  {label}: полнота {fmt(hit)}/{fmt(n_truth)} ({hit / max(1, n_truth):.2f}), точность {fmt(tp)}/{fmt(n_found)} ({tp / max(1, n_found):.2f})")


if __name__ == '__main__':
    main()
