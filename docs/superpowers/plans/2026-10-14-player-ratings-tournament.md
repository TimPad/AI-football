# Player Ratings and Tournament Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Воспроизводимые оценки за матч, общий и позиционные рейтинги турнира с подтверждённым участием, прозрачными метриками и независимой публикацией.

**Architecture:** Отдельный модуль ratings принимает выбранные версии протокола, подтверждённых CV-действий и ручного участия; не вызывает VLM для выдачи балла. Чистые формулы нормируют действия/время внутри роли, затем создаются immutable tournament snapshots. Qwen предоставляет кандидаты и доказательства, но полнота действий/времени устанавливается отдельно.

**Tech Stack:** Python 3.12, dataclasses/Decimal/stdlib для формул, существующие PostgreSQL/SQLAlchemy/Alembic/Pydantic/FastAPI, React/TypeScript/Vitest/Playwright. Новая ML-зависимость первой эвристической модели не нужна.

**Spec:** [Оценки и аналитика турнира](../specs/2026-10-14-player-ratings-tournament-design.md). Это расширение общего [Qwen-плана](2026-10-14-qwen-match-understanding.md), а не уже реализованный рейтинг.

## Global Constraints

- Identity = player_id UUID; рейтинг первого этапа внутри выбранного турнира.
- Роли: goalkeeper/fixo/ala/pivot/universal; неизвестная роль остаётся unknown. История сохраняет роль в матче, каталог не переписывает прошлое.
- Участие, время наблюдения и время мяча в игре различны. time_basis хранится, разные базы не смешиваются.
- per10 = 600*count/eligible_play_s; физическая работа не повышает основной score автоматически (вес 0).
- Модель role-profile-v1, компоненты/веса/percentile/prior/qualification из спецификации; все предварительные параметры версионные.
- Percentile требует reference cohort: ≥5 игроков и ≥20 eligible player-match на роль. До этого rating unavailable, raw metrics доступны.
- % сглаживаются с prior strength 10; mu_ref = сумма successes / сумма attempts совместимой reference. Если наблюдаемых возможностей нет, feature score=50; unknown denominator даёт null. При нулевых attempts всей reference нейтральный вклад, не выдуманный rate.
- Match rating: score 0–100, display=round(1+9*score/100,1); сравнение по unrounded score. Обязательное missing семейство блокирует полный score, не перенормировать веса.
- Основная оценка матча: ≥3 минуты и coverage≥80%; tournament: ≥3 rated matches, ≥20 минут, coverage≥80%; предварительные списки отдельно.
- Tournament shrinkage: u=min(minutes/10,1), T=(Σu*S+3*50)/(Σu+3); без eligible rows T=null.
- Один match/источник/канонический event учитывается один раз. Технические результаты/невыходы/серия пенальти не становятся appearances/голами игры.
- Для private используются выбранные подтверждённые факты; для public только явно опубликованные версии. Старое издание сохраняется до отдельной публикации нового.
- Рейтинг не меняет протокол. Исправление фактов, политики или reference создаёт новую версию/edition; снимок pagination неизменен.
- xG/PSxG/xT/VAEP, коррекция силы соперника и межтурнирный talent rating — отдельный обучаемый этап.
- Тесты на выделенной DB, обычный CI без платного API/видео/моделей. Синтетические данные можно коммитить, реальные кадры/keys нельзя.

## Review Focus

1. Полная категория с нулём действий и неизвестная категория дают разные результаты; цель видео не становится дублем официального гола (задачи 2–4).
2. Игрок с одним выходом/минутным голом и GK без ударов не получает необоснованное первое место (задачи 4–5).
3. Смена каталожного амплуа, несколько ролей, повторные замены, исчезновение из камеры: снимки/время/appearance сохраняются (задачи 1, 3, 5).
4. Новый analysis run/policy/reference или переключение public pointer не удваивает матч и не смешивает edition на страницах (задачи 5–6).
5. Команда с плохой камерой/неполными матчами не получает искусственно высокий score от перенормирования доступных метрик; privacy и полнота видны (задачи 4, 6–8).

## Files and Interfaces

Чистый пакет `src/aifootball/ratings/`: schema.py (факты/единицы), registry.py (метрики), features.py (числители/знаменатели), reference.py (версионный cohort), scoring.py (компоненты), aggregate.py (турнир), validate.py (ссылки/полнота). Пакет `service/ratings/`: models/schemas/operations/queries/routes — транзакции, решения/версии и DTO. Факты ratings не изменяют CV job context или старые хеши.

```python
@dataclass(frozen=True)
class MetricFact:
    value: float | None
    numerator: float | None
    denominator: float | None
    unit: str
    completeness: Literal['complete', 'partial', 'unknown']
    reason: str | None

@dataclass(frozen=True)
class MatchPerformance:
    tournament_id: str
    match_id: str
    player_id: str
    role: str
    time_basis: str
    eligible_play_s: float | None
    participation_s: float | None
    coverage: float | None
    facts: dict[str, MetricFact]
    provenance: dict
```

Определить эти типы в schema.py; bool/NaN не допускаются вместо числа, UUID/finite время валидируются. Multi-role = несколько строк MatchPerformance; общий appearance считает distinct match_id. Policy/ref/cutoff записываются в CalculationContext и snapshot, не выводятся из текущей даты во время сортировки.

## Task 1: Подтверждённое участие, роли и время

**Files:** создать `ratings/{__init__,schema,validate}.py`, `service/ratings/{__init__,models,schemas,operations,routes}.py`, миграцию `0011_player_performance.py` после Qwen 0010, `tests/service/test_participation.py`; включить routes в service/app.py. Если Qwen migration получает другой id, down_revision следует фактическому head; старые миграции не переписывать.

**Interfaces:** ParticipationVersion хранит match_id/source_analysis_run_id/source_protocol_version/context hash/clock basis/initial five/presence and role intervals/completeness/actor/revision/status. `save_participation(db, match_id, actor_id, payload) -> dict`, `exposure_by_role(participation: dict, play_intervals: list, possession_intervals: list) -> dict`. Time source video/game явно записан и переводится только при наличии проверенного mapping; отсутствие mapping не превращает elapsed_ms в video_ms.

- [ ] Написать failing tests повторных входов, overlapping roles, >5 обычных игроков с учётом rule.players_on_pitch/удалений/powerplay, player не из состава, timestamp вне видео, unknown интервала, confirmed immutability и изменения глобального position.

```python
def test_repeated_stints_count_playing_time_once():
    p = {'presence': [[0, 60_000], [90_000, 150_000]],
         'roles': [{'role': 'ala', 'intervals': [[0, 60_000], [90_000, 150_000]]}]}
    result = exposure_by_role(p, [[0, 30_000], [100_000, 150_000]], [])
    assert result['ala']['effective_play_s'] == 80
    assert result['ala']['on_pitch_s'] == 120
```

- [ ] Запустить `.venv/bin/python -m pytest tests/service/test_participation.py -q` до реализации.
- [ ] Реализовать версии, locks/expected_revision/request_id, роль в матче и интервалы отдельно от каталога; учесть паузы и null. На неполных видео сохранить unknown participation, не выводить его из треков. Добавить приватные GET/PUT участия с require_analytics_admin.
- [ ] Повторить tests и migrations suite; коммит `feat: record verified participation and positional exposure`.

## Task 2: Канонические действия и полнота источников

**Files:** создать `ratings/actions.py`, `service/ratings/actions.py`, `tests/test_rating_actions.py`, `tests/service/test_performance_actions.py`; расширить модели миграции 0011 до её применения.

**Interfaces:** `canonical_actions(protocol: dict, reviewed_actions: list[dict], links: list[dict]) -> list[dict]`. Action: UUID, kind, player_id/recipient/opponent, role/null, start/end video time/null, success/on_target/outcome, possession_id, start/end coordinates/null, canonical_event_id, source references and version, completeness. Действия: shot/pass/carry/duel/recovery/shot_block/turnover/save/distribution/error; официальный goal/card/foul пришёл из протокола. `save_actions` — versioned admin+ ручная разметка/связь с эпизодами Qwen и полнота по категории/диапазону.

- [ ] Tests одного гола в protocol/Qwen, unknown автора, assist_known=false, автогола, penalty_goal+attempt, shootout, второй жёлтой и связанного foul/card/penalty incident. Неверное связывание двух реальных разных событий отклоняется, а не silently dedup.

