"""Проверка моделей мяча по эталонам и журналам. Отчёт — docs/2026-10-20-multi-venue-ball-model.md.

    .venv/bin/python scripts/eval_ball_multivenue.py frames --weights NAME=W [...] --hall NAME VENUE VIDEO BALL_LABELS [...]
    .venv/bin/python scripts/eval_ball_multivenue.py select --hall NAME VENUE BALL_LABELS MATCH CANDIDATES [...]
    .venv/bin/python scripts/eval_ball_multivenue.py passes --fragment HALL VENUE MATCH TOUCHES CANDIDATES [...]
    .venv/bin/python scripts/eval_ball_multivenue.py missed --fragment HALL VENUE MATCH TOUCHES [...]

frames  — модель на кадрах эталона тем же путём, что пайплайн (BallDetector), метрики analytics.validation.evaluate_ball.
select  — как выбрать один мяч на кадр из кандидатов (ball_model_multivenue.py candidates): по уверенности, + отсев
          скачков > 25 м/с (как process_ball_trajectory), + «неподвижный мяч», + «не на торсе». «Найден» — выбранный
          кандидат накрывает клик; «точность» — доля кадров с выбранным кандидатом (мяч виден или его нет), где это мяч.
passes  — передачи, владение и остановки по журналу, если в готовом прогоне заменить мяч кандидатами; игроки из прогона,
          позиции пересчитаны текущим кодом, как scripts/eval_events.py.
missed  — для каждой пропущенной передачи журнала: первое звено цепочки, которое порвалось у момента приёма.
Пороги правил заданы из физики игры и под залы не подбирались.
"""
import argparse
from collections import Counter
from pathlib import Path

import numpy as np
import polars as pl

from aifootball import schemas
from aifootball.analytics.validation import BALL_HIT_TOL_PX
from aifootball.geometry.homography import apply_homography
from aifootball.geometry.polygons import points_near_polygon
from aifootball.geometry.undistort import undistort_points
from aifootball.perception.ball import _filter_ball_spikes
from aifootball.processor.job import ball_settings
from aifootball.venue import load_venue

PIPELINE_CONF = 0.25
TORSO = (0.0, 0.6)  # доля высоты рамки человека от макушки: мяч там не бывает, а номера на футболках — да
STATIC_WINDOW_S = 10.0  # «мяч», стоящий на месте дольше, чем бывает в игре, — рука зрителя на бортике, предмет у скамейки
STATIC_RADIUS_PX = 15
STATIC_SHARE = 0.5
PASS_TOL_S = 1.0
MISS_WINDOW_S = 0.5


def centers_of(c: pl.DataFrame) -> np.ndarray:
    return np.column_stack([((c['x1'] + c['x2']) / 2).to_numpy(), ((c['y1'] + c['y2']) / 2).to_numpy()])


def static_mask(frames: np.ndarray, centers: np.ndarray, fps: float) -> np.ndarray:
    """Кандидат неподвижен, если в окне ±STATIC_WINDOW_S в той же точке есть кандидат не меньше чем в STATIC_SHARE кадров."""
    from scipy.spatial import cKDTree

    if len(frames) == 0:
        return np.zeros(0, bool)
    half = int(round(STATIC_WINDOW_S * fps))
    out = np.zeros(len(frames), bool)
    for i, near in enumerate(cKDTree(centers).query_ball_point(centers, STATIC_RADIUS_PX)):
        f = frames[near]
        f = f[np.abs(f - frames[i]) <= half]
        lo, hi = max(frames.min(), frames[i] - half), min(frames.max(), frames[i] + half)
        out[i] = len(np.unique(f)) >= STATIC_SHARE * (hi - lo + 1)
    return out


def torso_mask(cand: pl.DataFrame, persons: pl.DataFrame) -> np.ndarray:
    by_frame = {k[0]: g.select('x1', 'y1', 'x2', 'y2').to_numpy() for k, g in persons.partition_by('frame_id', as_dict=True).items()}
    cx, cy = centers_of(cand).T if len(cand) else (np.zeros(0), np.zeros(0))
    out = np.zeros(len(cand), bool)
    for i, f in enumerate(cand['frame_id'].to_list()):
        p = by_frame.get(f)
        if p is None:
            continue
        inside = (p[:, 0] <= cx[i]) & (cx[i] <= p[:, 2]) & (p[:, 1] <= cy[i]) & (cy[i] <= p[:, 3])
        rel = (cy[i] - p[inside, 1]) / (p[inside, 3] - p[inside, 1])
        out[i] = bool(((rel >= TORSO[0]) & (rel < TORSO[1])).any())
    return out


