# Приёмка UX/UI турниров, капитана и публичного сайта — 18 октября 2026

Локальная поставка в ветке `codex/tournament-captain-ux`. Рабочая база организатора и исходный checkout не изменялись. Развёртывание отдельно: применить новые миграции до `0026_registration_credentials`, собрать frontend и настроить внешние интеграции.

## Реализованные сценарии

| Роль | Результат |
|---|---|
| Зритель | Главная с датой, поиском/фильтрами и группами турниров, ближайшие игры, топ-5 квалифицированных игроков выбранного турнира из опубликованного издания. Команды, игроки и история имён из опубликованных протоколов; переходы сохраняют календарный контекст. Нулевой счёт отличается от неопубликованного. |
| Администратор | Быстрый черновик турнира или последовательная настройка, команды и люди внутри сценария, Excel с предпросмотром/исправлениями, постоянный состав и турнирная заявка отдельно, создание команды/зала прямо в форме матча. Видимость турнира включается явно. Приём и возврат версий заявок капитанов. |
| Админ+ | Очередь обработки с фильтрами и следующими действиями, готовность сторон, выдача ограниченных заданий капитанам, явная замена капитанского решения с причиной, техническое подтверждение и независимая публикация. Сравнение текущих и выбранных версий при публикации. |
| Капитан | Регистрация/верификация email/восстановление, приглашение или запрос владения, свои команды/игроки/Excel, предложения изменений общих карточек, отправка версий заявок, сопоставление своих кадров с UUID игроков и самостоятельное подтверждение стороны. |

## Границы данных

Ручной протокол и CV остаются независимы. Капитанское подтверждение не рассчитывает метрики и не публикует отчёт. Изменение другой стороны не откатывает уже сохранённые назначения; техническая заморозка проверяет обе стороны и открытые исправления. Изменение контекста/групп/доступа делает старое задание недействительным, подтверждённые версии сохраняются. Задание действует семь дней и затем требует перевыдачи.

Публичные профили читают только текущие опубликованные указатели протоколов активных публичных турниров. Закрытые импортированные атрибуты и фото не выдаются. Переименование справочника не переписывает имя уже опубликованного выступления. Архивирование самого справочника команды сохраняет историю её публичного участия; закрытие/архивирование турнира закрывает новые публичные readers.

Excel: `.xlsx`, до 5 МиБ файла / 25 МиБ распаковки, 512 частей, 64 колонок, 1000 участников, 10000 физических строк. Формулы не вычисляются. Совпадение имени не объединяет людей автоматически. Импорт добавляет состав, не перезаписывает общие карточки; проверка revisions и сохранённый request ID защищают повтор после потерянного ответа. Незавершённые импорты имеют срок семь дней и удаляются штатной командой cleanup, которую нужно запускать регулярно; результат завершённой команды остаётся для безопасного повтора.

## Внешние настройки и ограничения

Адресные подсказки проверены синтетическим провайдером: клавиатура, отмена устаревшего запроса, выбор точки, ручной ввод, сохранение контекста матча. Для Яндекса нужны ключи Suggest/Geocoder, секрет подписи и подходящие условия использования/хранения; реальный провайдер при этой приёмке не вызывался.

Письма проверены через зашифрованную outbox и синтетический транспорт. Нужны SMTP, Fernet key и регулярный запуск mail-worker; реальные письма при приёмке не отправлялись. SMTP допускает повторную доставку со стабильным Message-ID. Проверка конечной доставки в конкретной установке остаётся этапом её подключения.

Подключённый Processor, OCR, маски, S3 и Colab-ноутбук остаются будущей работой. Видеоаналитика получает внешний result.zip; UI не изображает прогресс несуществующего процессора.

## Проверки

Полный backend после исправлений review: **836 passed, 1 slow deselected, 176,99 с**; полный UI после исправления возврата календаря: **183 passed**. TypeScript и production-сборка без ошибок; новые публичные API — 3 теста. Весь E2E-набор: **26 passed, 1,8 мин**. После ревью повторены все затронутые и общие проверки; ошибок не осталось. Для E2E выделены база `aifootball_ux_e2e`, порт 8283 и отдельная папка сборки, без перезаписи `web/dist` работающей установки.

## Независимое ревью и исправления

Проверена вся ветка от `71308da` до `2f03653` отдельным reviewer (gpt-6-astra), без изменения данных. Три замечания воспроизведены четырьмя падающими тестами до исправления, затем 33 целевые проверки прошли:

