"""``cee verify --layout`` — canonical-paths drift detection.

Phase 1 task 14. Walks the canonical paths declared in :mod:`paths` and
reports any required directory or file that's missing. Existence checks
only — permission checks (chmod 600 on ``raw_input.json``, etc.) are
deferred to Phase 5+ when the security writer ships and the audit
``cee verify --security`` mode is added.

Bible mapping:

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

The 23-path canonical set:

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

Future ``cee verify`` modes (out of scope for task 14):

* ``--schemas`` — validate every JSON schema file (task 15).
* ``--bible`` — check the bible mirror against Notion (Phase 2).
* ``--security`` — permission checks on ``raw_input.json`` etc.
  (Phase 5+).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import paths


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


def cmd_verify(args: argparse.Namespace) -> int:
    """``cee verify`` dispatcher.

    Phase 1 ships only ``--layout``. Future modes (``--schemas``,
    ``--bible``, ``--security``) plug in here. With no flag, the
    command prints a usage hint to stderr and returns ``2`` — the
    same exit code argparse uses for a malformed invocation.
    """
    if args.layout:
        return _verify_layout()
    print("Specify a verify mode (e.g. --layout)", file=sys.stderr)
    return 2
