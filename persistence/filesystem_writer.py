"""Role-aware atomic filesystem writes.

The ``filesystem_writer`` is the role-enforcement layer above
``persistence.atomic``. Every write goes through one of two functions —
:func:`write_text` or :func:`write_json` — that take an explicit
``role: RoleEnum`` parameter, validate the role's authority over the
target path against the canonical bible 02 §7 allowed-writes map, and
then delegate to the underlying atomic helpers.

**Authority model** (bible 02 §7). The role-as-arg pattern matches
``persistence.audit.audit_log_append(log_path, actor, ...)``. Each
role's filesystem-write authority is a tuple of allowed roots; a write
is permitted iff the resolved target path equals one of the allowed
roots or is a descendant of one. Six roles have direct filesystem write
surfaces (per bible 02 §7.8, §7.9, §7.10, §7.11, §7.13, §7.13a):

* ``PERSISTENCE_WRITER`` — Run artifacts + new SKILL.md + agent files
* ``OBSIDIAN_WRITER`` — the ``~/SecondBrain/cee/`` mirror
* ``NOTION_WRITER`` — the on-disk promotion queue (Notion writes
  themselves go via MCP, not filesystem)
* ``BOOT_SEQUENCER`` — bible mirror, ``.sync_meta.json``, registry
  index files, boot.log
* ``PIPELINE_DRIVER`` — Run-lifecycle artifacts under
  ``~/cee/runs/<run_id>/``
* ``SAFETY_GATE`` — redacted FinalPrompt (per-Run) + security audit log

The 15 roles excluded from the map have no direct filesystem write
surface per bible 02 §7's wording: pipeline-step roles
(INTERPRETER/CLASSIFIER/AGENT_SELECTOR/SKILL_ENGINE/STRATEGY_BUILDER/
PROMPT_BUILDER) explicitly write "in-memory; persisted by
PERSISTENCE_WRITER"; OPERATOR writes happen via shell editor; EXECUTOR
is external; BIBLE_LOADER writes "in-memory bible state"; AUDITOR
writes go through ``persistence.audit.audit_log_append`` directly;
FILESYSTEM_CANON / FILESYSTEM_OS / NOTION_API / NOTION_BIBLE /
OBSIDIAN_VAULT are substrate-identity roles, not write actors.

**Violation handling.** A disallowed write raises
:class:`errors.RoleSurfaceViolation` (Phase 1's canonical exception
for "role accessed a path outside its allowed_reads/allowed_writes")
*and* emits a ``filesystem_write_denied`` entry to
``paths.AUDIT_ROLES_LOG`` per bible 12 §5.8 (audit-completeness for
rejected actions). Successful writes are NOT audited per route — the
artifact's own ``produced_by`` field is the canonical provenance, and
emitting per-write would explode roles.log size without forensic gain.

**Test-time path overrides.** ``_ALLOWED_WRITES`` is built at module
import time from the live ``paths.*`` constants. Tests that need to
exercise alternate path layouts can either (a) monkey-patch the map
directly via ``monkeypatch.setattr(filesystem_writer, '_ALLOWED_WRITES',
...)``, or (b) monkey-patch the underlying ``paths.*`` constants and
call :func:`_rebuild_allowed_writes` to refresh.

Bible references:

* **02 §7** — allowed-writes per role (the load-bearing source).
* **04 §5.1** — names this module at ``~/cee/persistence/filesystem_writer.py``.
* **04 §11** + **14** + **23** — every filesystem write must go through
  ``persistence.atomic``; this module enforces that.
* **12 §5.7** — Substrate-specific security passes. The canonical
  Detailed Workflow excludes filesystem_writer from substrate-redaction
  duty: only OBSIDIAN_WRITER and NOTION_WRITER re-run the redactor as
  defense-in-depth on derived substrates. Filesystem (canon) substrate's
  security pass is mode-bits + path-containment, NOT redaction. (T3
  originally placed a ``# TODO #32`` redactor-hook marker grounded in
  §11 line 470, but that line contradicts §5.7; closed Path A in
  post-T6 reconciliation. See build_status.md #32 + #42.)
* **12 §5.8** — rejected-write audit emission is mandatory.
* **20 §5.3** — Phase 3 output: "atomic writes, role-aware".
"""

from __future__ import annotations

from pathlib import Path

import paths
from errors import RoleSurfaceViolation
from persistence.atomic import atomic_write_json, atomic_write_text
from persistence.audit import audit_log_append
from roles import RoleEnum


def _rebuild_allowed_writes() -> dict[RoleEnum, tuple[Path, ...]]:
    """Build the allowed-writes map from current ``paths.*`` values.

    Called once at module import to populate ``_ALLOWED_WRITES``; tests
    can call again after monkey-patching ``paths.*`` to refresh. Each
    entry is grounded in the cited bible 02 §7.x bullet.
    """
    return {
        # bible 02 §7.9: Run artifacts + new SKILL.md + agent files
        RoleEnum.PERSISTENCE_WRITER: (
            paths.RUNS_DIR,
            paths.SKILLS_DIR,
            paths.AGENTS_DIR,
        ),
        # bible 02 §7.10: ~/SecondBrain/cee/runs/<run_id>.md, ~/SecondBrain/cee/skills/<slug>.md
        RoleEnum.OBSIDIAN_WRITER: (
            paths.OBSIDIAN_VAULT,
        ),
        # bible 02 §7.11: Notion writes via MCP; only the on-disk
        # promotion queue (bible 04 §7.2) lands on the local filesystem
        RoleEnum.NOTION_WRITER: (
            paths.PROMOTION_QUEUE,
        ),
        # bible 02 §7.13: rebuilt registries + boot log + bible mirror + .sync_meta.json
        RoleEnum.BOOT_SEQUENCER: (
            paths.BIBLE_DIR,
            paths.BIBLE_SYNC_META,
            paths.SKILLS_DIR / "index.json",
            paths.AGENTS_DIR / "index.json",
            paths.AUDIT_BOOT_LOG,
        ),
        # bible 02 §7.13a: ~/cee/runs/<run_id>/{run_summary,halt,run_error}.json,
        # pipeline.log, .lock
        RoleEnum.PIPELINE_DRIVER: (
            paths.RUNS_DIR,
        ),
        # bible 02 §7.8: redacted FinalPrompt (lives per-Run) + safety_log
        # (= security audit log per bible 12 §5.8)
        RoleEnum.SAFETY_GATE: (
            paths.RUNS_DIR,
            paths.AUDIT_SECURITY_LOG,
        ),
    }


_ALLOWED_WRITES: dict[RoleEnum, tuple[Path, ...]] = _rebuild_allowed_writes()


def _is_under(path: Path, root: Path) -> bool:
    """True iff ``path`` equals ``root`` or lives below it.

    Both inputs are expected to be already resolved to absolute paths
    (``Path.resolve()``). ``Path.is_relative_to`` (Python 3.9+) returns
    True for the equality case, so a single call suffices.
    """
    return path.is_relative_to(root)


def _emit_denial(role: RoleEnum, target: Path, run_id: str | None) -> None:
    """Append the ``filesystem_write_denied`` event to roles.log.

    Per bible 12 §5.8 the rejected attempt must be recorded before the
    raise. Failures in the audit emission itself propagate (we don't
    swallow them — a broken audit chain is a halt-worthy condition,
    not a silent best-effort).
    """
    audit_log_append(
        paths.AUDIT_ROLES_LOG,
        actor=role.value,
        event="filesystem_write_denied",
        details={
            "path": str(target),
            "reason": "outside_allowed_writes",
        },
        run_id=run_id,
    )


def _assert_role_can_write(
    role: RoleEnum, path: Path, *, run_id: str | None
) -> None:
    """Validate that ``role`` is authorised to write ``path``.

    On violation, emits the rejected-write audit event AND raises
    :class:`errors.RoleSurfaceViolation`. The audit emit happens before
    the raise so the forensic record is durable even if the caller's
    exception handler swallows the violation.
    """
    # filesystem_writer does NOT re-run the redactor per bible 12 §5.7
    # canonical Detailed Workflow. Redaction is SAFETY_GATE's responsibility
    # upstream; filesystem_writer writes already-redacted bytes. Re-running
    # the redactor here would corrupt audit-log hash chains, bible mirror
    # canonical content, and registry index.json files (false-positive
    # matches on hash digests, regex examples in bible 12 §5.2 itself, etc.).
    # See build_status.md candidate #32 (closed) and #42 for the bible
    # 12 §5.7-vs-§11-line-470 contradiction.
    resolved = path.resolve()
    allowed = _ALLOWED_WRITES.get(role)

    if allowed is None:
        _emit_denial(role, resolved, run_id)
        raise RoleSurfaceViolation(
            f"Role {role.value} has no filesystem write surface per "
            f"bible 02 §7; attempted write to {resolved}"
        )

    for root in allowed:
        if _is_under(resolved, root.resolve()):
            return

    _emit_denial(role, resolved, run_id)
    raise RoleSurfaceViolation(
        f"Role {role.value} not authorised to write {resolved}; "
        f"allowed roots per bible 02 §7: {[str(r) for r in allowed]}"
    )


def write_text(
    role: RoleEnum,
    path: Path,
    text: str,
    *,
    run_id: str | None = None,
    encoding: str = "utf-8",
    mode: int | None = None,
) -> None:
    """Atomically write ``text`` to ``path`` if ``role`` is authorised.

    Validates the role-path pair against the bible 02 §7 allowed-writes
    map, then delegates to :func:`persistence.atomic.atomic_write_text`.

    Raises
    ------
    RoleSurfaceViolation
        If ``role`` is not allowed to write ``path``. A
        ``filesystem_write_denied`` event is emitted to
        ``paths.AUDIT_ROLES_LOG`` before the raise.
    """
    _assert_role_can_write(role, path, run_id=run_id)
    atomic_write_text(path, text, encoding=encoding, mode=mode)


def write_json(
    role: RoleEnum,
    path: Path,
    data: object,
    *,
    run_id: str | None = None,
    indent: int = 2,
    sort_keys: bool = True,
    mode: int | None = None,
) -> None:
    """Atomically write ``data`` as JSON to ``path`` if ``role`` is authorised.

    Validates the role-path pair against the bible 02 §7 allowed-writes
    map, then delegates to :func:`persistence.atomic.atomic_write_json`.

    Raises
    ------
    RoleSurfaceViolation
        If ``role`` is not allowed to write ``path``. A
        ``filesystem_write_denied`` event is emitted to
        ``paths.AUDIT_ROLES_LOG`` before the raise.
    """
    _assert_role_can_write(role, path, run_id=run_id)
    atomic_write_json(path, data, indent=indent, sort_keys=sort_keys, mode=mode)
