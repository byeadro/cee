"""SkillSet artifact schema.

Authorized by System Design Bible section 07 §7.1. Produced by SKILL_ENGINE
from IntentObject + Classification + AgentPlan; persisted at
``~/cee/runs/<run_id>/skills.json``.

Match zones per bible 07 Rule 4 / §6.3 thresholds:
- ``reuse``    : score >= 0.85 (REUSE_THRESHOLD)
- ``ask``      : 0.60 <= score < 0.85 (ASK_THRESHOLD)
- ``generate`` : score < 0.60
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from roles import RoleEnum

# Bible 15 §5.1: kebab-case ASCII, 3–60 chars.
_KEBAB_CASE_PATTERN = r"^[a-z][a-z0-9-]{1,58}[a-z0-9]$"

# Bible 15 §5.2: version is semver. Examples: "1.0.0", "2.3.1". Permits
# pre-release ("-rc.1") and build ("+sha.abc") suffixes per the spec.
_SEMVER_PATTERN = r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$"

MatchZone = Literal["reuse", "ask", "generate"]

# Threshold constants from bible 07 Rule 4 / §6.3.
_REUSE_THRESHOLD = 0.85
_ASK_THRESHOLD = 0.60


def _expected_zone_for_score(score: float) -> MatchZone:
    """Map a match score to its canonical zone per bible 07 §6.3."""
    if score >= _REUSE_THRESHOLD:
        return "reuse"
    if score >= _ASK_THRESHOLD:
        return "ask"
    return "generate"


class SkillRef(BaseModel):
    """A single Skill reference inside a SkillSet.

    Per bible 07 §7.1 the canonical core is ``slug``, ``version``, ``path``.
    ``match_score`` / ``match_zone`` / ``generated_in_run`` are matcher
    audit-trail fields beyond the canonical core (bible doesn't forbid
    additions). The Skill file lives at ``~/cee/skills/<slug>/SKILL.md``;
    ``path`` is the file location. ``version`` mirrors the Skill file's
    frontmatter ``version`` (bible 15 §5.2 semver).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    slug: Annotated[str, Field(pattern=_KEBAB_CASE_PATTERN)]
    version: Annotated[str, Field(pattern=_SEMVER_PATTERN)]
    path: Annotated[str, Field(min_length=1)]
    match_score: Annotated[float, Field(ge=0.0, le=1.0)]
    match_zone: MatchZone
    generated_in_run: bool = False

    @model_validator(mode="after")
    def _check_zone_aligns_with_score(self) -> "SkillRef":
        expected = _expected_zone_for_score(self.match_score)
        if self.match_zone != expected:
            raise ValueError(
                f"match_zone ({self.match_zone}) does not match "
                f"score {self.match_score}; expected {expected} "
                f"(reuse>={_REUSE_THRESHOLD}, ask>={_ASK_THRESHOLD}, "
                f"else generate)"
            )
        return self


class SkillSet(BaseModel):
    """The set of Skills resolved for the Run.

    Per bible 07 §7.1: ``skills`` lists every Skill referenced by the
    FinalPrompt (reused + generated); ``newly_generated`` lists only those
    generated in the current Run (used by the promotion queue per §5.5).
    Both lists may be empty — LOW-complexity Runs whose capabilities are
    covered by the primary agent's general skills require no Skill.
    Bible §7.1: "When new Skills are generated, they appear in both
    ``skills`` (referenced by the FinalPrompt) and ``newly_generated``
    (for promotion queue tracking)."
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    skills: list[SkillRef] = Field(default_factory=list)
    newly_generated: list[SkillRef] = Field(default_factory=list)
    produced_by: RoleEnum = RoleEnum.SKILL_ENGINE