def on_pitch_metres(c: pl.DataFrame, venue) -> pl.DataFrame:
    """Кандидаты у поля, как в process_ball_trajectory, с точкой на полу в метрах."""
    def floor(df):
        return np.column_stack([((df['x1'] + df['x2']) / 2).to_numpy(), df['y2'].to_numpy()])

    c = c.filter(pl.Series(points_near_polygon(floor(c), venue.require_polygon(), venue.ball_margin_px)))
    m = apply_homography(venue.H, undistort_points(floor(c), venue.calib))
    return c.with_columns(x_m=pl.Series(m[:, 0]), y_m=pl.Series(m[:, 1]))


def top_per_frame(c: pl.DataFrame) -> pl.DataFrame:
    return c.sort('conf', descending=True).unique('frame_id', keep='first').sort('frame_id')


def pipeline_pick(c: pl.DataFrame, fps: float, conf: float = PIPELINE_CONF, static: bool = True, spikes: bool = True) -> pl.DataFrame:
    """Один мяч на кадр: порог, без неподвижных, самый уверенный, отсев скачков > 25 м/с."""
    k = c.filter(pl.col('conf') >= conf)
    if static and len(k):
        k = k.filter(~pl.Series(static_mask(k['frame_id'].to_numpy(), centers_of(k), fps)))
    k = top_per_frame(k)
    if not spikes or len(k) < 2:
        return k
    _, _, _, kept = _filter_ball_spikes((k['frame_id'] / fps).to_numpy(), k['x_m'].to_numpy(), k['y_m'].to_numpy(), k['frame_id'].to_numpy())
    return k.filter(pl.col('frame_id').is_in(kept.tolist()))


def score_pick(pick: pl.DataFrame, labels: pl.DataFrame) -> str:
    by = {f: b for f, *b in pick.select('frame_id', 'x1', 'y1', 'x2', 'y2').iter_rows()}
    t = BALL_HIT_TOL_PX
    right = wrong = 0
    visible = labels.filter(pl.col('status') == 'visible')
    for f, x, y in visible.select('frame_id', 'x', 'y').iter_rows():
        b = by.get(f)
        if b is not None:
            hit = b[0] - t <= x <= b[2] + t and b[1] - t <= y <= b[3] + t
            right, wrong = right + hit, wrong + (not hit)
    absent = labels.filter(pl.col('status') == 'absent')['frame_id'].to_list()
    false_alarms = sum(f in by for f in absent)
    return (f'найден {right}/{len(visible)} ({right / max(1, len(visible)):.0%}), '
            f'точность {right / max(1, right + wrong + false_alarms):.2f}, ложные без мяча {false_alarms}/{len(absent)}')


