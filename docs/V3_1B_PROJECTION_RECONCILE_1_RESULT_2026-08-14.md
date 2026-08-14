# V3-1B-PROJECTION-RECONCILE-1 — Acceptance Result

**Date:** 2026-08-14
**Status:** ACCEPTED / CLOSED
**Implementation commit:** `bc0871f830c239e4eeaff7ae57398bd948670373`
**Gate:** `docs/V3_1B_PROJECTION_RECONCILE_1_GATE_2026-08-14.md`

## Result

The bounded internal Company Kernel projection and receipt-only reconciliation package is accepted.

Implemented source now provides:

- read-only Company, Mission, PlanRevision, WorkPackage and attempt projections rebuilt directly from canonical Company Kernel, ProjectScope, Task and selected-backend publication facts;
- no materialised WorkPackage lifecycle/result cache and no duplicate Task/Run execution authority;
- bounded Company mission references and bounded WorkPackage attempt lineage with total counts/truncation signals preserved;
- explicit lifecycle projections for admitted, queued, running, awaiting-controller, cancellation/recovery, uncertainty, terminal-unpublished, published-awaiting-acceptance, accepted, failed, superseded-route and scope-invalid states;
- acceptance-candidate projection only when the selected durable-Run or reasoning publication carries acceptance-grade mechanical evidence;
- provider-neutral reasoning projection without fabricating a canonical Run;
- receipt-only `reconcile_one` authority for `owner_turn -> no_op` and `package_completion -> acceptance_candidate_ready`;
- deterministic trigger replay/conflict handling with no Mission kernel-version mutation for receipt-only observations;
- fail-closed rejection of unsupported reconciliation transition names.

## Acceptance evidence

Focused validation after the final bounded-projection refinement:

- `tests/test_company_kernel_projection_reconcile.py`: **37 passed**;
- changed-file Ruff validation: **clean**;
- `git diff --check` over the implementation files: **clean**.

Immediately before the final bounded-list-only refinement, the full repository suite completed successfully:

- **3143 passed**;
- **35 skipped**;
- **1 xfailed**;
- **0 failed**;
- duration: **791.09 s**.

The final bounded-list refinement changes only projection response bounding and is covered by the final focused suite.

## Gate audit

The package meets its exit requirements:

- projections are reconstructed from canonical tables and fresh service instances without a materialised lifecycle cache;
- read-only projection calls do not create canonical Company/Task/Run mutations;
- ProjectScope invalidity, recovery and uncertainty remain visible and fail closed;
- immutable AcceptanceCommit remains authoritative for an already accepted historical outcome;
- durable-Run and fake-reasoning publication candidates are distinguished from terminal-unpublished and failed states;
- reconciliation creates at most one immutable receipt for an explicitly named trigger and never auto-accepts an outcome;
- unsupported transition names remain unavailable through this bounded service;
- no provider/model generation, Codex call, workflow/supervisor launch, external business mutation, deployment or push occurred.

## Preserved boundaries

This acceptance does **not** activate public `company_query` / `company_action`, live Company Kernel capability advertisement, reasoning-provider execution, scheduled reconciliation, worker-facing Soma MCP, Role/Assignment/delegation state, workflow/supervisor retirement, deployment or push.

## Next package

Advance to strict owner/executive public Company gateways. That package may expose the already-proven internal authorities only through exact discriminated request models, bounded projections, authority/version/idempotency checks and capability-honest runtime wiring. Live Company Kernel activation remains a separate later gate.
