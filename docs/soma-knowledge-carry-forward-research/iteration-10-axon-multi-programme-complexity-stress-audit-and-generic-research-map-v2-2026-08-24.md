# Soma Knowledge Carry-Forward Research — Iteration 10

**Date:** 2026-08-24  
**Status:** COMPLETE — Axon complexity stress audit; generic research-map v2 boundary selected  
**Scope:** stress-test Iteration-09's hybrid research-map contract against a much larger, multi-programme, multi-thread scientific repository and refine the contract for future projects that may become still more complex

## 1. Owner direction

The owner asked to inspect the Axon repository before freezing a future implementation design because Axon already contains two major research lanes and substantially more complicated scientific history than NSDN.

The purpose of this iteration is not to backfill Axon and not to modify Axon.

The purpose is to answer:

> Does the Iteration-09 `project -> lane -> research -> reviewed relations` mental model survive a repository with parallel programmes, duplicate research numbers, cross-project evidence transfer, composite authority, dataset-contamination boundaries, independent audits, incidents, terminal results and multiple simultaneous scientific threads?

Repository research documents remain authoritative. Graphiti remains derived/disposable. Sol/ChatGPT remains semantic adjudicator. Continuation remains unchanged and out of scope. Codex integration remains forbidden.

## 2. Repositories and live safety state

Axon registered repository:

```text
D:\Github\Axon_modelling
registered Soma name: axon_modelling
branch: master
HEAD at audit start: 09a2d95318236c682ee6145f7ef89755fbdcda7f
```

Live worktree already contained two unrelated modified files:

```text
src/axon_modelling/asg_g5/research168.py
tests/phase5/test_asg_g5_research168.py
```

They were not modified by this audit.

The audit used repository reads/searches and one read-only PowerShell filename analysis. No Axon source/document write, fit, scientific run, commit or push was performed.

## 3. Corpus scale

Two major research roots are present.

### 3.1 Main architecture/collaboration corpus

```text
docs/architecture_research/
284 Markdown research records
```

The corpus spans early architecture research through Research 285 and includes, among other things:

- spectral representation/mathematical contracts;
- patient-safe BUS-BRA phases;
- controls and comparator programmes;
- source reconciliation;
- Professor-guided programmes;
- reconstruction work;
- Retina/Pneumonia/Path transport and benchmark work;
- fixed-transform/wavelet/radial-MKL work;
- Android/deployment work;
- parametric-MKL/CUDA work;
- incidents, recovery records and terminal reports.

### 3.2 Independent architecture corpus

```text
docs/axon_independent_architecture/
176 Markdown research records
```

This corpus contains ASG G1-G5 work, including:

- G1/G2 scattering/locality studies;
- G3 relational/topology generations;
- G4 parallel TAD/DLK and later U3 work;
- G5 hierarchical-neuron, N2 and N2-TRA programmes;
- independent audits, protocol amendments, execution incidents, recovery records and terminal scientific results.

### 3.3 Total immediate stress corpus

```text
284 + 176 = 460 research Markdown records
```

This excludes ROADMAP/PROJECT_MEMORY, evidence JSON, code, external manuscripts, Android artifacts and other repository material.

Axon therefore represents a substantially harder long-horizon context-mapping workload than the 78-file NSDN corpus used for the first pilot.

## 4. Finding 1 — research number is not identity

A read-only filename audit found:

```text
architecture_research
  284 files
  284 numeric-prefix records
  duplicate numeric-prefix groups: 0

axon_independent_architecture
  176 files
  176 numeric-prefix records
  duplicate numeric-prefix groups: 6
```

The independent corpus contains these real collisions:

