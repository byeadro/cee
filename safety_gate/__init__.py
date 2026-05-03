"""CEE safety gate — redaction, injection scanning, destructive-action gate.

Per bible 12 §5 (the Detailed Workflow for the Security System), the
safety gate has three responsibilities:

* **Redaction** (§5.1, §5.2, §5.3) — strip sensitive content from
  every artifact written to filesystem, Obsidian, or Notion. Phase 3
  task T6 ships :func:`redact`, :func:`load_user_patterns`, and
  :func:`assert_no_residual` — the pure-transform layer, plus a
  caller-invoked residual scanner.
* **Injection scanning** (§5.5) — Phase 3 task T7. Detects
  prompt-injection patterns in already-redacted text before the
  interpreter runs. Ships :func:`scan_text` (per-string primitive)
  + :class:`InjectionMatch`. The ``scan(raw_input: RawInput)``
  pipeline wrapper is deferred to Phase 5+ pipeline integration
  (downstream candidate #43).
* **Destructive-action gate** (§5.4) — Phase 3 task T8. Halts the
  pipeline before destructive Run completion until the OPERATOR
  confirms via ``cee confirm <run_id>``. Ships four pure builders
  (:func:`build_safety_banner_text`, :func:`build_confirmation_request`,
  :func:`build_operator_message`, :func:`record_confirmation`),
  the two Pydantic schemas (:class:`Confirmation`,
  :class:`ConfirmationRequest`), and the convenience exception
  subclass :class:`errors.AwaitingDestructiveConfirmation`.
  Detection of destructive actions is OUT OF SCOPE per bible 12
  §5.4 line 233 (lives in CLASSIFIER per bible 08 §5.4.3, Phase 4
  territory). ``cee confirm`` / ``cee abort`` CLI commands and 24h
  auto-abort thread defer to Track C / future infrastructure
  (downstream candidates #48 + #49).

Phase 3 T6 public surface:

* :func:`redact` — pure transform. Takes a string, returns
  ``(redacted_text, log_entries)``. No I/O, no audit emission. Caller
  decides what to do with the log.
* :func:`load_user_patterns` — read ``~/.cee/redact_list`` per
  bible 12 §5.3 and return compiled patterns (plain-match + regex:
  prefix). Absent file returns ``[]``.
* :func:`assert_no_residual` — re-scan text for built-in patterns;
  raise :class:`errors.RedactionFailed` on any hit per bible 12 §10.2.
* :class:`errors.RedactionFailed` — re-exported from ``errors`` for
  convenience; defined in :mod:`errors.exceptions` (Phase 1 shipped).

Phase 3 T7 public surface:

* :func:`scan_text` — pure function. Takes a string + location label,
  returns a list of :class:`InjectionMatch`. Runs all three bible
  §5.5 detection categories (direct-override regexes, hidden-unicode,
  CEE tag impersonation). Empty list iff clean. Does not halt — the
  pipeline decides whether to halt with ``injection_detected``.
* :class:`InjectionMatch` — frozen dataclass mirroring bible §5.5's
  ``InjectionFlag``: ``(pattern, location, tag)``.

Phase 3 T8 public surface:

* :func:`build_safety_banner_text` — returns the bible §5.4 line 216
  ``"[CONFIRM BEFORE EXECUTION]"`` banner string for the FinalPrompt's
  ``<safety_banner>`` tag.
* :func:`build_confirmation_request` — pure builder for
  :class:`ConfirmationRequest` (the at-gate artifact).
* :func:`build_operator_message` — pure builder for the bible §5.4
  lines 220-228 user-facing halt message.
* :func:`record_confirmation` — pure builder for
  :class:`Confirmation` (the OPERATOR-confirms-receipt artifact).
* :class:`Confirmation` / :class:`ConfirmationRequest` — re-exported
  Pydantic models from :mod:`schemas.confirmation`.
* :class:`errors.AwaitingDestructiveConfirmation` — re-exported
  ``PipelineHalt`` subclass; payload carries the serialized
  :class:`ConfirmationRequest`.
"""

from __future__ import annotations

from errors import AwaitingDestructiveConfirmation, RedactionFailed
from schemas.confirmation import Confirmation, ConfirmationRequest
from safety_gate.confirmation import (
    build_confirmation_request,
    build_operator_message,
    build_safety_banner_text,
    record_confirmation,
)
from safety_gate.injection_scanner import InjectionMatch, scan_text
from safety_gate.redactor import (
    assert_no_residual,
    load_user_patterns,
    redact,
)

__all__ = [
    "AwaitingDestructiveConfirmation",
    "Confirmation",
    "ConfirmationRequest",
    "InjectionMatch",
    "RedactionFailed",
    "assert_no_residual",
    "build_confirmation_request",
    "build_operator_message",
    "build_safety_banner_text",
    "load_user_patterns",
    "record_confirmation",
    "redact",
    "scan_text",
]
