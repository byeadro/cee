# CEE Build Status

> **Status:** Living document · **Owner:** AB · **Updated:** 2026-05-01
>
> Phase-by-phase task tracking for the CEE build. Phase 1 ships were tracked inline in `bible/21_first_action_tasks.md` §5.2; from Phase 2 forward, this file is canonical for task-level planning.

---

## Completed phases

### Phase 1 — Foundations (shipped)

Phase 1 gate passed 2026-04-30. Gate commit: `4c1a506`. Outcomes: 14 Pydantic schemas, atomic write helpers, audit log infrastructure with hash-chain, `cee init`, `cee verify --layout`, `cee verify --schemas`. 778 tests passing at gate, zero warnings, 18 commits on main. Tasks 1–16 detailed in `bible/21_first_action_tasks.md` §5.2.

#### Bible edits made during Phase 1

Cross-cutting bible changes made during Phase 1 task work (distinct from the systematic gap reconciliation that came after Phase 1):

- **bible 02 §4.2 + §7.13a + §8** — added `PIPELINE_DRIVER` as 13th system role.
- **bible 03 Step 6** — added `estimated_cost_tokens` field to `ExecutionStrategy`.
- **bible 06 §7.1** — `AgentPlan` flat-keyed dict → list-of-`AgentRef` + coordination string.
- **bible 17** — rewritten with full `FinalPrompt` XML for all 8 examples.

### Bible reconciliation — Phase 2 prep (shipped)

Four hard blockers from initial Phase 2 read closed before task planning:

| Gap | Subject | Commit |
|-----|---------|--------|
| 3 | `BOOT_SEQUENCER` authorization for bible mirror writes | `b1aae45` |
| 2 | `.sync_meta.json` schema in bible 04 §5.5 | `380f5c2` |
| 8 | `credentials.toml` schema in bible 04 §5.2 | `ec4597b` |
| 1 | `cee sync-bible` operational spec in bible 04 §5.6 | `8963612` |

---

## Phase 2 — Boot Sequence + Bible Sync

**Scope:** Implement boot sequencer B1–B9 (per bible 00 §12), `cee sync-bible` (per bible 04 §5.6), schema models for `SyncMeta` and `Credentials`, registry rebuilders (empty-catalog Phase 2 versions), cross-section consistency check, CLI verify extensions (`--bible`, `--boot`).

**Gate:** Phase 2 closes when all tasks below have shipped, full test suite passes, and the gate task's verification (Task 11) passes end-to-end.

**Reference:** bible 20 §5.2 (Phase 2 outputs + gate criteria), bible 00 §12 (B1–B9), bible 04 §5.6 (sync-bible operational spec).

### Tasks

#### Task 1 — `SyncMeta` Pydantic schema

**Effort:** S
**Goal:** Implement the Pydantic model for `~/cee/bible/.sync_meta.json` and wire it into the schema registry.
**Reads:** `bible/04_database_file_structure.md` §5.5 (schema spec), `schemas/__init__.py` (registry pattern), `schemas/raw_input.py` (convention reference).
**Writes:** `schemas/sync_meta.py`, `schemas/__init__.py` (export added), `tests/unit/test_schemas/test_sync_meta.py`.
**Bible cross-refs:** bible 04 §5.5 (canonical schema), bible 04 §6.1 (schema table — sync_meta.json row), bible 02 §7.13 (`produced_by: BOOT_SEQUENCER`).
**Checklist:**
- [ ] Create `schemas/sync_meta.py` with `SyncMeta` and per-page nested model. `ConfigDict(extra="forbid", ...)`. `SCHEMA_VERSION: ClassVar[str] = "1.0.0"`. `produced_by: RoleEnum = RoleEnum.BOOT_SEQUENCER`.
- [ ] Fields per §5.5: top-level `schema_version`, `produced_by`, `last_synced`, `pages: dict[str, PageEntry]`. `PageEntry`: `notion_page_id`, `notion_last_edited_time`, `local_path`, `content_sha256`.
- [ ] Add `SyncMeta` import + `__all__` entry in `schemas/__init__.py`.
- [ ] Write tests: round-trip serialization, `extra="forbid"` rejection, `RoleEnum.BOOT_SEQUENCER` default, sha256 pattern validation, ISO timestamp format.
- [ ] Confirm `cee verify --schemas` now reports 15 schemas (14 from Phase 1 + `SyncMeta`).
- [ ] Commit: "Phase 2 task 1: SyncMeta schema + verify --schemas walks 15."

