"""Tests for the CEE exception class hierarchy.

Verifies the 10 exception classes from bible section 19 §5.7 and the
dispatch shape from §5.8. The bible-grounding test parses the bible
mirror and fails if the implementation drifts from §5.7.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from errors import (
    BootBibleSyncError,
    BootConsistencyError,
    BootEnvironmentError,
    BootError,
    BootRegistryError,
    BootRunIndexError,
    BootSchemaError,
    CEEException,
    HaltType,
    InjectionDetected,
    PipelineHalt,
    RedactionFailed,
    RoleAuthorityError,
    RoleSurfaceViolation,
    RunError,
    RunErrorType,
    SubstrateBoundaryError,
    ValidationError,
)

# Bible mirror — the bible-grounding test reads this; tests skip if missing.
_BIBLE_PATH = Path.home() / "cee" / "bible" / "19_error_handling_failure_states.md"

# All named CEE exception classes for hierarchy parametrization.
_ALL_EXCEPTIONS: tuple[type[CEEException], ...] = (
    CEEException,
    PipelineHalt,
    RunError,
    BootError,
    ValidationError,
    RoleAuthorityError,
    SubstrateBoundaryError,
    RoleSurfaceViolation,
    InjectionDetected,
    RedactionFailed,
)

# Expected class names per bible §5.7 (frozenset literal so the drift
# detector fails closed if the implementation accidentally diverges).
EXPECTED_EXCEPTION_CLASS_NAMES = frozenset(
    {
        "CEEException",
        "PipelineHalt",
        "RunError",
        "BootError",
        "ValidationError",
        "RoleAuthorityError",
        "SubstrateBoundaryError",
        "RoleSurfaceViolation",
        "InjectionDetected",
        "RedactionFailed",
    }
)


# --------------------------------------------------------------------------- #
# Hierarchy                                                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("exc_cls", _ALL_EXCEPTIONS)
def test_all_inherit_from_cee_exception(exc_cls: type) -> None:
    assert issubclass(exc_cls, CEEException)


def test_cee_exception_inherits_from_exception() -> None:
    assert issubclass(CEEException, Exception)


def test_injection_detected_inherits_from_pipeline_halt() -> None:
    assert issubclass(InjectionDetected, PipelineHalt)


def test_redaction_failed_inherits_from_pipeline_halt() -> None:
    assert issubclass(RedactionFailed, PipelineHalt)


# --------------------------------------------------------------------------- #
# Construction                                                                #
# --------------------------------------------------------------------------- #


def test_pipeline_halt_stores_halt_type_and_payload() -> None:
    exc = PipelineHalt(HaltType.INPUT_VALIDATION_ERROR, {"field": "text"})
    assert exc.halt_type == HaltType.INPUT_VALIDATION_ERROR
    assert exc.payload == {"field": "text"}


def test_pipeline_halt_str_informative() -> None:
    exc = PipelineHalt(HaltType.INPUT_VALIDATION_ERROR, {})
    assert HaltType.INPUT_VALIDATION_ERROR.value in str(exc)


def test_run_error_stores_error_type_and_payload() -> None:
    exc = RunError(RunErrorType.SCHEMA_VIOLATION, {"module": "interpreter"})
    assert exc.error_type == RunErrorType.SCHEMA_VIOLATION
    assert exc.payload == {"module": "interpreter"}


def test_run_error_str_informative() -> None:
    exc = RunError(RunErrorType.SCHEMA_VIOLATION, {})
    assert RunErrorType.SCHEMA_VIOLATION.value in str(exc)


def test_boot_error_stores_step_and_reason() -> None:
    exc = BootError("B3", "schema check failed")
    assert exc.step == "B3"
    assert exc.reason == "schema check failed"
    assert "B3" in str(exc)
    assert "schema check failed" in str(exc)


def test_injection_detected_sets_halt_type_automatically() -> None:
    flags = [{"pattern": "ignore previous"}]
    exc = InjectionDetected(flags)
    assert exc.halt_type == HaltType.INJECTION_DETECTED
    assert exc.payload == {"flags": flags}


def test_redaction_failed_sets_halt_type_automatically() -> None:
    residual = ["ssn-like-pattern", "credit-card-like-pattern"]
    exc = RedactionFailed(residual)
    assert exc.halt_type == HaltType.REDACTION_FAILED
    assert exc.payload == {"residual_patterns": residual}


# --------------------------------------------------------------------------- #
# Catch behavior                                                              #
# --------------------------------------------------------------------------- #


def test_can_catch_pipeline_halt_via_cee_exception() -> None:
    try:
        raise PipelineHalt(HaltType.INPUT_VALIDATION_ERROR, {})
    except CEEException as exc:
        assert isinstance(exc, PipelineHalt)
    else:
        pytest.fail("CEEException did not catch PipelineHalt")


def test_can_catch_pipeline_halt_specifically() -> None:
    try:
        raise PipelineHalt(HaltType.INPUT_VALIDATION_ERROR, {})
    except PipelineHalt as exc:
        assert exc.halt_type == HaltType.INPUT_VALIDATION_ERROR
    else:
        pytest.fail("PipelineHalt did not catch itself")


def test_can_catch_injection_detected_as_pipeline_halt() -> None:
    try:
        raise InjectionDetected([{"pattern": "x"}])
    except PipelineHalt as exc:
        assert isinstance(exc, InjectionDetected)
        assert exc.halt_type == HaltType.INJECTION_DETECTED
    else:
        pytest.fail("PipelineHalt did not catch InjectionDetected")


def test_can_catch_injection_detected_specifically() -> None:
    try:
        raise InjectionDetected([{"pattern": "x"}])
    except InjectionDetected as exc:
        assert exc.payload == {"flags": [{"pattern": "x"}]}
    else:
        pytest.fail("InjectionDetected did not catch itself")


def test_run_error_does_not_match_pipeline_halt() -> None:
    caught_as_halt = False
    caught_as_run_error = False
    try:
        raise RunError(RunErrorType.SCHEMA_VIOLATION, {})
    except PipelineHalt:
        caught_as_halt = True
    except RunError:
        caught_as_run_error = True
    assert caught_as_halt is False
    assert caught_as_run_error is True


def test_validation_error_does_not_match_run_error() -> None:
    caught_as_run_error = False
    caught_as_validation_error = False
    try:
        raise ValidationError("bad artifact")
    except RunError:
        caught_as_run_error = True
    except ValidationError:
        caught_as_validation_error = True
    assert caught_as_run_error is False
    assert caught_as_validation_error is True


# --------------------------------------------------------------------------- #
# Driver dispatch shape (per bible §5.8)                                      #
# --------------------------------------------------------------------------- #


def _dispatch(exc: CEEException) -> str:
    """Mirror the §5.8 dispatch order: PipelineHalt → RunError → other."""
    if isinstance(exc, PipelineHalt):
        return "halt"
    if isinstance(exc, RunError):
        return "error"
    if isinstance(exc, CEEException):
        return "driver_bug"
    return "unknown"  # pragma: no cover - defensive


def test_dispatch_priority_pipeline_halt_first() -> None:
    halt = PipelineHalt(HaltType.INPUT_VALIDATION_ERROR, {})
    error = RunError(RunErrorType.SCHEMA_VIOLATION, {})
    injection = InjectionDetected([])
    boot = BootError("B0", "config missing")

    assert _dispatch(halt) == "halt"
    assert _dispatch(error) == "error"
    # InjectionDetected is a PipelineHalt — must dispatch as halt, not error.
    assert _dispatch(injection) == "halt"
    # BootError is neither PipelineHalt nor RunError — falls through.
    assert _dispatch(boot) == "driver_bug"


# --------------------------------------------------------------------------- #
# Bible-grounding (drift detector)                                            #
# --------------------------------------------------------------------------- #

# Inside §5.7's code fence, classes appear as: class Name(Parent):
# (Each class fits on one line in the bible's code block.)
_CLASS_LINE = re.compile(r"^\s*class\s+(\w+)\s*\(")


def _extract_class_names_from_section_5_7(bible_text: str) -> set[str]:
    """Walk the bible, find §5.7's code fence, return declared class names."""
    classes: set[str] = set()
    in_section_5_7 = False
    in_code_fence = False

    for raw_line in bible_text.splitlines():
        stripped = raw_line.strip()

        if stripped.startswith("#") and not in_code_fence:
            heading_match = re.match(r"^#+\s*(\d+\.\d+)\b", stripped)
            if heading_match:
                in_section_5_7 = heading_match.group(1) == "5.7"
            else:
                in_section_5_7 = False
            continue

        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue

        if in_section_5_7 and in_code_fence:
            class_match = _CLASS_LINE.match(raw_line)
            if class_match:
                classes.add(class_match.group(1))

    return classes


