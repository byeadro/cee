---
notion_section: 01
notion_title: 01 — REAL PROBLEM BREAKDOWN
mirrored_at: 2026-04-30
---

# 01 — REAL PROBLEM BREAKDOWN
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** define every failure mode in human↔Claude interaction precisely enough that each one maps to a specific module in CEE. If a problem is named here, it must be solved by a named module.
---
## 1. What This Is
This page enumerates the actual failure modes between human intent and Claude execution — the failures CEE was built to eliminate. Every problem in this section traces to either:
- a missing piece of structure between input and output, or
- a missing decision the user shouldn't have had to make.
This is not a list of complaints about prompting. It is the **requirements spec** for the CEE pipeline, expressed in problem form. Section 00 describes what CEE *is*. This section describes what CEE *defeats*.
The structure: one core problem → ten layered sub-problems → root cause → mapped solution per module → derived design principles.
---
## 2. Why This Matters
If CEE solves problems that don't exist, it's bloat. If CEE misses problems that do exist, it's incomplete. This page is the contract: every named problem here must have a named owner module in CEE. Anything not listed here is out of scope.
When a future engineer asks "why does CEE have a classifier?" — the answer must be on this page. When they ask "why doesn't CEE do X?" — the answer must be that X isn't on this page.
---
## 3. The Core Problem
> **Humans express intent in natural language. Claude executes against structured prompts. The translation between these two is a high-loss interface, and the loss is currently paid by the user, manually, every time.**
The failure isn't that Claude is bad. It isn't that humans are bad. It's that the interface between them is unstandardized, unaudited, and unmemoried — and the user is the only thing carrying the load across runs.
### 3.1 The mismatch table
<table header-row="true">
<tr>
<td>Human-native input</td>
<td>Claude-required input</td>
</tr>
<tr>
<td>Fragmented, mid-thought</td>
<td>Complete, single-pass</td>
</tr>
<tr>
<td>Implicit context</td>
<td>Explicit context block</td>
</tr>
<tr>
<td>Goal mixed with rationale</td>
<td>Goal isolated, role isolated, constraints isolated</td>
</tr>
<tr>
<td>Tone-driven</td>
<td>Schema-driven</td>
</tr>
<tr>
<td>Forgetting prior runs</td>
<td>Stateless unless told otherwise</td>
</tr>
<tr>
<td>One paragraph for everything</td>
<td>Tagged sections per concern</td>
</tr>
</table>
Every Run, the user re-bridges this mismatch. CEE bridges it once, then replays the bridge.
### 3.2 The compounding cost
The mismatch is not a one-time tax — it compounds:
- Every Run pays the structural-translation cost
- Every Run forgets the last Run's context, so the user re-explains
- Every Run risks a different output shape, so downstream tooling breaks
- Every Run has its own ad-hoc safety posture, so risky tasks slip through
CEE's job is to make this cost paid **once**, at architecture time, and then never again.
---
## 4. The Ten Problem Layers
Each layer is a distinct failure surface. Each maps to a specific CEE module.
### Layer 1 — Input under-specification (user-side)
**What goes wrong:** users write what they're thinking, not what Claude needs. Common omissions: deliverable format, success criteria, scope, constraints, audience.
**Example failure:** "build something that reads bills better." Missing: what "better" means, output shape, target user, what bill format, what currently happens, what success looks like.
**Why it persists:** users don't know what's missing because the cost of omission only shows up in Claude's output, after the fact.
**CEE module that owns this:** `interpreter`. Detects under-specification via `ambiguity_score`. Halts and emits `ClarificationRequest` with at most 3 targeted questions when score exceeds threshold.
### Layer 2 — No translation layer (system gap)
**What goes wrong:** there is no canonical converter from "human idea" to "machine-shaped instruction." Users guess at structure, sometimes copying templates from blog posts.
**Example failure:** the same user writes the same task three different ways across three sessions, gets three different output shapes.
**Why it persists:** prompt templates aren't context-aware; they're static. They don't observe the actual input and decide what structure it needs.
**CEE module that owns this:** the entire pipeline §5 in section 00 — but the linchpin is `prompt_builder`, which produces the standardized `FinalPrompt` schema regardless of how the input arrived.
### Layer 3 — Prompt engineering as a manual craft (skill gap)
**What goes wrong:** good prompts require role assignment, output format declaration, constraint enumeration, and grounding. Most users skip 2–4 of these.
**Example failure:** a user asks for "a strategy" with no role, no output format, no constraints. Output is a generic essay; user retries 3 times.
**Why it persists:** prompt engineering is treated as something users learn. CEE's position: users shouldn't have to. Treat it as compiler work.
**CEE module that owns this:** `prompt_builder` enforces the XML-tagged schema; missing tags fail validation.
### Layer 4 — Wrong agent posture (role gap)
**What goes wrong:** Claude takes whatever role the prompt implies. If the prompt implies nothing, Claude defaults to "helpful generalist," which is wrong for most non-trivial tasks.
**Example failure:** debugging task gets prose explanation instead of methodical diagnosis. Strategic decision gets a list of pros/cons instead of a stance.
**Why it persists:** users don't think in terms of "what role should Claude take." They think in terms of "what answer do I want."
**CEE module that owns this:** `classifier` (selects task_type) → `agent_selector` (maps task_type to agent file). Both deterministic, both bounded by closed enums.
### Layer 5 — No reusable capability layer (memory gap)
**What goes wrong:** every task is treated as new. The same instructions ("when summarizing legal docs, always extract X, Y, Z") get re-typed across sessions, often imperfectly.
**Example failure:** user writes a 200-word preamble explaining their preferred style for the 40th time.
**Why it persists:** there is no first-class "Skill" concept in raw prompting. Every prompt starts from zero.
**CEE module that owns this:** `skill_engine`. Skills are persistent [SKILL.md](http://SKILL.md) files. New repeat → generate Skill on first use, reference on every subsequent use. Stored in filesystem (canonical), Obsidian (human-readable), Notion (promoted on approval).
### Layer 6 — No execution strategy (orchestration gap)
**What goes wrong:** even good prompts fail because Claude executes them in one pass with no validation gates, no checkpoints, no stop conditions.
**Example failure:** user asks Claude to refactor a 500-line file. Claude rewrites it linearly, breaks tests, returns the broken version, user has to revert and try again.
**Why it persists:** prompts are usually structured as "do this," not "do this in steps with these checks."
**CEE module that owns this:** `strategy_builder`. Produces an ordered execution plan with validation checkpoints between steps and explicit stop conditions. For LOW-complexity tasks the plan is one step; for EXTREME it can be a 10+ step DAG.
### Layer 7 — Unstructured output (interface gap downstream)
**What goes wrong:** outputs come back in inconsistent shapes — sometimes prose, sometimes JSON, sometimes a mix — making programmatic consumption impossible.
**Example failure:** user wants a list of action items; Claude returns a paragraph with the items embedded.
**Why it persists:** users rarely declare an output schema, and "output as a list" is too weak a directive.
**CEE module that owns this:** `prompt_builder` — the `<output_format>` tag is required, schema-validated, and inferred from `task_type` when not user-specified.
### Layer 8 — Hallucination on unstated context
**What goes wrong:** when context is missing, Claude fills the gap. Sometimes correctly, sometimes not. Users can't tell which.
**Example failure:** user asks about a specific framework version; Claude invents API methods that don't exist.
**Why it persists:** raw prompting offers no mechanism to declare "only use sources X and Y."
**CEE module that owns this:** `safety_gate` enforces grounding rules; `prompt_builder` includes a `<grounding_rules>` tag declaring allowed sources, prohibited inferences, and required citation behavior.
### Layer 9 — Unintended data exposure
**What goes wrong:** users paste sensitive data (API keys, client names, internal docs) into prompts without thinking. The prompt persists in chat logs, telemetry, and — if shared — in unintended places.
**Example failure:** user pastes a stack trace containing a database connection string into Claude.
**Why it persists:** humans aren't natural redactors, especially mid-thought.
**CEE module that owns this:** `safety_gate`. Pattern-matched redaction (keys, tokens, emails, items in `~/.cee/redact_list`). Redaction happens before any substrate write.
### Layer 10 — Over-engineering by power users
**What goes wrong:** users who learn prompt engineering then over-apply it: 8 agents for a task that needs 1, 2000-word system prompts for trivial questions, complex orchestration for "rename this file."
**Example failure:** user asks Claude to capitalize a sentence and routes it through a 5-agent CrewAI pipeline.
**Why it persists:** complexity feels like sophistication. Without a forcing function, complexity grows monotonically.
**CEE module that owns this:** `classifier`'s complexity score. LOW tasks are explicitly forbidden from spawning more than 1 agent. The classifier is the floor and the ceiling.
---
## 5. Root Cause
All ten layers reduce to one root:
> **There is no standardized, deterministic, persistent interface between human intent and AI execution.**
Three properties of the missing interface:
- **Standardized.** Same artifact shape every time, regardless of input shape.
- **Deterministic.** Same input ⇒ same intermediate decisions ⇒ same output shape.
- **Persistent.** What the system learns once is kept and reused. The user does not carry the memory.
CEE is exactly that interface.
---
## 6. What Existing Tools Get Wrong
<table header-row="true">
<tr>
<td>Tool category</td>
<td>What they do</td>
<td>What they miss</td>
</tr>
<tr>
<td>Static prompt templates</td>
<td>Provide a structure</td>
<td>No input awareness, no agent selection, no skill memory</td>
</tr>
<tr>
<td>Prompt generators (web tools)</td>
<td>Auto-format text into a prompt</td>
<td>Generic structure; no classification; no determinism; no persistence</td>
</tr>
<tr>
<td>AI assistants (default chat)</td>
<td>Reactive turn-by-turn response</td>
<td>No system memory across runs; no enforced output schema</td>
</tr>
<tr>
<td>Documentation, courses, blog posts</td>
<td>Teach prompting</td>
<td>Don't build a system; load stays on the user</td>
</tr>
<tr>
<td>NotebookLM, RAG tools</td>
<td>Ground outputs in user-provided sources</td>
<td>Strong on retrieval, weak on execution structure and agent posture</td>
</tr>
<tr>
<td>Workflow tools (n8n, Zapier + LLM)</td>
<td>Chain calls</td>
<td>No interpretation layer; require pre-structured input</td>
</tr>
<tr>
<td>Agent frameworks (CrewAI, AutoGen)</td>
<td>Spawn multi-agent flows</td>
<td>No classification step deciding whether multi-agent is even appropriate; users wire agents manually</td>
</tr>
</table>
CEE's distinction: it sits *upstream* of the executor. It doesn't run agents — it decides which agents Claude Code should run, then writes the prompt that tells Claude Code to run them.
---
## 7. Problem-to-Module Mapping
Authoritative table. Every named problem ↔ named module.
<table header-row="true">
<tr>
<td>Problem layer</td>
<td>Symptom</td>
<td>CEE module</td>
<td>Artifact produced</td>
</tr>
<tr>
<td>L1 — Under-specification</td>
<td>Missing goal/format/constraints</td>
<td>`interpreter`</td>
<td>`IntentObject`</td>
</tr>
<tr>
<td>L2 — No translation layer</td>
<td>Inconsistent prompt shape</td>
<td>`prompt_builder` (structural)</td>
<td>`FinalPrompt`</td>
</tr>
<tr>
<td>L3 — Manual prompt engineering</td>
<td>Missing role/output/grounding</td>
<td>`prompt_builder` (schema enforcement)</td>
<td>Validated `FinalPrompt`</td>
</tr>
<tr>
<td>L4 — Wrong agent posture</td>
<td>Wrong role for task</td>
<td>`classifier`  • `agent_selector`</td>
<td>`Classification`, `AgentPlan`</td>
</tr>
<tr>
<td>L5 — No reusable capability layer</td>
<td>Re-explaining the same thing</td>
<td>`skill_engine`</td>
<td>`SkillSet`  • persisted `SKILL.md` files</td>
</tr>
<tr>
<td>L6 — No execution strategy</td>
<td>Single-pass execution, no validation</td>
<td>`strategy_builder`</td>
<td>`ExecutionStrategy`</td>
</tr>
<tr>
<td>L7 — Unstructured output</td>
<td>Output shape varies</td>
<td>`prompt_builder` `<output_format>` tag</td>
<td>`FinalPrompt` (with required schema)</td>
</tr>
<tr>
<td>L8 — Hallucination on missing context</td>
<td>Invented facts</td>
<td>`safety_gate`  • `prompt_builder` `<grounding_rules>`</td>
<td>Grounded `FinalPrompt`</td>
</tr>
<tr>
<td>L9 — Data exposure</td>
<td>Sensitive data in prompt</td>
<td>`safety_gate` (redaction)</td>
<td>Redacted artifacts</td>
</tr>
<tr>
<td>L10 — Over-engineering</td>
<td>Complex prompt for trivial task</td>
<td>`classifier` (complexity score floor/ceiling)</td>
<td>`Classification` with capped complexity</td>
</tr>
</table>
If a future feature does not solve a problem in this table, it does not belong in CEE.
---
## 8. Internal Logic — Decision Flow
The decisions CEE makes on every Run, in order. This is the explicit branching logic the modules implement.
### 8.1 Decision 1 — Is the input executable?
Inputs to decision: `RawInput.text`, `IntentObject.ambiguity_score`.
```javascript
if text is empty or whitespace only:
    halt with InputEmptyError
elif ambiguity_score > 0.6:
    emit ClarificationRequest, halt this Run, await follow-up
elif ambiguity_score in [0.3, 0.6]:
    proceed but log implicit_assumptions visibly in FinalPrompt
else:
    proceed silently
```
### 8.2 Decision 2 — What task type?
Closed enum: `BUILD | ANALYZE | DEBUG | WRITE | RESEARCH | TRANSFORM | DECIDE | ORCHESTRATE`.
Classification rules (precedence top to bottom — first match wins):
- Output is code or system → `BUILD`
- Input contains broken behavior + asks for fix → `DEBUG`
- Input asks "what does this mean" or "find patterns in" → `ANALYZE`
- Output is prose deliverable (essay, post, doc) → `WRITE`
- Input asks for sourced information → `RESEARCH`
- Input is data + asks for shape change → `TRANSFORM`
- Input asks for a recommendation or stance → `DECIDE`
- Input requires coordinating multiple of the above → `ORCHESTRATE`
If two rules match, the classifier emits `Classification` with both candidates and a confidence score; selector picks higher confidence. Tie → escalate to user.
### 8.3 Decision 3 — What complexity tier?
Score = `input_ambiguity (0–25) + output_structure (0–25) + agent_count_required (0–25) + skill_count_required (0–25)`.
- 0–24 → LOW (1 agent, 0–1 Skill, 1-step strategy)
- 25–49 → MEDIUM (1 primary + optional critic, 1–3 Skills, 2–3 step strategy)
- 50–74 → HIGH (primary + critic + optimizer, 3–5 Skills, multi-step strategy)
- 75–100 → EXTREME (orchestrator + 3+ subagents, 3+ Skills, multi-step DAG with validation gates)
Hard caps: LOW Runs cannot exceed 1 agent regardless of input. EXTREME Runs cannot proceed without `flags.requires_human_gate = true`.
### 8.4 Decision 4 — Reuse or generate Skill?
```javascript
for each required_capability in IntentObject:
    matches = skill_index.search(required_capability)
    if matches.top_score >= 0.85:
        reuse(matches.top)
    elif matches.top_score >= 0.60:
        ask user: reuse, modify, or generate new?
    else:
        generate new SKILL.md
        write to filesystem, Obsidian; queue for Notion promotion
```
### 8.5 Decision 5 — Apply safety gates?
```javascript
if flags.sensitive_data:
    run redaction before any substrate write
if flags.destructive_potential:
    require explicit user confirmation in next turn before delivering FinalPrompt
if flags.requires_human_gate:
    emit FinalPrompt with [HUMAN CONFIRM BEFORE EXECUTION] banner
    emit ExecutionStrategy separately for user review
if flags.needs_grounding:
    populate <grounding_rules> tag with sources/restrictions
```
### 8.6 Decision 6 — Promote to bible?
After Run completes, if any new Skill or agent was generated:
```javascript
write to filesystem (done in Step 9)
write to Obsidian (done in Step 9)
add to promotion_queue.json with metadata
on next boot or manual `cee promote <slug>`:
    write candidate page to Notion under "Skill Promotions"
    user reviews and either approves (page moves to canon) or rejects (page archived)
```
Filesystem keeps using the Skill regardless of Notion approval status. Notion approval is the canon-promotion step, not a usage gate.
---
## 9. Edge Cases (Detailed)
**EC1 — Input is one word.** `interpreter` returns `ambiguity_score = 1.0`. Pipeline halts; ClarificationRequest with 3 targeted questions. No artifacts written.
**EC2 — Input contradicts itself.** `interpreter` flags contradiction in `implicit_assumptions`; classifier sets `flags.needs_grounding = true`; `prompt_builder` emits `<contradiction_note>` tag asking executor to resolve.
**EC3 — Input is multilingual.** Interpreter normalizes to English for internal processing but preserves the original verbatim in `<context>`. `FinalPrompt` `<output_format>` declares the response language.
**EC4 — Input is a previously-generated FinalPrompt.** Interpreter detects CEE schema markers (XML tag signatures); pipeline asks: "Re-run prior generation, modify, or treat as new task?"
**EC5 — Two Skills match equally.** Resolver picks more recent `version`; tie → earlier created. Logs the tie for tuning.
**EC6 — No agent matches ****`task_type`****.** Selector generates an agent stub (with `needs_review: true` in frontmatter) from the closest match, proceeds, queues for human review.
**EC7 — Sensitive data inside a code block.** Redactor pattern-matches inside fenced blocks too. Code structure is preserved, redacted strings replaced with `<redacted:type>`.
**EC8 — User wants the FinalPrompt to *include* a sensitive item.** User must add `--allow-sensitive <pattern>` to the run command. CEE refuses to allow blanket override.
**EC9 — Bible references a task type that doesn't exist in the closed enum.** Boot's cross-section consistency check halts; user must reconcile in Notion before next Run.
**EC10 — User wants to disable a problem layer.** Not allowed. Layers are integral. The classifier may *route around* a layer (e.g., a LOW task skips orchestration entirely), but layers are not toggleable.
**EC11 — Same input run twice.** Filesystem-deduplication via input hash. Second Run is a "replay" by default — uses cached artifacts unless `--force-rerun` is set.
**EC12 — Input is an apology or social pleasantry.** Interpreter detects no actionable goal, halts with explicit "no executable intent detected." Does not generate an empty FinalPrompt.
---
## 10. Failure Modes
Cross-referenced with section 00 §10. This page focuses on failure modes specific to *the problem layers* — i.e., when the system thinks it solved a problem but didn't.
### 10.1 The interpreter is wrong about intent
**Failure:** `IntentObject.goal` doesn't match what the user actually wanted.
**Detection:** in Phase 1, only via user feedback. In Phase 2, by an output validator that re-checks the executed output against `IntentObject`.
**Recovery:** `cee replay <run_id> --reinterpret` re-runs the interpreter with the user's correction injected. Filesystem keeps both.
### 10.2 The classifier picks the wrong task type
**Failure:** `task_type = ANALYZE` when user wanted `BUILD`.
**Detection:** mismatch between `task_type` and required Skill capabilities; mismatched agent posture; user feedback.
**Recovery:** classifier re-runs once with `task_type` as a forced parameter from user. After 5 corrections of the same misclassification pattern, classifier weights flagged for retuning.
### 10.3 A generated Skill conflicts with an existing one
**Failure:** new [SKILL.md](http://SKILL.md) has same `name` as existing but different signature.
**Detection:** `skill_engine` enforces uniqueness on `name` at write time.
**Recovery:** `SkillConflictError`. User must either rename the new Skill, version the old (`v1` → `v2`), or merge manually.
### 10.4 A required Skill exists but is stale
**Failure:** Skill works in old executor context but frontmatter is missing fields added in a later schema.
**Detection:** boot's Skill registry build flags stale Skills.
**Recovery:** `skill_engine` generates a v2 alongside v1; user reviews; v1 remains usable.
### 10.5 The user rejects the clarification request
**Failure:** user sends a non-answer ("just figure it out") to a ClarificationRequest.
**Detection:** the response itself has high `ambiguity_score` and contains no answers to the asked questions.
**Recovery:** CEE proceeds with `implicit_assumptions` filled in and the FinalPrompt explicitly tags the assumptions in `<assumptions_made>` for the executor to flag back. User accepts the consequences.
### 10.6 The bible itself is wrong
**Failure:** a section of this bible specifies behavior that's contradictory or unimplementable.
**Detection:** boot's cross-section consistency check; failing tests in section 18.
**Recovery:** halt all Runs until bible is reconciled. The bible is source of truth — code does not override it.
### 10.7 Phase-2 API drift
**Failure (future):** when Phase 2 ships, the Anthropic API changes and breaks CEE's executor assumption.
**Detection:** end-to-end golden Run tests fail.
**Recovery:** the `FinalPrompt` schema is unchanged across phases by design. Only the executor adapter changes. This isolates API drift to a single module.
### 10.8 The promotion queue stalls
**Failure:** Notion is offline for an extended period; `promotion_queue.json` grows unbounded.
**Detection:** queue length monitoring; warning at 50+ entries.
**Recovery:** queue is bounded at 500; oldest entries log a warning but are not auto-dropped. Manual `cee promote --flush` clears.
### 10.9 The bible drifts from filesystem mirror
**Failure:** user edits Notion directly; filesystem mirror stale.
**Detection:** `cee sync-bible` detects via `updated_at` comparison.
**Recovery:** auto-sync if `auto_sync: true` in config; otherwise halt with instructions. Destructive bible changes (removing a task type, etc.) require manual confirmation regardless of auto_sync setting.
### 10.10 The user discovers a new problem layer
**Failure (procedural):** an 11th problem layer emerges that CEE doesn't address.
**Detection:** user observation; recurring failure pattern not covered by §7's problem-to-module mapping.
**Recovery:** new layer is added to this section, mapped to a module (existing or new), and section 00 + the relevant module are updated. Bible drives architecture; architecture does not drive bible.
---
## 11. Build Notes for Claude Code
This section is the requirements bridge into the engine. Build implications:
- **Every problem layer is testable.** Section 18 (Testing) must include at least one failing-input test case per layer that CEE catches and handles correctly.
- **The problem-to-module table in §7 is the dependency graph.** Modules that own multiple layers (e.g., `prompt_builder` owns L2, L3, L7) are higher-priority; build them first.
- **The closed enums are referenced from this section.** `task_type` (§8.2), complexity tiers (§8.3), and flags (§8.5) are defined here. Changes here propagate to schemas in `~/cee/schemas/` and to section 08 (Task Classification Engine).
- **Decision logic in §8 is implementation pseudocode.** The actual implementations live in their respective modules but the logic must match.
- **No layer is implemented without its test.** A module that claims to solve Layer N must have a regression test in section 18 against a known failing input for Layer N.
- **The ****`redact_list`**** is a user-managed file at ****`~/.cee/redact_list`****.** CEE must never auto-add to it without user consent, and never silently fail to redact something not in the list — pattern-based redaction (regex for keys, tokens) is also required.
- **`ClarificationRequest`**** shape.** Defined in `~/cee/schemas/clarification_request.json`. Maximum 3 questions; each question single-select or short-text; questions must be answerable without further context.
- **Phase 2 readiness.** Every module must work with `executor_target` as a parameter, even though Phase 1 only emits prompts. This avoids a rewrite when API execution arrives.
---
## 12. Definition of Done
This section is complete — and CEE's problem definition is locked — when:
- [ ] Every layer in §4 has a named module owner in §7.
- [ ] Every closed enum in §8 has a corresponding schema file.
- [ ] Every failure mode in §10 has a corresponding test case in section 18's plan.
- [ ] Every edge case in §9 is reachable in the codebase (verifiable by `grep`).
- [ ] No layer in §4 is "owned" by hand-waving — each owner module has a defined `run()` signature.
- [ ] The decision flow in §8 has been traced end-to-end against a real Run and produces the expected branches.
- [ ] No item in §6 (existing tools) is something CEE accidentally became — CEE remains *the upstream interface*, not a re-implementation of any of those.
---
## 13. Final Statement
The Claude Execution Engine exists because the interface between human intent and Claude execution is currently a personal craft. CEE turns that craft into infrastructure. Every problem on this page was paid for in user time, output quality, or silent failure under the old regime. Under CEE, each one is paid once — at architecture time — and never again.
