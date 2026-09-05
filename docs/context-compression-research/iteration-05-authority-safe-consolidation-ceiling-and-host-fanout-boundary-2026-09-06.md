# Context Compression Research — Iteration 05

## Authority-safe consolidation ceiling and host-fanout boundary

Date: 2026-09-06
Status: completed research iteration; architecture remains open
Repository: Soma

## Purpose

Iteration 05 tests how far Soma can safely reduce MCP tool-definition pressure while preserving the architecture constraints established by Iterations 01–04 and by the prior ChatGPT MCP transport regression.

This iteration is research-only. It does not change the running Soma server, the ChatGPT app registration, the public tool catalog, the MCP endpoint, the stateless transport configuration, or any public schema.

## Hard inherited constraints

The accepted research perimeter is:

- one ChatGPT app;
- one Streamable HTTP `/mcp` endpoint;
- one canonical Soma backend;
- stateless HTTP compatibility must remain intact;
- no dependence on ChatGPT preserving `Mcp-Session-Id` across batches;
- no generic read/write dispatcher that hides materially different permission classes;
- exact evidence must remain reopenable;
- Soma remains mechanical and does not become a semantic router;
- the live connector is a protected control until an evidence-backed design justifies a change.

## Questions

1. How are the current 40 public tools partitioned by their actual MCP safety annotations?
2. Which tools can truthfully share a public query namespace without collapsing safety or authority boundaries?
3. How much descriptor size can safe consolidation remove before relying on undocumented ChatGPT host behavior?
4. Is a nested `request` namespace acceptable, or would it reintroduce a previously corrected MCP ergonomics problem?
5. Is the large discovery fan-out explained by Soma description text, or does the ChatGPT host have additional linkage/grouping behavior?
6. Does Plane A still have enough deterministic headroom to justify a risky public-surface experiment?

## Evidence method

All measurements were performed against the current Soma source/runtime without changing the running public surface.

The local catalog probe explicitly called `register_knowledge_tools(mcp)` before `mcp.list_tools()` so the measured catalog matched the 40-tool public surface rather than the 38-tool eager-registration subset.

Descriptor sizes are compact UTF-8 JSON byte counts. They are transport/schema measurements, not exact model-token counts.

An attempt to obtain an `o200k_base` token estimate found that `tiktoken` is not installed in the Soma venv. No package was installed for this research, so no exact tokenizer claim is made.

## Finding 1 — actual 40-tool MCP annotation classes

The complete local public catalog measured:

- tool count: **40**;
- serialized descriptor bytes: **184,516** in this probe.

The exact MCP annotation partitions were:

### Read-only, non-destructive, idempotent, open-world

- `ssh_inspect`
- `cloudflare_query`

Annotation tuple:

`(readOnly=True, destructive=False, idempotent=True, openWorld=True)`

These two tools do not share the same external authority domain, so equal annotations alone are not sufficient reason to merge them.

### Read-only, non-destructive, idempotent, closed-world

- `docker_query`
- `task_query`
- `skill_query`
- `continuation_query`
- `company_query`
- `workflow_query`
- `run_query`
- `system_query`
- `supervisor_query`
- `trading_signal_get`
- `trading_signal_list`
- `research_map_query`
- `repo_query`

Annotation tuple:

`(True, False, True, False)`

This is the only large safety-equivalent class, but it still spans materially different authority domains: local project state, Docker infrastructure, Company, and Trading. Therefore it must be subdivided by authority before any consolidation is considered.

### Mutating/destructive/open-world

- `docker_action`
- `cloudflare_action`
- `ssh_action`
- `run_start`
- `task_action`
- `workflow_action`
- `supervisor_action`
- `trading_companion_action`
- `trading_action_submit`
- `trading_runtime_control`

Annotation tuple:

`(False, True, False, True)`

This class contains distinct machine, infrastructure, lifecycle and trading authorities. No cross-domain consolidation is justified by the annotations.

### Non-read-only, non-destructive, non-idempotent, open-world

- `ssh_query`
- `company_action`
- `trading_query`

Annotation tuple:

`(False, False, False, True)`

The important evidence here is that names ending in `_query` are not automatically read-only. Soma's own public annotations correctly prevent treating `ssh_query` and `trading_query` as ordinary closed-world query tools.

### Remaining distinct classes

`skill_action`:

`(False, True, True, False)`

`continuation_action`:

`(False, False, True, False)`

`cancel_run`, `trading_signal_cancel_before_entry`, `repo_apply`, `knowledge_action`:

`(False, True, False, False)`

`system_action`, `trading_signal_submit`, `research_map_action`, `repo_preview`, `repo_commit`, `knowledge_query`:

`(False, False, False, False)`

