# ChatGPT Normal-Chat Tool UX Research — Iteration 3

**Date:** 2026-08-12  
**Status:** research and investigation only; no production code change  
**Repository:** `D:\Github\Soma`  
**Starting HEAD:** `24fa7774d97e8a04bed3ec79054ae9b66182fd39`  
**Live server build:** `f55d37e7d65b7389a3f33ae0911a4a95ab93e9746b76e720b19dd1f40bc8e765`  
**Live public input-schema hash:** `84d0af8b66d7df990320268ba905bf536cbb2722dfabf6cda30aaa5e93f9012c`  
**Follows:** `CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_2_2026-08-12.md`

## 1. Governing research rule

The owner corrected an important bias after Iteration 2:

> Existing support is a baseline, not a preference. Lower migration effort is a cost advantage, not evidence of architectural superiority. If a modern route is materially better on routing quality, safety clarity, UX, efficiency, maintainability, interoperability, or future platform fit, prefer that route even when it requires substantially more implementation work.

Iteration 3 therefore compares the current Soma surface against current OpenAI Plugin-era and FastMCP 3.x primitives instead of asking only how cheaply the current surface can be patched.

A modern primitive is not automatically preferred either. It must outperform the baseline on measured outcomes and preserve Soma's authority/safety contracts.

## 2. Research questions

1. Is the 32-tool consolidated MCP surface itself inefficient enough to justify topology changes?
2. Does normal Chat actually receive the whole 32-tool schema on every turn?
3. Can newer FastMCP transforms cleanly overlay modern metadata onto Soma's flat-input tools?
4. Can FastMCP Tool Search replace the large catalog without weakening safety or worsening the exact UX complaint?
5. Can Soma expose smaller focused MCP server views while reusing the existing handlers and schemas?
6. Which current gateways are overloaded across distinct user-goal or safety boundaries?
7. Are Soma's existing MCP safety annotations truthful under current OpenAI semantics?
8. What should be the exact `public_descriptor_hash` contract?
9. Which modern routes deserve a live A/B gate in the next iteration?

## 3. Primary sources

### OpenAI

- Plugin tool planning: `https://developers.openai.com/plugins/plan/tools`
- Plugin reference: `https://developers.openai.com/plugins/reference`
- Metadata optimization: `https://developers.openai.com/plugins/guides/optimize-metadata`
- Connect/test/refresh: `https://developers.openai.com/plugins/deploy/connect-chatgpt`
- Build Skills: `https://developers.openai.com/plugins/build/skills`
- Package Plugins: `https://developers.openai.com/plugins/build/plugins`
- Plugins Help Center: `https://help.openai.com/en/articles/20001256`
- Skills Help Center: `https://help.openai.com/en/articles/20001066`
- GPT-5.6 model guidance: `https://developers.openai.com/api/docs/guides/latest-model`

OpenAI's current tool-planning guidance is directly relevant to the architecture comparison. It says to group operations that represent one coherent action, but split operations when permissions, safety risks, or confirmation requirements differ. It also recommends separating reads from writes and describing user intent rather than internal implementation.

The current Plugin reference defines:

- `readOnlyHint: true` only for tools that retrieve/compute without creating, updating, deleting, or sending data;
- `destructiveHint: true` when a tool may delete/overwrite user data and the host should elicit explicit approval;
- `openWorldHint: true` for public/external effects;
- invocation labels under `_meta["openai/toolInvocation/invoking"]` and `.../invoked`.

### FastMCP

- Composition: `https://gofastmcp.com/servers/composition`
- Providers: `https://gofastmcp.com/servers/providers/overview`
- Transforms: `https://gofastmcp.com/servers/transforms/transforms`
- Tool Transformation: `https://gofastmcp.com/servers/transforms/tool-transformation`
- Tool Search: current FastMCP transform documentation discovered through the transforms index

### Soma repository/runtime

