"""CEE safety gate — redaction, injection scanning, destructive-action gate.

Per bible 12 §5 (the Detailed Workflow for the Security System), the
safety gate has three responsibilities:

* **Redaction** (§5.1, §5.2, §5.3) — strip sensitive content from
  every artifact written to filesystem, Obsidian, or Notion. Phase 3
  task T6 ships :func:`redact`, :func:`load_user_patterns`, and
  :func:`assert_no_residual` — the pure-transform layer, plus a
  caller-invoked residual scanner.
* **Injection scanning** (§5.5) — Phase 3 task T7. Detects
  prompt-injection patterns in ``RawInput`` before the interpreter
  runs.
* **Destructive-action gate** (§5.4) — Phase 3 task T8. Halts the
  pipeline before destructive Run completion until the OPERATOR
  confirms via ``cee confirm <run_id>``.

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
"""

from __future__ import annotations

from errors import RedactionFailed
from safety_gate.redactor import (
    assert_no_residual,
    load_user_patterns,
    redact,
)

__all__ = [
    "RedactionFailed",
    "assert_no_residual",
    "load_user_patterns",
    "redact",
]
