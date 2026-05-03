"""Tests for ``cli/commands/audit_verify.py`` — ``cee audit-verify``.

Every test redirects ``paths.AUDIT_*`` constants under ``tmp_path`` via
``monkeypatch``. None of these tests touch the real ``~/cee/audit/``
directory.

Phase 3 task 10 (Track C). Wraps Phase 1's
:func:`persistence.audit.verify_audit_chain` with operator-facing CLI
plumbing — these tests verify the wrapper behaviour (per-log walk,
halt-on-audit-dir-missing, JSONDecodeError catch, hint emission) but
do NOT re-cover the underlying chain verification logic (which has
its own tests in ``tests/unit/test_persistence/test_audit.py``).

The four canonical logs (bible 12 §5.8) are seeded by
:func:`persistence.audit.scaffold_audit_logs` in the ``audit_root``
fixture; per-test mutation simulates drift.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

import paths
from cli.commands.audit_verify import (
    _AUDIT_VERIFY_HINTS,
    cmd_audit_verify,
)
from persistence.audit import audit_log_append, scaffold_audit_logs


# ─── Fixture ────────────────────────────────────────────────────────────


@pytest.fixture
def audit_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every ``paths.AUDIT_*`` constant under ``tmp_path``.

    Mirrors ``tests/unit/test_persistence/test_audit.py:audit_root``
    (Phase 1) so the same drift-injection patterns work here. Seeds
    the four canonical log files via ``scaffold_audit_logs`` so a
    fresh-state happy-path test sees the post-init substrate.
    """
    audit_dir = tmp_path / "cee" / "audit"
    monkeypatch.setattr(paths, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(paths, "AUDIT_ARCHIVE_DIR", audit_dir / "archive")
    monkeypatch.setattr(paths, "AUDIT_CLI_LOG", audit_dir / "cli.log")
    monkeypatch.setattr(paths, "AUDIT_ROLES_LOG", audit_dir / "roles.log")
    monkeypatch.setattr(paths, "AUDIT_BOOT_LOG", audit_dir / "boot.log")
    monkeypatch.setattr(
        paths, "AUDIT_SECURITY_LOG", audit_dir / "security.log"
    )
    scaffold_audit_logs()
    return audit_dir


def _ns() -> argparse.Namespace:
    """Argparse Namespace stand-in — ``audit-verify`` takes no flags."""
    return argparse.Namespace(command="audit-verify")


# ─── Happy path ─────────────────────────────────────────────────────────


def test_audit_verify_returns_zero_when_all_logs_valid(
    audit_root: Path,
) -> None:
    """Freshly-scaffolded audit dir (4 empty logs) → exit 0."""
    assert cmd_audit_verify(_ns()) == 0


def test_audit_verify_passed_message_when_all_valid(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    cmd_audit_verify(_ns())
    out = capsys.readouterr().out
    assert "PASSED." in out


def test_audit_verify_summary_shows_correct_counts(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """All 4 logs valid → ``Summary: 4 of 4 logs valid.``"""
    cmd_audit_verify(_ns())
    out = capsys.readouterr().out
    assert "Summary: 4 of 4 logs valid." in out


# ─── Halt-on-audit-dir-missing ─────────────────────────────────────────


def test_audit_verify_returns_one_when_audit_dir_missing(
    audit_root: Path,
) -> None:
    """Audit dir deleted → halt-on-missing → exit 1."""
    import shutil
    shutil.rmtree(audit_root)
    assert cmd_audit_verify(_ns()) == 1


def test_audit_verify_does_not_walk_when_audit_dir_missing(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Halt-on-missing short-circuits — no spurious per-log reports.

    A naive walk under a missing audit dir would emit four spurious
    "valid empty chain" lines, masking the real failure. This test
    asserts the short-circuit: only the audit-dir MISSING line
    appears, not per-log entries like ``cli.log`` or ``boot.log``.
    """
    import shutil
    shutil.rmtree(audit_root)
    cmd_audit_verify(_ns())
    captured = capsys.readouterr()
    assert "MISSING" in captured.out
    # Spurious per-log reports must NOT appear.
    assert "cli.log" not in captured.out
    assert "roles.log" not in captured.out
    assert "boot.log" not in captured.out
    assert "security.log" not in captured.out
    # The audit_dir_missing hint goes to stderr.
    assert "audit_dir_missing" in captured.err
    assert _AUDIT_VERIFY_HINTS["audit_dir_missing"] in captured.err


# ─── Chain integrity failure modes ─────────────────────────────────────


def test_audit_verify_returns_one_on_tampered_entry(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Mutate a field without recomputing hash → entry_hash mismatch."""
    log = audit_root / "boot.log"
    audit_log_append(log, actor="A", event="e1", details={"i": 1})
    audit_log_append(log, actor="A", event="e2", details={"i": 2})

    # Tamper with the second entry's actor field. The stored entry_hash
    # is now wrong (and prev_hash linkage may also break).
    raw = log.read_text(encoding="utf-8")
    entries = [json.loads(line) for line in raw.split("\n") if line]
    entries[1]["actor"] = "MALICIOUS"
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    rc = cmd_audit_verify(_ns())
    assert rc == 1
    out = capsys.readouterr().out
    assert "BROKEN" in out
    assert "entry_hash mismatch" in out


def test_audit_verify_returns_one_on_broken_chain_link(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Modify prev_hash to wrong value → chain linkage break detected."""
    log = audit_root / "roles.log"
    audit_log_append(log, actor="A", event="e1", details={})
    audit_log_append(log, actor="A", event="e2", details={})

    raw = log.read_text(encoding="utf-8")
    entries = [json.loads(line) for line in raw.split("\n") if line]
    entries[1]["prev_hash"] = "f" * 64
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    rc = cmd_audit_verify(_ns())
    assert rc == 1
    out = capsys.readouterr().out
    # Tampering prev_hash breaks both entry_hash (it's hashed payload)
    # AND the prev_hash linkage check. Either rendering is acceptable.
    assert "prev_hash does not match" in out or "entry_hash mismatch" in out


def test_audit_verify_returns_one_on_genesis_hash_violation(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """First entry's prev_hash != GENESIS_HASH → broken."""
    log = audit_root / "cli.log"
    audit_log_append(log, actor="A", event="e1", details={})

    raw = log.read_text(encoding="utf-8")
    entries = [json.loads(line) for line in raw.split("\n") if line]
    entries[0]["prev_hash"] = "a" * 64
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    rc = cmd_audit_verify(_ns())
    assert rc == 1
    out = capsys.readouterr().out
    assert "prev_hash does not match" in out


def test_audit_verify_returns_one_on_malformed_jsonl(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Append a non-JSON line → JSONDecodeError caught + rendered as broken.

    Verifies T10's wrapper catches :class:`json.JSONDecodeError` from
    :func:`verify_audit_chain` (which raises rather than returning a
    broken entry per audit.py:391-396 design) and surfaces it as a
    chain failure with line_number + reason — but NOT the surrounding
    file bytes (per AB-locked decision to avoid leaking audit log
    content through stdout).
    """
    log = audit_root / "security.log"
    audit_log_append(log, actor="A", event="e", details={})
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("THIS_IS_NOT_JSON\n")

    rc = cmd_audit_verify(_ns())
    assert rc == 1
    out = capsys.readouterr().out
    assert "BROKEN" in out
    assert "malformed JSONL" in out
    # Critical: do NOT leak the offending line's bytes through stdout.
    assert "THIS_IS_NOT_JSON" not in out


# ─── Aggregation across logs ───────────────────────────────────────────


def test_audit_verify_aggregates_failures_across_logs(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Tamper with two different logs → both reported, exit 1."""
    boot_log = audit_root / "boot.log"
    cli_log = audit_root / "cli.log"
    audit_log_append(boot_log, actor="A", event="e", details={})
    audit_log_append(cli_log, actor="A", event="e", details={})

    # Tamper boot.log
    raw = boot_log.read_text(encoding="utf-8")
    entries = [json.loads(line) for line in raw.split("\n") if line]
    entries[0]["actor"] = "TAMPERED_BOOT"
    boot_log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    # Tamper cli.log
    raw = cli_log.read_text(encoding="utf-8")
    entries = [json.loads(line) for line in raw.split("\n") if line]
    entries[0]["actor"] = "TAMPERED_CLI"
    cli_log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    rc = cmd_audit_verify(_ns())
    out = capsys.readouterr().out
    assert rc == 1
    # Both logs report BROKEN.
    assert out.count("BROKEN") == 2
    # Summary reflects 2 of 4 valid (roles + security still clean).
    assert "Summary: 2 of 4 logs valid." in out


def test_audit_verify_continues_walking_after_one_log_breaks(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """First log broken, others valid → all 4 reported."""
    cli_log = audit_root / "cli.log"
    audit_log_append(cli_log, actor="A", event="e", details={})
    raw = cli_log.read_text(encoding="utf-8")
    entries = [json.loads(line) for line in raw.split("\n") if line]
    entries[0]["actor"] = "TAMPERED"
    cli_log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    rc = cmd_audit_verify(_ns())
    out = capsys.readouterr().out
    assert rc == 1
    # All 4 canonical logs must appear in output (cli broken, others ✓).
    assert "cli.log" in out
    assert "roles.log" in out
    assert "boot.log" in out
    assert "security.log" in out
    # 1 broken, 3 valid.
    assert out.count("✓") == 3
    assert out.count("✗") == 1


# ─── Per-log line rendering ─────────────────────────────────────────────


def test_audit_verify_per_log_line_shows_entry_count_on_valid(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Valid log line includes entry count: ``(chain valid, N entries)``."""
    audit_log_append(audit_root / "cli.log", actor="A", event="e", details={})
    audit_log_append(audit_root / "cli.log", actor="A", event="e", details={})

    cmd_audit_verify(_ns())
    out = capsys.readouterr().out
    assert "(chain valid, 2 entries)" in out
    # Other 3 logs are empty → 0 entries.
    assert "(chain valid, 0 entries)" in out


def test_audit_verify_per_log_line_shows_broken_count_on_broken(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Broken log line shows broken-entry count: ``BROKEN (M broken entries)``."""
    log = audit_root / "boot.log"
    audit_log_append(log, actor="A", event="e", details={})

    raw = log.read_text(encoding="utf-8")
    entries = [json.loads(line) for line in raw.split("\n") if line]
    entries[0]["actor"] = "X"
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    cmd_audit_verify(_ns())
    out = capsys.readouterr().out
    # Broken-entry count is 1 (entry_hash mismatch). prev_hash linkage
    # may or may not break depending on whether the tamper invalidated
    # the genesis link too — it doesn't (only the actor field changed,
    # leaving prev_hash intact). So count is exactly 1 in this case.
    assert "BROKEN (1 broken entries)" in out


# ─── Stdout / stderr invariants ────────────────────────────────────────


def test_audit_verify_stdout_uses_check_marks_for_valid(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    cmd_audit_verify(_ns())
    out = capsys.readouterr().out
    assert "✓" in out  # U+2713
    # All present + valid → no ✗ marks anywhere.
    assert "✗" not in out


def test_audit_verify_stderr_emits_chain_broken_hint_on_tamper(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Chain-integrity failure → chain_broken hint on stderr."""
    log = audit_root / "boot.log"
    audit_log_append(log, actor="A", event="e", details={})
    raw = log.read_text(encoding="utf-8")
    entries = [json.loads(line) for line in raw.split("\n") if line]
    entries[0]["actor"] = "X"
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    cmd_audit_verify(_ns())
    err = capsys.readouterr().err
    assert "chain_broken" in err
    assert _AUDIT_VERIFY_HINTS["chain_broken"] in err


def test_audit_verify_stderr_emits_malformed_jsonl_hint_on_bad_line(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Malformed JSONL → malformed_jsonl hint on stderr.

    Categorically distinct from chain_broken — the JSONDecodeError
    catch path triggers a different hint key than the chain-mismatch
    paths.
    """
    log = audit_root / "security.log"
    audit_log_append(log, actor="A", event="e", details={})
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("not-json\n")

    cmd_audit_verify(_ns())
    err = capsys.readouterr().err
    assert "malformed_jsonl" in err
    assert _AUDIT_VERIFY_HINTS["malformed_jsonl"] in err


def test_audit_verify_stderr_silent_on_success(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Happy path emits nothing on stderr (hint table is failure-only)."""
    cmd_audit_verify(_ns())
    err = capsys.readouterr().err
    assert err == ""


# ─── Walk order ────────────────────────────────────────────────────────


def test_audit_verify_walks_all_four_canonical_logs_in_declaration_order(
    audit_root: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    """Output order: cli → roles → boot → security.

    Matches :func:`persistence.audit._canonical_log_paths` declaration
    order verbatim (audit.py:135-147), so the verifier renders logs
    in the same sequence the writer enumerates them.
    """
    cmd_audit_verify(_ns())
    out = capsys.readouterr().out

    cli_pos = out.find("cli.log")
    roles_pos = out.find("roles.log")
    boot_pos = out.find("boot.log")
    security_pos = out.find("security.log")

    assert cli_pos != -1, "cli.log missing from output"
    assert roles_pos != -1, "roles.log missing from output"
    assert boot_pos != -1, "boot.log missing from output"
    assert security_pos != -1, "security.log missing from output"

    assert cli_pos < roles_pos < boot_pos < security_pos


# ─── Direct cmd_audit_verify dispatcher coverage ───────────────────────


def test_cmd_audit_verify_returns_zero_on_clean_state(
    audit_root: Path,
) -> None:
    """Direct dispatcher call on freshly-scaffolded audit dir → exit 0.

    Confirms the public surface (cmd_audit_verify → int) honours its
    contract end-to-end without going through the argparse layer.
    """
    rc = cmd_audit_verify(_ns())
    assert rc == 0
