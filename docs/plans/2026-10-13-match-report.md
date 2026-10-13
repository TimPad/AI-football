# Отчёт по матчу — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `python -m aifootball.cli report` строит из готовых артефактов матча один HTML-файл с отчётом
в духе Sofascore (команды, трети, тепловые карты, ход матча, игроки, моменты) и `report.json` с теми же цифрами.

**Architecture:** таймы (`analytics/periods.py`) → цифры (`analytics/report_data.py`, словарь без HTML) →
`report.json` → картинки из видео (`report/frames.py`) + SVG (`report/svg.py`) → сборка страницы
(`report/render.py`). Перед этим исправляется назначение вратарей в `perception/teams.py`.

**Tech Stack:** Python 3.12, polars, numpy, OpenCV, pytest. Новых зависимостей нет: HTML собирается f-строками,
графики — SVG, картинки — JPEG в base64.

Спецификация: `docs/specs/2026-10-13-match-report-design.md`.

Запуск тестов: `.venv/bin/python -m pytest -q` из корня репозитория. Системный `python` — Anaconda без пакета,
им не пользоваться.

Соглашения кода: комментарии и docstring по-русски, короткие; константы модуля — в начале файла
с комментарием «почему такое значение». Координаты в `state.parquet`: `x_m` вдоль поля (0..length_m),
`y_m` поперёк (0..width_m). `role`: player | goalkeeper | referee | unknown; `team`: A | B | null.

---

## Карта файлов

| Файл | Что делает |
|---|---|
| `src/aifootball/perception/teams.py` (изменить) | вратарь — не короче 20 с у ворот; команда вратаря — защищающая эти ворота |
| `src/aifootball/analytics/periods.py` (новый) | `Period`, `parse_halves`, `find_halves`, `make_periods`, `in_period` |
| `src/aifootball/analytics/report_data.py` (новый) | все цифры отчёта, `build_report` |
| `src/aifootball/report/__init__.py` (новый) | пустой |
| `src/aifootball/report/svg.py` (новый) | поле, тепловая карта, трети, линейный график — SVG-строки |
| `src/aifootball/report/frames.py` (новый) | миниатюры и стоп-кадры из видео в base64 |
| `src/aifootball/report/render.py` (новый) | `image_requests`, `render_html` — страница целиком |
| `src/aifootball/cli.py` (изменить) | команда `report` |
| `tests/test_teams.py` (изменить) | вратари |
| `tests/test_periods.py`, `tests/test_report_data.py`, `tests/test_report_svg.py`, `tests/test_report_frames.py`, `tests/test_report_cli.py` (новые) | тесты |
| `tests/report_fixtures.py` (новый) | синтетический матч для тестов отчёта |

---

### Task 1: Вратари — длительность и команда по стороне поля

**Files:**
- Modify: `src/aifootball/perception/teams.py` (функция `assign_roles`)
- Test: `tests/test_teams.py`

Сейчас `assign_roles` делает вратарём любой трек с медианой x < 7 м (или > length − 7) у центра ширины
и даёт ему команду «A» для левых ворот, «B» для правых. Нужно: (1) вратарь — только если трек пробыл на поле
≥ 20 с; (2) левые ворота защищает команда, у полевых игроков которой медианное x меньше.

- [ ] **Step 1: Обновить существующий тест и добавить новые**

В `tests/test_teams.py` заменить функцию `test_assign_roles_goalkeeper_and_referee` целиком и добавить два теста:

```python
def _role_rows(track_id, foot_x, foot_y, seconds, team="A", a=60.0):
    """Трек, стоящий в точке (foot_x, foot_y) px seconds секунд при 10 fps (venue: 10 px = 1 м)."""
    return [{
        "frame_id": f, "ts": f / 10, "cls": "person",
        "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 30.0, "conf": 0.9,
        "torso_l": 120.0, "torso_a": a, "torso_b": 140.0,
        "track_id": track_id, "foot_x": foot_x, "foot_y": foot_y,
        "in_pitch": True, "role": "player", "team": team,
    } for f in range(int(seconds * 10))]


def _roles(res, track_id):
    return res.filter(pl.col("track_id") == track_id).select("role", "team").unique().rows()


def test_assign_roles_goalkeeper_and_referee(venue):
    from aifootball.perception.teams import assign_roles

    rows = (_role_rows(1, 200.0, 100.0, 30)  # центр поля
            + _role_rows(2, 20.0, 100.0, 30)  # у левых ворот: x = 2 м
            + _role_rows(3, 200.0, 2.0, 30, a=150.0))  # у бровки: y = 0.2 м
    res = assign_roles(pl.DataFrame(rows, schema=schemas.TRACKS), venue)

    assert _roles(res, 1) == [("player", "A")]
    assert _roles(res, 2)[0][0] == "goalkeeper"
    assert _roles(res, 3) == [("referee", None)]


def test_short_track_at_goal_is_not_goalkeeper(venue):
    # Атакующий полевой игрок 5 с у чужих ворот — не вратарь
    from aifootball.perception.teams import assign_roles

    res = assign_roles(pl.DataFrame(_role_rows(1, 20.0, 100.0, 5), schema=schemas.TRACKS), venue)

    assert _roles(res, 1) == [("player", "A")]


def test_goalkeeper_belongs_to_team_defending_that_goal(venue):
    # Полевые B держатся слева (x = 10 м), A — справа (x = 30 м): левые ворота защищает B
    from aifootball.perception.teams import assign_roles

    rows = (_role_rows(1, 100.0, 100.0, 30, team="B") + _role_rows(2, 300.0, 100.0, 30, team="A")
            + _role_rows(3, 20.0, 100.0, 30, team="A")  # у левых ворот, цвет формы ошибочно дал A
            + _role_rows(4, 380.0, 100.0, 30, team="B"))  # у правых ворот
    res = assign_roles(pl.DataFrame(rows, schema=schemas.TRACKS), venue)

    assert _roles(res, 3) == [("goalkeeper", "B")]
    assert _roles(res, 4) == [("goalkeeper", "A")]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_teams.py -q`
Expected: FAIL в `test_short_track_at_goal_is_not_goalkeeper` (трек 5 с стал вратарём)
и в `test_goalkeeper_belongs_to_team_defending_that_goal` (трек 3 получил «A»).

- [ ] **Step 3: Изменить `assign_roles`**

В `src/aifootball/perception/teams.py` после `MIN_OBSERVATIONS = 10` добавить:

```python
# Вратарь стоит у своих ворот долго; короче — обрывок трека атакующего полевого игрока у чужих ворот
GOALKEEPER_MIN_S = 20.0
```

В `assign_roles`:

1. В `pos_df` добавить время, команду и роль:

```python
    pos_df = on_pitch.select("track_id", "ts", "team", "role").with_columns(
        x_m=pl.Series(meters[:, 0]),
        y_m=pl.Series(meters[:, 1]),
    )
```

2. В `track_stats` добавить длительность:

```python
            duration_s=pl.col("ts").max() - pl.col("ts").min(),
```

3. Перед циклом `for row in track_stats.iter_rows(named=True):` определить, кто защищает левые ворота.
   Треки, стоящие у ворот, в этом не участвуют: это кандидаты во вратари, их команда по цвету ненадёжна
   (иначе в тесте `test_goalkeeper_belongs_to_team_defending_that_goal` они перетянут медианы):

```python
    away_from_goals = track_stats.filter(
        (pl.col("x_med") >= 7.0) & (pl.col("x_med") <= length_m - 7.0)
    ).select("track_id")
    left_team, right_team = defending_sides(pos_df.join(away_from_goals, on="track_id"))
```

   (`length_m` в функции уже определён выше как `venue.length_m`; если строка с ним стоит после этого места —
   перенести её выше.)

4. В цикле заменить блок проверки вратаря:

```python
        # Проверка на вратаря: у ворот (в пределах 7м), по центру ширины и достаточно долго
        if row["duration_s"] < GOALKEEPER_MIN_S:
            continue
        near_goal_a = (x_med < 7.0) and (abs(y_med - half_width) < 5.0) and (row["x_max"] < length_m / 2.0)
        near_goal_b = (x_med > length_m - 7.0) and (abs(y_med - half_width) < 5.0) and (row["x_min"] > length_m / 2.0)

        if near_goal_a:
            gk_tracks[tid] = left_team
        elif near_goal_b:
            gk_tracks[tid] = right_team
```

5. Добавить функцию в конец модуля (перед `_two_clusters`):

```python
def defending_sides(positions: pl.DataFrame) -> tuple[str, str]:
    """(команда у ворот x = 0, команда у ворот x = length): левые ворота защищает команда,
    у полевых игроков которой медианное x меньше. Без обеих команд — по умолчанию A слева.

    positions — строки с колонками team, role, x_m.
    """
    med = (
        positions.filter(pl.col("team").is_in(["A", "B"]) & (pl.col("role") == "player"))
        .group_by("team").agg(pl.col("x_m").median())
    )
    if med.height < 2:
        return "A", "B"
    left = med.sort("x_m")["team"][0]
    return left, ("B" if left == "A" else "A")
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest tests/test_teams.py -q`
Expected: PASS (все тесты файла).

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (весь набор; число тестов на 2 больше прежних 159).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/perception/teams.py tests/test_teams.py
git commit -m "Вратари: не короче 20 с у ворот, команда — защищающая эти ворота"
```

---

### Task 2: Таймы

**Files:**
- Create: `src/aifootball/analytics/periods.py`
- Test: `tests/test_periods.py`

- [ ] **Step 1: Написать тесты**

`tests/test_periods.py`:

```python
import polars as pl
import pytest

from aifootball import schemas
from aifootball.analytics.periods import find_halves, in_period, make_periods, parse_halves


def _crowd(seconds, people_at):
    """tracks: в кадре t (1 fps) на поле people_at(t) человек."""
    rows = []
    for t in range(seconds):
        for k in range(people_at(t)):
            rows.append({"frame_id": t, "ts": float(t), "cls": "person", "x1": 0.0, "y1": 0.0, "x2": 10.0,
                         "y2": 30.0, "conf": 0.9, "torso_l": 0.0, "torso_a": 0.0, "torso_b": 0.0,
                         "track_id": k, "foot_x": 5.0, "foot_y": 30.0, "in_pitch": True,
                         "role": "player", "team": "A"})
    return pl.DataFrame(rows, schema=schemas.TRACKS)


def test_parse_halves():
    assert parse_halves("0:40-21:50, 27:10-46:00", 3000) == [(40.0, 1310.0), (1630.0, 2760.0)]


@pytest.mark.parametrize("text", ["0:00-10:00,9:00-20:00", "0:00-60:00", "5:00-1:00"])
def test_parse_halves_rejects_bad_spans(text):
    with pytest.raises(ValueError):
        parse_halves(text, 1500)


