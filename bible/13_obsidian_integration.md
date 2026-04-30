---
notion_section: 13
notion_title: 13 — OBSIDIAN INTEGRATION
mirrored_at: 2026-04-30
---

# 13 — OBSIDIAN INTEGRATION
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the complete specification for how CEE writes to and (occasionally) reads from the Obsidian vault at `~/SecondBrain/cee/`. Section 04 defined the directory layout; section 02 defined `OBSIDIAN_WRITER` as a role; section 12 mandated redaction. This page is the implementation contract: the markdown formats, the linking conventions, the dataview-compatible structure, and the sync semantics.
---
## 1. What This Is
Obsidian is CEE's human-readable mirror layer. It is not canonical — filesystem (`~/cee/`) is. Obsidian's job is to make CEE's state walkable, searchable, and link-traversable by the OPERATOR using a familiar tool. Every Run, every Skill, every agent gets a corresponding markdown note with structured frontmatter, backlinks to other CEE entities, and human prose for the parts that benefit from prose.
This page defines:
- The Obsidian vault layout (already named in section 04; refined here)
- The note formats per entity type (run, skill, agent, bible_section, audit_summary)
- The frontmatter schemas for each note type
- The linking conventions (wiki-link patterns, tag patterns)
- The dataview-compatible index structure
- The sync semantics: when CEE writes, what it writes, what it never writes
- The OPERATOR usage patterns (what's done in Obsidian, what's done in CEE)
This page does not prescribe what plugins the OPERATOR uses; it prescribes what CEE produces so any compatible plugin (Dataview, Templater, Smart Connections) works against it.
---
## 2. Why This Matters
Without a defined Obsidian integration:
- Notes accumulate inconsistently — some have frontmatter, others don't.
- Links break because slug formats drift.
- The OPERATOR can't query "all Runs that used the `code-builder` agent" because the relationship isn't expressible.
- The sync direction is unclear, leading to manual edits getting overwritten or filesystem drift going unsurfaced.
Obsidian's value is amplified by structure. A pile of notes is worth less than a graph. CEE produces the graph by writing every note with consistent frontmatter, predictable links, and queryable tags. The OPERATOR then uses Obsidian's native tools (search, graph view, Dataview) on that structure.
---
## 3. Core Requirements
The Obsidian integration MUST:
1. Write every Run, every new Skill, every new agent, and bible mirror sections to the vault using the formats in §5.
2. Use Obsidian wiki-link syntax (`[[note-name]]`) for cross-references — never hard-coded paths.
3. Include frontmatter on every note matching the schema for the note type.
4. Tag notes with the conventions in §5.5 so OPERATOR can filter by Run state, complexity, agent, etc.
5. Apply redaction (per section 12) on every write; Obsidian sees redacted content only.
6. Produce idempotent writes — re-running the same write produces the same file.
7. Produce dataview-queryable indexes at `runs/index.md`, `skills/index.md`, `agents/index.md`.
8. Reference the canonical filesystem path in every note's frontmatter (`canon_path`) for backlinking.
The Obsidian integration MUST NOT:
- Write unredacted content under any circumstance.
- Treat Obsidian as a source of truth — manual edits to Obsidian notes do not propagate back to filesystem.
- Block the Run pipeline on Obsidian failures (Rule 9 of section 02).
- Create notes outside `~/SecondBrain/cee/`.
- Use plugin-specific syntax that breaks if the plugin isn't installed (Dataview queries are an exception — they're plain markdown when the plugin isn't loaded).
---
## 4. System Rules
**Rule 1 — Vault root is ****`~/SecondBrain/cee/`****.**
All CEE-owned notes live under this root. CEE never writes elsewhere in the vault. The OPERATOR can have other notes alongside; CEE doesn't touch them.
**Rule 2 — Filesystem is canonical; Obsidian is derived.**
Obsidian is rebuilt from filesystem on demand via `cee resync-obsidian`. Manual edits in Obsidian survive only if they don't conflict with regenerated content. CEE doesn't actively detect manual edits.
**Rule 3 — Write order is filesystem → Obsidian, always.**
A Run's filesystem artifacts are written first; Obsidian writes happen during Step 9 of the pipeline. Failures in Obsidian writing do not roll back filesystem writes.
**Rule 4 — Idempotent writes.**
Writing the same note twice produces the same file. Implementation: render the note, hash the rendered content, skip the write if the on-disk hash matches.
**Rule 5 — Closed note-type enum.**
Note types: `run`, `skill`, `agent`, `bible_section`, `audit_summary`, `index`. Adding a type requires a bible edit.
**Rule 6 — Wiki-links over hard paths.**
Cross-references between CEE notes use `[[<slug>]]` syntax. Obsidian resolves them. Hard paths (`~/cee/skills/foo/SKILL.md`) appear only in frontmatter `canon_path` field, never in note body.
**Rule 7 — Frontmatter is authoritative for queries.**
Dataview and other queries should rely on frontmatter, not body content. Frontmatter follows a fixed schema per note type.
**Rule 8 — Tags follow a hierarchical convention.**
`#cee/<note_type>`, `#cee/run/<state>`, `#cee/run/complexity/<tier>`, `#cee/skill/<task_type>`, etc. Hierarchy enables Obsidian's tag filtering.
**Rule 9 — Sync writes the minimum needed.**
A new Run produces 1–4 new notes (the Run note plus optional new Skill / new agent / promotion candidate notes). It does not rewrite indexes on every write — indexes regenerate on `cee resync-obsidian` or on a periodic background pass.
**Rule 10 — Failure is logged but non-fatal.**
An Obsidian write failure (permission, disk full, vault locked) is logged to `~/cee/audit/cli.log` with severity `warning`. The Run completes; OPERATOR can re-sync later.
---
## 5. Detailed Workflow — The Integration
### 5.1 Vault layout (refined from section 04 §5.3)
```javascript
~/SecondBrain/cee/
├── README.md                       # explains the mirror; frontmatter type=meta
├── runs/
│   ├── index.md                    # dataview index of all Runs
│   └── <run_id>.md                 # one note per Run
├── skills/
│   ├── index.md                    # dataview index of all Skills
│   └── <skill-slug>.md             # one note per Skill
├── agents/
│   ├── index.md                    # dataview index of all agents
│   └── <agent-slug>.md             # one note per agent
├── bible/
│   ├── index.md
│   └── <section-slug>.md           # mirror of bible sections
├── audit/
│   ├── index.md
│   └── <YYYY-MM-DD>.md             # daily audit summaries
└── _templates/                     # Obsidian Templater-compatible templates
    ├── run.md
    ├── skill.md
    ├── agent.md
    ├── bible_section.md
    └── audit_summary.md
```
The `_templates/` directory is for OPERATOR convenience if they use Templater; CEE writes notes by direct rendering (it does not invoke Templater). The templates in `_templates/` are kept in sync with CEE's rendering format so the OPERATOR can manually create equivalent notes.
### 5.2 The `run` note format
File: `~/SecondBrain/cee/runs/<run_id>.md`.
```markdown
---
type: run
id: <run_id>
created: <ISO timestamp>
canon_path: ~/cee/runs/<run_id>/
notion_url: <if applicable, e.g., promoted Skill candidate URL>
state: delivered | paused | failed | aborted
target_executor: claude_ai | claude_code | api
task_type: BUILD | ANALYZE | DEBUG | WRITE | RESEARCH | TRANSFORM | DECIDE | ORCHESTRATE
complexity_tier: LOW | MEDIUM | HIGH | EXTREME
complexity_score: <0-100>
agents_used: ["<slug>", ...]
skills_used: ["<slug>", ...]
flags:
  needs_grounding: <bool>
  sensitive_data: <bool>
  destructive_potential: <bool>
  requires_human_gate: <bool>
tags: [cee, run, run/<state>, run/complexity/<tier>, run/task/<task_type>]
---

# Run <run_id>

## Summary
<one-paragraph human-readable summary of the Run's input and output, redacted>

## Input (redacted)
> <redacted IntentObject.goal>

## Classification
- Task type: <task_type>
- Complexity: <tier> (score: <score>)
- Flags: <flag list with descriptions>

## Agents
- Primary: [[<primary_agent_slug>]]
- Critic: [[<critic_agent_slug>]] (if present)
- Optimizer: [[<optimizer_agent_slug>]] (if present)
- Specialists: [[<specialist_slug>]], ...

## Skills
- [[<skill_slug_1>]]
- [[<skill_slug_2>]]
...

## Execution Strategy
<rendered ExecutionStrategy steps as a numbered list, redacted>

## Output Format Declaration
- Type: <format_type>
- Acceptance criteria: <list>

## Grounding (if applicable)
- Allowed sources: <list>
- Citation requirement: <text>

## Safety Notes (if applicable)
- Destructive potential: <yes/no>; confirmed at <timestamp> if yes
- Sensitive data: <yes/no>; redactions count: <n>

## Verdict (Phase 2, if applicable)
- Format validation: <pass/soft_fail/hard_fail>
- Grounding validation: <pass/soft_fail/hard_fail>
- Quality score: <0-100>

## Linked
- [[bible/00 — PROJECT VISION]]
- Filesystem canon: `~/cee/runs/<run_id>/`
```
The `## Input (redacted)` section quotes the goal with redactions applied. The full `IntentObject` is not embedded; the OPERATOR follows `canon_path` for full detail.
### 5.3 The `skill` note format
File: `~/SecondBrain/cee/skills/<skill-slug>.md`.
```markdown
---
type: skill
slug: <slug>
version: <semver>
canon_path: ~/cee/skills/<slug>/SKILL.md
notion_url: <if promoted>
created_by_run: <run_id> | manual | seed
created_at: <ISO timestamp>
task_types_supported: [BUILD, ANALYZE, ...]
posture_hints: [primary, critic, ...]
domain: <if specified>
needs_review: <bool>
promotion_status: pending | approved | rejected | not_queued
usage_count: <int>  # how many Runs have referenced this Skill
last_used: <ISO timestamp>
tags: [cee, skill, skill/<task_type_1>, skill/<task_type_2>, skill/domain/<domain>]
---

# <Skill Slug>

## Description
<the description from frontmatter, restated for readability>

## When to Use
<paraphrased from triggers list>

## Inputs / Outputs
- Inputs: <list>
- Outputs: <list>

## Body Preview
<first 500 chars of the SKILL.md body, with a link to the full file at canon_path>

## Usage History
- Used by: [[run-<run_id_1>]], [[run-<run_id_2>]], ...
- Generated by: [[run-<originating_run_id>]]

## Linked
- Compatible agents: [[<agent_slug_1>]], [[<agent_slug_2>]]
```
The "Usage History" section is regenerated by `cee resync-obsidian` rather than updated incrementally — this avoids consistency bugs.
### 5.4 The `agent` note format
File: `~/SecondBrain/cee/agents/<agent-slug>.md`.
```markdown
---
type: agent
slug: <slug>
version: <semver>
canon_path: ~/cee/.claude/agents/<slug>.md
posture: primary | critic | optimizer | orchestrator | specialist
domain: <if specified>
task_types_supported: [...]
allowed_tools: [...]
created_by_run: <run_id> | manual | seed
created_at: <ISO timestamp>
needs_review: <bool>
usage_count: <int>
last_used: <ISO timestamp>
tags: [cee, agent, agent/posture/<posture>, agent/domain/<domain>, agent/task/<task_type_1>, ...]
---

# <Agent Slug>

## Posture
<posture> agent for <task_types_supported>.

## Description
<from frontmatter>

## Capabilities
<list from frontmatter>

## Body Preview
<first 500 chars of agent body>

## Usage History
- Used by: [[run-<run_id_1>]], ...
- Composed with: [[<other_agent_1>]], [[<other_agent_2>]]

## Linked
- Compatible Skills: [[<skill_1>]], [[<skill_2>]]
```
### 5.5 The `bible_section` note format
File: `~/SecondBrain/cee/bible/<section-slug>.md`.
```markdown
---
type: bible_section
section_number: <00-22>
section_slug: <slug>
canon_path: ~/cee/bible/<section_number>_<section_slug>.md
notion_url: <Notion page URL>
last_synced: <ISO timestamp>
tags: [cee, bible, bible/<section_number>]
---

# <Section Title>

<full content of the bible section, mirrored verbatim from filesystem>
```
These notes are large (full bible content). They are rewritten on every `cee sync-bible`. Manual edits to the body are overwritten on next sync; OPERATOR edits the bible in Notion.
### 5.6 The `audit_summary` note format
File: `~/SecondBrain/cee/audit/<YYYY-MM-DD>.md`.
```markdown
---
type: audit_summary
date: <YYYY-MM-DD>
runs_total: <int>
runs_delivered: <int>
runs_failed: <int>
runs_aborted: <int>
new_skills_generated: <int>
new_agents_generated: <int>
security_events: <int>
tags: [cee, audit, audit/<YYYY-MM>]
---

# Audit Summary <date>

## Runs
<list of [[run-<id>]] for each Run that day, with state>

## Skills Generated
<list of [[skill-<slug>]]>

## Agents Generated
<list of [[agent-<slug>]]>

## Security Events
<count and list of unacknowledged warnings>
```
Generated by a daily cron-style task or by `cee summarize-audit --date <date>`.
### 5.7 The `index` note format
Each `index.md` is a Dataview-compatible markdown file. Example for `runs/index.md`:
```markdown
---
type: index
indexes: run
generated: <ISO timestamp>
tags: [cee, index, index/runs]
---

# Runs Index

## Recent Runs (last 50)

```
TABLE
	task_type,
	complexity_tier,
	state,
	agents_used,
	created
FROM "cee/runs"
WHERE type = "run"
SORT created DESC
LIMIT 50
```javascript

## By State

### Delivered
```
LIST FROM "cee/runs" WHERE state = "delivered" SORT created DESC LIMIT 20
```javascript

### Failed / Aborted
```
LIST FROM "cee/runs" WHERE state IN ("failed", "aborted") SORT created DESC LIMIT 20
```javascript

## By Complexity

```
TABLE COUNT(rows) AS count FROM "cee/runs" WHERE type = "run" GROUP BY complexity_tier
```javascript

```
When Dataview isn't installed, the `dataview` code blocks render as plain code blocks — the note is still readable, just not queryable. Indexes for `skills/`, `agents/`, `audit/` follow analogous patterns.
### 5.8 Linking conventions
- **Run → Agent:** `[[<agent_slug>]]` (Obsidian resolves to the agent note, not the canonical agent file).
- **Run → Skill:** `[[<skill_slug>]]`.
- **Run → bible section:** `[[00 — PROJECT VISION]]` or `[[bible/00_project_vision]]` depending on which file naming Obsidian resolves.
- **Skill → Run that generated it:** `[[run-<run_id>]]`.
- **Agent → composed-with agents:** `[[<other_agent_slug>]]`.
To avoid slug collisions between Run notes and Skill notes (both using slug-based filenames), Run notes use the prefix `run-<run_id>` while Skill and agent notes use bare slugs. The link `[[run-<run_id>]]` is unambiguous.
### 5.9 Sync semantics
Three sync triggers:
**Per-Run write (during Step 9 of pipeline):**
- Always writes the Run note.
- Writes new Skill notes if the Run generated any.
- Writes new agent notes if the Run generated any.
- Does NOT regenerate indexes (avoid contention).
**Manual ****`cee resync-obsidian`****:**
- Walks `~/cee/` filesystem.
- Regenerates all notes from canonical state.
- Regenerates all indexes.
- Manual edits not in frontmatter are preserved if the rendering pipeline didn't change those sections; otherwise overwritten.
**Daily background sync (optional, configurable):**
- Runs index regeneration only.
- Updates Skill / agent `usage_count` and `last_used` by walking recent Runs.
- Generates the day's `audit_summary` note.
### 5.10 Idempotency mechanism
```python
def write_note(path: Path, content: str):
    if path.exists():
        existing_hash = sha256(path.read_bytes())
        new_hash = sha256(content.encode())
        if existing_hash == new_hash:
            return  # skip write
    
    atomic_write_text(path, content)
```
The hash check is fast and prevents Obsidian's "modified" indicator from firing on every Run.
---
## 6. Data / Inputs Needed
### 6.1 Required inputs to writing
- The artifact bundle from a Run (for run notes)
- New Skill / agent files (for skill / agent notes)
- The bible mirror (for bible_section notes)
- Audit logs (for audit_summary notes)
### 6.2 Configuration
- `~/.cee/config.toml` `[obsidian]` section:
	- `vault_root` (default `~/SecondBrain/cee/`)
	- `enable_daily_sync` (default false; OPERATOR can enable)
	- `regenerate_indexes_on_run` (default false; expensive)
	- `preserve_manual_edits` (default true; experimental)
### 6.3 OPERATOR-managed
- Plugin choices (Dataview, Templater, Smart Connections, etc.) — CEE doesn't manage but produces compatible content.
- Any non-CEE notes in the vault — CEE never touches.
---
## 7. Outputs Produced
### 7.1 Per Run
- `~/SecondBrain/cee/runs/<run_id>.md` — always.
- `~/SecondBrain/cee/skills/<slug>.md` — if new Skill generated.
- `~/SecondBrain/cee/agents/<slug>.md` — if new agent generated.
### 7.2 On `cee resync-obsidian`
- All notes regenerated.
- All indexes regenerated.
### 7.3 On daily background sync (when enabled)
- `~/SecondBrain/cee/audit/<YYYY-MM-DD>.md` — created.
- Indexes regenerated.
- Skill / agent `usage_count` updated.
---
## 8. Agent + Skill Implications
### 8.1 The OPERATOR can find related Skills/agents via Obsidian
The graph view in Obsidian shows Skill ↔ Run ↔ agent connections. Backlinks reveal "this Skill is used by Runs A, B, C." This is the primary OPERATOR usage pattern for understanding Skill reuse.
### 8.2 Skill / agent promotion candidates appear in Notion, not Obsidian
Obsidian mirrors filesystem; promotion is a Notion-specific concept. A Skill's Obsidian note shows `promotion_status` in frontmatter so OPERATOR can filter "all Skills with `promotion_status: pending`" via Dataview.
### 8.3 Bible sections are read-only in Obsidian
The mirror reflects what's in `~/cee/bible/`. OPERATOR edits the bible in Notion; sync brings it down to filesystem; Obsidian writer brings it to vault. Direct vault edits are overwritten on next sync.
---
## 9. Edge Cases
**EC1 — Vault doesn't exist on first Run.**
Obsidian writer logs a warning and skips. `cee scaffold-obsidian` creates the vault structure. Filesystem writes proceed.
**EC2 — Vault is on a network mount that's slow or unavailable.**
Writes have a 5-second timeout. Failures logged. Run completes.
**EC3 — OPERATOR has manually edited a Run note's body.**
On next `cee resync-obsidian`, the body is regenerated. OPERATOR's edits are lost unless `preserve_manual_edits` is true and edits don't conflict with regenerated content.
**EC4 — Slug collision between a Run note (****`run-...`****) and a Skill (****`...`****).**
Filename prefix prevents this — Run notes always start with `run-`, Skill / agent notes don't.
**EC5 — Obsidian's metadata cache is stale (frontmatter changed but cache outdated).**
CEE doesn't manage Obsidian's cache. OPERATOR can refresh manually. Future sync runs will produce up-to-date frontmatter regardless.
**EC6 — A note's content is too large for Obsidian's preview.**
Obsidian handles large notes. CEE doesn't truncate. The "Body Preview" sections in Skill / agent notes are summaries; the full body lives in `canon_path`.
**EC7 — User pastes an Obsidian internal link into the CEE input.**
Treated as data. The link doesn't auto-resolve at CEE time.
**EC8 — Bible section in Notion is renamed.**
Sync detects the change via Notion ID; the Obsidian filename is regenerated. Old Obsidian filename is left orphaned (OPERATOR can clean up via `cee resync-obsidian --prune`).
**EC9 — Vault is shared across machines (cloud sync).**
CEE writes are atomic so partial writes don't propagate. Idempotency check prevents re-writes from polluting sync history.
**EC10 — Vault has plugins that auto-modify frontmatter (e.g., a plugin adds last-modified timestamps).**
Plugin-added fields are preserved on re-write (CEE merges new frontmatter into existing rather than fully replacing). CEE-managed fields take precedence on conflict.
**EC11 — Wiki-link target doesn't exist (e.g., link to a Skill that was deleted).**
Obsidian shows the link as broken; CEE doesn't auto-clean. `cee resync-obsidian --prune` removes broken links.
**EC12 — Daily sync is enabled but takes too long (vault has 10K+ Runs).**
Background sync is incremental — it only regenerates indexes, not all notes. For large vaults, indexes are paginated.
---
## 10. Failure Modes
### 10.1 Write permission failure
**Failure:** vault directory not writable.
**Detection:** `OBSIDIAN_WRITER` write fails.
**Recovery:** logged; Run continues; OPERATOR fixes permissions.
### 10.2 Idempotency hash check breaks
**Failure:** hash check produces false equal (same hash, different content).
**Detection:** practically impossible (SHA-256 collision); not realistic.
**Recovery:** none needed.
### 10.3 Slug collision across note types
**Failure:** a Skill named `run-foo` collides with Run notes.
**Detection:** Skill registry validation rejects slugs starting with `run-`.
**Recovery:** Skill renamed; tests prevent regression.
### 10.4 Frontmatter schema drift
**Failure:** rendering produces frontmatter that doesn't match the documented schema.
**Detection:** golden tests against committed expected notes.
**Recovery:** rendering fixed; tests updated.
### 10.5 Wiki-link drift
**Failure:** rendering produces broken links because slug naming changed.
**Detection:** `cee verify --obsidian` walks notes and checks all wiki-links resolve.
**Recovery:** rendering fixed; bulk re-render triggered.
### 10.6 Index regeneration fails
**Failure:** Dataview query syntax is invalid.
**Detection:** Obsidian shows query error; OPERATOR reports.
**Recovery:** index template fixed; tests added.
### 10.7 Vault corrupted (e.g., partial writes from a crash)
**Failure:** notes are partial or unreadable.
**Detection:** OPERATOR notices; `cee verify --obsidian` reports.
**Recovery:** `cee resync-obsidian` rebuilds. Filesystem is canonical, so no data loss.
### 10.8 Manual-edit-preservation conflict
**Failure:** OPERATOR's manual edit and CEE's regenerated content can't coexist.
**Detection:** when `preserve_manual_edits` is true, conflicts are reported.
**Recovery:** OPERATOR resolves; CEE never silently drops their work.
### 10.9 Obsidian plugin breaks rendering
**Failure:** a plugin modifies frontmatter in a way CEE doesn't recognize.
**Detection:** sync rewrites incorrectly.
**Recovery:** CEE preserves unknown frontmatter fields on rewrite.
### 10.10 Vault path renamed by OPERATOR
**Failure:** OPERATOR moved the vault; `~/SecondBrain/cee/` no longer exists.
**Detection:** boot's vault check.
**Recovery:** OPERATOR updates `vault_root` in config; `cee scaffold-obsidian` creates structure at new path; manual migration of old notes if desired.
---
## 11. Build Notes for Claude Code
- **Writer location:** `~/cee/persistence/obsidian_writer.py`. Public entry: `write_run(run_id)`, `write_skill(slug)`, `write_agent(slug)`, `write_bible_section(section)`.
- **Renderer modules:** `~/cee/persistence/obsidian/renderers/` — one per note type (`run.py`, `skill.py`, etc.).
- **Frontmatter builder:** `~/cee/persistence/obsidian/frontmatter.py`. Pure function from artifact data to YAML frontmatter.
- **Wiki-link helper:** `~/cee/persistence/obsidian/links.py`. Builds `[[<slug>]]` strings; centralizes slug-to-link mapping.
- **Index generator:** `~/cee/persistence/obsidian/indexes.py`. Produces Dataview-compatible markdown.
- **Atomic write:** uses the same `atomic_write_text` helper from `~/cee/persistence/atomic.py`.
- **Idempotency check:** `~/cee/persistence/obsidian/idempotent.py`. Hash-and-skip helper.
- **`cee resync-obsidian`****:** implemented in `~/cee/cli.py`. Walks filesystem, regenerates everything.
- **`cee scaffold-obsidian`****:** creates vault structure if missing.
- **Tests:** unit tests per renderer (frontmatter + body) against golden notes. Integration tests for full vault state after a Run.
- **Section 12 redaction:** every renderer pulls from artifacts that have already been redacted by `SAFETY_GATE`. The renderer doesn't re-redact (defense in depth lives in the writer per section 12 §5.7), but it shouldn't introduce new sensitive content either.
---
## 12. Definition of Done
This page is complete — and the Obsidian integration is unblocked for build — when:
- [ ] The vault layout in §5.1 is created by `cee scaffold-obsidian`.
- [ ] One renderer per note type, producing correct frontmatter and body.
- [ ] Wiki-link resolution works across all note pairs (Run ↔ Skill, Run ↔ Agent, etc.).
- [ ] Indexes render correctly with Dataview installed AND degrade gracefully without it.
- [ ] Idempotent writes verified (hash check works).
- [ ] `cee resync-obsidian` regenerates the entire vault from filesystem.
- [ ] `cee verify --obsidian` checks vault integrity (links resolve, frontmatter schemas valid).
- [ ] Section 12 redaction is honored (all writes pass through redacted artifacts).
- [ ] Tag conventions in §4 Rule 8 are applied consistently across all note types.
- [ ] All edge cases in §9 have tests or documented recovery.
- [ ] Failure modes in §10 each have a corresponding test or documented recovery.
---
## 13. Final Statement
Obsidian is where CEE's history becomes readable. Every Run, every Skill, every agent is a markdown note with structured frontmatter, wiki-links to related entities, and tags for filtering. The OPERATOR opens the vault, looks at the graph, and sees how their work connects: which Runs used which Skills, which agents handled which task types, which Skills came out of which Runs. The pile becomes a graph; the graph becomes navigable; the navigation becomes insight. CEE produces the structure; Obsidian renders it.
