# Итоги: harden-agent (попытка with-spec)

## 1. Модель и дата

- Модель: Claude Opus 5.5 (`claude-opus-5-5`)
- Дата: 15.11.2026
- Попытка: with-spec (через OpenSpec)

## 2. Запросы и исправления своих ошибок

- Запросов пользователя в сессии: **2** (основная задача и этот запрос на отчёт).
- Исправлений своих ошибок: **1**.
  - Команда сравнения вывода `--replay` с эталоном была составлена неверно. Эталон снимался с `--output`, поэтому `diff` нашёл лишнюю строку «Трасса сохранена». Пересравнил без этой строки — вывод совпал. Код, спецификацию и тесты исправлять не пришлось.

Не считаю ошибкой: в системе не было node/npm, поэтому сначала пришлось поставить Node.js v22.21.0 (официальный архив с nodejs.org, SHA-256 проверен) в `~/.local/node-v22.21.0-darwin-arm64`, и только потом openspec.

## 3. OpenSpec

| Параметр | Значение |
|---|---|
| Версия openspec | 2.0.0 |
| `openspec init` | `--tools claude` |
| Change | `openspec/changes/harden-agent/` (proposal.md, specs/agent/spec.md, design.md, tasks.md) |
| `openspec validate harden-agent --strict --no-interactive` | valid **с 1-й попытки**; повторная проверка после реализации тоже valid |
| Требований в spec.md | 6 (R1–R6, все с MUST) |
| Сценариев в spec.md | 10 (R1 — 1, R2 — 1, R3 — 2, R4 — 3, R5 — 2, R6 — 1), формат WHEN/THEN |
| Задачи в tasks.md | 9 из 9 отмечены `[x]`; `openspec list` показывает `✓ Complete` |

## 4. Что изменено в agent.py

| Треб. | Где (функция) | Как |
|---|---|---|
| R1 | `run_allowed_tool`; `run_agent` → `missing_ids()` | В ошибку `not_found` добавлено поле `doc_id`. `missing_ids` собирается из событий `read_doc` с кодом `not_found`: без повторов, по возрастанию. |
| R2 | `run_agent` (цикл выполнения инструментов) | Вызов инструмента обёрнут в `try/except Exception`. Исключение и не-dict результат превращаются в `{"error": {"code": "tool_failure", "message": "<Тип>: <текст>"}}`. Вызов засчитывается в `tool_calls`, цикл продолжается. Добавлен необязательный параметр `tool_fn=run_allowed_tool`, через который тесты подставляют сбой. |
| R3 | `run_agent` → `finish()`, `read_ids()`, событие `tool` | У каждого события `tool` есть `status`: `"ok"`/`"error"`. Все выходы идут через `finish()`, поэтому `read_ids` (по возрастанию), `missing_ids` и `tool_errors` есть при любом `stop_reason`. |
| R4 | `run_agent` (ветка финального ответа), `CITED_ID_RE`, `MAX_SOURCE_REMARKS = 2` | Прочитанными считаются только `read_doc` со статусом `ok`. В ответе ищутся все ссылки `Dnn`, а не только первая в скобках. Замечание модели перечисляет конкретные ID (событие `validation` с `ids`); таких замечаний за запуск не больше 2. Третий неподтверждённый ответ даёт `stop_reason = "unverified_sources"`, `answer = null`. Прежние условия проверки (был поиск; найденное прочитано) сохранены. |
| R5 | `run_agent` | Логика лимитов не изменена. `budget_exhausted` и `tool_budget_exhausted` теперь возвращаются через `finish()` с `answer = null`. |
| R6 | `TOOLS`, `run_allowed_tool`, `REPLAY_RESPONSES`, `main` | Схемы инструментов, формат успешных результатов, записи replay и CLI не менялись. Консольный вывод `--replay` построчно совпадает с выводом до изменения. |

## 5. Размер agent.py

| | Строк |
|---|---|
| До | 225 |
| После | 257 (+32) |

## 6. Вывод тестов и replay

`python3 tests/test_agent.py`:

```
test_citing_missing_id_is_not_accepted (__main__.TestA1MissingDocument.test_citing_missing_id_is_not_accepted) ... ok
test_missing_id_in_final_result (__main__.TestA1MissingDocument.test_missing_id_in_final_result) ... ok
test_tool_returns_structured_not_found (__main__.TestA1MissingDocument.test_tool_returns_structured_not_found) ... ok
test_always_failing_tool_stays_within_limits (__main__.TestA2ToolFailure.test_always_failing_tool_stays_within_limits) ... ok
test_exception_becomes_tool_failure_and_loop_continues (__main__.TestA2ToolFailure.test_exception_becomes_tool_failure_and_loop_continues) ... ok
test_answer_accepted_after_reading (__main__.TestA3SourceVerification.test_answer_accepted_after_reading) ... ok
test_answer_without_search_is_not_accepted (__main__.TestA3SourceVerification.test_answer_without_search_is_not_accepted) ... ok
test_unverified_answer_stops_after_two_remarks (__main__.TestA3SourceVerification.test_unverified_answer_stops_after_two_remarks) ... ok
test_model_budget_exhausted (__main__.TestA4ModelBudget.test_model_budget_exhausted) ... ok
test_remarks_do_not_extend_model_budget (__main__.TestA4ModelBudget.test_remarks_do_not_extend_model_budget) ... ok
test_tool_budget_exhausted (__main__.TestA5ToolBudget.test_tool_budget_exhausted) ... ok
test_live_model_cannot_reach_network (__main__.TestNetworkIsBlocked.test_live_model_cannot_reach_network) ... ok
test_socket_connection_blocked (__main__.TestNetworkIsBlocked.test_socket_connection_blocked) ... ok
test_replay_cli_output (__main__.TestReplayRegression.test_replay_cli_output) ... ok
test_replay_run_agent (__main__.TestReplayRegression.test_replay_run_agent) ... ok
test_successful_result_shapes (__main__.TestToolInterfaceCompat.test_successful_result_shapes) ... ok
test_tool_schema (__main__.TestToolInterfaceCompat.test_tool_schema) ... ok

----------------------------------------------------------------------
Ran 17 tests in 0.009s

OK
```

`python3 agent.py --replay`, кратко:

- `stop_reason`: `final_answer`
- вызовов модели: 4; вызовов инструментов: 4 (2 × `search_docs`, 2 × `read_doc`)
- замечаний о непрочитанных источниках: 1 (после 2-го шага модели, как и до изменения)
- `read_ids`: `["D01", "D02"]`; `missing_ids`: `[]`; `tool_errors`: 0
- ответ тот же, что до изменения (ссылки D01:1-3, D02:1-2)

## 7. Проверки A1–A5 и регрессия

| Проверка | Что проверяет тест | Результат |
|---|---|---|
| A1 | `read_doc` с `D99` → `not_found` с `doc_id`; `missing_ids == ["D99"]`, `read_ids` отсортированы, `tool_errors == 1`, статусы событий верные; ответ со ссылкой на отсутствующий D99 не принимается | PASS (3 теста) |
| A2 | Исключение в инструменте → `tool_failure` в журнале и в истории модели, цикл продолжается до `final_answer`, сбойный вызов засчитан; постоянно падающий инструмент не выходит за лимиты | PASS (2 теста) |
| A3 | Ссылка на непрочитанный D02 → ровно 2 замечания с ID `D02`, затем `unverified_sources`, `answer = null`; ответ без поиска не принимается; после чтения ответ принимается | PASS (3 теста) |
| A4 | Исчерпание `max_model_calls` → `budget_exhausted`, `answer = null`, ровно N вызовов модели, есть поля сводки; замечания не увеличивают бюджет | PASS (2 теста) |
| A5 | Пакеты по 5 вызовов при лимите 12 → `tool_budget_exhausted`, третий пакет не выполнен (`tool_calls == 10`), `answer = null` | PASS (1 тест) |
| Регрессия `--replay` | `run_agent` с replay: 4/4 вызова, тот же ответ, `read_ids == ["D01","D02"]`; `main()` с `--replay`: последовательность строк шагов совпадает с эталоном | PASS (2 теста) |
| Доп. R6 | Схемы `search_docs`/`read_doc` и формат успешных результатов не изменились | PASS (2 теста) |
| Доп. сеть | Сокеты и `urllib` заблокированы; живой клиент не может выйти в сеть | PASS (2 теста) |

Итого: 17 из 17 PASS.

## 8. Что не сделано или сделано не полностью

- **Расшифровка A1–A5.** В change-brief.md написано только «Тесты A1–A5 (из ДЗ)», без описания. Открывать соседние папки было запрещено, поэтому сопоставление A1–A5 с R1/R2/R4/R5 моё (оно записано в proposal.md). Если в ДЗ A1–A5 означают другое, тесты нужно сверить.
- **Живой режим (`--live`, `--ping`) не проверялся:** сети и ключа в задаче нет. Клиент API не менялся.
- **Change не архивирован** (`openspec archive` не выполнялся), `openspec/specs/` пуст — в задаче этого не было.
- **Не выполнялся `base.sha256`.** Бриф упоминает хеши исходного кода в `base.sha256`, но этого файла в папке нет, так что исходный `agent.py` по хешу не сверялся.
- **Ошибка сериализации результата не перехватывается.** Если подставленный `tool_fn` вернёт dict с несериализуемым в JSON содержимым, процесс упадёт уже вне инструмента, на `json.dumps`. Стандартный `run_allowed_tool` такого не возвращает.
- **Ужесточение R4.** Теперь отклоняется любое упоминание непрочитанного `Dnn` в ответе, даже без номеров строк (например, «см. D06»). Это сознательное решение по R4, но поведение отличается от прежнего.
- **Node.js и openspec остались вне рабочей папки.** Node.js лежит в `~/.local/node-v22.21.0-darwin-arm64`, openspec установлен туда же глобально. Оба остались на диске.
