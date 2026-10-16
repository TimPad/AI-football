"""Оценка кандидатов стандартных положений по ручной разметке касаний (локальные данные, вне Git).

python scripts/eval_restart_candidates.py
"""
import json
from pathlib import Path
import polars as pl
from aifootball.processor.candidates import evaluate, restart_candidates

FRAGMENTS = [
    ('yaroslavl-60-240', 'output/analysis-acceptance/processor-cd7da23d0e7e4ab78c4bc2e9c195e193', 'data/gt/yaroslavl-60-240/touches.parquet'),
    ('yaroslavl-600-780', 'data/matches/yaroslavl-600-780-v2', 'data/gt/yaroslavl-600-780/touches.parquet'),
]
SETTINGS = {'строгий': {'max_speed': 1.0, 'min_duration_s': 1.5}, 'мягкий': {'max_speed': 1.5, 'min_duration_s': 1.0}}


def restart_team(touches: pl.DataFrame, dead_s: float) -> str | None:
    after = touches.filter((pl.col('ts') > dead_s) & pl.col('event').is_in(['A', 'B'])).sort('ts')
    return after['event'][0] if after.height else None


def main():
    totals = {name: {'candidates': 0, 'true_positive': 0, 'dead': 0, 'found': 0, 'team_same': 0, 'team_checked': 0} for name in SETTINGS}
    for fragment, folder, gt in FRAGMENTS:
        if not Path(gt).exists():
            print(f'{fragment}: нет разметки {gt}'); continue
        state = pl.read_parquet(Path(folder) / 'state.parquet')
        pitch = json.loads((Path(folder) / 'metrics.json').read_text())['pitch']
        touches = pl.read_parquet(gt)
        dead = touches.filter(pl.col('event') == 'dead')['ts'].to_list()
        for name, params in SETTINGS.items():
            found = restart_candidates(state, pitch['length_m'], pitch['width_m'], **params)
            score = evaluate(found, dead)
            # Команда, вводящая мяч, — та, чьё касание первое после остановки.
            for c in found:
                d = next((d for d in sorted(dead) if d - 1 <= c['start_s'] <= d + 7), None)
                team = restart_team(touches, d) if d is not None else None
                if team:
                    totals[name]['team_checked'] += 1; totals[name]['team_same'] += team == c['team']
            for key in ('candidates', 'true_positive', 'dead', 'found'):
                totals[name][key] += score[key]
            print(f"{fragment} · {name}: точность {score['true_positive']}/{score['candidates']}, полнота {score['found']}/{score['dead']}")
    for name, t in totals.items():
        print(f"ИТОГО · {name}: точность {t['true_positive']}/{t['candidates']}, полнота {t['found']}/{t['dead']}, "
              f"команда совпала {t['team_same']}/{t['team_checked']}")


if __name__ == '__main__':
    main()