def test_find_halves_splits_at_long_break():
    # Игра 0–300 с, перерыв (1 человек) 300–600 с, игра 600–900 с, пустой хвост 900–1000 с
    tracks = _crowd(1000, lambda t: 8 if t < 300 or 600 <= t < 900 else 1)
    halves = find_halves(tracks)
    assert len(halves) == 2
    (s1, e1), (s2, e2) = halves
    assert s1 == pytest.approx(0, abs=10) and e1 == pytest.approx(300, abs=10)
    assert s2 == pytest.approx(600, abs=10) and e2 == pytest.approx(900, abs=10)


def test_find_halves_ignores_short_stoppage():
    # Пауза 60 с — не перерыв
    tracks = _crowd(600, lambda t: 1 if 200 <= t < 260 else 8)
    halves = find_halves(tracks)
    assert len(halves) == 1
    assert halves[0][0] == pytest.approx(0, abs=10) and halves[0][1] == pytest.approx(599, abs=10)


def test_make_periods_and_filter():
    periods = make_periods([(0.0, 10.0), (20.0, 30.0)])
    assert [p.key for p in periods] == ["all", "h1", "h2"]
    assert periods[0].duration_s == 20.0
    df = pl.DataFrame({"ts": [1.0, 15.0, 25.0]})
    assert in_period(df, periods[0].spans)["ts"].to_list() == [1.0, 25.0]
    assert [p.key for p in make_periods([(0.0, 10.0)])] == ["all"]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_periods.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aifootball.analytics.periods'`

- [ ] **Step 3: Реализация**

`src/aifootball/analytics/periods.py`:

```python
"""Таймы матча: автоматически по пустому полю или из флага --halves.

Перерыв — участок дольше BREAK_MIN_S, где на поле меньше ACTIVE_MIN_PEOPLE человек
(медиана по кадрам окна WINDOW_S). Короче — остановка внутри тайма (аут, замена, травма).
"""

from dataclasses import dataclass

import numpy as np
import polars as pl

BREAK_MIN_S = 120.0
ACTIVE_MIN_PEOPLE = 4
WINDOW_S = 10.0


@dataclass(frozen=True)
class Period:
    key: str  # all | h1 | h2
    name: str
    spans: tuple[tuple[float, float], ...]

    @property
    def duration_s(self) -> float:
        return sum(end - start for start, end in self.spans)


def parse_halves(text: str, video_s: float) -> list[tuple[float, float]]:
    """«0:40-21:50,27:10-46:00» -> [(40, 1310), (1630, 2760)]; ошибка, если таймы пересекаются или вне записи."""
    spans = []
    for part in text.split(","):
        start, end = part.strip().split("-")
        spans.append((_seconds(start), _seconds(end)))
    spans.sort()
    for start, end in spans:
        if not 0 <= start < end <= video_s + 1e-6:
            raise ValueError(f"тайм {start:.0f}–{end:.0f} с вне записи 0–{video_s:.0f} с")
    for (_, end), (start, _) in zip(spans, spans[1:]):
        if start < end:
            raise ValueError("таймы пересекаются")
    return spans


def _seconds(clock: str) -> float:
    minutes, seconds = clock.strip().split(":")
    return int(minutes) * 60 + float(seconds)


def find_halves(tracks: pl.DataFrame) -> list[tuple[float, float]]:
    """Участки игры: один (перерыв не найден) или два — до и после самого длинного перерыва."""
    if tracks.is_empty():
        return []
    frames = tracks.select("frame_id", "ts").unique("frame_id")
    counts = tracks.filter(pl.col("in_pitch")).group_by("frame_id").agg(n=pl.len())
    per_frame = frames.join(counts, on="frame_id", how="left").with_columns(pl.col("n").fill_null(0))
    windows = (
        per_frame.with_columns(w=(pl.col("ts") // WINDOW_S).cast(pl.Int64))
        .group_by("w").agg(pl.col("n").median())
    )
    t_end = float(tracks["ts"].max())
    active = np.zeros(int(t_end // WINDOW_S) + 1, dtype=bool)
    active[windows["w"].to_numpy()] = windows["n"].to_numpy() >= ACTIVE_MIN_PEOPLE

    runs = _runs(active)
    if not runs:
        return []
    merged = [list(runs[0])]
    for start, end in runs[1:]:
        if (start - merged[-1][1]) * WINDOW_S < BREAK_MIN_S:
            merged[-1][1] = end  # короткая остановка внутри тайма
        else:
            merged.append([start, end])
    spans = [(start * WINDOW_S, min(end * WINDOW_S, t_end)) for start, end in merged]
    if len(spans) <= 2:
        return spans
    gaps = [b[0] - a[1] for a, b in zip(spans, spans[1:])]
    k = int(np.argmax(gaps))
    return [(spans[0][0], spans[k][1]), (spans[k + 1][0], spans[-1][1])]


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """Отрезки [начало, конец) подряд идущих True."""
    padded = np.concatenate([[False], mask, [False]]).astype(int)
    edges = np.flatnonzero(np.diff(padded))
    return list(zip(edges[::2].tolist(), edges[1::2].tolist()))


def make_periods(spans: list[tuple[float, float]]) -> list[Period]:
    """«Весь матч» и, если таймов два, «1-й тайм» и «2-й тайм»."""
    periods = [Period("all", "Весь матч", tuple(spans))]
    if len(spans) == 2:
        periods += [Period("h1", "1-й тайм", (spans[0],)), Period("h2", "2-й тайм", (spans[1],))]
    return periods


def in_period(df: pl.DataFrame, spans) -> pl.DataFrame:
    """Строки с ts внутри любого из интервалов [начало, конец)."""
    cond = pl.lit(False)
    for start, end in spans:
        cond = cond | ((pl.col("ts") >= start) & (pl.col("ts") < end))
    return df.filter(cond)
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest tests/test_periods.py -q`
Expected: PASS (7 тестов: 1 + 3 параметра + 3).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/analytics/periods.py tests/test_periods.py
git commit -m "Таймы матча: перерыв по пустому полю, флаг --halves"
```

---

### Task 3: Синтетический матч для тестов отчёта

**Files:**
- Create: `tests/report_fixtures.py`

Общий генератор для задач 4–12. Поле 40 × 20 м (как у фикстуры `venue` в `tests/conftest.py`:
10 px = 1 м). Команда B держится слева (защищает x = 0, игроки около x = 11), A — справа (около x = 29).
По 4 полевых игрока и вратарю, 2 кадра в секунду, 200 с, бег по синусоиде (амплитуда 3 м, период 20 с:
0.6 м/с = 36 м/мин). При `sprint=True` игрок A1 (трек 11) вместо синусоиды стоит на x = 30, на 20–24 с
бежит к x = 6 со скоростью 6 м/с и дальше стоит на x = 6.

- [ ] **Step 1: Создать файл**

`tests/report_fixtures.py`:

```python
"""Синтетический матч для тестов отчёта: state и tracks с известными цифрами."""

import numpy as np
import polars as pl

from aifootball import schemas

FPS = 2.0
SECONDS = 200
LENGTH, WIDTH = 40.0, 20.0


def _player(track_id, team, role, x0, y0, amp, phase, ts):
    """Траектория: колебание вдоль x вокруг x0 (амплитуда amp м, период 20 с)."""
    x = x0 + amp * np.sin(2 * np.pi * ts / 20 + phase)
    y = np.full_like(ts, y0)
    return track_id, team, role, x, y


def synthetic_match(seconds: int = SECONDS, sprint: bool = True) -> tuple[pl.DataFrame, pl.DataFrame]:
    ts = np.arange(0, seconds, 1 / FPS)
    people = []
    for i in range(4):
        people.append(_player(1 + i, "B", "player", 11.0, 4.0 + 4 * i, 3.0, i, ts))
        people.append(_player(11 + i, "A", "player", 29.0, 4.0 + 4 * i, 3.0, i, ts))
    people.append(_player(9, "B", "goalkeeper", 1.5, 10.0, 0.5, 0.0, ts))
    people.append(_player(19, "A", "goalkeeper", 38.5, 10.0, 0.5, 0.0, ts))

    state_rows, track_rows = [], []
    for track_id, team, role, x, y in people:
        if sprint and track_id == 11:  # A1: стоит, спринт 6 м/с с 20 по 24 с, снова стоит
            x = np.where(ts < 20, 30.0, np.where(ts < 24, 30.0 - 6.0 * (ts - 20), 6.0))
        vx = np.gradient(x, ts)
        vy = np.gradient(y, ts)
        speed = np.hypot(vx, vy)
        for k in range(len(ts)):
            frame_id = int(round(ts[k] * FPS))
            state_rows.append({"frame_id": frame_id, "ts": float(ts[k]), "track_id": track_id, "role": role,
                               "team": team, "x_m": x[k], "y_m": y[k], "vx": vx[k], "vy": vy[k],
                               "speed": speed[k], "interpolated": False})
            px, py = x[k] * 10, y[k] * 10
            track_rows.append({"frame_id": frame_id, "ts": float(ts[k]), "cls": "person",
                               "x1": px - 5, "y1": py - 30, "x2": px + 5, "y2": py, "conf": 0.9,
                               "torso_l": 120.0, "torso_a": 100.0 if team == "A" else 180.0, "torso_b": 150.0,
                               "track_id": track_id, "foot_x": px, "foot_y": py, "in_pitch": True,
                               "role": role, "team": team})
    state = pl.DataFrame(state_rows, schema=schemas.STATE).sort("frame_id", "track_id")
    tracks = pl.DataFrame(track_rows, schema=schemas.TRACKS).sort("frame_id", "track_id")
    return state, tracks
```

- [ ] **Step 2: Проверить, что модуль импортируется и данные валидны**

Run: `.venv/bin/python -c "import sys; sys.path.insert(0, 'tests'); from report_fixtures import synthetic_match; s, t = synthetic_match(); print(s.height, t.height, s['speed'].max())"`
Expected: `4000 4000 6.0`.

- [ ] **Step 3: Commit**

```bash
git add tests/report_fixtures.py
git commit -m "Синтетический матч для тестов отчёта"
```

---

### Task 4: Скорости и бег быстрее 4 м/с

**Files:**
- Create: `src/aifootball/analytics/report_data.py`
- Test: `tests/test_report_data.py`

- [ ] **Step 1: Тесты**

`tests/test_report_data.py`:

```python
import numpy as np
import pytest

from aifootball.analytics.report_data import hsr_distance, segments, sustained_max_speed


def _run(speeds, dt=0.1):
    ts = np.arange(len(speeds)) * dt
    speed = np.asarray(speeds, dtype=float)
    x = np.concatenate([[0.0], np.cumsum(speed[1:] * dt)])
    return ts, x, np.zeros_like(x), speed


def test_segments_split_on_gap():
    ts = np.array([0.0, 0.1, 0.2, 3.0, 3.1])
    assert [(s.start, s.stop) for s in segments(ts)] == [(0, 3), (3, 5)]


