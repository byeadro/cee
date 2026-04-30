---
notion_section: 20
notion_title: 20 — PRODUCTION BUILD PLAN
mirrored_at: 2026-04-30
---

# 20 — PRODUCTION BUILD PLAN

> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the dependency-ordered build sequence that takes CEE from empty filesystem to a fully complete, production-ready system. There is no MVP. There is no "we'll add this later." Every section 00–19 is implemented, tested, and verified before CEE is considered done. This page is the order in which that happens, the gates between phases, and the verification at each gate.

---

## 1. What This Is

A complete, dependency-ordered build sequence for CEE. Eight phases. Each phase has:

- **Inputs** — what must exist before the phase starts
- **Outputs** — what the phase produces
- **Gate** — the verification that proves the phase is complete
- **Dependencies** — which prior phases this phase requires
- **Risk profile** — what's likely to go wrong and how to recover

The phases are not weekly milestones. They are dependency layers. A phase completes when its gate passes, regardless of calendar time. Phases can overlap where their dependencies don't conflict.

This page is the build sequence; section 21 is the day-one action list distilled from this sequence's first phase.

---

## 2. Why This Matters

Without this page:

- The natural impulse is to build the most exciting parts first (the agents, the prompt builder), bypassing the foundation.
- Modules end up half-implemented because their dependencies weren't ready.
- "We'll write tests later" becomes "we never write tests."
- The build feels chaotic; progress is ambiguous.

With this page:

- Each phase has a clear gate. Past the gate, that part of CEE is done.
- The build sequence is forced by dependencies, not preferences.
- Tests are inseparable from each phase — no phase completes without its tests passing.
- Progress is unambiguous: count phases passed.

---

## 3. Core Requirements

The build plan MUST:

1. Sequence phases by dependency, not by interest.
2. Make every phase end at a verifiable gate.
3. Treat tests as integral to each phase — every phase produces tests, not just code.
4. Preserve the option to do work in parallel where dependencies allow.
5. Produce a fully complete system at the end of phase 8 — every section 00–19 is implemented and verified.
6. Ensure the bible itself stays the source of truth — implementation follows bible, not reverse.
7. Identify the highest-risk phases and allocate buffer accordingly.

The build plan MUST NOT:

- Defer "polish" to a later release. There is no later release.
- Mark a phase complete because the code "mostly works." Gates are pass/fail.
- Allow phase N+1 work to compensate for incomplete phase N work.
- Treat documentation as separate from code. Every phase updates the relevant bible section if implementation reveals a gap.

---

## 4. System Rules

**Rule 1 — Phases are gated.**
A phase is not complete until its gate passes. Gates are objective, runnable verifications.

**Rule 2 — Tests are inseparable.**
Every phase ships with its tests. The bible already specified test coverage in section 18; this plan delivers them by phase, not at the end.

**Rule 3 — Bible drives code.**
If a phase's implementation reveals a bible gap, the bible is updated first, then the code follows. Code-first changes are forbidden.

**Rule 4 — Parallel work is allowed within a phase.**
Within a phase, multiple modules can be built in parallel as long as they don't share dependencies. Cross-phase parallelism is not allowed.

**Rule 5 — Risk is accounted, not hidden.**
Each phase declares its risk profile. Phases with high risk get buffer time and earlier review checkpoints.

**Rule 6 — Phase outputs include validation, not just code.**
A phase's deliverables include the tests and gate verification, not just the implementation. "Phase done" means "phase tested."

**Rule 7 — Phases are not retrospectively renumbered.**
If a new phase is needed mid-build, it gets the next unused number. Phase 4 doesn't become "Phase 4a/4b" because that's confusing.

**Rule 8 — Phase 8 is the production gate.**
Phase 8 is "production-ready verification." Everything before is internal. Past phase 8, CEE is in production use.

---

## 5. Detailed Workflow — The Eight Phases

### 5.1 Phase 1 — Foundation

**Goal:** the bare bones that make every other phase possible.

**Inputs:** the bible (sections 00–19) as filesystem mirror at `~/cee/bible/`.

**Outputs:**

