---
notion_section: 18
notion_title: 18 — TESTING + QUALITY FRAMEWORK
mirrored_at: 2026-04-30
---

# 18 — TESTING + QUALITY FRAMEWORK
> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the consolidated testing strategy. Every prior section in this bible has at least one reference that says "tests in section 18" — this page is where those obligations are collected, organized, and turned into a runnable test suite. Quality in CEE is a property the test suite enforces; this page defines the suite.
---
## 1. What This Is
CEE is a deterministic system: same inputs produce same outputs. Determinism is testable. Section 18 defines:
- The four test categories (unit, integration, golden, adversarial) and what each owns
- Every test obligation the bible has accumulated, mapped to the test category that owns it
- The test infrastructure: pytest layout, fixtures, markers, CI configuration
- Coverage requirements per module (what percentage of code paths must be exercised)
- The replay-equivalence test that runs golden Runs end-to-end and asserts byte-identical output
- The determinism CI test that runs critical modules N times against the same input and asserts identical output
- The release gate: which tests must pass before any code merge
This page is the test plan. Section 17's golden Runs are the inputs. The test suite at `~/cee/tests/` is the implementation.
---
## 2. Why This Matters
Without a defined testing framework:
- Every test obligation in prior sections becomes an open item with no owner.
- Coverage drifts; modules become untested without anyone noticing.
- Determinism regressions slip in (a tweak to a prompt, a non-pinned model version) and are caught only after a Run drifts mysteriously.
- New contributors don't know what "merging is safe" means.
The test suite is what makes the bible's invariants ("deterministic," "schema-validated," "loud failure") survive contact with code changes. Without it, the bible is documentation; with it, the bible is a contract the codebase honors.
---
## 3. Core Requirements
The testing framework MUST:
1. Test every closed enum in the bible — adding an enum value without test coverage halts CI.
2. Test every halt type in section 19 — each halt must be reachable from at least one test input.
3. Test every failure mode listed across sections 00–16 (each section has a §10 — those are inputs to this page).
4. Replay every example in section 17 through the pipeline and assert byte-identical output.
5. Run determinism checks on `INTERPRETER`, `CLASSIFIER`, `PROMPT_BUILDER`, `OUTPUT_FORMAT_ENGINE`, and `GROUNDING_ENGINE` — modules required to be deterministic.
6. Validate every Skill in `~/cee/skills/` and every agent in `~/cee/.claude/agents/` using their respective file validators.
7. Run on every commit via CI; block merges if any test fails.
8. Provide a fast subset (`pytest -m fast`) that runs in under 60 seconds for OPERATOR's local feedback loop.
The testing framework MUST NOT:
- Make production calls to the Anthropic API in CI by default. API tests use mocked responses.
- Write to the OPERATOR's actual `~/cee/`, `~/SecondBrain/`, or Notion. Tests use isolated temp directories.
- Assume Claude Code is installed — tests cover CEE's logic, not Claude Code's.
- Be skipped because of "flakiness." A flaky test is a determinism bug; treat as a failure.
---
## 4. System Rules
**Rule 1 — Four test categories.**
- **Unit tests:** isolated module tests. No filesystem, no LLM calls (or mocked).
- **Integration tests:** multi-module flows in isolated temp dirs.
- **Golden tests:** end-to-end replays of section 17 examples.
- **Adversarial tests:** intentionally bad inputs that should halt or fail loudly.
**Rule 2 — Determinism is non-negotiable.**
A determinism test runs each deterministic module N=10 times against the same input and asserts identical output. N is configurable (lower in CI for speed, higher in nightly).
**Rule 3 — Mocked LLM calls in CI.**
The Anthropic SDK is mocked. Mocks return canned responses derived from golden Runs. Real API calls are reserved for nightly regression suites or manual verification.
**Rule 4 — Test isolation.**
Each test that touches filesystem uses `tmp_path` from pytest. No test reads or writes the OPERATOR's real directories.
**Rule 5 — Coverage thresholds.**
Module coverage (from `coverage.py`) must be ≥85% for each module under `~/cee/`. CI fails on drop below.
**Rule 6 — Schema tests are a category of their own.**
For every JSON schema in `~/cee/schemas/`, tests assert: valid examples pass; invalid examples fail; schema migration scripts handle version bumps.
**Rule 7 — Linter tests as code.**
The "no `f`-string XML construction outside templates" rule from section 09 is a test, not just a guideline. Same for "no string concatenation of paths outside `paths.py`" from section 04.
**Rule 8 — Test markers are required.**
Every test has at least one marker: `@pytest.mark.fast` (under 1 second), `@pytest.mark.slow` (over 1 second), `@pytest.mark.integration`, `@pytest.mark.golden`, `@pytest.mark.adversarial`. Default `pytest` runs all; markers allow filtering.
**Rule 9 — One test, one assertion class.**
A test asserts one behavior. Compound tests are split. This makes failure messages diagnostic.
**Rule 10 — Test names describe what they prove.**
`test_classifier_picks_BUILD_for_imperative_create_verb` is good. `test_classifier_1` is bad. The name tells the next reader what broke when it fails.
---
## 5. Detailed Workflow — The Test Plan
### 5.1 Test categories and what they cover
#### 5.1.1 Unit tests (`~/cee/tests/unit/`)
One subdirectory per module. Tests are isolated — no filesystem, no LLM calls (mocked), no cross-module imports beyond what's natural.
```javascript
~/cee/tests/unit/
├── test_interpreter/
│   ├── test_intent_object_schema.py
│   ├── test_ambiguity_score_calculation.py
│   └── test_implicit_assumptions_detection.py
├── test_classifier/
│   ├── test_task_type_assignment.py
│   ├── test_complexity_components.py
│   ├── test_tier_thresholds.py
│   ├── test_flag_triggers.py
│   ├── test_precedence_order.py
│   └── test_ambiguity_halt.py
├── test_agent_selector/
├── test_skill_engine/
├── test_strategy_builder/
├── test_prompt_builder/
│   ├── test_each_tag_renders.py
│   ├── test_tag_order.py
│   ├── test_conditional_tags.py
│   ├── test_chunker.py
│   └── test_validators_per_tag.py
├── test_safety_gate/
│   ├── test_redaction_patterns.py
│   ├── test_destructive_gate.py
│   ├── test_injection_scanner.py
│   └── test_audit_hash_chain.py
├── test_grounding/
├── test_output_format/
├── test_persistence/
│   ├── test_atomic_writes.py
│   ├── test_filesystem_writer.py
│   ├── test_obsidian_writer.py
│   └── test_notion_writer.py
├── test_executor/
│   ├── test_paste_executor.py
│   └── test_api_executor.py  # mocked
├── test_skill_files/
│   ├── test_validator_per_rule.py
│   └── test_seed_skills_validate.py
├── test_agent_files/
│   ├── test_validator_per_rule.py
│   └── test_seed_agents_validate.py
└── test_schemas/
    ├── test_every_schema_loads.py
    ├── test_valid_examples_pass.py
    └── test_invalid_examples_fail.py
```
Coverage target: ≥85% per module.
#### 5.1.2 Integration tests (`~/cee/tests/integration/`)
Multi-module flows in isolated temp dirs. These test the pipeline driver, the boot sequence, the persistence chain, and the substrate writers in combination.
```javascript
~/cee/tests/integration/
├── test_boot_sequence.py            # full boot from a fresh ~/cee/ template
├── test_pipeline_low_complexity.py  # full pipeline, LOW Run
├── test_pipeline_medium_complexity.py
├── test_pipeline_high_complexity.py
├── test_pipeline_extreme_complexity.py
├── test_clarification_cycle.py      # halt → answer → resume
├── test_replay_cycle.py
├── test_promotion_cycle.py
├── test_persistence_chain.py        # filesystem → Obsidian → Notion (mocked Notion)
├── test_safety_gate_chain.py        # redaction + destructive gate end-to-end
├── test_grounding_end_to_end.py
├── test_format_validation_phase2.py # mocked API, validates verdict
└── test_cross_section_consistency.py # boot's consistency check on bible mirror
```
#### 5.1.3 Golden tests (`~/cee/tests/golden/`)
Replays of section 17's 8 examples. Each test loads the example's `RawInput`, runs it through the pipeline, and asserts byte equality with the committed expected `FinalPrompt`.
```javascript
~/cee/tests/golden/
├── test_ex_build_low_rls_policy.py
├── test_ex_analyze_medium_utility_bill.py
├── test_ex_debug_medium_failing_test.py
├── test_ex_write_medium_investor_email.py
├── test_ex_research_high_niche_vertical.py
├── test_ex_transform_medium_csv_to_json.py
├── test_ex_decide_high_bootstrap_vs_raise.py
└── test_ex_orchestrate_extreme_build_feature.py
```
Each test:
```python
def test_ex_build_low_rls_policy():
    raw_input = load_fixture("ex-build-low-rls-policy")
    result = run_pipeline(raw_input)
    expected = load_expected("ex-build-low-rls-policy")
    assert result.final_prompt == expected
```
If the test fails, either: (a) the bible changed (and the example needs regeneration), or (b) the code regressed. Failure messages include a diff between produced and expected output.
#### 5.1.4 Adversarial tests (`~/cee/tests/adversarial/`)
Intentionally bad inputs. Each test asserts the system halts loudly with the expected halt type, rather than producing degraded output.
```javascript
~/cee/tests/adversarial/
├── test_input_one_word.py             # ambiguity_score = 1.0 → halt for clarification
├── test_input_empty.py                # InputValidationError
├── test_input_contradicts_itself.py   # contradiction_note in FinalPrompt
├── test_attachment_injection.py       # injection scanner halts
├── test_hidden_unicode_attachment.py
├── test_cee_tag_impersonation.py
├── test_redaction_pattern_in_input.py # SAFETY_GATE redacts
├── test_destructive_input_no_confirm.py # halts at gate
├── test_grounding_no_sources.py       # halt with grounding_unsourceable
├── test_skill_conflict.py             # generated Skill collides with existing
├── test_agent_conflict.py             # two primaries selected
├── test_token_budget_exceeded.py      # chunker fires
├── test_chunker_cant_split.py         # halt with prompt_too_large
├── test_invalid_target_executor.py    # rejected at validation
├── test_phase2_disabled_but_targeted.py  # explicit error
├── test_bible_mirror_stale.py         # boot halts
├── test_bible_cross_section_drift.py  # boot's consistency check fails
├── test_skill_invalid_frontmatter.py  # generation retries then halts
├── test_agent_body_posture_mismatch.py # LLM validator rejects
└── test_audit_hash_chain_tampered.py  # cee audit-verify reports break
```
#### 5.1.5 Schema tests (subset of unit tests)
`~/cee/tests/unit/test_schemas/test_every_schema_loads.py`:
```python
@pytest.mark.fast
@pytest.mark.parametrize("schema_path", list_all_schemas())
def test_schema_loads(schema_path):
    """Every JSON schema must parse and be a valid JSON Schema."""
    with open(schema_path) as f:
        schema = json.load(f)
    jsonschema.Draft7Validator.check_schema(schema)
```
Plus per-schema valid/invalid example tests at `~/cee/tests/fixtures/schemas/<schema_name>/valid/` and `invalid/`.
### 5.2 Determinism tests
The most important test category. At `~/cee/tests/determinism/`:
```python
DETERMINISTIC_MODULES = [
    "interpreter",
    "classifier",
    "prompt_builder",
    "output_format_engine",
    "grounding_engine",
]

@pytest.mark.determinism
@pytest.mark.parametrize("module", DETERMINISTIC_MODULES)
@pytest.mark.parametrize("input_fixture", list_determinism_inputs())
def test_module_determinism(module, input_fixture, n=10):
    """Run the module N times against the same input; assert identical output."""
    outputs = []
    for _ in range(n):
        out = invoke_module(module, input_fixture)
        outputs.append(out)
    
    first = outputs[0]
    for i, out in enumerate(outputs[1:], start=1):
        assert out == first, f"Determinism break at iteration {i+1}"
```
`n` is 10 in CI, 100 in nightly. Failure indicates either: temperature ≠ 0 somewhere, system-clock dependency, env var read at runtime, or input-ordering instability.
### 5.3 Coverage requirements
```toml
# pyproject.toml or setup.cfg

[tool.coverage.report]
fail_under = 85
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]

[tool.coverage.run]
source = ["cee"]
omit = [
    "cee/.template/*",
    "cee/tests/*",
]
```
Per-module coverage check:
```javascript
pytest --cov=cee --cov-report=term --cov-fail-under=85
```
Per-module specific minimums:
<table header-row="true">
<tr>
<td>Module</td>
<td>Minimum</td>
</tr>
<tr>
<td>Interpreter</td>
<td>90%</td>
</tr>
<tr>
<td>Classifier</td>
<td>95% (closed enum branches)</td>
</tr>
<tr>
<td>Agent selector</td>
<td>90%</td>
</tr>
<tr>
<td>Skill engine</td>
<td>90%</td>
</tr>
<tr>
<td>Prompt builder</td>
<td>95% (templates and validators are critical)</td>
</tr>
<tr>
<td>Safety gate</td>
<td>95% (security-critical)</td>
</tr>
<tr>
<td>Persistence</td>
<td>90%</td>
</tr>
<tr>
<td>Output format</td>
<td>90%</td>
</tr>
<tr>
<td>Grounding</td>
<td>90%</td>
</tr>
<tr>
<td>Executor</td>
<td>85%</td>
</tr>
</table>
Modules below their threshold block CI.
### 5.4 The linter tests
These enforce code-style invariants the bible declared. At `~/cee/tests/lint/`:
```python
@pytest.mark.fast
def test_no_xml_string_interpolation_outside_templates():
    """Section 09 Rule 1: only Jinja templates assemble XML strings."""
    pattern = re.compile(r'f["\'<].*</.*?>["\']')
    violations = []
    for path in walk_python_files("cee/"):
        if "prompt_builder/templates" in str(path):
            continue  # templates are exempt
        with open(path) as f:
            for lineno, line in enumerate(f, 1):
                if pattern.search(line):
                    violations.append(f"{path}:{lineno}: {line.strip()}")
    assert not violations, f"XML interpolation outside templates:\n" + "\n".join(violations)


@pytest.mark.fast
def test_no_path_string_concatenation_outside_paths_module():
    """Section 04 Rule: all paths reference ~/cee/paths.py."""
    pattern = re.compile(r'f["\'~/].*?["\']|"\.\./')
    violations = []
    for path in walk_python_files("cee/"):
        if path.name == "paths.py":
            continue
        # detect path concatenation patterns
        ...
    assert not violations


@pytest.mark.fast
def test_no_global_writes_outside_persistence():
    """All filesystem writes go through persistence/atomic.py wrappers."""
    forbidden_calls = ["open(", "Path.write_text", "Path.write_bytes", "shutil."]
    violations = []
    for path in walk_python_files("cee/"):
        if "persistence/" in str(path):
            continue
        ...
    assert not violations
```
These tests are fast and run on every commit.
### 5.5 The CI configuration
`.github/workflows/ci.yml` (or equivalent):
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  fast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: pytest -m fast --cov=cee --cov-fail-under=85
  
  full:
    runs-on: ubuntu-latest
    needs: fast
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: pytest -m "not slow"  # excludes nightly-only tests
  
  golden:
    runs-on: ubuntu-latest
    needs: fast
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: pytest -m golden
  
  determinism:
    runs-on: ubuntu-latest
    needs: fast
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -e ".[dev]"
      - run: pytest -m determinism
```
A nightly job runs the full suite with `n=100` for determinism, and runs against the real Anthropic API for executor adapter validation (using a budget-capped account).
### 5.6 Mocking strategy
Anthropic SDK calls are mocked via `~/cee/tests/conftest.py`:
```python
@pytest.fixture(autouse=True)
def mock_anthropic(monkeypatch):
    def fake_create(model, max_tokens, temperature, system, messages):
        # Return a canned response based on the input pattern
        return CannedResponse(canned_for(messages, system))
    monkeypatch.setattr(anthropic.Anthropic, "messages.create", fake_create)
```
Canned responses live at `~/cee/tests/fixtures/llm_responses/<input_hash>.json`. When a new test needs a new canned response, it's recorded once via `cee record-llm-response <test_name>` against the real API, then committed.
This way unit and integration tests never make live API calls but the canned responses reflect real model behavior.
### 5.7 Quality metrics beyond pass/fail
`cee test-stats` reports:
- Coverage per module
- Test count per category
- Determinism check pass rate over last 30 runs
- Average test runtime per category
- Slowest 10 tests
- Tests not run in last 30 days (potential dead tests)
This is reviewed periodically to keep the suite healthy.
### 5.8 The test obligations consolidated
Every prior section has obligations of the form "test in section 18." Consolidated:
<table header-row="true">
<tr>
<td>From section</td>
<td>Obligation</td>
<td>Test location</td>
</tr>
<tr>
<td>00</td>
<td>Test every halt type from §10.4</td>
<td>`tests/adversarial/`</td>
</tr>
<tr>
<td>00</td>
<td>"Hello-world" Run completes end-to-end</td>
<td>`tests/integration/test_pipeline_low_complexity.py`</td>
</tr>
<tr>
<td>01</td>
<td>One failing-input test per problem layer</td>
<td>`tests/adversarial/`</td>
</tr>
<tr>
<td>01</td>
<td>Each closed enum has schema</td>
<td>`tests/unit/test_schemas/`</td>
</tr>
<tr>
<td>02</td>
<td>Per-role surface enforcement</td>
<td>`tests/unit/test_persistence/test_role_surface.py`</td>
</tr>
<tr>
<td>02</td>
<td>`produced_by` field present on every artifact</td>
<td>`tests/unit/test_schemas/test_provenance.py`</td>
</tr>
<tr>
<td>03</td>
<td>Golden Runs per complexity tier</td>
<td>`tests/golden/`</td>
</tr>
<tr>
<td>03</td>
<td>Halt-for-skill-conflict, resume-after-pause, replay-from-step</td>
<td>`tests/integration/test_clarification_cycle.py`, `test_replay_cycle.py`</td>
</tr>
<tr>
<td>04</td>
<td>Layout invariants test</td>
<td>`tests/unit/test_layout.py`</td>
</tr>
<tr>
<td>04</td>
<td>Atomic write helpers</td>
<td>`tests/unit/test_persistence/test_atomic_writes.py`</td>
</tr>
<tr>
<td>05</td>
<td>Per-tag render, per-tag validator, full FinalPrompt schema</td>
<td>`tests/unit/test_prompt_builder/`</td>
</tr>
<tr>
<td>06</td>
<td>Per-tier selection, scoring tie-breaks, generation, validation</td>
<td>`tests/unit/test_agent_selector/`</td>
</tr>
<tr>
<td>07</td>
<td>Match scoring, generation triggers, conflict detection, versioning</td>
<td>`tests/unit/test_skill_engine/`</td>
</tr>
<tr>
<td>08</td>
<td>Per task_type, per disambiguation pair, per flag trigger, hard cap escalation, ambiguity halt</td>
<td>`tests/unit/test_classifier/`</td>
</tr>
<tr>
<td>08</td>
<td>Determinism CI for classifier</td>
<td>`tests/determinism/`</td>
</tr>
<tr>
<td>09</td>
<td>Per-tag render, per-target executor variants, chunker</td>
<td>`tests/unit/test_prompt_builder/`</td>
</tr>
<tr>
<td>09</td>
<td>Determinism CI for prompt builder</td>
<td>`tests/determinism/`</td>
</tr>
<tr>
<td>09</td>
<td>Linter rule for XML interpolation outside templates</td>
<td>`tests/lint/`</td>
</tr>
<tr>
<td>10</td>
<td>Inference per task_type, validators per format, coherence</td>
<td>`tests/unit/test_output_format/`</td>
</tr>
<tr>
<td>11</td>
<td>Per source type, per prohibition pattern, citation validation</td>
<td>`tests/unit/test_grounding/`</td>
</tr>
<tr>
<td>12</td>
<td>Per redaction pattern, per injection pattern, confirmation flow, abort flow, hash chain</td>
<td>`tests/unit/test_safety_gate/`</td>
</tr>
<tr>
<td>13</td>
<td>Per renderer, vault integrity (`cee verify --obsidian`)</td>
<td>`tests/unit/test_persistence/test_obsidian_writer.py`</td>
</tr>
<tr>
<td>14</td>
<td>Slash commands valid frontmatter, hooks log correctly, executor adapter swap</td>
<td>`tests/unit/test_executor/`, `tests/integration/`</td>
</tr>
<tr>
<td>15</td>
<td>Per validation rule, seed Skills validate, generation success rate ≥95%</td>
<td>`tests/unit/test_skill_files/`</td>
</tr>
<tr>
<td>16</td>
<td>Per validation rule, seed agents validate, posture-body LLM validator</td>
<td>`tests/unit/test_agent_files/`</td>
</tr>
<tr>
<td>17</td>
<td>Replay each example, byte equality</td>
<td>`tests/golden/`</td>
</tr>
</table>
If a section's obligation is not in this table, this page is incomplete and needs an update.
---
## 6. Data / Inputs Needed
### 6.1 Test fixtures
- `~/cee/tests/fixtures/inputs/` — RawInput JSON files for each test case
- `~/cee/tests/fixtures/expected/` — expected output XML files for golden Runs
- `~/cee/tests/fixtures/llm_responses/` — canned LLM responses
- `~/cee/tests/fixtures/schemas/` — valid and invalid examples per schema
- `~/cee/tests/fixtures/bible_mirror_snapshots/` — frozen bible mirrors per test scenario
### 6.2 Required dependencies
- pytest, pytest-cov
- jsonschema
- pydantic (for schema validation)
- pyyaml (for frontmatter)
- [coverage.py](http://coverage.py)
### 6.3 CI environment
- Python 3.11+
- No real Anthropic API key (mocked)
- 4GB RAM minimum (tests run in parallel via `pytest-xdist`)
---
## 7. Outputs Produced
### 7.1 Per CI run
- Test results: pass/fail per test
- Coverage report: per module + overall
- Slowest tests log
- Determinism check results
### 7.2 Per test failure
- Diagnostic output: assertion message, traceback, relevant fixture data
- For golden Runs: diff between expected and actual FinalPrompt
- For determinism: which iterations differ and how
### 7.3 Periodic reports
- `cee test-stats` — quality metrics
- Nightly determinism report — pass rate over time
- Coverage drift report — modules approaching threshold
---
## 8. Agent + Skill Implications
### 8.1 Seed catalogs are tested for validation
The 12 seed agents and 12 seed Skills must each pass their respective file validators. Tests in `tests/unit/test_seed_skills_validate.py` and `test_seed_agents_validate.py`.
### 8.2 Each seed catalog item is exercised by at least one example
Section 17's 8 examples collectively reference every seed agent and Skill at least once. The golden test suite proves this.
### 8.3 Generation success rate is measured
A test runs the agent generator and Skill generator against 50 representative inputs each and asserts ≥95% produce valid files on first try. This is a soft quality metric; failures don't block CI but trigger investigation.
---
## 9. Edge Cases
**EC1 — A test depends on a fixture that's been moved.**
Test fails with `FileNotFoundError`. Fixture path corrected.
**EC2 — A determinism test fails because of a cosmic-ray bit flip.**
Tests are not retried automatically. A flake is reported and investigated. If reproducible at lower rate (e.g., 1 in 1000), it's a real bug.
**EC3 — Coverage drops below threshold because new code was added without tests.**
CI fails. Author adds tests before merge.
**EC4 — A schema migration breaks existing fixtures.**
The migration script updates fixtures. If it can't, the test author updates them manually as part of the migration PR.
**EC5 — A golden Run's expected output changes due to a bible update.**
The example regeneration tool updates the golden expected outputs. The PR includes both the bible change and the regenerated examples.
**EC6 — A test passes locally but fails in CI.**
Indicates environment dependency. Check for: timezone, locale, file system case sensitivity, hidden state. Fix the test.
**EC7 — Mocked LLM response is stale.**
A real API change makes the canned response unrealistic. `cee record-llm-response <test_name> --refresh` updates the canned response.
**EC8 — A test takes \>60 seconds and is marked ****`fast`****.**
Marker corrected. If genuinely fast in clean state but slow due to fixture loading, fixture moved to `conftest.py` for caching.
**EC9 — An adversarial test passes because the system actually accepts the bad input.**
Either the test is wrong (input wasn't actually adversarial) or there's a real bug (system should reject but doesn't). Investigate.
**EC10 — Phase 2 tests need a real API key.**
Nightly job uses a CI-secret-managed key with budget caps. No keys in repo or PR CI.
**EC11 — A test accidentally writes to ****`~/cee/`****.**
Tests use `tmp_path`. A test that doesn't is detected by a pre-commit hook that scans for filesystem writes outside `tmp_path`.
**EC12 — Test parallelization breaks fixtures (race condition).**
Fixtures use `tmp_path` per test. Module-scoped fixtures use locks. `pytest-xdist` is configured with `--dist=loadscope` to keep related tests on same worker.
---
## 10. Failure Modes
### 10.1 Tests pass but the system is broken
**Failure:** coverage is 85%+ but doesn't exercise critical paths.
**Detection:** golden Run fails when actually used.
**Recovery:** add the missing path to coverage; new tests reflect the regression.
### 10.2 Tests are flaky
**Failure:** intermittent failures that pass on retry.
**Detection:** CI reports.
**Recovery:** find the source of non-determinism; do not retry. Fix the root.
### 10.3 Determinism test passes but is meaningless
**Failure:** the deterministic module is so simple that running it 10 times always works, but the real model isn't deterministic.
**Detection:** integration test or golden test fails.
**Recovery:** determinism test inputs broadened; mocks made closer to real LLM behavior.
### 10.4 Coverage report misleads
**Failure:** code path is "covered" because a test imports the module, but no assertion exercises the path.
**Detection:** mutation testing (separate, slower test category).
**Recovery:** add assertion-driven tests; mutation testing reveals weak coverage.
### 10.5 Test fixtures grow unbounded
**Failure:** `tests/fixtures/` becomes huge; PR diffs unreadable.
**Detection:** size monitoring; PR review.
**Recovery:** factor common fixture data; large binary fixtures stored in Git LFS; old fixtures cleaned up.
### 10.6 New section added but no tests
**Failure:** bible expanded but section 18 not updated.
**Detection:** section 18's "every section's obligations are mapped" rule; CI's bible consistency check.
**Recovery:** test obligation table updated; tests added.
### 10.7 Mocked LLM responses drift from real model
**Failure:** tests pass against mocks but fail against real API.
**Detection:** nightly real-API run.
**Recovery:** canned responses re-recorded.
### 10.8 Golden Runs become hard to update
**Failure:** every bible change cascades into 8 golden Run regenerations; PR is huge.
**Detection:** PR size monitoring.
**Recovery:** examples are minimal-yet-realistic; bible changes that touch every section are batched; example regeneration is a single tool invocation.
### 10.9 CI takes too long
**Failure:** full test suite \>10 minutes; PRs are slow.
**Detection:** CI duration tracking.
**Recovery:** parallelize via `pytest-xdist`; mark slow tests `slow` and exclude from PR CI; nightly catches them.
### 10.10 Test names obscure failures
**Failure:** generic test names; failure logs are useless.
**Detection:** OPERATOR friction; PR review.
**Recovery:** Rule 10 strictly applied; CI rejects PRs with test names that don't describe behavior.
---
## 11. Build Notes for Claude Code
- **Test layout:** `~/cee/tests/` with subdirectories per category as in §5.1.
- **`conftest.py`****:** module-scoped fixtures, mock setup, environment isolation.
- **Mock framework:** `pytest-mock` plus `responses` for HTTP mocking. Anthropic SDK mocked via monkeypatch.
- **Coverage:** `coverage.py` configured in `pyproject.toml`; report generated per CI run.
- **Markers:** `fast`, `slow`, `integration`, `golden`, `adversarial`, `determinism`. Defined in `pytest.ini`.
- **Fixtures:** `tests/fixtures/` for test data. `tests/conftest.py` for fixtures used across multiple tests.
- **Mutation testing:** `mutmut` or equivalent, run nightly. Targets coverage gaps — generates mutants of source code and asserts tests catch them.
- **Pre-commit:** runs `pytest -m fast` and the linter tests. Catches obvious regressions before push.
- **Test runner:** `pytest` with `-x` (stop on first failure) for OPERATOR debugging, `--tb=short` for clean output.
- **Recording new mock responses:** `cee record-llm-response <test_name>` invokes the real API once, captures the response, commits as fixture.
- **Test obligation tracking:** a script `cee verify --test-obligations` walks bible §10 sections and asserts every named failure mode has a test in the suite.
---
## 12. Definition of Done
This page is complete — and the test framework is unblocked for build — when:
- [ ] All 8 examples in section 17 have golden tests that pass.
- [ ] Coverage is ≥85% per module.
- [ ] Determinism tests pass with `n=10` for all 5 deterministic modules.
- [ ] Every halt type in section 19 has at least one adversarial test.
- [ ] Every closed enum (task_type, posture, format, source_type, etc.) has schema-level tests.
- [ ] Linter tests enforce the "no XML interpolation outside templates" and "no path string concatenation" rules.
- [ ] CI runs in under 10 minutes for the fast subset, under 30 for the full suite.
- [ ] Pre-commit hook blocks fast-test failures and lint violations.
- [ ] `cee test-stats` and `cee verify --test-obligations` work and report correctly.
- [ ] Mocked LLM responses are recorded for every test that needs them; no test makes live API calls in PR CI.
- [ ] The test obligation table in §5.8 is verified — every "test in section 18" reference across the bible is mapped.
---
## 13. Final Statement
The test suite is what makes the bible's invariants enforceable. Determinism, schema validity, halt correctness, coverage — all become properties the codebase honors because tests fail otherwise. Without this page, sections 00–16 are policy. With it, they are infrastructure. Every PR that merges has been through the full enforcement gauntlet; that's why merging is safe.
