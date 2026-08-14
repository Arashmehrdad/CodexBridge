# V3-1B-CONTROLLED-LIVE-KERNEL-OF-ONE-ACTIVATION-1 — Runtime Convergence Gate

**Date:** 2026-08-14
**Status:** ACCEPTED / CLOSED
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

## 8. Acceptance evidence

### 8.1 Source/runtime convergence

- accepted public Company source entered from `5335f9f389e2e4d414051af6a3486e578be7e71b` / `dd5ce955dbeb85d0b15f9b2d54d92f5671f2c714`;
- controlled gate opened at `0ed0ff8bbc2e6529289b380e832a7fb3645e3f1a`;
- the server-only restart preserved the Cloudflare tunnel and converged the running process onto the accepted 34-tool source;
- final running/source server build hash: `967e9f4051187186d3f833ccefea6be64d413c5bc38563da2b453b11f290f5c4`;
- public schema hash remained the accepted `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`;
- operation inventory hash remained the accepted `7b61ecc4ef565357483c11168e55f3fa962e767a295a720453af7ca86f7f731f`;
- live inventory contains 34 gateways, including flat-root `company_query` and `company_action`;
- capability identity reports source/runtime convergence, no mismatches, no restart required and no connector refresh required.

A small capability-honesty defect was found during activation: `live_activation_gate_complete` was a hard-coded pre-activation `false`. It was corrected without broadening authority in commit `23e9ee3892ef7005777218c88415e2fe6bcf1256`. The live value is now derived only from owner-enabled Company Kernel configuration, a configured trusted executive and an installed/up-to-date Company schema. Disabled and pre-migration states remain false.

### 8.2 Narrow runtime activation and schema migration

The accepted live owner configuration is:

```yaml
company_kernel:
  enabled: true
  executive_authority_ref: "owner:kernel-of-one-live-proof-2026-08-14"
```

Reasoning remained absent/disabled throughout. Live capability evidence after the final restart reports:

- `runtime_enabled = true`;
- `trusted_executive_configured = true`;
- `reasoning_attempt_route_enabled = false`;
- `live_activation_gate_complete = true`;
- `automatic_outcome_acceptance = false`;
- `scheduled_reconciliation = false`.

Before schema installation the public capability correctly exposed the missing Company tables/indexes/triggers. A pre-migration SQLite backup was created at:

- `runs/activation-gates/soma-pre-company-kernel-20260814.sqlite3`.

The existing explicit `CompanyKernelStore.init_db()` authority then applied migrations `[1, 2, 3, 4]`. Final schema state is version 4, up to date, with no missing tables, indexes or triggers. `schema_state().active_capability` remains the existing static migration-state field and was deliberately not repurposed as live configuration state.

Config mutation backups were also retained at:

- `runs/activation-gates/config-pre-company-kernel-20260814.yaml`;
- `runs/activation-gates/config-pre-proof-repo-20260814.yaml`.

### 8.3 Disposable ProjectScope and Company proof

Disposable repository/profile:

- repo: `kernel_one_proof`;
- path: `runs/activation-gates/kernel-one-proof-repo`;
- ProjectScope project ID: `proj_repo_3b4a7a9954afaf5048a79a3b`;
- resource ID: `res_repo_3b4a7a9954afaf5048a79a3b`;
- scope generation: `1`;
- access mode: `exclusive`.

Live public MCP proof created:

- Company: `company_e12fee1e7714fb46330d0589`;
- Mission: `mission_2ad273451bd2778dc476dd23`;
- PlanRevision: `planrev_bcdbdb169e0cc983bea51273`;
- WorkPackage: `workpkg_c481415c275620556813ce9a`.

Bootstrap and PlanRevision acceptance each created exactly once; exact replay returned `created = false`. The accepted graph contains one bounded package and zero dependency edges. Mission projections reported `kernel_state_version = 1`, `plan_state_version = 1`, one current package, one open outcome and zero accepted outcomes. A different request attempting to re-accept content-identical plan material was rejected with `content-identical PlanRevision was accepted under different request metadata` rather than mutating canonical state.

Durable proof evidence is retained at:

- `runs/activation-gates/company-live-proof.json`.

### 8.4 Provider-free admission boundary and reconciliation

A structurally valid reasoning admission request was submitted while reasoning remained owner-disabled. Public `reserve_attempt` refused with:

`reserve_attempt is unavailable because owner-controlled reasoning is disabled`

Database evidence before and after the refusal remained:

- WorkPackage attempts: `0`;
- linked canonical Tasks: `0`.

Therefore the public gateway refused before attempt/Task mutation and no provider generation occurred.

No `OutcomeAcceptance` was fabricated. With no mechanically valid Task/Run/publication facts, there is no legitimate provider-free AcceptanceCommit to create. That is the truthful terminal boundary of this proof.

One bounded `reconcile_one` owner-turn produced receipt:

- `kreconcile_8f4e67b5af7d068b1d2f407b`;
- selected transition: `no_op`.

The receipt query reproduced the same transition, while kernel state remained version 1 and package/outcome state remained `not_started`. Reconciliation did not launch work, accept an outcome or schedule another transition.

### 8.5 Legacy start-path measurement

The legacy public orchestration surfaces remain live and were measured without retirement.

`workflow_action.start`:

- disposable workflow `20260814T155032Z_workflow_e3c196d4`;
- one `local_summary` step;
- completed successfully;
- `active_child_run_id = null`;
- confirms the legacy workflow path can still originate its own durable worker-backed work independently of Company/Task admission.

`supervisor_action.start`:

- disposable supervisor `20260814T155034Z_supervisor_d18eda79`;
- final state `needs_external_coder`;
- no active child;
- zero run links;
- current supervisor source explicitly creates an inert external-coder handoff and does not select/invoke Codex or another coding provider.

Repository compatibility search found 14 direct test references to `workflow_action` and 14 direct test references to `supervisor_action`, spanning public inventory, MCP discovery, flat-input contract, gateway models/server delegation and transport compatibility. Their removal therefore requires a separate reviewed retirement package and coordinated public-schema changes.

### 8.6 Final validation

Focused post-honesty-fix public Company/descriptor suite:

- run `20260814T155324Z_executable_profile_12fe5b19`;
- `284 passed, 26 skipped`;
- exit code `0`.

Final full repository regression against the live-activation source:

- run `20260814T155620Z_executable_profile_6b44b1f4`;
- `3168 passed, 35 skipped, 1 xfailed, 0 failed`;
- exit code `0`;
- duration `940.93s` pytest / `942.583s` durable run.

Focused Ruff validation:

- run `20260814T161239Z_executable_profile_a0d889ce`;
- `All checks passed!`;
- exit code `0`.

No Codex CLI, Codex App Server, OpenAI provider generation, reasoning provider generation, push, deployment, automatic outcome acceptance or background Company scheduling occurred. The protected `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` and `docs/patch-auto-repair-research/*` files remained excluded and untouched.

## 9. Exit

**ACCEPTED / CLOSED.** The live runtime is converged onto the accepted 34-tool Company gateway source, the Company Kernel schema and narrow owner-controlled capability are live, and the disposable provider-free Kernel-of-One proof preserves the accepted authority model. The remaining inability to reserve a Company attempt while reasoning is disabled is an intentional architecture boundary, not a failed activation.

Legacy workflow/supervisor retirement is explicitly deferred to a separate package. No convenience path was added, no second WorkPackage admission source was created, and no semantic acceptance authority moved into Soma.
