# V3-1B-CONTROLLED-LIVE-KERNEL-OF-ONE-ACTIVATION-1 — Runtime Convergence Gate

**Date:** 2026-08-14
**Status:** ACTIVE
**Parent:** V3-1B Kernel of One
**Depends on:** accepted `V3-1B-PUBLIC-COMPANY-GATEWAYS-1` at `dd5ce955dbeb85d0b15f9b2d54d92f5671f2c714`
**Codex/provider generation:** forbidden
**Reasoning provider activation:** forbidden
**Push:** forbidden
**Legacy workflow/supervisor retirement:** forbidden

## 1. Objective

Converge the running Soma service onto the accepted 34-tool public Company gateway source, activate only the narrow owner-controlled Company Kernel capability required for a disposable Kernel-of-One proof, and verify live mechanical behavior without enabling a reasoning provider or inventing a second WorkPackage admission path.

Source capability is not treated as live capability until fresh runtime/public schema identity is verified.

## 2. Entry state

Accepted public Company implementation:

- implementation commit `5335f9f389e2e4d414051af6a3486e578be7e71b`;
- acceptance commit `dd5ce955dbeb85d0b15f9b2d54d92f5671f2c714`;
- accepted public tool count `34`;
- accepted public schema hash `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`;
- accepted operation inventory hash `7b61ecc4ef565357483c11168e55f3fa962e767a295a720453af7ca86f7f731f`.

Pre-activation live state intentionally remains the old 32-tool schema:

- public schema hash `f7dc8e9296b62e6f82843ba64a8a67078a4d9ff6dd1ecf7a6659f36097fab4a4`;
- operation inventory hash `3daa3f0443f7ffaec92fe5791df8a323b6e70a9aeb5375a4583bc53481d19045`.

`config.yaml` currently omits both `company_kernel` and `reasoning`, so their resolved defaults remain disabled before activation.

## 3. Runtime convergence proof

Before Company activation:

1. reload/restart Soma onto the accepted source;
2. verify clean-process import/startup, lightweight self-check and configuration validation;
3. verify live public inventory contains exactly the accepted Company additions `company_query` and `company_action`;
4. verify live tool count, public schema hash, operation inventory hash, metadata and flat public schemas converge with accepted source identity;
5. distinguish Soma service reload from any connector/discovery cache refresh required by the current client.

Any import/schema mismatch blocks activation until resolved.

## 4. Narrow Company activation

Only after runtime/schema convergence, enable:

```yaml
company_kernel:
  enabled: true
  executive_authority_ref: <trusted disposable proof authority>
```

Keep reasoning absent/disabled. Do not enable Codex, App Server, Responses/API generation, local/provider generation, scheduled autonomy or background reconciliation.

Validate the candidate config before reload and verify effective capability state afterward.

## 5. Disposable proof boundary

Use a disposable, explicitly scoped ProjectScope/repository binding. Prove as much of the accepted path as the architecture legitimately supports with reasoning disabled:

- Company/Mission bootstrap;
- immutable accepted PlanRevision and bounded WorkPackage graph;
- strict public query projections;
- version/CAS and idempotent replay behavior;
- receipt-only `reconcile_one`;
- explicit refusal of reasoning-specific `reserve_attempt` before mutation while reasoning is disabled;
- OutcomeAcceptance only when exact mechanically published Task/backend facts legitimately exist.

Do not fabricate a provider-free WorkPackage admission path and do not create synthetic Task/Run facts merely to complete the diagram. If the accepted admission authority cannot enter a canonical Task without reasoning, record that limitation as the truthful terminal boundary of this proof.

## 6. Legacy-path measurement

Measure, without retiring or rewriting them:

- whether `workflow_action.start` can still originate work;
- whether `supervisor_action.start` can still originate work;
- their overlap with Company/Task authority;
- compatibility/tests/users that would be affected by later retirement.

Retirement requires a separate reviewed package.

## 7. Required evidence

The gate can close only with recorded evidence for:

- accepted source/runtime/public schema convergence;
- live `company_query` and `company_action` discovery;
- reasoning provider still disabled;
- narrow Company Kernel activation with named trusted executive authority;
- disposable Company/Mission/Plan/WorkPackage proof and bounded projections;
- replay/idempotency/CAS behavior;
- reasoning-disabled `reserve_attempt` pre-mutation refusal;
- reconciliation receipt behavior;
- any legitimate OutcomeAcceptance proof, or an explicit statement why no mechanically valid provider-free acceptance facts exist;
- legacy workflow/supervisor start-path measurement;
- no Codex/provider generation, push, deployment, automatic acceptance or background scheduling.

## 8. Exit

Accept only if live behavior remains faithful to the accepted authority model. Any convenience change that would weaken authority, enable reasoning, synthesize execution facts, or create a second admission source of truth is outside this gate.
