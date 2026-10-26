# Формат турнира, жеребьёвка, таблицы и сетка — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Цель:** организатор задаёт формат турнира из этапов, проводит жеребьёвку (автоматически и вручную, с предпросмотром), получает пары по турам и раундам и назначает им дату; зритель видит таблицы групп и сетку плей-офф.

**Архитектура:** новый пакет `aifootball.service.stages`. Правила (`stages/rules/`) — чистые функции без базы: генерация пар, жеребьёвка, подсчёт мест, швейцарка, продвижение. Слой `operations.py` загружает этапы, пары и результаты протоколов и вызывает правила. Пары (`fixtures`) живут отдельно от матчей; матч создаётся при назначении даты, поэтому инварианты матча и экраны PR #19 не меняются. На фронтенде новый каталог `web/src/features/stages/` общий для кабинета и зрителя.

**Технологии:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Pydantic 2; React 19, TypeScript, Vite, Vitest + Testing Library + MSW, Playwright.

Спецификация: [2026-10-27-tournament-format-design.md](../specs/2026-10-27-tournament-format-design.md).

---

## Карта файлов

Бэкенд (`src/aifootball/service/stages/`):
- `rules/brackets.py` — `FixtureSpec`, Бергер, олимпийка, двойное выбывание, удаление пустых мест.
- `rules/draws.py` — корзины, змейка, случайный порядок, схема выхода из групп.
- `rules/standings.py` — таблица, личные встречи, Бухгольц, жребий, сравнение лучших по месту.
- `rules/swiss.py` — пары очередного тура швейцарки.
- `rules/progress.py` — победитель пары, разрешение источников, итог группового этапа.
- `models.py` — `Stage`, `StageDraw`, `Fixture`.
- `schemas.py` — настройки этапов, шаблоны, тела запросов, представления.
- `generate.py` — пары этапа из настроек и жеребьёвки (связка правил и настроек).
- `results.py` — результаты матчей из подтверждённых или опубликованных версий протокола.
- `operations.py` — состояние этапов, таблицы, сетка, жеребьёвка, назначение, замена, жребий, следующий тур.
- `routes.py` — API кабинета; `public_routes.py` — API зрителя.
- `migrations/versions/0027_tournament_stages.py`.

Изменяются: `src/aifootball/service/app.py` (роутеры), `tournaments/models.py` и `tournaments/schemas.py` (`standings_public`), `views.py` (`TournamentView`, `PublicTournament`), `data/service/openapi.json`, `web/src/api/types.ts`.

Фронтенд (`web/src/features/stages/`):
- `api.ts` — типы и вызовы.
- `labels.ts` — подписи источников, раундов, видов этапа.
- `GroupTable.tsx`, `Bracket.tsx`, `StandingsView.tsx` — показ (общий для кабинета и зрителя).
- `FormatStep.tsx` — шаблоны и настройки этапов.
- `DrawStep.tsx` — посев, способ, предпросмотр, обмен, подтверждение.
- `UnscheduledFixtures.tsx` — пары без даты (кабинет с кнопкой «Назначить», зритель — список).
- `ScheduleFixtureForm.tsx` — форма назначения.
- `StageWorkspace.tsx` — вкладка «Таблица» кабинета.
- `stages.css`.

