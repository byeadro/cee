"""Tests for the FormatDeclaration schema."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import FormatDeclaration


_BIBLE_PATH = Path.home() / "cee" / "bible" / "10_output_format_engine.md"


def _valid_kwargs(**overrides: object) -> dict:
    base: dict = {
        "type": "markdown_report",
        "shape": "structured markdown document",
        "acceptance_criteria": ["All required sections present"],
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_format_declaration_minimal_valid() -> None:
    obj = FormatDeclaration(**_valid_kwargs())
    assert obj.type == "markdown_report"
    assert obj.shape == "structured markdown document"
    assert obj.required_sections == []
    assert obj.heading_convention is None
    assert obj.inline_schema is None
    assert obj.required_artifacts == []


def test_format_declaration_full_valid() -> None:
    obj = FormatDeclaration(
        type="markdown_report",
        shape="structured markdown document",
        required_sections=["Summary", "Findings", "Recommendations"],
        heading_convention="Use H2 (##) for top-level sections.",
        acceptance_criteria=[
            "All required sections present.",
            "Each finding includes evidence reference.",
        ],
        inline_schema=None,
        required_artifacts=[],
    )
    assert len(obj.required_sections) == 3
    assert len(obj.acceptance_criteria) == 2


@pytest.mark.parametrize("missing_field", ["type", "shape", "acceptance_criteria"])
def test_format_declaration_missing_required_field_raises(
    missing_field: str,
) -> None:
    kwargs = _valid_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        FormatDeclaration(**kwargs)


def test_format_declaration_extra_field_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        FormatDeclaration(**kwargs)


def test_format_declaration_string_whitespace_stripped() -> None:
    obj = FormatDeclaration(**_valid_kwargs(shape="  shape  "))
    assert obj.shape == "shape"


def test_format_declaration_schema_version_present() -> None:
    assert FormatDeclaration.SCHEMA_VERSION == "1.0.0"


def test_format_declaration_json_round_trip() -> None:
    original = FormatDeclaration(**_valid_kwargs())
    payload = original.model_dump_json()
    restored = FormatDeclaration.model_validate_json(payload)
    assert restored == original


def test_format_declaration_dict_round_trip() -> None:
    original = FormatDeclaration(**_valid_kwargs())
    payload = original.model_dump()
    restored = FormatDeclaration.model_validate(payload)
    assert restored == original


def test_format_declaration_field_order_stable() -> None:
    obj = FormatDeclaration(**_valid_kwargs())
    expected_order = [
        "type",
        "shape",
        "required_sections",
        "heading_convention",
        "acceptance_criteria",
        "inline_schema",
        "required_artifacts",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific validators                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "format_type",
    [
        "code_file",
        "code_project",
        "prose_short",
        "prose_long",
        "prose_manuscript",
        "markdown_report",
        "markdown_decision",
        "diagnosis_and_fix",
        "json_object",
        "json_array",
        "csv_table",
        "mixed_artifact",
        "email_draft",
        "outline",
        "comparison_table",
        "step_by_step_guide",
        "code_review",
        "audit_report",
    ],
)
def test_type_must_be_valid_enum(format_type: str) -> None:
    obj = FormatDeclaration(**_valid_kwargs(type=format_type))
    assert obj.type == format_type


def test_type_rejects_invented_values() -> None:
    with pytest.raises(ValidationError):
        FormatDeclaration(**_valid_kwargs(type="plain_text"))
    with pytest.raises(ValidationError):
        FormatDeclaration(**_valid_kwargs(type="markdown_decision_doc"))


def test_acceptance_criteria_non_empty() -> None:
    with pytest.raises(ValidationError):
        FormatDeclaration(**_valid_kwargs(acceptance_criteria=[]))


def test_required_sections_default_empty() -> None:
    obj = FormatDeclaration(**_valid_kwargs())
    assert obj.required_sections == []


def test_inline_schema_optional() -> None:
    # None is fine.
    obj_a = FormatDeclaration(**_valid_kwargs(type="json_object"))
    assert obj_a.inline_schema is None
    # Set is fine.
    obj_b = FormatDeclaration(
        **_valid_kwargs(
            type="json_object",
            inline_schema='{"id": "string", "score": "number"}',
        )
    )
    assert obj_b.inline_schema is not None


def test_heading_convention_optional() -> None:
    obj_a = FormatDeclaration(**_valid_kwargs())
    assert obj_a.heading_convention is None
    obj_b = FormatDeclaration(
        **_valid_kwargs(heading_convention="Use H2 for sections.")
    )
    assert obj_b.heading_convention == "Use H2 for sections."


def test_required_artifacts_default_empty() -> None:
    obj = FormatDeclaration(**_valid_kwargs(type="mixed_artifact"))
    assert obj.required_artifacts == []
    obj_b = FormatDeclaration(
        **_valid_kwargs(
            type="mixed_artifact",
            required_artifacts=["spec.md", "code.py", "tests.py"],
        )
    )
    assert len(obj_b.required_artifacts) == 3


def test_shape_non_empty() -> None:
    with pytest.raises(ValidationError):
        FormatDeclaration(**_valid_kwargs(shape=""))


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_format_declaration_types_match_bible() -> None:
    """Bible 10 §5.1 enumerates the closed format catalog table. The
    FormatDeclaration ``type`` Literal must include every catalog entry.
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    text = _BIBLE_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"###\s*5\.1\s+The closed format catalog.*?(### |\Z)",
        text,
        re.DOTALL,
    )
    assert section_match, "Could not locate §5.1 in bible 10"
    section = section_match.group(0)

    # Each format type appears in the first cell of a row as
    # ``<td>`<format>`</td>``. Parse them.
    code_cells = re.findall(r"<td>`([a-z_]+)`</td>", section)

    # First-column entries are the format names; later columns may
    # include things like task-types or shape descriptions. Constrain
    # to lowercase snake_case identifiers and intersect with known
    # formats from the catalog.
    expected_known = {
        "code_file",
        "code_project",
        "prose_short",
        "prose_long",
        "prose_manuscript",
        "markdown_report",
        "markdown_decision",
        "diagnosis_and_fix",
        "json_object",
        "json_array",
        "csv_table",
        "mixed_artifact",
        "email_draft",
        "outline",
        "comparison_table",
        "step_by_step_guide",
        "code_review",
        "audit_report",
    }

    bible_format_types = {
        cell for cell in code_cells if re.fullmatch(r"[a-z_]+", cell)
    }

    assert expected_known.issubset(bible_format_types), (
        f"Bible §5.1 parsing missed expected formats. Parsed: "
        f"{sorted(bible_format_types)}"
    )

    # Implementation must accept every catalog format.
    for format_type in expected_known:
        FormatDeclaration(
            type=format_type,  # type: ignore[arg-type]
            shape="x",
            acceptance_criteria=["c"],
        )
