"""Boot orchestration — runs B1–B9 per bible 00 §12.

Authorized by System Design Bible section 00 §12 (Boot Sequence, the
canonical 9-step definition), section 02 §7.13 (``BOOT_SEQUENCER``
allowed_reads / allowed_writes), section 12 §5.8 (audit log shape),
section 19 §5.7 (``BootError`` hierarchy), section 20 §5.2 (Phase 2
gate — "Boot sequence completes B1–B9 from a clean state"), and
section 04 §5.6 (B2's auto-sync trigger semantics).

This module is the integration layer for everything Phase 2 has
shipped so far: it composes :func:`boot.consistency.check` (T5),
:func:`boot.bible_sync.sync` + :func:`boot.bible_sync.check_drift`
(T6), :func:`skill_engine.registry.rebuild` (T3), and
:func:`agent_selector.registry.rebuild` (T4) into a single
:func:`run` entry point that the future ``cee verify --boot`` (T9)
and ``cee run`` (Phase 4+) callers invoke.

**Public API.** One entry point :func:`run` that returns a typed
:class:`BootResult` — never propagates :class:`errors.BootError` to
the caller. Halt is reflected in :attr:`BootResult.ok` ``= False``,
:attr:`BootResult.halt_step`, and :attr:`BootResult.halt_error`. The
caller (T9 or the future pipeline driver) decides whether to re-raise
or translate to a non-zero exit code. Catastrophic non-CEE
exceptions (disk full mid audit-write, etc.) DO propagate, per
bible 19 §5.8 ("DRIVER_BUG — non-CEE; logged critical").

**Halt scope.** Per bible 00 §12 line 391, "If any step B1–B7 fails,
CEE halts." T8 reads this literally: B1–B7 halt on failure, B8 is
best-effort and never halts (entries stay queued, boot continues to
B9), B9 is success-only. Surfaces as a downstream candidate at
commit — the wording should be canonized.

**Step summary.**

* B1 — Verify environment. Python floor, required packages, write
  perms on canon roots, config validity. Halts on
  :class:`errors.BootEnvironmentError`.
* B2 — Load bible. Reads bible mirror; if drift detected against
  ``.sync_meta.json`` and ``auto_sync = true``, invokes
  :func:`boot.bible_sync.sync`; if ``auto_sync = false``, halts.
  Halts on :class:`errors.BootBibleSyncError`.
* B3 — Cross-section consistency check. Calls
  :func:`boot.consistency.check`. Halts on
  :class:`errors.BootConsistencyError`.
* B4 — Build Skill registry. Calls
  :func:`skill_engine.registry.rebuild`. Per-entry parse failures
  are logged and skipped (T3 spec); only catastrophic failure halts
  on :class:`errors.BootRegistryError`.
* B5 — Build agent registry. Same shape as B4 but for the agent
  catalog (T4 spec).
* B6 — Load schemas. Imports every module under ``schemas/``;
  Pydantic models compile at class definition. Halts on
  :class:`errors.BootSchemaError` if any module fails to import.
* B7 — Load recent Runs. Walks ``~/cee/runs/`` for Run-id
  directories (excludes ``golden/``). Phase 2 substrate has no Run
  logs; B7 returns an empty index gracefully. Halts on
  :class:`errors.BootRunIndexError` only if the runs dir is
  unreadable.
* B8 — Drain promotion queue. Phase 2 substrate has no
  ``promotion_queue.json``; B8 logs ``queue_not_found`` and
  continues. Best-effort — never halts boot. Pre-Phase-3 calls with
  a populated queue surface a structured warning ("writer pending").
* B9 — Ready. Emits ``boot_complete`` audit entry. Returns
  :class:`BootResult` with ``ok = True``.

**Audit emissions.** All to ``boot.log`` (actor ``BOOT_SEQUENCER``)
via :func:`persistence.audit.audit_log_append`. Lifecycle envelope
events (``boot_start``, ``boot_complete``, ``boot_halted``) wrap
per-step events (``boot_step_start``, ``boot_step_complete``,
``boot_step_failed``). B2's ``b2_drift_detected`` and the per-page
sync events are emitted by T6's :func:`boot.bible_sync.sync`
internally; T8 does not duplicate them. Event-name canonization
beyond ``b2_drift_detected`` (the only one named explicitly in
bible 04 §5.6) is INFERRED — surface as a downstream candidate at
commit time.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, NamedTuple

import paths
from errors import (
    BootBibleSyncError,
    BootConsistencyError,
    BootEnvironmentError,
    BootError,
    BootRegistryError,
    BootRunIndexError,
    BootSchemaError,
)
from persistence.audit import audit_log_append
from roles import RoleEnum

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Public types                                                                #
# --------------------------------------------------------------------------- #

BootStepName = Literal["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]

#: Steps whose failure halts the boot. Per bible 00 §12 line 391.
_HALT_STEPS: frozenset[str] = frozenset(
    {"B1", "B2", "B3", "B4", "B5", "B6", "B7"}
)


@dataclass(frozen=True)
class BootStepResult:
    """Per-step outcome record.

    ``payload`` is step-specific structured data. Key names are
    stable per-step — see each ``_run_b*`` helper docstring for the
    payload shape it produces. The dict passed in at construction is
    wrapped in :class:`types.MappingProxyType` by ``__post_init__``
    so callers cannot mutate it through the result.
    """

    step: BootStepName
    ok: bool
    duration_ms: int
    summary: str
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Frozen dataclasses still permit attribute setting from
        # ``__post_init__`` via ``object.__setattr__``. Wrap once at
        # construction so the ``Mapping`` annotation is enforced
        # in practice, not just in type-checker land.
        if not isinstance(self.payload, MappingProxyType):
            object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))


@dataclass(frozen=True)
class BootResult:
    """Terminal boot outcome.

    Returned by :func:`run` regardless of whether boot succeeded or
    halted. Never raises ``BootError`` to the caller — the typed
    exception is preserved on :attr:`halt_error` for caller-side
    pattern matching.

    ``ok`` is True only when all of B1–B7 succeeded AND B9 emitted
    ready. B8 outcome does NOT gate ``ok`` (best-effort per AB Q2 +
    bible 00 §12 line 391's "B1–B7" halt scope).

    On halt at step Bx, :attr:`steps` contains every step that ran
    up to and including Bx (Bx itself has ``ok = False``); steps
    after Bx are absent. :attr:`warnings` collects non-halting
    issues (B2 mirror-modified pages, B8 skip / pending-writer
    notes).
    """

    ok: bool
    steps: tuple[BootStepResult, ...]
    halt_step: BootStepName | None
    halt_error: BootError | None
    warnings: tuple[str, ...]
    total_duration_ms: int


# --------------------------------------------------------------------------- #
# Internal — BootContext                                                      #
# --------------------------------------------------------------------------- #


class BootContext(NamedTuple):
    """Cached cross-step state assembled in B1, consumed in later steps.

    Kept as a ``NamedTuple`` (immutable, no ``__post_init__`` quirks).
    Carries the resolved overrides + the parsed config so B2 doesn't
    re-load.
    """

    config_path: Path
    bible_root: Path
    sync_meta_path: Path
    skills_dir: Path
    agents_dir: Path
    schemas_dir: Path
    runs_dir: Path
    promotion_queue_path: Path
    auto_sync: bool


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #


def run(
    *,
    config_path: Path | None = None,
    bible_root: Path | None = None,
    sync_meta_path: Path | None = None,
    skills_dir: Path | None = None,
    agents_dir: Path | None = None,
    schemas_dir: Path | None = None,
    runs_dir: Path | None = None,
    promotion_queue_path: Path | None = None,
    bible_drift_factory: Callable[..., Any] | None = None,
    bible_sync_factory: Callable[..., Any] | None = None,
    skill_rebuild_factory: Callable[[Path], Any] | None = None,
    agent_rebuild_factory: Callable[[Path], Any] | None = None,
    consistency_factory: Callable[..., Any] | None = None,
    trigger: Literal["auto", "cli"] = "auto",
) -> BootResult:
    """Run B1–B9 per bible 00 §12. Returns a :class:`BootResult`.

    Production callers leave every kwarg as ``None`` to use the
    canonical paths from :mod:`paths` and the canonical implementations
    from :mod:`boot.consistency`, :mod:`boot.bible_sync`,
    :mod:`skill_engine.registry`, :mod:`agent_selector.registry`. The
    factory kwargs are test injection points (matches T5 / T6).

    ``trigger`` discriminates the boot.log invocation entry: ``"auto"``
    for boot-driven invocations (the default — by ``cee run``),
    ``"cli"`` when invoked from ``cee verify --boot`` (T9 surface).

    Returns
    -------
    BootResult
        Always returned. ``ok = True`` on full success (B9 reached);
        ``ok = False`` on halt at any of B1–B7. B8 failure never sets
        ``ok = False`` — see :class:`BootResult` for the rationale.

    Raises
    ------
    Exception
        Only catastrophic non-:class:`errors.CEEException` errors
        propagate (e.g., disk full mid audit-write). Per bible 19
        §5.8, those are DRIVER_BUG.
    """
    started_monotonic = time.monotonic()
    completed_steps: list[BootStepResult] = []
    warnings: list[str] = []

    _audit_emit_boot_start(
        trigger=trigger,
        config_path=config_path or paths.CONFIG_FILE,
        bible_root=bible_root or paths.BIBLE_DIR,
    )

    # B1 establishes the BootContext that downstream steps share.
    try:
        b1_result, ctx = _run_b1(
            config_path=config_path,
            bible_root=bible_root,
            sync_meta_path=sync_meta_path,
            skills_dir=skills_dir,
            agents_dir=agents_dir,
            schemas_dir=schemas_dir,
            runs_dir=runs_dir,
            promotion_queue_path=promotion_queue_path,
        )
    except BootError as exc:
        return _halt(
            completed_steps,
            warnings,
            failing=_failed_step("B1", exc, started_monotonic),
            halt_step="B1",
            exc=exc,
            total_started=started_monotonic,
        )
    completed_steps.append(b1_result)

    # B2–B7 each follow the same pattern: run helper, capture result,
    # accumulate warnings, halt on BootError.
    for step_name, helper in (
        ("B2", lambda: _run_b2(
            ctx,
            drift_factory=bible_drift_factory,
            sync_factory=bible_sync_factory,
        )),
        ("B3", lambda: _run_b3(ctx, factory=consistency_factory)),
        ("B4", lambda: _run_b4(ctx, factory=skill_rebuild_factory)),
        ("B5", lambda: _run_b5(ctx, factory=agent_rebuild_factory)),
        ("B6", lambda: _run_b6(ctx)),
        ("B7", lambda: _run_b7(ctx)),
    ):
        try:
            step_result, step_warnings = helper()
        except BootError as exc:
            return _halt(
                completed_steps,
                warnings,
                failing=_failed_step(step_name, exc, time.monotonic()),
                halt_step=step_name,  # type: ignore[arg-type]
                exc=exc,
                total_started=started_monotonic,
            )
        completed_steps.append(step_result)
        warnings.extend(step_warnings)

    # B8 — best-effort, never halts; warnings only.
    b8_result, b8_warnings = _run_b8(ctx)
    completed_steps.append(b8_result)
    warnings.extend(b8_warnings)

    # B9 — ready; emit boot_complete + return success.
    b9_result = _run_b9(started_monotonic, warnings)
    completed_steps.append(b9_result)

    total_duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    _audit_emit_boot_complete(
        total_duration_ms=total_duration_ms,
        warnings_count=len(warnings),
    )

    return BootResult(
        ok=True,
        steps=tuple(completed_steps),
        halt_step=None,
        halt_error=None,
        warnings=tuple(warnings),
        total_duration_ms=total_duration_ms,
    )


# --------------------------------------------------------------------------- #
# B1 — Verify environment                                                     #
# --------------------------------------------------------------------------- #


# Required first-party packages (modules T8 + downstream steps depend on).
# Independent of ``schemas`` (covered by B6) and the registry rebuilders
# (covered by B4 / B5). Kept tight — a longer list invites brittleness.
# ``tomllib`` is stdlib (Python 3.11+); production callers also depend on
# ``pydantic`` for schema validation.
_B1_REQUIRED_MODULES: tuple[str, ...] = (
    # Third-party
    "pydantic",
    "tomllib",
    # First-party (Phase 1 + early Phase 2 substrate)
    "paths",
    "errors",
    "roles",
    "persistence.audit",
    "persistence.atomic",
    "boot.consistency",
    "boot.bible_sync",
    "config_loader",
)

# Python floor. ``pyproject.toml`` declares ``requires-python = ">=3.10"``,
# but :mod:`tomllib` is stdlib only from 3.11+ and ``boot.bible_sync`` /
# ``config_loader`` already import it. The effective floor is therefore
# 3.11 — the value here matches the actual import-graph requirement, not
# the declared metadata. Surface as a downstream candidate
# (pyproject.toml requires-python alignment).
_B1_PYTHON_FLOOR: tuple[int, int] = (3, 11)


def _run_b1(
    *,
    config_path: Path | None,
    bible_root: Path | None,
    sync_meta_path: Path | None,
    skills_dir: Path | None,
    agents_dir: Path | None,
    schemas_dir: Path | None,
    runs_dir: Path | None,
    promotion_queue_path: Path | None,
) -> tuple[BootStepResult, BootContext]:
    """B1 — Verify environment + assemble :class:`BootContext`.

    Per bible 00 §12 line 374 (strict canon): "Check Python version,
    required packages, write permissions on ``~/cee/``,
    ``~/SecondBrain/cee/``. Halt on any failure." T8 reads
    ``~/.cee/config.toml`` here too so B2 can rely on a parsed
    config without re-loading; the parsed value flows through
    :class:`BootContext`.

    Strict canon per AB Q1: B1 does NOT touch credentials.toml.
    Credentials are read inside :func:`boot.bible_sync.sync` if and
    when sync is invoked.
    """
    import sys

    started = time.monotonic()
    _audit_emit_step_start("B1")

    # Probe 1 — Python version.
    if sys.version_info[:2] < _B1_PYTHON_FLOOR:
        actual = ".".join(str(x) for x in sys.version_info[:3])
        floor = ".".join(str(x) for x in _B1_PYTHON_FLOOR)
        raise BootEnvironmentError(
            kind="python_version",
            reason=f"Python {actual} < required {floor}",
            detail={"actual": actual, "required": floor},
        )

    # Probe 2 — required packages importable.
    missing: list[str] = []
    for mod_name in _B1_REQUIRED_MODULES:
        try:
            importlib.import_module(mod_name)
        except ImportError as exc:
            missing.append(f"{mod_name}: {exc}")
    if missing:
        raise BootEnvironmentError(
            kind="missing_package",
            reason=f"{len(missing)} required module(s) failed to import",
            detail={"missing": missing[:10]},
        )

    # Probe 3 — write perms on filesystem canon root + audit dir +
    # Obsidian vault root (per bible 02 §7.13's allowed_writes
    # surface for BOOT_SEQUENCER).
    writable_required = (
        paths.CEE_ROOT,
        paths.AUDIT_DIR,
        paths.OBSIDIAN_VAULT,
    )
    not_writable: list[str] = []
    for p in writable_required:
        if not _path_writable(p):
            not_writable.append(str(p))
    if not_writable:
        raise BootEnvironmentError(
            kind="path_not_writable",
            reason=f"{len(not_writable)} required path(s) missing or unwritable",
            detail={"paths": not_writable},
        )

    # Probe 4 — ~/.cee/config.toml exists, parses, validates.
    cfg_path = config_path if config_path is not None else paths.CONFIG_FILE
    if not cfg_path.exists():
        raise BootEnvironmentError(
            kind="config_invalid",
            reason=f"config file does not exist at {cfg_path}",
            detail={"config_path": str(cfg_path)},
        )
    try:
        from config_loader import load_config

        # ``load_config()`` reads ``paths.CONFIG_FILE`` directly. The
        # ``config_path`` kwarg on :func:`run` is honored only to the
        # extent that callers monkeypatch ``paths.CONFIG_FILE`` (the
        # convention T5 / T6 follow).
        config = load_config()
    except Exception as exc:
        raise BootEnvironmentError(
            kind="config_invalid",
            reason=f"config load/validate failed: {exc}",
            detail={
                "config_path": str(cfg_path),
                "exception_type": type(exc).__name__,
            },
        ) from exc

    # Probe 5 — audit dir is writable (probe 3 covered existence;
    # this verifies write access via a no-op scaffold call).
    # ``scaffold_audit_logs`` is idempotent — pre-existing files
    # untouched, missing files get touched. If it raises OSError
    # here, audit infra itself is broken and B1 should halt.
    try:
        from persistence.audit import scaffold_audit_logs

        scaffold_audit_logs()
    except OSError as exc:
        raise BootEnvironmentError(
            kind="path_not_writable",
            reason=f"audit log scaffold failed: {exc}",
            detail={"audit_dir": str(paths.AUDIT_DIR)},
        ) from exc

    # All probes passed — build the BootContext.
    ctx = BootContext(
        config_path=cfg_path,
        bible_root=bible_root if bible_root is not None else paths.BIBLE_DIR,
        sync_meta_path=(
            sync_meta_path if sync_meta_path is not None else paths.BIBLE_SYNC_META
        ),
        skills_dir=skills_dir if skills_dir is not None else paths.SKILLS_DIR,
        agents_dir=agents_dir if agents_dir is not None else paths.AGENTS_DIR,
        schemas_dir=schemas_dir if schemas_dir is not None else paths.SCHEMAS_DIR,
        runs_dir=runs_dir if runs_dir is not None else paths.RUNS_DIR,
        promotion_queue_path=(
            promotion_queue_path
            if promotion_queue_path is not None
            else paths.PROMOTION_QUEUE
        ),
        auto_sync=bool(config.general.auto_sync),
    )

    actual_py = ".".join(str(x) for x in sys.version_info[:3])
    payload = {
        "python_version": actual_py,
        "packages_ok": len(_B1_REQUIRED_MODULES),
        "writable_paths": [str(p) for p in writable_required],
        "auto_sync": ctx.auto_sync,
    }
    summary = (
        f"environment OK (Python {actual_py}, "
        f"{len(_B1_REQUIRED_MODULES)} packages, auto_sync={ctx.auto_sync})"
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    result = BootStepResult(
        step="B1", ok=True, duration_ms=duration_ms, summary=summary, payload=payload
    )
    _audit_emit_step_complete(result)
    return result, ctx


def _path_writable(p: Path) -> bool:
    """True if ``p`` exists, is a directory, and is writable.

    Treats nonexistent paths as not-writable. Boot expects every
    canonical root directory to exist by the time it runs.
    """
    import os

    return p.exists() and p.is_dir() and os.access(p, os.W_OK)


# --------------------------------------------------------------------------- #
# B2 — Load bible (drift check + conditional sync)                            #
# --------------------------------------------------------------------------- #


def _run_b2(
    ctx: BootContext,
    *,
    drift_factory: Callable[..., Any] | None,
    sync_factory: Callable[..., Any] | None,
) -> tuple[BootStepResult, list[str]]:
    """B2 — Load bible; auto-sync on drift if ``auto_sync = true``.

    Per bible 00 §12 line 376 + bible 04 §5.6: compare per-page
    ``notion_last_edited_time`` in ``.sync_meta.json`` against live
    Notion. On drift, run ``cee sync-bible`` automatically iff
    ``auto_sync = true``; otherwise halt with instruction.

    Three terminal outcomes:

    * No drift → continue to B3.
    * Drift + ``auto_sync = true`` → sync; per-page failures land in
      :attr:`SyncResult.failed` and become warnings (partial-with-
      warning per bible 04 §5.6); continue to B3.
    * Drift + ``auto_sync = false`` → halt with
      :class:`BootBibleSyncError` ``kind = "auto_sync_disabled"``.
    * Any halt-cause from :func:`boot.bible_sync.sync` /
      :func:`check_drift` (``credentials_missing``,
      ``mcp_connect_failed``, ``page_deleted``) → halt.

    ``mirror_modified`` pages from the drift report become warnings
    on success (deferred policy per bible 04 §5.6 "Mirror-side drift
    handling" — not a halt).
    """
    started = time.monotonic()
    _audit_emit_step_start("B2")

    from boot.bible_sync import check_drift as _check_drift_default
    from boot.bible_sync import sync as _sync_default

    check_drift_fn = drift_factory if drift_factory is not None else _check_drift_default
    sync_fn = sync_factory if sync_factory is not None else _sync_default

    drift_report = check_drift_fn(
        bible_root=ctx.bible_root,
        sync_meta_path=ctx.sync_meta_path,
    )

    warnings: list[str] = []
    if drift_report.mirror_modified:
        warnings.append(
            f"B2: {len(drift_report.mirror_modified)} mirror-modified page(s) "
            f"(deferred policy — not halting): {list(drift_report.mirror_modified)[:5]}"
        )

    if not drift_report.has_drift:
        payload = {
            "drift": "in_sync",
            "in_sync_count": len(drift_report.in_sync),
        }
        summary = f"bible in sync ({len(drift_report.in_sync)} pages)"
        duration_ms = int((time.monotonic() - started) * 1000)
        result = BootStepResult(
            step="B2", ok=True, duration_ms=duration_ms, summary=summary, payload=payload
        )
        _audit_emit_step_complete(result)
        return result, warnings

    # Drift exists. Branch on auto_sync.
    if not ctx.auto_sync:
        raise BootBibleSyncError(
            kind="auto_sync_disabled",
            reason=(
                "drift detected and auto_sync=false; "
                "run `cee sync-bible` manually before retrying boot"
            ),
            detail={
                "notion_newer": list(drift_report.notion_newer)[:10],
                "missing_from_meta": list(drift_report.missing_from_meta)[:10],
                "orphan": list(drift_report.orphan)[:10],
            },
        )

    # auto_sync = true — invoke sync(); BootBibleSyncError propagates.
    sync_result = sync_fn(
        trigger="boot_auto",
        bible_root=ctx.bible_root,
        sync_meta_path=ctx.sync_meta_path,
    )

    # Partial failures (some pages didn't sync) become warnings, not halts.
    if sync_result.failed:
        warnings.append(
            f"B2: {len(sync_result.failed)} page(s) failed to sync "
            f"(partial-with-warning per bible 04 §5.6): "
            f"{[f.page_slug if hasattr(f, 'page_slug') else str(f) for f in sync_result.failed][:5]}"
        )

    payload = {
        "drift": "synced",
        "synced_count": len(sync_result.synced),
        "failed_count": len(sync_result.failed),
        "duration_ms": sync_result.duration_ms,
    }
    summary = (
        f"bible synced ({len(sync_result.synced)} synced, "
        f"{len(sync_result.failed)} failed)"
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    result = BootStepResult(
        step="B2", ok=True, duration_ms=duration_ms, summary=summary, payload=payload
    )
    _audit_emit_step_complete(result)
    return result, warnings


# --------------------------------------------------------------------------- #
# B3 — Cross-section consistency check                                        #
# --------------------------------------------------------------------------- #


def _run_b3(
    ctx: BootContext,
    *,
    factory: Callable[..., Any] | None,
) -> tuple[BootStepResult, list[str]]:
    """B3 — Closed-enum cross-section consistency.

    Per bible 00 §12 line 378: "Validate that closed enums referenced
    across sections (e.g., ``task_type`` values referenced in 00, 03,
    08) match. Halt on any drift."

    Delegates to :func:`boot.consistency.check` (T5). On any drift,
    raises :class:`BootConsistencyError` carrying the structured
    ``DriftRecord`` list — caught by :func:`run` and surfaced as
    :attr:`BootResult.halt_error`.
    """
    started = time.monotonic()
    _audit_emit_step_start("B3")

    from boot.consistency import check as _check_default

    check_fn = factory if factory is not None else _check_default
    report = check_fn(bible_root=ctx.bible_root)

    if not report.ok:
        raise BootConsistencyError(drifts=list(report.drifts))

    payload = {"enums_checked": report.enums_checked, "drifts": 0}
    summary = f"consistency OK ({report.enums_checked} enums checked)"
    duration_ms = int((time.monotonic() - started) * 1000)
    result = BootStepResult(
        step="B3", ok=True, duration_ms=duration_ms, summary=summary, payload=payload
    )
    _audit_emit_step_complete(result)
    return result, []


# --------------------------------------------------------------------------- #
# B4 — Build Skill registry                                                   #
# --------------------------------------------------------------------------- #


def _run_b4(
    ctx: BootContext,
    *,
    factory: Callable[[Path], Any] | None,
) -> tuple[BootStepResult, list[str]]:
    """B4 — Rebuild the Skill registry.

    Per bible 00 §12 line 380: "Walk ``~/cee/skills/``, parse each
    ``SKILL.md`` frontmatter, build ``index.json``. Skills with
    invalid frontmatter are logged and skipped, not loaded." T3
    implements the "logged and skipped" semantics inside
    :func:`skill_engine.registry.rebuild`. T8 only halts on
    catastrophic failure (filesystem unreadable, atomic write to
    ``index.json`` fails).
    """
    started = time.monotonic()
    _audit_emit_step_start("B4")

    from skill_engine.registry import rebuild as _rebuild_default

    rebuild_fn = factory if factory is not None else _rebuild_default
    try:
        entries = rebuild_fn(ctx.skills_dir)
    except (OSError, PermissionError) as exc:
        raise BootRegistryError(
            kind="skill",
            reason=f"skill registry rebuild failed: {exc}",
            detail={
                "skills_dir": str(ctx.skills_dir),
                "exception_type": type(exc).__name__,
            },
        ) from exc

    indexed_count = len(entries) if entries is not None else 0
    payload = {"kind": "skill", "indexed_count": indexed_count}
    summary = f"skill registry rebuilt ({indexed_count} entries)"
    duration_ms = int((time.monotonic() - started) * 1000)
    result = BootStepResult(
        step="B4", ok=True, duration_ms=duration_ms, summary=summary, payload=payload
    )
    _audit_emit_step_complete(result)
    return result, []


# --------------------------------------------------------------------------- #
# B5 — Build agent registry                                                   #
# --------------------------------------------------------------------------- #


def _run_b5(
    ctx: BootContext,
    *,
    factory: Callable[[Path], Any] | None,
) -> tuple[BootStepResult, list[str]]:
    """B5 — Rebuild the agent registry.

    Per bible 00 §12 line 382: "Walk ``~/cee/.claude/agents/``, parse
    frontmatter, build ``index.json``." Same "logged and skipped"
    semantics as B4 per T4 spec.
    """
    started = time.monotonic()
    _audit_emit_step_start("B5")

    from agent_selector.registry import rebuild as _rebuild_default

    rebuild_fn = factory if factory is not None else _rebuild_default
    try:
        entries = rebuild_fn(ctx.agents_dir)
    except (OSError, PermissionError) as exc:
        raise BootRegistryError(
            kind="agent",
            reason=f"agent registry rebuild failed: {exc}",
            detail={
                "agents_dir": str(ctx.agents_dir),
                "exception_type": type(exc).__name__,
            },
        ) from exc

    indexed_count = len(entries) if entries is not None else 0
    payload = {"kind": "agent", "indexed_count": indexed_count}
    summary = f"agent registry rebuilt ({indexed_count} entries)"
    duration_ms = int((time.monotonic() - started) * 1000)
    result = BootStepResult(
        step="B5", ok=True, duration_ms=duration_ms, summary=summary, payload=payload
    )
    _audit_emit_step_complete(result)
    return result, []


# --------------------------------------------------------------------------- #
# B6 — Load schemas                                                           #
# --------------------------------------------------------------------------- #


def _run_b6(ctx: BootContext) -> tuple[BootStepResult, list[str]]:
    """B6 — Pre-compile all Pydantic models from ``~/cee/schemas/``.

    Per bible 00 §12 line 384. In Python this means importing every
    module under ``schemas/`` so its Pydantic classes go through
    validation-schema construction at class-definition time. A
    failed import (syntax error, missing dep, invalid Pydantic
    class) halts boot via :class:`BootSchemaError`.
    """
    started = time.monotonic()
    _audit_emit_step_start("B6")

    # Import the package itself first so pkgutil can enumerate.
    try:
        import schemas as _schemas_pkg
    except ImportError as exc:
        raise BootSchemaError(
            module_name="schemas",
            reason=f"schemas package import failed: {exc}",
            detail={"exception_type": type(exc).__name__},
        ) from exc

    compiled: list[str] = []
    for mod_info in pkgutil.iter_modules(_schemas_pkg.__path__):
        full_name = f"schemas.{mod_info.name}"
        try:
            importlib.import_module(full_name)
        except Exception as exc:
            raise BootSchemaError(
                module_name=mod_info.name,
                reason=f"import failed: {exc}",
                detail={"exception_type": type(exc).__name__},
            ) from exc
        compiled.append(mod_info.name)

    payload = {
        "schemas_compiled": len(compiled),
        "modules": tuple(sorted(compiled)),
    }
    summary = f"{len(compiled)} schema module(s) compiled"
    duration_ms = int((time.monotonic() - started) * 1000)
    result = BootStepResult(
        step="B6", ok=True, duration_ms=duration_ms, summary=summary, payload=payload
    )
    _audit_emit_step_complete(result)
    return result, []


# --------------------------------------------------------------------------- #
# B7 — Load recent Runs                                                       #
# --------------------------------------------------------------------------- #


# Run-id pattern accepted as a Run directory name. Phase 4+ writers
# canonize this; T8 picks a permissive pattern that matches any
# leading "run_" directory, excludes ``golden/``, and rejects
# anything else.
_B7_RUN_DIR_PATTERN: re.Pattern[str] = re.compile(r"^run_[A-Za-z0-9_\-]+$")
_B7_INDEX_LIMIT: int = 50


def _run_b7(ctx: BootContext) -> tuple[BootStepResult, list[str]]:
    """B7 — Index the last 50 Run logs by ``IntentObject.goal``.

    Per bible 00 §12 line 386. Phase 2 substrate has no Run logs —
    only ``runs/golden/`` (Phase 1 fixtures). B7 returns an empty
    index gracefully. Phase 4+ writers populate ``runs/<run_id>/``
    directories; B7 walks them and builds the index then.

    The downstream similarity-search infrastructure (Skill resolution,
    Phase 5+) consumes this index. T8 produces only the raw
    ``run_id → goal`` collection.
    """
    started = time.monotonic()
    _audit_emit_step_start("B7")

    runs_dir = ctx.runs_dir
    indexed: dict[str, str] = {}
    skipped: int = 0

    if not runs_dir.exists():
        # Missing runs dir is success — bible 04 §5.1 lists it as a
        # canonical filesystem entry; absence means "no Run logs yet"
        # rather than "boot environment broken" (B1's job to verify
        # ``~/cee/`` exists; ``runs/`` is a child that materializes
        # on first Run).
        payload = {"runs_indexed": 0, "runs_skipped": 0, "runs_dir_present": False}
        summary = "runs dir absent — empty index"
        duration_ms = int((time.monotonic() - started) * 1000)
        result = BootStepResult(
            step="B7",
            ok=True,
            duration_ms=duration_ms,
            summary=summary,
            payload=payload,
        )
        _audit_emit_step_complete(result)
        return result, []

    try:
        children = sorted(runs_dir.iterdir(), key=lambda p: p.name, reverse=True)
    except OSError as exc:
        raise BootRunIndexError(
            reason=f"cannot read runs dir: {exc}",
            detail={
                "runs_dir": str(runs_dir),
                "exception_type": type(exc).__name__,
            },
        ) from exc

    for child in children:
        if not child.is_dir():
            continue
        if child.name == "golden":
            continue
        if not _B7_RUN_DIR_PATTERN.match(child.name):
            continue
        if len(indexed) >= _B7_INDEX_LIMIT:
            break
        intent_path = child / "intent_object.json"
        if not intent_path.exists():
            skipped += 1
            continue
        try:
            import json as _json

            data = _json.loads(intent_path.read_text(encoding="utf-8"))
            goal = data.get("goal")
            if isinstance(goal, str) and goal:
                indexed[child.name] = goal
            else:
                skipped += 1
        except (OSError, ValueError):
            # Malformed Run-log JSON is a per-Run skip, not a B7
            # halt. The Run that wrote it is responsible for its
            # own integrity; B7 just reports.
            skipped += 1

    payload = {
        "runs_indexed": len(indexed),
        "runs_skipped": skipped,
        "runs_dir_present": True,
    }
    summary = f"{len(indexed)} Run(s) indexed ({skipped} skipped)"
    duration_ms = int((time.monotonic() - started) * 1000)
    result = BootStepResult(
        step="B7", ok=True, duration_ms=duration_ms, summary=summary, payload=payload
    )
    _audit_emit_step_complete(result)
    return result, []


# --------------------------------------------------------------------------- #
# B8 — Drain promotion queue (best-effort, never halts)                       #
# --------------------------------------------------------------------------- #


def _run_b8(ctx: BootContext) -> tuple[BootStepResult, list[str]]:
    """B8 — Drain the promotion queue if present.

    Per bible 00 §12 line 388: "If ``promotion_queue.json`` has
    entries and Notion is reachable, attempt promotion writes.
    Failures stay queued."

    AB Q2: B8 is best-effort and NEVER halts boot. Per bible 00 §12
    line 391's literal "B1–B7" halt scope — B8 failure surfaces as
    warning + payload only, B9 still runs.

    Phase 3 T5 ships ``persistence.notion_writer.drain`` per bible 07
    §11 line 411. Outcomes:

    * Queue file missing → ``payload = {"skipped": "queue_not_found"}``,
      no warning. Most common in Phase 2.
    * Queue file present + drain returns ``DrainResult`` → payload
      mirrors DrainResult fields; warning iff
      ``transport_unavailable`` or per-entry failures occurred.
    * Queue file present + drain raises (defensive safety net; T5
      contracts that ``drain`` never raises) → warning + payload
      ``skipped="drain_raised"``; ``ok=False`` on this step but boot
      continues to B9 per AB Q2.
    """
    started = time.monotonic()
    _audit_emit_step_start("B8")

    queue_path = ctx.promotion_queue_path

    if not queue_path.exists():
        payload = {"skipped": "queue_not_found", "queue_path": str(queue_path)}
        summary = "promotion queue absent — skipped"
        duration_ms = int((time.monotonic() - started) * 1000)
        result = BootStepResult(
            step="B8",
            ok=True,
            duration_ms=duration_ms,
            summary=summary,
            payload=payload,
        )
        _audit_emit_step_complete(result)
        return result, []

    # Queue file exists. Call T5's bible-grounded drain() per
    # bible 07 §11 line 411. T5 contracts that drain() never raises;
    # the try/except below is a defensive safety net.
    try:
        from persistence import drain

        drain_result = drain()
    except Exception as exc:  # noqa: BLE001 — best-effort per AB Q2
        warning = (
            f"B8: promotion drain raised unexpectedly "
            f"({type(exc).__name__}: {exc}); entries left queued"
        )
        _audit_emit_b8_warning(reason="drain_raised", queue_path=queue_path)
        payload = {
            "skipped": "drain_raised",
            "queue_path": str(queue_path),
            "error": f"{type(exc).__name__}: {exc}",
        }
        summary = f"promotion drain raised ({type(exc).__name__}) — entries queued"
        duration_ms = int((time.monotonic() - started) * 1000)
        result = BootStepResult(
            step="B8",
            ok=False,
            duration_ms=duration_ms,
            summary=summary,
            payload=payload,
        )
        _audit_emit_step_complete(result)
        return result, [warning]

    # Normal path — DrainResult returned. Payload mirrors DrainResult
    # fields; ``ok=True`` on this step regardless of transport state
    # per AB Q2 (B8 best-effort never sets step ok=False from drain
    # outcomes — only the defensive raise above does).
    payload = {
        "ok": drain_result.ok,
        "attempted": list(drain_result.attempted),
        "succeeded": list(drain_result.succeeded),
        "failed": [
            {"slug": slug, "error_type": err}
            for slug, err in drain_result.failed
        ],
        "skipped": list(drain_result.skipped),
        "transport_unavailable": drain_result.transport_unavailable,
        "queue_path": str(queue_path),
    }

    warnings_to_return: list[str] = []
    if drain_result.transport_unavailable:
        warning = (
            f"B8: notion transport unavailable; "
            f"{len(drain_result.attempted)} entries left queued"
        )
        _audit_emit_b8_warning(
            reason="transport_unavailable", queue_path=queue_path
        )
        warnings_to_return.append(warning)
    elif drain_result.failed:
        warning = (
            f"B8: promotion drain partial failure; "
            f"{len(drain_result.failed)} entries failed, "
            f"{len(drain_result.succeeded)} succeeded"
        )
        _audit_emit_b8_warning(
            reason="partial_failure", queue_path=queue_path
        )
        warnings_to_return.append(warning)

    summary = (
        f"promotion queue: {len(drain_result.succeeded)} drained, "
        f"{len(drain_result.failed)} failed, "
        f"{len(drain_result.skipped)} skipped"
    )
    duration_ms = int((time.monotonic() - started) * 1000)
    result = BootStepResult(
        step="B8",
        ok=True,
        duration_ms=duration_ms,
        summary=summary,
        payload=payload,
    )
    _audit_emit_step_complete(result)
    return result, warnings_to_return


# --------------------------------------------------------------------------- #
# B9 — Ready                                                                  #
# --------------------------------------------------------------------------- #


def _run_b9(started_monotonic: float, warnings: list[str]) -> BootStepResult:
    """B9 — Ready signal. Pure orchestration, never fails.

    Per bible 00 §12 line 389-390: "At this point the Run pipeline
    (§5 Step 1 onward) can begin. Boot is complete."
    """
    started = time.monotonic()
    _audit_emit_step_start("B9")
    total_ms = int((time.monotonic() - started_monotonic) * 1000)
    payload = {"ready": True, "total_duration_ms": total_ms}
    summary = f"boot ready ({total_ms} ms total, {len(warnings)} warning(s))"
    duration_ms = int((time.monotonic() - started) * 1000)
    result = BootStepResult(
        step="B9", ok=True, duration_ms=duration_ms, summary=summary, payload=payload
    )
    _audit_emit_step_complete(result)
    return result


# --------------------------------------------------------------------------- #
# Halt path                                                                   #
# --------------------------------------------------------------------------- #


def _failed_step(
    step: str, exc: BootError, started_monotonic: float
) -> BootStepResult:
    """Build a ``BootStepResult(ok=False)`` for a step that raised."""
    duration_ms = max(0, int((time.monotonic() - started_monotonic) * 1000))
    payload: dict[str, Any] = {
        "error_class": type(exc).__name__,
        "reason": exc.reason,
    }
    # Surface kind/module_name when present (typed BootError subclasses
    # carry one or the other).
    kind = getattr(exc, "kind", None)
    if kind is not None:
        payload["kind"] = kind
    module_name = getattr(exc, "module_name", None)
    if module_name is not None:
        payload["module_name"] = module_name
    return BootStepResult(
        step=step,  # type: ignore[arg-type]
        ok=False,
        duration_ms=duration_ms,
        summary=f"{step} halted: {exc.reason}",
        payload=payload,
    )


def _halt(
    completed_steps: list[BootStepResult],
    warnings: list[str],
    *,
    failing: BootStepResult,
    halt_step: BootStepName,
    exc: BootError,
    total_started: float,
) -> BootResult:
    """Assemble + return the halt :class:`BootResult`. Emits audit."""
    completed_steps.append(failing)
    total_duration_ms = int((time.monotonic() - total_started) * 1000)
    _audit_emit_step_failed(failing, exc)
    _audit_emit_boot_halted(halt_step=halt_step, exc=exc)
    return BootResult(
        ok=False,
        steps=tuple(completed_steps),
        halt_step=halt_step,
        halt_error=exc,
        warnings=tuple(warnings),
        total_duration_ms=total_duration_ms,
    )


# --------------------------------------------------------------------------- #
# Audit emitters — all to boot.log, actor BOOT_SEQUENCER                      #
# --------------------------------------------------------------------------- #
#
# Per bible 02 §7.13 BOOT_SEQUENCER's audit surface is boot.log + the
# per-page roles.log entries that T6 already emits. T8 introduces 7
# new event names; only ``b2_drift_detected`` was previously canonized
# in bible 04 §5.6. Surface as downstream candidate at commit time.


def _audit_emit_boot_start(
    *, trigger: Literal["auto", "cli"], config_path: Path, bible_root: Path
) -> None:
    audit_log_append(
        log_path=paths.AUDIT_BOOT_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="boot_start",
        details={
            "trigger": trigger,
            "config_path": str(config_path),
            "bible_root": str(bible_root),
        },
    )


def _audit_emit_step_start(step: BootStepName) -> None:
    audit_log_append(
        log_path=paths.AUDIT_BOOT_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="boot_step_start",
        details={"step": step},
    )


def _audit_emit_step_complete(result: BootStepResult) -> None:
    audit_log_append(
        log_path=paths.AUDIT_BOOT_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="boot_step_complete",
        details={
            "step": result.step,
            "duration_ms": result.duration_ms,
            "summary": result.summary,
            "payload_keys": sorted(result.payload.keys()),
        },
    )


def _audit_emit_step_failed(result: BootStepResult, exc: BootError) -> None:
    details: dict[str, Any] = {
        "step": result.step,
        "duration_ms": result.duration_ms,
        "error_class": type(exc).__name__,
        "reason": exc.reason,
    }
    kind = getattr(exc, "kind", None)
    if kind is not None:
        details["kind"] = kind
    audit_log_append(
        log_path=paths.AUDIT_BOOT_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="boot_step_failed",
        details=details,
    )


def _audit_emit_boot_complete(*, total_duration_ms: int, warnings_count: int) -> None:
    audit_log_append(
        log_path=paths.AUDIT_BOOT_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="boot_complete",
        details={
            "total_duration_ms": total_duration_ms,
            "warnings_count": warnings_count,
            "steps_run": 9,
        },
    )


def _audit_emit_boot_halted(*, halt_step: BootStepName, exc: BootError) -> None:
    details: dict[str, Any] = {
        "halt_step": halt_step,
        "halt_error_class": type(exc).__name__,
        "halt_reason": exc.reason,
    }
    kind = getattr(exc, "kind", None)
    if kind is not None:
        details["halt_kind"] = kind
    audit_log_append(
        log_path=paths.AUDIT_BOOT_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="boot_halted",
        details=details,
    )


def _audit_emit_b8_warning(*, reason: str, queue_path: Path) -> None:
    audit_log_append(
        log_path=paths.AUDIT_BOOT_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="b8_promotion_drain_warning",
        details={
            "reason": reason,
            "queue_path": str(queue_path),
        },
    )


__all__ = [
    "BootContext",
    "BootResult",
    "BootStepName",
    "BootStepResult",
    "run",
]
