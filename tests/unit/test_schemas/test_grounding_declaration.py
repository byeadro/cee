"""Tests for the GroundingDeclaration schema."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import GroundingDeclaration, Source


_BIBLE_PATH = (
    Path.home() / "cee" / "bible" / "11_hallucination_source_grounding.md"
)


def _valid_source(**overrides: object) -> Source:
    base: dict = {
        "type": "attachment",
        "id": "q1_report.pdf",
        "description": "Q1 financial report (12 pages)",
    }
    base.update(overrides)
    return Source(**base)


def _valid_kwargs(**overrides: object) -> dict:
    base: dict = {
        "allowed_sources": [_valid_source()],
        "prohibited_inferences": [
            "Do not invent numerical values not present in allowed sources.",
        ],
        "citation_requirement": (
            "Every factual claim must reference a source by id."
        ),
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_grounding_declaration_minimal_valid() -> None:
    obj = GroundingDeclaration(allowed_sources=[_valid_source()])
    assert len(obj.allowed_sources) == 1
    assert obj.prohibited_inferences == []
    assert obj.citation_requirement == ""


def test_grounding_declaration_full_valid() -> None:
    obj = GroundingDeclaration(
        allowed_sources=[
            _valid_source(),
            _valid_source(
                type="filesystem_path",
                id="~/projects/embra/src/auth.py",
                description="Current auth implementation",
            ),
            _valid_source(
                type="internal_skill_reference",
                id="write-rls-policies",
                description="Sourced Skill for Supabase RLS",
            ),
        ],
        prohibited_inferences=[
            "Do not invent API methods, parameters, or return types.",
            "Do not invent numerical values not present in allowed sources.",
        ],
        citation_requirement=(
            "Every factual claim must reference a specific source by its "
            "identifier in <allowed_sources>."
        ),
    )
    assert len(obj.allowed_sources) == 3
    assert len(obj.prohibited_inferences) == 2


def test_grounding_declaration_missing_required_field_raises() -> None:
    with pytest.raises(ValidationError):
        GroundingDeclaration()  # type: ignore[call-arg]


def test_grounding_declaration_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        GroundingDeclaration(
            allowed_sources=[_valid_source()], unknown_field="x"
        )


def test_grounding_declaration_string_whitespace_stripped() -> None:
    obj = GroundingDeclaration(
        allowed_sources=[_valid_source()],
        citation_requirement="  cite by id  ",
    )
    assert obj.citation_requirement == "cite by id"


def test_grounding_declaration_schema_version_present() -> None:
    assert GroundingDeclaration.SCHEMA_VERSION == "1.0.0"


def test_grounding_declaration_json_round_trip() -> None:
    original = GroundingDeclaration(**_valid_kwargs())
    payload = original.model_dump_json()
    restored = GroundingDeclaration.model_validate_json(payload)
    assert restored == original


def test_grounding_declaration_dict_round_trip() -> None:
    original = GroundingDeclaration(**_valid_kwargs())
    payload = original.model_dump()
    restored = GroundingDeclaration.model_validate(payload)
    assert restored == original


def test_grounding_declaration_field_order_stable() -> None:
    obj = GroundingDeclaration(**_valid_kwargs())
    expected_order = [
        "allowed_sources",
        "prohibited_inferences",
        "citation_requirement",
    ]
    assert list(obj.model_dump().keys()) == expected_order


def test_source_field_order_stable() -> None:
    src = _valid_source()
    expected_order = ["type", "id", "description"]
    assert list(src.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific validators                                                   #
# --------------------------------------------------------------------------- #


def test_allowed_sources_non_empty() -> None:
    with pytest.raises(ValidationError):
        GroundingDeclaration(allowed_sources=[])


@pytest.mark.parametrize(
    "source_type",
    [
        "attachment",
        "filesystem_path",
        "url",
        "internal_skill_reference",
        "bible_section",
        "prior_run_artifact",
        "system_of_record",
        "user_provided_text",
    ],
)
def test_source_type_must_be_valid_enum(source_type: str) -> None:
    src = _valid_source(type=source_type)
    assert src.type == source_type


def test_source_type_rejects_invented_values() -> None:
    with pytest.raises(ValidationError):
        _valid_source(type="primary_news")
    with pytest.raises(ValidationError):
        _valid_source(type="user_memory")
    with pytest.raises(ValidationError):
        _valid_source(type="git_diff")


def test_citation_requirement_can_be_empty_string() -> None:
    obj = GroundingDeclaration(
        allowed_sources=[_valid_source()], citation_requirement=""
    )
    assert obj.citation_requirement == ""


def test_prohibited_inferences_default_empty() -> None:
    obj = GroundingDeclaration(allowed_sources=[_valid_source()])
    assert obj.prohibited_inferences == []


def test_source_id_required() -> None:
    with pytest.raises(ValidationError):
        Source(type="attachment", description="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Source(type="attachment", id="", description="x")


def test_source_description_required() -> None:
    with pytest.raises(ValidationError):
        Source(type="attachment", id="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Source(type="attachment", id="x", description="")


def test_source_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Source(
            type="attachment",
            id="x",
            description="y",
            unknown="z",
        )


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_grounding_declaration_source_types_match_bible() -> None:
    """Bible 11 §5.1 enumerates the closed source-type table. The Source
    model's ``type`` Literal must equal the bible's set exactly.
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    text = _BIBLE_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"###\s*5\.1\s+The closed source-type enum.*?(### |\Z)",
        text,
        re.DOTALL,
    )
    assert section_match, "Could not locate §5.1 in bible 11"
    section = section_match.group(0)

    # Each source type appears as `<td>`<type>`</td>` (a code-fenced cell
    # in the markdown table). Parse those.
    code_cells = re.findall(r"<td>`([a-z_]+)`</td>", section)

    # Filter to plausible source-type identifiers (lowercase, snake_case,
    # appears as the first cell of each row). The first column of the
    # table has type names.
    bible_source_types = {
        cell for cell in code_cells if re.fullmatch(r"[a-z_]+", cell)
    }

    # Ground-truth: the brief verified these eight closed values from
    # bible 11 §5.1. Defensive check that the regex parsed at least them.
    expected_known = {
        "attachment",
        "filesystem_path",
        "url",
        "internal_skill_reference",
        "bible_section",
        "prior_run_artifact",
        "system_of_record",
        "user_provided_text",
    }
    assert expected_known.issubset(bible_source_types), (
        f"Bible §5.1 parsing missed expected types. Parsed: "
        f"{sorted(bible_source_types)}"
    )

    # Implementation must allow every parsed source type.
    for source_type in expected_known:
        Source(type=source_type, id="x", description="y")  # type: ignore[arg-type]
