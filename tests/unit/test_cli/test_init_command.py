"""Tests for ``cli/commands/init.py`` — the ``cee init`` subcommand.

Every test redirects every relevant ``paths.*`` constant under
``tmp_path`` via ``monkeypatch``. None of these tests touches the real
``~/.cee/``, ``~/cee/audit/``, or ``~/SecondBrain/cee/``.

This test module verifies the **composition contract**: that ``cmd_init``
correctly orchestrates ``load_config``, ``scaffold_obsidian``,
``scaffold_audit_logs``, and ``audit_log_append`` in the right order
with the right arguments, and that idempotency holds. It does *not*
re-test the underlying primitives — those have their own test modules.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import paths
from cli.commands import init as init_module
from cli.commands.init import cmd_init
from persistence.audit import GENESIS_HASH


# ─── Fixture ────────────────────────────────────────────────────────────


@pytest.fixture
def cee_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Redirect every path the init command touches under ``tmp_path``.

    Returns a dict of relevant root paths so individual tests don't need
    to reconstruct them.
    """
    user_config = tmp_path / "user_config"
    cee_install = tmp_path / "cee"
    audit_dir = cee_install / "audit"
    template_dir = cee_install / ".template"
    obsidian_vault = tmp_path / "SecondBrain" / "cee"

    # Make a real template config.toml.default by copying the project's
    # actual one — the loader needs a parseable template to copy from.
    real_template = paths.TEMPLATE_CONFIG_FILE
    template_dir.mkdir(parents=True)
    shutil.copy(real_template, template_dir / "config.toml.default")

    # User config layout
    monkeypatch.setattr(paths, "USER_CONFIG_DIR", user_config)
    monkeypatch.setattr(paths, "CONFIG_FILE", user_config / "config.toml")
    monkeypatch.setattr(paths, "REDACT_LIST", user_config / "redact_list")
    monkeypatch.setattr(
        paths, "NOTION_REDACT_LIST", user_config / "notion_redact_list"
    )
    monkeypatch.setattr(
        paths, "TEMPLATE_CONFIG_FILE", template_dir / "config.toml.default"
    )

    # Obsidian vault
    monkeypatch.setattr(paths, "OBSIDIAN_VAULT", obsidian_vault)
    monkeypatch.setattr(paths, "OBSIDIAN_RUNS_DIR", obsidian_vault / "runs")
    monkeypatch.setattr(paths, "OBSIDIAN_SKILLS_DIR", obsidian_vault / "skills")
    monkeypatch.setattr(paths, "OBSIDIAN_AGENTS_DIR", obsidian_vault / "agents")
    monkeypatch.setattr(paths, "OBSIDIAN_BIBLE_DIR", obsidian_vault / "bible")
    monkeypatch.setattr(paths, "OBSIDIAN_AUDIT_DIR", obsidian_vault / "audit")
    monkeypatch.setattr(
        paths, "OBSIDIAN_TEMPLATES_DIR", obsidian_vault / "_templates"
    )

    # Audit logs
    monkeypatch.setattr(paths, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(paths, "AUDIT_ARCHIVE_DIR", audit_dir / "archive")
    monkeypatch.setattr(paths, "AUDIT_CLI_LOG", audit_dir / "cli.log")
    monkeypatch.setattr(paths, "AUDIT_ROLES_LOG", audit_dir / "roles.log")
    monkeypatch.setattr(paths, "AUDIT_BOOT_LOG", audit_dir / "boot.log")
    monkeypatch.setattr(
        paths, "AUDIT_SECURITY_LOG", audit_dir / "security.log"
    )

    return {
        "user_config": user_config,
        "cee_install": cee_install,
        "audit_dir": audit_dir,
        "obsidian_vault": obsidian_vault,
    }


def _ns() -> argparse.Namespace:
    """Trivial Namespace stand-in — cmd_init takes no flags."""
    return argparse.Namespace()


def _read_boot_entries(boot_log: Path) -> list[dict[str, Any]]:
    raw = boot_log.read_text(encoding="utf-8")
    return [json.loads(line) for line in raw.split("\n") if line]


# ─── User-config files ─────────────────────────────────────────────────


def test_init_creates_user_config_dir(cee_root: dict[str, Path]) -> None:
    cmd_init(_ns())
    assert cee_root["user_config"].is_dir()


def test_init_creates_config_toml_from_template(
    cee_root: dict[str, Path],
) -> None:
    cmd_init(_ns())
    assert paths.CONFIG_FILE.is_file()
    # Template content must have been copied (non-empty).
    assert paths.CONFIG_FILE.read_text(encoding="utf-8").strip() != ""


def test_init_creates_empty_redact_list_with_header(
    cee_root: dict[str, Path],
) -> None:
    cmd_init(_ns())
    body = paths.REDACT_LIST.read_text(encoding="utf-8")
    assert body.startswith("# CEE redact_list")
    # No actual patterns yet — header only.
    non_comment_lines = [
        line for line in body.splitlines()
        if line and not line.startswith("#")
    ]
    assert non_comment_lines == []


def test_init_creates_empty_notion_redact_list_with_header(
    cee_root: dict[str, Path],
) -> None:
    cmd_init(_ns())
    body = paths.NOTION_REDACT_LIST.read_text(encoding="utf-8")
    assert body.startswith("# CEE notion_redact_list")
    non_comment_lines = [
        line for line in body.splitlines()
        if line and not line.startswith("#")
    ]
    assert non_comment_lines == []


def test_init_redact_list_template_has_regex_doc_comment(
    cee_root: dict[str, Path],
) -> None:
    """The header documents the ``regex:`` prefix per bible 12 §5.3."""
    cmd_init(_ns())
    body = paths.REDACT_LIST.read_text(encoding="utf-8")
    assert "regex:" in body


# ─── Composition: scaffold helpers are called ──────────────────────────


def test_init_calls_scaffold_obsidian(cee_root: dict[str, Path]) -> None:
    with patch.object(
        init_module, "scaffold_obsidian",
        wraps=init_module.scaffold_obsidian,
    ) as spy:
        cmd_init(_ns())
    spy.assert_called_once()


def test_init_calls_scaffold_audit_logs(cee_root: dict[str, Path]) -> None:
    with patch.object(
        init_module, "scaffold_audit_logs",
        wraps=init_module.scaffold_audit_logs,
    ) as spy:
        cmd_init(_ns())
    spy.assert_called_once()


# ─── First boot.log entry ──────────────────────────────────────────────


def test_init_writes_first_boot_log_entry_to_boot_log(
    cee_root: dict[str, Path],
) -> None:
    cmd_init(_ns())
    entries = _read_boot_entries(paths.AUDIT_BOOT_LOG)
    assert len(entries) == 1


def test_init_first_boot_log_entry_actor_is_boot_sequencer(
    cee_root: dict[str, Path],
) -> None:
    cmd_init(_ns())
    entries = _read_boot_entries(paths.AUDIT_BOOT_LOG)
    assert entries[0]["actor"] == "BOOT_SEQUENCER"


def test_init_first_boot_log_entry_event_is_cee_init_complete(
    cee_root: dict[str, Path],
) -> None:
    cmd_init(_ns())
    entries = _read_boot_entries(paths.AUDIT_BOOT_LOG)
    assert entries[0]["event"] == "cee_init_complete"


def test_init_first_boot_log_entry_has_genesis_prev_hash(
    cee_root: dict[str, Path],
) -> None:
    cmd_init(_ns())
    entries = _read_boot_entries(paths.AUDIT_BOOT_LOG)
    assert entries[0]["prev_hash"] == GENESIS_HASH
    assert GENESIS_HASH == "0" * 64


def test_init_first_boot_log_entry_details_includes_all_counts(
    cee_root: dict[str, Path],
) -> None:
    cmd_init(_ns())
    entries = _read_boot_entries(paths.AUDIT_BOOT_LOG)
    details = entries[0]["details"]
    expected_keys = {
        "config_toml",
        "redact_list",
        "notion_redact_list",
        "obsidian_directories_created",
        "obsidian_files_created",
        "audit_files_created",
    }
    assert set(details.keys()) == expected_keys
    # Counts are non-negative ints.
    for key in (
        "obsidian_directories_created",
        "obsidian_files_created",
        "audit_files_created",
    ):
        assert isinstance(details[key], int)
        assert details[key] >= 0


# ─── Idempotency ───────────────────────────────────────────────────────


def test_init_is_idempotent_state(cee_root: dict[str, Path]) -> None:
    """Running twice does not modify the OPERATOR-mutable files."""
    cmd_init(_ns())
    config_after_first = paths.CONFIG_FILE.read_text(encoding="utf-8")
    redact_after_first = paths.REDACT_LIST.read_text(encoding="utf-8")
    notion_after_first = paths.NOTION_REDACT_LIST.read_text(encoding="utf-8")

    cmd_init(_ns())

    assert paths.CONFIG_FILE.read_text(encoding="utf-8") == config_after_first
    assert paths.REDACT_LIST.read_text(encoding="utf-8") == redact_after_first
    assert (
        paths.NOTION_REDACT_LIST.read_text(encoding="utf-8")
        == notion_after_first
    )


def test_init_is_idempotent_audit(cee_root: dict[str, Path]) -> None:
    """The audit chain advances by one entry per invocation."""
    cmd_init(_ns())
    cmd_init(_ns())

    entries = _read_boot_entries(paths.AUDIT_BOOT_LOG)
    assert len(entries) == 2
    assert entries[0]["prev_hash"] == GENESIS_HASH
    assert entries[1]["prev_hash"] == entries[0]["entry_hash"]


def test_init_existing_redact_list_preserved(
    cee_root: dict[str, Path],
) -> None:
    """OPERATOR's pre-existing redact_list survives ``cee init``."""
    paths.ensure_dir(paths.USER_CONFIG_DIR)
    paths.REDACT_LIST.write_text(
        "ClientCorp Inc\nProject Lighthouse\n", encoding="utf-8"
    )

    cmd_init(_ns())

    assert (
        paths.REDACT_LIST.read_text(encoding="utf-8")
        == "ClientCorp Inc\nProject Lighthouse\n"
    )


def test_init_existing_config_toml_preserved(
    cee_root: dict[str, Path],
) -> None:
    """OPERATOR's pre-existing config.toml survives ``cee init``.

    We pre-write a parseable but custom config (missing optional fields,
    so load_config validates with defaults). The loader only writes
    when the file is missing — it never overwrites existing content.
    """
    paths.ensure_dir(paths.USER_CONFIG_DIR)
    custom_config = paths.TEMPLATE_CONFIG_FILE.read_text(encoding="utf-8")
    # Inject a marker comment that wouldn't appear in the template.
    custom_config = "# OPERATOR-EDITED\n" + custom_config
    paths.CONFIG_FILE.write_text(custom_config, encoding="utf-8")

    cmd_init(_ns())

    assert paths.CONFIG_FILE.read_text(encoding="utf-8") == custom_config


def test_init_existing_notion_redact_list_preserved(
    cee_root: dict[str, Path],
) -> None:
    paths.ensure_dir(paths.USER_CONFIG_DIR)
    paths.NOTION_REDACT_LIST.write_text(
        "regex:notion-secret-[a-z0-9]+\n", encoding="utf-8"
    )

    cmd_init(_ns())

    assert (
        paths.NOTION_REDACT_LIST.read_text(encoding="utf-8")
        == "regex:notion-secret-[a-z0-9]+\n"
    )


# ─── Return code & stdout summary ──────────────────────────────────────


def test_init_returns_zero_on_success(cee_root: dict[str, Path]) -> None:
    rc = cmd_init(_ns())
    assert rc == 0


def test_init_prints_summary_to_stdout(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    cmd_init(_ns())
    captured = capsys.readouterr()
    assert "CEE initialized successfully." in captured.out


def test_init_summary_includes_obsidian_counts(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    cmd_init(_ns())
    out = capsys.readouterr().out
    assert "Obsidian vault" in out
    assert "directories created:" in out
    assert "files created:" in out


def test_init_summary_includes_audit_counts(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    cmd_init(_ns())
    out = capsys.readouterr().out
    assert "Audit logs" in out
    assert "log files created:" in out


def test_init_summary_marks_existing_files(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """Second invocation reports ``already exists`` for the 3 user files."""
    cmd_init(_ns())
    capsys.readouterr()  # discard first-run output

    cmd_init(_ns())
    out = capsys.readouterr().out
    assert "config.toml          [already exists]" in out
    assert "redact_list          [already exists]" in out
    assert "notion_redact_list   [already exists]" in out


# ─── No leakage outside the patched roots ──────────────────────────────


def test_init_writes_only_under_tmp_path(
    cee_root: dict[str, Path], tmp_path: Path,
) -> None:
    """No file system mutation happens outside ``tmp_path``."""
    sibling = tmp_path / "sentinel.txt"
    sibling.write_text("untouched", encoding="utf-8")

    cmd_init(_ns())

    # All writes should be under one of the patched roots, all of which
    # are themselves under tmp_path.
    for path in tmp_path.rglob("*"):
        rel = path.relative_to(tmp_path)
        first = rel.parts[0]
        assert first in {"user_config", "cee", "SecondBrain", "sentinel.txt"}, (
            f"unexpected write outside patched roots: {rel}"
        )

    assert sibling.read_text(encoding="utf-8") == "untouched"
