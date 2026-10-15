# Qwen Match Understanding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Локально получить проверяемые предложения личностей, состояний и эпизодов футзального матча через YOLO + Qwen3.8-Omni-Flash, импортировать их в кабинет и безопасно продолжать обработку после прерывания.

**Architecture:** YOLO сохраняет детекции по частям; трекер воспроизводится из них без повторного YOLO. Qwen получает кропы игроков и короткие клипы/кадры, возвращает ограниченный JSON через потоковый API; ответы и бюджет сохраняются на диск. Результат версии 2 импортируется рядом с прежней версией 1; проверка эпизодов не меняет официальный протокол.

**Tech Stack:** Python 3.12+, текущие Polars/OpenCV/YOLO/ByteTrack, новый optional extra `vlm` с httpx, FFmpeg для клипов; существующие FastAPI/Pydantic/SQLAlchemy/Alembic/PostgreSQL, React/TypeScript/Vitest/Playwright. Qwen размещается у поставщика API; локальный GPU выполняет CV.

**Spec:** [Утверждённая архитектура, редакция Qwen](../specs/2026-10-14-qwen-match-understanding-design.md). Пользователь одобрил архитектуру и затем явно заменил DeepSeek на Qwen. Реализация ещё не начата; способ исполнения выбирается после проверки этого плана.

## Global Constraints

Дополнение: [проверенный разбор FootballVideoAnalyst](../../2026-10-14-football-video-analyst-review.md).
Его интерфейсные идеи включены в существующие задачи; код Gemini/Streamlit не переносится.

- Модель `qwen3.8-omni-flash`, API файлового анализа; realtime-модель не используется.
- `DASHSCOPE_API_KEY` и `DASHSCOPE_BASE_URL` относятся к одному региону/workspace и читаются из окружения.
- Платные запросы включаются только `--understand`; обычный `process-job` сохраняет результат версии 1.
- Первоначальная параллельность — 2; до 32 изображений, до 12 MiB тела запроса, один клип до 20 секунд; base64 отдельного аудио/видео менее 8 MiB.
- Обзорные окна 12 секунд с шагом 6 секунд; контрольная выборка 1 кадр/с, уточнение до 4 кадров/с.
- До 5 лучших кадров разных моментов одного трека; пиксели номера не дорисовываются.
- До 200 запросов, 300 000 входных и 100 000 выходных токенов по умолчанию; повторные попытки включены, исчерпание даёт `partial`.
- Максимум 3 попытки при 429/5xx; максимум одна попытка исправления неполного/неверного JSON. Незавершённый SSE-поток не является готовым ответом.
- JSON Object используется с `reasoning_effort: none`; только `delta.content` составляет итог, `reasoning_content` не смешивается с ним.
- Личность — UUID состава задания, номер/track_id/имя не заменяют UUID. Без установленного соответствия A/B сторонам матча UUID не предлагается однозначно.
- Подтверждённые результаты неизменяемы; исправления создают новую версию. Протокол и CV независимы.
- `observed_s` остаётся временем наблюдения; фазы, владение и интервалы «мяч в игре» показываются как оценки с неизвестным покрытием.
- Результат 2 содержит прежние файлы, `understanding.json` и `evidence/<id>.jpg`; job и метрический report остаются версии 1.
- До 10 000 эпизодов, 10 000 номерных наблюдений, 500 доказательств по 512 KiB, JSON до 8 MiB; ZIP до 100 MiB сжатых/300 MiB распакованных.
- Гипотезы и кадры понимания доступны Админ+; публичные DTO не расширяются этими данными.
- Сначала локальная приёмка; S3, очередь/lease и развёртывание прерываемой ВМ — следующая поставка.
- Не изменять рабочую БД, не публиковать ключи, видео, фото, модели, ответы реального API и рабочие файлы. Синтетические fixtures идут в Git.

## Review Focus

1. Обрыв SSE после части JSON/потеря usage: готового ответа нет, неизвестный расход зарезервирован; повтор не обнуляет бюджет (задачи 2–3, 8).
2. Один номер у соперников/смена личности внутри трека: нет произвольного UUID и автоматического назначения всему треку (задача 7).
3. Мяч пропал, камера перекрыта, комментарий запаздывает: не объявлять паузу или гол без контекста; неизвестное покрытие видно (задачи 5–8).
4. Остановка на границе CV-частей/два процесса одного workspace: глобальное время и непрерывность трекера сохранены, конкурентный запуск блокируется (задачи 3–4, 12).
5. Старый ZIP/обычный администратор/повтор ручного решения: совместимость версии 1, закрытые доказательства, идемпотентность и прежняя публикация сохранены (задачи 9–11).

## Границы файлов и зависимостей

`understanding/` содержит схемы, типы кадров/окон, сборщик гипотез, чистые правила идентификации и временного согласования. `processor/` владеет файлами, FFmpeg, сетью, бюджетом и восстановлением. Модуль обмена не импортирует YOLO, torch, HTTP-клиент или сервис. Сервис владеет правами, UUID, версиями и ручными решениями.

Задачи исполняются последовательно: 1 → 2/3 → 4/5 → 6/7 → 8 → 9 → 10 → 11 → 12. Это один связанный путь: выход одной задачи является входом следующей; отдельное облачное развёртывание в него не включено.

Во время исполнения использовать изолированную ветку `codex/qwen-match-understanding`, основанную на текущем коммите со спецификацией и планом; не потерять локальные изменения `AGENTS.md`. До изменения кода прочитать `using-git-worktrees`, на каждом цикле — `test-driven-development`; при ошибке — `systematic-debugging`. Не запускать реальный API в обычном pytest/CI.

## Task 1: Типы, строгая схема и синтетические данные

