# Context-Efficient Chat Projection Research — Iteration 02

Date: 2026-09-06
Status: research iteration complete; architecture not frozen
Programme continuation: `cont_20260905T204910Z_07a66dcb7a07`
Parent iteration: `docs/context-compression-research/iteration-01-context-pressure-baseline-and-external-patterns-2026-09-06.md`

## Research objective

Resolve the most important host-boundary uncertainty left by Iteration 01: whether ChatGPT's deferred Soma tool discovery actually prevents schema accumulation during a continuation-heavy research response, and identify a native ChatGPT/MCP architecture candidate that could hard-bound that accumulation without moving Soma to the paid Responses API or weakening safety/authority semantics.

This iteration does not authorize implementation and does not select a final architecture.

## Owner constraints carried forward

1. Normal ChatGPT remains the reasoning/controller surface.
2. Soma remains the local durable authority for Runs, continuations, repository state, evidence, Research Map infrastructure, and related mechanical state.
3. No Responses-API migration is desired; API-side `defer_loading`/tool search is architecture reference evidence only.
4. Context reduction must not be achieved by dropping useful project/research information.
5. Exact evidence must remain deterministically reopenable.
6. Soma must not become a semantic router or second reasoning head.

## Method

1. Resumed the exact programme continuation and reopened Iteration 01.
2. Reused the current `arash-research` discipline and current Soma `AGENTS.md` already loaded in this Chat.
3. Queried current OpenAI ChatGPT plugin/app documentation and current MCP tool contracts.
4. Measured actual ChatGPT host `api_tool.list_resources` discovery groups for Soma.
5. Mechanically compared host-selected groups against literal Soma tool-name/description matching.
6. Tested whether a previously discovered tool remained callable after a later, different discovery bundle.
7. Measured cumulative unique descriptor bytes for a realistic research lifecycle.
8. Sized a hypothetical static multi-app partition without changing the running Soma service.
9. Considered adversarial alternatives and product/runtime counter-risks.

Soma's own project Research Map remains `not_adopted`; no sidecar or map sync applies.

## Local evidence

### L2-01 — No usable prompt/context-token telemetry is exposed by the current desktop logs

Read-only search of the current packaged ChatGPT desktop logs found no `input_tokens`, `prompt_tokens`, `context_window`, `cached_tokens`, or equivalent prompt-size counters that can be tied to the problematic continuation response.

Run: `20260905T205700Z_executable_profile_ca96d368`

Consequence: exact active model-token occupancy cannot currently be read from the desktop host. Architecture evaluation therefore needs observable proxy metrics plus live behavioral A/B rather than pretending byte counts are exact model-token counts.

### L2-02 — Iteration 01's literal-cross-reference explanation was falsified as sufficient

Iteration 01 hypothesized that explicit tool names in neighboring descriptions might explain most discovery fan-out.

A mechanical live scan showed that `run_start` occurs by exact tool-name/description matching in only four Soma descriptors, totaling about 20,962 descriptor bytes. Yet the actual ChatGPT host call `api_tool.list_resources(paths=["Soma"], query="run_start")` exposed 15 tools whose current live descriptors total about 60 KB.

Run for mechanical matching: `20260905T205714Z_executable_profile_c2a7d402`

Observed host discovery in this Chat:
- `run_start` -> 15 tools
- `knowledge_action` -> 18 tools
- `continuation_query` -> 18 tools
- `repo_commit` -> 5 tools

Therefore literal description references contribute at most part of the behavior. ChatGPT's connector host applies an additional grouping/expansion policy not described by Soma's MCP metadata.

This supersedes Iteration 01 hypothesis H4 as a sufficient causal explanation. Tool-description shortening must not be implemented as the primary fix without independent routing/context evidence.

### L2-03 — Discovered tool availability accumulates within one active response

Direct harness observation:

1. `continuation_query` discovery loaded an 18-tool Soma group.
2. A later `run_start` discovery loaded a different 15-tool group.
3. After the later discovery, `knowledge_query` — present in the earlier group but absent from the later `run_start` group — remained directly callable without another `api_tool.list_resources` discovery call.

The `knowledge_query(memory_scope)` call succeeded normally.

This proves at least one operational fact relevant to the freeze: in the same active assistant response, later discovery does not replace the earlier callable tool universe. The host retains earlier discovered capability sufficiently for subsequent calls.

This does **not** prove how OpenAI internally tokenizes or deduplicates schema definitions, and it does not prove cross-turn persistence. It does prove that a single long tool-heavy response can accumulate a broad callable universe, which is the failure shape we need to explain.

### L2-04 — Three normal discovery families expose 34/40 Soma tools

Read-only live measurement:

Run: `20260905T210534Z_executable_profile_caefa617`

