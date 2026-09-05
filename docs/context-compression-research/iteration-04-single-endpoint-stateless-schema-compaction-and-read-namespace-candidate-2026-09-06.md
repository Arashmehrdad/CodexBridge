# Context-Efficient Chat Projection Research — Iteration 04

Date: 2026-09-06
Status: research iteration complete; architecture not frozen
Programme continuation: `cont_20260905T204910Z_07a66dcb7a07`

## Research objective

Continue the context-efficiency programme under a stricter owner constraint established after Iteration 03:

> Keep normal ChatGPT + one Soma app + one stateless Streamable HTTP MCP endpoint + one canonical Soma backend. Do not trade lower model-context pressure for more MCP lifecycle/session complexity.

This iteration does not authorize runtime changes, connector refresh, endpoint changes, app registration, server restart, or public tool-surface mutation.

## Hard architectural invariants entering this iteration

1. The existing live Soma ChatGPT connector is the protected control.
2. Soma must remain compatible with stateless Streamable HTTP operation.
3. No candidate may depend on ChatGPT correctly preserving `Mcp-Session-Id` across tool-call batches.
4. No candidate may add a second semantic planner or hidden next-action router.
5. Read and write capabilities must remain truthfully separated.
6. Exact repository/research/run evidence remains authoritative outside any compact active representation.
7. A reduction in schema bytes is not a win if it increases connector initialization, `tools/list`, authentication, or session churn.

## Source-supported transport evidence

### E1 — MCP Streamable HTTP session continuity is a client obligation only when the server issues a session ID

The MCP 2025-06-18 Streamable HTTP transport specification states that a server MAY issue an `Mcp-Session-Id` during initialization. If it does, the client MUST include that ID on subsequent requests and SHOULD explicitly terminate the session when no longer needed.

Source:
- https://modelcontextprotocol.io/specification/2025-06-18/basic/transports

This means a stateless MCP server is a protocol-valid design and avoids acquiring correctness dependence on client session persistence.

### E2 — OpenAI issue #201 is still open and documents batch-to-batch session loss

OpenAI Apps SDK examples issue #201 remains open. It reports production evidence that `openai-mcp/1.0.0` receives and uses an MCP session ID within one batch, then drops it before the next batch, repeatedly causing `initialize -> tools/list -> tool call` cycles. The report quantified 20 sessions for 12 tool calls in 14.5 minutes, zero session-ID reuse across batches, and a 7:1 OIDC-verification-to-work ratio.

Source:
- https://github.com/openai/openai-apps-sdk-examples/issues/201

This is external evidence, not proof of the exact behavior of every current ChatGPT build, but it is strong enough that Soma should not reacquire stateful-session dependence without explicit future acceptance evidence.

### E3 — Soma currently preserves stateless MCP deliberately

Repository evidence:

- `scripts/manage_soma_service.ps1` sets `$FastMcpStatelessHttp = "true"` and exports `FASTMCP_STATELESS_HTTP` when launching the server.
- Historical commit `e027112b8459dc7897859978c9c65aa8bf4f6d0a` is titled `Preserve stateless MCP on pre-hardening baseline`.

The stateless transport posture is therefore an accepted architectural scar, not an incidental default.

## Single-endpoint hypothesis space

Iteration 04 examined mechanisms that can reduce Plane-A tool-definition context without creating additional apps/endpoints:

1. preserve `$ref` / `$defs` rather than serving dereferenced schemas;
2. validation-equivalent branch deduplication inside discriminated unions;
3. removal of validation-neutral schema metadata;
4. consolidation of same-safety-class read tools into one fully typed project namespace.

No live surface was changed for any experiment.

## L1 — `$ref` preservation is not a Soma win

FastMCP documents `dereference_schemas=False` as a way to keep `$ref`/`$defs` and reduce schema size for clients that support references. MCP's current JSON Schema direction also supports local references.

Source:
- https://gofastmcp.com/servers/tools
- https://modelcontextprotocol.io/specification/draft/server/tools
- https://modelcontextprotocol.io/seps/2106-json-schema-2020-12

However Soma already has a custom public projection, `FlatGatewayTool`, which does more than ordinary FastMCP dereferencing:

- hoists the mandatory `request` envelope to the root;
- strips advertised defaults while preserving runtime defaults;
- hoists the `operation` / `action` discriminator;
- preserves constraints, enums, ranges and descriptions;
- keeps the original Pydantic discriminated union as the sole runtime validator.

Read-only local measurement:

- Run: `20260905T213142Z_executable_profile_993740ca`
- local import exposed 38 tools because lazy knowledge-tool registration was not driven in that process; use this result directionally rather than as the canonical 40-tool total.
- pre-middleware/raw descriptors: 178,767 bytes;
- served/post-middleware descriptors: 147,099 bytes;
- 37/38 raw tools contained `$ref` or `$defs`;
- raw referenced representation was 31,668 bytes larger than the served representation.

Conclusion:

> Simply disabling FastMCP schema dereferencing would regress Soma's current public descriptor size. The obvious `$ref` shortcut is falsified for the present Soma projection.

## L2 — Current FlatGatewayTool is already a meaningful compression layer

Source inspection confirmed that `flatten_request_input_schema()` and `FlatGatewayTool` alter only the advertised MCP schema and invocation envelope while delegating actual validation to the unchanged typed function signature.

This is a useful architectural pattern for future compression work:

> Public schema projection may be optimized mechanically as long as the canonical operation models remain the sole acceptance/validation authority and the projected accepted language remains equivalent.

## L3 — Strict validation-equivalent branch deduplication saves 8.8% globally

A read-only transform grouped union branches only when their schemas were byte-identical after removing branch `title` and discriminator value. The merged branch replaced multiple discriminator constants with one enum while preserving all other constraints/descriptions.

Run:
- `20260905T213256Z_executable_profile_bc9303ac`

Full live 40-tool input schemas:

- before: 143,644 bytes;
- after strict branch merge: 130,989 bytes;
- saved: 12,655 bytes;
- reduction: 8.8%;
- affected tools: 18.

Large examples included Cloudflare and Docker action families where many operations share an otherwise identical payload contract.

This is validation-equivalent by construction for the grouped branches, but model-routing equivalence is not yet proven because branch titles/discrete operation presentation can carry model-facing information even when they do not affect JSON Schema validation.

## L4 — On the project hot path, strict branch deduplication saves only 5.0%

Run:
- `20260905T213328Z_executable_profile_43ba77ee`

15-tool project hot-path input schemas:

- before: 62,251 bytes;
- after: 59,156 bytes;
- saved: 3,095 bytes;
- reduction: 5.0%.

Largest local savings:

- `system_query`: -999 bytes / 39.2%;
- `run_query`: -794 / 14.8%;
- `repo_apply`: -429 / 16.8%;
- `continuation_query`: -305 / 17.2%;
- `continuation_action`: -304 / 11.6%;
- `research_map_action`: -264 / 19.2%.

`run_start`, `skill_query` and several other hot tools had no strict merge opportunity.

Conclusion:

> Branch deduplication is a worthwhile finishing optimization, not the primary architecture. It cannot explain or solve the continuation-heavy freeze on its own.

## L5 — Validation-neutral metadata removal is negligible

Run:
- `20260905T213409Z_executable_profile_54c315ff`

Across all 40 input schemas:

- recursive `title` occurrences: 16;
- `discriminator` occurrences: 0;
- stripping all titles saved 504 bytes / 0.4%.

On the 15-tool project hot path:

- stripping titles saved 448 bytes / 0.7%.

Conclusion:

> Removing annotation metadata is not worth risking model readability for sub-1% savings.

## L6 — Static schema microcompression is insufficient

Combining L3/L5 makes the ceiling clear. Safe-ish syntactic cleanup can recover single-digit percentages, while Iteration 02 observed one heavy response accumulating about 175 KB / 95.8% of the full descriptor catalog.

Therefore the primary problem is not merely inefficient JSON encoding inside each schema. It is **which logical tool definitions the host brings into the active tool universe**.

## Candidate C1 — one typed read-only `project_query` namespace

A stronger single-endpoint candidate was synthesized offline.

Current six read-only project-query tools:

- `continuation_query`
- `repo_query`
- `research_map_query`
- `skill_query`
- `run_query`
- `system_query`

Candidate shape:

```text
project_query(
    surface = continuation | repo | research_map | skill | run | system,
    request = <the exact existing typed schema for that surface>
)
```

Important distinctions from the rejected universal `soma_call` design:

1. C1 is read-only only.
2. It does not execute arbitrary named tools.
3. Every `surface` retains the exact existing input schema under `request`.
4. The dispatcher is mechanical; it does not choose the surface.
5. No write, infrastructure, trading or external side effect can be reached through C1.
6. Canonical implementation/validation remains in the existing six handlers.

## L7 — C1 has truthful common MCP safety semantics

Run:
- `20260905T213605Z_executable_profile_74258114`

All six current tools advertise exactly:

```text
readOnlyHint     = true
destructiveHint  = false
idempotentHint   = true
openWorldHint    = false
```

Therefore C1 does not collapse different MCP permission/risk classes.

This is materially different from combining query and mutation operations behind one generic tool.

## L8 — C1 is 12% smaller than the six existing descriptors even before host-discovery effects

Run:
- `20260905T213547Z_executable_profile_e3edf03f`

Existing six descriptors:

- 25,428 bytes total;
- 20,911 bytes input schemas.

Synthetic typed `project_query` descriptor:

- 22,372 bytes total;
- 22,045-byte nested input schema.

Static descriptor reduction:

- 3,056 bytes;
- 12.0%.

The nested schema itself is slightly larger because it must add `surface` plus an explicit `request` branch. The net descriptor is still smaller because six tool-level descriptions/metadata envelopes become one.

More importantly, Iteration 02 observed the host loading 85,033 descriptor bytes when discovering `continuation_query`. If a future host A/B demonstrated that C1 is loaded alone rather than with the broad current query family, its descriptor would be about 73.7% smaller than that observed discovery group.

That 73.7% number is explicitly conditional on host behavior and is **not yet an achieved saving**.

