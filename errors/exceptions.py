"""CEE exception class hierarchy.

Authorized by System Design Bible section 19 §5.7. The pipeline driver
catches ``CEEException`` once and dispatches by isinstance per §5.8:

- ``PipelineHalt``   → halt artifact, RunResult(state="paused")
- ``RunError``       → error artifact, RunResult(state="failed")
- ``CEEException``   → other; treated as DRIVER_BUG
- ``Exception``      → non-CEE; logged critical, treated as DRIVER_BUG

Per Rule 2, all CEE exceptions inherit from ``CEEException`` so the driver
needs exactly one outer ``except``. Per §5.4 the payload shape varies by
halt_type; we do not validate shape here (per-halt schemas come later).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from errors.types import HaltType, RunErrorType

if TYPE_CHECKING:
    from boot.consistency import DriftRecord


class CEEException(Exception):
    """Base class for every CEE exception.

    Per bible §5.7 and Rule 2, the pipeline driver catches this once and
    dispatches by class. No exception that escapes a CEE module should
    bypass this base class — pure ``Exception`` subclasses are treated as
    DRIVER_BUG by the driver per §5.8.
    """


class PipelineHalt(CEEException):
    """A named pause point in the pipeline (bible §5.7).

    Pauses the Run with state preserved on disk. The OPERATOR takes a
    recovery action defined per halt_type in §5.4 and the Run resumes.
    The payload is a typed dict matching the halt_type; shape is not
    validated here (per-halt schemas live in later modules).
    """

    def __init__(self, halt_type: HaltType, payload: dict) -> None:
        self.halt_type = halt_type
        self.payload = payload
        super().__init__(f"Pipeline halted: {halt_type.value}")


class RunError(CEEException):
    """A terminal Run failure (bible §5.7).

    Marks the Run as ``failed``. Resume is unavailable; replay
    (``cee replay <run_id>``) remains. Recovery semantics are defined
    per error_type in §5.5.
    """

    def __init__(self, error_type: RunErrorType, payload: dict) -> None:
        self.error_type = error_type
        self.payload = payload
        super().__init__(f"Run errored: {error_type.value}")


class BootError(CEEException):
    """A boot sequence failure (bible §5.7).

    Raised by the boot module when CEE cannot reach a state where it
    accepts new Runs. ``step`` identifies the boot step (e.g. "B3");
    ``reason`` is a human-readable cause.
    """

    def __init__(self, step: str, reason: str) -> None:
        self.step = step
        self.reason = reason
        super().__init__(f"Boot failed at {step}: {reason}")


class BootConsistencyError(BootError):
    """Boot step B3 failed: closed-enum drift detected across bible+code.

    Carries the structured drift report from ``boot.consistency.check()``.
    The caller (``boot.sequencer``) raises this when ``ConsistencyReport.ok``
    is False so the driver can refuse to accept new Runs until the bible
    and code are reconciled (bible 00 §12 step B3, bible 20 §5.2).
    """

    def __init__(self, drifts: list["DriftRecord"]) -> None:
        self.drifts = drifts
        summary = f"{len(drifts)} drift(s) detected across closed enums"
        super().__init__(step="B3", reason=summary)


# ``BootBibleSyncError`` halt-cause taxonomy. Three values today:
#
# * ``mcp_connect_failed`` — bible 04 §5.6 step 2 ("halt before any page
#   fetch if connection fails"). Initial Anthropic / Notion MCP transport
#   failure; no pages have been touched yet.
# * ``page_deleted`` — bible 04 §9 EC9 ("Notion bible page deleted")
#   referenced from §5.6 ("halts with restore instruction rather than
#   treating the missing page as a transient failure").
# * ``credentials_missing`` — INFERRED halt cause. Bible 04 §5.2 makes
#   ``[anthropic] api_key`` a required precondition for sync-bible; bible
#   04 §5.6 step 1 says to read it. Neither §5.2 nor §5.6's failure-
#   handling list explicitly states "halt when missing". This kind=
#   value treats missing credentials as a connect-equivalent halt cause
#   (no pages can be touched) but the bible should canonize this
#   explicitly. Tracked as downstream candidate #13 at T6 commit time.
BootBibleSyncErrorKind = Literal[
    "mcp_connect_failed",
    "page_deleted",
    "credentials_missing",
]


class BootBibleSyncError(BootError):
    """Boot step B2 failed: ``cee sync-bible`` cannot proceed.

    Per bible 04 §5.6 ("Failure handling"), three halt causes exist
    where sync-bible refuses to start or stops globally instead of
    falling through to partial-with-warning:

    1. ``mcp_connect_failed`` — initial Anthropic / Notion MCP
       reachability check failed; bible 04 §5.6 mandates "halt
       immediately before any page is touched".
    2. ``page_deleted`` — EC9 surfaced; the parent bible page or a
       known child page has been deleted in Notion. Bible 04 §5.6
       "halts with restore instruction rather than treating the
       missing page as a transient failure".
    3. ``credentials_missing`` — INFERRED from bible 04 §5.2
       (credentials.toml schema requires ``[anthropic] api_key``
       when sync-bible runs) plus bible 04 §5.6 step 1 (read
       credentials first). Not in §5.6's explicit failure list;
       treated here as a connect-equivalent halt. Surface as
       downstream candidate #13.

    Per-page transient failures (network blip on one of N pages,
    write error on a single mirror file) are NOT halts — they go
    into ``SyncResult.failed`` and the sync loop continues per
    bible 04 §5.6's partial-with-warning default.
    """

    def __init__(
        self,
        *,
        reason: str,
        kind: BootBibleSyncErrorKind,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.kind: BootBibleSyncErrorKind = kind
        self.detail: dict[str, Any] = detail or {}
        super().__init__(step="B2", reason=f"{kind}: {reason}")


class ValidationError(CEEException):
    """Pydantic schema validation failure (bible §5.7, §8.3).

    Raised internally when a module emits an artifact that fails its
    schema. The driver wraps these as ``RunError(SCHEMA_VIOLATION)``
    per §8.3 — a module emitting an invalid artifact is a bug.
    """


class RoleAuthorityError(CEEException):
    """A role attempted a canon-modifying action it is not authorized for.

    Raised by the role enforcement layer (bible §02 §299). The Run halts;
    bug fix or authority change required before retry.
    """


class SubstrateBoundaryError(CEEException):
    """A writer wrote outside its declared substrate (bible §02 §303).

    Raised by the persistence layer when an artifact is written to a
    substrate the writing role does not own. Run halts; bug fix required.
    """


class RoleSurfaceViolation(CEEException):
    """A role accessed a path outside its allowed_reads/allowed_writes.

    Raised by the role surface enforcement layer per bible §02 §289.
    The Run halts; logged with role name and the attempted out-of-surface
    action.
    """


class InjectionDetected(PipelineHalt):
    """Convenience subclass of ``PipelineHalt`` for injection halts.

    Auto-sets ``halt_type`` to ``HaltType.INJECTION_DETECTED`` and stores
    the supplied flags as ``payload={"flags": flags}`` per bible §5.7.
    """

    def __init__(self, flags: list) -> None:
        super().__init__(
            halt_type=HaltType.INJECTION_DETECTED,
            payload={"flags": flags},
        )


class RedactionFailed(PipelineHalt):
    """Convenience subclass of ``PipelineHalt`` for redaction halts.

    Auto-sets ``halt_type`` to ``HaltType.REDACTION_FAILED`` and stores
    the supplied residual patterns as ``payload={"residual_patterns": ...}``
    per bible §5.7.
    """

    def __init__(self, residual_patterns: list) -> None:
        super().__init__(
            halt_type=HaltType.REDACTION_FAILED,
            payload={"residual_patterns": residual_patterns},
        )
