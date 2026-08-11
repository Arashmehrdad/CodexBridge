# ChatGPT Normal Chat Tool UX Research - Iteration 5

Date: 2026-08-12  
Status: research-only candidate contract; not live  
Repository: `D:\Github\Soma`  
Branch: `lane/memory-integration-foundation-1`  
Source HEAD during research: `24fa7774d97e8a04bed3ec79054ae9b66182fd39`

## 1. Purpose

Iteration 5 converts the first four research passes into a reproducible candidate rather than another broad architecture survey.

This iteration had five concrete deliverables:

1. an exact proposed public MCP contract with selective tool splits, human titles, trigger-first descriptions, truthful annotations, and ChatGPT invocation labels;
2. a complete G01-G48 normal-chat corpus;
3. a small `soma-engineering` workflow Skill draft;
4. a FastMCP compatibility proof for the proposed metadata and typed subset-union approach;
5. an offline evaluator that builds the candidate from the current Soma schemas and measures its structure/descriptor footprint without changing the live MCP surface.

No production tool registration, server restart, connector refresh, plugin installation, runtime configuration change, canonical memory mutation, commit, or push was part of this iteration.

## 2. External contract pinned for this iteration

Current OpenAI Plugin/MCP guidance supports the design direction established in Iteration 4:

- tool metadata is part of routing/selection quality;
- descriptions should tell the model when to use the tool and distinguish nearby tools;
- read-only, destructive, idempotent, and open-world annotations should describe the actual effect of a call;
- invocation status labels are available through ChatGPT tool metadata;
- Skills are the workflow/sequencing layer around an MCP connection rather than a replacement for MCP authorization or execution;
- a Plugin can package Skills and MCP server connections together.

The resulting principle for Soma remains:

> Metadata and Skills can make normal ChatGPT interaction coherent, but Soma's MCP/server remains the authority for validation, authorization, idempotency, execution, and evidence.

## 3. FastMCP compatibility result

The Soma checkout is currently using FastMCP `3.4.2`.

An isolated registration probe confirmed that FastMCP 3.4.2 preserves all three metadata layers required by the candidate:

- `title`;
- MCP tool annotations;
- arbitrary tool `meta`, including:
  - `openai/toolInvocation/invoking`
  - `openai/toolInvocation/invoked`.

Therefore the metadata part of this proposal does **not** require a FastMCP fork or upgrade.

### 3.1 Typed subset-union proof

The more important compatibility question was whether a selective split could preserve Soma's current flat discriminated-union contract.

A standalone probe built:

```text
MemoryReadRequest =
    MemoryScopeQuery
  | MemorySearchQuery
  | MemoryGetQuery
  | MemoryHealthQuery
  | MemoryPacketGetQuery
```

under the existing `operation` discriminator, then passed it through:

```text
FlatGatewayTool.from_function(...)
flatten_request_input_schema(...)
```

Result:

- all five variants remained five schema branches;
- the public `request` wrapper remained flattened;
- the operation enum contained only the intended subset;
- title/description/annotations/meta survived;
- a flat invocation executed successfully.

Research evidence run:

```text
20260811T222020Z_executable_profile_a629febd
```

Conclusion: the viable implementation seam is **dedicated typed subset unions/wrappers using the existing `FlatGatewayTool` path**, not generic `ToolTransform`.

## 4. Important correction discovered during Iteration 5

Iteration 4 proposed splitting `trading_query` into two tools:

```text
local journal reads
live provider/market reads
```

That was incomplete.

Inspection of the installed `trading_lab` package showed that:

```python
companion_get(companion_run_id, sync=True)
```

does not merely read a row. With the default `sync=True`, it refreshes authoritative journal links for signal/action/outcome and then returns the updated record.

Therefore `companion_get` is a **stateful local query-shaped operation**.

The corrected C1 trading split is:

```text
trading_journal_query     pure local journal/report/status reads
trading_market_query      pure provider/MT5 reads
trading_companion_sync    stateful local companion sync/read
```

This changes C1 from the provisional 42-tool count to **43 tools**.

The correction is deliberately preserved rather than forcing the older prettier number.

## 5. Candidate B - same 32-tool topology, truthful conservative metadata

B remains the first live A/B candidate because it changes metadata/annotations without changing public tool count.

For broad mixed gateways, truthful annotations necessarily become conservative:

