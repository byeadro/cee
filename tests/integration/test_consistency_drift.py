"""Integration tests for ``boot.consistency`` — end-to-end drift flows.

The unit tests in ``tests/unit/test_boot/test_consistency.py`` exercise
the registry shape, individual extractors, and synthetic drift-record
construction. These tests cover the full flow:

* Synthetic bibles + synthetic code mirrors are written to ``tmp_path``.
* ``check(bible_root=...)`` is invoked end-to-end with a patched
  registry.
* The report's ``ok`` flag and the boot-sequencer-level handoff to
  ``BootConsistencyError`` are asserted.

Each test models a realistic drift scenario the boot check exists to
catch.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from boot import consistency
from boot.consistency import (
    RegistryEntry,
    _extract_regex_html_table_backticks,
    _extract_regex_pipe_list,
    _extract_regex_python_class,
    check,
)
from errors import BootConsistencyError, BootError, CEEException


@pytest.fixture
def tmp_bible_root(tmp_path: Path) -> Path:
    root = tmp_path / "bible"
    root.mkdir()
    return root


# --------------------------------------------------------------------------- #
# 1. Drift: code declares a value the bible does not (python class shape)    #
# --------------------------------------------------------------------------- #


def test_drift_python_class_extra_value(
    tmp_bible_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bible §5.1 declares a 2-value enum; code adds a third value.
    The boot check must surface this as ``bible_canonical`` drift."""
    (tmp_bible_root / "fake.md").write_text(
        "### 5.1 Things\n"
        "```python\n"
        "class Things(str, Enum):\n"
        "    A = \"a\"\n"
        "    B = \"b\"\n"
        "```\n",
        encoding="utf-8",
    )
    code_loader: Callable[[], frozenset[str]] = lambda: frozenset(
        {"a", "b", "rogue"}
    )
    entry = RegistryEntry(
        enum_name="Things",
        code_source_loaders=(code_loader,),
        canonical_bible="fake.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_python_class,
    )
    monkeypatch.setattr(consistency, "REGISTRY", {"Things": entry})

    report = check(bible_root=tmp_bible_root)
    assert report.ok is False
    assert any(
        d.drift_kind == "bible_canonical" and "rogue" in d.detail
        for d in report.drifts
    )


# --------------------------------------------------------------------------- #
# 2. Drift: bible declares a value the code does not (HTML table shape)      #
# --------------------------------------------------------------------------- #


