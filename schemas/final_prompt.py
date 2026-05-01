"""FinalPrompt artifact schema.

Authorized by System Design Bible section 05 §5.1 (the canonical 15-tag
schema) and §5.2 (per-tag content rules). Produced by PROMPT_BUILDER from
all prior artifacts; persisted at ``~/cee/runs/<run_id>/prompt.xml``.

Tag set and order match bible 05 §5.1 Table:
1. ``<final_prompt>``     (top-level wrapper, implicit at this layer)
2. ``<target_executor>``  R
3. ``<context>``          R
4. ``<role>``             R
5. ``<task>``             R
6. ``<agents>``           C  (when more than one agent)
7. ``<skills>``           C  (when SkillSet non-empty)
8. ``<execution_plan>``   R
9. ``<constraints>``      R  (rendered as "None." if list empty per §5.2)
10. ``<grounding_rules>`` C  (when flags.needs_grounding)
11. ``<assumptions_made>`` C (when implicit_assumptions non-empty)
12. ``<output_format>``   R
13. ``<stop_conditions>`` R
14. ``<safety_banner>``   C  (when requires_human_gate or destructive_potential)
15. ``<run_metadata>``    O  (suppressed via --no-metadata)

Plus ``<chunking>`` per §5.4 when the prompt exceeds the token budget.

XML rendering is implemented by ``prompt_builder.builder`` per bible 20 §5.6.
This schema only defines the data shape; ``to_xml()`` is a deferred stub.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from roles import RoleEnum

TargetExecutor = Literal["claude_ai", "claude_code", "api"]
ComplexityTier = Literal["LOW", "MEDIUM", "HIGH", "EXTREME"]


# --------------------------------------------------------------------------- #
# Nested models for required tags                                             #
# --------------------------------------------------------------------------- #


class AttachmentSummary(BaseModel):
    """One attachment summary inside ``<context>`` (bible 05 §5.2)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    name: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]


class Context(BaseModel):
    """The ``<context>`` tag content (bible 05 §5.2).

    ``original_input`` carries the OPERATOR's verbatim input;
    ``attachment_summaries`` is one entry per attachment;
    ``inferred_context`` captures the interpreter's pulled context from
    prior Runs (marked as such per the bible).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    original_input: Annotated[str, Field(min_length=1)]
    attachment_summaries: list[AttachmentSummary] = Field(default_factory=list)
    inferred_context: str | None = None


class PlanStep(BaseModel):
    """One step inside the ``<execution_plan>`` tag (bible 05 §5.2)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    n: Annotated[int, Field(ge=1)]
    action: Annotated[str, Field(min_length=1)]
    checkpoint: str | None = None


class ExecutionPlan(BaseModel):
    """The ``<execution_plan>`` tag content (bible 05 §5.2).

    LOW tasks have one step; EXTREME tasks have many. Order is the
    iteration order of ``steps``.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    steps: Annotated[list[PlanStep], Field(min_length=1)]


class OutputFormat(BaseModel):
    """The ``<output_format>`` tag content (bible 05 §5.2).

    Always concrete per bible Rule: never "appropriate format" or "as you
    see fit." A single ``description`` string captures the per-task_type
    template (bible 05 §5.2 lists shape per task_type).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    description: Annotated[str, Field(min_length=1)]


class StopConditions(BaseModel):
    """The ``<stop_conditions>`` tag content (bible 05 §5.2).

    Always at least one condition: per bible, "task complete and output
    validates against ``<output_format>``."
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    conditions: Annotated[list[str], Field(min_length=1)]


class RunMetadata(BaseModel):
    """The ``<run_metadata>`` tag content (bible 05 §5.2).

    Trace info, suppressible via the CLI ``--no-metadata`` flag (the field
    on FinalPrompt then becomes None — see ``FinalPrompt.run_metadata``).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    run_id: Annotated[str, Field(min_length=1)]
    generated_at: Annotated[str, Field(min_length=1)]
    complexity: ComplexityTier
    complexity_score: Annotated[int, Field(ge=0, le=100)]
    bible_version: Annotated[str, Field(min_length=1)]


# --------------------------------------------------------------------------- #
# Nested models for conditional tags                                          #
# --------------------------------------------------------------------------- #


