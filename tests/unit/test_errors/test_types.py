"""Tests for the closed error-state enums.

Verifies HaltType (19), RunErrorType (7), and WarningType (15) from bible
section 19 §5.1–§5.3. The bible-grounding test parses the bible mirror and
fails if the implementation drifts from the spec.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path

import pytest

from errors import HaltType, RunErrorType, WarningType

# Snake-case validator from the bible's value convention.
_SNAKE_CASE = re.compile(r"^[a-z]+(_[a-z0-9]+)*$")

# Bible mirror — the bible-grounding test reads this; tests skip if missing.
_BIBLE_PATH = Path.home() / "cee" / "bible" / "19_error_handling_failure_states.md"

# Expected member sets per bible §5.1, §5.2, §5.3 (frozenset literal so the
# test fails closed if the implementation accidentally adds or removes a name).
EXPECTED_HALT_TYPE_NAMES = frozenset(
    {
        "INPUT_VALIDATION_ERROR",
        "INPUT_EMPTY_ERROR",
        "PAUSED_FOR_CLARIFICATION",
        "NO_EXECUTABLE_INTENT",
        "INJECTION_DETECTED",
        "AMBIGUOUS_CLASSIFICATION",
        "AGENT_CONFLICT",
        "NO_PRIMARY_AGENT",
        "AGENT_GENERATION_FAILED",
        "SKILL_RESOLUTION_CHOICE",
        "SKILL_CONFLICT",
        "SKILL_GENERATION_FAILED",
        "SKILL_DUPLICATE",
        "PROMPT_SCHEMA_VIOLATION",
        "PROMPT_TOO_LARGE",
        "AWAITING_DESTRUCTIVE_CONFIRMATION",
        "REDACTION_FAILED",
        "GROUNDING_UNSOURCEABLE",
        "PERSISTENCE_FAILURE",
    }
)

EXPECTED_RUN_ERROR_TYPE_NAMES = frozenset(
    {
        "SCHEMA_VIOLATION",
        "DRIVER_BUG",
        "CONFIRMATION_TIMEOUT",
        "REPLAY_DRIFT",
        "UNRECOVERABLE_PERSISTENCE",
        "API_FAILED",
        "API_RATE_LIMITED_TERMINAL",
    }
)

EXPECTED_WARNING_TYPE_NAMES = frozenset(
    {
        "OBSIDIAN_WRITE_FAILED",
        "NOTION_WRITE_FAILED",
        "SKILL_REGISTRY_INVALID_ENTRY",
        "AGENT_REGISTRY_INVALID_ENTRY",
        "LLM_CALL_FALLBACK",
        "HOOK_FAILED",
        "SKILL_NEEDS_REVIEW_AGED",
        "AGENT_NEEDS_REVIEW_AGED",
        "BIBLE_DRIFT_DETECTED",
        "UNKNOWN_TOOL_IN_AGENT",
        "OVER_REDACTION",
        "SECURITY_OVERRIDE",
        "INJECTION_FLAG_ACKNOWLEDGED",
        "DETERMINISM_DRIFT",
        "PROMOTION_QUEUE_LARGE",
    }
)


# --------------------------------------------------------------------------- #
# HaltType                                                                    #
# --------------------------------------------------------------------------- #


def test_halt_type_has_expected_member_count() -> None:
    assert len(HaltType) == 19


def test_halt_type_has_expected_members() -> None:
    assert {m.name for m in HaltType} == EXPECTED_HALT_TYPE_NAMES


def test_halt_type_values_are_string_subclass() -> None:
    for member in HaltType:
        assert isinstance(member.value, str)


def test_halt_type_values_are_lowercase_snake_case() -> None:
    for member in HaltType:
        assert _SNAKE_CASE.fullmatch(member.value), member.value


def test_halt_type_values_match_member_names() -> None:
    for member in HaltType:
        assert member.value == member.name.lower()


# --------------------------------------------------------------------------- #
# RunErrorType                                                                #
# --------------------------------------------------------------------------- #


def test_run_error_type_has_expected_member_count() -> None:
    assert len(RunErrorType) == 7


def test_run_error_type_has_expected_members() -> None:
    assert {m.name for m in RunErrorType} == EXPECTED_RUN_ERROR_TYPE_NAMES


def test_run_error_type_values_are_string_subclass() -> None:
    for member in RunErrorType:
        assert isinstance(member.value, str)


def test_run_error_type_values_are_lowercase_snake_case() -> None:
    for member in RunErrorType:
        assert _SNAKE_CASE.fullmatch(member.value), member.value


def test_run_error_type_values_match_member_names() -> None:
    for member in RunErrorType:
        assert member.value == member.name.lower()


# --------------------------------------------------------------------------- #
# WarningType                                                                 #
# --------------------------------------------------------------------------- #


def test_warning_type_has_expected_member_count() -> None:
    assert len(WarningType) == 15


def test_warning_type_has_expected_members() -> None:
    assert {m.name for m in WarningType} == EXPECTED_WARNING_TYPE_NAMES


def test_warning_type_values_are_string_subclass() -> None:
    for member in WarningType:
        assert isinstance(member.value, str)


def test_warning_type_values_are_lowercase_snake_case() -> None:
    for member in WarningType:
        assert _SNAKE_CASE.fullmatch(member.value), member.value


def test_warning_type_values_match_member_names() -> None:
    for member in WarningType:
        assert member.value == member.name.lower()


# --------------------------------------------------------------------------- #
# Cross-cutting                                                               #
# --------------------------------------------------------------------------- #


def test_no_overlap_between_enums() -> None:
    halt_values = {m.value for m in HaltType}
    run_error_values = {m.value for m in RunErrorType}
    warning_values = {m.value for m in WarningType}

    assert halt_values.isdisjoint(run_error_values)
    assert halt_values.isdisjoint(warning_values)
    assert run_error_values.isdisjoint(warning_values)


@pytest.mark.parametrize(
    "enum_cls,sample",
    [
        (HaltType, HaltType.INPUT_VALIDATION_ERROR),
        (RunErrorType, RunErrorType.SCHEMA_VIOLATION),
        (WarningType, WarningType.OBSIDIAN_WRITE_FAILED),
    ],
)
def test_enums_are_json_serializable(
    enum_cls: type[Enum], sample: Enum
) -> None:
    payload = json.dumps({"x": sample.value})
    assert json.loads(payload) == {"x": sample.value}
    assert isinstance(sample.value, str)


def test_enums_are_str_comparable() -> None:
    assert HaltType.INPUT_VALIDATION_ERROR == "input_validation_error"
    assert RunErrorType.SCHEMA_VIOLATION == "schema_violation"
    assert WarningType.OBSIDIAN_WRITE_FAILED == "obsidian_write_failed"


def test_enum_membership_check() -> None:
    assert "input_validation_error" in [e.value for e in HaltType]
    assert "schema_violation" in [e.value for e in RunErrorType]
    assert "obsidian_write_failed" in [e.value for e in WarningType]


def test_enum_iteration_order_stable() -> None:
    assert list(HaltType) == list(HaltType)
    assert list(RunErrorType) == list(RunErrorType)
    assert list(WarningType) == list(WarningType)


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #

# Maps bible section heading → (enum class, expected count).
_BIBLE_SECTIONS = {
    "5.1": (HaltType, 19),
    "5.2": (RunErrorType, 7),
    "5.3": (WarningType, 15),
}

# Inside a code fence, an enum member appears as: NAME = "value"
# Anchored at line start (after optional indent) to avoid prose mentions.
_MEMBER_LINE = re.compile(
    r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*\"([a-z][a-z0-9_]*)\"\s*$"
)


def _extract_members_per_section(bible_text: str) -> dict[str, set[str]]:
    """Parse §5.1, §5.2, §5.3 enum bodies and return {section: {NAME, ...}}.

    Walks line by line, tracks the active section heading (e.g. "### 5.1 ..."),
    and only collects ``NAME = "value"`` lines that fall inside fenced code
    blocks beneath one of the target sections. Stops collection for a section
    when a new section heading or a non-target heading is encountered.
    """
    sections: dict[str, set[str]] = {key: set() for key in _BIBLE_SECTIONS}
    active_section: str | None = None
    in_code_fence = False

    for raw_line in bible_text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        # Heading detection — any markdown heading flips active_section.
        if stripped.startswith("#") and not in_code_fence:
            heading_match = re.match(r"^#+\s*(\d+\.\d+)\b", stripped)
            if heading_match:
                section_id = heading_match.group(1)
                active_section = section_id if section_id in sections else None
            else:
                # Non-numeric heading — leave any active section.
                active_section = None
            continue

        # Code fence toggle.
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue

        if active_section and in_code_fence:
            member_match = _MEMBER_LINE.match(line)
            if member_match:
                name, value = member_match.group(1), member_match.group(2)
                # Sanity: value must equal name.lower() per bible convention.
                if value == name.lower():
                    sections[active_section].add(name)

    return sections


def test_enum_member_names_match_bible() -> None:
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")
    extracted = _extract_members_per_section(bible_text)

    for section_id, (enum_cls, expected_count) in _BIBLE_SECTIONS.items():
        bible_members = extracted[section_id]
        impl_members = {m.name for m in enum_cls}

        # Sanity check: parser found the right count from the bible itself.
        assert len(bible_members) == expected_count, (
            f"Bible §{section_id} parser found {len(bible_members)} members, "
            f"expected {expected_count}. Parser may be broken or bible "
            f"has drifted. Found: {sorted(bible_members)}"
        )

        # The drift detector: implementation must equal bible exactly.
        assert impl_members == bible_members, (
            f"{enum_cls.__name__} drifted from bible §{section_id}.\n"
            f"  Only in implementation: {sorted(impl_members - bible_members)}\n"
            f"  Only in bible:          {sorted(bible_members - impl_members)}"
        )
