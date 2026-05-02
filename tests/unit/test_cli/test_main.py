"""Tests for ``cli/main.py`` — the argparse dispatcher.

The dispatcher's only job is to (a) wire subcommand functions, (b) parse
argv, (c) call the chosen function, and (d) translate exceptions into
exit codes. These tests cover that contract directly without touching
the ``cmd_init`` body — that lives in ``test_init_command.py``.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from cli import main as main_module
from cli.main import main
from errors import BootError


def test_main_with_no_args_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    """``cee`` with no subcommand → argparse SystemExit, non-zero code.

    argparse raises ``SystemExit(2)`` for missing-required-arg before our
    try/except can run. That's standard CLI behaviour and what
    ``required=True`` on the subparser produces.
    """
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0


def test_main_with_unknown_subcommand_exits_nonzero() -> None:
    """An unregistered subcommand → argparse SystemExit, non-zero code."""
    with pytest.raises(SystemExit) as exc_info:
        main(["does-not-exist"])
    assert exc_info.value.code != 0


def test_main_with_init_invokes_cmd_init() -> None:
    """``cee init`` calls cmd_init with the parsed args namespace."""
    fake_cmd = MagicMock(return_value=0)
    with patch.object(main_module, "cmd_init", fake_cmd):
        # Re-run main; the dispatcher reads cmd_init from main_module at
        # main() call time when it builds the parser, so the patch needs
        # to be on main_module's namespace.
        rc = main(["init"])
    assert rc == 0
    fake_cmd.assert_called_once()
    # The single positional arg is the parsed argparse Namespace.
    call_args = fake_cmd.call_args
    assert call_args.args[0].command == "init"


def test_main_returns_zero_on_success() -> None:
    """When the subcommand returns 0, main returns 0."""
    fake_cmd = MagicMock(return_value=0)
    with patch.object(main_module, "cmd_init", fake_cmd):
        rc = main(["init"])
    assert rc == 0


def test_main_returns_subcommand_nonzero_exit_code() -> None:
    """A subcommand returning a non-zero int is propagated."""
    fake_cmd = MagicMock(return_value=42)
    with patch.object(main_module, "cmd_init", fake_cmd):
        rc = main(["init"])
    assert rc == 42


def test_main_catches_boot_error_returns_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """BootError → return 1, stderr formatted as ``BOOT FAILURE [step]: reason``."""
    fake_cmd = MagicMock(side_effect=BootError("B1", "config missing"))
    with patch.object(main_module, "cmd_init", fake_cmd):
        rc = main(["init"])
    assert rc == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "BOOT FAILURE [B1]: config missing" in captured.err


def test_main_boot_error_stderr_includes_step_and_reason(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The stderr line carries both the boot step and the reason."""
    fake_cmd = MagicMock(side_effect=BootError("B7", "schema mismatch"))
    with patch.object(main_module, "cmd_init", fake_cmd):
        main(["init"])
    captured = capsys.readouterr()
    assert "B7" in captured.err
    assert "schema mismatch" in captured.err