- `~/cee/` directory layout per section 04 (every directory exists, even if empty).
- `~/.cee/` user config directory with `config.toml` and `redact_list` (empty templates).
- `~/SecondBrain/cee/` Obsidian vault structure (idempotent scaffolding).
- `cee init` CLI command that scaffolds all of the above from `~/cee/.template/`.
- `~/cee/paths.py` — the path constants module.
- `~/cee/persistence/atomic.py` — the atomic write helpers.
- `~/cee/errors/types.py` — the closed enums for `HaltType`, `RunErrorType`, `WarningType`.
- `~/cee/errors/__init__.py` — the exception class hierarchy.
- `~/cee/audit/` infrastructure (append-only logs with hash chain).
- The Pydantic schemas at `~/cee/schemas/` for every artifact type (raw_input, intent_object, classification, agent_plan, skill_set, execution_strategy, final_prompt, clarification_request, run_error, run_summary, skill_frontmatter, agent_frontmatter, grounding_declaration, format_declaration).

**Gate:**

- `cee init` produces the full directory layout from a clean machine.
- `cee verify --layout` reports no missing directories.
- All Pydantic schemas import without errors.
- Test: `tests/unit/test_layout.py` passes.
- Test: `tests/unit/test_schemas/test_every_schema_loads.py` passes.

**Dependencies:** the bible.

**Risk profile:** Low. This is mechanical scaffolding; no judgment calls.

**Notes:** This phase is foundation-only — no business logic. Resist the temptation to start building modules.

---

### 5.2 Phase 2 — Boot Sequence and Bible Sync

**Goal:** CEE can start up cleanly and stay synced with the Notion bible.

**Inputs:** Phase 1 complete.

**Outputs:**

- `~/cee/boot/sequencer.py` — the B1–B9 boot sequence per section 00 §12.
- `cee sync-bible` — pulls the bible from Notion to `~/cee/bible/`.
- The `.sync_meta.json` mechanism for drift detection.
- Cross-section consistency check (verifies closed enums match across bible sections + schemas + code).
- The Skill registry rebuilder at `~/cee/skill_engine/registry.py` (initial empty implementation).
- The agent registry rebuilder at `~/cee/agent_selector/registry.py` (initial empty implementation).
- `cee verify --bible` and `cee verify --boot`.

**Gate:**

- A clean shell can run `cee init` then `cee sync-bible` then `cee verify` without errors.
- Boot sequence completes B1–B9 from a clean state.
- Bible drift is detected when a Notion page changes after sync.
- Test: `tests/integration/test_boot_sequence.py` passes.
- Test: cross-section consistency check rejects a deliberately-introduced enum mismatch.

**Dependencies:** Phase 1.

**Risk profile:** Medium. Bible sync depends on Notion MCP and may surface unexpected page-shape issues.

**Notes:** This is when the bible and code first meet. Surprises here often mean the bible needs clarification. Update bible first, then code.

---

### 5.3 Phase 3 — Persistence and Substrate Adapters

**Goal:** every artifact type can be written to filesystem, mirrored to Obsidian, and (where applicable) queued for Notion promotion. Section 04, 12, 13 implementations.

**Inputs:** Phase 2 complete.

**Outputs:**

- `~/cee/persistence/filesystem_writer.py` — atomic writes, role-aware.
- `~/cee/persistence/obsidian_writer.py` — idempotent vault writes per section 13.
- `~/cee/persistence/notion_writer.py` — promotion queue + Notion MCP writes.
- `~/cee/persistence/audit.py` — append-only with hash chain per section 12.
- `~/cee/safety_gate/redactor.py` — the redaction patterns + user redact_list per section 12.
- `~/cee/safety_gate/injection_scanner.py` — the injection patterns per section 12.
- `~/cee/safety_gate/confirmation.py` — the destructive gate per section 12.
- `cee verify --security`, `cee verify --obsidian`, `cee audit-verify`.
- `cee resync-obsidian` and `cee scaffold-obsidian` commands.

**Gate:**

- A test fixture artifact can be written to all three substrates and reads back identically (modulo redaction differences).
- Redaction tests pass for every pattern in section 12.
- Injection tests pass for every pattern in section 12.
- Hash chain detects tampering.
- Test: `tests/unit/test_safety_gate/`, `tests/unit/test_persistence/` pass.
- Test: `tests/integration/test_persistence_chain.py` passes.

