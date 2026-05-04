"""Unit tests for ``llm.anthropic_client`` — Phase 4 T3.

Six tests covering the production surface:

1. LLMResponse is a frozen dataclass.
2. LLMClient Protocol exposes the canonical ``complete`` signature.
3. LiveAnthropicClient.complete rejects nonzero temperature.
4. LiveAnthropicClient.complete emits the canonized audit details shape.
5. default_client_factory raises RuntimeError without CEE_LLM_LIVE.
6. default_client_factory returns LiveAnthropicClient with full env wiring.

Tests use the ``mock_anthropic_sdk`` conftest fixture (bible 18 §5.6)
where they need a working SDK call. Audit emission is verified by
monkeypatching :func:`persistence.audit.audit_log_append` to capture
calls without writing to disk.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import llm.anthropic_client as llm_module
from llm.anthropic_client import (
    LiveAnthropicClient,
    LLMClient,
    LLMResponse,
    default_client_factory,
)
from roles import RoleEnum


# --------------------------------------------------------------------------- #
# 1. LLMResponse frozen-dataclass invariant                                   #
# --------------------------------------------------------------------------- #


def test_llm_response_is_frozen_dataclass() -> None:
    response = LLMResponse(
        text="hello",
        model="claude-opus-4-7",
        input_hash="a" * 64,
        output_hash="b" * 64,
        latency_ms=42,
        prompt_tokens=10,
        completion_tokens=20,
    )
    with pytest.raises(FrozenInstanceError):
        response.text = "tampered"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# 2. LLMClient Protocol shape                                                 #
# --------------------------------------------------------------------------- #


def test_llm_client_protocol_exposes_canonical_complete_signature() -> None:
    """Protocol must declare complete with the bible-grounded keyword args.

    T5 (Interpreter) and T11 (Classifier) consume LLMClient; the
    signature contract must stay stable so swapping implementations
    (live vs test stub) doesn't require touching consumers.
    """
    sig = inspect.signature(LLMClient.complete)
    params = sig.parameters

    assert "system" in params
    assert "user" in params
    assert "max_tokens" in params
    assert "temperature" in params
    assert "run_id" in params
    assert "role" in params

    assert params["max_tokens"].default == 4096
    assert params["temperature"].default == 0.0
    assert params["role"].default == RoleEnum.INTERPRETER


# --------------------------------------------------------------------------- #
# 3. LiveAnthropicClient — temperature contract                               #
# --------------------------------------------------------------------------- #


def test_live_client_rejects_nonzero_temperature(
    mock_anthropic_sdk: list[dict],
) -> None:
    """Bible 03 §5.2 Step 2 + bible 08 §5.5 mandate temperature 0."""
    client = LiveAnthropicClient(api_key="sk-ant-test", model="claude-opus-4-7")

    with pytest.raises(ValueError, match="temperature=0.0"):
        client.complete(
            system="anything",
            user="anything",
            temperature=0.5,
        )


# --------------------------------------------------------------------------- #
# 4. LiveAnthropicClient — audit emission shape                               #
# --------------------------------------------------------------------------- #


def test_live_client_emits_audit_with_canonized_details_shape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mock_anthropic_sdk: list[dict],
) -> None:
    """T3 canonizes ``details`` for ``event="llm_call"`` (candidate #61)."""
    # Seed a fixture matching the input hash this call will produce.
    from tests.conftest import _compute_input_hash

    expected_hash = _compute_input_hash(
        model="claude-opus-4-7",
        system="sys-prompt",
        user="user-prompt",
        max_tokens=4096,
    )
    fixture_dir = Path(__file__).resolve().parents[2] / "fixtures" / "llm_responses"
    fixture_path = fixture_dir / f"{expected_hash}.json"
    fixture_path.write_text(
        json.dumps(
            {"text": "canned-response", "input_tokens": 7, "output_tokens": 3}
        ),
        encoding="utf-8",
    )

    captured: list[dict] = []

    def fake_audit(
        log_path: Path,
        actor: str,
        event: str,
        details: dict,
        run_id: str | None = None,
    ) -> str:
        captured.append(
            {
                "log_path": log_path,
                "actor": actor,
                "event": event,
                "details": details,
                "run_id": run_id,
            }
        )
        return "fake-entry-hash"

    monkeypatch.setattr(llm_module, "audit_log_append", fake_audit)

    try:
        client = LiveAnthropicClient(
            api_key="sk-ant-test", model="claude-opus-4-7"
        )
        response = client.complete(
            system="sys-prompt",
            user="user-prompt",
            run_id="run-test-001",
            role=RoleEnum.CLASSIFIER,
        )
    finally:
        # Clean up the seeded fixture to keep the directory empty for
        # other tests.
        fixture_path.unlink(missing_ok=True)

    assert response.text == "canned-response"
    assert response.prompt_tokens == 7
    assert response.completion_tokens == 3

    assert len(captured) == 1
    entry = captured[0]
    assert entry["event"] == "llm_call"
    assert entry["actor"] == "CLASSIFIER"
    assert entry["run_id"] == "run-test-001"

    details = entry["details"]
    assert details["model"] == "claude-opus-4-7"
    assert details["mode"] == "live"
    assert details["input_hash"] == expected_hash
    assert details["output_hash"]
    assert details["latency_ms"] >= 0
    assert details["prompt_tokens"] == 7
    assert details["completion_tokens"] == 3


# --------------------------------------------------------------------------- #
# 5. default_client_factory — env-var gate                                    #
# --------------------------------------------------------------------------- #


def test_default_client_factory_requires_cee_llm_live_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CEE_LLM_LIVE", raising=False)

    with pytest.raises(RuntimeError, match="CEE_LLM_LIVE"):
        default_client_factory()


# --------------------------------------------------------------------------- #
# 6. default_client_factory — returns LiveAnthropicClient under full env     #
# --------------------------------------------------------------------------- #


def test_default_client_factory_returns_live_client_with_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end factory wiring: env var + API key + pinned model."""
    monkeypatch.setenv("CEE_LLM_LIVE", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-factory-test-key")

    monkeypatch.setattr(
        llm_module, "_load_pinned_model", lambda: "claude-opus-4-7"
    )

    client = default_client_factory()
    assert isinstance(client, LiveAnthropicClient)
    assert client.model == "claude-opus-4-7"
