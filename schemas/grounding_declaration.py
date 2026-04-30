"""GroundingDeclaration schema.

Authorized by System Design Bible section 11 §5 / §7. Models the
sub-structure that PROMPT_BUILDER renders into the FinalPrompt's
``<grounding_rules>`` tag (bible 11 §5.4) when ``flags.needs_grounding``
is true.

The eight closed source types come from bible 11 §5.1 and are the only
allowed values inside ``<allowed_sources>``:

* ``attachment`` — file in ``IntentObject.attachments``
* ``filesystem_path`` — file/directory the executor reads at run time
* ``url`` — web URL (Phase 2 fetched, Phase 1 user-pasted)
* ``internal_skill_reference`` — a Skill that encodes domain knowledge
* ``bible_section`` — section of CEE's own System Design Bible
* ``prior_run_artifact`` — artifact from a previous Run
* ``system_of_record`` — documented authoritative source (DB, API)
* ``user_provided_text`` — verbatim user-supplied ground truth

This schema is a sub-structure used by PROMPT_BUILDER, not a top-level
on-disk artifact. The richer persisted form
(``GroundingDeclaration`` artifact at ``~/cee/runs/<run_id>/grounding.json``
per bible 11 §7.1, including ``needs_grounding`` /
``override_acknowledged`` / ``produced_by``) is a separate concern.
``SCHEMA_VERSION`` lives only on the top-level model; ``Source`` is a
pure value type without its own version line.

NOTE: This schema describes the contents of FinalPrompt's
``<grounding_rules>`` tag (3 fields: ``allowed_sources``,
``prohibited_inferences``, ``citation_requirement``). Bible 11 §7.1 also
defines a richer persisted-artifact form with additional fields
(``needs_grounding``, ``override_acknowledged``, ``produced_by``) for
future on-disk storage at ``~/cee/runs/<run_id>/grounding.json``. That
model is not implemented in task 8c — TODO future task: add
``GroundingArtifact`` (or extend this model) when the persisted artifact
is needed (likely Phase 5 — grounding subsystem).
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

# Bible 11 §5.1: the closed source-type enum. Any source declaration
# must reduce to one of these eight values.
SourceType = Literal[
    "attachment",
    "filesystem_path",
    "url",
    "internal_skill_reference",
    "bible_section",
    "prior_run_artifact",
    "system_of_record",
    "user_provided_text",
]


class Source(BaseModel):
    """One entry inside ``<allowed_sources>``.

    Per bible 11 §5.4 each rendered ``<source>`` carries a ``type``
    (closed enum), an ``id`` (stable identifier within the prompt — the
    citation pivot the executor uses), and a human-readable
    ``description`` summarizing the source. The executor cites by ``id``;
    the description is for reader orientation only.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    type: SourceType
    id: Annotated[str, Field(min_length=1)]
    description: Annotated[str, Field(min_length=1)]


class GroundingDeclaration(BaseModel):
    """The contents of the FinalPrompt's ``<grounding_rules>`` tag.

    Per bible 11 §5.3 / §5.4, when ``needs_grounding`` is true the engine
    derives three sub-objects:

    * ``allowed_sources`` — non-empty list of :class:`Source` entries
      (the engine emits a ``ClarificationRequest`` per §5.6 if it cannot
      enumerate any sources, so the rendered tag is never empty).
    * ``prohibited_inferences`` — fabrication-risk prohibitions specific
      to the Run; defaults empty when the engine derives none.
    * ``citation_requirement`` — the inline citation rule the executor
      follows (e.g. "[source_id]"). Defaults to empty string when the
      run's prohibitions cover citation implicitly.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    allowed_sources: Annotated[list[Source], Field(min_length=1)]
    prohibited_inferences: list[str] = Field(default_factory=list)
    citation_requirement: str = ""
