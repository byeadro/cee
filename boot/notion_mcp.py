"""Notion MCP transport layer for ``cee sync-bible``.

Authorized by System Design Bible section 04 §5.6 (the bible-sync
operational spec) + section 14 line 273 (canonical Anthropic SDK
usage pattern: ``anthropic.Anthropic(api_key=...)``) + section 18
line 400 (canonical test-injection pattern: monkeypatch on
``anthropic.Anthropic.messages.create``). The Protocol below is the
adapter point bible 14 §5.6 establishes for transport-layer
substrate access — Notion content reaches CEE through Anthropic's
Messages API with the Notion MCP server attached, not through a
direct Notion REST integration. CEE-side credentials are limited to
``[anthropic] api_key`` per bible 04 §5.2; Notion MCP authentication
is platform-level per bible 21 §5.1.

**T6 ships orchestration only.** The concrete
``client.beta.messages.create(..., mcp_servers=[...])`` glue lands
in a later focused commit per AB lock at T6's Step 2 architectural
review. The :class:`_StubMCPClient` raises ``NotImplementedError``
on real operations; tests inject mocks via ``client_factory=`` to
:func:`boot.bible_sync.sync` / :func:`boot.bible_sync.check_drift`.

**Why a separate module from boot/bible_sync.py.** Mirrors bible 14
§5.6's ``executor/`` adapter directory pattern (``protocol.py``,
``paste_executor.py``, ``api_executor.py``). When concrete transport
lands, the diff lives entirely in this file — ``bible_sync.py``
remains untouched. This keeps the orchestration layer stable as the
substrate side evolves.

**Return-type field shapes mirror the Notion API.** The fields on
:class:`PageMeta`, :class:`ChildRef`, :class:`Block`, and
:class:`RichTextSpan` use Notion's JSON key names verbatim
(``page_id``, ``last_edited_time``, ``rich_text``, etc.) so the
future concrete implementer parses Notion's MCP tool_result blocks
into these dataclasses with minimal translation. The block ``type``
discriminator literal matches Notion's block-type taxonomy
(``heading_1``, ``paragraph``, ``bulleted_list_item``, ...) — see
:func:`boot.bible_sync._blocks_to_markdown` for the supported set.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


# --------------------------------------------------------------------------- #
# Return types — field shapes mirror Notion API JSON                          #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PageMeta:
    """One Notion page's metadata, as returned by Notion's
    ``notion.get-page`` MCP tool.

    Field names match Notion's API JSON keys verbatim so future
    parsing of ``messages.create`` tool_result blocks is a direct
    field-by-field assignment.
    """

    page_id: str  # hyphenated UUID per Notion's wire format
    title: str  # extracted from the page's title property
    last_edited_time: str  # ISO 8601 with timezone; Notion-canonical


@dataclass(frozen=True)
class ChildRef:
    """One child page enumerated under a parent page.

    Returned by the Notion ``notion.get-block-children`` MCP tool when
    the parent's children include ``child_page`` blocks. The order
    returned reflects Notion's canonical ordering.
    """

    page_id: str
    title: str


@dataclass(frozen=True)
class RichTextSpan:
    """One span inside a Notion ``rich_text`` array.

    Annotation field names match Notion's annotation object verbatim.
    Phase 2 stub scope: ``bold``, ``italic``, ``code`` only — none of
    underline/strikethrough/color have surfaced in the bible corpus
    so far. When they do, extending this dataclass is additive.
    """

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False


@dataclass(frozen=True)
class Block:
    """One Notion block, as returned by ``notion.get-block-children``.

    The ``type`` discriminator matches Notion's block-type taxonomy.
    Per-type payload fields populate per Notion's block schema:

    * Text-bearing blocks (headings, paragraph, list items, quote,
      code) populate :attr:`rich_text`.
    * Code blocks additionally populate :attr:`code_language`.
    * Table rows populate :attr:`cells` (one tuple of rich_text
      spans per cell).
    * Bulleted/numbered list items and table rows may have nested
      :attr:`children` (max depth 2 per AB-locked T6 Q1).

    Block types not in the Literal below are excluded from the Phase 2
    normalization stub — see :func:`boot.bible_sync._blocks_to_markdown`
    for the full supported set + exclusion rationale.
    """

    type: Literal[
        "heading_1",
        "heading_2",
        "heading_3",
        "paragraph",
        "bulleted_list_item",
        "numbered_list_item",
        "code",
        "divider",
        "quote",
        "table",
        "table_row",
    ]
    rich_text: tuple[RichTextSpan, ...] = ()
    code_language: str | None = None
    cells: tuple[tuple[RichTextSpan, ...], ...] = ()
    children: tuple["Block", ...] = ()


# --------------------------------------------------------------------------- #
# Protocol                                                                    #
# --------------------------------------------------------------------------- #


class NotionMCPClient(Protocol):
    """Transport-layer Protocol for Notion access via Anthropic's MCP.

    Concrete implementation (lands in a later commit) issues
    ``client.beta.messages.create(..., mcp_servers=[{"type": "url",
    "url": "...", "name": "notion", ...}])`` calls and parses the
    ``tool_result`` blocks back into the dataclasses above. T6 ships
    only the Protocol + :class:`_StubMCPClient`; tests inject mocks.

    Each method may raise an exception to indicate transport failure.
    The orchestration layer (:func:`boot.bible_sync.sync`) classifies
    exceptions:

    * :meth:`connect` failure → halt before any page is fetched
      (``BootBibleSyncError(kind="mcp_connect_failed")``).
    * :meth:`fetch_page_metadata` / :meth:`fetch_page_blocks` failure
      mid-sync → that page is logged as failed and the loop continues
      (partial-with-warning per bible 04 §5.6).
    * :meth:`enumerate_children` returning empty when bible 04 §5.2's
      ``notion_bible_root_id`` is set → EC9 deleted-page halt
      (``BootBibleSyncError(kind="page_deleted")``).
    """

    def connect(self) -> None:
        """Verify the transport is reachable.

        Per bible 04 §5.6 step 2: this is the precondition that lets
        sync proceed; failure here halts before any page is touched.
        Concrete impl: short ``messages.create`` call confirming the
        Notion MCP tool is callable, or equivalent reachability check.
        Raises on auth failure, network unavailability, or MCP
        unavailable.
        """
        ...

    def fetch_page_metadata(self, page_id: str) -> PageMeta:
        """Return one page's metadata.

        Concrete impl: ``messages.create`` call requesting the
        ``notion.get-page`` MCP tool for ``page_id``; parse the
        ``tool_result`` block into :class:`PageMeta`.
        """
        ...

    def enumerate_children(self, parent_id: str) -> list[ChildRef]:
        """Return the parent page's child-page references in order.

        Concrete impl: ``messages.create`` call requesting
        ``notion.get-block-children`` for ``parent_id``, filtering
        the returned blocks to ``child_page`` type, and resolving each
        to its title via ``notion.get-page`` (or whatever shape MCP
        ergonomics dictate at landing time).
        """
        ...

    def fetch_page_blocks(self, page_id: str) -> list[Block]:
        """Return the page's body blocks as a flat list, with nested
        children resolved up to depth 2.

        Concrete impl: ``messages.create`` walking
        ``notion.get-block-children`` recursively. Block types outside
        the :class:`Block` Literal are converted to the closest
        supported type or omitted (concrete impl decides the mapping;
        T6's stub scope is the supported set in :class:`Block`).
        """
        ...


# --------------------------------------------------------------------------- #
# Stub                                                                        #
# --------------------------------------------------------------------------- #


_NOT_IMPLEMENTED_MESSAGE = (
    "Notion MCP transport not yet implemented. T6 ships orchestration "
    "+ Protocol; concrete `client.beta.messages.create(..., "
    "mcp_servers=[...])` glue lands in a later focused commit. Inject "
    "a mock client via `client_factory=` to "
    "boot.bible_sync.sync()/check_drift() for testing."
)


class _StubMCPClient:
    """Default :class:`NotionMCPClient` impl that raises on real calls.

    This class exists so :func:`default_client_factory` can return a
    Protocol-conforming object today without forcing every caller to
    pass ``client_factory=`` explicitly. Production callers (boot
    sequencer + CLI dispatcher) will get a clear error pointing at
    the deferred commit; tests inject mocks via ``client_factory=``.
    """

    def connect(self) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)

    def fetch_page_metadata(self, page_id: str) -> PageMeta:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)

    def enumerate_children(self, parent_id: str) -> list[ChildRef]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)

    def fetch_page_blocks(self, page_id: str) -> list[Block]:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)


def default_client_factory() -> NotionMCPClient:
    """Return the default :class:`NotionMCPClient` for production use.

    Returns a :class:`_StubMCPClient` that raises ``NotImplementedError``
    on real operations. Tests bypass this by passing
    ``client_factory=`` to the orchestration entry points.
    """
    return _StubMCPClient()
