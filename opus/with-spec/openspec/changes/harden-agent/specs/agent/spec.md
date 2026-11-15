## ADDED Requirements

### Requirement: R1 Missing document handling
When `read_doc` is called with a well-formed `doc_id` that is not in the corpus, the agent MUST return a structured error result with code `not_found` instead of document content, and MUST add that ID to `missing_ids` of the final result.

#### Scenario: Unknown doc_id is reported as not_found
- **WHEN** the model calls `read_doc` with `{"doc_id": "D99"}` and the corpus has no document `D99`
- **THEN** the tool result is `{"error": {"code": "not_found", ...}}`
- **AND** the final result contains `"D99"` in `missing_ids`
- **AND** `"D99"` is not in `read_ids`

### Requirement: R2 Tool failure isolation
An exception raised inside a tool MUST NOT terminate the process. The agent MUST convert it into the tool result `{"error": {"code": "tool_failure", "message": ...}}`, pass that result to the model and continue the loop within the configured limits. A failed call MUST count towards the tool-call budget.

#### Scenario: Exception inside a tool becomes tool_failure
- **WHEN** a tool raises an exception while handling a call
- **THEN** the tool result recorded in the trace and sent to the model is an error with code `tool_failure`
- **AND** the agent requests the next model step instead of raising
- **AND** `tool_errors` in the final result is incremented

### Requirement: R3 Tool status and result summary
Every `tool` event in the trace MUST have a `status` field equal to `"ok"` when the result has no `error` and `"error"` otherwise. Every final result, for any `stop_reason`, MUST contain `read_ids` (IDs successfully read by `read_doc`, unique, sorted ascending), `missing_ids` (IDs that produced `not_found`, unique, sorted ascending) and `tool_errors` (number of `tool` events with status `"error"`).

#### Scenario: Summary fields after mixed tool results
- **WHEN** during one run the model reads `D02`, then `D01`, then the unknown `D99`
- **THEN** every `tool` event in the trace has `status` `"ok"` or `"error"` matching its result
- **AND** the final result has `read_ids` equal to `["D01", "D02"]`, `missing_ids` equal to `["D99"]` and `tool_errors` equal to `1`

#### Scenario: Summary fields are present on budget stop
- **WHEN** the run stops with `budget_exhausted` or `tool_budget_exhausted`
- **THEN** the final result still contains `read_ids`, `missing_ids` and `tool_errors`

### Requirement: R4 Source verification
A final answer MUST NOT reference any document ID that was not successfully read by `read_doc` in the same run. When a candidate answer fails verification, the agent MUST send the model a remark that names the specific offending IDs, at most 2 times per run. If a candidate answer fails verification after 2 remarks were already sent, the agent MUST stop with `stop_reason` equal to `"unverified_sources"` and `answer` equal to `null`. An unverified answer MUST NOT be returned.

#### Scenario: Remark names the unread IDs
- **WHEN** the model returns a final answer citing `D01` and `D02` while only search results were obtained
- **THEN** the agent sends the model a remark that contains `D01` and `D02`
- **AND** the answer is not returned as final

#### Scenario: Third unverified answer stops the run
- **WHEN** the model keeps citing an unread ID after two remarks were sent
- **THEN** the agent stops with `stop_reason` `"unverified_sources"` and `answer` `null`
- **AND** exactly 2 remarks were sent during the run

#### Scenario: Verified answer after a remark is accepted
- **WHEN** after a remark the model reads every cited ID and answers again
- **THEN** the agent stops with `stop_reason` `"final_answer"` and returns the answer

### Requirement: R5 Limits are not relaxed
The agent MUST NOT exceed `max_model_calls` or `max_tool_calls`. When model calls are exhausted, the run MUST stop with `stop_reason` `"budget_exhausted"`; when a requested batch of tool calls would exceed the tool budget, the run MUST stop with `stop_reason` `"tool_budget_exhausted"` without executing that batch. In both cases `answer` MUST be `null`.

#### Scenario: Model call budget exhausted
- **WHEN** the model requests tools on every step until `max_model_calls` is reached
- **THEN** the run stops with `stop_reason` `"budget_exhausted"` and `answer` `null`
- **AND** the model was called exactly `max_model_calls` times

#### Scenario: Tool call budget exhausted
- **WHEN** the model requests more tool calls than remain in `max_tool_calls`
- **THEN** the run stops with `stop_reason` `"tool_budget_exhausted"` and `answer` `null`
- **AND** `tool_calls` does not exceed `max_tool_calls`

### Requirement: R6 Compatibility of tools and replay
The tool interface MUST stay unchanged: `search_docs` takes only `query` and `read_doc` takes only `doc_id`, with the same result shapes for successful calls. The default `--replay` run MUST keep its behavior: the same sequence of model steps and tool calls, `stop_reason` `"final_answer"` and the same answer text.

#### Scenario: Replay regression
- **WHEN** the agent is run with `--replay` and the default configuration
- **THEN** it performs 4 model calls and 4 tool calls and stops with `stop_reason` `"final_answer"`
- **AND** the answer cites `D01` and `D02`, and `read_ids` equals `["D01", "D02"]`
