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
    from schemas.clarification_request import ClarificationRequest
    from schemas.confirmation import ConfirmationRequest


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


# ``BootBibleSyncError`` halt-cause taxonomy. Four values today:
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
# * ``auto_sync_disabled`` — INFERRED halt cause added by T8. Bible 00
#   §12 step B2 canonizes the halt path itself ("else halts with
#   instruction to run it manually") when boot detects drift and
#   ``auto_sync = false``. The kind name is inferred. Tracked as
#   downstream candidate at T8 commit time.
BootBibleSyncErrorKind = Literal[
    "mcp_connect_failed",
    "page_deleted",
    "credentials_missing",
    "auto_sync_disabled",
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


BootEnvironmentErrorKind = Literal[
    "python_version",
    "missing_package",
    "path_not_writable",
    "config_invalid",
]


class BootEnvironmentError(BootError):
    """Boot step B1 failed: runtime environment unsuitable for CEE.

    Per bible 00 §12 step B1: "Check Python version, required packages,
    write permissions on ``~/cee/``, ``~/SecondBrain/cee/``. Halt on
    any failure." The four halt kinds discriminate the failure mode:

    * ``python_version`` — interpreter version below the floor.
    * ``missing_package`` — a required first-party module or third-
      party package failed to import.
    * ``path_not_writable`` — a required directory is missing or the
      user lacks write permission. Covers ``~/cee/``, the audit dir,
      and the Obsidian vault root per bible 02 §7.13's allowed_writes.
    * ``config_invalid`` — ``~/.cee/config.toml`` is missing or fails
      to parse / validate against :class:`schemas.Config`. Bible 00
      §12 B1 implies env validation; T8 reads the config here so B2
      can rely on it without re-loading.

    ``detail`` carries structured context (path that failed, package
    name, etc.) so the boot.log entry is useful for forensics.
    """

    def __init__(
        self,
        *,
        reason: str,
        kind: BootEnvironmentErrorKind,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.kind: BootEnvironmentErrorKind = kind
        self.detail: dict[str, Any] = detail or {}
        super().__init__(step="B1", reason=f"{kind}: {reason}")


BootRegistryErrorKind = Literal["skill", "agent"]


class BootRegistryError(BootError):
    """Boot step B4 or B5 failed catastrophically.

    Per bible 00 §12 step B4: "Skills with invalid frontmatter are
    logged and skipped, not loaded." Per-entry parse failures are
    handled inside :func:`skill_engine.registry.rebuild` and
    :func:`agent_selector.registry.rebuild`; they do NOT raise.
    This class is for irrecoverable failures only — filesystem
    unreadable, atomic write to ``index.json`` failed, etc.

    ``kind`` discriminates which registry failed (and therefore
    which boot step):

    * ``skill`` → step B4 (``skill_engine.registry``).
    * ``agent`` → step B5 (``agent_selector.registry``).
    """

    def __init__(
        self,
        *,
        reason: str,
        kind: BootRegistryErrorKind,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.kind: BootRegistryErrorKind = kind
        self.detail: dict[str, Any] = detail or {}
        step = "B4" if kind == "skill" else "B5"
        super().__init__(step=step, reason=f"{kind}: {reason}")


class BootSchemaError(BootError):
    """Boot step B6 failed: a schemas/* module did not import cleanly.

    Per bible 00 §12 step B6: "Pre-compile all Pydantic models from
    ``~/cee/schemas/``." In Python this means importing every module
    under ``schemas/`` so its Pydantic classes go through validation-
    schema construction at class-definition time.

    Carries the offending module name (e.g. ``"sync_meta"``) and a
    ``detail`` payload with the underlying exception type so boot.log
    forensics can pinpoint the regression.
    """

    def __init__(
        self,
        *,
        reason: str,
        module_name: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.module_name: str = module_name
        self.detail: dict[str, Any] = detail or {}
        super().__init__(step="B6", reason=f"{module_name}: {reason}")


class BootRunIndexError(BootError):
    """Boot step B7 failed: cannot walk ``~/cee/runs/`` to build index.

    Per bible 00 §12 step B7: "Index the last 50 Run logs by
    ``IntentObject.goal`` for similarity search during Skill
    resolution." An EMPTY index is success, not failure — Phase 2
    substrate has no Run logs and B7 returns an empty index. This
    class is for IO-level failures only (runs dir unreadable,
    permission denied, etc.).
    """

    def __init__(
        self,
        *,
        reason: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self.detail: dict[str, Any] = detail or {}
        super().__init__(step="B7", reason=reason)


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


class AwaitingDestructiveConfirmation(PipelineHalt):
    """Convenience subclass of ``PipelineHalt`` for the destructive-action
    gate halt per bible 12 §5.4.

    Auto-sets ``halt_type`` to
    ``HaltType.AWAITING_DESTRUCTIVE_CONFIRMATION`` and stores the
    supplied :class:`schemas.ConfirmationRequest` (serialized to a JSON-
    safe dict) as ``payload={"request": <dump>}``. The pipeline driver
    writes this payload to ``halt.json`` per bible 19 §7.1; the CLI
    reads it to render the bible §5.4 lines 220-228 user-facing
    message.

    Mirrors the existing :class:`InjectionDetected` /
    :class:`RedactionFailed` constructor pattern: typed input, dict
    payload, no schema validation in the exception itself (per-halt
    schemas live elsewhere — here in :mod:`schemas.confirmation`).
    """

    def __init__(self, request: "ConfirmationRequest") -> None:
        super().__init__(
            halt_type=HaltType.AWAITING_DESTRUCTIVE_CONFIRMATION,
            payload={"request": request.model_dump(mode="json")},
        )


class NoExecutableIntent(PipelineHalt):
    """Convenience subclass of ``PipelineHalt`` for the interpreter
    pleasantry / non-actionable halt per bible 03 §5.2 Step 2 + bible
    01 EC12.

    Auto-sets ``halt_type`` to ``HaltType.NO_EXECUTABLE_INTENT``. The
    payload carries (a) ``reason`` discriminating the detection path
    (``regex_pleasantry`` for the pre-LLM regex-based pleasantry
    detector, ``claude_sentinel`` for the post-LLM detection of the
    T4-prompt-emitted sentinel goal ``"Input is empty or
    non-actionable"``); (b) a truncated ``raw_text_preview`` (first
    200 characters of the OPERATOR's input) for forensic readability
    of the halt artifact; and (c) the ``run_id`` so the pipeline
    driver writes the halt without re-deriving it.

    Mirrors the existing :class:`InjectionDetected` /
    :class:`RedactionFailed` constructor pattern: typed inputs, dict
    payload, no schema validation in the exception itself.
    """

    def __init__(
        self,
        *,
        reason: str,
        raw_text_preview: str,
        run_id: str,
    ) -> None:
        super().__init__(
            halt_type=HaltType.NO_EXECUTABLE_INTENT,
            payload={
                "reason": reason,
                "raw_text_preview": raw_text_preview,
                "run_id": run_id,
            },
        )


class PausedForClarification(PipelineHalt):
    """Convenience subclass of ``PipelineHalt`` for the interpreter
    ambiguity halt per bible 03 §5.2 Step 2 + bible 03 §5.3.

    Auto-sets ``halt_type`` to ``HaltType.PAUSED_FOR_CLARIFICATION``
    and stores the supplied :class:`schemas.ClarificationRequest`
    (serialized to a JSON-safe dict) as ``payload={"request": <dump>}``.
    The pipeline driver writes the request to
    ``~/cee/runs/<run_id>/clarification.json`` per bible 03 §5.3 and
    the wrapping payload to ``halt.json`` per bible 19 §7.1, then
    emits the questions to stdout.

    Mirrors :class:`AwaitingDestructiveConfirmation`: typed input,
    dict payload, no schema validation in the exception itself
    (per-halt schemas live in :mod:`schemas.clarification_request`).
    """

    def __init__(self, *, request: "ClarificationRequest") -> None:
        super().__init__(
            halt_type=HaltType.PAUSED_FOR_CLARIFICATION,
            payload={"request": request.model_dump(mode="json")},
        )
