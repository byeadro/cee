---
notion_section: 06
notion_title: 06 — AGENT SYSTEM DESIGN
mirrored_at: 2026-04-30
---

# 06 — AGENT SYSTEM DESIGN
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the complete specification for what an agent is in CEE, how agents are stored, selected, and composed. The closed enum of agent postures lives here. Section 02 said "agents are roles inside the executor, invoked by `AGENT_SELECTOR`" — this page is what that means concretely.
---
## 1. What This Is
In CEE, an "agent" is a Claude Code subagent — a single markdown file with YAML frontmatter and a system-prompt body that defines a role Claude can take when invoked by Claude Code. Agents live at `~/cee/.claude/agents/<slug>.md` in the format Claude Code natively loads.
CEE does not invent a parallel agent format. CEE does not run agents itself. CEE *selects* agents: it reads the registry, matches against `Classification` and `IntentObject`, and references the chosen agents in the `<agents>` tag of the FinalPrompt. The executor (Claude Code) then loads them.
This page defines:
- The agent file format (frontmatter schema + body conventions)
- The closed enum of agent postures
- How `AGENT_SELECTOR` chooses agents per Run
- How agents compose when more than one is selected
- The agent-generation path (when no existing agent fits)
- The pre-built agent catalog that ships with CEE
---
## 2. Why This Matters
Without a tight agent specification:
- "Picking the right agent" becomes vibes-based, not deterministic.
- Two agents end up with overlapping postures, and the selector picks arbitrarily.
- New agents proliferate without a defined generation path, breaking reuse.
- The executor doesn't know how multiple agents coordinate.
This page makes agent selection a deterministic function over a closed set, with a defined generation path for genuinely new postures.
---
## 3. Core Requirements
The agent system MUST:
1. Store every agent as a single `.md` file at `~/cee/.claude/agents/<slug>.md` with YAML frontmatter conforming to the schema in §6.
2. Use a closed enum of postures (§5.1). New postures require a bible edit.
3. Provide a deterministic selection function: `Classification + IntentObject → AgentPlan`.
4. Cap agent count per Run by complexity tier (1 / 1–2 / 3 / 4+).
5. Generate a new agent only when no existing agent matches and the gap is real (not when an existing agent could be reused with different framing).
6. Document, for every agent, what `task_type`s it supports and what tools it expects.
7. Support agent composition — when multiple agents are selected, the FinalPrompt's `<agents>` tag describes how they coordinate.
The agent system MUST NOT:
- Allow runtime agent definition (no agents that exist only in memory).
- Allow agents to read from each other's files at selection time. Coordination is described in the FinalPrompt; execution happens in Claude Code.
- Mix CEE's role taxonomy (section 02) with agent postures. Roles act on CEE; agents act on the user's task.
- Embed CEE-internal logic in agent system prompts. Agents are about the user's task, not about CEE.
---
## 4. System Rules
**Rule 1 — Closed posture enum.**
Postures: `primary | critic | optimizer | orchestrator | specialist`. Defined in §5.1. No others.
**Rule 2 — One primary per Run.**
The primary agent is the lead. There is exactly one. Other postures support.
**Rule 3 — Posture-to-tier mapping.**
- LOW: `primary` only.
- MEDIUM: `primary` + optional `critic`.
- HIGH: `primary` + `critic` + `optimizer`.
- EXTREME: `orchestrator` + `primary` + `critic` + `optimizer` + zero or more `specialist`s.
**Rule 4 — Specialists are domain-bound.**
A `specialist` agent declares a `domain` in its frontmatter and is selected only when `IntentObject.domain` matches. Specialists are domain experts; they do not replace the primary.
**Rule 5 — Agents have declared tool access.**
Each agent's frontmatter lists `allowed_tools`. The executor enforces. CEE only verifies the list exists; it doesn't enforce tool boundaries (that's Claude Code's job).
**Rule 6 — Agent generation requires a real gap.**
Before generating a new agent, `AGENT_SELECTOR` must verify no existing agent has matching capabilities. The bar is high — most "missing" agents are actually existing agents the selector didn't match because the description was weak.
**Rule 7 — Generated agents need review before promotion.**
A newly generated agent gets `needs_review: true` in frontmatter. The Run uses it. It is queued for promotion to Notion. After OPERATOR review, the flag is cleared.
**Rule 8 — Agents do not change between Runs.**
A Run captures `bible_snapshot/` and uses the agent files referenced in `AgentPlan` at Run start. If an agent file is edited mid-Run, the Run continues with the snapshot version.
**Rule 9 — Posture is enforced in the agent's body.**
The agent's system prompt must explicitly state its posture. A `critic` agent that writes prose like a `primary` is broken — the body and the frontmatter must agree.
**Rule 10 — Agents are not Skills.**
An agent defines *who* the executor is. A Skill defines *what capability* the executor can apply. Agents have stable identity across Runs; Skills are capabilities to load. Don't conflate.
---
## 5. Detailed Workflow — The Agent System
### 5.1 The closed posture enum
<table header-row="true">
<tr>
<td>Posture</td>
<td>Role</td>
<td>Count per Run</td>
</tr>
<tr>
<td>`primary`</td>
<td>Leads the task. Produces the main output.</td>
<td>Exactly 1</td>
</tr>
<tr>
<td>`critic`</td>
<td>Reviews the primary's output, identifies gaps, errors, and weaknesses.</td>
<td>0–1</td>
</tr>
<tr>
<td>`optimizer`</td>
<td>Improves the primary's output along a defined axis (clarity, performance, cost).</td>
<td>0–1</td>
</tr>
<tr>
<td>`orchestrator`</td>
<td>Coordinates multiple agents on EXTREME tasks. Decomposes, assigns, integrates.</td>
<td>0–1 (only on EXTREME)</td>
</tr>
<tr>
<td>`specialist`</td>
<td>Brings deep domain knowledge as a consultant to the primary.</td>
<td>0+ (typically 0–2)</td>
</tr>
</table>
### 5.2 Agent file format
Every agent is a `.md` file at `~/cee/.claude/agents/<slug>.md`.
#### 5.2.1 Frontmatter schema (`~/cee/schemas/agent_frontmatter.json`)
```yaml
---
name: <kebab-case-slug>
description: <one paragraph; used for selection matching>
posture: primary | critic | optimizer | orchestrator | specialist
domain: <optional; required for specialists; one of: code | writing | analysis | research | ops | personal | other>
task_types_supported: [BUILD, ANALYZE, DEBUG, WRITE, RESEARCH, TRANSFORM, DECIDE, ORCHESTRATE]
capabilities: [<short capability tags>]
allowed_tools: [<tool names — Bash, Read, Edit, Write, Glob, Grep, etc.>]
version: <semver>
created_by_run: <run_id> | manual
created_at: <ISO timestamp>
needs_review: false
---
```
Required fields: `name`, `description`, `posture`, `task_types_supported`, `capabilities`, `allowed_tools`, `version`. Optional: `domain` (required if `posture: specialist`), `created_by_run`, `created_at`, `needs_review`.
#### 5.2.2 Body conventions
The body is the agent's system prompt — what Claude Code passes when invoking the subagent. Conventions:
- Open with a one-sentence identity statement: "You are a \[role\] focused on \[primary capability\]."
- Declare posture explicitly: "Your posture is \[primary\|critic\|optimizer\|orchestrator\|specialist\]. \[Posture-specific behavior contract.\]"
- Enumerate tool usage if relevant: "When given a task, you typically use Read, Edit, and Bash."
- Define output expectations: "Your output is \[shape\]. You do not \[anti-patterns\]."
- Limit length: agent bodies should be 200–600 words. Longer ones bloat the executor's context; shorter ones are usually under-specified.
#### 5.2.3 Posture-specific body contracts
**`primary`****:** "You produce the main deliverable. You commit to a single approach. You do not hedge between alternatives — you pick one and execute. If you encounter ambiguity, you make a defensible choice and flag it explicitly."
**`critic`****:** "You review the primary's output. You do not produce a parallel deliverable. You identify gaps, errors, weak reasoning, and missing considerations. You write in the form: 'Issue: \<description\>. Severity: \<low\|med\|high\>. Suggested fix: \<action\>.'"
**`optimizer`****:** "You improve the primary's output along a declared axis (specified in your task). You do not change scope or correctness; you tighten, clarify, or compress. You produce a revised version with a brief change log."
**`orchestrator`****:** "You decompose the task into sub-tasks, assign each to a sub-agent, integrate their outputs, and resolve conflicts. You do not produce content directly; you coordinate."
**`specialist`****:** "You bring deep domain knowledge as a consultant to the primary. You answer questions, flag domain-specific risks, and suggest approaches. You do not own the deliverable — the primary does."
### 5.3 Agent selection algorithm
`AGENT_SELECTOR.run(Classification, IntentObject) -> AgentPlan`:
```javascript
def run(classification, intent_object):
    plan = AgentPlan()

    # 1. Determine posture set per tier
    postures_needed = posture_set_for_tier(classification.complexity_tier)
    # LOW -> [primary]
    # MEDIUM -> [primary, optional critic]
    # HIGH -> [primary, critic, optimizer]
    # EXTREME -> [orchestrator, primary, critic, optimizer, specialists?]

    # 2. For each posture, select best matching agent
    for posture in postures_needed:
        candidates = agent_registry.filter(
            posture=posture,
            task_type_supported=classification.task_type
        )
        if posture == "specialist":
            candidates = candidates.filter(domain=intent_object.domain)
        if not candidates:
            if posture in {"primary"}:
                # Generate new agent if no primary fits — primary is required
                new_agent = generator.generate(posture, intent_object, classification)
                plan.add(new_agent)
            else:
                # Optional postures are skipped if no fit
                continue
        else:
            best = score_and_pick(candidates, intent_object)
            plan.add(best)

    # 3. Validate plan against tier limits
    plan.validate(classification.complexity_tier)

    return plan
```
Scoring function:
```javascript
score = (
    capability_overlap(agent.capabilities, intent_object.required_capabilities) * 0.5 +
    description_semantic_match(agent.description, intent_object.goal) * 0.3 +
    recent_usage_bonus(agent, recent_runs) * 0.2
)
```
The recent-usage bonus is small but present — it slightly favors agents already validated by recent successful Runs.
### 5.4 Agent composition
When more than one agent is selected, the FinalPrompt's `<agents>` tag describes how they coordinate. Patterns:
**Primary + critic:**
```javascript
Primary executes the task. Critic reviews and emits issues. Primary then revises based on critic feedback.
Two-pass execution.
```
**Primary + critic + optimizer:**
```javascript
Primary executes. Critic reviews. Primary revises. Optimizer tightens the revised output along the declared axis.
Three-pass execution.
```
**Orchestrator + primary + critic + optimizer + specialist(s):**
```javascript
Orchestrator decomposes the task into sub-tasks. Primary owns each sub-task's execution.
Specialists are consulted by primary as needed for domain questions.
Critic reviews each sub-task's output. Optimizer tightens after critic. Orchestrator integrates final output.
Multi-pass DAG execution.
```
The composition pattern is selected by the orchestrator's body or, on non-EXTREME tasks, by a fixed pattern in `~/cee/agent_selector/composition_patterns.py`.
### 5.5 Agent generation
When `AGENT_SELECTOR` finds no match for the `primary` posture (or for a required `specialist` domain):
1. Generator (`~/cee/agent_selector/generator.py`) constructs frontmatter from:
	- `posture` from the missing slot
	- `task_types_supported` from `Classification.task_type`
	- `domain` from `IntentObject.domain` (for specialists)
	- `capabilities` extracted from `IntentObject.required_capabilities`
	- `allowed_tools` from a default set per posture
2. Generator constructs the body via a Claude call (temperature 0, fixed system prompt at `~/cee/prompts/agent_generator_system.txt`).
3. Generator validates the rendered file against `agent_frontmatter.json`.
4. File is written to `~/cee/.claude/agents/<slug>.md` with `needs_review: true`.
5. Promotion candidate queued for Notion.
The generator is conservative — it generates only when the gap is real. The default behavior is to reuse the closest existing agent (within a similarity threshold).
### 5.6 The shipped agent catalog
CEE ships with a starter set in `~/cee/.template/.claude/agents/`. These cover the common cases so most Runs reuse rather than generate. Recommended initial catalog:
<table header-row="true">
<tr>
<td>Slug</td>
<td>Posture</td>
<td>Domain</td>
<td>task_types_supported</td>
</tr>
<tr>
<td>`code-builder`</td>
<td>primary</td>
<td>code</td>
<td>BUILD, DEBUG, TRANSFORM</td>
</tr>
<tr>
<td>`code-critic`</td>
<td>critic</td>
<td>code</td>
<td>BUILD, DEBUG, TRANSFORM</td>
</tr>
<tr>
<td>`code-optimizer`</td>
<td>optimizer</td>
<td>code</td>
<td>BUILD, TRANSFORM</td>
</tr>
<tr>
<td>`prose-writer`</td>
<td>primary</td>
<td>writing</td>
<td>WRITE</td>
</tr>
<tr>
<td>`prose-editor`</td>
<td>critic</td>
<td>writing</td>
<td>WRITE</td>
</tr>
<tr>
<td>`analyst`</td>
<td>primary</td>
<td>analysis</td>
<td>ANALYZE, DECIDE</td>
</tr>
<tr>
<td>`researcher`</td>
<td>primary</td>
<td>research</td>
<td>RESEARCH</td>
</tr>
<tr>
<td>`data-transformer`</td>
<td>primary</td>
<td>code</td>
<td>TRANSFORM</td>
</tr>
<tr>
<td>`decision-advisor`</td>
<td>primary</td>
<td>analysis</td>
<td>DECIDE</td>
</tr>
<tr>
<td>`task-orchestrator`</td>
<td>orchestrator</td>
<td>other</td>
<td>ORCHESTRATE</td>
</tr>
<tr>
<td>`legal-specialist`</td>
<td>specialist</td>
<td>analysis</td>
<td>ANALYZE, RESEARCH, WRITE</td>
</tr>
<tr>
<td>`infra-specialist`</td>
<td>specialist</td>
<td>code</td>
<td>BUILD, DEBUG</td>
</tr>
</table>
This catalog is illustrative. It's edited and expanded as CEE is used. The point: most Runs hit the catalog; generation is the exception.
---
## 6. Data / Inputs Needed
### 6.1 Required inputs to `AGENT_SELECTOR`
- `Classification`
- `IntentObject`
- Agent registry (`~/cee/.claude/agents/index.json`)
- Per-posture allowed-tools defaults (`~/cee/agent_selector/tool_defaults.json`)
### 6.2 Required inputs for agent generation
- `~/cee/prompts/agent_generator_system.txt`
- `~/cee/schemas/agent_frontmatter.json`
- A defined slug-naming convention (kebab-case, derived from `posture` + `domain` + a short noun from `IntentObject.goal`)
### 6.3 Configuration
- `~/.cee/config.toml` `[agent_selector]` section with thresholds:
	- `description_match_threshold` (default 0.65)
	- `generation_threshold` (default 0.50 — below this, generate; above, reuse)
	- `recent_usage_bonus_window_days` (default 30)
---
## 7. Outputs Produced
### 7.1 The `AgentPlan` artifact
JSON object listing selected agents as a list of `AgentRef` entries plus a free-text `coordination` description. Schema:
```json
{
  "agents": [
    {"slug": "code-builder", "posture": "primary", "path": "~/cee/.claude/agents/code-builder.md", "generated_in_run": false},
    {"slug": "code-critic", "posture": "critic", "path": "~/cee/.claude/agents/code-critic.md", "generated_in_run": false}
  ],
  "coordination": "Primary executes the task; critic reviews and emits issues; primary revises based on critic feedback. Two-pass execution.",
  "produced_by": "AGENT_SELECTOR"
}
```
Field rules:
- `agents`: list of `AgentRef` objects, length ≥ 1. Each `AgentRef` has `slug` (kebab-case ASCII), `posture` (one of the closed enum values from §5.1), `path` (under `~/cee/.claude/agents/`), `generated_in_run` (bool, true if generated in the current Run).
- At least one agent in the list MUST have `posture` in `{primary, orchestrator}` — every Run needs a lead. The validator enforces this.
- `coordination`: free-text string describing how the agents interact for this Run. Replaces the prior `composition_pattern` enum because the list-form can describe arbitrary compositions that no fixed enum captures.
- `produced_by`: `"AGENT_SELECTOR"`.
Note: this schema replaces the earlier flat-keyed-dict shape (with named `primary`, `critic`, `optimizer`, `orchestrator`, `specialists` fields). The list-form is more extensible — it gracefully supports multiple specialists, future postures, and custom coordination descriptions without a schema migration. Selection logic in `AGENT_SELECTOR` filters the list by `posture` when it needs the lead or any specific role.
### 7.2 Generated agent files (when applicable)
New `.md` files at `~/cee/.claude/agents/<slug>.md`. Mirror to Obsidian. Promotion candidate in Notion.
### 7.3 Audit log entries
Every selection and every generation logged in `~/cee/audit/roles.log`.
---
## 8. Agent + Skill Implications
### 8.1 Agents reference Skills indirectly
Agents do not declare which Skills they use — that's the Skill engine's job, downstream. An agent's frontmatter says "I support task_type X with capabilities Y"; the Skill engine then picks Skills that match.
### 8.2 Some Skills depend on specific agent postures
A Skill like "code-review-checklist" only makes sense with a `critic` agent. The Skill's `triggers` field can include posture hints, but the binding is loose — the FinalPrompt declares both, and the executor wires them.
### 8.3 Generated agents and generated Skills can co-occur
A Run that needs a new domain (e.g., "first time building a CrewAI workflow") may generate both a `crewai-specialist` agent and a `crewai-workflow-init` Skill. Both go through their respective generation paths in parallel.
---
## 9. Edge Cases
**EC1 — ****`task_type`**** is ****`ORCHESTRATE`**** but complexity is MEDIUM.**
Treat as HIGH for selection purposes — orchestration tasks need at least an orchestrator + primary + critic.
**EC2 — Two agents claim the same ****`primary`**** slot for the same ****`task_type`****.**
Selector picks higher score. If tied, more recent `version`. If still tied, earlier `created_at`. Final tie-break: alphabetical slug.
**EC3 — A ****`specialist`**** is needed for a domain not in the closed enum (****`code | writing | analysis | research | ops | personal | other`****).**
The closed enum covers `other` as a catchall. Specialists for `other` are domain-tagged with a free-form `domain_tag` sub-field but selection still uses `other` as the match key.
**EC4 — Multiple specialists could apply (e.g., legal + finance for a contract review).**
Selector picks up to 2 by score. EXTREME is the only tier that allows specialists at all — MEDIUM and HIGH skip them.
**EC5 — A generated agent's body fails validation.**
Generator retries up to 2x with stricter prompt. Third failure: halt with `agent_generation_failed`.
**EC6 — A previously-generated agent has ****`needs_review: true`**** and the same posture/task_type comes up again.**
Treat the agent as usable but flag in the AgentPlan. OPERATOR sees it in the run summary and can review.
**EC7 — The user wants to override agent selection.**
CLI flag: `--agents <slug>,<slug>,<slug>`. Selector validates the chosen agents support the task_type and complexity, then uses them instead of its own selection.
**EC8 — The agent registry is empty (fresh install, before catalog scaffold).**
Boot fails — every Run needs at least one primary candidate. `cee init` includes the catalog scaffold.
**EC9 — Orchestrator is needed but no orchestrator exists in registry.**
Generate one. Orchestrators are simple in structure (their body is mostly the composition pattern), so generation is reliable.
**EC10 — Two agents have the same slug but different content.**
Filesystem prevents this (one slug = one file). The Skill registry rebuild logs a warning and uses the on-disk version.
---
## 10. Failure Modes
### 10.1 No primary fits and generation fails
**Failure:** no existing primary matches and the generator can't produce a valid one.
**Detection:** generator returns failure after retries.
**Recovery:** halt with `no_primary_agent`; user must either narrow the task or hand-author an agent.
### 10.2 Posture mismatch in body
**Failure:** an agent's frontmatter says `posture: critic` but the body reads like a primary.
**Detection:** body validator (lightweight LLM check) flags during scaffold; tests in section 18 catch with example outputs.
**Recovery:** body fixed to match posture contract.
### 10.3 Selection drift across runs
**Failure:** same Classification + IntentObject pair selects different primaries on different days.
**Detection:** golden Run replay tests.
**Recovery:** tie-breaking rules tightened; recent-usage bonus may be the culprit (replay disables it).
### 10.4 Agent file edited mid-Run
**Failure:** OPERATOR edits an agent file while a Run is using it.
**Detection:** Run uses `bible_snapshot` semantics — agents are also snapshotted at Run start.
**Recovery:** Run continues with snapshot version. Edit applies to next Run.
### 10.5 Generated agent gets stuck in `needs_review: true` forever
**Failure:** Notion promotion never happens; agent is used in many Runs but never reviewed.
**Detection:** boot warns when `needs_review: true` agents are older than 30 days.
**Recovery:** OPERATOR reviews and clears flag, or `cee promote-agent <slug>` is run.
### 10.6 Agent capabilities drift from real behavior
**Failure:** agent's frontmatter claims capability X but the body doesn't support it; selector picks it for tasks needing X; executor underperforms.
**Detection:** user feedback on outputs; failing golden Runs.
**Recovery:** capabilities corrected; tests added.
### 10.7 Tool list out of sync with executor reality
**Failure:** agent's `allowed_tools` lists a tool Claude Code no longer provides.
**Detection:** Claude Code at execution time errors; CEE catches via output validator (Phase 2) or user report (Phase 1).
**Recovery:** tool list updated; tests pin the canonical tool set per Claude Code version.
### 10.8 Agent generation is over-eager
**Failure:** generator creates a new agent when an existing one with a slightly different `description` would have worked.
**Detection:** review of the generation log shows close matches that scored just below threshold.
**Recovery:** thresholds tuned; descriptions of existing agents improved to match more queries.
### 10.9 Specialist runaway
**Failure:** every Run generates a new specialist instead of reusing.
**Detection:** specialist count growth over time.
**Recovery:** specialist generation requires explicit OPERATOR confirmation in the CLI prompt.
### 10.10 Composition pattern doesn't match selected postures
**Failure:** AgentPlan says `primary + optimizer` but composition pattern says `primary_then_critic`.
**Detection:** AgentPlan validator.
**Recovery:** halt with explicit error; pattern selection logic fixed.
---
## 11. Build Notes for Claude Code
- **Selector location:** `~/cee/agent_selector/selector.py`. Public function: `run(classification, intent_object) -> AgentPlan`.
- **Generator location:** `~/cee/agent_selector/generator.py`. Public function: `generate(posture, intent_object, classification) -> Path`.
- **Registry location:** `~/cee/agent_selector/registry.py`. Public function: `rebuild() -> AgentIndex`. Called by boot.
- **Composition patterns:** `~/cee/agent_selector/composition_patterns.py` exports `pattern_for(plan: AgentPlan) -> str`. Closed enum of patterns.
- **Tool defaults:** `~/cee/agent_selector/tool_defaults.json` maps posture → default `allowed_tools` list. Generator uses this when `IntentObject` doesn't specify.
- **Scoring weights:** declared in `~/cee/agent_selector/scoring.py` as constants. Tunable via `~/.cee/config.toml`.
- **Agent body validator:** `~/cee/agent_selector/body_validator.py` runs after generation; uses temperature 0 LLM check to verify body matches frontmatter posture.
- **Tests:** `~/cee/tests/unit/test_agent_selector/` covers per-tier selection, scoring tie-breaks, generation triggers, validation. Golden Runs in `~/cee/runs/golden/` exercise the full path.
- **CLI override:** `cee run --agents <slug>,<slug>` is implemented in `~/cee/cli.py`. Validates against registry before invoking pipeline.
- **No agent state outside files.** Agents are filesystem-only. The registry is a derived index. There is no in-memory agent state between Runs.
---
## 12. Definition of Done
This page is complete — and the agent system is unblocked for build — when:
- [ ] The closed posture enum in §5.1 is reflected in `~/cee/schemas/agent_frontmatter.json`.
- [ ] `~/cee/.template/.claude/agents/` ships with the catalog in §5.6.
- [ ] `AGENT_SELECTOR` selects deterministically over the catalog for every `task_type` × `complexity` combination — verified by tests.
- [ ] Generation works end-to-end for at least one previously-uncovered `task_type` × `domain` combination.
- [ ] Generated agents validate against the frontmatter schema and pass body validation.
- [ ] Composition patterns cover all tier × posture combinations.
- [ ] CLI override (`--agents`) works.
- [ ] No agent state lives outside the filesystem.
- [ ] Agent failure modes in §10 each have a corresponding test in section 18.
---
## 13. Final Statement
Agents are who Claude becomes for a given Run. CEE selects them, the executor invokes them. The closed posture enum makes selection deterministic. The catalog makes most Runs reuse-only. The generation path covers the long tail. Everything that follows about how Claude executes a CEE Run starts from "which agent file did the FinalPrompt reference."
