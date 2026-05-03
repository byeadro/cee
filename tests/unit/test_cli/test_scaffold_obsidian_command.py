"""Tests for ``cli/commands/scaffold_obsidian.py`` — ``cee scaffold-obsidian``.

Every test redirects ``paths.OBSIDIAN_*`` constants under ``tmp_path``
via ``monkeypatch``. None of these tests touch the real
``~/SecondBrain/cee/`` vault.

Phase 3 task 11 (Track C). Wraps Phase 1's
:func:`persistence.scaffold_obsidian` with operator-facing CLI plumbing.
These tests verify the wrapper behaviour (existence-snapshot pattern,
per-path render with +/✓/✗ markers, OSError catch + hint emission, exit
code semantics) but do NOT re-cover the underlying scaffold logic
(which has its own tests in
``tests/unit/test_persistence/test_obsidian_writer.py``).

The 13-path canonical manifest (bible 13 §5.1) is consumed verbatim
from T9's :func:`cli.commands.verify._obsidian_required` — drift
between verifier (T9) and scaffolder (T11) is structurally impossible.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

import paths
from cli.commands import scaffold_obsidian as scaffold_module
from cli.commands.scaffold_obsidian import (
    _SCAFFOLD_OBSIDIAN_HINTS,
    cmd_scaffold_obsidian,
)
from cli.commands.verify import _obsidian_required
from persistence import scaffold_obsidian


# ─── Fixture ────────────────────────────────────────────────────────────


@pytest.fixture
def obsidian_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every ``paths.OBSIDIAN_*`` constant under ``tmp_path``.

    Mirrors ``tests/unit/test_cli/test_verify_command.py:cee_root``
    pattern for Obsidian-only paths. Does NOT pre-seed via
    :func:`scaffold_obsidian` — fresh state is the default; tests
    that need a pre-seeded state call ``scaffold_obsidian()``
    explicitly.
    """
    vault = tmp_path / "SecondBrain" / "cee"
    monkeypatch.setattr(paths, "OBSIDIAN_VAULT", vault)
    monkeypatch.setattr(paths, "OBSIDIAN_RUNS_DIR", vault / "runs")
    monkeypatch.setattr(paths, "OBSIDIAN_SKILLS_DIR", vault / "skills")
    monkeypatch.setattr(paths, "OBSIDIAN_AGENTS_DIR", vault / "agents")
    monkeypatch.setattr(paths, "OBSIDIAN_BIBLE_DIR", vault / "bible")
    monkeypatch.setattr(paths, "OBSIDIAN_AUDIT_DIR", vault / "audit")
    monkeypatch.setattr(paths, "OBSIDIAN_TEMPLATES_DIR", vault / "_templates")
    return vault


def _ns() -> argparse.Namespace:
    """Argparse Namespace stand-in — ``scaffold-obsidian`` takes no flags."""
    return argparse.Namespace(command="scaffold-obsidian")


# ─── Happy path ─────────────────────────────────────────────────────────


def test_scaffold_obsidian_creates_full_scaffold_on_clean_state(
    obsidian_root: Path,
) -> None:
    """Fresh dir → exit 0, all 13 paths created."""
    rc = cmd_scaffold_obsidian(_ns())
    assert rc == 0


