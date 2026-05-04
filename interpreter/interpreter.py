"""INTERPRETER pipeline-step module.

Phase 4 T5 — Track B close. Authorized by:

* **Bible 03 §5.2 Step 2** — INTERPRETER converts ``RawInput`` to
  ``IntentObject`` via temperature-0 Claude call with the fixed
  system prompt at ``~/cee/prompts/interpreter_system.txt``. Loads
  bible §00, §01, and recent Run logs for context. Halts via
  ``paused_for_clarification`` (ambiguity_score > 0.6) or
  ``no_executable_intent`` (pleasantry / non-actionable).
* **Bible 03 §5.3** — clarification cycle. T5 raises
  ``PausedForClarification`` carrying a populated
  :class:`schemas.ClarificationRequest`; the pipeline driver
  persists ``clarification.json`` and emits to stdout.
* **Bible 02 §7.2** — INTERPRETER read surface (``RawInput``,
  recent Run logs (last 50), bible §00, §01) and write surface
  ("``IntentObject`` (in-memory; persisted by ``PERSISTENCE_WRITER``)").
  T5 does NOT write filesystem artifacts — it returns the
  ``IntentObject`` or raises a ``PipelineHalt`` carrying the halt
  payload, and the pipeline driver (Phase 5+) handles persistence.
* **Bible 12 §5.8** — every system-role action emits a hash-chained
  JSONL entry to ``~/cee/audit/roles.log``. T5 emits two events per
  ``Interpreter.run()`` call: ``pipeline_step_start`` at entry and
  ``pipeline_step_complete`` at exit (via ``try/finally``). The T3
  client emits the nested ``llm_call`` event automatically.
* **Bible 19 §5.1, §5.4, §5.7** — closed ``HaltType`` enum +
  per-halt recovery semantics + exception class hierarchy. T5
  raises two halt types (``NO_EXECUTABLE_INTENT``,
  ``PAUSED_FOR_CLARIFICATION``) and one error type
  (``SCHEMA_VIOLATION``). The convenience halt subclasses
  ``NoExecutableIntent`` / ``PausedForClarification`` ship in
  ``errors/exceptions.py`` alongside the existing
  ``InjectionDetected`` / ``RedactionFailed`` /
  ``AwaitingDestructiveConfirmation`` precedent.
* **Bible 19 §8.3** — Pydantic / JSON validation failures on Claude
  output propagate as ``RunError(SCHEMA_VIOLATION)``: a module
  emitting an out-of-schema artifact is a module bug, not a
  pause-point.
* **Bible 04 §4 Rule 3** — canonical ``run_id`` pattern
  (``YYYYMMDD_HHMMSS_8hex``); T5 uses ``paths.derive_run_dir`` for
  validated run-directory access.

**Pleasantry detection** (candidate #64, canonical-by-shipped-state).
Six closed regex patterns cover whitespace-only, greetings, thanks,
acknowledgements, farewells, and punctuation-only inputs. Bare
"yes" / "no" are treated as pleasantry in Phase 4 — T5 has no
conversation-context awareness; revisit with Phase 7's pipeline
driver when replay/conversation context exists.

**Bible context injection** (candidate #65, canonical-by-shipped-state).
Single user message with delimiter headers
(``## BIBLE_CONTEXT`` / ``## RECENT_RUNS`` / ``## RAW_INPUT:``)
matching T4 prompt's INPUT-section accommodation. Bible 03 §5.2
Step 2 names the loaded artifacts but does not specify wire
format; T5 ships this format pending bible canonicalization.

**Recent-runs loader.** Walks ``paths.RUNS_DIR``, validates each
subdirectory name against the canonical ``run_id`` pattern via
``paths.derive_run_dir``, reads ``intent.json``, extracts ``goal``.
Silent skip on non-canonical name, missing ``intent.json``,
malformed JSON, or missing ``goal`` field. Sorts descending by
``run_id`` — lexicographic order matches chronological order for
the canonical pattern, with the 8-char-hex tail providing a stable
tiebreaker for same-second runs. Independent from
``boot/sequencer.py`` B7 (which drifted from canon — surfaced as
candidate #66).

**Determinism contract.** Same ``RawInput`` + ``run_id`` + bible
state + recent runs produces the same Claude input (input_hash
stable across calls). Claude itself may produce small drift across
runs at temperature 0 — captured by Phase 4 T12's determinism test
framework.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError as PydanticValidationError

import paths
from errors import (
    NoExecutableIntent,
    PausedForClarification,
    RunError,
    RunErrorType,
)
from llm import LLMClient
from persistence.audit import audit_log_append
from roles import RoleEnum
from schemas.clarification_request import (
    ClarificationQuestion,
    ClarificationRequest,
)
from schemas.config import Config, InterpreterConfig as _BibleInterpreterConfig
from schemas.intent_object import IntentObject
from schemas.raw_input import RawInput


# --------------------------------------------------------------------------- #
# Pleasantry detection                                                        #
# --------------------------------------------------------------------------- #


# Closed 6-pattern set. Each pattern is anchored at start and end so partial
# matches inside longer actionable inputs do not trip the detector.
#
# - whitespace-only: defense-in-depth (RawInput schema also rejects).
# - greetings: bare "hi" / "hello" / etc. without an actionable trailer.
# - thanks: bare "thanks" / "thank you" / etc. (the negative-test case
#   "thanks much I appreciate it" passes through because the trailing
#   "I appreciate it" extends past the regex's end-anchor).
# - acknowledgements: bare "ok" / "yes" / "no" / etc. Bare yes/no are
#   pleasantry-treated in Phase 4 since T5 has no prior-turn context;
#   conversation-context handling is part of candidate #64.
# - farewells: bare "bye" / "goodbye" / etc.
# - punctuation-only: "?" / "!" / "..." with no semantic content.
_PLEASANTRY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*$"),
    re.compile(
        r"^\s*(hi|hello|hey|good\s+(morning|afternoon|evening)|yo|sup|howdy)"
        r"[!.\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(thanks|thank\s+you|ty|thx|appreciated|cheers)[!.\s]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(ok|okay|cool|nice|great|fine|sure|yes|no|maybe|alright|"
        r"got\s+it)[!.\s?]*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(bye|goodbye|see\s+ya|later|night)[!.\s]*$",
        re.IGNORECASE,
    ),
    re.compile(r"^\s*[?!.]+\s*$"),
)


def _is_pleasantry(text: str) -> bool:
    """Return ``True`` if ``text`` matches any pleasantry pattern.

    Pure regex scan over the closed :data:`_PLEASANTRY_PATTERNS` set.
    No conversation-context awareness; bare "yes" / "no" are treated
    as pleasantry in Phase 4. Surfaced as part of candidate #64.
    """
    return any(pattern.match(text) for pattern in _PLEASANTRY_PATTERNS)


# --------------------------------------------------------------------------- #
# Sentinel + fallback constants                                               #
# --------------------------------------------------------------------------- #


# T4-prompt-emitted sentinel goal: emit when Claude detects empty / non-
# actionable input. Pattern-match exactly (the prompt instructs Claude to
# use this literal string).
_CLAUDE_SENTINEL_GOAL: str = "Input is empty or non-actionable"


# Single deterministic fallback question used when the IntentObject's
# ``implicit_assumptions`` list is empty at clarification halt time.
# Bible silent on the fallback wording; this string is canonical-by-
# shipped-state (part of candidate #64's ambit).
_GENERIC_CLARIFICATION_QUESTION: str = (
    "What specifically should I help you accomplish? The current input "
    "is too ambiguous to proceed."
)


# Identifier slug for the generic fallback question. Must match the
# ClarificationQuestion pattern (lowercase alphanumeric + hyphens).
_GENERIC_QUESTION_ID: str = "ambiguity-clarification"


# --------------------------------------------------------------------------- #
# Bible + run-log context loaders                                             #
# --------------------------------------------------------------------------- #


# Recent-runs loader limit per bible 02 §7.2 ("recent Run logs (last 50)").
_RECENT_RUNS_LIMIT: int = 50


def _load_bible_context(*, bible_dir: Path | None = None) -> str:
    """Load bible §00 + §01 concatenated with delimiter headers.

    Returns a string suitable for inclusion in T5's user message under
    the ``## BIBLE_CONTEXT`` block. Reads
    ``bible/00_project_vision.md`` and ``bible/01_real_problem_breakdown.md``
    via ``paths.BIBLE_DIR`` (overridable for tests).

    Raises
    ------
    OSError
        If either bible file cannot be read. Per bible 03 §5.2 Step 2
        this is a hard precondition — if the bible mirror is broken,
        the interpreter should not silently degrade. Callers wrap as
        appropriate (boot's B2 normally guarantees these files exist).
    """
    root = bible_dir if bible_dir is not None else paths.BIBLE_DIR
    files = (
        "00_project_vision.md",
        "01_real_problem_breakdown.md",
    )
    blocks: list[str] = []
    for filename in files:
        path = root / filename
        content = path.read_text(encoding="utf-8")
        blocks.append(f"### bible/{filename}\n{content}")
    return "\n\n".join(blocks)


def _load_recent_runs(
    *,
    runs_dir: Path | None = None,
    limit: int = _RECENT_RUNS_LIMIT,
) -> list[tuple[str, str]]:
    """Walk ``runs_dir`` for canonical Run directories and read goals.

    Returns up to ``limit`` ``(run_id, goal)`` tuples sorted descending
    by ``run_id``. Lexicographic descending sort matches chronological
    descending order for the bible 04 §4 Rule 3 pattern
    (``YYYYMMDD_HHMMSS_8hex``); the hex tail provides a deterministic
    tiebreaker for same-second runs.

    Silently skips any directory whose name fails the canonical
    ``run_id`` validation (raised by ``paths.derive_run_dir``), whose
    ``intent.json`` is missing, whose JSON is malformed, or whose
    ``goal`` field is missing or non-string. No audit emission for
    skipped runs — silent skip is the documented contract.

    Returns an empty list if ``runs_dir`` itself is absent (Phase 4
    state — no real runs persisted yet).
    """
    root = runs_dir if runs_dir is not None else paths.RUNS_DIR
    if not root.exists() or not root.is_dir():
        return []

    candidates: list[tuple[str, str]] = []
    try:
        children = list(root.iterdir())
    except OSError:
        return []

    for child in children:
        if not child.is_dir():
            continue
        if child.name == "golden":
            continue
        try:
            paths.derive_run_dir(child.name)
        except ValueError:
            continue
        intent_path = child / "intent.json"
        if not intent_path.exists():
            continue
        try:
            data = json.loads(intent_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        goal = data.get("goal") if isinstance(data, dict) else None
        if not isinstance(goal, str) or not goal:
            continue
        candidates.append((child.name, goal))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    return candidates[:limit]


def _format_recent_runs_block(runs: list[tuple[str, str]]) -> str:
    """Render the ``## RECENT_RUNS`` body from a (run_id, goal) list.

    Empty list yields the empty-section sentinel ``(no recent runs)``
    so the prompt block remains structurally consistent.
    """
    if not runs:
        return "(no recent runs)"
    return "\n".join(f"{run_id}: {goal}" for run_id, goal in runs)


def _build_user_message(
    raw_input: RawInput,
    bible_ctx: str,
    run_ctx: list[tuple[str, str]],
) -> str:
    """Compose the user message per bible 03 §5.2 Step 2 + T4 prompt INPUT.

    Format (delimiter headers exactly as below; T4 prompt instructs
    Claude to focus on the ``RAW_INPUT:`` line):

        ## BIBLE_CONTEXT
        <bible_ctx>

        ## RECENT_RUNS
        <run_ctx as run_id: goal lines, or "(no recent runs)">

        ## RAW_INPUT:
        <raw_input.text>

    Surfaced as candidate #65 (canonical-by-shipped-state pending
    bible canonicalization of the wire format).
    """
    runs_block = _format_recent_runs_block(run_ctx)
    return (
        "## BIBLE_CONTEXT\n"
        f"{bible_ctx}\n"
        "\n"
        "## RECENT_RUNS\n"
        f"{runs_block}\n"
        "\n"
        "## RAW_INPUT:\n"
        f"{raw_input.text}"
    )


# --------------------------------------------------------------------------- #
# JSON parse + schema validation                                              #
# --------------------------------------------------------------------------- #


def _parse_intent_json(text: str) -> dict[str, Any]:
    """Parse Claude's text output as JSON.

    Raises ``json.JSONDecodeError`` on parse failure. Caller wraps as
    ``RunError(SCHEMA_VIOLATION)`` per bible 19 §8.3.
    """
    return json.loads(text)


def _validate_intent(data: dict[str, Any]) -> IntentObject:
    """Schema-validate a parsed JSON dict as an :class:`IntentObject`.

    Always overwrites ``produced_by`` to ``RoleEnum.INTERPRETER`` per
    bible 02 §7.2 (the artifact's provenance is the role that
    produced it; T4's prompt explicitly instructs Claude not to emit
    this field). If Claude emits ``produced_by`` despite the prompt
    instruction, ``extra="forbid"`` would otherwise reject — we strip
    Claude's value and inject the canonical one before validation.

    Raises ``pydantic.ValidationError`` on schema failure (caller
    wraps as ``RunError(SCHEMA_VIOLATION)`` per bible 19 §8.3).
    """
    if isinstance(data, dict):
        data = {k: v for k, v in data.items() if k != "produced_by"}
        data["produced_by"] = RoleEnum.INTERPRETER
    return IntentObject.model_validate(data)


# --------------------------------------------------------------------------- #
# ClarificationRequest construction                                           #
# --------------------------------------------------------------------------- #


def _slugify_assumption_id(index: int) -> str:
    """Stable slug for an assumption-derived ClarificationQuestion id.

    Format ``assumption-<index>`` matches the ClarificationQuestion
    id pattern (``^[a-z0-9][a-z0-9-]{0,59}$``) and is deterministic.
    """
    return f"assumption-{index}"


def _build_clarification_request(
    intent: IntentObject,
    *,
    run_id: str,
    now_iso: str,
) -> ClarificationRequest:
    """Build a ClarificationRequest from a high-ambiguity IntentObject.

    One question per ``intent.implicit_assumptions`` entry, each in
    the deterministic format::

        "You assumed: {assumption}. Is that correct?"

    Fallback when ``implicit_assumptions`` is empty: a single generic
    question (``_GENERIC_CLARIFICATION_QUESTION``) with id
    ``ambiguity-clarification``.

    ``paused_at_step`` is always 2 per bible 03 §5.2 step numbering.
    """
    questions: list[ClarificationQuestion]
    if intent.implicit_assumptions:
        questions = [
            ClarificationQuestion(
                id=_slugify_assumption_id(index),
                question=f"You assumed: {assumption}. Is that correct?",
                expected_answer_type="yes_no",
            )
            for index, assumption in enumerate(intent.implicit_assumptions)
        ]
    else:
        questions = [
            ClarificationQuestion(
                id=_GENERIC_QUESTION_ID,
                question=_GENERIC_CLARIFICATION_QUESTION,
                expected_answer_type="free_text",
            )
        ]

    return ClarificationRequest(
        run_id=run_id,
        questions=questions,
        paused_at_step=2,
        intent_object_so_far=intent.model_dump(mode="json"),
        paused_at_iso_timestamp=now_iso,
    )


# --------------------------------------------------------------------------- #
# Audit emission                                                              #
# --------------------------------------------------------------------------- #


def _hash_raw_input(raw_input: RawInput) -> str:
    """SHA-256 of the OPERATOR's input text for forensic correlation.

    Same hash function T3 uses for input_hash on the LLM call side;
    here the input is just the text (no model/system context), which
    is sufficient for correlation between RawInput and llm_call audit
    events.
    """
    return hashlib.sha256(raw_input.text.encode("utf-8")).hexdigest()


def _audit_step_start(*, run_id: str, raw_input: RawInput) -> None:
    """Emit ``pipeline_step_start`` to ``paths.AUDIT_ROLES_LOG``.

    Details: ``{step: 2, raw_input_hash: <sha256>, source: <raw_input.source>}``.
    """
    audit_log_append(
        log_path=paths.AUDIT_ROLES_LOG,
        actor=RoleEnum.INTERPRETER.value,
        event="pipeline_step_start",
        details={
            "step": 2,
            "raw_input_hash": _hash_raw_input(raw_input),
            "source": raw_input.source,
        },
        run_id=run_id,
    )


def _audit_step_complete(
    *,
    run_id: str,
    outcome: str,
    ambiguity_score: float | None,
    duration_ms: int,
) -> None:
    """Emit ``pipeline_step_complete`` to ``paths.AUDIT_ROLES_LOG``.

    Details: ``{step: 2, outcome: <str>, ambiguity_score: <float|None>,
    duration_ms: <int>}``. ``outcome`` is one of
    ``success``, ``halt:no_executable_intent``,
    ``halt:paused_for_clarification``, ``error:schema_violation``,
    ``error:other``.
    """
    audit_log_append(
        log_path=paths.AUDIT_ROLES_LOG,
        actor=RoleEnum.INTERPRETER.value,
        event="pipeline_step_complete",
        details={
            "step": 2,
            "outcome": outcome,
            "ambiguity_score": ambiguity_score,
            "duration_ms": duration_ms,
        },
        run_id=run_id,
    )


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class InterpreterConfig:
    """Frozen interpreter knobs per bible 04 §5.2 ``[interpreter]`` block.

    Mirrors :class:`schemas.config.InterpreterConfig` but as a frozen
    dataclass so the runtime can pass it around without holding the
    full Pydantic model. Construction with no arguments yields the
    bible-default values (0.6 / 0.3) without requiring a config file
    on disk — useful for tests and for the empty-config fast path.
    """

    ambiguity_clarification_threshold: float = 0.6
    ambiguity_visible_threshold: float = 0.3

    def __post_init__(self) -> None:
        # Mirror the Pydantic cross-validator from schemas/config.py so
        # the two paths cannot disagree at runtime.
        if not 0.0 <= self.ambiguity_visible_threshold <= 1.0:
            raise ValueError(
                f"ambiguity_visible_threshold "
                f"({self.ambiguity_visible_threshold}) out of [0.0, 1.0]"
            )
        if not 0.0 <= self.ambiguity_clarification_threshold <= 1.0:
            raise ValueError(
                f"ambiguity_clarification_threshold "
                f"({self.ambiguity_clarification_threshold}) out of [0.0, 1.0]"
            )
        if (
            self.ambiguity_visible_threshold
            >= self.ambiguity_clarification_threshold
        ):
            raise ValueError(
                "ambiguity_visible_threshold must be strictly less than "
                "ambiguity_clarification_threshold per bible 03 §5.2"
            )

    @classmethod
    def from_bible_config(
        cls, bible_config: _BibleInterpreterConfig
    ) -> "InterpreterConfig":
        """Adapt a Pydantic ``Config.interpreter`` block to the runtime form."""
        return cls(
            ambiguity_clarification_threshold=(
                bible_config.ambiguity_clarification_threshold
            ),
            ambiguity_visible_threshold=bible_config.ambiguity_visible_threshold,
        )

    @classmethod
    def from_user_config(cls) -> "InterpreterConfig":
        """Read ``~/.cee/config.toml`` and adapt the ``[interpreter]`` block.

        Falls back to defaults if the file is absent. Caller may
        prefer to inject an explicit ``InterpreterConfig`` rather than
        depending on filesystem state at construction time.
        """
        if not paths.CONFIG_FILE.exists():
            return cls()
        raw = paths.CONFIG_FILE.read_text(encoding="utf-8")
        config = Config.model_validate(tomllib.loads(raw))
        return cls.from_bible_config(config.interpreter)


# --------------------------------------------------------------------------- #
# Interpreter                                                                 #
# --------------------------------------------------------------------------- #


# Deferred system-prompt path; read at call time so tests that monkey-patch
# ``paths.PROMPTS_DIR`` get the patched path without re-import.
def _system_prompt_path() -> Path:
    return paths.PROMPTS_DIR / "interpreter_system.txt"


class Interpreter:
    """The CEE INTERPRETER pipeline-step module.

    Per bible 03 §5.2 Step 2: invoked by the pipeline driver as
    ``Interpreter(...).run(raw_input, run_id=...)``. Returns an
    ``IntentObject`` on the silent (< visible_threshold) and visible
    ([visible_threshold, clarification_threshold]) bands; raises a
    ``PipelineHalt`` on the clarification (> clarification_threshold)
    and pleasantry/sentinel paths; raises a ``RunError`` when Claude
    emits a malformed or out-of-schema artifact.

    DI surface: ``client`` is the :class:`llm.LLMClient` (production:
    :class:`llm.LiveAnthropicClient`; tests: SDK monkey-patch via the
    bible 18 §5.6 conftest fixture). ``config`` is an optional
    :class:`InterpreterConfig`; defaults to bible-defaults.
    """

    def __init__(
        self,
        *,
        client: LLMClient,
        config: InterpreterConfig | None = None,
    ) -> None:
        self._client = client
        self._config = config if config is not None else InterpreterConfig()

    def run(
        self,
        raw_input: RawInput,
        *,
        run_id: str,
    ) -> IntentObject:
        """Convert ``raw_input`` to an ``IntentObject``.

        Parameters
        ----------
        raw_input
            The OPERATOR's RawInput (already past pipeline-driver
            schema validation; ``text`` is non-empty).
        run_id
            Canonical run_id (bible 04 §4 Rule 3 pattern). Required
            for ClarificationRequest construction and audit emission.

        Returns
        -------
        IntentObject
            Schema-validated, ``produced_by=INTERPRETER``-stamped
            artifact. In-memory only — pipeline driver persists per
            bible 02 §7.2.

        Raises
        ------
        NoExecutableIntent
            Pleasantry detected pre-LLM OR Claude emitted the
            sentinel goal post-LLM.
        PausedForClarification
            ``ambiguity_score`` exceeds the clarification threshold.
        RunError
            Claude emitted malformed JSON or a schema-violating
            artifact (``RunErrorType.SCHEMA_VIOLATION``).
        """
        started = time.monotonic()
        outcome: str = "success"
        ambiguity_score: float | None = None
        _audit_step_start(run_id=run_id, raw_input=raw_input)

        try:
            # 1. Pre-LLM pleasantry detection.
            if _is_pleasantry(raw_input.text):
                outcome = "halt:no_executable_intent"
                raise NoExecutableIntent(
                    reason="regex_pleasantry",
                    raw_text_preview=raw_input.text[:200],
                    run_id=run_id,
                )

            # 2. Build user message: bible context + recent runs + raw input.
            bible_ctx = _load_bible_context()
            run_ctx = _load_recent_runs()
            user_msg = _build_user_message(raw_input, bible_ctx, run_ctx)

            # 3. Read T4 fixed system prompt.
            system_text = _system_prompt_path().read_text(encoding="utf-8")

            # 4. Call T3 client at temperature 0. T3 emits llm_call audit.
            response = self._client.complete(
                system=system_text,
                user=user_msg,
                temperature=0.0,
                run_id=run_id,
                role=RoleEnum.INTERPRETER,
            )

            # 5. Parse Claude's JSON output.
            try:
                data = _parse_intent_json(response.text)
            except json.JSONDecodeError as exc:
                outcome = "error:schema_violation"
                raise RunError(
                    error_type=RunErrorType.SCHEMA_VIOLATION,
                    payload={
                        "module": "interpreter",
                        "stage": "json_parse",
                        "claude_output_preview": response.text[:500],
                        "decode_error": str(exc),
                        "run_id": run_id,
                    },
                ) from exc

            # 6. Schema-validate (Pydantic; extra="forbid" + closed enums).
            try:
                intent = _validate_intent(data)
            except PydanticValidationError as exc:
                outcome = "error:schema_violation"
                raise RunError(
                    error_type=RunErrorType.SCHEMA_VIOLATION,
                    payload={
                        "module": "interpreter",
                        "stage": "schema_validate",
                        "claude_output_preview": response.text[:500],
                        "validation_errors": exc.errors(),
                        "run_id": run_id,
                    },
                ) from exc

            ambiguity_score = intent.ambiguity_score

            # 7. Post-LLM sentinel detection.
            if intent.goal == _CLAUDE_SENTINEL_GOAL:
                outcome = "halt:no_executable_intent"
                raise NoExecutableIntent(
                    reason="claude_sentinel",
                    raw_text_preview=raw_input.text[:200],
                    run_id=run_id,
                )

            # 8. Ambiguity branching.
            if (
                intent.ambiguity_score
                > self._config.ambiguity_clarification_threshold
            ):
                outcome = "halt:paused_for_clarification"
                now_iso = datetime.now(timezone.utc).isoformat()
                request = _build_clarification_request(
                    intent, run_id=run_id, now_iso=now_iso
                )
                raise PausedForClarification(request=request)
            # [visible_threshold, clarification_threshold] continues with
            # implicit_assumptions surfaced; < visible_threshold continues
            # silently. Both fall through to return.

            return intent

        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            _audit_step_complete(
                run_id=run_id,
                outcome=outcome,
                ambiguity_score=ambiguity_score,
                duration_ms=duration_ms,
            )
