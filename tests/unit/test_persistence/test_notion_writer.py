"""Tests for persistence/notion_writer.py - promotion queue lifecycle.

Coverage per Step 3 design:

* queue() idempotency (7) + dedupe (audit + skip-silent)
* drain() against current T6 stub (transport_unavailable path) (7)
* drain() against mock concrete client (write Protocol scaffold) (5)
* mark_approved() lifecycle (5)
* mark_rejected() lifecycle (5)
* read_queue() file-state cases (4)
* Persistence round-trip (3)
* DrainResult shape (3)
* B8-callable contract (3)
* Audit emission completeness (5)
* Bible-grounding drift detectors (4)
* Queue size warning at 50+ (2)
* Public API surface (2)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import paths
from persistence import (
    DrainResult,
    drain,
    mark_approved,
    mark_rejected,
    queue,
    read_queue,
)
from persistence import notion_writer
from schemas.promotion_queue import (
    PromotionQueue,
    PromotionQueueEntry,
    PromotionStatus,
)


# ---------------------------------------------------------------------------
# Fixtures: redirect paths.PROMOTION_QUEUE + paths.AUDIT_ROLES_LOG to tmp
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect both queue file and audit log to tmp paths.

    Re-binds paths.PROMOTION_QUEUE + paths.AUDIT_ROLES_LOG, scaffolds
    the audit dir + empty log, and resets the filesystem_writer
    allowed-writes map so NOTION_WRITER can target the tmp queue path.
    """
    queue_path = tmp_path / "promotion_queue.json"
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    audit_log = audit_dir / "roles.log"
    audit_log.touch()

    monkeypatch.setattr(paths, "PROMOTION_QUEUE", queue_path)
    monkeypatch.setattr(paths, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(paths, "AUDIT_ROLES_LOG", audit_log)

    # Refresh filesystem_writer's allowed-writes map so role checks
    # see the new PROMOTION_QUEUE.
    from persistence import filesystem_writer

    monkeypatch.setattr(
        filesystem_writer,
        "_ALLOWED_WRITES",
        filesystem_writer._rebuild_allowed_writes(),
    )

    return queue_path


def _read_audit_events(audit_log: Path) -> list[dict[str, Any]]:
    """Read all audit entries as parsed dicts."""
    if not audit_log.exists():
        return []
    return [
        json.loads(line)
        for line in audit_log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# Section 1: queue() idempotency + dedupe (7 tests)
# ---------------------------------------------------------------------------


def test_queue_first_enqueue_persists(isolated_paths: Path) -> None:
    entry = queue(
        slug="cool-skill", kind="skill", payload_path="/tmp/skill.md"
    )
    assert entry.slug == "cool-skill"
    assert entry.status == "queued"
    persisted = read_queue()
    assert len(persisted.entries) == 1
    assert persisted.entries[0].slug == "cool-skill"


def test_queue_dedupes_same_slug_kind(isolated_paths: Path) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/a.md")
    queue(slug="x", kind="skill", payload_path="/tmp/b.md")  # different path
    persisted = read_queue()
    assert len(persisted.entries) == 1
    # original payload_path preserved (skip-silent)
    assert persisted.entries[0].payload_path == "/tmp/a.md"


def test_queue_dedupe_returns_existing_entry(isolated_paths: Path) -> None:
    first = queue(slug="x", kind="skill", payload_path="/tmp/a.md")
    second = queue(slug="x", kind="skill", payload_path="/tmp/b.md")
    assert second.slug == first.slug
    assert second.enqueued_at == first.enqueued_at


def test_queue_distinct_kind_same_slug_allowed(isolated_paths: Path) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/skill.md")
    queue(slug="x", kind="agent", payload_path="/tmp/agent.md")
    persisted = read_queue()
    assert len(persisted.entries) == 2
    kinds = {e.kind for e in persisted.entries}
    assert kinds == {"skill", "agent"}


def test_queue_emits_enqueue_audit(isolated_paths: Path) -> None:
    queue(
        slug="x",
        kind="skill",
        payload_path="/tmp/x.md",
        enqueued_by_run="run123",
    )
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    enqueue_events = [e for e in events if e["event"] == "notion_queue_enqueue"]
    assert len(enqueue_events) == 1
    assert enqueue_events[0]["actor"] == "NOTION_WRITER"
    assert enqueue_events[0]["details"]["slug"] == "x"
    assert enqueue_events[0]["run_id"] == "run123"


def test_queue_dedupe_emits_dedupe_audit(isolated_paths: Path) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    dedupe_events = [
        e for e in events if e["event"] == "notion_queue_enqueue_dedupe"
    ]
    assert len(dedupe_events) == 1
    assert dedupe_events[0]["details"]["existing_status"] == "queued"


def test_queue_default_enqueued_at_is_iso_utc(
    isolated_paths: Path,
) -> None:
    entry = queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    # ISO 8601 with Z suffix per bible canonical
    assert entry.enqueued_at.endswith("Z")
    assert "T" in entry.enqueued_at


# ---------------------------------------------------------------------------
# Section 2: drain() against current T6 stub (7 tests)
# ---------------------------------------------------------------------------


def test_drain_empty_queue_no_transport_call(isolated_paths: Path) -> None:
    """Empty queue must not invoke client.connect()."""
    sentinel: list[str] = []

    class FailFastClient:
        def connect(self) -> None:
            sentinel.append("connect_called")
            raise AssertionError("should not be called for empty queue")

    result = drain(client_factory=lambda: FailFastClient())
    assert result.ok is True
    assert result.attempted == ()
    assert result.transport_unavailable is False
    assert sentinel == []


def test_drain_against_stub_marks_entries_transport_not_implemented(
    isolated_paths: Path,
) -> None:
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    queue(slug="b", kind="agent", payload_path="/tmp/b.md")
    result = drain()  # default factory returns _StubMCPClient
    assert result.ok is False
    assert result.transport_unavailable is True
    assert set(result.attempted) == {"a", "b"}
    assert result.succeeded == ()
    assert sorted(result.failed) == [
        ("a", "transport_not_implemented"),
        ("b", "transport_not_implemented"),
    ]


def test_drain_against_stub_increments_attempts_and_persists(
    isolated_paths: Path,
) -> None:
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    drain()
    after_first = read_queue()
    assert after_first.entries[0].attempts == 1
    assert after_first.entries[0].last_error == "transport_not_implemented"
    drain()
    after_second = read_queue()
    assert after_second.entries[0].attempts == 2


def test_drain_against_stub_does_not_raise(isolated_paths: Path) -> None:
    """Per bible 00 Sec 12 B8: failures stay queued, never raise."""
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    # Should return DrainResult, not raise
    result = drain()
    assert isinstance(result, DrainResult)


def test_drain_skipped_count_excludes_non_queued(
    isolated_paths: Path,
) -> None:
    """Entries in pending_review/approved/rejected status are skipped."""
    # Manually set up a queue with mixed statuses
    q = PromotionQueue(
        last_updated="2026-01-01T00:00:00Z",
        entries=[
            PromotionQueueEntry(
                slug="queued1",
                kind="skill",
                status="queued",
                enqueued_at="2026-01-01T00:00:00Z",
                payload_path="/tmp/q.md",
            ),
            PromotionQueueEntry(
                slug="approved1",
                kind="skill",
                status="approved",
                enqueued_at="2026-01-01T00:00:00Z",
                payload_path="/tmp/a.md",
            ),
            PromotionQueueEntry(
                slug="rejected1",
                kind="agent",
                status="rejected",
                enqueued_at="2026-01-01T00:00:00Z",
                payload_path="/tmp/r.md",
            ),
        ],
    )
    notion_writer._persist_queue(q)
    result = drain()
    assert set(result.attempted) == {"queued1"}
    assert set(result.skipped) == {"approved1", "rejected1"}


def test_drain_emits_start_and_end_audit(isolated_paths: Path) -> None:
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    drain()
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    starts = [e for e in events if e["event"] == "notion_queue_drain_start"]
    ends = [e for e in events if e["event"] == "notion_queue_drain_end"]
    assert len(starts) == 1
    assert len(ends) == 1
    assert ends[0]["details"]["transport_unavailable"] is True


def test_drain_emits_per_entry_failed_audit_for_stub(
    isolated_paths: Path,
) -> None:
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    queue(slug="b", kind="agent", payload_path="/tmp/b.md")
    drain()
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    failed_events = [
        e for e in events if e["event"] == "notion_queue_drain_entry_failed"
    ]
    assert len(failed_events) == 2
    assert all(
        e["details"]["error_type"] == "transport_not_implemented"
        for e in failed_events
    )


# ---------------------------------------------------------------------------
# Section 3: drain() against mock concrete client (5 tests)
# ---------------------------------------------------------------------------


class _MockConcreteClient:
    """Mock that simulates the future concrete-transport write Protocol.

    Used to exercise the post-connect per-entry write loop framework
    (the # TODO #52 scaffold) without depending on the real Notion
    MCP transport.
    """

    def __init__(
        self,
        *,
        connect_ok: bool = True,
        page_id_for: dict[str, str] | None = None,
        raise_for: dict[str, Exception] | None = None,
    ) -> None:
        self.connect_ok = connect_ok
        self.page_id_for = page_id_for or {}
        self.raise_for = raise_for or {}
        self.connect_calls = 0
        self.create_calls: list[tuple[str, str, str]] = []

    def connect(self) -> None:
        self.connect_calls += 1
        if not self.connect_ok:
            raise ConnectionError("mock connect failed")

    def create_promotion_page(
        self, *, slug: str, kind: str, payload_path: str
    ) -> str:
        self.create_calls.append((slug, kind, payload_path))
        if slug in self.raise_for:
            raise self.raise_for[slug]
        return self.page_id_for.get(slug, f"page-{slug}")


def test_drain_concrete_success_transitions_to_pending_review(
    isolated_paths: Path,
) -> None:
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    client = _MockConcreteClient(page_id_for={"a": "notion-page-a"})
    result = drain(client_factory=lambda: client)
    assert result.ok is True
    assert result.succeeded == ("a",)
    assert result.transport_unavailable is False
    persisted = read_queue()
    assert persisted.entries[0].status == "pending_review"
    assert persisted.entries[0].target_notion_page_id == "notion-page-a"
    assert persisted.entries[0].last_error is None


def test_drain_concrete_per_entry_failure_isolates(
    isolated_paths: Path,
) -> None:
    queue(slug="ok", kind="skill", payload_path="/tmp/ok.md")
    queue(slug="bad", kind="agent", payload_path="/tmp/bad.md")
    client = _MockConcreteClient(
        page_id_for={"ok": "page-ok"},
        raise_for={"bad": RuntimeError("notion 500")},
    )
    result = drain(client_factory=lambda: client)
    assert result.ok is False
    assert result.succeeded == ("ok",)
    assert result.failed == (("bad", "RuntimeError"),)
    persisted = read_queue()
    by_slug = {e.slug: e for e in persisted.entries}
    assert by_slug["ok"].status == "pending_review"
    assert by_slug["bad"].status == "queued"
    assert by_slug["bad"].attempts == 1
    assert "RuntimeError" in by_slug["bad"].last_error


def test_drain_concrete_emits_per_entry_succeeded_audit(
    isolated_paths: Path,
) -> None:
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    client = _MockConcreteClient(page_id_for={"a": "page-a"})
    drain(client_factory=lambda: client)
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    succeeded_events = [
        e
        for e in events
        if e["event"] == "notion_queue_drain_entry_succeeded"
    ]
    assert len(succeeded_events) == 1
    assert succeeded_events[0]["details"]["target_notion_page_id"] == "page-a"


def test_drain_connect_failure_marks_with_connect_failed_error_type(
    isolated_paths: Path,
) -> None:
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    client = _MockConcreteClient(connect_ok=False)
    result = drain(client_factory=lambda: client)
    assert result.transport_unavailable is True
    assert result.failed[0][0] == "a"
    assert "connect_failed" in result.failed[0][1]
    persisted = read_queue()
    assert "ConnectionError" in persisted.entries[0].last_error


def test_drain_concrete_calls_connect_before_create(
    isolated_paths: Path,
) -> None:
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    client = _MockConcreteClient()
    drain(client_factory=lambda: client)
    assert client.connect_calls == 1
    assert len(client.create_calls) == 1
    assert client.create_calls[0] == ("a", "skill", "/tmp/a.md")


# ---------------------------------------------------------------------------
# Section 4: mark_approved() (5 tests)
# ---------------------------------------------------------------------------


def _seed_pending_review(slug: str, kind: str = "skill") -> None:
    queue(slug=slug, kind=kind, payload_path=f"/tmp/{slug}.md")
    client = _MockConcreteClient(page_id_for={slug: f"page-{slug}"})
    drain(client_factory=lambda: client)


def test_mark_approved_pending_review_to_approved(
    isolated_paths: Path,
) -> None:
    _seed_pending_review("x")
    entry = mark_approved(slug="x", kind="skill")
    assert entry.status == "approved"


def test_mark_approved_idempotent_on_already_approved(
    isolated_paths: Path,
) -> None:
    _seed_pending_review("x")
    mark_approved(slug="x", kind="skill")
    # Second call is no-op
    entry = mark_approved(slug="x", kind="skill")
    assert entry.status == "approved"


def test_mark_approved_raises_on_missing_entry(
    isolated_paths: Path,
) -> None:
    with pytest.raises(ValueError, match="no promotion queue entry"):
        mark_approved(slug="ghost", kind="skill")


def test_mark_approved_raises_on_queued_status(
    isolated_paths: Path,
) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    # entry is "queued"; cannot mark_approved without going through drain
    with pytest.raises(ValueError, match="cannot mark_approved"):
        mark_approved(slug="x", kind="skill")


def test_mark_approved_emits_transition_audit(
    isolated_paths: Path,
) -> None:
    _seed_pending_review("x")
    mark_approved(slug="x", kind="skill")
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    transitions = [
        e
        for e in events
        if e["event"] == "notion_queue_transition"
        and e["details"]["to_status"] == "approved"
    ]
    assert len(transitions) == 1
    assert transitions[0]["details"]["from_status"] == "pending_review"


# ---------------------------------------------------------------------------
# Section 5: mark_rejected() (5 tests)
# ---------------------------------------------------------------------------


def test_mark_rejected_pending_review_to_rejected(
    isolated_paths: Path,
) -> None:
    _seed_pending_review("x")
    entry = mark_rejected(slug="x", kind="skill")
    assert entry.status == "rejected"


def test_mark_rejected_allowed_from_queued(isolated_paths: Path) -> None:
    """OPERATOR can pre-reject before drain has run."""
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    entry = mark_rejected(slug="x", kind="skill")
    assert entry.status == "rejected"


def test_mark_rejected_idempotent_on_already_rejected(
    isolated_paths: Path,
) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    mark_rejected(slug="x", kind="skill")
    entry = mark_rejected(slug="x", kind="skill")
    assert entry.status == "rejected"


def test_mark_rejected_raises_on_approved_status(
    isolated_paths: Path,
) -> None:
    _seed_pending_review("x")
    mark_approved(slug="x", kind="skill")
    with pytest.raises(ValueError, match="cannot mark_rejected"):
        mark_rejected(slug="x", kind="skill")


def test_mark_rejected_emits_transition_audit(
    isolated_paths: Path,
) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    mark_rejected(slug="x", kind="skill")
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    transitions = [
        e
        for e in events
        if e["event"] == "notion_queue_transition"
        and e["details"]["to_status"] == "rejected"
    ]
    assert len(transitions) == 1
    assert transitions[0]["details"]["from_status"] == "queued"


# ---------------------------------------------------------------------------
# Section 6: read_queue() (4 tests)
# ---------------------------------------------------------------------------


def test_read_queue_absent_file_returns_empty(isolated_paths: Path) -> None:
    assert not isolated_paths.exists()
    q = read_queue()
    assert q.entries == []


def test_read_queue_with_entries_round_trips(isolated_paths: Path) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    q = read_queue()
    assert len(q.entries) == 1
    assert q.entries[0].slug == "x"


def test_read_queue_empty_file_raises(isolated_paths: Path) -> None:
    isolated_paths.write_text("", encoding="utf-8")
    from pydantic import ValidationError

    with pytest.raises((ValidationError, json.JSONDecodeError, ValueError)):
        read_queue()


def test_read_queue_malformed_json_raises(isolated_paths: Path) -> None:
    isolated_paths.write_text("{not valid json", encoding="utf-8")
    from pydantic import ValidationError

    with pytest.raises((ValidationError, json.JSONDecodeError, ValueError)):
        read_queue()


# ---------------------------------------------------------------------------
# Section 7: Persistence round-trip (3 tests)
# ---------------------------------------------------------------------------


def test_persistence_enqueue_then_read(isolated_paths: Path) -> None:
    queue(
        slug="x",
        kind="skill",
        payload_path="/tmp/x.md",
        enqueued_by_run="run42",
    )
    q = read_queue()
    assert q.entries[0].enqueued_by_run == "run42"


def test_persistence_uses_filesystem_writer_role_check(
    isolated_paths: Path,
) -> None:
    """The on-disk file should appear after queue() returns."""
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    assert isolated_paths.exists()
    raw = json.loads(isolated_paths.read_text(encoding="utf-8"))
    assert raw["produced_by"] == "NOTION_WRITER"


def test_persistence_last_updated_changes_on_write(
    isolated_paths: Path,
) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    first = read_queue().last_updated
    # Force a transition to trigger another write
    mark_rejected(slug="x", kind="skill")
    second = read_queue().last_updated
    # both are valid ISO 8601 timestamps; second >= first lexicographically
    assert second >= first


# ---------------------------------------------------------------------------
# Section 8: DrainResult shape (3 tests)
# ---------------------------------------------------------------------------


def test_drain_result_is_frozen() -> None:
    result = DrainResult(
        ok=True,
        attempted=(),
        succeeded=(),
        failed=(),
        skipped=(),
        transport_unavailable=False,
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        result.ok = False  # type: ignore[misc]


def test_drain_result_has_six_fields() -> None:
    fields = list(DrainResult.__dataclass_fields__.keys())
    assert fields == [
        "ok",
        "attempted",
        "succeeded",
        "failed",
        "skipped",
        "transport_unavailable",
    ]


def test_drain_result_ok_derives_from_failed(isolated_paths: Path) -> None:
    """ok mirrors the conventional `not failed` pattern."""
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    client = _MockConcreteClient(page_id_for={"a": "p"})
    result = drain(client_factory=lambda: client)
    assert result.ok is True
    assert result.failed == ()


# ---------------------------------------------------------------------------
# Section 9: B8-callable contract (3 tests)
# ---------------------------------------------------------------------------


def test_drain_importable_from_persistence() -> None:
    from persistence import drain as drain_imported

    assert drain_imported is drain


def test_drain_signature_accepts_client_factory_keyword(
    isolated_paths: Path,
) -> None:
    """B8 calls drain(client_factory=...). Signature must accept it."""
    import inspect

    sig = inspect.signature(drain)
    assert "client_factory" in sig.parameters
    assert (
        sig.parameters["client_factory"].kind
        == inspect.Parameter.KEYWORD_ONLY
    )


def test_drain_returns_drain_result_not_raises(isolated_paths: Path) -> None:
    """B8 expects drain() to return, never raise (failures stay queued)."""
    queue(slug="a", kind="skill", payload_path="/tmp/a.md")
    result = drain()  # default stub raises internally
    assert isinstance(result, DrainResult)


# ---------------------------------------------------------------------------
# Section 10: Audit emission completeness (5 tests)
# ---------------------------------------------------------------------------


def test_audit_actor_is_notion_writer(isolated_paths: Path) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    drain()
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    assert all(e["actor"] == "NOTION_WRITER" for e in events)


def test_audit_drain_emits_start_end_pair(isolated_paths: Path) -> None:
    drain()  # empty queue
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    starts = [e for e in events if e["event"] == "notion_queue_drain_start"]
    ends = [e for e in events if e["event"] == "notion_queue_drain_end"]
    assert len(starts) == 1
    assert len(ends) == 1


def test_audit_queue_emits_enqueue_event(isolated_paths: Path) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    assert any(e["event"] == "notion_queue_enqueue" for e in events)


def test_audit_mark_approved_emits_transition(isolated_paths: Path) -> None:
    _seed_pending_review("x")
    mark_approved(slug="x", kind="skill")
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    assert any(
        e["event"] == "notion_queue_transition"
        and e["details"]["to_status"] == "approved"
        for e in events
    )


def test_audit_lands_in_paths_audit_roles_log(isolated_paths: Path) -> None:
    queue(slug="x", kind="skill", payload_path="/tmp/x.md")
    # All events land in the path the fixture redirected
    assert paths.AUDIT_ROLES_LOG.exists()
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    assert len(events) > 0


# ---------------------------------------------------------------------------
# Section 11: Bible-grounding drift detectors (4 tests)
# ---------------------------------------------------------------------------

_BIBLE_ROOT = Path(__file__).resolve().parents[3] / "bible"


def test_bible_07_section_11_still_names_four_function_api() -> None:
    """Bible 07 Sec 11 line 411 must still name the bible-grounded API."""
    text = (_BIBLE_ROOT / "07_skill_system_design.md").read_text(
        encoding="utf-8"
    )
    assert "queue(skill)" in text
    assert "drain()" in text
    assert "mark_approved(slug)" in text
    assert "mark_rejected(slug)" in text


def test_bible_00_section_12_b8_still_says_failures_stay_queued() -> None:
    text = (_BIBLE_ROOT / "00_project_vision.md").read_text(encoding="utf-8")
    assert "B8" in text
    assert "Failures stay queued" in text


def test_bible_01_section_10_8_still_caps_at_500_warns_at_50() -> None:
    text = (_BIBLE_ROOT / "01_real_problem_breakdown.md").read_text(
        encoding="utf-8"
    )
    assert "queue is bounded at 500" in text
    assert "50+" in text


def test_bible_04_still_names_promotion_queue_file_path() -> None:
    text = (_BIBLE_ROOT / "04_database_file_structure.md").read_text(
        encoding="utf-8"
    )
    assert "promotion_queue.json" in text


# ---------------------------------------------------------------------------
# Section 12: Queue size warning at 50+ (2 tests)
# ---------------------------------------------------------------------------


def test_queue_size_below_threshold_no_warn(isolated_paths: Path) -> None:
    """Enqueueing fewer than 50 entries does not emit size_warn."""
    for i in range(10):
        queue(slug=f"s{i}", kind="skill", payload_path=f"/tmp/s{i}.md")
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    warns = [e for e in events if e["event"] == "notion_queue_size_warn"]
    assert warns == []


def test_queue_size_at_threshold_emits_warn(isolated_paths: Path) -> None:
    """Reaching 50 entries emits notion_queue_size_warn."""
    # Pin the constant for the test (cheaper than enqueueing 50 entries)
    from persistence import notion_writer as nw

    # We enqueue exactly _QUEUE_SIZE_WARN_THRESHOLD entries to verify
    threshold = nw._QUEUE_SIZE_WARN_THRESHOLD
    assert threshold == 50  # bible 01 Sec 10.8
    for i in range(threshold):
        queue(slug=f"s{i}", kind="skill", payload_path=f"/tmp/s{i}.md")
    events = _read_audit_events(paths.AUDIT_ROLES_LOG)
    warns = [e for e in events if e["event"] == "notion_queue_size_warn"]
    # The warn fires on the 50th enqueue (queue_size >= 50)
    assert len(warns) >= 1
    assert warns[0]["details"]["queue_size"] >= 50


# ---------------------------------------------------------------------------
# Section 13: Public API surface (2 tests)
# ---------------------------------------------------------------------------


def test_public_api_importable_from_persistence() -> None:
    from persistence import (
        DrainResult as DR,
        drain as drain_fn,
        mark_approved as ma,
        mark_rejected as mr,
        queue as q_fn,
        read_queue as rq,
    )

    assert callable(drain_fn)
    assert callable(ma)
    assert callable(mr)
    assert callable(q_fn)
    assert callable(rq)
    assert DR is not None


def test_public_api_function_names_match_bible_07() -> None:
    """API names are bible 07 Sec 11 line 411 verbatim."""
    from persistence import notion_writer as nw

    assert hasattr(nw, "queue")
    assert hasattr(nw, "drain")
    assert hasattr(nw, "mark_approved")
    assert hasattr(nw, "mark_rejected")
    assert hasattr(nw, "read_queue")
