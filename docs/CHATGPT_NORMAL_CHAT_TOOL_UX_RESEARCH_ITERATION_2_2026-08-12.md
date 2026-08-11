# ChatGPT Normal-Chat Tool UX Research — Iteration 2

**Date:** 2026-08-12  
**Status:** research and investigation only; no production code change  
**Repository:** `D:\Github\Soma`  
**Starting HEAD:** `24fa7774d97e8a04bed3ec79054ae9b66182fd39`  
**Live server build:** `f55d37e7d65b7389a3f33ae0911a4a95ab93e9746b76e720b19dd1f40bc8e765`  
**Live public input-schema hash:** `84d0af8b66d7df990320268ba905bf536cbb2722dfabf6cda30aaa5e93f9012c`  
**Follows:** `CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_1_2026-08-12.md`

## 1. Research question

Iteration 1 established that the visible `api_tool -> Call tool` card is host-owned, while Soma currently fails to provide several supported human-facing MCP signals. Iteration 2 asks what can be changed safely and how an eventual patch can be measured rather than judged by appearance alone.

The specific questions are:

1. What does ChatGPT cache at MCP/plugin enrollment and what requires an explicit refresh?
2. Does Soma's current `FlatGatewayTool` preserve human-facing descriptor metadata?
3. Does the existing `public_schema_hash` identify those changes?
4. What identity should Soma use for exact `tools/list` descriptor drift without redefining an accepted compatibility field?
5. Is a repository-owned Plugin/Skill a supported way to teach `explain -> act -> validate -> report`?
6. What representative prompt corpus should be frozen before tuning metadata?
7. Should optional UI be part of the first patch or held until metadata/skill A/B evidence exists?

## 2. Sources inspected

### Soma repository and runtime

- `soma/server.py`
- `soma/mcp_flat_input.py`
- `soma/gateway_models.py`
- `soma/public_gateway_inventory.py`
- `soma/public_footprint_measurement.py`
- `tests/test_capabilities.py`
- `tests/test_mcp_action_discovery.py`
- `tests/test_gateway_benchmark.py`
- `docs/PUBLIC_CAPABILITY_METADATA_1_RESULT_2026-07-29.md`
- `docs/MEMORY_CONNECTOR_REFRESH_VERIFY_1_GATE_2026-07-29.md`
- `docs/MEMORY_CONNECTOR_REFRESH_VERIFY_1_RESULT_2026-07-29.md`
- `docs/RELIABILITY_1_OPERATOR_RUNBOOK_2026-08-01.md`
- `docs/MCP_OPERATION_USAGE_INSTRUMENTATION_1_GATE_2026-07-29.md`
- live `system_query(operation="capabilities")`
- disposable FastMCP descriptor probes through `run_start`
- repository file inventory for Plugin/Skill packaging files

### Current OpenAI primary documentation

- Plugin reference: `https://developers.openai.com/plugins/reference`
- Optimize Metadata: `https://developers.openai.com/plugins/guides/optimize-metadata`
- Connect and test your plugin: `https://developers.openai.com/plugins/deploy/connect-chatgpt`
- Build skills: `https://developers.openai.com/plugins/build/skills`
- Package your plugin: `https://developers.openai.com/plugins/build/plugins`
- UI guidelines: `https://developers.openai.com/plugins/concepts/ui-guidelines`
- Plugins in ChatGPT and Codex: `https://help.openai.com/en/articles/20001256`
- Skills in ChatGPT: `https://help.openai.com/en/articles/20001066`
- GPT-5.6 model guidance: `https://developers.openai.com/api/docs/guides/latest-model`

### FastMCP primary documentation/runtime

- installed runtime: FastMCP `3.4.2`
- tool metadata API inspected directly from the installed package
- `https://gofastmcp.com/servers/tools`
- `https://gofastmcp.com/apps/overview`

## 3. Platform findings

### P2-01 — Developer-mode MCP metadata is snapshot-like, not live-per-turn

Current OpenAI documentation explicitly says that after changing tool names, descriptions, schemas, annotations, authentication, or UI resources, the developer must:

1. deploy or restart the MCP server;
2. open the ChatGPT plugin connection;
3. select **Refresh**;
4. confirm that advertised metadata changed;
5. start a new conversation and rerun tests.

Published plugins use reviewed metadata snapshots and require a new scan/submission/publish cycle for metadata updates.

**Consequence:** a correct Soma metadata patch can remain invisible to ChatGPT until the appropriate connection snapshot is refreshed. Activation evidence must distinguish source, running MCP discovery, and ChatGPT's enrolled snapshot.

