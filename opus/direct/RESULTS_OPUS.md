# RESULTS_OPUS

- **Модель:** Claude Opus 5.5
- **Дата:** 15.11.2026
- **Режим:** direct (без спецификации и плана; change-brief.md, R1–R6 + таблица A1–A5)
- **Запросов пользователя:** 1
- **Исправлений с моей стороны:** 0 — все 13 тестов прошли с первого запуска, ничего чинить не пришлось. Ожидаемые результаты тестов не менялись.

## Что изменено по R1–R6

| Треб. | Функция | Как |
|---|---|---|
| R1 | `run_allowed_tool` | Ошибка `not_found` для неизвестного `doc_id` теперь содержит поле `doc_id`. `summarize_tools` собирает такие ID в `missing_ids`. Содержимое не подставляется. |
| R2 | новая `call_tool_safely` (вызывается из `run_agent`) | Оборачивает `run_allowed_tool` в `try/except Exception`; исключение превращается в `{"error": {"code": "tool_failure", "message": "Сбой инструмента <name>: <тип исключения>."}}`. Не-dict результат тоже даёт `tool_failure`. Вызов засчитывается в `tool_calls`, цикл продолжается в рамках лимитов. |
| R3 | `run_agent`, новая `summarize_tools` | У каждого события `tool` в трассе есть `status` (`ok`/`error`). Все варианты итогового результата (через внутреннюю `finish`) содержат `read_ids` (отсортированы), `missing_ids`, `tool_errors`. CLI печатает их строкой после `stop_reason`. |
| R4 | новая `unverified_ids`, константа `MAX_SOURCE_REMARKS = 2`, `run_agent` | Ссылка в скобках (`[D01:1-3]`, `(D02)`, `[D01, D02]`) допустима только на успешно прочитанный ID; упоминание без скобок — на прочитанный ID или на ID из `missing_ids` (например, «D99 не найден»). Прежние условия (нужен search_docs; если поиск что-то нашёл, нужно прочитать хотя бы один документ) сохранены. Модели отправляется замечание с конкретными ID, не больше 2 раз; при третьем неподтверждённом ответе — `stop_reason = "unverified_sources"`, `answer = None`. |
| R5 | `run_agent` | Лимиты из config.json не менялись; `budget_exhausted` / `tool_budget_exhausted` возвращаются с `answer = None` (через `finish`). |
| R6 | — | Схемы `TOOLS`, сигнатуры `run_allowed_tool` и `run_agent`, `REPLAY_RESPONSES`, CLI не менялись. Вывод `--replay` отличается от исходного только двумя добавлениями: к строке `[проверка]` дописано `ID: D01, D02`, и появилась строка `read_ids: … missing_ids: … tool_errors: …`. Сравнение делал через diff с выводом до изменения. |

**Строк agent.py:** до — 225, после — 274.

## Вывод тестов (`python3 tests/test_agent.py`)

```
test_a1_answer_citing_unread_doc_is_rejected_then_accepted_after_read (__main__.TestA1to5.test_a1_answer_citing_unread_doc_is_rejected_then_accepted_after_read) ... ok
test_a1_search_read_answer_confirmed_by_d01_d02 (__main__.TestA1to5.test_a1_search_read_answer_confirmed_by_d01_d02) ... ok
test_a2_invented_tariff_with_unread_source_is_not_returned (__main__.TestA1to5.test_a2_invented_tariff_with_unread_source_is_not_returned) ... ok
test_a2_license_price_absent_answer_reports_no_data (__main__.TestA1to5.test_a2_license_price_absent_answer_reports_no_data) ... ok
test_a3_citation_of_missing_d99_is_rejected (__main__.TestA1to5.test_a3_citation_of_missing_d99_is_rejected) ... ok
test_a3_unknown_d99_and_bad_arguments_structured_errors (__main__.TestA1to5.test_a3_unknown_d99_and_bad_arguments_structured_errors) ... ok
test_a4_persistent_read_doc_failure_stops_with_clear_status (__main__.TestA1to5.test_a4_persistent_read_doc_failure_stops_with_clear_status) ... ok
test_a4_read_doc_failure_recorded_and_agent_recovers (__main__.TestA1to5.test_a4_read_doc_failure_recorded_and_agent_recovers) ... ok
test_a5_model_call_limit_stops_loop (__main__.TestA1to5.test_a5_model_call_limit_stops_loop) ... ok
test_a5_tool_call_limit_stops_loop (__main__.TestA1to5.test_a5_tool_call_limit_stops_loop) ... ok
test_a5_unverified_answer_loop_is_bounded (__main__.TestA1to5.test_a5_unverified_answer_loop_is_bounded) ... ok
test_replay_cli (__main__.TestReplayRegression.test_replay_cli) ... ok
test_replay_run_agent_same_result (__main__.TestReplayRegression.test_replay_run_agent_same_result) ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.046s

OK
```

