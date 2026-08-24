# Soma Knowledge Carry-Forward Research — Iteration 12

**Date:** 2026-08-24  
**Status:** COMPLETE — Axon repo-local persistence, crash-recovery, portable-source-identity and semantic-retrieval pilot passed with required design corrections  
**Scope:** empirically test the Iteration-09–11 hybrid research-map architecture against a difficult Axon slice using a repository-local Graphiti/FalkorDB-Lite runtime, tracked reviewed sidecars, a portable project manifest, process restarts, desired-state drift, and a deliberately interrupted sync boundary

## 1. Owner direction

The owner accepted the repo-local hybrid architecture and authorized the Axon-scale deployment/persistence pilot.

The governing architecture remains:

```text
repository research Markdown = authoritative scientific truth
Sol / ChatGPT               = semantic understanding and adjudication
tracked reviewed sidecars    = durable semantic projection
Soma                         = project scope, validation, health, sync workflow
Graphiti                     = derived semantic retrieval
repo-local .soma/ runtime    = disposable local index state
```

Continuation remains unchanged and out of scope.

Codex integration remains forbidden.

No production Soma research-map implementation was authorized by this iteration. The purpose was to determine whether the architecture was sufficiently evidenced to proceed to an implementation plan.

## 2. Duplicate guard

Before this document was created, the Soma research directory was enumerated and contained exactly Iterations 01–11.

No Iteration 12 existed.

This preserves the explicit interruption guard introduced after the duplicate Iteration-08 incident.

## 3. Live Axon safety boundary

The authoritative Axon repository at pilot start was:

```text
D:\Github\Axon_modelling
branch: master
HEAD: e871350e436e2f5ef70b14c4dc9b2a0f08dccf55
```

The live repository was initially clean.

A repo-local pilot write was attempted only after owner authorization, but Soma refused it because the Axon repository was busy under another durable operation.

That refusal was respected. The pilot did not fight the live repository lock or interfere with the active Axon thread.

Instead, the test used a disposable local clone:

```text
D:\Services\GraphitiPilot\axon_shadow_repo
```

Clone evidence:

```text
run 20260824T141751Z_executable_profile_18064c6f
SHADOW_HEAD=e871350e436e2f5ef70b14c4dc9b2a0f08dccf55
```

The shadow clone therefore tested the exact Axon source state while isolating all pilot mutations from the live project.

Final live Axon inspection after the pilot still reported:

```text
HEAD e871350e436e2f5ef70b14c4dc9b2a0f08dccf55
branch master
worktree clean
```

No live Axon tracked file was modified by this research.

## 4. Pilot corpus

The pilot intentionally did not attempt a 460-record backfill.

It selected a difficult 14-document Axon slice containing the failure modes that drove the v2 design:

### Main architecture/collaboration corpus

```text
docs/architecture_research/89_phase5_owner_decision_negative_finding_closeout.md
docs/architecture_research/91_phase5_owner_decision_reopen_maharatna_improvement.md
docs/architecture_research/285_parametric_pathmnist_terminal_result.md
```

### Independent architecture corpus

```text
docs/axon_independent_architecture/077_asg_g3_closeout_and_g4_evidence_integration_charter.md
docs/axon_independent_architecture/081_asg_g4_candidate_reconciliation_provenance_and_evaluation_boundary.md
docs/axon_independent_architecture/091_asg_g4_tad1_historical_development_terminal_result.md
docs/axon_independent_architecture/162_asg_g5_n2_tra_historical_medical_mechanism_protocol.md
docs/axon_independent_architecture/164_asg_g5_n2_tra_protocol_determinism_amendment.md
docs/axon_independent_architecture/166_asg_g5_n2_tra_full_owner_inner_fold_amendment.md
docs/axon_independent_architecture/168_asg_g5_n2_tra_historical_runner_contract.md
docs/axon_independent_architecture/169_asg_g5_n2_tra_historical_runner_contract_independent_audit.md
docs/axon_independent_architecture/170_asg_g5_n2_tra_runner_authority_readiness_binding_amendment.md
docs/axon_independent_architecture/171_asg_g5_n2_tra_independent_runner_binding_amendment_audit.md
docs/axon_independent_architecture/172_asg_g5_n2_tra_independent_final_runner_source_readiness_audit.md
```

The slice contains:

- two different research records labelled Research 091 in different research surfaces;
- scoped reopening that preserves an earlier negative finding;
- duplicate-number reconciliation for 077–080;
- cross-project NSDN methodological transfer;
- supported locality with explicit topology-causality limits;
- terminal mechanism failure without collapsing the whole architecture family;
- a three-record composite scientific protocol;
- a four-record runner-governance chain;
- an independent readiness boundary;
- a sealed official-test terminal result with explicit descriptive-only comparison limits.

Sol reviewed and encoded:

```text
14 source documents
38 material semantic relations
20 adversarial natural-language questions
```

## 5. Repo-local layout under test

The shadow clone used the intended split:

```text
TRACKED / PORTABLE
soma.project.json
docs/architecture_research/_soma_map/*.json
docs/axon_independent_architecture/_soma_map/*.json

LOCAL / DISPOSABLE
.soma/research-map-pilot/
  CURRENT.json
  DESIRED.json
  index/
```

The local runtime path was added to the shadow repository's local Git exclude file:

```text
.git/info/exclude
.soma/research-map-pilot/
```

After sidecar/manifest generation, `git status --short` showed only:

```text
?? docs/architecture_research/_soma_map/
?? docs/axon_independent_architecture/_soma_map/
?? soma.project.json
```

The `.soma/research-map-pilot/` runtime never appeared in Git status.

This confirms the intended portability boundary without requiring a tracked `.gitignore` edit.

## 6. Backend persistence finding — `driver.close()` is insufficient for FalkorDB Lite

Iteration 11 left FalkorDB Lite cross-process persistence unresolved because one earlier reopen appeared empty.

Iteration 12 reproduced the issue with a single-node two-process smoke test.

### 6.1 Close-only smoke

Run:

```text
20260824T141808Z_executable_profile_6430994c
```

Process one:

```text
WRITE_COUNT = 1
```

Process two:

```text
READ_COUNT = 0
```

Therefore the previous empty-reopen observation was real.

### 6.2 Wrapper inspection

The installed `redislite` async wrapper was inspected.

Its async close path closes the Redis client and invokes cleanup, but does not issue an explicit persistence command before shutdown.

### 6.3 Explicit SAVE smoke

The same smoke was repeated with:

```python
await lite.connection.execute_command("SAVE")
```

Run:

```text
20260824T141951Z_executable_profile_e13173e0
```

Observed:

```text
WRITE_COUNT = 1
SAVE_REPLY = True
DB_EXISTS_BEFORE_CLOSE = True
DB size = 1098 bytes
DB_EXISTS_ON_REOPEN = True
READ_COUNT = 1
```

### Decision

FalkorDB Lite is not disqualified by this pilot, but `driver.close()` alone is not an acceptable durability boundary.

Any production Lite adapter must use an explicit transaction sequence:

```text
write/reconcile desired graph
→ read-back verify graph state
→ explicit Redis SAVE
→ require successful SAVE reply
→ close
→ only then publish/advance CURRENT.json
```

If explicit persistence cannot be guaranteed under a future backend/version, that backend fails the adapter contract.

## 7. Major portability correction — raw filesystem SHA-256 is not a portable Markdown source identity

The first 14-source preflight failed even though the shadow clone was at exactly the same Git commit as live Axon.

Research 285 had:

```text
live raw SHA-256
c3bfc32630e9e5a25caffb8c354eba5197a1de3722a0435a281a2bb7908df2e9

shadow raw SHA-256
2503182c1b9fcc5f8b7419b161760344fa4e981854ca66a41cace23aa7edfc1e
```

Git evidence showed both copies were the same tracked blob:

```text
a0cc917e77f7e64d8faca0a466da8f57259b4284
```

Byte inspection established the reason:

```text
live   : 8245 bytes, 0 CRLF,   209 LF
shadow : 8454 bytes, 209 CRLF, 209 LF
```

After canonical newline normalization:

```text
CRLF -> LF
CR   -> LF
```

both produced:

```text
c3bfc32630e9e5a25caffb8c354eba5197a1de3722a0435a281a2bb7908df2e9
```

Evidence run:

```text
20260824T142530Z_executable_profile_30e54461
```

### Decision

Iterations 09–11 are corrected on this point.

For UTF-8 research Markdown, the portable sidecar source identity must be:

```text
read UTF-8 text
→ canonicalize CRLF/CR to LF
→ encode UTF-8
→ SHA-256
```

Call this field, for example:

```text
canonical_text_sha256
```

Raw filesystem SHA-256 may still be diagnostic evidence but must not determine cross-clone sidecar freshness.

For committed files, Git blob OID is useful additional provenance.

However Git blob identity cannot replace canonical worktree-text validation because a current research document may legitimately be uncommitted while being reviewed.

## 8. Locator encoding finding

After the canonical-text correction, preflight reached source-anchor validation and found one pilot-harness transport defect: an em dash in an R172 anchor had been mojibaked while the external Python harness was written through PowerShell.

The locator was replaced with the exact ASCII-safe phrase from the same authoritative status line:

```text
PROTECTED TRAINING STILL CLOSED
```

No source document was changed.

This is not an argument to ban Unicode from research documents.

It is an implementation requirement that the sidecar writer and validator use explicit UTF-8 end to end and test Unicode round trips.

## 9. Successful portable preflight

After the source-identity and locator corrections, the 14-source preflight passed.

Run:

```text
20260824T142653Z_executable_profile_35351a60
```

Result:

```text
sources = 14
relations = 38
HEAD = e871350e436e2f5ef70b14c4dc9b2a0f08dccf55
desired_state_sha256 = 541b274d6ca67c0348b34266e46cc1543c94b80222f317686d71a6835a0e2f5b
```

The generated sidecars remained tracked/portable candidates while the local runtime stayed Git-invisible.

## 10. Structured-sidecar / primitive-graph projection boundary

The first complete graph build failed before persistence.

Run:

```text
20260824T142710Z_executable_profile_44eb8309
```

FalkorDB rejected the structured `facets` dictionary in edge attributes:

```text
Property values can only be of primitive types or arrays of primitive types
```

### Decision

This is a projection limitation, not a reason to flatten the durable scientific sidecar schema.

The sidecar keeps structured facets such as:

```json
{
  "programme": ["ASG-G5"],
  "record_role": ["independent-audit"]
}
```

The Graphiti/FalkorDB adapter projects them using a backend-compatible representation.

The pilot used:

```text
facets_json = canonical JSON string
```

Future backends may use native structured properties if supported.

The durable research-map contract therefore remains backend-independent.

## 11. Successful repo-local graph build

After primitive projection correction, a clean graph build succeeded.

Run:

```text
20260824T142926Z_executable_profile_0f96391c
```

Observed:

```text
nodes = 52
edges = 38
explicit SAVE = true
DB size = 374728 bytes
desired_state_sha256 = 541b274d6ca67c0348b34266e46cc1543c94b80222f317686d71a6835a0e2f5b
```

A separate process then reopened the persisted DB.

Run:

```text
20260824T142958Z_executable_profile_9ae87da8
```

Health:

```text
wanted_edges = 38
actual_edges = 38
missing = []
extra = []
desired_match = true
sync_current = true
```

This closes the basic cross-process persistence question when explicit SAVE is used.

## 12. First Axon semantic retrieval result

A third process ran the 20 adversarial questions.

Run:

```text
20260824T143029Z_executable_profile_7ebfdf97
```

Initial result:

```text
Hit@1 = 65%
Hit@3 = 95%
Hit@5 = 95%
MRR   = 0.7833333333
```

Nineteen of twenty questions recovered an acceptable governing relation within Top-5.

The sole miss was Q18:

```text
Are the PathMNIST differences versus the earlier ResNet and P1 programmes prospective superiority claims?
```

Expected relation:

```text
PATH285_DESCRIPTIVE_ONLY
```

A 20-result diagnostic placed the correct relation at rank 16.

Run:

```text
20260824T143124Z_executable_profile_c7134329
```

## 13. Q18 miss was a semantic-projection defect, not a source or benchmark defect

The original reviewed relation statement compressed the relevant comparison into:

```text
Research-209 models
```

while the authoritative Research 285 source explicitly names P1 and scratch ResNet-18 in the comparison table and states that the cross-programme differences remain descriptive because no paired superiority/inferiority interval was predeclared.

The sidecar statement was therefore improved, without changing the source or the question, to retain the source's explicit model names and qualification:

```text
Research 285 treats comparisons with the earlier Research-209 P1 and scratch
ResNet-18 PathMNIST models as descriptive historical comparisons only; no
prospective superiority or inferiority claim is allowed because no paired
interval was predeclared.
```

This is exactly the kind of reviewed semantic compression the sidecar is intended to preserve.

The benchmark question and gold target were not rewritten.

## 14. Desired-state drift detection after reviewed-sidecar change

Regenerating the corrected sidecar changed desired state from:

```text
541b274d6ca67c0348b34266e46cc1543c94b80222f317686d71a6835a0e2f5b
```

to:

```text
3d8f8b165ff646e36e26c3999ee37ab23da1ddcb5e0122bc2efdb4f3b89d887e
```