**Verification:** `pytest tests/unit/test_schemas/test_sync_meta.py` passes; `cee verify --schemas` exits 0 and reports 15 schemas.

---

#### Task 2 — `Credentials` Pydantic schema

**Effort:** S
**Goal:** Implement the Pydantic model for `~/.cee/credentials.toml` and wire it into the schema registry.
**Reads:** `bible/04_database_file_structure.md` §5.2 (schema spec), `bible/14_claude_code_integration.md` §6.2 (authoritative bullet), `schemas/config.py` (TOML-loading convention reference).
**Writes:** `schemas/credentials.py`, `schemas/__init__.py` (export added), `tests/unit/test_schemas/test_credentials.py`.
**Bible cross-refs:** bible 04 §5.2 (canonical schema), bible 14 §6.2 (literal field), bible 14 §9 EC12 (failure mode).
**Checklist:**
- [ ] Create `schemas/credentials.py` with `Anthropic` nested model and top-level `Credentials` model. `ConfigDict(extra="forbid", ...)`. `SCHEMA_VERSION: ClassVar[str] = "1.0.0"`.
- [ ] `Anthropic`: `api_key: Annotated[str, Field(min_length=1, pattern=r"^sk-ant-")]`. `Credentials`: `anthropic: Anthropic | None = None` (optional in Phase 1; required by `APIExecutor` per EC12).
- [ ] Add `Credentials` import + `__all__` entry in `schemas/__init__.py`.
- [ ] Write tests: round-trip, `extra="forbid"`, `sk-ant-` prefix enforcement, `chmod 600` warning if file is world-readable (utility test, not schema test).
- [ ] Confirm `cee verify --schemas` now reports 16 schemas.
- [ ] Commit: "Phase 2 task 2: Credentials schema + verify --schemas walks 16."

**Verification:** `pytest tests/unit/test_schemas/test_credentials.py` passes; `cee verify --schemas` exits 0 and reports 16 schemas.

---

#### Task 3 — Skill registry rebuilder (empty-catalog)

