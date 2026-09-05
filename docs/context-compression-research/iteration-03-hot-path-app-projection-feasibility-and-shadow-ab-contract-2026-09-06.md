# Context-Efficient Chat Projection Research — Iteration 03

Date: 2026-09-06
Status: research iteration complete; architecture not frozen
Programme continuation: `cont_20260905T204910Z_07a66dcb7a07`

## Research objective

Determine whether ChatGPT-native app partitioning can materially reduce Soma tool-definition context without moving off normal ChatGPT, duplicating Soma authority, weakening action safety, or forcing impractical manual app switching. Establish the safest controlled A/B contract before any runtime change.

This iteration is research-only. It does not authorize a shadow endpoint, a new ChatGPT app, or a change to the current production Soma app.

## Inputs reopened

- Iteration 01: `docs/context-compression-research/iteration-01-context-pressure-baseline-and-external-patterns-2026-09-06.md`
- Iteration 02: `docs/context-compression-research/iteration-02-chatgpt-host-discovery-accumulation-and-native-partition-candidate-2026-09-06.md`
- Durable continuation: `cont_20260905T204910Z_07a66dcb7a07`

## Prior boundary

Iteration 02 established that a normal continuation-heavy research response can cause ChatGPT's host-side deferred discovery to expose 35 of 40 Soma tools, representing 175,042 descriptor bytes or 95.8% of the current full tool catalog. Literal cross-references in Soma descriptions do not explain the host fan-out by themselves.

Therefore Iteration 03 asks whether the correct control boundary is the ChatGPT app snapshot itself.

## External evidence — OpenAI ChatGPT app behavior

### E3-01 — App selection is message-scoped

OpenAI's current developer-mode/custom-MCP documentation states that a chat can select one or more apps for a single message, that app selection applies to the message where it is used rather than the entire conversation, and that an app can be mentioned again when a later message needs new data or another action.

Source:
- OpenAI Help Center, "Developer mode and MCP apps in ChatGPT", lines 90-101 as retrieved 2026-09-06: https://help.openai.com/en/articles/12584461-developer-mode-apps-and-full-mcp-connectors-in-chatgpt-beta

Consequence:
- app-level capability partitioning is a real ChatGPT-native control boundary;
- a narrow app does not have to remain globally selected for the entire conversation;
- however, selecting multiple apps in one message can still expose multiple capability sets during that message.

### E3-02 — A custom app receives a scanned/frozen tool snapshot

The same OpenAI documentation states that app setup scans the MCP server's tools and that, after approval, ChatGPT uses a frozen snapshot of the app's available tools and inputs. Later MCP changes are not automatically enabled; an admin refresh/review is required for changed actions.

Source:
- same OpenAI Help Center article, configuration lines 39-58 and FAQ lines 165-170.

Consequence:
- separate app projections can hold separate stable tool catalogs even if they are backed by the same canonical system;
- dynamic per-call hiding inside one already-scanned app is not a reliable context-control architecture because ChatGPT reasons from the approved snapshot;
- projection identity/versioning and refresh discipline would be mandatory.

### E3-03 — Multiple apps can be invoked together

OpenAI explicitly documents that multiple first-party and third-party apps can be invoked in one prompt.

Consequence:
- merely splitting Soma into many apps does not guarantee context savings;
- if a heavy workflow selects every Soma partition in one message, the combined schema load can recreate the current problem;
- the partition must be designed around actual workflow locality, not arbitrary subsystem ownership.

### E3-04 — App action controls and confirmation remain app/action scoped

OpenAI documents app-level action configuration and confirmation behavior for write/modify actions. Enterprise/Edu can enable or disable specific actions; ChatGPT may request confirmation based on permissions and action context.

Consequence:
- a universal `soma_search` / `soma_call` meta-tool remains a poor safety trade-off because it would collapse materially different actions behind one generic public contract;
- app partitioning can retain explicit action-level schemas and host controls.

### E3-05 — Plugin packaging can contain multiple apps

OpenAI's current Plugin documentation states that one plugin may include multiple apps and skills.

Source:
- OpenAI Help Center, "Plugins in ChatGPT and Codex": https://help.openai.com/en/articles/20001256

Consequence:
- multiple narrow Soma app projections do not necessarily require multiple unrelated user-facing products;
- one logical Soma plugin can, in principle, package several app-backed capability surfaces.

Important uncertainty:
- the documentation does not prove that invoking the containing plugin automatically selects only the minimum required underlying app at each sub-step of one model response. That host behavior must be measured rather than assumed.

## Local feasibility evidence — FastMCP

### L3-01 — Current FastMCP supports projection construction without a second durable backend

Read-only introspection run:
- `20260905T211632Z_executable_profile_e2e0155e`

The installed FastMCP constructor supports an explicit `tools: Sequence[Tool | Callable]` argument. It also exposes:
- `mount(...)`
- `as_proxy(...)`
- `http_app(...)`
- providers and transforms
- separate tool listing/calling through the same FastMCP machinery.

This means a shadow projection does not require cloning Soma's durable stores, workers, locks, Runs, continuation authority, or domain logic.

### L3-02 — FastMCP has native include/exclude transformation support

Read-only package inspection:
- `20260905T211821Z_executable_profile_7655a7d8`
- `20260905T211834Z_executable_profile_0ca705ee`

Installed FastMCP source contains transforming MCP server configuration with:
- `tools`
- `include_tags`
- `exclude_tags`

The configuration explicitly describes these as proxy/tool transformation controls.

Consequence:
- the safest prototype can be a static filtered projection over the existing canonical tool implementations;
- tool business logic does not need to be copied;
- canonical state remains owned by the current Soma backend.

## Candidate projection sizing

Read-only live sizing run:
- `20260905T211749Z_executable_profile_8f17bac7`

Current full catalog:
- 40 tools
- 182,756 descriptor bytes in this measurement

Candidate sets:

| Candidate | Tools | Descriptor bytes | % of full | Crude 4-char magnitude |
|---|---:|---:|---:|---:|
| `project_read_lean` | 6 | 25,428 | 13.9% | ~6,357 |
| `project_read_hot` | 7 | 34,464 | 18.9% | ~8,616 |
| `execution_min` | 3 | 13,549 | 7.4% | ~3,387 |
| `repo_write` | 3 | 9,138 | 5.0% | ~2,284 |
| `research_maintenance` | 3 | 32,136 | 17.6% | ~8,034 |
| `project_full_hot` | 15 | 83,219 | 45.5% | ~20,805 |

Exact members:

### `project_read_lean`
- `continuation_query`
- `repo_query`
- `research_map_query`
- `skill_query`
- `run_query`
- `system_query`

### `project_read_hot`
The lean set plus `knowledge_query`.

### `execution_min`
- `run_start`
- `run_query`
- `cancel_run`

### `repo_write`
- `repo_preview`
- `repo_apply`
- `repo_commit`

### `research_maintenance`
- `knowledge_action`
- `research_map_action`
- `continuation_action`

### `project_full_hot`
- `continuation_query`
- `continuation_action`
- `repo_query`
- `repo_preview`
- `repo_apply`
- `repo_commit`
- `research_map_query`
- `research_map_action`
- `skill_query`
- `run_start`
- `run_query`
- `cancel_run`
- `system_query`
- `knowledge_query`
- `knowledge_action`

The `project_full_hot` set excludes unrelated infrastructure, trading, Company, SSH, Docker, Cloudflare, workflow/supervisor/task surfaces that are not required in ordinary repo/research work.

## Architecture inference

### I3-01 — The strongest current candidate is not "many tiny apps"

A large number of tiny apps would minimize each individual schema set but creates three problems:

1. a heavy message could select several apps and reconstruct the union;
2. repeated manual app selection would damage workflow ergonomics;
3. additional apps may increase global app/MCP status-scan overhead, which is already slow in the desktop client.

Therefore the stronger candidate is:

```text
                  one canonical Soma backend
                           |
         +-----------------+------------------+
         |                                    |
  Soma Project app                    peripheral apps
  normal engineering                  infra / trading /
  and research hot path               company / special
         |
  ~15 public tools
```

This is a public-projection split, not an authority split.

### I3-02 — A single project hot-path app could cut Plane-A exposure substantially

The measured 15-tool project hot path is 83,219 descriptor bytes, 45.5% of the current full catalog and less than half of the 175,042 bytes accumulated during the Iteration-02 heavy research lifecycle.

This is only a structural byte estimate. It is not proof of an equal model-token reduction and not proof that the freeze disappears.

### I3-03 — A read-only shadow app is the safest first experiment

The 6-tool `project_read_lean` projection is 25,428 bytes, only 13.9% of the full catalog. It contains no write/action surfaces.

It is therefore the best first host A/B because:
- it cannot mutate repo or system state;
- it exercises continuation/re-entry, repository navigation, Research Map, Skill lookup, run inspection, and system health — the common first half of a project-resume workflow;
- it gives a large schema-size contrast against the current monolithic app;
- it can be discarded without changing the canonical Soma app.

### I3-04 — The second experiment should be one full project hot-path app, not several simultaneous micro-apps

If the read-only shadow proves that app-level partitioning changes host behavior beneficially, the next projection should be `project_full_hot` as one app.

That allows a complete normal research/engineering turn without selecting multiple Soma apps while still excluding peripheral domains.

## Adversarial alternatives

### A3-01 — "Split every Soma domain into its own app"

