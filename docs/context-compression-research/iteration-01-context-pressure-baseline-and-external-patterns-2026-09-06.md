# Context-Efficient Chat Projection Research — Iteration 01

Date: 2026-09-06
Status: research iteration complete; architecture not frozen
Programme continuation: `cont_20260905T204910Z_07a66dcb7a07`

## Research objective

Establish a measured baseline for context pressure in Soma-heavy ChatGPT workflows and identify externally supported architecture patterns that could reduce active model-context load without reducing reasoning-relevant information or exact scientific/evidence availability.

This is the first iteration of a multi-iteration programme. It does not authorize implementation and does not select a final architecture.

## Owner requirement

The target is not lower context at any cost. Existing project context limits are already performance-sensitive. The desired system should reduce representational redundancy while preserving the information needed for high-quality reasoning. Exact evidence must remain recoverable.

## Method

1. Reopened current Soma `AGENTS.md` and the current `arash-research` Skill.
2. Reopened prior authoritative Soma normal-Chat tool-UX research rather than rediscovering it from memory.
3. Measured the current live FastMCP descriptor catalog mechanically.
4. Measured three real host dynamic-discovery sets observed in this Chat.
5. Reviewed current external evidence from OpenAI, MCP, Anthropic, and long-context research.
6. Separated source-supported facts from architecture inference.

Soma's project Research Map is currently `not_adopted`, so no Research Map sidecar or sync is applicable to this iteration.

## Local evidence

### L1 — Normal Chat already uses host-side deferred tool discovery

Prior Soma research, `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_3_2026-08-12.md`, directly observed that normal Chat initially receives lightweight connector information and loads selected Soma function schemas on demand through the host discovery layer.

That prior research explicitly warned that the entire MCP `tools/list` catalog must not be equated with model-context usage on every turn. This remains an important constraint on interpretation.

### L2 — Current full live Soma descriptor catalog is 184,476 JSON bytes

Read-only live measurement:

- Run: `20260905T205155Z_executable_profile_9fb5b42e`
- Public tools: 40
- Serialized descriptor bytes: 184,476
- Crude 4-character magnitude estimate: ~46,119 tokens
- No exact tokenizer count was claimed because `tiktoken` is not installed in the Soma environment.

Largest current descriptors measured:

| Tool | Descriptor bytes | Input-schema bytes |
|---|---:|---:|
| `knowledge_action` | 26,664 | 16,498 |
| `trading_query` | 14,125 | 13,311 |
| `company_action` | 11,492 | 10,715 |
| `knowledge_query` | 9,079 | 8,312 |
| `task_action` | 8,187 | 7,403 |
| `ssh_action` | 7,095 | 6,174 |
| `repo_query` | 6,717 | 5,855 |
| `run_start` | 6,530 | 5,439 |
| `run_query` | 6,111 | 5,351 |
| `docker_action` | 5,936 | 5,078 |

The older 2026-08-12 measurement was 139,149 bytes across 32 tools, so the raw catalog has grown materially. This does not by itself prove proportional active-context growth because host-side discovery is deferred.

### L3 — Real deferred-discovery sets are still large

This Chat directly observed host discovery calls where the query string matched not only the requested tool name but also neighboring tool descriptions that mention that name. The selected tools and their exact live descriptor sets were mechanically serialized.

Read-only measurement:

- Run: `20260905T205231Z_executable_profile_5ac25bd8`

| Observed discovery query | Tools loaded | Descriptor bytes | Crude 4-char magnitude |
|---|---:|---:|---:|
| `run_start` | 15 | 60,689 | ~15,172 tokens |
| `skill_query` | 18 | 85,889 | ~21,472 tokens |
| `continuation_action` | 17 | 107,887 | ~26,972 tokens |

This is a first-class context-pressure candidate. It also exposes a possible trade-off: explicit cross-tool routing prose improves tool selection but can broaden host discovery because literal tool names appear in multiple descriptions.

The unresolved question is whether and how the host deduplicates, caches, or retains these dynamically loaded definitions in the active model context across subsequent turns. No architecture decision should assume the answer.

### L4 — Schema weight dominates prose weight

Both the 2026-08-12 research and the current live measurements show that discriminated-union input schemas dominate descriptor size. Shortening ordinary descriptions alone therefore cannot deliver the major reduction target.

### L5 — Current freeze evidence does not point to Soma execution failure

Recent AVA and NSDN freeze investigations established two distinct cases:

- a long-held tool call can outlive ChatGPT stream recovery while Soma's durable job continues normally;
- NSDN also reproduced a freeze with only short Soma operations, HTTP 200 MCP responses, healthy Soma state, no OS-level ChatGPT crash, and slow ChatGPT-global MCP/plugin status scans after app re-entry.

The user additionally reproduced the problem in fresh chats after continuation re-entry and after Windows app reset/repair and `--no-gpu` launch. Therefore this programme must consider active controller-context pressure rather than treating cache, GPU rendering, old-thread age, or one slow Soma operation as the sole cause.

## External evidence

### E1 — OpenAI compaction preserves carry-forward state in a smaller active context

OpenAI's current Responses API compaction documentation describes server-side and standalone compaction. A compacted response can contain an opaque encrypted compaction item that carries forward key prior state/reasoning using fewer tokens. The compacted output becomes the canonical next context window.

Sources:
- OpenAI, "Compaction" guide: https://developers.openai.com/api/docs/guides/compaction
- OpenAI, "Unrolling the Codex agent loop": https://openai.com/index/unrolling-the-codex-agent-loop/

Implication: production OpenAI agents already treat active-context representation as replaceable while preserving sufficient carry-forward state. This is semantic compaction, not mathematical byte-lossless compression.

### E2 — Large tool catalogs can consume substantial prompt/context budget

OpenAI's GPT-5.4/tool-search guidance states that placing every tool definition in the prompt can add thousands to tens of thousands of tokens and crowd out useful context. Tool search/deferred loading is the documented mitigation. OpenAI reports a 47% total-token reduction at the same accuracy on a 250-task MCP Atlas evaluation using tool-search configuration across 36 MCP servers.

Sources:
- OpenAI, GPT-5.4 announcement/tool search: https://openai.com/index/introducing-gpt-5-4/
- OpenAI model/tool guidance: https://developers.openai.com/api/docs/guides/latest-model

Implication: Soma's descriptor/discovery footprint is not peripheral; it belongs in the core context-efficiency model.

### E3 — Prompt caching is not context compression

OpenAI prompt caching reuses matching prefixes to reduce latency and cost. It does not remove those tokens from the logical context window. It is complementary to, not a substitute for, context compression.

Source:
- OpenAI, "Prompt caching": https://developers.openai.com/api/docs/guides/prompt-caching

### E4 — MCP supports reference-style evidence delivery

The MCP tool-result contract supports embedded resources and `resource_link` results. A resource link can identify additional context/data by URI instead of embedding the entire resource inline in the immediate tool result.

Source:
- Model Context Protocol, Tools specification: https://modelcontextprotocol.io/specification/2026-07-28/server/tools

Implication: an exact-evidence-outside-active-context architecture is protocol-compatible in principle. ChatGPT's actual handling of resource links must be tested before relying on this mechanism.

### E5 — Context editing/tool-result clearing is an established agent pattern

Anthropic's current context-editing architecture can clear older tool results from active context while retaining the original unmodified conversation externally. Their documentation explicitly warns that this is less suitable when precise early-context recall is required.

Sources:
- Anthropic, "Context editing": https://platform.claude.com/docs/en/build-with-claude/context-editing
- Anthropic, "Effective context engineering for AI agents": https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

Implication: tool-result offloading is a credible pattern, but authoritative research/evidence needs stronger reopen/reference guarantees than ordinary conversational context.

### E6 — Large windows still suffer retrieval/degradation effects

OpenAI's published GPT-5.4 long-context metrics decline substantially at larger context ranges on several tasks, and the peer-reviewed "Lost in the Middle" work shows that retrieval quality can depend strongly on relevant-information position.

Sources:
- OpenAI GPT-5.4 long-context evaluation: https://openai.com/index/introducing-gpt-5-4/
- Liu et al., "Lost in the Middle: How Language Models Use Long Contexts", TACL 2024: https://aclanthology.org/2024.tacl-1.9/

Implication: context reduction can potentially improve reasoning quality if it raises relevant-information density; simply having a larger nominal context window is not sufficient.

### E7 — Learned semantic prompt compression exists but is not safe enough as the default authority path

LongLLMLingua reports prompt compression benefits, but it is a learned semantic compression method. That class of method may omit details and therefore does not meet the default requirement for exact scientific evidence preservation.

Source:
- Jiang et al., "LongLLMLingua: Accelerating and Enhancing LLMs in Long Context Scenarios via Prompt Compression", ACL 2024: https://aclanthology.org/2024.acl-long.91/

## First architecture model: three context planes

The evidence supports separating three materially different sources of context pressure.

### Plane A — Tool-definition context

Contains public tool names, descriptions, annotations, and input/output schemas loaded through discovery.

Characteristics:
- no scientific evidence is stored here;
- current dynamic-discovery sets can still be very large;
- high potential for safe representation reduction;
- routing and safety semantics must not be weakened.

### Plane B — Active working-state context

Contains the current continuation boundary, current task/run state, repository identity, decisions, constraints, IDs, and recently changed facts.

Characteristics:
- exact canonical state already exists durably in Soma for many fields;
- repeated full projections can create redundancy;
- delta or reference-backed projections may be possible;
- state identity/versioning is required to avoid stale-delta ambiguity.

### Plane C — Exact evidence payloads

Contains source Markdown, repo excerpts, test output, run artifacts, research evidence, diffs, and other source material.

Characteristics:
- exactness can matter scientifically and operationally;
- canonical copies can remain in repository/Soma durable evidence;
- default inlining of large evidence may be replaceable with compact manifests/references plus exact reopen-on-demand;
- semantic summaries must not silently become authority.

A fourth plane exists outside direct Soma control: ChatGPT's accumulated natural-language/reasoning history and platform compaction policy.

## Working definition of "lossless"

For this programme, "lossless" must not mean that every original evidence byte remains resident in the active model prompt. That would defeat compression.

A candidate mechanism is evidence-lossless only if:

1. the exact authoritative source remains unchanged and durably addressable;
2. the compact active representation preserves enough identity/provenance to reopen the exact source deterministically;
3. material conclusions are not allowed to rely on a lossy summary when exact evidence is required;
4. stale/mismatched references fail visibly rather than silently resolving to different evidence;
5. a full-fidelity path remains available.

Semantic summaries can be useful navigation aids but are not, by themselves, evidence-lossless.

## Adversarial alternatives considered

### A1 — "Only compress old tool outputs"

Rejected as an incomplete model for now. Current measurements show tool-definition discovery alone can introduce 60–108 KB in one observed discovery set.

### A2 — "Just shorten tool descriptions"

Insufficient. Input schemas dominate descriptor weight. Descriptions also encode routing/safety behavior and aggressive shortening could worsen tool selection.

### A3 — "Prompt caching solves it"

Rejected as the primary solution. Caching reduces repeated compute/cost/latency but does not reduce logical context occupancy.

### A4 — "Use a learned semantic compressor on everything"

Unsafe as the default. It would create a new semantic transformation layer between authoritative research/evidence and the reasoning controller and can lose detail.

### A5 — "Reduce the amount of research/project context supplied"

Contrary to the owner requirement and potentially harmful to performance. The programme targets representation cost and redundancy instead.

## Current hypotheses — not accepted architecture

H1. The safest high-value reduction may begin in Plane A because tool schemas are large and contain no project evidence.

H2. Soma can likely reduce Plane B redundancy through state-versioned delta/reference projections without becoming a semantic planner.

H3. Plane C should prefer exact evidence references/manifests with deterministic reopen rather than semantic compression, where the ChatGPT/MCP client path supports it reliably.

H4. Cross-tool literal names in routing descriptions may be causing discovery-set fan-out. Removing them could reduce schema load but may harm routing quality; this requires controlled A/B evidence before any change.

H5. A final architecture will likely need to be compaction-friendly across all three planes rather than rely on one compression mechanism.

## Required next evidence

Iteration 02 should focus on the host/model boundary:

1. Determine whether dynamically discovered tool schemas persist or are deduplicated in active ChatGPT model context across turns.
2. Search desktop/app telemetry for usable input-token/context metrics during continuation-heavy turns.
3. Mechanically estimate discovery fan-out for the full Soma catalog and identify which literal cross-references cause the largest sets.
4. Compare actual dynamic-discovery payload against tool-result payload during a representative continuation-heavy workflow.
5. Research OpenAI tool-search/deferred-loading contracts for namespaces or mechanisms that could preserve routing while narrowing schema loading.
6. Define an A/B experiment that measures context cost and reasoning quality, not merely serialized wire bytes.

Only after that should the programme begin selecting candidate architectures.
