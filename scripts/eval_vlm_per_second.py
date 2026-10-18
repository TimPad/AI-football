"""Посекундная переоценка уже оплаченных VLM-ответов и бесплатных базовых правил. Сеть не используется.

    .venv/bin/python scripts/eval_vlm_per_second.py --manifest M.json --output DIR

Manifest (локальный, вне Git):
  vlm_span_s: [начало, конец] — общий интервал, на котором сравниваются VLM-прогоны;
  fragments: [{id, sources: [sha256], video, touches, shots, cv, venue}] — cv: каталог артефактов
    с state.parquet/detections.parquet/meta.json, обработанный своей моделью мяча;
  runs: [{name, kind: understanding_zip|pilot_report, path, fragment?}] — fragment обязателен для zip.
Эталон — журнал касаний (tools.label_touches); удары — shots.parquet. Метки в запросы не попадали.
"""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile

import polars as pl

from aifootball.perception.ball import process_ball_trajectory
from aifootball.processor.job import ball_settings, video_info
from aifootball.understanding.per_second import (auc, ball_visible_seconds, dead_intervals, fit_threshold, match_shots,
                                                 player_speed_seconds, predicted_seconds, reference_seconds,
                                                 score_seconds, stoppage_interval_recall)
from aifootball.venue import load_venue

SYMBOL = {'playing': 'И', 'stoppage': 'О', 'unknown': '·'}


def load_fragment(item):
    touches = pl.read_parquet(item['touches']).select('ts', 'event').to_dicts()
    shots = pl.read_parquet(item['shots']).to_dicts() if item.get('shots') else []
    cv = Path(item['cv'])
    meta = json.loads((cv / 'meta.json').read_text())
    if not meta.get('ball_model'):
        raise ValueError(f"{item['id']}: CV без своей модели мяча")
    venue = load_venue(Path(item['venue']))
    venue = ball_settings(venue, venue.frame_width or video_info(Path(item['video']))['width'])
    detections = pl.read_parquet(cv / 'detections.parquet')
    frames = detections.select('frame_id', 'ts').unique('frame_id')
    ball = process_ball_trajectory(detections.filter((pl.col('cls') != 'ball') | (pl.col('conf') >= venue.conf_ball)), venue)
    reference, mixed = reference_seconds(touches, start_s=0.0, end_s=float('inf'))
    state = pl.read_parquet(cv / 'state.parquet')
    return {'id': item['id'], 'sources': set(item['sources']), 'touches': touches, 'shots': shots,
            'dead': dead_intervals(touches), 'reference': reference, 'mixed': mixed, 'ball_model': meta['ball_model'],
            'speed': player_speed_seconds(state, reference), 'ball': ball_visible_seconds(ball, frames, reference)}


def run_cases(run, fragments):
    """(fragment_id, абсолютные states, абсолютные events, окна) для каждого кейса прогона."""
    if run['kind'] == 'understanding_zip':
        with ZipFile(run['path']) as z:
            doc = json.loads(z.read('understanding.json'))
        fragment = fragments[run['fragment']]
        if doc['source']['sha256'] not in fragment['sources']:
            raise ValueError(f"{run['name']}: другой исходник")
        windows = [{'start_ms': a, 'end_ms': b, 'status': 'covered'} for a, b in doc['coverage']['covered_intervals']]
        yield fragment['id'], doc['states'], doc['events'], windows
        return
    report = json.loads(Path(run['path']).read_text())
    for case in report['cases']:
        if case['id'] not in fragments:
            continue
        if case['source_sha256'] not in fragments[case['id']]['sources']:
            raise ValueError(f"{run['name']}/{case['id']}: другой исходник")
        states, events, windows = [], [], []
        for w in case['windows']:
            # v1: локальная проекция с журналом правок; v2: только строго принятые ответы.
            valid = w.get('projection_status') == 'valid' if 'projection_status' in w else w['status'] == 'valid'
            windows.append({'start_ms': w['start_ms'], 'end_ms': w['end_ms'], 'status': w['status'], 'used': valid})
            if not valid:
                continue
            doc = w['projected_document']
            shift = lambda item: {**item, 'start_ms': w['start_ms'] + item['start_ms'], 'end_ms': w['start_ms'] + item['end_ms']}
            states += [shift(s) for s in doc['states']]
            events += [shift(e) for e in doc['events']]
        yield case['id'], states, events, windows


def in_span(reference, span):
    return {s: v for s, v in reference.items() if span[0] <= s and s + 1 <= span[1]}


def timeline(reference, predicted, span):
    seconds = range(int(span[0]), int(span[1]) + 1)
    ref = ''.join(SYMBOL[reference[s]] if s in reference else ' ' for s in seconds)
    pred = ''.join(SYMBOL[predicted[s]] if s in predicted else ' ' for s in seconds)
    return ref, pred


