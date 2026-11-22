"""Точность передач по ручным журналам: находимость, точность команды и что стоит за неточными. Отчёт —
docs/2026-11-22-pass-accuracy.md.

    .venv/bin/python scripts/eval_pass_accuracy.py --fragment NAME VENUE MATCH TOUCHES [...] [--verbose]

Передачи обработчика — как в задании (analytics.events.extract_events, с фильтром остановок) по готовым прогонам.
Передача журнала и обработчика совпадают, если команда отдающего та же и приём в ±1 с (как в
scripts/eval_ball_multivenue.py). Итоги — по залам: первое слово NAME группирует отрезки.

- точность: доля точных среди передач журнала и среди передач обработчика, и расхождение в п.п.;
- красные (неточные у обработчика): верные — в журнале тоже неточная, ложные — в журнале точная,
  лишние — в журнале передачи нет;
- неточные журнала: найдены неточными, найдены точными, срезаны фильтром остановок, ушли в единоборство
  или не найдены совсем.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import eval_ownership as O  # noqa: E402

from aifootball.analytics import events as EV  # noqa: E402
from aifootball.analytics.validation import truth_from_touches  # noqa: E402

TOL_S = 1.0


def pairs(truth: list[dict], pred: list[dict], tol: float = TOL_S) -> list[tuple[int, int]]:
    """Сопоставление передач журнала и обработчика: та же команда, приём в ±tol с; ближайшие пары первыми."""
    candidates = sorted(
        (abs(p['end_s'] - t['ts_receive']), i, j)
        for i, t in enumerate(truth)
        for j, p in enumerate(pred)
        if p['team'] == t['team'] and abs(p['end_s'] - t['ts_receive']) <= tol
    )
    used_truth, used_pred, out = set(), set(), []
    for _, i, j in candidates:
        if i not in used_truth and j not in used_pred:
            used_truth.add(i)
            used_pred.add(j)
            out.append((i, j))
    return out


def score(truth: list[dict], pred: list[dict]) -> dict:
    """Счётчики одного отрезка: передачи, точные, красные по видам."""
    matched = pairs(truth, pred)
    by_pred = {j: i for i, j in matched}
    reds = [j for j, p in enumerate(pred) if p['success'] is False]
    return {
        'truth': len(truth),
        'pred': len(pred),
        'hit': len(matched),
        'truth_ok': sum(1 for t in truth if t['completed']),
        'pred_ok': sum(1 for p in pred if p['success']),
        'red': len(reds),
        'red_true': sum(1 for j in reds if j in by_pred and not truth[by_pred[j]]['completed']),
        'red_false': sum(1 for j in reds if j in by_pred and truth[by_pred[j]]['completed']),
        'red_extra': sum(1 for j in reds if j not in by_pred),
    }


def missed_failures(truth: list[dict], kept: list[dict], raw: list[dict], tol: float = TOL_S) -> Counter:
    """Что обработчик сделал с неточными передачами журнала (kept — с фильтром остановок, raw — без него)."""
    out = Counter()
    for t in truth:
        if t['completed']:
            continue
        near = lambda events, kind: [
            e for e in events if e['kind'] == kind and abs(e.get('end_s', e['start_s']) - t['ts_receive']) <= tol
        ]
        found = [e for e in near(kept, 'pass') if e['team'] == t['team']]
        cut = [e for e in near(raw, 'pass') if e['team'] == t['team']]
        if found:
            out['найдена точной' if found[0]['success'] else 'найдена неточной'] += 1
        elif cut:
            out['срезана фильтром остановок'] += 1
        elif near(raw, 'duel'):
            out['единоборство'] += 1
        else:
            out['не найдена'] += 1
    return out


def evaluate(fragment: dict, verbose: bool = False) -> tuple[dict, Counter]:
    args = (fragment['ball'], fragment['state'], fragment['venue'].length_m, fragment['venue'].width_m)
    inside = lambda e: fragment['t0'] <= e['start_s'] <= fragment['t1'] + 1
    kept = [e for e in EV.extract_events(*args, fragment['attack']) if inside(e)]
    raw = [e for e in EV.extract_events(*args, fragment['attack'], skip_stoppages=False) if inside(e)]
    truth = truth_from_touches(fragment['touches'])[1]
    pred = [e for e in kept if e['kind'] == 'pass']
    counts = score(truth, pred)
    if verbose:
        by_pred = {j: i for i, j in pairs(truth, pred)}
        for j, p in enumerate(pred):
            if p['success'] is False:
                t = truth[by_pred[j]] if j in by_pred else None
                kind = 'лишняя' if t is None else 'верная' if not t['completed'] else 'ложная'
                print(f'  {fragment["name"]:>12} красная {kind:6} {p["start_s"]:7.2f} → {p["end_s"]:7.2f} с')
    return counts, missed_failures(truth, kept, raw)


def f1(hit: int, n_truth: int, n_pred: int) -> float:
    recall, precision = hit / max(1, n_truth), hit / max(1, n_pred)
    return 2 * recall * precision / max(1e-9, recall + precision)


def report(results: list[tuple[str, dict, Counter]]) -> None:
    halls: dict[str, tuple[Counter, Counter]] = {}
    for name, counts, missed in results:
        total, lost = halls.setdefault(name.split()[0], (Counter(), Counter()))
        total.update(counts)
        lost.update(missed)
    for hall, (c, lost) in halls.items():
        journal = 100 * c['truth_ok'] / max(1, c['truth'])
        found = 100 * c['pred_ok'] / max(1, c['pred'])
        print(
            f'{hall}: передачи R {c["hit"]}/{c["truth"]} P {c["hit"]}/{c["pred"]} F1 {f1(c["hit"], c["truth"], c["pred"]):.2f} | '
            f'точность журнал {journal:.0f}%, обработчик {found:.0f}% (Δ {found - journal:+.0f} п.п.) | '
            f'красных {c["red"]}: верных {c["red_true"]}, ложных {c["red_false"]}, лишних {c["red_extra"]}'
        )
        print(f'  неточные журнала ({sum(lost.values())}): ' + ', '.join(f'{k} {v}' for k, v in lost.most_common()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--fragment',
        nargs=4,
        action='append',
        required=True,
        metavar=('NAME', 'VENUE', 'MATCH', 'TOUCHES'),
        help='NAME — «зал время»: первое слово группирует отрезки по залам',
    )
    parser.add_argument('--verbose', action='store_true', help='каждая красная передача')
    args = parser.parse_args()
    results = []
    for name, venue, match, touches in args.fragment:
        fragment = O.load_fragment(name, venue, match, touches)
        counts, missed = evaluate(fragment, args.verbose)
        results.append((name, counts, missed))
    report(results)


if __name__ == '__main__':
    main()
