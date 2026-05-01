"""Unit tests for ``boot.bible_sync`` — orchestration via mocked Protocol.

Per T6's Step 3 design (Path A1.5): tests inject a ``MockMCPClient``
implementing :class:`boot.notion_mcp.NotionMCPClient` so the
orchestration layer can be exercised end-to-end without a live
Anthropic / Notion MCP transport. No ``tests/fixtures/notion/``
directory is created by T6; that ships with concrete transport.

Test classes covered:

* Frozen dataclass invariants (SyncResult, DriftReport).
* Slug derivation (``00 — PROJECT VISION`` → ``00_project_vision``).
* Per-block-type rendering for the 10 supported types.
* sync() happy paths (cli_manual, boot_auto, skip-when-unchanged).
* sync() failure paths (initial connect, mid-sync per-page, EC9,
  missing credentials).
* check_drift() against in-sync, notion-newer, mirror-modified,
  orphan, missing-from-meta.
* Audit emission lands in the correct log per trigger.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, field
from pathlib import Path
from typing import Any

import pytest

import paths
from boot import bible_sync
from boot.bible_sync import (
    DriftReport,
    SyncResult,
    _blocks_to_markdown,
    _slug_for_child,
    check_drift,
    sync,
)
from boot.notion_mcp import (
    Block,
    ChildRef,
    NotionMCPClient,
    PageMeta,
    RichTextSpan,
)
from errors import BootBibleSyncError


# --------------------------------------------------------------------------- #
# Mock MCP client                                                             #
# --------------------------------------------------------------------------- #


@dataclass
class MockMCPClient:
    """Test double implementing :class:`NotionMCPClient`.

    Fields configure per-method behavior:

    * ``connect_raises`` — exception (or None) raised by ``connect()``.
    * ``children`` — what ``enumerate_children`` returns.
    * ``page_meta_by_id`` — id → PageMeta map for ``fetch_page_metadata``.
    * ``blocks_by_id`` — id → Block list map for ``fetch_page_blocks``.
    * ``page_meta_raise_for_ids`` / ``blocks_raise_for_ids`` — sets of
      page_ids whose corresponding fetch raises ``RuntimeError``.

    Captured call counts on each method allow assertions about how
    many calls happened (e.g. skip-when-unchanged shouldn't call
    fetch_page_blocks).
    """

    connect_raises: BaseException | None = None
    children: list[ChildRef] = field(default_factory=list)
    page_meta_by_id: dict[str, PageMeta] = field(default_factory=dict)
    blocks_by_id: dict[str, list[Block]] = field(default_factory=dict)
    page_meta_raise_for_ids: set[str] = field(default_factory=set)
    blocks_raise_for_ids: set[str] = field(default_factory=set)

    connect_calls: int = 0
    enumerate_calls: int = 0
    page_meta_calls: int = 0
    page_blocks_calls: int = 0

    def connect(self) -> None:
        self.connect_calls += 1
        if self.connect_raises is not None:
            raise self.connect_raises

    def enumerate_children(self, parent_id: str) -> list[ChildRef]:
        self.enumerate_calls += 1
        return list(self.children)

    def fetch_page_metadata(self, page_id: str) -> PageMeta:
        self.page_meta_calls += 1
        if page_id in self.page_meta_raise_for_ids:
            raise RuntimeError(f"synthetic metadata fetch failure for {page_id}")
        return self.page_meta_by_id[page_id]

    def fetch_page_blocks(self, page_id: str) -> list[Block]:
        self.page_blocks_calls += 1
        if page_id in self.blocks_raise_for_ids:
            raise RuntimeError(f"synthetic blocks fetch failure for {page_id}")
        return self.blocks_by_id.get(page_id, [])


# --------------------------------------------------------------------------- #
# Fixtures: tmp env that redirects paths                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture
def tmp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Build a tmp environment that redirects paths.* targets.

    Every Phase 1 path constant T6 reads/writes is repointed under
    ``tmp_path``. The ``credentials.toml`` and ``config.toml`` files
    are pre-populated with valid Phase 2 contents so sync() doesn't
    halt on credentials_missing in the happy-path tests.
    """
    bible_dir = tmp_path / "cee" / "bible"
    bible_dir.mkdir(parents=True)
    sync_meta = bible_dir / ".sync_meta.json"

    audit_dir = tmp_path / "cee" / "audit"
    audit_dir.mkdir(parents=True)
    cli_log = audit_dir / "cli.log"
    boot_log = audit_dir / "boot.log"
    roles_log = audit_dir / "roles.log"

    user_cfg_dir = tmp_path / ".cee"
    user_cfg_dir.mkdir(parents=True)
    creds_file = user_cfg_dir / "credentials.toml"
    creds_file.write_text(
        '[anthropic]\napi_key = "sk-ant-test-key"\n', encoding="utf-8"
    )
    config_file = user_cfg_dir / "config.toml"
    config_file.write_text(
        '[paths]\nnotion_bible_root_id = "352e8536-d882-8050-aff6-f1dbcff68a09"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(paths, "BIBLE_DIR", bible_dir)
    monkeypatch.setattr(paths, "BIBLE_SYNC_META", sync_meta)
    monkeypatch.setattr(paths, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(paths, "AUDIT_CLI_LOG", cli_log)
    monkeypatch.setattr(paths, "AUDIT_BOOT_LOG", boot_log)
    monkeypatch.setattr(paths, "AUDIT_ROLES_LOG", roles_log)
    monkeypatch.setattr(paths, "USER_CONFIG_DIR", user_cfg_dir)
    monkeypatch.setattr(paths, "CONFIG_FILE", config_file)
    monkeypatch.setattr(paths, "CREDENTIALS_FILE", creds_file)

    return {
        "bible_dir": bible_dir,
        "sync_meta": sync_meta,
        "cli_log": cli_log,
        "boot_log": boot_log,
        "roles_log": roles_log,
        "creds_file": creds_file,
        "config_file": config_file,
    }


def _audit_lines(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    return [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# --------------------------------------------------------------------------- #
# Frozen dataclass invariants                                                 #
# --------------------------------------------------------------------------- #


def test_sync_result_is_frozen() -> None:
    r = SyncResult(
        ok=True,
        trigger="cli_manual",
        synced=(),
        skipped=(),
        failed=(),
        duration_ms=0,
    )
    with pytest.raises(FrozenInstanceError):
        r.ok = False  # type: ignore[misc]


def test_drift_report_is_frozen() -> None:
    r = DriftReport(
        in_sync=(), notion_newer=(), mirror_modified=(), orphan=(), missing_from_meta=()
    )
    with pytest.raises(FrozenInstanceError):
        r.in_sync = ("x",)  # type: ignore[misc]


def test_drift_report_has_drift_property() -> None:
    no_drift = DriftReport(
        in_sync=("00_x",),
        notion_newer=(),
        mirror_modified=(),
        orphan=(),
        missing_from_meta=(),
    )
    assert no_drift.has_drift is False
    with_drift = DriftReport(
        in_sync=(),
        notion_newer=("00_x",),
        mirror_modified=(),
        orphan=(),
        missing_from_meta=(),
    )
    assert with_drift.has_drift is True


# --------------------------------------------------------------------------- #
# Slug derivation                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "title,expected",
    [
        ("00 — PROJECT VISION", "00_project_vision"),
        ("01 — REAL PROBLEM BREAKDOWN", "01_real_problem_breakdown"),
        ("19 — ERROR HANDLING + FAILURE STATES", "19_error_handling_failure_states"),
        ("22 — MASTER SYSTEM BUILD PROMPT", "22_master_system_build_prompt"),
    ],
)
def test_slug_for_child_canonical_titles(title: str, expected: str) -> None:
    slug = _slug_for_child(ChildRef(page_id="x", title=title))
    assert slug == expected


@pytest.mark.parametrize(
    "title",
    ["", "no leading number", "X — bad prefix", " "],
)
def test_slug_for_child_rejects_malformed(title: str) -> None:
    assert _slug_for_child(ChildRef(page_id="x", title=title)) == ""


# --------------------------------------------------------------------------- #
# Per-block-type rendering                                                    #
# --------------------------------------------------------------------------- #


def test_render_heading_1() -> None:
    out = _blocks_to_markdown([
        Block(type="heading_1", rich_text=(RichTextSpan(text="00 — PROJECT VISION"),))
    ])
    assert out == "# 00 — PROJECT VISION\n"


def test_render_heading_2_and_3() -> None:
    out = _blocks_to_markdown([
        Block(type="heading_2", rich_text=(RichTextSpan(text="1. What This Is"),)),
        Block(type="heading_3", rich_text=(RichTextSpan(text="5.1 The closed enum"),)),
    ])
    assert "## 1. What This Is" in out
    assert "### 5.1 The closed enum" in out


def test_render_paragraph_with_inline_annotations() -> None:
    out = _blocks_to_markdown([
        Block(
            type="paragraph",
            rich_text=(
                RichTextSpan(text="A "),
                RichTextSpan(text="bold", bold=True),
                RichTextSpan(text=" word and "),
                RichTextSpan(text="code", code=True),
                RichTextSpan(text="."),
            ),
        )
    ])
    assert "A **bold** word and `code`." in out


def test_render_bulleted_list_with_nested_children() -> None:
    out = _blocks_to_markdown([
        Block(
            type="bulleted_list_item",
            rich_text=(RichTextSpan(text="parent"),),
            children=(
                Block(
                    type="bulleted_list_item",
                    rich_text=(RichTextSpan(text="child"),),
                ),
            ),
        )
    ])
    assert "- parent" in out
    assert "  - child" in out


def test_render_numbered_list() -> None:
    out = _blocks_to_markdown([
        Block(type="numbered_list_item", rich_text=(RichTextSpan(text="first"),)),
        Block(type="numbered_list_item", rich_text=(RichTextSpan(text="second"),)),
    ])
    assert "1. first" in out
    assert "1. second" in out


def test_render_code_block() -> None:
    out = _blocks_to_markdown([
        Block(
            type="code",
            code_language="python",
            rich_text=(RichTextSpan(text="x = 1\nprint(x)"),),
        )
    ])
    assert "```python\nx = 1\nprint(x)\n```" in out


def test_render_divider() -> None:
    out = _blocks_to_markdown([Block(type="divider")])
    assert out.strip() == "---"


def test_render_quote() -> None:
    out = _blocks_to_markdown([
        Block(type="quote", rich_text=(RichTextSpan(text="purpose: ..."),))
    ])
    assert "> purpose: ..." in out


def test_render_table() -> None:
    out = _blocks_to_markdown([
        Block(
            type="table",
            children=(
                Block(
                    type="table_row",
                    cells=(
                        (RichTextSpan(text="Header 1"),),
                        (RichTextSpan(text="Header 2"),),
                    ),
                ),
                Block(
                    type="table_row",
                    cells=(
                        (RichTextSpan(text="cell A"),),
                        (RichTextSpan(text="cell B"),),
                    ),
                ),
            ),
        )
    ])
    assert '<table header-row="true">' in out
    assert "<tr><td>Header 1</td><td>Header 2</td></tr>" in out
    assert "<tr><td>cell A</td><td>cell B</td></tr>" in out
    assert "</table>" in out


def test_render_combined_tree() -> None:
    """A small synthetic tree exercising heading + paragraph + list +
    code + divider in one render — verifies the multi-block joiner."""
    out = _blocks_to_markdown([
        Block(type="heading_2", rich_text=(RichTextSpan(text="Section"),)),
        Block(type="paragraph", rich_text=(RichTextSpan(text="Intro."),)),
        Block(type="bulleted_list_item", rich_text=(RichTextSpan(text="point"),)),
        Block(type="code", code_language="bash", rich_text=(RichTextSpan(text="ls -la"),)),
        Block(type="divider"),
    ])
    assert out.startswith("## Section\n\n")
    assert "\n\nIntro.\n\n" in out
    assert "\n\n- point\n\n" in out
    assert "\n\n```bash\nls -la\n```\n\n---\n" in out
    assert out.endswith("\n")


# --------------------------------------------------------------------------- #
# sync() happy paths                                                          #
# --------------------------------------------------------------------------- #


def _build_minimal_pages(
    children: list[ChildRef],
    blocks_per_id: dict[str, list[Block]] | None = None,
    last_edited: str = "2026-05-01T00:00:00+00:00",
) -> tuple[dict[str, PageMeta], dict[str, list[Block]]]:
    metas = {
        c.page_id: PageMeta(
            page_id=c.page_id, title=c.title, last_edited_time=last_edited
        )
        for c in children
    }
    blocks = blocks_per_id or {
        c.page_id: [
            Block(type="heading_1", rich_text=(RichTextSpan(text=c.title),)),
            Block(type="paragraph", rich_text=(RichTextSpan(text="body"),)),
        ]
        for c in children
    }
    return metas, blocks


def test_sync_cli_manual_happy_path(tmp_env: dict[str, Path]) -> None:
    children = [
        ChildRef(page_id="page-uuid-00", title="00 — PROJECT VISION"),
        ChildRef(page_id="page-uuid-01", title="01 — REAL PROBLEM BREAKDOWN"),
    ]
    metas, blocks = _build_minimal_pages(children)
    client = MockMCPClient(
        children=children,
        page_meta_by_id=metas,
        blocks_by_id=blocks,
    )
    result = sync(trigger="cli_manual", client_factory=lambda: client)

    assert result.ok is True
    assert result.trigger == "cli_manual"
    assert set(result.synced) == {"00_project_vision", "01_real_problem_breakdown"}
    assert result.failed == ()

    # Bible files written
    bd = tmp_env["bible_dir"]
    assert (bd / "00_project_vision.md").exists()
    assert (bd / "01_real_problem_breakdown.md").exists()

    # Sync meta written + valid SyncMeta shape
    meta_raw = json.loads(tmp_env["sync_meta"].read_text(encoding="utf-8"))
    assert meta_raw["produced_by"] == "BOOT_SEQUENCER"
    assert set(meta_raw["pages"].keys()) == {
        "00_project_vision",
        "01_real_problem_breakdown",
    }


def test_sync_cli_manual_emits_cli_invoke(tmp_env: dict[str, Path]) -> None:
    children = [ChildRef(page_id="page-uuid-00", title="00 — PROJECT VISION")]
    metas, blocks = _build_minimal_pages(children)
    sync(
        trigger="cli_manual",
        client_factory=lambda: MockMCPClient(
            children=children, page_meta_by_id=metas, blocks_by_id=blocks
        ),
    )
    cli = _audit_lines(tmp_env["cli_log"])
    assert any(e["event"] == "cli_invoke" for e in cli)
    boot = _audit_lines(tmp_env["boot_log"])
    assert all(e["event"] != "b2_drift_detected" for e in boot)


def test_sync_boot_auto_emits_b2_drift_detected(tmp_env: dict[str, Path]) -> None:
    children = [ChildRef(page_id="page-uuid-00", title="00 — PROJECT VISION")]
    metas, blocks = _build_minimal_pages(children)
    sync(
        trigger="boot_auto",
        client_factory=lambda: MockMCPClient(
            children=children, page_meta_by_id=metas, blocks_by_id=blocks
        ),
    )
    boot = _audit_lines(tmp_env["boot_log"])
    assert any(e["event"] == "b2_drift_detected" for e in boot)
    cli = _audit_lines(tmp_env["cli_log"])
    assert all(e["event"] != "cli_invoke" for e in cli)


def test_sync_emits_per_page_synced_audit(tmp_env: dict[str, Path]) -> None:
    children = [
        ChildRef(page_id="page-uuid-00", title="00 — PROJECT VISION"),
        ChildRef(page_id="page-uuid-01", title="01 — REAL PROBLEM BREAKDOWN"),
    ]
    metas, blocks = _build_minimal_pages(children)
    sync(
        trigger="cli_manual",
        client_factory=lambda: MockMCPClient(
            children=children, page_meta_by_id=metas, blocks_by_id=blocks
        ),
    )
    roles = _audit_lines(tmp_env["roles_log"])
    synced_events = [e for e in roles if e["event"] == "sync_bible_page_synced"]
    assert len(synced_events) == 2
    assert all("content_sha256" in e["details"] for e in synced_events)
    assert all("notion_last_edited_time" in e["details"] for e in synced_events)


def test_sync_emits_start_and_end_audit(tmp_env: dict[str, Path]) -> None:
    children = [ChildRef(page_id="page-uuid-00", title="00 — PROJECT VISION")]
    metas, blocks = _build_minimal_pages(children)
    sync(
        trigger="cli_manual",
        client_factory=lambda: MockMCPClient(
            children=children, page_meta_by_id=metas, blocks_by_id=blocks
        ),
    )
    roles = _audit_lines(tmp_env["roles_log"])
    starts = [e for e in roles if e["event"] == "sync_bible_start"]
    ends = [e for e in roles if e["event"] == "sync_bible_end"]
    assert len(starts) == 1
    assert len(ends) == 1
    assert starts[0]["details"]["page_count_expected"] == 1
    assert ends[0]["details"]["synced_count"] == 1
    assert ends[0]["details"]["failed_count"] == 0


def test_sync_skip_when_unchanged(tmp_env: dict[str, Path]) -> None:
    """Page already in .sync_meta with matching last_edited_time skips
    block fetch entirely."""
    children = [ChildRef(page_id="page-uuid-00", title="00 — PROJECT VISION")]
    metas = {
        "page-uuid-00": PageMeta(
            page_id="page-uuid-00",
            title="00 — PROJECT VISION",
            last_edited_time="2026-05-01T00:00:00+00:00",
        )
    }
    blocks: dict[str, list[Block]] = {}  # nothing — would raise on call

    # Pre-seed sync_meta.json with matching state
    seed = {
        "schema_version": "1.0.0",
        "produced_by": "BOOT_SEQUENCER",
        "last_synced": "2026-04-01T00:00:00+00:00",
        "pages": {
            "00_project_vision": {
                "notion_page_id": "page-uuid-00",
                "notion_last_edited_time": "2026-05-01T00:00:00+00:00",
                "local_path": str(tmp_env["bible_dir"] / "00_project_vision.md"),
                "content_sha256": "0" * 64,
            }
        },
    }
    tmp_env["sync_meta"].write_text(json.dumps(seed), encoding="utf-8")

    client = MockMCPClient(
        children=children,
        page_meta_by_id=metas,
        blocks_by_id=blocks,
    )
    result = sync(trigger="cli_manual", client_factory=lambda: client)
    assert result.synced == ()
    assert result.skipped == ("00_project_vision",)
    assert client.page_blocks_calls == 0  # short-circuit confirmed


# --------------------------------------------------------------------------- #
# sync() failure paths                                                        #
# --------------------------------------------------------------------------- #


def test_sync_initial_connect_failure_halts_before_pages(
    tmp_env: dict[str, Path],
) -> None:
    client = MockMCPClient(connect_raises=ConnectionError("network down"))
    with pytest.raises(BootBibleSyncError) as excinfo:
        sync(trigger="cli_manual", client_factory=lambda: client)
    assert excinfo.value.kind == "mcp_connect_failed"
    assert excinfo.value.step == "B2"
    # No pages written
    assert not list(tmp_env["bible_dir"].glob("*.md"))
    assert client.page_meta_calls == 0


def test_sync_per_page_failure_partial_with_warning(
    tmp_env: dict[str, Path],
) -> None:
    children = [
        ChildRef(page_id="page-uuid-00", title="00 — PROJECT VISION"),
        ChildRef(page_id="page-uuid-01", title="01 — REAL PROBLEM BREAKDOWN"),
        ChildRef(page_id="page-uuid-02", title="02 — USER ROLES"),
    ]
    metas, blocks = _build_minimal_pages(children)
    client = MockMCPClient(
        children=children,
        page_meta_by_id=metas,
        blocks_by_id=blocks,
        page_meta_raise_for_ids={"page-uuid-01"},  # one page fails
    )
    result = sync(trigger="cli_manual", client_factory=lambda: client)

    assert result.ok is False
    assert "00_project_vision" in result.synced
    assert "02_user_roles" in result.synced
    failed_slugs = {slug for slug, _ in result.failed}
    assert failed_slugs == {"01_real_problem_breakdown"}

    # Audit reflects the per-page failure
    roles = _audit_lines(tmp_env["roles_log"])
    failed_events = [e for e in roles if e["event"] == "sync_bible_page_failed"]
    assert len(failed_events) == 1
    assert failed_events[0]["details"]["page_slug"] == "01_real_problem_breakdown"


def test_sync_blocks_fetch_failure_marks_page_failed(
    tmp_env: dict[str, Path],
) -> None:
    children = [ChildRef(page_id="page-uuid-00", title="00 — PROJECT VISION")]
    metas, blocks = _build_minimal_pages(children)
    client = MockMCPClient(
        children=children,
        page_meta_by_id=metas,
        blocks_by_id=blocks,
        blocks_raise_for_ids={"page-uuid-00"},
    )
    result = sync(trigger="cli_manual", client_factory=lambda: client)
    assert result.ok is False
    assert ("00_project_vision", "RuntimeError") in result.failed


def test_sync_ec9_page_deleted_halts(tmp_env: dict[str, Path]) -> None:
    """Empty children list from a known parent → EC9 halt."""
    client = MockMCPClient(children=[])  # parent returns no children
    with pytest.raises(BootBibleSyncError) as excinfo:
        sync(trigger="cli_manual", client_factory=lambda: client)
    assert excinfo.value.kind == "page_deleted"


def test_sync_credentials_missing_halts(
    tmp_env: dict[str, Path],
) -> None:
    """credentials.toml exists but has no [anthropic] section."""
    tmp_env["creds_file"].write_text("", encoding="utf-8")  # blank file
    client = MockMCPClient()
    with pytest.raises(BootBibleSyncError) as excinfo:
        sync(trigger="cli_manual", client_factory=lambda: client)
    assert excinfo.value.kind == "credentials_missing"
    assert client.connect_calls == 0  # halted before connect


def test_sync_credentials_file_absent_halts(
    tmp_env: dict[str, Path],
) -> None:
    tmp_env["creds_file"].unlink()
    client = MockMCPClient()
    with pytest.raises(BootBibleSyncError) as excinfo:
        sync(trigger="cli_manual", client_factory=lambda: client)
    assert excinfo.value.kind == "credentials_missing"


# --------------------------------------------------------------------------- #
# check_drift()                                                               #
# --------------------------------------------------------------------------- #


def _seed_meta_and_mirror(
    tmp_env: dict[str, Path],
    slug: str,
    page_id: str,
    last_edited: str,
    body: str,
) -> None:
    """Write a mirror file + matching .sync_meta entry so the slug is
    in_sync to start."""
    mirror = tmp_env["bible_dir"] / f"{slug}.md"
    mirror.write_text(body, encoding="utf-8")
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()

    existing: dict[str, Any]
    if tmp_env["sync_meta"].exists():
        existing = json.loads(tmp_env["sync_meta"].read_text(encoding="utf-8"))
    else:
        existing = {
            "schema_version": "1.0.0",
            "produced_by": "BOOT_SEQUENCER",
            "last_synced": "2026-04-01T00:00:00+00:00",
            "pages": {},
        }
    existing["pages"][slug] = {
        "notion_page_id": page_id,
        "notion_last_edited_time": last_edited,
        "local_path": str(mirror),
        "content_sha256": sha,
    }
    tmp_env["sync_meta"].write_text(json.dumps(existing), encoding="utf-8")


def test_check_drift_in_sync(tmp_env: dict[str, Path]) -> None:
    body = "# 00\n\nbody\n"
    _seed_meta_and_mirror(
        tmp_env, "00_project_vision", "p00", "2026-05-01T00:00:00+00:00", body
    )
    children = [ChildRef(page_id="p00", title="00 — PROJECT VISION")]
    client = MockMCPClient(
        children=children,
        page_meta_by_id={
            "p00": PageMeta(
                page_id="p00",
                title="00 — PROJECT VISION",
                last_edited_time="2026-05-01T00:00:00+00:00",
            )
        },
    )
    rep = check_drift(client_factory=lambda: client)
    assert rep.in_sync == ("00_project_vision",)
    assert rep.has_drift is False


def test_check_drift_notion_newer(tmp_env: dict[str, Path]) -> None:
    body = "# 00\n\nbody\n"
    _seed_meta_and_mirror(
        tmp_env, "00_project_vision", "p00", "2026-04-01T00:00:00+00:00", body
    )
    children = [ChildRef(page_id="p00", title="00 — PROJECT VISION")]
    client = MockMCPClient(
        children=children,
        page_meta_by_id={
            "p00": PageMeta(
                page_id="p00",
                title="00 — PROJECT VISION",
                last_edited_time="2026-05-15T00:00:00+00:00",  # newer
            )
        },
    )
    rep = check_drift(client_factory=lambda: client)
    assert rep.notion_newer == ("00_project_vision",)


def test_check_drift_mirror_modified(tmp_env: dict[str, Path]) -> None:
    body = "# 00\n\nbody\n"
    _seed_meta_and_mirror(
        tmp_env, "00_project_vision", "p00", "2026-05-01T00:00:00+00:00", body
    )
    # Manually edit the mirror so sha256 changes
    (tmp_env["bible_dir"] / "00_project_vision.md").write_text(
        body + "extra\n", encoding="utf-8"
    )
    children = [ChildRef(page_id="p00", title="00 — PROJECT VISION")]
    client = MockMCPClient(
        children=children,
        page_meta_by_id={
            "p00": PageMeta(
                page_id="p00",
                title="00 — PROJECT VISION",
                last_edited_time="2026-05-01T00:00:00+00:00",
            )
        },
    )
    rep = check_drift(client_factory=lambda: client)
    assert rep.mirror_modified == ("00_project_vision",)


def test_check_drift_orphan(tmp_env: dict[str, Path]) -> None:
    """Local file with no meta entry and Notion doesn't claim it."""
    (tmp_env["bible_dir"] / "99_orphan.md").write_text("# orphan\n", encoding="utf-8")
    # Provide an unrelated child so connect/enumerate succeed
    children = [ChildRef(page_id="p00", title="00 — PROJECT VISION")]
    client = MockMCPClient(
        children=children,
        page_meta_by_id={
            "p00": PageMeta(
                page_id="p00",
                title="00 — PROJECT VISION",
                last_edited_time="2026-05-01T00:00:00+00:00",
            )
        },
    )
    rep = check_drift(client_factory=lambda: client)
    assert "99_orphan" in rep.orphan
    assert "00_project_vision" in rep.missing_from_meta


def test_check_drift_missing_from_meta(tmp_env: dict[str, Path]) -> None:
    """Notion has it, meta does not."""
    children = [ChildRef(page_id="p00", title="00 — PROJECT VISION")]
    client = MockMCPClient(
        children=children,
        page_meta_by_id={
            "p00": PageMeta(
                page_id="p00",
                title="00 — PROJECT VISION",
                last_edited_time="2026-05-01T00:00:00+00:00",
            )
        },
    )
    rep = check_drift(client_factory=lambda: client)
    assert rep.missing_from_meta == ("00_project_vision",)


def test_check_drift_credentials_missing_halts(tmp_env: dict[str, Path]) -> None:
    tmp_env["creds_file"].unlink()
    with pytest.raises(BootBibleSyncError) as excinfo:
        check_drift(client_factory=lambda: MockMCPClient())
    assert excinfo.value.kind == "credentials_missing"


def test_check_drift_connect_failure_halts(tmp_env: dict[str, Path]) -> None:
    client = MockMCPClient(connect_raises=ConnectionError("down"))
    with pytest.raises(BootBibleSyncError) as excinfo:
        check_drift(client_factory=lambda: client)
    assert excinfo.value.kind == "mcp_connect_failed"