```text
077
  077_asg_g3_closeout_and_g4_evidence_integration_charter.md
  077_asg_g4_cross_lane_reset_and_dendritic_locality_kernel_charter.md

078
  078_asg_g4_dlk_s1_exact_mathematical_design_and_no_data_audit_contract.md
  078_asg_g4_tad1_candidate_family_prior_art_and_branch_selection.md

079
  079_asg_g4_dlk_s1_independent_no_data_mathematical_audit.md
  079_asg_g4_tad1_exact_mathematical_design.md

080
  080_asg_g4_dlk_s1_generated_source_implementation_contract.md
  080_asg_g4_tad1_independent_no_data_mathematical_audit.md

109
  109_asg_g4_u3_organcmnist_pre_member_launch_failure_and_recovery_authorization.md
  109_asg_g4_u3_organcmnist_train_stage_authorization.md

111
  111_asg_g4_u3_organcmnist_armed_preload_failure_recovery_authorization.md
  111_asg_g4_u3_organcmnist_one_test_event_authorization.md
  111_asg_g4_u3_organcmnist_pre_arm_mapping_parser_correction_and_reauthorization.md
```

Research 081 explicitly records that the G4 077-080 collisions arose because two scientifically legitimate design threads progressed in parallel before the numbering collision was noticed.

It preserves committed history and creates thread aliases `077A-080A` and `077M-080M` rather than renaming old files.

### Decision

Neither of these can be primary identity:

```text
research_number
lane + research_number
```

The durable identity must be source-bound.

Iteration-10 refines the identity model into two levels:

```text
logical_record_id
  deterministic from normalized repository-relative source path

record_version_id
  deterministic from logical_record_id + authoritative source SHA-256
```

The human Research number/title remains searchable metadata only.

A sealed source edit changes `record_version_id` and makes the existing reviewed sidecar stale until re-reviewed.

A source rename is treated as a new logical record unless an explicit reviewed rename/migration relation records the history. Research files should normally remain stable and not be renamed casually.

## 5. Finding 2 — a research repository is not a tree

The earlier convenient hierarchy was:

```text
project
  -> programme
    -> lane
      -> research
```

Axon proves that this is too rigid.

A single record may simultaneously belong to several scientific dimensions.

For example Research 081 is simultaneously:

- ASG-G4 programme governance;
- reconciliation of two parallel threads;
- TAD-1 primary-candidate selection;
- DLK-S1 nested-challenger disposition;
- duplicate-number provenance repair;
- historical/development-vs-confirmation dataset-boundary policy;
- future execution ordering.

Likewise Research 077 imports evidence from:

```text
ASG-G2
ASG-G3
main Axon Architecture Research
NSDN
```

A hard tree would force one artificial parent and lose the other dimensions.

### Decision — facets, not hierarchy

Research-map v2 uses optional **facets** for navigation/classification rather than identity or authority.

Recommended standard facets include:

```text
programme
thread
phase_or_generation
dataset
mechanism
record_role
evidence_surface
execution_stage
```

Example:

```json
{
  "facets": {
    "programme": ["ASG-G4"],
    "thread": ["G4-A", "programme-reconciliation"],
    "mechanism": ["TAD-1", "DLK-S1"],
    "record_role": ["reconciliation", "provenance-repair"],
    "evidence_surface": ["historical-development-boundary"]
  }
}
```

Facets are many-to-many and may gain new keys in future projects without changing record identity.

The adapter may maintain a recommended facet vocabulary, but the durable schema must permit additional reviewed facet keys rather than assuming all future research organization has already been invented.

## 6. Finding 3 — branch/thread identity is scientifically real

Research 081 proves that two parallel threads can exist inside one programme:

```text
G4-A / TAD-1
  primary next-model research
  tests cross-view complementarity + global weighting

G4-M / DLK-S1
  nested mechanism challenger
  tests internal weighting of B4 without adding new information
```

The important relationship is not merely chronology.

Research 081 freezes rules such as:

```text
TAD-1 = primary G4-A candidate
DLK-S1 = nested G4-M challenger

Do not merge both mechanisms before G4-A adjudication.
Do not use one branch's medical result to change the other branch's definitions.
```

Therefore thread/branch belongs in searchable facets and explicit governance/scientific relations, but not in record identity.

Future projects may have more than two parallel threads and nested challengers; no schema migration should be required.

## 7. Finding 4 — cross-project evidence transfer is real

The independent Axon corpus contains explicit NSDN references.

Repository search returned nine `NSDN Research` hits in the independent corpus, including Research 077's parent/evidence chain and direct methodological imports from NSDN Research 025, 034 and 035.

Research 077 distinguishes this carefully:

```text
NSDN supplies methodological/attribution primitives
not direct medical-model evidence
```

Examples include:

- transfer the primitive, not the literal module;
- separate functional jobs;
- use matched attribution before mechanism credit;
- repair coverage before architecture claims;
- stop optimizing a stage after the bottleneck moves.

### Decision — project-isolated graph with external reference stubs

One Graphiti database per project remains the preferred isolation boundary.

A local project's sidecar may explicitly reference another project's source record:

```json
{
  "kind": "external_record",
  "project": "NSDN",
  "path": "docs/research/025_transformer_microbenchmark_final_report_result.md",
  "sha256": "..."
}
```

The Axon Graphiti DB stores a local external-reference node/stub rather than merging all NSDN facts into Axon's DB.

If a future query materially depends on the external result:

```text
Axon retrieval
  -> external NSDN reference returned
  -> Sol explicitly queries/reopens NSDN map/source
  -> exact NSDN document verified
```

This provides cross-project knowledge without creating one global graph whose failures or namespace defects contaminate every project.

A later optional federation layer can query selected project DBs, but federation is a reasoning/navigation service, not a global authority store.

## 8. Finding 5 — current authority can be composite

A simple `latest record wins` rule is false in Axon.

Research 171 states:

```text
Effective runner contract:
  Research 168
  + Research 170 amendment

Independent acceptance records:
  Research 169
  Research 171

Effective scientific protocol:
  Research 162
  + Research 164
  + Research 166
```

Research 170 does not replace all of Research 168. It amends one provenance blocker while leaving the accepted scientific/runner architecture intact.

Likewise Research 091 in the main lane supersedes only Research 089's project-endpoint decision; it does not erase the negative scientific findings.

### Decision

`SUPERSEDES` alone is insufficient.

The map must represent authority/governance links including scoped amendments and acceptance.

Minimum governance predicate family should support concepts such as:

```text
GOVERNS
AMENDS
AUDITS
ACCEPTS
SUPERSEDES
RECONCILES
CLOSES
REOPENS
AUTHORIZES
PARKS
```

The exact vocabulary may grow only from reviewed real needs.

A composite authority is reconstructed from these explicit links rather than hidden in a special "latest" field.

Example conceptual graph:

```text
R168 --GOVERNS--> N2_TRA_RUNNER_CONTRACT
R170 --AMENDS-->  N2_TRA_RUNNER_CONTRACT
R169 --AUDITS-->  R168
R171 --ACCEPTS--> R170

R162 --GOVERNS--> N2_TRA_SCIENTIFIC_PROTOCOL
R164 --AMENDS-->  N2_TRA_SCIENTIFIC_PROTOCOL
R166 --AMENDS-->  N2_TRA_SCIENTIFIC_PROTOCOL
```

The source statements remain authoritative; the graph is only the reviewed map of those relationships.

## 9. Finding 6 — scope/contamination is part of scientific meaning

Research 081 explicitly distinguishes datasets already used for architecture design from possible fresh confirmation surfaces.

It marks:

```text
BUS-BRA
RetinaMNIST
PneumoniaMNIST
BreastMNIST
PathMNIST
```

as already having materially informed model choice or interpretation.

They may be historical-development/viability surfaces where permitted, but may not be described as independent confirmation of TAD-1.

It also records previously rejected independence candidates and states that PathMNIST official test is already terminal/consumed and must not be rerun for G4 selection or confirmation.