def test_exception_classes_match_bible() -> None:
    if not _BIBLE_PATH.exists():
        pytest.skip(f"Bible mirror not found at {_BIBLE_PATH}")

    bible_text = _BIBLE_PATH.read_text(encoding="utf-8")
    bible_classes = _extract_class_names_from_section_5_7(bible_text)
    impl_classes = {cls.__name__ for cls in _ALL_EXCEPTIONS}

    # Sanity: parser found the expected 10 classes from the bible itself.
    assert len(bible_classes) == 10, (
        f"Bible §5.7 parser found {len(bible_classes)} classes, expected 10. "
        f"Parser may be broken or bible has drifted. Found: "
        f"{sorted(bible_classes)}"
    )

    # The drift detector: implementation must equal bible exactly.
    assert impl_classes == bible_classes, (
        f"Exception hierarchy drifted from bible §5.7.\n"
        f"  Only in implementation: {sorted(impl_classes - bible_classes)}\n"
        f"  Only in bible:          {sorted(bible_classes - impl_classes)}"
    )

    # Defensive: implementation set also matches the literal expectation.
    assert impl_classes == EXPECTED_EXCEPTION_CLASS_NAMES


# --------------------------------------------------------------------------- #
# BootConsistencyError (Phase 2 task 5 — boot/consistency.py)                 #
# --------------------------------------------------------------------------- #
#
# BootConsistencyError extends BootError; it is NOT a canonical bible §5.7
# class. The bible-grounding test above intentionally excludes it. These
# tests cover the structural contract the boot sequencer relies on:
# step="B3", drifts payload preserved, catchable through the BootError /
# CEEException hierarchy.


