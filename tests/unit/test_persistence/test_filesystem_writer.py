"""Tests for persistence.filesystem_writer.

Per bible 02 §7 + bible 12 §5.8 + bible 20 §5.3. Each test fixtures a
clean ``paths.AUDIT_*`` set under ``tmp_path`` so audit emissions are
captured + verifiable in isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

import paths
from errors import RoleSurfaceViolation
from persistence import filesystem_write_json, filesystem_write_text
from persistence import filesystem_writer
from persistence.audit import scaffold_audit_logs
from roles import RoleEnum


_BIBLE_02_PATH = Path.home() / "cee" / "bible" / "02_user_roles.md"


@pytest.fixture
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every paths.* T3 touches into ``tmp_path``.

    Rebuilds ``filesystem_writer._ALLOWED_WRITES`` from the patched
    paths so the live map reflects the fixture. Scaffolds audit logs so
    ``audit_log_append`` has somewhere to write.
    """
    cee_root = tmp_path / "cee"
    obsidian_root = tmp_path / "SecondBrain" / "cee"

    overrides = {
        "CEE_ROOT": cee_root,
        "RUNS_DIR": cee_root / "runs",
        "SKILLS_DIR": cee_root / "skills",
        "AGENTS_DIR": cee_root / ".claude" / "agents",
        "BIBLE_DIR": cee_root / "bible",
        "BIBLE_SYNC_META": cee_root / "bible" / ".sync_meta.json",
        "AUDIT_DIR": cee_root / "audit",
        "AUDIT_ARCHIVE_DIR": cee_root / "audit" / "archive",
        "AUDIT_CLI_LOG": cee_root / "audit" / "cli.log",
        "AUDIT_ROLES_LOG": cee_root / "audit" / "roles.log",
        "AUDIT_BOOT_LOG": cee_root / "audit" / "boot.log",
        "AUDIT_SECURITY_LOG": cee_root / "audit" / "security.log",
        "PROMOTION_QUEUE": cee_root / "promotion_queue.json",
        "OBSIDIAN_VAULT": obsidian_root,
    }
    for name, value in overrides.items():
        monkeypatch.setattr(paths, name, value)

    monkeypatch.setattr(
        filesystem_writer,
        "_ALLOWED_WRITES",
        filesystem_writer._rebuild_allowed_writes(),
    )

    scaffold_audit_logs()
    return cee_root


def _read_roles_log(cee_root: Path) -> list[dict]:
    raw = (cee_root / "audit" / "roles.log").read_text(encoding="utf-8").strip()
    return [json.loads(line) for line in raw.split("\n") if line]


# --------------------------------------------------------------------------- #
# Allowed-writes positive tests (one per role in the map)                     #
# --------------------------------------------------------------------------- #


def test_persistence_writer_can_write_to_runs_dir(isolated_paths: Path) -> None:
    target = isolated_paths / "runs" / "run_001" / "intent.json"
    filesystem_write_json(RoleEnum.PERSISTENCE_WRITER, target, {"goal": "x"})
    assert json.loads(target.read_text()) == {"goal": "x"}


def test_persistence_writer_can_write_to_skills_dir(isolated_paths: Path) -> None:
    target = isolated_paths / "skills" / "my-skill" / "SKILL.md"
    filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "# Skill body")
    assert target.read_text() == "# Skill body"


def test_persistence_writer_can_write_to_agents_dir(isolated_paths: Path) -> None:
    target = isolated_paths / ".claude" / "agents" / "custom-agent.md"
    filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "agent body")
    assert target.read_text() == "agent body"


def test_obsidian_writer_can_write_to_obsidian_vault(
    isolated_paths: Path,
) -> None:
    target = paths.OBSIDIAN_VAULT / "runs" / "run_001.md"
    filesystem_write_text(RoleEnum.OBSIDIAN_WRITER, target, "# Run note")
    assert target.read_text() == "# Run note"


def test_notion_writer_can_write_promotion_queue(isolated_paths: Path) -> None:
    target = paths.PROMOTION_QUEUE
    filesystem_write_json(RoleEnum.NOTION_WRITER, target, {"entries": []})
    assert json.loads(target.read_text()) == {"entries": []}


def test_boot_sequencer_can_write_to_bible_dir(isolated_paths: Path) -> None:
    target = isolated_paths / "bible" / "00_project_vision.md"
    filesystem_write_text(RoleEnum.BOOT_SEQUENCER, target, "# Bible page")
    assert target.read_text() == "# Bible page"