- [ ] Расширить ещё не реализованную схему понимания: `source.analysis_scope` enum full_match/continuous_excerpt/highlights/unknown, default unknown для старых synthetic fixtures. Значение устанавливается оператором после ответа VLM, не моделью; недопустимое значение отклонить. Tests разделяют coverage файла и полноту спортивных фактов; job/report v1 остаются прежними.

**Files:** создать `src/aifootball/understanding/{__init__,types,schema}.py`, `tests/understanding_fixtures.py`, `tests/test_understanding_schema.py`.

**Interfaces:** `validate_understanding(document: dict, *, manifest: dict, tracks: dict, files: dict[str, bytes] | None = None, rosters: list[dict] | None = None) -> dict`. Без rosters проверять синтаксис UUID; сервис позже проверяет принадлежность. `validate_window_response(document: dict, window: Window) -> dict` проверяет локальные времена в `[0, end_ms-start_ms)`, переводит их в глобальные ровно один раз и возвращает объект window_id/start_ms/end_ms/document/evidence. В ответе VLM обязательно `time_basis='window'`; кадры с глобальным временем сопровождаются этим правилом. Общие dataclasses из `types.py`:

```python
@dataclass(frozen=True)
class FrameAsset:
    id: str
    frame_id: int
    video_ms: int
    path: Path
    sha256: str
    crop: tuple[int, int, int, int] | None

@dataclass(frozen=True)
class MediaAsset:
    id: str
    kind: Literal['video', 'audio']
    path: Path
    sha256: str
    start_ms: int
    end_ms: int
    has_audio: bool

@dataclass(frozen=True)
class Window:
    id: str
    start_ms: int
    end_ms: int
    frames: tuple[FrameAsset, ...]
    media: MediaAsset | None
    track_ids: tuple[int, ...]
    mode: Literal['frames', 'native']

@dataclass(frozen=True)
class InferenceResult:
    document: dict
    usage: dict | None
    request_id: str | None
    response_model: str
```

Импорты типов: `dataclass`, `Path`, `Literal`. Runtime-валидатор использует stdlib и чистые функции, а не CV/HTTP. Общая схема: `schema_version='1'`, source/context, provider/settings, budget/usage, coverage, evidence, observations, identity_suggestions, states, phases, events, summary. Время — `video_ms`, интервалы `[start_ms,end_ms)`. Event: id, kind, start_ms/end_ms, team A/B/null, track_ids, evidence_ids, audio_observations, limitations. В audio_observations сохранять видимый диапазон клипа и его хеш, тип сигнала/текст; MP4/WAV в ZIP не включать.

Observation: track_id, video_ms, role, number, team A/B/null, evidence_ids, visible_features, limitations. State: kind, start_ms/end_ms, evidence_ids, limitations. Phase: kind, team A/B/null, possession A/B/null, attacking_direction left/right/unknown, start_ms/end_ms, evidence_ids, limitations. Summary assertion: text, event_ids, metric_refs (period_key, team/track_id, metric_name); metric reference дополнительно проверяется против измеренного report при упаковке/импорте. Coverage содержит covered_intervals/unknown_intervals и status complete/partial/unavailable, интервалы образуют полное непересекающееся разбиение видео.

Категории: state `pre_match|playing|stoppage|break|post_match|unknown`; phase `attack|defend|transition|unknown`; event `kickoff|kick_in|corner|free_kick_candidate|penalty_candidate|timeout|shot_candidate|save_candidate|goal_candidate|substitution_candidate|keeper_out_candidate|pressing_candidate|compact_block_candidate|unknown`. Номер — строка/null; роль `player|goalkeeper|referee|unknown`. Self-reported confidence не является вероятностью.

- [ ] Написать параметризованные отказы: лишние поля, NaN, неверная версия, вне видео/окна, несуществующий трек/кадр, отсутствующий JPEG, неверный хеш, неверный UUID и превышение каждого лимита. Fixture `understanding_document(manifest, tracks, *, duration_ms, evidence=None) -> dict` возвращает полный минимальный объект с unknown-шкалой; `make_frame(tmp_path, *, frame_id, video_ms) -> FrameAsset` создаёт синтетический JPEG и хеш.

В `tests/test_understanding_schema.py` определить локальные `manifest` и `track_index` fixtures из одного `validate_result(result_zip())` (существующие функции в `test_analysis_exchange` и `analytics.exchange`), чтобы пример ниже не зависел от отсутствующих общих fixtures. Конструктор synthetic doc заполняет все перечисленные поля, covered=[] и unknown=[[0,duration_ms]], status unavailable; source/context берёт из manifest.

```python
def test_event_cannot_reference_unknown_evidence(manifest, track_index):
    doc = understanding_document(manifest, track_index,
        duration_ms=round(manifest['source_video']['duration_s'] * 1000))
    doc['events'] = [{'id': 'e1', 'kind': 'goal_candidate', 'start_ms': 1000,
                      'end_ms': 2000, 'team': None, 'track_ids': [],
                      'evidence_ids': ['missing'], 'audio_observations': [],
                      'limitations': ['Мяч не виден']}]
    with pytest.raises(ValueError, match='evidence'):
        validate_understanding(doc, manifest=manifest, tracks=track_index)
```

- [ ] Запустить `.venv/bin/python -m pytest tests/test_understanding_schema.py -q`; ожидать отказ из-за отсутствующей реализации.
- [ ] Реализовать строгие множества полей/enum, конечные числа, полуоткрытое время, ссылки, счётчики и независимый unknown-охват. Не преобразовывать непонятный вывод в подтверждённый факт.
- [ ] Повторить тот же тестовый файл; ожидаются успешные результаты, включая валидный пустой неизвестный документ.
- [ ] Коммит `feat: define bounded match understanding schema` с перечисленными файлами.

## Task 2: Qwen HTTP-клиент и потоковый JSON

