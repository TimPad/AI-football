# Решения и проверка локальной реализации

14 октября 2026. Ветка `codex/qwen-match-understanding`. Реализованы планы локального
понимания матча через Qwen и пилотных рейтингов игроков/турнира. Облачная инфраструктура
и спортивная калибровка не входят в подтверждённую готовность.

## Проверенный результат

- Backend: 662 теста прошли, 1 slow исключён; только выделенная тестовая БД.
- Интерфейс: 48 тестов в 15 файлах, production build успешен.
- Playwright: 10 сценариев прошли; после последнего изменения отображения неизвестных
  исходов отдельно повторён сценарий рейтингов — прошёл.
- Независимый численный verifier: 100/100 синтетических эталонных оценок по 5 ролям.
- Backup/restore: точная сверка данных, источников и файлов на отдельной E2E-базе.
  Рабочая БД организатора не очищалась и не мигрировалась.
- Каждый план прошёл отдельный свежий обзор. Девять важных ошибок рейтингов исправлены
  одной серией RED→GREEN и общей проверкой, без повторного обзора.

Подробные сценарии и ограничения: [рейтинги](player-ratings-local-acceptance.md),
[Qwen](2026-10-14-qwen-local-acceptance.md).

## Полный журнал решений

Ниже сохранены все строки `Ruling:` из обоих журналов исполнения в исходном порядке,
включая причину и цену решения. Более позднее решение может уточнять более раннее;
отложенный во время обзора Qwen модуль рейтингов затем реализован отдельным планом.
Формулировки сохранены дословно для аудита.

