"""Phase 3 gate validation per bible 20 §5.3.

Phase 3 task 13 commit 1 — gate verification. Mirrors Phase 2 task 11
pattern (``tests/integration/test_phase2_gate.py``). Validates the six
gate criteria literal in bible 20 §5.3 (lines 186–191).

Bible 20 §5.3 verbatim gate criteria:

1. "A test fixture artifact can be written to all three substrates and
   reads back identically (modulo redaction differences)."
2. "Redaction tests pass for every pattern in section 12."
3. "Injection tests pass for every pattern in section 12."
4. "Hash chain detects tampering."
5. "Test: ``tests/unit/test_safety_gate/``,
   ``tests/unit/test_persistence/`` pass."
6. "Test: ``tests/integration/test_persistence_chain.py`` passes."

Resolution decisions (locked at design phase):

* **H1 (6 vs 5 criteria).** Bible 20 §5.3 has six unlabeled bullets;
  ``build_status.md`` T13 spec uses an "(a)–(e)" five-criterion identifier
  set that collapses bullets 5+6. Implementation tracks bible verbatim →
  six test functions, one per bullet. ``build_status.md`` correction is
  a Commit 2 paperwork item.
* **H2 (criterion 2 substrate).** Bible §5.2 enumerates more redaction
  patterns than ``safety_gate.redactor._BUILTIN_PATTERNS`` ships
  (street_address_us, email, credit_card, ip_address are bible-side
  deferred per downstream candidates #38 and #39). Criterion 2 asserts
  coverage against the **shipped** ``_BUILTIN_PATTERNS`` set, not the
  bible §5.2 catalog — interpreting "every pattern in section 12" as
  "every shipped pattern from section 12." The four deferred patterns
  surface separately in candidates #38/#39 and the bible-edit pass.
* **H3 (criteria 1+6 textual nesting).** ``test_persistence_chain.py``
  literally is the round-trip fixture. Both criteria are shipped as
  separate test functions per bible-verbatim adherence — criterion 1
  verifies the round-trip *invariant* (the artifact's three-substrate
  semantics), criterion 6 verifies the file-named test *passes*. Both
  subprocess-run T12; the redundancy is bible-verbatim discipline.

Subprocess vs in-process (Q4 resolution): criteria 1, 5, 6 use
subprocess pytest invocation. The bible bullets read "Test: <path>
passes" — a runtime claim about the suites actually running green, not
just an existence claim about the test files. Subprocess isolates each
gate criterion from the parent pytest's collection and fixture state.
Phase 2 T11's criteria 4+5 are file-existence checks; T13's stronger
subprocess approach matches what bible 20 §5.3 demands.

Cross-references:

* Criteria 1 + 6 lift T12's chain fixture
  (``tests/integration/test_persistence_chain.py``).
* Criteria 2 + 3 introspect Phase 1 unit tests
  (``tests/unit/test_safety_gate/test_redaction_patterns.py``,
  ``tests/unit/test_safety_gate/test_injection_patterns.py``).
* Criterion 4 mirrors the unit-level invariant from
  ``tests/unit/test_persistence/test_audit.py``
  (``test_verify_returns_false_on_tampered_entry``) but is shipped here
  as a gate-level direct-tamper restatement; T12's
  ``test_planted_tamper_detected_after_round_trip`` covers the
  full-substrate-chain version.
* Criterion 5 is a bare subprocess pytest of the two unit-test
  directories bible 20 §5.3 names by path.

No fixtures. Subprocess-runs are isolated; criterion 4 uses
``tmp_path`` + ``monkeypatch`` inline (matching ``test_audit.py``'s
``audit_root`` pattern). Criteria 2 + 3 are pure introspection with no
filesystem state.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import paths
from persistence.audit import (
    audit_log_append,
    scaffold_audit_logs,
    verify_audit_chain,
)
from safety_gate.injection_scanner import (
    _DIRECT_PATTERNS,
    _HIDDEN_UNICODE_CHARS,
)
from safety_gate.redactor import _BUILTIN_PATTERNS


# --------------------------------------------------------------------------- #
# Project root + shared paths                                                 #
# --------------------------------------------------------------------------- #


_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent
_REDACTION_TESTS_FILE: Path = (
    _PROJECT_ROOT
    / "tests"
    / "unit"
    / "test_safety_gate"
    / "test_redaction_patterns.py"
)
_INJECTION_TESTS_FILE: Path = (
    _PROJECT_ROOT
    / "tests"
    / "unit"
    / "test_safety_gate"
    / "test_injection_patterns.py"
)
_PERSISTENCE_CHAIN_TEST: str = (
    "tests/integration/test_persistence_chain.py"
)
_UNIT_SAFETY_GATE_DIR: str = "tests/unit/test_safety_gate/"
_UNIT_PERSISTENCE_DIR: str = "tests/unit/test_persistence/"


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #


def _extract_test_names_from_file(path: Path) -> set[str]:
    """Return the set of ``def test_<name>(...)`` identifiers in ``path``.

    Pure source introspection — does not import or execute the file. The
    regex anchors on column zero so nested helper functions inside test
    bodies are excluded. Used by criteria 2 + 3 to map shipped pattern
    names against test-function declarations.
    """
    source = path.read_text(encoding="utf-8")
    return set(re.findall(r"^def (test_\w+)\(", source, re.MULTILINE))


def _has_test_for_pattern(test_names: set[str], pattern_name: str) -> bool:
    """True if any ``test_<pattern_name>_*`` exists in ``test_names``.

    Matches ``test_anthropic_api_key_positive_match``,
    ``test_anthropic_api_key_negative_no_match``,
    ``test_anthropic_api_key_placeholder_format`` and friends. The
    trailing underscore prevents false matches between e.g.
    ``aws_access_key`` and ``aws_secret_key``.
    """
    prefix = f"test_{pattern_name}_"
    return any(name.startswith(prefix) for name in test_names)


def _run_pytest_subprocess(*targets: str) -> subprocess.CompletedProcess[str]:
    """Run ``pytest -q <targets>`` from the project root in a subprocess.

    Subprocess isolation per Q4 resolution: criteria 1, 5, 6 must verify
    the suites actually run green, not merely that the test files exist.
    Recursive in-process ``pytest.main()`` would inherit this run's
    collection + fixture state. ``check=False`` so the caller can surface
    stdout/stderr in the assertion message on non-zero exit.
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", *targets, "-q"],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------------- #
# Criterion 1 — round-trip artifact through three substrates                  #
# --------------------------------------------------------------------------- #


def test_phase3_gate_criterion_1_round_trip_artifact_through_three_substrates() -> (
    None
):
    """Bible 20 §5.3 criterion #1: "A test fixture artifact can be
    written to all three substrates and reads back identically (modulo
    redaction differences)."

    Verification: subprocess-runs T12's chain fixture
    (``tests/integration/test_persistence_chain.py``) and asserts exit
    0. T12's nine tests collectively prove the round-trip invariant —
    filesystem byte-equal persistence, Obsidian byte-equal persistence,
    Notion drain via stub, plus tamper-detection across the audit chain
    after round-trip. This criterion verifies the *invariant* (the
    artifact's three-substrate semantics); criterion 6 separately
    verifies that the file-named test passes. Both subprocess-run the
    same target per H3 resolution — bible-verbatim discipline preserves
    the bullet-by-bullet enumeration.
    """
    result = _run_pytest_subprocess(_PERSISTENCE_CHAIN_TEST)
    assert result.returncode == 0, (
        f"criterion 1: round-trip chain test failed (exit "
        f"{result.returncode})\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )


# --------------------------------------------------------------------------- #
# Criterion 2 — redaction patterns all covered                                #
# --------------------------------------------------------------------------- #


def test_phase3_gate_criterion_2_redaction_patterns_all_covered() -> None:
    """Bible 20 §5.3 criterion #2: "Redaction tests pass for every
    pattern in section 12."

    Verification: introspect ``safety_gate.redactor._BUILTIN_PATTERNS``;
    for each pattern's ``.name`` attribute, assert at least one matching
    ``def test_<name>_*`` exists in
    ``tests/unit/test_safety_gate/test_redaction_patterns.py``.

    Substitution per H2 resolution: bible §5.2 enumerates patterns T6
    deferred (street_address_us per candidate #38; email, credit_card,
    ip_address per candidate #39). Criterion asserts against the
    *shipped* pattern set (``_BUILTIN_PATTERNS``), interpreting "every
    pattern in section 12" as "every shipped pattern from section 12."
    The deferred patterns close separately at the bible-edit pass.

    Coverage proof: this gate confirms every shipped pattern has at
    least one test declaration. ``test_phase3_gate_criterion_5`` then
    subprocess-runs ``tests/unit/test_safety_gate/`` and asserts those
    tests *pass*. Together criteria 2 + 5 satisfy "tests pass for every
    pattern."
    """
    test_names = _extract_test_names_from_file(_REDACTION_TESTS_FILE)
    shipped_pattern_names = [pattern.name for pattern in _BUILTIN_PATTERNS]

    missing: list[str] = [
        name
        for name in shipped_pattern_names
        if not _has_test_for_pattern(test_names, name)
    ]

    assert not missing, (
        f"criterion 2: redaction patterns without test coverage in "
        f"{_REDACTION_TESTS_FILE.name}: {missing}. Each shipped pattern "
        f"in _BUILTIN_PATTERNS must have at least one matching "
        f"test_<pattern_name>_* declaration."
    )


# --------------------------------------------------------------------------- #
# Criterion 3 — injection patterns all covered                                #
# --------------------------------------------------------------------------- #


def test_phase3_gate_criterion_3_injection_patterns_all_covered() -> None:
    """Bible 20 §5.3 criterion #3: "Injection tests pass for every
    pattern in section 12."

    Verification: introspect
    ``safety_gate.injection_scanner._DIRECT_PATTERNS`` (the six direct
    string-match patterns) plus the ``_HIDDEN_UNICODE_CHARS`` mechanism
    (T7's hidden-unicode detection — separate from the direct-pattern
    table; mapped to the ``hidden_unicode`` coverage marker since tests
    name it that way). For each, assert at least one matching
    ``def test_<name>_*`` exists in
    ``tests/unit/test_safety_gate/test_injection_patterns.py``.

    Mirrors criterion 2's coverage-declaration shape. Criterion 5
    separately asserts those tests *pass* via subprocess.
    """
    test_names = _extract_test_names_from_file(_INJECTION_TESTS_FILE)

    direct_pattern_names = [pattern.name for pattern in _DIRECT_PATTERNS]
    # _HIDDEN_UNICODE_CHARS is a frozenset of characters, not a named
    # pattern. T7's tests name the mechanism "hidden_unicode" by
    # convention; this gate uses that conventional marker.
    expected_coverage_markers = direct_pattern_names + ["hidden_unicode"]

    missing: list[str] = [
        name
        for name in expected_coverage_markers
        if not _has_test_for_pattern(test_names, name)
    ]

    # Sanity-check: _HIDDEN_UNICODE_CHARS must be non-empty for the
    # "hidden_unicode" marker to represent meaningful coverage.
    assert len(_HIDDEN_UNICODE_CHARS) > 0, (
        "criterion 3: _HIDDEN_UNICODE_CHARS is empty — no hidden-unicode "
        "characters declared, so 'hidden_unicode' coverage marker is "
        "vacuous."
    )

    assert not missing, (
        f"criterion 3: injection patterns without test coverage in "
        f"{_INJECTION_TESTS_FILE.name}: {missing}. Each pattern in "
        f"_DIRECT_PATTERNS plus the 'hidden_unicode' mechanism must "
        f"have at least one matching test_<pattern_name>_* declaration."
    )


# --------------------------------------------------------------------------- #
# Criterion 4 — hash chain detects tampering                                  #
# --------------------------------------------------------------------------- #


def test_phase3_gate_criterion_4_hash_chain_detects_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bible 20 §5.3 criterion #4: "Hash chain detects tampering."

    Verification: build a 3-entry audit log via ``audit_log_append``,
    tamper one entry's stored fields without recomputing the hash, then
    assert ``verify_audit_chain`` returns ``(False, broken)`` with a
    non-empty broken list flagging the tampered line.

    Scope distinction from T12's
    ``test_planted_tamper_detected_after_round_trip``: T12 plants a
    tamper after the substrate-emission cycle ran, exercising the
    chain-detection mechanism *over* the round-trip's audit emissions.
    This criterion is the unit-level invariant — does
    ``verify_audit_chain`` flag a hand-crafted tamper on a
    minimally-constructed log? The narrow restatement at gate level
    proves the bible 20 §5.3 bullet 4 mechanism is independently
    verifiable, not just a side effect of T12's full chain.

    Audit-dir scaffold required because ``audit_log_append`` enforces
    ``_assert_under_audit_dir`` against ``paths.AUDIT_DIR`` (bible 12
    §5.8 path-containment check). Mirrors ``test_audit.py``'s
    ``audit_root`` fixture pattern inline.
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

    log = audit_dir / "boot.log"
    audit_log_append(log, actor="GATE", event="e1", details={"i": 1})
    audit_log_append(log, actor="GATE", event="e2", details={"i": 2})
    audit_log_append(log, actor="GATE", event="e3", details={"i": 3})

    pre_tamper_valid, pre_tamper_broken = verify_audit_chain(log)
    assert pre_tamper_valid is True, (
        f"criterion 4: pre-tamper chain unexpectedly invalid: "
        f"{pre_tamper_broken}"
    )
    assert pre_tamper_broken == []

    raw_lines = log.read_text(encoding="utf-8").rstrip("\n").split("\n")
    entries = [json.loads(line) for line in raw_lines]
    assert len(entries) == 3
    # Mutate the second entry's actor field without recomputing the
    # stored entry_hash — classic tamper: payload changed, hash stale.
    entries[1]["actor"] = "MALICIOUS"
    log.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n",
        encoding="utf-8",
    )

    post_tamper_valid, post_tamper_broken = verify_audit_chain(log)

    assert post_tamper_valid is False, (
        "criterion 4: hash chain failed to detect tampering — "
        "verify_audit_chain returned True after mutating entry payload "
        "without recomputing hash"
    )
    assert post_tamper_broken, (
        "criterion 4: chain reported invalid but no broken entries "
        "surfaced"
    )
    assert any(
        b["line_number"] == 2 for b in post_tamper_broken
    ), (
        f"criterion 4: tampered line (2) not flagged in broken list: "
        f"{post_tamper_broken}"
    )


# --------------------------------------------------------------------------- #
# Criterion 5 — unit test suites pass                                         #
# --------------------------------------------------------------------------- #


def test_phase3_gate_criterion_5_unit_test_suites_pass() -> None:
    """Bible 20 §5.3 criterion #5: "Test:
    ``tests/unit/test_safety_gate/``,
    ``tests/unit/test_persistence/`` pass."

    Verification: subprocess-runs the two named unit-test directories
    and asserts exit 0. Subprocess per Q4 resolution — bullet 5 is a
    runtime claim ("pass"), not an existence claim. Phase 2 T11's
    criteria 4+5 use file-existence checks and so are weaker than what
    bible 20 §5.3 demands; T13 uses the stronger subprocess approach.
    """
    result = _run_pytest_subprocess(
        _UNIT_SAFETY_GATE_DIR, _UNIT_PERSISTENCE_DIR
    )
    assert result.returncode == 0, (
        f"criterion 5: unit test suites failed (exit "
        f"{result.returncode})\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )


# --------------------------------------------------------------------------- #
# Criterion 6 — persistence chain integration test passes                     #
# --------------------------------------------------------------------------- #


def test_phase3_gate_criterion_6_persistence_chain_integration_test_passes() -> (
    None
):
    """Bible 20 §5.3 criterion #6: "Test:
    ``tests/integration/test_persistence_chain.py`` passes."

    Verification: subprocess-runs the named integration test file and
    asserts exit 0. Textually nested with criterion 1 per H3 resolution
    — both subprocess-run T12's chain fixture. Criterion 1 verifies the
    round-trip *invariant* (the artifact's three-substrate semantics);
    criterion 6 verifies the file-named test *passes*. Both are shipped
    as separate test functions per bible-verbatim adherence; the bible
    enumerates them as distinct bullets, so the gate enumerates them
    as distinct functions.
    """
    result = _run_pytest_subprocess(_PERSISTENCE_CHAIN_TEST)
    assert result.returncode == 0, (
        f"criterion 6: persistence-chain integration test failed (exit "
        f"{result.returncode})\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
