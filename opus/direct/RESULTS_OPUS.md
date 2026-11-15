# Итоги: попытка direct

## 1. Модель и дата

- Модель: Claude Opus 5.5 (`claude-opus-5-5`)
- Дата: 15.11.2026
- Попытка: **direct**, без спецификации и плана. Работа шла только в папке `direct/`, папку `with-spec/` я не открывал.

## 2. Запросы и исправления

- Запросов пользователя в сессии: **2**. Первый — реализовать изменение и тесты, второй — этот отчёт.
- Исправлений своих ошибок: **2**. Ни одно из них не затрагивает логику agent.py:
  1. Первую команду чтения файлов запустил в родительской папке `hw1-opus/`, где их нет. Нашёл их в `direct/` и перечитал оттуда.
  2. В тесте `test_a5_trace_status_and_summary_fields` был лишний цикл `for stop in ("final_answer",)`. Заменил его прямым `assertEqual`. Это косметика, результат теста не изменился.
- После написания кода агент правок не потребовал: все 16 тестов прошли с первого запуска.

## 3. Что изменено в agent.py

| Треб. | Где в коде | Как |
|---|---|---|
| R1 | `run_allowed_tool` | Для неизвестного ID `read_doc` возвращает `{"error": {"code": "not_found", "message": ..., "doc_id": <ID>}}`. Поле `doc_id` добавлено. `source_summary` собирает такие ID в `missing_ids`. |
| R2 | новая `safe_run_tool`, вызов в `run_agent` | Обёртка над `run_allowed_tool` с `try/except Exception`. Исключение превращается в `{"error": {"code": "tool_failure", "message": "Сбой инструмента: <тип>."}}`, текст исключения наружу не уходит. Вызов засчитывается в `tool_calls`, цикл продолжается в пределах лимитов. |
| R3 | новые `tool_status`, `source_summary`; вложенная `finish` в `run_agent` | Каждое событие `tool` в `trace` получает `status`: `"ok"` или `"error"`. `finish()` собирает итог для любого `stop_reason` и добавляет `read_ids` (успешные `read_doc`, по возрастанию), `missing_ids` (`not_found`, по возрастанию) и `tool_errors` (число событий со статусом `error`). |
| R4 | `run_agent`, ветка финального ответа; новые `cited_ids_in`, `CITATION_GROUP`, `CITATION_ID`, `MAX_SOURCE_REMARKS = 2` | Ссылки ищутся внутри `[...]` и `(...)`, поддерживаются форматы `[D01:1-3; D02:1-2]`, `(D01, D02)`, `(D01)`. Раньше в квадратных скобках учитывался только первый ID. Непрочитанные ID = ссылки минус `read_ids`. Замечание модели перечисляет их поимённо. После 2 замечаний ответ отклоняется: `stop_reason = "unverified_sources"`, `answer = None`. Прежние проверки («нужен search_docs», «найденное нужно прочитать») сохранены и расходуют тот же счётчик. В `trace` событие `validation` теперь содержит `unread_ids`. |
| R5 | `run_agent` | Проверки лимитов не менялись: `tool_budget_exhausted` срабатывает до выполнения пачки вызовов, `budget_exhausted` — по `max_model_calls`, в обоих случаях `answer = None`. Замечания R4 тратят вызовы модели из того же бюджета. |
| R6 | `TOOLS`, `run_allowed_tool`, `main`, `REPLAY_RESPONSES` | Схемы инструментов, формат успешных ответов, CLI и запись replay не менялись. В консоли `--replay` изменилась только строка проверки: было `[проверка] Источники ещё не прочитаны...`, стало `[проверка 1/2] Источники не прочитаны: D01, D02. Нужен read_doc.` |

## 4. Размер agent.py

| | Строк |
|---|---|
| До | 225 |
| После | 267 |
| Разница | +42 |

Файл тестов `tests/test_agent.py` — 229 строк.

## 5. Вывод запусков

### `python3 tests/test_agent.py`

