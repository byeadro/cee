"""ClarificationRequest artifact schema.

Authorized by System Design Bible section 03 §5.3 (the clarification cycle)
and section 19 §5.4 (per-halt recovery semantics for
``PAUSED_FOR_CLARIFICATION`` and the related INTERPRETER halts). Produced
by INTERPRETER when the resolved IntentObject is too ambiguous to advance
(``ambiguity_score > 0.6`` per bible 03 §5.2). Persisted at
``~/cee/runs/<run_id>/clarification.json``.

Per bible 03 §5.3 the Run pauses, the questions are emitted to stdout, and
OPERATOR resumes via ``cee answer <run_id> "<answers>"`` (or the
``cee run <run_id> --resume "<answers>"`` form). Each question carries a
slug-style ``id`` so the resume path can map answers back to the halted
IntentObject deterministically.

The ``intent_object_so_far`` field intentionally uses a plain ``dict``
rather than the typed :class:`schemas.IntentObject` model: the partial
extraction is the *reason* the Run halted and would not validate against
the IntentObject schema. Storing the partial state preserves it for
replay and for the resume cycle.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from roles import RoleEnum

# Mirrors ``cee.paths._RUN_ID_PATTERN`` (bible 04 §5.1). Kept inline so the
# schema package does not take a runtime dependency on ``cee.paths``.
_RUN_ID_PATTERN = r"^\d{8}_\d{6}_[0-9a-f]{8}$"

# Slug shape for question ids: lowercase alphanumeric plus hyphens, 1–60
# chars. Must start with [a-z0-9] so ``id`` is round-trippable through CLI
# argument parsers without quoting.
_QUESTION_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,59}$"


ExpectedAnswerType = Literal["yes_no", "free_text", "choice", "number"]


class ClarificationQuestion(BaseModel):
    """One question inside a ClarificationRequest.

    Per bible 03 §5.3 each question must be addressable by ``id`` during
    the resume cycle. ``expected_answer_type`` lets the resume validator
    coerce and shape-check the OPERATOR's answer before re-injecting it
    into the halted IntentObject.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    id: Annotated[str, Field(pattern=_QUESTION_ID_PATTERN)]
    question: Annotated[str, Field(min_length=1)]
    context: str | None = None
    expected_answer_type: ExpectedAnswerType
    choices: list[str] | None = None

    @model_validator(mode="after")
    def _check_choice_question_has_choices(self) -> "ClarificationQuestion":
        if self.expected_answer_type == "choice":
            if not self.choices:
                raise ValueError(
                    "expected_answer_type='choice' requires non-empty "
                    "choices list"
                )
        return self


class ClarificationRequest(BaseModel):
    """Halt-time artifact emitted when INTERPRETER cannot resolve the input.

    Persisted at ``~/cee/runs/<run_id>/clarification.json`` per bible 03
    §5.3. Triggered by ``ambiguity_score > 0.6`` (bible 03 §5.2) or by any
    of the named INTERPRETER clarification halts (bible 19 §5.4). The
    ``produced_by`` field is the INTERPRETER role because the interpreter
    is what halts for clarification; downstream halts (e.g.
    AMBIGUOUS_CLASSIFICATION) emit their own halt artifacts.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    run_id: Annotated[str, Field(pattern=_RUN_ID_PATTERN)]
    questions: Annotated[list[ClarificationQuestion], Field(min_length=1)]
    paused_at_step: Annotated[int, Field(ge=1, le=10)]
    intent_object_so_far: dict[str, Any]
    paused_at_iso_timestamp: Annotated[str, Field(min_length=1)]
    produced_by: RoleEnum = RoleEnum.INTERPRETER