def test_drift_html_table_missing_value(
    tmp_bible_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bible §5.1 lists three values in an HTML table; code only has
    two. The check must surface this as ``bible_canonical`` drift,
    naming the missing value."""
    (tmp_bible_root / "fake.md").write_text(
        "### 5.1 Closed enum\n"
        "<table>\n"
        "<tr><td>Value</td></tr>\n"
        "<tr><td>`alpha`</td></tr>\n"
        "<tr><td>`beta`</td></tr>\n"
        "<tr><td>`gamma`</td></tr>\n"
        "</table>\n",
        encoding="utf-8",
    )
    code_loader: Callable[[], frozenset[str]] = lambda: frozenset(
        {"alpha", "beta"}
    )
    entry = RegistryEntry(
        enum_name="Greek",
        code_source_loaders=(code_loader,),
        canonical_bible="fake.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_html_table_backticks,
    )
    monkeypatch.setattr(consistency, "REGISTRY", {"Greek": entry})

    report = check(bible_root=tmp_bible_root)
    assert report.ok is False
    drift = [d for d in report.drifts if d.drift_kind == "bible_canonical"][0]
    assert "gamma" in drift.detail


# --------------------------------------------------------------------------- #
# 3. Drift: 4-way internal-schema disagreement                                #
# --------------------------------------------------------------------------- #


def test_drift_internal_schema_taskttype_4way(
    tmp_bible_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Four code mirrors of TaskType disagree pairwise. The check must
    flag at least one ``internal_schema`` drift; the boot sequencer
    will refuse to start until reconciliation."""
    (tmp_bible_root / "fake.md").write_text(
        "### 5.1 TaskType\n"
        "<table>\n"
        "<tr><td>Value</td></tr>\n"
        "<tr><td>`BUILD`</td></tr>\n"
        "<tr><td>`ANALYZE`</td></tr>\n"
        "<tr><td>`DEBUG`</td></tr>\n"
        "</table>\n",
        encoding="utf-8",
    )

    loaders = (
        lambda: frozenset({"BUILD", "ANALYZE", "DEBUG"}),
        lambda: frozenset({"BUILD", "ANALYZE", "DEBUG"}),
        lambda: frozenset({"BUILD", "ANALYZE"}),  # drifted: missing DEBUG
        lambda: frozenset({"BUILD", "ANALYZE", "DEBUG", "WRITE"}),  # drifted: extra
    )
    entry = RegistryEntry(
        enum_name="TaskType",
        code_source_loaders=loaders,
        canonical_bible="fake.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_html_table_backticks,
    )
    monkeypatch.setattr(consistency, "REGISTRY", {"TaskType": entry})

    report = check(bible_root=tmp_bible_root)
    assert report.ok is False
    internal = [d for d in report.drifts if d.drift_kind == "internal_schema"]
    # At least the two off-mirrors disagree with mirror #0.
    assert len(internal) >= 2


# --------------------------------------------------------------------------- #
# 4. Drift: cross-section bible mentions an unknown token                     #
# --------------------------------------------------------------------------- #


def test_drift_cross_section_unknown_token(
    tmp_bible_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Canonical bible declares the enum cleanly; another bible page
    mentions an extra value in backticks. ``cross_section`` drift is
    raised so the operator notices the dangling reference before it
    becomes a runtime bug."""
    (tmp_bible_root / "canonical.md").write_text(
        "### 5.2 Tier\n"
        "tier: low | medium | high\n",
        encoding="utf-8",
    )
    (tmp_bible_root / "other.md").write_text(
        "Cross-page narrative discussing `low`, `medium`, `high` and "
        "the wholly-unauthorized `extreme` value.\n",
        encoding="utf-8",
    )
    code_loader: Callable[[], frozenset[str]] = lambda: frozenset(
        {"low", "medium", "high"}
    )
    entry = RegistryEntry(
        enum_name="Tier",
        code_source_loaders=(code_loader,),
        canonical_bible="canonical.md",
        canonical_section="### 5.2 ",
        canonical_line=2,
        extractor=_extract_regex_pipe_list,
        cross_ref_bibles=("other.md",),
    )
    monkeypatch.setattr(consistency, "REGISTRY", {"Tier": entry})

    report = check(bible_root=tmp_bible_root)
    assert report.ok is False
    cross = [d for d in report.drifts if d.drift_kind == "cross_section"]
    assert cross, "expected cross_section drift"
    assert "extreme" in cross[0].detail


# --------------------------------------------------------------------------- #
# 5. No drift: bible + code agree (positive baseline)                         #
# --------------------------------------------------------------------------- #


def test_no_drift_clean_state(
    tmp_bible_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_bible_root / "fake.md").write_text(
        "### 5.1 Things\n"
        "```python\n"
        "class Things(str, Enum):\n"
        "    A = \"a\"\n"
        "    B = \"b\"\n"
        "```\n",
        encoding="utf-8",
    )
    code_loader: Callable[[], frozenset[str]] = lambda: frozenset({"a", "b"})
    entry = RegistryEntry(
        enum_name="Things",
        code_source_loaders=(code_loader,),
        canonical_bible="fake.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_python_class,
    )
    monkeypatch.setattr(consistency, "REGISTRY", {"Things": entry})

    report = check(bible_root=tmp_bible_root)
    assert report.ok is True
    assert report.drifts == ()
    assert report.enums_checked == 1


# --------------------------------------------------------------------------- #
# 6. Boot sequencer hand-off: drift report → BootConsistencyError              #
# --------------------------------------------------------------------------- #


def test_drift_caller_halts_via_BootConsistencyError(
    tmp_bible_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end shape the boot sequencer relies on: a non-clean
    report can be wrapped into ``BootConsistencyError`` and caught
    through the BootError / CEEException hierarchy. The drift list
    must round-trip through the exception payload."""
    (tmp_bible_root / "fake.md").write_text(
        "### 5.1 Things\n"
        "```python\n"
        "class Things(str, Enum):\n"
        "    A = \"a\"\n"
        "```\n",
        encoding="utf-8",
    )
    code_loader: Callable[[], frozenset[str]] = lambda: frozenset(
        {"a", "drifted"}
    )
    entry = RegistryEntry(
        enum_name="Things",
        code_source_loaders=(code_loader,),
        canonical_bible="fake.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_python_class,
    )
    monkeypatch.setattr(consistency, "REGISTRY", {"Things": entry})

    report = check(bible_root=tmp_bible_root)
    assert not report.ok

    try:
        if not report.ok:
            raise BootConsistencyError(drifts=list(report.drifts))
    except CEEException as exc:
        assert isinstance(exc, BootConsistencyError)
        assert isinstance(exc, BootError)
        assert exc.step == "B3"
        assert len(exc.drifts) == len(report.drifts)
        assert exc.drifts[0].enum_name == "Things"
    else:
        pytest.fail("BootConsistencyError did not propagate")