Current measurement method serialized the exact live MCP descriptors for the tools that ChatGPT had exposed in the observed discovery groups.

| Discovery stage | Group tools | Group descriptor bytes | Newly exposed tools | Cumulative unique tools | Cumulative descriptor bytes |
|---|---:|---:|---:|---:|---:|
| `continuation_query` | 18 | 85,033 | 18 | 18 | 85,033 |
| `run_start` | 15 | 60,028 | 10 | 28 | 125,296 |
| `knowledge_action` | 18 | 116,174 | 6 | 34 | 173,155 |

Full live catalog under the same serialization method:
- 40 tools
- 182,756 descriptor bytes
- crude four-character magnitude: ~45,689 token-equivalents

The three observed discovery families therefore expose 34/40 tools and 173,155 bytes, or **94.7% of the full live descriptor catalog**.

The crude character/token ratio is only a magnitude indicator, not an OpenAI tokenizer measurement.

### L2-05 — Completing the normal research lifecycle reaches 35/40 and 95.8% of descriptor bytes

A completed Soma research iteration normally ends with a repository commit. ChatGPT host discovery for `repo_commit` returned five tools. Four were already present in the cumulative 34-tool union; `repo_commit` was the only new tool.

Exact current `repo_commit` descriptor size:
- 1,887 bytes
- crude four-character magnitude: ~472 tokens

Run: `20260905T210757Z_executable_profile_05ab7bd2`

Cumulative result:
- 35/40 tools
- 175,042 descriptor bytes
- **95.8% of the current full descriptor catalog by serialized bytes**

This is the central Iteration 02 finding.

ChatGPT's host-side deferred discovery is real, but for Soma's current single-app shape, a normal continuation -> execution -> knowledge/research -> commit workflow can operationally converge on almost the whole tool catalog inside one response.

### L2-06 — Current descriptor pressure is not evenly distributed across domains

A hypothetical static partition was sized without changing source or the live server.

Run: `20260905T210627Z_executable_profile_5f4ca65d`

| Candidate static surface | Tools | Descriptor bytes | Crude four-character magnitude |
|---|---:|---:|---:|
| Core (`system`, continuation) | 4 | 10,611 | ~2,653 |
| Repository | 4 | 15,812 | ~3,953 |
| Research/knowledge/skills | 6 | 48,160 | ~12,040 |
| Execution/task/workflow/supervisor | 9 | 34,488 | ~8,622 |
| Infrastructure (SSH/Docker/Cloudflare) | 6 | 26,651 | ~6,663 |
| Company | 2 | 16,445 | ~4,111 |
| Trading core | 4 | 22,875 | ~5,719 |
| Unassigned legacy/specialized signals | 5 | 7,714 | n/a |

The research/knowledge surface remains relatively heavy because `knowledge_action` and `knowledge_query` are large discriminated-union gateways. Prior authoritative Soma UX research already found that these gateways combine multiple distinct semantic systems (canonical memory, wiki, legacy knowledge, and research) and identified them as strong user-goal split candidates for reasons independent of context size.

This means app-level partitioning alone may not be the final Plane-A solution; operation/gateway projection may also matter.

## External evidence

### E2-01 — ChatGPT plugins can contain multiple apps

Current OpenAI plugin documentation states that a plugin can include multiple apps and skills. It explicitly describes plugins as workflow containers that can bring together several capabilities rather than forcing users to manually switch between unrelated products.

Source:
- OpenAI Help, "Plugins in ChatGPT and Codex": https://help.openai.com/en/articles/20001256/

Implication: one logical `Soma` plugin does not require one monolithic MCP app surface. Multiple narrow apps under one plugin are a first-class ChatGPT product concept.

### E2-02 — ChatGPT app selection is message-scoped and multiple apps can participate in one prompt

Current developer-mode documentation states:
- users may select one or more apps for a single message;
- multiple apps can be invoked in one prompt;
- app selection applies to the message, not the entire conversation;
- an app need not be reselected merely to discuss results already present in chat.

Source:
- OpenAI Help, "Developer mode and MCP apps in ChatGPT": https://help.openai.com/en/articles/12584461

Implication: static capability partitioning by app is architecturally compatible with ChatGPT's current interaction model. It is not yet proven to reduce model schema context because the host's cross-app discovery/loading behavior has not been A/B measured.

### E2-03 — ChatGPT custom apps are tool-scanned and action changes are not transparently dynamic

OpenAI's current custom-app workflow explicitly includes a `Scan Tools` step. Server updates are not automatically enabled; the user/admin must Refresh to obtain updated actions, new actions are disabled by default in relevant flows, and changes can be shown as diffs. Product behavior varies somewhat by plan/workspace.

Sources:
- OpenAI Help, "Developer mode and MCP apps in ChatGPT": https://help.openai.com/en/articles/12584461
- OpenAI Help, "Admin controls, security, and compliance for plugins and apps": https://help.openai.com/en/articles/11509118

Implication: relying on a single MCP server to continuously mutate its public `tools/list` according to hidden per-chat state is not a safe product-contract assumption. Static app surfaces are more compatible with ChatGPT's action-management model.

### E2-04 — Responses API deferred loading remains an API-only reference, not a ChatGPT app contract

The current Responses API exposes `defer_loading`, tool search, allowed tools, and related orchestration controls for application developers. Current OpenAI model guidance recommends tool search for large catalogs.

Sources:
- OpenAI API reference, Responses create: https://developers.openai.com/api/reference/cli/resources/responses/methods/create
- OpenAI model guidance: https://developers.openai.com/api/docs/guides/latest-model

No current ChatGPT custom-app/plugin documentation located in this iteration exposes an equivalent per-tool `defer_loading` or namespace knob to the MCP app developer.

Implication: do not design Soma around an undocumented ChatGPT equivalent of the API control.

### E2-05 — MCP itself leaves tool incorporation to the host and keeps tool identity explicit

The current MCP tools specification defines tools as named schema-bearing capabilities discovered through `tools/list`, with optional list-change notifications. It emphasizes explicit tool identity, schemas, annotations, human-visible invocation, and confirmation for sensitive operations.

Source:
- Model Context Protocol, Tools specification (2025-11-25): https://modelcontextprotocol.io/specification/2025-11-25/server/tools

Implication: static capability surfaces and explicit action identity align with the protocol. A hidden semantic router behind a generic catch-all tool would throw away some of the very information the protocol gives hosts for selection, safety, and UI.

### E2-06 — MCP resource links remain promising for Plane C, but host behavior is application-defined

MCP permits a tool result to return `resource_link` items rather than embedding the full resource. MCP resource documentation also states that applications decide how resources are incorporated into model context; the protocol does not mandate one inclusion policy.

Sources:
- MCP Tools: https://modelcontextprotocol.io/specification/2025-11-25/server/tools
- MCP Resources: https://modelcontextprotocol.io/specification/2025-06-18/server/resources

Implication: resource-link evidence offloading remains a viable later experiment, not an accepted lossless path until ChatGPT's actual retrieval/context behavior is tested.

## Candidate architecture A — Static multi-app capability projections over one Soma core

### Concept

Keep exactly one durable Soma backend and authority model, but expose several **static, narrow MCP app projections** under one logical Soma plugin.

Conceptual shape:

```text
                     ChatGPT / Soma plugin
                              |
          +-------------------+-------------------+
          |                   |                   |
      Soma Project        Soma Execute        Soma Infra ...
          |                   |                   |
          +-------------------+-------------------+
                              |
                    one canonical Soma core
            Runs / locks / continuation / repo / evidence
```

Each public app would contain only a bounded set of existing canonical capabilities. The app does not own state. It is a projection/transport surface over the same backend.

### Why this is mechanically attractive

1. It places a hard upper bound on what one app can advertise: the host cannot discover a tool that is not exposed by that app endpoint.
2. It preserves normal ChatGPT rather than moving to the Responses API.
3. It preserves MCP-native action identity, schemas, annotations, confirmation behavior, and admin controls.
4. It does not require Soma to semantically choose which tools matter; ChatGPT/plugin workflow remains the reasoning layer.
5. It can reuse the same handlers and canonical state instead of creating duplicate domain authority.

### Why it is not accepted yet

The crucial host behavior is unmeasured: when one logical plugin contains several apps, ChatGPT may still scan/load multiple app schemas together for a workflow. If it does, the expected context saving could collapse.

There is also a serious counter-risk from the freeze investigation: ChatGPT desktop `mcpServerStatus/list` scans already measured roughly 14.7 s median and 27.3 s worst-case during recent app startup/re-entry. More underlying apps could increase connection/status-management overhead even if schema context improves.

Therefore **number of app surfaces is itself an optimization variable**, not "more partitions is always better".

## Candidate architecture B — Static narrowed schema projections inside app surfaces

If app partitioning proves useful but one domain remains heavy, a second mechanical technique is possible:

- expose a narrower operation subset of an existing canonical gateway on a given app surface;
- route it to the same underlying handler/state authority;
- do not create a second implementation of the operation;
- preserve explicit operation/tool safety semantics.

The strongest current candidate is the research/knowledge family because prior Soma UX research independently found `knowledge_query`/`knowledge_action` semantically over-broad.

This is a schema/projection design, not semantic compression.

It is not accepted until the app-level A/B establishes that smaller public schemas translate into actual ChatGPT benefit.

## Adversarial alternatives

