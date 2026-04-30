"""CEE error subsystem.

Re-exports the closed error-state enums from bible section 19 §5.1–§5.3.
The exception hierarchy from §5.7 is added in task 7; this module exposes
only the enums for now.
"""

from errors.types import HaltType, RunErrorType, WarningType

__all__ = ["HaltType", "RunErrorType", "WarningType"]
