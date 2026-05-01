"""RunError artifact schema (NOT the exception class).

Authorized by System Design Bible section 03 §7.3 and section 19 §5.5.
Produced by the pipeline driver at ``~/cee/runs/<run_id>/error.json`` when
a :class:`cee.errors.exceptions.RunError` exception terminates a Run
unrecoverably (bible 19 §5.7 dispatch flow).

This module defines the *artifact* — the JSON file written when a Run
fails. The corresponding *exception class* lives at
``cee.errors.exceptions.RunError``; both can coexist — one is the
persisted data, the other is the runtime signal. To avoid a name
collision, ``schemas/__init__.py`` re-exports this class as
``RunErrorArtifact``.

Bible 03 §7.3 mandates the four canonical fields ``{failed_step,
error_type, error_message, recovery_suggestion}``. The remaining fields
(``run_id``, ``error_payload``, ``failed_at_iso_timestamp``,
``produced_by``) carry the contextual data needed by replay (bible 19
§5.5) and by the audit log (bible 19 §7.2). ``error_payload`` mirrors the
``payload`` dict on the underlying ``RunError`` exception (bible 19 §5.7).

The seven valid ``error_type`` values mirror the closed
:class:`cee.errors.types.RunErrorType` enum (bible 19 §5.2). They are
listed here as a ``Literal`` rather than imported as the enum to keep
schemas free of runtime dependencies on the errors package — schemas
are pure data shape. Drift between the two is caught by the
bible-grounding test below and by ``errors.types``'s own grounding tests.
"""

from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from roles import RoleEnum

# Mirrors ``cee.paths._RUN_ID_PATTERN`` (bible 04 §5.1).
_RUN_ID_PATTERN = r"^\d{8}_\d{6}_[0-9a-f]{8}$"


RunErrorTypeLiteral = Literal[
    "schema_violation",
    "driver_bug",
    "confirmation_timeout",
    "replay_drift",
    "unrecoverable_persistence",
    "api_failed",
    "api_rate_limited_terminal",
]


class RunError(BaseModel):
    """The on-disk error artifact for a terminally failed Run.

    Per bible 03 §7.3 the four bible-mandated fields are ``failed_step``,
    ``error_type``, ``error_message``, and ``recovery_suggestion``. The
    schema extends those with ``run_id`` (artifact addressing),
    ``error_payload`` (the typed payload from the exception),
    ``failed_at_iso_timestamp`` (audit-log correlation), and
    ``produced_by`` (role tracking per bible section 02). All extensions
    are bible-section-02 authorized.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    run_id: Annotated[str, Field(pattern=_RUN_ID_PATTERN)]
    error_type: RunErrorTypeLiteral
    failed_step: Annotated[int, Field(ge=1, le=10)]
    error_message: Annotated[str, Field(min_length=1)]
    error_payload: dict[str, Any]
    recovery_suggestion: Annotated[str, Field(min_length=1)]
    failed_at_iso_timestamp: Annotated[str, Field(min_length=1)]
    produced_by: RoleEnum = RoleEnum.PIPELINE_DRIVER