**Effort:** S
**Goal:** Implement `rebuild() -> Index` for `~/cee/skills/` — walks the directory, parses `SKILL.md` frontmatter, writes `index.json`. Phase 2 catalog is empty; rebuilder must handle empty cleanly.
**Reads:** `bible/04_database_file_structure.md` §11 ("Index rebuild" build note), `bible/04_database_file_structure.md` §6.5 (registry shape), `bible/15_skill_file_structure.md` (frontmatter contract), `bible/00_project_vision.md` §12 B4 (boot caller).
**Writes:** `skill_engine/registry.py`, `tests/unit/test_skill_engine/test_registry.py`.
**Bible cross-refs:** bible 04 §11 ("Index rebuild"), bible 04 §6.5 (registry format), bible 00 §12 B4 (boot integration), bible 20 §5.2 (Phase 2 output).
**Checklist:**
- [ ] Create `skill_engine/registry.py` exporting `rebuild(skills_dir: Path = paths.SKILLS_DIR) -> list[dict]`.
- [ ] Walk `skills_dir` for `<slug>/SKILL.md`. Parse frontmatter via `python-frontmatter`. Validate against `schemas.SkillFrontmatter`. Skip + log invalid entries (don't halt — per bible 00 §12 B4).
- [ ] Write `<skills_dir>/index.json` atomically via `atomic_write_json`. Format: flat array of `{"slug", "path", "version", "frontmatter"}` per §6.5.
- [ ] Empty-catalog test: rebuild against empty dir produces `[]`.
- [ ] Invalid-frontmatter test: confirms log + skip behavior.
- [ ] Atomic write test: in-progress write doesn't expose partial file.
- [ ] Commit: "Phase 2 task 3: skill_engine registry rebuilder (empty-catalog)."

**Verification:** `pytest tests/unit/test_skill_engine/test_registry.py` passes; `python -c "from skill_engine.registry import rebuild; print(rebuild())"` returns `[]` against the empty Phase 2 catalog.

---

#### Task 4 — Agent registry rebuilder (empty-catalog)

**Effort:** S
**Goal:** Implement `rebuild() -> Index` for `~/cee/.claude/agents/` — same shape as Task 3 but for agents.
**Reads:** `bible/04_database_file_structure.md` §11 + §6.5, `bible/16_agent_file_structure.md` (frontmatter contract), `bible/00_project_vision.md` §12 B5 (boot caller), `skill_engine/registry.py` (Task 3 — pattern reference).
**Writes:** `agent_selector/registry.py`, `tests/unit/test_agent_selector/test_registry.py`.
**Bible cross-refs:** bible 04 §11, bible 04 §6.5, bible 00 §12 B5, bible 20 §5.2.
**Checklist:**
- [ ] Create `agent_selector/registry.py` exporting `rebuild(agents_dir: Path = paths.AGENTS_DIR) -> list[dict]`.
- [ ] Walk `agents_dir` for `<slug>.md`. Parse frontmatter. Validate against `schemas.AgentFrontmatter`. Skip + log invalid entries.
- [ ] Write `<agents_dir>/index.json` atomically. Same record shape as Task 3.
- [ ] Tests: empty-catalog returns `[]`, invalid frontmatter logs+skips, atomic write invariant.
- [ ] Commit: "Phase 2 task 4: agent_selector registry rebuilder (empty-catalog)."

**Verification:** `pytest tests/unit/test_agent_selector/test_registry.py` passes; rebuild against empty Phase 2 catalog returns `[]`.

---

#### Task 5 — Cross-section consistency check

**Effort:** M
**Goal:** Implement the closed-enum cross-reference validator that asserts enum values referenced in bible sections match the canonical Python `Enum` definitions and schema literal types. Required by boot step B3.
**Reads:** `bible/00_project_vision.md` §12 B3 (spec), `bible/08_task_classification_engine.md` (canonical `task_type` enum reference), `roles/__init__.py` (`RoleEnum`), `schemas/*.py` (`Literal[...]` definitions across schemas), bible files for cross-section enum mentions.
**Writes:** `boot/consistency.py`, `tests/unit/test_boot/test_consistency.py`, `tests/integration/test_consistency_drift.py`.
**Bible cross-refs:** bible 00 §12 B3, bible 20 §5.2 (Phase 2 output + gate criterion), bible 08 (`task_type` enum source).
**Checklist:**
- [ ] Create `boot/consistency.py` exporting `check() -> ConsistencyReport`.
- [ ] Define authoritative enum sources: `RoleEnum` (roles), `Literal[...]` types in schemas (e.g., `task_type` in `Classification`, `source` in `RawInput`, `target_executor` in `RawInput`/`ExecutionStrategy`).
- [ ] For each enum, scan referenced bible sections (configured in `paths.py` or hardcoded list) for the enum's values; assert presence/match.
- [ ] Halt with structured `ConsistencyError` on any drift. Report includes: enum name, expected values, bible section, mismatch description.
- [ ] Unit tests: synthetic bible+schema fixtures pass and fail correctly.
- [ ] Integration test: `tests/integration/test_consistency_drift.py` deliberately introduces an enum mismatch in a fixture-bible and asserts `check()` halts.
- [ ] Commit: "Phase 2 task 5: cross-section consistency check (B3)."

**Verification:** `pytest tests/unit/test_boot/test_consistency.py tests/integration/test_consistency_drift.py` passes; `python -c "from boot.consistency import check; print(check().ok)"` returns `True` against the current bible state.

---

#### Task 6 — `boot/bible_sync.py` (`cee sync-bible` implementation)

**Effort:** L
**Goal:** Implement the Notion-to-filesystem bible sync per bible 04 §5.6. Reads credentials, connects to Notion MCP, fetches pages, normalizes to markdown, writes atomically, updates `.sync_meta.json` last, logs to three audit logs (Path α split).
**Reads:** `bible/04_database_file_structure.md` §5.6 (operational spec), §5.5 (`.sync_meta.json` schema), §5.2 (`credentials.toml` schema + `notion_bible_root_id`), `bible/02_user_roles.md` §7.13 (BOOT_SEQUENCER write surface), `bible/12_prompt_leak_security_rules.md` §5.8 (audit log structure), `schemas/sync_meta.py` (Task 1), `schemas/credentials.py` (Task 2), `persistence/atomic.py` (atomic_write_text).
**Writes:** `boot/bible_sync.py`, `tests/unit/test_boot/test_bible_sync.py`, `tests/integration/test_bible_sync_e2e.py`.
**Bible cross-refs:** bible 04 §5.6 (full operational spec — primary), bible 04 §5.5 (.sync_meta schema), bible 04 §5.2 (credentials + notion_bible_root_id), bible 02 §7.13 (write surface), bible 12 §5.8 (audit format), bible 03 Rule 6 (last_synced timestamp captured at start), bible 04 §9 EC9 (deleted-page halt).
**Checklist:**
- [ ] Create `boot/bible_sync.py` exporting `run(trigger: Literal["boot_auto", "cli_manual"]) -> SyncResult` and `check_drift() -> DriftReport` (read-only helper for Task 10).
- [ ] Step 1: load `Credentials` from `~/.cee/credentials.toml` per Task 2.
- [ ] Step 2: connect to Notion MCP. Halt before any page fetch on connection failure (audit `sync_bible_start` not written; halt log written to `roles.log` separately).
- [ ] Step 3: fetch parent page (`notion_bible_root_id` from config), enumerate children.
- [ ] Step 4: capture `last_synced` once at start (per bible 03 Rule 6 — applied by analogy).
- [ ] Step 5: per-child loop. Compare `last_edited_time` to local `.sync_meta.json` entry. On drift or missing entry, fetch + normalize + atomic-write + recompute `content_sha256` + update in-memory metadata. On match, skip.
- [ ] Step 6: atomic-write updated `.sync_meta.json` last (consistency invariant).
- [ ] Step 7: emit audit entries to three logs per Path α — `cli.log` (manual only), `boot.log` (boot only), `roles.log` (always; `sync_bible_start`/`sync_bible_page_synced`/`sync_bible_page_failed`/`sync_bible_end`).
- [ ] Failure handling: per-page partial-with-warning per §5.6. Initial-MCP-failure halts before any page touched. EC9 (page deleted) halts with restore instruction.
- [ ] Stub `_normalize_notion_to_markdown(page) -> str` with minimal block-type coverage; full normalization rules deferred per §5.6.
- [ ] Unit tests: per-step mocked tests, audit-log entry shape, partial-failure handling, EC9 halt path.
- [ ] Integration test: end-to-end against a recorded Notion fixture (no live MCP); asserts mirror state + .sync_meta.json shape + three-log audit trail.
- [ ] Commit: "Phase 2 task 6: boot/bible_sync.py — cee sync-bible per bible 04 §5.6."

**Verification:** `pytest tests/unit/test_boot/test_bible_sync.py tests/integration/test_bible_sync_e2e.py` passes; integration test produces exactly the audit-log entries enumerated in bible 04 §5.6.

---

#### Task 7 — `cee sync-bible` CLI subcommand

**Effort:** S
**Goal:** Wire the `cee sync-bible` CLI entry point to `boot/bible_sync.py:run`. Manual-trigger path; emits `cli_invoke` audit entry per §5.6.
**Reads:** `bible/04_database_file_structure.md` §5.6 (CLI invocation path), `bible/00_project_vision.md` §11 line 361 (CLI surface listing), `cli/commands/init.py` + `cli/commands/verify.py` (Phase 1 CLI pattern reference), `boot/bible_sync.py` (Task 6).
**Writes:** `cli/commands/sync_bible.py`, `cli/__init__.py` (subcommand registration), `tests/integration/test_cli_sync_bible.py`.
**Bible cross-refs:** bible 04 §5.6 (CLI manual invocation path), bible 00 §11 (CLI surface), bible 21 line 514 (Phase 2 sync-bible reference).
**Checklist:**
- [ ] Create `cli/commands/sync_bible.py` with `cmd_sync_bible(args) -> int`. Calls `boot.bible_sync.run(trigger="cli_manual")`.
- [ ] Register subcommand in `cli/__init__.py`. Help text matches bible 00 line 361 phrasing.
- [ ] Emit `cli_invoke` entry to `cli.log` per §5.6 (this happens via the existing CLI dispatcher's pre-call wrapper if Phase 1 already does it; otherwise add here).
- [ ] Exit code: 0 on full success, 1 on partial-with-warning, 2 on initial-MCP-failure halt or EC9 halt.
- [ ] Integration test: invokes CLI via `subprocess`, asserts exit code + cli.log entry + roles.log entries.
- [ ] Commit: "Phase 2 task 7: cee sync-bible CLI subcommand."

**Verification:** `cee sync-bible --help` shows the subcommand; `pytest tests/integration/test_cli_sync_bible.py` passes.

---

#### Task 8 — `boot/sequencer.py` (B1–B9)

**Effort:** L
**Goal:** Implement the boot sequence per bible 00 §12. B1 verify environment, B2 load bible (calls Task 6 on drift if `auto_sync = true`), B3 cross-section consistency (calls Task 5), B4 skill registry (calls Task 3), B5 agent registry (calls Task 4), B6 load schemas, B7 load recent runs (stub — Run pipeline lands Phase 7), B8 drain promotion queue (stub — promotion lands Phase 5+), B9 ready.
**Reads:** `bible/00_project_vision.md` §12 (B1–B9 spec), `bible/04_database_file_structure.md` §5.6 (B2 trigger logic), `bible/12_prompt_leak_security_rules.md` §5.8 (boot.log format), `schemas/__init__.py`, `boot/bible_sync.py` (Task 6), `boot/consistency.py` (Task 5), `skill_engine/registry.py` (Task 3), `agent_selector/registry.py` (Task 4), `schemas/sync_meta.py` (Task 1), `schemas/config.py`.
**Writes:** `boot/sequencer.py`, `tests/unit/test_boot/test_sequencer.py`, `tests/integration/test_boot_sequence.py`.
**Bible cross-refs:** bible 00 §12 (full B1–B9), bible 04 §5.6 (B2 trigger), bible 02 §7.13 (BOOT_SEQUENCER reads/writes), bible 20 §5.2 (Phase 2 output + gate criterion).
**Checklist:**
- [ ] Create `boot/sequencer.py` exporting `run() -> BootResult`.
- [ ] B1: verify python version, package presence, write permissions on `~/cee/` + `~/SecondBrain/cee/`. Halt on failure with explicit chmod/install instruction.
- [ ] B2: read `~/cee/bible/.sync_meta.json`. If missing or any per-page `notion_last_edited_time` older than live Notion (and `auto_sync = true` per config), invoke `boot.bible_sync.run(trigger="boot_auto")`. Else halt with instruction. Emit `b2_drift_detected` to `boot.log` if drift found.
- [ ] B3: invoke `boot.consistency.check()`. Halt on failure.
- [ ] B4: invoke `skill_engine.registry.rebuild()`. Empty-catalog OK.
- [ ] B5: invoke `agent_selector.registry.rebuild()`. Empty-catalog OK.
- [ ] B6: pre-compile all Pydantic models via `schemas.__init__.py` walk.
- [ ] B7: stub — `pass` with `boot.log` entry noting "B7 stub (Phase 7 work)".
- [ ] B8: stub — `pass` with `boot.log` entry noting "B8 stub (Phase 5+ work)".
- [ ] B9: emit `boot.log` "boot ready" entry; return success.
- [ ] All-or-nothing semantics per §12: any B1–B7 failure halts (B8 stays soft per spec wording, but stub means no-op).
- [ ] Each step writes a structured entry to `boot.log` (start/end + result).
- [ ] Unit tests: per-step mocked, halt paths, audit emission shape.
- [ ] Integration test (`test_boot_sequence.py` per bible 20 §5.2 gate): from clean state, full B1–B9 completes successfully; asserts each step's boot.log entry; asserts indexes rebuilt.
- [ ] Commit: "Phase 2 task 8: boot/sequencer.py — B1–B9."

**Verification:** `pytest tests/unit/test_boot/test_sequencer.py tests/integration/test_boot_sequence.py` passes; `python -c "from boot.sequencer import run; r = run(); assert r.ok"` succeeds against the clean Phase 2 state.

---

#### Task 9 — `cee verify --boot` subcommand

**Effort:** M
**Goal:** Add `cee verify --boot` per bible 20 §5.2 — invokes the boot sequencer (Task 8) from a clean state and asserts all B1–B9 steps complete, surfacing any halt with structured output.
**Reads:** `bible/20_production_build_plan.md` §5.2 (gate criterion), `bible/00_project_vision.md` §12 (B1–B9), `cli/commands/verify.py` (existing `--layout` + `--schemas` pattern), `boot/sequencer.py` (Task 8).
**Writes:** `cli/commands/verify.py` (extended), `tests/integration/test_cli_verify_boot.py`.
**Bible cross-refs:** bible 20 §5.2 (Phase 2 output), bible 00 §12 (boot spec).
**Checklist:**
- [ ] Extend `cli/commands/verify.py` with `--boot` flag handler. Calls `boot.sequencer.run()`, captures `BootResult`.
- [ ] Print structured per-step report (B1 ✓ / B2 ✓ / ... / B9 ✓). On failure, print which step halted + the halt's structured payload.
- [ ] Exit code: 0 on full success; 1 on any halt.
- [ ] Integration test: clean state → exit 0; injected B3-failure (planted enum drift) → exit 1 + structured B3 message.
- [ ] Update help text and the `cli/commands/verify.py:46` docstring to include `--boot`.
- [ ] Commit: "Phase 2 task 9: cee verify --boot."

**Verification:** `cee verify --boot` against clean Phase 2 state exits 0; `pytest tests/integration/test_cli_verify_boot.py` passes.

---

#### Task 10 — `cee verify --bible` subcommand

**Effort:** M
**Goal:** Add `cee verify --bible` per bible 20 §5.2 (and promoted from Phase 1's Path B deferral list). Read-only counterpart to `cee sync-bible`: contacts Notion MCP, compares per-page `notion_last_edited_time` against `.sync_meta.json`, reports drift without writing. Exit non-zero if drift detected.
**Reads:** `bible/20_production_build_plan.md` §5.2, `bible/04_database_file_structure.md` §5.6 (drift-detection logic), `bible/04_database_file_structure.md` §5.5 (.sync_meta schema), `cli/commands/verify.py` (existing pattern), `boot/bible_sync.py` (Task 6 — `check_drift()` helper exposed as part of Task 6).
**Writes:** `cli/commands/verify.py` (extended), `tests/integration/test_cli_verify_bible.py`.
**Bible cross-refs:** bible 20 §5.2 (Phase 2 output), bible 04 §5.6 (drift-check logic), bible 04 §9 EC8 (drift detection).
**Checklist:**
- [ ] Extend `cli/commands/verify.py` with `--bible` flag handler. Calls `boot.bible_sync.check_drift()`, prints per-page drift status (`in_sync` / `notion_newer` / `mirror_orphan` / `missing_from_meta`).
- [ ] Mirror-side drift via `content_sha256` recomputation: if local file's sha256 ≠ recorded, flag `mirror_modified` per §5.6 mirror-side drift bullet.
- [ ] Read-only — no atomic writes, no `.sync_meta.json` updates, no audit-log entries (since this is verification, not action).
- [ ] Exit code: 0 on no drift, 1 on Notion-side drift, 2 on mirror-side drift, 3 on connection failure.
- [ ] Integration test: clean state (no drift) → exit 0; planted Notion drift → exit 1; planted local-edit drift → exit 2.
- [ ] Update help text and the `cli/commands/verify.py:46` docstring to include `--bible`.
- [ ] Commit: "Phase 2 task 10: cee verify --bible (Path B deferral promoted)."

**Verification:** `cee verify --bible` exits 0 against clean state; `pytest tests/integration/test_cli_verify_bible.py` passes.

---

#### Task 11 — Phase 2 gate

**Effort:** M
**Goal:** Confirm Phase 2 is complete per bible 20 §5.2 gate criteria: clean shell can run `cee init` + `cee sync-bible` + all `cee verify` subcommands without errors; `tests/integration/test_boot_sequence.py` passes; consistency check rejects deliberate enum mismatch.
**Reads:** `bible/20_production_build_plan.md` §5.2 (gate criteria — load-bearing), `build_status.md` (this file — Phase 2 task list), all Tasks 1–10 outputs.
**Writes:** `build_status.md` (Phase 2 marked complete with gate-passed timestamp), `tests/integration/test_phase2_gate.py`, gate commit.
**Bible cross-refs:** bible 20 §5.2 (gate criteria), bible 21 §5.2 Task 16 (pattern reference).
**Checklist:**
- [ ] From clean shell (or fresh test fixture), run sequence: `cee init` → `cee sync-bible` → `cee verify --layout` → `cee verify --schemas` → `cee verify --bible` → `cee verify --boot`. Assert each exits 0.
- [ ] Run `pytest tests/` end-to-end. Assert all pass; record total count (expect ≥ 778 + Phase 2 additions).
- [ ] Run consistency-drift integration test (Task 5's deliberate-mismatch scenario). Assert it halts as expected.
- [ ] Update `build_status.md`: Phase 2 status to "shipped" with gate-passed date and final test count. Move any remaining Phase-2 tickets to Phase 3+ if they slipped.
- [ ] Update Phase 1's "Carried-forward deferrals" if any Phase 5/6+ items got reclassified.
- [ ] Trigger downstream reconciliation back-port pass (gap-1 deferred §5.6 items: normalization, mirror-side drift UX, retry policy, rate-limit handling). Spec back-ports at this gate per gap-1 commit body.
- [ ] Commit: "Phase 2 complete — gate passed."

**Verification:** Phase 2 gate per bible 20 §5.2 is satisfied: `cee init && cee sync-bible && cee verify --layout && cee verify --schemas && cee verify --bible && cee verify --boot` exits 0 in sequence; `pytest tests/integration/test_phase2_gate.py` passes; full test suite passes.

---

## Carried-forward deferrals

Items deferred during Phase 1 task work, targeting Phase 5/6+. Each preserves the existing build_status.md classification.

- **Obsidian renderers** (run / skill / agent / bible_section / audit_summary). Defer to: Phase 5+. The Obsidian writer was scaffolded (Path B); per-type rendering bodies are deferred until the source artifacts exist.
- **Obsidian `_templates/` contents.** Defer to: Phase 5+. Co-deferred with the renderers above.
- **Audit log security-event-specific writers.** Defer to: Phase 5+. The audit infrastructure ships in Phase 1; security-event taxonomy lands with Phase 5+ security work.
- **Strict §5.10 hash-and-skip per-Run writer.** Defer to: Phase 5+. The atomic write helper ships in Phase 1; per-Run skip-on-hash-match optimization is a Phase 5+ refinement.
- **`cee verify --security`** (permission checks). Defer to: Phase 5+. Co-deferred with security-event audit work.
- **`CLAUDE.md` generation.** Defer to: Phase 6+. Per bible 14 §5.8 (`cee sync-claude-md`); part of the Claude Code integration phase.
- **Slash commands and hooks installation.** Defer to: Phase 6+. Per bible 14 §5.3 + §5.4; co-shipped with `CLAUDE.md`.

(Path B deferral promoted to Phase 2: `cee verify --bible` — now Task 10.)

---

## Downstream reconciliation candidates

Bible reconciliations surfaced during Phase 2 prep (commit `8963612`'s body). Distinct in provenance from Carried-forward deferrals — these are bible-side cleanups, not implementation deferrals.

1. **Bible 13 §5.5 line 273 phrasing.** Loose "rewritten on every `cee sync-bible`" needs tightening to reflect Path I (Obsidian rebuild is downstream by `OBSIDIAN_WRITER` per bible 04 §10.10, not by sync-bible directly). Defer to: next bible-edit pass.
2. **`updated_at` vs `notion_last_edited_time` terminology drift** in bibles 00 §12 + bible 01 line 363. Gap-2 canon uses `notion_last_edited_time`; bibles 00/01 should align. Defer to: next bible-edit pass.
3. **`auto_sync = true` (TOML) vs `auto_sync: true` (colon) drift** in bible 04 §9 EC8 + bible 00 §12 line 376. §5.2 + §5.5 canon uses TOML form; colon-form references should align. Defer to: next bible-edit pass.
4. **Bible 02 §7.13 could optionally back-ref bible 04 §5.6** for sync-bible operational details. Defer to: next bible-edit pass; optional polish.
5. **Bible 03 Rule 6 scope** could broaden to cover boot-time external reads (sync-bible's `last_synced` capture), not just `RawInput.timestamp`. Defer to: next bible-edit pass; principle generalization.
6. **Phase 2 close back-ports four §5.6 deferred items**: Notion-block-to-markdown normalization rules, mirror-side drift UX (halt-and-ask vs. force-overwrite), retry policy with exponential backoff, rate-limit handling. Defer to: Phase 2 gate (Task 11 trigger).
7. **Bible 06 §5.2.1 ↔ Bible 16 §5.2 `AgentFrontmatter` contract drift.** Bible 06 specifies 7 required + 4 optional fields with `created_by_run` ∈ {run_id, manual}. Bible 16 specifies 9 required + 11 optional fields with `created_by_run` ∈ {run_id, manual, seed}. Phase 1's `AgentFrontmatter` schema follows bible 06 (commit history). Empty-catalog Phase 2 work is unaffected; Phase 5 seed-agent work (12-agent seed catalog) requires reconciliation first — pick the canonical bible, align the other, update the schema. Defer to: Phase 5 prep.

---

## Phase 3+ (placeholder)

To be planned at Phase 2 close, following the same pattern as this Phase 2 section. Per bible 20: Phase 3 (Persistence + Substrate Adapters), Phase 4 (Interpreter + Classifier), Phase 5 (Agents + Skills + Strategy), Phase 6 (Prompt Builder + Output Format + Grounding), Phase 7 (Pipeline Driver + Executor + Claude Code Integration), Phase 8 (Production Verification).
