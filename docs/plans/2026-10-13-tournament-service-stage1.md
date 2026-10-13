# Админка турниров и протокол матча — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** организатор через веб-приложение создаёт турниры, регламенты, команды, заявки и матчи,
ведёт ручной протокол во время игры или после неё, исправляет и подтверждает результат без видео.

**Architecture:** Python API и PostgreSQL хранят справочники и версии протокола; React работает
через API того же origin. Правила подсчёта вынесены в чистые функции. Изменения матча выполняются
как атомарные команды с проверкой версии и защитой от повторной отправки; подтверждённые снимки неизменяемы.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic, psycopg 3,
PostgreSQL 16; React 19, TypeScript, Vite, React Router, обычный CSS, lucide-react;
pytest/httpx, Vitest/Testing Library и Playwright. Node.js 24 LTS имеется локально.
Конкретные совместимые patch-версии фиксируются lock-файлами при установке в задаче 1/7.

**Spec:** `docs/specs/2026-10-13-tournament-service-design.md`.

## Global Constraints

- «Один организатор ведёт несколько турниров: команды, игроков, календарь, результаты и видеоаналитику».
- «Админка должна удобно работать на компьютере; календарь, карточки матчей и отчёты доступны также на телефоне».
- «Эта возможность не зависит от видео, завершения его обработки или доступности AI».
- «Изменение настроек турнира не переписывает прошлые матчи».
- «Отсутствующая информация не представляется нулём и не получает выдуманных временных отметок».
- «Повторная отправка одного действия не создаёт дубликат».
- «Одновременное редактирование проверяет версию записи».
- «Серия послематчевых пенальти хранится отдельно от счёта основного и дополнительного времени».
- «Игровое время события, время исходного видео и время внесения записи — отдельные поля».
- «Полная автономная работа без сети не является обещанием первой версии».
- Существующие CLI, аналитика и самостоятельные отчёты работают без установки web-зависимостей.
- Интерфейс и сообщения ошибок по-русски; имена кода и API на английском. Даты хранятся UTC,
  отображаются в часовом поясе турнира. Не использовать `datetime.now()` без timezone.
- В этой поставке нет импорта расписания/видео, S3-загрузки оригиналов, AI, идентификации треков
  и таблицы турнирных мест с неоговорёнными правилами равенства очков. Они имеют отдельные планы.
- Первую поставку запускаем локально с постоянной БД. Облачный деплой и внешний доступ не входят
  в выполнение этого плана; пароль администратора не коммитится, открытая регистрация отсутствует.

## Review Focus

1. Ответ потерялся после сохранения гола: повтор той же команды возвращает сохранённый результат,
   счёт не растёт второй раз; другой payload с тем же ключом отклоняется. Задачи 5 и 8.
2. Два открытых окна редактируют матч: устаревшая версия получает 409, локальный ввод не исчезает.
   Настоящий параллельный тест PostgreSQL, а не только последовательный mock. Задачи 5 и 8.
3. Сначала ввели 3:2, потом добавили два гола: видны 3:2 и неполный журнал 2:0,
   а не счёт 5:2; полный расходящийся журнал нельзя подтвердить. Задачи 4 и 5.
4. Изменили регламент/заявку после создания или публикации матча: исторический регламент,
   состав и опубликованный протокол сохраняются; удаление справочника не ломает ссылки. Задачи 2, 3 и 5.
5. Неизвестные участники/минуты, технический результат и серия пенальти: сведения остаются
   неполными, технический счёт не превращается в фиктивные голы, серия не меняет игровой счёт. Задачи 4–6.

## Границы поставки и технические решения

Это план первого этапа общей спецификации. Выход — рабочий приватный кабинет и возможность
явно опубликовать подтверждённый ручной протокол по отдельной публичной ссылке. Публичная
видеоаналитика остаётся третьим этапом. Протокол можно подтвердить и не публиковать.

Синхронные SQLAlchemy Session/FastAPI `def`-обработчики: здесь короткие транзакции, GPU и видео
не импортируются. БД одинаковая в разработке и тестах — PostgreSQL; SQLite не подменяет блокировки.
Vite proxy `/api` → `127.0.0.1:8000`; собранный SPA отдаётся тем же приложением. Производственный
режим требует HTTPS, Secure-cookie и конкретного разрешённого origin.

Документ протокола первой поставки хранится в закрытом локальном каталоге `data/service/attachments`,
доступен только через авторизованный API. Сохраняется UUID, MIME, размер и SHA256; интерфейс
`AttachmentStore` позволяет подключить S3 в следующем плане без изменения ссылок матчей.
Разрешены PDF/JPEG/PNG до 20 MiB, без inline-просмотра пользовательского HTML/SVG.

Состояние матча — один агрегат с `revision`: метаданные, текущая версия регламента, состав,
черновой протокол и ручной секундомер меняются под одной блокировкой строки матча.
События черновика — JSONB, валидируемый Pydantic. История команд и подтверждённые снимки —
отдельные таблицы; команды не стирают историю. Это осознанный выбор для малого кабинета:
сложные статистические запросы по множеству матчей относятся к следующему этапу.

### Карта файлов

| Файлы | Ответственность |
|---|---|
| `pyproject.toml`, `uv.lock`, `.gitignore`, `.env.example`, `compose.yaml`, `alembic.ini` | optional web-зависимости, PostgreSQL, окружение и миграции |
| `src/aifootball/service/__init__.py`, `config.py`, `db.py`, `errors.py`, `app.py` | конфигурация, фабрика API, БД, единый формат ошибок |
| `service/auth/{models,schemas,security,routes,cli}.py` | администраторы, сессии, CSRF, создание первого пользователя |
| `service/tournaments/{models,schemas,rules,operations,routes}.py` | турниры, неизменяемые варианты регламента, preview применения |
| `service/catalog/{models,schemas,operations,routes}.py` | постоянные команды/игроки, заявки турнира |
| `service/matches/{models,schemas,operations,routes}.py` | матч, состав, статусы, версия агрегата |
| `service/protocol/{schemas,events,projection,validation,commands,routes}.py` | журнал, подсчёты, подтверждение и история |
| `service/protocol/clock.py` | чистые переходы ручного секундомера |
| `service/storage/{attachments,routes}.py` | защищённые документы протокола |
| `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_service.py` | явная начальная схема; не `create_all()` при старте |
| `tests/service/conftest.py`, `fixtures.py`, `test_*.py` | интеграционные тесты API и чистые правила |
| `web/package.json`, `package-lock.json`, `index.html`, `vite.config.ts`, `tsconfig*.json` | фронтенд и фиксированные зависимости |
| `web/src/{main,App}.tsx`, `styles.css`, `api/{client,types}.ts` | маршруты, оболочка, общий API и сгенерированные типы |
| `web/src/features/auth/LoginPage.tsx` | вход и восстановление истёкшей сессии |
| `web/src/features/tournaments/{TournamentList,TournamentPage,RegulationForm}.tsx` | турниры, регламент, preview |
| `web/src/features/catalog/{TeamsPage,TeamRoster,PlayersPage}.tsx` | команды/игроки/заявки |
| `web/src/features/matches/{MatchList,MatchPage,LineupEditor}.tsx` | календарь, карточка и составы |
| `web/src/features/protocol/{ProtocolEditor,EventForm,EventJournal,ScoreEditor,ClockPanel,ConfirmPanel}.tsx` | ввод событий, счёт, ручные часы, подтверждение |
| `web/src/features/protocol/{outbox,useProtocolCommands}.ts` | локальная очередь ввода, версия, повтор, конфликты |
| `web/src/features/protocol/Attachments.tsx`, `PublicProtocolPage.tsx` | документы и опубликованный снимок |
| `web/src/test/setup.ts`, `web/src/**/*.test.ts*`, `web/e2e/*.spec.ts`, `web/playwright.config.ts` | проверки поведения и сквозной сценарий |
| `docs/service-stage1.md`, `scripts/export_service_openapi.py` | запуск, backup/restore, выгрузка схемы API |

Все `service/...` в таблице находятся внутри `src/aifootball/service/`. В новых пакетах создаются
`__init__.py`. Существующие файлы аналитики и их незакоммиченные изменения не включать в коммиты сервиса.
Перед выполнением сохранить исходный `git status` и проверить текущие тесты. Изоляцию выбирать
по using-git-worktrees: первый этап не зависит от незакоммиченного report-кода и может выполняться
в отдельном управляемом worktree текущего HEAD; использовать там актуальные spec/plan.

### Таблицы и ограничения

- `admins(id UUID PK, login unique, password_hash, active, created_at)`.
- `sessions(token_hash PK, admin_id FK, csrf_token, expires_at, created_at)`; сырой токен сессии только в cookie.
- `tournaments(id, name, season, starts_on, ends_on, timezone, revision, archived)`.
- `regulations(id, tournament_id FK, variant_name, version, rules JSONB, created_at)`;
  unique `(tournament_id, variant_name, version)`, immutable, FK из матча с RESTRICT.
- `teams(id, name, archived)` и `players(id, name, archived)` — постоянные личности.
- `entries(id, tournament_id FK, team_id FK, revision)` unique `(tournament_id, team_id)`;
  `entry_players(id, entry_id FK, player_id FK, shirt_number nullable, active)` unique `(entry_id, player_id)`.
  Активный номер уникален внутри заявки; неизвестный номер разрешён. Изменение команды в другом
  турнире не создаёт другого игрока. Историческая запись заявки не удаляется.
- `matches(id, tournament_id FK, home_entry_id FK, away_entry_id FK, regulation_id FK,
  regulation_override JSONB nullable, override_reason nullable, scheduled_at timestamptz,
  venue_label, referees JSONB, status, revision, protocol JSONB, clock JSONB,
  published_version_id nullable, created_at)`; CHECK домашняя заявка ≠ гостевой;
  обе заявки и регламент проверяются на принадлежность турниру.
- `lineup_members(id, match_id FK, entry_player_id FK, player_id FK, side, shirt_number,
  display_name)` unique `(match_id, player_id)`; снимок имени/номера при включении в состав.
- `match_commands(id, match_id FK, actor_id FK, request_id UUID, request_hash,
  before_revision, after_revision, body JSONB, response JSONB, created_at)`;
  unique `(match_id, request_id)`; успешные команды и audit фиксируются в одной транзакции.
- `protocol_versions(id, match_id FK, number, snapshot JSONB, confirmed_by FK,
  confirmed_at, published_at nullable, public_id UUID unique nullable)`;
  unique `(match_id, number)`. Снимок содержит регламент, состав, события, рассчитанные
  итоги и пометки неполноты. Опубликованный снимок не зависит от последующих справочников.
- `attachments(id, match_id FK, original_name, storage_key, mime, size, sha256,
  created_by FK, created_at, removed_at nullable)`; удаление ссылки аудируется, файл
  сохраняется пока на него ссылается подтверждённая версия.

Имена всех FK/unique/check задавать явно. JSON не заменяет FK справочников. Произвольные
UUID участников внутри события проверяет сервис по сохранённому составу матча до записи.
Архивирование вместо каскадного удаления; архивированные сущности доступны историческим матчам,
но не новым выборам. Нормализовать пробелы имени, не объединять игроков только по совпадению имени.

### Формат API и публичные контракты

Все приватные маршруты под `/api/v1`; UUID в JSON строками, даты ISO8601 с offset.
Успешный GET списка: `{items: [...], total: int}`; `limit=50`, max 100, `offset=0`.
Ошибка: `{error: {code: str, message: str, fields: object, current_revision: int|null}}`.
422 — ошибка полей/правил, 401 — сессия, 403 — CSRF/доступ, 404 — нет сущности,
409 — конфликт версии/ключа/ссылок. Не отдавать внутренние SQL/traceback клиенту.

Каждая изменяющая команда матча имеет:

```json
{
  "request_id": "UUID, созданный клиентом один раз",
  "expected_revision": 0,
  "kind": "add_event",
  "payload": {"event": {"id": "UUID", "kind": "goal", "side": "home", "period": 1,
    "elapsed_ms": null, "player_id": null, "assist_id": null, "own_goal": false,
    "from_penalty": false, "penalty_id": null, "video_ms": null, "notes": ""}}
}
```

Ответ `{match_id, revision, protocol, projection, clock, status, lineup, regulation}`;
его Pydantic-тип `MatchView`. `created_at` события задаёт сервер и не использует как игровое время.
`video_ms` первой поставки всегда null; ненулевое значение отклоняется до привязки видео.

**Определяемые типы:** `Regulation`, `ProtocolDocument`, `Event` (discriminated union),
`Projection`, `ClockState`, `Command`, `MatchView`, `DomainError(code, message, fields)`.
Pydantic `extra='forbid'`, UUID/enum/неотрицательные целые проверяются на входе.

**Regulation:** `periods_s: list[int>`, `clock_mode: clean|running|mixed`,
`mixed_stop_last_s: int|null`, `clock_display: elapsed|remaining`, `break_s: list[int]`,
`schedule_slot_s: int`, `timeouts: {allowed, duration_s, count, scope: period|match}`,
`extra: {enabled, periods_s, clock_mode, mixed_stop_last_s}`, `shootout: {enabled, initial_attempts}`,
`players_on_pitch`, `tournament_roster_limit`, `match_roster_limit`, `pitch_length_m`, `pitch_width_m`,
`fouls: {enabled, warning_threshold, reset: period|match, extra_carry: bool}`,
`points: {win, draw, loss}`, `allow_draw`. Число периодов и общая длительность — производные.
Слоты и длительности ограничены 24 часами, периодов 1–10, размеры >0, лимиты состава 1–1000.
Проверить ограничения extra/тайм-аутов даже при выключенных флагах; выключенные значения не применяются.

**ProtocolDocument:** `events: list[Event]`, `reported_totals` (nullable поля для обеих команд:
score, fouls, yellow_cards, dismissals; `period_scores` optional), `shootout_totals` nullable,
`completeness` по `goals/assists/fouls/cards/lineup/time` = unknown|partial|complete,
`result_type: played|technical`, `technical_reason: str|null`, `notes`, `public_notes`,
`attachment_ids`, `draft: bool`. Явный ноль отличается от null.

**Event:** общие `id, kind, side nullable, period nullable, elapsed_ms nullable,
video_ms nullable, notes, created_at`; полезная нагрузка:

| kind | Поля |
|---|---|
| goal | player_id, assist_id, assist_known: bool, own_goal, from_penalty, penalty_id |
| foul | player_id, victim_id, accumulated: bool, reason |
| card | player_id, card: yellow\|second_yellow\|red, previous_yellow_id nullable, reason |
| penalty_awarded | player_id nullable, reason |
| penalty_attempt | player_id nullable, penalty_id, outcome: goal\|saved\|off_target\|unknown |
| shootout_attempt | player_id nullable, attempt_number positive, outcome: goal\|saved\|off_target\|unknown |
| timeout | duration_ms nullable |
| substitution | player_out_id nullable, player_in_id nullable |
| stoppage | reason: injury\|technical\|other, duration_ms nullable |
| period_start / period_end | period обязательно, side=null |

У gol/фола/карточки/пенальти/замены/тайм-аута команда обязательна. Неизвестный участник допустим.
`assist_known` default=false; true с assist_id=null означает известное отсутствие ассиста.
У own_goal ассист отсутствует и known=true. Наличие assist_id требует known=true.
У shootout время и период null; лимиты попыток не запрещают sudden death.
Игровой timestamp внутри длины соответствующего периода. Extra-периоды нумеруются после основных;
не применять основной режим часов к extra. Для running допускается превышение времени периода
только с документированным `override_reason` матча и увеличенной длительностью в override.

**Чистые функции:**

- `validate_regulation(rules: Regulation) -> Regulation`.
- `validate_event(event: Event, *, regulation: Regulation, lineup: list[dict], events: list[Event]) -> Event`.
- `project_protocol(doc: ProtocolDocument, regulation: Regulation) -> Projection`.
- `validate_confirmation(doc: ProtocolDocument, projection: Projection, *, acknowledge_incomplete: bool) -> None`.
- `transition_clock(state: ClockState, action: str, *, now_ms: int, regulation: Regulation, elapsed_ms: int | None = None) -> ClockState`.

`Projection` содержит `event_score`, `effective_score`, `period_event_scores`,
`event_totals`, `reported_totals`, `shootout_score`, `warnings`, `incomplete_sections`.
Каждое nullable поле неизвестного общего итога остаётся null, если раздел не объявлен полным;
количество известных событий возвращается отдельно. `effective_score`: reported score при наличии,
иначе event score только при complete goals; иначе null с отображением «известно голов: N».
Для technical score берётся reported, голевой журнал не обязан его объяснять.

**Маршруты:**

| API | Задача |
|---|---|
| GET `/health`, `/ready` | процесс / SELECT 1 и версия миграций; не раскрывают credentials |
| POST `/auth/login`, `/auth/logout`; GET `/auth/me` | cookie-сессия, csrf token |
| GET/POST `/tournaments`; GET/PATCH `/tournaments/{id}` | турнир, проверка revision при PATCH |
| GET `/tournaments/regulation-presets` | редактируемый шаблон футзала; статический route регистрируется раньше UUID route |
| GET/POST `/tournaments/{id}/regulations` | список/новая версия именованного варианта |
| POST `/tournaments/{id}/regulations/{rid}/preview`, `/apply` | выбранные будущие матчи, ожидаемые revisions |
| GET/POST `/teams`, `/players`; PATCH `/teams/{id}`, `/players/{id}` | справочники, архивирование |
| GET/POST `/tournaments/{id}/entries`; GET/PUT `/entries/{id}/players` | команды/заявки, expected_revision |
| GET/POST `/tournaments/{id}/matches`; GET `/matches/{id}` | календарь и создание с регламентом |
| POST `/matches/{id}/commands` | все изменения существующего матча, составов, событий, часов |
| GET `/matches/{id}/history`, `/versions` | аудит/подтверждённые снимки |
| POST/GET `/matches/{id}/attachments`; GET `/attachments/{id}/download` | документы; POST headers request-id/revision |
| GET `/public/protocols/{public_id}` | только опубликованный snapshot с ограниченным набором полей |

**Command.kind:** `update_match`, `set_lineup`, `add_event`, `replace_event`, `remove_event`,
`set_totals`, `set_completeness`, `set_notes`, `set_status`, `clock_start`, `clock_pause`,
`clock_resume`, `clock_set`, `clock_end_period`, `confirm`, `reopen`, `publish`, `unpublish`,
`add_attachment`, `remove_attachment`. Payload-модели discriminated union;
не принимать произвольную замену всего JSON протокола клиентом.
Для связанного penalty эпизода add/replace/remove содержит `related_events: list[Event]`
либо `related_ids: list[UUID]`; итоговый документ валидируется атомарно. MatchView также содержит
`server_now_ms`, `home_entry_id`, `away_entry_id`, `tournament_id`, метаданные матча и
ссылки на текущую подтверждённую/опубликованную версии. Полный API DTO определяется backend,
frontend получает типы генерацией OpenAPI.

---

### Task 1: API, PostgreSQL и приватный вход

