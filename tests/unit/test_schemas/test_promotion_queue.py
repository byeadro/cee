"""Tests for the PromotionQueue + PromotionQueueEntry schemas."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from roles import RoleEnum
from schemas import PromotionQueue, PromotionQueueEntry


_BIBLE_04_PATH = Path.home() / "cee" / "bible" / "04_database_file_structure.md"
_BIBLE_00_PATH = Path.home() / "cee" / "bible" / "00_project_vision.md"
_BIBLE_07_PATH = Path.home() / "cee" / "bible" / "07_skill_system_design.md"


def _valid_entry_kwargs() -> dict:
    return {
        "slug": "read-codebase",
        "kind": "skill",
        "enqueued_at": "2026-05-02T10:15:00Z",
        "payload_path": "~/cee/skills/read-codebase/SKILL.md",
    }


def _valid_queue_kwargs() -> dict:
    return {
        "last_updated": "2026-05-02T10:15:00Z",
    }


# --------------------------------------------------------------------------- #
# Entry — standard schema tests                                               #
# --------------------------------------------------------------------------- #


def test_entry_minimal_valid() -> None:
    obj = PromotionQueueEntry(**_valid_entry_kwargs())
    assert obj.slug == "read-codebase"
    assert obj.kind == "skill"
    assert obj.status == "queued"
    assert obj.enqueued_at == "2026-05-02T10:15:00Z"
    assert obj.enqueued_by_run is None
    assert obj.target_notion_page_id is None
    assert obj.payload_path == "~/cee/skills/read-codebase/SKILL.md"
    assert obj.attempts == 0
    assert obj.last_error is None


def test_entry_full_valid() -> None:
    obj = PromotionQueueEntry(
        slug="custom-agent",
        kind="agent",
        status="pending_review",
        enqueued_at="2026-05-02T10:15:00Z",
        enqueued_by_run="run-2026-05-02-001",
        target_notion_page_id="abc123",
        payload_path="~/cee/.claude/agents/custom-agent.md",
        attempts=2,
        last_error="notion mcp timeout",
    )
    assert obj.kind == "agent"
    assert obj.status == "pending_review"
    assert obj.attempts == 2
    assert obj.last_error == "notion mcp timeout"


@pytest.mark.parametrize(
    "missing_field",
    ["slug", "kind", "enqueued_at", "payload_path"],
)
def test_entry_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_entry_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        PromotionQueueEntry(**kwargs)


def test_entry_extra_field_rejected() -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        PromotionQueueEntry(**kwargs)


def test_entry_string_whitespace_stripped() -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["slug"] = "  read-codebase  "
    kwargs["payload_path"] = "  ~/cee/skills/read-codebase/SKILL.md  "
    obj = PromotionQueueEntry(**kwargs)
    assert obj.slug == "read-codebase"
    assert obj.payload_path == "~/cee/skills/read-codebase/SKILL.md"


def test_entry_schema_version_present() -> None:
    assert PromotionQueueEntry.SCHEMA_VERSION == "1.0.0"


def test_entry_json_round_trip() -> None:
    original = PromotionQueueEntry(
        slug="custom-agent",
        kind="agent",
        status="approved",
        enqueued_at="2026-05-02T10:15:00Z",
        enqueued_by_run="run-2026-05-02-001",
        target_notion_page_id="abc123",
        payload_path="~/cee/.claude/agents/custom-agent.md",
        attempts=1,
        last_error=None,
    )
    payload = original.model_dump_json()
    restored = PromotionQueueEntry.model_validate_json(payload)
    assert restored == original


def test_entry_dict_round_trip() -> None:
    original = PromotionQueueEntry(**_valid_entry_kwargs())
    payload = original.model_dump()
    restored = PromotionQueueEntry.model_validate(payload)
    assert restored == original


def test_entry_field_order_stable() -> None:
    """Field order is stable across dumps so on-disk JSON is diffable."""
    obj = PromotionQueueEntry(**_valid_entry_kwargs())
    expected_order = [
        "slug",
        "kind",
        "status",
        "enqueued_at",
        "enqueued_by_run",
        "target_notion_page_id",
        "payload_path",
        "attempts",
        "last_error",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Entry — closed enums + value invariants                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", ["skill", "agent"])
def test_entry_kind_accepts_canonical_values(kind: str) -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["kind"] = kind
    obj = PromotionQueueEntry(**kwargs)
    assert obj.kind == kind


@pytest.mark.parametrize("kind", ["bible_section", "run", "agent_plan", "", "Skill"])
def test_entry_kind_rejects_unknown_values(kind: str) -> None:
    """``kind`` is a closed Literal — bible 04 §7.2 mentions only
    Skills and agents as promotable artifacts.
    """
    kwargs = _valid_entry_kwargs()
    kwargs["kind"] = kind
    with pytest.raises(ValidationError):
        PromotionQueueEntry(**kwargs)


@pytest.mark.parametrize(
    "status", ["queued", "pending_review", "approved", "rejected"]
)
def test_entry_status_accepts_canonical_lifecycle_values(status: str) -> None:
    """The four lifecycle values come from bible 07 §5.5 + bible 03 §5.5."""
    kwargs = _valid_entry_kwargs()
    kwargs["status"] = status
    obj = PromotionQueueEntry(**kwargs)
    assert obj.status == status


@pytest.mark.parametrize("status", ["draining", "in_review", "PENDING_REVIEW", ""])
def test_entry_status_rejects_unknown_values(status: str) -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["status"] = status
    with pytest.raises(ValidationError):
        PromotionQueueEntry(**kwargs)


def test_entry_status_defaults_to_queued() -> None:
    """A newly-enqueued entry hasn't reached Notion yet — it's `queued`,
    not `pending_review`. Per bible 07 §5.5 step 1 vs step 3.
    """
    obj = PromotionQueueEntry(**_valid_entry_kwargs())
    assert obj.status == "queued"


def test_entry_attempts_defaults_to_zero() -> None:
    obj = PromotionQueueEntry(**_valid_entry_kwargs())
    assert obj.attempts == 0


def test_entry_attempts_must_be_non_negative() -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["attempts"] = -1
    with pytest.raises(ValidationError):
        PromotionQueueEntry(**kwargs)


def test_entry_last_error_defaults_to_none() -> None:
    obj = PromotionQueueEntry(**_valid_entry_kwargs())
    assert obj.last_error is None


def test_entry_required_fields_must_be_non_empty() -> None:
    """slug, enqueued_at, and payload_path use min_length=1."""
    for field in ["slug", "enqueued_at", "payload_path"]:
        bad = _valid_entry_kwargs()
        bad[field] = ""
        with pytest.raises(ValidationError):
            PromotionQueueEntry(**bad)


def test_entry_optional_fields_accept_none_explicitly() -> None:
    """enqueued_by_run, target_notion_page_id, and last_error are
    explicitly nullable."""
    kwargs = _valid_entry_kwargs()
    kwargs["enqueued_by_run"] = None
    kwargs["target_notion_page_id"] = None
    kwargs["last_error"] = None
    obj = PromotionQueueEntry(**kwargs)
    assert obj.enqueued_by_run is None
    assert obj.target_notion_page_id is None
    assert obj.last_error is None


# --------------------------------------------------------------------------- #
# Wrapper — PromotionQueue                                                    #
# --------------------------------------------------------------------------- #


def test_queue_minimal_valid() -> None:
    obj = PromotionQueue(**_valid_queue_kwargs())
    assert obj.last_updated == "2026-05-02T10:15:00Z"
    assert obj.schema_version == "1.0.0"
    assert obj.produced_by == RoleEnum.NOTION_WRITER
    assert obj.entries == []


def test_queue_with_entries() -> None:
    e1 = PromotionQueueEntry(**_valid_entry_kwargs())
    e2 = PromotionQueueEntry(
        slug="custom-agent",
        kind="agent",
        enqueued_at="2026-05-02T11:00:00Z",
        payload_path="~/cee/.claude/agents/custom-agent.md",
    )
    obj = PromotionQueue(
        last_updated="2026-05-02T11:00:00Z",
        entries=[e1, e2],
    )
    assert len(obj.entries) == 2
    assert obj.entries[0].slug == "read-codebase"
    assert obj.entries[1].kind == "agent"


def test_queue_missing_required_field_raises() -> None:
    with pytest.raises(ValidationError):
        PromotionQueue()


def test_queue_extra_field_rejected() -> None:
    kwargs = _valid_queue_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        PromotionQueue(**kwargs)


def test_queue_string_whitespace_stripped() -> None:
    obj = PromotionQueue(last_updated="  2026-05-02T10:15:00Z  ")
    assert obj.last_updated == "2026-05-02T10:15:00Z"


def test_queue_schema_version_defaults_to_one_zero_zero() -> None:
    obj = PromotionQueue(**_valid_queue_kwargs())
    assert obj.schema_version == "1.0.0"
    assert obj.schema_version == PromotionQueue.SCHEMA_VERSION


def test_queue_schema_version_appears_in_json_dump() -> None:
    """Mirrors SyncMeta convention: durable cross-Run state carries
    the schema version on disk.
    """
    obj = PromotionQueue(**_valid_queue_kwargs())
    payload = obj.model_dump()
    assert "schema_version" in payload
    assert payload["schema_version"] == "1.0.0"


def test_queue_produced_by_defaults_to_notion_writer() -> None:
    """Bible 02 §7.11 names NOTION_WRITER as the read+update authority
    on the queue.
    """
    obj = PromotionQueue(**_valid_queue_kwargs())
    assert obj.produced_by == RoleEnum.NOTION_WRITER
    assert obj.produced_by == "NOTION_WRITER"


def test_queue_produced_by_can_be_overridden() -> None:
    """In production PERSISTENCE_WRITER also writes the queue at Run
    finalize time per bible 04 §7.2; the schema permits that."""
    obj = PromotionQueue(
        last_updated="2026-05-02T10:15:00Z",
        produced_by=RoleEnum.PERSISTENCE_WRITER,
    )
    assert obj.produced_by == RoleEnum.PERSISTENCE_WRITER


def test_queue_entries_defaults_to_empty_list() -> None:
    a = PromotionQueue(**_valid_queue_kwargs())
    b = PromotionQueue(**_valid_queue_kwargs())
    a.entries.append(PromotionQueueEntry(**_valid_entry_kwargs()))
    # default_factory must produce independent lists
    assert b.entries == []


def test_queue_last_updated_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        PromotionQueue(last_updated="")
    with pytest.raises(ValidationError):
        PromotionQueue(last_updated="   ")


def test_queue_field_order_stable() -> None:
    obj = PromotionQueue(**_valid_queue_kwargs())
    expected_order = [
        "schema_version",
        "produced_by",
        "last_updated",
        "entries",
    ]
    assert list(obj.model_dump().keys()) == expected_order


def test_queue_json_round_trip_with_entries() -> None:
    e1 = PromotionQueueEntry(**_valid_entry_kwargs())
    e2 = PromotionQueueEntry(
        slug="custom-agent",
        kind="agent",
        status="approved",
        enqueued_at="2026-05-02T11:00:00Z",
        payload_path="~/cee/.claude/agents/custom-agent.md",
        attempts=1,
    )
    original = PromotionQueue(
        last_updated="2026-05-02T11:00:00Z",
        entries=[e1, e2],
    )
    payload = original.model_dump_json()
    restored = PromotionQueue.model_validate_json(payload)
    assert restored == original
    assert len(restored.entries) == 2


def test_queue_entries_value_must_be_promotion_queue_entry() -> None:
    """A dict missing required PromotionQueueEntry fields fails coercion."""
    with pytest.raises(ValidationError):
        PromotionQueue(
            last_updated="2026-05-02T10:15:00Z",
            entries=[{"slug": "x"}],
        )


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_kind_values_match_bible_promotable_artifact_taxonomy() -> None:
    """Bible 04 §7.2 names the promotable artifacts as Skills and agents:
    "promotion_queue.json — appended if new Skill/agent." If the bible
    later expands the set (e.g., to include bible_section), this test
    fails loudly so the schema enum is updated in lockstep.
    """
    if not _BIBLE_04_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_04_PATH}")

    bible_text = _BIBLE_04_PATH.read_text(encoding="utf-8")
    line_458 = "promotion_queue.json` — appended if new Skill/agent"
    assert line_458 in bible_text, (
        "bible 04 §7.2 promotable-artifact taxonomy not found at expected line; "
        "if reworded, re-validate that PromotionQueueEntry.kind enum "
        "{skill, agent} still matches bible canon"
    )


def test_status_values_match_bible_lifecycle_taxonomy() -> None:
    """Bible 03 §5.5 + bible 07 §5.5 enumerate the lifecycle: queued
    (created at Run finalize) → pending_review (candidate page in
    Notion Pending/) → approved | rejected (operator move). This test
    asserts the canonical strings appear in those sections.
    """
    if not _BIBLE_07_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_07_PATH}")

    bible_text = _BIBLE_07_PATH.read_text(encoding="utf-8")

    # bible 07 §5.5 step 3 names "Pending /" — which corresponds to
    # status="pending_review" on our side.
    assert "Pending /" in bible_text, (
        "bible 07 §5.5 'Pending /' lifecycle stage not found; revisit "
        "PromotionQueueEntry.status enum mapping if reworded"
    )

    # bible 07 §5.5 step 5 names "Approved" and "Rejected".
    assert "Approved" in bible_text
    assert "Rejected" in bible_text


def test_b8_drain_semantics_grounded_in_bible() -> None:
    """Bible 00 §12 B8: "If promotion_queue.json has entries and Notion
    is reachable, attempt promotion writes. Failures stay queued."
    The "stay queued" wording is what justifies the ``attempts``
    counter — entries that fail drain stay in the queue with an
    incremented retry count. If bible removes "stay queued", revisit.
    """
    if not _BIBLE_00_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_00_PATH}")

    bible_text = _BIBLE_00_PATH.read_text(encoding="utf-8")
    assert "Failures stay queued" in bible_text, (
        "bible 00 §12 B8 'Failures stay queued' not found; if reworded, "
        "revisit ``attempts`` field rationale"
    )


def test_queue_file_path_grounded_in_bible() -> None:
    """Bible 00 §11 line 359 lists ``promotion_queue.json`` as a
    canonical repo file. paths.PROMOTION_QUEUE must point at it.
    """
    from paths import PROMOTION_QUEUE

    assert PROMOTION_QUEUE.name == "promotion_queue.json", (
        f"paths.PROMOTION_QUEUE name should be 'promotion_queue.json' "
        f"per bible 00 §11; got {PROMOTION_QUEUE.name!r}"
    )
