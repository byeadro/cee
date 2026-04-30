"""Closed enums for CEE error states.

Authorized by System Design Bible section 19 (Error Handling + Failure States),
specifically §5.1 (HaltType), §5.2 (RunErrorType), §5.3 (WarningType).

Adding, removing, or renaming any value here requires a bible edit first; the
boot consistency check (bible §11) verifies these enums match §5.1–§5.3 exactly.

All three enums inherit from ``(str, Enum)`` so members are JSON-serializable
as strings and compare equal to their string values (``HaltType.X == "x"``).
"""

from enum import Enum


class HaltType(str, Enum):
    """Every named pause point the pipeline driver can raise.

    A ``PipelineHalt`` carrying one of these values pauses the Run with state
    preserved on disk; the OPERATOR takes a recovery action defined in
    bible §5.4 and the Run resumes. Used by ``cee.errors.PipelineHalt`` and
    dispatched by the pipeline driver per bible §5.8.
    """

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


class RunErrorType(str, Enum):
    """Every terminal Run failure.

    A ``RunError`` carrying one of these values marks the Run as ``failed``;
    resume is unavailable but replay (``cee replay <run_id>``) remains.
    Used by ``cee.errors.RunError`` and dispatched per bible §5.8. Recovery
    semantics are defined in bible §5.5.
    """

    SCHEMA_VIOLATION = "schema_violation"
    DRIVER_BUG = "driver_bug"
    CONFIRMATION_TIMEOUT = "confirmation_timeout"
    REPLAY_DRIFT = "replay_drift"
    UNRECOVERABLE_PERSISTENCE = "unrecoverable_persistence"
    API_FAILED = "api_failed"
    API_RATE_LIMITED_TERMINAL = "api_rate_limited_terminal"


class WarningType(str, Enum):
    """Every non-fatal event worth logging.

    Warnings do not halt or fail the Run; they are appended to
    ``~/cee/audit/cli.log`` (and ``security.log`` when security-relevant) and
    surfaced on next ``cee verify`` or boot until acknowledged. Used by the
    audit logger per bible §7.3.
    """

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
