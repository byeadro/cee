"""Destructive-action gate builders per bible 12 §5.4.

Implements the gate-behaviour half of the SAFETY_GATE per bible 12
§5.4 (the destructive-action gate workflow), §7.3 (confirmation
artifacts), §11 line 468 (module home), and bible 19 §5.1 +
§5.7 (the closed ``HaltType.AWAITING_DESTRUCTIVE_CONFIRMATION`` enum
+ ``PipelineHalt`` exception hierarchy).

**Module location.** This file lives at ``safety_gate/confirmation.py``
per bible 12 §11 line 468 + bible 04 §5.1 + bible 20 §5.3.

**Scope discipline (Path A, locked Step 3).** T8 ships **only**
pure builders + the convenience exception subclass. Three things are
explicitly OUT OF SCOPE:

* **Destructive-action detection.** Bible 12 §5.4 line 233:
  *"The destructive trigger detection lives in section 08 §5.4.3.
  This page only handles the gate behavior."* The CLASSIFIER (Phase 4)
  sets ``flags.destructive_potential`` on the ``Classification``
  artifact; T8 consumes the flag, never re-detects.
* **``cee confirm`` / ``cee abort`` CLI commands** per bible 12 §11
  line 468. T8 supplies the building blocks (:func:`record_confirmation`,
  :class:`AwaitingDestructiveConfirmation`); CLI-side wiring lives in
  ``cli/commands/`` (Track C, downstream candidate #48).
* **24-hour auto-abort background thread** per bible 12 §5.4 line 232
  + §11 line 468. Needs a persistent daemon; pure-builder T8 cannot
  ship the scheduler. Surfaced as downstream candidate #49.

**Public API contract — four pure functions.**

* :func:`build_safety_banner_text` — returns the bible §5.4 line 216
  banner string. Set by the prompt builder on
  :attr:`schemas.FinalPrompt.safety_banner` when the destructive flag
  is true.
* :func:`build_confirmation_request` — pure builder for
  :class:`schemas.ConfirmationRequest`. Derives ``confirm_command`` /
  ``cancel_command`` from ``run_id`` per bible §5.4 lines 225-226.
* :func:`build_operator_message` — pure builder for the bible §5.4
  lines 220-228 user-facing message. Driver / CLI prints this on halt.
* :func:`record_confirmation` — pure builder for
  :class:`schemas.Confirmation`. Caller (CLI) supplies ``timestamp``,
  ``command_used``, and ``operator_identity`` (from ``whoami``) per
  bible §7.3 line 384.

All four are pure: no I/O, no halt emission, no waiting. The pipeline
driver / CLI orchestrates: build request → raise
:class:`errors.AwaitingDestructiveConfirmation` → driver writes
``halt.json`` → CLI reads it → user runs ``cee confirm`` → CLI calls
:func:`record_confirmation` → CLI writes ``confirmation.json`` →
pipeline resumes.

**Banner text is bible-canonical.** :func:`build_safety_banner_text`
returns ``"[CONFIRM BEFORE EXECUTION]"`` verbatim per bible 12 §5.4
line 216. The bible-grounding drift detector test asserts this and
also asserts that bible §5.4 line 233 still defers detection to bible
08 §5.4.3 (catches future bible-edit drift that would invalidate
T8's scope).
"""

from __future__ import annotations

from schemas.confirmation import Confirmation, ConfirmationRequest


# bible 12 §5.4 line 216 — exact banner text inserted into the
# FinalPrompt's <safety_banner> tag when destructive_potential is true.
_SAFETY_BANNER_TEXT: str = "[CONFIRM BEFORE EXECUTION]"


def build_safety_banner_text() -> str:
    """Return the safety banner string per bible 12 §5.4 line 216.

    Pure function. The prompt builder sets the resulting string on
    :attr:`schemas.FinalPrompt.safety_banner` when the destructive
    flag is true. Bible mandates the literal
    ``"[CONFIRM BEFORE EXECUTION]"`` string.
    """
    return _SAFETY_BANNER_TEXT


def build_confirmation_request(
    *,
    run_id: str,
    action_description: str,
    affects: list[str],
    requested_at: str,
) -> ConfirmationRequest:
    """Build a :class:`ConfirmationRequest` for the destructive-action gate.

    Pure builder. ``confirm_command`` and ``cancel_command`` are
    derived deterministically from ``run_id`` per bible 12 §5.4 lines
    225-226 (``"cee confirm <run_id>"`` / ``"cee abort <run_id>"``).

    Parameters
    ----------
    run_id
        The Run identifier (e.g. ``"20260430_141522_a3f8c2d1"``).
    action_description
        Human-readable summary per bible §5.4 line 220 — typically
        derived from the IntentObject + classifier triggers by the
        pipeline driver.
    affects
        List of paths / systems the action would touch per bible
        §5.4 line 223. Empty list is allowed (bible silent on shape;
        downstream candidate #47).
    requested_at
        ISO 8601 timestamp at which SAFETY_GATE emitted the request.
        Required for the bible §5.4 line 232 24-hour auto-abort
        calculation.

    Returns
    -------
    ConfirmationRequest
        A frozen-validated Pydantic instance ready for the caller to
        persist via ``persistence.filesystem_writer.write_json``.
    """
    return ConfirmationRequest(
        run_id=run_id,
        action_description=action_description,
        affects=list(affects),
        requested_at=requested_at,
        confirm_command=f"cee confirm {run_id}",
        cancel_command=f"cee abort {run_id}",
    )


def build_operator_message(request: ConfirmationRequest) -> str:
    """Format the bible 12 §5.4 lines 220-228 user-facing message.

    Pure builder. The CLI prints this on
    :class:`errors.AwaitingDestructiveConfirmation` halt to inform
    the OPERATOR what to do.

    The message format follows the bible §5.4 template verbatim:

        This Run has destructive potential. The action involves: <action_description>.

        Run ID: <run_id>
        Affects: <comma-joined affects, or "(none specified)" if empty>

        Confirm by running: <confirm_command>
        Cancel by running: <cancel_command>

        The Run is paused until one of these commands is issued.
    """
    if request.affects:
        affects_line = ", ".join(request.affects)
    else:
        affects_line = "(none specified)"
    return (
        f"This Run has destructive potential. "
        f"The action involves: {request.action_description}.\n"
        f"\n"
        f"Run ID: {request.run_id}\n"
        f"Affects: {affects_line}\n"
        f"\n"
        f"Confirm by running: {request.confirm_command}\n"
        f"Cancel by running: {request.cancel_command}\n"
        f"\n"
        f"The Run is paused until one of these commands is issued."
    )


def record_confirmation(
    *,
    timestamp: str,
    command_used: str,
    operator_identity: str,
) -> Confirmation:
    """Build the :class:`Confirmation` receipt artifact.

    Pure builder. Called by the CLI after the OPERATOR runs
    ``cee confirm <run_id>``. The resulting instance is persisted by
    the caller to ``~/cee/runs/<run_id>/confirmation.json`` per bible
    12 §7.3 line 384.

    Parameters
    ----------
    timestamp
        ISO 8601 timestamp at confirmation time.
    command_used
        The verbatim CLI command the OPERATOR ran (e.g.
        ``"cee confirm 20260430_141522_a3f8c2d1"``).
    operator_identity
        Output of ``whoami`` per bible §7.3 line 384.
    """
    return Confirmation(
        timestamp=timestamp,
        command_used=command_used,
        operator_identity=operator_identity,
    )
