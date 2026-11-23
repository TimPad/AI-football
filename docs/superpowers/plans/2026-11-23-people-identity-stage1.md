# Люди вместо фрагментов — этап 1: сборка людей и замер

> **Выполнен 23.11.2026:** ворота не пройдены ([замер](../../2026-11-23-people-clustering.md)). Код в плане — как
> он был задуман; рабочие версии — в `src/` и `scripts/`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** собрать фрагменты матча ВШЭ в людей по внешности и замерить точность склеек; пройти или не пройти ворота
спецификации (точность ≥ 0,95, людей ≤ 20 на команду, «Неразобранные» ≤ 15% времени).

**Architecture:** модуль сборки `analytics/people.py` не зависит от модели признаков: средняя связь с запретом
одновременных. Кадры фрагментов — `perception/person_crops.py` (выбор рамок по `tracks.parquet`, вырезка по метке
времени через `FrameReader`). Признаки — `perception/appearance.py` (цвет без модели, DINOv2 ViT-S/14 с
регистрами и SigLIP 2 ViT-B/16 через timm).
Замер — `scripts/eval_people.py`: кадры, признаки, сборка с перебором порога, листы пар для разметки глазами,
оценка. Пакет результата, сервис и экран «Люди» — во втором плане, после ворот.

**Tech Stack:** Python 3.12, numpy, polars, OpenCV, torch (уже в зависимостях через ultralytics), timm
(необязательная группа `people`) для DINOv2 с регистрами и SigLIP 2; pytest, ruff. Модели выбраны по навыку
cv-model-selection (таблица лицензий — Task 3).

Спецификация: `docs/superpowers/specs/2026-11-23-people-identity-design.md`.

Данные ВШЭ (не в Git): артефакты `/Users/timofeynikulin/AI-football/data/processing/hse-2026-11-15/work/artifacts`,
установка `.../work/venue`, видео `/Users/timofeynikulin/AI-football/data/raw/hse_futsal_456239351_16596-19200.mp4`,
пакет с индексом треков — последний загруженный прогон:
`/Users/timofeynikulin/AI-football/data/service/attachments/analysis/92e661fe-7bb6-4d3b-9e06-79c05d24ae23-788414d6920ee90d.zip`.
Папка замера `data/people/hse` (в worktree `data/` игнорируется): в ней кадры участников, в Git не попадает.

---

## Файлы

- Create `src/aifootball/analytics/people.py` — единицы, запреты, сборка, ключи, уверенность, неразобранные.
- Create `src/aifootball/perception/person_crops.py` — выбор кадров фрагмента и вырезка из видео.
- Create `src/aifootball/perception/appearance.py` — признак цвета и DINOv2.
- Create `scripts/eval_people.py` — шаги замера.
- Create `tests/test_people.py`, `tests/test_person_crops.py`, `tests/test_appearance.py`, `tests/test_eval_people.py`.
- Create `docs/<дата замера>-people-clustering.md`; Modify `docs/README.md` (строка индекса).

---

### Task 1: Сборка людей (`analytics/people.py`)

**Files:**
- Create: `src/aifootball/analytics/people.py`
- Test: `tests/test_people.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Сборка фрагментов в людей по внешности: запрет одновременных, порог, ключи, сомнительные, неразобранные."""

import numpy as np
import pytest

from aifootball.analytics.people import Unit, assemble, cluster, conflicts, max_overlap, units_from_index


def v(*xs):
    a = np.array(xs, float)
    return a / np.linalg.norm(a)


def unit(tids, team, start, end, feature):
    return Unit(tuple(tids), team, ((float(start), float(end)),), feature)


def groups_of(units, threshold):
    return sorted(sorted(g) for g in cluster(units, threshold, conflicts(units)))


def test_max_overlap_is_the_longest_shared_interval():
    assert max_overlap(((0, 10),), ((9.5, 20),)) == pytest.approx(0.5)
    assert max_overlap(((0, 10), (30, 40)), ((35, 50),)) == pytest.approx(5)
    assert max_overlap(((0, 10),), ((11, 20),)) <= 0


def test_simultaneous_or_other_team_units_never_merge():
    same_time = [unit([1], 'A', 0, 30, v(1, 0)), unit([2], 'A', 10, 40, v(1, 0))]
    other_team = [unit([1], 'A', 0, 10, v(1, 0)), unit([2], 'B', 20, 30, v(1, 0))]
    assert groups_of(same_time, 0.5) == [[0], [1]]
    assert groups_of(other_team, 0.5) == [[0], [1]]


def test_merging_stops_at_threshold_and_blocks_add_up():
    # 0 и 1 склеиваются первыми; 2 похож на обоих, но виден одновременно с 1 — к их человеку не присоединяется.
    units = [
        unit([1], 'A', 0, 10, v(1, 0)),
        unit([2], 'A', 20, 30, v(1, 0.05)),
        unit([3], 'A', 25, 35, v(1, 0.1)),
        unit([4], 'A', 50, 60, v(0, 1)),
    ]
    assert groups_of(units, 0.9) == [[0, 1], [2], [3]]


def test_units_without_features_stay_alone():
    units = [unit([1], 'A', 0, 10, None), unit([2], 'A', 20, 30, v(1, 0)), unit([3], 'A', 40, 50, v(1, 0))]
    assert groups_of(units, 0.5) == [[0], [1, 2]]


def test_people_keys_doubtful_and_unsorted():
    units = [
        unit([1], 'A', 0, 40, v(1, 0, 0)),
        Unit((2, 3), 'A', ((50.0, 75.0), (75.0, 100.0)), v(1, 0.1, 0)),  # цепочка по движению
        unit([4], 'A', 0, 30, v(0, 1, 0)),  # второй человек, виден вместе с первым
        unit([5], 'A', 120, 125, v(0.7, 0.7, 0)),  # между ними: склеится с первым, но сомнительно
        unit([6], 'A', 200, 203, None),  # без кадров
        unit([7], 'A', 300, 310, v(0, 0, 1)),  # один, 10 с — короче человека
    ]
    people = assemble(units, threshold=0.6, margin=0.1)
    assert [(p.key, p.track_ids) for p in people.persons] == [('A1', [1, 2, 3, 5]), ('A2', [4])]
    first = people.persons[0]
    assert first.doubtful == [5] and first.seconds == pytest.approx(95)
    assert first.scores[0] == pytest.approx(0.851, abs=1e-3)  # среднее похожести на 2–3 и 5
    assert people.persons[1].scores == [1.0]  # единственная единица человека
    assert [u['track_id'] for u in people.unsorted] == [6, 7]
    assert people.unsorted[0]['suggestions'] == []
    assert [s['key'] for s in people.unsorted[1]['suggestions']] == ['A1', 'A2']


def test_units_follow_motion_chains_and_weight_features_by_time():
    index = {
        'tracks': [
            {'track_id': 1, 'team': 'A', 'role': 'player', 'intervals': [[0, 10]]},
            {'track_id': 2, 'team': 'A', 'role': 'player', 'intervals': [[11, 30]]},
            {'track_id': 3, 'team': 'B', 'role': 'goalkeeper', 'intervals': [[0, 5]]},
            {'track_id': 4, 'team': None, 'role': 'referee', 'intervals': [[0, 50]]},
        ],
        'groups': [{'track_ids': [1, 2], 'links': []}],
    }
    units = units_from_index(index, {1: v(1, 0), 2: v(0, 1)})
    assert [(u.track_ids, u.team) for u in units] == [((1, 2), 'A'), ((3,), 'B')]
    assert units[0].feature == pytest.approx(v(10, 19))
    assert units[1].feature is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_people.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aifootball.analytics.people'`

