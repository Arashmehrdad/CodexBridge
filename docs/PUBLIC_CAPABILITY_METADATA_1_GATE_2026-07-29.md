# PUBLIC-CAPABILITY-METADATA-1 — Effective Contract Identity Gate

**Date:** 2026-07-29
**Status:** prepared for owner review; not authorised or executed.
**Decision level:** public connector contract and compatibility boundary.
**Evidence source:** [`MEMORY_CONNECTOR_REFRESH_VERIFY_1_RESULT_2026-07-29.md`](MEMORY_CONNECTOR_REFRESH_VERIFY_1_RESULT_2026-07-29.md) §Trap worth recording

## Problem

Every Soma public gateway response currently carries:

```text
schema_hash: 42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888
```

That value is derived from `PATCH_OPERATION_SCHEMA`, not from the effective
input or output contract of the gateway that produced the response. It remained
unchanged across builds that added operations and output fields.

The correct effective contract identities already exist through
`system_query(operation="capability_identity")`:

- `public_schema_hash` and `live_input_schema_hash`;
- `discovery_cache_generation`;
- per-operation hashes keyed as `gateway.operation`;
- build and capability-epoch identity;
- explicit mismatches and connector-refresh guidance.

The legacy field is therefore ambiguous: its name suggests a public contract
identity while its value describes an unrelated repo-patch schema. Silently
redefining it would be a second compatibility hazard because all 32 public
gateways expose it.

## Decision boundary

A future implementation lane may make public capability metadata unambiguous
without silently changing the meaning of an existing field.

The preferred compatibility direction is:

1. keep the current `schema_hash` value explicitly classified as a legacy field
   until consumers and compatibility impact are measured;
2. expose a clearly named effective public-contract identity derived from the
   same live schema objects used by discovery and runtime validation;
3. keep `capability_identity` as the authoritative detailed comparison and
   refresh surface;
4. document and test the relationship among build identity, effective public
   schema identity, discovery-cache generation, and per-operation identity;
5. deprecate or eventually remove the ambiguous legacy field only through an
   explicit versioned compatibility decision.

This gate does not preselect an exact new field name or removal schedule. The
implementing agent must first inventory current consumers and choose the
smallest compatible contract that satisfies the required outcomes below.

## Required outcomes

1. **Inventory the live meaning and consumers.** Identify every producer,
   schema, projection, test, document, connector path, and controller assumption
   involving `schema_hash`, `public_schema_hash`, `live_input_schema_hash`,
   `discovery_cache_generation`, operation hashes, and `capability_epoch`.
2. **Preserve compatibility deliberately.** No existing field may silently
   change meaning. Any legacy alias or deprecation must be explicit and covered
   by compatibility tests.
3. **One effective schema authority.** Discovery, runtime validation,
   capability identity, and any per-response effective-contract metadata must
   derive from the same effective public schema objects or generator.
4. **Correct movement properties.** A public operation or field change must
   move the effective contract identity and the affected operation hash. An
   unrelated implementation-only edit must not masquerade as a contract change.
5. **Connector-safe refresh.** A stale expected public schema or discovery
   generation must produce `converged: false`, exact mismatch names, and bounded
   refresh guidance; current expected values must converge cleanly.
6. **All gateways covered.** The solution must apply coherently across the full
   live public gateway inventory, not only memory or knowledge gateways.
7. **Honest projections.** Compact projections must retain enough identity to
   determine whether a response belongs to the expected effective contract.
8. **Documentation migration.** Controller guidance must state which fields are
   authoritative for contract comparison and which are legacy or informational.

## Required evidence

Acceptance requires:

- a machine-readable before/after inventory of all public metadata fields and
  their semantic owners;
- exact hashes for discovery, live validation, and every operation before and
  after one deliberate schema fixture change;
- proof that the intended global and affected operation identities move while
  unaffected operation identities remain stable;
- proof that an implementation-only fixture does not alter effective contract
  identity merely because the build changed;
- positive and stale-value `capability_identity` tests;
- connector discovery and invocation agreement through localhost and the public
  tunnel;
- compatibility tests for every retained legacy field;
- full gateway enumeration validation and proportional full regression;
- clean repository and no unrelated durable-state mutation.

## Explicit exclusions

This gate does not authorise:

- memory, research, task, run, workflow, supervisor, SSH, Trading Lab, Docker,
  Cloudflare, or repository-operation behaviour changes;
- connector cache deletion, credential changes, new permissions, or connector
  client implementation changes;
- changing operation input/output payloads except metadata required by this
  contract lane;
- a new transport, top-level gateway, task plane, or schema registry;
- semantic retrieval, personal memory, imports, provider work, or vault changes;
- deployment, public release, main-branch push, or unrelated cleanup;
- removal or silent reinterpretation of `schema_hash` without measured consumer
  evidence and explicit owner acceptance.

## Stop conditions

Stop and return a decision report without implementation if:

- current consumers of `schema_hash` cannot be identified sufficiently to
  preserve compatibility;
- the effective schema cannot be derived from the same objects used by live
  discovery and validation;
- a proposed fix requires silently redefining or deleting the legacy field;
- operation hashes fail to isolate the affected public operation;
- discovery and runtime schemas disagree at any point;
- the public tunnel does not expose the same build and contract as localhost;
- the change expands into gateway payload redesign or unrelated architecture;
- credentials, connector internals, deployment, or production state changes
  become necessary;
- unrelated owner work appears in the worktree.

## Acceptance outcome

The lane may close with either:

- **implemented-compatible** — effective contract identity is unambiguous,
  compatibility is preserved, all evidence passes; or
- **decision-only** — consumer or compatibility evidence shows that a safe
  additive contract cannot yet be selected. The exact blocker and next owner
  decision must be recorded without changing public semantics.

## Owner start language

A sufficient start instruction is:

> Start PUBLIC-CAPABILITY-METADATA-1 exactly as prepared. First inventory every producer and consumer of the public capability identity fields. Then implement only the smallest additive, compatibility-preserving contract that makes effective gateway schema identity unambiguous and derived from live discovery/runtime schemas. Do not silently redefine or remove `schema_hash`, change non-metadata gateway behaviour, touch connector credentials or internals, deploy, or widen into unrelated architecture. Stop with a decision report if compatibility cannot be proven.