class AgentEntry(BaseModel):
    """One agent reference inside the ``<agents>`` tag (bible 05 §5.2)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    role: Annotated[str, Field(min_length=1)]
    path: Annotated[str, Field(min_length=1)]


class Agents(BaseModel):
    """The ``<agents>`` tag content (bible 05 §5.2).

    Present when ``AgentPlan`` references more than one agent. The
    ``coordination`` field is the 1–2 sentence handoff description.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    entries: Annotated[list[AgentEntry], Field(min_length=1)]
    coordination: Annotated[str, Field(min_length=1)]


class SkillEntry(BaseModel):
    """One Skill reference inside the ``<skills>`` tag (bible 05 §5.2)."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    name: Annotated[str, Field(min_length=1)]
    path: Annotated[str, Field(min_length=1)]


class Skills(BaseModel):
    """The ``<skills>`` tag content (bible 05 §5.2).

    Present when ``SkillSet`` is non-empty. Path semantics depend on
    ``target_executor`` per bible 05 §5.3.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    entries: Annotated[list[SkillEntry], Field(min_length=1)]


class GroundingRules(BaseModel):
    """The ``<grounding_rules>`` tag content (bible 05 §5.2).

    Three sub-sections: allowed sources, prohibited inferences, citation
    requirement. Present when ``flags.needs_grounding`` is true on the
    upstream Classification.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    allowed_sources: Annotated[list[str], Field(min_length=1)]
    prohibited_inferences: list[str] = Field(default_factory=list)
    citation_requirement: Annotated[str, Field(min_length=1)]


class AssumptionsMade(BaseModel):
    """The ``<assumptions_made>`` tag content (bible 05 §5.2).

    Present when ``IntentObject.implicit_assumptions`` is non-empty. The
    ``flag_back_instruction`` invites the executor to halt if any
    assumption is wrong.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    assumptions: Annotated[list[str], Field(min_length=1)]
    flag_back_instruction: Annotated[str, Field(min_length=1)]


class Chunking(BaseModel):
    """Chunk metadata when the prompt exceeds budget (bible 05 §5.4).

    Each chunk gets ``<chunk_metadata>`` with ``n`` and ``of``; the first
    chunk additionally carries ``<chunking_instructions>`` telling the
    executor to wait for all chunks.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    n: Annotated[int, Field(ge=1)]
    of: Annotated[int, Field(ge=1)]
    chunking_instructions: str | None = None


# --------------------------------------------------------------------------- #
# FinalPrompt                                                                 #
# --------------------------------------------------------------------------- #


class FinalPrompt(BaseModel):
    """The Run's deliverable artifact (bible 05 §5.1).

    Field order matches the §5.1 tag order so ``model_dump()`` output is
    stable for byte-deterministic JSON. Optional fields default to None (or
    empty list for ``constraints``); rendering logic in
    ``prompt_builder.builder`` handles absence vs empty per bible §4.

    The ``to_xml()`` method is a deferred stub — XML rendering happens in
    Phase 6 per bible 20 §5.6, not at schema construction time.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    # Required fields, ordered by §5.1 tag position.
    target_executor: TargetExecutor
    context: Context
    role: Annotated[str, Field(min_length=1)]
    task: Annotated[str, Field(min_length=1)]

    # Conditional/optional fields between role and execution_plan.
    agents: Agents | None = None
    skills: Skills | None = None

    execution_plan: ExecutionPlan
    constraints: list[str] | None = None
    grounding_rules: GroundingRules | None = None
    assumptions_made: AssumptionsMade | None = None
    output_format: OutputFormat
    stop_conditions: StopConditions
    safety_banner: str | None = None
    run_metadata: RunMetadata
    chunking: Chunking | None = None

    produced_by: RoleEnum = RoleEnum.PROMPT_BUILDER

    def to_xml(self) -> str:
        """Render this model as XML matching bible 05 §5.1 structure.

        Implemented by ``prompt_builder.builder`` in Phase 6 per bible
        20 §5.6. The schema layer only defines the data shape.
        """
        raise NotImplementedError(
            "FinalPrompt.to_xml is implemented by prompt_builder.builder "
            "in Phase 6 per bible 20 §5.6"
        )
