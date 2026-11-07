# Подсказки формата, сетка с датами и счётом, неполный состав, тёмная тема — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Цель:** организатору — подсказки при выборе формата и ручная правка состава (до жеребьёвки, до старта, снятие после старта); зрителю — сетка и матчи групп с датами и счётом каждого матча, дерево сетки на компьютере, тёмная тема по системной настройке.

**Архитектура:** продолжение пакета `aifootball.service.stages` в ветке `feat/tournament-format` (PR #20). Подсказки считает новый модуль `stages/estimate.py` теми же генераторами пар. Правки состава до старта — новая версия жеребьёвки (`method='manual'` с участниками). Снятие после старта — отметки `fixtures.outcome` и журнал `stage_withdrawals`; правила продвижения получают множество снявшихся. Фронтенд — компоненты в `web/src/features/stages/`, тёмная тема — токены `tokens.css` для `:root:has(.public-shell)`.

**Технологии:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, Pydantic 2; React 19, TypeScript, Vite, Vitest + Testing Library, Playwright.

Спецификация: [2026-10-27-tournament-format-ux-design.md](../specs/2026-10-27-tournament-format-ux-design.md).

---

## Карта файлов

Бэкенд (`src/aifootball/service/stages/`):
- создать `estimate.py` — автоподбор параметров, расчёт матчей/дней/предупреждений, правило «Рекомендуем»;
- создать `adjust.py` — правки состава до старта (убрать, добавить, перенести) поверх текущей жеребьёвки;
- создать `withdrawals.py` — предпросмотр и снятие команды после старта;
- изменить `rules/progress.py` — `group_outcome(..., removed, withdrawn)`, `resolve_bracket(..., withdrawn)`;
- изменить `models.py` — `StageDraw.participants`, `Fixture.outcome`, `StageWithdrawal`;
- изменить `schemas.py` — `EstimateInput`, `AdjustInput`, `WithdrawalInput`, `walkover_score`, поля представлений;
- изменить `operations.py` — участники, исход пары в таблицах, снявшиеся, `home_from`/`away_from`, текущий раунд;
- изменить `routes.py`; создать миграцию `migrations/versions/0028_stage_adjustments.py`.

Фронтенд (`web/src/features/stages/`):
- создать `Stepper.tsx`, `FormatHelp.tsx`, `ParticipantsPicker.tsx`, `RosterPanel.tsx`, `WithdrawDialog.tsx`, `BracketTree.tsx`, `GroupMatches.tsx`, `contrast.ts`;
- изменить `FormatStep.tsx`, `DrawStep.tsx`, `StageWorkspace.tsx`, `Bracket.tsx` (карточка пары и раунды на телефоне), `StandingsView.tsx`, `GroupTable.tsx`, `labels.ts`, `stages.css`;
- тёмная тема: `web/src/styles/tokens.css`, `styles.css` (публичная часть), `features/public/schedule.css`, `features/public/match-center/match-center.css`, `features/navigation/shell.css`, `features/public/profiles.css`, `features/match-report/report.css`, `features/stages/stages.css`; `docs/design/2026-10-15-ui-system.md`.

Тесты: `tests/service/test_stage_estimate.py`, `tests/service/test_stage_adjust.py`, `tests/service/test_stage_withdrawals.py`, дополнение `tests/service/test_stage_rules.py`; `web/src/features/stages/{FormatStep,RosterPanel,PairCard,BracketTree}.test.tsx`, `web/src/styles/tokens.test.ts`; `web/e2e/tournament-format.spec.ts` (дополнение), `web/e2e/public-dark.spec.ts`.

Команда тестов бэкенда: `.venv/bin/python -m pytest <файл> -q` (база `aifootball_test`). Фронтенд: `npm --prefix web run test -- <имя>`. E2E — только на отдельной сборке, см. задачу 12.

---

### Задача 1. Расчёт подсказок (`estimate.py`)

**Файлы:** создать `stages/estimate.py`, `tests/service/test_stage_estimate.py`; изменить `schemas.py` (`EstimateInput`, `EstimateView`), `routes.py`.

- [ ] **Шаг 1. Тесты.**

```python
import pytest
from aifootball.service.stages.estimate import auto_params, estimate, estimate_all
from aifootball.service.stages.schemas import template_stages, StageConfig
from aifootball.service.stages.generate import fixtures_for, scheme_for, qualifier_count


def real_matches(template, params, n):
    """Число пар, которые реально создаст жеребьёвка этих параметров."""
    stages = [StageConfig.model_validate(s['config']) for s in template_stages(template, params)]
    teams = [f't{i}' for i in range(n)]; total = 0; prior = None
    for config in stages:
        if config.source.get('previous'):
            placement = scheme_for(config, prior)
        elif config.kind == 'groups':
            from aifootball.service.stages.rules.draws import snake_draw
            placement = snake_draw(teams, config.group_count)
        elif config.kind in ('single_elim', 'double_elim'):
            placement = [{'entry': t} for t in teams]
        else:
            placement = teams
        specs = [s for s in fixtures_for(config, placement) if not s.bye and s.bracket != 'final_reset']
        total += len(specs) if config.kind != 'swiss' else (config.rounds or (n - 1).bit_length()) * (n // 2)
        prior = config
    return total


@pytest.mark.parametrize('n', [4, 5, 6, 7, 8, 11, 14, 16, 20, 24])
@pytest.mark.parametrize('template', ['league', 'groups_playoff', 'playoff', 'double_elim', 'swiss'])
def test_matches_equal_real_fixtures(template, n):
    params = auto_params(template, n)
    assert estimate(template, params, n)['matches'] == real_matches(template, params, n)


def test_auto_groups_have_at_least_four_teams_and_power_of_two_playoff():
    p = auto_params('groups_playoff', 14)
    assert (p['group_count'], p['per_group'], p['best_thirds']) == (3, 2, 2)


def test_days_with_matches_per_day():
    league = estimate('league', auto_params('league', 6), 6)
    assert league['rounds'] == 5 and league['days'] == 5
    assert estimate('league', auto_params('league', 6), 6, per_day=2)['days'] == 10     # 3 матча тура → 2 дня


@pytest.mark.parametrize('n,days,expected', [(4, None, 'league'), (6, None, 'league'), (8, None, 'groups_playoff'),
                                             (14, 6, 'groups_playoff'), (14, 20, 'league'), (20, 3, 'playoff')])
def test_recommendation_rule(n, days, expected):
    cards = estimate_all(n, days=days, per_day=8)
    assert [c['template'] for c in cards if c['recommended']] == [expected]


def test_warnings_and_fix():
    card = estimate('groups_playoff', {'group_count': 4, 'per_group': 2}, 7)
    assert card['fix'] == {'group_count': 3}
    assert any('минимум 8 команд' in w for w in card['warnings'])
    assert any('пропуск' in w.lower() or 'второго раунда' in w for w in estimate('playoff', {}, 6)['warnings'])
```

- [ ] **Шаг 2.** Запуск — FAIL.
- [ ] **Шаг 3. Реализация** `stages/estimate.py`:

```python
"""Подсказки при выборе формата: матчи, игровые дни, предупреждения и рекомендация — теми же генераторами пар."""
import random
from math import ceil
from aifootball.service.stages.schemas import template_stages, StageConfig, ELIMINATION
from aifootball.service.stages.generate import fixtures_for, scheme_for
from aifootball.service.stages.rules.brackets import bracket_size
from aifootball.service.stages.rules.draws import snake_draw, group_sizes
from aifootball.service.stages.rules.progress import Leg, resolve_bracket

TEMPLATES = ('league', 'groups_playoff', 'playoff', 'double_elim', 'swiss')
ORDER = {t: i for i, t in enumerate(TEMPLATES)}


def auto_params(template, n):
    if template == 'groups_playoff':
        groups = max(2, n // 4) if n >= 8 else 2
        qualifiers = 2 * groups; target = bracket_size(qualifiers)
        best = target - qualifiers if target - qualifiers <= groups and n - qualifiers >= target - qualifiers else 0
        return {'group_count': groups, 'per_group': 2, 'best_thirds': best, 'legs': 1}
    if template == 'league': return {'legs': 1}
    if template == 'swiss': return {'rounds': max(1, (n - 1).bit_length())}
    return {}


def _placement(config, prior, teams):
    if config.source.get('previous'): return scheme_for(config, prior)
    if config.kind == 'groups': return snake_draw(teams, config.group_count)
    if config.kind in ELIMINATION: return [{'entry': t} for t in teams]
    return teams


def _per_team_elimination(specs, teams, rng):
    """Матчей у команды в сетке: от и до по 30 случайным прогонам (сетка ≤ 64 команд — быстро)."""
    low, high = None, 0
    for _ in range(30):
        legs = {}
        for _ in range(64):
            pairs = resolve_bracket(specs, legs)
            todo = [p for p in pairs.values() if p.home and p.away and p.winner is None and p.key not in legs]
            if not todo: break
            for p in todo: legs[p.key] = [Leg(p.home, p.away, *rng.choice([(1, 0), (0, 1)]))]
        played = {t: 0 for t in teams}
        for key, items in legs.items():
            for leg in items: played[leg.home] += 1; played[leg.away] += 1
        low = min(played.values()) if low is None else min(low, min(played.values()))
        high = max(high, max(played.values()))
    return low or 0, high


def _elimination_range(config, specs, count, rng):
    """Матчей у команды в сетке. Первый этап — прогоном; сетка из предыдущего этапа — от 1 до числа раундов."""
    if config.source.get('previous'):
        rounds = len({s.round_no for s in specs if s.bracket == 'upper'})
        return 1, rounds + (1 if config.third_place else 0)
    teams = [s['entry'] for s in (x.home for x in specs if x.round_no == 1) if s] + \
            [s['entry'] for s in (x.away for x in specs if x.round_no == 1) if s]
    return _per_team_elimination(specs, list(dict.fromkeys(teams)), rng)


def estimate(template, params, n, days=None, per_day=None):
    stages = [StageConfig.model_validate(s['config']) for s in template_stages(template, {**auto_params(template, n), **params})]
    teams = [f't{i}' for i in range(n)]; rng = random.Random(n)
    warnings, fix = [], None; matches = 0; tours = []; low = high = 0; prior = None; count = n
    for config in stages:
        if config.kind == 'groups':
            if config.group_count * 2 > count:
                fix = {'group_count': max(2, count // 4) if count >= 8 else max(1, count // 2)}
                warnings.append(f'Для {config.group_count} групп нужно минимум {config.group_count * 2} команд')
                config = config.model_copy(update={'group_count': max(2, count // 2)}) if count >= 4 else config
            sizes = group_sizes(count, config.group_count)
            if len(set(sizes)) > 1:
                warnings.append(f"Группы {', '.join(map(str, sizes))}: третьи места сравниваются по очкам за матч")
        placement = _placement(config, prior, teams[:count])
        specs = fixtures_for(config, placement)
        real = [s for s in specs if not s.bye and s.bracket != 'final_reset']
        if config.kind == 'swiss':
            rounds = config.rounds or max(1, (count - 1).bit_length())
            matches += rounds * (count // 2); tours += [count // 2] * rounds
            low += rounds - (1 if count % 2 else 0); high += rounds
        else:
            matches += len(real)
            by_round = {}
            for s in real: by_round.setdefault((s.bracket in ('third', 'final') and 'final' or s.bracket, s.round_no, s.leg), []).append(s)
            tours += [len(v) for _, v in sorted(by_round.items(), key=lambda kv: (kv[0][1], str(kv[0][0]), kv[0][2]))]
            if config.kind in ELIMINATION:
                byes = bracket_size(count) - count
                if byes: warnings.append(f'{byes} команд начнут со второго раунда (пропуск хода)')
                a, b = _elimination_range(config, specs, count, rng)
                low += a; high += b
            else:
                played = {}
                for s in real:
                    for side in (s.home, s.away): played[side['entry']] = played.get(side['entry'], 0) + 1
                low += min(played.values(), default=0); high += max(played.values(), default=0)
        prior = config
        count = min(count, (config.advance.per_group * config.group_count + sum(b.count for b in config.advance.best))
                    if config.kind == 'groups' else (config.playoff_teams or count))
    need = sum(ceil(k / per_day) if per_day else 1 for k in tours)
    return {'template': template, 'params': {**auto_params(template, n), **params}, 'matches': matches,
            'per_team': [low, high], 'rounds': len(tours), 'days': need,
            'fits': None if days is None else need <= days, 'warnings': warnings, 'fix': fix,
            'summary': summary(template, stages, n), 'recommended': False, 'reason': None}


def summary(template, stages, n):
    first = stages[0]
    if first.kind == 'groups':
        sizes = group_sizes(n, first.group_count); lo, hi = min(sizes), max(sizes)
        q = first.advance.per_group * first.group_count + sum(b.count for b in first.advance.best)
        return f"{first.group_count} группы по {lo if lo == hi else f'{lo}–{hi}'} команд, в плей-офф {q}"
    if first.kind == 'round_robin':
        tail = f', в плей-офф {first.playoff_teams}' if first.playoff_teams else ''
        return ('Два круга' if first.legs == 2 else 'Один круг') + tail
    if first.kind == 'swiss': return f'{first.rounds or max(1, (n - 1).bit_length())} туров'
    return f'Сетка на {bracket_size(n)} мест'


def estimate_all(n, days=None, per_day=None, template=None, params=None):
    cards = [estimate(t, params if t == template and params else {}, n, days, per_day) for t in TEMPLATES]
    by = {c['template']: c for c in cards}
    fits = lambda c: c['fits'] is not False
    choice = None
    if (days is not None and fits(by['league'])) or (days is None and n <= 6): choice = by['league']
    elif fits(by['groups_playoff']) and n >= 8: choice = by['groups_playoff']
    else:
        fitting = [c for c in cards if fits(c) and c['template'] in ('league', 'groups_playoff', 'playoff')]
        choice = max(fitting, key=lambda c: (c['per_team'][0], -c['matches'])) if fitting else min(cards, key=lambda c: c['days'])
        if not fitting: choice['warnings'].insert(0, f"Ни один формат не укладывается: нужно минимум {choice['days']} игровых дней")
    choice['recommended'] = True
    choice['reason'] = f"Каждая команда сыграет минимум {choice['per_team'][0]} матча за {choice['days']} игровых дней"
    return cards
```

Ожидаемые значения в `test_recommendation_rule` при расхождении пересчитать вручную по правилу из спецификации и исправить именно тест или код, где ошибка.

- [ ] **Шаг 4. Эндпоинт.** `schemas.py`:

```python
class EstimateInput(Input):
    teams: Annotated[int, Field(ge=2, le=128)] | None = None
    days: Annotated[int, Field(ge=1, le=365)] | None = None
    per_day: Annotated[int, Field(ge=1, le=50)] | None = None
    template: Template | None = None
    params: dict = Field(default_factory=dict)


class EstimateCard(View):
    template: Template
    params: dict
    summary: str
    matches: int
    per_team: list[int]
    rounds: int
    days: int
    fits: bool | None = None
    warnings: list[str]
    fix: dict | None = None
    recommended: bool
    reason: str | None = None


class EstimateView(View):
    teams: int
    cards: list[EstimateCard]
```

`routes.py`: `POST /tournaments/{tid}/format/estimate` (`require_csrf`, без записи): `teams = data.teams or число заявок турнира`; `{'teams': teams, 'cards': estimate_all(...)}`; при `teams < 2` — `422` «Для формата нужны минимум две команды».
- [ ] **Шаг 5.** Тесты — PASS. Коммит `feat(stages): format estimates and recommendation`.

### Задача 2. Участники и исправление «не хватает команд»

**Файлы:** `schemas.py` (`DrawInput.participants: list[UUID] | None`), `operations.py` (`_participants`, `_placement`), `generate.py` (код ошибки), миграция задачи 4 (колонка `participants`), `tests/service/test_stage_adjust.py`.

- [ ] **Шаг 1. Тесты.**

```python
def test_subset_participants(admin_client, format_env):
    env = format_env(template='league', teams=6)
    stage = env['stages'][0]
    chosen = env['entries'][:4]
    r = draw(admin_client, stage, method='seeded', seeding=chosen, participants=chosen)
    assert r.status_code == 200, r.text
    assert r.json()['stages'][0]['draw']['participants'] == chosen
    assert len(fixtures(admin_client, env)) == 6


def test_not_enough_teams_suggests_fix(admin_client, format_env):
    env = format_env(teams=7, group_count=4, per_group=2)
    groups = env['stages'][0]
    r = admin_client.post(f"/api/v1/stages/{groups['id']}/draw/preview", json={'method': 'pots', 'seed': 1})
    assert r.status_code == 422
    body = r.json()['error']
    assert body['code'] == 'not_enough_teams' and body['fields'] == {'group_count': '3'}
```

(`format_env`, `draw`, `fixtures` импортировать из `test_stages_api.py`; в `draw` добавить проброс `participants`.)
- [ ] **Шаг 2.** FAIL. **Шаг 3.** Реализация: `_participants(..., chosen)` — для источника «все заявки» берёт `data.participants` (каждый должен быть заявкой турнира, без повторов, не меньше 2), иначе все заявки; `seeding` — перестановка участников. `participants_placement` для групп при нехватке: `DomainError('not_enough_teams', f'Для {g} групп нужно минимум {2*g} команд', fields={'group_count': str(max(2, n // 4) if n >= 8 else max(1, n // 2))})`. Версия жеребьёвки пишет `participants`; `DrawView.participants`.
- [ ] **Шаг 4.** PASS. Коммит `feat(stages): choose participants and suggest a group count fix`.

### Задача 3. Правки состава до старта (`adjust.py`)

**Файлы:** создать `stages/adjust.py`; `schemas.py` (`AdjustInput`), `routes.py`, `operations.py` (валидация ручной сетки с пропусками), тесты в `test_stage_adjust.py`.

- [ ] **Шаг 1. Тесты.**

```python
def test_remove_from_group_keeps_other_groups_matches(admin_client, format_env):
    env = format_env(teams=8, group_count=2, per_group=2)
    groups = env['stages'][0]
    stage = draw(admin_client, groups, method='snake', seeding=env['entries']).json()['stages'][0]
    other = next(f for f in fixtures(admin_client, env) if f['group_no'] == 2)
    kept = schedule(admin_client, env, other)
    victim = stage['draw']['placement'][0][0]
    body = {'op': 'remove', 'entry_id': victim, 'expected_revision': stage['revision']}
    preview = admin_client.post(f"/api/v1/stages/{groups['id']}/draw/adjust/preview", json=body).json()
    assert (preview['kept'], preview['cancelled']) == (1, 0)
    r = admin_client.post(f"/api/v1/stages/{groups['id']}/draw/adjust", json={**body, 'request_id': str(uuid4())})
    assert r.status_code == 200, r.text
    group_a = [f for f in fixtures(admin_client, env, unscheduled=False) if f['group_no'] == 1]
    assert len(group_a) == 3                                   # 3 команды — 3 пары
    assert admin_client.get(f"/api/v1/matches/{kept['id']}").json()['status'] == 'scheduled'


def test_add_late_team_to_smallest_group_and_bracket_bye(admin_client, format_env):
    env = format_env(template='playoff', teams=5)
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries'][:4], participants=env['entries'][:4]).json()['stages'][0]
    r = admin_client.post(f"/api/v1/stages/{stage['id']}/draw/adjust",
                          json={'op': 'add', 'entry_id': env['entries'][4], 'expected_revision': stage['revision'], 'request_id': str(uuid4())})
    assert r.status_code == 409 and r.json()['error']['code'] == 'no_free_slot'   # сетка на 4 заполнена
    removed = admin_client.post(f"/api/v1/stages/{stage['id']}/draw/adjust", json={'op': 'remove', 'entry_id': env['entries'][3],
                                'expected_revision': stage['revision'], 'request_id': str(uuid4())}).json()['stages'][0]
    first = removed['sections'][0]['rounds'][0]['pairs']
    assert any(p['bye'] for p in first)                        # соперник убранной проходит дальше


def test_adjust_locked_after_start(admin_client, format_env, send_command):
    env = format_env(template='league', teams=4)
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries']).json()['stages'][0]
    result(send_command, schedule(admin_client, env, fixtures(admin_client, env)[0]), 1, 0)
    r = admin_client.post(f"/api/v1/stages/{stage['id']}/draw/adjust", json={'op': 'remove', 'entry_id': env['entries'][0],
                          'expected_revision': stage['revision'], 'request_id': str(uuid4())})
    assert r.status_code == 409 and r.json()['error']['code'] == 'draw_locked'
```

- [ ] **Шаг 2.** FAIL. **Шаг 3. Реализация.**

```python
class AdjustInput(Input):
    op: Literal['remove', 'add', 'move']
    entry_id: UUID
    group_no: Annotated[int, Field(ge=1, le=16)] | None = None
    expected_revision: int = Field(ge=0)
    request_id: UUID = Field(default_factory=uuid4)
```

`adjust.py`:

```python
"""Правка состава этапа до старта: новая версия жеребьёвки с ручной расстановкой."""
from aifootball.service.errors import DomainError
from aifootball.service.stages.schemas import DrawConfirm, DrawInput, ELIMINATION
from aifootball.service.stages import operations as ops


def adjusted(stage, draw, data):
    """(участники, расстановка) после правки."""
    entry = str(data.entry_id); config = ops.config_of(stage)
    participants = [str(p) for p in (draw.participants or draw.seeding)]
    placement = [list(g) for g in draw.placement] if config.kind == 'groups' else list(draw.placement)
    present = entry in participants
    if data.op == 'remove':
        if not present: raise DomainError('validation', 'Этой команды нет в этапе')
        participants.remove(entry)
        if config.kind == 'groups':
            placement = [[t for t in g if t != entry] for g in placement]
            if any(len(g) < 2 for g in placement): raise DomainError('validation', 'В группе должно остаться минимум две команды')
        elif config.kind in ELIMINATION:
            placement = [None if s and s.get('entry') == entry else s for s in placement]
        else:
            placement = [t for t in placement if t != entry]
    elif data.op == 'add':
        if present: raise DomainError('validation', 'Команда уже в этапе')
        participants.append(entry)
        if config.kind == 'groups':
            target = (data.group_no or min(range(1, len(placement) + 1), key=lambda g: (len(placement[g - 1]), g))) - 1
            placement[target].append(entry)
        elif config.kind in ELIMINATION:
            if None not in placement: raise DomainError('no_free_slot', 'Свободных мест нет. Проведите жеребьёвку заново', status=409)
            placement[placement.index(None)] = {'entry': entry}
        else:
            placement.append(entry)
    else:
        if config.kind != 'groups' or not data.group_no or not present:
            raise DomainError('validation', 'Перенести можно команду этапа в другую группу')
        placement = [[t for t in g if t != entry] for g in placement]; placement[data.group_no - 1].append(entry)
        if any(len(g) < 2 for g in placement): raise DomainError('validation', 'В группе должно остаться минимум две команды')
    return participants, placement


def preview_adjust(db, tournament, stage, data):
    draw = ops.current_draw(db, stage.id)
    if draw is None: raise DomainError('validation', 'Сначала проведите жеребьёвку')
    participants, placement = adjusted(stage, draw, data)
    return ops.preview_draw(db, tournament, stage, DrawInput(method='manual', seed=draw.seed, seeding=participants,
                                                             participants=participants, placement=placement))


def apply_adjust(db, actor, tournament, stage, data):
    draw = ops.current_draw(db, stage.id)
    if draw is None: raise DomainError('validation', 'Сначала проведите жеребьёвку')
    participants, placement = adjusted(stage, draw, data)
    return ops.confirm_draw(db, actor, tournament, stage, DrawConfirm(method='manual', seed=draw.seed, seeding=participants,
        participants=participants, placement=placement, expected_revision=data.expected_revision, request_id=data.request_id))
```

`operations._placement` для `manual` в сетке: проверять, что множество заявок в расстановке (без `None`) равно участникам, а длина равна `bracket_size(len(placement))`, вместо сравнения с посевом. Маршруты: `POST /stages/{sid}/draw/adjust/preview` (без записи), `POST /stages/{sid}/draw/adjust` (`setup_command` вид `stage-adjust`).
- [ ] **Шаг 4.** PASS. Коммит `feat(stages): remove, add and move teams before the stage starts`.

### Задача 4. Исход пары и снятие команды

**Файлы:** миграция `0028_stage_adjustments.py`, `models.py`, `schemas.py` (`walkover_score`, `WithdrawalInput`, `WithdrawalPreview`), создать `withdrawals.py`, изменить `rules/progress.py`, `operations.py`, `routes.py`; тесты `test_stage_rules.py` (правила), `test_stage_withdrawals.py` (API).

- [ ] **Шаг 1. Миграция и модели.**

```python
# 0027_tournament_stages → 0028_stage_adjustments
op.add_column('stage_draws', sa.Column('participants', JSONB()))
op.add_column('fixtures', sa.Column('outcome', JSONB()))
op.create_table('stage_withdrawals',
    sa.Column('id', sa.Uuid(), primary_key=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('stage_id', sa.Uuid(), sa.ForeignKey('stages.id', name='fk_withdrawal_stage'), nullable=False),
    sa.Column('entry_id', sa.Uuid(), sa.ForeignKey('entries.id', name='fk_withdrawal_entry'), nullable=False),
    sa.Column('rule', sa.String(20), nullable=False),
    sa.Column('played', sa.Integer(), nullable=False),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), sa.ForeignKey('admins.id', name='fk_withdrawal_admin'), nullable=False),
    sa.UniqueConstraint('stage_id', 'entry_id', name='uq_stage_withdrawal'),
    sa.CheckConstraint("rule in ('annul','walkover','elimination','swiss')", name='ck_withdrawal_rule'))
```

Модели: `StageDraw.participants=Column(JSONB)`, `Fixture.outcome=Column(JSONB)`, класс `StageWithdrawal` с теми же полями. `StageConfig.walkover_score: list[Annotated[int, Field(ge=0, le=50)]] = Field(default_factory=lambda: [5, 0], min_length=2, max_length=2)`. Тест миграции — по образцу `test_stage_tables_and_standings_flag`.

- [ ] **Шаг 2. Тесты правил** (`test_stage_rules.py`):

```python
def test_group_outcome_removes_annulled_and_sinks_withdrawn():
    groups = [['A', 'B', 'C', 'D']]
    results = {1: [R('A', 'B', 0, 3), R('C', 'D', 1, 0)]}
    tables, _ = group_outcome(groups, results, removed={'D'}, expected=[3])
    assert [r.team for r in tables[0]] == ['B', 'C', 'A']
    tables, outcome = group_outcome(groups, {1: [R('A', 'B', 3, 0), R('A', 'C', 3, 0), R('A', 'D', 3, 0),
                                                 R('B', 'C', 1, 0), R('B', 'D', 1, 0), R('C', 'D', 1, 0)]},
                                    per_group=2, withdrawn={'A'}, expected=[6])
    assert tables[0][-1].team == 'A' and outcome.places[(1, 1)] == 'B'


def test_bracket_walkover_for_withdrawn():
    specs = single_elim([entry(t) for t in 'ABCD'])
    pairs = resolve_bracket(specs, {'U1-1': [Leg('A', 'D', 1, 0)]}, withdrawn={'C'})
    assert pairs['U1-2'].winner == 'B' and pairs['U2-1'].home == 'A' and pairs['U2-1'].away == 'B'
```

- [ ] **Шаг 3. Правила.** `group_outcome(..., removed=frozenset(), withdrawn=frozenset())`: команды из `removed` не входят в состав группы; таблица считается обычным `rank`, затем строки `withdrawn` переносятся в конец, места пересчитываются по порядку, у них `tied=False`, в `places` они не попадают. `resolve_bracket(..., withdrawn=frozenset())`: если обе стороны известны, у пары нет победителя, а одна сторона в `withdrawn` — победитель другая (`state.walkover = 'home'|'away'`); если сняты обе — победителя нет.

- [ ] **Шаг 4. Исход пары в таблицах** (`operations._evaluate_stage`): для пар с `outcome.kind == 'annulled'` — пропуск (и в `expected`); с `walkover` — `Result(home, away, *score)` по сторонам источников, очки из регламента этапа; эти пары считаются сыгранными для статуса этапа и для `can_next_round`. Снявшиеся берутся из `stage_withdrawals` этапа: `annul` → `removed`, `walkover` → `withdrawn` (группы/лига), `elimination` → `withdrawn` для `resolve_bracket`, `swiss` → исключаются из `ranked` в `next_swiss_round`. В представлении пары: `walkover`, у матча — `technical`/`annulled` и счёт из исхода.

- [ ] **Шаг 5. Тесты API** (`test_stage_withdrawals.py`):

```python
def test_half_rule_annuls_before_half(admin_client, format_env, send_command):
    env = format_env(template='league', teams=6)          # у каждой 5 матчей
    stage = draw(admin_client, env['stages'][0], method='seeded', seeding=env['entries']).json()['stages'][0]
    team = env['entries'][0]
    played = [f for f in fixtures(admin_client, env) if team in (f['home']['team']['entry_id'], f['away']['team']['entry_id'])][:2]
    for f in played: result(send_command, schedule(admin_client, env, f), 1, 0)
    preview = admin_client.post(f"/api/v1/stages/{stage['id']}/withdrawals/preview", json={'entry_id': team}).json()
    assert (preview['played'], preview['total'], preview['rule']) == (2, 5, 'annul')
    r = admin_client.post(f"/api/v1/stages/{stage['id']}/withdrawals",
                          json={'entry_id': team, 'expected_revision': stage_list(admin_client, env)[0]['revision'], 'request_id': str(uuid4())})
    assert r.status_code == 200, r.text
    rows = r.json()['stages'][0]['groups'][0]['rows']
    assert team not in [row['team']['entry_id'] for row in rows]
    assert r.json()['stages'][0]['withdrawn'][0]['rule'] == 'annul'


def test_half_rule_walkovers_from_half(admin_client, format_env, send_command):
    env = format_env(template='league', teams=7)          # 6 матчей, сыграно 3 — технические
    ...  # сыграть 3 пары команды; снятие → rule 'walkover'; 3 оставшиеся пары — тех. победы соперников 5:0;
         # команда последняя с пометкой; назначенный матч снятой команды → cancelled


def test_bracket_withdrawal_gives_walkover(admin_client, format_env, send_command):
    ...  # плей-офф 4: результат U1-1, этап начат; снять команду из U1-2 → её соперник в финале, U1-2 winner


def test_withdrawal_before_start_points_to_adjust(admin_client, format_env):
    ...  # этап с жеребьёвкой без результатов → 409 'use_adjust' «Этап ещё не начался: уберите команду из состава»
```

Каждый `...` при реализации раскрывается в полные проверки по комментарию.

- [ ] **Шаг 6. Реализация** `withdrawals.py`:

```python
"""Снятие команды после старта этапа: правило половины в группах, техническая победа в сетке, без новых туров в швейцарке."""
from sqlalchemy import select
from aifootball.service.common import get_entity
from aifootball.service.errors import DomainError
from aifootball.service.matches.models import Match
from aifootball.service.stages import operations as ops
from aifootball.service.stages.models import Stage, StageWithdrawal
from aifootball.service.stages.schemas import ELIMINATION


def plan(db, tournament, stage, entry_id, rule=None):
    ev = next(e for e in ops.evaluate(db, tournament, 'cabinet') if e.stage.id == stage.id)
    if ev.status == 'completed': raise DomainError('stage_completed', 'Этап уже завершён', status=409)
    if ev.status != 'started': raise DomainError('use_adjust', 'Этап ещё не начался: уберите команду из состава', status=409)
    team = str(entry_id)
    if db.scalar(select(StageWithdrawal).where(StageWithdrawal.stage_id == stage.id, StageWithdrawal.entry_id == entry_id)):
        raise DomainError('already_withdrawn', 'Команда уже снята', status=409)
    own = [f for f in ev.fixtures if not f.bye and team in ev.computed.get(f.id, ())]
    played = [f for f in own if f.id in ev.legs or (f.outcome or {}).get('kind') == 'walkover']
    kind = ev.config.kind
    default = 'elimination' if kind in ELIMINATION else 'swiss' if kind == 'swiss' else ('annul' if 2 * len(played) < len(own) else 'walkover')
    rule = rule or default
    if kind in ('groups', 'round_robin') and rule not in ('annul', 'walkover'): raise DomainError('validation', 'Выберите правило для группы')
    open_ = [f for f in own if f not in played]
    affected = own if rule == 'annul' else open_
    cancel = [f for f in affected if f.match_id and f.id not in ev.legs]
    return ev, team, rule, default, own, played, affected, cancel


def preview(db, tournament, stage, data):
    ev, team, rule, default, own, played, affected, cancel = plan(db, tournament, stage, data.entry_id, data.rule)
    return {'entry_id': team, 'rule': rule, 'default_rule': default, 'played': len(played), 'total': len(own),
            'annulled': len(affected) if rule == 'annul' else 0, 'walkovers': len(affected) if rule == 'walkover' else 0,
            'cancelled_matches': len(cancel)}


def withdraw(db, actor, tournament, stage, data):
    stage = get_entity(db, Stage, stage.id, lock=True)
    if stage.revision != data.expected_revision: raise ops.stage_conflict(stage)
    ev, team, rule, _, own, played, affected, cancel = plan(db, tournament, stage, data.entry_id, data.rule)
    score = ev.config.walkover_score
    for f in affected:
        if rule == 'annul': f.outcome = {'kind': 'annulled'}
        elif rule in ('walkover', 'swiss'):
            home, _ = ev.computed[f.id]
            f.outcome = {'kind': 'walkover', 'winner': 'away' if home == team else 'home', 'score': score}
    for f in cancel:
        match = get_entity(db, Match, f.match_id, lock=True); match.status = 'cancelled'; match.revision += 1
    db.add(StageWithdrawal(stage_id=stage.id, entry_id=data.entry_id, rule=rule, played=len(played), total=len(own), actor_id=actor.id))
    stage.revision += 1
    db.flush()
    return ops.standings(db, tournament, 'cabinet')
```

Для швейцарки: пары уже составленного, но не сыгранного тура со снятой командой получают техническую победу соперника (правило `swiss` использует ту же ветку, что `walkover`, только для открытых пар). Для сетки исход пары не пишется — победителя даёт `resolve_bracket(withdrawn=…)`, отменяются только назначенные матчи снятой команды без результата.

Маршруты: `POST /stages/{sid}/withdrawals/preview` и `POST /stages/{sid}/withdrawals` (`setup_command` вид `stage-withdrawal`). Схемы:

```python
class WithdrawalInput(Input):
    entry_id: UUID
    rule: Literal['annul', 'walkover'] | None = None
    expected_revision: int | None = Field(default=None, ge=0)
    request_id: UUID = Field(default_factory=uuid4)


class WithdrawalPreview(View):
    entry_id: UUID
    rule: str
    default_rule: str
    played: int
    total: int
    annulled: int
    walkovers: int
    cancelled_matches: int
```

- [ ] **Шаг 7.** Все тесты задачи — PASS; весь `pytest` — PASS. Коммит `feat(stages): walkovers, annulled pairs and team withdrawal`.

### Задача 5. Данные для показа сетки

**Файлы:** `schemas.py` (`PairView.home_from/away_from/walkover`, `LegView.technical/annulled`, `SectionView.current_round`, `StageView.withdrawn`, `DrawView.participants`), `operations.py`; тест в `test_stages_api.py`; OpenAPI и `web/src/api/types.ts`.

- [ ] **Шаг 1. Тест:** в сценарии плей-офф 4 после результата первой пары `sections[0].current_round == 1`, после обеих — `2`; у финала `home_from == 'U1-1'`, `away_from == 'U1-2'`; у тех. победы `legs[0].technical is True` и счёт `{'home': 5, 'away': 0}`.
- [ ] **Шаг 2–3.** FAIL → реализация: `home_from = source.get('winner') or source.get('loser')`; `current_round` — номер первого раунда раздела, где есть пара не `bye` без победителя (сетка) или с матчем без счёта (туры), иначе последний.
- [ ] **Шаг 4.** PASS. OpenAPI и типы:

```bash
.venv/bin/python scripts/export_service_openapi.py --output data/service/openapi.json
npm --prefix web run types:api
```

Коммит `feat(stages): bracket links, current round and technical results in views`.

### Задача 6. Подсказки в шаге «Формат» (фронтенд)

**Файлы:** создать `Stepper.tsx`, `FormatHelp.tsx`, `FormatStep.test.tsx` (переписать); изменить `FormatStep.tsx`, `labels.ts`, `stages.css`.

- `Stepper` — `<div role="group" aria-label={label}>` с кнопками «−»/«+» (48×48, `aria-label="Уменьшить: Групп"`) и значением `<output aria-live="polite">`; границы `min/max`, кнопка на границе остаётся доступной для фокуса, но не меняет значение и озвучивает «Минимум 2» (без `disabled`, по правилу Material «не прятать причину»).
- `FormatStep`: строка «Команд: 14 · Изменить» (кнопка открывает `ParticipantsPicker` из задачи 7), степперы «Игровых дней» и «Матчей за день» (необязательные, пустое значение — «не задано»); запрос `POST /tournaments/{tid}/format/estimate` с задержкой 300 мс и `AbortController`; карточки из ответа: название, `TEMPLATE_HINT`, факты «29 матчей · 3–6 на команду · 5 дней», «Рекомендуем» + `reason`, предупреждения (значок + текст), кнопка исправления (`fix`) — «Сделать 3 группы»; не укладывающиеся — подпись «Не уложится в N дн.». Прошлый ответ виден до нового; при ошибке — «Не удалось пересчитать. Повторить».
- `FormatHelp` — кнопка «Как выбрать формат»; на ширине < 600 px — нижняя панель (`<dialog>` с `position: fixed; bottom: 0`, ручка, закрытие свайпом вниз и кнопкой «Готово»), шире — всплывающее окно рядом с кнопкой; содержимое — `FORMAT_GUIDE` в `labels.ts`:

```ts
export const FORMAT_GUIDE:Record<Template,{fits:string;pros:string;cons:string}>={
 league:{fits:'До 8 команд и много игровых дней',pros:'Самый честный итог: каждый с каждым',cons:'Матчей много: при 12 командах — 66'},
 groups_playoff:{fits:'От 8 до 32 команд',pros:'Все играют минимум 3 матча, в конце — решающие игры',cons:'Нужно согласовать группы и сетку'},
 playoff:{fits:'Мало игровых дней',pros:'Быстро: за 3 дня можно провести турнир на 8 команд',cons:'Проигравшие выбывают после первого матча'},
 double_elim:{fits:'4–16 команд, один насыщенный турнирный день или два',pros:'Одна неудача не выбивает из турнира',cons:'Сложнее понять зрителям'},
 swiss:{fits:'Много команд и мало дней',pros:'Соперники равной силы, все играют одинаково',cons:'Незнакомо многим игрокам'},
};
```

- [ ] **Шаг 1. Тесты:** рекомендация видна на карточке с `reason`; изменение степпера «Групп» шлёт новый расчёт с `params.group_count`; предупреждение и кнопка «Сделать 3 группы» меняют значение степпера; «Как выбрать формат» открывает диалог с пятью разделами и закрывается «Готово»; степпер на минимуме не уходит ниже и сообщает «Минимум 2».
- [ ] **Шаг 2–4.** FAIL → реализация → PASS. Коммит `feat(web): format hints with estimates, steppers and guide`.

### Задача 7. Кто играет, правка состава, снятие (фронтенд)

**Файлы:** создать `ParticipantsPicker.tsx`, `RosterPanel.tsx`, `WithdrawDialog.tsx`, `RosterPanel.test.tsx`; изменить `DrawStep.tsx`, `StageWorkspace.tsx`.

- `ParticipantsPicker` — список заявок с переключателями (строки 48 px, «Выбрать всех»), счётчик «Играют 12 из 14»; результат передаётся в `participants` предпросмотра и подтверждения жеребьёвки и в расчёт подсказок.
- `DrawStep`: ошибка `not_enough_teams` показывает текст и кнопку «Сделать N групп» (PATCH этапа `config.group_count`, затем повтор предпросмотра).
- `RosterPanel` (этап с жеребьёвкой, статус `drawn`): группы с командами; у команды меню «Убрать из этапа», «Перенести в группу…»; «Добавить команду» — выбор из заявок не в этапе; каждое действие сначала `adjust/preview`, затем лист подтверждения «Сохранятся N назначенных матчей, M будут отменены» и «Применить».
- `WithdrawDialog` (этап `started`): выбор команды → `withdrawals/preview` → текст «Сыграно 2 из 5. Результаты команды будут аннулированы, 1 назначенный матч будет отменён», для групп — сегмент «Аннулировать / Технические поражения» (по умолчанию из ответа), кнопки «Снять команду» (опасное действие, красная) и «Отмена»; после снятия — уведомление «Команда снята» на 4 с.
- `StageWorkspace`: для `drawn` — `RosterPanel`; для `started` — кнопка «Снять команду»; для этапа после старта на месте «Добавить команду» — «Этап уже начался: новую команду можно добавить в следующий этап».

- [ ] **Шаг 1. Тесты:** убрать команду → запрос `adjust/preview` с `op:'remove'`, затем `adjust` после «Применить»; «Добавить команду» без свободного места показывает «Свободных мест нет. Проведите жеребьёвку заново»; диалог снятия показывает правило по ответу и отправляет `rule` после переключения сегмента; «Отмена» ничего не отправляет.
- [ ] **Шаг 2–4.** FAIL → реализация → PASS. Коммит `feat(web): participants, roster changes and withdrawal dialog`.

### Задача 8. Карточка пары, раунды на телефоне, матчи группы

**Файлы:** изменить `Bracket.tsx` (вынести `PairCard` в `PairCard.tsx`), создать `GroupMatches.tsx`, `PairCard.test.tsx`; изменить `StandingsView.tsx`, `labels.ts`, `stages.css`.

- `PairCard`:
  - строки команд — эмблема 20 px (`logo_id` → `/api/v1/public/catalog/team-logos/{id}`), название, итог пары; победитель — `font-weight:600` и значок `Check` (lucide) с `aria-hidden`; при равном итоге — пенальти «1 (4)»;
  - строки матчей: `Матч 1 · 12 нояб., 19:00 · 2 : 2` для пар из двух матчей; для одного — дата/время или «Дата не назначена»; статусы текстом: «Идёт» (точка `--live`), «Перенесён», «Отменён», «Тех. поражение», «Аннулирован»;
  - одна подпись для диктора (`aria-label` у `<article>`), функция `pairSpeech(pair,timezone)` в `labels.ts`: «Полуфинал. Север 5, Юг 3. Север прошёл дальше. Матч 2 — 19 ноября, 19:00»;
  - касание: один матч — ссылка на матч на всю карточку (минимум 48 px высотой); два матча — кнопка раскрытия списка матчей со ссылками.
- Раунды на телефоне: начальный раунд — `current_round` раздела; ряд раундов с `scroll-snap`, стрелки ←/→ переключают вкладки; при смене раунда без анимации, если `prefers-reduced-motion`.
- `GroupMatches` — под таблицей группы «Матчи группы» (`<details>`, открыт, если пар ≤ 6): туры с датой, командами и счётом.

- [ ] **Шаг 1. Тесты:** пара из двух матчей показывает обе строки с датами и итог 5:3; пенальти «1 (4)»; тех. поражение подписано; `aria-label` совпадает с `pairSpeech`; начальная вкладка — `current_round`; стрелка вправо переключает раунд; матчи группы показывают счёт сыгранного и «Дата не назначена».
- [ ] **Шаг 2–4.** FAIL → реализация → PASS. Коммит `feat(web): pair card with every match, current round and group matches`.

### Задача 9. Дерево сетки на компьютере и путь команды

**Файлы:** создать `BracketTree.tsx`, `BracketTree.test.tsx`; изменить `Bracket.tsx` (на ширине ≥ 900 px — `BracketTree`, ниже — раунды), `stages.css`.

- Раскладка: CSS-сетка, колонка на раунд; в верхней сетке пара раунда `r`, место `s` занимает строки `(s−1)·2^(r−1)+1 … s·2^(r−1)` (`grid-row: a / span n`, `align-self:center`); в нижней — у раунда столько строк, сколько пар в первом раунде нижней сетки, пары равномерно.
- Линии: `<svg aria-hidden="true">` поверх сетки; для каждой пары с `home_from`/`away_from` из того же раздела — путь от правого края карточки-источника к левому краю пары (горизонталь, вертикаль, горизонталь); координаты из `getBoundingClientRect` относительно контейнера; пересчёт в `ResizeObserver` и при смене шрифта (`document.fonts.ready`); цвет `--line-strong` (контраст 3:1).
- Заголовки раундов — `position: sticky; top: 0` внутри контейнера прокрутки; матч за 3-е место — отдельный блок под колонкой финала.
- Путь команды: кнопка-название команды в карточке (`aria-pressed`) выделяет все карточки с этой командой (`data-path`) и линии между ними; повторное нажатие или Escape снимает; на телефоне то же выделение в списке раундов.

- [ ] **Шаг 1. Тесты** (jsdom: подменить `getBoundingClientRect`): для сетки на 8 команд в SVG 6 путей (4 к полуфиналам + 2 к финалу); полуфинал 1 занимает `grid-row: 1 / span 2`; нажатие на «Север» помечает его карточки `data-path`, Escape снимает.
- [ ] **Шаг 2–4.** FAIL → реализация → PASS. Коммит `feat(web): bracket tree with connectors and team path`.

### Задача 10. Тёмная тема сайта зрителя

**Файлы:** `web/src/styles/tokens.css`, публичные стили (см. карту файлов), создать `web/src/features/stages/contrast.ts`, `web/src/styles/tokens.test.ts`; `docs/design/2026-10-15-ui-system.md`.

- [ ] **Шаг 1. Тест контраста** (`tokens.test.ts`): читает `tokens.css` как текст, вытаскивает значения токенов для светлой темы (`:root{…}`) и тёмной (`@media (prefers-color-scheme: dark){:root:has(.public-shell){…}}`), считает контраст по WCAG (`contrast.ts`: относительная яркость sRGB) и проверяет:

```ts
const TEXT_PAIRS=[['--text','--app-bg'],['--text','--surface'],['--text-muted','--surface'],['--text-muted','--app-bg'],['--link','--surface'],['--accent-ink','--accent'],['--warn','--warn-soft'],['--danger','--danger-soft'],['--ok','--ok-soft']];
const UI_PAIRS=[['--line-strong','--surface'],['--accent-line','--surface'],['--focus','--surface']];
for(const theme of ['light','dark'])for(const [fg,bg] of TEXT_PAIRS)expect(contrast(t[theme][fg],t[theme][bg])).toBeGreaterThanOrEqual(4.5);
for(const theme of ['light','dark'])for(const [fg,bg] of UI_PAIRS)expect(contrast(t[theme][fg],t[theme][bg])).toBeGreaterThanOrEqual(3);
```

- [ ] **Шаг 2.** FAIL (тёмных токенов нет).
- [ ] **Шаг 3. Токены.** В `tokens.css` — новые `--surface-2`, `--line-strong`, `--live`, `--logo-plate`; тёмный блок:

```css
.public-shell{color-scheme:light dark}
@media (prefers-color-scheme:dark){
 :root:has(.public-shell){
  --app-bg:#0f1412;--surface:#171d1a;--surface-2:#1e2622;--text:#e8eeea;--text-muted:#a3aea8;--border:#2b3530;--line-strong:#5d6b64;
  --accent:#b8ec64;--accent-strong:#9fd94a;--accent-ink:#1a2a12;--accent-soft:#24331a;--accent-line:#8fcf45;
  --ok:#7fd283;--ok-soft:#173020;--warn:#f0b75a;--warn-soft:#33270f;--danger:#ff8a80;--danger-soft:#3a1714;--info-soft:#16263a;
  --link:#7fb2ef;--focus:#7fb2ef;--live:#ff6b5e;--logo-plate:#f2f5f3;
 }
}
```

Значения подгоняются, пока тест контраста не пройдёт; итоговая таблица — в `docs/design/2026-10-15-ui-system.md`, раздел «Тёмная тема».
- [ ] **Шаг 4. Перевод стилей на токены.** В публичных стилях заменить прямые цвета (`#fff`, `white`, `#E7ECEF`, `#FFF9E9` и др.) токенами; для прямых цветов, которых нет среди токенов, — новый токен, а не значение в месте использования. Логотипы команд в тёмной теме — на подложке `--logo-plate` с радиусом 6 px. `pitch.css` не трогать. Проверка перечня:

```bash
grep -nE "#[0-9a-fA-F]{3,8}\b|\bwhite\b" web/src/features/public/*.css web/src/features/public/match-center/*.css web/src/features/navigation/shell.css web/src/features/stages/stages.css web/src/features/match-report/report.css
```

Ожидаемо: пусто (кроме комментариев к цветам поля в `report.css`, если они относятся к схеме поля).
- [ ] **Шаг 5.** Тест контраста и весь Vitest — PASS. Коммит `feat(web): dark theme for the viewer site`.

### Задача 11. Документация

- [ ] `README.md` — дополнить пункт «Формат турнира и таблица»: подсказки, участники, правки состава, снятие (правило половины), сетка с датами и счётом, тёмная тема у зрителя.
- [ ] Спецификация `2026-10-27-tournament-format-ux-design.md` — статус «реализовано 27 октября» и раздел «Отличия реализации», если они появятся.
- [ ] `docs/README.md` — ссылка на спецификацию и этот план.
- [ ] Коммит `docs: format hints, partial rosters, bracket and dark theme`.

### Задача 12. E2E и полная проверка

**Файлы:** дополнить `web/e2e/tournament-format.spec.ts`, создать `web/e2e/public-dark.spec.ts`.

Сценарии:
1. Организатор: 7 команд, шаблон «Группы и плей-офф» с 4 группами → предупреждение и «Сделать 3 группы» → карточка «Рекомендуем» видна; «Кто играет» — снять одну команду → «Играют 6 из 7».
2. После жеребьёвки: «Убрать из этапа» → предпросмотр → «Применить» → в группе на одну команду меньше; назначенный матч другой группы остался.
3. После старта (подтверждён результат): «Снять команду» → «Сыграно 1 из 3» → «Снять команду» → команды нет в таблице, строка «снялась» под таблицей.
4. Зритель 375 px: сетка открыта на текущем раунде, у пары из двух матчей видны обе даты и счёт; 1440 px — дерево, SVG-линий столько, сколько связей; нажатие на команду подсвечивает путь; `scrollWidth <= innerWidth` у страницы.
5. Тёмная тема (`page.emulateMedia({colorScheme:'dark'})`) на главной, турнире (таблица и сетка) и матче: фон `body` тёмный (яркость < 0,1), контраст текста карточки пары и строки таблицы ≥ 4,5:1 (вычисляется в странице по `getComputedStyle`), без горизонтальной прокрутки; кабинет в тёмной системе остаётся светлым.

- [ ] Сборка ветки отдельно и запуск на свободном порту (8283 был занят; проверить `lsof -i :<порт>`), общий `web/dist` и сервис на 8000 не трогать:

```bash
npx --prefix web vite build --outDir /private/tmp/claude-501/-Users-timofeynikulin-AI-football/ec609083-3245-4507-bea3-30409c6dda10/scratchpad/dist --emptyOutDir
AIF_E2E_FAKE_MAIL=1 AIF_E2E_FAKE_ADDRESS=1 AIF_E2E_PORT=8291 AIF_E2E_DATABASE_NAME=aifootball_format_e2e AIF_WEB_DIST=/private/tmp/claude-501/-Users-timofeynikulin-AI-football/ec609083-3245-4507-bea3-30409c6dda10/scratchpad/dist npx --prefix web playwright test
```

- [ ] Полная проверка: `.venv/bin/python -m pytest --tb=line -q`, `npm --prefix web run test`, `npx --prefix web tsc -b`, весь E2E, `git diff --check`.
- [ ] Скриншоты зрителя (375 и 1440 px, светлая и тёмная) — в описание PR, не в Git.
- [ ] Пуш в `feat/tournament-format`, обновление описания PR #20 (раздел «Вторая поставка» и проверки).
