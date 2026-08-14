# V3-1B-BOOTSTRAP-PLAN-AUTHORITY-1 — Trusted Kernel Root and Plan/Package Authority Gate

**Date:** 2026-08-14  
**Status:** ACTIVE  
**Parent:** V3-1B Kernel of One  
**Depends on:** accepted V3-1B schema/models and accepted Agent/Worker core  
**Provider activation:** forbidden  
**Push:** forbidden

## 1. Objective

Close the smallest missing authority beneath the already-accepted PlanRevision DAG and WorkPackage admission mechanics.

The package must provide one trusted Company/Mission root bound to one exact active ProjectScope and make the existing atomic graph-acceptance service usable as the internal current-plan/package authority. It must not create a second planner, lifecycle, task executor, result publisher, or public company surface.

## 2. Accepted mechanisms to reuse

The implementation must reuse, not fork:

- `CompanyKernelStore` and Company Kernel schema v3;
- immutable Company, Mission, PlanRevision and WorkPackage records;
- `accept_plan_graph` for atomic immutable PlanRevision + complete WorkPackage DAG acceptance and current-plan CAS;
- ProjectScope as project/resource/generation authority;
- canonical Task/Run as execution authority;
- Agent/Worker admission/dependency/evidence mechanics as already accepted.

## 3. Required outcomes

1. Add an owner-controlled Company Kernel runtime configuration with capability disabled by default and a bounded trusted executive authority reference.
2. Add an internal bootstrap service that atomically creates or replays exactly one Company and one Mission under one controller request.
3. Bootstrap must derive deterministic opaque IDs and request hashes from canonical request material; exact replay returns the same records and conflicting replay fails.
4. The requested executive assertion must equal the trusted configured executive reference. Callers cannot create, replace, delegate, or widen root authority.
5. Mission accountable owner and acceptance authority must equal that immutable Company executive.
6. Mission scope must resolve to an existing active ProjectScope repository/resource binding at the exact generation. Wrong repository, resource, project, lifecycle, generation, or unscoped requests fail before mutation.
7. Bootstrap is one `BEGIN IMMEDIATE` transaction. Crash/fault injection proves zero-or-both Company/Mission creation; response loss is replay-safe.
8. The existing `accept_plan_graph` service is exercised against the bootstrapped root and proves current-plan CAS, exact authority ceiling, graph immutability, and replay without inserting fixtures directly.
9. No public `company_query`/`company_action` gateway is added in this package.
10. No provider/model generation, worker launch, external mutation, scheduled reconciliation, or new generic lifecycle authority is introduced.

## 4. Configuration contract

The smallest accepted configuration shape is an additive `company_kernel` section containing:

- `enabled: false` by default;
- `executive_authority_ref`: bounded opaque non-secret reference, empty while disabled;
- optional display/default identity material only if required for deterministic bootstrap; do not store credentials or provider identity.

Enabling without a trusted executive reference must fail configuration validation. Configuration alone does not migrate or mutate the database.

## 5. Transaction and replay requirements

Bootstrap request identity must bind at minimum:

- company key/display name;
- mission key and canonical mission contract;
- exact project ID, repository name/resource identity, and scope generation;
- trusted executive assertion;
- controller request ID.

The service must reject:

- same request ID with different normalized material;
- existing Company key with conflicting content;
- existing Mission key with conflicting content;
- Company executive mismatch;
- inactive/archived/wrong-generation ProjectScope;
- pre-existing partial root that cannot be proven to be the exact replay.

## 6. Acceptance evidence

Required focused proof:

- config disabled/default and invalid-enabled cases;
- fresh bootstrap and exact replay;
- conflicting replay;
- wrong executive assertion;
- wrong project/resource/repository/generation/lifecycle;
- fault before Company insert, after Company insert, and after Mission insert with zero partial commit;
- concurrent identical bootstrap convergence;
- concurrent conflicting bootstrap one-winner/fail-closed behavior;
- bootstrapped-root `accept_plan_graph` first plan, exact replay, and stale/current-plan CAS rejection;
- existing ProjectScope/Task/Run rows unchanged except normal migration metadata if a disposable database is used;
- focused Ruff and proportional adjacent regression.

A broader suite is required only if the implementation touches shared gateway/runtime behavior beyond config and Company Kernel internals.

## 7. Explicit exclusions

- OutcomeAcceptance/AcceptanceCommit creation service;
- `reconcile_one` and company projections;
- `company_query` or `company_action` public tools;
- runtime capability advertisement of Company Kernel operations;
- real reasoning provider activation or Codex use;
- worker-facing Soma MCP or V3-2 capability broker;
- Role, Assignment, mandate/delegation product state;
- workflow/supervisor retirement;
- scheduler/background advancement;
- external business mutation;
- deployment, push, credentials, purchase, or release.

## 8. Exit

Close only when the trusted root and plan/package authority are proven against exact ProjectScope and replay/crash boundaries. Record an acceptance result, update `PLANS.md`, commit selected files locally, refresh canonical repository knowledge, and then advance to the separately bounded exact OutcomeAcceptance package.
