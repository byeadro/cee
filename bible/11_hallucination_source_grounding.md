---
notion_section: 11
notion_title: 11 — HALLUCINATION + SOURCE GROUNDING
mirrored_at: 2026-04-30
---

# 11 — HALLUCINATION + SOURCE GROUNDING
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the complete specification for how CEE prevents Claude from filling missing context with fabrication. Section 08 sets the `needs_grounding` flag. Section 05 includes a `<grounding_rules>` tag in the FinalPrompt. This page defines the *content* of those rules — what allowed-source enumeration looks like, what prohibited-inference statements look like, and what citation requirements look like — plus how (in Phase 2) outputs are checked for grounding compliance.
---
## 1. What This Is
Hallucination in CEE's context means: the executor producing content not supported by either the upstream artifacts or the explicitly-allowed sources, presented as if it were grounded. The fix is structural — the FinalPrompt declares allowed sources, prohibited inferences, and citation requirements, and (in Phase 2) the output is validated against those declarations.
This page defines:
- The closed enum of source types (the only kinds of source a Run can declare)
- The grounding rules engine: how it builds the `<grounding_rules>` tag content from upstream artifacts
- The prohibited-inference catalog: what classes of fabrication CEE explicitly forbids
- The citation contract: when and how the executor must reference its sources
- The Phase 2 validation pass: how to check whether the output stayed grounded
- The escalation path when grounding cannot be guaranteed
This page is owned by `SAFETY_GATE` for the grounding-specific rules, but the content generation happens upstream during prompt construction. The split: the format engine (10) declares output shape; this page declares output truthfulness.
---
## 2. Why This Matters
Without grounding rules:
- Claude fills missing context with plausible-sounding fabrication.
- The user can't tell what was sourced and what was invented.
- Research outputs cite imaginary papers; code outputs invent API methods; analysis outputs hallucinate numbers.
- Trust degrades silently — most outputs look fine until one is checked carefully.
The cost of hallucination is highest when it's hardest to detect. CEE's defense is to make grounding explicit in the prompt and (Phase 2) verifiable in the output. The user gets two protections: the executor was told exactly what it could rely on, and the system checks whether it complied.
---
## 3. Core Requirements
The grounding system MUST:
1. Set `flags.needs_grounding` deterministically in the classifier (rules in §5.4.1 of section 08, refined here).
2. When grounding is needed, populate the `<grounding_rules>` tag with three sub-tags: `<allowed_sources>`, `<prohibited_inferences>`, `<citation_requirement>`.
3. Enumerate allowed sources from a closed catalog of source types — vague references like "the internet" or "your training data" are forbidden.
4. List prohibited inferences explicitly when patterns suggest fabrication risk.
5. Define citation requirements concretely: where citations appear, what they reference, what format they take.
6. (Phase 2) Validate the executor's output against the declared grounding rules and produce a `GroundingVerdict`.
7. Halt the Run when grounding is required but no allowed sources can be identified.
The grounding system MUST NOT:
- Allow grounding to be silently disabled. If `needs_grounding` is true, `<grounding_rules>` must appear in the FinalPrompt.
- Accept "general knowledge" as a source. If a fact is general knowledge, it doesn't need a source; if it isn't, it needs an explicit one.
- Use Claude's training corpus as a declarable source. Training data is not a verifiable source.
- Check only structural compliance in Phase 2. Citation presence does not equal citation correctness.
---
## 4. System Rules
**Rule 1 — Grounding is conditional but binary.**
Either `needs_grounding` is true (and the tag appears, fully populated) or false (and the tag is omitted). There is no "weakly grounded" mode.
**Rule 2 — Closed source-type enum.**
Sources are typed (§5.1). New source types require a bible edit.
**Rule 3 — Sources must be specific and reachable.**
A "reachable" source is one the executor can actually consult: an attachment in the FinalPrompt's `<context>`, a file path the executor can read, a URL Claude can fetch (Phase 2), or a documented system-of-record. Vague gestures fail.
**Rule 4 — Prohibited inferences are explicit, not implicit.**
When the classifier identifies a fabrication risk pattern (e.g., "specific API methods" or "exact dates"), the prompt explicitly forbids inference on those. The executor sees the prohibition; it doesn't have to guess.
**Rule 5 — Citation format is specified.**
The `<citation_requirement>` tag declares the format (inline, footnote, bracketed reference, etc.) and the granularity (per fact, per paragraph, per section).
**Rule 6 — Empty allowed sources halt the Run.**
If grounding is required but no allowed source can be assembled, the Run halts with `grounding_unsourceable`. Better to halt than to deliver a prompt that demands grounding from nothing.
**Rule 7 — Validation is non-blocking by default.**
Phase 2 validation produces a verdict, not a hard stop. Like the format engine (Rule 6 of section 10), this prevents loops.
**Rule 8 — Grounding does not replace the executor's judgment.**
The grounding rules constrain what the executor can claim. They do not constrain how the executor reasons. Good reasoning over allowed sources is still expected.
**Rule 9 — Failure to ground is failure to deliver.**
A Phase 2 output with grounding violations is flagged for OPERATOR review. Repeated violations of the same type indicate a prompt construction issue, not an executor issue.
**Rule 10 — Grounding rules don't apply to creative outputs.**
WRITE tasks for creative prose (fiction, opinion, branded voice) don't require grounding even when sources are present. The classifier distinguishes via `IntentObject.deliverable` shape — "an essay arguing X" needs grounding on X's facts; "a short story about Y" doesn't.
---
## 5. Detailed Workflow — The Grounding System
### 5.1 The closed source-type enum
<table header-row="true">
<tr>
<td>Type</td>
<td>Description</td>
<td>Reachability</td>
</tr>
<tr>
<td>`attachment`</td>
<td>A file attached to the Run (`IntentObject.attachments`).</td>
<td>Inlined or summarized in `<context>`.</td>
</tr>
<tr>
<td>`filesystem_path`</td>
<td>A file or directory the executor can read at execution time.</td>
<td>Path in `<context>`; executor reads via Read/Bash tools.</td>
</tr>
<tr>
<td>`url`</td>
<td>A web URL.</td>
<td>Phase 2: web_fetch tool. Phase 1: user pastes content.</td>
</tr>
<tr>
<td>`internal_skill_reference`</td>
<td>A specific Skill that encodes domain knowledge.</td>
<td>Skill referenced in `<skills>`; executor loads it.</td>
</tr>
<tr>
<td>`bible_section`</td>
<td>A section of CEE's own System Design Bible (for self-referential Runs).</td>
<td>Referenced by section number; bible mirror in `~/cee/bible/`.</td>
</tr>
<tr>
<td>`prior_run_artifact`</td>
<td>An artifact from a previous Run.</td>
<td>Path in `<context>`.</td>
</tr>
<tr>
<td>`system_of_record`</td>
<td>A documented authoritative source the executor can query (database, API, calendar).</td>
<td>Reachable via tool; named in `<allowed_sources>`.</td>
</tr>
<tr>
<td>`user_provided_text`</td>
<td>Verbatim text the user supplied as ground truth.</td>
<td>Quoted in `<context>`.</td>
</tr>
</table>
These are the only allowed values inside `<allowed_sources>`. Any source declaration must reduce to one of these.
### 5.2 When `needs_grounding` is set
Section 08 §5.4.1 lists the trigger rules. Restating with refinements specific to this engine:
The flag is true when:
1. `task_type = RESEARCH` — always grounded.
2. `task_type = ANALYZE` and the analysis subject is a user-supplied document.
3. `IntentObject.goal` mentions specific facts, numbers, names, or sources that the executor must respect (regex match on dates, proper nouns indicating sources, numeric quantities).
4. `IntentObject.implicit_assumptions` contains any assumption about specific factual content.
5. `task_type = DECIDE` and the decision rests on factual claims (regex: "based on", "according to", "given that the data shows").
6. Any Skill in `SkillSet` declares `outputs` that include sourced content (`outputs: [sourced_summary, ...]`).
The flag is false when (overrides above):
- `task_type = WRITE` and `IntentObject.deliverable` indicates creative prose (fiction, opinion, branded voice, narrative).
- `task_type = BUILD` for self-contained code where no external facts are claimed.
- `IntentObject.user_specified_format` is `prose_short` and the goal is conversational (e.g., draft an email).
### 5.3 Building `<grounding_rules>` content
When `needs_grounding` is true, the engine constructs the tag from three derived sub-objects.
#### 5.3.1 Allowed sources
```python
def derive_allowed_sources(intent_object, agent_plan, skill_set, classification):
    sources = []
    
    # Attachments are always allowed sources
    for attachment in intent_object.attachments:
        sources.append(SourceRef(
            type="attachment",
            identifier=attachment.name,
            description=attachment.summary
        ))
    
    # Filesystem paths mentioned in the goal
    for path in extract_paths(intent_object.goal):
        if filesystem_path_exists(path):
            sources.append(SourceRef(
                type="filesystem_path",
                identifier=path,
                description=infer_description(path)
            ))
    
    # URLs explicitly mentioned
    for url in extract_urls(intent_object.goal):
        sources.append(SourceRef(
            type="url",
            identifier=url,
            description="referenced by user"
        ))
    
    # Skills with sourced-output expectations
    for skill in skill_set.skills:
        if "sourced" in str(skill.outputs):
            sources.append(SourceRef(
                type="internal_skill_reference",
                identifier=skill.slug,
                description=skill.description
            ))
    
    # User-provided text in IntentObject.context_pasted (if any)
    if intent_object.context_pasted:
        sources.append(SourceRef(
            type="user_provided_text",
            identifier="user-supplied context",
            description="treat as ground truth"
        ))
    
    # System-of-record (Phase 2): connectors named in IntentObject
    for sor in intent_object.system_of_record_refs:
        sources.append(SourceRef(
            type="system_of_record",
            identifier=sor.name,
            description=sor.description
        ))
    
    return sources
```
If the result is empty and `needs_grounding` is true: halt with `grounding_unsourceable`.
#### 5.3.2 Prohibited inferences
The engine consults a pattern catalog at `~/cee/grounding/prohibition_patterns.py` to identify which fabrication risks apply. Examples:
<table header-row="true">
<tr>
<td>Pattern in goal</td>
<td>Prohibition emitted</td>
</tr>
<tr>
<td>API names mentioned without docs attached</td>
<td>"Do not invent API methods, parameters, or return types not documented in allowed sources."</td>
</tr>
<tr>
<td>Specific dates referenced</td>
<td>"Do not invent dates not present in allowed sources."</td>
</tr>
<tr>
<td>Specific numbers / statistics</td>
<td>"Do not invent numerical values not present in allowed sources."</td>
</tr>
<tr>
<td>Author / paper / publication names</td>
<td>"Do not invent citations, authors, paper titles, or publication metadata."</td>
</tr>
<tr>
<td>Code references (function names, class names)</td>
<td>"Do not invent function or class names; reference only those visible in allowed sources."</td>
</tr>
<tr>
<td>Legal concepts</td>
<td>"Do not invent statute numbers, case citations, or jurisdiction-specific rules."</td>
</tr>
<tr>
<td>Medical / scientific facts</td>
<td>"Do not invent dosages, study results, or mechanism descriptions."</td>
</tr>
</table>
The engine emits the relevant prohibitions based on which patterns the input matches. Prohibition text is from a fixed library, not generated.
A default prohibition always appears: "If a fact cannot be grounded in an allowed source, state explicitly that the source does not cover it. Do not infer."
#### 5.3.3 Citation requirement
Generated based on `task_type` and the source types in `<allowed_sources>`:
<table header-row="true">
<tr>
<td>Task / source pattern</td>
<td>Citation requirement</td>
</tr>
<tr>
<td>`RESEARCH` with multiple sources</td>
<td>"Every factual claim must reference a specific source by its identifier in `<allowed_sources>`."</td>
</tr>
<tr>
<td>`ANALYZE` with one document attachment</td>
<td>"Reference specific sections/pages of the attachment for each finding."</td>
</tr>
<tr>
<td>`DECIDE` with sourced rationale</td>
<td>"Each tradeoff in the decision should reference the source that informs it."</td>
</tr>
<tr>
<td>`BUILD` with a documented API source</td>
<td>"API references in code comments must cite the source documentation."</td>
</tr>
<tr>
<td>Single user-provided text source</td>
<td>"Treat user-provided text as authoritative; do not contradict it."</td>
</tr>
</table>
Citation format defaults to inline bracketed reference: `[<source_identifier>]`. For longer sources (manuscripts, large codebases), section-level: `[<source_identifier> § <section>]`.
### 5.4 The `<grounding_rules>` tag content
Combining the three sub-objects, the engine produces XML the prompt builder's `grounding_rules.j2` template renders:
```xml
<grounding_rules>
  <allowed_sources>
    <source type="attachment" id="2026_q1_report.pdf">Q1 financial report (12 pages, summary in context)</source>
    <source type="filesystem_path" id="~/projects/embra/src/auth.py">Current auth implementation</source>
    <source type="internal_skill_reference" id="write-rls-policies">Sourced Skill for Supabase RLS</source>
  </allowed_sources>
  <prohibited_inferences>
    <prohibition>Do not invent API methods, parameters, or return types not documented in allowed sources.</prohibition>
    <prohibition>Do not invent numerical values not present in allowed sources.</prohibition>
    <prohibition>If a fact cannot be grounded in an allowed source, state explicitly that the source does not cover it. Do not infer.</prohibition>
  </prohibited_inferences>
  <citation_requirement>
    Every factual claim must reference a specific source by its identifier in &lt;allowed_sources&gt;.
    Use inline bracketed reference format: [source_id] or [source_id § section] for sectional sources.
  </citation_requirement>
</grounding_rules>
```
### 5.5 Phase 2 validation
When the executor's output returns (Phase 2), the engine validates grounding compliance:
```python
def validate_grounding(declaration: GroundingDeclaration, output: str) -> GroundingVerdict:
    # 1. Citation presence
    citations = extract_citations(output)
    
    # 2. Citation correctness — each citation maps to an allowed source
    invalid_citations = [c for c in citations if c.source_id not in declaration.allowed_source_ids]
    
    # 3. Citation coverage — claims that should be cited but aren't
    claims = extract_factual_claims(output)  # uses Claude with temperature 0
    uncited_claims = [claim for claim in claims if not has_nearby_citation(claim, citations)]
    
    # 4. Prohibited content detection — flagged inferences that match prohibition patterns
    prohibited_violations = []
    for prohibition in declaration.prohibited_inferences:
        violations = scan_for_violation(output, prohibition)
        prohibited_violations.extend(violations)
    
    # 5. Score
    structural_pass = len(invalid_citations) == 0 and len(prohibited_violations) == 0
    coverage_pass = len(uncited_claims) / max(len(claims), 1) < 0.10  # 90% of claims cited
    
    return GroundingVerdict(
        structural_pass=structural_pass,
        coverage_pass=coverage_pass,
        invalid_citations=invalid_citations,
        uncited_claims=uncited_claims,
        prohibited_violations=prohibited_violations,
        overall_quality_score=score(...)
    )
```
The verdict is logged and surfaced to OPERATOR. Per Rule 7, it does not auto-rerun unless explicitly enabled.
### 5.6 The escalation path
When grounding cannot be guaranteed for a Run that requires it:
1. The engine attempts source enumeration (§5.3.1).
2. If no sources can be identified, the engine emits a `ClarificationRequest` asking the OPERATOR: "This Run requires grounding but no source was identifiable. Please provide: (a) attachments, (b) URLs, or (c) say 'override grounding' to proceed with explicit acknowledgment that the output may be ungrounded."
3. If OPERATOR provides sources, the Run continues normally.
4. If OPERATOR overrides, the FinalPrompt includes a `<grounding_override_acknowledgment>` block instead of `<grounding_rules>`. The override is logged; the executor knows the user accepted ungrounded output.
The override path exists because forcing grounding on a Run that genuinely doesn't have a source produces empty output. But the override is loud, not silent — both the FinalPrompt and the audit log show the override.
---
## 6. Data / Inputs Needed
### 6.1 Required inputs
- `IntentObject` (with attachments, mentioned paths, mentioned URLs)
- `Classification` (with `flags.needs_grounding`)
- `AgentPlan` (for posture-specific grounding context)
- `SkillSet` (for source-declaring Skills)
- `~/cee/grounding/prohibition_patterns.py` — fabrication risk patterns
- `~/cee/grounding/citation_formats.py` — per-pattern citation rules
### 6.2 Configuration
- `~/.cee/config.toml` `[grounding]` section:
	- `coverage_threshold` (default 0.90 — 90% of claims must be cited)
	- `auto_rerun_on_violation` (default false)
	- `acceptance_check_uses_llm` (default true)
	- `default_citation_format` (default "inline_bracket")
