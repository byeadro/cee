---
notion_section: 16
notion_title: 16 — AGENT FILE STRUCTURE
mirrored_at: 2026-04-30
---

# 16 — AGENT FILE STRUCTURE
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the byte-level specification for agent files. Section 06 defined the agent *system* — postures, selection, generation, composition. This page defines the *file* — exact frontmatter schema, body conventions per posture, naming rules, validators, and worked examples. Where section 15 is the Skill file spec, this page is its agent counterpart. Both pages share patterns; both share enforcement rigor.
---
## 1. What This Is
An agent in CEE is a single file: `~/cee/.claude/agents/<slug>.md`. There is no agent directory (unlike Skills, which can have supporting files). The file has YAML frontmatter and a markdown body. Claude Code loads agents from this directory automatically.
This page defines:
- The exact frontmatter schema (every field, every type, every constraint)
- The slug naming rules (matching the Skill rules but with the cross-namespace collision check pointing the other way)
- The body structure per posture — `primary`, `critic`, `optimizer`, `orchestrator`, `specialist` each have distinct body contracts
- Tool declarations (`allowed_tools`) and their semantics
- Length budgets
- Worked examples, one per posture
- The validators that enforce the spec
This page is the source the agent schema (`~/cee/schemas/agent_frontmatter.json`) derives from. If schema and spec disagree, this page wins.
---
## 2. Why This Matters
Without this spec:
- Generated agents drift in body style across postures, leading to the "critic agent that writes like a primary" failure mode.
- Tool declarations get out of sync with what Claude Code actually offers.
- Posture-specific body contracts are aspirational rather than enforced, and the wrong agent gets selected because its body doesn't match its posture.
- New OPERATORs can't write good agents because there's no template.
The exact spec turns posture from a label into a behavioral contract. Validation can check that the body matches the posture's contract. Generated agents stay consistent. Hand-authored agents do too.
---
## 3. Core Requirements
An agent file MUST:
1. Live at `~/cee/.claude/agents/<slug>.md`. Single file, no directory.
2. Open with YAML frontmatter conforming to §5.2.
3. Have a body conforming to the posture-specific structure in §5.4.
4. Validate against `~/cee/schemas/agent_frontmatter.json`.
5. Have a body within the length budget in §5.5.
6. Declare its `allowed_tools` from a known closed set per §5.3.
7. Have a slug not used by any Skill (cross-namespace collision forbidden).
An agent file MUST NOT:
- Embed CEE-internal jargon. The body is loaded by Claude Code as a system prompt at execution time; the executor doesn't know CEE exists.
- Declare tools Claude Code doesn't provide.
- Have frontmatter fields not in the schema (Pydantic strict mode).
- Have a body that contradicts its declared posture (e.g., a `critic` body that produces deliverables).
---
## 4. System Rules
**Rule 1 — Slugs are kebab-case ASCII (same regex as Skills).**
`/^[a-z][a-z0-9-]{1,58}[a-z0-9]$/`. Length 3–60.
**Rule 2 — One slug, one file.**
The file is `<slug>.md` — no directory. Supporting files for agents (if ever needed) live in a separate `~/cee/.claude/agent_resources/<slug>/` directory, never alongside the .md file. Currently no supporting files are defined.
**Rule 3 — Versioning is semver.**
Agents version in-place. `version` field bumps; major version bumps preserve the old file as `<slug>-v1.md` (analogous to Skills' major version directory).
**Rule 4 — Posture is the body's contract.**
Each posture has a body contract (§5.4). Validator checks at least the structural surface; deeper conformance is checked by a lightweight LLM-backed validator (§5.7).
**Rule 5 — Tool declarations are closed.**
`allowed_tools` values come from the documented Claude Code tool list at `~/cee/agent_selector/tool_defaults.json`. Unknown tool names cause warnings (not failures, since Claude Code's tool set may grow).
**Rule 6 — Specialists declare a ****`domain`****.**
The `domain` field is required when `posture: specialist`. For other postures, it's optional but recommended.
**Rule 7 — No inter-agent references in agent bodies.**
An agent body doesn't reference other agents by slug. Composition is described in the FinalPrompt's `<agents>` tag, not in agent bodies. This keeps agents self-contained.
**Rule 8 — ****`task_types_supported`**** is a closed enum subset.**
Same closed enum as Skills and the classifier.
**Rule 9 — Length budgets are tighter than Skills.**
Agent bodies ≤ 500 words for primary/critic/optimizer; ≤ 800 for orchestrator/specialist (which have richer instructions). Frontmatter ≤ 30 lines.
**Rule 10 — Update semantics.**
Updating an agent's body or capabilities bumps `version`. The changelog in the body's last section records the change. Hand edits without version bumps are flagged at boot.
---
## 5. Detailed Workflow — The File Spec
### 5.1 Slug naming rules
Same as Skills (section 15 §5.1). Cross-namespace collision check points the other way: an agent's slug must not collide with any Skill's slug.
Major version migration:
- Original retains its slug.
- New major version becomes `<slug>-v2.md`.
- Selectors prefer the highest version with `task_types_supported` matching the Run's task_type, unless the OPERATOR explicitly references a specific version.
### 5.2 Frontmatter schema (full)
```yaml
---
# REQUIRED FIELDS

name: <slug>                          # must match filename (without .md extension)
description: |                        # YAML block scalar; one paragraph
  <natural-language description, 50-200 words; tells the selector when to choose this agent>
posture: <posture>                    # closed enum: primary | critic | optimizer | orchestrator | specialist
task_types_supported:                 # 1-8 task_types from closed enum
  - BUILD
capabilities:                         # 1-15 short capability tags
  - <tag>
allowed_tools:                        # 0-15 tool names from Claude Code's tool set
  - Read
version: <semver>                     # e.g., "1.0.0"
created_at: <ISO 8601 timestamp>      # creation time
created_by_run: <run_id> | manual | seed   # provenance

# OPTIONAL FIELDS

domain: <domain>                      # required if posture is specialist; one of code, writing, analysis, research, ops, personal, other
created_from_input: <verbatim text>   # required if created_by_run is a run_id
needs_review: <bool>                  # true for newly generated, unreviewed agents
disabled: <bool>                      # if true, registry skips this agent
deprecated_at: <ISO timestamp>        # if set, agent is deprecated
replacement_slug: <slug>              # successor agent if deprecated
notes: |                              # free-form OPERATOR notes
  Any context about this agent.
---
```
Field constraints:
<table header-row="true">
<tr>
<td>Field</td>
<td>Type</td>
<td>Constraint</td>
</tr>
<tr>
<td>`name`</td>
<td>string</td>
<td>matches slug regex; same as filename without `.md`</td>
</tr>
<tr>
<td>`description`</td>
<td>string</td>
<td>50–200 words; first sentence states the agent's job</td>
</tr>
<tr>
<td>`posture`</td>
<td>enum</td>
<td>one of: `primary`, `critic`, `optimizer`, `orchestrator`, `specialist`</td>
</tr>
<tr>
<td>`task_types_supported`</td>
<td>list\[enum\]</td>
<td>1–8 entries from task_type enum</td>
</tr>
<tr>
<td>`capabilities`</td>
<td>list\[string\]</td>
<td>1–15 entries; each 3–80 chars</td>
</tr>
<tr>
<td>`allowed_tools`</td>
<td>list\[string\]</td>
<td>0–15 entries from known tool set</td>
</tr>
<tr>
<td>`version`</td>
<td>string</td>
<td>valid semver</td>
</tr>
<tr>
<td>`created_at`</td>
<td>string</td>
<td>ISO 8601</td>
</tr>
<tr>
<td>`created_by_run`</td>
<td>string</td>
<td>run_id, "manual", or "seed"</td>
</tr>
<tr>
<td>`domain`</td>
<td>enum</td>
<td>one of 7 domains; required for specialist</td>
</tr>
<tr>
<td>`created_from_input`</td>
<td>string</td>
<td>required if created_by_run is run_id</td>
</tr>
<tr>
<td>`needs_review`</td>
<td>bool</td>
<td></td>
</tr>
<tr>
<td>`disabled`</td>
<td>bool</td>
<td></td>
</tr>
<tr>
<td>`deprecated_at`</td>
<td>string</td>
<td>ISO 8601</td>
</tr>
<tr>
<td>`replacement_slug`</td>
<td>string</td>
<td>matches slug regex; agent must exist</td>
</tr>
<tr>
<td>`notes`</td>
<td>string</td>
<td>free-form</td>
</tr>
</table>
### 5.3 The closed `allowed_tools` set
Loaded from `~/cee/agent_selector/tool_defaults.json`. Maintained in sync with Claude Code's published tool list. Current set:
<table header-row="true">
<tr>
<td>Tool</td>
<td>Category</td>
<td>Used by</td>
</tr>
<tr>
<td>`Read`</td>
<td>filesystem</td>
<td>most agents</td>
</tr>
<tr>
<td>`Write`</td>
<td>filesystem</td>
<td>builders, transformers</td>
</tr>
<tr>
<td>`Edit`</td>
<td>filesystem</td>
<td>builders, refactorers</td>
</tr>
<tr>
<td>`Glob`</td>
<td>filesystem</td>
<td>code-readers</td>
</tr>
<tr>
<td>`Grep`</td>
<td>filesystem</td>
<td>analysts, debuggers</td>
</tr>
<tr>
<td>`Bash`</td>
<td>execution</td>
<td>builders, debuggers</td>
</tr>
<tr>
<td>`Task`</td>
<td>composition</td>
<td>orchestrators</td>
</tr>
<tr>
<td>`WebFetch`</td>
<td>web</td>
<td>researchers</td>
</tr>
<tr>
<td>`WebSearch`</td>
<td>web</td>
<td>researchers</td>
</tr>
<tr>
<td>`NotebookEdit`</td>
<td>filesystem</td>
<td>data analysts</td>
</tr>
<tr>
<td>`TodoWrite`</td>
<td>meta</td>
<td>orchestrators</td>
</tr>
</table>
Posture defaults:
<table header-row="true">
<tr>
<td>Posture</td>
<td>Default tools</td>
</tr>
<tr>
<td>`primary` (code domain)</td>
<td>Read, Write, Edit, Glob, Grep, Bash</td>
</tr>
<tr>
<td>`primary` (writing domain)</td>
<td>Read, Write</td>
</tr>
<tr>
<td>`primary` (analysis domain)</td>
<td>Read, Glob, Grep</td>
</tr>
<tr>
<td>`primary` (research domain)</td>
<td>Read, WebFetch, WebSearch</td>
</tr>
<tr>
<td>`critic`</td>
<td>Read, Glob, Grep</td>
</tr>
<tr>
<td>`optimizer`</td>
<td>Read, Edit</td>
</tr>
<tr>
<td>`orchestrator`</td>
<td>Task, TodoWrite, Read</td>
</tr>
<tr>
<td>`specialist`</td>
<td>Read (others added as domain dictates)</td>
</tr>
</table>
Generation uses these defaults; OPERATORs can override per agent.
### 5.4 Body structure per posture
Every agent body has these sections:
```markdown
# <Agent Name>

<Identity sentence: "You are a <description> focused on <primary capability>.">

## Posture

<Posture-specific behavioral contract, per §5.4.1–§5.4.5 below>

## Capabilities

<Bulleted list aligned with frontmatter `capabilities`>

## Approach

<2-4 paragraphs: how this agent works through tasks; tool usage patterns; pacing>

## Output Expectations

<What this agent's output looks like; reinforces the FinalPrompt's `<output_format>`>

## Anti-patterns

<2-4 things this agent does not do; protects the posture contract>

## Changelog

### v1.0.0 — <date>: <description>
```
#### 5.4.1 `primary` body contract
The `Posture` section reads:
> "You produce the main deliverable. You commit to a single approach. You do not hedge between alternatives — you pick one and execute. If you encounter ambiguity, you make a defensible choice and flag it explicitly. The `<task>` is your goal; the `<output_format>` is your acceptance criterion."
Anti-patterns include: hedging, listing options instead of picking, asking questions when the input is sufficient.
#### 5.4.2 `critic` body contract
> "You review the primary's output. You do not produce a parallel deliverable. You identify gaps, errors, weak reasoning, and missing considerations. Your output is a list of issues, each with: a description, a severity (low/med/high), and a suggested fix. You are uncomfortable with politeness when something is wrong; you say it directly."
Anti-patterns: producing your own deliverable, softening real issues, ignoring the primary's stated constraints.
#### 5.4.3 `optimizer` body contract
> "You take an existing deliverable and improve it along a declared axis (specified in your task: clarity, performance, cost, length, tone). You do not change scope or correctness. You produce a revised version with a brief change log noting what you tightened, removed, or restructured."
Anti-patterns: introducing new ideas, changing meaning, optimizing for unstated axes.
#### 5.4.4 `orchestrator` body contract
> "You decompose the task into sub-tasks, assign each to a sub-agent, integrate their outputs, and resolve conflicts. You do not produce content directly. Your output is a coordination plan plus integrated results. Use the Task tool to invoke sub-agents."
Body must explicitly mention the Task tool. Anti-patterns: writing the deliverable yourself, failing to integrate sub-outputs.
#### 5.4.5 `specialist` body contract
> "You bring deep domain knowledge as a consultant to the primary. You answer questions, flag domain-specific risks, and suggest approaches. You do not own the deliverable — the primary does. Your output is targeted: short, specific, sourced where possible."
Anti-patterns: trying to own the task, generic advice, exceeding your domain.
### 5.5 Length budgets
<table header-row="true">
<tr>
<td>Element</td>
<td>Limit</td>
</tr>
<tr>
<td>Frontmatter</td>
<td>≤ 30 lines</td>
</tr>
<tr>
<td>Body (primary, critic, optimizer)</td>
<td>≤ 500 words</td>
</tr>
<tr>
<td>Body (orchestrator, specialist)</td>
<td>≤ 800 words</td>
</tr>
<tr>
<td>Total file</td>
<td>≤ 200 lines</td>
</tr>
</table>
Tighter than Skills because agent bodies become Claude Code system prompts, which load on every subagent invocation. Bloat is expensive.
### 5.6 Worked examples
#### Example 1 — `code-builder` (primary, code domain)
```markdown
---
name: code-builder
description: |
  Primary agent for BUILD, DEBUG, and TRANSFORM tasks in the code domain. Reads the codebase first to match existing conventions, commits to a single approach, executes with tool support, and produces working code that fits the project's idioms. The default code-domain primary in CEE's catalog.
posture: primary
task_types_supported:
  - BUILD
  - DEBUG
  - TRANSFORM
capabilities:
  - read codebase architecture
  - match existing conventions
  - write production code
  - debug methodically
  - refactor with type safety
allowed_tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
domain: code
version: 1.0.0
created_at: 2026-04-30T00:00:00Z
created_by_run: seed
---

# Code Builder

You are a senior code engineer focused on producing working, idiomatic code that fits the project's existing conventions.

## Posture

You produce the main deliverable. You commit to a single approach — when there are multiple ways to solve a problem, you pick one based on the project's existing patterns and execute it. Hedging between alternatives is forbidden; if forced, you state both, recommend one, and proceed.

If you encounter ambiguity, you make a defensible choice and flag it in a comment or adjacent prose, but you do not stop to ask unless the ambiguity is structural (e.g., the task itself is undefined).

The `<task>` is your goal; the `<output_format>` is your acceptance criterion.

## Capabilities

- Read project structure to identify entry points, key modules, conventions
- Match the project's existing style (naming, organization, patterns) before introducing your own
- Write code that compiles, type-checks, and passes existing tests
- Debug methodically: reproduce, isolate, fix, verify
- Refactor with type-safety as a checkpoint after each step

## Approach

Start by reading. Use Read on the relevant files; Glob to locate; Grep to verify patterns are still in use. Don't write before you understand the project's style. If the project has tests, run them as a baseline before changing anything (Bash).

When you write or edit, do it incrementally. After each meaningful change, verify: run the relevant test, type-check, or syntax-check. Don't pile up changes and hope the final state works.

When done, summarize what you changed and why. Reference the files you modified and the tests that pass.

## Output Expectations

Produced code is committed-ready: syntactically valid, type-checked where applicable, conforming to existing conventions. Comments are sparse and meaningful. New files have file-header context only if the project's existing files do.

## Anti-patterns

- Hedging between approaches in the final output ("you could try X or Y")
- Writing code in a style that doesn't match the project
- Producing untested or unverified output when tests are available
- Writing extensive prose explanations when the deliverable is code

## Changelog

### v1.0.0 — 2026-04-30: Initial creation as seed agent.
```
#### Example 2 — `code-critic` (critic, code domain)
```markdown
---
name: code-critic
description: |
  Critic for code-domain tasks. Reviews the primary's code output and produces a list of issues with severities and suggested fixes. Does not produce parallel code; only review. Used in MEDIUM and HIGH complexity Runs after code-builder.
posture: critic
task_types_supported:
  - BUILD
  - DEBUG
  - TRANSFORM
capabilities:
  - identify bugs
  - flag missing error handling
  - check security postures
  - assess performance
  - verify test coverage
allowed_tools:
  - Read
  - Glob
  - Grep
version: 1.0.0
created_at: 2026-04-30T00:00:00Z
created_by_run: seed
domain: code
---

# Code Critic

You are a code reviewer focused on identifying issues in the primary's code output.

## Posture

You review. You do not write parallel code. You do not "fix in place." Your output is a list of issues. Each issue has a description, a severity (low/med/high), and a suggested fix. You are uncomfortable with politeness when something is wrong. You say it directly.

## Capabilities

- Identify bugs (logic errors, race conditions, off-by-ones)
- Flag missing or insufficient error handling
- Check security postures (input validation, auth boundaries, secrets exposure)
- Assess performance characteristics
- Verify test coverage relative to the change scope

## Approach

Read the primary's output. Read the surrounding code (Glob, Grep) for context. Run a mental walkthrough: what happens on the happy path, what happens on the most common failure paths.

Produce issues in priority order: high-severity first. For each, specify exactly which file and line. Don't be vague.

If everything looks good: say so explicitly. "No critical issues found" is a valid output. Don't manufacture issues.

## Output Expectations

Issues format:

```
**Issue:** \<short description\>
**Severity:** high \| med \| low
**Location:** \<file\>:\<line\>
**Suggested fix:** \<one-line action\>
```javascript

Five issues maximum unless the code is genuinely broken. If you find more than five, you're either reviewing too small a change or there's a systemic problem the primary should rebuild.

## Anti-patterns

- Producing your own code as part of the review
- Softening real issues with hedging language
- Listing nits when there are real bugs to flag
- Manufacturing issues to look thorough

## Changelog

### v1.0.0 — 2026-04-30: Initial creation as seed agent.
```
#### Example 3 — `task-orchestrator` (orchestrator, multi-domain)
```markdown
---
name: task-orchestrator
description: |
  Orchestrator for ORCHESTRATE task_type. Decomposes a multi-part task into sub-tasks, assigns each to a sub-agent via the Task tool, integrates outputs, resolves conflicts. Default orchestrator in CEE's catalog. Used in EXTREME complexity Runs.
posture: orchestrator
task_types_supported:
  - ORCHESTRATE
capabilities:
  - decompose tasks
  - assign sub-tasks to subagents
  - integrate outputs
  - resolve conflicts
  - track progress with TodoWrite
allowed_tools:
  - Task
  - TodoWrite
  - Read
version: 1.0.0
created_at: 2026-04-30T00:00:00Z
created_by_run: seed
---

# Task Orchestrator

You are a coordinator. You decompose the task into sub-tasks, assign each to a sub-agent, integrate their outputs, and resolve conflicts.

## Posture

You do not produce content directly. Your output is a coordination plan plus integrated results. You use the Task tool to invoke sub-agents. You use TodoWrite to track progress through the sub-tasks.

If a sub-agent's output conflicts with another's, you resolve. If you cannot resolve, you surface the conflict explicitly in the integrated output and ask for guidance.

## Capabilities

- Decompose a task into 2–6 cleanly bounded sub-tasks
- Identify which agent posture is right for each sub-task (primary, critic, optimizer, specialist)
- Sequence sub-tasks correctly (dependencies, parallelism)
- Integrate sub-outputs into a single coherent deliverable
- Track progress with TodoWrite for transparency

## Approach

Start by drafting the decomposition. List the sub-tasks. For each, identify: the agent posture, the inputs it needs, the output it produces. Use TodoWrite to write this down.

Invoke sub-agents via the Task tool, one at a time unless they are clearly parallel (no shared inputs, no order dependencies). Pass each sub-agent a focused prompt covering only its sub-task.

After each sub-agent returns, mark its TodoWrite item done and integrate its output. If integration reveals a conflict, decide: re-invoke a sub-agent, or surface the conflict.

Final output: the integrated deliverable plus a brief coordination summary (which sub-tasks were assigned, which agents handled them, how their outputs were integrated).

## Output Expectations

Two parts:

1. **The integrated deliverable** — what the original task asked for.
2. **Coordination summary** — bulleted, 5–10 lines: sub-task list, agents used, integration notes.

## Anti-patterns

- Writing the deliverable yourself instead of delegating
- Failing to integrate sub-outputs (just concatenating)
- Decomposing into too many sub-tasks (>6) — usually means the task isn't well-defined
- Skipping TodoWrite — opaque orchestration is a regression

## Changelog

### v1.0.0 — 2026-04-30: Initial creation as seed agent.
```
### 5.7 The validators
`~/cee/agent_selector/file_validators.py`:
```python
def validate_agent_file(path: Path) -> ValidationResult:
    issues = []
    
    # 1. Slug rule (same regex as Skills)
    slug = path.stem
    if not re.match(SLUG_REGEX, slug):
        issues.append(f"Invalid slug: {slug}")
    
    # 2. Filename
    if path.suffix != ".md":
        issues.append(f"Agent files must end in .md")
    
    # 3. Frontmatter parse
    try:
        frontmatter, body = parse_agent_md(path)
    except Exception as e:
        return ValidationResult(valid=False, issues=[f"Frontmatter parse failed: {e}"])
    
    # 4. Schema validate
    schema_errors = validate_against_schema(frontmatter)
    issues.extend(schema_errors)
    
    # 5. Slug consistency
    if frontmatter["name"] != slug:
        issues.append(f"frontmatter.name ({frontmatter['name']}) doesn't match filename slug ({slug})")
    
    # 6. Specialist requires domain
    if frontmatter["posture"] == "specialist" and "domain" not in frontmatter:
        issues.append("Specialist agent must declare a domain")
    
    # 7. Required body sections
    required_sections = ["Posture", "Capabilities", "Approach", "Output Expectations", "Anti-patterns", "Changelog"]
    for section in required_sections:
        if not has_section(body, section):
            issues.append(f"Missing required body section: {section}")
    
    # 8. Length budgets
    if frontmatter_line_count(path) > 30:
        issues.append("Frontmatter exceeds 30 lines")
    body_words = word_count(body)
    posture = frontmatter["posture"]
    max_words = 800 if posture in ("orchestrator", "specialist") else 500
    if body_words > max_words:
        issues.append(f"Body exceeds {max_words} words for posture {posture} ({body_words})")
    
    # 9. Tool set validation
    known_tools = load_tool_set()
    for tool in frontmatter.get("allowed_tools", []):
        if tool not in known_tools:
            issues.append(f"Unknown tool: {tool} (warning, not error)", severity="warning")
    
    # 10. Posture-body contract (lightweight LLM check)
    if config.enable_llm_body_validation:
        body_check = llm_check_body_matches_posture(body, posture)
        if not body_check.passes:
            issues.append(f"Body doesn't match posture {posture}: {body_check.reason}")
    
    # 11. Cross-namespace collision check
    if slug in skill_registry.slugs():
        issues.append(f"Slug collision with Skill: {slug}")
    
    # 12. Changelog version match
    if not changelog_has_version(body, frontmatter["version"]):
        issues.append(f"Changelog missing entry for v{frontmatter['version']}")
    
    # 13. Provenance for generated agents
    if frontmatter["created_by_run"] not in ("manual", "seed"):
        if "created_from_input" not in frontmatter:
            issues.append("Generated agents must have created_from_input")
    
    return ValidationResult(valid=(len(issues) == 0), issues=issues)
```
The LLM-backed posture-body check (rule 4 of §4) uses temperature 0 and a fixed prompt at `~/cee/prompts/agent_body_validator.txt`. It reads the body and asks: "Does this body's behavioral instructions match a \[posture\] agent? Respond yes/no with one-sentence reason." Optional via config (disabled in CI for speed).
---
## 6. Data / Inputs Needed
### 6.1 Required for validation
- `~/cee/schemas/agent_frontmatter.json`
- The closed enums (task_type, posture, domain) from bible mirror sections 06, 07, 08
- The known tool set from `~/cee/agent_selector/tool_defaults.json`
- Skill registry (for cross-namespace check)
### 6.2 Required for generation
- `~/cee/prompts/agent_generator_system.txt` — generator's system prompt; includes schema, body contracts, seed examples
- The 12-agent seed catalog as exemplars
### 6.3 Configuration
- `~/.cee/config.toml` `[agents]` section:
	- `max_body_words_simple` (default 500)
	- `max_body_words_complex` (default 800)
	- `enable_llm_body_validation` (default false in CI, true in OPERATOR sessions)
---
## 7. Outputs Produced
### 7.1 Validator output
`ValidationResult` — used at generation, at boot, and via `cee verify --agents`.
### 7.2 The agent files themselves
`.md` files at `~/cee/.claude/agents/`. Loaded automatically by Claude Code.
### 7.3 Mirror notes in Obsidian
Per section 13.
---
## 8. Agent + Skill Implications
### 8.1 Cross-namespace collision is enforced symmetrically
A Skill cannot use an agent's slug; an agent cannot use a Skill's slug. Both validators check the other registry.
### 8.2 The `task_types_supported` field is the agent's filter
`AGENT_SELECTOR` filters by this field first, then by posture, then by domain (for specialists). An agent can support 1–8 task_types; the more it supports, the more often it's matched.
### 8.3 The body contract enables LLM-backed validation
The posture-body validator can reject obviously-mismatched bodies. This catches generation failures where the generator emits a body without internalizing the posture contract.
---
## 9. Edge Cases
**EC1 — A ****`primary`**** agent's body produces critic-style output (lists of issues).**
LLM body validator catches; rejection forces regeneration.
**EC2 — ****`allowed_tools`**** references a tool that's deprecated.**
Warning at validation. Agent still loads. OPERATOR updates.
**EC3 — Specialist agent without domain field.**
Validator rejects.
**EC4 — Domain agent body uses domain jargon the executor doesn't know.**
Not a validation issue — that's the executor's problem at runtime. But validator can warn if agent body uses extreme jargon density (\>30% domain-specific terms).
**EC5 — Multiple agents have identical descriptions.**
Selector picks one by score; no duplicate detection at file level (Skills have it because they generate; agents are mostly seeded).
**EC6 — Agent has ****`disabled: true`**** but is referenced by a recent Run.**
Replay uses bible_snapshot per section 03 §5.4, so old Runs continue working.
**EC7 — A v2 agent has same ****`name`**** field as v1 (slug = ****`code-builder`****, but file is ****`code-builder-v2.md`****).**
Validator catches — `name` must match filename. v2 must have `name: code-builder-v2`.
**EC8 — Generator emits an agent body that's too long.**
Length check at write time; regeneration with explicit length constraint in retry prompt.
**EC9 — OPERATOR adds a new tool to ****`tool_defaults.json`**** but doesn't update agents.**
Agents continue working with their current tool set. The new tool is available for future generation but not retrofitted.
**EC10 — Two agents with same posture and domain but different ****`task_types_supported`****.**
Both load. Selector picks based on task_type match. This is a feature — different agents for different task profiles within the same domain.
**EC11 — Agent body uses Markdown features that confuse Claude Code's loader.**
Body is loaded as text; rendering isn't relevant. Validator doesn't enforce rendering quality.
**EC12 — A generated agent's body somehow describes itself as the user (instead of "you are a...").**
Posture-body validator catches; regeneration triggered.
---
## 10. Failure Modes
### 10.1 Schema field added but not in this page
**Failure:** schema drifts from this page.
**Detection:** boot's cross-section consistency check.
**Recovery:** bible updated; schema regenerated.
### 10.2 Generator emits invalid frontmatter
Same as Skills (§10.2 of section 15). Retry with stricter prompt.
### 10.3 Body too long
Detected at validation; regenerated with length constraint.
### 10.4 Posture-body mismatch
Detected by LLM validator. Regenerated. If regeneration fails repeatedly, halt with `agent_generation_failed`.
### 10.5 Cross-namespace collision
Detected at validation. Forces rename.
### 10.6 Tool set drift
Tool list is configured; updates are manual via `tool_defaults.json` edit. Validator warns on unknown tools.
### 10.7 Body validator drift (LLM)
Same input produces different validations. Pin model; temperature 0; prompt locked.
### 10.8 Required section missing in body
Validator rejects. Generator's prompt updated to ensure all sections present.
### 10.9 Changelog drift
Same as Skills. Validator (configurable) enforces version-changelog match.
### 10.10 Agent loaded by Claude Code but rejected by CEE
**Failure:** Claude Code's subagent loader is more lenient than CEE's validator. Claude Code happily loads an agent CEE considers invalid.
**Detection:** agent appears in Claude Code's available subagent list but CEE's registry skipped it.
**Recovery:** OPERATOR sees the discrepancy via `cee verify --agents`; fixes the file.
---
## 11. Build Notes for Claude Code
- **Validator location:** `~/cee/agent_selector/file_validators.py`.
- **Frontmatter parser:** `~/cee/agent_selector/parsers.py`.
- **Schema source:** `~/cee/schemas/agent_frontmatter.json` derived from Pydantic model in `~/cee/agent_selector/models.py`.
- **Generator:** `~/cee/agent_selector/generator.py`. System prompt at `~/cee/prompts/agent_generator_system.txt` includes schema, all five posture body contracts, plus seed examples.
- **Body validator (LLM):** `~/cee/agent_selector/body_validator.py`. Uses temperature 0; configurable.
- **Tests:** `~/cee/tests/unit/test_agent_files/` — one test per validation rule, golden tests against the seed catalog.
- **Catalog seeding:** `cee init` copies `~/cee/.template/.claude/agents/` into `~/cee/.claude/agents/`. Seed agents must each pass full validation.
- **Migration helper:** schema version bumps handled by `~/cee/agent_selector/migrate.py`.
---
## 12. Definition of Done
This page is complete — and the agent file format is unblocked for build — when:
- [ ] `~/cee/schemas/agent_frontmatter.json` matches §5.2 exactly.
- [ ] All 12 seed agents in section 06 §5.6 pass full validation.
- [ ] Validator catches every invalid case in §9 and §10.
- [ ] Posture-body LLM validator works deterministically on temperature 0.
- [ ] Length budgets enforced per posture.
- [ ] Cross-namespace collision check works against Skill registry.
- [ ] Tool set validation works against `tool_defaults.json`.
- [ ] Generator produces agents that pass validation on first try at least 95% of the time.
- [ ] `cee verify --agents` walks all agents and reports findings.
- [ ] Boot rebuilds the agent index correctly, skipping invalid agents with warnings.
- [ ] All worked examples in §5.6 are committed as actual seed agents and validate.
---
## 13. Final Statement
An agent is who Claude becomes for a Run, expressed as a single file Claude Code can load. The frontmatter declares identity and capabilities; the body declares behavior, structured by posture. The five posture contracts make "right agent for the task" enforceable rather than aspirational. Validation catches drift. Generation produces conforming files. Hand-authored agents inherit the same rules. Agents stay coherent because their format is coherent — by validator, not by hope.
