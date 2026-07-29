# MEMORY-CONNECTOR-REFRESH-VERIFY-1 — Refreshed ChatGPT Connector Gate

**Date:** 2026-07-29
**Status:** owner-authorised gate prepared; not executed.
**Decision level:** verification-only. No implementation authority.
**Follows:** [`MEMORY_CONTROLLER_ERGONOMICS_1_RESULT_2026-07-29.md`](MEMORY_CONTROLLER_ERGONOMICS_1_RESULT_2026-07-29.md)
**Owner authorisation:** explicit instruction on 2026-07-29 to prepare the next gate after the controller-ergonomics closure correction.

## Decision

One bounded verification gate may refresh the ChatGPT-to-Soma connector discovery state and prove the new `knowledge_query(operation="memory_scope", ...)` contract from a genuinely refreshed ChatGPT connector session.

The gate exists to resolve one precise mismatch:

- the live restarted Soma build and repository contract include `memory_scope`;
- the already-open ChatGPT connector session still advertises the previous `knowledge_query` schema and rejects `memory_scope` before runtime validation.

This gate determines whether that mismatch is only stale connector discovery or a real connected-surface contract failure. It does not authorise a fix.

## Baseline state

At preparation time:

- branch: `lane/memory-integration-foundation-1`;
- repository HEAD: `f5b51f18271b3360586da690329dec697a2e747f`;
- worktree: clean and synchronised with origin;
- implementation commit: `da5ef525e0deb877dfecee24777e629231cab8e5`;
- live server build hash: `cd134cfc2c441c666f8baaf5cb6a8ef907241ff84b61d45e066af5ae9c9ca917`;
- public schema hash: `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`;
- canonical memory health: `healthy`, 10/10, zero malformed, zero unadopted, zero drifted;
- provider health: `degraded`, as designed;
- retrieval mode: `catalog_lexical`;
- exact project identity: `proj_a144f759-1619-4276-9292-28704b6611f4`, repository `soma`.

The previous cross-controller trial remains closed. Claude Code, ChatGPT, and Hermes were already verified end to end for the pre-existing memory flow. This gate verifies only the newly added `memory_scope` operation through a refreshed ChatGPT connector.

## Required outcome

The gate must prove all of the following from the refreshed connected surface:

1. Fresh connector discovery advertises `memory_scope` as a `knowledge_query` operation.
2. Its public input shape is the flat gateway form:

   ```json
   {
     "operation": "memory_scope",
     "repo_name": "soma"
   }
   ```

3. The call succeeds and returns a directly reusable explicit scope:

   ```json
   {
     "kind": "project",
     "project_id": "proj_a144f759-1619-4276-9292-28704b6611f4",
     "repo_name": "soma"
   }
   ```

4. The response identifies the configured canonical vault root, healthy canonical state, and current canonical record count.
5. The returned `scope` object is passed back verbatim to `memory_health` and succeeds.
6. The health result remains `healthy`, canonical/indexed 10/10, with zero malformed, unadopted, or drifted records.
7. A memory operation without explicit `scope` remains refused. Discovery must not become an inference path.
8. No canonical record, catalog row, packet, provider index, configuration file, or repository source file is mutated by the verification.
9. The result records the connector discovery state, server build hash, schema hash, capability epoch, exact request and response identity, and final repository/vault health.

## Execution sequence

1. Confirm the repository is clean and synchronised and that no unrelated owner work is present.
2. Confirm the current Soma service is healthy and canonical memory is still healthy at 10/10 with zero drift.
3. Refresh or reconnect the ChatGPT Soma connector using the supported connector lifecycle. Do not edit connector internals, credentials, or generated metadata.
4. Fetch fresh tool discovery from the refreshed session.
5. Record whether `knowledge_query` now advertises `memory_scope`, including the effective schema/build/capability identifiers visible to the connector.
6. Call `memory_scope` with `repo_name="soma"` and no `project_id` override.
7. Compare the returned scope exactly with the accepted ProjectScope identity.
8. Pass the returned scope verbatim to `memory_health`.
9. Intentionally verify that omitting scope from `memory_health` is still refused before execution.
10. Recheck canonical memory health and repository cleanliness.
11. Write one result document and update `PLANS.md` with either `passed` or the exact bounded failure classification.
12. Commit and push documentation-only closure evidence. Do not modify implementation in this gate.

## Allowed actions

- refresh or reconnect the existing ChatGPT Soma connector;
- read live connector discovery and Soma health/capability surfaces;
- invoke read-only `memory_scope` and `memory_health` queries;
- perform one expected missing-scope refusal check;
- inspect repository status and committed contracts;
- create and push documentation-only result/closure changes.

## Explicit exclusions

This gate does **not** authorise:

- source-code, test, schema, adapter, configuration, credential, or connector-internal changes;
- `memory_save`, `memory_correct`, `memory_supersede`, drift acceptance, rebuild, or any other memory write;
- provider installation, semantic activation, retrieval changes, stopword handling, scoring, ranking, or a custom retriever;
- personal scope, shared scope, legacy import, bulk import, or automatic conversation ingestion;
- changing the canonical vault root or Obsidian configuration;
- restarting or upgrading unrelated services;
- deleting connector state, revoking access, granting new external permissions, or changing secrets;
- reopening `MEMORY-REAL-PROJECT-TRIAL-1` or `MEMORY-CONTROLLER-ERGONOMICS-1`;
- beginning another implementation lane.

## Failure classification

Only three outcomes are valid:

### Pass — stale connector discovery resolved

Fresh discovery advertises `memory_scope`, the query succeeds, the returned scope works verbatim, missing scope remains refused, and state remains unchanged. Close the gate as passed.

### Discovery failure — refreshed connector still advertises the old schema

After one supported refresh/reconnect cycle, `memory_scope` is still absent or rejected before reaching Soma while the live server contract includes it. Record a connected-surface discovery/cache failure. Do not patch or repeatedly restart inside this gate.

### Runtime contract failure — fresh discovery advertises the operation but invocation fails

If the refreshed schema includes `memory_scope` but the valid flat request fails at or after Soma runtime validation, record the exact request, response, build, schema, and capability evidence. A separate owner-authored implementation lane is required before any fix.

A failure is still a completed gate when it is classified honestly and leaves state unchanged.

## Acceptance evidence

The result is acceptable only if it includes:

- fresh connector discovery evidence, not a reused pre-refresh schema;
- server build hash, schema hash, and capability epoch;
- exact `memory_scope` request and returned scope identity, or the exact bounded failure;
- exact `memory_health` result using the discovered scope, when discovery succeeds;
- proof that omitted scope remains refused;
- before/after canonical counts and drift state;
- confirmation that no memory write occurred;
- clean, synchronised repository status;
- a result document linked from `PLANS.md` and pushed.

## Stop conditions

Stop without retrying, widening scope, or editing code if:

- the repository is dirty with unrelated work;
- canonical memory is not healthy before the gate;
- the live project identity differs from the accepted Soma binding;
- connector refresh requires credential changes, access revocation, new permissions, or destructive state deletion;
- one supported refresh/reconnect cycle still exposes the stale schema;
- `memory_scope` is advertised but rejects the documented flat request;
- the returned scope differs from the accepted ProjectScope identity;
- `memory_health` fails with the returned scope;
- missing scope is accepted or silently inferred;
- canonical counts, hashes, drift state, or repository files change unexpectedly;
- any implementation change appears necessary;
- another lane or unrelated cleanup becomes entangled with the verification.

## Owner start language

A sufficient start instruction is:

> Start MEMORY-CONNECTOR-REFRESH-VERIFY-1 exactly as prepared. Refresh the ChatGPT Soma connector once, verify `memory_scope` and explicit-scope health from the refreshed surface, record either pass or the bounded failure classification, and do not change implementation, memory contents, credentials, provider state, retrieval behaviour, or unrelated files.
