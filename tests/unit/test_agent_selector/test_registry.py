"""Tests for ``agent_selector/registry.py`` — boot's agent-index rebuilder.

Verifies the contract from bible 04 §11 + §6.5, bible 00 §12 B5, and
bible 16 §5.2:

- the rebuilder walks ``agents_dir`` for ``<slug>.md`` flat files
- emits records in the bible 04 §6.5 shape:
  ``{slug, path, version, frontmatter}``
- skips invalid agents with a logged warning (symmetric to bible 00
  §12 B4's "logged and skipped" precedent — B5 itself is terse)
- enforces ``frontmatter.name == filename_stem`` per bible 16 §5.2
- writes ``index.json`` atomically (via ``persistence.atomic``)
- empty catalog → ``[]``
- output sorted by slug for byte-stable ``index.json``

Mirrors ``tests/unit/test_skill_engine/test_registry.py`` structurally —
the registries are intentionally parallel (bible 04 §11 names them in
the same sentence). Differences: flat-file walk, slug-from-filename,
``AgentFrontmatter``, filename-based cross-check.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import frontmatter
import pytest

from agent_selector.registry import rebuild


# ─── Helpers ────────────────────────────────────────────────────────────


def _minimal_valid_metadata(slug: str, **overrides: object) -> dict:
    """Bible 06 §5.2.1 / Phase 1 ``AgentFrontmatter`` minimum required
    field set. Default posture is ``primary`` so ``domain`` is not
    required. Specialist-domain coupling is exercised in a dedicated
    test below."""
    metadata: dict = {
        "name": slug,
        "description": f"Test agent fixture for {slug}.",
        "posture": "primary",
        "task_types_supported": ["BUILD"],
        "capabilities": ["fixture-capability"],
        "allowed_tools": ["Read"],
        "version": "1.0.0",
    }
    metadata.update(overrides)
    return metadata


def _write_agent(catalog: Path, slug: str, metadata: dict, body: str = "") -> Path:
    catalog.mkdir(parents=True, exist_ok=True)
    agent_md = catalog / f"{slug}.md"
    post = frontmatter.Post(content=body, **metadata)
    agent_md.write_text(frontmatter.dumps(post), encoding="utf-8")
    return agent_md


# ─── Empty catalog ──────────────────────────────────────────────────────


def test_rebuild_empty_catalog_returns_empty_list(tmp_path: Path) -> None:
    """Bible 04 §11 DoD: index rebuilds work from filesystem walk alone."""
    result = rebuild(tmp_path)

    assert result == []


def test_rebuild_empty_catalog_writes_empty_index_json(tmp_path: Path) -> None:
    rebuild(tmp_path)

    index = tmp_path / "index.json"
    assert index.exists()
    assert json.loads(index.read_text(encoding="utf-8")) == []


def test_rebuild_handles_missing_catalog_directory(tmp_path: Path) -> None:
    """If ``agents_dir`` does not exist yet, rebuild treats it as empty
    and creates it (via ``atomic_write_json`` ensuring the parent dir).
    Same boot-resilience guarantee as bible 04 §11."""
    missing = tmp_path / "agents"

    result = rebuild(missing)

    assert result == []
    assert (missing / "index.json").exists()


# ─── Single valid agent ─────────────────────────────────────────────────


def test_rebuild_single_valid_agent_emits_one_record(tmp_path: Path) -> None:
    _write_agent(tmp_path, "demo", _minimal_valid_metadata("demo"))

    result = rebuild(tmp_path)

    assert len(result) == 1
    record = result[0]
    assert record["slug"] == "demo"
    assert record["path"] == "demo.md"
    assert record["version"] == "1.0.0"
    assert record["frontmatter"]["name"] == "demo"
    assert record["frontmatter"]["posture"] == "primary"


def test_rebuild_record_shape_matches_bible_6_5(tmp_path: Path) -> None:
    """Bible 04 §6.5 declares the literal record shape:
    ``{"slug": "...", "path": "...", "version": "...", "frontmatter": {...}}``.
    The four keys are exhaustive — no extras."""
    _write_agent(tmp_path, "shape-check", _minimal_valid_metadata("shape-check"))

    [record] = rebuild(tmp_path)

    assert set(record.keys()) == {"slug", "path", "version", "frontmatter"}
    assert isinstance(record["slug"], str)
    assert isinstance(record["path"], str)
    assert isinstance(record["version"], str)
    assert isinstance(record["frontmatter"], dict)


def test_rebuild_writes_index_json_with_record(tmp_path: Path) -> None:
    _write_agent(tmp_path, "demo", _minimal_valid_metadata("demo"))

    rebuild(tmp_path)

    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert len(index) == 1
    assert index[0]["slug"] == "demo"


def test_rebuild_specialist_agent_with_domain_validates(tmp_path: Path) -> None:
    """Bible 06 §5.2.1 model_validator: posture=specialist requires
    domain. A correctly-formed specialist must validate; ensures the
    rebuilder doesn't accidentally reject the specialist case."""
    _write_agent(
        tmp_path,
        "code-specialist",
        _minimal_valid_metadata(
            "code-specialist", posture="specialist", domain="code"
        ),
    )

    [record] = rebuild(tmp_path)

    assert record["frontmatter"]["posture"] == "specialist"
    assert record["frontmatter"]["domain"] == "code"


