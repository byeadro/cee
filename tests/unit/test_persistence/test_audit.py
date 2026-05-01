"""Tests for ``persistence/audit.py`` — hash-chained audit logs.

All tests redirect ``paths.AUDIT_*`` constants to a ``tmp_path`` subtree
via ``monkeypatch``. None of these tests touch the real ``~/cee/audit/``
directory.

Bible-grounding: :func:`test_audit_entry_schema_matches_bible_12_section_5_8`
parses bible 12 §5.8 directly so any future drift between the entry
shape and the bible surfaces in CI.

Halt resolutions applied (per pre-write reasoning):

- ``entry_hash`` excludes only ``entry_hash`` itself; ``prev_hash`` is
  inside the hashed payload (otherwise an attacker could rewrite history
  without invalidating any hash, defeating bible 12 §5.8's claim that
  "the hash chain makes tampering detectable").
- Genesis hash is ``"0" * 64`` — bible silent; standard convention.
- ``audit_log_append`` refuses to extend a broken chain. Bible 12 §10.6
  recovery ("future entries continue from new chain root") is a manual
  operator action; refusing here prevents masking tamper.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

import paths
from persistence import audit as audit_module
from persistence.audit import (
    GENESIS_HASH,
    audit_log_append,
    scaffold_audit_logs,
    verify_audit_chain,
)


# ─── Fixture ────────────────────────────────────────────────────────────


@pytest.fixture
def audit_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every ``paths.AUDIT_*`` constant under ``tmp_path``."""
    audit_dir = tmp_path / "cee" / "audit"
    monkeypatch.setattr(paths, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(paths, "AUDIT_ARCHIVE_DIR", audit_dir / "archive")
    monkeypatch.setattr(paths, "AUDIT_CLI_LOG", audit_dir / "cli.log")
    monkeypatch.setattr(paths, "AUDIT_ROLES_LOG", audit_dir / "roles.log")
    monkeypatch.setattr(paths, "AUDIT_BOOT_LOG", audit_dir / "boot.log")
    monkeypatch.setattr(
        paths, "AUDIT_SECURITY_LOG", audit_dir / "security.log"
    )
    return audit_dir


# ─── Helpers ────────────────────────────────────────────────────────────


def _read_entries(log_path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL audit log into a list of entry dicts."""
    raw = log_path.read_text(encoding="utf-8")
    return [json.loads(line) for line in raw.split("\n") if line]


def _expected_hash(entry: dict[str, Any]) -> str:
    """Recompute entry_hash the way the implementation does."""
    payload = {k: v for k, v in entry.items() if k != "entry_hash"}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


# ─── scaffold_audit_logs ────────────────────────────────────────────────


def test_scaffold_creates_four_log_files(audit_root: Path) -> None:
    scaffold_audit_logs()

    assert (audit_root / "cli.log").is_file()
    assert (audit_root / "roles.log").is_file()
    assert (audit_root / "boot.log").is_file()
    assert (audit_root / "security.log").is_file()


def test_scaffold_returns_correct_count_on_fresh_install(
    audit_root: Path,
) -> None:
    result = scaffold_audit_logs()

    assert result == {"files_created": 4}


def test_scaffold_returns_zero_on_idempotent_rerun(audit_root: Path) -> None:
    scaffold_audit_logs()
    second = scaffold_audit_logs()

    assert second == {"files_created": 0}


def test_scaffold_does_not_overwrite_existing_log(audit_root: Path) -> None:
    """Pre-existing content survives a rerun — no overwrite."""
    paths.ensure_dir(audit_root)
    pre = audit_root / "cli.log"
    pre.write_text(
        '{"ts":"2026-04-30T00:00:00+00:00","actor":"x","event":"y",'
        '"run_id":null,"details":{},"prev_hash":"' + GENESIS_HASH + '",'
        '"entry_hash":"deadbeef"}\n',
        encoding="utf-8",
    )
    original = pre.read_text(encoding="utf-8")

    result = scaffold_audit_logs()

    # cli.log already existed → only 3 created
    assert result == {"files_created": 3}
    assert pre.read_text(encoding="utf-8") == original


def test_scaffold_files_are_empty_on_creation(audit_root: Path) -> None:
    scaffold_audit_logs()

    for name in ("cli.log", "roles.log", "boot.log", "security.log"):
        assert (audit_root / name).read_text(encoding="utf-8") == ""


def test_scaffold_creates_archive_dir(audit_root: Path) -> None:
    scaffold_audit_logs()
    assert (audit_root / "archive").is_dir()


# ─── audit_log_append — chain construction ─────────────────────────────


def test_append_to_empty_log_uses_genesis_hash(audit_root: Path) -> None:
    scaffold_audit_logs()
    log = audit_root / "boot.log"

    audit_log_append(log, actor="BOOT_ROLE", event="boot_start", details={})

    entries = _read_entries(log)
    assert len(entries) == 1
    assert entries[0]["prev_hash"] == GENESIS_HASH


def test_append_to_missing_log_uses_genesis_hash(audit_root: Path) -> None:
    """No prior scaffold; append should still work and create the file."""
    paths.ensure_dir(audit_root)
    log = audit_root / "boot.log"
    assert not log.exists()

    audit_log_append(log, actor="BOOT_ROLE", event="boot_start", details={})

    entries = _read_entries(log)
    assert entries[0]["prev_hash"] == GENESIS_HASH


def test_append_chains_prev_hash_to_previous_entry_hash(
    audit_root: Path,
) -> None:
    scaffold_audit_logs()
    log = audit_root / "boot.log"

    h1 = audit_log_append(log, actor="A", event="e1", details={"i": 1})
    h2 = audit_log_append(log, actor="A", event="e2", details={"i": 2})

    entries = _read_entries(log)
    assert entries[0]["entry_hash"] == h1
    assert entries[1]["prev_hash"] == h1
    assert entries[1]["entry_hash"] == h2
    assert h1 != h2


def test_append_three_entries_chain_correctly(audit_root: Path) -> None:
    scaffold_audit_logs()
    log = audit_root / "boot.log"

    h1 = audit_log_append(log, actor="A", event="e1", details={"i": 1})
    h2 = audit_log_append(log, actor="A", event="e2", details={"i": 2})
    h3 = audit_log_append(log, actor="A", event="e3", details={"i": 3})

    entries = _read_entries(log)
    assert len(entries) == 3
    assert entries[0]["prev_hash"] == GENESIS_HASH
    assert entries[1]["prev_hash"] == h1
    assert entries[2]["prev_hash"] == h2
    assert [e["entry_hash"] for e in entries] == [h1, h2, h3]


def test_append_returns_entry_hash(audit_root: Path) -> None:
    scaffold_audit_logs()
    log = audit_root / "boot.log"

    returned = audit_log_append(log, actor="A", event="e", details={})

    entries = _read_entries(log)
    assert returned == entries[0]["entry_hash"]
    # Must look like a sha256 hex digest.
    assert re.fullmatch(r"[0-9a-f]{64}", returned)


# ─── audit_log_append — file format ────────────────────────────────────


def test_append_writes_jsonl_format(audit_root: Path) -> None:
    """One JSON object per line, terminated by newline."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"

    audit_log_append(log, actor="A", event="e1", details={})
    audit_log_append(log, actor="A", event="e2", details={})

    raw = log.read_text(encoding="utf-8")
    # Trailing newline (POSIX convention).
    assert raw.endswith("\n")
    # Each line independently parseable as JSON.
    lines = raw.rstrip("\n").split("\n")
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # raises if any line is malformed


def test_append_includes_required_fields(audit_root: Path) -> None:
    """Every entry has the seven bible-12 §5.8 fields, exactly."""
    scaffold_audit_logs()
    log = audit_root / "cli.log"
    audit_log_append(
        log, actor="OPERATOR", event="cli_invoked",
        details={"argv": ["cee", "verify"]}, run_id="20260430_120000_aaaaaaaa",
    )

    entries = _read_entries(log)
    expected = {"ts", "actor", "event", "run_id", "details",
                "prev_hash", "entry_hash"}
    assert set(entries[0].keys()) == expected


def test_append_run_id_can_be_none(audit_root: Path) -> None:
    scaffold_audit_logs()
    log = audit_root / "boot.log"

    audit_log_append(log, actor="BOOT_ROLE", event="boot", details={})

    entries = _read_entries(log)
    assert entries[0]["run_id"] is None


def test_append_run_id_can_be_provided(audit_root: Path) -> None:
    scaffold_audit_logs()
    log = audit_root / "roles.log"

    audit_log_append(
        log, actor="INTERPRETER", event="parse",
        details={}, run_id="20260430_120000_aaaaaaaa",
    )

    entries = _read_entries(log)
    assert entries[0]["run_id"] == "20260430_120000_aaaaaaaa"


def test_append_details_can_be_arbitrary_dict(audit_root: Path) -> None:
    scaffold_audit_logs()
    log = audit_root / "security.log"

    payload = {
        "patterns_matched": ["api_key", "ssn"],
        "count": 2,
        "nested": {"a": [1, 2, 3]},
    }
    audit_log_append(
        log, actor="SAFETY_GATE", event="redaction_applied", details=payload,
    )

    entries = _read_entries(log)
    assert entries[0]["details"] == payload


def test_append_uses_atomic_write(audit_root: Path) -> None:
    """The whole-file rewrite must go through atomic_write_text."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"

    with patch.object(
        audit_module, "atomic_write_text",
        wraps=audit_module.atomic_write_text,
    ) as spy:
        audit_log_append(log, actor="A", event="e", details={})

    # Called exactly once for this single append.
    assert spy.call_count == 1
    # First positional arg is the target path.
    assert spy.call_args.args[0] == log


# ─── audit_log_append — defence ────────────────────────────────────────


def test_append_rejects_path_outside_audit_dir(
    audit_root: Path, tmp_path: Path,
) -> None:
    """A path outside AUDIT_DIR raises ValueError."""
    paths.ensure_dir(audit_root)
    outsider = tmp_path / "not-audit" / "rogue.log"

    with pytest.raises(ValueError, match="not under AUDIT_DIR"):
        audit_log_append(outsider, actor="A", event="e", details={})

    assert not outsider.exists()


def test_append_accepts_path_inside_audit_dir(audit_root: Path) -> None:
    """A subdirectory under AUDIT_DIR is allowed (defensive baseline)."""
    paths.ensure_dir(audit_root)
    log = audit_root / "cli.log"

    # Should not raise.
    audit_log_append(log, actor="A", event="e", details={})


def test_append_rejects_extending_broken_chain_malformed_json(
    audit_root: Path,
) -> None:
    """Last line not valid JSON → refuse to extend."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"
    audit_log_append(log, actor="A", event="e", details={})

    # Corrupt: append junk to the file outside of CEE's writer.
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("this is not json\n")

    with pytest.raises(ValueError, match="malformed final entry"):
        audit_log_append(log, actor="A", event="e2", details={})


def test_append_rejects_extending_broken_chain_missing_entry_hash(
    audit_root: Path,
) -> None:
    """Last line is JSON but lacks entry_hash → refuse to extend."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"
    log.write_text(
        json.dumps({"ts": "x", "actor": "y", "event": "z",
                    "prev_hash": GENESIS_HASH}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="missing entry_hash"):
        audit_log_append(log, actor="A", event="e2", details={})


def test_append_rejects_extending_broken_chain_non_string_entry_hash(
    audit_root: Path,
) -> None:
    """entry_hash present but wrong type → refuse to extend."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"
    log.write_text(
        json.dumps({
            "ts": "x", "actor": "y", "event": "z",
            "run_id": None, "details": {},
            "prev_hash": GENESIS_HASH,
            "entry_hash": 12345,  # not a string
        }) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-string entry_hash"):
        audit_log_append(log, actor="A", event="e2", details={})


# ─── audit_log_append — determinism ────────────────────────────────────


def test_append_uses_sort_keys_in_json(audit_root: Path) -> None:
    """Hash is computed with sort_keys=True so identical content → identical hash.

    Construct two semantically identical details payloads with different
    insertion orders. The resulting entry_hashes must match (modulo ts,
    which we fix below).
    """
    scaffold_audit_logs()

    fixed_ts = "2026-04-30T12:00:00+00:00"

    class _FrozenDT:
        @staticmethod
        def now(tz: Any = None) -> datetime:
            return datetime.fromisoformat(fixed_ts)

    log_a = audit_root / "cli.log"
    log_b = audit_root / "boot.log"

    with patch.object(audit_module, "datetime", _FrozenDT):
        h_a = audit_log_append(
            log_a, actor="A", event="e",
            details={"x": 1, "y": 2},  # x first
        )
        h_b = audit_log_append(
            log_b, actor="A", event="e",
            details={"y": 2, "x": 1},  # y first — same content
        )

    assert h_a == h_b


def test_same_event_produces_same_entry_hash_when_ts_is_fixed(
    audit_root: Path,
) -> None:
    """Determinism baseline: identical inputs → identical hash."""
    scaffold_audit_logs()
    fixed_ts = "2026-04-30T12:00:00+00:00"

    class _FrozenDT:
        @staticmethod
        def now(tz: Any = None) -> datetime:
            return datetime.fromisoformat(fixed_ts)

    log_a = audit_root / "cli.log"
    log_b = audit_root / "boot.log"

    with patch.object(audit_module, "datetime", _FrozenDT):
        h_a = audit_log_append(
            log_a, actor="A", event="e", details={"k": "v"},
        )
        h_b = audit_log_append(
            log_b, actor="A", event="e", details={"k": "v"},
        )

    assert h_a == h_b


def test_append_ts_is_timezone_aware_utc(audit_root: Path) -> None:
    """ts is ISO-8601 with timezone info, in UTC."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"

    audit_log_append(log, actor="A", event="e", details={})

    entries = _read_entries(log)
    ts_str = entries[0]["ts"]
    parsed = datetime.fromisoformat(ts_str)
    assert parsed.tzinfo is not None
    # UTC offset is zero.
    assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)


# ─── verify_audit_chain ─────────────────────────────────────────────────


def test_verify_returns_true_on_empty_log(audit_root: Path) -> None:
    scaffold_audit_logs()
    log = audit_root / "boot.log"

    is_valid, broken = verify_audit_chain(log)
    assert is_valid is True
    assert broken == []


def test_verify_returns_true_on_missing_log(audit_root: Path) -> None:
    """An absent log is an empty chain — valid."""
    paths.ensure_dir(audit_root)
    log = audit_root / "boot.log"
    assert not log.exists()

    is_valid, broken = verify_audit_chain(log)
    assert is_valid is True
    assert broken == []


@pytest.mark.parametrize("count", [1, 2, 5])
def test_verify_returns_true_on_valid_chain(
    audit_root: Path, count: int,
) -> None:
    scaffold_audit_logs()
    log = audit_root / "boot.log"
    for i in range(count):
        audit_log_append(log, actor="A", event=f"e{i}", details={"i": i})

    is_valid, broken = verify_audit_chain(log)
    assert is_valid is True
    assert broken == []


def test_verify_returns_false_on_tampered_entry(audit_root: Path) -> None:
    """Mutate a field without recomputing hash → entry_hash mismatch."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"
    audit_log_append(log, actor="A", event="e1", details={"i": 1})
    audit_log_append(log, actor="A", event="e2", details={"i": 2})

    # Tamper with the second entry's actor field. The stored entry_hash
    # is now wrong.
    entries = _read_entries(log)
    entries[1]["actor"] = "MALICIOUS"
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    is_valid, broken = verify_audit_chain(log)
    assert is_valid is False
    assert any(b["line_number"] == 2 and "entry_hash mismatch" in b["reason"]
               for b in broken)


def test_verify_returns_false_on_broken_chain_link(audit_root: Path) -> None:
    """Modify prev_hash to wrong value → both entry_hash + prev_hash break."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"
    audit_log_append(log, actor="A", event="e1", details={})
    audit_log_append(log, actor="A", event="e2", details={})

    entries = _read_entries(log)
    entries[1]["prev_hash"] = "f" * 64
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    is_valid, broken = verify_audit_chain(log)
    assert is_valid is False
    reasons = [b["reason"] for b in broken if b["line_number"] == 2]
    # Tampering prev_hash breaks both entry_hash (it's hashed payload) AND
    # the prev_hash linkage check — both are surfaced.
    assert any("entry_hash mismatch" in r for r in reasons)
    assert any("prev_hash does not match" in r for r in reasons)


def test_verify_returns_false_on_first_entry_wrong_genesis(
    audit_root: Path,
) -> None:
    """First entry's prev_hash != GENESIS_HASH → broken."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"
    audit_log_append(log, actor="A", event="e1", details={})

    # Tamper: change first prev_hash to non-genesis.
    entries = _read_entries(log)
    entries[0]["prev_hash"] = "a" * 64
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    is_valid, broken = verify_audit_chain(log)
    assert is_valid is False
    assert any(b["line_number"] == 1 and "prev_hash does not match" in b["reason"]
               for b in broken)


def test_verify_returns_list_of_broken_entries(audit_root: Path) -> None:
    """``broken`` carries entries with line_number + reason + entry."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"
    audit_log_append(log, actor="A", event="e1", details={})
    audit_log_append(log, actor="A", event="e2", details={})

    entries = _read_entries(log)
    entries[1]["actor"] = "TAMPERED"
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    is_valid, broken = verify_audit_chain(log)
    assert is_valid is False
    assert len(broken) >= 1
    for item in broken:
        assert "line_number" in item
        assert "reason" in item
        assert "entry" in item
        assert isinstance(item["line_number"], int)
        assert isinstance(item["reason"], str)


def test_verify_rejects_path_outside_audit_dir(
    audit_root: Path, tmp_path: Path,
) -> None:
    paths.ensure_dir(audit_root)
    outsider = tmp_path / "not-audit" / "rogue.log"

    with pytest.raises(ValueError, match="not under AUDIT_DIR"):
        verify_audit_chain(outsider)


def test_verify_handles_invalid_json_line(audit_root: Path) -> None:
    """Malformed JSONL line raises JSONDecodeError."""
    scaffold_audit_logs()
    log = audit_root / "boot.log"
    audit_log_append(log, actor="A", event="e", details={})
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("not-json\n")

    with pytest.raises(json.JSONDecodeError):
        verify_audit_chain(log)


# ─── Bible-grounding ───────────────────────────────────────────────────


def test_audit_entry_schema_matches_bible_12_section_5_8(
    audit_root: Path,
) -> None:
    """Parse the bible 12 §5.8 JSON code block and assert field parity.

    If the bible adds, removes, or renames an entry field, this test
    fails — surfacing drift in CI rather than in production.
    """
    bible_path = paths.BIBLE_DIR / "12_prompt_leak_security_rules.md"
    bible_text = bible_path.read_text(encoding="utf-8")

    # Locate the §5.8 fenced JSON block (the audit log entry shape).
    match = re.search(
        r"### 5\.8 The audit log structure.*?```json\s*(\{.*?\})\s*```",
        bible_text, flags=re.DOTALL,
    )
    assert match, "could not locate bible 12 §5.8 JSON example"
    bible_json_str = match.group(1)
    # The block uses placeholder values (e.g. "<ISO timestamp>") so it
    # parses as JSON but the values aren't real. Field names are what we
    # care about. Replace nested "{ ... }" placeholder with a real {} so
    # json.loads succeeds.
    cleaned = bible_json_str.replace("{ ... }", "{}")
    parsed = json.loads(cleaned)
    bible_field_names = set(parsed.keys())

    expected = {"ts", "actor", "event", "run_id", "details",
                "prev_hash", "entry_hash"}
    assert bible_field_names == expected, (
        f"bible 12 §5.8 fields {bible_field_names!r} drifted from "
        f"implementation expectation {expected!r}"
    )

    # And our written entry must match exactly.
    scaffold_audit_logs()
    log = audit_root / "security.log"
    audit_log_append(
        log, actor="SAFETY_GATE", event="redaction_applied",
        details={}, run_id="20260430_120000_aaaaaaaa",
    )
    entries = _read_entries(log)
    assert set(entries[0].keys()) == bible_field_names


# ─── No leakage outside the patched audit root ────────────────────────


def test_audit_writes_only_under_audit_dir(
    audit_root: Path, tmp_path: Path,
) -> None:
    """Scaffold + append + verify never write outside the patched tree."""
    sibling = tmp_path / "outside-audit.txt"
    sibling.write_text("untouched", encoding="utf-8")

    scaffold_audit_logs()
    log = audit_root / "cli.log"
    audit_log_append(log, actor="A", event="e", details={})
    verify_audit_chain(log)

    for path in tmp_path.rglob("*"):
        rel = str(path.relative_to(tmp_path))
        assert (
            rel == "outside-audit.txt"
            or rel == "cee"
            or rel.startswith("cee/audit")
        ), f"unexpected write outside audit dir: {rel}"

    assert sibling.read_text(encoding="utf-8") == "untouched"
