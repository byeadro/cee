"""Tests for ``skill_engine/registry.py`` — boot's Skill-index rebuilder.

Verifies the contract from bible 04 §11 + §6.5 + bible 00 §12 B4:

- the rebuilder walks ``skills_dir`` for ``<slug>/SKILL.md`` files
- emits records in the bible 04 §6.5 shape:
  ``{slug, path, version, frontmatter}``
- skips invalid Skills with a logged warning (bible 00 §12 B4: "logged
  and skipped, not loaded")
- writes ``index.json`` atomically (via ``persistence.atomic``)
- empty catalog → ``[]`` (bible 04 §11 DoD: "filesystem walk alone")
- output is sorted by slug for byte-stable ``index.json``

Tests use ``tmp_path`` for filesystem isolation. The real ``~/cee/skills/``
is never touched.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import frontmatter
import pytest

from skill_engine.registry import rebuild


# ─── Helpers ────────────────────────────────────────────────────────────


def _minimal_valid_metadata(slug: str, **overrides: object) -> dict:
    """Bible 15 §5.2 minimum required field set (with one trigger/input/
    output/task_type to satisfy ``min_length=1`` constraints)."""
    metadata: dict = {
        "name": slug,
        "description": f"Test fixture for {slug}.",
        "version": "1.0.0",
        "triggers": [f"trigger for {slug}"],
        "inputs": ["a context"],
        "outputs": ["a result"],
        "task_types_supported": ["BUILD"],
        "created_at": "2026-05-01T00:00:00Z",
        "created_by_run": "seed",
    }
    metadata.update(overrides)
    return metadata


def _write_skill(catalog: Path, slug: str, metadata: dict, body: str = "") -> Path:
    skill_dir = catalog / slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    post = frontmatter.Post(content=body, **metadata)
    skill_md.write_text(frontmatter.dumps(post), encoding="utf-8")
    return skill_md


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
    """If ``skills_dir`` does not exist yet, rebuild treats it as empty
    and creates it (via ``atomic_write_json`` ensuring the parent dir).
    Same boot-resilience guarantee as bible 04 §11."""
    missing = tmp_path / "skills"

    result = rebuild(missing)

    assert result == []
    assert (missing / "index.json").exists()


# ─── Single valid skill ─────────────────────────────────────────────────


def test_rebuild_single_valid_skill_emits_one_record(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo", _minimal_valid_metadata("demo"))

    result = rebuild(tmp_path)

    assert len(result) == 1
    record = result[0]
    assert record["slug"] == "demo"
    assert record["path"] == "demo/SKILL.md"
    assert record["version"] == "1.0.0"
    assert record["frontmatter"]["name"] == "demo"


def test_rebuild_record_shape_matches_bible_6_5(tmp_path: Path) -> None:
    """Bible 04 §6.5 declares the literal record shape:
    ``{"slug": "...", "path": "...", "version": "...", "frontmatter": {...}}``.
    The four keys are exhaustive — no extras."""
    _write_skill(tmp_path, "shape-check", _minimal_valid_metadata("shape-check"))

    [record] = rebuild(tmp_path)

    assert set(record.keys()) == {"slug", "path", "version", "frontmatter"}
    assert isinstance(record["slug"], str)
    assert isinstance(record["path"], str)
    assert isinstance(record["version"], str)
    assert isinstance(record["frontmatter"], dict)


def test_rebuild_writes_index_json_with_record(tmp_path: Path) -> None:
    _write_skill(tmp_path, "demo", _minimal_valid_metadata("demo"))

    rebuild(tmp_path)

    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert len(index) == 1
    assert index[0]["slug"] == "demo"


# ─── Determinism / sort order ───────────────────────────────────────────


def test_rebuild_sorts_records_by_slug(tmp_path: Path) -> None:
    """Bible 04 §11: ``index.json`` is regenerated on every boot. Stable
    byte output requires deterministic record order — sorted by slug."""
    _write_skill(tmp_path, "charlie", _minimal_valid_metadata("charlie"))
    _write_skill(tmp_path, "alpha", _minimal_valid_metadata("alpha"))
    _write_skill(tmp_path, "bravo", _minimal_valid_metadata("bravo"))

    result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["alpha", "bravo", "charlie"]


def test_rebuild_is_idempotent(tmp_path: Path) -> None:
    """Same filesystem state → same index.json bytes, every time."""
    _write_skill(tmp_path, "alpha", _minimal_valid_metadata("alpha"))
    _write_skill(tmp_path, "bravo", _minimal_valid_metadata("bravo"))

    rebuild(tmp_path)
    first = (tmp_path / "index.json").read_bytes()
    rebuild(tmp_path)
    second = (tmp_path / "index.json").read_bytes()

    assert first == second


# ─── Invalid skills are logged + skipped ────────────────────────────────


def test_rebuild_skips_skill_with_no_frontmatter_markers(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Bible 00 §12 B4: invalid frontmatter is logged + skipped."""
    _write_skill(tmp_path, "good", _minimal_valid_metadata("good"))
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text("no frontmatter here\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    # The valid one still appears.
    assert [r["slug"] for r in result] == ["good"]
    # The invalid one was logged (by the parser).
    assert any("no frontmatter markers" in rec.message for rec in caplog.records)


def test_rebuild_skips_skill_with_malformed_yaml(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _write_skill(tmp_path, "good", _minimal_valid_metadata("good"))
    bad_dir = tmp_path / "bad"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text(
        "---\nname: [unclosed\n---\nbody\n", encoding="utf-8"
    )

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]
    assert any("malformed YAML" in rec.message for rec in caplog.records)


def test_rebuild_skips_skill_with_schema_validation_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Frontmatter parses cleanly but fails ``SkillFrontmatter`` (e.g.,
    version is not semver). Halt-and-skip applies the same way."""
    _write_skill(tmp_path, "good", _minimal_valid_metadata("good"))
    _write_skill(
        tmp_path,
        "bad",
        _minimal_valid_metadata("bad", version="not-a-semver"),
    )

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]
    assert any(
        "validation failed" in rec.message and "bad" in rec.message
        for rec in caplog.records
    )


def test_rebuild_skips_skill_with_extra_field_in_frontmatter(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``SkillFrontmatter`` is ``extra='forbid'`` per bible 15 §5.2 — an
    unknown field must fail validation, not be silently accepted."""
    _write_skill(tmp_path, "good", _minimal_valid_metadata("good"))
    _write_skill(
        tmp_path,
        "extra",
        _minimal_valid_metadata("extra", surprise_field="should_be_rejected"),
    )

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]
    assert any("validation failed" in rec.message for rec in caplog.records)


def test_rebuild_skips_skill_when_name_disagrees_with_directory(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Bible 15 §5.2: ``name`` must match the parent directory name. The
    rebuilder enforces it — the schema only validates the slug regex,
    not the cross-check."""
    _write_skill(tmp_path, "good", _minimal_valid_metadata("good"))
    # directory ``mismatch`` but frontmatter ``name: other-name``
    _write_skill(
        tmp_path,
        "mismatch",
        _minimal_valid_metadata("mismatch", name="other-name"),
    )

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]
    assert any("disagrees with directory" in rec.message for rec in caplog.records)


def test_rebuild_skips_missing_skill_md_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """A directory under ``skills/`` without ``SKILL.md`` is logged
    (parser reports file-not-found) and skipped — not treated as a
    Skill."""
    _write_skill(tmp_path, "good", _minimal_valid_metadata("good"))
    (tmp_path / "no-skill-md").mkdir()

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]
    assert any("file not found" in rec.message for rec in caplog.records)


def test_rebuild_does_not_halt_on_first_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Bible 00 §12 B4: invalid Skills are skipped, *not* fatal. A
    bad Skill in the middle of the catalog must not block valid Skills
    that sort after it."""
    _write_skill(tmp_path, "alpha", _minimal_valid_metadata("alpha"))
    _write_skill(tmp_path, "bravo", _minimal_valid_metadata("bravo", version="bad"))
    _write_skill(tmp_path, "charlie", _minimal_valid_metadata("charlie"))

    with caplog.at_level(logging.WARNING):
        result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["alpha", "charlie"]


# ─── Filesystem hygiene ─────────────────────────────────────────────────


def test_rebuild_ignores_non_directory_entries(tmp_path: Path) -> None:
    """Loose files at the top of ``skills/`` (README, .DS_Store, etc.)
    are not Skills and must not cause the walk to fail or produce
    spurious records."""
    _write_skill(tmp_path, "good", _minimal_valid_metadata("good"))
    (tmp_path / "README.md").write_text("a readme", encoding="utf-8")
    (tmp_path / ".DS_Store").write_bytes(b"\x00\x01")

    result = rebuild(tmp_path)

    assert [r["slug"] for r in result] == ["good"]


def test_rebuild_uses_atomic_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bible 14: every filesystem write goes through
    ``persistence.atomic``. The rebuilder must call ``atomic_write_json``
    — never raw ``open(..., 'w')`` or ``json.dump`` to a file handle."""
    calls: list[Path] = []

    import skill_engine.registry as registry_module
    original = registry_module.atomic_write_json

    def tracking_atomic_write_json(path: Path, data: object, **kwargs: object) -> None:
        calls.append(path)
        original(path, data, **kwargs)

    monkeypatch.setattr(registry_module, "atomic_write_json", tracking_atomic_write_json)

    _write_skill(tmp_path, "demo", _minimal_valid_metadata("demo"))
    rebuild(tmp_path)

    assert calls == [tmp_path / "index.json"]


# ─── Integration with the live ``paths.SKILLS_DIR`` default ─────────────


def test_rebuild_default_skills_dir_is_paths_constant() -> None:
    """The ``skills_dir`` default must be ``paths.SKILLS_DIR`` so boot
    code calling ``rebuild()`` with no args hits the canonical
    catalog. Phase 2 build_status spec."""
    import inspect

    from paths import SKILLS_DIR
    from skill_engine.registry import rebuild as rebuild_fn

    sig = inspect.signature(rebuild_fn)
    assert sig.parameters["skills_dir"].default == SKILLS_DIR
