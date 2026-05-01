"""Unit tests for ``boot.notion_mcp`` — Protocol + dataclass + stub.

Per T6's Step 3 design:

* The Protocol shape itself is structural; we verify it's importable
  and that the stub conforms.
* The frozen dataclasses are invariants the orchestration relies on.
* The stub's only contract is "raise NotImplementedError on every
  real op" — concrete transport lands in a later commit per AB lock.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from boot.notion_mcp import (
    Block,
    ChildRef,
    NotionMCPClient,
    PageMeta,
    RichTextSpan,
    _StubMCPClient,
    default_client_factory,
)


# --------------------------------------------------------------------------- #
# Frozen dataclass invariants                                                 #
# --------------------------------------------------------------------------- #


def test_page_meta_is_frozen() -> None:
    pm = PageMeta(page_id="x", title="t", last_edited_time="2026-05-01T00:00:00Z")
    with pytest.raises(FrozenInstanceError):
        pm.title = "tampered"  # type: ignore[misc]


def test_child_ref_is_frozen() -> None:
    cr = ChildRef(page_id="x", title="t")
    with pytest.raises(FrozenInstanceError):
        cr.title = "tampered"  # type: ignore[misc]


def test_rich_text_span_is_frozen() -> None:
    span = RichTextSpan(text="hi")
    with pytest.raises(FrozenInstanceError):
        span.text = "tampered"  # type: ignore[misc]


def test_block_is_frozen() -> None:
    block = Block(type="paragraph", rich_text=(RichTextSpan(text="hi"),))
    with pytest.raises(FrozenInstanceError):
        block.type = "heading_1"  # type: ignore[misc]


def test_rich_text_span_defaults() -> None:
    span = RichTextSpan(text="hello")
    assert span.bold is False
    assert span.italic is False
    assert span.code is False


def test_block_defaults_match_protocol_contract() -> None:
    """Every per-type field defaults to a sensible empty value so a
    block of a given ``type`` only needs to populate the fields it
    cares about."""
    block = Block(type="divider")
    assert block.rich_text == ()
    assert block.code_language is None
    assert block.cells == ()
    assert block.children == ()


# --------------------------------------------------------------------------- #
# Stub                                                                        #
# --------------------------------------------------------------------------- #


def test_default_client_factory_returns_stub() -> None:
    client = default_client_factory()
    assert isinstance(client, _StubMCPClient)


def test_stub_connect_raises_not_implemented() -> None:
    client = default_client_factory()
    with pytest.raises(NotImplementedError) as excinfo:
        client.connect()
    assert "Notion MCP transport not yet implemented" in str(excinfo.value)
    assert "client_factory" in str(excinfo.value)


def test_stub_fetch_page_metadata_raises() -> None:
    client = default_client_factory()
    with pytest.raises(NotImplementedError):
        client.fetch_page_metadata("any-id")


def test_stub_enumerate_children_raises() -> None:
    client = default_client_factory()
    with pytest.raises(NotImplementedError):
        client.enumerate_children("any-id")


def test_stub_fetch_page_blocks_raises() -> None:
    client = default_client_factory()
    with pytest.raises(NotImplementedError):
        client.fetch_page_blocks("any-id")


# --------------------------------------------------------------------------- #
# Protocol structural conformance                                             #
# --------------------------------------------------------------------------- #


def test_stub_conforms_to_protocol() -> None:
    """The stub must structurally satisfy the Protocol — required so
    callers can pass it without isinstance checks."""

    def takes_protocol(client: NotionMCPClient) -> None:
        # Just exists to surface a type-checker error if the stub
        # doesn't satisfy the Protocol.
        return None

    takes_protocol(_StubMCPClient())


def test_protocol_has_expected_methods() -> None:
    """Spot-check: the Protocol declares the four orchestration-level
    operations T6 needs."""
    expected = {
        "connect",
        "fetch_page_metadata",
        "enumerate_children",
        "fetch_page_blocks",
    }
    actual = {name for name in dir(NotionMCPClient) if not name.startswith("_")}
    missing = expected - actual
    assert not missing, f"Protocol missing methods: {missing}"
