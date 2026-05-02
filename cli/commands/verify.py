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

Phase 2 task 9 adds:

* ``--boot`` — runs the canonical boot sequence (:func:`boot.sequencer.run`,
  T8) and renders the per-step + halt-aware report. Exit 0 when
  :class:`boot.sequencer.BootResult` reports ``ok=True``; exit 1 on any
  halt at B1–B7. Per T8 design, ``boot.sequencer.run`` returns a
  :class:`BootResult` rather than raising — so this mode inspects
  ``result.ok`` directly and never relies on :func:`cli.main.main`'s
  outer ``BootError`` catch.

Phase 2 task 10 adds:

* ``--bible`` — runs both the cross-section consistency check
  (:func:`boot.consistency.check`, T5) and the bible-drift check
  (:func:`boot.bible_sync.check_drift`, T6) within a single report.
  Exit 0 when both checks pass; exit 1 if either reports drift OR
  :func:`check_drift` halts on :class:`errors.BootBibleSyncError`.
  Like ``--boot``, this mode never propagates exceptions — drift-side
  halts are caught and rendered as a section ✗ with reuse of T9's
  ``_BOOT_HALT_HINTS`` table for the stderr remediation hint.

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

Future ``cee verify`` modes (still out of scope as of T10):

* ``--security`` — permission checks on ``raw_input.json`` etc.
  (Phase 5+).

Bible mapping (boot, task 9):

* **00 §12** — the canonical 9-step boot sequence (B1–B9).
* **20 §5.2 line 148** — names ``cee verify --boot`` verbatim.
* **02 §7.13** — ``BOOT_SEQUENCER`` is the role; this command
  invokes it from the operator surface.

Bible mapping (bible, task 10):

* **00 §12 step B3** — cross-section consistency check.
* **04 §5.5 + §5.6** — ``.sync_meta.json`` schema + drift detection
  semantics (read by :func:`boot.bible_sync.check_drift`).
* **20 §5.2 line 148** — names ``cee verify --bible`` verbatim.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

import paths
from errors import BootBibleSyncError
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


# ─── Boot verifier (Phase 2 task 9) ─────────────────────────────────────


# Remediation hints surfaced on halt. Keyed by ``(error_class_name,
# kind)``; the dispatcher falls back to ``(error_class_name, None)`` if
# the exact ``kind`` isn't registered, then to a generic catch-all line
# if neither lookup hits. Hints intentionally point the OPERATOR at the
# bible §s that justify the halt cause so the recovery is grounded.
#
# The canonical home for these hints is bible 19 §5.6 ("user-facing
# message format" with "To resume" exact CLI commands). T9 ships them
# inline; surface as downstream candidate for migration into a bible-
# read template loader once Phase 3+ ships :mod:`errors.messages`.
_BOOT_HALT_HINTS: dict[tuple[str, str | None], str] = {
    ("BootEnvironmentError", "python_version"):
        "upgrade Python to >= 3.11 (tomllib stdlib requirement)",
    ("BootEnvironmentError", "missing_package"):
        "reinstall dependencies via `pip install -e .`",
    ("BootEnvironmentError", "path_not_writable"):
        "check ownership/permissions on the listed path; "
        "run `cee init` if the directory is missing",
    ("BootEnvironmentError", "config_invalid"):
        "run `cee init` to scaffold ~/.cee/config.toml from the template",
    ("BootBibleSyncError", "credentials_missing"):
        "populate ~/.cee/credentials.toml [anthropic] api_key per bible 04 §5.2",
    ("BootBibleSyncError", "mcp_connect_failed"):
        "check Notion MCP transport reachability; "
        "verify [anthropic] api_key validity",
    ("BootBibleSyncError", "page_deleted"):
        "restore the bible parent page in Notion per bible 04 §9 EC9",
    ("BootBibleSyncError", "auto_sync_disabled"):
        "run `cee sync-bible` manually, OR set `auto_sync = true` "
        "in ~/.cee/config.toml",
    ("BootConsistencyError", None):
        "reconcile the listed enum drifts — bible canonicals vs code mirrors",
    ("BootRegistryError", "skill"):
        "check filesystem permissions on ~/cee/skills/",
    ("BootRegistryError", "agent"):
        "check filesystem permissions on ~/cee/.claude/agents/",
    ("BootSchemaError", None):
        "check the named schemas/* module for syntax / import errors",
    ("BootRunIndexError", None):
        "check filesystem permissions on ~/cee/runs/",
}

_BOOT_HALT_HINT_FALLBACK = (
    "contact operator; see ~/cee/audit/boot.log for full halt details"
)


# Per-step labels rendered next to ``B<n>`` in the report. Closed set —
# matches bible 00 §12's nine canonical steps verbatim.
_BOOT_STEP_LABELS: dict[str, str] = {
    "B1": "verify_environment",
    "B2": "load_bible",
    "B3": "consistency_check",
    "B4": "build_skill_registry",
    "B5": "build_agent_registry",
    "B6": "load_schemas",
    "B7": "load_recent_runs",
    "B8": "drain_promotion_queue",
    "B9": "ready",
}

# Pad the per-step label column to one space past the longest entry
# (``build_agent_registry`` = 20). Hard-coded so a future relabel
# loudly breaks the visual grid instead of silently shifting columns.
_BOOT_LABEL_COLUMN_WIDTH = 22


def _run_boot_sequence():
    """Thin seam over :func:`boot.sequencer.run`.

    Tests mock this single seam via
    ``patch.object(verify_module, "_run_boot_sequence", ...)`` rather
    than monkey-patching :mod:`boot.sequencer` directly, matching the
    existing ``patch.object(verify_module, "_verify_layout")`` pattern.
    """
    from boot.sequencer import run as _boot_run

    return _boot_run()


def _format_step_line(step: object) -> str:
    """One report line for one :class:`boot.sequencer.BootStepResult`."""
    label = _BOOT_STEP_LABELS.get(step.step, "?")
    mark = "✓" if step.ok else "✗"
    label_col = label.ljust(_BOOT_LABEL_COLUMN_WIDTH)
    summary = step.summary
    # Cap summary to keep the visual grid readable; the full payload is
    # always preserved on the BootResult itself for programmatic access.
    if len(summary) > 60:
        summary = summary[:57] + "..."
    summary_col = summary.ljust(60)
    return f"  {mark} {step.step}  {label_col}{summary_col}  ({step.duration_ms} ms)"


def _hint_for_halt(halt_error: object) -> str:
    """Look up the remediation hint for a typed :class:`BootError`.

    Lookup precedence: ``(class_name, kind)`` → ``(class_name, None)``
    → :data:`_BOOT_HALT_HINT_FALLBACK`.
    """
    class_name = type(halt_error).__name__
    kind = getattr(halt_error, "kind", None)
    if (class_name, kind) in _BOOT_HALT_HINTS:
        return _BOOT_HALT_HINTS[(class_name, kind)]
    if (class_name, None) in _BOOT_HALT_HINTS:
        return _BOOT_HALT_HINTS[(class_name, None)]
    return _BOOT_HALT_HINT_FALLBACK