**Files:** создать `src/aifootball/processor/qwen.py`, `tests/test_qwen_client.py`; изменить `pyproject.toml`, `uv.lock`, `.env.example`.

**Interfaces:** `QwenConfig.from_env() -> QwenConfig` (key скрыт в repr, base_url, model, timeout); `QwenClient(config, *, transport=None).infer(window: Window, prompt: str, *, max_output_tokens: int) -> InferenceResult`. Один infer — одна оплачиваемая попытка; backoff/repair в задаче 8. Исключение `QwenError(code, retryable, retry_after=None, usage_unknown=False)` не содержит ключ/тело медиа.

- [ ] Через `httpx.MockTransport` написать тесты endpoint/model, заголовков, изображений/video/audio, отсутствия public URLs, UTF-8/SSE, usage без choices, обрыва, finish_reason length, пустого ответа и 401/429/5xx. Ключ теста — фиктивный.

```python
def test_sse_keeps_only_final_content(qwen_transport, frame_window):
    client = QwenClient(QwenConfig('test-key', 'https://example.invalid/v1'),
                        transport=qwen_transport([
                            {'choices': [{'delta': {'reasoning_content': 'ignore'}}]},
                            {'choices': [{'delta': {'content': '{"events":[]}'},
                                          'finish_reason': 'stop'}]},
                            {'choices': [], 'usage': {'prompt_tokens': 10,
                                                     'completion_tokens': 5}},
                        ]))
    result = client.infer(frame_window, 'Return JSON', max_output_tokens=512)
    assert result.document == {'events': []}
    assert result.usage['prompt_tokens'] == 10
```

`qwen_transport(chunks, *, status=200, done=True)` — helper теста: serializes `data: <json>\n\n` и `[DONE]`, поддерживает разрыв посреди записи; добавляет к chunks id и model `qwen3.8-omni-flash`. frame_window собирается из `make_frame` и Window задачи 1.

- [ ] Запустить `.venv/bin/python -m pytest tests/test_qwen_client.py -q`, получить отказ до реализации.
- [ ] Добавить extra `vlm = ["httpx>=0.28,<1"]`, обновить lock без произвольного обновления остальных зависимостей. Читать endpoint/key из окружения, запретить URL с userinfo/query/fragment, требовать HTTPS. Тело:

```python
body = {'model': config.model, 'messages': messages, 'modalities': ['text'],
        'stream': True, 'stream_options': {'include_usage': True},
        'reasoning_effort': 'none', 'response_format': {'type': 'json_object'},
        'max_tokens': max_output_tokens}
```

Собирать content только после корректного finish, учитывать optional usage; bound 2 MiB текста/50 000 SSE chunks/60s чтения и 180s общего запроса. Лимиты медиа проверять до HTTP. Значения из задания не управляют endpoint. `.env.example` содержит пустой ключ и комментарий об адресе workspace.
- [ ] Повторить client/schema tests, проверить `uv sync --locked --all-extras --dry-run`; не выполнять реальный запрос.
- [ ] Коммит `feat: add Qwen omni client with bounded SSE parsing`.

## Task 3: Workspace, кэш и устойчивый бюджет

**Files:** создать `src/aifootball/processor/{workspace,budget}.py`, `tests/test_processor_workspace.py`.

**Interfaces:** `Workspace(root: Path, fingerprint: dict)`, `exclusive()` context manager, `get_json(key: str) -> dict | None`, `put_json(key: str, value: dict) -> None`; `Budget(workspace, *, max_requests=200, max_input_tokens=300_000, max_output_tokens=100_000)`, `reserve_call(key, input_estimate, output_limit) -> str`, `settle_call(reservation, usage: dict | None) -> None`. JSON/Parquet write temp → fsync → replace; файл журнала обновляется после артефакта. Один процесс на workspace через flock для macOS/Linux.

- [ ] Написать тесты mismatch fingerprint, падения до/после rename, повреждённого готового файла, двух процессов, повторного открытия после reserved-запроса и общего бюджета retry. Fingerprint не содержит key/исходных имён участников.

```python
def test_unknown_usage_does_not_reset_budget_on_resume(tmp_path):
    store = Workspace(tmp_path, {'source': 'a' * 64, 'prompt': '1'})
    budget = Budget(store, max_requests=1)
    reservation = budget.reserve_call('window-1', 100, 200)
    budget.settle_call(reservation, None)
    resumed = Budget(Workspace(tmp_path, {'source': 'a' * 64, 'prompt': '1'}),
                     max_requests=1)
    with pytest.raises(ValueError, match='budget'):
        resumed.reserve_call('window-2', 100, 200)
```

- [ ] Запустить workspace tests, увидеть fail.
- [ ] Реализовать ключ кэша по источнику/context/CV/model/prompt/media/settings; отдельно ledger reserved/completed/unknown. Резервировать до HTTP и сохранять после ответа, учитывать реальные completion tokens включая reasoning при наличии. Неизвестный usage не освобождает резерв. Повтор settle не списывает второй раз.
- [ ] Повторить workspace tests с subprocess lock и injected crash, получить pass.
- [ ] Коммит `feat: persist processing workspace and inference budget`.

## Task 4: Сохраняемые CV-части и воспроизведение трекинга

**Files:** создать `src/aifootball/processor/cv.py`, `tests/test_processor_resume.py`; изменить `perception/{detect,frames}.py`, `processor/job.py` только для общего CV-runner.

**Interfaces:** `detect_batches(video, venue, weights, *, batch_size=16, start_ms=0) -> Iterator[pl.DataFrame]`; `run_cv(job_path: Path, video: Path, workspace: Workspace, *, models: Path) -> Path` возвращает корень прежних artifacts. `detect_video` собирает прежний результат из генератора для совместимости CLI. Fingerprint включает хеш весов, camera/context, разрешение, target_fps/imgsz/conf и параметры обработки.

- [ ] Синтетическое видео и fake predictor: прерывание после первого 60s chunk, пустая часть без людей, последний короткий chunk, неизменный глобальный frame_id/ts, ошибка разрешения, mismatch модели и camera, tracker пересекающий границу. Сравнить результаты непрерванного и resumed прогонов без настоящего YOLO.

```python
def test_resume_keeps_global_time_and_skips_saved_predictions(resume_case):
    full = resume_case.run(interrupt_after=None)
    resume_case.run(interrupt_after=1, workspace='resumed')
    continued = resume_case.run(resume=True, workspace='resumed')
    assert full['tracks'].equals(continued['tracks'])
    assert full['state'].equals(continued['state'])
    assert resume_case.predicted_again_before_ms(60_000) == 0
```

`resume_case` — fixture этого файла, использует `write_video`, venue и deterministic boxes-to-rows, регистрирует вызовы/времена, crash hook и читает Parquet. Interrupt должен быть реальным остановом subprocess в дополнительном тесте, а не только исключением.
- [ ] Запустить `.venv/bin/python -m pytest tests/test_processor_resume.py tests/test_processor_job.py -q` до реализации.
- [ ] Извлечь обработку batches без многократной загрузки весов; сохранять chunks, coverage/end-of-stream и metadata атомарно. Sampling привязан к исходному времени, не к старту части. Из всех готовых chunks собрать detections.parquet и последовательно запустить прежние track/project/metrics/check. Не сериализовать torch/ByteTrack и не начинать трекер заново на каждом chunk.
- [ ] Повторить целевые тесты и `.venv/bin/python -m pytest tests/test_frames.py tests/test_detect_rows.py tests/test_track.py tests/test_ball_detect.py -q`; проверить CPU synthetic path.
- [ ] Коммит `feat: resume CV from persisted detection chunks`.

## Task 5: Кадры, синхронные клипы и границы исходника

**Files:** создать `src/aifootball/processor/media.py`, `tests/test_understanding_media.py`.

**Interfaces:** `select_player_frames(video: Path, tracks: pl.DataFrame, out: Path, *, max_per_track=5) -> dict[int, tuple[FrameAsset,...]]`; `make_window(video: Path, *, start_ms: int, end_ms: int, out: Path, mode: str, fps=1, track_ids=()) -> Window`. MediaAsset содержит фактическое начало/конец, has_audio и хеш файла; локальные пути не сериализуются в result ZIP.

- [ ] Тесты кропов за краем, размытых/перекрытых кадров, разных моментов, отсутствующей аудиодорожки, диапазона с offset, >20s/8MiB, отсутствующего FFmpeg. FFmpeg integration на синтетическом видео запускается только при наличии binary; smoke приёмки требует его реально. Fixtures generate sine tone, не используют запись участника.

```python
def test_window_retains_source_offset_and_missing_audio(tmp_path):
    video = write_video(tmp_path / 'silent.mp4', n_frames=80, fps=4)
    window = make_window(video, start_ms=6000, end_ms=12_000,
                         out=tmp_path / 'window', mode='native')
    assert window.media.start_ms == 6000
    assert window.media.has_audio is False
    assert all(6000 <= f.video_ms < 12_000 for f in window.frames)
```

- [ ] Запустить media tests, получить fail.
- [ ] Проверить FFmpeg до запросов, subprocess argv без shell, ffprobe/ffmpeg с таймаутом и bound stderr. Точно вырезать/re-encode MP4, не применять неточное stream-copy seek; проверить duration/offset после экспорта. Нативный клип и выборка кадров имеют общий source offset. Для номеров сохранить кропы и показатель качества, без дорисовки/генеративного увеличения. Большие окна разделить до пределов, неизвестный/повреждённый диапазон пометить.
- [ ] Повторить media tests и синтетический FFmpeg smoke с аудио/без него; сохранить только тестовый журнал в output.
- [ ] Коммит `feat: extract timed player evidence and audiovisual clips`.

## Task 6: Окна, промпты и все категории понимания матча

- [ ] Промпт и tests учитывают analysis_scope: монтаж не трактуется как непрерывный матч; неизвестное покрытие не заполняется. Summary содержит ограничения/ссылки, не выводит ФИО или итоговый счёт из хайлайтов. Видимое табло — кандидат с временем, не правка официального счёта; комментарий не доказывает событие.

**Files:** создать `src/aifootball/understanding/{windows,prompts}.py`, `tests/test_understanding_windows.py`, `tests/test_understanding_prompts.py`.

**Interfaces:** `plan_windows(*, duration_ms: int, tracks: pl.DataFrame, ball_candidates: list[dict], mode='native') -> list[dict]` — specs id/start_ms/end_ms/fps/track_ids/kind; `identity_prompt(window: Window) -> str`, `match_prompt(window: Window, *, measured: dict) -> str`. Связь со схемой задачи 1 — те же enums и evidence ids.

- [ ] Проверить короткое/пустое видео, последний диапазон, перекрытие 12/6, кандидаты рядом с границей, отсутствие мяча и порядок id. Отдельные tests для каждой группы: состояния, вводы/стандарты, удары/сейвы/голы, замены/выход вратаря, фазы, прессинг/блок. Промпт не включает ФИО, key и arbitrary text задания.

```python
def test_no_ball_still_gets_overview_windows(empty_tracks):
    windows = plan_windows(duration_ms=25_000, tracks=empty_tracks,
                           ball_candidates=[], mode='native')
    assert windows[0]['start_ms'] == 0
    assert windows[-1]['end_ms'] == 25_000
    assert all(w['end_ms'] - w['start_ms'] <= 20_000 for w in windows)
```

- [ ] Запустить windows/prompts tests до реализации.
- [ ] Построить регулярные окна и кандидаты по движению/зонам людей и доступного мяча; потеря мяча не является состоянием stoppage. Объединять specs с сохранением coverage. Промпты описывают футзал, локальное/глобальное время, JSON и неизвестное; требуют наблюдения до/после, различают свисток и причину, комментарий и увиденное действие. VLM не запрашивает интернет/инструменты и не устанавливает официальное решение судьи.
- [ ] Повторить tests; fixture answers покрывают все enums, но не используются как доказательство спортивной точности.
- [ ] Коммит `feat: plan futsal windows and grounded omni prompts`.

## Task 7: Номера, роли и согласование эпизодов

**Files:** создать `src/aifootball/understanding/{identity,reconcile}.py`, `tests/test_understanding_identity.py`, `tests/test_understanding_reconcile.py`.

**Interfaces:** `resolve_identity(observations: list[dict], rosters: list[dict], *, side_map: dict | None) -> list[dict]`; `reconcile_windows(results: list[dict], *, duration_ms: int) -> dict` возвращает states/phases/events/summary/coverage. Window results имеют поля window_id/start_ms/end_ms/document/evidence; их глобальное время уже вычислено `validate_window_response`, повторно offset не добавлять.

- [ ] Тесты одинакового номера у команд, дубля номера внутри команды, противоречия 7/17 внутри трека, судьи, неизвестной роли, пустого side_map, перекрывающихся фрагментов. Тесты согласования: один event двух окон, два разных типа в одном моменте, out-of-window timestamp, конфликт states, дырка coverage, запаздывающий комментарий без изображения мяча.

```python
def test_same_number_without_side_map_has_no_unique_uuid():
    observations = [{'track_id': 1, 'team': 'A', 'number': '7',
                     'role': 'player', 'evidence_ids': ['f1']}]
    rosters = [{'player_id': '11111111-1111-4111-8111-111111111111',
                'side': 'home', 'shirt_number': '7'},
               {'player_id': '22222222-2222-4222-8222-222222222222',
                'side': 'away', 'shirt_number': '7'}]
    suggestion = resolve_identity(observations, rosters, side_map=None)[0]
    assert suggestion['player_id'] is None
```

- [ ] Запустить identity/reconcile tests, получить fail.
- [ ] Фильтровать кандидатные UUID только по снимку состава/стороне/номеру, не выбирать первое совпадение. Противоречивый трек получает conflict, требует разрезания/пересчёта, не majority identity. Episode id строить по source hash/prompt/кандидату и нормализованным полям, не принимать id модели; сверять ссылки. Противоречивые состояния заменить unknown, не продлевать игру/владение через дырки. Summary — только ссылки на найденные эпизоды/измерения, не свободный неподтверждённый текст.
- [ ] Повторить tests; не изменять уже подтверждённые назначения и CV-метрики.
- [ ] Коммит `feat: reconcile identities and uncertain match episodes`.

## Task 8: Локальная оркестрация и режим understand

- [ ] Добавить `analysis_scope='unknown'` в process_job/run_understanding и CLI `--analysis-scope full_match|continuous_excerpt|highlights|unknown`. Настройка входит в fingerprint понимания/кэш, но не меняет CV context/hash и не заставляет повторять готовые детекции. Tests проверяют смену scope при resume и понимают complete как покрытие файла, не матча.

**Files:** создать `src/aifootball/processor/understand.py`, `tests/test_understanding_processor.py`; изменить `processor/job.py`, `cli.py`.

**Interfaces:** `run_understanding(job: JobContext, video: Path, artifacts: Path, workspace: Workspace, *, client: QwenClient, budget: Budget, mode='native') -> tuple[dict, dict[str, bytes]]`; второе значение — JPEG-доказательства. `process_job(..., understand=False, work_dir=None, resume=False, vlm_mode='native', vlm_max_requests=200, vlm_max_input_tokens=300_000, vlm_max_output_tokens=100_000)` сохраняет прежние аргументы. `package_result(..., understanding=None, evidence_files=None)` выбирает версию 1/2.

- [ ] Synthetic CLI tests без API: understand off не читает key/не создаёт клиент; understand on требует key/endpoint/FFmpeg, budgets, готовые окна не повторяются, ошибка середины сохраняет CV и partial, смена prompt/media invalidates cache. Проверить repair плюс retries не превышают общего бюджета.

```python
def test_resume_does_not_repeat_completed_qwen_windows(processor_case):
    processor_case.run(understand=True, fail_after_window=1)
    result = processor_case.run(understand=True, resume=True)
    assert processor_case.api_calls_for('window-1') == 1
    assert result['coverage']['status'] == 'complete'
```

`processor_case` строит job через `job_package`, fake CV runner, fake QwenClient с таблицей ответов из fixture задачи 1 и реальный Workspace/Budget; возвращает read_archive результата. Нативный и frames mode тестируются отдельно.
- [ ] Запустить processor/client/resume tests до реализации.
- [ ] Добавить argparse параметры `--understand --work-dir --resume --vlm-mode native|frames --vlm-max-requests --vlm-max-input-tokens --vlm-max-output-tokens`. Проверить conflicting artifacts/resume/fingerprint до вычислений. Код оркестрации:

```python
cached = workspace.get_json(cache_key)
if cached is None:
    reservation = budget.reserve_call(cache_key, estimate, output_limit)
    response = client.infer(window, prompt, max_output_tokens=output_limit)
    budget.settle_call(reservation, response.usage)
    validated = validate_window_response(response.document, window)
    workspace.put_json(cache_key, {'document': validated, 'usage': response.usage,
                                   'model': response.response_model,
                                   'request_id': response.request_id})
```

