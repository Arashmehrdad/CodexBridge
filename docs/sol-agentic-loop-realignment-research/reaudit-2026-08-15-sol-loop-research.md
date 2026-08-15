# Sol Agentic-Loop Research Re-Audit - 2026-08-15

Status: RE-AUDIT COMPLETE - implementation not authorized
Scope: Iterations 1-10, current Soma source, current public gateway inventory, and current official OpenAI Chat/Work/Codex product boundary
Purpose: adversarially test the research before implementation planning and identify any surviving Agent/Worker drift or unsafe simplification

## Executive verdict

The central research conclusion survives re-audit:

```text
Sol / Work owns semantic cognition
Soma owns durable operational state, execution, recovery, evidence, and continuation bookkeeping
optional specialists remain subordinate and explicitly chosen
```

The Agent/Worker realignment diagnosis also survives. Current source still contains the Company-specific reasoning-provider leakage identified in Iteration 8, and Git history confirms the August 12 reasoning-Task integration pivot identified in Iteration 10.

The re-audit found two material implementation corrections and several contract tightenings. None require restoring a reasoning worker, Supervisor, Workflow, Company, turn table, copied observation table, or second execution engine.

## Material correction 1 - continuation observation cannot be only a Task-row fingerprint

### Finding

Iterations 5 and 10 minimized continuation detection to a per-membership `last_consumed_observation_hash` computed from canonical Task fields.

That is directionally correct but too narrow if interpreted literally as a hash of only the `tasks` row.

Current Soma has controller-relevant mechanical truth outside the Task row. In particular, ProjectScope attempt state can enter `recovery_pending` or quarantine independently. Current TaskManager can record a ProjectScope attachment problem as a Task event while the Task backend projection itself may still remain running or otherwise fail to encode the complete scope problem in its row immediately.

Therefore this invariant is required:

> No controller-relevant mechanical change may occur in an authority linked to a continuation-associated Task without changing the continuation observation fingerprint or otherwise appearing as unconsumed continuation evidence.

### Corrected concept

Replace the implementation-level phrase `TaskObservationV1` with a broader bounded mechanical projection such as:

```text
ControllerObservationV1
    canonical Task action/lifecycle fields
    current ProjectScope binding/attempt projection when scoped
    current checkpoint/open-input projection
    result/evidence publication identity
    recovery/uncertainty projection
    existing event/watermark input where needed to prove no relevant transition is lost
```

The exact field set remains an implementation-design question and must be proven by tests.

The loop still stores only the **last consumed hash**, not a copied observation body.

No new observation/event table is required by this correction. Existing authoritative tables/events remain the source of truth.

### Lost-event rule

The implementation must pressure-test sequences where current state can return to a superficially similar value after an intermediate warning/recovery event. If the final aggregate projection alone cannot prove that Sol has seen all controller-relevant changes, include an existing authoritative event/recovery watermark in the hash domain rather than inventing a duplicate event store.

## Material correction 2 - lock-free reasoning does not mean fine-grained same-repository mutation concurrency

### Finding

The post-research multi-project amendment correctly states that Sol/controller reasoning and continuation bookkeeping must never own a repository operation lock.

Current `OperationLockStore`, however, is keyed by `repo_name`. That is a repository-wide mutation lock, not a fine-grained conflict detector.

Therefore the wording `only conflicting concrete mutations should serialize` is too strong if read as a statement about current Soma behavior.

### Corrected rule

```text
reasoning / planning / observation / continuation
    -> never owns repository/resource operation lock

concrete execution that requires an existing repository/resource lock
    -> serializes according to that resource authority's current lock granularity
```

The ControllerContinuation must **not widen** the current serialization domain or hold the lock longer. Refining repository mutation locking into sub-repository/worktree/conflict-aware locking would be a separate future resource-concurrency project, not part of the Sol-loop realignment.

### SQLite clarification

`lock-free reasoning` also does not mean SQLite can have unlimited simultaneous writers. Short atomic controller-loop transactions may briefly serialize on SQLite's own write coordination. The forbidden condition is holding a database write transaction while Sol reasons or while an external tool, backend, Task, owner response, or wake-up is pending.

## Contract tightening 1 - loop membership must not bypass ProjectScope

A loop is intentionally not required to belong to one project. It may span zero, one, or many Tasks and potentially more than one project.

That flexibility must not become an authority bypass.

Required invariant:

> `loop_id -> task_id` membership proves continuation/control relationship only. It does not grant repository/project access by itself.

For every scoped Task, continuation query/action paths must resolve and honor canonical ProjectScope identity/generation/status. A quarantined, generation-mismatched, or otherwise invalid scoped Task must surface as such rather than being readable/mutable merely because its Task ID is linked to a continuation.

The preferred approach is to derive current scope from ProjectScope rather than copy mutable scope truth into the loop row.

## Contract tightening 2 - deterministic Task request identity must be loop-namespaced

Current Task schema has a global unique index on `tasks(controller_request_id)`.

Iteration 7 correctly deferred exact request-ID derivation. Re-audit makes the requirement explicit:

> A continuation command that creates one or more Tasks must derive or allocate Task controller-request identities that are stable for replay and collision-safe across concurrent continuations/projects.

A suitable conceptual identity is derived from:

```text
loop_id
continuation command request identity
child/action index or stable action identity
```

The exact encoding is implementation detail. Replaying the same continuation command must return the same Task; a different continuation/action must never collide merely because a caller reused a human-readable request token.

## Revalidated findings

### Sol remains semantic authority - PASS

Nothing in current source requires a reasoning provider for the proposed normal-Chat loop. No new model/provider belongs in ControllerContinuation state.

### Company leakage diagnosis - PASS