def _verify_boot() -> int:
    """Run the canonical boot sequence and render the operator report.

    Per T8's contract, :func:`boot.sequencer.run` returns a
    :class:`boot.sequencer.BootResult` — it does NOT propagate
    :class:`errors.BootError` to its caller. Halt is reflected in
    ``result.ok=False`` + ``result.halt_step`` + ``result.halt_error``.
    This function inspects ``result.ok`` directly and translates to an
    exit code; it does NOT rely on :func:`cli.main.main`'s outer
    ``BootError`` catch (which remains live as a safety net for any
    unexpected raise from within the sequencer).

    Returns
    -------
    int
        ``0`` if every B-step succeeded (B1–B9 all green; B8 best-
        effort warnings do not gate the exit code per T8 design);
        ``1`` if the sequencer halted at any of B1–B7. Exit code
        ``2`` is reserved for the outer :func:`cli.main.main` catch
        — non-CEE exceptions only.
    """
    result = _run_boot_sequence()

    print("CEE Boot Verification")
    print()
    print("Boot sequence (B1–B9):")
    for step in result.steps:
        print(_format_step_line(step))
    print()

    # Warnings (rendered before Summary so the OPERATOR sees them in
    # context with the per-step report).
    if result.warnings:
        print(f"Warnings ({len(result.warnings)}):")
        for warning in result.warnings:
            print(f"  ! {warning}")
        print()

    passed_count = sum(1 for s in result.steps if s.ok)
    if result.ok:
        print(
            f"Summary: {passed_count} of 9 steps passed. "
            f"Total duration: {result.total_duration_ms} ms. "
            f"{len(result.warnings)} warning(s)."
        )
        print("PASSED.")
        return 0

    # Halt path. ``halt_step`` and ``halt_error`` are guaranteed
    # populated when ok=False per T8's BootResult contract.
    halt_step = result.halt_step
    halt_error = result.halt_error
    print(
        f"Summary: {passed_count} of 9 steps passed (halted at {halt_step}). "
        f"Total duration: {result.total_duration_ms} ms."
    )
    print(f"FAILED: boot halted at {halt_step}.")

    # Halt detail to stderr — separable from the stdout report so log
    # scrapers can grep for ``BOOT HALT`` independently.
    class_name = type(halt_error).__name__
    kind = getattr(halt_error, "kind", None)
    kind_render = f"(kind={kind})" if kind is not None else ""
    sys.stderr.write(
        f"BOOT HALT [{halt_step}] {class_name}{kind_render}\n"
    )
    reason = getattr(halt_error, "reason", str(halt_error))
    sys.stderr.write(f"Reason: {reason}\n")
    sys.stderr.write(f"Hint: {_hint_for_halt(halt_error)}\n")

    return 1


# ─── Bible verifier (Phase 2 task 10) ──────────────────────────────────


# Drift-category remediation hints. Keyed by the :class:`boot.bible_sync.
# DriftReport` field name; surfaced on stderr per category that contains
# at least one item. A separate table from T9's :data:`_BOOT_HALT_HINTS`
# because the keying shape differs (drift category vs error class+kind).
# Long-term these belong in bible 19 §5.6 alongside the boot-halt hints
# (downstream candidate alongside #24).
_BIBLE_DRIFT_HINTS: dict[str, str] = {
    "notion_newer":
        "run `cee sync-bible` to pull updates from Notion",
    "mirror_modified":
        "review local edits; run `cee sync-bible --force` to overwrite "
        "(Phase 5+ feature) or manually sync to Notion",
    "orphan":
        "remove from ~/cee/bible/ or add to .sync_meta.json "
        "(manual until Phase 5+ tooling)",
    "missing_from_meta":
        "run `cee sync-bible` to fetch + register the page",
}

# DriftReport categories rendered in the per-category report block. The
# tuple order is the canonical render order; each entry is
# ``(field_name, render_label)``.
_DRIFT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("in_sync", "in_sync"),
    ("notion_newer", "notion_newer"),
    ("mirror_modified", "mirror_modified"),
    ("orphan", "orphan"),
    ("missing_from_meta", "missing_from_meta"),
)

# Categories that constitute "drift" — listed here because
# :attr:`DriftReport.has_drift` already encodes the same set, but T10
# also iterates per-category for stderr hint emission and needs an
# explicit ordering.
_DRIFT_FAILURE_CATEGORIES: tuple[str, ...] = (
    "notion_newer", "mirror_modified", "orphan", "missing_from_meta",
)

# Pad the category-name column to one space past the longest entry
# (``missing_from_meta`` = 17). Hard-coded so future relabel breaks
# the visual grid loudly.
_DRIFT_CATEGORY_COLUMN_WIDTH = 19


def _run_consistency_check():
    """Thin seam over :func:`boot.consistency.check`.

    Tests mock this single seam via
    ``patch.object(verify_module, "_run_consistency_check", ...)``
    rather than monkey-patching :mod:`boot.consistency` directly.
    Matches T9's ``_run_boot_sequence`` pattern.
    """
    from boot.consistency import check as _consistency_check

    return _consistency_check()


def _run_drift_check():
    """Thin seam over :func:`boot.bible_sync.check_drift`.

    Mirrors :func:`_run_consistency_check`. Per T6's contract,
    :func:`boot.bible_sync.check_drift` raises
    :class:`errors.BootBibleSyncError` on credentials_missing /
    mcp_connect_failed / page_deleted; T10 catches these in
    :func:`_verify_bible` and renders as a drift-section halt.
    """
    from boot.bible_sync import check_drift as _check_drift

    return _check_drift()