### P2-02 — OpenAI explicitly requires golden-prompt routing evaluation

The current Optimize Metadata guide says to freeze direct, indirect, and negative prompts before tuning, document the expected behavior, and replay them while recording selected tool and arguments. The connection-testing guide adds follow-ups, write/confirmation cases, and unsupported requests.

This strongly supports treating Soma descriptor work as a routing change with measurable precision/recall, not a cosmetic rewrite.

### P2-03 — Current recommended description style is materially different from Soma's

OpenAI currently recommends descriptions that start with user-trigger language such as `Use this when...` and call out disallowed cases.

Soma's current descriptors were quantitatively measured:

```text
public tools:                32
start with "Read-only":       13
start with "Write":           12
contain "gateway":            25
start with "Use this when":    0
average description chars:   83.1
maximum description chars:  269
```

This does not make the existing descriptions incorrect. It demonstrates that they were written primarily as implementation/control-plane summaries rather than as current Plugin-era routing copy.

### P2-04 — Invocation labels are supported descriptor metadata

OpenAI's Plugin reference defines:

- `_meta["openai/toolInvocation/invoking"]` — short text while a tool runs;
- `_meta["openai/toolInvocation/invoked"]` — short text after completion.

Both are bounded to 64 characters. They are presentation signals, not safety/authorization controls.

### P2-05 — Skills are a supported workflow layer separate from MCP execution

A Skill has a required `SKILL.md` and can specify trigger conditions, workflow steps, required output, stop/ask rules, and supporting resources. OpenAI explicitly says a Skill can guide the model through MCP tools: use the Skill for workflow instructions and the server for live data, authorization, and controlled actions.

That maps cleanly to Soma's UX requirement:

```text
understand owner intent
-> explain the next meaningful action
-> inspect through Soma
-> make only authorised changes
-> validate
-> report one coherent result
```

This should remain separate from the MCP safety/authority contract. A Skill may guide behavior; it must not become authorization.

### P2-06 — Plugin packaging is a real additional artifact, not hidden in the current repo

OpenAI's current package shape requires `.codex-plugin/plugin.json` and may include `skills/`, `.app.json`, `.mcp.json`, assets, and hooks.

A complete Soma repository inventory found none of these Plugin package files. The currently connected Soma MCP surface therefore must not be described as already having a repo-owned Plugin/Skill package.

The earlier `soma-agent:soma-operator` inline harness skill observed in Claude is a different external/harness-injected surface and is not a repository-owned ChatGPT Plugin artifact.

### P2-07 — Plugins are available in ChatGPT web, but Skill availability remains account/surface dependent

OpenAI says the Plugin Directory is available on ChatGPT web and desktop and can package Apps plus Skills. It also says installation/invocation depends on plan, workspace settings, role, supported surface, region, and included capabilities. Personal Skills have narrower eligibility and may need separate installation across web/mobile and desktop.

**Consequence:** a repo-owned Skill is a valid design candidate, but the first implementation plan must not make normal Chat functionality depend on a Skill until the owner's actual connected surface is verified to load it.

### P2-08 — Inline UI should remain a later, focused layer

OpenAI's UI guidance positions inline cards as lightweight, single-purpose surfaces for quick status, confirmations, or small structured results and warns against deep/multi-view cards.

No evidence yet proves that an inline Soma card is required to solve the complaint. Titles, invocation labels, routing metadata, and workflow guidance should be evaluated first. UI remains a second-stage enhancement candidate for one coherent status/result surface, not every low-level tool call.

## 4. Live Soma findings

### S2-01 — `FlatGatewayTool` preserves title and OpenAI metadata exactly

A disposable FastMCP probe constructed a `FlatGatewayTool` with:

```text
title: Human title
description: Use this when testing metadata.
meta:
  openai/toolInvocation/invoking: Working
  openai/toolInvocation/invoked: Done
  custom:
    x: 1
```

`mcp.list_tools()` followed by `to_mcp_tool().model_dump(mode="json")` preserved all fields.

**Run evidence:** `20260811T205729Z_executable_profile_420e904c`

**Conclusion:** the existing flattening architecture is compatible with the proposed metadata. There is no justification for replacing `FlatGatewayTool` merely to add titles/status labels.

### S2-02 — Live descriptor absence reconfirmed in a bounded runtime probe

A separate live probe over all 32 public tools measured:

```text
count:              32
titles_nonnull:      0
meta_non_fastmcp:    0
```

