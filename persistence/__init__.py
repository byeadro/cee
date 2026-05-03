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

Public surface (Phase 3):

- :func:`filesystem_write_text` / :func:`filesystem_write_json` —
  role-aware atomic writes per bible 02 §7 + bible 20 §5.3. The
  ``filesystem_*`` namespace is deliberate: callers should use these
  for any *role-authoritative* write, while ``atomic_*`` remains
  available as the lower-level primitive for cases where role
  enforcement is intentionally bypassed (e.g., audit-log appends,
  which carry their own actor field).
- :func:`write_artifact` — Obsidian per-artifact write plumbing per
  bible 13 §5 + §11. Resolves a ``(kind, id)`` pair to the canonical
  vault path and delegates to :func:`filesystem_write_text` with the
  role hard-coded to :attr:`RoleEnum.OBSIDIAN_WRITER`. Caller renders
  the Markdown body; per-kind renderer dispatch is Phase 5+ work
  (see ``persistence.obsidian_writer`` module docstring).
- :func:`queue` / :func:`drain` / :func:`mark_approved` /
  :func:`mark_rejected` / :func:`read_queue` — promotion queue
  lifecycle per bible 07 §11 line 411 + bible 00 §12 B8. T5 ships
  orchestration only; concrete Notion writes defer to a later commit
  when T6's ``NotionMCPClient`` Protocol gains write methods
  (downstream candidate #52). With the current T6 stub, :func:`drain`
  catches ``NotImplementedError`` from ``client.connect()`` and
  returns :class:`DrainResult` with ``transport_unavailable=True``
  per bible 00 §12 B8 "Failures stay queued".
- :class:`DrainResult` — read-only summary of a :func:`drain`
  invocation, mirroring :class:`boot.bible_sync.SyncResult` shape.

Phase 3 T4 renamed ``persistence/obsidian.py`` →
``persistence/obsidian_writer.py`` per bible 04 §5.1, bible 13 §11,
bible 18, and bible 20 §5.3 canonical naming. ``scaffold_obsidian``
is preserved verbatim under the new module path.
"""

from __future__ import annotations

from persistence.atomic import atomic_write_json, atomic_write_text
from persistence.audit import (
    audit_log_append,
    scaffold_audit_logs,
    verify_audit_chain,
)
from persistence.filesystem_writer import write_json as filesystem_write_json
from persistence.filesystem_writer import write_text as filesystem_write_text
from persistence.notion_writer import (
    DrainResult,
    drain,
    mark_approved,
    mark_rejected,
    queue,
    read_queue,
)
from persistence.obsidian_writer import scaffold_obsidian, write_artifact

__all__ = [
    "DrainResult",
    "atomic_write_json",
    "atomic_write_text",
    "audit_log_append",
    "drain",
    "filesystem_write_json",
    "filesystem_write_text",
    "mark_approved",
    "mark_rejected",
    "queue",
    "read_queue",
    "scaffold_audit_logs",
    "scaffold_obsidian",
    "verify_audit_chain",
    "write_artifact",
]