def test_boot_consistency_error_inherits_from_boot_error() -> None:
    assert issubclass(BootConsistencyError, BootError)
    assert issubclass(BootConsistencyError, CEEException)
    assert issubclass(BootConsistencyError, Exception)


def test_boot_consistency_error_payload_preserved() -> None:
    drifts = [
        {"enum_name": "RunState", "drift_kind": "bible_canonical"},
        {"enum_name": "TaskType", "drift_kind": "internal_schema"},
    ]
    exc = BootConsistencyError(drifts=drifts)
    assert exc.drifts is drifts
    assert len(exc.drifts) == 2


def test_boot_consistency_error_step_is_B3() -> None:
    exc = BootConsistencyError(drifts=[])
    assert exc.step == "B3"


def test_boot_consistency_error_str_includes_count() -> None:
    exc = BootConsistencyError(drifts=[{"x": 1}, {"x": 2}, {"x": 3}])
    rendered = str(exc)
    assert "B3" in rendered
    assert "3" in rendered
    assert "drift" in rendered.lower()


def test_boot_consistency_error_caught_by_CEEException() -> None:
    try:
        raise BootConsistencyError(drifts=[])
    except CEEException as exc:
        assert isinstance(exc, BootConsistencyError)
    else:
        pytest.fail("CEEException did not catch BootConsistencyError")


def test_boot_consistency_error_caught_by_BootError() -> None:
    try:
        raise BootConsistencyError(drifts=[{"enum_name": "Foo"}])
    except BootError as exc:
        assert isinstance(exc, BootConsistencyError)
        assert exc.step == "B3"
        assert exc.drifts == [{"enum_name": "Foo"}]
    else:
        pytest.fail("BootError did not catch BootConsistencyError")


# --------------------------------------------------------------------------- #
# BootBibleSyncError (Phase 2 task 6 — boot/bible_sync.py)                    #
# --------------------------------------------------------------------------- #
#
# Like BootConsistencyError, BootBibleSyncError extends BootError and
# is NOT a canonical bible §5.7 class. The bible-grounding test above
# intentionally excludes it. These tests cover the structural contract
# the boot sequencer relies on: step="B2", kind in the closed
# Literal, detail payload preserved, catchable through BootError /
# CEEException.