Research 285 similarly allows descriptive comparison with Research 209 but explicitly says no new paired superiority/inferiority claim was prospectively declared across the separately executed programmes.

### Decision — relation qualifiers

A semantic statement cannot always be represented by only:

```text
subject - predicate - object
```

Research-map v2 adds optional reviewed **qualifiers** that bound applicability without inventing another relation.

Examples:

```json
{
  "qualifiers": {
    "dataset": ["PathMNIST"],
    "evidence_role": ["historical-comparator"],
    "claim_limit": ["descriptive-only"],
    "test_state": ["official-test-consumed"]
  }
}
```

or:

```json
{
  "qualifiers": {
    "dataset": ["RetinaMNIST"],
    "evidence_role": ["historical-development"],
    "independent_confirmation": ["false"]
  }
}
```

Qualifiers are semantic restrictions and therefore belong on the reviewed relation/fact, not merely on the source document.

## 10. Finding 7 — epistemic class must be preserved

Research 153 explicitly labels statements as:

```text
OBSERVED
INFERENCE
HYPOTHESIS
DESIGN REQUIREMENT
```

This is exactly the distinction a long-horizon map must preserve.

Without it, a future retrieval could incorrectly surface:

```text
"target-conditioned over-specialization caused Breast failure"
```

as established fact even though Research 153 clearly labels that explanation a hypothesis.

### Decision — epistemic_class

Every material reviewed semantic assertion should carry an epistemic class.

Initial recommended vocabulary:

```text
observed
inference
hypothesis
decision
requirement
constraint
interpretation
```

`unknown` may be used only when the source does not support a tighter classification and Sol cannot safely infer one.

The vocabulary is expandable, but retrieval must never silently promote `hypothesis` into `observed`.

This field is independent of lifecycle.

Example:

```text
epistemic_class = hypothesis
lifecycle        = current
```

means a current live hypothesis, not a confirmed fact.

## 11. Finding 8 — record role matters for retrieval

Axon research records include materially different roles:

```text
charter
research plan
mathematical design
protocol
implementation contract
implementation review
independent audit
authorization
incident
recovery authorization
scientific result
terminal result
reconciliation
closeout
owner decision
```

A future query such as:

> Did N2-TRA scientifically fail?

must not treat an implementation incident or prelaunch audit as equivalent to a terminal scientific result.

### Decision

`record_role` is a standard facet.

Retrieval may use it for reranking/filtering, but source content and semantic relations still govern the answer.

## 12. Revised sidecar model — `soma.research-map.v2`

Iteration 09's sidecar principle survives Axon, but the record becomes facet-aware and authority-aware.

Conceptual minimum:

```json
{
  "schema": "soma.research-map.v2",
  "source": {
    "path": "docs/.../081_....md",
    "sha256": "...",
    "record_id": "doc_...",
    "record_version_id": "docv_...",
    "label": "Research 081",
    "title": "..."
  },
  "review": {
    "state": "reviewed",
    "materiality": "material",
    "reviewed_by": "Sol"
  },
  "facets": {
    "programme": ["ASG-G4"],
    "thread": ["G4-A", "programme-reconciliation"],
    "record_role": ["reconciliation"],
    "mechanism": ["TAD-1", "DLK-S1"]
  },
  "relations": [
    {
      "relation_id": "rel_...",
      "relation_class": "scientific",
      "epistemic_class": "decision",
      "subject": {...},
      "predicate": "NARROWS",
      "object": {...},
      "statement": "...",
      "lifecycle": "current",
      "qualifiers": {...},
      "locator": {
        "anchor": "...",
        "anchor_sha256": "...",
        "line_start": 123
      },
      "supersedes": []
    }
  ]
}
```

The durable sidecar still does not contain Soma runtime `project_id`, machine path or Graphiti database identity.

Those belong to the adapter/runtime binding.

## 13. Three relation classes

Axon supports separating relation semantics into three broad classes.

### 13.1 Scientific

Scientific/mechanistic meaning:

```text
SUPPORTS
FALSIFIES
QUALIFIES
NARROWS
LIMITS
MOTIVATES
REQUIRES
ALLOWS
FORBIDS
CONSTRAINS
PRESERVES
```

These were already sufficient for the 30-fact NSDN pilot and remain useful in Axon.

### 13.2 Governance / authority

How records/programmes control one another:

```text
GOVERNS
AMENDS
AUDITS
ACCEPTS
SUPERSEDES
RECONCILES
CLOSES
REOPENS
AUTHORIZES
PARKS
```

These are necessary for Axon's composite contract/protocol and parallel-thread history.

### 13.3 Provenance / transfer

Why a later record uses prior work:

```text
DERIVES_FROM
INFORMED_BY
IMPORTS_EVIDENCE_FROM
REPRODUCES
REPLAYS
```

This class is especially important for Axion <-> NSDN transfer because methodological influence must not be mistaken for direct medical evidence.

### Predicate policy

The classes are stable. The predicate registry is **versioned but extensible**.

A new predicate may be added when a real reviewed research relationship cannot be represented faithfully with the existing vocabulary.

Do not generate generic `RELATED_TO` edges merely to increase graph density.

## 14. Node/reference types

A relation endpoint should minimally distinguish:

```text
concept
source_record
external_record
programme_or_contract_object
```

Examples:

```text
concept:
  generic upstream dendritic gating

source_record:
  current repository Research 081

external_record:
  NSDN Research 025

programme_or_contract_object:
  N2-TRA scientific protocol
```

This is enough to represent composite authority without creating a special-case bundle database.

For example:

```text
R162 GOVERNS N2_TRA_SCIENTIFIC_PROTOCOL
R164 AMENDS  N2_TRA_SCIENTIFIC_PROTOCOL
R166 AMENDS  N2_TRA_SCIENTIFIC_PROTOCOL
```

## 15. Sidecar coverage is mandatory even when no material relation exists

Axon's scale exposes an ambiguity that NSDN did not make urgent.

If a 460-record corpus has no sidecar for Research X, that could mean:

```text
not reviewed yet
```

or:

```text
reviewed; nothing material to carry forward
```

Those states must not be conflated.

### Decision

Every eligible research document eventually receives a coverage sidecar/state.

At minimum:

```text
review.state = reviewed
materiality  = material
```

or:

```text
review.state = reviewed
materiality  = none
relations    = []
```

A deliberately deferred source receives:

```text
review.state = deferred
reason       = ...
```

Absence of a sidecar means **unreviewed/unmapped**.

A source-SHA mismatch means **stale** and is derived mechanically; it is never silently restamped.

## 16. Coverage manifest and health

A project map needs a mechanically generated coverage manifest, not another authority document.

Suggested health surface:

```text
eligible_sources
reviewed_material
reviewed_empty
deferred
unreviewed
stale_sidecars
verified_relations
graph_relations
missing_graph_relations
extra_graph_relations
unresolved_external_refs
last_verified_generation
```

Important rule:

```text
map health may be partial
research itself must not be blocked
```

If only 250/460 Axon records have been reviewed, retrieval remains useful but must disclose partial coverage rather than pretending the map is complete.

## 17. Massive-project bootstrap strategy

A 460-record project should not require a blind chronological reread before the map becomes useful.

Recommended bootstrap order:

### Tier A — current controlling frontier

Map first:

- current programme charters;
- effective protocols/contracts;
- latest independent audits;
- current terminal results;
- current explicit HOLD/forbidden/reopen boundaries.

For current Axon this would prioritize the active ASG-G5/N2-TRA frontier and its controlling parent chain rather than beginning at Architecture Research 01.

### Tier B — terminal scientific findings and negative constraints

Backfill:

- terminal positives/negatives;
- mechanism falsifications;
- no-rescue boundaries;
- transfer limits;
- comparator baselines still governing current work.

### Tier C — programme reconciliation / cross-lane bridges