The last group is particularly important: `knowledge_query` and `repo_preview` are not truthfully equivalent to ordinary pure reads even though their names can sound read-oriented. The existing annotation contract therefore provides a useful guard against over-consolidation.

## Finding 2 — conservative authority classes

For this iteration, safe consolidation candidates were limited to tools that satisfy both:

1. identical MCP safety annotations; and
2. a defensible shared authority class.

The conservative local-project/control-plane read class used for synthesis was:

- `continuation_query`
- `repo_query`
- `research_map_query`
- `skill_query`
- `run_query`
- `system_query`
- `task_query`
- `workflow_query`
- `supervisor_query`

These are all read-only, non-destructive, idempotent and closed-world. They read local Soma/project/control-plane state and do not cross into Docker, Company, Trading, SSH or Cloudflare authority.

A second small candidate family was:

- `trading_signal_get`
- `trading_signal_list`

They share the same safety annotations and the same narrow Trading signal-record authority.

The following were deliberately excluded from consolidation despite sometimes sharing annotations:

- `docker_query` — infrastructure authority;
- `company_query` — Company authority;
- `ssh_inspect` / `cloudflare_query` — different external authorities;
- `knowledge_query` — not advertised read-only;
- all write/action surfaces — distinct confirmation, destructive, idempotency or authority semantics.

## Finding 3 — static catalog consolidation ceiling is small

Three synthetic catalogs were generated entirely in memory. Every consolidated namespace retained each member's exact existing input schema under a typed `surface` branch. No handler or runtime path was changed.

Baseline:

- **40 tools**
- **184,516 bytes**

### Candidate B — six-tool hot project read namespace

Members:

- `continuation_query`
- `repo_query`
- `research_map_query`
- `skill_query`
- `run_query`
- `system_query`

Synthetic catalog:

- 35 tools
- 181,133 bytes
- savings: **3,383 bytes / 1.8% of full catalog**

The six original descriptors occupied 25,692 bytes; the nested synthetic `project_query` occupied 22,309 bytes.

### Candidate C — nine-tool local project/control-plane read namespace

Adds:

- `task_query`
- `workflow_query`
- `supervisor_query`

Synthetic catalog:

- 32 tools
- 179,585 bytes
- savings: **4,931 bytes / 2.7% of full catalog**

The nine original descriptors occupied 34,354 bytes; the nested synthetic namespace occupied 29,423 bytes.

### Candidate D — Candidate C plus Trading signal read namespace

Also consolidates `trading_signal_get` + `trading_signal_list`.

Synthetic catalog:

- 31 tools
- 178,988 bytes
- savings: **5,528 bytes / 3.0% of full catalog**

Therefore even the most aggressive consolidation accepted by this iteration's authority rules removes only about three percent of the complete descriptor catalog *statically*.

This is not enough by itself to explain or solve the observed freeze phenotype.

## Finding 4 — nested `request` is the wrong ergonomic shape

Iteration 04's first synthetic `project_query` used:

```text
project_query(
    surface = "repo",
    request = { ... exact repo_query request ... }
)
```

Reopening `soma/mcp_flat_input.py` showed that this quietly reintroduced a previously corrected public-contract problem.

`FlatGatewayTool` exists specifically because public gateways originally advertised a mandatory outer `request` object. Soma deliberately hoisted those arguments to the root while keeping the original Pydantic union as the sole runtime validator.

Therefore a new consolidated namespace should not casually restore the mandatory nested request envelope merely because it serializes smaller.

## Finding 5 — flat namespace is possible but saves even less statically

A second synthetic schema injected a required `surface` discriminator into each existing operation branch while preserving all operation arguments at the root.

Conceptually:

```text
project_query(
    surface = "repo",
    operation = "compact_status",
    repo_name = "soma"
)
```

The public synthetic schema remained valid JSON Schema 2020-12 in the offline check.

Results:

### hot6 flat namespace

- existing six descriptors: 25,692 bytes
- nested namespace: 22,236 bytes
- flat namespace: **24,830 bytes**
- flat savings versus existing: **862 bytes / 3.4% of the six-tool subset**

### local9 flat namespace

- existing nine descriptors: 34,354 bytes
- nested namespace: 29,347 bytes
- flat namespace: **32,583 bytes**
- flat savings versus existing: **1,771 bytes / 5.2% of the nine-tool subset**

Relative to the complete 184,516-byte catalog, those flat savings are well below the level needed to solve the problem on their own.

The flat form is semantically/ergonomically preferable to the nested form, but its value would still depend primarily on ChatGPT loading a much smaller discovery group for `project_query`.

## Finding 6 — description cross-references do not explain host fan-out

A literal scan of the actual Soma tool names/descriptions produced:

