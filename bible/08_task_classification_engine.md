---
notion_section: 08
notion_title: 08 — TASK CLASSIFICATION ENGINE
mirrored_at: 2026-04-30
---

# 08 — TASK CLASSIFICATION ENGINE
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the canonical definition of `task_type`, complexity scoring, and the flag set. Sections 00, 01, 03, 05, 06, and 07 all defer to this page for the closed enums. If this page changes, those sections must be checked for drift; the boot-time consistency check is what catches drift before a Run runs.
---
## 1. What This Is
The Task Classification Engine is the module `CLASSIFIER` in CEE. It takes an `IntentObject` and produces a `Classification` artifact containing:
- A `task_type` from a closed enum of 8 values
- A `complexity_tier` (LOW / MEDIUM / HIGH / EXTREME) backed by a 0–100 numeric `complexity_score`
- A four-component score breakdown showing how complexity was reached
- A four-flag set (`needs_grounding`, `sensitive_data`, `destructive_potential`, `requires_human_gate`)
This page defines:
- The complete `task_type` enum with disambiguation rules
- The complexity rubric: components, scoring weights, tier thresholds, hard caps
- The flag-setting rules: when each flag is true, what triggers it
- The classifier algorithm and its tie-break behavior
- The data the classifier needs and the audit trail it produces
This is the most consequential closed enum in the bible. Every downstream module branches on it.
---
## 2. Why This Matters
Without a deterministic classification engine:
- "Pick the right agent" is unanswerable, because the agent set depends on `task_type`.
- Complexity becomes vibes-based, leading to over-engineered LOW Runs and under-engineered EXTREME Runs.
- Safety flags are inconsistently set, so destructive Runs sometimes proceed without human review.
- The system can't be tested deterministically, because the same input yields different classifications across days.
The classifier is the deterministic gateway from "what the user wants" to "what CEE will do." Everything downstream of it is mechanical given its output. Get the classifier right, and the rest of the system has nothing to guess about.
---
## 3. Core Requirements
The classifier MUST:
1. Produce a `Classification` artifact validating against `~/cee/schemas/classification.json`.
2. Assign exactly one `task_type` from the closed enum in §5.1.
3. Score complexity against the four-component rubric in §5.2 and assign a tier per §5.3 thresholds.
4. Set each flag in §5.4 according to the trigger rules listed there. Flags are deterministic given the same `IntentObject`.
5. Use temperature 0 and a fixed system prompt at `~/cee/prompts/classifier_system.txt` for any internal Claude call.
6. Log a full breakdown of each classification decision (the four component scores, which `task_type` precedence rule fired, which flag triggers fired) to `~/cee/runs/<run_id>/classification.json`.
7. Detect ambiguous classifications (two `task_type` candidates with similar confidence, or borderline complexity) and surface them.
The classifier MUST NOT:
- Invent a `task_type` outside the closed enum.
- Skip complexity scoring even on obviously simple inputs (LOW still has a score; it just lands at 0–24).
- Set a flag without a logged trigger.
- Use any non-deterministic mechanism — temperature must be 0, ordering of inputs must be stable.
- Re-classify mid-Run. Once `Classification` is written to `~/cee/runs/<run_id>/`, it is immutable for that Run.
---
## 4. System Rules
**Rule 1 — Closed ****`task_type`**** enum.**
The 8 values in §5.1 are exhaustive. Adding a new task_type requires a bible edit (this page) plus consistency updates in 00, 01, 03, 05, 06, 07.
**Rule 2 — One task_type per Run.**
Tasks that span multiple types are classified as `ORCHESTRATE` and decomposed by an orchestrator agent during execution. The classifier does not decompose; it labels.
**Rule 3 — Closed flag set.**
Four flags. Adding a fifth requires a bible edit and a schema migration.
**Rule 4 — Complexity is scored, not declared.**
Even if the user says "this is a simple task," the classifier computes the score against the rubric. User hints can influence component scores (e.g., explicit constraints reduce ambiguity) but don't bypass scoring.
**Rule 5 — Hard caps are non-negotiable.**
- LOW Runs: max 1 agent, regardless of input.
- EXTREME Runs: `requires_human_gate` is forced true, even if the trigger rules don't fire.
- Both caps are applied by the classifier itself, not by downstream modules.
**Rule 6 — Tier thresholds are inclusive on the lower bound.**
`score in [0, 25)` → LOW. `score in [25, 50)` → MEDIUM. `score in [50, 75)` → HIGH. `score in [75, 100]` → EXTREME. Boundary scores go to the higher tier.
**Rule 7 — Classifier escalates ambiguity.**
If two `task_type` candidates are within 0.10 confidence of each other, the classifier emits both candidates in `Classification.task_type_candidates` and halts the pipeline with `ambiguous_classification`. The OPERATOR picks.
**Rule 8 — Flags can compound.**
Multiple flags can be true simultaneously. Each is evaluated independently. The combined effect (multiple banners, multiple gates) is handled by `SAFETY_GATE`, not the classifier.
**Rule 9 — The classifier reads, never writes.**
The classifier reads `IntentObject`, the bible's section 08, and (optionally) recent classifications for pattern matching. It writes `Classification` and an audit log entry — nothing else.
**Rule 10 — Re-classification means a new Run.**
If OPERATOR believes a Run was misclassified, they re-run with corrections. The original Run's classification stays in its `~/cee/runs/<id>/` directory unchanged.
---
## 5. Detailed Workflow — The Classification Engine
### 5.1 The closed `task_type` enum
<table header-row="true">
<tr>
<td>Value</td>
<td>Definition</td>
<td>Output is</td>
</tr>
<tr>
<td>`BUILD`</td>
<td>Create a new artifact (code, file, system, configuration).</td>
<td>A new thing that didn't exist.</td>
</tr>
<tr>
<td>`ANALYZE`</td>
<td>Examine an existing artifact and produce structured findings.</td>
<td>A report or assessment.</td>
</tr>
<tr>
<td>`DEBUG`</td>
<td>Identify the cause of broken behavior and produce a fix.</td>
<td>A diagnosis + a corrected artifact.</td>
</tr>
<tr>
<td>`WRITE`</td>
<td>Produce prose deliverable (post, essay, doc, email, narrative).</td>
<td>A document.</td>
</tr>
<tr>
<td>`RESEARCH`</td>
<td>Gather sourced information on a topic and synthesize.</td>
<td>A sourced summary or briefing.</td>
</tr>
<tr>
<td>`TRANSFORM`</td>
<td>Convert input data from one shape to another (refactor, reformat, translate, restructure).</td>
<td>A transformed version of the input.</td>
</tr>
<tr>
<td>`DECIDE`</td>
<td>Produce a recommendation or stance with reasoning.</td>
<td>A recommendation + tradeoffs.</td>
</tr>
<tr>
<td>`ORCHESTRATE`</td>
<td>Coordinate multiple sub-tasks of varying types.</td>
<td>A coordinated set of outputs.</td>
</tr>
</table>
Each task_type has a precedence rule (used when input could fit multiple). Rules in §5.5.
### 5.1.1 Disambiguation between task types
These pairs cause the most miscategorization:
**`BUILD`**** vs. ****`TRANSFORM`****:**
- `BUILD`: deliverable did not exist before. Even if "based on" something, the output is net-new.
- `TRANSFORM`: deliverable is a reshaped version of the input. Same data, different form.
- Rule: if the input is being preserved as the basis for output (refactor, translate, reformat), it's TRANSFORM. If the input is just context/inspiration for something new, it's BUILD.
**`ANALYZE`**** vs. ****`RESEARCH`****:**
- `ANALYZE`: subject is something the user supplies (file, codebase, document).
- `RESEARCH`: subject requires gathering external information.
- Rule: if the user says "look at this and tell me X," it's ANALYZE. If "find out X about Y," it's RESEARCH.
**`ANALYZE`**** vs. ****`DECIDE`****:**
- `ANALYZE`: produces findings, not a recommendation.
- `DECIDE`: produces a recommendation, with reasoning visible.
- Rule: if the user wants "what's true," it's ANALYZE. If they want "what should I do," it's DECIDE.
**`DEBUG`**** vs. ****`BUILD`****:**
- `DEBUG`: existing artifact is broken; goal is fix.
- `BUILD`: building from scratch, possibly into existing context.
- Rule: if there's broken behavior to fix, it's DEBUG. If new functionality is being added, it's BUILD.
**`WRITE`**** vs. anything code-related:**
- `WRITE` is exclusively prose deliverables for human reading (essays, posts, emails, narratives, documentation as a deliverable).
- Code with comments is BUILD. README files as part of code repos are BUILD (the deliverable is the repo, the README is incidental).
**`ORCHESTRATE`**** vs. all others:**
- `ORCHESTRATE` is the catchall for genuinely multi-task work where decomposition is the point.
- Rule: if the work cannot be cleanly labeled as one of the other 7 types because it requires multiple of them as sub-tasks, it's ORCHESTRATE.
### 5.2 The complexity rubric
Complexity score is a 0–100 integer = sum of four components, each scored 0–25.
#### 5.2.1 Component A — Input ambiguity (0–25)
How clear is the goal from the input?
<table header-row="true">
<tr>
<td>Score</td>
<td>Description</td>
</tr>
<tr>
<td>0–5</td>
<td>Goal is fully specified; deliverable shape is explicit; constraints are listed.</td>
</tr>
<tr>
<td>6–10</td>
<td>Goal is clear; minor gaps the interpreter filled with safe assumptions.</td>
</tr>
<tr>
<td>11–15</td>
<td>Goal is clear in direction but specifics need inference; some assumptions were made.</td>
</tr>
<tr>
<td>16–20</td>
<td>Goal is partially specified; multiple assumptions required; user may need to clarify.</td>
</tr>
<tr>
<td>21–25</td>
<td>Goal is largely implicit; significant interpretation required to proceed.</td>
</tr>
</table>
Source: `IntentObject.ambiguity_score` mapped to the 0–25 range (multiply by 25, round). Plus +5 if `IntentObject.implicit_assumptions` count \> 3.
#### 5.2.2 Component B — Output structure complexity (0–25)
How structurally complex is the deliverable?
<table header-row="true">
<tr>
<td>Score</td>
<td>Description</td>
</tr>
<tr>
<td>0–5</td>
<td>Single sentence, single paragraph, or single small file.</td>
</tr>
<tr>
<td>6–10</td>
<td>Multi-paragraph prose, single file with structure (headers, sections), or simple JSON.</td>
</tr>
<tr>
<td>11–15</td>
<td>Multi-section document, multi-file output, or structured artifact with required schema.</td>
</tr>
<tr>
<td>16–20</td>
<td>Complex artifact: multi-file system, structured database schema, document with cross-references.</td>
</tr>
<tr>
<td>21–25</td>
<td>Highly structured deliverable with strict validation requirements (e.g., a working application, a manuscript).</td>
</tr>
</table>
Source: inferred from `IntentObject.deliverable` shape and `IntentObject.constraints`.
#### 5.2.3 Component C — Agent count required (0–25)
Mapped from posture set per §5.3:
<table header-row="true">
<tr>
<td>Agent count</td>
<td>Score</td>
</tr>
<tr>
<td>1 (primary only)</td>
<td>5</td>
</tr>
<tr>
<td>2 (primary + critic)</td>
<td>10</td>
</tr>
<tr>
<td>3 (primary + critic + optimizer)</td>
<td>15</td>
</tr>
<tr>
<td>4 (orchestrator + 3)</td>
<td>20</td>
</tr>
<tr>
<td>5+ (orchestrator + 3 + specialists)</td>
<td>25</td>
</tr>
</table>
#### 5.2.4 Component D — Skill count required (0–25)
Estimated from capability extraction in `SKILL_ENGINE`:
<table header-row="true">
<tr>
<td>Skill count</td>
<td>Score</td>
</tr>
<tr>
<td>0</td>
<td>0</td>
</tr>
<tr>
<td>1</td>
<td>5</td>
</tr>
<tr>
<td>2–3</td>
<td>10</td>
</tr>
<tr>
<td>4–5</td>
<td>15</td>
</tr>
<tr>
<td>6+</td>
<td>25</td>
</tr>
</table>
The classifier estimates Skill count *before* the Skill engine runs (since classification precedes Skill resolution in the pipeline). Estimation uses the same capability extraction logic as the Skill engine, but only counts; matching happens later.
### 5.3 Tier thresholds and hard caps
<table header-row="true">
<tr>
<td>Tier</td>
<td>Score range</td>
<td>Agent count</td>
<td>Skill count guideline</td>
<td>Strategy steps</td>
</tr>
<tr>
<td>LOW</td>
<td>0–24</td>
<td>1 (cap)</td>
<td>0–1</td>
<td>1</td>
</tr>
<tr>
<td>MEDIUM</td>
<td>25–49</td>
<td>1–2</td>
<td>1–3</td>
<td>2–3</td>
</tr>
<tr>
<td>HIGH</td>
<td>50–74</td>
<td>3</td>
<td>3–5</td>
<td>3–5</td>
</tr>
<tr>
<td>EXTREME</td>
<td>75–100</td>
<td>4+</td>
<td>3+</td>
<td>5+</td>
</tr>
</table>
**Hard caps applied by classifier:**
- If tier is LOW and components C or D would push agent/Skill count above the cap, the classifier flags `over_specified_for_tier` and either:
	- Reduces the score components to fit LOW (if components A and B are clearly LOW), or
	- Escalates the tier to MEDIUM (if components C or D are high enough that LOW genuinely doesn't fit).
- If tier is EXTREME, `requires_human_gate` is forced true regardless of trigger rules.
### 5.4 The flag set
Four flags. Each evaluated independently.
#### 5.4.1 `needs_grounding`
True when any of:
- `task_type` is `RESEARCH` (always grounded).
- `task_type` is `ANALYZE` and the analysis subject is a user-supplied document (input includes attachments).
- `IntentObject` mentions specific facts, numbers, names, or sources that the executor must respect (regex match on the goal: dates, proper nouns indicating sources, numbers).
- `IntentObject.implicit_assumptions` includes any assumption about specific factual content.
#### 5.4.2 `sensitive_data`
True when any of:
- The input matches any pattern in `~/.cee/redact_list`.
- Pattern-based detection finds: API key shapes (`sk-...`, `AKIA...`, JWT structures), email addresses, phone numbers, addresses with house numbers, credit card patterns, SSN patterns.
- `IntentObject.domain` is `personal` and the goal includes specific names (proper nouns).
- The user explicitly tagged the input with `--sensitive` flag.
#### 5.4.3 `destructive_potential`
True when any of:
- `task_type` is `BUILD`, `TRANSFORM`, or `DEBUG` and the goal involves modifying existing user files (regex: "delete", "remove", "drop", "truncate", "overwrite", "rewrite", "replace", followed by file/directory references).
- `task_type` is `ORCHESTRATE` and any sub-task would be destructive.
- The input mentions database schema changes, production deployments, or external API calls with side effects.
- The input includes destructive shell commands (regex: `rm -rf`, `DROP TABLE`, `TRUNCATE`, `git push --force`).
#### 5.4.4 `requires_human_gate`
True when any of:
- `complexity_tier` is `EXTREME` (forced).
- `destructive_potential` is true and the destruction is irreversible (delete-without-backup, force-push, prod database changes).
- The input affects external parties (email sends, payment processing, public posts).
- The OPERATOR has set a global rule in `~/.cee/config.toml` requiring a gate for certain task types or domains.
### 5.5 The classifier algorithm
`CLASSIFIER.run(intent_object) -> Classification`:
```javascript
def run(intent_object):
    # 1. Determine task_type via precedence rules
    candidates = []
    if matches_orchestrate_pattern(intent_object):
        candidates.append((ORCHESTRATE, confidence))
    if matches_debug_pattern(intent_object):
        candidates.append((DEBUG, confidence))
    if matches_research_pattern(intent_object):
        candidates.append((RESEARCH, confidence))
    if matches_decide_pattern(intent_object):
        candidates.append((DECIDE, confidence))
    if matches_transform_pattern(intent_object):
        candidates.append((TRANSFORM, confidence))
    if matches_analyze_pattern(intent_object):
        candidates.append((ANALYZE, confidence))
    if matches_write_pattern(intent_object):
        candidates.append((WRITE, confidence))
    if matches_build_pattern(intent_object):
        candidates.append((BUILD, confidence))
    
    candidates.sort(by=confidence, descending=True)
    
    if len(candidates) >= 2 and candidates[0].confidence - candidates[1].confidence < 0.10:
        # Ambiguous: halt and ask
        raise PipelineHalt("ambiguous_classification", {
            "candidates": candidates[:2]
        })
    
    task_type = candidates[0].value if candidates else BUILD  # default to BUILD if nothing matches
    
    # 2. Score complexity components
    component_a = score_input_ambiguity(intent_object)
    component_b = score_output_structure(intent_object)
    component_c = estimate_agent_count(task_type, component_a, component_b)
    component_d = estimate_skill_count(intent_object, task_type)
    
    raw_score = component_a + component_b + component_c + component_d
    
    # 3. Apply hard caps
    tier = tier_from_score(raw_score)
    if tier == LOW and (component_c > 5 or component_d > 5):
        # Real complexity is higher than LOW — escalate
        tier = MEDIUM
    
    # 4. Set flags
    flags = {
        "needs_grounding": evaluate_grounding(intent_object, task_type),
        "sensitive_data": evaluate_sensitive(intent_object),
        "destructive_potential": evaluate_destructive(intent_object, task_type),
        "requires_human_gate": evaluate_human_gate(intent_object, task_type, tier)
    }
    
    if tier == EXTREME:
        flags["requires_human_gate"] = True
    
    # 5. Build artifact
    return Classification(
        task_type=task_type,
        task_type_candidates=candidates,
        complexity_score=raw_score,
        complexity_tier=tier,
        complexity_components={
            "input_ambiguity": component_a,
            "output_structure": component_b,
            "agent_count_required": component_c,
            "skill_count_required": component_d
        },
        flags=flags,
        produced_by="CLASSIFIER"
    )
```
The pattern matchers (`matches_*_pattern`) use a combination of:
- Regex on `IntentObject.goal` and `IntentObject.deliverable`
- Verb-class lookup (build verbs: "create", "make", "implement"; analyze verbs: "examine", "review", "look at"; etc.)
- A single Claude call (temperature 0, fixed prompt) when regex/lookup is inconclusive
### 5.6 Precedence order
When multiple patterns match, precedence breaks ties:
1. `ORCHESTRATE` — if the input genuinely needs decomposition, this wins.
2. `DEBUG` — if there's broken behavior to fix.
3. `RESEARCH` — if external info gathering is required.
4. `DECIDE` — if a recommendation is the deliverable.
5. `TRANSFORM` — if the input is being reshaped.
6. `ANALYZE` — if the user-supplied input is being examined.
7. `WRITE` — prose deliverable for humans.
8. `BUILD` — default for "make something."
This precedence is the tiebreaker when patterns score equally. For genuinely ambiguous cases (confidence within 0.10), the classifier halts.
---
## 6. Data / Inputs Needed
### 6.1 Required inputs
- `IntentObject` (full)
- `~/cee/prompts/classifier_system.txt` — fixed system prompt for any internal Claude call
- `~/cee/schemas/classification.json` — output schema
- `~/.cee/redact_list` — for `sensitive_data` flag detection
### 6.2 Configuration
- `~/.cee/config.toml` `[classifier]` section:
	- `ambiguity_halt_delta` (default 0.10) — confidence delta below which two candidates trigger a halt
	- `human_gate_for_destructive_irreversible` (default true)
	- `human_gate_for_external_effects` (default true)
	- `low_tier_escalation_strict` (default true) — whether component C/D \> 5 escalates LOW to MEDIUM
### 6.3 Reference data
- The verb-class lookup at `~/cee/classifier/verb_classes.json` — maps verbs to task_type votes
- Pattern regex library at `~/cee/classifier/patterns.py`
---
## 7. Outputs Produced
### 7.1 The `Classification` artifact
```json
{
  "task_type": "BUILD",
  "task_type_candidates": [
    {"value": "BUILD", "confidence": 0.82},
    {"value": "TRANSFORM", "confidence": 0.34}
  ],
  "complexity_score": 42,
  "complexity_tier": "MEDIUM",
  "complexity_components": {
    "input_ambiguity": 8,
    "output_structure": 14,
    "agent_count_required": 10,
    "skill_count_required": 10
  },
  "flags": {
    "needs_grounding": false,
    "sensitive_data": false,
    "destructive_potential": false,
    "requires_human_gate": false
  },
  "audit": {
    "task_type_precedence_fired": "BUILD",
    "tier_escalation_applied": false,
    "extreme_human_gate_forced": false,
    "flag_triggers": {
      "needs_grounding": [],
      "sensitive_data": [],
      "destructive_potential": [],
      "requires_human_gate": []
    }
  },
  "produced_by": "CLASSIFIER"
}
```
### 7.2 Audit log entries
Every classification logged in `~/cee/audit/roles.log` with the four component scores, the precedence rule that fired, and any flag triggers.
---
## 8. Agent + Skill Implications
### 8.1 `task_type` directly determines the agent pool
`AGENT_SELECTOR` filters its registry by `task_types_supported`. The 8 task_types are the partition.
### 8.2 `complexity_tier` determines posture set
The posture-to-tier mapping in section 06 §5.1 is enforced by the classifier's hard caps. A LOW Run cannot have a critic, regardless of input.
### 8.3 Flags drive `SAFETY_GATE` and `<grounding_rules>`
- `needs_grounding` triggers the `<grounding_rules>` tag in the FinalPrompt (section 05 §5.2).
- `sensitive_data` triggers `SAFETY_GATE` redaction.
- `destructive_potential` triggers explicit OPERATOR confirmation.
- `requires_human_gate` adds the `<safety_banner>` tag to the FinalPrompt.
### 8.4 Skill count component is an estimate
The classifier estimates Skill count for component D, but the actual count is determined later by `SKILL_ENGINE`. Discrepancy is logged but doesn't trigger re-classification — the Run proceeds with the original tier. If discrepancies are frequent, the estimator gets tuned.
---
## 9. Edge Cases
**EC1 — Input matches no task_type pattern.**
Default to `BUILD` with low confidence. The complexity score will reflect the high `input_ambiguity` component, likely landing the Run in MEDIUM or HIGH and surfacing the issue to the user via assumptions visibility.
**EC2 — Input matches all 8 task_types weakly.**
Pick highest confidence; if all are below 0.30, halt with `ambiguous_classification` and return all candidates. This usually indicates the input is too vague for the interpreter.
**EC3 — User explicitly says "this is a simple task."**
The hint slightly reduces `input_ambiguity` component, but doesn't override scoring. If components C or D are high, the tier still escalates.
**EC4 — Input has contradictions.**
Already handled at interpreter level (`ambiguity_score` boost + halt). If the contradiction makes it to classifier, the contradicting passages create high `input_ambiguity` and pull the tier up. May still proceed with `<contradiction_note>` in the FinalPrompt.
**EC5 — Same input classified differently across Runs.**
Indicates non-determinism. Bug. Replay tests in section 18 must catch.
**EC6 — Borderline complexity score (e.g., 24).**
24 is LOW per Rule 6 (boundary goes to higher tier means scores ≥ 25 go to MEDIUM). The score is logged so OPERATOR can see how close it was.
**EC7 — ****`requires_human_gate`**** is true but user wants to bypass for a test.**
CLI flag `--bypass-gate` works only when also `--test-mode` is set. Otherwise rejected. Audit logs the bypass.
**EC8 — Multiple flags fire simultaneously.**
Each handled independently downstream. The FinalPrompt may have a `<safety_banner>`, `<grounding_rules>`, and a `[CONFIRM BEFORE EXECUTION]` marker all together. SAFETY_GATE handles composition.
**EC9 — Input is a paste of a previous FinalPrompt.**
Already detected by the interpreter (which halts and asks). Classifier never sees raw FinalPrompts.
**EC10 — Input is multilingual.**
Classifier reads the interpreter's normalized English version. Pattern matchers work on the normalized form. The `task_type` is language-agnostic.
**EC11 — Domain is ****`personal`**** and goal includes user's own life events.**
`sensitive_data` flag fires due to proper nouns + personal domain combination. SAFETY_GATE redacts names but preserves structure.
**EC12 — Estimation of Skill count is wildly off.**
Logged as `skill_count_estimation_error`. Doesn't trigger re-classification. Tuning data accumulates for the estimator.
---
## 10. Failure Modes
### 10.1 Ambiguity halt loop
**Failure:** User answers an ambiguity question; classifier still sees ambiguous candidates.
**Detection:** repeated `ambiguous_classification` halts on same Run.
**Recovery:** after 2 ambiguity halts, classifier picks the precedence-winning candidate and proceeds, flagging the choice in audit. OPERATOR can override.
### 10.2 Confidence drift
**Failure:** Same input scores different confidences across Runs.
**Detection:** golden Run replay tests.
**Recovery:** ensure temperature 0; fix non-determinism in pattern matching; classifier system prompt locked down.
### 10.3 Hard cap not applied
**Failure:** A LOW Run somehow reaches the agent selector with 3 agents requested.
**Detection:** AGENT_SELECTOR validates against tier; this is a backstop catch.
**Recovery:** classifier bug; tier escalation logic fixed.
### 10.4 Flag trigger missed
**Failure:** `sensitive_data` should have fired but didn't (e.g., a new key format not in the regex library).
**Detection:** OPERATOR finds sensitive content in a delivered FinalPrompt.
**Recovery:** add the pattern to the regex library; back-test against recent Runs to find other Runs that may have leaked.
### 10.5 Flag trigger spurious
**Failure:** `destructive_potential` fires for benign verbs (e.g., "remove a comment from the code").
**Detection:** OPERATOR sees confirmation prompts on obviously safe Runs.
**Recovery:** trigger refined; verb classes adjusted.
### 10.6 Tier escalation cascade
**Failure:** LOW always escalates to MEDIUM because Skill estimation is over-aggressive.
**Detection:** monitor LOW-tier Run rate; if dropping over time, investigate.
**Recovery:** tune Skill count estimator.
### 10.7 EXTREME human-gate forced spuriously
**Failure:** Routine MEDIUM tasks somehow score 75+ and get forced human gate.
**Detection:** OPERATOR friction; complaints about excessive gates.
**Recovery:** rubric weights re-tuned; component D estimator improved.
### 10.8 Pattern matcher false positive
**Failure:** A `WRITE` request matches the `BUILD` regex because of an incidental word.
**Detection:** misclassification reported; replay tests catch.
**Recovery:** regex tightened; verb class lookup adjusted.
### 10.9 Precedence drift
**Failure:** A change makes `RESEARCH` win over `DEBUG` when both match.
**Detection:** golden Run tests.
**Recovery:** precedence list in §5.6 is canonical; tests pin order.
### 10.10 Audit log incomplete
**Failure:** Classification artifact has `flags.sensitive_data: true` but no entry in `audit.flag_triggers.sensitive_data`.
**Detection:** schema asserts triggers list is non-empty when flag is true.
**Recovery:** classifier code fix; trigger logging is required wherever flags are set.
---
## 11. Build Notes for Claude Code
- **Classifier location:** `~/cee/classifier/classifier.py`. Public function: `run(intent_object) -> Classification`.
- **Pattern matchers:** `~/cee/classifier/patterns.py`. One function per task_type: `matches_<task_type>_pattern(intent_object) -> (bool, confidence)`.
- **Verb class lookup:** `~/cee/classifier/verb_classes.json`. Maps verb → list of (task_type, weight) pairs.
- **Component scorers:** `~/cee/classifier/scoring.py`. Four functions, one per component, each returning 0–25.
- **Tier mapper:** `~/cee/classifier/tiers.py`. Pure function from score to tier, plus the escalation logic.
- **Flag evaluators:** `~/cee/classifier/flags.py`. Four functions, one per flag, each returning (bool, list_of_triggers).
- **System prompt:** `~/cee/prompts/classifier_system.txt`. Used only when pattern matching is inconclusive. Locked down with examples for each task_type.
- **Schema:** `~/cee/schemas/classification.json`. Covers all fields including `audit` sub-object.
- **Tests:** `~/cee/tests/unit/test_classifier/` — one test per task_type for clean inputs, one per disambiguation pair for borderline inputs, one per flag trigger, one for hard cap escalation, one for ambiguity halt. Plus golden Runs in `~/cee/runs/golden/`.
- **Determinism check:** a CI test runs the same `IntentObject` through the classifier 10 times and asserts identical output.
- **Tuning interface:** `cee classifier-stats` reports recent classification distribution (task_type counts, tier counts, flag fire rates) so OPERATOR can spot drift.
---
## 12. Definition of Done
This page is complete — and the classifier is unblocked for build — when:
- [ ] The 8-value `task_type` enum in §5.1 is reflected verbatim in `~/cee/schemas/classification.json` and in every section that references it (00, 01, 03, 05, 06, 07).
- [ ] All four complexity components have their own scorer module.
- [ ] Tier escalation logic is implemented and tested.
- [ ] All four flags have their evaluator and the trigger list is logged on every flag fire.
- [ ] Pattern matchers exist for all 8 task_types.
- [ ] Precedence order in §5.6 is the only thing that breaks ties — no implicit ordering elsewhere.
- [ ] Determinism CI check passes.
- [ ] Each edge case in §9 has a corresponding test.
- [ ] Each failure mode in §10 has a corresponding test or documented recovery.
- [ ] Boot's cross-section consistency check verifies this page's enums match the schemas.
---
## 13. Final Statement
The classifier is the system's deterministic gateway. Everything downstream is mechanical given its output. The 8 task_types, the four-component complexity rubric, and the four-flag set are the spine of CEE — every other section in this bible defers to them. This page is the spine's definition. Drift here breaks everything; consistency here makes everything else inevitable.