`estimate`, `output_limit` получают из настроек и изображений/длительности media, не из свободного ответа. Вход Task 7 — cached['document']; audit usage/model не теряется при resume. Ошибки settle(None) сохраняют резерв. Retry backoff/jitter с injectable clock для tests, Retry-After bounded, 401/оплата/config останавливают VLM. После исчерпания бюджета упаковка включает unknown-диапазоны/причину, не «полный анализ».
- [ ] Повторить tests; проверить `process-job --help` и прежний синтетический ZIP версии 1.
- [ ] Коммит `feat: run resumable Qwen understanding from local CLI`.

## Task 9: Версия обмена 2 и доказательства

**Files:** изменить `analytics/exchange.py`, `processor/job.py`, `tests/test_analysis_exchange.py`; создать `tests/test_understanding_exchange.py`.

**Interfaces:** `ValidatedResult` получает `understanding: dict | None` с default None в конце dataclass; `validate_result` принимает 1/2, report schema остаётся 1. `read_archive` допускает только прежние имена, `understanding.json` и `evidence/[A-Za-z0-9_-]{1,100}.jpg`; manifest version определяет допустимый набор после чтения. Job whitelist остаётся прежним.

- [ ] Написать tests старого result, валидного v2, unknown version, v1+understanding, v2 без JSON, подмены hash/видео/context, лишнего evidence, symlink/path traversal, JPEG с неверным форматом/dimensions, каждого лимита. Helper `result_v2(job=None, *, mutate=None) -> bytes` в этом тестовом файле надстраивается над `result_zip`: распаковать в память, добавить полный synthetic understanding/evidence, пересчитать manifest sizes/hashes и собрать ZIP.

По умолчанию result_v2 содержит synthetic JPEG f1 с frame_id/time/hash, event e1 `goal_candidate` в [1000,2000), track 1, evidence_ids=['f1'], limitations=['Синтетический пример']; coverage covered=[[0,2000]], unknown=[[2000,duration_ms]], status partial. Это даёт конкретный эпизод тестам ручной проверки Task 10/11 без реального изображения участника. mutate(manifest, document) выполняется до пересчёта файлов/манифеста.

```python
def test_v1_cannot_smuggle_private_understanding():
    package = result_v2(mutate=lambda manifest, doc: manifest.update(contract_version='1'))
    with pytest.raises(ExchangeError, match='version|контракт'):
        validate_result(package)
```

- [ ] Запустить exchange/processor tests, увидеть fail.
- [ ] Проверять v2 schema/ref/hash/лимиты до создания файлов/БД; evidence использовать существующую проверку Pillow JPEG с отдельным size cap 512 KiB. Manifest integrity охватывает все новые файлы. `result_v2` включает source offset/hash/context и неизменяемые measured report/track-index/checks. Ограничить JPEG count до упаковки, при переполнении явная ошибка.
- [ ] Повторить оба exchange test files и processor tests, включая read_job(version=1).
- [ ] Коммит `feat: add compatible version two understanding exchange`.

## Task 10: Импорт, приватные API и версионные ручные решения

**Files:** создать `migrations/versions/0010_match_understanding.py`, `service/analysis/understanding.py`, `tests/service/test_understanding.py`; изменить `service/analysis/{models,schemas,imports,commands,routes}.py`, `scripts/verify_service_backup.py`, `tests/service/test_migrations.py`.

**Interfaces:** JSONB `AnalysisRun.understanding` nullable и `understanding_reviews` default `{}`; новая append-only `AnalysisUnderstandingDecision` (id/run_id/event_id/actor_id/revision/before/after). `get_understanding(db, run) -> dict` и `review_understanding(db, match_id, run_id, actor_id, data) -> dict`. DTO `UnderstandingView` содержит source understanding, текущие decisions, revision и динамические identity suggestions для текущего run.side_map. `UnderstandingReviewUpdate(Mutation)` содержит event_id, decision accepted/corrected/rejected, correction dict|null, reason≤500.

Новые маршруты с `require_analytics_admin`: `GET /matches/{mid}/analysis/runs/{rid}/understanding`, `GET .../understanding/evidence/{eid}`, `PUT .../understanding/reviews`. Полные данные не добавлять в общий RunView: он доступен обычному админу. Evidence route разрешает id из реестра, не arbitrary path. Correction проверяет enums/границы/roster/track ids и не меняет исходную гипотезу.

- [ ] Через существующие analytics_match/new_job/upload fixtures и result_v2 проверить идемпотентный импорт, foreign UUID, чужой run, права 401/403, revision conflict, потерю успешного ответа, confirmed immutability, clone/reviews, пустой v1 understanding, public DTO и отсутствие изменения счёта.

```python
def test_goal_review_cannot_change_protocol(admin_client, analytics_match):
    job = new_job(admin_client, analytics_match)
    run = upload(admin_client, analytics_match, result_v2(job)).json()
    before = admin_client.get(f"/api/v1/matches/{analytics_match['id']}").json()
    response = review_event(admin_client, analytics_match, run, 'e1', 'accepted')
    assert response.status_code == 200
    after = admin_client.get(f"/api/v1/matches/{analytics_match['id']}").json()
    assert after['protocol'] == before['protocol']
```

`review_event(client, match, run, event_id, decision, *, request_id=None, correction=None)` — test helper, PUT с Mutation/reason и stable request_id. `MatchView.protocol` и `MatchView.projection` существуют в `service/views.py`; дополнительно сравнивать projection.effective_score, как в tests/service/test_commands.py.
- [ ] Запустить service understanding/migrations tests, увидеть fail.
- [ ] Миграция следует `0009_analysis_revision`, старые строки имеют null/{}; import сохраняет исходное JSON после проверки roster job, view пересчитывает suggestions с run.side_map. Решение использует prior_command/remember, match/run locks, expected_revision; изменения разрешены только review, revision++ и append audit в одной транзакции. В commands reviews скопировать понимание и текущие decisions в новую версию без правки старой; аудит истории сохраняется. Evidence Cache-Control private/no-store, nosniff. Подтверждение CV-метрик не требует принятия всех гипотез; отчёт не объявляет их подтверждёнными.
- [ ] Расширить backup verifier точным сравнением understanding/audit/current decisions и существующих ZIP bytes, не только counts. Повторить service tests и backup на E2E DB.
- [ ] Коммит `feat: review private match understanding with immutable history`.

