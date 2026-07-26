# PILOT-ACP-1 — Worker Session Boundary

**Date:** 2026-07-26
**Status:** In progress. Findings below are measured, not projected.
**Constraint honoured:** bounded pilot, no new external service, no production code changed.

## Purpose

Determine whether ACP can serve as Soma's standard coding-agent session boundary
for Claude Code and Codex while Soma retains task, project, workspace,
cancellation, evidence, and acceptance authority. The decision it must inform is
whether ACP session recovery is sufficient, whether provider CLI resume is also
required, or whether a small custom component remains justified.

## Environment

| Component | Version | Auth |
|---|---|---|
| Claude Code | 2.1.220 (`@anthropic-ai/claude-code`) | logged in |
| Codex | 0.145.0 (`@openai/codex`) | ChatGPT |
| Node | v24.14.0 | — |

Both installed globally during this pilot. Note that `%APPDATA%\npm` is on
neither the session PATH nor the persistent user PATH, so the binaries are not
reachable from a normal shell without prepending it. Before this install, the
`codex` on PATH was a leftover sandbox shim at `~/.codex/.sandbox-bin/codex`
rather than a real installation.

All tests ran against a disposable git repository in scratch. The Soma
repository was never used as an agent workspace.

---

## Finding 1 — Neither agent exposes ACP

This is the pilot's headline result and it was established before any session
was run.

- **Claude Code 2.1.220** has no `acp` flag or subcommand. It exposes
  `--print` with `--output-format stream-json`, `--input-format stream-json`,
  and `--resume` / `--continue` / `--from-pr`.
- **Codex 0.145.0** has no `acp` subcommand. It exposes `exec` (with `--json`),
  `resume`, `mcp-server`, and an experimental `app-server` whose JSON-RPC
  protocol can be emitted as JSON Schema
  (`codex app-server generate-json-schema --out DIR`, 39 files, methods
  including `initialize` and `thread/start`).

ACP support for both exists only through Zed's adapters, which would be a new
external dependency. The pilot's budget excludes new services, so the real
question is no longer "is ACP sufficient" but **"provider-native protocols
behind a thin Soma adapter, versus taking on Zed's adapters as a dependency."**

## Finding 2 — Both native protocols give Soma what it needs

| Capability | Claude Code | Codex |
|---|---|---|
| Structured streaming | `system`, `assistant`, `user`, `result`, `rate_limit_event` | `thread.started`, `turn.started`, `item.started`, `item.completed`, `turn.completed` |
| Stable session identity | `session_id` | `thread_id` |
| Identity emitted even on failure | yes — a not-logged-in run still returned `session_id` and `is_error: true` | not tested |
| Applies real edits | yes (`Read`, `Edit`; `calc.py` +8) | yes (`calc.py` +4) |
| Cost reported | `total_cost_usd` ($0.1094 on a 3-turn edit) | not observed in `exec --json` |

Both emit a stable session identity and a structured event stream, which are the
two things a Soma adapter requires. Claude additionally reports per-run cost and
a `rate_limit_event`, which feed the usage-accounting prerequisite recorded in
the architecture findings §5.7.

## Finding 3 — Resume works, and both can resume a *specific* session

`--last`-style resume is not useful to Soma, which may supervise several
concurrent sessions. Both agents accept an explicit identifier.

| Test | Claude Code | Codex |
|---|---|---|
| Resume carries prior context | yes — recalled `multiply` | yes — recalled `subtract` |
| Resume by explicit id | yes — `--resume <session_id>`, returned id matched | yes — `exec resume <SESSION_ID>`, returned `thread_id` matched |

Provider-native resume is therefore sufficient for context continuity, and the
session identifier is stable across processes. **No ACP `session/load` is
required to achieve resumption.**

## Finding 4 — Both agents orphan child processes on a naive parent kill

This is the most operationally important result, and it corrects an earlier
reading within this same pilot.

A first cancellation test against Codex used a task that only wrote a file. The
whole process tree died with the parent, which suggested no orphan risk. That
conclusion was an artifact of the task, not a property of the agent. Repeating
the test with a genuinely long-running child process (a 120-second `python`
sleep invoked through the agent's shell tool) produced the opposite result for
both agents.

**Claude Code** — mid-tool-call tree, 6 processes, 5 levels deep:

```
15436 claude.exe
└── 36512 bash.exe
    └── 12044 bash.exe
        ├── 10612 conhost.exe
        └── 37864 bash.exe
            └── 14052 python.exe   <- the actual work
```

Killing only `15436` left **5 of 6 processes alive**, including the `python.exe`
performing the work.

**Codex** — mid-tool-call tree, 5 processes:

```
28164 codex.exe
├── 37588 node_repl.exe
├── 23328 pwsh.exe
└── 32536 pwsh.exe
    └── 39284 python.exe   <- the actual work
```

Killing only `28164` left **2 of 5 alive** (`pwsh` and `python`).

### Consequence

Owned-tree cancellation is **mandatory** for both workers, not an optimisation.
An adapter that terminates only the agent process leaks running work, and that
work can continue mutating a workspace after Soma believes the task is
cancelled. Soma's existing exact-process-identity and owned-tree cancellation
capability is therefore directly load-bearing for coding-agent supervision, and
is a genuine differentiator rather than redundant infrastructure.

Neither agent's own protocol removes this requirement, so it is not a reason to
prefer ACP either — an ACP adapter would sit at the same level and inherit the
same problem.

## Safety note

The headless Claude Code process tree had to be separated from the running
Claude Desktop application, whose processes share the `claude.exe` image name.
Subtree isolation was verified against the desktop root PID before any
termination, and desktop integrity was re-confirmed after every kill. All pilot
processes were terminated at the end; a final sweep confirmed none survived.

---

## Outstanding tests

- concurrency: two sessions in two worktrees, no interference
- Soma-side restart mid-session, then recovery through provider resume
- the Codex `app-server` protocol as an alternative to `exec` (schema extracted,
  not yet exercised)
- Claude `--input-format stream-json` for mid-session steering

## Provisional reading

Not a conclusion; recorded so the direction of evidence is visible.

The evidence so far points away from adopting ACP and towards **a thin
Soma-owned adapter over each provider's native protocol**. ACP would add an
external adapter dependency for both agents while providing nothing the native
protocols do not already supply: structured streaming, stable session identity,
and resume by explicit id are all present today. The one capability neither
protocol provides — reliable termination of the whole process tree — is not
supplied by ACP either and must come from Soma regardless.

The adapter surface required looks small: spawn with a recorded session
identifier, parse one event stream per provider into Soma task events, resume by
identifier, and cancel through Soma's owned-tree mechanism rather than the
agent's own process.