```python
def test_confirmed_cv_goal_does_not_double_protocol_goal():
    official = {'id': 'goal-1', 'kind': 'goal', 'player_id': 'person-1'}
    candidate = {'id': 'episode-1', 'kind': 'goal_candidate', 'player_id': 'person-1'}
    facts = canonical_actions({'events': [official]}, [candidate],
        [{'canonical_event_id': 'goal-1', 'source_event_id': 'episode-1'}])
    assert sum(f['kind'] == 'goal' for f in facts) == 1
```

Для tests использовать фиктивные строковые идентификаторы в чистой функции; API-тесты используют реальные UUID fixtures analytics_match/new_job. Helper возвращает provenance всех объединённых источников.
- [ ] Запустить action tests до реализации.
- [ ] Реализовать приоритет официального протокола для счёта/авторов, явные ссылки и конфликты; ревью эпизода не задаёт completeness=complete автоматически. Ручное внесение действий возможно без Qwen/видео с отметкой источник, но rate/роль требуют соответствующих знаменателей. Аудит решений сохраняется.
- [ ] Повторить action/API tests; коммит `feat: canonicalize player actions with reviewed completeness`.

## Task 3: Реестр, нормализация и турнирные показатели

- [ ] Учитывать scope/полноту каждого источника в provenance фактов. highlights/continuous_excerpt/unknown не дают полного видео-знаменателя/полноты действий матча; complete processing и full_match сами по себе её не подтверждают. Tests: один монтажный гол не даёт полный рейтинг; независимая полная ручная разметка по тому же игроку может обеспечить факты/полноту. Не запрещать рейтинг по надёжным источникам из-за неполного дополнительного видео.

**Files:** создать `ratings/{registry,features}.py`, `tests/test_rating_features.py`.

**Interfaces:** `build_features(performance: MatchPerformance, actions: list[dict], *, profile_id: str) -> dict[str, MetricFact]`; `aggregate_facts(rows: list[MatchPerformance]) -> dict[str, MetricFact]`. Registry включает definitions, unit, direction good/bad, required sources, numerator/denominator и допустимые базы времени.

Канонические feature IDs для policy/scoring: npg_rate10, assists_rate10, shots_on_target_pct,
key_pass_rate10, recoveries_rate10, duel_win_pct, blocks_rate10,
dangerous_turnover_rate10, pass_completion_pct, discipline_cost_rate10,
save_pct, distribution_pct, progression_rate10. Counts/known_count/physical
хранятся отдельными ID и не подменяют эти normalized features.

- [ ] Tests per10, ratios из сумм, смешанных time_basis, полного нуля/unknown, possession denominator=0/unknown, чужого действия, нескольких ролей, голов серии, missing assist и карты разных залов.

```python
def test_tournament_rate_is_ratio_of_sums():
    rows = [MetricFact(2, 2, 600, 'count/10min', 'complete', None),
            MetricFact(.5, 1, 1200, 'count/10min', 'complete', None)]
    result = combine_rate(rows)  # helper внутри features.py
    assert result.value == 1  # 600*(2+1)/(600+1200)
```

Определить `combine_rate(rows: list[MetricFact]) -> MetricFact` как часть aggregate_facts; данный helper не усредняет значения 2 и 0.5.
- [ ] Запустить features tests до реализации.
- [ ] Реализовать реестр из таблицы спецификации, ключевую передачу в одной possession цепочке, продвижение по четвертям реального зала и опасную потерю в своей четверти. Goal/shot/pass linkage сохраняется; метрики с неизвестной полнотой не дают полного значения. Physical maxima берутся max устойчивых maxima; не суммировать карты несопоставимых залов. Для неполных counts вернуть known_count отдельно, total=null.
- [ ] Повторить features/actions tests; коммит `feat: calculate exposure-aware futsal player metrics`.

## Task 4: Reference cohort и объяснимая оценка матча

**Files:** создать `ratings/{reference,scoring}.py`, `tests/test_rating_scoring.py`; создать `configs/ratings/role-profile-v1.json` с весами, qualification и metric direction из спецификации.

**Interfaces:** `build_reference(rows: list[MatchPerformance], *, policy: dict, cutoff: str) -> dict`; `score_match(features: dict[str, MetricFact], *, role: str, policy: dict, reference: dict) -> dict`; `percentile(value: float, values: list[float], *, lower_is_better=False) -> float`. Output score/null, display_rating/null, components/contributions/reasons, model/reference/profile ids, eligibility and time basis.