def test_hsr_counts_only_fast_steps():
    ts, x, y, speed = _run([3.0] * 20 + [6.0] * 20 + [3.0] * 20)
    assert hsr_distance(ts, x, y, speed) == pytest.approx(6.0 * 0.1 * 20, abs=0.01)


def test_sustained_speed_ignores_single_spike_and_cap():
    ts, _, _, speed = _run([3.0] * 20 + [9.5] + [3.0] * 20 + [6.0] * 10 + [10.0] * 10)
    # одиночный пик 9.5 сглаживается, 10.0 — упор в фильтр, отбрасывается
    assert sustained_max_speed(ts, speed, cap=10.0) == pytest.approx(6.0)


def test_sustained_speed_none_when_only_capped():
    ts, _, _, speed = _run([10.0] * 20)
    assert sustained_max_speed(ts, speed, cap=10.0) is None
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/test_report_data.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aifootball.analytics.report_data'`

- [ ] **Step 3: Реализация**

`src/aifootball/analytics/report_data.py`:

```python
"""Цифры отчёта по матчу: обзор команд, трети, тепловые карты, ход матча, игроки, моменты.

Только данные — никакого HTML. Всё считается внутри периода (весь матч / тайм).
Спецификация: docs/specs/2026-10-13-match-report-design.md.
"""

import numpy as np
import polars as pl

from aifootball.state.smooth import MAX_GAP_S

HSR_MS = 4.0  # бег быстрее этого — «высокоинтенсивный»; стартовое значение, см. спецификацию
SUSTAIN_S = 0.5  # устойчивая скорость: медиана за это окно, одиночные пики не в счёт


def segments(ts: np.ndarray) -> list[slice]:
    """Непрерывные куски трека: разрыв больше MAX_GAP_S начинает новый."""
    if len(ts) == 0:
        return []
    cuts = (np.flatnonzero(np.diff(ts) > MAX_GAP_S) + 1).tolist()
    bounds = [0, *cuts, len(ts)]
    return [slice(a, b) for a, b in zip(bounds, bounds[1:])]


def hsr_distance(ts: np.ndarray, x: np.ndarray, y: np.ndarray, speed: np.ndarray) -> float:
    """Метры на шагах, где скорость в конце шага выше HSR_MS (через разрыв трека не считаем)."""
    if len(ts) < 2:
        return 0.0
    steps = np.hypot(np.diff(x), np.diff(y))
    fast = (np.diff(ts) <= MAX_GAP_S) & (speed[1:] > HSR_MS)
    return round(float(steps[fast].sum()), 2)


def sustained_speeds(ts: np.ndarray, speed: np.ndarray, cap: float) -> tuple[np.ndarray, np.ndarray]:
    """(время середины окна, медиана скорости за SUSTAIN_S); окна на пределе фильтра cap выброшены."""
    if len(ts) < 2:
        return np.array([]), np.array([])
    step = float(np.median(np.diff(ts)))
    n = max(1, int(round(SUSTAIN_S / step))) if step > 0 else 1
    times, values = [], []
    for seg in segments(ts):
        s, t = speed[seg], ts[seg]
        if len(s) < n:
            continue
        med = np.median(np.lib.stride_tricks.sliding_window_view(s, n), axis=1)
        mid = np.lib.stride_tricks.sliding_window_view(t, n)[:, n // 2]
        keep = med < cap - 1e-3
        times.append(mid[keep])
        values.append(med[keep])
    if not values:
        return np.array([]), np.array([])
    return np.concatenate(times), np.concatenate(values)


def sustained_max_speed(ts: np.ndarray, speed: np.ndarray, cap: float) -> float | None:
    _, values = sustained_speeds(ts, speed, cap)
    return round(float(values.max()), 2) if values.size else None
```

- [ ] **Step 4: Прогнать**

Run: `.venv/bin/python -m pytest tests/test_report_data.py -q`
Expected: PASS (4 теста).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/analytics/report_data.py tests/test_report_data.py
git commit -m "Отчёт: устойчивая скорость и бег быстрее 4 м/с"
```

---

### Task 5: Направление, вратари по таймам, поворот поля, трети

**Files:**
- Modify: `src/aifootball/analytics/report_data.py`
- Test: `tests/test_report_data.py`

- [ ] **Step 1: Тесты** (дописать в конец `tests/test_report_data.py`)

```python
import sys
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
from report_fixtures import LENGTH, synthetic_match  # noqa: E402

from aifootball.analytics.report_data import assign_goalkeeper_teams, orient, thirds_share  # noqa: E402


def _swap_halves(state, at):
    """После at секунд команды меняются воротами: x -> LENGTH - x."""
    return state.with_columns(
        x_m=pl.when(pl.col("ts") >= at).then(LENGTH - pl.col("x_m")).otherwise(pl.col("x_m"))
    )


def test_goalkeeper_team_follows_side_in_each_half():
    state, _ = synthetic_match()
    state = _swap_halves(state, 100).with_columns(
        team=pl.when(pl.col("role") == "goalkeeper").then(pl.lit("A")).otherwise(pl.col("team")))
    fixed = assign_goalkeeper_teams(state, [(0.0, 100.0), (100.0, 200.0)], LENGTH)
    gk = fixed.filter(pl.col("track_id") == 9)  # вратарь B: в 1-м тайме слева, во 2-м справа
    assert gk.filter(pl.col("ts") < 100)["team"].unique().to_list() == ["B"]
    assert gk.filter(pl.col("ts") >= 100)["team"].unique().to_list() == ["B"]


def test_orient_puts_own_goal_left_in_both_halves():
    state, _ = synthetic_match(sprint=False)
    state = _swap_halves(state, 100)
    oriented, ok = orient(state, [(0.0, 100.0), (100.0, 200.0)], LENGTH)
    assert ok
    a = oriented.filter((pl.col("team") == "A") & (pl.col("role") == "player"))
    # A защищает правые ворота в 1-м тайме и левые во 2-м; после поворота всегда держится слева (x ≈ 11)
    assert a.filter(pl.col("ts") < 100)["x_m"].median() == pytest.approx(11.0, abs=1.0)
    assert a.filter(pl.col("ts") >= 100)["x_m"].median() == pytest.approx(11.0, abs=1.0)


def test_thirds_share_on_oriented_state():
    state, _ = synthetic_match(sprint=False)
    oriented, _ = orient(state, [(0.0, 200.0)], LENGTH)
    shares = thirds_share(oriented, LENGTH)
    # центр команды — x = 11 ± 1.5 м < 40/3: всё время в своей трети
    assert shares == {"A": [100, 0, 0], "B": [100, 0, 0]}
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/test_report_data.py -q`
Expected: FAIL — `ImportError: cannot import name 'assign_goalkeeper_teams'`

- [ ] **Step 3: Реализация** (дописать в `src/aifootball/analytics/report_data.py`)

В импорты добавить:

```python
from aifootball.analytics.periods import in_period
from aifootball.perception.teams import defending_sides

TEAMS = ("A", "B")
```

Функции:

```python
def assign_goalkeeper_teams(state: pl.DataFrame, spans, length_m: float) -> pl.DataFrame:
    """Команда вратаря в каждом тайме — защищающая ворота, у которых он стоит (команды меняются воротами)."""
    parts = []
    for span in spans:
        part = in_period(state, [span])
        left, right = defending_sides(part)
        parts.append(part.with_columns(
            team=pl.when(pl.col("role") != "goalkeeper").then(pl.col("team"))
            .when(pl.col("x_m") < length_m / 2).then(pl.lit(left)).otherwise(pl.lit(right))
        ))
    return pl.concat(parts) if parts else state.clear()


def orient(state: pl.DataFrame, spans, length_m: float) -> tuple[pl.DataFrame, bool]:
    """Поворачивает поле так, чтобы свои ворота каждой команды были слева (x = 0) в каждом тайме.

    Возвращает (повёрнутые строки, удалось ли определить направление во всех таймах).
    """
    parts, ok = [], True
    for span in spans:
        part = in_period(state, [span])
        has_both = part.filter((pl.col("role") == "player") & pl.col("team").is_in(TEAMS))["team"].n_unique() == 2
        if not has_both:
            ok = False
            parts.append(part)
            continue
        left, _ = defending_sides(part)
        parts.append(part.with_columns(
            x_m=pl.when(pl.col("team") == left).then(pl.col("x_m")).otherwise(length_m - pl.col("x_m"))
        ))
    return (pl.concat(parts) if parts else state.clear()), ok


def thirds_share(oriented: pl.DataFrame, length_m: float) -> dict:
    """Проценты времени, когда центр команды в своей / средней / чужой трети (свои ворота слева)."""
    out = {}
    for team in TEAMS:
        centers = (
            oriented.filter((pl.col("role") == "player") & (pl.col("team") == team))
            .group_by("frame_id").agg(x=pl.col("x_m").mean(), n=pl.len())
            .filter(pl.col("n") >= 2)["x"].to_numpy()
        )
        if centers.size == 0:
            out[team] = None
            continue
        idx = np.clip((centers / (length_m / 3)).astype(int), 0, 2)
        counts = np.bincount(idx, minlength=3)
        out[team] = [int(round(c / counts.sum() * 100)) for c in counts]
    return out
```

- [ ] **Step 4: Прогнать**

Run: `.venv/bin/python -m pytest tests/test_report_data.py -q`
Expected: PASS (7 тестов).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/analytics/report_data.py tests/test_report_data.py
git commit -m "Отчёт: направление атаки, вратари по таймам, трети"
```

---

### Task 6: Обзор команд и ход матча

**Files:**
- Modify: `src/aifootball/analytics/report_data.py`
- Test: `tests/test_report_data.py`

- [ ] **Step 1: Тесты** (дописать)

```python
from aifootball.analytics.report_data import series, team_overview  # noqa: E402


def test_team_overview_numbers():
    state, _ = synthetic_match(sprint=False)
    oriented, _ = orient(state, [(0.0, 200.0)], LENGTH)
    ov = team_overview(state, oriented, LENGTH, 20.0, cap=10.0, period_s=200.0)
    a = ov["A"]
    # 4 игрока бегут по синусоиде амплитудой 3 м с периодом 20 с: 12 м за период, 0.6 м/с = 36 м/мин
    assert a["m_per_min"] == pytest.approx(36.0, rel=0.05)
    assert a["distance_m"] == pytest.approx(4 * 0.6 * 199.5, rel=0.05)
    assert a["hsr_m"] == 0.0 and a["sprints"] == 0
    assert a["width_m"] == pytest.approx(12.0, abs=0.1)  # игроки на y = 4, 8, 12, 16
    assert a["low_data"] is False
    assert len(a["heatmap_s"]) == 40 and len(a["heatmap_s"][0]) == 20


def test_low_data_flag():
    state, _ = synthetic_match(sprint=False)
    one = state.filter(pl.col("track_id").is_in([11, 1]))  # по одному полевому игроку
    oriented, _ = orient(one, [(0.0, 200.0)], LENGTH)
    assert team_overview(one, oriented, LENGTH, 20.0, cap=10.0, period_s=200.0)["A"]["low_data"] is True


def test_series_by_five_minutes():
    state, _ = synthetic_match(seconds=600, sprint=False)
    s = series(state, [(0.0, 600.0)])
    assert s["start_min"] == [0.0, 5.0]
    assert s["A"][0] == pytest.approx(36.0, rel=0.05) and s["B"][1] == pytest.approx(36.0, rel=0.05)
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/test_report_data.py -q`
Expected: FAIL — `ImportError: cannot import name 'series'`

- [ ] **Step 3: Реализация** (дописать)

В импорты:

```python
from aifootball.analytics.metrics import HEATMAP_CELL_M, _heatmap, _sampling_step, compute_metrics
```

Константы (к остальным в начале модуля):

```python
SERIES_BIN_S = 300.0  # ход матча по 5-минутным отрезкам
LOW_DATA_SHARE = 0.5  # меньше половины от «период × 4 полевых» — пометка «мало данных»
FIELD_PLAYERS = 4
```

Функции:

```python
def team_overview(state: pl.DataFrame, oriented: pl.DataFrame, length_m: float, width_m: float,
                  cap: float, period_s: float) -> dict:
    """Строки сравнения команд по полевым игрокам; тепловая карта — по повёрнутому полю."""
    field = state.filter(pl.col("role") == "player")
    metrics = compute_metrics(field, length_m, width_m)
    oriented_field = oriented.filter(pl.col("role") == "player")
    sample_s = _sampling_step(field) if not field.is_empty() else 0.0
    out = {}
    for team in TEAMS:
        t = metrics["teams"][team]
        g = field.filter(pl.col("team") == team).sort("track_id", "ts")
        hsr = sum(
            hsr_distance(tr["ts"].to_numpy(), tr["x_m"].to_numpy(), tr["y_m"].to_numpy(), tr["speed"].to_numpy())
            for _, tr in g.group_by("track_id", maintain_order=True)
        )
        width, depth = _shape(g)
        observed = t["observed_s"]
        out[team] = {
            "distance_m": t["distance_m"],
            "m_per_min": round(t["distance_m"] / observed * 60, 1) if observed > 0 else 0.0,
            "hsr_m": round(hsr, 1),
            "sprints": t["sprints_count"],
            "compactness_m2": t["compactness_m2"],
            "width_m": width,
            "depth_m": depth,
            "observed_s": observed,
            "low_data": bool(observed < LOW_DATA_SHARE * FIELD_PLAYERS * period_s),
            "heatmap_s": _heatmap(oriented_field.filter(pl.col("team") == team), length_m, width_m, sample_s),
        }
    return out


def _shape(team_state: pl.DataFrame) -> tuple[float, float]:
    """(ширина поперёк поля, глубина вдоль поля) — средний размах по кадрам, где ≥ 3 игрока команды."""
    per = (
        team_state.group_by("frame_id")
        .agg(n=pl.len(), dx=pl.col("x_m").max() - pl.col("x_m").min(), dy=pl.col("y_m").max() - pl.col("y_m").min())
        .filter(pl.col("n") >= 3)
    )
    if per.is_empty():
        return 0.0, 0.0
    return round(float(per["dy"].mean()), 1), round(float(per["dx"].mean()), 1)


def _steps(state: pl.DataFrame) -> pl.DataFrame:
    """Шаги треков: ts конца шага, команда, длина шага, dt; через разрыв трека шагов нет."""
    return (
        state.sort("track_id", "ts")
        .with_columns(
            dt=pl.col("ts").diff().over("track_id"),
            step=(pl.col("x_m").diff().over("track_id") ** 2 + pl.col("y_m").diff().over("track_id") ** 2).sqrt(),
        )
        .filter(pl.col("dt").is_not_null() & (pl.col("dt") <= MAX_GAP_S))
    )


def series(state: pl.DataFrame, spans) -> dict:
    """Метров в минуту на полевого игрока по отрезкам SERIES_BIN_S; start_min — от начала периода."""
    steps = _steps(state.filter(pl.col("role") == "player"))
    out = {"bin_s": SERIES_BIN_S, "start_min": [], "A": [], "B": []}
    offset = 0.0
    for start, end in spans:
        for b0 in np.arange(start, end, SERIES_BIN_S):
            chunk = steps.filter((pl.col("ts") >= b0) & (pl.col("ts") < min(b0 + SERIES_BIN_S, end)))
            out["start_min"].append(round((offset + b0 - start) / 60, 1))
            for team in TEAMS:
                c = chunk.filter(pl.col("team") == team)
                observed = float(c["dt"].sum())
                out[team].append(round(float(c["step"].sum()) / observed * 60, 1) if observed > 0 else None)
        offset += end - start
    return out
```

- [ ] **Step 4: Прогнать**

Run: `.venv/bin/python -m pytest tests/test_report_data.py -q`
Expected: PASS (10 тестов).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/analytics/report_data.py tests/test_report_data.py
git commit -m "Отчёт: обзор команд, ширина и глубина, ход матча по 5 минут"
```

---

### Task 7: Игроки и моменты

**Files:**
- Modify: `src/aifootball/analytics/report_data.py`
- Test: `tests/test_report_data.py`

- [ ] **Step 1: Тесты** (дописать)

```python
from aifootball.analytics.report_data import moments, player_labels, players_table, thumb_request  # noqa: E402


def test_player_labels_by_team_and_first_seen():
    state, _ = synthetic_match()
    short = state.filter(~((pl.col("track_id") == 4) & (pl.col("ts") > 30)))  # трек 4 — всего 30 с
    labels = player_labels(short, min_s=60.0)
    assert labels[1] == "Игрок 1" and labels[11] == "Игрок 1"
    assert labels[9] == "Вратарь" and labels[19] == "Вратарь"
    assert 4 not in labels


def test_players_table_rows():
    state, _ = synthetic_match()
    oriented, _ = orient(state, [(0.0, 200.0)], LENGTH)
    rows = players_table(state, oriented, player_labels(state, 60.0), LENGTH, 20.0, cap=10.0)
    a1 = next(r for r in rows if r["track_id"] == 11)
    assert a1["team"] == "A" and a1["label"] == "Игрок 1"
    assert a1["hsr_m"] == pytest.approx(21.0, abs=1.5)  # 7 шагов по 3 м со скоростью 6 м/с
    assert a1["vmax_ms"] == pytest.approx(6.0, abs=0.3)
    assert len(rows) == 10


def test_thumb_request_middle_of_longest_segment():
    _, tracks = synthetic_match()
    req = thumb_request(tracks, 11)
    assert req["kind"] == "thumb" and 190 <= req["frame_id"] <= 210
    assert len(req["box"]) == 4


def test_moments_find_sprint():
    state, tracks = synthetic_match()
    labels = player_labels(state, 60.0)
    found = {m["kind"]: m for m in moments(state, tracks, labels, [(0.0, 200.0)], cap=10.0)}
    assert found["sprint"]["track_id"] == 11
    assert 20.0 <= found["sprint"]["ts"] <= 24.0
    assert found["speed"]["track_id"] == 11
    assert {"sprint", "speed", "minute_A", "minute_B"} <= set(found)
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/test_report_data.py -q`
Expected: FAIL — `ImportError: cannot import name 'moments'`

- [ ] **Step 3: Реализация** (дописать)

В импорты:

```python
from aifootball.analytics.metrics import SPRINT_MIN_DURATION_S, SPRINT_THRESHOLD_MS
```

Константы:

```python
MIN_PLAYER_S = 60.0  # трек короче — только в командных суммах, в таблице игроков его нет
BUSY_WINDOW_S = 60.0  # «самая беговая минута»
```

Функции:

```python
def _observed(state: pl.DataFrame) -> pl.DataFrame:
    """По треку: секунды наблюдения, первое появление, команда (чаще всего), роль."""
    return (
        _steps(state).group_by("track_id").agg(observed_s=pl.col("dt").sum())
        .join(state.group_by("track_id").agg(
            first_ts=pl.col("ts").min(), team=pl.col("team").mode().first(), role=pl.col("role").first()),
            on="track_id")
    )


def player_labels(state: pl.DataFrame, min_s: float = MIN_PLAYER_S) -> dict[int, str]:
    """Имена строк таблицы: «Игрок N» по порядку появления внутри команды, «Вратарь», «Вратарь 2»…"""
    obs = _observed(state.filter(pl.col("role").is_in(["player", "goalkeeper"]) & pl.col("team").is_in(TEAMS)))
    labels, players, keepers = {}, {t: 0 for t in TEAMS}, {t: 0 for t in TEAMS}
    for row in obs.filter(pl.col("observed_s") >= min_s).sort("first_ts", "track_id").iter_rows(named=True):
        team = row["team"]
        if row["role"] == "goalkeeper":
            keepers[team] += 1
            labels[row["track_id"]] = "Вратарь" if keepers[team] == 1 else f"Вратарь {keepers[team]}"
        else:
            players[team] += 1
            labels[row["track_id"]] = f"Игрок {players[team]}"
    return labels


def players_table(state: pl.DataFrame, oriented: pl.DataFrame, labels: dict[int, str],
                  length_m: float, width_m: float, cap: float) -> list[dict]:
    """Строки таблицы игроков периода: треки из labels, наблюдавшиеся в периоде ≥ MIN_PLAYER_S."""
    metrics = compute_metrics(state, length_m, width_m)["tracks"]
    sample_s = _sampling_step(state) if not state.is_empty() else 0.0
    rows = []
    for track_id, label in labels.items():
        m = metrics.get(str(track_id))
        if m is None or m["observed_s"] < MIN_PLAYER_S:
            continue
        g = state.filter(pl.col("track_id") == track_id).sort("ts")
        ts, speed = g["ts"].to_numpy(), g["speed"].to_numpy()
        rows.append({
            "track_id": track_id,
            "label": label,
            "team": g["team"].mode().first(),
            "role": m["role"],
            "observed_s": m["observed_s"],
            "distance_m": m["distance_m"],
            "m_per_min": m["distance_per_min"],
            "hsr_m": hsr_distance(ts, g["x_m"].to_numpy(), g["y_m"].to_numpy(), speed),
            "sprints": m["sprints_count"],
            "vmax_ms": sustained_max_speed(ts, speed, cap),
            "heatmap_s": _heatmap(oriented.filter(pl.col("track_id") == track_id), length_m, width_m, sample_s),
        })
    return sorted(rows, key=lambda r: (r["team"], r["role"] != "player", -r["observed_s"]))


