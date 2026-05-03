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
    _OBSIDIAN_VERIFY_HINTS,
    SCHEMA_MANIFEST,
    _is_ok,
    _render_item,
    _shorten_path,
    _verify_layout,
    _verify_obsidian,
    _verify_one_schema,
    _verify_schemas,
    cmd_verify,
)
from persistence.audit import scaffold_audit_logs
from persistence.obsidian_writer import scaffold_obsidian
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


def _ns(
    layout: bool = True,
    schemas: bool = False,
    boot: bool = False,
    bible: bool = False,
    obsidian: bool = False,
) -> argparse.Namespace:
    """Argparse Namespace stand-in matching the verify subparser shape."""
    return argparse.Namespace(
        layout=layout,
        schemas=schemas,
        boot=boot,
        bible=bible,
        obsidian=obsidian,
        command="verify",
    )


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
    rc = cmd_verify(
        _ns(
            layout=False, schemas=False, boot=False, bible=False, obsidian=False,
        )
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert "Specify a verify mode" in captured.err
    # The hint must mention every currently-shipping mode.
    assert "--layout" in captured.err
    assert "--schemas" in captured.err
    assert "--boot" in captured.err
    assert "--bible" in captured.err
    assert "--obsidian" in captured.err
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
    """The 20 real schemas on disk must all validate cleanly."""
    assert _verify_schemas() == 0


def test_verify_schemas_walks_all_20_schemas(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Bible 04 §6.1 + 04 §5.5 + 04 §5.2 + 10 §6.3 + 11 §6.2 + Phase 3
    T2 (PromotionQueue) + T6 (RedactionLog) + T8 (Confirmation +
    ConfirmationRequest) → 20 schemas total."""
    _verify_schemas()
    out = capsys.readouterr().out
    assert "20 of 20" in out


def test_verify_schemas_categorizes_all_seven_categories(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """All seven category headings appear with correct counts."""
    _verify_schemas()
    out = capsys.readouterr().out
    assert "Pipeline artifact schemas (10):" in out
    assert "Frontmatter schemas (2):" in out
    assert "Declaration schemas (2):" in out
    assert "Bible sync state schemas (1):" in out
    assert "User config schemas (1):" in out
    assert "Promotion queue schemas (1):" in out
    assert "Safety gate schemas (3):" in out


def test_verify_schemas_summary_format(capsys: pytest.CaptureFixture[str]) -> None:
    _verify_schemas()
    out = capsys.readouterr().out
    assert "Summary: 20 of 20 schemas valid." in out


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


def test_schema_manifest_count_is_20() -> None:
    assert len(SCHEMA_MANIFEST) == 20


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


def test_schema_manifest_user_config_count_is_1() -> None:
    user_config = [e for e in SCHEMA_MANIFEST if e[3] == "user_config"]
    assert len(user_config) == 1


def test_schema_manifest_pipeline_entries_have_produced_by() -> None:
    """has_produced_by must be True for every pipeline entry."""
    for _, _, has_pb, category in SCHEMA_MANIFEST:
        if category == "pipeline":
            assert has_pb is True


def test_schema_manifest_non_pipeline_entries_have_no_produced_by() -> None:
    """Frontmatter, declaration, and user_config schemas must not declare produced_by."""
    for _, _, has_pb, category in SCHEMA_MANIFEST:
        if category in {"frontmatter", "declaration", "user_config"}:
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


# ─── _verify_boot (Phase 2 task 9) ─────────────────────────────────────
#
# Tests mock the single ``_run_boot_sequence`` seam in ``verify_module``
# and supply canned BootResult / BootStepResult instances. This isolates
# the renderer + exit-code logic from the full T8 sequencer machinery
# (which has its own 59-test unit suite). T8's contract: run() returns
# BootResult; never raises BootError. T9's _verify_boot reads result.ok
# directly and translates to exit codes.


from boot.sequencer import BootResult, BootStepResult  # noqa: E402
from cli.commands.verify import (  # noqa: E402
    _BOOT_HALT_HINTS,
    _hint_for_halt,
    _run_boot_sequence,
    _verify_boot,
)
from errors import (  # noqa: E402
    BootBibleSyncError,
    BootConsistencyError,
    BootEnvironmentError,
    BootError,
    BootRegistryError,
    BootRunIndexError,
    BootSchemaError,
)


def _step(
    name: str, ok: bool = True, summary: str = "ok", duration_ms: int = 1,
) -> BootStepResult:
    return BootStepResult(
        step=name, ok=ok, duration_ms=duration_ms, summary=summary, payload={}
    )


def _ok_boot_result(total_ms: int = 75) -> BootResult:
    return BootResult(
        ok=True,
        steps=tuple(_step(s, summary=f"{s} OK") for s in (
            "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"
        )),
        halt_step=None,
        halt_error=None,
        warnings=(),
        total_duration_ms=total_ms,
    )


def _halt_boot_result(
    *, halt_step: str, halt_error: BootError, completed: tuple[str, ...] = ("B1",),
) -> BootResult:
    """Build a BootResult that halted at ``halt_step``.

    ``completed`` lists the steps that ran successfully before the halt;
    the failing step is added as ok=False at the end.
    """
    steps = [_step(s) for s in completed]
    steps.append(_step(halt_step, ok=False, summary=f"{halt_step} halted"))
    return BootResult(
        ok=False,
        steps=tuple(steps),
        halt_step=halt_step,
        halt_error=halt_error,
        warnings=(),
        total_duration_ms=100,
    )


def test_verify_boot_returns_zero_on_happy_result() -> None:
    """All 9 steps succeed → _verify_boot returns 0."""
    with patch.object(
        verify_module, "_run_boot_sequence", return_value=_ok_boot_result()
    ):
        rc = _verify_boot()
    assert rc == 0


def test_verify_boot_stdout_lists_all_nine_steps_on_happy_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every B1-B9 step appears with a ✓ mark."""
    with patch.object(
        verify_module, "_run_boot_sequence", return_value=_ok_boot_result()
    ):
        _verify_boot()
    out = capsys.readouterr().out
    for step in ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"):
        assert step in out, f"missing step {step} in stdout"
    # ✓ mark must appear at least once per step.
    assert out.count("✓") >= 9


def test_verify_boot_stdout_includes_summary_and_passed_on_happy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch.object(
        verify_module, "_run_boot_sequence", return_value=_ok_boot_result()
    ):
        _verify_boot()
    out = capsys.readouterr().out
    assert "Summary: 9 of 9 steps passed." in out
    assert "PASSED." in out


def test_verify_boot_returns_one_on_halt_at_b1() -> None:
    halt = _halt_boot_result(
        halt_step="B1",
        halt_error=BootEnvironmentError(
            reason="config missing", kind="config_invalid"
        ),
        completed=(),
    )
    with patch.object(verify_module, "_run_boot_sequence", return_value=halt):
        rc = _verify_boot()
    assert rc == 1


def test_verify_boot_stderr_includes_halt_class_and_kind_on_halt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    halt = _halt_boot_result(
        halt_step="B1",
        halt_error=BootEnvironmentError(
            reason="too old", kind="python_version"
        ),
        completed=(),
    )
    with patch.object(verify_module, "_run_boot_sequence", return_value=halt):
        _verify_boot()
    err = capsys.readouterr().err
    assert "BOOT HALT [B1]" in err
    assert "BootEnvironmentError" in err
    assert "kind=python_version" in err


def test_verify_boot_stderr_includes_remediation_hint_for_credentials_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The most realistic current-state halt — credentials_missing at B2."""
    halt = _halt_boot_result(
        halt_step="B2",
        halt_error=BootBibleSyncError(
            kind="credentials_missing",
            reason="no [anthropic] api_key",
        ),
    )
    with patch.object(verify_module, "_run_boot_sequence", return_value=halt):
        rc = _verify_boot()
    err = capsys.readouterr().err
    assert rc == 1
    assert "credentials_missing" in err
    assert "Hint:" in err
    assert "~/.cee/credentials.toml" in err


def test_verify_boot_stderr_includes_remediation_hint_for_consistency_drift(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """BootConsistencyError uses the (class, None) fallback lookup."""
    halt = _halt_boot_result(
        halt_step="B3",
        halt_error=BootConsistencyError(drifts=[]),
        completed=("B1", "B2"),
    )
    with patch.object(verify_module, "_run_boot_sequence", return_value=halt):
        rc = _verify_boot()
    err = capsys.readouterr().err
    assert rc == 1
    assert "BootConsistencyError" in err
    assert "Hint:" in err
    assert "enum drift" in err.lower()


def test_verify_boot_stdout_lists_partial_steps_on_halt(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """On halt at B5, only B1-B5 (with B5 failed) appear in stdout.

    Match against the per-step line pattern (``  <mark> Bx  <label>``)
    so the literal "B1–B9" in the section header doesn't confuse the
    substring check.
    """
    halt = _halt_boot_result(
        halt_step="B5",
        halt_error=BootRegistryError(reason="permission denied", kind="agent"),
        completed=("B1", "B2", "B3", "B4"),
    )
    with patch.object(verify_module, "_run_boot_sequence", return_value=halt):
        _verify_boot()
    out = capsys.readouterr().out
    for step in ("B1", "B2", "B3", "B4"):
        assert f"✓ {step}" in out, f"missing successful {step} line"
    assert "✗ B5" in out, "missing failed B5 line"
    for step in ("B6", "B7", "B8", "B9"):
        assert f"✓ {step}" not in out
        assert f"✗ {step}" not in out
    assert "halted at B5" in out


def test_verify_boot_renders_warnings_when_present(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B8 best-effort warnings appear in the report even on ok=True."""
    result = BootResult(
        ok=True,
        steps=tuple(_step(s) for s in (
            "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"
        )),
        halt_step=None,
        halt_error=None,
        warnings=(
            "B8: promotion_queue.json exists but writer is pending",
        ),
        total_duration_ms=80,
    )
    with patch.object(verify_module, "_run_boot_sequence", return_value=result):
        rc = _verify_boot()
    out = capsys.readouterr().out
    assert rc == 0
    assert "Warnings (1):" in out
    assert "promotion_queue.json" in out
    assert "PASSED." in out


def test_verify_boot_unknown_halt_class_falls_back_to_generic_hint() -> None:
    """A BootError subclass not in the hint table → fallback string."""

    class _UnknownBootError(BootError):
        def __init__(self) -> None:
            super().__init__(step="B7", reason="something exotic")

    hint = _hint_for_halt(_UnknownBootError())
    assert "operator" in hint
    assert "boot.log" in hint


def test_cmd_verify_with_boot_flag_dispatches_to_verify_boot() -> None:
    """cmd_verify(--boot) calls _verify_boot exactly once."""
    with patch.object(verify_module, "_verify_boot", return_value=0) as spy:
        rc = cmd_verify(_ns(layout=False, schemas=False, boot=True))
    spy.assert_called_once()
    assert rc == 0


def test_cmd_verify_with_boot_and_layout_runs_both_max_exit_code(
    cee_root: dict[str, Path],
) -> None:
    """--boot --layout: both run; exit = max(layout_rc, boot_rc)."""
    with (
        patch.object(verify_module, "_verify_layout", return_value=0) as layout_spy,
        patch.object(verify_module, "_verify_boot", return_value=1) as boot_spy,
    ):
        rc = cmd_verify(_ns(layout=True, schemas=False, boot=True))
    layout_spy.assert_called_once()
    boot_spy.assert_called_once()
    assert rc == 1  # max(0, 1)


# ─── _verify_bible (Phase 2 task 10) ───────────────────────────────────
#
# Tests mock the two ``_run_*_check`` seams in ``verify_module`` and
# supply canned ConsistencyReport / DriftReport instances (or have the
# drift seam raise BootBibleSyncError). This isolates the renderer +
# exit-code logic from the full T5 / T6 backend machinery (each of
# which has its own unit suite).


from boot.bible_sync import DriftReport  # noqa: E402
from boot.consistency import ConsistencyReport, DriftRecord  # noqa: E402
from cli.commands.verify import (  # noqa: E402
    _BIBLE_DRIFT_HINTS,
    _run_consistency_check,
    _run_drift_check,
    _verify_bible,
)


def _ok_consistency(enums: int = 13) -> ConsistencyReport:
    return ConsistencyReport(ok=True, enums_checked=enums, drifts=())


def _drift_consistency(*drifts: DriftRecord) -> ConsistencyReport:
    return ConsistencyReport(
        ok=False, enums_checked=13, drifts=tuple(drifts)
    )


def _empty_drift_report(in_sync_count: int = 24) -> DriftReport:
    return DriftReport(
        in_sync=tuple(f"{i:02d}_p" for i in range(in_sync_count)),
        notion_newer=(),
        mirror_modified=(),
        orphan=(),
        missing_from_meta=(),
    )


def test_verify_bible_returns_zero_when_both_checks_pass() -> None:
    """Both subsections clean → exit 0."""
    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_ok_consistency(),
        ),
        patch.object(
            verify_module, "_run_drift_check",
            return_value=_empty_drift_report(),
        ),
    ):
        rc = _verify_bible()
    assert rc == 0


