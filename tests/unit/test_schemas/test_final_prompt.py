"""Tests for the FinalPrompt schema and its nested models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas import (
    AgentEntry,
    Agents,
    AssumptionsMade,
    AttachmentSummary,
    Chunking,
    Context,
    ExecutionPlan,
    FinalPrompt,
    GroundingRules,
    OutputFormat,
    PlanStep,
    RunMetadata,
    SkillEntry,
    Skills,
    StopConditions,
)


def _valid_context() -> Context:
    return Context(original_input="Refactor auth module.")


def _valid_execution_plan() -> ExecutionPlan:
    return ExecutionPlan(steps=[PlanStep(n=1, action="Refactor")])


def _valid_output_format() -> OutputFormat:
    return OutputFormat(description="A complete patched file at src/auth.ts.")


def _valid_stop_conditions() -> StopConditions:
    return StopConditions(
        conditions=["Output validates against output_format."]
    )


def _valid_run_metadata() -> RunMetadata:
    return RunMetadata(
        run_id="20260430_141522_a3f8c2d1",
        generated_at="2026-04-30T14:15:22Z",
        complexity="MEDIUM",
        complexity_score=42,
        bible_version="2026-04-30T14:00:00Z",
    )


def _valid_kwargs() -> dict:
    return {
        "target_executor": "claude_code",
        "context": _valid_context(),
        "role": "You are a senior backend engineer focused on auth systems.",
        "task": "Refactor the authentication module to use JWTs.",
        "execution_plan": _valid_execution_plan(),
        "output_format": _valid_output_format(),
        "stop_conditions": _valid_stop_conditions(),
        "run_metadata": _valid_run_metadata(),
    }


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_final_prompt_minimal_valid() -> None:
    obj = FinalPrompt(**_valid_kwargs())
    assert obj.target_executor == "claude_code"
    assert obj.agents is None
    assert obj.skills is None
    assert obj.constraints is None
    assert obj.grounding_rules is None
    assert obj.assumptions_made is None
    assert obj.safety_banner is None
    assert obj.chunking is None
    assert obj.produced_by == "PROMPT_BUILDER"


def test_final_prompt_full_valid() -> None:
    obj = FinalPrompt(
        target_executor="claude_ai",
        context=Context(
            original_input="Refactor auth.",
            attachment_summaries=[
                AttachmentSummary(name="spec.pdf", summary="Auth spec.")
            ],
            inferred_context="Prior Run used JWT.",
        ),
        role="You are a senior backend engineer focused on auth.",
        task="Refactor auth.",
        agents=Agents(
            entries=[
                AgentEntry(role="primary", path="~/cee/.claude/agents/p.md"),
                AgentEntry(role="critic", path="~/cee/.claude/agents/c.md"),
            ],
            coordination="Primary executes; critic reviews.",
        ),
        skills=Skills(
            entries=[
                SkillEntry(name="read-codebase", path="~/cee/skills/r/SKILL.md"),
            ]
        ),
        execution_plan=_valid_execution_plan(),
        constraints=["Python 3.11+", "no external API calls"],
        grounding_rules=GroundingRules(
            allowed_sources=["The attached PDF"],
            prohibited_inferences=["Do not infer undocumented API behavior."],
            citation_requirement="Every claim must cite a section.",
        ),
        assumptions_made=AssumptionsMade(
            assumptions=["Assumed Python 3.11."],
            flag_back_instruction="If wrong, halt and ask.",
        ),
        output_format=_valid_output_format(),
        stop_conditions=_valid_stop_conditions(),
        safety_banner="[CONFIRM BEFORE EXECUTION]",
        run_metadata=_valid_run_metadata(),
        chunking=Chunking(n=1, of=3, chunking_instructions="Wait for all 3."),
        produced_by="PROMPT_BUILDER",
    )
    assert obj.agents is not None
    assert obj.skills is not None
    assert obj.constraints == ["Python 3.11+", "no external API calls"]


@pytest.mark.parametrize(
    "missing_field",
    [
        "target_executor",
        "context",
        "role",
        "task",
        "execution_plan",
        "output_format",
        "stop_conditions",
        "run_metadata",
    ],
)
def test_final_prompt_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        FinalPrompt(**kwargs)


def test_final_prompt_extra_field_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        FinalPrompt(**kwargs)


def test_final_prompt_string_whitespace_stripped() -> None:
    kwargs = _valid_kwargs()
    kwargs["role"] = "  trimmed role  "
    obj = FinalPrompt(**kwargs)
    assert obj.role == "trimmed role"


def test_final_prompt_schema_version_present() -> None:
    assert FinalPrompt.SCHEMA_VERSION == "1.0.0"


def test_final_prompt_json_round_trip() -> None:
    original = FinalPrompt(**_valid_kwargs())
    payload = original.model_dump_json()
    restored = FinalPrompt.model_validate_json(payload)
    assert restored == original


def test_final_prompt_dict_round_trip() -> None:
    original = FinalPrompt(**_valid_kwargs())
    payload = original.model_dump()
    restored = FinalPrompt.model_validate(payload)
    assert restored == original


def test_final_prompt_field_order_stable() -> None:
    obj = FinalPrompt(**_valid_kwargs())
    expected_order = [
        "target_executor",
        "context",
        "role",
        "task",
        "agents",
        "skills",
        "execution_plan",
        "constraints",
        "grounding_rules",
        "assumptions_made",
        "output_format",
        "stop_conditions",
        "safety_banner",
        "run_metadata",
        "chunking",
        "produced_by",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("executor", ["claude_ai", "claude_code", "api"])
def test_target_executor_accepts_valid_enum(executor: str) -> None:
    kwargs = _valid_kwargs()
    kwargs["target_executor"] = executor
    FinalPrompt(**kwargs)


def test_target_executor_rejects_invalid() -> None:
    kwargs = _valid_kwargs()
    kwargs["target_executor"] = "claude_unknown"
    with pytest.raises(ValidationError):
        FinalPrompt(**kwargs)


def test_to_xml_raises_not_implemented_in_8a() -> None:
    obj = FinalPrompt(**_valid_kwargs())
    with pytest.raises(NotImplementedError, match="prompt_builder"):
        obj.to_xml()


def test_optional_fields_can_be_omitted() -> None:
    obj = FinalPrompt(**_valid_kwargs())
    # All conditional/optional fields default to None or are not present.
    assert obj.agents is None
    assert obj.skills is None
    assert obj.constraints is None
    assert obj.grounding_rules is None
    assert obj.assumptions_made is None
    assert obj.safety_banner is None
    assert obj.chunking is None


def test_run_metadata_complexity_enum_enforced() -> None:
    with pytest.raises(ValidationError):
        RunMetadata(
            run_id="x",
            generated_at="2026-04-30T14:15:22Z",
            complexity="UNKNOWN",
            complexity_score=10,
            bible_version="2026-04-30T14:00:00Z",
        )


def test_execution_plan_requires_at_least_one_step() -> None:
    with pytest.raises(ValidationError):
        ExecutionPlan(steps=[])


def test_stop_conditions_requires_at_least_one_condition() -> None:
    with pytest.raises(ValidationError):
        StopConditions(conditions=[])


def test_agents_requires_at_least_one_entry() -> None:
    with pytest.raises(ValidationError):
        Agents(entries=[], coordination="x")


def test_skills_requires_at_least_one_entry() -> None:
    with pytest.raises(ValidationError):
        Skills(entries=[])


def test_grounding_rules_requires_at_least_one_source() -> None:
    with pytest.raises(ValidationError):
        GroundingRules(
            allowed_sources=[],
            prohibited_inferences=[],
            citation_requirement="x",
        )


def test_assumptions_made_requires_at_least_one_assumption() -> None:
    with pytest.raises(ValidationError):
        AssumptionsMade(assumptions=[], flag_back_instruction="x")


def test_chunking_default_no_instructions() -> None:
    chunk = Chunking(n=2, of=3)
    assert chunk.chunking_instructions is None


def test_nested_models_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Context(original_input="x", unknown="y")
    with pytest.raises(ValidationError):
        OutputFormat(description="x", unknown="y")
