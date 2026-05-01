"""Tests for the RunError artifact schema.

The schema models the on-disk ``error.json`` file (bible 03 §7.3 / bible
19 §5.5). The corresponding exception class
(:class:`cee.errors.exceptions.RunError`) is a separate concern — these
tests cover only the persisted artifact shape.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from roles import RoleEnum
from schemas import RunErrorArtifact


_BIBLE_03_PATH = Path.home() / "cee" / "bible" / "03_full_system_workflow.md"
_BIBLE_19_PATH = (
    Path.home() / "cee" / "bible" / "19_error_handling_failure_states.md"
)


_VALID_ERROR_TYPES = (
    "schema_violation",
    "driver_bug",
    "confirmation_timeout",
    "replay_drift",
    "unrecoverable_persistence",
    "api_failed",
    "api_rate_limited_terminal",
)


def _valid_kwargs(**overrides: object) -> dict:
    base: dict = {
        "run_id": "20260430_140000_a1b2c3d4",
        "error_type": "driver_bug",
        "failed_step": 4,
        "error_message": "AGENT_SELECTOR raised KeyError on missing slot.",
        "error_payload": {"slot": "primary_agent", "trace_id": "abc-123"},
        "recovery_suggestion": "File a bug report with the run_id.",
        "failed_at_iso_timestamp": "2026-04-30T14:05:00Z",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_run_error_minimal_valid() -> None:
    obj = RunErrorArtifact(**_valid_kwargs())
    assert obj.run_id == "20260430_140000_a1b2c3d4"
    assert obj.error_type == "driver_bug"
    assert obj.failed_step == 4
    assert obj.produced_by == "PIPELINE_DRIVER"


def test_run_error_full_valid() -> None:
    obj = RunErrorArtifact(
        run_id="20260430_140000_a1b2c3d4",
        error_type="schema_violation",
        failed_step=2,
        error_message="IntentObject failed validation: missing 'goal'.",
        error_payload={
            "module": "INTERPRETER",
            "validation_errors": [
                {"loc": ["goal"], "msg": "Field required"},
            ],
        },
        recovery_suggestion="Investigate INTERPRETER and replay.",
        failed_at_iso_timestamp="2026-04-30T14:05:00Z",
        produced_by=RoleEnum.PIPELINE_DRIVER,
    )
    assert obj.error_type == "schema_violation"
    assert obj.error_payload["module"] == "INTERPRETER"


@pytest.mark.parametrize(
    "missing_field",
    [
        "run_id",
        "error_type",
        "failed_step",
        "error_message",
        "error_payload",
        "recovery_suggestion",
        "failed_at_iso_timestamp",
    ],
)
def test_run_error_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        RunErrorArtifact(**kwargs)


def test_run_error_extra_field_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        RunErrorArtifact(**kwargs)


def test_run_error_string_whitespace_stripped() -> None:
    obj = RunErrorArtifact(
        **_valid_kwargs(
            error_message="  boom  ",
            recovery_suggestion="  retry  ",
            failed_at_iso_timestamp="  2026-04-30T14:05:00Z  ",
        )
    )
    assert obj.error_message == "boom"
    assert obj.recovery_suggestion == "retry"
    assert obj.failed_at_iso_timestamp == "2026-04-30T14:05:00Z"


def test_run_error_schema_version_present() -> None:
    assert RunErrorArtifact.SCHEMA_VERSION == "1.0.0"


def test_run_error_json_round_trip() -> None:
    original = RunErrorArtifact(**_valid_kwargs())
    payload = original.model_dump_json()
    restored = RunErrorArtifact.model_validate_json(payload)
    assert restored == original


def test_run_error_dict_round_trip() -> None:
    original = RunErrorArtifact(**_valid_kwargs())
    payload = original.model_dump()
    restored = RunErrorArtifact.model_validate(payload)
    assert restored == original


def test_run_error_field_order_stable() -> None:
    obj = RunErrorArtifact(**_valid_kwargs())
    expected_order = [
        "run_id",
        "error_type",
        "failed_step",
        "error_message",
        "error_payload",
        "recovery_suggestion",
        "failed_at_iso_timestamp",
        "produced_by",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("error_type", _VALID_ERROR_TYPES)
def test_error_type_accepts_all_seven_enum_values(error_type: str) -> None:
    obj = RunErrorArtifact(**_valid_kwargs(error_type=error_type))
    assert obj.error_type == error_type


@pytest.mark.parametrize(
    "invalid_type",
    [
        "schema_invalid",
        "SCHEMA_VIOLATION",  # uppercase rejected
        "halt_for_clarification",
        "",
        "unknown",
    ],
)
def test_error_type_must_be_valid_enum_value(invalid_type: str) -> None:
    with pytest.raises(ValidationError):
        RunErrorArtifact(**_valid_kwargs(error_type=invalid_type))


@pytest.mark.parametrize("step", [1, 5, 10])
def test_failed_step_in_range(step: int) -> None:
    obj = RunErrorArtifact(**_valid_kwargs(failed_step=step))
    assert obj.failed_step == step


@pytest.mark.parametrize("step", [0, -1, 11, 99])
def test_failed_step_out_of_range(step: int) -> None:
    with pytest.raises(ValidationError):
        RunErrorArtifact(**_valid_kwargs(failed_step=step))


def test_error_payload_accepts_arbitrary_dict() -> None:
    payload = {
        "string": "x",
        "number": 1,
        "bool": True,
        "list": [1, 2, 3],
        "nested": {"a": [{"b": "c"}]},
        "none": None,
    }
    obj = RunErrorArtifact(**_valid_kwargs(error_payload=payload))
    assert obj.error_payload == payload


def test_error_payload_accepts_empty_dict() -> None:
    obj = RunErrorArtifact(**_valid_kwargs(error_payload={}))
    assert obj.error_payload == {}


def test_error_payload_rejects_non_dict() -> None:
    with pytest.raises(ValidationError):
        RunErrorArtifact(**_valid_kwargs(error_payload=["not", "a", "dict"]))


def test_run_id_pattern_enforced() -> None:
    # Valid.
    RunErrorArtifact(**_valid_kwargs(run_id="20260430_140000_a1b2c3d4"))
    # Invalid: wrong shape.
    with pytest.raises(ValidationError):
        RunErrorArtifact(**_valid_kwargs(run_id="not-a-run-id"))


def test_error_message_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        RunErrorArtifact(**_valid_kwargs(error_message=""))
    with pytest.raises(ValidationError):
        RunErrorArtifact(**_valid_kwargs(error_message="   "))


def test_recovery_suggestion_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        RunErrorArtifact(**_valid_kwargs(recovery_suggestion=""))


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_run_error_field_set_matches_bible() -> None:
    """Bible 03 §7.3 declares: 'RunError artifact at
    ~/cee/runs/<run_id>/error.json with {failed_step, error_type,
    error_message, recovery_suggestion}.' Those four field names are the
    canonical core. The schema may extend with section-02-authorized
    contextual fields (run_id, error_payload, failed_at_iso_timestamp,
    produced_by). Bible 19 §5.5 confirms the seven RunErrorType values.
    """
    if not _BIBLE_03_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_03_PATH}")
    if not _BIBLE_19_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_19_PATH}")

    bible_03 = _BIBLE_03_PATH.read_text(encoding="utf-8")
    bible_19 = _BIBLE_19_PATH.read_text(encoding="utf-8")

    # Parse the §7.3 brace list: "{failed_step, error_type, error_message,
    # recovery_suggestion}".
    pattern = re.compile(
        r"`RunError`\s*artifact\s*at\s*`[^`]+`\s*with\s*`\{([^}]+)\}`",
        re.IGNORECASE,
    )
    match = pattern.search(bible_03)
    assert match, (
        "Could not locate the §7.3 RunError field list in bible 03"
    )
    bible_fields = {f.strip() for f in match.group(1).split(",") if f.strip()}
    assert bible_fields == {
        "failed_step",
        "error_type",
        "error_message",
        "recovery_suggestion",
    }, (
        f"Bible 03 §7.3 RunError field list drift detected: {bible_fields}"
    )

    # All bible-listed fields must be present in the schema.
    impl_fields = set(RunErrorArtifact.model_fields.keys())
    missing = bible_fields - impl_fields
    assert not missing, (
        f"RunError artifact missing bible-required fields: {sorted(missing)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )

    # All seven RunErrorType values from bible 19 §5.2 must be accepted.
    for error_type in _VALID_ERROR_TYPES:
        assert error_type in bible_19, (
            f"Bible 19 §5.2 missing expected RunErrorType value '{error_type}'"
        )
