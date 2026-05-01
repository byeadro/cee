"""Skill registry rebuilder — boots the Skill catalog from filesystem state.

Authorized by:

- bible 04 §11 ("Index rebuild") — names this module and its
  ``rebuild()`` export, declares it stateless ("filesystem walk alone").
- bible 04 §6.5 ("Registries") — the literal record shape this rebuilder
  emits: ``{slug, path, version, frontmatter}``.
- bible 00 §12 B4 ("Build Skill registry") — the boot step that calls
  this rebuilder; mandates "Skills with invalid frontmatter are logged
  and skipped, not loaded."
- bible 15 §11 — names the parser module (``skill_engine/parsers.py``)
  this rebuilder delegates to.
- bible 14 — atomic writes only; never raw ``open()`` for writes.

Behavior, in order:

    1. Walk ``skills_dir`` (default ``paths.SKILLS_DIR``) for
       ``<slug>/SKILL.md`` files.
    2. For each, parse frontmatter via
       ``skill_engine.parsers.parse_frontmatter`` (returns ``None`` on
       any I/O or YAML failure; the parser already logged the warning).
    3. Validate the parsed dict against ``schemas.SkillFrontmatter``
       (``extra="forbid"``). On ``ValidationError``, log + skip.
    4. Emit a record per bible 04 §6.5:
       ``{slug, path, version, frontmatter}`` — ``path`` is relative to
       ``skills_dir``, ``frontmatter`` is the full validated dict.
    5. Sort results by ``slug`` for byte-stable ``index.json`` output.
    6. Atomically write ``<skills_dir>/index.json`` via
       ``persistence.atomic.atomic_write_json``.

Empty-catalog case (bible 04 §11 DoD: "Index rebuilds work from
filesystem walk alone"): an empty ``skills_dir`` returns ``[]`` and
writes ``[]`` to ``index.json``. No state is carried between runs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from paths import SKILLS_DIR
from persistence.atomic import atomic_write_json
from schemas.skill_frontmatter import SkillFrontmatter
from skill_engine.parsers import parse_frontmatter

logger = logging.getLogger(__name__)

# Bible 04 §6.5: the index file name is fixed by spec.
_INDEX_FILENAME = "index.json"


def rebuild(skills_dir: Path = SKILLS_DIR) -> list[dict]:
    """Walk ``skills_dir`` and rebuild ``<skills_dir>/index.json``.

    Returns the list of records written to the index (also written to
    disk atomically). Each record matches bible 04 §6.5:

        {"slug": "...", "path": "...", "version": "...",
         "frontmatter": {...}}

    Skills whose frontmatter cannot be parsed (parser returns ``None``)
    or fails ``SkillFrontmatter`` validation are logged at WARNING and
    skipped — never partially included. Bible 00 §12 B4: "logged and
    skipped, not loaded."

    The walk is non-recursive in spirit (one level: ``<skills_dir>/<slug>/
    SKILL.md``) per bible 15 §5: a Skill is a directory at the top of
    the catalog. Nested directories are not Skills and are ignored.

    Results are sorted by slug so the same filesystem state always
    produces the same ``index.json`` bytes.
    """
    skills_dir = Path(skills_dir)
    records: list[dict] = []

    if skills_dir.is_dir():
        for skill_dir in sorted(skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            record = _load_skill(skill_dir, skills_dir)
            if record is not None:
                records.append(record)

    records.sort(key=lambda r: r["slug"])

    atomic_write_json(skills_dir / _INDEX_FILENAME, records)
    return records


def _load_skill(skill_dir: Path, catalog_root: Path) -> dict | None:
    """Parse + validate a single ``<slug>/SKILL.md``; return a record or
    ``None`` (with a logged warning) on any failure.

    The slug is derived from the directory name. Bible 15 §5.2 also
    requires ``frontmatter.name == slug``; the schema does not enforce
    that cross-check (it only validates ``name`` matches the slug
    regex). We enforce the directory-name match here so the index
    cannot point a slug at a Skill whose self-declared name disagrees.
    """
    skill_md = skill_dir / "SKILL.md"
    slug = skill_dir.name

    metadata = parse_frontmatter(skill_md)
    if metadata is None:
        # parser already logged; nothing to add here.
        return None

    try:
        validated = SkillFrontmatter.model_validate(metadata)
    except ValidationError as exc:
        logger.warning(
            "skill registry: frontmatter validation failed for %s: %s",
            skill_md,
            exc,
        )
        return None

    if validated.name != slug:
        logger.warning(
            "skill registry: frontmatter name=%r disagrees with directory "
            "name=%r at %s",
            validated.name,
            slug,
            skill_md,
        )
        return None

    return {
        "slug": slug,
        "path": str(skill_md.relative_to(catalog_root)),
        "version": validated.version,
        "frontmatter": validated.model_dump(mode="json", exclude_none=True),
    }
