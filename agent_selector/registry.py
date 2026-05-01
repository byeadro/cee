"""Agent registry rebuilder — boots the agent catalog from filesystem state.

Authorized by:

- bible 04 §11 ("Index rebuild") — names this module and its
  ``rebuild()`` export, declares it stateless ("filesystem walk alone").
- bible 04 §6.5 ("Registries") — the literal record shape this rebuilder
  emits: ``{slug, path, version, frontmatter}``.
- bible 00 §12 B5 ("Build agent registry") — the boot step that calls
  this rebuilder ("Walk ``~/cee/.claude/agents/``, parse frontmatter,
  build ``index.json``."). B5 itself is terse on failure handling, but
  bible 04 §11 DoD — "Index rebuilds work from filesystem walk alone"
  — and B4's "logged and skipped, not loaded" set the precedent: a
  single bad agent file does not halt the boot. Applied symmetrically.
- bible 16 §5.2 — frontmatter contract this rebuilder consumes; in
  particular, ``name`` "must match filename (without .md extension)"
  (line 80, also constraint table line 116, also the validator error
  message at line 615). The cross-check is the registry's job because
  the schema only knows the slug regex, not the filename.
- bible 16 §3 — agents are flat files at ``<agents_dir>/<slug>.md``;
  any directory under ``<agents_dir>/`` (e.g., ``agent_resources/``,
  per bible 16 §3 the canonical home for any future supporting files)
  is NOT an agent and is ignored.
- bible 14 — atomic writes only; never raw ``open()`` for writes.

Behavior, in order:

    1. Glob ``agents_dir`` (default ``paths.AGENTS_DIR``) for top-level
       ``*.md`` files. Subdirectories and non-``.md`` entries
       (``.gitkeep``, ``.DS_Store``, ``index.json``) are skipped without
       a warning — they are not invalid agents, they are simply not
       agents.
    2. For each ``<slug>.md``, parse frontmatter via
       ``skill_engine.parsers.parse_frontmatter`` (the parser is shared
       with the Skill registry; bible 15 §11 names it as
       ``skill_engine/parsers.py`` and bible 16 §11 cross-references it
       for agents). The parser returns ``None`` on any I/O or YAML
       failure and has already logged the warning.
    3. Validate the parsed dict against ``schemas.AgentFrontmatter``
       (``extra="forbid"``). On ``ValidationError``, log + skip.
    4. Cross-check ``frontmatter.name == filename_stem`` per bible 16
       §5.2. On mismatch, log + skip.
    5. Emit a record per bible 04 §6.5:
       ``{slug, path, version, frontmatter}`` — ``path`` is relative to
       ``agents_dir``, ``frontmatter`` is the full validated dict.
    6. Sort results by ``slug`` for byte-stable ``index.json`` output.
    7. Atomically write ``<agents_dir>/index.json`` via
       ``persistence.atomic.atomic_write_json``.

Empty-catalog case: an empty ``agents_dir`` returns ``[]`` and writes
``[]`` to ``index.json``. No state is carried between runs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from paths import AGENTS_DIR
from persistence.atomic import atomic_write_json
from schemas.agent_frontmatter import AgentFrontmatter
from skill_engine.parsers import parse_frontmatter

logger = logging.getLogger(__name__)

# Bible 04 §6.5: the index file name is fixed by spec.
_INDEX_FILENAME = "index.json"


def rebuild(agents_dir: Path = AGENTS_DIR) -> list[dict]:
    """Walk ``agents_dir`` and rebuild ``<agents_dir>/index.json``.

    Returns the list of records written to the index (also written to
    disk atomically). Each record matches bible 04 §6.5:

        {"slug": "...", "path": "...", "version": "...",
         "frontmatter": {...}}

    Agents whose frontmatter cannot be parsed (parser returns ``None``),
    fail ``AgentFrontmatter`` validation, or have a ``name`` that
    disagrees with their filename are logged at WARNING and skipped —
    never partially included.

    Bible 16 §3 declares agents as flat ``<slug>.md`` files; any
    subdirectory under ``agents_dir`` is ignored. The conventional
    ``index.json``, ``.gitkeep``, and OS detritus (``.DS_Store``) are
    likewise skipped silently — they're not agents, so they're not
    "invalid agents."

    Results are sorted by slug so the same filesystem state always
    produces the same ``index.json`` bytes.
    """
    agents_dir = Path(agents_dir)
    records: list[dict] = []

    if agents_dir.is_dir():
        for entry in sorted(agents_dir.iterdir()):
            if not entry.is_file() or entry.suffix != ".md":
                continue
            record = _load_agent(entry, agents_dir)
            if record is not None:
                records.append(record)

    records.sort(key=lambda r: r["slug"])

    atomic_write_json(agents_dir / _INDEX_FILENAME, records)
    return records


def _load_agent(agent_md: Path, catalog_root: Path) -> dict | None:
    """Parse + validate a single ``<slug>.md`` agent file; return a
    record or ``None`` (with a logged warning) on any failure.

    The slug is derived from the filename stem. Bible 16 §5.2 requires
    ``frontmatter.name == <filename without .md>``; the schema does
    not enforce this cross-check (it only validates ``name`` matches
    the slug regex). We enforce the filename match here so the index
    cannot point a slug at an agent whose self-declared name disagrees.
    """
    slug = agent_md.stem

    metadata = parse_frontmatter(agent_md)
    if metadata is None:
        # parser already logged; nothing to add here.
        return None

    try:
        validated = AgentFrontmatter.model_validate(metadata)
    except ValidationError as exc:
        logger.warning(
            "agent registry: frontmatter validation failed for %s: %s",
            agent_md,
            exc,
        )
        return None

    if validated.name != slug:
        logger.warning(
            "agent registry: frontmatter name=%r disagrees with filename "
            "stem=%r at %s",
            validated.name,
            slug,
            agent_md,
        )
        return None

    return {
        "slug": slug,
        "path": str(agent_md.relative_to(catalog_root)),
        "version": validated.version,
        "frontmatter": validated.model_dump(mode="json", exclude_none=True),
    }
