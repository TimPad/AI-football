# Кабинет капитана и самостоятельное подтверждение игроков — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Капитан регистрируется, ведёт свою команду/состав, направляет заявку и самостоятельно подтверждает соответствие кадров игрокам своей стороны.

**Architecture:** Отдельные CaptainAccount/Session и командные grants дополняют текущий административный вход. Капитанские редакторы используют ограниченные контракты команды и общего Excel-импорта. Черновики по кадрам отделены от канонических назначений; самостоятельное captain confirm сохраняет неизменяемую версию стороны и сразу применяет только её patch. Общий технический confirm и публикация остаются раздельными административными командами, без повторного согласования капитанских UUID.

**Tech Stack:** Текущие FastAPI, SQLAlchemy/PostgreSQL/Alembic, Argon2, React/TypeScript, Vitest/Playwright; новый почтовый адаптер с тестовым outbox.

**Spec:** [Регистрация, сценарии, права и обработка кадров](../specs/2026-10-17-captain-self-service-design.md).

**Статус:** проектное предложение; реализация не начата. Пользователь подтвердил: капитан самостоятельно подтверждает свою команду. Зависит от поставки A общего [UX/UI-плана](2026-10-17-tournament-onboarding-and-continuous-ux.md); tasks 1–2 дают E1, task 3 — E2, tasks 4–6 — F.

## Global Constraints

- Карточка человека `Player` со стабильным UUID остаётся отдельной от учётной записи входа.
- Капитан не получает `can_manage_analytics`.
- В первой поставке у команды один активный владелец, помощники и самостоятельная передача капитанства отложены.
- Сохранение черновика капитана не меняет `AnalysisAssignment`, метрики, подтверждение и публикацию. Собственное подтверждение сразу применяет только назначения своей стороны, без принятия Админ+.
- Капитан не объединяет/разделяет исходные группы и не меняет A/B.
- Исходные ZIP, общий закрытый отчёт, произвольные пути файлов и чужая очередь не доступны.
- Подтверждённые версии неизменяемы; изменения — новой версией. Ручной протокол и CV независимы.
- Новые миграции, обновление OpenAPI/типов, lockfile, синтетические fixtures и выделенные тестовые базы обязательны; не трогать рабочие данные и общий `web/dist`.

## Review Focus

1. Подмена team/player/task/run/track ID и старый session после отзыва grant не расширяют доступ — tasks 1, 2, 4.
2. UUID капитана не записывается в текущие FK `admins.id`; общая карточка существующего игрока не меняется чужим владельцем — tasks 1–2, 5.
3. Подтверждение одной стороны не удаляет/откатывает назначения другой; общий confirm не замораживает открытые задачи и проверяет авторство подтверждений — task 5.
4. Новый run, изменённые A/B/группы/снимок состава делают старое задание obsolete; confirmed/public version не меняется — tasks 4–5.
5. Потерянный ответ, двойная отправка заявки, подтверждение стороны или токена не создают дубли; неопределённый кадр остаётся явно неизвестным — tasks 1, 3, 5–6.

## Task 1: Капитанский вход, почта, приглашения и владение

**Files:** Create `src/aifootball/service/captains/{__init__,models,schemas,auth,security,mail,routes}.py`, `tests/service/test_captain_auth.py`, `test_captain_grants.py`; modify `app.py`, `config.py`, `views.py`; новая миграция.

**Interfaces:**
- `CaptainAccount{id,email,password_hash,display_name,verified_at,active}`; `CaptainSession` с отдельным cookie `af_captain_session`, CSRF, expiration; `TeamCaptainGrant{account_id,team_id,active}` с ограничением одного активного владельца на команду.
- `POST /captain/auth/register|verify|login|logout|password-reset|password-reset/complete`, `GET /captain/auth/me`. Обычные admin guards капитанскую сессию не принимают и наоборот.
- `TeamCaptainInvitation{team_id,email,token_hash,expires_at,used_at,revoked_at}` и запрос владения без доступа к закрытым данным; admin endpoints создают/отзывают приглашения и утверждают запросы.
- `MailOutbox` с типом письма и повторяемой доставкой, `MailSender.send(message)`. Токены в БД только hash; секрет доставки в outbox защищён и недоступен обычному UI, не попадает в логи. Политика хранения/очистки после доставки фиксируется в реализации.
- `require_captain_team(db, account, team_id) -> TeamCaptainGrant` вызывается при каждом чтении/изменении, включая выдачу изображений. 404 для чужого ресурса, 403 для отсутствующих прав на известную свою задачу.