def _format_consistency_section(report) -> tuple[list[str], int]:
    """Render the consistency section. Returns ``(stdout_lines, rc)``.

    ``rc`` is ``0`` if ``report.ok``, ``1`` otherwise. Each
    :class:`boot.consistency.DriftRecord` is rendered with its
    ``enum_name``, ``drift_kind``, and short ``detail`` line so the
    operator can map back to the bible canonical that diverged.
    """
    lines: list[str] = ["Bible consistency (B3 — boot.consistency.check):"]
    if report.ok:
        lines.append(
            f"  ✓ all {report.enums_checked} enums consistent across "
            "bible sections + code mirrors"
        )
        return lines, 0

    lines.append(f"  ✗ {len(report.drifts)} drift(s) detected:")
    for drift in report.drifts:
        lines.append(
            f"    - {drift.enum_name} ({drift.drift_kind}) — {drift.detail}"
        )
    return lines, 1


def _format_drift_section(
    report_or_exc,
) -> tuple[list[str], list[str], int]:
    """Render the drift section. Returns ``(stdout_lines, stderr_lines, rc)``.

    ``report_or_exc`` is either a :class:`boot.bible_sync.DriftReport`
    (success path — drift may or may not be present) or a
    :class:`errors.BootBibleSyncError` (halt path — credentials_missing
    / mcp_connect_failed / page_deleted). The halt path reuses T9's
    :func:`_hint_for_halt` for the stderr hint so all
    ``BootBibleSyncError`` kinds share one canonical hint table.
    """
    stdout: list[str] = ["Bible drift (B2 — boot.bible_sync.check_drift):"]
    stderr: list[str] = []

    # Halt path — _run_drift_check raised BootBibleSyncError.
    if isinstance(report_or_exc, BaseException):
        exc = report_or_exc
        class_name = type(exc).__name__
        kind = getattr(exc, "kind", None)
        kind_render = f"(kind={kind})" if kind is not None else ""
        stdout.append(f"  ✗ check unavailable: {class_name}{kind_render}")
        stderr.append(f"BIBLE HALT [drift] {class_name}{kind_render}")
        reason = getattr(exc, "reason", str(exc))
        stderr.append(f"Reason: {reason}")
        stderr.append(f"Hint: {_hint_for_halt(exc)}")
        return stdout, stderr, 1

    # Success path — DriftReport with per-category counts.
    report = report_or_exc
    has_drift = report.has_drift
    for field_name, label in _DRIFT_CATEGORIES:
        items: tuple[str, ...] = getattr(report, field_name)
        is_drift_cat = field_name in _DRIFT_FAILURE_CATEGORIES
        mark = "✗" if (is_drift_cat and items) else "✓"
        label_col = label.ljust(_DRIFT_CATEGORY_COLUMN_WIDTH)
        if items and is_drift_cat:
            sample = ", ".join(items[:3])
            if len(items) > 3:
                sample += f", ... +{len(items) - 3} more"
            stdout.append(
                f"  {mark} {label_col}{len(items):>3} page(s): {sample}"
            )
        else:
            stdout.append(f"  {mark} {label_col}{len(items):>3} page(s)")

    if has_drift:
        for cat in _DRIFT_FAILURE_CATEGORIES:
            items = getattr(report, cat)
            if not items:
                continue
            stderr.append(f"BIBLE DRIFT {cat}: {len(items)} page(s)")
            stderr.append(f"Hint: {_BIBLE_DRIFT_HINTS[cat]}")
        return stdout, stderr, 1

    return stdout, [], 0


