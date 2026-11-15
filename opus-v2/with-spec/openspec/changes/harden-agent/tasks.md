## 1. Инструменты (R1, R2, R6)

- [x] 1.1 Добавить `doc_id` в ошибку `not_found` у `read_doc`, не меняя схему `TOOLS`
- [x] 1.2 Добавить параметр `tool_fn` в `run_agent` и обернуть вызов инструмента в `try/except` → `tool_failure`
- [x] 1.3 Нестроковые `arguments` передавать в инструмент (→ `bad_arguments`) вместо `AgentError`

## 2. Журнал и итоговый результат (R3, R5)

- [x] 2.1 Добавить `status` (`ok`/`error`) в каждое событие `tool`
- [x] 2.2 Ввести общую функцию завершения с `read_ids`, `missing_ids`, `tool_errors` для всех `stop_reason`
- [x] 2.3 Сохранить проверки `budget_exhausted`/`tool_budget_exhausted` с `answer = None`

## 3. Проверка источников (R4)

- [x] 3.1 Расширить извлечение ссылок до любого `D\d{2}` как отдельного слова
- [x] 3.2 Формировать замечание с конкретными ID; ограничить замечания `MAX_SOURCE_REMARKS = 2`
- [x] 3.3 При превышении — `stop_reason = "unverified_sources"`, `answer = None`

## 4. CLI (R6)

- [x] 4.1 Печатать `read_ids`, `missing_ids`, `tool_errors` и понятное сообщение для `unverified_sources`
- [x] 4.2 Проверить, что `--replay` даёт прежний ответ и `final_answer`

## 5. Тесты

- [x] 5.1 Написать `tests/test_agent.py`: заглушка модели, `test_a1_...`–`test_a5_...` по таблице A1–A5
- [x] 5.2 Добавить регрессию `--replay` (подпроцесс, сравнение с исходным ответом)
- [x] 5.3 Запустить тесты, `python3 agent.py --replay` и `openspec validate harden-agent --strict`
