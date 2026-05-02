"""PromotionQueue + PromotionQueueEntry artifact schemas.

The promotion queue is the bookkeeping layer between Run finalization
(when a new Skill or agent is generated and queued for Notion canon
promotion) and ``BOOT_SEQUENCER``'s B8 drain step (per bible 00 §12).
The on-disk file is ``~/cee/promotion_queue.json`` (per bible 00 §11
line 359, bible 04 §6.x line 182, ``paths.PROMOTION_QUEUE``).

**Bible coverage status:** No bible section defines the canonical
field-by-field schema for promotion-queue entries. The bible refers to
the file in many places (bible 00 §12 B8, bible 03 §5.5, bible 04
§5.4 / §7.2 / §7.3 / §10.6, bible 07 §5.5, bible 01 §8.6 / §10.8,
bible 02 §7.11, bible 19 §5.3) but always at the lifecycle-behavior
level — never field-set. This schema is the canonical T2 declaration;
ratification in bible is tracked as downstream candidate #31.

**Lifecycle status values** (bible 07 §5.5 + bible 03 §5.5):

* ``queued`` — entry created at Run finalize time; no Notion page yet.
* ``pending_review`` — candidate page written to Notion under
  ``Skill Promotions / Pending /``; awaiting OPERATOR move.
* ``approved`` — OPERATOR moved candidate to ``Approved /``.
* ``rejected`` — OPERATOR moved candidate to ``Rejected /``.

**Retry semantics** (bible 00 §12 B8): "Failures stay queued." The
``attempts`` counter increments on each drain attempt; ``last_error``
records the most recent failure reason. Bible 01 §10.8 caps the queue
at 500 entries with a warning at 50+; ``PROMOTION_QUEUE_LARGE`` is the
canonical warn event (bible 19 §5.3 line 149).

**Default ``produced_by``** is ``NOTION_WRITER`` per Phase 3 build_status
plan T2 spec; bible 02 §7.11 names ``NOTION_WRITER`` as the read+update
authority on the queue. The actual write surface in production is
shared (``PERSISTENCE_WRITER`` enqueues at Run finalize per bible 04
§7.2; ``NOTION_WRITER`` updates status on drain per bible 03 §5.5);
the schema default reflects the dominant lifecycle owner.

**Wrapper shape:** the on-disk JSON is a single object wrapping a list
of entries (mirroring ``SyncMeta``'s ``pages`` wrapper convention).
List rather than dict because (a) bible 04 §7.2 says "appended", (b)
bible 04 §10.6 says "rebuilt by walking", (c) the same slug may legally
appear with different statuses (e.g., a rejected candidate re-enqueued
after an OPERATOR-driven retry).
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

from roles import RoleEnum

PromotionKind = Literal["skill", "agent"]
PromotionStatus = Literal["queued", "pending_review", "approved", "rejected"]


class PromotionQueueEntry(BaseModel):
    """One entry in the promotion queue.

    Per the bible coverage notes in the module docstring, this is the
    canonical T2 declaration; bible ratification is tracked as
    downstream candidate #31.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    slug: Annotated[str, Field(min_length=1)]
    kind: PromotionKind
    status: PromotionStatus = "queued"
    enqueued_at: Annotated[str, Field(min_length=1)]
    enqueued_by_run: str | None = None
    target_notion_page_id: str | None = None
    payload_path: Annotated[str, Field(min_length=1)]
    attempts: Annotated[int, Field(ge=0)] = 0
    last_error: str | None = None


class PromotionQueue(BaseModel):
    """Top-level wrapper for the promotion queue file.

    Persisted at ``~/cee/promotion_queue.json``. Mirrors ``SyncMeta``'s
    wrapper convention (``schema_version`` carried as instance field
    in addition to ``ClassVar``, since this is durable cross-Run state
    that may outlive its schema definition).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    schema_version: str = "1.0.0"
    produced_by: RoleEnum = RoleEnum.NOTION_WRITER
    last_updated: Annotated[str, Field(min_length=1)]
    entries: list[PromotionQueueEntry] = Field(default_factory=list)
