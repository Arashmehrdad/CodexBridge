# ChatGPT Normal-Chat Tool UX Research — Iteration 1

**Date:** 2026-08-12  
**Status:** research and investigation only; no production code change  
**Repository:** `D:\Github\Soma`  
**Starting HEAD:** `24fa7774d97e8a04bed3ec79054ae9b66182fd39`  
**Live server build:** `f55d37e7d65b7389a3f33ae0911a4a95ab93e9746b76e720b19dd1f40bc8e765`  
**Live public schema:** `84d0af8b66d7df990320268ba905bf536cbb2722dfabf6cda30aaa5e93f9012c`

## 1. Research question

The owner reports that normal ChatGPT project chats now visibly render Soma calls in a generic `api_tool -> Call tool` style, including historical conversations that previously appeared differently. The desired long-term experience is not to hide evidence, but to restore a coherent engineering interaction: explain intent, perform bounded work, and report the result without making the conversation feel like a stream of opaque low-level tool calls.

This iteration asks:

1. Which parts of the observed presentation are controlled by ChatGPT rather than Soma?
2. Which supported OpenAI plugin/MCP metadata can Soma provide but currently does not?
3. Did recent Soma gateway consolidation or transport patches remove useful presentation metadata?
4. Does the current public-contract identity detect controller-facing metadata changes?
5. What should be measured before designing a patch?

## 2. Sources inspected

### Soma repository and live runtime

- `soma/server.py`
- `soma/mcp_flat_input.py`
- `soma/public_gateway_inventory.py`
- `soma/cf1_gateway_operation_inventory.py`
- `tests/test_mcp_action_discovery.py`
- `docs/domain-tool-gateway-migration.md`
- `docs/domain-tool-gateway-progress.md`
- `pyproject.toml`
- live `system_query(operation="capabilities")`
- live installed FastMCP introspection through Soma `run_start`
- relevant Git history, especially:
  - `33623c4` — Serialize MCP projection into `content[].text` for all clients
  - `756c98f` — Flatten public MCP gateway input schemas
  - `99aa122` — Decode nested gateway arguments arriving as JSON text
  - `9b651e0` — Remove public Codex gateways and action-surface entries
  - `c32f365` — Remove Codex CLI execution, transport, and configuration

### Current OpenAI documentation

- Plugins in ChatGPT and Codex: https://help.openai.com/en/articles/20001256-plugins-in-codexOpenAI
- Skills in ChatGPT: https://help.openai.com/en/articles/20001066
- Plugin tool planning: https://developers.openai.com/plugins/plan/tools
- Plugin metadata optimization: https://developers.openai.com/plugins/guides/optimize-metadata
- Plugin reference: https://developers.openai.com/plugins/reference
- Add UI to an MCP server: https://developers.openai.com/plugins/build/chatgpt-ui
- GPT-5.6 model guidance: https://developers.openai.com/api/docs/guides/latest-model

### FastMCP primary documentation

- Tools: https://gofastmcp.com/servers/tools
- Server: https://gofastmcp.com/servers/server

## 3. Platform findings

### P-01 — The ChatGPT integration model has moved to Plugins

As of 2026-07-09, OpenAI documents Plugins as the primary discovery/package surface across ChatGPT and Codex. A plugin may combine Skills, Apps/MCP servers, app templates, and optional UI. Existing app connections remain valid, but the packaging and workflow model has changed around them.

This means Soma should now be evaluated as more than a bare MCP tool catalog. Current platform primitives include:

- MCP tools for data and actions;
- Skills for reusable workflow instructions;
- optional inline UI/components;
- richer tool descriptor metadata.

### P-02 — Tool presentation metadata is first-class and supported

OpenAI's current Plugin reference explicitly supports on each tool descriptor:

- `title`: concise human-readable action name;
- `description`: selection/routing guidance;
- `_meta["openai/toolInvocation/invoking"]`: short status while running;
- `_meta["openai/toolInvocation/invoked"]`: short status after completion;
- `_meta.ui.resourceUri`: optional component resource;
- standard MCP annotations including `readOnlyHint`, `destructiveHint`, `openWorldHint`, and `idempotentHint`.

The current Plugin guidance says every tool should map to a user goal rather than mirror an internal API, and tool descriptions should state the user goal and triggering conditions.

### P-03 — Metadata affects routing as well as appearance

OpenAI's metadata optimization guidance states that ChatGPT and Codex decide when to call tools based on metadata. It recommends a labelled golden-prompt dataset containing direct, indirect, and negative prompts, then replaying it in Developer mode and tracking selection precision/recall.

A presentation patch therefore cannot safely be treated as cosmetic only. Titles and descriptions can change tool selection.

### P-04 — UI can improve a focused result, but should not be attached to every data call

OpenAI recommends starting with the smallest presentation that helps the user understand the result. Inline cards are appropriate for focused results, confirmations, and small action sets. It also explicitly recommends separating data-processing tools from render tools so the host does not re-render an iframe on every tool call.

Therefore a Soma UI, if adopted, should not become a widget attached to every `repo_query`, `run_query`, or internal evidence call. A later design should identify a small number of coherent user-facing completion/status surfaces.

### P-05 — Skills are now a supported workflow channel

Current OpenAI documentation describes Skills as reusable workflows that ChatGPT can automatically use when helpful, and Plugins can package Skills together with apps. This provides a supported future channel for rules such as `explain -> act -> validate -> report`, instead of relying only on generic tool descriptions or an external harness-injected skill.

Plan/availability constraints still need a separate deployment investigation before making this a hard dependency.

## 4. Soma live findings

### S-01 — All 32 live public tools have no human-readable MCP title

`system_query(operation="capabilities")` was queried against the live server. The exposed action count is 32. The descriptors inspected show:

```text
title: null
```

The existing annotations also carry `title: null`.

This is not inferred from source alone; it is confirmed on the live MCP discovery surface.

### S-02 — Soma publishes no OpenAI invocation-status metadata

A source search found no `openai/toolInvocation/invoking` or `openai/toolInvocation/invoked` keys in `soma/`. Live descriptors contain only FastMCP's own metadata namespace:

```text
meta:
  fastmcp:
    tags: []
```

No Soma/OpenAI-specific invocation label is exposed.

### S-03 — Installed FastMCP already supports the needed metadata

A live read-only introspection run reported:

```text
fastmcp_version=3.4.2
```

The installed `FastMCP.tool` signature includes `title`, `description`, `icons`, `annotations`, `meta`, and `app`. `FunctionTool.from_function` also accepts `title`, `description`, `annotations`, and `meta`.

Soma's `FlatGatewayTool.from_function(function, **tool_kwargs)` architecture therefore appears capable of carrying this metadata without replacing the flattening layer. This must still be proven with a disposable descriptor test before implementation.

### S-04 — FastMCP is unpinned

`pyproject.toml` currently declares simply:

```toml
"fastmcp",
```

The live environment is FastMCP 3.4.2. Because a proposed patch would depend directly on descriptor/meta behavior, leaving this dependency completely unbounded is a reproducibility risk. Version strategy requires a separate compatibility audit before changing dependency policy.

### S-05 — Current descriptions are domain/internal-language centric

Representative live descriptors include:

```text
repo_query: "Read-only gateway for bounded repository inspection and patch lifecycle status."
run_start:  "Write gateway for durable validation and unrestricted permissive PowerShell runs."
system_query: "Read-only system gateway for capabilities, health, configuration validation, and reload status."
```

These descriptions are accurate at an implementation level, but they do not consistently answer the current OpenAI-recommended question: what user goal should cause the model to select this tool, and when should it not use it?

This is a routing/ergonomics gap, not evidence that the underlying gateway design is wrong.

### S-06 — Gateway consolidation is the measured baseline, not a protected implementation choice

Historical Soma work reduced a much larger direct-action catalog into consolidated domain gateways. The migration documents explicitly aimed to reduce tool-selection ambiguity and connector overhead, so the current consolidated surface is an important baseline with real prior evidence behind it.

That evidence does **not** create a presumption that the existing route must survive. The current problem should not be solved by recreating dozens of one-operation public tools merely to obtain prettier labels, but neither should a more modern Plugin-era tool, Skill, app, UI, or routing architecture be rejected because it requires more migration work. Any retained, split, replaced, or newly packaged surface must earn its place through comparative evidence on user-goal routing, call count/context cost, latency, UX, safety/authority clarity, maintainability, interoperability, and future platform fit.

**Owner research principle:** implementation effort and compatibility with the current code are costs to measure, not optimization objectives. When research demonstrates that a modern supported route is materially better overall, prefer the better architecture even when it requires more implementation work.

### S-07 — Public contract identity excludes descriptor metadata

`_input_schema_hash_from_actions()` hashes only:

```text
{name -> inputSchema}
```

`_operation_identity_metadata()` then uses that input-schema hash as `public_schema_hash` / `runtime_input_schema_hash` and includes it in `discovery_cache_generation`.

Consequently, changes to any of these controller-facing fields can occur without changing `public_schema_hash`:

- `title`;
- `description`;
- annotations;
- custom `_meta` / `meta`;
- icons;
- optional UI resource linkage.

