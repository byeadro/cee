---
notion_section: 03
notion_title: 03 — FULL SYSTEM WORKFLOW
mirrored_at: 2026-04-30
---

# 03 — FULL SYSTEM WORKFLOW
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the operational walkthrough of CEE end-to-end. Sections 00 and 01 define what CEE is and what it solves. Section 02 defines who acts. This page defines what happens, in what order, with what data flowing where. An engineer reading only this page should be able to trace any input through the system to its output, including every branch.
---
## 1. What This Is
A complete walkthrough of CEE as it runs. Three perspectives, in order:
1. **Lifecycle perspective** — from cold start to delivered prompt, all phases.
2. **Pipeline perspective** — the Run pipeline, step-by-step, with data contracts at every boundary.
3. **Branch perspective** — every decision point, every branch taken, every halt condition.
This page does not redefine modules, schemas, or roles — those live in 00, 01, 02, and the upcoming sections. It connects them into a single executable trace.
---
## 2. Why This Matters
Sections 00–02 establish vocabulary. This page establishes choreography. Without it:
- An engineer can build the modules but not know the order to call them in.
- A failure can be traced to a module but not to a step.
- A new feature has no obvious insertion point.
This page is the dance card. Every artifact, every module, every role lines up here in execution order.
---
## 3. Core Requirements
The workflow MUST:
1. Be linear at the top level — one Run, one path, no concurrent branches at the pipeline level (parallelism, if any, lives inside individual modules).
2. Define a clean contract at every step boundary — input artifact in, output artifact out, both schema-validated.
3. Have exactly one start (`OPERATOR` invokes `cee run`) and exactly one of three terminal states (`delivered`, `halted_for_clarification`, `halted_for_error`).
4. Be traceable — given a `run_id`, `cee replay <run_id>` reconstructs the exact path.
5. Be replayable — same input, same boot state ⇒ same path through the workflow.
The workflow MUST NOT:
- Have hidden steps that happen "automatically" without being named.
- Allow modules to call each other directly. Steps are sequenced by the pipeline driver, not by inter-module calls.
- Skip persistence on success paths. Every successful step writes its artifact before the next step starts.
---
## 4. System Rules
**Rule 1 — One pipeline driver.**
A single Python module, `~/cee/pipeline.py`, drives the Run. Modules don't invoke each other; the driver invokes them in order, passing artifacts.
**Rule 2 — Step boundaries are persistence boundaries.**
On success, every step writes its output artifact to `FILESYSTEM_CANON` before the next step starts. This means a Run halted between steps is partially recoverable — every completed step's artifact survives.
**Rule 3 — No silent branches.**
Every branch (e.g., "ambiguity_score \> 0.6 → halt for clarification") is logged with the deciding artifact value and the chosen path.
**Rule 4 — Halts are first-class.**
A halt for clarification is not a failure — it is an expected terminal state. The Run is paused, not failed. Resumption uses the same `run_id`.
**Rule 5 — Replay is deterministic.**
Replaying a Run with the same boot state produces byte-identical artifacts (for deterministic modules) or schema-identical artifacts (for modules with controlled non-determinism such as Skill generation). Drift is a bug.
**Rule 6 — Time stops at capture.**
The `RawInput.timestamp` is the only timestamp used for "now" in a Run. Modules don't read system time; they read this field. This makes replays stable across calendar time.
**Rule 7 — The pipeline driver is dumb.**
The driver's only logic is: invoke step, validate artifact, write artifact, invoke next step. It does not interpret artifacts. All decisions live in the modules.
---
## 5. Detailed Workflow
### 5.1 The three-phase lifecycle
CEE has three phases per session, even if the session contains many Runs:
1. **Cold start** — happens once per shell session. Boot sequence (section 00 §12).
2. **Run cycle** — repeats per `cee run` invocation. The pipeline of §5.2 below.
3. **Shutdown** — implicit. Filesystem state is canonical; nothing needs explicit teardown.
Cold start happens before the first Run of a session. Subsequent Runs in the same session can reuse loaded registries unless `--fresh-boot` is passed.
### 5.2 The Run pipeline (annotated)
This is the canonical Run trace. Every Run goes through this path or terminates explicitly inside it.
#### Step 1 — Capture
**Driver action:** read `OPERATOR` input from CLI argv, stdin, or `--input-file`.
**Artifact produced:** `RawInput` with `{text, timestamp, source, attachments[], target_executor}`.
**Validation:** non-empty `text`; `target_executor ∈ {claude_ai, claude_code, api}`; attachments exist on disk if specified.
**Persist:** `~/cee/runs/<run_id>/raw_input.json`.
**Branches:** none. If validation fails, halt with `InputValidationError`.
#### Step 2 — Interpretation
**Driver action:** invoke `INTERPRETER.run(RawInput)`.
**Module behavior:** loads bible §00, §01; loads recent Run logs for context; calls Claude (temperature 0, fixed system prompt at `~/cee/prompts/interpreter_system.txt`) to extract structured intent.
**Artifact produced:** `IntentObject` (schema in section 00 §5 Step 2).
**Validation:** schema-validate; `goal` non-empty; `ambiguity_score ∈ [0, 1]`.
**Persist:** `~/cee/runs/<run_id>/intent.json`.
**Branches:**
- `ambiguity_score > 0.6` → emit `ClarificationRequest`, **halt with ****`paused_for_clarification`**.
- `ambiguity_score ∈ [0.3, 0.6]` → continue, but flag `implicit_assumptions` for visible inclusion in `FinalPrompt`.
- `ambiguity_score < 0.3` → continue silently.
- Goal is detected as social pleasantry / non-actionable → **halt with ****`no_executable_intent`**.
#### Step 3 — Classification
**Driver action:** invoke `CLASSIFIER.run(IntentObject)`.
**Module behavior:** loads bible §08 (task taxonomy + complexity rubric); applies precedence rules from section 01 §8.2 to assign `task_type`; computes complexity score from four 0–25 components.
**Artifact produced:** `Classification`.
**Validation:** `task_type` in closed enum; `complexity_score ∈ [0, 100]`; complexity tier matches score range.
**Persist:** `~/cee/runs/<run_id>/classification.json`.
**Branches:**
- Two `task_type` candidates with similar confidence → emit ambiguity log; pick higher; if tie, **halt with ****`ambiguous_classification`** asking `OPERATOR` to choose.
- `complexity = EXTREME` and `flags.requires_human_gate = false` → driver overrides flag to `true` (rule from section 00 §8.3).
#### Step 4 — Agent Selection
**Driver action:** invoke `AGENT_SELECTOR.run(Classification)`.
**Module behavior:** loads agent registry; filters by `task_type` support; orders by `posture` match; selects N agents per complexity tier (1 / 1–2 / 3 / 4+).
**Artifact produced:** `AgentPlan` referencing agent file paths.
**Validation:** at least 1 agent selected; agent count within tier limits; all referenced files exist.
**Persist:** `~/cee/runs/<run_id>/agents.json`.
**Branches:**
- No matching agent for `task_type` → generate stub agent (`needs_review: true`), proceed.
- Two agents claim same `posture` slot (e.g., two primaries) → **halt with ****`agent_conflict`**.
#### Step 5 — Skill Resolution
**Driver action:** invoke `SKILL_ENGINE.run(IntentObject, Classification, AgentPlan)`.
**Module behavior:** identifies required capabilities from `IntentObject`; searches Skill registry by semantic match; reuses, asks, or generates per section 01 §8.4.
**Artifact produced:** `SkillSet` (list of Skill references) + zero or more new [SKILL.md](http://SKILL.md) files.
**Validation:** every referenced Skill resolves to an existing or newly-created file; new Skills have valid frontmatter; no name conflicts.
**Persist:** `~/cee/runs/<run_id>/skills.json`; new [SKILL.md](http://SKILL.md) files at `~/cee/skills/<slug>/SKILL.md`.
**Branches:**
- Match score in \[0.60, 0.85\] for any required capability → **halt with ****`skill_resolution_choice`** asking `OPERATOR` to pick reuse / modify / generate.
- New Skill name collides with existing different-signature Skill → **halt with ****`skill_conflict`**.
#### Step 6 — Execution Strategy
**Driver action:** invoke `STRATEGY_BUILDER.run(all_prior_artifacts)`.
**Module behavior:** constructs ordered step list; inserts validation checkpoints; defines stop conditions.
**Artifact produced:** `ExecutionStrategy` with `{steps[], checkpoints[], stop_conditions[], estimated_cost_tokens}`. The `estimated_cost_tokens` field is a non-negative integer estimate of total token budget across all steps; populated by `STRATEGY_BUILDER` from per-step heuristics. Used downstream by `PROMPT_BUILDER` for chunking decisions.
**Validation:** at least one step; checkpoints reference defined steps; stop conditions are evaluable; `estimated_cost_tokens ≥ 0`.
**Persist:** `~/cee/runs/<run_id>/strategy.json`.
**Branches:**
- LOW complexity → 1 step, no checkpoints.
- MEDIUM → 2–3 steps, optional checkpoint.
- HIGH → 3–5 steps, mandatory checkpoint after each.
- EXTREME → 5+ steps, checkpoints after each, mandatory rollback notes.
#### Step 7 — Prompt Generation
**Driver action:** invoke `PROMPT_BUILDER.run(all_prior_artifacts)`.
**Module behavior:** assembles XML-tagged prompt per the schema in section 00 §5 Step 7; inserts `<assumptions_made>` if `implicit_assumptions` non-empty; sets `<target_executor>`.
**Artifact produced:** `FinalPrompt` (XML block).
**Validation:** all required tags present; tag content schemas match; total length within `target_executor`'s context limit.
**Persist:** `~/cee/runs/<run_id>/prompt.xml`.
**Branches:**
- Length exceeds limit → invoke chunking; emit multi-part `FinalPrompt` with explicit ordering.
- Required tag missing → **halt with ****`prompt_schema_violation`**.
#### Step 8 — Safety Pass
**Driver action:** invoke `SAFETY_GATE.run(FinalPrompt, IntentObject.flags)`.
**Module behavior:** runs redaction if `flags.sensitive_data`; adds confirmation banner if `flags.requires_human_gate`; sets `[CONFIRM BEFORE EXECUTION]` if `flags.destructive_potential`.
**Artifact produced:** safety-annotated `FinalPrompt`; `safety_log` entry.
**Validation:** redaction patterns matched ≥ patterns in input (no missed redactions); banners present where flagged.
**Persist:** updated `~/cee/runs/<run_id>/prompt.xml`; `~/cee/runs/<run_id>/safety_log.json`.
**Branches:**
- `flags.destructive_potential = true` → driver pauses for `OPERATOR` confirmation; resumes after `cee confirm <run_id>`.
- `flags.requires_human_gate = true` → driver completes Run but emits `FinalPrompt` with banner.
#### Step 9 — Persistence (full)
**Driver action:** invoke `PERSISTENCE_WRITER.finalize(run_id)`, then `OBSIDIAN_WRITER.write_run(run_id)`, then `NOTION_WRITER.queue_promotions(run_id)`.
**Module behavior:** filesystem writes are already done step-by-step; finalize creates the Run summary file. Obsidian writes a single human-readable Run note. Notion queues any new Skills/agents for promotion.
**Artifact produced:** `~/cee/runs/<run_id>/summary.json`; `~/SecondBrain/cee/runs/<run_id>.md`; promotion queue entries.
**Validation:** summary references all step artifacts; Obsidian note links to summary.
**Persist:** the writes themselves are the persistence.
**Branches:**
- Filesystem write fails → **halt with ****`persistence_failure`**, Run marked failed.
- Obsidian write fails → log warning, continue.
- Notion write fails → queue, continue.
#### Step 10 — Deliver
**Driver action:** print `FinalPrompt` to stdout; print summary line listing agents, Skills, complexity, target executor; exit 0.
**Module behavior:** none — the `FinalPrompt` is already on disk.
**Artifact produced:** stdout output.
**Validation:** none.
**Persist:** none — already done.
**Branches:** none. Run is complete.
### 5.3 The clarification cycle
When a step halts with `paused_for_clarification` (or any of the named halt states that ask `OPERATOR` for input):
1. CEE writes a `ClarificationRequest` artifact to `~/cee/runs/<run_id>/clarification.json` and emits the questions to stdout.
2. The Run is in state `paused`. Filesystem keeps all artifacts written so far.
3. `OPERATOR` answers via `cee answer <run_id> "<answers>"` or via re-running `cee run <run_id> --resume "<answers>"`.
4. The pipeline driver re-enters at the step that halted, with the answers injected into the relevant artifact.
5. The Run continues from that step. Earlier artifacts are not recomputed unless `--reinterpret` is passed.
### 5.4 The replay cycle
`cee replay <run_id>` reconstructs a Run:
1. Reads all artifacts from `~/cee/runs/<run_id>/`.
2. Rebuilds the pipeline trace.
3. Either prints the trace (default) or re-executes from a specific step (`--from-step N`).
4. Re-execution writes to a *new* `run_id` derived from the original (`<run_id>_replay_<n>`), preserving the original Run.
Replay never modifies the original Run. Filesystem canon is append-only at the Run level.
### 5.5 The promotion cycle
Separate from the Run pipeline. Triggered by `cee promote <skill_slug>` or by Notion sync:
1. Reads candidate from `~/cee/promotion_queue.json`.
2. Writes a candidate page to Notion under "Skill Promotions".
3. Marks the queue entry as `pending_review`.
4. `OPERATOR` reviews in Notion; either approves (page moves to canon section of bible) or rejects (page archived).
5. CEE detects the move on next sync; updates `promotion_queue.json` accordingly.
This cycle is async to Runs. A Skill is fully usable in `FILESYSTEM_CANON` regardless of its promotion status.
---
## 6. Data / Inputs Needed
### 6.1 Per-Run inputs
- `RawInput.text` — required.
- `target_executor` — required, default `claude_ai`.
- Attachments — optional.
- `--resume <answers>` — for clarification cycle.
- `--from-step N` — for replay cycle.
### 6.2 Per-session inputs (boot)
See section 00 §12 (Boot Sequence). The pipeline relies on a clean boot.
### 6.3 Persistent inputs (filesystem)
- Bible mirror at `~/cee/bible/`.
- Skill registry at `~/cee/skills/index.json`.
- Agent registry at `~/cee/.claude/agents/index.json`.
- Schemas at `~/cee/schemas/`.
- Prior Runs at `~/cee/runs/`.
- Config at `~/.cee/config.toml`.
- Redact list at `~/.cee/redact_list`.
---
## 7. Outputs Produced
### 7.1 On successful Run
- `FinalPrompt` to stdout (the user-facing deliverable).
- All step artifacts on disk under `~/cee/runs/<run_id>/`.
- Run summary in Obsidian.
- Promotion queue entries (if applicable).
- Audit log entries.
### 7.2 On halted Run
- `ClarificationRequest` to stdout (or relevant halt-state artifact).
- All artifacts produced before the halt, on disk.
- Run state marked `paused` in summary.
- Clear instructions on how to resume.
### 7.3 On failed Run
- `RunError` artifact at `~/cee/runs/<run_id>/error.json` with `{failed_step, error_type, error_message, recovery_suggestion}`.
- All artifacts produced before the failure, on disk.
- Audit log entry.
- Non-zero exit code.
---
## 8. Agent + Skill Implications
The workflow exposes Skills and agents at exactly two points:
- Step 4 (Agent Selection) reads agent files; produces `AgentPlan`.
- Step 5 (Skill Resolution) reads/writes Skill files; produces `SkillSet`.
Outside these steps, the workflow is agent-agnostic and skill-agnostic. The `FinalPrompt` references them by file path; the executor loads them.
Implication: changes to Skill or agent formats only affect Steps 4 and 5 plus the executor adapter. Changes to the workflow itself do not require Skill or agent changes.
---
## 9. Edge Cases
**EC1 — ****`cee run`**** invoked with no input.**
CLI rejects before pipeline starts.
**EC2 — ****`cee run`**** invoked while a previous Run is paused.**
By default, refuse with "Run \<id\> is paused. Resume or abort first." `--force-new-run` overrides.
**EC3 — Multiple ****`cee run`**** invocations in parallel.**
Each gets its own `run_id` and its own subdirectory. Pipelines do not cross. Skill registry rebuilds are file-locked.
**EC4 — Step N succeeds, step N+1 fails.**
N's artifact is preserved. N+1's failure is logged. Replay can resume from N+1 with `--from-step N+1`.
**EC5 — Driver itself crashes mid-step.**
On next `cee run`, boot detects an in-progress Run (via `~/cee/runs/<run_id>/.lock` file), offers to resume or abandon.
**EC6 — ****`OPERATOR`**** resumes a paused Run after substantial time.**
Boot is full per section 00 §12. The bible may have changed; if so, the resumed Run uses the *original* bible state from `~/cee/runs/<run_id>/bible_snapshot/`. Bible drift across resume is logged but does not break the Run.
**EC7 — ****`target_executor`**** mismatch.**
`OPERATOR` paste of a `FinalPrompt` targeted at `claude_code` into `claude_ai` is detected by the executor banner. Workflow itself doesn't catch this — by design, post-delivery is `OPERATOR`'s domain.
**EC8 — A new Skill generated during Run is needed by a later step in the same Run.**
The Skill is committed to filesystem during Step 5. Step 7 (`PROMPT_BUILDER`) references it normally. The pipeline does not require a registry rebuild mid-Run.
**EC9 — Bible reload mid-Run.**
Forbidden. Bible state is captured at Step 0 of the Run and frozen for that Run's duration. Snapshot lives at `~/cee/runs/<run_id>/bible_snapshot/`.
**EC10 — Replay against a deleted Skill.**
The Run's `bible_snapshot/` is read; the Skill referenced in original `SkillSet` may be gone from current filesystem. Replay flags this and offers to regenerate from the snapshot.
---
## 10. Failure Modes
### 10.1 Step boundary corruption
**Failure:** an artifact is partially written (driver killed mid-write).
**Detection:** schema validation on next read. Atomic write via temp file + rename minimizes the window.
**Recovery:** Run is marked failed at the partial step; replay from N-1 succeeds.
### 10.2 Driver bug
**Failure:** driver invokes steps in wrong order or skips a step.
**Detection:** end-to-end golden Run tests in section 18.
**Recovery:** code fix; failed Runs replayed.
### 10.3 Module returns out-of-schema artifact
**Failure:** a module emits something the driver can't validate.
**Detection:** Pydantic validation at the driver level.
**Recovery:** Run fails with `schema_violation`; module bug logged.
### 10.4 Halt state ambiguity
**Failure:** a module signals halt but the driver doesn't recognize the halt type.
**Detection:** halt types are a closed enum (`paused_for_clarification | no_executable_intent | ambiguous_classification | agent_conflict | skill_resolution_choice | skill_conflict | prompt_schema_violation | persistence_failure`); unknown halts crash the driver.
**Recovery:** code fix; closed enum updated in lockstep with module behavior.
### 10.5 Resume corruption
**Failure:** `OPERATOR` resumes a Run with answers that don't match the question schema.
**Detection:** answer validator rejects.
**Recovery:** Run stays paused; new clarification request issued if needed.
### 10.6 Replay drift
**Failure:** replaying a Run produces artifacts that differ from the originals (beyond controlled non-determinism).
**Detection:** golden Run tests fail.
**Recovery:** drift is a bug; track to root module.
### 10.7 Concurrent write collision
**Failure:** two parallel Runs both try to generate the same Skill name.
**Detection:** filesystem lock on `~/cee/skills/<slug>/`.
**Recovery:** second Run waits, then either reuses the first's output (if signature matches) or halts with `skill_conflict`.
### 10.8 Disk full mid-step
**Failure:** filesystem write fails.
**Detection:** write returns error.
**Recovery:** Run halts; explicit error tells `OPERATOR` to free space; replay resumes.
### 10.9 Bible snapshot corruption
**Failure:** a Run's `bible_snapshot/` is unreadable.
**Detection:** boot read at resume time.
**Recovery:** Run cannot be resumed; can only be re-run from scratch with current bible.
### 10.10 The "happy path" everyone forgets to test
**Failure (procedural):** all tests target halts and errors; no test covers a clean LOW-complexity Run end-to-end.
**Detection:** test coverage review.
**Recovery:** section 18 must include at least one golden test per complexity tier on the success path.
---
## 11. Build Notes for Claude Code
- **Driver location:** `~/cee/pipeline.py`. Single function: `run_pipeline(raw_input: RawInput) -> RunResult`. Delegates to step functions in order.
- **Step functions:** each step is a function `step_N(...)` in `~/cee/pipeline.py` that invokes the relevant module and validates the artifact. The module itself does the work; the step function is the orchestration shim.
- **Halt mechanism:** modules raise `PipelineHalt(halt_type, payload)`. The driver catches and emits the appropriate artifact. No exceptions cross the driver boundary unanticipated.
- **Artifact write pattern:** every step writes via `write_artifact(run_id, step_name, artifact)` which atomic-writes to a temp file and renames. Schema validation happens before write.
- **Run ID generation:** `run_id = <timestamp>_<short_hash_of_input>`. Deterministic from input + time. Collisions resolved by appending `_<n>`.
- **Resume support:** the driver's first action on `cee run --resume <run_id>` is to load the existing Run directory and skip steps with completed artifacts.
- **Replay support:** `~/cee/replay.py` reads a Run directory, rebuilds the trace from artifacts, optionally re-executes from a step. Lives separately from the driver.
- **Bible snapshot:** at Step 0, copy `~/cee/bible/` to `~/cee/runs/<run_id>/bible_snapshot/`. Resume reads from this snapshot, not from current bible.
- **Tests:** section 18 must include golden Runs for: clean LOW, clean MEDIUM, clean HIGH, clean EXTREME, halt-for-clarification, halt-for-skill-conflict, resume-after-pause, replay-from-step.
- **Logging:** every step start, every artifact write, every halt, every branch taken — logged to `~/cee/runs/<run_id>/pipeline.log` in JSONL format.
---
## 12. Definition of Done
This page is complete — and the workflow is unblocked for build — when:
- [ ] `~/cee/pipeline.py` exists with a clean step function per Step 1–10.
- [ ] Every step has a schema-validated input and output artifact.
- [ ] Every halt type in §10.4 is implemented and reachable.
- [ ] The clarification cycle (§5.3) works end-to-end.
- [ ] The replay cycle (§5.4) works end-to-end.
- [ ] The promotion cycle (§5.5) works end-to-end.
- [ ] Bible snapshot is captured at Step 0 of every Run.
- [ ] Section 18 includes at least one golden test per complexity tier and per halt type.
- [ ] An end-to-end Run from CLI to delivered prompt completes in under a minute on a clean boot.
- [ ] Replay of any Run produces schema-equivalent artifacts.
---
## 13. Final Statement
The workflow is the system's choreography. Modules are dancers; the pipeline driver is the conductor. Sections 00–02 told you who's on stage; this page tells you how the dance goes. Every Run goes through it. Every Run ends in one of three explicit terminal states. There are no other paths.
