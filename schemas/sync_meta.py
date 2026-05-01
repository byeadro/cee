"""SyncMeta artifact schema.

Authorized by System Design Bible section 04 §5.5. Per-page sync state
for the bible mirror at ``~/cee/bible/.sync_meta.json``. Read by
``BOOT_SEQUENCER`` at boot step B2 (per bible 00 §12) to detect drift
between Notion canon and the local mirror; written exclusively by
``BOOT_SEQUENCER`` via ``cee sync-bible`` (per bible 02 §7.13);
bypasses ``PERSISTENCE_WRITER``.

Two deliberate deviations from the strict Phase 1 schema convention,
both grounded in bible 04 §5.5:

* ``schema_version`` is carried as an *instance field* (default
  ``"1.0.0"``) in addition to the ``ClassVar`` ``SCHEMA_VERSION``,
  because bible §5.5's JSON example explicitly includes it. Sync state
  is persistent across runs and may outlive its schema definition;
  carrying the version on disk lets future readers route through the
  migration scripts under ``~/cee/schemas/migrations/`` (per bible 04
  §6.1).
* Field ordering matches bible §5.5's JSON example exactly
  (``schema_version``, ``produced_by``, ``last_synced``, ``pages``)
  rather than Phase 1's required-first / defaulted-last stylistic
  convention. The bible JSON example is the canonical wire format;
  Pydantic v2 supports mixed required/defaulted ordering via keyword
  construction.
"""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from roles import RoleEnum

# sha256 hex check: 64 lowercase hex characters. Matches the convention
# established in ``schemas/raw_input.py`` for ``Attachment.sha256``.
_SHA256_PATTERN = r"^[0-9a-f]{64}$"


class PageEntry(BaseModel):
    """One bible-page entry inside ``SyncMeta.pages``.

    Per bible 04 §5.5: each entry records the Notion page identity,
    the Notion-side last-edited timestamp (used for Notion-side drift
    detection per §5.5 bullet 1), the local path of the mirror file,
    and the sha256 of that file at last sync (used for mirror-side
    drift detection per §5.5 bullet 2 + §4 Rule 7).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    notion_page_id: Annotated[str, Field(min_length=1)]
    notion_last_edited_time: Annotated[str, Field(min_length=1)]
    local_path: Annotated[str, Field(min_length=1)]
    content_sha256: Annotated[str, Field(pattern=_SHA256_PATTERN)]


class SyncMeta(BaseModel):
    """Per-page sync state for the bible mirror.

    Persisted at ``~/cee/bible/.sync_meta.json``. Per bible 04 §5.5,
    the file is written exclusively by ``BOOT_SEQUENCER`` via
    ``cee sync-bible`` and bypasses ``PERSISTENCE_WRITER`` (gap 3
    canon, bible 02 §7.13). The default ``produced_by`` reflects this.

    The keys of ``pages`` are ``<NN>_<slug>`` strings matching the
    ``.md`` filenames under ``~/cee/bible/`` (e.g., ``00_project_vision``).
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        str_strip_whitespace=True,
    )

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    schema_version: str = "1.0.0"
    produced_by: RoleEnum = RoleEnum.BOOT_SEQUENCER
    last_synced: Annotated[str, Field(min_length=1)]
    pages: dict[str, PageEntry] = Field(default_factory=dict)
