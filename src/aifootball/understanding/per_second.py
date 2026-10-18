"""Посекундная оценка «мяч в игре / вне игры» по ручному журналу касаний. Без API, БД и моделей.

Журнал tools.label_touches: A/B — мяч получил игрок команды, dead — мяч вне игры до следующего
касания A/B. Секунда [s, s+1) эталона — «игра», если не пересекает остановку, и «остановка», если
целиком внутри неё. Смешанные секунды не оцениваются: граница известна с точностью нажатия клавиши.
"""
import math

import polars as pl

from aifootball.understanding.evaluate import _match

SHOT_KINDS = {'shot_candidate', 'save_candidate', 'goal_candidate'}
# Мяч не в игре и в перерыве, и до/после матча; unknown — отказ от ответа.
OUT_OF_PLAY = {'stoppage', 'break', 'pre_match', 'post_match'}
LABELS = ('playing', 'stoppage')


def dead_intervals(touches) -> list[tuple[float, float]]:
    """Остановки [dead, следующее касание A/B), слитые; остановка без размеченного конца отброшена."""
    log = sorted(touches, key=lambda t: t['ts'])
    merged = []
    for i, mark in enumerate(log):
        if mark['event'] != 'dead':
            continue
        end = next((t['ts'] for t in log[i + 1:] if t['event'] != 'dead'), None)
        if end is None:
            continue
        if merged and mark['ts'] <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((mark['ts'], end))
    return merged


def reference_seconds(touches, *, start_s: float, end_s: float) -> tuple[dict[int, str], int]:
    """Чистые секунды эталона внутри [start_s, end_s) и размеченного журнала; второе — число смешанных."""
    log = sorted(touches, key=lambda t: t['ts'])
    if not log:
        return {}, 0
    dead = dead_intervals(log)
    labels, mixed = {}, 0
    for s in range(math.ceil(max(start_s, log[0]['ts'])), math.floor(min(end_s, log[-1]['ts']))):
        overlap = sum(max(0.0, min(b, s + 1) - max(a, s)) for a, b in dead)
        if overlap == 0:
            labels[s] = 'playing'
        elif overlap >= 1 - 1e-9:
            labels[s] = 'stoppage'
        else:
            mixed += 1
    return labels, mixed


def predicted_seconds(states, seconds) -> dict[int, str]:
    """Состояние секунды — известное состояние, покрывающее большую часть секунды, не меньше 0,5 с."""
    result = {}
    for s in seconds:
        cover = dict.fromkeys(LABELS, 0)
        for state in states:
            label = 'playing' if state['kind'] == 'playing' else 'stoppage' if state['kind'] in OUT_OF_PLAY else None
            if label:
                cover[label] += max(0, min((s + 1) * 1000, state['end_ms']) - max(s * 1000, state['start_ms']))
        label = max(LABELS, key=cover.get)
        result[s] = label if cover[label] >= 500 else 'unknown'
    return result


def wilson(k: int, n: int, z: float = 1.96):
    if not n:
        return None
    p = k / n
    centre, half = p + z * z / (2 * n), z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    # При k=0 или k=n граница аналитически ровно 0 или 1; float даёт ±1e-17.
    low = 0.0 if k == 0 else (centre - half) / (1 + z * z / n)
    high = 1.0 if k == n else (centre + half) / (1 + z * z / n)
    return low, high


def _ratio(a, b):
    return a / b if b else None


def score_seconds(reference: dict[int, str], predicted: dict[int, str]) -> dict:
    """unknown снижает покрытие и считается промахом в accuracy; accuracy_covered — только по ответам."""
    if set(reference) - set(predicted):
        raise ValueError('Нет предсказания для части размеченных секунд')
    confusion = {t: {p: 0 for p in (*LABELS, 'unknown')} for t in LABELS}
    for s, truth in reference.items():
        confusion[truth][predicted[s] if predicted[s] in LABELS else 'unknown'] += 1
    n = len(reference)
    covered = n - sum(row['unknown'] for row in confusion.values())
    hits = {t: confusion[t][t] for t in LABELS}
    totals = {t: sum(confusion[t].values()) for t in LABELS}
    correct = sum(hits.values())
    recall = {t: _ratio(hits[t], totals[t]) for t in LABELS}
    return {'labelled': n, 'covered': covered, 'correct': correct, 'coverage': _ratio(covered, n),
            'accuracy': _ratio(correct, n), 'accuracy_covered': _ratio(correct, covered),
            # Та же точность у правила «всегда игра» на отвеченных секундах: ниже неё ответы бесполезны.
            'always_playing_covered': _ratio(covered - sum(confusion['stoppage'][t] for t in LABELS), covered),
            'stoppage_precision': _ratio(hits['stoppage'], hits['stoppage'] + confusion['playing']['stoppage']),
            'stoppage_recall': recall['stoppage'], 'playing_recall': recall['playing'],
            'balanced_accuracy': None if None in recall.values() else (recall['playing'] + recall['stoppage']) / 2,
            'accuracy_ci': wilson(correct, n), 'stoppage_recall_ci': wilson(hits['stoppage'], totals['stoppage']),
            'confusion': confusion}


