"""Tests for the ClarificationRequest schema."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from roles import RoleEnum
from schemas import ClarificationQuestion, ClarificationRequest


_BIBLE_03_PATH = Path.home() / "cee" / "bible" / "03_full_system_workflow.md"
_BIBLE_19_PATH = (
    Path.home() / "cee" / "bible" / "19_error_handling_failure_states.md"
)


def _valid_question_kwargs(**overrides: object) -> dict:
    base: dict = {
        "id": "auth-target",
        "question": "Which auth provider should we use?",
        "context": "Input mentions 'auth' without specifying provider.",
        "expected_answer_type": "free_text",
        "choices": None,
    }
    base.update(overrides)
    return base


def _valid_request_kwargs(**overrides: object) -> dict:
    base: dict = {
        "run_id": "20260430_140000_a1b2c3d4",
        "questions": [ClarificationQuestion(**_valid_question_kwargs())],
        "paused_at_step": 1,
        "intent_object_so_far": {"goal": "refactor auth"},
        "paused_at_iso_timestamp": "2026-04-30T14:00:00Z",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_clarification_request_minimal_valid() -> None:
    obj = ClarificationRequest(**_valid_request_kwargs())
    assert obj.run_id == "20260430_140000_a1b2c3d4"
    assert obj.paused_at_step == 1
    assert obj.produced_by == "INTERPRETER"
    assert len(obj.questions) == 1
    assert obj.intent_object_so_far == {"goal": "refactor auth"}


def test_clarification_request_full_valid() -> None:
    questions = [
        ClarificationQuestion(
            id="auth-target",
            question="Which auth provider should we use?",
            context="Input is ambiguous re: provider.",
            expected_answer_type="choice",
            choices=["clerk", "supabase", "auth0"],
        ),
        ClarificationQuestion(
            id="rollout",
            question="Should we ship behind a feature flag?",
            context=None,
            expected_answer_type="yes_no",
            choices=None,
        ),
    ]
    obj = ClarificationRequest(
        run_id="20260430_140000_a1b2c3d4",
        questions=questions,
        paused_at_step=3,
        intent_object_so_far={"goal": "refactor auth", "_partial": True},
        paused_at_iso_timestamp="2026-04-30T14:00:00Z",
        produced_by=RoleEnum.INTERPRETER,
    )
    assert len(obj.questions) == 2
    assert obj.paused_at_step == 3


@pytest.mark.parametrize(
    "missing_field",
    [
        "run_id",
        "questions",
        "paused_at_step",
        "intent_object_so_far",
        "paused_at_iso_timestamp",
    ],
)
def test_clarification_request_missing_required_field_raises(
    missing_field: str,
) -> None:
    kwargs = _valid_request_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        ClarificationRequest(**kwargs)


def test_clarification_request_extra_field_rejected() -> None:
    kwargs = _valid_request_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        ClarificationRequest(**kwargs)


def test_clarification_request_string_whitespace_stripped() -> None:
    obj = ClarificationRequest(
        **_valid_request_kwargs(
            paused_at_iso_timestamp="  2026-04-30T14:00:00Z  ",
        )
    )
    assert obj.paused_at_iso_timestamp == "2026-04-30T14:00:00Z"


def test_clarification_request_schema_version_present() -> None:
    assert ClarificationRequest.SCHEMA_VERSION == "1.0.0"
    assert ClarificationQuestion.SCHEMA_VERSION == "1.0.0"


def test_clarification_request_json_round_trip() -> None:
    original = ClarificationRequest(**_valid_request_kwargs())
    payload = original.model_dump_json()
    restored = ClarificationRequest.model_validate_json(payload)
    assert restored == original


def test_clarification_request_dict_round_trip() -> None:
    original = ClarificationRequest(**_valid_request_kwargs())
    payload = original.model_dump()
    restored = ClarificationRequest.model_validate(payload)
    assert restored == original


def test_clarification_request_field_order_stable() -> None:
    obj = ClarificationRequest(**_valid_request_kwargs())
    expected_order = [
        "run_id",
        "questions",
        "paused_at_step",
        "intent_object_so_far",
        "paused_at_iso_timestamp",
        "produced_by",
    ]
    assert list(obj.model_dump().keys()) == expected_order


def test_clarification_question_field_order_stable() -> None:
    q = ClarificationQuestion(**_valid_question_kwargs())
    expected_order = [
        "id",
        "question",
        "context",
        "expected_answer_type",
        "choices",
    ]
    assert list(q.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific                                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "valid_run_id",
    [
        "20260430_140000_a1b2c3d4",
        "20990101_000000_00000000",
        "19700101_000000_ffffffff",
    ],
)
def test_run_id_pattern_accepts_valid(valid_run_id: str) -> None:
    obj = ClarificationRequest(**_valid_request_kwargs(run_id=valid_run_id))
    assert obj.run_id == valid_run_id


@pytest.mark.parametrize(
    "invalid_run_id",
    [
        "2026-04-30_14_00_00_a1b2c3d4",  # wrong separators
        "20260430_140000_A1B2C3D4",  # uppercase hex
        "20260430_140000_a1b2c3d",  # short hex
        "20260430_140000_a1b2c3d44",  # long hex
        "26260430_140000_a1b2c3d4-extra",  # trailing junk
        "",
    ],
)
def test_run_id_pattern_rejects_invalid(invalid_run_id: str) -> None:
    with pytest.raises(ValidationError):
        ClarificationRequest(**_valid_request_kwargs(run_id=invalid_run_id))


@pytest.mark.parametrize("step", [1, 5, 10])
def test_paused_at_step_in_range(step: int) -> None:
    obj = ClarificationRequest(**_valid_request_kwargs(paused_at_step=step))
    assert obj.paused_at_step == step


@pytest.mark.parametrize("step", [0, -1, 11, 99])
def test_paused_at_step_out_of_range(step: int) -> None:
    with pytest.raises(ValidationError):
        ClarificationRequest(**_valid_request_kwargs(paused_at_step=step))


def test_questions_non_empty() -> None:
    with pytest.raises(ValidationError):
        ClarificationRequest(**_valid_request_kwargs(questions=[]))


def test_choice_question_must_have_choices() -> None:
    # choices=None should fail.
    with pytest.raises(ValidationError):
        ClarificationQuestion(
            id="auth-target",
            question="Which one?",
            expected_answer_type="choice",
            choices=None,
        )

    # choices=[] should also fail.
    with pytest.raises(ValidationError):
        ClarificationQuestion(
            id="auth-target",
            question="Which one?",
            expected_answer_type="choice",
            choices=[],
        )

    # choices=[...] passes.
    q = ClarificationQuestion(
        id="auth-target",
        question="Which one?",
        expected_answer_type="choice",
        choices=["a", "b"],
    )
    assert q.choices == ["a", "b"]


def test_yes_no_question_choices_optional() -> None:
    """For non-choice questions, ``choices`` defaults to None and is not
    required by the validator. The field is structurally optional —
    keeping it on every question type lets the resume validator inspect
    the same shape regardless of expected_answer_type.
    """
    q = ClarificationQuestion(
        id="ship-it",
        question="Ship behind a flag?",
        expected_answer_type="yes_no",
    )
    assert q.choices is None


def test_question_id_must_be_slug() -> None:
    with pytest.raises(ValidationError):
        ClarificationQuestion(
            id="Has Spaces",
            question="?",
            expected_answer_type="free_text",
        )
    with pytest.raises(ValidationError):
        ClarificationQuestion(
            id="UPPER",
            question="?",
            expected_answer_type="free_text",
        )


def test_intent_object_so_far_accepts_arbitrary_dict() -> None:
    payload = {
        "goal": "x",
        "constraints": ["a", "b"],
        "metadata": {"nested": True, "score": 0.42},
    }
    obj = ClarificationRequest(
        **_valid_request_kwargs(intent_object_so_far=payload)
    )
    assert obj.intent_object_so_far == payload


def test_intent_object_so_far_rejects_non_dict() -> None:
    with pytest.raises(ValidationError):
        ClarificationRequest(
            **_valid_request_kwargs(intent_object_so_far="not a dict")
        )


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_clarification_request_field_set_matches_bible() -> None:
    """Bible 03 §5.3 names the artifact and its filesystem path. Bible 19
    §5.4 names the halt type that triggers it. The bible doesn't enumerate
    field names in a JSON block, but it mandates: the artifact exists, it
    contains the questions, and it pauses the Run. Drift detector asserts
    those references are present and that the schema reflects them.
    """
    if not _BIBLE_03_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_03_PATH}")
    if not _BIBLE_19_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_19_PATH}")

    bible_03 = _BIBLE_03_PATH.read_text(encoding="utf-8")
    bible_19 = _BIBLE_19_PATH.read_text(encoding="utf-8")

    # Bible 03 §5.3 references — artifact name and path.
    assert "ClarificationRequest" in bible_03, (
        "Bible 03 must reference the artifact name 'ClarificationRequest'"
    )
    assert "clarification.json" in bible_03, (
        "Bible 03 must reference the persisted path 'clarification.json'"
    )
    assert "questions" in bible_03, (
        "Bible 03 §5.3 must reference 'questions' (the question payload)"
    )

    # Bible 19 §5.4 references — the halt type.
    assert "PAUSED_FOR_CLARIFICATION" in bible_19, (
        "Bible 19 must reference the PAUSED_FOR_CLARIFICATION halt type"
    )

    # Schema must include fields covering the bible's narrative:
    # - questions (the payload)
    # - run_id (artifact addressing per bible 04)
    # - intent_object_so_far (the partial state preserved per §5.3)
    # - paused_at_step (the resume re-entry point per §5.3 step 4)
    impl_fields = set(ClarificationRequest.model_fields.keys())
    bible_required = {
        "questions",
        "run_id",
        "intent_object_so_far",
        "paused_at_step",
    }
    missing = bible_required - impl_fields
    assert not missing, (
        f"ClarificationRequest is missing bible-grounded fields: "
        f"{sorted(missing)}\nImpl: {sorted(impl_fields)}"
    )