Run:

```text
20260824T143206Z_executable_profile_9792bb38
```

The old graph still had all 38 deterministic edge UUIDs, so edge-count comparison alone could not detect the changed reviewed statement.

Health correctly reported:

```text
actual_edges = 38
wanted_edges = 38
current_desired_state = 541b274d...
live_desired_state = 3d8f8b16...
desired_match = false
sync_current = false
```

The query path then refused with a non-zero exit rather than silently searching stale semantic content.

Evidence:

```text
20260824T143219Z_executable_profile_3745a19f
QUERY_EXIT=1
```

### Decision

A production desired-state hash is mandatory.

Set equality of relation IDs is insufficient because the semantic text, lifecycle, facets, locator or provenance of an existing deterministic relation may change.

Queries must fail closed or explicitly degrade when desired-state identity does not match the published local index state.

They must never rebuild as a read-side effect.

## 15. Corrected graph rebuild and final retrieval result

The graph was rebuilt from the corrected sidecars.

Run:

```text
20260824T143311Z_executable_profile_dcb9fb05
```

Observed:

```text
nodes = 52
edges = 38
explicit SAVE = true
DB size = 268019 bytes
desired_state_sha256 = 3d8f8b165ff646e36e26c3999ee37ab23da1ddcb5e0122bc2efdb4f3b89d887e
```

Two completely separate Python process opens then replayed all 20 questions.

Run:

```text
20260824T143352Z_executable_profile_964c5a4a
```

Both opens produced identical aggregate scores and identical ranked result lists:

```text
Hit@1 = 45%
Hit@3 = 95%
Hit@5 = 100%
MRR   = 0.6958333333
```

Q18 improved from rank 16 to rank 2.

The lower Hit@1 is not treated as a regression against the carry-forward acceptance purpose.

The architecture's priority is:

```text
governing context included in a small candidate set
>
perfect first-result ordering
```

A future Sol controller is expected to reopen the exact authoritative sources and reason over the candidate set rather than treating rank 1 as an automatic scientific answer.

## 16. What the 20-query test covered

The successful final Top-5 set covered all of these adversarial questions:

1. why method development can reopen without erasing the earlier negative result;
2. whether the Maharatna-vs-ResNet failure remains true after reopening;
3. duplicate 077–080 G4 reconciliation and TAD/DLK role separation;
4. whether committed duplicate-number files should be renamed;
5. what Axion actually imports from NSDN;
6. whether locality proves explicit junction topology;
7. whether H6 distance/pooling should be the next primary optimization;
8. whether TAD weighting failure implies complementary fusion failure;
9. whether Retina class collapse was solved;
10. whether the N2-TRA scientific protocol is composite rather than one latest file;
11. whether R164 replaces all of R162;
12. what R166 adds;
13. why R169 placed the runner on HOLD;
14. which records form the accepted runner-governance chain;
15. whether protected medical execution opened after R171;
16. what R172 actually accepted and whether training remained closed;
17. whether Path FP32 may be rescued after official-test observation;
18. whether cross-programme Path comparisons are prospective superiority claims;
19. the strongest defensible Path claim and the morphology-learning limit;
20. whether a point-estimate AUROC win is sufficient for the reopened project objective.

Final Top-5 coverage:

```text
20 / 20 = 100%
```

## 17. Simulated branch desired-state test

Without mutating the shadow source branch, the pilot computed an alternate desired state representing a branch where Research 285 is absent from the research map.

Run:

```text
20260824T143502Z_executable_profile_4ff0d135
```

Observed:

```text
base desired state
3d8f8b165ff646e36e26c3999ee37ab23da1ddcb5e0122bc2efdb4f3b89d887e

alternate desired state
8200c98490212474eb4dab4f5f60b6bb0bbbfdbac0ec1435b56deacae15ea75e

different = true
CURRENT matches base = true
CURRENT matches alternate = false
```

### Decision

Branch identity itself does not need to be the primary freshness key.

The current effective research-map desired state detects meaningful branch/worktree differences directly.

Branch name/HEAD remain useful provenance but do not replace desired-state validation.

## 18. Crash-after-SAVE-before-CURRENT test

The pilot copied the healthy baseline database to an isolated crash database.

It then:

1. opened the crash database;
2. inserted one extra transient relation;
3. observed 39 graph edges;
4. explicitly issued `SAVE`;
5. received successful SAVE reply;
6. deliberately terminated the Python process with exit code 77 using `os._exit(77)`;
7. did **not** advance `CURRENT.json`.