def stoppage_interval_recall(intervals, predicted: dict[int, str]) -> dict:
    """Сколько остановок с оценёнными секундами получили хотя бы одну секунду «остановка»."""
    scored = found = 0
    for a, b in intervals:
        inside = [s for s in predicted if a <= s and s + 1 <= b]
        if inside:
            scored += 1
            found += any(predicted[s] == 'stoppage' for s in inside)
    return {'intervals': scored, 'found': found}


def match_shots(shots, events, *, tolerance_ms: int = 1500) -> dict:
    """Удар найден, если кандидат удара/сейва/гола не дальше tolerance_ms от размеченного момента."""
    predicted = [e for e in events if e['kind'] in SHOT_KINDS]
    truth = [round(s['ts'] * 1000) for s in shots]
    pairs = _match(predicted, truth, lambda e, t: max(0, e['start_ms'] - t, t - e['end_ms']), tolerance_ms)
    sure = {j for j, s in enumerate(shots) if s.get('certainty') == 'sure'}
    return {'labelled': len(shots), 'labelled_sure': len(sure), 'predicted': len(predicted),
            'matched': len(pairs), 'matched_sure': sum(j in sure for _, j in pairs)}


def _known(values, reference):
    return [(-values[s], reference[s] == 'stoppage') for s in reference if values.get(s) is not None]


def auc(values: dict[int, float], reference: dict[int, str]) -> float | None:
    """AUC признака «чем меньше значение, тем вероятнее остановка»; ничьи — пополам."""
    pairs = _known(values, reference)
    pos = [v for v, stop in pairs if stop]
    neg = [v for v, stop in pairs if not stop]
    if not pos or not neg:
        return None
    return sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))


def fit_threshold(values: dict[int, float], reference: dict[int, str]) -> float:
    """Порог правила «остановка, если значение < порога» с наибольшей сбалансированной точностью."""
    known = sorted({values[s] for s in reference if values.get(s) is not None})
    candidates = [(a + b) / 2 for a, b in zip(known, known[1:])] + [known[-1] + 1e-6]

    def balanced(threshold):
        predicted = {s: 'unknown' if values.get(s) is None else 'stoppage' if values[s] < threshold else 'playing'
                     for s in reference}
        return score_seconds(reference, predicted)['balanced_accuracy'] or 0.0
    return max(candidates, key=balanced)


def player_speed_seconds(state: pl.DataFrame, seconds, *, q: float = 0.8, window_s: float = 3.0) -> dict:
    """Квантиль скорости полевых игроков в окне window_s с центром в середине секунды."""
    players = state.filter((pl.col('role') == 'player') & pl.col('speed').is_finite()).select('ts', 'speed')
    result = {}
    for s in seconds:
        centre = s + 0.5
        part = players.filter((pl.col('ts') >= centre - window_s / 2) & (pl.col('ts') < centre + window_s / 2))
        result[s] = None if part.is_empty() else float(part['speed'].quantile(q, interpolation='nearest'))
    return result


def ball_visible_seconds(ball: pl.DataFrame, frames: pl.DataFrame, seconds) -> dict:
    """Доля обработанных кадров секунды, где мяч найден детектором, а не интерполирован."""
    seen = ball.filter(~pl.col('interpolated'))
    result = {}
    for s in seconds:
        total = frames.filter((pl.col('ts') >= s) & (pl.col('ts') < s + 1)).height
        hits = seen.filter((pl.col('ts') >= s) & (pl.col('ts') < s + 1)).height
        result[s] = hits / total if total else None
    return result
