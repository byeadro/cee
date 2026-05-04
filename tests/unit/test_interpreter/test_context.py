"""Tests for the interpreter's bible + recent-runs context loaders.

Verifies the two helpers the user-message builder consumes:

* :func:`_load_bible_context` reads ``bible/00`` + ``bible/01``,
  concatenates with delimiter headers. Hard precondition: both files
  must exist (bible 03 §5.2 Step 2).
* :func:`_load_recent_runs` walks ``paths.RUNS_DIR``, validates each
  child name against the canonical run_id pattern, reads
  ``intent.json``, extracts ``goal``. Silent skip on every failure
  mode. Sort descending by run_id.

Recent-runs loader is independent from ``boot/sequencer.py`` B7
which drifted from canon (downstream candidate #66).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import paths
from interpreter.interpreter import (
    _build_user_message,
    _format_recent_runs_block,
    _load_bible_context,
    _load_recent_runs,
)
from roles import RoleEnum
from schemas.raw_input import RawInput


# --------------------------------------------------------------------------- #
# Bible context loader                                                        #
# --------------------------------------------------------------------------- #


def test_bible_context_concatenates_both_files(tmp_path: Path) -> None:
    bible_dir = tmp_path / "bible"
    bible_dir.mkdir()
    (bible_dir / "00_project_vision.md").write_text("VISION\n", encoding="utf-8")
    (bible_dir / "01_real_problem_breakdown.md").write_text(
        "PROBLEM\n", encoding="utf-8"
    )

    out = _load_bible_context(bible_dir=bible_dir)

    assert "### bible/00_project_vision.md" in out
    assert "### bible/01_real_problem_breakdown.md" in out
    assert "VISION" in out
    assert "PROBLEM" in out
    assert out.index("VISION") < out.index("PROBLEM")


def test_bible_context_raises_when_file_missing(tmp_path: Path) -> None:
    bible_dir = tmp_path / "bible"
    bible_dir.mkdir()
    (bible_dir / "00_project_vision.md").write_text("VISION\n", encoding="utf-8")
    # bible/01_real_problem_breakdown.md absent on purpose

    with pytest.raises(FileNotFoundError):
        _load_bible_context(bible_dir=bible_dir)


def test_bible_context_uses_paths_bible_dir_by_default() -> None:
    out = _load_bible_context()
    assert "### bible/00_project_vision.md" in out
    assert "### bible/01_real_problem_breakdown.md" in out


# --------------------------------------------------------------------------- #
# Recent-runs loader                                                          #
# --------------------------------------------------------------------------- #


def _seed_run(runs_dir: Path, run_id: str, goal: str | None) -> None:
    """Create ``runs_dir/run_id/intent.json`` with the given goal."""
    d = runs_dir / run_id
    d.mkdir(parents=True)
    payload: dict = {} if goal is None else {"goal": goal}
    (d / "intent.json").write_text(json.dumps(payload), encoding="utf-8")


def test_recent_runs_empty_dir_returns_empty(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    assert _load_recent_runs(runs_dir=runs_dir) == []


def test_recent_runs_missing_dir_returns_empty(tmp_path: Path) -> None:
    runs_dir = tmp_path / "absent"
    assert _load_recent_runs(runs_dir=runs_dir) == []


def test_recent_runs_returns_all_when_under_limit(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    _seed_run(runs_dir, "20260501_120000_aaaaaaaa", "first goal")
    _seed_run(runs_dir, "20260502_130000_bbbbbbbb", "second goal")
    _seed_run(runs_dir, "20260503_140000_cccccccc", "third goal")

    out = _load_recent_runs(runs_dir=runs_dir)

    assert out == [
        ("20260503_140000_cccccccc", "third goal"),
        ("20260502_130000_bbbbbbbb", "second goal"),
        ("20260501_120000_aaaaaaaa", "first goal"),
    ]


def test_recent_runs_truncates_to_limit(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    # Seed 5 valid runs and apply limit=3.
    for index in range(5):
        run_id = f"2026050{index + 1}_120000_{'a' * 8}"
        _seed_run(runs_dir, run_id, f"goal {index}")

    out = _load_recent_runs(runs_dir=runs_dir, limit=3)

    assert len(out) == 3
    # Newest three (descending order).
    assert out[0][0] == "20260505_120000_aaaaaaaa"
    assert out[1][0] == "20260504_120000_aaaaaaaa"
    assert out[2][0] == "20260503_120000_aaaaaaaa"


def test_recent_runs_silently_skips_non_canonical_dir(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    _seed_run(runs_dir, "20260501_120000_aaaaaaaa", "valid goal")
    # B7-style legacy "run_*" prefix — non-canonical per bible 04 §4
    # Rule 3 (downstream candidate #66).
    _seed_run(runs_dir, "run_legacy_001", "legacy goal")
    # Random non-conforming directory.
    (runs_dir / "scratch").mkdir()

    out = _load_recent_runs(runs_dir=runs_dir)

    assert out == [("20260501_120000_aaaaaaaa", "valid goal")]


def test_recent_runs_silently_skips_missing_intent_file(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    # Canonical run_id directory but no intent.json inside.
    (runs_dir / "20260501_120000_aaaaaaaa").mkdir()
    _seed_run(runs_dir, "20260502_130000_bbbbbbbb", "valid goal")

    out = _load_recent_runs(runs_dir=runs_dir)

    assert out == [("20260502_130000_bbbbbbbb", "valid goal")]


def test_recent_runs_silently_skips_malformed_json(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    bad = runs_dir / "20260501_120000_aaaaaaaa"
    bad.mkdir()
    (bad / "intent.json").write_text("not json at all", encoding="utf-8")
    _seed_run(runs_dir, "20260502_130000_bbbbbbbb", "valid goal")

    out = _load_recent_runs(runs_dir=runs_dir)

    assert out == [("20260502_130000_bbbbbbbb", "valid goal")]


def test_recent_runs_silently_skips_missing_goal_field(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    _seed_run(runs_dir, "20260501_120000_aaaaaaaa", goal=None)
    _seed_run(runs_dir, "20260502_130000_bbbbbbbb", "valid goal")

    out = _load_recent_runs(runs_dir=runs_dir)

    assert out == [("20260502_130000_bbbbbbbb", "valid goal")]


def test_recent_runs_skips_golden_directory(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    (runs_dir / "golden").mkdir()
    _seed_run(runs_dir, "20260501_120000_aaaaaaaa", "valid goal")

    out = _load_recent_runs(runs_dir=runs_dir)

    assert out == [("20260501_120000_aaaaaaaa", "valid goal")]


# --------------------------------------------------------------------------- #
# Formatter + user-message builder                                            #
# --------------------------------------------------------------------------- #


def test_format_recent_runs_empty_section_sentinel() -> None:
    assert _format_recent_runs_block([]) == "(no recent runs)"


def test_format_recent_runs_renders_run_id_goal_lines() -> None:
    runs = [
        ("20260503_140000_cccccccc", "third goal"),
        ("20260502_130000_bbbbbbbb", "second goal"),
    ]
    out = _format_recent_runs_block(runs)
    assert (
        out == "20260503_140000_cccccccc: third goal\n"
        "20260502_130000_bbbbbbbb: second goal"
    )


def test_build_user_message_assembles_three_blocks() -> None:
    raw = RawInput(
        text="write me an RLS policy",
        timestamp="2026-05-04T13:00:00Z",
        source="cli",
        produced_by=RoleEnum.OPERATOR,
    )
    out = _build_user_message(
        raw,
        bible_ctx="### bible/00_project_vision.md\nVISION",
        run_ctx=[("20260503_140000_cccccccc", "third goal")],
    )

    # Three delimiter headers, in order, with RAW_INPUT: marker on its
    # own line and content on the line below.
    assert "## BIBLE_CONTEXT\n" in out
    assert "## RECENT_RUNS\n" in out
    assert "## RAW_INPUT:\nwrite me an RLS policy" in out
    assert out.index("## BIBLE_CONTEXT") < out.index("## RECENT_RUNS")
    assert out.index("## RECENT_RUNS") < out.index("## RAW_INPUT:")
