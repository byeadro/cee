"""CEE persistence layer — atomic filesystem writers and vault scaffolding.

The persistence package owns every sanctioned write path in CEE. Per
bible 14 §"Build Notes for Claude Code", raw ``open()`` for writes is
forbidden; callers go through the helpers re-exported here.

Public surface (Phase 1):

- :func:`atomic_write_text` / :func:`atomic_write_json` — atomic file
  writes with fsync + ``os.replace``. Bible 04 §11.
- :func:`scaffold_obsidian` — creates the ``~/SecondBrain/cee/`` vault
  layout per bible 13 §5.1. Layout-only; renderers ship in Phase 5+.
- :func:`scaffold_audit_logs` / :func:`audit_log_append` /
  :func:`verify_audit_chain` — hash-chained audit log infrastructure
  per bible 12 §5.8 + §10.6. Phase 1 ships the primitives; per-event
  writers are Phase 5+.
"""

from __future__ import annotations

from persistence.atomic import atomic_write_json, atomic_write_text
from persistence.audit import (
    audit_log_append,
    scaffold_audit_logs,
    verify_audit_chain,
)
from persistence.obsidian import scaffold_obsidian

__all__ = [
    "atomic_write_json",
    "atomic_write_text",
    "audit_log_append",
    "scaffold_audit_logs",
    "scaffold_obsidian",
    "verify_audit_chain",
]