# ─── Determinism / sort order ───────────────────────────────────────────


def test_rebuild_sorts_records_by_slug(tmp_path: Path) -> None:
    """Bible 04 §11: ``index.json`` is regenerated on every boot. Stable
    byte output requires deterministic record order — sorted by slug."""
    _write_agent(tmp_path, "charlie", _minimal_valid_metadata("charlie"))
    _write_agent(tmp_path, "alpha", _minimal_valid_metadata("alpha"))
    _write_agent(tmp_path, "bravo", _minimal_valid_metadata("bravo"))

    result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["alpha", "bravo", "charlie"]


def test_rebuild_is_idempotent(tmp_path: Path) -> None:
    """Same filesystem state → same index.json bytes, every time."""
    _write_agent(tmp_path, "alpha", _minimal_valid_metadata("alpha"))
    _write_agent(tmp_path, "bravo", _minimal_valid_metadata("bravo"))

    rebuild(tmp_path)
    first = (tmp_path / "index.json").read_bytes()
    rebuild(tmp_path)
    second = (tmp_path / "index.json").read_bytes()

    assert first == second


# ─── Invalid agents are logged + skipped ────────────────────────────────


def test_rebuild_skips_agent_with_no_frontmatter_markers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Symmetric to bible 00 §12 B4: invalid frontmatter is logged +
    skipped. B5 doesn't contradict; bible 04 §11 DoD requires
    walk-from-filesystem-alone resilience."""
    _write_agent(tmp_path, "good", _minimal_valid_metadata("good"))
    (tmp_path / "bad.md").write_text("no frontmatter here\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    # The valid one still appears.
    assert [r["slug"] for r in result] == ["good"]
    # The invalid one was logged (by the parser).
    assert any("no frontmatter markers" in rec.message for rec in caplog.records)


def test_rebuild_skips_agent_with_malformed_yaml(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_agent(tmp_path, "good", _minimal_valid_metadata("good"))
    (tmp_path / "bad.md").write_text(
        "---\nname: [unclosed\n---\nbody\n", encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]
    assert any("malformed YAML" in rec.message for rec in caplog.records)


def test_rebuild_skips_agent_with_schema_validation_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Frontmatter parses cleanly but fails ``AgentFrontmatter`` (e.g.,
    posture not in the closed enum). Halt-and-skip applies."""
    _write_agent(tmp_path, "good", _minimal_valid_metadata("good"))
    _write_agent(
        tmp_path,
        "bad",
        _minimal_valid_metadata("bad", posture="invalid-posture"),
    )

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]
    assert any(
        "validation failed" in rec.message and "bad" in rec.message
        for rec in caplog.records
    )


def test_rebuild_skips_specialist_without_domain(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Bible 06 §5.2.1 model_validator: posture=specialist requires
    domain. The schema rejects, the rebuilder logs + skips."""
    _write_agent(tmp_path, "good", _minimal_valid_metadata("good"))
    _write_agent(
        tmp_path,
        "specialist-no-domain",
        _minimal_valid_metadata("specialist-no-domain", posture="specialist"),
    )

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]
    assert any("validation failed" in rec.message for rec in caplog.records)


def test_rebuild_skips_agent_with_extra_field_in_frontmatter(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``AgentFrontmatter`` is ``extra='forbid'`` — an unknown field
    must fail validation, not be silently accepted."""
    _write_agent(tmp_path, "good", _minimal_valid_metadata("good"))
    _write_agent(
        tmp_path,
        "extra",
        _minimal_valid_metadata("extra", surprise_field="should_be_rejected"),
    )

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]
    assert any("validation failed" in rec.message for rec in caplog.records)


