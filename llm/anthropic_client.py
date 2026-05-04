"""Live Anthropic SDK wrapper for internal pipeline LLM calls.

Phase 4 T3 — Track B start. Authorized by:

* **Bible 03 §5.2 Step 2** — INTERPRETER calls Claude at temperature 0
  with a fixed system prompt at ``~/cee/prompts/interpreter_system.txt``.
* **Bible 08 §5.5** — CLASSIFIER falls back to a single Claude call
  (temperature 0, fixed prompt) when regex/lookup is inconclusive.
* **Bible 12 §5.8** — every role-action emits a hash-chained JSONL
  entry to ``~/cee/audit/roles.log`` via :func:`persistence.audit.audit_log_append`.
  The envelope is canonical; the per-event ``details`` shape for
  ``event="llm_call"`` is canonized in this module (downstream
  candidate #61 for bible-side canonicalization).
* **Bible 18 §5.6** — tests mock at the SDK boundary
  (``anthropic.Anthropic.messages.create``) via ``tests/conftest.py``;
  no parallel ``MockLLMClient`` lives in production code.

**Semantic distinction from bible 14 §5.6 ExecutorProtocol.** Bible 14
§5.6 names ``~/cee/executor/api_executor.py`` with ``ExecutorProtocol.send(final_prompt, target)``
for Phase 7's terminal EXECUTOR step. Phase 4 modules call Claude
*internally* per pipeline stage — distinct call site, distinct semantics.
Surfaced as candidate #60 for bible canonicalization.

**Production guard.** :func:`default_client_factory` requires
``CEE_LLM_LIVE=true`` env var. Production code that constructs a client
without explicit injection fails fast. Tests bypass via the
``conftest.py`` SDK monkeypatch fixture (bible 18 §5.6).

**Determinism contract.** Every call asserts ``temperature == 0.0``
(raises ``ValueError`` otherwise). Anthropic doesn't guarantee bit-equal
output across runs even at temperature 0, so this guarantees CEE's input
side stays deterministic; cross-run drift on the model side is captured
by the determinism test framework (T12, bible 18 §5.2) which runs N=10
and asserts identical output.
"""

from __future__ import annotations

import hashlib
import os
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Protocol

import paths
from persistence.audit import audit_log_append
from roles import RoleEnum
from schemas.config import Config
from schemas.credentials import Credentials


_LIVE_ENV_VAR: str = "CEE_LLM_LIVE"
_API_KEY_ENV_VAR: str = "ANTHROPIC_API_KEY"


