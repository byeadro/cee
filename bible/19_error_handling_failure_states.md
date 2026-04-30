---
notion_section: 19
notion_title: 19 — ERROR HANDLING + FAILURE STATES
mirrored_at: 2026-04-30
---

# 19 — ERROR HANDLING + FAILURE STATES
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the consolidated catalog of every halt type, every failure state, every typed exception CEE can produce. Sections 00–16 named halts and failures inline; this page collects them into the closed enum, defines per-state recovery semantics, and specifies the user-facing message format. Where section 18 is the test plan that exercises failures, this page is the failure spec the tests verify against.
---
## 1. What This Is
Errors in CEE are first-class. Every halt is named, every failure state is typed, every recovery is defined. This page covers:
- The closed `HaltType` enum — the only halt types CEE can raise from the pipeline driver
- The closed `RunErrorType` enum — terminal failures that mark a Run unrecoverable
- The closed `WarningType` enum — non-fatal events worth logging
- The recovery semantics per halt type: what state is preserved, what action the OPERATOR takes, what happens on retry
- The user-facing message format: every error message has a structure
- The audit trail: every halt and error appears in `~/cee/audit/`
- The exception class hierarchy in code
This is the "what happens when things go wrong" page. Without it, error handling is ad hoc. With it, errors are a defined system on equal footing with success paths.
---
## 2. Why This Matters
Without consolidated error handling:
- Halts emerge organically from modules in inconsistent shapes; the pipeline driver can't dispatch cleanly.
- Recovery semantics differ per failure (some preserve state, some don't) without an obvious reason.
- User-facing messages drift in tone and detail.
- Audit logs miss failure events because each module logs differently.
- Tests can't verify behavior because there's no spec to check against.
This page makes failure a designed surface. Every halt has a name, a payload, a message format, a recovery instruction. Tests verify each exists and behaves correctly. Operators learn one set of recovery patterns instead of memorizing dozens.
---
## 3. Core Requirements
The error handling system MUST:
1. Use a closed `HaltType` enum for every pipeline halt — no untyped halts.
2. Use a closed `RunErrorType` enum for terminal failures.
3. Use a closed `WarningType` enum for non-fatal logged events.
4. Preserve all artifacts written before the failure point (filesystem is canonical; partial Runs survive).
5. Emit a structured user-facing message with halt type, run_id, cause, and recovery action.
6. Log every halt and error to `~/cee/audit/cli.log` and `~/cee/audit/security.log` (the latter for security-relevant events).
7. Use a single exception class hierarchy in code so the pipeline driver can dispatch with one `except`.
8. Make every halt type recoverable (or explicitly mark as terminal) — no failures with undefined recovery.
The error handling system MUST NOT:
- Use untyped exceptions that escape the pipeline driver.
- Allow modules to print error messages directly to stdout (they raise; the driver formats).
- Lose partial state on failure (artifacts written before failure stay on disk).
- Use error messages as the recovery instruction (the message describes what happened; recovery is a separate field).
---
## 4. System Rules
**Rule 1 — Closed enums for all error states.**
`HaltType`, `RunErrorType`, `WarningType` are closed Python enums in `~/cee/errors/types.py`. Adding a value requires bible edit + schema migration.
**Rule 2 — One exception hierarchy.**
All CEE exceptions inherit from `CEEException`. Subclasses: `PipelineHalt`, `RunError`, `BootError`, `ValidationError`, `RoleAuthorityError`, `SubstrateBoundaryError`, `RoleSurfaceViolation`, `InjectionDetected`, `RedactionFailed`. The driver catches `CEEException` once.
**Rule 3 — Halts pause; errors terminate.**
A `PipelineHalt` pauses the Run — state preserved, OPERATOR action expected. A `RunError` terminates the Run — state preserved but the Run is marked failed.
**Rule 4 — Every halt has structured payload.**
`PipelineHalt(halt_type, payload)` where `payload` is a typed dict matching the halt type. The payload contains everything needed to resume or diagnose.
**Rule 5 — User messages follow a format.**
```
[<halt_type>] Run <run_id> halted at step <step_n>.

Cause: <one-sentence description>.

What happened:
<longer description if needed, max 5 lines>

To resume:
<exact CLI command(s) the OPERATOR should run>

Artifacts preserved at: <path>
```
**Rule 6 — Audit-first persistence.**
Halt and error events are written to `~/cee/audit/cli.log` (and `security.log` if security-relevant) before the user sees the message.
**Rule 7 — Failures don't roll back canon.**
A failure mid-step does not delete artifacts from prior successful steps.
**Rule 8 — Resume must be deterministic.**
Resuming a halted Run produces the same final artifacts as a Run that completed without halting.
**Rule 9 — Terminal failures are loud.**
A `RunError` produces stderr output, non-zero exit code, and an entry in `security.log` if security-relevant.
**Rule 10 — No silent fallback.**
If the system can't fulfill a request, it halts or errors. It does not produce a degraded version "just to be helpful."
---
## 5. Detailed Workflow — The Error Catalog
### 5.1 The closed `HaltType` enum (19 values)
```python
class HaltType(str, Enum):
    # Interpreter halts
    INPUT_VALIDATION_ERROR = "input_validation_error"
    INPUT_EMPTY_ERROR = "input_empty_error"
    PAUSED_FOR_CLARIFICATION = "paused_for_clarification"
    NO_EXECUTABLE_INTENT = "no_executable_intent"
    INJECTION_DETECTED = "injection_detected"
    
    # Classifier halts
    AMBIGUOUS_CLASSIFICATION = "ambiguous_classification"
    
    # Agent selector halts
    AGENT_CONFLICT = "agent_conflict"
    NO_PRIMARY_AGENT = "no_primary_agent"
    AGENT_GENERATION_FAILED = "agent_generation_failed"
    
    # Skill engine halts
    SKILL_RESOLUTION_CHOICE = "skill_resolution_choice"
    SKILL_CONFLICT = "skill_conflict"
    SKILL_GENERATION_FAILED = "skill_generation_failed"
    SKILL_DUPLICATE = "skill_duplicate"
    
    # Prompt builder halts
    PROMPT_SCHEMA_VIOLATION = "prompt_schema_violation"
    PROMPT_TOO_LARGE = "prompt_too_large"
    
    # Safety gate halts
    AWAITING_DESTRUCTIVE_CONFIRMATION = "awaiting_destructive_confirmation"
    REDACTION_FAILED = "redaction_failed"
    
    # Grounding halts
    GROUNDING_UNSOURCEABLE = "grounding_unsourceable"
    
    # Persistence halts
    PERSISTENCE_FAILURE = "persistence_failure"
```
### 5.2 The closed `RunErrorType` enum (7 values)
```python
class RunErrorType(str, Enum):
    SCHEMA_VIOLATION = "schema_violation"
    DRIVER_BUG = "driver_bug"
    CONFIRMATION_TIMEOUT = "confirmation_timeout"
    REPLAY_DRIFT = "replay_drift"
    UNRECOVERABLE_PERSISTENCE = "unrecoverable_persistence"
    API_FAILED = "api_failed"
    API_RATE_LIMITED_TERMINAL = "api_rate_limited_terminal"
```
These mark a Run as `failed`; resume is not available, but replay (`cee replay <run_id>`) is.
### 5.3 The closed `WarningType` enum (15 values)
```python
class WarningType(str, Enum):
    OBSIDIAN_WRITE_FAILED = "obsidian_write_failed"
    NOTION_WRITE_FAILED = "notion_write_failed"
    SKILL_REGISTRY_INVALID_ENTRY = "skill_registry_invalid_entry"
    AGENT_REGISTRY_INVALID_ENTRY = "agent_registry_invalid_entry"
    LLM_CALL_FALLBACK = "llm_call_fallback"
    HOOK_FAILED = "hook_failed"
    SKILL_NEEDS_REVIEW_AGED = "skill_needs_review_aged"
    AGENT_NEEDS_REVIEW_AGED = "agent_needs_review_aged"
    BIBLE_DRIFT_DETECTED = "bible_drift_detected"
    UNKNOWN_TOOL_IN_AGENT = "unknown_tool_in_agent"
    OVER_REDACTION = "over_redaction"
    SECURITY_OVERRIDE = "security_override"
    INJECTION_FLAG_ACKNOWLEDGED = "injection_flag_acknowledged"
    DETERMINISM_DRIFT = "determinism_drift"
    PROMOTION_QUEUE_LARGE = "promotion_queue_large"
```
### 5.4 Per-halt recovery semantics
Each halt type has defined behavior. Format: cause, payload contents, what state is preserved, OPERATOR action.

- **`INPUT_VALIDATION_ERROR`**: Schema validation fails. Action: OPERATOR fixes input; re-runs.
- **`INPUT_EMPTY_ERROR`**: Empty/whitespace input. Action: OPERATOR provides actual input.
- **`PAUSED_FOR_CLARIFICATION`**: ambiguity_score > 0.6. Action: OPERATOR runs `cee answer <run_id>`.
- **`NO_EXECUTABLE_INTENT`**: Input has no actionable goal. Action: OPERATOR provides actual task.
- **`INJECTION_DETECTED`**: Injection scanner flagged input. Action: OPERATOR aborts or acknowledges flags.
- **`AMBIGUOUS_CLASSIFICATION`**: confidence delta < 0.10 between task_types. Action: OPERATOR runs `cee run --resume <run_id> --task-type <chosen>`.
- **`AGENT_CONFLICT`**: Two agents claim same posture. Action: OPERATOR investigates AGENT_SELECTOR; manual override.
- **`NO_PRIMARY_AGENT`**: No agent matches; generation failed. Action: OPERATOR hand-authors agent or narrows task.
- **`AGENT_GENERATION_FAILED`**: Generator couldn't produce valid agent. Action: same as NO_PRIMARY_AGENT.
- **`SKILL_RESOLUTION_CHOICE`**: Match score in ASK zone [0.60, 0.85]. Action: `cee run --resume --skill-action reuse|modify|generate`.
- **`SKILL_CONFLICT`**: Slug collision. Action: OPERATOR resolves manually.
- **`SKILL_GENERATION_FAILED`**: Generator produced invalid Skill. Action: OPERATOR hand-authors or skips.
- **`SKILL_DUPLICATE`**: Near-identical to existing. Action: `cee run --resume --skill-action reuse-existing|fork|proceed`.
- **`PROMPT_SCHEMA_VIOLATION`**: FinalPrompt failed schema. Action: PROMPT_BUILDER bug investigation.
- **`PROMPT_TOO_LARGE`**: Chunks exceed budget. Action: OPERATOR reduces attachments or scope.
- **`AWAITING_DESTRUCTIVE_CONFIRMATION`**: destructive_potential=true. Action: `cee confirm <run_id>` or `cee abort <run_id>`. Auto-abort after 24h.
- **`REDACTION_FAILED`**: Sensitive pattern undetectable. Action: OPERATOR updates redact_list; re-runs.
- **`GROUNDING_UNSOURCEABLE`**: needs_grounding but no sources. Action: OPERATOR provides sources or `--no-grounding` override.
- **`PERSISTENCE_FAILURE`**: Filesystem write failed. Action: OPERATOR fixes filesystem; replays.
### 5.5 Per-RunError recovery semantics
Run errors are terminal — the Run cannot resume, only replay.
- **`SCHEMA_VIOLATION`**: Module bug. Recovery: investigate, fix, replay.
- **`DRIVER_BUG`**: Pipeline driver raised unexpected exception. Recovery: bug report; Run preserved.
- **`CONFIRMATION_TIMEOUT`**: 24h passed without confirmation. Recovery: re-run if desired.
- **`REPLAY_DRIFT`**: Determinism violation. Recovery: investigate non-determinism bug.
- **`UNRECOVERABLE_PERSISTENCE`**: Filesystem fundamentally unwritable. Recovery: fix underlying issue.
- **`API_FAILED`**: Phase 2 API failure. Recovery: investigate; replay.
- **`API_RATE_LIMITED_TERMINAL`**: Rate limit exceeded. Recovery: wait or upgrade plan; replay.
### 5.6 The user-facing message format
Every halt and error produces a structured message with halt type, run_id, step, cause, "What happened" detail, "To resume" exact CLI command(s), and "Artifacts preserved at" path. Generated by `~/cee/errors/messages.py` from a template per halt type.
### 5.7 The exception class hierarchy
```python
class CEEException(Exception): pass
class PipelineHalt(CEEException):
    def __init__(self, halt_type: HaltType, payload: dict): ...
class RunError(CEEException):
    def __init__(self, error_type: RunErrorType, payload: dict): ...
class BootError(CEEException):
    def __init__(self, step: str, reason: str): ...
class ValidationError(CEEException): pass
class RoleAuthorityError(CEEException): pass
class SubstrateBoundaryError(CEEException): pass
class RoleSurfaceViolation(CEEException): pass
class InjectionDetected(PipelineHalt):
    def __init__(self, flags):
        super().__init__(HaltType.INJECTION_DETECTED, {"flags": flags})
class RedactionFailed(PipelineHalt):
    def __init__(self, residual_patterns):
        super().__init__(HaltType.REDACTION_FAILED, {"residual_patterns": residual_patterns})
```
The pipeline driver catches `CEEException` once and dispatches by class.
### 5.8 The dispatch flow
The pipeline driver in `~/cee/pipeline.py` wraps the entire pipeline in a try/except that:
- Catches `PipelineHalt`: writes halt artifact, logs to audit, formats message, returns RunResult(state="paused").
- Catches `RunError`: writes error artifact, logs as error, formats message, returns RunResult(state="failed").
- Catches `CEEException` (other): treats as DRIVER_BUG.
- Catches `Exception` (non-CEE): real bug; logs critical; treats as DRIVER_BUG with traceback.
The driver catches everything. Pure exceptions don't escape.
---
## 6. Data / Inputs Needed
### 6.1 Required for error handling
- The closed enum definitions at `~/cee/errors/types.py`
- Message templates at `~/cee/errors/message_templates/`
- Audit log writers from `~/cee/persistence/audit.py`
### 6.2 Configuration
- `~/.cee/config.toml` `[errors]` section: `verbose_messages` (default true), `auto_open_run_dir_on_halt` (default false), `treat_warnings_as_errors` (default false).
### 6.3 Reference data
- The halt type → message template mapping
- The halt type → recovery action mapping
- The exception class hierarchy
---
## 7. Outputs Produced
### 7.1 On halt
- `~/cee/runs/<run_id>/halt.json` — typed halt with payload
- User-facing message on stdout (via the driver)
- Audit log entry in `~/cee/audit/cli.log` (and `security.log` if security-relevant)
### 7.2 On error
- `~/cee/runs/<run_id>/error.json` — typed error with payload
- User-facing message on stderr
- Non-zero exit code
- Audit log entries (severity: error or critical)
### 7.3 On warning
- Audit log entry in `~/cee/audit/cli.log`
- May surface in next `cee verify` or boot output until acknowledged
---
## 8. Agent + Skill Implications
### 8.1 Halts can be Skill-driven
A Skill resolution halt (`SKILL_RESOLUTION_CHOICE`) is part of the normal Run flow when matching scores fall in the ASK zone.
### 8.2 Agent generation halts are rare but real
Most Runs hit the catalog. When generation does fire and fails, `AGENT_GENERATION_FAILED` is the halt.
### 8.3 Validation errors propagate up as `RunError(SCHEMA_VIOLATION)`
A module emitting an invalid artifact is a bug. The driver catches the underlying `ValidationError` and re-raises as `RunError(SCHEMA_VIOLATION)`.
---
## 9. Edge Cases
**EC1 — Halt happens during persistence (Step 9).** Replay reconstructs.
**EC2 — Multiple halts could fire simultaneously.** Pipeline is sequential; only one halt fires per step.
**EC3 — A halt's payload is too large to log.** Soft size limit (10KB). Larger payloads are truncated with a marker.
**EC4 — User force-quits during a halt prompt.** Run directory persists. Next `cee run` detects in-progress Run.
**EC5 — Two halts fire on simultaneous parallel Runs.** Each Run has independent run_id.
**EC6 — Same halt type fires multiple times in a Run's history.** After 2 ambiguity halts on same Run, classifier proceeds with precedence-winning candidate.
**EC7 — A halt type is added to the enum but no message template exists.** Boot's cross-section consistency check catches.
**EC8 — Recovery action fails (e.g., ****`cee confirm`**** errors).** Original halt remains; OPERATOR retries.
**EC9 — A ****`RunError`**** happens during error handling.** Triple-fault scenario. Logged with extreme severity.
**EC10 — Hooks fail during error handling.** Hook failures are logged but don't escalate.
**EC11 — User wants to convert a halt to a ****`RunError`****.** `cee abort <run_id>` does exactly this.
**EC12 — ****`WarningType`**** is logged but no one notices.** Boot prints unacknowledged warnings on each session start.
---
## 10. Failure Modes
### 10.1 Halt without resume path
**Recovery:** template updated; tests assert all halts have resume guidance.
### 10.2 Recovery command has wrong syntax
**Recovery:** templates fixed; CI tests for command syntax.
### 10.3 Halt payload missing required fields
**Recovery:** halt schemas defined per halt type; tests assert.
### 10.4 RunError fires on a recoverable failure
**Recovery:** classify the failure correctly — transient errors should be `Halt`, not `RunError`.
### 10.5 Halt fires on a non-recoverable failure
**Recovery:** convert to `RunError`; investigate root cause.
### 10.6 Audit log loses entries on burst
**Recovery:** audit writer is synchronous; bursts are rare in practice.
### 10.7 Message template breaks on long payloads
**Recovery:** template's `{value}` substitutions handle multi-line correctly.
### 10.8 Exception class drift
**Recovery:** module updated to use proper exception class.
### 10.9 Pipeline driver doesn't catch a specific exception
**Recovery:** driver's catch updated; test expanded.
### 10.10 User sees an internal stacktrace
**Recovery:** driver's outer `except` catches everything; raw tracebacks go to audit log only.
---
## 11. Build Notes for Claude Code
- **Enum location:** `~/cee/errors/types.py`. Closed enums for `HaltType`, `RunErrorType`, `WarningType`.
- **Exception location:** `~/cee/errors/__init__.py`. Single hierarchy.
- **Message templates:** `~/cee/errors/message_templates/<halt_type>.txt` and `<error_type>.txt`. One per enum value.
- **Message renderer:** `~/cee/errors/messages.py`. Pure function: `format_message(halt_or_error) -> str`.
- **Audit logger:** `~/cee/persistence/audit.py`. `log_halt(run_id, halt)`, `log_error(run_id, error)`, `log_warning(warning_type, payload)`.
- **Driver dispatch:** `~/cee/pipeline.py`'s outer try/except as in §5.8.
- **Tests:** `~/cee/tests/unit/test_errors/` for enum coverage and exception hierarchy. `~/cee/tests/integration/` for halt-resume flows. `~/cee/tests/adversarial/` for triggering each halt type.
- **CLI integration:** `cee abort <run_id>` lives in `~/cee/cli.py`; converts current halt state to aborted RunError.
- **Security-relevant flag:** halts and errors carry a `security_relevant: bool` field that determines whether they also write to `security.log`.
- **Bible consistency check:** boot validates that this page's enum lists match `~/cee/errors/types.py` exactly. Drift halts boot.
---
## 12. Definition of Done
- [ ] All 19 halt types, 7 run-error types, 15 warning types in §5.1–§5.3 exist in `~/cee/errors/types.py`.
- [ ] Every halt type has a message template at `~/cee/errors/message_templates/`.
- [ ] Every halt has documented recovery semantics in §5.4.
- [ ] Every run-error has documented recovery in §5.5.
- [ ] The exception hierarchy matches §5.7.
- [ ] The pipeline driver dispatches per §5.8 with no exceptions escaping.
- [ ] Every halt type is reachable from at least one adversarial test in section 18.
- [ ] Every recovery command in messages is verified by an integration test.
- [ ] Boot's consistency check verifies enums in this page match `~/cee/errors/types.py`.
- [ ] Audit log entries are produced for every halt, error, and warning.
- [ ] User-facing messages match the format in §5.6 for every halt and error.
---
## 13. Final Statement
Errors in CEE are not afterthoughts. They are a designed surface, with closed enums, typed payloads, formatted messages, and defined recovery. The pipeline driver catches everything; modules raise typed exceptions; users see structured messages with exact recovery commands. Failure becomes legible. Section 18 verifies; this page specifies. Together, they make "things going wrong" a path the system handles deliberately rather than something the user has to debug.
