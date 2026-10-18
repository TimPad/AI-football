"""Сравнение VLM-вариантов на общих секундах, где ответили все, с парным тестом Макнемара. Сеть не используется.

    .venv/bin/python scripts/compare_vlm_common_seconds.py --manifest M.json

Manifest — тот же, что у eval_vlm_per_second.py. Скорость CV оценивается с порогом другого фрагмента.
"""
import argparse
from itertools import combinations
import json
from math import comb
from pathlib import Path

from eval_vlm_per_second import in_span, load_fragment, run_cases
from aifootball.understanding.per_second import fit_threshold, predicted_seconds, score_seconds


def mcnemar(a_right, b_right):
    """Точный двусторонний тест по секундам, где прав ровно один из методов."""
    only_a = sum(x and not y for x, y in zip(a_right, b_right))
    only_b = sum(y and not x for x, y in zip(a_right, b_right))
    n, k = only_a + only_b, min(only_a, only_b)
    p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
    return only_a, only_b, p


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--manifest', type=Path, required=True)
    manifest = json.loads(parser.parse_args().manifest.read_text())
    span = tuple(manifest['vlm_span_s'])
    fragments = {f['id']: load_fragment(f) for f in manifest['fragments']}
    reference, predictions = {}, {}
    for fid, f in fragments.items():
        reference.update({(fid, s): v for s, v in in_span(f['reference'], span).items()})
        others = [g for g in fragments.values() if g['id'] != fid]
        threshold = fit_threshold({(g['id'], s): v for g in others for s, v in g['speed'].items()},
                                  {(g['id'], s): v for g in others for s, v in g['reference'].items()})
        predictions.setdefault('cv_speed', {}).update(
            {(fid, s): 'unknown' if v is None else 'stoppage' if v < threshold else 'playing' for s, v in f['speed'].items()})
    for run in manifest['runs']:
        for fid, states, _, _ in run_cases(run, fragments):
            seconds = [s for f_id, s in reference if f_id == fid]
            predictions.setdefault(run['name'], {}).update(
                {(fid, s): v for s, v in predicted_seconds(states, seconds).items()})
    names = [r['name'] for r in manifest['runs']]
    common = [k for k in reference if all(predictions[n].get(k, 'unknown') != 'unknown' for n in names)]
    print(f'Общих секунд с ответом всех VLM-вариантов: {len(common)} из {len(reference)} '
          f'(остановка {sum(reference[k] == "stoppage" for k in common)})')
    subset = {k: reference[k] for k in common}
    methods = ['always_playing', 'cv_speed', *names]
    predictions['always_playing'] = dict.fromkeys(reference, 'playing')
    for name in methods:
        s = score_seconds(subset, {k: predictions[name][k] for k in common})
        print(f"  {name:>15}: верно {s['correct']}/{s['labelled']} ({s['accuracy']:.2f}), остановки P "
              f"{s['stoppage_precision'] or 0:.2f} R {s['stoppage_recall']:.2f}, сбаланс {s['balanced_accuracy']:.2f}")
    print('Все секунды: VLM, а где ответа нет — скорость CV (без доплаты):')
    for name in names:
        merged = {k: predictions[name].get(k, 'unknown') if predictions[name].get(k, 'unknown') != 'unknown'
                  else predictions['cv_speed'][k] for k in reference}
        s = score_seconds(reference, merged)
        print(f"  {name + '+cv':>15}: верно {s['correct']}/{s['labelled']} ({s['accuracy']:.2f}), остановки P "
              f"{s['stoppage_precision'] or 0:.2f} R {s['stoppage_recall']:.2f}, сбаланс {s['balanced_accuracy']:.2f}")
    print('Парные сравнения: секунды, где прав только первый / только второй, p; затем то же по 12-с окнам')
    right = {n: [predictions[n][k] == reference[k] for k in common] for n in methods}
    windows = sorted({(fid, s // 12) for fid, s in common})
    for a, b in combinations(methods[1:], 2):
        only_a, only_b, p = mcnemar(right[a], right[b])
        # Секунды одного окна зависимы; знаковый тест по окнам осторожнее.
        per = [(sum(predictions[a][k] == reference[k] for k in common if (k[0], k[1] // 12) == w),
                sum(predictions[b][k] == reference[k] for k in common if (k[0], k[1] // 12) == w)) for w in windows]
        wins_a, wins_b, pw = mcnemar([x > y for x, y in per], [y > x for x, y in per])
        print(f'  {a} vs {b}: {only_a} / {only_b}, p={p:.3f}; окна {wins_a} / {wins_b} из {len(per)}, p={pw:.3f}')


if __name__ == '__main__':
    main()
