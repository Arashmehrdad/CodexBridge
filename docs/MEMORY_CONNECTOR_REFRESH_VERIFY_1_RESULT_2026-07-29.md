# MEMORY-CONNECTOR-REFRESH-VERIFY-1 — Result

**Date:** 2026-07-29
**Status:** **passed and closed.** The local server, public tunnel, and refreshed
ChatGPT connector all expose and execute the same contract. No code change was
required.
**Authorisation:** [`MEMORY_CONNECTOR_REFRESH_VERIFY_1_GATE_2026-07-29.md`](MEMORY_CONNECTOR_REFRESH_VERIFY_1_GATE_2026-07-29.md)
**Follows:** [`MEMORY_CONTROLLER_ERGONOMICS_1_RESULT_2026-07-29.md`](MEMORY_CONTROLLER_ERGONOMICS_1_RESULT_2026-07-29.md) §Operational connector note
**Branch:** `lane/memory-integration-foundation-1`

## Question

The ergonomics lane recorded that an already-open ChatGPT connector session
rejected `memory_scope` against its cached schema. Two candidate causes, and
they call for opposite responses:

1. the server does not actually publish the operation on the surface ChatGPT
   reaches — a real defect;
2. the server publishes it and the connector holds a stale cached schema — a
   client refresh, nothing to fix.

## Answer — cause 2, with evidence

`memory_scope` is published on **both** endpoints, including the public tunnel
that ChatGPT actually talks to. The local endpoint alone would not have settled
this: a stale or misrouted tunnel would look identical from the caller's side.

| | local `127.0.0.1:8000` | public `mcp.spaceshipgames.win` |
|---|---|---|
| tools advertised | 32 | 32 |
| `knowledge_query` operations | 18 | 18 |
| `memory_scope` advertised | **yes** | **yes** |
| live `memory_scope` call | `ok: true` | `ok: true` |
| `server_build_hash` | `cd134cfc…` | `cd134cfc…` |

Both endpoints serve the same build and the same contract. Nothing is wrong
with the server.

## The authoritative refresh signal

`system_query(operation="capability_identity")` exists for exactly this and was
verified to work, including its failure path:

- `public_schema_hash` / `live_input_schema_hash` — `b99de44a…`, computed from
  the **live effective input schemas**;
- `discovery_cache_generation` — `17b66e9b…`, what a connector should cache;
- `operation_schema_hashes` — 245 entries keyed `gateway.operation`, so a
  connector can identify *which* operation moved. `knowledge_query.memory_scope`
  is present and hashes to `3b7902e9…`;
- with deliberately stale values supplied it returned `ok: false`,
  `converged: false`, `mismatches: ["connector_public_schema_hash",
  "connector_discovery_cache_generation"]`, and
  `refresh_guidance: "refresh connector schema and discovery cache, then retry
  capability_identity"`.

Already regression-covered in `tests/test_tool_gateway_models.py`, so no new
test was warranted.

## Trap worth recording — `schema_hash` is not the schema's hash

Every public response carries `schema_hash: 42bdb69d…`. **It does not identify
the tool contract and never changes when the contract does.**

`server.py` stamps one process-wide constant onto every response,
`capability_metadata(PATCH_OPERATION_SCHEMA)` — a fixed schema about repo-patch
operations, unrelated to any gateway. Verified: `schema_hash(PATCH_OPERATION_SCHEMA)`
equals the live value exactly, while the real gateway schemas hash to entirely
different values.

Observed across four builds in this branch, spanning two added operations and
several added output fields:

| Build | Added | `schema_hash` |
|---|---|---|
| `a4954c21` | — | `42bdb69d…` |
| `8dacb8b7` | drift reporting | `42bdb69d…` |
| `1c7e387c` | `memory_accept_drift` | `42bdb69d…` |
| `cd134cfc` | `memory_scope` | `42bdb69d…` |

The knowledge gateways *do* pass their own output schema to
`_with_capability_metadata`, but it uses `setdefault` and the process-wide
constant is already stamped, so the per-gateway value never lands.

Anyone — a connector, or a person debugging exactly this — who compares
`schema_hash` to decide whether the contract moved gets "unchanged" when the
answer is "changed". `capability_epoch` does move, but only because its first
half is the build hash, which changes on every code edit.

**Use `public_schema_hash`, `discovery_cache_generation`, or the per-operation
hashes from `capability_identity`. Never `schema_hash`.**

Not fixed here: `schema_hash` is stamped on all 32 public gateways, so changing
its meaning is a public-contract change well outside a memory verification lane,
and the correct values are already exposed. Recommended as its own lane.

## Refreshed ChatGPT connector verification — passed

After the connector refresh, ChatGPT completed the gate through its connected
Soma surface:

1. `system_query(operation="capability_identity")` returned `ok: true`,
   `converged: true`, and `mismatches: []`. The effective contract identity was
   `public_schema_hash: b99de44a…`,
   `discovery_cache_generation: 17b66e9b…`, and
   `knowledge_query.memory_scope: 3b7902e9…`.
2. `knowledge_query(operation="memory_scope", repo_name="soma")` returned
   `ok: true` and the exact reusable scope
   `{"kind":"project","project_id":"proj_a144f759-1619-4276-9292-28704b6611f4","repo_name":"soma"}`,
   with `canonical_health: healthy`, `canonical_count: 10`, and the configured
   project vault root.
3. Passing that returned scope verbatim to `memory_health` returned
   `canonical_count: 10`, `indexed_count: 10`, zero malformed, zero unadopted,
   and `drifted_count: 0`; provider health remained honestly `degraded` and
   retrieval remained `catalog_lexical`.
4. Omitting `scope` from `memory_health` was rejected by the connected public
   input schema before execution. Discovery therefore did not become an
   inference path.

This closes the fresh-controller requirement for the newly added operation.
No memory record, packet, provider state, configuration, or repository source
was changed.

## Historical evidence reconciliation

There is no conflict in the current authoritative repository. The final
[`MEMORY_REAL_PROJECT_TRIAL_1_RESULT`](MEMORY_REAL_PROJECT_TRIAL_1_RESULT_2026-07-28.md)
records exact end-to-end evidence for all three controllers: ChatGPT packet
`pkt_84ca729a14c88027bb4f555a40c96315` with SHA-256
`aa743ec3240e24a9b7ee6901a096173d6b73862a1a9621119345c1f63a63b242`, and
Hermes packet `pkt_4bde9f78f4eb577d321f5fb7a4c699ff` with SHA-256
`9602b50e9fc3a5a60513d543eda3f8c4a05d3a523bbdb21d53763647a1c4641e`.

The contrary statement came from the trial's superseded partial closure state,
which existed before the later ChatGPT and Hermes evidence was delivered and
was corrected in commit `2821ee6`. This result now follows the current
repository authority rather than that stale view.

## Closure

`MEMORY-CONNECTOR-REFRESH-VERIFY-1` is closed with outcome **pass — stale
connector discovery resolved**. The public server contract was already correct;
a refreshed ChatGPT connector discovered and exercised it successfully.

## Boundaries

Read-only verification. No code, schema, configuration, credential, connector,
or memory change. The only expected failure was the deliberate missing-scope
request, rejected before runtime execution.
