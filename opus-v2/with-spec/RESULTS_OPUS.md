# RESULTS_OPUS — harden-agent

## Модель и условия
- Модель: **Claude Opus 5.5**
- Дата: **15.11.2026**
- Вариант: **with-spec**, полный бриф (`change-brief.md`, R1–R6 + таблица A1–A5)

## Счётчики
- Запросов пользователя: **1** (одно задание из 7 пунктов).
- Исправлений с моей стороны: **2**:
  1. `agent.py` — косметическая правка текста замечания (убрана повторяющаяся фраза «Сначала нужен search_docs»), до запуска тестов.
  2. `tests/test_agent.py` — в первом прогоне 1 из 14 тестов упал (`test_a3_non_string_arguments_do_not_crash`): в сценарии заглушки
     не хватало реплики модели (агент по R4 правильно выдал замечание «найдено, но не прочитано» и запросил ещё один ход).
     В сценарий добавлено чтение D01; ожидаемый результат (`bad_arguments`) не менялся. После правки — 14/14 OK.

## OpenSpec
- Версия: **openspec 2.0.0** (`~/.local/node-v22.21.0-darwin-arm64/bin/openspec`, в PATH не было), `openspec init --tools claude`.
- Change: `openspec/changes/harden-agent/` — `proposal.md`, `specs/agent/spec.md`, `design.md`, `tasks.md`.
- `openspec validate harden-agent --strict --no-interactive`: **valid с 1-й попытки**; повторная проверка после реализации — тоже valid.
- Требований: **7** (R1–R6 + «Acceptance checks A1-A5»); сценариев: **15** (10 для R1–R6 + 5 для A1–A5).
- Задачи в `tasks.md`: **14 из 14 отмечены [x]**.

## Что изменено по R1–R6 (agent.py)
- **R1**: ошибка `read_doc` для неизвестного ID — `{"error": {"code": "not_found", "message": ..., "doc_id": "D99"}}`; ID собирается в `missing_ids`.
- **R2**: новый `call_tool_safely` — любое исключение инструмента → `{"error": {"code": "tool_failure", "message": "<Тип>: <текст>"}}`, цикл продолжается.
  `run_agent(..., tool_fn=run_allowed_tool)` — точка внедрения для тестов. Нестроковые `arguments` теперь дают `bad_arguments`, а не `AgentError`
  (некорректные `id`/`type` вызова по-прежнему `AgentError`). Сбойный вызов засчитывается в `tool_calls`.
- **R3**: у каждого события `tool` есть `status` (`ok`/`error`); общая функция `finish()` добавляет `read_ids` (по возрастанию), `missing_ids`, `tool_errors` во всех ветках выхода.
- **R4**: ссылки извлекаются по `\bD\d{2}\b` (раньше только `[D01:`/`(D01)`); замечание перечисляет конкретные ID; `MAX_SOURCE_REMARKS = 2`;
  третье нарушение → `stop_reason = "unverified_sources"`, `answer = None`. Прежние условия (нет поиска; найдено, но не прочитано) сохранены и делят тот же счётчик.
- **R5**: проверки `budget_exhausted` / `tool_budget_exhausted` не изменены, `answer = None`.
- **R6**: `TOOLS`, `SYSTEM`, `REPLAY_RESPONSES`, live-клиент не менялись; `--replay` даёт тот же ответ. `main` дополнительно печатает `read_ids/missing_ids/tool_errors` и сообщение для `unverified_sources`.

## Размер agent.py
- До: **225** строк, после: **263** строки.

## Полный вывод тестов (`python3 -m unittest -v tests/test_agent.py`)
```
test_a1_answer_citing_unread_d02_is_not_accepted (tests.test_agent.TestAcceptance.test_a1_answer_citing_unread_d02_is_not_accepted) ... ok
test_a1_ocr_and_external_api_answer_confirmed_by_d01_d02 (tests.test_agent.TestAcceptance.test_a1_ocr_and_external_api_answer_confirmed_by_d01_d02) ... ok
test_a2_demodesk_license_price_absent_reported (tests.test_agent.TestAcceptance.test_a2_demodesk_license_price_absent_reported) ... ok
test_a2_invented_price_with_unread_source_not_returned (tests.test_agent.TestAcceptance.test_a2_invented_price_with_unread_source_not_returned) ... ok
test_a3_answer_with_content_of_d99_rejected (tests.test_agent.TestAcceptance.test_a3_answer_with_content_of_d99_rejected) ... ok
test_a3_non_string_arguments_do_not_crash (tests.test_agent.TestAcceptance.test_a3_non_string_arguments_do_not_crash) ... ok
test_a3_unknown_d99_and_bad_arguments_structured_errors (tests.test_agent.TestAcceptance.test_a3_unknown_d99_and_bad_arguments_structured_errors) ... ok
test_a4_read_doc_always_fails_clear_stop (tests.test_agent.TestAcceptance.test_a4_read_doc_always_fails_clear_stop) ... ok
test_a4_read_doc_failure_recovered (tests.test_agent.TestAcceptance.test_a4_read_doc_failure_recovered) ... ok
test_a5_reduced_limit_with_unverified_answers_no_answer (tests.test_agent.TestAcceptance.test_a5_reduced_limit_with_unverified_answers_no_answer) ... ok
test_a5_reduced_model_call_limit_stops (tests.test_agent.TestAcceptance.test_a5_reduced_model_call_limit_stops) ... ok
test_a5_reduced_tool_call_limit_stops (tests.test_agent.TestAcceptance.test_a5_reduced_tool_call_limit_stops) ... ok
test_replay_regression (tests.test_agent.TestReplayRegression.test_replay_regression) ... ok
test_replay_tool_interface_unchanged (tests.test_agent.TestReplayRegression.test_replay_tool_interface_unchanged) ... ok

----------------------------------------------------------------------
Ran 14 tests in 0.056s

OK
exit=0
```

## `python3 agent.py --replay` (кратко)
- Код выхода 0; модель 1 → 2× `search_docs` (ok); модель 2 → финальный ответ без чтения → `[проверка 1/2] Источники не прочитаны: D01, D02`;
  модель 3 → `read_doc D01`, `read_doc D02` (ok); модель 4 → финальный ответ.
- `stop_reason: final_answer`, ответ идентичен исходному (до изменения), `read_ids: ['D01', 'D02'] missing_ids: [] tool_errors: 0`.
- Отличия в выводе от исходного — только дополнительная диагностика (`-> ok`, номер замечания с ID, строка `read_ids`).

## Таблица A1–A5 + регрессия
| ID | Сценарий | Тест | Результат |
|---|---|---|---|
| A1 | «Что проверить после OCR и перед внешним API?»: поиск + чтение, ответ подтверждён D01/D02 | `test_a1_ocr_and_external_api_answer_confirmed_by_d01_d02` | PASS |
| A1 | Ответ ссылается на непрочитанный D02 → замечание с D02, не принимается | `test_a1_answer_citing_unread_d02_is_not_accepted` | PASS |
| A2 | «Сколько стоит лицензия DemoDesk?»: D03 прочитан, ответ «нет сведений», без суммы | `test_a2_demodesk_license_price_absent_reported` | PASS |
| A2 | Выдуманный тариф со ссылкой на непрочитанный D07 → `unverified_sources`, ответа нет | `test_a2_invented_price_with_unread_source_not_returned` | PASS |
| A3 | D99 → `not_found`; неверные аргументы → `bad_arguments`; чужой инструмент → `unknown_tool`; без падения | `test_a3_unknown_d99_and_bad_arguments_structured_errors` | PASS |
| A3 | `arguments` не строкой → `bad_arguments`, без падения | `test_a3_non_string_arguments_do_not_crash` | PASS |
| A3 | Ответ «по D99» не выдаётся (`unverified_sources`) | `test_a3_answer_with_content_of_d99_rejected` | PASS |
| A4 | Разовый сбой `read_doc` → `tool_failure`, повторное чтение, `final_answer` | `test_a4_read_doc_failure_recovered` | PASS |
| A4 | `read_doc` всегда падает → `unverified_sources`, `answer = null` | `test_a4_read_doc_always_fails_clear_stop` | PASS |
| A5 | `max_model_calls = 2` → `budget_exhausted`, ровно 2 вызова модели | `test_a5_reduced_model_call_limit_stops` | PASS |
| A5 | `max_tool_calls = 3` → `tool_budget_exhausted`, 3 вызова инструмента | `test_a5_reduced_tool_call_limit_stops` | PASS |
| A5 | Лимит 2 + неподтверждённые ответы → `budget_exhausted`, ответа нет | `test_a5_reduced_limit_with_unverified_answers_no_answer` | PASS |
| Регрессия | `python agent.py --replay` (подпроцесс): код 0, `final_answer`, ответ = исходному, 4/4 вызова | `test_replay_regression` | PASS |
| Регрессия | Интерфейс `search_docs`/`read_doc` не изменён | `test_replay_tool_interface_unchanged` | PASS |

## Что не сделано или сделано не полностью
- **Живая модель не проверялась** (`--live` требует ключа и сети; по брифу в тестах не используется). Поведение реальной модели на замечаниях R4 не подтверждено.
- **A2 проверяет конвейер, а не честность модели**: заглушка задаёт «правильный» ответ; агент гарантирует лишь, что ссылки подтверждены чтением,
  но не может обнаружить выдуманную цену, если модель сошлётся на реально прочитанный D03.
- Проверка R4 — синтаксическая (ID в тексте ⊆ прочитанных); соответствие номеров строк и содержания не проверяется.
- Более широкое распознавание ссылок отклоняет и простое упоминание непрочитанного ID (например, «D99 не найден») — осознанный строгий выбор по R4.
- Change не архивирован (`openspec archive` не запускался — в задании не требовалось).
