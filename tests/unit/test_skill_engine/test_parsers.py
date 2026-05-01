"""Tests for ``skill_engine/parsers.py`` — the frontmatter parser.

Covers the contract laid out in bible 00 §12 B4 ("Skills with invalid
frontmatter are logged and skipped, not loaded") and bible 15 §5.2 (the
YAML-mapping-between-``---``-markers shape). The parser must:

- return the parsed mapping on success
- return ``None`` and log a WARNING for every documented failure mode
- treat genuinely empty frontmatter (``---\\n---``) as a valid empty
  mapping rather than a failure

``frontmatter.dumps`` is used in fixtures because it is the canonical
way to *write* the format the parser consumes — even though the parser
itself bypasses ``python-frontmatter`` (see ``parsers.py`` docstring for
why). Round-tripping fixture-write through the same library OPERATORs
will use to author Skills keeps the test corpus honest.
"""

from __future__ import annotations

import logging
from pathlib import Path

import frontmatter
import pytest

from skill_engine.parsers import parse_frontmatter


# ─── Helpers ────────────────────────────────────────────────────────────


def _write_skill_md(path: Path, metadata: dict, body: str = "") -> None:
    """Write a SKILL.md fixture with `metadata` as YAML frontmatter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    post = frontmatter.Post(content=body, **metadata)
    path.write_text(frontmatter.dumps(post), encoding="utf-8")


# ─── Happy path ─────────────────────────────────────────────────────────


def test_parse_frontmatter_returns_dict_for_valid_skill(tmp_path: Path) -> None:
    skill_md = tmp_path / "demo-skill" / "SKILL.md"
    metadata = {
        "name": "demo-skill",
        "version": "1.0.0",
        "description": "A demo skill for parser testing.",
    }
    _write_skill_md(skill_md, metadata, body="# Demo body\n")

    result = parse_frontmatter(skill_md)

    assert result == metadata


def test_parse_frontmatter_preserves_full_field_set(tmp_path: Path) -> None:
    """The parser does not drop or transform fields; it surfaces what
    YAML loaded. Schema validation belongs to the caller."""
    skill_md = tmp_path / "full" / "SKILL.md"
    metadata = {
        "name": "full",
        "version": "2.3.1",
        "description": "All fields populated.",
        "triggers": ["trigger one", "trigger two"],
        "inputs": ["input descriptor"],
        "outputs": ["output descriptor"],
        "task_types_supported": ["BUILD", "ANALYZE"],
        "created_at": "2026-05-01T00:00:00Z",
        "created_by_run": "manual",
        "posture_hints": ["primary"],
        "domain": "code",
        "sensitivity": "low",
        "grounding_required": False,
        "disabled": False,
        "needs_review": False,
        "notes": "free-form",
    }
    _write_skill_md(skill_md, metadata)

    result = parse_frontmatter(skill_md)

    assert result == metadata


# ─── Empty / minimal frontmatter (still valid) ──────────────────────────


def test_parse_frontmatter_returns_empty_dict_for_empty_block(
    tmp_path: Path,
) -> None:
    """``---\\n---`` is a valid (empty) YAML mapping per bible 15 §5.2's
    syntactic shape; schema rejection happens at the caller layer."""
    skill_md = tmp_path / "empty" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("---\n---\nbody\n", encoding="utf-8")

    result = parse_frontmatter(skill_md)

    assert result == {}


def test_parse_frontmatter_returns_empty_dict_for_comments_only_block(
    tmp_path: Path,
) -> None:
    """A YAML body with only comments loads to ``None``; we normalise to
    an empty mapping so the caller sees a uniform "empty" signal."""
    skill_md = tmp_path / "comments" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("---\n# only a comment\n---\nbody\n", encoding="utf-8")

    result = parse_frontmatter(skill_md)

    assert result == {}


# ─── Failure modes (return None + log) ──────────────────────────────────


def test_parse_frontmatter_returns_none_for_missing_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    missing = tmp_path / "nope" / "SKILL.md"

    with caplog.at_level(logging.WARNING, logger="skill_engine.parsers"):
        result = parse_frontmatter(missing)

    assert result is None
    assert any(
        "file not found" in rec.message and str(missing) in rec.message
        for rec in caplog.records
    )


def test_parse_frontmatter_returns_none_for_no_markers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    skill_md = tmp_path / "no-markers" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(
        "no frontmatter here, just a markdown body\n",
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="skill_engine.parsers"):
        result = parse_frontmatter(skill_md)

    assert result is None
    assert any(
        "no frontmatter markers" in rec.message and str(skill_md) in rec.message
        for rec in caplog.records
    )


def test_parse_frontmatter_returns_none_for_unclosed_markers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Opening ``---`` without a matching closing ``---`` is treated as
    "no frontmatter block" — the regex anchor fails to match."""
    skill_md = tmp_path / "unclosed" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("---\nname: foo\nno closing marker\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="skill_engine.parsers"):
        result = parse_frontmatter(skill_md)

    assert result is None
    assert any(
        "no frontmatter markers" in rec.message for rec in caplog.records
    )


def test_parse_frontmatter_returns_none_for_malformed_yaml(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    skill_md = tmp_path / "malformed" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    # Unclosed flow sequence — yaml.safe_load raises ParserError.
    skill_md.write_text("---\nname: [unclosed\n---\nbody\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="skill_engine.parsers"):
        result = parse_frontmatter(skill_md)

    assert result is None
    assert any("malformed YAML" in rec.message for rec in caplog.records)


def test_parse_frontmatter_returns_none_for_top_level_list(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    skill_md = tmp_path / "list" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("---\n- a\n- b\n---\nbody\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="skill_engine.parsers"):
        result = parse_frontmatter(skill_md)

    assert result is None
    assert any(
        "top-level mapping required" in rec.message and "list" in rec.message
        for rec in caplog.records
    )


def test_parse_frontmatter_returns_none_for_top_level_scalar(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    skill_md = tmp_path / "scalar" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("---\nplain string\n---\nbody\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="skill_engine.parsers"):
        result = parse_frontmatter(skill_md)

    assert result is None
    assert any(
        "top-level mapping required" in rec.message
        for rec in caplog.records
    )


# ─── Robustness ─────────────────────────────────────────────────────────


def test_parse_frontmatter_handles_crlf_line_endings(tmp_path: Path) -> None:
    skill_md = tmp_path / "crlf" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_bytes(b"---\r\nname: crlf\r\nversion: 1.0.0\r\n---\r\nbody\r\n")

    result = parse_frontmatter(skill_md)

    assert result == {"name": "crlf", "version": "1.0.0"}


def test_parse_frontmatter_handles_leading_whitespace(tmp_path: Path) -> None:
    """A blank line before the opening ``---`` is tolerated; bible 15
    §5.2 doesn't forbid it explicitly, and YAML/markdown editors often
    add one."""
    skill_md = tmp_path / "ws" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("\n---\nname: ws\n---\nbody\n", encoding="utf-8")

    result = parse_frontmatter(skill_md)

    assert result == {"name": "ws"}
