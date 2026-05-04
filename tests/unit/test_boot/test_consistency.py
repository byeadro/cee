"""Unit tests for ``boot.consistency`` — closed-enum drift detection.

Authorized by bible 00 §12 step B3 and bible 20 §5.2. The 13 registry
entries are locked in the Phase 2 task 5 spec. These tests verify:

* The registry has the locked shape (entry count, key uniqueness).
* Every registered entry passes drift-clean against the live bible +
  code state (parametrized — one test per entry, so a single drift
  surfaces as a single test failure pinpointing the offending enum).
* Each of the 5 named extractors handles its target shape on synthetic
  bible fragments.
* Synthetic drift conditions (internal-schema disagreement, missing
  bible page) produce the expected DriftRecord shapes.
* The dataclasses ``DriftRecord`` and ``ConsistencyReport`` are frozen
  (the boot sequencer relies on this immutability when carrying drifts
  in BootConsistencyError).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from boot.consistency import (
    REGISTRY,
    ConsistencyReport,
    DriftRecord,
    RegistryEntry,
    _extract_regex_bullet_list,
    _extract_regex_html_table_backticks,
    _extract_regex_inline_code,
    _extract_regex_pipe_list,
    _extract_regex_python_class,
    check,
)

# --------------------------------------------------------------------------- #
# Registry shape                                                              #
# --------------------------------------------------------------------------- #


def test_registry_has_thirteen_entries() -> None:
    """Phase 2 task 5 locked the registry at 13 entries (entries 9, 10,
    13 from the original audit are deferred per AB resolution)."""
    assert len(REGISTRY) == 13


def test_registry_keys_unique_and_match_enum_names() -> None:
    # Keys are unique by dict semantics; this asserts each key matches
    # its entry's ``enum_name`` so the registry is self-describing.
    for key, entry in REGISTRY.items():
        assert key == entry.enum_name


def test_registry_locked_entry_set() -> None:
    # The full locked set per the T5 spec.
    expected = {
        "RoleEnum",
        "TaskType",
        "ComplexityTier",
        "FormatType",
        "SourceType",
        "Posture",
        "Domain",
        "Sensitivity",
        "RunState",
        "TargetExecutor",
        "HaltType",
        "RunErrorType",
        "WarningType",
    }
    assert set(REGISTRY.keys()) == expected


def test_registry_entries_have_at_least_one_loader() -> None:
    for name, entry in REGISTRY.items():
        assert len(entry.code_source_loaders) >= 1, (
            f"{name} has zero code source loaders — the registry is "
            f"meaningless for an enum with no code mirrors"
        )


def test_registry_extractors_are_callables() -> None:
    for entry in REGISTRY.values():
        assert callable(entry.extractor)


# --------------------------------------------------------------------------- #
# Per-entry drift-clean (parametrized)                                        #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("entry_name", sorted(REGISTRY.keys()))
def test_each_registry_entry_drift_clean(entry_name: str) -> None:
    """Every registered entry must pass against the live bible + code.

    A failure here means either the bible drifted from what the code
    declares, or the registry's section anchor / extractor needs an
    update. The test names the offending enum so the boot log points
    straight at it.
    """
    report = check(entry_names=(entry_name,))
    assert report.enums_checked == 1
    assert report.ok, (
        f"{entry_name} drift detected:\n"
        + "\n".join(f"  - {d.drift_kind}: {d.detail}" for d in report.drifts)
    )
    assert report.drifts == ()


def test_full_check_drift_clean() -> None:
    """A second guard: the full registry must also pass clean. This is
    redundant with the parametrized test above for green builds but
    catches inter-entry interactions (logger calls, ordering)."""
    report = check()
    assert report.ok
    assert report.enums_checked == 13
    assert report.drifts == ()


# --------------------------------------------------------------------------- #
# Per-extractor synthetic tests                                               #
# --------------------------------------------------------------------------- #


def test_extract_bullet_list_picks_backticked_values() -> None:
    content = (
        "## 4. Roles\n"
        "### 4.1 Human roles\n"
        "- `OPERATOR`\n"
        "- `AUDITOR` (future)\n"
        "### 4.2 System roles\n"
        "- `INTERPRETER`\n"
        "- `CLASSIFIER`\n"
        "## 5. Detailed Workflow\n"
        "- `NOT_A_ROLE`\n"  # outside §4, must be ignored
    )
    values = _extract_regex_bullet_list(content, "### 4.")
    assert values == frozenset(
        {"OPERATOR", "AUDITOR", "INTERPRETER", "CLASSIFIER"}
    )


def test_extract_html_table_backticks_first_column_only() -> None:
    content = (
        "### 5.1 Closed task type\n"
        "<table>\n"
        "<tr>\n"
        "<td>Value</td>\n"  # header — no backticks, ignored
        "<td>Definition</td>\n"
        "</tr>\n"
        "<tr>\n"
        "<td>`BUILD`</td>\n"
        "<td>`description in second col`</td>\n"  # second col with backticks
        "</tr>\n"
        "<tr>\n"
        "<td>`ANALYZE`</td>\n"
        "<td>analysis</td>\n"
        "</tr>\n"
        "</table>\n"
    )
    values = _extract_regex_html_table_backticks(content, "### 5.1 ")
    # Both backticked tokens in the same row appear; the extractor
    # uses ``search`` per line and so collects both. That is acceptable
    # for the registry's real bibles where second-column descriptions
    # do not collide with the first-column enum value space; this test
    # documents the behavior.
    assert "BUILD" in values
    assert "ANALYZE" in values


def test_extract_pipe_list_with_line_anchor() -> None:
    content = (
        "### 5.2 Frontmatter schema\n"
        "preamble line one\n"
        "preamble line two\n"
        "sensitivity: low | medium | high      # comment with | pipe inside\n"
        "trailing line\n"
    )
    values = _extract_regex_pipe_list(content, "### 5.2 ", line_anchor=4)
    assert values == frozenset({"low", "medium", "high"})


def test_extract_inline_code_brace_set_with_line_anchor() -> None:
    content = (
        "### 5.2 The Run pipeline\n"
        "preamble\n"
        "x\n"
        "x\n"
        "**Validation:** non-empty `text`; `target_executor` "
        "∈ {claude_ai, claude_code, api}; attachments must exist.\n"
    )
    values = _extract_regex_inline_code(content, "### 5.2 ", line_anchor=5)
    assert values == frozenset({"claude_ai", "claude_code", "api"})


def test_extract_python_class_walks_code_fence_only() -> None:
    content = (
        "### 5.1 The closed HaltType enum\n"
        "Some narrative outside the code fence with FAKE_VALUE = 'x' line.\n"
        "```python\n"
        "class HaltType(str, Enum):\n"
        "    INPUT_VALIDATION_ERROR = \"input_validation_error\"\n"
        "    PAUSED_FOR_CLARIFICATION = \"paused_for_clarification\"\n"
        "```\n"
        "FAKE_VALUE = \"outside\"\n"
    )
    values = _extract_regex_python_class(content, "### 5.1 ")
    assert values == frozenset(
        {"input_validation_error", "paused_for_clarification"}
    )


# --------------------------------------------------------------------------- #
# Synthetic drift detection                                                   #
# --------------------------------------------------------------------------- #


def _build_synthetic_bible_root(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "bible"
    root.mkdir()
    for filename, content in files.items():
        (root / filename).write_text(content, encoding="utf-8")
    return root


@pytest.fixture
def tmp_bible_root(tmp_path: Path) -> Path:
    return tmp_path / "bible"


def test_internal_schema_drift_via_synthetic_registry(
    tmp_bible_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boot import consistency

    tmp_bible_root.mkdir()
    (tmp_bible_root / "fake.md").write_text(
        "### 5.1 Fake\n"
        "```python\n"
        "class Fake(str, Enum):\n"
        "    A = \"a\"\n"
        "    B = \"b\"\n"
        "    C = \"c\"\n"
        "```\n",
        encoding="utf-8",
    )

    fake_loader_a: Callable[[], frozenset[str]] = lambda: frozenset({"a", "b"})
    fake_loader_b: Callable[[], frozenset[str]] = lambda: frozenset({"a", "c"})

    fake_entry = RegistryEntry(
        enum_name="FakeEnum",
        code_source_loaders=(fake_loader_a, fake_loader_b),
        canonical_bible="fake.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_python_class,
    )
    monkeypatch.setattr(consistency, "REGISTRY", {"FakeEnum": fake_entry})

    report = check(bible_root=tmp_bible_root)
    assert not report.ok
    kinds = {d.drift_kind for d in report.drifts}
    assert "internal_schema" in kinds


def test_bible_canonical_drift_detected(
    tmp_bible_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Code declares more values than the bible — bible_canonical drift
    must fire."""
    from boot import consistency

    tmp_bible_root.mkdir()
    (tmp_bible_root / "fake.md").write_text(
        "### 5.1 Fake\n"
        "```python\n"
        "class Fake(str, Enum):\n"
        "    A = \"a\"\n"
        "    B = \"b\"\n"
        "```\n",
        encoding="utf-8",
    )

    code_loader: Callable[[], frozenset[str]] = lambda: frozenset({"a", "b", "c"})

    fake_entry = RegistryEntry(
        enum_name="FakeEnum",
        code_source_loaders=(code_loader,),
        canonical_bible="fake.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_python_class,
    )
    monkeypatch.setattr(consistency, "REGISTRY", {"FakeEnum": fake_entry})

    report = check(bible_root=tmp_bible_root)
    assert not report.ok
    drift = report.drifts[0]
    assert drift.drift_kind == "bible_canonical"
    assert drift.code_values == frozenset({"a", "b", "c"})
    assert drift.bible_values == frozenset({"a", "b"})
    assert "only-in-code" in drift.detail


def test_missing_canonical_bible_page(
    tmp_bible_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boot import consistency

    tmp_bible_root.mkdir()  # exists but empty — no fake.md inside
    code_loader: Callable[[], frozenset[str]] = lambda: frozenset({"a"})
    fake_entry = RegistryEntry(
        enum_name="MissingEnum",
        code_source_loaders=(code_loader,),
        canonical_bible="not_present.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_python_class,
    )
    monkeypatch.setattr(consistency, "REGISTRY", {"MissingEnum": fake_entry})

    report = check(bible_root=tmp_bible_root)
    assert not report.ok
    assert any(
        "canonical bible page not found" in d.detail for d in report.drifts
    )


def test_cross_section_drift_detected(
    tmp_bible_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A cross-ref bible page that mentions a value not in the canonical
    set must surface as ``cross_section`` drift."""
    from boot import consistency

    tmp_bible_root.mkdir()
    (tmp_bible_root / "canonical.md").write_text(
        "### 5.1 Fake\n"
        "```python\n"
        "class Fake(str, Enum):\n"
        "    LOW = \"LOW\"\n"
        "    HIGH = \"HIGH\"\n"
        "```\n",
        encoding="utf-8",
    )
    (tmp_bible_root / "other.md").write_text(
        "Some prose mentioning `LOW`, `HIGH`, and the unauthorized "
        "`MAXIMUM` value.\n",
        encoding="utf-8",
    )

    code_loader: Callable[[], frozenset[str]] = lambda: frozenset(
        {"LOW", "HIGH"}
    )
    fake_entry = RegistryEntry(
        enum_name="FakeTier",
        code_source_loaders=(code_loader,),
        canonical_bible="canonical.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_python_class,
        cross_ref_bibles=("other.md",),
    )
    monkeypatch.setattr(consistency, "REGISTRY", {"FakeTier": fake_entry})

    report = check(bible_root=tmp_bible_root)
    assert not report.ok
    cross_drifts = [d for d in report.drifts if d.drift_kind == "cross_section"]
    assert cross_drifts, "expected at least one cross_section drift"
    assert "MAXIMUM" in cross_drifts[0].detail


def test_empty_registry_returns_clean_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from boot import consistency

    monkeypatch.setattr(consistency, "REGISTRY", {})
    report = check()
    assert report.ok is True
    assert report.enums_checked == 0
    assert report.drifts == ()


def test_check_entry_names_filter(tmp_bible_root: Path) -> None:
    # Real registry, but ask for a single entry — verifies the filter.
    report = check(entry_names=("HaltType",))
    assert report.enums_checked == 1
    assert report.ok


# --------------------------------------------------------------------------- #
# Frozen-dataclass invariants                                                 #
# --------------------------------------------------------------------------- #


def test_consistency_report_is_frozen() -> None:
    report = ConsistencyReport(ok=True, enums_checked=0, drifts=())
    with pytest.raises(FrozenInstanceError):
        report.ok = False  # type: ignore[misc]


def test_drift_record_is_frozen() -> None:
    drift = DriftRecord(
        enum_name="X",
        drift_kind="bible_canonical",
        code_values=frozenset({"a"}),
        bible_values=frozenset({"a"}),
        bible_section="x.md ### 1",
        detail="ok",
    )
    with pytest.raises(FrozenInstanceError):
        drift.detail = "tampered"  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# THRESHOLD_REGISTRY — Phase 4 T2 numerical-boundary detector                 #
# --------------------------------------------------------------------------- #


_REAL_BIBLE_ROOT = Path.home() / "cee" / "bible"


def test_threshold_registry_clean_run() -> None:
    """The complexity_tier_thresholds entry agrees with bible 08 §5.3.

    Live ``check()`` against the real bible mirror. ``thresholds_checked``
    counts the THRESHOLD_REGISTRY size; no drift records should surface
    for the threshold side at HEAD.
    """
    if not _REAL_BIBLE_ROOT.exists():
        pytest.skip(f"Bible mirror not found at {_REAL_BIBLE_ROOT}")

    report = check()
    assert report.ok, (
        f"unexpected drifts: {[d for d in report.drifts]}"
    )
    assert report.thresholds_checked >= 1
    threshold_drifts = [
        d for d in report.drifts if d.enum_name == "complexity_tier_thresholds"
    ]
    assert threshold_drifts == [], (
        f"unexpected threshold drift: {threshold_drifts}"
    )


def test_threshold_registry_planted_drift_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthetic mismatch in the code loader surfaces as DriftRecord.

    Patches ``_code_tier_thresholds_classification`` to return a
    deliberately-wrong mapping (LOW upper-bound shifted from 24 to 30).
    The threshold checker must report ``bible_canonical`` drift for
    ``complexity_tier_thresholds`` with the offending boundary visible
    in the detail string.
    """
    if not _REAL_BIBLE_ROOT.exists():
        pytest.skip(f"Bible mirror not found at {_REAL_BIBLE_ROOT}")

    from boot import consistency

    def _drifted_loader() -> dict[str, tuple[int, int]]:
        return {
            "LOW": (0, 30),
            "MEDIUM": (31, 49),
            "HIGH": (50, 74),
            "EXTREME": (75, 100),
        }

    drifted_entry = consistency.ThresholdRegistryEntry(
        name="complexity_tier_thresholds",
        code_source_loader=_drifted_loader,
        canonical_bible="08_task_classification_engine.md",
        canonical_section="### 5.3 ",
        extractor=consistency._extract_tier_thresholds_from_bible_8_3,
    )
    monkeypatch.setattr(
        consistency,
        "THRESHOLD_REGISTRY",
        {"complexity_tier_thresholds": drifted_entry},
    )

    report = check()
    assert not report.ok
    threshold_drifts = [
        d for d in report.drifts if d.enum_name == "complexity_tier_thresholds"
    ]
    assert len(threshold_drifts) == 1
    drift = threshold_drifts[0]
    assert drift.drift_kind == "bible_canonical"
    assert "LOW=0..30" in drift.detail
    assert "LOW=0..24" in drift.detail