Run:

```text
20260824T143514Z_executable_profile_79e24de2
```

Observed:

```text
CRASH_EDGE_COUNT_BEFORE_SAVE = 39
CRASH_SAVE_REPLY = True
CRASH_CHILD_EXIT = 77
```

This models a process dying after durable backend mutation but before publication of the new index generation.

## 19. Crash-state health detection

A fresh process reopened the saved crash database.

Run:

```text
20260824T143532Z_executable_profile_eac9d0b7
```

Observed:

```text
wanted_edges = 38
actual_edges = 39
missing = []
extra = ["transient-edge"]
desired_match = true
sync_current = false
```

This is a crucial result.

`CURRENT.json` still named the correct desired state, but graph read-back reconciliation detected that the durable backend did not exactly equal that desired state.

Therefore production health must not infer correctness from `CURRENT.json` alone.

A published generation is valid only when its backend state reconciles to the desired relation identity/state set.

## 20. Deterministic crash recovery

The damaged crash database was deleted/rebuilt solely from the tracked reviewed sidecars.

Run:

```text
20260824T143605Z_executable_profile_8fb37393
```

Observed:

```text
nodes = 52
edges = 38
wanted_edges = 38
actual_edges = 38
missing = []
extra = []
explicit SAVE = true
sync_current = true
```

A further completely fresh process reopened the recovered crash database.

Run:

```text
20260824T143650Z_executable_profile_141de975
```

Observed again:

```text
wanted_edges = 38
actual_edges = 38
missing = []
extra = []
desired_match = true
sync_current = true
```

No bespoke deletion of `transient-edge` was required.

The recovery operation is therefore:

```text
untrusted/stale derived DB
→ discard
→ validate authoritative docs + reviewed sidecars
→ deterministic rebuild
→ read-back reconcile
→ explicit SAVE
→ publish generation
```

This is simpler and safer than attempting journal-style repair of arbitrary graph mutations.

## 21. Final Git hygiene

Final shadow repository state remained:

```text
?? docs/architecture_research/_soma_map/
?? docs/axon_independent_architecture/_soma_map/
?? soma.project.json
```

The local database/runtime remained absent from Git status.

Shadow HEAD remained:

```text
e871350e436e2f5ef70b14c4dc9b2a0f08dccf55
```

Live Axon remained clean at the same HEAD.

No Axon commit or push was made.

## 22. Updated minimum production contract

Iteration 12 refines the hybrid design into this transaction model.

### 22.1 Durable tracked layer

```text
research Markdown
  authoritative scientific truth

reviewed sidecar
  canonical source-text hash
  exact locator
  reviewed semantic relations
  epistemic class
  lifecycle
  facets

portable manifest
  repository_uid
  research roots
  sidecar convention
  research-map schema
```

### 22.2 Local derived layer

```text
.soma/research-map/
  DESIRED.json
  CURRENT.json
  health.json / generation evidence
  index/
```

The local backend can be deleted at any time without losing scientific meaning.

### 22.3 Sync transaction

```text
1. resolve explicit attached repository
2. load portable manifest
3. enumerate configured research sources
4. canonicalize UTF-8 newlines
5. validate sidecars against canonical_text_sha256
6. derive complete desired-state hash
7. reconcile/build graph in local runtime
8. read back backend relation state
9. require desired/backend equality
10. explicitly persist backend (Lite: Redis SAVE)
11. verify persistence success
12. publish CURRENT atomically
13. optionally reopen/read-back for stronger acceptance gates
```

A failure before step 12 leaves the previously published generation authoritative for local index state.

A backend that changed before publication is detected by reconciliation and can be discarded/rebuilt.

## 23. Read/query contract

Queries must be read-only.

Before returning semantic candidates, query health must establish at minimum:

```text
sidecars current against authoritative sources
live desired-state hash == published CURRENT desired-state hash
backend relation state reconciles to desired state
backend readable
```

If not:

```text
report stale/degraded
return no claim of current semantic-map completeness
never rebuild as a side effect of query
```

The caller may then explicitly authorize or invoke an update/rebuild action.

This directly avoids the old `search_research` mutation defect found in Iteration 08.

## 24. Coverage and sync remain separate

This 14-source pilot intentionally has partial Axon corpus coverage.

It can therefore be:

```text
sync_current = true
coverage_complete = false
```

These are not contradictory states.

Production health should expose separately:

```text
eligible_sources
reviewed_material_sources
reviewed_no_material_sources
deferred_sources
unreviewed_sources
stale_sidecars

and

desired_relations
indexed_relations
missing_relations
extra_relations
published_generation
sync_current
```

The system must never imply full research coverage merely because the current subset is perfectly synchronized.

## 25. Graphiti/FalkorDB Lite disposition

### Graphiti

Graphiti remains a strong candidate for the derived semantic retrieval layer.

The Axon pilot recovered all 20 adversarial governing facts within Top-5 after one legitimate reviewed semantic-projection correction.

No Graphiti LLM performed scientific extraction or contradiction resolution.

The pilot again used:

```text
Sol-reviewed semantic relations
local BGE-small embeddings
NoLLM
NoCross
Graphiti hybrid search
```

### FalkorDB Lite

FalkorDB Lite earns **conditional continued use**, not unconditional production acceptance.

Positive evidence:

- explicit SAVE persists across independent process restarts;
- a 38-edge Graphiti graph reopened cleanly;
- repeated query runs were deterministic in this pilot;
- saved-but-unpublished extra graph state was detectable;
- deterministic rebuild recovered the damaged DB;
- recovered DB survived another fresh process reopen.

Required production rule:

- explicit SAVE is part of the adapter transaction contract;
- close-only persistence is forbidden;
- backend read-back reconciliation is mandatory;
- backend/runtime remains disposable.

A future backend replacement must be possible without changing tracked sidecars or research semantics.

## 26. Adversarial alternatives tested

### Alternative A — trust raw filesystem SHA

Rejected.

Same Git content on another clone can differ only by checkout newline representation and falsely appear stale.

### Alternative B — use relation-ID equality only for freshness

Rejected.

A sidecar statement changed while the same deterministic relation UUIDs remained present. Desired-state hashing detected the semantic drift; edge-ID equality did not.

### Alternative C — trust CURRENT without backend read-back

Rejected.

Crash DB had the correct CURRENT desired hash but contained one extra persisted relation.

### Alternative D — repair unexpected graph mutations in place

Not selected.

Because the graph is disposable and sidecars are durable, deterministic rebuild is simpler and safer.

### Alternative E — flatten scientific facets in the durable sidecar to satisfy FalkorDB

Rejected.

Backend storage limits belong in the projection adapter, not the durable semantic contract.

## 27. Remaining uncertainty

The pilot is deliberately bounded and does not yet prove:

- performance with all ~460 Axon records and potentially thousands of relations;
- multi-gigabyte or long-running FalkorDB Lite behavior;
- OS/power-loss behavior during Redis SAVE itself;
- simultaneous research-map writers across multiple processes;
- migration behavior across Graphiti/FalkorDB versions;
- semantic quality after a full historical Axon backfill;
- automatic discovery of which historical documents deserve zero-relation coverage sidecars;
- final operational UX for attach/update/rebuild/query health.

These are implementation/scale acceptance concerns, not unresolved conceptual architecture questions.

## 28. Final verdict

**PASS — THE HYBRID RESEARCH-MAP ARCHITECTURE IS READY FOR AN IMPLEMENTATION PLAN.**

The Axon stress pilot materially strengthened the design rather than merely confirming it.

It established that:

1. repo-local derived DB state is viable and stays Git-invisible;
2. tracked manifest + reviewed sidecars travel with the repository;
3. raw Markdown filesystem hashes must be replaced by canonical UTF-8/LF text hashes for portability;
4. structured scientific sidecars can project into Graphiti without constraining their durable schema to FalkorDB property types;
5. explicit Redis SAVE is required for FalkorDB Lite durability;
6. current desired-state identity detects semantic changes even when deterministic relation IDs do not change;
7. stale queries can fail closed without mutating state;
8. 20/20 difficult Axon questions recovered a governing relation within Top-5 after source-supported semantic refinement;
9. ranking was identical across two independent reopen/query processes;
10. branch-like desired-state changes are detectable without treating branch name as authority;
11. a crash after durable graph mutation but before publication is detectable;
12. deterministic rebuild restores the graph without repairing scientific meaning mechanically;
13. a fresh process reopens the recovered graph cleanly;
14. the live Axon repository remained untouched.

The next step should therefore be a **production implementation plan and acceptance matrix**, not another broad architecture-research cycle.

That plan should stage implementation so the tracked contract and read-only health/query surfaces land before any large historical backfill or automatic after-research update workflow.

No production source implementation was performed in this iteration. No old RAGFlow research runtime was reactivated or repaired. No Codex integration was introduced. No commit or push was performed.
