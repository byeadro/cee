---
notion_section: 09
notion_title: 09 — PROMPT GENERATOR ENGINE
mirrored_at: 2026-04-30
---

# 09 — PROMPT GENERATOR ENGINE
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the implementation contract for the `PROMPT_BUILDER` module. Section 05 defined what a FinalPrompt looks like and the rules it follows. This page defines the engine that produces it — the modules, the templates, the determinism guarantees, and the failure recovery. Where 05 is "what the artifact contains," this page is "what the code does to construct it."
---
## 1. What This Is
The Prompt Generator Engine is `PROMPT_BUILDER` — the module that consumes the upstream artifact bundle (`IntentObject`, `Classification`, `AgentPlan`, `SkillSet`, `ExecutionStrategy`) and produces the `FinalPrompt` artifact. It is the next-to-last step of the Run pipeline; only `SAFETY_GATE` runs after it.
This page defines:
- The engine's module structure and public interface
- The template architecture (per-tag Jinja templates, no string concatenation outside)
- The construction order and determinism guarantees
- The internal Claude calls (when, how, with what constraints)
- The validation pipeline (per-tag validators + final schema check)
- The chunking implementation for over-budget prompts
- The replay equivalence guarantee
Section 05 is the spec the engine implements. This page is how it actually gets built.
---
## 2. Why This Matters
Without this page, the rules in 05 are guidance but not infrastructure. With it:
- The engine is a pure function from artifact bundle to FinalPrompt — replayable, testable, deterministic.
- Templates are the only place strings get assembled, so the rules in 05 can't be silently bypassed by an `f"<tag>{x}</tag>"` somewhere in the codebase.
- Internal Claude calls are bounded — temperature 0, fixed system prompt, fixed parameter list — so they don't introduce drift.
- Chunking is a clean separate phase, not interleaved with construction.
The combination of "rules in 05 + engine in 09" makes "every prompt is perfect" a property the codebase enforces, not a goal.
---
## 3. Core Requirements
The engine MUST:
1. Be a pure function: `build(artifacts: ArtifactBundle, target: ExecutorTarget) -> FinalPrompt`. No global state, no side effects beyond the returned artifact.
2. Construct the FinalPrompt by iterating the closed tag list in §5.1 of section 05, in order, no exceptions.
3. Render each tag exclusively through its Jinja template at `~/cee/prompt_builder/templates/<tag_name>.j2`.
4. Validate each tag's content against its per-tag validator before incorporating it into the FinalPrompt buffer.
5. Validate the assembled FinalPrompt against `~/cee/schemas/final_prompt.json` before write.
6. Count tokens against the target executor's budget (minus 4000-token safety buffer) and chunk if over.
7. Produce byte-identical output for byte-identical input + boot state. Replay-equivalent.
8. Use temperature 0 and a fixed system prompt for any internal Claude call.
9. Emit a structured construction log to `~/cee/runs/<run_id>/prompt_builder.log` showing every tag rendered, every validation passed, every Claude call made.
10. Halt the Run cleanly with a typed exception when any step fails — no partial output reaches the user.
The engine MUST NOT:
- Construct FinalPrompts via direct string formatting outside templates.
- Make Claude calls with non-zero temperature.
- Skip validation on any tag.
- Modify upstream artifacts. They are read-only.
- Cache state across Runs. Every Run starts cold.
---
## 4. System Rules
**Rule 1 — Templates are the only string assemblers.**
Every piece of FinalPrompt text comes from a Jinja template at `~/cee/prompt_builder/templates/`. The builder iterates tags, renders each template, and concatenates. Other places that produce strings (verbose error messages, log lines) are not part of the FinalPrompt.
**Rule 2 — Closed template set.**
One template per tag in section 05 §5.1. Adding a tag requires both bible edits (section 05 + this page) and a new template file. No template, no tag.
**Rule 3 — Pure functions.**
Every render function `render_<tag>(artifacts, target) -> str` is a pure function: same inputs always produce the same output. Side effects forbidden.
**Rule 4 — One internal Claude call per FinalPrompt, max.**
Most rendering is deterministic from artifacts. Only `<role>` rendering may invoke Claude (to phrase the role sentence elegantly), and only if the artifact-derived sentence reads as awkward. Even then, temperature 0 and fixed prompt. The single call per FinalPrompt cap prevents drift.
**Rule 5 — Validation runs at three levels.**
- Per-tag content validation after each render.
- Cross-tag consistency check after all renders (e.g., `<agents>` and `<role>` agree on primary).
- Whole-artifact schema validation before write.
**Rule 6 — Chunking is a post-construction transform.**
The builder constructs the full FinalPrompt first, then checks length. If over budget, the chunker splits along defined seams. Construction and chunking are separate phases.
**Rule 7 — Construction log is required.**
Every tag's render is logged with its inputs (artifact references) and output length. The log is what makes replay diagnostics possible.
**Rule 8 — Templates declare their own conditionality.**
Each template exports `should_render(artifacts) -> bool`. The builder calls this to decide whether to invoke the template at all. Conditional logic is colocated with the template.
**Rule 9 — Builder failure stops the Run.**
A render error, a validation error, or a chunking error halts the pipeline with a typed exception. SAFETY_GATE never sees a malformed FinalPrompt.
**Rule 10 — Replay equivalence is a contract.**
The builder is replay-tested. A Run replayed with the same upstream artifacts must produce a byte-identical FinalPrompt. Drift is a bug.
---
## 5. Detailed Workflow — The Engine
### 5.1 Module structure
```javascript
~/cee/prompt_builder/
├── __init__.py
├── builder.py                 # public `build()` entry point
├── tag_order.py               # canonical ordered tag list
├── templates/
│   ├── final_prompt.j2        # outer wrapper
│   ├── target_executor.j2
│   ├── context.j2
│   ├── role.j2
│   ├── task.j2
│   ├── agents.j2
│   ├── skills.j2
│   ├── execution_plan.j2
│   ├── constraints.j2
│   ├── grounding_rules.j2
│   ├── assumptions_made.j2
│   ├── output_format.j2
│   ├── stop_conditions.j2
│   ├── safety_banner.j2
│   └── run_metadata.j2
├── conditionality/
│   ├── __init__.py            # `should_render` per tag
│   └── rules.py
├── validators/
│   ├── __init__.py
│   ├── content/               # per-tag content validators
│   │   ├── target_executor.py
│   │   ├── context.py
│   │   ├── role.py
│   │   └── ...
│   ├── consistency.py         # cross-tag consistency
│   └── schema.py              # whole-artifact schema check
├── chunker.py                 # over-budget splitting
├── token_counter.py           # token counting per executor
├── llm.py                     # the single optional internal Claude call
└── construction_log.py        # the per-tag log writer
```
### 5.2 The public interface
```python
def build(
    artifacts: ArtifactBundle,
    target: ExecutorTarget,
    suppress_metadata: bool = False
) -> FinalPrompt:
    """Construct a FinalPrompt from the artifact bundle for the given target.
    
    Returns a FinalPrompt object (single-chunk or multi-chunk depending on budget).
    Raises PipelineHalt with halt_type='prompt_schema_violation' or 'prompt_too_large' on failure.
    """
```
`ArtifactBundle` is a dataclass holding `IntentObject`, `Classification`, `AgentPlan`, `SkillSet`, `ExecutionStrategy`, plus the run_id and timestamp.
### 5.3 The construction algorithm
```python
def build(artifacts, target, suppress_metadata=False):
    construction_log = ConstructionLog(artifacts.run_id)
    rendered_tags = []
    
    for tag_name in TAG_ORDER:  # from tag_order.py
        if tag_name == "run_metadata" and suppress_metadata:
            continue
        
        if not should_render(tag_name, artifacts):
            construction_log.skip(tag_name, reason="conditionality")
            continue
        
        # Render
        try:
            rendered = render_tag(tag_name, artifacts, target)
        except Exception as e:
            raise PipelineHalt("prompt_schema_violation", {
                "tag": tag_name,
                "error": str(e)
            })
        
        # Per-tag content validation
        validator = content_validators.get(tag_name)
        if validator:
            validation_result = validator(rendered, artifacts)
            if not validation_result.valid:
                raise PipelineHalt("prompt_schema_violation", {
                    "tag": tag_name,
                    "violations": validation_result.errors
                })
        
        construction_log.render(tag_name, rendered)
        rendered_tags.append((tag_name, rendered))
    
    # Cross-tag consistency
    consistency_check(rendered_tags, artifacts)  # raises on failure
    
    # Wrap in <final_prompt>
    body = "\n".join(rendered for _, rendered in rendered_tags)
    final_prompt_xml = render_tag("final_prompt", artifacts, target, body=body)
    
    # Whole-artifact schema validation
    schema_validate(final_prompt_xml)  # raises on failure
    
    # Token count and chunking
    token_count = count_tokens(final_prompt_xml, target)
    budget = budget_for(target) - SAFETY_BUFFER  # SAFETY_BUFFER = 4000
    
    if token_count > budget:
        chunks = chunk(final_prompt_xml, budget, artifacts)
        return FinalPrompt(chunks=chunks, target=target, run_id=artifacts.run_id)
    
    return FinalPrompt(chunks=[final_prompt_xml], target=target, run_id=artifacts.run_id)
```
### 5.4 The render functions
Each tag's render function is in `templates/<tag_name>.j2` plus a small Python wrapper in `templates/__init__.py`. The wrapper:
1. Loads the Jinja template.
2. Builds a context dict from `artifacts` and `target`.
3. Renders.
4. Returns the rendered string.
Example wrapper:
```python
def render_role(artifacts, target):
    template = env.get_template("role.j2")
    context = {
        "primary_agent": artifacts.agent_plan.primary,
        "domain": artifacts.intent_object.domain,
        "task_type": artifacts.classification.task_type,
    }
    return template.render(**context)
```
The template itself is constrained to use only the context keys declared in the wrapper. No template reads from globals, environment, or filesystem.
### 5.5 The internal Claude call
The single optional Claude call is in `llm.py`. It is invoked only when:
- The tag being rendered is `<role>` AND
- The artifact-derived role sentence is flagged by a heuristic as awkward (e.g., agent posture and domain don't combine into natural English).
The call:
```python
def smooth_role_sentence(rough_sentence: str) -> str:
    """Use Claude to phrase a role sentence elegantly. Pure function with temperature 0."""
    response = anthropic_client.messages.create(
        model=config.classifier_model,  # same model classifier uses
        max_tokens=100,
        temperature=0,
        system=load_fixed_prompt("~/cee/prompts/prompt_builder_system.txt"),
        messages=[{"role": "user", "content": f"Rephrase this role sentence in natural English, preserving meaning exactly: {rough_sentence}"}]
    )
    return response.content[0].text.strip()
```
If this call fails (network, rate limit), the builder falls back to the rough sentence — no halt. The fallback is logged.
### 5.6 The validators
Three layers:
**Per-tag content validators** — one per tag at `validators/content/<tag>.py`. Each is a function `validate(rendered: str, artifacts: ArtifactBundle) -> ValidationResult`. Examples:
- `target_executor.py`: rendered value must be one of the closed enum strings.
- `task.py`: rendered must be a single sentence; must be imperative; must not contain hedge words ("maybe", "could you", "if possible").
- `constraints.py`: if `IntentObject.constraints` is empty, rendered must contain "None"; otherwise must list each constraint.
**Cross-tag consistency** — `validators/consistency.py`. Checks:
- `<role>` and `<agents>`'s primary refer to the same agent.
- `<execution_plan>` step count matches `ExecutionStrategy.steps` length.
- `<constraints>` includes everything in `IntentObject.constraints`.
- Conditional tags appear iff their `should_render` returns true.
**Whole-artifact schema validation** — `validators/schema.py`. Validates the assembled XML string against `~/cee/schemas/final_prompt.json`. Catches structural issues: malformed XML, missing required tags, tags out of order.
### 5.7 The chunker
`chunker.py` splits over-budget FinalPrompts into ordered chunks. Algorithm:
```python
def chunk(final_prompt_xml: str, budget: int, artifacts) -> list[str]:
    # 1. Identify splittable seams: <context> and <execution_plan>
    seams = find_seams(final_prompt_xml)
    
    # 2. Compute total length and target chunk count
    total = count_tokens(final_prompt_xml, artifacts.target_executor)
    chunk_count = ceil(total / budget)
    target_size = total / chunk_count
    
    # 3. Split <context> into roughly-equal pieces, preserving attachments as units
    context_pieces = split_context(seams.context, target_size_for_context)
    
    # 4. For each chunk: include all non-splittable tags + one piece of context + relevant execution_plan steps
    chunks = []
    for i, piece in enumerate(context_pieces):
        chunk_xml = build_chunk(
            chunk_n=i+1,
            chunk_total=len(context_pieces),
            non_splittable_tags=seams.non_splittable,
            context_piece=piece,
            execution_steps=relevant_steps_for(piece, seams.execution_plan)
        )
        chunks.append(chunk_xml)
    
    # 5. Add chunking_instructions to first chunk
    chunks[0] = add_chunking_instructions(chunks[0], len(chunks))
    
    return chunks
```
Chunks are independent in structure but related by `<chunk_metadata>` which tells the executor to wait for all before starting.
If chunking can't reduce any chunk below budget (e.g., a single attachment is larger than budget), halt with `prompt_too_large`.
### 5.8 The construction log
Every render and every validation outcome logged to `~/cee/runs/<run_id>/prompt_builder.log` in JSONL:
```javascript
{"ts": "...", "event": "tag_skip", "tag": "agents", "reason": "conditionality"}
{"ts": "...", "event": "tag_render", "tag": "role", "input_refs": ["agent_plan.primary", "intent_object.domain"], "output_length": 78}
{"ts": "...", "event": "validation_pass", "tag": "role", "validator": "content"}
{"ts": "...", "event": "claude_call", "purpose": "smooth_role_sentence", "input_length": 78, "output_length": 82}
{"ts": "...", "event": "consistency_pass"}
{"ts": "...", "event": "schema_pass"}
{"ts": "...", "event": "token_count", "count": 1840, "budget": 196000, "chunked": false}
{"ts": "...", "event": "build_complete"}
```
This log is what `cee replay <run_id>` reads to reconstruct the construction trace.
### 5.9 Determinism guarantees
The engine's determinism rests on five conditions:
1. **Pure render functions.** Each render function depends only on its declared inputs.
2. **Temperature 0 for any LLM call.** Including the optional `<role>` smoothing.
3. **Stable input ordering.** When iterating Skill lists, agent lists, etc., the order is stable (sorted by slug).
4. **No system clock reads.** All timestamps come from `RawInput.timestamp` (frozen at capture).
5. **No environment variable reads at render time.** Configuration is loaded once at module import.
A CI test in section 18 runs the same artifact bundle through the engine 10 times and asserts byte-identical output.
---
## 6. Data / Inputs Needed
### 6.1 Required inputs
- `IntentObject`, `Classification`, `AgentPlan`, `SkillSet`, `ExecutionStrategy` (from prior pipeline steps)
- `ExecutorTarget` (one of `claude_ai | claude_code | api`)
- `~/cee/schemas/final_prompt.json`
- `~/cee/config/models.json` (for token budgets per executor)
- `~/cee/prompts/prompt_builder_system.txt` (for the optional Claude call)
### 6.2 Configuration
- `~/.cee/config.toml` `[prompt_builder]` section:
	- `safety_buffer_tokens` (default 4000)
	- `enable_role_smoothing` (default true)
	- `chunking_strategy` (default "context_then_plan"; alternatives planned for later)
### 6.3 Templates
All Jinja templates at `~/cee/prompt_builder/templates/`. Locked down — templates are part of the bible, not user-editable.
---
## 7. Outputs Produced
### 7.1 Single-chunk FinalPrompt
Standard case. One XML block written to `~/cee/runs/<run_id>/prompt.xml`.
### 7.2 Multi-chunk FinalPrompt
Over-budget case. Multiple XML blocks at `prompt_1.xml`, `prompt_2.xml`, ..., plus `prompt_manifest.json` listing them.
### 7.3 Construction log
Always produced at `~/cee/runs/<run_id>/prompt_builder.log` in JSONL.
### 7.4 Audit log entries
Every build invocation logged in `~/cee/audit/roles.log`.
---
## 8. Agent + Skill Implications
### 8.1 Agents shape `<role>` and `<agents>`
The primary agent's frontmatter (posture, domain, capabilities) feeds the `<role>` template. Multi-agent Runs add the `<agents>` tag with composition pattern from section 06 §5.4.
### 8.2 Skills are referenced by path, never inlined
Per section 05 §8.3. The `<skills>` template renders paths only. Inlining would explode token budgets.
### 8.3 The engine doesn't validate Skills or agents
It validates that they exist on disk (via path checks) and that `AgentPlan`/`SkillSet` reference existing files. It does not validate the *content* of Skills and agents — that's the registry's job at boot.
---
## 9. Edge Cases
**EC1 — ****`IntentObject.implicit_assumptions`**** is empty.**
`<assumptions_made>` template's `should_render` returns false; tag skipped.
**EC2 — ****`IntentObject.constraints`**** is empty.**
`<constraints>` template renders with content "None." — not skipped (constraints is required).
**EC3 — Agent has no ****`domain`**** (e.g., ****`task-orchestrator`****).**
`<role>` template falls back to a domain-agnostic phrasing.
**EC4 — ****`AgentPlan`**** has only a primary.**
`<agents>` template's `should_render` returns false; tag skipped. Section 05 §5.1 marks `<agents>` as conditional.
**EC5 — ****`SkillSet`**** is empty.**
`<skills>` template's `should_render` returns false; tag skipped.
**EC6 — ****`flags.needs_grounding`**** is true but no specific sources are identified.**
`<grounding_rules>` template renders with "Sources: as referenced in `<context>`. Inferences beyond `<context>` are prohibited."
**EC7 — Target is ****`api`**** but Phase 2 not implemented.**
Builder rejects target with explicit error before construction starts.
**EC8 — Construction log directory doesn't exist.**
Pipeline driver ensures the run directory exists before invoking the builder. Builder fails fast if not.
**EC9 — Internal Claude call hits rate limit.**
Fallback to rough sentence; warning logged. Run continues.
**EC10 — Token counter disagrees between Phase 1 and Phase 2 (different tokenizers).**
Tokenizer is locked per `target_executor`. Phase 1 (paste-based targets) uses the tokenizer that matches Claude's. Phase 2 API can use the Anthropic SDK's `count_tokens` directly.
**EC11 — A consistency check fails (e.g., ****`<role>`****'s primary doesn't match ****`<agents>`****'s primary).**
Halt with structured error pointing to both tags. Bug indicates either AgentPlan corruption or a render function bug.
**EC12 — Chunker produces a chunk that's still over budget.**
Halt with `prompt_too_large`. User must reduce attachments or split the task.
---
## 10. Failure Modes
### 10.1 Template missing
**Failure:** a tag's template file is missing.
**Detection:** Jinja loader throws on first render attempt.
**Recovery:** halt with `prompt_schema_violation` naming the missing template. Boot's layout validator should catch this earlier.
### 10.2 Template references undeclared variable
**Failure:** a template uses a context key the wrapper doesn't pass.
**Detection:** Jinja `UndefinedError`.
**Recovery:** halt; bug in template-wrapper sync.
### 10.3 Per-tag validator regression
**Failure:** validator passes content that doesn't match the tag's content rule.
**Detection:** golden Run tests + section 18 explicit validator tests.
**Recovery:** validator strengthened; tests updated.
### 10.4 Cross-tag consistency drift
**Failure:** `<role>` and `<agents>` disagree.
**Detection:** consistency check.
**Recovery:** halt; bug usually in `<role>` template not pulling from `AgentPlan.primary`.
### 10.5 Schema validation fails after consistency passes
**Failure:** assembled XML is malformed (e.g., template emitted unescaped `<`).
**Detection:** schema validator.
**Recovery:** halt; identify which template emitted bad XML; sanitization rule added.
### 10.6 Token counter inaccurate
**Failure:** counter says 195K, actual is 205K, executor rejects paste.
**Detection:** user reports paste failure; OPERATOR feeds back.
**Recovery:** counter adjusted; safety buffer increased.
### 10.7 Chunking corrupts XML
**Failure:** chunker splits inside a tag, producing invalid XML in chunks.
**Detection:** post-chunk schema validation per chunk.
**Recovery:** halt; chunker logic fixed; seams tightened.
### 10.8 Replay drift
**Failure:** same artifact bundle produces different FinalPrompts.
**Detection:** replay equivalence tests.
**Recovery:** verify temperature 0; verify input ordering stable; investigate any new non-determinism.
### 10.9 Internal Claude call drift
**Failure:** the smoothing call returns different output for same input on different days.
**Detection:** golden Run tests.
**Recovery:** model version pinned in config; system prompt locked down further if needed; or smoothing disabled.
### 10.10 Construction log corruption
**Failure:** log file truncated or unparseable.
**Detection:** log validator.
**Recovery:** log rebuilt from artifact (best effort); Run still completes; warning logged.
---
## 11. Build Notes for Claude Code
- **Engine entry point:** `~/cee/prompt_builder/builder.py`. The `build()` function is the only public API.
- **Tag order constant:** `~/cee/prompt_builder/tag_order.py`. A single Python list. The list in this file must match section 05 §5.1 exactly. Boot validates.
- **Template loader:** Jinja2 environment initialized once at module import with `~/cee/prompt_builder/templates/` as the search path. `autoescape=True` for XML output.
- **Validator registry:** `~/cee/prompt_builder/validators/__init__.py` exports a dict mapping tag names to validator functions.
- **Token counter:** `~/cee/prompt_builder/token_counter.py`. Uses `tiktoken` for paste-target executors (approximating Claude's tokenization) and Anthropic SDK's `count_tokens` for API target.
- **Chunker tests:** include adversarial inputs — a single attachment larger than budget, an `IntentObject.goal` that's verbose, etc.
- **Determinism CI:** a test runs the same bundle through the builder 10 times, asserts identical output. Failure blocks merge.
- **Replay tests:** golden Runs in `~/cee/runs/golden/` are regenerated through the builder and asserted equal to committed expected outputs. Drift on any tag means a regression.
- **No ****`f"<tag>{x}</tag>"`**** anywhere.** A linter rule in `~/cee/tests/lint/` rejects any string interpolation that looks like XML construction outside `templates/`.
- **Construction log writer:** `~/cee/prompt_builder/construction_log.py`. Appends JSONL. Rotated per Run (each Run gets its own log, no cross-Run accumulation).
---
## 12. Definition of Done
This page is complete — and the engine is unblocked for build — when:
- [ ] `~/cee/prompt_builder/builder.py` exposes the `build()` function with the signature in §5.2.
- [ ] One Jinja template per tag in section 05 §5.1.
- [ ] One content validator per tag.
- [ ] Cross-tag consistency check covers role/agents, execution_plan/strategy, constraints/intent.
- [ ] Whole-artifact schema validator passes for all golden Runs.
- [ ] Chunker produces valid chunked output for over-budget Runs.
- [ ] Determinism CI passes.
- [ ] Construction log captures every render, validation, and Claude call.
- [ ] No string interpolation that looks like XML construction outside templates (linter enforced).
- [ ] Replay of all golden Runs produces byte-identical FinalPrompts.
---
## 13. Final Statement
The Prompt Generator Engine is the codification of section 05's rules. Where the rules say "every required tag must be present," the engine enforces it via tag iteration. Where the rules say "deterministic output," the engine guarantees it via pure render functions and temperature 0. Where the rules say "fail loud, not silent," the engine raises typed exceptions that halt the pipeline. The engine is not creative; it is mechanical. That's the point.