def test_boot_sequencer_can_write_sync_meta(isolated_paths: Path) -> None:
    target = paths.BIBLE_SYNC_META
    filesystem_write_json(RoleEnum.BOOT_SEQUENCER, target, {"pages": {}})
    assert json.loads(target.read_text()) == {"pages": {}}


def test_boot_sequencer_can_write_skills_index(isolated_paths: Path) -> None:
    target = isolated_paths / "skills" / "index.json"
    filesystem_write_json(RoleEnum.BOOT_SEQUENCER, target, [])
    assert json.loads(target.read_text()) == []


def test_boot_sequencer_can_write_agents_index(isolated_paths: Path) -> None:
    target = isolated_paths / ".claude" / "agents" / "index.json"
    filesystem_write_json(RoleEnum.BOOT_SEQUENCER, target, [])
    assert json.loads(target.read_text()) == []


def test_boot_sequencer_can_write_boot_log(isolated_paths: Path) -> None:
    # Direct write of the boot.log target itself; smoke that the path
    # is in the allowed roots. (Audit infrastructure uses
    # audit_log_append for actual append semantics; this just proves
    # role authority over the path.)
    target = paths.AUDIT_BOOT_LOG
    filesystem_write_text(RoleEnum.BOOT_SEQUENCER, target, "boot ok\n")
    assert "boot ok" in target.read_text()


def test_pipeline_driver_can_write_to_runs_dir(isolated_paths: Path) -> None:
    target = isolated_paths / "runs" / "run_001" / "run_summary.json"
    filesystem_write_json(RoleEnum.PIPELINE_DRIVER, target, {"status": "ok"})
    assert json.loads(target.read_text()) == {"status": "ok"}


def test_safety_gate_can_write_to_runs_dir(isolated_paths: Path) -> None:
    target = isolated_paths / "runs" / "run_001" / "safety_log.json"
    filesystem_write_json(RoleEnum.SAFETY_GATE, target, {"flags": []})
    assert json.loads(target.read_text()) == {"flags": []}


def test_safety_gate_can_write_security_log(isolated_paths: Path) -> None:
    target = paths.AUDIT_SECURITY_LOG
    filesystem_write_text(RoleEnum.SAFETY_GATE, target, "security note\n")
    assert "security note" in target.read_text()


# --------------------------------------------------------------------------- #
# Roles excluded from the map — every write denied                            #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "role",
    [
        RoleEnum.INTERPRETER,
        RoleEnum.OPERATOR,
        RoleEnum.EXECUTOR,
        RoleEnum.BIBLE_LOADER,
    ],
)
def test_role_with_no_filesystem_surface_cannot_write(
    isolated_paths: Path, role: RoleEnum
) -> None:
    target = isolated_paths / "runs" / "run_001" / "anything.json"
    with pytest.raises(RoleSurfaceViolation, match="no filesystem write surface"):
        filesystem_write_json(role, target, {})


# --------------------------------------------------------------------------- #
# Cross-role denial — role can write somewhere but not the requested path     #
# --------------------------------------------------------------------------- #


def test_obsidian_writer_cannot_write_to_runs_dir(isolated_paths: Path) -> None:
    target = isolated_paths / "runs" / "run_001" / "x.json"
    with pytest.raises(RoleSurfaceViolation, match="not authorised"):
        filesystem_write_json(RoleEnum.OBSIDIAN_WRITER, target, {})


def test_persistence_writer_cannot_write_to_obsidian_vault(
    isolated_paths: Path,
) -> None:
    target = paths.OBSIDIAN_VAULT / "runs" / "run_001.md"
    with pytest.raises(RoleSurfaceViolation, match="not authorised"):
        filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "x")


def test_persistence_writer_cannot_write_to_bible_dir(
    isolated_paths: Path,
) -> None:
    target = isolated_paths / "bible" / "00_project_vision.md"
    with pytest.raises(RoleSurfaceViolation, match="not authorised"):
        filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "x")


def test_notion_writer_cannot_write_to_runs_dir(isolated_paths: Path) -> None:
    target = isolated_paths / "runs" / "run_001" / "x.json"
    with pytest.raises(RoleSurfaceViolation, match="not authorised"):
        filesystem_write_json(RoleEnum.NOTION_WRITER, target, {})


def test_boot_sequencer_cannot_write_to_obsidian_vault(
    isolated_paths: Path,
) -> None:
    target = paths.OBSIDIAN_VAULT / "anything.md"
    with pytest.raises(RoleSurfaceViolation, match="not authorised"):
        filesystem_write_text(RoleEnum.BOOT_SEQUENCER, target, "x")


# --------------------------------------------------------------------------- #
# Path-prefix edge cases                                                      #
# --------------------------------------------------------------------------- #


def test_write_to_subdirectory_of_allowed_root_succeeds(
    isolated_paths: Path,
) -> None:
    """A nested path under an allowed root is accepted."""
    target = isolated_paths / "runs" / "run_001" / "step_3" / "intent.json"
    filesystem_write_json(RoleEnum.PERSISTENCE_WRITER, target, {"x": 1})
    assert json.loads(target.read_text()) == {"x": 1}


def test_write_to_parent_of_allowed_root_denied(isolated_paths: Path) -> None:
    """PERSISTENCE_WRITER cannot escape upward — CEE_ROOT is above
    its allowed roots.
    """
    target = isolated_paths / "stray.json"
    with pytest.raises(RoleSurfaceViolation, match="not authorised"):
        filesystem_write_json(RoleEnum.PERSISTENCE_WRITER, target, {})


def test_write_to_sibling_of_allowed_root_denied(isolated_paths: Path) -> None:
    """RUNS_DIR is allowed; a sibling like /tmp/.../cee/prompts is not."""
    target = isolated_paths / "prompts" / "intruder.txt"
    with pytest.raises(RoleSurfaceViolation, match="not authorised"):
        filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "x")


def test_path_traversal_rejected(isolated_paths: Path) -> None:
    """A path containing ``..`` segments resolves before authority
    check, so traversal escape is caught.
    """
    target = isolated_paths / "runs" / ".." / "bible" / "00_project_vision.md"
    with pytest.raises(RoleSurfaceViolation, match="not authorised"):
        filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "x")


