"""End-to-end integration tests for ``boot.sequencer``.

Exercises :func:`boot.sequencer.run` end-to-end against:

* The current real Phase 2 substrate (smoke check — documents the
  expected halt path given current ``~/.cee`` and ``~/cee/bible``
  state).
* Synthetic happy-path fixtures (drift-free + sync-meta valid
  + auto_sync flagged either way).
* Synthetic halt fixtures (B3 enum drift, B2 auto_sync_disabled).

These tests satisfy bible 20 §5.2 Phase 2 gate criterion: "Boot
sequence completes B1–B9 from a clean state" (Test:
``tests/integration/test_boot_sequence.py`` passes).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import paths
from boot.sequencer import BootResult, run
from errors import BootBibleSyncError, BootConsistencyError, BootError


# --------------------------------------------------------------------------- #
# Stubs                                                                       #
# --------------------------------------------------------------------------- #


@dataclass
class _DriftStub:
    in_sync: tuple[str, ...] = ()
    notion_newer: tuple[str, ...] = ()
    mirror_modified: tuple[str, ...] = ()
    orphan: tuple[str, ...] = ()
    missing_from_meta: tuple[str, ...] = ()

    @property
    def has_drift(self) -> bool:
        return bool(
            self.notion_newer
            or self.mirror_modified
            or self.orphan
            or self.missing_from_meta
        )


@dataclass
class _SyncStub:
    synced: tuple[str, ...] = ()
    failed: tuple[Any, ...] = ()
    duration_ms: int = 0


@dataclass
class _ConsistencyStub:
    ok: bool = True
    enums_checked: int = 13
    drifts: tuple[Any, ...] = ()


# --------------------------------------------------------------------------- #
# Tmp environment                                                             #
# --------------------------------------------------------------------------- #


@pytest.fixture
def integ_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Build a tmp env with all canonical paths repointed.

    Same shape as ``test_sequencer.py``'s ``tmp_env`` but exposed for
    integration-test composition.
    """
    cee_root = tmp_path / "cee"
    cee_root.mkdir()
    bible_dir = cee_root / "bible"
    bible_dir.mkdir()
    sync_meta = bible_dir / ".sync_meta.json"
    audit_dir = cee_root / "audit"
    audit_dir.mkdir()
    skills_dir = cee_root / "skills"
    skills_dir.mkdir()
    agents_dir = cee_root / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    runs_dir = cee_root / "runs"
    runs_dir.mkdir()
    schemas_dir = cee_root / "schemas"
    schemas_dir.mkdir()
    promotion_queue = cee_root / "promotion_queue.json"

    obsidian_vault = tmp_path / "SecondBrain" / "cee"
    obsidian_vault.mkdir(parents=True)

    user_cfg_dir = tmp_path / ".cee"
    user_cfg_dir.mkdir()
    config_file = user_cfg_dir / "config.toml"
    config_file.write_text(
        "[general]\n"
        "auto_sync = true\n"
        "fresh_boot = false\n"
        "[paths]\n"
        'cee_root = "~/cee"\n'
        'obsidian_vault = "~/SecondBrain"\n'
        'notion_bible_root_id = "352e8536-d882-8050-aff6-f1dbcff68a09"\n',
        encoding="utf-8",
    )

    for name, value in (
        ("CEE_ROOT", cee_root),
        ("BIBLE_DIR", bible_dir),
        ("BIBLE_SYNC_META", sync_meta),
        ("AUDIT_DIR", audit_dir),
        ("AUDIT_BOOT_LOG", audit_dir / "boot.log"),
        ("AUDIT_CLI_LOG", audit_dir / "cli.log"),
        ("AUDIT_ROLES_LOG", audit_dir / "roles.log"),
        ("AUDIT_SECURITY_LOG", audit_dir / "security.log"),
        ("AUDIT_ARCHIVE_DIR", audit_dir / "archive"),
        ("SKILLS_DIR", skills_dir),
        ("AGENTS_DIR", agents_dir),
        ("RUNS_DIR", runs_dir),
        ("SCHEMAS_DIR", schemas_dir),
        ("PROMOTION_QUEUE", promotion_queue),
        ("USER_CONFIG_DIR", user_cfg_dir),
        ("CONFIG_FILE", config_file),
        ("OBSIDIAN_VAULT", obsidian_vault),
    ):
        monkeypatch.setattr(paths, name, value)

    return {
        "cee_root": cee_root,
        "bible_dir": bible_dir,
        "sync_meta": sync_meta,
        "audit_dir": audit_dir,
        "boot_log": audit_dir / "boot.log",
        "config_file": config_file,
        "promotion_queue": promotion_queue,
        "runs_dir": runs_dir,
    }


def _factories(**overrides: Any) -> dict[str, Callable[..., Any]]:
    """Default factories that all succeed; override by name."""
    base = {
        "bible_drift_factory": lambda **_: _DriftStub(in_sync=("00_a", "01_b")),
        "bible_sync_factory": lambda **_: _SyncStub(synced=("00_a",)),
        "consistency_factory": lambda **_: _ConsistencyStub(),
        "skill_rebuild_factory": lambda _p: [{"id": "s1"}],
        "agent_rebuild_factory": lambda _p: [{"id": "a1"}],
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #


def test_synthetic_happy_path_completes_b1_through_b9(
    integ_env: dict[str, Path]
) -> None:
    """Bible 20 §5.2 Phase 2 gate: B1–B9 from a clean state."""
    br = run(**_factories())
    assert isinstance(br, BootResult)
    assert br.ok is True
    assert br.halt_step is None
    assert tuple(s.step for s in br.steps) == (
        "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"
    )


def test_synthetic_halt_at_b3_on_enum_drift(integ_env: dict[str, Path]) -> None:
    """Bible 20 §5.2 gate: cross-section consistency check rejects
    a deliberately-introduced enum mismatch."""
    factories = _factories(
        consistency_factory=lambda **_: _ConsistencyStub(ok=False, drifts=(object(),))
    )
    br = run(**factories)
    assert br.ok is False
    assert br.halt_step == "B3"
    assert isinstance(br.halt_error, BootConsistencyError)


def test_synthetic_halt_at_b2_with_auto_sync_disabled(
    integ_env: dict[str, Path]
) -> None:
    """auto_sync = false + drift detected → halt with new kind."""
    integ_env["config_file"].write_text(
        "[general]\nauto_sync = false\n"
        "[paths]\nnotion_bible_root_id = \"352e8536-d882-8050-aff6-f1dbcff68a09\"\n",
        encoding="utf-8",
    )
    factories = _factories(
        bible_drift_factory=lambda **_: _DriftStub(notion_newer=("02_x",))
    )
    br = run(**factories)
    assert br.ok is False
    assert br.halt_step == "B2"
    assert isinstance(br.halt_error, BootBibleSyncError)
    assert br.halt_error.kind == "auto_sync_disabled"


def test_synthetic_b8_warning_when_queue_present_no_writer(
    integ_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Queue present + drain transport unavailable -> warning, not halt.

    Phase 3 T5 ships persistence.notion_writer.drain per bible 07 §11
    line 411; T6's stub raises NotImplementedError on connect(),
    surfacing as DrainResult.transport_unavailable=True. B8 emits a
    warning but boot continues.

    (Originally tested the now-dead 'writer_pending' branch; T5 makes
    that branch unreachable. Migrated to the new equivalent.)
    """
    # Rebuild filesystem_writer._ALLOWED_WRITES so NOTION_WRITER can
    # target the temp PROMOTION_QUEUE path. T5's drain persists the
    # queue after marking entries with last_error.
    from persistence import filesystem_writer

    monkeypatch.setattr(
        filesystem_writer,
        "_ALLOWED_WRITES",
        filesystem_writer._rebuild_allowed_writes(),
    )

    # Seed one queued entry so drain has something to mark.
    integ_env["promotion_queue"].write_text(
        '{"schema_version":"1.0.0","produced_by":"NOTION_WRITER",'
        '"last_updated":"2026-01-01T00:00:00Z",'
        '"entries":[{"slug":"x","kind":"skill","status":"queued",'
        '"enqueued_at":"2026-01-01T00:00:00Z","payload_path":"/tmp/x.md"}]}',
        encoding="utf-8",
    )

    br = run(**_factories())
    assert br.ok is True
    assert any("transport unavailable" in w for w in br.warnings)


def test_idempotent_consecutive_boots_chain_intact(
    integ_env: dict[str, Path]
) -> None:
    """Two clean boots in sequence — audit chain stays intact."""
    from persistence.audit import verify_audit_chain

    factories = _factories()
    br1 = run(**factories)
    br2 = run(**factories)
    assert br1.ok is True
    assert br2.ok is True
    ok, broken = verify_audit_chain(integ_env["boot_log"])
    assert ok is True
    assert broken == []


def test_run_with_real_runs_dir_indexes_zero(integ_env: dict[str, Path]) -> None:
    """B7 against an empty runs dir produces a 0-entry index."""
    br = run(**_factories())
    b7 = next(s for s in br.steps if s.step == "B7")
    assert b7.payload["runs_indexed"] == 0


def test_smoke_real_substrate_halts_or_succeeds_gracefully() -> None:
    """Smoke against the real ``~/cee`` + ``~/.cee`` substrate.

    Per T8 acceptance criterion #5: the boot sequencer must produce a
    documented graceful outcome, not a Python traceback. Two
    acceptable outcomes given current state:

    * Halt at B2 with ``BootBibleSyncError(kind="credentials_missing")``
      — current state has ``~/.cee/credentials.toml`` missing, the
      bible mirror present but ``.sync_meta.json`` in legacy shape
      (treated by T6 as "first sync — re-sync everything"), and
      ``auto_sync = true``. So B2's ``check_drift()`` reads
      credentials → halts on ``credentials_missing``.
    * Halt at B2 with ``BootBibleSyncError(kind="mcp_connect_failed")``
      — same path but credentials present and the Notion MCP
      transport unreachable.
    * Clean B1–B9 success — only when the bible mirror fully matches
      ``.sync_meta.json`` (canonical shape) and B1 passes. Unlikely
      in current state.

    What MUST NOT happen: a raw Python exception escapes ``run()``.
    """
    # Run with NO factory overrides — production paths.
    br = run()
    assert isinstance(br, BootResult)

    if br.ok:
        # Clean boot — all 9 steps, no warnings of fatal kind.
        assert br.halt_step is None
        assert br.halt_error is None
        assert tuple(s.step for s in br.steps) == (
            "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"
        )
    else:
        # Halt path — must be a typed BootError, never a raw Exception.
        assert br.halt_step is not None
        assert isinstance(br.halt_error, BootError)
        # Documented expected halt steps in current state: B1 (env)
        # or B2 (bible). Anything else suggests substrate has drifted
        # in a way the smoke test should surface, not silently accept.
        assert br.halt_step in {"B1", "B2"}, (
            f"unexpected halt at {br.halt_step}: {br.halt_error}"
        )
