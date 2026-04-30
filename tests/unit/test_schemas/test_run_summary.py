"""Tests for the RunSummary schema."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import RunSummary


_BIBLE_PATH = Path.home() / "cee" / "bible" / "03_full_system_workflow.md"


def _delivered_kwargs(**overrides: object) -> dict:
    base: dict = {
        "run_id": "20260430_140000_a1b2c3d4",
        "state": "delivered",
        "started_at": "2026-04-30T14:00:00Z",
        "ended_at": "2026-04-30T14:05:00Z",
        "task_type": "BUILD",
        "complexity_tier": "MEDIUM",
        "target_executor": "claude_code",
        "agent_slugs": ["primary-coder", "reviewer"],
        "skill_slugs": ["python-patterns"],
        "newly_generated_agents": [],
        "newly_generated_skills": [],
        "artifact_paths": {
            "raw_input": "raw_input.json",
            "intent": "intent.json",
            "classification": "classification.json",
            "agent_plan": "agent_plan.json",
            "skills": "skills.json",
            "execution_strategy": "execution_strategy.json",
            "prompt": "prompt.xml",
        },
        "prompt_chunks": 1,
        "halt_or_error_ref": None,
    }
    base.update(overrides)
    return base


def _paused_kwargs(**overrides: object) -> dict:
    base: dict = {
        "run_id": "20260430_140000_a1b2c3d4",
        "state": "paused",
        "started_at": "2026-04-30T14:00:00Z",
        "ended_at": "2026-04-30T14:01:00Z",
        "task_type": None,
        "complexity_tier": None,
        "target_executor": "claude_code",
        "artifact_paths": {"raw_input": "raw_input.json"},
        "prompt_chunks": 0,
        "halt_or_error_ref": "clarification.json",
    }
    base.update(overrides)
    return base


def _failed_kwargs(**overrides: object) -> dict:
    base: dict = {
        "run_id": "20260430_140000_a1b2c3d4",
        "state": "failed",
        "started_at": "2026-04-30T14:00:00Z",
        "ended_at": "2026-04-30T14:01:30Z",
        "task_type": None,
        "complexity_tier": None,
        "target_executor": "claude_code",
        "artifact_paths": {"raw_input": "raw_input.json"},
        "prompt_chunks": 0,
        "halt_or_error_ref": "error.json",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_run_summary_minimal_valid() -> None:
    obj = RunSummary(**_delivered_kwargs())
    assert obj.run_id == "20260430_140000_a1b2c3d4"
    assert obj.state == "delivered"
    assert obj.produced_by == "PIPELINE_DRIVER"
    assert obj.halt_or_error_ref is None


def test_run_summary_full_valid() -> None:
    obj = RunSummary(
        **_delivered_kwargs(
            task_type="ORCHESTRATE",
            complexity_tier="EXTREME",
            agent_slugs=["a", "b", "c"],
            skill_slugs=["s1", "s2"],
            newly_generated_agents=["new-agent"],
            newly_generated_skills=["new-skill"],
            prompt_chunks=3,
        )
    )
    assert obj.task_type == "ORCHESTRATE"
    assert obj.complexity_tier == "EXTREME"
    assert obj.prompt_chunks == 3
    assert obj.newly_generated_agents == ["new-agent"]


@pytest.mark.parametrize(
    "missing_field",
    [
        "run_id",
        "state",
        "started_at",
        "ended_at",
        "target_executor",
        "prompt_chunks",
    ],
)
def test_run_summary_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _delivered_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        RunSummary(**kwargs)


def test_run_summary_extra_field_rejected() -> None:
    kwargs = _delivered_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        RunSummary(**kwargs)


def test_run_summary_string_whitespace_stripped() -> None:
    obj = RunSummary(
        **_delivered_kwargs(
            started_at="  2026-04-30T14:00:00Z  ",
            ended_at="  2026-04-30T14:05:00Z  ",
        )
    )
    assert obj.started_at == "2026-04-30T14:00:00Z"
    assert obj.ended_at == "2026-04-30T14:05:00Z"


def test_run_summary_schema_version_present() -> None:
    assert RunSummary.SCHEMA_VERSION == "1.0.0"


def test_run_summary_json_round_trip() -> None:
    original = RunSummary(**_delivered_kwargs())
    payload = original.model_dump_json()
    restored = RunSummary.model_validate_json(payload)
    assert restored == original


def test_run_summary_dict_round_trip() -> None:
    original = RunSummary(**_delivered_kwargs())
    payload = original.model_dump()
    restored = RunSummary.model_validate(payload)
    assert restored == original


def test_run_summary_field_order_stable() -> None:
    obj = RunSummary(**_delivered_kwargs())
    expected_order = [
        "run_id",
        "state",
        "started_at",
        "ended_at",
        "task_type",
        "complexity_tier",
        "target_executor",
        "agent_slugs",
        "skill_slugs",
        "newly_generated_agents",
        "newly_generated_skills",
        "artifact_paths",
        "prompt_chunks",
        "halt_or_error_ref",
        "produced_by",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific                                                              #
# --------------------------------------------------------------------------- #


def test_delivered_state_no_halt_ref_required() -> None:
    obj = RunSummary(**_delivered_kwargs())
    assert obj.halt_or_error_ref is None
    assert obj.prompt_chunks >= 1


def test_delivered_state_rejects_halt_ref() -> None:
    with pytest.raises(ValidationError):
        RunSummary(
            **_delivered_kwargs(halt_or_error_ref="clarification.json")
        )


def test_delivered_state_requires_prompt_chunks_at_least_one() -> None:
    with pytest.raises(ValidationError):
        RunSummary(**_delivered_kwargs(prompt_chunks=0))


def test_paused_state_requires_halt_ref() -> None:
    # None must fail.
    with pytest.raises(ValidationError):
        RunSummary(**_paused_kwargs(halt_or_error_ref=None))
    # Empty string must fail.
    with pytest.raises(ValidationError):
        RunSummary(**_paused_kwargs(halt_or_error_ref=""))
    # Non-empty path passes.
    obj = RunSummary(**_paused_kwargs(halt_or_error_ref="clarification.json"))
    assert obj.halt_or_error_ref == "clarification.json"


def test_failed_state_requires_halt_ref() -> None:
    with pytest.raises(ValidationError):
        RunSummary(**_failed_kwargs(halt_or_error_ref=None))
    with pytest.raises(ValidationError):
        RunSummary(**_failed_kwargs(halt_or_error_ref=""))
    obj = RunSummary(**_failed_kwargs(halt_or_error_ref="error.json"))
    assert obj.halt_or_error_ref == "error.json"


def test_paused_state_allows_zero_prompt_chunks() -> None:
    """When the Run halts before prompt build, no prompt has been
    produced. The schema must allow ``prompt_chunks = 0`` for non-
    delivered states.
    """
    obj = RunSummary(**_paused_kwargs(prompt_chunks=0))
    assert obj.prompt_chunks == 0


def test_state_must_be_valid_enum_value() -> None:
    with pytest.raises(ValidationError):
        RunSummary(**_delivered_kwargs(state="aborted"))
    with pytest.raises(ValidationError):
        RunSummary(**_delivered_kwargs(state="halted"))


def test_task_type_optional() -> None:
    obj = RunSummary(**_paused_kwargs(task_type=None))
    assert obj.task_type is None


def test_task_type_must_be_valid_enum_value() -> None:
    with pytest.raises(ValidationError):
        RunSummary(**_delivered_kwargs(task_type="UNKNOWN"))


def test_complexity_tier_must_be_valid_enum_value() -> None:
    with pytest.raises(ValidationError):
        RunSummary(**_delivered_kwargs(complexity_tier="MID"))


def test_target_executor_must_be_valid_enum_value() -> None:
    with pytest.raises(ValidationError):
        RunSummary(**_delivered_kwargs(target_executor="claude_unknown"))


def test_artifact_paths_dict_accepts_string_values() -> None:
    paths = {
        "raw_input": "raw_input.json",
        "intent": "intent.json",
        "prompt": "prompt.xml",
        "summary": "summary.json",
    }
    obj = RunSummary(**_delivered_kwargs(artifact_paths=paths))
    assert obj.artifact_paths == paths


def test_artifact_paths_rejects_non_string_values() -> None:
    with pytest.raises(ValidationError):
        RunSummary(
            **_delivered_kwargs(artifact_paths={"raw_input": 123})
        )


def test_artifact_paths_can_be_empty() -> None:
    """The dict default factory produces empty dicts; Runs that halt
    before any artifact is written would have an empty mapping.
    """
    obj = RunSummary(**_paused_kwargs(artifact_paths={}))
    assert obj.artifact_paths == {}


def test_slug_lists_default_to_empty() -> None:
    obj = RunSummary(**_paused_kwargs())
    assert obj.agent_slugs == []
    assert obj.skill_slugs == []
    assert obj.newly_generated_agents == []
    assert obj.newly_generated_skills == []


def test_slug_list_default_factories_independent() -> None:
    a = RunSummary(**_paused_kwargs())
    b = RunSummary(**_paused_kwargs())
    a.agent_slugs.append("x")
    assert b.agent_slugs == []


def test_run_id_pattern_enforced() -> None:
    with pytest.raises(ValidationError):
        RunSummary(**_delivered_kwargs(run_id="not-a-run-id"))


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_run_summary_field_set_matches_bible() -> None:
    """Bible 03 §7.1 lists the outputs of a successful Run (FinalPrompt,
    step artifacts on disk, Obsidian Run summary, promotion queue,
    audit log entries). Bible 03 Step 9 (§5.4 line 138) declares the
    artifact path 'summary.json' and its role as the index of all step
    artifacts. The bible does not enumerate field names in a JSON block,
    so the drift detector asserts narrative grounding: the artifact
    path is referenced, the 'references all step artifacts' role is
    declared, and the schema reflects the runtime states from §3 and
    §5.7.
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")

    # Bible 03 must reference the persisted artifact path.
    assert "summary.json" in bible_text, (
        "Bible 03 must reference the persisted path 'summary.json'"
    )

    # Bible 03 Step 9 declares the summary's role as the artifact index.
    assert "references all step artifacts" in bible_text, (
        "Bible 03 Step 9 must declare summary's 'references all step "
        "artifacts' role"
    )

    # Bible 03 §3 declares the three high-level terminal states. Our
    # state Literal uses the runtime labels ('delivered', 'paused',
    # 'failed'); 'delivered' appears verbatim, 'paused' surfaces in
    # §5.3 ("the Run is in state ``paused``") and §5.7
    # (RunResult(state="paused" / "failed")).
    assert "delivered" in bible_text, (
        "Bible 03 must reference the 'delivered' terminal state"
    )
    assert "paused" in bible_text, (
        "Bible 03 must reference the 'paused' runtime state"
    )

    # The schema must include fields that satisfy the bible's narrative.
    impl_fields = set(RunSummary.model_fields.keys())
    bible_required = {
        "run_id",
        "state",
        "artifact_paths",  # the "references all step artifacts" mapping
    }
    missing = bible_required - impl_fields
    assert not missing, (
        f"RunSummary missing bible-grounded fields: {sorted(missing)}\n"
        f"Impl: {sorted(impl_fields)}"
    )