def test_boot_bible_sync_error_inherits_from_boot_error() -> None:
    assert issubclass(BootBibleSyncError, BootError)
    assert issubclass(BootBibleSyncError, CEEException)
    assert issubclass(BootBibleSyncError, Exception)


def test_boot_bible_sync_error_step_is_B2() -> None:
    exc = BootBibleSyncError(kind="mcp_connect_failed", reason="anything")
    assert exc.step == "B2"


def test_boot_bible_sync_error_kind_preserved() -> None:
    for kind in ("mcp_connect_failed", "page_deleted", "credentials_missing"):
        exc = BootBibleSyncError(kind=kind, reason="r")  # type: ignore[arg-type]
        assert exc.kind == kind


def test_boot_bible_sync_error_detail_preserved() -> None:
    detail = {"parent_page_id": "abc", "exception_type": "ConnectionError"}
    exc = BootBibleSyncError(
        kind="mcp_connect_failed", reason="net down", detail=detail
    )
    assert exc.detail == detail


def test_boot_bible_sync_error_detail_defaults_to_empty_dict() -> None:
    exc = BootBibleSyncError(kind="page_deleted", reason="missing parent")
    assert exc.detail == {}


def test_boot_bible_sync_error_str_includes_kind_and_reason() -> None:
    exc = BootBibleSyncError(
        kind="credentials_missing", reason="no api_key in [anthropic]"
    )
    rendered = str(exc)
    assert "B2" in rendered
    assert "credentials_missing" in rendered
    assert "no api_key" in rendered


def test_boot_bible_sync_error_caught_by_CEEException() -> None:
    try:
        raise BootBibleSyncError(kind="mcp_connect_failed", reason="x")
    except CEEException as exc:
        assert isinstance(exc, BootBibleSyncError)
    else:
        pytest.fail("CEEException did not catch BootBibleSyncError")


def test_boot_bible_sync_error_caught_by_BootError() -> None:
    try:
        raise BootBibleSyncError(
            kind="page_deleted",
            reason="parent gone",
            detail={"parent_page_id": "abc"},
        )
    except BootError as exc:
        assert isinstance(exc, BootBibleSyncError)
        assert exc.step == "B2"
        assert exc.kind == "page_deleted"
        assert exc.detail == {"parent_page_id": "abc"}
    else:
        pytest.fail("BootError did not catch BootBibleSyncError")


# --------------------------------------------------------------------------- #
# BootBibleSyncErrorKind extension (Phase 2 task 8)                           #
# --------------------------------------------------------------------------- #
#
# T8 adds a fourth kind value: "auto_sync_disabled" (bible 00 §12 step B2
# halt path when drift detected and auto_sync = false). Surface as
# downstream candidate at commit.


def test_boot_bible_sync_error_kind_auto_sync_disabled() -> None:
    exc = BootBibleSyncError(
        kind="auto_sync_disabled",
        reason="drift detected and auto_sync=false",
    )
    assert exc.kind == "auto_sync_disabled"
    assert exc.step == "B2"
    assert "auto_sync_disabled" in str(exc)


# --------------------------------------------------------------------------- #
# BootEnvironmentError (Phase 2 task 8 — boot/sequencer.py B1)                #
# --------------------------------------------------------------------------- #


def test_boot_environment_error_inherits_from_boot_error() -> None:
    assert issubclass(BootEnvironmentError, BootError)
    assert issubclass(BootEnvironmentError, CEEException)


def test_boot_environment_error_step_is_B1() -> None:
    exc = BootEnvironmentError(reason="x", kind="python_version")
    assert exc.step == "B1"


@pytest.mark.parametrize(
    "kind",
    ["python_version", "missing_package", "path_not_writable", "config_invalid"],
)
def test_boot_environment_error_all_kinds(kind: str) -> None:
    exc = BootEnvironmentError(reason="any", kind=kind)  # type: ignore[arg-type]
    assert exc.kind == kind
    assert exc.step == "B1"
    assert kind in str(exc)