Not accepted. It optimizes static catalog size but can recreate the union when a workflow crosses domains and can add UX/status-scan overhead.

### A3-02 — "One project app containing every Soma tool"

No context benefit; equivalent to current monolithic surface.

### A3-03 — "Generic two-tool dispatcher"

Still disfavored. It would obscure action-specific permissions, schemas, safety annotations, and confirmation semantics.

### A3-04 — "Use dynamic tool visibility inside one approved app"

Not currently a safe primary architecture. OpenAI documents a frozen approved tool/input snapshot for custom MCP apps. Host refresh/update behavior, not server-side dynamic hiding, owns the public action catalog.

### A3-05 — "Assume multiple apps automatically reduce context"

Rejected. OpenAI explicitly allows multiple apps in one message. Context savings must be measured with realistic selected-app combinations.

## Preregistered shadow A/B contract

No implementation has started. The following is the proposed next experimental batch if the owner authorizes it.

### B0 — Baseline

Use the current production Soma app unchanged.

Measure:
- app discovery/tool count observed by ChatGPT;
- serialized live descriptor bytes for the host-exposed group;
- first useful tool-call latency;
- desktop `mcpServerStatus/list` latency around fresh app/chat re-entry;
- routing correctness on a frozen prompt corpus;
- freeze/stream-recovery outcome on controlled continuation-heavy prompts.

### B1 — Read-only shadow projection

Create a second, clearly named development-only app backed by the same Soma process/state, exposing only `project_read_lean`.

Hard constraints:
- no writes;
- no second durable state store;
- no second worker/run authority;
- no Docker dependency;
- no change to the existing production Soma app/tool snapshot;
- no automatic publication;
- easy rollback by removing the shadow route/app.

Frozen prompt corpus should include at minimum:
1. resume a known continuation and state the exact boundary;
2. read current `AGENTS.md`;
3. locate a repository symbol/file;
4. inspect latest run status;
5. inspect Research Map health;
6. find related research through Research Map search;
7. inspect a Skill;
8. answer a project-state question requiring two or more of the read tools;
9. a negative-control trivial prompt requiring no Soma tool;
10. a prompt that requires a write and must correctly fail/route away from the read-only shadow.

### B1 acceptance dimensions

The shadow is interesting only if all of the following hold:
- exact result parity with the corresponding production read tools;
- no new semantic authority or summarizer;
- no incorrect mutation capability;
- routing accuracy is not materially worse;
- host-exposed descriptor footprint is materially lower;
- first-use latency does not regress materially;
- desktop/global MCP status scanning does not show a material adverse regression attributable to the extra app;
- no increase in connector errors.

Suggested structural target for the read-only shadow:
- <= 35 KB serialized descriptor footprint for the app's frozen tool set.

Do not use freeze absence from a tiny read-only sample as proof of the final fix.

### B2 — Full project hot-path shadow

Only after B1 passes, test a 15-tool `project_full_hot` projection.

Purpose:
- reproduce a complete continuation/research/execute/edit/commit lifecycle inside one selected app;
- test whether the host now remains near the ~83 KB projected catalog rather than accumulating ~175 KB;
- measure whether stream freezes/recovery timeouts materially decline under repeated heavy-duty project work.

Additional acceptance requirements:
- action annotations/confirmations remain truthful;
- repo preview/apply/commit safety semantics remain unchanged;
- Run and continuation identities are identical to production because the backend is shared;
- existing production app remains available for comparison and rollback.

### B3 — Peripheral separation decision

Only if B2 passes, decide whether infrastructure, Company, trading, and other uncommon domains should become separate apps under the same logical Soma plugin.

Do not pre-split them merely because static sizing looks attractive.

## Measurement limitations

1. ChatGPT does not expose exact active prompt/token counters for custom app schemas in the desktop logs inspected so far.
2. Descriptor bytes are therefore a structural proxy, not an exact token accounting.
3. Current desktop `mcpServerStatus/list` latency is global and does not identify per-app contribution.
4. The OpenAI docs prove message-scoped app selection and frozen app snapshots, but do not prove how selected-app schemas are internally tokenized/deduplicated.
5. A real shadow app is required to measure those host behaviors.

## Iteration 03 conclusion

The app-projection architecture has moved from merely plausible to **technically feasible and experimentally justified**, but it is not yet accepted.

The strongest current candidate is:

> one canonical Soma backend + one normal project hot-path ChatGPT app + separate peripheral app projections only where evidence justifies them.

The safest next evidence is a development-only, read-only 6-tool shadow app. If that produces the expected host reduction without status-scan/routing regressions, proceed to a 15-tool full project hot-path shadow and test the actual freeze phenotype.

No production migration, API route, generic dispatcher, or context-reducing semantic summarizer is justified by the evidence yet.
