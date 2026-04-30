---
notion_section: 07
notion_title: 07 — SKILL SYSTEM DESIGN
mirrored_at: 2026-04-30
---

# 07 — SKILL SYSTEM DESIGN
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the complete specification for Skills in CEE — what they are, how they're stored, how they're matched, how new ones are generated, and how they're promoted to canonical status. Skills are the persistent memory layer; they exist because a system that re-explains itself every Run is a worse system than one that learns once and reuses.
---
## 1. What This Is
A Skill in CEE is a Claude Code [SKILL.md](http://SKILL.md) file: YAML frontmatter plus a body of natural-language instructions describing *how to do something*. Skills live at `~/cee/skills/<slug>/SKILL.md` in the format Claude Code natively loads.
Skills differ from agents in three structural ways:
- **Identity.** An agent is *who* Claude is. A Skill is *what Claude can do*.
- **Composition.** A Run uses one to many Skills, plus exactly one primary agent. Skills stack; agents (mostly) don't.
- **Generation cadence.** Agents come from a small, slow-growing catalog. Skills grow continuously — every novel reusable instruction becomes a new Skill.
This page defines:
- The Skill file format (frontmatter schema + body conventions)
- How `SKILL_ENGINE` matches required capabilities to existing Skills
- The generation path when no Skill matches
- The promotion path: filesystem → Obsidian → Notion canon
- The starter catalog of pre-built Skills
- The "is this really a new Skill or am I duplicating?" detection
---
## 2. Why This Matters
Skills are the difference between a system that learns and one that doesn't. Without Skills:
- Every Run re-explains the same conventions ("when summarizing legal docs, always extract X, Y, Z").
- Outputs drift across Runs because the user's preferred style isn't captured.
- The user becomes the memory layer, manually copy-pasting context into every prompt.
With Skills, the first Run that needs a new capability generates a Skill; every subsequent Run that needs the same capability references it. The user's accumulated knowledge becomes infrastructure.
The bar for what gets to be a Skill is high though — proliferation kills reuse. This page defines that bar.
---
## 3. Core Requirements
The Skill system MUST:
1. Store every Skill as a [SKILL.md](http://SKILL.md) file at `~/cee/skills/<slug>/SKILL.md`, plus optional supporting files in the same directory.
2. Use Claude Code's native [SKILL.md](http://SKILL.md) format — no parallel custom format.
3. Provide a deterministic matcher: given an `IntentObject`'s required capabilities, return existing Skills that cover them.
4. Generate new Skills only when the gap is real — close-but-not-perfect matches default to reuse, not generation.
5. Track every Skill's provenance: which Run created it, what input triggered it.
6. Mirror to Obsidian (auto) and queue for Notion promotion (manual approval).
7. Support versioning — a Skill can evolve (`v1` → `v2`) without breaking older Runs that reference `v1`.
The Skill system MUST NOT:
- Generate a Skill that overwrites an existing Skill with a different signature.
- Allow Skill generation without a defined `IntentObject` triggering it (no orphan Skills).
- Embed CEE-internal logic in Skill bodies. Skills describe how to do user-facing work, not how CEE works.
- Treat Skills as runtime configuration. Skills are reference material; CEE doesn't execute them.
---
## 4. System Rules
**Rule 1 — One Skill per directory.**
Each Skill lives in its own subdirectory: `~/cee/skills/<slug>/`. The main file is `SKILL.md`. Supporting files (examples, references) live alongside.
**Rule 2 — The slug is the identity.**
A Skill's identity is its slug. Two Skills with the same slug are the same Skill (different versions or duplicates). Slug uniqueness is enforced by filesystem.
**Rule 3 — Versioning is semver.**
A Skill's `version` field follows semver. Major version bumps for incompatible changes; minor for additive; patch for clarifications.
**Rule 4 — Reuse defaults; generation is the exception.**
The matcher's `reuse_threshold` (default 0.85) is high. Below it but above `ask_threshold` (default 0.60), CEE asks. Below `ask_threshold`, CEE generates.
**Rule 5 — A Skill must be reusable.**
The bar for generating a new Skill is "this could plausibly be reused on at least 3 future Runs." One-off instructions go in `<constraints>` of the FinalPrompt, not in a Skill.
**Rule 6 — Generated Skills carry provenance.**
Every generated Skill's frontmatter includes `created_by_run` and the original input that triggered generation. This makes audit trivial.
**Rule 7 — Skills are filesystem-canonical.**
A Skill's existence is its file existing. Notion promotion is a separate canon (the bible says "this Skill is approved"); filesystem usability does not depend on Notion approval.
**Rule 8 — Skill bodies are Claude Code native.**
The body follows Claude Code's [SKILL.md](http://SKILL.md) conventions (instructions, examples, tool usage notes). CEE does not invent body conventions.
**Rule 9 — Skill registry rebuilds on boot.**
No incremental state. Every boot walks `~/cee/skills/` and rebuilds `index.json`. This means hand-edits to Skills are picked up immediately.
**Rule 10 — Skills are self-contained.**
A Skill does not reference other Skills by hard dependency. If two Skills are always used together, they are merged into one. If they're sometimes used together, the FinalPrompt's `<skills>` tag references both — composition happens at Run time, not at Skill definition time.
---
## 5. Detailed Workflow — The Skill System
### 5.1 Skill file format
#### 5.1.1 Frontmatter schema (`~/cee/schemas/skill_frontmatter.json`)
```yaml
---
name: <kebab-case-slug>
description: |
  One paragraph describing what this Skill does, in natural language.
  Used for matching — the matcher compares this against IntentObject capability needs.
  Be specific about when this Skill applies and what it produces.
version: <semver>
triggers:
  - <natural-language phrase that should activate this Skill>
  - <another phrase>
inputs:
  - <expected input type or shape>
outputs:
  - <produced output type or shape>
task_types_supported: [BUILD, ANALYZE, DEBUG, WRITE, RESEARCH, TRANSFORM, DECIDE, ORCHESTRATE]
posture_hints: [primary, critic, optimizer]
domain: <optional; one of code | writing | analysis | research | ops | personal | other>
created_by_run: <run_id> | manual | seed
created_at: <ISO timestamp>
created_from_input: <verbatim user input that triggered generation, if applicable>
needs_review: false
---
```
Required: `name`, `description`, `version`, `triggers`, `inputs`, `outputs`, `task_types_supported`. Optional: `posture_hints`, `domain`, `created_by_run`, `created_at`, `created_from_input`, `needs_review`.
#### 5.1.2 Body conventions
The body is Claude Code native [SKILL.md](http://SKILL.md). Conventions:
- Open with a one-paragraph statement of what the Skill does and when to use it.
- Provide step-by-step instructions where the work has structure.
- Include at least one worked example showing input → output.
- Note any tool usage assumptions (e.g., "this Skill assumes Read and Edit are available").
- Avoid CEE-internal jargon. The Skill is read by Claude Code at execution time, which doesn't know CEE exists.
- Keep length 200–800 words for typical Skills. Specialized or complex Skills can exceed this; review carefully.
#### 5.1.3 Supporting files in the Skill directory
Optional, in `~/cee/skills/<slug>/`:
- `examples.md` — additional worked examples.
- `references.md` — links to docs, papers, prior Runs that informed this Skill.
- `_meta.json` — extended provenance (the originating IntentObject, the Run trace).
The matcher only reads `SKILL.md`; supporting files are for human reference.
### 5.2 The matcher algorithm
`SKILL_ENGINE.resolve(intent_object, classification, agent_plan) -> SkillSet`:
```javascript
def resolve(intent_object, classification, agent_plan):
    skill_set = []
    required_capabilities = extract_capabilities(intent_object, classification, agent_plan)
    
    for cap in required_capabilities:
        candidates = registry.search(cap)  # semantic search over descriptions + triggers
        candidates = candidates.filter(
            task_types_supported__contains=classification.task_type
        )
        
        if not candidates:
            best_score = 0.0
            best = None
        else:
            best, best_score = top_match(candidates, cap, intent_object)
        
        if best_score >= REUSE_THRESHOLD:  # 0.85
            skill_set.append(best)
        elif best_score >= ASK_THRESHOLD:  # 0.60
            raise PipelineHalt("skill_resolution_choice", {
                "capability": cap,
                "best_match": best,
                "score": best_score
            })
        else:
            new_skill = generator.generate(cap, intent_object, classification)
            skill_set.append(new_skill)
    
    return SkillSet(skills=skill_set)
```
The capability extraction draws from:
- `IntentObject.required_capabilities` (if interpreter populated it)
- Verb + object pairs in `IntentObject.goal` ("summarize legal docs" → capability: "summarize legal documents")
- Implicit needs from `Classification.task_type` (e.g., DEBUG implies a "diagnose-and-fix" capability)
### 5.3 Capability extraction
The matcher needs to know what capabilities the Run requires. Extraction sources:
<table header-row="true">
<tr>
<td>Source</td>
<td>What it contributes</td>
</tr>
<tr>
<td>`IntentObject.required_capabilities`</td>
<td>Direct list (if interpreter extracted it)</td>
</tr>
<tr>
<td>`IntentObject.goal` parsed for verb+object</td>
<td>"Refactor X to Y" → capability "refactor X"</td>
</tr>
<tr>
<td>`IntentObject.deliverable` shape</td>
<td>"A summary" → capability "summarize"</td>
</tr>
<tr>
<td>`IntentObject.domain`</td>
<td>Domain-specific capability bundles (e.g., "code" → "read code", "edit code")</td>
</tr>
<tr>
<td>`Classification.task_type`</td>
<td>Default capability set per task type</td>
</tr>
<tr>
<td>`AgentPlan.primary.capabilities`</td>
<td>Capabilities the agent expects to leverage</td>
</tr>
</table>
Extracted capabilities are normalized — "summarize legal docs" and "summarize legal documents" map to the same canonical form. Normalization uses a canonicalizer at `~/cee/skill_engine/canonicalizer.py`.
### 5.4 Skill generation
When `SKILL_ENGINE` decides to generate:
1. Generator (`~/cee/skill_engine/generator.py`) constructs frontmatter from:
	- `name` slugified from the capability + a short distinguisher
	- `description` written by Claude (temperature 0, fixed prompt at `~/cee/prompts/skill_generator_system.txt`)
	- `triggers` derived from `IntentObject.goal` and related phrasing
	- `inputs`, `outputs` inferred from `IntentObject.deliverable`
	- `task_types_supported` from `Classification.task_type`
	- `domain` from `IntentObject.domain`
	- `created_by_run`, `created_at`, `created_from_input` populated
2. Generator writes the body via the same Claude call that produced the description, but with explicit instructions to follow Claude Code [SKILL.md](http://SKILL.md) conventions.
3. Validates against `skill_frontmatter.json` schema.
4. Checks for slug collision. If collision, append `-v2` and bump version.
5. Writes to `~/cee/skills/<slug>/SKILL.md` with `needs_review: true`.
6. Mirrors to Obsidian.
7. Queues promotion candidate for Notion.
### 5.5 Promotion
Async to Runs. The cycle:
1. Generated Skill written to filesystem with `needs_review: true`.
2. Promotion queue entry created in `~/cee/promotion_queue.json`.
3. On `cee promote <slug>` or boot's queue drain: a candidate page is created in Notion under `system design bible / Skill Promotions / Pending /`.
4. Page contains: Skill name, slug, version, full [SKILL.md](http://SKILL.md) content, provenance (Run ID, original input), approve/reject action.
5. OPERATOR moves the page to `Approved` or `Rejected` in Notion.
6. CEE detects the move on next sync, updates `promotion_queue.json`, clears `needs_review` on approval.
A rejected Skill stays in `~/cee/skills/` and remains usable. Rejection just means "don't promote to bible canon." The OPERATOR can also delete the Skill manually if they don't want it usable.
### 5.6 Versioning
Skill versioning follows semver. Mechanics:
- A new Skill starts at `1.0.0`.
- An additive change (clarifying instructions, adding triggers) bumps to `1.1.0`.
- An incompatible change (different inputs/outputs, different task_types_supported) starts a new Skill at `2.0.0`. The old Skill is not deleted; it's preserved at `~/cee/skills/<slug>-v1/SKILL.md`.
- Runs that referenced an older version continue to work via `bible_snapshot` semantics — the Run uses the version that was current at Run time.
### 5.7 The shipped Skill catalog
CEE ships with a starter set in `~/cee/.template/skills/`. These cover common reusable instructions so most Runs reuse rather than generate. Recommended initial catalog:
<table header-row="true">
<tr>
<td>Slug</td>
<td>Description (short)</td>
<td>task_types_supported</td>
</tr>
<tr>
<td>`read-codebase`</td>
<td>Walk a project, identify entry points, key modules, and architecture.</td>
<td>BUILD, ANALYZE, DEBUG</td>
</tr>
<tr>
<td>`match-existing-style`</td>
<td>Match the codebase's existing patterns before introducing new ones.</td>
<td>BUILD, TRANSFORM</td>
</tr>
<tr>
<td>`write-tests-pgtap`</td>
<td>Write database tests in pgTAP.</td>
<td>BUILD, DEBUG</td>
</tr>
<tr>
<td>`write-rls-policies`</td>
<td>Generate Supabase RLS policies for a table.</td>
<td>BUILD</td>
</tr>
<tr>
<td>`next-app-router-page`</td>
<td>Scaffold a Next.js App Router page with the project's conventions.</td>
<td>BUILD</td>
</tr>
<tr>
<td>`analyze-utility-bill`</td>
<td>Extract structured data from a utility bill PDF.</td>
<td>ANALYZE, TRANSFORM</td>
</tr>
<tr>
<td>`refactor-typescript`</td>
<td>Methodical TypeScript refactor with type-safety checkpoints.</td>
<td>TRANSFORM</td>
</tr>
<tr>
<td>`editorial-letter-nonfiction`</td>
<td>Produce a developmental editorial letter for a nonfiction manuscript.</td>
<td>WRITE, ANALYZE</td>
</tr>
<tr>
<td>`cold-email-investor`</td>
<td>Draft a personalized investor outreach email.</td>
<td>WRITE</td>
</tr>
<tr>
<td>`decision-with-tradeoffs`</td>
<td>Recommendation format with rationale, tradeoffs, and what would change the answer.</td>
<td>DECIDE</td>
</tr>
<tr>
<td>`pre-commit-review`</td>
<td>Review staged changes before commit; flag issues.</td>
<td>DEBUG</td>
</tr>
<tr>
<td>`summarize-legal-doc`</td>
<td>Extract parties, obligations, dates, and risk flags from legal text.</td>
<td>ANALYZE</td>
</tr>
</table>
This is illustrative. The catalog grows as CEE is used. A Skill that's generated, used, and approved becomes part of the catalog over time.
### 5.8 The "duplicate detection" pass
Before generating, the generator runs a duplicate detection check beyond the standard matcher:
1. Hash the proposed `description` and `triggers`.
2. Search the registry for fuzzy matches on the hash space.
3. If a near-duplicate is found (Levenshtein distance below threshold on description, or any trigger match), halt and ask OPERATOR: reuse, fork, or proceed with generation?
This is a guard against over-generation. The default answer is "reuse with description tweak" rather than "generate near-duplicate."
---
## 6. Data / Inputs Needed
### 6.1 Required inputs to `SKILL_ENGINE`
- `IntentObject` (for capability extraction)
- `Classification` (for task_type filtering)
- `AgentPlan` (for posture hints)
- Skill registry (`~/cee/skills/index.json`)
### 6.2 Required inputs for Skill generation
- `~/cee/prompts/skill_generator_system.txt` — fixed system prompt
- `~/cee/schemas/skill_frontmatter.json` — schema for validation
- Slug-naming convention (kebab-case, derived from capability + distinguisher)
### 6.3 Configuration
- `~/.cee/config.toml` `[skill_engine]` section:
	- `reuse_threshold` (default 0.85)
	- `ask_threshold` (default 0.60)
	- `duplicate_levenshtein_threshold` (default 0.10)
	- `min_reuse_count_for_promotion_priority` (default 3 — Skills used 3+ times jump the promotion queue)
---
## 7. Outputs Produced
### 7.1 The `SkillSet` artifact
JSON object listing referenced Skills:
```json
{
  "skills": [
    {"slug": "read-codebase", "version": "1.2.0", "path": "~/cee/skills/read-codebase/SKILL.md"},
    {"slug": "write-tests-pgtap", "version": "1.0.0", "path": "~/cee/skills/write-tests-pgtap/SKILL.md"}
  ],
  "newly_generated": [],
  "produced_by": "SKILL_ENGINE"
}
```
When new Skills are generated, they appear in both `skills` (referenced by the FinalPrompt) and `newly_generated` (for promotion queue tracking).
### 7.2 Generated Skill files (when applicable)
New `~/cee/skills/<slug>/SKILL.md`. Mirror to Obsidian. Promotion candidate.
### 7.3 Audit log entries
Every match (reuse, ask, generate) logged with capability, score, decision.
---
## 8. Agent + Skill Implications
### 8.1 The Skill engine is invoked after agent selection
Agents inform Skill matching via `posture_hints` and the agent's declared capabilities. A `critic` agent will pull different Skills than a `primary` agent for the same `task_type`.
### 8.2 Skills can be agent-agnostic or posture-specific
Most Skills are agent-agnostic (e.g., `read-codebase` works with any primary). Some are posture-specific (e.g., `pre-commit-review` is naturally a critic Skill). The frontmatter's `posture_hints` makes this explicit but not enforced — a primary can still use a critic-hinted Skill if it makes sense.
### 8.3 Skills don't trigger agent re-selection
Once `AGENT_SELECTOR` has produced an `AgentPlan`, Skill resolution doesn't change it. If the Skill engine discovers it really needs a domain specialist that wasn't selected, it raises a halt — the pipeline doesn't silently re-route.
---
## 9. Edge Cases
**EC1 — Two Skills both match a capability with score \> reuse_threshold.**
Pick higher score. Tie → more recent `version`. Tie → earlier `created_at`. Final → alphabetical.
**EC2 — A required capability has no matching Skill at any score.**
Generate. This is the expected case for novel work.
**EC3 — Generated Skill description is identical to an existing Skill.**
Hash collision detection catches before write. Halt with `skill_duplicate`.
**EC4 — A Skill's ****`task_types_supported`**** doesn't include the current ****`task_type`**** but its description otherwise matches.**
Strict filter — Skill not selected. If frequent, OPERATOR can edit the Skill to add the task_type.
**EC5 — User pastes a previous Run's ****`FinalPrompt`**** and asks for "the same thing but for a different domain."**
Interpreter detects the pattern; `SKILL_ENGINE` reuses the same Skills as the original Run if the new IntentObject still matches them.
**EC6 — A Skill is referenced in a Run but the file is missing at execution time.**
Run uses `bible_snapshot/skills/` — Skills are also snapshotted at Run start. Replay reads from snapshot.
**EC7 — A Skill's body references a deprecated Claude Code tool.**
Skill body is updated; version bumped. Old version preserved.
**EC8 — User wants to disable a Skill without deleting it.**
Add `disabled: true` to frontmatter. Registry skips disabled Skills. Old Runs continue working via snapshots.
**EC9 — Two simultaneous Runs both want to generate the same new Skill.**
Filesystem lock on the slug prevents simultaneous writes. Second Run waits, then sees the new Skill on registry rebuild and reuses.
**EC10 — Skill is generated, used, then OPERATOR rejects in promotion review.**
Skill stays usable. Rejection only blocks bible canon. OPERATOR can still delete manually if desired.
**EC11 — Generated Skill description leaks user-specific content (e.g., a client name).**
`SAFETY_GATE` runs on the FinalPrompt but not on Skill descriptions. The generator's system prompt includes "do not include client-specific details in descriptions; describe the capability generically." If it leaks anyway, OPERATOR catches in promotion review.
**EC12 — A Skill has ****`triggers`**** so generic that it matches almost everything.**
This is a quality bug. The matcher's scoring should down-weight overly-generic descriptions. Audit detects via "this Skill was matched 50% of recent Runs" — any single Skill matching that often is suspicious.
---
## 10. Failure Modes
### 10.1 Generation produces invalid frontmatter
**Failure:** generator emits YAML that doesn't validate.
**Detection:** schema validator at write time.
**Recovery:** retry up to 2x with stricter prompt; halt on third failure with `skill_generation_failed`.
### 10.2 Skill conflict (slug collision with different signature)
**Failure:** new Skill has same slug as existing but different `inputs`/`outputs`.
**Detection:** generator's collision check.
**Recovery:** halt with `skill_conflict`; OPERATOR must rename or version manually.
### 10.3 Capability extraction misses needs
**Failure:** Run completes but the FinalPrompt is missing a Skill that should have been referenced; user finds the executor underperforms.
**Detection:** user feedback; in Phase 2, output validator can flag missing capabilities.
**Recovery:** capability extraction logic improved; tests added against the failing Run.
### 10.4 Reuse threshold too high (over-generation)
**Failure:** thresholds let near-duplicates slip through; Skill catalog bloats.
**Detection:** OPERATOR review during promotion finds many near-duplicates.
**Recovery:** thresholds tuned downward; existing near-duplicates merged into versioned Skills.
### 10.5 Reuse threshold too low (under-generation)
**Failure:** matcher reuses a Skill that doesn't actually fit; output quality drops.
**Detection:** user feedback; failing golden Runs.
**Recovery:** thresholds tuned upward; Skill descriptions improved for accuracy.
### 10.6 Stale Skills used in modern Runs
**Failure:** an old Skill assumes deprecated tools or out-of-date conventions.
**Detection:** boot flags Skills whose `version` is below current schema; user feedback.
**Recovery:** Skill versioned up; old version preserved.
### 10.7 Promotion queue stalls
**Failure:** Notion is offline; queue grows unbounded.
**Detection:** queue length monitoring (warn at 50).
**Recovery:** queue capped at 500; manual `cee promote --flush` clears.
### 10.8 Generated Skill body fails Claude Code's loader
**Failure:** body has formatting issues that Claude Code rejects.
**Detection:** user reports executor errors; Phase 2 catches via dry-run load.
**Recovery:** generator's prompt updated; old generated Skills audited.
### 10.9 Two Skills cover the same capability with different approaches
**Failure:** both match equally; selector picks one but the other was better for this Run.
**Detection:** user feedback.
**Recovery:** OPERATOR merges Skills, picks a canonical approach, or splits by sub-capability.
### 10.10 The "everything is a Skill" anti-pattern
**Failure (procedural):** OPERATOR or system generates Skills for every minor variation; reuse signal degrades.
**Detection:** Skill count growth rate; promotion review finds many one-off Skills.
**Recovery:** Rule 5 enforcement tightened. The bar is "reusable on at least 3 future Runs." OPERATOR's promotion gate is the enforcement point.
---
## 11. Build Notes for Claude Code
- **Engine location:** `~/cee/skill_engine/engine.py`. Public function: `resolve(intent_object, classification, agent_plan) -> SkillSet`.
- **Matcher:** `~/cee/skill_engine/resolver.py`. Pure function: `top_match(candidates, capability, intent_object) -> (skill, score)`.
- **Generator:** `~/cee/skill_engine/generator.py`. Public function: `generate(capability, intent_object, classification) -> Skill`.
- **Registry:** `~/cee/skill_engine/registry.py`. Public function: `rebuild() -> SkillIndex`. Called by boot.
- **Canonicalizer:** `~/cee/skill_engine/canonicalizer.py`. Maps capability phrases to canonical forms.
- **Duplicate detector:** `~/cee/skill_engine/duplicate_check.py`. Hash-based fuzzy match before generation.
- **Body validator:** `~/cee/skill_engine/body_validator.py`. Checks generated bodies for Claude Code [SKILL.md](http://SKILL.md) compliance.
- **Tests:** `~/cee/tests/unit/test_skill_engine/` covers match scoring, generation triggers, conflict detection, versioning. Golden Runs exercise full path.
- **Promotion API:** `~/cee/skill_engine/promotion.py` has `queue(skill)`, `drain()`, `mark_approved(slug)`, `mark_rejected(slug)`. Called by writer modules.
- **Skill loading by Claude Code:** ensure the skills directory matches what Claude Code expects. If Claude Code expects `~/.claude/skills/` instead of `~/cee/skills/`, add a symlink at `cee init` time. The path constants in `~/cee/paths.py` are the single source of truth.
---
## 12. Definition of Done
This page is complete — and the Skill system is unblocked for build — when:
- [ ] `~/cee/schemas/skill_frontmatter.json` matches §5.1.1.
- [ ] `~/cee/.template/skills/` ships with the catalog in §5.7.
- [ ] `SKILL_ENGINE.resolve()` deterministically matches every Run's required capabilities.
- [ ] Generation works for at least one previously-uncovered capability and produces a valid [SKILL.md](http://SKILL.md).
- [ ] Duplicate detection catches near-duplicates before generation.
- [ ] Versioning preserves old Skills when bumping major versions.
- [ ] Promotion cycle: generate → queue → Notion → approve/reject works end-to-end.
- [ ] Boot rebuilds registry from filesystem walk, no incremental state.
- [ ] All edge cases in §9 are tested or documented.
- [ ] Failure modes in §10 each have a corresponding test in section 18.
---
## 13. Final Statement
Skills are CEE's memory. The first Run that needs a capability pays the cost of generating it; every Run after pays nothing. The system grows more useful over time without growing more expensive to use. The user's accumulated knowledge becomes infrastructure — exactly the inversion the bible's Rule 5 demands: "Skills over repetition." This page is what makes that rule executable.
