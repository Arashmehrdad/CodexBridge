# V3-1B-PROJECTION-RECONCILE-1 — Derived State and One-Shot Reconciliation Gate

**Date:** 2026-08-14
**Status:** ACCEPTED / CLOSED
**Parent:** V3-1B Kernel of One
**Depends on:** accepted bootstrap/plan authority, Agent/Worker core, accepted provider-neutral OutcomeAcceptance
**Result:** `docs/V3_1B_PROJECTION_RECONCILE_1_RESULT_2026-08-14.md`
**Provider activation:** forbidden
**Public Company gateways:** forbidden
**Push:** forbidden

## 1. Objective

Add the smallest internal read-only projection authority for Company, Mission, current PlanRevision and WorkPackage state, plus one bounded `reconcile_one` receipt path for an explicitly named owner/package trigger.

The package must prove that company state can be reconstructed from canonical facts without a materialised lifecycle cache and that reconciliation remains a one-shot deterministic operation rather than a scheduler, hidden retry loop or second Task/Run authority.

## 2. Canonical-source rule

Projections derive only from existing authoritative records:

- immutable Company/Mission/PlanRevision/WorkPackage/WorkPackageAttempt/AcceptanceCommit facts;
- ProjectScope lifecycle, resource and current generation;
- canonical Task state, phase, checkpoint/recovery and backend identity;
- selected durable-Run or reasoning-backend publication evidence;
- immutable reconciliation receipts.

No WorkPackage status/result/publication column or projection cache may be added. Deleting all transient Python objects and rebuilding from the database must produce the same projection and mutate zero canonical rows.

## 3. Required bounded projections

### Company

Return immutable Company identity/executive authority plus bounded Mission references/counts. Do not infer business health or authority not stored by the Company Kernel.

### Mission

Return exact ProjectScope validity, current PlanRevision identity, plan/kernel versions and bounded package/outcome counts derived from the current plan. Archived/stale generation must be visible rather than hidden.

### PlanRevision

Return immutable revision/content identity, whether it is current, and bounded graph package/edge counts from canonical graph facts.

### WorkPackage

Return the route-neutral package/outcome identity and one derived lifecycle state from the accepted vocabulary:

- `not_started`;
- `attempt_admitted`;
- `queued`;
- `running`;
- `awaiting_controller`;
- `cancellation_pending`;
- `recovery_pending`;
- `uncertain`;
- `terminal_unpublished`;
- `published_awaiting_acceptance`;
- `accepted`;
- `failed_without_acceptance`;
- `superseded_route` for subordinate attempt projections;
- `scope_invalid`.

Precedence must fail closed: invalid ProjectScope outranks an active execution projection for new work; immutable AcceptanceCommit outranks backend lifecycle for the accepted historical outcome; uncertainty/recovery must never appear as published success.

The WorkPackage projection must expose bounded attempt lineage/identity without copying provider transcripts, raw command output or result bodies.

## 4. `reconcile_one` boundary

This package activates only the receipt-only transitions that require no second mutation authority:

1. `owner_turn -> no_op`;
2. `package_completion -> acceptance_candidate_ready`.

`acceptance_candidate_ready` is legal only when the exact current-plan WorkPackage projection is `published_awaiting_acceptance`. It records that a named package-completion trigger observed a mechanically eligible acceptance candidate; it **must not** create an AcceptanceCommit or decide semantic correctness.

`no_op` records one explicitly named owner turn with no target effect.

The schema's other reserved transition names (`plan_selected`, `package_defined`, `attempt_reserved`, `outcome_accepted`) remain unavailable through this bounded service until a later package proves atomic delegation to their owning authorities. `reconcile_one` must fail closed rather than pretending to perform them.

## 5. Receipt protocol

Inside one `BEGIN IMMEDIATE` transaction:

1. require Company Kernel schema current and internal capability only;
2. read the exact Mission and expected `kernel_state_version`;
3. require exact active ProjectScope project/resource/generation for a new receipt;
4. validate trigger kind/ref and requested transition pair;
5. for `acceptance_candidate_ready`, derive the exact current WorkPackage projection from canonical tables inside the same transaction and require `published_awaiting_acceptance`;
6. derive deterministic target/effect hash and reconciliation identity;
7. insert one immutable `KernelReconciliationReceipt`, or return an exact trigger replay;
8. commit.

The receipt does not increment Mission kernel state because it records an observation/coordination decision rather than changing Company/Mission/Plan/Package/Task/Run truth. A later unrelated kernel transition therefore does not invalidate exact historical trigger replay.

Changed transition, target, observed version or effect under the same `(mission_id, trigger_kind, trigger_ref)` must fail closed. Concurrent identical triggers converge to one receipt; conflicting triggers have one winner.

## 6. Acceptance evidence

Required proof:

- Company/Mission/current-plan/WorkPackage projections rebuild deterministically with no writes;
- fresh Python/store reconstruction returns identical projection objects/hashes;
- every declared WorkPackage lifecycle state used by this package has focused fixtures from canonical Task/backend/scope facts;
- durable-Run and fake-reasoning published outcomes both project `published_awaiting_acceptance` before acceptance and `accepted` after immutable AcceptanceCommit;
- reasoning projection creates no synthetic Run;
- awaiting-controller, cancellation, recovery, uncertainty, terminal-unpublished, failure, superseded-route and scope-invalid boundaries are honest;
- stale/archived ProjectScope is visible and blocks a new reconciliation receipt;
- `owner_turn/no_op` creates one receipt and exact replay is idempotent;
- `package_completion/acceptance_candidate_ready` requires exactly a current-plan published candidate and never creates AcceptanceCommit;
- unsupported transition names fail before mutation;
- same trigger with changed material fails;
- injected failures before/after receipt insert leave zero-or-one receipt and no other canonical mutation;
- identical/conflicting concurrent reconciliation requests converge deterministically;
- no Task, Run, provider, workflow, supervisor or external mutation is launched;
- focused Ruff, proportional Company Kernel/Task/ProjectScope/reasoning regression and full repository suite pass.

## 7. Explicit exclusions

- semantic acceptance or automatic AcceptanceCommit creation;
- public `company_query` / `company_action` gateways;
- live Company Kernel capability advertisement;
- reasoning provider activation or Codex use;
- dispatch of plan/package/attempt/acceptance mutations from `reconcile_one`;
- background scheduling, recursive ticking or hidden retry loops;
- materialised projection cache;
- worker-facing Soma MCP, Role/Assignment/delegation state;
- workflow/supervisor retirement;
- external business mutation, deployment or push.

## 8. Exit

**Accepted.** Projection reconstruction and the two receipt-only reconciliation paths are proven deterministic, bounded, fail-closed and mutation-free outside the receipt itself. The roadmap advances to `V3-1B-PUBLIC-COMPANY-GATEWAYS-1`; live Company Kernel activation remains a separate later gate.
