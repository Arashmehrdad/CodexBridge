# MCP-OPERATION-USAGE-INSTRUMENTATION-1 — Bounded Aggregate Operation Counters

**Date:** 2026-07-29
**Status:** owner-authorised and amended to an exact 8-hour window; implementation validated; production window not yet activated.
**Decision level:** temporary runtime instrumentation and bounded public-operation usage evidence only.
**Follows:** [`EXTERNAL_CONSUMER_MEASUREMENT_1_RESULT_2026-07-29.md`](EXTERNAL_CONSUMER_MEASUREMENT_1_RESULT_2026-07-29.md).

## Purpose

Answer one question Soma cannot currently answer from existing evidence:

> Which public MCP operations are actually invoked during a representative live window?

`EXTERNAL-CONSUMER-MEASUREMENT-1` established that Soma receives substantial real traffic but logs only `POST /mcp`. The selected operation lives in the unlogged JSON-RPC body, so static searches and HTTP access logs cannot establish whether the six generic knowledge operations are still used.

This lane may add temporary, aggregate-only operation counting for one bounded window. It does not identify clients and does not record request or response content.

The immediate decision target is:

- `knowledge_action.save_knowledge`;
- `knowledge_action.supersede_knowledge`;
- `knowledge_action.rebuild_knowledge`;
- `knowledge_query.get_knowledge`;
- `knowledge_query.search_knowledge`;
- `knowledge_query.knowledge_health`.

The counter must cover the complete public operation inventory so the evidence is reusable for later public-operation retirement questions. Covering all operations does not authorise changing or retiring any operation.

## Governing privacy rule

The runtime may learn only the already validated canonical operation identity and increment an aggregate integer.

It may not record or derive:

- request arguments or raw JSON-RPC bodies;
- response bodies, result status, errors or durations;
- prompts, messages, memory content or source content;
- project IDs, repository names, paths or resource identifiers;
- IP addresses, Cloudflare source addresses, user agents or transport headers;
- controller, user, account, session, conversation or request identity;
- credentials, tokens or environment values;
- per-call timestamps, ordering or event rows.

The persisted evidence is a count by canonical `gateway.operation`, not a request log.

## Canonical operation identity

Operation keys must come from Soma's existing authoritative public operation inventory:

- `PUBLIC_GATEWAY_OPERATION_INVENTORY`;
- `operation_names_by_gateway()`;
- the same `gateway.operation` naming used by `capability_identity.operation_schema_hashes`.

The lane must not create a second manually maintained operation map.

Counting occurs only after FastMCP/Pydantic request validation and canonical operation resolution, and before the selected gateway operation executes. The implementation must not parse the raw HTTP or JSON-RPC body to discover the operation.

Every advertised public operation must have one explicit counter initialised to zero. An operation not present in the authoritative inventory must never be written as a free-form key. Such a call increments only one aggregate `unmapped_or_rejected_count` and triggers investigation.

## Exact measurement artifact

The only runtime measurement artifact is:

```text
runs/measurements/mcp-operation-usage/<measurement-id>/counts.json
```

It remains outside Git and contains only these fields:

```json
{
  "measurement_id": "mcp-operation-usage-...",
  "window_started_at": "RFC3339 UTC",
  "window_ends_at": "RFC3339 UTC",
  "instrumented_build_hash": "...",
  "public_schema_hash": "...",
  "inventory_version": "...",
  "total_counted_calls": 0,
  "unmapped_or_rejected_count": 0,
  "counts": {
    "gateway.operation": 0
  },
  "complete": false
}
```

No additional field is permitted. The artifact schema is closed and regression-tested.

The file is an aggregate snapshot. It contains no per-request record and no information from which per-request timing, source or content can be reconstructed.

## Measurement window

**Owner amendment — 2026-07-29:** Arash reduced the production window from 48 hours to 8 hours because Soma runs on a personal laptop that cannot reasonably remain continuously available for two days. The minimum traffic threshold is reduced proportionally from 500 to 100 counted public-operation calls. No privacy, mapping, recovery, expiry, cleanup, contract, or interpretation rule is weakened by this amendment.

The production window is exactly **8 consecutive hours** beginning only after validation counters are reset and the first production snapshot is written.

A valid window requires:

- the full 8 hours to elapse;
- at least 100 counted public operation calls;
- `unmapped_or_rejected_count == 0` for the production window;
- no unexplained counter loss across restart or crash;
- the public tunnel and localhost endpoint to advertise the same contract throughout.

If fewer than 100 calls occur, the lane closes `measurement-insufficient` unless the owner explicitly authorises one new bounded window. The executing controller may not silently extend the deadline.

The counter must stop automatically at `window_ends_at`. Restarting Soma must preserve the original deadline and accumulated aggregate counts; restart must not open a new window or reset evidence.

## Temporary implementation lifecycle

When started, the lane may:

1. record the clean baseline commit, build hash, public schema hash, operation inventory version and public operation count;
2. add the minimum temporary counter implementation and focused tests on the current lane branch;
3. run a separate disposable validation window and positive controls;
4. reset the artifact, activate the 8-hour production window and restart the local Soma service;
5. collect and hash the final aggregate artifact;
6. disable the counter, remove the temporary implementation and temporary activation configuration;
7. restart Soma on the restored product tree;
8. publish only the result, aggregate matrix and `PLANS.md` closure update.

At closure, the tracked product source, tests and configuration must contain no operation-usage counter, activation flag, telemetry hook or measurement-specific path. Temporary implementation commits may remain in branch history, followed by an explicit removal commit, but the final tracked product tree must match the pre-lane product tree exactly apart from authorised documentation.

The lane may restart the local Soma service and public tunnel only as required to activate and remove the temporary counter. It may not alter connector credentials, Cloudflare configuration, public DNS or external client configuration.

## Implementation boundary

The implementation must be centralized at the normalized public tool-dispatch boundary or through one shared helper used by every public gateway. It must not scatter independent logging logic across operation handlers.

The counter must:

- be disabled by default;
- require an explicit measurement ID, output path and absolute end time;
- reject output paths outside `runs/measurements/mcp-operation-usage/`;
- use atomic, restart-safe aggregate snapshots;
- preserve exact integer counts under concurrent calls;
- stop counting after expiry without relying on a human to disable it;
- fail open for the requested Soma operation if measurement persistence fails, while incrementing no fabricated count and surfacing the measurement failure in local operator evidence;
- never change gateway request validation, routing, return values or error behaviour;
- never add a public field or operation;
- leave `public_schema_hash` unchanged.

A measurement failure must not make Soma unavailable or alter the requested operation's result.

## Validation controls

Before the production window, use a separate disposable measurement ID and artifact.

Required positive controls:

1. invoke one read operation with a known key and prove its count increases by exactly one;
2. invoke one write-class gateway through a non-mutating rejected or dry validation path only if it can be counted after canonical operation resolution without product-state mutation;
3. invoke the six target generic operations only where a read-only probe exists; do not write canonical or generic knowledge merely to test counting;
4. prove every key in `operation_schema_hashes` has exactly one counter and no extra counter exists.

Required privacy controls:

- place unique sentinel strings in request arguments during a disposable test and prove none appears in the aggregate artifact;
- prove project IDs, repository names, paths, response text, error text, IP-like strings and user-agent text cannot appear under the closed artifact schema;
- prove no per-event file, access-log augmentation or request-body copy is created;
- inspect the temporary patch for logging or serialization of the request object.

Required reliability controls:

- concurrent increments produce the exact expected total;
- atomic snapshots survive process interruption without malformed JSON;
- restart resumes the same measurement ID, deadline and counts;
- expiry prevents further increments;
- disabled mode performs no filesystem write;
- unknown or invalid operation names cannot create new keys;
- the validation artifact is deleted before the production window;
- `public_schema_hash` remains equal to the baseline value.

## Decision rules for the six generic knowledge operations

Controlled validation probes do not count toward the production result.

For each target operation:

- **count greater than zero:** classify `observed_live_use`; no deprecation gate may claim non-use;
- **count equal to zero in a valid window:** classify `no_use_observed_in_bounded_window`; the owner may prepare a deprecation and data-migration gate while explicitly accepting residual use outside the window;
- **invalid or incomplete window:** classify `not_measurable`; retain the operation and make no retirement inference.

A zero count is never proof of global non-use. It is stronger than static absence only because the window includes real public traffic and every validated operation is counted.

Because generic knowledge writes target a different vault root while sharing the canonical catalog, this lane cannot treat zero or non-zero counts as permission to redirect or remove data paths. Any retirement successor must separately resolve the shared-catalog/two-vault data boundary.

## Required outputs

The authorised closure files are:

- `docs/MCP_OPERATION_USAGE_INSTRUMENTATION_1_RESULT_2026-07-29.md`;
- `docs/mcp-operation-usage-instrumentation-1-counts-2026-07-29.json`;
- the corresponding `PLANS.md` status update.

The committed JSON is a reviewed projection of the aggregate artifact. It may contain the closed artifact fields, per-operation counts, interpretation and artifact SHA-256. It must not add client identity or request-level material.

The Markdown result must report:

1. baseline and instrumented/restored build identities;
2. public contract identity before, during and after the window;
3. exact window duration and total public calls;
4. counts for every public operation;
5. specific decisions for the six target generic operations;
6. any restart, loss, dropped or unmapped evidence;
7. privacy-control results;
8. proof the temporary implementation and activation were removed;
9. the smallest justified successor decision;
10. whether the Pre-Roadmap V3 bridge can close.

## Closure invariants

The lane may close `measurement-complete` only when:

- the window satisfies every validity rule;
- aggregate counts reconcile exactly;
- the raw aggregate artifact has a recorded SHA-256;
- all privacy and reliability controls pass;
- no measured public contract changed;
- temporary instrumentation and activation are removed;
- the final tracked product tree matches the pre-lane product tree apart from the three authorised documentation files;
- the full test suite passes on the restored tree;
- localhost and the public tunnel are healthy after restoration.

It closes `measurement-insufficient` when the implementation is trustworthy but the traffic/window requirements are not met.

It closes `instrumentation-rejected` when privacy, mapping, counting, recovery or cleanup cannot be proven. A rejected lane must remove the temporary instrumentation and restore the service before documentation closure.

## Explicit exclusions

This gate does not authorise:

- permanent telemetry, analytics, dashboards or usage history;
- per-request logs or timestamps;
- client, user, address, session or repository attribution;
- request/response body capture;
- adding deprecation warnings or response metadata;
- changing public request or output schemas;
- changing operation routing or semantics;
- removing, renaming, hiding or deprecating any operation;
- writing generic or canonical knowledge as a measurement probe;
- migrating or reconciling the two knowledge vault roots;
- editing external controller prompts or configurations;
- Cloudflare, DNS, credential or connector changes;
- deployment beyond the existing local Soma service and tunnel;
- Roadmap V3 implementation, code-intelligence activation, RAGFlow deployment, personal memory or Cortana work.

## Stop conditions

Stop, restore the baseline tree and publish the failure if:

- any request content or client-identifying data reaches the artifact;
- operation identity cannot be derived from the authoritative inventory after validation;
- counting changes operation behaviour or public schemas;
- the aggregate snapshot loses or double-counts calls;
- a restart changes the deadline or resets counts;
- the public contract differs between localhost and tunnel;
- unrelated owner work appears in the worktree;
- cleanup cannot prove the final product tree is restored.

## Owner start language

A sufficient start instruction is:

> Start MCP-OPERATION-USAGE-INSTRUMENTATION-1 exactly as amended. Add only temporary aggregate counters keyed by Soma's authoritative gateway.operation inventory, activate one exact 8-hour production window, and record no request content, per-call event, timestamp, client, address, session, project or repository identity. Validate mapping, privacy, concurrency, restart recovery and automatic expiry before the window. Do not write memory, change any public contract, migrate or deprecate anything. After the window, hash the aggregate artifact, remove all instrumentation and activation, restore and validate the original product tree, and close only with the authorised result, counts JSON and PLANS.md update.