def test_main_catches_unexpected_error_returns_two(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Any non-BootError exception → return 2, stderr formatted."""
    fake_cmd = MagicMock(side_effect=ValueError("kaboom"))
    with patch.object(main_module, "cmd_init", fake_cmd):
        rc = main(["init"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "UNEXPECTED ERROR: ValueError: kaboom" in captured.err


def test_main_unexpected_error_stderr_includes_exception_type(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_cmd = MagicMock(side_effect=RuntimeError("oops"))
    with patch.object(main_module, "cmd_init", fake_cmd):
        main(["init"])
    captured = capsys.readouterr()
    # Type name is included so the OPERATOR can grep for it in shell history.
    assert re.search(r"UNEXPECTED ERROR: RuntimeError: oops", captured.err)


def test_main_with_verify_layout_invokes_cmd_verify() -> None:
    """``cee verify --layout`` dispatches to cmd_verify with layout=True."""
    fake_cmd = MagicMock(return_value=0)
    with patch.object(main_module, "cmd_verify", fake_cmd):
        rc = main(["verify", "--layout"])
    assert rc == 0
    fake_cmd.assert_called_once()
    call_args = fake_cmd.call_args
    ns = call_args.args[0]
    assert ns.command == "verify"
    assert ns.layout is True


def test_main_with_verify_no_flag_invokes_cmd_verify_layout_false() -> None:
    """``cee verify`` (no --layout) still reaches cmd_verify; layout=False."""
    fake_cmd = MagicMock(return_value=2)
    with patch.object(main_module, "cmd_verify", fake_cmd):
        rc = main(["verify"])
    assert rc == 2
    ns = fake_cmd.call_args.args[0]
    assert ns.layout is False


def test_main_verify_help_includes_layout_option(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``cee verify --help`` mentions the --layout flag."""
    with pytest.raises(SystemExit):
        main(["verify", "--help"])
    out = capsys.readouterr().out
    assert "--layout" in out


def test_main_with_verify_schemas_invokes_cmd_verify() -> None:
    """``cee verify --schemas`` dispatches with schemas=True, layout=False."""
    fake_cmd = MagicMock(return_value=0)
    with patch.object(main_module, "cmd_verify", fake_cmd):
        rc = main(["verify", "--schemas"])
    assert rc == 0
    fake_cmd.assert_called_once()
    ns = fake_cmd.call_args.args[0]
    assert ns.command == "verify"
    assert ns.schemas is True
    assert ns.layout is False


def test_main_with_verify_both_flags_invokes_cmd_verify_with_both_true() -> None:
    """``cee verify --layout --schemas`` → both flags True on the namespace."""
    fake_cmd = MagicMock(return_value=0)
    with patch.object(main_module, "cmd_verify", fake_cmd):
        rc = main(["verify", "--layout", "--schemas"])
    assert rc == 0
    ns = fake_cmd.call_args.args[0]
    assert ns.layout is True
    assert ns.schemas is True


def test_main_with_verify_layout_only_has_schemas_false() -> None:
    """``cee verify --layout`` (no --schemas) defaults schemas to False."""
    fake_cmd = MagicMock(return_value=0)
    with patch.object(main_module, "cmd_verify", fake_cmd):
        main(["verify", "--layout"])
    ns = fake_cmd.call_args.args[0]
    assert ns.layout is True
    assert ns.schemas is False


def test_main_verify_help_includes_schemas_option(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``cee verify --help`` mentions the --schemas flag."""
    with pytest.raises(SystemExit):
        main(["verify", "--help"])
    out = capsys.readouterr().out
    assert "--schemas" in out


# ─── Phase 2 task 9: --boot flag registration ──────────────────────────


def test_main_verify_boot_flag_is_registered() -> None:
    """``cee verify --boot`` parses without an argparse error."""
    fake_cmd = MagicMock(return_value=0)
    with patch.object(main_module, "cmd_verify", fake_cmd):
        rc = main(["verify", "--boot"])
    assert rc == 0
    ns = fake_cmd.call_args.args[0]
    assert ns.boot is True
    assert ns.layout is False
    assert ns.schemas is False


def test_main_verify_help_includes_boot_option(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``cee verify --help`` mentions the --boot flag and B1-B9 grounding."""
    with pytest.raises(SystemExit):
        main(["verify", "--help"])
    out = capsys.readouterr().out
    assert "--boot" in out
    assert "B1-B9" in out or "boot sequence" in out.lower()


# ─── Phase 2 task 10: --bible flag registration ────────────────────────


def test_main_verify_bible_flag_is_registered() -> None:
    """``cee verify --bible`` parses without an argparse error."""
    fake_cmd = MagicMock(return_value=0)
    with patch.object(main_module, "cmd_verify", fake_cmd):
        rc = main(["verify", "--bible"])
    assert rc == 0
    ns = fake_cmd.call_args.args[0]
    assert ns.bible is True
    assert ns.boot is False
    assert ns.layout is False
    assert ns.schemas is False


def test_main_verify_help_includes_bible_option(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``cee verify --help`` mentions the --bible flag and bible-04 grounding."""
    with pytest.raises(SystemExit):
        main(["verify", "--help"])
    out = capsys.readouterr().out
    assert "--bible" in out
    assert "drift" in out.lower() or "consistency" in out.lower()
