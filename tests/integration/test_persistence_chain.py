"""Three-substrate round-trip integration test.

Phase 3 task 12 (Track C). Satisfies bible 20 §5.3 gate criterion (a):
"A test fixture artifact can be written to all three substrates and
reads back identically (modulo redaction differences)."

The round-trip exercises one canonical Skill artifact through:

1. **Filesystem leg** — :func:`persistence.filesystem_writer.write_text`
   with ``role=PERSISTENCE_WRITER`` writes ``SKILL.md`` under
   :data:`paths.SKILLS_DIR / <slug>`.
2. **Obsidian leg** — :func:`persistence.obsidian_writer.write_artifact`
   with ``artifact_kind="skill"`` writes the vault note under
   :data:`paths.OBSIDIAN_SKILLS_DIR / <slug>.md`.
3. **Notion leg** — :func:`persistence.notion_writer.queue` enqueues
   a promotion candidate; :func:`persistence.notion_writer.drain` with
   an injected stub :class:`NotionMCPClient` records the
   ``create_promotion_page`` call and returns a fake page id.

Verification is **content equivalence** (Q2 path (b)) — each substrate
has the artifact at its expected canonical path with byte-equal content
against canonical inputs. No canonical-form hashing infrastructure
exists in the repo, so cross-substrate hash equivalence (Q2 path (c))
is not yet feasible; deferred.

# TODO #46 / bible 20 §5.3: Q2 path (c) cross-substrate hash
# equivalence. Requires a canonical-form normalizer that produces
# identical bytes from the per-substrate rendered shapes (which differ
# by frontmatter — bible 13 §5.3's Obsidian note carries
# ``canon_path`` + ``notion_url`` fields the filesystem SKILL.md does
# not). Defer until normalizer exists.

Bible references:

* **20 §5.3** — gate criterion (a) load-bearing source.
* **04 §5.1** — filesystem canon paths for Skills.
* **13 §5.3** — Obsidian skill note format.
* **07 §5.5 + §11** — promotion lifecycle (queue → drain → pending_review
  → approved/rejected) + canonical API names.
* **12 §5.8** — roles.log audit entry shape (verified by
  :func:`verify_audit_chain`).

build_status.md spec staleness — surfaced for posterity:

The build_status.md T12 spec (lines 612-630) carries four material
inaccuracies relative to current Phase 1-3 ships. T12 implementation
aligns with reality, not the stale spec. Cleanup of build_status.md
deferred to T13 (Phase 3 gate) per AB sign-off.

1. **Wrong filesystem function name.** Spec: ``filesystem_writer.write
   (artifact)``. Reality: writers are :func:`write_text(role, target,
   content)` / :func:`write_json(role, target, payload)`. T12 uses
   ``write_text`` for SKILL.md (markdown text body).
2. **Wrong Obsidian expectation.** Spec: "expects the dispatch shell's
   ``NotImplementedError('renderer deferred')``". Reality: T4 ships
   :func:`obsidian_writer.write_artifact(kind, id, content)` plumbing
   that accepts pre-rendered content; per-kind renderers are deferred
   but the plumbing layer is live. T12 hand-constructs canonical
   Obsidian content (Phase 5+ renderer not in scope) and exercises
   the live plumbing.
3. **Wrong Notion function name.** Spec: ``notion_writer.enqueue
   (artifact)``. Reality: function name is :func:`queue`, signature is
   ``(*, slug, kind, payload_path, ...) -> PromotionQueueEntry``. T12
   uses ``queue`` + :func:`drain` (Notion's two-phase
   enqueue-then-flush model per bible 07 §5.5).
4. **Wrong audit assertion.** Spec: "exactly one ``filesystem_write``
   + one ``promotion_enqueued`` event in roles.log". Reality:
   :mod:`filesystem_writer` does NOT audit per-write on success
   (filesystem_writer.py module docstring lines 42-44 explicitly:
   "Successful writes are NOT audited per route — the artifact's own
   ``produced_by`` field is the canonical provenance"). Audit emission
   is exclusive to :mod:`notion_writer` lifecycle events
   (``notion_queue_enqueue``, ``notion_queue_drain_*`` family).
   T12 asserts only events that actually fire.

Stub injection mechanism:

:func:`persistence.notion_writer.drain`'s post-connect write loop
(notion_writer.py:431-441) looks up ``create_promotion_page`` on the
injected client via :func:`getattr`, providing the deliberate test
hook for the post-Phase-3 concrete transport (``# TODO #52`` in the
upstream module). T12's :class:`_ChainStubClient` attaches this method
non-Protocol-conformantly — the canonical Phase 1-shipped test
injection mechanism, not a workaround.
"""