def test_scaffold_obsidian_passed_message_when_complete(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    cmd_scaffold_obsidian(_ns())
    out = capsys.readouterr().out
    assert "PASSED." in out


def test_scaffold_obsidian_summary_shows_created_count_on_fresh_state(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Fresh state → ``Summary: 13 created, 0 already present, 0 failed.``"""
    cmd_scaffold_obsidian(_ns())
    out = capsys.readouterr().out
    assert "Summary: 13 created, 0 already present, 0 failed." in out


def test_scaffold_obsidian_creates_all_13_canonical_paths_on_disk(
    obsidian_root: Path,
) -> None:
    """Post-call, every path in _obsidian_required() must exist."""
    cmd_scaffold_obsidian(_ns())
    for path, _kind in _obsidian_required():
        assert path.exists(), f"{path} missing after scaffold"


# ─── Idempotency ────────────────────────────────────────────────────────


def test_scaffold_obsidian_returns_zero_on_already_complete_scaffold(
    obsidian_root: Path,
) -> None:
    """Pre-scaffolded state → exit 0."""
    scaffold_obsidian()  # seed fully scaffolded state
    rc = cmd_scaffold_obsidian(_ns())
    assert rc == 0


def test_scaffold_obsidian_idempotent_second_call_creates_nothing(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Second invocation → 0 created, 13 already present."""
    cmd_scaffold_obsidian(_ns())  # first call: creates everything
    capsys.readouterr()  # discard first call's output
    cmd_scaffold_obsidian(_ns())  # second call: idempotency demo
    out = capsys.readouterr().out
    assert "Summary: 0 created, 13 already present, 0 failed." in out
    assert "PASSED." in out


# ─── Manual-edit preservation (bible 13 §EC3) ──────────────────────────


def test_scaffold_obsidian_preserves_existing_readme(
    obsidian_root: Path,
) -> None:
    """Pre-existing README.md content is never modified by scaffold."""
    paths.ensure_dir(paths.OBSIDIAN_VAULT)
    custom_readme = "OPERATOR-CUSTOM CONTENT\n"
    readme_path = paths.OBSIDIAN_VAULT / "README.md"
    readme_path.write_text(custom_readme, encoding="utf-8")

    cmd_scaffold_obsidian(_ns())

    assert readme_path.read_text(encoding="utf-8") == custom_readme


def test_scaffold_obsidian_preserves_existing_index_md(
    obsidian_root: Path,
) -> None:
    """Pre-existing index.md content is never modified by scaffold."""
    paths.ensure_dir(paths.OBSIDIAN_RUNS_DIR)
    custom_index = "OPERATOR-CUSTOM INDEX BODY\n"
    index_path = paths.OBSIDIAN_RUNS_DIR / "index.md"
    index_path.write_text(custom_index, encoding="utf-8")

    cmd_scaffold_obsidian(_ns())

    assert index_path.read_text(encoding="utf-8") == custom_index


# ─── Partial state ─────────────────────────────────────────────────────


def test_scaffold_obsidian_partial_complete_state_creates_only_missing(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Delete one dir from fully-scaffolded state → only that dir created."""
    scaffold_obsidian()  # full scaffold
    # Remove just runs/ (and its index.md)
    shutil.rmtree(paths.OBSIDIAN_RUNS_DIR)

    cmd_scaffold_obsidian(_ns())
    out = capsys.readouterr().out
    # 2 created (runs/ dir + runs/index.md), 11 already present, 0 failed.
    assert "Summary: 2 created, 11 already present, 0 failed." in out
    assert "PASSED." in out


# ─── Render markers ────────────────────────────────────────────────────


def test_scaffold_obsidian_render_lines_show_created_marker_for_new_paths(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Created paths render with ``+`` marker."""
    cmd_scaffold_obsidian(_ns())
    out = capsys.readouterr().out
    assert "+" in out
    assert "created" in out


def test_scaffold_obsidian_render_lines_show_check_marker_for_already_present(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Already-present paths render with ``✓`` marker on idempotent re-run."""
    cmd_scaffold_obsidian(_ns())  # first call
    capsys.readouterr()
    cmd_scaffold_obsidian(_ns())  # second call: all already-present
    out = capsys.readouterr().out
    assert "✓" in out  # U+2713
    assert "already present" in out
    # First call was capsys-discarded; second-call output has no ✗ or +.
    assert "✗" not in out
    assert "+" not in out


# ─── Stderr invariants ────────────────────────────────────────────────


def test_scaffold_obsidian_stderr_silent_on_success(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Happy path emits nothing on stderr (hint table is failure-only)."""
    cmd_scaffold_obsidian(_ns())
    err = capsys.readouterr().err
    assert err == ""


# ─── OSError handling ────────────────────────────────────────────────


def test_scaffold_obsidian_returns_one_on_oserror(
    obsidian_root: Path,
) -> None:
    """OSError from scaffold_obsidian → exit 1."""
    with patch.object(
        scaffold_module, "scaffold_obsidian",
        side_effect=OSError(13, "Permission denied"),
    ):
        rc = cmd_scaffold_obsidian(_ns())
    assert rc == 1


def test_scaffold_obsidian_stderr_emits_partial_failure_hint_on_oserror(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """OSError catch → partial_failure hint on stderr."""
    with patch.object(
        scaffold_module, "scaffold_obsidian",
        side_effect=OSError(13, "Permission denied"),
    ):
        cmd_scaffold_obsidian(_ns())
    err = capsys.readouterr().err
    assert "partial_failure" in err
    assert _SCAFFOLD_OBSIDIAN_HINTS["partial_failure"] in err


def test_scaffold_obsidian_stderr_includes_oserror_cause_line(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """OSError catch → stderr includes Cause: OSError <errno> <strerror>."""
    with patch.object(
        scaffold_module, "scaffold_obsidian",
        side_effect=OSError(13, "Permission denied"),
    ):
        cmd_scaffold_obsidian(_ns())
    err = capsys.readouterr().err
    assert "Cause:" in err
    assert "OSError" in err
    assert "13" in err
    assert "Permission denied" in err


def test_scaffold_obsidian_render_shows_failed_marker_for_uncreated_paths(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """When scaffold raises before any path created, all 13 render as ✗ FAILED."""
    with patch.object(
        scaffold_module, "scaffold_obsidian",
        side_effect=OSError(13, "Permission denied"),
    ):
        cmd_scaffold_obsidian(_ns())
    out = capsys.readouterr().out
    assert "✗" in out
    assert "FAILED" in out
    # All 13 paths failed since the helper aborted before creating any.
    assert "Summary: 0 created, 0 already present, 13 failed." in out


# ─── Walk order ────────────────────────────────────────────────────────


def test_scaffold_obsidian_walks_paths_in_obsidian_required_declaration_order(
    obsidian_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Render order matches _obsidian_required() declaration order.

    Locks T11's render sequence to T9's manifest source. Any drift in
    the verifier's enumeration would shift the scaffolder's output
    order in lockstep — there is no second source of truth.
    """
    cmd_scaffold_obsidian(_ns())
    out = capsys.readouterr().out

    # Find each manifest path's first occurrence in the output by its
    # short-path rendering. The kind annotations are unique enough
    # that path-name substrings work as ordering anchors.
    manifest = _obsidian_required()
    positions: list[int] = []
    for path, _kind in manifest:
        # Use the trailing path component for the search since
        # multiple paths share parent prefixes.
        anchor = path.name if path.name else "cee/"
        # The vault root path's name is "cee" — render it specially.
        if path == paths.OBSIDIAN_VAULT:
            anchor = "~/"  # vault root renders as "~/SecondBrain/cee/"
        # We just need positions to be monotonically increasing across
        # the manifest order; exact substring isn't critical as long as
        # each path's render line comes before the next's.
        # Strategy: search for each path's full short-path rendering.
        from cli.commands.verify import _shorten_path
        rendered = _shorten_path(path)
        pos = out.find(rendered)
        assert pos != -1, f"{rendered} missing from output"
        positions.append(pos)

    # Strictly monotonically increasing → declaration order preserved.
    for i in range(1, len(positions)):
        assert positions[i] > positions[i - 1], (
            f"order violation at index {i}: "
            f"{manifest[i - 1][0]} at {positions[i - 1]} > "
            f"{manifest[i][0]} at {positions[i]}"
        )


# ─── Direct dispatcher coverage ────────────────────────────────────────


def test_cmd_scaffold_obsidian_dispatcher_returns_zero_on_clean_state(
    obsidian_root: Path,
) -> None:
    """Direct call honours its int-return contract end-to-end."""
    rc = cmd_scaffold_obsidian(_ns())
    assert rc == 0
