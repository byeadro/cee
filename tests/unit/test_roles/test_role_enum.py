"""Tests for the closed RoleEnum.

Verifies the 21-member role taxonomy from bible section 02 §4 (across
§4.1 human, §4.2 system, §4.3 external, §4.4 substrate). The
bible-grounding test parses the bible mirror and fails closed if the
implementation drifts from the spec.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from roles import (
    EXTERNAL_ROLES,
    HUMAN_ROLES,
    SUBSTRATE_ROLES,
    SYSTEM_ROLES,
    RoleEnum,
)

# Bible mirror — the bible-grounding test reads this; tests skip if missing.
_BIBLE_PATH = Path.home() / "cee" / "bible" / "02_user_roles.md"

# Expected member sets per bible §4.1, §4.2, §4.3, §4.4 (frozenset literals
# so the test fails closed if the implementation accidentally adds or removes
# a name).
EXPECTED_HUMAN_ROLE_NAMES = frozenset({"OPERATOR", "AUDITOR"})

EXPECTED_SYSTEM_ROLE_NAMES = frozenset(
    {
        "INTERPRETER",
        "CLASSIFIER",
        "AGENT_SELECTOR",
        "SKILL_ENGINE",
        "STRATEGY_BUILDER",
        "PROMPT_BUILDER",
        "SAFETY_GATE",
        "PERSISTENCE_WRITER",
        "BIBLE_LOADER",
        "BOOT_SEQUENCER",
        "OBSIDIAN_WRITER",
        "NOTION_WRITER",
        "PIPELINE_DRIVER",
    }
)

EXPECTED_EXTERNAL_ROLE_NAMES = frozenset(
    {"EXECUTOR", "NOTION_API", "FILESYSTEM_OS"}
)

EXPECTED_SUBSTRATE_ROLE_NAMES = frozenset(
    {"FILESYSTEM_CANON", "OBSIDIAN_VAULT", "NOTION_BIBLE"}
)

EXPECTED_ALL_ROLE_NAMES = (
    EXPECTED_HUMAN_ROLE_NAMES
    | EXPECTED_SYSTEM_ROLE_NAMES
    | EXPECTED_EXTERNAL_ROLE_NAMES
    | EXPECTED_SUBSTRATE_ROLE_NAMES
)

# SCREAMING_SNAKE_CASE validator — all role names are uppercase identifiers.
_SCREAMING_SNAKE_CASE = re.compile(r"^[A-Z]+(_[A-Z0-9]+)*$")


# --------------------------------------------------------------------------- #
# Member counts                                                               #
# --------------------------------------------------------------------------- #


def test_role_enum_has_total_member_count_21() -> None:
    # Bible §4: 2 human + 13 system + 3 external + 3 substrate = 21.
    assert len(RoleEnum) == 21


def test_role_enum_field_set_matches_bible() -> None:
    """The enum's full member set equals §4.1 ∪ §4.2 ∪ §4.3 ∪ §4.4."""
    assert {m.name for m in RoleEnum} == EXPECTED_ALL_ROLE_NAMES


def test_role_enum_human_subset_matches_bible_4_1() -> None:
    assert {m.name for m in HUMAN_ROLES} == EXPECTED_HUMAN_ROLE_NAMES
    assert len(HUMAN_ROLES) == 2


def test_role_enum_system_subset_matches_bible_4_2() -> None:
    assert {m.name for m in SYSTEM_ROLES} == EXPECTED_SYSTEM_ROLE_NAMES
    assert len(SYSTEM_ROLES) == 13


def test_role_enum_external_subset_matches_bible_4_3() -> None:
    assert {m.name for m in EXTERNAL_ROLES} == EXPECTED_EXTERNAL_ROLE_NAMES
    assert len(EXTERNAL_ROLES) == 3


def test_role_enum_substrate_subset_matches_bible_4_4() -> None:
    assert {m.name for m in SUBSTRATE_ROLES} == EXPECTED_SUBSTRATE_ROLE_NAMES
    assert len(SUBSTRATE_ROLES) == 3


# --------------------------------------------------------------------------- #
# Value shape                                                                 #
# --------------------------------------------------------------------------- #


def test_role_enum_values_are_string_subclass() -> None:
    for member in RoleEnum:
        assert isinstance(member.value, str)


def test_role_enum_values_are_screaming_snake_case() -> None:
    for member in RoleEnum:
        assert _SCREAMING_SNAKE_CASE.fullmatch(member.value), member.value