def thumb_request(tracks: pl.DataFrame, track_id: int) -> dict | None:
    """Кадр для миниатюры: середина самого длинного непрерывного куска трека на поле."""
    g = tracks.filter((pl.col("track_id") == track_id) & pl.col("in_pitch")).sort("ts")
    if g.is_empty():
        return None
    longest = max(segments(g["ts"].to_numpy()), key=lambda s: s.stop - s.start)
    row = g.row(longest.start + (longest.stop - longest.start) // 2, named=True)
    return {"kind": "thumb", "frame_id": row["frame_id"], "box": [row["x1"], row["y1"], row["x2"], row["y2"]]}


def _still(tracks: pl.DataFrame, ts: float, track_id: int | None) -> dict:
    """Стоп-кадр на момент ts; с track_id — с рамкой игрока."""
    if track_id is not None:
        g = tracks.filter(pl.col("track_id") == track_id)
        if not g.is_empty():
            row = g.with_columns(d=(pl.col("ts") - ts).abs()).sort("d").row(0, named=True)
            return {"kind": "still", "frame_id": row["frame_id"], "box": [row["x1"], row["y1"], row["x2"], row["y2"]]}
    row = tracks.with_columns(d=(pl.col("ts") - ts).abs()).sort("d").row(0, named=True)
    return {"kind": "still", "frame_id": row["frame_id"], "box": None}


def moments(state: pl.DataFrame, tracks: pl.DataFrame, labels: dict[int, str], spans, cap: float) -> list[dict]:
    """Самый длинный спринт, самая высокая устойчивая скорость, самая беговая минута каждой команды."""
    found = []
    best_sprint, best_speed = None, None
    for (track_id,), g in state.filter(pl.col("role") == "player").sort("track_id", "ts").group_by(
            "track_id", maintain_order=True):
        ts, x, y, speed = (g[c].to_numpy() for c in ("ts", "x_m", "y_m", "speed"))
        team = g["team"].mode().first()
        for seg in segments(ts):
            fast = speed[seg] >= SPRINT_THRESHOLD_MS
            padded = np.concatenate([[0], fast.astype(int), [0]])
            edges = np.flatnonzero(np.diff(padded))
            for a, b in zip(edges[::2], edges[1::2]):
                i0, i1 = seg.start + a, seg.start + b
                if ts[i1 - 1] - ts[i0] < SPRINT_MIN_DURATION_S:
                    continue
                dist = float(np.hypot(np.diff(x[i0:i1]), np.diff(y[i0:i1])).sum())
                if best_sprint is None or dist > best_sprint[0]:
                    best_sprint = (dist, track_id, team, float(ts[i0]))
        times, values = sustained_speeds(ts, speed, cap)
        if values.size and (best_speed is None or values.max() > best_speed[0]):
            k = int(np.argmax(values))
            best_speed = (float(values[k]), track_id, team, float(times[k]))

    def label(track_id):
        return labels.get(track_id, f"трек {track_id}")

    if best_sprint:
        dist, track_id, team, ts0 = best_sprint
        found.append({"kind": "sprint", "title": "Самый длинный спринт", "value": f"{dist:.0f} м",
                      "ts": ts0, "team": team, "track_id": track_id, "label": label(track_id),
                      "still": _still(tracks, ts0, track_id)})
    if best_speed:
        v, track_id, team, ts0 = best_speed
        found.append({"kind": "speed", "title": "Самая высокая скорость", "value": f"{v:.1f} м/с",
                      "ts": ts0, "team": team, "track_id": track_id, "label": label(track_id),
                      "still": _still(tracks, ts0, track_id)})

    steps = _steps(state.filter(pl.col("role") == "player"))
    for team in TEAMS:
        per_s = (
            steps.filter(pl.col("team") == team)
            .with_columns(sec=pl.col("ts").floor())
            .group_by("sec").agg(step=pl.col("step").sum(), dt=pl.col("dt").sum())
        )
        best = None
        for start, end in spans:
            grid = pl.DataFrame({"sec": np.arange(np.floor(start), np.floor(end))}).join(per_s, on="sec", how="left").fill_null(0)
            n = int(BUSY_WINDOW_S)
            if grid.height < n:
                continue
            step_w = np.lib.stride_tricks.sliding_window_view(grid["step"].to_numpy(), n).sum(axis=1)
            dt_w = np.lib.stride_tricks.sliding_window_view(grid["dt"].to_numpy(), n).sum(axis=1)
            ok = dt_w >= 2 * BUSY_WINDOW_S  # в среднем хотя бы 2 игрока в кадре
            if not ok.any():
                continue
            rate = np.where(ok, step_w / np.maximum(dt_w, 1e-9) * 60, -1)
            k = int(np.argmax(rate))
            if best is None or rate[k] > best[0]:
                best = (float(rate[k]), float(grid["sec"][k]))
        if best:
            found.append({"kind": f"minute_{team}", "title": "Самая беговая минута", "value": f"{best[0]:.0f} м/мин",
                          "ts": best[1], "team": team, "track_id": None, "label": None,
                          "still": _still(tracks, best[1] + BUSY_WINDOW_S / 2, None)})
    return found
```

- [ ] **Step 4: Прогнать**

Run: `.venv/bin/python -m pytest tests/test_report_data.py -q`
Expected: PASS (14 тестов).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/analytics/report_data.py tests/test_report_data.py
git commit -m "Отчёт: таблица игроков, миниатюры, моменты"
```

---

### Task 8: Сборка цифр отчёта

**Files:**
- Modify: `src/aifootball/analytics/report_data.py`
- Test: `tests/test_report_data.py`

- [ ] **Step 1: Тест** (дописать)

```python
import json  # noqa: E402

from aifootball.analytics.report_data import build_report, team_colors  # noqa: E402


class _Venue:
    length_m, width_m, max_physical_speed = LENGTH, 20.0, 10.0


def test_build_report_structure_and_json():
    state, tracks = synthetic_match()
    data = build_report(state, tracks, _Venue(), [(0.0, 100.0), (100.0, 200.0)],
                        {"A": "Зелёные", "B": "Оранжевые"}, video_s=200.0)
    assert [p["key"] for p in data["periods"]] == ["all", "h1", "h2"]
    assert data["match"]["halves_found"] is True and data["match"]["processed_s"] == 200.0
    p = data["periods"][0]
    assert set(p) >= {"teams", "thirds", "series", "players", "moments"}
    assert "11" in data["thumbs"]
    json.dumps(data)  # всё сериализуется


def test_team_colors_fallback_and_hex():
    _, tracks = synthetic_match()
    colors = team_colors(tracks)
    assert set(colors) == {"A", "B"} and all(c.startswith("#") and len(c) == 7 for c in colors.values())
    same = tracks.with_columns(torso_a=pl.lit(100.0))
    assert team_colors(same) == {"A": "#1fae4b", "B": "#f07a1a"}
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/test_report_data.py -q`
Expected: FAIL — `ImportError: cannot import name 'build_report'`

- [ ] **Step 3: Реализация** (дописать)

В импорты:

```python
import cv2

from aifootball.analytics.periods import make_periods
```

Константы:

```python
FALLBACK_COLORS = {"A": "#1fae4b", "B": "#f07a1a"}
MIN_COLOR_DIST = 30.0  # цвета формы ближе — неразличимы на полосках, берём зелёный и оранжевый
```

Функции:

```python
def team_colors(tracks: pl.DataFrame) -> dict[str, str]:
    """Цвет команды для полосок — медианный цвет формы, затемнённый для белого фона."""
    lab = {}
    for team in TEAMS:
        g = tracks.filter((pl.col("role") == "player") & (pl.col("team") == team) & pl.col("torso_a").is_not_nan())
        if g.is_empty():
            return dict(FALLBACK_COLORS)
        lab[team] = [float(g[c].median()) for c in ("torso_l", "torso_a", "torso_b")]
    if np.hypot(lab["A"][1] - lab["B"][1], lab["A"][2] - lab["B"][2]) < MIN_COLOR_DIST:
        return dict(FALLBACK_COLORS)
    out = {}
    for team, (l, a, b) in lab.items():
        bgr = cv2.cvtColor(np.uint8([[[min(l, 170.0), a, b]]]), cv2.COLOR_LAB2BGR)[0, 0]
        out[team] = "#{:02x}{:02x}{:02x}".format(int(bgr[2]), int(bgr[1]), int(bgr[0]))
    return out


def ball_summary(ball_state: pl.DataFrame, state: pl.DataFrame) -> dict:
    """Владение и передачи за период — только по --with-ball, с замеренной точностью."""
    from aifootball.perception.ball import compute_possession, detect_passes

    return {
        "possession": compute_possession(ball_state, state),
        "passes": detect_passes(ball_state, state),
        "caveat": "Приблизительно: по ручным журналам двух отрезков находится около половины передач, "
                  "из найденных верны около 60%.",
    }


def build_report(state: pl.DataFrame, tracks: pl.DataFrame, venue, spans, team_names: dict,
                 video_s: float, ball_state: pl.DataFrame | None = None) -> dict:
    """Все цифры отчёта; venue нужен только для length_m, width_m, max_physical_speed."""
    length_m, width_m, cap = venue.length_m, venue.width_m, venue.max_physical_speed
    state = assign_goalkeeper_teams(in_period(state, spans), spans, length_m)
    labels = player_labels(state)
    thumbs = {str(tid): req for tid in labels if (req := thumb_request(tracks, tid)) is not None}

    periods = []
    for p in make_periods(spans):
        part = in_period(state, p.spans)
        oriented, oriented_ok = orient(part, p.spans, length_m)
        entry = {
            "key": p.key,
            "name": p.name,
            "spans": [list(s) for s in p.spans],
            "duration_s": round(p.duration_s, 1),
            "teams": team_overview(part, oriented, length_m, width_m, cap, p.duration_s),
            "thirds": thirds_share(oriented, length_m) if oriented_ok else {t: None for t in TEAMS},
            "series": series(part, p.spans),
            "players": players_table(part, oriented, labels, length_m, width_m, cap),
            "moments": moments(part, tracks, labels, p.spans, cap),
        }
        if ball_state is not None:
            entry["ball"] = ball_summary(in_period(ball_state, p.spans), part)
        periods.append(entry)

    return {
        "schema_version": "1",
        "match": {
            "teams": team_names,
            "colors": team_colors(tracks),
            "video_s": round(video_s, 1),
            "processed_s": round(sum(end - start for start, end in spans), 1),
            "halves_found": len(spans) == 2,
        },
        "pitch": {"length_m": length_m, "width_m": width_m, "cell_m": HEATMAP_CELL_M},
        "thumbs": thumbs,
        "periods": periods,
    }
```

- [ ] **Step 4: Прогнать**

Run: `.venv/bin/python -m pytest tests/test_report_data.py -q`
Expected: PASS (16 тестов).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/analytics/report_data.py tests/test_report_data.py
git commit -m "Отчёт: сборка цифр по периодам, цвета команд, мяч по флагу"
```

---

### Task 9: SVG — поле, тепловая карта, трети, график

**Files:**
- Create: `src/aifootball/report/__init__.py` (пустой)
- Create: `src/aifootball/report/svg.py`
- Test: `tests/test_report_svg.py`

- [ ] **Step 1: Тесты**

`tests/test_report_svg.py`:

```python
import xml.etree.ElementTree as ET

from aifootball.report.svg import heatmap_svg, line_chart_svg, thirds_svg


def _parse(svg):
    return ET.fromstring(svg)  # падает, если SVG не XML


def test_heatmap_svg_is_xml_with_cells():
    grid = [[0.0] * 20 for _ in range(40)]
    grid[5][5] = 10.0
    root = _parse(heatmap_svg(grid, 40.0, 20.0, "#1fae4b"))
    rects = [e for e in root.iter() if e.tag.endswith("rect") and e.get("class") == "cell"]
    assert len(rects) == 1


def test_thirds_svg_has_labels():
    svg = thirds_svg([30, 44, 26], 40.0, 20.0, "#f07a1a")
    _parse(svg)
    assert "30%" in svg and "44%" in svg and "26%" in svg


def test_line_chart_skips_missing_points():
    svg = line_chart_svg([0.0, 5.0, 10.0], {"A": [100.0, None, 90.0], "B": [95.0, 97.0, 99.0]},
                         {"A": "#1fae4b", "B": "#f07a1a"})
    root = _parse(svg)
    lines = [e for e in root.iter() if e.tag.endswith("polyline")]
    assert len(lines) == 3  # у A пропуск рвёт линию на две
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/test_report_svg.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aifootball.report'`

- [ ] **Step 3: Реализация**

`src/aifootball/report/__init__.py` — пустой файл.

`src/aifootball/report/svg.py`:

```python
"""SVG для отчёта: поле с разметкой футзала, тепловая карта, трети, линейный график.

Координаты поля в SVG — метры (viewBox), свои ворота команды слева.
"""

from html import escape

LINE = "#ffffff"
GRASS = "#e9f3ea"
PAD = 0.6  # поля вокруг площадки, м


def _pitch_lines(length_m: float, width_m: float) -> str:
    """Разметка: контур, средняя линия, центральный круг 3 м, штрафные дуги 6 м, ворота 3 м."""
    cy = width_m / 2
    parts = [
        f'<rect x="0" y="0" width="{length_m}" height="{width_m}" fill="none" stroke="{LINE}" stroke-width="0.15"/>',
        f'<line x1="{length_m / 2}" y1="0" x2="{length_m / 2}" y2="{width_m}" stroke="{LINE}" stroke-width="0.15"/>',
        f'<circle cx="{length_m / 2}" cy="{cy}" r="3" fill="none" stroke="{LINE}" stroke-width="0.15"/>',
    ]
    for gx, sign in ((0.0, 1), (length_m, -1)):
        parts.append(f'<path d="M {gx} {cy - 6} A 6 6 0 0 {1 if sign > 0 else 0} {gx} {cy + 6}" '
                     f'fill="none" stroke="{LINE}" stroke-width="0.15"/>')
        parts.append(f'<line x1="{gx}" y1="{cy - 1.5}" x2="{gx}" y2="{cy + 1.5}" stroke="#555" stroke-width="0.5"/>')
    return "".join(parts)


def _svg(length_m: float, width_m: float, body: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="pitch" '
            f'viewBox="{-PAD} {-PAD} {length_m + 2 * PAD} {width_m + 2 * PAD}">'
            f'<rect x="{-PAD}" y="{-PAD}" width="{length_m + 2 * PAD}" height="{width_m + 2 * PAD}" fill="{GRASS}"/>'
            f'{body}{_pitch_lines(length_m, width_m)}</svg>')


def heatmap_svg(grid: list[list[float]], length_m: float, width_m: float, color: str, cell_m: float = 1.0) -> str:
    """Клетки с прозрачностью по доле от максимума; grid[ix][iy] — секунды в клетке."""
    peak = max((v for col in grid for v in col), default=0.0)
    cells = []
    if peak > 0:
        for ix, col in enumerate(grid):
            for iy, v in enumerate(col):
                if v > 0:
                    cells.append(f'<rect class="cell" x="{ix * cell_m}" y="{iy * cell_m}" width="{cell_m}" '
                                 f'height="{cell_m}" fill="{color}" fill-opacity="{0.15 + 0.85 * v / peak:.2f}"/>')
    return _svg(length_m, width_m, "".join(cells))


def thirds_svg(shares: list[int], length_m: float, width_m: float, color: str) -> str:
    """Три зоны (своя, средняя, чужая треть) с яркостью по доле времени и подписью «NN%»."""
    third = length_m / 3
    peak = max(shares) or 1
    body = []
    for k, share in enumerate(shares):
        x = k * third
        body.append(f'<rect x="{x}" y="0" width="{third}" height="{width_m}" fill="{color}" '
                    f'fill-opacity="{0.12 + 0.6 * share / peak:.2f}"/>')
        body.append(f'<rect x="{x + third / 2 - 3}" y="{width_m / 2 - 1.8}" width="6" height="3.6" rx="0.6" fill="#fff"/>')
        body.append(f'<text x="{x + third / 2}" y="{width_m / 2 + 1.0}" font-size="2.6" font-weight="700" '
                    f'text-anchor="middle" fill="#111">{share}%</text>')
    return _svg(length_m, width_m, "".join(body))


def line_chart_svg(x_values: list[float], series: dict[str, list[float | None]], colors: dict[str, str],
                   width: int = 320, height: int = 120) -> str:
    """Линии по командам; пропуск (None) рвёт линию. Подписи: минуты по x, значения по y."""
    values = [v for s in series.values() for v in s if v is not None]
    if not values or not x_values:
        return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}"></svg>'
    lo, hi = min(values) * 0.9, max(values) * 1.1 or 1.0
    x0, x1 = min(x_values), max(x_values) or 1.0
    left, right, top, bottom = 34, 8, 8, 18

    def px(x, y):
        fx = left + (x - x0) / ((x1 - x0) or 1) * (width - left - right)
        fy = top + (1 - (y - lo) / ((hi - lo) or 1)) * (height - top - bottom)
        return f"{fx:.1f},{fy:.1f}"

    parts = [f'<line x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}" stroke="#ddd"/>',
             f'<text x="2" y="{top + 8}" font-size="10" fill="#888">{hi:.0f}</text>',
             f'<text x="2" y="{height - bottom}" font-size="10" fill="#888">{lo:.0f}</text>']
    for x in x_values:
        parts.append(f'<text x="{px(x, lo).split(",")[0]}" y="{height - 4}" font-size="10" fill="#888" '
                     f'text-anchor="middle">{x:g}′</text>')
    for team, ys in series.items():
        run = []
        for x, y in list(zip(x_values, ys)) + [(None, None)]:
            if y is None:
                if run:
                    parts.append(f'<polyline fill="none" stroke="{escape(colors[team])}" stroke-width="2.5" '
                                 f'points="{" ".join(run)}"/>')
                run = []
            else:
                run.append(px(x, y))
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}">{"".join(parts)}</svg>'
```

- [ ] **Step 4: Прогнать**

Run: `.venv/bin/python -m pytest tests/test_report_svg.py -q`
Expected: PASS (3 теста).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/report/__init__.py src/aifootball/report/svg.py tests/test_report_svg.py
git commit -m "Отчёт: SVG поля, тепловой карты, третей и графика"
```

---

### Task 10: Картинки из видео

**Files:**
- Create: `src/aifootball/report/frames.py`
- Test: `tests/test_report_frames.py`

- [ ] **Step 1: Тесты**

`tests/test_report_frames.py` (фикстура `tiny_video` из `tests/conftest.py`: 50 кадров 320 × 240):

```python
import base64

import cv2
import numpy as np

from aifootball.report.frames import STILL_W, THUMB_H, grab_images


def _decode(uri):
    raw = base64.b64decode(uri.split(",", 1)[1])
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


def test_grab_thumb_and_still(tiny_video):
    images = grab_images(tiny_video, {
        "thumb:1": {"kind": "thumb", "frame_id": 10, "box": [100, 50, 140, 150]},
        "moment:all:0": {"kind": "still", "frame_id": 20, "box": [100, 50, 140, 150]},
        "moment:all:1": {"kind": "still", "frame_id": 30, "box": None},
    })
    assert set(images) == {"thumb:1", "moment:all:0", "moment:all:1"}
    assert all(uri.startswith("data:image/jpeg;base64,") for uri in images.values())
    assert _decode(images["thumb:1"]).shape[0] == THUMB_H
    assert _decode(images["moment:all:1"]).shape[1] == STILL_W


def test_missing_frame_is_skipped(tiny_video):
    assert grab_images(tiny_video, {"thumb:1": {"kind": "thumb", "frame_id": 999, "box": [0, 0, 10, 10]}}) == {}
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/test_report_frames.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aifootball.report.frames'`

- [ ] **Step 3: Реализация**

`src/aifootball/report/frames.py`:

```python
"""Картинки для отчёта: миниатюры игроков и стоп-кадры моментов, JPEG в base64 (data URI)."""

import base64
from pathlib import Path

import cv2
import numpy as np

THUMB_H = 120
STILL_W = 640
JPEG_QUALITY = 80
THUMB_PAD = 0.15  # запас вокруг рамки игрока
STILL_CONTEXT = 6.0  # стоп-кадр с игроком: окно шириной в столько ростов игрока
STILL_MIN_W = 480  # px исходного кадра
BOX_BGR = (0, 230, 255)


def grab_images(video: Path, requests: dict[str, dict]) -> dict[str, str]:
    """requests: ключ -> {kind: thumb|still, frame_id, box: [x1, y1, x2, y2] | None}. Нечитаемые кадры пропускаются."""
    cap = cv2.VideoCapture(str(video))
    out = {}
    try:
        for key, req in sorted(requests.items(), key=lambda kv: kv[1]["frame_id"]):
            cap.set(cv2.CAP_PROP_POS_FRAMES, req["frame_id"])
            ok, frame = cap.read()
            if not ok:
                continue
            image = _thumb(frame, req["box"]) if req["kind"] == "thumb" else _still(frame, req["box"])
            ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                out[key] = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode("ascii")
    finally:
        cap.release()
    return out


def _clip(frame: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, x2 = int(max(0, x1)), int(min(w, x2))
    y1, y2 = int(max(0, y1)), int(min(h, y2))
    return frame[y1:max(y2, y1 + 1), x1:max(x2, x1 + 1)]


def _thumb(frame: np.ndarray, box) -> np.ndarray:
    x1, y1, x2, y2 = box
    pw, ph = (x2 - x1) * THUMB_PAD, (y2 - y1) * THUMB_PAD
    crop = _clip(frame, x1 - pw, y1 - ph, x2 + pw, y2 + ph)
    scale = THUMB_H / crop.shape[0]
    return cv2.resize(crop, (max(1, int(round(crop.shape[1] * scale))), THUMB_H))


def _still(frame: np.ndarray, box) -> np.ndarray:
    image = frame.copy()
    if box is not None:
        x1, y1, x2, y2 = box
        cv2.rectangle(image, (int(x1), int(y1)), (int(x2), int(y2)), BOX_BGR, 3)
        win_w = max(STILL_MIN_W, STILL_CONTEXT * (y2 - y1))
        win_h = win_w * 3 / 4
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        image = _clip(image, cx - win_w / 2, cy - win_h / 2, cx + win_w / 2, cy + win_h / 2)
    scale = STILL_W / image.shape[1]
    return cv2.resize(image, (STILL_W, max(1, int(round(image.shape[0] * scale)))))
```

- [ ] **Step 4: Прогнать**

Run: `.venv/bin/python -m pytest tests/test_report_frames.py -q`
Expected: PASS (2 теста).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/report/frames.py tests/test_report_frames.py
git commit -m "Отчёт: миниатюры игроков и стоп-кадры из видео"
```

---

### Task 11: Страница отчёта

**Files:**
- Create: `src/aifootball/report/render.py`
- Test: `tests/test_report_render.py`

Страница: тёмная шапка (команды, дата не знаем — пишем длительность и покрытие), вкладки «Статистика / Игроки /
Моменты», переключатель периодов. Каждому периоду и вкладке — свой блок `<section data-period=… data-tab=…>`;
JS показывает один. Игроки — по команде (переключатель), строка игрока раскрывается (`<details>`) в карточку
с тепловой картой.

- [ ] **Step 1: Тесты**

`tests/test_report_render.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from report_fixtures import LENGTH, synthetic_match  # noqa: E402

from aifootball.analytics.report_data import build_report  # noqa: E402
from aifootball.report.render import image_requests, render_html  # noqa: E402


class _Venue:
    length_m, width_m, max_physical_speed = LENGTH, 20.0, 10.0


def _data():
    state, tracks = synthetic_match()
    return build_report(state, tracks, _Venue(), [(0.0, 100.0), (100.0, 200.0)],
                        {"A": "Зелёные <script>", "B": "Оранжевые"}, video_s=200.0)


def test_render_has_tabs_periods_and_escapes_names():
    html = render_html(_data(), images={})
    for key in ("all", "h1", "h2"):
        for tab in ("stats", "players", "moments"):
            assert f'data-period="{key}" data-tab="{tab}"' in html
    assert "Зелёные &lt;script&gt;" in html and "Зелёные <script>" not in html
    assert "<img" not in html  # без видео картинок нет


def test_image_requests_cover_thumbs_and_moments():
    data = _data()
    req = image_requests(data)
    assert "thumb:11" in req
    assert any(k.startswith("moment:all:") for k in req)


def test_render_inlines_images():
    data = _data()
    html = render_html(data, images={"thumb:11": "data:image/jpeg;base64,AAAA"})
    assert 'src="data:image/jpeg;base64,AAAA"' in html
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/test_report_render.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'aifootball.report.render'`

- [ ] **Step 3: Реализация**

`src/aifootball/report/render.py`:

```python
"""Сборка report.html из цифр отчёта (analytics.report_data) — один файл, всё внутри."""

from html import escape

from aifootball.report.svg import heatmap_svg, line_chart_svg, thirds_svg

TABS = (("stats", "Статистика"), ("players", "Игроки"), ("moments", "Моменты"))

CSS = """
:root{--bg:#f2f3f5;--card:#fff;--ink:#111;--muted:#7a8390;--head:#1c2430}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:14px}
.wrap{max-width:480px;margin:0 auto}
header{background:var(--head);color:#fff;padding:16px 16px 0}
header .teams{display:flex;justify-content:space-between;align-items:center;gap:8px}
header .dot{width:36px;height:36px;border-radius:50%;flex:none}
header .title{text-align:center;font-weight:700;font-size:16px}
header .sub{color:#9aa4b2;font-size:12px;text-align:center;margin-top:4px}
nav.tabs{display:flex;justify-content:space-around;margin-top:12px}
nav.tabs button{background:none;border:0;color:#9aa4b2;font-weight:600;font-size:14px;padding:10px 4px;cursor:pointer}
nav.tabs button.on{color:#fff;border-bottom:3px solid #fff}
.seg{display:flex;background:#e3e6ea;border-radius:20px;margin:12px 16px;padding:3px}
.seg button{flex:1;border:0;background:none;padding:7px;border-radius:16px;font-weight:600;cursor:pointer;color:var(--ink)}
.seg button.on{background:var(--head);color:#fff}
section{display:none}section.on{display:block}
.card{background:var(--card);border-radius:14px;margin:12px 16px;padding:14px}
.card h3{text-align:center;margin:0 0 12px;font-size:16px}
.row{margin:12px 0}.row .t{display:flex;justify-content:space-between;gap:8px}.row .t b{text-align:center}
.bars{display:flex;gap:12px;margin-top:5px}.bar{flex:1;height:6px;background:#eceef1;border-radius:3px;position:relative}
.bar i{position:absolute;top:0;bottom:0;border-radius:3px}.bar.l i{right:0}.bar.r i{left:0}
.note{font-size:12px;color:var(--muted);text-align:center;margin-top:8px}
.warn{font-size:12px;color:#b45309;text-align:center}
svg.pitch{width:100%;height:auto;display:block;border-radius:6px}
table{width:100%;border-collapse:collapse;font-size:13px}td,th{padding:6px 3px;text-align:right}
td:first-child,th:first-child{text-align:left}tr+tr td{border-top:1px solid #eee}
details summary{list-style:none;cursor:pointer}details summary::-webkit-details-marker{display:none}
details[open]{background:#fafbfc}.ava{width:30px;height:40px;object-fit:cover;border-radius:4px;vertical-align:middle;margin-right:6px}
.moment img{width:100%;border-radius:8px;display:block;margin-bottom:8px}
.moment .v{font-size:20px;font-weight:700}
.team-view{display:none}.team-view.on{display:block}
"""

JS = """
let period='all',tab='stats';
function show(){document.querySelectorAll('section').forEach(s=>s.classList.toggle('on',
 s.dataset.period===period&&s.dataset.tab===tab));
 document.querySelectorAll('[data-set-period]').forEach(b=>b.classList.toggle('on',b.dataset.setPeriod===period));
 document.querySelectorAll('[data-set-tab]').forEach(b=>b.classList.toggle('on',b.dataset.setTab===tab));}
document.querySelectorAll('[data-set-period]').forEach(b=>b.onclick=()=>{period=b.dataset.setPeriod;show()});
document.querySelectorAll('[data-set-tab]').forEach(b=>b.onclick=()=>{tab=b.dataset.setTab;show()});
document.querySelectorAll('.team-switch button').forEach(b=>b.onclick=()=>{const box=b.closest('.card');
 box.querySelectorAll('.team-switch button').forEach(x=>x.classList.toggle('on',x===b));
 box.querySelectorAll('.team-view').forEach(v=>v.classList.toggle('on',v.dataset.team===b.dataset.team));});
show();
"""


def image_requests(data: dict) -> dict[str, dict]:
    """Какие кадры вырезать из видео: миниатюры игроков и стоп-кадры моментов всех периодов."""
    req = {f"thumb:{tid}": r for tid, r in data["thumbs"].items()}
    for p in data["periods"]:
        for i, m in enumerate(p["moments"]):
            req[f"moment:{p['key']}:{i}"] = m["still"]
    return req


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def _row(name: str, a: float, b: float, fmt: str, colors: dict) -> str:
    peak = max(a, b) or 1
    return (f'<div class="row"><div class="t"><span>{fmt.format(a)}</span><b>{name}</b><span>{fmt.format(b)}</span></div>'
            f'<div class="bars"><div class="bar l"><i style="width:{a / peak * 100:.0f}%;background:{colors["A"]}"></i></div>'
            f'<div class="bar r"><i style="width:{b / peak * 100:.0f}%;background:{colors["B"]}"></i></div></div></div>')


def _team_switch(names: dict) -> str:
    return ('<div class="seg team-switch" style="margin:0 0 10px">'
            + "".join(f'<button data-team="{t}" class="{"on" if t == "A" else ""}">{escape(names[t])}</button>'
                      for t in ("A", "B")) + "</div>")


def _stats(p: dict, data: dict) -> str:
    names, colors, pitch = data["match"]["teams"], data["match"]["colors"], data["pitch"]
    a, b = p["teams"]["A"], p["teams"]["B"]
    warn = '<div class="warn">Мало данных: команда большую часть времени вне кадра</div>' if a["low_data"] or b["low_data"] else ""
    overview = "".join([
        _row("Дистанция", a["distance_m"] / 1000, b["distance_m"] / 1000, "{:.2f} км", colors),
        _row("Метров в минуту", a["m_per_min"], b["m_per_min"], "{:.0f}", colors),
        _row("Бег быстрее 4 м/с", a["hsr_m"], b["hsr_m"], "{:.0f} м", colors),
        _row("Спринты", a["sprints"], b["sprints"], "{:.0f}", colors),
        _row("Компактность", a["compactness_m2"], b["compactness_m2"], "{:.0f} м²", colors),
        _row("Ширина", a["width_m"], b["width_m"], "{:.1f} м", colors),
        _row("Глубина", a["depth_m"], b["depth_m"], "{:.1f} м", colors),
    ])
    views = []
    for t in ("A", "B"):
        thirds = p["thirds"][t]
        thirds_html = (thirds_svg(thirds, pitch["length_m"], pitch["width_m"], colors[t])
                       + '<div class="note">Доля времени в своей / средней / чужой трети. Свои ворота слева</div>'
                       if thirds else '<div class="note">Направление атаки не определено — трети не показаны</div>')
        views.append(f'<div class="team-view {"on" if t == "A" else ""}" data-team="{t}">{thirds_html}'
                     f'<div style="height:10px"></div>'
                     f'{heatmap_svg(p["teams"][t]["heatmap_s"], pitch["length_m"], pitch["width_m"], colors[t], pitch["cell_m"])}'
                     f'<div class="note">Где проводили время полевые игроки</div></div>')
    s = p["series"]
    chart = line_chart_svg(s["start_min"], {"A": s["A"], "B": s["B"]}, colors)
    ball = ""
    if "ball" in p:
        poss, passes = p["ball"]["possession"], p["ball"]["passes"]
        ball = (f'<div class="card"><h3>Владение и передачи</h3>'
                + _row("Владение", poss["possession_pct"]["A"], poss["possession_pct"]["B"], "{:.0f}%", colors)
                + _row("Передачи", passes["passes_total"]["A"], passes["passes_total"]["B"], "{:.0f}", colors)
                + f'<div class="warn">{escape(p["ball"]["caveat"])}</div></div>')
    return (f'<div class="card"><h3>Обзор матча</h3>{warn}{overview}</div>'
            f'<div class="card"><h3>Где играла команда</h3>{_team_switch(names)}{"".join(views)}</div>'
            f'<div class="card"><h3>По ходу матча</h3>{chart}'
            f'<div class="note">Метров в минуту на полевого игрока, по 5 минут</div></div>{ball}')


def _players(p: dict, data: dict, images: dict) -> str:
    names, colors, pitch = data["match"]["teams"], data["match"]["colors"], data["pitch"]
    views = []
    for t in ("A", "B"):
        rows = []
        for r in (r for r in p["players"] if r["team"] == t):
            img = images.get(f"thumb:{r['track_id']}")
            ava = f'<img class="ava" src="{img}" alt="">' if img else ""
            vmax = f"{r['vmax_ms']:.1f} м/с" if r["vmax_ms"] is not None else "—"
            card = (f'{heatmap_svg(r["heatmap_s"], pitch["length_m"], pitch["width_m"], colors[t], pitch["cell_m"])}'
                    f'<table><tr><td>Бег быстрее 4 м/с</td><td>{r["hsr_m"]:.0f} м</td></tr>'
                    f'<tr><td>Макс. скорость (устойчивая)</td><td>{vmax}</td></tr></table>')
            rows.append(f'<tr><td colspan="5"><details><summary><table><tr>'
                        f'<td>{ava}{escape(r["label"])}</td><td>{_clock(r["observed_s"])}</td>'
                        f'<td>{r["distance_m"] / 1000:.2f}</td><td>{r["m_per_min"]:.0f}</td><td>{r["sprints"]}</td>'
                        f'</tr></table></summary>{card}</details></td></tr>')
        body = "".join(rows) or '<tr><td colspan="5">Нет треков дольше минуты</td></tr>'
        views.append(f'<div class="team-view {"on" if t == "A" else ""}" data-team="{t}"><table>'
                     f'<tr><th>Игрок</th><th>Время</th><th>км</th><th>м/мин</th><th>Спр.</th></tr>{body}</table></div>')
    return (f'<div class="card">{_team_switch(names)}{"".join(views)}'
            '<div class="note">Строки — треки, а не люди: при заменах и столкновениях один человек может '
            'дать несколько строк. Узнать себя можно по миниатюре.</div></div>')


def _moments(p: dict, data: dict, images: dict) -> str:
    names = data["match"]["teams"]
    cards = []
    for i, m in enumerate(p["moments"]):
        img = images.get(f"moment:{p['key']}:{i}")
        who = f'{escape(names[m["team"]])}' + (f' · {escape(m["label"])}' if m["label"] else "")
        pic = f'<img src="{img}" alt="">' if img else ""
        cards.append(f'<div class="card moment">{pic}'
                     f'<div>{escape(m["title"])}</div><div class="v">{escape(m["value"])}</div>'
                     f'<div class="note" style="text-align:left">{_clock(m["ts"])} · {who}</div></div>')
    return "".join(cards) or '<div class="card"><div class="note">Моментов нет</div></div>'


def render_html(data: dict, images: dict[str, str]) -> str:
    match, colors = data["match"], data["match"]["colors"]
    names = match["teams"]
    halves = "" if match["halves_found"] else " · таймы не определены"
    header = (f'<header><div class="teams"><div class="dot" style="background:{colors["A"]}"></div>'
              f'<div><div class="title">{escape(names["A"])} — {escape(names["B"])}</div>'
              f'<div class="sub">обработано {_clock(match["processed_s"])} из {_clock(match["video_s"])}{halves}</div></div>'
              f'<div class="dot" style="background:{colors["B"]}"></div></div>'
              '<nav class="tabs">' + "".join(f'<button data-set-tab="{k}">{n}</button>' for k, n in TABS) + '</nav></header>')
    seg = ('<div class="seg">' + "".join(f'<button data-set-period="{p["key"]}">{escape(p["name"])}</button>'
                                          for p in data["periods"]) + "</div>")
    sections = []
    for p in data["periods"]:
        sections.append(f'<section data-period="{p["key"]}" data-tab="stats">{_stats(p, data)}</section>')
        sections.append(f'<section data-period="{p["key"]}" data-tab="players">{_players(p, data, images)}</section>')
        sections.append(f'<section data-period="{p["key"]}" data-tab="moments">{_moments(p, data, images)}</section>')
    title = escape(f'{names["A"]} — {names["B"]}')
    return (f'<!doctype html><html lang="ru"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>'
            f'<style>{CSS}</style></head><body><div class="wrap">{header}{seg}{"".join(sections)}</div>'
            f'<script>{JS}</script></body></html>')
```

- [ ] **Step 4: Прогнать**

Run: `.venv/bin/python -m pytest tests/test_report_render.py -q`
Expected: PASS (3 теста).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/report/render.py tests/test_report_render.py
git commit -m "Отчёт: страница со вкладками, периодами, игроками и моментами"
```

---

### Task 12: Команда `cli report`

**Files:**
- Modify: `src/aifootball/cli.py`
- Test: `tests/test_report_cli.py`

- [ ] **Step 1: Тест**

`tests/test_report_cli.py`:

```python
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from report_fixtures import synthetic_match  # noqa: E402

from aifootball import schemas  # noqa: E402
from aifootball.cli import main  # noqa: E402


def test_report_command_writes_html_and_json(venue, tmp_path):
    match = tmp_path / "match"
    state, tracks = synthetic_match()
    schemas.write(state, match / "state.parquet", "state")
    schemas.write(tracks, match / "tracks.parquet", "tracks")

    code = main(["report", "--venue", str(venue.root), "--match", str(match),
                 "--halves", "0:00-1:40,1:40-3:19", "--team-a", "Зелёные", "--team-b", "Оранжевые"])

    assert code == 0
    data = json.loads((match / "report.json").read_text(encoding="utf-8"))
    assert [p["key"] for p in data["periods"]] == ["all", "h1", "h2"]
    html = (match / "report.html").read_text(encoding="utf-8")
    assert "Зелёные — Оранжевые" in html and "<img" not in html
```

- [ ] **Step 2: Убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_report_cli.py -q`
Expected: FAIL — `argparse` ошибка `invalid choice: 'report'` (SystemExit 2).

- [ ] **Step 3: Реализация** (в `src/aifootball/cli.py`)

1. В docstring модуля добавить строку после `eval-passes`:

```
    python -m aifootball.cli report  --venue DIR --match DIR [--video V] [--halves 0:40-21:50,27:10-46:00]
```

2. Функция (перед `def _fmt`):

```python
def cmd_report(args, venue) -> None:
    from aifootball.analytics.periods import find_halves, parse_halves
    from aifootball.analytics.report_data import build_report
    from aifootball.report.render import image_requests, render_html

    state = schemas.read(args.match / "state.parquet", "state")
    tracks = schemas.read(args.match / "tracks.parquet", "tracks")
    video_s = float(tracks["ts"].max())
    spans = parse_halves(args.halves, video_s) if args.halves else find_halves(tracks)
    if not spans:
        spans = [(0.0, video_s)]
    ball_state = None
    if args.with_ball:
        from aifootball.perception.ball import process_ball_trajectory

        ball_state = process_ball_trajectory(schemas.read(args.match / "detections.parquet", "detections"), venue)
    names = {"A": args.team_a or "Команда A", "B": args.team_b or "Команда B"}
    data = build_report(state, tracks, venue, spans, names, video_s, ball_state)
    schemas.write_json(data, args.match / "report.json")

    images = {}
    if args.video:
        from aifootball.report.frames import grab_images

        images = grab_images(args.video, image_requests(data))
    out = args.match / "report.html"
    out.write_text(render_html(data, images), encoding="utf-8")
    halves = " / ".join(f"{s / 60:.1f}–{e / 60:.1f} мин" for s, e in spans)
    print(f"report: таймы {halves}, игроков {len(data['periods'][0]['players'])}, "
          f"картинок {len(images)}, {out.stat().st_size / 1e6:.1f} МБ -> {out}")
```

3. В `build_parser` перед `run = add("run", ...)`:

```python
    rep = add("report")
    rep.add_argument("--video", type=Path, default=None, help="для миниатюр и стоп-кадров")
    rep.add_argument("--halves", default=None, help="таймы вручную: 0:40-21:50,27:10-46:00")
    rep.add_argument("--team-a", default=None)
    rep.add_argument("--team-b", default=None)
    rep.add_argument("--with-ball", action="store_true", help="владение и передачи (приблизительно)")
```

4. В `COMMANDS` добавить `"report": cmd_report,`.

- [ ] **Step 4: Прогнать**

Run: `.venv/bin/python -m pytest tests/test_report_cli.py -q`
Expected: PASS.

Run: `.venv/bin/python -m pytest -q`
Expected: PASS (весь набор).

- [ ] **Step 5: Commit**

```bash
git add src/aifootball/cli.py tests/test_report_cli.py
git commit -m "Команда report: report.html и report.json по матчу"
```

---

### Task 13: Проверка на живых данных

**Files:** без изменений кода, кроме найденных багов (каждый — отдельный коммит с тестом).

- [ ] **Step 1: Пересчитать треки после правки вратарей (Task 1)**

```bash
for seg in 60-240 600-780; do for c in track project metrics; do .venv/bin/python -m aifootball.cli $c --venue configs/venues/yaroslavl --match data/matches/yaroslavl-$seg; done; done
```

Expected: в выводе `track` у отрезка 600-780 вратарей заметно меньше 19 треков; ролей `goalkeeper` — по 1–3 трека на команду.

- [ ] **Step 2: Собрать отчёты**

```bash
.venv/bin/python -m aifootball.cli report --venue configs/venues/yaroslavl --match data/matches/yaroslavl-60-240 --video data/raw/yaroslavl_futsal_n4WAFg0FfV4_60-240.mp4 --team-a "Альта-Тур 35+" --team-b "БлэкСкрап 35+"
```

```bash
.venv/bin/python -m aifootball.cli report --venue configs/venues/yaroslavl --match data/matches/yaroslavl-600-780 --video data/raw/yaroslavl_futsal_n4WAFg0FfV4_600-780.mp4 --team-a "Альта-Тур 35+" --team-b "БлэкСкрап 35+"
```

Expected: `report: таймы 0.0–3.1 мин` (отрезок короче перерыва — один период), размер ≤ 3 МБ.

- [ ] **Step 3: Посмотреть глазами**

Открыть `data/matches/yaroslavl-60-240/report.html` во встроенном браузере (desktop и `resize_window` preset `mobile`).
Проверить: шапка, вкладки и периоды переключаются; полоски сравнения в цветах команд; поле с третями
и тепловая карта ориентированы «свои ворота слева» (для B — левые ворота кадра); миниатюры узнаваемы;
стоп-кадры моментов показывают обведённого игрока; на ширине 375 px нет горизонтальной прокрутки.

- [ ] **Step 4: Записать итог**

В `docs/specs/2026-10-13-match-report-design.md` ничего не менять, если поведение совпало. Найденные
расхождения — исправить (тест + код + коммит) или записать открытым вопросом в конец спецификации.

- [ ] **Step 5: Полный матч (фон, по согласованию с пользователем)**

Скачать всю запись Ярославля (≈ 55 мин), прогнать `run` (детекция ≈ 6 ч), затем `report` без `--halves`
и проверить, что автомат нашёл перерыв около 21:50.
