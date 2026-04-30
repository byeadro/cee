---
notion_section: 23
notion_title: 23 — VS CODE + CLAUDE CODE SETUP
mirrored_at: 2026-04-30
---

# 23 — VS CODE + CLAUDE CODE SETUP

> **Status:** Authoritative · **Owner:** AB · **Reads on boot:** Yes
> **Purpose of this page:** the concrete day-zero setup. Sections 00–22 specified what to build; this page is how to set up the editor and orchestrate the Claude Code sessions that will do the building. The other sections are deliberately abstract; this one is deliberately copy-paste-ready. By the end of this page, you have a configured VS Code workspace, a working Claude Code project, and the exact prompts to paste to bootstrap the build.

---

## 1. What This Is

A hands-on setup guide for the OPERATOR (AB) on a fresh build session. Covers:

- The dedicated VS Code workspace for CEE (`cee.code-workspace`)
- Recommended VS Code extensions and their configurations
- Python debugging setup (launch configs, breakpoints, pytest integration)
- The Claude Code session pattern: how to invoke, what to paste, what to expect
- The exact step-by-step Claude Code script for Phase 1 (the first 16 tasks from section 21)
- The transition from Phase 1 to subsequent phases using section 22's bootstrap prompt
- Troubleshooting for the common surprises

This page is the most operationally specific page in the bible. Where every other section answered "what," this answers "now what do I actually click."

---

## 2. Why This Matters

The gap between "the bible is complete" and "my fingers are typing the first command" is real. Without this page:

- The OPERATOR opens VS Code and immediately faces 5 small decisions (which window? which folder? terminal here or external? which Python interpreter?).
- Claude Code sessions are invoked ad-hoc and produce inconsistent results because each session lacks the right context.
- Phase 1's 16 tasks are technically defined but operationally opaque — "open Claude Code and ask it to create [paths.py](http://paths.py)" is true but underspecified.
- The OPERATOR loses momentum to setup friction.

This page eliminates that friction. The setup is one-time; the resulting workspace and Claude Code rhythm carry through every phase.

---

## 3. Core Requirements

The setup MUST:

1. Result in a single dedicated VS Code workspace at `~/cee/cee.code-workspace` opened to the CEE root.
2. Have Python debugging fully configured — breakpoints, step-through, pytest integration, run/debug buttons next to test functions.
3. Have a defined Claude Code invocation pattern: where to launch, what context to provide, when to start a new session.
4. Provide the exact prompts the OPERATOR pastes for the first session (Phase 1 task 1 onward).
5. Document what "a session ends" looks like and how to start the next one cleanly.
6. Cover the common surprises (Python interpreter not detected, pytest not finding tests, Claude Code not seeing the workspace).

The setup MUST NOT:

- Require extensions that aren't widely used and well-maintained.
- Lock the OPERATOR into a specific Python version manager (pyenv, conda, system Python all work).
- Make assumptions about non-VS Code tooling. The Obsidian vault is separate; Notion is separate; CEE itself is separate. This page is just VS Code + Claude Code.
- Replace section 21's task list. This page is *how* to execute that list, not *what* the list contains.

---

## 4. System Rules

**Rule 1 — One workspace, one project root.**
The workspace file is `~/cee/cee.code-workspace`. It opens `~/cee/` as the single folder. No multi-root experimentation; CEE is self-contained.

**Rule 2 — Python interpreter is explicit.**
The workspace specifies Python 3.11+ via `python.defaultInterpreterPath`. No relying on "VS Code will figure it out."

**Rule 3 — Tests are debuggable.**
Every test function has a clickable Run/Debug gutter icon. Failures step into the code with full variable inspection.

**Rule 4 — Claude Code sessions are scoped.**
One Claude Code session per task (per section 21 Rule 3). Sessions don't accumulate context across tasks.

**Rule 5 — The terminal lives inside VS Code.**
The integrated terminal (View → Terminal) is where `cee` commands run. External terminals are fine for personal preference but the workspace is set up for integrated use.

**Rule 6 — Setup is reproducible.**
The `cee.code-workspace` file and `.vscode/` directory are committed to git so a fresh clone produces an identical setup.

**Rule 7 — Extensions are minimal but specific.**
Four extensions, each with a defined purpose. No "install everything that looks useful."

**Rule 8 — The page is updated when the toolchain shifts.**
If VS Code, Python, or Claude Code change the recommended pattern, this page is updated. The bible follows reality.

---

## 5. Detailed Workflow — The Setup

### 5.1 Pre-flight verification

Before starting, confirm in a terminal:

```bash
code --version              # VS Code itself
python3.11 --version        # Python 3.11+
git --version               # git installed
claude --version            # Claude Code installed (or however it's invoked)
```

If any fail, resolve before proceeding. VS Code is assumed installed and configured per the OPERATOR's preference; this page configures the CEE-specific layer on top.

### 5.2 Create the workspace

```bash
mkdir -p ~/cee
cd ~/cee
git init
```

Now create the workspace file. Open VS Code:

```bash
code ~/cee
```

VS Code opens to `~/cee/`. From the menu: **File → Save Workspace As…** → save as `~/cee/cee.code-workspace`. This becomes the project's canonical workspace file.

Close VS Code. From now on, open the project via:

```bash
code ~/cee/cee.code-workspace
```

This ensures the workspace settings are loaded.

### 5.3 The workspace file contents

Replace the contents of `~/cee/cee.code-workspace` with:

```json
{
  "folders": [
    {
      "name": "CEE",
      "path": "."
    }
  ],
  "settings": {
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python",
    "python.testing.pytestEnabled": true,
    "python.testing.pytestArgs": [
      "tests"
    ],
    "python.testing.unittestEnabled": false,
    "python.analysis.typeCheckingMode": "basic",
    "python.analysis.autoImportCompletions": true,
    "python.linting.enabled": true,
    "editor.formatOnSave": true,
    "editor.rulers": [100],
    "files.exclude": {
      "**/__pycache__": true,
      "**/.pytest_cache": true,
      "**/.coverage": true,
      "**/htmlcov": true,
      "**/*.egg-info": true
    },
    "files.watcherExclude": {
      "**/runs/**": true,
      "**/audit/archive/**": true
    },
    "search.exclude": {
      "**/runs/**": true,
      "**/.venv/**": true
    },
    "terminal.integrated.cwd": "${workspaceFolder}",
    "[python]": {
      "editor.defaultFormatter": "ms-python.black-formatter",
      "editor.tabSize": 4
    },
    "[json]": {
      "editor.tabSize": 2
    },
    "[yaml]": {
      "editor.tabSize": 2
    },
    "[markdown]": {
      "editor.wordWrap": "on",
      "editor.tabSize": 2
    }
  },
  "extensions": {
    "recommendations": [
      "ms-python.python",
      "ms-python.black-formatter",
      "ms-python.mypy-type-checker",
      "redhat.vscode-yaml",
      "tamasfe.even-better-toml"
    ]
  }
}
```

Key decisions baked in:

- Python interpreter pinned to a venv at `~/cee/.venv/` (created in 5.5).
- pytest is the test runner; unittest disabled.
- Type checking on, basic level (catches obvious issues without overwhelming).
- Format on save with Black.
- The `runs/` directory is excluded from search and file watching — it grows large during use.
- Terminal opens at the workspace root.

### 5.4 Install recommended extensions

Reopen the workspace:

```bash
code ~/cee/cee.code-workspace
```

VS Code prompts to install the recommended extensions. Accept. The five:

| Extension | Purpose |
|---|---|
| **Python** (ms-python.python) | Python language support, debugger, test runner integration |
| **Black Formatter** ([ms-python.black](http://ms-python.black)-formatter) | Code formatting on save |
| **Mypy Type Checker** (ms-python.mypy-type-checker) | Static type checking |
| **YAML** (redhat.vscode-yaml) | YAML syntax + schema validation (for [SKILL.md](http://SKILL.md) / agent frontmatter) |
| **Even Better TOML** (tamasfe.even-better-toml) | TOML support (for pyproject.toml, .cee/config.toml) |

### 5.5 Create the Python virtual environment

In the integrated terminal (Ctrl+` or Cmd+` to open):

```bash
cd ~/cee
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

The `.venv` directory is created. VS Code automatically detects it (because the workspace settings point to it) and uses it for the Python language server, pytest, and debugging.

Verify:

```bash
which python   # should print ~/cee/.venv/bin/python
```

### 5.6 Add `.gitignore`

Create `~/cee/.gitignore`:

```plain text
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
.venv/
venv/
ENV/
env/
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/
.coverage
htmlcov/

# CEE-specific (user state, runtime artifacts)
# DO commit: ~/cee/runs/golden/ (test fixtures)
# DO NOT commit: ~/cee/runs/* (real Run state)
runs/*
!runs/golden/
!runs/golden/**
audit/
bible/.sync_meta.json
promotion_queue.json

# IDE
.vscode/*
!.vscode/launch.json
!.vscode/tasks.json
!.vscode/settings.json
!.vscode/extensions.json
.idea/

# OS
.DS_Store
Thumbs.db
```

Note: `.vscode/` has selective ignores. The launch / tasks / settings / extensions files are committed (they're shared workspace config); other .vscode files (user-specific state) are not.

### 5.7 Set up Python debugging

Create `~/cee/.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Current File",
      "type": "debugpy",
      "request": "launch",
      "program": "${file}",
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Pytest: Current File",
      "type": "debugpy",
      "request": "launch",
      "module": "pytest",
      "args": [
        "${file}",
        "-v"
      ],
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Pytest: Current Test (line)",
      "type": "debugpy",
      "request": "launch",
      "module": "pytest",
      "args": [
        "${file}::${selectedText}",
        "-v",
        "-s"
      ],
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Pytest: All Unit Tests",
      "type": "debugpy",
      "request": "launch",
      "module": "pytest",
      "args": [
        "tests/unit",
        "-v"
      ],
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "Pytest: Determinism Suite",
      "type": "debugpy",
      "request": "launch",
      "module": "pytest",
      "args": [
        "tests/determinism",
        "-v",
        "-m",
        "determinism"
      ],
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "CEE: Run pipeline",
      "type": "debugpy",
      "request": "launch",
      "module": "cee.cli",
      "args": [
        "run",
        "${input:ceeInput}"
      ],
      "console": "integratedTerminal",
      "justMyCode": false
    },
    {
      "name": "CEE: Verify all",
      "type": "debugpy",
      "request": "launch",
      "module": "cee.cli",
      "args": [
        "verify",
        "--all"
      ],
      "console": "integratedTerminal",
      "justMyCode": false
    }
  ],
  "inputs": [
    {
      "id": "ceeInput",
      "type": "promptString",
      "description": "CEE input (paste your messy idea)"
    }
  ]
}
```

`justMyCode: false` lets you step into Pydantic, Jinja, the Anthropic SDK — useful when CEE's behavior depends on library internals.

### 5.8 Set up tasks

Create `~/cee/.vscode/tasks.json`:

```json
{
  "version": "2.0.0",
  "tasks": [
    {
      "label": "pytest: fast",
      "type": "shell",
      "command": "pytest -m fast --cov=cee --cov-fail-under=85",
      "group": {
        "kind": "test",
        "isDefault": true
      },
      "presentation": {
        "reveal": "always",
        "panel": "new"
      }
    },
    {
      "label": "pytest: full",
      "type": "shell",
      "command": "pytest -m 'not slow' --cov=cee",
      "group": "test",
      "presentation": {
        "reveal": "always",
        "panel": "new"
      }
    },
    {
      "label": "pytest: golden",
      "type": "shell",
      "command": "pytest -m golden -v",
      "group": "test"
    },
    {
      "label": "cee: verify all",
      "type": "shell",
      "command": "cee verify --all",
      "problemMatcher": []
    },
    {
      "label": "cee: sync bible",
      "type": "shell",
      "command": "cee sync-bible",
      "problemMatcher": []
    },
    {
      "label": "cee: list runs",
      "type": "shell",
      "command": "cee list-runs",
      "problemMatcher": []
    },
    {
      "label": "black: format all",
      "type": "shell",
      "command": "black cee/ tests/",
      "problemMatcher": []
    },
    {
      "label": "mypy: typecheck",
      "type": "shell",
      "command": "mypy cee/",
      "problemMatcher": ["$mypy"]
    }
  ]
}
```

Access these via Ctrl+Shift+P (Cmd+Shift+P on Mac) → "Tasks: Run Task."

### 5.9 Workspace settings (defaults)

The settings in the `.code-workspace` file are workspace-scoped. If you want to override anything just for your machine, create `~/cee/.vscode/settings.json` with the override. Workspace-file settings still take precedence in the file's scope.

### 5.10 Final verification

At this point:

1. Open the workspace: `code ~/cee/cee.code-workspace`.
2. Activate the venv in terminal: `source .venv/bin/activate`.
3. Confirm Python interpreter in VS Code's bottom-right shows the venv path.
4. Open command palette → "Python: Run All Tests" — should report 0 tests (none yet) without errors.
5. Open `Run and Debug` panel (Ctrl+Shift+D) — should show the launch configurations from `launch.json`.
6. Open Tasks (Ctrl+Shift+P → "Tasks: Run Task") — should list the tasks from `tasks.json`.

If all six pass, the editor is configured. Commit:

```bash
git add cee.code-workspace .vscode/ .gitignore
git commit -m "Initial VS Code workspace setup"
```

---

## 6. Claude Code Session Pattern

Claude Code is invoked from within the VS Code terminal (or a separate shell, depending on your preference). The pattern below assumes the integrated terminal.

### 6.1 How to invoke a session

```bash
cd ~/cee
claude
```

This opens a Claude Code session with `~/cee/` as the project root. Claude Code reads `~/cee/CLAUDE.md` if it exists (it doesn't yet — Phase 7 builds it).

Until Phase 7 generates a real [CLAUDE.md](http://CLAUDE.md), you provide context per session. The pattern in section 6.3 below covers this.

### 6.2 Session scoping

One task = one Claude Code session. Sessions accumulate context; long-running sessions confuse the model. Pattern:

1. Open Claude Code.
2. Paste the task prompt.
3. Let Claude Code complete the task.
4. Verify (run tests, check files exist).
5. Commit.
6. Exit Claude Code (`/exit` or Ctrl+D).
7. Open a new session for the next task.

This is friction. It is also what keeps results consistent. Resist the urge to chain tasks in one session.

### 6.3 Session context template

Until [CLAUDE.md](http://CLAUDE.md) exists, every Claude Code session for CEE work begins with this context block, pasted before the actual task prompt:

```javascript
# CEE Build Context

You are helping build the Claude Execution Engine (CEE), a system specified in the System Design Bible at ~/cee/bible/. The bible has 23 sections (00-23). Each section is authoritative for its scope. Implementation follows the bible; the bible does not follow implementation.

## Important rules

- Bible is the source of truth. If a task seems to conflict with the bible, halt and ask.
- All paths reference ~/cee/paths.py (once it exists). Never concatenate path strings.
- All filesystem writes go through ~/cee/persistence/atomic.py (once it exists). Never use raw open() in module code.
- Tests ship with the code that produces them. No "tests later."
- Closed enums are in the bible. Do not invent values.
- LLM calls use temperature 0 and a fixed system prompt. No creative sampling.
- Determinism is a property the codebase enforces. No system clock reads, no env var reads at module import, no random ordering.

## What you should NOT do

- Do not edit files in ~/cee/bible/ (read-only mirror; bible edits happen in Notion).
- Do not write outside ~/cee/, ~/.cee/, ~/SecondBrain/cee/.
- Do not invent module names, schema fields, enum values, agent slugs, or Skill slugs not specified in the bible.

## Today's task

[paste the task here]
```

This context block is ~250 words. Pasting it once per session is the cost of consistent results.

---

## 7. The Phase 1 Hand-Held Walkthrough

This section walks through Phase 1 (the 16 tasks from section 21) with the exact Claude Code invocations. After Phase 1, subsequent phases use section 22's bootstrap prompt or analogous task lists.

### Task 1 — Repository scaffold

**Done already** if you followed sections 5.2 through 5.10 above. The repo exists with workspace and .gitignore. Skip to task 2.

### Task 2 — Mirror the bible to filesystem

This task does not need Claude Code; it's manual copy from Notion to filesystem. From the integrated terminal:

```bash
mkdir -p ~/cee/bible
```

Then, for each of the 23 Notion bible pages, copy the markdown content into a file at `~/cee/bible/<NN>_<slug>.md`. Use Notion's "Export to Markdown" feature for cleanliness. The slug is derived from the title (kebab-case, lowercase).

After copying, create `~/cee/bible/.sync_meta.json`:

```bash
cat > ~/cee/bible/.sync_meta.json <<'EOF'
{
  "last_synced": "2026-04-30T00:00:00Z",
  "pages": {
    "00_project_vision": "manual_initial",
    "01_real_problem_breakdown": "manual_initial"
  }
}
EOF
```

(Add an entry per page; the sync command in Phase 2 automates this.)

Commit:

```bash
git add bible/
git commit -m "Mirror bible 00-23 to filesystem"
```

### Task 3 — Directory layout

Launch Claude Code: `claude` from the workspace terminal.

Paste the context template from §6.3, then:

```javascript
Task: Create the full directory layout per section 04 §5.1 of the bible at ~/cee/bible/04_database_file_structure.md.

For every directory mentioned in §5.1 of that section, create it. For every Python package directory (anywhere a Python module will live per the bible), add an empty __init__.py file.

Do not create any files other than __init__.py at this stage. Do not write any module code yet. Just the directory skeleton.

When done, run: find ~/cee -type d | sort

Report the count of directories created.
```

When Claude Code finishes, verify:

```bash
find ~/cee -type d | wc -l
```

Should show ≥35 directories. Commit:

```bash
git add .
git commit -m "Phase 1 task 3: full directory layout"
```

Exit Claude Code.

### Task 4 — Create [paths.py](http://paths.py)

New Claude Code session. Paste context template, then:

```javascript
Task: Create ~/cee/paths.py per section 04 of the bible at ~/cee/bible/04_database_file_structure.md.

Define Path constants for every location referenced in the bible:

- CEE_ROOT (= ~/cee/)
- BIBLE_DIR (= ~/cee/bible/)
- SCHEMAS_DIR (= ~/cee/schemas/)
- PROMPTS_DIR (= ~/cee/prompts/)
- SKILLS_DIR (= ~/cee/skills/)
- AGENTS_DIR (= ~/cee/.claude/agents/)
- COMMANDS_DIR (= ~/cee/.claude/commands/)
- HOOKS_DIR (= ~/cee/.claude/hooks/)
- RUNS_DIR (= ~/cee/runs/)
- GOLDEN_RUNS_DIR (= ~/cee/runs/golden/)
- AUDIT_DIR (= ~/cee/audit/)
- TEMPLATE_DIR (= ~/cee/.template/)
- USER_CONFIG_DIR (= ~/.cee/)
- CONFIG_FILE (= ~/.cee/config.toml)
- REDACT_LIST (= ~/.cee/redact_list)
- NOTION_REDACT_LIST (= ~/.cee/notion_redact_list)
- CREDENTIALS_FILE (= ~/.cee/credentials.toml)
- OBSIDIAN_VAULT (= ~/SecondBrain/cee/)

Use pathlib.Path and Path.home() for ~. No string concatenation; use Path division operator.

After creating paths.py, run from a Python REPL:

  from cee.paths import CEE_ROOT, BIBLE_DIR
  print(CEE_ROOT, BIBLE_DIR)

Verify the output is the absolute path under your home directory.
```

Claude Code creates the file. Verify import works:

```bash
cd ~/cee
python -c "from cee.paths import CEE_ROOT, BIBLE_DIR; print(CEE_ROOT, BIBLE_DIR)"
```

If import fails, you may need a minimal pyproject.toml to make `cee` importable. If so, the next prompt to Claude Code:

```javascript
The import failed because cee is not yet installable. Create a minimal pyproject.toml at ~/cee/pyproject.toml that:

- Names the project "cee" version 0.1.0
- Requires Python >=3.11
- Lists dependencies: pydantic, pyyaml, jinja2, anthropic, python-frontmatter, tiktoken, pytest, pytest-cov, pytest-mock, pytest-xdist, coverage[toml], tomli, click
- Specifies the package source as the cee/ directory
- Configures Black with line length 100
- Configures pytest with markers from section 18: fast, slow, integration, golden, adversarial, determinism, lint

Then run: pip install -e .

And verify the import works.
```

Claude Code handles it. Verify:

```bash
pip install -e .
python -c "from cee.paths import CEE_ROOT; print(CEE_ROOT)"
```

Commit:

```bash
git add cee/paths.py pyproject.toml
git commit -m "Phase 1 task 4: paths.py + minimal pyproject.toml"
```

### Task 5 — Atomic write helpers

New session. Context + task:

```javascript
Task: Create ~/cee/persistence/atomic.py per section 04 §5.1 and the build notes in §11 of section 04.

Implement two functions:

  def atomic_write_json(path: Path, data: dict) -> None
  def atomic_write_text(path: Path, text: str) -> None

Each must:

- Write to a temp file in the same directory as the target (use tempfile.NamedTemporaryFile with delete=False).
- fsync the temp file before rename.
- Atomically rename to the target.
- On any error during write, clean up the temp file.
- Preserve permissions if the target already existed.

Then create ~/cee/tests/unit/test_persistence/test_atomic_writes.py with tests:

1. test_atomic_write_json_creates_file
2. test_atomic_write_text_creates_file
3. test_atomic_write_replaces_existing_atomically (write same path twice; verify final contents)
4. test_failure_during_write_leaves_no_partial (use a mocked write that raises mid-stream)
5. test_idempotent_double_write (write same content twice; second is no-op or successful)
6. test_permissions_preserved_on_overwrite (chmod target to 0644, overwrite, verify permission unchanged)

Use pytest's tmp_path fixture. No test writes outside tmp_path.

Run: pytest tests/unit/test_persistence/test_atomic_writes.py -v

All 6 tests must pass.
```

Verify by running pytest from VS Code's terminal or by clicking the Run button next to a test in VS Code's test explorer.

Commit:

```bash
git add cee/persistence/atomic.py tests/
git commit -m "Phase 1 task 5: atomic write helpers + tests"
```

### Tasks 6–16 — same pattern

The pattern continues for the remaining tasks. For each:

1. Open new Claude Code session.
2. Paste context template from §6.3.
3. Paste task prompt referencing the relevant bible section.
4. Verify (run tests, check files).
5. Commit.
6. Exit session.

The specific prompts for tasks 6 through 16 follow the same shape. Examples for the next two:

**Task 6 prompt (closed enums):**

```javascript
Task: Create ~/cee/errors/types.py per section 19 §5.1, §5.2, §5.3 of the bible at ~/cee/bible/19_error_handling_failure_states.md.

Define three Python Enum classes inheriting from (str, Enum):

1. HaltType with the 19 values from §5.1.
2. RunErrorType with the 7 values from §5.2.
3. WarningType with the 15 values from §5.3.

Match the bible's enum values exactly. Do not invent additional values.

Then create ~/cee/tests/unit/test_errors/test_types.py with tests asserting each enum has the expected values (count and specific names).

Run: pytest tests/unit/test_errors/ -v
```

**Task 7 prompt (exception hierarchy):**

```javascript
Task: Create ~/cee/errors/__init__.py per section 19 §5.7.

Define the exception class hierarchy:

- CEEException (base, inherits from Exception)
- PipelineHalt(halt_type: HaltType, payload: dict) inherits from CEEException
- RunError(error_type: RunErrorType, payload: dict) inherits from CEEException
- BootError(step: str, reason: str) inherits from CEEException
- ValidationError inherits from CEEException
- RoleAuthorityError inherits from CEEException
- SubstrateBoundaryError inherits from CEEException
- RoleSurfaceViolation inherits from CEEException
- InjectionDetected(flags: list) inherits from PipelineHalt (sets halt_type to HaltType.INJECTION_DETECTED)
- RedactionFailed(residual_patterns: list) inherits from PipelineHalt (sets halt_type to HaltType.REDACTION_FAILED)

Each exception's __init__ stores its parameters as attributes and calls super().__init__ with a sensible message.

Create tests in ~/cee/tests/unit/test_errors/test_exceptions.py that:

1. Each exception can be instantiated and raised.
2. Each exception can be caught at its specific class and at CEEException.
3. PipelineHalt and RunError carry their payload correctly.
4. InjectionDetected sets halt_type correctly.

Run: pytest tests/unit/test_errors/ -v (should now have tests from task 6 and task 7 both passing).
```

For tasks 8 through 16, follow the descriptions in section 21 §5.2. Each task prompt:

- Cites the specific bible section.
- Specifies the deliverable (module file + test file).
- States the verification command.
- Reminds about the rules (no path concatenation, no raw open(), tests in same task).

The rhythm becomes natural by task 8 or so. Each task takes roughly 30 minutes to 2 hours of OPERATOR time, including verification.

### After Task 16 — Phase 1 gate

From the integrated terminal:

```bash
cee verify --layout
cee verify --schemas
pytest tests/unit/ -v --cov=cee --cov-fail-under=85
```

All three must exit 0 (or report all-passing). When they do:

```bash
echo "# CEE Build Status

## Phase 1 — Foundation

- Started: $(date -I -d '5 days ago' 2>/dev/null || date -v-5d -I 2>/dev/null)
- Completed: $(date -I)
- Gate: PASSED
- Notes: <add observations here>

## Phase 2 — Boot Sequence + Bible Sync

- Status: pending
" > ~/cee/build_status.md

git add build_status.md
git commit -m "Phase 1 complete — gate passed"
```

Phase 1 is done. The foundation works.

---

## 8. Phase 2 and Beyond

For Phase 2 onward, you have two paths:

### Path A — Continue with task-by-task prompts

Distill each phase from section 20 into a numbered task list (analogous to what section 21 did for Phase 1). Use the same Claude Code rhythm: one session per task, context template each time, verify-commit-exit.

This is slower but gives maximum control. Recommended for Phases 2 and 3 (where security and persistence are critical).

### Path B — Use the section 22 bootstrap prompt

For Phases 4 onward (once you have a sense of CEE's rhythm), you can paste section 22's master bootstrap prompt and let Claude Code drive multiple phases with checkpoints between each.

This is faster but requires you to verify gate criteria carefully between phases.

### Recommended hybrid

- Phases 1–3: task-by-task. Foundation + boot + persistence + safety. The hardest-to-verify phases. Take the time.
- Phase 4 (Interpreter + Classifier): hybrid. Use task-list rhythm because determinism is critical, but the tasks within Phase 4 can be longer.
- Phases 5–7: section 22 bootstrap. By here you trust the rhythm and want to move.
- Phase 8: explicit verification, no shortcuts. Run every gate, check every test, verify every golden Run.

---

## 9. Edge Cases

**EC1 — VS Code does not detect the venv automatically.**
Click the Python version in the bottom-right status bar. Select "Enter interpreter path" and provide `~/cee/.venv/bin/python`. Or run `Python: Select Interpreter` from the command palette.

**EC2 — pytest discovery shows 0 tests when there should be some.**
Reload the test discovery: command palette → `Python: Refresh Tests`. If still empty, check that pytest is installed in the venv (`pip list | grep pytest`).

**EC3 — Black is not formatting on save.**
Verify the Black extension is installed (`[ms-python.black](http://ms-python.black)-formatter`) and the workspace setting `editor.formatOnSave` is true. Sometimes a VS Code reload (`Developer: Reload Window`) is needed.

**EC4 — Claude Code session loses context between turns.**
This is normal Claude Code behavior. The context template covers it: re-paste at session start. Don't try to maintain context across many turns; close and reopen sessions for new tasks.

**EC5 — Claude Code session takes too long on a single task.**
If a Claude Code session has been working on one task for >2 hours of wall-clock time, the task is too big. Stop the session, split the task into sub-tasks, restart with a smaller scope.

**EC6 — OPERATOR confused about which task is current.**
Check `build_[status.md](http://status.md)`. If unclear, run `git log --oneline` and inspect the most recent commit message (each task has a commit per the rhythm).

**EC7 — OPERATOR forgets to activate the venv in a new terminal.**
VS Code's integrated terminal usually auto-activates if the venv was selected as the interpreter. If not, add to your shell rc: `source ~/cee/.venv/bin/activate` when entering the directory (using direnv is a common pattern).

**EC8 — Tests pass locally but feel slow.**
Use the marker filtering: `pytest -m fast` for just fast tests. The fast suite should complete in under 60 seconds per the CI config in section 18.

**EC9 — Workspace settings get out of sync with .vscode/settings.json.**
The workspace file's settings take precedence in its scope. If both define the same key, the workspace file wins. Keep machine-specific overrides in `.vscode/settings.json` and project-wide settings in the workspace file.

**EC10 — Phase 1 takes much longer than estimated.**
Normal. The 16-hour estimate is focused work; 3–5 calendar days is realistic with day job. Don't rush; the foundation must be solid.

**EC11 — Claude Code generates code that violates a bible rule.**
Reject it. Re-prompt with explicit reference to the bible section the rule comes from. The context template covers most rules, but specific violations need specific reminders.

**EC12 — OPERATOR wants to use Cursor or another VS Code fork.**
The workspace file format is compatible. Most extensions work. The launch.json may need adjustment if the fork uses a different debugger. Otherwise, the setup transfers cleanly.

---

## 10. Failure Modes

### 10.1 Workspace not loaded; settings ignored

**Failure:** OPERATOR opens `~/cee` directly instead of the .code-workspace file. Settings from the workspace file don't apply.
**Detection:** type checking off, formatter not applied, debugging configs missing.
**Recovery:** close VS Code, reopen via `code ~/cee/cee.code-workspace`.

### 10.2 Wrong Python interpreter selected

**Failure:** VS Code uses system Python instead of venv. Imports fail at runtime; types not detected.
**Detection:** bottom-right shows wrong path; `which python` in terminal shows system path.
**Recovery:** select interpreter via command palette; reload window.

### 10.3 .gitignore too aggressive

**Failure:** important files (like `runs/golden/`) are accidentally ignored.
**Detection:** `git status --ignored` shows committed-fixture files as ignored.
**Recovery:** the .gitignore in §5.6 has explicit `!runs/golden/` rules. If bypassed, fix.

### 10.4 Claude Code drifts from task scope

**Failure:** session does the task plus "helpful" extra work that isn't in the bible.
**Detection:** unexpected files appear; tests fail because they expect specific behavior.
**Recovery:** revert the unwanted changes; re-prompt with stricter scope language. Reference bible section explicitly.

### 10.5 Tests written but not run

**Failure:** OPERATOR commits a task as complete without running the test command.
**Detection:** Phase 1 gate fails because some task's tests fail.
**Recovery:** return to the task; run tests; fix failures.

### 10.6 Claude Code uses a different code style than the project

**Failure:** generated code uses tabs instead of spaces, or a different naming convention.
**Detection:** Black formatter complains; PR diff is large because reformat.
**Recovery:** Black on save catches formatting; for naming conventions, the context template should reinforce (add a "naming conventions" line if you encounter drift).

### 10.7 Multi-task session pollution

**Failure:** OPERATOR ignores the one-session-per-task rule; one session does multiple tasks; later tasks are influenced by earlier context in confusing ways.
**Detection:** tasks 4 and onwards in the same session start producing inconsistent code.
**Recovery:** end the session; start a fresh one. Treat as lesson learned.

### 10.8 OPERATOR debugging takes too long

**Failure:** a test fails; OPERATOR spends an hour stepping through Python rather than fixing the underlying issue.
**Detection:** time tracking; gut feeling.
**Recovery:** debugging is valuable but bounded. After 30 minutes, ask Claude Code to diagnose with the failing test as input.

### 10.9 Workspace file gets corrupted

**Failure:** invalid JSON in cee.code-workspace; VS Code fails to open.
**Detection:** error on workspace open.
**Recovery:** the workspace file is committed in git; restore from history.

### 10.10 Forgetting to update build_[status.md](http://status.md)

**Failure:** OPERATOR finishes phase but doesn't update the tracking file.
**Detection:** ambiguity about phase state.
**Recovery:** check git log; reconstruct status from commit history; update file.

---

## 11. Build Notes for Claude Code

This page is itself instructions to Claude Code, but a few meta-notes:

- **The page is reread by Claude Code at boot** if cited in [CLAUDE.md](http://CLAUDE.md) (post-Phase 7). Until then, the OPERATOR copies relevant prompts from this page manually.
- **The session context template in §6.3 is intentionally short.** Pasting longer context every session is friction; this version covers the essential rules.
- **The 16 tasks in §7 are the only place this page hand-holds.** After Phase 1, the OPERATOR has internalized the rhythm and section 22's bootstrap can take over.
- **VS Code's settings file structure may shift.** If a future VS Code release deprecates the launch.json schema or workspace file format, this page is updated to match.
- **Phase 7 will integrate further.** When Phase 7 builds [CLAUDE.md](http://CLAUDE.md) and the slash commands, this page gains references to those (e.g., "after Phase 7, use `/cee-run` instead of pasting context manually").

---

## 12. Definition of Done

This page is complete — and the VS Code + Claude Code setup is unblocked — when:

- [ ] The workspace file at `~/cee/cee.code-workspace` opens cleanly and loads settings.
- [ ] All five recommended extensions install and activate.
- [ ] Python interpreter detection points to `~/cee/.venv/bin/python`.
- [ ] launch.json has all 7 configurations and they appear in the Run and Debug panel.
- [ ] tasks.json has all 8 tasks and they appear in the task picker.
- [ ] The session context template in §6.3 covers all the rules from sections 02, 04, 09, 12, 19.
- [ ] The 16 Phase 1 tasks have explicit prompts in §7 (task 3 onward demonstrates the pattern; tasks 6–16 follow the same shape).
- [ ] All edge cases in §9 have either a fix or a workaround documented.
- [ ] The hybrid recommendation in §8 is matched to the OPERATOR's risk tolerance.
- [ ] The page is reachable from the bible TOC and from [CLAUDE.md](http://CLAUDE.md) (once that exists).

---

## 13. Final Statement

The bible specified what CEE is. Sections 20–22 specified the build sequence and the bootstrap. This page is what the OPERATOR actually does on Monday morning: open VS Code, see the dedicated workspace, open a Claude Code session in the integrated terminal, paste the context template plus the first task, watch CEE come into existence one verified commit at a time. The setup is one-time; the rhythm carries through the full build. From here, you are not just reading the bible — you are executing it.
