"""End-to-end integration tests for ``boot.bible_sync``.

Per T6's Step 3 design (Path A1.5): no real ``tests/fixtures/notion/``
directory yet — synthetic Notion responses are constructed inline
(matching the shape Anthropic SDK + Notion MCP will eventually
return). Tests exercise the full sync flow against a tmp filesystem
+ mock client, asserting:

* Multi-page sync end-to-end (parent enumerates, all children
  fetched, blocks normalized, files written, sync_meta valid).
* Idempotent re-sync against unchanged Notion state is a no-op
  (everything skipped, no rewrites).
* ``.sync_meta.json`` shape after sync round-trips through T1's
  :class:`schemas.SyncMeta` model.
* End-to-end failure flow: caller catches ``BootBibleSyncError``
  through the ``BootError`` / ``CEEException`` hierarchy.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import paths
from boot.bible_sync import sync
from boot.notion_mcp import (
    Block,
    ChildRef,
    NotionMCPClient,
    PageMeta,
    RichTextSpan,
)
from errors import BootBibleSyncError, BootError, CEEException
from schemas import SyncMeta


@dataclass
class IntegMockClient:
    """A more elaborate mock for integration tests — supports
    re-fetching the same data deterministically across multiple sync
    calls (so idempotency can be verified)."""

    children: list[ChildRef]
    page_meta_by_id: dict[str, PageMeta]
    blocks_by_id: dict[str, list[Block]]
    connect_calls: int = 0
    enumerate_calls: int = 0
    page_meta_calls: int = 0
    page_blocks_calls: int = 0

    def connect(self) -> None:
        self.connect_calls += 1

    def enumerate_children(self, parent_id: str) -> list[ChildRef]:
        self.enumerate_calls += 1
        return list(self.children)

    def fetch_page_metadata(self, page_id: str) -> PageMeta:
        self.page_meta_calls += 1
        return self.page_meta_by_id[page_id]

    def fetch_page_blocks(self, page_id: str) -> list[Block]:
        self.page_blocks_calls += 1
        return self.blocks_by_id[page_id]


@pytest.fixture
def tmp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    bible_dir = tmp_path / "cee" / "bible"
    bible_dir.mkdir(parents=True)
    sync_meta = bible_dir / ".sync_meta.json"

    audit_dir = tmp_path / "cee" / "audit"
    audit_dir.mkdir(parents=True)

    user_cfg_dir = tmp_path / ".cee"
    user_cfg_dir.mkdir(parents=True)
    creds = user_cfg_dir / "credentials.toml"
    creds.write_text('[anthropic]\napi_key = "sk-ant-integ-test"\n', encoding="utf-8")
    cfg = user_cfg_dir / "config.toml"
    cfg.write_text(
        '[paths]\nnotion_bible_root_id = "352e8536-d882-8050-aff6-f1dbcff68a09"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(paths, "BIBLE_DIR", bible_dir)
    monkeypatch.setattr(paths, "BIBLE_SYNC_META", sync_meta)
    monkeypatch.setattr(paths, "AUDIT_DIR", audit_dir)
    monkeypatch.setattr(paths, "AUDIT_CLI_LOG", audit_dir / "cli.log")
    monkeypatch.setattr(paths, "AUDIT_BOOT_LOG", audit_dir / "boot.log")
    monkeypatch.setattr(paths, "AUDIT_ROLES_LOG", audit_dir / "roles.log")
    monkeypatch.setattr(paths, "USER_CONFIG_DIR", user_cfg_dir)
    monkeypatch.setattr(paths, "CONFIG_FILE", cfg)
    monkeypatch.setattr(paths, "CREDENTIALS_FILE", creds)

    return {
        "bible_dir": bible_dir,
        "sync_meta": sync_meta,
        "creds_file": creds,
    }


def _build_three_page_corpus() -> IntegMockClient:
    """A small fixture corpus mimicking three real bibles. Block trees
    are minimal but include heading + paragraph + list + code +
    divider so the normalization stub gets exercised end-to-end."""
    children = [
        ChildRef(page_id="uuid-00", title="00 — PROJECT VISION"),
        ChildRef(page_id="uuid-04", title="04 — DATABASE FILE STRUCTURE"),
        ChildRef(page_id="uuid-19", title="19 — ERROR HANDLING + FAILURE STATES"),
    ]
    metas = {
        "uuid-00": PageMeta(
            page_id="uuid-00",
            title="00 — PROJECT VISION",
            last_edited_time="2026-04-15T10:00:00+00:00",
        ),
        "uuid-04": PageMeta(
            page_id="uuid-04",
            title="04 — DATABASE FILE STRUCTURE",
            last_edited_time="2026-04-20T11:00:00+00:00",
        ),
        "uuid-19": PageMeta(
            page_id="uuid-19",
            title="19 — ERROR HANDLING + FAILURE STATES",
            last_edited_time="2026-04-25T12:00:00+00:00",
        ),
    }
    blocks = {
        "uuid-00": [
            Block(type="heading_1", rich_text=(RichTextSpan(text="00 — PROJECT VISION"),)),
            Block(type="heading_2", rich_text=(RichTextSpan(text="1. What This Is"),)),
            Block(
                type="paragraph",
                rich_text=(
                    RichTextSpan(text="CEE is the "),
                    RichTextSpan(text="Claude Execution Engine", bold=True),
                    RichTextSpan(text="."),
                ),
            ),
            Block(type="divider"),
        ],
        "uuid-04": [
            Block(type="heading_1", rich_text=(RichTextSpan(text="04 — DATABASE FILE STRUCTURE"),)),
            Block(type="bulleted_list_item", rich_text=(RichTextSpan(text="filesystem canon"),)),
            Block(type="bulleted_list_item", rich_text=(RichTextSpan(text="user config"),)),
        ],
        "uuid-19": [
            Block(type="heading_1", rich_text=(RichTextSpan(text="19 — ERROR HANDLING"),)),
            Block(
                type="code",
                code_language="python",
                rich_text=(RichTextSpan(text="class CEEException(Exception): pass"),),
            ),
        ],
    }
    return IntegMockClient(
        children=children,
        page_meta_by_id=metas,
        blocks_by_id=blocks,
    )


# --------------------------------------------------------------------------- #
# E2E: multi-page sync                                                        #
# --------------------------------------------------------------------------- #


def test_e2e_three_page_sync(tmp_env: dict[str, Path]) -> None:
    client = _build_three_page_corpus()
    result = sync(trigger="cli_manual", client_factory=lambda: client)

    assert result.ok is True
    assert set(result.synced) == {
        "00_project_vision",
        "04_database_file_structure",
        "19_error_handling_failure_states",
    }
    bd = tmp_env["bible_dir"]
    for slug in result.synced:
        assert (bd / f"{slug}.md").exists()
    assert (bd / "00_project_vision.md").read_text(encoding="utf-8").startswith(
        "# 00 — PROJECT VISION\n"
    )


def test_e2e_sync_meta_roundtrips_through_schema(
    tmp_env: dict[str, Path],
) -> None:
    client = _build_three_page_corpus()
    sync(trigger="cli_manual", client_factory=lambda: client)

    raw = json.loads(tmp_env["sync_meta"].read_text(encoding="utf-8"))
    meta = SyncMeta.model_validate(raw)
    assert len(meta.pages) == 3
    assert meta.pages["00_project_vision"].notion_page_id == "uuid-00"
    assert meta.produced_by.value == "BOOT_SEQUENCER"
    # Every entry's content_sha256 is a valid 64-hex string
    for slug, entry in meta.pages.items():
        assert len(entry.content_sha256) == 64
        assert all(c in "0123456789abcdef" for c in entry.content_sha256)


# --------------------------------------------------------------------------- #
# E2E: idempotent re-sync                                                     #
# --------------------------------------------------------------------------- #


def test_e2e_idempotent_resync_skips_all(tmp_env: dict[str, Path]) -> None:
    client_a = _build_three_page_corpus()
    sync(trigger="cli_manual", client_factory=lambda: client_a)
    blocks_calls_first = client_a.page_blocks_calls

    # Re-sync against same data — should skip everything
    client_b = _build_three_page_corpus()
    result = sync(trigger="cli_manual", client_factory=lambda: client_b)

    assert result.synced == ()
    assert set(result.skipped) == {
        "00_project_vision",
        "04_database_file_structure",
        "19_error_handling_failure_states",
    }
    assert client_b.page_blocks_calls == 0  # no body fetches second time
    assert blocks_calls_first == 3  # all three fetched on first sync


def test_e2e_resync_after_notion_change_refetches_only_changed(
    tmp_env: dict[str, Path],
) -> None:
    """If only one page's last_edited_time changed in Notion, only
    that page's blocks should be re-fetched."""
    client_a = _build_three_page_corpus()
    sync(trigger="cli_manual", client_factory=lambda: client_a)

    # Bump only page 04's last_edited_time
    client_b = _build_three_page_corpus()
    client_b.page_meta_by_id["uuid-04"] = PageMeta(
        page_id="uuid-04",
        title="04 — DATABASE FILE STRUCTURE",
        last_edited_time="2026-05-30T15:00:00+00:00",  # newer
    )
    result = sync(trigger="cli_manual", client_factory=lambda: client_b)

    assert result.synced == ("04_database_file_structure",)
    assert set(result.skipped) == {
        "00_project_vision",
        "19_error_handling_failure_states",
    }
    assert client_b.page_blocks_calls == 1  # only page 04's blocks fetched


# --------------------------------------------------------------------------- #
# E2E: written markdown reflects normalization                                #
# --------------------------------------------------------------------------- #


def test_e2e_written_markdown_contains_expected_blocks(
    tmp_env: dict[str, Path],
) -> None:
    client = _build_three_page_corpus()
    sync(trigger="cli_manual", client_factory=lambda: client)
    bd = tmp_env["bible_dir"]

    page00 = (bd / "00_project_vision.md").read_text(encoding="utf-8")
    assert "# 00 — PROJECT VISION" in page00
    assert "## 1. What This Is" in page00
    assert "**Claude Execution Engine**" in page00
    assert "\n---\n" in page00

    page04 = (bd / "04_database_file_structure.md").read_text(encoding="utf-8")
    assert "- filesystem canon" in page04
    assert "- user config" in page04

    page19 = (bd / "19_error_handling_failure_states.md").read_text(encoding="utf-8")
    assert "```python\nclass CEEException(Exception): pass\n```" in page19


# --------------------------------------------------------------------------- #
# E2E: caller halts via BootBibleSyncError                                    #
# --------------------------------------------------------------------------- #


def test_e2e_halt_propagates_through_CEEException_hierarchy(
    tmp_env: dict[str, Path],
) -> None:
    """Boot sequencer (T8) catches BootBibleSyncError. End-to-end
    shape: it propagates through ``BootError`` and ``CEEException``."""
    client = _build_three_page_corpus()
    client.children = []  # force EC9

    try:
        sync(trigger="boot_auto", client_factory=lambda: client)
    except CEEException as exc:
        assert isinstance(exc, BootBibleSyncError)
        assert isinstance(exc, BootError)
        assert exc.kind == "page_deleted"
        assert exc.step == "B2"
    else:
        pytest.fail("BootBibleSyncError did not propagate via CEEException")
