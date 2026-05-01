"""Frontmatter parser for ``SKILL.md`` (and, by symmetry, agent files).

Authorized by System Design Bible section 15 §11 ("Build Notes for Claude
Code"), which names this module:

    **Frontmatter parser:** ``~/cee/skill_engine/parsers.py``. Uses
    ``python-frontmatter`` library or equivalent.

The "or equivalent" clause is load-bearing here. ``python-frontmatter``
silently coerces three distinct failure modes into a single
``metadata == {}`` result — files without ``---`` markers, files whose
top-level YAML is a list/scalar instead of a mapping, and files with a
genuinely empty mapping. Bible 00 §12 B4 is unambiguous on the first
two: "Skills with invalid frontmatter are logged and skipped, not
loaded." A library that can't distinguish "no frontmatter" from "empty
frontmatter" can't enforce that contract. So this module parses with
``yaml.safe_load`` against an explicit marker regex, which:

    1. detects missing ``---`` markers as a failure (vs. empty content),
    2. preserves the raw YAML type so list/scalar frontmatter can be
       rejected (vs. silently accepted as ``{}``),
    3. still treats genuinely empty frontmatter (``---\\n---``) as a
       successful empty-mapping load.

This module does not validate frontmatter against any schema. Callers
(``skill_engine.registry.rebuild`` for SKILL.md, the future agent
registry for agent files) own schema validation via
``schemas.SkillFrontmatter`` / ``schemas.AgentFrontmatter``. Keeping
parse and validate separate lets each registry choose its own schema
without the parser knowing which file kind it's reading.

Bible cross-references:

- ``00_project_vision.md`` §12 B4 — "logged and skipped, not loaded".
- ``04_database_file_structure.md`` §6.5 — registry record shape that
  consumes this parser's output.
- ``15_skill_file_structure.md`` §5.2 — frontmatter contract this
  parser surfaces (a YAML mapping between ``---`` markers).
- ``15_skill_file_structure.md`` §11 — names this file as the parser.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Bible 15 §5.2: frontmatter is a YAML block bounded by ``---`` markers
# at the top of the file. The regex is anchored at start-of-string with
# ``\A``, allows leading whitespace, requires a newline after the
# opening ``---``, captures the YAML body non-greedily, and accepts the
# closing ``---`` with or without a preceding/following newline (handles
# the ``---\n---`` empty-frontmatter case as well as files that end
# immediately after the closing marker).
_FRONTMATTER_BLOCK = re.compile(
    r"\A\s*---\r?\n(.*?)\r?\n?---(?:\r?\n|\Z)",
    re.DOTALL,
)


def parse_frontmatter(path: Path) -> dict | None:
    """Parse YAML frontmatter from ``path``.

    Returns the parsed mapping on success. Returns ``None`` and logs a
    WARNING on every failure mode bible 00 §12 B4 describes as "invalid
    frontmatter":

    - file does not exist or cannot be read
    - file does not start with the ``---`` opening marker
    - YAML body between markers is malformed
    - top-level YAML is not a mapping (a list, scalar, etc.)

    Empty frontmatter (``---\\n---``, or whitespace/comments-only between
    markers) is a valid YAML mapping and returns ``{}`` — the caller
    decides whether the empty mapping satisfies the field requirements
    of its schema.

    The caller owns schema validation; this function only enforces the
    file-shape contract from bible 15 §5.2.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("frontmatter parse: file not found: %s", path)
        return None
    except OSError as exc:
        logger.warning("frontmatter parse: read failed for %s: %s", path, exc)
        return None

    match = _FRONTMATTER_BLOCK.match(text)
    if match is None:
        logger.warning("frontmatter parse: no frontmatter markers in %s", path)
        return None

    yaml_body = match.group(1)
    if not yaml_body.strip():
        # Bible 15 §5.2 requires fields, but empty-mapping is
        # *syntactically* valid YAML; the caller's schema will reject it
        # via missing-required-field errors. Don't double-enforce here.
        return {}

    try:
        loaded = yaml.safe_load(yaml_body)
    except yaml.YAMLError as exc:
        logger.warning("frontmatter parse: malformed YAML in %s: %s", path, exc)
        return None

    if loaded is None:
        # Comments-only body (e.g. ``---\n# c\n---``) yields ``None`` from
        # safe_load. Treat the same as empty frontmatter — empty mapping.
        return {}

    if not isinstance(loaded, dict):
        logger.warning(
            "frontmatter parse: top-level mapping required in %s, got %s",
            path,
            type(loaded).__name__,
        )
        return None

    return loaded
