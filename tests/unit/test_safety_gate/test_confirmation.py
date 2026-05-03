"""Tests for safety_gate/confirmation.py builders + exception class.

Pure-function builder tests + AwaitingDestructiveConfirmation
exception class tests + bible-grounding drift detectors per bible
12 §5.4 + §7.3.
"""

from __future__ import annotations

from pathlib import Path

from errors import AwaitingDestructiveConfirmation, PipelineHalt
from errors.types import HaltType
from roles import RoleEnum
from safety_gate import (
    Confirmation,
    ConfirmationRequest,
    build_confirmation_request,
    build_operator_message,
    build_safety_banner_text,
    record_confirmation,
)


# ---------------------------------------------------------------------------
# build_safety_banner_text — bible §5.4 line 216 (1 test)
# ---------------------------------------------------------------------------


def test_safety_banner_text_is_bible_canonical() -> None:
    """Bible §5.4 line 216 mandates the literal banner string."""
    assert build_safety_banner_text() == "[CONFIRM BEFORE EXECUTION]"


# ---------------------------------------------------------------------------
# build_confirmation_request (4 tests)
# ---------------------------------------------------------------------------


def _build_request() -> ConfirmationRequest:
    return build_confirmation_request(
        run_id="20260430_141522_a3f8c2d1",
        action_description="delete /tmp/test",
        affects=["/tmp/test"],
        requested_at="2026-04-30T14:15:22Z",
    )


def test_build_request_propagates_fields() -> None:
    req = _build_request()
    assert req.run_id == "20260430_141522_a3f8c2d1"
    assert req.action_description == "delete /tmp/test"
    assert req.affects == ["/tmp/test"]
    assert req.requested_at == "2026-04-30T14:15:22Z"


def test_build_request_derives_confirm_and_cancel_commands() -> None:
    """Bible §5.4 lines 225-226: cee confirm <run_id> / cee abort <run_id>."""
    req = _build_request()
    assert req.confirm_command == "cee confirm 20260430_141522_a3f8c2d1"
    assert req.cancel_command == "cee abort 20260430_141522_a3f8c2d1"


def test_build_request_accepts_empty_affects() -> None:
    req = build_confirmation_request(
        run_id="run123",
        action_description="some action",
        affects=[],
        requested_at="2026-04-30T14:15:22Z",
    )
    assert req.affects == []


def test_build_request_is_pure() -> None:
    """Same args → equal output. Pure-function contract."""
    a = _build_request()
    b = _build_request()
    assert a == b


# ---------------------------------------------------------------------------
# build_operator_message — bible §5.4 lines 220-228 template (3 tests)
# ---------------------------------------------------------------------------


def test_operator_message_includes_action_run_id_affects() -> None:
    msg = build_operator_message(_build_request())
    assert "destructive potential" in msg
    assert "delete /tmp/test" in msg
    assert "Run ID: 20260430_141522_a3f8c2d1" in msg
    assert "/tmp/test" in msg


def test_operator_message_includes_confirm_and_cancel_lines() -> None:
    msg = build_operator_message(_build_request())
    assert "Confirm by running: cee confirm 20260430_141522_a3f8c2d1" in msg
    assert "Cancel by running: cee abort 20260430_141522_a3f8c2d1" in msg


def test_operator_message_handles_empty_affects() -> None:
    req = build_confirmation_request(
        run_id="run123",
        action_description="some action",
        affects=[],
        requested_at="2026-04-30T14:15:22Z",
    )
    msg = build_operator_message(req)
    assert "Affects: (none specified)" in msg


# ---------------------------------------------------------------------------
# record_confirmation (3 tests)
# ---------------------------------------------------------------------------


def test_record_confirmation_populates_three_fields() -> None:
    c = record_confirmation(
        timestamp="2026-04-30T14:16:00Z",
        command_used="cee confirm run123",
        operator_identity="adrianbond",
    )
    assert c.timestamp == "2026-04-30T14:16:00Z"
    assert c.command_used == "cee confirm run123"
    assert c.operator_identity == "adrianbond"


