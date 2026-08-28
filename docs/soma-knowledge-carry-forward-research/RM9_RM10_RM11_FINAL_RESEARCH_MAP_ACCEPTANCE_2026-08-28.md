# RM9–RM11 Final Research Map Acceptance — 2026-08-28

Status: **ACCEPTED — SOMA HYBRID RESEARCH MAP ROADMAP COMPLETE**

Authoritative roadmap:

`docs/SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md`

This record closes RM9, RM10, and RM11 and therefore closes the Soma Hybrid Research Map implementation roadmap.

## 1. Ownership correction preserved

The final accepted ownership boundary is:

- Soma owns the Research Map engine, public contracts, deterministic identity, validation, publication, rebuild, retrieval, durability and conformance testing.
- Each research project lane owns its own scientific materiality, historical curation, relation wording, lifecycle/supersession decisions, sidecars and future finishing-touch maintenance.
- NSDN and Axion are real-project rollout/conformance evidence, not research corpora owned by the Soma implementation lane.
- Soma must not change a project sidecar merely to make an engine benchmark pass.
- Retrieved relations are navigation/carry-forward context; exact project Markdown remains scientific authority.

This correction supersedes any earlier interpretation that RM9/RM10 authorized the Soma implementation lane to take over ongoing NSDN or Axion research-map maintenance.

## 2. RM9 — NSDN controlled rollout

Verdict: **ACCEPTED**

The controlled NSDN rollout completed the roadmap acceptance contract at its rollout boundary.

Accepted evidence includes:

- explicit NSDN adoption with tracked `soma.project.json` and `_soma_map` sidecars;
- initial gold backfill of 21 reviewed source documents;
- bounded historical backfill to complete source coverage;
- zero stale/unreviewed/missing/deferred records at the acceptance boundary;
- fixed semantic benchmark reproduced at **15/15 Top-5**;
- full-map benchmark run `20260826T143643Z_executable_profile_1fedcd60`:
  - 15/15 Top-5;
  - 12/15 Hit@1;
- deterministic clean-clone rebuild run `20260826T143750Z_executable_profile_c2692c5b`:
  - fresh clone started without `.soma` runtime;
  - 107 relations rebuilt;
  - publication succeeded;
  - reopen verification succeeded;
  - repository identity and desired-state identity matched;
- incremental new-research publication run `20260826T143517Z_executable_profile_6ada4487`:
  - publication succeeded;
  - 107 relations;
  - reopen verification succeeded;
- idempotent repeat sync returned `already_current`.

### Current NSDN state after hand-back

NSDN subsequently continued under its own project lane and is currently:

```text
adoption_state = adopted
manifest_state = valid
coverage_state = complete
sync_state = published_verified
reviewed_material = 64
reviewed_no_material = 71
stale = 0
unreviewed = 0
deferred = 0
missing_source = 0
issue_count = 0
published_generation = gen_20260828T143915481400Z_9217cbf36375_65dd8583
```

A final closure audit intentionally rechecked the old benchmark against the evolved project map. Exact historical expected-fact matching no longer reproduces 15/15 because the NSDN project lane has since reviewed several formerly benchmarked historical facts as `reviewed-no-material` or consolidated their current carry-forward semantics.

That later project-owned materiality decision does **not** reopen RM9. RM9 is a controlled rollout acceptance point, and its 15/15 benchmark was actually achieved and recorded before ownership was handed back. Soma is forbidden from rewriting current NSDN scientific materiality merely to preserve a historical engine benchmark identity.

Future NSDN map quality and materiality remain the NSDN lane's responsibility; engine defects discovered there return to Soma as minimal reproducible infrastructure issues.

## 3. RM9 search-strengthening implementation

The controlled rollout exposed a generic retrieval weakness: semantic backend order alone could miss a governing reviewed relation in a larger candidate set.

Accepted generic fix:

`c1a1c2d609c0c2a9ae3cff435b4f717c638e9df3` — `Strengthen Research Map semantic reranking`

The production search path now applies deterministic BM25 lexical evidence over immutable reviewed relation text while preserving the backend semantic candidate set and deterministic ordering.

This implementation contains no NSDN-specific scientific strings or relation identities.

Final validation after cleanup:

```text
Research Map tests: 94 passed, 1 dependency warning, 0 failed
xdist workers: 12
Ruff: PASS
```

The warning is Graphiti's existing Pydantic class-config deprecation and is not a Research Map correctness failure.

## 4. RM10 — Axion rollout and scale acceptance

Verdict: **ACCEPTED**

Axion adoption/backfill was completed by the Axion scientific lane, preserving the corrected project-ownership boundary.

Current live Axion Research Map state:

```text
project_id = proj_repo_23058ce41311b76c56303da0
repository_uid = srepo_bec50c1dfc037630e3dee90402708f17
adoption_state = adopted
manifest_state = valid
coverage_state = complete
sync_state = published_verified
reviewed_material = 385
reviewed_no_material = 120
eligible/reviewed records = 505
stale = 0
unreviewed = 0
deferred = 0
missing_source = 0
issue_count = 0
published_generation = gen_20260828T133807696688Z_7ce419a05878_9849d8b4
```

The completed map projects **1,727 reviewed relations** into the derived backend.

Axion Git remained project-owned; the Soma lane did not curate its scientific corpus during final acceptance.

### Difficult retrieval acceptance

The frozen Axion Iteration-12 adversarial retrieval pilot established:

```text
20 / 20 difficult questions = governing relation within Top-5
Hit@1 = 45%
Hit@3 = 95%
Hit@5 = 100%
MRR = 0.6958333333
```

Two independent reopen/query processes produced identical aggregate scores and identical ranked result lists.

The accepted pilot is preserved in:

`docs/soma-knowledge-carry-forward-research/iteration-12-axon-repo-local-persistence-crash-recovery-and-portable-source-identity-pilot-2026-08-24.md`

### Full-scale runtime defect discovered and closed

The complete 505-record/1,727-relation Axion map exposed a real scale defect during final semantic-search verification.

Observed diagnosis:

```text
backend open/model initialization ≈ 5.79 s cold
manifest verification ≈ 0.29 s
query embedding ≈ 0.25 s
Graphiti/Falkor search failed at ≈ 1.23 s
FalkorDB server TIMEOUT = 1000 ms
```

Research Map does not use Soma's `local_model` or Ollama path. The backend explicitly uses local FastEmbed and a `NoLLM` Graphiti client; any Graphiti LLM path is forbidden.

The engine fix makes Soma supply a deterministic bounded **5000 ms per-query Falkor timeout** rather than inherit the server's arbitrary 1000 ms default.

Accepted commits:

- `c3e49f1e675044afc3c3b9e71ff2fb6d3a0d4ecc` — `Bound Research Map Falkor query timeout`
- `4a848b23460ca24b1166794c6939d1627f324861` — `Fix Research Map timeout test fixture`

Diagnostic search with explicit bounded timeouts succeeded at approximately 2.0–2.4 seconds for 20 results.

After service restart, the previously failing public Axion query:

`joint-aware N3 N4 generated GPU first implementation contract`

returned five source-verified results with `backend_state = verified`, including the generated GPU-first implementation contract in Top-5.

No Axion rebuild, scientific rewrite, or project-side workaround was required.

## 5. RM10 scale interpretation

RM10 required measurement before threshold invention. The full rollout supplied real scale evidence rather than a synthetic threshold:

- eligible reviewed sources: 505;
- published relations: 1,727;
- cold backend/model-open cost measured;
- manifest verification cost measured;
- embedding cost measured;
- semantic-search cost measured;
- a server-timeout scaling failure was reproduced, attributed and fixed generically;
- complete publication remained reopen-verified;
- project coverage remained complete and truthful.

No new scientific or performance threshold was invented merely to close the roadmap.

## 6. RM11 — final rollout, documentation and legacy boundary

Verdict: **ACCEPTED**

### Public gateways

The sole Research Map public gateways are:

`research_map_query`

- `health`
- `coverage`
- `relation`
- `search`
- `authoring_contract`
- `relation_id`

`research_map_action`

- `adopt`
- `sync`
- `rebuild`

Project threads no longer need to inspect Soma source to discover the sidecar schema or deterministic relation-ID rule.

### Public authoring contract

Commit:

`b00c23a90a774fa9e93e0d1dc822f0ce82c79673` — `Expose Research Map authoring contract`

`authoring_contract` returns the live v2 sidecar schema, configured roots, placement rule, source-hash contract, predicate registry, deterministic identity contract and explicit project/Soma authoring boundary.

`relation_id` calls Soma's canonical deterministic relation-ID implementation directly.

### Documentation

Canonical production documentation is now:

`docs/research-map.md`

It documents:

- `.soma/research-map/` as ignored local generated runtime;
- tracked `soma.project.json` portability contract;
- tracked `_soma_map` sidecar v2 contract;
- canonical source hashing;
- deterministic relation-ID usage;
- public query/action gateways;
- project-owned authoring/materiality boundary;
- adoption/backfill/incremental update workflow;
- source-verification trust rule;
- optional backend/NoLLM model;
- failure/rebuild behavior;
- legacy isolation.

README points to this canonical Research Map documentation and lists the complete current gateway surface.

### Legacy boundary

The duplicate RAGFlow research service was retired in:

`daceafec9ab183fa8e227208f391a08e6da5cab3` — `Retire legacy RAGFlow research service`

The old RAGFlow Compose service was brought down without deleting its volumes, and the public legacy research gateway was removed. New Research Map traffic does not route through `soma.research.v1` or the old context-packet path.

The shared `arash-research` Skill remained untouched throughout RM0–RM11 as required. Its post-roadmap finishing-touch revision becomes eligible only after this acceptance is sealed.

## 7. Production-ready v1 matrix

Final status:

```text
portable manifest                         ACCEPTED
sidecar v2                               ACCEPTED
.soma namespace protection               ACCEPTED
coverage/desired-state engine             ACCEPTED
separate read-only query gateway          ACCEPTED
explicit adopt/sync/rebuild action        ACCEPTED
optional backend isolation                ACCEPTED
immutable generation transaction          ACCEPTED
explicit persistence/reopen verification  ACCEPTED
NSDN controlled benchmark                 ACCEPTED
Axon difficult benchmark                  ACCEPTED
clone/rebuild                              ACCEPTED
new-research incremental workflow         ACCEPTED
legacy research runtime isolation         ACCEPTED
core Soma without backend                 ACCEPTED
project-owned materiality boundary         ACCEPTED
public sidecar authoring contract          ACCEPTED
full-scale Falkor timeout behavior         ACCEPTED
```

Acceptance matrix A01–A30 is therefore **ACCEPTED** under the ownership clarification above.

A23 is satisfied by the recorded controlled NSDN rollout benchmark, not by forcing future NSDN materiality to preserve frozen relation identities forever.

A24 is satisfied by the frozen 20/20 Axion difficult benchmark plus successful full-scale verified search after the RM10 timeout fix.

## 8. Final exclusions preserved

The programme did not introduce:

- a global all-project graph;
- automatic LLM extraction;
- automatic contradiction truth;
- a second semantic reasoning controller;
- hidden auto-adoption;
- hidden after-save semantic generation;
- RAGFlow revival;
- continuation redesign;
- provider/subagent routing;
- automatic Git push;
- automatic project scientific materiality decisions.

## 9. Final verdict

**RM9 ACCEPTED.**

**RM10 ACCEPTED.**

**RM11 ACCEPTED.**

**SOMA HYBRID RESEARCH MAP IMPLEMENTATION ROADMAP COMPLETE.**

The Research Map engine is production-ready v1 under the documented repository-scoped, project-owned scientific-authority boundary.

The next activity is not another RM implementation stage. The previously deferred post-roadmap finishing touch may now update the shared `arash-research` Skill so each project lane performs its own Research Map finishing touch after future research iterations.
