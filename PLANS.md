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

### No paid infrastructure for validation

- Do not start, rent, or retain RunPod or any other paid remote/GPU host solely for CodexBridge testing, acceptance, or roadmap evidence.
- Prefer local Windows validation, deterministic mocks and replayed fixtures, existing free CI, or infrastructure already running for an actual user-requested workload.
- OS-, provider-, or hardware-specific execution evidence that cannot be obtained without new cost is non-blocking deferred evidence. Collect it opportunistically during real work rather than making it a roadmap gate.

### Evidence before Roadmap V3

After the Hermes integration reaches its bounded gate, architectural feature expansion pauses. CodexBridge will be exercised on real projects before another broad reliability roadmap is created.

## Current Baseline

Complete: D1-D5 durability; G0/G1 managed editing and executable closure; X1/X2 unrestricted local PowerShell; X2A parallel groups; C1 permissive-only cleanup; R3 managed transfer; R4 durable remote Linux ownership; and optional X4 remote PowerShell.

R5 absolute resource enforcement is complete. H1A has selected and pinned the Hermes companion-process architecture. The H1B protocol foundation, pinned read-only stdio companion adapter, and durable one-request executable client contract are complete; public gateway routing and terminal-result publication are the next executable unit.

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

Status: **complete**.

Implemented:

- deterministic cgroup-v2 absolute memory policy at conservative `40_000_000_000`, graceful `45_000_000_000`, and hard `48_000_000_000` bytes;
- policy and samples in authoritative R4 state and heartbeats;
- graceful and hard process-group enforcement with identity revalidation;
- persisted threshold, signal, identity, confirmation, and terminal evidence;
- a separate `16_384`-byte ceiling for internal encoded controllers;
- authoritative GPU temperature/memory, disk-capacity, controller-heartbeat, and bounded CUDA-OOM evidence while preserving absolute-memory-first enforcement;
- POSIX execution coverage for graceful exit, forced escalation, direct hard termination, identity refusal, and persisted evidence.

Acceptance evidence:

- `tests/test_remote_controller_state.py`: `8 passed`;
- `tests/test_ssh_watchdog.py`: `9 passed`;
- `tests/test_remote_resource_enforcement.py`: `7 passed`;
- `tests/test_ssh_watchdog_execution.py`: `4 skipped` on Windows as platform-gated;
- the actual generated controller completed all four process-group cases on the existing free Linux host: graceful, escalation, hard, and identity refusal;
- affected modules compiled and `git diff --check` passed.

R5 satisfies deterministic threshold paths, visible overrides, exact termination targeting, durable remaining-signal evidence, and real POSIX process-group validation without provisioning paid infrastructure.

## H1 - ChatGPT-Controlled Hermes Tool Runtime

Status: **in progress; H1A feasibility audit and the H1B protocol foundation are complete**.

### H1A - Feasibility audit

- Identify and pin the candidate Hermes revision.
- Confirm registry, toolset, search, schema, dispatch, result, cancellation, and approval interfaces.
- Prove whether `tool_search`, `tool_describe`, and `tool_call` work without a Hermes model-agent loop.
- Inspect how built-ins, plugins, skills, and connected MCP tools enter the effective registry.
- Identify required runtime state, credentials, browser state, and long-running ownership.
- Prefer a versioned process boundary: upstream server mode or a small Hermes companion adapter.
- Avoid direct in-process Hermes imports unless no stable boundary exists and the coupling is explicitly accepted.

The audit produces a compact decision and implementation scope; it must not silently expand into implementation.

H1A decision (2026-07-18):

