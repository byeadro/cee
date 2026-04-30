---
notion_section: 10
notion_title: 10 — OUTPUT FORMAT ENGINE
mirrored_at: 2026-04-30
---

# 10 — OUTPUT FORMAT ENGINE
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the system that decides what shape the executor's output should take, populates the `<output_format>` tag in the FinalPrompt, and (in Phase 2) validates the executor's actual output against that declared shape. Section 05 said `<output_format>` is required and must be specific. This page defines how specificity is achieved deterministically and how compliance is verified.
---
## 1. What This Is
The Output Format Engine is the subsystem responsible for:
1. **Inferring** the appropriate output format for a Run from `task_type`, `IntentObject.deliverable`, and any user-specified format hints.
2. **Rendering** that format as the `<output_format>` tag content in the FinalPrompt (this is the input to template `output_format.j2` referenced in section 09).
3. **Validating** (Phase 2) the executor's actual response against the declared format — confirming the executor delivered what was requested.
The engine sits across two pipeline locations:
- During `PROMPT_BUILDER` execution, it produces the `<output_format>` content.
- During Phase 2's response handling, it produces a validation verdict.
In Phase 1 (paste-based execution), only the inference path runs. Validation is by the OPERATOR's eye on the pasted-back result. In Phase 2, validation is automated and feeds back to a quality loop.
This page defines:
- The closed catalog of output format types and their schemas
- The inference algorithm: from artifacts to format declaration
- The format declaration rendering (what goes into `<output_format>`)
- The Phase 2 validation algorithm
- The escalation path when the executor's output doesn't match
---
## 2. Why This Matters
Without a format engine:
- `<output_format>` tags say "appropriate format" — a non-instruction.
- Executors return prose when the user wanted JSON, or vice versa.
- Downstream consumers (other CEE Runs, programmatic uses) can't rely on shape.
- Phase 2 has no way to check whether the executor did what was asked.
The engine makes "every prompt is perfect" extend to the output side: the prompt declares the shape, and (in Phase 2) the system can verify the shape was honored.
---
## 3. Core Requirements
The engine MUST:
1. Maintain a closed catalog of output format types (§5.1) — extensible only via bible edit.
2. Infer exactly one format per Run from upstream artifacts.
3. Render the `<output_format>` tag content as a specific, machine-checkable description, not vague guidance.
4. Support user-supplied format overrides via `IntentObject` and CLI flags.
5. (Phase 2) Validate executor output against the declared format and produce a verdict artifact.
6. Be deterministic: same inputs produce the same format declaration.
7. Be invokable independently of `PROMPT_BUILDER` for testing.
The engine MUST NOT:
- Output a free-form description for `<output_format>`. Even prose deliverables get structured spec (length, tone, sections).
- Allow ambiguous formats (e.g., "JSON or XML, your choice").
- Validate output in Phase 1 — that's the OPERATOR's job until the API loop exists.
- Generate new format types at runtime. The catalog is closed.
---
## 4. System Rules
**Rule 1 — Closed format catalog.**
Format types are an enum. New types require a bible edit and a schema migration. §5.1 is the canonical list.
**Rule 2 — Every Run has exactly one declared format.**
Multi-format outputs (e.g., "a markdown report plus a CSV file") are expressed by the format `multi_artifact` with a structured manifest, not by listing two formats.
**Rule 3 — Format inference is artifact-driven.**
Inference reads only `IntentObject` and `Classification`. It does not call Claude. Pure deterministic logic.
**Rule 4 — User overrides win.**
If `IntentObject.user_specified_format` is set, that wins over inference. The engine still validates the user's specification against the catalog.
**Rule 5 — Format declarations are concrete.**
A format declaration always includes: shape (file, prose, JSON, table, etc.), structure (sections, fields, length), and acceptance criteria (what makes it valid).
**Rule 6 — Phase 2 validation is non-blocking by default.**
A failed validation produces a warning and a quality verdict, not an automatic re-run. The OPERATOR decides whether to re-run. This avoids loops on legitimate edge cases.
**Rule 7 — Format and ****`task_type`**** are coupled but not identical.**
The default format per `task_type` is in §5.2. User overrides and `IntentObject.deliverable` can pull the format toward a different value within the catalog. The combination of `task_type` + format must be coherent (validated in §5.5).
**Rule 8 — Output format is part of ****`FinalPrompt`****.**
The engine produces the *content* of the `<output_format>` tag. The tag itself is rendered by `PROMPT_BUILDER`'s template per section 09. The engine and the template are separate; the engine produces a structured object, the template formats it as text.
---
## 5. Detailed Workflow — The Engine
### 5.1 The closed format catalog
<table header-row="true">
<tr>
<td>Format</td>
<td>Shape</td>
<td>Typical for</td>
<td>Structure declaration</td>
</tr>
<tr>
<td>`code_file`</td>
<td>One source file</td>
<td>BUILD (small)</td>
<td>language, path, expected size range</td>
</tr>
<tr>
<td>`code_project`</td>
<td>Multi-file repo</td>
<td>BUILD (large)</td>
<td>language, file list, entry point</td>
</tr>
<tr>
<td>`prose_short`</td>
<td>\<500 word prose</td>
<td>WRITE (email, post)</td>
<td>length, tone, sections</td>
</tr>
<tr>
<td>`prose_long`</td>
<td>500–5000 word prose</td>
<td>WRITE (article, doc)</td>
<td>length, tone, headers, sections</td>
</tr>
<tr>
<td>`prose_manuscript`</td>
<td>5000+ word prose</td>
<td>WRITE (chapter, manuscript)</td>
<td>structure, voice, scope</td>
</tr>
<tr>
<td>`markdown_report`</td>
<td>Structured markdown</td>
<td>ANALYZE, RESEARCH</td>
<td>section list, required headings</td>
</tr>
<tr>
<td>`markdown_decision`</td>
<td>Decision doc</td>
<td>DECIDE</td>
<td>recommendation + tradeoffs + change-conditions</td>
</tr>
<tr>
<td>`diagnosis_and_fix`</td>
<td>DEBUG output</td>
<td>DEBUG</td>
<td>diagnosis section + fix section + verification</td>
</tr>
<tr>
<td>`json_object`</td>
<td>Single JSON</td>
<td>TRANSFORM, ANALYZE</td>
<td>schema reference or inline schema</td>
</tr>
<tr>
<td>`json_array`</td>
<td>Array of JSON objects</td>
<td>TRANSFORM, ANALYZE</td>
<td>item schema</td>
</tr>
<tr>
<td>`csv_table`</td>
<td>CSV/TSV</td>
<td>TRANSFORM, ANALYZE</td>
<td>columns, types</td>
</tr>
<tr>
<td>`mixed_artifact`</td>
<td>Multiple files of varying types</td>
<td>ORCHESTRATE</td>
<td>manifest of artifacts</td>
</tr>
<tr>
<td>`email_draft`</td>
<td>Email content</td>
<td>WRITE</td>
<td>subject + body, optionally to/cc fields</td>
</tr>
<tr>
<td>`outline`</td>
<td>Hierarchical outline</td>
<td>RESEARCH, WRITE</td>
<td>depth, format (numbered/nested)</td>
</tr>
<tr>
<td>`comparison_table`</td>
<td>Side-by-side analysis</td>
<td>ANALYZE, DECIDE</td>
<td>rows, columns, criteria</td>
</tr>
<tr>
<td>`step_by_step_guide`</td>
<td>Procedural</td>
<td>BUILD, WRITE</td>
<td>step count, format per step</td>
</tr>
<tr>
<td>`code_review`</td>
<td>Issue list with severity</td>
<td>DEBUG, ANALYZE</td>
<td>issue format, severity scale</td>
</tr>
<tr>
<td>`audit_report`</td>
<td>Findings + recommendations</td>
<td>ANALYZE</td>
<td>finding format, severity, remediation</td>
</tr>
</table>
### 5.2 Default format per task_type
<table header-row="true">
<tr>
<td>`task_type`</td>
<td>Default format</td>
<td>Rationale</td>
</tr>
<tr>
<td>`BUILD`</td>
<td>`code_file` (or `code_project` if `IntentObject.deliverable` implies multi-file)</td>
<td>The build is the deliverable.</td>
</tr>
<tr>
<td>`ANALYZE`</td>
<td>`markdown_report`</td>
<td>Structured findings are the typical analyze output.</td>
</tr>
<tr>
<td>`DEBUG`</td>
<td>`diagnosis_and_fix`</td>
<td>Two-part: explain + correct.</td>
</tr>
<tr>
<td>`WRITE`</td>
<td>`prose_short`, `prose_long`, or `prose_manuscript` based on length hints</td>
<td>Prose is the deliverable.</td>
</tr>
<tr>
<td>`RESEARCH`</td>
<td>`markdown_report`</td>
<td>Sourced summary, structured.</td>
</tr>
<tr>
<td>`TRANSFORM`</td>
<td>inferred from input/output type pair</td>
<td>"CSV → JSON" → `json_array`; "code old → code new" → `code_file`.</td>
</tr>
<tr>
<td>`DECIDE`</td>
<td>`markdown_decision`</td>
<td>Recommendation + tradeoffs + change-conditions.</td>
</tr>
<tr>
<td>`ORCHESTRATE`</td>
<td>`mixed_artifact`</td>
<td>Multi-output by definition.</td>
</tr>
</table>
The defaults are starting points. `IntentObject.deliverable` can pull the format toward a different catalog entry — e.g., `task_type=ANALYZE` + `deliverable="comparison of two frameworks"` → `comparison_table`.
### 5.3 The inference algorithm
```python
def infer_format(intent_object, classification) -> FormatDeclaration:
    # 1. Check for user-specified format
    if intent_object.user_specified_format:
        validated = validate_user_format(intent_object.user_specified_format)
        if validated:
            return populate_declaration(validated, intent_object, classification)
        # Invalid user spec — fall through to inference with a warning
    
    # 2. Start from task_type default
    candidate = DEFAULT_FORMAT_BY_TASK_TYPE[classification.task_type]
    
    # 3. Refine based on IntentObject.deliverable
    deliverable_signals = parse_deliverable(intent_object.deliverable)
    if deliverable_signals.suggests_format:
        candidate = pick_better_match(candidate, deliverable_signals)
    
    # 4. Refine based on length hints
    if classification.task_type == "WRITE":
        candidate = pick_prose_length(intent_object, classification)
    
    # 5. Refine based on attachments
    if intent_object.attachments and classification.task_type == "TRANSFORM":
        candidate = pick_transform_format(intent_object.attachments, intent_object.deliverable)
    
    # 6. Validate task_type + format coherence
    if not is_coherent(classification.task_type, candidate):
        candidate = DEFAULT_FORMAT_BY_TASK_TYPE[classification.task_type]
        log_incoherence(candidate, classification)
    
    return populate_declaration(candidate, intent_object, classification)
```
`populate_declaration` fills in the format-specific structure declaration:
```python
def populate_declaration(format_type, intent_object, classification):
    return FormatDeclaration(
        format_type=format_type,
        shape=SHAPE_BY_FORMAT[format_type],
        structure=derive_structure(format_type, intent_object, classification),
        acceptance_criteria=derive_acceptance(format_type, intent_object),
        produced_by="OUTPUT_FORMAT_ENGINE"
    )
```
### 5.4 The format declaration object
```json
{
  "format_type": "markdown_report",
  "shape": "structured markdown document",
  "structure": {
    "required_sections": ["Summary", "Findings", "Recommendations"],
    "optional_sections": ["Methodology", "References"],
    "section_order": "as listed",
    "heading_level": "H2 for sections"
  },
  "acceptance_criteria": [
    "All required sections present",
    "Each finding includes evidence reference",
    "Recommendations are actionable (verb + object)"
  ],
  "produced_by": "OUTPUT_FORMAT_ENGINE"
}
```
Different format types have different `structure` shapes. `code_file` has `language`, `path`, `size_range`. `csv_table` has `columns` (array of `{name, type}`).
### 5.5 Coherence validation
Some `task_type` × format pairs are incoherent. For example:
- `task_type=DEBUG` + format=`prose_long` is incoherent (debugging needs the diagnosis-and-fix structure).
- `task_type=BUILD` + format=`comparison_table` is incoherent (a build deliverable isn't a table).
The coherence matrix at `~/cee/output_format/coherence.py` encodes allowed pairs. Incoherent pairs trigger a fallback to the default format with a warning.
### 5.6 Format declaration rendering
The format declaration flows into `PROMPT_BUILDER`'s `output_format.j2` template. The template renders the declaration as text inside the `<output_format>` tag.
Example rendering for `markdown_report`:
```xml
<output_format>
  <type>markdown_report</type>
  <shape>Structured markdown document.</shape>
  <required_sections>
    <section>Summary</section>
    <section>Findings</section>
    <section>Recommendations</section>
  </required_sections>
  <heading_convention>Use H2 (##) for top-level sections.</heading_convention>
  <acceptance_criteria>
    <criterion>All required sections present.</criterion>
    <criterion>Each finding includes evidence reference.</criterion>
    <criterion>Recommendations are actionable (verb + object).</criterion>
  </acceptance_criteria>
</output_format>
```
The renderer is deterministic; the same `FormatDeclaration` always renders the same XML.
### 5.7 Phase 2 validation
When Phase 2 ships and CEE receives the executor's output programmatically, the engine validates:
```python
def validate_output(declaration: FormatDeclaration, output: str) -> ValidationVerdict:
    validator = VALIDATORS_BY_FORMAT[declaration.format_type]
    structural_result = validator.check_structure(output, declaration.structure)
    acceptance_result = validator.check_acceptance(output, declaration.acceptance_criteria)
    
    return ValidationVerdict(
        format_type=declaration.format_type,
        structural_pass=structural_result.passed,
        structural_issues=structural_result.issues,
        acceptance_pass=acceptance_result.passed,
        acceptance_issues=acceptance_result.issues,
        overall_quality_score=score(structural_result, acceptance_result)
    )
```
Validators per format:
- `code_file`: parses the file with the appropriate language parser; checks syntax, file extension, size.
- `markdown_report`: parses headings; checks required sections present; checks heading levels.
- `json_object` / `json_array`: parses JSON; validates against declared schema.
- `csv_table`: parses CSV; checks column names and types.
- `prose_*`: word count check; tone-check (lightweight LLM call); section detection.
- `diagnosis_and_fix`: checks for both a diagnosis section and a fix section.
- `mixed_artifact`: parses the manifest; recursively validates each artifact.
Acceptance criteria checks may use Claude (temperature 0, fixed prompt) when structure check alone can't verify (e.g., "recommendations are actionable" requires comprehension).
### 5.8 Verdict handling
The verdict is logged but not blocking by default (Rule 6). Three response paths:
- **Pass:** Run completes; verdict logged.
- **Soft fail:** non-critical issues (e.g., one missing optional section). Verdict logged with severity `warning`. Run completes.
- **Hard fail:** critical issues (e.g., no JSON parse). Verdict logged with severity `error`. OPERATOR is notified. Optionally, with `--auto-rerun` config, the Run re-executes with format reinforcement in the prompt.
Auto-rerun is opt-in to prevent loops.
---
## 6. Data / Inputs Needed
### 6.1 Required inputs to inference
- `IntentObject`
- `Classification`
- Format catalog (`~/cee/output_format/catalog.py`)
- Coherence matrix (`~/cee/output_format/coherence.py`)
- Defaults table (`~/cee/output_format/defaults.py`)
### 6.2 Required inputs to validation (Phase 2)
- `FormatDeclaration` (from inference, persisted in run dir)
- Executor's raw output
- Format-specific validators at `~/cee/output_format/validators/<format>.py`
### 6.3 Configuration
- `~/.cee/config.toml` `[output_format]` section:
	- `auto_rerun_on_hard_fail` (default false)
	- `acceptance_check_uses_llm` (default true; false disables LLM-backed acceptance checks for deterministic tests)
	- `prose_short_max_words` (default 500)
	- `prose_long_max_words` (default 5000)
---
## 7. Outputs Produced
### 7.1 The `FormatDeclaration` artifact
Persisted to `~/cee/runs/<run_id>/format.json`. Consumed by `PROMPT_BUILDER`.
### 7.2 The `<output_format>` tag content
Rendered into the FinalPrompt via section 09's template.
### 7.3 The `ValidationVerdict` artifact (Phase 2)
Persisted to `~/cee/runs/<run_id>/validation_verdict.json` after executor returns. Used by quality monitoring.
### 7.4 Audit log entries
Inference decision, refinement steps, and validation outcomes logged to `~/cee/audit/roles.log`.
---
## 8. Agent + Skill Implications
### 8.1 Format informs agent selection indirectly
`AGENT_SELECTOR` doesn't read `FormatDeclaration` directly (selection happens before format inference in the pipeline). But the default format per `task_type` is part of what `task_types_supported` agents are good at — agents declare `task_types_supported`, and the format engine declares the default per `task_type`, so the chain is implicit but consistent.
### 8.2 Skills can declare format expectations
A Skill's frontmatter `outputs` field can name a format (e.g., `outputs: [markdown_report]`). When such a Skill is selected, the format engine treats it as a strong signal toward that format. If the user-specified format conflicts with the Skill's expected output, the engine prefers the user but logs the conflict.
### 8.3 Some Skills enforce structure beyond what the format engine knows
For example, a `decision-with-tradeoffs` Skill mandates a specific decision-doc structure. The format engine declares `markdown_decision` format; the Skill body refines the structure further. The Skill takes precedence on details.
---
## 9. Edge Cases
**EC1 — User explicitly specifies a format not in the catalog.**
The engine validates against catalog; rejects with explicit error listing the closed enum.
**EC2 — ****`task_type=ORCHESTRATE`**** with sub-tasks of varying formats.**
Default format is `mixed_artifact` with a manifest declaring per-sub-task formats. The orchestrator agent populates the manifest at execution time.
**EC3 — ****`IntentObject.deliverable`**** is empty.**
Fall back to default format for the `task_type`. Log the fallback.
**EC4 — Input is a CSV and user wants "summarize this."**
`task_type=ANALYZE`, format=`markdown_report`. Even though input is CSV, output is structured markdown. The engine differentiates input format from output format.
**EC5 — Multi-file project requested under prose-style framing ("write me documentation for this codebase").**
`task_type=WRITE`, format=`prose_long` or `markdown_report` depending on structure. Documentation is prose, not code, even though the input is code.
**EC6 — Validation in Phase 2 hits a parser bug.**
Verdict is `inconclusive`. Logged. Run treated as soft pass.
**EC7 — Acceptance criterion requires LLM judgment but config disables LLM checks.**
That criterion is skipped; verdict notes "acceptance check skipped: LLM disabled."
**EC8 — Output is technically valid but low quality (e.g., recommendations are present but generic).**
Quality score reflects this; verdict may be `soft_fail` even though structural pass.
**EC9 — User wants the SAME run with output in TWO formats.**
Two Runs. The engine doesn't multi-render. The replay path (`cee replay --different-format`) supports this for the second.
**EC10 — Format inference produces a different format than what the user reads as "natural."**
User can override via `--format <type>` CLI flag. The engine validates and uses if coherent.
**EC11 — A format type's validator doesn't exist yet.**
Verdict is `validation_unavailable`. Logged. Format declaration still rendered correctly. Validator added in subsequent build.
**EC12 — Phase 1 user wants format validation.**
They paste the executor's output back to CEE: `cee validate <run_id> --output-file <path>`. The engine runs validation and emits a verdict. Manual but available.
---
## 10. Failure Modes
### 10.1 Inference picks an incoherent format
**Failure:** `task_type=DEBUG` + format=`prose_long` slips through.
**Detection:** coherence matrix check.
**Recovery:** fall back to default; log incoherence; coherence matrix updated if a new pattern emerges.
### 10.2 User override is invalid
**Failure:** user specifies a format not in catalog.
**Detection:** validate at IntentObject parse time.
**Recovery:** halt at interpreter step with a clarification request listing valid formats.
### 10.3 Format declaration is too vague
**Failure:** `<output_format>` tag content is generic ("a report"); executor produces something unstructured.
**Detection:** Phase 2 validation flags low structural compliance; in Phase 1, OPERATOR notices.
**Recovery:** declaration rendering tightened; structure derivation made more specific per format.
### 10.4 Validator regression
**Failure:** validator passes obviously bad output.
**Detection:** golden Run validation tests.
**Recovery:** validator strengthened; tests updated.
### 10.5 LLM-backed acceptance check drifts
**Failure:** same output validates differently across days.
**Detection:** validation determinism test.
**Recovery:** temperature 0 verified; system prompt locked; pin model version.
### 10.6 Format catalog drift
**Failure:** a new format is added in code but not in this bible page.
**Detection:** boot's cross-section consistency check.
**Recovery:** halt; bible updated.
### 10.7 Coherence matrix incomplete
**Failure:** a `task_type` × format pair is neither marked coherent nor incoherent.
**Detection:** matrix check returns "unknown."
**Recovery:** treat as incoherent (conservative); update matrix.
### 10.8 Auto-rerun loop
**Failure:** `auto_rerun_on_hard_fail` triggers; rerun also fails; loop.
**Detection:** rerun counter per Run.
**Recovery:** cap at 2 reruns. After cap, halt with error.
### 10.9 Phase 2 validation overwhelms small-Run quality
**Failure:** validation overhead exceeds Run value for trivial Runs.
**Detection:** validation latency monitoring.
**Recovery:** validation can be disabled per Run via `--no-validate` flag.
### 10.10 Format declaration gets stale relative to Skill body
**Failure:** Skill body says "output as a numbered list" but format declaration says `prose_long`.
**Detection:** Phase 2 validation finds compliance with Skill but not declaration.
**Recovery:** declaration takes precedence; Skill body updated to match, or Skill's `outputs` field aligned with the format engine.
---
## 11. Build Notes for Claude Code
- **Engine location:** `~/cee/output_format/engine.py`. Public function: `infer(intent_object, classification) -> FormatDeclaration`.
- **Catalog:** `~/cee/output_format/catalog.py`. Closed enum + per-format shape constants.
- **Defaults:** `~/cee/output_format/defaults.py`. `task_type` → default format mapping.
- **Coherence matrix:** `~/cee/output_format/coherence.py`. Pair table.
- **Inference refinement functions:** `~/cee/output_format/refinement/` — per-input-source refinement logic (deliverable parsing, length hints, attachment parsing).
- **Validators (Phase 2):** `~/cee/output_format/validators/<format>.py`. One module per format type. Each exports `check_structure(output, structure)` and `check_acceptance(output, criteria)`.
- **Format-specific schemas (for ****`json_*`**** types):** at `~/cee/output_format/schemas/`. Referenced by validators.
- **Tests:** unit tests per format type for inference and validation. Golden Runs include format declarations and (for Phase 2) sample executor outputs to validate against.
- **Catalog consistency check:** boot validates that the catalog in code matches the catalog in this bible page §5.1. Drift halts boot.
- **Renderer integration:** `PROMPT_BUILDER`'s `output_format.j2` template imports the renderer at `~/cee/output_format/renderer.py`. The renderer takes a `FormatDeclaration` and produces the XML inner content.
---
## 12. Definition of Done
This page is complete — and the engine is unblocked for build — when:
- [ ] The closed format catalog in §5.1 is reflected in `~/cee/output_format/catalog.py`.
- [ ] Default format per task_type from §5.2 is in `~/cee/output_format/defaults.py`.
- [ ] Coherence matrix covers every `task_type` × format pair.
- [ ] Inference is deterministic and tested per task_type.
- [ ] User override path validates and uses correctly.
- [ ] `<output_format>` tag rendering produces consistent, structured XML.
- [ ] Phase 2 validators exist for all format types — even stub implementations that return `inconclusive` are acceptable, so Phase 2 doesn't break.
- [ ] All edge cases in §9 are tested.
- [ ] Failure modes in §10 each have a corresponding test or documented recovery.
- [ ] Boot's consistency check verifies catalog/defaults/coherence align with this page.
---
## 13. Final Statement
The Output Format Engine is what makes "specific output format" a property of every Run rather than a hope. It infers the format deterministically, declares it concretely in the FinalPrompt, and (in Phase 2) verifies the executor honored it. Combined with the upstream determinism of `INTERPRETER`, `CLASSIFIER`, and `PROMPT_BUILDER`, this closes the loop: input → declared format → output → validation. Every Run can be audited end-to-end. The user stops wondering whether the executor "got the shape right" — the system knows.
