"""IntentObject artifact schema.

Authorized by System Design Bible section 00 §5 Step 2 and section 01.
Produced by the INTERPRETER from RawInput; consumed by the CLASSIFIER and
every downstream module. Persisted at ``~/cee/runs/<run_id>/intent.json``.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class IntentObject(BaseModel):
    """The interpreter's structured extraction of OPERATOR intent.

    Per bible 00 §5 Step 2: the interpreter normalizes free-text input into
    this fixed shape. ``ambiguity_score`` drives the §03 Step 2 branches
    (>0.6 halts for clarification). ``domain`` partitions the executor
    catalog. ``implicit_assumptions`` surface in the FinalPrompt's
    ``<assumptions_made>`` tag (bible 05 §5.2).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    goal: Annotated[str, Field(min_length=1)]
    deliverable: Annotated[str, Field(min_length=1)]
    constraints: list[str] = Field(default_factory=list)
    implicit_assumptions: list[str] = Field(default_factory=list)
    ambiguity_score: Annotated[float, Field(ge=0.0, le=1.0)]
    domain: Literal[
        "code",
        "writing",
        "analysis",
        "research",
        "ops",
        "personal",
        "other",
    ]
    raw_signals: list[str] = Field(default_factory=list)
    # TODO task 9: replace with RoleEnum once roles/__init__.py defines it.
    produced_by: str = "INTERPRETER"
