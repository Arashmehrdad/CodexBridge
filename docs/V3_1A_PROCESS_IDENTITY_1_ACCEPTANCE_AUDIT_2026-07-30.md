# V3-1A-PROCESS-IDENTITY-1 — Independent Acceptance Audit

**Date:** 2026-07-30
**Verdict:** not accepted; corrective gate required.
**Implementation commit audited:** `bd007ec72ca7b2e24ffe7b4587570f0173a111d8`
**Parent lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`
**Push:** not authorised.

## 1. Summary

The submitted package establishes a useful internal process boundary for sanitised stand-in launch, executable identity, PID/start-identity evidence, and owned-tree cancellation. It preserves the canonical Task → Run authority and adds no public gateway or second lifecycle.

The gate does not close because independent adversarial review reproduced fail-open paths inside the exact safety boundary this package was required to prove. The package remains implemented but unaccepted. Its corrections stay inside `V3-1A-PROCESS-IDENTITY-1`; interaction commands remain inactive.

## 2. Evidence that passed

- focused process-identity suite: 34 passed;
- accepted adapter/foundation regression suite: 208 passed;
- adjacent validation: 227 passed, with the known cancellation baseline still failing;
- clean worktree at the audited commit;
- no public gateway, schema, server import, lifecycle vocabulary, lease authority, result publisher, or repository lock added;
- real Windows stand-in root/child/grandchild cancellation proof passed for the covered topology;
- executable replacement with equal size and restored mtime was detected through content SHA-256;
- provider-recursion and inherited secret variables were withheld from the tested child environment.

Durable validation references:

- focused: `20260730T170532Z_executable_profile_577ca30b`;
- adapter/foundation: `20260730T170532Z_executable_profile_e910a342`;
- adjacent: `20260730T170532Z_executable_profile_d0199c0c`;
- adversarial source probes: `20260730T170809Z_executable_profile_48ca3c59`;
- live PID-12345 identity confirmation: `20260730T171052Z_executable_profile_b089817f`.

## 3. Acceptance blockers

### 3.1 Environment additions and extras can bypass sanitisation

`environment_additions` and `allowlist_extra` can reintroduce provider-recursion markers, Soma/MCP configuration, and secret-shaped names after inherited variables were filtered. The audit reproduced `CLAUDECODE` and `MCP_SERVER_TOKEN` reaching the constructed child environment.

The corrected boundary must reject forbidden additions and extras before process creation. Deliberate additions require a positive internal-name policy; they are not an unrestricted escape hatch.

### 3.2 Empty subordinate evidence is not cancellation proof

`CancellationDisposition.NOTHING_RECORDED` currently allows `may_publish_terminal_cancellation=True`. An empty `worker_child_processes` set can mean that no process existed, but it can also mean that process creation or attachment crossed a crash window.

Terminal cancellation may be published with no subordinate process row only when the canonical run plane proves a pre-launch state in which no process could have been created. The process boundary alone cannot infer that from an empty table.

### 3.3 Missing live identity still permits raw-PID termination

When a PID is live but its current start identity cannot be read, `_terminate_one` can still call `terminate_process_tree(pid)`. This is unproven ownership and must fail closed.

The owner accepted the corrected contract on 2026-07-30:

> A live PID without an exact matching recorded start identity is never terminated. The run remains `cancellation_pending`, uncertainty is recorded, and the repository lock remains held.

### 3.4 Root identity must be verified before descendant enumeration

The current cancellation path can enumerate descendants from a live root PID before proving that the live root matches the recorded root identity. Under PID reuse, this can inspect or target another process tree.

The exact root identity must be verified first. A mismatch proves the recorded root absent and forbids action against the new occupant. An unreadable identity produces uncertainty and forbids enumeration or termination.

### 3.5 Descendant attachment failure can leave a live tree

Failures during descendant enumeration, identity capture, or persistence can escape after the root has launched and been recorded. Identity-less descendants can also be skipped while attachment is still reported healthy.

Every post-launch attachment failure must contain the full owned tree, mark the binding unverified, and refuse healthy attachment. Containment failure remains durable uncertainty.

### 3.6 Parent-link enumeration is not a complete zero-descendant guarantee

The report correctly records that the proof is non-atomic. A root can exit or be killed before a late descendant is observed; the descendant may then be reparented and disappear from a root-based final sweep. Parent-table enumeration alone cannot satisfy the gate's claim that zero owned descendants is proven before terminal publication.

On Windows, the corrective package must use a kernel-backed Job Object or an equivalently strong owned-process containment primitive whose empty state can be queried after termination. A process-group or parent-table snapshot may remain supporting evidence, but it cannot be the sole terminal proof.

### 3.7 Required race and publication evidence is incomplete

The submitted package does not yet prove:

- cancellation racing normal exit through a dedicated interleaving test;
- root exits while a live descendant remains;
- cancellation publication fails after termination proof and succeeds on idempotent retry.

These are required before the process gate can close.

### 3.8 Canonical JobManager cancellation remains unsafe and host-dependent

`test_cancel_run_marks_cancelled` uses hard-coded PID `12345`. On this host, PID `12345` is a live unrelated process with start identity `12345:windows:134298559964499988`. The canonical local cancellation path stores `worker_identity` but not launcher or child identities and terminates its local PID set by number alone.

This is a product safety defect, not merely a flaky test. The corrective package must add exact launcher and child process identities to the canonical run plane and make cancellation identity-scoped.

## 4. Authority decision

The process boundary remains subordinate evidence. `RunStore` and `JobManager` continue to own cancellation state, terminal transition, lock release, and ResultPublication. `process_control` continues to own process identity and termination primitives.

The corrective work changes no authority count. It strengthens the canonical owner's evidence requirements and removes raw-PID action.

## 5. Disposition

- `V3-1A-PROCESS-IDENTITY-1`: implemented but not accepted;
- corrective subgate: [`V3_1A_CANCELLATION_AUTHORITY_1_GATE_2026-07-30.md`](V3_1A_CANCELLATION_AUTHORITY_1_GATE_2026-07-30.md);
- real Claude/Codex launch: forbidden;
- interaction commands and operational controller waiting: inactive;
- V3-1B: inactive;
- production activation and push: forbidden.
