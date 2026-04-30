"""Tests for the SkillFrontmatter schema."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import SkillFrontmatter


_BIBLE_PATH = Path.home() / "cee" / "bible" / "15_skill_file_structure.md"


def _valid_kwargs(**overrides: object) -> dict:
    base: dict = {
        "name": "read-codebase",
        "description": (
            "Reads a codebase and produces a structured summary of its "
            "architecture, conventions, and entry points."
        ),
        "version": "1.0.0",
        "triggers": ["read this codebase", "summarize the repo"],
        "inputs": ["filesystem_path"],
        "outputs": ["markdown_report"],
        "task_types_supported": ["ANALYZE", "RESEARCH"],
        "created_at": "2026-04-30T12:00:00Z",
        "created_by_run": "manual",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_skill_frontmatter_minimal_valid() -> None:
    obj = SkillFrontmatter(**_valid_kwargs())
    assert obj.name == "read-codebase"
    assert obj.version == "1.0.0"
    assert obj.posture_hints == []
    assert obj.domain is None
    assert obj.disabled is False
    assert obj.needs_review is False
    assert obj.grounding_required is False


def test_skill_frontmatter_full_valid() -> None:
    obj = SkillFrontmatter(
        name="read-codebase",
        description="Reads a codebase and summarizes it.",
        version="1.2.3",
        triggers=["read", "scan", "summarize the repo"],
        inputs=["filesystem_path"],
        outputs=["markdown_report"],
        task_types_supported=["ANALYZE", "RESEARCH"],
        created_at="2026-04-30T12:00:00Z",
        created_by_run="20260430_140000_a1b2c3d4",
        created_from_input="please read this codebase and summarize it",
        posture_hints=["primary", "specialist"],
        domain="code",
        sensitivity="medium",
        grounding_required=True,
        disabled=False,
        needs_review=True,
        deprecated_at="2026-12-31",
        replacement_slug="read-codebase-v2",
        notes="Initial seed Skill; replaced by v2 after Phase 2.",
    )
    assert obj.posture_hints == ["primary", "specialist"]
    assert obj.domain == "code"
    assert obj.replacement_slug == "read-codebase-v2"


@pytest.mark.parametrize(
    "missing_field",
    [
        "name",
        "description",
        "version",
        "triggers",
        "inputs",
        "outputs",
        "task_types_supported",
        "created_at",
        "created_by_run",
    ],
)
def test_skill_frontmatter_missing_required_field_raises(
    missing_field: str,
) -> None:
    kwargs = _valid_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        SkillFrontmatter(**kwargs)


def test_skill_frontmatter_extra_field_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        SkillFrontmatter(**kwargs)


def test_skill_frontmatter_string_whitespace_stripped() -> None:
    obj = SkillFrontmatter(**_valid_kwargs(description="  hello  "))
    assert obj.description == "hello"


def test_skill_frontmatter_schema_version_present() -> None:
    assert SkillFrontmatter.SCHEMA_VERSION == "1.0.0"


def test_skill_frontmatter_json_round_trip() -> None:
    original = SkillFrontmatter(**_valid_kwargs())
    payload = original.model_dump_json()
    restored = SkillFrontmatter.model_validate_json(payload)
    assert restored == original


def test_skill_frontmatter_dict_round_trip() -> None:
    original = SkillFrontmatter(**_valid_kwargs())
    payload = original.model_dump()
    restored = SkillFrontmatter.model_validate(payload)
    assert restored == original


def test_skill_frontmatter_field_order_stable() -> None:
    obj = SkillFrontmatter(**_valid_kwargs())
    expected_order = [
        "name",
        "description",
        "version",
        "triggers",
        "inputs",
        "outputs",
        "task_types_supported",
        "created_at",
        "created_by_run",
        "posture_hints",
        "domain",
        "created_from_input",
        "sensitivity",
        "grounding_required",
        "disabled",
        "needs_review",
        "deprecated_at",
        "replacement_slug",
        "notes",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific validators                                                   #
# --------------------------------------------------------------------------- #


def test_slug_must_be_kebab_case() -> None:
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(name="Read_Codebase"))
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(name="read codebase"))
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(name="r"))
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(name="1-fix"))
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(name="read-"))
    SkillFrontmatter(**_valid_kwargs(name="next-app-router-page"))
    SkillFrontmatter(**_valid_kwargs(name="write-rls-policies"))


def test_version_must_be_semver() -> None:
    SkillFrontmatter(**_valid_kwargs(version="1.0.0"))
    SkillFrontmatter(**_valid_kwargs(version="2.3.1"))
    SkillFrontmatter(**_valid_kwargs(version="10.20.30"))
    SkillFrontmatter(**_valid_kwargs(version="1.0.0-rc.1"))
    SkillFrontmatter(**_valid_kwargs(version="1.0.0+build.123"))

    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(version="1.0"))
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(version="v1.0.0"))
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(version="abc"))


@pytest.mark.parametrize(
    "task_type",
    [
        "BUILD",
        "ANALYZE",
        "DEBUG",
        "WRITE",
        "RESEARCH",
        "TRANSFORM",
        "DECIDE",
        "ORCHESTRATE",
    ],
)
def test_task_types_supported_must_be_subset_of_8(task_type: str) -> None:
    obj = SkillFrontmatter(**_valid_kwargs(task_types_supported=[task_type]))
    assert obj.task_types_supported == [task_type]


def test_task_types_supported_rejects_unknown_values() -> None:
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(task_types_supported=["FROBNICATE"]))
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(task_types_supported=["build"]))


def test_task_types_supported_min_one_max_eight() -> None:
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(task_types_supported=[]))
    # All 8 is fine.
    SkillFrontmatter(
        **_valid_kwargs(
            task_types_supported=[
                "BUILD",
                "ANALYZE",
                "DEBUG",
                "WRITE",
                "RESEARCH",
                "TRANSFORM",
                "DECIDE",
                "ORCHESTRATE",
            ]
        )
    )


def test_needs_review_default_false() -> None:
    obj = SkillFrontmatter(**_valid_kwargs())
    assert obj.needs_review is False


def test_triggers_min_one_max_ten() -> None:
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(triggers=[]))
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(triggers=["x"] * 11))


def test_trigger_length_constraints() -> None:
    # Each trigger 3-100 chars per bible 15 §5.2 table.
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(triggers=["ab"]))
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(triggers=["x" * 101]))


def test_run_provenance_requires_created_from_input() -> None:
    """Bible 15 §5.2: created_from_input is required when created_by_run
    is a run_id (rather than 'manual' or 'seed').
    """
    with pytest.raises(ValidationError, match="created_from_input"):
        SkillFrontmatter(
            **_valid_kwargs(
                created_by_run="20260430_140000_a1b2c3d4",
                created_from_input=None,
            )
        )
    # Manual provenance does not require created_from_input.
    SkillFrontmatter(
        **_valid_kwargs(created_by_run="manual", created_from_input=None)
    )
    # Seed provenance does not require created_from_input.
    SkillFrontmatter(
        **_valid_kwargs(created_by_run="seed", created_from_input=None)
    )


def test_created_by_run_invalid_values_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(created_by_run="auto"))
    with pytest.raises(ValidationError):
        SkillFrontmatter(
            **_valid_kwargs(created_by_run="2026-04-30_14_00_00_a1b2c3d4")
        )


def test_replacement_slug_must_be_kebab_case() -> None:
    with pytest.raises(ValidationError):
        SkillFrontmatter(**_valid_kwargs(replacement_slug="Bad_Slug"))


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_skill_frontmatter_field_set_matches_bible() -> None:
    """Bible 15 §5.2 enumerates the YAML frontmatter fields. The schema
    must include every field named in the ``REQUIRED FIELDS`` and
    ``OPTIONAL FIELDS`` blocks of the YAML literal.
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    text = _BIBLE_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"###\s*5\.2\s+Frontmatter schema.*?```yaml\s*(.*?)```",
        text,
        re.DOTALL,
    )
    assert section_match, "Could not locate §5.2 YAML block in bible 15"

    yaml_text = section_match.group(1)
    # Collect every line that looks like ``<field>:`` at column 0
    # (skipping list dashes and comments).
    field_pattern = re.compile(r"^([a-z_]+):", re.MULTILINE)
    bible_fields = set(field_pattern.findall(yaml_text))

    # The YAML literal uses the front-matter delimiter ``---`` which is
    # not a field; the regex naturally excludes it. Confirm we caught
    # the canonical anchor fields.
    assert "name" in bible_fields
    assert "task_types_supported" in bible_fields

    impl_fields = set(SkillFrontmatter.model_fields.keys())
    missing = bible_fields - impl_fields
    assert not missing, (
        f"SkillFrontmatter missing bible-required fields: {sorted(missing)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )
