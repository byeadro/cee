---
notion_section: 05
notion_title: 05 — PROMPT ENGINEERING RULES
mirrored_at: 2026-04-30
---

# 05 — PROMPT ENGINEERING RULES
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the complete specification for what a `FinalPrompt` looks like and how `PROMPT_BUILDER` constructs one. The rules here are what makes "every prompt is perfect" mean something concrete instead of aspirational. If `PROMPT_BUILDER` follows this page, output is paste-ready. If it doesn't, the Run fails schema validation and halts.
---
## 1. What This Is
A `FinalPrompt` is the deliverable of every Run. It is an XML-tagged block of text intended to be pasted into [Claude.ai](http://Claude.ai), Claude Code, or (Phase 2) sent via the Anthropic API. This page defines:
- The exact XML tag schema — every tag, when required, when conditional, in what order
- The semantic content rules per tag — what belongs inside, what doesn't
- Target-executor variants — how `claude_ai`, `claude_code`, and `api` formats differ
- Length budgets and chunking rules
- Determinism rules — what makes the same artifact bundle produce the same `FinalPrompt`
This page is not about prompt engineering as a discipline. It is the construction spec for a single artifact type. Best practices that didn't make this page didn't survive the deterministic-construction filter.
---
## 2. Why This Matters
Without this page, "build a perfect prompt" is subjective. With it:
- `PROMPT_BUILDER` becomes a code generator with a defined output grammar.
- Schema validation can reject malformed prompts before they reach the user.
- The same input produces the same prompt every time, byte-identical (modulo controlled randomness).
- Prompt quality stops being about taste and starts being about whether the construction rules were followed.
The user-facing claim from section 00 ("every prompt is perfect") cashes out here. Perfect = schema-conformant + complete + grounded + within budget + correctly targeted.
---
## 3. Core Requirements
A `FinalPrompt` MUST:
1. Be a single XML-tagged block, top-level wrapped in `<final_prompt>`.
2. Contain every required tag from §5.1, in the order specified there.
3. Pass schema validation against `~/cee/schemas/final_prompt.json`.
4. Declare its target executor explicitly via the `<target_executor>` tag.
5. Fit within the target executor's context window or be chunked into ordered parts.
6. Include grounding rules whenever `flags.needs_grounding` is true on the upstream `Classification`.
7. Include a `<assumptions_made>` block whenever `IntentObject.implicit_assumptions` is non-empty.
8. Be self-contained — pasted standalone into the executor, it must produce the intended behavior with no surrounding context.
9. Be human-readable — even though it's XML, the content inside tags is prose or structured prose, not machine codes.
A `FinalPrompt` MUST NOT:
- Contain raw redactable patterns (keys, tokens) — `SAFETY_GATE` runs after `PROMPT_BUILDER` for this reason.
- Reference Skills or agents that don't exist on the executor's filesystem.
- Use ad-hoc tags outside the defined schema. New tags require a bible update.
- Be longer than the target executor's context window minus a 4000-token safety buffer.
- Include CEE-internal artifacts (run IDs, internal classifications) unless explicitly requested for debugging.
---
## 4. System Rules
**Rule 1 — Closed tag set.**
The XML tags listed in §5.1 are the complete set. `PROMPT_BUILDER` cannot invent tags. Adding a tag requires a bible edit and a schema migration.
**Rule 2 — Tag order is fixed.**
Tags appear in the order specified in §5.1. This is not aesthetic — it determines reading order for the executor. Reordering changes semantics for some executors.
**Rule 3 — Required tags are non-negotiable.**
A `FinalPrompt` missing a required tag is rejected. There is no "this task is simple, skip the role tag" exception. Simple tasks get short tag content, not absent tags.
**Rule 4 — Content rules per tag.**
Each tag in §5 has a content rule (what belongs inside). Violations are caught by per-tag content validators.
**Rule 5 — Grounding is conditional but explicit.**
When grounding is needed, the `<grounding_rules>` tag enumerates allowed sources, prohibited inferences, and citation requirements. When it isn't needed, the tag is omitted (not empty).
**Rule 6 — One target executor per FinalPrompt.**
Multi-target prompts are not supported. If a Run could go to multiple executors, generate one FinalPrompt per executor — same Run ID, different artifacts.
**Rule 7 — Determinism via temperature 0 + fixed system prompt.**
`PROMPT_BUILDER` is the only module besides `INTERPRETER` and `CLASSIFIER` that may invoke Claude internally (for prose smoothing within tags). When it does, temperature is 0 and the system prompt is fixed at `~/cee/prompts/prompt_builder_system.txt`.
**Rule 8 — Length budgets are enforced before delivery.**
The builder counts tokens against the target executor's documented limit minus a 4000-token safety buffer. Over-budget prompts are chunked per §5.4.
**Rule 9 — No fluff, no preamble, no postamble.**
The `FinalPrompt` is the prompt. It does not include "here is your prompt" framing or "let me know if you need changes" trailers. Those belong outside the artifact, in the deliver step.
**Rule 10 — Assumptions made are surfaced, not buried.**
Whenever the interpreter filled gaps with assumptions, the `<assumptions_made>` tag lists them. The executor sees them. The user sees them. Silent assumptions are forbidden.
---
## 5. Detailed Workflow — The FinalPrompt Schema
### 5.1 Tag set, order, required vs. conditional
The complete schema. Tags appear in this order. R = always required, C = conditional, O = optional.
<table header-row="true">
<tr>
<td>#</td>
<td>Tag</td>
<td>Status</td>
<td>Content rule</td>
</tr>
<tr>
<td>1</td>
<td>`<final_prompt>`</td>
<td>R</td>
<td>Top-level wrapper.</td>
</tr>
<tr>
<td>2</td>
<td>`<target_executor>`</td>
<td>R</td>
<td>One of: \`claude_ai</td>
</tr>
<tr>
<td>3</td>
<td>`<context>`</td>
<td>R</td>
<td>The relevant background the executor needs. Includes the user's original input verbatim plus any attachments summarized or quoted.</td>
</tr>
<tr>
<td>4</td>
<td>`<role>`</td>
<td>R</td>
<td>The role the executor takes for this task. Derived from `AgentPlan` primary agent.</td>
</tr>
<tr>
<td>5</td>
<td>`<task>`</td>
<td>R</td>
<td>The single, explicit goal the executor must accomplish. Imperative form.</td>
</tr>
<tr>
<td>6</td>
<td>`<agents>`</td>
<td>C</td>
<td>Required if `AgentPlan` references more than one agent. References agent file paths and how they coordinate.</td>
</tr>
<tr>
<td>7</td>
<td>`<skills>`</td>
<td>C</td>
<td>Required if `SkillSet` is non-empty. References Skill file paths the executor should load.</td>
</tr>
<tr>
<td>8</td>
<td>`<execution_plan>`</td>
<td>R</td>
<td>The ordered steps from `ExecutionStrategy`, formatted as numbered steps with checkpoints.</td>
</tr>
<tr>
<td>9</td>
<td>`<constraints>`</td>
<td>R</td>
<td>Hard constraints. From `IntentObject.constraints` plus any classifier-derived constraints (e.g., "single agent only" for LOW). Empty list rendered as "None."</td>
</tr>
<tr>
<td>10</td>
<td>`<grounding_rules>`</td>
<td>C</td>
<td>Required if `flags.needs_grounding` is true. Allowed sources, prohibited inferences, citation requirements.</td>
</tr>
<tr>
<td>11</td>
<td>`<assumptions_made>`</td>
<td>C</td>
<td>Required if `IntentObject.implicit_assumptions` is non-empty. List form.</td>
</tr>
<tr>
<td>12</td>
<td>`<output_format>`</td>
<td>R</td>
<td>The exact shape of the expected output. Inferred from `task_type` if not user-specified.</td>
</tr>
<tr>
<td>13</td>
<td>`<stop_conditions>`</td>
<td>R</td>
<td>When the executor should stop. From `ExecutionStrategy.stop_conditions`. Always at least: "task complete and output validates against `<output_format>`."</td>
</tr>
<tr>
<td>14</td>
<td>`<safety_banner>`</td>
<td>C</td>
<td>Required if `flags.requires_human_gate` or `flags.destructive_potential`. Visible warning that pre-execution confirmation is required.</td>
</tr>
<tr>
<td>15</td>
<td>`<run_metadata>`</td>
<td>O</td>
<td>CEE Run ID, timestamp, complexity tier. Included by default; suppressible via `--no-metadata`.</td>
</tr>
</table>
### 5.2 Per-tag content rules
#### `<target_executor>`
Single token. One of `claude_ai`, `claude_code`, `api`. Determines downstream formatting:
- `claude_ai`: full XML preserved; assumes web UI rendering.
- `claude_code`: full XML preserved; references to `~/cee/skills/` and `~/cee/.claude/agents/` are absolute paths.
- `api`: XML preserved; the prompt is intended for direct API consumption (Phase 2).
#### `<context>`
Includes:
- The user's original input verbatim, fenced in a `<original_input>` sub-tag.
- Summaries of attachments (if any), one per attachment, in `<attachment_summary name="...">` sub-tags.
- Any inferred domain context the interpreter pulled from prior Runs, marked as such.
Rule: if the executor needs to know something to do the task, it goes in `<context>`. If the executor needs to know it to *format* the output, it goes in `<output_format>`.
#### `<role>`
A single sentence in the form: "You are a \[role description\] focused on \[primary capability\]."
Examples:
- "You are a senior backend engineer focused on API design and database schema."
- "You are a developmental editor focused on nonfiction manuscript structure."
- "You are an investigative analyst focused on identifying patterns in data."
Drawn from `AgentPlan.primary_agent.posture` and `domain`. Not invented.
#### `<task>`
One imperative sentence. Active voice. No hedging.
Bad: "It would be great if you could maybe look into refactoring this."
Good: "Refactor the authentication module to use token-based auth."
If the task is too complex for one sentence, the complexity is wrong (LOW tasks should always be expressible in one sentence). The fix is upstream — re-classify or break into sub-tasks via `ORCHESTRATE`.
#### `<agents>` (when present)
Lists each agent referenced in `AgentPlan`:
```xml
<agents>
  <agent role="primary" path="~/cee/.claude/agents/<slug>.md"/>
  <agent role="critic" path="~/cee/.claude/agents/<slug>.md"/>
  <coordination>describe how agents hand off, in 1–2 sentences</coordination>
</agents>
```
The executor (Claude Code) loads these subagents. For `claude_ai` target, the tag still appears but the paths are illustrative — the user will need to manually reference these in their session.
#### `<skills>` (when present)
Lists each Skill referenced in `SkillSet`:
```xml
<skills>
  <skill name="<slug>" path="~/cee/skills/<slug>/SKILL.md"/>
  <skill name="<slug>" path="~/cee/skills/<slug>/SKILL.md"/>
</skills>
```
For `claude_code` target, paths are absolute and Claude Code loads them. For `claude_ai`, the user manually pastes Skill content or references it.
#### `<execution_plan>`
Numbered steps. Each step has a one-line action and an optional checkpoint condition.
```xml
<execution_plan>
  <step n="1" action="Read the input file"/>
  <step n="2" action="Identify all function definitions" checkpoint="count matches expectation"/>
  <step n="3" action="Refactor to use new auth pattern" checkpoint="all tests pass"/>
  <step n="4" action="Emit refactored file"/>
</execution_plan>
```
LOW tasks have one step. EXTREME tasks have many.
#### `<constraints>`
List form. Each constraint on one line:
```xml
<constraints>
  <constraint>Use Python 3.11+</constraint>
  <constraint>No external API calls</constraint>
  <constraint>Output must be a single file</constraint>
</constraints>
```
If empty: `<constraints>None.</constraints>`.
#### `<grounding_rules>` (when present)
Three sub-sections:
```xml
<grounding_rules>
  <allowed_sources>
    <source>The attached PDF</source>
    <source>The codebase at ~/projects/foo/</source>
  </allowed_sources>
  <prohibited_inferences>
    <prohibition>Do not infer API behavior not documented in the attached PDF.</prohibition>
  </prohibited_inferences>
  <citation_requirement>Every factual claim must reference a specific section of the allowed sources.</citation_requirement>
</grounding_rules>
```
#### `<assumptions_made>` (when present)
List of assumptions the interpreter or classifier filled in. The executor is invited to flag them back if any are wrong:
```xml
<assumptions_made>
  <assumption>Assumed "the file" refers to the most recently mentioned file in the conversation.</assumption>
  <assumption>Assumed Python 3.11 since no version was specified.</assumption>
  <flag_back_instruction>If any assumption is wrong, halt and ask before proceeding.</flag_back_instruction>
</assumptions_made>
```
#### `<output_format>`
The exact shape of the deliverable. Specific to `task_type`:
- `BUILD` → "A complete file at \<path\>, syntactically valid, with \<described content\>."
- `ANALYZE` → "A structured report with sections: \<list of sections\>."
- `DEBUG` → "A diagnosis followed by a fix; both in markdown."
- `WRITE` → "Prose deliverable, \<length\>, in \<tone/voice\>."
- `RESEARCH` → "Sourced summary with citations to the allowed sources."
- `TRANSFORM` → "Output data in \<format\>."
- `DECIDE` → "A recommendation with rationale and tradeoffs."
- `ORCHESTRATE` → "Coordination plan plus per-sub-task outputs."
Always concrete. Never "appropriate format" or "as you see fit."
#### `<stop_conditions>`
When to stop. Default: task complete and output validates against `<output_format>`. Additional conditions per `ExecutionStrategy`:
```xml
<stop_conditions>
  <condition>Output validates against <output_format>.</condition>
  <condition>All checkpoints in <execution_plan> have passed.</condition>
  <condition>If any constraint is violated, halt and report.</condition>
</stop_conditions>
```
#### `<safety_banner>` (when present)
A visible warning at the top of the executor's reading order:
```xml
<safety_banner>
  [HUMAN CONFIRM BEFORE EXECUTION]
  This task has destructive potential. Do not execute until the OPERATOR has explicitly confirmed.
</safety_banner>
```
#### `<run_metadata>`
Trace info, suppressible:
```xml
<run_metadata>
  <run_id>20260430_141522_a3f8c2d1</run_id>
  <generated_at>2026-04-30T14:15:22Z</generated_at>
  <complexity>MEDIUM</complexity>
  <complexity_score>42</complexity_score>
  <bible_version>2026-04-30T14:00:00Z</bible_version>
</run_metadata>
```
### 5.3 Target executor formatting variants
Same tag schema, different rendering details:
**`claude_ai`****:**
- Paths to Skills/agents are illustrative; the user knows they live in `~/cee/`.
- No expectation that `.claude/agents/` is loaded automatically — the user pastes Skill content if needed.
- Length budget: 200K tokens minus 4000 buffer.
**`claude_code`****:**
- All Skills and agents paths are absolute (`~/cee/skills/...`, `~/cee/.claude/agents/...`).
- Claude Code loads them automatically when started in the `~/cee/` project root.
- The `<execution_plan>` may reference Claude Code tools (Bash, Edit, Read) by name.
- Length budget: same as claude_ai.
**`api`**** (Phase 2):**
- The full FinalPrompt becomes the user message in a single `messages.create` call.
- The system prompt is constructed from `<role>` plus a fixed CEE preamble.
- No assumption that Skills/agents are loaded — the prompt must be self-contained or the API caller (CEE itself) must handle Skill injection.
- Length budget: model-specific, looked up at boot from `~/cee/config/models.json`.
### 5.4 Length budget and chunking
If total token count exceeds budget:
1. `PROMPT_BUILDER` calls `chunk(final_prompt, budget) -> list[FinalPrompt]`.
2. Chunking strategy: split `<context>` and `<execution_plan>` only. Other tags are duplicated across chunks.
3. Each chunk gets a `<chunk_metadata>` tag: `<chunk n="1" of="3"/>`.
4. The user pastes chunks in order. The first chunk includes a `<chunking_instructions>` block telling the executor to wait for all chunks before starting.
Chunking is an escape hatch, not a default. Most Runs fit in one prompt.
### 5.5 Determinism construction order
`PROMPT_BUILDER` constructs the FinalPrompt by:
1. Reading all upstream artifacts.
2. For each tag in §5.1 order: pulling the source data, formatting per the content rule, appending to the buffer.
3. Wrapping in `<final_prompt>`.
4. Validating against the schema.
5. Counting tokens; chunking if over budget.
6. Returning the artifact.
No random sampling. No "creative formatting." The construction is mechanical. Where natural-language phrasing is needed (e.g., turning a `domain` and `posture` into a `<role>` sentence), Claude is called with temperature 0 and a fixed prompt that produces deterministic output.
---
## 6. Data / Inputs Needed
### 6.1 Required artifacts (from upstream)
- `IntentObject` — for `<context>`, `<assumptions_made>`, parts of `<constraints>`.
- `Classification` — for complexity tier, flags, and tag conditionality.
- `AgentPlan` — for `<role>` and `<agents>`.
- `SkillSet` — for `<skills>`.
- `ExecutionStrategy` — for `<execution_plan>` and `<stop_conditions>`.
### 6.2 Configuration inputs
- `~/cee/config/models.json` — token budgets per model.
- `~/cee/prompts/prompt_builder_system.txt` — system prompt for any internal Claude calls.
- `~/cee/schemas/final_prompt.json` — the schema the artifact must validate against.
### 6.3 Optional inputs
- `--no-metadata` flag from CLI to suppress `<run_metadata>`.
- `--target-executor <executor>` override.
---
## 7. Outputs Produced
### 7.1 The artifact
`FinalPrompt` written to `~/cee/runs/<run_id>/prompt.xml`. Single file.
### 7.2 Multi-chunk variant
If chunked: `prompt.xml` contains the first chunk plus a manifest; chunks 2..N at `prompt_2.xml`, `prompt_3.xml`. The summary file lists all chunks.
### 7.3 What the user sees on stdout
The XML block, ready to paste. Plus a one-line summary above it: "Generated MEDIUM-complexity prompt for claude_code, 2 agents, 3 skills, 1850 tokens."
---
## 8. Agent + Skill Implications
### 8.1 Agents inform `<role>` and `<agents>`
The primary agent's `posture` and `capabilities` are templated into `<role>`. The full agent list goes into `<agents>` only when there's more than one — single-agent Runs skip the `<agents>` tag entirely.
### 8.2 Skills inform `<skills>` and constraints
Each Skill's name and path go into `<skills>`. Skill-declared `inputs` and `outputs` may inform `<constraints>` (e.g., a Skill that requires Python 3.11 adds that as a constraint).
### 8.3 The prompt does not embed Skill content
For `claude_code` target, Skill paths are referenced; Claude Code loads them. For `claude_ai`, the user is responsible for ensuring Skills are accessible — the prompt instructs them where the Skills live but does not paste their content. Embedding Skill content inline would explode token budgets.
Exception: if `target_executor = api` (Phase 2), CEE's API caller injects Skill content into the system prompt. The FinalPrompt itself still references by path; the injection happens at send time, not build time.
---
## 9. Edge Cases
**EC1 — A required tag's source data is missing.**
Example: `IntentObject` somehow has no `goal`. `PROMPT_BUILDER` halts with `prompt_schema_violation` — this should have been caught upstream. Indicates a bug in `INTERPRETER`.
**EC2 — ****`IntentObject.constraints`**** is empty.**
`<constraints>` tag still appears, with content "None."
**EC3 — User specifies a target executor that doesn't exist.**
`PROMPT_BUILDER` rejects at schema validation. Closed enum.
**EC4 — Run produces 50K-token context (huge attachments).**
Chunking triggered. Three or more chunks emitted with sequencing metadata.
**EC5 — Two agents share the same posture.**
`AGENT_SELECTOR` should have caught this earlier. If somehow it slips through, `PROMPT_BUILDER` halts with `agent_conflict` (delayed detection).
**EC6 — Skill path doesn't exist on disk.**
Validated at build time. Halt with explicit error naming the missing Skill.
**EC7 — The original user input contains XML that looks like CEE tags.**
The `<original_input>` sub-tag escapes content. User input is treated as data, not structure.
**EC8 — The user wants no ****`<run_metadata>`**** for production sharing.**
`--no-metadata` flag. The tag is suppressed.
**EC9 — ****`<output_format>`**** would conflict with what ****`<execution_plan>`**** produces.**
This is upstream's problem (`STRATEGY_BUILDER` should align format and plan). `PROMPT_BUILDER` does not re-derive; it formats what it's given.
**EC10 — Target executor is ****`api`**** but Phase 2 isn't built yet.**
Reject with explicit "Phase 2 not implemented; use claude_ai or claude_code target."
**EC11 — A Skill's ****`description`**** contains characters that break XML.**
Sanitized at build time. The original Skill content is preserved at the file; only the rendered description in `<skills>` is sanitized.
**EC12 — Run regenerates a FinalPrompt and the result is byte-different from the original (replay drift).**
Indicates a non-determinism bug. Failing test in section 18. Drift is logged with diff.
---
## 10. Failure Modes
### 10.1 Schema violation at build time
**Failure:** the constructed FinalPrompt fails validation.
**Detection:** Pydantic schema check before write.
**Recovery:** halt with `prompt_schema_violation`; the failing tag and constraint logged.
### 10.2 Token count exceeds budget even after chunking
**Failure:** chunking helper can't split `<context>` finely enough.
**Detection:** chunker's max-iteration check.
**Recovery:** halt with `prompt_too_large`; user must reduce attachments or scope.
### 10.3 Required tag content is empty after construction
**Failure:** e.g., `<task>` resolves to empty string because `IntentObject.goal` was empty.
**Detection:** per-tag content validator.
**Recovery:** halt; root cause is upstream (`INTERPRETER` or `CLASSIFIER`).
### 10.4 Internal Claude call drifts
**Failure:** `PROMPT_BUILDER` calls Claude for prose smoothing and gets different output across runs.
**Detection:** golden Run replay tests in section 18.
**Recovery:** verify temperature 0 and fixed system prompt. If still drifting, expand the system prompt to be more constraining.
### 10.5 Tag order regression
**Failure:** a refactor accidentally reorders tags.
**Detection:** golden Run tests check tag order in produced prompts.
**Recovery:** code fix; locked-down tag order list referenced from one place in the code.
### 10.6 Sanitization escapes too aggressive
**Failure:** user input legitimately contains characters that get over-escaped, distorting meaning.
**Detection:** golden Run tests with adversarial inputs.
**Recovery:** sanitization rules tightened to only escape what would break XML parsing.
### 10.7 Conditional tag wrongly included
**Failure:** `<grounding_rules>` appears when `flags.needs_grounding` is false.
**Detection:** schema tests assert tag presence matches flags.
**Recovery:** code fix.
### 10.8 Conditional tag wrongly omitted
**Failure:** `<assumptions_made>` is omitted when `IntentObject.implicit_assumptions` is non-empty.
**Detection:** same as above.
**Recovery:** code fix; tests prevent regression.
### 10.9 Target executor mismatch in rendered paths
**Failure:** prompt targets `claude_ai` but renders absolute filesystem paths the user can't access.
**Detection:** target-specific rendering tests.
**Recovery:** rendering switch is per-target; bug indicates the switch was bypassed.
### 10.10 Length-budget lookup fails
**Failure:** `~/cee/config/models.json` is missing or doesn't have an entry for the requested model.
**Detection:** boot validates the file; build-time falls back to a hardcoded conservative default (100K tokens) and warns.
**Recovery:** populate the config; rerun.
---
## 11. Build Notes for Claude Code
- **Builder location:** `~/cee/prompt_builder/builder.py`. Public function: `build(artifacts: ArtifactBundle, target: Executor) -> FinalPrompt`.
- **Tag templates:** each tag has a Jinja-style template at `~/cee/prompt_builder/templates/<tag_name>.j2`. Templates take artifact data, render the tag's content. Tag templates do not invoke each other — composition happens in `builder.py`.
- **Tag order constant:** defined once at `~/cee/prompt_builder/tag_order.py`. Builder iterates this list.
- **Tag conditionality:** each tag's template includes a `should_render(artifacts) -> bool` function. Builder checks before rendering.
- **Per-tag validators:** `~/cee/prompt_builder/validators/<tag_name>.py`. Run after rendering to catch empty-content cases.
- **Chunker:** `~/cee/prompt_builder/chunker.py`. Pure function: `chunk(prompt: FinalPrompt, budget: int) -> list[FinalPrompt]`.
- **Token counting:** uses Anthropic's `count_tokens` helper or a local tiktoken-equivalent. Cached per model.
- **Internal Claude calls:** if used, go through a single helper at `~/cee/prompt_builder/llm.py` with temperature 0 and the fixed system prompt loaded from `~/cee/prompts/prompt_builder_system.txt`.
- **Tests:** `~/cee/tests/unit/test_prompt_builder/` includes one test per tag (rendering, content rules, conditionality), one test per target executor (rendering variants), and golden tests that compare full FinalPrompts against committed expected outputs.
- **No string concatenation outside templates.** All string assembly happens inside templates or the top-level builder. No ad-hoc `f"<task>{goal}</task>"` anywhere else.
---
## 12. Definition of Done
This page is complete — and `PROMPT_BUILDER` is unblocked for build — when:
- [ ] Every tag in §5.1 has a template at `~/cee/prompt_builder/templates/`.
- [ ] Every tag has a content validator.
- [ ] The tag order constant matches §5.1 exactly.
- [ ] All three target executor variants render correctly.
- [ ] Chunking works for over-budget prompts and produces ordered, valid sub-prompts.
- [ ] Schema validation is the last step before write.
- [ ] Golden Run tests in section 18 cover at least: clean LOW (single agent, no Skills), MEDIUM (with Skills), HIGH (with grounding), EXTREME (with safety banner and chunking).
- [ ] Replay of any Run produces byte-identical FinalPrompts.
- [ ] No tag is rendered outside its template; no template runs outside the builder.
---
## 13. Final Statement
A FinalPrompt is the entire deliverable of CEE. Everything else in the system exists to populate this artifact correctly. The rules on this page are the difference between "a prompt" and "the prompt CEE meant to produce." Determinism, completeness, and target-specificity are all encoded here. If `PROMPT_BUILDER` follows this page, the user gets paste-ready output. If it doesn't, the Run halts before the user is misled.
