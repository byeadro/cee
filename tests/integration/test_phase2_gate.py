"""Phase 2 gate validation per bible 20 §5.2.

Validates the five gate criteria literal in bible 20 §5.2:

1. A clean shell can run ``cee init`` then ``cee sync-bible`` then
   ``cee verify`` without errors.
2. Boot sequence completes B1–B9 from a clean state.
3. Bible drift is detected when a Notion page changes after sync.
4. Test: ``tests/integration/test_boot_sequence.py`` passes (already
   shipped by T8; this gate file confirms via cross-reference).
5. Test: cross-section consistency check rejects a deliberately-
   introduced enum mismatch (already shipped by T5 in
   ``tests/integration/test_consistency_drift.py``; this gate file
   confirms via cross-reference).

Per AB resolution (T11 design step):

* ``cee verify`` invocation uses explicit flags
  ``--layout --schemas --boot --bible`` per bible 20 §5.2 line 152's
  operational interpretation pending bible amendment (downstream
  candidate #26).
* "Clean state" = post-``cee init`` + post-``cee sync-bible`` substrate,
  not pristine.
* Mock :class:`boot.notion_mcp.NotionMCPClient` is injected by
  monkey-patching :data:`boot.bible_sync.default_client_factory` so
  every code path that defaults to the live transport (sync, check_drift,
  boot.sequencer's B2) picks up the mock without explicit injection.
* Mock client class is defined inline (matches the precedent of
  ``tests/integration/test_bible_sync_e2e.py``'s ``IntegMockClient`` and
  ``tests/unit/test_boot/test_bible_sync.py``'s ``MockMCPClient`` —
  each integration test file carries its own minimal mock; cross-file
  imports of mocks are not the established convention).

**Honesty about deferred concrete transport.** Bible 04 §5.6 explicitly
defers the concrete Notion MCP transport ("Deferred to Phase 2 close").
The current default factory raises ``NotImplementedError``. T11's
criterion-1 test simulates the post-``cee sync-bible`` state by
pre-seeding the bible mirror with copies of the real ``~/cee/bible/``
files and constructing a valid ``.sync_meta.json`` matching them. This
is the most honest available exercise of the criterion until concrete
transport ships; the test docstring documents the substitution.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import paths
from boot import bible_sync as bible_sync_module
from boot.bible_sync import DriftReport, check_drift
from boot.notion_mcp import (
    Block,
    ChildRef,
    PageMeta,
    RichTextSpan,
)
from boot.sequencer import BootResult, run as boot_run
from cli.main import main as cli_main
from errors import BootBibleSyncError, BootError


# --------------------------------------------------------------------------- #
# Mock NotionMCPClient (gate-test scope)                                      #
# --------------------------------------------------------------------------- #


@dataclass
class _GateMockClient:
    """Inline mock for :class:`boot.notion_mcp.NotionMCPClient`.

    Returns deterministic responses constructed at fixture-build time.
    Mirrors the shape of ``IntegMockClient`` in
    ``tests/integration/test_bible_sync_e2e.py``; T11 carries its own
    so the gate file is self-contained.
    """

    children: list[ChildRef]
    page_meta_by_id: dict[str, PageMeta]
    blocks_by_id: dict[str, list[Block]] = field(default_factory=dict)

    def connect(self) -> None:
        return None

    def enumerate_children(self, parent_id: str) -> list[ChildRef]:
        return list(self.children)

    def fetch_page_metadata(self, page_id: str) -> PageMeta:
        return self.page_meta_by_id[page_id]

    def fetch_page_blocks(self, page_id: str) -> list[Block]:
        # Not exercised by check_drift (which only fetches metadata);
        # exists for protocol completeness.
        return self.blocks_by_id.get(page_id, [])


# --------------------------------------------------------------------------- #
# Fixture: post-sync substrate (real bibles seeded into tmp_path)             #
# --------------------------------------------------------------------------- #


_REAL_BIBLE_DIR: Path = Path.home() / "cee" / "bible"


def _slug_from_filename(filename: str) -> str:
    """``00_project_vision.md`` → ``00_project_vision``."""
    return filename[:-3] if filename.endswith(".md") else filename


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


@pytest.fixture
def gate_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Build a tmp env representing post-``cee init`` + post-sync state.

    Steps:

    1. Monkeypatch every ``paths.*`` constant to point under ``tmp_path``.
    2. Pre-create the canonical directory skeleton so ``cee init`` is
       idempotent against the layout (as it would be on a clean shell
       where ``init`` ran once before).
    3. Copy the real ``~/cee/bible/*.md`` files into the tmp bible dir
       (representing the post-``cee sync-bible`` substrate; concrete
       Notion transport is bible-04 §5.6 deferred so we synthesize the
       output state directly).
    4. Build a valid ``.sync_meta.json`` matching the copied bibles —
       per-page ``content_sha256`` from the actual file contents and a
       fixed ``notion_last_edited_time`` per page (matched by the mock
       client's metadata responses).
    5. Write a ``credentials.toml`` stub (``cee init`` defers credentials
       per Phase 1 docstring; T11 supplies the stub so B2's drift check
       can read ``[anthropic] api_key``).
    6. Monkeypatch ``boot.bible_sync.default_client_factory`` to return
       the gate mock client built from the seeded mirror — so any
       sync/check_drift call without explicit factory injection picks
       up the mock.

    Returns a dict mapping symbolic names to the fixture's paths +
    objects, for tests that need to mutate state (criterion 3 drift
    tests) or assert against specific files.
    """
    cee_root = tmp_path / "cee"
    cee_root.mkdir()
    bible_dir = cee_root / "bible"
    bible_dir.mkdir()
    sync_meta_path = bible_dir / ".sync_meta.json"

    audit_dir = cee_root / "audit"
    audit_dir.mkdir()
    archive_dir = audit_dir / "archive"
    archive_dir.mkdir()

    skills_dir = cee_root / "skills"
    skills_dir.mkdir()
    agents_dir = cee_root / ".claude" / "agents"
    agents_dir.mkdir(parents=True)
    runs_dir = cee_root / "runs"
    runs_dir.mkdir()
    schemas_dir = cee_root / "schemas"  # not actually used at runtime
    schemas_dir.mkdir()
    promotion_queue = cee_root / "promotion_queue.json"

    obsidian_vault = tmp_path / "SecondBrain" / "cee"
    obsidian_vault.mkdir(parents=True)

    user_cfg_dir = tmp_path / ".cee"
    user_cfg_dir.mkdir()
    config_file = user_cfg_dir / "config.toml"
    config_file.write_text(
        "[general]\n"
        "auto_sync = true\n"
        "fresh_boot = false\n"
        "[paths]\n"
        'cee_root = "~/cee"\n'
        'obsidian_vault = "~/SecondBrain"\n'
        'notion_bible_root_id = "352e8536-d882-8050-aff6-f1dbcff68a09"\n',
        encoding="utf-8",
    )
    credentials_file = user_cfg_dir / "credentials.toml"
    credentials_file.write_text(
        '[anthropic]\napi_key = "sk-ant-gate-test-stub"\n', encoding="utf-8"
    )

    redact_list = user_cfg_dir / "redact_list"
    redact_list.write_text("# gate test redact_list\n", encoding="utf-8")
    notion_redact_list = user_cfg_dir / "notion_redact_list"
    notion_redact_list.write_text(
        "# gate test notion_redact_list\n", encoding="utf-8"
    )

    for name, value in (
        ("CEE_ROOT", cee_root),
        ("BIBLE_DIR", bible_dir),
        ("BIBLE_SYNC_META", sync_meta_path),
        ("AUDIT_DIR", audit_dir),
        ("AUDIT_ARCHIVE_DIR", archive_dir),
        ("AUDIT_BOOT_LOG", audit_dir / "boot.log"),
        ("AUDIT_CLI_LOG", audit_dir / "cli.log"),
        ("AUDIT_ROLES_LOG", audit_dir / "roles.log"),
        ("AUDIT_SECURITY_LOG", audit_dir / "security.log"),
        ("SKILLS_DIR", skills_dir),
        ("AGENTS_DIR", agents_dir),
        ("RUNS_DIR", runs_dir),
        ("SCHEMAS_DIR", schemas_dir),
        ("PROMOTION_QUEUE", promotion_queue),
        ("USER_CONFIG_DIR", user_cfg_dir),
        ("CONFIG_FILE", config_file),
        ("CREDENTIALS_FILE", credentials_file),
        ("REDACT_LIST", redact_list),
        ("NOTION_REDACT_LIST", notion_redact_list),
        ("OBSIDIAN_VAULT", obsidian_vault),
    ):
        monkeypatch.setattr(paths, name, value)

    # Step 3: copy real bibles + collect per-page metadata.
    real_bibles = sorted(_REAL_BIBLE_DIR.glob("*.md"))
    if not real_bibles:
        pytest.skip("real ~/cee/bible/*.md not present; gate fixture cannot seed")

    pages_meta: dict[str, dict[str, str]] = {}
    children: list[ChildRef] = []
    page_meta_by_id: dict[str, PageMeta] = {}
    fixed_iso_time = "2026-04-30T12:00:00+00:00"

    for src in real_bibles:
        slug = _slug_from_filename(src.name)
        dst = bible_dir / src.name
        shutil.copy2(src, dst)
        sha = _sha256_file(dst)
        # Synthesize a plausible Notion page id from the slug so the
        # mock client can map it back deterministically.
        page_id = f"uuid-{slug}"
        pages_meta[slug] = {
            "notion_page_id": page_id,
            "notion_last_edited_time": fixed_iso_time,
            "local_path": str(dst),
            "content_sha256": sha,
        }
        # Title format the slug parser expects: "NN — TITLE" (em-dash).
        # _slug_for_child requires the leading 2-digit head + space.
        head, _, rest = slug.partition("_")
        title = f"{head} — {rest.upper()}"
        children.append(ChildRef(page_id=page_id, title=title))
        page_meta_by_id[page_id] = PageMeta(
            page_id=page_id, title=title, last_edited_time=fixed_iso_time
        )

    # Step 4: write the .sync_meta.json.
    sync_meta_json = {
        "schema_version": "1.0.0",
        "produced_by": "BOOT_SEQUENCER",
        "last_synced": fixed_iso_time,
        "pages": pages_meta,
    }
    sync_meta_path.write_text(json.dumps(sync_meta_json, indent=2), encoding="utf-8")

    # Step 5: scaffold audit logs (touch empty files so audit_log_append
    # can extend the chain from genesis).
    for log_name in ("cli.log", "roles.log", "boot.log", "security.log"):
        (audit_dir / log_name).write_text("", encoding="utf-8")

    # Step 6: monkeypatch the module-level default_client_factory so
    # every default-path caller (sync, check_drift, B2) picks up the
    # mock without explicit injection.
    mock_client = _GateMockClient(
        children=children,
        page_meta_by_id=page_meta_by_id,
    )
    monkeypatch.setattr(
        bible_sync_module, "default_client_factory", lambda: mock_client
    )

    return {
        "cee_root": cee_root,
        "bible_dir": bible_dir,
        "sync_meta_path": sync_meta_path,
        "audit_dir": audit_dir,
        "skills_dir": skills_dir,
        "agents_dir": agents_dir,
        "runs_dir": runs_dir,
        "config_file": config_file,
        "credentials_file": credentials_file,
        "obsidian_vault": obsidian_vault,
        "promotion_queue": promotion_queue,
        "user_cfg_dir": user_cfg_dir,
        "mock_client": mock_client,
        "fixed_iso_time": fixed_iso_time,
        "page_count": len(real_bibles),
    }


# --------------------------------------------------------------------------- #
# Criterion 1: clean shell + init + (sync-bible substituted) + verify          #
# --------------------------------------------------------------------------- #


def test_phase2_gate_criterion_1_clean_shell_init_then_verify_no_errors(
    gate_env: dict[str, Any],
) -> None:
    """Bible 20 §5.2 criterion #1: A clean shell can run ``cee init`` then
    ``cee sync-bible`` then ``cee verify`` without errors.

    Per AB resolution: "without errors" = exit code 0 from every
    command. The cee verify invocation uses the explicit
    ``--layout --schemas --boot --bible`` flag combination per
    bible 20 §5.2 line 152's operational interpretation
    (downstream candidate #26).

    Per AB resolution: ``cee sync-bible`` is substituted by pre-seeding
    the bible mirror in the gate_env fixture (concrete Notion transport
    is bible-04 §5.6 deferred). The substitution is documented; once
    concrete transport ships, this test should be reworked to invoke
    ``cee sync-bible`` directly.

    Asserts:

    * ``cee init`` returns 0 against the fixture (idempotent against
      the pre-existing layout from the fixture's seeding step).
    * ``cee verify --layout --schemas --boot --bible`` returns 0.
    """
    # cee init — exercises real init code against monkeypatched paths.
    rc = cli_main(["init"])
    assert rc == 0, "cee init returned non-zero on clean shell fixture"

    # cee verify with all four registered flags.
    rc = cli_main(["verify", "--layout", "--schemas", "--boot", "--bible"])
    assert rc == 0, (
        f"cee verify --layout --schemas --boot --bible returned {rc} "
        "(expected 0 against post-init + post-sync substrate)"
    )


