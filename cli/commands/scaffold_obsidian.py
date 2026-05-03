"""``cee scaffold-obsidian`` — idempotent Obsidian vault scaffolder.

Phase 3 task 11. Operator-facing standalone verb that creates the
``~/SecondBrain/cee/`` vault scaffold per bible 13 §5.1 (7 directories
+ 6 stub files = 13 paths). Idempotent — re-runnable on partial or
complete scaffolds without modifying any pre-existing files.

Bible canonical surface:

* **Bible 13 §5.1** — canonical vault layout. The 13-path manifest
  enumerated by :func:`cli.commands.verify._obsidian_required`
  (consumed here verbatim) and materialised by
  :func:`persistence.scaffold_obsidian` is bible-grounded in this
  section.
* **Bible 13 §EC1** — names the dual-entry-point pattern: "``cee
  init`` materialises the Obsidian vault scaffold". Phase 3 task 11
  ships the standalone verb so the OPERATOR can re-scaffold without
  rerunning full ``cee init`` (avoids re-touching ``redact_list``,
  ``config.toml``, etc.).
* **Bible 13 §EC3** — manual-edit preservation. Existing files are
  OPERATOR property and are never modified by setup. Implemented
  by :func:`persistence.obsidian_writer._idempotent_write`'s
  create-only semantics; T11 inherits this guarantee verbatim by
  wrapping the helper.
* **Bible 20 §5.3** — Phase 3 CLI surface lists ``cee scaffold-
  obsidian`` as a Phase 3 output, alongside ``cee verify --obsidian``
  (T9, shipped) and ``cee audit-verify`` (T10, shipped).

Scope (Path A per AB sign-off):

* **Wrap, don't reimplement.** :func:`persistence.scaffold_obsidian`
  (Phase 1 surface) is the sole filesystem-write path. T11 calls
  it once inside try/except OSError, then renders per-path state
  via an existence-snapshot pattern. T11 does NOT call
  :func:`pathlib.Path.mkdir` / :func:`pathlib.Path.write_text` /
  :func:`open` directly.
* **No audit emission.** Unlike :mod:`cli.commands.init` (which
  appends a ``cee_init_complete`` event to ``boot.log``), T11 is
  silent on audit. Audit emission for vault scaffolding belongs
  inside :func:`persistence.scaffold_obsidian` (correct layer)
  rather than the CLI wrapper; that migration is deferred to a
  Phase 5+ infrastructure pass.
* **No new error class.** :func:`persistence.scaffold_obsidian`
  raises :class:`OSError` directly on filesystem failure
  (obsidian_writer.py:203-209); T11 catches and surfaces the
  ``errno`` + ``strerror`` in the failure render. A typed
  ``ObsidianScaffoldError`` is deferred to the Phase 5+ error-class
  hierarchy refactor.

OSError short-circuit honesty:

:func:`persistence.scaffold_obsidian` walks its 13-path manifest
sequentially via :func:`paths.ensure_dir` + :func:`_idempotent_write`.
On the first :class:`OSError` (permission denied, disk full, …) the
helper aborts — subsequent paths in the manifest are NOT attempted.
T11's existence-snapshot then accurately reflects this: paths the
helper got to before the abort show as ``+`` (created), paths it
didn't get to show as ``✗`` (FAILED). The render is honest about
actual filesystem state, not aspirational about what *should* have
been created.

Output contract:

* **Stdout** — ``CEE Obsidian Vault Scaffold`` header, per-path
  ``+`` (created) / ``✓`` (already present) / ``✗`` (FAILED) line
  with kind annotation, ``Summary: K created, M already present,
  N failed.`` line, ``PASSED.`` or ``FAILED:`` banner.
* **Stderr** — silent on success. On OSError catch: one
  ``OBSIDIAN-SCAFFOLD HALT [partial_failure]`` line, one
  ``Cause: OSError <errno> <strerror>`` line, one ``Hint: …`` line
  pulled from :data:`_SCAFFOLD_OBSIDIAN_HINTS`.

Helper imports:

The 13-path manifest (:func:`_obsidian_required`) and short-path
renderer (:func:`_shorten_path`) live in :mod:`cli.commands.verify`
as underscore-prefixed module-private functions. Importing them
across sibling modules in the same ``cli/commands/`` package is the
same soft Python convention violation made in T10's
:mod:`cli.commands.audit_verify`. The inverse — duplicating the
13-path manifest in T11 — would create drift risk between the
verifier (T9) and the scaffolder (T11), where any future change
to bible 13 §5.1 would have to land in two places. Locking T11's
manifest to T9's source makes drift structurally impossible.

# TODO #44 / bible 19 §5.6: long-term home for
# _SCAFFOLD_OBSIDIAN_HINTS table. Co-deferred with the four
# existing hint tables (_BOOT_HALT_HINTS, _BIBLE_DRIFT_HINTS,
# _OBSIDIAN_VERIFY_HINTS, _AUDIT_VERIFY_HINTS) — all five should
# migrate into a bible-grounded loader once bible 19 §5.6 ships
# its structured message catalog.

# TODO #45 / cli/commands refactor: promote _shorten_path and
# _obsidian_required from cli/commands/verify.py into a shared
# cli/commands/_render.py + cli/commands/_manifest.py module pair.
# T11 is the third consumer of cross-package underscore-private
# imports (after T10's audit_verify); a third consumer is the
# canonical justification threshold for the refactor.

Exit code semantics (matching :mod:`cli.main`'s contract):

* ``0`` — every path in the 13-path manifest exists post-call,
  whether genuinely created in this run or already-present from a
  prior scaffold.
* ``1`` — at least one manifest path failed to be created (did not
  exist before AND does not exist after).
* ``2`` — reserved for the outer :func:`cli.main.main` catch —
  non-CEE exceptions only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cli.commands.verify import _obsidian_required, _shorten_path
from persistence import scaffold_obsidian


# ─── Hint table ─────────────────────────────────────────────────────────


# Remediation hints for ``cee scaffold-obsidian`` failures. One-entry
# table — most failure modes are filesystem-permission-related and the
# OSError surface (errno + strerror) is self-explanatory; a second
# permission_denied-specific entry would be redundant.
#
# Mirrors the inline-hint precedent established by:
# - T9 of Phase 2 :data:`cli.commands.verify._BOOT_HALT_HINTS`
# - T10 of Phase 2 :data:`cli.commands.verify._BIBLE_DRIFT_HINTS`
# - T9 of Phase 3 :data:`cli.commands.verify._OBSIDIAN_VERIFY_HINTS`
# - T10 of Phase 3 :data:`cli.commands.audit_verify._AUDIT_VERIFY_HINTS`
#
# Long-term home is bible 19 §5.6 alongside the four predecessors. See
# # TODO #44 above.
_SCAFFOLD_OBSIDIAN_HINTS: dict[str, str] = {
    "partial_failure":
        "scaffold did not complete — investigate filesystem "
        "permissions on the vault path; OPERATOR re-runs `cee "
        "scaffold-obsidian` after fixing (idempotent)",
}


# ─── Public API ─────────────────────────────────────────────────────────


def cmd_scaffold_obsidian(args: argparse.Namespace) -> int:  # noqa: ARG001 — argparse contract
    """Run ``cee scaffold-obsidian``.

    Wraps :func:`persistence.scaffold_obsidian` with operator-facing
    plumbing: snapshots existence-before per path, calls the helper
    once inside try/except OSError, then renders per-path post-state
    by inspecting actual filesystem state.

    The 13-path manifest is consumed verbatim from T9's
    :func:`cli.commands.verify._obsidian_required` so the verifier
    and scaffolder share one source of truth — drift between
    ``cee verify --obsidian`` and ``cee scaffold-obsidian`` is
    structurally impossible.

    **Idempotency.** Inherited from
    :func:`persistence.obsidian_writer._idempotent_write` (create-
    only semantics; pre-existing files are never modified per bible
    13 §EC3). Re-running this verb on a fully-scaffolded vault
    yields ``Summary: 0 created, 13 already present, 0 failed.``
    + ``PASSED.`` + exit 0.

    **OSError handling.** On :class:`OSError` from the helper
    (permission denied, disk full, etc.): caught, error message
    captured, rendering proceeds via the post-call snapshot. The
    render honestly reflects which paths got created before the
    abort and which didn't.

    Returns
    -------
    int
        ``0`` if every manifest path exists post-call (any mix of
        created + already-present). ``1`` if at least one path
        failed to be created. Exit code ``2`` is reserved for the
        outer :func:`cli.main.main` catch — non-CEE exceptions only.
    """
    print("CEE Obsidian Vault Scaffold")
    print()

    # The 13-path manifest. Mirrors T9's _obsidian_required exactly
    # so verifier + scaffolder enumerate the same closed set.
    manifest = _obsidian_required()

    # Snapshot existence-before so we can render per-path "created"
    # vs "already present" by comparing before/after state.
    before_existed: dict[Path, bool] = {p: p.exists() for p, _ in manifest}

    # Wrap the canonical Phase 1 helper. Single call. Any per-path
    # filesystem failure raises OSError and aborts the helper's
    # internal walk; the post-call snapshot accurately reflects
    # actual state regardless of where the abort fired.
    oserror_msg: str | None = None
    try:
        scaffold_obsidian()
    except OSError as e:
        oserror_msg = f"OSError: {e.errno} {e.strerror}"

    # Per-path render walks the manifest in declaration order so the
    # output sequence is stable across runs.
    print("Obsidian vault (~/SecondBrain/cee/):")
    created = 0
    already_present = 0
    failed = 0
    for path, kind in manifest:
        if before_existed[path]:
            print(
                f"  ✓ {_shorten_path(path)}  ({kind}, already present)"
            )
            already_present += 1
        elif path.exists():
            print(f"  + {_shorten_path(path)}  ({kind}, created)")
            created += 1
        else:
            print(f"  ✗ {_shorten_path(path)}  ({kind}, FAILED)")
            failed += 1
    print()

    print(
        f"Summary: {created} created, "
        f"{already_present} already present, "
        f"{failed} failed."
    )
    if failed == 0:
        print("PASSED.")
        return 0

    print("FAILED: see per-path failures above.")
    sys.stderr.write("OBSIDIAN-SCAFFOLD HALT [partial_failure]\n")
    if oserror_msg is not None:
        sys.stderr.write(f"Cause: {oserror_msg}\n")
    sys.stderr.write(
        f"Hint: {_SCAFFOLD_OBSIDIAN_HINTS['partial_failure']}\n"
    )
    return 1
