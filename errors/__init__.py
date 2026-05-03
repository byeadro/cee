"""CEE error subsystem.

Re-exports the closed error-state enums from bible section 19 §5.1–§5.3 and
the exception class hierarchy from §5.7.
"""

from errors.exceptions import (
    AwaitingDestructiveConfirmation,
    BootBibleSyncError,
    BootConsistencyError,
    BootEnvironmentError,
    BootError,
    BootRegistryError,
    BootRunIndexError,
    BootSchemaError,
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
    # BootError subclasses added by Phase 2 task 8 (boot/sequencer.py)
    "BootEnvironmentError",
    "BootRegistryError",
    "BootSchemaError",
    "BootRunIndexError",
    "ValidationError",
    "RoleAuthorityError",
    "SubstrateBoundaryError",
    "RoleSurfaceViolation",
    "InjectionDetected",
    "RedactionFailed",
    # Phase 3 T8 — destructive-action gate (bible 12 §5.4)
    "AwaitingDestructiveConfirmation",
]
