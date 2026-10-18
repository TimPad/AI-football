# VLM Context and Commentary Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Проверить, улучшают ли паспорт/память и лента из конкретных событий качество единого экономичного разбора.

**Architecture:** Отдельный opt-in v2 использует прежний `paid_once` и клипы, добавляет валидированный паспорт, полный журнал с компактной памятью, фильтр наблюдаемых сигналов и детерминированный экспорт реплик. Сохранённые планы исключают незаметное изменение оплаченного запроса при resume.

**Tech Stack:** Python, существующие Polars/OpenCV/httpx/pytest; локальные JSON/HTML, без новых зависимостей/БД/API сервиса.

**Spec:** `docs/superpowers/specs/2026-10-18-vlm-context-pilot-design.md`

## Global Constraints

- Один совместный запрос на 12-секундное окно, максимум шесть новых вызовов; старый baseline из кеша.
- Порог бюджета 150000 входных по оценкам/usage, 24576 выходных, резерв 25000/4096; неизвестный исход не повторять.
- Полный журнал отделён от компактной памяти ≤6000 UTF-8 байт; кандидаты не становятся подтверждёнными фактами.
- Времена VLM локальные; экспорт в шкале записи; UUID/протокол/публикации независимы.
- Источники паспортных фактов явны; GT не передаётся модели. Данные и ключи вне Git; рабочую БД не трогать.

## Review Focus

- Изменение паспорта/трека или локальных правил при resume: уже оплаченный вход не перезапрашивается скрыто — Task 3.
- Гэп/невалидное окно и будущая запись истории: модель не получает непрерывную игру или данные из будущего — Task 1.
- Неизвестный/противоречивый номер: не переносится на другой трек и не превращается в UUID — Task 1.
- Формально валидный кандидат без видимого мяча: не становится утверждением об ударе/голе — Task 2.
- Пустой/повреждённый ответ и длинный source offset: отчёт не падает, время не сдвигается дважды — Tasks 2, 3.

### Task 1: Passport and chronology

**Files:** Create `src/aifootball/understanding/match_context.py`; test `tests/test_vlm_match_context.py`.

**Interfaces:** `validate_passport(document: dict, source_sha256: str) -> dict`; `MatchChronology(source_sha256: str, passport: dict)` with `add(window, document, request_key)`, `gap(start_ms, end_ms, reason)`, `snapshot(before_ms, track_ids=()) -> dict`, `document() -> dict`.

- [ ] Write synthetic tests for source/provenance/unknown facts; 20 windows retain all events while snapshot bounded; future exclusion, gap, idempotent add, conflicting numbers, track scope. Expected: import failure before module exists.
- [ ] Implement validated passport and deterministic full journal/compact snapshot per spec. No external I/O/API in this module.
- [ ] Run `.venv/bin/python -m pytest tests/test_vlm_match_context.py -q`; Expected: all pass. Commit task.

### Task 2: Grounded joint contract and timed feed

**Files:** Create `src/aifootball/understanding/context_pilot.py`, `src/aifootball/understanding/commentary.py`; test `tests/test_vlm_context_commentary.py`.

**Interfaces:** `context_prompt(window, *, context, passport, memory, crop_tracks=None) -> str`; `project_context(document, window, *, crop_tracks=None) -> tuple[dict,list]`; `compile_commentary(chronology: dict, passport: dict) -> dict`.

- [ ] Write failing tests: v2 has no free commentary dependency; invalid visual signals rejected; unsupported playing becomes unknown; approach to goal is not a shot; valid observed shot produces one stable video-timed entry; no match start/official score; gap prevents resumed-play line; raw immutable.
- [ ] Implement v2 response adapter using existing base validator, explicit signal gates and code templates. Keep candidates and rejection reasons visible. Export stable IDs and video time exactly once; version contract separately from v1.
- [ ] Run `.venv/bin/python -m pytest tests/test_vlm_match_context.py tests/test_vlm_context_commentary.py tests/test_joint_vlm_pilot.py -q`; Expected: all pass. Commit task.

### Task 3: Resumable runner and report

**Files:** Create `scripts/verify_context_vlm.py`, test `tests/test_vlm_context_runner.py`; reuse `verify_joint_vlm.py` media/evaluation helpers and existing `paid_once`.

**Interfaces:** CLI `--manifest --output [--apply|--cache-only]`; manifest passport per case and optional `baseline_report`. Save exact request plans before inference, chronology JSON, commentary JSON, report JSON/HTML.

- [ ] Write failing tests for synthetic client first run/resume (one paid call), crash after plan/receipt, changed source/passport/tracks rejection, corrupted cached answer rendered safely, all labelled points counted, no GT in prompt.
- [ ] Implement input fingerprint, six-call budget, frozen plans and standalone report with global timed feed, evidence/rejections, per-case comparison and unknown outcomes. New output workspace; old experiment remains readable.
- [ ] Run `.venv/bin/python -m pytest tests/test_vlm_match_context.py tests/test_vlm_context_commentary.py tests/test_vlm_context_runner.py tests/test_joint_vlm_pilot.py tests/test_qwen_client.py -q`; Expected: all pass. Commit task.

### Task 4: Comparative pilot and acceptance

**Files:** Create `docs/2026-10-18-vlm-context-pilot-acceptance.md`; update `docs/README.md`. Only synthetic fixtures/source/docs in Git.

- [ ] Review the two recordings for passport provenance, create ignored manifest for the same 72 seconds and capture dry run. Expected: zero API calls.
- [ ] Run at most six new calls, inspect raw/schema/content, then cache-only. Expected: zero new calls on replay; failures/unknowns remain visible, not silently retried. Record actual tokens/coverage/error comparison even if quality worsens.
- [ ] Run processor/understanding/Qwen/v2 regression tests and browser-check report. Expected: green tests and accessible clips/feed.
- [ ] Obtain fresh read-only final code review for changes since `2bebd2f`; fix material findings with RED→GREEN. Commit acceptance and verified changes; delete this plan's scratch ledger only after completion.