| Discovery string | Literal Soma descriptor matches | Literal descriptor bytes |
| --- | ---: | ---: |
| `continuation_query` | 1 | 2,554 |
| `knowledge_action` | 1 | 26,665 |
| `run_start` | 4 | 20,966 |
| `repo_preview` | 1 | 3,951 |
| `skill_query` | 1 | 2,603 |
| `quarantine` | 1 | 3,860 |

Earlier live ChatGPT discovery measurements observed:

- `continuation_query` → 18 tools;
- `knowledge_action` → 18 tools;
- `run_start` → 15 tools;
- `repo_preview` → 6 tools;
- `skill_query` → 18 tools.

In this iteration, querying the ChatGPT connector discovery layer for the unique descriptive term `quarantine` returned exactly one tool: `task_query`.

This creates a useful control:

- the host *can* expose a single narrow tool for a unique descriptive match;
- exact established tool names can trigger much broader related-tool expansion than their literal name/description occurrences justify.

Therefore broad fan-out is not reducible to Soma's visible description text alone. The ChatGPT host has additional tool-name/resource linkage or grouping behavior that is not represented in Soma's MCP descriptors.

The internal policy of that grouping remains unavailable to Soma.

## Finding 7 — the large Plane-A benefit remains host-dependent

The large potential reduction previously estimated for a consolidated `project_query` did not come from static schema compaction. It came from a conditional assumption:

> ChatGPT would treat the new namespace as one narrow discovery target instead of expanding it into the existing related-tool bundle.

Iteration 05 confirms that static safe consolidation alone saves only 1.8–3.0% of the total catalog, or 3.4–5.2% within the flat consolidated subsets.

Therefore the dominant proposed benefit cannot be proven offline.

Proving it requires changing the public app/tool snapshot and observing ChatGPT's host behavior after refresh/review.

That is precisely the boundary carrying elevated risk because of the previous OpenAI MCP transport/client regression and the still-required stateless operating model.

## Architecture implication

Plane A now has two sharply separated components:

### A1 — deterministic schema/descriptor compaction

Evidence-backed ceiling so far:

- strict identical-branch merging: useful but small;
- title/annotation trimming: negligible;
- safe tool-family consolidation: only a few percent of the full catalog statically;
- flat namespace is preferable to nested request but even less compact.

A1 is not large enough to justify immediate live-connector risk.

### A2 — ChatGPT host discovery fan-out

Potentially very large, but:

- controlled by the ChatGPT host;
- not explained by literal Soma descriptions;
- not directly observable through local FastMCP tests;
- cannot be validated for a hypothetical new tool name without changing the public app snapshot;
- any live test crosses the exact connector/refresh boundary we are protecting after the prior MCP bug.

A2 remains a research candidate, not an accepted implementation target.

## Decision for the research programme

**Do not implement Plane-A public-surface consolidation yet.**

This is not a rejection of `project_query`. The namespace remains the strongest single-endpoint Plane-A candidate if later evidence justifies a host-side A/B.

But current evidence does not support risking the stable ChatGPT/Soma connector merely to chase a benefit whose dominant component is host-dependent and undocumented.

The programme should now shift its next evidence pass to the parts Soma controls completely: active result projection and exact-evidence delivery.

## Next iteration — Plane B/C measurement

Iteration 06 should profile representative continuation-heavy workloads without changing the public schema:

1. continuation resume/status;
2. repeated run polling and terminal results;
3. repository status/search/read responses;
4. Research Map navigation responses;
5. exact source reads;
6. test/log output retrieval;
7. common public projection envelopes.

For each, measure:

- total bytes delivered to ChatGPT;
- unique bytes/facts versus repeated invariant metadata;
- repeated values across sequential calls;
- exact evidence already durable elsewhere;
- fields required for immediate reasoning;
- fields safe to replace with stable evidence references;
- whether a delta representation can be mechanically reconstructed;
- whether exact evidence can be reopened deterministically on demand.

The target is **evidence-lossless context reduction**, not semantic summarization.

No output projection should be changed until the research proves that the exact authoritative record remains addressable and that model-facing reductions do not remove information required for correct next-action reasoning.

## Current conclusion

Iteration 05 narrows the architecture space materially:

- multi-app partitioning remains disfavored because it increases MCP lifecycle surfaces;
- broad generic dispatch remains disfavored because it collapses permission semantics;
- safe single-endpoint tool consolidation is possible;
- flat consolidation avoids the old request-envelope regression;
- however deterministic Plane-A savings are only a few percent;
- the large theoretical Plane-A win depends on opaque ChatGPT discovery behavior and would require a risky public-snapshot experiment to prove;
- therefore Plane B/C is now the safer and higher-value research frontier.

Architecture status: **OPEN — not frozen**.
