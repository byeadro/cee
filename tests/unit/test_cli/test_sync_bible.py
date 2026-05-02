"""Tests for ``cli/commands/sync_bible.py`` — the ``cee sync-bible``
subcommand.

The orchestration body lives in ``boot.bible_sync.sync`` (T6) and has
its own dedicated test module. These tests cover only the CLI shim:

* The dispatcher invokes :func:`boot.bible_sync.sync` with
  ``trigger="cli_manual"``.
* :class:`SyncResult` is translated into the expected stdout summary
  + exit code.
* :class:`errors.BootBibleSyncError` propagates unwrapped to
  :func:`cli.main.main` (which catches it as a :class:`BootError`
  per Phase 1 convention) — verified end-to-end via ``main(...)``.
* Unexpected exceptions propagate to ``main``'s outer ``except``
  (exit ``2``).
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

import pytest

from boot.bible_sync import SyncResult
from cli import main as main_module
from cli.commands import sync_bible as sync_bible_module
from cli.commands.sync_bible import cmd_sync_bible
from cli.main import main
from errors import BootBibleSyncError


# --------------------------------------------------------------------------- #
# cmd_sync_bible — direct invocation                                          #
# --------------------------------------------------------------------------- #


def _ns() -> argparse.Namespace:
    """Argparse namespace stand-in matching the sync-bible subparser
    shape (no flags, no positional args)."""
    return argparse.Namespace(command="sync-bible")


def test_cmd_sync_bible_invokes_sync_with_cli_manual_trigger() -> None:
    fake_result = SyncResult(
        ok=True,
        trigger="cli_manual",
        synced=("00_project_vision",),
        skipped=(),
        failed=(),
        duration_ms=42,
    )
    with patch.object(sync_bible_module, "sync", return_value=fake_result) as fake_sync:
        rc = cmd_sync_bible(_ns())
    assert rc == 0
    fake_sync.assert_called_once_with(trigger="cli_manual")


def test_cmd_sync_bible_happy_path_prints_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_result = SyncResult(
        ok=True,
        trigger="cli_manual",
        synced=("00_project_vision", "01_real_problem_breakdown"),
        skipped=("19_error_handling_failure_states",),
        failed=(),
        duration_ms=128,
    )
    with patch.object(sync_bible_module, "sync", return_value=fake_result):
        rc = cmd_sync_bible(_ns())
    assert rc == 0
    out = capsys.readouterr().out
    assert "synced=2" in out
    assert "skipped=1" in out
    assert "failed=0" in out
    assert "duration_ms=128" in out
    assert "PASSED." in out


def test_cmd_sync_bible_partial_failure_returns_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_result = SyncResult(
        ok=False,
        trigger="cli_manual",
        synced=("00_project_vision",),
        skipped=(),
        failed=(("01_real_problem_breakdown", "RuntimeError"),),
        duration_ms=77,
    )
    with patch.object(sync_bible_module, "sync", return_value=fake_result):
        rc = cmd_sync_bible(_ns())
    assert rc == 1
    captured = capsys.readouterr()
    assert "synced=1" in captured.out
    assert "failed=1" in captured.out
    assert "FAILED" in captured.out
    # Per-page failure surfaces on stderr for log scrapers.
    assert "01_real_problem_breakdown" in captured.err
    assert "RuntimeError" in captured.err


def test_cmd_sync_bible_partial_failure_lists_every_failed_page(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_result = SyncResult(
        ok=False,
        trigger="cli_manual",
        synced=(),
        skipped=(),
        failed=(
            ("00_project_vision", "ConnectionError"),
            ("04_database_file_structure", "OSError"),
        ),
        duration_ms=22,
    )
    with patch.object(sync_bible_module, "sync", return_value=fake_result):
        rc = cmd_sync_bible(_ns())
    assert rc == 1
    err = capsys.readouterr().err
    assert "00_project_vision" in err
    assert "ConnectionError" in err
    assert "04_database_file_structure" in err
    assert "OSError" in err


def test_cmd_sync_bible_does_not_catch_BootBibleSyncError() -> None:
    """Halts must propagate so :func:`cli.main.main` formats them
    via its existing ``BOOT FAILURE [{step}]: {reason}`` handler.
    Catching them in the cmd would duplicate the formatter and break
    the Phase 1 convention."""
    halt = BootBibleSyncError(kind="mcp_connect_failed", reason="net down")
    with patch.object(sync_bible_module, "sync", side_effect=halt):
        with pytest.raises(BootBibleSyncError):
            cmd_sync_bible(_ns())


# --------------------------------------------------------------------------- #
# End-to-end via cli.main.main                                                #
# --------------------------------------------------------------------------- #


def test_main_with_sync_bible_invokes_cmd_sync_bible() -> None:
    """``cee sync-bible`` dispatches to cmd_sync_bible with the parsed
    namespace and returns its exit code."""
    fake_result = SyncResult(
        ok=True,
        trigger="cli_manual",
        synced=(),
        skipped=(),
        failed=(),
        duration_ms=0,
    )
    with patch.object(sync_bible_module, "sync", return_value=fake_result):
        rc = main(["sync-bible"])
    assert rc == 0


def test_main_sync_bible_help_lists_subcommand(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Top-level ``cee --help`` mentions sync-bible so operators
    discover it."""
    with pytest.raises(SystemExit):
        main(["--help"])
    out = capsys.readouterr().out
    assert "sync-bible" in out


def test_main_sync_bible_no_extra_flags_accepted() -> None:
    """Bible 04 §5.6 + bible 00 §11 canonize ``cee sync-bible`` with
    no flags. Adding ``--force`` (or any flag) must error out."""
    with pytest.raises(SystemExit):
        main(["sync-bible", "--force"])


def test_main_sync_bible_propagates_partial_failure_exit_code() -> None:
    fake_result = SyncResult(
        ok=False,
        trigger="cli_manual",
        synced=(),
        skipped=(),
        failed=(("00_project_vision", "RuntimeError"),),
        duration_ms=10,
    )
    with patch.object(sync_bible_module, "sync", return_value=fake_result):
        rc = main(["sync-bible"])
    assert rc == 1


def test_main_sync_bible_halt_caught_as_boot_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """End-to-end: BootBibleSyncError raised by sync() is caught by
    main()'s outer BootError handler, formatted as
    ``BOOT FAILURE [B2]: <kind>: <reason>``, returns ``1``."""
    halt = BootBibleSyncError(
        kind="mcp_connect_failed", reason="Anthropic SDK unreachable"
    )
    with patch.object(sync_bible_module, "sync", side_effect=halt):
        rc = main(["sync-bible"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "BOOT FAILURE [B2]" in err
    assert "mcp_connect_failed" in err
    assert "Anthropic SDK unreachable" in err


def test_main_sync_bible_page_deleted_halt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    halt = BootBibleSyncError(
        kind="page_deleted",
        reason="parent page returned zero children",
    )
    with patch.object(sync_bible_module, "sync", side_effect=halt):
        rc = main(["sync-bible"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "page_deleted" in err


def test_main_sync_bible_credentials_missing_halt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    halt = BootBibleSyncError(
        kind="credentials_missing",
        reason="credentials.toml has no [anthropic] section",
    )
    with patch.object(sync_bible_module, "sync", side_effect=halt):
        rc = main(["sync-bible"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "credentials_missing" in err


def test_main_sync_bible_unexpected_exception_returns_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A non-BootError exception bubbles to ``main()``'s ``except
    Exception`` and produces exit ``2``. The Phase 1 contract."""
    with patch.object(sync_bible_module, "sync", side_effect=ValueError("bug")):
        rc = main(["sync-bible"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "UNEXPECTED ERROR" in err
    assert "ValueError" in err


def test_main_module_exports_cmd_sync_bible() -> None:
    """Defensive: the dispatcher imports cmd_sync_bible at module load
    time. If a future refactor breaks the import, this test fails
    instead of letting ``cee sync-bible`` blow up at runtime."""
    assert hasattr(main_module, "cmd_sync_bible")
