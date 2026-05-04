"""Boot step B3: closed-enum consistency check across bible + code.

Authorized by System Design Bible section 00 §12 (Boot Sequence, step B3
"Consistency check") and section 20 §5.2 (Production build plan, boot
checks). When CEE starts a new Run, the boot sequencer must verify that
every closed enum the system relies on is identically declared in:

* the canonical bible page (the one source of truth for that enum), and
* every code module that mirrors that enum (Pydantic ``Literal`` aliases
  in ``schemas/``, Python ``Enum`` classes in ``errors/`` and ``roles/``).

If any mirror disagrees with its canonical page, or two mirrors disagree
with each other, the boot sequencer halts via
``BootConsistencyError(drifts=[...])`` and refuses to accept new Runs
until reconciliation lands. This guarantees that a Run can never use an
enum value the bible doesn't authorize, and that two code modules can
never silently disagree on the value space of a shared enum.

The 13 closed enums covered in Phase 2 (locked in T5 spec):

* RoleEnum            — bible 02 §4.1–§4.4
* TaskType            — bible 08 §5.1
* ComplexityTier      — bible 08 §5.3
* FormatType          — bible 10 §5.1
* SourceType          — bible 11 §5.1
* Posture/PostureHint — bible 06 §5.1
* Domain              — bible 15 §5.2 (line 111)
* Sensitivity         — bible 15 §5.2 (line 113)
* RunState            — bible 13 §5.2 (line 107)
* TargetExecutor      — bible 03 §5.2 Step 1 (line 65)
* HaltType            — bible 19 §5.1
* RunErrorType        — bible 19 §5.2
* WarningType         — bible 19 §5.3

Three drift kinds are reported:

* ``bible_canonical``  — the union of code values disagrees with the
  bible's canonical extraction.
* ``internal_schema``  — two or more code mirrors disagree with each
  other, even if their union happens to match the bible.
* ``cross_section``    — another bible page mentions a value (in
  backticks) that is not in the canonical set.

Three deferred enums (per AB resolution at T5 lock) are intentionally
absent from the registry: ``ExpectedAnswerType`` (no bible canonical),
``MatchZone`` (algorithm-shape only), ``RawInput.source`` (no labeled
enum). They will be added once their bible canonicals are reconciled.

**Two-registry pattern (introduced by Phase 4 T2).** This module owns
two parallel registries:

* :data:`REGISTRY` — name-set drift detectors. Each entry asserts that
  a closed enum's value-name set matches between bible and code.
* :data:`THRESHOLD_REGISTRY` — numerical-boundary drift detectors. Each
  entry asserts that a tier-style mapping (label → score range) matches
  between bible and code.

Name-set drift and numerical-mapping drift are conceptually different
invariant categories; folding them into one dataclass would force the
existing :class:`RegistryEntry` to carry a comparison-mode discriminator
that makes name-set entries less honest about what they check. Keeping
them parallel lets each registry stay narrowly typed. T2 ships the
threshold-registry pattern with a single entry (``complexity_tier_thresholds``
covering bible 08 §5.3); future phases (e.g., Phase 6's prompt-builder
length-budget contracts) can add more.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, get_args

from errors.types import HaltType, RunErrorType, WarningType
from roles import RoleEnum

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Bible root resolution                                                       #
# --------------------------------------------------------------------------- #

_DEFAULT_BIBLE_ROOT = Path.home() / "cee" / "bible"


def _resolve_bible_root(bible_root: Path | None) -> Path:
    return bible_root if bible_root is not None else _DEFAULT_BIBLE_ROOT


# --------------------------------------------------------------------------- #
# Drift report types                                                          #
# --------------------------------------------------------------------------- #

DriftKind = Literal["bible_canonical", "internal_schema", "cross_section"]


@dataclass(frozen=True)
class DriftRecord:
    """One detected drift between bible and code (or among code mirrors).

    ``code_values`` and ``bible_values`` are the value sets that
    disagreed; ``bible_section`` localizes the canonical authority;
    ``detail`` is a short human-readable cause line for the boot log.
    """

    enum_name: str
    drift_kind: DriftKind
    code_values: frozenset[str] | None
    bible_values: frozenset[str] | None
    bible_section: str | None
    detail: str


@dataclass(frozen=True)
class ConsistencyReport:
    """The result of one ``check()`` invocation.

    ``ok`` is True iff every registered entry passed every applicable
    check (across both :data:`REGISTRY` and :data:`THRESHOLD_REGISTRY`).
    ``enums_checked`` counts every name-set entry that was inspected.
    ``thresholds_checked`` (Phase 4 T2 addition) counts every
    numerical-boundary entry that was inspected. ``drifts`` is the full
    ordered tuple of detected drifts from both registries; the boot
    sequencer raises ``BootConsistencyError`` when this is non-empty.
    """

    ok: bool
    enums_checked: int
    drifts: tuple[DriftRecord, ...]
    thresholds_checked: int = 0


# --------------------------------------------------------------------------- #
# Code-side value loaders                                                     #
# --------------------------------------------------------------------------- #
#
# Each loader is a thin function returning a frozenset of the enum's value
# space as declared in one specific code module. The registry stores a
# tuple of loaders per entry; cross-mirror disagreement among them is
# ``internal_schema`` drift. Loaders import lazily so importing this
# module does not eagerly drag every schema into memory.


def _literal_values(literal_alias: object) -> frozenset[str]:
    """Extract the value set from a ``typing.Literal[...]`` alias."""
    return frozenset(get_args(literal_alias))


def _enum_values(enum_cls: type) -> frozenset[str]:
    """Extract the value set from a ``(str, Enum)`` class."""
    return frozenset(member.value for member in enum_cls)


# RoleEnum
def _code_role_enum() -> frozenset[str]:
    return _enum_values(RoleEnum)


# TaskType — 4 mirrors
def _code_tasktype_classification() -> frozenset[str]:
    from schemas.classification import TaskType
    return _literal_values(TaskType)


def _code_tasktype_run_summary() -> frozenset[str]:
    from schemas.run_summary import TaskTypeLiteral
    return _literal_values(TaskTypeLiteral)


def _code_tasktype_agent_frontmatter() -> frozenset[str]:
    from schemas.agent_frontmatter import TaskTypeSupported
    return _literal_values(TaskTypeSupported)


def _code_tasktype_skill_frontmatter() -> frozenset[str]:
    from schemas.skill_frontmatter import TaskTypeSupported
    return _literal_values(TaskTypeSupported)


# ComplexityTier — 3 mirrors
def _code_complexitytier_classification() -> frozenset[str]:
    from schemas.classification import ComplexityTier
    return _literal_values(ComplexityTier)


def _code_complexitytier_run_summary() -> frozenset[str]:
    from schemas.run_summary import ComplexityTierLiteral
    return _literal_values(ComplexityTierLiteral)


def _code_complexitytier_final_prompt() -> frozenset[str]:
    from schemas.final_prompt import ComplexityTier
    return _literal_values(ComplexityTier)


# FormatType — 1 mirror
def _code_formattype_format_declaration() -> frozenset[str]:
    from schemas.format_declaration import FormatType
    return _literal_values(FormatType)


# SourceType — 1 mirror
def _code_sourcetype_grounding_declaration() -> frozenset[str]:
    from schemas.grounding_declaration import SourceType
    return _literal_values(SourceType)


# Posture / PostureHint — 3 mirrors (compare-by-values; type names diverge
# intentionally: agents declare a single ``Posture``; Skills hint at
# multiple ``PostureHint``s).
def _code_posture_agent_frontmatter() -> frozenset[str]:
    from schemas.agent_frontmatter import Posture
    return _literal_values(Posture)


def _code_posture_agent_plan() -> frozenset[str]:
    from schemas.agent_plan import Posture
    return _literal_values(Posture)


def _code_posture_skill_frontmatter() -> frozenset[str]:
    from schemas.skill_frontmatter import PostureHint
    return _literal_values(PostureHint)


# Domain — 3 mirrors
def _code_domain_agent_frontmatter() -> frozenset[str]:
    from schemas.agent_frontmatter import Domain
    return _literal_values(Domain)


def _code_domain_skill_frontmatter() -> frozenset[str]:
    from schemas.skill_frontmatter import Domain
    return _literal_values(Domain)


def _code_domain_intent_object() -> frozenset[str]:
    from schemas.intent_object import IntentObject
    field_info = IntentObject.model_fields["domain"]
    return _literal_values(field_info.annotation)


# Sensitivity — 1 mirror
def _code_sensitivity_skill_frontmatter() -> frozenset[str]:
    from schemas.skill_frontmatter import Sensitivity
    return _literal_values(Sensitivity)


# RunState — 1 mirror
def _code_runstate_run_summary() -> frozenset[str]:
    from schemas.run_summary import RunState
    return _literal_values(RunState)


# TargetExecutor — 4 mirrors. Set comparison ignores order.
def _code_target_raw_input() -> frozenset[str]:
    from schemas.raw_input import RawInput
    field_info = RawInput.model_fields["target_executor"]
    return _literal_values(field_info.annotation)


def _code_target_run_summary() -> frozenset[str]:
    from schemas.run_summary import TargetExecutorLiteral
    return _literal_values(TargetExecutorLiteral)


def _code_target_final_prompt() -> frozenset[str]:
    from schemas.final_prompt import TargetExecutor
    return _literal_values(TargetExecutor)


def _code_target_config() -> frozenset[str]:
    from schemas.config import ExecutorConfig
    field_info = ExecutorConfig.model_fields["default_target"]
    return _literal_values(field_info.annotation)


# HaltType / RunErrorType / WarningType — bible-grounded Enum classes
def _code_halt_type() -> frozenset[str]:
    return _enum_values(HaltType)


def _code_run_error_type() -> frozenset[str]:
    return _enum_values(RunErrorType)


def _code_warning_type() -> frozenset[str]:
    return _enum_values(WarningType)


# --------------------------------------------------------------------------- #
# Bible scoping helpers                                                       #
# --------------------------------------------------------------------------- #


def _scope_section(content: str, section_anchor: str) -> str:
    """Return the text under all headings starting with ``section_anchor``.

    The anchor is matched as a literal prefix at the start of a heading
    line (e.g. ``"### 5.1 "`` matches ``"### 5.1 The closed task_type"``
    but not ``"### 5.10 ..."``). Each matched heading's scope runs from
    just after that heading until the next ``##`` or ``###`` heading at
    any level. Multiple matches are concatenated (used for RoleEnum's
    §4.1–§4.4 family).
    """
    lines = content.splitlines()
    scopes: list[str] = []
    in_scope = False
    buffer: list[str] = []

    for line in lines:
        stripped = line.lstrip()
        is_heading = stripped.startswith("## ") or stripped.startswith("### ")
        if is_heading:
            if in_scope:
                scopes.append("\n".join(buffer))
                buffer = []
                in_scope = False
            if stripped.startswith(section_anchor):
                in_scope = True
            continue
        if in_scope:
            buffer.append(line)

    if in_scope:
        scopes.append("\n".join(buffer))
    return "\n".join(scopes)


def _scope_line(content: str, line_number: int) -> str:
    """Return just the requested 1-indexed line, or empty string if out
    of range. Used when an extractor needs a single specific line (e.g.
    ``state: delivered | paused | failed | aborted`` at bible 13:107).
    """
    lines = content.splitlines()
    if 1 <= line_number <= len(lines):
        return lines[line_number - 1]
    return ""


# --------------------------------------------------------------------------- #
# Extractors                                                                  #
# --------------------------------------------------------------------------- #
#
# Each extractor takes the full bible markdown content, the section
# anchor, and an optional line anchor. It returns the frozenset of enum
# values found in the in-scope text.

_BACKTICK_BULLET = re.compile(r"^\s*-\s+`([^`]+)`")
_HTML_TD_BACKTICK = re.compile(r"<td>\s*`([^`]+)`\s*</td>")
_PIPE_LIST_RHS = re.compile(r"[:=]\s*([A-Za-z0-9_\- ]+(?:\s*\|\s*[A-Za-z0-9_\- ]+)+)")
_INLINE_CODE_TOKEN = re.compile(r"`([^`]+)`")
_PYTHON_ENUM_MEMBER = re.compile(r'^\s*[A-Z][A-Z0-9_]*\s*=\s*"([^"]+)"')
_HTML_TD_PLAIN = re.compile(r"<td>\s*([A-Za-z][A-Za-z0-9_]*)\s*</td>")


def _extract_regex_bullet_list(
    content: str,
    section_anchor: str,
    line_anchor: int | None = None,
) -> frozenset[str]:
    """Extract values from bullet lines like ``- \\`OPERATOR\\``.

    Used for RoleEnum (bible 02 §4.1–§4.4) where each role value sits
    inside backticks at the start of a list item.
    """
    if line_anchor is not None:
        scope = _scope_line(content, line_anchor)
    else:
        scope = _scope_section(content, section_anchor)
    values: set[str] = set()
    for line in scope.splitlines():
        m = _BACKTICK_BULLET.match(line)
        if m:
            value = m.group(1).split()[0]  # strip "(future)" annotations
            values.add(value)
    return frozenset(values)


def _extract_regex_html_table_backticks(
    content: str,
    section_anchor: str,
    line_anchor: int | None = None,
) -> frozenset[str]:
    """Extract backtick-quoted values from <td> cells.

    Used for TaskType (bible 08 §5.1), FormatType (bible 10 §5.1),
    SourceType (bible 11 §5.1), Posture (bible 06 §5.1). These tables
    declare values inside backticks within the first column of <td>
    cells; descriptions (without backticks) in subsequent cells are
    ignored.
    """
    if line_anchor is not None:
        scope = _scope_line(content, line_anchor)
    else:
        scope = _scope_section(content, section_anchor)

    # First column only: take the first <td>`...`</td> on each row of
    # data. Header rows (<td>Value</td> without backticks) are ignored
    # by the backtick requirement.
    values: set[str] = set()
    for line in scope.splitlines():
        m = _HTML_TD_BACKTICK.search(line)
        if m:
            values.add(m.group(1))
    return frozenset(values)


def _extract_regex_pipe_list(
    content: str,
    section_anchor: str,
    line_anchor: int | None = None,
) -> frozenset[str]:
    """Extract pipe-delimited values like ``low | medium | high``.

    Used for Sensitivity (bible 15 §5.2 line 113), RunState (bible 13
    §5.2 line 107), and (as a fallback inline declaration) Posture
    Rule 1 (bible 06 §4 ``primary | critic | optimizer | orchestrator |
    specialist``). A line anchor pins a specific line; otherwise the
    extractor scans the section for the first qualifying pipe list.
    """
    if line_anchor is not None:
        scope = _scope_line(content, line_anchor)
    else:
        scope = _scope_section(content, section_anchor)

    for raw_line in scope.splitlines():
        # Strip YAML-style trailing comments before parsing.
        line = raw_line.split("#", 1)[0]
        m = _PIPE_LIST_RHS.search(line)
        if not m:
            continue
        rhs = m.group(1)
        tokens = [tok.strip() for tok in rhs.split("|")]
        # Discard the trailing column when the line continues past the
        # pipe list (e.g. ``state: a | b | c\nother: ...``). Keep only
        # tokens that are simple identifiers.
        cleaned = {t for t in tokens if t and re.fullmatch(r"[A-Za-z][A-Za-z0-9_\-]*", t)}
        if len(cleaned) >= 2:
            return frozenset(cleaned)
    return frozenset()


def _extract_regex_inline_code(
    content: str,
    section_anchor: str,
    line_anchor: int | None = None,
) -> frozenset[str]:
    """Extract values from inline code spans, table cells, or set literals.

    Used for ComplexityTier (bible 08 §5.3 — plain ``<td>LOW</td>``
    cells with no backticks), Domain (bible 15 §5.2 — YAML comment
    ``# one of: code, writing, ...``), and TargetExecutor (bible 03
    §5.2 Step 1 line 65 — ``target_executor ∈ {claude_ai, claude_code,
    api}``). The extractor tolerates all three shapes by trying them in
    order.
    """
    if line_anchor is not None:
        scope = _scope_line(content, line_anchor)
    else:
        scope = _scope_section(content, section_anchor)

    # Shape 3: brace-set literal on a single line (TargetExecutor).
    brace_match = re.search(r"\{([^{}]+)\}", scope)
    if brace_match and line_anchor is not None:
        tokens = [tok.strip() for tok in brace_match.group(1).split(",")]
        cleaned = {t for t in tokens if re.fullmatch(r"[a-z][a-z0-9_]*", t)}
        if len(cleaned) >= 2:
            return frozenset(cleaned)

    # Shape 2: comment-delimited list (Domain). Look for "one of: a, b, c".
    comment_match = re.search(r"#\s*one of:\s*([A-Za-z0-9_,\s]+?)$", scope, re.MULTILINE)
    if comment_match:
        tokens = [tok.strip() for tok in comment_match.group(1).split(",")]
        cleaned = {t for t in tokens if re.fullmatch(r"[a-z][a-z0-9_]*", t)}
        if len(cleaned) >= 2:
            return frozenset(cleaned)

    # Shape 1: HTML table cells without backticks (ComplexityTier).
    values: set[str] = set()
    seen_header = False
    for line in scope.splitlines():
        m = _HTML_TD_PLAIN.search(line)
        if not m:
            continue
        token = m.group(1)
        # The first <td> we hit is typically a header label like "Tier";
        # subsequent rows are the enum values. Skip the first hit.
        if not seen_header:
            seen_header = True
            continue
        # Heuristic: enum values for ComplexityTier are SCREAMING_CASE.
        if re.fullmatch(r"[A-Z][A-Z0-9_]+", token):
            values.add(token)
    if values:
        return frozenset(values)

    return frozenset()


def _extract_regex_python_class(
    content: str,
    section_anchor: str,
    line_anchor: int | None = None,
) -> frozenset[str]:
    """Extract enum members from a ``class X(str, Enum):`` code fence.

    Used for HaltType (bible 19 §5.1), RunErrorType (bible 19 §5.2),
    WarningType (bible 19 §5.3). The extractor scopes to the requested
    section, walks its python code fence, and returns each
    ``MEMBER = "value"`` declaration's value.
    """
    if line_anchor is not None:
        scope = _scope_line(content, line_anchor)
    else:
        scope = _scope_section(content, section_anchor)

    values: set[str] = set()
    in_code_fence = False
    for line in scope.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if not in_code_fence:
            continue
        m = _PYTHON_ENUM_MEMBER.match(line)
        if m:
            values.add(m.group(1))
    return frozenset(values)


# --------------------------------------------------------------------------- #
# Registry                                                                    #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RegistryEntry:
    """One closed enum tracked by the consistency check.

    * ``enum_name``         — human-readable label used in DriftRecords.
    * ``code_source_loaders`` — one callable per code mirror; each
      returns the value set declared in that file. Cross-mirror drift
      is reported as ``internal_schema``.
    * ``canonical_bible``   — bible filename (``"08_..."``).
    * ``canonical_section`` — heading anchor (``"### 5.1"``).
    * ``canonical_line``    — optional 1-indexed line for line-anchored
      enums (Domain, Sensitivity, RunState, TargetExecutor).
    * ``extractor``         — one of the ``_extract_regex_*`` callables.
    * ``cross_ref_bibles``  — other bible filenames that mention this
      enum's values; scanned conservatively for backtick mentions of
      values not in the canonical set.
    * ``comparison``        — ``"set"`` (exact set equality) or
      ``"set_ignore_name"`` (Posture-style: agents and Skills use
      different type names but identical value sets).
    """

    enum_name: str
    code_source_loaders: tuple[Callable[[], frozenset[str]], ...]
    canonical_bible: str
    canonical_section: str
    canonical_line: int | None
    extractor: Callable[..., frozenset[str]]
    cross_ref_bibles: tuple[str, ...] = field(default_factory=tuple)
    comparison: Literal["set", "set_ignore_name"] = "set"


REGISTRY: dict[str, RegistryEntry] = {
    "RoleEnum": RegistryEntry(
        enum_name="RoleEnum",
        code_source_loaders=(_code_role_enum,),
        canonical_bible="02_user_roles.md",
        canonical_section="### 4.",
        canonical_line=None,
        extractor=_extract_regex_bullet_list,
    ),
    "TaskType": RegistryEntry(
        enum_name="TaskType",
        code_source_loaders=(
            _code_tasktype_classification,
            _code_tasktype_run_summary,
            _code_tasktype_agent_frontmatter,
            _code_tasktype_skill_frontmatter,
        ),
        canonical_bible="08_task_classification_engine.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_html_table_backticks,
    ),
    "ComplexityTier": RegistryEntry(
        enum_name="ComplexityTier",
        code_source_loaders=(
            _code_complexitytier_classification,
            _code_complexitytier_run_summary,
            _code_complexitytier_final_prompt,
        ),
        canonical_bible="08_task_classification_engine.md",
        canonical_section="### 5.3 ",
        canonical_line=None,
        extractor=_extract_regex_inline_code,
    ),
    "FormatType": RegistryEntry(
        enum_name="FormatType",
        code_source_loaders=(_code_formattype_format_declaration,),
        canonical_bible="10_output_format_engine.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_html_table_backticks,
    ),
    "SourceType": RegistryEntry(
        enum_name="SourceType",
        code_source_loaders=(_code_sourcetype_grounding_declaration,),
        canonical_bible="11_hallucination_source_grounding.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_html_table_backticks,
    ),
    "Posture": RegistryEntry(
        enum_name="Posture",
        code_source_loaders=(
            _code_posture_agent_frontmatter,
            _code_posture_agent_plan,
            _code_posture_skill_frontmatter,
        ),
        canonical_bible="06_agent_system_design.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_html_table_backticks,
        comparison="set_ignore_name",
    ),
    "Domain": RegistryEntry(
        enum_name="Domain",
        code_source_loaders=(
            _code_domain_agent_frontmatter,
            _code_domain_skill_frontmatter,
            _code_domain_intent_object,
        ),
        canonical_bible="15_skill_file_structure.md",
        canonical_section="### 5.2 ",
        canonical_line=111,
        extractor=_extract_regex_inline_code,
    ),
    "Sensitivity": RegistryEntry(
        enum_name="Sensitivity",
        code_source_loaders=(_code_sensitivity_skill_frontmatter,),
        canonical_bible="15_skill_file_structure.md",
        canonical_section="### 5.2 ",
        canonical_line=113,
        extractor=_extract_regex_pipe_list,
    ),
    "RunState": RegistryEntry(
        enum_name="RunState",
        code_source_loaders=(_code_runstate_run_summary,),
        canonical_bible="13_obsidian_integration.md",
        canonical_section="### 5.2 ",
        canonical_line=107,
        extractor=_extract_regex_pipe_list,
    ),
    "TargetExecutor": RegistryEntry(
        enum_name="TargetExecutor",
        code_source_loaders=(
            _code_target_raw_input,
            _code_target_run_summary,
            _code_target_final_prompt,
            _code_target_config,
        ),
        canonical_bible="03_full_system_workflow.md",
        canonical_section="### 5.2 ",
        canonical_line=65,
        extractor=_extract_regex_inline_code,
    ),
    "HaltType": RegistryEntry(
        enum_name="HaltType",
        code_source_loaders=(_code_halt_type,),
        canonical_bible="19_error_handling_failure_states.md",
        canonical_section="### 5.1 ",
        canonical_line=None,
        extractor=_extract_regex_python_class,
    ),
    "RunErrorType": RegistryEntry(
        enum_name="RunErrorType",
        code_source_loaders=(_code_run_error_type,),
        canonical_bible="19_error_handling_failure_states.md",
        canonical_section="### 5.2 ",
        canonical_line=None,
        extractor=_extract_regex_python_class,
    ),
    "WarningType": RegistryEntry(
        enum_name="WarningType",
        code_source_loaders=(_code_warning_type,),
        canonical_bible="19_error_handling_failure_states.md",
        canonical_section="### 5.3 ",
        canonical_line=None,
        extractor=_extract_regex_python_class,
    ),
}


# --------------------------------------------------------------------------- #
# Threshold registry — numerical-boundary detectors (Phase 4 T2)              #
# --------------------------------------------------------------------------- #
#
# Parallel to REGISTRY. Each entry asserts that a tier-style mapping
# ``label -> (min_score, max_score)`` matches between the bible's canonical
# table and the code's encoding. Drift surfaces in the same
# ``ConsistencyReport`` as ``DriftRecord`` with ``drift_kind="bible_canonical"``;
# the ``code_values`` and ``bible_values`` carry repr strings of the
# offending mappings so the existing report consumers (boot sequencer,
# CLI verifier) need no shape changes.
#
# The single T2 entry covers bible 08 §5.3 (complexity tier score ranges).
# Future phases can register more numerical contracts the same way.


_TierThresholdMap = dict[str, tuple[int, int]]


@dataclass(frozen=True)
class ThresholdRegistryEntry:
    """One numerical-boundary mapping tracked by the consistency check.

    * ``name``                — human-readable label used in DriftRecords.
    * ``code_source_loader``  — callable returning the
      ``label -> (min, max)`` mapping declared in code.
    * ``canonical_bible``     — bible filename hosting the canonical table.
    * ``canonical_section``   — heading anchor (``"### 5.3 "``).
    * ``extractor``           — callable taking ``(bible_text, section)``
      and returning the canonical mapping. Single-purpose per entry —
      the threshold table shapes vary too much to share extractors.
    """

    name: str
    code_source_loader: Callable[[], _TierThresholdMap]
    canonical_bible: str
    canonical_section: str
    extractor: Callable[[str, str], _TierThresholdMap]


# Bible 08 §5.3 uses HTML tables with en-dash (U+2013) score ranges
# (e.g. ``<td>0–24</td>``). The extractor accepts both en-dash and ASCII
# hyphen for safety.
_TIER_TABLE_ROW = re.compile(
    r"<tr>\s*<td>\s*(?P<label>[A-Z]+)\s*</td>\s*"
    r"<td>\s*(?P<lo>\d+)\s*[–\-]\s*(?P<hi>\d+)\s*</td>",
)


def _extract_tier_thresholds_from_bible_8_3(
    bible_text: str, section_anchor: str
) -> _TierThresholdMap:
    """Parse bible 08 §5.3's tier table into ``label -> (min, max)``.

    Anchors on the section heading then walks subsequent ``<tr>`` rows
    until the next section heading or the table closer. Handles en-dash
    (U+2013) and ASCII hyphen for the score-range separator.
    """
    section = _scope_section(bible_text, section_anchor)
    if not section:
        return {}
    result: _TierThresholdMap = {}
    for match in _TIER_TABLE_ROW.finditer(section):
        label = match.group("label")
        lo = int(match.group("lo"))
        hi = int(match.group("hi"))
        result[label] = (lo, hi)
    return result


def _code_tier_thresholds_classification() -> _TierThresholdMap:
    """Probe ``schemas.classification._tier_from_score`` for its boundaries.

    Calls the function at every integer in ``[0, 100]`` and buckets each
    score by the tier label returned. The min/max of each bucket gives
    the encoded boundary contract. This shape is robust to refactor of
    the function body — only the public input/output behaviour matters.
    """
    from schemas.classification import _tier_from_score

    buckets: dict[str, list[int]] = {}
    for score in range(0, 101):
        tier = _tier_from_score(score)
        buckets.setdefault(tier, []).append(score)
    return {label: (min(scores), max(scores)) for label, scores in buckets.items()}


THRESHOLD_REGISTRY: dict[str, ThresholdRegistryEntry] = {
    "complexity_tier_thresholds": ThresholdRegistryEntry(
        name="complexity_tier_thresholds",
        code_source_loader=_code_tier_thresholds_classification,
        canonical_bible="08_task_classification_engine.md",
        canonical_section="### 5.3 ",
        extractor=_extract_tier_thresholds_from_bible_8_3,
    ),
}


def _check_one_threshold(
    entry: ThresholdRegistryEntry, bible_root: Path
) -> list[DriftRecord]:
    """Compare one threshold mapping between bible and code."""
    drifts: list[DriftRecord] = []
    section_label = entry.canonical_section.strip()

    code_map = entry.code_source_loader()

    bible_path = bible_root / entry.canonical_bible
    if not bible_path.exists():
        drifts.append(
            DriftRecord(
                enum_name=entry.name,
                drift_kind="bible_canonical",
                code_values=frozenset(_format_threshold_map(code_map)),
                bible_values=None,
                bible_section=f"{entry.canonical_bible} {section_label}",
                detail=f"canonical bible page not found: {bible_path}",
            )
        )
        return drifts

    bible_text = bible_path.read_text(encoding="utf-8")
    bible_map = entry.extractor(bible_text, entry.canonical_section)

    if not bible_map:
        drifts.append(
            DriftRecord(
                enum_name=entry.name,
                drift_kind="bible_canonical",
                code_values=frozenset(_format_threshold_map(code_map)),
                bible_values=frozenset(),
                bible_section=f"{entry.canonical_bible} {section_label}",
                detail=(
                    f"extractor returned empty mapping from "
                    f"{entry.canonical_bible} {section_label} — anchor or "
                    f"bible content has drifted"
                ),
            )
        )
    elif code_map != bible_map:
        drifts.append(
            DriftRecord(
                enum_name=entry.name,
                drift_kind="bible_canonical",
                code_values=frozenset(_format_threshold_map(code_map)),
                bible_values=frozenset(_format_threshold_map(bible_map)),
                bible_section=f"{entry.canonical_bible} {section_label}",
                detail=(
                    f"threshold mapping drift: "
                    f"code={_format_threshold_map(code_map)!r}, "
                    f"bible={_format_threshold_map(bible_map)!r}"
                ),
            )
        )

    return drifts


def _format_threshold_map(mapping: _TierThresholdMap) -> list[str]:
    """Render a threshold mapping as a sorted ``"LABEL=lo..hi"`` list.

    Used to fit threshold drift into the existing :class:`DriftRecord`
    ``frozenset[str]`` value-set fields without needing a separate
    record type.
    """
    return sorted(f"{label}={lo}..{hi}" for label, (lo, hi) in mapping.items())


# --------------------------------------------------------------------------- #
# Drift detection                                                             #
# --------------------------------------------------------------------------- #


def _check_one(
    entry: RegistryEntry,
    bible_root: Path,
) -> list[DriftRecord]:
    """Run all three drift checks for a single registry entry."""
    drifts: list[DriftRecord] = []
    section_label = entry.canonical_section.strip()
    if entry.canonical_line is not None:
        section_label = f"{section_label} (line {entry.canonical_line})"

    # 1. Internal-schema drift across code mirrors.
    code_value_sets = [loader() for loader in entry.code_source_loaders]
    if len(code_value_sets) > 1:
        first = code_value_sets[0]
        for idx, other in enumerate(code_value_sets[1:], start=1):
            if other != first:
                drifts.append(
                    DriftRecord(
                        enum_name=entry.enum_name,
                        drift_kind="internal_schema",
                        code_values=first,
                        bible_values=other,
                        bible_section=None,
                        detail=(
                            f"code mirror #{idx} disagrees with mirror #0: "
                            f"only-in-#0={sorted(first - other)!r}, "
                            f"only-in-#{idx}={sorted(other - first)!r}"
                        ),
                    )
                )

    # The merged code value set is what we compare against the bible.
    merged_code = frozenset().union(*code_value_sets) if code_value_sets else frozenset()

    # 2. Bible-canonical drift.
    bible_path = bible_root / entry.canonical_bible
    if not bible_path.exists():
        drifts.append(
            DriftRecord(
                enum_name=entry.enum_name,
                drift_kind="bible_canonical",
                code_values=merged_code,
                bible_values=None,
                bible_section=f"{entry.canonical_bible}{section_label}",
                detail=f"canonical bible page not found: {bible_path}",
            )
        )
        return drifts

    bible_text = bible_path.read_text(encoding="utf-8")
    bible_values = entry.extractor(
        bible_text,
        entry.canonical_section,
        entry.canonical_line,
    )

    if not bible_values:
        drifts.append(
            DriftRecord(
                enum_name=entry.enum_name,
                drift_kind="bible_canonical",
                code_values=merged_code,
                bible_values=bible_values,
                bible_section=f"{entry.canonical_bible} {section_label}",
                detail=(
                    f"extractor returned empty value set from "
                    f"{entry.canonical_bible} {section_label} — anchor or "
                    f"bible content has drifted"
                ),
            )
        )
    elif merged_code != bible_values:
        drifts.append(
            DriftRecord(
                enum_name=entry.enum_name,
                drift_kind="bible_canonical",
                code_values=merged_code,
                bible_values=bible_values,
                bible_section=f"{entry.canonical_bible} {section_label}",
                detail=(
                    f"only-in-code={sorted(merged_code - bible_values)!r}, "
                    f"only-in-bible={sorted(bible_values - merged_code)!r}"
                ),
            )
        )

    # 3. Cross-section drift in other bible pages. We scan each cross-ref
    # bible for backtick-quoted tokens that look like enum values; any
    # token that is not in the canonical set is reported. This is
    # conservative — we only flag tokens that match the canonical set's
    # style (lower/upper-case shape) to avoid noise from natural prose.
    if bible_values:
        canonical_lc = bible_values
        canonical_style_lower = all(v.islower() or "_" in v for v in bible_values)
        for cross_bible in entry.cross_ref_bibles:
            cross_path = bible_root / cross_bible
            if not cross_path.exists():
                continue
            cross_text = cross_path.read_text(encoding="utf-8")
            cited_tokens: set[str] = set()
            for m in _INLINE_CODE_TOKEN.finditer(cross_text):
                token = m.group(1)
                if canonical_style_lower:
                    if not re.fullmatch(r"[a-z][a-z0-9_]+", token):
                        continue
                else:
                    if not re.fullmatch(r"[A-Z][A-Z0-9_]+", token):
                        continue
                cited_tokens.add(token)
            unknown = cited_tokens - canonical_lc
            # Discard tokens that look like enum-shape but are very short
            # — they're often common backtick-quoted words ("code") that
            # collide with enum values; if they're already in canonical
            # the set difference removed them.
            if unknown:
                drifts.append(
                    DriftRecord(
                        enum_name=entry.enum_name,
                        drift_kind="cross_section",
                        code_values=merged_code,
                        bible_values=bible_values,
                        bible_section=cross_bible,
                        detail=(
                            f"{cross_bible} mentions tokens not in canonical "
                            f"set: {sorted(unknown)!r}"
                        ),
                    )
                )

    return drifts


def check(
    *,
    bible_root: Path | None = None,
    entry_names: tuple[str, ...] | None = None,
) -> ConsistencyReport:
    """Run all registered consistency checks and return a structured report.

    Per bible 00 §12 step B3 the boot sequencer calls this exactly once
    per session before opening the Run pipeline. ``ok=False`` means the
    sequencer must raise ``BootConsistencyError(drifts=report.drifts)``
    and refuse to accept new Runs until reconciliation lands.

    Optional ``bible_root`` redirects the canonical bible mirror (used
    by tests to point at fixtures). Optional ``entry_names`` restricts
    the name-set check to the named registry entries (used by tests to
    scope a parametrized assertion to one enum at a time); when ``None``
    every name-set entry is checked. Threshold-registry entries are
    always checked (the registry is small enough that gating isn't
    needed).
    """
    root = _resolve_bible_root(bible_root)
    selected = (
        REGISTRY
        if entry_names is None
        else {k: v for k, v in REGISTRY.items() if k in entry_names}
    )

    all_drifts: list[DriftRecord] = []
    for name, entry in selected.items():
        logger.info("boot.consistency: checking %s", name)
        entry_drifts = _check_one(entry, root)
        for d in entry_drifts:
            logger.warning(
                "boot.consistency: drift %s (%s) — %s",
                d.enum_name,
                d.drift_kind,
                d.detail,
            )
        all_drifts.extend(entry_drifts)

    for name, threshold_entry in THRESHOLD_REGISTRY.items():
        logger.info("boot.consistency: checking threshold %s", name)
        threshold_drifts = _check_one_threshold(threshold_entry, root)
        for d in threshold_drifts:
            logger.warning(
                "boot.consistency: drift %s (%s) — %s",
                d.enum_name,
                d.drift_kind,
                d.detail,
            )
        all_drifts.extend(threshold_drifts)

    return ConsistencyReport(
        ok=not all_drifts,
        enums_checked=len(selected),
        drifts=tuple(all_drifts),
        thresholds_checked=len(THRESHOLD_REGISTRY),
    )
