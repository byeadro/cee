"""Tests for the Classification schema."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from roles import RoleEnum
from schemas import (
    CandidateScore,
    Classification,
    ClassificationAudit,
    ClassificationFlags,
    ComplexityComponents,
    FlagTriggers,
)


_BIBLE_PATH = Path.home() / "cee" / "bible" / "08_task_classification_engine.md"


def _components(a: int = 5, b: int = 5, c: int = 5, d: int = 5) -> dict:
    return {
        "input_ambiguity": a,
        "output_structure": b,
        "agent_count_required": c,
        "skill_count_required": d,
    }


def _flags(**overrides: bool) -> dict:
    base = {
        "needs_grounding": False,
        "sensitive_data": False,
        "destructive_potential": False,
        "requires_human_gate": False,
    }
    base.update(overrides)
    return base


def _audit(
    precedence: str = "BUILD",
    tier_escalation: bool = False,
    extreme_forced: bool = False,
    triggers: dict | None = None,
) -> dict:
    return {
        "task_type_precedence_fired": precedence,
        "tier_escalation_applied": tier_escalation,
        "extreme_human_gate_forced": extreme_forced,
        "flag_triggers": triggers or {},
    }


def _valid_kwargs(
    score: int = 20,
    tier: str = "LOW",
    components: dict | None = None,
    flags: dict | None = None,
    audit: dict | None = None,
) -> dict:
    return {
        "task_type": "BUILD",
        "complexity_score": score,
        "complexity_tier": tier,
        "complexity_components": components or _components(),
        "flags": flags or _flags(),
        "audit": audit or _audit(),
    }


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_classification_minimal_valid() -> None:
    obj = Classification(**_valid_kwargs())
    assert obj.task_type == "BUILD"
    assert obj.complexity_tier == "LOW"
    assert obj.task_type_candidates == []
    assert obj.audit.task_type_precedence_fired == "BUILD"
    assert obj.audit.tier_escalation_applied is False
    assert obj.produced_by == "CLASSIFIER"


def test_classification_full_valid() -> None:
    obj = Classification(
        task_type="ANALYZE",
        task_type_candidates=[
            CandidateScore(value="ANALYZE", confidence=0.82),
            CandidateScore(value="DECIDE", confidence=0.34),
        ],
        complexity_score=42,
        complexity_tier="MEDIUM",
        complexity_components=ComplexityComponents(**_components(8, 14, 10, 10)),
        flags=ClassificationFlags(**_flags(needs_grounding=True)),
        audit=ClassificationAudit(
            task_type_precedence_fired="ANALYZE",
            tier_escalation_applied=False,
            extreme_human_gate_forced=False,
            flag_triggers=FlagTriggers(
                needs_grounding=["RESEARCH-like phrasing in goal"],
            ),
        ),
        produced_by=RoleEnum.CLASSIFIER,
    )
    assert obj.flags.needs_grounding is True
    assert len(obj.task_type_candidates) == 2
    assert obj.audit.flag_triggers.needs_grounding == [
        "RESEARCH-like phrasing in goal"
    ]


@pytest.mark.parametrize(
    "missing_field",
    [
        "task_type",
        "complexity_score",
        "complexity_tier",
        "complexity_components",
        "flags",
        "audit",
    ],
)
def test_classification_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        Classification(**kwargs)


def test_classification_extra_field_rejected() -> None:
    kwargs = _valid_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        Classification(**kwargs)


def test_classification_produced_by_rejects_whitespace_padded_string() -> None:
    """produced_by is a RoleEnum (bible 02 §4); enum validation runs before
    str_strip_whitespace, so padded values are rejected outright rather than
    silently coerced. Documents the stricter contract introduced by task 9."""
    kwargs = _valid_kwargs()
    kwargs["produced_by"] = "  CLASSIFIER  "
    with pytest.raises(ValidationError):
        Classification(**kwargs)


def test_classification_schema_version_present() -> None:
    assert Classification.SCHEMA_VERSION == "1.0.0"
    assert ComplexityComponents.SCHEMA_VERSION == "1.0.0"
    assert ClassificationFlags.SCHEMA_VERSION == "1.0.0"
    assert CandidateScore.SCHEMA_VERSION == "1.0.0"
    assert FlagTriggers.SCHEMA_VERSION == "1.0.0"
    assert ClassificationAudit.SCHEMA_VERSION == "1.0.0"


def test_classification_json_round_trip() -> None:
    original = Classification(**_valid_kwargs())
    payload = original.model_dump_json()
    restored = Classification.model_validate_json(payload)
    assert restored == original


def test_classification_dict_round_trip() -> None:
    original = Classification(**_valid_kwargs())
    payload = original.model_dump()
    restored = Classification.model_validate(payload)
    assert restored == original


def test_classification_field_order_stable() -> None:
    obj = Classification(**_valid_kwargs())
    expected_order = [
        "task_type",
        "task_type_candidates",
        "complexity_score",
        "complexity_tier",
        "complexity_components",
        "flags",
        "audit",
        "produced_by",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific validators                                                   #
# --------------------------------------------------------------------------- #


def test_complexity_score_must_equal_components_sum() -> None:
    # components sum to 20; score 20 OK.
    Classification(**_valid_kwargs(score=20))

    # mismatch: score 30 vs components sum 20.
    with pytest.raises(ValidationError, match="must equal"):
        Classification(**_valid_kwargs(score=30))


@pytest.mark.parametrize(
    "score,tier",
    [
        (0, "LOW"),
        (24, "LOW"),
        (25, "MEDIUM"),
        (49, "MEDIUM"),
        (50, "HIGH"),
        (74, "HIGH"),
        (75, "EXTREME"),
        (100, "EXTREME"),
    ],
)
def test_complexity_tier_aligns_with_score(score: int, tier: str) -> None:
    """Bible 08 §5.3 thresholds: LOW [0,25), MEDIUM [25,50), HIGH [50,75), EXTREME [75,100]."""
    # Build components that sum to score.
    a = min(25, score)
    b = min(25, max(0, score - 25))
    c = min(25, max(0, score - 50))
    d = min(25, max(0, score - 75))
    components = _components(a, b, c, d)
    assert a + b + c + d == score, "test setup error"
    # EXTREME tier requires the §10.10 trigger; provide a non-empty list.
    if tier == "EXTREME":
        flags = _flags()
        triggers = {"requires_human_gate": ["EXTREME complexity (auto-forced)"]}
    else:
        flags = _flags()
        triggers = {}
    Classification(
        task_type="BUILD",
        complexity_score=score,
        complexity_tier=tier,
        complexity_components=components,
        flags=flags,
        audit=_audit(triggers=triggers),
    )


def test_complexity_tier_mismatch_rejected() -> None:
    # score=20 is LOW; declaring HIGH should fail.
    with pytest.raises(ValidationError, match="does not match"):
        Classification(**_valid_kwargs(score=20, tier="HIGH"))


def test_extreme_tier_forces_requires_human_gate() -> None:
    """EXTREME tier (≥75) coerces requires_human_gate=True per bible 08 Rule 5."""
    components = _components(25, 25, 25, 25)  # sum = 100
    obj = Classification(
        task_type="BUILD",
        complexity_score=100,
        complexity_tier="EXTREME",
        complexity_components=components,
        flags=_flags(requires_human_gate=False),
        audit=_audit(
            extreme_forced=True,
            triggers={"requires_human_gate": ["EXTREME complexity (auto-forced)"]},
        ),
    )
    assert obj.flags.requires_human_gate is True


def test_extreme_tier_preserves_other_flags() -> None:
    components = _components(25, 25, 25, 25)
    obj = Classification(
        task_type="BUILD",
        complexity_score=100,
        complexity_tier="EXTREME",
        complexity_components=components,
        flags=_flags(needs_grounding=True, sensitive_data=True),
        audit=_audit(
            extreme_forced=True,
            triggers={
                "needs_grounding": ["explicit fact-check required"],
                "sensitive_data": ["redact_list match"],
                "requires_human_gate": ["EXTREME complexity (auto-forced)"],
            },
        ),
    )
    assert obj.flags.needs_grounding is True
    assert obj.flags.sensitive_data is True
    assert obj.flags.requires_human_gate is True


def test_non_extreme_tier_does_not_force_human_gate() -> None:
    obj = Classification(**_valid_kwargs(score=20, tier="LOW"))
    assert obj.flags.requires_human_gate is False


def test_task_type_enum_enforced() -> None:
    kwargs = _valid_kwargs()
    kwargs["task_type"] = "UNKNOWN"
    with pytest.raises(ValidationError):
        Classification(**kwargs)


def test_complexity_component_bounds() -> None:
    bad = _components(26, 0, 0, 0)
    with pytest.raises(ValidationError):
        ComplexityComponents(**bad)
    bad = _components(-1, 0, 0, 0)
    with pytest.raises(ValidationError):
        ComplexityComponents(**bad)


# --------------------------------------------------------------------------- #
# Audit fields (bible 08 §7.1, §10.10)                                        #
# --------------------------------------------------------------------------- #


def test_candidate_score_bounds() -> None:
    # Valid edges.
    CandidateScore(value="BUILD", confidence=0.0)
    CandidateScore(value="BUILD", confidence=1.0)
    # Out of range.
    with pytest.raises(ValidationError):
        CandidateScore(value="BUILD", confidence=-0.01)
    with pytest.raises(ValidationError):
        CandidateScore(value="BUILD", confidence=1.01)


def test_candidate_score_value_enum_enforced() -> None:
    with pytest.raises(ValidationError):
        CandidateScore(value="UNKNOWN", confidence=0.5)


def test_audit_default_flag_triggers_empty() -> None:
    audit = ClassificationAudit(task_type_precedence_fired="BUILD")
    assert audit.flag_triggers.needs_grounding == []
    assert audit.flag_triggers.sensitive_data == []
    assert audit.flag_triggers.destructive_potential == []
    assert audit.flag_triggers.requires_human_gate == []


def test_audit_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ClassificationAudit(
            task_type_precedence_fired="BUILD",
            unknown="x",
        )


def test_flag_triggers_extra_field_rejected() -> None:
    with pytest.raises(ValidationError):
        FlagTriggers(unknown_flag=["x"])


def test_audit_task_type_precedence_enum_enforced() -> None:
    with pytest.raises(ValidationError):
        ClassificationAudit(task_type_precedence_fired="UNKNOWN")


@pytest.mark.parametrize(
    "flag_name",
    [
        "needs_grounding",
        "sensitive_data",
        "destructive_potential",
        "requires_human_gate",
    ],
)
def test_true_flag_requires_non_empty_trigger_list(flag_name: str) -> None:
    """Bible 08 §10.10: every True flag must have a non-empty trigger list."""
    # True flag with empty triggers → ValidationError.
    with pytest.raises(ValidationError, match=f"flags\\.{flag_name}"):
        Classification(**_valid_kwargs(flags=_flags(**{flag_name: True})))

    # True flag with non-empty triggers → OK.
    Classification(
        **_valid_kwargs(
            flags=_flags(**{flag_name: True}),
            audit=_audit(triggers={flag_name: ["some_trigger"]}),
        )
    )


def test_false_flag_with_triggers_is_allowed() -> None:
    """A False flag may still have triggers logged (e.g., a near-miss)."""
    obj = Classification(
        **_valid_kwargs(
            flags=_flags(),  # all False
            audit=_audit(
                triggers={"needs_grounding": ["near-miss: low confidence"]}
            ),
        )
    )
    assert obj.flags.needs_grounding is False
    assert obj.audit.flag_triggers.needs_grounding == [
        "near-miss: low confidence"
    ]


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_classification_field_set_matches_bible() -> None:
    """Bible 08 §7.1 declares the Classification artifact as a JSON object.
    The implementation's top-level field set must match the bible's keys.
    Extra fields on impl (none currently) would be allowed only if bible-
    authorized.
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")

    # Find the §7.1 JSON block.
    section_match = re.search(
        r"###\s*7\.1\s+The\s+`Classification`\s+artifact.*?```json\s*(\{.*?\})\s*```",
        bible_text,
        re.DOTALL,
    )
    assert section_match, "Could not locate §7.1 JSON block in bible 08"

    bible_json = json.loads(section_match.group(1))
    bible_fields = set(bible_json.keys())

    impl_fields = set(Classification.model_fields.keys())

    # All bible-listed fields must be present.
    missing = bible_fields - impl_fields
    assert not missing, (
        f"Classification missing bible-required fields: {sorted(missing)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )
    # Currently the only impl extras would be section-02-authorized, but
    # for Classification §7.1 spans the full canonical shape — assert exact
    # match.
    extras = impl_fields - bible_fields
    assert not extras, (
        f"Classification has extra fields not in bible §7.1: {sorted(extras)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )
