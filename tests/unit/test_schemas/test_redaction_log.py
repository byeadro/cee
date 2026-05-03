"""Tests for the RedactionLog + RedactionLogEntry schemas standalone.

Schema-side tests independent of the redactor module. Bible-grounding
+ field-shape + round-trip + extras-forbidden + term-field optionality.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from roles import RoleEnum
from schemas import RedactionLog, RedactionLogEntry


def _valid_entry_kwargs() -> dict:
    return {
        "pattern": "anthropic_api_key",
        "location": "prompt",
        "replaced_with": "<redacted:anthropic_api_key>",
    }


def test_entry_minimal_valid() -> None:
    entry = RedactionLogEntry(**_valid_entry_kwargs())
    assert entry.pattern == "anthropic_api_key"
    assert entry.location == "prompt"
    assert entry.replaced_with == "<redacted:anthropic_api_key>"
    assert entry.term is None


def test_entry_with_term() -> None:
    """Per bible 12 §5.1 user_term entries carry the matched term."""
    entry = RedactionLogEntry(
        pattern="user_term",
        location="prompt",
        replaced_with="<redacted:user_term>",
        term="ClientCorp",
    )
    assert entry.term == "ClientCorp"


@pytest.mark.parametrize(
    "missing_field", ["pattern", "location", "replaced_with"]
)
def test_entry_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_entry_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        RedactionLogEntry(**kwargs)


def test_entry_extras_forbidden() -> None:
    kwargs = _valid_entry_kwargs()
    kwargs["mystery"] = "x"
    with pytest.raises(ValidationError):
        RedactionLogEntry(**kwargs)


def test_log_default_produced_by_safety_gate() -> None:
    log = RedactionLog()
    assert log.produced_by == RoleEnum.SAFETY_GATE


def test_log_round_trip_with_entries() -> None:
    entry = RedactionLogEntry(**_valid_entry_kwargs())
    original = RedactionLog(redactions=[entry])
    restored = RedactionLog.model_validate_json(original.model_dump_json())
    assert restored == original


def test_log_schema_version_present() -> None:
    assert RedactionLog.SCHEMA_VERSION == "1.0.0"
    assert RedactionLogEntry.SCHEMA_VERSION == "1.0.0"
