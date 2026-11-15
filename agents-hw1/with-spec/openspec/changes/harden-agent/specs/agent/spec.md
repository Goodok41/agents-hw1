## ADDED Requirements

### Requirement: Missing document handling
The agent MUST return a structured error with code not_found when read_doc receives an unknown ID, and MUST list such IDs in missing_ids.

#### Scenario: Unknown document ID
- **WHEN** read_doc is called with D99
- **THEN** the tool result has error code not_found, no document content is invented, and missing_ids contains D99

### Requirement: Tool failure isolation
The agent MUST convert an exception raised inside a tool into an error result with code tool_failure and MUST continue within the call limits.

#### Scenario: Read failure then retry
- **WHEN** read_doc raises an exception once and the model calls it again
- **THEN** the first call is logged with status error, the second succeeds, and the process does not crash

#### Scenario: Exception text is not logged
- **WHEN** a tool raises an exception with a secret in its message
- **THEN** the secret is absent from the result and the trace

### Requirement: Journal status and totals
Every tool event MUST have status ok or error, and the final result MUST contain read_ids, missing_ids and tool_errors.

#### Scenario: Successful run
- **WHEN** D01 and D02 are read successfully
- **THEN** read_ids is D01 and D02 in ascending order, missing_ids is empty, tool_errors is 0

### Requirement: Source verification
The agent MUST NOT accept a final answer that cites an ID which was not successfully read. The program MUST send the model a correction naming such IDs at most 2 times per run, and then MUST stop with stop_reason unverified_sources and answer null.

#### Scenario: Citing a missing document
- **WHEN** the model keeps citing D99 after read_doc returned not_found
- **THEN** stop_reason is unverified_sources and answer is null

#### Scenario: Correction then success
- **WHEN** the model cites D01 after only a search, then reads D01 and answers again
- **THEN** the answer is accepted and the correction named D01

### Requirement: Limits preserved
The agent MUST stop with budget_exhausted when model calls run out and with tool_budget_exhausted when tool calls would exceed the limit, with answer null.

#### Scenario: Model call limit
- **WHEN** max_model_calls is 2 and the model always requests a tool
- **THEN** stop_reason is budget_exhausted and answer is null

### Requirement: Interface compatibility
The agent MUST keep the search_docs and read_doc interface, and the default --replay run MUST still end with final_answer citing D01 and D02.

#### Scenario: Default replay
- **WHEN** agent.py is run with --replay
- **THEN** stop_reason is final_answer and read_ids is D01 and D02
