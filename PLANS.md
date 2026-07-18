# CodexBridge Active Engineering Plan

## Purpose

CodexBridge is the durable control plane connecting this ChatGPT conversation to local machines, repositories, services, remote hosts, and external tool runtimes.

```text
ChatGPT conversation
  -> reasoning, user context, tool selection, and approvals
  -> CodexBridge MCP
      -> durable identity, policy, execution, cancellation, and evidence
      -> local and remote engineering substrates
      -> Hermes searchable tool runtime
          -> built-in tools, plugins, skills, and connected MCP tools
```

ChatGPT remains the reasoning agent. Hermes supplies tools; its Codex, Claude, or other model-agent loop is not part of this request path.

This file is an active decision document, not an engineering journal. The complete V2 implementation and validation history through commit `d1c43340af48c03ca31505ef64f4c6a60248f61c` is preserved in [`docs/roadmap-v2-achievements.md`](docs/roadmap-v2-achievements.md).

## Governing Decisions

### Durable before powerful

Every accepted asynchronous operation must persist launch intent, request identity, ownership and lease state, cancellation state, output locations, and terminal publication semantics before it is production-ready.

### ChatGPT remains the brain

- The live ChatGPT conversation owns reasoning, user context, planning, and tool selection.
- CodexBridge exposes governed capabilities to that conversation.
- Hermes is a tool runtime, not a delegated reasoning agent, for this integration.
- The design does not depend on exporting ChatGPT's private memory store. Relevant context stays in the conversation; only required tool arguments or explicit context are transmitted.

### Reuse Hermes rather than duplicate it

- Reuse Hermes registration, availability checks, toolsets, plugin discovery, MCP discovery, and searchable dispatch where feasible.
- Do not create one CodexBridge wrapper for every Hermes tool.
- New Hermes plugins or MCP tools should become discoverable without corresponding CodexBridge source changes.
- Pin and negotiate the supported Hermes interface so upstream changes fail explicitly.

### Existing execution decisions remain in force

- `permissive` is the only active execution profile.
- Unrestricted PowerShell remains the single arbitrary-command local gateway.
- Native remote Linux execution continues through the accepted R4 controller protocol.
- Remote PowerShell remains optional for hosts that already provide it.
- Existing human-only boundaries continue to apply to real-money, credential, destructive, and production-impacting actions.

### Evidence before Roadmap V3

After the Hermes integration reaches its bounded gate, architectural feature expansion pauses. CodexBridge will be exercised on real projects before another broad reliability roadmap is created.

## Current Baseline

Complete: D1-D5 durability; G0/G1 managed editing and executable closure; X1/X2 unrestricted local PowerShell; X2A parallel groups; C1 permissive-only cleanup; R3 managed transfer; R4 durable remote Linux ownership; and optional X4 remote PowerShell.

R5 absolute resource enforcement is in progress. The latest preserved checkpoint is `d1c43340af48c03ca31505ef64f4c6a60248f61c`.

Known observations, not yet separate repair programs:

- occasional HTTP 502 responses from the ChatGPT connector path;
- external acceptance fixtures that may disappear independently of CodexBridge;
- one stale assertion expecting eight `run_start` variants while nine are exposed;
- increased complexity in durable state and reconciliation contracts.

Collect operational evidence before prescribing broad fixes for these observations.

## Active Sequence

1. Complete the already-scoped R5 boundary.
2. Perform the Hermes tool-runtime feasibility audit.
3. Implement the smallest durable ChatGPT-to-Hermes tool path satisfying the accepted architecture.
4. Freeze architectural expansion and exercise the combined system on representative real projects.
5. Build Roadmap V3 from observed frequency, severity, recovery cost, and violated invariants.

Do not resume the older broad R6, R7, or P2 sequence automatically. Only supporting work required by R5, Hermes integration, or a proven pilot defect is active.

## R5 - Absolute Resource Enforcement

Status: **in progress**.

Implemented:

- deterministic cgroup-v2 absolute memory policy at conservative `40_000_000_000`, graceful `45_000_000_000`, and hard `48_000_000_000` bytes;
- policy and samples in authoritative R4 state and heartbeats;
- graceful and hard process-group enforcement with identity revalidation;
- persisted threshold, signal, identity, confirmation, and terminal evidence;
- a separate `16_384`-byte ceiling for internal encoded controllers;
- POSIX execution tests for graceful exit, escalation, hard termination, identity refusal, and persisted evidence.

Current unit:

1. Run `tests/test_ssh_watchdog_execution.py` on disposable Linux and confirm all four POSIX cases execute rather than skip.
2. Add GPU temperature/memory, disk, heartbeat, and CUDA OOM signals to authoritative controller evidence.
3. Preserve absolute-memory-first precedence and exact process identity.
4. Run focused adjacent validation and `git diff --check`.

Exit requires deterministic threshold paths, visible overrides, exact termination targeting, passing Linux execution tests with no orphan or duplicate enforcement, and durable remaining-signal evidence.

## H1 - ChatGPT-Controlled Hermes Tool Runtime

Status: **approved direction; feasibility audit not started**.

### H1A - Feasibility audit

- Identify and pin the candidate Hermes revision.
- Confirm registry, toolset, search, schema, dispatch, result, cancellation, and approval interfaces.
- Prove whether `tool_search`, `tool_describe`, and `tool_call` work without a Hermes model-agent loop.
- Inspect how built-ins, plugins, skills, and connected MCP tools enter the effective registry.
- Identify required runtime state, credentials, browser state, and long-running ownership.
- Prefer a versioned process boundary: upstream server mode or a small Hermes companion adapter.
- Avoid direct in-process Hermes imports unless no stable boundary exists and the coupling is explicitly accepted.

The audit produces a compact decision and implementation scope; it must not silently expand into implementation.

### H1B - Minimal external surface

The preferred ChatGPT-facing capability can search enabled tools, describe one exact schema, invoke it with validated arguments, inspect long-running status/results, and cancel through authoritative ownership.

The contract must preserve Hermes version, registry generation or schema hash, tool identity, selected toolset, accepted arguments, result classification, and artifact references. Exact public tool names are chosen during implementation.

### H1C - Execution and policy

- ChatGPT plans and chooses the tool; Hermes must not reinterpret the task through a second model.
- CodexBridge remains authoritative for request identity, durability, cancellation, bounded output, protected evidence, and applicable locks.
- Search and description are read-only.
- Side effects include communications, bookings, purchases, refunds, credential changes, destructive actions, and real-money operations.
- Ambiguous transport failure must never cause blind replay of a mutation.
- Automatic mutation retry requires provider-appropriate idempotency or outcome reconciliation.
- Secrets use the narrowest safe existing channel and never appear in public events or summaries.
- Long-running tools use an accepted durable owner or are explicitly unsupported.

R6 secret-reference work is conditional supporting scope: implement only the minimum required if existing protected input and environment mechanisms cannot safely launch Hermes.

### H1D - Acceptance

- ChatGPT searches Hermes without loading every deferred schema into the connector.
- ChatGPT inspects and invokes one read-only built-in or plugin tool.
- ChatGPT invokes one Hermes-connected MCP tool without tool-specific CodexBridge code.
- Evidence proves no Hermes model-agent invocation occurred.
- Exact tool/schema identity and arguments are durable.
- One approved reversible side effect executes once and its external outcome is verified.
- Ambiguous responses reconcile without duplicate mutation.
- Accepted asynchronous calls have deterministic restart and cancellation behavior.
- Credentials and protected results stay out of bounded public output.

No real-money purchase, booking, cancellation, or refund is used as an acceptance test.

## OP1 - Evidence-Driven Real-Project Pilot

Status: **blocked on R5 and H1 acceptance**.

After H1, freeze architectural expansion and exercise:

- a fresh Wan2.2 or comparable GPU-host setup;
- ordinary repository work;
- parallel build or test work;
- repeated connector use across separate ChatGPT sessions;
- Hermes-backed reads and approved reversible external actions.

Create a separate pilot evidence log. Each entry records timestamp, project, expected outcome, HEAD/build identity, relevant run/tool identities, exact failure, lost or duplicated work, recovery, attribution, reproduction frequency, and artifacts.

Record normal friction before redesign. Repair immediately only for security violations, destructive targeting, lost or duplicated work, unrecoverable corruption, or a blocker preventing continuation.

## Roadmap V3 Promotion Rules

Promote an observation when it violates a durability/security invariant, can lose or duplicate work, blocks a representative workflow, repeatedly requires manual recovery, reveals a repeated architectural pattern, or carries sufficient expected impact.

Attribute connector 502s before repair. Treat external fixture loss as infrastructure unavailability unless CodexBridge mishandles it. Write Roadmap V3 only after representative pilot evidence is reviewed.

## Deferred Work

- broad environment and secret-reference expansion beyond H1 needs;
- a large provider-neutral synthetic acceptance matrix;
- project-memory and local-model expansion;
- supervisor, workflow, optional coding, and dashboard expansion;
- Codex re-enablement.

Historical R6, R7, P2, gate, commit, and validation specifications remain in the V2 achievement record.

## Validation and Commit Policy

For code: run focused then proportional adjacent tests, `git diff --check`, milestone-level full checks where justified, and real process/host tests when OS behavior is the subject. Commit every completed batch locally and never push without explicit instruction.

For documentation only: inspect the exact diff, run `git diff --check`, confirm only intended documentation changed, commit locally, confirm a clean worktree, and do not run the full suite.

Before every write or validation, inspect active durable runs and repository locks. Preserve unrelated work and never reset, clean, restore, discard, stash, amend, rebase, or rewrite history.