Current Company admission still hard-wires generic WorkPackage attempt admission to:

```text
ReasoningSpecV1
TaskKind.REASONING
BackendKind.SOMA_REASONING
```

and the public Company reserve-attempt path still checks whether reasoning is enabled.

This remains the main Company-specific Agent/Worker leakage seam. Company repair should stay in its separate explicitly authorized lane.

### Historical drift pivot - PASS

Git history confirms commit `fcba03c2e553920d11b0300d72b51c0a44983bd4` on 2026-08-12 is `Soma: integrate provider-neutral reasoning Tasks`, matching the research timeline's principal architectural pivot.

### Atomic loop-to-Task reservation seam - PASS

`TaskStore.reserve_task_in_connection()` remains an appropriate connection-scoped insertion seam. ProjectScope, Company admission, and worker activation demonstrate caller-owned shared-transaction patterns. `ExecutionBackend.reserve()` remains inert with respect to starting external provider/process work in the inspected backends.

Backend launch must remain outside the SQLite ownership transaction.

### No second executor - PASS

A future loop coordinator should coordinate identity/ownership only and reuse TaskManager/backend launch, cancellation, reconciliation, evidence, and recovery authorities.

### Specialist positioning - PASS

Reasoning-provider machinery remains technically useful as optional subordinate specialist infrastructure. No Task failure, context-size threshold, or ordinary next-step requirement should automatically transfer cognition away from Sol/Work.

Codex remains explicit-owner-authorization only in this owner architecture.

### Company separation - PASS

Normal-Chat ControllerContinuation work does not require Mission/Plan/WorkPackage/Company and must not alter Company admission in the same patch.

### Public compatibility - PASS

The current public gateway inventory still contains 34 gateways, including Workflow, Supervisor, Task, and Company families. First Sol-loop implementation should not incidentally remove or rename existing public gateways. Whether loop operations add new gateways or are exposed through another clean topology remains a deliberate implementation-plan decision.

### Chat vs Work product boundary - PASS with wording discipline

Current official OpenAI product documentation still distinguishes Chat from Work and describes Work as the agentic, longer multi-step surface. This supports the architectural asymmetry used by the research.

Do not conflate Codex/Work goal-pursuit or continuation features with reasoning ownership. A Goal/long-running mode is a continuation/execution product capability; it does not imply that a separate reasoning brain is needed in Soma.

Subagent/provider implementation details should be treated as surface capability, not as a reason to put worker cognition into Soma's core.

## Revised minimal reasoning-continuation contract

**Terminology correction from owner clarification:** the **loop** is Sol's cognitive `reason -> act -> observe -> reason` cycle. The durable Soma component below is only continuation state; it must not be implemented as a Task loop, scheduler, stage runner, or autonomous workflow.

The minimal durable continuation authority remains three small logical authorities:

```text
controller_continuations
controller_continuation_tasks
controller_continuation_commands
```

No fourth copied-observation table is required by the re-audit.

However `controller_continuation_tasks.last_consumed_observation_hash` now means:

```text
last consumed ControllerObservationV1 hash
```

not `hash(tasks row)`.

The observation projection is computed from existing canonical authorities at query/ack time.

## Required implementation acceptance tests added by re-audit

1. ProjectScope attempt changes to recovery/quarantine while Task row remains otherwise unchanged -> continuation becomes unconsumed.
2. Controller-relevant Task event/recovery transition cannot occur and disappear without changing the continuation observation/watermark.
3. Checkpoint creation/resolution changes continuation observation correctly without a copied loop checkpoint authority.
4. Observation acknowledgement recomputes the complete aggregate projection and fails stale if any included authority changed.
5. Loop membership never bypasses ProjectScope project/generation/quarantine checks.
6. Two unrelated projects can reason/query/ack loops without repository operation locks.
7. Two loops concerning the same repository can reason/read/perform loop bookkeeping concurrently subject only to short SQLite transaction serialization.
8. Same-repository concrete mutations continue to obey existing repository lock granularity; ControllerContinuation does not claim finer concurrency than exists.
9. Loop-created Task controller request identities do not collide across simultaneous loops/projects.
10. Replayed continuation command resolves the same Task identities and never launches duplicate external effects.
11. Existing direct Task/tool path remains usable without ControllerContinuation.
12. Work direct use of Soma Tasks remains unaffected.
13. Reasoning provider disabled -> normal ControllerContinuation path still fully usable.
14. Company frozen/disabled -> normal ControllerContinuation path still fully usable.

## Findings explicitly rejected during re-audit

The following are **not** valid reasons to change the architecture:

- Goal mode exists, therefore reasoning architecture is solved.
- Goal mode exists, therefore Soma should become a reasoning worker.
- Work/Codex can use subagents, therefore Soma should mirror every subagent as a canonical Task.
- ProjectScope exists, therefore the loop should own a repository lock.
- SQLite briefly serializes a metadata write, therefore reasoning is not concurrent.
- Task is the canonical action identity, therefore every controller-relevant fact must live in the Task row.

## Final re-audit verdict

**PASS WITH TWO MATERIAL CORRECTIONS.**

The research is still suitable as the basis for a bounded implementation plan after the Iteration 10 synthesis is amended to incorporate:

1. aggregate `ControllerObservationV1` semantics instead of a Task-row-only observation fingerprint;
2. precise lock wording: no lock ownership for reasoning/continuation, current repository lock granularity unchanged by this lane;
3. ProjectScope enforcement on loop membership access;
4. deterministic collision-safe Task request identity for loop-created Tasks.

No evidence was found that justifies restoring the Agent/Worker reasoning architecture into the core path.

No runtime change, Company activation, reasoning-provider activation, Codex invocation, public gateway removal, source change, commit, or push is authorized by this re-audit.
