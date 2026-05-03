"""Tests for the Confirmation + ConfirmationRequest schemas standalone.

Schema-side tests independent of the safety_gate.confirmation builder
module. Bible-grounding + field-shape + round-trip + extras-forbidden
+ default-produced-by-divergence per bible 12 §7.3.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from roles import RoleEnum
from schemas import Confirmation, ConfirmationRequest


# ---------------------------------------------------------------------------
# Confirmation — bible §7.3 line 384 (3 fields verbatim)
# ---------------------------------------------------------------------------


def _valid_confirmation_kwargs() -> dict:
    return {
        "timestamp": "2026-04-30T14:15:22Z",
        "command_used": "cee confirm 20260430_141522_a3f8c2d1",
        "operator_identity": "adrianbond",
    }


def test_confirmation_minimal_valid() -> None:
    c = Confirmation(**_valid_confirmation_kwargs())
    assert c.timestamp == "2026-04-30T14:15:22Z"
    assert c.command_used == "cee confirm 20260430_141522_a3f8c2d1"
    assert c.operator_identity == "adrianbond"


def test_confirmation_default_produced_by_operator() -> None:
    """Per bible §7.3 line 384 OPERATOR is the authoring identity."""
    c = Confirmation(**_valid_confirmation_kwargs())
    assert c.produced_by == RoleEnum.OPERATOR


@pytest.mark.parametrize(
    "missing_field", ["timestamp", "command_used", "operator_identity"]
)
def test_confirmation_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_confirmation_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        Confirmation(**kwargs)


def test_confirmation_extras_forbidden() -> None:
    kwargs = _valid_confirmation_kwargs()
    kwargs["mystery"] = "x"
    with pytest.raises(ValidationError):
        Confirmation(**kwargs)


def test_confirmation_round_trip() -> None:
    original = Confirmation(**_valid_confirmation_kwargs())
    restored = Confirmation.model_validate_json(original.model_dump_json())
    assert restored == original


# ---------------------------------------------------------------------------
# ConfirmationRequest — bible §7.3 line 383 (T8-defined shape; #47)
# ---------------------------------------------------------------------------


def _valid_request_kwargs() -> dict:
    return {
        "run_id": "20260430_141522_a3f8c2d1",
        "action_description": "delete /tmp/test",
        "affects": ["/tmp/test"],
        "requested_at": "2026-04-30T14:15:22Z",
        "confirm_command": "cee confirm 20260430_141522_a3f8c2d1",
        "cancel_command": "cee abort 20260430_141522_a3f8c2d1",
    }


def test_request_minimal_valid() -> None:
    req = ConfirmationRequest(**_valid_request_kwargs())
    assert req.run_id == "20260430_141522_a3f8c2d1"
    assert req.action_description == "delete /tmp/test"
    assert req.affects == ["/tmp/test"]


def test_request_default_produced_by_safety_gate() -> None:
    """SAFETY_GATE emits the request at the gate per bible §5.4."""
    req = ConfirmationRequest(**_valid_request_kwargs())
    assert req.produced_by == RoleEnum.SAFETY_GATE


def test_request_default_affects_is_empty_list() -> None:
    """affects has a default_factory; bible §5.4 line 223 says
    "<list of paths/systems detected>" — empty list is allowed."""
    kwargs = _valid_request_kwargs()
    del kwargs["affects"]
    req = ConfirmationRequest(**kwargs)
    assert req.affects == []


@pytest.mark.parametrize(
    "missing_field",
    [
        "run_id",
        "action_description",
        "requested_at",
        "confirm_command",
        "cancel_command",
    ],
)
def test_request_missing_required_field_raises(missing_field: str) -> None:
    kwargs = _valid_request_kwargs()
    del kwargs[missing_field]
    with pytest.raises(ValidationError):
        ConfirmationRequest(**kwargs)


def test_request_extras_forbidden() -> None:
    kwargs = _valid_request_kwargs()
    kwargs["mystery"] = "x"
    with pytest.raises(ValidationError):
        ConfirmationRequest(**kwargs)


def test_request_round_trip() -> None:
    original = ConfirmationRequest(**_valid_request_kwargs())
    restored = ConfirmationRequest.model_validate_json(
        original.model_dump_json()
    )
    assert restored == original


# ---------------------------------------------------------------------------
# Schema-version invariant
# ---------------------------------------------------------------------------


def test_schema_versions_present() -> None:
    assert Confirmation.SCHEMA_VERSION == "1.0.0"
    assert ConfirmationRequest.SCHEMA_VERSION == "1.0.0"
