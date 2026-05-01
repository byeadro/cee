"""``cee init`` — first-run scaffolder for a CEE installation.

Path B scope (Phase 1 task 13). This is the **first composition task**:
it wires together the foundation primitives shipped in tasks 9–12
(:mod:`paths`, :mod:`config_loader`, :func:`persistence.scaffold_obsidian`,
:func:`persistence.scaffold_audit_logs`, :func:`persistence.audit_log_append`)
into a single OPERATOR-runnable command.

Phase 6+ deferrals (not in scope here):

* CLAUDE.md generation per bible 14 §5.1 — needs the bible-mirror reader
  and skill/agent registry walkers.
* Slash command installation per bible 14 §5.3.
* Hook installation per bible 14 §5.4.
* ``credentials.toml`` per bible 04 §5.2 — Phase 2.

Bible mapping:

* **04 §5.2** — the ``~/.cee/`` user-config layout (``config.toml``,
  ``redact_list``, ``credentials.toml``).
* **12 §5.3** — references the additional ``notion_redact_list`` file
  that bible 04 §5.2 omits. OPERATOR-resolved Path B: include all four
  files conceptually but defer ``credentials.toml`` to Phase 2.
* **13 §EC1** — ``cee init`` materialises the Obsidian vault scaffold.
* **12 §5.8** — first ``boot.log`` entry uses the genesis hash chain.
* **19** + **00 §12 B0** — boot-step taxonomy. ``cee init`` is the
  ``BOOT_SEQUENCER``'s first action.

Idempotency: every step uses an idempotent helper. The OPERATOR can run
``cee init`` repeatedly (e.g. after installing on a new machine) without
losing manual edits to ``redact_list``, ``config.toml``, or any vault
file. Each invocation appends one new entry to ``boot.log``, advancing
the hash chain — the audit log is the only state that grows monotonically.
"""

from __future__ import annotations

import argparse

import paths
from config_loader.loader import load_config
from persistence.atomic import atomic_write_text
from persistence.audit import audit_log_append, scaffold_audit_logs
from persistence.obsidian import scaffold_obsidian


# Bible 12 §5.3 documents the file format. The header here is a learning
# aid — the redactor parses lines, ignoring blanks and ``#`` comments.
_REDACT_LIST_TEMPLATE = """\
# CEE redact_list — one pattern per line. Plain entries match exactly.
# Lines starting with `regex:` are interpreted as Python regex patterns.
# Lines starting with `#` are comments. Empty lines ignored.
"""

_NOTION_REDACT_LIST_TEMPLATE = """\
# CEE notion_redact_list — Notion-stricter redactions.
# Same format as redact_list. Patterns here are applied IN ADDITION to
# the main redact_list when writing to Notion.
"""


def cmd_init(args: argparse.Namespace) -> int:  # noqa: ARG001 — argparse contract
    """Run ``cee init``.

    Steps (idempotent — each helper handles the "already exists" case):

    1. Ensure ``~/.cee/`` exists.
    2. Delegate to :func:`config_loader.loader.load_config` for
       ``config.toml`` (creates from template if missing per bible 04
       §10.7).
    3. Create ``redact_list`` (with header comment) if missing.
    4. Create ``notion_redact_list`` (with header comment) if missing.
    5. :func:`persistence.scaffold_obsidian` — vault scaffold per
       bible 13 §5.1.
    6. :func:`persistence.scaffold_audit_logs` — four log files per
       bible 12 §5.8.
    7. Append the first ``boot.log`` entry (event ``cee_init_complete``,
       actor ``BOOT_SEQUENCER``).
    8. Print a multi-line summary to stdout.

    Returns
    -------
    int
        ``0`` on success. Errors propagate to :func:`cli.main.main`,
        which maps :class:`errors.BootError` to exit code ``1`` and any
        other exception to ``2``.
    """
    # Step 1: ~/.cee/
    paths.ensure_dir(paths.USER_CONFIG_DIR)

    # Step 2: config.toml — load_config creates it from the template if
    # missing (bible 04 §10.7). We probe existence beforehand so the
    # summary can report "created" vs "already exists" without parsing
    # load_config's behaviour.
    config_existed = paths.CONFIG_FILE.exists()
    load_config()  # side effect: copy template if missing
    config_status = "already exists" if config_existed else "created"

    # Step 3: redact_list
    redact_existed = paths.REDACT_LIST.exists()
    if not redact_existed:
        atomic_write_text(paths.REDACT_LIST, _REDACT_LIST_TEMPLATE)
    redact_status = "already exists" if redact_existed else "created"

    # Step 4: notion_redact_list
    notion_redact_existed = paths.NOTION_REDACT_LIST.exists()
    if not notion_redact_existed:
        atomic_write_text(
            paths.NOTION_REDACT_LIST, _NOTION_REDACT_LIST_TEMPLATE
        )
    notion_redact_status = (
        "already exists" if notion_redact_existed else "created"
    )

    # Step 5: Obsidian vault scaffold (bible 13 §5.1)
    obsidian_counts = scaffold_obsidian()

    # Step 6: Audit logs (bible 12 §5.8)
    audit_counts = scaffold_audit_logs()

    # Step 7: First boot.log entry. The actor is BOOT_SEQUENCER per
    # bible 02's role taxonomy + bible 19's boot pipeline. Run ID is
    # None — `cee init` is not a Run, it's a setup verb.
    audit_log_append(
        paths.AUDIT_BOOT_LOG,
        actor="BOOT_SEQUENCER",
        event="cee_init_complete",
        details={
            "config_toml": config_status,
            "redact_list": redact_status,
            "notion_redact_list": notion_redact_status,
            "obsidian_directories_created": obsidian_counts[
                "directories_created"
            ],
            "obsidian_files_created": obsidian_counts["files_created"],
            "audit_files_created": audit_counts["files_created"],
        },
    )

    # Step 8: Summary to stdout.
    print("CEE initialized successfully.\n")
    print("User config (~/.cee/):")
    print(f"  config.toml          [{config_status}]")
    print(f"  redact_list          [{redact_status}]")
    print(f"  notion_redact_list   [{notion_redact_status}]\n")
    print(f"Obsidian vault ({paths.OBSIDIAN_VAULT}):")
    print(
        f"  directories created: {obsidian_counts['directories_created']}"
    )
    print(f"  files created: {obsidian_counts['files_created']}\n")
    print(f"Audit logs ({paths.AUDIT_DIR}):")
    print(f"  log files created: {audit_counts['files_created']}\n")
    print("First boot.log entry written.")

    return 0