1. Ruling: Native managed worktree was created but filesystem sandbox denied writes — archived it and use codex/qwen-match-understanding in the authorized primary workspace — loss of directory isolation, mitigated by preserving external AGENTS.md change and committing named files only.
2. Task 2: Ruling: extra vlm includes python-dotenv as well as httpx — local .env promised to user and already used by service; no SDK install or dependency upgrades — slightly larger processor dependency set.
3. Task 3: Ruling: actual provider token usage may exceed a local estimate — preserve real usage in report and block further reservations, do not reject all completed CV/observations — token estimates are not a guaranteed financial cap; request count remains hard-bounded. RED→GREEN test_actual_token_overrun_remains_reportable.
4. Task 4: Ruling: detect_batches yields DetectionBatch(detections, frame_ids, timestamps), not bare DataFrame — an empty detection frame must still prove sampled coverage and EOS — minor internal API difference; detect_video compatibility preserved.
5. Task 7: Ruling: reconcile_windows requires explicit source_sha256 and accepts prompt_version — candidate identity must include source provenance absent from original signature — internal callers must pass it. resolve_identity accepts optional track_intervals to flag overlapping candidate UUID fragments; service still blocks invalid assignments independently.
6. Task 8/9: Ruling: implement exchange v2 (Task 9) before wiring Task 8 CLI — Task 8 packages a v2 result that the old validator would reject — ordering change only, avoids an unusable intermediate CLI.
7. Task 8: Ruling: pass normalized frame boxes/known CV teams and explicit crop-track links in prompts — raw images plus arbitrary track IDs cannot ground event participants — local prompt ceiling becomes 64 KiB inside unchanged 12 MiB request cap, modest additional tokens.
8. Task 10: Ruling: add explicit side_map_verified (backfill old confirmed/revised runs) and validate accepted track-event temporal overlap with a 2-second candidate tolerance — default side mapping and unrelated-time tracks must not produce identity claims — admins may need to correct an uncertain candidate before acceptance.
9. Task 10/11: Ruling: expose only non-secret has_understanding capability in run summaries and defer the large private JSON column — allow parallel gated UI fetch for v2 without new requests for legacy/ordinary-admin views, avoid loading VLM blobs for every summary — one optional DTO flag added; raw understanding stays separate.
10. Task 12: Ruling: available source is an excerpt; key absent and no Linux GPU — implement reproducible evaluator/container, record live API and sporting/CUDA checks as unavailable, never synthesize a success claim — actual provider compatibility and accuracy still require operator acceptance.
11. Task 12: Ruling: request execution is serial (within the planned cap of two), not a two-worker initial implementation — budget/receipt/repair commits have one owner in this first local release — throughput may be lower; no change to paid-attempt limits or output contract.
12. Final: Ruling: timeline truncation regraded Minor→Important — long valid reports hide phases and cannot be fully inspected — add bounded incremental disclosure; cost: more UI state, no API change.
13. Final: Ruling: endpoint/native/usage compatibility remains unverified without local credentials — keep live acceptance pending, not mocked success — provider incompatibility may require a later adapter change.
14. Final: Ruling: sports identity/event/state accuracy requires independent control labels/live processing — synthetic tests prove mechanics only — actual accuracy is unknown.
15. Final: Ruling: real-media/VFR synchronization was not independently judged — preserve source-time checks but do not assert broad VFR acceptance — some recordings may need normalization.
16. Final: Ruling: actual Linux GPU/CUDA/driver/preemption acceptance remains pending — emulated CPU smoke does not establish it — GPU rollout can reveal hardware/runtime issues.
17. Final: Ruling: S3/queue/lease/fencing/remote deployment remain subsequent infrastructure work — current operator starts CLI locally — no automatic cloud orchestration.
18. Final: Ruling: player ratings/actions/tournament module remains the approved next plan — Qwen review does not certify it — implement and verify separately.
19. Final: Ruling: web original-video storage/player/VK seek remain deferred — present source time and closed frames — no original playback on the service.
20. Final: Ruling: token estimates are not hard money guarantees — preserve actual/unknown usage and request cap — actual token cost may exceed estimate.
21. Final: Ruling: serial calls remain the accepted first-release choice — single writer for receipts and budget — lower throughput than two workers.
22. Final: Ruling: authorized primary checkout/feature branch remains the accepted sandbox fallback — preserve external AGENTS.md — weaker directory isolation.
23. Final: Ruling: reviewer did not repeat shared DB/full UI/container suites — executor's recorded outputs are the verification evidence — no second independent full-suite execution.
24. Ruling: Task 2 cannot extend 0011 after Task 1 migration tests have applied it — AGENTS requires new migrations and immutable migration history — add 0012_performance_actions, shift tournament ratings to 0013; numbering-only cost.
25. Task 1: Ruling: each participation save creates an immutable version (draft or confirmed), with optimistic checks on both participation and match revisions — preserve snapshots/audit rather than editing an existing record — extra version rows per save. Explicit clock_basis and manual analysis_scope prevent treating an excerpt/observed_s as full participation; cross-axis conversion remains rejected without a mapping.
26. Task 6: Ruling: no existing match stage taxonomy exists — add nullable administrator-entered stage_label in new migration 0013 and snapshot it; never infer stage from regulation variant — extra optional field in match editing. Public reference is built solely from published input pointers and an explicitly approved policy; publishing the resulting public-scope snapshot approves that reference edition. Private snapshots cannot be published by flipping visibility — one additional calculation before public publication.
27. Task 4 clarification: Ruling: the prior of 10 observations is applied to success/attempt percentages, not added as ten seconds to count/time rates — the specified smoothing equation has attempts as its denominator, while per10 rates retain count/eligible seconds and empirical percentiles — short playing-time rates may vary more; minimum exposure and sporting calibration remain necessary.
28. Task 8: Ruling: a fully annotated real match, independent real role cohorts and coach are not available; the user authorized demonstration labels — complete reproducible technical/synthetic acceptance and mark sporting calibration explicitly pending rather than invent full-match ground truth — the pilot weights, event completeness and explanatory usefulness remain unvalidated on real matches. Tournament-wide tactical team-phase aggregation is not delivered by the player ratings API; current team reports remain match/period CV views and the architecture/acceptance now say so.
29. Final: Ruling: sporting validity and coach acceptance need real annotated matches and independent role cohorts — deliver reproducible technical pilot with sporting acceptance explicitly pending — actual ranking quality and usefulness remain unknown.
30. Final: Ruling: explanation usefulness to coaches was not judged — retain tested UUID/role/action provenance without claiming coaching acceptance — examples may need redesign after coach review.
31. Final: Ruling: live Qwen accuracy and paid provider compatibility were outside the ratings review — retain offline-tested integration with live acceptance pending — provider behavior and real accuracy may require changes.
32. Final: Ruling: CUDA/cloud/Connected Processor/OCR/masks/S3/Colab remain subsequent work — deliver local operator-driven processing and imported reports — no automatic GPU/cloud pipeline or measured preemption acceptance.
33. Final: Ruling: learned expected-value metrics, opponent adjustment and cross-tournament talent comparison remain future work — present relative pilot efficiency within a compatible edition — cannot infer calibrated player strength from these scores.
34. Final: Ruling: tournament-wide tactical team-phase aggregation is outside the delivered player API — document current team views as match/period CV reports — no tournament tactical phase summary yet.
35. Final: Ruling: previous Qwen implementation is outside this fresh ratings review range — rely on its completed separate fresh review and regression pass — ratings reviewer supplies no second independent certification of Qwen.
36. Final: Ruling: production latency and capacity were not measured — describe this as local technical acceptance — hosting sizing and load behavior remain unverified.

## Отложенные мелкие замечания

В обоих свежих финальных обзорах таких замечаний нет. Перечисленные выше ограничения
продукта и приёмки не объявлены выполненными.