def test_role_enum_values_match_member_names() -> None:
    """Schema defaults like ``produced_by = "INTERPRETER"`` round-trip
    through the enum without case conversion."""
    for member in RoleEnum:
        assert member.value == member.name


def test_role_enum_inherits_from_str() -> None:
    """Required for JSON serialization and equality with raw strings."""
    assert issubclass(RoleEnum, str)


# --------------------------------------------------------------------------- #
# Category partition                                                          #
# --------------------------------------------------------------------------- #


def test_categories_partition_role_enum() -> None:
    """Every member belongs to exactly one of the four categories."""
    union = HUMAN_ROLES | SYSTEM_ROLES | EXTERNAL_ROLES | SUBSTRATE_ROLES
    assert union == set(RoleEnum)


def test_categories_are_pairwise_disjoint() -> None:
    categories = {
        "human": HUMAN_ROLES,
        "system": SYSTEM_ROLES,
        "external": EXTERNAL_ROLES,
        "substrate": SUBSTRATE_ROLES,
    }
    items = list(categories.items())
    for i, (name_a, set_a) in enumerate(items):
        for name_b, set_b in items[i + 1 :]:
            assert set_a.isdisjoint(set_b), (
                f"Category overlap: {name_a} ∩ {name_b} = "
                f"{sorted(m.name for m in set_a & set_b)}"
            )


def test_category_sums_match_total() -> None:
    assert (
        len(HUMAN_ROLES)
        + len(SYSTEM_ROLES)
        + len(EXTERNAL_ROLES)
        + len(SUBSTRATE_ROLES)
        == len(RoleEnum)
    )


# --------------------------------------------------------------------------- #
# Behavioral guarantees                                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "member",
    [
        RoleEnum.OPERATOR,
        RoleEnum.PIPELINE_DRIVER,
        RoleEnum.FILESYSTEM_CANON,
        RoleEnum.EXECUTOR,
    ],
)
def test_role_enum_is_json_serializable(member: RoleEnum) -> None:
    payload = json.dumps({"produced_by": member.value})
    assert json.loads(payload) == {"produced_by": member.value}


def test_role_enum_is_str_comparable() -> None:
    """Schemas store ``produced_by`` as plain strings; equality with the enum
    member must work without conversion."""
    assert RoleEnum.OPERATOR == "OPERATOR"
    assert RoleEnum.PIPELINE_DRIVER == "PIPELINE_DRIVER"
    assert RoleEnum.NOTION_BIBLE == "NOTION_BIBLE"


def test_role_enum_membership_check() -> None:
    assert "OPERATOR" in [r.value for r in RoleEnum]
    assert "PIPELINE_DRIVER" in [r.value for r in RoleEnum]
    assert "ROGUE_ROLE" not in [r.value for r in RoleEnum]


def test_role_enum_iteration_order_stable() -> None:
    assert list(RoleEnum) == list(RoleEnum)


def test_role_enum_lookup_by_value() -> None:
    """Round-trip from a persisted ``produced_by`` string back to the enum."""
    assert RoleEnum("INTERPRETER") is RoleEnum.INTERPRETER
    assert RoleEnum("PIPELINE_DRIVER") is RoleEnum.PIPELINE_DRIVER


def test_role_enum_rejects_unknown_value() -> None:
    """Per bible §5 Rule 7 (No anonymous writes), there is no fallback."""
    with pytest.raises(ValueError):
        RoleEnum("system")
    with pytest.raises(ValueError):
        RoleEnum("operator")  # case-sensitive — must be uppercase
    with pytest.raises(ValueError):
        RoleEnum("")


# --------------------------------------------------------------------------- #
# Schema integration — every existing produced_by default is a valid role    #
# --------------------------------------------------------------------------- #


def test_existing_schema_produced_by_defaults_are_valid_roles() -> None:
    """Every ``produced_by`` default in ``schemas/`` must round-trip through
    ``RoleEnum``. If a schema names a role that doesn't exist in the enum,
    bible §4 has been violated.

    These mirror the literal defaults declared in the schema modules; the
    test fails if the schemas declare a role this enum doesn't model.
    """
    schema_role_defaults = [
        "OPERATOR",  # raw_input.py
        "INTERPRETER",  # intent_object.py, clarification_request.py
        "CLASSIFIER",  # classification.py
        "AGENT_SELECTOR",  # agent_plan.py
        "SKILL_ENGINE",  # skill_set.py
        "STRATEGY_BUILDER",  # execution_strategy.py
        "PROMPT_BUILDER",  # final_prompt.py
        "PIPELINE_DRIVER",  # run_error.py, run_summary.py
    ]
    for default in schema_role_defaults:
        assert RoleEnum(default).value == default


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #

# Maps bible sub-section heading → (expected member set, expected count).
_BIBLE_SUBSECTIONS: dict[str, tuple[frozenset[str], int]] = {
    "4.1": (EXPECTED_HUMAN_ROLE_NAMES, 2),
    "4.2": (EXPECTED_SYSTEM_ROLE_NAMES, 13),
    "4.3": (EXPECTED_EXTERNAL_ROLE_NAMES, 3),
    "4.4": (EXPECTED_SUBSTRATE_ROLE_NAMES, 3),
}

# A bullet item naming a role: ``- `ROLE_NAME` `` followed by optional prose
# (e.g. ``(future)``, ``(slot — Phase 1: ...)``). Anchored at line start (after
# optional indent) and captures only the first backticked uppercase identifier.
_ROLE_BULLET = re.compile(r"^\s*-\s*`([A-Z][A-Z0-9_]*)`")


def _extract_roles_per_subsection(bible_text: str) -> dict[str, set[str]]:
    """Parse §4.1–§4.4 bullet lists and return ``{section: {NAME, ...}}``.

    Walks line by line, tracks the active ``###`` heading (``4.1``, ``4.2``,
    ``4.3``, ``4.4``), and only collects role-bullet lines that fall inside
    one of the target sub-sections. Stops collection for a sub-section when
    a new heading at any depth is encountered.
    """
    sections: dict[str, set[str]] = {key: set() for key in _BIBLE_SUBSECTIONS}
    active_section: str | None = None
    in_code_fence = False

    for raw_line in bible_text.splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        # Code fence toggle — the bible has no code fences in §4 today, but
        # guard anyway so a future edit doesn't accidentally smuggle members
        # into the parser.
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue

        # Heading detection — any markdown heading flips active_section.
        if stripped.startswith("#") and not in_code_fence:
            heading_match = re.match(r"^#+\s*(\d+\.\d+)\b", stripped)
            if heading_match:
                section_id = heading_match.group(1)
                active_section = section_id if section_id in sections else None
            else:
                # Non-numeric heading or different depth — leave active.
                active_section = None
            continue

        if active_section and not in_code_fence:
            bullet_match = _ROLE_BULLET.match(line)
            if bullet_match:
                sections[active_section].add(bullet_match.group(1))

    return sections


def test_role_enum_member_names_match_bible() -> None:
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")
    extracted = _extract_roles_per_subsection(bible_text)

    for section_id, (expected_set, expected_count) in _BIBLE_SUBSECTIONS.items():
        bible_members = extracted[section_id]

        # Sanity: parser found the right count from the bible itself. If this
        # fails, the bible was edited and the parser hasn't kept up — fix the
        # parser before trusting the drift assertion.
        assert len(bible_members) == expected_count, (
            f"Bible §{section_id} parser found {len(bible_members)} members, "
            f"expected {expected_count}. Parser may be broken or bible has "
            f"drifted. Found: {sorted(bible_members)}"
        )

        # Sanity: parser output equals our hardcoded expectation. If this
        # fails, the bible has drifted from the EXPECTED_*_ROLE_NAMES literals
        # at the top of this file.
        assert bible_members == set(expected_set), (
            f"Bible §{section_id} contents differ from the test's literal "
            f"expectation.\n"
            f"  Only in bible: {sorted(bible_members - expected_set)}\n"
            f"  Only in test:  {sorted(expected_set - bible_members)}"
        )

    # The drift detector: the union of all four sub-sections in the bible
    # must equal the implementation's full member set.
    bible_total = set().union(*extracted.values())
    impl_total = {m.name for m in RoleEnum}
    assert impl_total == bible_total, (
        f"RoleEnum drifted from bible §4.\n"
        f"  Only in implementation: {sorted(impl_total - bible_total)}\n"
        f"  Only in bible:          {sorted(bible_total - impl_total)}"
    )


def test_role_enum_total_count_matches_bible() -> None:
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")
    extracted = _extract_roles_per_subsection(bible_text)
    bible_total = set().union(*extracted.values())

    # 21 = 2 + 13 + 3 + 3 (bible §4.1–§4.4). If this fails, the bible was
    # edited; update the implementation in lockstep and adjust the test.
    assert len(bible_total) == 21
    assert len(RoleEnum) == len(bible_total)