| Current broad gateway | readOnly | destructive | idempotent | openWorld | Why |
|---|---:|---:|---:|---:|---|
| `knowledge_query` | false | false | false | false | includes persisted memory/research context packets |
| `knowledge_action` | false | true | false | false | mixes ordinary writes with lifecycle/rebuild/consequential operations |
| `ssh_query` | false | false | false | true | mixes pure reads, local persisted preparation, and live external probes |
| `docker_action` | false | true | false | true | contains removal/prune/kill operations |
| `cloudflare_action` | false | true | false | true | contains delete/secret-rotation operations |
| `trading_query` | false | false | false | true | mixes local reads, stateful companion sync, and provider-backed reads |

B is useful precisely because it exposes the cost of keeping mixed semantics behind one descriptor. If normal ChatGPT begins over-confirming or framing harmless reads/writes too aggressively, that is evidence for C1 rather than a reason to lie in the annotations.

## 6. Candidate C1 - selective 43-tool contract

The exact contract is stored in:

```text
docs/chatgpt-tool-ux/candidate-contract-c1.json
```

Contract version:

```text
chatgpt-tool-ux.c1.v1
```

Every candidate tool has:

- source gateway;
- exact operation subset where split;
- human title;
- description beginning with `Use this when`;
- explicit nearby-tool exclusion where useful;
- `readOnlyHint`;
- `destructiveHint`;
- `idempotentHint`;
- `openWorldHint`;
- invoking label;
- invoked label.

All invocation labels satisfy the current 64-character host limit.

### 6.1 Knowledge/query split

`knowledge_query` becomes five public tools:

| C1 tool | Operations | R | D | I | O |
|---|---|---:|---:|---:|---:|
| `memory_query` | memory scope/search/get/health/packet get | T | F | T | F |
| `memory_context` | `memory_context` | F | F | F | F |
| `research_query` | source/evidence/list/health reads | T | F | T | F |
| `research_context` | research search/context packet build | F | F | F | F |
| `knowledge_query` | wiki + legacy/project knowledge reads | T | F | T | F |

The narrowed `knowledge_query` description explicitly states that it is **not** the canonical project-memory surface.

### 6.2 Knowledge/action split

`knowledge_action` becomes:

| C1 tool | Role | R | D | I | O |
|---|---|---:|---:|---:|---:|
| `memory_action` | canonical memory binding, write, lifecycle, drift, rebuild/sync | F | T | F | F |
| `knowledge_action` | wiki + legacy/research knowledge writes | F | T | F | F |

C1 intentionally keeps `memory_save` and consequential lifecycle actions together and therefore marks `memory_action` conservatively destructive. G47/G48 are retained specifically to measure whether a later memory-lifecycle split earns its added catalog cost.

### 6.3 SSH query split

| C1 tool | Role | R | D | I | O |
|---|---|---:|---:|---:|---:|
| `ssh_query` | capabilities/profile status/project bindings | T | F | T | F |
| `ssh_prepare` | credential probe/profile preview; persists local manifests | F | F | F | F |
| `ssh_probe` | fresh capability/binding validation; external probe + persisted snapshot | F | F | F | T |

`ssh_inspect` remains the live read-only external inspection surface.

### 6.4 Docker split

`docker_action` keeps the ordinary configured actions.

`docker_destructive_action` contains exactly:

```text
builder_prune
compose_down_volumes
compose_kill
compose_rm
container_kill
container_prune
container_remove
image_prune
image_remove
network_prune
network_remove
system_prune
system_prune_volumes
volume_prune
volume_remove
```

Ordinary Docker action:

```text
R=false D=false I=false O=true
```

Destructive Docker action:

```text
R=false D=true I=false O=true
```

### 6.5 Cloudflare split

`cloudflare_destructive_action` contains exactly:

```text
delete_dns_record
dns_delete
dns_batch
ruleset_delete
ruleset_rule_delete
turnstile_rotate_secret
turnstile_delete
tunnel_delete
tunnel_route_delete
```

`dns_batch` stays on the destructive side because one batch may contain deletion.
`turnstile_rotate_secret` stays on the destructive side because the old secret is invalidated.

All other current Cloudflare mutations remain in `cloudflare_action`.

### 6.6 Trading-query split

Pure local journal/report/status:

```text
trading_journal_query
```

Provider-backed market/account reads:

```text
trading_market_query
```

