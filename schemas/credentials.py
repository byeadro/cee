"""Credentials artifact schema.

Authorized by System Design Bible section 04 §5.2 (canonical schema)
and section 14 §6.2 + §9 EC12 (consumer + failure mode). Models the
``~/.cee/credentials.toml`` user-managed credentials file required when
``[phase2] api_enabled = true`` in ``~/.cee/config.toml``. Read by
``APIExecutor`` (per bible 14 §5.6) at construction time; missing
credentials trigger ``APIExecutor.__init__`` to raise a clear error
(bible 14 §9 EC12).

The ``[anthropic]`` section is the only section in scope per gap 8's
Path A reconciliation (commit ec4597b). Notion MCP authentication is
handled at the Claude Code / Anthropic platform layer (bible 21 §5.1
prerequisites), not via this file. Future services (e.g., Phase 4+)
that need their own credential sections will land them here in
additional Pydantic classes following the same Optional pattern.

Three design calls, all bible-grounded:

* The nested class is named ``AnthropicCredentials`` rather than
  ``Anthropic`` to avoid collision with ``anthropic.Anthropic`` (the
  SDK client class that Phase 2 task 6/7 will import). The TOML
  section name ``[anthropic]`` is preserved at the field level via
  the ``anthropic: AnthropicCredentials | None`` attribute.
* The top-level ``anthropic`` field is ``AnthropicCredentials | None``
  so Phase 1 — which ships an empty/commented-out ``credentials.toml``
  per bible 21 task 10 — can construct a valid ``Credentials`` from
  the empty file without errors. The required-when-Phase-2-enabled
  invariant is enforced at ``APIExecutor`` construction (bible 14 §9
  EC12), not by the schema.
* ``schema_version`` is carried as both a ``ClassVar`` and an
  instance field, matching the Phase 2 convention established by
  ``SyncMeta`` (commit 65327aa). Persistent user-config files
  benefit from on-disk version tags for migration routing per bible
  04 §6.1.
"""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field


class AnthropicCredentials(BaseModel):
    """The ``[anthropic]`` section of ``credentials.toml``.

    Per bible 04 §5.2 + bible 14 §6.2, the only field is ``api_key``
    — the Anthropic API key consumed by ``APIExecutor`` when
    ``[phase2] api_enabled = true``. Anthropic API keys begin with
    ``sk-ant-`` per Anthropic's published key format; the pattern
    enforces this prefix to catch obviously-wrong values (e.g.,
    placeholder strings, keys from other providers).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    api_key: Annotated[str, Field(min_length=1, pattern=r"^sk-ant-")]


class Credentials(BaseModel):
    """User-managed credentials at ``~/.cee/credentials.toml``.

    Per bible 04 §5.2: ``chmod 600``, user-managed, CEE never
    auto-writes. Contains the ``[anthropic]`` section (Phase 2);
    future sections may be added by future bible reconciliations as
    additional Optional fields.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    schema_version: str = "1.0.0"
    anthropic: AnthropicCredentials | None = None