```
test_a1_direct_tool_call (__main__.TestAgent.test_a1_direct_tool_call) ... ok
test_a1_unknown_doc_id_is_not_found_and_in_missing_ids (__main__.TestAgent.test_a1_unknown_doc_id_is_not_found_and_in_missing_ids) ... ok
test_a2_tool_exception_becomes_tool_failure_and_loop_continues (__main__.TestAgent.test_a2_tool_exception_becomes_tool_failure_and_loop_continues) ... ok
test_a2_tool_failure_respects_limits (__main__.TestAgent.test_a2_tool_failure_respects_limits) ... ok
test_a3_at_most_two_remarks_then_unverified_sources (__main__.TestAgent.test_a3_at_most_two_remarks_then_unverified_sources) ... ok
test_a3_citation_formats (__main__.TestAgent.test_a3_citation_formats) ... ok
test_a3_citation_of_missing_doc_is_rejected (__main__.TestAgent.test_a3_citation_of_missing_doc_is_rejected) ... ok
test_a3_remark_names_unread_ids_then_success (__main__.TestAgent.test_a3_remark_names_unread_ids_then_success) ... ok
test_a4_limits_not_relaxed_by_remarks (__main__.TestAgent.test_a4_limits_not_relaxed_by_remarks) ... ok
test_a4_model_budget_exhausted (__main__.TestAgent.test_a4_model_budget_exhausted) ... ok
test_a4_tool_budget_exhausted (__main__.TestAgent.test_a4_tool_budget_exhausted) ... ok
test_a5_summary_fields_present_on_every_stop_reason (__main__.TestAgent.test_a5_summary_fields_present_on_every_stop_reason) ... ok
test_a5_trace_status_and_summary_fields (__main__.TestAgent.test_a5_trace_status_and_summary_fields) ... ok
test_r6_tool_interface_unchanged (__main__.TestAgent.test_r6_tool_interface_unchanged) ... ok
test_replay_regression_cli (__main__.TestAgent.test_replay_regression_cli) ... ok
test_replay_regression_run_agent (__main__.TestAgent.test_replay_regression_run_agent) ... ok

----------------------------------------------------------------------
Ran 16 tests in 0.004s

OK
```

### `python3 agent.py --replay` (кратко)

| Поле | Значение |
|---|---|
| Код выхода | 0 |
| `stop_reason` | `final_answer` |
| Вызовов модели | 4 |
| Вызовов инструментов | 4 (2 × `search_docs`, 2 × `read_doc`) |
| `read_ids` | `["D01", "D02"]` |
| `missing_ids` | `[]` |
| `tool_errors` | 0 |
| Замечаний R4 | 1 из 2: первый ответ ссылался на D01 и D02 до их чтения |

Ответ совпадает с ответом до изменений и ссылается на (D01:1-3) и (D02:1-2).

## 6. Проверки A1–A5 и регрессия

Текста A1–A5 в `change-brief.md` нет, там только «Тесты A1-A5 (из ДЗ)». Сопоставление A1–A5 с R1–R5 — моя интерпретация.

| Проверка | Тест | Что проверяет | Итог |
|---|---|---|---|
| A1 (R1) | `test_a1_unknown_doc_id_is_not_found_and_in_missing_ids` | `read_doc("D99")` → `status=error`, `code=not_found`, `doc_id=D99`; `missing_ids=["D99"]`, `read_ids=["D07"]`, ответ принят | PASS |
| A1 (R1) | `test_a1_direct_tool_call` | Прямой вызов `run_allowed_tool` с `D42` → `not_found` | PASS |
| A2 (R2) | `test_a2_tool_exception_becomes_tool_failure_and_loop_continues` | `RuntimeError` в инструменте → `tool_failure` без текста исключения; цикл дошёл до `final_answer`; `tool_errors=1`; сбой не попадает в `missing_ids` | PASS |
| A2 (R2) | `test_a2_tool_failure_respects_limits` | Инструмент падает постоянно → `budget_exhausted`, `answer=None`, без падения процесса | PASS |
| A3 (R4) | `test_a3_remark_names_unread_ids_then_success` | Замечание называет D02 и не называет прочитанный D01; после чтения D02 ответ принят | PASS |
| A3 (R4) | `test_a3_at_most_two_remarks_then_unverified_sources` | Ровно 2 замечания с D03 и D05, на третий раз → `unverified_sources`, `answer=None` | PASS |
| A3 (R4) | `test_a3_citation_of_missing_doc_is_rejected` | Ссылка на отсутствующий D99 не проходит → `unverified_sources` | PASS |
| A3 (R4) | `test_a3_citation_formats` | Разбор `[D01:1-3; D02:1-2]`, `(D03, D04)`, `(D05)`; простое упоминание D99/D98 не считается ссылкой | PASS |
| A4 (R5) | `test_a4_model_budget_exhausted` | Модель бесконечно зовёт инструменты → `budget_exhausted`, `answer=None`, ровно `max_model_calls` вызовов | PASS |
| A4 (R5) | `test_a4_tool_budget_exhausted` | Пачка вызовов превышает `max_tool_calls` → `tool_budget_exhausted`, `answer=None`, лишние вызовы не выполнены | PASS |
| A4 (R5) | `test_a4_limits_not_relaxed_by_remarks` | Замечания R4 не дают лишних вызовов модели → `budget_exhausted` | PASS |
| A5 (R3) | `test_a5_trace_status_and_summary_fields` | `status` у каждого события `tool` (ok/error для `unknown_tool`, пустого `doc_id`, `D77`); `read_ids=["D01","D06"]` по возрастанию; `missing_ids=["D77"]`; `tool_errors=3` | PASS |
| A5 (R3) | `test_a5_summary_fields_present_on_every_stop_reason` | `read_ids`, `missing_ids`, `tool_errors` есть при `budget_exhausted`, `tool_budget_exhausted` и `unverified_sources` | PASS |
| R6 | `test_r6_tool_interface_unchanged` | Имена и обязательные параметры `search_docs`/`read_doc`, поля успешного `read_doc` | PASS |
| Регрессия `--replay` | `test_replay_regression_run_agent` | Replay через `run_agent`: `final_answer`, 4 + 4 вызова, `read_ids=["D01","D02"]`, одно событие `validation` | PASS |
| Регрессия `--replay` | `test_replay_regression_cli` | `main()` с `--replay`: код 0, `stop_reason: final_answer`, ссылка `(D02:1-2)` в выводе | PASS |

Итого: 16 тестов, 16 PASS, 0 FAIL. Сеть в тестах заблокирована: `build_opener` подменён функцией, которая вызывает ошибку.

## 7. Что не сделано или сделано не полностью

- **A1–A5 восстановлены по смыслу.** Формулировок из ДЗ у меня не было, тесты построены по R1–R5. Если в ДЗ проверки другие, тесты нужно с ними сверить.
- **Режим `--live` не проверялся.** Сеть была запрещена. `make_live_model` я не менял, но новую логику с живой моделью не запускал.
- **Ссылки распознаются эвристически.** Учитываются только ID в `[...]`/`(...)`, за которыми идёт `:`, `,`, `;` или конец скобки. ID без скобок (например, «см. D03») проверкой не ловится, и такой ответ пройдёт. Диапазоны вида `D01-D02` не разбираются. `(см. D01)` считается ссылкой.
- **Счётчик замечаний общий.** «Не более 2 раз» относится ко всем замечаниям проверки источников, включая прежние общие («нужен search_docs»), а не только к замечаниям с конкретными ID. Это моя трактовка R4.
- **`missing_ids` собирается только из `read_doc`.** ID, упомянутые в документах (например, D99 в D07), туда не попадают, пока модель не попробует их прочитать.
- **`doc_id` не нормализуется.** Например, `" D01"` с пробелом даст `not_found` с этим же значением. Так было и до изменений.
- **В консоль новые поля не выводятся.** `main()` не печатает `read_ids`, `missing_ids`, `tool_errors`, чтобы не менять вывод `--replay` (R6). Они есть только в результате `run_agent` и в JSON при `--output`.
- **Причина сбоя инструмента сохраняется не полностью.** При `tool_failure` в журнал попадает только тип исключения, текст и traceback не сохраняются.
- **Diff не зафиксирован.** Папка не git-репозиторий. Копия исходного agent.py лежит во временной папке сессии и может быть удалена.
