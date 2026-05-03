"""Redaction patterns + transform per bible 12 §5.

Implements the redaction half of the SAFETY_GATE per bible 12 §5.1
(pipeline pseudocode), §5.2 (pattern catalog), §5.3 (user-config file
format), §7.2 (RedactionLog artifact), §10.2 (residual halt
contract).

**Module location.** This file lives at ``safety_gate/redactor.py``
per bible 04 §5.1 + bible 20 §5.3 + bible 18 + Phase 3 T6 plan. Bible
12 §5.2 + §6.1 still reference an older ``~/cee/security/redaction_
patterns.py`` location — that's documented bible drift, surfaced as
downstream candidate #37.

**Pattern catalog scope.** Bible 12 §5.2 enumerates 14 named
patterns. T6 ships **10 of them** — every pattern with a complete
bible-grounded regex specification:

  1. ``anthropic_api_key``        7. ``password_in_url``
  2. ``openai_api_key``           8. ``phone_us``
  3. ``aws_access_key``           9. ``ssn_us``
  4. ``aws_secret_key``          10. ``private_key_block``
  5. ``github_token``
  6. ``jwt``

Four patterns are deferred:

* ``street_address_us`` — bible 12 §5.2's markdown table cell is
  corrupted (broken regex `\\\\bd+s+\\\\[A-Z\\\\]\\\\[a-z\\\\]+s+(St`
  with split table cells `Ave`). Surfaced as downstream candidate #38.
* ``email``, ``credit_card``, ``ip_address`` — bible 12 §5.2 gives
  prose descriptions only ("standard RFC pattern", "Luhn-validated
  13-19 digit groups", "IPv4 / IPv6") with no regex. Surfaced
  collectively as downstream candidate #39.

**Public API contract.**

* :func:`redact` is a **pure transform**. No I/O, no audit emission.
  Caller decides what to do with the returned log entries (typically
  serialise into a :class:`schemas.RedactionLog` artifact and persist).
* :func:`load_user_patterns` reads the ``~/.cee/redact_list`` file
  per bible 12 §5.3 format. Absent file returns ``[]`` (per bible 04
  §EC10 "redact_list is empty or missing — pattern-based redaction
  still runs").
* :func:`assert_no_residual` is **caller-invoked**, not auto-invoked
  inside :func:`redact`. Bible 12 §5.7 makes the substrate writers
  responsible for re-scanning before each write (defense in depth);
  bible 12 §10.2 makes residual content a halt-worthy condition. The
  separation gives callers control over halt boundaries.

**Placeholder format.** Per bible 12 §5.1 line 84:
``f"<redacted:{pattern_name}>"`` for built-in patterns;
``"<redacted:user_term>"`` for user_term entries (line 101). T6
matches both literal templates exactly.

**Compilation cost.** Built-in patterns compile once at module import.
User patterns compile once per :func:`load_user_patterns` call.
:func:`redact` does no compilation in the hot path.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path

import paths
from errors import RedactionFailed
from schemas import RedactionLogEntry


@dataclass(frozen=True)
class CompiledPattern:
    """A redaction pattern ready for matching.

    ``name`` is the canonical pattern identifier (e.g.
    ``"anthropic_api_key"``); ``pattern`` is a compiled regex;
    ``placeholder`` is the substitution text (e.g.
    ``"<redacted:anthropic_api_key>"``).
    """

    name: str
    pattern: re.Pattern[str]
    placeholder: str


# bible 12 §5.2 catalog — 10 of 14 patterns (4 deferred per module
# docstring). Every entry is grounded in §5.2's table.
_BUILTIN_PATTERNS: tuple[CompiledPattern, ...] = (
    CompiledPattern(
        name="anthropic_api_key",
        pattern=re.compile(r"sk-ant-[A-Za-z0-9_-]{32,}"),
        placeholder="<redacted:anthropic_api_key>",
    ),
    CompiledPattern(
        name="openai_api_key",
        pattern=re.compile(r"sk-[A-Za-z0-9]{40,}"),
        placeholder="<redacted:openai_api_key>",
    ),
    CompiledPattern(
        name="aws_access_key",
        pattern=re.compile(r"AKIA[A-Z0-9]{16}"),
        placeholder="<redacted:aws_access_key>",
    ),
    CompiledPattern(
        name="aws_secret_key",
        pattern=re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9])"),
        placeholder="<redacted:aws_secret_key>",
    ),
    CompiledPattern(
        name="github_token",
        pattern=re.compile(r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}"),
        placeholder="<redacted:github_token>",
    ),
    CompiledPattern(
        name="jwt",
        pattern=re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
        placeholder="<redacted:jwt>",
    ),
    CompiledPattern(
        name="password_in_url",
        pattern=re.compile(r"://[^:\s]+:[^@\s]+@"),
        placeholder="<redacted:password_in_url>",
    ),
    CompiledPattern(
        name="phone_us",
        pattern=re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        placeholder="<redacted:phone_us>",
    ),
    CompiledPattern(
        name="ssn_us",
        pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        placeholder="<redacted:ssn_us>",
    ),
    CompiledPattern(
        name="private_key_block",
        pattern=re.compile(
            r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----"
        ),
        placeholder="<redacted:private_key_block>",
    ),
)


def _apply_pattern(
    text: str, pattern: CompiledPattern, location: str
) -> tuple[str, list[RedactionLogEntry]]:
    """Apply a single ``CompiledPattern`` to ``text``.

    Returns ``(new_text, entries)``: the substituted text plus a log
    entry per match. Per bible 12 §5.1 the log records the pattern
    name + location + placeholder — never the redacted content.
    """
    matches = pattern.pattern.findall(text)
    if not matches:
        return text, []
    new_text = pattern.pattern.sub(pattern.placeholder, text)
    entries = [
        RedactionLogEntry(
            pattern=pattern.name,
            location=location,
            replaced_with=pattern.placeholder,
        )
        for _ in matches
    ]
    return new_text, entries


def _apply_user_pattern(
    text: str, pattern: CompiledPattern, location: str, term: str
) -> tuple[str, list[RedactionLogEntry]]:
    """Apply a user-config ``CompiledPattern``, attaching ``term``.

    Per bible 12 §5.1's pseudocode (line 105), user_term entries
    carry the matched ``term`` string in their log entry. This
    populates the optional ``term`` field on
    :class:`RedactionLogEntry`.
    """
    matches = pattern.pattern.findall(text)
    if not matches:
        return text, []
    new_text = pattern.pattern.sub(pattern.placeholder, text)
    entries = [
        RedactionLogEntry(
            pattern=pattern.name,
            location=location,
            replaced_with=pattern.placeholder,
            term=term,
        )
        for _ in matches
    ]
    return new_text, entries


def redact(
    text: str,
    *,
    user_patterns: list[tuple[CompiledPattern, str]] | None = None,
    location: str = "prompt",
) -> tuple[str, list[RedactionLogEntry]]:
    """Apply all built-in patterns + ``user_patterns`` to ``text``.

    Pure transform. No I/O, no audit emission, no halt on residual
    (use :func:`assert_no_residual` for that).

    Parameters
    ----------
    text
        Input string. Typically a FinalPrompt body or rendered note.
    user_patterns
        Optional list of ``(pattern, term)`` tuples produced by
        :func:`load_user_patterns`. ``term`` is the original matched
        string from ``~/.cee/redact_list`` (used for log provenance).
    location
        Where in the artifact this text lives. Bible 12 §7.2's
        example uses ``"prompt"``; callers may pass ``"context"``,
        ``"attachment:<name>"``, etc.

    Returns
    -------
    (redacted_text, log_entries)
        ``redacted_text`` has every match replaced with its
        placeholder; ``log_entries`` carries one entry per match,
        per bible 12 §7.2.
    """
    log: list[RedactionLogEntry] = []
    for pattern in _BUILTIN_PATTERNS:
        text, entries = _apply_pattern(text, pattern, location)
        log.extend(entries)

    if user_patterns:
        for pattern, term in user_patterns:
            text, entries = _apply_user_pattern(text, pattern, location, term)
            log.extend(entries)

    return text, log


def load_user_patterns(
    path: Path = paths.REDACT_LIST,
) -> list[tuple[CompiledPattern, str]]:
    """Read ``~/.cee/redact_list`` per bible 12 §5.3 and return
    compiled patterns paired with the original matched term.

    Format per bible 12 §5.3:

    * Lines starting with ``#`` are comments.
    * Blank lines are ignored.
    * Lines starting with ``regex:`` are interpreted as Python regex.
    * Other lines are exact-match (``re.escape`` applied).

    Absent file returns ``[]`` (bible 04 §EC10).
    Malformed regex lines are skipped with a warning, per the
    pure-transform contract: redactor never halts on its own.
    """
    if not path.exists():
        return []

    out: list[tuple[CompiledPattern, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("regex:"):
            regex_src = line[len("regex:") :].strip()
            try:
                compiled = re.compile(regex_src)
            except re.error as exc:
                warnings.warn(
                    f"safety_gate.redactor: skipping malformed regex "
                    f"in {path}: {regex_src!r} ({exc})",
                    stacklevel=2,
                )
                continue
            term = regex_src
        else:
            compiled = re.compile(re.escape(line))
            term = line
        out.append(
            (
                CompiledPattern(
                    name="user_term",
                    pattern=compiled,
                    placeholder="<redacted:user_term>",
                ),
                term,
            )
        )
    return out


def assert_no_residual(text: str) -> None:
    """Re-scan ``text`` for built-in patterns; raise on any hit.

    Per bible 12 §10.2 a residual sensitive pattern after redaction
    is a halt-worthy failure. This function is **caller-invoked**
    (bible 12 §5.7 makes substrate writers responsible for the
    pre-write defense-in-depth scan); :func:`redact` does NOT call
    this itself.

    Raises
    ------
    RedactionFailed
        With ``payload={"residual_patterns": [<pattern_names>]}``
        per the Phase 1 :class:`errors.RedactionFailed` contract.
    """
    residual: list[str] = []
    for pattern in _BUILTIN_PATTERNS:
        if pattern.pattern.search(text):
            residual.append(pattern.name)
    if residual:
        raise RedactionFailed(residual_patterns=residual)
