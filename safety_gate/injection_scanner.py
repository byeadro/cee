"""Injection scanner per bible 12 §5.5.

Implements the injection-scanning half of the SAFETY_GATE per bible 12
§5.5 (the canonical pseudocode for ``scan_for_injection``), §1 line 15
("Prompt injection — adversarial content in inputs..."), §3.3 (input
sanitization), §3.5 (logging every injection-pattern detection),
§4 line 57 ("All raw input ... is processed through the injection
scanner before reaching the interpreter"), §8.3 ("the injection-aware
role instruction is universal"), and §11 line 467 (module location).

**Module location.** This file lives at
``safety_gate/injection_scanner.py`` per bible 12 §11 line 467 + bible
04 §5.1 + bible 20 §5.3.

**Pattern catalog scope — 8 ship-ready pattern types.** Bible 12 §5.5
enumerates three detection categories. T7 ships every pattern with a
complete bible-grounded specification:

  Category 1 — Direct instruction-override (6 regex, IGNORECASE):
    1. ``ignore_previous_instructions``
    2. ``disregard_above``
    3. ``system_prefix``
    4. ``you_are_now``
    5. ``new_instructions``
    6. ``cee_tag_open_close``

  Category 2 — Hidden Unicode (1 pattern):
    7. ``hidden_unicode`` — zero-width chars + bidi/RTL overrides + BOM.

  Category 3 — CEE tag impersonation (1 pattern, 11 sub-tags):
    8. ``cee_tag_impersonation`` — emits one match per detected tag,
       with the tag name in :attr:`InjectionMatch.tag`. Sub-tags:
       ``final_prompt``, ``role``, ``task``, ``context``, ``agents``,
       ``skills``, ``execution_plan``, ``constraints``,
       ``grounding_rules``, ``output_format``, ``safety_banner``.

**Overlap fidelity.** Bible §5.5 lines 247 + 269 deliberately overlap:
``<role>`` matches both ``cee_tag_open_close`` (Category 1, regex) AND
``cee_tag_impersonation`` (Category 3, substring). T7 preserves both
checks; consumers can dedupe by ``(pattern, tag)`` if needed.

**Public API contract.**

* :func:`scan_text` is a **pure function**. No I/O, no audit emission,
  no halt — caller (pipeline) decides whether to halt the Run with
  ``injection_detected`` per bible §5.5 line 280.
* Operates on a single string. The full ``scan_for_injection(raw_input:
  RawInput)`` wrapper that iterates ``raw_input.text`` plus each
  attachment is deferred to the pipeline-integration phase (downstream
  candidate #43) — ``RawInput`` schema doesn't exist yet.
* Already-redacted input expected: redactor (T6) runs *before* this
  scanner per bible §3 ordering.

**Compilation cost.** Direct-override patterns compile once at module
import (matches T6's ``_BUILTIN_PATTERNS`` pattern). The hidden-unicode
set is a frozenset for O(1) membership tests. CEE tag impersonation
uses substring matching per bible §5.5 line 271 (``f"<{tag}"`` /
``f"</{tag}"``) — no regex compilation needed.

**Reserved for downstream candidates:**

* User-extendable patterns at ``~/cee/security/injection_patterns.py``
  per bible §11 line 467 — surfaced as candidate #44.
* ``scan(raw_input: RawInput)`` pipeline wrapper — candidate #43.
* ``InjectionScanResult`` Pydantic wrapper for halt-envelope
  serialization — candidate #45.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CompiledInjectionPattern:
    """A direct-override injection pattern ready for matching.

    ``name`` is the canonical pattern identifier (e.g.
    ``"ignore_previous_instructions"``); ``regex`` is a compiled regex
    with IGNORECASE per bible §5.5 line 250; ``category`` is the
    bible-§5.5 detection category this pattern belongs to.
    """

    name: str
    regex: re.Pattern[str]
    category: str


@dataclass(frozen=True)
class InjectionMatch:
    """A single injection-pattern hit produced by :func:`scan_text`.

    Mirrors bible §5.5's ``InjectionFlag`` data shape (lines 251, 263,
    272). ``pattern`` is the pattern *name* (never the regex source —
    log-safe). ``location`` is the caller-supplied provenance label
    (e.g. ``"text"``, ``"attachment:utility_bill.pdf"``). ``tag`` is
    populated only for ``cee_tag_impersonation`` matches per bible
    §5.5 line 275; all other categories leave it ``None``.
    """

    pattern: str
    location: str
    tag: str | None = None


# bible 12 §5.5 lines 241-248 — Category 1: Direct instruction-override.
# Regexes preserved verbatim from bible; IGNORECASE per line 250. Names
# assigned for log-safety and drift-detector reference.
_DIRECT_PATTERNS: tuple[CompiledInjectionPattern, ...] = (
    CompiledInjectionPattern(
        name="ignore_previous_instructions",
        regex=re.compile(r"ignore (all )?previous instructions", re.IGNORECASE),
        category="direct_override",
    ),
    CompiledInjectionPattern(
        name="disregard_above",
        regex=re.compile(r"disregard (the )?(above|previous|prior)", re.IGNORECASE),
        category="direct_override",
    ),
    CompiledInjectionPattern(
        name="system_prefix",
        regex=re.compile(r"system:?\s", re.IGNORECASE),
        category="direct_override",
    ),
    CompiledInjectionPattern(
        name="you_are_now",
        regex=re.compile(r"you are now", re.IGNORECASE),
        category="direct_override",
    ),
    CompiledInjectionPattern(
        name="new_instructions",
        regex=re.compile(r"new instructions:", re.IGNORECASE),
        category="direct_override",
    ),
    CompiledInjectionPattern(
        name="cee_tag_open_close",
        regex=re.compile(
            r"</?(role|task|context|instructions?|system)\s*>", re.IGNORECASE
        ),
        category="direct_override",
    ),
)


# bible 12 §5.5 line 269 — Category 3: CEE tag impersonation. The 11
# tag names that comprise CEE's FinalPrompt structure. An adversarial
# input that contains these tags is attempting to forge structural
# boundaries the executor relies on.
_CEE_TAG_NAMES: tuple[str, ...] = (
    "final_prompt",
    "role",
    "task",
    "context",
    "agents",
    "skills",
    "execution_plan",
    "constraints",
    "grounding_rules",
    "output_format",
    "safety_banner",
)


# bible 12 §5.5 line 262 — Category 2: hidden Unicode. The bible names
# "zero-width chars" and "RTL overrides" without enumerating; T7 ships
# the standard set covering both families plus BOM. Each char is one
# codepoint; membership test is O(1) via frozenset.
#
#   U+200B  ZERO WIDTH SPACE
#   U+200C  ZERO WIDTH NON-JOINER
#   U+200D  ZERO WIDTH JOINER
#   U+FEFF  ZERO WIDTH NO-BREAK SPACE / BOM
#   U+202A  LEFT-TO-RIGHT EMBEDDING
#   U+202B  RIGHT-TO-LEFT EMBEDDING
#   U+202C  POP DIRECTIONAL FORMATTING
#   U+202D  LEFT-TO-RIGHT OVERRIDE
#   U+202E  RIGHT-TO-LEFT OVERRIDE
#   U+2066  LEFT-TO-RIGHT ISOLATE
#   U+2067  RIGHT-TO-LEFT ISOLATE
#   U+2068  FIRST STRONG ISOLATE
#   U+2069  POP DIRECTIONAL ISOLATE
_HIDDEN_UNICODE_CHARS: frozenset[str] = frozenset(
    {
        "​",
        "‌",
        "‍",
        "﻿",
        "‪",
        "‫",
        "‬",
        "‭",
        "‮",
        "⁦",
        "⁧",
        "⁨",
        "⁩",
    }
)


def _has_hidden_unicode(text: str) -> bool:
    """True iff ``text`` contains any character from
    :data:`_HIDDEN_UNICODE_CHARS`.

    Mirrors bible §5.5 line 262's ``has_hidden_unicode(content)``
    helper. Returns a single boolean — caller emits at most one
    ``InjectionMatch`` per text per bible §5.5 lines 263-266.
    """
    return any(ch in _HIDDEN_UNICODE_CHARS for ch in text)


def scan_text(text: str, *, location: str = "text") -> list[InjectionMatch]:
    """Scan ``text`` for injection patterns; return zero or more matches.

    Pure function. No I/O, no audit emission, no halt — caller
    (pipeline) decides whether to halt the Run with
    ``injection_detected`` per bible 12 §5.5 line 280.

    Runs all three bible §5.5 detection categories on the input:

    1. Six direct instruction-override regexes (IGNORECASE).
    2. Hidden-unicode character set membership.
    3. Eleven CEE-tag-impersonation substring checks (one match per
       tag found, with the tag in :attr:`InjectionMatch.tag`).

    Categories 1 and 3 deliberately overlap on tags like ``<role>``
    per bible §5.5 lines 247 + 269 — both checks fire, both matches
    emitted.

    Parameters
    ----------
    text
        Input string. Typically already-redacted output from
        :func:`safety_gate.redact` (T6 contract).
    location
        Provenance label propagated to each :class:`InjectionMatch`.
        Bible §5.5 example values include ``"text"`` and
        ``"attachment:<name>"``.

    Returns
    -------
    list[InjectionMatch]
        One match per pattern hit. Empty list iff text is clean.
    """
    matches: list[InjectionMatch] = []

    # Category 1 — Direct instruction-override regexes.
    for pattern in _DIRECT_PATTERNS:
        if pattern.regex.search(text):
            matches.append(InjectionMatch(pattern=pattern.name, location=location))

    # Category 2 — Hidden Unicode.
    if _has_hidden_unicode(text):
        matches.append(
            InjectionMatch(pattern="hidden_unicode", location=location)
        )

    # Category 3 — CEE tag impersonation. Per bible §5.5 line 271, an
    # open-tag prefix (``<final_prompt``) OR close-tag prefix
    # (``</final_prompt``) anywhere in text counts as a hit. Emit one
    # match per detected tag, with the tag name attached.
    for tag in _CEE_TAG_NAMES:
        if f"<{tag}" in text or f"</{tag}" in text:
            matches.append(
                InjectionMatch(
                    pattern="cee_tag_impersonation",
                    location=location,
                    tag=tag,
                )
            )

    return matches