## Task 11: Кабинет проверки номеров и эпизодов

- [ ] Дополнить отдельный приватный UnderstandingView проверенной сводкой из текущих accepted/corrected решений, исходную model summary оставить явно гипотезой. Сводка/фильтр по UUID обновляются при correction/reject/переназначении/новой версии; неподтверждённые эпизоды исключены. Вычисление сводки разместить в service/analysis/understanding.py из Task 10, добавить service/UI tests. Навигация игрок → эпизод открывает evidence и video_ms; без оригинала нет обещания проигрывания. В overview показать analysis_scope, стадию/готовые окна/partial. Official metadata — из сервиса; расхождение с наблюдавшимся табло не меняет protocol. VK seek и веб-хранилище исходника остаются следующей поставкой.

**Files:** создать `web/src/features/analysis/{MatchUnderstanding,EvidenceGallery,understanding.test}.tsx`; изменить `IdentityReview.tsx`, `AnalysisTab.tsx`, `web/src/api/{domain,types}.ts`; создать `web/e2e/match-understanding.spec.ts`, дополнить fixtures E2E через существующие scripts.

**Interfaces:** `MatchUnderstanding({runId,matchId,actorId,editable,onChanged})` грузит отдельный закрытый UnderstandingView только при canManage; `EvidenceGallery({matchId,runId,evidence})`; IdentityReview получает optional suggestions и callback просмотра evidence. Текущий select остаётся решением пользователя, не автоматически выбранным UUID.

- [ ] Vitest tests v1, partial/unknown, conflict номера, смена side_map, сохранение черновика после сети/409, обычный админ не делает closed API call, HTML модели отображается текстом, accepted/corrected/rejected, отсутствие видеоплеера без оригинала.

```tsx
it('does not turn a number suggestion into an assignment', () => {
  render(<MemoryRouter><IdentityReview run={run} actorId="actor" editable
    suggestions={[{track_id:1,player_id:'person',evidence_ids:['f1']}]} onSave={vi.fn()}/></MemoryRouter>);
  expect(screen.getByLabelText('Игрок фрагмента 1')).toHaveValue('');
  expect(screen.getByText(/Предположение/)).toBeVisible();
});
```

`run` fixture — синтетический AnalysisRun из текущего analysis.test.tsx с optional DTO; test не требует реальных UUID в browser mock. Для E2E использовать валидный синтетический ZIP v2.
- [ ] Запустить `npm --prefix web run test -- src/features/analysis/understanding.test.tsx`, получить fail.
- [ ] Добавить шкалу состояний/эпизодов и фильтры групп, фактическое время исходника/кадры, явные unknown и ограничения аудио/видимости. Формы корректировки/отклонения используют текущие sendJson/useDraft/stable request_id; unresolved command не перезаписывается. Заголовки объясняют оценочность, confirmed version read-only. На narrow viewport галерея/таблица читаемы. Не показывать ключ, endpoint, model implementation details в продуктовых формах.
- [ ] Экспортировать OpenAPI `.venv/bin/python scripts/export_service_openapi.py --output data/service/openapi.json`, `npm --prefix web run types:api`; выполнить UI tests/build, targeted E2E и проверку rendered UI по frontend-testing-debugging/React skill. E2E: импорт→сверка→исправление→confirm→new review; обычный админ/публичный гость не получают evidence.
- [ ] Коммит `feat: inspect and review match episodes in analysis cabinet`.

## Task 12: Реальная локальная приёмка, сравнение и контейнер

- [ ] В acceptance добавить highlights/continuous_excerpt/unknown cases, неподтверждённый final score, rejected summary fact, неверную UUID-привязку и отсутствие оригинала. Synthetic tests проверяют механизмы ограничения/навигации; реальную точность summary оценить по независимой разметке. Не выдавать положительный synthetic case за качество модели.

**Files:** создать `scripts/verify_match_understanding.py`, `src/aifootball/understanding/evaluate.py`, `tests/test_understanding_evaluate.py`, `Dockerfile.processor`, `.dockerignore`, `docs/2026-10-14-qwen-local-acceptance.md`; изменить README/докиндекс/статус AGENTS.md только после реальной проверки.

**Interfaces:** `evaluate_understanding(predicted: dict, labels: dict, *, tolerance_ms=2000) -> dict`; labels schema: source_sha256, split tune|control, number observations с frame/time/track/demo UUID, events с kind/start/end, states/coverage. Script arguments `--job --video --labels --work-dir --mode native|frames --max-requests`; результат — отчёт качества/расхода без ключа, сохранённый в ignored output. Обычный CI не требует API/video/FFmpeg/GPU.

- [ ] Tests evaluator: не дублировать matched GT по окнам, false positives/negatives, wrong identity, unknown coverage, интервальная граница, категория без GT, разделение tune/control. Написать first failing test:

```python
def test_category_without_examples_is_not_perfect_accuracy():
    result = evaluate_understanding({'events': [], 'observations': [],
         'source': {'sha256': 'a' * 64}},
        {'events': [], 'observations': [], 'source_sha256': 'a' * 64,
         'split': 'control', 'states': [], 'coverage': []})
    assert result['events']['goal_candidate']['recall'] is None
    assert result['events']['goal_candidate']['gt_count'] == 0
```

