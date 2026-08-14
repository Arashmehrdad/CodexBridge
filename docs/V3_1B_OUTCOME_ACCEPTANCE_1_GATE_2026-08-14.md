# V3-1B-OUTCOME-ACCEPTANCE-1 — Exact Outcome Acceptance Authority Gate

**Date:** 2026-08-14  
**Status:** ACTIVE  
**Parent:** V3-1B Kernel of One  
**Depends on:** accepted bootstrap/plan authority, Agent/Worker core, canonical Task/Run publication authority  
**Provider activation:** forbidden  
**Push:** forbidden

## 1. Objective

Add the smallest internal authority that can create exactly one immutable `AcceptanceCommit` for one WorkPackage outcome after an explicitly named acceptance authority has reviewed exact canonical execution/publication evidence.

Process success, Task completion, Run publication, evidence quality, verifier confidence, or dependency satisfaction must never auto-accept an outcome.

## 2. Required authority chain

One acceptance request must bind exactly:

- Company, Mission, current PlanRevision, WorkPackage and outcome identity;
- one exact WorkPackageAttempt, canonical Task and canonical Run;
- exact active ProjectScope project/resource/generation;
- terminal successful canonical Task state and matching backend Run identity;
- terminal successful Run state with no uncertainty or safety failure;
- durable `result_publication_status='published'`;
- exact `result_published_hash` and authoritative `public_result_source_sha256` from Run publication metadata;
- Mission/WorkPackage acceptance authority equal to the immutable Company executive;
- explicit acceptance basis reference and SHA-256 hash;
- expected Mission kernel state version;
- controller request/idempotency identity.

## 3. Transaction protocol

Inside one `BEGIN IMMEDIATE` transaction:

1. verify Company/Mission authority and expected Mission kernel version;
2. verify Mission scope is still active and exact and its PlanRevision is current;
3. verify WorkPackage/outcome belong to that current Mission/PlanRevision;
4. verify WorkPackageAttempt binds that exact WorkPackage/outcome and Task;
5. require ProjectScope exact Task/Run attempt binding;
6. require canonical Task terminal success and exact backend Run reference;
7. require canonical Run terminal success, non-uncertain, non-safety-failed, published result metadata and exact supplied hashes;
8. require named acceptance authority equals Company, Mission and WorkPackage acceptance authority;
9. require non-empty acceptance basis reference and valid basis SHA-256;
10. derive deterministic acceptance identity/request hash, insert immutable AcceptanceCommit or verify exact replay;
11. increment Mission `kernel_state_version` with compare-and-set;
12. commit.

Exact request replay must return the existing AcceptanceCommit without incrementing state again. Changed material under the same controller request or already-accepted outcome must fail closed. Concurrent conflicting acceptance requests have one winner.

## 4. Canonical-source rule

Do not reconstruct success from public projections when authoritative stores are available. Read Task and Run records from their canonical durable stores/transactional tables. Reuse existing publication hashes and ProjectScope assertions; do not create a parallel result or scope truth.

## 5. Acceptance evidence

Required focused proof:

- happy-path acceptance from a fully canonical Task/Run publication fixture;
- exact request replay;
- same controller request with changed basis/hash/evidence fails;
- second request for already accepted outcome fails;
- wrong Company/Mission/PlanRevision/WorkPackage/outcome/attempt/Task/Run fails;
- stale or archived ProjectScope fails for a new acceptance;
- non-current plan fails;
- non-terminal/failed/cancelled/uncertain Task or Run fails;
- Task backend Run mismatch fails;
- unpublished Run fails;
- publication hash or public source SHA mismatch fails;
- wrong acceptance authority fails;
- missing/invalid acceptance basis hash fails;
- stale Mission kernel version fails;
- faults before insert, after insert and before/after Mission CAS leave old-or-new atomic state only;
- concurrent identical acceptance converges; concurrent conflicting acceptance has one winner;
- accepted-outcome dependency proof consumes the resulting AcceptanceCommit exactly;
- no provider/model call, new Task/Run, external mutation or public gateway occurs;
- focused Ruff and proportional Company Kernel/Task/Run/ProjectScope regression pass.

## 6. Explicit exclusions

- semantic auto-acceptance or model-owned acceptance authority;
- `reconcile_one` or derived public projections;
- `company_query` / `company_action` public tools;
- live Company Kernel capability advertisement;
- reasoning provider activation or Codex use;
- worker-facing Soma MCP / V3-2 capability broker;
- Role/Assignment/delegation state;
- scheduled/background advancement;
- workflow/supervisor retirement;
- external business mutation, deployment or push.

## 7. Exit

Close only when exact acceptance authority, publication evidence, ProjectScope, replay, crash and concurrency boundaries are proven. Then advance to the separately bounded projection + `reconcile_one` package; public gateways and live activation remain later gates.
