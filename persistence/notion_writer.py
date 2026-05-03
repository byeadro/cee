"""Promotion queue lifecycle + Notion MCP write orchestration.

Implements the queue-mechanics half of NOTION_WRITER per bible 20
§5.3 line 176 ("``persistence/notion_writer.py`` -- promotion queue +
Notion MCP writes"). T5 ships orchestration only; concrete Notion
write operations defer to T6's :class:`boot.notion_mcp.NotionMCPClient`
Protocol whose stub raises ``NotImplementedError`` on every method.

**Module location drift surfaced as #51.** Bible 07 §11 line 411 names
the promotion API home as ``~/cee/skill_engine/promotion.py``; bible
20 §5.3 line 176 names ``~/cee/persistence/notion_writer.py``. T5
ships at the bible-20 location per Phase 3 plan + recency. The
public-API names (``queue``, ``drain``, ``mark_approved``,
``mark_rejected``) are bible 07 §11's canonical names verbatim.

**Lifecycle** (bible 07 §5.5 + bible 03 §5.5 + T2 ``PromotionStatus``):

* ``queued`` -- entry created at Run finalize time; no Notion page yet.
* ``pending_review`` -- candidate page written to Notion; awaiting
  OPERATOR move in Notion bible.
* ``approved`` -- OPERATOR moved candidate to Approved.
* ``rejected`` -- OPERATOR moved candidate to Rejected.

**B8 contract** (bible 00 Sec 12 line 387-388): "If
``promotion_queue.json`` has entries and Notion is reachable, attempt
promotion writes. Failures stay queued." :func:`drain` is best-effort:
it never raises on transport failure; failed entries persist with
``attempts++`` and ``last_error`` populated.

**Public API** (bible 07 Sec 11 line 411 names):

* :func:`queue` -- idempotent enqueue. Dedupes by ``(slug, kind)``
  with skip-silent semantics. Bible silent on dedupe; surfaced as #54.
* :func:`drain` -- best-effort flush per B8. Returns
  :class:`DrainResult` (never raises). With current T6 stub,
  :meth:`NotionMCPClient.connect` raises ``NotImplementedError`` and
  drain returns ``transport_unavailable=True`` after marking every
  queued entry with ``last_error="transport_not_implemented"``.
* :func:`mark_approved` -- transition ``pending_review -> approved``.
  Idempotent on already-approved.
* :func:`mark_rejected` -- transition ``pending_review -> rejected``;
  also allowed from ``queued`` (OPERATOR pre-reject). Idempotent on
  already-rejected.
* :func:`read_queue` -- load + validate queue file. Empty queue if
  file absent (bible 04 EC10 pattern -- absent config returns empty,
  not raise).

**Concrete-transport scaffold (#52).** The post-connect per-entry
write loop in :func:`drain` carries a ``# TODO #52`` marker for the
``client.create_promotion_page(...)`` call site. T6's
:class:`NotionMCPClient` Protocol has read-only methods; the write
methods land with concrete Notion MCP transport. Until then the loop
is dead code in production (connect() raises before reaching it) but
mock-testable via test fixtures.

**Notion-page-move detection (#53).** Bible 07 Sec 5.5 step 6 ("CEE
detects the move on next sync, updates ``promotion_queue.json``
accordingly") is a separate read pass over Notion that updates queue
status based on observed page locations. NOT in T5. Defer to a
future ``cee sync-promotions`` command or boot B8 extension.

**Queue size cap (#56).** Bible 01 Sec 10.8 says queue bounded at 500
with warning at 50+ entries. T5 emits :data:`_QUEUE_SIZE_WARN_THRESHOLD`
warn event at the 50 threshold but does NOT enforce the 500 cap; the
``cee promote --flush`` recovery command (Track C) is the enforcement
point.

**Audit emission** -- every lifecycle event lands in
``paths.AUDIT_ROLES_LOG`` under ``actor="NOTION_WRITER"``. Eight
event types per Step 3 taxonomy; see :func:`_emit` for the canonical
emission helper.

Bible references:

* **00 Sec 12 B8** -- boot drain contract.
* **01 Sec 10.8** -- queue size bounds.
* **03 Sec 5.5** -- promotion cycle.
* **04 Sec 7.2 / Sec 7.3** -- file location + write semantics.
* **04 Sec 10.6** -- recovery (rebuild by walking runs); out of T5 scope.
* **07 Sec 5.5 / Sec 11 line 411** -- canonical lifecycle + API names.
* **20 Sec 5.3 line 176** -- module location.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

import paths
from boot.notion_mcp import NotionMCPClient, default_client_factory
from persistence.audit import audit_log_append
from persistence.filesystem_writer import write_json as filesystem_write_json
from roles import RoleEnum
from schemas.promotion_queue import (
    PromotionKind,
    PromotionQueue,
    PromotionQueueEntry,
)


# bible 01 Sec 10.8: warning at 50+ entries; cap at 500 (not enforced
# by T5 -- defer to Track C cee promote --flush per #56).
_QUEUE_SIZE_WARN_THRESHOLD: int = 50


# --------------------------------------------------------------------------- #
# DrainResult -- frozen dataclass mirroring boot.bible_sync.SyncResult shape  #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DrainResult:
    """Best-effort drain outcome per bible 00 Sec 12 B8.

    Mirrors :class:`boot.bible_sync.SyncResult` shape -- read-only
    summary for the caller (boot B8 / ``cee promote --flush``). Never
    carries exceptions; transport failures surface as
    ``transport_unavailable=True`` and per-entry failures land in
    :attr:`failed`.
    """

    ok: bool
    attempted: tuple[str, ...]
    succeeded: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]
    skipped: tuple[str, ...]
    transport_unavailable: bool


# --------------------------------------------------------------------------- #
# Internal helpers                                                            #
# --------------------------------------------------------------------------- #


def _utc_now_iso() -> str:
    """Return current UTC time as an ISO 8601 string with Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _emit(event: str, details: dict, *, run_id: str | None = None) -> None:
    """Append an audit entry under ``actor=NOTION_WRITER`` to roles.log.

    Centralised so every lifecycle event uses identical (actor, log)
    tuple and so tests can patch one helper to capture emissions.
    """
    audit_log_append(
        paths.AUDIT_ROLES_LOG,
        actor=RoleEnum.NOTION_WRITER.value,
        event=event,
        details=details,
        run_id=run_id,
    )


def _persist_queue(queue: PromotionQueue) -> None:
    """Write the queue file via T3's role-aware writer.

    Per T3 ``_ALLOWED_WRITES``, NOTION_WRITER is authorised to write
    only :data:`paths.PROMOTION_QUEUE`; the role check is structural.
    """
    queue.last_updated = _utc_now_iso()
    filesystem_write_json(
        RoleEnum.NOTION_WRITER,
        paths.PROMOTION_QUEUE,
        queue.model_dump(mode="json"),
    )


def _find_entry(
    queue: PromotionQueue, slug: str, kind: PromotionKind
) -> PromotionQueueEntry | None:
    """Return the first entry matching ``(slug, kind)`` or None."""
    for entry in queue.entries:
        if entry.slug == slug and entry.kind == kind:
            return entry
    return None


# --------------------------------------------------------------------------- #
# Public API -- bible 07 Sec 11 line 411 names                                #
# --------------------------------------------------------------------------- #


def read_queue() -> PromotionQueue:
    """Load + validate the on-disk queue file.

    Returns an empty queue (no entries, ``last_updated`` set to
    current UTC time) if the file is absent. This matches the
    bible 04 EC10 pattern: absent state is not a halt; it is "the
    queue has nothing in it yet".

    Raises
    ------
    pydantic.ValidationError
        If the file exists but is malformed JSON or fails schema
        validation (bible 04 Sec 10.6 recovery is OPERATOR-driven).
    """
    if not paths.PROMOTION_QUEUE.exists():
        return PromotionQueue(last_updated=_utc_now_iso(), entries=[])
    return PromotionQueue.model_validate_json(
        paths.PROMOTION_QUEUE.read_text(encoding="utf-8")
    )


def queue(
    *,
    slug: str,
    kind: PromotionKind,
    payload_path: str,
    enqueued_by_run: str | None = None,
    enqueued_at: str | None = None,
) -> PromotionQueueEntry:
    """Idempotent enqueue. Dedupes by ``(slug, kind)`` with skip-silent.

    If an entry with the same ``(slug, kind)`` already exists,
    returns the existing entry unchanged and emits a
    ``notion_queue_enqueue_dedupe`` audit event. The original
    ``enqueued_at`` is preserved for forensic value.

    Parameters
    ----------
    slug
        The Skill / agent slug being queued.
    kind
        ``"skill"`` or ``"agent"`` (per :data:`PromotionKind`).
    payload_path
        Filesystem path to the artifact body to be promoted (e.g.
        ``~/cee/skills/<slug>/SKILL.md``).
    enqueued_by_run
        Optional Run ID that produced this candidate.
    enqueued_at
        Optional ISO 8601 timestamp; defaults to current UTC.

    Returns
    -------
    PromotionQueueEntry
        The new entry on first enqueue, or the existing entry on
        dedupe. In both cases the entry is the persisted form.
    """
    current = read_queue()
    existing = _find_entry(current, slug, kind)
    if existing is not None:
        _emit(
            "notion_queue_enqueue_dedupe",
            {"slug": slug, "kind": kind, "existing_status": existing.status},
            run_id=enqueued_by_run,
        )
        return existing

    new_entry = PromotionQueueEntry(
        slug=slug,
        kind=kind,
        status="queued",
        enqueued_at=enqueued_at or _utc_now_iso(),
        enqueued_by_run=enqueued_by_run,
        payload_path=payload_path,
    )
    current.entries.append(new_entry)
    _persist_queue(current)
    _emit(
        "notion_queue_enqueue",
        {
            "slug": slug,
            "kind": kind,
            "payload_path": payload_path,
            "enqueued_by_run": enqueued_by_run,
        },
        run_id=enqueued_by_run,
    )
    if len(current.entries) >= _QUEUE_SIZE_WARN_THRESHOLD:
        _emit(
            "notion_queue_size_warn",
            {"queue_size": len(current.entries)},
            run_id=enqueued_by_run,
        )
    return new_entry


def drain(
    *,
    client_factory: Callable[[], NotionMCPClient] | None = None,
) -> DrainResult:
    """Best-effort drain of queued entries per bible 00 Sec 12 B8.

    Iterates entries in ``status="queued"`` and attempts a Notion
    write for each. Per bible 00 B8: "Failures stay queued."

    Behaviour against the current T6 stub: ``client.connect()``
    raises :class:`NotImplementedError`; drain catches and marks
    every queued entry with ``last_error="transport_not_implemented"``,
    increments ``attempts``, and returns
    ``transport_unavailable=True``. No raise reaches the caller.

    Parameters
    ----------
    client_factory
        Test injection point for the Notion MCP transport. Production
        callers leave as ``None`` to use
        :func:`boot.notion_mcp.default_client_factory`.

    Returns
    -------
    DrainResult
        Best-effort summary; see field docs.
    """
    current = read_queue()
    queued_entries = [e for e in current.entries if e.status == "queued"]
    skipped = tuple(
        e.slug for e in current.entries if e.status != "queued"
    )

    _emit(
        "notion_queue_drain_start",
        {
            "queued_count": len(queued_entries),
            "skipped_count": len(skipped),
        },
    )

    if not queued_entries:
        _emit(
            "notion_queue_drain_end",
            {
                "ok": True,
                "succeeded_count": 0,
                "failed_count": 0,
                "transport_unavailable": False,
            },
        )
        return DrainResult(
            ok=True,
            attempted=(),
            succeeded=(),
            failed=(),
            skipped=skipped,
            transport_unavailable=False,
        )

    factory = client_factory or default_client_factory
    client = factory()

    try:
        client.connect()
    except NotImplementedError:
        # Stub path -- transport not yet implemented.
        for entry in queued_entries:
            entry.attempts += 1
            entry.last_error = "transport_not_implemented"
            _emit(
                "notion_queue_drain_entry_failed",
                {
                    "slug": entry.slug,
                    "kind": entry.kind,
                    "error_type": "transport_not_implemented",
                    "attempts": entry.attempts,
                },
                run_id=entry.enqueued_by_run,
            )
        _persist_queue(current)
        result = DrainResult(
            ok=False,
            attempted=tuple(e.slug for e in queued_entries),
            succeeded=(),
            failed=tuple(
                (e.slug, "transport_not_implemented") for e in queued_entries
            ),
            skipped=skipped,
            transport_unavailable=True,
        )
        _emit(
            "notion_queue_drain_end",
            {
                "ok": False,
                "succeeded_count": 0,
                "failed_count": len(queued_entries),
                "transport_unavailable": True,
            },
        )
        return result
    except Exception as exc:
        # Concrete-transport connect failure (post-Phase-3) takes the
        # same path as the stub but with a richer error_type.
        error_type = f"connect_failed:{type(exc).__name__}"
        for entry in queued_entries:
            entry.attempts += 1
            entry.last_error = error_type
            _emit(
                "notion_queue_drain_entry_failed",
                {
                    "slug": entry.slug,
                    "kind": entry.kind,
                    "error_type": error_type,
                    "attempts": entry.attempts,
                },
                run_id=entry.enqueued_by_run,
            )
        _persist_queue(current)
        result = DrainResult(
            ok=False,
            attempted=tuple(e.slug for e in queued_entries),
            succeeded=(),
            failed=tuple((e.slug, error_type) for e in queued_entries),
            skipped=skipped,
            transport_unavailable=True,
        )
        _emit(
            "notion_queue_drain_end",
            {
                "ok": False,
                "succeeded_count": 0,
                "failed_count": len(queued_entries),
                "transport_unavailable": True,
            },
        )
        return result

    # Post-connect per-entry write loop. Dead code under current T6
    # stub (connect raises) but mock-testable. Concrete transport
    # write methods land with #52.
    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []
    for entry in queued_entries:
        try:
            # TODO #52 / bible 04 Sec 7.3: client.create_promotion_page(
            #     slug=entry.slug, kind=entry.kind,
            #     payload_path=entry.payload_path,
            # ) -- write methods land with concrete Notion MCP transport.
            # For test injection: a mock client may attach a
            # `create_promotion_page` attribute; if present, call it.
            create_page = getattr(client, "create_promotion_page", None)
            if create_page is None:
                raise NotImplementedError(
                    "create_promotion_page not in NotionMCPClient Protocol "
                    "yet -- see candidate #52"
                )
            page_id = create_page(
                slug=entry.slug,
                kind=entry.kind,
                payload_path=entry.payload_path,
            )
            entry.status = "pending_review"
            entry.target_notion_page_id = page_id
            entry.last_error = None
            succeeded.append(entry.slug)
            _emit(
                "notion_queue_drain_entry_succeeded",
                {
                    "slug": entry.slug,
                    "kind": entry.kind,
                    "target_notion_page_id": page_id,
                },
                run_id=entry.enqueued_by_run,
            )
        except Exception as exc:
            entry.attempts += 1
            entry.last_error = repr(exc)
            failed.append((entry.slug, type(exc).__name__))
            _emit(
                "notion_queue_drain_entry_failed",
                {
                    "slug": entry.slug,
                    "kind": entry.kind,
                    "error_type": type(exc).__name__,
                    "attempts": entry.attempts,
                },
                run_id=entry.enqueued_by_run,
            )
    _persist_queue(current)
    result = DrainResult(
        ok=not failed,
        attempted=tuple(e.slug for e in queued_entries),
        succeeded=tuple(succeeded),
        failed=tuple(failed),
        skipped=skipped,
        transport_unavailable=False,
    )
    _emit(
        "notion_queue_drain_end",
        {
            "ok": not failed,
            "succeeded_count": len(succeeded),
            "failed_count": len(failed),
            "transport_unavailable": False,
        },
    )
    return result


