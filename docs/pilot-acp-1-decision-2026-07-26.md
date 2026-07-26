# PILOT-ACP-1 — Decision Record

**Date:** 2026-07-26
**Status:** Decided. Closes PILOT-ACP-1.
**Evidence:** [`pilot-acp-1-evidence-2026-07-26.md`](pilot-acp-1-evidence-2026-07-26.md) — ten measured findings.
**Scope of this record:** a decision only. No Soma implementation was performed
and none is authorized by this document.

## Naming

The pilot keeps the name `PILOT-ACP-1` for traceability, even though its
conclusion is not about adopting ACP. The name records what was asked; this
record states what was found.

**Its evidence rejected ACP as the primary worker boundary.** That is a
successful pilot outcome, not a failed one: it cost two days and it prevented an
adapter layer that would have been carried indefinitely.

---

## 1. Decision

> **Soma's coding-agent boundary will be a thin Soma-owned adapter over each
> provider's native protocol. ACP is evaluated and declined as the primary
> boundary, and retained as a known-good design reference.**

## 2. Why ACP was declined

ACP is not broken. It works, and its session recovery is genuine — for Claude
Code, `session/load` after a supervisor crash restored context the agent then
used correctly. That was the pilot's central question and the answer was yes.

It is declined on three measured grounds.

**It supplies nothing the native protocols lack.** Structured streaming, a
stable session identity, resume by explicit id, and mid-turn steering are all
present natively today. ACP would restate capabilities Soma can already reach.

**It does not solve the problem that actually threatens correctness.** Orphaned
processes survive a root kill under ACP exactly as under native: 5 of 8 for
Claude ACP against 5 of 6 native. An ACP adapter sits at the same level as the
CLI and inherits the same process tree. Owned-tree cancellation must come from
Soma either way. This is the decisive point — it removes the strongest argument
ACP had.

**It adds a release cadence that is already failing.** `codex-acp` 0.16.0
establishes and loads sessions but cannot complete a single turn against this
ChatGPT account, because it bundles a Codex core older than the installed native
CLI. The native CLI runs the same account without complaint. Adapter version-lag
is not a hypothetical cost here; today it is blocking.

## 3. What the native path is confirmed to support

Every capability a future execution-backend contract would need was exercised.

| Contract capability | Claude Code | Codex | Evidence |
|---|---|---|---|
| Start a session with a recorded identity | `session_id` | `thread_id` | F2 |
| Structured progress stream | yes | yes | F2 |
| Resume a **specific** session by id | yes | yes | F3 |
| Context survives resume | yes | yes | F3 |
| Steer a turn already in flight | yes | not tested | F10 |
| Report cost/usage | `total_cost_usd`, `rate_limit_event` | not in `exec --json` | F2, F9 |
| Concurrent isolated sessions | yes, mixed-agent | yes, mixed-agent | F9 |
| Honest machine-readable failure | yes — id and `is_error` even when unauthenticated | yes | F2 |
| Cancellation without orphans | **no — Soma must own this** | **no — Soma must own this** | F4 |

The last row is the only gap, and Soma already has the mechanism.

## 4. Consequences for a future backend contract

Stated as constraints for whoever writes Roadmap V3, not as a design.

1. **Cancellation is Soma's, not the adapter's.** The contract must terminate an
   owned process tree, never just the agent process. An adapter that calls the
   agent's own cancel is insufficient and will leak work that keeps mutating a
   workspace after the task is reported cancelled.
2. **Session identity is provider-owned; task identity is Soma's.** Both agents
   emit a stable identifier that survives process death. The contract stores it
   as a mapping, exactly as the canonical-authority rule requires, and never
   promotes it to task identity.
3. **Resume is by explicit id, never "last".** Both providers support this.
   `--last`-style resume is unusable when supervising concurrent sessions.
4. **Inherited environment must be sanitized.** A supervising agent leaks its own
   markers into workers; Claude Code refuses to start "inside another Claude Code
   session". This is the roadmap's existing sanitized-environment requirement,
   now measured rather than anticipated.
5. **Worktrees are sufficient isolation.** Nothing agent-specific was needed for
   two different agent products to work in parallel on one repository.
6. **Executables must be addressed by full resolved path.** The Claude npm
   package ships a native `bin/claude.exe` with no `cli.js`; a bare command name
   is not resolvable by `subprocess` on Windows. This also matters for the
   runtime-identity capture the roadmap already requires.
7. **Cost accounting has a source on at least one provider.** Claude reports
   `total_cost_usd` per run. The usage-accounting prerequisite is reachable
   without estimating tokens.

## 5. What this record does not decide

- It does not authorize building the worker plane, an adapter, or a backend
  implementation.
- It does not settle whether Codex's `app-server` protocol is preferable to
  `exec`. The schema was extracted but not exercised; the decision did not turn
  on it.
- It does not revisit the canonical task plane's coverage, which the lifecycle
  inventory records as one of nine authorities.

## 6. Residual risk

**Provider protocol drift.** Choosing native protocols means tracking two
vendor-specific event shapes instead of one standard. This is accepted because
the alternative measured worse: the ACP adapters are themselves version-lagged
behind the same vendors, adding a third moving part rather than removing one.

**Codex ACP may become viable later.** If `codex-acp` catches up, the decision is
worth re-testing. Nothing here forecloses it, which is why ACP is retained as a
design reference: the ACP shape — `session/new`, `session/prompt`,
`session/load`, `session/cancel`, streamed `session/update` — is a good model for
the Soma-side adapter interface even when the wire protocol is native.

## 7. Status

PILOT-ACP-1 is closed. Its stop conditions were not triggered: it stayed inside
its budget, changed no production code, created no second authority, and left
nothing that needs removing. All pilot artifacts live in scratch; the only
repository changes are this record and the evidence document.
