# V3-1A-PROCESS-IDENTITY-1 — Sanitised Launch and Owned-Tree Cancellation

**Date:** 2026-07-30
**Status:** implementation submitted at `bd007ec72ca7b2e24ffe7b4587570f0173a111d8`; independent acceptance failed; corrective subgate active.
**Parent lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`
**Depends on:** accepted [`V3_1A_ADAPTER_CONTRACT_1_ACCEPTANCE_AUDIT_2026-07-30.md`](V3_1A_ADAPTER_CONTRACT_1_ACCEPTANCE_AUDIT_2026-07-30.md)
**Repository baseline:** `7d629c5bdd0ade1d3d0da262bcd8509f50744041`
**Push:** not authorised.

**Audit:** [`V3_1A_PROCESS_IDENTITY_1_ACCEPTANCE_AUDIT_2026-07-30.md`](V3_1A_PROCESS_IDENTITY_1_ACCEPTANCE_AUDIT_2026-07-30.md)
**Corrective gate:** [`V3_1A_CANCELLATION_AUTHORITY_1_GATE_2026-07-30.md`](V3_1A_CANCELLATION_AUTHORITY_1_GATE_2026-07-30.md)

The original gate remains unaccepted. Its corrective work is governed by the linked cancellation-authority gate; no later V3-1A package is active.

## 1. Objective

Prove the process and security boundary required before Soma may launch a real provider session.

This gate may launch controlled local stand-in Windows process trees that reproduce the ownership and cancellation shape measured in the provider pilot. It may not launch Claude Code or Codex, use a provider account, send a provider prompt, parse a live provider stream, or activate an interactive worker publicly.

The outcome is a reusable internal process boundary under the existing canonical Task → Run authority, not a second worker lifecycle.

## 2. Canonical authority boundary

### Existing owners retained

- `RunStore` and `JobManager` own launch intent, run lease, running/cancellation state, terminal transition, and ResultPublication.
- `process_control` owns process-start identity, PID-reuse checks, tree termination, and process liveness evidence.
- `ProjectScope` owns the exact project and repository resource.
- `OperationLockStore` owns repository write exclusion.
- `WorkerSubstrateStore.worker_child_processes` stores subordinate observations of provider-root and descendant identities.

### This gate may add

- an internal sanitised-environment builder;
- exact executable-path and file-identity verification;
- a bounded stand-in process-launch boundary;
- provider-root and owned-descendant discovery/attachment evidence;
- identity-scoped tree-cancellation evidence;
- zero-owned-descendant verification;
- the smallest correction needed to make canonical cancellation reporting consistent with durable state.

It may not add a queued/running/cancelled vocabulary, lease store, result publisher, repository lock, or provider-session lifecycle.

## 3. Required outcomes

### 3.1 Sanitised environment

Construct a child environment from an explicit safe baseline rather than blindly inheriting the controller process.

Prove that the stand-in child does not receive:

- `CLAUDECODE` or other recursion markers declared by the accepted adapters;
- inherited `CODEX_*` or Claude supervisor markers that the adapter declares for removal;
- inherited Soma MCP or connector configuration;
- unrelated credentials, API keys, tokens, or secret-bearing variables;
- controller-only Python or tool configuration unless explicitly allowlisted.

The proof must report names and classifications, never secret values.

### 3.2 Exact executable identity

Before process creation:

- require an absolute normalised path from the accepted command specification;
- prove the file exists and is executable for the current platform;
- record a stable file identity sufficient to detect path replacement between verification and launch;
- reject PATH lookup, unresolved traversal, directory targets, and identity mismatch;
- keep provider-specific installation or subscription logic outside this gate.

The stand-in may use the current project virtual-environment Python executable or another committed test fixture executable. No provider binary is required.

### 3.3 Persist before healthy attachment

For one canonical test Task → Run → ProjectScope chain:

1. preserve the canonical launch intent before starting the stand-in;
2. start one independently terminable stand-in root process;
3. obtain its exact PID and `process_control.process_identity`;
4. persist the provider-root observation in `worker_child_processes` before the boundary may report attachment ready;
5. discover and persist owned descendants with PID/start identity;
6. if identity attachment fails after process creation, contain the whole tree and publish uncertainty rather than leaving an orphan.

Substrate records remain observations. They do not own the run or declare it running.

### 3.4 Owned-tree cancellation

Prove cancellation against a real Windows stand-in tree containing at least a root, child, and grandchild or an equivalently adversarial descendant topology.

Cancellation must:

- target the exact recorded root/start identity rather than PID alone;
- enumerate or otherwise prove the owned descendant set before termination;
- terminate the complete owned tree;
- verify every recorded PID/start identity is absent afterward;
- refuse success when the root stops but one owned descendant remains;
- preserve bounded per-process termination evidence;
- publish no terminal cancellation result until zero owned descendants is proven;
- behave idempotently when replayed after successful cancellation;
- fail closed on PID reuse or start-identity mismatch.

### 3.5 Canonical cancellation baseline

Repair or provide an explicit evidence-backed disposition for:

```text
tests/test_job_manager.py::test_cancel_run_marks_cancelled
```

The public cancellation response, durable run state, terminal result, lock release, and publication must agree. A test expectation may not be weakened merely to hide a real contract disagreement.

## 4. Required crash and race tests

- executable verification succeeds, but the file identity changes before launch;
- process creation fails after durable launch intent;
- root starts, but child-identity attachment fails;
- cancellation races normal process exit;
- cancellation is replayed after terminal cancellation;
- PID remains but start identity differs;
- root exits while a descendant remains active;
- tree termination reports success but descendant verification disproves it;
- cancellation publication fails after termination proof and is retried;
- stand-in process output or environment evidence contains a secret-shaped value and is withheld or redacted.

Use deterministic fakes for narrow branches plus at least one real Windows process-tree integration test.

## 5. Security and evidence rules

- Never include secret values in argv, logs, ordinary test output, or stored evidence.
- Never persist the full inherited environment.
- Environment evidence records allowed/removed variable names and hashes or classifications only where necessary.
- Process evidence binds PID to start identity and exact canonical task/run/session binding.
- A process-control error becomes durable uncertainty; it never becomes apparent cancellation success.
- Repository/resource ownership is released only by the canonical run owner after zero-descendant proof.

## 6. Required validation

- new focused environment, executable-identity, attachment, cancellation, PID-reuse, and race tests;
- real Windows root/child/grandchild termination proof;
- accepted 208-test adapter/foundation gate remains green;
- adjacent JobManager, RunStore, `job_worker`, `process_control`, ProjectScope, operation-lock, and result-publication tests pass;
- the previously failing cancellation test passes or is closed through an explicitly reviewed compatibility decision supported by evidence;
- public gateway and schema hashes remain unchanged unless a separately approved public-contract change becomes unavoidable;
- authority audit confirms all lifecycle transitions still occur through canonical RunStore/JobManager owners.

## 7. Acceptance evidence

The gate closes only when:

- sanitisation is executed and verified against a stand-in child;
- executable existence and stable identity are verified before launch;
- root and descendant identities are persisted before attachment is reported ready;
- real Windows cancellation proves zero owned descendants;
- terminal cancellation publication cannot precede that proof;
- the known cancellation baseline is repaired or formally disposed;
- no provider account, provider process, public worker operation, or second lifecycle is introduced;
- focused and adjacent validation passes;
- the worktree is clean, local commits and an acceptance record exist, and nothing is pushed.

## 8. Explicit exclusions

- launching Claude Code or Codex;
- provider authentication, installation, upgrade, or subscription purchase;
- validating Codex stdin prompt delivery;
- live provider stream capture or fixture replacement;
- provider-native steering or supplied input;
- `STEER`, `SUPPLY_INPUT`, pause, resume, or checkpoint task commands;
- operational `AWAITING_CONTROLLER` continuation;
- public worker gateway or direct worker Soma MCP access;
- V3-1B Company, Mission, PlanRevision, WorkPackage, or AcceptanceCommit work;
- workflow/supervisor migration, deployment, production activation, or push.

## 9. Stop conditions

Stop and return to architecture review if:

- correct cancellation requires a second process lifecycle or lease authority;
- the owned descendant set cannot be proven before and after termination;
- terminal publication or lock release can occur while an owned descendant may remain;
- safe launch requires inheriting broad controller credentials or MCP configuration;
- executable identity cannot be protected from path replacement;
- the cancellation baseline can be made green only by weakening its externally visible contract;
- the package requires a real provider account, provider prompt, public gateway, V3-1B, or broad lifecycle consolidation.

## 10. Completion report

Report:

- internal process boundary chosen and alternatives rejected;
- files and canonical authorities touched;
- environment allow/remove policy and evidence;
- executable identity proof;
- stand-in process-tree topology and exact cancellation evidence;
- PID-reuse and crash-window results;
- cancellation-baseline root cause and correction;
- focused and adjacent validation;
- authority delta and compatibility impact;
- known limitations;
- exact recommended next V3-1A package.