Изменяются: `TournamentSetup.tsx` (шаги), `TournamentWorkspace.tsx` и `navigation/rail.tsx` (вкладка «Таблица»), `public/PublicPages.tsx` (раздел «Таблица», блок «Ещё без даты»). `Schedule.tsx` не трогаем (PR #19).

Тесты: `tests/service/test_stage_rules.py` (без базы), `tests/service/test_stages_api.py`, `tests/service/test_standings_public.py`, `web/src/features/stages/*.test.tsx`, `web/e2e/tournament-format.spec.ts`.

## Подготовка рабочей копии

- [ ] Рабочая копия — `.claude/worktrees/tournament-format`, ветка `feat/tournament-format` от `main`.
- [ ] `uv sync --locked --all-extras` и `npm --prefix web ci` в рабочей копии.
- [ ] Проверка исходного состояния: `.venv/bin/python -m pytest tests/service/test_tournaments.py -q` — PASS.

---

### Задача 1. Пары круговых этапов и сеток (`rules/brackets.py`)

**Файлы:** создать `src/aifootball/service/stages/__init__.py`, `stages/rules/__init__.py`, `stages/rules/brackets.py`; тест `tests/service/test_stage_rules.py`.

- [ ] **Шаг 1. Тесты.**

```python
from collections import Counter
import random
import pytest
from aifootball.service.stages.rules.brackets import (berger_rounds, round_robin, seed_positions,
    single_elim, double_elim, entry, bracket_size)


@pytest.mark.parametrize('n', range(2, 17))
def test_berger_every_pair_once_and_home_balance(n):
    rounds = berger_rounds(range(n))
    pairs = Counter(frozenset(p) for r in rounds for p in r)
    assert len(pairs) == n * (n - 1) // 2 and set(pairs.values()) == {1}
    home = Counter(a for r in rounds for a, _ in r); away = Counter(b for r in rounds for _, b in r)
    assert max(abs(home[t] - away[t]) for t in range(n)) <= (0 if n % 2 else 1)
    assert all(len({t for p in r for t in p}) == 2 * len(r) for r in rounds)  # никто не играет дважды за тур


def test_second_leg_mirrors_home():
    first, second = berger_rounds('ABCD'), berger_rounds('ABCD', legs=2)[3:]
    assert second == [[(b, a) for a, b in r] for r in first]


def test_seed_positions_standard():
    assert seed_positions(8) == [1, 8, 4, 5, 2, 7, 3, 6]


def simulate(specs, rng):
    win, lose, losses = {}, {}, Counter()
    def team(src):
        if src is None: return None
        if 'entry' in src: return src['entry']
        return (win if 'winner' in src else lose).get(src.get('winner') or src.get('loser'), '?')
    pending = list(specs)
    while pending:
        progressed = False
        for s in list(pending):
            h, a = team(s.home), team(s.away)
            if '?' in (h, a): continue
            pending.remove(s); progressed = True
            if s.bye: win[s.key], lose[s.key] = h, None; continue
            if s.bracket == 'final_reset' and win.get('F') == a: continue
            w, l = (h, a) if rng.random() < .5 else (a, h)
            win[s.key], lose[s.key] = w, l; losses[l] += 1
        assert progressed
    return win, losses


@pytest.mark.parametrize('n', range(2, 33))
def test_single_elim_one_unbeaten_champion(n):
    teams = [str(i) for i in range(n)]
    specs = single_elim([entry(t) for t in teams], third_place=n >= 4)
    assert len({s.key for s in specs}) == len(specs)
    win, losses = simulate(specs, random.Random(n))
    champion = win[f'U{bracket_size(n).bit_length() - 1}-1']
    assert champion in teams and losses[champion] == 0


def test_byes_go_to_top_seeds():
    first = [s for s in single_elim([entry(t) for t in 'ABCDE']) if s.round_no == 1]
    assert [(s.home, s.bye) for s in first if s.bye] == [({'entry': 'A'}, True), ({'entry': 'B'}, True), ({'entry': 'C'}, True)]


def test_two_leg_round_swaps_home_in_first_leg():
    legs = [s for s in single_elim([entry(t) for t in 'ABCD'], two_leg_rounds=(1,)) if s.key == 'U1-1']
    assert [(s.leg, s.home, s.away) for s in legs] == [(1, {'entry': 'D'}, {'entry': 'A'}), (2, {'entry': 'A'}, {'entry': 'D'})]


@pytest.mark.parametrize('n', range(3, 33))
@pytest.mark.parametrize('reset', [False, True])
def test_double_elim_two_losses_out(n, reset):
    teams = [str(i) for i in range(n)]
    specs = double_elim([entry(t) for t in teams], reset)
    assert len({s.key for s in specs}) == len(specs)
    win, losses = simulate(specs, random.Random(n * 2 + reset))
    champion = win.get('F2') or win['F']
    assert losses[champion] <= 1
    for t in teams:
        if t != champion: assert losses[t] == 2 or (losses[t] == 1 and not reset)
```

- [ ] **Шаг 2.** `.venv/bin/python -m pytest tests/service/test_stage_rules.py -q` — FAIL (`ModuleNotFoundError`).
- [ ] **Шаг 3. Реализация** `stages/rules/brackets.py`:

```python
"""Пары круговых этапов и сеток на выбывание: чистые функции без базы."""
from dataclasses import dataclass, field, replace

# Источник стороны пары: {'entry': id}, {'winner': key}, {'loser': key},
# {'group': 'A', 'place': 1}, {'best': 3, 'rank': 1}, {'stage_place': 1}; None — соперника нет.
Source = dict | None


@dataclass(frozen=True)
class FixtureSpec:
    key: str
    round_no: int
    home: Source
    away: Source
    bracket: str | None = None
    slot: int = 0
    leg: int = 1
    group_no: int | None = None
    bye: bool = False


def entry(value):
    return None if value is None else {'entry': str(value)}


def berger_rounds(teams, legs=1):
    """Туры методом Бергера: последняя позиция неподвижна, остальные вращаются; отдых не создаёт пару."""
    items = list(teams)
    if len(items) % 2: items.append(None)
    n = len(items); rounds = []
    for r in range(n - 1):
        pairs = []
        for i in range(n // 2):
            a, b = items[i], items[n - 1 - i]
            if (i == 0 and r % 2) or (i > 0 and i % 2): a, b = b, a
            if a is not None and b is not None: pairs.append((a, b))
        rounds.append(pairs)
        items = [items[n - 2], *items[:n - 2], items[n - 1]]
    if legs == 2: rounds += [[(b, a) for a, b in pairs] for pairs in rounds]
    return rounds


def round_robin(teams, legs=1, group_no=None):
    prefix = f'G{group_no}' if group_no is not None else 'L'
    return [FixtureSpec(f'{prefix}-R{r}-{i}', r, entry(a), entry(b), group_no=group_no, slot=i)
            for r, pairs in enumerate(berger_rounds(teams, legs), 1) for i, (a, b) in enumerate(pairs, 1)]


def seed_positions(size):
    """Номера посева по местам сетки: 1–16, 8–9… — первые номера встречаются как можно позже."""
    order = [1]
    while len(order) < size:
        total = len(order) * 2 + 1
        order = [s for seed in order for s in (seed, total - seed)]
    return order


def bracket_size(count):
    size = 1
    while size < count: size *= 2
    return size


def _legs(spec, two_leg):
    if not two_leg or spec.bye: return [spec]
    # В первом матче принимает нижняя сторона пары, во втором — сеянная выше.
    return [replace(spec, home=spec.away, away=spec.home, leg=1), replace(spec, leg=2)]


def single_elim(seeds, third_place=False, two_leg_rounds=()):
    """seeds — источники по силе (первый сильнейший). Ключи: U<раунд>-<пара>, T — за 3-е место."""
    size = bracket_size(len(seeds)); rounds = size.bit_length() - 1
    padded = list(seeds) + [None] * (size - len(seeds))
    places = [padded[s - 1] for s in seed_positions(size)]
    specs = []
    for r in range(1, rounds + 1):
        for slot in range(1, size // 2 ** r + 1):
            if r == 1: home, away = places[2 * slot - 2], places[2 * slot - 1]
            else: home, away = {'winner': f'U{r-1}-{2*slot-1}'}, {'winner': f'U{r-1}-{2*slot}'}
            specs.append(FixtureSpec(f'U{r}-{slot}', r, home, away, 'upper', slot))
    if third_place and rounds >= 2:
        specs.append(FixtureSpec('T', rounds, {'loser': f'U{rounds-1}-1'}, {'loser': f'U{rounds-1}-2'}, 'third', 1))
    specs = prune(specs)
    return [leg for spec in specs for leg in _legs(spec, spec.round_no in two_leg_rounds and spec.bracket != 'third')]


def double_elim(seeds, grand_final_reset=False):
    """Верхняя сетка как олимпийка; проигравшие опускаются в нижнюю (L<раунд>-<пара>), финал F и переигровка F2."""
    size = bracket_size(max(len(seeds), 4)); k = size.bit_length() - 1
    upper = [s for s in single_elim(seeds) if s.bracket == 'upper']
    specs = list(upper)
    # L1: проигравшие первого раунда верхней сетки между собой.
    for slot in range(1, size // 4 + 1):
        specs.append(FixtureSpec(f'L1-{slot}', 1, {'loser': f'U1-{2*slot-1}'}, {'loser': f'U1-{2*slot}'}, 'lower', slot))
    for j in range(1, k):
        count = size // 2 ** (j + 1)
        # Чётный раунд: победители нижней против проигравших верхней в обратном порядке — меньше повторных встреч.
        for slot in range(1, count + 1):
            specs.append(FixtureSpec(f'L{2*j}-{slot}', 2 * j, {'winner': f'L{2*j-1}-{slot}'},
                                     {'loser': f'U{j+1}-{count+1-slot}'}, 'lower', slot))
        if j < k - 1:
            for slot in range(1, count // 2 + 1):
                specs.append(FixtureSpec(f'L{2*j+1}-{slot}', 2 * j + 1, {'winner': f'L{2*j}-{2*slot-1}'},
                                         {'winner': f'L{2*j}-{2*slot}'}, 'lower', slot))
    specs.append(FixtureSpec('F', k + 1, {'winner': f'U{k}-1'}, {'winner': f'L{2*(k-1)}-1'}, 'final', 1))
    if grand_final_reset:
        # Пара показывается и назначается, только если финал выиграла команда из нижней сетки.
        specs.append(FixtureSpec('F2', k + 2, {'winner': f'L{2*(k-1)}-1'}, {'winner': f'U{k}-1'}, 'final_reset', 1))
    return prune(specs)


def prune(specs):
    """Пустые места сетки: пара с одним соперником — пропуск хода, без соперников — исчезает."""
    specs = list(specs)
    while True:
        by_key = {s.key: s for s in specs}
        def resolve(source):
            if not source or ('winner' not in source and 'loser' not in source): return source, False
            ref = by_key.get(source.get('winner') or source.get('loser'))
            if ref is None: return None, True
            if ref.bye:
                if 'loser' in source: return None, True
                return (ref.home or ref.away), True
            return source, False
        changed = False; result = []
        for s in specs:
            home, ch1 = resolve(s.home); away, ch2 = resolve(s.away); changed |= ch1 or ch2
            if home is None and away is None:
                changed = True; continue
            bye = home is None or away is None
            if bye and not s.bye: changed = True
            if bye: home, away = (home or away), None
            result.append(replace(s, home=home, away=away, bye=bye))
        if not changed: return result
        specs = result
```

- [ ] **Шаг 4.** Тот же запуск — PASS.
- [ ] **Шаг 5.** Коммит `feat(stages): round robin and elimination fixture generators`.

### Задача 2. Жеребьёвка и схема из групп (`rules/draws.py`)

**Файлы:** создать `stages/rules/draws.py`; дополнить `tests/service/test_stage_rules.py`.

- [ ] **Шаг 1. Тесты.**

```python
from aifootball.service.stages.rules.draws import pots_draw, snake_draw, group_scheme, group_sizes


def test_pots_one_team_from_each_pot_and_reproducible():
    groups = pots_draw(list(range(12)), 4, seed=7)
    assert groups == pots_draw(list(range(12)), 4, seed=7)
    for pot in range(3):
        assert sorted(g[pot] for g in groups) == list(range(pot * 4, pot * 4 + 4))


def test_snake():
    assert snake_draw(list(range(8)), 4) == [[0, 7], [1, 6], [2, 5], [3, 4]]


def test_group_sizes_differ_by_one():
    assert group_sizes(10, 3) == [4, 3, 3]


def label(s): return f"{'ABCDEFGH'[s['group'] - 1]}{s['place']}" if 'group' in s else f"3-{s['rank']}"


def test_two_groups_cross():
    first = [(label(s.home), label(s.away)) for s in single_elim(group_scheme(2, 2)) if s.round_no == 1]
    assert first == [('A1', 'B2'), ('B1', 'A2')]


@pytest.mark.parametrize('groups', [4, 8])
def test_group_mates_meet_only_in_final(groups):
    seeds = group_scheme(groups, 2)
    from aifootball.service.stages.rules.draws import meeting_round
    size = bracket_size(len(seeds)); rounds = size.bit_length() - 1
    for i, a in enumerate(seeds):
        for j, b in enumerate(seeds):
            if i < j and a['group'] == b['group']:
                assert meeting_round(size, i + 1, j + 1) == rounds
```

- [ ] **Шаг 2.** Запуск — FAIL.
- [ ] **Шаг 3. Реализация** `stages/rules/draws.py`:

```python
"""Жеребьёвка: корзины, змейка и схема выхода из групп в сетку."""
import random
from itertools import permutations
from aifootball.service.stages.rules.brackets import seed_positions, bracket_size


def group_sizes(count, groups):
    return [count // groups + (1 if g < count % groups else 0) for g in range(groups)]


def pots_draw(seeding, groups, seed):
    """Корзины по посеву; из каждой корзины в каждую группу случайно одна команда."""
    rng = random.Random(seed); result = [[] for _ in range(groups)]
    for start in range(0, len(seeding), groups):
        pot = list(seeding[start:start + groups]); rng.shuffle(pot)
        for g, team in enumerate(pot): result[g].append(team)
    return result


def snake_draw(seeding, groups):
    result = [[] for _ in range(groups)]
    for i, team in enumerate(seeding):
        row, col = divmod(i, groups)
        result[col if row % 2 == 0 else groups - 1 - col].append(team)
    return result


def random_order(seeding, seed):
    order = list(seeding); random.Random(seed).shuffle(order); return order


def meeting_round(size, a, b):
    """Раунд, в котором встречаются номера посева a и b, если оба побеждают."""
    places = {s: i for i, s in enumerate(seed_positions(size))}
    return (places[a] ^ places[b]).bit_length()


def group_scheme(group_count, per_group, best=()):
    """Источники по силе для сетки из групп: победители групп разнесены, одногруппники встречаются как можно позже."""
    tiers = [[{'group': g, 'place': p} for g in range(1, group_count + 1)] for p in range(1, per_group + 1)]
    for item in best:
        tiers.append([{'best': item['place'], 'rank': r} for r in range(1, item['count'] + 1)])
    size = bracket_size(sum(map(len, tiers))); rounds = size.bit_length() - 1
    def cost(seq):
        total = 0
        for i, a in enumerate(seq):
            for j in range(i + 1, len(seq)):
                if 'group' in a and a.get('group') == seq[j].get('group'):
                    total += 4 ** (rounds - meeting_round(size, i + 1, j + 1))
        return total
    placed = list(tiers[0])
    for tier in tiers[1:]:
        options = permutations(tier) if len(tier) <= 8 else [tier]
        placed += min(options, key=lambda perm: cost(placed + list(perm)))
    return placed
```

- [ ] **Шаг 4.** Запуск — PASS. **Шаг 5.** Коммит `feat(stages): pots, snake and group-to-bracket scheme`.

### Задача 3. Места и критерии (`rules/standings.py`)

**Файлы:** создать `stages/rules/standings.py`; дополнить тест.

- [ ] **Шаг 1. Тесты.**

```python
from aifootball.service.stages.rules.standings import rank, rank_across, Result as R, SWISS_CRITERIA


def places(rows): return [(r.team, r.place, r.tied) for r in rows]


def test_head_to_head_beats_goal_difference():
    res = [R('A', 'B', 1, 0), R('B', 'C', 9, 0), R('C', 'A', 1, 0), R('A', 'D', 1, 0), R('B', 'D', 0, 1), R('C', 'D', 1, 0)]
    # A, B, C по 6? — нет: A 6, B 3, C 6. A и C равны; C выиграл личную встречу.
    assert [r.team for r in rank('ABCD', res)][:2] == ['C', 'A']


def test_three_way_cycle_falls_to_overall_then_lot():
    cycle = [R('A', 'B', 1, 0), R('B', 'C', 1, 0), R('C', 'A', 1, 0)]
    res = cycle + [R('A', 'D', 5, 0), R('B', 'D', 1, 0), R('C', 'D', 1, 0)]
    assert places(rank('ABCD', res)) == [('A', 1, False), ('B', 2, True), ('C', 2, True), ('D', 4, False)]
    res = cycle + [R(t, 'D', 1, 0) for t in 'ABC']
    assert places(rank('ABCD', res))[:3] == [('A', 1, True), ('B', 1, True), ('C', 1, True)]
    assert places(rank('ABCD', res, lot=['C', 'A', 'B']))[:3] == [('C', 1, False), ('A', 2, False), ('B', 3, False)]


def test_subgroup_reapplies_head_to_head():
    # Все четверо по 4 очка; мини-таблица делит на {B, D} и {A, C}, внутри пар решает личная встреча.
    res = [R('A', 'B', 1, 1), R('A', 'C', 0, 1), R('A', 'D', 2, 1), R('B', 'C', 2, 1), R('B', 'D', 1, 2), R('C', 'D', 1, 1)]
    assert [r.team for r in rank('ABCD', res)] == ['D', 'B', 'C', 'A']


def test_technical_points_from_regulation_and_swiss_bye():
    rows = rank('AB', [R('A', 'B', 2, 2, points=(2, 1, 0))], SWISS_CRITERIA, byes=[('B', 2)])
    assert {r.team: r.points for r in rows} == {'A': 1, 'B': 3}


def test_best_thirds_per_match():
    from aifootball.service.stages.rules.standings import Row
    rows = [Row('X', played=3, points=4), Row('Y', played=2, points=3), Row('Z', played=2, points=1)]
    ordered, cutoff_tied = rank_across(rows)
    assert [r.team for r in ordered] == ['Y', 'X', 'Z'] and not cutoff_tied(2)
```

- [ ] **Шаг 2.** Запуск — FAIL.
- [ ] **Шаг 3. Реализация** `stages/rules/standings.py`:

```python
"""Таблица и порядок мест: личные встречи по правилу УЕФА, затем общие показатели, затем жребий."""
from dataclasses import dataclass, field
from fractions import Fraction

H2H = ('h2h_points', 'h2h_goal_diff', 'h2h_goals')
DEFAULT_CRITERIA = ('points', *H2H, 'goal_diff', 'goals_for', 'wins', 'lot')
SWISS_CRITERIA = ('points', 'buchholz', 'goal_diff', 'goals_for', 'wins', 'lot')


@dataclass(frozen=True)
class Result:
    home: str
    away: str
    home_goals: int
    away_goals: int
    points: tuple[int, int, int] = (3, 1, 0)  # победа, ничья, поражение — из регламента матча


@dataclass
class Row:
    team: str
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0
    buchholz: int = 0
    place: int = 0
    tied: bool = False

    @property
    def goal_diff(self): return self.goals_for - self.goals_against


def _table(teams, results, byes=()):
    rows = {t: Row(t) for t in teams}
    for r in results:
        if r.home not in rows or r.away not in rows: continue
        win, draw, loss = r.points
        for side, gf, ga in ((r.home, r.home_goals, r.away_goals), (r.away, r.away_goals, r.home_goals)):
            row = rows[side]; row.played += 1; row.goals_for += gf; row.goals_against += ga
            if gf > ga: row.won += 1; row.points += win
            elif gf == ga: row.drawn += 1; row.points += draw
            else: row.lost += 1; row.points += loss
    for team, win_points in byes:
        # Отдых в швейцарке — победа без мячей.
        if team in rows: rows[team].played += 1; rows[team].won += 1; rows[team].points += win_points
    return rows


def _value(row, criterion):
    return {'points': row.points, 'goal_diff': row.goal_diff, 'goals_for': row.goals_for,
            'wins': row.won, 'buchholz': row.buchholz}[criterion]


def _split(group, key):
    parts = {}
    for team in group: parts.setdefault(key(team), []).append(team)
    return [parts[k] for k in sorted(parts, reverse=True)]


def rank(teams, results, criteria=DEFAULT_CRITERIA, lot=(), byes=()):
    """Строки таблицы по местам. lot — порядок по жребию; равные без жребия получают общее место и tied."""
    rows = _table(teams, results, byes)
    if 'buchholz' in criteria:
        for r in results:
            if r.home in rows and r.away in rows:
                rows[r.home].buchholz += rows[r.away].points; rows[r.away].buchholz += rows[r.home].points
    lot_index = {team: i for i, team in enumerate(lot)}

    def order(group, start):
        if len(group) <= 1: return [group]
        i = start
        while i < len(criteria):
            criterion = criteria[i]
            if criterion == 'lot':
                if all(t in lot_index for t in group):
                    return [[t] for t in sorted(group, key=lot_index.__getitem__)]
                return [group]
            if criterion in H2H:
                end = i
                while end < len(criteria) and criteria[end] in H2H: end += 1
                block = criteria[i:end]
                mini = _table(group, [r for r in results if r.home in group and r.away in group])
                names = {'h2h_points': 'points', 'h2h_goal_diff': 'goal_diff', 'h2h_goals': 'goals_for'}
                parts = _split(group, lambda t: tuple(_value(mini[t], names[c]) for c in block))
                if len(parts) > 1:
                    # Разделившиеся подгруппы заново проходят личные встречи только между собой.
                    return [sub for part in parts for sub in order(part, i)]
                i = end; continue
            parts = _split(group, lambda t: _value(rows[t], criterion))
            if len(parts) > 1:
                return [sub for part in parts for sub in order(part, i + 1)]
            i += 1
        return [group]

    blocks = order(sorted(teams), 0)
    ranked = []; place = 1
    for block in blocks:
        for team in block:
            row = rows[team]; row.place = place; row.tied = len(block) > 1; ranked.append(row)
        place += len(block)
    return ranked


def rank_across(rows, lot=()):
    """Команды одного места из разных групп: очки, разница и забитые за матч, затем жребий.
    Возвращает порядок и функцию «граница после count мест зависит от жребия»."""
    lot_index = {team: i for i, team in enumerate(lot)}
    def key(row):
        games = max(row.played, 1)
        return (Fraction(row.points, games), Fraction(row.goal_diff, games), Fraction(row.goals_for, games))
    ordered = sorted(rows, key=lambda r: (tuple(-v for v in key(r)), lot_index.get(r.team, len(lot_index)), r.team))
    def cutoff_tied(count):
        if count >= len(ordered): return False
        a, b = ordered[count - 1], ordered[count]
        return key(a) == key(b) and not (a.team in lot_index and b.team in lot_index)
    return ordered, cutoff_tied
```

- [ ] **Шаг 4.** Запуск — PASS (при расхождении в составленных вручную примерах сначала пересчитать пример на бумаге, затем код). **Шаг 5.** Коммит `feat(stages): standings with head-to-head, Buchholz and lots`.

### Задача 4. Швейцарка и продвижение (`rules/swiss.py`, `rules/progress.py`)

**Файлы:** создать оба модуля; дополнить тест.

- [ ] **Шаг 1. Тесты.**

```python
from aifootball.service.stages.rules.swiss import swiss_pairs
from aifootball.service.stages.rules.progress import Leg, pair_winner, resolve_bracket, group_outcome
from aifootball.service.stages.rules.brackets import FixtureSpec


@pytest.mark.parametrize('n', [7, 8, 9, 10])
def test_swiss_four_rounds_without_rematches(n):
    rng = random.Random(n); teams = [str(i) for i in range(n)]; played = set(); byes = []; homes = Counter(); results = []
    for _ in range(4):
        ranked = [r.team for r in rank(teams, results, SWISS_CRITERIA, byes=[(b, 3) for b in byes])]
        pairs, bye = swiss_pairs(ranked, played, set(byes), homes)
        if bye: assert bye not in byes; byes.append(bye)
        for h, a in pairs:
            assert frozenset((h, a)) not in played; played.add(frozenset((h, a))); homes[h] += 1
            results.append(R(h, a, rng.randint(0, 4), rng.randint(0, 4)))


def test_pair_winner_aggregate_and_penalties():
    assert pair_winner(('A', 'B'), [Leg('B', 'A', 1, 0), Leg('A', 'B', 2, 0)], 2) == 'A'
    assert pair_winner(('A', 'B'), [Leg('B', 'A', 1, 0), Leg('A', 'B', 1, 0, 3, 4)], 2) == 'B'
    assert pair_winner(('A', 'B'), [Leg('B', 'A', 1, 0), Leg('A', 'B', 1, 0)], 2) is None
    assert pair_winner(('A', 'B'), [Leg('A', 'B', 1, 0)], 2) is None


def test_bracket_resolves_from_groups_and_separates_thirds():
    groups = [['a1', 'a2', 'a3'], ['b1', 'b2', 'b3'], ['c1', 'c2', 'c3']]
    results = {g: [R(t[0], t[1], 1, 0), R(t[0], t[2], 1, 0), R(t[1], t[2], g, 0)] for g, t in enumerate(groups, 1)}
    tables, outcome = group_outcome(groups, results, per_group=2, best=[{'place': 3, 'count': 2}], expected=[3, 3, 3])
    assert outcome.places[(1, 1)] == 'a1' and len(outcome.best) == 2
    specs = single_elim(group_scheme(3, 2, [{'place': 3, 'count': 2}]))
    pairs = resolve_bracket(specs, {}, outcome)
    for p in pairs.values():
        if p.home and p.away: assert p.home[0] != p.away[0]   # никто не играет с одногруппником в первом раунде


def test_group_places_wait_for_all_results_and_lot():
    groups = [['A', 'B', 'C']]
    _, outcome = group_outcome(groups, {1: [R('A', 'B', 1, 0)]}, expected=[3])
    assert outcome.places == {} and not outcome.complete


def test_grand_final_reset_only_after_lower_win():
    specs = double_elim([entry(t) for t in 'ABCD'], grand_final_reset=True)
    legs = {}
    def play(key, home, away, hg, ag): legs[key] = [Leg(home, away, hg, ag)]
    play('U1-1', 'A', 'D', 1, 0); play('U1-2', 'B', 'C', 1, 0); play('U2-1', 'A', 'B', 1, 0)
    play('L1-1', 'D', 'C', 1, 0); play('L2-1', 'D', 'B', 1, 0)
    play('F', 'A', 'D', 1, 0)
    assert resolve_bracket(specs, legs)['F2'].home is None
    play('F', 'A', 'D', 0, 1)
    assert resolve_bracket(specs, legs)['F2'].home == 'D'
```

- [ ] **Шаг 2.** Запуск — FAIL.
- [ ] **Шаг 3. Реализация** `stages/rules/swiss.py`:

```python
"""Пары очередного тура швейцарской системы: по очкам, без повторных встреч."""


def swiss_pairs(ranked, played, had_bye, home_games):
    """ranked — команды по текущей таблице; played — множество frozenset уже сыгранных пар.
    Возвращает (пары (хозяин, гость), отдыхающая команда или None) либо None, если пар без повторов нет."""
    def pair(rest):
        if not rest: return []
        first, others = rest[0], rest[1:]
        for i, other in enumerate(others):
            if frozenset((first, other)) in played: continue
            tail = pair(others[:i] + others[i + 1:])
            if tail is not None:
                # Хозяин — у кого меньше домашних матчей; при равенстве — выше в таблице.
                home, away = (first, other) if home_games.get(first, 0) <= home_games.get(other, 0) else (other, first)
                return [(home, away)] + tail
        return None
    candidates = [None] if len(ranked) % 2 == 0 else [t for t in reversed(ranked) if t not in had_bye] or list(reversed(ranked))
    for bye in candidates:
        result = pair([t for t in ranked if t != bye])
        if result is not None: return result, bye
    return None
```

и `stages/rules/progress.py`:

```python
"""Продвижение: кто играет в паре, кто прошёл дальше и что этап отдаёт следующему — всё вычисляется из результатов."""
from dataclasses import dataclass, field
from itertools import permutations
from aifootball.service.stages.rules.standings import rank, rank_across, Result, DEFAULT_CRITERIA


@dataclass(frozen=True)
class Leg:
    home: str
    away: str
    home_goals: int
    away_goals: int
    home_pens: int | None = None
    away_pens: int | None = None
    points: tuple[int, int, int] = (3, 1, 0)


@dataclass
class Outcome:
    """Что этап отдаёт следующему: места в группах, лучшие по месту, итоговые места."""
    places: dict = field(default_factory=dict)       # (group_no, place) -> team
    best: dict = field(default_factory=dict)         # (place, rank) -> team
    group_of: dict = field(default_factory=dict)     # team -> group_no
    final: dict = field(default_factory=dict)        # place -> team
    complete: bool = False


def pair_winner(teams, legs, expected_legs):
    """Победитель пары по сумме матчей; при равенстве — серия пенальти последнего матча; None — не определён."""
    if len(legs) < expected_legs: return None
    goals = {t: 0 for t in teams}
    for leg in legs:
        goals[leg.home] += leg.home_goals; goals[leg.away] += leg.away_goals
    a, b = teams
    if goals[a] != goals[b]: return a if goals[a] > goals[b] else b
    last = legs[-1]
    if last.home_pens is None or last.away_pens is None or last.home_pens == last.away_pens: return None
    return last.home if last.home_pens > last.away_pens else last.away


@dataclass
class PairState:
    key: str
    home: str | None
    away: str | None
    winner: str | None = None
    loser: str | None = None
    legs: list = field(default_factory=list)


def resolve_source(source, pairs, prior):
    if source is None: return None
    if 'entry' in source: return source['entry']
    if 'winner' in source:
        pair = pairs.get(source['winner']); return pair.winner if pair else None
    if 'loser' in source:
        pair = pairs.get(source['loser']); return pair.loser if pair else None
    if prior is None: return None
    if 'group' in source: return prior.places.get((source['group'], source['place']))
    if 'best' in source: return prior.best.get((source['best'], source['rank']))
    if 'stage_place' in source: return prior.final.get(source['stage_place'])
    return None


def resolve_bracket(fixtures, legs_by_key, prior=None):
    """fixtures — пары этапа (ключ, источники, bye, номер матча). legs_by_key[key] — сыгранные матчи пары по порядку.
    Пары обходятся в порядке раундов, поэтому источники «победитель/проигравший» уже вычислены."""
    prior = _separate_best(fixtures, prior)
    pairs = {}
    by_key = {}
    for f in fixtures: by_key.setdefault(f.key, []).append(f)
    order = sorted(by_key, key=lambda k: (_stage_order(by_key[k][0]), k))
    for key in order:
        group = sorted(by_key[key], key=lambda f: f.leg)
        main = group[-1]  # последний матч пары хранит стороны в порядке посева
        home = resolve_source(main.home, pairs, prior); away = resolve_source(main.away, pairs, prior)
        state = PairState(key, home, away)
        if main.bye:
            state.winner = home
        elif home and away:
            legs = [l for l in legs_by_key.get(key, []) if {l.home, l.away} == {home, away}]
            state.legs = legs
            state.winner = pair_winner((home, away), legs, len(group))
            if state.winner: state.loser = away if state.winner == home else home
        pairs[key] = state
    if 'F2' in pairs and pairs.get('F') and pairs['F'].winner and pairs['F'].winner == pairs['F'].home:
        # Переигровка не нужна: финал выиграла команда из верхней сетки.
        pairs['F2'] = PairState('F2', None, None)
    return pairs


def _stage_order(f):
    # Нижняя сетка идёт после верхнего раунда, из которого получает проигравших; финалы — в конце.
    weight = {'upper': 0, 'third': 0.5, 'lower': 0.25, 'final': 1000, 'final_reset': 1001}.get(f.bracket, 0)
    if f.bracket == 'lower': return (f.round_no + 1) / 2 + weight
    return f.round_no + weight


def _separate_best(fixtures, prior):
    """Лучшие команды одного места меняются местами между собой, чтобы не играть с победителем своей группы."""
    if prior is None or not prior.best: return prior
    first = [f for f in fixtures if f.round_no == 1 and f.bracket in (None, 'upper') and not f.bye]
    slots = sorted({(s['best'], s['rank']) for f in first for s in (f.home, f.away) if s and 'best' in s})
    teams = [prior.best.get(slot) for slot in slots]
    if not slots or None in teams: return prior
    def conflicts(assign):
        mapping = dict(zip(slots, assign)); total = 0
        for f in first:
            sides = [mapping.get((s['best'], s['rank'])) if s and 'best' in s else s for s in (f.home, f.away)]
            groups = [prior.group_of.get(x) if isinstance(x, str) else x.get('group') if isinstance(x, dict) else None for x in sides]
            if groups[0] is not None and groups[0] == groups[1]: total += 1
        return total
    choice = min(permutations(teams), key=conflicts) if len(teams) <= 8 else teams
    best = dict(prior.best); best.update(zip(slots, choice))
    return Outcome(prior.places, best, prior.group_of, prior.final, prior.complete)


def group_outcome(groups, results, criteria=DEFAULT_CRITERIA, lots=None, per_group=0, best=(), expected=None):
    """groups — составы групп; results[g] — результаты группы; expected[g] — число пар группы.
    Возвращает (таблицы, Outcome). Места группы известны, когда сыграны все её пары и нет равенства без жребия."""
    lots = lots or {}; tables = []; outcome = Outcome()
    for g, teams in enumerate(groups, 1):
        rows = rank(teams, results.get(g, []), criteria, lots.get(g, ()))
        tables.append(rows)
        done = expected is None or len(results.get(g, [])) >= expected[g - 1]
        for row in rows:
            outcome.group_of[row.team] = g
            if done and not row.tied: outcome.places[(g, row.place)] = row.team
    all_done = all(expected is None or len(results.get(g, [])) >= expected[g - 1] for g in range(1, len(groups) + 1))
    for item in best:
        candidates = [r for rows in tables for r in rows if r.place == item['place'] and not r.tied]
        ordered, cutoff_tied = rank_across(candidates, lots.get(f"best-{item['place']}", ()))
        if all_done and len(candidates) == len(groups) and not cutoff_tied(item['count']):
            for i, row in enumerate(ordered[:item['count']], 1): outcome.best[(item['place'], i)] = row.team
    outcome.complete = all_done
    if all_done and len(groups) == 1:
        outcome.final = {row.place: row.team for row in tables[0] if not row.tied}
    return tables, outcome
```

- [ ] **Шаг 4.** Запуск всего `test_stage_rules.py` — PASS. **Шаг 5.** Коммит `feat(stages): swiss pairing and bracket progression`.

### Задача 5. Модели и миграция

**Файлы:** создать `stages/models.py`, `migrations/versions/0027_tournament_stages.py`; изменить `tournaments/models.py`, `tournaments/schemas.py` (`TournamentPatch.standings_public: bool|None`), `views.py` (поле `standings_public` в `TournamentView` и `PublicTournament`); тест `tests/service/test_migrations.py` (дополнить), `tests/service/test_stages_api.py`.

- [ ] **Шаг 1. Тест миграции** — в `test_migrations.py` добавить проверку, что `stages`, `stage_draws`, `fixtures` существуют и `tournaments.standings_public` по умолчанию `true` (по образцу соседних тестов этого файла: `inspect(engine).get_table_names()`).
- [ ] **Шаг 2.** Запуск — FAIL.
- [ ] **Шаг 3. Модели** (`stages/models.py`, стиль как в `tournaments/models.py`):

```python
from sqlalchemy import Column,String,Integer,Boolean,Uuid,ForeignKey,DateTime,UniqueConstraint,CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from aifootball.service.db import Base,Entity,utcnow


class Stage(Entity,Base):
    __tablename__='stages'
    tournament_id=Column(Uuid,ForeignKey('tournaments.id',name='fk_stage_tournament'),nullable=False)
    position=Column(Integer,nullable=False)
    name=Column(String(100),nullable=False)
    kind=Column(String(20),nullable=False)
    regulation_id=Column(Uuid,ForeignKey('regulations.id',name='fk_stage_regulation'),nullable=False)
    config=Column(JSONB,nullable=False)
    lots=Column(JSONB,nullable=False,default=dict,server_default='{}')
    revision=Column(Integer,nullable=False,default=0)
    __table_args__=(UniqueConstraint('tournament_id','position',name='uq_stage_position'),
        CheckConstraint("kind in ('round_robin','groups','single_elim','double_elim','swiss')",name='ck_stage_kind'))


class StageDraw(Entity,Base):
    __tablename__='stage_draws'
    stage_id=Column(Uuid,ForeignKey('stages.id',name='fk_draw_stage'),nullable=False)
    version=Column(Integer,nullable=False)
    method=Column(String(20),nullable=False)
    seed=Column(Integer,nullable=False)
    seeding=Column(JSONB,nullable=False)
    placement=Column(JSONB,nullable=False)
    confirmed_by=Column(Uuid,ForeignKey('admins.id',name='fk_draw_admin'),nullable=False)
    confirmed_at=Column(DateTime(timezone=True),nullable=False,default=utcnow)
    __table_args__=(UniqueConstraint('stage_id','version',name='uq_stage_draw_version'),)


class Fixture(Entity,Base):
    __tablename__='fixtures'
    stage_id=Column(Uuid,ForeignKey('stages.id',name='fk_fixture_stage'),nullable=False)
    draw_id=Column(Uuid,ForeignKey('stage_draws.id',name='fk_fixture_draw'),nullable=False)
    key=Column(String(20),nullable=False)
    leg=Column(Integer,nullable=False,default=1)
    group_no=Column(Integer)
    round_no=Column(Integer,nullable=False)
    bracket=Column(String(20))
    slot=Column(Integer,nullable=False,default=0)
    home_entry_id=Column(Uuid,ForeignKey('entries.id',name='fk_fixture_home'))
    away_entry_id=Column(Uuid,ForeignKey('entries.id',name='fk_fixture_away'))
    home_source=Column(JSONB)
    away_source=Column(JSONB)
    bye=Column(Boolean,nullable=False,default=False)
    match_id=Column(Uuid,ForeignKey('matches.id',name='fk_fixture_match'),unique=True)
    __table_args__=(UniqueConstraint('draw_id','key','leg',name='uq_fixture_key'),
        CheckConstraint('home_entry_id is null or away_entry_id is null or home_entry_id != away_entry_id',name='ck_fixture_teams'))
```

`tournaments/models.py`: `standings_public=Column(Boolean,nullable=False,default=True,server_default='true')`.

- [ ] **Шаг 4. Миграция** `0027_tournament_stages.py` (`down_revision='0026_registration_credentials'`; ревизию взять из заголовка `0026`): `op.create_table` для трёх таблиц с теми же колонками, ограничениями и индексами `ix_fixtures_stage_id`, `ix_stages_tournament_id`; `op.add_column('tournaments', sa.Column('standings_public', sa.Boolean(), nullable=False, server_default='true'))`; `downgrade` удаляет в обратном порядке.
- [ ] **Шаг 5.** `.venv/bin/python -m pytest tests/service/test_migrations.py -q` — PASS. Коммит `feat(stages): stages, draws and fixtures schema`.

### Задача 6. Настройки этапов и шаблоны (`schemas.py`)

**Файлы:** создать `stages/schemas.py`; тест в `test_stages_api.py`.

- [ ] **Шаг 1. Тест** проверяет Pydantic-схемы напрямую:

```python
import pytest
from pydantic import ValidationError
from aifootball.service.stages.schemas import StageConfig, template_stages


def test_config_validation():
    StageConfig.model_validate({'kind': 'groups', 'group_count': 4, 'advance': {'per_group': 2, 'best': []}})
    with pytest.raises(ValidationError): StageConfig.model_validate({'kind': 'groups', 'group_count': 1})
    with pytest.raises(ValidationError): StageConfig.model_validate({'kind': 'round_robin', 'criteria': ['points', 'magic']})


def test_groups_playoff_template_links_stages():
    stages = template_stages('groups_playoff', {'group_count': 2, 'per_group': 2, 'third_place': True})
    assert [s['kind'] for s in stages] == ['groups', 'single_elim']
    assert stages[1]['config']['source'] == {'previous': True}
```

- [ ] **Шаг 2.** Запуск — FAIL.
- [ ] **Шаг 3. Реализация.** Ключевые типы:

```python
from typing import Annotated, Literal
from uuid import UUID, uuid4
from pydantic import Field, model_validator
from aifootball.service.tournaments.schemas import Input

Criterion=Literal['points','h2h_points','h2h_goal_diff','h2h_goals','goal_diff','goals_for','wins','buchholz','lot']
Kind=Literal['round_robin','groups','single_elim','double_elim','swiss']
Template=Literal['league','groups_playoff','playoff','double_elim','swiss']


class Best(Input):
    place: Annotated[int,Field(ge=1,le=20)]
    count: Annotated[int,Field(ge=1,le=32)]


class Advance(Input):
    per_group: Annotated[int,Field(ge=0,le=32)]=0
    best: list[Best]=Field(default_factory=list,max_length=3)


class StageConfig(Input):
    kind: Kind
    legs: Literal[1,2]=1
    criteria: list[Criterion]|None=None       # None — по умолчанию для вида
    source: dict=Field(default_factory=lambda:{'entries':'all'})  # {'entries':'all'|[ids]} или {'previous':True}
    group_count: Annotated[int,Field(ge=2,le=16)]|None=None
    advance: Advance=Field(default_factory=Advance)
    third_place: bool=False
    two_leg_rounds: list[Annotated[int,Field(ge=1,le=8)]]=Field(default_factory=list)
    grand_final_reset: bool=False
    rounds: Annotated[int,Field(ge=1,le=15)]|None=None

    @model_validator(mode='after')
    def coherent(self):
        if self.kind=='groups' and self.group_count is None: raise ValueError('Укажите число групп')
        if self.criteria is not None and (not self.criteria or self.criteria[0]!='points'):
            raise ValueError('Первым критерием должны быть очки')
        if 'buchholz' in (self.criteria or []) and self.kind!='swiss': raise ValueError('Бухгольц — только для швейцарской системы')
        return self

    def effective_criteria(self):
        from aifootball.service.stages.rules.standings import DEFAULT_CRITERIA,SWISS_CRITERIA
        return tuple(self.criteria or (SWISS_CRITERIA if self.kind=='swiss' else DEFAULT_CRITERIA))


class StageInput(Input):
    name: str=Field(min_length=1,max_length=100)
    regulation_id: UUID
    config: StageConfig


class FormatCreate(Input):
    request_id: UUID=Field(default_factory=uuid4)
    template: Template
    regulation_id: UUID
    playoff_regulation_id: UUID|None=None
    group_count: Annotated[int,Field(ge=2,le=16)]=2
    per_group: Annotated[int,Field(ge=1,le=16)]=2
    best_thirds: Annotated[int,Field(ge=0,le=16)]=0
    legs: Literal[1,2]=1
    playoff_teams: Annotated[int,Field(ge=2,le=64)]|None=None   # для «лига → плей-офф»
    third_place: bool=False
    grand_final_reset: bool=False
    rounds: Annotated[int,Field(ge=1,le=15)]|None=None


class DrawInput(Input):
    method: Literal['pots','snake','seeded','random','scheme','manual']
    seed: Annotated[int,Field(ge=0,le=2**31-1)]=0
    seeding: list[UUID]=Field(default_factory=list,max_length=128)
    placement: list[list[UUID|None]]|list[dict|None]|None=None    # группы списками или слоты сетки


class DrawConfirm(DrawInput):
    request_id: UUID=Field(default_factory=uuid4)
    expected_revision: int=Field(ge=0)


class LotInput(Input):
    request_id: UUID=Field(default_factory=uuid4)
    group: str=Field(min_length=1,max_length=20)   # номер группы или 'best-3'
    order: list[UUID]=Field(min_length=2,max_length=64)


class FixtureSchedule(Input):
    request_id: UUID=Field(default_factory=uuid4)
    scheduled_at: datetime
    hall_id: UUID
    camera_profile_id: UUID|None=None
    venue_label: str=Field(default='',max_length=200)
    referees: list[str]=Field(default_factory=list,max_length=10)
    broadcast_url: str|None=None
    broadcast_embed_url: str|None=None


class FixtureReplace(Input):
    request_id: UUID=Field(default_factory=uuid4)
    side: Literal['home','away']
    entry_id: UUID
```

`template_stages(template, params)` возвращает список словарей `{'name','kind','config'}`: `league` → один `round_robin` («Лига»); `groups_playoff` → `groups` («Групповой этап») + `single_elim` («Плей-офф», `source={'previous':True}`); `playoff` → `single_elim`; `double_elim` → `double_elim`; `swiss` → `swiss`. Если в `league`/`swiss` задан `playoff_teams` — добавляется `single_elim` с `source={'previous':True}`. `FixtureSchedule` повторно использует валидаторы VK и часового пояса из `matches/schemas.py` (`BroadcastFields`, `MatchCreate.aware`).

- [ ] **Шаг 4.** Запуск — PASS. **Шаг 5.** Коммит `feat(stages): stage config, templates and request schemas`.

### Задача 7. Генерация пар этапа (`generate.py`)

**Файлы:** создать `stages/generate.py`; тест в `test_stage_rules.py`.

Связывает настройки с правилами. Функции:
- `participants_placement(config, method, seeding, seed, prior_count)` → `placement`: для `groups` — список групп (списки id заявок), для сеток — список источников по силе (`{'entry': id}` или источники схемы), для круговых и швейцарки — порядок команд;
- `fixtures_for(config, placement)` → `list[FixtureSpec]`: `round_robin` — `round_robin(order, legs)`; `groups` — `round_robin(group, legs, group_no=g)` по каждой группе; `single_elim` — `single_elim(placement, third_place, two_leg_rounds)`; `double_elim` — `double_elim(placement, grand_final_reset)`; `swiss` — пары первого тура: верхняя половина посева против нижней (`S1-i`), отдых нижнему при нечётном числе (`bye=True`);
- `scheme_for(config, prior_stage)` — для этапа с `source.previous` после `groups`: `group_scheme(group_count, per_group, best)`; после `round_robin`/`swiss`: `[{'stage_place': n} for n in 1..playoff_teams]`.

- [ ] **Шаг 1. Тесты:**

```python
from aifootball.service.stages.generate import participants_placement, fixtures_for, scheme_for
from aifootball.service.stages.schemas import StageConfig


def test_groups_fixtures_have_group_numbers():
    config = StageConfig(kind='groups', group_count=2, advance={'per_group': 2})
    placement = participants_placement(config, 'snake', list('ABCDEFGH'), 0)
    specs = fixtures_for(config, placement)
    assert {s.group_no for s in specs} == {1, 2} and len(specs) == 12


def test_swiss_first_round_top_half_vs_bottom():
    config = StageConfig(kind='swiss', rounds=3)
    specs = fixtures_for(config, list('ABCDE'))
    assert [(s.home, s.away, s.bye) for s in specs] == [
        ({'entry': 'A'}, {'entry': 'C'}, False), ({'entry': 'B'}, {'entry': 'D'}, False), ({'entry': 'E'}, None, True)]


def test_scheme_after_groups():
    groups = StageConfig(kind='groups', group_count=2, advance={'per_group': 2})
    assert scheme_for(StageConfig(kind='single_elim', source={'previous': True}), groups)[:2] == [
        {'group': 1, 'place': 1}, {'group': 2, 'place': 1}]
```

- [ ] **Шаг 2–4.** FAIL → реализация → PASS. **Шаг 5.** Коммит `feat(stages): fixtures from stage config and draw placement`.

### Задача 8. Результаты матчей (`results.py`)

**Файлы:** создать `stages/results.py`; тест `tests/service/test_stages_api.py`.

`load_results(db, match_ids, scope)` → `dict[match_id, Leg]`:
- `scope='cabinet'` — последняя `ProtocolVersion` матча по `number`;
- `scope='public'` — версия `Match.published_version_id`;
- матчи со статусом `cancelled` пропускаются;
- `Leg(home=str(snapshot['home']['id']), away=…, home_goals=projection.effective_score.home, …, home_pens=protocol.shootout_totals.home, points=tuple(regulation.rules.points.values()))`, где `home`/`away` — id заявок из `snapshot['home']['id']`/`['away']['id']`; если счёт неполный (`None`) — результата нет.

- [ ] **Шаг 1. Тест** (использует фикстуры `match_factory`, `send_command`, `finish` из `test_confirmation.py`):

```python
from aifootball.service.stages.results import load_results
from sqlalchemy.orm import Session
from .test_confirmation import finish


def test_cabinet_sees_confirmed_public_sees_published(admin_client, match_factory, send_command):
    m = send_command(finish(send_command, match_factory()), 'confirm', {'acknowledge_incomplete': True}).json()
    with Session(admin_client.app.state.engine) as db:
        assert load_results(db, [m['id']], 'public') == {}
        leg = load_results(db, [m['id']], 'cabinet')[__import__('uuid').UUID(m['id'])]
        assert (leg.home_goals, leg.away_goals, leg.points) == (3, 2, (3, 1, 0))
```

- [ ] **Шаг 2–4.** FAIL → реализация → PASS. **Шаг 5.** Коммит `feat(stages): results from confirmed and published protocols`.

### Задача 9. Операции: формат, жеребьёвка, таблицы (`operations.py`)

**Файлы:** создать `stages/operations.py`; тест `test_stages_api.py` (через HTTP после задачи 10; в этой задаче — через функции и `Session`).

Функции и правила:
- `create_format(db, tournament, data)` — запрещено, если у турнира есть этап с жеребьёвкой (`409 format_locked`, «Формат нельзя изменить: жеребьёвка уже проведена»); удаляет черновые этапы и создаёт этапы шаблона с `position` 1..n. Регламент плей-офф — `playoff_regulation_id` или общий.
- `stage_state(db, tournament, scope)` — обходит этапы по `position`: текущая жеребьёвка (максимальная `version`), её пары, результаты `load_results` по `fixture.match_id`, затем:
  - круговой/группы: `group_outcome(groups, results_by_group, criteria, lots, per_group, best, expected)`; результаты групп — `Result(leg.home, leg.away, …, points=leg.points)` для пар с матчем и результатом;
  - сетки: `resolve_bracket(specs, legs_by_key, prior_outcome)`; `legs_by_key` в порядке `leg`;
  - швейцарка: таблица по всем турам с отдыхом `byes=[(team, win_points)]`; `Outcome.final`, когда сыграны все `rounds` туров;
  - статус: `draft`/`drawn`/`started`/`completed` по §5 спецификации (`started` — есть хотя бы одна подтверждённая версия протокола у матча пары, независимо от `scope`).
  Результат — представление `standings` из §7 спецификации, плюс для кабинета у пар: `fixture_id`, `match_id`, `can_schedule`, `changed` («Результат изменился»: зафиксированная команда ≠ вычисленной).
- `implicit_standings(db, tournament, scope)` — турнир без этапов: все матчи турнира, `rank(entries, results, DEFAULT_CRITERIA)`, `implicit=True`.
- `preview_draw(db, stage, data)` — без записи: `participants_placement`/`scheme_for` → `fixtures_for` → пары с подписями команд; последствия для назначенных матчей (`kept`, `cancelled`) по совпадению `(key, leg, home, away)`.
- `confirm_draw(db, actor, stage, data)` — блокирует этап (`get_entity(..., lock=True)`), проверяет `expected_revision`, запрещает при подтверждённом протоколе в этапе (`409 draw_locked`); для `manual` проверяет, что каждая заявка участника встречается ровно один раз; создаёт `StageDraw(version+1)` и `Fixture` из `FixtureSpec` (`home_entry_id` = `source['entry']`, если источник — заявка); переносит `match_id` со старых пар при совпадении `(key, leg, home, away)`, иначе ставит матчу `status='cancelled'`; `stage.revision += 1`. Обёрнуто в `setup_command(..., 'stage-draw', ...)`.
- `set_lot(db, stage, data)` — пишет порядок в `stage.lots[group]`; проверяет, что команды действительно равны в этой группе.
- `schedule_fixture(db, actor, fixture, data)` — вычисляет команды (кабинет); если одной нет — `422 opponent_unknown` «Соперник ещё не известен»; если у пары уже есть матч — `409`; иначе `create_match` из `matches/operations.py` с `MatchCreate(home_entry_id, away_entry_id, regulation_id=stage.regulation_id, stage_label=label, ...)`, затем фиксирует команды в паре и `fixture.match_id`. Подпись: группы — «Группа A · Тур 2», лига — «Тур 2», сетка — «1/8 финала», «1/4 финала», «Полуфинал», «Финал», «Матч за 3-е место», нижняя сетка — «Нижняя сетка · Раунд 3», «Гранд-финал», «Переигровка финала», швейцарка — «Тур 2»; для двух матчей добавляется «· Матч 1/2».
- `replace_team(db, fixture, data)` — запрещено, если у матча пары есть подтверждённый протокол; меняет заявку в паре и в матче (`home_entry_id`/`away_entry_id`, затем `match.revision += 1`).
- `next_swiss_round(db, actor, stage)` — требует подтверждённых результатов всех пар последнего тура и `round < rounds`; `swiss_pairs(...)` по кабинетной таблице; создаёт пары `S{r}-{i}` в текущей жеребьёвке; при `None` — `409 swiss_exhausted` «Пары без повторов больше не составить».

- [ ] **Шаг 1. Тест на уровне функций** (полный сценарий групп → плей-офф проверяется в задаче 10 через HTTP):

```python
def test_preview_is_pure_and_confirm_creates_fixtures(stage_env):
    db, stage, entries, admin = stage_env(kind='groups', teams=8, group_count=2)
    preview = preview_draw(db, stage, DrawInput(method='pots', seed=3, seeding=entries))
    assert len(preview['groups']) == 2 and db.scalar(select(func.count()).select_from(Fixture)) == 0
    confirm_draw(db, admin, stage, DrawConfirm(method='pots', seed=3, seeding=entries, expected_revision=0))
    assert db.scalar(select(func.count()).select_from(Fixture)) == 12
```

`stage_env` — фикстура в `test_stages_api.py`: создаёт через HTTP турнир, регламент, N заявок (`/api/v1/teams`, `/api/v1/tournaments/{tid}/entries`), формат и возвращает `Session`, этап, id заявок, администратора.

- [ ] **Шаг 2–4.** FAIL → реализация → PASS. **Шаг 5.** Коммит `feat(stages): format, draw, standings operations`.

### Задача 10. API кабинета и зрителя

**Файлы:** создать `stages/routes.py`, `stages/public_routes.py`; изменить `app.py` (подключить оба роутера рядом с `tournament_router` и `public_router`), `tournaments/routes.py` (`standings_public` в PATCH уже проходит через `TournamentPatch`); тесты `test_stages_api.py`, `test_standings_public.py`.

Эндпоинты — §7 спецификации; все изменения в `with db.begin():` и через `setup_command` (виды `stage-format`, `stage-draw`, `stage-lot`, `fixture-schedule`, `fixture-replace`, `stage-next-round`). Публичные — через `require_public_tournament`.

- [ ] **Шаг 1. Тесты API** (`test_stages_api.py`):

```python
def test_groups_playoff_flow(admin_client, format_env, send_command):
    env = format_env(template='groups_playoff', teams=8, group_count=2, per_group=2)
    groups, playoff = env['stages']
    draw = {'method': 'pots', 'seed': 5, 'seeding': env['entries']}
    preview = admin_client.post(f"/api/v1/stages/{groups['id']}/draw/preview", json=draw)
    assert preview.status_code == 200 and len(preview.json()['groups']) == 2
    # Ручной обмен: меняем местами первые команды двух групп.
    placement = preview.json()['placement']; placement[0][0], placement[1][0] = placement[1][0], placement[0][0]
    body = {**draw, 'method': 'manual', 'placement': placement, 'expected_revision': groups['revision'], 'request_id': str(uuid4())}
    first = admin_client.post(f"/api/v1/stages/{groups['id']}/draw", json=body)
    again = admin_client.post(f"/api/v1/stages/{groups['id']}/draw", json=body)
    assert first.status_code == 200 and again.json() == first.json()          # идемпотентность
    scheme = admin_client.post(f"/api/v1/stages/{playoff['id']}/draw", json={'method': 'scheme', 'expected_revision': 0,
                                                                             'request_id': str(uuid4())})
    assert scheme.status_code == 200
    fixtures = admin_client.get(f"/api/v1/tournaments/{env['tid']}/fixtures?unscheduled=true").json()['items']
    semi = next(f for f in fixtures if f['key'] == 'U1-1')
    assert admin_client.post(f"/api/v1/fixtures/{semi['id']}/schedule", json=env['slot']).status_code == 422  # соперник неизвестен
    group_fixture = next(f for f in fixtures if f['group_no'] == 1)
    match = admin_client.post(f"/api/v1/fixtures/{group_fixture['id']}/schedule", json=env['slot']).json()
    assert match['stage_label'].startswith('Группа A · Тур')
    confirm_result(send_command, match, 2, 1)
    locked = admin_client.post(f"/api/v1/stages/{groups['id']}/draw", json={**body, 'request_id': str(uuid4())})
    assert locked.status_code == 409


def test_redraw_keeps_matching_and_cancels_others(admin_client, format_env):
    ...  # назначить две пары, перетянуть с другим зерном, проверить preview['consequences'] и статусы матчей


def test_result_change_marks_fixture(admin_client, format_env, send_command):
    ...  # плей-офф 4 команды: результат U1-1, назначить финал, изменить результат U1-1 → в standings у F changed=True;
         # replace → матч финала получает новую команду


def test_swiss_next_round_requires_results(admin_client, format_env, send_command):
    ...  # 6 команд, 3 тура: next-round до результатов → 409; после — пары тура 2 без повторов


def test_lot_resolves_tie(admin_client, format_env, send_command):
    ...  # круговая ничья трёх → needs_lot; POST lots → места определены
```

Каждый `...` в тестах при реализации раскрывается в полноценные проверки по описанию в комментарии; `confirm_result(send, match, home, away)` — помощник в этом же файле: `set_lineup` при необходимости, `set_totals`, `set_status ended`, `confirm`.

`test_standings_public.py`:

```python
def test_public_standings_only_published(admin_client, format_env, send_command, client):
    # Подтверждённый, но не опубликованный результат не виден зрителю ни в таблице, ни в продвижении.
    ...


def test_formatless_tournament_has_implicit_table_and_can_hide(admin_client, match_factory, send_command, client):
    m = match_factory(); m = send_command(finish(send_command, m), 'confirm', {'acknowledge_incomplete': True}).json()
    version = admin_client.get(f"/api/v1/matches/{m['id']}/versions").json()['items'][0]
    send_command(m, 'publish', {'version_id': version['id']})
    r = client.get(f"/api/v1/public/tournaments/{m['tournament_id']}/standings").json()
    assert r['implicit'] and r['stages'][0]['groups'][0]['rows'][0]['points'] == 3
    t = admin_client.get(f"/api/v1/tournaments/{m['tournament_id']}").json()
    admin_client.patch(f"/api/v1/tournaments/{t['id']}", json={'expected_revision': t['revision'], 'standings_public': False})
    assert client.get(f"/api/v1/public/tournaments/{m['tournament_id']}/standings").json()['stages'] == []
```

- [ ] **Шаг 2.** `.venv/bin/python -m pytest tests/service/test_stages_api.py tests/service/test_standings_public.py -q` — FAIL.
- [ ] **Шаг 3.** Реализация роутеров.
- [ ] **Шаг 4.** Те же тесты — PASS; затем весь бэкенд `.venv/bin/python -m pytest --tb=line -q` — PASS.
- [ ] **Шаг 5.** OpenAPI и типы:

```bash
.venv/bin/python scripts/export_service_openapi.py --output data/service/openapi.json
npm --prefix web run types:api
```

- [ ] **Шаг 6.** Коммит `feat(stages): organizer and public stage API`.

### Задача 11. Показ таблиц и сетки (фронтенд, общий)

**Файлы:** создать `web/src/features/stages/{api.ts,labels.ts,GroupTable.tsx,Bracket.tsx,StandingsView.tsx,stages.css}` и тесты `GroupTable.test.tsx`, `Bracket.test.tsx`.

- `api.ts`: `export type Standings=S['StandingsView']`, `StageView`, `PairView`, `RowView`, `FixtureView`; функции `loadStandings(tid, scope)`.
- `labels.ts`: `groupName(n)` → «Группа A»; `sourceLabel(src)` → «A1», «Победитель пары 3», «Лучшая 3-я №1», «Место 2»; `roundName(bracket, round, total)` → «1/4», «Полуфинал», «Финал», «Матч за 3-е место», «Нижняя · Раунд 2», «Гранд-финал».
- `GroupTable` — `<table>` с колонками «№, Команда, И, О»; строка — кнопка-раскрытие (`aria-expanded`), раскрытая строка показывает «В Н П · Мячи 7:3»; от 600 px CSS показывает все колонки (`@media (min-width:600px)`). Зона выхода: `data-zone="advance"` → полоса `border-inline-start: 3px solid var(--accent)`. Подпись под таблицей: «Места: очки → личные встречи → разница → …» из `criteria`. Если есть `tied` — строка «Нужен жребий» (`role="status"`).
- `Bracket` — на узком экране `role="tablist"` с раундами и карточки пар; на широком — колонки раундов (`display:grid; grid-auto-flow:column`), горизонтальная прокрутка только внутри блока сетки (`overflow-x:auto` у контейнера, не у страницы). Карточка пары: две строки команд (логотип, название или подпись источника), счёт или дата/«Дата не назначена», победитель — `font-weight:600`. Для `double_elim` — переключатель «Верхняя · Нижняя · Финал». Пустой `F2` скрыт.
- `StandingsView` — по этапам: заголовок этапа, затем таблицы групп или сетка; для швейцарки и лиги — таблица и, под ней, ссылка «Туры» (пары по турам).

- [ ] **Шаг 1. Тесты:**

```tsx
it('раскрывает строку таблицы и показывает подпись критериев',async()=>{
 render(<GroupTable name="Группа A" criteria={['points','h2h_points','goal_diff','lot']} rows={[row('Север',1,'advance'),row('Юг',2,null)]}/>);
 expect(screen.getByText('Места: очки → личные встречи → разница мячей → жребий')).toBeInTheDocument();
 await userEvent.click(screen.getByRole('button',{name:/Север/}));
 expect(screen.getByText(/Мячи 7:3/)).toBeVisible();
});
it('переключает раунды сетки',async()=>{
 render(<Bracket sections={sample}/>);
 await userEvent.click(screen.getByRole('tab',{name:'Финал'}));
 expect(screen.getByText('Дата не назначена')).toBeInTheDocument();
});
```

- [ ] **Шаг 2–4.** `npm --prefix web run test -- stages` FAIL → реализация → PASS. **Шаг 5.** Коммит `feat(web): group tables and bracket`.

### Задача 12. Организатор: формат, жеребьёвка, вкладка «Таблица», назначение пар

**Файлы:** создать `FormatStep.tsx`, `DrawStep.tsx`, `StageWorkspace.tsx`, `UnscheduledFixtures.tsx`, `ScheduleFixtureForm.tsx` и тесты `FormatStep.test.tsx`, `DrawStep.test.tsx`; изменить `TournamentSetup.tsx`, `TournamentWorkspace.tsx`, `navigation/rail.tsx`, `TournamentSetup.test.tsx`, `TournamentWorkspace.test.tsx`.

- `TournamentSetup`: `STEPS=[['rules','1. Регламент'],['teams','2. Команды'],['format','3. Формат'],['draw','4. Жеребьёвка'],['review','5. Проверка']]`; шаг «Проверка» добавляет строки «✓ Формат выбран», «✓ Жеребьёвка проведена». Кнопка «Продолжить» на шаге формата неактивна, пока формат не создан.
- `FormatStep`: пять карточек-радиокнопок (`role="radio"`) с названием, подписью в одну строку и маленькой схемой (CSS-полосы, без картинок): «Лига — каждый с каждым», «Группы и плей-офф», «Плей-офф», «Двойное выбывание», «Швейцарская система». Под выбранной — параметры словами: «Групп: 2 · Выходят из группы: 2 · Лучшие третьи: 0», «Круги: один / два», «Матч за 3-е место», «Переигровка финала», «Туров: 4», «В плей-офф выходят: 4» (для лиги/швейцарки — переключатель «Добавить плей-офф»). Регламент — выбор из регламентов турнира, для плей-офф отдельный выбор («Тот же»). Кнопка «Сохранить формат» → `POST /tournaments/{tid}/format` с `request_id` из `useDraft` (как в `TournamentCreate`). Если жеребьёвка проведена — карточки неактивны, подпись «Формат закреплён жеребьёвкой».
- `DrawStep`: по каждому этапу без жеребьёвки — список «Посев» (кнопки «Выше»/«Ниже» по 44 px, на широком экране также перетаскивание), выбор способа (сегменты «По корзинам · Змейкой» для групп, «По посеву · Случайно» для сеток, «По схеме» для этапа после групп), кнопка «Провести жеребьёвку» → `preview`. Предпросмотр: группы карточками (команда окрашена цветом своей корзины) или пары сетки; касание команды выделяет её, касание второй меняет их местами (метод становится `manual`); «Перетянуть» — новое `seed`; при повторной жеребьёвке — блок последствий «Сохранятся N назначенных матчей, M будут отменены». «Подтвердить жеребьёвку» → `POST draw`. Ошибка `409 draw_locked` показывает «Жеребьёвку нельзя изменить: в этапе уже есть подтверждённый результат».
- `StageWorkspace` (вкладка `table` кабинета, название «Таблица»): `StandingsView` по кабинетным данным + действия: «Провести жеребьёвку»/«Изменить жеребьёвку» (открывает `DrawStep` для этапа в `Modal`), «Ввести жребий» у группы с `tied` (диалог с порядком команд), «Следующий тур» для швейцарки, «Заменить команду» у пары с `changed`.
- `UnscheduledFixtures`: группировка «Группа A · Тур 2» / «Полуфинал»; строка «Север — Юг» или «Победитель A — B2»; кнопка «Назначить» активна при `can_schedule`, иначе подпись «Соперник ещё не известен». Во вкладке «Матчи» кабинета компонент выводится под `Schedule` с заголовком «Без даты».
- `ScheduleFixtureForm`: дата и время, зал (тот же выбор зала, что в `MatchCreateForm` — переиспользовать его поле зала, вынеся `HallField` из `matches/MatchForms.tsx`, если он ещё не отдельный), камера, трансляция; команды и регламент показаны текстом. `POST /fixtures/{id}/schedule`.
- `rail.tsx`: вкладка `table` с подписью «Таблица» перед «Матчи»; `readTournamentTab` принимает `table`.

- [ ] **Шаг 1. Тесты** (MSW-обработчики по образцу `TournamentWorkspace.test.tsx`):

```tsx
it('сохраняет формат «Группы и плей-офф» с параметрами',async()=>{
 const sent=captureJson('/api/v1/tournaments/t1/format');
 render(<FormatStep tid="t1" regulations={[reg]} stages={[]} onSaved={vi.fn()}/>);
 await userEvent.click(screen.getByRole('radio',{name:/Группы и плей-офф/}));
 await userEvent.clear(screen.getByLabelText('Групп'));await userEvent.type(screen.getByLabelText('Групп'),'4');
 await userEvent.click(screen.getByRole('button',{name:'Сохранить формат'}));
 expect(await sent).toMatchObject({template:'groups_playoff',group_count:4,per_group:2});
});
it('меняет две команды местами и подтверждает ручную жеребьёвку',async()=>{
 const sent=captureJson('/api/v1/stages/s1/draw');
 render(<DrawStep stage={groupsStage} entries={entries} onSaved={vi.fn()}/>);
 await userEvent.click(screen.getByRole('button',{name:'Провести жеребьёвку'}));
 await userEvent.click(await screen.findByRole('button',{name:'Север'}));
 await userEvent.click(screen.getByRole('button',{name:'Юг'}));
 await userEvent.click(screen.getByRole('button',{name:'Подтвердить жеребьёвку'}));
 expect((await sent).method).toBe('manual');
});
```

- [ ] **Шаг 2–4.** FAIL → реализация → PASS (`npm --prefix web run test`). **Шаг 5.** Коммит `feat(web): format step, draw and stage workspace`.

### Задача 13. Зритель: раздел «Таблица» и «Ещё без даты»

**Файлы:** изменить `web/src/features/public/PublicPages.tsx`; создать тест `web/src/features/stages/PublicStandings.test.tsx`.

- Разделы турнира: `table` («Таблица»), `matches`, `teams`, `ratings`. По умолчанию открывается `table`, если в `GET /public/tournaments/{tid}/standings` есть этапы; иначе `matches`. URL: `?tab=table` (как остальные разделы через `useQueryPatch`).
- В разделе «Матчи» под `<Schedule>` — `<UnscheduledFixtures mode="public">` с заголовком «Ещё без даты», если `GET /public/tournaments/{tid}/fixtures` не пуст.
- Проверка 375 px: нет горизонтальной прокрутки страницы (`document.documentElement.scrollWidth <= innerWidth` в E2E).

- [ ] **Шаг 1. Тест:** турнир с этапом открывается на «Таблице» и показывает «Группа A»; турнир без этапов и со скрытой таблицей открывается на «Матчах».
- [ ] **Шаг 2–4.** FAIL → реализация → PASS. **Шаг 5.** Коммит `feat(web): public standings and unscheduled pairs`.

### Задача 14. E2E

**Файлы:** создать `web/e2e/tournament-format.spec.ts` (помощники из `web/e2e/helpers.ts`).

Сценарий по §10 спецификации: вход организатора → новый турнир → регламент → 8 команд → «Группы и плей-офф» (2 группы, выходят по 2) → жеребьёвка по корзинам → обмен двух команд → подтверждение → «Таблица» показывает группы A и B → «Матчи → Без даты → Назначить» первой пары → протокол: счёт, «Завершён», подтверждение, публикация → зритель на `page.setViewportSize({width:375,height:812})` открывает турнир: раздел «Таблица», строка победителя с 3 очками, сетка «Полуфинал» с подписями «A1»/«B2»; `scrollWidth <= 375`. Второй тест: турнир без формата с опубликованным матчем показывает общую таблицу.

- [ ] **Шаг 1.** Написать спецификацию.
- [ ] **Шаг 2.** Собрать ветку отдельно и запустить изолированно (общий `web/dist` и порт 8000 не трогать):

```bash
npx --prefix web vite build --outDir /private/tmp/claude-501/aif-format-dist
AIF_E2E_PORT=8283 AIF_E2E_DATABASE_NAME=aifootball_format_e2e AIF_WEB_DIST=/private/tmp/claude-501/aif-format-dist npm --prefix web run test:e2e -- tournament-format
```

- [ ] **Шаг 3.** Прогнать весь E2E тем же способом. **Шаг 4.** Коммит `test(e2e): tournament format, draw, standings on phone width`.

### Задача 15. Документация, полная проверка, PR

- [ ] `README.md` — короткий раздел «Формат турнира и таблица» (шаблоны, жеребьёвка, назначение пар, что видит зритель); `docs/README.md` — ссылки на спецификацию и план.
- [ ] Полная проверка из `CONTRIBUTING.md`:

```bash
.venv/bin/python -m pytest --tb=line -q
npm --prefix web run test
npx --prefix web tsc -b
git diff --check
```

плюс E2E из задачи 14. Скриншоты зрителя на 375 px (таблица и сетка) приложить к PR, в Git не добавлять.
- [ ] Пуш ветки и PR в `main`: проблема (нет формата и таблицы), поведение, проверки, пересечение с PR #19 (`PublicPages.tsx` — добавлен раздел; `Schedule.tsx` не тронут).
