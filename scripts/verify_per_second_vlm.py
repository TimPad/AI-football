"""Opt-in посекундный VLM-эксперимент: dry-run по умолчанию; фиксированный бюджет, без автоповторов.

    .venv/bin/python scripts/verify_per_second_vlm.py --manifest M.json --output DIR --env-file .env [--apply|--cache-only]

Manifest (локальный, вне Git): cases: [{id, video, cv, venue, start_ms, end_ms}] — cv: артефакты CV этой
записи со своей моделью мяча. Варианты: fullframe — весь кадр; follow — половина кадра, плавно следующая
за мячом из CV (без мяча — за игроками); follow_cv — то же и посекундные подсказки CV. Разметка в запросы
не попадает. Отчёт каждого
варианта — DIR/<вариант>/report.json в формате, который читает scripts/eval_vlm_per_second.py.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import time

from dotenv import dotenv_values
import numpy as np
import polars as pl

from aifootball.analytics.exchange import canonical
from aifootball.geometry.polygons import points_near_polygon
from aifootball.perception.ball import process_ball_trajectory
from aifootball.processor.budget import Budget
from aifootball.processor.job import ball_settings, file_hash, video_info
from aifootball.processor.media import make_window
from aifootball.processor.qwen import QwenClient, QwenConfig
from aifootball.processor.workspace import Workspace
from aifootball.understanding.per_second_pilot import (VERSION, cv_hints, follow_keys, per_second_prompt, project_per_second,
                                                       window_seconds)
from aifootball.understanding.pilot import OUTPUT_LIMIT, PilotStopped, joint_window, paid_once, request_key
from aifootball.venue import load_venue
from verify_context_vlm import pack_window, unpack_window

VARIANTS = ('fullframe', 'follow', 'follow_cv')
# Одобрено пользователем 18.10: до ~120 вызовов и ~1,5 CNY; план — 3 варианта × 30 окон.
LIMITS = {'max_requests': 90, 'max_input_tokens': 1_200_000, 'max_output_tokens': 120_000}
WINDOW_MS = 12000
CV_FILES = ('tracks.parquet', 'state.parquet', 'detections.parquet', 'meta.json')


def load_case(case):
    video, cv = Path(case['video']), Path(case['cv'])
    meta = json.loads((cv / 'meta.json').read_text())
    if not meta.get('ball_model'):
        raise ValueError(f"{case['id']}: CV без своей модели мяча")
    info = video_info(video)
    venue = load_venue(Path(case['venue']))
    venue = ball_settings(venue, venue.frame_width or info['width'])
    detections = pl.read_parquet(cv / 'detections.parquet')
    balls = detections.filter((pl.col('cls') == 'ball') & (pl.col('conf') >= venue.conf_ball))
    floor = np.column_stack([((balls['x1'] + balls['x2']) / 2).to_numpy(), balls['y2'].to_numpy()])
    balls = balls.filter(pl.Series(points_near_polygon(floor, venue.require_polygon(), venue.ball_margin_px)))
    return {**case, 'info': info, 'venue': venue, 'tracks': pl.read_parquet(cv / 'tracks.parquet'),
            'state': pl.read_parquet(cv / 'state.parquet'), 'ball_boxes': balls,
            'frames': detections.select('frame_id', 'ts').unique('frame_id'),
            'ball': process_ball_trajectory(detections.filter((pl.col('cls') != 'ball') | (pl.col('conf') >= venue.conf_ball)), venue)}


def window_follow(case, begin, end):
    span = (pl.col('ts') >= begin / 1000 - 1) & (pl.col('ts') < end / 1000 + 1)
    # Один мяч на кадр — самый уверенный, как в process_ball_trajectory.
    balls = case['ball_boxes'].filter(span).sort('conf', descending=True).unique('frame_id', keep='first')
    players = case['tracks'].filter(span & (pl.col('role') == 'player') & pl.col('in_pitch'))
    centre = lambda df: df.select('ts', ((pl.col('x1') + pl.col('x2')) / 2), ((pl.col('y1') + pl.col('y2')) / 2)).to_numpy()
    return follow_keys(centre(balls), centre(players), start_s=begin / 1000, duration_s=(end - begin) / 1000,
                       frame_w=case['info']['width'], frame_h=case['info']['height'])


def media_preparer():
    """(case, begin, end, variant, output) -> (window, crop, hints); видео и CV читаются один раз и лениво."""
    loaded, clips = {}, {}

    def prepare(case, begin, end, variant, output):
        if case['id'] not in loaded:
            loaded[case['id']] = load_case(case)
        c = loaded[case['id']]
        kind = 'full' if variant == 'fullframe' else 'follow'
        crop = None if kind == 'full' else window_follow(c, begin, end)
        key = (case['id'], begin, end, kind)
        if key not in clips:
            folder = output / 'media' / case['id'] / f'{begin}-{end}' / kind
            clips[key] = joint_window(make_window(Path(case['video']), start_ms=begin, end_ms=end, out=folder,
                                                  mode='native', fps=1, crop=crop))
        window = clips[key]
        hints = None if variant != 'follow_cv' else cv_hints(
            c['state'], c['ball'], c['frames'], start_ms=window.start_ms, seconds=window_seconds(window.end_ms - window.start_ms),
            length_m=c['venue'].length_m, width_m=c['venue'].width_m)
        return window, crop, hints
    return prepare


def identity(cases, client):
    return {'purpose': VERSION, 'preparation': 'per-second-follow-v1', 'variants': VARIANTS, 'limits': LIMITS,
            'provider': {'model': client.config.model, 'endpoint': client.config.base_url},
            'cases': [{'id': c['id'], 'source_sha256': file_hash(Path(c['video'])), 'start_ms': c['start_ms'],
                       'end_ms': c['end_ms'], 'cv': {n: file_hash(Path(c['cv']) / n) for n in CV_FILES}} for c in cases]}


def run(manifest, output, *, apply=False, cache_only=False, client=None, prepare=None):
    if apply and cache_only:
        raise ValueError('conflicting modes')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    client = client or QwenClient(QwenConfig.from_env())
    prepare = prepare or media_preparer()
    cases = manifest['cases']
    fingerprint = identity(cases, client)
    planned = sum(-(-(c['end_ms'] - c['start_ms']) // WINDOW_MS) for c in cases) * len(VARIANTS)
    if planned > LIMITS['max_requests']:
        raise ValueError(f'plan needs {planned} requests, limit {LIMITS["max_requests"]}')
    workspace = Workspace(output / 'work', fingerprint)
    budget = Budget(workspace, **LIMITS)
    before, started = budget.snapshot(), time.monotonic()
    mode = 'apply' if apply else 'cache_only' if cache_only else 'dry_run'
    reports = {v: {'version': VERSION, 'variant': v, 'mode': mode, 'cases': []} for v in VARIANTS}
    for case, ident in zip(cases, fingerprint['cases']):
        rows = {v: [] for v in VARIANTS}
        for v in VARIANTS:
            reports[v]['cases'].append({'id': case['id'], 'source_sha256': ident['source_sha256'], 'windows': rows[v]})
        for begin in range(case['start_ms'], case['end_ms'], WINDOW_MS):
            end = min(begin + WINDOW_MS, case['end_ms'])
            for variant in VARIANTS:
                plan_key = 'plan:' + sha256(canonical([ident['source_sha256'], begin, end, variant, VERSION])).hexdigest()
                plan = workspace.get_json(plan_key)
                if plan is None:
                    window, crop, hints = prepare(case, begin, end, variant, output)
                    prompt = per_second_prompt(window.end_ms - window.start_ms, hints=hints)
                    plan = {'window': pack_window(window), 'crop': crop, 'prompt': prompt,
                            'request_key': request_key(client, window, prompt, OUTPUT_LIMIT)}
                    if apply:
                        workspace.put_json(plan_key, plan)
                else:
                    window = unpack_window(plan['window'])
                if request_key(client, window, plan['prompt'], OUTPUT_LIMIT) != plan['request_key']:
                    raise ValueError('frozen request mismatch')
                row = {'start_ms': window.start_ms, 'end_ms': window.end_ms, 'crop': plan['crop'],
                       'clip': str(window.media.path), 'request_key': plan['request_key'],
                       'prompt_sha256': sha256(plan['prompt'].encode()).hexdigest(), 'prompt_bytes': len(plan['prompt'].encode())}
                if mode == 'dry_run':
                    row['status'] = 'dry_run'
                else:
                    try:
                        received = paid_once(client, window, plan['prompt'], workspace, budget, allow_network=apply)
                    except PilotStopped as exc:
                        row.update(status='unavailable', reason=str(exc))
                    else:
                        row.update(received)
                        try:
                            projected, repairs = project_per_second(received['document'], window.end_ms - window.start_ms)
                        except (ValueError, KeyError, TypeError):
                            row['status'] = 'invalid_response'
                        else:
                            row.update(status='valid', projected_document=projected, local_repairs=repairs)
                rows[variant].append(row)
                after = budget.snapshot()
                for report in reports.values():
                    report.update(budget=after, new_requests_this_run=after['requests'] - before['requests'],
                                  wall_s=round(time.monotonic() - started, 3), sports_accuracy_validated=False)
                folder = output / variant
                folder.mkdir(exist_ok=True)
                (folder / 'report.json').write_text(json.dumps(reports[variant], ensure_ascii=False, indent=2))
                usage = row.get('usage') or {}
                print(json.dumps({'variant': variant, 'case': case['id'], 'start_ms': window.start_ms, 'status': row['status'],
                                  'cache_hit': row.get('cache_hit'), 'follow': plan['crop'] is not None, 'prompt_bytes': row['prompt_bytes'],
                                  'in': usage.get('prompt_tokens'), 'out': usage.get('completion_tokens'),
                                  'requests': after['requests']}, ensure_ascii=False), flush=True)
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--env-file', type=Path, help='локальный .env с DASHSCOPE_API_KEY и DASHSCOPE_BASE_URL')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--apply', action='store_true')
    group.add_argument('--cache-only', action='store_true')
    args = parser.parse_args()
    if args.env_file:
        os.environ.update({k: v for k, v in dotenv_values(args.env_file).items() if k.startswith('DASHSCOPE_') and v})
    try:
        reports = run(json.loads(args.manifest.read_text()), args.output, apply=args.apply, cache_only=args.cache_only)
    except (ValueError, OSError) as exc:
        # Ответы провайдера сюда не попадают: paid_once превращает их в код PilotStopped внутри run.
        parser.exit(2, f'Per-second pilot stopped: {str(exc)[:200]}; no automatic retry.\n')
    first = next(iter(reports.values()))
    print(json.dumps({'budget': first['budget'], 'new_requests_this_run': first['new_requests_this_run']}), flush=True)
    if any(w['status'] not in ('valid', 'dry_run') for r in reports.values() for c in r['cases'] for w in c['windows']):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