def keyed(fragment_id, values):
    return {(fragment_id, s): v for s, v in values.items()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    span = tuple(manifest['vlm_span_s'])
    fragments = {f['id']: load_fragment(f) for f in manifest['fragments']}
    report = {'version': 'per-second-eval-v1', 'network_requests': 0, 'vlm_span_s': span, 'fragments': {}, 'methods': {}}
    methods = {}  # имя -> {'full'|'span': (reference, predicted) по ключам (fragment, s)}

    def add(name, scope, fragment_id, reference, predicted):
        # Итог по всем фрагментам и отдельно по каждому: v0 есть только для одного фрагмента.
        for key in (scope, f'{scope}/{fragment_id}'):
            ref, pred = methods.setdefault(name, {}).setdefault(key, ({}, {}))
            ref.update(keyed(fragment_id, reference))
            pred.update(keyed(fragment_id, {s: predicted[s] for s in reference}))

    for fid, f in fragments.items():
        full, short = f['reference'], in_span(f['reference'], span)
        report['fragments'][fid] = {
            'ball_model': f['ball_model'], 'labelled_seconds': len(full), 'mixed_seconds': f['mixed'],
            'stoppage_seconds': sum(v == 'stoppage' for v in full.values()), 'dead_intervals': f['dead'],
            'span_labelled_seconds': len(short), 'span_stoppage_seconds': sum(v == 'stoppage' for v in short.values()),
            'shots': f['shots'],
            'cv_auc_in_sample': {'player_speed_p80': auc(f['speed'], full), 'ball_visible_share': auc(f['ball'], full)},
            'timelines': {'reference': timeline(short, short, span)[0]}}
        for scope, reference in (('full', full), ('span', short)):
            add('always_playing', scope, fid, reference, dict.fromkeys(reference, 'playing'))
    # Порог скорости подбирается на другом фрагменте: честный перенос, а не подгонка под оцениваемый.
    for fid, f in fragments.items():
        others = [g for g in fragments.values() if g['id'] != fid]
        if not others:
            continue
        train_ref = {(g['id'], s): v for g in others for s, v in g['reference'].items()}
        train_speed = {(g['id'], s): v for g in others for s, v in g['speed'].items()}
        threshold = fit_threshold(train_speed, train_ref)
        predicted = {s: 'unknown' if v is None else 'stoppage' if v < threshold else 'playing' for s, v in f['speed'].items()}
        report['fragments'][fid]['cv_speed_threshold_from_other'] = threshold
        short = in_span(f['reference'], span)
        report['fragments'][fid]['timelines']['cv_speed'] = timeline(short, {s: predicted[s] for s in short}, span)[1]
        for scope, reference in (('full', f['reference']), ('span', short)):
            add('cv_speed_transfer', scope, fid, reference, predicted)
    runs = {}
    for run in manifest['runs']:
        for fid, states, events, windows in run_cases(run, fragments):
            f = fragments[fid]
            reference = in_span(f['reference'], span)
            predicted = predicted_seconds(states, reference)
            add(run['name'], 'span', fid, reference, predicted)
            shots = [s for s in f['shots'] if span[0] <= s['ts'] < span[1]]
            # Кандидаты вне интервала сравнения не должны снижать точность ударов.
            events = [e for e in events if span[0] * 1000 <= e['start_ms'] < span[1] * 1000]
            interval = stoppage_interval_recall(f['dead'], predicted)
            runs.setdefault(run['name'], {})[fid] = {
                'windows': windows, 'score': score_seconds(reference, predicted), 'dead_intervals': interval,
                'shots': match_shots(shots, events), 'events': [(e['kind'], e['start_ms'], e['end_ms']) for e in events]}
            report['fragments'][fid]['timelines'][run['name']] = timeline(reference, predicted, span)[1]
    report['runs'] = runs
    for name, scopes in methods.items():
        report['methods'][name] = {scope: score_seconds(ref, pred) for scope, (ref, pred) in scopes.items()}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=list))
    print_summary(report)


def fmt(value):
    return '—' if value is None else f'{value:.2f}'


def print_summary(report):
    print(f"Интервал сравнения VLM: {report['vlm_span_s'][0]}–{report['vlm_span_s'][1]} с; новых запросов: 0")
    for fid, f in report['fragments'].items():
        print(f"\n{fid}: эталон {f['labelled_seconds']} с (остановка {f['stoppage_seconds']}), смешанных {f['mixed_seconds']}; "
              f"в интервале VLM {f['span_labelled_seconds']} с (остановка {f['span_stoppage_seconds']}); "
              f"AUC скорости {fmt(f['cv_auc_in_sample']['player_speed_p80'])}, мяча {fmt(f['cv_auc_in_sample']['ball_visible_share'])}; "
              f"порог с другого фрагмента {fmt(f.get('cv_speed_threshold_from_other'))} м/с")
        for name, line in f['timelines'].items():
            print(f'  {name:>18} |{line}|')
    print('\nМетод / объём: секунд, покрытие, верно из всех, верно из ответов (у «всегда игра» на них же), '
          'остановки P/R, сбаланс.')
    for name, scopes in report['methods'].items():
        for scope, s in scopes.items():
            print(f"  {name:>18} {scope:>4}: {s['labelled']:3d} с, покр {fmt(s['coverage'])}, верно {fmt(s['accuracy'])}, "
                  f"из ответов {fmt(s['accuracy_covered'])} ({fmt(s['always_playing_covered'])}), "
                  f"остановки P {fmt(s['stoppage_precision'])} "
                  f"R {fmt(s['stoppage_recall'])}, сбаланс {fmt(s['balanced_accuracy'])}")
    for name, cases in report['runs'].items():
        for fid, r in cases.items():
            print(f"  {name}/{fid}: остановок найдено {r['dead_intervals']['found']}/{r['dead_intervals']['intervals']}, "
                  f"удары {r['shots']['matched']}/{r['shots']['labelled']} (кандидатов {r['shots']['predicted']}), "
                  f"события {r['events']}")


if __name__ == '__main__':
    main()
