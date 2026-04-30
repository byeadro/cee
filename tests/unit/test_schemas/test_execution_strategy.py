"""Tests for the ExecutionStrategy schema."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import ExecutionStrategy, StepSpec


_BIBLE_PATH = Path.home() / "cee" / "bible" / "03_full_system_workflow.md"


def _step(n: int, action: str = "do thing", **extra) -> StepSpec:
    return StepSpec(n=n, action=action, **extra)


def _valid_kwargs(num_steps: int = 1) -> dict:
    return {
        "steps": [_step(i) for i in range(1, num_steps + 1)],
        "estimated_cost_tokens": 1000,
    }


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_execution_strategy_minimal_valid() -> None:
    obj = ExecutionStrategy(**_valid_kwargs())
    assert len(obj.steps) == 1
    assert obj.checkpoints == []
    assert obj.stop_conditions == []
    assert obj.produced_by == "STRATEGY_BUILDER"


def test_execution_strategy_full_valid() -> None:
    obj = ExecutionStrategy(
        steps=[
            StepSpec(n=1, action="Read input", agent="reader-agent"),
            StepSpec(
                n=2,
                action="Process",
                checkpoint=True,
                expected_artifacts=["result.json"],
            ),
            StepSpec(n=3, action="Write output"),
        ],
        checkpoints=[2],
        stop_conditions=["any step exceeds 10000 tokens", "critic blocks"],
        estimated_cost_tokens=5000,
        produced_by="STRATEGY_BUILDER",
    )
    assert len(obj.steps) == 3
    assert obj.checkpoints == [2]
    assert obj.stop_conditions == [
        "any step exceeds 10000 tokens",
        "critic blocks",
    ]


@pytest.mark.parametrize("missing_field", ["steps", "estimated_cost_tokens"])
def test_execution_strategy_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        ExecutionStrategy(**kwargs)


def test_execution_strategy_extra_field_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        ExecutionStrategy(**kwargs)


def test_execution_strategy_string_whitespace_stripped() -> None:
    obj = ExecutionStrategy(
        steps=[StepSpec(n=1, action="  trimmed action  ")],
        estimated_cost_tokens=0,
    )
    assert obj.steps[0].action == "trimmed action"


def test_execution_strategy_schema_version_present() -> None:
    assert ExecutionStrategy.SCHEMA_VERSION == "1.0.0"
    assert StepSpec.SCHEMA_VERSION == "1.0.0"


def test_execution_strategy_json_round_trip() -> None:
    original = ExecutionStrategy(**_valid_kwargs(num_steps=3))
    payload = original.model_dump_json()
    restored = ExecutionStrategy.model_validate_json(payload)
    assert restored == original


def test_execution_strategy_dict_round_trip() -> None:
    original = ExecutionStrategy(**_valid_kwargs(num_steps=3))
    payload = original.model_dump()
    restored = ExecutionStrategy.model_validate(payload)
    assert restored == original


def test_execution_strategy_field_order_stable() -> None:
    obj = ExecutionStrategy(**_valid_kwargs())
    expected_order = [
        "steps",
        "checkpoints",
        "stop_conditions",
        "estimated_cost_tokens",
        "produced_by",
    ]
    assert list(obj.model_dump().keys()) == expected_order


def test_step_spec_field_order_stable() -> None:
    step = StepSpec(n=1, action="x")
    expected_order = ["n", "action", "agent", "checkpoint", "expected_artifacts"]
    assert list(step.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific validators                                                   #
# --------------------------------------------------------------------------- #


def test_step_n_values_sequential_from_one() -> None:
    # Valid: 1, 2, 3.
    ExecutionStrategy(
        steps=[_step(1), _step(2), _step(3)],
        estimated_cost_tokens=0,
    )

    # Invalid: starts at 2.
    with pytest.raises(ValidationError, match="must be 1"):
        ExecutionStrategy(
            steps=[_step(2), _step(3)],
            estimated_cost_tokens=0,
        )

    # Invalid: gap.
    with pytest.raises(ValidationError, match="must be 2"):
        ExecutionStrategy(
            steps=[_step(1), _step(3)],
            estimated_cost_tokens=0,
        )

    # Invalid: out of order.
    with pytest.raises(ValidationError):
        ExecutionStrategy(
            steps=[_step(1), _step(3), _step(2)],
            estimated_cost_tokens=0,
        )

    # Invalid: duplicate.
    with pytest.raises(ValidationError):
        ExecutionStrategy(
            steps=[_step(1), _step(1)],
            estimated_cost_tokens=0,
        )


def test_estimated_cost_tokens_non_negative() -> None:
    # Zero is allowed.
    ExecutionStrategy(steps=[_step(1)], estimated_cost_tokens=0)
    # Negative rejected.
    with pytest.raises(ValidationError):
        ExecutionStrategy(steps=[_step(1)], estimated_cost_tokens=-1)


def test_empty_steps_list_rejected() -> None:
    with pytest.raises(ValidationError):
        ExecutionStrategy(steps=[], estimated_cost_tokens=0)


def test_step_n_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        StepSpec(n=0, action="x")


def test_step_action_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        StepSpec(n=1, action="")


def test_checkpoints_reference_valid_steps() -> None:
    # Valid.
    ExecutionStrategy(
        steps=[_step(1), _step(2)],
        checkpoints=[1, 2],
        estimated_cost_tokens=0,
    )
    # Invalid: 3 not in steps.
    with pytest.raises(ValidationError, match="does not reference"):
        ExecutionStrategy(
            steps=[_step(1), _step(2)],
            checkpoints=[3],
            estimated_cost_tokens=0,
        )


def test_stop_conditions_default_empty_and_accepts_strings() -> None:
    obj_empty = ExecutionStrategy(steps=[_step(1)], estimated_cost_tokens=0)
    assert obj_empty.stop_conditions == []

    obj_with = ExecutionStrategy(
        steps=[_step(1)],
        stop_conditions=["budget exceeded", "validation gate fails"],
        estimated_cost_tokens=0,
    )
    assert obj_with.stop_conditions == [
        "budget exceeded",
        "validation gate fails",
    ]


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_execution_strategy_field_set_matches_bible() -> None:
    """Bible 03 Step 6 declares ExecutionStrategy with
    {steps[], checkpoints[], stop_conditions[], estimated_cost_tokens}.
    Implementation must include all bible fields. ``produced_by`` is
    permitted (section 02 role tracking).
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")

    # Find: "ExecutionStrategy with `{steps[], checkpoints[], ...}`"
    pattern = re.compile(
        r"`ExecutionStrategy`\s*with\s*`\{([^}]+)\}`",
        re.IGNORECASE,
    )
    match = pattern.search(bible_text)
    assert match, (
        "Could not locate ExecutionStrategy field list in bible 03 Step 6"
    )

    raw_fields = match.group(1).split(",")
    bible_fields = {f.strip().rstrip("[]").strip() for f in raw_fields if f.strip()}

    impl_fields = set(ExecutionStrategy.model_fields.keys())

    missing = bible_fields - impl_fields
    assert not missing, (
        f"ExecutionStrategy missing bible-required fields: {sorted(missing)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )
