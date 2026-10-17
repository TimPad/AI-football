# Сквозной UX/UI и Excel-заявки — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Use superpowers:subagent-driven-development only if the user chooses delegation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать организатору быстрый и полный путь создания турнира с командами и Excel-заявками, связать повседневное управление и публичный просмотр, добавить подсказки адреса и самостоятельный кабинет капитана.

**Architecture:** Развивать текущие React/FastAPI-экраны и модели каталога, заявок и матчей. Добавить явную видимость турнира, повторяемые команды настройки и серверный предпросмотр Excel; интерфейс мастера использует те же редакторы, что повседневный кабинет. Очередь Админ+ и публичные страницы поставляются отдельно поверх этих контрактов.

**Tech Stack:** React 19, TypeScript, React Router, текущий CSS, FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Alembic, Vitest, Playwright. `.xlsx`-парсер выбрать по официальной документации при реализации и зафиксировать в `uv.lock`.

**Spec:** [Сценарии, правила и критерии](../specs/2026-10-17-tournament-onboarding-and-continuous-ux-design.md).

**Статус:** предложение от 17 октября 2026, дополнено 18 октября; никакой пункт реализации не выполнен. Подтверждены Excel, самостоятельное подтверждение капитаном своей команды и направление главной как календаря с группами турниров. Дополнения карт, капитана и главной оформлены отдельными планами ниже; оценки длительности не делались.

## Global Constraints

- Новые турниры имеют `visibility=draft`; существующие при миграции получают `public`, сохраняя текущие ссылки.
- Публикация страницы турнира не публикует результаты, CV и рейтинги.
- Стабильный UUID определяет личность игрока. ФИО, дата рождения, номер и команда — признаки поиска, но не разрешение на автоматическое объединение.
- По умолчанию импорт **добавляет** игроков, сохраняя тех, кого нет в файле. Замена всего состава и массовое удаление не входят в первую поставку.
- Ручной протокол и CV остаются разными источниками. Connected Processor, OCR, маски, S3, Colab и платные VLM-вызовы не входят в этот UX-проект.
- Миграции только новые. Публичная схема и frontend-типы обновляются вместе.
- Проверки реализации выполняются на синтетических данных в `aifootball_test`, `aifootball_migration_test`, `aifootball_e2e`. Рабочие данные организатора и общий `web/dist` для приёмки не перезаписываются.

## Review Focus

1. Закрытый турнир не читается по прямому public ID протокола, ссылке на CV, рейтинг, статистику, игрока или изображение — задача 1, повторная проверка в задаче 7.
2. Ответ потерян после commit: тот же request ID возвращает прежний результат; изменённое тело даёт 409 — задачи 2 и 3, UI в задаче 4.
3. Два человека с одинаковым ФИО или два номера в разных командах не объединяются; повтор номера внутри одной заявки блокируется — задача 3.
4. Состав/карточка изменились после предпросмотра: 409, ввод сохранён, повторная проверка обязательна; незатронутые заявки и матчи сохраняются — задачи 3 и 4.
5. Excel содержит несколько листов, формулы, даты, ведущие нули, ошибки/пустые строки — предпросмотр объясняет исходную строку и не теряет остальные данные — задачи 3 и 4.

## Карта поставок и файлов

| Задача | Поставка | Основные файлы |
|---|---|---|
| 1. Видимость | A, P0 | `tournaments/{models,schemas,routes}.py`, `public.py`, публичные readers, новая миграция |
| 2. Команды настройки | A, P0 | `tournaments/{commands,schemas,routes}.py`, `catalog/{routes,operations,profiles}.py`, новая миграция |
| 3. Excel backend | A, P0 | новый `service/catalog/roster_imports/`, `config.py`, `app.py`, новая миграция |
| 4. Excel UI и мастер | A, P0 | новые `features/roster-import/`, `TournamentSetup.tsx`, текущие редакторы |
| 5. Удобство кабинета | B, P1 | navigation, tournaments, catalog, matches, общие компоненты |
| 6. Работа Админ+ | C, P1 | analysis, publication, ratings, `TournamentWorkspace.tsx` |
| [7a. Главная — календарь матчей](2026-10-18-public-match-center.md) | D0, P1 | public aggregate дня/upcoming, `features/public/match-center/`, PublicHome, топ-5 из существующего public ratings API |
| 7. Гостевые связи | D1, P1 | `public.py`, публичные views, PublicPages, новые Team/Player pages, Schedule |
| [8. Адрес из карт](2026-10-17-hall-address-suggest.md) | A1, P0 | `halls/address_provider.py`, `address_routes.py`, `AddressField.tsx` |
| [9. Кабинет капитана](2026-10-17-captain-self-service.md) | E1/E2, P1 | `service/captains/`, captain UI, scoped Excel и версии заявок |
| [10. Подтверждение игроков капитаном](2026-10-17-captain-self-service.md#task-4-выдача-капитану-ограниченной-задачи-по-кадрам) | F, P1 | `analysis/team_review/`, независимые подтверждения сторон, captain review UI |

Пути backend относительно `src/aifootball/service/`, frontend — `web/src/`. Указанные новые имена — решения плана; действующие файлы проверены по репозиторию. Номер новой миграции определить по актуальной голове при реализации, не занимать заранее.

## Task 1: Черновик турнира и проверка всех публичных путей

**Files:**
- Modify: `src/aifootball/service/tournaments/{models,schemas,routes}.py`, `src/aifootball/service/views.py`, `src/aifootball/service/public.py`.
- Modify: публичные readers в `protocol/routes.py`, `analysis/{routes,queries}.py`, `ratings/{routes,queries,team_stats}.py` по фактической точке проверки.
- Create: новая Alembic-миграция и `tests/service/test_tournament_visibility.py`.
- Modify: `tests/service/test_public_calendar.py`, `test_public_team_logos.py`, публичные fixtures и `web/src/api/{types,domain}.ts`.

**Interfaces:** `Tournament.visibility: Literal['draft','public']`; create defaults to draft. `PATCH /tournaments/{tid}` принимает видимость с `expected_revision`. Общий guard `require_public_tournament(db: Session, tournament_id: UUID) -> Tournament` доступен всем public readers; для архивного/закрытого турнира 404. Публичный DTO не раскрывает внутренние поля настройки.

- [ ] Написать тесты: новый турнир скрыт в списке и detail; существующий после миграции остаётся public; переключение видимости проверяет ревизию; публикация турнира не изменяет published IDs протокола/CV/рейтинга.
- [ ] Добавить параметризованный тест всех дочерних публичных путей, включая `/public/protocols/{public_id}` и историю игрока по разным турнирам. Если логотип используется также публичной командой другого турнира, он остаётся доступен только по разрешённой публичной связи; фото игрока закрыто.
- [ ] Запустить `.venv/bin/python -m pytest tests/service/test_tournament_visibility.py tests/service/test_migrations.py --tb=line -q`; новые сценарии должны падать до реализации.
- [ ] Добавить поле и миграцию с backfill `public` для существующих строк; для новых записей и ORM, и DB default — `draft`. Применить guard ко всем выявленным public readers, а в истории игрока фильтровать источники по видимости каждого турнира.
- [ ] Обновить публичные fixtures: там, где нужен гостевой доступ, явно опубликовать турнир. Экспортировать OpenAPI, обновить типы; повторить целевые тесты до PASS. Зафиксировать только файлы задачи.

## Task 2: Повторяемые операции настройки и команды на месте

**Files:**
- Create: `src/aifootball/service/tournaments/commands.py`, `tests/service/test_tournament_setup.py`, новая миграция журнала команд.
- Modify: `tournaments/{models,schemas,routes}.py`, `catalog/{schemas,routes,operations,profiles}.py`.

**Interfaces:**
- `POST /tournaments`: дополнить вход `request_id: UUID`; старый клиент без поля получает ID по default, новый мастер всегда передаёт свой. Ответ — текущий `TournamentView`.
- `POST /tournaments/{tid}/regulations`: добавить такой же повторяемый request ID; не создавать новую версию при повторе того же сохранения.
- `POST /tournaments/{tid}/teams`: `CreateTournamentTeam(request_id, team: TeamCreate, expected_tournament_revision)` → `EntryView`; создание команды/людей и заявки в одной транзакции.
- `POST /tournaments/{tid}/entries/batch`: `AddTournamentTeams(request_id, team_ids: list[UUID], expected_tournament_revision)` → список `EntryView`; проверка лимита и предпросмотр подхватываемых составов до отправки.
- Новый журнал `SetupCommand`: request ID, actor ID, тип операции, hash входа, resource ID, response. Проверка архивности и ревизии турнира выполняется внутри транзакции; заявки дополнительно защищены существующими ограничениями уникальности.

- [ ] Написать `test_create_tournament_retry_returns_same_id`, `test_regulation_retry_keeps_one_version`, `test_create_team_entry_is_atomic`, `test_batch_entries_limit_failure_rolls_back`, `test_request_id_reuse_with_changed_body_is_409`.
- [ ] В этих тестах проверить: ответ после искусственно потерянного успешного ответа воспроизводится; при ошибке заявки новые команда/игроки не остаются; команда в архиве недоступна; два вызова с одним ID не создают две записи.
- [ ] Запустить `.venv/bin/python -m pytest tests/service/test_tournament_setup.py --tb=line -q`, убедиться в FAIL новых сценариев.
- [ ] Реализовать команды через текущие доменные проверки. При извлечении `save_profile` отделить управление транзакцией от логики, чтобы одна операция покрывала Team + Player + Entry + EntryPlayer. Старые API не удалять.
- [ ] Экспортировать OpenAPI и типы; запустить новые тесты вместе с `tests/service/test_team_profiles.py`, `test_catalog.py`, `test_regulations.py`. Ожидается PASS; отдельный commit.

## Task 3: Excel-предпросмотр, сопоставление и атомарное применение

**Files:**
- Create: `src/aifootball/service/catalog/roster_imports/{__init__,models,schemas,xlsx,operations,routes}.py`.
- Create: `tests/service/test_roster_imports.py`, `tests/test_roster_xlsx.py`, новая миграция.
- Modify: `src/aifootball/service/{app,config}.py`, `pyproject.toml`, `uv.lock`.

**Interfaces:**
- Scope `team` + target team UUID → постоянный состав; scope `tournament` + target tournament UUID → заявки. Автоматического изменения общих профилей существующих людей нет.
- `GET /roster-imports/template?scope=team|tournament` → синтетический `.xlsx` с заголовками спецификации.
- `POST /roster-imports` (multipart: scope, target_id, file) → `ImportSourceView{id, revision, sheets, expires_at}`. Чтение не создаёт команды/игроков.
- `PUT /roster-imports/{id}/preview`: `ImportPreviewInput{expected_revision, sheet, mapping, edits, decisions, excluded_rows}` → `ImportPreviewView`.
- `GET /roster-imports/{id}` → состояние для продолжения; `DELETE` отменяет неприменённый предпросмотр своего автора.
- `POST /roster-imports/{id}/commit`: `{request_id, expected_revision}` → `ImportResult{teams_created, players_created, players_reused, entries_updated, skipped_rows, links}`.
- `GET /roster-imports/{id}/report` → `.xlsx`-отчёт исходных строк, действий и причин, без исполняемых формул.
- Нормализованная строка хранит sheet/source_row, team_ref, person_ref, name, shirt_number, необязательные параметры, resolution и issues. Решение о существующем UUID явное; для нового UUID закрепляется в preview и не меняется при повторе.
- Предпросмотр хранит actor, scope/target, revision, ограниченные значения/типы исходных ячеек всех листов для смены сопоставления, нормализованные строки и решения, ожидаемые ревизии team/entry/повторно используемых players, last_touched и status. Неактивные неприменённые данные очищаются через 7 дней; минимальный результат применённой команды хранится для повтора. Исходный файл не сохраняется после разбора.

- [ ] Выбрать поддерживаемый `.xlsx`-парсер по официальной документации; зафиксировать зависимость в web extra и `uv.lock`. Использовать безопасный ограниченный разбор: 5 МиБ входа, 25 МиБ распакованных данных, 1 000 непустых строк суммарно по книге, 64 команды на выбранном листе; обрабатывать ячейки формул явно, не использовать их cached result как проверенное значение.
- [ ] До доменной реализации написать parser-тесты с генерируемыми книгами: несколько листов, раздельное ФИО, разные даты, номер `07`, пустые строки, формула в нужной ячейке, повреждённый файл и превышение каждого ограничения. Выход сохраняет исходный номер строки; unsupported `.xls` объясняет сохранение в `.xlsx`.
- [ ] Написать API-тесты: 3 команды/45 игроков; несколько команд с номером 7 разрешены; дубль номера внутри команды запрещён; однофамильцы требуют решения; существующая карточка не затирается; импорт только добавляет; превышение регламента блокирует commit.
- [ ] Дополнить тесты: строка исключается явно; preview не пишет каталог; две команды применяются целиком или никак; изменения после preview дают 409; сбой/повтор commit не дублирует людей; архивность/истечение/чужой author блокируют доступ; другие заявки и подтверждённые матчи сохраняют прежнее содержимое.
- [ ] Запустить `.venv/bin/python -m pytest tests/test_roster_xlsx.py tests/service/test_roster_imports.py --tb=line -q`; убедиться, что новые сценарии FAIL до соответствующих реализаций.
- [ ] Реализовать parser, preview, проверку кандидатов и транзакцию commit с блокировкой затронутых записей и проверкой ревизий. У команды уже в турнире обновлять её заявку добавлением, а не повторно создавать Entry. Использовать `set_roster`/ограничения профиля и новый журнал применения; не обращаться к БД из frontend для обхода API.
- [ ] Добавить очистку неприменённых preview по TTL как локальную служебную команду, доступную операционному запуску без обязательного внешнего планировщика. Выполнить целевые тесты, обновить OpenAPI/типы и документацию сервиса. Отдельный commit после PASS.

## Task 4: Полный пользовательский путь — мастер и общий Excel UI

**Files:**
- Create: `web/src/features/roster-import/{RosterImportPage,ImportMapping,ImportPreview}.tsx`, `types.ts`, `roster-import.css`, тесты компонентов.
- Create: `web/src/features/tournaments/TournamentSetup.tsx`, `TournamentSetup.test.tsx`, `web/e2e/tournament-onboarding.spec.ts`, `roster-import.spec.ts`.
- Modify: `web/src/App.tsx`, `features/tournaments/{TournamentList,TournamentPage,TournamentWorkspace}.tsx`, `features/catalog/{TeamEditor,RosterPage}.tsx`, `components/ui.tsx`.

**Interfaces:**
- `/tournaments/new` — первый шаг. После create расширенный путь → `/tournaments/{id}/setup?step=rules|teams|review`.
- `/roster-imports/{id}` — общий серверный preview; обратно возвращает только проверенный локальный маршрут в scope, а не произвольный `returnTo`.
- `RosterImportLaunch({scope:'team'|'tournament', targetId: string, onCommitted: (result: ImportResult) => void})` используется всеми тремя точками входа.
- `TeamEditor` получает режим встраивания и `onCancel/onSaved`; сценарий команды в турнире отправляет атомарную команду задачи 2. Его существующий standalone route сохраняется.
- Состояние мастера хранит ID турнира и выбранный шаг; фактическая готовность определяется сохранёнными сущностями. Локальные незавершённые поля и request ID привязаны к actor+resource.

- [ ] Написать проверки UI: обе кнопки создания дают один турнир; быстрый путь не требует команд; расширенный остаётся в турнире; закрытие и возврат восстанавливают поля; после timeout повторяет тот же ID/body; 409 сохраняет ввод.
- [ ] Написать проверки импорта: выбор листа, подтверждение столбцов, исправление строки, явный выбор человека, исключение строки, пересчитанный итог, scope-подпись и отключённый commit до устранения ошибок. Возможна полная работа клавиатурой.
- [ ] Запустить `npm --prefix web run test -- TournamentSetup RosterImport` и убедиться в FAIL новых сценариев. Названия фильтров должны соответствовать именам созданных тестовых файлов.
- [ ] Реализовать полноэкранный мастер и импорт с короткими шагами, постоянными «Назад / Сохранить и выйти / Продолжить», раздельными статусами локального и серверного сохранения. Добавить скачивание настоящего `.xlsx`-шаблона из задачи 3.
- [ ] Включить «Выбрать существующие / Создать команду / Загрузить Excel» на шаге команд и в обычной странице команд турнира; на созданной команде оставить ссылку к заявке. Встроенные формы не сбрасывают окружающий контекст.
- [ ] Обновить Modal и новый Drawer: начальный фокус, удержание фокуса, возврат, Escape и проверка dirty. Проверить, что улучшение общего компонента не ломает текущие EventForm/публикацию.
- [ ] E2E на синтетическом `.xlsx`: создать турнир → импортировать две команды → исправить строку → применить → создать первый матч; справочники не открываются. Отдельный E2E: потеря ответа commit, reload и повтор; число UUID неизменно.
- [ ] Запустить целевые Vitest, затем `npm --prefix web run test:e2e -- tournament-onboarding roster-import team-profile`. После PASS поставка A может пройти отдельную приёмку и выпуск. Обновить описание сценария; отдельный commit.

## Task 5: Обзор турнира и повседневный кабинет

**Files:**
- Create: `web/src/features/tournaments/TournamentOverview.tsx`, `features/catalog/TeamPicker.tsx`, `components/Drawer.tsx` при необходимости извлечения из задачи 4; тесты.
- Modify: `features/navigation/{rail.tsx,query.ts,useQueryPatch.ts}`, `features/tournaments/{TournamentWorkspace,TournamentPage}.tsx`, `features/catalog/{RosterPage,TeamEditor}.tsx`, `features/matches/{MatchForms,MatchPage}.tsx`, текущие CSS.
- Create/extend: `web/e2e/tournament-workspace.spec.ts`; `tests/service/test_tournament_setup.py` для агрегированной готовности, если её нельзя вычислить из текущего набора ответов.

**Interfaces:** `TournamentSetupSummary` — сведения, регламент, число команд/заявок, число матчей, visibility, `next_action{label,href,reason}`. UI использует текущие данные workspace; отдельный endpoint добавляется только при доказанной лишней загрузке. URL сохраняет `tab`, `day`, `hall_id`, `status`, `view`, фильтр команды и attention.

- [ ] Проверить модель следующего шага: нет регламента → к регламенту; нет двух команд → к командам; готово → создать матч; публикация страницы явно отдельно. В архиве нет редактирующих действий.
- [ ] Переустроить заявку: текущий состав на первом экране; поиск по людям и добавление нового на месте; основные поля в строке, расширенные в деталях. Подхват постоянного состава показывает сравнение и не сбрасывает уже выбранных игроков.
- [ ] Добавить безопасный возврат к расписанию и сохранение незавершённой формы матча при создании команды/зала на месте; калибровка камеры остаётся дополнительной задачей.
- [ ] В списке матчей показать ясные статусы готовности и переходы к исправлению. Семантику «Есть новая версия» вычислять сравнением опубликованного ID с последней подтверждённой версией, а не только status матча.
- [ ] Добавить E2E: фильтр дня/зала → матч → назад; inline зал → возврат к форме с прежней датой; заявка другого турнира и уже подтверждённый матч остаются прежними.
- [ ] Проверить targeted Vitest/E2E и клавиатуру на 1440/1024/390 px. Готовность — конкретные действия без потери ввода и контекста; отдельный commit поставки B.

## Task 6: Очередь Админ+ и понятная публикация

**Files:**
- Create: `web/src/features/analysis/TournamentAnalysisQueue.tsx`, тесты и `web/e2e/analysis-queue.spec.ts`.
- Modify: `src/aifootball/service/analysis/{routes,queries,schemas}.py`, `web/src/features/tournaments/TournamentWorkspace.tsx`, `features/analysis/{ReviewWorkspace,AnalysisTab}.tsx`, `features/publication/{MatchPublication,publicationModel}.tsx`, `features/ratings/TournamentRatings.tsx`.
- Create/extend: `tests/service/test_analysis_queue.py`, проверки публикации в существующих тестах.

**Interfaces:** `GET /tournaments/{tid}/analysis-queue?status=&offset=&limit=` → `Page[AnalysisQueueItem]`, только analytics reader. Элемент: match_id, team names, scheduled_at, run_id, состояние существующей работы, нерешённые назначения, актуальность источников, next_action. Статусы очереди вычисляются из существующих данных, имеют ясные причины; проценты внешнего процессора не выдумываются.

- [ ] Написать тесты агрегирования и прав: обычный администратор получает 403 на закрытую очередь; Админ+ видит нужные состояния; опубликованная старая версия не делает новую подтверждённой; список не выполняет запрос на каждый матч.
- [ ] Реализовать очередь в контексте турнира, прямой переход в соответствующую задачу/версию и возврат к тем же фильтрам. Отдельную роль «суперадминистратор» не вводить.
- [ ] Расширить существующий экран публикации сравнением «На сайте / Выбрано / Что изменится» для каждого независимого источника. Показывать конкретный блокер и ссылку на исправление; не добавлять общую кнопку, скрыто публикующую все источники.
- [ ] Написать UI/E2E: несохранённые назначения блокируют подтверждение; обычный админ публикует протокол без аналитики; Админ+ публикует выбранную версию CV, не меняя публичный протокол; stale рейтинг требует пересчёта, прежний остаётся виден.
- [ ] Запустить целевые backend/UI/E2E. Экспортировать типы, описать рабочий путь; отдельный commit поставки C.

## Task 7: Публичная команда, игрок и сохранение пути зрителя (D1)

**Files:**
- Modify: `src/aifootball/service/{public,views}.py`; при росте выделить `public/` без изменения действующих URL.
- Create: `tests/service/test_public_team_player_pages.py`, `web/src/features/public/{PublicTeamPage,PublicPlayerPage}.tsx`, компонентные тесты, `web/e2e/public-team-player.spec.ts`.
- Modify: `web/src/{App.tsx,features/public/PublicPages.tsx,features/public/Schedule.tsx,components/match/MatchHeader.tsx,features/public/PublicPlayerHistoryPage.tsx}`, `features/navigation/query.ts`.

**Interfaces:**
- `/watch/tournaments/{tid}/teams/{teamId}` → команда в турнире; API `/public/tournaments/{tid}/teams` и `/public/tournaments/{tid}/teams/{teamId}`.
- API `/public/players/{playerId}?tournament_id={tid}` → разрешённая карточка из опубликованных протоколов этого турнира; текущий `/watch/players/{id}` расширяется, ссылки на историю и `snapshot_id` сохраняются.
- `PublicTeamView`: ID/name/logo, разрешённые участники из опубликованных protocol snapshots, ссылки/ID доступных матчей. `PublicPlayerProfile`: ID, имя из последнего доступного опубликованного снимка, команды и опубликованные выступления. Без импортированных закрытых атрибутов и фотографий.
- Расписание получает `home_team_id/away_team_id`, уже доступные в `PublicMatch`, и командный URL-фильтр; переход на профиль сохраняет локальный безопасный контекст турнира.

- [ ] Написать backend-тесты: команда без опубликованного протокола показывает только публичные сведения и расписание; импортированный roster не раскрывается; игрок без рейтинга, но с опубликованным протоколом открывается; закрытый турнир и приватный snapshot дают 404.
- [ ] Закрепить происхождение имён: переименование общего каталога не переписывает имя в историческом опубликованном протоколе. Для нескольких снимков карточка использует последний по времени публикации; история сохраняет каждый снимок.
- [ ] Реализовать «Команды» в турнире, ссылки из матча/расписания, профиль игрока с доступной историей оценок. Главная и ближайшие игры реализуются отдельно по [плану D0](2026-10-18-public-match-center.md), без второго конкурирующего PublicHome/агрегата. После D1 подключить ссылки команд в строках главной, сохранив календарный контекст.
- [ ] E2E: турнир → команда → матч → игрок без рейтинга → назад; день/зал/команда восстановлены. Дополнительно проверить архив, длинные имена, нулевой опубликованный счёт и отсутствие результата.
- [ ] Запустить новые тесты и текущие `public-calendar`, `public-match-center`, `match-report`, `tournament-ratings`, `public-team-player`. Сверить отсутствие закрытых полей в API, обновить документацию; отдельный commit поставки D1.

## Сквозная приёмка каждой готовой поставки

- [ ] Следовать `CONTRIBUTING.md`: тестовые базы только выделенные, не останавливать чужой сервис на 8181, не перезаписывать общий `web/dist`. Если порт занят, использовать согласованный изолированный тестовый запуск, не очищать его данные вслепую.
- [ ] После изменения API выполнить `.venv/bin/python scripts/export_service_openapi.py --output data/service/openapi.json` и `npm --prefix web run types:api`; сверить отсутствие неожиданного diff типов.
- [ ] Запустить backend/UI-проверки изменённых подсистем, затем полный набор `.venv/bin/python -m pytest --tb=line -q`, `npm --prefix web run test` и сборку в отдельный output, когда основной сервис использует `web/dist`.
- [ ] На подготовленном изолированном E2E-сервисе пройти соответствующую поставке цепочку, роли и ошибки 422/409/network/session expiry. Для финальной общей приёмки — весь E2E-набор.
- [ ] Ручная визуальная проверка в браузере: 1440/1024/390 px; основной экран без обязательной горизонтальной прокрутки; импорт больших составов прокручивается внутри таблицы; фокус и действия доступны клавиатурой.
- [ ] Записать фактические результаты и ограничения в новый документ приёмки; время импорта 15 игроков измерить, ориентир 2 минуты не выдавать за уже достигнутый показатель. Добавить ссылки в `docs/README.md`, выполнить `git diff --check`.

## Граница следующего решения

Первым реализуется A: задачи 1–4. A1 — независимая адресная задача с отдельным [планом](2026-10-17-hall-address-suggest.md). После visibility A новая [главная D0](2026-10-18-public-match-center.md) может выйти первой в клиентской части, не ожидая капитана/профилей D1. E1 даёт капитану регистрацию и собственную команду, F — самостоятельное подтверждение кадров; E2 добавляет согласование турнирной заявки. Подробные задачи и зависимости — в [плане капитана](2026-10-17-captain-self-service.md). B, C, D1 остаются отдельными поставками по задачам 5–7. Перед написанием кода нужно принять оставшиеся предложенные сценарии; этот документ сам по себе не означает разрешения на развёртывание, изменение рабочих данных или публикацию.
