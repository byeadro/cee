"""RedactionLog + RedactionLogEntry artifact schemas.

Persisted to ``~/cee/runs/<run_id>/redaction_log.json`` per bible 12
§7.2. Records every redaction performed by ``SAFETY_GATE`` during a
Run — pattern name, location, and the placeholder text inserted.
**Never the actual redacted content** (per bible 12 §5.1's closing
note: "Logging the actual sensitive content would defeat the purpose").

**Bible drift surfaced (downstream candidate #40):** Bible 12 §5.1's
``RedactionEntry`` pseudocode (line 105) includes a ``term`` field for
``user_term`` entries (the user-config-defined patterns from
``~/.cee/redact_list``). Bible 12 §7.2's JSON example omits this field,
showing only ``{pattern, location, replaced_with}``. T6 ships the
schema with ``term: str | None = None`` to handle both shapes — built-in
catalog entries set ``term=None`` (matching §7.2's three-field
example); user_term entries set ``term=<the matched user term>``
(matching §5.1's pseudocode). Bible should canonize one shape.

Default ``produced_by = RoleEnum.SAFETY_GATE`` per bible 12 §7.2's
JSON example (``"produced_by": "SAFETY_GATE"``).

Field shape per bible 12 §5.1 + §7.2:

* ``pattern`` — canonical pattern name (e.g., ``anthropic_api_key``,
  ``jwt``, or ``user_term`` for user-config entries).
* ``location`` — where the redaction occurred. Bible §7.2's example
  uses ``"prompt"``; SAFETY_GATE callers may pass ``"context"``,
  ``"attachment:<name>"``, etc.
* ``replaced_with`` — the placeholder string substituted (e.g.,
  ``<redacted:anthropic_api_key>``). Caller-determined; T6 emits
  ``<redacted:{pattern_name}>`` per bible 12 §5.1's f-string template.
* ``term`` — see bible-drift note above. ``None`` for built-in
  patterns; the matched user-term string for user-config entries.
"""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from roles import RoleEnum


class RedactionLogEntry(BaseModel):
    """One redaction event inside a RedactionLog.

    Per the module docstring's bible-drift note, ``term`` is optional:
    built-in catalog entries omit it (or set ``None``); user_term
    entries from ``~/.cee/redact_list`` populate it with the matched
    string.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    pattern: Annotated[str, Field(min_length=1)]
    location: Annotated[str, Field(min_length=1)]
    replaced_with: Annotated[str, Field(min_length=1)]
    term: str | None = None


class RedactionLog(BaseModel):
    """Per-Run redaction summary persisted at
    ``~/cee/runs/<run_id>/redaction_log.json`` per bible 12 §7.2.

    Mirrors ``SyncMeta`` / ``PromotionQueue`` wrapper convention:
    ``schema_version`` carried as instance field (in addition to the
    ``ClassVar`` ``SCHEMA_VERSION``) since this is durable cross-Run
    state that may outlive its schema definition.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    schema_version: str = "1.0.0"
    produced_by: RoleEnum = RoleEnum.SAFETY_GATE
    redactions: list[RedactionLogEntry] = Field(default_factory=list)
