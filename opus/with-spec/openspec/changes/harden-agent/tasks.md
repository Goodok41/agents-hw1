# Tasks

## 1. Инструменты (R1, R2, R6)

- [x] 1.1 Добавить `doc_id` в ошибку `not_found` в `run_allowed_tool`, не меняя формат успешных результатов
- [x] 1.2 Добавить в `run_agent` параметр `tool_fn=run_allowed_tool` и обернуть вызов инструмента в `try/except Exception` с результатом `tool_failure`

## 2. Журнал и сводка (R3, R5)

- [x] 2.1 Записывать `status` (`ok`/`error`) в каждое событие `tool`
- [x] 2.2 Ввести `finish(...)` с полями `read_ids`, `missing_ids`, `tool_errors` и провести через неё все пути выхода (`final_answer`, `tool_budget_exhausted`, `budget_exhausted`, `unverified_sources`)

## 3. Проверка источников (R4)

- [x] 3.1 Считать прочитанными только `read_doc` со статусом `ok`; искать все ссылки `Dnn` в ответе
- [x] 3.2 Замечание модели с конкретными ID, не более 2 раз за запуск; событие `validation` с `ids`
- [x] 3.3 После 2 замечаний неподтверждённый ответ даёт `unverified_sources`, `answer = null`

## 4. Тесты и проверка

- [x] 4.1 Написать `tests/test_agent.py` (unittest, заглушка модели, сеть заблокирована): A1–A5 и регрессия `--replay`
- [x] 4.2 Запустить тесты и `python3 agent.py --replay`, сверить вывод с эталоном до изменения