def test_boot_environment_error_detail_preserved() -> None:
    detail = {"actual": "3.9.7", "required": "3.10"}
    exc = BootEnvironmentError(
        reason="too old", kind="python_version", detail=detail
    )
    assert exc.detail == detail


def test_boot_environment_error_detail_defaults_to_empty_dict() -> None:
    exc = BootEnvironmentError(reason="x", kind="missing_package")
    assert exc.detail == {}


def test_boot_environment_error_caught_via_BootError() -> None:
    try:
        raise BootEnvironmentError(reason="x", kind="config_invalid")
    except BootError as exc:
        assert isinstance(exc, BootEnvironmentError)
        assert exc.step == "B1"
    else:
        pytest.fail("BootError did not catch BootEnvironmentError")


# --------------------------------------------------------------------------- #
# BootRegistryError (Phase 2 task 8 — boot/sequencer.py B4 + B5)              #
# --------------------------------------------------------------------------- #


def test_boot_registry_error_inherits_from_boot_error() -> None:
    assert issubclass(BootRegistryError, BootError)
    assert issubclass(BootRegistryError, CEEException)


def test_boot_registry_error_skill_kind_is_step_B4() -> None:
    exc = BootRegistryError(reason="permission denied", kind="skill")
    assert exc.step == "B4"
    assert exc.kind == "skill"


def test_boot_registry_error_agent_kind_is_step_B5() -> None:
    exc = BootRegistryError(reason="permission denied", kind="agent")
    assert exc.step == "B5"
    assert exc.kind == "agent"


def test_boot_registry_error_detail_preserved() -> None:
    detail = {"skills_dir": "/tmp/skills", "exception_type": "PermissionError"}
    exc = BootRegistryError(reason="r", kind="skill", detail=detail)
    assert exc.detail == detail


def test_boot_registry_error_caught_via_BootError() -> None:
    try:
        raise BootRegistryError(reason="x", kind="agent")
    except BootError as exc:
        assert isinstance(exc, BootRegistryError)
        assert exc.step == "B5"
    else:
        pytest.fail("BootError did not catch BootRegistryError")


# --------------------------------------------------------------------------- #
# BootSchemaError (Phase 2 task 8 — boot/sequencer.py B6)                     #
# --------------------------------------------------------------------------- #


def test_boot_schema_error_inherits_from_boot_error() -> None:
    assert issubclass(BootSchemaError, BootError)
    assert issubclass(BootSchemaError, CEEException)


def test_boot_schema_error_step_is_B6() -> None:
    exc = BootSchemaError(reason="syntax error", module_name="intent_object")
    assert exc.step == "B6"


def test_boot_schema_error_module_name_preserved() -> None:
    exc = BootSchemaError(reason="r", module_name="sync_meta")
    assert exc.module_name == "sync_meta"
    assert "sync_meta" in str(exc)


def test_boot_schema_error_caught_via_BootError() -> None:
    try:
        raise BootSchemaError(reason="x", module_name="config")
    except BootError as exc:
        assert isinstance(exc, BootSchemaError)
        assert exc.step == "B6"
        assert exc.module_name == "config"
    else:
        pytest.fail("BootError did not catch BootSchemaError")


# --------------------------------------------------------------------------- #
# BootRunIndexError (Phase 2 task 8 — boot/sequencer.py B7)                   #
# --------------------------------------------------------------------------- #


def test_boot_run_index_error_inherits_from_boot_error() -> None:
    assert issubclass(BootRunIndexError, BootError)
    assert issubclass(BootRunIndexError, CEEException)


def test_boot_run_index_error_step_is_B7() -> None:
    exc = BootRunIndexError(reason="permission denied")
    assert exc.step == "B7"


def test_boot_run_index_error_detail_preserved() -> None:
    detail = {"runs_dir": "/tmp/runs", "exception_type": "OSError"}
    exc = BootRunIndexError(reason="r", detail=detail)
    assert exc.detail == detail


def test_boot_run_index_error_caught_via_BootError() -> None:
    try:
        raise BootRunIndexError(reason="x")
    except BootError as exc:
        assert isinstance(exc, BootRunIndexError)
        assert exc.step == "B7"
    else:
        pytest.fail("BootError did not catch BootRunIndexError")