def cmd_frames(args) -> None:
    import cv2

    from aifootball.analytics.validation import evaluate_ball
    from aifootball.perception.ball_detect import BallDetector
    from aifootball.perception.detect import pick_device

    for hall, venue_dir, video, labels_path in args.hall:
        labels = schemas.read(Path(labels_path), 'ball_labels')
        cap = cv2.VideoCapture(video)
        shape = (int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
        venue = ball_settings(load_venue(Path(venue_dir)), shape[1])
        frames = {}
        for f, ts in labels.select('frame_id', 'ts').iter_rows():
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ok, frame = cap.read()
            if ok:
                frames[f] = (ts, frame)
        cap.release()
        for spec in args.weights:
            name, weights = spec.split('=', 1)
            det = BallDetector(Path(weights), venue.require_polygon(), shape, venue.ball_tile, venue.ball_margin_px, 0.05, pick_device())
            rows = []
            for f, (ts, frame) in frames.items():
                boxes, confs = det(frame)
                rows += [{'frame_id': f, 'ts': ts, 'cls': 'ball', 'x1': float(b[0]), 'y1': float(b[1]), 'x2': float(b[2]),
                          'y2': float(b[3]), 'conf': float(c), 'torso_l': np.nan, 'torso_a': np.nan, 'torso_b': np.nan}
                         for b, c in zip(boxes, confs)]
            detections = pl.DataFrame(rows, schema=schemas.DETECTIONS) if rows else schemas.empty('detections')
            for conf in (0.1, 0.25, 0.5):
                r = evaluate_ball(detections, labels, venue, conf_min=conf)
                precision = r['precision'] if r['precision'] is not None else float('nan')
                print(f"{hall} · {name}, порог {conf}: найдено {r['found']}/{r['visible']} ({r['recall']:.0%}), самая уверенная — "
                      f"мяч {precision:.2f}, ложные в кадрах без мяча {r['false_alarm_frames']}/{r['absent']}", flush=True)


def cmd_select(args) -> None:
    for hall, venue_dir, labels_path, match, candidates in args.hall:
        venue = load_venue(Path(venue_dir))
        labels = schemas.read(Path(labels_path), 'ball_labels')
        c = on_pitch_metres(pl.read_parquet(candidates), venue)
        persons = pl.read_parquet(Path(match) / 'detections.parquet').filter(pl.col('cls') == 'person')
        c = c.with_columns(torso=pl.Series(torso_mask(c, persons)))
        fps = venue.target_fps
        print(f'== {hall}: кандидатов {len(c)}')
        print(f'  самый уверенный:                       {score_pick(pipeline_pick(c, fps, static=False, spikes=False), labels)}')
        print(f'  + отсев скачков (как пайплайн):        {score_pick(pipeline_pick(c, fps, static=False), labels)}')
        print(f'  + неподвижный мяч:                     {score_pick(pipeline_pick(c, fps), labels)}')
        print(f'  + неподвижный мяч + не на торсе:       {score_pick(pipeline_pick(c.filter(~pl.col("torso")), fps), labels)}')


def _fragment_state(venue, match: Path):
    from aifootball.analytics.report_data import assign_goalkeeper_teams
    from aifootball.perception.teams import defending_sides
    from aifootball.perception.track import _compute_robust_foot_points
    from aifootball.state.project import project_tracks

    tracks = schemas.read(match / 'tracks.parquet', 'tracks')
    tracks = tracks.with_columns(foot_y=pl.Series(_compute_robust_foot_points(tracks)[1]))
    state = project_tracks(tracks, venue)
    state = assign_goalkeeper_teams(state, [(state['ts'].min(), state['ts'].max() + 1)], venue.length_m)
    sides = defending_sides(state)
    attack = {sides[0]: venue.length_m, sides[1]: 0.0} if sides else None
    return state, attack


def _match(truth: list[dict], found: list[dict]) -> int:
    used, hit = set(), 0
    for t in truth:
        best = min((i for i, f in enumerate(found) if i not in used and f['team'] == t['team'] and abs(f['ts'] - t['ts']) <= PASS_TOL_S),
                   key=lambda i: abs(found[i]['ts'] - t['ts']), default=None)
        if best is not None:
            used.add(best)
            hit += 1
    return hit


def _swap_ball(det: pl.DataFrame, cand: pl.DataFrame, torso: bool, static: bool, fps: float) -> pl.DataFrame:
    persons = det.filter(pl.col('cls') != 'ball')
    frames = det.select('frame_id', 'ts').unique().sort('frame_id')
    c = cand.filter(pl.col('conf') >= PIPELINE_CONF)
    if static and len(c):
        c = c.filter(~pl.Series(static_mask(c['frame_id'].to_numpy(), centers_of(c), fps)))
    if torso:
        c = c.filter(~pl.Series(torso_mask(c, persons.filter(pl.col('cls') == 'person'))))
    ts = np.interp(c['frame_id'].to_numpy(), frames['frame_id'].to_numpy(), frames['ts'].to_numpy())
    balls = c.with_columns(ts=pl.Series(ts), cls=pl.lit('ball'), torso_l=pl.lit(np.nan), torso_a=pl.lit(np.nan),
                           torso_b=pl.lit(np.nan)).select(persons.columns).cast(dict(persons.schema))
    return pl.concat([persons, balls]).sort('frame_id')


def cmd_passes(args) -> None:
    from aifootball.analytics.events import extract_events, stoppages
    from aifootball.analytics.validation import evaluate_possession, truth_from_touches
    from aifootball.perception.ball import process_ball_trajectory

    variants = [('мяч прогона', None, None), ('кандидаты', False, False), ('+ не на торсе', True, False),
                ('+ неподвижный мяч', False, True), ('+ неподвижный + торс', True, True)]
    total = {}
    for hall, venue_dir, match, touches_path, candidates in args.fragment:
        venue = ball_settings(load_venue(Path(venue_dir)), None)
        state, attack = _fragment_state(venue, Path(match))
        det = schemas.read(Path(match) / 'detections.parquet', 'detections')
        cand = pl.read_parquet(candidates)
        touches = pl.read_parquet(touches_path)
        t0, t1 = touches['ts'].min(), touches['ts'].max()
        intervals, truth_passes = truth_from_touches(touches)
        dead = [(a, b) for a, b, team in intervals if team is None]
        truth = [{'team': p['team'], 'ts': p['ts_receive']} for p in truth_passes]
        print(f'== {hall} · {Path(match).name}: передач в журнале {len(truth)}, остановок {len(dead)}')
        for label, torso, static in variants:
            d = (det.filter((pl.col('cls') != 'ball') | (pl.col('conf') >= venue.conf_ball)) if torso is None
                 else _swap_ball(det, cand, torso, static, venue.target_fps))
            ball = process_ball_trajectory(d, venue)
            events = [e for e in extract_events(ball, state, venue.length_m, venue.width_m, attack) if t0 <= e['start_s'] <= t1 + 1]
            pred = [{'team': e['team'], 'ts': e['end_s']} for e in events if e['kind'] == 'pass']
            hit, tp = _match(truth, pred), _match(pred, truth)
            pos = evaluate_possession(ball, state, touches)
            ag = pos['possession_by_time_s']
            agree = (ag['A']['A'] + ag['B']['B']) / max(1e-9, sum(ag['A'].values()) + sum(ag['B'].values()))
            stops = [(max(a, t0), min(b, t1)) for a, b in stoppages(state, venue.length_m, venue.width_m, ball) if b > t0 and a < t1]
            both = sum(max(0.0, min(b, d2) - max(a, c)) for a, b in dead for c, d2 in stops)
            seen = ball.filter(~pl.col('interpolated')).height / max(1, det['frame_id'].n_unique())
            print(f"  {label:>22}: мяч {seen:.0%} кадров; передачи R {hit}/{len(truth)} P {tp}/{len(pred)}; синие "
                  f"{pos['possession']['truth_pct']['A']}% журнал / {pos['possession']['pipeline_pct']['A']}%; команда у мяча "
                  f"{agree:.0%} игрового времени; остановки R {both / max(1, sum(b - a for a, b in dead)):.2f} "
                  f"P {both / max(1, sum(b - a for a, b in stops)):.2f}")
            t = total.setdefault((hall, label), [0, 0, 0, 0])
            for i, v in enumerate((hit, len(truth), tp, len(pred))):
                t[i] += v
    print('ИТОГО по залам: передачи')
    for (hall, label), (hit, n_truth, tp, n_found) in total.items():
        r, p = hit / max(1, n_truth), tp / max(1, n_found)
        print(f'  {hall:>10} · {label:>22}: R {hit}/{n_truth} ({r:.2f}) P {tp}/{n_found} ({p:.2f}) F1 {2 * r * p / max(1e-9, r + p):.2f}')


def cmd_missed(args) -> None:
    """Звенья по порядку: мяч у приёма → игрок рядом → владелец подтверждён → команда владельца →
    смена владельца → что пайплайн из смены сделал (передача другой команды, удар, остановка, долгий полёт)."""
    from aifootball.analytics.events import MAX_PASS_FLIGHT_S, extract_events, owner_runs, stoppages
    from aifootball.perception.ball import TAKE_RADIUS_M, ball_owners, process_ball_trajectory

    total, examples = Counter(), {}
    for hall, venue_dir, match, touches_path in args.fragment:
        venue = ball_settings(load_venue(Path(venue_dir)), None)
        state, attack = _fragment_state(venue, Path(match))
        ball = process_ball_trajectory(schemas.read(Path(match) / 'detections.parquet', 'detections'), venue)
        owners = ball_owners(ball, state)
        runs = owner_runs(owners, state)
        all_events = extract_events(ball, state, venue.length_m, venue.width_m, attack, skip_stoppages=False)
        spans = stoppages(state, venue.length_m, venue.width_m, ball)
        passes = [e for e in extract_events(ball, state, venue.length_m, venue.width_m, attack) if e['kind'] == 'pass']
        players = state.filter(pl.col('team').is_in(['A', 'B']))
        b_ts, b_x, b_y, b_int = (ball[c].to_numpy() for c in ('ts', 'x_m', 'y_m', 'interpolated'))
        rows = pl.read_parquet(touches_path).sort('ts').to_dicts()
        cats = Counter()
        for a, b in zip(rows, rows[1:]):
            if a['event'] not in ('A', 'B') or b['event'] not in ('A', 'B'):
                continue
            tr, passer, receiver = b['ts'], a['event'], b['event']
            if any(p['team'] == passer and abs(p['end_s'] - tr) <= PASS_TOL_S for p in passes):
                cats['найдена'] += 1
                continue
            near_ball = np.abs(b_ts - tr) <= MISS_WINDOW_S
            run = min((r for r in runs if abs(r['ts_start'] - tr) <= PASS_TOL_S), key=lambda r: abs(r['ts_start'] - tr), default=None)
            covering = next((r for r in runs if r['ts_start'] - PASS_TOL_S <= tr <= r['ts_end'] + PASS_TOL_S), None)
            if not near_ball.any():
                why = 'мяча нет'
            elif b_int[near_ball].all():
                why = 'мяч только дорисован'
            elif not _player_close(players, b_ts[near_ball], b_x[near_ball], b_y[near_ball], TAKE_RADIUS_M):
                why = 'мяч далеко от игроков'
            elif run is None and covering is not None:
                why = 'владелец не сменился (держит прежний)'
            elif run is None:
                later = min((r['ts_start'] - tr for r in runs if r['ts_start'] > tr), default=np.inf)
                why = 'владелец назначен позже на 1–3 с' if later <= 3 else 'мяч ничей дольше 3 с'
            else:
                i = runs.index(run)
                prev = runs[i - 1] if i else None
                kinds = {e['kind'] for e in all_events if prev and e['kind'] in ('shot', 'duel') and abs(e['start_s'] - prev['ts_end']) < 0.05}
                if prev is None:
                    why = 'нет предыдущего владельца'
                elif run['team'] != receiver:
                    why = 'принял игрок другой команды'
                elif prev['team'] != passer:
                    why = 'отдал игрок другой команды'
                elif run['ts_start'] - prev['ts_end'] > MAX_PASS_FLIGHT_S:
                    why = f'пауза владения > {MAX_PASS_FLIGHT_S:.0f} с'
                elif 'shot' in kinds:
                    why = 'засчитано ударом'
                elif 'duel' in kinds:
                    why = 'засчитано единоборством'
                elif any(s <= run['ts_start'] <= e or s <= prev['ts_end'] <= e for s, e in spans):
                    why = 'выпала внутри остановки'
                else:
                    why = 'другое'
            cats[why] += 1
            examples.setdefault(why, []).append(f'{Path(match).name} {tr:.1f} с')
        print(f'== {hall} · {Path(match).name}: передач {sum(cats.values())}')
        for k, v in cats.most_common():
            print(f'  {k:>40}: {v}')
        total += cats
    print('== итого')
    for k, v in total.most_common():
        sample = ', '.join(examples.get(k, [])[:3])
        print(f'  {k:>40}: {v}' + (f'   (например {sample})' if sample else ''))


def _player_close(players: pl.DataFrame, ts: np.ndarray, x: np.ndarray, y: np.ndarray, radius: float) -> bool:
    for t, bx, by in zip(ts, x, y):
        fr = players.filter((pl.col('ts') - t).abs() < 0.021)
        if len(fr) and np.hypot(fr['x_m'].to_numpy() - bx, fr['y_m'].to_numpy() - by).min() <= radius:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('frames')
    p.add_argument('--weights', action='append', required=True, metavar='NAME=PATH')
    p.add_argument('--hall', nargs=4, action='append', required=True, metavar=('NAME', 'VENUE', 'VIDEO', 'BALL_LABELS'))
    p = sub.add_parser('select')
    p.add_argument('--hall', nargs=5, action='append', required=True, metavar=('NAME', 'VENUE', 'BALL_LABELS', 'MATCH', 'CANDIDATES'))
    p = sub.add_parser('passes')
    p.add_argument('--fragment', nargs=5, action='append', required=True, metavar=('HALL', 'VENUE', 'MATCH', 'TOUCHES', 'CANDIDATES'))
    p = sub.add_parser('missed')
    p.add_argument('--fragment', nargs=4, action='append', required=True, metavar=('HALL', 'VENUE', 'MATCH', 'TOUCHES'))
    args = parser.parse_args()
    {'frames': cmd_frames, 'select': cmd_select, 'passes': cmd_passes, 'missed': cmd_missed}[args.cmd](args)


if __name__ == '__main__':
    main()
