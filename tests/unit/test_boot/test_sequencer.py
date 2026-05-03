"""Unit tests for ``boot.sequencer`` — orchestration via injection.

Per T8 Step 3 design: tests inject factories so the orchestration
layer is exercised without re-running real registry rebuilds /
consistency walks / Notion MCP transports. Tests fall into seven
groups:

* Per-step happy + halt paths for B1–B7.
* B8 best-effort behavior (queue absent / writer pending / drain
  fails — never halts).
* B9 + lifecycle envelope (boot_start / boot_complete / boot_halted).
* Halt-propagation: every B1–B7 halt produces ``BootResult.ok=False``,
  ``halt_step`` set, no exception escapes ``run()``.
* ``BootResult`` / ``BootStepResult`` shape: frozen dataclass,
  Literal step type, payload immutable, tuple semantics.
* Audit emissions: every step emits start + complete (or failed) to
  boot.log; lifecycle events wrap the per-step events.
* End-to-end synthetic happy path with all factories injected.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

import paths
from boot import sequencer
from boot.sequencer import (
    BootContext,
    BootResult,
    BootStepResult,
    run,
)
from errors import (
    BootBibleSyncError,
    BootConsistencyError,
    BootEnvironmentError,
    BootError,
    BootRegistryError,
    BootRunIndexError,
    BootSchemaError,
)


# --------------------------------------------------------------------------- #
# Test fixtures                                                               #
# --------------------------------------------------------------------------- #


@dataclass
class _StubDriftReport:
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
class _StubSyncResult:
    synced: tuple[str, ...] = ()
    failed: tuple[Any, ...] = ()
    duration_ms: int = 0


@dataclass
class _StubConsistencyReport:
    ok: bool = True
    enums_checked: int = 13
    drifts: tuple[Any, ...] = ()


@pytest.fixture
def tmp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Build a tmp environment with all canonical paths repointed.

    Pre-populates ``~/.cee/config.toml`` with valid Phase 2 contents
    (auto_sync defaults to ``true``); credentials.toml is intentionally
    NOT created — boot.sequencer.B1 doesn't read it (strict canon per
    AB Q1) and individual tests provision it when their B2 path
    requires sync().
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
    # Minimal valid Phase 2 config — auto_sync true so B2 default
    # path (drift → sync) is the more interesting one to exercise.
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

    monkeypatch.setattr(paths, "CEE_ROOT", cee_root)
    monkeypatch.setattr(paths, "BIBLE_DIR", bible_dir)
    monkeypatch.setattr(paths, "BIBLE_SYNC_META", sync_meta)
    monkeypatch.setattr(paths, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(paths, "AUDIT_BOOT_LOG", audit_dir / "boot.log")
    monkeypatch.setattr(paths, "AUDIT_CLI_LOG", audit_dir / "cli.log")
    monkeypatch.setattr(paths, "AUDIT_ROLES_LOG", audit_dir / "roles.log")
    monkeypatch.setattr(paths, "AUDIT_SECURITY_LOG", audit_dir / "security.log")
    monkeypatch.setattr(paths, "AUDIT_ARCHIVE_DIR", audit_dir / "archive")
    monkeypatch.setattr(paths, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(paths, "AGENTS_DIR", agents_dir)
    monkeypatch.setattr(paths, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(paths, "SCHEMAS_DIR", schemas_dir)
    monkeypatch.setattr(paths, "PROMOTION_QUEUE", promotion_queue)
    monkeypatch.setattr(paths, "USER_CONFIG_DIR", user_cfg_dir)
    monkeypatch.setattr(paths, "CONFIG_FILE", config_file)
    monkeypatch.setattr(paths, "OBSIDIAN_VAULT", obsidian_vault)

    return {
        "cee_root": cee_root,
        "bible_dir": bible_dir,
        "sync_meta": sync_meta,
        "audit_dir": audit_dir,
        "boot_log": audit_dir / "boot.log",
        "skills_dir": skills_dir,
        "agents_dir": agents_dir,
        "runs_dir": runs_dir,
        "schemas_dir": schemas_dir,
        "promotion_queue": promotion_queue,
        "config_file": config_file,
        "obsidian_vault": obsidian_vault,
    }


def _ok_factories() -> dict[str, Callable[..., Any]]:
    """Return a dict of factories that all succeed cleanly.

    Suitable as a baseline; individual tests override one or two
    keys to exercise the failure paths.
    """
    return {
        "bible_drift_factory": lambda **_: _StubDriftReport(in_sync=("00_a", "01_b")),
        "bible_sync_factory": lambda **_: _StubSyncResult(synced=("00_a",)),
        "consistency_factory": lambda **_: _StubConsistencyReport(),
        "skill_rebuild_factory": lambda _p: [{"id": "s1"}, {"id": "s2"}],
        "agent_rebuild_factory": lambda _p: [{"id": "a1"}],
    }


def _audit_lines(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _events(log_path: Path) -> list[str]:
    return [e["event"] for e in _audit_lines(log_path)]


# --------------------------------------------------------------------------- #
# BootStepResult / BootResult shape                                           #
# --------------------------------------------------------------------------- #


def test_boot_step_result_is_frozen() -> None:
    r = BootStepResult(step="B1", ok=True, duration_ms=10, summary="ok", payload={})
    with pytest.raises(FrozenInstanceError):
        r.ok = False  # type: ignore[misc]


def test_boot_step_result_payload_is_immutable() -> None:
    r = BootStepResult(
        step="B1", ok=True, duration_ms=0, summary="ok", payload={"a": 1}
    )
    assert isinstance(r.payload, MappingProxyType)
    with pytest.raises(TypeError):
        r.payload["a"] = 2  # type: ignore[index]


def test_boot_step_result_payload_round_trip_dict_to_proxy() -> None:
    src = {"key": "val", "nested": [1, 2, 3]}
    r = BootStepResult(
        step="B6", ok=True, duration_ms=0, summary="ok", payload=src
    )
    # Mutating the original dict must not affect the result.
    src["key"] = "mutated"
    assert r.payload["key"] == "val"


def test_boot_step_name_literal_accepts_b1_through_b9() -> None:
    for step in ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"):
        r = BootStepResult(
            step=step,  # type: ignore[arg-type]
            ok=True,
            duration_ms=0,
            summary="x",
            payload={},
        )
        assert r.step == step


def test_boot_result_is_frozen() -> None:
    br = BootResult(
        ok=True, steps=(), halt_step=None, halt_error=None,
        warnings=(), total_duration_ms=0,
    )
    with pytest.raises(FrozenInstanceError):
        br.ok = False  # type: ignore[misc]


def test_boot_result_steps_is_tuple() -> None:
    s1 = BootStepResult(
        step="B1", ok=True, duration_ms=1, summary="x", payload={}
    )
    br = BootResult(
        ok=True, steps=(s1,), halt_step=None, halt_error=None,
        warnings=("w",), total_duration_ms=10,
    )
    assert isinstance(br.steps, tuple)
    assert isinstance(br.warnings, tuple)


# --------------------------------------------------------------------------- #
# B1 — environment                                                            #
# --------------------------------------------------------------------------- #


def test_b1_happy_path(tmp_env: dict[str, Path]) -> None:
    """Canonical clean env yields a valid BootContext + step result."""
    result, ctx = sequencer._run_b1(
        config_path=None,
        bible_root=None,
        sync_meta_path=None,
        skills_dir=None,
        agents_dir=None,
        schemas_dir=None,
        runs_dir=None,
        promotion_queue_path=None,
    )
    assert result.step == "B1"
    assert result.ok is True
    assert result.duration_ms >= 0
    assert ctx.bible_root == tmp_env["bible_dir"]
    assert ctx.skills_dir == tmp_env["skills_dir"]
    assert ctx.auto_sync is True


def test_b1_python_version_check_uses_running_interpreter(
    tmp_env: dict[str, Path],
) -> None:
    """B1 records the running Python version in its payload."""
    import sys

    result, _ = sequencer._run_b1(
        config_path=None, bible_root=None, sync_meta_path=None,
        skills_dir=None, agents_dir=None, schemas_dir=None,
        runs_dir=None, promotion_queue_path=None,
    )
    expected = ".".join(str(x) for x in sys.version_info[:3])
    assert result.payload["python_version"] == expected


def test_b1_halts_on_python_too_old(
    tmp_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the floor moves above the running Python, B1 halts."""
    monkeypatch.setattr(sequencer, "_B1_PYTHON_FLOOR", (99, 0))
    with pytest.raises(BootEnvironmentError) as exc_info:
        sequencer._run_b1(
            config_path=None, bible_root=None, sync_meta_path=None,
            skills_dir=None, agents_dir=None, schemas_dir=None,
            runs_dir=None, promotion_queue_path=None,
        )
    assert exc_info.value.kind == "python_version"
    assert exc_info.value.step == "B1"


def test_b1_halts_on_missing_package(
    tmp_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sequencer, "_B1_REQUIRED_MODULES", ("paths", "definitely_not_a_real_pkg_xyz")
    )
    with pytest.raises(BootEnvironmentError) as exc_info:
        sequencer._run_b1(
            config_path=None, bible_root=None, sync_meta_path=None,
            skills_dir=None, agents_dir=None, schemas_dir=None,
            runs_dir=None, promotion_queue_path=None,
        )
    assert exc_info.value.kind == "missing_package"
    assert "definitely_not_a_real_pkg_xyz" in str(exc_info.value.detail["missing"])


def test_b1_halts_when_obsidian_vault_missing(
    tmp_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bible 02 §7.13 lists the Obsidian vault root in BOOT_SEQUENCER's
    allowed_writes. Missing root halts B1."""
    nonexistent = tmp_env["cee_root"].parent / "DoesNotExist" / "cee"
    monkeypatch.setattr(paths, "OBSIDIAN_VAULT", nonexistent)
    with pytest.raises(BootEnvironmentError) as exc_info:
        sequencer._run_b1(
            config_path=None, bible_root=None, sync_meta_path=None,
            skills_dir=None, agents_dir=None, schemas_dir=None,
            runs_dir=None, promotion_queue_path=None,
        )
    assert exc_info.value.kind == "path_not_writable"


def test_b1_halts_when_config_missing(
    tmp_env: dict[str, Path]
) -> None:
    tmp_env["config_file"].unlink()
    with pytest.raises(BootEnvironmentError) as exc_info:
        sequencer._run_b1(
            config_path=None, bible_root=None, sync_meta_path=None,
            skills_dir=None, agents_dir=None, schemas_dir=None,
            runs_dir=None, promotion_queue_path=None,
        )
    assert exc_info.value.kind == "config_invalid"


def test_b1_halts_when_config_invalid(
    tmp_env: dict[str, Path]
) -> None:
    tmp_env["config_file"].write_text("not valid toml [[[", encoding="utf-8")
    with pytest.raises(BootEnvironmentError) as exc_info:
        sequencer._run_b1(
            config_path=None, bible_root=None, sync_meta_path=None,
            skills_dir=None, agents_dir=None, schemas_dir=None,
            runs_dir=None, promotion_queue_path=None,
        )
    assert exc_info.value.kind == "config_invalid"


def test_b1_path_writable_helper_rejects_nonexistent(tmp_path: Path) -> None:
    assert sequencer._path_writable(tmp_path / "nope") is False


def test_b1_path_writable_helper_accepts_writable_dir(tmp_path: Path) -> None:
    assert sequencer._path_writable(tmp_path) is True


# --------------------------------------------------------------------------- #
# B2 — bible load + drift handling                                            #
# --------------------------------------------------------------------------- #


def _b1_ctx(tmp_env: dict[str, Path], auto_sync: bool = True) -> BootContext:
    """Minimal BootContext for direct B2-B8 invocation."""
    if not auto_sync:
        tmp_env["config_file"].write_text(
            "[general]\nauto_sync = false\n"
            "[paths]\nnotion_bible_root_id = \"352e8536-d882-8050-aff6-f1dbcff68a09\"\n",
            encoding="utf-8",
        )
    result, ctx = sequencer._run_b1(
        config_path=None, bible_root=None, sync_meta_path=None,
        skills_dir=None, agents_dir=None, schemas_dir=None,
        runs_dir=None, promotion_queue_path=None,
    )
    return ctx


def test_b2_no_drift_continues(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    drift_factory = lambda **_: _StubDriftReport(in_sync=("00_a", "01_b"))
    result, warnings = sequencer._run_b2(
        ctx, drift_factory=drift_factory, sync_factory=None
    )
    assert result.ok is True
    assert result.payload["drift"] == "in_sync"
    assert result.payload["in_sync_count"] == 2
    assert warnings == []


def test_b2_drift_with_auto_sync_true_invokes_sync(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    sync_called: list[dict[str, Any]] = []

    def drift_factory(**_: Any) -> _StubDriftReport:
        return _StubDriftReport(notion_newer=("02_x",))

    def sync_factory(**kwargs: Any) -> _StubSyncResult:
        sync_called.append(kwargs)
        return _StubSyncResult(synced=("02_x",), duration_ms=42)

    result, warnings = sequencer._run_b2(
        ctx, drift_factory=drift_factory, sync_factory=sync_factory
    )
    assert result.ok is True
    assert result.payload["drift"] == "synced"
    assert result.payload["synced_count"] == 1
    assert len(sync_called) == 1
    assert sync_called[0]["trigger"] == "boot_auto"


def test_b2_drift_with_auto_sync_false_halts_with_new_kind(
    tmp_env: dict[str, Path],
) -> None:
    ctx = _b1_ctx(tmp_env, auto_sync=False)
    drift_factory = lambda **_: _StubDriftReport(notion_newer=("02_x",))
    with pytest.raises(BootBibleSyncError) as exc_info:
        sequencer._run_b2(ctx, drift_factory=drift_factory, sync_factory=None)
    assert exc_info.value.kind == "auto_sync_disabled"
    assert exc_info.value.step == "B2"


def test_b2_credentials_missing_propagates_from_check_drift(
    tmp_env: dict[str, Path],
) -> None:
    ctx = _b1_ctx(tmp_env)

    def raising_drift(**_: Any) -> _StubDriftReport:
        raise BootBibleSyncError(
            kind="credentials_missing", reason="missing api_key"
        )

    with pytest.raises(BootBibleSyncError) as exc_info:
        sequencer._run_b2(ctx, drift_factory=raising_drift, sync_factory=None)
    assert exc_info.value.kind == "credentials_missing"


def test_b2_mcp_connect_failed_propagates(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)

    def raising_drift(**_: Any) -> _StubDriftReport:
        raise BootBibleSyncError(kind="mcp_connect_failed", reason="net down")

    with pytest.raises(BootBibleSyncError) as exc_info:
        sequencer._run_b2(ctx, drift_factory=raising_drift, sync_factory=None)
    assert exc_info.value.kind == "mcp_connect_failed"


def test_b2_partial_sync_failures_become_warnings(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    drift_factory = lambda **_: _StubDriftReport(notion_newer=("02_x", "03_y"))
    sync_factory = lambda **_: _StubSyncResult(
        synced=("02_x",), failed=("03_y",), duration_ms=10
    )
    result, warnings = sequencer._run_b2(
        ctx, drift_factory=drift_factory, sync_factory=sync_factory
    )
    assert result.ok is True
    assert result.payload["failed_count"] == 1
    assert any("failed to sync" in w for w in warnings)


def test_b2_mirror_modified_is_warning_not_halt(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    drift_factory = lambda **_: _StubDriftReport(
        in_sync=("00_a",), mirror_modified=("01_b",)
    )
    # mirror_modified counts as drift via has_drift; auto_sync=true
    # so sync runs.
    sync_factory = lambda **_: _StubSyncResult(synced=("01_b",))
    result, warnings = sequencer._run_b2(
        ctx, drift_factory=drift_factory, sync_factory=sync_factory
    )
    assert result.ok is True
    assert any("mirror-modified" in w for w in warnings)


# --------------------------------------------------------------------------- #
# B3 — consistency                                                            #
# --------------------------------------------------------------------------- #


def test_b3_happy_path(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    factory = lambda **_: _StubConsistencyReport(ok=True, enums_checked=13)
    result, warnings = sequencer._run_b3(ctx, factory=factory)
    assert result.ok is True
    assert result.payload["enums_checked"] == 13
    assert warnings == []


def test_b3_halts_on_drift(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    drift_record = type("DR", (), {})()
    factory = lambda **_: _StubConsistencyReport(
        ok=False, enums_checked=13, drifts=(drift_record,)
    )
    with pytest.raises(BootConsistencyError) as exc_info:
        sequencer._run_b3(ctx, factory=factory)
    assert exc_info.value.step == "B3"
    assert len(exc_info.value.drifts) == 1


# --------------------------------------------------------------------------- #
# B4 — skill registry                                                         #
# --------------------------------------------------------------------------- #


def test_b4_happy_path(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    factory = lambda _p: [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}]
    result, warnings = sequencer._run_b4(ctx, factory=factory)
    assert result.ok is True
    assert result.payload["indexed_count"] == 3
    assert result.payload["kind"] == "skill"


def test_b4_halts_on_oserror(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)

    def factory(_p: Path) -> list:
        raise PermissionError("denied")

    with pytest.raises(BootRegistryError) as exc_info:
        sequencer._run_b4(ctx, factory=factory)
    assert exc_info.value.kind == "skill"
    assert exc_info.value.step == "B4"


def test_b4_per_entry_skip_does_not_halt(tmp_env: dict[str, Path]) -> None:
    """Per T3 spec, per-entry parse failures are absorbed inside
    rebuild() — they produce a shorter list, not an exception."""
    ctx = _b1_ctx(tmp_env)
    factory = lambda _p: [{"id": "only_one"}]  # 4 candidates, 3 skipped
    result, _ = sequencer._run_b4(ctx, factory=factory)
    assert result.ok is True


# --------------------------------------------------------------------------- #
# B5 — agent registry                                                         #
# --------------------------------------------------------------------------- #


def test_b5_happy_path(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    factory = lambda _p: [{"id": "a1"}]
    result, warnings = sequencer._run_b5(ctx, factory=factory)
    assert result.ok is True
    assert result.payload["indexed_count"] == 1
    assert result.payload["kind"] == "agent"


def test_b5_halts_on_oserror(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)

    def factory(_p: Path) -> list:
        raise OSError("permission denied")

    with pytest.raises(BootRegistryError) as exc_info:
        sequencer._run_b5(ctx, factory=factory)
    assert exc_info.value.kind == "agent"
    assert exc_info.value.step == "B5"


# --------------------------------------------------------------------------- #
# B6 — schemas                                                                #
# --------------------------------------------------------------------------- #


def test_b6_compiles_all_schema_modules(tmp_env: dict[str, Path]) -> None:
    """B6 against the real schemas/ package compiles all modules."""
    ctx = _b1_ctx(tmp_env)
    result, warnings = sequencer._run_b6(ctx)
    assert result.ok is True
    assert result.payload["schemas_compiled"] >= 17
    assert "intent_object" in result.payload["modules"]


def test_b6_halts_on_module_import_failure(
    tmp_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _b1_ctx(tmp_env)
    import importlib

    real_import = importlib.import_module

    def patched(name: str, *a: Any, **k: Any) -> Any:
        if name == "schemas.intent_object":
            raise SyntaxError("synthetic")
        return real_import(name, *a, **k)

    monkeypatch.setattr(sequencer.importlib, "import_module", patched)
    with pytest.raises(BootSchemaError) as exc_info:
        sequencer._run_b6(ctx)
    assert exc_info.value.module_name == "intent_object"
    assert exc_info.value.step == "B6"


# --------------------------------------------------------------------------- #
# B7 — runs index                                                             #
# --------------------------------------------------------------------------- #


def test_b7_empty_runs_dir_returns_empty_index(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    result, warnings = sequencer._run_b7(ctx)
    assert result.ok is True
    assert result.payload["runs_indexed"] == 0


def test_b7_missing_runs_dir_returns_empty_index(
    tmp_env: dict[str, Path]
) -> None:
    """Bible 04 §5.1 lists runs/ as canonical — but absence ≠ env
    failure (B1's job); B7 just produces an empty index."""
    ctx = _b1_ctx(tmp_env)
    # Replace runs dir with a path that doesn't exist.
    ctx2 = ctx._replace(runs_dir=tmp_env["cee_root"] / "no_runs_yet")
    result, warnings = sequencer._run_b7(ctx2)
    assert result.ok is True
    assert result.payload["runs_dir_present"] is False
    assert result.payload["runs_indexed"] == 0


def test_b7_excludes_golden_dir(tmp_env: dict[str, Path]) -> None:
    """Golden fixtures are not real Run logs."""
    ctx = _b1_ctx(tmp_env)
    (tmp_env["runs_dir"] / "golden").mkdir()
    result, _ = sequencer._run_b7(ctx)
    assert result.payload["runs_indexed"] == 0


def test_b7_indexes_run_directories(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    for name, goal in [("run_1700000000_aaa", "fix login"), ("run_1700000001_bbb", "add feature")]:
        d = tmp_env["runs_dir"] / name
        d.mkdir()
        (d / "intent_object.json").write_text(
            json.dumps({"goal": goal}), encoding="utf-8"
        )
    result, _ = sequencer._run_b7(ctx)
    assert result.payload["runs_indexed"] == 2


def test_b7_skips_runs_without_intent_object(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    (tmp_env["runs_dir"] / "run_1700_xx").mkdir()
    result, _ = sequencer._run_b7(ctx)
    assert result.payload["runs_indexed"] == 0
    assert result.payload["runs_skipped"] == 1


def test_b7_skips_malformed_intent_object(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    d = tmp_env["runs_dir"] / "run_1700_zz"
    d.mkdir()
    (d / "intent_object.json").write_text("not json", encoding="utf-8")
    result, _ = sequencer._run_b7(ctx)
    assert result.payload["runs_skipped"] == 1


def test_b7_halts_on_runs_dir_unreadable(
    tmp_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = _b1_ctx(tmp_env)

    def raising_iter(self: Path) -> Any:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "iterdir", raising_iter)
    with pytest.raises(BootRunIndexError) as exc_info:
        sequencer._run_b7(ctx)
    assert exc_info.value.step == "B7"


# --------------------------------------------------------------------------- #
# B8 — promotion queue (best-effort, never halts)                             #
# --------------------------------------------------------------------------- #


def test_b8_queue_not_found_returns_skipped(tmp_env: dict[str, Path]) -> None:
    ctx = _b1_ctx(tmp_env)
    result, warnings = sequencer._run_b8(ctx)
    assert result.ok is True
    assert result.payload["skipped"] == "queue_not_found"
    assert warnings == []


def test_b8_queue_present_drain_transport_unavailable_emits_warning(
    tmp_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 3 T5 ships drain(); current T6 stub raises NotImplementedError
    on connect(), surfacing as transport_unavailable=True in DrainResult.
    B8 emits warning + step ok stays True per AB Q2.

    (Previously tested the now-dead 'writer_pending' branch; T5 makes
    that branch unreachable since persistence.notion_writer is shipped.
    Migrated to the new equivalent: queue exists + drain reports
    transport unavailable.)
    """
    ctx = _b1_ctx(tmp_env)
    tmp_env["promotion_queue"].write_text("dummy", encoding="utf-8")

    from persistence import notion_writer as nw

    fake_result = nw.DrainResult(
        ok=False,
        attempted=("a", "b"),
        succeeded=(),
        failed=(("a", "transport_not_implemented"), ("b", "transport_not_implemented")),
        skipped=(),
        transport_unavailable=True,
    )
    monkeypatch.setattr("persistence.drain", lambda: fake_result)

    result, warnings = sequencer._run_b8(ctx)
    assert result.ok is True
    assert result.payload["transport_unavailable"] is True
    assert result.payload["attempted"] == ["a", "b"]
    assert result.payload["succeeded"] == []
    assert len(warnings) == 1
    assert "transport unavailable" in warnings[0]


def test_b8_drain_failure_does_not_halt(
    tmp_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defensive safety net: T5 contracts drain() never raises, but if
    it ever did, B8 must still not halt boot. Per AB Q2."""
    ctx = _b1_ctx(tmp_env)
    tmp_env["promotion_queue"].write_text("dummy", encoding="utf-8")

    def _raises() -> Any:
        raise RuntimeError("notion api down")

    monkeypatch.setattr("persistence.drain", _raises)

    result, warnings = sequencer._run_b8(ctx)
    # B8 reports ok=False on its own step (defensive raise path) but boot continues.
    assert result.payload["skipped"] == "drain_raised"
    assert any("notion api down" in w for w in warnings)


def test_b8_drain_success(
    tmp_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: drain returns DrainResult with succeeded entries;
    payload mirrors DrainResult fields."""
    ctx = _b1_ctx(tmp_env)
    tmp_env["promotion_queue"].write_text("dummy", encoding="utf-8")

    from persistence import notion_writer as nw

    fake_result = nw.DrainResult(
        ok=True,
        attempted=("skill_a", "skill_b", "skill_c"),
        succeeded=("skill_a", "skill_b", "skill_c"),
        failed=(),
        skipped=(),
        transport_unavailable=False,
    )
    monkeypatch.setattr("persistence.drain", lambda: fake_result)

    result, warnings = sequencer._run_b8(ctx)
    assert result.ok is True
    assert result.payload["ok"] is True
    assert result.payload["succeeded"] == ["skill_a", "skill_b", "skill_c"]
    assert result.payload["failed"] == []
    assert result.payload["transport_unavailable"] is False
    assert warnings == []


# --------------------------------------------------------------------------- #
# B9 + lifecycle envelope                                                     #
# --------------------------------------------------------------------------- #


def test_b9_returns_ready_signal() -> None:
    import time as _time

    started = _time.monotonic() - 0.1  # simulate 100ms of prior work
    result = sequencer._run_b9(started, [])
    assert result.step == "B9"
    assert result.ok is True
    assert result.payload["ready"] is True
    assert result.payload["total_duration_ms"] >= 0


# --------------------------------------------------------------------------- #
# End-to-end run() tests                                                      #
# --------------------------------------------------------------------------- #


def test_run_full_happy_path(tmp_env: dict[str, Path]) -> None:
    """All factories injected to succeed → BootResult.ok=True, 9 steps."""
    factories = _ok_factories()
    br = run(**factories)
    assert br.ok is True
    assert br.halt_step is None
    assert br.halt_error is None
    assert len(br.steps) == 9
    assert tuple(s.step for s in br.steps) == (
        "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"
    )
    assert br.total_duration_ms >= 0


def test_run_halts_at_b2_on_credentials_missing(tmp_env: dict[str, Path]) -> None:
    factories = _ok_factories()

    def raising_drift(**_: Any) -> _StubDriftReport:
        raise BootBibleSyncError(kind="credentials_missing", reason="no api_key")

    factories["bible_drift_factory"] = raising_drift
    br = run(**factories)
    assert br.ok is False
    assert br.halt_step == "B2"
    assert isinstance(br.halt_error, BootBibleSyncError)
    assert br.halt_error.kind == "credentials_missing"
    # B1 ran successfully + B2 is in the list with ok=False
    assert len(br.steps) == 2
    assert br.steps[0].step == "B1" and br.steps[0].ok is True
    assert br.steps[1].step == "B2" and br.steps[1].ok is False


def test_run_halts_at_b3_on_consistency_drift(tmp_env: dict[str, Path]) -> None:
    factories = _ok_factories()
    factories["consistency_factory"] = lambda **_: _StubConsistencyReport(
        ok=False, drifts=(object(),)
    )
    br = run(**factories)
    assert br.ok is False
    assert br.halt_step == "B3"
    assert isinstance(br.halt_error, BootConsistencyError)
    assert len(br.steps) == 3


def test_run_halts_at_b4_on_registry_failure(tmp_env: dict[str, Path]) -> None:
    factories = _ok_factories()

    def raising(_p: Path) -> list:
        raise OSError("disk full")

    factories["skill_rebuild_factory"] = raising
    br = run(**factories)
    assert br.ok is False
    assert br.halt_step == "B4"
    assert isinstance(br.halt_error, BootRegistryError)
    assert br.halt_error.kind == "skill"


def test_run_halts_at_b5_on_registry_failure(tmp_env: dict[str, Path]) -> None:
    factories = _ok_factories()

    def raising(_p: Path) -> list:
        raise PermissionError("no read")

    factories["agent_rebuild_factory"] = raising
    br = run(**factories)
    assert br.ok is False
    assert br.halt_step == "B5"
    assert isinstance(br.halt_error, BootRegistryError)
    assert br.halt_error.kind == "agent"


def test_run_halts_at_b6_on_schema_failure(
    tmp_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    factories = _ok_factories()
    import importlib

    real_import = importlib.import_module

    def patched(name: str, *a: Any, **k: Any) -> Any:
        if name == "schemas.config":
            raise ImportError("synthetic")
        return real_import(name, *a, **k)

    monkeypatch.setattr(sequencer.importlib, "import_module", patched)
    br = run(**factories)
    assert br.ok is False
    assert br.halt_step == "B6"
    assert isinstance(br.halt_error, BootSchemaError)
    assert br.halt_error.module_name == "config"


def test_run_b8_failure_does_not_set_ok_false(
    tmp_env: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Per AB Q2: B8 best-effort never halts boot.

    Defensive safety-net path — T5 contracts drain() never raises but
    if it ever did, boot continues with the warning surfaced."""
    factories = _ok_factories()
    tmp_env["promotion_queue"].write_text("dummy", encoding="utf-8")

    def _raises() -> Any:
        raise RuntimeError("notion outage")

    monkeypatch.setattr("persistence.drain", _raises)

    br = run(**factories)
    # Boot succeeds despite B8 failure.
    assert br.ok is True
    assert br.halt_step is None
    assert any("notion outage" in w for w in br.warnings)


def test_run_does_not_propagate_boot_error(tmp_env: dict[str, Path]) -> None:
    """Even on halt, run() returns BootResult, never raises BootError."""
    factories = _ok_factories()
    factories["consistency_factory"] = lambda **_: _StubConsistencyReport(
        ok=False, drifts=(object(),)
    )
    # No try/except — if run() raised, this test would fail.
    br = run(**factories)
    assert isinstance(br, BootResult)
    assert br.halt_error is not None


# --------------------------------------------------------------------------- #
# Audit emissions                                                             #
# --------------------------------------------------------------------------- #


def test_audit_full_happy_path_event_sequence(tmp_env: dict[str, Path]) -> None:
    factories = _ok_factories()
    run(**factories)
    events = _events(tmp_env["boot_log"])
    # Lifecycle envelope wraps step events.
    assert events[0] == "boot_start"
    assert events[-1] == "boot_complete"
    # Each B1-B9 step produces start + complete.
    for step in ("B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"):
        starts = [
            e for e in _audit_lines(tmp_env["boot_log"])
            if e["event"] == "boot_step_start" and e["details"]["step"] == step
        ]
        completes = [
            e for e in _audit_lines(tmp_env["boot_log"])
            if e["event"] == "boot_step_complete" and e["details"]["step"] == step
        ]
        assert len(starts) == 1, f"missing boot_step_start for {step}"
        assert len(completes) == 1, f"missing boot_step_complete for {step}"


def test_audit_halt_emits_step_failed_and_boot_halted(tmp_env: dict[str, Path]) -> None:
    factories = _ok_factories()
    factories["consistency_factory"] = lambda **_: _StubConsistencyReport(
        ok=False, drifts=(object(),)
    )
    run(**factories)
    events = _events(tmp_env["boot_log"])
    assert "boot_step_failed" in events
    assert "boot_halted" in events
    assert "boot_complete" not in events  # halt path bypasses complete


def test_audit_actor_is_boot_sequencer(tmp_env: dict[str, Path]) -> None:
    factories = _ok_factories()
    run(**factories)
    actors = {e["actor"] for e in _audit_lines(tmp_env["boot_log"])}
    assert actors == {"BOOT_SEQUENCER"}


def test_audit_b8_emits_warning_event_when_queue_present_no_writer(
    tmp_env: dict[str, Path],
) -> None:
    factories = _ok_factories()
    tmp_env["promotion_queue"].write_text("[]", encoding="utf-8")
    run(**factories)
    events = _events(tmp_env["boot_log"])
    assert "b8_promotion_drain_warning" in events


def test_audit_chain_intact_after_full_boot(tmp_env: dict[str, Path]) -> None:
    """Per bible 12 §10.6, verify_audit_chain returns (ok, broken).
    On a happy boot, ok is True and broken is empty; the actual
    entries live in the log file itself.
    """
    from persistence.audit import verify_audit_chain

    factories = _ok_factories()
    run(**factories)
    ok, broken = verify_audit_chain(tmp_env["boot_log"])
    assert ok is True
    assert broken == []
    # Expected: boot_start + 9 (step_start + step_complete) + boot_complete = 20.
    assert len(_audit_lines(tmp_env["boot_log"])) >= 20


# --------------------------------------------------------------------------- #
# Halt internals                                                              #
# --------------------------------------------------------------------------- #


def test_failed_step_records_class_and_kind() -> None:
    import time as _time

    exc = BootEnvironmentError(reason="too old", kind="python_version")
    started = _time.monotonic()
    result = sequencer._failed_step("B1", exc, started)
    assert result.step == "B1"
    assert result.ok is False
    assert result.payload["error_class"] == "BootEnvironmentError"
    assert result.payload["kind"] == "python_version"


def test_failed_step_records_module_name_for_schema_error() -> None:
    import time as _time

    exc = BootSchemaError(reason="bad", module_name="raw_input")
    result = sequencer._failed_step("B6", exc, _time.monotonic())
    assert result.payload["module_name"] == "raw_input"


def test_failed_step_records_no_kind_for_consistency_error() -> None:
    import time as _time

    exc = BootConsistencyError(drifts=[])
    result = sequencer._failed_step("B3", exc, _time.monotonic())
    # BootConsistencyError has no kind attribute — payload should not crash.
    assert "kind" not in result.payload
    assert result.payload["error_class"] == "BootConsistencyError"
