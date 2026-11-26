"""Сборка фрагментов в людей по внешности для сопоставления с составом.

Склейка по движению (track_groups) собирает цепочки, пока игрок в кадре; камера трансляции теряет игроков каждые
несколько секунд, и цепочки короткие (ВШЭ, 15.11.2026: 924 кандидата примерно на 24 человека). Здесь цепочки и
одиночные фрагменты собираются в людей по признакам внешности. Средняя связь: похожесть двух людей — средняя
похожесть их единиц; на каждом шаге объединяются два самых похожих совместимых человека. Несовместимы люди разных
команд и люди, видимые одновременно дольше OVERLAP_S; запреты складываются при объединении. Порог похожести и
порог сомнения подбираются замером (scripts/eval_people.py, спецификация 2026-11-23-people-identity-design).
"""

from dataclasses import dataclass, field

import numpy as np

from aifootball.analytics.track_groups import OVERLAP_S

# Человек короче — в «Неразобранные»: обрывок без своего человека.
MIN_PERSON_S = 20.0
SUGGESTIONS = 3


@dataclass(frozen=True)
class Unit:
    """Цепочка склейки по движению или одиночный фрагмент; feature — нормированный признак или None (нет кадров)."""

    track_ids: tuple[int, ...]
    team: str
    intervals: tuple[tuple[float, float], ...]
    feature: np.ndarray | None = field(default=None, compare=False)

    @property
    def seconds(self) -> float:
        return float(sum(b - a for a, b in self.intervals))

    @property
    def start(self) -> float:
        return min(a for a, _ in self.intervals)


@dataclass
class Person:
    key: str
    team: str
    track_ids: list[int]
    scores: list[float]  # похожесть фрагмента на остальные единицы своего человека
    doubtful: list[int]  # фрагменты, почти так же похожие на другого совместимого человека
    seconds: float


@dataclass
class People:
    persons: list[Person]
    unsorted: list[dict]  # {'track_id', 'suggestions': [{'key', 'score'}]}


def mean_feature(vectors, weights=None) -> np.ndarray | None:
    """Нормированное среднее признаков (веса — время или площадь); без признаков — None."""
    if not len(vectors):
        return None
    w = weights if weights is not None and sum(weights) > 0 else None
    m = np.average(np.stack(vectors), axis=0, weights=w)
    n = float(np.linalg.norm(m))
    return m / n if n > 0 else None


def max_overlap(a, b) -> float:
    """Самое долгое одновременное появление: наибольшее пересечение интервалов (≤ 0 — не пересекаются)."""
    return max((min(a1, b1) - max(a0, b0) for a0, a1 in a for b0, b1 in b), default=0.0)


def conflicts(units: list[Unit]) -> np.ndarray:
    """Матрица запретов: разные команды или одновременная видимость дольше OVERLAP_S; диагональ — запрет."""
    n = len(units)
    out = np.eye(n, dtype=bool)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = units[i], units[j]
            if a.team != b.team or max_overlap(a.intervals, b.intervals) > OVERLAP_S:
                out[i, j] = out[j, i] = True
    return out


def cluster(units: list[Unit], threshold: float, blocked: np.ndarray) -> list[list[int]]:
    """Индексы единиц по людям. Единица без признака остаётся одна."""
    idx = [i for i, u in enumerate(units) if u.feature is not None]
    groups = {k: [i] for k, i in enumerate(idx)}
    if len(idx) > 1:
        x = np.stack([units[i].feature for i in idx])
        sums = x @ x.T  # суммы похожести пар единиц между людьми
        sizes = np.ones(len(idx))
        block = blocked[np.ix_(idx, idx)].copy()
        while True:
            avg = np.where(block, -np.inf, sums / np.outer(sizes, sizes))
            i, j = np.unravel_index(int(np.argmax(avg)), avg.shape)
            if not np.isfinite(avg[i, j]) or avg[i, j] < threshold:
                break
            r = sums[i] + sums[j]
            diag = r[i] + r[j]
            sums[i, :] = r
            sums[:, i] = r
            sums[i, i] = diag
            sizes[i] += sizes[j]
            block[i, :] |= block[j, :]
            block[:, i] |= block[:, j]
            block[j, :] = True
            block[:, j] = True
            groups[i] += groups.pop(j)
    return list(groups.values()) + [[i] for i, u in enumerate(units) if u.feature is None]