- [ ] Tests одинаковых значений/нулей, отсутствующего обязательного семейства, роли GK, нуля ударов при полной разметке, unknown shots faced, малого cohort и нарушения суммы весов. Проверить, что увеличение дистанции само по себе не повышает score, а missing defence не заменяется goal-only.

```python
def test_tied_metrics_get_neutral_percentile():
    assert percentile(0, [0, 0, 0]) == 50

def test_incomplete_defence_cannot_be_hidden_by_goals(score_case):
    features = score_case.complete_features(role='fixo')
    features['recoveries_rate10'] = MetricFact(None, None, None, 'count/10min', 'unknown', 'Нет разметки')
    result = score_match(features, role='fixo', policy=score_case.policy,
                         reference=score_case.reference)
    assert result['score'] is None
    assert result['reasons']
```

`score_case` fixture строит reference из ≥5 synthetic UUID/≥20 строк, все обязательные признаки из registry, policy из configs; не использует реальные фамилии. Zero observed opportunities → neutral feature=50, неизвестное → null.
- [ ] Запустить scoring tests до реализации.
- [ ] Реализовать веса и проценты/prior strength 10, direction и неокруглённый score; policy фиксирует required metrics, thresholds, no-missing-renormalization. Reference сохраняет cohort состав/cutoff/hash/units/time_basis, не смешивает роли/лиги/profile. Недостаточный reference блокирует score. Подготовить sensitivity test, меняющий веса в разумном диапазоне и показывающий изменение рангов, а не заявлять объективность эвристики.
- [ ] Повторить tests; коммит `feat: score role-adjusted match performance transparently`.

## Task 5: Турнирный рейтинг, позиции и small-sample shrinkage

**Files:** создать `ratings/aggregate.py`, `tests/test_tournament_ratings.py`.

**Interfaces:** `tournament_rating(matches: list[dict], *, prior_score=50, prior_weight=3) -> dict`; `rank_players(rows: list[dict], *, role: str | None, policy: dict) -> list[dict]`. Уникальность по (match_id,player_id,role,selected_source); выбор active версии выполняется до функций. Несколько role scores матча агрегируются по role eligible seconds, u общего матча capped один раз.

- [ ] Tests 1/5 матчей, один короткий выход, zero eligible matches, технического матча/заявки без выхода, нескольких ролей, equal ranks и несовместимых editions. Tournament percentages/rates — sums, match count — distinct, не число треков.

```python
def test_small_sample_is_pulled_to_baseline():
    one = [{'match_id': 'm1', 'score': 80, 'eligible_play_minutes': 10}]
    assert tournament_rating(one)['score'] == 57.5
    five = [{**one[0], 'match_id': f'm{i}'} for i in range(5)]
    assert tournament_rating(five)['score'] == 68.75
    assert tournament_rating([])['score'] is None
```

- [ ] Запустить tournament tests до реализации.
- [ ] Реализовать из спецификации u/prior/qualification; rated/played coverage неизвестно при unknown total time. Полнота missing categories не penalize игрока нулевым баллом, но не даёт qualified status. Сортировать unrounded score, выставлять одинаковые спортивные места при точном равенстве; UUID — только стабильное отображение. Позиционные appearances/rates считают только эту роль, общий appearance один на матч.
- [ ] Повторить tests; коммит `feat: build stable tournament and positional rankings`.

## Task 6: Immutable snapshots, API и публикация

- [ ] Хранить объяснение балла/выбранные key moments в рамках rating snapshot с component/metric/canonical_action ids и ролью; private и public объяснения собираются из соответствующих разрешённых источников. Переназначение игрока, reject или новая версия не меняют старый snapshot, но инвалидируют текущий черновой расчёт. Tests исключают приватный текст/кадры в public и чужие UUID/отклонённые факты в новой версии.

**Files:** создать `0012_tournament_ratings.py`, `service/ratings/{queries,calculation}.py`, `tests/service/test_ratings_snapshots.py`; расширить models/schemas/routes, scripts/verify_service_backup.py. Source roles/actions versions из 0011; snapshot после них.

