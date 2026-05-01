"""ExecutionStrategy artifact schema.

Authorized by System Design Bible section 03 (Step 6). Produced by
STRATEGY_BUILDER from all prior artifacts; persisted at
``~/cee/runs/<run_id>/strategy.json``.

Per bible 03 Step 6 the artifact carries ``steps``, ``checkpoints``,
``stop_conditions``, and ``estimated_cost_tokens``. The ``stop_conditions``
field carries strategy-level halt conditions (when STRATEGY_BUILDER decides
to stop the multi-step plan); these are distinct from the FinalPrompt's
``<stop_conditions>`` tag (bible 05 §5.2), which tells the executor when
to stop. The ``estimated_cost_tokens`` field is a non-negative integer
estimate used downstream by PROMPT_BUILDER for chunking decisions.

Per-tier step counts (bible 03 Step 6 branches): LOW=1, MEDIUM=2–3,
HIGH=3–5, EXTREME=5+. Step count caps are runtime constraints applied by
STRATEGY_BUILDER, not enforced here.
"""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from roles import RoleEnum


class StepSpec(BaseModel):
    """One step of the execution strategy.

    Per bible 05 §5.2 ``<execution_plan>`` and bible 03 Step 6: each step
    has a sequential index ``n`` (≥1), an imperative ``action``, an optional
    ``checkpoint`` flag, optional pre-bound ``agent`` (slug), and a list of
    artifacts the step is expected to produce.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    n: Annotated[int, Field(ge=1)]
    action: Annotated[str, Field(min_length=1)]
    agent: str | None = None
    checkpoint: bool = False
    expected_artifacts: list[str] = Field(default_factory=list)


class ExecutionStrategy(BaseModel):
    """The ordered execution plan for the Run.

    Per bible 03 Step 6. Validators enforce: at least one step (HIGH/EXTREME
    runtime caps live in STRATEGY_BUILDER); ``n`` values run sequentially
    starting at 1 (no gaps, no duplicates, no out-of-order); checkpoint
    indices reference valid step positions.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    steps: Annotated[list[StepSpec], Field(min_length=1)]
    checkpoints: list[int] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    estimated_cost_tokens: Annotated[int, Field(ge=0)]
    produced_by: RoleEnum = RoleEnum.STRATEGY_BUILDER

    @model_validator(mode="after")
    def _check_step_indices_sequential(self) -> "ExecutionStrategy":
        for expected_n, step in enumerate(self.steps, start=1):
            if step.n != expected_n:
                raise ValueError(
                    f"steps[{expected_n - 1}].n must be {expected_n}, "
                    f"got {step.n}; step n values must be sequential "
                    f"starting from 1"
                )
        return self

    @model_validator(mode="after")
    def _check_checkpoints_reference_valid_steps(self) -> "ExecutionStrategy":
        valid_indices = {step.n for step in self.steps}
        for cp in self.checkpoints:
            if cp not in valid_indices:
                raise ValueError(
                    f"checkpoint {cp} does not reference any step; "
                    f"valid step indices are {sorted(valid_indices)}"
                )
        return self
