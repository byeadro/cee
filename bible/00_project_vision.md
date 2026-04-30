---
notion_section: 00
notion_title: 00 — PROJECT VISION
mirrored_at: 2026-04-30
---

# 00 — PROJECT VISION
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes (see §12 Boot Sequence)
> **Consumers of this page:** human engineers, Claude Code at runtime, CEE itself when reasoning about its own purpose.
---
## 1. What This Is
The **Claude Execution Engine (CEE)** is a local system that converts unstructured human input into a complete, validated, paste-ready Claude prompt — every time, deterministically.
CEE is **not** a prompt. It is **not** a chatbot. It is an executable architecture, distributed across three substrates:
- **Filesystem** (`~/cee/`) — canonical source of truth for code, Skills, agents, and generated prompts. This is what Claude Code actually loads.
- **Obsidian vault** (`~/SecondBrain/cee/`) — the human-readable thinking layer. Every CEE run writes a markdown note linking input → classification → output.
- **Notion** (this System Design Bible) — the architectural spec. Humans edit it here. CEE reads it on boot to load its own rules.
The unit of work is a **Run**: one messy human input enters, one validated artifact bundle exits.
A Run produces, in order:
1. An `IntentObject` (interpreter output)
2. A `Classification` (task type + complexity score)
3. An `AgentPlan` (one or more `.claude/agents/*.md` references)
4. A `SkillSet` (existing or newly generated `SKILL.md` files)
5. An `ExecutionStrategy` (steps, validation gates, stop conditions)
6. A `FinalPrompt` (the paste-ready artifact, the deliverable)
Phase 1 (current build): a human pastes the `FinalPrompt` into [Claude.ai](http://Claude.ai) or Claude Code.
Phase 2 (planned): the Anthropic API replaces the manual paste. The contract of `FinalPrompt` does not change between phases — that is the point of the architecture.
---
## 2. Why This Matters
### 2.1 The interface, not the model, is the bottleneck
Claude is a high-capability model bottlenecked by an under-specified interface. Every quality failure traces to one of:
- input that under-specifies the goal
- prompts missing role, constraint, or output contract
- wrong agent posture for the task
- repeated re-explanation of context the user already wrote down once
- silent hallucination from missing grounding
- destructive action with no validation gate
CEE eliminates these by making the *interface* deterministic, even when the input is not.
### 2.2 The user-facing claim
> The user must only do three things: **think → type → paste.** Everything between "type" and "paste" is CEE's job.
### 2.3 Quantified before/after
<table header-row="true">
<tr>
<td>Failure mode under raw prompting</td>
<td>CEE behavior</td>
</tr>
<tr>
<td>User forgets to specify output format</td>
<td>Required field in `FinalPrompt`; Run fails validation if absent</td>
</tr>
<tr>
<td>User picks wrong agent posture (or none)</td>
<td>Classifier + AgentPlan selects from a closed enum</td>
</tr>
<tr>
<td>Same task re-explained across sessions</td>
<td>Skill is generated on first occurrence, reused on every subsequent occurrence</td>
</tr>
<tr>
<td>Hallucination from missing source</td>
<td>Grounding rules enforced; `FinalPrompt` declares allowed sources explicitly</td>
</tr>
<tr>
<td>Sensitive data leaks into prompt</td>
<td>Security layer redacts before `FinalPrompt` is emitted</td>
</tr>
<tr>
<td>Over-engineered prompt for trivial task</td>
<td>Complexity score routes LOW tasks to a single-agent path with no orchestrator</td>
</tr>
</table>
---
## 3. Core Requirements
CEE MUST, on every Run:
1. Accept free-text input of any length, including fragments, voice-transcribed dumps, and pasted code.
2. Produce a deterministic `IntentObject` from the input — same input ⇒ same intent extraction ±tokenization noise.
3. Classify the task against a **closed enum** of task types (see §6).
4. Score complexity on a defined rubric (see §6.3) — never "vibes-based."
5. Select agents from `~/cee/agents/` and Skills from `~/cee/skills/` using a deterministic resolver.
6. Generate new Skills when no existing Skill covers a required capability — and persist them to filesystem, Obsidian, and (on user confirmation) Notion.
7. Produce a `FinalPrompt` that is structurally complete by schema (see §7) — missing-field validation must fail the Run loud, not silently.
8. Apply hallucination grounding rules and prompt-leak security rules per §10.
9. Refuse to emit a `FinalPrompt` when input is irrecoverably ambiguous; instead emit a `ClarificationRequest` with at most 3 targeted questions.
10. Log every Run to filesystem (canonical), Obsidian (human-readable), and Notion (when the Run produced a new Skill or agent).
CEE MUST NOT:
- Execute the `FinalPrompt` in Phase 1 — emit only.
- Modify the System Design Bible without explicit user instruction.
- Generate a Skill that overwrites an existing Skill with a different signature without a versioned upgrade path.
- Emit a `FinalPrompt` containing redacted-class data (see §10.2).
---
## 4. System Rules
These are invariants. Every module must hold them.
**Rule 1 — Closed enums over open language.**
Task types, complexity tiers, agent roles, and Skill categories are closed sets defined in this bible. The classifier never invents a new tier at runtime.
**Rule 2 — Deterministic resolution.**
Given the same `IntentObject`, the classifier, agent selector, and skill resolver must produce the same outputs. Non-determinism is treated as a bug.
**Rule 3 — Schema-validated artifacts.**
`IntentObject`, `Classification`, `AgentPlan`, `SkillSet`, `ExecutionStrategy`, and `FinalPrompt` all have JSON schemas in `~/cee/schemas/`. No artifact passes a module boundary without validating.
**Rule 4 — Skills are first-class persistent assets.**
A Skill is a `SKILL.md` file with YAML frontmatter, in the format Claude Code natively loads. CEE does not invent a parallel Skill format. If a capability is reusable, it becomes a [SKILL.md](http://SKILL.md) — full stop.
**Rule 5 — Agents are Claude Code subagents.**
Agents live at `~/cee/.claude/agents/*.md` in the format Claude Code natively loads. CEE selects, never roleplays.
**Rule 6 — Complexity scales the system, not the user effort.**
LOW Runs use a single agent and zero generated Skills if existing ones cover. EXTREME Runs may use orchestrator + 4+ subagents + multiple Skills. The user does not choose — the classifier does.
**Rule 7 — Safety is conditional and explicit.**
Grounding, security, and human-confirmation gates activate based on classification flags. They are not always-on (which would slow every Run) and not opt-in (which would let the user forget). The classifier sets the flags.
**Rule 8 — The bible is the rulebook.**
On every Run, CEE re-reads the relevant bible sections from filesystem mirrors of these Notion pages. If the bible says X and CEE behavior contradicts X, CEE behavior is wrong. There is no in-code override of the bible.
**Rule 9 — Three-substrate write order.**
On any state change: write to filesystem first (atomic), then Obsidian (idempotent markdown), then Notion (only when promoting a Skill, agent, or rule to the bible). If Obsidian or Notion writes fail, filesystem still wins; the run is still valid.
**Rule 10 — Loud failure over silent assumption.**
If CEE cannot determine intent, it asks. If it cannot validate an artifact, it errors. It never proceeds on a guess.
---
## 5. Detailed Workflow
A Run executes the following pipeline. Each step has a defined input and output artifact. Every artifact is validated against schema before passing to the next step.
### Step 0 — Boot
CEE loads:
- The current bible state (sections 00–22, mirrored in `~/cee/bible/`)
- The Skill registry (`~/cee/skills/index.json`, regenerated from filesystem)
- The Agent registry (`~/cee/agents/index.json`)
- The schema directory (`~/cee/schemas/`)
- The last 50 Run logs (for similarity-based Skill suggestion)
If any of these fail to load, CEE halts. There is no degraded mode.
### Step 1 — Capture
Input: free-text from the user (CLI, file, or — Phase 2 — API).
Output: `RawInput` object with `{text, timestamp, source, attachments[]}`.
Attachments are read but not yet interpreted. They are passed alongside `IntentObject` to downstream steps.
### Step 2 — Interpretation
Module: `interpreter`.
Input: `RawInput`.
Output: `IntentObject` with fields:
```javascript
{
  "goal": "single-sentence statement of what the user wants",
  "deliverable": "the concrete artifact the user expects back",
  "constraints": ["explicit constraint 1", "explicit constraint 2"],
  "implicit_assumptions": ["assumption CEE is making, flagged for user review"],
  "ambiguity_score": 0.0–1.0,
  "domain": "code | writing | analysis | research | ops | personal | other",
  "raw_signals": ["urgency markers", "tone markers", "domain markers"]
}
```
If `ambiguity_score > 0.6`, the pipeline halts and emits a `ClarificationRequest` (max 3 questions, in `ask_user_input_v0`-style format). Otherwise it proceeds.
### Step 3 — Classification
Module: `classifier`.
Input: `IntentObject`.
Output: `Classification` with:
```javascript
{
  "task_type": "BUILD | ANALYZE | DEBUG | WRITE | RESEARCH | TRANSFORM | DECIDE | ORCHESTRATE",
  "complexity": "LOW | MEDIUM | HIGH | EXTREME",
  "complexity_score": 0–100,
  "complexity_components": {
    "input_ambiguity": 0–25,
    "output_structure": 0–25,
    "agent_count_required": 0–25,
    "skill_count_required": 0–25
  },
  "flags": {
    "needs_grounding": bool,
    "sensitive_data": bool,
    "destructive_potential": bool,
    "requires_human_gate": bool
  }
}
```
Tier thresholds: LOW 0–24, MEDIUM 25–49, HIGH 50–74, EXTREME 75–100.
### Step 4 — Agent Selection
Module: `agent_selector`.
Input: `Classification`.
Output: `AgentPlan` referencing files in `~/cee/.claude/agents/`:
- LOW → 1 agent (the primary).
- MEDIUM → 1 primary + optional 1 critic.
- HIGH → primary + critic + optimizer.
- EXTREME → orchestrator + primary + critic + optimizer + domain specialist(s).
The selector reads agent frontmatter (capabilities, allowed tools, posture) and matches against `task_type` and `domain`.
### Step 5 — Skill Resolution
Module: `skill_engine`.
Input: `IntentObject`, `Classification`, `AgentPlan`.
Output: `SkillSet`.
Resolution order:
1. **Match.** Search `~/cee/skills/index.json` for Skills whose `description` semantically covers a required capability.
2. **Reuse.** If match score ≥ threshold, include the existing Skill.
3. **Generate.** If no match, generate a new [SKILL.md](http://SKILL.md) (with YAML frontmatter, instructions, and example) and write to `~/cee/skills/<slug>/SKILL.md`. Mirror to Obsidian. Flag for promotion to Notion at end of Run.
4. **Conflict.** If a generated Skill would shadow an existing one with a different signature, halt and emit a `SkillConflictError`.
### Step 6 — Execution Strategy
Module: `strategy_builder`.
Input: all prior artifacts.
Output: `ExecutionStrategy` with ordered steps, validation checkpoints between steps, stop conditions, and rollback notes.
For LOW tasks this is a 1-step strategy. For EXTREME it can be a 10+ step DAG.
### Step 7 — Prompt Generation
Module: `prompt_builder`.
Input: all prior artifacts.
Output: `FinalPrompt` — an XML-tagged block containing:
```javascript
<context>...</context>
<role>...</role>
<task>...</task>
<agents>...</agents>
<skills>...</skills>
<execution_plan>...</execution_plan>
<constraints>...</constraints>
<grounding_rules>...</grounding_rules>
<output_format>...</output_format>
<stop_conditions>...</stop_conditions>
```
Schema validation runs here. A `FinalPrompt` missing any required tag is rejected.
### Step 8 — Safety Pass
Module: `safety_gate`.
- If `flags.sensitive_data`, run redaction.
- If `flags.requires_human_gate`, mark the FinalPrompt with a `[HUMAN CONFIRM BEFORE EXECUTION]` banner and emit the `ExecutionStrategy` separately for review.
- If `flags.destructive_potential`, require the user to type confirmation in the next turn before the FinalPrompt is delivered.
### Step 9 — Persistence
In order:
1. Write Run artifacts to `~/cee/runs/<run_id>/` (filesystem, canonical).
2. Write a Run note to `~/SecondBrain/cee/runs/<run_id>.md` (Obsidian).
3. If the Run generated new Skills/agents, write a promotion candidate page to Notion under the `Skill Promotions` section.
### Step 10 — Deliver
Output to user: the `FinalPrompt` block, ready to paste. Plus, if requested, the `ExecutionStrategy` and a one-line summary of which agents and Skills it references.
---
## 6. Data / Inputs Needed
### 6.1 Required input
- `RawInput.text` — non-empty free text.
### 6.2 Optional input
- File attachments (`.txt`, `.md`, `.pdf`, `.docx`, `.xlsx`, code files, images).
- Explicit constraints ("must run on Python 3.11", "cannot use external APIs").
- Reference Run ID (for "do this again but with X changed").
- Target executor hint (`claude.ai | claude_code | api`) — affects formatting only.
### 6.3 Internal inputs CEE loads on every Run
- Bible mirror at `~/cee/bible/`.
- Skill registry at `~/cee/skills/index.json`.
- Agent registry at `~/cee/agents/index.json`.
- Schema directory at `~/cee/schemas/`.
- Recent Run logs at `~/cee/runs/` (last 50 by mtime).
---
## 7. Outputs Produced
Every successful Run produces:
<table header-row="true">
<tr>
<td>Artifact</td>
<td>Location</td>
<td>Purpose</td>
</tr>
<tr>
<td>`FinalPrompt` (XML block)</td>
<td>stdout + `~/cee/runs/<id>/prompt.xml`</td>
<td>The deliverable; user pastes this</td>
</tr>
<tr>
<td>`IntentObject`</td>
<td>`~/cee/runs/<id>/intent.json`</td>
<td>Audit + replay</td>
</tr>
<tr>
<td>`Classification`</td>
<td>`~/cee/runs/<id>/classification.json`</td>
<td>Audit + tuning</td>
</tr>
<tr>
<td>`AgentPlan`</td>
<td>`~/cee/runs/<id>/agents.json`</td>
<td>Which agents the prompt references</td>
</tr>
<tr>
<td>`SkillSet`</td>
<td>`~/cee/runs/<id>/skills.json`</td>
<td>Which Skills the prompt references</td>
</tr>
<tr>
<td>`ExecutionStrategy`</td>
<td>`~/cee/runs/<id>/strategy.json`</td>
<td>Step-by-step plan</td>
</tr>
<tr>
<td>Run note</td>
<td>`~/SecondBrain/cee/runs/<id>.md`</td>
<td>Human-readable record</td>
</tr>
<tr>
<td>New Skill files (if any)</td>
<td>`~/cee/skills/<slug>/SKILL.md`</td>
<td>Reusable for future Runs</td>
</tr>
<tr>
<td>Promotion candidates (if any)</td>
<td>Notion under `Skill Promotions`</td>
<td>Awaits human approval</td>
</tr>
</table>
A failed Run produces a `RunError` with the failing step, the schema violation, and a remediation suggestion. The `RawInput` is still preserved.
---
## 8. Agent + Skill Implications
### 8.1 Agents
- Native Claude Code subagents in `~/cee/.claude/agents/*.md`.
- Each has YAML frontmatter declaring `name`, `posture`, `allowed_tools`, `capabilities`, `task_types_supported`.
- CEE never invents an agent at runtime. If no agent fits, it generates a new agent file (same way it generates Skills) and promotes to Notion for review.
- Agent count per Run is determined by complexity tier (§5 Step 4), not user choice.
### 8.2 Skills
- Native Claude Code [SKILL.md](http://SKILL.md) files in `~/cee/skills/<slug>/SKILL.md`.
- Frontmatter: `name`, `description`, `triggers`, `inputs`, `outputs`, `version`.
- Skills are written to be loaded by Claude Code, not by CEE. CEE only references them in the `FinalPrompt`.
- The Skill registry is regenerated from filesystem on every boot. There is no separate database.
### 8.3 The promotion pipeline
A new Skill or agent flows: filesystem (auto) → Obsidian (auto) → Notion (manual approval). Notion is the "promoted to canon" state. Nothing in `~/cee/` is deleted when a Skill is rejected for promotion — it stays usable, just not canonical.
---
## 9. Edge Cases
**E1 — Input is one word.**
Example: "fix it." Interpreter sets `ambiguity_score = 1.0`, pipeline halts, ClarificationRequest emitted: "What is 'it'? What does 'fixed' look like? What's the deliverable?"
**E2 — Input contradicts itself.**
Example: "I want a 5-page essay in 10 words." Interpreter flags contradiction in `implicit_assumptions`, classifier sets `flags.needs_grounding=true`, prompt generation includes a `<contradiction_note>` tag asking the executor to resolve.
**E3 — Input is enormous (\>10k tokens).**
Interpreter chunks and summarizes attachments, but `RawInput.text` is preserved verbatim in the FinalPrompt context. If total exceeds executor's context window, `ExecutionStrategy` includes a chunking plan.
**E4 — Required Skill exists but is stale.**
Skill registry compares `version` against schema; if frontmatter is missing required fields added in a later schema version, Skill is flagged stale and CEE generates a v2 alongside it. Old version is preserved.
**E5 — Two Skills both match.**
Skill resolver picks higher specificity (longer matching description, more recent `version`, more triggers matched). Tie → earlier created.
**E6 — User pastes a previous FinalPrompt as new input.**
Interpreter detects CEE schema markers, asks: "Re-run the prior generation, modify it, or treat as new task?"
**E7 — Sensitive data detected.**
Security layer redacts `secrets`, `keys`, `auth tokens`, `personal identifiers`, `client names flagged in ~/.cee/redact_list`. Redaction happens before `FinalPrompt` is written to any substrate.
**E8 — Skill generation produces a Skill identical to an existing one.**
Resolver detects identity (hash of normalized content), discards the new one, reuses existing.
**E9 — Notion is offline.**
Filesystem and Obsidian writes succeed; Notion promotion is queued in `~/cee/promotion_queue.json` for retry on next boot.
**E10 — Bible has been edited in Notion since last boot.**
Boot sequence detects diff, updates filesystem mirror, logs the diff to Obsidian for review. CEE does not auto-apply destructive bible changes (e.g., removing a task type) — those require manual sync confirmation.
---
## 10. Failure Modes
Failure modes are categorized by which module fails and how the system recovers.
### 10.1 Interpreter failures
- **F1.1** — Interpreter returns malformed `IntentObject`. → Schema validator rejects, Run halts at Step 2, error returned. No artifact written.
- **F1.2** — Interpreter under-extracts (misses goal). → Detected only by user feedback in Phase 1; in Phase 2, by output validator comparing `FinalPrompt` against `IntentObject` for goal coverage.
- **F1.3** — Interpreter hallucinates a goal not in input. → Flagged when `implicit_assumptions` count exceeds threshold; pipeline halts and asks user.
### 10.2 Classifier failures
- **F2.1** — Wrong `task_type`. → Detected by mismatch between `task_type` and required Skill capabilities; classifier re-runs once with explicit prompt; if still wrong, asks user.
- **F2.2** — Complexity miscalibrated. → Auto-tuning loop in `~/cee/runs/` accumulates user corrections; classifier weights update on weekly review (manual until tuning UI is built).
### 10.3 Agent selector failures
- **F3.1** — No agent matches. → CEE generates an agent stub from the closest match, marks it `needs_review`, proceeds with stub.
- **F3.2** — Agents conflict (two primaries selected). → Halt; emit error.
### 10.4 Skill engine failures
- **F4.1** — Skill generation produces invalid YAML frontmatter. → Generator retries up to 2x; on third failure, halt and emit error with the bad frontmatter.
- **F4.2** — Skill conflicts with existing Skill (same name, different signature). → `SkillConflictError`; user must rename or version manually.
- **F4.3** — Skill registry corrupted. → Boot regenerates from filesystem; if regeneration fails, halt with explicit recovery instructions.
### 10.5 Prompt builder failures
- **F5.1** — Required XML tag missing. → Schema rejection; Run halts; error names the missing tag.
- **F5.2** — `FinalPrompt` exceeds executor context window. → Builder chunks and emits a multi-part FinalPrompt with explicit ordering; user pastes in sequence.
### 10.6 Persistence failures
- **F6.1** — Filesystem write fails (disk full, permissions). → Halt entire Run; nothing is partial-written.
- **F6.2** — Obsidian write fails. → Log warning, continue. Filesystem is canonical.
- **F6.3** — Notion write fails. → Queue for retry; do not block Run.
### 10.7 Bible failures
- **F7.1** — Bible mirror missing on boot. → Halt with explicit instruction to run `cee sync-bible`.
- **F7.2** — Bible contradicts itself across sections. → Detected by cross-section consistency check at boot; halt with diff.
### 10.8 User-side failures CEE must defend against
- **F8.1** — User pastes `FinalPrompt` into wrong executor. → `FinalPrompt` includes a `<target_executor>` tag; mismatched executor gets a banner suggesting rerun with corrected target.
- **F8.2** — User edits `FinalPrompt` and breaks it. → CEE does not own this. The XML schema is documented in §5 Step 7 so manual edits remain valid if the user respects it.
---
## 11. Build Notes for Claude Code
When implementing CEE in Claude Code:
- **Repo layout.** `~/cee/` contains: `interpreter/`, `classifier/`, `agent_selector/`, `skill_engine/`, `strategy_builder/`, `prompt_builder/`, `safety_gate/`, `persistence/`, `schemas/`, `skills/`, `.claude/agents/`, `bible/`, `runs/`, `promotion_queue.json`, `cli.py`.
- **Language.** Python 3.11+. Pydantic for schemas. Anthropic SDK for Phase 2.
- **CLI surface.** `cee run "<input>"`, `cee sync-bible`, `cee promote <skill_slug>`, `cee replay <run_id>`, `cee list-skills`, `cee list-agents`.
- **No hidden state.** Every state change writes to filesystem before any in-memory variable mutates. CEE must be fully reconstructable from `~/cee/`.
- **Idempotent boot.** `cee run` from a fresh shell must produce identical output to one immediately following another `cee run`. Boot is not allowed to depend on warm caches.
- **Schema-first.** Build the JSON schemas in `~/cee/schemas/` before writing module code. Modules are validated against schemas in CI.
- **Module isolation.** Each module is a Python package with a single public entry point (`run(input) -> output`) and is testable in isolation against its schema.
- **Obsidian writes.** Use a single `obsidian_writer.py` module; never write to the vault directly from anywhere else.
- **Notion writes.** Use the Notion MCP via `notion_writer.py`; rate-limit, retry, queue on failure.
- **Determinism.** Where Claude is called inside CEE (e.g., interpreter, classifier), use temperature 0 and a fixed system prompt loaded from filesystem.
- **Tests.** Each module has unit tests against schema. End-to-end tests replay golden Runs in `~/cee/runs/golden/` and assert artifact equality.
---
## 12. Boot Sequence
CEE rereads its own rulebook on every Run. This is the boot sequence executed by `cee run` before any input is processed:
**B1 — Verify environment.**
Check Python version, required packages, write permissions on `~/cee/`, `~/SecondBrain/cee/`. Halt on any failure.
**B2 — Load bible.**
Read every file in `~/cee/bible/`. These are filesystem mirrors of the Notion pages in this System Design Bible (00–22). If any file is missing or older than the Notion `updated_at` timestamp stored in `~/cee/bible/.sync_meta.json`, run `cee sync-bible` automatically — but only if the user has set `auto_sync: true` in `~/cee/config.toml`. Otherwise halt and instruct.
**B3 — Cross-section consistency check.**
Validate that closed enums referenced across sections (e.g., `task_type` values referenced in 00, 03, 08) match. Halt on any drift.
**B4 — Build Skill registry.**
Walk `~/cee/skills/`, parse each `SKILL.md` frontmatter, build `index.json`. Skills with invalid frontmatter are logged and skipped, not loaded.
**B5 — Build agent registry.**
Walk `~/cee/.claude/agents/`, parse frontmatter, build `index.json`.
**B6 — Load schemas.**
Pre-compile all Pydantic models from `~/cee/schemas/`.
**B7 — Load recent Runs.**
Index the last 50 Run logs by `IntentObject.goal` for similarity search during Skill resolution.
**B8 — Drain promotion queue.**
If `promotion_queue.json` has entries and Notion is reachable, attempt promotion writes. Failures stay queued.
**B9 — Ready.**
At this point the Run pipeline (§5 Step 1 onward) can begin. Boot is complete.
If any step B1–B7 fails, CEE halts. Boot is all-or-nothing. There is no degraded mode where CEE runs without its bible.
---
## 13. Definition of Done
This section is complete — and the CEE foundation is unblocked for build — when:
- [ ] Every artifact in §7 has a JSON schema in `~/cee/schemas/`.
- [ ] Every module in §11 has a public `run()` signature defined.
- [ ] The closed enum for `task_type` (§5 Step 3) is finalized in section 08.
- [ ] The complexity rubric (§5 Step 3) has scoring weights agreed in section 08.
- [ ] Every failure mode in §10 has a corresponding test case planned in section 18.
- [ ] The Boot Sequence in §12 is implemented end-to-end.
- [ ] A "hello-world" Run completes: input → all 7 output artifacts → user pastes prompt → Claude executes correctly.
- [ ] No section of this bible is contradicted by behavior in any module.
---
## 14. Final Statement
CEE eliminates the lossy step between human intent and Claude execution by replacing it with a deterministic, schema-validated, three-substrate system. The user thinks, types, and pastes. CEE handles every decision in between, the same way every time, with every decision auditable.
When CEE is done, the question "did I write a good prompt?" stops being a user concern. The user concern becomes "did I describe what I want?" — which is a question humans are already good at answering.