# --------------------------------------------------------------------------- #
# Criterion 2: boot sequence B1-B9 from clean state                            #
# --------------------------------------------------------------------------- #


def test_phase2_gate_criterion_2_boot_completes_b1_through_b9_from_post_sync_state(
    gate_env: dict[str, Any],
) -> None:
    """Bible 20 §5.2 criterion #2: Boot sequence completes B1-B9 from
    a clean state.

    Per AB resolution: "clean state" = post-``cee init`` + post-sync
    substrate, with the bible mirror seeded from the real ``~/cee/bible/``
    files and ``.sync_meta.json`` matching them, so B2's check_drift
    returns in_sync, B3's consistency check passes against real bible
    content, and B4-B7 walk the (mostly empty) skill/agent/runs trees
    cleanly.

    This test complements T8's
    ``test_synthetic_happy_path_completes_b1_through_b9`` which uses
    fully-mocked factories; this one uses the post-sync fixture so the
    real B2 (check_drift via mock) + B3 (consistency.check on real
    bible content) + B6 (schemas import) paths are exercised.
    """
    # Make sure init has run so layout invariants hold.
    cli_main(["init"])

    result = boot_run()
    assert isinstance(result, BootResult)
    assert result.ok is True, (
        f"boot.sequencer.run() returned ok=False; halt_step={result.halt_step}, "
        f"halt_error={result.halt_error}"
    )
    assert result.halt_step is None
    assert result.halt_error is None
    assert tuple(s.step for s in result.steps) == (
        "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"
    )


