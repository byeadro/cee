"""CEE CLI dispatcher — entry point for the ``cee`` console script.

Phase 1 task 13 ships only the ``init`` subcommand. Tasks 14, 15 and
later phases extend the dispatcher with additional verbs (``verify``,
``audit-verify``, ``replay``, …). Each verb is added by registering a
``set_defaults(func=cmd_<name>)`` call in :func:`main`.

Exit codes (bible 19 §5 boot-error contract + standard CLI convention):

* ``0`` — success.
* ``1`` — :class:`errors.BootError`. The boot step and reason are
  surfaced on stderr so the OPERATOR can map back to bible 00 §12 step
  taxonomy. Bible 19 §5.7 names this the recoverable-by-OPERATOR class.
* ``2`` — any other exception. The exception type and message are
  surfaced on stderr; the stack trace is intentionally suppressed
  (debugging happens via the audit logs and the per-Run ``error.json``,
  not by dumping a traceback to a CLI user).

Argparse with ``required=True`` on the subparser means a bare ``cee``
invocation (no subcommand) produces argparse's "the following arguments
are required: command" error and exits non-zero — matching standard
``git``-style behaviour.
"""

from __future__ import annotations

import argparse
import sys

from cli.commands.audit_verify import cmd_audit_verify
from cli.commands.init import cmd_init
from cli.commands.sync_bible import cmd_sync_bible
from cli.commands.verify import cmd_verify
from errors import BootError


def main(argv: list[str] | None = None) -> int:
    """CEE CLI entry point.

    Parameters
    ----------
    argv
        Command-line argument list (without ``argv[0]``). ``None`` (the
        default) lets argparse read from :data:`sys.argv`. Tests pass an
        explicit list to avoid coupling to the live process state.

    Returns
    -------
    int
        Exit code: ``0`` success, ``1`` :class:`errors.BootError`,
        ``2`` any other unexpected exception.
    """
    parser = argparse.ArgumentParser(
        prog="cee",
        description="Claude Execution Engine",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize CEE installation (~/.cee/, Obsidian vault, audit logs)",
    )
    init_parser.set_defaults(func=cmd_init)

    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify CEE installation (layout, schemas, ...)",
    )
    verify_parser.add_argument(
        "--layout",
        action="store_true",
        help="Verify directory layout (existence checks against bible "
        "04 §5.1, §5.2, §5.3 + 12 §5.8)",
    )
    verify_parser.add_argument(
        "--schemas",
        action="store_true",
        help="Verify the 14 artifact schemas import, validate, and "
        "produce JSON-serializable model_json_schema() output "
        "(bible 04 §6.1 + 10 §6.3 + 11 §6.2)",
    )
    verify_parser.add_argument(
        "--boot",
        action="store_true",
        help="Run the canonical boot sequence (B1-B9 per bible 00 §12) "
        "and report per-step results + halt detail (bible 20 §5.2)",
    )
    verify_parser.add_argument(
        "--bible",
        action="store_true",
        help="Verify bible consistency (B3) + bible drift vs Notion "
        "(bible 04 §5.5 + §5.6, bible 20 §5.2)",
    )
    verify_parser.add_argument(
        "--obsidian",
        action="store_true",
        help="Verify Obsidian vault scaffold under ~/SecondBrain/cee/ "
        "(read-only existence checks against bible 13 §5 layout, "
        "per bible 20 §5.3 Phase 3 CLI surface)",
    )
    verify_parser.set_defaults(func=cmd_verify)

    sync_bible_parser = subparsers.add_parser(
        "sync-bible",
        help="Sync the bible mirror from Notion (bible 04 §5.6)",
    )
    sync_bible_parser.set_defaults(func=cmd_sync_bible)

    audit_verify_parser = subparsers.add_parser(
        "audit-verify",
        help="Verify hash chain integrity of the four canonical audit "
        "logs under ~/cee/audit/ (bible 12 §10.6 + bible 20 §5.3)",
        description=(
            "Verify the hash chain integrity of every canonical audit "
            "log under ~/cee/audit/ — cli.log, roles.log, boot.log, "
            "security.log (bible 12 §5.8). Detects tampering or "
            "corruption per bible 12 §10.6. Pure read; no writes. "
            "Phase 3 CLI surface per bible 20 §5.3."
        ),
    )
    audit_verify_parser.set_defaults(func=cmd_audit_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BootError as e:
        sys.stderr.write(f"BOOT FAILURE [{e.step}]: {e.reason}\n")
        return 1
    except Exception as e:  # noqa: BLE001 — outer CLI safety net
        sys.stderr.write(f"UNEXPECTED ERROR: {type(e).__name__}: {e}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
