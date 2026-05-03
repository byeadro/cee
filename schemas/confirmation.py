"""Confirmation + ConfirmationRequest artifact schemas.

Persisted at ``~/cee/runs/<run_id>/confirmation_request.json`` and
``~/cee/runs/<run_id>/confirmation.json`` per bible 12 §7.3 lines
383-384. The destructive-action gate's two-artifact lifecycle:

* ``ConfirmationRequest`` — emitted by SAFETY_GATE *at the gate* when
  ``flags.destructive_potential = true`` (per bible 12 §5.4 + §7.3
  line 383). Carries the bible §5.4 lines 220-228 user-facing message
  payload.
* ``Confirmation`` — written by SAFETY_GATE *when OPERATOR confirms*
  via ``cee confirm <run_id>`` (per bible 12 §7.3 line 384). Three
  fields verbatim: ``timestamp``, ``command_used``, ``operator_identity``
  (from ``whoami``).

**Two coupled models in one file** mirrors T6's ``RedactionLog`` +
``RedactionLogEntry`` template — tightly-coupled lifecycle, one
schema file, both exported.

**``produced_by`` divergence between the two:**

* ``ConfirmationRequest.produced_by = RoleEnum.SAFETY_GATE`` — the
  gate emits the request when destructive_potential is true.
* ``Confirmation.produced_by = RoleEnum.OPERATOR`` — bible §7.3 line
  384 makes OPERATOR the authoring identity ("written when OPERATOR
  confirms"). Different actor → different ``produced_by``. This
  diverges from T6's ``RedactionLog.produced_by = SAFETY_GATE`` where
  SAFETY_GATE is both producer and persister; here OPERATOR
  authorises and SAFETY_GATE merely persists. Surfaced as downstream
  candidate #50 for bible canonization.

**Bible-silent on ConfirmationRequest JSON shape:** Bible §7.3 line
383 names the artifact path but does not enumerate fields. T8
defines minimal viable shape from the bible §5.4 lines 220-228
user-facing message template — every field surfaces somewhere in
that message (run_id at line 222, action_description at line 220,
affects at line 223, confirm/cancel commands at lines 225-226). The
``requested_at`` ISO 8601 timestamp is implicit but required for the
bible §5.4 line 232 24-hour auto-abort calculation. Bible silence
surfaced as downstream candidate #47 for shape canonization.

Bible references:

* **12 §5.4** — destructive-action gate behaviour + user-facing
  message template (lines 220-228).
* **12 §7.3** — confirmation artifacts (lines 383-384).
* **12 §11 line 468** — ``safety_gate/confirmation.py`` module home.
* **19 §5.1 line 111** — ``HaltType.AWAITING_DESTRUCTIVE_CONFIRMATION``
  enum value (already shipped Phase 1).
* **20 §5.3** — Phase 3 output: "destructive-action gate".
"""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from roles import RoleEnum


class ConfirmationRequest(BaseModel):
    """Per-Run destructive-action gate request, persisted at
    ``~/cee/runs/<run_id>/confirmation_request.json`` per bible 12 §7.3.

    Field set is T8-defined per the bible §5.4 lines 220-228
    user-facing message template; bible §7.3 silent on JSON shape
    (downstream candidate #47).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    schema_version: str = "1.0.0"
    produced_by: RoleEnum = RoleEnum.SAFETY_GATE
    run_id: Annotated[str, Field(min_length=1)]
    action_description: Annotated[str, Field(min_length=1)]
    affects: list[str] = Field(default_factory=list)
    requested_at: Annotated[str, Field(min_length=1)]
    confirm_command: Annotated[str, Field(min_length=1)]
    cancel_command: Annotated[str, Field(min_length=1)]


class Confirmation(BaseModel):
    """Per-Run destructive-action confirmation receipt, persisted at
    ``~/cee/runs/<run_id>/confirmation.json`` per bible 12 §7.3 line 384.

    Three core fields verbatim from bible §7.3 line 384:
    ``timestamp``, ``command_used``, ``operator_identity`` (from
    ``whoami``). ``produced_by = RoleEnum.OPERATOR`` per bible's
    "written when OPERATOR confirms" wording (downstream candidate
    #50 if bible later canonizes SAFETY_GATE for consistency with
    RedactionLog).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    schema_version: str = "1.0.0"
    produced_by: RoleEnum = RoleEnum.OPERATOR
    timestamp: Annotated[str, Field(min_length=1)]
    command_used: Annotated[str, Field(min_length=1)]
    operator_identity: Annotated[str, Field(min_length=1)]
