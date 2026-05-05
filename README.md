<div align="center">

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:0D1117,30:1f6feb,60:7C3AED,100:F7DF1E&height=240&section=header&text=CEE&fontSize=90&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=Claude%20Execution%20Engine%20%E2%80%A2%20Deterministic%20Prompt%20Pipeline&descAlignY=62&descSize=18" />

# ⚙️ Claude Execution Engine

### A deterministic Python pipeline that turns unstructured input into validated XML FinalPrompts for Claude.

[![Typing SVG](https://readme-typing-svg.herokuapp.com?font=JetBrains+Mono&weight=600&size=22&pause=1000&color=58A6FF&center=true&vCenter=true&width=900&lines=Built+in+public+under+Made+Without+Instructions.;Same+input.+Same+config.+Same+prompt+out.;Bible-first.+Halt-and-resolve.+Audit-everything.;1%2C531+tests+passing.+Zero+drift+in+the+pipeline.;The+git+history+IS+the+build+log.)](https://git.io/typing-svg)

<br />

![](https://komarev.com/ghpvc/?username=byeadro&color=blueviolet&style=for-the-badge&label=REPO+VIEWS)

<br />
<br />

[![Phase](https://img.shields.io/badge/Phase%203-Complete-2ea043?style=for-the-badge&logo=checkmarx&logoColor=white)](#-status)
[![Tests](https://img.shields.io/badge/Tests-1%2C531%20passing-2ea043?style=for-the-badge&logo=pytest&logoColor=white)](#-status)
[![Python](https://img.shields.io/badge/Python-3.11.15-3776AB?style=for-the-badge&logo=python&logoColor=white)](#)
[![Status](https://img.shields.io/badge/Build-In%20Public-7C3AED?style=for-the-badge)](https://medium.com/@byeadro)
[![License](https://img.shields.io/badge/License-All%20Rights%20Reserved-1f6feb?style=for-the-badge)](#-license)

</div>

---

## 🧭 What This Is

CEE takes raw, unstructured input — a question, a task, a half-formed thought — and runs it through a **strict, auditable pipeline** that produces a validated XML prompt structured for Claude's optimal response shape.

> **It's a deterministic prompt engine.**
> Same input, same configuration, same prompt out.
> No LLM-in-the-loop drift in the pipeline itself — Claude is what runs *against* the FinalPrompt, not what builds it.

Every step is bible-grounded. Every artifact is persisted to three substrates. Every operation is recorded in a tamper-evident hash-chained audit log. Every classifier decision is checkable.

---

## 🎯 Why This Exists

```text
I'm a non-technical solo founder.
I'm building real software with AI-assisted development tools.
I'm documenting the process publicly under MWI.

CEE is the production-quality demonstration of what disciplined,
AI-assisted, bible-driven development looks like at scale.
```

Every architectural decision lives in `bible/`. Every task ships with a design proposal, halt-and-resolve protocol, verification, and commit message that traces back to a specific bible section.

**The git history is the build log.**

If you're a fellow non-technical builder, an investor evaluating AI-native tooling, or another founder thinking *"could I actually build this?"* — yes, you can. This repo is one example of what that path looks like.

---

## 🏛️ Architecture — 1-Minute Overview

CEE has **three substrates**, each with a defined role:

<table>
  <tr>
    <td align="center" width="33%">
      <h3>📁 Filesystem Canon</h3>
      <code>~/cee/</code>
      <br /><br />
      <p>The source of truth. All artifacts (Skills, Agents, Runs, audit logs, promotion queue) live here as files. Atomic writes, role-enforced via <code>persistence/filesystem_writer.py</code>.</p>
    </td>
    <td align="center" width="33%">
      <h3>🧠 Obsidian Vault Mirror</h3>
      <code>~/SecondBrain/cee/</code>
      <br /><br />
      <p>A human-readable mirror layer. Derived from filesystem canon. Edits in the vault don't propagate back. Operator authority over post-scaffold edits is absolute (bible 13 §EC3).</p>
    </td>
    <td align="center" width="33%">
      <h3>📚 Notion (Async)</h3>
      <code>via MCP</code>
      <br /><br />
      <p>Promotion targets for Skills and Agents that get approved for the Notion knowledge layer. Goes through an async queue with stub-injectable client for testability.</p>
    </td>
  </tr>
</table>

### Around those substrates

| Layer | Path | Job |
|---|---|---|
| 🛡️ **Safety Gate** | `safety_gate/` | Redaction patterns + injection scanners + confirmation gate before any artifact crosses a substrate boundary |
| 🔗 **Audit Log** | `persistence/audit.py` | Hash-chained JSONL across four canonical logs (cli, roles, boot, security). Tamper-evident |
| ⌨️ **CLI** | `cli/` | Operator-facing verbs: `cee verify`, `cee audit-verify`, `cee scaffold-obsidian`, `cee init`, `cee sync-bible` |
| 📖 **Bible** | `bible/` | 24 markdown chapters defining every architectural rule. The codebase implements the bible; the bible doesn't describe the codebase |

---

## 🗺️ How to Read This Repo

<details>
<summary><b>⏱️ If you have 5 minutes</b></summary>

<br />

1. Read this file.
2. Skim `bible/00_project_vision.md` for the phase plan.
3. Open `build_status.md` and look at the Phase 3 close-out section.

</details>

<details>
<summary><b>🕰️ If you have 30 minutes</b></summary>

<br />

1. Read `bible/00_project_vision.md` in full.
2. Read `bible/04_database_file_structure.md` for the substrate layout.
3. Read `bible/12_prompt_leak_security_rules.md` for the safety + audit posture.
4. Read `bible/20_production_build_plan.md` for the module-by-module map.

</details>

<details>
<summary><b>🛠️ If you want to understand how it was built (the MWI angle)</b></summary>

<br />

- Browse the commit history. Phase 3 (T1 through T13) is **13 disciplined task cycles**.
- Each commit message documents the design decisions, halts surfaced, and bible-grounded rationale.
- The `build_status.md` file tracks every phase, every task, and every downstream candidate (deferred work items) with resolution commit hashes.

</details>

---

## 📊 Status

```yaml
Phase 1 — Foundations:                          ✅ shipped
Phase 2 — Boot Sequence + Bible Sync:           ✅ shipped (gate: 635d003)
Phase 3 — Persistence + Substrates + Safety:    ✅ shipped 2026-05-03 (gate: a5a4673)
Phase 4 — Pipeline Driver:                      🔜 designed
Phase 5 — Classifier:                           🔜 designed
Phase 6 — Builders:                             🔜 designed
Phase 7 — Runtime:                              🔜 designed
Phase 8 — Observability:                        🔜 designed
```

### 📈 Test Count Progression

```text
Phase 1 close   ──────────►  baseline
Phase 2 close   ──────────►  1,134 tests
Phase 3 close   ──────────►  1,531 tests   (+397 across Phase 3's 13 tasks)
```

---

## 🧰 Stack

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11.15-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-2.x-E92063?style=for-the-badge&logo=pydantic&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-1531%20tests-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)
![Notion](https://img.shields.io/badge/Notion-MCP-000000?style=for-the-badge&logo=notion&logoColor=white)
![Obsidian](https://img.shields.io/badge/Obsidian-Mirror-7C3AED?style=for-the-badge&logo=obsidian&logoColor=white)

</div>

| Component | Choice |
|---|---|
| **Runtime** | Python 3.11.15 |
| **Schemas** | Pydantic 2.x (closed schemas, `extra="forbid"`, frozen where appropriate) |
| **Tests** | pytest — 1,531 tests across unit + integration suites |
| **Filesystem writes** | Atomic via `os.replace` |
| **Audit logs** | Hash-chained JSONL (SHA-256, `GENESIS_HASH` anchored) |
| **Knowledge sync** | Notion MCP integration (deferred client wrapping) |
| **Frameworks** | None. No magic. Just disciplined Python. |

---

## 🏗️ Built With

<table>
  <tr>
    <td align="center" width="25%">
      <img src="https://img.shields.io/badge/Claude%20Code-D97757?style=for-the-badge&logo=anthropic&logoColor=white" /><br />
      <sub>For implementation</sub>
    </td>
    <td align="center" width="25%">
      <img src="https://img.shields.io/badge/Claude.ai-D97757?style=for-the-badge&logo=anthropic&logoColor=white" /><br />
      <sub>For design conversations</sub>
    </td>
    <td align="center" width="25%">
      <img src="https://img.shields.io/badge/VS%20Code-007ACC?style=for-the-badge&logo=visual-studio-code&logoColor=white" /><br />
      <sub>The editor surface</sub>
    </td>
    <td align="center" width="25%">
      <img src="https://img.shields.io/badge/Bible--First-7C3AED?style=for-the-badge" /><br />
      <sub>Halt-and-resolve discipline</sub>
    </td>
  </tr>
</table>

The bible-first / halt-and-resolve workflow is described in `build_status.md` and demonstrated in every Phase 3 commit.

---

## 🧪 The Discipline

```text
1.  Read the bible section.
2.  Write the design proposal.
3.  Surface the halts before writing code.
4.  Resolve every halt against a bible-grounded rationale.
5.  Implement.
6.  Verify (tests, audit chain, substrate consistency).
7.  Commit with a message that traces back to the bible section.
8.  Update build_status.md.
9.  Next task.
```

No skipped steps. No "we'll fix it later." Every task closes clean or it doesn't close.

---

## 📜 License

**All rights reserved.**

This repository is public for build-in-public visibility, not for redistribution. If you want to use this code or pattern for your own work, get in touch.

---

## 📬 Contact

<div align="center">

[![LinkedIn](https://img.shields.io/badge/LinkedIn-adrianbond-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/adrian-bond-87994b20a/)
[![Medium](https://img.shields.io/badge/Medium-@byeadro-12100E?style=for-the-badge&logo=medium&logoColor=white)](https://medium.com/@byeadro)
[![GitHub](https://img.shields.io/badge/GitHub-@byeadro-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/byeadro)

</div>

---

<div align="center">

### Made Without Instructions.

<img width="100%" src="https://capsule-render.vercel.app/api?type=waving&color=0:F7DF1E,40:7C3AED,100:0D1117&height=120&section=footer" />

</div>
