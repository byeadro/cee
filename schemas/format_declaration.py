"""FormatDeclaration schema.

Authorized by System Design Bible section 10 §5 / §7. Models the
sub-structure that PROMPT_BUILDER renders into the FinalPrompt's
``<output_format>`` tag (bible 10 §5.6).

The closed format-type catalog comes from bible 10 §5.1 (eighteen
entries). Any format declaration must reduce to one of these:

* ``code_file`` / ``code_project`` (BUILD)
* ``prose_short`` / ``prose_long`` / ``prose_manuscript`` (WRITE)
* ``markdown_report`` (ANALYZE, RESEARCH)
* ``markdown_decision`` (DECIDE)
* ``diagnosis_and_fix`` (DEBUG)
* ``json_object`` / ``json_array`` (TRANSFORM, ANALYZE)
* ``csv_table`` (TRANSFORM, ANALYZE)
* ``mixed_artifact`` (ORCHESTRATE)
* ``email_draft`` (WRITE)
* ``outline`` (RESEARCH, WRITE)
* ``comparison_table`` (ANALYZE, DECIDE)
* ``step_by_step_guide`` (BUILD, WRITE)
* ``code_review`` (DEBUG, ANALYZE)
* ``audit_report`` (ANALYZE)

This schema is a sub-structure used by PROMPT_BUILDER, not a top-level
on-disk artifact. The persisted form (``FormatDeclaration`` at
``~/cee/runs/<run_id>/format.json`` per bible 10 §7.1, including
``produced_by``) is a separate concern. ``SCHEMA_VERSION`` lives only on
the top-level model.

Bible 10 §5.4's nested ``structure`` object carries format-specific
sub-fields (``required_sections``, ``heading_level``, ``columns``,
``schema``, etc.). This schema flattens the most commonly used keys
(``required_sections``, ``heading_convention``, ``inline_schema``,
``required_artifacts``) into top-level optional fields so that the
``output_format.j2`` renderer can address them without unpacking a
polymorphic nested object. Format-specific keys not represented here
(e.g. ``columns`` for ``csv_table``) belong to a future revision when
those formats are wired through Phase 2 validation.

NOTE: This schema describes the contents of FinalPrompt's
``<output_format>`` tag (flattened fields: ``type``, ``shape``,
``required_sections``, ``heading_convention``, ``acceptance_criteria``,
``inline_schema``, ``required_artifacts``). Bible 10 §5.4 also defines a
persisted-artifact form using ``format_type`` (not ``type``) and a
polymorphic nested ``structure`` object for future on-disk storage. That
model is not implemented in task 8c — TODO future task: add
``FormatArtifact`` (or extend this model) when the persisted artifact is
needed (likely Phase 5 — output format subsystem).
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

# Bible 10 §5.1: the closed format catalog (18 entries, in catalog order).
FormatType = Literal[
    "code_file",
    "code_project",
    "prose_short",
    "prose_long",
    "prose_manuscript",
    "markdown_report",
    "markdown_decision",
    "diagnosis_and_fix",
    "json_object",
    "json_array",
    "csv_table",
    "mixed_artifact",
    "email_draft",
    "outline",
    "comparison_table",
    "step_by_step_guide",
    "code_review",
    "audit_report",
]


class FormatDeclaration(BaseModel):
    """The contents of the FinalPrompt's ``<output_format>`` tag.

    Per bible 10 §5.6 the rendered XML always carries ``<type>``,
    ``<shape>``, and ``<acceptance_criteria>``. Optional sub-tags
    (``<required_sections>``, ``<heading_convention>``, ``<schema>``,
    ``<required_artifacts>``) are emitted when the corresponding optional
    fields are populated.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    type: FormatType
    shape: Annotated[str, Field(min_length=1)]
    required_sections: list[str] = Field(default_factory=list)
    heading_convention: str | None = None
    acceptance_criteria: Annotated[list[str], Field(min_length=1)]
    inline_schema: str | None = None
    required_artifacts: list[str] = Field(default_factory=list)
