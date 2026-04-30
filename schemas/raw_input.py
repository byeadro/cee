"""RawInput artifact schema.

Authorized by System Design Bible section 03 (Step 1) and section 04 §6.1.
RawInput is the very first pipeline artifact — produced by the OPERATOR's
``cee run`` invocation, captured by the pipeline driver before any module
runs. Persisted at ``~/cee/runs/<run_id>/raw_input.json``.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

# ISO 8601 sha256 hex check (64 lowercase hex chars).
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class Attachment(BaseModel):
    """One attached file referenced by RawInput.

    Files live at ``~/cee/runs/<run_id>/attachments/<path>`` (path is relative
    to that directory). The pipeline driver verifies disk presence before
    handing RawInput to the interpreter.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    filename: Annotated[str, Field(min_length=1)]
    content_type: Annotated[str, Field(min_length=1)]
    size_bytes: Annotated[int, Field(ge=0)]
    sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)]
    path: Annotated[str, Field(min_length=1)]


class RawInput(BaseModel):
    """The OPERATOR's raw, unstructured input to a Run.

    Per bible 03 Step 1: captured before any interpretation. Schema
    validation enforces non-empty text; the pipeline halts with
    INPUT_VALIDATION_ERROR or INPUT_EMPTY_ERROR if construction fails.
    The ``produced_by`` field is the only artifact in the pipeline whose
    producer is OPERATOR (the human role).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    text: Annotated[str, Field(min_length=1)]
    timestamp: Annotated[str, Field(min_length=1)]
    source: Literal["cli", "api", "resume", "replay"]
    attachments: list[Attachment] = Field(default_factory=list)
    target_executor: Literal["claude_code", "claude_ai", "api"] = "claude_code"
    # TODO task 9: replace with RoleEnum once roles/__init__.py defines it.
    produced_by: str = "OPERATOR"
