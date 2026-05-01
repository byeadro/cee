"""Tests for the SyncMeta schema."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from roles import RoleEnum
from schemas import PageEntry, SyncMeta


_BIBLE_PATH = Path.home() / "cee" / "bible" / "04_database_file_structure.md"


def _valid_page_entry_kwargs() -> dict:
    return {
        "notion_page_id": "352e8536-d882-8050-aff6-f1dbcff68a09",
        "notion_last_edited_time": "2026-05-01T13:42:09Z",
        "local_path": "~/cee/bible/00_project_vision.md",
        "content_sha256": "0" * 64,
    }


def _valid_sync_meta_kwargs() -> dict:
    return {
        "last_synced": "2026-05-01T14:15:22Z",
    }


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_sync_meta_minimal_valid() -> None:
    obj = SyncMeta(**_valid_sync_meta_kwargs())
    assert obj.last_synced == "2026-05-01T14:15:22Z"
    assert obj.schema_version == "1.0.0"
    assert obj.produced_by == "BOOT_SEQUENCER"
    assert obj.pages == {}


def test_sync_meta_full_valid() -> None:
    page = PageEntry(**_valid_page_entry_kwargs())
    obj = SyncMeta(
        last_synced="2026-05-01T14:15:22Z",
        pages={"00_project_vision": page},
    )
    assert len(obj.pages) == 1
    assert obj.pages["00_project_vision"].notion_page_id == (
        "352e8536-d882-8050-aff6-f1dbcff68a09"
    )


def test_sync_meta_missing_required_field_raises() -> None:
    # last_synced is the only required field on SyncMeta.
    with pytest.raises(ValidationError):
        SyncMeta()


@pytest.mark.parametrize(
    "missing_field",
    ["notion_page_id", "notion_last_edited_time", "local_path", "content_sha256"],
)
def test_page_entry_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_page_entry_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        PageEntry(**kwargs)


def test_sync_meta_extra_field_rejected() -> None:
    kwargs = _valid_sync_meta_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        SyncMeta(**kwargs)


def test_page_entry_extra_field_rejected() -> None:
    kwargs = _valid_page_entry_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        PageEntry(**kwargs)


def test_sync_meta_string_whitespace_stripped() -> None:
    obj = SyncMeta(last_synced="  2026-05-01T14:15:22Z  ")
    assert obj.last_synced == "2026-05-01T14:15:22Z"


def test_page_entry_string_whitespace_stripped() -> None:
    kwargs = _valid_page_entry_kwargs()
    kwargs["notion_page_id"] = "  abc  "
    kwargs["local_path"] = "  ~/cee/bible/00_project_vision.md  "
    obj = PageEntry(**kwargs)
    assert obj.notion_page_id == "abc"
    assert obj.local_path == "~/cee/bible/00_project_vision.md"


def test_sync_meta_schema_version_present() -> None:
    assert SyncMeta.SCHEMA_VERSION == "1.0.0"
    assert PageEntry.SCHEMA_VERSION == "1.0.0"


def test_sync_meta_json_round_trip() -> None:
    page = PageEntry(**_valid_page_entry_kwargs())
    original = SyncMeta(
        last_synced="2026-05-01T14:15:22Z",
        pages={"00_project_vision": page},
    )
    payload = original.model_dump_json()
    restored = SyncMeta.model_validate_json(payload)
    assert restored == original


def test_sync_meta_dict_round_trip() -> None:
    page = PageEntry(**_valid_page_entry_kwargs())
    original = SyncMeta(
        last_synced="2026-05-01T14:15:22Z",
        pages={"00_project_vision": page},
    )
    payload = original.model_dump()
    restored = SyncMeta.model_validate(payload)
    assert restored == original


def test_sync_meta_field_order_stable() -> None:
    """Field order matches bible 04 §5.5's JSON example exactly:
    schema_version, produced_by, last_synced, pages.
    """
    obj = SyncMeta(**_valid_sync_meta_kwargs())
    expected_order = [
        "schema_version",
        "produced_by",
        "last_synced",
        "pages",
    ]
    assert list(obj.model_dump().keys()) == expected_order


def test_page_entry_field_order_stable() -> None:
    """Field order matches bible 04 §5.5's PageEntry JSON example."""
    obj = PageEntry(**_valid_page_entry_kwargs())
    expected_order = [
        "notion_page_id",
        "notion_last_edited_time",
        "local_path",
        "content_sha256",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific                                                              #
# --------------------------------------------------------------------------- #


def test_produced_by_defaults_to_boot_sequencer() -> None:
    obj = SyncMeta(**_valid_sync_meta_kwargs())
    assert obj.produced_by == RoleEnum.BOOT_SEQUENCER
    assert obj.produced_by == "BOOT_SEQUENCER"


def test_produced_by_can_be_overridden_at_schema_level() -> None:
    # Override is structurally allowed; bible 02 §7.13 + §10 enforces the
    # BOOT_SEQUENCER constraint at write-time, not via the schema.
    obj = SyncMeta(
        last_synced="2026-05-01T14:15:22Z",
        produced_by=RoleEnum.OPERATOR,
    )
    assert obj.produced_by == RoleEnum.OPERATOR


def test_schema_version_defaults_to_one_zero_zero() -> None:
    obj = SyncMeta(**_valid_sync_meta_kwargs())
    assert obj.schema_version == "1.0.0"
    assert obj.schema_version == SyncMeta.SCHEMA_VERSION


def test_schema_version_appears_in_json_dump() -> None:
    """Bible 04 §5.5 explicitly carries schema_version in the on-disk
    JSON. Phase 1 schemas use ClassVar only; SyncMeta is the first to
    serialize the version field. This test guards that deviation.
    """
    obj = SyncMeta(**_valid_sync_meta_kwargs())
    payload = obj.model_dump()
    assert "schema_version" in payload
    assert payload["schema_version"] == "1.0.0"


def test_pages_defaults_to_empty_dict() -> None:
    a = SyncMeta(**_valid_sync_meta_kwargs())
    b = SyncMeta(**_valid_sync_meta_kwargs())
    a.pages["00_project_vision"] = PageEntry(**_valid_page_entry_kwargs())
    # Default factory must produce independent dicts.
    assert b.pages == {}


def test_last_synced_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        SyncMeta(last_synced="")
    # Whitespace-only also rejected since str_strip_whitespace + min_length=1.
    with pytest.raises(ValidationError):
        SyncMeta(last_synced="   ")


def test_page_entry_content_sha256_format() -> None:
    # Valid: 64 lowercase hex.
    PageEntry(**_valid_page_entry_kwargs())

    # Wrong length.
    bad = _valid_page_entry_kwargs()
    bad["content_sha256"] = "0" * 63
    with pytest.raises(ValidationError):
        PageEntry(**bad)

    # Uppercase hex rejected — pattern enforces lowercase per
    # raw_input.py convention.
    bad = _valid_page_entry_kwargs()
    bad["content_sha256"] = "A" * 64
    with pytest.raises(ValidationError):
        PageEntry(**bad)

    # Non-hex characters rejected.
    bad = _valid_page_entry_kwargs()
    bad["content_sha256"] = "g" * 64
    with pytest.raises(ValidationError):
        PageEntry(**bad)


def test_page_entry_required_fields_must_be_non_empty() -> None:
    """notion_page_id, notion_last_edited_time, local_path all use
    min_length=1; empty strings are rejected.
    """
    for field in ["notion_page_id", "notion_last_edited_time", "local_path"]:
        bad = _valid_page_entry_kwargs()
        bad[field] = ""
        with pytest.raises(ValidationError):
            PageEntry(**bad)


def test_pages_dict_uses_string_keys() -> None:
    """Per bible 04 §5.5, page keys are <NN>_<slug> matching the .md
    filename.
    """
    page = PageEntry(**_valid_page_entry_kwargs())
    obj = SyncMeta(
        last_synced="2026-05-01T14:15:22Z",
        pages={
            "00_project_vision": page,
            "21_first_action_tasks": page.model_copy(
                update={"local_path": "~/cee/bible/21_first_action_tasks.md"}
            ),
        },
    )
    assert "00_project_vision" in obj.pages
    assert "21_first_action_tasks" in obj.pages


def test_pages_value_must_be_page_entry() -> None:
    # A dict missing required PageEntry fields fails coercion.
    with pytest.raises(ValidationError):
        SyncMeta(
            last_synced="2026-05-01T14:15:22Z",
            pages={"00_project_vision": {"local_path": "x"}},
        )


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_sync_meta_field_set_matches_bible() -> None:
    """Bible 04 §5.5's JSON example declares SyncMeta with top-level
    fields {schema_version, produced_by, last_synced, pages} and
    PageEntry with {notion_page_id, notion_last_edited_time, local_path,
    content_sha256}. Implementation must include all of those fields.
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")

    section_start = bible_text.find("### 5.5 Bible sync metadata")
    section_end = bible_text.find("### 5.6", section_start)
    assert section_start != -1, "§5.5 not found in bible 04"
    assert section_end != -1, "§5.6 boundary not found in bible 04"
    section = bible_text[section_start:section_end]

    sync_meta_fields = {
        "schema_version",
        "produced_by",
        "last_synced",
        "pages",
    }
    for field in sync_meta_fields:
        assert f'"{field}":' in section, (
            f"§5.5 JSON example missing top-level field {field!r}"
        )

    page_entry_fields = {
        "notion_page_id",
        "notion_last_edited_time",
        "local_path",
        "content_sha256",
    }
    for field in page_entry_fields:
        assert f'"{field}":' in section, (
            f"§5.5 JSON example missing PageEntry field {field!r}"
        )

    sync_meta_impl_fields = set(SyncMeta.model_fields.keys())
    page_entry_impl_fields = set(PageEntry.model_fields.keys())

    missing_sync = sync_meta_fields - sync_meta_impl_fields
    assert not missing_sync, (
        f"SyncMeta is missing bible §5.5 fields: {sorted(missing_sync)}\n"
        f"Bible: {sorted(sync_meta_fields)}\n"
        f"Impl:  {sorted(sync_meta_impl_fields)}"
    )

    missing_page = page_entry_fields - page_entry_impl_fields
    assert not missing_page, (
        f"PageEntry is missing bible §5.5 fields: {sorted(missing_page)}\n"
        f"Bible: {sorted(page_entry_fields)}\n"
        f"Impl:  {sorted(page_entry_impl_fields)}"
    )