- [ ] Запустить evaluator tests, получить fail; реализовать one-to-one matching по типу/времени с допуском 2s и отдельным unknown denominator. На имеющемся видео выделить непересекающиеся tune/control фрагменты, вручную разметить читаемые номера и события; демо-обозначения не выдаются за реальные ФИО. Если запись не содержит категории, явно «нет оценки», не обещать точность.
- [ ] Проверить наличие регионального key/endpoint только по факту настройки, не печатать значение и не просить отправлять ключ в чат. Короткий smoke Qwen: синтетическое изображение, silent clip и clip с звуком; подтвердить native формат, JSON/SSE/usage и указанные request limits. Затем запустить реальный локальный фрагмент в native и frames режиме с ограниченным бюджетом. При отсутствии key/media не подменять интеграционный результат mocked успехом, записать конкретную недоступную проверку.
- [ ] Сравнить baseline CV, номерной режим и расширенное понимание: identity precision/coverage, number accuracy, ID conflicts, event precision/recall по группам, temporal error, unknown coverage, wall time, память, usage и время ручной сверки. Повтор после kill процесса не вызывает готовые Qwen окна/YOLO chunks; CLI-report/hash metrics совпадают, provider stochastic answers сравниваются по сохранённому кэшу, не новым вызовам.
- [ ] Контейнер: Linux Python 3.12+, FFmpeg, uv lock, проект + vlm; torch из проверенного lock, Linux GPU-wheels без замены на CPU-only. Entry `python -m aifootball.cli`, mount /work и readonly /models, ключ runtime env. Минимальный Dockerfile:

```dockerfile
FROM python:3.12-slim-bookworm
WORKDIR /app
RUN apt-get update
RUN apt-get install -y --no-install-recommends ffmpeg libgl1 libglib2.0-0
RUN pip install --no-cache-dir uv==0.11.7
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --locked --extra vlm
ENTRYPOINT ["/app/.venv/bin/python", "-m", "aifootball.cli"]
```

Перед финальным build закрепить digest базового образа из реестра и проверить совместимость host driver с установленным torch CUDA runtime. build context исключает .git/.env/data/output/models/.venv/web/node_modules. Сначала CPU synthetic container smoke, затем CUDA тест на реально доступном Linux GPU; Mac MPS не считать проверкой CUDA. Создать образ без развёртывания облачной ВМ.
- [ ] Полная проверка после всех изменений:

```sh
.venv/bin/python -m pytest --tb=line -q
npm --prefix web run test
npm --prefix web run build
npm --prefix web run test:e2e
.venv/bin/python scripts/verify_service_backup.py --source e2e
git diff --check
```

Тестовая БД/порт 8181 используются по текущим scripts, данные организатора не трогать. Повторять suite только после нового изменения/провала. Приёмочный документ явно различает synthetic, live API, actual-video и CUDA evidence; не отмечать недоступные проверки как пройденные.
- [ ] Коммит `test: verify local Qwen understanding and processor recovery`; перед публикацией review всей ветки и свежие проверки. PR/публикация — отдельный GitHub workflow с сохранением приватности, не прямой push в main в процессе разработки.

## Покрытие спецификации и граница завершения

| Требование | Задачи |
|---|---|
| Qwen, регион, JSON/SSE, нативные видео/аудио | 2, 5, 8, 12 |
| UUID, номера, роли, противоречия | 1, 5, 7, 10, 11 |
| Все группы моментов и фазы футзала | 1, 6, 7, 8, 11, 12 |
| Метрические измерения остаются CV | 4, 7–9 |
| Покрытие, неизвестное время, evidence, резюме | 1, 5–9, 11 |
| Возобновление, кэш, бюджет, повторная оплата | 2–4, 8, 12 |
| Результат 1/2, происхождение и лимиты | 1, 8–10 |
| Ручная проверка, версии, права, протокол, backup | 10–12 |
| Локальная/контрольная приёмка и контейнер | 12 |
| Прерываемая ВМ/S3/lease | подготовка 3–4, 12; отдельная следующая поставка |

Первая поставка завершена после работающего локального сквозного пути и честной приёмки.
Наличие категорий JSON само по себе не означает распознавание всех событий с нужной точностью.
Автоматическая публикация гипотез, облачная очередь, S3 и запуск ВМ в этот план не входят.

## Расширение: оценки игроков и весь турнир

По запросу пользователя добавлена следующая локальная поставка:
[спецификация метрик и рейтингов](../specs/2026-10-14-player-ratings-tournament-design.md)
и [исполняемый план из 8 задач](2026-10-14-player-ratings-tournament.md).
Она включает подтверждённое время/роль на площадке, полный журнал действий с
ручной разметкой, прозрачную матчевую оценку, турнирные totals/динамику,
общий и позиционные рейтинги, reference/shrinkage и независимую публикацию.
Qwen выдаёт кандидаты, score считает детерминированный модуль. Первые tasks
схемы/ручных фактов проверяются без полного автоматического распознавания передач.
Advanced xG/PSxG/xT/VAEP требуют отдельной футзальной обучающей выборки.
Облачная ВМ остаётся после локальной приёмки согласованного объёма.

## Execution Handoff

Рекомендуется **native**: один исполнитель последовательно ведёт задачи в этой сессии,
затем один независимый reviewer проверяет всю ветку. Причина: CV-кадры, JSON-контракт,
приватные API и UI зависят от общих интерфейсов; постоянная смена исполнителя увеличивает
стоимость контекста. Альтернатива — свежий исполнитель и reviewer на каждой задаче,
с более частыми независимыми проверками и большим расходом контекста.

До кода пользователь проверяет этот план и выбирает способ исполнения. Существующее
одобрение спецификации сохраняется; повторного выбора модели/архитектуры не требуется.