def assemble(units: list[Unit], threshold: float, margin: float, min_person_s: float = MIN_PERSON_S) -> People:
    """Люди с ключами A1…/B1… по убыванию времени на площадке, сомнительные фрагменты и неразобранные."""
    blocked = conflicts(units)
    groups = cluster(units, threshold, blocked)

    def seconds(g):
        return sum(units[i].seconds for i in g)

    def kept(g):
        return all(units[i].feature is not None for i in g) and seconds(g) >= min_person_s

    def sim(i, members):
        others = [m for m in members if m != i]
        if units[i].feature is None or not others:
            return None
        return float(np.mean([units[i].feature @ units[m].feature for m in others]))

    def fits(i, members):
        return not any(blocked[i, m] for m in members if m != i)

    keyed = []
    for team in sorted({units[g[0]].team for g in groups if kept(g)}):
        ranked = sorted(
            (g for g in groups if kept(g) and units[g[0]].team == team),
            key=lambda g: (-seconds(g), min(units[i].start for i in g)),
        )
        keyed += [(f'{team}{n}', sorted(g, key=lambda i: units[i].start)) for n, g in enumerate(ranked, 1)]
    persons = []
    for key, g in keyed:
        track_ids, scores, doubtful = [], [], []
        for i in g:
            own = sim(i, g)
            own = 1.0 if own is None else own
            others = [s for k, h in keyed if k != key and fits(i, h) and (s := sim(i, h)) is not None]
            for t in units[i].track_ids:
                track_ids.append(t)
                scores.append(round(own, 3))
                if others and own - max(others) < margin:
                    doubtful.append(t)
        persons.append(Person(key, units[g[0]].team, track_ids, scores, doubtful, round(seconds(g), 2)))
    unsorted = []
    for i in sorted((i for g in groups if not kept(g) for i in g), key=lambda i: units[i].start):
        options = sorted(
            ((s, k) for k, h in keyed if fits(i, h) and (s := sim(i, h)) is not None),
            key=lambda o: (-o[0], o[1]),
        )[:SUGGESTIONS]
        for t in units[i].track_ids:
            unsorted.append({'track_id': t, 'suggestions': [{'key': k, 'score': round(s, 3)} for s, k in options]})
    return People(persons, unsorted)


def units_from_index(index: dict, features: dict[int, np.ndarray]) -> list[Unit]:
    """Единицы из индекса треков пакета: цепочки groups и одиночные фрагменты игроков и вратарей с командой.
    Признак единицы — среднее признаков её фрагментов с весом по времени на площадке."""
    tracks = {
        t['track_id']: t for t in index['tracks'] if t['team'] in ('A', 'B') and t['role'] in ('player', 'goalkeeper')
    }
    chains = [[t for t in g['track_ids'] if t in tracks] for g in index.get('groups', [])]
    chains = [c for c in chains if c]
    grouped = {t for c in chains for t in c}
    chains += [[t] for t in sorted(tracks) if t not in grouped]
    units = []
    for chain in chains:
        intervals = tuple((float(a), float(b)) for t in chain for a, b in tracks[t]['intervals'])
        have = [t for t in chain if t in features]
        weights = [sum(b - a for a, b in tracks[t]['intervals']) for t in have]
        units.append(
            Unit(tuple(chain), tracks[chain[0]]['team'], intervals, mean_feature([features[t] for t in have], weights))
        )
    return sorted(units, key=lambda u: (u.start, u.track_ids))