Representative `run_start`, `repo_query`, `repo_apply`, `knowledge_query`, and `knowledge_action` descriptors all had `title: null` and only `meta.fastmcp.tags=[]`.

**Run evidence:** `20260811T205710Z_executable_profile_648a1ea4`

### S2-03 — `public_schema_hash` intentionally does not identify descriptor metadata

Iteration 1 called this a contract bug too broadly. The historical `PUBLIC-CAPABILITY-METADATA-1` result shows that `public_schema_hash` was intentionally defined as **served public input-schema identity**. Its accepted movement rule is:

- input contract changes -> hash moves;
- implementation-only changes -> hash does not move.

That narrow meaning should be preserved for compatibility.

A disposable live-discovery mutation changed one tool's `title`, `description`, and OpenAI invocation metadata while leaving input schemas untouched. The hash remained exactly:

```text
84d0af8b66d7df990320268ba905bf536cbb2722dfabf6cda30aaa5e93f9012c
```

before and after.

**Run evidence:** `20260811T205901Z_executable_profile_6a3d59e3`

**Corrected conclusion:** the defect is a **missing descriptor identity dimension**, not a broken `public_schema_hash` implementation.

### S2-04 — A full served-descriptor hash is technically straightforward and stable in a disposable probe

A candidate hash was computed over the exact served descriptor fields per tool:

```text
name
title
description
inputSchema
outputSchema
icons
annotations
meta
execution
```

sorted deterministically by tool name/key.

Baseline candidate value on the current 32-tool surface:

```text
80f16d9c0028d185024b82e5264be7f0ee1b8343d17ea96ff83b7234f2e1dfbe
```

Properties proven in the disposable probe:

- repeated hashing of unchanged discovery: stable;
- title + invocation-meta mutation: hash moves;
- input-schema mutation: hash moves.

**Run evidence:** `20260811T210158Z_executable_profile_2b741874`

This is evidence that a separate `public_descriptor_hash` is feasible. It is not yet an approved field definition; exact inclusion/exclusion policy still needs implementation review.

### S2-05 — `discovery_cache_generation` is useful but not an exact descriptor identity

Current `discovery_cache_generation` hashes:

- operation inventory version/hash;
- `public_schema_hash`;
- server build hash;
- capability epoch.

A Python metadata edit would normally move the build hash and therefore move `discovery_cache_generation` after restart. But it does not answer **what descriptor ChatGPT should have cached**, and it does not cover a future Skill/plugin package independently of Python source.

It should remain a conservative cache-generation signal. It should not be relabelled as a descriptor hash.

### S2-06 — `capability_identity` cannot by itself observe ChatGPT's frozen descriptor snapshot

`capability_identity` compares live/source state to **expected values supplied by the caller**. It has no API into ChatGPT's current frozen connection metadata.

Therefore it can say a supplied connector generation/hash is stale, but it cannot independently prove that ChatGPT refreshed a title, description, invocation label, Skill, or plugin manifest. That proof still requires connection refresh/readback plus a fresh-conversation behavioral test.

This is a boundary, not necessarily an implementation bug.

### S2-07 — One current audit statement is factually wrong

`docs/CANONICAL_MEMORY_WORKFLOW_AUDIT_2026-08-04.md` currently says a gateway-description change:

```text
changes public_schema_hash
```

The live mutation probe disproves that. A description-only change does not alter the current hash because the hash intentionally covers input schemas only.

The audit's operational conclusion that a description edit needs server activation and connector refresh remains directionally correct, but its identity claim is wrong and must be corrected before that audit is used as activation authority.

### S2-08 — Current operator guidance predates descriptor-aware identity

The operator runbook correctly separates:

- source/running build mismatch -> restart;
- connector-only contract mismatch -> connector refresh.

But it was written before Soma had a need to distinguish input-schema identity from full Plugin-era descriptor identity. An eventual descriptor patch should extend the operator evidence model rather than silently changing the meaning of existing fields.

### S2-09 — Current gateway benchmark protects structure, not model-selection behavior

`tests/test_gateway_benchmark.py` validates the 32-tool inventory, input/output schemas, annotations, retirement boundaries, and transport serialization. It does not evaluate semantic tool selection or conversational workflow.

A golden prompt corpus therefore belongs beside, not inside, the existing deterministic schema benchmark. Local deterministic tests should validate descriptor shape; fresh ChatGPT tests should validate routing behavior.

## 5. Recommended identity model — research conclusion, not implementation approval

