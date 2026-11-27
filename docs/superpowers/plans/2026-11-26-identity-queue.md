# Очередь разметки и одна разметка на матч — план

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** разметка игроков без перестроения экрана: «Очередь» (по одному), «Сетка» (кисть класса и массовый выбор),
«Игроки» (участие и исправления); сервис держит одну разметку на матч — запись только в самую новую версию, новая
версия сама забирает решения и участие; подсветку даёт модель матча (SigLIP 2 + цвет по решениям этого матча).

**Architecture:** сервис — поле версии `absent_players` (миграция 0030), проверки в `set_assignments`, перенос
разметки при загрузке пакета (`carry.py`), копия участия в «Новой проверке». Кабинет — чистые функции `queue.ts` и
`grid.ts`, компоненты `IdentityQueue`, `IdentityGrid`, `PlayersPanel`, переработанная `IdentityReview` (режимы,
автосохранение) и выбор самой новой версии в `AnalysisTab`. Обработчик кладёт в пакет признак SigLIP 2 фрагмента
(`embedding`), кабинет обучает на нём модель матча в браузере (`matchModel.ts`, `useMatchModel.ts`). Спецификация —
`docs/superpowers/specs/2026-11-26-identity-queue-design.md`.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic + pytest (сервис); React 18 + TypeScript, Vitest + Testing Library,
Playwright, Biome (кабинет).

---

## Где работать

Сайт организатора работает из этой рабочей копии (`laughing-pike`, ветка `local/serve-hse`). Ветку не
переключать; коммиты — в `local/serve-hse`; перенос в PR — задача 19. Общую `web/dist` не пересобирать до задачи 19
(сайт читает её), сервис на 8000 не останавливать.

- Тесты сервиса — только на тестовой базе `aifootball_test` (её поднимает `tests/service/conftest.py`):
  `.venv/bin/python -m pytest tests/service/<файл> -q`. Базу организатора не трогать, `alembic` вручную не запускать.
- Кабинет — из `web/`: `npx vitest run <файлы>`, `npx tsc -b`, `npm run lint`, `npx biome format --write <файлы>`.
- Python: `.venv/bin/ruff format <файлы>` и `.venv/bin/ruff check <файлы>`.
- `<scratchpad>` — временная папка вне репозитория (выгрузки и сборки для E2E).

## Отличия от спецификации (уточнены при планировании)

- Режим по умолчанию — «Очередь», если у прогона есть признаки цвета; прогоны без признаков, как и сейчас,
  открываются «По фрагментам» (на этой таблице держатся сценарии E2E и тесты вкладки).
- Подтверждённая самая новая версия: кнопка «Продолжить разметку» (команда `reviews` и переход в новую проверку)
  вместо автоматического создания на первом решении — без переноса неотправленного решения между версиями.