def test_relative_path_resolved_before_authority_check(
    isolated_paths: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relative path is resolved against cwd; if cwd is the allowed
    root, the relative path resolves underneath and is accepted.
    """
    runs_dir = isolated_paths / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(runs_dir)
    target = Path("run_001") / "intent.json"
    filesystem_write_json(RoleEnum.PERSISTENCE_WRITER, target, {"x": 1})
    assert (runs_dir / "run_001" / "intent.json").exists()


# --------------------------------------------------------------------------- #
# Atomicity invariants (delegation to persistence.atomic)                     #
# --------------------------------------------------------------------------- #


def test_write_text_overwrites_atomically(isolated_paths: Path) -> None:
    target = isolated_paths / "runs" / "run_001" / "x.json"
    filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "first")
    filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "second")
    assert target.read_text() == "second"


def test_write_text_atomic_no_partial_on_failure(isolated_paths: Path) -> None:
    """Make atomic_write_text raise mid-write; assert no partial file
    is left at the target path.
    """
    target = isolated_paths / "runs" / "run_001" / "x.txt"

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    with patch("persistence.filesystem_writer.atomic_write_text", side_effect=_boom):
        with pytest.raises(OSError, match="disk full"):
            filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "x")

    assert not target.exists()


def test_write_json_atomic_no_partial_on_failure(isolated_paths: Path) -> None:
    target = isolated_paths / "runs" / "run_001" / "x.json"

    def _boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    with patch("persistence.filesystem_writer.atomic_write_json", side_effect=_boom):
        with pytest.raises(OSError, match="disk full"):
            filesystem_write_json(RoleEnum.PERSISTENCE_WRITER, target, {})

    assert not target.exists()


# --------------------------------------------------------------------------- #
# Audit emission policy (denial-only per AB Step-3 adjustment)                #
# --------------------------------------------------------------------------- #


def test_successful_write_does_not_emit_audit_event(
    isolated_paths: Path,
) -> None:
    """Per AB-locked policy, success-path writes do NOT audit."""
    target = isolated_paths / "runs" / "run_001" / "x.json"
    filesystem_write_json(RoleEnum.PERSISTENCE_WRITER, target, {})
    entries = _read_roles_log(isolated_paths)
    assert entries == [], (
        f"successful write must not emit; got {len(entries)} entries"
    )


def test_denied_write_emits_filesystem_write_denied_event(
    isolated_paths: Path,
) -> None:
    target = paths.OBSIDIAN_VAULT / "anything.md"
    with pytest.raises(RoleSurfaceViolation):
        filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "x")
    entries = _read_roles_log(isolated_paths)
    assert len(entries) == 1
    assert entries[0]["event"] == "filesystem_write_denied"


def test_audit_event_carries_actor_role(isolated_paths: Path) -> None:
    target = paths.OBSIDIAN_VAULT / "anything.md"
    with pytest.raises(RoleSurfaceViolation):
        filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "x")
    entries = _read_roles_log(isolated_paths)
    assert entries[0]["actor"] == RoleEnum.PERSISTENCE_WRITER.value


def test_audit_event_carries_path_and_reason(isolated_paths: Path) -> None:
    target = paths.OBSIDIAN_VAULT / "anything.md"
    with pytest.raises(RoleSurfaceViolation):
        filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "x")
    entries = _read_roles_log(isolated_paths)
    details = entries[0]["details"]
    assert details["reason"] == "outside_allowed_writes"
    assert str(target.resolve()) == details["path"]


def test_audit_event_carries_run_id_when_provided(isolated_paths: Path) -> None:
    target = paths.OBSIDIAN_VAULT / "anything.md"
    with pytest.raises(RoleSurfaceViolation):
        filesystem_write_text(
            RoleEnum.PERSISTENCE_WRITER, target, "x", run_id="run_xyz"
        )
    entries = _read_roles_log(isolated_paths)
    assert entries[0]["run_id"] == "run_xyz"


def test_audit_event_omits_run_id_when_none(isolated_paths: Path) -> None:
    target = paths.OBSIDIAN_VAULT / "anything.md"
    with pytest.raises(RoleSurfaceViolation):
        filesystem_write_text(RoleEnum.PERSISTENCE_WRITER, target, "x")
    entries = _read_roles_log(isolated_paths)
    # audit_log_append carries None as the JSON null
    assert entries[0]["run_id"] is None


# --------------------------------------------------------------------------- #
# JSON serialisation passthrough                                              #
# --------------------------------------------------------------------------- #


def test_write_json_serializes_dict_correctly(isolated_paths: Path) -> None:
    target = isolated_paths / "runs" / "run_001" / "x.json"
    payload = {"a": 1, "b": [2, 3], "c": {"d": "e"}}
    filesystem_write_json(RoleEnum.PERSISTENCE_WRITER, target, payload)
    assert json.loads(target.read_text()) == payload


def test_write_json_rejects_nan(isolated_paths: Path) -> None:
    target = isolated_paths / "runs" / "run_001" / "x.json"
    with pytest.raises(ValueError):
        filesystem_write_json(
            RoleEnum.PERSISTENCE_WRITER, target, {"x": float("nan")}
        )


# --------------------------------------------------------------------------- #
# Map shape invariants                                                        #
# --------------------------------------------------------------------------- #


def test_allowed_writes_map_has_six_roles() -> None:
    """The role count is fixed at 6 per Step 3 design + bible 02 §7."""
    assert len(filesystem_writer._ALLOWED_WRITES) == 6


def test_allowed_writes_map_role_set() -> None:
    expected = {
        RoleEnum.PERSISTENCE_WRITER,
        RoleEnum.OBSIDIAN_WRITER,
        RoleEnum.NOTION_WRITER,
        RoleEnum.BOOT_SEQUENCER,
        RoleEnum.PIPELINE_DRIVER,
        RoleEnum.SAFETY_GATE,
    }
    assert set(filesystem_writer._ALLOWED_WRITES.keys()) == expected


def test_allowed_writes_values_are_tuples() -> None:
    """Tuples (not lists) so the map is structurally immutable."""
    for value in filesystem_writer._ALLOWED_WRITES.values():
        assert isinstance(value, tuple)


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #


def test_obsidian_writer_path_matches_bible_7_10() -> None:
    """Bible 02 §7.10 names the OBSIDIAN_WRITER write surface as
    ``~/SecondBrain/cee/...`` paths.
    """
    if not _BIBLE_02_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_02_PATH}")
    text = _BIBLE_02_PATH.read_text(encoding="utf-8")
    section_start = text.find("### 7.10 OBSIDIAN_WRITER")
    section_end = text.find("### 7.11", section_start)
    assert section_start != -1, "§7.10 not found"
    section = text[section_start:section_end]
    assert "~/SecondBrain/cee/" in section, (
        "bible 02 §7.10 OBSIDIAN_WRITER write surface canonical path "
        "missing — revisit OBSIDIAN_WRITER's allowed_writes entry"
    )


def test_persistence_writer_path_matches_bible_7_9() -> None:
    """Bible 02 §7.9 names PERSISTENCE_WRITER's write surface as
    ``~/cee/runs/<run_id>/`` files + new SKILL.md and agent files.
    """
    if not _BIBLE_02_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_02_PATH}")
    text = _BIBLE_02_PATH.read_text(encoding="utf-8")
    section_start = text.find("### 7.9 PERSISTENCE_WRITER")
    section_end = text.find("### 7.10", section_start)
    section = text[section_start:section_end]
    assert "~/cee/runs/" in section
    assert "SKILL.md" in section
    assert "agent files" in section


def test_boot_sequencer_path_matches_bible_7_13() -> None:
    """Bible 02 §7.13 names rebuilt registries + boot log + bible
    mirror + .sync_meta.json as BOOT_SEQUENCER's write surface.
    """
    if not _BIBLE_02_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_02_PATH}")
    text = _BIBLE_02_PATH.read_text(encoding="utf-8")
    section_start = text.find("### 7.13 BOOT_SEQUENCER")
    section_end = text.find("### 7.13a", section_start)
    section = text[section_start:section_end]
    assert "rebuilt registries" in section
    assert "boot log" in section
    assert "bible/*.md" in section
    assert ".sync_meta.json" in section


def test_in_memory_only_roles_excluded_from_map() -> None:
    """Bible 02 §7.2-§7.7 explicitly mark pipeline-step writes as
    'in-memory; persisted by PERSISTENCE_WRITER'. Those roles must
    not appear in the filesystem write map.
    """
    in_memory_only = {
        RoleEnum.INTERPRETER,
        RoleEnum.CLASSIFIER,
        RoleEnum.AGENT_SELECTOR,
        RoleEnum.SKILL_ENGINE,
        RoleEnum.STRATEGY_BUILDER,
        RoleEnum.PROMPT_BUILDER,
        RoleEnum.BIBLE_LOADER,
    }
    map_keys = set(filesystem_writer._ALLOWED_WRITES.keys())
    assert in_memory_only.isdisjoint(map_keys), (
        f"in-memory-only roles must not have filesystem write surfaces: "
        f"overlap={in_memory_only & map_keys}"
    )


def test_filesystem_writer_does_not_invoke_redactor_per_bible_12_5_7() -> None:
    """Bible 12 §5.7 canonical Detailed Workflow: filesystem_writer does
    NOT re-run the redactor. Redaction is SAFETY_GATE's responsibility
    upstream; filesystem_writer writes already-redacted bytes. Re-running
    the redactor here would corrupt audit-log hash chains, bible mirror
    canonical content (bible 12 §5.2 contains regex examples that would
    self-redact), and registry index.json files.

    Path A close of downstream candidate #32 (bible-misread; superseded
    by #42 surfacing bible 12 §5.7-vs-§11-line-470 contradiction).
    """
    src = Path(filesystem_writer.__file__).read_text(encoding="utf-8")

    # filesystem_writer must not import safety_gate (transitively or
    # directly). String-presence in source is sufficient — the module
    # has no conditional imports.
    assert "from safety_gate" not in src, (
        "filesystem_writer must not invoke the redactor per bible 12 §5.7"
    )
    assert "import safety_gate" not in src, (
        "filesystem_writer must not invoke the redactor per bible 12 §5.7"
    )

    # The §5.7 grounding comment must remain (anchors the negative
    # contract; future readers see why the wire-up was deliberately
    # omitted).
    assert "bible 12 §5.7" in src, (
        "filesystem_writer must document the §5.7-grounded non-invocation"
    )

    # The original active TODO marker must be gone (Path A closure).
    # Asserts the literal active-marker text — historical references in
    # the module docstring (e.g., "originally placed a ``# TODO #32``")
    # are intentional documentation and do not count as active markers.
    assert "TODO #32 / bible 12 §5: invoke redactor" not in src, (
        "active TODO #32 marker should be removed in Path A closure"
    )