Keep three identities conceptually separate:

### A. Callable input contract

Existing field:

```text
public_schema_hash
```

Meaning remains exactly as accepted: served tool names + effective input schemas.

### B. Exact MCP discovery descriptor

Candidate new field:

```text
public_descriptor_hash
```

Potential meaning: deterministic identity of the served `tools/list` descriptor snapshot, including the user/controller-facing fields ChatGPT may cache.

Candidate source fields:

```text
name
title
description
inputSchema
outputSchema
icons
annotations
meta
execution
```

The implementation review must decide whether FastMCP-internal metadata should be included verbatim or normalized out. The guiding question is not "does Soma care about this field?" but "does a connected MCP client receive/cache this field?"

### C. Plugin package/workflow snapshot

Future separate identity, only if Soma is formally packaged as a Plugin:

```text
plugin_package_hash / plugin_version
```

It would cover artifacts outside `tools/list`, for example:

- `.codex-plugin/plugin.json`;
- repo-owned Skill content and supporting references;
- `.app.json` mapping;
- optional UI bundle/resource manifests.

Do not mix this into `public_schema_hash` or rely on `server_build_hash` to represent it indirectly.

## 6. Golden prompt corpus v0

This corpus is frozen from recurring real Soma interaction patterns before metadata tuning. It is a starting benchmark, not a complete product test suite.

| ID | Representative owner prompt | Expected Soma behavior | Expected gateway family | Conversational requirement |
|---|---|---|---|---|
| G01 | `check the audit docs/CANONICAL_MEMORY_WORKFLOW_AUDIT_2026-08-04.md` | read relevant file/status only | `repo_query` | explain what is being checked, then report findings |
| G02 | `did we repatch the agent code route?` | inspect history/source/live state; do not launch an agent | `repo_query` + read-only run evidence if needed | answer the architecture question, not merely dump tools |
| G03 | `what changed recently around the gateway patch?` | inspect Git history/diff/docs | `repo_query` | synthesize changes chronologically |
| G04 | `can you make the change?` after a concrete code/doc correction is established | preflight, preview, apply only the established change | `run_query.preflight`, `repo_preview`, `repo_apply` | brief intent before mutation, coherent result after |
| G05 | `run the focused tests` | execute validation only, no unrelated edit | `run_start` | state which validation is running, summarize outcome |
| G06 | `check if the run is still active` | read durable status/control; never relaunch | `run_query` | distinguish query success from run outcome |
| G07 | `stop` while a known durable run is active | cancel exact known run | `cancel_run` | no broad process kill, report exact cancellation result |
| G08 | `did you use Claude?` | inspect durable run evidence/history; do not invoke Claude | `run_query` | report provider/process evidence and route used |
| G09 | `update Soma project memory` | canonical memory workflow only | `knowledge_query` + `knowledge_action` | never substitute MEMORY.md/wiki/repo handoff |
| G10 | `refresh the repo wiki` | wiki refresh only | `knowledge_action.refresh_wiki` | do not mutate canonical memory unless separately requested |
| G11 | `is tunnel reachable?` | inspect authorized SSH/network/service evidence as appropriate | `ssh_inspect` / `ssh_query` / system evidence | read first, no restart/reconfigure |
| G12 | `check Docker health` | read Docker health | `docker_query` | no action gateway |
| G13 | `restart the container` with an exact authorized target | perform bounded Docker action | `docker_action` | acknowledge side effect and result |
| G14 | `check Cloudflare DNS` | inspect only | `cloudflare_query` | no write call |
| G15 | `change this DNS record` with complete authorized details | bounded mutation | `cloudflare_action` | surface confirmation/authority boundary |
| G16 | `what model are you?` | answer directly; Soma should not run | none | no tool call |
| G17 | `rewrite this paragraph` | rewrite directly | none | no Soma call |
| G18 | `what is VAT in the UK?` | web/general answer as appropriate, not Soma | none | no Soma call |
| G19 | `make a cocktail from these ingredients` | normal assistant answer, not Soma | none | no Soma call |
| G20 | `search the repo for X but don't change anything` | bounded repository search | `repo_query` | preserve read-only intent |
| G21 | `commit only these validated files` | selected local commit only | `repo_commit` | no push, preserve unrelated work |
| G22 | `push it` | outside current default authority unless explicitly allowed by a dedicated path/policy | no accidental substitute | state actual supported boundary rather than improvise |
| G23 | `continue` after an interrupted repository task with a known checkpoint | re-establish live state before acting | `repo_query` / `run_query` then appropriate action | do not trust stale chat state blindly |
| G24 | `what happened?` after a failed run | retrieve terminal/result/evidence | `run_query` | explain business failure vs tool/query success |