- `soma/server.py`
- `soma/mcp_flat_input.py`
- `soma/public_gateway_inventory.py`
- `soma/cf1_gateway_operation_inventory.py`
- `soma/knowledge_tools_integration.py`
- `soma/gateway_models.py`
- `tests/test_capabilities.py`
- `tests/test_gateway_benchmark.py`
- `tests/test_mcp_action_discovery.py`
- `docs/PUBLIC_CAPABILITY_METADATA_1_RESULT_2026-07-29.md`
- `docs/MEMORY_CONNECTOR_REFRESH_VERIFY_1_RESULT_2026-07-29.md`
- current live/disposable FastMCP probes listed below

## 4. Current ChatGPT host behavior changes the efficiency interpretation

### HOST-01 — Normal Chat already uses a host-side dynamic discovery layer

Observation from the current ChatGPT/Soma session:

1. Soma is exposed to the model as an `api_tool` resource/connector entry.
2. The harness initially supplies only lightweight connector/resource information.
3. `api_tool.list_resources` loads the relevant Soma function schemas on demand.
4. Only the dynamically selected Soma tool definitions then become callable in that turn/context.

This is a direct observation of the current runtime harness, not a documented stable OpenAI public contract. It may change again.

**Consequence:** the full MCP `tools/list` size is a real catalog/enrollment/discovery footprint, but it is **not proven to equal per-turn normal-Chat model context**.

This corrects a tempting but unsupported inference from the raw catalog measurement below. A 139 KB MCP catalog does not mean normal Chat consumes 139 KB of Soma schemas on every user turn.

It also explains part of the visual complaint: the generic `api_tool -> Call tool` event belongs to the host's dynamic connector-discovery layer. Soma cannot directly rename or remove that outer host card through MCP metadata alone.

Soma metadata can still improve the actual loaded Soma tool title, routing copy, invocation status, and safety framing after discovery.

## 5. Raw MCP catalog footprint

### M3-01 — Current served `tools/list` is 139,149 JSON bytes

Read-only/disposable runtime measurement:

**Run:** `20260811T211143Z_executable_profile_fad795c0`

```text
public tools:                 32
full descriptor JSON bytes: 139,149
input-schema bytes:          112,720
all description characters:   2,660
```

`tiktoken` was not installed in the Soma environment, so this research does **not** invent an exact token count from the byte count.

The important ratio is structural: most catalog weight comes from discriminated-union input schemas, not prose descriptions.

Largest descriptors:

| Tool | Descriptor bytes | Input-schema bytes |
|---|---:|---:|
| `knowledge_action` | 28,607 | 18,725 |
| `trading_query` | 13,805 | 13,311 |
| `knowledge_query` | 11,392 | 10,943 |
| `task_action` | 6,805 | 6,302 |
| `docker_action` | 5,661 | 5,078 |
| `run_query` | 5,599 | 5,095 |
| `ssh_action` | 5,404 | 4,823 |
| `repo_query` | 5,240 | 4,736 |
| `run_start` | 5,110 | 4,519 |
| `trading_companion_action` | 4,819 | 4,105 |

### M3-02 — Domain concentration is large

**Run:** `20260811T211221Z_executable_profile_e5bab0e2`

| Family | Tools | Descriptor bytes | Input-schema bytes |
|---|---:|---:|---:|
| knowledge | 2 | 39,999 | 29,668 |
| trading | 8 | 26,706 | 22,340 |
| repository | 4 | 12,444 | 10,421 |
| ssh | 3 | 11,924 | 10,337 |
| runs | 3 | 11,540 | 9,854 |
| tasks | 2 | 9,997 | 8,984 |
| docker | 2 | 7,523 | 6,439 |
| cloudflare | 2 | 6,320 | 5,228 |
| supervisors | 2 | 4,918 | 3,866 |
| system | 2 | 4,373 | 3,350 |
| workflows | 2 | 3,372 | 2,233 |

This supports examining modular surfaces, but HOST-01 prevents claiming direct per-turn token savings without a live ChatGPT A/B measurement.