def mark_approved(
    *, slug: str, kind: PromotionKind
) -> PromotionQueueEntry:
    """Transition ``pending_review -> approved`` per bible 07 Sec 5.5 step 6.

    Idempotent on already-approved entries (no-op + no audit event).

    Raises
    ------
    ValueError
        If the entry doesn't exist or is in ``queued`` / ``rejected``
        state. The lifecycle invariant is "approval requires that
        Notion has the candidate page" -- only ``pending_review``
        entries have a Notion page per drain semantics.
    """
    current = read_queue()
    entry = _find_entry(current, slug, kind)
    if entry is None:
        raise ValueError(
            f"no promotion queue entry for slug={slug!r} kind={kind!r}"
        )
    if entry.status == "approved":
        return entry  # idempotent; no audit event
    if entry.status != "pending_review":
        raise ValueError(
            f"cannot mark_approved from status={entry.status!r}; "
            f"only pending_review -> approved is allowed"
        )
    from_status = entry.status
    entry.status = "approved"
    entry.last_error = None
    _persist_queue(current)
    _emit(
        "notion_queue_transition",
        {
            "slug": slug,
            "kind": kind,
            "from_status": from_status,
            "to_status": "approved",
        },
        run_id=entry.enqueued_by_run,
    )
    return entry


def mark_rejected(
    *, slug: str, kind: PromotionKind
) -> PromotionQueueEntry:
    """Transition to ``rejected`` per bible 07 Sec 5.5 step 6.

    Allowed from ``pending_review`` (the canonical Notion-page-moved
    case) and from ``queued`` (OPERATOR pre-reject before drain ever
    runs). Idempotent on already-rejected.

    Raises
    ------
    ValueError
        If the entry doesn't exist or is in ``approved`` state. The
        lifecycle invariant is "rejection cannot undo approval".
    """
    current = read_queue()
    entry = _find_entry(current, slug, kind)
    if entry is None:
        raise ValueError(
            f"no promotion queue entry for slug={slug!r} kind={kind!r}"
        )
    if entry.status == "rejected":
        return entry  # idempotent; no audit event
    if entry.status not in ("queued", "pending_review"):
        raise ValueError(
            f"cannot mark_rejected from status={entry.status!r}; "
            f"only queued or pending_review allowed"
        )
    from_status = entry.status
    entry.status = "rejected"
    entry.last_error = None
    _persist_queue(current)
    _emit(
        "notion_queue_transition",
        {
            "slug": slug,
            "kind": kind,
            "from_status": from_status,
            "to_status": "rejected",
        },
        run_id=entry.enqueued_by_run,
    )
    return entry
