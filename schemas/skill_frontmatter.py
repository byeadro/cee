"""SkillFrontmatter schema.

Authorized by System Design Bible section 15 §5.2 ("Frontmatter schema
(full)"). Models the YAML frontmatter at the top of every Skill file at
``~/cee/skills/<slug>/SKILL.md``.

Bible 15 §5.1 defines the slug regex shared with agent slugs and
``schemas.skill_set.SkillRef.slug`` (3-60 chars, lowercase kebab-case).
Bible 15 §5.2 names the seven required fields plus a closed set of
optional fields and the per-field constraints (semver for ``version``,
1-10 entries for ``triggers``/``inputs``/``outputs``, 1-8 entries for
``task_types_supported``, 0-5 entries for ``posture_hints``, etc.).

This schema is a sub-structure (not a top-level pipeline artifact), so
there is no ``produced_by`` field. ``SCHEMA_VERSION`` tracks the schema's
own evolution independently of any individual Skill's ``version`` field.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Bible 15 §5.1: kebab-case ASCII, 3-60 chars (regex includes the
# leading letter and trailing letter/digit constraints).
_KEBAB_CASE_PATTERN = r"^[a-z][a-z0-9-]{1,58}[a-z0-9]$"

# Bible 15 §5.2: ``version`` is semver MAJOR.MINOR.PATCH, with optional
# pre-release and build metadata suffixes per SemVer 2.0.0. Same regex
# used by SkillRef.version.
_SEMVER_PATTERN = r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$"

# ISO 8601: a permissive shape check. Full ISO 8601 validation belongs to
# the consumer; here we just guard against empty strings or obvious
# malformed inputs at the schema boundary.
_ISO_8601_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}"
    r"(T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?)?$"
)

# Bible 15 §5.2: ``created_by_run`` is a run_id, the literal string
# "manual", or the literal string "seed" (only seed Skills shipped at
# install time use the "seed" value). Run-id pattern mirrors bible 04 §5.1
# (also used by ClarificationRequest.run_id).
_RUN_ID_PATTERN = r"^\d{8}_\d{6}_[0-9a-f]{8}$"
_PROVENANCE_PATTERN = (
    rf"({_RUN_ID_PATTERN[1:-1]}|manual|seed)"
)
_CREATED_BY_RUN_PATTERN = rf"^{_PROVENANCE_PATTERN}$"

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

PostureHint = Literal[
    "primary",
    "critic",
    "optimizer",
    "orchestrator",
    "specialist",
]

Domain = Literal[
    "code",
    "writing",
    "analysis",
    "research",
    "ops",
    "personal",
    "other",
]

Sensitivity = Literal["low", "medium", "high"]


class SkillFrontmatter(BaseModel):
    """The YAML frontmatter block at the top of a Skill file.

    Required fields per bible 15 §5.2: ``name``, ``description``,
    ``version``, ``triggers``, ``inputs``, ``outputs``,
    ``task_types_supported``, ``created_at``, ``created_by_run``.

    Optional fields per bible 15 §5.2: ``posture_hints``, ``domain``,
    ``created_from_input`` (required when ``created_by_run`` is a run_id
    rather than ``manual``/``seed``), ``sensitivity``,
    ``grounding_required``, ``disabled``, ``needs_review``,
    ``deprecated_at``, ``replacement_slug``, ``notes``.

    Field order mirrors bible 15 §5.2's YAML block (required first, then
    optional).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    # Required (bible 15 §5.2)
    name: Annotated[str, Field(pattern=_KEBAB_CASE_PATTERN)]
    description: Annotated[str, Field(min_length=1)]
    version: Annotated[str, Field(pattern=_SEMVER_PATTERN)]
    triggers: Annotated[
        list[Annotated[str, Field(min_length=3, max_length=100)]],
        Field(min_length=1, max_length=10),
    ]
    inputs: Annotated[list[str], Field(min_length=1, max_length=10)]
    outputs: Annotated[list[str], Field(min_length=1, max_length=10)]
    task_types_supported: Annotated[
        list[TaskTypeSupported],
        Field(min_length=1, max_length=8),
    ]
    created_at: Annotated[str, Field(pattern=_ISO_8601_PATTERN)]
    created_by_run: Annotated[str, Field(pattern=_CREATED_BY_RUN_PATTERN)]

    # Optional (bible 15 §5.2)
    posture_hints: Annotated[
        list[PostureHint],
        Field(default_factory=list, max_length=5),
    ]
    domain: Domain | None = None
    created_from_input: str | None = None
    sensitivity: Sensitivity | None = None
    grounding_required: bool = False
    disabled: bool = False
    needs_review: bool = False
    deprecated_at: Annotated[str | None, Field(default=None, pattern=_ISO_8601_PATTERN)]
    replacement_slug: Annotated[
        str | None,
        Field(default=None, pattern=_KEBAB_CASE_PATTERN),
    ]
    notes: str | None = None

    @model_validator(mode="after")
    def _check_provenance_inputs_consistency(self) -> "SkillFrontmatter":
        """Bible 15 §5.2: ``created_from_input`` is required when
        ``created_by_run`` is a run_id (i.e., not ``manual`` / ``seed``).
        Generated Skills must preserve the verbatim input that triggered
        their creation for promotion review.
        """
        is_run_provenance = self.created_by_run not in {"manual", "seed"}
        if is_run_provenance and not self.created_from_input:
            raise ValueError(
                "created_from_input is required when created_by_run is a "
                "run_id (manual/seed Skills exempt)"
            )
        return self
