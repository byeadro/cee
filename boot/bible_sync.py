"""``cee sync-bible`` — Notion-to-filesystem bible sync orchestration.

Authorized by System Design Bible section 04 §5.6 (the operational
spec, committed 8963612), section 04 §5.5 (``.sync_meta.json``
schema), section 04 §5.2 (``credentials.toml``), section 02 §7.13
(``BOOT_SEQUENCER``'s allowed_writes surface), section 12 §5.8
(audit log shape), section 00 §11 (CLI surface), section 00 §12 B2
(boot-time auto-sync trigger), section 20 §5.2 (Phase 2 scope).

This module is the orchestration layer. The transport layer lives at
:mod:`boot.notion_mcp` (Protocol + stub). T6 ships this module + the
Protocol with a stub default; the concrete ``messages.create(...)``
glue lands in a later focused commit per AB lock at Step 2 review.

Two public entry points:

* :func:`sync` — performs the full Notion-to-filesystem sync. Called
  by ``BOOT_SEQUENCER`` at boot step B2 (when ``auto_sync = true``
  and drift detected) or by the operator via ``cee sync-bible``
  (CLI). Both triggers converge on this function; only the
  ``trigger`` argument differs (and which audit log gets the
  invocation entry).
* :func:`check_drift` — read-only drift detection between live Notion
  and the local mirror. Used by ``cee verify --bible`` (T10) and by
  boot step B2 itself before deciding whether to call :func:`sync`.

**Failure handling.** Per bible 04 §5.6:

* Initial MCP connect failure → halt before any page is touched
  (raises :class:`errors.BootBibleSyncError` with
  ``kind="mcp_connect_failed"``).
* Per-page failure → log to ``roles.log``, mark page failed in the
  result, continue the loop (partial-with-warning).
* EC9 (page deleted in Notion) → halt with restore instruction
  (``kind="page_deleted"``).
* Missing credentials → halt before connect attempt
  (``kind="credentials_missing"``; INFERRED — see
  :class:`errors.BootBibleSyncError` docstring + downstream
  candidate #13).

**Substrate boundary.** Writes go only to ``~/cee/bible/*.md`` and
``~/cee/bible/.sync_meta.json`` per bible 02 §7.13's
``BOOT_SEQUENCER`` allowed_writes. Does not touch ``~/SecondBrain/``
— Obsidian's bible mirror is rebuilt downstream by ``OBSIDIAN_WRITER``
on next Run (per bible 04 §10.10).

**heading_4 caveat.** Notion has no ``heading_4`` block type. The
current local bibles contain ``#### ...`` markdown from Phase 1's
manual transcription (12 bibles affected as of T6). On first sync
after the concrete transport ships, those H4 headings will surface
as :attr:`DriftReport.mirror_modified` because Notion's emitted
markdown will not contain them. This is bible 04 §5.6's deferred
"Mirror-side drift handling" item (UX policy: halt-and-ask vs.
force-overwrite). Out of T6 scope — T6 reports the drift, the
deferred policy decides how to act on it.

**Deferred to Phase 2 close** (per bible 04 §5.6 verbatim):

* Notion-block-to-markdown normalization rules — T6 ships a stub
  covering only the block types observed in current bibles
  (:func:`_blocks_to_markdown` documents the supported set + the
  exclusions). Future block types extend the stub when they surface.
* Mirror-side drift UX (halt-and-ask vs. force-overwrite).
* Retry policy with exponential backoff for transient Notion MCP
  errors. T6 surfaces transient errors as per-page failures; no
  retry attempted.
* Rate-limit handling for the Notion API.
"""

from __future__ import annotations

import hashlib
import logging
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import paths
from boot.notion_mcp import (
    Block,
    ChildRef,
    NotionMCPClient,
    PageMeta,
    RichTextSpan,
    default_client_factory,
)
from config_loader import load_config
from errors import BootBibleSyncError
from persistence.atomic import atomic_write_json, atomic_write_text
from persistence.audit import audit_log_append
from roles import RoleEnum
from schemas import Credentials, PageEntry, SyncMeta

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Result / report types                                                       #
# --------------------------------------------------------------------------- #


SyncTrigger = Literal["boot_auto", "cli_manual"]


@dataclass(frozen=True)
class SyncResult:
    """The outcome of a :func:`sync` invocation.

    Per bible 04 §5.6: the CLI exits with non-zero status when
    :attr:`failed` is non-empty (partial-with-warning). The boot
    sequencer (T8) inspects this report to decide whether to proceed
    to step B3 or halt.
    """

    ok: bool  # True iff failed is empty AND no halt occurred
    trigger: SyncTrigger
    synced: tuple[str, ...]  # page slugs successfully written
    skipped: tuple[str, ...]  # page slugs already in sync (no fetch)
    failed: tuple[tuple[str, str], ...]  # (page_slug, error_type) pairs
    duration_ms: int


@dataclass(frozen=True)
class DriftReport:
    """Read-only drift categorization between live Notion + local mirror.

    Used by :func:`check_drift` for ``cee verify --bible`` (T10) and
    by ``BOOT_SEQUENCER`` step B2 to decide whether to invoke
    :func:`sync`.
    """

    in_sync: tuple[str, ...]  # slug + sha256 + notion_last_edited match
    notion_newer: tuple[str, ...]  # Notion last_edited_time > meta entry
    mirror_modified: tuple[str, ...]  # local sha256 != meta sha256
    orphan: tuple[str, ...]  # local *.md exists, no meta entry
    missing_from_meta: tuple[str, ...]  # Notion has it, meta does not

    @property
    def has_drift(self) -> bool:
        return bool(
            self.notion_newer
            or self.mirror_modified
            or self.orphan
            or self.missing_from_meta
        )


# --------------------------------------------------------------------------- #
# sync()                                                                      #
# --------------------------------------------------------------------------- #


def sync(
    *,
    trigger: SyncTrigger,
    bible_root: Path | None = None,
    sync_meta_path: Path | None = None,
    client_factory: Callable[[], NotionMCPClient] | None = None,
) -> SyncResult:
    """Run the full Notion-to-filesystem bible sync.

    Per bible 04 §5.6 step ordering:

    1. Read ``[anthropic] api_key`` from ``credentials.toml`` (halt
       on missing — kind ``credentials_missing``).
    2. Connect to Notion MCP via the injected client. Halt before any
       page fetch on connect failure (kind ``mcp_connect_failed``).
    3. Fetch the parent page + enumerate its children. Halt on EC9
       (parent deleted, kind ``page_deleted``).
    4. Capture ``last_synced`` once at sync start (bible 03 Rule 6).
    5. For each child: fetch metadata; compare to ``.sync_meta.json``;
       skip if unchanged, otherwise fetch blocks + normalize +
       atomic-write the mirror file + update in-memory meta.
    6. After all pages processed, atomically write the updated
       ``.sync_meta.json``.
    7. Append audit summary entries.

    Parameters
    ----------
    trigger
        Which invocation surface called this function. Determines
        which auxiliary audit log gets the start entry (``cli.log``
        for ``cli_manual``, ``boot.log`` for ``boot_auto``); the
        ``roles.log`` entries are emitted under both triggers.
    bible_root, sync_meta_path
        Test injection points. Production callers leave both as
        ``None`` to use the canonical paths from :mod:`paths`.
    client_factory
        Test injection point for the Notion MCP transport. Production
        callers leave as ``None``; the default factory returns a
        :class:`boot.notion_mcp._StubMCPClient` that raises
        ``NotImplementedError`` on real calls (concrete transport
        lands in a later commit).

    Returns
    -------
    SyncResult
        See :class:`SyncResult` field docs.

    Raises
    ------
    errors.BootBibleSyncError
        On the three halt causes: ``credentials_missing``,
        ``mcp_connect_failed``, ``page_deleted``. Per-page transient
        failures do NOT raise — they go into
        :attr:`SyncResult.failed`.
    """
    bible_dir = bible_root if bible_root is not None else paths.BIBLE_DIR
    meta_path = (
        sync_meta_path if sync_meta_path is not None else paths.BIBLE_SYNC_META
    )
    factory = client_factory if client_factory is not None else default_client_factory

    started_monotonic = time.monotonic()

    # Step 0 — emit trigger-specific audit invocation entry.
    if trigger == "cli_manual":
        _audit_emit_cli_invoke()
    else:
        _audit_emit_b2_drift_detected()

    # Step 1 — credentials + config.
    credentials = _load_credentials()
    if credentials.anthropic is None:
        _emit_terminal_audit(trigger, started_monotonic, synced=(), failed=())
        raise BootBibleSyncError(
            kind="credentials_missing",
            reason=(
                "credentials.toml has no [anthropic] section or api_key; "
                "sync-bible requires it per bible 04 §5.2 + §5.6 step 1"
            ),
            detail={"credentials_path": str(paths.CREDENTIALS_FILE)},
        )

    config = load_config()
    parent_page_id = config.paths.notion_bible_root_id

    # Step 2 — connect (halts before page touch on failure).
    client = factory()
    try:
        client.connect()
    except Exception as exc:
        _emit_terminal_audit(trigger, started_monotonic, synced=(), failed=())
        raise BootBibleSyncError(
            kind="mcp_connect_failed",
            reason=str(exc),
            detail={"exception_type": type(exc).__name__},
        ) from exc

    # Step 3 — fetch parent + enumerate children.
    try:
        children = client.enumerate_children(parent_page_id)
    except Exception as exc:
        _emit_terminal_audit(trigger, started_monotonic, synced=(), failed=())
        raise BootBibleSyncError(
            kind="mcp_connect_failed",
            reason=f"failed to enumerate parent {parent_page_id}: {exc}",
            detail={
                "parent_page_id": parent_page_id,
                "exception_type": type(exc).__name__,
            },
        ) from exc

    if not children:
        _emit_terminal_audit(trigger, started_monotonic, synced=(), failed=())
        raise BootBibleSyncError(
            kind="page_deleted",
            reason=(
                f"parent page {parent_page_id} returned zero children; "
                "EC9 (Notion bible page deleted) — restore the parent "
                "page or its children before retrying"
            ),
            detail={"parent_page_id": parent_page_id},
        )

    # Step 4 — capture last_synced once (bible 03 Rule 6).
    last_synced = _utc_now_iso()

    # Step 5 — load existing sync_meta to compare per-page state.
    existing_meta = _load_sync_meta(meta_path)
    existing_pages = dict(existing_meta.pages) if existing_meta else {}

    _audit_emit_sync_start(trigger=trigger, page_count_expected=len(children))

    new_pages: dict[str, PageEntry] = {}
    synced: list[str] = []
    skipped: list[str] = []
    failed: list[tuple[str, str]] = []

    for child in children:
        slug = _slug_for_child(child)
        if not slug:
            failed.append((child.title or child.page_id, "invalid_slug"))
            _audit_emit_page_failed(slug or child.page_id, "invalid_slug")
            continue

        try:
            page_meta = client.fetch_page_metadata(child.page_id)
        except Exception as exc:
            error_type = type(exc).__name__
            failed.append((slug, error_type))
            _audit_emit_page_failed(slug, error_type)
            # Preserve the prior meta entry if present so we don't lose
            # state for a page that just had a transient fetch failure.
            if slug in existing_pages:
                new_pages[slug] = existing_pages[slug]
            continue

        prior = existing_pages.get(slug)
        if prior is not None and prior.notion_last_edited_time == page_meta.last_edited_time:
            skipped.append(slug)
            new_pages[slug] = prior
            continue

        try:
            blocks = client.fetch_page_blocks(child.page_id)
        except Exception as exc:
            error_type = type(exc).__name__
            failed.append((slug, error_type))
            _audit_emit_page_failed(slug, error_type)
            if prior is not None:
                new_pages[slug] = prior
            continue

        markdown = _blocks_to_markdown(blocks)
        local_path = bible_dir / f"{slug}.md"

        try:
            atomic_write_text(local_path, markdown)
        except OSError as exc:
            error_type = type(exc).__name__
            failed.append((slug, error_type))
            _audit_emit_page_failed(slug, error_type)
            if prior is not None:
                new_pages[slug] = prior
            continue

        sha = _sha256_text(markdown)
        new_pages[slug] = PageEntry(
            notion_page_id=page_meta.page_id,
            notion_last_edited_time=page_meta.last_edited_time,
            local_path=str(local_path),
            content_sha256=sha,
        )
        synced.append(slug)
        _audit_emit_page_synced(slug, page_meta.last_edited_time, sha)

    # Step 6 — write updated .sync_meta.json atomically.
    new_meta = SyncMeta(
        last_synced=last_synced,
        pages=new_pages,
    )
    atomic_write_json(meta_path, new_meta.model_dump(mode="json"))

    # Step 7 — terminal audit.
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    _audit_emit_sync_end(
        trigger=trigger,
        synced_count=len(synced),
        failed_count=len(failed),
        duration_ms=duration_ms,
    )

    return SyncResult(
        ok=not failed,
        trigger=trigger,
        synced=tuple(synced),
        skipped=tuple(skipped),
        failed=tuple(failed),
        duration_ms=duration_ms,
    )


# --------------------------------------------------------------------------- #
# check_drift()                                                               #
# --------------------------------------------------------------------------- #


def check_drift(
    *,
    bible_root: Path | None = None,
    sync_meta_path: Path | None = None,
    client_factory: Callable[[], NotionMCPClient] | None = None,
) -> DriftReport:
    """Read-only drift check between live Notion and the local mirror.

    Three substrates compared:

    * :attr:`DriftReport.notion_newer` — Notion's
      ``last_edited_time`` > the meta entry's recorded value.
    * :attr:`DriftReport.mirror_modified` — local mirror's sha256
      differs from the meta entry's recorded ``content_sha256``
      (manual edit since last sync).
    * :attr:`DriftReport.orphan` — local file exists but no meta
      entry covers it.
    * :attr:`DriftReport.missing_from_meta` — Notion has the page
      but ``.sync_meta.json`` does not.

    Like :func:`sync`, the transport layer is injected via
    ``client_factory``; the default raises
    ``NotImplementedError`` until concrete transport ships. Tests
    inject a mock client returning synthetic
    :class:`boot.notion_mcp.PageMeta` / :class:`ChildRef` instances.

    Raises
    ------
    errors.BootBibleSyncError
        On the same halt causes as :func:`sync`. Drift detection
        cannot proceed without transport reachability.
    """
    bible_dir = bible_root if bible_root is not None else paths.BIBLE_DIR
    meta_path = (
        sync_meta_path if sync_meta_path is not None else paths.BIBLE_SYNC_META
    )
    factory = client_factory if client_factory is not None else default_client_factory

    credentials = _load_credentials()
    if credentials.anthropic is None:
        raise BootBibleSyncError(
            kind="credentials_missing",
            reason=(
                "credentials.toml has no [anthropic] section or api_key; "
                "drift check requires it per bible 04 §5.2"
            ),
            detail={"credentials_path": str(paths.CREDENTIALS_FILE)},
        )

    config = load_config()
    parent_page_id = config.paths.notion_bible_root_id

    client = factory()
    try:
        client.connect()
    except Exception as exc:
        raise BootBibleSyncError(
            kind="mcp_connect_failed",
            reason=str(exc),
            detail={"exception_type": type(exc).__name__},
        ) from exc

    try:
        children = client.enumerate_children(parent_page_id)
    except Exception as exc:
        raise BootBibleSyncError(
            kind="mcp_connect_failed",
            reason=f"failed to enumerate parent {parent_page_id}: {exc}",
            detail={"parent_page_id": parent_page_id},
        ) from exc

    if not children:
        raise BootBibleSyncError(
            kind="page_deleted",
            reason=f"parent page {parent_page_id} returned zero children",
            detail={"parent_page_id": parent_page_id},
        )

    existing_meta = _load_sync_meta(meta_path)
    existing_pages = dict(existing_meta.pages) if existing_meta else {}

    in_sync: list[str] = []
    notion_newer: list[str] = []
    mirror_modified: list[str] = []
    missing_from_meta: list[str] = []

    notion_slugs: set[str] = set()
    for child in children:
        slug = _slug_for_child(child)
        if not slug:
            continue
        notion_slugs.add(slug)

        if slug not in existing_pages:
            missing_from_meta.append(slug)
            continue

        prior = existing_pages[slug]
        try:
            live_meta = client.fetch_page_metadata(child.page_id)
        except Exception:
            # Drift check is best-effort on the Notion side; if we
            # cannot fetch metadata, classify as notion_newer to err
            # on the side of "needs sync" — caller can re-run.
            notion_newer.append(slug)
            continue

        if live_meta.last_edited_time != prior.notion_last_edited_time:
            notion_newer.append(slug)
            continue

        # Compare local file sha256 against recorded sha.
        local_path = bible_dir / f"{slug}.md"
        if not local_path.exists():
            mirror_modified.append(slug)
            continue
        local_sha = _sha256_text(local_path.read_text(encoding="utf-8"))
        if local_sha != prior.content_sha256:
            mirror_modified.append(slug)
            continue

        in_sync.append(slug)

    # Orphans: local *.md exists but no meta entry, AND Notion did
    # not claim the slug. (If Notion has it but meta doesn't, that
    # is missing_from_meta, not orphan.)
    orphan: list[str] = []
    if bible_dir.exists():
        for md_path in sorted(bible_dir.glob("*.md")):
            slug = md_path.stem
            if slug in existing_pages:
                continue
            if slug in notion_slugs:
                continue
            orphan.append(slug)

    return DriftReport(
        in_sync=tuple(in_sync),
        notion_newer=tuple(notion_newer),
        mirror_modified=tuple(mirror_modified),
        orphan=tuple(orphan),
        missing_from_meta=tuple(missing_from_meta),
    )


# --------------------------------------------------------------------------- #
# Internals — credentials, sync_meta, hashing                                 #
# --------------------------------------------------------------------------- #


def _load_credentials() -> Credentials:
    """Read and validate ``~/.cee/credentials.toml`` against the
    :class:`schemas.Credentials` model.

    Phase 1 ships a commented-out credentials.toml; bible 04 §5.2
    makes the file optional in Phase 1. Missing file or empty
    ``[anthropic]`` section yields ``Credentials(anthropic=None)``,
    which the caller treats as ``credentials_missing``.
    """
    path = paths.CREDENTIALS_FILE
    if not path.exists():
        return Credentials(anthropic=None)

    try:
        with path.open("rb") as fh:
            raw = tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise BootBibleSyncError(
            kind="credentials_missing",
            reason=f"failed to read {path}: {exc}",
            detail={"credentials_path": str(path)},
        ) from exc

    return Credentials.model_validate(raw)


def _load_sync_meta(meta_path: Path) -> SyncMeta | None:
    """Read and validate ``.sync_meta.json``. Returns ``None`` if the
    file does not exist (first sync) or fails to parse / validate
    (treated as if missing — sync proceeds and rewrites it)."""
    if not meta_path.exists():
        return None
    try:
        text = meta_path.read_text(encoding="utf-8")
    except OSError:
        return None
    import json

    try:
        raw = json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return None
    try:
        return SyncMeta.model_validate(raw)
    except Exception:  # pydantic.ValidationError
        return None


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _utc_now_iso() -> str:
    """ISO-8601 UTC timestamp matching the format the audit log uses."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _slug_for_child(child: ChildRef) -> str:
    """Derive the canonical ``<NN>_<slug>`` filename stem from a child
    page's title.

    Bible mirror filenames are lowercase, underscore-delimited,
    starting with a two-digit number. The Notion canonical title
    is something like ``"00 — PROJECT VISION"``. This helper
    extracts the leading two-digit number and a snake-case version
    of the rest.
    """
    title = child.title.strip()
    if not title:
        return ""
    # Try to match leading "NN" or "NN —" / "NN -".
    head, _, tail = title.partition(" ")
    if not (len(head) == 2 and head.isdigit()):
        return ""
    rest = tail.strip()
    # Strip a leading em-dash or hyphen separator.
    for sep in ("— ", "- ", "-- "):
        if rest.startswith(sep):
            rest = rest[len(sep):]
            break
    # Slugify: lowercase, replace non-alphanumeric with underscore,
    # collapse runs.
    import re

    slug_body = re.sub(r"[^a-z0-9]+", "_", rest.lower()).strip("_")
    if not slug_body:
        return ""
    return f"{head}_{slug_body}"


# --------------------------------------------------------------------------- #
# Audit emitters                                                              #
# --------------------------------------------------------------------------- #


def _audit_emit_cli_invoke() -> None:
    """Per bible 04 §5.6 + bible 12 §5.8 — manual invocation entry."""
    audit_log_append(
        log_path=paths.AUDIT_CLI_LOG,
        actor=RoleEnum.OPERATOR.value,
        event="cli_invoke",
        details={"command": "cee sync-bible"},
    )


def _audit_emit_b2_drift_detected() -> None:
    """Per bible 04 §5.6 + bible 12 §5.8 — boot-trigger entry."""
    audit_log_append(
        log_path=paths.AUDIT_BOOT_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="b2_drift_detected",
        details={"trigger": "auto_sync"},
    )


def _audit_emit_sync_start(*, trigger: SyncTrigger, page_count_expected: int) -> None:
    audit_log_append(
        log_path=paths.AUDIT_ROLES_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="sync_bible_start",
        details={"trigger": trigger, "page_count_expected": page_count_expected},
    )


def _audit_emit_page_synced(
    page_slug: str,
    notion_last_edited_time: str,
    content_sha256: str,
) -> None:
    audit_log_append(
        log_path=paths.AUDIT_ROLES_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="sync_bible_page_synced",
        details={
            "page_slug": page_slug,
            "notion_last_edited_time": notion_last_edited_time,
            "content_sha256": content_sha256,
        },
    )


def _audit_emit_page_failed(page_slug: str, error_type: str) -> None:
    audit_log_append(
        log_path=paths.AUDIT_ROLES_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="sync_bible_page_failed",
        details={"page_slug": page_slug, "error_type": error_type},
    )


def _audit_emit_sync_end(
    *,
    trigger: SyncTrigger,
    synced_count: int,
    failed_count: int,
    duration_ms: int,
) -> None:
    audit_log_append(
        log_path=paths.AUDIT_ROLES_LOG,
        actor=RoleEnum.BOOT_SEQUENCER.value,
        event="sync_bible_end",
        details={
            "trigger": trigger,
            "synced_count": synced_count,
            "failed_count": failed_count,
            "duration_ms": duration_ms,
        },
    )


def _emit_terminal_audit(
    trigger: SyncTrigger,
    started_monotonic: float,
    *,
    synced: tuple[str, ...],
    failed: tuple[tuple[str, str], ...],
) -> None:
    """Emit the ``sync_bible_end`` entry just before raising a halt
    exception, so even halted syncs leave a forensic trail.

    Per bible 04 §5.6: the audit log is the source of truth for
    sync-bible activity. A halt with no ``sync_bible_end`` entry
    looks like the sync silently disappeared mid-flight, which would
    contradict bible 12 §5.8's audit-completeness invariant.
    """
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    _audit_emit_sync_end(
        trigger=trigger,
        synced_count=len(synced),
        failed_count=len(failed),
        duration_ms=duration_ms,
    )


# --------------------------------------------------------------------------- #
# Normalization stub: blocks → markdown                                       #
# --------------------------------------------------------------------------- #


def _blocks_to_markdown(blocks: list[Block]) -> str:
    """Render a Notion block tree to bible-style markdown.

    **Phase 2 stub scope.** This stub handles only the block types
    observed in the current bible corpus (verified by surveying
    bibles 00, 04, 19 at T6's Step 3 design pass). The supported set:

    * ``heading_1`` / ``heading_2`` / ``heading_3`` →
      ``# `` / ``## `` / ``### `` (Notion has no heading_4).
    * ``paragraph`` → rendered rich_text on its own line.
    * ``bulleted_list_item`` → ``- ...`` with depth-1 children
      indented by 2 spaces.
    * ``numbered_list_item`` → ``1. ...`` (always ``1.``; Notion
      auto-numbers within consecutive sibling runs).
    * ``code`` → fenced code with language tag.
    * ``divider`` → ``---``.
    * ``quote`` → ``> ...`` (single-line).
    * ``table`` + ``table_row`` → HTML ``<table header-row="true">``
      with ``<tr><td>...</td>...</tr>`` rows. Bible's tables are
      authored as HTML in markdown because GFM tables don't roundtrip
      cleanly with Notion.

    **heading_4 caveat (per bible 04 §5.6 deferred mirror-side
    drift):** Notion has no ``heading_4`` block type, so this stub
    never emits ``####``. Current local bibles contain ``####``
    headings from manual Phase 1 transcription (12 bibles affected as
    of T6); after sync those H4 headings disappear. The resulting
    sha256 mismatch will surface as :attr:`DriftReport.mirror_modified`
    on the next ``check_drift()`` call. This is bible 04 §5.6's
    deferred "Mirror-side drift handling" item — out of T6 scope.

    **Explicit exclusions (NOT emitted, NOT round-tripped):**

    * Toggle, callout, image, file, video, embed, equation,
      synced_block, column, column_list — none observed in current
      bibles.
    * Underline, strikethrough, color rich_text annotations — none
      observed.
    * List nesting beyond depth 2 — per AB-locked T6 Q1.
    * Multi-line block quotes — single-line only; multi-line collapses
      to consecutive ``> ...`` lines if Notion emits them as
      consecutive quote blocks.
    """
    lines: list[str] = []
    for block in blocks:
        rendered = _render_block(block, indent=0)
        if rendered:
            lines.append(rendered)
    text = "\n\n".join(lines)
    # Trailing newline to match POSIX file convention.
    return text + "\n" if text else ""


def _render_block(block: Block, *, indent: int) -> str:
    """Render one block (and its children) to a markdown string."""
    rt = _render_rich_text(block.rich_text)
    indent_str = " " * indent

    if block.type == "heading_1":
        return f"# {rt}"
    if block.type == "heading_2":
        return f"## {rt}"
    if block.type == "heading_3":
        return f"### {rt}"
    if block.type == "paragraph":
        return rt
    if block.type == "divider":
        return "---"
    if block.type == "quote":
        return f"> {rt}"
    if block.type == "code":
        lang = block.code_language or ""
        body = _render_rich_text_plain(block.rich_text)
        return f"```{lang}\n{body}\n```"
    if block.type == "bulleted_list_item":
        head = f"{indent_str}- {rt}"
        nested = [_render_block(child, indent=indent + 2) for child in block.children]
        return "\n".join([head, *(n for n in nested if n)])
    if block.type == "numbered_list_item":
        head = f"{indent_str}1. {rt}"
        nested = [_render_block(child, indent=indent + 3) for child in block.children]
        return "\n".join([head, *(n for n in nested if n)])
    if block.type == "table":
        rows = [_render_block(child, indent=0) for child in block.children]
        body = "\n".join(r for r in rows if r)
        return (
            '<table header-row="true">\n'
            + body
            + ("\n</table>" if body else "</table>")
        )
    if block.type == "table_row":
        cells = "".join(
            f"<td>{_render_rich_text(cell)}</td>" for cell in block.cells
        )
        return f"<tr>{cells}</tr>"
    return ""


def _render_rich_text(spans: tuple[RichTextSpan, ...]) -> str:
    """Render a rich_text array to inline markdown.

    Annotation rendering order: code wraps innermost (the bibles use
    ``\\`text\\``), bold/italic wrap outermost. When multiple
    annotations apply, the order matches what shows up in the
    existing bible mirrors (e.g., ``**bold**`` outside ``\\`code\\``
    — but combined annotations are rare in observed bibles, so the
    stub keeps a simple, predictable rule).
    """
    out: list[str] = []
    for span in spans:
        text = span.text
        if span.code:
            text = f"`{text}`"
        if span.italic:
            text = f"*{text}*"
        if span.bold:
            text = f"**{text}**"
        out.append(text)
    return "".join(out)


def _render_rich_text_plain(spans: tuple[RichTextSpan, ...]) -> str:
    """Render rich_text without annotations (used inside code fences,
    where backticks/asterisks are literal)."""
    return "".join(span.text for span in spans)
