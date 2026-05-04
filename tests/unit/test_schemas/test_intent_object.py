"""Tests for the IntentObject schema."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from roles import RoleEnum
from schemas import IntentObject


_BIBLE_PATH = Path.home() / "cee" / "bible" / "00_project_vision.md"


def _valid_kwargs() -> dict:
    return {
        "goal": "Refactor the auth module to use JWT.",
        "deliverable": "A patched auth module file.",
        "ambiguity_score": 0.2,
        "domain": "code",
    }


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_intent_object_minimal_valid() -> None:
    obj = IntentObject(**_valid_kwargs())
    assert obj.goal.startswith("Refactor")
    assert obj.constraints == []
    assert obj.implicit_assumptions == []
    assert obj.raw_signals == []
    assert obj.produced_by == "INTERPRETER"


def test_intent_object_full_valid() -> None:
    obj = IntentObject(
        goal="Refactor the auth module.",
        deliverable="A patched auth.ts.",
        constraints=["Python 3.11+", "no external API calls"],
        implicit_assumptions=["assumed JWT format"],
        ambiguity_score=0.42,
        domain="code",
        raw_signals=["urgency: high"],
        produced_by=RoleEnum.INTERPRETER,
    )
    assert obj.constraints == ["Python 3.11+", "no external API calls"]
    assert obj.implicit_assumptions == ["assumed JWT format"]


@pytest.mark.parametrize(
    "missing_field",
    ["goal", "deliverable", "ambiguity_score", "domain"],
)
def test_intent_object_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        IntentObject(**kwargs)


def test_intent_object_extra_field_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        IntentObject(**kwargs)


def test_intent_object_string_whitespace_stripped() -> None:
    kwargs = _valid_kwargs()
    kwargs["goal"] = "  trimmed goal  "
    obj = IntentObject(**kwargs)
    assert obj.goal == "trimmed goal"


def test_intent_object_schema_version_present() -> None:
    assert IntentObject.SCHEMA_VERSION == "1.0.0"


def test_intent_object_json_round_trip() -> None:
    original = IntentObject(**_valid_kwargs())
    payload = original.model_dump_json()
    restored = IntentObject.model_validate_json(payload)
    assert restored == original


def test_intent_object_dict_round_trip() -> None:
    original = IntentObject(**_valid_kwargs())
    payload = original.model_dump()
    restored = IntentObject.model_validate(payload)
    assert restored == original


def test_intent_object_field_order_stable() -> None:
    obj = IntentObject(**_valid_kwargs())
    expected_order = [
        "goal",
        "deliverable",
        "constraints",
        "implicit_assumptions",
        "ambiguity_score",
        "domain",
        "raw_signals",
        "produced_by",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific                                                              #
# --------------------------------------------------------------------------- #


def test_ambiguity_score_bounds() -> None:
    valid = _valid_kwargs()
    valid["ambiguity_score"] = 0.0
    IntentObject(**valid)
    valid["ambiguity_score"] = 1.0
    IntentObject(**valid)

    invalid = _valid_kwargs()
    invalid["ambiguity_score"] = -0.01
    with pytest.raises(ValidationError):
        IntentObject(**invalid)
    invalid["ambiguity_score"] = 1.01
    with pytest.raises(ValidationError):
        IntentObject(**invalid)


@pytest.mark.parametrize(
    "domain",
    ["code", "writing", "analysis", "research", "ops", "personal", "other"],
)
def test_domain_accepts_all_seven_values(domain: str) -> None:
    kwargs = _valid_kwargs()
    kwargs["domain"] = domain
    IntentObject(**kwargs)


def test_domain_rejects_unknown() -> None:
    kwargs = _valid_kwargs()
    kwargs["domain"] = "unknown_domain"
    with pytest.raises(ValidationError):
        IntentObject(**kwargs)


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_intent_object_field_set_matches_bible() -> None:
    """Bible 00 §5 Step 2 declares IntentObject with seven fields.

    The canonical contract lives in the ``javascript`` code-fence under
    ``### Step 2 — Interpretation``. ``produced_by`` is permitted as an
    extra (authorized by section 02's role tracking convention, mirroring
    the RawInput + Classification field-set tests).
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")

    # Anchor the IntentObject code-fence inside §5 Step 2.
    section_match = re.search(
        r"###\s*Step\s*2\s*—\s*Interpretation.*?```javascript\s*\{(.*?)\}\s*```",
        bible_text,
        re.DOTALL,
    )
    assert section_match, (
        "Could not locate IntentObject javascript code-fence under "
        "bible 00 §5 Step 2"
    )

    # The fence is pseudo-JSON (values include `0.0–1.0`, `key | key`),
    # not parseable by json.loads. Extract field names by matching the
    # leading ``"<name>":`` of each field line.
    field_block = section_match.group(1)
    bible_fields = set(re.findall(r'"(\w+)"\s*:', field_block))

    assert bible_fields, (
        "Bible §5 Step 2 IntentObject code-fence yielded zero field "
        "names — anchor or fence shape has drifted"
    )

    impl_fields = set(IntentObject.model_fields.keys())

    missing = bible_fields - impl_fields
    assert not missing, (
        f"IntentObject is missing bible-required fields: {sorted(missing)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )

    extras = impl_fields - bible_fields - {"produced_by"}
    assert not extras, (
        f"IntentObject has unauthorized extra fields: {sorted(extras)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )
