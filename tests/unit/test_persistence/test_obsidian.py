"""Tests for ``persistence/obsidian.py`` — the vault scaffold function.

All tests redirect ``paths.OBSIDIAN_*`` constants to a ``tmp_path``
subtree via ``monkeypatch``. None of these tests touch the real
``~/SecondBrain/cee/`` vault. The bible-grounding test parses bible
13 §5.1 directly so any future drift between code and bible surfaces
in CI rather than in production.

Halt resolutions applied (per task 11 OPERATOR sign-off):

- ``_templates/`` is created empty. The five template ``.md`` files
  bible §5.1 lists inside it ship with the Phase 5+ renderers; the
  bible-grounding test compares directories only.
- Idempotency is *create-only*: a pre-existing file is preserved
  regardless of content. The strict §5.10 hash-and-skip belongs to
  the per-Run writer.
- README.md uses minimal frontmatter ``type: meta`` and the verbatim
  body text from the OPERATOR-approved task spec. No wiki-links, no
  generated_by/created_at provenance fields (closed-frontmatter).
"""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from unittest.mock import patch

import pytest

import paths
from persistence import obsidian as obsidian_module
from persistence.obsidian import _idempotent_write, scaffold_obsidian


# ─── Fixture ────────────────────────────────────────────────────────────


@pytest.fixture
def vault_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every ``paths.OBSIDIAN_*`` constant under ``tmp_path``.

    Returns the patched ``OBSIDIAN_VAULT`` (which does NOT exist yet —
    creation is the function under test's job). Reverts after the test.
    """
    vault = tmp_path / "SecondBrain" / "cee"
    monkeypatch.setattr(paths, "OBSIDIAN_VAULT", vault)
    monkeypatch.setattr(paths, "OBSIDIAN_RUNS_DIR", vault / "runs")
    monkeypatch.setattr(paths, "OBSIDIAN_SKILLS_DIR", vault / "skills")
    monkeypatch.setattr(paths, "OBSIDIAN_AGENTS_DIR", vault / "agents")
    monkeypatch.setattr(paths, "OBSIDIAN_BIBLE_DIR", vault / "bible")
    monkeypatch.setattr(paths, "OBSIDIAN_AUDIT_DIR", vault / "audit")
    monkeypatch.setattr(paths, "OBSIDIAN_TEMPLATES_DIR", vault / "_templates")
    return vault


# ─── Helpers ────────────────────────────────────────────────────────────


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _extract_frontmatter(text: str) -> dict[str, str]:
    """Tiny YAML-ish frontmatter parser for the scaffold's 1-2 field stubs.

    The scaffold writes plain ``key: value`` pairs between ``---`` lines.
    Full YAML parsing would be overkill (and would pull in PyYAML for a
    test helper). If a future change adds nested structures here, this
    helper stops being sufficient and the test will fail loudly — which
    is the desired signal.
    """
    lines = text.splitlines()
    assert lines and lines[0] == "---", (
        f"missing opening frontmatter delimiter; first lines: {lines[:3]!r}"
    )
    end = lines.index("---", 1)
    out: dict[str, str] = {}
    for raw in lines[1:end]:
        if not raw.strip():
            continue
        key, _, val = raw.partition(":")
        out[key.strip()] = val.strip()
    return out


# ─── Standard scaffolding behaviour ─────────────────────────────────────


def test_scaffold_creates_vault_root(vault_root: Path) -> None:
    assert not vault_root.exists()
    scaffold_obsidian()
    assert vault_root.is_dir()


def test_scaffold_creates_all_subdirs(vault_root: Path) -> None:
    scaffold_obsidian()
    for sub in ("runs", "skills", "agents", "bible", "audit", "_templates"):
        assert (vault_root / sub).is_dir(), f"missing subdir: {sub}/"


def test_scaffold_creates_readme_at_root(vault_root: Path) -> None:
    scaffold_obsidian()
    readme = vault_root / "README.md"
    assert readme.is_file()
    text = _read(readme)
    assert text.startswith("---\n")
    assert "type: meta" in text
    # Verbatim body sentence (bible 13 §5.1 + task 11 OPERATOR sign-off).
    assert "human-readable mirror layer" in text
    assert "Filesystem at `~/cee/` is canonical" in text


def test_scaffold_creates_index_in_each_content_dir(vault_root: Path) -> None:
    scaffold_obsidian()
    for sub in ("runs", "skills", "agents", "bible", "audit"):
        idx = vault_root / sub / "index.md"
        assert idx.is_file(), f"missing {sub}/index.md"
    # _templates/ deliberately has no index.md (bible §5.1 lists templates,
    # not an index, in that directory; templates ship in Phase 5+).
    assert not (vault_root / "_templates" / "index.md").exists()


def test_scaffold_returns_correct_counts_on_fresh_install(
    vault_root: Path,
) -> None:
    counts = scaffold_obsidian()
    # 7 dirs: vault root + runs/skills/agents/bible/audit/_templates/
    # 6 files: README + 5 indexes
    assert counts == {"directories_created": 7, "files_created": 6}


def test_scaffold_returns_zero_counts_on_idempotent_rerun(
    vault_root: Path,
) -> None:
    scaffold_obsidian()
    second = scaffold_obsidian()
    assert second == {"directories_created": 0, "files_created": 0}


def test_scaffold_does_not_overwrite_modified_readme(
    vault_root: Path,
) -> None:
    """Pre-existing README is OPERATOR property — scaffold preserves it.

    This is the §5.10-vs-§EC3 conflict resolution: scaffold uses
    create-only semantics, stricter than §5.10 hash-and-skip.
    """
    paths.ensure_dir(vault_root)
    readme = vault_root / "README.md"
    operator_text = "OPERATOR custom note — do not overwrite\n"
    readme.write_text(operator_text, encoding="utf-8")

    counts = scaffold_obsidian()

    assert _read(readme) == operator_text
    # README skipped; the 5 indexes were still created.
    assert counts["files_created"] == 5


def test_scaffold_uses_atomic_write(vault_root: Path) -> None:
    """Every scaffold write goes through ``atomic_write_text``.

    Wraps the real implementation so the side effect (file creation)
    still occurs while the spy counts calls. Fresh install ⇒ 6 writes.
    """
    import persistence.atomic as atomic_module

    with patch.object(
        obsidian_module,
        "atomic_write_text",
        wraps=atomic_module.atomic_write_text,
    ) as spy:
        scaffold_obsidian()

    # 1 README + 5 indexes
    assert spy.call_count == 6
    # Every call's first positional arg is a Path under vault_root.
    for call in spy.call_args_list:
        target = call.args[0]
        assert isinstance(target, Path)
        assert vault_root in target.parents or target.parent == vault_root


def test_scaffold_uses_paths_constants() -> None:
    """Source must reference ``paths.OBSIDIAN_*`` — never hardcode strings.

    Catches a regression where someone hardcodes
    ``Path("~/SecondBrain/cee/runs")`` instead of using
    ``paths.OBSIDIAN_RUNS_DIR``. The check excludes docstrings (which
    legitimately describe the vault layout in prose) by parsing the AST
    and only inspecting non-docstring string constants.
    """
    source = inspect.getsource(obsidian_module)
    tree = ast.parse(source)

    # Identify every node that is a docstring (first stmt of module /
    # function / class if it's a string Expr). Exclude those nodes from
    # the "is this a hardcoded literal in code?" check.
    docstring_constants: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(
            node,
            (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_constants.add(id(body[0].value))

    code_string_literals: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_constants
        ):
            code_string_literals.append(node.value)

    joined = "\n".join(code_string_literals)
    assert "SecondBrain" not in joined, (
        "obsidian.py contains a hardcoded 'SecondBrain' string in "
        "executable code — use paths.OBSIDIAN_* constants instead"
    )

    # Every required constant referenced (anywhere in source, including
    # docstrings — references in prose are fine; what matters is that
    # the code path actually uses them, which the other tests verify).
    for const in (
        "OBSIDIAN_VAULT",
        "OBSIDIAN_RUNS_DIR",
        "OBSIDIAN_SKILLS_DIR",
        "OBSIDIAN_AGENTS_DIR",
        "OBSIDIAN_BIBLE_DIR",
        "OBSIDIAN_AUDIT_DIR",
        "OBSIDIAN_TEMPLATES_DIR",
    ):
        assert const in source, f"obsidian.py must reference paths.{const}"


# ─── Frontmatter tests (bible 13 §5.7 schema for index notes, §5.1 meta) ─


def test_readme_has_type_meta_frontmatter(vault_root: Path) -> None:
    scaffold_obsidian()
    fm = _extract_frontmatter(_read(vault_root / "README.md"))
    assert fm == {"type": "meta"}


def test_runs_index_has_type_index_indexes_run(vault_root: Path) -> None:
    scaffold_obsidian()
    fm = _extract_frontmatter(_read(vault_root / "runs" / "index.md"))
    assert fm == {"type": "index", "indexes": "run"}


def test_skills_index_has_type_index_indexes_skill(vault_root: Path) -> None:
    scaffold_obsidian()
    fm = _extract_frontmatter(_read(vault_root / "skills" / "index.md"))
    assert fm == {"type": "index", "indexes": "skill"}


def test_agents_index_has_type_index_indexes_agent(vault_root: Path) -> None:
    scaffold_obsidian()
    fm = _extract_frontmatter(_read(vault_root / "agents" / "index.md"))
    assert fm == {"type": "index", "indexes": "agent"}


def test_bible_index_has_type_index_indexes_bible(vault_root: Path) -> None:
    scaffold_obsidian()
    fm = _extract_frontmatter(_read(vault_root / "bible" / "index.md"))
    assert fm == {"type": "index", "indexes": "bible"}


def test_audit_index_has_type_index_indexes_audit(vault_root: Path) -> None:
    scaffold_obsidian()
    fm = _extract_frontmatter(_read(vault_root / "audit" / "index.md"))
    assert fm == {"type": "index", "indexes": "audit"}


# ─── Bible-grounding ────────────────────────────────────────────────────


def test_scaffold_directory_set_matches_bible_section_5_1(
    vault_root: Path,
) -> None:
    """Parse bible 13 §5.1's tree and verify scaffold materialises the directory set.

    Per Halt 1 resolution: directories only. The five ``.md`` template
    files bible §5.1 lists inside ``_templates/`` ship with Phase 5+
    renderers; this test ignores files-inside-directories and asserts
    only that the *directory shape* matches.
    """
    bible_path = paths.BIBLE_DIR / "13_obsidian_integration.md"
    bible_text = bible_path.read_text(encoding="utf-8")

    # Locate §5.1 block: from "### 5.1" header to the next "###" header.
    match = re.search(
        r"### 5\.1[^\n]*\n(.*?)(?=\n### )",
        bible_text,
        flags=re.DOTALL,
    )
    assert match is not None, "bible 13 §5.1 block not found"
    block = match.group(1)

    # Extract first-level directory names: lines like "├── runs/" or
    # "└── _templates/", trimmed of tree-drawing characters and any
    # trailing comment. Exclude nested entries (deeper indent) and
    # files (no trailing slash).
    bible_dirs: set[str] = set()
    for line in block.splitlines():
        # First-level entries start with "├──" or "└──" (no nesting).
        token_match = re.match(
            r"^(?:├──|└──)\s+([A-Za-z_][A-Za-z0-9_]*)/",
            line.strip(),
        )
        if token_match is None:
            continue
        bible_dirs.add(token_match.group(1))

    expected = {"runs", "skills", "agents", "bible", "audit", "_templates"}
    assert bible_dirs == expected, (
        f"parsed bible §5.1 dirs {bible_dirs!r} do not match expected "
        f"{expected!r} — bible may have drifted or parser is wrong"
    )

    scaffold_obsidian()
    actual_dirs = {p.name for p in vault_root.iterdir() if p.is_dir()}
    assert actual_dirs == bible_dirs, (
        f"scaffold dirs {actual_dirs!r} != bible §5.1 dirs {bible_dirs!r}"
    )


# ─── No leakage outside the patched vault root ──────────────────────────


def test_scaffold_writes_only_under_obsidian_vault_root(
    vault_root: Path, tmp_path: Path,
) -> None:
    """No write occurs outside the patched ``OBSIDIAN_VAULT``.

    Creates a sibling file outside ``vault_root`` (but inside ``tmp_path``),
    runs scaffold, and asserts (a) the sibling is untouched, (b) every
    new path under ``tmp_path`` is either ``SecondBrain/`` (auto-created
    by ``ensure_dir``'s ``parents=True``) or under ``SecondBrain/cee/``.
    """
    sibling = tmp_path / "outside-vault.txt"
    sibling.write_text("untouched", encoding="utf-8")

    scaffold_obsidian()

    for path in tmp_path.rglob("*"):
        rel = str(path.relative_to(tmp_path))
        assert (
            rel == "outside-vault.txt"
            or rel == "SecondBrain"
            or rel.startswith("SecondBrain/cee")
        ), f"unexpected write outside vault: {rel}"

    assert sibling.read_text(encoding="utf-8") == "untouched"


# ─── _idempotent_write helper unit tests ────────────────────────────────


def test_idempotent_write_creates_when_missing(tmp_path: Path) -> None:
    target = tmp_path / "new.md"
    assert _idempotent_write(target, "hello") is True
    assert target.read_text(encoding="utf-8") == "hello"


def test_idempotent_write_skips_when_present_with_matching_content(
    tmp_path: Path,
) -> None:
    target = tmp_path / "exists.md"
    target.write_text("hello", encoding="utf-8")
    assert _idempotent_write(target, "hello") is False
    assert target.read_text(encoding="utf-8") == "hello"


def test_idempotent_write_preserves_when_present_with_different_content(
    tmp_path: Path,
) -> None:
    """The §5.10-vs-§EC3 conflict resolution at the helper level."""
    target = tmp_path / "operator-edited.md"
    target.write_text("OPERATOR edit", encoding="utf-8")
    assert _idempotent_write(target, "scaffold default") is False
    assert target.read_text(encoding="utf-8") == "OPERATOR edit"
