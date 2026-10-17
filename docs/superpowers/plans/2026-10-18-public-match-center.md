# Главная с календарём и группами турниров — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить стартовый каталог турниров общим календарём матчей, сгруппированных по турнирам, с ближайшими играми и лидерами опубликованного рейтинга выбранного турнира.

**Architecture:** Добавить публичные агрегаты дня и будущих матчей на существующих PublicMatch/проекциях. Новый PublicHome хранит календарь/фильтры в URL, показывает группы и отдельный ограниченный upcoming-блок; текущие страницы турнира/матча сохраняются.

**Tech Stack:** Текущие FastAPI/Pydantic/SQLAlchemy/PostgreSQL, React/TypeScript/Router, CSS tokens, Vitest/Playwright.

**Spec:** [Сценарий главной, референс и ограничения](../specs/2026-10-18-public-match-center-design.md).

**Статус:** предложение от 18 октября 2026; реализация не начата. Поставка D0 из общего UX/UI-проекта, после visibility A; профили команд/игроков — следующая D1.

## Global Constraints

- `/` и `/watch` открывают один центр матчей; без даты выбран текущий день Europe/Moscow.
- «Идут» использует существующий статус организатора; счёт — только из опубликованного протокола. Live-счёт и игровая минута не обещаются.
- Скрытый/архивный турнир не попадает в items, total, group counts, поиск и upcoming.
- Ближайшие — до 3 scheduled-игр на 14 дней от серверного now; учитывают турнир/команду/поиск и не зависят от выбранной даты/статуса списка.
- Группы по UUID турнира, порядок по названию без регистра/UUID; матчи внутри по scheduled_at/UUID.
- Лидеры — до 5 qualified-игроков только одного текущего публичного издания турнира. Порядок/места/пороги существующей методики, никакого смешения турниров или нового расчёта; ссылки фиксируют snapshot_id.
- Старые ссылки матча/турнира сохраняются; ручной протокол и CV независимы, опубликованные версии не меняются.
- Миграции только новые; обычные тесты на синтетических данных и выделенных БД, работающий сервис/общий `web/dist` не перезаписывать.

## Review Focus

1. Внешне совпадающие названия турниров не склеиваются, группа корректно продолжается на второй странице — tasks 1–2.
2. Матч около полуночи относится к одному московскому дню вне зависимости от timezone турнира — task 1.
3. Черновой счёт/live clock и закрытые турниры не попадают ни в строки, ни в счётчики/поиск/ближайшие — task 1.
4. Ответ старого дня не заменяет новый, смена фильтра сбрасывает cursor, возврат восстанавливает контекст — task 2.
5. Пустой исторический день остаётся выбранным; ближайшие обозначены отдельно и не изменяют список скрыто — tasks 2–3.
6. Неопубликованное издание и предварительный игрок не попадают в топ; равные места и переходы сохраняют snapshot, переключение турнира не показывает старых лидеров — tasks 1–3.

## Task 1: Публичная выдача дня и ближайших игр

**Files:** Modify `src/aifootball/service/public.py`, `views.py`; create `tests/service/test_public_match_center.py`; extend `tests/service/test_public_calendar.py`; update OpenAPI и `web/src/api/{types,domain}.ts`. При необходимости вынести общую query-логику из public.py в отдельный `public_queries.py`, сохранив URL.

**Interfaces:**
- `GET /public/matches?day=YYYY-MM-DD&status=all|live|upcoming|finished&tournament_id=&team_id=&q=&limit=50&cursor=` → `PublicMatchDayPage{day,timezone,generated_at,items:list[PublicMatch],total,next_cursor,tournament_totals}`.
- `GET /public/matches/upcoming?tournament_id=&team_id=&q=&limit=3` → `PublicUpcomingMatches{timezone,generated_at,items:list[PublicMatch]}`. Зарегистрировать раньше UUID detail route.
- `GET /public/tournaments?q=&limit=&offset=` расширяет существующий поиск для выбора. Все входные UUID/дата/длина строки/limit валидируются; cursor относится к конкретному набору фильтров, чужой cursor даёт 422.

- [ ] Написать `test_day_groups_across_tournaments`, `test_moscow_midnight_boundary`, `test_same_name_tournaments_stay_distinct`, `test_only_published_score`, `test_hidden_tournament_excluded_from_counts_and_upcoming`, `test_live_status_does_not_expose_clock`, `test_upcoming_uses_server_now`.
- [ ] Добавить проверки 120 матчей/продолжения группы: каждая запись встречается один раз, сортировка стабильна, total группы больше загруженного фрагмента. При изменении фильтров старый cursor отвергается. Проверить отмены/переносы, 0:0, q по команде/турниру и пределы запроса.
- [ ] Запустить `.venv/bin/python -m pytest tests/service/test_public_match_center.py --tb=line -q`; новые сценарии должны FAIL до реализации.
- [ ] Реализовать общий query поверх текущих `match_query`/`match_view` и visibility A. Day-окно — Moscow midnight/следующая midnight в UTC; `upcoming` исключает прошедшие scheduled и берёт только будущие в пределах 14 дней. No N+1: единый join и ограниченные aggregate queries.
- [ ] Согласовать cursor-order с выражением сортировки групп; total считать под теми же фильтрами. `tournament_totals` содержит UUID→полное число совпавших матчей до cursor/limit только для групп текущей страницы. Main upcoming — scheduled с началом не раньше серверного now, live — live, finished — ended. Не выгружать все сезоны в браузер. Проверить query plan; индексы добавлять только новой миграцией при необходимости.
- [ ] В текущих public ratings tests закрепить для виджета: `qualification=qualified&limit=5` даёт канонический топ, tied ranks сохраняются, snapshot_id/published_at согласованы, приватный новый snapshot не заменяет публичный, закрытый турнир недоступен. Новую методику и endpoint не добавлять.
- [ ] Запустить новые и текущие public-calendar/visibility/ratings-тесты до PASS. Экспортировать OpenAPI и типы, зафиксировать задачу отдельным commit.

## Task 2: Главная, календарь, группы и ближайшие карточки

**Files:** Create `web/src/features/public/match-center/{PublicMatchCenter,DateNavigation,TournamentMatchGroup,UpcomingMatches,TournamentFilter,TournamentLeaders}.tsx`, `match-center.css`, компонентные тесты; modify `features/public/PublicPages.tsx`, `features/navigation/{PublicShell.tsx,query.ts}`, `App.tsx`. Общую строку матча извлечь из `Schedule.tsx` только если это не меняет её турнирное поведение.

**Interfaces:** `PublicHome` делегирует `PublicMatchCenter`; текущий каталог доступен через `/watch/tournaments` с сохранением `/watch/tournaments/:id`. `DateNavigation({day,onDayChange})`; `TournamentMatchGroup({tournament,total,items})`; `UpcomingMatches({items,onShowDay})`. Основные фильтры только через `useQueryPatch`, пагинация сбрасывается при их изменении.

`TournamentLeaders({tournamentId,onTournamentChange})` читает существующий `/public/tournaments/{tid}/ratings?qualification=qualified&limit=5&offset=0`. Если общий tournament_id выбран, он приоритетен; иначе leaders_tournament_id из URL, иначе первая загруженная группа. При отсутствии всех трёх — выбор турнира, без случайного fallback. Свой выбор не меняется при pagination; ссылки `/watch/tournaments/{tid}?tab=ratings&snapshot_id=...` и `/watch/players/{pid}?tournament_id=...&snapshot_id=...` используют то же издание.

- [ ] Написать тесты текущего дня с mock time, смены месяца, «Сегодня», фильтров и q, двух групп с одинаковым названием, раскрытия групп и pagination merge. Прогресс загрузки не показывает старые матчи под новой датой.
- [ ] Написать тесты upcoming: историческая дата списка не меняет набор ближайших; выбор турнира/команды меняет оба запроса; «Показать этот день» сохраняет поиск и сбрасывает статус на all; ошибка блока не скрывает основной список.
- [ ] Написать `TournamentLeaders` tests: выбор турнира и приоритет общего фильтра, сохранение leaders_tournament_id при смене дня и догрузке, один запрос вместо N запросов по группам, stale response, до 5 qualified, сохранённые tied ranks, unpublished/empty/error, snapshot в обеих ссылках. Поиск/команда/дата не сужают рейтинг всего турнира.
- [ ] Запустить `npm --prefix web run test -- PublicMatchCenter DateNavigation TournamentMatchGroup UpcomingMatches`, убедиться в FAIL новых сценариев.
- [ ] Реализовать основной экран без большого intro: левая навигация турниров, центральная лента дат+группы, справа ближайшие. Зоны 1440/1024/390 px по спецификации; на мобильном upcoming по умолчанию компактно свёрнут.
- [ ] Под ближайшими на desktop разместить один блок лидеров: место/имя/команда/оценка/число оценённых матчей, выбор турнира, «Весь рейтинг», дата публикации и «Пилотный рейтинг». На tablet/mobile — после календарного списка, свёрнут по умолчанию. Использовать готовый public DTO/правила формата, не грузить частные фото или общую административную сводку.
- [ ] Использовать существующие логотипы и правила опубликованного счёта. У live подписать значение «Опубликованный счёт», не выводить private clock/производную игровую минуту. До D1 не показывать неработающие ссылки профиля команды.
- [ ] Отменять старые запросы или проверять их ключ; сохранять фильтры при ошибках и возврате. Обновлять чтения при возврате во вкладку/кнопке, без фоновой live-подписки; показывать время успешного получения.
- [ ] Пройти targeted Vitest и существующие Schedule/PublicMatchPage tests до PASS, сборку в отдельный output. Отдельный commit.

## Task 3: Сквозная приёмка публичного пути

**Files:** Create `web/e2e/public-match-center.spec.ts`; extend `web/e2e/public-calendar.spec.ts`; update `docs/README.md`, новый документ приёмки.

- [ ] E2E: открыть `/` → сегодня, выбрать другой день → группы двух турниров → открыть матч → назад → прежние фильтры и scroll. Каталог турниров остаётся доступен отдельно.
- [ ] E2E: пустой день → ближайшая карточка → «Показать этот день»; 0:0 отличается от неопубликованного результата; закрытый турнир отсутствует в поиске и счётчиках; пагинация не дублирует группу/матчи.
- [ ] E2E с двумя опубликованными рейтингами: выбрать турнир → его лидеры → полный рейтинг/игрок в том же snapshot → назад. Новый приватный расчёт не меняет виджет; unpublished и отсутствие qualified имеют разные честные состояния. На телефоне лидеры не отодвигают матчи.
- [ ] Проверить 1440/1024/390 px, длинные названия, клавиатуру/фокус, loading/empty/error/retry, смену суток и запоздалые ответы. На телефоне нет горизонтальной прокрутки всей страницы.
- [ ] Выполнить целевые backend/UI/E2E, обновление типов и `git diff --check`; тестовый запуск по CONTRIBUTING без очистки рабочей базы/пересборки общего dist. Результаты отличать от обещаний live-сервиса.
- [ ] Записать фактические результаты, ссылку на референс и оставшиеся D1/P2-этапы. Не объявлять реализацию завершённой только по готовому плану.