Map records such as Research 077/081 that explain how older programmes influence newer ones.

### Tier D — historical implementation/audit/incident detail

Review remaining records. Many may validly receive `materiality = none` for long-horizon scientific carry-forward or only one governance/provenance link.

This staged process yields useful coverage early while retaining a path to complete audited coverage.

## 18. Incremental maintenance after bootstrap

The owner's mental model remains correct, with the v2 refinements.

For each project:

```text
one-time bootstrap
  -> discover eligible research roots
  -> review source records in bounded programme batches
  -> produce coverage sidecars
  -> build project Graphiti DB
  -> verify map/graph coverage
```

Then after each new research iteration:

```text
1. authoritative research doc is saved/sealed
2. existing exact-SHA sidecar is checked first
3. if missing/stale, Sol adjudicates material carry-forward relations
4. sidecar is written and hash/anchors verified
5. Graphiti desired-state sync runs
6. graph read-back verifies relation identities/counts
7. coverage generation advances
```

This directly addresses stream interruption.

If a cut occurs after step 1:

```text
doc exists
sidecar absent
=> review/sync still pending
```

After step 4:

```text
doc + sidecar valid
graph generation behind
=> graph sync only
```

Repeating the sidecar generation for an already exact reviewed source must be idempotent, and repeating graph sync must not duplicate relations. Iteration 09 already demonstrated these properties empirically on the 30-fact NSDN graph.

## 19. Desired-state graph reconciliation

Incremental upsert alone is insufficient when a source changes or a sidecar relation is intentionally removed.

The adapter should treat all verified sidecars as the **desired derived graph state** for that project.

Periodic or post-update reconciliation compares:

```text
desired relation IDs from verified sidecars
vs
actual derived relation IDs in Graphiti
```

Then:

- missing derived relations are inserted;
- exact matching relations remain unchanged;
- derived relations no longer present in the reviewed desired set are removed/replaced;
- unknown/non-Soma graph material must not be silently adopted into reviewed state.

Because Graphiti is disposable, a full rebuild remains a valid recovery path.

## 20. Retrieval pipeline refined by Axon

Simple top-k semantic retrieval is not enough when authority is composite.

Recommended future query flow:

```text
natural-language research question
        |
        v
Graphiti hybrid semantic candidates
        |
        v
bounded one-hop authority/provenance expansion
  AMENDS / AUDITS / ACCEPTS / SUPERSEDES
  RECONCILES / GOVERNS / CLOSES / REOPENS
        |
        v
facet/qualifier-aware reranking
        |
        v
candidate source references
        |
        v
verify current source SHA + reopen exact docs
        |
        v
Sol reasons from source evidence
```

Do not use Graphiti `invalid_at` as the definition of current scientific truth.

Do not hide historical/falsified results automatically: a current question may specifically require them.

Use reviewed sidecar lifecycle/governance plus source verification.

## 21. Cross-project query behavior

If a retrieved Axon relation points to an NSDN external reference:

```text
Axon graph returns external stub
        |
        v
Soma resolves registered NSDN project if available
        |
        v
query NSDN map or reopen exact NSDN source
        |
        v
Sol evaluates whether the transfer is methodological,
scientific, historical or merely contextual
```

No automatic global cross-project semantic merging is required.

This keeps project failures isolated while allowing explicit science transfer.

## 22. Adversarial alternative — one global graph

A plausible alternative is one shared Graphiti graph containing all projects, programmes and threads.

Axon makes this less attractive.

Advantages:

- direct cross-project traversal;
- no explicit federation step.

Risks:

- namespace/full-text filtering already showed a defect in the FalkorDB pilot;
- one project can contaminate candidate retrieval for another;
- rebuild/failure blast radius grows;
- per-project coverage/health becomes harder to prove;
- scientific project isolation is weakened;
- cross-project similarity can be mistaken for authority or direct evidence.

Verdict:

**Reject one global graph as the initial architecture.**