- Критическое: повторная регистрация чужого ещё не подтверждённого email могла активировать первоначально заданный пароль. Каждая ссылка теперь содержит привязку к хешу пароля и имени именно своей регистрации; первое подтверждение атомарно применяет их и отменяет остальные ссылки. Проверены регистрация до/после владельца и безопасный повтор использованного токена. Миграция 0026: ранее выданные, но ещё не использованные ссылки верификации требуют повторной регистрации; подтверждённые учётные записи сохраняются.
- Существенное: новые импорт/версия проверки не закрывали старые задания капитанов. Теперь задания предыдущих результатов становятся устаревшими; сохранение/подтверждение и кадры закрываются, повторная выдача на старый результат отвергается. Неизменяемые подтверждения и опубликованные версии сохраняются.
- Существенное: ошибка Excel в ячейке имени могла стать обычной строкой. Парсер сохраняет признаки error cells; предпросмотр требует исправить или исключить затронутую строку и сохраняет остальные строки.

Внешние SMTP/Яндекс и развёртывание reviewer отнёс к проверкам конкретной установки. Числовой формат Excel `000` не равен текстовому номеру `007`: ведущие нули гарантированы для текстовых значений, число пользователь проверяет в предпросмотре. Отложенных замечаний reviewer нет.

## Журнал принятых решений — сквозной UX

- - Ruling: execute in a native managed worktree on a codex/ branch, copying only approved design docs and local private env — main has user edits and a running service — cost: separate checkout is the reviewable deliverable.
- - Ruling: preserve existing admin-only flows and test fixtures, add explicit publication for public test scenarios — new default remains draft — cost: fixture updates, no production data clearing.
- - Ruling: use an isolated E2E database and port for this branch because 8181 is already occupied — never reset/stop the existing E2E service — cost: small configurable test launcher change.
- Ruling: record actual successful test evidence directly instead of rerunning task-done helper — no new changes justify a duplicate test run.
- Task 2 Ruling: derive omitted nested team request_id from parent request ID — Pydantic random defaults otherwise break safe replay — regression covered.
- Task 3 Ruling: also bound XLSX physical rows to 10,000 and columns to 64 — sparse sheet dimensions otherwise cause unbounded iteration — cost: exceptionally sparse sheets must be compacted.
- Ruling: group pytest service paths before root parser paths — pytest 9 collection otherwise misses scoped fixture discovery — cost: command ordering only.
- Ruling: keep the existing visual tokens and component language — these are workflow extensions of the approved 15 October UI, no new visual identity or ImageGen assets — cost: visual continuity over a separate redesign.
- Ruling: derive the cursor sort key from PostgreSQL lower(), not Python lower() — collation rules can differ for international names — cost: one additional selected scalar, bounded query count.
- Ruling: make both existing E2E seed scripts respect the isolated database name and explicitly publish synthetic tournament pages — avoid touching the already-running E2E environment — cost: test harness configuration only.
- Ruling: preserve manual legacy coordinates and omit null selection token from command digest — existing clients and saved retry hashes must remain compatible — cost: legacy manual coordinates retain a manual provenance label.
- Ruling: use a persistent per-admin minute counter and stable configured signing secret — limits and tokens must work across processes — cost: one small migration/table; no permanent suggestion cache.
- Ruling: render modal editors in a portal with submit isolation and top-dialog focus handling — an inline hall otherwise nests forms and submits the surrounding match — regression RED→GREEN.
- Task 5: Ruling: add a journaled PUT /entries/{id}/roster command for new inline players plus full roster — existing POST /players then PUT roster could strand a person after failed validation or duplicate after a lost response; the new operation is atomic and UUID-based — cost if wrong: one additional internal API surface to maintain.
- Task 6: Ruling: queue filters cover actionable stages (not started / awaiting result / stale context / blocked quality / review / unpublished / published), while independently computed team-side readiness is shown within review — this avoids inventing processor progress and keeps SQL pagination/filter totals exact — cost if wrong: users filter the review stage rather than each captain-side combination.
- Task 7: Ruling: public identity/history uses only each match's currently published protocol pointer, matching the existing /public/protocols boundary. Superseded/unpublished versions do not become accessible through the new profiles — cost if wrong: users see historical appearances across currently published matches, not withdrawn protocol editions.
- Task 7: Ruling: public team metadata/roster is composed with the existing now team-filterable calendar; matches are not duplicated into a second embedded unpaged array. Roster/appearances use paginated public DTOs — cost if wrong: one extra public read in the team screen.
- Task 7: Ruling: an archived catalogue team remains identifiable through its Entry in a public active tournament, consistent with existing historical match readers; tournament draft/archive still returns 404 — cost if wrong: archiving a catalogue team does not hide its already published appearances.
- Final: Ruling: token-bound registration credentials are applied only when consuming that proof, not overwritten by another unverified registration — prevents both pre-claim and reverse registration races — cost if wrong: verification links issued before migration0026 require re-registration; verified accounts unaffected.
- Final: Ruling: imports and new review runs supersede earlier captain tasks in the same locked match; old confirmed versions/public pointers remain — captains must not finish a result replaced in the organizer workflow — cost if wrong: deliberately returning to an old review requires a new review of the desired confirmed result.
- Final: Ruling: numeric Excel display format 000 does not supply textual leading zeros; store shirt numbers as text — approved guarantee covers text values and raw values remain visible in preview — cost if wrong: users correct a formatted numeric number before import.
- Final: Ruling: live SMTP/Yandex and deployment remain installation checks, with clear configuration and synthetic verification — no credentials were supplied — cost if wrong: an integration issue could appear during deployment rather than this local acceptance.

