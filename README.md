# CEE — Claude Execution Engine

A deterministic Python pipeline that converts unstructured input into validated XML FinalPrompts for Claude. Built in public by [Adrian Bond](https://www.linkedin.com/in/adrianbond) under the [Made Without Instructions](https://medium.com/@byeadro) brand.

**Status:** Phase 3 complete (gate-passed). Phases 4–8 ahead per [`bible/00_project_vision.md`](bible/00_project_vision.md).

---

## What this is

CEE takes raw, unstructured input — a question, a task, a half-formed thought — and runs it through a strict, auditable pipeline that produces a validated XML prompt structured for Claude's optimal response shape. Every step is bible-grounded, every artifact is persisted to three substrates (filesystem canon, Obsidian vault mirror, Notion via async queue), every operation is recorded in a tamper-evident hash-chained audit log, and every classifier decision is checkable.

It's a deterministic prompt engine. Same input, same configuration, same prompt out. No LLM-in-the-loop drift in the pipeline itself — Claude is what runs *against* the FinalPrompt, not what builds it.

## Why this exists

I'm a non-technical solo founder. I'm building real software with AI-assisted development tools — primarily [Claude Code](https://www.anthropic.com/claude-code) — and documenting the process publicly under MWI. CEE is the production-quality demonstration of what disciplined, AI-assisted, bible-driven development looks like at scale.

Every architectural decision lives in [`bible/`](bible/). Every task ships with a design proposal, halt-and-resolve protocol, verification, and commit message that traces back to a specific bible section. The git history *is* the build log.

If you're a fellow non-technical builder, an investor evaluating AI-native tooling, or another founder thinking "could I actually build this?" — yes, you can. This repo is one example of what that path looks like.

## Architecture (1-minute overview)

CEE has three substrates, each with a defined role:

1. **Filesystem canon** (`~/cee/`): the source of truth. All artifacts (Skills, Agents, Runs, audit logs, promotion queue) live here as files. Atomic writes, role-enforced via `persistence/filesystem_writer.py`.
2. **Obsidian vault mirror** (`~/SecondBrain/cee/`): a human-readable mirror layer. Derived from filesystem canon. Edits in the vault don't propagate back. Operator authority over post-scaffold edits is absolute (bible 13 §EC3).
3. **Notion** (async): promotion targets for Skills and Agents that get approved for the Notion knowledge layer. Goes through an async queue with stub-injectable client for testability.

Around those substrates:

- **Safety gate** (`safety_gate/`): redaction patterns + injection scanners + confirmation gate before any artifact crosses a substrate boundary.
- **Audit log** (`persistence/audit.py`): hash-chained JSONL across four canonical logs (cli, roles, boot, security). Tamper-evident.
- **CLI** (`cli/`): operator-facing verbs (`cee verify`, `cee audit-verify`, `cee scaffold-obsidian`, `cee init`, `cee sync-bible`).
- **Bible** (`bible/`): 24 markdown chapters defining every architectural rule. Numbered 00–23. The codebase implements the bible; the bible doesn't describe the codebase.

## How to read this repo

If you have 5 minutes:
- Read this file.
- Skim [`bible/00_project_vision.md`](bible/00_project_vision.md) for the phase plan.
- Open [`build_status.md`](build_status.md) and look at the Phase 3 close-out section.

If you have 30 minutes:
- Read [`bible/00_project_vision.md`](bible/00_project_vision.md) in full.
- Read [`bible/04_database_file_structure.md`](bible/04_database_file_structure.md) for the substrate layout.
- Read [`bible/12_prompt_leak_security_rules.md`](bible/12_prompt_leak_security_rules.md) for the safety + audit posture.
- Read [`bible/20_module_inventory.md`](bible/20_module_inventory.md) for the module-by-module map.

If you want to understand *how* it was built (the MWI angle):
- Browse the commit history. Phase 3 (T1 through T13) is 13 disciplined task cycles.
- Each commit message documents the design decisions, halts surfaced, and bible-grounded rationale.
- The `build_status.md` file tracks every phase, every task, and every downstream candidate (deferred work items) with resolution commit hashes.

## Status

**Phase 1 — Foundations:** shipped.
**Phase 2 — Boot Sequence + Bible Sync:** shipped (gate at commit `635d003`).
**Phase 3 — Persistence + Substrate Adapters + Safety Gate:** shipped 2026-05-03 (gate at commit `a5a4673`). 1531 tests passing.
**Phases 4–8:** pipeline driver, classifier, builders, runtime, observability. Designed in `bible/00_project_vision.md`.

Test count progression: Phase 1 close → Phase 2 close (1134) → Phase 3 close (1531). Delta +397 across Phase 3's 13 tasks.

## Stack

- Python 3.11.15
- Pydantic 2.x (closed schemas, `extra="forbid"`, frozen where appropriate)
- pytest (1531 tests across unit + integration suites)
- Atomic filesystem writes via `os.replace`
- Hash-chained audit logs (SHA-256, GENESIS_HASH anchored)
- Notion MCP integration (deferred client wrapping)
- No frameworks. No magic. Just disciplined Python.

## Built with

- [Claude Code](https://www.anthropic.com/claude-code) for implementation
- [Claude](https://claude.ai/) (the chat interface) for design conversations and prompt construction
- VS Code as the editor surface
- The bible-first / halt-and-resolve workflow described in build_status.md and demonstrated in every Phase 3 commit

## License

All rights reserved. This repository is public for build-in-public visibility, not for redistribution. If you want to use this code or pattern for your own work, get in touch.

## Contact

- **LinkedIn:** [adrianbond](https://www.linkedin.com/in/adrianbond)
- **MWI on Medium:** [@byeadro](https://medium.com/@byeadro)
- **GitHub:** [@byeadro](https://github.com/byeadro)

---

*Made Without Instructions.*