Use one DB per project plus explicit external-reference/federated resolution.

## 23. Adversarial alternative — rigid programme/lane hierarchy

A rigid hierarchy is simpler to visualize but fails real Axon cases:

- records belong to multiple scientific dimensions;
- G4 has parallel A/M threads;
- main-lane evidence and NSDN both inform independent Axon work;
- dataset/evidence-surface constraints cut across programme boundaries;
- composite authority is not a single parent chain.

Verdict:

**Reject hierarchy as semantic identity.**

Keep hierarchy-like values only as optional facets/navigation views.

## 24. Adversarial alternative — map only records with material facts

This saves files but makes coverage unknowable.

On a 460-record corpus, a missing sidecar could mean either:

- never reviewed;
- deliberately judged irrelevant.

Verdict:

**Reject material-only sidecar presence as coverage semantics.**

Every eligible record eventually needs explicit reviewed/materiality state.

## 25. What remains deliberately out of the sidecar

Do not copy entire research reports into sidecars.

Do not persist:

- full metrics tables unless a metric itself is a material carry-forward assertion;
- every code/source hash mentioned by a report;
- every run ID;
- every implementation function/class;
- every parent link mechanically;
- continuation state;
- wiki structure;
- Graphiti-generated summaries;
- runtime `project_id`;
- local absolute paths;
- credentials or secrets.

The sidecar is a **reviewed semantic index**, not a second research report.

## 26. Recommended v2 predicate discipline

The map should prefer a small precise vocabulary over graph density.

Do not create:

```text
RELATED_TO
SIMILAR_TO
MENTIONS
```

unless a future concrete use case proves such edges carry meaningful research value.

A relation should answer a future question such as:

- what falsified this mechanism?
- what constraint still governs it?
- what later record narrowed rather than erased the result?
- what record amends the effective protocol?
- what dataset is only historical-development evidence?
- what external project supplied this methodological primitive?

If a link cannot plausibly help such a decision, it probably does not belong in the reviewed map.

## 27. Axon-specific examples the v2 model must represent

### 27.1 Duplicate-number parallel threads

```text
source-path 077A
  facet programme=ASG-G4
  facet thread=G4-A

source-path 077M
  facet programme=ASG-G4
  facet thread=G4-M

R081 RECONCILES both
R081 selects TAD-1 primary and DLK-S1 nested challenger
```

No identity collision occurs because path/version identities differ.

### 27.2 Scoped supersession

```text
R091 REOPENS project endpoint decision from R089
R091 PRESERVES R089 tested negative results
```

This prevents a future query from treating the reopened objective as erasure of the negative experiment.

### 27.3 Composite protocol

```text
R162 GOVERNS N2-TRA protocol
R164 AMENDS protocol determinism
R166 AMENDS full-owner fold rule
R163 AUDITS R162
R165 AUDITS R164
R167 AUDITS R166
```

No "latest document" shortcut is required.

### 27.4 Cross-project methodological transfer

```text
NSDN R025 INFORMS branch-local/late-integration primitive
NSDN R034 INFORMS functional-job separation
NSDN R035 INFORMS matched attribution

Axon R077 IMPORTS_METHOD_FROM those sources
```

The relation is methodological, not direct medical performance evidence.

### 27.5 Dataset evidence boundary

```text
PathMNIST
  official test consumed
  historical/descriptive comparison allowed
  not fresh independent G4 confirmation
```

This is represented with qualifiers and explicit constraints rather than one generic dataset tag.

## 28. Generic architecture after Axon audit

```text
                        AUTHORITATIVE
                 repository research documents
                 path + source SHA + exact locator
                              |
                              v
                         Sol / ChatGPT
                    semantic adjudication
                              |
                              v
          DURABLE REVIEWED RESEARCH-MAP SIDECARS v2
             source/version identity + coverage state
             facets + epistemic class + qualifiers
             scientific/governance/provenance relations
                              |
                    verify/reconcile desired state
                              v
                 PROJECT-ISOLATED GRAPHITI DB
             hybrid semantic + graph candidate retrieval
                              |
                   one-hop authority expansion
                              v
                    source references returned
                              |
                              v
                 reopen exact authoritative docs
                              |
                              v
                       Sol reasons/decides
```

