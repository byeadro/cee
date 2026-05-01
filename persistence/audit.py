"""Hash-chained audit log infrastructure for ``~/cee/audit/*.log``.

This module is the canonical writer named by bible 12 §11
("Audit log writer: ``~/cee/persistence/audit.py``. Append-only with
hash chain. ``cee audit-verify`` implemented in ``~/cee/cli.py``").

**Phase 1 scope.** Three primitives ship now: scaffold of the four log
files, atomic hash-chained append, and chain integrity verification.
Event-specific writers (security events, role actions, boot steps, CLI
commands) belong to their own roles and ship in Phase 5+ when those
callers exist. The ``cee audit-verify`` CLI command lives in
``~/cee/cli.py`` (task 13). Daily archive rotation is operational, not
foundational, and is also deferred.

**The four logs (bible 12 §5.8, bible 04 §5.1).**

==================  ===============================================
File                Captures
==================  ===============================================
``cli.log``         every CLI command, timestamp, exit code
``roles.log``       every system-role action
``boot.log``        every boot
``security.log``    redactions, confirmations, injection detections,
                    aborts, timeouts (bible 12 §5.8 only — bible 04
                    §5.1 omits this file in its diagram; bible 12
                    is the canonical source for the security log)
==================  ===============================================

**Entry shape (bible 12 §5.8 verbatim).**

.. code-block:: json

    {
      "ts": "<ISO timestamp>",
      "actor": "<role name>",
      "event": "<event name>",
      "run_id": "<run id, if applicable>",
      "details": { ... },
      "prev_hash": "<sha256 of previous entry>",
      "entry_hash": "<sha256 of this entry's content>"
    }

**Hash chain semantics.**

- ``entry_hash = sha256(json.dumps({ts, actor, event, run_id, details,
  prev_hash}, sort_keys=True))``. The hash covers every field *except*
  ``entry_hash`` itself (chicken-and-egg avoidance) and *includes*
  ``prev_hash`` (otherwise an attacker rewrites history by editing
  prev_hash links without invalidating any entry_hash, which would
  defeat bible 12 §5.8's claim that "the hash chain makes tampering
  detectable").
- The first entry in a log uses the genesis hash ``"0" * 64`` for
  ``prev_hash``. Bible is silent on the genesis convention; this is
  standard practice.
- ``json.dumps`` uses ``sort_keys=True`` so the same logical entry
  produces the same hash byte-for-byte regardless of insertion order
  in the source dict.
- SHA-256, hex digest, lowercase. ``hashlib.sha256(...).hexdigest()``
  is lowercase by default.

**Determinism caveat — wall clock.** ``ts`` reads system time
(``datetime.now(timezone.utc)``). This is one of the few legitimate
wall-clock reads in CEE. Bible 03 Rule 6's "time stops at capture"
applies to per-Run *logic* (so a Run replay produces identical
artifacts); it does not apply to *audit timestamps*, which must
reflect real wall-clock time for forensic value.

**Atomicity.** Each append reads the entire log, appends one JSON line,
and rewrites the whole file via :func:`persistence.atomic.atomic_write_text`.
This is O(N) per append in log size — acceptable for an audit log that
rotates daily. It guarantees that a crash mid-write never produces a
partial line: the chain is either extended cleanly or unchanged. A raw
``open(..., "a")`` would risk a torn final line, which would corrupt
the chain by making the last ``entry_hash`` unrecoverable.

**Refuse-to-extend semantics.** If the last line of the log fails to
parse as JSON or is missing ``entry_hash``, :func:`audit_log_append`
raises ``ValueError`` rather than silently starting a new chain. Bible
12 §10.6 recovery ("future entries continue from new chain root") is a
manual operator action, not an automatic decision: the operator
investigates, archives the broken file, then a fresh append starts a
new chain. Refusing here prevents masking tamper.

**Failure mode.** Bible 02 §7.10 → bible 00 Rule 9: substrate-write
failures (filesystem, Obsidian) are non-fatal *at the pipeline level*;
audit failures are no exception. ``OSError`` propagates unswallowed and
the caller (``SAFETY_GATE``, ``PERSISTENCE_WRITER``, ``cli.py``, etc.)
decides whether to log-and-continue or surface.

**Path containment.** Both :func:`audit_log_append` and
:func:`verify_audit_chain` reject any ``log_path`` that is not under
:data:`paths.AUDIT_DIR`. This is defence-in-depth: a programming bug
that hands the writer an arbitrary path (e.g. a Run artifact path)
cannot accidentally clobber non-audit files with hash-chained content.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import paths
from persistence.atomic import atomic_write_text

# ─── Module-level constants ─────────────────────────────────────────────

#: Genesis ``prev_hash`` for the first entry in any log. Bible 12 §5.8
#: is silent on the convention; ``"0" * 64`` is standard practice
#: (matches the SHA-256 hex-digest width and is unambiguously a sentinel).
GENESIS_HASH: str = "0" * 64

#: Field ordering used to construct each entry. The hashed payload is
#: every field below *except* ``entry_hash``. Listed here so a reader
#: can confirm against bible 12 §5.8 at a glance.
_ENTRY_FIELDS: tuple[str, ...] = (
    "ts",
    "actor",
    "event",
    "run_id",
    "details",
    "prev_hash",
    "entry_hash",
)

#: The four canonical log files per bible 12 §5.8 + bible 04 §5.1.
#: Resolved at call time via :func:`_canonical_log_paths` so test
#: monkeypatching of ``paths.AUDIT_*`` works correctly.

# ─── Internal helpers ───────────────────────────────────────────────────


def _canonical_log_paths() -> tuple[Path, ...]:
    """Return the four canonical audit-log paths in declaration order.

    Read from :mod:`paths` at call time so test fixtures that monkeypatch
    ``paths.AUDIT_*`` are honoured. Order: cli, roles, boot, security
    (bible 12 §5.8 declaration order).
    """
    return (
        paths.AUDIT_CLI_LOG,
        paths.AUDIT_ROLES_LOG,
        paths.AUDIT_BOOT_LOG,
        paths.AUDIT_SECURITY_LOG,
    )


def _assert_under_audit_dir(log_path: Path) -> None:
    """Raise ``ValueError`` if ``log_path`` is not inside ``AUDIT_DIR``.

    Defence-in-depth against a buggy caller passing an arbitrary path.
    Comparison uses ``Path.is_relative_to`` (Python 3.9+) on the
    *resolved* parent, so ``..`` traversals don't slip past. The path
    itself is not required to exist — verification of a missing log
    is a legal call.
    """
    audit_root = paths.AUDIT_DIR.resolve()
    # Resolve the path's parent (which exists once scaffold has run, or
    # will be created by atomic_write_text). For a not-yet-existing
    # leaf, ``log_path.parent`` is the canonical anchor.
    candidate = log_path.resolve() if log_path.exists() else (
        log_path.parent.resolve() / log_path.name
    )
    if not candidate.is_relative_to(audit_root):
        raise ValueError(
            f"log_path {log_path!s} is not under AUDIT_DIR "
            f"{audit_root!s}; refusing to write hash-chained content "
            "outside the canonical audit area"
        )


def _hash_entry_payload(entry: dict[str, Any]) -> str:
    """Compute ``entry_hash`` over every field except ``entry_hash``.

    ``json.dumps`` with ``sort_keys=True`` makes the byte serialisation
    deterministic so identical logical inputs produce identical hashes.
    """
    payload = {k: v for k, v in entry.items() if k != "entry_hash"}
    serialised = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def _read_lines(log_path: Path) -> list[str]:
    """Return the non-empty lines of ``log_path``, or ``[]`` if missing.

    Trailing blank lines from the POSIX final-newline convention are
    discarded. Other blank lines (within the body) would indicate file
    corruption and are also discarded — verification will surface the
    chain break separately.
    """
    if not log_path.exists():
        return []
    raw = log_path.read_text(encoding="utf-8")
    return [line for line in raw.split("\n") if line]


def _parse_last_prev_hash(log_path: Path) -> str:
    """Return ``prev_hash`` for the next-to-be-appended entry.

    Empty/missing log → :data:`GENESIS_HASH`. Otherwise, parse the last
    JSON line and return its ``entry_hash``. Raises ``ValueError`` if
    the last line is malformed or missing ``entry_hash`` — bible 12
    §10.6 recovery is a manual operator action; we refuse to silently
    bridge over a broken chain.
    """
    lines = _read_lines(log_path)
    if not lines:
        return GENESIS_HASH

    last_line = lines[-1]
    try:
        last_entry = json.loads(last_line)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"audit log {log_path!s} has a malformed final entry — "
            f"chain is broken; refusing to extend (bible 12 §10.6). "
            f"underlying error: {e}"
        ) from e

    if not isinstance(last_entry, dict) or "entry_hash" not in last_entry:
        raise ValueError(
            f"audit log {log_path!s} final entry is missing entry_hash — "
            "chain is broken; refusing to extend (bible 12 §10.6)"
        )

    last_hash = last_entry["entry_hash"]
    if not isinstance(last_hash, str):
        raise ValueError(
            f"audit log {log_path!s} final entry has non-string "
            "entry_hash — chain is broken; refusing to extend"
        )
    return last_hash


# ─── Public API ─────────────────────────────────────────────────────────


def scaffold_audit_logs() -> dict[str, int]:
    """Touch the four audit log files at their canonical paths if missing.

    Per bible 12 §5.8 + bible 04 §5.1, the four logs are ``cli.log``,
    ``roles.log``, ``boot.log``, ``security.log``. Each is JSONL —
    one JSON entry per line. An empty file means an empty chain;
    the first :func:`audit_log_append` to such a file uses
    :data:`GENESIS_HASH` for ``prev_hash``.

    Returns
    -------
    dict
        ``{"files_created": int}`` — counts only files that did *not*
        already exist. Fresh scaffold: ``{"files_created": 4}``.
        Re-run on a scaffolded tree: ``{"files_created": 0}``.
        Pre-existing files are never modified.

    Raises
    ------
    OSError
        Filesystem failures propagate. Per bible 02 §7.10 → bible 00
        Rule 9, audit-write failures are non-fatal at the *pipeline*
        level; the caller decides whether to log-and-continue.
    """
    paths.ensure_dir(paths.AUDIT_DIR)
    paths.ensure_dir(paths.AUDIT_ARCHIVE_DIR)

    files_created = 0
    for log_path in _canonical_log_paths():
        if not log_path.exists():
            atomic_write_text(log_path, "")
            files_created += 1
    return {"files_created": files_created}


def audit_log_append(
    log_path: Path,
    actor: str,
    event: str,
    details: dict[str, Any],
    run_id: str | None = None,
) -> str:
    """Append a hash-chained entry to ``log_path`` per bible 12 §5.8.

    Reads the last line of ``log_path`` to extract ``prev_hash`` (or
    uses :data:`GENESIS_HASH` if the log is empty/missing), constructs
    the entry per bible 12 §5.8, computes ``entry_hash`` over all other
    fields with ``sort_keys=True`` for determinism, and rewrites the
    whole file atomically.

    Parameters
    ----------
    log_path
        Target log file. Must be inside :data:`paths.AUDIT_DIR`.
    actor
        The role name responsible for the event (typically a value
        from :class:`roles.RoleEnum`, but this function does not
        enforce that — callers in Phase 5+ will supply role-typed
        wrappers).
    event
        Short event name (e.g. ``"redaction_applied"``,
        ``"boot_complete"``).
    details
        Arbitrary JSON-serialisable dict. Caller defines the shape.
    run_id
        Run ID if the event is associated with a Run; ``None`` for
        events without one (boot steps, ad-hoc CLI commands).

    Returns
    -------
    str
        The ``entry_hash`` of the newly-appended entry.

    Raises
    ------
    ValueError
        If ``log_path`` is not under :data:`paths.AUDIT_DIR`, or if
        the existing log's last line cannot be parsed / is missing
        ``entry_hash`` (chain is broken; refusing to extend per
        bible 12 §10.6).
    OSError
        Filesystem failures propagate. Per bible 02 §7.10 → bible 00
        Rule 9.

    Notes
    -----
    ``ts`` is the current wall-clock time as ISO-8601 with timezone
    info (UTC). Bible 03 Rule 6's "time stops at capture" governs
    per-Run logic; audit timestamps must reflect real wall-clock
    time for forensic value.
    """
    _assert_under_audit_dir(log_path)

    prev_hash = _parse_last_prev_hash(log_path)
    ts = datetime.now(timezone.utc).isoformat()

    # Build the entry without entry_hash, hash it, then attach.
    entry: dict[str, Any] = {
        "ts": ts,
        "actor": actor,
        "event": event,
        "run_id": run_id,
        "details": details,
        "prev_hash": prev_hash,
    }
    entry_hash = _hash_entry_payload(entry)
    entry["entry_hash"] = entry_hash

    # Read existing content, append the new line, atomically rewrite.
    # atomic_write_text guarantees no torn writes; a crash leaves the
    # log unchanged from before the call.
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    if existing and not existing.endswith("\n"):
        # POSIX convention: lines end with newline. A pre-existing log
        # that's missing the trailing newline is a sign of partial-write
        # damage, but we recover by adding the separator rather than
        # corrupting further.
        existing = existing + "\n"
    new_line = json.dumps(entry, sort_keys=True) + "\n"
    atomic_write_text(log_path, existing + new_line)

    return entry_hash


def verify_audit_chain(log_path: Path) -> tuple[bool, list[dict[str, Any]]]:
    """Verify the hash chain integrity of ``log_path`` per bible 12 §10.6.

    Walks the log line by line. For each entry:

    1. Recompute ``entry_hash`` from the other fields and compare to
       the stored ``entry_hash`` — catches tampering with any field
       (including ``prev_hash``, since it's part of the hashed payload).
    2. Compare the entry's ``prev_hash`` to the previous entry's
       ``entry_hash`` (or :data:`GENESIS_HASH` for the first entry) —
       catches insertion, deletion, or reordering of entries.

    Returns
    -------
    tuple
        ``(is_valid: bool, broken_entries: list[dict])``. When
        ``is_valid`` is ``True``, ``broken_entries`` is empty.
        Otherwise each element of ``broken_entries`` has shape
        ``{"line_number": int (1-based), "reason": str,
        "entry": dict | str}`` — ``entry`` is the parsed dict if
        parsing succeeded, otherwise the raw line.

    Raises
    ------
    ValueError
        If ``log_path`` is not under :data:`paths.AUDIT_DIR`.
    json.JSONDecodeError
        If a line is not valid JSON. (The bible §10.6 contract is
        that the verifier *detects* corruption; for a malformed
        entry, the JSONDecodeError surfaces immediately so the
        operator sees the structural break with line context. A
        malformed line is unambiguously corruption — there is no
        "valid but unhashable" interpretation.)
    """
    _assert_under_audit_dir(log_path)

    lines = _read_lines(log_path)
    broken: list[dict[str, Any]] = []
    expected_prev_hash = GENESIS_HASH

    for idx, line in enumerate(lines, start=1):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # Re-raise with context so the operator sees the line.
            raise

        if not isinstance(entry, dict):
            broken.append({
                "line_number": idx,
                "reason": "entry is not a JSON object",
                "entry": entry,
            })
            # We can't continue the chain check past a non-object entry.
            return False, broken

        if "entry_hash" not in entry:
            broken.append({
                "line_number": idx,
                "reason": "entry missing entry_hash field",
                "entry": entry,
            })
            return False, broken

        stored_hash = entry["entry_hash"]
        recomputed = _hash_entry_payload(entry)
        if recomputed != stored_hash:
            broken.append({
                "line_number": idx,
                "reason": (
                    "entry_hash mismatch (entry was tampered or hash is "
                    f"corrupt): stored={stored_hash}, recomputed={recomputed}"
                ),
                "entry": entry,
            })

        actual_prev = entry.get("prev_hash")
        if actual_prev != expected_prev_hash:
            broken.append({
                "line_number": idx,
                "reason": (
                    "prev_hash does not match previous entry_hash "
                    f"(expected={expected_prev_hash}, actual={actual_prev})"
                ),
                "entry": entry,
            })

        # Advance the chain expectation using the *stored* hash, not the
        # recomputed one — verification reports both kinds of break, and
        # using the stored hash keeps subsequent comparisons faithful to
        # the on-disk state.
        expected_prev_hash = stored_hash

    return (len(broken) == 0), broken