## L9 — C1 synthetic schema is valid JSON Schema 2020-12 and representative calls remain valid

Runs:
- first sample attempt: `20260905T213650Z_executable_profile_6cdb4033` — correctly failed because the research-map health sample omitted its required `project_id`; no product/state change occurred.
- corrected proof: `20260905T213710Z_executable_profile_b2f987c5`.

The corrected proof:

1. built the synthetic `project_query` schema entirely in memory;
2. validated the schema using `Draft202012Validator.check_schema()`;
3. validated one representative wrapped call for each of the six surfaces;
4. called each existing read-only tool directly with the same inner request.

Results:

- synthetic JSON Schema valid: PASS;
- six wrapped representative calls accepted by synthetic schema: 6/6;
- six direct existing tool calls: 6/6 successful.

Representative operations:

- continuation: `capabilities`;
- repo: `compact_status`;
- research map: `health` with exact project/repo identity;
- skill: `capabilities`;
- run: `preflight`;
- system: `self_check`.

This proves only schema/mechanical feasibility. It does not prove ChatGPT routing quality or discovery-group behavior.

## Adversarial alternatives and disposition

### A1 — Add multiple narrow ChatGPT apps/endpoints

Downgraded after Iteration 03 because it increases MCP lifecycle surfaces and may amplify client-side `initialize`/`tools/list` churn. Issue #201 makes that a materially unsafe direction until disproved.

### A2 — Disable schema dereferencing

Rejected for present Soma. The current FlatGatewayTool projection is smaller than the raw referenced form.

### A3 — Strip titles/descriptions aggressively

Rejected as primary strategy. Titles save <1%; descriptions carry routing semantics and OpenAI model guidance generally recommends clear tool/parameter descriptions.

### A4 — Merge identical operation branches

Retained as a low-risk secondary optimization candidate. Measured 8.8% global / 5.0% project-hot-path input-schema reduction, but model-facing equivalence requires A/B evaluation before implementation.

### A5 — Universal `soma_search` / `soma_call`

Still rejected. It would hide distinct permission/destructive/open-world semantics behind a generic execution surface and weaken the public contract even if runtime validation remained strict.

### A6 — Read-only typed family consolidation

Promoted to the strongest new single-endpoint candidate. It preserves one safety class and exact child schemas while potentially reducing host discovery fan-out.

## Current architecture model after Iteration 04

The evidence now favors a hierarchy of context-efficiency mechanisms:

```text
Tier 0 — preserve one stateless MCP endpoint and one canonical backend

Tier 1 — reduce host discovery fan-out by consolidating only capabilities
         that share the same truthful MCP safety/authority class

Tier 2 — apply validation-equivalent branch deduplication inside those
         public schemas where it is mechanically provable

Tier 3 — compact repeated result/envelope state and externalize exact
         evidence by stable references where client behavior is proven

Tier 4 — rely on platform compaction only as an additional host-owned layer
```

C1 (`project_query`) currently fits Tier 1 without violating the stateless transport boundary.

## What is still unknown

1. Whether ChatGPT's host would discover only `project_query` or still expand to unrelated read tools.
2. Whether a two-level `surface + request` schema changes routing accuracy or argument quality versus six first-class tools.
3. Whether one larger read tool causes any model-search latency regression despite lower total discovered bytes.
4. Whether replacing six existing tools with C1 can be introduced without a problematic connector refresh on the current ChatGPT client.
5. Whether the same safety-class consolidation principle can be extended to any mutation surfaces without hiding confirmation/destructive semantics.
6. Whether Plane-B/Plane-C result/evidence compaction provides a larger gain than further Plane-A work after C1.

## Required next research

Iteration 05 should remain offline/read-only and should **not** register C1 yet.

Recommended questions:

1. Build a complete capability-class matrix for all 40 tools using live MCP annotations plus owner architecture semantics.
2. Identify only consolidation groups whose readOnly/destructive/idempotent/openWorld properties are identical and whose authority boundaries remain coherent.
3. Synthesize the resulting single-endpoint catalog and measure total descriptor bytes, likely host query/action-group bytes, and project-hot-path bytes.
4. Compare at least three candidate catalogs:
   - current 40-tool surface;
   - read-only C1 only plus unchanged remaining tools;
   - broader safety-class family consolidation.
5. Explicitly reject any merge that crosses repository/machine/infrastructure/trading authority or confirmation classes even if it saves more bytes.
6. Decide from those measurements whether Plane A still has enough safe headroom to justify a future connector-side A/B, or whether the programme should pivot next to Plane B/C context compaction.

## Iteration conclusion

Iteration 04 changes the leading direction again.

The evidence does **not** support multiple apps/endpoints as the safe next move, and it does **not** support simple `$ref` or metadata trimming as a sufficient solution.

The strongest current candidate is:

> **Keep one stateless Soma MCP endpoint, but reduce host discovery fan-out by consolidating only same-safety-class project reads into one fully typed, mechanically dispatched public namespace while leaving canonical handlers and validation untouched.**

This remains a research candidate. No runtime architecture is frozen and no live public surface has changed.