## Журнал принятых решений — капитан

- Ruling: send token links in URL fragments, not query strings — fragments are not included in web access logs/referrers — cost: the captain UI reads the fragment before posting to verify/reset/accept.
- Ruling: encrypt outbox payloads with a configured Fernet key, erase them on delivery/expiry, retain only token hashes — configurable SMTP worker retries with stable Message-ID and no production sending during tests — cost: key and mail transport remain required deployment configuration.
- Ruling: captain profile edits create proposals; outside-name collisions block an import row and offer an organizer request without exposing foreign UUIDs/profiles — preserves shared identity — cost: organizer resolves ambiguous people.
- Ruling: keep uploaded image ownership separate and namespace upload keys by captain — prevents cross-account request ID claims — cost: small ownership table.
- Ruling: scope client CSRF and session-expiry events by audience, ignore responses from older sessions — separate cookies need separate client tokens — two regressions RED→GREEN.
- Ruling: track dirty state synchronously in useDraft — an initial passive effect could erase an edit before the next render — deterministic layout-effect regression RED→GREEN.
- Task 4: Ruling: task lifetime is seven days with dynamic context/grant/own-assignment checks on every read — spec requires expiry but gives no duration; old tasks remain history and require explicit reissue — cost if wrong: organizer may reissue earlier than desired.
- Task 4: Ruling: side fallback controls and final side summaries are delivered with Task 5's confirmation transaction — avoids a UI button without its atomic actor/audit behavior; no scope removed — cost if wrong: controls appear one implementation step later.
- Task 6: Ruling: the full cross-plan E2E gate and final whole-branch review run after remaining B/C/D1 integration — their navigation and queue changes share the reviewed UI, so testing only the captain milestone would be premature — cost if wrong: integration regressions are found at final acceptance. Full backend/UI regression running now; Task 6 completion remains pending that final gate.

## Проверка интерфейса и времени импорта

Просмотрены главная, команда/игрок, очередь Админ+ и подтверждение капитана на 1440/1024/390 px. Основные экраны без горизонтального переполнения; на телефоне данные и действия идут по одной колонке. Синтетический отсутствующий кадр имеет явное пустое состояние. Нативная проверка в браузере не обнаружила ошибок консоли.

Импорт 15 игроков с исправлением дублирующегося номера и потерей ответа после commit/восстановлением: **502 мс** в первом общем E2E и **486 мс** в следующем и **528 мс** в финальном общем прогоне. Это время автоматизированных действий на локальной машине, без подготовки файла и времени решения человека. Ориентир «2 минуты для пользователя» не подтверждается этим замером.

Возврат из матча после «Ещё матчи» восстанавливает загруженную глубину календаря и прокрутку, перечитывая свежие публичные страницы. Добавлен отдельный тест RED→GREEN. Число восстанавливаемых страниц ограничено 100 (до 5000 матчей), содержимое протоколов в браузерном кеше не сохраняется.

- Final: Ruling: restore at most 100 previously loaded calendar pages from fresh API reads, not cached payloads — keeps return context while respecting withdrawals and bounding malformed session state — cost if wrong: calendars browsed past 5,000 matches need further manual loading on return.

## Итог поставки

Все локальные поставки A/A1/B/C/D0/D1/E1/E2/F реализованы и проверены. Ветка и worktree сохранены для просмотра и интеграции; рабочая установка не обновлялась. Для интеграции нужны миграции до 0026, сборка и настройка почты/карт.

- Final: Ruling: keep the verified implementation in its existing local managed branch/worktree — the requested implementation is complete, while merge/deployment was not requested — cost if wrong: integration into the working installation is a separate action.