### Evaluation dimensions

For each prompt, record at minimum:

```text
expected tool/no-tool
selected gateway
selected operation/action
argument correctness
read/write class correctness
unnecessary call count
confirmation behavior
pre-action explanation present/absent
final coherent report present/absent
host card label/status observed
errors/retries
```

Primary routing metrics:

- tool-selection precision;
- tool-selection recall;
- operation-selection accuracy inside the chosen gateway;
- read/write boundary accuracy;
- unnecessary tool-call count.

Primary UX metrics:

- intent explained before a meaningful mutation;
- no narration spam between routine read calls;
- final answer summarizes result/evidence rather than ending on a tool card;
- visible invocation label is meaningful where the host supports it.

## 7. Bug and risk ledger — Iteration 2

### UX-001 — Missing human-readable tool titles

**Status:** reconfirmed live.  
All 32 titles are null.

### UX-002 — Missing OpenAI invocation-status metadata

**Status:** reconfirmed live.  
FastMCP can carry it through the existing flattening layer.

### IDENTITY-001 — No exact full-descriptor identity

**Class:** confirmed observability/activation gap.  
`public_schema_hash` is intentionally input-only. `discovery_cache_generation` is broader but build-derived and not an exact `tools/list` snapshot identity. Soma cannot name the exact live descriptor version that should be visible after a ChatGPT metadata refresh.

**Likely patch direction:** additive `public_descriptor_hash`; preserve existing field meanings.

### DOC-001 — Canonical memory audit falsely says description changes move `public_schema_hash`

**Class:** confirmed documentation defect.  
A live descriptor mutation left the hash unchanged exactly as the accepted implementation design predicts.

**Required correction before implementation planning uses that sentence:** description changes require refresh because ChatGPT caches metadata, not because `public_schema_hash` moves.

### ROUTE-001 — Gateway descriptions are implementation-centric

**Status:** strengthened with quantitative evidence.  
25/32 descriptions contain `gateway`; 0/32 start with the current OpenAI-recommended user-trigger shape.

### TEST-001 — No descriptor metadata regression contract

**Status:** reconfirmed.  
Current tests validate nonempty descriptions and annotations but do not pin titles, invocation labels, full-descriptor identity, or routing evals.

### PLUGIN-001 — Soma has no repo-owned Plugin/Skill package

**Class:** confirmed capability gap, not necessarily a bug.  
No `.codex-plugin/plugin.json`, `skills/`, `.app.json`, or `.mcp.json` package artifacts exist in the repository.

**Impact:** Soma has no repository-versioned workflow layer that can teach normal Chat the desired engineering interaction independently of generic tool descriptions.

### CACHE-001 — Activation evidence cannot independently prove ChatGPT's frozen descriptor snapshot

**Class:** confirmed external-observability boundary.  
Soma can publish its live descriptor identity and compare supplied expected identities, but it cannot read ChatGPT's private connection cache. A supported Refresh + readback/fresh-chat A/B test remains necessary.

Do not misclassify this as a server bug.

### DEP-001 — FastMCP remains unbounded

**Status:** unchanged confirmed risk.  
The metadata prototype now directly depends on behavior proven on 3.4.2, raising the value of a tested compatibility bound.

### UX-003 — Focused status/result UI

**Status:** still hypothesis; deferred.  
No evidence yet justifies UI in the first patch.

## 8. Research incidents

One malformed PowerShell introspection probe produced:

```text
python.exe: ScriptBlock should only be specified as a value of the Command parameter.
```

The problem was quoting in the research command. A corrected stdin-based probe succeeded. Because PowerShell itself returned a success process code for that malformed wrapper shape, this is recorded as a research incident, not promoted to a Soma defect without a separate execution-semantics investigation.

No product file or runtime configuration was changed by any disposable probe.

## 9. What Iteration 2 rules out

1. Do not replace `FlatGatewayTool` **solely because title/meta support is needed**; it already preserves them. This is a capability finding, not a preference for retaining the layer. Replacement remains in scope if comparative research demonstrates a more efficient, maintainable, lower-context, better-routed, or more future-compatible modern architecture.
2. Do not redefine `public_schema_hash`; its accepted input-contract meaning is useful and tested.
3. Do not claim metadata alone can force ChatGPT to restore old card chrome; the host still owns rendering.
4. Do not add a widget to every Soma tool.
5. Do not restore the retired Codex/Claude execution route to solve normal-Chat presentation.
6. Do not rely on a Skill as an authorization layer.
7. Do not assume a repository-owned Skill will load on the owner's exact web surface until installation/activation is verified.
8. Do not judge metadata by prose taste; use the frozen prompt corpus and fresh-chat A/B runs.

## 10. Provisional patch layers after Iteration 2

The research now supports a likely sequence, still pending further research and owner approval:

### Layer 1 — Descriptor foundation

- central metadata authority for all public tools;
- non-null human titles;
- concise invoking/invoked labels;
- user-goal descriptions tuned against the golden corpus;
- deterministic descriptor tests;
- additive exact `public_descriptor_hash`.

### Layer 2 — Activation/convergence evidence

- preserve `public_schema_hash` semantics;
- expose descriptor identity through capability discovery/identity;
- document server restart + ChatGPT Refresh + fresh-chat verification for descriptor changes;
- correct stale docs that equate description edits with input-schema-hash movement.

### Layer 3 — Workflow guidance

- prototype a repo-owned focused Skill for normal engineering interaction;
- keep it lean: explain meaningful intent, use Soma as the live authority, validate requested mutations, report coherently;
- verify the owner's actual ChatGPT web surface can install/use it before making it required.

### Layer 4 — Optional UI only after A/B evidence

- at most one focused engineering status/result surface initially;
- no UI on routine internal reads;
- preserve plain structured/text MCP results for non-ChatGPT consumers.

### Layer 5 — Dependency reproducibility

- establish a tested FastMCP compatibility range or lock strategy after checking installation/update workflow;
- avoid an arbitrary exact pin without upgrade policy.

## 11. Iteration 3 research targets

Before writing the final implementation plan, investigate:

1. **Descriptor registry shape:** how to centralize metadata across 32 tools, including the dynamically registered knowledge gateways, without duplicating decorator configuration or breaking inventory tests.
2. **Descriptor hash normalization:** whether to hash the exact served descriptor verbatim or normalize SDK-owned `meta.fastmcp` fields; test behavior across a clean FastMCP process and current registration paths.
3. **Plugin/Skill feasibility on the owner's actual ChatGPT web setup:** distinguish generic documented support from this account's installable surfaces without changing the live connection yet.
4. **Current connection identity:** document the existing Soma endpoint/registration and what can be read back before any refresh, without refreshing it.
5. **Metadata candidate copy:** draft titles, invoking/invoked labels, and concise routing descriptions for the highest-value engineering gateways first, then score them against G01-G24 before touching runtime code.
6. **Tool-count/context cost:** estimate descriptor-token change so the patch does not improve labels while bloating every normal-chat turn.
7. **Skill boundary:** decide whether one focused `soma-engineering` Skill is sufficient or whether memory/infrastructure need separate triggers; prefer the smallest workflow set that passes the corpus.
8. **UI hold gate:** define evidence that would justify a status/result component after metadata/Skill A/B, rather than assuming UI is necessary.
9. **Activation test design:** exact before/after evidence required from source, local MCP discovery, public tunnel, refreshed ChatGPT connection, and a fresh conversation.

## 12. Iteration 2 verdict

The strongest correction from this iteration is conceptual:

> Soma does not have one public contract snapshot. In the current Plugin-era integration it has at least a callable input contract and an MCP descriptor snapshot, and a future packaged Skill introduces a third plugin/workflow snapshot.

The existing input-schema identity is correct for its original job. The missing piece is an additive descriptor identity plus routing/UX metadata and measured activation.

Iteration 2 proves that a compatibility patch around the existing 32 consolidated gateways is technically viable, but **viability and lower migration effort do not make it the preferred solution**. The flattening layer, gateway consolidation, and transport serialization remain valid baseline candidates because no Iteration-2 evidence invalidates them; they are not protected from replacement. Iteration 3 and later comparisons must evaluate modern Plugin-era alternatives on measured end-to-end routing quality, tool-call/context efficiency, latency, UX, safety clarity, maintainability, multi-client compatibility, and future platform fit. If a modern route wins that comparison materially, the plan should choose it even when implementation and migration work are larger. UI remains deferred until evidence establishes whether it contributes to that optimum.

**Owner optimization rule:** minimize total system cost and maximize the quality of the resulting architecture, not merely the amount of code changed. Existing support is a useful baseline and migration-cost input; proven superior modern architecture outranks convenience.