## 6. Metadata copy is cheap but cannot be the efficiency solution

A candidate metadata pass for 15 core engineering tools was measured without changing source.

The first probe was explicitly flagged by the harness as unreliable and is not used as evidence. The measurement was rerun successfully.

**Authoritative rerun:** `20260811T212555Z_executable_profile_428c81cf`

```text
candidate tools:                    15
old description chars:           1,138
new description chars:           2,120
added description chars:           982
title + invocation-status chars: 1,020
total added human metadata chars:2,002
full catalog baseline bytes:    139,149
```

The copy is therefore a small addition relative to schema weight.

This is good news for routing quality: modern titles/descriptions/status labels can be added without meaningful raw catalog inflation. But it also means metadata copy by itself cannot solve catalog-size efficiency.

## 7. Gateway operation density and intent boundaries

A full live inventory counted discriminated operations per gateway.

**Run:** `20260811T211413Z_executable_profile_748f865e`

Highest operation counts:

```text
docker_action       37
cloudflare_action   31
trading_query       30
knowledge_action    18
knowledge_query     18
run_query           14
repo_query          10
ssh_action           8
ssh_query            7
trading_runtime_control 7
task_action          6
task_query           6
system_query         6
run_start            5
```

Operation count alone is **not** a split rule. A ten-operation read gateway may still be one coherent user goal.

The stronger split triggers are the ones OpenAI now documents: user-goal distinction, permission difference, safety risk, and confirmation requirement.

### Candidate mixed-boundary gateways

#### `knowledge_query` / `knowledge_action`

Currently combine four different semantic systems:

1. canonical Soma project memory;
2. repository wiki;
3. legacy/general repository knowledge;
4. research source/evidence platform.

A variant-only size estimate was computed from the existing schemas:

**Run:** `20260811T211615Z_executable_profile_5e1df4b8`

```text
canonical memory: 17,488 input-schema bytes (~58.9% of current knowledge input)
wiki:              2,165 (~7.3%)
legacy knowledge:  5,985 (~20.2%)
research:          5,272 (~17.8%)
```

The percentages overlap slightly because the estimate preserves common root/discriminator material per candidate subset. It is a planning estimate, not a proposed final wire contract.

The memory audit already proves that this semantic mixture causes routing confusion. This is the strongest candidate for an intent-based split regardless of raw size.

#### `ssh_action`

Combines ordinary commands, monitored commands, reviewed scripts, unrestricted root shell, administration, transfer, deployment, and profile application. Those have materially different authority and risk profiles.

#### `docker_action`

Combines ordinary build/start/stop operations with container/image/network/volume removal and system/prune operations.

#### `cloudflare_action`

Combines DNS writes, cache purge, SSL/security settings, rulesets, Turnstile, and tunnel create/update/delete operations.

#### `task_action`

Combines ordinary task lifecycle/interaction with owner-only recovery and quarantine adjudication.

#### `run_start`

Combines local PowerShell, remote PowerShell, PowerShell groups, Hermes companion, and Hermes service operations.

These candidates require a safety/UX comparison, not automatic splitting.

## 8. Safety annotation defect discovered

### SAFETY-001 — Soma's public write annotation model cannot represent destructive variants

Soma has a generic write template in both `soma/server.py` and `soma/knowledge_tools_integration.py`:

```python
WRITE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "idempotentHint": False,
    "openWorldHint": False,
}
```

A full source search found **zero** occurrences of:

```text
"destructiveHint": True
```

anywhere under `soma/`.

Current OpenAI Plugin semantics say `destructiveHint` should be true when a tool may delete/overwrite user data; the tool-planning guidance broadens the planning criterion to irreversible or difficult-to-reverse outcomes and says operations with different safety/confirmation requirements should be split.

At least two live public gateways are unambiguously misrepresented by `destructiveHint: false`:

### Confirmed affected: `docker_action`

Live/public operations include:

```text
compose_down_volumes
container_remove
image_remove
network_remove
volume_remove
builder_prune
container_prune
image_prune
network_prune
volume_prune
system_prune
system_prune_volumes
```

A volume removal or volume-inclusive prune can destroy data. A single public descriptor claiming the entire gateway is non-destructive is therefore false for some valid variants.

### Confirmed affected: `cloudflare_action`

Live/public operations include:

```text
delete_dns_record
dns_delete
ruleset_delete
ruleset_rule_delete
turnstile_delete
tunnel_delete
tunnel_route_delete
```

These are consequential external deletions. The gateway already correctly carries `openWorldHint: true`, but still advertises `destructiveHint: false` for every variant.

### Review-required mixed gateways

A mechanical operation-name scan found seven additional write gateways containing words such as cancel, stop, rollback, revert, or archive:

- `task_action`
- `workflow_action`
- `system_action`
- `supervisor_action`
- `trading_runtime_control`
- `repo_apply`
- `knowledge_action`

Those are **not automatically classified as destructive**. A cancellation, rollback, archive, or revert can be safe/reversible under its domain contract. They require operation-level semantic review before changing annotations.

**Inventory run:** `20260811T212500Z_executable_profile_7380cb62`

### Architectural consequence

This is more than a boolean bug. A single MCP tool descriptor has one annotation set, while `docker_action` and `cloudflare_action` contain both ordinary and destructive variants.

Three possible fixes exist:

1. mark the entire broad gateway destructive, causing approval framing even for benign variants;
2. split the gateway by safety/confirmation boundary;
3. introduce some host-supported operation-level policy mechanism if one exists and proves equivalent.

Under current OpenAI guidance, option 2 is the cleanest architecture candidate and now has a safety reason independent of UX or token savings.

## 9. `public_descriptor_hash` design became clearer

### M3-03 — Exact served descriptor is stable across fresh processes

**Run:** `20260811T211638Z_executable_profile_d862663d`

Three independent fresh Python processes generated the exact same deterministic SHA-256 when hashing the sorted served `tools/list` JSON:

```text
182f20f67d486eec02ec9911ba476107d78bed42718e4b0ca3425d3eae360af6
182f20f67d486eec02ec9911ba476107d78bed42718e4b0ca3425d3eae360af6
182f20f67d486eec02ec9911ba476107d78bed42718e4b0ca3425d3eae360af6
```

This includes the current FastMCP-generated metadata that clients actually receive.

**Research conclusion:** the cleanest `public_descriptor_hash` candidate is the exact served descriptor snapshot, sorted deterministically by tool name and JSON keys. Do not normalize SDK-owned fields merely because Soma did not author them. If an MCP client receives/caches a field and that field changes, the descriptor identity should move.

`public_schema_hash` remains unchanged in meaning: input contract only.

## 10. Modern FastMCP ToolTransform comparison

FastMCP 3.x `ToolTransform` is designed to modify titles, descriptions, tags, metadata, annotations, and argument schemas as tools flow through providers. Architecturally this looked cleaner than Soma's registration hook because presentation could be separated from handler implementation.

### COMPAT-001 — Generic ToolTransform destroys Soma's flat discriminated union contract

Disposable test:

**Run:** `20260811T211915Z_executable_profile_b88219b9`

A metadata-only transform was applied to `repo_query` to change only:

- title;
- description;
- invocation metadata.

Result:

- title changed correctly;
- description changed correctly;
- metadata merged correctly;
- annotations remained;
- output schema remained;
- **input schema changed.**

Detailed reproduction:

**Run:** `20260811T211934Z_executable_profile_ce3b70c8`

Before:

```text
root keys: type, properties, required, oneOf
oneOf branches: 10
```

After metadata-only `ToolTransform`:

```text
root keys: type, properties, required, additionalProperties
oneOf branches: 0
only operation enum remained
all operation-specific fields disappeared
```

This would make the transformed gateway unusable for its real operations.

**Verdict:** the generic modern transform loses this comparison for current Soma. Registration-time metadata injection remains the safer candidate **because it preserves the proven public schema**, not because it is cheaper.

A custom flat-schema-aware transform could be designed later, but it needs a concrete advantage over registration-time metadata before adding another abstraction.

## 11. Modern FastMCP Tool Search comparison

FastMCP 3.x provides Tool Search transforms that replace a large tool catalog with search + execution proxies.

### M3-04 — Enormous raw catalog reduction

**Run:** `20260811T211719Z_executable_profile_2fa8ceb5`

Applying `BM25SearchTransform(max_results=8)` to the current Soma server produced:

```text
before: 32 tools / 139,149 descriptor bytes
after:   2 tools /   1,226 descriptor bytes
raw reduction: ~99.1%
```

The visible tools became only:

```text
search_tools
call_tool
```

### But the safety/UX contract regressed

Both synthetic tools exposed:

```text
annotations: null
```

The transform constructor exposes search/result/naming controls but no direct per-original-tool safety annotation preservation on the public `call_tool` proxy.

**Constructor probe:** `20260811T211739Z_executable_profile_874fa022`

Consequences for Soma normal Chat:

1. host-visible read/write/destructive/open-world distinctions collapse behind one generic execution tool;
2. every hidden operation is invoked through a generic `call_tool` descriptor;
3. most flows add an extra search hop before execution;
4. the visible conversation could become even more `search tool -> call tool` oriented—the exact UX regression under investigation;
5. approval framing would be based on the proxy rather than the original operation unless a more sophisticated safety-aware proxy were designed.

**Verdict:** reject unmodified FastMCP Tool Search as Soma's primary normal-Chat surface despite its dramatic catalog reduction.

This is an important example of the owner's research rule: a newer and vastly smaller route is still worse when it destroys critical safety semantics and user interaction quality.

### OpenAI native API Tool Search is a separate future route

Current OpenAI API model/tool documentation supports native Tool Search/deferred loading for selected models in the Responses API. That is a strong modern option for a future custom API/agent runtime.

However, Iteration 3 did not find equivalent `defer_loading`/native Tool Search behavior documented in the current normal-Chat Plugin MCP reference. Do not design the normal-Chat patch around an API-only assumption.

## 12. Modular MCP server views

FastMCP supports composition, providers, mounting/importing, tag filtering, and focused subservers.

Instead of rewriting Soma handlers, Iteration 3 tested whether the already-correct registered Tool objects can be re-exposed through a focused server.

### M3-05 — Focused engineering view preserves schemas

A new in-memory `FastMCP("Soma Engineering")` was populated with the existing registered Tool objects for:

```text
repo_query
repo_preview
repo_apply
repo_commit
run_query
run_start
cancel_run
task_query
task_action
workflow_query
workflow_action
supervisor_query
supervisor_action
system_query
system_action
```

**Run:** `20260811T212002Z_executable_profile_b4bf7dfe`

Result:

```text
tools: 15
descriptor bytes: 46,660
input schemas preserved:  yes
output schemas preserved: yes
```

That is about a 66.5% raw MCP catalog reduction relative to the monolithic 139,149-byte surface.

### M3-06 — Focused view can execute the existing flat gateway

The first call probe failed before routing because the disposable Python process had not loaded Soma configuration. This is a research setup error, not a modular-server defect.

After bootstrapping the same `config.yaml` used by Soma:

**Run:** `20260811T212050Z_executable_profile_dbd62632`

A flat call through the focused server succeeded:

```text
repo_query(
  operation="status",
  repo_name="Soma",
  view="compact"
)

is_error: false
ok: true
repo_name: soma
head_commit: 24fa7774...
```

No handler rewrite was required.

### Interpretation after HOST-01

This proves modular server views are technically viable and preserve Soma contracts. It does **not** prove they reduce normal-Chat per-turn context, because ChatGPT's current connector harness already dynamically loads Soma function schemas.

Modularization may still improve:

- installation/enrollment catalog size;
- permission and safety isolation;
- domain discoverability;
- independent plugin/application composition;
- testability and maintenance boundaries;
- ability to expose only relevant domain capabilities to other controllers.

It requires an actual ChatGPT-side A/B before being chosen primarily for efficiency.

## 13. Current connection and transport baseline

Tracked repository evidence still describes the current ChatGPT route as:

```text
https://mcp.spaceshipgames.win/mcp
```

served through the existing Cloudflare tunnel configuration.

**Evidence run:** `20260811T211124Z_executable_profile_5c68dc44`

No `plugin_asdk_app...` registered-connection technical ID is versioned in the repository.

Current OpenAI documentation now also supports **Secure MCP Tunnel** for private developer-mode MCP servers without exposing the server publicly. This is a genuine modern transport candidate.

It is independent of the current tool-card UX problem. A transport migration must be evaluated separately for privacy, reliability, availability, and operational cost; it should not be bundled into the first UX patch without evidence.

## 14. Plugin and Skill feasibility

Current OpenAI architecture now allows a plugin package to contain:

```text
.codex-plugin/plugin.json
skills/
.app.json       # mapping to registered MCP connection
.mcp.json       # bundled MCP server configuration when applicable
optional assets/hooks
```

For a registered MCP connection, the current docs use a technical connection ID beginning `plugin_asdk_app...` in `.app.json` wiring.

A Skill can teach a repeatable workflow while the MCP server remains responsible for live data, authorization, and controlled actions. This remains an excellent conceptual fit for:

```text
understand intent
-> explain meaningful next action
-> inspect through Soma
-> perform only authorized changes
-> validate
-> report coherently
```

However, current OpenAI Help guidance makes capability availability plan/surface dependent. Personal Skills are generally documented for Business, Enterprise, Healthcare, and Edu, while Plugins can package Skills and Apps and the Plugins Directory is visible broadly. Local/private plugin testing also has specific supported-surface workflows.

**Iteration 3 conclusion:** do not make a Skill a hard dependency for the existing normal-Chat path until the exact target ChatGPT web installation route is proven. Keep Skill packaging as a high-value modern enhancement candidate, not a prerequisite for basic Soma operation.

## 15. Architecture comparison matrix

Scores are qualitative research status, not final owner decisions.

| Candidate | Routing | Safety semantics | Raw catalog efficiency | Normal-Chat support confidence | Extra call overhead | Migration cost | Iteration-3 disposition |
|---|---|---|---|---|---|---|---|
| A. Current monolith + modern metadata | improved | unchanged; currently flawed on destructive variants | unchanged | **high** | low | low | baseline; still viable |
| B. Monolith + FastMCP Tool Search | proxy-dependent | **regresses** original annotations | **excellent (~99.1% raw reduction)** | technically MCP-compatible | high/search hop | medium | **reject unmodified** |
| C. Focused modular MCP views + native tools | potentially improved | preserves original annotations | strong raw reduction per module | needs ChatGPT A/B | low | medium/high | **leading experiment candidate** |
| D. Selective intent/safety splits + modern metadata | potentially strongest | **can fix mixed-risk descriptors** | could improve or worsen total catalog depending exposure | high if kept in normal MCP | low | high | **leading architecture candidate where evidence supports split** |
| E. Repo-owned Plugin + Skill | potentially strong workflow UX | server retains safety authority | plugin-dependent | availability/install path must be proven | low after activation | medium/high | promising enhancement, not core dependency yet |
| F. OpenAI API native Tool Search | strong for custom API route | can use native tool contracts | excellent | **not proven for normal-Chat Plugin path** | model-managed | high/new runtime | future API/controller candidate |
| G. Secure MCP Tunnel | neutral to routing | neutral | neutral | documented developer-mode option | neutral | medium | separate transport experiment only |

### Current leading hypothesis

The most promising **product** architecture is not one giant rewrite and not a return to hundreds of direct tools.

It is a selective modernisation:

1. keep coherent read surfaces consolidated where they work well;
2. split gateways only where user goals, permissions, safety, or confirmation boundaries genuinely differ;
3. fix the public descriptor/safety model;
4. add modern human titles, invocation labels, and measured routing copy;
5. add exact descriptor identity and activation evidence;
6. optionally package workflow guidance as a Plugin/Skill when the target web surface supports it;
7. use modular server views only when live A/B evidence shows a real benefit beyond ChatGPT's existing dynamic discovery.

This is a hypothesis to test, not a final implementation plan.

## 16. Bug and risk ledger — Iteration 3

### UX-001 — Missing human-readable tool titles

**Status:** confirmed, carried forward.

### UX-002 — Missing OpenAI invocation labels

**Status:** confirmed, carried forward.

### ROUTE-001 — Descriptions are implementation-centric

**Status:** confirmed and already quantitatively measured.

### IDENTITY-001 — No exact descriptor identity

**Status:** confirmed. Exact served-descriptor hashing is now proven stable in three fresh processes.

### DOC-001 — Memory audit incorrectly says description edits move `public_schema_hash`

**Status:** confirmed; correction still pending implementation/documentation stage.

### SAFETY-001 — Mixed-risk public write gateways advertise `destructiveHint: false`

**Status:** **new confirmed product defect.** At minimum `docker_action` and `cloudflare_action` contain valid destructive variants while advertising false. No Soma public tool advertises true anywhere in source.

**Impact:** host approval framing cannot accurately reflect those operations. Current OpenAI guidance explicitly uses these hints to frame approval and recommends splitting operations when safety/confirmation requirements differ.

### SAFETY-002 — Remaining mixed write gateways need operation-level annotation audit

**Status:** review required, not yet a bug verdict.

Candidates: `ssh_action`, `run_start`, `task_action`, `workflow_action`, `system_action`, `supervisor_action`, `trading_runtime_control`, `repo_apply`, `knowledge_action`, and broker/demo trading actions.

The review must classify destructive and open-world behavior semantically, not by operation names alone.

### COMPAT-001 — FastMCP `ToolTransform` strips Soma's flat `oneOf` branches

**Status:** new confirmed compatibility blocker for the tested metadata-only transform route.

This is not a current production regression because Soma does not use that transform. It is evidence against adopting the generic transform without a flat-schema-aware fix.

### SEARCH-001 — FastMCP Tool Search collapses safety annotations behind generic proxy tools

**Status:** new confirmed architecture blocker for unmodified use as Soma's normal-Chat surface.

### HOST-001 — Full MCP catalog size is not equal to observed per-turn ChatGPT tool context

**Status:** important measurement correction / host boundary, not a Soma bug.

Current ChatGPT dynamically loads matching connector tool schemas. Actual host-side per-turn cost must be measured experimentally rather than inferred from `tools/list` bytes.

### PLUGIN-001 — No repo-owned Plugin/Skill package

**Status:** confirmed capability gap, not necessarily a bug.

### DEP-001 — FastMCP dependency remains unbounded

**Status:** confirmed reproducibility risk. Iteration 3 increased the importance of version compatibility because newer transform behavior is now directly relevant.

### UX-003 — Optional status/result UI

**Status:** still deferred. Nothing in Iteration 3 justifies making UI part of the first implementation stage.

## 17. Research incidents deliberately not promoted to bugs

1. A broad repository text search timed out. A bounded `git grep` supplied the needed connection evidence.
2. The first focused-subserver execution failed because the disposable process had not called `load_config`; the corrected bootstrap succeeded.
3. One candidate-metadata probe was marked unreliable by the harness; it was rerun successfully as `20260811T212555Z_executable_profile_428c81cf` and only the rerun is authoritative.

## 18. What Iteration 3 rules out

1. Do not pick the existing monolith merely because it is already implemented.
2. Do not split gateways merely because they have many operations.
3. Do not claim the 139 KB `tools/list` is paid/per-turn ChatGPT context.
4. Do not adopt generic FastMCP Tool Search as the public normal-Chat route without solving its safety/approval proxy problem.
5. Do not use generic `ToolTransform` for Soma metadata while it strips flat union branches.
6. Do not mark every write tool destructive merely because it mutates state.
7. Do not leave confirmed destructive variants under an unqualified `destructiveHint: false` descriptor.
8. Do not make Plugin Skills a hard dependency until the exact target web installation path is verified.
9. Do not migrate transport to Secure MCP Tunnel merely because it is newer; evaluate it separately.
10. Do not restore the retired coding-agent route to solve this normal-Chat issue.

## 19. Iteration 4 research targets

Iteration 4 should now be narrower and more decision-oriented:

### A. Full safety/annotation audit

For every 32 public tools and every discriminated operation:

- classify read-only vs state-changing;
- classify destructive vs reversible;
- classify open-world/external effects;
- classify idempotency truthfully;
- identify which gateways cannot express truthful annotations without a split.

This should produce the exact minimum safety-driven split proposal.

### B. Selective split prototypes

Prototype schemas only, without production mutation, for the strongest candidates:

1. `knowledge_*` -> canonical memory / wiki / research / legacy boundary;
2. `docker_action` -> ordinary lifecycle/build vs destructive cleanup/removal;
3. `cloudflare_action` -> ordinary update vs delete/destructive groups;
4. `ssh_action` / `run_start` only if the annotation audit proves mixed external/high-risk boundaries require separation;
5. task/recovery only if owner-only recovery semantics materially improve with an explicit tool boundary.

Measure:

- descriptor size;
- routing ambiguity;
- truthful annotations;
- required confirmations;
- compatibility with existing handlers and clients.

### C. Host-side A/B gate design

Before changing the live connection, define a reproducible Developer-mode trial comparing:

- current baseline;
- metadata-only baseline improvement;
- selective split candidate;
- focused modular server candidate if still justified.

Use G01-G24 plus new destructive-action prompts.

Capture:

- `api_tool` discovery calls;
- Soma tool calls;
- unnecessary call count;
- selected gateway/action;
- approval behavior;
- visible tool title/status;
- explanation-before-mutation;
- final coherent report;
- latency where observable.

No connection refresh should occur until the owner explicitly approves the live A/B gate.

### D. Plugin/Skill availability check

Verify the exact target ChatGPT web surface and supported local/plugin installation route without assuming Personal Skills availability. If the route is available, draft one narrow `soma-engineering` Skill and compare it against metadata-only behavior. If unavailable, do not block the MCP patch.

### E. Dependency boundary

Determine a tested FastMCP compatibility range covering:

- flat-input behavior;
- metadata passthrough;
- served-descriptor stability;
- composition/server views;
- any selected transform/provider APIs.

## 20. Iteration 3 verdict

Iteration 3 materially changes the direction of the research.

The current monolithic 32-tool server is no longer presumed optimal, but neither are newer primitives presumed superior.

Two modern FastMCP routes were tested and rejected in their generic form:

- Tool Search is dramatically smaller but collapses safety semantics and likely worsens the visible search/call-tool interaction;
- ToolTransform is architecturally elegant but currently destroys Soma's flat discriminated union schema.

One modern route tested well:

- focused FastMCP server views can reuse the existing Tool objects, preserve schemas, execute correctly, and substantially reduce the raw catalog for a domain.

But the current ChatGPT harness already performs host-side dynamic schema discovery, so modularization needs live host evidence before it can claim normal-Chat efficiency gains.

The most important new defect is not cosmetic: Soma currently has no way to truthfully annotate mixed destructive/non-destructive variants inside broad write gateways. `docker_action` and `cloudflare_action` are confirmed examples.

The strongest next research direction is therefore **selective safety- and intent-aligned modernization**, evaluated against the real ChatGPT host workflow, rather than a blanket metadata patch or blanket topology rewrite.