### A2-01 — One generic `soma_search` + `soma_call` meta-tool

This could make the public schema extremely small and imitate API-side tool search mechanically.

**Rejected as the default architecture candidate on safety/host-integration grounds.**

Reasons:
1. ChatGPT/app action controls and confirmations operate on exposed actions. A generic catch-all action would mix read, write, destructive, infrastructure, trading, and repository capabilities behind one descriptor.
2. MCP annotations are tool-descriptor level. Soma has already proven that mixed safety boundaries inside broad tools can misrepresent destructive behavior.
3. The model/host would lose the native per-action schema/description information it is trained to use for tool calling.
4. It would create a second routing protocol that ChatGPT must learn rather than using MCP as designed.
5. It risks recreating the forbidden hidden-router pattern, even if the router is nominally mechanical.

A future constrained meta-tool could still be researched for **read-only evidence retrieval only**, where safety/confirmation semantics are homogeneous. It is not a suitable universal Soma front door.

### A2-02 — Dynamically mutate `tools/list` per chat/recent action

Not selected.

ChatGPT's app-management contract scans and manages a known action set and does not automatically enable arbitrary server action changes. Dynamic tool-list behavior would also create cache/identity/debugging problems and could make tool availability depend on hidden connection state.

Static versioned surfaces are easier to audit, hash, refresh, and roll back.

### A2-03 — Split Soma into independent backends

Rejected. Context optimization does not justify duplicating Runs, locks, continuation, repository authority, Research Map infrastructure, or other canonical state.

Only public capability projections are candidates for partitioning.

### A2-04 — Split every operation into its own app/tool immediately

Rejected as premature. More apps/tools could worsen discovery/status latency and management overhead. The correct granularity must be measured.

## Updated context-pressure model

Iteration 02 refines Plane A into two subplanes:

### Plane A1 — App/plugin capability enrollment

Which MCP app surfaces are selected/available to ChatGPT for the current workflow.

### Plane A2 — Tool-schema discovery within an enrolled app

Which tools from an app the host actually exposes to the reasoning response and how those discovered schemas accumulate during a long response.

Current single-app Soma allows A2 to converge on almost the full 40-tool catalog during one ordinary research lifecycle.

Plane B (working state) and Plane C (exact evidence) remain as defined in Iteration 01.

## Current evidence-backed conclusions

1. **The heavy-response schema-accumulation mechanism is real enough to prioritize.** Within one active response, previously discovered tools remain callable, and a realistic Soma research lifecycle reaches 35/40 tools and ~95.8% of current descriptor bytes.
2. **Description cross-references are not the primary sufficient cause.** Host expansion is broader than exact name/description matching.
3. **Soma cannot currently control a documented ChatGPT equivalent of Responses API `defer_loading`.**
4. **ChatGPT's native plugin/app model gives us a legitimate partitioning primitive:** one plugin may contain multiple apps, with message-scoped app use.
5. **Static multi-app projections are the strongest current Plane-A candidate**, but they are not safe to adopt until host loading and startup/status overhead are measured.
6. **Generic universal meta-tools are currently disfavored** because they collapse action-level safety, approval, and schema semantics.
7. **The final architecture likely needs both coarse app partitioning and selective schema narrowing**, but the amount of each is still an empirical question.

## Required next evidence — Iteration 03

Iteration 03 should be a controlled ChatGPT A/B design and, if the owner approves the temporary test surface, a small live experiment.

### A/B topology

Control:
- current monolithic Soma app, unchanged.

Candidate:
- same Soma backend;
- one or two **read-only or otherwise low-risk shadow app surfaces** exposing a deliberately small static subset;
- no new canonical state or duplicate execution path;
- easy removal/rollback.

### Minimum measurements

1. ChatGPT app/plugin setup and `mcpServerStatus/list` latency with control vs candidate app count.
2. Number of host-exposed tool schemas for exact prompts/workflow phases.
3. Cumulative unique descriptor bytes during a continuation-heavy response.
4. First useful tool-call latency.
5. Correct-tool routing on a frozen prompt corpus.
6. Ability to cross app boundaries when a task genuinely requires two domains.
7. Confirmation/safety behavior for write-capable tools; no safety weakening accepted.
8. Stream-freeze/recovery behavior across repeated continuation-heavy runs.
9. Whether app selection can remain transparent through one logical Soma plugin or imposes manual user switching.

### Acceptance direction, not yet thresholds

A candidate should only advance if it materially reduces active schema exposure **without** degrading routing, scientific/evidence access, safety semantics, or normal workflow completion, and without creating unacceptable app-start/status latency.

## Programme status

Iteration 02 closes the host-discovery characterization stage sufficiently to justify an A/B partition experiment. It does **not** freeze the desired architecture. The continuation remains open.
