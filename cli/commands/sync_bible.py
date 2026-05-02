"""``cee sync-bible`` — manual CLI dispatcher for bible sync.

Phase 2 task 7. Wires :func:`boot.bible_sync.sync` into the ``cee``
CLI as the ``sync-bible`` subcommand. The orchestration layer ships
in T6; this module is the operator-facing surface.

Bible canonical surface (no flags, no args):

* **Bible 00 §11** — "**CLI surface.** ``cee run "<input>"``,
  ``cee sync-bible``, ..." — listed verbatim, no flags.
* **Bible 04 §5.6 "Triggered by → Manual CLI invocation"** —
  "OPERATOR runs ``cee sync-bible`` directly. Always allowed;
  force-syncs regardless of ``auto_sync``."

So manual invocation always force-syncs. The ``auto_sync = true``
config flag in ``~/.cee/config.toml`` only governs the boot-time
auto-sync trigger (boot step B2 per bible 00 §12), not this CLI
subcommand.

**Exit code semantics** (matching :mod:`cli.main`'s Phase 1 contract):

* ``0`` — full sync, every page synced or skipped successfully.
* ``1`` — partial failure: at least one page failed but the sync
  itself ran to completion (returned directly from this function),
  OR :class:`errors.BootBibleSyncError` propagated to
  :func:`cli.main.main` and caught as :class:`errors.BootError`
  (mcp_connect_failed / page_deleted / credentials_missing halts).
  In both cases the operator can re-run after addressing the cause.
* ``2`` — unexpected exception (caught by :func:`cli.main.main`'s
  outer ``except Exception``).

The two ``1`` exit causes are distinguished by the stderr stream:

* Partial failure prints ``PARTIAL: ...`` per-page summary from
  this function.
* Halt prints ``BOOT FAILURE [B2]: <kind>: <reason>`` from
  :func:`cli.main.main`'s formatter.
"""

from __future__ import annotations

import argparse
import sys

from boot.bible_sync import sync


def cmd_sync_bible(args: argparse.Namespace) -> int:  # noqa: ARG001 — argparse contract
    """Run ``cee sync-bible``.

    Calls :func:`boot.bible_sync.sync` with ``trigger="cli_manual"``
    and translates the :class:`boot.bible_sync.SyncResult` into a
    short stdout summary plus an exit code. Halts
    (:class:`errors.BootBibleSyncError`) propagate up to
    :func:`cli.main.main` which formats them per the boot-error
    convention; this function does not catch them.

    Returns
    -------
    int
        ``0`` if every page synced or skipped successfully, ``1``
        if any page failed.
    """
    result = sync(trigger="cli_manual")

    # Summary to stdout — matches verify.py's ``Summary: N of M ...``
    # cadence. Counts are sufficient for the OPERATOR; per-page detail
    # lives in roles.log per bible 04 §5.6's audit trail.
    print(
        f"Summary: synced={len(result.synced)} "
        f"skipped={len(result.skipped)} "
        f"failed={len(result.failed)} "
        f"duration_ms={result.duration_ms}"
    )

    if result.ok:
        print("PASSED.")
        return 0

    # Partial failure: list per-page failures on stderr so log scrapers
    # can grep them out. Matching verify.py's ``FAILED: see ...`` line
    # on stdout for the human reader.
    print("FAILED: at least one page did not sync.")
    for slug, error_type in result.failed:
        sys.stderr.write(f"  PARTIAL: {slug} ({error_type})\n")
    return 1