def _verify_bible() -> int:
    """Run the bible consistency + drift checks, render the operator report.

    Two subsections:

    * **Bible consistency** — local-only enum drift across bible sections
      + code mirrors (:func:`boot.consistency.check`, T5). Never raises.
    * **Bible drift** — local-vs-Notion comparison for each bible page
      (:func:`boot.bible_sync.check_drift`, T6). May raise
      :class:`errors.BootBibleSyncError` on
      credentials_missing / mcp_connect_failed / page_deleted; T10
      catches and renders as a section halt with stderr hint.

    Per T9's contract pattern: this function does NOT propagate any
    exception. The drift halt is caught internally and translated to
    a section ✗ + stderr block + section_rc=1. Total exit code is
    ``max(consistency_rc, drift_rc)``.

    Returns
    -------
    int
        ``0`` if both checks pass; ``1`` if either reports drift OR
        the drift check halted on a :class:`errors.BootBibleSyncError`.
        Exit code ``2`` is reserved for the outer
        :func:`cli.main.main` catch — non-CEE exceptions only.
    """
    print("CEE Bible Verification")
    print()

    # Section 1 — consistency (local-only; never raises).
    consistency_report = _run_consistency_check()
    consistency_lines, consistency_rc = _format_consistency_section(
        consistency_report
    )
    for line in consistency_lines:
        print(line)
    print()

    # Section 2 — drift (catches BootBibleSyncError internally).
    try:
        drift_outcome = _run_drift_check()
    except BootBibleSyncError as exc:
        drift_outcome = exc
    drift_stdout, drift_stderr, drift_rc = _format_drift_section(drift_outcome)
    for line in drift_stdout:
        print(line)
    print()

    # Summary line — describes both subsection outcomes in one sentence.
    consistency_phrase = (
        "bible consistent" if consistency_rc == 0 else
        f"{len(consistency_report.drifts)} consistency drift(s)"
    )
    if isinstance(drift_outcome, BaseException):
        drift_phrase = "drift check halted"
    elif drift_rc == 0:
        drift_phrase = "bible in sync"
    else:
        # DriftReport with at least one drift category populated.
        drift_count = sum(
            len(getattr(drift_outcome, cat))
            for cat in _DRIFT_FAILURE_CATEGORIES
        )
        drift_phrase = f"{drift_count} drift item(s) detected"
    print(f"Summary: {consistency_phrase}; {drift_phrase}.")

    total_rc = max(consistency_rc, drift_rc)
    if total_rc == 0:
        print("PASSED.")
        return 0

    # Failure stdout banner — discriminates which subsection(s) failed.
    if consistency_rc and drift_rc:
        print("FAILED: bible consistency check failed AND drift detected.")
    elif consistency_rc:
        print("FAILED: bible consistency check failed.")
    elif isinstance(drift_outcome, BaseException):
        print("FAILED: bible drift check did not complete.")
    else:
        print("FAILED: bible mirror has drift vs Notion.")

    # stderr halt + drift hints. Consistency drift gets its own line
    # using the existing _BOOT_HALT_HINTS table so BootConsistencyError's
    # remediation matches the one T9 emits when the same class halts
    # boot at B3.
    if consistency_rc:
        from errors import BootConsistencyError

        synthetic = BootConsistencyError(drifts=list(consistency_report.drifts))
        sys.stderr.write(
            f"BIBLE HALT [consistency] BootConsistencyError"
            f"({len(consistency_report.drifts)} drifts)\n"
        )
        sys.stderr.write(f"Hint: {_hint_for_halt(synthetic)}\n")
    for line in drift_stderr:
        sys.stderr.write(line + "\n")

    return 1


def cmd_verify(args: argparse.Namespace) -> int:
    """``cee verify`` dispatcher.

    Phase 1 shipped ``--layout`` and ``--schemas``; Phase 2 task 9
    added ``--boot``; Phase 2 task 10 adds ``--bible``. Future modes
    (``--security``) plug in here. Behaviour:

    * No flag → print usage hint to stderr, return ``2`` (matches
      argparse's malformed-invocation exit code).
    * One flag → run that mode, return its exit code.
    * Multiple flags → run each mode in declaration order
      (layout → schemas → boot → bible), return the worst exit code
      so a failure in any is surfaced.
    """
    if not (args.layout or args.schemas or args.boot or args.bible):
        print(
            "Specify a verify mode "
            "(e.g. --layout, --schemas, --boot, or --bible)",
            file=sys.stderr,
        )
        return 2

    exit_codes: list[int] = []
    if args.layout:
        exit_codes.append(_verify_layout())
    if args.schemas:
        exit_codes.append(_verify_schemas())
    if args.boot:
        exit_codes.append(_verify_boot())
    if args.bible:
        exit_codes.append(_verify_bible())
    return max(exit_codes)
