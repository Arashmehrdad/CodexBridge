# V3-1B-BOOTSTRAP-PLAN-AUTHORITY-1 — Acceptance Result

**Date:** 2026-08-14  
**Status:** ACCEPTED / CLOSED  
**Gate:** `docs/V3_1B_BOOTSTRAP_PLAN_AUTHORITY_1_GATE_2026-08-14.md`  
**Activation commit:** `e45db010e673103d768ec25419222dd43b605e77`  
**Implementation commit:** `8b07a944fa30a58ea506485b9435140c15acd21a`  
**Push:** none

## Result

The trusted Kernel-of-One root is implemented in source without activating a public Company Kernel or reasoning provider.

Accepted outcomes:

- additive `company_kernel` runtime configuration exists and is disabled by default;
- enabling requires a bounded trusted executive authority reference;
- caller executive identity is assertion-only and must exactly match trusted configuration;
- `bootstrap_company_mission` creates Company + Mission atomically under one `BEGIN IMMEDIATE` transaction;
- deterministic opaque Company/Mission identities and domain-separated request hashes are derived from canonical material;
- exact controller-request replay returns the same immutable root; changed material under that identity fails closed;
- new creation requires an exact active ProjectScope repository binding, resource identity and scope generation;
- Mission accountable owner and acceptance authority are both fixed to the immutable Company executive;
- injected faults before Company insert, after Company insert and after Mission insert leave zero partial root state;
- concurrent identical bootstrap converges to one root; conflicting concurrent requests produce one winner and one fail-closed result;
- the existing `accept_plan_graph` service successfully accepts/replays a PlanRevision DAG from a bootstrapped root and preserves current-plan CAS;
- no Task, Run, provider, scheduler, public company gateway, acceptance action or reconciliation path was introduced by bootstrap.

## Validation

Focused source/config/graph validation:

- `60 passed`
- Ruff: clean

Proportional adjacent Company Kernel / ProjectScope / reasoning regression:

- `143 passed`
- `git diff --check`: clean

The runtime service was not restarted for this source-only package because no public Company Kernel capability was activated. Production reasoning remains owner-disabled.

## Authority delta

New authority is intentionally narrow: trusted configuration may anchor one immutable Company executive and the internal bootstrap service may create/replay the corresponding Company/Mission root under exact ProjectScope. Plan/package authority remains the already-accepted `accept_plan_graph` service.

No new execution, result-publication, provider, scheduling, delegation, public-gateway or acceptance authority was created.

## Next package

Advance to `V3-1B-OUTCOME-ACCEPTANCE-1`: exact named-authority creation of one AcceptanceCommit from canonical Task/Run publication evidence. Public company gateways and live activation remain later gates.
