"""Closed enum of every actor authorized to act on CEE.

Authorized by System Design Bible section 02 (User Roles), specifically §4
(closed taxonomy across four categories: human, system, external, substrate).

Adding, removing, or renaming any value here requires a bible edit first; the
boot consistency check (bible §12) verifies this enum matches §4 exactly. The
test ``test_role_enum_field_set_matches_bible`` is the drift detector that
parses ``~/cee/bible/02_user_roles.md`` §4.1–§4.4 and fails closed if the
implementation diverges from the spec.

The enum inherits from ``(str, Enum)`` so members are JSON-serializable as
strings and compare equal to their string values
(``RoleEnum.OPERATOR == "OPERATOR"``). Values are SCREAMING_SNAKE_CASE — the
same form used by the bible and by every artifact's existing ``produced_by``
default in ``schemas/`` — so members round-trip through persisted artifacts
without case conversion.

Categorization lives alongside the enum so callers can ask permission
questions ("is this a human role?", "is this a substrate?") without
re-parsing the bible. The four ``frozenset`` constants are derived from §4
and tested for partition completeness.
"""

from __future__ import annotations

from enum import Enum


class RoleEnum(str, Enum):
    """Every actor that can act on CEE — human, system, external, or substrate.

    Per bible §5 Rule 1 (Closed role enum), this list is exhaustive: 21
    members partitioned across four categories per §4.1–§4.4. No actor exists
    in the system that is not one of these. New roles require a bible edit
    and a corresponding update to this enum.

    Members are grouped here in bible order (human → system → external →
    substrate) for readability. The category ``frozenset`` constants below
    are the authoritative grouping for permission checks.
    """

    # ----------------------------------------------------------------- #
    # §4.1 Human roles                                                  #
    # ----------------------------------------------------------------- #
    OPERATOR = "OPERATOR"
    AUDITOR = "AUDITOR"

    # ----------------------------------------------------------------- #
    # §4.2 System roles (CEE internal modules)                          #
    # ----------------------------------------------------------------- #
    INTERPRETER = "INTERPRETER"
    CLASSIFIER = "CLASSIFIER"
    AGENT_SELECTOR = "AGENT_SELECTOR"
    SKILL_ENGINE = "SKILL_ENGINE"
    STRATEGY_BUILDER = "STRATEGY_BUILDER"
    PROMPT_BUILDER = "PROMPT_BUILDER"
    SAFETY_GATE = "SAFETY_GATE"
    PERSISTENCE_WRITER = "PERSISTENCE_WRITER"
    BIBLE_LOADER = "BIBLE_LOADER"
    BOOT_SEQUENCER = "BOOT_SEQUENCER"
    OBSIDIAN_WRITER = "OBSIDIAN_WRITER"
    NOTION_WRITER = "NOTION_WRITER"
    PIPELINE_DRIVER = "PIPELINE_DRIVER"

    # ----------------------------------------------------------------- #
    # §4.3 External roles (services CEE communicates with)              #
    # ----------------------------------------------------------------- #
    EXECUTOR = "EXECUTOR"
    NOTION_API = "NOTION_API"
    FILESYSTEM_OS = "FILESYSTEM_OS"

    # ----------------------------------------------------------------- #
    # §4.4 Substrate roles (persistence layers)                         #
    # ----------------------------------------------------------------- #
    FILESYSTEM_CANON = "FILESYSTEM_CANON"
    OBSIDIAN_VAULT = "OBSIDIAN_VAULT"
    NOTION_BIBLE = "NOTION_BIBLE"


HUMAN_ROLES: frozenset[RoleEnum] = frozenset(
    {RoleEnum.OPERATOR, RoleEnum.AUDITOR}
)

SYSTEM_ROLES: frozenset[RoleEnum] = frozenset(
    {
        RoleEnum.INTERPRETER,
        RoleEnum.CLASSIFIER,
        RoleEnum.AGENT_SELECTOR,
        RoleEnum.SKILL_ENGINE,
        RoleEnum.STRATEGY_BUILDER,
        RoleEnum.PROMPT_BUILDER,
        RoleEnum.SAFETY_GATE,
        RoleEnum.PERSISTENCE_WRITER,
        RoleEnum.BIBLE_LOADER,
        RoleEnum.BOOT_SEQUENCER,
        RoleEnum.OBSIDIAN_WRITER,
        RoleEnum.NOTION_WRITER,
        RoleEnum.PIPELINE_DRIVER,
    }
)

EXTERNAL_ROLES: frozenset[RoleEnum] = frozenset(
    {RoleEnum.EXECUTOR, RoleEnum.NOTION_API, RoleEnum.FILESYSTEM_OS}
)

SUBSTRATE_ROLES: frozenset[RoleEnum] = frozenset(
    {RoleEnum.FILESYSTEM_CANON, RoleEnum.OBSIDIAN_VAULT, RoleEnum.NOTION_BIBLE}
)


__all__ = [
    "RoleEnum",
    "HUMAN_ROLES",
    "SYSTEM_ROLES",
    "EXTERNAL_ROLES",
    "SUBSTRATE_ROLES",
]