**Interfaces:** RatingPolicyVersion, RatingReferenceVersion, TournamentRatingSnapshot, PlayerRatingRow с unique(snapshot,match,player,role) и tournament summary rows; RatingCommand (actor/request_id/hash/response). `calculate_snapshot(db, tid, actor_id, request_id, *, scope='private') -> dict`, `publish_snapshot(...)`, `get_rankings(db, tid, snapshot_id, filters, pagination) -> dict`. Транзакционно зафиксировать выбранные источники, одна версия на матч; fingerprint включает pointer IDs, input hashes, participation/actions, policy/ref. Если вход изменился во время расчёта, snapshot stale и публикация отклонена.

- [ ] Tests replay same request/content, изменённого request payload, новой CV версии, catalogue position change, новой ref edition, unpublished source/reference, двух страниц с одним snapshot и rollback. Игрок за разные команды турнира учитывается одним UUID; team filter использует команду матча, не текущую affiliation. Ordinary admin не меняет policy/срез; гость видит только опубликованный sanitized DTO.

```python
def test_new_run_does_not_add_second_appearance(ratings_client):
    first = ratings_client.calculate()
    ratings_client.activate_replacement_run()
    second = ratings_client.calculate()
    assert first['players'][0]['match_count'] == second['players'][0]['match_count']
    assert first['snapshot_id'] != second['snapshot_id']
```

`ratings_client` — helper service test: использует analytics_match, создаёт два синтетических подтверждённых прогона и полную ручную разметку; выполняет real API вызовы, не mocked scoring.
- [ ] Запустить snapshots/migrations tests до реализации.
- [ ] Реализовать GET `/tournaments/{tid}/analytics`, `/tournaments/{tid}/ratings?position=...&snapshot_id=...`, `/players/{pid}/ratings?tournament_id=...`; admin+ POST calc и POST publish со stable request_id и revisions. Public GET под `/public/` выбирает только опубликованный срез, без кадров/annotations/private source contents. Новый public snapshot строить из published pointers и допущенного к публикации reference/policy, не делать public существующий private snapshot с закрытыми фактами. Статистика всех состоявшихся матчей содержит coverage evaluated/unrated; closed кадры не нужны leaderboard.
- [ ] Расширить точный backup/restore для новых версий/rows/pointers/files; выполнить service tests и backup E2E. Индексы tournament/snapshot/position/player покрывают pagination и query; query per-player не N+1.
- [ ] Коммит `feat: version and publish tournament analytics snapshots`.

## Task 7: Интерфейсы матч/турнир/игрок и ручная разметка

- [ ] Создать `src/aifootball/ratings/explanation.py` и `tests/test_rating_explanation.py`: `explain_rating(score, facts, actions) -> dict` строит короткий шаблонный текст и до трёх полезных действий/до трёх ошибок из подтверждённого вклада и роли, без API. Утверждения содержат source ids; пустая выборка не означает отсутствие ошибок. В MatchRating показать объяснение, раскрываемые детали и key moments; ручной факт открывает журнал, видеофакт — разрешённый evidence. Переход по времени не обещает плеер без оригинала. Tests: нет оценки → причина, rejected/foreign player excluded, same input → same explanation, unpublished evidence → no public link, HTML rendered as text. Подробное обоснование: [FootballVideoAnalyst review](../../2026-10-14-football-video-analyst-review.md).

**Files:** создать `web/src/features/ratings/{MatchRating,TournamentRatings,PlayerRatingHistory,ParticipationEditor,ActionReview,ratings.test}.tsx`; изменить tournaments/TournamentPage.tsx, analysis/AnalysisTab.tsx, catalog/CatalogPage.tsx и api/domain/types.ts; public/PublicPages.tsx для published aggregates. Создать `web/e2e/tournament-ratings.spec.ts` и synthetic E2E seed.

**Interfaces:** DTO из Task 6; ActionReview редактирует подтверждённые факты/полноту и связывает Qwen episode с protocol/action. ParticipationEditor показывает присутствие/роль/time_basis/unknown, не выставляет минуты из observed_s. MatchRating показывает компоненты+причину; TournamentRatings фильтрует role/team/stage/qualification в фиксированном snapshot; PlayerRatingHistory не смешивает reference/time_basis разных турниров.

- [ ] Tests incomplete score/no base, нулевых действий, goalie без shots, changing role, draft after network/409, insufficient participation, tie rank, publication/private evidence. Проверить UI copy пилотной методики и отображение минут/coverage рядом с рейтингом.

```tsx
it('shows missing data without a zero rating', () => {
  render(<MatchRating value={{score:null,display_rating:null,components:{},
    reasons:['Недостаточно данных по обороне'],eligibility:'unavailable'}}/>);
  expect(screen.getByText('Недостаточно данных по обороне')).toBeVisible();
  expect(screen.queryByText('0.0')).toBeNull();
});
```

- [ ] Запустить targeted Vitest до реализации.
- [ ] Реализовать сравнительные таблицы метрик, общий/по позиции leaderboard, блоки оценок, timeline нескольких выходов и trend. Не назначать predicted position автоматически. Рядом с баллом показывать роль, games/minutes/coverage и модель; details с исходными contributions. Черновики/request_id используют существующие useDraft/sendJson; same snapshot pagination. Physical radar/profile отдельно; отсутствие метрики не отрисовывать нулевой осью.
- [ ] Экспортировать OpenAPI/TS types, выполнить tests/build/E2E и rendered QA на узком/широком экране. E2E: mark facts→calculate→inspect match→role leaderboard→new source version→new edition→publish; старые snapshots и protocol unchanged.
- [ ] Коммит `feat: display explainable player and tournament ratings`.

## Task 8: Локальная приёмка и калибровка политики

- [ ] Проверить объяснение независимо от расчётного кода: все утверждения/действия соответствуют фактам этой роли/UUID/snapshot, хайлайты не создают полную оценку, reject/новая привязка обновляют новую сводку. С тренером проверить полезность выбранных положительных/отрицательных примеров; без полной записи/разметки не заявлять спортивную точность.

**Files:** создать `scripts/verify_tournament_ratings.py`, `docs/player-ratings-local-acceptance.md`; дополнить README/doc index/CHANGELOG и existing backup checker. Advanced model training в этой задаче не выполняется.

- [ ] Создать synthetic турнир минимум 5 игроков/20 player-match на каждую роль, с эталонными counts/exposures/percentiles/role weights, версиями/published/private. Добавить cases poor-camera team, unknown participation, missing action category и один удачный матч. Эталон вычислять независимо простой таблицей числителей/знаменателей, не вызовом scoring.py для expected values.
- [ ] Запустить script/targeted suite до реализации verifier; сверить sums/ratios/appearances, sample shrinkage, ties и независимость protocol. Проверить одинаковый input fingerprint → тот же расчёт и строка leaderboard; смена policy/reference → новая edition целиком.
- [ ] На реальном полном размеченном матче проверить actions/exposure и объяснение балла с тренером; train/control по матчам, ручная разметка спорных действий. Если имеющаяся запись только фрагмент или нет достаточной reference, честно проверить pipeline/отдельные метрики, полный рейтинг пометить недоступным. Не выдумывать игроков/полные игровые минуты для sporting acceptance. Демонстрационные обозначения сохраняются.
- [ ] Провести sensitivity/роль/coverage review: не награждается одна дистанция, не наказывается GK за общее число опасных ударов команды, один гол не квалифицирует MVP. Указать, что save% не учитывает сложность удара до PSxG. Веса/пороги принять как pilot policy, последующие изменения версионные.
- [ ] Выполнить backend suite, UI tests/build/E2E, backup verifier и git diff --check по CONTRIBUTING; recorded acceptance различает synthetic и реальную спортивную проверку.
- [ ] Коммит `test: verify tournament rating lineage and qualification`; review общей ветки до публикации. Не отмечать исполнение задач/advanced metrics готовыми при наличии только плана.

## Следующая научная поставка

После накопления полной футзальной разметки — отдельные планы обучения/калибровки xG/xA, PSxG/GSAA, xT/VAEP, opponent-adjusted impact. Первый шаг — dataset schema/splits, независимая оценка, calibration curves/Brier/log loss, analysis by role/powerplay/regulation. Готовые вероятности от Qwen/таблица 11×11 не заменяют эту приёмку.

## Execution Handoff

План дополняет, а не отменяет локальную поставку Qwen. Исполнение начинается после
проверки общего scope/плана и выбора метода; ранее выбранный метод сохраняется.
Сначала Qwen tasks 1–12, затем этот модуль; schema/фактология можно проверять
на synthetic/manual источниках независимо от качества VLM. Метод исполнения: native inline executing-plans. Локальная реализация и synthetic приёмка выполнены; спортивная калибровка с тренером остаётся отдельной приёмкой.
