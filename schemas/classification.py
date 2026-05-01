"""Classification artifact schema.

Authorized by System Design Bible section 08 §7.1. Produced by the CLASSIFIER
from an IntentObject; persisted at ``~/cee/runs/<run_id>/classification.json``.

Closed enums:
- ``task_type``: the 8-value enum from bible 08 §5.1.
- ``complexity_tier``: LOW / MEDIUM / HIGH / EXTREME per §5.3.
- ``flags``: 4 bools per §5.4.

Tier thresholds per bible 08 Rule 6: LOW [0,25), MEDIUM [25,50), HIGH [50,75),
EXTREME [75,100]. Hard cap per Rule 5: EXTREME forces requires_human_gate=True.

Audit fields per bible 08 §7.1: ``task_type_candidates`` surfaces runner-up
classifications (used by AMBIGUOUS_CLASSIFICATION halt); ``audit`` captures
the classifier's internal state for replay determinism. Cross-validator per
bible 08 §10.10: when a flag is True, the corresponding trigger list in
``audit.flag_triggers`` must be non-empty.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from roles import RoleEnum

TaskType = Literal[
    "BUILD",
    "ANALYZE",
    "DEBUG",
    "WRITE",
    "RESEARCH",
    "TRANSFORM",
    "DECIDE",
    "ORCHESTRATE",
]

ComplexityTier = Literal["LOW", "MEDIUM", "HIGH", "EXTREME"]


class ComplexityComponents(BaseModel):
    """The four 0–25 component scores summing to ``complexity_score``.

    Per bible 08 §5.2: input_ambiguity (A), output_structure (B),
    agent_count_required (C), skill_count_required (D). Each scored
    independently per the rubric tables in §5.2.1–§5.2.4.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    input_ambiguity: Annotated[int, Field(ge=0, le=25)]
    output_structure: Annotated[int, Field(ge=0, le=25)]
    agent_count_required: Annotated[int, Field(ge=0, le=25)]
    skill_count_required: Annotated[int, Field(ge=0, le=25)]


class ClassificationFlags(BaseModel):
    """The four-flag set from bible 08 §5.4.

    Each flag evaluated independently per §5.4.1–§5.4.4. Flags drive
    downstream tags: ``needs_grounding`` → ``<grounding_rules>``,
    ``sensitive_data`` → SAFETY_GATE redaction, ``destructive_potential`` →
    confirmation gate, ``requires_human_gate`` → ``<safety_banner>``.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    needs_grounding: bool = False
    sensitive_data: bool = False
    destructive_potential: bool = False
    requires_human_gate: bool = False


class CandidateScore(BaseModel):
    """One runner-up task_type candidate with its confidence (bible 08 §7.1).

    The classifier emits all candidates that scored above the noise floor
    in ``Classification.task_type_candidates``. Used by the
    AMBIGUOUS_CLASSIFICATION halt to surface choices to the OPERATOR
    (bible 08 Rule 7: confidence delta < 0.10 triggers halt).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    value: TaskType
    confidence: Annotated[float, Field(ge=0.0, le=1.0)]


class FlagTriggers(BaseModel):
    """Per-flag trigger descriptions from bible 08 §7.1's ``audit.flag_triggers``.

    Each list contains free-form trigger descriptions naming what fired the
    corresponding flag (regex match, redact_list pattern, verb-class hit,
    etc.). Bible 08 §10.10: when a flag is True, its trigger list must be
    non-empty — enforced by Classification's cross-validator.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    needs_grounding: list[str] = Field(default_factory=list)
    sensitive_data: list[str] = Field(default_factory=list)
    destructive_potential: list[str] = Field(default_factory=list)
    requires_human_gate: list[str] = Field(default_factory=list)


class ClassificationAudit(BaseModel):
    """The classifier's internal-state telemetry (bible 08 §7.1).

    Captures which precedence rule fired, whether tier escalation or the
    EXTREME force-gate kicked in, and the per-flag trigger lists. Used for
    replay determinism (bible 03 Rule 5) and for the §10.10 schema
    invariant on flag triggers.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    task_type_precedence_fired: TaskType
    tier_escalation_applied: bool = False
    extreme_human_gate_forced: bool = False
    flag_triggers: FlagTriggers = Field(default_factory=FlagTriggers)


def _tier_from_score(score: int) -> ComplexityTier:
    """Bible 08 Rule 6: inclusive lower bound; boundary scores go higher."""
    if score < 25:
        return "LOW"
    if score < 50:
        return "MEDIUM"
    if score < 75:
        return "HIGH"
    return "EXTREME"


class Classification(BaseModel):
    """The classifier's labeled view of the Run.

    Per bible 08 §7.1. Validators enforce: ``complexity_score`` equals the
    sum of its four components (deterministic by Rule 4); ``complexity_tier``
    aligns with score per the §5.3 thresholds; EXTREME tier forces
    ``requires_human_gate=True`` per Rule 5; per §10.10, every True flag has
    a non-empty trigger list in ``audit.flag_triggers``.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    task_type: TaskType
    task_type_candidates: list[CandidateScore] = Field(default_factory=list)
    complexity_score: Annotated[int, Field(ge=0, le=100)]
    complexity_tier: ComplexityTier
    complexity_components: ComplexityComponents
    flags: ClassificationFlags
    audit: ClassificationAudit
    produced_by: RoleEnum = RoleEnum.CLASSIFIER

    @model_validator(mode="after")
    def _check_score_equals_components_sum(self) -> "Classification":
        components_sum = (
            self.complexity_components.input_ambiguity
            + self.complexity_components.output_structure
            + self.complexity_components.agent_count_required
            + self.complexity_components.skill_count_required
        )
        if self.complexity_score != components_sum:
            raise ValueError(
                f"complexity_score ({self.complexity_score}) must equal "
                f"sum of complexity_components ({components_sum})"
            )
        return self

    @model_validator(mode="after")
    def _check_tier_aligns_with_score(self) -> "Classification":
        expected = _tier_from_score(self.complexity_score)
        if self.complexity_tier != expected:
            raise ValueError(
                f"complexity_tier ({self.complexity_tier}) does not match "
                f"score {self.complexity_score}; expected {expected}"
            )
        return self

    @model_validator(mode="after")
    def _check_flag_triggers_non_empty(self) -> "Classification":
        """Bible 08 §10.10: every True flag must have a non-empty trigger list."""
        for flag_name in (
            "needs_grounding",
            "sensitive_data",
            "destructive_potential",
            "requires_human_gate",
        ):
            if getattr(self.flags, flag_name):
                triggers = getattr(self.audit.flag_triggers, flag_name)
                if not triggers:
                    raise ValueError(
                        f"flags.{flag_name} is True but "
                        f"audit.flag_triggers.{flag_name} is empty; "
                        f"bible 08 §10.10 requires a logged trigger "
                        f"for every True flag"
                    )
        return self

    @model_validator(mode="before")
    @classmethod
    def _force_human_gate_for_extreme(cls, data: Any) -> Any:
        """Bible 08 Rule 5: EXTREME tier forces requires_human_gate=True.

        Applied before field validation so that constructions that would
        otherwise carry ``requires_human_gate=False`` are coerced to True
        rather than rejected — this matches the bible's "force the flag"
        semantics rather than failing the construction.
        """
        if not isinstance(data, dict):
            return data
        if data.get("complexity_tier") != "EXTREME":
            return data
        flags = data.get("flags")
        if isinstance(flags, dict):
            flags["requires_human_gate"] = True
        elif isinstance(flags, ClassificationFlags):
            data["flags"] = flags.model_copy(
                update={"requires_human_gate": True}
            )
        return data
