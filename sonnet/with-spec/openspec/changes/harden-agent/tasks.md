## 1. Инструменты (R1, R2)

- [x] 1.1 `read_doc`: ошибка `not_found` содержит запрошенный `doc_id`
- [x] 1.2 Обёртка `call_tool`: исключение → `{"error": {"code": "tool_failure", ...}}`

## 2. Журнал и итог (R3)

- [x] 2.1 В событие `tool` добавить `status` (`ok`/`error`)
- [x] 2.2 Единая функция сборки результата с `read_ids`, `missing_ids`, `tool_errors` во всех ветках

## 3. Проверка источников и лимиты (R4, R5)

- [x] 3.1 Замечание с конкретными непрочитанными ID, не более 2 раз за запуск
- [x] 3.2 После лимита замечаний: `stop_reason = "unverified_sources"`, `answer = null`
- [x] 3.3 Сохранить `budget_exhausted` и `tool_budget_exhausted` с `answer = null`

## 4. Совместимость и тесты (R6)

- [x] 4.1 `TOOLS`, CLI и `--replay` без изменений поведения
- [x] 4.2 `tests/test_agent.py`: A1–A5 и регрессия `--replay`
- [x] 4.3 Запустить тесты, `--replay`, `openspec validate harden-agent --strict --no-interactive`
