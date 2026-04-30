"""Tests for the AgentFrontmatter schema."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import AgentFrontmatter


_BIBLE_PATH = Path.home() / "cee" / "bible" / "06_agent_system_design.md"


def _valid_kwargs(**overrides: object) -> dict:
    base: dict = {
        "name": "primary-builder",
        "description": (
            "Primary agent that produces a single source-of-truth "
            "deliverable for BUILD task types."
        ),
        "posture": "primary",
        "task_types_supported": ["BUILD"],
        "capabilities": ["python", "tdd"],
        "allowed_tools": ["Read", "Edit", "Write", "Bash"],
        "version": "1.0.0",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_agent_frontmatter_minimal_valid() -> None:
    obj = AgentFrontmatter(**_valid_kwargs())
    assert obj.name == "primary-builder"
    assert obj.posture == "primary"
    assert obj.domain is None
    assert obj.created_by_run is None
    assert obj.created_at is None
    assert obj.needs_review is False


def test_agent_frontmatter_full_valid() -> None:
    obj = AgentFrontmatter(
        name="legal-specialist",
        description="Specialist consultant on legal/contracts.",
        posture="specialist",
        task_types_supported=["ANALYZE", "RESEARCH"],
        capabilities=["legal_review", "redline"],
        allowed_tools=["Read", "Grep"],
        version="2.0.1",
        domain="other",
        created_by_run="20260430_140000_a1b2c3d4",
        created_at="2026-04-30T14:00:00Z",
        needs_review=True,
    )
    assert obj.posture == "specialist"
    assert obj.domain == "other"
    assert obj.needs_review is True


@pytest.mark.parametrize(
    "missing_field",
    [
        "name",
        "description",
        "posture",
        "task_types_supported",
        "capabilities",
        "allowed_tools",
        "version",
    ],
)
def test_agent_frontmatter_missing_required_field_raises(
    missing_field: str,
) -> None:
    kwargs = _valid_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        AgentFrontmatter(**kwargs)


def test_agent_frontmatter_extra_field_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        AgentFrontmatter(**kwargs)


def test_agent_frontmatter_string_whitespace_stripped() -> None:
    obj = AgentFrontmatter(**_valid_kwargs(description="  description  "))
    assert obj.description == "description"


def test_agent_frontmatter_schema_version_present() -> None:
    assert AgentFrontmatter.SCHEMA_VERSION == "1.0.0"


def test_agent_frontmatter_json_round_trip() -> None:
    original = AgentFrontmatter(**_valid_kwargs())
    payload = original.model_dump_json()
    restored = AgentFrontmatter.model_validate_json(payload)
    assert restored == original


def test_agent_frontmatter_dict_round_trip() -> None:
    original = AgentFrontmatter(**_valid_kwargs())
    payload = original.model_dump()
    restored = AgentFrontmatter.model_validate(payload)
    assert restored == original


def test_agent_frontmatter_field_order_stable() -> None:
    obj = AgentFrontmatter(**_valid_kwargs())
    expected_order = [
        "name",
        "description",
        "posture",
        "task_types_supported",
        "capabilities",
        "allowed_tools",
        "version",
        "domain",
        "created_by_run",
        "created_at",
        "needs_review",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific validators                                                   #
# --------------------------------------------------------------------------- #


def test_specialist_requires_domain() -> None:
    with pytest.raises(ValidationError, match="domain is required"):
        AgentFrontmatter(**_valid_kwargs(posture="specialist", domain=None))
    # With domain it passes.
    obj = AgentFrontmatter(
        **_valid_kwargs(posture="specialist", domain="code")
    )
    assert obj.domain == "code"


@pytest.mark.parametrize(
    "posture",
    ["primary", "critic", "optimizer", "orchestrator"],
)
def test_non_specialist_allows_null_domain(posture: str) -> None:
    obj = AgentFrontmatter(**_valid_kwargs(posture=posture, domain=None))
    assert obj.domain is None


@pytest.mark.parametrize(
    "posture",
    ["primary", "critic", "optimizer", "orchestrator", "specialist"],
)
def test_posture_must_be_valid_enum(posture: str) -> None:
    domain = "code" if posture == "specialist" else None
    obj = AgentFrontmatter(**_valid_kwargs(posture=posture, domain=domain))
    assert obj.posture == posture


def test_posture_rejects_invalid() -> None:
    with pytest.raises(ValidationError):
        AgentFrontmatter(**_valid_kwargs(posture="leader"))
    with pytest.raises(ValidationError):
        AgentFrontmatter(**_valid_kwargs(posture="Primary"))


def test_version_must_be_semver() -> None:
    AgentFrontmatter(**_valid_kwargs(version="1.0.0"))
    AgentFrontmatter(**_valid_kwargs(version="2.3.1"))
    AgentFrontmatter(**_valid_kwargs(version="1.0.0-rc.1"))

    with pytest.raises(ValidationError):
        AgentFrontmatter(**_valid_kwargs(version="1.0"))
    with pytest.raises(ValidationError):
        AgentFrontmatter(**_valid_kwargs(version="v1.0.0"))


def test_needs_review_default_false() -> None:
    obj = AgentFrontmatter(**_valid_kwargs())
    assert obj.needs_review is False


def test_slug_must_be_kebab_case() -> None:
    with pytest.raises(ValidationError):
        AgentFrontmatter(**_valid_kwargs(name="Primary_Builder"))
    with pytest.raises(ValidationError):
        AgentFrontmatter(**_valid_kwargs(name="primary builder"))


def test_task_types_supported_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        AgentFrontmatter(**_valid_kwargs(task_types_supported=["FROBNICATE"]))


def test_capabilities_non_empty() -> None:
    with pytest.raises(ValidationError):
        AgentFrontmatter(**_valid_kwargs(capabilities=[]))


def test_allowed_tools_non_empty() -> None:
    with pytest.raises(ValidationError):
        AgentFrontmatter(**_valid_kwargs(allowed_tools=[]))


def test_created_by_run_accepts_run_id_or_manual() -> None:
    AgentFrontmatter(
        **_valid_kwargs(created_by_run="20260430_140000_a1b2c3d4")
    )
    AgentFrontmatter(**_valid_kwargs(created_by_run="manual"))
    AgentFrontmatter(**_valid_kwargs(created_by_run=None))
    # Bible 06 §5.2.1 does not list "seed" for agents (only Skills).
    with pytest.raises(ValidationError):
        AgentFrontmatter(**_valid_kwargs(created_by_run="seed"))


def test_domain_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        AgentFrontmatter(
            **_valid_kwargs(posture="specialist", domain="biology")
        )


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_agent_frontmatter_field_set_matches_bible() -> None:
    """Bible 06 §5.2.1 enumerates the YAML frontmatter fields. The schema
    must include every field named at column 0 of the YAML literal.
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    text = _BIBLE_PATH.read_text(encoding="utf-8")
    # Bible 06 nests §5.2.1 inside §5.2; find the §5.2.1 YAML block.
    section_match = re.search(
        r"####\s*5\.2\.1\s+Frontmatter schema.*?```yaml\s*(.*?)```",
        text,
        re.DOTALL,
    )
    assert section_match, "Could not locate §5.2.1 YAML block in bible 06"

    yaml_text = section_match.group(1)
    field_pattern = re.compile(r"^([a-z_]+):", re.MULTILINE)
    bible_fields = set(field_pattern.findall(yaml_text))

    assert "posture" in bible_fields
    assert "capabilities" in bible_fields

    impl_fields = set(AgentFrontmatter.model_fields.keys())
    missing = bible_fields - impl_fields
    assert not missing, (
        f"AgentFrontmatter missing bible-required fields: {sorted(missing)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )
