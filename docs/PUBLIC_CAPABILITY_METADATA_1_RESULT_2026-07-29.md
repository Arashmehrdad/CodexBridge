# PUBLIC-CAPABILITY-METADATA-1 — Result

**Date:** 2026-07-29
**Status:** closed **implemented-compatible**.
**Authorisation:** [`PUBLIC_CAPABILITY_METADATA_1_GATE_2026-07-29.md`](PUBLIC_CAPABILITY_METADATA_1_GATE_2026-07-29.md)
**Branch:** `lane/memory-integration-foundation-1`

## Inventory (required outcome 1)

| Field | Produced by | Derived from | Moves when |
|---|---|---|---|
| `schema_hash` | `_PROCESS_CAPABILITY_METADATA`, every response | `PATCH_OPERATION_SCHEMA` — a fixed repo-patch schema | **never** |
| `server_build_hash` | same | source tree | any code edit |
| `capability_epoch` | same | `build[:12]-schema[:12]` | any code edit |
| `public_schema_hash` **(new on responses)** | response wrapper | live advertised input schemas | a public input-contract change |
| `public_schema_hash` / `live_input_schema_hash` | `capability_identity` | same live schemas | same |
| `discovery_cache_generation` | `capability_identity` | inventory + public schema + build + epoch | contract **or** build |
| `operation_schema_hashes` | `capability_identity` | per-operation input schemas | that operation only |

Two facts shaped the design:

- **Only one of 32 gateways has a strict output schema** (`knowledge_action`,
  `additionalProperties: false`). It is also the gateway whose strict schema
  caused a successful write to be reported as a failure during the memory
  trial. An additive field is therefore safe, and that is exactly where it had
  to be declared.
- **Hermes already owns `effective_schema_hash`** for its own registry. Reusing
  that name would have collided across two unrelated contracts, so the new
  field takes the name `capability_identity` already uses for the same value.

## What changed

`public_schema_hash` is now stamped on every public response, carrying the same
value `capability_identity` reports, computed by the same generator from the
same served schemas.

`schema_hash` is untouched — same value, same meaning, same position. Nothing
was redefined, aliased or removed, and a compatibility test pins it to
`schema_hash(PATCH_OPERATION_SCHEMA)`.

### The trap inside the implementation

The obvious implementation — hash `tool.parameters` at registration — is wrong,
and silently so. FastMCP **dereferences `$defs` and inlines the union branches
when it advertises a tool**, so the held schema is not the schema a connector
caches. Hashing it produces an identity that looks authoritative and that no
client could ever reproduce.

The first version did exactly that. The agreement test caught it: 31 of 32
gateways differed, and `cancel_run` was missing entirely because the
non-flattened registration path returns no tool object.

Identity is therefore computed from **served discovery**, pre-warmed once in
`run_server` after all registration and before serving, because every registry
accessor is async and a response cannot drive discovery from inside the event
loop. `public_contract_hash()` returns `""` rather than guessing if discovery
has not run and cannot be driven — an absent field is honest, a wrong one is
not.

`tests/test_capabilities.py` asserts the response value equals the
discovery-derived value, so the cheap field and the authoritative one cannot
drift apart unnoticed.

## Evidence

Live on build `65355409`, both endpoints, after restart:

| Check | Result |
|---|---|
| `public_schema_hash` on `knowledge_query`, localhost | `b99de44a…` |
| `public_schema_hash` on `system_query`, localhost | `b99de44a…` |
| both, through the public tunnel | identical |
| legacy `schema_hash`, everywhere | `42bdb69d…`, unchanged |
| `capability_identity` with the correct expected value | `converged: true`, `mismatches: []` |
| `capability_identity` with a stale value | `converged: false`, `mismatches: ["connector_public_schema_hash"]`, refresh guidance |

**Movement properties, proven live rather than only in tests.** This lane
changed response metadata, output schemas and tests — no public *input*
operation. Across the restart:

| | before | after |
|---|---|---|
| `server_build_hash` | `cd134cfc…` | `65355409…` |
| `public_schema_hash` | `b99de44a…` | **`b99de44a…`** |

The build moved and the contract identity did not. That is required outcome 4
demonstrated on the running server: an implementation-only edit cannot
masquerade as a contract change. The complementary direction — a public
operation change moving the identity while unaffected gateways stay stable — is
covered by a fixture test.

Note `discovery_cache_generation` *does* move on an implementation-only edit,
because it deliberately mixes in the build hash. That is correct for its job:
it answers "should I refresh my cache?" conservatively, while
`public_schema_hash` answers "did the contract change?" precisely.

Full suite: 2258 passed, 35 skipped.

## Compatibility work the change forced

Adding one envelope field surfaced three places that had each restated the
capability key set by hand:

- the chat-footprint evidence comparison stripped a hardcoded set before
  comparing a gateway response to the stored authoritative record. The new
  field leaked straight into an evidence comparison. `CAPABILITY_METADATA_KEYS`
  now lives in `soma/capabilities.py` and the test imports it, so the next
  envelope field cannot repeat this;
- two byte-budget tests assert `payload_bytes`/`response_bytes` equal the
  encoded response. The three legacy tags are counted before accounting runs;
  the new field is stamped after. Those tests now exclude **only** the new
  field, so every existing assertion stays exactly as strict as it was.

## Controller guidance

- **To compare contracts:** `public_schema_hash`. Per-operation:
  `operation_schema_hashes[gateway.operation]` from `capability_identity`.
- **To decide whether to refresh a cache:** `discovery_cache_generation`.
- **Legacy, informational only:** `schema_hash` — it describes an unrelated
  repo-patch schema and never moves. Do not compare it to detect contract
  change.

## Not done, deliberately

`schema_hash` is not deprecated, renamed or removed. The gate requires measured
consumer evidence and explicit owner acceptance first, and no consumer inventory
outside this repository exists. It remains a live field with an unchanged value.