@dataclass(frozen=True)
class LLMResponse:
    """The structured return of one :meth:`LLMClient.complete` call.

    All fields are populated by the live client; tests construct mock
    responses with the same shape via the conftest fixture.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    text: str
    model: str
    input_hash: str
    output_hash: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int


class LLMClient(Protocol):
    """Type contract for any module calling Claude via this layer.

    Phase 4 T5 (Interpreter) and T11 (Classifier) accept ``LLMClient``
    as a constructor parameter; production wiring uses
    :class:`LiveAnthropicClient`, tests use SDK-level monkeypatch via
    bible 18 §5.6's conftest fixture.
    """

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
        ...


def _compute_input_hash(
    *, model: str, system: str, user: str, max_tokens: int
) -> str:
    """Stable SHA-256 over the call's input contract.

    Used as the cache key for canned-response fixtures (bible 18 §5.6)
    and as the audit-log ``input_hash`` field. The components are
    delimiter-joined with newlines so component-boundary collisions
    require an actual newline in the system or user text — distinct
    inputs map to distinct hashes deterministically.
    """
    payload = (
        f"model={model}\n"
        f"max_tokens={max_tokens}\n"
        f"system={system}\n"
        f"user={user}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LiveAnthropicClient:
    """Concrete :class:`LLMClient` wrapping ``anthropic.Anthropic``.

    Per bible 03 §5.2 Step 2 + bible 08 §5.5: calls
    ``client.messages.create`` at temperature 0 with the caller-supplied
    system + user content. Computes input/output hashes, measures
    latency, emits ``event="llm_call"`` audit to roles.log.
    """

    def __init__(self, *, api_key: str, model: str) -> None:
        # Lazy import keeps the module importable in environments where
        # the SDK is absent (tests that patch the import path, dev
        # environments without the dep installed yet).
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key)
        self._model = model

    @property
    def model(self) -> str:
        return self._model

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
        if temperature != 0.0:
            raise ValueError(
                f"LiveAnthropicClient.complete requires temperature=0.0 "
                f"per bible 03 §5.2 Step 2 + bible 08 §5.5 (got "
                f"{temperature!r}); CEE's deterministic-module contract "
                f"forbids non-zero temperature for INTERPRETER + "
                f"CLASSIFIER calls."
            )

        input_hash = _compute_input_hash(
            model=self._model, system=system, user=user, max_tokens=max_tokens
        )

        t0 = time.monotonic()
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        t1 = time.monotonic()

        latency_ms = int((t1 - t0) * 1000)
        text = response.content[0].text
        output_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens

        details: dict[str, Any] = {
            "model": self._model,
            "mode": "live",
            "input_hash": input_hash,
            "output_hash": output_hash,
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        }
        audit_log_append(
            paths.AUDIT_ROLES_LOG,
            actor=role.value,
            event="llm_call",
            details=details,
            run_id=run_id,
        )

        return LLMResponse(
            text=text,
            model=self._model,
            input_hash=input_hash,
            output_hash=output_hash,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )


def _load_api_key() -> str:
    """Resolve the Anthropic API key per env-then-credentials.toml chain.

    Environment variable wins to support CI/cron/secret-manager flows;
    falls back to the OPERATOR's ``~/.cee/credentials.toml [anthropic]``
    section per bible 04 §5.2.
    """
    env_key = os.environ.get(_API_KEY_ENV_VAR)
    if env_key:
        return env_key

    if not paths.CREDENTIALS_FILE.exists():
        raise RuntimeError(
            f"Anthropic API key not available: env var {_API_KEY_ENV_VAR} "
            f"is unset and {paths.CREDENTIALS_FILE} does not exist. "
            f"Set the env var or seed the credentials file per bible "
            f"04 §5.2."
        )
    raw = paths.CREDENTIALS_FILE.read_text(encoding="utf-8")
    creds = Credentials.model_validate(tomllib.loads(raw))
    if creds.anthropic is None or not creds.anthropic.api_key:
        raise RuntimeError(
            f"Anthropic API key not available: {paths.CREDENTIALS_FILE} "
            f"has no [anthropic] section or its api_key is empty. Set "
            f"{_API_KEY_ENV_VAR} or populate the file per bible 04 §5.2."
        )
    return creds.anthropic.api_key


def _load_pinned_model() -> str:
    """Read the pinned model from ``~/.cee/config.toml [phase2] api_model``.

    Bible 04 §5.2 + bible 14 Rule 10: ``[phase2]`` block is the
    canonical home for model pinning; default in template is
    ``claude-opus-4-7``.
    """
    if not paths.CONFIG_FILE.exists():
        raise RuntimeError(
            f"Config file {paths.CONFIG_FILE} does not exist; cannot "
            f"resolve pinned model. Run `cee init` to seed the user "
            f"config."
        )
    raw = paths.CONFIG_FILE.read_text(encoding="utf-8")
    config = Config.model_validate(tomllib.loads(raw))
    return config.phase2.api_model


def default_client_factory() -> LLMClient:
    """Return a configured :class:`LiveAnthropicClient` for production use.

    Requires ``CEE_LLM_LIVE=true`` env var. Without it, raises
    :class:`RuntimeError` with explicit remediation. Tests must NOT use
    this factory; they monkeypatch ``anthropic.Anthropic.messages.create``
    via ``tests/conftest.py``'s ``mock_anthropic_sdk`` fixture per bible
    18 §5.6.
    """
    if os.environ.get(_LIVE_ENV_VAR, "").lower() != "true":
        raise RuntimeError(
            f"default_client_factory refuses to construct a live client "
            f"without explicit opt-in. Set {_LIVE_ENV_VAR}=true to "
            f"authorize live API calls (bills the configured Anthropic "
            f"account). Tests should use the bible-18-§5.6 conftest "
            f"monkeypatch fixture instead of this factory."
        )

    api_key = _load_api_key()
    model = _load_pinned_model()
    return LiveAnthropicClient(api_key=api_key, model=model)