- [ ] Написать тесты register/verify/login/reset, одинаковых ответов на reset известного/неизвестного email, rate limit, повторного/истёкшего токена, CSRF и отзыва session после reset.
- [ ] Добавить тесты владения: одинаковое название не даёт чужую команду; expired/revoked invite не работает; другой email не принимает приглашение; один токен не выдаёт два grant; капитанская сессия не открывает admin endpoints; отозванный grant действует сразу.
- [ ] Запустить `.venv/bin/python -m pytest tests/service/test_captain_auth.py tests/service/test_captain_grants.py --tb=line -q`, новые сценарии FAIL до реализации.
- [ ] Реализовать auth на базе текущих Argon2/CSRF/rate-limit подходов без изменения Admin IDs и FK; приглашения 72 ч, verify 24 ч, reset 30 минут. Настроить тестовый sender; email не считать подтверждённым до действительного токена.
- [ ] Подготовить configurable production transport и worker/CLI доставки с повтором; отсутствие транспорта явно блокирует продуктивную саморегистрацию, не выдаёт токен на экране. На этапе тестов внешние письма не отправлять.
- [ ] Выполнить новые и текущие `tests/service/test_auth.py`; обновить OpenAPI/типы. Отдельный commit E1 после PASS.

## Task 2: Своя команда, состав, Excel и предложения профиля

**Files:** Create `captains/teams.py`, `captains/team_routes.py`, `web/src/features/captain/{CaptainAuth,CaptainShell,CaptainTeamPage}.tsx`, tests; modify `App.tsx`, общий `features/catalog/TeamEditor.tsx` и `features/roster-import/` из поставки A; extend backend import actor/model.

**Interfaces:** `GET /captain/teams`, `POST /captain/teams`, `GET|PUT /captain/teams/{team_id}`. Создание: `{request_id,expected_revision?,team_fields,players}` → team view + grant атомарно. Существующие player UUID только из разрешённой команды; глобальные person edits запрещены, отдельный `PlayerProfileProposal` передаётся организатору. Импорт принимает `ActorRef{kind:'admin'|'captain',id}` и проверяет scope/target; обычный captain scope только team. Idempotency ledger хранит kind+ID, не капитанский ID в admin FK.

- [ ] Написать тесты создания команды+владельца атомарно, retry/changed body, лимитов, чужого team ID, неизвестного player UUID, отсутствия глобального списка людей. Передача поля `can_manage_analytics` или чужого owner ID отклоняется схемой.
- [ ] Проверить импорт: капитан получает только совпадения из разрешённой команды; коллизия за пределами scope становится обращением организатору без раскрытия человека; совпадающее имя не объединяет UUID; изменение общей карточки только proposal; существующие заявки/матчи не переписываются.
- [ ] Реализовать ограниченный backend-фасад поверх сохранения команды. Не вызывать текущий `save_profile` с произвольными person edits от капитана; разрешённые поля и их влияние проверять до транзакции.
- [ ] Реализовать регистрацию/вход, переключатель своих команд, общую форму и Excel с сохранением контекста. Новая учётная запись сразу после создания команды видит следующий шаг «Добавить игроков».
- [ ] Запустить целевые backend/Vitest и E2E `web/e2e/captain-team.spec.ts`: verify через тестовый outbox → новая команда → Excel → reload → те же UUID. Зафиксировать E1 отдельным commit.

## Task 3: Версии заявок и согласование с организатором

**Files:** Create `captains/entries.py`, `captains/entry_routes.py`, новые модели `EntrySubmission/EntrySubmissionVersion/EntryInvitation`, `tests/service/test_captain_entries.py`, `features/captain/CaptainEntryPage.tsx`, тесты; extend admin tournament teams page; новая миграция.

**Interfaces:** `POST /captain/tournaments/{tid}/applications`, `PUT /captain/applications/{id}/draft`, `POST /captain/applications/{id}/submit`, admin `POST /tournaments/{tid}/applications/{id}/accept|request-changes`; всё с request ID и expected revision. Версия содержит UUID, номера, source roster revision и список изменений. До принятия Entry отсутствует; если уже существует, принятие обновляет только соответствующую заявку через `set_roster`.

- [ ] Написать тесты: заявка на public/open tournament и admin invitation; consent обеих сторон; повтор одного submit/accept; архив/закрытая подача/лимит/дубль номера; изменение постоянного состава не меняет отправленную версию; существующий Entry не дублируется.
- [ ] Добавить настройку подачи `applications_open` и optional deadline с ревизией турнира: по умолчанию открыто до явного закрытия. Captain не видит закрытые турниры без действительного приглашения.
- [ ] Реализовать самостоятельный application и приглашение организатора в едином автомате; сохранённые версии неизменяемы, исправление — новая draft/version. Принятие создаёт/обновляет Entry+EntryPlayer атомарно и не меняет состав уже созданного матча.
- [ ] UI показывает разницу текущего состава и отправленной заявки, причины возврата, статус и срок. Организатор видит входящие заявки рядом с командами турнира.
- [ ] Выполнить backend/UI и `web/e2e/captain-entry.spec.ts`; проверить интеграцию с текущими каталогом/лимитами/составами. Зафиксировать E2 отдельным commit.

## Task 4: Выдача капитану ограниченной задачи по кадрам

**Files:** Create `src/aifootball/service/analysis/team_review/{__init__,models,schemas,queries,routes}.py`, `tests/service/test_team_identity_tasks.py`, новая миграция; modify `app.py`, `analysis/{models,commands}.py`, admin analysis queue и review UI.

**Interfaces:**
- `TeamIdentityReviewTask{id,team_id,run_id,side,allowed_track_ids,allowed_player_ids,group_fingerprint,context_hash,own_assignment_fingerprint,status,revision}`.
- `AnalysisRun.identity_workflow: admin|team`; первое капитанское task включает team workflow, `reviews` наследует его и создаёт состояния сторон «Требуется подтверждение», даже до выдачи новых задач. Исторические версии не получают чужое новое авторство.
- Admin+ `POST /matches/{mid}/analysis/runs/{rid}/team-review-tasks` с `{team_id,request_id,expected_run_revision}`; предварительно подтверждён side_map, grant команды и доступные материалы. Задание не создаётся на confirmed run.
- Captain `GET /captain/identity-tasks`, `GET /captain/identity-tasks/{task_id}`, `GET /captain/identity-tasks/{task_id}/tracks/{track_id}/thumbnail` — только scoped DTO, no-store; сервер выводит путь изображения из task+run, произвольного file path нет.

- [ ] Написать тесты: не verified A/B блокирует выдачу; доступны только своя сторона/снимок состава; подмена team/run/track и отозванный grant дают отказ; ZIP/общие report endpoints остаются закрыты; отсутствующая миниатюра даёт честное пустое состояние.
- [ ] Реализовать создание task как снимка разрешённых групп и материала существующего импортированного run. Капитан видит свой team UUID/имена, а внутренние A/B остаются административной настройкой.
- [ ] При смене run/context/side_map/groups помечать задачи obsolete либо вычислять это при каждом обращении; старые материалы по obsolete/revoked task недоступны. Изменения только назначений другой стороны не отзывают задачу автоматически.
- [ ] Дать Админ+ статусы сторон «Не выдано / У капитана / Команда подтверждена / Нужны исправления материала / Задание устарело». Нет капитана — Админ+ подтверждает сторону со своим авторством и причиной; открытая задача явно отзывается с сохранением draft.
- [ ] Запустить целевые backend/UI и проверки текущих analysis assignments. Обновить OpenAPI; отдельный commit F.

## Task 5: Самостоятельное подтверждение стороны и общий технический confirm

**Files:** Create `analysis/team_review/confirmations.py`, `tests/service/test_team_identity_confirmations.py`; extend `models/schemas/routes`; modify `analysis/commands.py`, admin review UI и доменную валидацию `analysis/assignments.py` без ослабления ограничений.

**Interfaces:** Captain `PUT /captain/identity-tasks/{id}/draft` сохраняет draft; `POST /.../confirm` возвращает `TeamIdentityConfirmation` и атомарно применяет patch стороны; `POST /.../corrections` создаёт новый draft, прежняя версия действует до нового confirm. Все команды с task/draft revision и request ID. Решения: player UUID из allowlist, explicit_unknown+reason либо material issue (mixed_group/wrong_team/more_frames). Для каждой карточки требуется решение; material issue блокирует confirm до исправления. Отдельный admin endpoint подтверждает сторону вместо отсутствующего капитана с причиной и своим actor. `TeamIdentityConfirmation{task_id,version,actor_kind,actor_id,assignments,unknowns,source_fingerprint,confirmed_at}` неизменяем. Этапа accept/reject для капитанских назначений нет.

- [ ] Написать тесты: draft не меняет AnalysisAssignment; captain confirm сразу меняет свою сторону без admin-команды, создаёт одну неизменяемую версию и не меняет метрики/published IDs. Несовместимый UUID/дублирующий track/старый draft revision отвергается; explicit_unknown не превращается в UUID; material issue блокирует confirm; retry/changed body сохраняют идемпотентность.
- [ ] Проверить scoped merge под блокировкой run: перечитать полный набор; patch своей стороны сливается с актуальными чужими. Изменения соперника допускаются и сохраняются; конфликт тех же треков требует preview. Капитан не передаёт глобальный payload в `set_assignments` и не получает admin actor.
- [ ] Добавить тесты overlap с текущим `OVERLAP_S`, изменений side_map/group/context/run, независимых подтверждений двух капитанов, отзыва grant, исправления подтверждённой стороны новой ревизией. Прежний confirmation неизменяем, публичная версия не меняется.
- [ ] Запустить `.venv/bin/python -m pytest tests/service/test_team_identity_confirmations.py --tb=line -q`; новые сценарии FAIL до реализации.
- [ ] Реализовать `TeamIdentityConfirmation` и captain-scoped транзакцию. Admin FK в AnalysisCommand/AnalysisRun/автоверсиях рейтингов сохраняются: captain confirm пишет отдельный журнал и обновляет только назначения/ревизию draft run. Общая административная команда позже создаёт метрики и автоисточники своим actor; автоматически public IDs не меняются.
- [ ] Усилить общий `mutate(...,'confirm')` для team workflow: назначения совпадают с последними действительными подтверждениями обеих сторон, нет открытых задач/черновиков исправления. Если Админ+ изменил треки капитана, подтверждение становится obsolete; нужно новое captain confirm либо явное admin side confirmation с причиной. Открытая задача второй стороны блокирует заморозку run до завершения или явного отзыва с сохранением draft и admin side confirmation. Legacy-путь разрешён только admin workflow без капитанского процесса в source lineage. Тест `reviews → изменить UUID → confirm` без новых подтверждений должен давать 409, даже если task ещё не выданы.
- [ ] Для исправления личности при неизменном job/context использовать существующую `reviews` и новое task. Для отсутствующего в snapshot игрока: сохранить explicit_unknown; исправление состава требует нового processing job и повторного импорта, одного `reviews` недостаточно. Добавить тест этого пути, чтобы нельзя было выдать старый context за исправленный.
- [ ] Выполнить новые тесты, `test_analysis_assignments.py`, `test_analysis_versions.py`, `test_auto_rating_sources.py`; отдельный commit после PASS.

## Task 6: Рабочее место капитана и сквозная приёмка

**Files:** Create `web/src/features/captain/{CaptainHome,CaptainIdentityReview}.tsx`, тесты, `web/e2e/captain-identity.spec.ts`; modify admin review/queue UI и навигацию гостевого сайта.

**Interfaces:** Секции «Команда / Состав / Турниры и матчи / Проверка игроков». Review URL `/captain/identity-tasks/{taskId}?candidate=...&filter=...`; общий компонент кандидата переиспользует отображение thumbnail и UUID picker, без административных действий/DTO.

- [ ] Написать UI-тесты: кандидат → человек из snapshot roster; одно назначение на группу; «Не определён» и комментарии; draft после reload; «Подтвердить игроков своей команды» сразу даёт team_confirmed; неизвестные явно посчитаны, material issues видны; конфликт сохраняет ввод и показывает отличия.
- [ ] Реализовать карточки с кадрами, временем записи и прогрессом «Определено N из M». Не показывать вымышленный видеоплеер/проценты внешней обработки. На телефоне крупный кадр и короткий выбор человека, действия доступны клавиатурой.
- [ ] E2E на двух синтетических капитанах: Admin+ выдаёт задачи → каждый капитан независимо назначает и сам подтверждает свою команду → обе стороны готовы → Admin+ технически подтверждает run → публикует отдельно. Промежуточного принятия капитанских UUID нет; до публикации гостевая статистика не меняется.
- [ ] Негативные E2E: прямой URL чужой задачи/картинки, отзыв прав при открытой вкладке, новый run, нет кадров, истёкшая сессия, network timeout и повтор side confirm; общий confirm не замораживает работу второго капитана.
- [ ] Выполнить целевые проверки, затем общие backend/UI/E2E по CONTRIBUTING, сборку отдельно от рабочего `web/dist`, `git diff --check`. Email/live deployment проверять отдельно от fake-тестов; записать фактические ограничения и обновить `docs/README.md`.

## Зафиксированная граница самостоятельности

Капитан самостоятельно подтверждает свою сторону — это решение пользователя. Админ+ не принимает эти UUID повторно: он отвечает за техническое подтверждение целого run и отдельную публикацию. Остальные продуктовые defaults помечены в спецификации. Автоматическая финализация run и публикация по капитанскому нажатию в этот план не входят.
