# Итог: direct-попытка

**Модель и дата:** Claude Sonnet 5.5, 15.11.2026, direct (без спецификации и плана).

**Запросы и исправления:** 1 запрос пользователя. Исправлений моих — 1: первый прогон тестов дал одно падение (`test_a3_unknown_id_and_bad_arguments`). Сценарий был построен неверно: поиск «прокси» находит D07, и ответ без чтения D07 по старому правилу (найдено, но не прочитано) отклоняется. Я исправил сценарий теста (добавил чтение D07), а ожидаемые результаты и код агента не менял.

## Что изменено по R1–R6 ([agent.py](agent.py))
- **R1** — `run_allowed_tool`: для неизвестного ID `read_doc` возвращает `{"error": {"code": "not_found", ..., "doc_id": <ID>}}`. `summarize_tools` собирает такие ID в `missing_ids`.
- **R2** — новая `run_tool_safely`: `try/except Exception` вокруг инструмента даёт `{"error": {"code": "tool_failure", ...}}`. Цикл продолжается в рамках лимитов.
- **R3** — в событие `tool` добавлено `status` ("ok" или "error"). Новая `summarize_tools` считает `read_ids` (успешные `read_doc`, по возрастанию), `missing_ids` и `tool_errors`. Внутренняя `finish()` в `run_agent` добавляет эти поля во все возвращаемые результаты. `main` дополнительно печатает вызовы и `read_ids`/`missing_ids`.
- **R4** — в `run_agent` счётчик `rejections`. Ответ со ссылкой на непрочитанный ID, без поиска или с найденными, но непрочитанными документами отклоняется. Модели возвращается замечание с конкретными ID. Отклонений не больше 2 за запуск. На третьем `stop_reason = "unverified_sources"`, `answer = null`.
- **R5** — логика лимитов не тронута (`budget_exhausted`, `tool_budget_exhausted`, `answer = null`), только результат собирается через `finish()`.
- **R6** — схемы `TOOLS`, имена и аргументы `search_docs`/`read_doc`, `REPLAY_RESPONSES` и режим `--replay` не менялись.

**Строк agent.py:** до — 225, после — 261.

## Вывод `python3 tests/test_agent.py`
```
test_a1_ocr_then_external_api (__main__.TestA.test_a1_ocr_then_external_api) ... ok
test_a2_no_price_in_corpus (__main__.TestA.test_a2_no_price_in_corpus) ... ok
test_a3_citing_unknown_id_is_not_issued (__main__.TestA.test_a3_citing_unknown_id_is_not_issued) ... ok
test_a3_unknown_id_and_bad_arguments (__main__.TestA.test_a3_unknown_id_and_bad_arguments) ... ok
test_a4_persistent_failure_ends_with_clear_status (__main__.TestA.test_a4_persistent_failure_ends_with_clear_status) ... ok
test_a4_read_doc_failure_then_recovery (__main__.TestA.test_a4_read_doc_failure_then_recovery) ... ok
test_a5_model_call_limit (__main__.TestA.test_a5_model_call_limit) ... ok
test_a5_tool_call_limit (__main__.TestA.test_a5_tool_call_limit) ... ok
test_at_most_two_remarks_with_concrete_ids (__main__.TestR4.test_at_most_two_remarks_with_concrete_ids) ... ok
test_replay_cli_unchanged (__main__.TestRegression.test_replay_cli_unchanged) ... ok
test_replay_run_agent (__main__.TestRegression.test_replay_run_agent) ... ok
test_tool_interface_unchanged (__main__.TestRegression.test_tool_interface_unchanged) ... ok

----------------------------------------------------------------------
Ran 12 tests in 0.053s

OK
```

## `python3 agent.py --replay` (кратко)
- stop_reason: final_answer
- вызовы: модель = 4, инструменты = 4, ошибок = 0
- read_ids: ['D01', 'D02'], missing_ids: []
- В ходе записи один раз сработала проверка (ответ со ссылками до чтения), затем read_doc D01 и D02 и подтверждённый ответ. Как и раньше.

## Таблица проверок
| Сценарий | Тест | Результат |
|---|---|---|
| A1: OCR и внешний API | test_a1_ocr_then_external_api | PASS |
| A2: цена лицензии, в D03 её нет | test_a2_no_price_in_corpus | PASS |
| A3: D99 и неверные аргументы | test_a3_unknown_id_and_bad_arguments | PASS |
| A3: ссылка на D99 в ответе не выдаётся | test_a3_citing_unknown_id_is_not_issued | PASS |
| A4: сбой read_doc, затем восстановление | test_a4_read_doc_failure_then_recovery | PASS |
| A4: постоянный сбой, статус unverified_sources | test_a4_persistent_failure_ends_with_clear_status | PASS |
| A5: лимит вызовов модели | test_a5_model_call_limit | PASS |
| A5: лимит вызовов инструментов | test_a5_tool_call_limit | PASS |
| R4: не больше 2 замечаний с ID | test_at_most_two_remarks_with_concrete_ids | PASS |
| Регрессия --replay (CLI) | test_replay_cli_unchanged | PASS |
| Регрессия --replay (run_agent) | test_replay_run_agent | PASS |
| Регрессия: интерфейс инструментов | test_tool_interface_unchanged | PASS |

## Что не сделано или сделано не полностью
- `--live` и `--ping` не проверялись: сети и ключа нет.
- Правило «найдено через поиск, но не прочитано» оставлено из исходного кода. Честный ответ «сведений нет» без чтения найденных документов отклоняется. Он тоже тратит один из двух возвратов и может закончиться `unverified_sources`.
- Все отклонения проверки (не только по ссылкам на ID) делят общий лимит 2. Brief говорит о замечаниях с ID, поэтому это моя трактовка.
- Проверка ссылок распознаёт только формат `[D01:...]` / `(D01:...)`. Упоминание ID в тексте без скобок не проверяется.
- Тесты A3–A5 используют заглушки модели и подмену инструмента. Живая модель не проверялась, как и требовал brief.
- Печать `read_ids`/`missing_ids` в консоль `--replay` — небольшое добавление к выводу. Остальное поведение прежнее.