- Pin `NousResearch/hermes-agent` revision `862b1b37bf0aadba3a98b3756c7d71779379b53b` as the initial compatibility target.
- Use a small versioned Hermes companion process over stdio; do not import Hermes into the CodexBridge service process and do not invoke a Hermes model-agent loop.
- The existing upstream `mcp_serve.py` is session/event/approval oriented and is not the required generic tool-runtime boundary.
- Hermes catalog search and schema description can execute as pure registry reads. Deferred `tool_call` can invoke the underlying tool without model inference while preserving the normal Hermes hook, guardrail, edit-approval, and approval path.
- Built-ins, plugins, and connected MCP tools converge in the effective registry. Skills remain instruction resources unless associated code registers an actual tool.
- Generic detached or long-running tools remain unsupported initially because the registry has no provider-neutral external ownership and cancellation contract.
- The accepted implementation scope and evidence are recorded in [`docs/hermes-tool-runtime-feasibility.md`](docs/hermes-tool-runtime-feasibility.md).

H1B protocol foundation completed on 2026-07-18:

- added a versioned companion handshake bound to Hermes revision `862b1b37bf0aadba3a98b3756c7d71779379b53b`;
- bound registry generation and deterministic effective-schema hash into handshake, search, and describe responses;
- added deterministic interface-drift failures for protocol, revision, registry-generation, and schema changes;
- added bounded `tool_search` summaries and exact `tool_describe` schema identity;
- added fail-closed evidence that no Hermes model-runtime module was initialized;
- focused validation: `tests/test_hermes_companion_protocol.py` reported `5 passed`, the protocol module compiled, and `git diff --check` passed.

Pinned companion executable adapter completed on 2026-07-18:

- added a JSON-lines stdio executable that verifies the exact Hermes Git revision before importing upstream code;
- imports only the pinned `tools.registry` discovery boundary and fails closed on registry interface drift;
- emits the accepted handshake and routes schema-bound read-only `tool_search` and `tool_describe` requests;
- bounds request and response sizes and emits deterministic error envelopes;
- rejects any observed Hermes model-runtime import before serving requests;
- focused validation: `tests/test_hermes_companion.py` reported `5 passed`, `tests/test_hermes_companion_protocol.py` reported `5 passed`, the adapter compiled, and `git diff --check` passed.

Durable companion client contract completed on 2026-07-19:

- added bounded one-request handshake/search/describe launch construction over the existing durable executable-profile lifecycle;
- persisted the pinned Hermes revision, checkout, operation, and expected registry/schema identity in the accepted client metadata;
- added exact one-response parsing with handshake and bound catalog-identity verification;
- focused validation: `tests/test_hermes_companion_client.py` reported `5 passed`, the client module compiled, and `git diff --check` passed.

Next executable unit: expose the durable read-only Hermes handshake/search/describe path through the public gateway, publish verified terminal response metadata and protected stdout/stderr references, and add adjacent server/job-manager integration coverage.

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

Status: **blocked on H1 acceptance**.

After H1, freeze architectural expansion and exercise:

- ordinary local repository and service work that requires no newly rented infrastructure;
- parallel build or test work;
- repeated connector use across separate ChatGPT sessions;
- Hermes-backed reads and approved reversible external actions;
- optional remote or GPU-host work only when that infrastructure is already running for an actual user-requested workload, never provisioned solely for the pilot.

Create a separate pilot evidence log. Each entry records timestamp, project, expected outcome, HEAD/build identity, relevant run/tool identities, exact failure, lost or duplicated work, recovery, attribution, reproduction frequency, and artifacts.

Record normal friction before redesign. Repair immediately only for security violations, destructive targeting, lost or duplicated work, unrecoverable corruption, or a blocker preventing continuation.

## Roadmap V3 Promotion Rules

Promote an observation when it violates a durability/security invariant, can lose or duplicate work, blocks a representative workflow, repeatedly requires manual recovery, reveals a repeated architectural pattern, or carries sufficient expected impact.

Attribute connector 502s before repair. Treat external fixture loss as infrastructure unavailability unless CodexBridge mishandles it. Write Roadmap V3 only after representative pilot evidence is reviewed.

## Deferred Work

- paid RunPod or other paid remote/GPU validation; evidence may be collected only opportunistically during actual user-requested workloads;
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