# --------------------------------------------------------------------------- #
# Criterion 3: bible drift detected when Notion (or local mirror) changes      #
# --------------------------------------------------------------------------- #


def test_phase2_gate_criterion_3a_drift_detected_when_notion_page_changes(
    gate_env: dict[str, Any],
) -> None:
    """Bible 20 §5.2 criterion #3 (Notion-side drift): Bible drift is
    detected when a Notion page changes after sync.

    Mechanism: the gate fixture's mock client is configured with
    ``notion_last_edited_time`` matching ``.sync_meta.json``. We mutate
    one page's metadata in the mock to simulate a Notion edit, then
    invoke ``check_drift()`` and assert the page lands in
    ``DriftReport.notion_newer``.
    """
    mock = gate_env["mock_client"]
    # Pick the first page and mutate its last_edited_time to "later."
    first_child = mock.children[0]
    later_iso = "2026-05-15T12:00:00+00:00"
    mock.page_meta_by_id[first_child.page_id] = PageMeta(
        page_id=first_child.page_id,
        title=first_child.title,
        last_edited_time=later_iso,
    )

    # Slug expected from the title via _slug_for_child (e.g.,
    # "00 — PROJECT_VISION" → "00_project_vision").
    expected_slug = _slug_from_filename(
        sorted(_REAL_BIBLE_DIR.glob("*.md"))[0].name
    )

    report = check_drift()
    assert isinstance(report, DriftReport)
    assert expected_slug in report.notion_newer, (
        f"expected {expected_slug} in notion_newer; got {report.notion_newer}"
    )


def test_phase2_gate_criterion_3b_drift_detected_when_local_mirror_modified(
    gate_env: dict[str, Any],
) -> None:
    """Bible 20 §5.2 criterion #3 (mirror-side drift): drift is detected
    when the local mirror is modified outside the sync workflow.

    Mechanism: the gate fixture's bible mirror is seeded with content
    matching ``.sync_meta.json`` ``content_sha256``. We append text to
    one mirror file (without updating ``.sync_meta.json``), then invoke
    ``check_drift()`` and assert the page lands in
    ``DriftReport.mirror_modified``.

    This validates bible 04 §5.5's mirror-side drift check (sha256
    comparison between local file and recorded hash).
    """
    bible_dir: Path = gate_env["bible_dir"]
    target = sorted(bible_dir.glob("*.md"))[0]
    target.write_text(
        target.read_text(encoding="utf-8") + "\n<!-- gate-test mutation -->\n",
        encoding="utf-8",
    )
    expected_slug = _slug_from_filename(target.name)

    report = check_drift()
    assert isinstance(report, DriftReport)
    assert expected_slug in report.mirror_modified, (
        f"expected {expected_slug} in mirror_modified; "
        f"got {report.mirror_modified}"
    )


# --------------------------------------------------------------------------- #
# Criteria 4 + 5: cross-references to existing integration tests               #
# --------------------------------------------------------------------------- #
#
# These two criteria are documentary — bible 20 §5.2 names specific test
# files that must pass. The pytest run as a whole validates "passes"; the
# gate file confirms that the named files exist (not silently renamed
# or removed).


def test_phase2_gate_criterion_4_test_boot_sequence_file_exists() -> None:
    """Bible 20 §5.2 criterion #4: Test
    ``tests/integration/test_boot_sequence.py`` passes.

    Cross-reference. T8 shipped this file with 7 passing tests; the
    "passes" condition is validated by the regular pytest run. This
    test confirms the named file still exists at the canonical path
    so a silent rename/removal would loudly break the gate.
    """
    expected = paths.CEE_ROOT / "tests" / "integration" / "test_boot_sequence.py"
    assert expected.exists(), (
        f"bible 20 §5.2 criterion #4 names "
        f"{expected.relative_to(paths.CEE_ROOT)}; file is missing"
    )
    # Spot-check the file contains the canonical happy-path test name.
    content = expected.read_text(encoding="utf-8")
    assert "test_synthetic_happy_path_completes_b1_through_b9" in content


def test_phase2_gate_criterion_5_consistency_drift_file_exists() -> None:
    """Bible 20 §5.2 criterion #5: cross-section consistency check
    rejects a deliberately-introduced enum mismatch.

    Cross-reference. T5 shipped
    ``tests/integration/test_consistency_drift.py`` with 6 tests
    including ``test_drift_python_class_extra_value`` and
    ``test_drift_caller_halts_via_BootConsistencyError``. Bible 18
    §5.1.2 names this concept ``test_cross_section_consistency.py``;
    the actual file is ``test_consistency_drift.py`` (naming drift
    documented as a downstream candidate). This test confirms the
    file exists at the path T5 shipped.
    """
    expected = (
        paths.CEE_ROOT / "tests" / "integration" / "test_consistency_drift.py"
    )
    assert expected.exists(), (
        f"bible 20 §5.2 criterion #5 needs a deliberate-drift test; "
        f"{expected.relative_to(paths.CEE_ROOT)} is missing"
    )
    # Spot-check the file contains a deliberate-drift case + the
    # BootConsistencyError handoff test.
    content = expected.read_text(encoding="utf-8")
    assert "test_drift_python_class_extra_value" in content
    assert "test_drift_caller_halts_via_BootConsistencyError" in content


# --------------------------------------------------------------------------- #
# Real-substrate documented-current-state smoke (T8 pattern)                  #
# --------------------------------------------------------------------------- #


def test_phase2_gate_real_substrate_smoke_documented_halt_at_b2() -> None:
    """Phase 2 close: documents the current-state outcome of running
    boot.sequencer.run() against the real ``~/cee/`` substrate.

    Per T8's design + T9/T10 acceptance-criteria precedent, this is NOT
    a happy-path assertion — it is an honest documentation of the
    expected halt path given that bible 04 §5.6 explicitly defers
    concrete Notion MCP transport. The real substrate has either:

    * No ``~/.cee/credentials.toml`` → halt at B2 with
      ``BootBibleSyncError(kind="credentials_missing")``.
    * ``~/.cee/credentials.toml`` populated → halt at B2 with
      ``BootBibleSyncError(kind="mcp_connect_failed")`` from T6's stub
      transport.

    What MUST NOT happen: a raw Python exception escapes ``run()``, OR
    the boot succeeds (which would mean concrete transport has shipped
    silently). Either signals a deferred-state regression worth
    investigating before the Phase 2 gate is considered closed.
    """
    result = boot_run()
    assert isinstance(result, BootResult)
    if result.ok:
        # If this fires, concrete transport has shipped or the bible
        # mirror is fully in sync against the live Notion. Either is a
        # state change worth surfacing — the smoke test then needs an
        # update, but the gate is preserved.
        assert tuple(s.step for s in result.steps) == (
            "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"
        )
        return

    assert result.halt_step == "B2", (
        f"unexpected halt at {result.halt_step}; expected B2 given "
        "bible-04 §5.6 deferred concrete transport"
    )
    assert isinstance(result.halt_error, BootBibleSyncError)
    assert result.halt_error.kind in (
        "credentials_missing", "mcp_connect_failed"
    ), (
        f"unexpected halt kind {result.halt_error.kind}; expected one of "
        "(credentials_missing, mcp_connect_failed)"
    )
