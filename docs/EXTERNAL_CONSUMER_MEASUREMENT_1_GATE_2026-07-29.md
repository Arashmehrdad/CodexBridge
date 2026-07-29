# EXTERNAL-CONSUMER-MEASUREMENT-1 — Bounded Public-Surface Usage Evidence

**Date:** 2026-07-29
**Status:** prepared for owner review; not authorised or executed.
**Decision level:** measurement and retirement-evidence classification only.
**Follows:** [`LEGACY_RETIREMENT_AUDIT_1_RESULT_2026-07-29.md`](LEGACY_RETIREMENT_AUDIT_1_RESULT_2026-07-29.md) and [`PUBLIC_CAPABILITY_METADATA_1_RESULT_2026-07-29.md`](PUBLIC_CAPABILITY_METADATA_1_RESULT_2026-07-29.md).

## Purpose

Measure the owner-controlled consumer universe for three public surfaces whose
retirement is currently blocked by unknown external use:

1. the six generic knowledge operations that predate the canonical `memory_*`
   family;
2. the exported Python package symbols `LocalAgentOrchestrator` and
   `classify_task`;
3. the legacy response field `schema_hash`.

The lane must replace vague claims such as “no consumer found” with a bounded,
reproducible consumer matrix that states exactly what was inspected, what was
observed, what could not be observed, and what residual risk remains.

This lane collects evidence. It does **not** deprecate, remove, rename, redirect
or change any measured surface.

## Governing rule

Absence is meaningful only inside a declared measurement universe.

The result may say:

> No consumer was found in the inspected owner-controlled repositories,
> environments, configurations and controlled controller probes.

It may not silently turn that statement into:

> No external consumer exists.

A server can observe that a response field was emitted; it cannot infer that a
client read or compared that field. A repository search can prove that a symbol
is referenced in searched roots; it cannot prove that no unsearched package or
machine imports it. Every conclusion must preserve those distinctions.

## Exact measured surfaces

### A. Generic knowledge operations

The lane must measure these public MCP operations individually:

- `knowledge_action.save_knowledge`;
- `knowledge_action.supersede_knowledge`;
- `knowledge_action.rebuild_knowledge`;
- `knowledge_query.get_knowledge`;
- `knowledge_query.search_knowledge`;
- `knowledge_query.knowledge_health`.

The matrix must identify the canonical replacement, where one exists, without
changing routing or advertising. Candidate replacements include the scope-bound
`memory_save`, `memory_supersede`, `memory_rebuild_index`, `memory_get`,
`memory_search` and `memory_health` operations, but the executing controller must
verify the actual contract and semantic differences rather than assuming a
one-to-one alias.

### B. Exported Python package symbols

The lane must measure external imports and references to:

- `soma.local_agent.LocalAgentOrchestrator`;
- `soma.local_agent.classify_task`;
- equivalent direct-module imports from `soma.local_agent.orchestrator`.

The package export itself is a public surface because the symbols are present in
`__all__`, resolved by package-level `__getattr__`, and shipped under the Soma
package include rule. “Not an MCP gateway” is not evidence that it is private.

### C. Legacy `schema_hash`

The lane must distinguish:

- clients that merely receive `schema_hash` because every response contains it;
- clients whose source, configuration, tests or controlled behaviour actually
  read, persist, compare or branch on it;
- clients using the correct replacements: `public_schema_hash`,
  `discovery_cache_generation`, or per-operation hashes from
  `capability_identity`.

Emission count is not consumption evidence.

## Authority granted when started

The executing controller may:

- inspect the Soma repository and committed history read-only;
- enumerate repositories registered with Soma and inspect explicitly
  owner-approved client roots read-only;
- inspect relevant package metadata and Python environments that the owner has
  approved for this measurement;
- inspect existing Soma run, audit, service and connector evidence where access
  is already authorised;
- inspect known client configuration and source files with credentials and
  unrelated content redacted;
- run bounded, non-destructive controller probes through ChatGPT, Claude Code,
  Hermes and other known clients;
- run read-only commands needed to produce hashes, references and reproducible
  search evidence;
- create only the result, machine-readable consumer matrix and the corresponding
  `PLANS.md` status update.

The authorised outputs are:

- `docs/EXTERNAL_CONSUMER_MEASUREMENT_1_RESULT_2026-07-29.md`;
- `docs/external-consumer-measurement-1-matrix-2026-07-29.json`;
- the corresponding status update in `PLANS.md`.

No product source, test, schema, configuration, package export, gateway,
credential, connector, durable store, memory record, service or deployment may
be changed.

## Required measurement universe

Before searching, the result must freeze a named universe containing at least:

1. the current Soma repository and its Git history relevant to the measured
   surfaces;
2. every repository currently registered with Soma, with repository name,
   resolved root and inspected commit or content fingerprint;
3. the active CodexBridge checkout;
4. the Hermes checkout, service configuration and tool registry actually used by
   the current Soma integration;
5. the installed Trading Lab package or checkout and its active scheduled-task
   configuration;
6. Claude Code project configuration, skills and MCP configuration under the
   explicitly approved project roots;
7. the current ChatGPT connector contract and controlled live behaviour that is
   observable through Soma;
8. approved Python environments in which Soma or a client package is installed;
9. any additional owner-named controller, repository or environment discovered
   during the lane.

For each expected source, the matrix must record one of:

- `inspected`;
- `not_present`;
- `access_unavailable`;
- `owner_excluded`;
- `not_observable`.

The lane must not scan an entire disk, browser profile, home directory, email,
chat history, private vault content or unrelated repository merely to improve a
coverage percentage. New roots require explicit owner approval.

## Evidence hierarchy

Each consumer claim must identify its evidence level:

1. **Observed runtime use** — an existing authorised record or controlled probe
   shows the exact operation or behaviour.
2. **Direct static use** — source or configuration reads, imports, compares or
   invokes the exact surface.
3. **Derived compatibility dependency** — tests, serializers, persisted evidence
   or wrappers require the surface even if no current invocation was observed.
4. **No use found in measured universe** — complete bounded searches and probes
   found no use in the declared universe.
5. **Not observable** — the available evidence cannot answer the question.

Levels 4 and 5 never become proof of global non-use. A retirement recommendation
based on level 4 requires explicit owner acceptance of the residual external
risk.

## Static inspection requirements

The lane must use complete, non-truncated searches or prove continuation through
all cursors. It must record search roots, exclusion rules, query forms and result
counts so the truncated-search failure found during `LEGACY-RETIREMENT-AUDIT-1`
cannot recur silently.

Static inspection must cover, where applicable:

- exact operation strings and gateway-qualified names;
- request model construction and wrapper aliases;
- `schema_hash`, `public_schema_hash`, `discovery_cache_generation` and
  `capability_identity` comparisons;
- direct and package-level Python imports;
- dynamic import forms, `getattr`, string-based registries and plugin loading;
- configuration templates, examples, scripts, tests, docs that generate live
  client behaviour, and scheduled-task prompts;
- installed distribution metadata and editable/non-editable source locations;
- historical references that may still generate current configuration or
  controller instructions.

Documentation-only mentions must be separated from executable or configuration
consumers.

## Dynamic inspection requirements

The lane must perform bounded controlled probes for each currently available
controller:

- ChatGPT through the public connector;
- Claude Code through its active Soma MCP configuration;
- Hermes through the loaded companion/service registry;
- CodexBridge or another owner-approved client where it directly consumes Soma;
- Trading Lab where its active automation or package calls the measured surface.

A probe must use a non-sensitive, disposable intent and must record the exact
operation selected or the exact observable metadata behaviour. Read-only probes
are preferred. A write probe requires a disposable isolated scope and complete
cleanup evidence; it must never write into canonical owner or project memory.

Controlled probes show current behaviour under the tested prompt and client
version. They do not prove that every other prompt, cached schema or older client
behaves the same way.

## Existing evidence before new instrumentation

The controller must first determine whether existing server, tunnel, run, audit
or client records already expose operation names without exposing request
content. Existing evidence must be preferred.

This gate does not authorise a new persistent telemetry system, import callback,
response canary, deprecation warning, user fingerprint or hidden client tracker.
It also does not authorise logging request arguments, response bodies, prompts,
memory content, project or repository identity, IP address, user-agent, session
identifier, credential, token or private path.

If exact MCP operation use cannot be measured without new runtime
instrumentation, record that surface as `not_observable` and propose a separate,
owner-reviewed instrumentation gate. Do not smuggle logging into this lane.

Python import usage and response-field reads must not be “measured” through
outbound telemetry or behaviour changes in the exported package. Use approved
static sources and controlled clients, and preserve the residual unknown.

