# G4 Protected Mutation Broker Acceptance - 2026-08-12

STATUS: ACCEPTED

## Authority and range

- Canonical implementation plan: `docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md`
- Canonical plan SHA-256: `fa2afb72e51e5cc4494f29b7470eb33cd8a951144a2bc78db5e65a6d8301bea2`
- G3 accepted baseline: `ac0ad3c7c38256924e27fd4e850ff27094730083`
- G4 implementation head before this acceptance record: `b2a69c8e033975bea0723bcccdef35b025867a94`
- Branch: `lane/memory-integration-foundation-1`

G4 implementation checkpoints:

1. `c589199028f7a860bd9c3cb68be2d15f1c90dc6e` - protected mutation contracts;
2. `3d1b8bffd831bdd60aeaac10267b32ada743a966` - durable protected-effect idempotency/store;
3. `4375e21470e73796b806ae86947adfab23cab45a` - mechanical protected mutation broker;
4. `b2a69c8e033975bea0723bcccdef35b025867a94` - durable resource serialization, uncertainty containment, and cross-plan proof.

## Accepted architecture

G4 adds a provider-neutral protected mutation boundary beneath canonical Tasks without creating a second execution lifecycle or granting provider-native agents authority.

The authority chain remains:

`Mission -> PlanRevision -> WorkPackage -> WorkPackageAttempt -> canonical Task -> protected call -> exact effect evidence`.

Provider-local IDs and child-agent identities remain provenance only. They do not create mutation authority, canonical effect identity, or additional resource ownership.

### Protected call/effect contracts

`ProtectedToolCallV1` binds the exact Soma authority/effect material required before a protected mutation can begin, including Task/Attempt/backend identity, mandate, ProjectScope generation, capability, tool-operation contract, resource key, Soma-issued idempotency key, payload hash, expected Task state version, expiry, and mutation class.

Provider provenance and call correlation are deliberately excluded from canonical request identity. Repeated provider-local children/retries therefore cannot multiply canonical authority.

`ProtectedToolEffectV1` records one of:

- `prevented`;
- `rejected`;
- `acknowledged`;
- `outcome_unknown`.

Acknowledgement requires exact external-effect identity. Completion timestamp does not alter canonical effect identity.

### Durable idempotency and effect boundary

The protected-tools schema is an additive independent component. Canonical call reservation and provider provenance are durable before effect execution.

Delivery state is explicit:

`reserved -> effect_begun -> resolved`.

Exact replay converges to the existing canonical call/effect. Same Soma idempotency key with changed authority/tool/resource/payload is a hard conflict.

Once the effect boundary has been crossed, an ambiguous transport/create result is represented as `outcome_unknown`; automatic blind resend is forbidden. Cancellation arriving after the boundary does not fabricate reversal.

### Mechanical broker validation

Before crossing the protected-effect boundary the broker revalidates durable Soma facts, including:

- exact canonical Task identity/state/state-version/backend binding;
- exact WorkPackageAttempt binding and current PlanRevision;
- absence of a durable successor Attempt;
- cancellation precedence;
- exact ProjectScope project/resource/generation and attached lifecycle;
- mandate ref/hash/version;
- capability ref/hash;
- tool-operation ref/hash;
- Soma idempotency authority;
- required approval evidence when applicable;
- expiry;
- actual payload bytes against payload hash;
- exact resource ownership.

Mandate/capability/tool-operation/idempotency/approval facts are supplied through a Soma-controlled mechanical resolver protocol. Natural-language provider confidence is never authority.

G4 uses deterministic fake protected adapters only. No production or external protected mutation adapter is activated.

### Durable resource serialization and uncertainty containment

Protected-resource leases are durable and keyed by exact `resource_key`, canonical call, Task, and WorkPackageAttempt identity.

Lease states are:

- `held`;
- `uncertain`;
- `released`;
- `contained`.

A partial unique index permits only one `held`/`uncertain` lease per resource while preserving historical lease rows.

Accepted mechanics:

- independent resources may be held concurrently;
- the same resource serializes protected writers;
- an acknowledged or rejected durable effect releases the lease;
- `outcome_unknown` moves the lease to `uncertain` and blocks replacement writers across restart;
- uncertainty can be cleared only by exact mechanical containment evidence bound to the original request hash;
- broker replay repairs the crash window where a terminal acknowledged/rejected effect was persisted before lease reconciliation;
- caller-supplied effect objects cannot release a lease unless matching exact durable protected-effect evidence exists.

### Old-plan/new-plan contention

The integrated G4.4 fixture proves the frozen replan rule:

- an old-plan protected writer can cross the effect boundary and become `outcome_unknown`;
- selecting a new PlanRevision does not automatically cancel the old Task;
- old and new read-only reasoning Tasks can coexist as running canonical Tasks;
- the replacement current-plan writer passes current-plan validation but is blocked from the same resource by the old uncertain lease;
- replay of the old protected call after restart never resends the external effect;
- exact containment evidence changes the old lease from `uncertain` to `contained`;
- only then may the current-plan replacement acquire the resource and execute once;
- its acknowledged effect releases the resource normally.

This preserves the distinction between semantic replanning and physical mutation containment.

## Validation evidence

Protected-tool focused gate after G4.4 integration:

- run: `20260812T115836Z_executable_profile_af350d59`;
- result: `80 passed`;
- failures: `0`.

Cross-plan/restart integration proof after formatting:

- run: `20260812T120234Z_executable_profile_646dee32`;
- result: `2 passed`;
- Ruff check: passed;
- Ruff format-check: passed (`7 files already formatted`).

Broad affected regression gate covering protected tools, canonical Task, ProjectScope, Company Kernel, reasoning backend, dependency/FanIn and worker substrate:

- run: `20260812T115944Z_executable_profile_e97db69a`;
- result: `614 passed, 1 xfailed`;
- failures: `0`;
- duration: `114.63s`.

### Full-suite Gate 4

Authoritative complete repository suite:

- run: `20260812T120336Z_executable_profile_49ef471a`;
- result: `2933 passed, 35 skipped, 1 xfailed`;
- failures: `0`;
- duration: `727.25s (0:12:07)`;
- exit code: `0`;
- stdout protected-evidence SHA-256: `1031e302675959cfdbbde82d8eb9dc2578e36bb78e9eff5e5ed5c644e8c4980f`;
- terminal result source SHA-256: `ec21ee356b892f4eadf4e0794937d2d5ceecfef4183ad2d21dcc4ce7a8544529`.

Gate 4 therefore has focused, broad affected, restart/contention, quality, and complete-repository acceptance evidence.

## Non-architectural execution observations

Two environment/tooling events did not invalidate G4:

1. one direct `python -m pytest` invocation resolved to LibreOffice's bundled Python and failed because that interpreter does not contain pytest; subsequent broad/full gates used the repository's canonical `scripts/run_pytest.ps1` launcher and `.venv` interpreter;
2. unrelated short-lived network maintenance runs launched through Soma temporarily owned the repository execution lease; G4 mutations waited for those runs to become terminal and did not cancel or include their work.

Neither event changed production source or acceptance semantics.

## Negative-boundary verification

G4 did not:

- launch or spend quota on a real reasoning provider;
- perform a real external protected mutation;
- grant provider-native children independent mutation authority;
- add a second WorkPackage/Task lifecycle;
- expose a public reasoning start operation;
- add or change public MCP operations;
- change the accepted public schema hash `84d0af8b66d7df990320268ba905bf536cbb2722dfabf6cda30aaa5e93f9012c`;
- restart the live Soma service;
- refresh the ChatGPT connector;
- push any commit;
- touch the parked `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` owner file;
- touch or include concurrent patch-auto-repair research files.

The running Soma service remains unactivated for the new internal G4 source capability.

## Gate verdict

G4 is ACCEPTED.

Soma now has a provider-neutral, restart-safe, mechanically authorized protected-mutation broker with durable idempotency, exact resource serialization, explicit `outcome_unknown` retention, cross-plan containment safety, and deterministic fake-tool regression evidence.

The next roadmap boundary is G5 - real read-only reasoning-provider pilots. Per the canonical plan, every G5 substage requires fresh explicit owner authorization naming the pilot and cost ceiling, and current official provider documentation must be rechecked before provider execution.