from __future__ import annotations

import argparse
import contextlib
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import paths
from cli.commands.scaffold_obsidian import cmd_scaffold_obsidian
from persistence import filesystem_writer, notion_writer, obsidian_writer
from persistence.audit import scaffold_audit_logs, verify_audit_chain
from persistence.filesystem_writer import write_text as filesystem_write_text
from roles import RoleEnum


# ─── Canonical fixtures (hand-constructed) ──────────────────────────────


_TEST_SLUG: str = "test-roundtrip-skill"
_STUB_PAGE_ID: str = "notion-page-stub-001"

# Hand-constructed canonical SKILL.md content. Realistic frontmatter
# shape per bible 15 §5.2 plus a minimal body. T12 verifies byte-equal
# round-trip; schema validation is unit-test territory (covered in
# tests/unit/test_schemas/test_skill_frontmatter.py).
_SKILL_MD_CONTENT: str = """\
---
slug: test-roundtrip-skill
version: 1.0.0
description: Fixture skill for the T12 three-substrate round-trip integration test.
triggers:
  - "round-trip skill verification"
inputs:
  - "test fixture context"
outputs:
  - "verified round-trip evidence"
task_types_supported:
  - BUILD
posture_hints:
  - primary
---

# Test Round-Trip Skill

This skill exists exclusively as a fixture for the three-substrate
round-trip integration test. Body content is byte-faithfully verified
across the filesystem leg of the round-trip.
"""

# Hand-constructed canonical Obsidian note content per bible 13 §5.3
# format. Per-kind renderer (Phase 5+) would generate this from a
# Skill schema instance; T12 hand-constructs to exercise the
# write_artifact plumbing without depending on the deferred renderer.
_OBSIDIAN_NOTE_CONTENT: str = """\
---
type: skill
slug: test-roundtrip-skill
version: 1.0.0
canon_path: ~/cee/skills/test-roundtrip-skill/SKILL.md
created_by_run: manual
created_at: 2026-01-01T00:00:00Z
task_types_supported: [BUILD]
posture_hints: [primary]
needs_review: false
promotion_status: not_queued
usage_count: 0
tags: [cee, skill, skill/BUILD]
---

# test-roundtrip-skill

## Description
Fixture skill for the T12 three-substrate round-trip integration test.

## Linked
- Filesystem canon: `~/cee/skills/test-roundtrip-skill/SKILL.md`
"""


# ─── Inline NotionMCPClient stub ────────────────────────────────────────


@dataclass
class _ChainStubClient:
    """Inline :class:`boot.notion_mcp.NotionMCPClient` mock for T12.

    Records ``create_promotion_page`` invocations and returns a stable
    fake page id. Mirrors the inline-stub convention established by
    :class:`tests.integration.test_phase2_gate._GateMockClient` and
    :class:`tests.integration.test_bible_sync_e2e.IntegMockClient` —
    each integration test carries its own minimal mock; cross-file
    stub imports are explicitly NOT the established pattern.

    Conforms to :class:`NotionMCPClient` Protocol structurally
    (Protocol is not :func:`runtime_checkable`; duck typing is
    sufficient). Adds ``create_promotion_page`` non-Protocol-conformantly
    because that method is a ``# TODO #52`` getattr-injection point in
    :func:`persistence.notion_writer.drain` (notion_writer.py:431-441),
    not yet promoted into the Protocol.
    """

    create_promotion_page_calls: list[dict[str, str]] = field(
        default_factory=list
    )

    def connect(self) -> None:
        # No-op. Bypasses _StubMCPClient default which raises
        # NotImplementedError; that's what we WANT to bypass for T12.
        return None

    def fetch_page_metadata(self, page_id: str) -> Any:
        raise NotImplementedError(
            "T12 stub: fetch_page_metadata not exercised by round-trip"
        )

    def enumerate_children(self, parent_id: str) -> list[Any]:
        raise NotImplementedError(
            "T12 stub: enumerate_children not exercised by round-trip"
        )

    def fetch_page_blocks(self, page_id: str) -> list[Any]:
        raise NotImplementedError(
            "T12 stub: fetch_page_blocks not exercised by round-trip"
        )

    def create_promotion_page(
        self, *, slug: str, kind: str, payload_path: str,
    ) -> str:
        self.create_promotion_page_calls.append({
            "slug": slug,
            "kind": kind,
            "payload_path": payload_path,
        })
        return _STUB_PAGE_ID


# ─── chain_env fixture ─────────────────────────────────────────────────


@dataclass
class _ChainEnv:
    """Carrier for fixture state passed to test bodies."""

    tmp_root: Path
    skill_md_path: Path
    obsidian_skill_path: Path
    promotion_queue_path: Path
    roles_log_path: Path


@pytest.fixture
def chain_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> _ChainEnv:
    """Three-substrate isolated fixture under ``tmp_path``.

    Monkeypatches every ``paths.*`` constant the round-trip touches,
    rebuilds :data:`filesystem_writer._ALLOWED_WRITES` against the
    patched constants (required because the map is built at module
    import time per filesystem_writer.py:127 — untouched, the
    role-enforcement layer would still point at production paths and
    reject every test write), seeds via :func:`cmd_scaffold_obsidian`
    (T11) for the Obsidian leg and :func:`scaffold_audit_logs` for
    the audit substrate, and ensures the per-skill filesystem
    directory exists.

    Per AB-locked decision: scaffold via :func:`cmd_scaffold_obsidian`
    (not direct :func:`scaffold_obsidian` call) so T11 stays in the
    integration path — drift in T11's CLI surface would surface here.
    """
    # ─── Filesystem canon paths ────────────────────────────────────────
    cee_root = tmp_path / "cee"
    monkeypatch.setattr(paths, "CEE_ROOT", cee_root)
    monkeypatch.setattr(paths, "SKILLS_DIR", cee_root / "skills")
    monkeypatch.setattr(paths, "AGENTS_DIR", cee_root / ".claude" / "agents")
    monkeypatch.setattr(paths, "RUNS_DIR", cee_root / "runs")
    monkeypatch.setattr(paths, "PROMOTION_QUEUE", cee_root / "promotion_queue.json")
    monkeypatch.setattr(paths, "BIBLE_DIR", cee_root / "bible")
    monkeypatch.setattr(
        paths, "BIBLE_SYNC_META", cee_root / "bible" / ".sync_meta.json",
    )

    # ─── Audit log paths ───────────────────────────────────────────────
    audit_dir = cee_root / "audit"
    monkeypatch.setattr(paths, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(paths, "AUDIT_ARCHIVE_DIR", audit_dir / "archive")
    monkeypatch.setattr(paths, "AUDIT_CLI_LOG", audit_dir / "cli.log")
    monkeypatch.setattr(paths, "AUDIT_ROLES_LOG", audit_dir / "roles.log")
    monkeypatch.setattr(paths, "AUDIT_BOOT_LOG", audit_dir / "boot.log")
    monkeypatch.setattr(paths, "AUDIT_SECURITY_LOG", audit_dir / "security.log")

    # ─── Obsidian vault paths ──────────────────────────────────────────
    vault = tmp_path / "SecondBrain" / "cee"
    monkeypatch.setattr(paths, "OBSIDIAN_VAULT", vault)
    monkeypatch.setattr(paths, "OBSIDIAN_RUNS_DIR", vault / "runs")
    monkeypatch.setattr(paths, "OBSIDIAN_SKILLS_DIR", vault / "skills")
    monkeypatch.setattr(paths, "OBSIDIAN_AGENTS_DIR", vault / "agents")
    monkeypatch.setattr(paths, "OBSIDIAN_BIBLE_DIR", vault / "bible")
    monkeypatch.setattr(paths, "OBSIDIAN_AUDIT_DIR", vault / "audit")
    monkeypatch.setattr(paths, "OBSIDIAN_TEMPLATES_DIR", vault / "_templates")

    # Refresh the role-enforcement map after monkeypatching paths.
    # Pattern documented at filesystem_writer.py:46-51 + used by
    # tests/integration/test_boot_sequence.py:228-232.
    monkeypatch.setattr(
        filesystem_writer,
        "_ALLOWED_WRITES",
        filesystem_writer._rebuild_allowed_writes(),
    )

    # Seed Obsidian vault via T11's cmd_scaffold_obsidian (NOT a direct
    # scaffold_obsidian call). T11 stays in the integration path so
    # any future drift in the CLI surface would surface here.
    # Suppress stdout — scaffold's per-path render is operator UX
    # noise inside an integration fixture.
    with contextlib.redirect_stdout(io.StringIO()):
        rc = cmd_scaffold_obsidian(
            argparse.Namespace(command="scaffold-obsidian")
        )
    assert rc == 0, "T11 scaffold must succeed inside chain fixture"

    # Seed the four canonical audit logs so verify_audit_chain has
    # files to walk and notion_writer has a destination for emissions.
    scaffold_audit_logs()

    # Ensure the per-skill filesystem directory exists. SKILL.md will
    # be written here by the filesystem leg.
    skill_dir = paths.SKILLS_DIR / _TEST_SLUG
    paths.ensure_dir(skill_dir)

    return _ChainEnv(
        tmp_root=tmp_path,
        skill_md_path=skill_dir / "SKILL.md",
        obsidian_skill_path=paths.OBSIDIAN_SKILLS_DIR / f"{_TEST_SLUG}.md",
        promotion_queue_path=paths.PROMOTION_QUEUE,
        roles_log_path=paths.AUDIT_ROLES_LOG,
    )


# ─── Round-trip helper ─────────────────────────────────────────────────


def _execute_round_trip(env: _ChainEnv) -> tuple[_ChainStubClient, Any]:
    """Run the three-substrate round-trip and return (stub, drain_result).

    Centralises the common sequence so individual tests assert on
    different aspects of the same execution path. Returns the stub
    (with recorded calls) and the :class:`DrainResult` so tests can
    inspect both sides of the Notion leg.
    """
    # Filesystem leg
    filesystem_write_text(
        RoleEnum.PERSISTENCE_WRITER,
        env.skill_md_path,
        _SKILL_MD_CONTENT,
    )

    # Obsidian leg
    obsidian_writer.write_artifact(
        artifact_kind="skill",
        artifact_id=_TEST_SLUG,
        content=_OBSIDIAN_NOTE_CONTENT,
    )

    # Notion leg — queue + drain with stub injection
    notion_writer.queue(
        slug=_TEST_SLUG,
        kind="skill",
        payload_path=str(env.skill_md_path),
    )

    stub = _ChainStubClient()
    result = notion_writer.drain(client_factory=lambda: stub)

    return stub, result


# ─── Tests ─────────────────────────────────────────────────────────────


def test_three_substrate_round_trip_skill_writes_to_all_three(
    chain_env: _ChainEnv,
) -> None:
    """Bible 20 §5.3 gate (a): all three substrates have the artifact."""
    stub, _result = _execute_round_trip(chain_env)

    assert chain_env.skill_md_path.exists(), "filesystem leg failed"
    assert chain_env.obsidian_skill_path.exists(), "Obsidian leg failed"
    assert len(stub.create_promotion_page_calls) == 1, (
        "Notion leg did not invoke create_promotion_page exactly once"
    )


def test_filesystem_skill_md_persists_byte_equal(
    chain_env: _ChainEnv,
) -> None:
    """Filesystem leg: SKILL.md content is byte-equal to canonical input."""
    _execute_round_trip(chain_env)

    persisted = chain_env.skill_md_path.read_text(encoding="utf-8")
    assert persisted == _SKILL_MD_CONTENT


def test_obsidian_skill_note_persists_byte_equal(
    chain_env: _ChainEnv,
) -> None:
    """Obsidian leg: vault note content is byte-equal to canonical input."""
    _execute_round_trip(chain_env)

    persisted = chain_env.obsidian_skill_path.read_text(encoding="utf-8")
    assert persisted == _OBSIDIAN_NOTE_CONTENT


def test_notion_drain_invokes_stub_with_correct_payload(
    chain_env: _ChainEnv,
) -> None:
    """Notion leg: stub recorded the exact (slug, kind, payload_path) shape.

    Per AB refinement: also asserts the recorded payload_path points
    at an existing file whose content is byte-equal to the canonical
    SKILL.md input. This locks cross-substrate content equivalence
    via the payload_path linkage — the Notion leg's "content" IS the
    filesystem file, accessed via payload_path.
    """
    stub, _result = _execute_round_trip(chain_env)

    assert stub.create_promotion_page_calls == [{
        "slug": _TEST_SLUG,
        "kind": "skill",
        "payload_path": str(chain_env.skill_md_path),
    }]

    # Payload-path content equivalence (cross-substrate verification).
    recorded_path = Path(stub.create_promotion_page_calls[0]["payload_path"])
    assert recorded_path.exists(), (
        "stub recorded a payload_path that does not exist on disk"
    )
    assert recorded_path.read_text(encoding="utf-8") == _SKILL_MD_CONTENT, (
        "Notion-leg payload_path file content diverges from canonical "
        "SKILL.md input — cross-substrate equivalence violated"
    )


def test_notion_drain_marks_entry_pending_review_on_stub_success(
    chain_env: _ChainEnv,
) -> None:
    """Queue lifecycle: entry transitions queued → pending_review after drain."""
    _execute_round_trip(chain_env)

    queue_after = notion_writer.read_queue()
    matching = [
        e for e in queue_after.entries
        if e.slug == _TEST_SLUG and e.kind == "skill"
    ]
    assert len(matching) == 1
    entry = matching[0]
    assert entry.status == "pending_review"
    assert entry.target_notion_page_id == _STUB_PAGE_ID


def test_drain_returns_ok_with_succeeded_slug(
    chain_env: _ChainEnv,
) -> None:
    """DrainResult shape: ok=True, succeeded carries the slug, failed empty."""
    _stub, result = _execute_round_trip(chain_env)

    assert result.ok is True
    assert result.succeeded == (_TEST_SLUG,)
    assert result.failed == ()
    assert result.transport_unavailable is False


def test_audit_chain_records_notion_lifecycle_events(
    chain_env: _ChainEnv,
) -> None:
    """roles.log carries the canonical notion_writer lifecycle events.

    Per filesystem_writer.py module docstring lines 42-44, filesystem
    + Obsidian writes do NOT audit on success. Only notion_writer
    emits per-event entries. The four expected events are:

    * ``notion_queue_enqueue`` — from queue() at notion_writer.py:262
    * ``notion_queue_drain_start`` — from drain() at notion_writer.py:313
    * ``notion_queue_drain_entry_succeeded`` — from drain() at line 446
    * ``notion_queue_drain_end`` — from drain() at line 478 (final emit)
    """
    import json

    _execute_round_trip(chain_env)

    raw = chain_env.roles_log_path.read_text(encoding="utf-8")
    entries = [json.loads(line) for line in raw.split("\n") if line]
    events = [e["event"] for e in entries]

    assert "notion_queue_enqueue" in events
    assert "notion_queue_drain_start" in events
    assert "notion_queue_drain_entry_succeeded" in events
    assert "notion_queue_drain_end" in events


def test_audit_chain_integrity_after_round_trip(
    chain_env: _ChainEnv,
) -> None:
    """Hash chain stays intact through the full round-trip."""
    _execute_round_trip(chain_env)

    is_valid, broken = verify_audit_chain(chain_env.roles_log_path)
    assert is_valid is True
    assert broken == []


def test_planted_tamper_detected_after_round_trip(
    chain_env: _ChainEnv,
) -> None:
    """Tamper detection: flipping a byte in roles.log breaks the chain.

    Mutates one entry's ``actor`` field and rewrites the file. The
    stored ``entry_hash`` no longer matches the recomputed hash;
    :func:`verify_audit_chain` reports the broken entry.
    """
    import json

    _execute_round_trip(chain_env)

    # Read existing entries, tamper with one, write back.
    raw = chain_env.roles_log_path.read_text(encoding="utf-8")
    entries = [json.loads(line) for line in raw.split("\n") if line]
    assert len(entries) >= 2, (
        "round-trip should produce at least 2 audit entries to tamper"
    )
    entries[0]["actor"] = "TAMPERED_ACTOR"
    chain_env.roles_log_path.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    is_valid, broken = verify_audit_chain(chain_env.roles_log_path)
    assert is_valid is False
    assert len(broken) >= 1
    assert any("entry_hash mismatch" in b["reason"] for b in broken)