**Files:** config/db/errors/app, auth/*, migrations/*, pyproject/uv.lock/compose/.env.example,
tests/service/{conftest,test_auth,test_migrations}.py, .gitignore.

**Interfaces:** `create_app(settings: Settings) -> FastAPI`, `get_session() -> Iterator[Session]`,
`require_admin(request, session) -> Admin`, `require_csrf(request, session) -> Admin`;
`Settings` имеет database_url, allowed_origin, secure_cookies, session_hours=12, attachment_root.

- [ ] **Step 1: Добавить optional web-зависимости и тестовый harness.**
  `web = [fastapi, uvicorn, pydantic-settings, sqlalchemy, alembic, psycopg[binary],
  argon2-cffi, python-multipart]`, `web-dev = [httpx]` с major-ограничениями;
  существующий dev pytest сохраняется. Создать compose только PostgreSQL 16 с healthcheck,
  volume `service_pg`, dev порт `127.0.0.1:54329:5432`; пароль берётся из `.env`, не фиксируется.
  `.env.example`: PGUSER=aifootball, PGDATABASE=aifootball, PGPASSWORD пусто, DATABASE_URL
  объясняется в runbook. .gitignore дополнить `.env`, `node_modules/`, `web/dist/`,
  `web/test-results/`, `web/playwright-report/`, `.pytest_cache/`; lock-файлы не игнорировать.
  При выполнении Docker daemon сейчас выключен: запустить установленный Docker Desktop,
  затем compose; при отсутствии работающего runtime не утверждать, что интеграционные тесты прошли.

```bash
uv lock
uv sync --extra dev --extra web --extra web-dev
docker compose up -d db
```

- [ ] **Step 2: Написать проверки входа до обработчиков.** Фикстура `client` создаёт app с тестовой
  БД; `admin_client` создаёт admin через CLI-функцию и логинится, добавляет CSRF в headers.
  `db_session` использует отдельную БД `aifootball_test`; перед сессией мигрирует её с нуля,
  между тестами очищает только перечисленные service-таблицы. Нельзя TRUNCATE произвольную DATABASE_URL:
  имя БД обязано оканчиваться `_test`, и тестовая конфигурация передаётся явно.

```python
def test_private_routes_and_session(client, seed_admin):
    assert client.get('/api/v1/auth/me').status_code == 401
    assert client.post('/api/v1/auth/login', json={'login': 'admin', 'password': 'wrong'}).status_code == 401
    r = client.post('/api/v1/auth/login', json={'login': 'admin', 'password': seed_admin.password})
    assert r.status_code == 200
    assert 'HttpOnly' in r.headers['set-cookie']
    assert client.get('/api/v1/auth/me').json()['login'] == 'admin'
    assert client.post('/api/v1/auth/logout').status_code == 403
    client.headers['X-CSRF-Token'] = r.json()['csrf_token']
    assert client.post('/api/v1/auth/logout').status_code == 204
    assert client.get('/api/v1/auth/me').status_code == 401
```

- [ ] **Step 3: Запустить** `.venv/bin/python -m pytest tests/service/test_auth.py -q`;
  ожидается отсутствие service app/маршрутов, затем реализовать Session и seed CLI.

```python
from hashlib import sha256
from secrets import token_urlsafe
from argon2 import PasswordHasher

raw_token = token_urlsafe(32)
token_hash = sha256(raw_token.encode()).hexdigest()
password_hash = PasswordHasher().hash(password)
response.set_cookie('af_session', raw_token, httponly=True,
                    secure=settings.secure_cookies, samesite='lax', path='/')
```

  `python -m aifootball.service.auth.cli create-admin --login admin` читает пароль getpass,
  не принимает его в командной строке. CSRF хранится отдельным случайным токеном в sessions, клиент получает этот
  токен при login/me; verify constant-time. login проверяет Origin, все другие unsafe routes
  требуют session + Origin + CSRF. Разрешён ровно settings.allowed_origin; API без Origin
  допускается только с валидным CSRF после login (CLI bootstrap не HTTP).
  Защита login: после 10 ошибок за 10 минут по паре login/IP — 429; хранить счётчик в БД,
  доверять IP напрямую Request.client, не произвольному X-Forwarded-For.
  Auth-тесты покрывают истечение/деактивацию, Secure в prod, запрет foreign Origin,
  отсутствие парольных хэшей в ответах и throttling.

- [ ] **Step 4: Реализовать migration 0001 для таблиц всего плана** по схеме выше
  плюс `login_attempts(login, ip, failed_at)` с индексом; endpoint ready проверяет миграцию.
  Проверить fresh upgrade, downgrade/upgrade только в тестовой БД и отсутствие импортов
  torch/ultralytics при `create_app`. Добавить pytest.importorskip для web-модулей
  в service conftest, чтобы базовые тесты без extras не ломались.

```bash
.venv/bin/alembic upgrade head
.venv/bin/python -m pytest tests/service/test_auth.py tests/service/test_migrations.py -q
```

- [ ] **Step 5: Зафиксировать только файлы этой задачи** с сообщением
  `feat(service): add database and private admin sessions`; перед git add просмотреть diff
  и перечислить файлы явно. Коммиты выполнять в рабочем checkout по его permissions.

### Task 2: Турниры и версионированный регламент

**Files:** tournaments/*, tests/service/{test_regulations,test_tournaments}.py, fixtures.py.

**Interfaces:** Regulation и validate_regulation из контрактов; HTTP CRUD маршруты tournament/regulations;
`resolve_rules(match: Match) -> Regulation` применяет validated override к immutable regulation.

- [ ] **Step 1: Написать проверки правил и snapshot.**

```python
import pytest
from pydantic import ValidationError
from aifootball.service.tournaments.schemas import Regulation

def test_duration_and_mixed_window(regulation_data):
    r = Regulation.model_validate(regulation_data)
    assert r.total_s == 2400
    with pytest.raises(ValidationError):
        Regulation.model_validate({**regulation_data, 'periods_s': [0, 1200]})
    with pytest.raises(ValidationError):
        Regulation.model_validate({**regulation_data, 'clock_mode': 'mixed', 'mixed_stop_last_s': 1201})

def test_rule_versions_are_immutable(admin_client, tournament_factory, regulation_data):
    tid = tournament_factory()['id']
    url = f'/api/v1/tournaments/{tid}/regulations'
    old = admin_client.post(url, json={'variant_name': 'Группа', 'rules': regulation_data}).json()
    new = admin_client.post(url, json={'variant_name': 'Группа',
        'rules': {**regulation_data, 'periods_s': [900, 900]}}).json()
    assert new['version'] == old['version'] + 1
    items = admin_client.get(url).json()['items']
    assert next(item for item in items if item['id'] == old['id']) == old
```

  В этой задаче `regulation_data` определяет все поля Regulation: 2×1200s, clean/remaining,
  break=[600], slot=5400, тайм-аут 60s один за period, extra выключено с periods=[300,300],
  shootout выключено с initial_attempts=5, 5 игроков/30 турнир/14 матч, поле 40×20,
  fouls enabled threshold=5 reset=period extra_carry=true, points=3/1/0, allow_draw=true.
  Это редактируемый стартовый шаблон, не утверждение регламента конкретного турнира.
  tournament_factory создаёт турнир через POST с датами, сезоном и Europe/Moscow.

- [ ] **Step 2: Запустить** `.venv/bin/python -m pytest tests/service/test_regulations.py -q`.

- [ ] **Step 3: Реализовать модели/валидацию, create/read/update турнир и append regulation.**

```python
@model_validator(mode='after')
def coherent_periods(self):
    if len(self.break_s) != len(self.periods_s) - 1:
        raise ValueError('Число перерывов должно быть на один меньше числа таймов')
    if self.clock_mode == 'mixed' and (
        self.mixed_stop_last_s is None or not 0 < self.mixed_stop_last_s <= min(self.periods_s)
    ):
        raise ValueError('Укажите интервал чистого времени внутри каждого тайма')
    if self.match_roster_limit < self.players_on_pitch:
        raise ValueError('Заявка на матч меньше состава на поле')
    return self
```

  Сезон — строка, starts_on≤ends_on, timezone валидируется `zoneinfo.ZoneInfo`;
  PATCH requires expected_revision, UPDATE WHERE revision, иначе409.
  Новый вариант и новая версия создаются под блокировкой tournament для unique version.
  Именованные варианты «Группа»/«Плей-офф» не назначаются автоматически по названию матча.
  Override матча хранит полный валидированный итог rules и непустую причину.
  Маршруты применения к матчам принадлежат задаче 3, которая создаёт match aggregate и аудит.

- [ ] **Step 4: Проверить** invalid timezone/даты, extra mixed window, нулевые/отрицательные размеры,
  лимиты, disabled extras, variants. Две параллельные новые версии одного варианта получают
  разные номера; архивированный турнир не используется для создания нового варианта.

```bash
.venv/bin/python -m pytest tests/service/test_regulations.py tests/service/test_tournaments.py -q
```

- [ ] **Step 5: Commit** `feat(service): add tournament regulations and immutable versions`.

### Task 3: Команды, игроки, заявки, матчи и составы

**Files:** catalog/*, matches/*, tests/service/{fixtures,test_catalog,test_matches}.py.

**Interfaces:** `create_match(session, data: MatchCreate, actor: Admin) -> MatchView`,
`get_match_view(session, match_id: UUID) -> MatchView`; MatchView из контрактов;
fixture `match_factory(**overrides)` возвращает созданный MatchView JSON через API;
`execute_command(session, match_id: UUID, command: Command, actor: Admin) -> MatchView`
из protocol/commands.py — транзакционная оболочка, здесь поддерживает update_match/set_lineup/set_status.
Остальные kinds добавляются в задачах 5/6, неподдерживаемая команда возвращает 422.

- [ ] **Step 1: Написать API-тест полного базового сценария и неверных ссылок.**

```python
def test_match_keeps_roster_snapshot(admin_client, match_factory):
    m = match_factory()
    player = m['lineup'][0]
    r = admin_client.patch(f"/api/v1/players/{player['player_id']}", json={'name': 'Новое имя'})
    assert r.status_code == 200
    saved = admin_client.get(f"/api/v1/matches/{m['id']}").json()
    assert saved['lineup'][0]['display_name'] == player['display_name']

def test_entries_must_belong_to_match_tournament(admin_client, match_factory):
    a, b = match_factory(), match_factory()
    r = admin_client.post(f"/api/v1/tournaments/{a['tournament_id']}/matches",
        json={'home_entry_id': a['home_entry_id'], 'away_entry_id': b['away_entry_id'],
              'regulation_id': a['regulation']['id'], 'scheduled_at': '2026-10-20T18:00:00+03:00'})
    assert r.status_code == 422
```

  `match_factory` создаёт tournament+rules, два team, два entry, по два player/entry_player
  через HTTP; создаёт match, затем `set_lineup` command этой задачи.
  Все id берутся из реальных ответов, без магических внешних UUID.

- [ ] **Step 2: Запустить** `.venv/bin/python -m pytest tests/service/test_catalog.py tests/service/test_matches.py -q`.

- [ ] **Step 3: Реализовать CRUD и создание матча с snapshot регламента.**

```python
def assert_match_links(home, away, regulation, tournament_id):
    if home.id == away.id:
        raise DomainError('same_team', 'Команды матча должны отличаться', {})
    if {home.tournament_id, away.tournament_id, regulation.tournament_id} != {tournament_id}:
        raise DomainError('foreign_tournament', 'Выберите команды и регламент этого турнира', {})
```

  Новый match revision=0, scheduled, пустой ProtocolDocument, paused ClockState с elapsed=0;
  defaults completeness unknown. Команда `set_lineup` этой задачи заменяет состав под match lock:
  только entry_players обеих заявок, одна личность не в обеих командах, номер уникален на сторону,
  roster≤limit, snapshot display_name/shirt_number. Если событие ссылается на удаляемого участника,
  отклонить и объяснить, какие события исправить; архивирование player не стирает прежний состав.
  UTC scheduled_at должен иметь offset; дата календаря фильтруется границами дня timezone турнира.
  Каталог имён одноимённых игроков не объединяет автоматически.

  Здесь создать общие ProtocolDocument/ClockState/Command/MatchView DTO из контрактов без
  вычисления событий; задача4 добавляет полную union-валидацию и projection. Первичный MatchView
  возвращает пустой projection с unknown totals. Оболочка execute_command блокирует match,
  проверяет request_id/hash раньше expected_revision, пишет audit+новую revision атомарно
  и возвращает MatchView. Алгоритм целиком приведён в задаче5; он нужен уже для set_lineup.
  Hash включает kind/payload/expected_revision, канонический JSON sort_keys=True.
  Preview принимает `{match_ids, new_regulation_id}`, возвращает before/after и revision
  плюс причины отказа. Apply принимает request_id и пары id/revision, блокирует матчи по sorted UUID,
  проверяет scheduled+будущее время+нет событий/запущенных часов/confirmed version;
  одно изменение с историей для каждого, отклонение одного отменяет всю транзакцию.
  Пакетный повтор узнаётся по сохранённому request_id и списку payload в match_commands.

- [ ] **Step 4: Проверить** перенос матча сохраняет id; duplicate entry/active jersey=409;
  неизвестный номер/null разрешён; archived недоступен новым выборам; чужой игрок/слишком большой
  состав/две стороны/наивная дата отвергаются. Сохранить матч и прочитать из новой Session
  для проверки реального сохранения. Добавить тест новой версии регламента:
  create_match с версией1 → POST версия2 → GET match по-прежнему версия1;
  preview/apply двух будущих матчей при одной устаревшей revision не меняет ни одного.
  Повтор set_lineup не меняет revision дважды; scheduled→live→ended допустим,
  cancelled/postponed→live требует явного возвращения в scheduled.

```bash
.venv/bin/python -m pytest tests/service/test_catalog.py tests/service/test_matches.py -q
```

- [ ] **Step 5: Commit** `feat(service): add teams rosters and scheduled matches`.

### Task 4: События и честные итоги частичного протокола

**Files:** protocol/{schemas,events,projection,validation}.py, tests/service/{test_events,test_projection}.py.

**Interfaces:** Event/ProtocolDocument/Projection, validate_event/project_protocol/validate_confirmation
из контрактов. Эти функции не читают БД и не изменяют исходные документы.

- [ ] **Step 1: Написать проверки принципов счёта.**

```python
def test_partial_score_is_not_added_to_known_goals(protocol_factory, regulation):
    from aifootball.service.protocol.projection import project_protocol
    doc = protocol_factory(home_score=3, away_score=2, home_goals=2, goals='partial')
    p = project_protocol(doc, regulation)
    assert p.event_score == {'home': 2, 'away': 0}
    assert p.effective_score == {'home': 3, 'away': 2}
    assert 'goals' in p.incomplete_sections

def test_own_goal_and_shootout_are_separate(protocol_factory, regulation):
    from aifootball.service.protocol.projection import project_protocol
    doc = protocol_factory(own_goal_side='home', shootout_home_goals=2, goals='complete')
    p = project_protocol(doc, regulation)
    assert p.effective_score == {'home': 0, 'away': 1}
    assert p.shootout_score == {'home': 2, 'away': 0}
```

  protocol_factory в tests/service/fixtures.py строит валидированные документы:
  home_goals=N создаёт N goal Event с уникальными UUID; own_goal_side отдельный goal;
  shootout_home_goals отдельные shootout_attempt с порядковыми номерами; nullable поля не
  заполняет нулями. regulation fixture = Regulation(regulation_data).

- [ ] **Step 2: Запустить** `.venv/bin/python -m pytest tests/service/test_events.py tests/service/test_projection.py -q`.

- [ ] **Step 3: Реализовать типизированные события и подсчёт.**

```python
def goal_side(event):
    if event.own_goal:
        return 'away' if event.side == 'home' else 'home'
    return event.side

score = {'home': 0, 'away': 0}
for event in doc.events:
    if event.kind == 'goal':
        score[goal_side(event)] += 1
```

  Обычный goal: автор/ассист в забивающей команде; при неизвестном авторе ассист допускается
  только известному игроку этой стороны с пометкой неполного автора. Own goal player в стороне
  автора, assist_id запрещён. Goal.from_penalty требует существующий penalty_awarded и
  penalty_attempt outcome=goal; один penalty_id максимум у одного goal и одной попытки.
  При добавлении goal-from-penalty команда добавляет попытку/гол атомарно (UI форма),
  не сохраняет промежуточный несогласованный протокол. В проекции attempt не прибавляет гол.
  Remove linked goal/attempt требует удалить/исправить весь связанный эпизод явной командой
  с `related_ids`, без скрытого удаления пользователю.
  second_yellow связан с предыдущей yellow того же player/match, которая раньше в журнале;
  при неизвестном player предыдущая карточка может быть null и помечается неизвестной.
  Счётчик yellow включает вторую yellow, dismissals считает second_yellow/red по одному.
  Запрещён независимый derived red того же эпизода. Foul.accumulated только если fouls enabled;
  группировка накопленных по period или match с extra_carry по rules, без догадки о фоле по карточке.
  Substitution неизвестные участники допустимы, известные той же стороны и не одинаковые.
  Тайм-ауты сверх лимита/аномальный порядок карточек дают явное предупреждение и требуют
  примечания; не терять реально случившееся событие из-за лимита правил.

- [ ] **Step 4: Проверить** неизвестные minutes/player, отрицательное время, extra при disabled,
  assist=self/opponent, victim той же стороны с явным отказом, повтор event.id, блок удаления
  previous_yellow/penalty_awarded, отмену гола, карточки и фола с пересчётом; отсутствие изменения
  doc; технический результат требует reason, полнота+счёт по таймам сверяются при confirm.
  В partial режиме conflicting reported/event totals → warning; в complete → 422 при confirm.

```bash
.venv/bin/python -m pytest tests/service/test_events.py tests/service/test_projection.py -q
```

- [ ] **Step 5: Commit** `feat(service): add manual events and protocol projections`.

### Task 5: Атомарный протокол, подтверждение, публикация и документы

**Files:** protocol/{commands,routes}.py, matches/models.py, storage/*,
tests/service/{test_commands,test_confirmation,test_attachments}.py.

**Interfaces:** execute_command из задачи3; `apply_mutation(match, command, actor, now) -> None`
в commands.py делегирует события validate_event и project_protocol;
`AttachmentStore.put(id: UUID, stream: BinaryIO, mime: str) -> AttachmentInfo`,
`AttachmentStore.open(storage_key: str) -> BinaryIO`. AttachmentInfo: key,size,sha256,mime.

- [ ] **Step 1: Написать сценарии повторов, подтверждения и конфликтов.**

```python
from uuid import uuid4

def test_retry_adds_goal_once(admin_client, match_factory):
    m = match_factory()
    command = {'request_id': str(uuid4()), 'expected_revision': m['revision'],
        'kind': 'add_event', 'payload': {'event': {'id': str(uuid4()), 'kind': 'goal',
        'side': 'home', 'period': 1, 'elapsed_ms': None, 'player_id': None,
        'assist_id': None, 'own_goal': False, 'from_penalty': False,
        'penalty_id': None, 'video_ms': None, 'notes': ''}}}
    url = f"/api/v1/matches/{m['id']}/commands"
    first = admin_client.post(url, json=command)
    repeat = admin_client.post(url, json=command)
    assert first.status_code == repeat.status_code == 200
    assert repeat.json() == first.json()
    saved = admin_client.get(f"/api/v1/matches/{m['id']}").json()
    assert len(saved['protocol']['events']) == 1
    assert saved['revision'] == m['revision'] + 1
    conflicting = {**command, 'payload': {'event': {**command['payload']['event'], 'side': 'away'}}}
    assert admin_client.post(url, json=conflicting).status_code == 409
```

  Добавить два независимых Client/Session: оба команды с одной expected_revision;
  синхронизировать ThreadPoolExecutor+Barrier, после commit одной вторая409;
  по новой Session ровно один event и audit. Тест использует отдельную PostgreSQL БД,
  без оборачивания двух клиентов в одну rollback-транзакцию.

- [ ] **Step 2: Запустить** `.venv/bin/python -m pytest tests/service/test_commands.py tests/service/test_confirmation.py -q`.

- [ ] **Step 3: Расширить оболочку команды полным протоколом.**

```python
with session.begin():
    match = session.scalar(select(Match).where(Match.id == match_id).with_for_update())
    if match is None:
        raise DomainError('not_found', 'Матч не найден', {})
    digest = request_digest(command)
    previous = session.scalar(select(MatchCommand).where(
        MatchCommand.match_id == match_id, MatchCommand.request_id == command.request_id))
    if previous is not None:
        if previous.request_hash != digest:
            raise DomainError('idempotency_conflict', 'Ключ отправки уже использован', {})
        return MatchView.model_validate(previous.response)
    if match.revision != command.expected_revision:
        raise RevisionConflict(match.revision)
    apply_mutation(match, command, actor, datetime.now(timezone.utc))
    match.revision += 1
    session.flush()
    view = get_match_view(session, match.id)
    session.add(MatchCommand(match_id=match.id, actor_id=actor.id,
        request_id=command.request_id, request_hash=digest,
        before_revision=command.expected_revision, after_revision=match.revision,
        body=command.model_dump(mode='json'), response=view.model_dump(mode='json')))
return view
```

  request_digest — SHA256 json.dumps(command.model_dump(mode='json'), sort_keys=True,
  separators=(',', ':')); RevisionConflict наследует DomainError с code=revision_conflict
  и current_revision. get_session не запускает SELECT до session.begin в commands:
  auth использует отдельную короткую read Session, чтобы избежать nested transaction.
  Копировать protocol JSON через model_dump после изменения, чтобы SQLAlchemy видел dirty;
  ошибку/rollback не оставлять в shared ORM Session после ответа.

  replace_event сохраняет id/created_at, исправления в audit, remove_event физически убирает
  из draft, исходные body в audit остаются. Для связанного penalty эпизода add/replace/remove
  payload имеет `related_events`/`related_ids`; union разрешает только goal/attempt этого
  penalty_id, валидируется итоговый документ целиком до flush.
  set_totals заменяет nullable reported totals; set_completeness не подделывает отсутствующие
  player/time. Каждый event сохраняется сразу, но confirmation проверяет весь документ.
  status ended не означает confirmed. confirm разрешён только ended и paused clock,
  требует acknowledge_incomplete если есть unknown/partial, выдаёт неизменяемый номер снимка.
  Технический результат подтверждается без goal-событий с обязательной причиной.
  Complete goal journal должен совпадать с reported score и полными period_scores;
  sum period_scores = score, shootout отдельно. Complete assists требует информации об
  ассисте каждого обычного гола (добавить `assist_known: bool`, известное отсутствие ≠ неизвестно).
  Полнота участников/времени проверяет фактические null, а не доверяет только переключателю UI.
  confirm запрещает дальнейшее изменение draft: reopen явно копирует последний snapshot,
  снимает draft confirmation, оставляя прежний published_version_id.
  publish принимает version_id собственного матча, сохраняет public_id и переключает
  published_version_id; public route возвращает только выбранный опубликованный снимок,
  прежняя ссылка после смены/отзыва возвращает404. Audit/session/storage_key/несохранённый
  draft/внутренние notes не входят в public DTO; заметки для публикации отдельное
  поле `public_notes`. Скачать attachment публично нельзя в этом этапе.

  Attachment POST получает X-Request-ID/X-Expected-Revision и CSRF. Потоково ограничить
  20MiB и сверить MIME по сигнатуре PDF/PNG/JPEG, оригинальное имя только metadata;
  storage_key = UUID, пользователь не выбирает путь. tempfile→rename после проверки,
  затем add_attachment под match lock с audit. Неудача БД удаляет новый неиспользуемый файл;
  существующие файлы/исторические версии не удаляются. Retry сверяет SHA256/размер и возвращает
  прежнее attachment без добавления новой ссылки. Download Content-Disposition=attachment,
  nosniff; untrusted filename безопасно кодируется, path traversal невозможен.

- [ ] **Step 4: Проверить** confirm partial с acknowledge/без него, 3:2 vs полный2:0,
  null assists vs explicit no assist, reopen/publish/revoke, snapshot после исправления,
  повтор remove/update/confirm, сбой после записи до получения ответа, rollback audit,
  401 и неопубликованный public_id404, документы size/magic/path и недоступность без session.
  Повтор подтверждения не создаёт вторую версию. Два simultaneous confirm получают200/409.
  Запустить завершённые snapshot/apply тесты задач2–3 со всеми events.

```bash
.venv/bin/python -m pytest tests/service -q
```

- [ ] **Step 5: Commit** `feat(service): persist audited protocol commands and confirmations`.

### Task 6: Ручной секундомер и периоды

**Files:** protocol/clock.py, protocol/commands.py, tests/service/{test_clock,test_clock_commands}.py.

**Interfaces:** transition_clock из контрактов;
`clock_elapsed(state: ClockState, *, now_ms: int, regulation: Regulation) -> int`.
ClockState: period (1-based), phase=not_started|running|paused|ended,
elapsed_ms, anchor_utc_ms nullable, break_started_utc_ms nullable, source='manual'.

- [ ] **Step 1: Написать детерминированные тесты часов без sleep.**

```python
def test_clean_clock_excludes_pauses(regulation, empty_clock):
    from aifootball.service.protocol.clock import transition_clock, clock_elapsed
    s = transition_clock(empty_clock, 'start', now_ms=1000, regulation=regulation)
    s = transition_clock(s, 'pause', now_ms=11000, regulation=regulation)
    assert clock_elapsed(s, now_ms=21000, regulation=regulation) == 10000
    s = transition_clock(s, 'resume', now_ms=21000, regulation=regulation)
    assert clock_elapsed(s, now_ms=26000, regulation=regulation) == 15000

def test_remaining_is_display_only(regulation, empty_clock):
    from aifootball.service.protocol.clock import transition_clock, clock_elapsed
    s = transition_clock(empty_clock, 'start', now_ms=1000, regulation=regulation)
    elapsed = clock_elapsed(s, now_ms=61000, regulation=regulation)
    assert elapsed == 60000
    assert regulation.periods_s[0] * 1000 - elapsed == 1140000
```

- [ ] **Step 2: Запустить** `.venv/bin/python -m pytest tests/service/test_clock.py -q`.

- [ ] **Step 3: Реализовать переходы с server time и сохранением anchor.**

```python
def elapsed_from_anchor(state, now_ms):
    delta = max(0, now_ms - state.anchor_utc_ms) if state.phase == 'running' else 0
    return state.elapsed_ms + delta
```

  clean: pause фиксирует elapsed и снимает anchor; running: обычная остановка игры пишет
  stoppage, но не pause часы (UI объясняет); ручная коррекция clock_set всё равно доступна
  с причиной. mixed: pause допустима только после threshold текущего периода, часы
  не останавливаются автоматически при достижении threshold — нужен сигнал администратора.
  При delta<0 вернуть неизменённое elapsed и warning о времени сервера.
  Каждая команда возвращает server_now_ms для коррекции клиентского display; request
  client timestamp не влияет на clock. На экране requestAnimationFrame/performance.now
  экстраполирует только отображение, refresh получает server state, не прибавляет заново.
  При достижении длительности clamp display, показать «Подтвердите конец тайма», не менять
  статус/протокол автоматически. clock_end_period создаёт ровно один period_end Event,
  phase ended и фиксирует boundary. clock_start следующего period допустим только после
  end предыдущего, сбрасывает elapsed, создаёт period_start. Дополнительные периоды
  доступны только enabled; переход в shootout отключает игровой секундомер.
  clock_set требует reason, elapsed 0..period length и аудит, не передвигает timestamps
  ранее введённых событий. event.elapsed_ms UI может подставить из ручных часов, но
  пользователь может очистить/исправить; не присваивать video_ms.

- [ ] **Step 4: Проверить** running/mixed threshold и resume, extra иной режим,
  refresh при running, двойной start/end через idempotency, pause не запущенных часов,
  manual correction с причиной, неизвестное время событий без clock_start,
  истёкшую длительность без автоматического окончания и отрицательный server delta.

```bash
.venv/bin/python -m pytest tests/service/test_clock.py tests/service/test_clock_commands.py -q
```

- [ ] **Step 5: Commit** `feat(service): add regulation-aware manual match clock`.

### Task 7: Веб-кабинет с турнирами, регламентом и календарём

**Files:** web конфигурация/src shell/api/auth/tournaments/catalog/matches из карты;
web/src/features/{tournaments,catalog,matches}/*.test.tsx, scripts/export_service_openapi.py,
service/app.py (SPA/static fallback).

**Interfaces:** сгенерированный `web/src/api/types.ts` из OpenAPI всех завершённых маршрутов;
`api<T>(path: string, options?: RequestInit): Promise<T>`;
`ApiError(code, message, fields, currentRevision)`; App маршруты перечислены ниже.

- [ ] **Step 1: Подготовить React/Vite без внешнего проекта.** Перед реализацией прочитать
  frontend-app-builder/react-best-practices для нового UI. Создать package scripts
  `dev`, `build` (tsc -b && vite build), `test` (vitest run), `test:e2e` (playwright test),
  `types:api` (openapi-typescript ../data/service/openapi.json -o src/api/types.ts).
  React/ReactDOM одной версии19, TS5, Vite совместим с Node24; router в library mode.
  Vitest/jsdom/TestingLibrary/MSW для поведения. Генерацию npm lock выполнить при установке,
  не писать выдуманный lock вручную. Backend OpenAPI экспортируется без подключения к БД.

```bash
npm --prefix web install
.venv/bin/python scripts/export_service_openapi.py --output data/service/openapi.json
npm --prefix web run types:api
```

- [ ] **Step 2: Написать UI-тесты формы регламента и ошибок.**

```tsx
it('показывает общую длительность и отправляет длины таймов', async () => {
  const save = vi.fn().mockResolvedValue(undefined);
  render(<RegulationForm initial={futsalPreset} onSave={save} />);
  await userEvent.clear(screen.getByLabelText('Длительность тайма 1, минут'));
  await userEvent.type(screen.getByLabelText('Длительность тайма 1, минут'), '15');
  expect(screen.getByText('Основное время: 35 минут')).toBeVisible();
  await userEvent.click(screen.getByRole('button', {name: 'Сохранить регламент'}));
  expect(save.mock.calls[0][0].periods_s).toEqual([900, 1200]);
});
```

  `futsalPreset` = GET API preset/локальный typed объект из regulation_data; использовать
  один backend preset endpoint `/tournaments/regulation-presets` с данным задачи2,
  а не второй независимо меняющийся источник defaults. Тест импортирует fixture этого ответа.

- [ ] **Step 3: Запустить** `npm --prefix web test`; затем реализовать shell и формы.

```ts
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options, credentials: 'same-origin',
    headers: {...options.headers, ...(options.method && options.method !== 'GET'
      ? {'X-CSRF-Token': sessionCsrfToken()} : {})},
  });
  if (!response.ok) throw await decodeApiError(response);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
```

  `sessionCsrfToken()` читает текущий AuthContext, `decodeApiError` создаёт ApiError
  по единому формату и fallback «Не удалось связаться с сервером» для неверного JSON.
  Headers создавать через `new Headers(options.headers)` в реальной реализации,
  чтобы RequestInit.headers в форме Headers/array тоже поддерживались.
  JSON Content-Type только JSON body; FormData не получает принудительный boundary.
  Сессия в cookie, токен сессии не localStorage; /auth/me при загрузке и послеlogin.
  401 возвращает форму входа с сохранением path и локального черновика.

  Routes: `/login`, `/tournaments`, `/tournaments/:id`, `/teams`, `/players`,
  `/tournaments/:id/teams/:entryId`, `/matches/:id`, `/protocols/:publicId`.
  Desktop1440px: sidebar232px, рабочая область на всю оставшуюся ширину;
  турнир tabs «Матчи / Команды / Регламент»; календарь широкая таблица с датой, временем,
  командами, статусом и счётом. Нет центральной телефонной колонки.
  На375px sidebar→drawer, формы одной колонкой, таблица в собственной scroll-области,
  документ целиком не распирается. Доступные labels, focus, ошибки рядом с полями,
  живой текст aria-live о сохранении. Empty/loading/error состояния реальны, без
  выдуманных матчей/статистики; seed demo только отдельной командой и меткой демо.
  Формы регламента включают все поля контракта, даты/часовой пояс, варианты, versions,
  override с причиной и preview future apply; предупреждение что существующие матчи не меняются.
  Match create: заявки из выбранного турнира, конкретный variant/version, дата local→UTC,
  venue label, referees; составы редактируются только commands API. перенос через update_match.
  SPA fallback не перехватывает `/api`, missing assets404 и path traversal; HTML приватной
  оболочки не даёт доступа к данным, API всегда проверяет session.

- [ ] **Step 4: Проверить** выбор archived/history, server field errors,
  timezone сохранение, preview409, create tournament→teams→entries→match через API,
  клавиатуру и screen layout1440/768/375. Build и basic UI tests проходят.

```bash
npm --prefix web test
npm --prefix web run build
```

- [ ] **Step 5: Commit** `feat(web): add tournament administration and match calendar`.

### Task 8: Протокол в браузере, повтор отправки и сохранение ввода

**Files:** web/src/features/protocol/* из карты,
web/src/features/protocol/{outbox,useProtocolCommands,ProtocolEditor}.test.ts*.

**Interfaces:** `QueuedCommand {matchId, requestId, expectedRevision, kind, payload,
state: queued|sending|uncertain|conflict, createdAt}`;
`Outbox` методы `load(matchId, adminId)`, `save(items)`, `remove(requestId)`;
`useProtocolCommands(matchId)` возвращает `view, enqueue, retry, resolveConflict, saveState`.

- [ ] **Step 1: Проверить потерянный ответ и конфликт в UI.**

```ts
it('повторяет сомнительную отправку с тем же ключом', async () => {
  const sent: string[] = [];
  const send = vi.fn(async (command: QueuedCommand) => {
    sent.push(command.requestId);
    if (sent.length === 1) throw new TypeError('Network failed');
    return savedMatch;
  });
  const queue = createCommandQueue({send, store: memoryOutbox, refresh: async () => savedMatch});
  await queue.enqueue(goalCommand);
  await queue.retry();
  expect(sent).toEqual([goalCommand.requestId, goalCommand.requestId]);
  expect(memoryOutbox.load(goalCommand.matchId, 'admin')).toEqual([]);
});
```

  `createCommandQueue({send, store, refresh})` реализуется в outbox.ts, работает вне React;
  send: (QueuedCommand)=>Promise<MatchView>, refresh: ()=>Promise<MatchView>;
  memoryOutbox — тестовый объект тех же методов с structuredClone, goalCommand/savedMatch —
  typed фикстуры фактического API задачи5. Второй тест: send409→state conflict,
  payload сохраняется, автоматического retry с новой revision нет.

- [ ] **Step 2: Запустить** `npm --prefix web test` до реализаций outbox/UI.

- [ ] **Step 3: Реализовать последовательную очередь и editor.**

```ts
const storageKey = (adminId: string, matchId: string) =>
  `aifootball:protocol:v1:${adminId}:${matchId}`;
const requestId = crypto.randomUUID();
const stored = {matchId, requestId, expectedRevision: view.revision,
  kind, payload, state: 'queued', createdAt: new Date().toISOString()};
```

  До первой отправки записать outbox. localStorage failure/quota → показать «Локальная
  копия недоступна», не заявлять что input защищён, сохранять в памяти и позволять скачать
  черновик JSON. В store только ввод протокола данного admin/match, без cookie/CSRF/документов.
  JSON store schema-version валидируется; повреждённое значение не отправлять как команду.
  При logout скрыть очередь, очистку предложить после экспорта несохранённых данных.
  Для нескольких окон проверять storage event: не позволять обоим автоматически отправлять
  одну локальную очередь, режим «Открыто в другом окне»/ручной takeover; сервер всё равно
  гарантирует idempotency и CAS. Нужен тест двух queue instances на общем store.

  Только одна команда in flight на матч. Новая queued команда получает expected_revision
  перед первой отправкой из последнего view; после первой попытки requestId+payload+
  expectedRevision неизменяемы даже при uncertain. При network error/timeout сохранить
  uncertain, bounded retry (1s/3s/10s) при доступной сети, затем явная кнопка; refresh
  не означает, что сомнительная команда не сохранилась. При200 удалить запись, GET актуальный
  MatchView перед следующей queued (повтор мог вернуть исторический ответ).
  При409 остановить очередь, показать серверную версию рядом с локальным вводом;
  пользователь выбирает «Применить как новое изменение» (новый requestId/revision) или
  «Оставить серверную версию» с экспортом удаляемого локального ввода. Никакого silent merge.
  422 → показать поля и оставить draft формы; исправление создаёт новую команду.
  401 → форма входа, outbox не стирается; возвращение тем же admin продолжает повтор.

  ProtocolEditor имеет «Вести матч»/«Заполнить после матча», крупные кнопки гол/фол/карточка/
  тайм-аут/период, остальные виды в меню. EventForm fields соответствует union;
  секундомер подставляет elapsed только при желании, null доступен. Гол с пенальти одной
  формой создаёт связанные события атомарно; second-yellow previous-yellow выбор/unknown.
  Счёт reported рядом с known events, clear→null, explicit0; отдельный shootout.
  Completeness по разделам, warnings несоответствия, notes/internal vs public notes,
  technical reason, подтверждение с перечнем пропусков и acknowledge checkbox.
  EventJournal: edit/cancel с просмотром зависимых событий, history, exact source of time.
  ClockPanel: ручные start/pause/resume/set/end, elapsed/countdown, явная маркировка
  «Ручные часы», режим остановки по rules, не обещать синхронизацию с табло.
  Autosave по действиям; notes debounce500ms без отправки на каждую букву,
  beforeunload предупреждает о pending, хранит и несохранённое состояние открытой формы.
  Attachments загружаются с progress, не кладутся в localStorage; при network error
  пользователь повторно выбирает файл, request-id сохраняется для проверки повтора.
  PublicProtocolPage вызывает только public DTO, без админских методов/ссылок документов.

- [ ] **Step 4: Проверить** пользовательский полный сценарий гол→изменение автора→отмена,
  частичный3:2+дваголa, yellow→second-yellow, submit без минуты, автоgoal, penalty,
  сохранение формы после reload,401/409/422, localStorage quota/invalidJSON,
  retry после lost response, отсутствие автоматического confirm/publish.

```bash
npm --prefix web test
npm --prefix web run build
```

- [ ] **Step 5: Commit** `feat(web): add live manual protocol and recoverable edits`.

### Task 9: Сквозная проверка и запуск первой поставки

**Files:** web/e2e/{tournament-protocol,conflict,retry}.spec.ts,
web/playwright.config.ts, docs/service-stage1.md, service/app.py (только найденные проблемы).

**Interfaces:** запускаемый API `uvicorn aifootball.service.app:create_app --factory`,
build SPA из web/dist; начальный admin CLI, опубликованный protocol URL.

- [ ] **Step 1: Написать E2E сценарий на настоящем backend/PostgreSQL.**

```ts
test('турнир, ручной протокол и опубликованная версия', async ({page}) => {
  await loginAdmin(page);
  await createTournamentWithTeams(page, {name: 'Тестовый кубок', periodMinutes: 20});
  await page.getByRole('button', {name: 'Создать матч'}).click();
  await fillMatch(page, {home: 'Север', away: 'Юг'});
  await page.getByRole('button', {name: 'Сохранить матч'}).click();
  await page.getByRole('button', {name: 'Гол', exact: true}).click();
  await page.getByLabel('Команда события').selectOption('home');
  await page.getByRole('button', {name: 'Сохранить событие'}).click();
  await expect(page.getByText('Известно голов: 1:0')).toBeVisible();
  await finishAndConfirmPartial(page, {score: [1, 0]});
  await page.getByRole('button', {name: 'Опубликовать протокол'}).click();
  const publicUrl = await page.getByRole('link', {name: 'Открыть опубликованный протокол'}).getAttribute('href');
  const guest = await page.context().browser()!.newContext();
  const publicPage = await guest.newPage();
  await publicPage.goto(new URL(publicUrl!, page.url()).href);
  await expect(publicPage.getByText('1:0', {exact: true})).toBeVisible();
  await guest.close();
});
```

  helpers в web/e2e/helpers.ts выполняют UI-действия: loginAdmin вводит login/password
  из тестового env (не реальные secrets); createTournamentWithTeams создаёт tournament,
  two teams и заявки через UI; fillMatch выбирает команды/дату/регламент;
  finishAndConfirmPartial ставит reported score, ended, открывает confirm, отмечает
  acknowledge, подтверждает. Здесь не использовать API для подмены проверяемых UI-действий.
  Setup создаёт отдельный admin/БД сценария; имена тестовых турниров с UUID, без очищения
  пользовательской БД. API для setup допускается только за кадром создания admin.

- [ ] **Step 2: Запустить** `npm --prefix web run test:e2e` и исправить конкретные failures.
  lost-response тест: первый POST пропустить на backend через route.fetch, затем
  abort отдачу ответа; повтор проходит и счёт ровно1. Conflict: два context same user,
  разные команды с одной revision; второй UI сохраняет input и показывает conflict.
  Отдельный регламентный тест меняет 2×20 на2×15, старый матч сохраняет 40min.
  Проверить publish→reopen→исправить: гостю до новой публикации остаётся старый снимок.

- [ ] **Step 3: Написать точный runbook и проверить инструкции на локальном запуске.**

```bash
uv sync --extra dev --extra web --extra web-dev
docker compose up -d db
.venv/bin/alembic upgrade head
.venv/bin/python -m aifootball.service.auth.cli create-admin --login admin
npm --prefix web ci
npm --prefix web run build
.venv/bin/uvicorn aifootball.service.app:create_app --factory --host 127.0.0.1 --port 8000
```

  Runbook объясняет .env (URL psycopg, private dirs, allowed_origin http://127.0.0.1:8000,
  secure_cookies=false только localhost), отдельный Vite dev origin http://127.0.0.1:5173,
  DB readiness и restart без потери данных. create_app фабрика допускает settings=None
  с чтением Settings(), тесты передают explicit settings. Без web/dist GET/ отдаёт
  понятную страницу «Соберите интерфейс», API работает; без DB GET/ready503.
  Backup: pg_dump через compose плюс archive закрытого attachment volume; restore
  только в отдельную чистую тестовую БД, проверить match/public snapshot/attachment.
  Никаких git tracked credentials и chmod публичных data directories.

- [ ] **Step 4: Финальные проверки.**

```bash
.venv/bin/python -m pytest -q
npm --prefix web test
npm --prefix web run build
npm --prefix web run test:e2e
git diff --check
```

  После успешных автоматических проверок открыть приложение в браузере и пройти
 1440px/768px/375px с настоящими данными: создание и редактирование, reload после
  сохранения, отсутствие горизонтального скролла всей страницы, доступность кнопок
  протокола, пустой турнир и ошибки. Открыть private route без входа и public route
  в guest. Зафиксировать фактический вывод/ограничения, не объявлять AI/S3 готовыми.
  Не запускать YOLO на полном матче ради этой поставки; базовые existing tests достаточно.
  Использовать verification-before-completion и выбранный execution skill; требуемый
  ими финальный независимый обзор должен проверить CAS/idempotency/исторические версии.
  Нельзя устранять review failures отключением tests или подменой БД SQLite.

- [ ] **Step 5: Commit** `test(service): verify tournament protocol workflow`;
  оставить готовую локальную ссылку и короткую инструкцию входа (без пароля в chat).
  Не push/merge/deploy без отдельного запроса. Существующие незакоммиченные изменения
  отчёта не должны случайно оказаться в service-коммите.

## Самопроверка плана и покрытие спецификации

| Требование первого этапа | Задачи |
|---|---|
| Приватный кабинет, постоянные данные, восстановление после restart | 1, 7, 9 |
| Все параметры времени/состава/поля/фолов/очков, варианты, версии/override/preview | 2, 3, 7 |
| Постоянные игроки, заявки, match lineups, timezone и календарь | 3, 7 |
| Голы/ассисты/own goals/фолы/карточки/penalties/shootout/замены/паузы | 4, 5, 8 |
| Частичный протокол, неизвестные значения, сверка, технический результат | 4, 5, 8 |
| Ручные часы и периоды без табло/видео | 6, 8 |
| Autosave, потерянный ответ, conflicts, audit, локальный ввод | 3, 5, 8, 9 |
| Документ протокола, notes/referees, подтверждение/исправления/публикация | 3, 5, 8, 9 |
| Desktop и телефон, build, настоящий backend end-to-end | 7–9 |

Поздние уточнения типов из задачи5 (`assist_known`, `public_notes`, `related_events`,
`related_ids`, `server_now_ms`) должны быть включены в initial DTO/миграцию до генерации
OpenAPI; не вводить несовместимые handwritten frontend типы. `assist_known` default=false,
для own_goal=true и отсутствующего ассиста known=true. Публичные заметки отдельны от internal.

Полные требования общей спецификации вне этого этапа перечислены в границах поставки;
импорт расписания, S3/Disk, работник и аналитический отчёт составят план этапа2,
треки/видеособытия/публикация аналитики — этапа3. AI-время/удары исследуются отдельно.
Первый этап принимается без подключения облачных ключей и без обработки видео.

## Проверенные первичные источники

- [FastAPI TestClient](https://fastapi.tiangolo.com/tutorial/testing/) — API-проверки с pytest/httpx.
- [Pydantic models](https://pydantic.dev/docs/validation/latest/concepts/models/) — типизированные входные DTO.
- [SQLAlchemy version counters](https://docs.sqlalchemy.org/en/20/orm/versioning.html) — ограничения ORM-versioning;
  наш агрегат блокируется явно и дополнительно сравнивает expected_revision.
- [PostgreSQL row locks](https://www.postgresql.org/docs/16/explicit-locking.html) — транзакционные блокировки строк.
- [Alembic migration environment](https://alembic.sqlalchemy.org/en/latest/tutorial.html) — управляемая схема БД.
- [React app choices](https://react.dev/learn/creating-a-react-app), [Vite requirements](https://vite.dev/guide/) —
  выбираем клиентский кабинет с существующим Python backend; SSR в первом этапе не требуется.
- [localStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage) — долговременная копия ввода
  с обработкой отказа хранилища; не источник истины и не обещание полной работы без сети.

## Перед выполнением

План подготовлен для обзора. Рекомендованный способ: реализация основным агентом по задачам
с финальным независимым обзором, поскольку API/агрегат/интерфейс тесно связаны и можно
последовательно проверить их на одном локальном приложении. Альтернатива — отдельный
исполнитель и reviewer на каждую задачу. Пользователь выбирает способ после обзора плана;
этот документ сам по себе не означает, что код сервиса уже написан.
