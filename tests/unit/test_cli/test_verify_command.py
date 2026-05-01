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
import importlib
import json
import shutil
import sys
import types
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import pytest
from pydantic import BaseModel

import paths
from cli.commands import verify as verify_module
from cli.commands.verify import (
    SCHEMA_MANIFEST,
    _is_ok,
    _render_item,
    _shorten_path,
    _verify_layout,
    _verify_one_schema,
    _verify_schemas,
    cmd_verify,
)
from persistence.audit import scaffold_audit_logs
from persistence.obsidian import scaffold_obsidian
from roles import RoleEnum


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


def _ns(layout: bool = True, schemas: bool = False) -> argparse.Namespace:
    """Argparse Namespace stand-in matching the verify subparser shape."""
    return argparse.Namespace(layout=layout, schemas=schemas, command="verify")


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


def test_cmd_verify_without_any_flag_returns_two(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """Bare ``cee verify`` (no mode) → exit 2 + usage hint on stderr."""
    rc = cmd_verify(_ns(layout=False, schemas=False))
    captured = capsys.readouterr()
    assert rc == 2
    assert "Specify a verify mode" in captured.err
    # The hint must mention both currently-shipping modes.
    assert "--layout" in captured.err
    assert "--schemas" in captured.err
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


# ─── Schema verifier — happy path against real schemas ─────────────────


def test_verify_schemas_returns_zero_when_all_valid() -> None:
    """The 15 real schemas on disk must all validate cleanly."""
    assert _verify_schemas() == 0


def test_verify_schemas_walks_all_15_schemas(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Bible 04 §6.1 + 04 §5.5 + 10 §6.3 + 11 §6.2 → 15 schemas total."""
    _verify_schemas()
    out = capsys.readouterr().out
    assert "15 of 15" in out


def test_verify_schemas_categorizes_pipeline_vs_frontmatter_vs_declaration_vs_bible_sync(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """All four category headings appear with correct counts."""
    _verify_schemas()
    out = capsys.readouterr().out
    assert "Pipeline artifact schemas (10):" in out
    assert "Frontmatter schemas (2):" in out
    assert "Declaration schemas (2):" in out
    assert "Bible sync state schemas (1):" in out


def test_verify_schemas_summary_format(capsys: pytest.CaptureFixture[str]) -> None:
    _verify_schemas()
    out = capsys.readouterr().out
    assert "Summary: 15 of 15 schemas valid." in out


def test_verify_schemas_passed_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _verify_schemas()
    out = capsys.readouterr().out
    assert "PASSED." in out


def test_verify_schemas_uses_check_marks_for_valid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _verify_schemas()
    out = capsys.readouterr().out
    assert "✓" in out
    assert "✗" not in out


def test_verify_schemas_lists_module_path_for_each_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every manifest module path must appear in the report."""
    _verify_schemas()
    out = capsys.readouterr().out
    for module_name, _, _, _ in SCHEMA_MANIFEST:
        assert f"({module_name})" in out


def test_verify_schemas_lists_class_name_for_each_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every manifest class name must appear in the report."""
    _verify_schemas()
    out = capsys.readouterr().out
    for _, class_name, _, _ in SCHEMA_MANIFEST:
        assert class_name in out


# ─── Schema verifier — manifest invariants ─────────────────────────────


def test_schema_manifest_count_is_15() -> None:
    assert len(SCHEMA_MANIFEST) == 15


def test_schema_manifest_pipeline_count_is_10() -> None:
    pipeline = [e for e in SCHEMA_MANIFEST if e[3] == "pipeline"]
    assert len(pipeline) == 10


def test_schema_manifest_frontmatter_count_is_2() -> None:
    frontmatter = [e for e in SCHEMA_MANIFEST if e[3] == "frontmatter"]
    assert len(frontmatter) == 2


def test_schema_manifest_declaration_count_is_2() -> None:
    declaration = [e for e in SCHEMA_MANIFEST if e[3] == "declaration"]
    assert len(declaration) == 2


def test_schema_manifest_bible_sync_count_is_1() -> None:
    bible_sync = [e for e in SCHEMA_MANIFEST if e[3] == "bible_sync"]
    assert len(bible_sync) == 1


def test_schema_manifest_pipeline_entries_have_produced_by() -> None:
    """has_produced_by must be True for every pipeline entry."""
    for _, _, has_pb, category in SCHEMA_MANIFEST:
        if category == "pipeline":
            assert has_pb is True


def test_schema_manifest_non_pipeline_entries_have_no_produced_by() -> None:
    """Frontmatter and declaration schemas must not declare produced_by."""
    for _, _, has_pb, category in SCHEMA_MANIFEST:
        if category in {"frontmatter", "declaration"}:
            assert has_pb is False


def test_schema_manifest_does_not_include_config_module() -> None:
    """schemas/config.py is the user-config Pydantic model, not an artifact."""
    for module_name, _, _, _ in SCHEMA_MANIFEST:
        assert module_name != "schemas.config"


# ─── Schema verifier — produced_by RoleEnum invariants (real schemas) ──


def test_verify_schemas_checks_produced_by_role_enum() -> None:
    """Every pipeline schema declares produced_by: RoleEnum.

    This guards against drift from task 9b's typesystem closure.
    """
    for module_name, class_name, has_pb, _ in SCHEMA_MANIFEST:
        if not has_pb:
            continue
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        field = cls.model_fields["produced_by"]
        assert field.annotation is RoleEnum, (
            f"{class_name}.produced_by annotation is "
            f"{field.annotation!r}, expected RoleEnum"
        )


def test_verify_schemas_skips_produced_by_check_for_frontmatter() -> None:
    """Frontmatter schemas have no produced_by — verifier must not require it."""
    for module_name, class_name, has_pb, category in SCHEMA_MANIFEST:
        if category != "frontmatter":
            continue
        assert has_pb is False
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        # Sanity: confirm the schema really has no produced_by field on
        # disk so this isn't testing a manifest fiction.
        assert "produced_by" not in cls.model_fields
        ok, reason = _verify_one_schema(module_name, class_name, has_pb)
        assert ok, f"{class_name} failed without produced_by check: {reason}"


def test_verify_schemas_skips_produced_by_check_for_declaration() -> None:
    """Declaration schemas have no top-level produced_by either."""
    for module_name, class_name, has_pb, category in SCHEMA_MANIFEST:
        if category != "declaration":
            continue
        assert has_pb is False
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        assert "produced_by" not in cls.model_fields


def test_verify_schemas_validates_json_schema_output() -> None:
    """Each model_json_schema() output must round-trip through JSON."""
    for module_name, class_name, _, _ in SCHEMA_MANIFEST:
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        schema = cls.model_json_schema()
        assert isinstance(schema, dict)
        # Round-trip — TypeError or ValueError here means a non-
        # serialisable default leaked in.
        round_tripped = json.loads(json.dumps(schema))
        assert round_tripped == schema


def test_verify_schemas_checks_real_schema_versions_are_one_dot_zero() -> None:
    """Every artifact schema's SCHEMA_VERSION ClassVar is exactly '1.0.0'."""
    for module_name, class_name, _, _ in SCHEMA_MANIFEST:
        mod = importlib.import_module(module_name)
        cls = getattr(mod, class_name)
        assert cls.SCHEMA_VERSION == "1.0.0"


# ─── Schema verifier — failure modes via fake modules ──────────────────


def _install_fake_schema(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    cls: type[BaseModel],
    class_attr: str,
) -> None:
    """Inject ``cls`` as ``module_name.<class_attr>`` for the test."""
    fake_mod = types.ModuleType(module_name)
    setattr(fake_mod, class_attr, cls)
    monkeypatch.setitem(sys.modules, module_name, fake_mod)


def test_verify_schemas_checks_schema_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Wrong SCHEMA_VERSION → ✗ and exit 1, with reason on the report line."""

    class WrongVersion(BaseModel):
        SCHEMA_VERSION: ClassVar[str] = "9.9.9"

    _install_fake_schema(
        monkeypatch, "fake_wrong_version", WrongVersion, "WrongVersion"
    )
    custom = (
        ("fake_wrong_version", "WrongVersion", False, "pipeline"),
    )
    monkeypatch.setattr(verify_module, "SCHEMA_MANIFEST", custom)
    rc = _verify_schemas()
    out = capsys.readouterr().out
    assert rc == 1
    assert "✗" in out
    assert "wrong_schema_version" in out


def test_verify_schemas_checks_produced_by_type_when_required(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """produced_by typed as str (not RoleEnum) → ✗ wrong_produced_by_type."""

    class WrongProducedBy(BaseModel):
        SCHEMA_VERSION: ClassVar[str] = "1.0.0"
        produced_by: str = "OPERATOR"

    _install_fake_schema(
        monkeypatch, "fake_wrong_pb", WrongProducedBy, "WrongProducedBy"
    )
    custom = (("fake_wrong_pb", "WrongProducedBy", True, "pipeline"),)
    monkeypatch.setattr(verify_module, "SCHEMA_MANIFEST", custom)
    rc = _verify_schemas()
    out = capsys.readouterr().out
    assert rc == 1
    assert "wrong_produced_by_type" in out


def test_verify_schemas_checks_produced_by_field_exists_when_required(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """has_produced_by=True but field absent → ✗ missing_produced_by."""

    class NoProducedBy(BaseModel):
        SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    _install_fake_schema(
        monkeypatch, "fake_no_pb", NoProducedBy, "NoProducedBy"
    )
    custom = (("fake_no_pb", "NoProducedBy", True, "pipeline"),)
    monkeypatch.setattr(verify_module, "SCHEMA_MANIFEST", custom)
    rc = _verify_schemas()
    out = capsys.readouterr().out
    assert rc == 1
    assert "missing_produced_by" in out


def test_verify_schemas_reports_import_error_on_missing_module(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Module path doesn't import → ✗ import_error."""
    custom = (("schemas.does_not_exist", "Ghost", False, "pipeline"),)
    monkeypatch.setattr(verify_module, "SCHEMA_MANIFEST", custom)
    rc = _verify_schemas()
    out = capsys.readouterr().out
    assert rc == 1
    assert "import_error" in out


def test_verify_schemas_reports_missing_class_when_attr_absent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Module imports but class name not present → ✗ missing_class."""

    class Present(BaseModel):
        SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    _install_fake_schema(
        monkeypatch, "fake_present", Present, "Present"
    )
    custom = (("fake_present", "Absent", False, "pipeline"),)
    monkeypatch.setattr(verify_module, "SCHEMA_MANIFEST", custom)
    rc = _verify_schemas()
    out = capsys.readouterr().out
    assert rc == 1
    assert "missing_class" in out


def test_verify_schemas_failed_message_when_any_invalid(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Any invalid entry → 'FAILED:' message and exit 1."""

    class Bad(BaseModel):
        SCHEMA_VERSION: ClassVar[str] = "0.0.0"

    _install_fake_schema(monkeypatch, "fake_bad", Bad, "Bad")
    custom = (("fake_bad", "Bad", False, "pipeline"),)
    monkeypatch.setattr(verify_module, "SCHEMA_MANIFEST", custom)
    rc = _verify_schemas()
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAILED" in out
    assert "PASSED." not in out


def test_verify_schemas_summary_counts_match_partial_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    """Mixed manifest (one valid, one invalid) → 1 of 2 valid; exit 1."""

    class Good(BaseModel):
        SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    class Stale(BaseModel):
        SCHEMA_VERSION: ClassVar[str] = "0.0.0"

    _install_fake_schema(monkeypatch, "fake_good", Good, "Good")
    _install_fake_schema(monkeypatch, "fake_stale", Stale, "Stale")
    custom = (
        ("fake_good", "Good", False, "pipeline"),
        ("fake_stale", "Stale", False, "pipeline"),
    )
    monkeypatch.setattr(verify_module, "SCHEMA_MANIFEST", custom)
    rc = _verify_schemas()
    out = capsys.readouterr().out
    assert rc == 1
    assert "Summary: 1 of 2 schemas valid." in out


def test_verify_one_schema_returns_ok_for_real_pipeline_schema() -> None:
    """Direct unit test of the per-schema helper against a real schema."""
    ok, reason = _verify_one_schema("schemas.raw_input", "RawInput", True)
    assert ok is True
    assert reason is None


def test_verify_one_schema_returns_ok_for_real_frontmatter_schema() -> None:
    ok, reason = _verify_one_schema(
        "schemas.skill_frontmatter", "SkillFrontmatter", False,
    )
    assert ok is True
    assert reason is None


# ─── cmd_verify dispatcher — schemas + combined modes ──────────────────


def test_cmd_verify_with_schemas_flag_dispatches_to_verify_schemas() -> None:
    """cmd_verify(--schemas) → calls _verify_schemas exactly once."""
    with patch.object(verify_module, "_verify_schemas", return_value=0) as spy:
        rc = cmd_verify(_ns(layout=False, schemas=True))
    spy.assert_called_once()
    assert rc == 0


def test_cmd_verify_with_both_flags_runs_both(
    cee_root: dict[str, Path],
) -> None:
    """Both flags set → both verifiers run, both invoked exactly once."""
    with (
        patch.object(verify_module, "_verify_layout", return_value=0) as layout_spy,
        patch.object(verify_module, "_verify_schemas", return_value=0) as schemas_spy,
    ):
        rc = cmd_verify(_ns(layout=True, schemas=True))
    layout_spy.assert_called_once()
    schemas_spy.assert_called_once()
    assert rc == 0


def test_cmd_verify_returns_max_exit_code_when_both_flags_one_fails() -> None:
    """If one mode fails, the worst exit code is returned."""
    with (
        patch.object(verify_module, "_verify_layout", return_value=0),
        patch.object(verify_module, "_verify_schemas", return_value=1),
    ):
        rc = cmd_verify(_ns(layout=True, schemas=True))
    assert rc == 1


def test_cmd_verify_returns_max_exit_code_when_layout_fails() -> None:
    with (
        patch.object(verify_module, "_verify_layout", return_value=1),
        patch.object(verify_module, "_verify_schemas", return_value=0),
    ):
        rc = cmd_verify(_ns(layout=True, schemas=True))
    assert rc == 1


def test_cmd_verify_with_schemas_only_does_not_invoke_layout() -> None:
    """--schemas alone must not run the layout verifier."""
    with (
        patch.object(verify_module, "_verify_layout", return_value=0) as layout_spy,
        patch.object(verify_module, "_verify_schemas", return_value=0),
    ):
        cmd_verify(_ns(layout=False, schemas=True))
    layout_spy.assert_not_called()


def test_cmd_verify_with_layout_only_does_not_invoke_schemas() -> None:
    """--layout alone must not run the schemas verifier."""
    with (
        patch.object(verify_module, "_verify_layout", return_value=0),
        patch.object(verify_module, "_verify_schemas", return_value=0) as schemas_spy,
    ):
        cmd_verify(_ns(layout=True, schemas=False))
    schemas_spy.assert_not_called()
