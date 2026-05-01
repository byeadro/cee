"""CEE error subsystem.

Re-exports the closed error-state enums from bible section 19 §5.1–§5.3 and
the exception class hierarchy from §5.7.
"""

from errors.exceptions import (
    BootBibleSyncError,
    BootConsistencyError,
    BootError,
    CEEException,
    InjectionDetected,
    PipelineHalt,
    RedactionFailed,
    RoleAuthorityError,
    RoleSurfaceViolation,
    RunError,
    SubstrateBoundaryError,
    ValidationError,
)
from errors.types import HaltType, RunErrorType, WarningType

__all__ = [
    # Enums (task 6)
    "HaltType",
    "RunErrorType",
    "WarningType",
    # Exception hierarchy (task 7)
    "CEEException",
    "PipelineHalt",
    "RunError",
    "BootError",
    "BootConsistencyError",
    "BootBibleSyncError",
    "ValidationError",
    "RoleAuthorityError",
    "SubstrateBoundaryError",
    "RoleSurfaceViolation",
    "InjectionDetected",
    "RedactionFailed",
]
