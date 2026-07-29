# MEMORY-CONNECTOR-REFRESH-VERIFY-1 — Result

**Date:** 2026-07-29
**Status:** server side **verified**; ChatGPT connector side **not verified**
and cannot be from here. No code change was required.
**Authorisation:** owner instruction in session; no prior decision document.
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

## What remains, and who can do it

Verifying the ChatGPT connector requires refreshing that connector and calling
it, which cannot be driven from this session. The server-side precondition is
now proven, so any remaining failure is client-side.

Procedure for the owner, after refreshing the Soma connector in ChatGPT:

1. `system_query(operation="capability_identity")` — expect `ok: true`,
   `converged: true`, `mismatches: []`.
2. `knowledge_query(operation="memory_scope", repo_name="soma")` — expect the
   scope object, `canonical_health: healthy`.
3. `knowledge_query(operation="memory_health", scope=<the scope from step 2>)` —
   expect `canonical_count: 10`, `drifted_count: 0`.

Step 3 passing is what would make a fresh-controller claim on ChatGPT true.

## Correction needed in a sibling document

[`MEMORY_CONTROLLER_ERGONOMICS_1_RESULT`](MEMORY_CONTROLLER_ERGONOMICS_1_RESULT_2026-07-29.md)
§Operational connector note states that Claude Code, ChatGPT and Hermes "were
already verified end to end" in the closed trial. That conflicts with
[`MEMORY_REAL_PROJECT_TRIAL_1_RESULT`](MEMORY_REAL_PROJECT_TRIAL_1_RESULT_2026-07-28.md)
§Cross-controller verification — final, which records ChatGPT as never
exercised and Hermes as verified at the MCP boundary rather than through a full
agent session.

The two cannot both be right. This session cannot verify ChatGPT either way, so
the conflict is recorded rather than resolved: if the owner exercised ChatGPT
outside these sessions, the trial document should be updated with that evidence;
otherwise the ergonomics note should be corrected.

## Boundaries

Read-only verification. No code, schema, configuration or connector change. Two
outbound requests to the owner's own public MCP endpoint, which is the subject
of the verification.