def test_verify_bible_stdout_shows_both_sections_on_happy_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_ok_consistency(),
        ),
        patch.object(
            verify_module, "_run_drift_check",
            return_value=_empty_drift_report(),
        ),
    ):
        _verify_bible()
    out = capsys.readouterr().out
    assert "Bible consistency" in out
    assert "Bible drift" in out
    assert "PASSED." in out


def test_verify_bible_drift_section_shows_all_five_categories(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every DriftReport category appears with a count, even at 0."""
    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_ok_consistency(),
        ),
        patch.object(
            verify_module, "_run_drift_check",
            return_value=_empty_drift_report(),
        ),
    ):
        _verify_bible()
    out = capsys.readouterr().out
    for cat in (
        "in_sync", "notion_newer", "mirror_modified",
        "orphan", "missing_from_meta",
    ):
        assert cat in out, f"missing drift category {cat} in stdout"


def test_verify_bible_returns_one_on_consistency_drift(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """ConsistencyReport with ≥1 drift → exit 1, stderr hint emitted."""
    drift = DriftRecord(
        enum_name="RoleEnum",
        drift_kind="bible_canonical",
        code_values=frozenset({"A"}),
        bible_values=frozenset({"B"}),
        bible_section="bible 02 §4.1",
        detail="code values differ from bible canonical",
    )
    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_drift_consistency(drift),
        ),
        patch.object(
            verify_module, "_run_drift_check",
            return_value=_empty_drift_report(),
        ),
    ):
        rc = _verify_bible()
    captured = capsys.readouterr()
    assert rc == 1
    assert "RoleEnum" in captured.out
    assert "BIBLE HALT [consistency]" in captured.err
    assert "Hint:" in captured.err
    assert "enum drift" in captured.err.lower()


def _drift_with(**categories: tuple[str, ...]) -> DriftReport:
    """Build a DriftReport with selected categories populated."""
    base = {
        "in_sync": (), "notion_newer": (), "mirror_modified": (),
        "orphan": (), "missing_from_meta": (),
    }
    base.update(categories)
    return DriftReport(**base)  # type: ignore[arg-type]


def test_verify_bible_returns_one_on_notion_newer_pages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_ok_consistency(),
        ),
        patch.object(
            verify_module, "_run_drift_check",
            return_value=_drift_with(notion_newer=("04_database",)),
        ),
    ):
        rc = _verify_bible()
    captured = capsys.readouterr()
    assert rc == 1
    assert "BIBLE DRIFT notion_newer" in captured.err
    assert "cee sync-bible" in captured.err
    assert "04_database" in captured.out


def test_verify_bible_returns_one_on_mirror_modified_pages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_ok_consistency(),
        ),
        patch.object(
            verify_module, "_run_drift_check",
            return_value=_drift_with(mirror_modified=("00_vision",)),
        ),
    ):
        rc = _verify_bible()
    captured = capsys.readouterr()
    assert rc == 1
    assert "BIBLE DRIFT mirror_modified" in captured.err
    assert "review local edits" in captured.err.lower()


def test_verify_bible_returns_one_on_orphan_pages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_ok_consistency(),
        ),
        patch.object(
            verify_module, "_run_drift_check",
            return_value=_drift_with(orphan=("99_scratch",)),
        ),
    ):
        rc = _verify_bible()
    captured = capsys.readouterr()
    assert rc == 1
    assert "BIBLE DRIFT orphan" in captured.err
    assert "remove from" in captured.err.lower()


def test_verify_bible_returns_one_on_missing_from_meta_pages(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_ok_consistency(),
        ),
        patch.object(
            verify_module, "_run_drift_check",
            return_value=_drift_with(missing_from_meta=("23_new",)),
        ),
    ):
        rc = _verify_bible()
    captured = capsys.readouterr()
    assert rc == 1
    assert "BIBLE DRIFT missing_from_meta" in captured.err
    assert "cee sync-bible" in captured.err


def test_verify_bible_handles_check_drift_credentials_missing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """check_drift raises BootBibleSyncError → caught, rendered as halt."""
    def raising(**_: object) -> object:
        raise BootBibleSyncError(
            kind="credentials_missing",
            reason="no [anthropic] api_key",
        )

    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_ok_consistency(),
        ),
        patch.object(
            verify_module, "_run_drift_check", side_effect=raising,
        ),
    ):
        rc = _verify_bible()
    captured = capsys.readouterr()
    assert rc == 1
    # Drift section in stdout shows the unavailable line.
    assert "check unavailable" in captured.out
    assert "BootBibleSyncError" in captured.out
    # stderr block from _BOOT_HALT_HINTS reuse — same hint as T9 emits.
    assert "BIBLE HALT [drift]" in captured.err
    assert "credentials_missing" in captured.err
    assert "~/.cee/credentials.toml" in captured.err
    # Consistency section still ran and rendered.
    assert "Bible consistency" in captured.out


def test_verify_bible_consistency_clean_drift_dirty_exits_one() -> None:
    """Mixed: ok consistency + drifty drift → exit 1."""
    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_ok_consistency(),
        ),
        patch.object(
            verify_module, "_run_drift_check",
            return_value=_drift_with(notion_newer=("a", "b")),
        ),
    ):
        rc = _verify_bible()
    assert rc == 1


def test_verify_bible_consistency_dirty_drift_clean_exits_one() -> None:
    """Mixed: drifty consistency + clean drift → exit 1."""
    drift = DriftRecord(
        enum_name="TaskType", drift_kind="internal_schema",
        code_values=None, bible_values=None,
        bible_section="bible 08 §5.1",
        detail="Classification disagrees with RunSummary",
    )
    with (
        patch.object(
            verify_module, "_run_consistency_check",
            return_value=_drift_consistency(drift),
        ),
        patch.object(
            verify_module, "_run_drift_check",
            return_value=_empty_drift_report(),
        ),
    ):
        rc = _verify_bible()
    assert rc == 1


def test_cmd_verify_with_bible_flag_dispatches_to_verify_bible() -> None:
    """cmd_verify(--bible) calls _verify_bible exactly once."""
    with patch.object(verify_module, "_verify_bible", return_value=0) as spy:
        rc = cmd_verify(_ns(layout=False, schemas=False, boot=False, bible=True))
    spy.assert_called_once()
    assert rc == 0


def test_cmd_verify_with_bible_and_boot_runs_both_max_exit_code() -> None:
    """--bible --boot: both run; exit = max(boot_rc, bible_rc)."""
    with (
        patch.object(verify_module, "_verify_boot", return_value=0) as boot_spy,
        patch.object(verify_module, "_verify_bible", return_value=1) as bible_spy,
    ):
        rc = cmd_verify(_ns(layout=False, schemas=False, boot=True, bible=True))
    boot_spy.assert_called_once()
    bible_spy.assert_called_once()
    assert rc == 1  # max(0, 1)


# ─── Phase 3 task 9: --obsidian flag ───────────────────────────────────


# Per design proposal Path A (AB-approved): scaffold-existence checks
# only — no frontmatter walk, no --vault-path. The 13-path canonical
# Obsidian set is the same one ``--layout`` already walks (vault root +
# README.md + 5 content dirs + their 5 index.md stubs + _templates/),
# but reported under a dedicated heading with halt-on-vault-missing
# semantics + a 2-entry remediation hint table.


def test_verify_obsidian_returns_zero_when_all_present(
    cee_root: dict[str, Path],
) -> None:
    """Happy path on a fully-seeded vault → exit 0."""
    assert _verify_obsidian() == 0


def test_verify_obsidian_passed_message_when_all_present(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    _verify_obsidian()
    out = capsys.readouterr().out
    assert "PASSED." in out


def test_verify_obsidian_summary_shows_correct_counts(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """All 13 obsidian paths present → ``Summary: 13 of 13 paths present.``"""
    _verify_obsidian()
    out = capsys.readouterr().out
    assert "Summary: 13 of 13 paths present." in out


def test_verify_obsidian_returns_one_when_vault_root_missing(
    cee_root: dict[str, Path],
) -> None:
    """Vault root deleted → halt-on-vault-missing → exit 1."""
    shutil.rmtree(cee_root["obsidian_vault"])
    assert _verify_obsidian() == 1


def test_verify_obsidian_does_not_walk_when_vault_root_missing(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """Halt-on-vault-missing short-circuits — no spurious child reports.

    A naive walk under a missing root would emit 12 spurious "missing
    child" lines, obscuring the real failure. This test asserts the
    short-circuit behaviour: only the vault-root MISSING line appears,
    not children like ``runs/index.md`` or ``README.md``.
    """
    shutil.rmtree(cee_root["obsidian_vault"])
    _verify_obsidian()
    out = capsys.readouterr().out
    # The vault-root failure line must be present.
    assert "MISSING" in out
    # Spurious child reports must NOT appear (the verifier short-circuits
    # at the root check before walking the 12 children).
    assert "README.md" not in out
    assert "index.md" not in out
    assert "runs" not in out
    assert "skills" not in out
    assert "agents" not in out
    assert "_templates" not in out


def test_verify_obsidian_returns_one_when_runs_dir_missing(
    cee_root: dict[str, Path],
) -> None:
    shutil.rmtree(paths.OBSIDIAN_RUNS_DIR)
    assert _verify_obsidian() == 1


def test_verify_obsidian_returns_one_when_skills_dir_missing(
    cee_root: dict[str, Path],
) -> None:
    shutil.rmtree(paths.OBSIDIAN_SKILLS_DIR)
    assert _verify_obsidian() == 1


def test_verify_obsidian_returns_one_when_agents_dir_missing(
    cee_root: dict[str, Path],
) -> None:
    shutil.rmtree(paths.OBSIDIAN_AGENTS_DIR)
    assert _verify_obsidian() == 1


def test_verify_obsidian_returns_one_when_bible_dir_missing(
    cee_root: dict[str, Path],
) -> None:
    shutil.rmtree(paths.OBSIDIAN_BIBLE_DIR)
    assert _verify_obsidian() == 1


def test_verify_obsidian_returns_one_when_audit_dir_missing(
    cee_root: dict[str, Path],
) -> None:
    shutil.rmtree(paths.OBSIDIAN_AUDIT_DIR)
    assert _verify_obsidian() == 1


def test_verify_obsidian_returns_one_when_templates_dir_missing(
    cee_root: dict[str, Path],
) -> None:
    """``_templates/`` is required-and-empty per bible 13 §5.1."""
    paths.OBSIDIAN_TEMPLATES_DIR.rmdir()
    assert _verify_obsidian() == 1


def test_verify_obsidian_returns_one_when_readme_missing(
    cee_root: dict[str, Path],
) -> None:
    (paths.OBSIDIAN_VAULT / "README.md").unlink()
    assert _verify_obsidian() == 1


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
def test_verify_obsidian_returns_one_when_index_md_missing(
    cee_root: dict[str, Path], subdir_attr: str,
) -> None:
    """Each of the 5 vault content subdirs must have its index.md."""
    subdir = getattr(paths, subdir_attr)
    (subdir / "index.md").unlink()
    assert _verify_obsidian() == 1


def test_verify_obsidian_stdout_uses_check_marks_for_present(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    _verify_obsidian()
    out = capsys.readouterr().out
    assert "✓" in out  # U+2713
    # All present → no ✗ marks anywhere.
    assert "✗" not in out


def test_verify_obsidian_stderr_emits_scaffold_hint_on_failure(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """Drift (some scaffold child missing) → scaffold_incomplete hint on stderr."""
    (paths.OBSIDIAN_VAULT / "README.md").unlink()
    _verify_obsidian()
    err = capsys.readouterr().err
    assert "cee scaffold-obsidian" in err
    assert "scaffold_incomplete" in err
    # The hint text from the table appears verbatim.
    assert _OBSIDIAN_VERIFY_HINTS["scaffold_incomplete"] in err


def test_verify_obsidian_stderr_silent_on_success(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """Happy path emits nothing on stderr (the hint table is failure-only)."""
    _verify_obsidian()
    err = capsys.readouterr().err
    assert err == ""


def test_verify_obsidian_returns_one_when_wrong_type(
    cee_root: dict[str, Path], capsys: pytest.CaptureFixture[str],
) -> None:
    """A regular file occupying a directory slot is not 'present'."""
    shutil.rmtree(paths.OBSIDIAN_RUNS_DIR)
    paths.OBSIDIAN_RUNS_DIR.write_text("oops", encoding="utf-8")
    rc = _verify_obsidian()
    out = capsys.readouterr().out
    assert rc == 1
    assert "WRONG_TYPE" in out


# ─── cmd_verify dispatcher coverage for --obsidian ──────────────────────


def test_cmd_verify_with_obsidian_flag_dispatches_to_verify_obsidian(
    cee_root: dict[str, Path],
) -> None:
    """cmd_verify(--obsidian) calls _verify_obsidian exactly once."""
    with patch.object(
        verify_module, "_verify_obsidian", return_value=0,
    ) as spy:
        rc = cmd_verify(
            _ns(
                layout=False, schemas=False, boot=False, bible=False,
                obsidian=True,
            )
        )
    spy.assert_called_once()
    assert rc == 0


def test_cmd_verify_with_obsidian_and_layout_runs_both_max_exit_code(
    cee_root: dict[str, Path],
) -> None:
    """--layout --obsidian: both run; exit = max(layout_rc, obsidian_rc)."""
    with (
        patch.object(
            verify_module, "_verify_layout", return_value=0,
        ) as layout_spy,
        patch.object(
            verify_module, "_verify_obsidian", return_value=1,
        ) as obsidian_spy,
    ):
        rc = cmd_verify(
            _ns(
                layout=True, schemas=False, boot=False, bible=False,
                obsidian=True,
            )
        )
    layout_spy.assert_called_once()
    obsidian_spy.assert_called_once()
    assert rc == 1  # max(0, 1)
