"""``cee verify`` — installation drift detection.

Phase 1 ships two modes:

* ``--layout`` (task 14) — walks the canonical paths declared in
  :mod:`paths` and reports any required directory or file that's
  missing. Existence checks only — permission checks (chmod 600 on
  ``raw_input.json``, etc.) are deferred to Phase 5+ when the security
  writer ships and the ``--security`` mode is added.
* ``--schemas`` (task 15) — imports every artifact schema, asserts the
  ``SCHEMA_VERSION`` ClassVar is ``"1.0.0"``, asserts pipeline schemas
  declare ``produced_by: RoleEnum``, and asserts ``model_json_schema()``
  output round-trips through ``json.dumps``/``json.loads``.

Bible mapping (layout):

* **04 §10.1** — Layout drift failure mode. The verifier is the
  detector named in the recovery procedure.
* **04 §11** — Build notes name ``cee verify`` as the layout-invariants
  test entry point.
* **04 §12** — Definition of Done: "cee verify walks all three substrates
  and reports drift".
* **04 §5.1, §5.2, §5.3** — the three canonical layouts (filesystem,
  user config, Obsidian vault).
* **12 §5.8** — audit log file layout.
* **13 §5.1** — Obsidian vault layout (mirrored by ``scaffold_obsidian``).

Bible mapping (schemas):

* **04 §6.1** — original 12 artifact schemas (RawInput → AgentFrontmatter).
* **10 §6.3** — adds ``GroundingDeclaration`` to the canonical set.
* **11 §6.2** — adds ``FormatDeclaration`` to the canonical set.
* **04 §5.5** — adds ``SyncMeta`` (Phase 2 task 1, gap 2 deferral closed).
* **04 §5.2** — adds ``Credentials`` (Phase 2 task 2, gap 8 deferral closed).
* **21 §5.2 task 15** — operational build notes for this command.

The reconciled count is **16 schemas**, split five ways for reporting:

* **Pipeline artifacts (10)** — produced/consumed by the pipeline at
  runtime. Each declares ``produced_by: RoleEnum``.
* **Frontmatter (2)** — describe ``.md`` files on disk; no ``produced_by``.
* **Declaration (2)** — embedded inside ``FinalPrompt``/``RunSummary``;
  no top-level ``produced_by``.
* **Bible sync state (1)** — ``SyncMeta`` for ``~/cee/bible/.sync_meta.json``;
  declares ``produced_by: RoleEnum.BOOT_SEQUENCER`` (bible 04 §5.5).
* **User config (1)** — ``Credentials`` for ``~/.cee/credentials.toml``;
  user-managed, no ``produced_by`` (bible 04 §5.2).

The 23-path layout canonical set:

* **User config (4)**: ``~/.cee/`` + ``config.toml`` + ``redact_list``
  + ``notion_redact_list``. Bible 04 §5.2 + bible 12 §5.3.
  ``credentials.toml`` is deferred to Phase 2.
* **Obsidian vault (13)**: ``~/SecondBrain/cee/`` + ``README.md`` +
  five content dirs + their five ``index.md`` files + ``_templates/``.
  Bible 13 §5.1 (mirrored exactly by ``scaffold_obsidian``). The
  ``_templates/`` directory is intentionally empty in Phase 1; the five
  template files inside ship with their Phase 5+ renderers.
* **Audit logs (6)**: ``~/cee/audit/`` + ``archive/`` + four log files.
  Bible 12 §5.8 + bible 04 §5.1.

Future ``cee verify`` modes (out of scope for Phase 1):

* ``--bible`` — check the bible mirror against Notion (Phase 2).
* ``--security`` — permission checks on ``raw_input.json`` etc.
  (Phase 5+).
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

import paths
from roles import RoleEnum


# ─── Canonical path manifests ───────────────────────────────────────────


def _user_config_required() -> tuple[tuple[Path, str], ...]:
    """User-config layout per bible 04 §5.2 + bible 12 §5.3.

    Resolved at call time so test monkeypatching of ``paths.*`` works.
    """
    return (
        (paths.USER_CONFIG_DIR, "directory"),
        (paths.CONFIG_FILE, "file"),
        (paths.REDACT_LIST, "file"),
        (paths.NOTION_REDACT_LIST, "file"),
    )


def _obsidian_required() -> tuple[tuple[Path, str], ...]:
    """Obsidian vault layout per bible 13 §5.1.

    Mirrors :func:`persistence.scaffold_obsidian` exactly: 7 directories
    (vault root + 5 content dirs + ``_templates/``) plus 6 files
    (``README.md`` + 5 ``index.md`` stubs). ``_templates/`` is
    intentionally empty in Phase 1 — bible 13 §5.1 lists 5 template
    ``.md`` files inside it that ship with the Phase 5+ renderers.
    """
    return (
        (paths.OBSIDIAN_VAULT, "directory"),
        (paths.OBSIDIAN_VAULT / "README.md", "file"),
        (paths.OBSIDIAN_RUNS_DIR, "directory"),
        (paths.OBSIDIAN_RUNS_DIR / "index.md", "file"),
        (paths.OBSIDIAN_SKILLS_DIR, "directory"),
        (paths.OBSIDIAN_SKILLS_DIR / "index.md", "file"),
        (paths.OBSIDIAN_AGENTS_DIR, "directory"),
        (paths.OBSIDIAN_AGENTS_DIR / "index.md", "file"),
        (paths.OBSIDIAN_BIBLE_DIR, "directory"),
        (paths.OBSIDIAN_BIBLE_DIR / "index.md", "file"),
        (paths.OBSIDIAN_AUDIT_DIR, "directory"),
        (paths.OBSIDIAN_AUDIT_DIR / "index.md", "file"),
        (paths.OBSIDIAN_TEMPLATES_DIR, "directory"),
    )


def _audit_required() -> tuple[tuple[Path, str], ...]:
    """Audit log layout per bible 12 §5.8 + bible 04 §5.1."""
    return (
        (paths.AUDIT_DIR, "directory"),
        (paths.AUDIT_ARCHIVE_DIR, "directory"),
        (paths.AUDIT_CLI_LOG, "file"),
        (paths.AUDIT_ROLES_LOG, "file"),
        (paths.AUDIT_BOOT_LOG, "file"),
        (paths.AUDIT_SECURITY_LOG, "file"),
    )


# ─── Output helpers ─────────────────────────────────────────────────────


def _shorten_path(p: Path) -> str:
    """Render ``p`` with ``~`` shorthand for the user's home directory.

    A trailing ``/`` is appended for directories (purely cosmetic — keeps
    the report visually consistent with the way humans read directory
    paths in shell prompts).
    """
    home = Path.home()
    try:
        rel = p.relative_to(home)
        rendered = "~/" + str(rel)
    except ValueError:
        rendered = str(p)
    if p.is_dir():
        rendered = rendered.rstrip("/") + "/"
    return rendered


def _render_item(p: Path, kind: str) -> str:
    """One report line for one required path.

    Three states:

    * present + correct kind → ``✓ <path>  (<kind>)``
    * present but wrong kind (file where directory expected, etc.) →
      ``✗ <path>  WRONG_TYPE (expected <kind>)``
    * missing → ``✗ <path>  MISSING (<kind>)``

    Wrong-type is reported separately from missing because the
    remediation differs: ``cee init`` won't fix a stale file occupying
    a directory slot — the OPERATOR has to remove it first.
    """
    if not p.exists():
        return f"✗ {_shorten_path(p)}  MISSING ({kind})"
    actual_is_dir = p.is_dir()
    expected_is_dir = kind == "directory"
    if actual_is_dir != expected_is_dir:
        return f"✗ {_shorten_path(p)}  WRONG_TYPE (expected {kind})"
    return f"✓ {_shorten_path(p)}  ({kind})"


def _is_ok(p: Path, kind: str) -> bool:
    """True iff ``p`` exists and matches the expected kind."""
    if not p.exists():
        return False
    return p.is_dir() == (kind == "directory")


# ─── Schema manifest ────────────────────────────────────────────────────


# (module_name, class_name, has_produced_by, category)
#
# The 16 canonical artifact schemas per bible 04 §6.1 + 04 §5.5 + 04 §5.2
# + 10 §6.3 + 11 §6.2. Class names verified against the actual modules —
# drift here means either a schema was renamed or this manifest is stale;
# either way the importlib lookup below will catch it. Keep in module-load
# order so the report reads top-to-bottom in the same order pipeline
# artifacts are produced (raw_input → run_summary), with bible sync state
# and user config last.
SCHEMA_MANIFEST: tuple[tuple[str, str, bool, str], ...] = (
    ("schemas.raw_input", "RawInput", True, "pipeline"),
    ("schemas.intent_object", "IntentObject", True, "pipeline"),
    ("schemas.classification", "Classification", True, "pipeline"),
    ("schemas.agent_plan", "AgentPlan", True, "pipeline"),
    ("schemas.skill_set", "SkillSet", True, "pipeline"),
    ("schemas.execution_strategy", "ExecutionStrategy", True, "pipeline"),
    ("schemas.final_prompt", "FinalPrompt", True, "pipeline"),
    ("schemas.clarification_request", "ClarificationRequest", True, "pipeline"),
    ("schemas.run_error", "RunError", True, "pipeline"),
    ("schemas.run_summary", "RunSummary", True, "pipeline"),
    ("schemas.skill_frontmatter", "SkillFrontmatter", False, "frontmatter"),
    ("schemas.agent_frontmatter", "AgentFrontmatter", False, "frontmatter"),
    ("schemas.grounding_declaration", "GroundingDeclaration", False, "declaration"),
    ("schemas.format_declaration", "FormatDeclaration", False, "declaration"),
    ("schemas.sync_meta", "SyncMeta", True, "bible_sync"),
    ("schemas.credentials", "Credentials", False, "user_config"),
)

_CATEGORY_HEADINGS: tuple[tuple[str, str], ...] = (
    ("pipeline", "Pipeline artifact schemas"),
    ("frontmatter", "Frontmatter schemas"),
    ("declaration", "Declaration schemas"),
    ("bible_sync", "Bible sync state schemas"),
    ("user_config", "User config schemas"),
)

# Pad the class-name column to one space past the longest name in the
# manifest (ClarificationRequest = 20). Hard-coded so a future rename
# loudly breaks the visual grid instead of silently shifting columns.
_NAME_COLUMN_WIDTH = 22


def _verify_one_schema(
    module_name: str, class_name: str, has_produced_by: bool,
) -> tuple[bool, str | None]:
    """Validate a single schema. Returns ``(ok, reason)``.

    ``reason`` is ``None`` on success and a short kebab-style tag on
    failure (``import_error``, ``missing_class``, ``wrong_schema_version``,
    ``missing_produced_by``, ``wrong_produced_by_type``,
    ``invalid_json_schema``). The tag is what the OPERATOR sees on the
    report line; the upstream exception message is appended for context.
    """
    try:
        module = importlib.import_module(module_name)
    except Exception as e:  # noqa: BLE001 — any import failure is a fail
        return (False, f"import_error: {type(e).__name__}: {e}")

    cls = getattr(module, class_name, None)
    if cls is None:
        return (False, f"missing_class: {class_name}")

    schema_version = getattr(cls, "SCHEMA_VERSION", None)
    if schema_version != "1.0.0":
        return (False, f"wrong_schema_version: {schema_version!r}")

    if has_produced_by:
        field = cls.model_fields.get("produced_by")
        if field is None:
            return (False, "missing_produced_by")
        if field.annotation is not RoleEnum:
            return (False, f"wrong_produced_by_type: {field.annotation!r}")

    try:
        schema = cls.model_json_schema()
    except Exception as e:  # noqa: BLE001
        return (False, f"invalid_json_schema: {type(e).__name__}: {e}")
    if not isinstance(schema, dict):
        return (False, f"invalid_json_schema: not a dict ({type(schema).__name__})")
    try:
        # Round-trip through json so a non-serialisable value (set, bytes,
        # custom object that snuck into a default) fails here, not later
        # when an artifact is being persisted.
        json.loads(json.dumps(schema))
    except (TypeError, ValueError) as e:
        return (False, f"invalid_json_schema: {type(e).__name__}: {e}")

    return (True, None)


# ─── Verifier ───────────────────────────────────────────────────────────


def _verify_layout() -> int:
    """Walk canonical paths, render the report, return exit code.

    Returns
    -------
    int
        ``0`` if every required path is present with the correct kind;
        ``1`` otherwise. The full report is printed regardless so the
        OPERATOR sees both passing and failing items in context.
    """
    sections: tuple[tuple[str, str, tuple[tuple[Path, str], ...]], ...] = (
        ("User config (~/.cee/):", "USER_CONFIG", _user_config_required()),
        (
            "Obsidian vault (~/SecondBrain/cee/):",
            "OBSIDIAN",
            _obsidian_required(),
        ),
        ("Audit logs (~/cee/audit/):", "AUDIT", _audit_required()),
    )

    print("CEE Layout Verification")
    print()

    total = 0
    present = 0
    for heading, _label, items in sections:
        print(heading)
        for path, kind in items:
            print(f"  {_render_item(path, kind)}")
            total += 1
            if _is_ok(path, kind):
                present += 1
        print()

    missing = total - present
    print(f"Summary: {present} of {total} paths present.", end="")
    if missing == 0:
        print()
        print("PASSED.")
        return 0
    print(f" {missing} missing.")
    print("FAILED: run cee init to scaffold missing items.")
    return 1


def _verify_schemas() -> int:
    """Walk :data:`SCHEMA_MANIFEST`, validate each schema, render report.

    For each manifest entry, :func:`_verify_one_schema` checks: module
    imports, class exists, ``SCHEMA_VERSION == "1.0.0"``, ``produced_by``
    annotation is :class:`RoleEnum` (when applicable), and
    ``model_json_schema()`` output round-trips through JSON.

    The report mirrors :func:`_verify_layout` structure: section headings
    with counts, ``✓``/``✗`` per item, summary line, ``PASSED.``/``FAILED:``.

    Returns
    -------
    int
        ``0`` if every schema is valid; ``1`` otherwise.
    """
    print("CEE Schema Verification")
    print()

    # Run all checks first so the report shows full state even when
    # multiple schemas fail (don't short-circuit on first failure).
    results: list[tuple[str, str, str, bool, str | None]] = []
    for module_name, class_name, has_produced_by, category in SCHEMA_MANIFEST:
        ok, reason = _verify_one_schema(module_name, class_name, has_produced_by)
        results.append((module_name, class_name, category, ok, reason))

    for cat_key, cat_label in _CATEGORY_HEADINGS:
        cat_results = [r for r in results if r[2] == cat_key]
        print(f"{cat_label} ({len(cat_results)}):")
        for module_name, class_name, _cat, ok, reason in cat_results:
            mark = "✓" if ok else "✗"
            name_col = class_name.ljust(_NAME_COLUMN_WIDTH)
            line = f"  {mark} {name_col}({module_name})"
            if not ok:
                line += f"  {reason}"
            print(line)
        print()

    valid = sum(1 for r in results if r[3])
    total = len(results)
    print(f"Summary: {valid} of {total} schemas valid.")
    if valid == total:
        print("PASSED.")
        return 0
    print("FAILED: see schema errors above.")
    return 1


def cmd_verify(args: argparse.Namespace) -> int:
    """``cee verify`` dispatcher.

    Phase 1 ships ``--layout`` and ``--schemas``. Future modes
    (``--bible``, ``--security``) plug in here. Behaviour:

    * Neither flag → print usage hint to stderr, return ``2`` (matches
      argparse's malformed-invocation exit code).
    * One flag → run that mode, return its exit code.
    * Both flags → run both modes (in declaration order: layout, then
      schemas), return the worst exit code so a failure in either is
      surfaced.
    """
    if not (args.layout or args.schemas):
        print(
            "Specify a verify mode (e.g. --layout or --schemas)",
            file=sys.stderr,
        )
        return 2

    exit_codes: list[int] = []
    if args.layout:
        exit_codes.append(_verify_layout())
    if args.schemas:
        exit_codes.append(_verify_schemas())
    return max(exit_codes)
