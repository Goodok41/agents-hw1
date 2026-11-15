## ADDED Requirements

### Requirement: R1 Structured not_found for unknown document
Вызов `read_doc` с ID, которого нет в корпусе, MUST возвращать структурированную ошибку
`{"error": {"code": "not_found", "message": ..., "doc_id": <ID>}}` без выдуманного содержимого.
Такой ID MUST попадать в `missing_ids` итогового результата.

#### Scenario: Unknown doc_id
- **WHEN** модель вызывает `read_doc` с аргументами `{"doc_id": "D99"}`
- **THEN** результат инструмента содержит `error.code = "not_found"` и `error.doc_id = "D99"`
- **AND** в результате нет полей `lines`, `title` и иного содержимого документа
- **AND** итоговый результат содержит `"D99"` в `missing_ids` и не содержит его в `read_ids`

#### Scenario: Known doc_id
- **WHEN** модель вызывает `read_doc` с `{"doc_id": "D01"}`
- **THEN** результат содержит `id`, `title`, `version` и пронумерованные `lines` документа D01

### Requirement: R2 Tool exceptions do not crash the process
Исключение, возникшее внутри инструмента, MUST превращаться в результат
`{"error": {"code": "tool_failure", "message": ...}}`. Процесс MUST NOT завершаться из-за такого исключения;
цикл агента MUST продолжаться в пределах лимитов. Неверные аргументы инструмента MUST давать
структурированную ошибку `bad_arguments`, неизвестный инструмент — `unknown_tool`.

#### Scenario: Exception inside tool
- **WHEN** выполнение `read_doc` бросает исключение
- **THEN** модель получает результат с `error.code = "tool_failure"`
- **AND** агент продолжает цикл и делает следующий вызов модели

#### Scenario: Invalid tool arguments
- **WHEN** модель передаёт `read_doc` аргументы, не являющиеся корректным JSON-объектом с единственным полем `doc_id`
- **THEN** результат содержит `error.code = "bad_arguments"`, процесс не падает

### Requirement: R3 Trace status and result summary
Каждое событие `tool` в трассе MUST содержать `status` со значением `"ok"` или `"error"`.
Итоговый результат при любом `stop_reason` MUST содержать `read_ids` (успешно прочитанные ID по возрастанию,
без повторов), `missing_ids` (ID с ошибкой `not_found`, по возрастанию) и `tool_errors` (число вызовов
инструментов, завершившихся ошибкой).

#### Scenario: Mixed successful and failed calls
- **WHEN** за запуск успешно прочитаны D02 и D01, а вызов `read_doc` для D99 вернул `not_found`
- **THEN** у успешных событий `status = "ok"`, у события D99 `status = "error"`
- **AND** `read_ids = ["D01", "D02"]`, `missing_ids = ["D99"]`, `tool_errors = 1`

### Requirement: R4 Source verification of the final answer
Финальный ответ MUST NOT ссылаться на ID документа, который не был успешно прочитан через `read_doc`.
При нарушении программа MUST вернуть модели замечание с перечнем конкретных неподтверждённых ID;
таких замечаний MUST быть не более 2 за запуск. При следующем нарушении `stop_reason` MUST быть
`"unverified_sources"`, а `answer` MUST быть `null`; неподтверждённый ответ MUST NOT выдаваться.

#### Scenario: Answer cites unread document
- **WHEN** модель даёт финальный ответ со ссылкой на D02, а прочитан только D01
- **THEN** модель получает замечание, в тексте которого указан `D02`
- **AND** этот ответ не возвращается как итоговый

#### Scenario: Remarks limit reached
- **WHEN** модель трижды подряд даёт ответ со ссылкой на непрочитанный документ
- **THEN** программа отправляет ровно 2 замечания
- **AND** завершает работу с `stop_reason = "unverified_sources"` и `answer = null`

### Requirement: R5 Limits are not relaxed
Исчерпание `max_model_calls` MUST давать `stop_reason = "budget_exhausted"`, а превышение
`max_tool_calls` — `stop_reason = "tool_budget_exhausted"`; в обоих случаях `answer` MUST быть `null`.
Агент MUST NOT вызывать модель больше `max_model_calls` раз и выполнять инструменты сверх `max_tool_calls`.

#### Scenario: Model call budget exhausted
- **WHEN** `max_model_calls = 2`, а модель всё время запрашивает инструменты
- **THEN** модель вызвана ровно 2 раза, `stop_reason = "budget_exhausted"`, `answer = null`

#### Scenario: Tool call budget exhausted
- **WHEN** `max_tool_calls = 3`, а модель продолжает запрашивать инструменты
- **THEN** выполнено не более 3 вызовов инструментов, `stop_reason = "tool_budget_exhausted"`, `answer = null`

### Requirement: R6 Tool interface and replay compatibility
Имена, описания и схемы параметров `search_docs` и `read_doc` MUST оставаться прежними.
Запуск `python agent.py --replay` MUST завершаться с кодом 0, `stop_reason = "final_answer"` и тем же
ответом, что и до изменения.

#### Scenario: Replay regression
- **WHEN** выполняется `python agent.py --replay`
- **THEN** процесс завершается с кодом 0, `stop_reason = "final_answer"`
- **AND** ответ совпадает с последней записанной репликой модели, `read_ids = ["D01", "D02"]`

### Requirement: Acceptance checks A1-A5
Поведение агента MUST проверяться автоматическими тестами по таблице A1–A5 с контролируемой заглушкой
модели и инструментов; живая модель и сеть MUST NOT использоваться в тестах.

#### Scenario: A1 answer confirmed by D01 and D02
- **WHEN** задан вопрос «Что проверить после OCR и перед внешним API?» и модель выполняет поиск, читает D01 и D02 и отвечает со ссылками на них
- **THEN** `stop_reason = "final_answer"`, в трассе есть `search_docs` и `read_doc` со `status = "ok"`
- **AND** `read_ids = ["D01", "D02"]`, а все ссылки ответа входят в `read_ids`

#### Scenario: A2 no price for DemoDesk license
- **WHEN** задан вопрос «Сколько стоит лицензия DemoDesk?» и модель находит и читает D03
- **THEN** прочитанный D03 содержит строку об отсутствии цены, ответ явно сообщает об отсутствии сведений и не содержит суммы
- **AND** ответ с выдуманным тарифом и ссылкой на непрочитанный документ не выдаётся

#### Scenario: A3 unknown ID D99 and invalid arguments
- **WHEN** модель запрашивает `read_doc` для D99 и вызывает инструмент с неверными аргументами
- **THEN** возвращаются ошибки `not_found` и `bad_arguments`, процесс не падает
- **AND** содержимое D99 нигде не появляется, `D99` есть в `missing_ids`

#### Scenario: A4 artificial read_doc failure
- **WHEN** в тесте `read_doc` искусственно бросает исключение
- **THEN** ошибка `tool_failure` зафиксирована в трассе со `status = "error"` и учтена в `tool_errors`
- **AND** агент либо восстанавливается повторным чтением, либо завершается с понятным `stop_reason` без неподтверждённого ответа

#### Scenario: A5 reduced call limit
- **WHEN** лимит вызовов принудительно уменьшен, а модель зацикливается
- **THEN** цикл останавливается на лимите с `budget_exhausted` или `tool_budget_exhausted`
- **AND** `answer = null`, неподтверждённый финальный ответ не выдаётся
