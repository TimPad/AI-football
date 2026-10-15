# Match-centered UX/UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Пересобрать desktop-путь зрителя и организатора вокруг матча: расписание → матч → игрок → история, подготовка → протокол/проверка → независимая публикация.

**Architecture:** Сохранить FastAPI/Postgres и существующие команды, добавить два read-only контракта и поля публичной шапки. Разделить загрузчики public/private, представление отчёта и редакторы; общие React-компоненты получают разрешённые данные с отдельными указателями протокола, CV и рейтинга. В кабинете одна навигация задач, отдельные владельцы существующих черновиков и очередей; экран публикации координирует отдельные операции.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Postgres, Alembic; React 19, TypeScript, React Router 7, Vite, CSS, lucide-react; pytest, Vitest/Testing Library, Playwright. Зависимости из `uv.lock` и `web/package-lock.json`, без нового UI-фреймворка.

**Spec:** [Согласованная спецификация](../specs/2026-10-15-match-centered-ux-ui-design.md). [Исследование](../../2026-10-15-ux-ui-reference-audit.md). Пользователь согласовал спецификацию 15 октября 2026. Этот план и визуальная концепция перед реализацией проходят пользовательскую проверку.

## Global Constraints

Следующие требования цитируют спецификацию; дополнительные подробности обязательны в соответствующих разделах spec.

- «Пользователь выбрал приоритет компьютера для обоих сценариев».
- «Публичное содержимое: max-width 1440px, поля 24–32px».
- «Кабинет: навигация 224px; рабочая область занимает остаток».
- «На ширине от 1440px проверка имеет три области — очередь 240px, центральный материал не менее 420px, инспектор 300px».
- «На 1024–1439px очередь открывается из отдельной кнопки/панели, материал и инспектор используют две колонки».
- «Одна шкала типографики и отступов: основной текст 14–16px, подписи 12–13px, заголовки 20/28px; числовые показатели используют tabular-nums».
- «Счёт приходит только из опубликованного протокола».
- «Все опубликованные roster/metric/rating записи относятся к стабильному UUID».
- «Карточка старой оценки не подставляет новую карту как будто она входила в расчёт».
- «Смена периода не пересчитывает матчевую оценку и не переименовывает её в оценку тайма».
- «Командные карты выбранного периода используют общую шкалу максимумов обоих массивов, с числовыми значениями в секундах».
- «Ячейки с нулём не выглядят как горячие области. При отсутствии наблюдений карта не строится».
- «В первой поставке нет визуального сглаживания, которое могло бы скрыть пропуски».
- «Неполный CV не блокирует публикацию допустимого ручного протокола».
- «Просмотр отчёта и предпросмотр публикации не создают второй экземпляр этой очереди и не перехватывают управление».
- «Фильтрация и пагинация меняют только видимость строк».
- «Подтверждённые версии сохраняются» — также требование AGENTS.md.
- «Недоступный по роли запрос не выполняется только потому, что используется общий компонент».
- «GET ничего не создаёт/не подтверждает; PUT сохраняет существующие проверки и request idempotency».
- «Ответ предыдущего match/run не подставляется после смены контекста».
- «Lost response / 409» → «Черновик и request_id сохраняются; повтор либо сверка без двойной записи».
- «ordinary tests используют синтетические данные и выделенные БД».
- «Старый Python-renderer не используется как iframe внутри нового сервиса».

Схема БД не меняется по плану. Не редактировать миграции 0010–0013; если новое сохраняемое поле окажется необходимо, оформить отдельную новую миграцию. Не изменять спортивную методику, веса, источники времени и расчёт чисел. Не добавлять публичные фотографии/полные биографии, standings/playoffs, командные суммы действий, xG/xT, удалённый процессор, S3, OCR или GPU-телеметрию.

## Review Focus

1. Вошедший Админ+ открывает гостевой экран: он должен работать и в чистой гостевой сессии; приватные запросы/изображения исключены. Логотип, также связанный с `Player.photo_id`, не становится публичной фотографией. Тесты Task 2 и 6.
2. Историческое издание A + текущая CV-версия B + одинаковый UUID/изменившийся номер: факты A сохраняются, карта B не выдаётся за источник A; поздний ответ A не замещает новый контекст. Тесты Task 4 и 6.
3. В очереди 51 трек: назначение скрытой строки, смена фильтра/страницы/run не обрезают полный PUT и не переносят черновик между версиями. Тесты Task 9.
4. Ответ команды потерян, затем пользователь переходит между протоколом, отчётом и публикацией: один владелец очереди, тот же request_id/тело при повторе; 409/повреждённый ввод не стираются. Тесты Task 8 и 10.
5. Новый job при старом импортированном результате и разные ревизии матча/публикации/турнира: готовность относится к своему job; publication GET возвращает ревизию турнира без INSERT/UPDATE. Тесты Task 3 и 9.

---

## Проверенное исходное состояние и последовательность

Ветка `codex/ux-ui-redesign`, кодовая база `07944e8`, согласованная спецификация `c45131b`. Внешнее изменение `AGENTS.md` не включать в коммиты этой работы. Не перезапускать и не очищать рабочий сервис/БД организатора на 8000 ради тестов.

`RunSummary.job_id` уже есть в Python, `run_summary()` и TypeScript. Расширение этого поля не требуется: Task 3 фиксирует контракт тестом, Task 9 использует его в UI. Реальные изменения API: четыре поля `PublicMatch`, ограниченная выдача логотипов, publication GET. Новые команды обработки/публикации не вводятся.

Зависимости: 1 → 5; 2 + 3 → 4; 4 + 5 → 6; 5 → 7; 3 + 5 → 8 → 9; 3 + 4 + 8 → 10; 6–10 → 11. Выполнять по порядку: backend тесты используют одну выделенную БД и не запускаются одновременно. Tasks 2–3 можно проверять до принятия визуальных деталей, но продуктовую реализацию начинать после проверки этого плана.

## Карта файлов и интерфейсов

| Файлы | Ответственность |
|---|---|
| `docs/design/2026-10-15-ui-system.md` | Принятые изображения, точные copy/tokens/геометрия/состояния и отклонения |
| `service/public.py`, `service/views.py` | Публичная шапка и только связанный видимый логотип |
| `service/ratings/queries.py`, `routes.py` | Чтение разрешённых версий и ревизии турнира без мутаций |
| `web/src/components/match/MatchHeader.tsx`, `SectionNavigation.tsx`, `SourceStatus.tsx`, `PlayerInspector.tsx` | Общие элементы, без собственных HTTP-запросов/редакторов |
| `web/src/components/pitch/PitchMap.tsx`, `heatmap.ts`, `pitch.css` | Геометрия, несглаженная карта секунд, легенда/масштаб |
| `web/src/features/match-report/model.ts`, `adapters.ts`, `MatchReport.tsx`, `PlayerTable.tsx`, `TeamComparison.tsx`, `report.css` | Контекст источников и представление чтения |
| `web/src/features/public/matchLoader.ts`, `PublicMatchPage.tsx`, `PublicPlayerHistoryPage.tsx`, `Broadcast.tsx` | Только public HTTP, независимые состояния и URL-контекст |
| `web/src/features/navigation/query.ts`, `CabinetShell.tsx`, `PublicShell.tsx`, `shell.css` | Параметры URL, оболочки и сохранение турнира |
| `web/src/features/tournaments/TournamentWorkspace.tsx`, `TournamentPublicationList.tsx` | Навигация турнира, существующие справочники/сводки |
| `web/src/features/matches/MatchWorkspace.tsx`, `MatchOverview.tsx` | Одна глубина задач и обзор готовности |
| `web/src/features/protocol/ProtocolSession.tsx`, `ProtocolMode.tsx` | Один экземпляр редакторской очереди и режим ввода |
| `web/src/features/analysis/ReviewWorkspace.tsx`, `reviewQueue.ts`, `JobStatus.tsx`, `review.css` | Выбор материала, фильтр/пагинация, инспектор, фактические статусы |
| `web/src/features/publication/MatchPublication.tsx`, `publicationModel.ts`, `GuestPreview.tsx` | Независимые публикационные операции и read-only preview |
| `web/src/styles/tokens.css`, `controls.css` | Единые переменные, типографика, фокус и элементы форм |
| Соответствующие `*.test.ts[x]`, `tests/service/test_public_*.py`, `test_performance_publication_read.py`, `web/e2e/match-workspace.spec.ts` | Контракты/состояния/сквозные сценарии на synthetic |

В таблице пути `service/…` относительны `src/aifootball/`; во всех задачах сокращённые пути `features/…` относительны `web/src/`. Не раскладывать существующий каталог/редакторы по новой архитектуре без необходимости: извлекать только затронутые области. Старые импорты из `PublicPages.tsx`, `AnalysisTab.tsx`, `RatingWorkbench.tsx` временно сохранять экспортами адаптеров, затем удалять только неиспользуемые ветви.

Общие типы задаёт Task 4. Backend DTO остаются сгенерированными в `web/src/api/types.ts`, domain aliases — `web/src/api/domain.ts`. Видимые подписи русские; внутренние ключи — только в подробностях источника.

### Task 1: Принять визуальную систему четырёх основных экранов

Состояние подготовки: четыре изображения показаны; матч и календарь исправлены, проверка и публикация остаются черновиками с явными корректировками в [визуальной системе](../../design/2026-10-15-ui-system.md). Повторная генерация этих двух экранов завершилась сетевой ошибкой. Ревью 15 октября нашло дополнительные ошибки и в «исправленных» экранах (непропорциональная шкала календаря, легенда карты другого цвета, нейтральный факт как положительная причина оценки) — список в разделе «Правки по ревью» визуальной системы. Вместо повторной генерации `review` и `publication` собраны HTML-прототипами (см. визуальную систему). **Design lock принят пользователем 15 октября 2026.**

**Files:** Create `docs/design/2026-10-15-ui-system.md`; concept PNG хранятся локально вне Git, документ содержит brief/стабильную копию принятого референса в локальном workspace. Никакие кадры настоящих участников в концепции не используются.

**Interfaces:** Consumes: spec §§4–14. Produces: четыре согласованных референса `public-match`, `calendar`, `review`, `publication`; таблицы copy/tokens/component variants и адаптивные правила для Tasks 5–10.

- [x] **Step 1: Сгенерировать и показать концепции.** Codex: `frontend-app-builder` и `imagegen`. Если генерация недоступна или исполнитель не Codex — статический HTML-прототип на токенах визуальной системы (без продуктовой логики, демонстрационные данные; место хранения согласовать с пользователем). Растровый и HTML-референс равноправны для приёмки. По одному читаемому desktop-экрану: статистика матча с панелью игрока, календарь «время × зал», проверка личности, независимая публикация. Вся примерная информация подписана как демонстрационная; не рисовать неизвестные командные удары/передачи. Состояния загрузки/пустого блока/409/dirty описать рядом с соответствующим экраном, без дополнительных неработающих функций.
- [x] **Step 2: Проверить каждую картинку через `view_image` (или открыть HTML-прототип в браузере).** Сверить пункты «Правок по ревью» визуальной системы, навигацию, реальную ширину панелей, читаемость таблиц, легенду секунд и отсутствие «опубликовать всё». Исправить конкретные расхождения отдельным проходом генерации. Записать точный текст и намеренные отличия от картинки: визуальный mockup не изменяет контракт данных.
- [x] **Step 3: Получить пользовательскую оценку показанного набора и зафиксировать принятую версию.** Это приёмка дизайна, не разрешение выкладывать сайт/GitHub. Не писать продуктовые CSS/компоненты по непринятому изображению.
- [x] **Step 4: Записать извлечённую систему.** Документ обязан содержать таблицу `token | value | usage`, type scale, spacing, 8px radii/контейнеры по принятому изображению, кнопки default/hover/focus/disabled/pending, иконки lucide с размерами/толщиной, точные nav/CTA, 1440/1280/1024/390 поведение. Базовые значения до приёмки: white `#fff`, фон `#f4f6f8`, текст `#19221f`, акцент `#b8ec64`, поле `#172620`, home `#488ee6`, away `#e9aa49`; окончательные значения извлечь из принятого концепта, не менять по вкусу при кодировании.
- [x] **Step 5: Commit документа системы.** `git add docs/design/2026-10-15-ui-system.md` → `git commit -m "docs: lock accepted match workspace design system"`. Для растрового референса не писать unit-тест; проверка — визуальная и пользовательская.

### Task 2: Публичная шапка команд и ограниченная выдача логотипов

**Files:** Modify `src/aifootball/service/public.py`, `views.py`; Test `tests/service/test_public_calendar.py`; Create `tests/service/test_public_team_logos.py`; regenerate `web/src/api/types.ts` through export.

**Interfaces:** Produces: `PublicMatch.home_team_id: UUID`, `away_team_id: UUID`, `home_logo_id: UUID | None`, `away_logo_id: UUID | None`; `GET /api/v1/public/catalog/team-logos/{image_id}` → normalized PNG or 404. Existing private image route stays guarded. No new public player/photo API.

- [x] **Step 1: Добавить RED тест шапки.** Использовать `match_factory` и гостевой `TestClient`:

```python
def test_public_match_has_team_identity_without_private_roster(admin_client, match_factory):
    m = match_factory()
    with TestClient(admin_client.app) as guest:
        value = guest.get('/api/v1/public/matches/' + m['id']).json()
    assert value['home_team_id'] != value['away_team_id']
    assert value['home_logo_id'] is None and value['away_logo_id'] is None
    assert not {'lineup', 'notes', 'revision', 'photo_id'} & value.keys()
    assert value['score'] == {'home': None, 'away': None}
```

- [x] **Step 2: Добавить тесты логотипов с настоящей синтетической PNG.** В новом test-файле helper `upload_png(client)` создаёт `BytesIO`, `Image.new('RGB',(12,12),'blue')`, сохраняет PNG, POST `/catalog/images` с `X-Request-ID: str(uuid4())`, возвращает `response.json()['id']`. Связать через существующий `create/update` из `test_team_profiles`; добавить команду в `tournament_factory`. Гостевой GET: 200 только для логотипа команды неархивного турнира; 404 для непривязанного image, photo-only, image одновременно logo+photo, связи только с архивным турниром/командой, удалённого файла; 401 для приватного `/catalog/images/{id}`. У `Entry` нет поля archived: не добавлять искусственную проверку или миграцию. Общий logo с одной видимой и одной архивной связью доступен; архивирование последней видимой связи закрывает его при следующем запросе. Проверить `image/png`, `nosniff`, `no-store` для повторной проверки доступа при следующем запросе.
- [x] **Step 3: RED запуск.** `.venv/bin/python -m pytest tests/service/test_public_calendar.py tests/service/test_public_team_logos.py -q` → падают новые поля/404 существующего URL. Не запускать другую DB-suite параллельно.
- [x] **Step 4: Реализовать узкий запрос и DTO.** `match_query()` выбирает aliased `Team.id/logo_id` вместе с именами; обновить распаковку `match_view`. Logo route требует `CatalogImage`, существующую связь `Team.logo_id` → `Entry.team_id` → `Tournament` с `Tournament.archived=False` и `Team.archived=False`. Дополнительно исключить любой `Player.photo_id == image_id`. Возвращать только файл `attachment_root/catalog/{UUID}.png`; не вызывать приватный route с обходом guard. Использовать `exists()`/один SQL, не загрузку участников по одному.

```python
# Смысл предиката: existence видимой связи AND NOT existence photo-связи.
# Любой отсутствующий объект/файл -> тот же публичный 404.
return FileResponse(path, media_type='image/png', headers={
    'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})
```

- [x] **Step 5: GREEN, schema и commit.** Повторить тесты; `.venv/bin/python scripts/export_service_openapi.py --output data/service/openapi.json`; `npm --prefix web run types:api`; `npm --prefix web run build`. OpenAPI в `data/service/` локальный генерируемый файл — не форсировать ignored в Git. Commit точных source/test/types файлов: `feat: expose safe public match branding`.

### Task 3: Read-only публикационное состояние и контракт job/run

**Files:** Modify `src/aifootball/service/ratings/queries.py`, `routes.py`; Create `tests/service/test_performance_publication_read.py`; Modify `tests/service/test_analysis_versions.py`; regenerate `web/src/api/types.ts`.

**Interfaces:** Consumes: existing `PerformancePublicationView`, `rating_state(db, tid, create=False)`, `require_analytics_reader`. Produces: `performance_publication(db: Session, mid: UUID) -> dict` and GET `/matches/{mid}/performance-publication`; revision exactly `TournamentRatingState.revision`, absent state→0. `policy_approved` = `public_policy_id is not None`. `RunSummary.job_id` already implemented; no production change to that contract.

- [x] **Step 1: RED read-only test.** Импортировать `grant` из `test_analysis_jobs`, existing models from `ratings.models`:

```python
def test_read_absent_publication_creates_nothing(admin_client, match_factory):
    from sqlalchemy import select, func
    from aifootball.service.ratings.models import TournamentRatingState, RatingMatchPublication
    m = match_factory()
    grant(admin_client)
    url = '/api/v1/matches/' + m['id'] + '/performance-publication'
    for _ in range(2):
        r = admin_client.get(url)
        assert r.status_code == 200
        assert r.json() == {'revision': 0, 'match_id': m['id'],
            'participation_version_id': None, 'action_version_id': None,
            'policy_approved': False}
    with Session(admin_client.app.state.engine) as db:
        for model in (TournamentRatingState, RatingMatchPublication):
            assert db.scalar(select(func.count()).select_from(model)) == 0
```

- [x] **Step 2: RED boundaries.** Дополнить тестом state.revision=7 и publication.revision=2 (создать согласованные источники через `prepare/publish_sources` из `test_ratings_snapshots`, затем изменить только ревизии в Session). GET revision=7 и выбранные ID совпадают с PUT. С SQLAlchemy `before_cursor_execute` в `try/finally` записать SQL только вокруг GET и исключить INSERT/UPDATE/DELETE; проверить счётчики policy/command не выросли. Обычный admin→403, guest→401, absent match→404 для Admin+, malformed UUID→422. В существующем import→review fork тесте проверить, что оба run summary имеют исходный `job_id`, не включают `understanding`/evidence.
- [x] **Step 3: RED запуск.** `.venv/bin/python -m pytest tests/service/test_performance_publication_read.py tests/service/test_analysis_versions.py -q` → новый GET отсутствует; существующий job контракт уже проходит.
- [x] **Step 4: Реализовать GET без mutation helpers.** В query получить Match через `get_entity`, state с `create=False`, publication по match_id; вернуть пять полей существующего view. Route:

```python
@router.get('/matches/{mid}/performance-publication', response_model=PerformancePublicationView)
def read_performance_publication(mid: UUID, actor=Depends(require_analytics_reader),
                                 db: Session = Depends(get_session)):
    return queries.performance_publication(db, mid)
```

Использовать стиль импорта данного модуля (если `queries` не импортирован — добавить импорт модуля). Не вызывать `_policy_version`, `_command`, `publish_sources`, commit/flush или `rating_state(create=True)` из GET.
- [x] **Step 5: GREEN, schema и commit.** Повторить targeted suite, экспортировать OpenAPI/types командами Task 2, build. Commit: `feat: read performance publication without mutations`.

### Task 4: Контекст отчёта, источник игрока и честные карты

**Files:** Create `web/src/features/match-report/model.ts`, `adapters.ts`, `adapters.test.ts`; Create `web/src/components/pitch/heatmap.ts`, `heatmap.test.ts`, `PitchMap.tsx`, `pitch.css`; reuse types from domain/ratings.

**Interfaces:** Produces types/functions below; they contain no fetch, mutation or auth state:

```ts
export type PlayerOrigin = 'protocol' | 'cv' | 'rating';
export type ReportContext = {
  matchId: string; protocolPublicId: string | null; cvRunId: string | null;
  ratingSnapshotId: string | null; historicalRating: boolean; periodKey: string;
};
export type PlayerSelection = {playerId: string; origin: PlayerOrigin};
export type Resource<T> = {status:'loading'} | {status:'absent'} |
  {status:'error'; message:string} | {status:'ready'; value:T};
export function canAttachCurrentCv(context: ReportContext, origin: PlayerOrigin): boolean;
export function periodLabel(key: string, name: string, partial: boolean): string;
export function sharedHeatmapMax(maps: readonly (readonly (readonly number[])[] | null)[]): number;
export function heatCellOpacity(seconds: number, max: number): number;
```

`ReportModel` in `model.ts`: `{context: ReportContext; protocol: Resource<PublicProtocol>; cv: Resource<PublicAnalysis>; ratings: Resource<MatchRatingsView>}`; add domain aliases `PublicProtocol` and `MatchRatingsView` from generated schemas. A private adapter extracts only presentation-safe subset from `AnalysisRun` to the same `PublicAnalysis` shape; private evidence remains outside this model. `PitchMap` props: `{cells:number[][]|null;lengthM:number;widthM:number;orientation:string;maxSeconds:number;scaleLabel:string}`. `canAttachCurrentCv` conservative: returns false for ANY `origin==='rating'`; rating source manifest does not currently expose enough public information to prove map compatibility. Map can be opened separately with explicit CV context.

- [x] **Step 1: RED pure tests.**

```ts
it('does not relabel current CV as the source of a rating',()=>{
 const c:ReportContext={matchId:'m',protocolPublicId:'p',cvRunId:'B',
   ratingSnapshotId:'A',historicalRating:true,periodKey:'all'};
 expect(canAttachCurrentCv(c,'rating')).toBe(false);
 expect(canAttachCurrentCv(c,'cv')).toBe(true);
 expect(periodLabel('all','Весь матч',true)).toBe('Обработанный фрагмент');
});
it('compares both teams on one scale and leaves zero neutral',()=>{
 expect(sharedHeatmapMax([[[0,2]],[[0,12]]])).toBe(12);
 expect(heatCellOpacity(0,12)).toBe(0);
 expect(heatCellOpacity(12,12)).toBe(1);
 expect(sharedHeatmapMax([null,[[0,0]]])).toBe(0);
});
```

- [x] **Step 2: RED render coverage.** `PitchMap` tests: 41×15.5 pitch has that aspect ratio; all-zero/null/malformed/ragged/negative/nonfinite cells produce «Нет наблюдений»/«Карта недоступна» and no colored cells; unknown orientation is labeled «Ориентация не задана» without mirroring. No calls to image/private endpoints. Adapter matches by player UUID, not name/number; two identical names stay separate. Distances unknown stay null; zero remains zero; no shots/pass aggregation is added.
- [x] **Step 3: RED запуск.** `npm --prefix web run test -- src/features/match-report/adapters.test.ts src/components/pitch/heatmap.test.ts` → missing module/functions until implemented.
- [x] **Step 4: Реализовать helpers и SVG.**

```ts
export function heatCellOpacity(seconds:number,max:number):number {
  return max > 0 && Number.isFinite(seconds) && seconds > 0
    ? Math.min(1,seconds/max) : 0;
}
export function periodLabel(key:string,name:string,partial:boolean):string {
  return key==='all'&&partial?'Обработанный фрагмент':name;
}
```

`sharedHeatmapMax` scans only validated rectangular nonnegative finite matrices; reject invalid matrix as a whole. `PitchMap` SVG `viewBox="0 0 lengthM widthM"`, white futsal lines, time-cell rects and external textual legend `0 — maxSeconds с`; do not smooth/add per-cell confidence. Team max computed once from both matrices per selected period; player map gets explicit individual scale. Expose observed/video/processed durations separately; individual role not derived from coordinates. Add team width/depth/compactness only from existing numeric whitelist fields with their supplied units, no new formulas.
- [x] **Step 5: GREEN and commit.** Run targeted tests and build; commit all Task 4 files plus aliases: `feat: model report sources and comparable time heatmaps`.

### Task 5: Общие компоненты, оболочки и URL-навигация

**Files:** Create `web/src/styles/tokens.css`, `controls.css`; Create `web/src/features/navigation/{query.ts,query.test.ts,CabinetShell.tsx,PublicShell.tsx,shell.css}`; Create `web/src/components/match/{MatchHeader.tsx,SectionNavigation.tsx,SourceStatus.tsx,PlayerInspector.tsx,PlayerInspector.test.tsx}`; Modify `web/src/App.tsx`, `styles.css`, `features/public/PublicPages.tsx`.

**Interfaces:** Consumes accepted design, `PublicMatch`, Task 4 types. Produces: `MatchHeader({match:PublicMatch})`, `SectionNavigation({items:{id:string,label:string}[],selected:string,onSelect:(id:string)=>void})`, `SourceStatus({label:string,detail?:string})`, `PlayerInspector({title:string,onClose:()=>void,children:ReactNode})`. Navigation helpers `readMatchTab(params:URLSearchParams,audience:'public'|'private'):string`, `patchQuery(current:URLSearchParams,patch:Record<string,string|null>):URLSearchParams`, `isUuid(value:string|null):boolean`.

- [ ] **Step 1: RED navigation test.**

```ts
it('changes a section without discarding edition, player and tournament context',()=>{
 const next=patchQuery(new URLSearchParams('snapshot_id=A&player_id=P&tab=stats'),{tab:'players'});
 expect(next.get('snapshot_id')).toBe('A');
 expect(next.get('player_id')).toBe('P');
 expect(readMatchTab(new URLSearchParams('tab=private'),'public')).toBe('overview');
 expect(isUuid('not-a-uuid')).toBe(false);
});
```

- [ ] **Step 2: RED accessibility test.** Render trigger+inspector, open via userEvent; focus enters panel, Tab remains inside while modal on small viewport, Escape closes and returns focus to original trigger. Desktop inspector remains an accessible labeled dialog/panel; close button named «Закрыть карточку игрока». Selected nav has `aria-current`, keyboard focus ring visible; status contains text not only color. Assert no fetch inside these presentation components.
- [ ] **Step 3: RED запуск.** `npm --prefix web run test -- src/features/navigation/query.test.ts src/components/match/PlayerInspector.test.tsx` → missing modules.
- [ ] **Step 4: Implement exact visual system and routing glue.** Move existing cabinet/public shell JSX to named modules; `App` composes guards/routes. Import tokens before controls and feature CSS; remove only conflicting legacy selectors, not all CSS. Match tabs in URLs; filter replace, player open/close push+Back. `patchQuery` clones and deletes null keys, preserving unrelated valid context. Public route whitelist is `overview/events/players/stats/video`; private is `overview/lineup/protocol/review/participation/actions/report/publication/info/history`; default overview, old private `tab=analysis|video` redirects to review (preserve existing links), old bare `/matches/:id` works. Malformed IDs show error without making API requests. Add reduced-motion and local table overflow; keep 224px rail outside main width.

```css
:root { --app-bg:#f4f6f8; --surface:#fff; --text:#19221f; --accent:#b8ec64; }
.spectator-main { width:100%; max-width:1440px; margin-inline:auto; padding:24px 32px; }
.table-scroll { max-width:100%; overflow-x:auto; }
```

Values above must be reconciled with accepted Task 1 tokens, not blindly copied if concept differs. No whole UI bitmap in CSS.
- [ ] **Step 5: GREEN and visual check.** Targeted tests, full UI tests, build. Open both shells at 1440 and 1024 in IAB; compare to accepted concepts before continuing. Commit exact files: `feat: unify match navigation and desktop app shells`.

### Task 6: Гостевой матч, панель игрока и история турнира

**Разбиение на два коммита (объём задачи большой).** 6a — `matchLoader`, `PublicMatchPage`, `MatchReport/PlayerTable/TeamComparison/report.css`, извлечение `PublicProtocolContent`, `MatchRating.tsx`, `App.tsx`; тесты Step 1 и тесты Step 2 про origin карты, поздний ответ A/B, 404/500, пустую карту, 0/0. Commit: `feat: add unified public match report`. 6b — `PublicPlayerHistoryPage`, `Broadcast`, `PlayerRatingHistory/TournamentRatings/types.ts`; тест выбранного издания из Step 2, сохранение snapshot при клике по оценке, iframe только по нажатию. Commit: `feat: add public player history and broadcast`. Шаги ниже выполняются в каждой части только для её файлов.

**Files:** Create `web/src/features/public/{matchLoader.ts,matchLoader.test.ts,PublicMatchPage.tsx,PublicPlayerHistoryPage.tsx,Broadcast.tsx,PublicMatchPage.test.tsx}`; Create `web/src/features/match-report/{MatchReport.tsx,PlayerTable.tsx,TeamComparison.tsx,report.css}`; Modify `features/public/PublicPages.tsx`, `features/protocol/PublicProtocolPage.tsx`, `features/ratings/{MatchRating.tsx,TournamentRatings.tsx,PlayerRatingHistory.tsx,types.ts}`, `web/src/App.tsx`.

**Interfaces:** Consumes Task 2 branding and Task 4/5 types. Produces `MatchReport({model:ReportModel,selection:PlayerSelection|null,onSelect:(s:PlayerSelection)=>void})`; `loadPublicSection(match:PublicMatch,tab:string,snapshotId:string|null,signal:AbortSignal):Promise<Partial<ReportModel>>`; `PublicPlayerHistoryPage` at `/watch/players/:id?tournament_id=&snapshot_id=`. Public loader never calls a route outside `/public/` (except protected-independent auth shell if used, which must not gate content). Shared `PublicProtocolContent({value:PublicProtocol})` extracted from public page, no private protocol fetch.

- [ ] **Step 1: RED public boundary test.** Mock fetch and record every URL, simulate logged-in session but render public route; it must request `/public/matches/{id}` first, then only selected section's public dependencies. «События» uses `/public/protocols/{public_protocol_id}`; absence of pointer does not request private `/matches/id/versions`. Public image uses `/public/catalog/team-logos/id`, never `/catalog/images/id`. Re-run in guest E2E context. Public view must not request `/players/id` or `/players/id/analysis`.
- [ ] **Step 2: RED context tests.**

```ts
it('requests the selected edition without requesting private history',async()=>{
 const paths:string[]=[];
 vi.stubGlobal('fetch',vi.fn(async input=>{
   paths.push(String(input));
   return new Response(JSON.stringify({snapshot_id:'edition-A',summary:[],matches:[]}));
 }));
 render(<MemoryRouter><PlayerRatingHistory playerId="p1" publicView
   initialTournament="t1" initialSnapshot="edition-A"/></MemoryRouter>);
 await waitFor(()=>expect(paths.some(p=>p.includes('/public/players/p1/ratings')&&
   p.includes('snapshot_id=edition-A'))).toBe(true));
 expect(paths.every(p=>p.includes('/public/'))).toBe(true);
});
```

Add tests: A rating click preserves snapshot+origin; matching current CV map hidden for rating origin with «Карта этого издания недоступна», explicit «Открыть текущую CV-карту» switches origin. CV selection shows map and no invented role. Slow request for match A resolves after B: B stays visible (AbortController + context identity). 404 analysis is absent; 500 is retryable error within block; protocol still visible. No observations→neutral empty map; pass 0/0 → reason, not 0%; unresolved count visible. Initial overview never loads understanding/private evidence. Query player not in selected data gets an empty explanation, not a catalogue lookup.
- [ ] **Step 3: RED запуск.** `npm --prefix web run test -- src/features/public/matchLoader.test.ts src/features/public/PublicMatchPage.test.tsx src/features/ratings/ratings.test.tsx`.
- [ ] **Step 4: Implement public composition.** Match metadata first; independently fetch only selected dependencies in parallel with `Promise.allSettled`, not a single error boundary that hides header. Overview loads published protocol, public CV and match ratings (no private run); events only protocol; players all three; stats CV+ratings; video metadata only. Do not duplicate child-owned fetch with loader fetch: `MatchRatings` accept supplied value or separate renderer. `snapshot_id` passed to match ratings, rank pagination and history. If no supplied snapshot, store returned ID for that loaded view; refresh to current is explicit. Full history is existing `PlayerRatingHistory publicView`, header name from published rows only. Public roster from published protocol, union optional CV/rating rows keyed UUID with explicit source badges; group names/role names localized via static map. No fabricated 5×5 formation. MatchReport implements group tabs for individual shots/creation, passes, defense, GK and movement; team comparisons only existing CV aggregates. Saved physical facts within rating remain separate from current CV. Broadcast iframe created only on «Смотреть на сайте», URL already server-validated, external VK fallback retained; failed iframe does not imply no broadcast. Technical/shootout result labels from published protocol.
- [ ] **Step 5: GREEN and commit.** Targeted tests, full UI tests/build, browser match protocol-only/CV-only/no-result and player open/Back/history. Commit: `feat: add unified public match and player reports`.

### Task 7: Турнирный календарь и рабочее пространство организатора

**Files:** Modify `features/public/{Schedule.tsx,Schedule.test.tsx,PublicPages.tsx}`, `features/tournaments/TournamentPage.tsx`; Create `features/tournaments/{TournamentWorkspace.tsx,TournamentPublicationList.tsx,TournamentWorkspace.test.tsx}`; Modify `features/navigation/CabinetShell.tsx`, `web/e2e/helpers.ts` only where task-navigation contract changed.

**Interfaces:** `Schedule` сохраняет `{matches:PublicMatch[],timezone:string}`, читает view/day/hall/status из URL; optional `matchHref:(id:string)=>string` задаёт кабинетный адрес, default — гостевой. `TournamentWorkspace({tournamentId:string})` владеет навигацией, переиспользует existing entries/rules/ratings и создание матча. Список публикации читает поля текущей сводки матчей; подробности запрашиваются только для выбранного матча.

- [ ] **Step 1: RED tests.** Expand existing Schedule test: initial `?tab=matches&view=grid&day=2026-10-20&hall_id=hall-1&status=ended` opens correct grid/filter; two halls same name stay distinct; change day uses tournament timezone; Back restores previous tournament list parameters. Null score stays dash, not 0:0; cancelled/postponed text remains. Use `<MemoryRouter initialEntries={[...]}>` + a component reading `useLocation()` to assert params; no real clock assumption. Tournament tests: matches/teams/rules/ratings oldtabs work; players scoped from tournament entries, halls from schedule/membership, links reuse existing catalog editors; no new independent catalogue is created.
- [ ] **Step 2: RED запуск.** `npm --prefix web run test -- src/features/public/Schedule.test.tsx src/features/tournaments/TournamentWorkspace.test.tsx`.
- [ ] **Step 3: Реализовать календарь.** Столбцы определяются UUID зала, для старых записей — подписью; интервалы используют `schedule_slot_s`. Получать все страницы через существующий `all`, чтобы не терять матчи после первых 50. Строка содержит время, команды, статус, счёт, VK и ссылку. URL-фильтры применять до построения сетки:

```ts
const day=search.get('day');
const hall=search.get('hall_id');
const status=search.get('status');
const shown=matches.filter(m=>(!day||localDay(m.scheduled_at,timezone)===day)&&
 (!hall||(m.hall?.id??m.venue_label)===hall)&&(!status||m.status===status));
```

`localDay(iso:string,timezone:string):string` вынести в `features/matches/timezone.ts` из существующей day-функции Schedule, переиспользовать её тесты. На шкале времени границы слотов совпадают с подписями начала/конца; пересечения видны, не перекрывают контролы.
- [ ] **Step 4: Реализовать workspace.** Навигация «Работа / Участники и площадки / Настройки», сохранение выбранного турнира при входе в матч; общие каталоги остаются. В public турнире URL-вкладки matches/ratings и выбранное издание. Список готовности использует доступные pointers/status; неизвестные подробности подписаны «Откройте матч для проверки». Не делать для каждой строки полный набор versions/CV/ratings запросов. Ссылки ведут на `?tab=publication` матча; до готовности Task 10 они остаются за старым маршрутом, не вводить мёртвую кнопку в промежуточный релиз. TeamEditor и HallPage получают общую типографику контролов.
- [ ] **Step 5: GREEN/browser and commit.** Existing hall/team/profile UI tests + Task 7 tests, build; IAB compare calendar at 1440/1024 to concept and ensure no page-wide overflow at 390. Commit: `feat: organize tournament calendar and cabinet navigation`.

### Task 8: Кабинет матча и один владелец протокола

**Files:** Create `features/matches/{MatchWorkspace.tsx,MatchOverview.tsx,MatchWorkspace.test.tsx}`; Create `features/protocol/{ProtocolSession.tsx,ProtocolMode.tsx,ProtocolSession.test.tsx}`; Modify `features/protocol/{ProtocolEditor.tsx,outbox.test.ts}`, `features/matches/MatchPage.tsx`, `web/src/App.tsx`, `web/e2e/helpers.ts`.

**Interfaces:** `MatchWorkspace` владеет контекстом чтения матча и навигацией. `ProtocolSession({matchId,children})` создаёт один `useProtocolCommands` для редактирования protocol/lineup/info/history. `useProtocolSession():ReturnType<typeof useProtocolCommands>` передаёт существующий результат дочерним представлениям. Экран чтения report/publication session не создаёт. Pending сохраняется существующим outbox/drafts; новую очередь не вводить. Task 10 может создать такую же session только после явного действия публикации, когда редакторская session уже размонтирована.

- [ ] **Step 1: RED session ownership test.** Mock command hook/lock acquisition; open protocol then report/publication: editing owner count maximum 1, read-only views create no new hook/lock. Return to protocol with pending command: queue item request_id/body unchanged, retry once, no duplicate event. Use existing tests in `outbox.test.ts` for exact serialization; assert new workspace routing doesn't clear localStorage. Add same-admin second-tab lock case and corrupt-draft raw download remains before clear.
- [ ] **Step 2: RED only-result test.** Choose «Только итог», enter 3:2, inspect outgoing existing `set_totals`/mode commands; no implicit set_completeness all complete, no generated goals/participants. After save/return selected mode and score remain, absent action data stays unknown. Confirm button still uses existing server validation and explicit acknowledgement; failed 409 retains edits. Camera missing blocks CV task with fix link but does not block protocol. Ordinary admin sees no forbidden participation/actions/ratings mutations or associated requests.
- [ ] **Step 3: RED запуск.** `npm --prefix web run test -- src/features/matches/MatchWorkspace.test.tsx src/features/protocol/ProtocolSession.test.tsx src/features/protocol/outbox.test.ts src/features/protocol/drafts.test.ts`.
- [ ] **Step 4: Разделить workspace и владельца редактора.** Загружать match через существующий endpoint; шапка кабинета явно показывает частный статус. Overview содержит исправляющие ссылки `?tab=lineup|info|protocol|review`. Перенести вызов hook в Provider, не менять `useProtocolCommands` и outbox:

```tsx
type ProtocolSessionValue=ReturnType<typeof useProtocolCommands>;
const SessionContext=createContext<ProtocolSessionValue|null>(null);
export function ProtocolSession({matchId,children}:{matchId:string;children:ReactNode}) {
 const value=useProtocolCommands(matchId);
 return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
export function useProtocolSession():ProtocolSessionValue {
 const value=useContext(SessionContext);
 if(!value)throw new Error('ProtocolSession is required');
 return value;
}
```

В `ProtocolEditor` заменить собственный hook на context; EventForm/Clock/Totals/Notes/Versions и callbacks/revision сохранить. При входе в report session размонтируется без очистки durable outbox; при возвращении восстанавливается по текущим lock-правилам. Не держать скрытый ProtocolEditor ради preview.
- [ ] **Step 5: Вынести прямые задачи и режимы.** Существующие `live/after` и новый локальный `result` управляют видимостью полей; сохранять выбранный режим через scoped draft. `result` показывает итоги/полноту/подтверждение, не записывает фиктивные события или полноту. Участие/действия открываются напрямую с прежними actor keys и командами, без внешнего и внутреннего tab-wrapper. Подтверждённая версия read-only, новая редакция через действующую команду; сведения и история остаются доступны.
- [ ] **Step 6: GREEN and regression commit.** Targeted+full UI tests/build, run existing retry/conflict/roster/protocol E2E sequentially in dedicated E2E DB. `createTournament()` helper now opens `?tab=protocol` explicitly after match creation; `goal/totals` select task before controls, preserving assertions. Commit: `feat: introduce match workspace without duplicating protocol queues`.

### Task 9: Очередь проверки CV/Qwen и статусы внешнего результата

**Разбиение на два коммита (объём задачи большой).** 9a — чистые `reviewQueue.ts` (`jobResultState`, `visibleTrackIds`) с тестом, `JobStatus.tsx` и подписи статусов в `AnalysisTab.tsx`; Steps 1 и 5. Commit: `feat: derive external job status from imports`. 9b — `ReviewWorkspace`, `review.css`, `IdentityReview`, `MatchUnderstanding`; Steps 2, 3, 6, 7. Commit: `feat: add source-scoped video review workspace`.

**Files:** Create `features/analysis/{ReviewWorkspace.tsx,reviewQueue.ts,reviewQueue.test.ts,ReviewWorkspace.test.tsx,JobStatus.tsx,review.css}`; Modify `features/analysis/{AnalysisTab.tsx,IdentityReview.tsx,MatchUnderstanding.tsx,analysis.test.tsx,understanding.test.tsx}`.

**Interfaces:** Consumes `AnalysisOverview`, `AnalysisRun`, existing IdentityReview/Understanding commands; produces pure `jobResultState(jobId:string,runs:AnalysisOverview['runs']):'not_uploaded'|'review'|'confirmed'`, `visibleTrackIds(run:AnalysisRun,filter:'all'|'unassigned'|'assigned'|'excluded',page:number,pageSize:number):number[]`. `ReviewWorkspace({matchId,actorId,canManage})` reads URL run_id/task/item_id/filter; pagination local with full run assignments retained. Existing full PUT and side_map/revision body unchanged.

- [ ] **Step 1: RED exact job test.**

```ts
it('does not claim a new job is ready because an older job has an import',()=>{
 const runs=[{id:'r1',job_id:'j1',status:'confirmed'}] as AnalysisOverview['runs'];
 expect(jobResultState('j1',runs)).toBe('confirmed');
 expect(jobResultState('j2',runs)).toBe('not_uploaded');
 expect(jobResultState('j1',[{...runs[0],status:'review'}])).toBe('review');
});
```

Rule for mixed review+confirmed same job: result exists, confirmed label plus count of review versions; no running/in-progress claim. Active/published statuses shown from overview pointers independently.
- [ ] **Step 2: RED full-assignment test.** Expand existing `analysis.test.tsx` fixture to 51 tracks; assign #1, change to unassigned filter/page 3, assign #51, save: callback receives BOTH assignments and all pre-existing hidden ones. Switch run A→B→A after unsaved edit: restored scoped A only, no B material. Late fetch A after B not rendered. Dirty blocks confirm/publish; after successful save accepted revision updates, failed 409 remains dirty. Corrupt scoped draft raw download, actor/run mismatch rejected; side-map change retains existing side validation. Thumbnail absent shows interval/hint and no fabricated footage. Ordinary admin reads permitted run but no understanding request/import/job creation buttons.
- [ ] **Step 3: RED эпизоды.** Current accepted/corrected/rejected and no-decision filter; opening episode shows its own evidence/clock basis, number hint cannot autoaccept UUID. Saving correction reuses existing pending request, failed response retry same ID/body. Rejected reason required by server; no fabricated global readiness percentage.
- [ ] **Step 4: RED запуск.** `npm --prefix web run test -- src/features/analysis/reviewQueue.test.ts src/features/analysis/ReviewWorkspace.test.tsx src/features/analysis/analysis.test.tsx src/features/analysis/understanding.test.tsx`.
- [ ] **Step 5: Реализовать selector и статусы.** Полный draft остаётся у IdentityReview; selector вычисляет только видимые ID. Инспектор редактирует выбранный track в полном наборе. Сохранять весь draft, не массив видимых строк. Статус результата:

```ts
export function jobResultState(jobId:string,runs:AnalysisOverview['runs']) {
 const own=runs.filter(r=>r.job_id===jobId);
 return own.some(r=>r.status==='confirmed')?'confirmed':
   own.length?'review':'not_uploaded';
}
```

`not_uploaded` подписать «Результат не загружен»; активность/публикация run определяются отдельными pointers. Не добавлять процент удалённой обработки.
- [ ] **Step 6: Составить три панели.** Существующие guards и draft/pending helpers сохранить. Неизвестный item_id выбирает первый допустимый элемент своего run. От 1440: очередь 240 / material min 420 / инспектор 300; 1024–1439: кнопка очереди; 390: последовательные доступные панели. При отсутствии thumbnails/evidence показывать интервалы и состояние отсутствия материала, не подставлять генерированный кадр. Реальные ZIP import / create job / export package остаются под admin+; raw understanding загружается только для выбранного run. Подтверждённые версии не редактируются.
- [ ] **Step 7: GREEN/visual and commit.** Targeted suites / full UI / build, compare browser review to accepted concept with thumbnail missing and 51-track state. Existing import/understanding E2E run sequentially. Commit: `feat: add source-scoped video review workspace`.

### Task 10: Независимая публикация и честный гостевой preview

**Files:** Create `features/publication/{MatchPublication.tsx,publicationModel.ts,GuestPreview.tsx,MatchPublication.test.tsx}`; Modify `features/ratings/RatingWorkbench.tsx`, `features/ratings/TournamentRatings.tsx`, `features/tournaments/TournamentPublicationList.tsx`, `features/matches/MatchWorkspace.tsx`.

**Interfaces:** Consumes Task 3 GET, existing protocol versions, analysis overview, participation/actions, tournament analytics and existing writes. `MatchPublication({matchId,tournamentId,actorId,canManage})`; `GuestPreview({matchId})` only public loader; private preview separately labeled «В кабинете». `publicationModel.ts` pure description type: `{protocol:PublicationBlock;cv:PublicationBlock;performance:PublicationBlock;rating:PublicationBlock}`, `PublicationBlock={currentLabel:string;selectedLabel:string|null;blockers:{text:string;href:string}[]}`; no fake all-sources revision. Read-only component never invokes protocol queue hook.

- [ ] **Step 1: RED readback test.** Mock GET returns part P / action A / policy true / revision 7: form initially selects P/A, next existing PUT contains expected_revision 7 and current expected_match_revision, never local publication revision 2. Match change aborts old form response. Missing publication yields nullable selections; GET read has no request_id/write; ordinary admin skips Admin+ reads entirely.
- [ ] **Step 2: RED independent failure tests.** Protocol publish succeeds while CV lacks confirm: protocol published state updates, CV disabled with fix link, not generic allfailed/allcomplete. Tournament calculate creates candidate C but public preview remains B until explicit publish; stale fingerprint errors retain B and offer recalc. Rating action remains tournament route/command with return match context. Lost response repeats identical request; 409 preserves selection/draft; source edit invalidates readiness, not old published report. Public guest preview network uses only public endpoints even when logged in; private preview is not a shareable guest URL. Clicking preview doesn't mount editing lock.
- [ ] **Step 3: RED запуск.** `npm --prefix web run test -- src/features/publication/MatchPublication.test.tsx src/features/ratings/ratings.test.tsx`.
- [ ] **Step 4: Инициализировать форму чтением.** Извлечь форму разрешений RatingWorkbench, сохранив storage/request keys; начальные part/action/policy брать из нового GET. Тип сохранить из generated schema:

```ts
type PublicationView=components['schemas']['PerformancePublicationView'];
const saved=await api<PublicationView>(`/matches/${matchId}/performance-publication`);
// Existing PUT: expected_revision = saved.revision, а не локальная revision источника.
```

Источник dirty/pending имеет приоритет над повторным GET: refresh не затирает локальные selections.
- [ ] **Step 5: Подключить независимые команды.** Protocol publish использует confirmed version ID. При явном нажатии создать один `ProtocolSession` Task 8 со специализированным action-view вместо скрытого Editor; переход `idle → acquired → queued → result`, при размонтировании dispose. Если в outbox есть старая pending/conflict команда, новую публикацию не enqueue: показать её и ссылку на протокол для сверки. Команда публикации идёт через существующий queue.enqueue, не второй `post`/новый store; request_id сохраняется при потере ответа. Preview/простое открытие экрана никогда не создают session. CV использует текущие `sendJson` и `expected_analysis_revision`. Полный CV не требуется для публикации протокола. Tournament calculate и publish — две отдельные операции; обновляется только затронутый блок, остальные ошибки/успехи сохраняются. GuestPreview потребляет опубликованный ReportModel, частный preview отдельно подписан и закрыт admin+. Никаких batch endpoint или общей транзакции.
- [ ] **Step 6: GREEN and commit.** Targeted / full UI / build, IAB compare independent row layout/revisions/guestpreview against concept; commit: `feat: coordinate independent match publications`.

### Task 11: Сквозная, визуальная и эксплуатационная приёмка

**Files:** Create `web/e2e/match-workspace.spec.ts`, `docs/2026-10-15-ux-ui-acceptance.md`; Modify relevant existing `web/e2e/*.spec.ts`, `README.md`, `docs/README.md`, `docs/2026-10-15-ux-ui-reference-audit.md`, `docs/architecture/2026-10-14-final-service.html` status only, and this plan checkboxes. Do not label future GPU/S3/OCR complete.

**Interfaces:** Consumes implemented routes/contracts, existing synthetic API+E2E helpers and dedicated test DB lifecycle. Produces reproducible test evidence, compatibility statements, known limitations, current browser links and final review fixes.

- [ ] **Step 1: Записать синтетический сквозной сценарий до финальных исправлений.** `web/e2e/match-workspace.spec.ts` импортирует `{test,expect}` и `{login,createTournament,totals}`. Создать турнир/матч, внести итог, подтвердить с явным acknowledgement неполноты, опубликовать через новый экран. Гость `browser.newContext()` проходит турнир → матч → события; счёт совпадает с опубликованной версией, запросов private API нет, VK загружается только по нажатию. Для CV использовать синтетический ZIP из `analysis-import.spec.ts`, для истории A/текущего B — сценарий `tournament-ratings.spec.ts`. При извлечении helpers в `web/e2e/fixtures.ts` объявить тип результата по фактическому helper; не добавлять реальное видео или невалидные ручные rating payloads. Отдельные тесты: pending протокола → отчёт → публикация → повтор даёт одно событие; фильтр 51 назначений; права обычного admin; одинаковые названия залов; подписи частичного 186 с отчёта. Каждый тест создаёт свои данные, без ID локальной демонстрации.
- [ ] **Step 2: Execute required verification sequentially.**

```sh
.venv/bin/python -m pytest --tb=line -q
npm --prefix web run test
npm --prefix web run build
npm --prefix web run test:e2e
git diff --check
```

Expected: обычные тесты проходят. Real-video slow suite исключена действующим pytest config; новые падающие тесты не исключать. Освободить 8181 или намеренно использовать выделенный E2E-сервер через `AIF_REUSE_E2E=1`; не тестировать на БД организатора. Если после тестов код изменился, повторить затронутые проверки. Повторная генерация OpenAPI/types требуется только после изменения API.
- [ ] **Step 3: Визуальная проверка в IAB, снимки вне Git.** Проверить public/private при 1440×1000, 1280 и кабинет при 1600 (spec §16), сворачивание очереди при 1024, локальную прокрутку таблиц при 390. Проверить клавиатуру, Escape, Back, видимость счёта при открытой панели. В одном проходе `view_image` открыть каждый принятый концепт и свежий browser render. Сравнить минимум пять пунктов: иерархия/ширина, типографика/контролы, навигация, геометрия/легенда карты, таблицы/инспектор, независимые состояния публикаций. В acceptance записать расхождение → исправление → свидетельство. Временные файлы убрать после выбора итогового свидетельства, снимки не коммитить.
- [ ] **Step 4: Регрессии источников и восстановления.** Публичное издание A не меняется после частной версии B и повторной обработки; старые ссылки протокола/матча работают; просмотр не добавляет команды/версии. Backup/restore smoke test: `.venv/bin/python scripts/verify_service_backup.py --source e2e` (документирован в `docs/service-stage1.md`). Создаётся новая `aifootball_restore_<uuid>_test`; после восстановления проверить UUID, confirmed versions и pointers рейтинга. Рабочую БД не использовать. Платный Qwen/live GPU не требуются для UI-приёмки; указать их как непроверенный внешний путь.
- [ ] **Step 5: Независимое review ветки и исправления.** При Native навык `executing-plans` требует одного нового reviewer в конце: передать spec, план, base SHA, Review Focus и результаты проверок; проверить доступ, черновики, издания и UI. При исполнении по агентам следовать выбранному workflow. Проверить замечания, исправить реальные регрессии и повторить затронутые тесты. Не задавать model override без прямого требования навыка/пользователя.
- [ ] **Step 6: Зафиксировать фактический результат.** Acceptance содержит числа тестов, ссылки браузера, матрицу прав, разделение synthetic/real, ограничения архивных CV-карт и отдельного экспорта. README, индекс и статусы HTML-архитектуры обновлять только для проверенных функций. Commit названных файлов: `docs: record match workspace acceptance`. GitHub push/PR/deploy — при отдельном запросе; внешнее изменение `AGENTS.md`, локальные данные/архивы/фото/env в коммит не включать.

## Самопроверка плана

| Требование spec | Реализация / проверка |
|---|---|
| §§1–5 общий визуальный язык, desktop, URL, роли | Tasks 1,4,5; Task 11: 1440/1280/1024/390 и клавиатура |
| §6 турнир/матч/официальные события/видео | Tasks 2,6,7; guest boundary, protocol-only, iframe по нажатию |
| §§7–9 игрок/история/версии/карты/точность | Tasks 4,6; A/B, отсутствие карты, null/0/0, секунды, UUID |
| §10 состав/зал/протокол/подготовка/очередь | Tasks 7,8; catalog/halls E2E, только итог, один владелец |
| §11 очередь и действительный статус job | Tasks 3,9; 51 скрытое назначение, scoped run, новый job без импорта |
| §12 независимая публикация | Task 10; частичный отказ, stale, B до публикации C |
| §13 четыре обязательных пункта контрактов | Tasks 2,3; job_id уже есть, GET без SQL write, ACL |
| §14 состояния/потери/409/доступность | Tasks 5,6,8,9,10; pending/corrupt, Back, поздний fetch, клавиатура |
| §§15–17 границы и приёмка | Task 11; отдельный technical HTML, будущие функции не объявлены готовыми |

Пять Review Focus сопоставлены с конкретными RED-кейсами в задачах 2/6,4/6,9,8/10,3/9 соответственно. Общие типы и signatures объявлены в Tasks 4/5/6; backend-имена Tasks 2/3 совпадают с потребителями. DTO job не дублируется. Личность определяется UUID, выбранный snapshot передаётся по навигации и пагинации; компонент чтения не дублирует хранилище редактора.

## Передача на исполнение

Рекомендован **Native**: задачи тесно связаны контекстом источников и существующими очередями, их проще вести одному исполнителю с единым представлением кода и финальным независимым review. Альтернатива — отдельные исполнители/ревьюеры по задачам, с дополнительной стоимостью передачи контекста. До продуктового кода пользователь проверяет этот план и показанные концепции; выбор метода исполнения сохраняется для всей реализации.
