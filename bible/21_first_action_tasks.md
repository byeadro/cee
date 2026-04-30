---
notion_section: 21
notion_title: 21 — FIRST ACTION TASKS
mirrored_at: 2026-04-30
---

# 21 — FIRST ACTION TASKS

> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the concrete starting list for day one of building CEE. Section 20 sequenced the build into 8 phases. This page extracts Phase 1 into a numbered task list small enough to start in one sitting and structured enough that progress is visible after each task. If section 20 is the campaign, this page is the first march.

---

## 1. What This Is

A numbered checklist of the smallest atomic tasks that move CEE from "no code" to "Phase 1 gate passes." Each task is:

- **Atomic** — one task is one PR-sized unit of work; can be paused mid-task only at clean boundaries.
- **Verifiable** — completing it produces something runnable or testable.
- **Ordered** — the sequence respects dependencies; later tasks build on earlier ones.
- **Estimated** — each task has a rough effort estimate in minutes or hours.

This page covers Phase 1 in detail. Subsequent phases get analogous task breakdowns when their predecessors are complete, but those breakdowns are not pre-written here — they emerge from the work done in this phase.

---

## 2. Why This Matters

Section 20's Phase 1 says "Foundation, 2–5 days." That's not a starting point. The OPERATOR opens the terminal, sits down with Claude Code, and now what?

This page answers "now what" with a numbered list. Each task is small enough to start, defined enough to know when it's done, and ordered so completing them in sequence produces a working Phase 1 gate.

Without this page: paralysis or wandering. With it: a well-defined first session.

---

## 3. Core Requirements

This page MUST:

1. Cover everything Phase 1 of section 20 requires.
2. Order tasks by dependency.
3. Make each task atomic and verifiable.
4. Provide enough context that a Claude Code session can be invoked once per task and produce the result.
5. Surface the exact `cee` slash command (where applicable) or pasted prompt to use.
6. Be updateable — as the build progresses, the OPERATOR adds notes to each task.

This page MUST NOT:

- Pre-plan tasks beyond Phase 1.
- Substitute for the bible — tasks reference the bible, they don't replicate it.
- Skip foundation work in favor of "more interesting" tasks.

---

## 4. System Rules

**Rule 1 — Do tasks in order.**
Skipping ahead is forbidden. Dependencies are real.

**Rule 2 — Each task ends at a verifiable point.**
Either it produces a file, runs a command, or passes a test. Mid-task ambiguity is a smell.

**Rule 3 — One Claude Code session per task is the default.**
Open Claude Code, paste the task, complete it, close. This keeps context windows clean and outcomes traceable.

**Rule 4 — Update task status in this page.**
Each task has a checkbox. Check it when done. Add notes as you go (problems, deviations, surprises).

**Rule 5 — When a task spawns sub-tasks, add them inline.**
If task 7 turns out to need three sub-tasks, they become 7.1, 7.2, 7.3 — not appended at the end.

**Rule 6 — When a task reveals a bible gap, fix the bible first.**
The bible drives. If a task can't be done because the bible is unclear, update the bible (in Notion), then return to the task.

**Rule 7 — Phase 1 ends with the gate.**
The last task in this page is "run `cee verify --phase 1` and confirm exit 0." That's the gate from section 20 §5.1.

---

## 5. Detailed Workflow — The Tasks

### 5.1 Pre-flight (one-time setup)

Before task 1, confirm the environment:

- [ ] Linux machine (Ubuntu, Arch, etc.) with sudo access.
- [ ] Python 3.11+ installed (`python3.11 --version`).
- [ ] git installed and configured.
- [ ] Claude Code installed and authenticated.
- [ ] Notion MCP credentials available.
- [ ] Anthropic API key in a password manager (used in Phase 2; not Phase 1).
- [ ] Obsidian installed; vault at `~/SecondBrain/` exists (or noted to scaffold).
- [ ] `~/cee/` does not yet exist (or you're prepared to back it up if it does).

If any item fails, resolve before starting task 1.

### 5.2 The numbered tasks

#### Task 1 — Create the repository

**Effort:** 15 minutes.

**Goal:** initialize the CEE git repository and basic Python packaging.

- [ ] `mkdir -p ~/cee && cd ~/cee`
- [ ] `git init`
- [ ] Create a minimal `pyproject.toml` with project name `cee`, Python 3.11+, dependencies: `pydantic`, `pyyaml`, `jinja2`, `anthropic`, `python-frontmatter`, `tiktoken`, `pytest`, `pytest-cov`, `pytest-mock`, `pytest-xdist`, `coverage[toml]`, `tomli` (or `tomllib` for 3.11+).
- [ ] Create `.gitignore` with: `__pycache__/`, `.pytest_cache/`, `*.pyc`, `.coverage`, `htmlcov/`, `dist/`, `build/`, `*.egg-info/`, `.cee/`, `runs/`, but NOT `~/cee/runs/golden/` (those are committed fixtures).
- [ ] Create `README.md` with one-paragraph description and a link to the System Design Bible.
- [ ] First commit: "Initial scaffold."

**Verification:** `git log --oneline` shows one commit.

#### Task 2 — Mirror the bible to filesystem

**Effort:** 30 minutes.

**Goal:** create `~/cee/bible/` with text mirrors of all 23 Notion pages.

- [ ] Create `~/cee/bible/` directory.
- [ ] For each of the 23 sections (00–22), create a file named `<NN>_<slug>.md` (e.g., `00_project_vision.md`, `01_real_problem_breakdown.md`, ..., `22_master_system_build_prompt.md`). The slug is the kebab-case version of the title.
- [ ] Manually copy each Notion page's content into its file. For now, plain copy-paste is fine; `cee sync-bible` (built in task 9) will automate this later.
- [ ] Create `~/cee/bible/.sync_meta.json` with `{"last_synced": "<ISO timestamp now>", "pages": {"<NN>_<slug>": "<placeholder>"}}` for each section.
- [ ] Commit: "Mirror bible 00–22 to filesystem."

**Verification:** `ls ~/cee/bible/` shows 23 .md files plus `.sync_meta.json`.

#### Task 3 — Define the directory layout

**Effort:** 30 minutes.

**Goal:** create the full `~/cee/` directory layout per section 04 §5.1, even if directories are empty.

- [ ] Create the following empty directories:
	- `~/cee/interpreter/`, `classifier/`, `agent_selector/`, `skill_engine/`, `strategy_builder/`, `prompt_builder/`, `safety_gate/`, `persistence/`, `boot/`, `executor/`, `roles/`, `errors/`, `output_format/`, `grounding/`
	- `~/cee/schemas/`
	- `~/cee/prompts/`
	- `~/cee/skills/`
	- `~/cee/.claude/agents/`
	- `~/cee/.claude/commands/`
	- `~/cee/.claude/hooks/`
	- `~/cee/runs/`, `runs/golden/`
	- `~/cee/audit/`, `audit/archive/`
	- `~/cee/tests/`, `tests/unit/`, `tests/integration/`, `tests/golden/`, `tests/adversarial/`, `tests/determinism/`, `tests/lint/`, `tests/fixtures/`, `tests/soak/`
	- `~/cee/.template/` (will hold seed catalogs for `cee init`)
- [ ] In each Python module directory (every dir under `~/cee/` that's a Python package), create an empty `__init__.py`.
- [ ] Commit: "Create full directory layout."

**Verification:** `find ~/cee -type d | wc -l` shows ≥35 directories. `ls ~/cee/` shows expected structure.

#### Task 4 — Create `~/cee/paths.py`

**Effort:** 30 minutes.

**Goal:** the single source of truth for all paths in the codebase.

Open Claude Code in `~/cee/` and ask:

> "Create `~/cee/paths.py` per section 04 of the bible at `~/cee/bible/04_database_file_structure.md`. Define `Path` constants for every location referenced in the bible: bible mirror, schemas, prompts, skills, agents, runs, audit, user config, Obsidian vault. Include constants for the user-managed paths (\~/.cee/config.toml, redact_list, notion_redact_list, credentials.toml). Use `pathlib.Path` and `os.path.expanduser` for `~`. Do not concatenate strings; use Path division."

- [ ] Verify Claude Code produces a file that imports cleanly.
- [ ] `python -c "from cee.paths import *; print(CEE_ROOT)"` should print `/home/<user>/cee`.
- [ ] Commit: "Add [paths.py](http://paths.py) — single source of truth for all CEE paths."

**Verification:** Import works; no string concatenation visible in the file.

#### Task 5 — Create `~/cee/persistence/atomic.py`

**Effort:** 45 minutes.

**Goal:** the atomic write helpers used by every other writer.

In Claude Code:

> "Create `~/cee/persistence/atomic.py` per section 04 §5.1 and the Build Notes in §11 of the same section. Implement `atomic_write_json(path, data)` and `atomic_write_text(path, text)`. Each writes to a temp file in the same directory, fsyncs, and renames atomically. Both must succeed-or-fail-cleanly: a partial file is never visible. Add tests in `~/cee/tests/unit/test_persistence/test_atomic_writes.py` covering: success path, failure-during-write doesn't leave partial file, idempotent rename, permissions preserved."

- [ ] Verify the helper exists and tests pass.
- [ ] `pytest ~/cee/tests/unit/test_persistence/test_atomic_writes.py` exits 0.
- [ ] Commit: "Add atomic write helpers + tests."

**Verification:** Tests pass.

#### Task 6 — Define the closed enums

**Effort:** 1 hour.

**Goal:** `~/cee/errors/types.py` with the three closed enums from section 19.

In Claude Code:

> "Create `~/cee/errors/types.py` per section 19 §5.1, §5.2, §5.3. Define three Python `Enum` classes inheriting from `str, Enum`: `HaltType` (19 values), `RunErrorType` (7 values), `WarningType` (15 values). Match the bible's enum lists exactly. Add tests in `~/cee/tests/unit/test_errors/test_types.py` asserting each enum has the expected values."

- [ ] Verify all enum values from the bible are present.
- [ ] Tests pass.
- [ ] Commit: "Define closed enums for HaltType, RunErrorType, WarningType."

**Verification:** `pytest ~/cee/tests/unit/test_errors/` passes.

#### Task 7 — Define the exception hierarchy

**Effort:** 1 hour.

**Goal:** `~/cee/errors/__init__.py` with the hierarchy from section 19 §5.7.

In Claude Code:

> "Create `~/cee/errors/__init__.py` per section 19 §5.7. Define `CEEException` as the base class. Subclasses: `PipelineHalt(halt_type, payload)`, `RunError(error_type, payload)`, `BootError(step, reason)`, `ValidationError`, `RoleAuthorityError`, `SubstrateBoundaryError`, `RoleSurfaceViolation`, `InjectionDetected(flags)` (subclass of PipelineHalt), `RedactionFailed(residual_patterns)` (subclass of PipelineHalt). Add tests in `~/cee/tests/unit/test_errors/test_exceptions.py` that each can be raised and caught at the right level."

- [ ] Verify exceptions can be raised and caught.
- [ ] Tests pass.
- [ ] Commit: "Define CEE exception hierarchy."

**Verification:** Tests pass.

#### Task 8 — Define the Pydantic schemas

**Effort:** 4 hours (largest task in Phase 1).

**Goal:** every artifact has a Pydantic model in `~/cee/schemas/`.

This is the highest-leverage task in Phase 1. The Pydantic models are referenced by every module. Be careful and exhaustive.

In Claude Code (one prompt covering all schemas, but split into multiple sessions if needed):

> "Create Pydantic models in `~/cee/schemas/` per the bible. One file per artifact:
>
> - `raw_input.py` (RawInput per section 03 §5.2 Step 1)
> - `intent_object.py` (IntentObject per section 00 §5 Step 2)
> - `classification.py` (Classification per section 08 §7.1)
> - `agent_plan.py` (AgentPlan per section 06 §7.1)
> - `skill_set.py` (SkillSet per section 07 §7.1)
> - `execution_strategy.py` (ExecutionStrategy per section 03)
> - `final_prompt.py` (FinalPrompt per section 05 §5.1, with all 15 tags as fields)
> - `clarification_request.py` (ClarificationRequest)
> - `run_error.py` (RunError)
> - `run_summary.py` (RunSummary)
> - `skill_frontmatter.py` (per section 15 §5.2)
> - `agent_frontmatter.py` (per section 16 §5.2)
> - `grounding_declaration.py` (per section 11)
> - `format_declaration.py` (per section 10)
>
> Each model must include a `produced_by` field of type `RoleEnum` (you'll add the RoleEnum in `~/cee/roles/__init__.py` per section 02 §4). Models use Pydantic v2 syntax. Schema versions: `$schema_version = "1.0.0"` as a class variable.
>
> For each model, add a unit test in `~/cee/tests/unit/test_schemas/test_<artifact_name>.py` covering: a valid example passes, an example with a missing required field fails, an example with an extra field fails (Pydantic strict mode), the produced_by field is present and validates."

- [ ] Verify all 14 models import successfully.
- [ ] All schema unit tests pass.
- [ ] Commit: "Define all Pydantic schemas."

**Verification:** `pytest ~/cee/tests/unit/test_schemas/` passes.

**Notes:** This task is large. Split into multiple Claude Code sessions if needed (one per model, perhaps grouped by domain: artifact schemas first, then frontmatter schemas, then declaration schemas).

#### Task 9 — Define the RoleEnum

**Effort:** 30 minutes.

**Goal:** `~/cee/roles/__init__.py` with the closed role enum from section 02 §4.

In Claude Code:

> "Create `~/cee/roles/__init__.py` per section 02 §4. Define `RoleEnum` as a closed `str, Enum` with all 19 role values from §4.1 through §4.4 (1 human role + 12 system roles + 3 external roles + 3 substrate roles). Add a test in `~/cee/tests/unit/test_roles/test_role_enum.py` asserting all expected values are present and that the enum matches what the bible declares."

- [ ] Verify enum is complete.
- [ ] Test passes.
- [ ] Commit: "Define RoleEnum."

**Verification:** `pytest ~/cee/tests/unit/test_roles/` passes.

#### Task 10 — Set up `~/.cee/` user config

**Effort:** 45 minutes.

**Goal:** the user-managed config directory with template files.

- [ ] `mkdir -p ~/.cee/`
- [ ] Create `~/.cee/config.toml` from the template in section 04 §5.2.
- [ ] Create `~/.cee/redact_list` (empty file with comments showing how to add patterns).
- [ ] Create `~/.cee/notion_redact_list` (same).
- [ ] Create `~/.cee/credentials.toml` template (commented out for Phase 1; populated in Phase 2).
- [ ] `chmod 600 ~/.cee/credentials.toml` (even though empty).
- [ ] Don't commit any of these — they're user-specific and may contain secrets later. Add `~/.cee/` to a personal note about where this lives.

**Verification:** `cat ~/.cee/config.toml` shows expected sections.

#### Task 11 — Set up `~/SecondBrain/cee/` Obsidian vault structure

**Effort:** 30 minutes.

**Goal:** the Obsidian vault scaffolding per section 13 §5.1.

- [ ] If `~/SecondBrain/` doesn't exist, create it. (If you use a different vault location, update `~/.cee/config.toml`'s `obsidian_vault` value.)
- [ ] Create `~/SecondBrain/cee/` and the subdirectories per section 13 §5.1: `runs/`, `skills/`, `agents/`, `bible/`, `audit/`, `_templates/`.
- [ ] Create `~/SecondBrain/cee/README.md` with a one-paragraph description and frontmatter `type: meta`.
- [ ] Don't populate notes yet — that happens during Runs (post-Phase 1).

**Verification:** Open Obsidian; the `cee` folder is visible in the vault.

#### Task 12 — Write the audit log infrastructure

**Effort:** 2 hours.

**Goal:** the append-only audit log with hash chain per section 12 §5.8.

In Claude Code:

> "Create `~/cee/persistence/audit.py` per section 12 §5.8. Implement `log_event(actor, event, run_id, details, severity, security_relevant)`. Each entry is a JSON object appended to the appropriate log file (`cli.log`, `roles.log`, `boot.log`, `security.log`). Include a `prev_hash` and `entry_hash` for tamper detection (SHA-256). Also implement `verify_chain(log_path)` that walks the log and confirms each entry's `prev_hash` matches the previous entry's `entry_hash`.
>
> Add tests in `~/cee/tests/unit/test_persistence/test_audit.py`: append works, hash chain is valid, tampering with a middle entry is detected, missing log file creates a new chain rooted at zeros, log files are append-only (writes never overwrite)."

- [ ] Verify all log files end up in `~/cee/audit/`.
- [ ] All tests pass.
- [ ] Commit: "Add audit log with tamper-evident hash chain."

**Verification:** `pytest ~/cee/tests/unit/test_persistence/test_audit.py` passes.

#### Task 13 — Implement `cee init` (the scaffolder)

**Effort:** 2 hours.

**Goal:** `cee init` produces the full layout from `~/cee/.template/`.

In Claude Code:

> "Create `~/cee/cli.py` with a `cee` Click-based CLI (or argparse — your choice; Click preferred). Implement the `init` subcommand. It scaffolds:
>
> - The full `~/cee/` directory layout per section 04 §5.1 (idempotent — does not overwrite existing files unless `--force`).
> - Copies `~/cee/.template/.claude/` if not present.
> - Creates `~/.cee/` if not present (with template config and empty redact lists).
> - Creates `~/SecondBrain/cee/` if not present.
> - Logs the scaffolding actions to `~/cee/audit/cli.log`.
>
> Also add the entry point in `pyproject.toml` so `cee` is on PATH after `pip install -e .`.
>
> Add a test in `~/cee/tests/unit/test_cli/test_init.py` that runs `cee init` against a `tmp_path` and verifies the layout."

- [ ] `pip install -e .` makes `cee` available.
- [ ] `cee init --help` shows the help text.
- [ ] Test passes.
- [ ] Commit: "Implement `cee init` scaffolder."

**Verification:** `cee --help` works.

#### Task 14 — Implement `cee verify --layout`

**Effort:** 1 hour.

**Goal:** the layout integrity check.

In Claude Code:

> "Add the `verify` subcommand to `~/cee/cli.py`. Implement `--layout` flag that walks `~/cee/` and asserts every required directory exists per the layout in section 04 §5.1. Reports missing items with clear error messages. Exit code 0 on pass, non-zero on fail. Logs the check to `~/cee/audit/cli.log`. Test it in `~/cee/tests/unit/test_cli/test_verify.py`."

- [ ] `cee verify --layout` reports no missing directories on a freshly-initialized `~/cee/`.
- [ ] Test passes.
- [ ] Commit: "Add `cee verify --layout`."

**Verification:** `cee verify --layout` exits 0.

#### Task 15 — Implement `cee verify --schemas`

**Effort:** 1 hour.

**Goal:** all Pydantic schemas import cleanly.

In Claude Code:

> "Add `--schemas` flag to `cee verify`. Walks `~/cee/schemas/` and imports each module. Reports any import errors. Also runs each model's `model_json_schema()` and verifies the output is valid JSON Schema. Exit code 0 on pass."

- [ ] Test passes.
- [ ] Commit: "Add `cee verify --schemas`."

**Verification:** `cee verify --schemas` exits 0.

#### Task 16 — Run the Phase 1 gate

**Effort:** 30 minutes.

**Goal:** confirm Phase 1 is complete per section 20 §5.1.

- [ ] Run `cee verify --layout` — exit 0.
- [ ] Run `cee verify --schemas` — exit 0.
- [ ] Run `pytest ~/cee/tests/unit/` — all pass.
- [ ] Update `~/cee/build_status.md`: Phase 1 complete, gate passed.
- [ ] Commit: "Phase 1 complete — gate passed."

**Verification:** Phase 1 gate per section 20 §5.1 is satisfied.

### 5.3 Total Phase 1 effort

Sum of estimates: \~16 hours of focused work. Realistic calendar time accounting for context switching and the Bernhard/Embra/MWI workload: 3–5 days.

---

## 6. Data / Inputs Needed

### 6.1 Required to start

- The bible mirrored to `~/cee/bible/` (task 2).
- Python 3.11+, git, Claude Code, Obsidian.

### 6.2 Required for verification

- pytest installed.
- `~/cee/` Python package importable.

### 6.3 Tracking

- `~/cee/build_status.md` updated as tasks complete.

---

## 7. Outputs Produced

### 7.1 At Phase 1 gate

- Full directory layout under `~/cee/`.
- Bible mirror at `~/cee/bible/`.
- All Pydantic schemas in `~/cee/schemas/`.
- Closed enums (`HaltType`, `RunErrorType`, `WarningType`, `RoleEnum`).
- Exception hierarchy.
- Atomic write helpers.
- Audit log with hash chain.
- `cee init` and `cee verify --layout / --schemas` working.
- `~/.cee/` user config scaffolded.
- `~/SecondBrain/cee/` vault scaffolded.

### 7.2 What's not yet built

- Boot sequence (Phase 2).
- Bible sync from Notion (Phase 2).
- Any module beyond schemas and persistence helpers.
- Any agent or Skill (catalog comes in Phase 5).

---

## 8. Agent + Skill Implications

### 8.1 No agents or Skills loaded yet

Phase 1 doesn't load anything from `~/cee/.claude/agents/` or `~/cee/skills/` — those directories exist but are empty. Catalog seeding happens in Phase 5.

### 8.2 The OPERATOR's Claude Code sessions are using stock agents

While building CEE itself, the OPERATOR uses whatever Claude Code subagents are available natively. CEE's own agents come online in Phase 5. Until then, Claude Code sessions are stock.

---

## 9. Edge Cases

**EC1 — Task 8 (schemas) takes longer than estimated.**
Common — 14 schemas is a lot. Split across multiple sessions. Don't rush.

**EC2 — A schema reveals a bible ambiguity.**
Pause the task. Update the bible (in Notion). Re-sync `~/cee/bible/` mirror. Resume.

**EC3 — `cee init` fails on a fresh machine because of permissions.**
Common on systems with restrictive umask. Verify `~/cee/` is owned by the OPERATOR. Document in `build_status.md`.

**EC4 — Tests pass locally but the task hasn't materialized something visible.**
Some tasks are infrastructure-only (e.g., schemas). The visible result is "tests pass." That's the verification.

**EC5 — OPERATOR is unsure whether a sub-task is needed.**
Read the relevant bible section. If still unsure, add a question note in the task; resolve before proceeding.

**EC6 — A task's Claude Code session generates code that doesn't match the bible.**
Reject it. Re-prompt with explicit references to the bible section. Bible drives.

**EC7 — Mid-task, the OPERATOR runs out of time.**
Each task ends at a clean boundary. Commit progress. Resume next session.

**EC8 — `cee init` on a machine where `~/cee/` already exists.**
Default behavior: refuse with a message. `--force` would overwrite, but task 13 didn't implement `--force`. Add it later if needed.

**EC9 — The OPERATOR wants to skip ahead and start on, say, the classifier.**
Forbidden. Phase 1 dependencies are real. The classifier needs schemas, paths, audit, atomic writes — all Phase 1 outputs.

**EC10 — A new section is added to the bible (e.g., a section 23) during Phase 1.**
Update the bible mirror in task 2's pattern. Add the file. Continue Phase 1.

---

## 10. Failure Modes

### 10.1 OPERATOR loses track of which task they're on

**Failure:** intermittent work; task list state diverges from reality.
**Detection:** running `pytest` shows tests fail that should pass, or `cee verify --layout` reports missing items.
**Recovery:** review `build_status.md`; re-walk recent tasks; resume.

### 10.2 Tasks get done out of order

**Failure:** task 8 (schemas) attempted before task 6 (HaltType/RoleEnum needed by schemas).
**Detection:** schemas fail to import.
**Recovery:** complete the dependency task first.

### 10.3 Tests don't get written for a task

**Failure:** task marked complete but test directory empty.
**Detection:** `pytest` shows few tests.
**Recovery:** treat the task as incomplete; add tests.

### 10.4 `cee init` is not idempotent

**Failure:** running `cee init` twice creates duplicates or destroys content.
**Detection:** second run modifies content.
**Recovery:** task 13 needs idempotency fix; tests should catch.

### 10.5 Bible mirror gets stale during Phase 1

**Failure:** OPERATOR edits Notion bible during Phase 1; mirror falls behind.
**Detection:** when Phase 2 implements `cee sync-bible`, drift becomes apparent. In Phase 1, OPERATOR re-mirrors manually if changes made.
**Recovery:** re-do task 2's manual copy. Or wait for Phase 2's `cee sync-bible`.

### 10.6 OPERATOR over-engineers Phase 1

**Failure:** spends time polishing Phase 1 beyond gate criteria.
**Detection:** Phase 1 takes longer than 5 days with no obvious blocker.
**Recovery:** focus on gate criteria. Polish later.

### 10.7 OPERATOR under-engineers Phase 1

**Failure:** rushes through; tests are thin; gate passes but next phase struggles.
**Detection:** Phase 2 hits unexpected issues.
**Recovery:** back-fill Phase 1 tests; do not advance until robust.

### 10.8 New requirement from Embra / Bernhard / MWI interrupts Phase 1

**Failure:** OPERATOR's day-job demands pull focus mid-phase.
**Detection:** `build_status.md` stops updating.
**Recovery:** the bible and tests preserve state. Resume when possible. No phase is lost.

### 10.9 Atomic write helper has a subtle bug

**Failure:** under specific filesystem conditions (network mount), rename isn't atomic.
**Detection:** integration tests fail in unusual environments.
**Recovery:** task 5 needs hardening; tests expanded to cover more filesystems.

### 10.10 Schema definitions drift from bible during the work

**Failure:** OPERATOR's interpretation differs from bible literal text.
**Detection:** Phase 8 boot consistency check fails.
**Recovery:** re-align schema to bible; bible is source of truth.

---

## 11. Build Notes for Claude Code

- **Open Claude Code in `~/cee/`** for every task. `~/cee/CLAUDE.md` doesn't exist yet (built in Phase 7), but Claude Code still works without it — context is provided in each task's prompt.
- **Reference the bible explicitly in prompts.** "Per section 04 §5.1" in prompts is more reliable than "use the layout from the design doc."
- **One commit per task.** Makes git log readable as the build journal.
- **Use a Branch per phase (optional).** `phase-1-foundation` if you prefer branching. Trunk also fine.
- **Update `~/cee/build_status.md` after each task.** Even one line: "Task N done, no surprises" or "Task N done, hit X surprise, fixed by Y."
- **When stuck, re-read the bible first.** The bible is precise. Ambiguity in the build is usually the OPERATOR's interpretation, not the bible's gap.
- **If the bible IS ambiguous, fix it in Notion before continuing.** Bible drives.
- **Don't skip task 8 because it's big.** Schemas are foundation. Build them well.
- **Tests are not optional.** Every task that produces code produces tests in the same task.

---

## 12. Definition of Done

This page is complete — and Phase 1 of section 20 is unblocked — when:

- [ ] All 16 tasks in §5.2 are checked off.
- [ ] `cee verify --phase 1` exits 0.
- [ ] `~/cee/build_status.md` records Phase 1 as complete.
- [ ] All Phase 1 outputs from section 20 §5.1 exist.

The page itself is "done" once the task list completes Phase 1. Phases 2–8 will get their own task breakdowns when their predecessors complete (those breakdowns are not pre-planned here).

---

## 13. Final Statement

The first day starts with task 1: `mkdir ~/cee && git init`. Sixteen tasks later, Phase 1 is complete and CEE has a working foundation. The bible specifies what; this page specifies what to do first. From here, each subsequent phase emerges as its predecessor finishes — no need to plan further than the next checkbox.