Stateful local sync/read:

```text
trading_companion_sync
```

This keeps a status-only request such as G45 away from `trading_runtime_control`.

### 6.7 Existing broad execution/lifecycle tools

C1 does not pretend that an outer descriptor can know the exact effect of arbitrary PowerShell, a workflow step, task execution, supervisor advancement, or broad trading action.

The following stay conservatively destructive where their reachable behavior can overwrite, terminate, delete, or otherwise cause hard-to-reverse work:

```text
run_start
cancel_run
repo_apply
ssh_action
workflow_action
task_action
supervisor_action
trading_signal_cancel_before_entry
trading_companion_action
trading_action_submit
trading_runtime_control
```

That conservatism is intentional. Live A/B confirmation behavior, not naming aesthetics, decides whether more splitting is justified.

## 7. G01-G48 corpus

The machine-readable corpus is stored in:

```text
docs/chatgpt-tool-ux/golden-corpus-g01-g48.json
```

It covers:

- repository read/preview/apply/commit;
- durable run launch/read/cancel/evidence;
- canonical project memory vs wiki/legacy knowledge;
- Docker ordinary vs destructive actions;
- Cloudflare read/update/delete;
- SSH local state, persisted preparation, external probes, and root shell;
- local Trading Lab reads, live MT5 reads, stateful companion sync, paper/demo actions, emergency close;
- explicit no-Soma cases;
- unsupported push behavior;
- interrupted-work recovery.

Each case records:

- expected C1 public tool;
- expected operation family;
- whether Soma should be used;
- expected open-world semantics;
- expected destructive semantics;
- whether the operation is stateful;
- rationale.

## 8. Offline evaluator

The evaluator is:

```text
scripts/research_chatgpt_tool_ux_eval.py
```

It is intentionally offline.

It does **not**:

- call OpenAI;
- restart Soma;
- refresh connectors;
- install a Plugin;
- mutate runtime configuration;
- execute the candidate contract as the live MCP surface.

It does:

1. register the current 32 FastMCP descriptors in-process;
2. read the C1 contract and G01-G48 corpus;
3. slice the six audited mixed source gateways;
4. prove every source operation is covered exactly once;
5. verify descriptor names are unique;
6. verify all descriptions begin `Use this when`;
7. verify invocation labels are within 64 characters;
8. verify known stateful surfaces are not marked read-only;
9. verify known destructive/open-world surfaces carry the corresponding hint;
10. verify all 48 golden cases are compatible with the proposed annotations;
11. build the actual candidate MCP descriptor JSON from the current schemas;
12. measure descriptor/input-schema bytes and a candidate descriptor SHA-256;
13. run a lexical-overlap diagnostic.

The lexical result is explicitly **not** a ChatGPT router simulation.

## 9. Measured result

Final evaluator run:

```text
20260811T225451Z_executable_profile_e5efeff1
```

All structural and golden-contract checks passed:

```text
failed_checks: []
golden_contract_check_count: 48
```

### 9.1 Descriptor footprint

Current 32-tool baseline:

```text
tool_count             32
descriptor_bytes       139,181
input_schema_bytes     112,720
```

Final C1:

```text
tool_count             43
descriptor_bytes       169,548
input_schema_bytes     118,718
descriptor_delta       +30,367 bytes
descriptor_delta       +21.8%
input_schema_delta     +5,998 bytes
```

Candidate descriptor identity:

```text
63e1ff6c3a3f85a83713f614720229757b8a82747708ffd3f1b1f8440ad400d7
```

This is a **research candidate descriptor hash**, not the live Soma public schema hash or capability identity.

The important comparison is with Iteration 4's more aggressive 46-tool split:

```text
46-tool prototype raw descriptor growth: +36.7%
43-tool C1 raw descriptor growth:        +21.8%
```

C1 therefore recovers most of the safety/intent separation while avoiding a large portion of the catalog duplication created by the maximal split.

### 9.2 Metadata wording diagnostic

The first C1 wording pass produced:

```text
expected tool in lexical top 5: 36 / 43 = 83.7%
```

The seven misses were vague natural-language prompts such as:

```text
check the audit document
did we repatch the route
make the correction
run the tests
is the tunnel reachable
change the DNS record
continue the interrupted task
```

Only five descriptions were tightened. No operation set or annotation changed.

Final lexical diagnostic:

```text
43 / 43 = 100%
```

Again, this is only evidence that the wording contains useful routing vocabulary. It is **not evidence that ChatGPT itself will achieve 100% routing accuracy**.

The live A/B test remains mandatory.

## 10. `soma-engineering` Skill draft

Research draft:

```text
docs/chatgpt-tool-ux/soma-engineering-skill-draft/SKILL.md
```

The Skill teaches:

- establish target and current state first;
- use managed repo preview/apply rather than hidden file mutation;
- do not silently commit or invent push support;
- use durable run evidence after execution;
- distinguish canonical project memory from wiki/controller-local/legacy memory;
- inspect infrastructure before mutating when current state matters;
- reserve destructive tools for deletion/removal/invalidation intent;
- separate local trading journal reads, live market reads, and stateful companion sync;
- report one coherent result instead of narrating every internal tool call;
- stop rather than guess when target/destructive scope/memory lineage is ambiguous.

The draft explicitly says it is **guidance, not enforcement**.

## 11. Plugin packaging target

Iteration 5 does not install or create a live Plugin.

The candidate packaging model is now concrete enough to test later:

```text
Soma Plugin
|
+-- .codex-plugin/plugin.json
+-- .app.json
+-- .mcp.json  -> existing Soma MCP connection
+-- skills/
    +-- soma-engineering/
        +-- SKILL.md
```

No custom UI is required for the first experiment. Normal ChatGPT conversation remains the target UX.

The Plugin becomes worthwhile only if the Skill measurably improves sequencing/explanation/final reporting over metadata alone.

## 12. Decision after Iteration 5

The research is now specific enough to stop architecture expansion.

Recommended live ladder remains:

### A - current

Current live Soma exactly as-is.

### B - metadata-only

Same 32 tool topology with:

- human titles;
- trigger-first descriptions;
- invocation labels;
- truthful conservative annotations;
- a measurable public descriptor identity.

### C1 - selective split

The exact 43-tool candidate in:

```text
docs/chatgpt-tool-ux/candidate-contract-c1.json
```

### D - workflow Skill

Best of B/C1 plus the `soma-engineering` Skill in a repo-owned Plugin package.

### E - focused modular MCP view

Only if A-D show that the broad catalog itself creates measurable normal-chat cost or routing degradation.

## 13. Live A/B acceptance gate

A candidate does not win because it is newer, smaller, or has fewer calls.

For G01-G48, record:

```text
selected public tool
selected operation
arguments
wrong/no-tool result
unnecessary api_tool calls
unnecessary Soma calls
confirmation shown
confirmation false positive
confirmation false negative
destructive action framing
external action framing
explain-before-mutation quality
final coherent report quality
visible title/status label behavior
latency
```

Hard failures include:

- destructive/external mutation without appropriate framing/confirmation behavior;
- routing a pure read to a mutation surface when the correct read surface exists;
- substituting wiki/legacy memory for canonical project memory;
- executing an unsupported push substitute;
- hiding state creation behind `readOnlyHint=true`;
- losing required operation coverage in a split;
- materially worsening routing/answer quality for the sake of lower call count.

## 14. What Iteration 5 proved

Iteration 5 materially strengthens the implementation case:

1. the required metadata is supported by the FastMCP version already used by Soma;
2. typed subset unions work with the existing flat gateway machinery;
3. the 43-tool split is mechanically complete for the six audited mixed gateways;
4. the trading split needed a third stateful surface, and that defect is now corrected;
5. the exact candidate passes all structural and G01-G48 annotation-contract checks;
6. C1 costs +21.8% raw descriptor bytes rather than the maximal split's +36.7%;
7. inexpensive description tuning materially improves a lexical routing diagnostic;
8. the Skill can now be tested as a distinct workflow variable rather than mixed into the MCP redesign.

## 15. Research boundary / current live state

Iteration 5 did **not** change the live Soma public contract.

At completion of this report:

```text
production source patch        no
public tool registration       unchanged
server restart                 no
connector refresh              no
plugin install                 no
runtime config change          no
canonical memory mutation      no
commit                         no
push                           no
```

The new files are research artifacts only.

The next research action should be to prepare the smallest reversible **B live A/B activation plan** first, because B can isolate the value/cost of truthful metadata without simultaneously changing the public tool topology. C1 should be activated only after B establishes a baseline for confirmation behavior and normal-chat routing.
