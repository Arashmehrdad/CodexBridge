# Agent/Worker Core Acceptance - 2026-08-14

Status: `CORE_ARCHITECTURE_ACCEPTED`

## Decision

The required Agent/Worker core is accepted.

The durable authority chain is now:

```text
Sol
 -> immutable bounded PlanRevision DAG
 -> WorkPackage admission + exact dependency proofs
 -> canonical Task lifecycle
 -> provider-neutral backend
 -> bounded EvidenceSubmission
 -> deterministic FanIn
 -> Sol semantic adjudication
```

No second work-unit lifecycle was introduced. Provider-local identity remains evidence/provenance rather than canonical authority.

## Gate evidence

- G1 graph contracts: ACCEPTED.
- G2 provider-neutral reasoning Task and bounded evidence: ACCEPTED.
- G3 deterministic DAG admission, dependency proofs, fan-out/fan-in, restart/replay: ACCEPTED.
- G4 provider-neutral protected mutation broker and effect idempotency: ACCEPTED.
- G5 measured read-only provider route: ACCEPTED under the historical owner-approved provider budget.
- G6 provider contract: ACCEPTED under the owner-directed v10 budget closure; concurrency result remains explicitly inconclusive.
- Public normal-Chat surface: ACCEPTED as `EXISTING_TASK_SURFACES_ONLY` using `task_action.start_reasoning` and `task_query.evidence`.

G6.4 and G7 remain deferred optimization/research gates. They are not represented as completed and do not set runtime topology.

## Runtime activation boundary

Production reasoning remains disabled by default and is not currently advertised by live Task capabilities.

Live post-restart capability evidence contains only:

```text
task_kinds = [durable_command]
backends = [soma_durable_run]
```

Therefore this core acceptance does not activate or consume the optional provider route.

## Final regression audit

A clean detached-worktree validation was used so unrelated concurrent Soma implementation work could not contaminate the Agent/Worker acceptance result.

Committed source validated at:

```text
c0197775807386f2ec857a5ce71b57fa3a7855ec
```

Full pytest result:

```text
3037 passed
35 skipped
1 xfailed
0 failed
```

Focused Agent/Worker/public-contract validation previously passed:

```text
194 passed; focused Ruff clean
21 reasoning lifecycle/recovery tests passed; focused Ruff clean
33 public metadata/discovery tests passed; focused Ruff clean
```

Whole-repository Ruff was also probed. It reported ten pre-existing/unrelated lint findings in memory-pilot, memory-guard, reconciliation, and cancellation-authority files outside this lane. Those files were not modified to manufacture a clean result. Changed Agent/Worker and public routing files are Ruff-clean.

## Runtime convergence audit

After the final descriptor commit Soma was restarted.

```text
self_check = 10/10 green
server_build_hash = 8e00552c0d51934e9370e8fe07c54df4ff7af096c30ef2c756ec12dbd8ee8611
public_schema_hash = f6b6ac6936ce5a424489120e712372906b0f410426e4c43120feb14c13536d8b
```

No stale Soma repository lock remains part of this acceptance.

## Definition-of-done disposition

Required core properties 1-12 and 15-17 are satisfied by the accepted gate records and final regression/runtime audits.

Properties 13-14 are intentionally treated as deferred optimization gates under the owner-directed G6 budget closure:

- no benchmark-selected concurrency winner is claimed;
- runtime concurrency stays bounded;
- provider-native subagent benchmarking remains separate and deferred;
- neither result is used to set the accepted public surface or runtime authority.

## Preservation

No push was performed.

Concurrent owner memory and patch-auto-repair files were left untouched.

No live provider generation was used to implement or validate the public reasoning activation stage.

## Final gate

`AGENT_WORKER_CORE_ACCEPTED`

`PROVIDER_ROUTE_OWNER_DISABLED`

`CANONICAL_CONCURRENCY_UNSELECTED`

`G6_4_DEFERRED`

`G7_DEFERRED`

`NO_PUSH`