def test_rebuild_skips_agent_when_name_disagrees_with_filename(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Bible 16 §5.2: ``name`` must match the filename stem (no .md).
    The rebuilder enforces it — the schema only validates the slug
    regex, not the cross-check."""
    _write_agent(tmp_path, "good", _minimal_valid_metadata("good"))
    # filename ``mismatch.md`` but frontmatter ``name: other-name``
    _write_agent(
        tmp_path,
        "mismatch",
        _minimal_valid_metadata("mismatch", name="other-name"),
    )

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]
    assert any(
        "disagrees with filename" in rec.message for rec in caplog.records
    )


def test_rebuild_does_not_halt_on_first_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A bad agent in the middle of the catalog must not block valid
    agents that sort after it."""
    _write_agent(tmp_path, "alpha", _minimal_valid_metadata("alpha"))
    _write_agent(
        tmp_path, "bravo", _minimal_valid_metadata("bravo", version="bad")
    )
    _write_agent(tmp_path, "charlie", _minimal_valid_metadata("charlie"))

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["alpha", "charlie"]


# ─── Filesystem hygiene ─────────────────────────────────────────────────


def test_rebuild_ignores_non_md_files(tmp_path: Path) -> None:
    """Bible 16 §3: agents are flat ``<slug>.md`` files. Non-``.md``
    entries (``.gitkeep``, ``README.md``-stylized but not an agent,
    ``.DS_Store``) are not agents and must not produce records or
    spurious warnings."""
    _write_agent(tmp_path, "good", _minimal_valid_metadata("good"))
    (tmp_path / ".gitkeep").write_text("", encoding="utf-8")
    (tmp_path / ".DS_Store").write_bytes(b"\x00\x01")
    (tmp_path / "notes.txt").write_text("not an agent", encoding="utf-8")

    result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]


def test_rebuild_ignores_subdirectories(tmp_path: Path) -> None:
    """Bible 16 §3: agents are flat files; subdirectories like
    ``agent_resources/`` are not agents."""
    _write_agent(tmp_path, "good", _minimal_valid_metadata("good"))
    (tmp_path / "agent_resources").mkdir()
    (tmp_path / "agent_resources" / "shared.md").write_text(
        "---\nname: shared\n---\nbody\n", encoding="utf-8"
    )

    result = rebuild(tmp_path)

    # Only the flat-file agent appears; the nested .md is not walked.
    assert [r["slug"] for r in result] == ["good"]


def test_rebuild_ignores_existing_index_json(tmp_path: Path) -> None:
    """A stale ``index.json`` from a prior boot is not a ``.md`` file
    so it's already excluded by the suffix check, but make this an
    explicit invariant: the rebuilder must not try to interpret its
    own output as an agent."""
    _write_agent(tmp_path, "good", _minimal_valid_metadata("good"))
    (tmp_path / "index.json").write_text("[]", encoding="utf-8")

    result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]


def test_rebuild_uses_atomic_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bible 14: every filesystem write goes through
    ``persistence.atomic``. The rebuilder must call ``atomic_write_json``
    — never raw ``open(..., 'w')`` or ``json.dump`` to a file handle."""
    calls: list[Path] = []

    import agent_selector.registry as registry_module

    original = registry_module.atomic_write_json

    def tracking_atomic_write_json(
        path: Path, data: object, **kwargs: object
    ) -> None:
        calls.append(path)
        original(path, data, **kwargs)

    monkeypatch.setattr(
        registry_module, "atomic_write_json", tracking_atomic_write_json
    )

    _write_agent(tmp_path, "demo", _minimal_valid_metadata("demo"))
    rebuild(tmp_path)

    assert calls == [tmp_path / "index.json"]


# ─── Integration with the live ``paths.AGENTS_DIR`` default ─────────────


def test_rebuild_default_agents_dir_is_paths_constant() -> None:
    """The ``agents_dir`` default must be ``paths.AGENTS_DIR`` so boot
    code calling ``rebuild()`` with no args hits the canonical
    catalog. Phase 2 build_status spec."""
    import inspect

    from agent_selector.registry import rebuild as rebuild_fn
    from paths import AGENTS_DIR

    sig = inspect.signature(rebuild_fn)
    assert sig.parameters["agents_dir"].default == AGENTS_DIR
