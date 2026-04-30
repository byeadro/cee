---
notion_section: 02
notion_title: 02 — USER ROLES
mirrored_at: 2026-04-30
---

# 02 — USER ROLES
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** define every actor that interacts with CEE — human or machine — and the exact permissions, responsibilities, and surfaces each one touches. If something acts on the system, it is named here. If it isn't named here, it has no authority to act.
---
## 1. What This Is
CEE is a multi-actor system disguised as a single-user tool. The "user" sitting at the keyboard is one of several roles the system serves, and the codebase itself plays multiple internal roles that must be distinguished or the security and integrity rules in §10 of section 00 are unenforceable.
This page enumerates every actor:
- **Human roles** — people who can act on CEE (currently just AB; structured for future expansion)
- **System roles** — modules within CEE that act on behalf of humans
- **External roles** — services CEE talks to ([Claude.ai](http://Claude.ai), Claude Code, Anthropic API, Notion, Obsidian)
- **Substrate roles** — the three persistence layers, each with distinct authority over canon
Each role has: a defined surface (what it can touch), a defined authority level (what it can change without confirmation), and a defined audit trail (where its actions are logged).
This page is a permissions matrix. The rest of the bible assumes it.
---
## 2. Why This Matters
Without role definition, three concrete failures occur:
1. **Authority creep.** A module starts deciding things it shouldn't (e.g., the classifier silently overriding the bible). With roles defined, every action has a named owner.
2. **Audit holes.** Something changes; no one knows which actor did it. With roles, every artifact carries a `produced_by` field.
3. **Future-proofing breakage.** Phase 2 adds the API as an executor. Without roles, "executor" is hardcoded to mean [Claude.ai](http://Claude.ai). With roles, the executor is a slot, and Phase 2 fills it.
This is not bureaucracy. It is the contract that lets safety rules in section 00 §10 actually be enforceable.
---
## 3. Core Requirements
The role system MUST:
1. Name every actor that can write to any substrate.
2. Define each actor's surface (allowed reads), authority (allowed writes), and audit destination.
3. Distinguish between **canon-modifying** actions (require human role) and **canon-using** actions (any role).
4. Produce a `produced_by` field on every artifact emitted by any module.
5. Refuse any action by an undefined or unauthorized actor.
6. Survive Phase 2 transition without role schema changes — only the executor role's *implementation* changes.
The role system MUST NOT:
- Allow system roles to modify the bible.
- Allow external roles to write to the filesystem directly.
- Allow substrate roles to act on each other (filesystem doesn't write to Notion; the `notion_writer` module does).
- Be expandable at runtime. New roles require a bible update.
---
## 4. The Role Taxonomy
Four categories. Closed enum.
### 4.1 Human roles
- `OPERATOR`
- `AUDITOR` (future)
### 4.2 System roles (CEE internal modules)
- `INTERPRETER`
- `CLASSIFIER`
- `AGENT_SELECTOR`
- `SKILL_ENGINE`
- `STRATEGY_BUILDER`
- `PROMPT_BUILDER`
- `SAFETY_GATE`
- `PERSISTENCE_WRITER`
- `BIBLE_LOADER`
- `BOOT_SEQUENCER`
- `OBSIDIAN_WRITER`
- `NOTION_WRITER`
### 4.3 External roles (services CEE communicates with)
- `EXECUTOR` (slot — Phase 1: [Claude.ai/Claude](http://Claude.ai/Claude) Code via paste; Phase 2: Anthropic API)
- `NOTION_API`
- `FILESYSTEM_OS`
### 4.4 Substrate roles (persistence layers, treated as actors for audit purposes)
- `FILESYSTEM_CANON`
- `OBSIDIAN_VAULT`
- `NOTION_BIBLE`
---
## 5. System Rules
**Rule 1 — Closed role enum.**
The role list in §4 is exhaustive. No actor exists in the system that is not one of these. New roles require a bible edit and a schema update.
**Rule 2 — Every artifact carries provenance.**
Every artifact written to any substrate has a `produced_by` field naming the system role that produced it. Missing field = invalid artifact.
**Rule 3 — Canon-modifying actions require OPERATOR.**
Modifying the bible, redact_list, config, or rejecting/approving a Skill promotion can only be done by `OPERATOR`. System roles can *propose*, never *commit*, canon changes.
**Rule 4 — System roles are sandboxed to their declared surface.**
The `CLASSIFIER` cannot write to `~/cee/skills/`. The `SKILL_ENGINE` cannot read from `~/.cee/redact_list`. Surface enforcement is by code review and tested via section 18.
**Rule 5 — External roles never write directly to canon.**
Notion writes pass through `NOTION_WRITER`. Filesystem writes pass through `PERSISTENCE_WRITER`. The Anthropic API (Phase 2) returns text into a buffer that `INTERPRETER` validates before any persistence.
**Rule 6 — Substrate authority is hierarchical.**
`FILESYSTEM_CANON` is highest authority. `OBSIDIAN_VAULT` mirrors filesystem. `NOTION_BIBLE` is the only substrate where `OPERATOR` is the source of truth (for the bible specifically) — but for Run artifacts, filesystem still wins.
**Rule 7 — No anonymous writes.**
A write without a named role is rejected at the writer module. There is no "system" or "default" role.
---
## 6. Detailed Workflow — Role Interactions Per Run
This walks the Run pipeline (section 00 §5) annotating each step with the acting roles.
### Step 0 — Boot
- Acting role: `BOOT_SEQUENCER`
- Reads from: `FILESYSTEM_CANON` (bible mirror, registries, schemas), `NOTION_BIBLE` (only if `auto_sync` and drift detected)
- Writes to: `FILESYSTEM_CANON` (registry rebuilds), `OBSIDIAN_VAULT` (boot log)
- Authority: read-only on bible content; full write on registries
### Step 1 — Capture
- Acting role: `OPERATOR` (the input source)
- Reads from: nothing
- Writes to: `RawInput` object in memory only
- Authority: full input authority
### Step 2 — Interpretation
- Acting role: `INTERPRETER`
- Reads from: `RawInput`, recent Run logs (for context), bible §00 + §01
- Writes to: `IntentObject`
- Authority: read-only on bible; emits one artifact
### Step 3 — Classification
- Acting role: `CLASSIFIER`
- Reads from: `IntentObject`, bible §08
- Writes to: `Classification`
- Authority: read-only on bible; emits one artifact; cannot modify the closed enums
### Step 4 — Agent Selection
- Acting role: `AGENT_SELECTOR`
- Reads from: `Classification`, `~/cee/.claude/agents/index.json`
- Writes to: `AgentPlan`
- Authority: read-only on agent files; emits one artifact
### Step 5 — Skill Resolution
- Acting role: `SKILL_ENGINE`
- Reads from: prior artifacts, `~/cee/skills/index.json`
- Writes to: `SkillSet`; new [SKILL.md](http://SKILL.md) files in `~/cee/skills/<slug>/` (via `PERSISTENCE_WRITER`)
- Authority: can generate new Skills; cannot delete or modify existing Skills without explicit `OPERATOR` action
### Step 6 — Execution Strategy
- Acting role: `STRATEGY_BUILDER`
- Reads from: prior artifacts
- Writes to: `ExecutionStrategy`
- Authority: emits one artifact
### Step 7 — Prompt Generation
- Acting role: `PROMPT_BUILDER`
- Reads from: prior artifacts, schemas
- Writes to: `FinalPrompt`
- Authority: schema-validates; emits one artifact
### Step 8 — Safety Pass
- Acting role: `SAFETY_GATE`
- Reads from: `FinalPrompt`, `IntentObject.flags`, `~/.cee/redact_list`
- Writes to: redacted `FinalPrompt`; safety annotations
- Authority: can block delivery; cannot modify the underlying prompt structure, only redact content
### Step 9 — Persistence
- Acting roles: `PERSISTENCE_WRITER` → `OBSIDIAN_WRITER` → `NOTION_WRITER` (in that order)
- Reads from: all Run artifacts
- Writes to: `FILESYSTEM_CANON` (always), `OBSIDIAN_VAULT` (always), `NOTION_BIBLE` (only if Run produced promotion candidates)
- Authority: each writer can only write to its own substrate
### Step 10 — Deliver
- Acting role: `OPERATOR` (receives output)
- Reads from: `FinalPrompt`
- Writes to: nothing in CEE; the `OPERATOR` then pastes into `EXECUTOR`
- Authority: full ownership of what happens after delivery
---
## 7. Data / Inputs Needed (Per Role)
This is the surface declaration. Every role's allowed reads and writes are listed exhaustively.
### 7.1 OPERATOR
- **Reads:** anything in `~/cee/`, `~/SecondBrain/cee/`, the Notion bible
- **Writes:** the bible (Notion), `~/.cee/config.toml`, `~/.cee/redact_list`, accepts/rejects promotion candidates, runs CLI commands
- **Audit:** every CLI command logged to `~/cee/audit/cli.log` with timestamp and command
### 7.2 INTERPRETER
- **Reads:** `RawInput`, recent Run logs (last 50), bible §00, §01
- **Writes:** `IntentObject` (in-memory; persisted by `PERSISTENCE_WRITER`)
- **Audit:** `produced_by: "INTERPRETER"` on every IntentObject
### 7.3 CLASSIFIER
- **Reads:** `IntentObject`, bible §08
- **Writes:** `Classification`
- **Audit:** `produced_by: "CLASSIFIER"`; complexity_score breakdown logged
### 7.4 AGENT_SELECTOR
- **Reads:** `Classification`, `~/cee/.claude/agents/index.json`, individual agent files
- **Writes:** `AgentPlan`
- **Audit:** `produced_by: "AGENT_SELECTOR"`; selected agents listed by file path
### 7.5 SKILL_ENGINE
- **Reads:** prior artifacts, `~/cee/skills/index.json`, individual [SKILL.md](http://SKILL.md) files
- **Writes:** `SkillSet`, new [SKILL.md](http://SKILL.md) files (via `PERSISTENCE_WRITER`)
- **Audit:** `produced_by: "SKILL_ENGINE"`; on Skill generation, original input is logged
### 7.6 STRATEGY_BUILDER
- **Reads:** all prior artifacts
- **Writes:** `ExecutionStrategy`
- **Audit:** `produced_by: "STRATEGY_BUILDER"`
### 7.7 PROMPT_BUILDER
- **Reads:** all prior artifacts, schemas
- **Writes:** `FinalPrompt`
- **Audit:** `produced_by: "PROMPT_BUILDER"`; schema version recorded
### 7.8 SAFETY_GATE
- **Reads:** `FinalPrompt`, `IntentObject.flags`, `~/.cee/redact_list`
- **Writes:** redacted `FinalPrompt`, safety_log
- **Audit:** every redaction logged with pattern matched (not the redacted content)
### 7.9 PERSISTENCE_WRITER
- **Reads:** Run artifacts
- **Writes:** `~/cee/runs/<run_id>/` files; new [SKILL.md](http://SKILL.md) and agent files
- **Audit:** writes carry `produced_by: "PERSISTENCE_WRITER"` plus the upstream role that requested the write
### 7.10 OBSIDIAN_WRITER
- **Reads:** Run artifacts
- **Writes:** `~/SecondBrain/cee/runs/<run_id>.md`, `~/SecondBrain/cee/skills/<slug>.md`
- **Audit:** failures logged but non-blocking per section 00 Rule 9
### 7.11 NOTION_WRITER
- **Reads:** promotion queue, Run artifacts marked for promotion
- **Writes:** Notion pages under "Skill Promotions" section
- **Audit:** queue position, success/failure, Notion page URL on success
### 7.12 BIBLE_LOADER
- **Reads:** `~/cee/bible/`, `.sync_meta.json`
- **Writes:** in-memory bible state
- **Audit:** which sections loaded, hash of each
### 7.13 BOOT_SEQUENCER
- **Reads:** environment, `~/cee/`, all registries
- **Writes:** rebuilt registries, boot log
- **Audit:** every boot step's pass/fail logged
### 7.14 EXECUTOR (external, slot)
- **Reads (Phase 1):** `FinalPrompt` via paste
- **Writes (Phase 1):** nothing in CEE; output is read back manually
- **Reads (Phase 2):** `FinalPrompt` via API
- **Writes (Phase 2):** API response into a buffer that `INTERPRETER` validates before persistence
---
## 8. Outputs Produced (Per Role)
Each system role produces exactly one artifact type. This is enforced by the schemas.
<table header-row="true">
<tr>
<td>Role</td>
<td>Produces</td>
</tr>
<tr>
<td>`INTERPRETER`</td>
<td>`IntentObject`</td>
</tr>
<tr>
<td>`CLASSIFIER`</td>
<td>`Classification`</td>
</tr>
<tr>
<td>`AGENT_SELECTOR`</td>
<td>`AgentPlan`</td>
</tr>
<tr>
<td>`SKILL_ENGINE`</td>
<td>`SkillSet` (+ optional [SKILL.md](http://SKILL.md) files)</td>
</tr>
<tr>
<td>`STRATEGY_BUILDER`</td>
<td>`ExecutionStrategy`</td>
</tr>
<tr>
<td>`PROMPT_BUILDER`</td>
<td>`FinalPrompt`</td>
</tr>
<tr>
<td>`SAFETY_GATE`</td>
<td>safety-annotated `FinalPrompt`</td>
</tr>
<tr>
<td>`PERSISTENCE_WRITER`</td>
<td>filesystem state changes</td>
</tr>
<tr>
<td>`OBSIDIAN_WRITER`</td>
<td>vault state changes</td>
</tr>
<tr>
<td>`NOTION_WRITER`</td>
<td>Notion state changes</td>
</tr>
<tr>
<td>`BIBLE_LOADER`</td>
<td>in-memory bible state</td>
</tr>
<tr>
<td>`BOOT_SEQUENCER`</td>
<td>boot log + rebuilt registries</td>
</tr>
</table>
A role that produces something not in this table is a bug.
---
## 9. Agent + Skill Implications
### 9.1 Agents are not roles
Claude Code subagents in `~/cee/.claude/agents/*.md` are *invoked by* the `AGENT_SELECTOR` role; they are not themselves roles in this taxonomy. Subagents act inside the executor, not inside CEE. The distinction matters: roles in this page are CEE-internal; subagents are executor-internal.
### 9.2 Skills are not roles
Same logic. [SKILL.md](http://SKILL.md) files are referenced by `PROMPT_BUILDER` and loaded by the `EXECUTOR`. The `SKILL_ENGINE` is the role; the Skills themselves are artifacts.
### 9.3 Why this distinction is enforced
If subagents were roles in CEE's taxonomy, the boundary between CEE (which generates prompts) and the executor (which runs them) collapses. CEE's job ends when `FinalPrompt` is delivered. Anything happening inside the executor is the executor's domain.
---
## 10. Edge Cases
**EC1 — OPERATOR runs a CLI command CEE doesn't recognize.**
CLI rejects with a list of valid commands. No role action attempted.
**EC2 — A system role fails mid-Run.**
`PERSISTENCE_WRITER` records the partial state. The Run is marked `failed_at_<role>` with the exact role that failed. `OPERATOR` can replay with `cee replay <run_id>`.
**EC3 — Two roles try to write to the same file.**
Filesystem-level lock at the writer module. Second write blocks until first completes. If first write fails, second never starts.
**EC4 — A Skill generated by ****`SKILL_ENGINE`**** is rejected by ****`OPERATOR`**** at promotion time.**
The Skill remains in `FILESYSTEM_CANON` (still usable for Runs) and `OBSIDIAN_VAULT`. The promotion candidate page in Notion is moved to a "Rejected Promotions" archive. Run artifacts referencing the Skill are unaffected.
**EC5 — ****`EXECUTOR`**** (Phase 1) returns garbled output that the OPERATOR pastes back to CEE.**
`INTERPRETER` detects the response is non-actionable, marks it as a failed execution, and offers to replay the Run.
**EC6 — ****`NOTION_WRITER`**** is offline at end of Run.**
Promotion queue absorbs the write. Run artifacts in `FILESYSTEM_CANON` and `OBSIDIAN_VAULT` are unaffected.
**EC7 — ****`OPERATOR`**** edits a **[**SKILL.md**](http://SKILL.md)** by hand.**
Filesystem is canonical, so the edit takes effect immediately. The Skill registry is rebuilt on next boot. If the edit invalidates frontmatter, boot flags it as a stale Skill.
**EC8 — A future role is needed (e.g., ****`MULTI_USER_OPERATOR`****).**
Bible update required. Adding a role at runtime is forbidden.
**EC9 — ****`OPERATOR`**** and ****`BIBLE_LOADER`**** disagree about bible content.**
`OPERATOR` wins, but only via Notion. The `OPERATOR` edits Notion; `BIBLE_LOADER` syncs. The `OPERATOR` does not edit `~/cee/bible/` directly — that file is a mirror, not a source.
**EC10 — A role is invoked outside its declared surface.**
Module-level enforcement raises `RoleSurfaceViolation`. Run halts. Logged with role name and the attempted out-of-surface action.
---
## 11. Failure Modes
### 11.1 Role spoofing
**Failure:** code outside a role's module sets `produced_by` to that role's name.
**Detection:** `produced_by` is set automatically by the role's writer wrapper, not as a free-form parameter.
**Recovery:** code review; tests in section 18 assert that artifacts can only be produced via the wrapper.
### 11.2 Authority escalation
**Failure:** a system role attempts a canon-modifying action (e.g., `CLASSIFIER` tries to edit the bible).
**Detection:** writer modules for canon (`NOTION_WRITER` to bible, `PERSISTENCE_WRITER` to bible mirror) reject any caller that isn't `OPERATOR`.
**Recovery:** `RoleAuthorityError`; Run halts.
### 11.3 Substrate cross-contamination
**Failure:** `OBSIDIAN_WRITER` accidentally writes to filesystem canon, or vice versa.
**Detection:** each writer module is path-restricted at the OS level and validated by tests.
**Recovery:** `SubstrateBoundaryError`; Run halts; bug fix required.
### 11.4 Anonymous artifact
**Failure:** an artifact is written without `produced_by`.
**Detection:** schema validation rejects.
**Recovery:** Run halts at the writer; root cause is a missing wrapper call.
### 11.5 EXECUTOR contract drift
**Failure:** Phase 1 paste-based executor and Phase 2 API executor produce different output shapes.
**Detection:** the executor adapter normalizes to a single response schema; mismatches caught by adapter tests.
**Recovery:** adapter is the only thing that changes between phases; if the contract drifts, adapter tests catch it.
### 11.6 OPERATOR makes a destructive bible change
**Failure:** OPERATOR removes a `task_type` from the closed enum mid-flight.
**Detection:** `BIBLE_LOADER` cross-section consistency check on next boot.
**Recovery:** boot halts with diff. OPERATOR must reconcile (restore the task_type or migrate referencing sections).
### 11.7 Multi-actor race condition
**Failure:** OPERATOR runs `cee promote` while a Run is mid-flight and the promotion targets the same Skill the Run is generating.
**Detection:** filesystem-level lock on `~/cee/skills/<slug>/`.
**Recovery:** second action blocks; first completes; second proceeds with updated state.
### 11.8 Audit log corruption
**Failure:** `~/cee/audit/cli.log` is deleted or truncated.
**Detection:** boot checks for log file integrity.
**Recovery:** boot warns but does not halt (audit loss is recoverable; system function is not). New entries append from boot timestamp forward.
---
## 12. Build Notes for Claude Code
- **Role declarations in code.** Each role has a corresponding Python class in `~/cee/roles/<role_name>.py`. The class declares `name`, `allowed_reads: list[Path]`, `allowed_writes: list[Path]`, `produces: type`. The class is the enforcement point.
- **Writer wrappers.** No module writes directly with `open()`. All writes go through `roles.PersistenceWriter.write()` (or its substrate-specific equivalents). The wrapper sets `produced_by` automatically and validates the path against `allowed_writes`.
- **Provenance is a Pydantic field.** Every artifact schema in `~/cee/schemas/` includes `produced_by: RoleEnum` as required. Validation fails if missing.
- **Audit log location.** `~/cee/audit/` contains `cli.log`, `roles.log`, `boot.log`. Append-only. Daily rotation. Not synced to Obsidian or Notion (audit is filesystem-only).
- **Surface enforcement tests.** Section 18 must include a test per role asserting that calls outside `allowed_writes` raise `RoleSurfaceViolation`.
- **Phase 2 readiness.** The `EXECUTOR` role's interface is a Python protocol with `send(prompt) -> response`. Phase 1 implementation: `PasteExecutor` (no-op for sending; manual paste for receiving). Phase 2 implementation: `APIExecutor` (Anthropic SDK). Other modules depend on the protocol, not the implementation.
- **Role enum lives in one file.** `~/cee/roles/__init__.py` contains the `RoleEnum`. Adding a role requires editing this file *and* this bible page in lockstep. Boot validates the enum matches the bible.
---
## 13. Definition of Done
This page is complete — and the role system is unblocked for build — when:
- [ ] Every role in §4 has a Python class in `~/cee/roles/`.
- [ ] Every role has its `allowed_reads` and `allowed_writes` declared and tested.
- [ ] Every artifact schema in `~/cee/schemas/` has a required `produced_by` field.
- [ ] The writer wrappers exist and are the only path to substrate writes.
- [ ] The `RoleEnum` in code matches §4 in this page.
- [ ] Section 18 includes one test per failure mode in §11.
- [ ] An end-to-end Run audit-trace shows every artifact's `produced_by` correctly populated.
- [ ] Phase 2 transition can be done by swapping the `EXECUTOR` implementation only — verified by walking the import graph.
---
## 14. Final Statement
Roles are the smallest unit of trust in CEE. Every action has an actor; every actor has a surface; every surface has a boundary. Without these, "safe" and "deterministic" are aspirations. With these, they are enforceable.
