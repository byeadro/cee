"""Tests for cee/paths.py — the single source of truth for filesystem paths."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import paths


def _public_constants() -> list[tuple[str, object]]:
    """Return all public ALL_CAPS attributes of the paths module."""
    return [
        (name, getattr(paths, name))
        for name in dir(paths)
        if name.isupper() and not name.startswith("_")
    ]


def test_cee_root_is_user_home_cee() -> None:
    assert paths.CEE_ROOT == Path.home() / "cee"


def test_all_constants_are_paths() -> None:
    for name, value in _public_constants():
        assert isinstance(value, Path), (
            f"{name} is not pathlib.Path "
            f"(got {type(value).__name__}={value!r})"
        )


def test_no_string_paths() -> None:
    for name, value in _public_constants():
        assert not isinstance(value, str), (
            f"{name} is a str ({value!r}); paths must be pathlib.Path"
        )


def test_subdirs_under_cee_root() -> None:
    """Every constant intended to live under ~/cee/ is in fact under CEE_ROOT."""
    cee_subpaths = [
        paths.BIBLE_DIR,
        paths.BIBLE_SYNC_META,
        paths.SCHEMAS_DIR,
        paths.PROMPTS_DIR,
        paths.SKILLS_DIR,
        paths.AGENTS_DIR,
        paths.COMMANDS_DIR,
        paths.HOOKS_DIR,
        paths.RUNS_DIR,
        paths.GOLDEN_RUNS_DIR,
        paths.AUDIT_DIR,
        paths.AUDIT_ARCHIVE_DIR,
        paths.TEMPLATE_DIR,
        paths.TESTS_DIR,
        paths.TESTS_FIXTURES_DIR,
        paths.INTERPRETER_DIR,
        paths.CLASSIFIER_DIR,
        paths.AGENT_SELECTOR_DIR,
        paths.SKILL_ENGINE_DIR,
        paths.STRATEGY_BUILDER_DIR,
        paths.PROMPT_BUILDER_DIR,
        paths.SAFETY_GATE_DIR,
        paths.PERSISTENCE_DIR,
        paths.BOOT_DIR,
        paths.EXECUTOR_DIR,
        paths.ROLES_DIR,
        paths.ERRORS_DIR,
        paths.OUTPUT_FORMAT_DIR,
        paths.GROUNDING_DIR,
        paths.PROMOTION_QUEUE,
        paths.AUDIT_CLI_LOG,
        paths.AUDIT_ROLES_LOG,
        paths.AUDIT_BOOT_LOG,
        paths.AUDIT_SECURITY_LOG,
    ]
    for p in cee_subpaths:
        assert paths.CEE_ROOT in p.parents, f"{p} is not under CEE_ROOT"


def test_user_config_under_home() -> None:
    assert paths.USER_CONFIG_DIR == Path.home() / ".cee"
    user_config_files = [
        paths.CONFIG_FILE,
        paths.REDACT_LIST,
        paths.NOTION_REDACT_LIST,
        paths.CREDENTIALS_FILE,
    ]
    for p in user_config_files:
        assert paths.USER_CONFIG_DIR in p.parents, (
            f"{p} is not under USER_CONFIG_DIR"
        )


def test_obsidian_vault_under_home() -> None:
    assert paths.OBSIDIAN_VAULT == Path.home() / "SecondBrain" / "cee"
    obsidian_subdirs = [
        paths.OBSIDIAN_RUNS_DIR,
        paths.OBSIDIAN_SKILLS_DIR,
        paths.OBSIDIAN_AGENTS_DIR,
        paths.OBSIDIAN_BIBLE_DIR,
        paths.OBSIDIAN_AUDIT_DIR,
        paths.OBSIDIAN_TEMPLATES_DIR,
    ]
    for p in obsidian_subdirs:
        assert paths.OBSIDIAN_VAULT in p.parents, (
            f"{p} is not under OBSIDIAN_VAULT"
        )


def test_audit_logs_under_audit_dir() -> None:
    audit_logs = [
        paths.AUDIT_CLI_LOG,
        paths.AUDIT_ROLES_LOG,
        paths.AUDIT_BOOT_LOG,
        paths.AUDIT_SECURITY_LOG,
    ]
    for log in audit_logs:
        assert log.parent == paths.AUDIT_DIR, (
            f"{log} is not directly under AUDIT_DIR"
        )


def test_ensure_dir_creates(tmp_path: Path) -> None:
    target = tmp_path / "newdir" / "nested"
    assert not target.exists()
    result = paths.ensure_dir(target)
    assert target.exists()
    assert target.is_dir()
    assert result == target


def test_ensure_dir_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "alreadyhere"
    target.mkdir()
    paths.ensure_dir(target)
    paths.ensure_dir(target)
    assert target.is_dir()


def test_ensure_dir_returns_path(tmp_path: Path) -> None:
    target = tmp_path / "x"
    result = paths.ensure_dir(target)
    assert result is target


def test_derive_run_dir_valid() -> None:
    run_id = "20260430_141522_a3f8c2d1"
    assert paths.derive_run_dir(run_id) == paths.RUNS_DIR / run_id


def test_derive_run_dir_rejects_bad_format() -> None:
    with pytest.raises(ValueError):
        paths.derive_run_dir("not-a-valid-id")


def test_module_import_has_no_side_effects(tmp_path: Path) -> None:
    """Importing paths.py in a fresh process must not create any directories."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    project_root = Path(paths.__file__).resolve().parent

    env = os.environ.copy()
    env["HOME"] = str(fake_home)

    result = subprocess.run(
        [sys.executable, "-c", "import paths"],
        env=env,
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"import failed: stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    contents = list(fake_home.iterdir())
    assert contents == [], (
        f"importing paths created entries in fresh HOME: {contents}"
    )
