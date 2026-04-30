"""Tests for the AgentPlan schema."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import AgentPlan, AgentRef


_BIBLE_PATH = Path.home() / "cee" / "bible" / "06_agent_system_design.md"


def _valid_agent_ref(slug: str = "code-builder", posture: str = "primary") -> dict:
    return {
        "slug": slug,
        "posture": posture,
        "path": f"~/cee/.claude/agents/{slug}.md",
    }


def _valid_kwargs() -> dict:
    return {
        "agents": [_valid_agent_ref()],
        "coordination": "Single primary agent executes the task.",
    }


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_agent_plan_minimal_valid() -> None:
    obj = AgentPlan(**_valid_kwargs())
    assert len(obj.agents) == 1
    assert obj.agents[0].posture == "primary"
    assert obj.produced_by == "AGENT_SELECTOR"


def test_agent_plan_full_valid() -> None:
    obj = AgentPlan(
        agents=[
            AgentRef(**_valid_agent_ref("code-builder", "primary")),
            AgentRef(**_valid_agent_ref("code-critic", "critic")),
            AgentRef(**_valid_agent_ref("code-optimizer", "optimizer")),
        ],
        coordination="Primary executes; critic reviews; optimizer tightens.",
        produced_by="AGENT_SELECTOR",
    )
    assert len(obj.agents) == 3


@pytest.mark.parametrize("missing_field", ["agents", "coordination"])
def test_agent_plan_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        AgentPlan(**kwargs)


def test_agent_plan_extra_field_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        AgentPlan(**kwargs)


def test_agent_plan_string_whitespace_stripped() -> None:
    kwargs = _valid_kwargs()
    kwargs["coordination"] = "  trimmed  "
    obj = AgentPlan(**kwargs)
    assert obj.coordination == "trimmed"


def test_agent_plan_schema_version_present() -> None:
    assert AgentPlan.SCHEMA_VERSION == "1.0.0"
    assert AgentRef.SCHEMA_VERSION == "1.0.0"


def test_agent_plan_json_round_trip() -> None:
    original = AgentPlan(**_valid_kwargs())
    payload = original.model_dump_json()
    restored = AgentPlan.model_validate_json(payload)
    assert restored == original


def test_agent_plan_dict_round_trip() -> None:
    original = AgentPlan(**_valid_kwargs())
    payload = original.model_dump()
    restored = AgentPlan.model_validate(payload)
    assert restored == original


def test_agent_plan_field_order_stable() -> None:
    obj = AgentPlan(**_valid_kwargs())
    expected_order = ["agents", "coordination", "produced_by"]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific validators                                                   #
# --------------------------------------------------------------------------- #


def test_at_least_one_lead_agent_primary() -> None:
    AgentPlan(
        agents=[AgentRef(**_valid_agent_ref("code-builder", "primary"))],
        coordination="x",
    )


def test_at_least_one_lead_agent_orchestrator() -> None:
    AgentPlan(
        agents=[
            AgentRef(**_valid_agent_ref("task-orchestrator", "orchestrator")),
            AgentRef(**_valid_agent_ref("code-critic", "critic")),
        ],
        coordination="Orchestrator coordinates; critic reviews.",
    )


def test_no_lead_agent_rejected() -> None:
    with pytest.raises(ValidationError, match="primary"):
        AgentPlan(
            agents=[
                AgentRef(**_valid_agent_ref("code-critic", "critic")),
                AgentRef(**_valid_agent_ref("code-optimizer", "optimizer")),
            ],
            coordination="x",
        )


def test_empty_agents_list_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentPlan(agents=[], coordination="x")


def test_agent_slug_must_be_kebab_case() -> None:
    # Valid kebab-case.
    AgentRef(**_valid_agent_ref("code-builder", "primary"))
    AgentRef(slug="abc", posture="primary", path="x")
    AgentRef(slug="agent-with-numbers-123", posture="primary", path="x")

    # Invalid: uppercase.
    with pytest.raises(ValidationError):
        AgentRef(slug="Code-Builder", posture="primary", path="x")

    # Invalid: underscores.
    with pytest.raises(ValidationError):
        AgentRef(slug="code_builder", posture="primary", path="x")

    # Invalid: too short (< 3 chars after start char).
    with pytest.raises(ValidationError):
        AgentRef(slug="ab", posture="primary", path="x")

    # Invalid: starts with digit.
    with pytest.raises(ValidationError):
        AgentRef(slug="1-fix", posture="primary", path="x")

    # Invalid: ends with hyphen.
    with pytest.raises(ValidationError):
        AgentRef(slug="code-", posture="primary", path="x")

    # Invalid: spaces.
    with pytest.raises(ValidationError):
        AgentRef(slug="code builder", posture="primary", path="x")


@pytest.mark.parametrize(
    "posture", ["primary", "critic", "optimizer", "orchestrator", "specialist"]
)
def test_agent_posture_accepts_valid_enum(posture: str) -> None:
    # Only the lead-agent rule applies, so ensure at least one is primary.
    if posture in {"primary", "orchestrator"}:
        agents = [AgentRef(**_valid_agent_ref("agent-test", posture))]
    else:
        agents = [
            AgentRef(**_valid_agent_ref("agent-primary", "primary")),
            AgentRef(**_valid_agent_ref("agent-other", posture)),
        ]
    AgentPlan(agents=agents, coordination="x")


def test_agent_posture_rejects_invalid_enum() -> None:
    with pytest.raises(ValidationError):
        AgentRef(slug="agent-x", posture="reviewer", path="x")


def test_generated_in_run_default_false() -> None:
    ref = AgentRef(**_valid_agent_ref())
    assert ref.generated_in_run is False


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_agent_plan_field_set_matches_bible() -> None:
    """Bible 06 §7.1 declares the AgentPlan artifact as a JSON object with
    ``agents``, ``coordination``, ``produced_by``. Implementation top-level
    fields must match exactly.
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")

    section_match = re.search(
        r"###\s*7\.1\s+The\s+`AgentPlan`\s+artifact.*?```json\s*(\{.*?\})\s*```",
        bible_text,
        re.DOTALL,
    )
    assert section_match, "Could not locate §7.1 JSON block in bible 06"

    bible_json = json.loads(section_match.group(1))
    bible_fields = set(bible_json.keys())

    impl_fields = set(AgentPlan.model_fields.keys())

    missing = bible_fields - impl_fields
    assert not missing, (
        f"AgentPlan missing bible-required fields: {sorted(missing)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )
    extras = impl_fields - bible_fields
    assert not extras, (
        f"AgentPlan has extras not in bible §7.1: {sorted(extras)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )

    # Also verify AgentRef inner shape matches the example AgentRef in the
    # bible JSON. Bible's first agent entry has slug, posture, path,
    # generated_in_run.
    bible_agent_ref = bible_json["agents"][0]
    bible_ref_fields = set(bible_agent_ref.keys())
    impl_ref_fields = set(AgentRef.model_fields.keys())

    ref_missing = bible_ref_fields - impl_ref_fields
    assert not ref_missing, (
        f"AgentRef missing bible-required fields: {sorted(ref_missing)}"
    )
