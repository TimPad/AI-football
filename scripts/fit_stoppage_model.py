"""Обучение посекундного классификатора остановок (analytics.stoppage_model) по журналам касаний. Сеть не нужна.

    .venv/bin/python scripts/fit_stoppage_model.py --train MATCH TOUCHES VENUE [--train ...] [--test MATCH TOUCHES VENUE ...]

MATCH — каталог артефактов CV (state.parquet, detections.parquet) со своей моделью мяча; TOUCHES — журнал
tools.label_touches; VENUE — каталог установки. Признаки считаются тем же кодом, что в пайплайне (Витерби, траектория
мяча). Печатает блок WITH_BALL / NO_BALL для stoppage_model.py и точность на --test: фрагменты другого зала, которые
в обучение не входили. Логистическая регрессия: признаки стандартизованы, классы уравновешены, L2 = 1.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl
from scipy.optimize import minimize

from aifootball.analytics import stoppage_model as sm
from aifootball.analytics.events import viterbi_stoppages
from aifootball.perception.ball import process_ball_trajectory
from aifootball.processor.job import ball_settings
from aifootball.understanding.per_second import reference_seconds, score_seconds, stoppage_interval_recall, dead_intervals
from aifootball.venue import load_venue

L2 = 1.0


def fragment(match: Path, touches: Path, venue_dir: Path):
    venue = load_venue(venue_dir)
    venue = ball_settings(venue, venue.frame_width or 0)
    state = pl.read_parquet(match / 'state.parquet')
    det = pl.read_parquet(match / 'detections.parquet')
    ball = process_ball_trajectory(det.filter((pl.col('cls') != 'ball') | (pl.col('conf') >= venue.conf_ball)), venue)
    log = pl.read_parquet(touches).select('ts', 'event').to_dicts()
    last = max(t['ts'] for t in log)
    reference, _ = reference_seconds(log, start_s=0.0, end_s=float('inf'))
    reference = {s: v for s, v in reference.items() if s + 1 <= last}
    viterbi = viterbi_stoppages(state, venue.length_m, venue.width_m)
    feats = {'with_ball': sm.second_features(state, ball, venue.length_m, venue.width_m, viterbi),
             'no_ball': sm.second_features(state, None, venue.length_m, venue.width_m, viterbi)}
    return {'name': match.name, 'reference': reference, 'features': feats, 'viterbi': viterbi, 'dead': dead_intervals(log)}


def fit(X: np.ndarray, y: np.ndarray, names) -> dict:
    mean, std = X.mean(0), X.std(0) + 1e-9
    Z = np.column_stack([(X - mean) / std, np.ones(len(X))])
    weight = np.where(y == 1, len(y) / (2 * y.sum()), len(y) / (2 * (1 - y).sum()))

    def loss(w):
        p = 1 / (1 + np.exp(-(Z @ w)))
        ll = -(weight * (y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12))).sum()
        return ll + L2 * (w[:-1] ** 2).sum(), Z.T @ (weight * (p - y)) + 2 * L2 * np.append(w[:-1], 0)
    w = minimize(loss, np.zeros(Z.shape[1]), jac=True, method='L-BFGS-B').x
    r = lambda v: [round(float(x), 4) for x in v]
    return {'features': tuple(names), 'mean': r(mean), 'std': r(std), 'weights': r(w[:-1]), 'bias': round(float(w[-1]), 4)}


def matrix(fragments, key, names):
    idx = [sm.FEATURES.index(n) for n in names]
    rows = [(f['features'][key][s], f['reference'][s]) for f in fragments for s in f['reference'] if s in f['features'][key]]
    return np.array([[r[i] for i in idx] for r, _ in rows]), np.array([v == 'stoppage' for _, v in rows], float)


def report(fragments, models):
    reference = {(f['name'], s): v for f in fragments for s, v in f['reference'].items()}
    methods = {'Витерби': {}, 'классификатор': {}, 'классификатор без мяча': {}}
    found = {m: [0, 0] for m in methods}
    for f in fragments:
        cover = lambda s: sum(max(0.0, min(b, s + 1) - max(a, s)) for a, b in f['viterbi']) >= 0.5
        per = {'Витерби': {s: 'stoppage' if cover(s) else 'playing' for s in f['reference']}}
        for label, key, model in (('классификатор', 'with_ball', models['WITH_BALL']), ('классификатор без мяча', 'no_ball', models['NO_BALL'])):
            prob = sm.stoppage_probability(f['features'][key], model)
            per[label] = {s: 'stoppage' if prob.get(s, 0.0) >= sm.THRESHOLD else 'playing' for s in f['reference']}
        for m, pred in per.items():
            methods[m].update({(f['name'], s): v for s, v in pred.items()})
            hit = stoppage_interval_recall(f['dead'], pred)
            found[m][0] += hit['found']; found[m][1] += hit['intervals']
    for m, pred in methods.items():
        s = score_seconds(reference, pred)
        print(f"  {m:>24}: верно {s['accuracy']:.2f}  P {s['stoppage_precision'] or 0:.2f}  R {s['stoppage_recall']:.2f}  "
              f"сбаланс {s['balanced_accuracy']:.2f}; остановок {found[m][0]}/{found[m][1]} ({s['labelled']} с)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--train', nargs=3, action='append', type=Path, required=True, metavar=('MATCH', 'TOUCHES', 'VENUE'))
    parser.add_argument('--test', nargs=3, action='append', type=Path, default=[], metavar=('MATCH', 'TOUCHES', 'VENUE'))
    args = parser.parse_args()
    train = [fragment(*a) for a in args.train]
    models = {}
    for name, key, names in (('WITH_BALL', 'with_ball', sm.FEATURES), ('NO_BALL', 'no_ball', sm.NO_BALL['features'])):
        X, y = matrix(train, key, names)
        models[name] = fit(X, y, names)
        print(f'{name}: обучение на {len(y)} с, остановка {int(y.sum())}')
    print('--- блок для stoppage_model.py ---')
    for name, model in models.items():
        print(f'{name} = {json.dumps(model, ensure_ascii=False)}'.replace('[', '(', 1).replace('], "mean"', '), "mean"'))
    print('обучение (в выборке):')
    report(train, models)
    if args.test:
        print('проверка (в обучение не входило):')
        report([fragment(*a) for a in args.test], models)


if __name__ == '__main__':
    main()
