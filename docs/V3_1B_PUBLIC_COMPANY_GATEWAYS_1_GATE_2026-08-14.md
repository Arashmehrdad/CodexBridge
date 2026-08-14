# V3-1B-PUBLIC-COMPANY-GATEWAYS-1 — Strict Owner/Executive Gateway Gate

**Date:** 2026-08-14
**Status:** ACTIVE
**Parent:** V3-1B Kernel of One
**Depends on:** accepted bootstrap/plan authority, OutcomeAcceptance, bounded projections and receipt-only `reconcile_one`
**Live Company Kernel activation:** forbidden
**Reasoning provider activation:** forbidden
**Push:** forbidden

## 1. Objective

Expose the already-proven internal Company Kernel authorities through strict, bounded, owner/executive-facing public gateway contracts without creating a second source of truth or advertising a live capability before source/runtime activation converges.

This package is a public-contract and wiring gate. It does not turn on autonomous scheduling, provider execution or production business mutation.

## 2. `company_query`

Implement one discriminated-union read surface with operations:

- `capabilities`;
- `mission_status`;
- `current_plan`;
- `work_package`;
- `outcome_status`;
- `acceptance_commit`;
- `reconciliation_receipt`.

Queries must consume the canonical no-cache projection/record authorities rather than duplicate lifecycle state. Compact output must remain bounded; full output remains explicitly bounded by the public response budget.

## 3. `company_action`

Implement one discriminated-union mutation surface with operations:

- `bootstrap_kernel`;
- `accept_plan_revision`;
- `reserve_attempt`;
- `accept_outcome`;
- `reconcile_one`.

`accept_plan_revision` is intentionally the public name for the accepted atomic `accept_plan_graph` authority: one request carries the complete bounded WorkPackage DAG and creates/selects its immutable WorkPackages in the same transaction. There is no standalone `define_work_package` operation because the accepted graph architecture has no independent package-definition authority; adding one here would create a second mutation path solely to preserve an older proposal vocabulary.

`reserve_attempt` delegates to the accepted WorkPackage admission authority and therefore remains reasoning-route-specific until another provider-neutral admission authority is separately proven. It must refuse before mutation when the owner-controlled reasoning route is disabled.

Every operation delegates to the existing internal authority that already owns the transition. Gateway code must not reproduce transaction logic, create synthetic Task/Run rows or widen authority.

## 4. Strict request boundary

Every scoped write requires the exact fields its owning authority needs, including where applicable:

- Company/Mission/ProjectScope identities;
- project/resource/scope generation;
- controller request or trigger identity;
- expected Mission/plan/kernel version;
- expected immutable Company executive assertion;
- named accountable/acceptance authority where the internal request requires it;
- bounded canonical plan/package/route/evidence material;
- `extra='forbid'` request validation.

A caller value can assert expected authority; it cannot grant, expand, substitute or transfer root authority.

No Company gateway accepts raw credentials, arbitrary shell, deployment, provider-account control, external permission grants or legacy workflow/supervisor identity as authority.

## 5. Public response and capability rules

- public query/action projections remain non-authoritative views over canonical Company Kernel, ProjectScope, Task/Run and selected-backend facts;
- compact responses omit unbounded contract bodies and return hashes/opaque references/counts where possible;
- validation errors must identify the exact missing/conflicting field rather than collapse into a generic policy rejection;
- source registration, public metadata, operation inventory and schema fixtures must converge together;
- before the separate live activation gate, runtime capability must remain honest: current running Soma must not claim an operation that has not been restarted/activated and verified live;
- reasoning provider execution remains owner-disabled.

## 6. Required proof

- every query operation returns the same facts as the corresponding internal projection/record authority;
- every action operation delegates to the existing internal transaction authority and preserves its exact idempotency/version/scope behavior;
- malformed, extra-field, stale-version, wrong-scope and wrong-authority requests fail before mutation;
- compact/full response budgets are bounded and deterministic;
- acceptance/reconciliation responses never imply semantic auto-acceptance;
- `reserve_attempt` still ends at canonical Task admission; gateway code does not launch a provider directly;
- no synthetic Run is created for reasoning-backed Task state;
- public metadata descriptions satisfy the existing registration invariants and MCP description limits;
- operation inventories/schema hashes are updated intentionally and tested;
- existing public gateway, Company Kernel, Task, Run, ProjectScope and reasoning regression suites remain green;
- clean-process import/schema generation succeeds;
- full repository suite passes before closure;
- no live Company activation, provider generation, deployment or push occurs.

## 7. Explicit exclusions

- service restart/connector refresh and live Company Kernel activation;
- reasoning-provider/Codex activation or generation;
- background `reconcile_one`, recursive ticking or schedules;
- automatic/model-owned AcceptanceCommit creation;
- worker-facing Soma MCP or V3-2 dynamic capability delegation;
- Role/Assignment/department/team lifecycle;
- workflow/supervisor retirement;
- external business mutation, deployment, credentials, push or release.

## 8. Exit

Close only when strict public Company gateway source, schema, metadata, delegation and regression evidence are complete while the running service remains intentionally unactivated. Then advance to the separate controlled live Kernel-of-One activation gate for restart/refresh, disposable end-to-end proof and legacy-start measurement.