## Required consumer matrix

The JSON matrix is authoritative and must contain, for every surface and every
expected client or environment:

- stable surface ID and surface kind;
- exact operation, symbol or field name;
- current producer and advertised/exported location;
- verified replacement or `none`;
- inspected consumer label and consumer version/commit/fingerprint;
- measurement source and evidence level;
- relative source/config path and line, or controlled-probe evidence ID;
- first and last observed use when genuinely available;
- observed read, write, compare, import, persistence or invocation behaviour;
- search completeness and truncation/cursor status;
- result: `active`, `compatibility_dependency`, `no_use_found`,
  `not_observable`, or `not_applicable`;
- confidence and residual blind spots;
- migration requirement, if active;
- recommended action and required owner acceptance.

Raw external source content must not be copied into the matrix. Store the minimum
relative locator, hash and paraphrased finding needed to reproduce the claim.

## Required result

The Markdown result must provide:

1. the frozen measurement universe and coverage gaps;
2. a per-surface consumer summary;
3. named active consumers and the exact replacement/migration needed;
4. surfaces with no use found inside the measured universe;
5. surfaces that remain unobservable;
6. privacy and data-retention confirmation;
7. a retirement-readiness decision for each of the three surface families;
8. the smallest justified successor decision;
9. whether the Pre-Roadmap V3 bridge now has enough evidence to close.

## Retirement-readiness outcomes

Each surface family must close with exactly one recommendation:

- `keep_active` — measured use or compatibility requires retention;
- `migrate_named_consumers` — consumers are known and must move before any
  deprecation;
- `prepare_deprecation_gate` — no use was found in the complete measured
  universe and the owner may decide whether to accept residual external risk;
- `remain_unknown_blocked` — evidence is insufficient or not observable;
- `defer_to_v3` — the cost or architecture of retirement belongs in Roadmap V3.

This lane cannot itself choose removal or silently reinterpret an unknown as
unused.

## Explicit exclusions

This gate does not authorise:

- removing, renaming, hiding or deprecating any operation, symbol or field;
- changing `schema_hash`, `public_schema_hash`, capability metadata or response
  envelopes;
- changing knowledge or memory routing, schemas, scope rules or persistence;
- editing `soma.local_agent.__all__`, `__getattr__` or orchestrator behaviour;
- modifying client prompts, skills or configuration except disposable controlled
  probes that leave no persistent change;
- adding persistent telemetry, analytics, warnings or network callbacks;
- scanning unapproved personal or unrelated data;
- storing raw prompts, arguments, responses, source files or credentials;
- migration, cleanup, deletion, deployment, merge to main or Roadmap V3
  implementation;
- code-intelligence activation, RAGFlow deployment, personal memory,
  conversation ingestion or Cortana presence work.

## Stop conditions

Stop and publish the gap without broadening scope if:

- a required root or client cannot be inspected safely;
- search output is truncated and cannot be continued reproducibly;
- measurement would require secrets, unrelated personal data or unapproved
  filesystem access;
- exact use requires new persistent instrumentation;
- a controlled probe would mutate canonical state or client configuration;
- static and dynamic evidence conflict and the contradiction cannot be resolved;
- unrelated owner work appears in the worktree;
- the lane begins changing the measured public surface rather than observing it.

## Acceptance outcome

The lane may close only as:

- **measurement-complete** — the declared universe was fully classified, every
  expected source has an explicit inspection status, searches are complete,
  probes and blind spots are recorded, and the matrix/result agree; or
- **measurement-blocked** — exact unavailable or unobservable evidence is
  recorded without claiming non-use.

`measurement-complete` means complete for the declared universe, not complete
for the world. Any deprecation or migration remains a separate owner decision
and separate gate.

## Owner start language

A sufficient start instruction is:

> Start EXTERNAL-CONSUMER-MEASUREMENT-1 exactly as prepared. Freeze and inspect the owner-approved consumer universe for the six generic knowledge operations, the exported LocalAgentOrchestrator and classify_task symbols, and legacy schema_hash consumption. Use complete static searches, existing authorised evidence and bounded non-destructive controller probes. Do not add persistent telemetry, scan unapproved personal data, mutate canonical state, change any measured surface, migrate consumers or deprecate anything. Treat unobservable use and residual external risk explicitly. Close with the Markdown result, machine-readable consumer matrix and PLANS.md status only.
