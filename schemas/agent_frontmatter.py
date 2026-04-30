"""AgentFrontmatter schema.

Authorized by System Design Bible section 06 §5.2.1 ("Frontmatter
schema"). Models the YAML frontmatter at the top of every agent file at
``~/cee/.claude/agents/<slug>.md``.

Bible 06 §5.2.1 names the seven required fields (``name``,
``description``, ``posture``, ``task_types_supported``, ``capabilities``,
``allowed_tools``, ``version``) and the optional fields (``domain`` —
required when ``posture == "specialist"``, ``created_by_run``,
``created_at``, ``needs_review``).

The ``Posture`` enum is defined locally rather than imported from
``schemas.agent_plan`` to avoid a cross-schema import — both modules
ground the closed enum in bible 06 §5.1 / §5.2.1, so duplication here is
intentional and version-locked by the bible-grounding test below.

This schema is a sub-structure (not a top-level pipeline artifact), so
there is no ``produced_by`` field.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Bible 15 §5.1 (referenced by bible 06 §11): kebab-case slug regex,
# 3-60 chars. Agent slugs share the convention with Skill slugs.
_KEBAB_CASE_PATTERN = r"^[a-z][a-z0-9-]{1,58}[a-z0-9]$"

# Bible 06 §5.2.1: ``version`` is semver, same regex as
# ``SkillRef.version`` and ``SkillFrontmatter.version``.
_SEMVER_PATTERN = r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$"

# Permissive ISO 8601 shape; mirrors ``SkillFrontmatter._ISO_8601_PATTERN``.
_ISO_8601_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}"
    r"(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?$"
)

# Bible 06 §5.2.1: ``created_by_run`` is a run_id or the literal "manual".
# (Unlike SkillFrontmatter, agents have no "seed" provenance — agent files
# either ship by hand or are generated in a Run.)
_RUN_ID_PATTERN = r"^\d{8}_\d{6}_[0-9a-f]{8}$"
_CREATED_BY_RUN_PATTERN = rf"^({_RUN_ID_PATTERN[1:-1]}|manual)$"

# Bible 06 §5.1 / §5.2.1: closed posture enum. Defined locally rather
# than imported from ``schemas.agent_plan`` to avoid coupling the
# frontmatter schema to the pipeline artifact module.
Posture = Literal["primary", "critic", "optimizer", "orchestrator", "specialist"]

# Bible 08 §5.1 / bible 06 §5.2.1: closed task_type enum. Mirrors
# ``schemas.classification.TaskType``.
TaskTypeSupported = Literal[
    "BUILD",
    "ANALYZE",
    "DEBUG",
    "WRITE",
    "RESEARCH",
    "TRANSFORM",
    "DECIDE",
    "ORCHESTRATE",
]

# Bible 06 §5.2.1: closed domain enum. Mirrors
# ``schemas.skill_frontmatter.Domain``.
Domain = Literal[
    "code",
    "writing",
    "analysis",
    "research",
    "ops",
    "personal",
    "other",
]


class AgentFrontmatter(BaseModel):
    """The YAML frontmatter block at the top of an agent file.

    Required fields per bible 06 §5.2.1: ``name``, ``description``,
    ``posture``, ``task_types_supported``, ``capabilities``,
    ``allowed_tools``, ``version``.

    Optional fields per bible 06 §5.2.1: ``domain`` (required when
    ``posture == "specialist"``), ``created_by_run``, ``created_at``,
    ``needs_review`` (default False).

    Field order mirrors bible 06 §5.2.1's YAML block.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    # Required (bible 06 §5.2.1)
    name: Annotated[str, Field(pattern=_KEBAB_CASE_PATTERN)]
    description: Annotated[str, Field(min_length=1)]
    posture: Posture
    task_types_supported: Annotated[
        list[TaskTypeSupported],
        Field(min_length=1, max_length=8),
    ]
    capabilities: Annotated[list[str], Field(min_length=1)]
    allowed_tools: Annotated[list[str], Field(min_length=1)]
    version: Annotated[str, Field(pattern=_SEMVER_PATTERN)]

    # Optional (bible 06 §5.2.1)
    domain: Domain | None = None
    created_by_run: Annotated[
        str | None,
        Field(default=None, pattern=_CREATED_BY_RUN_PATTERN),
    ]
    created_at: Annotated[
        str | None,
        Field(default=None, pattern=_ISO_8601_PATTERN),
    ]
    needs_review: bool = False

    @model_validator(mode="after")
    def _check_specialist_requires_domain(self) -> "AgentFrontmatter":
        """Bible 06 §5.2.1: ``domain`` is required when
        ``posture == "specialist"``. The selector keys specialist
        candidates by domain (bible 06 §5.3), so a specialist without a
        declared domain is unmatchable.
        """
        if self.posture == "specialist" and self.domain is None:
            raise ValueError(
                "domain is required when posture == 'specialist' "
                "(bible 06 §5.2.1)"
            )
        return self