`server_build_hash` would move when Python source changes, but the public schema identity currently cannot answer whether the *discovered controller-facing descriptor* changed independently of an input schema change.

### S-08 — Discovery tests do not pin titles or OpenAI metadata

`tests/test_mcp_action_discovery.py` verifies:

- public action names;
- non-empty descriptions and a 300-character ceiling;
- input/output JSON-schema validity;
- read/write safety annotations.

It currently does not require:

- non-null `title`;
- invocation status labels;
- OpenAI metadata namespace correctness;
- user-goal-shaped description semantics;
- descriptor identity/hash coverage;
- a golden prompt routing corpus.

A metadata regression can therefore pass the current action-discovery suite.

### S-09 — Soma intentionally emits both structured content and text content

Earlier compatibility work made MCP projections available in `content[].text` as well as structured form so clients with differing MCP support could consume results. The current OpenAI reference likewise permits both `structuredContent` and `content`.

There is no evidence in Iteration 1 that this compatibility layer should be removed. It may influence visual verbosity, but removing it before a controlled A/B test would be speculative and could break non-ChatGPT consumers.

## 5. Bug and risk ledger — Iteration 1

### UX-001 — Missing human-readable tool titles

**Class:** confirmed UX/descriptor defect  
**Evidence:** all 32 live descriptors expose `title: null`.  
**Impact:** host presentation falls back to machine/tool identity rather than a meaningful action title; routing loses a supported semantic signal.  
**Patch candidate:** central descriptor metadata registry or decorator metadata, not per-call prose hacks.  
**Verification needed:** ChatGPT Developer-mode A/B test after metadata-only prototype.

### UX-002 — Missing invocation status metadata

**Class:** confirmed integration gap  
**Evidence:** no OpenAI invocation-status metadata in source or live descriptors.  
**Impact:** ChatGPT cannot use Soma-provided human-readable running/completed status text where the host supports it.  
**Patch candidate:** `_meta["openai/toolInvocation/invoking"]` and `_meta["openai/toolInvocation/invoked"]` on selected public tools.  
**Verification needed:** live normal-chat rendering A/B test; do not claim this alone removes the host's tool card.

### CONTRACT-001 — Controller-facing descriptor drift is not represented by `public_schema_hash`

**Class:** confirmed contract/observability gap  
**Evidence:** live discovery contains titles/descriptions/annotations/meta; `_input_schema_hash_from_actions()` hashes only name + input schema.  
**Impact:** a material tool-routing or presentation change can be invisible to the identity currently named `public_schema_hash`; activation evidence may report an unchanged schema even though a controller receives materially different metadata.  
**Patch candidate:** introduce a distinct descriptor/discovery hash rather than silently broadening `public_schema_hash` unless compatibility analysis proves that broadening is safe.  
**Verification needed:** existing connector-refresh and capability-identity tests.

### DEP-001 — FastMCP dependency is unbounded

**Class:** confirmed reproducibility risk  
**Evidence:** `pyproject.toml` contains bare `fastmcp`; live runtime is 3.4.2.  
**Impact:** future installs can receive a different major/minor descriptor or protocol behavior without a Soma code change. The proposed UX patch would rely more heavily on those APIs.  
**Patch candidate:** determine a tested compatibility range or lock strategy after examining installation/update workflow.  
**Verification needed:** clean-environment install, self-check, MCP discovery snapshot.

### ROUTE-001 — Tool descriptions are not systematically user-goal shaped

**Class:** confirmed design/selection gap  
**Evidence:** live descriptors are predominantly internal gateway summaries; current OpenAI guidance recommends descriptions centered on user intent and disallowed cases.  
**Impact:** avoidable wrong-tool selection or excessive tool hopping, especially across consolidated gateways.  
**Patch candidate:** metadata copy audit with golden prompts; preserve concise descriptions because overly long tool text also harms context efficiency.  
**Verification needed:** direct/indirect/negative prompt replay.

### TEST-001 — No descriptor-metadata regression contract

**Class:** confirmed test gap  
**Evidence:** discovery tests check descriptions and standard safety annotations but not titles, invocation metadata, descriptor hash, or OpenAI metadata.  
**Impact:** UX metadata can disappear silently.  
**Patch candidate:** focused discovery tests plus descriptor snapshot/hash tests.

### UX-003 — No coherent user-facing completion/status component

**Class:** design opportunity, not yet a bug  
**Evidence:** no `_meta.ui.resourceUri` on current Soma tools; OpenAI supports optional inline cards.  
**Potential benefit:** one compact result/status surface could make long engineering work easier to read.  
**Risk:** attaching UI to every tool would increase clutter and re-rendering; OpenAI explicitly recommends separating data tools from render tools.  
**Disposition:** research further before planning implementation.

## 6. Important non-findings

1. **No evidence that Soma changed historical ChatGPT tool-card rendering.** The owner observed the presentation change in old chats as well. Repository code cannot retroactively alter stored historical UI events. This remains strong evidence of a host/frontend rendering change, although Iteration 1 did not identify an OpenAI changelog item naming that exact visual rollout.
2. **No evidence that the dedicated coding-agent route was restored.** Current Soma still exposes the consolidated MCP/tool runtime; recent Claude use was through unrestricted PowerShell, not a restored Codex/Claude worker transport.
3. **No evidence yet that gateway consolidation should either be rolled back or preserved as the final optimum.** The existing 32-tool surface was intentionally consolidated to improve selection and reduce connector overhead and therefore remains the comparison baseline. A newer architecture remains eligible if comparative research demonstrates better overall routing, efficiency, UX, maintainability, or platform fit.
4. **No evidence yet that `content[].text` compatibility serialization causes the generic card.** Preserve it until an A/B test proves otherwise.
5. **No claim that adding titles/status metadata can force ChatGPT to hide tool cards.** The host owns final rendering. Soma can provide richer supported presentation signals; only live testing can establish the exact visible effect.

## 7. Research-operation incidents

Two investigation call mistakes were observed and are **not Soma bugs**:

1. A `repo_query(search_text)` call initially supplied a file as `directory`; Soma correctly refused it as not a directory.
2. The first FastMCP introspection attempt used unsupported `return_when="completed"` and an excessive `wait_seconds`. Schema validation correctly refused the call before execution. A corrected call succeeded with no repository changes.

Recording these prevents accidental inflation of the bug ledger.

## 8. Preliminary patch shape — not yet approved for implementation

Iteration 1 supports a likely multi-layer patch, but not yet a final plan:

1. **Descriptor metadata foundation** — central, tested titles and invocation labels for the current 32 public gateways.
2. **Routing copy pass** — concise user-goal descriptions, evaluated against a golden prompt corpus rather than edited by taste.
3. **Descriptor identity** — add a separate discoverable descriptor hash/epoch so metadata activation and drift are measurable.
4. **FastMCP compatibility boundary** — pin or bound the version only after installation/release impact is measured.
5. **Workflow guidance** — investigate a plugin-packaged Soma skill for `explain -> inspect -> act -> validate -> report` in normal Chat without moving the work to Codex/Work.
6. **Optional presentation layer** — prototype at most one focused engineering status/result card after metadata-only A/B results are known.
7. **Do not restore the retired coding-agent route merely to improve normal-chat UX.** That is an independent architecture decision.

## 9. Iteration 2 research targets

Before producing the final implementation plan, investigate:

1. The exact current Soma plugin/app registration path and what descriptor metadata ChatGPT receives at enrollment versus at live `tools/list`.
2. Whether metadata changes require connector refresh, app/plugin republish, server restart, or some combination.
3. Whether the current private MCP deployment can use optional UI resources through the existing secure tunnel without new public exposure.
4. FastMCP 3.4.2 `meta` passthrough through `FlatGatewayTool` in a disposable test, including exact serialized MCP descriptor keys.
5. Existing capability-identity/connector-refresh tests to design a non-breaking descriptor hash.
6. A representative golden-prompt corpus from actual Soma usage: repository inspection, patching, test execution, durable jobs, memory, infrastructure, and negative prompts.
7. Whether the inline `soma-agent:soma-operator` harness skill can or should be replaced/supplemented by a repo-owned plugin-packaged Skill under the owner's current ChatGPT plan.
8. Historical before/after evidence around the ChatGPT UI rollout where available, without assuming Soma can control host-owned card chrome.

## 10. Iteration 1 verdict

The visible regression is **not explained by a recent Soma code regression**, but the current platform exposes presentation and workflow capabilities that Soma is not using. The existing consolidated gateways are therefore the **baseline candidate**, not the predetermined solution. Iteration 1 does not justify returning blindly to early one-tool-per-action Soma or restoring the retired coding-agent route, but it also does not justify retaining the present gateway/flattening architecture merely because that would require less work. Modern supported routes must remain first-class candidates and should replace existing pieces wherever comparative research proves a materially better overall architecture.

The first confirmed engineering defects to carry forward are **UX-001, UX-002, CONTRACT-001, DEP-001, ROUTE-001, and TEST-001**. `UX-003` remains a design hypothesis until live A/B evidence justifies adding UI.
