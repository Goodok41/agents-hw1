# Результаты: with-spec

**Модель и дата:** Claude Sonnet 5.5, 15.11.2026, with-spec

## Взаимодействие
- Запросов пользователя: 1 (исходное задание).
- Исправлений с вашей стороны: 0.

## OpenSpec
- Версия: 2.0.0 (`openspec init --tools claude` выполнен, openspec вызван по пути ~/.local/node-v22.21.0-darwin-arm64/bin/openspec, в PATH его не было).
- `openspec validate harden-agent --strict --no-interactive`: valid с **1-й попытки**; повторная проверка после реализации тоже valid.
- Требований: 6 (R1–R6), сценариев: 13 (включая A1–A5 и регрессию --replay).
- Задач в tasks.md: 10, отмечены [x] все 10.

## Что изменено по R1–R6 (agent.py)
- R1: `read_doc` с неизвестным ID возвращает `not_found` (с полем `doc_id`); ID попадает в `missing_ids`.
- R2: новая обёртка `call_tool`: любое исключение инструмента → `{"error":{"code":"tool_failure",...}}`, цикл продолжается.
- R3: у событий `tool` есть `status` (ok/error); в результате `read_ids` (по возрастанию), `missing_ids`, `tool_errors`; сборка результата единой функцией `finish` во всех ветках.
- R4: замечание модели с конкретными непрочитанными ID не более 2 раз (`MAX_SOURCE_NOTICES`); затем `unverified_sources`, `answer = null`.
- R5: логика `budget_exhausted` / `tool_budget_exhausted` сохранена, `answer = null`.
- R6: `TOOLS`, CLI и `--replay` не менялись по поведению.

## Размер agent.py
- До: 225 строк. После: 255 строк.

## Тесты (python3 -m unittest discover -s tests -v)
```
test_a1_ocr_and_external_api_confirmed_by_d01_d02 (test_agent.AgentTests.test_a1_ocr_and_external_api_confirmed_by_d01_d02) ... ok
test_a2_license_price_absent_not_invented (test_agent.AgentTests.test_a2_license_price_absent_not_invented) ... ok
test_a3_unknown_id_and_bad_arguments_structured_errors (test_agent.AgentTests.test_a3_unknown_id_and_bad_arguments_structured_errors) ... ok
test_a4_persistent_failure_ends_with_clear_status (test_agent.AgentTests.test_a4_persistent_failure_ends_with_clear_status) ... ok
test_a4_read_doc_failure_is_recorded_and_agent_recovers (test_agent.AgentTests.test_a4_read_doc_failure_is_recorded_and_agent_recovers) ... ok
test_a5_reduced_limits_stop_loop_without_answer (test_agent.AgentTests.test_a5_reduced_limits_stop_loop_without_answer) ... ok
test_r4_notice_names_ids_then_unverified_sources_after_two (test_agent.AgentTests.test_r4_notice_names_ids_then_unverified_sources_after_two) ... ok
test_regression_replay_cli_works_as_before (test_agent.AgentTests.test_regression_replay_cli_works_as_before) ... ok
test_regression_replay_run_agent_and_tool_interface (test_agent.AgentTests.test_regression_replay_run_agent_and_tool_interface) ... ok

----------------------------------------------------------------------
Ran 9 tests in 0.042s

OK
```

## python3 agent.py --replay (кратко)
Код возврата 0; 4 вызова модели (поиск ×2 → отклонённый ответ без чтения → read_doc D01, D02 → ответ); `stop_reason: final_answer`; ответ ссылается на D01:1-3 и D02:1-2. Как и раньше, первый ответ записи отклоняется проверкой источников (теперь это 1 из 2 допустимых замечаний).

## Таблица проверок
| Сценарий | Тест | Результат |
|---|---|---|
| A1 OCR и внешний API | test_a1_ocr_and_external_api_confirmed_by_d01_d02 | PASS |
| A2 цена лицензии | test_a2_license_price_absent_not_invented | PASS |
| A3 D99 и неверные аргументы | test_a3_unknown_id_and_bad_arguments_structured_errors | PASS |
| A4 сбой read_doc | test_a4_read_doc_failure_is_recorded_and_agent_recovers, test_a4_persistent_failure_ends_with_clear_status | PASS |
| A5 уменьшенный лимит | test_a5_reduced_limits_stop_loop_without_answer | PASS |
| Регрессия --replay | test_regression_replay_cli_works_as_before, test_regression_replay_run_agent_and_tool_interface | PASS |
| (доп.) R4: 2 замечания → unverified_sources | test_r4_notice_names_ids_then_unverified_sources_after_two | PASS |

## Не сделано / ограничения
- Живая модель (`--live`) не проверялась: сеть и ключ не использовались.
- Проверка ссылок распознаёт только форму `[Dxx:…]` / `(Dxx:…)`, как в исходном коде; упоминания ID без номеров строк не проверяются.
- Счётчик замечаний R4 общий для всех причин (нет search_docs, непрочитанные источники), а не только для неверных ID.
- Добавлены поля результата и `doc_id` в ошибку `not_found`, а в журнал — событие validation с `ids`; это расширение формата трассы.
- A2 проверяет только заглушку: что агент с «правильной» моделью не выдумывает цену; поведение живой модели не гарантируется.
- Каталоги .agents/.claude/openspec созданы openspec init.