- «Сохранить сопоставление» остаётся как «сохранить сейчас»; автосохранение идёт через ту же функцию.
- Конфликт с другим окном: сервер отвечает «Проверка аналитики изменена…» (показывается как ошибка), автосохранение
  после ошибки останавливается до ручного сохранения; предупреждение «Черновик устарел» (PR #45) остаётся для
  черновиков, начатых с другой версии сервера.
- Номер тайма на карточке очереди не показывается: у кандидата нет границ таймов; есть отрезок и длительность.
- Задача 17 вносит эти уточнения в спецификацию.

## Файлы

| Файл | Что |
|---|---|
| `migrations/versions/0030_absent_players.py` | новый: поле `analysis_runs.absent_players` |
| `src/aifootball/service/analysis/models.py` | `AnalysisRun.absent_players` |
| `src/aifootball/service/analysis/schemas.py` | `AssignmentsUpdate.absent_players`, `RunView.absent_players` |
| `src/aifootball/service/analysis/assignments.py` | участие, запись только в самую новую версию |
| `src/aifootball/service/analysis/carry.py` | новый: перенос разметки в новую версию |
| `src/aifootball/service/analysis/imports.py` | вызов переноса |
| `src/aifootball/service/analysis/commands.py` | `reviews` копирует участие |
| `src/aifootball/service/analysis/queries.py` | `run_view` отдаёт участие |
| `tests/service/test_analysis_assignments.py` | участие, самая новая версия |
| `tests/service/test_analysis_carry.py` | новый: перенос при загрузке, копия в `reviews` |
| `web/src/api/types.ts` | перегенерирован |
| `web/src/features/analysis/identityBase.ts` (+ `identityBase.test.ts`) | отпечаток с участием |
| `web/src/features/analysis/identityFixtures.ts` | новый: общие тестовые данные (красная и синяя форма) |
| `web/src/features/analysis/queue.ts` (+ `queue.test.ts`) | новый: очередь, игроки, доступность, подсказка |
| `web/src/features/analysis/IdentityQueue.tsx` (+ тест) | новый: экран «Очередь» |
| `web/src/features/analysis/grid.ts` (+ `grid.test.ts`) | новый: порядок сетки, присвоение класса, диапазон |
| `web/src/features/analysis/IdentityGrid.tsx` (+ тест) | новый: экран «Сетка» |
| `web/src/features/analysis/PlayersPanel.tsx` (+ тест) | новый: режим «Игроки» |
| `web/src/features/analysis/IdentityReview.tsx` | режимы, участие, автосохранение |
| `web/src/features/analysis/AnalysisTab.tsx` | разметка в самой новой версии |
| `web/src/features/analysis/review.css` | стили новых экранов |
| удаляются | `SimilarPicker.tsx`, `SuggestionPicker.tsx`(+тест), `PlayerCandidates.tsx`(+тест), `suggestions.ts`(+тест); из `similar.ts` — `suggest`, `assignedShare` |
| `src/aifootball/perception/appearance.py` | признак SigLIP 2 для пакета: кодирование, загрузка весов без скачивания |
| `src/aifootball/processor/job.py` (`appearance`, `package_result`) | поле `embedding` у фрагментов |
| `src/aifootball/analytics/exchange.py` | проверка `embedding` (768 байт) |
| `src/aifootball/service/analysis/schemas.py` (`TrackView`) | `embedding` в виде версии |
| `web/src/features/analysis/similar.ts` | `decodeEmbedding`, `embeds` в индексе, `meanEmbed` |
| `web/src/features/analysis/matchModel.ts` (+ тест) | новый: обучение и предсказание модели матча |
| `web/src/features/analysis/useMatchModel.ts` | новый: обучение в паузах между решениями |
| `web/e2e/identity-queue.spec.ts` | новый вместо `similar-picker.spec.ts` |
| `README.md`, `docs/README.md`, спецификация | описание режимов |

---

### Task 1: участие в матче — поле версии и проверки сервера

**Files:**
- Create: `migrations/versions/0030_absent_players.py`
- Modify: `src/aifootball/service/analysis/models.py` (класс `AnalysisRun`), `schemas.py` (`AssignmentsUpdate`,
  `RunView`), `assignments.py` (`set_assignments`), `queries.py` (`run_view`)
- Test: `tests/service/test_analysis_assignments.py`

- [ ] **Step 1: Падающий тест.** В `tests/service/test_analysis_assignments.py` заменить помощник `save_assignments`:

```python
def save_assignments(client, match, run, values=None, absent=None):
    body = {
        'request_id': str(uuid4()),
        'expected_revision': run['revision'],
        'side_map': {'A': 'home', 'B': 'away'},
        'assignments': values if values is not None else assignments(run),
    }
    if absent is not None:
        body['absent_players'] = absent
    return client.put(f'/api/v1/matches/{match["id"]}/analysis/runs/{run["id"]}/assignments', json=body)
```

и добавить в конец файла:

```python
def test_absent_players_are_kept_and_get_no_fragments(admin_client, analytics_match):
    run = import_run(admin_client, analytics_match)
    home = [p['player_id'] for p in run['context']['rosters'] if p['side'] == 'home']
    saved = save_assignments(admin_client, analytics_match, run, absent=[home[1]])
    assert saved.status_code == 200, saved.text
    run = saved.json()
    assert run['absent_players'] == [home[1]]
    # Без поля участие не меняется.
    kept = save_assignments(admin_client, analytics_match, run)
    assert kept.status_code == 200, kept.text
    run = kept.json()
    assert run['absent_players'] == [home[1]]
    refused = save_assignments(admin_client, analytics_match, run, [{'track_id': 1, 'player_id': home[1]}])
    assert refused.status_code == 422
    assert refused.json()['error']['code'] == 'absent_player'
    stranger = save_assignments(admin_client, analytics_match, run, absent=[str(uuid4())])
    assert stranger.status_code == 422
    assert stranger.json()['error']['code'] == 'foreign_player'
```

- [ ] **Step 2: Убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/service/test_analysis_assignments.py -q -k absent`
Expected: FAIL — `KeyError: 'absent_players'` (поля нет в ответе).

- [ ] **Step 3: Миграция** — `migrations/versions/0030_absent_players.py`:

```python
"""Players who did not take part in the match, per labelling version (analysis run).

The cabinet hides them from the identity queue and the server refuses to give them fragments. The list travels with
the labelling to newer versions; the manual protocol lineup is not touched.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = '0030_absent_players'
down_revision = '0029_camera_motion'


def upgrade():
    op.add_column(
        'analysis_runs',
        sa.Column('absent_players', JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade():
    op.drop_column('analysis_runs', 'absent_players')
```

- [ ] **Step 4: Модель.** В `models.py`, класс `AnalysisRun`, после строки
  `side_map = Column(JSONB, nullable=False, default=lambda: {'A': 'home', 'B': 'away'})` добавить:

```python
    # Игроки состава, не участвовавшие в матче по разметке: им нельзя назначать фрагменты (миграция 0030).
    absent_players = Column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
```

- [ ] **Step 5: Схемы.** В `schemas.py`:

```python
class AssignmentsUpdate(Mutation):
    side_map: dict[str, Literal['home', 'away']]
    assignments: list[AssignmentInput] = Field(max_length=50000)
    # None — участие не меняется (капитанские задания и старые клиенты); список — заменить целиком.
    absent_players: list[UUID] | None = Field(default=None, max_length=200)
```

и в `RunView` после `assignments: list[AssignmentInput]`:

```python
    absent_players: list[UUID] = []
```

- [ ] **Step 6: Проверки сервера.** В `assignments.py`, функция `set_assignments`: после строки
  `roster = {p['player_id']: p for p in job.context['rosters']}` вставить

```python
    absent = {str(p) for p in run.absent_players or []}
    if getattr(data, 'absent_players', None) is not None:
        absent = {str(p) for p in data.absent_players}
        if absent - set(roster):
            raise DomainError('foreign_player', 'Игрок отсутствует в снимке состава задания')
```

внутри цикла, сразу после `if not player: raise DomainError('foreign_player', ...)` (тот же блок `if item.player_id:`):

```python
            if str(item.player_id) in absent:
                raise DomainError('absent_player', 'Игрок отмечен как не участвовавший в матче')
```

и в конце функции после `run.side_map = data.side_map`:

```python
    run.absent_players = sorted(absent)
```

- [ ] **Step 7: Вид версии.** В `queries.py`, `run_view`, после строки `'side_map_verified': run.side_map_verified,`:

```python
            'absent_players': run.absent_players or [],
```

- [ ] **Step 8: Тест проходит, остальные не сломаны**

Run: `.venv/bin/python -m pytest tests/service/test_analysis_assignments.py tests/service/test_team_identity_confirmations.py tests/service/test_migrations.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
.venv/bin/ruff format migrations/versions/0030_absent_players.py src/aifootball/service/analysis tests/service/test_analysis_assignments.py
.venv/bin/ruff check migrations src tests
git add migrations/versions/0030_absent_players.py src/aifootball/service/analysis/models.py src/aifootball/service/analysis/schemas.py src/aifootball/service/analysis/assignments.py src/aifootball/service/analysis/queries.py tests/service/test_analysis_assignments.py
git commit -m "feat(analysis): players who did not take part in the match"
```

---

### Task 2: запись разметки только в самую новую версию

**Files:**
- Modify: `src/aifootball/service/analysis/assignments.py` (`set_assignments`)
- Test: `tests/service/test_analysis_assignments.py`

- [ ] **Step 1: Падающий тест** — в конец `tests/service/test_analysis_assignments.py`:

```python
def test_only_the_newest_version_takes_labelling(admin_client, analytics_match):
    old = import_run(admin_client, analytics_match)
    new = import_run(admin_client, analytics_match)
    stale = save_assignments(admin_client, analytics_match, old)
    assert stale.status_code == 409
    assert stale.json()['error']['code'] == 'stale_analysis_run'
    assert stale.json()['error']['fields'] == {'newest_run_id': new['id']}
    assert save_assignments(admin_client, analytics_match, new).status_code == 200
```

- [ ] **Step 2: Убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/service/test_analysis_assignments.py -q -k newest`
Expected: FAIL — `assert 200 == 409`.

- [ ] **Step 3: Реализация.** В `assignments.py` заменить импорт моделей и добавить проверку после блока
  `if run.status != 'review': raise ...`:

```python
from aifootball.service.analysis.models import AnalysisAssignment, AnalysisRun, PlayerMatchMetric
```

```python
    # Одна разметка на матч: она живёт в самой новой версии, запись в старую сохранила бы решения мимо неё.
    newest = db.scalar(
        select(AnalysisRun.id)
        .where(AnalysisRun.match_id == run.match_id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .limit(1)
    )
    if newest != run.id:
        raise DomainError(
            'stale_analysis_run',
            'Есть более новая версия разметки. Откройте её.',
            fields={'newest_run_id': str(newest)},
            status=409,
        )
```

- [ ] **Step 4: Тесты анализа и капитанских заданий**

Run: `.venv/bin/python -m pytest tests/service/test_analysis_assignments.py tests/service/test_analysis_versions.py tests/service/test_team_identity_tasks.py tests/service/test_team_identity_confirmations.py tests/service/test_ratings_snapshots.py -q`
Expected: PASS. Если какой-то тест сохраняет разметку в версию, после которой уже загружена другая, — перенести
сохранение до загрузки новой версии (так работает и кабинет); правила проверки не ослаблять.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff format src/aifootball/service/analysis/assignments.py tests/service/test_analysis_assignments.py
git add src/aifootball/service/analysis/assignments.py tests/service/test_analysis_assignments.py
git commit -m "feat(analysis): labelling is saved only into the newest version"
```

---

### Task 3: новая версия забирает разметку прежней

**Files:**
- Create: `src/aifootball/service/analysis/carry.py`
- Modify: `src/aifootball/service/analysis/imports.py` (`import_result`)
- Test: `tests/service/test_analysis_carry.py`

- [ ] **Step 1: Падающие тесты** — `tests/service/test_analysis_carry.py`:

```python
from uuid import uuid4

from .test_analysis_assignments import assignments, import_run, save_assignments
from .test_analysis_jobs import analytics_match, grant  # noqa: F401


def lineup_without(client, match, player_id):
    m = client.get(f'/api/v1/matches/{match["id"]}').json()
    players = [{'entry_player_id': p['entry_player_id'], 'side': p['side']} for p in m['lineup'] if p['player_id'] != player_id]
    r = client.post(
        f'/api/v1/matches/{match["id"]}/commands',
        json={'request_id': str(uuid4()), 'expected_revision': m['revision'], 'kind': 'set_lineup', 'payload': {'players': players}},
    )
    assert r.status_code == 200, r.text


def decisions(run):
    return sorted((a['track_id'], a['player_id'], a['excluded_reason']) for a in run['assignments'])


def test_new_version_takes_the_labelling_when_fragments_match(admin_client, analytics_match):
    old = import_run(admin_client, analytics_match)
    home = [p['player_id'] for p in old['context']['rosters'] if p['side'] == 'home']
    saved = save_assignments(admin_client, analytics_match, old, absent=[home[1]])
    assert saved.status_code == 200, saved.text
    new = import_run(admin_client, analytics_match)
    assert decisions(new) == decisions(saved.json())
    assert new['absent_players'] == [home[1]]
    assert new['side_map_verified'] is True
    assert 'Перенесено решений из прежней версии: 3' in new['checks']['warnings']


def test_decisions_about_players_out_of_the_lineup_stay_behind(admin_client, analytics_match):
    old = import_run(admin_client, analytics_match)
    assert save_assignments(admin_client, analytics_match, old).status_code == 200
    away = assignments(old)[2]['player_id']
    lineup_without(admin_client, analytics_match, away)
    new = import_run(admin_client, analytics_match)
    assert [a['track_id'] for a in new['assignments']] == [1, 2]
    assert 'Перенесено решений из прежней версии: 2; не перенесено (игрок не в составе): 1' in new['checks']['warnings']


def test_new_version_with_other_fragments_starts_empty(admin_client, analytics_match):
    old = import_run(admin_client, analytics_match)
    assert save_assignments(admin_client, analytics_match, old).status_code == 200

    def other(m, r, t, c):
        t['tracks'][1]['intervals'] = [[30, 150]]

    new = import_run(admin_client, analytics_match, other)
    assert new['assignments'] == []
    assert 'Фрагменты отличаются от прежней версии — разметка не перенесена' in new['checks']['warnings']
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/service/test_analysis_carry.py -q`
Expected: FAIL — в новой версии `assignments == []` и нет предупреждения о переносе.

- [ ] **Step 3: Перенос** — `src/aifootball/service/analysis/carry.py`:

```python
"""Одна разметка на матч: новая версия забирает решения прежней самой новой версии, если фрагменты те же.

Решения хранятся по номерам фрагментов, поэтому переносятся только при совпадении номеров, команд, ролей и отрезков.
Решения об игроках, которых нет в составе нового задания, остаются в прежней версии — о них пишет предупреждение.
"""

from sqlalchemy import select

from aifootball.service.analysis.models import AnalysisAssignment, AnalysisRun


def newest_run(db, match_id):
    return db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.match_id == match_id)
        .order_by(AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .limit(1)
    )


def _key(track):
    return (
        track['track_id'],
        track.get('team'),
        track['role'],
        tuple((round(a, 3), round(b, 3)) for a, b in track['intervals']),
    )


def carry_labelling(db, run, previous, job):
    if previous is None:
        return
    rows = db.scalars(select(AnalysisAssignment).where(AnalysisAssignment.run_id == previous.id)).all()
    warnings = list(run.checks.get('warnings') or [])
    if sorted(map(_key, previous.tracks['tracks'])) != sorted(map(_key, run.tracks['tracks'])):
        if rows:
            run.checks = {**run.checks, 'warnings': [*warnings, 'Фрагменты отличаются от прежней версии — разметка не перенесена']}
        return
    roster = {p['player_id'] for p in job.context['rosters']}
    kept = [a for a in rows if a.player_id is None or str(a.player_id) in roster]
    for a in kept:
        db.add(AnalysisAssignment(run_id=run.id, track_id=a.track_id, player_id=a.player_id, excluded_reason=a.excluded_reason))
    run.side_map = dict(previous.side_map)
    run.side_map_verified = previous.side_map_verified
    run.absent_players = [p for p in previous.absent_players or [] if p in roster]
    if rows:
        note = f'Перенесено решений из прежней версии: {len(kept)}'
        if len(kept) < len(rows):
            note += f'; не перенесено (игрок не в составе): {len(rows) - len(kept)}'
        run.checks = {**run.checks, 'warnings': [*warnings, note]}
```

- [ ] **Step 4: Вызов при загрузке.** В `imports.py`, функция `import_result`: внутри `if run is None:` первой
  строкой

```python
        previous = newest_run(db, match_id)
```

и после `db.add(run)` / `db.flush()` (перед `from ... import obsolete_prior_tasks`):

```python
        carry_labelling(db, run, previous, job)
```

Импорт в начале файла:

```python
from aifootball.service.analysis.carry import carry_labelling, newest_run
```

- [ ] **Step 5: Тесты проходят**

Run: `.venv/bin/python -m pytest tests/service/test_analysis_carry.py tests/service/test_analysis_import.py tests/service/test_analysis_versions.py tests/service/test_team_identity_tasks.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
.venv/bin/ruff format src/aifootball/service/analysis/carry.py src/aifootball/service/analysis/imports.py tests/service/test_analysis_carry.py
.venv/bin/ruff check src tests
git add src/aifootball/service/analysis/carry.py src/aifootball/service/analysis/imports.py tests/service/test_analysis_carry.py
git commit -m "feat(analysis): a new version takes the labelling of the previous one"
```

---

### Task 4: «Новая проверка» копирует участие; типы кабинета

**Files:**
- Modify: `src/aifootball/service/analysis/commands.py` (ветка `kind == 'reviews'`)
- Modify: `web/src/api/types.ts` (генерация)
- Test: `tests/service/test_analysis_carry.py`

- [ ] **Step 1: Падающий тест** — в конец `tests/service/test_analysis_carry.py`:

```python
def test_a_new_review_copies_who_did_not_take_part(admin_client, analytics_match):
    from .test_analysis_assignments import command

    run = import_run(admin_client, analytics_match)
    home = [p['player_id'] for p in run['context']['rosters'] if p['side'] == 'home']
    run = save_assignments(admin_client, analytics_match, run, absent=[home[1]]).json()
    confirmed = command(admin_client, analytics_match, run, 'confirm').json()
    review = command(admin_client, analytics_match, confirmed, 'reviews').json()
    assert review['absent_players'] == [home[1]]
```

- [ ] **Step 2: Убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/service/test_analysis_carry.py -q -k review`
Expected: FAIL — `[] == ['…']`.

- [ ] **Step 3: Реализация.** В `commands.py`, в конструкторе `AnalysisRun(...)` ветки `reviews` после
  `side_map_verified=source.side_map_verified,`:

```python
            absent_players=list(source.absent_players or []),
```

- [ ] **Step 4: Тест проходит**

Run: `.venv/bin/python -m pytest tests/service/test_analysis_carry.py tests/service/test_analysis_versions.py -q`
Expected: PASS.

- [ ] **Step 5: Типы кабинета**

```bash
.venv/bin/python scripts/export_service_openapi.py --output data/service/openapi.json
npm --prefix web run types:api
grep -n "absent_players" web/src/api/types.ts
```
Expected: `absent_players` есть в `AssignmentsUpdate` и `RunView`.

- [ ] **Step 6: Commit**

```bash
.venv/bin/ruff format src/aifootball/service/analysis/commands.py tests/service/test_analysis_carry.py
git add src/aifootball/service/analysis/commands.py tests/service/test_analysis_carry.py web/src/api/types.ts
git commit -m "feat(analysis): a new review keeps who did not take part"
```

---

### Task 5: отпечаток разметки с участием

**Files:**
- Modify: `web/src/features/analysis/identityBase.ts`
- Test: `web/src/features/analysis/identityBase.test.ts` (новый)

- [ ] **Step 1: Падающий тест** — `web/src/features/analysis/identityBase.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { identityFingerprint } from './identityBase';

const base = { side_map: { A: 'home', B: 'away' }, assignments: [{ track_id: 1, player_id: 'p1' }] };

describe('identity fingerprint', () => {
  it('keeps old fingerprints when nobody is marked absent', () => {
    expect(identityFingerprint({ ...base, absent_players: [] })).toBe(identityFingerprint(base));
  });

  it('changes when a player is marked absent, regardless of order', () => {
    const a = identityFingerprint({ ...base, absent_players: ['p2', 'p3'] });
    expect(a).not.toBe(identityFingerprint(base));
    expect(identityFingerprint({ ...base, absent_players: ['p3', 'p2'] })).toBe(a);
  });
});
```

- [ ] **Step 2: Убедиться, что падает**

Run: `cd web && npx vitest run src/features/analysis/identityBase.test.ts`
Expected: FAIL — отпечатки с участием и без совпадают.

- [ ] **Step 3: Реализация.** В `identityBase.ts` заменить сигнатуру и строку `const text = ...`:

```ts
export function identityFingerprint(review: {
  side_map: Record<string, string>;
  assignments: AnalysisAssignment[];
  absent_players?: string[];
}) {
```

```ts
  // Участие входит в отпечаток, только если кто-то отмечен: прежние черновики не становятся «устаревшими».
  const absent = [...(review.absent_players ?? [])].sort();
  const text = JSON.stringify(absent.length ? [sides, rows, absent] : [sides, rows]);
```

- [ ] **Step 4: Тест проходит**

Run: `cd web && npx vitest run src/features/analysis/identityBase.test.ts src/features/analysis/ReviewWorkspace.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd web && npx biome format --write src/features/analysis/identityBase.ts src/features/analysis/identityBase.test.ts && cd ..
git add web/src/features/analysis/identityBase.ts web/src/features/analysis/identityBase.test.ts
git commit -m "feat(review): the labelling fingerprint includes who did not take part"
```

---

### Task 6: очередь — чистые функции `queue.ts`

**Files:**
- Create: `web/src/features/analysis/identityFixtures.ts`
- Create: `web/src/features/analysis/queue.ts`
- Test: `web/src/features/analysis/queue.test.ts`

- [ ] **Step 1: Общие тестовые данные** — `web/src/features/analysis/identityFixtures.ts` (кодом приложения не
  импортируется; им пользуются тесты задач 6–15):

```ts
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';

// Признак цвета из пакета: 156 байт в base64. «Красная» и «синяя» форма, косинус между ними ≈ 0,19.
const look = (hot: number) =>
  btoa(String.fromCharCode(...Array.from({ length: 156 }, (_, i) => (i === hot ? 255 : 8))));
export const RED = look(0);
export const BLUE = look(40);
const track = (id: number, team: string, from: number, to: number, appearance: string | null) => ({
  track_id: id,
  team,
  role: 'player',
  intervals: [[from, to]],
  thumb: `thumbs/${id}.jpg`,
  has_metrics: true,
  appearance,
});
const teams = { home: { id: 't1', name: 'Север' }, away: { id: 't2', name: 'Юг' } };
const p1 = { player_id: 'p1', side: 'home', display_name: 'Север · игрок 1', shirt_number: '7' };
const p2 = { player_id: 'p2', side: 'home', display_name: 'Север · игрок 2', shirt_number: null };
const p3 = { player_id: 'p3', side: 'home', display_name: 'Север · игрок 3', shirt_number: '3' };
const p9 = { player_id: 'p9', side: 'away', display_name: 'Юг · игрок 1', shirt_number: null };
// A: 1 красный (0:00–0:40) у p1, 4 синий (1:40–2:40) у p2; открыты по времени 3 синий (0:00–0:30, виден вместе с 1),
// 2 красный (0:50–1:30), 6 без признака (2:50–2:55), 5 синий (3:20–3:50). B: 7 (0–150).
const tracks = [
  track(1, 'A', 0, 40, RED),
  track(2, 'A', 50, 90, RED),
  track(3, 'A', 0, 30, BLUE),
  track(4, 'A', 100, 160, BLUE),
  track(5, 'A', 200, 230, BLUE),
  track(6, 'A', 170, 175, null),
  track(7, 'B', 0, 150, RED),
];
export const smallRun = {
  id: 'run',
  job_id: 'job',
  match_id: 'match',
  revision: 0,
  status: 'review',
  context: { teams, rosters: [p1, p2, p9] },
  side_map: { A: 'home', B: 'away' },
  assignments: [],
  tracks,
  groups: [],
} as unknown as AnalysisRun;
// Плюс игрок p3 (№3) без фрагментов и красные 8 (5:00–5:40), 9 и 10, видные одновременно (6:40–7:20, 6:50–7:30).
export const wideRun = {
  ...smallRun,
  context: { teams, rosters: [p1, p2, p3, p9] },
  tracks: [...tracks, track(8, 'A', 300, 340, RED), track(9, 'A', 400, 440, RED), track(10, 'A', 410, 450, RED)],
} as unknown as AnalysisRun;
export const sideMap = { A: 'home', B: 'away' } as AnalysisRun['side_map'];
export const base: AnalysisAssignment[] = [
  { track_id: 1, player_id: 'p1' },
  { track_id: 4, player_id: 'p2' },
];
```

- [ ] **Step 2: Падающие тесты** — `web/src/features/analysis/queue.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { baseGroups, candidatesOf } from './candidates';
import { base, wideRun as run } from './identityFixtures';
import { available, confidentHint, QUEUE_MARGIN, queueOrder, queuePlayers } from './queue';
import { lookIndex } from './similar';

const index = lookIndex(run);
const candidates = candidatesOf(run, baseGroups(run));
const rosters = run.context.rosters;
const cand = (key: string) => candidates.filter((c) => c.key === key)[0];

describe('identity queue', () => {
  it('takes open candidates of the team by start time', () => {
    expect(queueOrder(candidates, 'A', base)).toEqual(['3', '2', '6', '5', '8', '9', '10']);
  });

  it('lists players in a fixed order by shirt number, without the absent ones', () => {
    expect(queuePlayers(index, rosters, 'home', [], base).map((p) => p.id)).toEqual(['p3', 'p1', 'p2']);
    const players = queuePlayers(index, rosters, 'home', ['p3'], base);
    expect(players.map((p) => [p.key, p.label])).toEqual([
      ['1', '№7 Север · игрок 1'],
      ['2', 'Север · игрок 2'],
    ]);
  });

  it('marks a player seen together with the candidate as unavailable', () => {
    const [p1, p2] = queuePlayers(index, rosters, 'home', ['p3'], base);
    expect(available(index, p1, cand('3'))).toBe(false);
    expect(available(index, p2, cand('3'))).toBe(true);
  });

  it('gives only a confident colour hint', () => {
    const players = queuePlayers(index, rosters, 'home', [], base);
    expect(confidentHint(index, players, cand('5'))).toBe('p2');
    expect(confidentHint(index, players, cand('2'))).toBe('p1');
    expect(confidentHint(index, players, cand('6'))).toBeNull();
    // p1 и p3 одинаково красные: отрыв 0 — подсказки нет.
    const twins = queuePlayers(index, rosters, 'home', [], [...base, { track_id: 8, player_id: 'p3' }]);
    expect(confidentHint(index, twins, cand('2'))).toBeNull();
    expect(QUEUE_MARGIN).toBe(0.05);
  });
});
```

- [ ] **Step 3: Убедиться, что падают**

Run: `cd web && npx vitest run src/features/analysis/queue.test.ts`
Expected: FAIL — `Failed to resolve import "./queue"`.

- [ ] **Step 4: Реализация** — `web/src/features/analysis/queue.ts`:

```ts
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { type Candidate, decisionOf } from './candidates';
import { clash, cosine, type LookIndex, meanLook } from './similar';

// Уверенная подсказка: лучший доступный игрок обходит второго по цвету формы не меньше чем на 0,05. Замер ВШЭ Ю —
// JWH (513 фрагментов, по одному вне выборки): такая подсказка у 20% фрагментов и верна в 97%; остальные без неё.
export const QUEUE_MARGIN = 0.05;
const KEYS = '1234567890';

type Roster = AnalysisRun['context']['rosters'];
export type QueuePlayer = { id: string; label: string; key: string; own: number[]; mean: ReturnType<typeof meanLook> };

const shirt = (value: string | null | undefined) =>
  value && Number.isFinite(Number(value)) ? Number(value) : Number.POSITIVE_INFINITY;

// Игроки стороны в постоянном порядке — по номеру, без номера по имени в конце; клавиши 1–9 и 0 по этому порядку.
// Не участвовавшие в матче не показываются.
export function queuePlayers(
  index: LookIndex,
  roster: Roster,
  side: string,
  absent: string[],
  assignments: AnalysisAssignment[],
): QueuePlayer[] {
  return roster
    .filter((p) => p.side === side && !absent.includes(p.player_id))
    .sort((a, b) => shirt(a.shirt_number) - shirt(b.shirt_number) || a.display_name.localeCompare(b.display_name, 'ru'))
    .map((p, i) => {
      const own = assignments.filter((x) => x.player_id === p.player_id).map((x) => x.track_id);
      return {
        id: p.player_id,
        label: `${p.shirt_number ? `№${p.shirt_number} ` : ''}${p.display_name}`,
        key: KEYS[i] ?? '',
        own,
        mean: own.length ? meanLook(index, own) : null,
      };
    });
}

// Снимок очереди: неназначенные кандидаты команды по времени начала. Порядок не меняется до нового снимка.
export function queueOrder(candidates: Candidate[], team: 'A' | 'B', assignments: AnalysisAssignment[]): string[] {
  return candidates
    .filter((c) => c.team === team && decisionOf(assignments, c.trackIds).kind === 'none')
    .sort((a, b) => a.span[0] - b.span[0] || a.key.localeCompare(b.key))
    .map((c) => c.key);
}

// Игрок недоступен, если по разметке он на площадке одновременно с кандидатом (правило сервера, больше 1 с).
export const available = (index: LookIndex, player: QueuePlayer, candidate: Candidate) =>
  !player.own.length || !clash(index, player.own, candidate.trackIds);

export function confidentHint(index: LookIndex, players: QueuePlayer[], candidate: Candidate): string | null {
  const look = meanLook(index, candidate.trackIds);
  if (!look) return null;
  const scored = players
    .flatMap((p) => (p.mean && available(index, p, candidate) ? [{ id: p.id, score: cosine(p.mean, look) }] : []))
    .sort((a, b) => b.score - a.score);
  if (!scored.length) return null;
  return scored[0].score - (scored[1]?.score ?? 0) >= QUEUE_MARGIN ? scored[0].id : null;
}
```

- [ ] **Step 5: Тесты проходят**

Run: `cd web && npx vitest run src/features/analysis/queue.test.ts && npx tsc -b`
Expected: PASS, 4 теста; `tsc` без ошибок.

- [ ] **Step 6: Commit**

```bash
cd web && npx biome format --write src/features/analysis/identityFixtures.ts src/features/analysis/queue.ts src/features/analysis/queue.test.ts && cd ..
git add web/src/features/analysis/identityFixtures.ts web/src/features/analysis/queue.ts web/src/features/analysis/queue.test.ts
git commit -m "feat(review): identity queue order, players and a confident hint"
```

---

### Task 7: экран «Очередь»

**Files:**
- Create: `web/src/features/analysis/IdentityQueue.tsx`
- Modify: `web/src/features/analysis/review.css` (в конец)
- Test: `web/src/features/analysis/IdentityQueue.test.tsx`

- [ ] **Step 1: Падающие тесты** — `web/src/features/analysis/IdentityQueue.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { AnalysisAssignment } from '../../api/domain';
import { IdentityQueue } from './IdentityQueue';
import { base, sideMap, smallRun as run } from './identityFixtures';

function Harness({ onChange }: { onChange: (next: AnalysisAssignment[]) => void }) {
  const [assignments, setAssignments] = useState(base);
  return (
    <IdentityQueue
      run={run}
      assignments={assignments}
      sideMap={sideMap}
      absent={[]}
      disabled={false}
      onChange={(next) => {
        onChange(next);
        setAssignments(next);
      }}
    />
  );
}
const show = (onChange = vi.fn()) => {
  render(<Harness onChange={onChange} />);
  return onChange;
};
const last = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls[fn.mock.calls.length - 1][0] as AnalysisAssignment[];
const key = (k: string) => fireEvent.keyDown(window, { key: k });

describe('identity queue', () => {
  it('goes through open fragments by time and keeps the order after a decision', () => {
    const onChange = show();
    expect(screen.getByText(/0:00–0:30 · 30 с/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '1 · №7 Север · игрок 1' })).toBeDisabled();
    key('2');
    expect(last(onChange)).toContainEqual({ track_id: 3, player_id: 'p2' });
    expect(screen.getByText(/0:50–1:30 · 40 с/)).toBeInTheDocument();
    expect(screen.getByRole('status', { name: 'Прогресс очереди' })).toHaveTextContent('фрагмент 2 из 4 · осталось 3');
  });

  it('passes skipped fragments again at the end', () => {
    const onChange = show();
    key(' ');
    key('x');
    expect(last(onChange)).toContainEqual({ track_id: 2, excluded_reason: 'Не игрок матча' });
    key('x');
    key('2');
    expect(screen.getByText(/пропущено: 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Пройти пропущенные' }));
    expect(screen.getByText(/0:00–0:30 · 30 с/)).toBeInTheDocument();
  });

  it('undoes the last decision', () => {
    const onChange = show();
    key('2');
    key('Backspace');
    expect(last(onChange)).toEqual(base);
    expect(screen.getByText(/0:00–0:30 · 30 с/)).toBeInTheDocument();
  });

  it('highlights only a confident hint and never reorders the players', () => {
    show();
    expect(screen.getByRole('button', { name: '2 · Север · игрок 2' })).toHaveClass('hinted');
    key(' ');
    expect(screen.getByRole('button', { name: '1 · №7 Север · игрок 1' })).toHaveClass('hinted');
    key(' ');
    expect(screen.getByText('подсказки нет')).toBeInTheDocument();
    const names = screen.getAllByRole('button', { name: /Север · игрок/ }).map((b) => b.textContent);
    expect(names).toEqual(['1 · №7 Север · игрок 1', '2 · Север · игрок 2']);
  });
});
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd web && npx vitest run src/features/analysis/IdentityQueue.test.tsx`
Expected: FAIL — `Failed to resolve import "./IdentityQueue"`.

- [ ] **Step 3: Компонент** — `web/src/features/analysis/IdentityQueue.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { CandidateThumb } from './CandidateThumb';
import { assignGroup, baseGroups, candidatesOf, clock, decisionOf } from './candidates';
import { available, confidentHint, queueOrder, queuePlayers } from './queue';
import { lookIndex } from './similar';

type Step = { key: string; before: AnalysisAssignment[] };
const EXCLUDE_KEYS = ['x', 'X', 'ч', 'Ч'];

// Очередь разметки: один неназначенный фрагмент команды за раз, кнопки игроков в постоянном порядке. Порядок —
// снимок по времени: после решения ничего не перестраивается, пропущенные проходят в конце отдельным кругом.
export function IdentityQueue({
  run,
  assignments,
  sideMap,
  absent,
  disabled,
  onChange,
}: {
  run: AnalysisRun;
  assignments: AnalysisAssignment[];
  sideMap: AnalysisRun['side_map'];
  absent: string[];
  disabled: boolean;
  onChange: (next: AnalysisAssignment[]) => void;
}) {
  const index = useMemo(() => lookIndex(run), [run]);
  const candidates = useMemo(() => candidatesOf(run, baseGroups(run)), [run]);
  const byKey = useMemo(() => new Map(candidates.map((c) => [c.key, c])), [candidates]);
  const [team, setTeam] = useState<'A' | 'B'>('A');
  const [order, setOrder] = useState(() => queueOrder(candidates, 'A', assignments));
  const [pos, setPos] = useState(0);
  const [skipped, setSkipped] = useState<string[]>([]);
  const [history, setHistory] = useState<Step[]>([]);
  const open = (key: string) => decisionOf(assignments, byKey.get(key)?.trackIds ?? []).kind === 'none';
  const at = order.findIndex((k, i) => i >= pos && open(k) && !skipped.includes(k));
  const current = at >= 0 ? byKey.get(order[at]) : undefined;
  const players = queuePlayers(index, run.context.rosters, sideMap[team], absent, assignments);
  const hint = current ? confidentHint(index, players, current) : null;
  const left = order.filter(open).length;

  function restart(nextTeam: 'A' | 'B', keys?: string[]) {
    setTeam(nextTeam);
    setOrder(keys ?? queueOrder(candidates, nextTeam, assignments));
    setPos(0);
    setSkipped([]);
    setHistory([]);
  }
  function decide(value: string) {
    if (!current || disabled) return;
    setHistory((h) => [...h, { key: current.key, before: assignments }]);
    setPos(at + 1);
    onChange(assignGroup(assignments, current.trackIds, value));
  }
  function skip() {
    if (!current) return;
    setSkipped((s) => [...s, current.key]);
    setPos(at + 1);
  }
  function undo() {
    const step = history[history.length - 1];
    if (!step || disabled) return;
    setHistory((h) => h.slice(0, -1));
    setPos(Math.max(0, order.indexOf(step.key)));
    onChange(step.before);
  }
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLElement && ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const player = players.find((p) => p.key && p.key === e.key);
      if (player) {
        e.preventDefault();
        if (current && available(index, player, current)) decide(player.id);
      } else if (EXCLUDE_KEYS.includes(e.key)) {
        e.preventDefault();
        decide('exclude');
      } else if (e.key === ' ') {
        e.preventDefault();
        skip();
      } else if (e.key === 'Backspace') {
        e.preventDefault();
        undo();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  return (
    <section className="identity-queue" aria-label="Очередь разметки">
      <div className="similar-head">
        <div className="segmented review-mode" role="group" aria-label="Команда">
          {(['A', 'B'] as const).map((t) => (
            <button type="button" key={t} aria-pressed={team === t} onClick={() => restart(t)}>
              {run.context.teams[sideMap[t]].name}
            </button>
          ))}
        </div>
        <span className="muted small num" role="status" aria-label="Прогресс очереди">
          {current ? `фрагмент ${at + 1} из ${order.length} · ` : ''}осталось {left}
        </span>
      </div>
      {current ? (
        <div className="queue-body">
          <CandidateThumb run={run} index={index} candidate={current} className="queue" />
          <div className="queue-side">
            <p className="queue-title num">
              {clock(current.span[0])}–{clock(current.span[1])} · {Math.round(current.seconds)} с
              {current.goalkeeper ? ' · вратарь' : ''}
            </p>
            <p className="muted small">
              {hint ? `похож на ${players.find((p) => p.id === hint)?.label} (уверенно)` : 'подсказки нет'}
            </p>
            <div className="queue-players" role="group" aria-label="Игрок фрагмента">
              {players.map((p) => {
                const free = available(index, p, current);
                return (
                  <button
                    type="button"
                    key={p.id}
                    className={`queue-player${p.id === hint ? ' hinted' : ''}`}
                    disabled={disabled || !free}
                    title={free ? undefined : 'На площадке в это время'}
                    onClick={() => decide(p.id)}
                  >
                    {p.key ? `${p.key} · ` : ''}
                    {p.label}
                  </button>
                );
              })}
            </div>
            <div className="row wrap">
              <button type="button" disabled={disabled} onClick={() => decide('exclude')}>
                X · Не игрок матча
              </button>
              <button type="button" onClick={skip}>
                Пробел · Пропустить
              </button>
              <button type="button" disabled={disabled || !history.length} onClick={undo}>
                Назад
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="row wrap">
          <p className="muted">
            Все фрагменты команды в очереди размечены{skipped.length ? `, пропущено: ${skipped.length}` : ''}.
          </p>
          {skipped.length > 0 && (
            <button type="button" onClick={() => restart(team, skipped.filter(open))}>
              Пройти пропущенные
            </button>
          )}
          <button type="button" disabled={disabled || !history.length} onClick={undo}>
            Назад
          </button>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Стили** — в конец `web/src/features/analysis/review.css`:

```css
.identity-queue,
.identity-grid,
.players-panel {
  display: grid;
  gap: 12px;
}
.queue-body {
  display: grid;
  grid-template-columns: minmax(0, 260px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.track-thumb.queue,
.thumb-missing.queue {
  width: 100%;
  height: 300px;
  object-fit: contain;
  border-radius: 6px;
  background: var(--surface-2);
}
.queue-title {
  margin: 0;
  font-weight: 500;
}
.queue-players {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 6px;
}
.queue-player {
  text-align: left;
}
.queue-player:disabled {
  border-style: dashed;
}
.queue-player.hinted {
  border-color: var(--ok);
  background: var(--ok-soft);
}
@media (max-width: 600px) {
  .queue-body {
    grid-template-columns: minmax(0, 1fr);
  }
  .track-thumb.queue,
  .thumb-missing.queue {
    height: 220px;
  }
}
```

- [ ] **Step 5: Тесты проходят**

Run: `cd web && npx vitest run src/features/analysis/IdentityQueue.test.tsx && npx tsc -b`
Expected: PASS, 4 теста.

- [ ] **Step 6: Commit**

```bash
cd web && npx biome format --write src/features/analysis/IdentityQueue.tsx src/features/analysis/IdentityQueue.test.tsx src/features/analysis/review.css && cd ..
git add web/src/features/analysis/IdentityQueue.tsx web/src/features/analysis/IdentityQueue.test.tsx web/src/features/analysis/review.css
git commit -m "feat(review): identity queue, one fragment at a time with fixed player keys"
```

---

### Task 8: сетка — чистые функции `grid.ts`

**Files:**
- Create: `web/src/features/analysis/grid.ts`
- Test: `web/src/features/analysis/grid.test.ts`

- [ ] **Step 1: Падающие тесты** — `web/src/features/analysis/grid.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { baseGroups, candidatesOf } from './candidates';
import { applyClass, gridOrder, rangeKeys } from './grid';
import { base, wideRun as run } from './identityFixtures';
import { lookIndex } from './similar';

const index = lookIndex(run);
const candidates = candidatesOf(run, baseGroups(run));
const cand = (key: string) => candidates.filter((c) => c.key === key)[0];

describe('identity grid', () => {
  it('filters by class and sorts by time or by similarity to a player', () => {
    expect(gridOrder(index, candidates, 'A', base, 'open', null)).toEqual(['3', '2', '6', '5', '8', '9', '10']);
    expect(gridOrder(index, candidates, 'A', base, 'p1', null)).toEqual(['1']);
    expect(gridOrder(index, candidates, 'A', [...base, { track_id: 6, excluded_reason: 'Не игрок матча' }], 'excluded', null)).toEqual(['6']);
    // Похожие на синего p2: синие 3 и 5, затем красные по времени, без признака — в конце.
    expect(gridOrder(index, candidates, 'A', base, 'open', 'p2')).toEqual(['3', '5', '2', '8', '9', '10', '6']);
  });

  it('gives a class to the picked fragments, skipping ones seen together', () => {
    const one = applyClass(index, base, [cand('3'), cand('2')], 'p1');
    expect(one.skipped).toEqual(['3']);
    expect(one.next).toContainEqual({ track_id: 2, player_id: 'p1' });
    const pair = applyClass(index, base, [cand('9'), cand('10')], 'p2');
    expect(pair.skipped).toEqual(['10']);
    expect(applyClass(index, base, [cand('6')], 'exclude').next).toContainEqual({
      track_id: 6,
      excluded_reason: 'Не игрок матча',
    });
    expect(applyClass(index, base, [cand('1')], '').next).toEqual([{ track_id: 4, player_id: 'p2' }]);
  });

  it('selects a range between two tiles in either direction', () => {
    const order = ['3', '2', '6', '5'];
    expect(rangeKeys(order, '3', '6')).toEqual(['3', '2', '6']);
    expect(rangeKeys(order, '6', '3')).toEqual(['3', '2', '6']);
    expect(rangeKeys(order, 'x', '5')).toEqual(['5']);
  });
});
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd web && npx vitest run src/features/analysis/grid.test.ts`
Expected: FAIL — `Failed to resolve import "./grid"`.

- [ ] **Step 3: Реализация** — `web/src/features/analysis/grid.ts`:

```ts
import type { AnalysisAssignment } from '../../api/domain';
import { assignGroup, type Candidate, decisionOf } from './candidates';
import { clash, cosine, type LookIndex, meanLook } from './similar';

export const PAGE_TILES = 60;

// Плитка сетки: кандидаты команды выбранного класса — 'open' (неназначенные), 'excluded', 'all' или id игрока;
// по времени или по похожести на игрока (similarTo). Снимок — порядок меняется только по действию человека.
export function gridOrder(
  index: LookIndex,
  candidates: Candidate[],
  team: 'A' | 'B',
  assignments: AnalysisAssignment[],
  show: string,
  similarTo: string | null,
): string[] {
  const keep = candidates.filter((c) => {
    if (c.team !== team) return false;
    const d = decisionOf(assignments, c.trackIds);
    if (show === 'open') return d.kind === 'none';
    if (show === 'excluded') return d.kind === 'excluded';
    if (show === 'all') return true;
    return d.kind === 'player' && d.playerId === show;
  });
  const byTime = (a: Candidate, b: Candidate) => a.span[0] - b.span[0] || a.key.localeCompare(b.key);
  if (!similarTo) return [...keep].sort(byTime).map((c) => c.key);
  const own = assignments.filter((a) => a.player_id === similarTo).map((a) => a.track_id);
  const mean = own.length ? meanLook(index, own) : null;
  const score = (c: Candidate) => {
    const look = meanLook(index, c.trackIds);
    return mean && look ? cosine(mean, look) : -2;
  };
  return [...keep].sort((a, b) => score(b) - score(a) || byTime(a, b)).map((c) => c.key);
}

// Присвоить класс: id игрока, 'exclude' или '' (снять). Класс игрока не получают кадры, видные одновременно с его
// остальными фрагментами или с более ранним кадром той же операции (правило сервера, больше 1 с).
export function applyClass(
  index: LookIndex,
  assignments: AnalysisAssignment[],
  picked: Candidate[],
  value: string,
): { next: AnalysisAssignment[]; skipped: string[] } {
  const player = value !== '' && value !== 'exclude';
  const pickedIds = new Set(picked.flatMap((c) => c.trackIds));
  const taken = player
    ? assignments.filter((a) => a.player_id === value && !pickedIds.has(a.track_id)).map((a) => a.track_id)
    : [];
  let next = assignments;
  const skipped: string[] = [];
  for (const c of picked) {
    if (player && taken.length && clash(index, taken, c.trackIds)) {
      skipped.push(c.key);
      continue;
    }
    if (player) taken.push(...c.trackIds);
    next = assignGroup(next, c.trackIds, value);
  }
  return { next, skipped };
}

// Диапазон выделения Shift + щелчок: от якоря до кадра включительно, в любую сторону.
export function rangeKeys(order: string[], from: string, to: string): string[] {
  const i = order.indexOf(from);
  const j = order.indexOf(to);
  if (i < 0 || j < 0) return [to];
  return order.slice(Math.min(i, j), Math.max(i, j) + 1);
}
```

- [ ] **Step 4: Тесты проходят**

Run: `cd web && npx vitest run src/features/analysis/grid.test.ts && npx tsc -b`
Expected: PASS, 3 теста.

- [ ] **Step 5: Commit**

```bash
cd web && npx biome format --write src/features/analysis/grid.ts src/features/analysis/grid.test.ts && cd ..
git add web/src/features/analysis/grid.ts web/src/features/analysis/grid.test.ts
git commit -m "feat(review): grid order, class assignment and range selection"
```

---

### Task 9: экран «Сетка»

**Files:**
- Create: `web/src/features/analysis/IdentityGrid.tsx`
- Modify: `web/src/features/analysis/review.css` (в конец)
- Test: `web/src/features/analysis/IdentityGrid.test.tsx`

- [ ] **Step 1: Падающие тесты** — `web/src/features/analysis/IdentityGrid.test.tsx`:

```tsx
import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { AnalysisAssignment } from '../../api/domain';
import { IdentityGrid } from './IdentityGrid';
import { base, sideMap, smallRun as run } from './identityFixtures';

function Harness({ onChange }: { onChange: (next: AnalysisAssignment[]) => void }) {
  const [assignments, setAssignments] = useState(base);
  return (
    <IdentityGrid
      run={run}
      assignments={assignments}
      sideMap={sideMap}
      absent={[]}
      disabled={false}
      onChange={(next) => {
        onChange(next);
        setAssignments(next);
      }}
    />
  );
}
const show = (onChange = vi.fn()) => {
  render(<Harness onChange={onChange} />);
  return onChange;
};
const last = (fn: ReturnType<typeof vi.fn>) => fn.mock.calls[fn.mock.calls.length - 1][0] as AnalysisAssignment[];
const tile = (span: string) => screen.getByRole('button', { name: `Фрагмент ${span}` });

describe('identity grid', () => {
  it('assigns with the brush on click and clears on a second click', () => {
    const onChange = show();
    fireEvent.click(screen.getByRole('button', { name: '2 · Север · игрок 2' }));
    fireEvent.click(tile('3:20–3:50'));
    expect(last(onChange)).toContainEqual({ track_id: 5, player_id: 'p2' });
    expect(tile('3:20–3:50')).toHaveTextContent('Север · игрок 2');
    fireEvent.click(tile('3:20–3:50'));
    expect(last(onChange).some((a) => a.track_id === 5)).toBe(false);
  });

  it('selects with Ctrl and gives the class key to every selected tile', () => {
    const onChange = show();
    fireEvent.click(tile('0:00–0:30'), { ctrlKey: true });
    fireEvent.click(tile('3:20–3:50'), { ctrlKey: true });
    expect(screen.getByRole('status', { name: 'Выделение' })).toHaveTextContent('выделено: 2');
    fireEvent.keyDown(window, { key: '2' });
    expect(last(onChange)).toEqual(
      expect.arrayContaining([
        { track_id: 3, player_id: 'p2' },
        { track_id: 5, player_id: 'p2' },
      ]),
    );
    expect(screen.getByRole('status', { name: 'Выделение' })).toHaveTextContent('выделено: 0');
  });

  it('selects a range with Shift and excludes it', () => {
    const onChange = show();
    fireEvent.click(tile('0:00–0:30'), { ctrlKey: true });
    fireEvent.click(tile('2:50–2:55'), { shiftKey: true });
    fireEvent.click(screen.getByRole('button', { name: 'X · Не игрок матча' }));
    const excluded = last(onChange).filter((a) => a.excluded_reason === 'Не игрок матча').map((a) => a.track_id);
    expect(excluded.sort()).toEqual([2, 3, 6]);
  });

  it('refuses a fragment seen together with the player and counts it', () => {
    const onChange = show();
    fireEvent.click(screen.getByRole('button', { name: '1 · №7 Север · игрок 1' }));
    fireEvent.click(tile('0:00–0:30'));
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('status', { name: 'Не назначено' })).toHaveTextContent(
      'Не назначено из-за одновременности: 1',
    );
  });

  it('keeps tiles in place until refresh', () => {
    show();
    fireEvent.click(screen.getByRole('button', { name: '2 · Север · игрок 2' }));
    fireEvent.click(tile('3:20–3:50'));
    expect(tile('3:20–3:50')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Обновить' }));
    expect(screen.queryByRole('button', { name: 'Фрагмент 3:20–3:50' })).toBeNull();
  });
});
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd web && npx vitest run src/features/analysis/IdentityGrid.test.tsx`
Expected: FAIL — `Failed to resolve import "./IdentityGrid"`.

- [ ] **Step 3: Компонент** — `web/src/features/analysis/IdentityGrid.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { CandidateThumb } from './CandidateThumb';
import { baseGroups, type Candidate, candidatesOf, clock, decisionOf } from './candidates';
import { applyClass, gridOrder, PAGE_TILES, rangeKeys } from './grid';
import { queuePlayers } from './queue';
import { lookIndex } from './similar';

const EXCLUDE_KEYS = ['x', 'X', 'ч', 'Ч'];
type Click = { ctrlKey: boolean; metaKey: boolean; shiftKey: boolean };

// Сетка: кадры выбранного класса, кисть класса (щелчок присваивает, повторный снимает) и массовый выбор
// (Ctrl/⌘, Shift, «выделить все»). Плитка — снимок: после присвоения кадр остаётся на месте до «Обновить».
export function IdentityGrid({
  run,
  assignments,
  sideMap,
  absent,
  disabled,
  onChange,
}: {
  run: AnalysisRun;
  assignments: AnalysisAssignment[];
  sideMap: AnalysisRun['side_map'];
  absent: string[];
  disabled: boolean;
  onChange: (next: AnalysisAssignment[]) => void;
}) {
  const index = useMemo(() => lookIndex(run), [run]);
  const candidates = useMemo(() => candidatesOf(run, baseGroups(run)), [run]);
  const byKey = useMemo(() => new Map(candidates.map((c) => [c.key, c])), [candidates]);
  const names = useMemo(
    () => new Map(run.context.rosters.map((p) => [p.player_id, p.shirt_number ? `№${p.shirt_number}` : p.display_name])),
    [run],
  );
  const [team, setTeam] = useState<'A' | 'B'>('A');
  const [show, setShow] = useState('open');
  const [similarTo, setSimilarTo] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [tiles, setTiles] = useState(() => gridOrder(index, candidates, 'A', assignments, 'open', null));
  const [brush, setBrush] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [anchor, setAnchor] = useState<string | null>(null);
  const [clashed, setClashed] = useState<string[]>([]);
  const players = queuePlayers(index, run.context.rosters, sideMap[team], absent, assignments);
  const pages = Math.max(1, Math.ceil(tiles.length / PAGE_TILES));
  const visible = tiles.slice(page * PAGE_TILES, (page + 1) * PAGE_TILES);

  function refresh(next: { team?: 'A' | 'B'; show?: string; similarTo?: string | null } = {}) {
    const t = next.team ?? team;
    const s = next.show ?? show;
    const sim = next.similarTo === undefined ? similarTo : next.similarTo;
    setTeam(t);
    setShow(s);
    setSimilarTo(sim);
    setPage(0);
    setSelected([]);
    setAnchor(null);
    setClashed([]);
    setTiles(gridOrder(index, candidates, t, assignments, s, sim));
  }
  function apply(keys: string[], value: string) {
    const picked = keys.flatMap((k) => {
      const c = byKey.get(k);
      return c ? [c] : [];
    });
    const { next, skipped } = applyClass(index, assignments, picked, value);
    setClashed(skipped);
    if (next !== assignments) onChange(next);
  }
  // Кнопка или клавиша класса: меняет кисть; при выделении — присваивает класс всем выделенным.
  function choose(value: string) {
    if (disabled) return;
    setBrush(value);
    if (!selected.length) return;
    apply(selected, value);
    setSelected([]);
    setAnchor(null);
  }
  function click(key: string, e: Click) {
    if (e.shiftKey && anchor) {
      setSelected((s) => [...new Set([...s, ...rangeKeys(tiles, anchor, key)])]);
      return;
    }
    if (e.ctrlKey || e.metaKey) {
      setSelected((s) => (s.includes(key) ? s.filter((k) => k !== key) : [...s, key]));
      setAnchor(key);
      return;
    }
    const c = byKey.get(key);
    if (disabled || brush === null || !c) return;
    const d = decisionOf(assignments, c.trackIds);
    const same = (brush === 'exclude' && d.kind === 'excluded') || (d.kind === 'player' && d.playerId === brush);
    apply([key], same ? '' : brush);
  }
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLElement && ['INPUT', 'SELECT', 'TEXTAREA'].includes(e.target.tagName)) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const player = players.find((p) => p.key && p.key === e.key);
      if (player) choose(player.id);
      else if (EXCLUDE_KEYS.includes(e.key)) choose('exclude');
      else if (e.key === 'Delete') choose('');
      else if (e.key === 'Escape') setSelected([]);
      else return;
      e.preventDefault();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });
  const label = (c: Candidate) => {
    const d = decisionOf(assignments, c.trackIds);
    if (d.kind === 'player') return names.get(d.playerId ?? '') ?? '';
    if (d.kind === 'excluded') return 'не игрок';
    return d.kind === 'mixed' ? 'разные' : '';
  };

  return (
    <section className="identity-grid" aria-label="Сетка разметки">
      <div className="similar-head">
        <div className="segmented review-mode" role="group" aria-label="Команда">
          {(['A', 'B'] as const).map((t) => (
            <button type="button" key={t} aria-pressed={team === t} onClick={() => refresh({ team: t })}>
              {run.context.teams[sideMap[t]].name}
            </button>
          ))}
        </div>
        <label className="field">
          <span>Показать</span>
          <select aria-label="Показать" value={show} onChange={(e) => refresh({ show: e.target.value })}>
            <option value="open">Неназначенные</option>
            {players.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
            <option value="excluded">Не игроки матча</option>
            <option value="all">Все</option>
          </select>
        </label>
        <label className="field">
          <span>Порядок</span>
          <select
            aria-label="Порядок"
            value={similarTo ?? ''}
            onChange={(e) => refresh({ similarTo: e.target.value || null })}
          >
            <option value="">По времени</option>
            {players
              .filter((p) => p.mean)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  Похожие на {p.label}
                </option>
              ))}
          </select>
        </label>
        <button type="button" onClick={() => refresh()}>
          Обновить
        </button>
      </div>
      <div className="grid-brush" role="group" aria-label="Кисть">
        {players.map((p) => (
          <button type="button" key={p.id} aria-pressed={brush === p.id} disabled={disabled} onClick={() => choose(p.id)}>
            {p.key ? `${p.key} · ` : ''}
            {p.label}
          </button>
        ))}
        <button type="button" aria-pressed={brush === 'exclude'} disabled={disabled} onClick={() => choose('exclude')}>
          X · Не игрок матча
        </button>
        <button type="button" aria-pressed={brush === ''} disabled={disabled} onClick={() => choose('')}>
          Delete · Снять
        </button>
      </div>
      <div className="row wrap">
        <span className="muted small num" role="status" aria-label="Выделение">
          выделено: {selected.length}
        </span>
        <button type="button" disabled={!visible.length} onClick={() => setSelected(visible)}>
          Выделить все на странице
        </button>
        <button type="button" disabled={!selected.length} onClick={() => setSelected([])}>
          Снять выделение
        </button>
      </div>
      {visible.length ? (
        <ul className="grid-tiles">
          {visible.map((key) => {
            const c = byKey.get(key);
            if (!c) return null;
            const on = selected.includes(key);
            const bad = clashed.includes(key);
            return (
              <li key={key}>
                <button
                  type="button"
                  className={`grid-tile${on ? ' selected' : ''}${bad ? ' clash' : ''}`}
                  aria-label={`Фрагмент ${clock(c.span[0])}–${clock(c.span[1])}`}
                  aria-pressed={on}
                  title={bad ? 'На площадке в это время' : undefined}
                  onClick={(e) => click(key, e)}
                >
                  <CandidateThumb run={run} index={index} candidate={c} className="tile" />
                  <span className="grid-label">{label(c) || '—'}</span>
                  <span className="muted small num">
                    {clock(c.span[0])}–{clock(c.span[1])}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="muted">Кадров этого класса нет.</p>
      )}
      {clashed.length > 0 && (
        <p className="warning small" role="status" aria-label="Не назначено">
          Не назначено из-за одновременности: {clashed.length}
        </p>
      )}
      {pages > 1 && (
        <div className="row">
          <button type="button" disabled={page === 0} onClick={() => setPage(page - 1)}>
            Назад
          </button>
          <span className="muted small num">
            {page + 1} из {pages}
          </span>
          <button type="button" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>
            Дальше
          </button>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Стили** — в конец `web/src/features/analysis/review.css`:

```css
.grid-brush {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.grid-brush button[aria-pressed="true"] {
  border-color: var(--accent-line);
  background: var(--accent-soft);
}
.grid-tiles {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 8px;
}
.grid-tile {
  display: grid;
  gap: 4px;
  justify-items: center;
  width: 100%;
  padding: 6px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}
.grid-tile.selected {
  border-color: var(--accent-line);
  background: var(--accent-soft);
}
.grid-tile.clash {
  border-color: var(--danger);
  background: var(--danger-soft);
}
.track-thumb.tile,
.thumb-missing.tile {
  width: 100%;
  height: 150px;
  object-fit: contain;
  border-radius: 6px;
  background: var(--surface-2);
}
.grid-label {
  font-size: 13px;
  font-weight: 500;
}
```

- [ ] **Step 5: Тесты проходят**

Run: `cd web && npx vitest run src/features/analysis/IdentityGrid.test.tsx && npx tsc -b`
Expected: PASS, 5 тестов.

- [ ] **Step 6: Commit**

```bash
cd web && npx biome format --write src/features/analysis/IdentityGrid.tsx src/features/analysis/IdentityGrid.test.tsx src/features/analysis/review.css && cd ..
git add web/src/features/analysis/IdentityGrid.tsx web/src/features/analysis/IdentityGrid.test.tsx web/src/features/analysis/review.css
git commit -m "feat(review): identity grid with a class brush and bulk selection"
```

---

### Task 10: режим «Игроки» — участие и исправления

**Files:**
- Create: `web/src/features/analysis/PlayersPanel.tsx`
- Test: `web/src/features/analysis/PlayersPanel.test.tsx`

- [ ] **Step 1: Падающие тесты** — `web/src/features/analysis/PlayersPanel.test.tsx`:

```tsx
import { fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { base, smallRun as run } from './identityFixtures';
import { PlayersPanel } from './PlayersPanel';

const show = (absent: string[] = [], onChange = vi.fn()) => {
  render(<PlayersPanel run={run} assignments={base} absent={absent} disabled={false} onChange={onChange} />);
  return onChange;
};
afterEach(() => vi.restoreAllMocks());

describe('players panel', () => {
  it('returns the fragments of a player who did not take part to the queue', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    const onChange = show();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Участвовал в матче: Север · игрок 1' }));
    expect(window.confirm).toHaveBeenCalledWith('У игрока Север · игрок 1 фрагментов: 1 — вернуть их в очередь?');
    expect(onChange).toHaveBeenCalledWith([{ track_id: 4, player_id: 'p2' }], ['p1']);
  });

  it('keeps everything when the confirmation is declined', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const onChange = show();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Участвовал в матче: Север · игрок 1' }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it('brings a player back without his old fragments', () => {
    const onChange = show(['p2']);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Участвовал в матче: Север · игрок 2' }));
    expect(onChange).toHaveBeenCalledWith(base, []);
  });

  it('removes one fragment of the chosen player', () => {
    const onChange = show();
    fireEvent.click(screen.getByRole('button', { name: '№7 Север · игрок 1' }));
    const own = screen.getByRole('region', { name: 'Фрагменты игрока' });
    fireEvent.click(within(own).getByRole('button', { name: 'Убрать 0:00–0:40' }));
    expect(onChange).toHaveBeenCalledWith([{ track_id: 4, player_id: 'p2' }], []);
  });
});
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd web && npx vitest run src/features/analysis/PlayersPanel.test.tsx`
Expected: FAIL — `Failed to resolve import "./PlayersPanel"`.

- [ ] **Step 3: Компонент** — `web/src/features/analysis/PlayersPanel.tsx`:

```tsx
import { useMemo, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { CandidateThumb } from './CandidateThumb';
import { assignGroup, baseGroups, candidatesOf, clock, decisionOf } from './candidates';
import { lookIndex } from './similar';

type Player = AnalysisRun['context']['rosters'][number];
const shirt = (p: Player) =>
  p.shirt_number && Number.isFinite(Number(p.shirt_number)) ? Number(p.shirt_number) : Number.POSITIVE_INFINITY;

// Игроки матча: участие и исправления. Выключенное участие снимает назначения игрока (фрагменты вернутся в
// очередь) и убирает его из кнопок; протокол матча (ручной учёт) не меняется.
export function PlayersPanel({
  run,
  assignments,
  absent,
  disabled,
  onChange,
}: {
  run: AnalysisRun;
  assignments: AnalysisAssignment[];
  absent: string[];
  disabled: boolean;
  onChange: (assignments: AnalysisAssignment[], absent: string[]) => void;
}) {
  const index = useMemo(() => lookIndex(run), [run]);
  const candidates = useMemo(() => candidatesOf(run, baseGroups(run)), [run]);
  const [chosen, setChosen] = useState<string | null>(null);
  const rows = [...run.context.rosters].sort(
    (a, b) =>
      (a.side === 'home' ? 0 : 1) - (b.side === 'home' ? 0 : 1) ||
      shirt(a) - shirt(b) ||
      a.display_name.localeCompare(b.display_name, 'ru'),
  );
  const ownOf = (id: string) => assignments.filter((a) => a.player_id === id);
  const minutes = (id: string) =>
    ownOf(id).reduce(
      (s, a) => s + (index.tracks.get(a.track_id)?.intervals.reduce((x, [from, to]) => x + to - from, 0) ?? 0),
      0,
    ) / 60;
  const label = (p: Player) => `${p.shirt_number ? `№${p.shirt_number} ` : ''}${p.display_name}`;
  function toggle(p: Player, on: boolean) {
    if (on) {
      onChange(assignments, absent.filter((id) => id !== p.player_id));
      return;
    }
    const own = ownOf(p.player_id);
    if (own.length && !window.confirm(`У игрока ${p.display_name} фрагментов: ${own.length} — вернуть их в очередь?`))
      return;
    onChange(
      assignments.filter((a) => a.player_id !== p.player_id),
      [...absent, p.player_id],
    );
  }
  const player = rows.find((p) => p.player_id === chosen);
  const mine = player
    ? candidates.filter((c) => {
        const d = decisionOf(assignments, c.trackIds);
        return d.kind === 'player' && d.playerId === player.player_id;
      })
    : [];
  return (
    <section className="players-panel" aria-label="Игроки матча">
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Игрок</th>
              <th>Команда</th>
              <th>Фрагментов</th>
              <th>Минут</th>
              <th>Участвовал</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const off = absent.includes(p.player_id);
              return (
                <tr key={p.player_id} className={off ? 'muted' : undefined}>
                  <td>
                    <button type="button" aria-pressed={chosen === p.player_id} onClick={() => setChosen(p.player_id)}>
                      {label(p)}
                    </button>
                  </td>
                  <td>{p.side === 'home' ? run.context.teams.home.name : run.context.teams.away.name}</td>
                  <td className="num">{ownOf(p.player_id).length}</td>
                  <td className="num">{minutes(p.player_id).toFixed(1)}</td>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Участвовал в матче: ${p.display_name}`}
                      checked={!off}
                      disabled={disabled}
                      onChange={(e) => toggle(p, e.target.checked)}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {player && (
        <section aria-label="Фрагменты игрока">
          <h3>
            {label(player)} — фрагментов: {mine.length}
          </h3>
          <ul className="grid-tiles">
            {mine.map((c) => (
              <li key={c.key} className="grid-tile">
                <CandidateThumb run={run} index={index} candidate={c} className="tile" />
                <span className="muted small num">
                  {clock(c.span[0])}–{clock(c.span[1])}
                </span>
                <button
                  type="button"
                  aria-label={`Убрать ${clock(c.span[0])}–${clock(c.span[1])}`}
                  disabled={disabled}
                  onClick={() => onChange(assignGroup(assignments, c.trackIds, ''), absent)}
                >
                  Убрать
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Тесты проходят**

Run: `cd web && npx vitest run src/features/analysis/PlayersPanel.test.tsx && npx tsc -b`
Expected: PASS, 4 теста.

- [ ] **Step 5: Commit**

```bash
cd web && npx biome format --write src/features/analysis/PlayersPanel.tsx src/features/analysis/PlayersPanel.test.tsx && cd ..
git add web/src/features/analysis/PlayersPanel.tsx web/src/features/analysis/PlayersPanel.test.tsx
git commit -m "feat(review): players panel with participation and per-fragment removal"
```

---

### Task 11: вкладка «Проверка» — режимы, участие, автосохранение; удалить старые режимы

**Files:**
- Modify: `web/src/features/analysis/IdentityReview.tsx`
- Delete: `SimilarPicker.tsx`, `SuggestionPicker.tsx`, `SuggestionPicker.test.tsx`, `PlayerCandidates.tsx`,
  `PlayerCandidates.test.tsx`, `suggestions.ts`, `suggestions.test.ts`
- Modify: `web/src/features/analysis/similar.ts` (убрать `suggest`, `assignedShare`, тип `Suggestion`),
  `similar.test.tsx` (убрать их тесты и тесты «Подбора»)
- Test: `web/src/features/analysis/IdentityQueue.test.tsx` (тест вкладки)

- [ ] **Step 1: Падающий тест вкладки** — в конец `IdentityQueue.test.tsx` (два новых импорта — в начало файла):

```tsx
import { MemoryRouter } from 'react-router-dom';
import { IdentityReview } from './IdentityReview';

describe('review tab', () => {
  it('opens the queue by default and saves decisions by itself', async () => {
    vi.useFakeTimers();
    localStorage.clear();
    const save = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <IdentityReview run={{ ...run, assignments: base }} actorId="admin" editable onSave={save} />
      </MemoryRouter>,
    );
    expect(screen.getByRole('button', { name: 'Очередь' })).toHaveAttribute('aria-pressed', 'true');
    fireEvent.keyDown(window, { key: '2' });
    expect(save).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2100);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0].assignments).toContainEqual({ track_id: 3, player_id: 'p2' });
    expect(save.mock.calls[0][0].absent_players).toEqual([]);
    vi.useRealTimers();
  });

  it('keeps who did not take part in the draft', () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    localStorage.clear();
    render(
      <MemoryRouter>
        <IdentityReview run={{ ...run, assignments: base }} actorId="admin" editable onSave={vi.fn()} />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Игроки' }));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Участвовал в матче: Север · игрок 1' }));
    fireEvent.click(screen.getByRole('button', { name: 'Очередь' }));
    expect(screen.queryByRole('button', { name: /№7 Север · игрок 1/ })).toBeNull();
    vi.restoreAllMocks();
  });
});
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd web && npx vitest run src/features/analysis/IdentityQueue.test.tsx -t "review tab"`
Expected: FAIL — нет кнопки «Очередь».

- [ ] **Step 3: Импорты и тип разметки.** В `IdentityReview.tsx` заменить строки импорта с `useEffect` по
  `hintsFor` и тип `Review` на:

```tsx
import { useEffect, useRef, useState } from 'react';
import type { AnalysisAssignment, AnalysisRun } from '../../api/domain';
import { downloadJson, ErrorBox } from '../../components/ui';
import { useDraft } from '../protocol/drafts';
import { dropConflicts, identityConflicts } from './candidates';
import { IdentityGrid } from './IdentityGrid';
import { IdentityQueue } from './IdentityQueue';
import { identityFingerprint } from './identityBase';
import { PlayersPanel } from './PlayersPanel';
import { filteredCount, TRACK_FILTERS, type TrackFilter, trackState, visibleTrackIds } from './reviewQueue';
import type { IdentitySuggestion } from './understandingTypes';
import './review.css';

// Решение сохраняется само через 2 с после последнего изменения; null — без автосохранения.
const AUTOSAVE_MS = 2000;
type Review = { side_map: AnalysisRun['side_map']; assignments: AnalysisAssignment[]; absent_players?: string[] };
```

В `valid` перед закрывающей `)` выражения `return (` добавить условие:

```tsx
    &&
    (r.absent_players === undefined ||
      (Array.isArray(r.absent_players) && r.absent_players.every((x) => typeof x === 'string')))
```

(если Biome переставит `&&` в начало строки — оставить, как отформатирует).

- [ ] **Step 4: Пропсы, сервер, режим.** В сигнатуре компонента добавить проп `autosaveMs = AUTOSAVE_MS` (тип
  `autosaveMs?: number | null`). Заменить строку `const server = ...` на

```tsx
  const server = { side_map: run.side_map, assignments: run.assignments, absent_players: run.absent_players ?? [] };
```

Заменить объявление режима и весь блок подсчёта подсказок (от `const [mode, setMode]` до закрывающей `);` у
`hintCount`) на:

```tsx
  // Есть признаки цвета — очередь; старые версии без признаков открываются по фрагментам, как раньше.
  const [mode, setMode] = useState<'queue' | 'grid' | 'players' | 'tracks'>(looks ? 'queue' : 'tracks');
```

- [ ] **Step 5: Сохранение и автосохранение.** Заменить функцию `save` на:

```tsx
  // Сохраняется весь черновик, включая строки вне текущего фильтра и страницы. Одна запись за раз: кнопка и
  // автосохранение не отправляют одну ревизию дважды.
  const saving = useRef(false);
  async function save() {
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setError(undefined);
    try {
      await onSave(draft.value);
      draft.markSaved(draft.value);
      onDirty?.(false);
    } catch (e) {
      setError(e);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }
  const saveRef = useRef(save);
  saveRef.current = save;
```

и сразу после — эффект автосохранения (после объявления `stale` и `error`, они уже выше):

```tsx
  useEffect(() => {
    if (autosaveMs == null || !editable || !draft.dirty || draft.corrupt || stale || error) return;
    const timer = setTimeout(() => void saveRef.current(), autosaveMs);
    return () => clearTimeout(timer);
  }, [autosaveMs, editable, draft.dirty, draft.corrupt, draft.value, stale, error]);
```

Ниже, после `const assignments = draft.value.assignments;`, добавить:

```tsx
  const absent = draft.value.absent_players ?? [];
  const setAssignments = (next: AnalysisAssignment[]) => change({ ...draft.value, assignments: next });
```

- [ ] **Step 6: Кнопки режимов.** Заменить содержимое `<div className="segmented review-mode" role="group"
  aria-label="Сопоставлять">` на:

```tsx
          <button type="button" aria-pressed={mode === 'queue'} onClick={() => setMode('queue')}>
            Очередь
          </button>
          <button type="button" aria-pressed={mode === 'grid'} onClick={() => setMode('grid')}>
            Сетка
          </button>
          <button type="button" aria-pressed={mode === 'players'} onClick={() => setMode('players')}>
            Игроки
          </button>
          <button type="button" aria-pressed={mode === 'tracks'} onClick={() => setMode('tracks')}>
            По фрагментам · {run.tracks.length}
          </button>
```

- [ ] **Step 7: Ветки отрисовки.** Заменить ветки от `{mode === 'similar' ? (` до начала ветки по фрагментам
  (последнее `) : (` перед `<div className={\`review-panes...`) на:

```tsx
      {mode === 'queue' ? (
        <IdentityQueue
          run={run}
          assignments={assignments}
          sideMap={draft.value.side_map}
          absent={absent}
          disabled={disabled}
          onChange={setAssignments}
        />
      ) : mode === 'grid' ? (
        <IdentityGrid
          run={run}
          assignments={assignments}
          sideMap={draft.value.side_map}
          absent={absent}
          disabled={disabled}
          onChange={setAssignments}
        />
      ) : mode === 'players' ? (
        <PlayersPanel
          run={run}
          assignments={assignments}
          absent={absent}
          disabled={disabled}
          onChange={(next, nextAbsent) => change({ ...draft.value, assignments: next, absent_players: nextAbsent })}
        />
      ) : (
```

Если после этого `sidesChanged` или `suggestions` больше нигде не используются — оставить: `suggestions`
по-прежнему нужен ветке «По фрагментам» (подсказка номера), `sidesChanged` — ей же.

- [ ] **Step 8: Статус сохранения.** В строке над «Сохранить сопоставление» (`<p ...>Черновик сопоставления
  сохранён в этом браузере…`) текст оставить, а в ряд кнопок перед «Сохранить сопоставление» добавить статус:

```tsx
          <span className="muted small" role="status" aria-label="Сохранение">
            {busy ? 'сохраняется…' : draft.dirty ? 'изменения сохранятся сами' : 'сохранено'}
          </span>
```

- [ ] **Step 9: Удалить старые режимы**

```bash
git rm web/src/features/analysis/SimilarPicker.tsx web/src/features/analysis/SuggestionPicker.tsx web/src/features/analysis/SuggestionPicker.test.tsx web/src/features/analysis/PlayerCandidates.tsx web/src/features/analysis/PlayerCandidates.test.tsx web/src/features/analysis/suggestions.ts web/src/features/analysis/suggestions.test.ts
```

В `similar.ts` удалить тип `Suggestion`, функции `suggest` и `assignedShare` и ставшие лишними импорты
(`AnalysisAssignment`, `decisionOf`). В `similar.test.tsx` удалить тесты `starts with the longest open fragments…`,
`counts the share of team time…`, `adds marked fragments to the chosen player…` и блок `describe('marking all
suggestions at once', …)`, из импортов — `assignedShare`, `suggest`, константу `keys`; тесты `decodes the package
appearance…` и блок `simultaneous fragments of one player` оставить.

- [ ] **Step 10: Тесты анализа**

Run: `cd web && npx vitest run src/features/analysis && npx tsc -b && npm run lint`
Expected: PASS; `tsc` и Biome без ошибок. Если тест, рассчитанный на ручное сохранение, ловит лишний вызов
`onSave` от автосохранения, — передать в нём `autosaveMs={null}` в `IdentityReview`; ожидания теста не менять.

- [ ] **Step 11: Commit**

```bash
cd web && npx biome format --write src/features/analysis/IdentityReview.tsx src/features/analysis/IdentityQueue.test.tsx src/features/analysis/similar.ts src/features/analysis/similar.test.tsx && cd ..
git add -A web/src/features/analysis
git commit -m "feat(review): queue, grid and players modes with autosave replace the pickers"
```

---

### Task 12: разметка — только в самой новой версии матча

**Files:**
- Modify: `web/src/features/analysis/AnalysisTab.tsx` (`VideoAnalysisTab`, `RunContent`)
- Test: `web/src/features/analysis/analysis.test.tsx`

- [ ] **Step 1: Падающий тест** — в конец `analysis.test.tsx`:

```tsx
it('labels players only in the newest version of the match', async () => {
  const older = { ...run, id: 'old', created_at: '2026-10-12T10:00:00Z' };
  const newer = { ...run, id: 'new', created_at: '2026-10-13T10:00:00Z' };
  const overview = {
    match_id: 'match',
    analysis_revision: 0,
    active_run_id: null,
    published_run_id: null,
    jobs: [],
    runs: [newer, older],
  };
  vi.mocked(api).mockImplementation(async (path) => {
    const p = String(path);
    if (p.endsWith('/team-review-tasks')) return { items: [], total: 0 };
    if (p.endsWith('/team-confirmations')) return { workflow: 'admin', sides: [] };
    if (p.endsWith('/runs/old')) return older;
    if (p.endsWith('/runs/new')) return newer;
    return overview;
  });
  const update = vi.fn();
  render(
    <MemoryRouter>
      <VideoAnalysisTab
        matchId="match"
        actorId="actor"
        canManage
        nav={{ params: new URLSearchParams('run_id=old'), update }}
      />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole('button', { name: 'Перейти к разметке' }));
  expect(update).toHaveBeenCalledWith(expect.objectContaining({ run_id: 'new' }));
});
```

- [ ] **Step 2: Убедиться, что падает**

Run: `cd web && npx vitest run src/features/analysis/analysis.test.tsx -t "newest version"`
Expected: FAIL — нет кнопки «Перейти к разметке».

- [ ] **Step 3: Самая новая версия по умолчанию.** В `VideoAnalysisTab` заменить строки `const reviewRun = …` и
  `const selectedId = …` на:

```tsx
  // Одна разметка на матч: она в самой новой версии, её Админ+ и открывает по умолчанию.
  const newestId = [...(state.data?.runs ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))[0]?.id;
  const selectedId =
    (known ? selected : undefined) ??
    (canManage ? newestId : undefined) ??
    state.data?.active_run_id ??
    state.data?.runs[0]?.id;
```

и в `<RunContent …>` добавить пропсы `newestId={newestId}` и `onSelect={setSelected}`.

- [ ] **Step 4: Баннер и продолжение разметки.** В сигнатуре `RunContent` добавить пропсы
  `newestId?: string; onSelect: (id: string) => void;`. Перед `{task === 'identity' && (<IdentityReview` вставить:

```tsx
      {task === 'identity' && canManage && newestId && run.id !== newestId && (
        <p className="warning row wrap" role="status" aria-label="Разметка в новой версии">
          Разметка игроков ведётся в самой новой версии матча.
          <button type="button" onClick={() => onSelect(newestId)}>
            Перейти к разметке
          </button>
        </p>
      )}
      {task === 'identity' && canManage && run.id === newestId && run.status === 'confirmed' && (
        <p className="row wrap" role="status" aria-label="Продолжить разметку">
          Версия подтверждена: изменения пойдут в новую проверку с копией всех решений.
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void change('reviews')
                .then((r) => onSelect(r.id))
                .catch(() => {})
            }
          >
            Продолжить разметку
          </button>
        </p>
      )}
```

и в пропсе `editable` у `IdentityReview` добавить условие `&& run.id === newestId`:

```tsx
          editable={canManage && run.status === 'review' && run.id === newestId && !busy && !episodeDirty}
```

- [ ] **Step 5: Тесты проходят**

Run: `cd web && npx vitest run src/features/analysis && npx tsc -b`
Expected: PASS. Если тест вкладки ждал, что по умолчанию откроется первая версия «на проверке», а в его данных она
не самая новая, — поправить даты `created_at` в данных теста так, чтобы нужная версия была самой новой.

- [ ] **Step 6: Commit**

```bash
cd web && npx biome format --write src/features/analysis/AnalysisTab.tsx src/features/analysis/analysis.test.tsx && cd ..
git add web/src/features/analysis/AnalysisTab.tsx web/src/features/analysis/analysis.test.tsx
git commit -m "feat(review): labelling opens in the newest version of the match"
```

---

### Task 13: признак SigLIP 2 фрагмента в пакете

**Files:**
- Modify: `src/aifootball/perception/appearance.py` (кодирование признака, загрузка весов без скачивания)
- Modify: `src/aifootball/processor/job.py` (`appearance`, `package_result`)
- Modify: `src/aifootball/analytics/exchange.py` (проверка поля)
- Modify: `src/aifootball/service/analysis/schemas.py` (`TrackView`), `web/src/api/types.ts` (генерация)
- Test: `tests/test_appearance.py`, `tests/test_analysis_exchange.py`, `tests/test_processor_job.py`

- [ ] **Step 1: Падающие тесты.** В конец `tests/test_appearance.py`:

```python
def test_siglip_embedding_survives_the_package_encoding():
    from aifootball.perception.appearance import EMBEDDING_DIMS, decode_embedding, encode_embedding

    rng = np.random.default_rng(0)
    v = rng.normal(size=EMBEDDING_DIMS)
    v /= np.linalg.norm(v)
    back = decode_embedding(encode_embedding(v))
    assert back.shape == (EMBEDDING_DIMS,)
    assert float(back @ v) > 0.999


def test_siglip_weights_are_never_downloaded(tmp_path):
    from aifootball.perception.appearance import siglip_embedder

    assert siglip_embedder(None) is None
    assert siglip_embedder(tmp_path) is None  # в tmp_path/hf весов нет
```

В конец `tests/test_analysis_exchange.py`:

```python
@pytest.mark.parametrize(
    'value,ok',
    [
        (base64.b64encode(bytes(768)).decode(), True),
        (base64.b64encode(bytes(767)).decode(), False),
        ('не base64', False),
    ],
)
def test_fragment_embedding_is_768_bytes_of_base64(tmp_path, value, ok):
    from aifootball.analytics.exchange import ExchangeError, validate_result

    def mutate(m, r, t, c):
        t['tracks'][0]['embedding'] = value

    path = tmp_path / 'result.zip'
    path.write_bytes(result_zip(mutate=mutate))
    if ok:
        assert validate_result(path).tracks['tracks'][0]['embedding'] == value
    else:
        with pytest.raises(ExchangeError, match='признак SigLIP'):
            validate_result(path)


def test_embedding_size_matches_the_feature():
    from aifootball.analytics.exchange import EMBEDDING_BYTES
    from aifootball.perception.appearance import EMBEDDING_DIMS

    assert EMBEDDING_BYTES == EMBEDDING_DIMS
```

В конец `tests/test_processor_job.py`:

```python
def _fake_crops(monkeypatch):
    import numpy as np

    crop = np.full((64, 32, 3), (0, 0, 200), np.uint8)
    monkeypatch.setattr('aifootball.perception.person_crops.pick_frames', lambda *a, **k: {1: []})
    monkeypatch.setattr('aifootball.perception.person_crops.extract_crops', lambda video, picks: {1: [crop, crop]})
    monkeypatch.setattr('aifootball.cli.read_registration', lambda *a: None)


def test_fragment_gets_a_siglip_embedding_when_weights_exist(monkeypatch, tmp_path):
    from types import SimpleNamespace

    import numpy as np

    from aifootball.perception.appearance import EMBEDDING_DIMS, decode_embedding
    from aifootball.processor.job import appearance

    _fake_crops(monkeypatch)
    unit = np.eye(EMBEDDING_DIMS)[0]
    monkeypatch.setattr(
        'aifootball.perception.appearance.siglip_embedder', lambda models: lambda images: [unit for _ in images]
    )
    looks, warning = appearance(
        tmp_path / 'v.mp4', pl.DataFrame({'track_id': [1]}), SimpleNamespace(overlay=None), tmp_path, {1}, (100, 100),
        models=tmp_path,
    )
    assert warning is None
    colour, embedding = looks[1]
    assert colour and decode_embedding(embedding)[0] > 0.999


def test_without_weights_the_package_says_so_and_has_no_embedding(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from aifootball.processor.job import appearance

    _fake_crops(monkeypatch)
    looks, warning = appearance(
        tmp_path / 'v.mp4', pl.DataFrame({'track_id': [1]}), SimpleNamespace(overlay=None), tmp_path, {1}, (100, 100),
        models=tmp_path,
    )
    assert looks[1][1] is None
    assert 'SigLIP' in warning
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/bin/python -m pytest tests/test_appearance.py tests/test_analysis_exchange.py tests/test_processor_job.py -q -k "siglip or embedding"`
Expected: FAIL — `ImportError: cannot import name 'EMBEDDING_DIMS'`.

- [ ] **Step 3: Кодирование и веса.** В `perception/appearance.py` после `INPUT = (112, 224)`:

```python
# Признак SigLIP 2 фрагмента в пакете (поле embedding): нормированный вектор, по байту со знаком на число, base64.
# По нему кабинет обучает модель матча (docs/superpowers/specs/2026-11-26-identity-queue-design.md).
EMBEDDING_KIND = 'siglip2-b16-int8-v1'
EMBEDDING_DIMS = 768
```

и в конец файла:

```python
def encode_embedding(feature: np.ndarray) -> str:
    import base64

    q = np.clip(np.rint(np.asarray(feature, np.float64) * 127), -127, 127).astype(np.int8)
    return base64.b64encode(q.tobytes()).decode('ascii')


def decode_embedding(text: str) -> np.ndarray:
    import base64

    v = np.frombuffer(base64.b64decode(text, validate=True), np.int8).astype(np.float64) / 127
    return v / max(float(np.linalg.norm(v)), 1e-9)


def siglip_embedder(models: Path | None):
    """SigLIP 2 из models/hf без скачивания (HF_HUB_OFFLINE); весов нет — None."""
    if models is None:
        return None
    cache = Path(models) / 'hf'
    if not (cache / f'models--timm--{ENCODERS["siglip"]}').exists():
        return None
    import os

    os.environ.setdefault('HF_HUB_OFFLINE', '1')
    return TimmEmbedder('siglip', cache)
```

- [ ] **Step 4: Обработчик.** В `processor/job.py` заменить функцию `appearance` целиком:

```python
def appearance(video_path, tracks, venue, artifacts, track_ids, frame_size, models=None):
    """Признаки фрагментов для разметки в кабинете: {трек: (цвет base64, SigLIP 2 base64 или None)} и предупреждение.

    Цвет упорядочивает подсказки похожих фрагментов; SigLIP 2 нужен модели матча кабинета. Сборка людей по
    внешности без человека проверку не проходит (docs/2026-11-23-people-clustering.md) — решает человек.
    """
    import polars as pl

    from aifootball.analytics.people import mean_feature
    from aifootball.cli import read_registration
    from aifootball.geometry.registration import frame_homographies
    from aifootball.perception import appearance as features
    from aifootball.perception import person_crops

    registration = read_registration(Path(artifacts), venue)
    usable = set(frame_homographies(registration)) if registration is not None else None
    picks = person_crops.pick_frames(
        tracks.filter(pl.col('track_id').is_in(sorted(track_ids))), frame_size, usable, venue.overlay
    )
    embed = features.siglip_embedder(models)
    out = {}
    for tid, images in person_crops.extract_crops(Path(video_path), picks).items():
        colour = mean_feature([features.color_feature(i) for i in images])
        if colour is None:
            continue
        vector = mean_feature(embed(images)) if embed else None
        out[tid] = (features.encode(colour), features.encode_embedding(vector) if vector is not None else None)
    warning = None
    if models is not None and embed is None and out:
        warning = 'Признак SigLIP фрагментов не рассчитан: нет весов в models/hf — модель матча в кабинете недоступна'
    return out, warning
```

В `package_result` заменить блок `looks = appearance(...)` / `for track in indexed: ...` на:

```python
    looks, look_warning = appearance(
        video_path, tracks, venue, artifacts, playable, (source['width'], source['height']), models
    )
    for track in indexed:
        if track['track_id'] in looks:
            colour, embedding = looks[track['track_id']]
            track['appearance'] = colour
            if embedding:
                track['embedding'] = embedding
```

и в сборке `warnings = (...)` добавить строку `+ ([look_warning] if look_warning else [])` после
`+ ([events_warning] if events_warning else [])`.

- [ ] **Step 5: Проверка обмена.** В `analytics/exchange.py` после `APPEARANCE_BYTES = 156`:

```python
# Байт в признаке SigLIP 2 фрагмента: perception.appearance.EMBEDDING_DIMS.
EMBEDDING_BYTES = 768
```

после функции `appearance_ok`:

```python
def embedding_ok(value) -> bool:
    """Признак SigLIP 2 фрагмента (perception.appearance): EMBEDDING_BYTES байт в base64; поле необязательное."""
    if value is None:
        return True
    import base64
    import binascii

    try:
        return isinstance(value, str) and len(base64.b64decode(value, validate=True)) == EMBEDDING_BYTES
    except (binascii.Error, ValueError):
        return False
```

и после `ensure(appearance_ok(...), 'Неверный признак внешности фрагмента')`:

```python
            ensure(embedding_ok(track.get('embedding')), 'Неверный признак SigLIP фрагмента')
```

- [ ] **Step 6: Вид версии.** В `service/analysis/schemas.py`, `TrackView`, после `appearance: str | None = None`:

```python
    # Признак SigLIP 2 для модели матча (base64, analytics.exchange.EMBEDDING_BYTES байт); у старых пакетов — нет.
    embedding: str | None = None
```

- [ ] **Step 7: Тесты проходят, типы кабинета**

Run: `.venv/bin/python -m pytest tests/test_appearance.py tests/test_analysis_exchange.py tests/test_processor_job.py tests/test_processor_resume.py tests/test_processor_ptz.py -q`
Expected: PASS. Затем:

```bash
.venv/bin/python scripts/export_service_openapi.py --output data/service/openapi.json
npm --prefix web run types:api
grep -n "embedding" web/src/api/types.ts
```

- [ ] **Step 8: Commit**

```bash
.venv/bin/ruff format src/aifootball/perception/appearance.py src/aifootball/processor/job.py src/aifootball/analytics/exchange.py src/aifootball/service/analysis/schemas.py tests/test_appearance.py tests/test_analysis_exchange.py tests/test_processor_job.py
.venv/bin/ruff check src tests
git add src/aifootball/perception/appearance.py src/aifootball/processor/job.py src/aifootball/analytics/exchange.py src/aifootball/service/analysis/schemas.py tests/test_appearance.py tests/test_analysis_exchange.py tests/test_processor_job.py web/src/api/types.ts
git commit -m "feat(processor): SigLIP 2 embedding of each fragment in the package"
```

---

### Task 14: модель матча в кабинете

**Files:**
- Modify: `web/src/features/analysis/similar.ts` (`decodeEmbedding`, `embeds` в `lookIndex`, `meanEmbed`)
- Create: `web/src/features/analysis/matchModel.ts`
- Test: `web/src/features/analysis/matchModel.test.ts`

- [ ] **Step 1: Падающие тесты** — `web/src/features/analysis/matchModel.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { MODEL_CONFIDENCE, predict, probabilityOf, trainModel } from './matchModel';
import { decodeEmbedding } from './similar';

// Два игрока с одинаковым цветом и разным признаком SigLIP: модель матча должна их различать.
const sample = (hot: number, noise: number) => {
  const x = new Float64Array(10);
  x[hot] = 1;
  x[9] = 0.5; // «цвет» одинаковый
  x[(hot + 3) % 8] += noise;
  return x;
};
const samples = Array.from({ length: 40 }, (_, i) => ({
  x: sample(i % 2 ? 1 : 2, (i % 5) * 0.05),
  y: i % 2 ? 'p1' : 'p2',
}));

describe('match model', () => {
  it('tells apart players of the same colour and is confident', () => {
    const model = trainModel(samples);
    expect(model?.classes).toEqual(['p1', 'p2']);
    const r = model ? predict(model, sample(1, 0.02), ['p1', 'p2']) : null;
    expect(r?.playerId).toBe('p1');
    expect(r?.p).toBeGreaterThanOrEqual(MODEL_CONFIDENCE);
  });

  it('chooses only among available players', () => {
    const model = trainModel(samples);
    const r = model ? predict(model, sample(1, 0.02), ['p2']) : null;
    expect(r).toEqual({ playerId: 'p2', p: 1 });
    expect(model ? predict(model, sample(1, 0), []) : 'none').toBeNull();
  });

  it('needs at least two players and keeps learning from the previous weights', () => {
    expect(trainModel(samples.filter((s) => s.y === 'p1'))).toBeNull();
    const first = trainModel(samples);
    const again = trainModel(samples, first);
    expect(again && probabilityOf(again, sample(2, 0.02), 'p2')).toBeGreaterThan(0.9);
  });

  it('decodes a package embedding to a unit vector', () => {
    const bytes = Array.from({ length: 768 }, (_, i) => (i === 3 ? 127 : i === 4 ? 129 : 0)); // 129 = −127
    const v = decodeEmbedding(btoa(String.fromCharCode(...bytes)));
    expect(v[3]).toBeCloseTo(Math.SQRT1_2, 6);
    expect(v[4]).toBeCloseTo(-Math.SQRT1_2, 6);
  });
});
```

- [ ] **Step 2: Убедиться, что падают**

Run: `cd web && npx vitest run src/features/analysis/matchModel.test.ts`
Expected: FAIL — `Failed to resolve import "./matchModel"`.

- [ ] **Step 3: Признак в индексе.** В `similar.ts` после `decodeLook` добавить:

```ts
// Признак SigLIP 2 из пакета: 768 байт со знаком (−127…127) в base64, обратно в нормированный вектор.
export function decodeEmbedding(text: string): Look {
  const bin = atob(text);
  const v = new Float64Array(bin.length);
  let norm = 0;
  for (let i = 0; i < bin.length; i++) {
    const b = bin.charCodeAt(i);
    v[i] = (b > 127 ? b - 256 : b) / 127;
    norm += v[i] * v[i];
  }
  norm = Math.sqrt(norm) || 1;
  return v.map((x) => x / norm);
}
```

`lookIndex` заменить на:

```ts
export function lookIndex(run: AnalysisRun) {
  const tracks = new Map(run.tracks.map((t) => [t.track_id, t]));
  const looks = new Map<number, Look>();
  const embeds = new Map<number, Look>();
  for (const t of run.tracks) {
    if (t.appearance) looks.set(t.track_id, decodeLook(t.appearance));
    if (t.embedding) embeds.set(t.track_id, decodeEmbedding(t.embedding));
  }
  return { tracks, looks, embeds };
}
```

а `meanLook` — на общую функцию и две обёртки:

```ts
// Средний признак фрагментов с весом по времени на площадке; без признаков — null.
function meanOf(index: LookIndex, ids: number[], source: Map<number, Look>): Look | null {
  let out: Look | null = null;
  let total = 0;
  for (const id of ids) {
    const v = source.get(id);
    const t = index.tracks.get(id);
    if (!v || !t) continue;
    const w = seconds(t);
    if (!out) out = new Float64Array(v.length);
    for (let i = 0; i < v.length; i++) out[i] += v[i] * w;
    total += w;
  }
  if (!out || total <= 0) return null;
  const norm = Math.sqrt(cosine(out, out)) || 1;
  return out.map((x) => x / norm);
}
export const meanLook = (index: LookIndex, ids: number[]) => meanOf(index, ids, index.looks);
export const meanEmbed = (index: LookIndex, ids: number[]) => meanOf(index, ids, index.embeds);
```

- [ ] **Step 4: Модель** — `web/src/features/analysis/matchModel.ts`:

```ts
import type { AnalysisAssignment } from '../../api/domain';
import { type Candidate, decisionOf } from './candidates';
import { type LookIndex, meanEmbed, meanLook } from './similar';

// Модель матча: многоклассовая логистическая регрессия на признаке SigLIP 2 и цвете фрагмента по решениям этого
// матча (стандартизация, L2 с C = 1, Adam). Замер ВШЭ Ю — JWH: при вероятности ≥ 0,9 уверенных 72–84% фрагментов
// при точности 94–96%, у цвета — 21–28% (docs/superpowers/specs/2026-11-26-identity-queue-design.md).
export const MODEL_CONFIDENCE = 0.9;
const C = 1;
const STEPS = 200;
const WARM_STEPS = 60;
const RATE = 0.05;

export type MatchModel = { classes: string[]; w: Float64Array[]; b: Float64Array; mu: Float64Array; sd: Float64Array };
export type Sample = { x: Float64Array; y: string };

// Признак кандидата: средние SigLIP 2 и цвет его фрагментов; без любого из них — null.
export function candidateFeature(index: LookIndex, candidate: Candidate): Float64Array | null {
  const e = meanEmbed(index, candidate.trackIds);
  const l = meanLook(index, candidate.trackIds);
  if (!e || !l) return null;
  const x = new Float64Array(e.length + l.length);
  x.set(e);
  x.set(l, e.length);
  return x;
}

// Примеры для обучения: кандидаты команды с решением «игрок» среди данных игроков.
export function modelSamples(
  index: LookIndex,
  candidates: Candidate[],
  team: 'A' | 'B',
  playerIds: string[],
  assignments: AnalysisAssignment[],
): Sample[] {
  return candidates.flatMap((c) => {
    if (c.team !== team) return [];
    const d = decisionOf(assignments, c.trackIds);
    const x = d.kind === 'player' && d.playerId && playerIds.includes(d.playerId) ? candidateFeature(index, c) : null;
    return x && d.playerId ? [{ x, y: d.playerId }] : [];
  });
}

function softmax(model: Pick<MatchModel, 'w' | 'b'>, z: Float64Array): Float64Array {
  const logits = model.w.map((row, c) => {
    let s = model.b[c];
    for (let j = 0; j < z.length; j++) s += row[j] * z[j];
    return s;
  });
  const top = Math.max(...logits);
  const e = logits.map((v) => Math.exp(v - top));
  const sum = e.reduce((a, v) => a + v, 0);
  return Float64Array.from(e.map((v) => v / sum));
}

const standardize = (model: MatchModel, x: Float64Array) => x.map((v, j) => (v - model.mu[j]) / model.sd[j]);

// Обучение; prev с теми же игроками — тёплый старт (меньше шагов). Меньше двух игроков — модели нет.
export function trainModel(samples: Sample[], prev?: MatchModel | null): MatchModel | null {
  const classes = [...new Set(samples.map((s) => s.y))].sort();
  if (classes.length < 2) return null;
  const n = samples.length;
  const d = samples[0].x.length;
  const k = classes.length;
  const mu = new Float64Array(d);
  const sd = new Float64Array(d);
  for (const s of samples) for (let j = 0; j < d; j++) mu[j] += s.x[j] / n;
  for (const s of samples) for (let j = 0; j < d; j++) sd[j] += (s.x[j] - mu[j]) ** 2 / n;
  for (let j = 0; j < d; j++) sd[j] = sd[j] > 1e-12 ? Math.sqrt(sd[j]) : 1;
  const X = samples.map((s) => s.x.map((v, j) => (v - mu[j]) / sd[j]));
  const y = samples.map((s) => classes.indexOf(s.y));
  const warm = !!prev && prev.classes.join('|') === classes.join('|') && prev.w[0]?.length === d;
  const w = warm && prev ? prev.w.map((r) => Float64Array.from(r)) : classes.map(() => new Float64Array(d));
  const b = warm && prev ? Float64Array.from(prev.b) : new Float64Array(k);
  const mW = classes.map(() => new Float64Array(d));
  const vW = classes.map(() => new Float64Array(d));
  const mB = new Float64Array(k);
  const vB = new Float64Array(k);
  const lambda = 1 / (C * n);
  const steps = warm ? WARM_STEPS : STEPS;
  for (let step = 1; step <= steps; step++) {
    const gW = classes.map(() => new Float64Array(d));
    const gB = new Float64Array(k);
    for (let i = 0; i < n; i++) {
      const p = softmax({ w, b }, X[i]);
      for (let c = 0; c < k; c++) {
        const g = (p[c] - (y[i] === c ? 1 : 0)) / n;
        gB[c] += g;
        const row = gW[c];
        const xi = X[i];
        for (let j = 0; j < d; j++) row[j] += g * xi[j];
      }
    }
    const c1 = 1 - 0.9 ** step;
    const c2 = 1 - 0.999 ** step;
    for (let c = 0; c < k; c++) {
      for (let j = 0; j < d; j++) {
        const g = gW[c][j] + lambda * w[c][j];
        mW[c][j] = 0.9 * mW[c][j] + 0.1 * g;
        vW[c][j] = 0.999 * vW[c][j] + 0.001 * g * g;
        w[c][j] -= (RATE * (mW[c][j] / c1)) / (Math.sqrt(vW[c][j] / c2) + 1e-8);
      }
      mB[c] = 0.9 * mB[c] + 0.1 * gB[c];
      vB[c] = 0.999 * vB[c] + 0.001 * gB[c] * gB[c];
      b[c] -= (RATE * (mB[c] / c1)) / (Math.sqrt(vB[c] / c2) + 1e-8);
    }
  }
  return { classes, w, b, mu, sd };
}

// Лучший из доступных игроков и его вероятность, нормированная по доступным; никого нет — null.
export function predict(model: MatchModel, x: Float64Array, allowed: string[]): { playerId: string; p: number } | null {
  const p = softmax(model, standardize(model, x));
  const keep = model.classes.flatMap((c, i) => (allowed.includes(c) ? [i] : []));
  if (!keep.length) return null;
  const total = keep.reduce((s, i) => s + p[i], 0) || 1;
  const best = keep.reduce((a, i) => (p[i] > p[a] ? i : a), keep[0]);
  return { playerId: model.classes[best], p: p[best] / total };
}

// Вероятность одного игрока среди всех игроков модели (порядок «Похожие на …» в сетке).
export function probabilityOf(model: MatchModel, x: Float64Array, playerId: string): number {
  const i = model.classes.indexOf(playerId);
  return i < 0 ? 0 : softmax(model, standardize(model, x))[i];
}
```

- [ ] **Step 5: Тесты проходят**

Run: `cd web && npx vitest run src/features/analysis/matchModel.test.ts src/features/analysis && npx tsc -b`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd web && npx biome format --write src/features/analysis/similar.ts src/features/analysis/matchModel.ts src/features/analysis/matchModel.test.ts && cd ..
git add web/src/features/analysis/similar.ts web/src/features/analysis/matchModel.ts web/src/features/analysis/matchModel.test.ts
git commit -m "feat(review): a match model trained in the browser on this match's decisions"
```

---

### Task 15: подсветка и «Похожие на» по модели матча

**Files:**
- Create: `web/src/features/analysis/useMatchModel.ts`
- Modify: `web/src/features/analysis/queue.ts` (`confidentHint`), `grid.ts` (`gridOrder`),
  `IdentityQueue.tsx`, `IdentityGrid.tsx`, `identityFixtures.ts`
- Test: `web/src/features/analysis/queue.test.ts`, `grid.test.ts`

- [ ] **Step 1: Признаки SigLIP в данных тестов.** В `identityFixtures.ts` после `const BLUE = …` добавить

```ts
// Признак SigLIP 2 из пакета: 768 байт со знаком, 127 в одной позиции.
const emb = (hot: number) => btoa(String.fromCharCode(...Array.from({ length: 768 }, (_, i) => (i === hot ? 127 : 0))));
```

и в `wideRun` дописать признаки фрагментам (p1 и 2, 9, 10 — «первый», p3 и 8 — «второй», синие — «третий»):

```ts
export const wideRun = {
  ...smallRun,
  context: { teams, rosters: [p1, p2, p3, p9] },
  tracks: [...tracks, track(8, 'A', 300, 340, RED), track(9, 'A', 400, 440, RED), track(10, 'A', 410, 450, RED)].map(
    (t) => ({ ...t, embedding: { 1: emb(1), 2: emb(1), 8: emb(2), 9: emb(1), 10: emb(1), 3: emb(3), 4: emb(3), 5: emb(3) }[t.track_id] ?? null }),
  ),
} as unknown as AnalysisRun;
```

- [ ] **Step 2: Падающие тесты.** В `queue.test.ts` (импорты `MatchModel` из `./matchModel` — в начало файла):

```ts
import type { MatchModel } from './matchModel';

// Модель, которая узнаёт игрока по «своей» позиции признака SigLIP (первые 768 чисел признака кандидата).
const crafted = (classes: string[], hot: number[]): MatchModel => ({
  classes,
  w: hot.map((h) => Float64Array.from({ length: 768 + 156 }, (_, j) => (j === h ? 40 : 0))),
  b: new Float64Array(classes.length),
  mu: new Float64Array(768 + 156),
  sd: new Float64Array(768 + 156).fill(1),
});

describe('queue with a match model', () => {
  it('tells apart players of the same colour by the model', () => {
    const twins = [...base, { track_id: 8, player_id: 'p3' }];
    const players = queuePlayers(index, rosters, 'home', [], twins);
    expect(confidentHint(index, players, cand('2'))).toBeNull();
    expect(confidentHint(index, players, cand('2'), crafted(['p1', 'p3'], [1, 2]))).toBe('p1');
  });

  it('falls back to colour for a candidate without an embedding', () => {
    const players = queuePlayers(index, rosters, 'home', [], base);
    expect(confidentHint(index, players, cand('6'), crafted(['p1', 'p2'], [1, 3]))).toBeNull();
  });
});
```

В `grid.test.ts`:

```ts
import type { MatchModel } from './matchModel';

it('orders by the model probability of the chosen player', () => {
  const model: MatchModel = {
    classes: ['p1', 'p2'],
    w: [1, 3].map((h) => Float64Array.from({ length: 768 + 156 }, (_, j) => (j === h ? 40 : 0))),
    b: new Float64Array(2),
    mu: new Float64Array(768 + 156),
    sd: new Float64Array(768 + 156).fill(1),
  };
  // Похожие на p1 по модели: 2, 9, 10 (признак «первый»), затем остальные по времени; 6 без признака — в конце.
  expect(gridOrder(index, candidates, 'A', base, 'open', 'p1', model).slice(0, 3)).toEqual(['2', '9', '10']);
  expect(gridOrder(index, candidates, 'A', base, 'open', 'p1', model).slice(-1)).toEqual(['6']);
});
```

- [ ] **Step 3: Убедиться, что падают**

Run: `cd web && npx vitest run src/features/analysis/queue.test.ts src/features/analysis/grid.test.ts`
Expected: FAIL — `confidentHint` и `gridOrder` не принимают модель.

- [ ] **Step 4: Подсказка очереди.** В `queue.ts` импорт и начало `confidentHint`:

```ts
import { candidateFeature, type MatchModel, MODEL_CONFIDENCE, predict } from './matchModel';
```

```ts
export function confidentHint(
  index: LookIndex,
  players: QueuePlayer[],
  candidate: Candidate,
  model?: MatchModel | null,
): string | null {
  // Модель матча, если она есть и у кандидата есть признак SigLIP; иначе — отрыв по цвету.
  const x = model ? candidateFeature(index, candidate) : null;
  if (model && x) {
    const free = players.filter((p) => available(index, p, candidate)).map((p) => p.id);
    const r = predict(model, x, free);
    return r && r.p >= MODEL_CONFIDENCE ? r.playerId : null;
  }
```

(дальше — прежнее тело с `const look = meanLook(...)`).

- [ ] **Step 5: Порядок сетки.** В `grid.ts` импорт `import { candidateFeature, type MatchModel, probabilityOf } from './matchModel';`,
  параметр `model?: MatchModel | null` последним у `gridOrder` и замена функции `score`:

```ts
  const score = (c: Candidate) => {
    const x = model ? candidateFeature(index, c) : null;
    if (model && x && model.classes.includes(similarTo)) return probabilityOf(model, x, similarTo);
    const look = meanLook(index, c.trackIds);
    return mean && look ? cosine(mean, look) : -2;
  };
```

- [ ] **Step 6: Обучение в паузах** — `web/src/features/analysis/useMatchModel.ts`:

```ts
import { useEffect, useRef, useState } from 'react';
import type { AnalysisAssignment } from '../../api/domain';
import type { Candidate } from './candidates';
import { type MatchModel, modelSamples, trainModel } from './matchModel';
import type { LookIndex } from './similar';

const DELAY_MS = 600;

// Модель матча для команды: переобучается через 0,6 с после последнего решения (тёплый старт), чтобы ввод
// клавишами не ждал обучения; до первого обучения и без признаков SigLIP — null (подсветка по цвету).
export function useMatchModel(
  index: LookIndex,
  candidates: Candidate[],
  team: 'A' | 'B',
  playerIds: string[],
  assignments: AnalysisAssignment[],
): MatchModel | null {
  const [model, setModel] = useState<MatchModel | null>(null);
  const prev = useRef<MatchModel | null>(null);
  const trained = useRef('');
  const args = useRef({ index, candidates, team, playerIds, assignments });
  args.current = { index, candidates, team, playerIds, assignments };
  const key = `${team}|${playerIds.join(',')}|${assignments
    .filter((a) => a.player_id)
    .map((a) => `${a.track_id}:${a.player_id}`)
    .sort()
    .join(',')}`;
  useEffect(() => {
    if (key === trained.current) return;
    const timer = setTimeout(() => {
      trained.current = key;
      const a = args.current;
      const next = trainModel(modelSamples(a.index, a.candidates, a.team, a.playerIds, a.assignments), prev.current);
      prev.current = next;
      setModel(next);
    }, DELAY_MS);
    return () => clearTimeout(timer);
  }, [key]);
  return model;
}
```

- [ ] **Step 7: Экраны.** В `IdentityQueue.tsx` после `const players = queuePlayers(...)`:

```tsx
  const model = useMatchModel(index, candidates, team, players.map((p) => p.id), assignments);
  const hint = current ? confidentHint(index, players, current, model) : null;
```

(заменив прежнюю строку `const hint = …`; импорт `import { useMatchModel } from './useMatchModel';`). В
`IdentityGrid.tsx` после `const players = queuePlayers(...)` — та же строка `const model = useMatchModel(...)`, а в
`refresh` вызов `gridOrder(index, candidates, t, assignments, s, sim, model)`.

- [ ] **Step 8: Тесты анализа**

Run: `cd web && npx vitest run src/features/analysis && npx tsc -b && npm run lint`
Expected: PASS; новых предупреждений Biome нет.

- [ ] **Step 9: Сверка с замером на JWH** (временная проверка, в Git не попадает). Выгрузить признаки и эталон в
  JSON — `<scratchpad>/identity/export_jwh.py`:

```python
"""Признаки и эталон JWH для сверки модели кабинета с замером Python: JSON без кадров."""
import base64, json, sys
import numpy as np
sys.path.insert(0, 'scripts')
from eval_people import load_features
run = json.load(open(sys.argv[1]))
sig = load_features(__import__('pathlib').Path(sys.argv[2]), 'siglip')
roster = {p['player_id']: p for p in run['context']['rosters']}
rows = []
for a in run['assignments']:
    t = next(x for x in run['tracks'] if x['track_id'] == a['track_id'])
    if a.get('player_id') and roster[a['player_id']]['side'] == 'home' and t.get('appearance') and a['track_id'] in sig:
        q = np.clip(np.rint(sig[a['track_id']] / np.linalg.norm(sig[a['track_id']]) * 127), -127, 127).astype(np.int8)
        rows.append({'track_id': a['track_id'], 'player': a['player_id'], 'intervals': t['intervals'],
                     'appearance': t['appearance'], 'embedding': base64.b64encode(q.tobytes()).decode()})
json.dump(rows, open(sys.argv[3], 'w'))
print(len(rows))
```

```bash
.venv/bin/python <scratchpad>/identity/export_jwh.py <scratchpad>/identity/run_review2.json data/people/jwh <scratchpad>/identity/jwh-features.json
```

и временный тест `web/src/features/analysis/zz-jwh.test.ts` (удалить после прогона):

```ts
import { readFileSync, writeFileSync } from 'node:fs';
import { it } from 'vitest';
import { intervalsClash } from './candidates';
import { predict, trainModel } from './matchModel';
import { decodeEmbedding, decodeLook } from './similar';

it('jwh', () => {
  type Row = { track_id: number; player: string; intervals: number[][]; appearance: string; embedding: string };
  const rows: Row[] = JSON.parse(readFileSync('<scratchpad>/identity/jwh-features.json', 'utf8'));
  const x = (r: Row) => {
    const e = decodeEmbedding(r.embedding);
    const l = decodeLook(r.appearance);
    const v = new Float64Array(e.length + l.length);
    v.set(e);
    v.set(l, e.length);
    return v;
  };
  const train = rows.filter((r) => r.intervals[0][0] < 26 * 60);
  const test = rows.filter((r) => r.intervals[0][0] >= 26 * 60);
  const model = trainModel(train.map((r) => ({ x: x(r), y: r.player })));
  let right = 0, sure = 0, sureRight = 0;
  for (const r of test) {
    const free = [...new Set(train.map((t) => t.player))].filter(
      (p) => !train.some((t) => t.player === p && intervalsClash(t.intervals, r.intervals)),
    );
    const p = model ? predict(model, x(r), free) : null;
    if (p?.playerId === r.player) right++;
    if (p && p.p >= 0.9) { sure++; if (p.playerId === r.player) sureRight++; }
  }
  writeFileSync('<scratchpad>/identity/jwh-ts.txt', `верно ${right}/${test.length}; уверенных ${sure} верно ${sureRight}`);
});
```

Run: `cd web && npx vitest run src/features/analysis/zz-jwh.test.ts && cat <scratchpad>/identity/jwh-ts.txt && rm src/features/analysis/zz-jwh.test.ts`
Expected: как у замера Python (1-й тайм → 2-й: верно ≈ 85%, уверенных ≈ 81% при ≈ 94%) с расхождением не больше
4 п.п.; иначе — разобраться (шаги, скорость обучения, стандартизация) до коммита.

- [ ] **Step 10: Commit**

```bash
cd web && npx biome format --write src/features/analysis/useMatchModel.ts src/features/analysis/queue.ts src/features/analysis/grid.ts src/features/analysis/IdentityQueue.tsx src/features/analysis/IdentityGrid.tsx src/features/analysis/identityFixtures.ts src/features/analysis/queue.test.ts src/features/analysis/grid.test.ts && cd ..
git add web/src/features/analysis/useMatchModel.ts web/src/features/analysis/queue.ts web/src/features/analysis/grid.ts web/src/features/analysis/IdentityQueue.tsx web/src/features/analysis/IdentityGrid.tsx web/src/features/analysis/identityFixtures.ts web/src/features/analysis/queue.test.ts web/src/features/analysis/grid.test.ts
git commit -m "feat(review): queue hints and grid order follow the match model"
```

---

### Task 16: E2E — очередь, сетка, участие

**Files:**
- Create: `web/e2e/identity-queue.spec.ts` (подготовка матча — как в `similar-picker.spec.ts`)
- Delete: `web/e2e/similar-picker.spec.ts`

- [ ] **Step 1: Сценарий.** Скопировать `similar-picker.spec.ts` в `identity-queue.spec.ts`, переименовать тест в
  `'players are labelled in the queue and the grid, absent ones leave it'`, имена зала и турнира — `Очередь
  ${suffix}`, и заменить всё после `const run = await imported.json();` на:

```ts
  const saved = async () => (await page.request.get(`/api/v1${path}/analysis/runs/${run.id}`)).json();
  const mine = async (playerId: string) =>
    (await saved()).assignments
      .filter((a: { player_id: string | null }) => a.player_id === playerId)
      .map((a: { track_id: number }) => a.track_id)
      .sort();
  const [p1, p2] = people.home;

  await page.goto(`${path}?tab=review`);
  await expect(page.getByRole('button', { name: 'Очередь', exact: true })).toHaveAttribute('aria-pressed', 'true');
  const queue = page.getByRole('region', { name: 'Очередь разметки' });
  // Очередь по времени: 1 (0:00–1:00), затем 2 (2:00–4:00); клавиша 1 — первый игрок по имени.
  await expect(queue).toContainText('0:00–1:00');
  await page.keyboard.press('1');
  await expect(queue).toContainText('2:00–4:00');
  await page.keyboard.press('1');
  await expect(queue).toContainText('Все фрагменты команды в очереди размечены');
  await expect.poll(() => mine(p1.id)).toEqual([1, 2]);

  // Сетка: фрагменты первого игрока — снять все, неназначенные — второму.
  await page.getByRole('button', { name: 'Сетка', exact: true }).click();
  const grid = page.getByRole('region', { name: 'Сетка разметки' });
  await grid.getByLabel('Показать').selectOption(p1.id);
  await grid.getByRole('button', { name: 'Выделить все на странице' }).click();
  await page.keyboard.press('Delete');
  await grid.getByLabel('Показать').selectOption('open');
  await grid.getByRole('button', { name: 'Выделить все на странице' }).click();
  await page.keyboard.press('2');
  await expect.poll(() => mine(p2.id)).toEqual([1, 2]);
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
    ).toBe(true);
    await page.screenshot({ path: `test-results/identity-grid-${width}.png`, fullPage: true });
  }

  // Игроки: второй не участвовал — его фрагменты вернутся в очередь.
  await page.getByRole('button', { name: 'Игроки', exact: true }).click();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('checkbox', { name: `Участвовал в матче: ${p2.name}` }).uncheck();
  await expect.poll(async () => (await saved()).absent_players).toEqual([p2.id]);
  await expect.poll(() => mine(p2.id)).toEqual([]);

  await page.reload();
  await expect(page.getByRole('status', { name: 'Прогресс очереди' })).toContainText('осталось 2');
  await expect(page.getByRole('button', { name: new RegExp(p2.name) })).toHaveCount(0);
  for (const width of [390, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
    ).toBe(true);
    await page.screenshot({ path: `test-results/identity-queue-${width}.png`, fullPage: true });
  }
```

Удалить из файла неиспользуемые переменные (`player`, `chosen`, `picker`), если Biome на них укажет.

- [ ] **Step 2: Удалить старый сценарий**

```bash
git rm web/e2e/similar-picker.spec.ts
```

- [ ] **Step 3: Прогон E2E изолированно** (сервис на 8000 и общую `web/dist` не трогать). Выгрузка рабочего дерева
  без изменения ветки:

```bash
R=<scratchpad>/e2e-queue; E="$R/export"; rm -rf "${R:?}"; mkdir -p "$E"
W=$(git stash create); git archive "${W:-HEAD}" | tar -x -C "$E"
ln -s "$PWD/.env" "$E/.env"; ln -s "$PWD/.venv" "$E/.venv"; ln -s "$PWD/web/node_modules" "$E/web/node_modules"
cd "$E/web" && npx vite build --outDir "$R/dist"
PYTHONPATH="$E/src" AIF_E2E_FAKE_MAIL=1 AIF_E2E_FAKE_ADDRESS=1 AIF_E2E_PORT=8289 \
  AIF_E2E_DATABASE_NAME=aifootball_queue_e2e AIF_WEB_DIST="$R/dist" npx playwright test --reporter=line
```
Expected: 35 passed (новый сценарий вместо старого). Снимки `test-results/identity-*.png` посмотреть глазами.
Если упадёт другой сценарий, сохраняющий разметку в версию, после которой загружена новая (ответ 409
`stale_analysis_run`), — перенести в нём сохранение до загрузки новой версии; правило сервера не ослаблять.

- [ ] **Step 4: Commit**

```bash
cd web && npx biome format --write e2e/identity-queue.spec.ts && cd ..
git add web/e2e/identity-queue.spec.ts
git commit -m "test(e2e): labelling in the queue and the grid, absent players"
```

---

### Task 17: документация

**Files:**
- Modify: `README.md` (пункты «Подбор похожих фрагментов» и «Подсказки для оставшихся фрагментов»)
- Modify: `docs/README.md` (раздел «Архитектура и следующие этапы»)
- Modify: `docs/superpowers/specs/2026-11-26-identity-queue-design.md`

- [ ] **Step 1: README.** Пункт «**Подсказки для оставшихся фрагментов:** …» удалить; в пункте «**Подбор похожих
  фрагментов:** …» оставить первое предложение о признаке цвета (`appearance`, `perception/appearance.py`) и
  заменить описание режима на:

```markdown
В «Проверке» — режимы «Очередь» (по умолчанию: один фрагмент, кнопки игроков в постоянном порядке, клавиши 1–9 и 0, X — «Не игрок матча», пробел — пропустить, Backspace — назад; игроки, видные одновременно, недоступны; подсвечивается только уверенная подсказка — модель матча: SigLIP 2 и цвет, обученные в браузере на решениях этого матча, вероятность ≥ 0,9, на JWH уверенных 72–84% фрагментов при точности 94–96%; без признака SigLIP — цвет с отрывом ≥ 0,05), «Сетка» (кадры класса, кисть: щелчок присваивает, повторный снимает; Ctrl/⌘ и Shift выделяют, клавиша класса — всем выделенным; плитка не перестраивается до «Обновить»), «Игроки» (переключатель «Участвовал в матче» и «Убрать» по фрагментам) и «По фрагментам». Разметка одна на матч: сохраняется сама, только в самую новую версию, новая версия забирает решения и участие ([спецификация](docs/superpowers/specs/2026-11-26-identity-queue-design.md)).
```

- [ ] **Step 2: docs/README.md** — строку «Подсказки игрока для оставшихся фрагментов» заменить на:

```markdown
- [Очередь разметки и одна разметка на матч](superpowers/specs/2026-11-26-identity-queue-design.md): «Очередь», «Сетка», «Игроки», участие в матче, перенос разметки в новую версию ([план](superpowers/plans/2026-11-26-identity-queue.md)); заменяет [подсказки игрока](superpowers/specs/2026-11-26-identity-suggestions-design.md).
```

- [ ] **Step 3: Спецификация** — в разделе «Вкладка «Проверка»» отразить уточнения из раздела «Отличия от
  спецификации» этого плана: режим по умолчанию для прогонов без признаков, кнопка «Продолжить разметку»,
  «Сохранить сопоставление» как «сохранить сейчас»; в «Проверке» убрать «миграция вверх и вниз» (схему поднимают
  тесты сервиса на тестовой базе).

- [ ] **Step 4: Commit**

```bash
git add README.md docs/README.md docs/superpowers/specs/2026-11-26-identity-queue-design.md
git commit -m "docs: identity queue, grid and one labelling per match"
```

---

### Task 18: общая проверка

- [ ] **Step 1:** `.venv/bin/ruff check src tests scripts migrations && .venv/bin/ruff format --check src tests scripts migrations`
- [ ] **Step 2:** `.venv/bin/python -m pytest --tb=line -q` — все тесты сервиса на тестовой базе (фоном, если дольше
  2 минут).
- [ ] **Step 3:** `cd web && npm run lint && npx vitest run && npx tsc -b && npx vite build --outDir <scratchpad>/build-check`
  (не в общую `web/dist`); в новых строках нет предупреждений Biome, кроме `role="group"` у переключателей (как во
  всех режимах).
- [ ] **Step 4:** `git diff --check origin/main...HEAD`
- [ ] **Step 5:** E2E из задачи 16 — 35/35, снимки 390 и 1440 px без горизонтальной прокрутки.

---

### Task 19: PR от `main`, PR #46, сайт

- [ ] **Step 1: Ветка без checkout.** PR = ветка сайта без PR #47 (он отдельный): дерево `HEAD` с отменой
  коммита `e03066f`, родитель — `origin/main`:

```bash
git fetch -q origin
T=$(git merge-tree --write-tree --merge-base=e03066f e03066f~1 HEAD)   # конфликтов быть не должно
C=$(git commit-tree "$T" -p origin/main -m "feat(review): identity queue, grid and one labelling per match")
git branch feat/identity-queue "$C"
git diff --stat origin/main feat/identity-queue | tail -3
git diff origin/main feat/identity-queue -- src/aifootball/processor/job.py | wc -l   # 0: PR #47 не вошёл
```

PR включает PR #45 (`drafts.ts`, `identityBase.ts`, предупреждение об устаревшем черновике) — в описании PR
указать: «зависит от PR #45, сливать после него».

- [ ] **Step 2: Проверка ветки на выгрузке** (`git archive feat/identity-queue`): `pytest` на тестовой базе, vitest,
  `tsc -b`, сборка, E2E 35/35 — как в задачах 16 и 18.
- [ ] **Step 3: PR** — `git push -u origin feat/identity-queue`; `gh pr create --base main` с описанием на русском
  (зачем — три проблемы пользователя, что сделано по режимам и сервису, проверка). Привязать к сессии. Не сливать.
- [ ] **Step 4: PR #46** — закрыть с комментарием «заменён PR #N (очередь и сетка)» только после согласия
  пользователя.
- [ ] **Step 5: Сайт** — только по согласию пользователя: `vite build` в `web/`, перезапуск сервера во вкладке «site
  server» той же командой. Миграция 0030 применяется к базе организатора при старте сервиса так же, как прежние
  (проверить в логе запуска), иначе — спросить пользователя перед `alembic upgrade head`.
- [ ] **Step 6: JWH с признаком SigLIP** (после обновления сайта, с согласия пользователя; попросить его сохранить
  разметку перед этим). Код перепаковки — копия кода второго прогона с правками PR #47 и задачи 13 (склейка и бюджет
  миниатюр из другой рабочей копии ещё не в `main`):

```bash
S=<scratchpad>; D=/Users/timofeynikulin/AI-football/data/processing/hse-jwh-2026-11-22
rm -rf "${S:?}/jwh/combined4" && cp -R "$S/jwh/combined3" "$S/jwh/combined4"
git diff <коммит задачи 13>~1 <коммит задачи 13> -- src/aifootball/perception/appearance.py src/aifootball/processor/job.py src/aifootball/analytics/exchange.py > "$S/jwh/embedding.patch"
(cd "$S/jwh/combined4" && patch -p1 < "$S/jwh/embedding.patch")
PYTHONPATH="$S/jwh/combined4/src" .venv/bin/python -u -m aifootball.cli process-job --job "$D/job-lineup.zip" \
  --video /Users/timofeynikulin/AI-football/data/raw/hse_futsal_456239357_jwh.mp4 --output "$D/result-embed.zip" \
  --models "$PWD/models" --artifacts "$D/work-ball/artifacts" --artifacts-job "$D/job.zip" --halves 5:26-24:52,27:30-53:42
PYTHONPATH="$S/jwh" .venv/bin/python "$S/jwh/cabinet_jwh.py" import "$D/result-embed.zip" run_embed
```

Expected: в пакете у фрагментов с кадрами есть `embedding`, предупреждения о весах нет; новый прогон сам забрал
решения самой новой версии (предупреждение «Перенесено решений из прежней версии: N»). Проверить в кабинете, что
очередь подсвечивает игроков (доля подсвеченных — порядка 70–80% неназначенных фрагментов ВШЭ Ю).