### 6.3 Phase 2 reference data
- Source-of-record connector list (which `system_of_record` types CEE knows how to query)
- Prohibition pattern detector library
---
## 7. Outputs Produced
### 7.1 The `GroundingDeclaration` artifact
Persisted to `~/cee/runs/<run_id>/grounding.json`:
```json
{
  "needs_grounding": true,
  "allowed_sources": [...],
  "prohibited_inferences": [...],
  "citation_requirement": "...",
  "override_acknowledged": false,
  "produced_by": "GROUNDING_ENGINE"
}
```
### 7.2 `<grounding_rules>` tag content
Rendered into the FinalPrompt via the prompt builder template.
### 7.3 The `GroundingVerdict` artifact (Phase 2)
Persisted to `~/cee/runs/<run_id>/grounding_verdict.json` after executor returns.
### 7.4 Audit log entries
Source enumeration results, prohibition pattern matches, citation requirement derivation, and validation outcomes.
---
## 8. Agent + Skill Implications
### 8.1 Some agents are grounding-strict
A `researcher` primary or a `legal-specialist` requires strict grounding. Their bodies state this. The classifier reinforces by setting `needs_grounding` for their typical task_types.
### 8.2 Skills can declare grounding expectations
A Skill's frontmatter can include `grounding_required: true` (extension to the schema in section 07 §5.1.1). When such a Skill is selected, `needs_grounding` is forced true for the Run. This is how a Skill like `summarize-legal-doc` enforces grounding even when other signals don't.
### 8.3 Grounding rules don't change agent selection
Like format, grounding is downstream of selection. The classifier sets the flag; the engine builds the rules; the prompt builder includes them. Agents and Skills are already chosen.
---
## 9. Edge Cases
**EC1 — User attaches a file but it's an image with no extracted text.**
The image is in `<context>` as a base64-or-path reference. It counts as an `attachment` source. The executor (with vision) can read it. If the executor has no vision, halt with `grounding_unsourceable_image`.
**EC2 — User mentions a URL that returns 404 or is paywalled.**
Phase 1: this is the user's problem — they'll see when they paste. Phase 2: the engine pre-fetches and warns if unreachable; OPERATOR confirms whether to proceed.
**EC3 — User provides text that contradicts a Skill's instructions.**
User-provided text is treated as authoritative (per §5.3.3 single-source rule). The Skill is followed where it doesn't contradict. Conflict logged.
**EC4 — Multiple attachments contradict each other.**
The engine doesn't resolve content conflicts. The prompt instructs the executor to "if allowed sources contradict, identify the contradiction explicitly and do not invent a resolution." The OPERATOR resolves.
**EC5 — Task is creative writing but mentions a real person or place.**
WRITE creative is exempt from grounding by Rule 10, but factual claims about real people/places are still risk. The engine adds a single prohibition: "Do not assert specific real-world facts about real people or places not in allowed sources; fictionalize or omit." This is the only prohibition emitted for creative WRITE.
**EC6 — Run requires grounding but the executor is ****`claude_ai`**** (no tool access).**
Sources of type `filesystem_path`, `url`, or `system_of_record` aren't reachable from the web UI. The engine warns and either:
- Inlines short attachments into `<context>` directly (replacing the path reference), or
- Suggests the OPERATOR re-target to `claude_code` for tool access.
**EC7 — User explicitly disables grounding via CLI flag.**
`--no-grounding` is an OPERATOR override. Logs the override. The FinalPrompt skips `<grounding_rules>` and includes a `<grounding_disabled_acknowledgment>` block.
**EC8 — Grounding sources include a Skill but the Skill itself isn't well-grounded.**
The engine treats the Skill as a source in good faith. If the Skill's own content is ungrounded (it claims facts without citation), that's a Skill quality issue handled separately at promotion review.
**EC9 — Sensitive data is one of the allowed sources.**
The source reference in `<allowed_sources>` describes the source generally; sensitive content stays in `<context>` redacted by `SAFETY_GATE`. The grounding engine doesn't redact; section 12 owns that.
**EC10 — Phase 2 validation finds 100% of claims uncited.**
This indicates the executor entirely ignored the citation requirement. Verdict is hard fail. OPERATOR sees the verdict and decides: rerun with stronger citation language, or accept and adjust prompt template.
**EC11 — Validation Claude call drifts (different claims extracted across runs).**
Determinism test catches. Temperature 0 for the validation call. Pin model.
**EC12 — A Run has ****`needs_grounding=true`**** but the IntentObject has no detectable patterns and no attachments.**
This shouldn't happen if the classifier ran correctly. Halt with structured error pointing to upstream.
---
## 10. Failure Modes
### 10.1 Source enumeration empty when grounding required
**Failure:** `derive_allowed_sources` returns empty list.
**Detection:** length check.
**Recovery:** halt with `grounding_unsourceable`; emit clarification request.
### 10.2 Prohibition pattern over-fires
**Failure:** every Run gets all 7 prohibitions, polluting the prompt.
**Detection:** monitoring; OPERATOR feedback.
**Recovery:** patterns made more specific; default-prohibition-only fallback when no specific pattern matches.
### 10.3 Citation requirement too strict
**Failure:** "every factual claim cited" applied to a Run where most claims are paraphrase of one source; over-citation makes output unreadable.
**Detection:** Phase 2 verdict shows over-citation; OPERATOR feedback.
**Recovery:** citation requirement softened to per-paragraph rather than per-claim for low-source-count Runs.
### 10.4 Validation false positives
**Failure:** Claude's claim-extraction misidentifies prose as a factual claim that needs citation.
**Detection:** OPERATOR review of verdicts.
**Recovery:** claim-extraction prompt tightened.
### 10.5 Validation false negatives
**Failure:** real fabrication slips past validation.
**Detection:** OPERATOR catches in delivered output.
**Recovery:** specific patterns for common fabrications added to the prohibition catalog; validation prompt updated.
### 10.6 Override loophole
**Failure:** OPERATOR routinely overrides grounding for tasks that genuinely need it.
**Detection:** override count per task_type / domain.
**Recovery:** override prompt tightens; for sensitive task_types, requires CLI confirmation rather than just a flag.
### 10.7 Grounding rules contradict format declaration
**Failure:** `<output_format>` says "JSON" but `<grounding_rules>` says "inline bracketed citations" which can't fit in JSON.
**Detection:** cross-tag consistency check in `PROMPT_BUILDER`.
**Recovery:** citation format adjusted per output format (JSON gets a `citations` field; markdown gets inline brackets).
### 10.8 Grounding for self-referential Runs
**Failure:** A Run about CEE itself ("how does the classifier work") needs grounding in the bible. The engine doesn't recognize bible sections as sources.
**Detection:** source enumeration empty for self-referential Runs.
**Recovery:** added `bible_section` source type (already in §5.1); pattern detector recognizes self-referential goals.
### 10.9 Skill grounding signal ignored
**Failure:** A Skill declares `grounding_required: true` but the engine doesn't fire `needs_grounding`.
**Detection:** Skill-loading logic must propagate the flag.
**Recovery:** classifier reads Skill grounding flags during Skill resolution feedback; flag is set even after classification if Skills demand it.
### 10.10 Prohibition catalog drift from real fabrication patterns
**Failure:** new fabrication patterns emerge (e.g., a new framework's API methods that Claude hallucinates); not in catalog.
**Detection:** OPERATOR catches in output.
**Recovery:** catalog is editable; new patterns added; back-test against recent Runs.
---
## 11. Build Notes for Claude Code
- **Engine location:** `~/cee/grounding/engine.py`. Public function: `derive_grounding(intent_object, classification, agent_plan, skill_set) -> GroundingDeclaration`.
- **Pattern catalog:** `~/cee/grounding/prohibition_patterns.py`. Each pattern has a regex, a prohibition text, and a `task_types` filter (which task_types the pattern applies to).
- **Source extractors:** `~/cee/grounding/extractors/` — one module per source type (attachment, path, URL, etc.).
- **Validators (Phase 2):** `~/cee/grounding/validators/` — citation extractor, claim extractor (LLM-backed), prohibition violation scanner.
- **Renderer:** `~/cee/grounding/renderer.py` — produces XML for the `<grounding_rules>` tag from a `GroundingDeclaration`. Called by `PROMPT_BUILDER`'s `grounding_rules.j2` template.
- **Tests:** unit tests per source type, per prohibition pattern. Golden Runs include grounding declarations and (for Phase 2) sample executor outputs to validate.
- **Override CLI:** `cee run --no-grounding` triggers Rule 6 of section 11 (the override path). Audit log explicit.
- **Determinism:** all LLM calls in this engine (claim extraction, validation) use temperature 0 and fixed system prompts at `~/cee/prompts/grounding_*.txt`.
---
## 12. Definition of Done
This page is complete — and the grounding system is unblocked for build — when:
- [ ] The closed source-type enum in §5.1 is reflected in `~/cee/schemas/grounding_declaration.json`.
- [ ] Prohibition pattern catalog at `~/cee/grounding/prohibition_patterns.py` covers all common fabrication risks.
- [ ] Source enumeration handles all 8 source types.
- [ ] `<grounding_rules>` tag renders correctly for every `task_type` × source pattern combination.
- [ ] Halt-with-`grounding_unsourceable` is reachable and tested.
- [ ] Override path is reachable and clearly logged.
- [ ] Phase 2 validators exist for citation presence, citation correctness, and prohibition violations — even stub implementations.
- [ ] Edge cases in §9 each have a test or documented recovery.
- [ ] Failure modes in §10 each have a corresponding test or documented recovery.
- [ ] Boot's consistency check verifies the source-type enum and pattern catalog are in sync with this page.
---
## 13. Final Statement
Hallucination is the silent failure mode of LLM systems — outputs that look right but aren't. CEE defends against it by making the executor's allowed reality explicit: declared sources, prohibited inferences, required citations. The user gets something better than a confident answer; they get an answer with a clear boundary between "this is grounded" and "this exceeds the source." When the boundary can't be drawn — when no sources exist — CEE halts rather than fabricates. This is the hard rule that makes the rest of the system trustworthy.