def test_record_confirmation_default_produced_by_operator() -> None:
    c = record_confirmation(
        timestamp="t",
        command_used="c",
        operator_identity="o",
    )
    assert c.produced_by == RoleEnum.OPERATOR


def test_record_confirmation_is_pure() -> None:
    a = record_confirmation(
        timestamp="t", command_used="c", operator_identity="o"
    )
    b = record_confirmation(
        timestamp="t", command_used="c", operator_identity="o"
    )
    assert a == b


# ---------------------------------------------------------------------------
# AwaitingDestructiveConfirmation exception (4 tests)
# ---------------------------------------------------------------------------


def test_exception_subclass_of_pipeline_halt() -> None:
    exc = AwaitingDestructiveConfirmation(_build_request())
    assert isinstance(exc, PipelineHalt)


def test_exception_sets_correct_halt_type() -> None:
    exc = AwaitingDestructiveConfirmation(_build_request())
    assert exc.halt_type == HaltType.AWAITING_DESTRUCTIVE_CONFIRMATION


def test_exception_payload_carries_serialized_request() -> None:
    req = _build_request()
    exc = AwaitingDestructiveConfirmation(req)
    assert "request" in exc.payload
    assert exc.payload["request"]["run_id"] == "20260430_141522_a3f8c2d1"
    assert exc.payload["request"]["action_description"] == "delete /tmp/test"
    assert (
        exc.payload["request"]["confirm_command"]
        == "cee confirm 20260430_141522_a3f8c2d1"
    )


def test_exception_payload_is_json_dumpable() -> None:
    """The payload['request'] must be a plain dict (mode='json' dump),
    not a Pydantic instance, so the driver can write it to halt.json."""
    import json

    exc = AwaitingDestructiveConfirmation(_build_request())
    # Round-trip through JSON to confirm no non-serializable fields:
    serialized = json.dumps(exc.payload)
    assert "20260430_141522_a3f8c2d1" in serialized


# ---------------------------------------------------------------------------
# Bible-grounding drift detectors (4 tests)
# ---------------------------------------------------------------------------

_BIBLE_12 = (
    Path(__file__).resolve().parents[3]
    / "bible"
    / "12_prompt_leak_security_rules.md"
)


def test_bible_grounding_safety_banner_text_unchanged() -> None:
    """If bible §5.4 line 216 ever changes, drop the production string."""
    text = _BIBLE_12.read_text(encoding="utf-8")
    assert "[CONFIRM BEFORE EXECUTION]" in text


def test_bible_grounding_detection_still_in_bible_08() -> None:
    """Bible 12 §5.4 line 233 must still defer detection to bible 08
    §5.4.3. If this drifts, T8's no-detection scope decision is
    invalid and is_destructive must be added back."""
    text = _BIBLE_12.read_text(encoding="utf-8")
    assert "section 08 §5.4.3" in text
    assert "This page only handles the gate behavior" in text


def test_bible_grounding_confirmation_three_fields() -> None:
    """Bible §7.3 line 384 must still name the 3 confirmation.json
    fields T8's Confirmation schema implements."""
    text = _BIBLE_12.read_text(encoding="utf-8")
    assert "timestamp" in text
    assert "command used" in text  # bible's prose form (no underscore)
    assert "OPERATOR identity" in text
    assert "whoami" in text


def test_bible_grounding_module_location() -> None:
    """Bible §11 line 468 must still name safety_gate/confirmation.py."""
    text = _BIBLE_12.read_text(encoding="utf-8")
    assert "safety_gate/confirmation.py" in text


# ---------------------------------------------------------------------------
# Schema integration sanity (1 test)
# ---------------------------------------------------------------------------


def test_builders_return_schema_instances() -> None:
    req = _build_request()
    assert isinstance(req, ConfirmationRequest)
    c = record_confirmation(
        timestamp="t", command_used="c", operator_identity="o"
    )
    assert isinstance(c, Confirmation)
