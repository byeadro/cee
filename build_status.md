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

**Effort:** L
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
8. **ExpectedAnswerType bible reconciliation.** Code declares 4 values (`yes_no | free_text | choice | number`) at `~/cee/schemas/clarification_request.py:41`. Bible 01 §11 declares 2 ("single-select or short-text"). T5 deferred this entry from the consistency-check registry (no canonical to assert against). Resolution: ratify code's 4-value enum into bible (likely amend bible 01 §11 or add a §X to bible 19 covering ClarificationRequest). Defer to: future bible-edit pass.
9. **MatchZone canonical formalization.** Bible 07 §5.2 declares the algorithm behavior (reuse / ask / generate via threshold logic) but never names the closed enum `MatchZone` with labeled values. Code at `~/cee/schemas/skill_set.py:28` derives the enum from the algorithm shape. T5 deferred this entry. Resolution: optionally add a labeled enum declaration to bible 07 §5.2 if T5 v2 should cover MatchZone validation. Defer to: future bible-edit pass.
10. **RawInput.source bible reconciliation.** Code declares 4 values (`cli | api | resume | replay`) at `~/cee/schemas/raw_input.py:64`. Bible 03 §5.2 Step 1 declares the field but never enumerates allowed values; the validation rule on line 65 only enumerates `target_executor`. T5 deferred this entry. Resolution: amend bible 03 §5.2 Step 1's validation line to add `source ∈ {cli, api, resume, replay}` as canonical. Defer to: future bible-edit pass.
11. **BootConsistencyError bible ratification.** T5 added `BootConsistencyError` as the 11th canonical CEE exception subclass (extends existing `BootError` in `~/cee/errors/exceptions.py`). Bible 19 §5.7 declares 10 canonical exception classes; the bible-grounding test `test_exception_classes_match_bible` continues to validate that 10-class set. T5 chose not to add `BootConsistencyError` to the test's expected set so the test stays bible-grounded rather than code-grounded. Resolution: amend bible 19 §5.7's exception hierarchy to ratify `BootConsistencyError` as an 11th canonical class, then update the test to assert 11 classes. Defer to: future bible-edit pass.
12. **Bible 04 §5.6 credentials_missing halt ratification.** T6 added `BootBibleSyncError(kind="credentials_missing")` for the case where `~/.cee/credentials.toml` lacks a populated `[anthropic]` section. The kind is inferred from bible 04 §5.2 (credentials.toml schema) + bible 04 §5.6 step 2 ("auth resolved" implicit prereq) but is not explicitly canonized in §5.6's failure-handling list. Resolution: amend bible 04 §5.6 to add "credentials missing" as a canonical halt cause. Defer to: future bible-edit pass.
13. **paths.py lazy-derivation refactor.** Currently `paths.BIBLE_SYNC_META = paths.BIBLE_DIR / ".sync_meta.json"` is computed at module-import time. This means tests that monkey-patch `paths.BIBLE_DIR` don't get the override propagated to derived paths. T6's `sync()` and `check_drift()` accept an optional `sync_meta_path` parameter as a workaround. A cleaner solution is to make derived paths lazy (functions or properties), so monkey-patching propagates uniformly. Resolution: refactor `paths.py` to compute derived paths via functions or properties. Surface area: low (a handful of derived constants); risk: low (callers don't depend on import-time computation). Defer to: Phase 5+ polish.
14. **cli/__main__.py for `python -m cli` invocation parity.** Phase 1 shipped `cli/main.py` + `cli/commands/<name>.py` with the `cee` console script registered in pyproject.toml as the canonical entry point. `python -m cli ...` doesn't work because there's no `cli/__main__.py`. Adding a one-line `from cli.main import main; main()` in `cli/__main__.py` would make both invocation paths work. Surface area: 1 new file, ~3 lines. Defer to: Phase 5+ polish.
15. **pyproject.toml `requires-python` floor aligned with stdlib `tomllib` requirement.** Phase 1 declared `requires-python = ">=3.10"` but production code paths import `tomllib` (stdlib 3.11+) via `boot.bible_sync` and `config_loader`. T8's B1 enforces the effective 3.11 floor at runtime; T8's commit also aligns pyproject.toml's declaration. Closed in this commit.
16. **`tomli_w` dependency audit.** T8 surfaced that no production code imports `tomli_w` (grep clean across `~/cee/`). If `tomli_w` appears in any historical dep list, it's removable. Surface area: low. Defer to: Phase 5+ dep cleanup pass.
17. **Bible 00 §12 line 391 wording — B8/B9 halt scope.** "If any step B1–B7 fails, CEE halts." T8 reads literally: B8 best-effort (warning, no halt), B9 success-only (cannot fail). Bible should canonize whether this wording is deliberate or a typo. Defer to: future bible-edit pass.
18. **Bible 04 §5.6 + bible 12 §5 audit event-name canonization.** T8 introduces 7 new boot.log event names (`boot_start`, `boot_complete`, `boot_halted`, `boot_step_start`, `boot_step_complete`, `boot_step_failed`, `b8_promotion_drain_warning`). Currently only `b2_drift_detected` is canonized. Bible should enumerate the boot-lifecycle event vocabulary. Defer to: future bible-edit pass.
19. **`BootBibleSyncErrorKind` `auto_sync_disabled` ratification.** T6's existing kind taxonomy was `mcp_connect_failed | page_deleted | credentials_missing`. T8 added a fourth: `auto_sync_disabled` for the bible 00 §12 B2 "else halts with instruction to run it manually" path. Bible 04 §5.6 implicitly canonizes the halt; the kind name is inferred. Surface for explicit canonization. Defer to: future bible-edit pass.
20. **B6 schema pre-compilation semantics + B7 Run-log directory naming convention.** Bible 00 §12 line 384 says "Pre-compile all Pydantic models from `~/cee/schemas/`" — T8 implements as module import (Pydantic class definition is the compile step). Bible 00 §12 line 386 names "last 50 Run logs" but doesn't canonize the Run directory regex. T8 picks reasonable patterns for both. Bible should canonize to keep T8 + Phase 4+ writers aligned. Defer to: future bible-edit pass.
21. **B8 promotion queue location + entry shape contract.** Bible 00 §12 line 387 names `promotion_queue.json` but doesn't canonize its location (T8 uses `paths.PROMOTION_QUEUE` per Phase 1) or the entry shape. Phase 3 prerequisite — `notion_writer.py` will need this canonized. Defer to: Phase 3 prep.
22. **Legacy `~/cee/bible/.sync_meta.json` cleanup.** Current file is in pre-T6 string-valued shape (page values are strings: `"mirrored"`, `"mirrored_abbreviated"`); T6's canonical `SyncMeta` schema requires `PageEntry` dicts. T6's `_load_sync_meta()` silently returns `None` and treats as "first sync." Functionally fine but the file should be regenerated or removed manually after first successful real sync (when concrete Notion MCP transport ships). Ops note. Defer to: post-concrete-transport sync.
23. **Bible 20 §5.2 line 148 `cee verify --boot` flag canonization.** Bible names the command verbatim. T9 implements as a flag on the existing `verify` subcommand (matches `--layout` / `--schemas` precedent from Phase 1). Closed in T9.
24. **`_BOOT_HALT_HINTS` remediation content belongs in bible 19 §5.6.** Bible 19 §5.6 names "the user-facing message format" with "To resume" exact CLI commands as canonical content. T9 ships the boot-halt remediation hint table inline as a Python constant in `cli/commands/verify.py` (13 entries keyed by `(error_class_name, kind)`). Long-term, the canonical content should live in bible 19 §5.6, with `verify.py` reading from a structured bible-grounded source. Surface area: medium (one new bible section + a loader). Defer to: post-T9 bible-edit pass + Phase 5+ refactor.
25. **Bible 20 §5.2 line 148 `cee verify --bible` flag canonization.** Bible names the command verbatim. T10 implements as a flag on the existing `verify` subcommand (matches `--layout` / `--schemas` / `--boot` precedent). Closed in T10.
26. **Bible 20 §5.2 line 152 vs current `cee verify` no-flag behavior.** Bible says "A clean shell can run `cee init` then `cee sync-bible` then `cee verify` without errors" — implies `cee verify` (no flag) should run all registered checks. Current CLI (Phase 1 + T9 + T10) requires explicit flags; no-flag → exit 2 with usage hint. Two resolution paths: (a) bible amendment to canonize `cee verify --all` per bible 20 §5.2 line 367/374 cross-refs, OR (b) implementation change so `cee verify` (no flag) defaults to running every registered check. T11 (Phase 2 gate) will likely invoke `cee verify --layout --schemas --boot --bible` explicitly to satisfy the gate criterion. Long-term resolution deferred. Surface for T11 prep + future bible-edit pass.
27. **`_BIBLE_DRIFT_HINTS` remediation content belongs in bible alongside `_BOOT_HALT_HINTS`.** T10 ships drift-category-keyed remediation hint table (4 entries: `notion_newer`, `mirror_modified`, `orphan`, `missing_from_meta`) inline as Python constant in `cli/commands/verify.py`. Same rationale as #24 for `_BOOT_HALT_HINTS` — drift-remediation content is canonical operator UX. Long-term, this content should live in bible (likely bible 04 §5.6 or bible 19 §5.6). Defer to: post-T9/T10 bible-edit pass (combined with #24).
28. **Bible 20 §5.3 lists `~/cee/persistence/audit.py` as a Phase 3 output, but it shipped in Phase 1.** Per Phase 1 close commit history, `persistence/audit.py` (atomic append + hash chain + `verify_audit_chain`) was a Phase 1 deliverable. Phase 3 inherits and uses it but produces no new audit.py work. Resolution: amend bible 20 §5.3 to mark `persistence/audit.py` as Phase 1 carry-over (not a Phase 3 output) and reference Phase 1's actual ship. Surface area: low. Defer to: future bible-edit pass.
29. **`cee verify --security` Phase 5+ deferral confirmation (cross-ref to Phase 1 carried-forward).** Bible 20 §5.3 names `cee verify --security` (permission checks) as a Phase 3 CLI output. Phase 1's "Carried-forward deferrals" list (line 283) defers `cee verify --security` to Phase 5+ co-deferred with security-event audit work. Phase 3 plan honors that deferral — no `--security` ships in T9/T10/T11. Resolution: amend bible 20 §5.3 to align (move `--security` to Phase 5+ output list) or document the cross-phase split-of-scope. Defer to: future bible-edit pass.
30. **Phase 3 monolithic vs split-phase decision record.** Bible 20 §5.3 bundles persistence (3 writers + audit) + safety gate (3 stages) + 3 CLI verbs into a single phase. AB resolved Q6 as monolithic — ship all of bible 20 §5.3 in one phase rather than splitting into Phase 3a (persistence) + Phase 3b (safety gate). Rationale: §5.3 gate criterion (d) `tests/integration/test_persistence_chain.py` couples both halves end-to-end; splitting would force a redundant intermediate gate. Resolution: no bible amendment needed; recorded here as the Phase 3 planning decision for future-AB reference. Closed in Phase 3 T1.

---

## Phase 3 — Persistence + Substrate Adapters + Safety Gate

**Scope:** Implement the three substrate writers (`filesystem_writer`, `obsidian_writer`, `notion_writer`), the three safety-gate stages (`redactor`, `injection_scanner`, `confirmation`), and the Phase 3 CLI surface (`cee verify --obsidian`, `cee audit-verify`, `cee scaffold-obsidian`). Per bible 20 §5.3 — every artifact type can be written to filesystem, mirrored to Obsidian, and queued for Notion promotion; every redaction + injection pattern from bible 12 §5 is enforced.

**Gate:** Phase 3 closes when (a) a test-fixture artifact round-trips through all three substrates (modulo redaction), (b) every bible 12 §5 redaction pattern + injection pattern is covered by passing tests, (c) the audit hash chain detects tampering, (d) `tests/integration/test_persistence_chain.py` passes end-to-end, (e) `pytest tests/unit/test_persistence/ tests/unit/test_safety_gate/` passes.

**Reference:** bible 20 §5.3 (Phase 3 outputs + gate criteria), bible 04 §10 (per-artifact write contract), bible 12 §5 (redaction + injection + confirmation taxonomy), bible 13 §5 (Obsidian vault layout).

**Carried-forward deferrals targeted in Phase 3:** none from Phase 1's list — Phase 3 strictly delivers bible 20 §5.3 outputs. `cee verify --security` stays Phase 5+ (paired with security-event audit work); Obsidian per-type renderers stay Phase 5+ (paired with first artifact production).

**Track structure:**

- **Track A — Persistence** (T2–T5): the three writers + the queue schema they share.
- **Track B — Safety gate** (T6–T8): redactor → injection scanner → confirmation, in pipeline order per bible 12 §5.
- **Track C — CLI + integration** (T9–T12): operator-facing verbs + the chain-level integration test fixture.
- **Track D — Gate** (T13): Phase 3 gate test mirroring Phase 2 Task 11 pattern.

### Tasks

#### Task 1 — Phase 3 task plan (this commit)

**Effort:** S
**Goal:** Land the Phase 3 task list, scope, and downstream-candidate updates so that subsequent tasks have a canonical reference.
**Reads:** `bible/20_production_build_plan.md` §5.3 (scope), `build_status.md` Phase 2 task list (pattern reference), Phase 2 close commit `635d003` (gate-passed state baseline).
**Writes:** `build_status.md` (Phase 3+ placeholder replaced with this section + #28–30 appended to downstream candidates).
**Bible cross-refs:** bible 20 §5.3.
**Checklist:**
- [x] Pre-flight: confirm `git status` clean, baseline test count = 1134 (Phase 2 gate state).
- [x] Read bible 20 §5.3 verbatim; capture outputs + gate criteria.
- [x] Mirror Phase 2 task structure (Goal / Reads / Writes / Bible cross-refs / Checklist / Verification per task).
- [x] Append three new downstream candidates (#28 audit.py shipped-in-Phase-1 note, #29 `--security` Phase 5+ confirmation, #30 monolithic vs split-phase decision record).
- [x] Commit: "Phase 3 task 1: task plan + scope + Track A/B/C/D structure."

**Verification:** `git diff HEAD~0 -- build_status.md` shows Phase 3 plan replacing the placeholder; downstream candidates renumbered through #30.

---

#### Task 2 — `PromotionQueueEntry` Pydantic schema

**Effort:** S
**Goal:** Implement the Pydantic model for entries in `~/cee/state/promotion_queue.json` (drained by boot step B8 per bible 00 §12, written by Task 5 `notion_writer`). Shared shape for Phase 3's notion_writer + Phase 5+ promotion-handling work.
**Reads:** `bible/04_database_file_structure.md` §6.x (state directory layout), `bible/00_project_vision.md` §12 B8 (drain semantics + entry shape implications), `boot/sequencer.py` (T8 of Phase 2 — current B8 stub references `paths.PROMOTION_QUEUE`), `schemas/sync_meta.py` (Phase 2 T1 — pattern reference for state-shape Pydantic models).
**Writes:** `schemas/promotion_queue_entry.py`, `schemas/__init__.py` (export added), `tests/unit/test_schemas/test_promotion_queue_entry.py`.
**Bible cross-refs:** bible 00 §12 B8 (drain spec), bible 04 §6.x (state file location), bible 02 §7.x (writer role authorization).
**Checklist:**
- [ ] Create `schemas/promotion_queue_entry.py` with `PromotionQueueEntry` model. `ConfigDict(extra="forbid", ...)`. `SCHEMA_VERSION: ClassVar[str] = "1.0.0"`. `produced_by: RoleEnum = RoleEnum.NOTION_WRITER`.
- [ ] Required fields (inferred from bible 00 §12 B8): `artifact_type` (closed enum: `run | skill | agent | bible_section | audit_summary`), `local_path` (relative to `~/cee/`), `enqueued_at` (ISO8601), `attempt_count` (int, default 0), `last_attempt_at` (ISO8601 | None), `last_error` (str | None).
- [ ] Add `PromotionQueueEntry` import + `__all__` entry in `schemas/__init__.py`.
- [ ] Write tests: round-trip serialization, `extra="forbid"` rejection, closed-enum rejection of unknown `artifact_type`, ISO timestamp validation.
- [ ] Confirm `cee verify --schemas` walks 17 schemas (16 from Phase 2 + `PromotionQueueEntry`).
- [ ] Surface as a downstream candidate if bible 04 §6.x doesn't enumerate the entry shape — Phase 3 ratifies.
- [ ] Commit: "Phase 3 task 2: PromotionQueueEntry schema + verify --schemas walks 17."

**Verification:** `pytest tests/unit/test_schemas/test_promotion_queue_entry.py` passes; `cee verify --schemas` exits 0 reporting 17 schemas.

---

#### Task 3 — `persistence/filesystem_writer.py`

**Effort:** L
**Goal:** Implement the role-aware filesystem writer per bible 04 §10 + bible 12 §5.10 hash-and-skip semantics. Writes go to `~/cee/runs/<run_id>/`, `~/cee/skills/<slug>/`, `~/cee/agents/<slug>.md`, `~/cee/bible_sections/` (per artifact type). Atomic via `persistence/atomic.py` (Phase 1).
**Reads:** `bible/04_database_file_structure.md` §10 (per-artifact write contract — primary), §5.10 (hash-and-skip), §6.x (run dir layout), `bible/12_prompt_leak_security_rules.md` §5.10 (idempotent-write invariant), `bible/02_user_roles.md` §7.x (FILESYSTEM_WRITER role authorization), `persistence/atomic.py` (Phase 1 — `atomic_write_text` / `atomic_write_json`), `persistence/audit.py` (Phase 1 — for emitting write events).
**Writes:** `persistence/filesystem_writer.py`, `tests/unit/test_persistence/test_filesystem_writer.py`.
**Bible cross-refs:** bible 04 §10, bible 04 §5.10, bible 12 §5.10, bible 02 §7.x.
**Checklist:**
- [ ] Create `persistence/filesystem_writer.py` exporting `write(artifact: BaseModel, *, run_id: str | None = None) -> WriteResult`. Dispatches on artifact type.
- [ ] Per-artifact path resolution: Run artifacts → `paths.RUNS_DIR / run_id / <artifact_name>.json`; Skill → `paths.SKILLS_DIR / slug / SKILL.md`; Agent → `paths.AGENTS_DIR / slug.md`; etc. Path resolution is data-driven from artifact type.
- [ ] Strict §5.10 hash-and-skip per Phase 1's deferral note: stub for Phase 3, full implementation deferred per existing carried-forward item. Phase 3 ships unconditional atomic write.
- [ ] Audit emission: every write emits a `filesystem_write` entry to `roles.log` (or per-Run audit log if `run_id` provided) via `persistence/audit.py`.
- [ ] Halt taxonomy: `FilesystemWriteError(kind="permission_denied" | "disk_full" | "path_outside_root")` — never overwrites outside `~/cee/`.
- [ ] Unit tests: per-artifact-type path resolution, atomic-write invariant (partial-write doesn't expose), audit emission shape, error kinds, refusal to write outside `~/cee/`.
- [ ] Commit: "Phase 3 task 3: persistence/filesystem_writer.py — role-aware atomic writes."

**Verification:** `pytest tests/unit/test_persistence/test_filesystem_writer.py` passes; `python -c "from persistence.filesystem_writer import write"` succeeds.

---

#### Task 4 — `persistence/obsidian_writer.py` (rename + extend)

**Effort:** M
**Goal:** Rename existing Phase 1 scaffold `persistence/obsidian.py` → `persistence/obsidian_writer.py` (per bible 20 §5.3 naming) and extend with the per-artifact dispatch shell. Per-type renderer bodies stay deferred per Phase 1 carried-forward; Phase 3 ships the dispatch + idempotent-write infrastructure.
**Reads:** `bible/20_production_build_plan.md` §5.3 (canonical name `obsidian_writer.py`), `bible/13_obsidian_vault_structure.md` §5 (vault layout + per-artifact target paths), `bible/04_database_file_structure.md` §10.10 (Obsidian-rebuild downstream relationship), `persistence/obsidian.py` (Phase 1 scaffold being renamed), `bible/12_prompt_leak_security_rules.md` §5.10 (idempotent-write invariant — applies to Obsidian too).
**Writes:** `persistence/obsidian_writer.py` (renamed + extended), `persistence/__init__.py` (export updated), `tests/unit/test_persistence/test_obsidian_writer.py` (renamed if exists), `git mv` for the rename.
**Bible cross-refs:** bible 20 §5.3, bible 13 §5, bible 04 §10.10, bible 12 §5.10.
**Checklist:**
- [ ] `git mv persistence/obsidian.py persistence/obsidian_writer.py`. Update import sites (likely zero since Phase 1 only scaffolded).
- [ ] Update `persistence/__init__.py` re-exports.
- [ ] Add `write(artifact: BaseModel) -> WriteResult` dispatch shell. Per-type renderer bodies raise `NotImplementedError("deferred per Phase 1 carried-forward")` for Phase 3.
- [ ] Per-type target-path resolution data-driven from artifact type, mapping to bible 13 §5 vault layout.
- [ ] Audit emission: every write emits an `obsidian_write` entry to `roles.log` via `persistence/audit.py`.
- [ ] Halt taxonomy: `ObsidianWriteError(kind="vault_not_found" | "permission_denied" | "renderer_not_implemented")`.
- [ ] Unit tests: rename verified (old import path errors), per-type path resolution returns the right target, `renderer_not_implemented` for each unrendered type, vault-missing halt.
- [ ] Commit: "Phase 3 task 4: persistence/obsidian_writer.py — rename + dispatch shell."

**Verification:** `pytest tests/unit/test_persistence/test_obsidian_writer.py` passes; `python -c "from persistence.obsidian_writer import write"` succeeds; old `persistence/obsidian` import path errors.

---

#### Task 5 — `persistence/notion_writer.py` (queue mechanics)

**Effort:** L
**Goal:** Implement the promotion-queue mechanics: enqueue artifacts to `~/cee/state/promotion_queue.json` for later drain by boot step B8. Concrete Notion MCP write transport is deferred (parallels bible 04 §5.6 deferral pattern from Phase 2 — concrete transport is post-Phase-3).
**Reads:** `bible/00_project_vision.md` §12 B8 (drain spec — primary), `bible/04_database_file_structure.md` §6.x (state file location), `schemas/promotion_queue_entry.py` (Task 2), `persistence/atomic.py` (Phase 1 — `atomic_write_json`), `boot/sequencer.py` (T8 of Phase 2 — current B8 best-effort stub), `bible/02_user_roles.md` §7.x (NOTION_WRITER role).
**Writes:** `persistence/notion_writer.py`, `tests/unit/test_persistence/test_notion_writer.py`.
**Bible cross-refs:** bible 00 §12 B8, bible 04 §6.x, bible 02 §7.x.
**Checklist:**
- [ ] Create `persistence/notion_writer.py` exporting `enqueue(artifact: BaseModel) -> EnqueueResult` and `drain(*, dry_run: bool = False) -> DrainResult`.
- [ ] `enqueue()`: read current queue (atomic), append `PromotionQueueEntry`, atomic-write back. Idempotent: re-enqueueing the same `local_path` updates `attempt_count` rather than appending duplicate.
- [ ] `drain()`: load queue, attempt to write each to Notion via `_write_to_notion(entry)`. Phase 3: `_write_to_notion` raises `NotImplementedError("concrete Notion MCP transport deferred")`. With `dry_run=True`, returns the queue contents without attempting any writes.
- [ ] B8 callable surface: `boot.sequencer._B8_drain_promotion_queue` should call `notion_writer.drain(dry_run=False)` and treat `NotImplementedError` as a graceful no-op (matches Phase 2 T8's best-effort B8 contract).
- [ ] Audit emission: enqueue emits `promotion_enqueued`; drain attempts emit `promotion_drain_attempt` (success or failure).
- [ ] Halt taxonomy: `NotionWriteError(kind="queue_corrupted" | "transport_not_implemented")` — both surface but only `queue_corrupted` halts B8.
- [ ] Unit tests: enqueue idempotency, queue round-trip, dry-run drain returns queue without writes, `NotImplementedError` graceful in drain, queue-corruption halt.
- [ ] Surface as downstream candidate: concrete Notion MCP transport ships post-Phase-3 (parallels bible 04 §5.6 deferral pattern).
- [ ] Commit: "Phase 3 task 5: persistence/notion_writer.py — queue mechanics (concrete transport deferred)."

**Verification:** `pytest tests/unit/test_persistence/test_notion_writer.py` passes; `boot/sequencer.py` B8 still passes (graceful drain).

---

#### Task 6 — `safety_gate/redactor.py`

**Effort:** L
**Goal:** Implement the redactor per bible 12 §5 — applies built-in redaction patterns + per-user redact_list. Pipeline-stage 1 of the safety gate. Outputs are redacted-in-place (string transform) before injection scanner runs.
**Reads:** `bible/12_prompt_leak_security_rules.md` §5 (redaction patterns + redact_list semantics — primary), `bible/12_prompt_leak_security_rules.md` §5.x (audit-emission contract for redactions), `bible/02_user_roles.md` §7.x (REDACTOR role), `safety_gate/__init__.py` (Phase 1 stub).
**Writes:** `safety_gate/redactor.py`, `tests/unit/test_safety_gate/test_redactor.py`.
**Bible cross-refs:** bible 12 §5 (full redaction taxonomy).
**Checklist:**
- [ ] Create `safety_gate/redactor.py` exporting `redact(text: str, *, user_redact_list: list[str] | None = None) -> RedactionResult`. `RedactionResult` carries the redacted text + per-pattern hit counts.
- [ ] Built-in patterns from bible 12 §5: API keys (sk-ant-, sk-, ghp_, etc.), email addresses, file paths under `/Users/`, IP addresses, JWT tokens, AWS access keys, etc. — enumerate every pattern bible 12 §5 names.
- [ ] User `redact_list`: literal-string list per `~/.cee/config.toml` `[redaction]` section. Applied after built-ins.
- [ ] Replacement format: `[REDACTED:<pattern_name>]` — deterministic so audit logs are diffable.
- [ ] Audit emission: every `redact()` call emits a `redaction_applied` entry to `roles.log` (via `persistence/audit.py`) with per-pattern hit counts.
- [ ] Halt taxonomy: redactor never halts on its own — silent-failure-allergic, every miss is a defect found via test, not a runtime error.
- [ ] Unit tests: one test per built-in pattern (every bible 12 §5 pattern), user-redact_list applied, replacement format invariant, hit-count accuracy, no-redaction-needed passthrough, audit emission shape.
- [ ] Commit: "Phase 3 task 6: safety_gate/redactor.py — bible 12 §5 patterns + user redact_list."

**Verification:** `pytest tests/unit/test_safety_gate/test_redactor.py` passes; bible 12 §5 enumerated patterns each have a passing test.

---

#### Task 7 — `safety_gate/injection_scanner.py`

**Effort:** L
**Goal:** Implement the injection scanner per bible 12 §5 — detects prompt-injection patterns in `RawInput` (per bible 12 §5.5, runs before the interpreter). Pipeline-stage 2 of the safety gate. Halts pipeline on detection; never silently suppresses.
**Reads:** `bible/12_prompt_leak_security_rules.md` §5 (injection patterns — primary), §5.5 (pre-interpreter ordering), `bible/03_raw_input.md` (RawInput shape being scanned), `bible/02_user_roles.md` §7.x (INJECTION_SCANNER role), `schemas/raw_input.py` (input target).
**Writes:** `safety_gate/injection_scanner.py`, `tests/unit/test_safety_gate/test_injection_scanner.py`.
**Bible cross-refs:** bible 12 §5, bible 12 §5.5, bible 03.
**Checklist:**
- [ ] Create `safety_gate/injection_scanner.py` exporting `scan(raw_input: RawInput) -> ScanResult`. `ScanResult` carries `clean: bool` + per-pattern hit list.
- [ ] Built-in patterns from bible 12 §5: "ignore previous instructions" variants, role-injection ("you are now"), system-prompt-leak attempts, tool-call-fabrication patterns, etc. — enumerate every pattern bible 12 §5 names.
- [ ] Halt taxonomy: `InjectionDetectedError(patterns: list[str])` — raised by `scan()` on any hit (never returns hits silently). Per bible 12 §5.5 the pipeline must halt before interpreter.
- [ ] Audit emission: `scan()` emits `injection_scan_complete` (clean) or `injection_scan_halted` (hit) to `roles.log`.
- [ ] Unit tests: one test per built-in pattern (every bible 12 §5 pattern), clean-input passthrough, halt on first hit, audit emission shape, multi-pattern detection.
- [ ] Commit: "Phase 3 task 7: safety_gate/injection_scanner.py — bible 12 §5 patterns."

**Verification:** `pytest tests/unit/test_safety_gate/test_injection_scanner.py` passes; bible 12 §5 enumerated injection patterns each have a passing test.

---

#### Task 8 — `safety_gate/confirmation.py`

**Effort:** M
**Goal:** Implement the destructive-operation confirmation gate per bible 12 §5 — interrupts pipeline before destructive writes/deletes/external sends, requires explicit operator confirmation. Pipeline-stage 3 of the safety gate.
**Reads:** `bible/12_prompt_leak_security_rules.md` §5 (confirmation taxonomy — what counts as destructive), `bible/02_user_roles.md` §7.x (CONFIRMATION_GATE role), `safety_gate/redactor.py` (T6 — pattern reference for safety_gate module shape).
**Writes:** `safety_gate/confirmation.py`, `tests/unit/test_safety_gate/test_confirmation.py`.
**Bible cross-refs:** bible 12 §5.
**Checklist:**
- [ ] Create `safety_gate/confirmation.py` exporting `confirm(action: DestructiveAction, *, prompt_fn: Callable[[str], str] = input) -> ConfirmationResult`. `prompt_fn` injectable for testing.
- [ ] `DestructiveAction` closed enum (frozen dataclass) per bible 12 §5: `delete_file | overwrite_existing | external_send | rm_rf | etc.` — enumerate every category bible 12 §5 names.
- [ ] Confirmation prompt format: structured CLI prompt naming the action, target path/recipient, and reversibility. Operator must type the literal target name to confirm (per bible 12 §5 "exact-match confirmation").
- [ ] Halt taxonomy: `ConfirmationDeclinedError(action, target)` — raised on operator decline. Pipeline must halt; never proceed on a "no" or empty answer.
- [ ] Audit emission: `confirmation_requested` (always), `confirmation_granted` (on yes), `confirmation_declined` (on no/empty) to `roles.log`.
- [ ] Unit tests: per-action-type prompt format, exact-match enforcement (typo → declined), audit emission shape (all three event types), declined-by-default invariant.
- [ ] Commit: "Phase 3 task 8: safety_gate/confirmation.py — destructive-operation gate."

**Verification:** `pytest tests/unit/test_safety_gate/test_confirmation.py` passes.

---

#### Task 9 — `cee verify --obsidian` subcommand

**Effort:** M
**Goal:** Add `cee verify --obsidian` per bible 20 §5.3 — read-only verification of `~/SecondBrain/cee/` vault structure against bible 13 §5 layout. No writes, no scaffolding (that's Task 11).
**Reads:** `bible/20_production_build_plan.md` §5.3 (CLI surface), `bible/13_obsidian_vault_structure.md` §5 (canonical layout), `cli/commands/verify.py` (Phase 2 pattern — `--layout` / `--schemas` / `--boot` / `--bible`), `persistence/obsidian_writer.py` (Task 4).
**Writes:** `cli/commands/verify.py` (extended with `_verify_obsidian()` + `--obsidian` flag), `cli/main.py` (flag registration), `tests/unit/test_cli/test_verify_command.py` (extended), `tests/unit/test_cli/test_main.py` (extended).
**Bible cross-refs:** bible 20 §5.3, bible 13 §5.
**Checklist:**
- [ ] Extend `cli/commands/verify.py` with `_verify_obsidian()` mirroring T9/T10 Phase 2 patterns (test seam + hint table).
- [ ] Per-directory existence checks against bible 13 §5 layout: `_runs/`, `_skills/`, `_agents/`, `_bible/`, `_audit/`, `_templates/`. Report missing as `MISSING`, present as `OK`.
- [ ] No-write invariant: this verb never creates or modifies vault paths. Use Task 11 (`cee scaffold-obsidian`) for that.
- [ ] Hint table `_OBSIDIAN_VERIFY_HINTS` keyed by missing-dir name → suggested remediation (e.g., "run `cee scaffold-obsidian` to create").
- [ ] Register `--obsidian` flag in `cli/main.py` `verify_parser` with help text citing bible 13 §5 + bible 20 §5.3.
- [ ] Tests (`test_verify_command.py`): all-present → exit 0, missing-dir → exit non-zero with hint, vault-missing → halt with explicit instruction. Tests (`test_main.py`): flag registration + help-text presence.
- [ ] Commit: "Phase 3 task 9: cee verify --obsidian — vault-layout verification."

**Verification:** `pytest tests/unit/test_cli/test_verify_command.py tests/unit/test_cli/test_main.py` passes; `cee verify --obsidian --help` shows the flag.

---

#### Task 10 — `cee audit-verify` subcommand

**Effort:** M
**Goal:** Add `cee audit-verify` per bible 20 §5.3 — verifies the hash chain of every audit log under `~/SecondBrain/cee/_audit/`. Detects tampering or corruption. Bible 12 §5.x defines the chain format; Phase 1 shipped `persistence/audit.py:verify_audit_chain()` which this verb wraps.
**Reads:** `bible/20_production_build_plan.md` §5.3 (CLI surface), `bible/12_prompt_leak_security_rules.md` §5.x (hash-chain spec), `persistence/audit.py` (Phase 1 — `verify_audit_chain()` is the load-bearing call), `cli/commands/verify.py` (Phase 2 pattern reference).
**Writes:** `cli/commands/audit_verify.py`, `cli/main.py` (subcommand registration), `tests/unit/test_cli/test_audit_verify.py`, `tests/unit/test_cli/test_main.py` (extended).
**Bible cross-refs:** bible 20 §5.3, bible 12 §5.x.
**Checklist:**
- [ ] Create `cli/commands/audit_verify.py` exporting `cmd_audit_verify(args) -> int`. New subcommand (not a flag on `verify` — bible 20 §5.3 names it as a separate verb).
- [ ] Walk `paths.AUDIT_DIR` for every `*.log` (cli.log, boot.log, roles.log + per-Run audit logs). For each, call `persistence.audit.verify_audit_chain(path)`. Aggregate results.
- [ ] Per-log report: `OK` (chain intact, line count) or `BROKEN` (broken-entry line numbers + tamper detail).
- [ ] Exit code: 0 if every log OK; 1 if any chain broken.
- [ ] Hint table for broken-chain remediation: which file, which line, what to inspect (audit logs are append-only — broken chain implies external tampering).
- [ ] Register `audit-verify` subparser in `cli/main.py` (mirrors `init` / `verify` / `sync-bible` registration pattern).
- [ ] Tests (`test_audit_verify.py`): all-clean → exit 0, planted broken chain → exit 1 with broken-line report, no audit logs (fresh state) → exit 0 with "no logs found" note.
- [ ] Commit: "Phase 3 task 10: cee audit-verify — hash-chain verification."

**Verification:** `pytest tests/unit/test_cli/test_audit_verify.py tests/unit/test_cli/test_main.py` passes; `cee audit-verify --help` shows the subcommand.

---

#### Task 11 — `cee scaffold-obsidian` subcommand

**Effort:** M
**Goal:** Add `cee scaffold-obsidian` per bible 20 §5.3 — creates the `~/SecondBrain/cee/` vault directory tree per bible 13 §5 layout. Idempotent (re-runnable). Operator-facing complement to `cee verify --obsidian`.
**Reads:** `bible/20_production_build_plan.md` §5.3 (CLI surface), `bible/13_obsidian_vault_structure.md` §5 (canonical layout), `cli/commands/init.py` (Phase 1 pattern reference for directory-creation idempotency).
**Writes:** `cli/commands/scaffold_obsidian.py`, `cli/main.py` (subcommand registration), `tests/unit/test_cli/test_scaffold_obsidian.py`, `tests/unit/test_cli/test_main.py` (extended).
**Bible cross-refs:** bible 20 §5.3, bible 13 §5.
**Checklist:**
- [ ] Create `cli/commands/scaffold_obsidian.py` exporting `cmd_scaffold_obsidian(args) -> int`.
- [ ] Per-directory `mkdir(parents=True, exist_ok=True)` for every bible 13 §5 vault subdir. Report each as `CREATED` (new) or `EXISTS` (idempotent).
- [ ] No `_templates/` content writes — that's Phase 5+ (existing carried-forward deferral).
- [ ] Audit emission: emit `scaffold_obsidian` entry to `cli.log` (subcommand was invoked) + per-dir `obsidian_dir_created` entries to `roles.log` for genuinely new dirs.
- [ ] Halt taxonomy: `ObsidianScaffoldError(kind="parent_not_writable" | "permission_denied")`.
- [ ] Exit code: 0 on success (created or already-exists); non-zero on halt.
- [ ] Register `scaffold-obsidian` subparser in `cli/main.py`.
- [ ] Tests: fresh-state → all CREATED, idempotent re-run → all EXISTS, parent-not-writable → halt, audit shape per scenario.
- [ ] Commit: "Phase 3 task 11: cee scaffold-obsidian — idempotent vault tree creation."

**Verification:** `pytest tests/unit/test_cli/test_scaffold_obsidian.py tests/unit/test_cli/test_main.py` passes; `cee scaffold-obsidian` creates the vault tree against fresh state.

---

#### Task 12 — `tests/integration/test_persistence_chain.py`

**Effort:** L
**Goal:** Build the integration-level fixture proving a single test artifact round-trips through all three substrates per bible 20 §5.3 gate criterion (a). Uses real `persistence/atomic.py`, `persistence/audit.py`, `persistence/filesystem_writer.py` (T3), `persistence/obsidian_writer.py` (T4 — dispatch shell only, renderers stay deferred), `persistence/notion_writer.py` (T5 — enqueue path only, transport stays deferred).
**Reads:** `bible/20_production_build_plan.md` §5.3 gate criterion (a), `bible/04_database_file_structure.md` §10 (per-artifact write contract), `tests/integration/test_phase2_gate.py` (Phase 2 T11 — pattern reference for integration-fixture style), `persistence/*.py` (Tasks 3–5).
**Writes:** `tests/integration/test_persistence_chain.py`.
**Bible cross-refs:** bible 20 §5.3 gate (a), bible 04 §10.
**Checklist:**
- [ ] Build `chain_env` fixture mirroring Phase 2 T11's `gate_env` pattern: monkeypatches `paths.HOME_DIR`, `paths.OBSIDIAN_VAULT_DIR`, etc. to a tmpdir-based isolated install. Calls `cee scaffold-obsidian` (T11) to set up vault.
- [ ] Test artifact: a fixture-grade `RawInput` instance (chosen because Phase 1 schema is stable + simple).
- [ ] Round-trip: `filesystem_writer.write(artifact)` → file exists at expected path with matching content; `obsidian_writer.write(artifact)` → expects the dispatch shell's `NotImplementedError("renderer deferred")` (asserted as expected for Phase 3); `notion_writer.enqueue(artifact)` → entry appears in `promotion_queue.json`.
- [ ] Audit chain: assert exactly one `filesystem_write` + one `promotion_enqueued` event in `roles.log` after the round-trip.
- [ ] Hash chain integrity: call `persistence.audit.verify_audit_chain(roles.log path)` → `(True, [])`.
- [ ] Tamper detection: planted-tamper test (modify a roles.log line, re-verify, expect broken-entry list).
- [ ] Commit: "Phase 3 task 12: persistence-chain integration fixture."

**Verification:** `pytest tests/integration/test_persistence_chain.py` passes.

---

#### Task 13 — Phase 3 gate

**Effort:** M
**Goal:** Confirm Phase 3 is complete per bible 20 §5.3 gate criteria. Mirrors Phase 2 Task 11 pattern. Drives a clean-state run through every Phase 3 surface and asserts the five gate criteria.
**Reads:** `bible/20_production_build_plan.md` §5.3 gate (a)–(e) — load-bearing, `build_status.md` (this file), all Tasks 1–12 outputs, `tests/integration/test_phase2_gate.py` (Phase 2 T11 — pattern reference).
**Writes:** `tests/integration/test_phase3_gate.py`, `build_status.md` (Phase 3 marked shipped with gate-passed timestamp + final test count + gate commit hash).
**Bible cross-refs:** bible 20 §5.3 (gate criteria), `tests/integration/test_phase2_gate.py` (Phase 2 pattern).
**Checklist:**
- [ ] `test_persistence_chain_artifact_roundtrip` — invokes T12's chain fixture, asserts gate criterion (a).
- [ ] `test_redaction_patterns_all_covered` — gate criterion (b1): asserts every bible 12 §5 redaction pattern has at least one passing test (introspect test output or pattern → test mapping).
- [ ] `test_injection_patterns_all_covered` — gate criterion (b2): asserts every bible 12 §5 injection pattern has at least one passing test.
- [ ] `test_audit_chain_detects_tampering` — gate criterion (c): plants a tamper, asserts `verify_audit_chain` reports broken.
- [ ] `test_persistence_unit_suite_passes` — gate criterion (d/e): subprocess-runs `pytest tests/unit/test_persistence/ tests/unit/test_safety_gate/` and asserts exit 0.
- [ ] Update `build_status.md`: Phase 3 status to "shipped" with gate-passed date + final test count + gate commit hash. Move any deferrals discovered during Phase 3 work into the carried-forward list with reasoning.
- [ ] Trigger downstream-candidate back-port pass (any §5.3 deferred items + bible reconciliations surfaced during T2–T12).
- [ ] Commit: "Phase 3 complete — gate passed."

**Verification:** Phase 3 gate per bible 20 §5.3 is satisfied: `pytest tests/integration/test_phase3_gate.py` passes; full test suite passes; gate criteria (a)–(e) all green.

---

## Phase 4+ (placeholder)

To be planned at Phase 3 close, following the same pattern as Phase 2 + Phase 3. Per bible 20: Phase 4 (Interpreter + Classifier), Phase 5 (Agents + Skills + Strategy), Phase 6 (Prompt Builder + Output Format + Grounding), Phase 7 (Pipeline Driver + Executor + Claude Code Integration), Phase 8 (Production Verification).