Cross-project references remain explicit stubs/federated lookups rather than automatic graph merging.

## 29. What Axon changes from Iteration 09

Iteration 09 remains valid on:

- docs as authority;
- reviewed rebuildable sidecars;
- Graphiti as disposable retrieval;
- source SHA/anchor verification;
- interruption-safe idempotent update;
- one Graphiti DB per project;
- small controlled semantic predicate vocabulary.

Iteration 10 extends/corrects it with:

1. source-path/version identity rather than research number;
2. facets rather than a rigid programme/lane hierarchy;
3. explicit branch/thread facets;
4. governance/authority relations for composite contracts;
5. provenance/transfer relations for cross-project evidence;
6. relation-level qualifiers for dataset/claim applicability;
7. epistemic classification (`observed`, `inference`, `hypothesis`, etc.);
8. explicit empty/deferred sidecars for provable coverage;
9. desired-state graph reconciliation;
10. bounded authority expansion after semantic retrieval;
11. explicit external-project stubs/federation rather than one global graph.

## 30. Implementation implications

No implementation is authorized by this research record.

If implementation is later approved, the first implementation should target a **small general adapter contract**, not Axon-specific programme logic.

It should not contain hard-coded knowledge of:

```text
ASG
G4
G5
TAD
DLK
N2
N2-TRA
Professor programme
MedMNIST
```

Those are sidecar facets/content.

The adapter should understand only:

- eligible research roots;
- source/path/hash identity;
- sidecar validation;
- relation classes/predicate registry;
- facets/qualifiers;
- coverage health;
- project DB binding;
- Graphiti sync/reconcile/read-back;
- external project reference resolution;
- source reopen/verification.

That is the future-proof boundary.

## 31. Recommended next research

Before production implementation, the next highest-value research is a **scaled Axon bootstrap/acceptance pilot**, not another schema discussion.

It should avoid mapping all 460 records immediately.

Select a deliberately difficult representative slice containing:

- duplicate-number G4-A/G4-M records;
- Research 081 reconciliation;
- one scoped reopen/supersession case such as R089/R091;
- N2-TRA composite protocol/runner chain R162-171;
- one terminal main-lane result such as R285;
- one cross-project NSDN methodological import;
- one dataset-contamination/fresh-confirmation boundary.

Build reviewed v2 sidecars for that slice and create an Axon pilot DB.

Then ask adversarial natural-language questions that require:

- distinguishing duplicate IDs;
- reconstructing composite authority;
- differentiating hypothesis from observed evidence;
- respecting historical-development vs independent-confirmation scope;
- carrying a negative finding through a later reopen;
- following a cross-project methodological reference without treating it as direct evidence.

Only if that pilot passes should a full 460-record staged backfill and production adapter be planned.

## 32. Iteration-10 verdict

**THE ITERATION-09 HYBRID APPROACH SURVIVES AXON, BUT THE DATA MODEL MUST BE A FACETED RESEARCH GRAPH RATHER THAN A PROJECT/LANE TREE.**

Axon demonstrates that future-safe research continuity requires:

```text
source-bound identity
+ explicit coverage
+ scientific relations
+ governance/authority relations
+ provenance/transfer relations
+ epistemic classification
+ claim qualifiers
+ project-isolated graphs
+ explicit cross-project federation
```

The central authority rule remains unchanged:

> Graphiti retrieves candidate context. Reviewed sidecars preserve Sol's semantic mapping. Repository research documents remain the only scientific authority.

The design now handles existing Axon complexity without encoding Axon-specific logic and should therefore tolerate future projects with additional parallel programmes/threads without requiring a fundamental schema redesign.
