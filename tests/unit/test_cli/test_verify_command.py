"""Tests for ``cli/commands/verify.py`` — the ``cee verify --layout`` mode.

Every test redirects every relevant ``paths.*`` constant under
``tmp_path`` via ``monkeypatch``. None of these tests touch the real
``~/.cee/``, ``~/cee/audit/``, or ``~/SecondBrain/cee/``.

The 23-path canonical set (4 user-config + 13 obsidian + 6 audit) is
the source of truth — it directly mirrors what ``scaffold_obsidian``
and ``scaffold_audit_logs`` create. Tests assert against ``23`` rather
than computing it dynamically so a regression in the canonical set
fails loudly instead of silently producing a different total.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

import paths
from cli.commands import verify as verify_module
from cli.commands.verify import (
    _is_ok,
    _render_item,
    _shorten_path,
    _verify_layout,
    cmd_verify,
)
from persistence.audit import scaffold_audit_logs
from persistence.obsidian import scaffold_obsidian


# ─── Fixture ────────────────────────────────────────────────────────────


@pytest.fixture
def cee_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Redirect every path the verifier reads under ``tmp_path``.

    Also seeds a complete canonical state (the 23 paths) so individual
    tests can selectively delete one item to simulate drift.
    """
    user_config = tmp_path / "user_config"
    cee_install = tmp_path / "cee"
    audit_dir = cee_install / "audit"
    obsidian_vault = tmp_path / "SecondBrain" / "cee"

    # User config layout
    monkeypatch.setattr(paths, "USER_CONFIG_DIR", user_config)
    monkeypatch.setattr(paths, "CONFIG_FILE", user_config / "config.toml")
    monkeypatch.setattr(paths, "REDACT_LIST", user_config / "redact_list")
    monkeypatch.setattr(
        paths, "NOTION_REDACT_LIST", user_config / "notion_redact_list"
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

    # Seed the canonical state. We don't go through cmd_init (that's a
    # different test module's job); instead we drop the user-config
    # files directly and call the two scaffold helpers.
    paths.ensure_dir(user_config)
    paths.CONFIG_FILE.write_text("# fake config\n", encoding="utf-8")
    paths.REDACT_LIST.write_text("# redact_list\n", encoding="utf-8")
    paths.NOTION_REDACT_LIST.write_text(
        "# notion_redact_list\n", encoding="utf-8"
    )
    scaffold_obsidian()
    scaffold_audit_logs()

    return {
        "user_config": user_config,
        "audit_dir": audit_dir,
        "obsidian_vault": obsidian_vault,
    }


def _ns(layout: bool = True) -> argparse.Namespace:
    """Argparse Namespace stand-in matching the verify subparser shape."""
    return argparse.Namespace(layout=layout, command="verify")


# ─── Happy path ─────────────────────────────────────────────────────────


def test_verify_layout_returns_zero_when_all_present(
    cee_root: dict[str, Path],
) -> None:
    assert _verify_layout() == 0


def test_verify_layout_summary_shows_correct_counts(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """All 23 canonical paths present → ``Summary: 23 of 23 paths present.``"""
    _verify_layout()
    out = capsys.readouterr().out
    assert "Summary: 23 of 23 paths present." in out


def test_verify_layout_passed_message_when_all_present(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    _verify_layout()
    out = capsys.readouterr().out
    assert "PASSED." in out


# ─── Drift detection: user config ──────────────────────────────────────


def test_verify_layout_returns_one_when_user_config_missing(
    cee_root: dict[str, Path],
) -> None:
    shutil.rmtree(cee_root["user_config"])
    assert _verify_layout() == 1


def test_verify_layout_returns_one_when_redact_list_missing(
    cee_root: dict[str, Path],
) -> None:
    paths.REDACT_LIST.unlink()
    assert _verify_layout() == 1


def test_verify_layout_returns_one_when_notion_redact_list_missing(
    cee_root: dict[str, Path],
) -> None:
    paths.NOTION_REDACT_LIST.unlink()
    assert _verify_layout() == 1


def test_verify_layout_returns_one_when_config_toml_missing(
    cee_root: dict[str, Path],
) -> None:
    paths.CONFIG_FILE.unlink()
    assert _verify_layout() == 1


# ─── Drift detection: Obsidian ─────────────────────────────────────────


def test_verify_layout_returns_one_when_obsidian_vault_missing(
    cee_root: dict[str, Path],
) -> None:
    shutil.rmtree(cee_root["obsidian_vault"])
    assert _verify_layout() == 1


def test_verify_layout_returns_one_when_obsidian_readme_missing(
    cee_root: dict[str, Path],
) -> None:
    (paths.OBSIDIAN_VAULT / "README.md").unlink()
    assert _verify_layout() == 1


@pytest.mark.parametrize(
    "subdir_attr",
    [
        "OBSIDIAN_RUNS_DIR",
        "OBSIDIAN_SKILLS_DIR",
        "OBSIDIAN_AGENTS_DIR",
        "OBSIDIAN_BIBLE_DIR",
        "OBSIDIAN_AUDIT_DIR",
    ],
)
def test_verify_layout_returns_one_when_obsidian_index_missing(
    cee_root: dict[str, Path], subdir_attr: str,
) -> None:
    """Each of the 5 vault content subdirs must have its index.md."""
    subdir = getattr(paths, subdir_attr)
    (subdir / "index.md").unlink()
    assert _verify_layout() == 1


def test_verify_layout_returns_one_when_obsidian_templates_dir_missing(
    cee_root: dict[str, Path],
) -> None:
    """``_templates/`` is required-and-empty per Path B (bible 13 §5.1)."""
    paths.OBSIDIAN_TEMPLATES_DIR.rmdir()
    assert _verify_layout() == 1


# ─── Drift detection: audit ────────────────────────────────────────────


def test_verify_layout_returns_one_when_audit_dir_missing(
    cee_root: dict[str, Path],
) -> None:
    shutil.rmtree(cee_root["audit_dir"])
    assert _verify_layout() == 1


def test_verify_layout_returns_one_when_audit_archive_dir_missing(
    cee_root: dict[str, Path],
) -> None:
    paths.AUDIT_ARCHIVE_DIR.rmdir()
    assert _verify_layout() == 1


@pytest.mark.parametrize(
    "log_attr",
    [
        "AUDIT_CLI_LOG",
        "AUDIT_ROLES_LOG",
        "AUDIT_BOOT_LOG",
        "AUDIT_SECURITY_LOG",
    ],
)
def test_verify_layout_returns_one_when_audit_log_file_missing(
    cee_root: dict[str, Path], log_attr: str,
) -> None:
    getattr(paths, log_attr).unlink()
    assert _verify_layout() == 1


# ─── Output content ────────────────────────────────────────────────────


def test_verify_layout_stdout_lists_missing_items(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    paths.NOTION_REDACT_LIST.unlink()
    _verify_layout()
    out = capsys.readouterr().out
    assert "MISSING" in out
    assert "notion_redact_list" in out


def test_verify_layout_stdout_uses_check_marks_for_present(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    _verify_layout()
    out = capsys.readouterr().out
    assert "✓" in out  # U+2713
    # All present → no ✗ marks anywhere.
    assert "✗" not in out


def test_verify_layout_stdout_uses_x_marks_for_missing(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    paths.NOTION_REDACT_LIST.unlink()
    _verify_layout()
    out = capsys.readouterr().out
    assert "✗" in out  # U+2717


def test_verify_layout_summary_counts_match_drift(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """Two missing paths → ``Summary: 21 of 23 paths present. 2 missing.``"""
    paths.NOTION_REDACT_LIST.unlink()
    paths.AUDIT_BOOT_LOG.unlink()
    _verify_layout()
    out = capsys.readouterr().out
    assert "Summary: 21 of 23 paths present. 2 missing." in out


def test_verify_layout_failed_message_when_any_missing(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    paths.REDACT_LIST.unlink()
    _verify_layout()
    out = capsys.readouterr().out
    assert "FAILED" in out


def test_verify_layout_suggests_cee_init_on_failure(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    paths.REDACT_LIST.unlink()
    _verify_layout()
    out = capsys.readouterr().out
    assert "cee init" in out


def test_verify_layout_stdout_has_three_substrate_sections(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """All three substrate headings appear in the report."""
    _verify_layout()
    out = capsys.readouterr().out
    assert "User config (~/.cee/):" in out
    assert "Obsidian vault (~/SecondBrain/cee/):" in out
    assert "Audit logs (~/cee/audit/):" in out


# ─── Wrong-type detection (defensive coverage) ─────────────────────────


def test_verify_layout_reports_wrong_type_when_file_replaces_dir(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """If a regular file occupies a directory slot, it's not 'present'."""
    paths.OBSIDIAN_TEMPLATES_DIR.rmdir()
    paths.OBSIDIAN_TEMPLATES_DIR.write_text("oops", encoding="utf-8")
    rc = _verify_layout()
    out = capsys.readouterr().out
    assert rc == 1
    assert "WRONG_TYPE" in out


# ─── cmd_verify dispatcher ─────────────────────────────────────────────


def test_cmd_verify_with_layout_flag_dispatches_to_verify_layout(
    cee_root: dict[str, Path],
) -> None:
    """cmd_verify(--layout) → calls _verify_layout exactly once."""
    with patch.object(verify_module, "_verify_layout", return_value=0) as spy:
        rc = cmd_verify(_ns(layout=True))
    spy.assert_called_once()
    assert rc == 0


def test_cmd_verify_without_layout_flag_returns_two(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """Bare ``cee verify`` (no mode) → exit 2 + usage hint on stderr."""
    rc = cmd_verify(_ns(layout=False))
    captured = capsys.readouterr()
    assert rc == 2
    assert "Specify a verify mode" in captured.err
    # Nothing written to stdout (the report belongs to a real mode).
    assert captured.out == ""


# ─── Helpers ────────────────────────────────────────────────────────────


def test_shorten_path_replaces_home_with_tilde(tmp_path: Path) -> None:
    home = Path.home()
    p = home / "foo" / "bar"
    rendered = _shorten_path(p)
    assert rendered.startswith("~/")
    assert "foo/bar" in rendered


def test_shorten_path_appends_slash_for_existing_dir(tmp_path: Path) -> None:
    rendered = _shorten_path(tmp_path)
    assert rendered.endswith("/")


def test_shorten_path_no_slash_for_nonexistent_or_file(
    tmp_path: Path,
) -> None:
    f = tmp_path / "afile.txt"
    f.write_text("x", encoding="utf-8")
    rendered = _shorten_path(f)
    assert not rendered.endswith("/")


def test_is_ok_directory_present(tmp_path: Path) -> None:
    assert _is_ok(tmp_path, "directory") is True


def test_is_ok_file_present(tmp_path: Path) -> None:
    f = tmp_path / "x"
    f.write_text("y", encoding="utf-8")
    assert _is_ok(f, "file") is True


def test_is_ok_missing(tmp_path: Path) -> None:
    assert _is_ok(tmp_path / "ghost", "file") is False


def test_is_ok_wrong_kind(tmp_path: Path) -> None:
    f = tmp_path / "actually-a-file"
    f.write_text("x", encoding="utf-8")
    assert _is_ok(f, "directory") is False


def test_render_item_present_uses_check_mark(tmp_path: Path) -> None:
    line = _render_item(tmp_path, "directory")
    assert line.startswith("✓")


def test_render_item_missing_uses_x_mark_and_label(tmp_path: Path) -> None:
    line = _render_item(tmp_path / "ghost", "file")
    assert line.startswith("✗")
    assert "MISSING" in line
