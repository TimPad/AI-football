"""Замер склейки треков в игроков по разметке обрывов (data/gt/<фрагмент>/links.json).

Разметка: конец трека -> трек, который продолжает того же человека; null — продолжения среди
кандидатов нет; "?" — не уверен, в замер не входит. Состояние берётся из data/matches/<фрагмент>-v2.
Запуск: .venv/bin/python scripts/eval_identity.py
"""
import json
from pathlib import Path

import polars as pl
import yaml

from aifootball.analytics.track_groups import link_tracks, track_ends

FRAGMENTS = {'yaroslavl-60-240': 'data/matches/yaroslavl-60-240-v2', 'yaroslavl-600-780': 'data/matches/yaroslavl-600-780-v2'}


def score(predicted: dict[int, int], truth: dict[str, int | None | str]) -> dict:
    tp = fp = fn = 0
    errors = []
    for end, expected in truth.items():
        if expected == '?':
            continue
        got = predicted.get(int(end))
        if expected is None:
            if got is not None:
                fp += 1; errors.append((int(end), got, None))
        elif got == expected:
            tp += 1
        else:
            fn += 1
            if got is not None:
                fp += 1; errors.append((int(end), got, expected))
    return {'links': tp + fn, 'found': tp, 'false': fp, 'precision': round(tp / max(1, tp + fp), 2),
            'recall': round(tp / max(1, tp + fn), 2), 'errors': errors}


def main():
    for name, root in FRAGMENTS.items():
        truth = json.loads(Path(f'data/gt/{name}/links.json').read_text())['links']
        meta = json.loads(Path(root, 'meta.json').read_text())
        width = yaml.safe_load(Path('configs/venues', meta['venue_id'], 'venue.yaml').read_text())['pitch']['width_m']
        links = link_tracks(track_ends(pl.read_parquet(Path(root, 'state.parquet'))), width)
        print(name, score({a: b for a, (b, _) in links.items()}, truth))


if __name__ == '__main__':
    main()
