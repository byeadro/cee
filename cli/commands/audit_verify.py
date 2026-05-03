"""``cee audit-verify`` — hash-chain integrity verification for audit logs.

Phase 3 task 10. Wraps :func:`persistence.audit.verify_audit_chain`
(Phase 1 surface) with operator-facing CLI plumbing: walks the four
canonical audit logs per bible 12 §5.8, aggregates per-log results,
renders a report mirroring the Phase 2/3 ``cee verify`` precedent,
and emits remediation hints to stderr keyed by failure category.

Bible canonical surface:

* **Bible 12 §10.6** — ``Audit log corruption`` failure mode.
  *Failure:* "log file is truncated or modified outside CEE."
  *Detection:* "hash chain verification."
  *Recovery:* "log marked as compromised; future entries continue
  from new chain root; OPERATOR investigates."
* **Bible 12 §5.8** — canonical audit log structure: four files
  (``cli.log``, ``roles.log``, ``boot.log``, ``security.log``),
  JSONL, hash-chained per-entry. The closing line of §5.8 names
  this exact verb verbatim: "A ``cee audit-verify`` command walks
  the log and checks the chain."
* **Bible 12 §11** — "Audit log writer: ``~/cee/persistence/audit.py``.
  Append-only with hash chain. ``cee audit-verify`` implemented in
  ``~/cee/cli.py``." Phase 3 splits the CLI into per-verb modules
  under ``cli/commands/`` (the Phase 1+ structural choice); this is
  the per-verb home for ``audit-verify``.
* **Bible 20 §5.3** — Phase 3 CLI surface lists ``cee audit-verify``
  as a Phase 3 output, alongside ``cee verify --obsidian`` (T9) and
  ``cee scaffold-obsidian`` (T11).

Scope (Path A per AB sign-off):

* **Pure read.** No filesystem writes, no archive rotation, no
  remediation. Bible 12 §10.6 recovery is a *manual* OPERATOR
  action; this verb only detects.
* **Four canonical logs only.** ``cli.log`` / ``roles.log`` /
  ``boot.log`` / ``security.log`` per bible 12 §5.8. No glob walk
  of ``paths.AUDIT_DIR``; per-Run audit logs and other ``*.log``
  files are not bible-defined and are out of scope.
* **No flags, no positional args.** Canonical paths only via
  :mod:`paths` constants.

Output contract:

* **Stdout** — ``CEE Audit Log Verification`` header, per-log
  ``✓``/``✗`` line with entry count or broken-entry count, indented
  per-broken-entry ``line N: <reason>`` detail, ``Summary: K of 4
  logs valid.`` line, ``PASSED.`` or ``FAILED:`` banner.
* **Stderr** — silent on success. On failure, one ``AUDIT-VERIFY
  HALT [<category>]`` + ``Hint:`` pair per failure category present
  in this run (audit_dir_missing / chain_broken / malformed_jsonl).
  Matches the per-category emission pattern of T10's
  :data:`cli.commands.verify._BIBLE_DRIFT_HINTS` precedent.

Helpers reuse:

The render helpers (:func:`_shorten_path`, :func:`_render_item`,
:func:`_is_ok`) live in :mod:`cli.commands.verify` as
underscore-prefixed module-private functions. Importing them
across sibling modules in the same ``cli/commands/`` package is a
soft Python convention violation but the inverse — duplicating ~30
lines of stable Phase 1 helper code — would create drift risk
(any future change to ``_shorten_path``'s tilde-rendering rule
would have to land in two places). The canonical long-term fix is
to promote them into a shared ``cli/commands/_render.py`` module;
that refactor is deferred to a Phase 5+ cleanup pass to keep T10's
diff scoped per AB-locked decisions.

# TODO #44 / bible 19 §5.6: long-term home for _AUDIT_VERIFY_HINTS
# table. Co-deferred with #24 (_BOOT_HALT_HINTS), #27
# (_BIBLE_DRIFT_HINTS), and the implicit T9 _OBSIDIAN_VERIFY_HINTS
# trajectory — all four hint tables should migrate into a
# bible-grounded loader once bible 19 §5.6 ships its structured
# message catalog.

# TODO #45 / cli/commands refactor: promote _shorten_path /
# _render_item / _is_ok from verify.py to cli/commands/_render.py
# once a third consumer materialises (T10 is the second; the third
# would justify the refactor).

Exit code semantics (matching :mod:`cli.main`'s contract):

* ``0`` — every canonical log passes hash-chain verification.
* ``1`` — at least one log has a chain integrity failure OR the
  audit dir itself is missing OR a malformed JSONL line raised
  :class:`json.JSONDecodeError`.
* ``2`` — reserved for unexpected exceptions caught by
  :func:`cli.main.main`'s outer ``except Exception``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import paths
from cli.commands.verify import _is_ok, _render_item, _shorten_path  # noqa: F401 — _is_ok / _render_item kept available for future per-log layout extension; only _shorten_path is used today
from persistence.audit import verify_audit_chain


# ─── Canonical log manifest ────────────────────────────────────────────


def _AUDIT_LOG_PATHS() -> tuple[Path, ...]:
    """Return the four canonical audit log paths in declaration order.

    Order: ``cli`` → ``roles`` → ``boot`` → ``security``. Matches
    :func:`persistence.audit._canonical_log_paths` ordering verbatim
    so the verifier renders logs in the same sequence the writer
    enumerates them. Resolved at call time so test monkeypatching of
    ``paths.AUDIT_*`` constants is honoured.

    Per AB-locked decision (T10 design): enumerated locally rather
    than imported from :func:`audit._canonical_log_paths` (private
    API — same-module-private helpers should not be reached across
    package boundaries). The 4-tuple is bible-canonical (bible 12
    §5.8) and stable; duplication risk is bounded.
    """
    return (
        paths.AUDIT_CLI_LOG,
        paths.AUDIT_ROLES_LOG,
        paths.AUDIT_BOOT_LOG,
        paths.AUDIT_SECURITY_LOG,
    )


# ─── Hint table ─────────────────────────────────────────────────────────


# Remediation hints for ``cee audit-verify`` failures. Three-entry
# table mirroring the inline-hint precedent established by T9's
# :data:`cli.commands.verify._OBSIDIAN_VERIFY_HINTS`, T9 of Phase 2's
# :data:`cli.commands.verify._BOOT_HALT_HINTS`, and T10 of Phase 2's
# :data:`cli.commands.verify._BIBLE_DRIFT_HINTS`.
#
# Three categories rather than two (T9 had ``vault_missing`` +
# ``scaffold_incomplete``) because the audit failure space adds a
# distinct *malformed-JSONL* category — that's structural file
# corruption (an OPERATOR opened the log in an editor and saved
# garbage), distinct from *chain_broken* (a single field was tampered
# with, leaving the JSON intact). Bible 12 §10.6 names both as
# detectable forms of "log file is truncated or modified outside CEE";
# splitting them lets the OPERATOR see which class fired without
# scanning the per-broken-entry detail lines.
#
# Long-term home for these hints is bible 19 §5.6 alongside the three
# existing hint tables (downstream candidate alongside #24 + #27 +
# the implicit T9 deferral). See # TODO #44 above.
_AUDIT_VERIFY_HINTS: dict[str, str] = {
    "audit_dir_missing":
        "run `cee init` to scaffold ~/cee/audit/ + the four canonical "
        "log files (bible 12 §5.8)",
    "chain_broken":
        "audit log chain integrity has failed — investigate which "
        "entries diverge (bible 12 §10.6 recovery: archive the "
        "compromised log; future entries will start a new chain)",
    "malformed_jsonl":
        "audit log contains a non-JSON line — file was edited outside "
        "CEE; archive and investigate per bible 12 §10.6",
}


# ─── Internal helpers ───────────────────────────────────────────────────


def _verify_one_log(log_path: Path) -> tuple[bool, list[dict]]:
    """Wrap :func:`verify_audit_chain` with :class:`json.JSONDecodeError` catch.

    :func:`verify_audit_chain` raises :class:`json.JSONDecodeError` on
    a malformed JSONL line rather than returning it as a broken entry
    (audit.py:391-396 documents this as deliberate — "a malformed
    line is unambiguously corruption — there is no 'valid but
    unhashable' interpretation"). Without this wrapper the exception
    would propagate to :func:`cli.main.main`'s outer ``except
    Exception`` and produce an exit-code-2 ``UNEXPECTED ERROR``
    instead of the intended exit-code-1 chain-failure.

    The synthesized broken-entry record contains ONLY ``line_number``
    and ``reason`` — deliberately omitting any surrounding-bytes
    context window per AB-locked decision (avoid leaking audit log
    bytes through stdout, since the broken-entry ``reason`` is rendered
    on the operator's terminal).

    Returns
    -------
    tuple
        ``(is_valid: bool, broken: list[dict])``. Same shape as
        :func:`verify_audit_chain`. On JSONDecodeError catch:
        ``(False, [{"line_number": e.lineno, "reason": "malformed
        JSONL: <e.msg>"}])``.
    """
    try:
        return verify_audit_chain(log_path)
    except json.JSONDecodeError as e:
        return False, [{
            "line_number": e.lineno,
            "reason": f"malformed JSONL: {e.msg}",
        }]


def _count_entries(log_path: Path) -> int:
    """Count non-empty lines in an audit log file.

    Used only on logs that passed verification (where every non-empty
    line is a valid JSON entry — :func:`verify_audit_chain` rejects
    any other shape). For broken logs, the per-broken-entry detail
    block carries the diagnostic information; a separate entry count
    would be misleading.

    Mirrors :func:`persistence.audit._read_lines` behaviour: missing
    file → 0 entries (treated as empty chain per Phase 1 semantics).
    """
    if not log_path.exists():
        return 0
    raw = log_path.read_text(encoding="utf-8")
    return sum(1 for line in raw.split("\n") if line)


def _is_chain_failure(reason: str) -> bool:
    """Classify a broken-entry reason as chain-integrity vs malformed-JSONL.

    The two categories key into different :data:`_AUDIT_VERIFY_HINTS`
    entries. ``malformed JSONL:`` is the prefix synthesized by
    :func:`_verify_one_log` on :class:`json.JSONDecodeError` catch;
    every other reason originates from :func:`verify_audit_chain`'s
    own broken-entry construction (entry_hash mismatch, prev_hash
    linkage break, missing entry_hash field, non-object entry).
    """
    return not reason.startswith("malformed JSONL:")


# ─── Public API ─────────────────────────────────────────────────────────


def cmd_audit_verify(args: argparse.Namespace) -> int:  # noqa: ARG001 — argparse contract
    """Run ``cee audit-verify``.

    Walks the four canonical audit logs (bible 12 §5.8), invokes
    :func:`_verify_one_log` on each, aggregates results, renders the
    operator report, and emits per-category remediation hints to
    stderr.

    **Halt-on-audit-dir-missing.** When :data:`paths.AUDIT_DIR` itself
    is missing (OPERATOR deleted ``~/cee/audit/`` or never ran
    ``cee init``), short-circuit before walking the four children —
    rendering four spurious "valid empty chain" lines under a missing
    parent would mask the real failure (no audit substrate exists).
    Mirrors T9's halt-on-vault-missing pattern in
    :func:`cli.commands.verify._verify_obsidian` shipped at commit
    ``3fdacb5``.

    **Walk continuation.** Per AB-locked decision: walk continues
    through all four logs even if early ones fail. Operator gets the
    full picture of which logs are intact vs broken in one report,
    rather than having to re-run after fixing the first failure.

    **Hint emission.** Per failure category present in this run, emit
    one ``AUDIT-VERIFY HALT [<category>]`` + ``Hint:`` pair to
    stderr. Categories are ``audit_dir_missing`` (mutually exclusive
    with the other two — short-circuits) plus ``chain_broken`` and
    ``malformed_jsonl`` which can co-occur.

    Returns
    -------
    int
        ``0`` if every canonical log passes verification.
        ``1`` if any log has a chain integrity failure, or the audit
        dir is missing, or a malformed JSONL line was caught.
        Exit code ``2`` is reserved for the outer
        :func:`cli.main.main` catch — non-CEE exceptions only.
    """
    print("CEE Audit Log Verification")
    print()

    # Halt-on-audit-dir-missing: short-circuit before walking children
    # so the OPERATOR sees one focused line instead of four spurious
    # "valid empty chain" reports under a missing parent dir.
    if not paths.AUDIT_DIR.exists():
        print(
            f"✗ {_shorten_path(paths.AUDIT_DIR)}  "
            "MISSING (directory) — audit log directory absent; "
            "scaffold required before any further checks."
        )
        print()
        print("FAILED: Audit log directory missing.")
        sys.stderr.write("AUDIT-VERIFY HALT [audit_dir_missing]\n")
        sys.stderr.write(
            f"Hint: {_AUDIT_VERIFY_HINTS['audit_dir_missing']}\n"
        )
        return 1

    print("Audit logs (~/cee/audit/):")

    valid_count = 0
    total = 0
    chain_broken_present = False
    malformed_jsonl_present = False

    for log_path in _AUDIT_LOG_PATHS():
        total += 1
        is_valid, broken = _verify_one_log(log_path)
        if is_valid:
            entry_count = _count_entries(log_path)
            print(
                f"  ✓ {_shorten_path(log_path)}  "
                f"(chain valid, {entry_count} entries)"
            )
            valid_count += 1
        else:
            print(
                f"  ✗ {_shorten_path(log_path)}  "
                f"BROKEN ({len(broken)} broken entries)"
            )
            for entry in broken:
                # Per AB-locked: render only line_number + reason.
                # No surrounding bytes / entry payload to avoid leaking
                # audit log content through the operator's terminal.
                print(f"    line {entry['line_number']}: {entry['reason']}")
                if _is_chain_failure(entry["reason"]):
                    chain_broken_present = True
                else:
                    malformed_jsonl_present = True

    print()
    invalid = total - valid_count
    print(f"Summary: {valid_count} of {total} logs valid.", end="")
    if invalid == 0:
        print()
        print("PASSED.")
        return 0
    print(f" {invalid} chain integrity failure(s).")
    print("FAILED: see chain integrity failures above.")

    # Per-category hint emission. Both can co-occur in one run; emit in
    # _AUDIT_VERIFY_HINTS declaration order so the operator sees a
    # stable rendering across runs.
    if chain_broken_present:
        sys.stderr.write("AUDIT-VERIFY HALT [chain_broken]\n")
        sys.stderr.write(f"Hint: {_AUDIT_VERIFY_HINTS['chain_broken']}\n")
    if malformed_jsonl_present:
        sys.stderr.write("AUDIT-VERIFY HALT [malformed_jsonl]\n")
        sys.stderr.write(
            f"Hint: {_AUDIT_VERIFY_HINTS['malformed_jsonl']}\n"
        )

    return 1
