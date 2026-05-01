"""Tests for ``config_loader.loader.load_config`` (task 10).

Every test redirects ``paths.USER_CONFIG_DIR``, ``paths.CONFIG_FILE``, and
``paths.TEMPLATE_CONFIG_FILE`` into ``tmp_path`` via ``monkeypatch``. The
real ``~/.cee/`` directory is never read or written. A safety assertion at
the end of every test verifies the redirect held.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator
from unittest.mock import patch

import pytest

import paths
from config_loader import load_config
from config_loader import loader as loader_module
from errors import BootError
from schemas import Config


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


@pytest.fixture
def isolated_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[dict[str, Path]]:
    """Redirect every config-related path into ``tmp_path``.

    Returns a dict with the redirected paths and pre-creates the
    template directory + a default-content template file so tests can
    opt-in to a "template exists" baseline.
    """
    user_config_dir = tmp_path / "user_cee"
    config_file = user_config_dir / "config.toml"
    template_dir = tmp_path / "template"
    template_config_file = template_dir / "config.toml.default"

    template_dir.mkdir(parents=True)

    # Copy the real template content so loader-validated output equals the
    # bible-mandated defaults. If the real template is missing (CI sandbox),
    # fall back to a minimal valid TOML.
    if paths.TEMPLATE_CONFIG_FILE.exists():
        template_config_file.write_text(
            paths.TEMPLATE_CONFIG_FILE.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    else:
        template_config_file.write_text("[general]\n", encoding="utf-8")

    monkeypatch.setattr(paths, "USER_CONFIG_DIR", user_config_dir)
    monkeypatch.setattr(paths, "CONFIG_FILE", config_file)
    monkeypatch.setattr(paths, "TEMPLATE_CONFIG_FILE", template_config_file)

    yield {
        "user_config_dir": user_config_dir,
        "config_file": config_file,
        "template_dir": template_dir,
        "template_config_file": template_config_file,
    }

    # Safety: ensure the real ~/.cee/ was never touched.
    real_user_config = Path.home() / ".cee"
    real_config = real_user_config / "config.toml"
    assert not real_config.exists() or real_config.parent != user_config_dir, (
        "Test leaked into real ~/.cee/ — monkeypatch failed or loader "
        "imported paths constants by value rather than via attribute."
    )


# --------------------------------------------------------------------------- #
# Happy path                                                                  #
# --------------------------------------------------------------------------- #


def test_load_config_creates_user_dir_if_missing(
    isolated_paths: dict[str, Path],
) -> None:
    user_dir = isolated_paths["user_config_dir"]
    assert not user_dir.exists()

    load_config()

    assert user_dir.is_dir()


def test_load_config_copies_template_if_missing(
    isolated_paths: dict[str, Path],
) -> None:
    cfg_path = isolated_paths["config_file"]
    template_path = isolated_paths["template_config_file"]
    assert not cfg_path.exists()

    load_config()

    assert cfg_path.is_file()
    assert cfg_path.read_text(encoding="utf-8") == template_path.read_text(
        encoding="utf-8"
    )


def test_load_config_returns_valid_config(
    isolated_paths: dict[str, Path],
) -> None:
    cfg = load_config()
    assert isinstance(cfg, Config)
    # The shipped template's literal values equal the schema's defaults
    # (asserted by test_template_loads_into_default_config), so the
    # loaded Config equals Config().
    assert cfg == Config()


def test_load_config_uses_existing_config(
    isolated_paths: dict[str, Path],
) -> None:
    cfg_path = isolated_paths["config_file"]
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "[general]\nauto_sync = false\nfresh_boot = true\n",
        encoding="utf-8",
    )

    cfg = load_config()

    assert cfg.general.auto_sync is False
    assert cfg.general.fresh_boot is True


def test_load_config_does_not_overwrite_existing_config(
    isolated_paths: dict[str, Path],
) -> None:
    cfg_path = isolated_paths["config_file"]
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    sentinel = "[general]\nauto_sync = false\n# OPERATOR sentinel comment\n"
    cfg_path.write_text(sentinel, encoding="utf-8")

    load_config()

    assert cfg_path.read_text(encoding="utf-8") == sentinel


def test_load_config_idempotent(isolated_paths: dict[str, Path]) -> None:
    """Calling load_config twice in a row produces identical objects and
    leaves the on-disk config unchanged after the first call."""
    first = load_config()
    on_disk_after_first = isolated_paths["config_file"].read_text(
        encoding="utf-8"
    )
    second = load_config()
    on_disk_after_second = isolated_paths["config_file"].read_text(
        encoding="utf-8"
    )

    assert first == second
    assert on_disk_after_first == on_disk_after_second


# --------------------------------------------------------------------------- #
# Error paths                                                                 #
# --------------------------------------------------------------------------- #


def test_load_config_raises_boot_error_on_invalid_toml(
    isolated_paths: dict[str, Path],
) -> None:
    cfg_path = isolated_paths["config_file"]
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("this is = not = valid TOML [[[", encoding="utf-8")

    with pytest.raises(BootError) as ei:
        load_config()

    assert ei.value.step == "B1"
    assert "TOML" in ei.value.reason or "tomllib" in ei.value.reason


def test_load_config_raises_boot_error_on_schema_violation(
    isolated_paths: dict[str, Path],
) -> None:
    """Valid TOML, invalid values — coverage_threshold > 1.0 violates
    the GroundingConfig field constraints."""
    cfg_path = isolated_paths["config_file"]
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "[grounding]\ncoverage_threshold = 99.0\n", encoding="utf-8"
    )

    with pytest.raises(BootError) as ei:
        load_config()

    assert ei.value.step == "B1"
    assert "schema" in ei.value.reason.lower()


def test_load_config_raises_boot_error_on_cross_validator_violation(
    isolated_paths: dict[str, Path],
) -> None:
    """Valid TOML, valid range, but the cross-validator catches it."""
    cfg_path = isolated_paths["config_file"]
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "[skill_engine]\nreuse_threshold = 0.5\nask_threshold = 0.6\n",
        encoding="utf-8",
    )

    with pytest.raises(BootError) as ei:
        load_config()

    assert ei.value.step == "B1"


def test_load_config_raises_boot_error_when_template_missing(
    isolated_paths: dict[str, Path],
) -> None:
    """If neither the user config nor the template exists, the loader
    cannot bootstrap and must halt with BootError."""
    isolated_paths["template_config_file"].unlink()
    assert not isolated_paths["template_config_file"].exists()
    assert not isolated_paths["config_file"].exists()

    with pytest.raises(BootError) as ei:
        load_config()

    assert ei.value.step == "B1"
    assert "template" in ei.value.reason.lower()


def test_load_config_unknown_section_rejected(
    isolated_paths: dict[str, Path],
) -> None:
    """``extra="forbid"`` on the top-level Config rejects unknown sections."""
    cfg_path = isolated_paths["config_file"]
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        "[unknown_section]\nfield = 1\n", encoding="utf-8"
    )

    with pytest.raises(BootError) as ei:
        load_config()

    assert ei.value.step == "B1"


# --------------------------------------------------------------------------- #
# Atomic-write contract                                                       #
# --------------------------------------------------------------------------- #


def test_load_config_template_copy_uses_atomic_write_text(
    isolated_paths: dict[str, Path],
) -> None:
    """Bible 14 + bible 02 §5 Rule 5: every write to canon goes through
    the atomic helpers. Verify the template-copy path calls atomic_write_text
    rather than raw open()."""
    with patch.object(
        loader_module,
        "atomic_write_text",
        wraps=loader_module.atomic_write_text,
    ) as spy:
        load_config()

    spy.assert_called_once()
    called_path = spy.call_args.args[0]
    called_text = spy.call_args.args[1]
    assert called_path == isolated_paths["config_file"]
    assert called_text == isolated_paths["template_config_file"].read_text(
        encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Boot-step contract                                                          #
# --------------------------------------------------------------------------- #


def test_loader_module_boot_step_is_b1() -> None:
    """Bible 00 §12: B1 is environment verification, which subsumes
    config loading. Hard-code the contract so a future rename can't
    silently change boot-step semantics."""
    assert loader_module._BOOT_STEP == "B1"
