"""RunSummary artifact schema.

Authorized by System Design Bible section 03 §7.1 (outputs on success)
and section 03 Step 9 (Persistence). Produced by PERSISTENCE_WRITER
during the finalize step; persisted at
``~/cee/runs/<run_id>/summary.json`` (bible 04 §5.1).

Bible 03 Step 9 mandates that the summary "references all step
artifacts"; ``artifact_paths`` is that mapping. The slug lists let
downstream consumers (Obsidian writer, promotion queue) operate from
``summary.json`` alone without re-reading every step artifact.

The ``state`` field captures the high-level Run state machine — runtime
shorthand used in bible 03 §5.3 ("the Run is in state ``paused``") and
bible 19 §5.7 (``RunResult(state="paused")`` / ``RunResult(state="failed")``).
Bible 03 §3 enumerates three terminal states (``delivered``,
``halted_for_clarification``, ``halted_for_error``); ``paused`` and
``failed`` are the runtime labels of the latter two.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Mirrors ``cee.paths._RUN_ID_PATTERN`` (bible 04 §5.1).
_RUN_ID_PATTERN = r"^\d{8}_\d{6}_[0-9a-f]{8}$"


RunState = Literal["delivered", "paused", "failed"]

TaskTypeLiteral = Literal[
    "BUILD",
    "ANALYZE",
    "DEBUG",
    "WRITE",
    "RESEARCH",
    "TRANSFORM",
    "DECIDE",
    "ORCHESTRATE",
]

ComplexityTierLiteral = Literal["LOW", "MEDIUM", "HIGH", "EXTREME"]

TargetExecutorLiteral = Literal["claude_code", "claude_ai", "api"]


class RunSummary(BaseModel):
    """The Run summary written by PERSISTENCE_WRITER at finalize time.

    Per bible 03 Step 9 this single file is the run directory's index of
    truth — it lists every artifact written, the Run's terminal state,
    and the slugs of agents and Skills referenced by the FinalPrompt.

    Validators enforce the state machine:

    * ``delivered`` Runs must point to no halt or error artifact and
      must have produced at least one prompt chunk.
    * ``paused`` and ``failed`` Runs must point to their halt or error
      artifact respectively (a non-empty path).

    For Runs that halt before classification (e.g. INPUT_EMPTY_ERROR),
    ``task_type`` and ``complexity_tier`` are ``None`` and the slug
    lists default to empty.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    run_id: Annotated[str, Field(pattern=_RUN_ID_PATTERN)]
    state: RunState
    started_at: Annotated[str, Field(min_length=1)]
    ended_at: Annotated[str, Field(min_length=1)]
    task_type: TaskTypeLiteral | None = None
    complexity_tier: ComplexityTierLiteral | None = None
    target_executor: TargetExecutorLiteral
    agent_slugs: list[str] = Field(default_factory=list)
    skill_slugs: list[str] = Field(default_factory=list)
    newly_generated_agents: list[str] = Field(default_factory=list)
    newly_generated_skills: list[str] = Field(default_factory=list)
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    prompt_chunks: Annotated[int, Field(ge=0)]
    halt_or_error_ref: str | None = None
    # TODO task 9: replace with RoleEnum once roles/__init__.py defines it.
    produced_by: str = "PIPELINE_DRIVER"

    @model_validator(mode="after")
    def _check_terminal_state_invariants(self) -> "RunSummary":
        if self.state == "delivered":
            if self.halt_or_error_ref is not None:
                raise ValueError(
                    "state='delivered' requires halt_or_error_ref to be "
                    f"None; got {self.halt_or_error_ref!r}"
                )
            if self.prompt_chunks < 1:
                raise ValueError(
                    "state='delivered' requires prompt_chunks >= 1; "
                    f"got {self.prompt_chunks}"
                )
        else:
            # state in ("paused", "failed")
            if not self.halt_or_error_ref:
                raise ValueError(
                    f"state={self.state!r} requires halt_or_error_ref to "
                    f"be a non-empty path to halt.json or error.json"
                )
        return self