**Dependencies:** Phase 2.

**Risk profile:** Medium-high. Security is critical; redaction misses are silent failures. Heavy testing required.

**Notes:** The injection scanner runs before the interpreter (per section 12 §5.5), so this phase produces a working scanner even though phase 4 builds the interpreter that uses it.

---

### 5.4 Phase 4 — Interpreter and Classifier

**Goal:** raw input becomes structured intent and classification. Sections 00 §5.2, 01, 08.

**Inputs:** Phase 3 complete.

**Outputs:**

- `~/cee/interpreter/interpreter.py` — `RawInput → IntentObject`.
- `~/cee/prompts/interpreter_system.txt` — fixed prompt.
- `~/cee/classifier/classifier.py` — `IntentObject → Classification`.
- `~/cee/classifier/patterns.py` — pattern matchers per task_type.
- `~/cee/classifier/scoring.py` — complexity component scorers.
- `~/cee/classifier/tiers.py` — tier mapper with hard caps.
- `~/cee/classifier/flags.py` — flag evaluators.
- `~/cee/classifier/verb_classes.json` — verb-to-task_type mapping.
- `~/cee/prompts/classifier_system.txt` — fixed prompt.

**Gate:**

- All 8 task_types can be assigned to representative inputs.
- Complexity rubric produces stable scores (determinism test passes with N=10).
- All four flags fire on representative inputs and don't fire on neutral inputs.
- Hard caps apply (LOW Run can't exceed 1 agent post-classification).
- Ambiguity halt fires when confidence delta \< 0.10.
- Test: `tests/unit/test_interpreter/`, `tests/unit/test_classifier/` pass.
- Test: `tests/determinism/` passes for both modules.

**Dependencies:** Phase 3 (for persistence of artifacts).

**Risk profile:** High. Determinism is the hardest invariant; pattern matchers can drift; the LLM-backed parts of the interpreter need careful prompt engineering.

**Notes:** This is the spine. Every downstream module depends on the classifier producing stable, correct output. Allocate buffer.

---

### 5.5 Phase 5 — Agents, Skills, Strategy

**Goal:** the catalog systems and the strategy builder. Sections 06, 07, 15, 16, plus the strategy_builder referenced throughout.

**Inputs:** Phase 4 complete.

**Outputs:**

- `~/cee/.template/.claude/agents/` — 12 seed agents per section 06 §5.6.
- `~/cee/.template/skills/` — 12 seed Skills per section 07 §5.7.
- `~/cee/agent_selector/selector.py`, `generator.py`, `registry.py`, `body_validator.py`, `composition_patterns.py`.
- `~/cee/skill_engine/engine.py`, `resolver.py`, `generator.py`, `registry.py`, `canonicalizer.py`, `duplicate_check.py`.
- `~/cee/skill_engine/file_validators.py` and `~/cee/agent_selector/file_validators.py` per sections 15 and 16.
- `~/cee/strategy_builder/builder.py` — produces `ExecutionStrategy` per section 03.
- `~/cee/prompts/agent_generator_system.txt`, `skill_generator_system.txt`, `agent_body_validator.txt`.

**Gate:**

- All 12 seed agents validate against `agent_frontmatter.json` and pass posture-body LLM check.
- All 12 seed Skills validate against `skill_frontmatter.json`.
- Agent selector picks correct agents for representative inputs across all 8 task_types and all 4 complexity tiers.
- Skill matcher reuses, asks, and generates per the threshold zones.
- Skill generation produces valid [SKILL.md](http://SKILL.md) ≥95% on first try (measured over 50 representative inputs).
- Strategy builder produces correct step counts per tier.
- Test: `tests/unit/test_agent_selector/`, `tests/unit/test_skill_engine/`, `tests/unit/test_skill_files/`, `tests/unit/test_agent_files/` pass.

**Dependencies:** Phase 4 (classifier output drives selection).

**Risk profile:** Medium. Generation success rate is the main risk; mitigated by the seed catalog covering common cases.

**Notes:** This phase produces the catalog that determines reuse rate forever. Time spent making seed agents/Skills high-quality pays off immediately and compounds.

---

### 5.6 Phase 6 — Prompt Builder, Output Format, Grounding

**Goal:** the FinalPrompt is constructed correctly with all conditional tags. Sections 05, 09, 10, 11.

**Inputs:** Phase 5 complete.

**Outputs:**

- `~/cee/prompt_builder/builder.py` — the public `build()` function.
- `~/cee/prompt_builder/templates/*.j2` — one Jinja template per tag (15 templates).
- `~/cee/prompt_builder/tag_order.py` — canonical tag ordering.
- `~/cee/prompt_builder/conditionality/rules.py` — `should_render` per tag.
- `~/cee/prompt_builder/validators/content/*.py` — per-tag content validators.
- `~/cee/prompt_builder/validators/consistency.py` — cross-tag consistency.
- `~/cee/prompt_builder/validators/schema.py` — whole-artifact validator.
- `~/cee/prompt_builder/chunker.py` — over-budget chunking.
- `~/cee/prompt_builder/token_counter.py` — per-target counting.
- `~/cee/prompt_builder/llm.py` — single optional Claude call (role smoothing).
- `~/cee/prompt_builder/construction_log.py`.
- `~/cee/output_format/engine.py`, `catalog.py`, `defaults.py`, `coherence.py`.
- `~/cee/output_format/refinement/*` and `validators/*`.
- `~/cee/grounding/engine.py`, `prohibition_patterns.py`, `extractors/*`.

**Gate:**

- FinalPrompt construction is byte-deterministic (replay test with N=10 passes).
- All 15 tags render correctly under appropriate conditions.
- All 18 output formats infer correctly per task_type.
- Grounding rules emit when needed and omit when not.
- Coherence matrix catches incoherent task_type/format pairs.
- Chunking produces valid sub-prompts for over-budget Runs.
- Linter test passes: no XML interpolation outside templates.
- Test: `tests/unit/test_prompt_builder/`, `tests/unit/test_output_format/`, `tests/unit/test_grounding/` pass.
- Test: `tests/determinism/` passes for prompt_builder, output_format_engine, grounding_engine.

**Dependencies:** Phase 5.

**Risk profile:** Medium. Determinism in the builder is critical; the chunker is fiddly.

**Notes:** This phase delivers the artifact the OPERATOR actually pastes. Quality here is most visible to the user.

---

### 5.7 Phase 7 — Pipeline Driver, Executor, Claude Code Integration

**Goal:** all the modules connect. CEE runs end-to-end. Sections 03, 14.

**Inputs:** Phase 6 complete.

**Outputs:**

- `~/cee/pipeline.py` — the driver per section 03 §5 and section 19 §5.8.
- `~/cee/cli.py` — the full CLI surface (`run`, `replay`, `confirm`, `abort`, `answer`, `sync-bible`, `promote`, `verify`, `list-runs`, `list-skills`, `list-agents`, `classifier-stats`, `audit-verify`, `resync-obsidian`, `record-golden`, `migrate-examples`).
- `~/cee/replay.py` — the replay tool.
- `~/cee/executor/protocol.py`, `paste_executor.py`, `api_executor.py`.
- `~/cee/CLAUDE.md` (auto-generated).
- `~/cee/.claude/commands/*.md` (one per slash command in section 14 §5.3).
- `~/cee/.claude/hooks/*.sh` and `~/cee/.claude/hooks.json`.
- `cee sync-claude-md`, `cee install-claude-extras`.
- `~/cee/errors/messages.py` and message templates per section 19.

**Gate:**

- A clean Run from CLI invocation to delivered FinalPrompt completes for all 8 task_types (one Run per task_type).
- Halt cycles work: paused for clarification → answered → resumed → delivered.
- Replay produces byte-identical artifacts.
- Promotion cycle works: generate Skill → queue → Notion candidate → approve.
- Phase 1 paste executor produces the prompt to disk; Phase 2 API executor (with mocked API) produces an artifact.
- All slash commands invoke their CLI counterparts.
- Both hooks log correctly.
- Test: `tests/integration/test_pipeline_*` and `tests/integration/test_clarification_cycle.py`, `test_replay_cycle.py`, `test_promotion_cycle.py` pass.
- Test: `tests/unit/test_executor/` passes.

**Dependencies:** Phase 6.

**Risk profile:** Medium-high. Integration is where module-level assumptions meet reality.

**Notes:** This is the first phase where CEE feels real to the OPERATOR. Demo-able state achieved here.

---

### 5.8 Phase 8 — Production Verification

**Goal:** every gate from every prior phase passes simultaneously. CEE is verified production-ready.

**Inputs:** Phase 7 complete.

**Outputs:**

- All 8 golden Run examples from section 17 implemented as committed fixtures.
- Test coverage ≥85% per module, with per-module minimums per section 18 §5.3.
- All adversarial tests in section 18 §5.1.4 pass.
- All halt types from section 19 reachable in tests.
- Determinism tests pass at N=100 (nightly profile).
- All linter rules pass.
- CI pipeline runs and is green.
- `cee verify --all` reports zero failures.
- A "soak test" — CEE runs 100 representative inputs end-to-end without manual intervention beyond expected halts.
- The bible is reread by CEE at boot from filesystem mirror successfully every time.
- Phase 2 API executor verified against real Anthropic API in nightly run (with budget cap).

**Gate:**

- `cee verify --all` exit code 0.
- All tests pass: unit, integration, golden, adversarial, determinism, lint, security.
- Coverage thresholds met.
- Soak test completes with no unrecoverable failures.
- Documentation in [CLAUDE.md](http://CLAUDE.md), README, and bible all current.
- A second OPERATOR (or future-AB) can read the bible and run `cee init` on a fresh machine and reach a working state in under 30 minutes.

**Dependencies:** Phase 7.

**Risk profile:** High. Phase 8 surfaces every cross-cutting issue that earlier phases hid. Allocate the largest buffer.

**Notes:** This phase is the production-readiness gate. Past it, CEE is the system the bible promised.

---

### 5.9 Phase dependency graph

```javascript
Phase 1 (Foundation)
   ↓
Phase 2 (Boot + Bible Sync)
   ↓
Phase 3 (Persistence + Safety)
   ↓
Phase 4 (Interpreter + Classifier) ← spine
   ↓
Phase 5 (Agents + Skills + Strategy)
   ↓
Phase 6 (Prompt Builder + Format + Grounding)
   ↓
Phase 7 (Pipeline Driver + Executor + Claude Code)
   ↓
Phase 8 (Production Verification)
```

Strict linear dependency. Phases are sequential because each builds on the prior. Within a phase, parallelism is allowed.

### 5.10 Cross-cutting work

Some work happens continuously across phases:

- **Bible updates.** When implementation reveals a gap, the bible is updated first.
- **Test writing.** Tests ship with the phase that produces the code they test. No "tests later."
- **Audit log review.** Periodically check `~/cee/audit/` for security warnings.
- **Determinism vigilance.** Every phase that touches a deterministic module must run the determinism check.

These aren't phases; they're disciplines.

### 5.11 Estimated effort

Calendar time depends on focus and external constraints. Estimate ranges in working days assuming focused effort:

| Phase | Min days | Likely days | Max days | Notes |
|---|---|---|---|---|
| 1 — Foundation | 2 | 3 | 5 | Mechanical scaffolding |
| 2 — Boot + Bible Sync | 2 | 4 | 6 | Notion MCP integration |
| 3 — Persistence + Safety | 4 | 6 | 10 | Security testing extensive |
| 4 — Interpreter + Classifier | 5 | 8 | 12 | Determinism is hard |
| 5 — Agents + Skills + Strategy | 4 | 7 | 10 | Seed catalog quality matters |
| 6 — Prompt Builder + Format + Grounding | 5 | 8 | 12 | 15 templates + chunker |
| 7 — Pipeline Driver + Executor + Claude Code | 3 | 5 | 8 | Integration surprises |
| 8 — Production Verification | 4 | 6 | 10 | Soak test + cross-cutting fixes |
| **Total** | **29** | **47** | **73** | \~6–15 weeks at full focus |

These are estimates, not commitments. Adjust based on parallel work outside CEE (Bernhard day job, MWI content, Embra GTM).

---

## 6. Data / Inputs Needed

### 6.1 Required for the build itself

- The bible (sections 00–19) at `~/cee/bible/` and Notion.
- A Linux machine with Python 3.11+, git, Claude Code installed.
- Anthropic API access (for Phase 2 work in phases 4, 6, 7, 8).
- Notion MCP credentials (for bible sync).

### 6.2 Required for verification

- The 8 golden Run examples from section 17 as test fixtures.
- The adversarial input suite from section 18.
- The mocked LLM responses recorded from real API calls.

### 6.3 Tracking

- A simple Markdown file at `~/cee/build_status.md` tracks which phase is in progress, which gates have passed, which are pending.

---

## 7. Outputs Produced

### 7.1 Per phase

- The code listed in §5.1–§5.8.
- The tests for that code.
- Updates to the bible if implementation revealed gaps.
- A phase completion entry in `build_status.md`.

### 7.2 Final output (after Phase 8)

- A complete, verified CEE installation at `~/cee/`.
- Full test suite passing.
- Documentation current.
- The OPERATOR can run `cee run "..."` and produce paste-ready prompts.

---

## 8. Agent + Skill Implications

### 8.1 The seed catalogs are built in phase 5, used from phase 6 onward

The 12 seed agents and 12 seed Skills are the foundation of reuse. Quality investment in phase 5 reduces work in every later phase and every Run thereafter.

### 8.2 Phase 7's Claude Code integration enables development-mode CEE

Once phase 7 completes, CEE can be used to generate prompts for further building of CEE itself. Bootstrapping circularity becomes useful: the system helps build the next iteration of itself.

### 8.3 Phase 8 includes generation success rate measurement

Per section 18 §8.3 — generators must produce valid files ≥95% on first try. Phase 8 measures this and tunes if needed.

---

## 9. Edge Cases

**EC1 — A phase's gate fails on a quality issue, not a correctness issue.**
Example: tests pass but coverage is 84% (below threshold). Treat as failure. Add tests; don't lower threshold.

**EC2 — A bible update is needed mid-phase.**
Update the bible (Notion). Re-sync filesystem mirror. Continue. The build_[status.md](http://status.md) tracks the bible change.

**EC3 — Two OPERATORs (or future-AB) build phases out of order.**
Forbidden. Dependencies are strict. A phase that hasn't completed cannot have its successor started.

**EC4 — A phase reveals that a prior phase was incomplete.**
Pause current phase. Return to the prior phase. Fix the gate. Re-run the gate check. Resume current phase. The bible should describe what "complete" means precisely enough that this is rare.

**EC5 — External constraints (day job, family) interrupt build for weeks.**
The bible and tests preserve state. Returning is reading the bible and `build_status.md`. No phase is lost; it just resumes.

**EC6 — A phase succeeds but feels rushed; OPERATOR wants more polish.**
The gate is the gate. If polish matters, expand the gate criteria upfront — don't add post-gate work.

**EC7 — A nightly determinism test fails after merge.**
Treat as a phase-regression. Do not advance. Investigate, fix, re-pass the affected phase's gate.

**EC8 — The bible itself is wrong (specifies the impossible).**
Halt the build. Fix the bible. Resume.

**EC9 — A new requirement emerges that wasn't in the bible.**
Add it to the bible first. Update relevant sections. Then update the relevant phase. Then build.

**EC10 — The OPERATOR is tempted to skip phase 8.**
Phase 8 is the production gate. Skipping means CEE is not production-ready. Resist.

**EC11 — Phase 4 takes longer than max estimate.**
Determinism work often does. Don't shortcut. The classifier and interpreter are the spine.

**EC12 — Phase 7 reveals a bigger architectural issue.**
Pause. Update the bible. Cascade the implications back to affected phases. Re-pass their gates.

---

## 10. Failure Modes

### 10.1 Phase declared "complete" without gate passing

**Failure:** OPERATOR moves to next phase before tests pass.
**Detection:** `cee verify --phase <n>` checks gate criteria.
**Recovery:** return to prior phase; fix; re-pass gate.

### 10.2 Tests written after code instead of with code

**Failure:** Phase appears complete but coverage is low.
**Detection:** coverage check at gate.
**Recovery:** test debt accumulates; later phases must back-fill before their own gates.

### 10.3 Bible drift during build

**Failure:** code changes that should have been bible changes.
**Detection:** boot's cross-section consistency check; periodic OPERATOR review.
**Recovery:** bible updated to reflect intended state; code re-aligned if drifted.

### 10.4 Estimates ignored

**Failure:** OPERATOR commits to calendar dates that conflict with effort estimates.
**Detection:** calendar pressure; corner-cutting.
**Recovery:** estimates are not commitments; gates are. Don't trade gate quality for date.

### 10.5 Burnout mid-phase

**Failure:** OPERATOR runs out of energy mid-build.
**Detection:** `build_status.md` stops updating; tests break and aren't fixed.
**Recovery:** rest. The bible preserves state. Resume.

### 10.6 Scope creep within a phase

**Failure:** Phase 5 starts adding features not in the bible.
**Detection:** PR review (or OPERATOR self-review).
**Recovery:** scope cuts; out-of-bible work goes to a separate "post-phase-8" backlog (which doesn't exist yet but might).

### 10.7 Phase 8 finds many cross-cutting issues

**Failure:** Earlier phases passed gates but missed integration issues.
**Detection:** Phase 8 gate fails repeatedly.
**Recovery:** earlier gates are tightened; soak test added to phases 4, 6, 7 going forward.

### 10.8 Documentation drift

**Failure:** README and [CLAUDE.md](http://CLAUDE.md) become stale.
**Detection:** `cee verify --docs` cross-checks.
**Recovery:** doc updates required at every phase gate.

### 10.9 Test fixture rot

**Failure:** Golden Runs in section 17 become outdated as bible evolves.
**Detection:** golden tests fail.
**Recovery:** `cee migrate-examples --schema-version <v>` regenerates; PR includes both bible change and example regeneration.

### 10.10 OPERATOR disagrees with the bible mid-build

**Failure:** OPERATOR implements something differently than spec.
**Detection:** code review or bible/test mismatch.
**Recovery:** decide which is right. If the code is right, update the bible. If the bible is right, fix the code.

---

## 11. Build Notes for Claude Code

- **`build_status.md`** **location:** `~/cee/build_status.md`. Plain Markdown, manually edited. Format: heading per phase, checkboxes for outputs, gate check result.
- **`cee verify --phase <n>`** **:** runs the gate check for phase n. Exit code 0 = passed.
- **`cee verify --all`** **:** runs every phase's gate sequentially. Used for Phase 8 verification.
- **CI gates per phase:** the CI configuration in section 18 §5.5 covers fast / full / golden / determinism. Phase-specific gates can be added as additional CI jobs.
- **Phase tracking in commits:** commit messages include `[Phase N]` prefix. Makes git log readable as a build journal.
- **Phase-specific branches (optional):** if OPERATOR works in branches, naming `phase-<n>-<topic>` makes them traceable. Trunk-based is also fine.
- **Soak test runner:** `~/cee/tests/soak/run_soak.py` runs 100 representative inputs end-to-end. Used in Phase 8 gate.
- **Build retrospective:** after each phase, OPERATOR updates `build_status.md` with what worked, what was harder than expected, what to watch in the next phase. Builds organizational memory.

---

## 12. Definition of Done

This page is complete — and the build plan is unblocked for execution — when:

- [ ] All 8 phases have defined gates per §5.
- [ ] The phase dependency graph in §5.9 is unambiguous.
- [ ] Each phase's outputs map to specific files and modules from sections 00–19.
- [ ] Each phase's gate is runnable via `cee verify --phase <n>`.
- [ ] `build_status.md` template exists at `~/cee/.template/build_status.md` and is copied during `cee init`.
- [ ] Estimated effort is documented and conservative.
- [ ] Risk profiles per phase are accurate.
- [ ] OPERATOR has reviewed and accepted the plan (or revised it).

This page is meta: it doesn't get "completed" in the same way other phases do. It is verified by the build itself.

---

## 13. Final Statement

The build plan is the bridge from bible to system. Eight phases, strict dependencies, runnable gates. There is no MVP because there is no "later" — every section of the bible is implemented, tested, and verified before CEE is considered done. The plan respects the reality that the OPERATOR has competing demands: the bible and tests preserve state across interruptions, so the build can pause and resume without losing what was built. Past Phase 8, CEE is the system its bible promised.