## `python3 agent.py --replay` (кратко)

- `stop_reason: final_answer`, код выхода 0
- Вызовы: модель — 4, инструменты — 4 (2× search_docs, 2× read_doc); 1 замечание проверки источников (`ID: D01, D02`) после ответа без чтения
- `read_ids: ['D01', 'D02'] missing_ids: [] tool_errors: 0`
- Ответ совпадает с исходным (цитаты `(D01:1-3)`, `(D02:1-2)`)

## Таблица A1–A5 + регрессия

| ID | Сценарий из брифа | Тест(ы) | Результат |
|---|---|---|---|
| A1 | «Что проверить после OCR и перед внешним API?» — поиск + чтение, ответ подтверждён D01/D02, видны прочитанные ID | `test_a1_search_read_answer_confirmed_by_d01_d02`, `test_a1_answer_citing_unread_doc_is_rejected_then_accepted_after_read` | PASS |
| A2 | «Сколько стоит лицензия DemoDesk?» — цены в D03 нет, тариф не выдуман, сказано об отсутствии сведений | `test_a2_license_price_absent_answer_reports_no_data`, `test_a2_invented_tariff_with_unread_source_is_not_returned` | PASS |
| A3 | Неизвестный ID D99 и неверные аргументы — структурированная ошибка без падения, нет выдуманного D99 | `test_a3_unknown_d99_and_bad_arguments_structured_errors`, `test_a3_citation_of_missing_d99_is_rejected` | PASS |
| A4 | Искусственный сбой read_doc — ошибка зафиксирована, ограниченное восстановление или понятный статус | `test_a4_read_doc_failure_recorded_and_agent_recovers`, `test_a4_persistent_read_doc_failure_stops_with_clear_status` | PASS |
| A5 | Уменьшенный лимит вызовов — остановка на лимите, нет бесконечного повтора и неподтверждённого ответа | `test_a5_model_call_limit_stops_loop`, `test_a5_tool_call_limit_stops_loop`, `test_a5_unverified_answer_loop_is_bounded` | PASS |
| Регрессия | `python agent.py --replay` работает как раньше | `test_replay_run_agent_same_result`, `test_replay_cli` | PASS |

## Что не сделано или сделано не полностью

- **A1/A2 с живой моделью не проверялись.** По брифу живая модель в тестах не используется, а `--live` не запускался (нет сети/ключа в задаче). Поэтому A1/A2 проверяют механизм (поиск → чтение → проверка источников → ответ) на заглушке. Что реальная модель на вопрос о цене честно скажет «нет сведений», тесты не доказывают — доказано только, что ответ со ссылкой на непрочитанный источник не будет выдан.
- **R4 проверяет только ID, а не содержание.** Если модель сошлётся на прочитанный D03 и при этом выдумает цену, проверка ID это пропустит. Сверки текста ответа с прочитанными строками нет.
- **Граница «ссылки» — моё решение.** Упоминание ID без скобок разрешено для ID из `missing_ids` (чтобы можно было написать «D99 не найден»). В скобках допустимы только прочитанные ID. Номера строк (`D01:9` при 4 строках) не проверяются.
- **Счётчик замечаний общий.** Лимит в 2 замечания распространяется и на прежние проверки «не было search_docs» / «найдено, но ничего не прочитано», а не только на непрочитанные ID.
- **Ошибка протокола не стала ошибкой инструмента.** Если `arguments` в вызове инструмента не строка или ID вызова дублируется, по-прежнему поднимается `AgentError` (CLI: «Остановка: …», код 2, без traceback). Это не `bad_arguments` в журнале. Неверный JSON внутри строки `arguments` даёт `bad_arguments`, как и требуется.
- **Вывод `--replay` дополнен** двумя строками (см. R6). Решения модели и итоговый ответ не изменились.
