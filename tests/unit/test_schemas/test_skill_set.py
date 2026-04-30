"""Tests for the SkillSet schema."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import SkillRef, SkillSet


_BIBLE_PATH = Path.home() / "cee" / "bible" / "07_skill_system_design.md"


def _valid_skill_ref(
    slug: str = "read-codebase",
    score: float = 0.92,
    zone: str = "reuse",
    version: str = "1.0.0",
) -> dict:
    return {
        "slug": slug,
        "version": version,
        "path": f"~/cee/skills/{slug}/SKILL.md",
        "match_score": score,
        "match_zone": zone,
    }


def _valid_kwargs() -> dict:
    return {
        "skills": [SkillRef(**_valid_skill_ref())],
    }


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_skill_set_minimal_valid() -> None:
    obj = SkillSet()
    assert obj.skills == []
    assert obj.newly_generated == []
    assert obj.produced_by == "SKILL_ENGINE"


def test_skill_set_full_valid() -> None:
    obj = SkillSet(
        skills=[
            SkillRef(**_valid_skill_ref("read-codebase", 0.92, "reuse")),
            SkillRef(**_valid_skill_ref("write-tests", 0.50, "generate")),
        ],
        newly_generated=[
            SkillRef(
                **_valid_skill_ref(
                    slug="write-tests", score=0.50, zone="generate"
                )
            ),
        ],
        produced_by="SKILL_ENGINE",
    )
    assert len(obj.skills) == 2
    assert len(obj.newly_generated) == 1


def test_skill_set_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillSet(skills=[], unknown_field="x")


def test_skill_set_string_whitespace_stripped() -> None:
    obj = SkillSet(skills=[], produced_by="  SKILL_ENGINE  ")
    assert obj.produced_by == "SKILL_ENGINE"


def test_skill_set_schema_version_present() -> None:
    assert SkillSet.SCHEMA_VERSION == "1.0.0"
    assert SkillRef.SCHEMA_VERSION == "1.0.0"


def test_skill_set_json_round_trip() -> None:
    original = SkillSet(**_valid_kwargs())
    payload = original.model_dump_json()
    restored = SkillSet.model_validate_json(payload)
    assert restored == original


def test_skill_set_dict_round_trip() -> None:
    original = SkillSet(**_valid_kwargs())
    payload = original.model_dump()
    restored = SkillSet.model_validate(payload)
    assert restored == original


def test_skill_set_field_order_stable() -> None:
    obj = SkillSet()
    expected_order = ["skills", "newly_generated", "produced_by"]
    assert list(obj.model_dump().keys()) == expected_order


def test_skill_ref_field_order_stable() -> None:
    ref = SkillRef(**_valid_skill_ref())
    expected_order = [
        "slug",
        "version",
        "path",
        "match_score",
        "match_zone",
        "generated_in_run",
    ]
    assert list(ref.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific validators                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "score,zone",
    [
        (0.85, "reuse"),
        (0.92, "reuse"),
        (1.00, "reuse"),
        (0.60, "ask"),
        (0.70, "ask"),
        (0.84999, "ask"),
        (0.59999, "generate"),
        (0.30, "generate"),
        (0.00, "generate"),
    ],
)
def test_match_zone_aligns_with_score(score: float, zone: str) -> None:
    SkillRef(**_valid_skill_ref(score=score, zone=zone))


@pytest.mark.parametrize(
    "score,wrong_zone",
    [
        (0.92, "ask"),
        (0.70, "reuse"),
        (0.50, "ask"),
        (0.30, "reuse"),
    ],
)
def test_match_zone_misalignment_rejected(score: float, wrong_zone: str) -> None:
    with pytest.raises(ValidationError, match="does not match"):
        SkillRef(**_valid_skill_ref(score=score, zone=wrong_zone))


def test_match_score_bounds() -> None:
    with pytest.raises(ValidationError):
        SkillRef(**_valid_skill_ref(score=-0.01, zone="generate"))
    with pytest.raises(ValidationError):
        SkillRef(**_valid_skill_ref(score=1.01, zone="reuse"))


def test_skill_ref_slug_must_be_kebab_case() -> None:
    with pytest.raises(ValidationError):
        SkillRef(**_valid_skill_ref(slug="Read_Codebase"))
    # Valid edge: digits allowed in middle.
    SkillRef(**_valid_skill_ref(slug="next-app-router-page"))


def test_skill_ref_required_fields() -> None:
    with pytest.raises(ValidationError):
        SkillRef(slug="x", path="y")  # missing version, match_score, match_zone


def test_skill_ref_version_must_be_semver() -> None:
    # Valid semver formats.
    SkillRef(**_valid_skill_ref(version="1.0.0"))
    SkillRef(**_valid_skill_ref(version="2.3.1"))
    SkillRef(**_valid_skill_ref(version="10.20.30"))
    SkillRef(**_valid_skill_ref(version="1.0.0-rc.1"))
    SkillRef(**_valid_skill_ref(version="1.0.0+build.123"))

    # Invalid formats.
    with pytest.raises(ValidationError):
        SkillRef(**_valid_skill_ref(version="1.0"))
    with pytest.raises(ValidationError):
        SkillRef(**_valid_skill_ref(version="v1.0.0"))
    with pytest.raises(ValidationError):
        SkillRef(**_valid_skill_ref(version="1"))
    with pytest.raises(ValidationError):
        SkillRef(**_valid_skill_ref(version="abc"))


def test_generated_in_run_default_false() -> None:
    ref = SkillRef(**_valid_skill_ref())
    assert ref.generated_in_run is False


def test_skills_can_be_empty() -> None:
    obj = SkillSet(skills=[])
    assert obj.skills == []
    assert obj.newly_generated == []


def test_newly_generated_independent_of_skills() -> None:
    """newly_generated is a separate list — a Skill can appear in skills
    without appearing in newly_generated (reused) and vice versa is also
    valid (a generated Skill being prepared for promotion before it's
    referenced)."""
    reused_only = SkillSet(
        skills=[SkillRef(**_valid_skill_ref(slug="read-codebase"))],
        newly_generated=[],
    )
    assert reused_only.newly_generated == []

    generated = SkillRef(
        **_valid_skill_ref(slug="new-skill", score=0.50, zone="generate")
    )
    both = SkillSet(skills=[generated], newly_generated=[generated])
    assert len(both.newly_generated) == 1


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_skill_set_field_set_matches_bible() -> None:
    """Bible 07 §7.1 declares the SkillSet artifact as a JSON object with
    ``skills``, ``newly_generated``, ``produced_by``. Implementation top-
    level fields must include all bible fields exactly.
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")

    section_match = re.search(
        r"###\s*7\.1\s+The\s+`SkillSet`\s+artifact.*?```json\s*(\{.*?\})\s*```",
        bible_text,
        re.DOTALL,
    )
    assert section_match, "Could not locate §7.1 JSON block in bible 07"

    bible_json = json.loads(section_match.group(1))
    bible_fields = set(bible_json.keys())

    impl_fields = set(SkillSet.model_fields.keys())

    missing = bible_fields - impl_fields
    assert not missing, (
        f"SkillSet missing bible-required fields: {sorted(missing)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )
    extras = impl_fields - bible_fields
    assert not extras, (
        f"SkillSet has extras not in bible §7.1: {sorted(extras)}"
    )

    # SkillRef inner shape: bible's first skill entry has slug, version, path.
    # Impl has those plus matcher audit fields (allowed per task spec).
    bible_ref_fields = set(bible_json["skills"][0].keys())
    impl_ref_fields = set(SkillRef.model_fields.keys())
    ref_missing = bible_ref_fields - impl_ref_fields
    assert not ref_missing, (
        f"SkillRef missing bible-required canonical fields: "
        f"{sorted(ref_missing)}"
    )