- [ ] **Step 3: Write the implementation**

```python
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
        t['track_id']: t
        for t in index['tracks']
        if t['team'] in ('A', 'B') and t['role'] in ('player', 'goalkeeper')
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
        units.append(Unit(tuple(chain), tracks[chain[0]]['team'], intervals, mean_feature([features[t] for t in have], weights)))
    return sorted(units, key=lambda u: (u.start, u.track_ids))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_people.py -q`
Expected: `6 passed`

- [ ] **Step 5: Format, lint, commit**

```bash
.venv/bin/ruff format src/aifootball/analytics/people.py tests/test_people.py
.venv/bin/ruff check src/aifootball/analytics/people.py tests/test_people.py
git add src/aifootball/analytics/people.py tests/test_people.py
git commit -m "feat(analytics): assemble fragments into people with a no-simultaneity constraint"
```

---

### Task 2: Кадры фрагментов (`perception/person_crops.py`)

**Files:**
- Create: `src/aifootball/perception/person_crops.py`
- Test: `tests/test_person_crops.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Кадры фрагмента для признаков внешности: крупные, целые, без чужих рамок поверх, не у края кадра."""

import numpy as np
import polars as pl

from aifootball import schemas
from aifootball.perception.person_crops import CANDIDATES, KEEP, extract_crops, pick_frames
from conftest import write_video


def row(frame_id, track_id, box, ts=None, role='player', in_pitch=True):
    x1, y1, x2, y2 = box
    return {
        'frame_id': frame_id,
        'ts': frame_id * 0.1 if ts is None else ts,
        'cls': 'person',
        'x1': x1,
        'y1': y1,
        'x2': x2,
        'y2': y2,
        'conf': 0.9,
        'torso_l': None,
        'torso_a': None,
        'torso_b': None,
        'track_id': track_id,
        'foot_x': (x1 + x2) / 2,
        'foot_y': y2,
        'in_pitch': in_pitch,
        'role': role,
        'team': 'A',
    }


def tracks(rows):
    return pl.DataFrame(rows).cast(schemas.TRACKS)


def test_frames_skip_small_edge_covered_and_off_pitch_boxes():
    rows = [row(k, 1, (100, 50, 140, 150)) for k in range(60)]  # 6 с, рамка 100 px
    rows.append(row(5, 2, (102, 52, 142, 152)))  # кадр 5: чужая рамка поверх первой
    rows += [row(k, 3, (200, 100, 220, 140)) for k in range(30)]  # 40 px — мелко
    rows += [row(k, 4, (2, 50, 40, 150)) for k in range(30)]  # у края кадра
    rows += [row(k, 5, (250, 50, 290, 150), role='referee') for k in range(30)]
    rows += [row(k, 6, (300, 50, 340, 150), in_pitch=False) for k in range(30)]
    picks = pick_frames(tracks(rows), (400, 300))
    assert set(picks) == {1}
    ts = sorted(p['ts'] for p in picks[1])
    assert len(ts) <= CANDIDATES and all(b - a >= 1.0 - 1e-9 for a, b in zip(ts, ts[1:]))
    assert all(p['frame_id'] != 5 for p in picks[1])


def test_frames_respect_registration_and_broadcast_graphics():
    rows = [row(k, 1, (100, 50, 140, 150)) for k in range(60)]
    picks = pick_frames(tracks(rows), (400, 300), usable_frames={10, 30})
    assert sorted(p['frame_id'] for p in picks[1]) == [10, 30]
    # центр рамки (120, 100) внутри графики трансляции (доли кадра) — кадров нет
    assert pick_frames(tracks(rows), (400, 300), overlay=((0.2, 0.2, 0.5, 0.5),)) == {}


def test_crops_are_cut_from_the_video_by_timestamp(tmp_path):
    video = write_video(tmp_path / 'clip.mp4', n_frames=40, fps=10, size=(400, 300))
    picks = {1: [{'ts': t, 'frame_id': int(t * 10), 'box': [100, 50, 140, 150]} for t in (0.5, 1.5, 2.5)]}
    crops = extract_crops(video, picks)
    assert len(crops[1]) == min(KEEP, 3)
    assert all(c.shape == (100, 40, 3) for c in crops[1])
    assert isinstance(crops[1][0], np.ndarray)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_person_crops.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aifootball.perception.person_crops'`

- [ ] **Step 3: Write the implementation**

```python
"""Кадры фрагмента для признаков внешности.

Годная рамка: игрок или вратарь на площадке, высота не меньше MIN_H_PX, не ближе EDGE_PX к краю кадра, чужие рамки
того же кадра закрывают меньше MAX_COVER её площади, кадр привязан к полю (у поворотной камеры) и центр рамки не на
графике трансляции. Из годных берутся CANDIDATES самых крупных с шагом не меньше MIN_GAP_S; после вырезки остаются
KEEP самых резких (дисперсия лапласиана не ниже медианы фрагмента). Рамки tracks — в пикселях своего кадра и у
поворотной камеры тоже, кадр ищется по метке времени (FrameReader).
"""

from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
import polars as pl

MIN_H_PX = 60
EDGE_PX = 8
MAX_COVER = 0.1
MIN_GAP_S = 1.0
CANDIDATES = 8
KEEP = 5


def _covered(tracks: pl.DataFrame) -> pl.DataFrame:
    """cover — доля рамки, закрытая самой большой чужой рамкой того же кадра."""
    boxes = tracks.select('frame_id', 'track_id', 'x1', 'y1', 'x2', 'y2')
    pairs = boxes.join(boxes, on='frame_id', suffix='_o').filter(pl.col('track_id') != pl.col('track_id_o'))
    iw = (pl.min_horizontal('x2', 'x2_o') - pl.max_horizontal('x1', 'x1_o')).clip(lower_bound=0)
    ih = (pl.min_horizontal('y2', 'y2_o') - pl.max_horizontal('y1', 'y1_o')).clip(lower_bound=0)
    area = (pl.col('x2') - pl.col('x1')) * (pl.col('y2') - pl.col('y1'))
    cover = pairs.with_columns(cover=iw * ih / area).group_by('frame_id', 'track_id').agg(pl.col('cover').max())
    return tracks.join(cover, on=['frame_id', 'track_id'], how='left').with_columns(pl.col('cover').fill_null(0.0))


def pick_frames(
    tracks: pl.DataFrame, frame_size: tuple[int, int], usable_frames=None, overlay=()
) -> dict[int, list[dict]]:
    """{трек: [{ts, frame_id, box}]} — до CANDIDATES годных рамок, самые крупные с шагом MIN_GAP_S."""
    w, h = frame_size
    t = tracks.filter(pl.col('in_pitch') & pl.col('role').is_in(['player', 'goalkeeper']))
    if usable_frames is not None:
        t = t.filter(pl.col('frame_id').is_in(list(usable_frames)))
    for x1, y1, x2, y2 in overlay:
        cx, cy = (pl.col('x1') + pl.col('x2')) / 2 / w, (pl.col('y1') + pl.col('y2')) / 2 / h
        t = t.filter(~(cx.is_between(x1, x2) & cy.is_between(y1, y2)))
    t = _covered(t).filter(
        (pl.col('y2') - pl.col('y1') >= MIN_H_PX)
        & (pl.col('x1') >= EDGE_PX)
        & (pl.col('y1') >= EDGE_PX)
        & (pl.col('x2') <= w - EDGE_PX)
        & (pl.col('y2') <= h - EDGE_PX)
        & (pl.col('cover') < MAX_COVER)
    )
    out = {}
    ranked = t.with_columns(height=pl.col('y2') - pl.col('y1')).sort(['track_id', 'height', 'ts'], descending=[False, True, False])
    for (tid,), g in ranked.group_by('track_id', maintain_order=True):
        chosen = []
        for r in g.iter_rows(named=True):
            if all(abs(r['ts'] - c['ts']) >= MIN_GAP_S for c in chosen):
                chosen.append({'ts': r['ts'], 'frame_id': r['frame_id'], 'box': [r['x1'], r['y1'], r['x2'], r['y2']]})
                if len(chosen) == CANDIDATES:
                    break
        if chosen:
            out[int(tid)] = chosen
    return out


def sharpness(image: np.ndarray) -> float:
    return float(cv2.Laplacian(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())


def extract_crops(video: Path, picks: dict[int, list[dict]]) -> dict[int, list[np.ndarray]]:
    """Вырезки рамок по метке времени; у трека остаются KEEP самых резких не ниже его медианы."""
    from aifootball.perception.frames import FrameReader

    requests = sorted((p['ts'], tid, p['box']) for tid, ps in picks.items() for p in ps)
    crops = defaultdict(list)
    with FrameReader(Path(video)) as reader:
        for ts, tid, (x1, y1, x2, y2) in requests:
            frame = reader.read(ts)
            if frame is None:
                continue
            crop = frame[int(y1) : int(y2), int(x1) : int(x2)]
            if crop.size:
                crops[tid].append(crop.copy())
    out = {}
    for tid, images in crops.items():
        values = [sharpness(c) for c in images]
        middle = float(np.median(values))
        ranked = sorted(zip(values, range(len(images))), key=lambda x: (-x[0], x[1]))
        out[tid] = [images[i] for v, i in ranked if v >= middle][:KEEP]
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_person_crops.py -q`
Expected: `3 passed`. Если `FrameReader` не находит кадр синтетического видео — проверить сигнатуру
`FrameReader.read(ts)` в `src/aifootball/perception/frames.py:147` и поправить тест под неё (не реализацию).

- [ ] **Step 5: Format, lint, commit**

```bash
.venv/bin/ruff format src/aifootball/perception/person_crops.py tests/test_person_crops.py
.venv/bin/ruff check src/aifootball/perception/person_crops.py tests/test_person_crops.py
git add src/aifootball/perception/person_crops.py tests/test_person_crops.py
git commit -m "feat(perception): pick and cut fragment crops for appearance features"
```

---

### Task 3: Признаки внешности (`perception/appearance.py`)

Выбор моделей — по навыку cv-model-selection (проверено 2026-11-23 по его справочнику от 2026-09-27; перед
скачиванием перечитать лицензии в источнике):

| Кандидат | Загрузка | Код | Веса | Решение |
|---|---|---|---|---|
| DINOv2 ViT-S/14 с регистрами | timm `vit_small_patch14_reg4_dinov2.lvd142m` | Apache-2.0 | Apache-2.0, без доступа по запросу | берём: самообучение, сильные замороженные признаки |
| SigLIP 2 ViT-B/16 | timm `vit_base_patch16_siglip_224.v2_webli` | Apache-2.0 | Apache-2.0, без доступа по запросу | берём: другое предобучение (по подписям) |
| Цвет HSV | без модели | — | — | нижняя планка |
| OSNet (torchreid) | pip `torchreid` | MIT | обучены на Market-1501 / MSMT17, условия наборов не проверены | пропуск: лицензия весов, библиотека не обновлялась с 2022 |
| InsightFace, BoxMOT | — | — | NC / AGPL | пропуск: лицензия; лица не распознаём |

**Files:**
- Modify: `pyproject.toml` (необязательная группа `people = ["timm>=1.0.30"]`), `uv.lock`
- Create: `src/aifootball/perception/appearance.py`
- Test: `tests/test_appearance.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Признаки внешности: цвет верха, шорт и обуви; модели timm — только при скачанных весах."""

import os
from pathlib import Path

import numpy as np
import pytest

from aifootball.perception.appearance import ENCODERS, TimmEmbedder, color_feature

CACHE = Path('models/hf')


def person(shirt, shorts, shoes, h=200, w=80, seed=0):
    rng = np.random.default_rng(seed)
    image = np.zeros((h, w, 3), np.uint8)
    image[: int(h * 0.5)] = shirt
    image[int(h * 0.5) : int(h * 0.85)] = shorts
    image[int(h * 0.85) :] = shoes
    noise = rng.integers(-8, 9, image.shape)
    return np.clip(image.astype(int) + noise, 0, 255).astype(np.uint8)


def test_color_feature_tells_kits_apart_and_is_normalized():
    red = color_feature(person((30, 30, 200), (20, 20, 20), (250, 250, 250)))
    red2 = color_feature(person((30, 30, 200), (20, 20, 20), (250, 250, 250), seed=1))
    blue_shoes = color_feature(person((30, 30, 200), (20, 20, 20), (200, 60, 30), seed=2))
    orange = color_feature(person((0, 140, 255), (20, 20, 20), (250, 250, 250), seed=3))
    assert np.linalg.norm(red) == pytest.approx(1.0)
    # Отличие в одной полосе из трёх: общая только яркость этой полосы — около (1 + 1 + 0,5) / 3.
    assert red @ red2 > 0.95
    assert red @ blue_shoes < 0.9 and red @ orange < 0.9


@pytest.mark.parametrize('kind', ['dino', 'siglip'])
def test_timm_encoders_embed_crops_to_unit_vectors(kind):
    pytest.importorskip('timm')
    if not any(CACHE.glob(f'models--timm--{ENCODERS[kind].split(".")[0]}*')):
        pytest.skip(f'нет скачанных весов {ENCODERS[kind]} в {CACHE}')
    os.environ['HF_HUB_OFFLINE'] = '1'
    embed = TimmEmbedder(kind, CACHE)
    out = embed([person((30, 30, 200), (20, 20, 20), (250, 250, 250)), person((0, 140, 255), (20, 20, 20), (0, 0, 0))])
    assert len(out) == 2 and all(abs(np.linalg.norm(v) - 1) < 1e-5 for v in out)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_appearance.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aifootball.perception.appearance'`

- [ ] **Step 3: Write the implementation**

```python
"""Признаки внешности фрагмента для сборки людей (analytics/people.py).

color_feature — без модели: гистограммы HSV (оттенок × насыщенность 12×4 и яркость 4) трёх полос рамки — верх
(15–50% высоты), шорты (50–85%) и обувь (85–100%), по центральным 60% ширины, чтобы меньше брать пол. Корень из
нормированных гистограмм (расстояние Хеллингера) и общая нормировка: косинус — похожесть.

TimmEmbedder — замороженные признаки моделей timm с весами Apache-2.0 (выбор и лицензии — в плане этапа 1 и
документе замера): DINOv2 ViT-S/14 с регистрами и SigLIP 2 ViT-B/16. Вход 112×224 (кратно патчам 14 и 16),
нормировка — из настроек весов, выход — нормированный вектор. Веса лежат в models/hf (в Git не попадают).
"""

from pathlib import Path

import cv2
import numpy as np

BANDS = ((0.15, 0.5), (0.5, 0.85), (0.85, 1.0))
INPUT = (112, 224)  # ширина, высота
ENCODERS = {
    'dino': 'vit_small_patch14_reg4_dinov2.lvd142m',
    'siglip': 'vit_base_patch16_siglip_224.v2_webli',
}


def color_feature(crop: np.ndarray) -> np.ndarray:
    h, w = crop.shape[:2]
    hsv = cv2.cvtColor(crop[:, int(w * 0.2) : max(int(w * 0.8), int(w * 0.2) + 1)], cv2.COLOR_BGR2HSV)
    parts = []
    for a, b in BANDS:
        band = hsv[int(h * a) : max(int(h * b), int(h * a) + 1)]
        hs = cv2.calcHist([band], [0, 1], None, [12, 4], [0, 180, 0, 256]).ravel()
        v = cv2.calcHist([band], [2], None, [4], [0, 256]).ravel()
        hist = np.concatenate([hs, v])
        parts.append(np.sqrt(hist / max(float(hist.sum()), 1.0)))
    f = np.concatenate(parts)
    return f / max(float(np.linalg.norm(f)), 1e-9)


class TimmEmbedder:
    def __init__(self, kind: str, cache: Path, device: str | None = None):
        import os

        os.environ.setdefault('HF_HUB_CACHE', str(Path(cache).resolve()))
        import timm
        import torch

        from aifootball.perception.detect import pick_device

        self.torch = torch
        self.device = device or pick_device()
        self.model = timm.create_model(ENCODERS[kind], pretrained=True, num_classes=0, dynamic_img_size=True)
        self.model = self.model.eval().to(self.device)
        cfg = self.model.pretrained_cfg
        self.mean = np.array(cfg['mean'], np.float32)
        self.std = np.array(cfg['std'], np.float32)

    def __call__(self, crops: list[np.ndarray]) -> list[np.ndarray]:
        if not crops:
            return []
        batch = []
        for crop in crops:
            rgb = cv2.cvtColor(cv2.resize(crop, INPUT, interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
            batch.append(((rgb.astype(np.float32) / 255.0 - self.mean) / self.std).transpose(2, 0, 1))
        x = self.torch.from_numpy(np.stack(batch)).to(self.device)
        with self.torch.no_grad():
            out = self.model(x).float().cpu().numpy()
        return [v / max(float(np.linalg.norm(v)), 1e-9) for v in out]
```

- [ ] **Step 4: Run tests to verify the color test passes**

Run: `.venv/bin/python -m pytest tests/test_appearance.py -q`
Expected: `1 passed, 2 skipped` (timm и веса ещё не скачаны)

- [ ] **Step 5: Ask the owner before downloading**

Скачивание — только с разрешения владельца проекта. Спросить одним вопросом: «Скачать пакет timm (PyPI) и веса
`timm/vit_small_patch14_reg4_dinov2.lvd142m` (~90 МБ) и `timm/vit_base_patch16_siglip_224.v2_webli`
(~350 МБ, Hugging Face) в `models/hf`? Лицензии — Apache-2.0». Перед вопросом открыть карточки моделей на
huggingface.co и сверить лицензию весов. Только после «да»:

В `pyproject.toml` в `[project.optional-dependencies]` добавить строку:

```toml
people = ["timm>=1.0.30"]
```

```bash
cd /Users/timofeynikulin/AI-football/.claude/worktrees/laughing-pike-bce1b6
uv lock && uv sync --locked --all-extras
HF_HUB_CACHE=models/hf .venv/bin/python -c "import timm; [timm.create_model(n, pretrained=True, num_classes=0) for n in ('vit_small_patch14_reg4_dinov2.lvd142m', 'vit_base_patch16_siglip_224.v2_webli')]"
.venv/bin/python -m pytest tests/test_appearance.py -q
```

