"""Single source of truth for all CEE filesystem paths.

This module is the only place where CEE paths are defined. Every other
module in the codebase MUST import constants from here rather than
constructing paths via string concatenation, ``os.path.join``, or
hand-rolled expansion of ``~``. The bible — specifically
``04_database_file_structure.md`` (§5.1 filesystem, §5.2 user config,
§5.3 Obsidian mirror) and ``12_prompt_leak_security_rules.md`` (the
``security.log`` audit file) — is the spec; this module is the
executable mirror.

Importing this module has NO side effects: no directories are created,
no environment variables are read, no system clock is read. Callers
that require a directory to exist must call :func:`ensure_dir`
explicitly.
"""

from __future__ import annotations

import re
from pathlib import Path

# The single point at which "~" is expanded. Used internally only.
_HOME: Path = Path.home()

# ─── ~/cee/ — filesystem canon (bible 04 §5.1) ──────────────────────────

CEE_ROOT: Path = _HOME / "cee"

# Bible mirror
BIBLE_DIR: Path = CEE_ROOT / "bible"
BIBLE_SYNC_META: Path = BIBLE_DIR / ".sync_meta.json"

# Top-level CEE root contents
SCHEMAS_DIR: Path = CEE_ROOT / "schemas"
PROMPTS_DIR: Path = CEE_ROOT / "prompts"
SKILLS_DIR: Path = CEE_ROOT / "skills"
RUNS_DIR: Path = CEE_ROOT / "runs"
GOLDEN_RUNS_DIR: Path = RUNS_DIR / "golden"
AUDIT_DIR: Path = CEE_ROOT / "audit"
AUDIT_ARCHIVE_DIR: Path = AUDIT_DIR / "archive"
TEMPLATE_DIR: Path = CEE_ROOT / ".template"
# Default config template — copied to USER_CONFIG_DIR/config.toml on first
# boot. Authoritative reference: bible 04 §10.7 ("Default config can be
# regenerated from ``~/cee/.template/config.toml.default``"). The ``.default``
# suffix marks this file as the read-only template; the OPERATOR-editable
# copy lives at :data:`CONFIG_FILE`.
TEMPLATE_CONFIG_FILE: Path = TEMPLATE_DIR / "config.toml.default"
TESTS_DIR: Path = CEE_ROOT / "tests"
TESTS_FIXTURES_DIR: Path = TESTS_DIR / "fixtures"

# Claude Code project layout under the CEE project root
AGENTS_DIR: Path = CEE_ROOT / ".claude" / "agents"
COMMANDS_DIR: Path = CEE_ROOT / ".claude" / "commands"
HOOKS_DIR: Path = CEE_ROOT / ".claude" / "hooks"

# CEE module directories — each is a Python package
INTERPRETER_DIR: Path = CEE_ROOT / "interpreter"
CLASSIFIER_DIR: Path = CEE_ROOT / "classifier"
AGENT_SELECTOR_DIR: Path = CEE_ROOT / "agent_selector"
SKILL_ENGINE_DIR: Path = CEE_ROOT / "skill_engine"
STRATEGY_BUILDER_DIR: Path = CEE_ROOT / "strategy_builder"
PROMPT_BUILDER_DIR: Path = CEE_ROOT / "prompt_builder"
SAFETY_GATE_DIR: Path = CEE_ROOT / "safety_gate"
PERSISTENCE_DIR: Path = CEE_ROOT / "persistence"
BOOT_DIR: Path = CEE_ROOT / "boot"
EXECUTOR_DIR: Path = CEE_ROOT / "executor"
ROLES_DIR: Path = CEE_ROOT / "roles"
ERRORS_DIR: Path = CEE_ROOT / "errors"
OUTPUT_FORMAT_DIR: Path = CEE_ROOT / "output_format"
GROUNDING_DIR: Path = CEE_ROOT / "grounding"

# Specific files in CEE root
PROMOTION_QUEUE: Path = CEE_ROOT / "promotion_queue.json"

# Audit log files (bible 04 §5.1 + 12 §5 for security.log)
AUDIT_CLI_LOG: Path = AUDIT_DIR / "cli.log"
AUDIT_ROLES_LOG: Path = AUDIT_DIR / "roles.log"
AUDIT_BOOT_LOG: Path = AUDIT_DIR / "boot.log"
AUDIT_SECURITY_LOG: Path = AUDIT_DIR / "security.log"

# ─── ~/.cee/ — user config (bible 04 §5.2) ──────────────────────────────

USER_CONFIG_DIR: Path = _HOME / ".cee"
CONFIG_FILE: Path = USER_CONFIG_DIR / "config.toml"
REDACT_LIST: Path = USER_CONFIG_DIR / "redact_list"
NOTION_REDACT_LIST: Path = USER_CONFIG_DIR / "notion_redact_list"
CREDENTIALS_FILE: Path = USER_CONFIG_DIR / "credentials.toml"

# ─── ~/SecondBrain/cee/ — Obsidian mirror (bible 04 §5.3, 13 §5.1) ──────

OBSIDIAN_VAULT: Path = _HOME / "SecondBrain" / "cee"
OBSIDIAN_RUNS_DIR: Path = OBSIDIAN_VAULT / "runs"
OBSIDIAN_SKILLS_DIR: Path = OBSIDIAN_VAULT / "skills"
OBSIDIAN_AGENTS_DIR: Path = OBSIDIAN_VAULT / "agents"
OBSIDIAN_BIBLE_DIR: Path = OBSIDIAN_VAULT / "bible"
OBSIDIAN_AUDIT_DIR: Path = OBSIDIAN_VAULT / "audit"
OBSIDIAN_TEMPLATES_DIR: Path = OBSIDIAN_VAULT / "_templates"

# ─── Helpers ────────────────────────────────────────────────────────────

# Run ID format from bible 04 §4 Rule 3:
#   <YYYYMMDD>_<HHMMSS>_<8-char-hex>
# Example: 20260430_141522_a3f8c2d1
_RUN_ID_PATTERN: re.Pattern[str] = re.compile(r"^\d{8}_\d{6}_[0-9a-f]{8}$")


def ensure_dir(path: Path) -> Path:
    """Create the directory at ``path`` if missing; return ``path``.

    Idempotent: calling on an existing directory is a no-op. This is the
    only sanctioned way for callers to materialise a directory; importing
    this module never creates anything on disk.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def derive_run_dir(run_id: str) -> Path:
    """Return ``RUNS_DIR / run_id`` after validating ``run_id``.

    Run IDs follow the bible 04 §4 Rule 3 pattern
    ``<YYYYMMDD>_<HHMMSS>_<8-char-hex>``. A non-conforming ``run_id``
    raises :class:`ValueError` rather than silently producing a path that
    would break downstream readers.
    """
    if not _RUN_ID_PATTERN.match(run_id):
        raise ValueError(
            f"invalid run_id {run_id!r}: expected pattern "
            "<YYYYMMDD>_<HHMMSS>_<8-char-hex> per bible 04 §4 Rule 3"
        )
    return RUNS_DIR / run_id
