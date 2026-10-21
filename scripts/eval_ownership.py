"""Правила владения мячом по журналам касаний. Отчёт — docs/2026-10-21-ball-owner-confirmation.md.

    .venv/bin/python scripts/eval_ownership.py --fragment NAME VENUE MATCH TOUCHES [...] [--grid] [--touch] [--steal] [--report-path]

Игроки, мяч и остановки берутся из готовых прогонов один раз; меняются только правило владельца и
отсев коротких отрезков владения. Передача засчитана, если та же команда и приём ±1 с, как в
scripts/eval_ball_multivenue.py passes. Выбор — по худшему F1 из отрезков.

--grid        подтверждение владельца × минимальный отрезок × удержание/захват;
--touch       «касание»: на кадре, где мяч резко меняет направление или скорость, ближайший игрок сразу владелец;
--steal       игрок, который ближе владельца на запас, забирает мяч, даже если владелец ещё в радиусе удержания;
--report-path передачи пути отчёта (perception.ball.pass_events) при подтверждении 0,33 и 0,13 с.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_ball_multivenue as E  # noqa: E402

from aifootball import schemas  # noqa: E402
from aifootball.analytics import events as EV  # noqa: E402
from aifootball.analytics.validation import truth_from_touches  # noqa: E402
from aifootball.perception import ball as B  # noqa: E402
from aifootball.processor.job import ball_settings  # noqa: E402
from aifootball.venue import load_venue  # noqa: E402

BEFORE_CONFIRM_S = 0.33  # подтверждение владельца до 21.10.2026


def load_fragment(name, venue_dir, match, touches_path):
    venue = ball_settings(load_venue(Path(venue_dir)), None)
    state, attack = E._fragment_state(venue, Path(match))
    det = schemas.read(Path(match) / 'detections.parquet', 'detections')
    ball = B.process_ball_trajectory(det.filter((pl.col('cls') != 'ball') | (pl.col('conf') >= venue.conf_ball)), venue)
    touches = pl.read_parquet(touches_path)
    _, truth_passes = truth_from_touches(touches)
    return dict(name=name, venue=venue, state=state, attack=attack, ball=ball, touches=touches,
                truth=[{'team': p['team'], 'ts': p['ts_receive']} for p in truth_passes],
                spans=EV.stoppages(state, venue.length_m, venue.width_m, ball), t0=touches['ts'].min(), t1=touches['ts'].max())


def owner_runs_touch(owners, players):
    """Как events.owner_runs, но отрезок, начавшийся с касания, не отсеивается по длине."""
    if owners.is_empty():
        return []
    agg = [pl.col('track_id').first(), pl.col('team').first(), pl.col('ts').min().alias('ts_start'), pl.col('ts').max().alias('ts_end'),
           pl.col('frame_id').min().alias('frame_start'), pl.col('frame_id').max().alias('frame_end')]
    if 'touch' in owners.columns:
        agg.append(pl.col('touch').first().alias('touch'))
    runs = (owners.with_columns(run=(pl.col('track_id') != pl.col('track_id').shift(1)).fill_null(True).cum_sum())
            .group_by('run', maintain_order=True).agg(agg).to_dicts())
    pos = {(r['frame_id'], r['track_id']): (r['x_m'], r['y_m'], r['role'])
           for r in players.select('frame_id', 'track_id', 'x_m', 'y_m', 'role').iter_rows(named=True)}
    runs = [r for r in runs if r['ts_end'] - r['ts_start'] >= EV.MIN_RUN_S or r.get('touch')]
    for r in runs:
        r['xy_start'] = pos.get((r['frame_start'], r['track_id']), (None, None, None))[:2]
        r['xy_end'] = pos.get((r['frame_end'], r['track_id']), (None, None, None))[:2]
        r['role'] = pos.get((r['frame_end'], r['track_id']), (None, None, None))[2]
    return runs


def ball_touches(ball_state, window_s=0.2, min_speed=1.5, angle_deg=45.0, dv=3.0):
    """Кадры, где мяч резко меняет направление или скорость (удар или приём); только увиденные кадры."""
    b = ball_state.sort('frame_id')
    ts, x, y, interp = (b[c].to_numpy() for c in ('ts', 'x_m', 'y_m', 'interpolated'))
    out = np.zeros(len(ts), bool)
    lo = np.searchsorted(ts, ts - window_s)
    hi = np.searchsorted(ts, ts + window_s, side='right') - 1
    for i in range(len(ts)):
        if interp[i] or lo[i] >= i or hi[i] <= i:
            continue
        a, c = lo[i], hi[i]
        vin = np.array([x[i] - x[a], y[i] - y[a]]) / max(1e-3, ts[i] - ts[a])
        vout = np.array([x[c] - x[i], y[c] - y[i]]) / max(1e-3, ts[c] - ts[i])
        sin, sout = np.hypot(*vin), np.hypot(*vout)
        if abs(sout - sin) >= dv:
            out[i] = True
        elif sin >= min_speed and sout >= min_speed:
            out[i] = float(vin @ vout) / (sin * sout) <= np.cos(np.radians(angle_deg))
    return b['frame_id'].to_numpy(), out


def make_owners(confirm_s=B.OWNER_CONFIRM_S, keep=B.KEEP_RADIUS_M, take=B.TAKE_RADIUS_M, touch=None, steal_margin=None, steal_s=None):
    """perception.ball.ball_owners с вариантами: touch=dict(r=..., параметры ball_touches), steal_margin/steal_s — перехват ближайшим."""
    def owners_fn(ball_state, player_state):
        empty = pl.DataFrame(schema={'frame_id': pl.Int32, 'ts': pl.Float64, 'track_id': pl.Int32, 'team': pl.Utf8, 'touch': pl.Boolean})
        if ball_state.is_empty() or player_state.is_empty():
            return empty
        cand = player_state.filter(pl.col('team').is_in(B.TEAMS)).select('frame_id', 'track_id', 'team', 'x_m', 'y_m')
        joined = (ball_state.select('frame_id', 'ts', 'x_m', 'y_m').join(cand, on='frame_id', suffix='_player')
                  .with_columns(dist=((pl.col('x_m') - pl.col('x_m_player')) ** 2 + (pl.col('y_m') - pl.col('y_m_player')) ** 2).sqrt())
                  .sort('frame_id', 'dist'))
        by_frame = {k[0]: g for k, g in joined.partition_by('frame_id', as_dict=True).items()}
        step = float(np.median(np.diff(ball_state['ts'].to_numpy()))) if len(ball_state) > 1 else 0.1
        confirm = max(1, round(confirm_s / step))
        steal_n = max(1, round((steal_s if steal_s is not None else confirm_s) / step))
        touched = set()
        if touch is not None:
            f, m = ball_touches(ball_state, **{k: v for k, v in touch.items() if k != 'r'})
            touched = set(f[m].tolist())
        rows = []
        owner, challenger, streak, steal_by, steal_streak = None, None, 0, None, 0
        for frame_id, ts in ball_state.select('frame_id', 'ts').sort('frame_id').iter_rows():
            g = by_frame.get(frame_id)
            tids, teams, dists = (g['track_id'].to_list(), g['team'].to_list(), g['dist'].to_list()) if g is not None else ([], [], [])
            dist = dict(zip(tids, dists))
            if frame_id in touched and tids and dists[0] <= touch['r'] and (owner is None or tids[0] != owner[0]):
                owner = (tids[0], teams[0])
                challenger, streak, steal_by, steal_streak = None, 0, None, 0
                rows.append((frame_id, ts, *owner, True))
                continue
            if owner is not None and dist.get(owner[0], np.inf) <= keep:
                challenger, streak = None, 0
                if steal_margin is not None and tids and tids[0] != owner[0] and dists[0] <= take \
                        and dists[0] + steal_margin <= dist[owner[0]]:
                    steal_streak = steal_streak + 1 if tids[0] == steal_by else 1
                    steal_by = tids[0]
                    if steal_streak >= steal_n:
                        owner, steal_by, steal_streak = (tids[0], teams[0]), None, 0
                else:
                    steal_by, steal_streak = None, 0
                rows.append((frame_id, ts, *owner, False))
                continue
            owner, steal_by, steal_streak = None, None, 0
            if not tids or dists[0] > take:
                challenger, streak = None, 0
                continue
            streak = streak + 1 if tids[0] == challenger else 1
            challenger = tids[0]
            if streak >= confirm:
                owner = (tids[0], teams[0])
                rows.append((frame_id, ts, *owner, False))
        return pl.DataFrame(rows, schema=empty.schema, orient='row') if rows else empty
    return owners_fn


def passes_for(fr, owners_fn, min_run_s):
    saved = EV.ball_owners, EV.MIN_RUN_S, EV.stoppages, EV.owner_runs
    EV.ball_owners, EV.MIN_RUN_S, EV.owner_runs = owners_fn, min_run_s, owner_runs_touch
    EV.stoppages = lambda *a, **k: fr['spans']
    try:
        events = EV.extract_events(fr['ball'], fr['state'], fr['venue'].length_m, fr['venue'].width_m, fr['attack'])
    finally:
        EV.ball_owners, EV.MIN_RUN_S, EV.stoppages, EV.owner_runs = saved
    return [{'team': e['team'], 'ts': e['end_s']} for e in events if e['kind'] == 'pass' and fr['t0'] <= e['start_s'] <= fr['t1'] + 1]


def f1(hit, n_truth, tp, n_pred):
    r, p = hit / max(1, n_truth), tp / max(1, n_pred)
    return 2 * r * p / max(1e-9, r + p)


def report(label, frags, rows):
    """rows — (найдено из журнала, передач в журнале, верных из найденных, найдено) по отрезкам."""
    halls = {}
    for fr, r in zip(frags, rows):
        h = halls.setdefault(fr['name'].split()[0], [0, 0, 0, 0])
        for i, v in enumerate(r):
            h[i] += v
    per = [f1(*r) for r in rows]
    print(f"{label:>44}: по отрезкам {'  '.join(f'{v:.2f}' for v in per)} | худший {min(per):.2f} | "
          + '  '.join(f'{k} R {v[0]}/{v[1]} P {v[2]}/{v[3]} F1 {f1(*v):.2f}' for k, v in halls.items()), flush=True)


def events_rule(label, frags, owners_fn, min_run_s=EV.MIN_RUN_S):
    rows = []
    for fr in frags:
        pred = passes_for(fr, owners_fn, min_run_s)
        rows.append((E._match(fr['truth'], pred), len(fr['truth']), E._match(pred, fr['truth']), len(pred)))
    report(label, frags, rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--fragment', nargs=4, action='append', required=True, metavar=('NAME', 'VENUE', 'MATCH', 'TOUCHES'),
                        help='NAME — «зал время»: первое слово группирует отрезки по залам')
    for flag in ('--grid', '--touch', '--steal', '--report-path'):
        parser.add_argument(flag, action='store_true')
    args = parser.parse_args()
    frags = [load_fragment(*f) for f in args.fragment]
    events_rule(f'было: подтверждение {BEFORE_CONFIRM_S} с', frags, make_owners(confirm_s=BEFORE_CONFIRM_S))
    events_rule(f'стало: подтверждение {B.OWNER_CONFIRM_S} с', frags, make_owners())
    if args.grid:
        for keep, take in ((2.5, 1.8), (2.0, 1.8), (2.5, 1.5), (3.0, 1.8)):
            print(f'-- удержание {keep} м, захват {take} м')
            for c in (0.04, 0.07, 0.1, 0.13, 0.17, 0.2, 0.33):
                for m in (0.0, 0.1, 0.2, 0.25, 0.3, 0.4, 0.5):
                    events_rule(f'подтв. {c} с, отрезок ≥ {m} с', frags, make_owners(confirm_s=c, keep=keep, take=take), m)
    if args.touch:
        for confirm in (BEFORE_CONFIRM_S, B.OWNER_CONFIRM_S):
            print(f'-- касание поверх подтверждения {confirm} с')
            for r in (0.6, 0.8, 1.2, 1.8):
                for w, ang, dv in ((0.12, 30, 2.0), (0.12, 45, 3.0), (0.12, 60, 4.0), (0.2, 45, 3.0), (0.2, 90, 6.0), (0.3, 60, 4.0)):
                    events_rule(f'r {r} м, окно {w} с, угол {ang}°, Δv {dv}', frags,
                                make_owners(confirm_s=confirm, touch=dict(r=r, window_s=w, angle_deg=ang, dv=dv)))
    if args.steal:
        print(f'-- перехват ближайшим, подтверждение {BEFORE_CONFIRM_S} с')
        for margin in (0.3, 0.6, 1.0):
            for s in (0.13, 0.33):
                events_rule(f'ближе владельца на {margin} м {s} с', frags, make_owners(confirm_s=BEFORE_CONFIRM_S, steal_margin=margin, steal_s=s))
    if args.report_path:
        saved = B.ball_owners.__defaults__
        try:
            for confirm in (BEFORE_CONFIRM_S, B.OWNER_CONFIRM_S):
                B.ball_owners.__defaults__ = (B.KEEP_RADIUS_M, B.TAKE_RADIUS_M, confirm)
                rows = []
                for fr in frags:
                    pred = [{'team': p['team'], 'ts': p['ts_receive']} for p in B.pass_events(fr['ball'], fr['state'])
                            if fr['t0'] <= p['ts_receive'] <= fr['t1'] + 1]
                    rows.append((E._match(fr['truth'], pred), len(fr['truth']), E._match(pred, fr['truth']), len(pred)))
                report(f'путь отчёта, подтверждение {confirm} с', frags, rows)
        finally:
            B.ball_owners.__defaults__ = saved


if __name__ == '__main__':
    main()
