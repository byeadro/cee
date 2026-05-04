"""Test infrastructure shared across all CEE tests.

Currently houses the bible 18 §5.6 SDK-boundary mocking fixture for
Anthropic API calls. Tests that exercise :class:`llm.LiveAnthropicClient`
opt in by requesting the ``mock_anthropic_sdk`` fixture; production code
never invokes this layer (production uses
:func:`llm.default_client_factory` with ``CEE_LLM_LIVE=true``).

Bible 18 §5.6 verbatim:

    Anthropic SDK calls are mocked via ``~/cee/tests/conftest.py``:
    ``monkeypatch.setattr(anthropic.Anthropic, "messages.create", fake_create)``.
    Canned responses live at ``~/cee/tests/fixtures/llm_responses/<input_hash>.json``.

T3 ships the fixture without canned responses (the directory is
empty); T5 + T11 will populate ``tests/fixtures/llm_responses/`` as
their tests need specific Claude outputs. The cache-miss policy is
``pytest.fail`` with explicit remediation pointing at the deferred
``cee record-llm-response`` CLI command (bible 18 §5.6).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


_FIXTURE_DIR: Path = Path(__file__).parent / "fixtures" / "llm_responses"


def _compute_input_hash(
    *, model: str, system: str, user: str, max_tokens: int
) -> str:
    """Mirror :func:`llm.anthropic_client._compute_input_hash`.

    Duplicated rather than imported so the conftest stays usable even
    when ``llm.anthropic_client`` is monkeypatched mid-test.
    """
    payload = (
        f"model={model}\n"
        f"max_tokens={max_tokens}\n"
        f"system={system}\n"
        f"user={user}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class _FakeUsage:
    """Mirrors ``anthropic.types.Usage`` shape for the fields T3 reads."""

    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class _FakeContentBlock:
    """Mirrors the ``response.content[0]`` shape for ``.text`` access."""

    text: str


@dataclass(frozen=True)
class _FakeMessage:
    """Mirrors the ``Message`` return shape T3 reads (``content``, ``usage``)."""

    content: list[_FakeContentBlock]
    usage: _FakeUsage


def _load_fixture(input_hash: str) -> dict[str, Any]:
    """Read the canned response for ``input_hash`` or fail with remediation."""
    fixture_path = _FIXTURE_DIR / f"{input_hash}.json"
    if not fixture_path.exists():
        pytest.fail(
            f"No LLM fixture for input_hash {input_hash!r} at "
            f"{fixture_path}. Capture via the deferred "
            f"`cee record-llm-response` CLI (bible 18 §5.6) or seed the "
            f"file manually with the expected response shape: "
            f'{{"text": "...", "input_tokens": int, "output_tokens": int}}.'
        )
    return json.loads(fixture_path.read_text(encoding="utf-8"))


@pytest.fixture
def mock_anthropic_sdk(monkeypatch: pytest.MonkeyPatch):
    """Monkeypatch ``anthropic.Anthropic.messages.create`` per bible 18 §5.6.

    Returns a recorder dict so tests can inspect calls. The fixture
    intercepts the SDK call, computes the input_hash via the same
    formula T3 uses, looks up the cached response in
    ``tests/fixtures/llm_responses/<input_hash>.json``, and returns a
    ``_FakeMessage`` with the canned text + token counts.
    """
    import anthropic

    calls: list[dict[str, Any]] = []

    def fake_create(
        self: Any,
        *,
        model: str,
        max_tokens: int,
        messages: list[dict[str, str]],
        system: str = "",
        temperature: float = 0.0,
        **_unused: Any,
    ) -> _FakeMessage:
        user = messages[0]["content"] if messages else ""
        input_hash = _compute_input_hash(
            model=model, system=system, user=user, max_tokens=max_tokens
        )
        fixture = _load_fixture(input_hash)
        calls.append(
            {
                "model": model,
                "max_tokens": max_tokens,
                "system": system,
                "user": user,
                "temperature": temperature,
                "input_hash": input_hash,
            }
        )
        return _FakeMessage(
            content=[_FakeContentBlock(text=fixture["text"])],
            usage=_FakeUsage(
                input_tokens=fixture["input_tokens"],
                output_tokens=fixture["output_tokens"],
            ),
        )

    monkeypatch.setattr(
        anthropic.resources.messages.Messages, "create", fake_create
    )
    return calls
