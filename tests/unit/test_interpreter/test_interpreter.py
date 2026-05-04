"""Tests for the :class:`Interpreter` orchestration class.

T5's DI surface (``Interpreter(client=..., config=...)``) is the
canonical unit-test seam — bible 18 §5.6's ``mock_anthropic_sdk``
fixture is for testing :class:`llm.LiveAnthropicClient` itself
(T3's responsibility); for T5 we stub :class:`llm.LLMClient`
directly via DI so the test exercises T5 logic in isolation
without entangling SDK monkey-patch state.

The companion fixture set at
``tests/fixtures/llm_responses/*.json`` is seeded as canonical
reference data for T12 (determinism framework) and T13
(integration test) which exercise the full T3 → T5 chain.

Reference: bible 03 §5.2 Step 2, bible 03 §5.3, bible 12 §5.8,
bible 19 §5.1, §5.4, §8.3.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import interpreter.interpreter as interp_mod
import paths
from errors import (
    HaltType,
    NoExecutableIntent,
    PausedForClarification,
    RunError,
    RunErrorType,
)
from interpreter import Interpreter, InterpreterConfig
from llm import LLMResponse
from roles import RoleEnum
from schemas.raw_input import RawInput


# --------------------------------------------------------------------------- #
# Helpers and fixtures                                                        #
# --------------------------------------------------------------------------- #


_VALID_INTENT_LOW = json.dumps(
    {
        "goal": "Write a Supabase RLS policy.",
        "deliverable": "A SQL policy statement.",
        "constraints": ["Supabase RLS"],
        "implicit_assumptions": ["mentor_inquiries has user_id column"],
        "ambiguity_score": 0.15,
        "domain": "code",
        "raw_signals": ["task_explicit", "domain_specific_terminology"],
    }
)


_VALID_INTENT_MID = json.dumps(
    {
        "goal": "Examine a Bernhard utility bill PDF.",
        "deliverable": "A structured findings report.",
        "constraints": [],
        "implicit_assumptions": ["last quarter's bills exist"],
        "ambiguity_score": 0.45,
        "domain": "analysis",
        "raw_signals": ["task_explicit", "comparison_required"],
    }
)


_VALID_INTENT_HIGH = json.dumps(
    {
        "goal": "Help with the project.",
        "deliverable": "Clarification.",
        "constraints": [],
        "implicit_assumptions": ["unclear what 'project' means"],
        "ambiguity_score": 0.85,
        "domain": "other",
        "raw_signals": [],
    }
)


_VALID_INTENT_HIGH_NO_ASSUMPTIONS = json.dumps(
    {
        "goal": "Do something.",
        "deliverable": "Anything.",
        "constraints": [],
        "implicit_assumptions": [],
        "ambiguity_score": 0.95,
        "domain": "other",
        "raw_signals": [],
    }
)


_SENTINEL_INTENT = json.dumps(
    {
        "goal": "Input is empty or non-actionable",
        "deliverable": "Clarification from the OPERATOR",
        "constraints": [],
        "implicit_assumptions": [],
        "ambiguity_score": 1.0,
        "domain": "other",
        "raw_signals": [],
    }
)


class _StubLLMClient:
    """Stub :class:`llm.LLMClient` that returns a configured response.

    Unit-test seam for T5; satisfies the LLMClient Protocol via duck
    typing. Records every ``complete`` invocation in :attr:`calls`.
    """

    def __init__(
        self,
        *,
        response_text: str = "{}",
        raises: BaseException | None = None,
    ) -> None:
        self.response_text = response_text
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        run_id: str | None = None,
        role: RoleEnum = RoleEnum.INTERPRETER,
    ) -> LLMResponse:
        self.calls.append(
            {
                "system": system,
                "user": user,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "run_id": run_id,
                "role": role,
            }
        )
        if self.raises is not None:
            raise self.raises
        return LLMResponse(
            text=self.response_text,
            model="stub-model",
            input_hash="0" * 64,
            output_hash="1" * 64,
            latency_ms=1,
            prompt_tokens=10,
            completion_tokens=5,
        )


_RUN_ID = "20260504_140000_a1b2c3d4"


def _make_raw_input(text: str) -> RawInput:
    return RawInput(
        text=text,
        timestamp="2026-05-04T14:00:00Z",
        source="cli",
    )


@pytest.fixture
def stub_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Patch bible/runs/prompts paths to controlled tmp content.

    Bible content is minimal but non-empty so :func:`_load_bible_context`
    returns a valid string. Runs dir is empty so the recent-runs
    block renders the empty-section sentinel.
    """
    bible_dir = tmp_path / "bible"
    bible_dir.mkdir()
    (bible_dir / "00_project_vision.md").write_text(
        "VISION", encoding="utf-8"
    )
    (bible_dir / "01_real_problem_breakdown.md").write_text(
        "PROBLEM", encoding="utf-8"
    )

    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "interpreter_system.txt").write_text(
        "STUB SYSTEM PROMPT", encoding="utf-8"
    )

    monkeypatch.setattr(paths, "BIBLE_DIR", bible_dir)
    monkeypatch.setattr(paths, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(paths, "PROMPTS_DIR", prompts_dir)
    return tmp_path


@pytest.fixture
def captured_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, Any]]:
    """Capture :func:`audit_log_append` calls without writing to disk."""
    captured: list[dict[str, Any]] = []

    def fake_audit(
        *,
        log_path: Path,
        actor: str,
        event: str,
        details: dict[str, Any],
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

    monkeypatch.setattr(interp_mod, "audit_log_append", fake_audit)
    return captured


# --------------------------------------------------------------------------- #
# Pleasantry + sentinel halts                                                 #
# --------------------------------------------------------------------------- #


def test_pleasantry_pre_detect_raises_no_executable_intent(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    client = _StubLLMClient()
    interpreter_obj = Interpreter(client=client)

    with pytest.raises(NoExecutableIntent) as excinfo:
        interpreter_obj.run(_make_raw_input("hi"), run_id=_RUN_ID)

    exc = excinfo.value
    assert exc.halt_type == HaltType.NO_EXECUTABLE_INTENT
    assert exc.payload["reason"] == "regex_pleasantry"
    assert exc.payload["raw_text_preview"] == "hi"
    assert exc.payload["run_id"] == _RUN_ID
    # Stub LLM client must NOT be called when pleasantry pre-detects.
    assert client.calls == []


def test_sentinel_post_detect_raises_no_executable_intent(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    client = _StubLLMClient(response_text=_SENTINEL_INTENT)
    interpreter_obj = Interpreter(client=client)

    with pytest.raises(NoExecutableIntent) as excinfo:
        interpreter_obj.run(
            _make_raw_input("?? what should we do here ??"),
            run_id=_RUN_ID,
        )

    exc = excinfo.value
    assert exc.payload["reason"] == "claude_sentinel"
    assert len(client.calls) == 1


# --------------------------------------------------------------------------- #
# Happy paths — low and mid ambiguity                                         #
# --------------------------------------------------------------------------- #


def test_happy_path_low_ambiguity_returns_intent_object(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    client = _StubLLMClient(response_text=_VALID_INTENT_LOW)
    interpreter_obj = Interpreter(client=client)

    intent = interpreter_obj.run(
        _make_raw_input("write me a Supabase RLS policy"),
        run_id=_RUN_ID,
    )

    assert intent.goal == "Write a Supabase RLS policy."
    assert intent.ambiguity_score == 0.15
    assert intent.domain == "code"
    assert intent.produced_by == RoleEnum.INTERPRETER


def test_happy_path_mid_ambiguity_continues_silently(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    """ambiguity in [0.3, 0.6] returns IntentObject (no halt)."""
    client = _StubLLMClient(response_text=_VALID_INTENT_MID)
    interpreter_obj = Interpreter(client=client)

    intent = interpreter_obj.run(
        _make_raw_input("look at this utility bill PDF for anomalies"),
        run_id=_RUN_ID,
    )

    assert 0.3 <= intent.ambiguity_score <= 0.6
    assert intent.implicit_assumptions  # surfaced for FinalPrompt later


# --------------------------------------------------------------------------- #
# Ambiguity halt                                                              #
# --------------------------------------------------------------------------- #


def test_high_ambiguity_raises_paused_for_clarification(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    client = _StubLLMClient(response_text=_VALID_INTENT_HIGH)
    interpreter_obj = Interpreter(client=client)

    with pytest.raises(PausedForClarification) as excinfo:
        interpreter_obj.run(
            _make_raw_input("help me with the project"),
            run_id=_RUN_ID,
        )

    exc = excinfo.value
    assert exc.halt_type == HaltType.PAUSED_FOR_CLARIFICATION
    request = exc.payload["request"]
    assert request["run_id"] == _RUN_ID
    assert request["paused_at_step"] == 2
    assert len(request["questions"]) == 1
    assert "unclear what 'project' means" in request["questions"][0]["question"]


def test_high_ambiguity_with_empty_assumptions_uses_fallback_question(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    client = _StubLLMClient(response_text=_VALID_INTENT_HIGH_NO_ASSUMPTIONS)
    interpreter_obj = Interpreter(client=client)

    with pytest.raises(PausedForClarification) as excinfo:
        interpreter_obj.run(
            _make_raw_input("uhh do the thing maybe"),
            run_id=_RUN_ID,
        )

    request = excinfo.value.payload["request"]
    assert len(request["questions"]) == 1
    assert request["questions"][0]["id"] == "ambiguity-clarification"
    assert (
        request["questions"][0]["question"]
        == "What specifically should I help you accomplish? "
        "The current input is too ambiguous to proceed."
    )


# --------------------------------------------------------------------------- #
# produced_by injection                                                       #
# --------------------------------------------------------------------------- #


def test_produced_by_injected_when_claude_omits_field(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    """T4 prompt instructs Claude not to emit produced_by; T5 fills."""
    client = _StubLLMClient(response_text=_VALID_INTENT_LOW)
    interpreter_obj = Interpreter(client=client)

    intent = interpreter_obj.run(
        _make_raw_input("write me a Supabase RLS policy"),
        run_id=_RUN_ID,
    )

    assert intent.produced_by == RoleEnum.INTERPRETER


def test_produced_by_overwritten_when_claude_emits_field(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    """If Claude emits produced_by anyway, T5 strips and re-injects.

    Without this defense, ``extra="forbid"`` would reject any Claude
    output that included produced_by, even if the value happened to
    be the canonical "INTERPRETER".
    """
    payload = json.loads(_VALID_INTENT_LOW)
    payload["produced_by"] = "OPERATOR"  # wrong but should be overwritten
    client = _StubLLMClient(response_text=json.dumps(payload))
    interpreter_obj = Interpreter(client=client)

    intent = interpreter_obj.run(
        _make_raw_input("write me a Supabase RLS policy"),
        run_id=_RUN_ID,
    )

    assert intent.produced_by == RoleEnum.INTERPRETER


# --------------------------------------------------------------------------- #
# RunError(SCHEMA_VIOLATION) failure modes                                    #
# --------------------------------------------------------------------------- #


def test_non_json_output_raises_run_error_json_parse(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    client = _StubLLMClient(response_text="not json at all")
    interpreter_obj = Interpreter(client=client)

    with pytest.raises(RunError) as excinfo:
        interpreter_obj.run(
            _make_raw_input("write me a Supabase RLS policy"),
            run_id=_RUN_ID,
        )

    assert excinfo.value.error_type == RunErrorType.SCHEMA_VIOLATION
    assert excinfo.value.payload["stage"] == "json_parse"
    assert excinfo.value.payload["module"] == "interpreter"


def test_missing_required_field_raises_run_error_schema_validate(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    payload = json.loads(_VALID_INTENT_LOW)
    del payload["domain"]
    client = _StubLLMClient(response_text=json.dumps(payload))
    interpreter_obj = Interpreter(client=client)

    with pytest.raises(RunError) as excinfo:
        interpreter_obj.run(
            _make_raw_input("write me a Supabase RLS policy"),
            run_id=_RUN_ID,
        )

    assert excinfo.value.error_type == RunErrorType.SCHEMA_VIOLATION
    assert excinfo.value.payload["stage"] == "schema_validate"


def test_extra_field_raises_run_error(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    payload = json.loads(_VALID_INTENT_LOW)
    payload["unknown_extra_field"] = "boom"
    client = _StubLLMClient(response_text=json.dumps(payload))
    interpreter_obj = Interpreter(client=client)

    with pytest.raises(RunError) as excinfo:
        interpreter_obj.run(
            _make_raw_input("write me a Supabase RLS policy"),
            run_id=_RUN_ID,
        )

    assert excinfo.value.payload["stage"] == "schema_validate"


def test_wrong_type_raises_run_error(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    """Pydantic coerces numeric strings; to trigger schema_validate we
    use a non-numeric string for the ambiguity_score float field."""
    payload = json.loads(_VALID_INTENT_LOW)
    payload["ambiguity_score"] = "definitely-not-a-number"
    client = _StubLLMClient(response_text=json.dumps(payload))
    interpreter_obj = Interpreter(client=client)

    with pytest.raises(RunError) as excinfo:
        interpreter_obj.run(
            _make_raw_input("write me a Supabase RLS policy"),
            run_id=_RUN_ID,
        )

    assert excinfo.value.payload["stage"] == "schema_validate"


def test_domain_enum_violation_raises_run_error(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    payload = json.loads(_VALID_INTENT_LOW)
    payload["domain"] = "invalid_domain"
    client = _StubLLMClient(response_text=json.dumps(payload))
    interpreter_obj = Interpreter(client=client)

    with pytest.raises(RunError) as excinfo:
        interpreter_obj.run(
            _make_raw_input("write me a Supabase RLS policy"),
            run_id=_RUN_ID,
        )

    assert excinfo.value.payload["stage"] == "schema_validate"


# --------------------------------------------------------------------------- #
# Audit emission                                                              #
# --------------------------------------------------------------------------- #


def test_audit_step_start_emitted(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    client = _StubLLMClient(response_text=_VALID_INTENT_LOW)
    Interpreter(client=client).run(
        _make_raw_input("write me a Supabase RLS policy"), run_id=_RUN_ID
    )

    starts = [c for c in captured_audit if c["event"] == "pipeline_step_start"]
    assert len(starts) == 1
    entry = starts[0]
    assert entry["actor"] == "INTERPRETER"
    assert entry["run_id"] == _RUN_ID
    assert entry["details"]["step"] == 2
    assert entry["details"]["source"] == "cli"
    # raw_input_hash must be the SHA-256 of the raw text.
    expected_hash = hashlib.sha256(
        b"write me a Supabase RLS policy"
    ).hexdigest()
    assert entry["details"]["raw_input_hash"] == expected_hash


def test_audit_step_complete_emitted_on_success(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    client = _StubLLMClient(response_text=_VALID_INTENT_LOW)
    Interpreter(client=client).run(
        _make_raw_input("write me a Supabase RLS policy"), run_id=_RUN_ID
    )

    completes = [
        c for c in captured_audit if c["event"] == "pipeline_step_complete"
    ]
    assert len(completes) == 1
    entry = completes[0]
    assert entry["details"]["outcome"] == "success"
    assert entry["details"]["ambiguity_score"] == 0.15
    assert entry["details"]["duration_ms"] >= 0


def test_audit_step_complete_emitted_on_halt_path(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    """try/finally in Interpreter.run() must always emit step_complete."""
    client = _StubLLMClient(response_text=_VALID_INTENT_HIGH)
    with pytest.raises(PausedForClarification):
        Interpreter(client=client).run(
            _make_raw_input("help me with the project"), run_id=_RUN_ID
        )

    completes = [
        c for c in captured_audit if c["event"] == "pipeline_step_complete"
    ]
    assert len(completes) == 1
    assert (
        completes[0]["details"]["outcome"] == "halt:paused_for_clarification"
    )
    assert completes[0]["details"]["ambiguity_score"] == 0.85


def test_audit_step_complete_emitted_on_error_path(
    stub_paths: Path,
    captured_audit: list[dict[str, Any]],
) -> None:
    client = _StubLLMClient(response_text="not json")
    with pytest.raises(RunError):
        Interpreter(client=client).run(
            _make_raw_input("write me a Supabase RLS policy"),
            run_id=_RUN_ID,
        )

    completes = [
        c for c in captured_audit if c["event"] == "pipeline_step_complete"
    ]
    assert len(completes) == 1
    assert completes[0]["details"]["outcome"] == "error:schema_violation"
    # ambiguity_score is None when error fires before validation.
    assert completes[0]["details"]["ambiguity_score"] is None