Expected: `3 passed`. `git status --short` — `models/` нет (игнорируется), изменены только `pyproject.toml` и
`uv.lock`. При «нет» — замер только по цвету, это записывается в документ замера.

- [ ] **Step 6: Format, lint, commit**

```bash
.venv/bin/ruff format src/aifootball/perception/appearance.py tests/test_appearance.py
.venv/bin/ruff check src/aifootball/perception/appearance.py tests/test_appearance.py
git add pyproject.toml uv.lock src/aifootball/perception/appearance.py tests/test_appearance.py
git commit -m "feat(perception): colour, DINOv2-reg and SigLIP 2 appearance features"
```

---

### Task 4: Скрипт замера (`scripts/eval_people.py`)

**Files:**
- Create: `scripts/eval_people.py`
- Test: `tests/test_eval_people.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Скрипт замера сборки людей: интервал Уилсона, разложенная по похожести выборка пар, оценка порога."""

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('eval_people', Path('scripts/eval_people.py'))
eval_people = importlib.util.module_from_spec(spec)
sys.modules['eval_people'] = eval_people
spec.loader.exec_module(eval_people)


def test_wilson_interval():
    low, high = eval_people.wilson(72, 75)
    assert low == pytest.approx(0.889, abs=1e-3) and high == pytest.approx(0.986, abs=1e-3)
    assert eval_people.wilson(0, 0) == (0.0, 1.0)


def test_stratified_pairs_cover_every_similarity_band():
    rng = np.random.default_rng(0)
    sims = {(i, i + 1000): float(s) for i, s in enumerate(rng.uniform(0, 1, 500))}
    chosen = eval_people.stratified(sims, n=50, bands=10, seed=1)
    assert len(chosen) == 50 and len(set(chosen)) == 50
    values = sorted(sims[p] for p in chosen)
    assert values[0] < 0.1 and values[-1] > 0.9


def test_auc_and_paired_bootstrap():
    assert eval_people.auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert eval_people.auc([0.5], [0.5]) == 0.5
    truth = [True] * 20 + [False] * 20
    good = [0.9] * 20 + [0.1] * 20
    noisy = [0.6, 0.4] * 10 + [0.5] * 20
    low, high = eval_people.paired_bootstrap(truth, good, noisy, n=300)
    assert low > 0


def test_same_rate_by_similarity_is_a_step_function():
    labelled = [(0.1, False), (0.2, False), (0.6, True), (0.7, False), (0.9, True), (0.95, True)]
    p = eval_people.same_rate(labelled, bands=3)
    assert p(0.15) == 0.0 and p(0.65) == 0.5 and p(0.99) == 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_eval_people.py -q`
Expected: FAIL — `FileNotFoundError` / нет `scripts/eval_people.py`

- [ ] **Step 3: Write the script**

```python
"""Замер сборки фрагментов в людей по внешности (docs/superpowers/specs/2026-11-23-people-identity-design.md).

Папка --out (например data/people/hse) игнорируется Git: в ней кадры участников. Шаги:
  crops    — кадры фрагментов из видео: out/crops/<трек>_<n>.jpg и out/crops.json
  features — признаки фрагментов: out/features-<kind>.npz (kind: color | dino)
  cluster  — люди при порогах: по командам число людей, доля «Неразобранных» и сомнительных
  pairs    — пары для разметки глазами: out/pairs-<set>.json и листы out/sheets/<set>-NNN.jpg (6 пар на лист;
             на листе только номер пары, вариант и способ отбора не видны)
  score    — по разметке out/labels-<set>.json ({"<номер>": "same" | "different" | "unclear"})
Пример: .venv/bin/python scripts/eval_people.py crops --out data/people/hse --artifacts <...> --video <...> --venue <...>
"""

import argparse
import json
import random
import zipfile
from pathlib import Path

import cv2
import numpy as np

from aifootball.analytics.people import assemble, conflicts, mean_feature, units_from_index

KINDS = ['color', 'dino', 'siglip']
SHEET_H = 180
PER_SHEET = 6


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return float((c - r) / d), float((c + r) / d)


def auc(same: list[float], different: list[float]) -> float:
    """Площадь под ROC: доля пар (один человек, разные), где у «один человек» похожесть выше; ничья — половина."""
    if not same or not different:
        return float('nan')
    s, d = np.array(same)[:, None], np.array(different)[None, :]
    return float(((s > d).sum() + 0.5 * (s == d).sum()) / (s.size * d.size))


def paired_bootstrap(truth: list[bool], x: list[float], y: list[float], n: int = 2000, seed: int = 0):
    """95% интервал разницы AUC двух вариантов на одних и тех же парах."""
    rng = np.random.default_rng(seed)
    t, x, y = np.array(truth), np.array(x), np.array(y)
    diffs = []
    for _ in range(n):
        i = rng.integers(0, len(t), len(t))
        a = auc(list(x[i][t[i]]), list(x[i][~t[i]])) - auc(list(y[i][t[i]]), list(y[i][~t[i]]))
        if np.isfinite(a):
            diffs.append(a)
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def stratified(sims: dict, n: int, bands: int = 10, seed: int = 0) -> list:
    """n пар, поровну из полос по квантилям похожести."""
    rng = random.Random(seed)
    keys = sorted(sims, key=lambda k: sims[k])
    edges = np.linspace(0, len(keys), bands + 1).astype(int)
    per = [n // bands + (1 if b < n % bands else 0) for b in range(bands)]
    out = []
    for b in range(bands):
        band = keys[edges[b] : edges[b + 1]]
        out += rng.sample(band, min(per[b], len(band)))
    return out


def same_rate(labelled: list[tuple[float, bool]], bands: int = 8):
    """Доля «один человек» по полосам похожести (квантили размеченных): функция похожесть -> доля."""
    xs = sorted(labelled)
    edges = np.linspace(0, len(xs), bands + 1).astype(int)
    steps = []
    for b in range(bands):
        part = xs[edges[b] : edges[b + 1]]
        if part:
            steps.append((part[-1][0], sum(y for _, y in part) / len(part)))

    def p(s: float) -> float:
        for upper, rate in steps:
            if s <= upper:
                return rate
        return steps[-1][1]

    return p


def load_index(path: Path) -> dict:
    if path.suffix == '.zip':
        return json.loads(zipfile.ZipFile(path).read('track-index.json'))
    return json.loads(path.read_text())


def read_crops(out: Path) -> dict[int, list[np.ndarray]]:
    index = json.loads((out / 'crops.json').read_text())
    return {int(t): [cv2.imread(str(out / 'crops' / n)) for n in names] for t, names in index.items()}


def load_features(out: Path, kind: str) -> dict[int, np.ndarray]:
    data = np.load(out / f'features-{kind}.npz')
    return dict(zip(data['track_ids'].tolist(), data['features']))


def summary(index: dict, people) -> dict:
    info = {t['track_id']: t for t in index['tracks']}

    def sec(t):
        return sum(b - a for a, b in info[t]['intervals'])

    out = {}
    for team in 'AB':
        persons = [p for p in people.persons if p.team == team]
        loose = [u['track_id'] for u in people.unsorted if info[u['track_id']]['team'] == team]
        inside, rest = sum(p.seconds for p in persons), sum(sec(t) for t in loose)
        out[team] = {
            'people': len(persons),
            'unsorted_share': round(rest / max(inside + rest, 1e-9), 3),
            'doubtful': sum(len(p.doubtful) for p in persons),
            'top_seconds': [round(p.seconds) for p in persons[:15]],
        }
    return out


def cmd_crops(a):
    from aifootball import schemas
    from aifootball.perception.person_crops import extract_crops, pick_frames
    from aifootball.venue import load_venue

    venue = load_venue(a.venue)
    tracks = schemas.read(a.artifacts / 'tracks.parquet', 'tracks')
    usable = None
    if venue.is_ptz:
        from aifootball.geometry.registration import frame_homographies

        usable = set(frame_homographies(schemas.read(a.artifacts / 'registration.parquet', 'registration')))
    picks = pick_frames(tracks, (venue.frame_width, venue.frame_height), usable, venue.overlay)
    crops = extract_crops(a.video, picks)
    folder = a.out / 'crops'
    folder.mkdir(parents=True, exist_ok=True)
    index = {}
    for tid, images in sorted(crops.items()):
        names = []
        for n, image in enumerate(images):
            name = f'{tid}_{n}.jpg'
            cv2.imwrite(str(folder / name), image)
            names.append(name)
        index[str(tid)] = names
    (a.out / 'crops.json').write_text(json.dumps(index))
    print('фрагментов с кадрами:', len(index), 'кадров:', sum(map(len, index.values())))


def cmd_features(a):
    from aifootball.perception.appearance import TimmEmbedder, color_feature

    crops = read_crops(a.out)
    embed = (lambda images: [color_feature(i) for i in images]) if a.kind == 'color' else TimmEmbedder(a.kind, a.cache)
    ids, rows = [], []
    for tid, images in sorted(crops.items()):
        f = mean_feature(embed(images))
        if f is not None:
            ids.append(tid)
            rows.append(f)
    np.savez(a.out / f'features-{a.kind}.npz', track_ids=np.array(ids), features=np.stack(rows))
    print(a.kind, 'признаков:', len(ids))


def cmd_cluster(a):
    index = load_index(a.index)
    units = units_from_index(index, load_features(a.out, a.kind))
    for tau in a.threshold:
        people = assemble(units, tau, a.margin)
        print(a.kind, tau, json.dumps(summary(index, people), ensure_ascii=False))


def unit_key(u) -> str:
    return '-'.join(map(str, u.track_ids))


def sheet(out: Path, name: str, pairs: list[dict], crops: dict[int, list[np.ndarray]]):
    """Лист: строка на пару — номер, 3 кадра одной стороны, промежуток, 3 кадра другой."""

    def side(tracks):
        images = [c for t in tracks for c in crops.get(t, [])[:1]][:3] or [np.zeros((SHEET_H, 60, 3), np.uint8)]
        return [cv2.resize(i, (max(1, int(i.shape[1] * SHEET_H / i.shape[0])), SHEET_H)) for i in images]

    rows = []
    for p in pairs:
        label = np.full((SHEET_H, 90, 3), 255, np.uint8)
        cv2.putText(label, f'#{p["id"]}', (5, SHEET_H // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        gap = np.full((SHEET_H, 40, 3), 255, np.uint8)
        rows.append(np.hstack([label, *side(p['a']), gap, *side(p['b'])]))
    width = max(r.shape[1] for r in rows)
    rows = [np.hstack([r, np.full((SHEET_H, width - r.shape[1], 3), 255, np.uint8)]) for r in rows]
    folder = out / 'sheets'
    folder.mkdir(exist_ok=True)
    cv2.imwrite(str(folder / name), np.vstack([np.vstack([r, np.full((8, width, 3), 200, np.uint8)]) for r in rows]))


def cmd_pairs(a):
    index = load_index(a.index)
    labelled = set()
    for f in a.out.glob('pairs-*.json'):
        labelled |= {(tuple(p['a']), tuple(p['b'])) for p in json.loads(f.read_text())}
    chosen = []
    if a.set == 'calib':
        for kind in a.kinds:
            units = units_from_index(index, load_features(a.out, kind))
            blocked = conflicts(units)
            sims = {
                (i, j): float(units[i].feature @ units[j].feature)
                for i in range(len(units))
                for j in range(i + 1, len(units))
                if not blocked[i, j] and units[i].feature is not None and units[j].feature is not None
            }
            for i, j in stratified(sims, a.n // len(a.kinds), seed=a.seed):
                chosen.append({'a': list(units[i].track_ids), 'b': list(units[j].track_ids), 'kind': kind})
    else:
        units = units_from_index(index, load_features(a.out, a.kind))
        people = assemble(units, a.tau, a.margin)
        by_track = {t: u for u in units for t in u.track_ids}
        rng = random.Random(a.seed)
        members = {p.key: list({unit_key(by_track[t]): by_track[t] for t in p.track_ids}.values()) for p in people.persons}
        multi = [k for k, us in members.items() if len(us) > 1]
        for _ in range(a.n_within * 20):
            if sum(1 for c in chosen if c['kind'] == 'within') >= a.n_within:
                break
            us = members[rng.choice(multi)]
            x, y = rng.sample(us, 2)
            chosen.append({'a': list(x.track_ids), 'b': list(y.track_ids), 'kind': 'within'})
        blocked = conflicts(units)
        pos = {unit_key(u): i for i, u in enumerate(units)}
        for _ in range(a.n_neighbor * 20):
            if sum(1 for c in chosen if c['kind'] == 'neighbor') >= a.n_neighbor:
                break
            key = rng.choice(list(members))
            x = rng.choice(members[key])
            options = [
                (np.mean([x.feature @ y.feature for y in us]), k)
                for k, us in members.items()
                if k != key and not any(blocked[pos[unit_key(x)], pos[unit_key(y)]] for y in us)
            ]
            if options:
                _, best = max(options)
                chosen.append({'a': list(x.track_ids), 'b': list(rng.choice(members[best]).track_ids), 'kind': 'neighbor'})
    unique, seen = [], set(labelled)
    for c in chosen:
        k = (tuple(c['a']), tuple(c['b']))
        if k not in seen and k[::-1] not in seen:
            seen.add(k)
            unique.append(c)
    random.Random(a.seed).shuffle(unique)
    for n, c in enumerate(unique, 1):
        c['id'] = f'{a.set}{n}'
    (a.out / f'pairs-{a.set}.json').write_text(json.dumps(unique, ensure_ascii=False))
    crops = read_crops(a.out)
    for s in range(0, len(unique), PER_SHEET):
        sheet(a.out, f'{a.set}-{s // PER_SHEET + 1:03d}.jpg', unique[s : s + PER_SHEET], crops)
    print('пар:', len(unique), 'листов:', (len(unique) + PER_SHEET - 1) // PER_SHEET)


def cmd_score(a):
    index = load_index(a.index)
    pairs = json.loads((a.out / f'pairs-{a.set}.json').read_text())
    labels = json.loads((a.out / f'labels-{a.set}.json').read_text())
    known = [p for p in pairs if labels.get(p['id']) in ('same', 'different')]
    print('размечено:', len(known), 'из', len(pairs), '· не понять:', sum(labels.get(p['id']) == 'unclear' for p in pairs))
    if a.set == 'calib':
        sims = {}
        for kind in a.kinds:
            units = units_from_index(index, load_features(a.out, kind))
            by_track = {t: u for u in units for t in u.track_ids}
            sims[kind] = {
                p['id']: float(by_track[p['a'][0]].feature @ by_track[p['b'][0]].feature)
                for p in known
                if by_track[p['a'][0]].feature is not None and by_track[p['b'][0]].feature is not None
            }
        common = [p for p in known if all(p['id'] in sims[k] for k in a.kinds)]
        truth = [labels[p['id']] == 'same' for p in common]
        print('пар с признаками всех вариантов:', len(common), '· один человек:', sum(truth))
        for kind in a.kinds:
            v = [sims[kind][p['id']] for p in common]
            print(kind, 'AUC', round(auc([s for s, t in zip(v, truth) if t], [s for s, t in zip(v, truth) if not t]), 3))
        for n, x in enumerate(a.kinds):
            for y in a.kinds[n + 1 :]:
                low, high = paired_bootstrap(truth, [sims[x][p['id']] for p in common], [sims[y][p['id']] for p in common])
                print(f'AUC {x} − {y}: 95% {low:+.3f}…{high:+.3f}')
        for kind in a.kinds:
            feats = load_features(a.out, kind)
            units = units_from_index(index, feats)
            by_track = {t: u for u in units for t in u.track_ids}

            def sim(p):
                x, y = by_track[p['a'][0]].feature, by_track[p['b'][0]].feature
                return None if x is None or y is None else float(x @ y)

            data = [(s, labels[p['id']] == 'same') for p in known if (s := sim(p)) is not None]
            rate = same_rate(data)
            for tau in a.threshold:
                people = assemble(units, tau, a.margin)
                within = []
                for person in people.persons:
                    us = list({unit_key(by_track[t]): by_track[t] for t in person.track_ids}.values())
                    within += [(rate(float(x.feature @ y.feature)), x.seconds * y.seconds) for n, x in enumerate(us) for y in us[n + 1 :]]
                expected = sum(r * w for r, w in within) / max(sum(w for _, w in within), 1e-9)
                print(kind, tau, 'ожидаемая точность', round(expected, 3), json.dumps(summary(index, people), ensure_ascii=False))
    else:
        for kind in ('within', 'neighbor'):
            part = [p for p in known if p['kind'] == kind]
            same = sum(labels[p['id']] == 'same' for p in part)
            low, high = wilson(same, len(part))
            print(kind, f'один человек {same}/{len(part)} = {same / max(len(part), 1):.3f} (95%: {low:.3f}–{high:.3f})')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='step', required=True)
    s = sub.add_parser('crops')
    s.add_argument('--artifacts', type=Path, required=True)
    s.add_argument('--video', type=Path, required=True)
    s.add_argument('--venue', type=Path, required=True)
    s = sub.add_parser('features')
    s.add_argument('--kind', choices=KINDS, required=True)
    s.add_argument('--cache', type=Path, default=Path('models/hf'))
    s = sub.add_parser('cluster')
    s.add_argument('--index', type=Path, required=True)
    s.add_argument('--kind', choices=KINDS, required=True)
    s.add_argument('--threshold', type=float, nargs='+', required=True)
    s.add_argument('--margin', type=float, default=0.05)
    s = sub.add_parser('pairs')
    s.add_argument('--index', type=Path, required=True)
    s.add_argument('--set', choices=['calib', 'final'], required=True)
    s.add_argument('--kinds', nargs='+', default=KINDS)
    s.add_argument('--n', type=int, default=210)
    s.add_argument('--kind', choices=KINDS)
    s.add_argument('--tau', type=float)
    s.add_argument('--margin', type=float, default=0.05)
    s.add_argument('--n-within', type=int, default=75)
    s.add_argument('--n-neighbor', type=int, default=75)
    s.add_argument('--seed', type=int, default=1)
    s = sub.add_parser('score')
    s.add_argument('--index', type=Path, required=True)
    s.add_argument('--set', choices=['calib', 'final'], required=True)
    s.add_argument('--kinds', nargs='+', default=KINDS)
    s.add_argument('--threshold', type=float, nargs='*', default=[])
    s.add_argument('--margin', type=float, default=0.05)
    for s in sub.choices.values():
        s.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    {'crops': cmd_crops, 'features': cmd_features, 'cluster': cmd_cluster, 'pairs': cmd_pairs, 'score': cmd_score}[a.step](a)


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_eval_people.py -q`
Expected: `4 passed`

- [ ] **Step 5: Format, lint, commit**

```bash
.venv/bin/ruff format scripts/eval_people.py tests/test_eval_people.py
.venv/bin/ruff check scripts/eval_people.py tests/test_eval_people.py
git add scripts/eval_people.py tests/test_eval_people.py
git commit -m "feat(scripts): people clustering measurement with blind pair sheets"
```

---

### Task 5: Замер на ВШЭ — кадры, признаки, перебор порога

Переменные для всех шагов (вставлять в начало команды):

```bash
cd /Users/timofeynikulin/AI-football/.claude/worktrees/laughing-pike-bce1b6
D=/Users/timofeynikulin/AI-football/data/processing/hse-2026-11-15/work
I=/Users/timofeynikulin/AI-football/data/service/attachments/analysis/92e661fe-7bb6-4d3b-9e06-79c05d24ae23-788414d6920ee90d.zip
O=data/people/hse
```

- [ ] **Step 1: Кадры фрагментов** (видео 43 мин: в фоне, ожидание до ~15 мин)

```bash
.venv/bin/python scripts/eval_people.py crops --out $O --artifacts $D/artifacts --video /Users/timofeynikulin/AI-football/data/raw/hse_futsal_456239351_16596-19200.mp4 --venue $D/venue
```

Expected: `фрагментов с кадрами: N кадров: M`; N — большая часть из 1390 фрагментов игроков и вратарей.
Открыть 3–4 вырезки из `$O/crops` (Read) — рамка на человеке, не на поле.

- [ ] **Step 2: Признаки**

```bash
.venv/bin/python scripts/eval_people.py features --out $O --kind color
.venv/bin/python scripts/eval_people.py features --out $O --kind dino
.venv/bin/python scripts/eval_people.py features --out $O --kind siglip
```

Expected: `color признаков: N`, `dino признаков: N`, `siglip признаков: N` (то же N).

- [ ] **Step 3: Перебор порога**

```bash
.venv/bin/python scripts/eval_people.py cluster --out $O --index $I --kind color --threshold 0.6 0.7 0.8 0.85 0.9
.venv/bin/python scripts/eval_people.py cluster --out $O --index $I --kind dino --threshold 0.4 0.5 0.6 0.7 0.8
.venv/bin/python scripts/eval_people.py cluster --out $O --index $I --kind siglip --threshold 0.4 0.5 0.6 0.7 0.8
```

Expected: строка на порог — по командам `people`, `unsorted_share`, `doubtful`, `top_seconds`. Записать таблицу.
Если у модели даже на низком пороге людей больше 40 на команду — расширить перебор вниз (0.3, 0.2).

---

### Task 6: Калибровочная разметка и выбор порога

- [ ] **Step 1: Пары и листы**

```bash
.venv/bin/python scripts/eval_people.py pairs --out $O --index $I --set calib --n 210
```

Expected: `пар: ~210 листов: ~35` (по 70 на вариант, разложены по похожести, повторы убраны).

- [ ] **Step 2: Разметка глазами**

Открыть каждый лист `$O/sheets/calib-NNN.jpg` (Read) и для каждой строки `#calibK` записать «same» (один
человек: телосложение, волосы, обувь, гетры, шорты), «different» или «unclear» (не видно). Ответы — в
`$O/labels-calib.json`: `{"calib1": "same", "calib2": "different", ...}`. Пару не пропускать: не уверен — «unclear».

- [ ] **Step 3: Оценка по порогам**

```bash
.venv/bin/python scripts/eval_people.py score --out $O --index $I --set calib --threshold 0.4 0.5 0.6 0.7 0.8 0.85 0.9
```

Expected: сначала AUC каждого варианта на одних и тех же парах и 95% интервалы разниц AUC (парный бутстреп) —
вариант выбирается по ним, не по одному порогу; затем строки «<вариант> <порог> ожидаемая точность X {...}».
Выбрать вариант и наибольший охват при ожидаемой
точности ≥ 0,96 (запас к воротам 0,95), людях ≤ 20 и «Неразобранных» ≤ 15%. μ (порог сомнения) — значение, при
котором сомнительных 5–10% фрагментов в людях (перебор `--margin 0.02 0.05 0.1` шагом `cluster`). Если ни один
вариант не дотягивает — Task 8 (ворота не пройдены).

---

### Task 7: Проверка выбранного варианта (ворота)

- [ ] **Step 1: Новые пары**

```bash
.venv/bin/python scripts/eval_people.py pairs --out $O --index $I --set final --kind <вариант> --tau <τ> --margin <μ>
```

Expected: `пар: ~150` (пары калибровки исключены).

- [ ] **Step 2: Разметка глазами** — как в Task 6, файл `$O/labels-final.json`.

- [ ] **Step 3: Оценка**

```bash
.venv/bin/python scripts/eval_people.py score --out $O --index $I --set final
```

Expected: `within один человек k/n = p (95%: a–b)` и `neighbor ...`. Ворота: `within` p ≥ 0,95 и по Task 5 для
выбранных τ, μ людей ≤ 20 на команду, «Неразобранных» ≤ 15%.

---

### Task 8: Документ замера и решение

**Files:**
- Create: `docs/<дата замера>-people-clustering.md`
- Modify: `docs/README.md` (раздел «Архитектура и следующие этапы»)

- [ ] **Step 1: Документ** — по-русски, только числа, без кадров участников:
  данные и команды; таблица лицензий кандидатов (Task 3) с датой проверки; сколько фрагментов дали кадры;
  AUC вариантов на общих парах и интервалы разниц; таблица перебора порога (Task 5); калибровка по вариантам
  (доля «один человек» по полосам похожести, ожидаемая точность по порогам); выбранные вариант, τ, μ и почему;
  проверка (within и neighbor с интервалами); итог ворот; ограничения (разметка одним разметчиком, один матч,
  трансляция). При непройденных воротах — что не дотянуло и что пробовать (OSNet, кадры крупнее, обучение
  на ВШЭ) — без реализации.

- [ ] **Step 2: Строка в `docs/README.md`** под «Люди вместо фрагментов»: итог замера одной фразой с числами.

- [ ] **Step 3: Проверки и коммит**

```bash
.venv/bin/ruff format --check src tests scripts migrations
.venv/bin/ruff check src tests scripts migrations
.venv/bin/python -m pytest tests/test_people.py tests/test_person_crops.py tests/test_appearance.py tests/test_eval_people.py -q
git status --short   # data/ и models/ не в списке
git add docs
git commit -m "docs: people clustering measurement on the HSE broadcast"
```

- [ ] **Step 4: PR этапа 1 и отчёт владельцу** — ветка `feat/people-identity`, PR в `main`: модуль сборки, кадры,
  признаки, скрипт, документ замера. В отчёте — итог ворот. Пройдены — писать план этапа 2 (пакет результата,
  сервис, экран «Люди») по спецификации с выбранными τ, μ и моделью. Не пройдены — остановиться и показать цифры.
