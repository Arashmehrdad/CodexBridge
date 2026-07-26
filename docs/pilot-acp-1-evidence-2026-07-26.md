# PILOT-ACP-1 — Worker Session Boundary

**Date:** 2026-07-26
**Status:** Complete. Findings below are measured, not projected.
**Decision:** see `pilot-acp-1-decision-2026-07-26.md`.
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

## Finding 5 — ACP does work, and `loadSession` is real

ACP was reachable after all, through Zed's adapters
(`@zed-industries/claude-code-acp` 0.16.2, `@zed-industries/codex-acp` 0.16.0),
driven by a ~180-line dependency-free Python JSON-RPC client written for this
pilot — deliberately shaped like a Soma adapter rather than a test harness, so
the measured cost reflects what Soma would carry.

Both adapters initialize and both advertise `loadSession: true`.

| | claude-code-acp | codex-acp |
|---|---|---|
| protocolVersion | 1 | 1 |
| `loadSession` | true | true |
| promptCapabilities | image, embeddedContext | image, audio, embeddedContext |
| authMethods | `claude-login` | `chatgpt`, `codex-api-key`, `openai-api-key` |

## Finding 6 — crash/recovery matrix

Measured. Native rows are from Findings 3–4; ACP rows from the client above.

| Failure | Claude ACP | Claude native | Codex ACP | Codex native |
|---|---|---|---|---|
| Supervisor dies, then recover session | `session/load` ok, **context genuinely recalled** | `--resume <id>` ok, context recalled | `session/load` ok | `exec resume <id>` ok, context recalled |
| Orphans after supervisor dies | 0 | n/a | 0 | n/a |
| Agent killed mid-tool-call: tree size | 8 | 6 | not reached | 5 |
| Orphans after killing agent root | **5 of 8** | **5 of 6** | not reached | **2 of 5** |
| `session/load` still works after agent kill | yes | n/a | yes | n/a |
| Turn execution works at all | yes | yes | **no** | yes |

### The decisive row

Orphaned processes survive a root kill under **both** transports. ACP does not
improve cancellation, because the ACP adapter sits at the same level as the CLI
and inherits the same process tree. Owned-tree cancellation must come from Soma
either way. This removes the strongest possible argument for adopting ACP.

## Finding 7 — the Codex ACP adapter is version-lagged and currently unusable

`codex-acp` 0.16.0 establishes sessions and loads them, but **cannot complete a
turn** against this ChatGPT account:

- configured `gpt-5.6-sol` → `400: The 'gpt-5.6-sol' model requires a newer version of Codex`
- `gpt-5.1-codex` → `400: not supported when using Codex with a ChatGPT account`
- `gpt-5-codex`, `gpt-5.1`, `o3` → `Model metadata not found`, no `stopReason`

The adapter bundles a Codex core older than the installed native CLI, which runs
the same account's model without complaint. Adapter version-lag is therefore not
a theoretical risk of adopting ACP; today it is blocking, and it would place a
second upstream release cadence between Soma and a working coding agent.

## Finding 8 — supervising agents leak identity into workers

The first ACP attempt failed with `Claude Code cannot be launched inside another
Claude Code session`, because the adapter inherited `CLAUDECODE` from the
supervising process. The client now strips `CLAUDECODE`, `CLAUDE_CODE*`, and
`CODEX_*` before spawning.

This is a direct, measured instance of the roadmap's "sanitized inherited
environment and handles for agent workers" requirement. Soma will hit it the
moment it supervises a coding agent from inside another one.

## Measurement corrections made during this pilot

Recorded because both were caught only by re-checking a favourable result, and
both would otherwise have become false findings.

1. **"Codex leaves no orphans"** (Finding 4) was an artifact of a task with no
   long-lived child process. Re-run with a real one, Codex orphans too.
2. **"Codex ACP recalled context"** was an artifact of the recall check scanning
   *all* drained notifications. `session/load` replays session history, which
   contains the original prompt, so the codeword was matched from replayed
   history rather than from the agent. Distinguishing the two requires checking
   that the codeword arrives in an `agent_message_chunk` emitted *after* the
   recall prompt. Under that stricter check Claude genuinely recalls and Codex
   is unverified, because its turns never complete.

Any future recovery test must assert on post-prompt agent output, never on the
presence of a token anywhere in the stream.

## Finding 9 — concurrent mixed-agent sessions isolate cleanly

Two git worktrees from one repository, one Claude Code session and one Codex
session running simultaneously, 34s wall clock.

| Check | Result |
|---|---|
| Worktree A (Claude) | `AGENT_A.txt` = `ALPHA`, no B artifact |
| Worktree B (Codex) | `AGENT_B.txt` = `BRAVO`, no A artifact |
| Main worktree | untouched |
| `git status` per worktree | each shows only its own change |
| Session identities | `91f5d23f-…` vs `019fa061-…`, distinct |
| Claude cost for its half | $0.0774 |

Two different agent products operated in parallel against one repository without
contaminating each other or the main worktree. Nothing agent-specific was needed
to achieve isolation: ordinary Git worktrees were sufficient.

## Finding 10 — Claude Code accepts steering mid-turn

`--input-format stream-json` with `--output-format stream-json` gives a genuine
bidirectional channel. A second user message injected while a turn was already
running was received and acted upon.

Turn 1 was a deliberately slow counting task. After it had written `1`, `2`, and
`3`, a steering message was sent. The agent replied "Stopping the count as
instructed", abandoned the remaining count, and did the new work instead:

```
COUNT.txt : 1
            2
            3        <- halted mid-sequence, never reached 5
STEER.txt : STEERED
result    : is_error=False, num_turns=5
```

This is the capability a backend contract would expose as `supply_input` or
`steer`, and it is available today over the native protocol without ACP.

Practical note for any future implementation: the npm package ships a native
`bin/claude.exe`. `subprocess` on Windows cannot resolve a bare `claude`, and
there is no `cli.js` to invoke through node. The executable must be addressed by
its full path.

## Outstanding tests

All tests this pilot committed to are complete. Two items were deliberately not
pursued and are recorded as out of scope rather than pending:

- the Codex `app-server` protocol as an alternative to `exec` — schema extracted
  (39 files) but not exercised, because the decision no longer depends on it
- Codex ACP turn execution — blocked upstream by adapter version-lag, which is
  itself Finding 7

## Reading

The crash/recovery matrix is complete enough to state a direction, with one cell
unmeasurable for reasons that are themselves evidence.

**ACP is a real, working protocol and its session recovery is genuine** — for
Claude Code, `session/load` after a supervisor crash restored context that the
agent then used. That was the pilot's central open question and the answer is
yes, ACP recovery works.

**It is still not worth adopting here**, for three measured reasons:

1. It solves nothing the native protocols do not already solve. Structured
   streaming, stable session identity, and resume by explicit id are present in
   both native CLIs today.
2. It does not solve the one problem that actually threatens correctness.
   Orphaned processes survive a root kill under ACP exactly as under native, so
   owned-tree cancellation must come from Soma regardless.
3. It adds an upstream release cadence that is already failing. `codex-acp`
   cannot complete a turn against this account while the native CLI can.

The recommendation is therefore **a thin Soma-owned adapter over each provider's
native protocol**, with ACP kept as a known-good fallback shape rather than a
dependency. The required surface is small: spawn with a recorded session
identifier, parse one event stream per provider into Soma task events, resume by
identifier, and cancel through Soma's owned-tree mechanism rather than the
agent's own process.

The pilot's own framing should be updated: its name presumes ACP is the subject,
but the decision it produced is *native-plus-Soma-adapter*, with ACP evaluated
and declined on evidence.
