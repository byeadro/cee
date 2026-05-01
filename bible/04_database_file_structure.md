---
notion_section: 04
notion_title: 04 — DATABASE / FILE STRUCTURE
mirrored_at: 2026-04-30
---

# 04 — DATABASE / FILE STRUCTURE
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the complete on-disk and in-Notion layout for CEE. Every directory, every filename pattern, every schema location, every audit trail. If a path is referenced anywhere in this bible, it is defined here. Deviation from this layout breaks boot.
---
## 1. What This Is
CEE has no traditional database. State lives in three substrates:
- **Filesystem** at `~/cee/` (canonical)
- **Obsidian vault** at `~/SecondBrain/cee/` (mirror, human-readable)
- **Notion** (this bible plus promotion candidates, source of truth for spec-level canon)
This page is the path-level specification. It defines every directory, file naming convention, JSON/YAML schema location, log format, and substrate boundary. Sections 00, 02, 03 reference paths. This is where the paths *live*.
---
## 2. Why This Matters
A system distributed across three substrates can fail in three ways simultaneously. Path-level explicitness is what prevents:
- Filesystem and Obsidian drifting because nobody agreed where Run summaries live.
- Notion promotion candidates landing in the wrong section because the parent ID was implicit.
- Schema files getting orphaned because the directory boundary was assumed.
- A new module writing to a path no other module reads from.
Every path in this page is referenced by at least one module. Unreferenced paths are deprecated and removed.
---
## 3. Core Requirements
The structure MUST:
1. Have exactly one canonical location per artifact type.
2. Use deterministic naming (no random IDs without input-derivable components).
3. Survive backup-and-restore — every file is plain text, no opaque binaries.
4. Be walkable — `find ~/cee/` produces a complete inventory of state.
5. Map cleanly between substrates — every artifact in `~/cee/runs/<id>/` has a corresponding Obsidian note.
6. Separate user-editable config from system-managed state.
The structure MUST NOT:
- Use system-wide locations (`/etc/`, `/var/`). All state under `$HOME`.
- Mix substrates (no Notion data in filesystem, no filesystem state pushed to Notion outside the promotion path).
- Embed state in code (no Python modules with stateful globals).
- Use database engines (no SQLite, no Postgres). JSONL and JSON files only.
---
## 4. System Rules
**Rule 1 — Three substrates, three roots.**
- `~/cee/` — filesystem canon.
- `~/SecondBrain/cee/` — Obsidian mirror.
- Notion bible (existing pages 00–22) + a "Skill Promotions" section — Notion canon for spec.
**Rule 2 — Filesystem is canonical.**
If filesystem and another substrate disagree, filesystem wins for Run artifacts. Notion wins for bible content.
**Rule 3 — Naming conventions are enforced.**
- Run IDs: `<YYYYMMDD>_<HHMMSS>_<8-char-hash>`. Example: `20260430_141522_a3f8c2d1`.
- Skill slugs: `kebab-case`, ASCII only, max 60 chars.
- Agent slugs: same as Skill slugs.
- File extensions: `.json` for machine-read, `.md` for human-read, `.txt` for raw text, `.xml` for `FinalPrompt`, `.log` for append-only.
**Rule 4 — Atomic writes only.**
Every JSON/YAML write goes through write-temp + rename. No partial files visible to readers.
**Rule 5 — User config is separate from system state.**
- `~/.cee/config.toml` — user preferences.
- `~/.cee/redact_list` — user redaction patterns.
- Everything under `~/cee/` is system-managed; the user can read but generally should not hand-edit (Skill files and agent files being the exception).
**Rule 6 — Append-only logs.**
Logs in `~/cee/audit/` and `~/cee/runs/<id>/pipeline.log` are append-only, daily-rotated, never edited.
**Rule 7 — Bible mirror is read-only at the OS level.**
Files in `~/cee/bible/` are written by `cee sync-bible` and otherwise treated as read-only. Manual edits trigger a drift warning on next boot.
---
## 5. Detailed Workflow — Layout Reference
### 5.1 Filesystem layout (`~/cee/`)
```javascript
~/cee/
├── pipeline.py                    # the Run pipeline driver
├── replay.py                      # replay tool
├── cli.py                         # CLI entry point (`cee` command)
│
├── interpreter/                   # module: input → IntentObject
│   ├── __init__.py
│   └── interpreter.py
├── classifier/                    # module: IntentObject → Classification
│   ├── __init__.py
│   └── classifier.py
├── agent_selector/                # module: Classification → AgentPlan
│   ├── __init__.py
│   └── selector.py
├── skill_engine/                  # module: artifacts → SkillSet (+ new Skills)
│   ├── __init__.py
│   ├── engine.py
│   ├── generator.py               # generates new SKILL.md files
│   └── resolver.py                # matches required capabilities to existing
├── strategy_builder/              # module: artifacts → ExecutionStrategy
│   ├── __init__.py
│   └── builder.py
├── prompt_builder/                # module: artifacts → FinalPrompt
│   ├── __init__.py
│   └── builder.py
├── safety_gate/                   # module: redaction + gating
│   ├── __init__.py
│   ├── redactor.py
│   └── gates.py
├── persistence/                   # writer wrappers per substrate
│   ├── __init__.py
│   ├── filesystem_writer.py
│   ├── obsidian_writer.py
│   └── notion_writer.py
├── boot/                          # boot sequence implementation
│   ├── __init__.py
│   └── sequencer.py
├── roles/                         # role definitions per section 02
│   ├── __init__.py                # contains the RoleEnum
│   ├── operator.py
│   ├── interpreter.py
│   ├── classifier.py
│   └── ...
│
├── schemas/                       # JSON Schema / Pydantic model definitions
│   ├── raw_input.json
│   ├── intent_object.json
│   ├── classification.json
│   ├── agent_plan.json
│   ├── skill_set.json
│   ├── execution_strategy.json
│   ├── final_prompt.json
│   ├── clarification_request.json
│   ├── run_error.json
│   ├── run_summary.json
│   └── skill_frontmatter.json
│
├── bible/                         # mirror of Notion bible pages 00–22
│   ├── .sync_meta.json            # per-page sync metadata; schema in §5.5
│   ├── 00_project_vision.md
│   ├── 01_real_problem_breakdown.md
│   ├── 02_user_roles.md
│   ├── 03_full_system_workflow.md
│   ├── 04_database_file_structure.md
│   └── ... (all 23 pages)
│
├── prompts/                       # fixed system prompts for internal Claude calls
│   ├── interpreter_system.txt
│   ├── classifier_system.txt
│   ├── skill_generator_system.txt
│   └── agent_generator_system.txt
│
├── skills/                        # all SKILL.md files (Claude Code native format)
│   ├── index.json                 # auto-rebuilt registry; never hand-edit
│   └── <skill-slug>/
│       ├── SKILL.md               # YAML frontmatter + instructions
│       ├── examples.md            # optional
│       └── _meta.json             # provenance: which Run created this Skill
│
├── .claude/                       # Claude Code project root for execution
│   └── agents/
│       ├── index.json
│       └── <agent-slug>.md        # Claude Code subagent files
│
├── runs/                          # one directory per Run, append-only at Run level
│   ├── golden/                    # canonical test Runs
│   │   ├── low_clean/
│   │   ├── medium_clean/
│   │   ├── high_clean/
│   │   ├── extreme_clean/
│   │   ├── halt_clarification/
│   │   ├── halt_skill_conflict/
│   │   ├── resume_after_pause/
│   │   └── replay_from_step/
│   └── <run_id>/
│       ├── .lock                  # exists during in-progress Runs
│       ├── raw_input.json
│       ├── intent.json
│       ├── classification.json
│       ├── agents.json
│       ├── skills.json
│       ├── strategy.json
│       ├── prompt.xml
│       ├── safety_log.json
│       ├── summary.json
│       ├── pipeline.log           # JSONL of every step start/end/branch/halt
│       ├── clarification.json     # only if halted for clarification
│       ├── error.json             # only on failure
│       └── bible_snapshot/        # full copy of ~/cee/bible/ at Run start
│
├── audit/                         # append-only audit trail
│   ├── cli.log                    # every CLI command + timestamp + exit code
│   ├── roles.log                  # every role action
│   ├── boot.log                   # every boot + result
│   └── archive/                   # daily-rotated old logs
│
├── promotion_queue.json           # pending Notion promotions
└── tests/                         # pytest suite
    ├── unit/                      # per-module tests
    ├── integration/               # multi-module tests
    └── golden/                    # replay golden Runs and assert outputs
```
### 5.2 User config layout (`~/.cee/`)
Separated from system state because it is user-editable.
```javascript
~/.cee/
├── config.toml                    # user preferences
├── redact_list                    # newline-separated regex patterns for redaction
└── credentials.toml               # API keys (Phase 2); chmod 600
```
#### `config.toml` schema:
```toml
[general]
auto_sync = true                   # auto-sync bible from Notion on boot drift
fresh_boot = false                 # force full boot every Run

[paths]
cee_root = "~/cee"                 # override defaults if needed
obsidian_vault = "~/SecondBrain"
notion_bible_root_id = "352e8536-d882-8050-aff6-f1dbcff68a09"

[interpreter]
ambiguity_clarification_threshold = 0.6
ambiguity_visible_threshold = 0.3

[skill_engine]
reuse_threshold = 0.85
ask_threshold = 0.60

[executor]
default_target = "claude_code"     # or claude_ai, api

[phase2]
api_enabled = false
api_model = "claude-opus-4-7"
```
### 5.3 Obsidian mirror layout (`~/SecondBrain/cee/`)
```javascript
~/SecondBrain/cee/
├── README.md                      # explains the mirror and its purpose
├── runs/
│   ├── index.md                   # auto-generated dataview-style index
│   └── <run_id>.md                # one note per Run
├── skills/
│   ├── index.md
│   └── <skill-slug>.md            # human-readable view of each Skill
├── agents/
│   ├── index.md
│   └── <agent-slug>.md
├── bible/
│   └── <section-slug>.md          # mirror of bible sections, human-read
└── audit/
    └── <YYYY-MM-DD>.md            # daily audit summaries
```
Every Obsidian note has a frontmatter block:
```yaml
---
type: run | skill | agent | bible_section | audit
id: <run_id> | <slug> | <section_id>
created: <ISO timestamp>
canon_path: <absolute path in ~/cee/>
notion_url: <URL if applicable>
tags: [cee, <type>, ...]
---
```
The `canon_path` field is the back-pointer to filesystem canon. Obsidian is the explorer view; filesystem is the source.
### 5.4 Notion layout
The bible itself is the existing pages 00–22 under "system design bible." This page is one of those.
In addition, a "Skill Promotions" section (auto-created on first promotion if missing):
```javascript
system design bible/
├── 00 — PROJECT VISION
├── 01 — REAL PROBLEM BREAKDOWN
├── 02 — USER ROLES
├── ...
├── 22 — MASTER SYSTEM BUILD PROMPT
└── Skill Promotions/              # auto-managed
    ├── Pending/
    │   └── <skill-slug>           # candidate page for review
    ├── Approved/
    │   └── <skill-slug>           # promoted to canon
    └── Rejected/
        └── <skill-slug>           # archived
```
Each promotion candidate page contains:
- Skill name, slug, version
- Generated [SKILL.md](http://SKILL.md) content (verbatim)
- Provenance: which Run created it, the input that triggered generation
- Approve / Reject buttons (manual; `OPERATOR` moves the page)
CEE detects page moves between Pending/Approved/Rejected on next sync and updates `promotion_queue.json` accordingly.
### 5.5 Bible sync metadata (`.sync_meta.json`)
Per-page sync state for the bible mirror at `~/cee/bible/.sync_meta.json`. Read by `BOOT_SEQUENCER` at boot step B2 (per bible 00 §12) to detect drift between Notion canon and the local mirror.
```json
{
  "schema_version": "1.0.0",
  "produced_by": "BOOT_SEQUENCER",
  "last_synced": "2026-05-01T14:15:22Z",
  "pages": {
    "00_project_vision": {
      "notion_page_id": "<UUID of the Notion page>",
      "notion_last_edited_time": "2026-05-01T13:42:09Z",
      "local_path": "~/cee/bible/00_project_vision.md",
      "content_sha256": "<sha256 hex of local file at last sync>"
    },
    "...": "one entry per bible section, keyed by <NN>_<slug> matching the .md filename"
  }
}
```
Two drift checks are enabled by this file:
- **Notion-side drift:** `pages[X].notion_last_edited_time` is compared against the live Notion `last_edited_time` for that page. Mismatch triggers `cee sync-bible` if `auto_sync = true` (per §5.2), else halts (per bible 00 §12 B2).
- **Mirror-side drift:** `pages[X].content_sha256` is compared against the sha256 of the local mirror file. Mismatch indicates a manual edit to the mirror and triggers a drift warning per §4 Rule 7.
Written exclusively by `BOOT_SEQUENCER` via `cee sync-bible` (per bible 02 §7.13); bypasses `PERSISTENCE_WRITER`. The Pydantic model lives at `~/cee/schemas/sync_meta.py` per §6.1.
---
## 6. Data / Inputs Needed
### 6.1 Schemas (`~/cee/schemas/`)
Every artifact has a JSON Schema file. Pydantic models are generated from these. Authoritative list:
<table header-row="true">
<tr>
<td>Schema file</td>
<td>Defines</td>
</tr>
<tr>
<td>`raw_input.json`</td>
<td>`RawInput`</td>
</tr>
<tr>
<td>`intent_object.json`</td>
<td>`IntentObject`</td>
</tr>
<tr>
<td>`classification.json`</td>
<td>`Classification`</td>
</tr>
<tr>
<td>`agent_plan.json`</td>
<td>`AgentPlan`</td>
</tr>
<tr>
<td>`skill_set.json`</td>
<td>`SkillSet`</td>
</tr>
<tr>
<td>`execution_strategy.json`</td>
<td>`ExecutionStrategy`</td>
</tr>
<tr>
<td>`final_prompt.json`</td>
<td>XML structure of `FinalPrompt`</td>
</tr>
<tr>
<td>`clarification_request.json`</td>
<td>`ClarificationRequest`</td>
</tr>
<tr>
<td>`run_error.json`</td>
<td>`RunError`</td>
</tr>
<tr>
<td>`run_summary.json`</td>
<td>`RunSummary`</td>
</tr>
<tr>
<td>`skill_frontmatter.json`</td>
<td>YAML frontmatter for [SKILL.md](http://SKILL.md)</td>
</tr>
<tr>
<td>`agent_frontmatter.json`</td>
<td>YAML frontmatter for agent files</td>
</tr>
<tr>
<td>`sync_meta.json`</td>
<td>`SyncMeta`</td>
</tr>
</table>
Each schema is versioned (`$schema_version: "1.0.0"`). Schema changes require a migration script under `~/cee/schemas/migrations/`. Net-new schemas introduced at version 1.0.0 do not require a migration script; the `migrations/` directory exists for version bumps on existing schemas (e.g., 1.0.0 → 1.1.0).
### 6.2 Skill file format
Skills are native Claude Code [SKILL.md](http://SKILL.md) files. The frontmatter schema (defined in section 07) requires at minimum:
```yaml
---
name: <kebab-case-slug>
description: <one-paragraph natural-language description used for matching>
version: <semver>
triggers:
  - <natural-language trigger phrase>
inputs:
  - <expected input type>
outputs:
  - <produced output type>
created_by_run: <run_id>
created_at: <ISO timestamp>
---
```
The body is the Skill instructions, in Claude Code's native [SKILL.md](http://SKILL.md) prose format.
### 6.3 Agent file format
Agents are native Claude Code subagent files (`.claude/agents/<slug>.md`). Frontmatter (defined in section 06):
```yaml
---
name: <kebab-case-slug>
posture: primary | critic | optimizer | orchestrator | specialist
allowed_tools: [...]
capabilities: [...]
task_types_supported: [BUILD, DEBUG, ...]
created_by_run: <run_id> | manual
---
```
Body is the agent's system prompt in Claude Code's native subagent format.
### 6.4 Logs
All logs are JSONL (one JSON object per line). Log entry minimum fields:
```json
{"ts": "2026-04-30T14:15:22Z", "actor": "INTERPRETER", "event": "step_start", "run_id": "...", "details": {...}}
```
### 6.5 Registries
`index.json` files are flat arrays of objects, regenerated on boot from filesystem walk. Never hand-edit.
```json
[
  {"slug": "...", "path": "...", "version": "...", "frontmatter": {...}}
]
```
---
## 7. Outputs Produced
### 7.1 What boot writes
- `~/cee/skills/index.json` (rebuilt)
- `~/cee/.claude/agents/index.json` (rebuilt)
- `~/cee/audit/boot.log` (append)
- `~/cee/bible/.sync_meta.json` (updated if synced)
### 7.2 What a successful Run writes
- `~/cee/runs/<id>/` — full set of step artifacts.
- `~/SecondBrain/cee/runs/<id>.md` — Obsidian note.
- `~/cee/promotion_queue.json` — appended if new Skill/agent.
- `~/cee/audit/cli.log` — appended.
- `~/cee/audit/roles.log` — appended for every role action.
- `~/SecondBrain/cee/skills/<slug>.md` — created if new Skill.
- `~/cee/skills/<slug>/SKILL.md` — created if new Skill.
### 7.3 What promotion writes
- A page under `system design bible / Skill Promotions / Pending /` in Notion.
- An update to `~/cee/promotion_queue.json` marking the candidate `pending_review`.
### 7.4 What never gets written
- No filesystem changes outside `~/cee/`, `~/.cee/`, `~/SecondBrain/cee/`.
- No Notion writes outside the system design bible parent and its children.
- No state in environment variables.
- No state in stdout/stderr beyond what's intended for the user.
---
## 8. Agent + Skill Implications
### 8.1 Skills live in two places
- `~/cee/skills/<slug>/SKILL.md` — canonical, machine-loaded.
- `~/SecondBrain/cee/skills/<slug>.md` — Obsidian view, human-loaded.
These are linked by `canon_path` in the Obsidian frontmatter. A change in canonical Skill triggers an Obsidian update on next Run; the reverse is not true (Obsidian edits don't propagate back).
### 8.2 Agents live in three places
- `~/cee/.claude/agents/<slug>.md` — canonical, loaded by Claude Code at execution time.
- `~/SecondBrain/cee/agents/<slug>.md` — Obsidian view.
- Nowhere else. Agents do not appear in the Notion bible unless promoted (rare; agents are usually pre-built, not generated).
### 8.3 Why the split exists
Claude Code expects `.claude/agents/*.md` at the project root. CEE's project root is `~/cee/`. So agents live there. Skills are also Claude Code native, but Claude Code looks for them at `<project_root>/skills/` (or per Claude Code's documented convention) — CEE places them at `~/cee/skills/`.
If Claude Code's expected locations change, the only file that needs to update is the boot sequencer's path constants.
---
## 9. Edge Cases
**EC1 — ****`~/cee/`**** doesn't exist on first run.**
CLI's first action is to scaffold the full layout from a template in `~/cee/.template/` (committed in the repo). User confirms before scaffolding.
**EC2 — ****`~/SecondBrain/`**** doesn't exist.**
Obsidian writes are skipped with a warning; filesystem writes proceed. `OPERATOR` can later run `cee scaffold-obsidian` to backfill.
**EC3 — Disk full.**
Atomic write fails; Run halts at the failing step; nothing partial is left.
**EC4 — Permission error on ****`~/cee/`****.**
Boot halts with explicit chmod instructions.
**EC5 — Schema version mismatch.**
A Run loaded from `~/cee/runs/<id>/` has artifacts in old schema version. Replay runs migration scripts from `~/cee/schemas/migrations/` to bring them to current version. Original artifacts preserved alongside migrated ones (as `intent.json.v1`).
**EC6 — Two Skills with same slug.**
Filesystem prevents this (directory uniqueness). The Skill engine's conflict detection catches it earlier in the pipeline.
**EC7 — Run directory deleted while Run is in progress.**
Driver detects on next write attempt; halts with `persistence_failure`.
**EC8 — Bible mirror older than current Notion.**
Boot detects via `.sync_meta.json` comparison; auto-syncs if `auto_sync: true`, else halts.
**EC9 — Notion bible page deleted.**
Boot's bible mirror sync fails for that page; halts with explicit instruction to restore in Notion.
**EC10 — ****`redact_list`**** is empty or missing.**
Pattern-based redaction (regex for keys, tokens, emails) still runs. Empty list is allowed; missing file triggers a warning and the file is created empty.
**EC11 — Obsidian vault is on a different filesystem (network mount).**
Obsidian writes have a 5-second timeout. Failures are non-blocking. Logged.
**EC12 — ****`~/cee/runs/`**** grows unbounded.**
No automatic cleanup. `cee archive-runs --older-than 90d` moves old Runs to `~/cee/runs/archive/`. Manual command, `OPERATOR`-invoked.
---
## 10. Failure Modes
### 10.1 Layout drift
**Failure:** a module writes outside its declared path.
**Detection:** filesystem-level path check in writer wrappers; tests in section 18 enforce.
**Recovery:** code fix; misplaced file removed.
### 10.2 Index corruption
**Failure:** `~/cee/skills/index.json` or agents index is malformed.
**Detection:** boot's index rebuild detects; if rebuild itself fails, halt.
**Recovery:** delete the bad index and re-run boot.
### 10.3 Schema drift
**Failure:** an artifact is written with fields not in its schema.
**Detection:** Pydantic strict mode rejects extra fields.
**Recovery:** schema update + migration; or module fix.
### 10.4 Substrate desync
**Failure:** Obsidian or Notion mirrors fall out of sync with filesystem.
**Detection:** `cee verify` walks all three substrates and reports drift.
**Recovery:** `cee resync` rebuilds mirrors from filesystem canon.
### 10.5 Audit log loss
**Failure:** `audit/` directory deleted or rotated incorrectly.
**Detection:** boot checks for log files; missing files trigger warning.
**Recovery:** logs cannot be recovered; new logs start fresh. System function unaffected.
### 10.6 Promotion queue corruption
**Failure:** `promotion_queue.json` is malformed.
**Detection:** boot validation.
**Recovery:** queue is rebuilt by walking `~/cee/runs/` for unflagged-for-promotion Runs that should be queued. May lose tracking of in-flight Notion writes; `OPERATOR` reconciles by checking Notion's "Skill Promotions / Pending" manually.
### 10.7 User config error
**Failure:** `~/.cee/config.toml` has invalid TOML or unknown keys.
**Detection:** boot's TOML parser.
**Recovery:** halt with explicit error pointing at the bad line. Default config can be regenerated from `~/cee/.template/config.toml.default`.
### 10.8 Bible page renamed in Notion
**Failure:** `OPERATOR` renames "00 — PROJECT VISION" to something else; bible mirror sync fails to find it.
**Detection:** sync's section-by-section fetch.
**Recovery:** halt with explicit message. The bible mirror references pages by Notion ID, not title, so this should only fail if the page itself is deleted; renaming alone shouldn't break it. If it does, fall back to ID-based fetch.
### 10.9 Skill directory deleted by user
**Failure:** `OPERATOR` manually deletes `~/cee/skills/<slug>/`.
**Detection:** boot's index rebuild notices missing directory.
**Recovery:** index is rebuilt without the Skill. Any Run that referenced it via `bible_snapshot` can replay from snapshot.
### 10.10 Backup-restore mismatch
**Failure:** restored from backup; filesystem and Obsidian are at different timestamps.
**Detection:** `cee verify` reports drift.
**Recovery:** `cee resync` reconciles. If Obsidian is newer (because it was backed up later), no canonical loss; Obsidian is rebuilt from filesystem on next Run anyway.
---
## 11. Build Notes for Claude Code
- **Scaffolding script:** `cee init` creates the full `~/cee/` layout from the template at `~/cee/.template/`. The template ships with the repo.
- **Path constants:** all paths in code reference `~/cee/paths.py` — a single module exporting `Path` constants. No string concatenation of paths.
- **Atomic write helper:** `~/cee/persistence/atomic.py` exports `atomic_write_json(path, data)` and `atomic_write_text(path, text)`. Every write goes through these.
- **Index rebuild:** `~/cee/skill_engine/registry.py` and `~/cee/agent_selector/registry.py` each export `rebuild() -> Index`. Called by boot.
- **Bible sync:** `cee sync-bible` is implemented in `~/cee/boot/bible_sync.py`. Uses Notion MCP. Writes only to `~/cee/bible/` and `~/cee/bible/.sync_meta.json`.
- **Test fixtures:** `~/cee/tests/fixtures/` contains miniature versions of the layout for unit tests. Tests do not write to the real `~/cee/`.
- **Layout invariants:** a test in `~/cee/tests/unit/test_layout.py` walks `~/cee/` after a fresh boot and asserts every required directory exists and has expected permissions.
- **No global writes:** modules import path constants; they do not call `os.makedirs` outside `paths.py`.
- **Schema migrations:** every schema version bump requires a migration script. The schema version is in the file's `$schema_version` field; migrations chain `v1 → v2 → v3`.
- **Obsidian writer is idempotent:** running it twice produces the same output. Implementation hashes the rendered note and skips the write if the hash matches.
- **Notion writer respects rate limits:** built-in retry with exponential backoff. On persistent failure, queue retains the entry.
---
## 12. Definition of Done
This page is complete — and the layout is unblocked for build — when:
- [ ] `cee init` scaffolds the full layout described in §5.1, §5.2, §5.3.
- [ ] Every schema in §6.1 has a JSON Schema file at `~/cee/schemas/`.
- [ ] Every path in this document is referenced by exactly one module's path constant.
- [ ] `cee verify` walks all three substrates and reports drift.
- [ ] `cee resync` rebuilds mirrors from filesystem canon.
- [ ] Atomic write helpers are the only path to filesystem mutation.
- [ ] Index rebuilds work from filesystem walk alone (no incremental state).
- [ ] All edge cases in §9 have either a test or a documented manual recovery.
- [ ] No path outside `~/cee/`, `~/.cee/`, `~/SecondBrain/cee/`, and the Notion bible parent is touched by any module.
- [ ] Backup-and-restore round-trip preserves all canonical state.
---
## 13. Final Statement
CEE's "database" is its filesystem layout, mirrored to Obsidian for human inspection and to Notion for spec promotion. Every path in this page has a job; every job has exactly one path. The layout is the schema. Walk `~/cee/` and you have walked CEE's complete state.
