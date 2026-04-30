"""Tests for the RawInput schema."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas import Attachment, RawInput


_BIBLE_PATH = Path.home() / "cee" / "bible" / "03_full_system_workflow.md"


def _valid_attachment_kwargs() -> dict:
    return {
        "filename": "report.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1234,
        "sha256": "0" * 64,
        "path": "attachments/report.pdf",
    }


def _valid_raw_input_kwargs() -> dict:
    return {
        "text": "Refactor the auth module.",
        "timestamp": "2026-04-30T14:00:00Z",
        "source": "cli",
    }


# --------------------------------------------------------------------------- #
# Standard schema tests                                                       #
# --------------------------------------------------------------------------- #


def test_raw_input_minimal_valid() -> None:
    obj = RawInput(**_valid_raw_input_kwargs())
    assert obj.text == "Refactor the auth module."
    assert obj.attachments == []
    assert obj.target_executor == "claude_code"
    assert obj.produced_by == "OPERATOR"
    assert obj.source == "cli"


def test_raw_input_full_valid() -> None:
    attachment = Attachment(**_valid_attachment_kwargs())
    obj = RawInput(
        text="Analyze the attached log.",
        attachments=[attachment],
        target_executor="claude_ai",
        timestamp="2026-04-30T14:00:00Z",
        source="api",
        produced_by="OPERATOR",
    )
    assert len(obj.attachments) == 1
    assert obj.target_executor == "claude_ai"
    assert obj.source == "api"


@pytest.mark.parametrize("missing_field", ["text", "timestamp", "source"])
def test_raw_input_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_raw_input_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        RawInput(**kwargs)


def test_raw_input_extra_field_rejected() -> None:
    kwargs = _valid_raw_input_kwargs()
    kwargs["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        RawInput(**kwargs)


def test_raw_input_string_whitespace_stripped() -> None:
    obj = RawInput(
        text="  hello  ",
        timestamp="  2026-04-30T14:00:00Z  ",
        source="cli",
    )
    assert obj.text == "hello"
    assert obj.timestamp == "2026-04-30T14:00:00Z"


def test_raw_input_schema_version_present() -> None:
    assert RawInput.SCHEMA_VERSION == "1.0.0"
    assert Attachment.SCHEMA_VERSION == "1.0.0"


def test_raw_input_json_round_trip() -> None:
    original = RawInput(**_valid_raw_input_kwargs())
    payload = original.model_dump_json()
    restored = RawInput.model_validate_json(payload)
    assert restored == original


def test_raw_input_dict_round_trip() -> None:
    original = RawInput(**_valid_raw_input_kwargs())
    payload = original.model_dump()
    restored = RawInput.model_validate(payload)
    assert restored == original


def test_raw_input_field_order_stable() -> None:
    obj = RawInput(**_valid_raw_input_kwargs())
    expected_order = [
        "text",
        "timestamp",
        "source",
        "attachments",
        "target_executor",
        "produced_by",
    ]
    assert list(obj.model_dump().keys()) == expected_order


# --------------------------------------------------------------------------- #
# Model-specific                                                              #
# --------------------------------------------------------------------------- #


def test_text_must_be_non_empty() -> None:
    with pytest.raises(ValidationError):
        RawInput(text="", timestamp="2026-04-30T14:00:00Z", source="cli")
    # Whitespace-only also rejected since str_strip_whitespace + min_length=1.
    with pytest.raises(ValidationError):
        RawInput(text="   ", timestamp="2026-04-30T14:00:00Z", source="cli")


def test_attachment_sha256_format() -> None:
    # Valid: 64 lowercase hex.
    Attachment(**_valid_attachment_kwargs())

    # Wrong length.
    bad = _valid_attachment_kwargs()
    bad["sha256"] = "0" * 63
    with pytest.raises(ValidationError):
        Attachment(**bad)

    # Uppercase hex rejected (the spec is lowercase hex).
    bad = _valid_attachment_kwargs()
    bad["sha256"] = "A" * 64
    with pytest.raises(ValidationError):
        Attachment(**bad)

    # Non-hex characters rejected.
    bad = _valid_attachment_kwargs()
    bad["sha256"] = "g" * 64
    with pytest.raises(ValidationError):
        Attachment(**bad)


def test_target_executor_enum_enforced() -> None:
    kwargs = _valid_raw_input_kwargs()
    kwargs["target_executor"] = "claude_unknown"
    with pytest.raises(ValidationError):
        RawInput(**kwargs)


@pytest.mark.parametrize("source", ["cli", "api", "resume", "replay"])
def test_source_accepts_valid_enum(source: str) -> None:
    kwargs = _valid_raw_input_kwargs()
    kwargs["source"] = source
    RawInput(**kwargs)


def test_source_rejects_invalid_enum() -> None:
    kwargs = _valid_raw_input_kwargs()
    kwargs["source"] = "stdin"
    with pytest.raises(ValidationError):
        RawInput(**kwargs)


def test_attachments_default_empty_list() -> None:
    a = RawInput(**_valid_raw_input_kwargs())
    b = RawInput(**_valid_raw_input_kwargs())
    a.attachments.append(Attachment(**_valid_attachment_kwargs()))
    # Default factory must produce independent lists.
    assert b.attachments == []


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_raw_input_field_set_matches_bible() -> None:
    """Bible 03 Step 1 declares RawInput with {text, timestamp, source,
    attachments[], target_executor}. Implementation must include all of
    those fields. ``produced_by`` is permitted as an extra (authorized
    by section 02's role tracking convention).
    """
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")

    # Find: "RawInput with `{text, timestamp, source, attachments[], target_executor}`"
    pattern = re.compile(
        r"`RawInput`\s*with\s*`\{([^}]+)\}`",
        re.IGNORECASE,
    )
    match = pattern.search(bible_text)
    assert match, "Could not locate RawInput field list in bible 03 Step 1"

    # Extract and normalize: strip [] suffixes, whitespace.
    raw_fields = match.group(1).split(",")
    bible_fields = {f.strip().rstrip("[]").strip() for f in raw_fields if f.strip()}

    impl_fields = set(RawInput.model_fields.keys())

    missing = bible_fields - impl_fields
    assert not missing, (
        f"RawInput is missing bible-required fields: {sorted(missing)}\n"
        f"Bible: {sorted(bible_fields)}\n"
        f"Impl:  {sorted(impl_fields)}"
    )
