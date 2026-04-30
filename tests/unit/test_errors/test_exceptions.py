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
    BootError,
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
