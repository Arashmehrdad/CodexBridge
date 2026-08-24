# Soma Knowledge Carry-Forward Research — Iteration 11

**Date:** 2026-08-24  
**Status:** COMPLETE — repo-local runtime and portable manifest architecture accepted with corrections and unresolved backend durability gate  
**Scope:** audit the owner-proposed per-repository database placement, Git-ignore policy, attach-time manifest, clone/move/worktree behavior, and interaction with Soma's existing repository discovery, ProjectScope, wiki and research-map findings

## 1. Owner proposal under audit

The owner proposed that each project's semantic database should live with that repository under a Soma-local folder, remain Git-ignored, and be described by a manifest when the project is attached to Soma.

The intended shape was approximately:

```text
repo/
├── .soma/                     local / disposable / ignored
│   └── research-map/
│       └── database/index
├── docs/.../_soma_map/        tracked reviewed sidecars
└── soma.project.json          tracked portable manifest
```

This iteration audits that deployment model against the live Soma implementation and Iterations 09-10.

No production implementation is authorized by this record.

## 2. Authoritative local evidence inspected

The audit inspected the following live Soma sources and accepted records at Soma HEAD `7e7450e08331aeed744867be955feb42149b18f4`:

```text
soma/repo_discovery.py
  SHA-256 a6847e2fc4d2c93d37aa3e1bef014130fbb8ebd3e8070a71fed4947c37bcb3f7

soma/repo_discovery_integration.py
  SHA-256 cbc40c775d0894d17bdff863e9e28a0b17a884e988961738bdbbaf0be49ac29d

soma/project_scope/models.py
  SHA-256 36b10e47ac1672a2009da5e1c2cadebd746c5735a17f21ee8f05872bf1b5d2a1

soma/project_scope/store.py
  SHA-256 ac7316b57fc5a51e07d9beb6e6d1086582ece6bdabb9d0a160b2e81ed8fdfa89

soma/knowledge_tools_integration.py
  SHA-256 c26c5ab887a6956a2dd53f60083015e719f68aebce70bb8473c9584dc23cb0b9

soma/repo_wiki.py
  SHA-256 02df88b7381ff4cb782fd71989c3522195621eab7302bda95846125e95cc2d8b

soma/repo_reader.py
  SHA-256 ea5fadd6380470140120b9049a8911c8b21699d77adb3c47b1015727e17dc03c

soma/tool_owned_paths.py
  SHA-256 5790e18498ac43ab319cce86ed25697d78541ddcbd7659ffd7f67ab01aeb65de

docs/MEMORY_REPOSITORY_ONBOARDING_1_RESULT_2026-08-01.md
  SHA-256 831c5cd48a15c3761b8c2243a3beb8c3ef0cec491025d31e63bf0b81f86136b7

docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md
  SHA-256 31a8388dde7dd5e346024d31e83d726f07305345278cee8e428c41d8404ca33a

Iteration 09
  SHA-256 50fb5c409bbe6f5df546f5d2df6e1f65d8f69676b71f85044a4c2df33dbf9703

Iteration 10
  SHA-256 1fe389078c6e8079890a8ea091f0160320e43b6be483c3dfde1a845c37c3a4fe
```

The audit also inspected the live Axon repository's `.gitignore` and ran one read-only Git ignore probe. Axon advanced concurrently during this audit and was clean at HEAD `085cef8da6ec4b47e37824883d75600eb36dbf8e`; no Axon write was made by this research.

Read-only probe:

```text
run: 20260824T132147Z_executable_profile_5de9816c
exit: 0

GIT_DIR=.git
EXCLUDE=.git/info/exclude
.git/info/exclude:7:.soma/wiki/    .soma/wiki/CURRENT.json
```

This proves that Axon's existing repo-local Soma wiki already uses the Git-local exclude mechanism even though Axon's tracked `.gitignore` does not contain `.soma/`.

## 3. High-level verdict

The owner's placement model is **accepted with corrections**.

Preferred boundary:

```text
TRACKED / PORTABLE
soma.project.json
research Markdown
reviewed research-map sidecars

LOCAL / DISPOSABLE
.soma/research-map/
semantic retrieval database/index
sync generation
health/read-back state
locks/backend-private files
```

The key corrections are:

1. ordinary repository discovery must remain read-only and must not silently create the tracked manifest;
2. a dedicated explicit research-map attach/adoption action creates or validates the manifest;
3. `.soma/` must become a formally reserved Soma runtime namespace in code, not merely an ignored directory;
4. the manifest must never contain local ProjectScope authority or absolute paths;
5. a portable repository identity is useful and distinct from Soma's local ProjectScope `project_id`;
6. tracked `_soma_map` sidecars should be excluded from the generated code wiki by default;
7. research-map queries must remain strictly read-only;
8. branch/worktree/clone changes are handled through desired-state hashes, not by trusting a persistent local DB blindly;
9. FalkorDB Lite cross-process durability remains unaccepted and must be tested before production backend selection.

## 4. Existing Soma precedent strongly supports `.soma/`

This is not a new repository-layout idea.

`RepoWikiService` already defines:

```text
repo_root/.soma/wiki/
```

as repository-local generated state.

The live Axon Git probe proved `.soma/wiki/` is currently excluded through `.git/info/exclude`.

Therefore extending the local namespace to:

```text
.soma/
├── wiki/
└── research-map/
```

is consistent with Soma's existing repository-local cache architecture.

The research database is the same class of object as the wiki in one important sense:

> it is useful local derived state whose loss must never imply loss of authoritative project knowledge.

The difference is that the research-map DB is semantically richer and therefore requires stronger rebuild/read-back validation.

## 5. Correction — `.soma/` cannot rely only on Git ignore

The current implementation does **not** globally reserve `.soma` in repository readers/indexers.

Observed facts:

- `repo_reader.py` blocks many runtime/cache directories, but `.soma` is not in `_BLOCKED_NAMES`;
- `repo_wiki.py` blocks many directories, but `.soma` is not in `_BLOCKED_DIRS`;
- `tool_owned_paths.py` does not list `.soma/` in `TOOL_OWNED_PREFIXES`;
- the normal Git-backed file listing respects `--exclude-standard`, so the current `.soma/wiki/` local exclude generally protects it;
- filesystem fallback paths do not gain that protection automatically from the Git candidate list.

A repo-local Graphiti/FalkorDB store may contain binary/backend files not covered by existing extension blocks.

Therefore production implementation must reserve:

```text
.soma/
```

at the Soma repository-access layer.

Required direction:

```text
repo_reader
  .soma = blocked runtime namespace

repo_writer
  generic repository mutation cannot edit .soma
  dedicated research-map runtime owns it

repo_wiki
  .soma = always excluded, including filesystem fallback

tool-owned classification/status
  .soma = Soma-owned local runtime
```

Git ignore remains useful defense-in-depth and worktree hygiene. It is not the security/isolation boundary.

## 6. Git-ignore policy

The read-only Axon probe confirms an existing safe precedent:

```text
.git/info/exclude
```

already contains:

```text
.soma/wiki/
```

A research-map attach action should idempotently ensure a root-local pattern equivalent to:

```text
/.soma/
```

through the repository's Git-local exclude file resolved by Git itself:

```text
git rev-parse --git-path info/exclude
```

This is preferable to silently editing tracked `.gitignore` because ordinary local Soma attachment should not create unrelated repository history.

A project may additionally choose to commit `/.soma/` to `.gitignore`, but that is optional repository policy, not required runtime correctness.

On a fresh clone, `.soma/` does not exist. The first explicit research-map attachment re-establishes the local exclude before creating runtime files.

## 7. Important distinction — repository discovery versus research-map adoption

Current automatic repository discovery is intentionally read-only:

```text
unknown repo_name
  -> scan trusted roots
  -> validate Git repository
  -> cache RepoConfig in memory
```

It does not create repository authority or tracked project files.

Canonical memory similarly requires a distinct explicit `memory_bind_repository` action when a discovered repository lacks ProjectScope authority.

Research mapping should follow the same discipline.

### Rejected behavior

```text
mere discovery of Git repo
  -> silently create soma.project.json
  -> silently create sidecar folders
  -> silently build semantic DB
```

This would turn repository discovery into an unexpected write path.

### Accepted behavior

```text
repository discovery
  read-only

explicit research-map attach/adopt
  validate/bind local project scope
  create/validate portable manifest
  establish local .soma exclusion
  initialize local runtime state
  inspect sidecar coverage
```

The existing canonical-memory binding action should not be overloaded to mean research-map adoption. They are separate product surfaces with different lifecycles.

## 8. ProjectScope is local attachment authority, not portable identity

This is the most important manifest correction.

`repository_identity_hash()` currently hashes:

```text
canonical absolute repository root path
```

and `memory_bind_repository` derives defaults such as:

```text
project_id  = proj_repo_<path-identity-prefix>
resource_id = res_repo_<path-identity-prefix>
project_key = <repo-name>-<path-identity-prefix>
```

Therefore moving or cloning the same Git project to another filesystem path can legitimately produce a different local ProjectScope identity.

That is correct for current machine authority, but it is unsuitable as tracked portable metadata.

The tracked manifest must **not** contain:

```text
runtime project_id
runtime resource_id
scope_generation
absolute repository root
repository_identity_hash derived from absolute path
local Graphiti/FalkorDB port/path
machine hostname
credentials
```

These remain local Soma state.

## 9. A tracked portable repository UID is justified

Iteration 10 introduced explicit cross-project references.

Using only current `repo_name` is insufficient for portable references because folder names/aliases may change across clones or machines.

A tracked manifest therefore benefits from one stable generated logical identity, distinct from ProjectScope.

Recommended name:

```text
repository_uid
```

Example:

```text
srepo_7b64...
```

Properties:

- generated once when the repository adopts the research-map feature;
- path-independent;
- committed with the repository;
- shared naturally by normal clones of the same logical project;
- never used as authorization for a write;
- used to identify cross-project research references and portable sidecar provenance.

External reference example:

```json
{
  "kind": "external_record",
  "repository_uid": "srepo_<NSDN>",
  "path": "docs/research/025_transformer_microbenchmark_final_report_result.md",
  "sha256": "..."
}
```

Runtime resolution remains:

```text
portable repository_uid
  -> currently attached trusted repo instance(s)
  -> exact ProjectScope/root validation
  -> exact path + source SHA validation
```

If more than one clone/worktree carrying the same UID is attached and no current instance is unambiguous, resolution must fail closed rather than pick one silently.

A fork that intends to become a distinct logical project would require an explicit future re-key operation. That is a lifecycle question, not an initial implementation requirement.

## 10. Revised portable manifest

The earlier sample manifest contained too much runtime implementation detail.

Recommended minimal tracked shape:

```json
{
  "schema": "soma.project.v1",
  "repository_uid": "srepo_<stable-generated-id>",
  "research_map": {
    "enabled": true,
    "schema": "soma.research-map.v2",
    "roots": [
      {
        "path": "docs/architecture_research",
        "sidecar_dir": "_soma_map",
        "include": ["*.md"]
      },
      {
        "path": "docs/axon_independent_architecture",
        "sidecar_dir": "_soma_map",
        "include": ["*.md"]
      }
    ]
  }
}
```

Deliberately absent:

```text
repo_name
runtime project_id
runtime_root
backend = graphiti
FalkorDB configuration
absolute paths
timestamps
current HEAD/branch
coverage counts
last sync state
```

`Graphiti` is an implementation detail. The durable repository contract should describe the research-map feature, not pin the retrieval engine forever.

The local runtime convention can remain fixed by Soma:

```text
.soma/research-map/
```

without repeating it in every tracked manifest.

## 11. Manifest validation requirements

Before adoption/sync, validate at minimum:

1. strict known schema version;
2. repository UID shape;
3. all research roots are repository-relative;
4. no absolute path, drive prefix, UNC path or `..` traversal;
5. no research root enters `.git` or `.soma`;
6. configured roots exist or are explicitly reported missing;
7. overlapping/nested roots cannot silently double-own one source;
8. include patterns are bounded and safe;
9. sidecar directory is relative to its research root;
10. sidecar directory cannot equal the source root itself;
11. manifest contains no secret/runtime fields;
12. source eligibility and sidecar eligibility are deterministic.

Malformed manifest degrades only the research-map feature. It must not make ordinary repository tools or continuation unavailable.

## 12. Sidecars remain tracked

The owner proposal does not change Iterations 09-10 on this point.

Reviewed sidecars must remain in Git because they preserve the semantic judgment needed to rebuild the local DB without reinterpreting historical research.

For each research root:

```text
docs/<research-root>/
├── 001_....md
├── 002_....md
└── _soma_map/
    ├── 001_....json
    └── 002_....json
```

The database is disposable.

The reviewed semantic projection is not.

## 13. Correction — sidecars should not inflate the generated code wiki

`repo_wiki.py` currently considers tracked/untracked non-ignored text/JSON candidates and has:

```text
MAX_SOURCE_FILES = 2000
```

A project such as Axon can eventually add hundreds of tracked `_soma_map/*.json` files.

Indexing those in the generated code wiki would:

- duplicate information the research-map layer already owns;
- increase scan/hash cost;
- pollute module/source navigation;
- move large projects unnecessarily toward the 2,000-file cap;
- cause wiki refresh churn after every semantic sidecar update.

Therefore `_soma_map/` should be a default wiki exclusion.

This exclusion is **wiki-specific**.

The research-map adapter and ordinary authorized repo reads must still be able to inspect the tracked sidecars.

## 14. Recommended local runtime layout

Backend-neutral local layout:

```text
.soma/
├── wiki/
└── research-map/
    ├── CURRENT.json
    ├── health.json
    ├── .sync.lock
    └── index/
        └── <backend-private state>
```

The stable public contract should talk about `index/`, not a `graphiti/` directory.

Possible `CURRENT.json` diagnostic fields:

```text
schema_version
repository_uid
bound_repository_identity_hash
desired_state_sha256
manifest_sha256
verified_sidecar_count
verified_relation_count
coverage_state
backend_name
backend_version
index_generation
sync_status
```

Unlike tracked sidecars, local timestamps are harmless here because this file is not portable scientific metadata.

`CURRENT.json` is a derived runtime pointer/receipt, not authority.

## 15. Clone behavior

A normal clone carries:

```text
soma.project.json                    yes
research Markdown                    yes
tracked _soma_map sidecars           yes
.soma/research-map/index             no
local ProjectScope binding           no
```

Then:

```text
clone
  -> explicit Soma research-map attach
  -> new local ProjectScope/root validation
  -> establish local /.soma/ exclude
  -> validate portable manifest + sidecars
  -> DB missing
  -> explicit rebuild action from reviewed sidecars
  -> read-back verify
  -> publish CURRENT.json
```

No scientific reinterpretation is required.

This is the strongest portability property of the design.

## 16. Repository move behavior

A repository directory may be physically moved together with an old `.soma/` directory.

Because current ProjectScope identity is root-path-derived, the move changes local repository identity even if Git content is identical.

Therefore local runtime must store the ProjectScope/root identity it was built under.

On attach/open:

```text
CURRENT.bound_repository_identity_hash
        !=
live ProjectScope repository identity
```

must cause:

```text
local DB = untrusted/stale derived state
```

Safe response:

```text
rebind current ProjectScope
validate tracked manifest + sidecars
rebuild or fully reconcile local index
```

Never silently reuse the old database merely because `.soma/` moved with the folder.

## 17. Branch switching and dirty worktrees

A repo-local ignored DB persists when Git branches change.

Tracked research documents and sidecars do not.

Therefore `branch` is useful diagnostic metadata but cannot be the semantic freshness key.

Use a deterministic **desired-state hash** derived from the current working-tree research-map contract, for example:

```text
manifest bytes/hash
+ ordered verified sidecar identities
+ each sidecar's exact source SHA
+ research-map schema/predicate registry version
```

The precise hash contract should be frozen before implementation.

On branch switch, sidecar edit, sidecar deletion, source edit or manifest edit:

```text
live desired_state_sha256
    !=
CURRENT.desired_state_sha256
```

means the local semantic index is stale.

HEAD and branch should still be recorded for diagnostics, but correctness is based on current verified content.

This also supports the owner's normal workflow where research documents may exist in an uncommitted worktree before a later selected-file commit.

## 18. Linked worktrees

A Git linked worktree may share logical repository history while having its own filesystem root and checked-out content.

The design naturally handles this if local runtime remains inside each worktree root:

```text
worktree A/.soma/research-map
worktree B/.soma/research-map
```

Each worktree receives its own local ProjectScope/root identity and desired-state hash.

The tracked `repository_uid` may be the same because both are instances of the same logical repository.

Git-local exclusion must be resolved using Git (`git rev-parse --git-path info/exclude`) rather than assuming `.git` is always a directory at `repo_root/.git`.

This avoids hard-coding ordinary-clone Git layout.

## 19. Query purity is a hard acceptance requirement

Iteration 08 found that the old `search_research` path was advertised as read-only but persisted context packets.

The new research-map architecture must explicitly prevent the same mistake.

### Read/query operations may

```text
read CURRENT/health
read graph/index
read sidecars
hash/validate sources
retrieve candidate relations
reopen exact source documents
report stale/partial/unavailable status
```

### Read/query operations may not

```text
create manifest
write sidecars
rebuild database
reconcile graph
advance CURRENT generation
repair stale state
change Git exclude
```

Those are explicit mutation actions:

```text
attach/adopt
update/sync
rebuild
repair/reconcile
```

If a query discovers stale state, it returns stale/degraded status and falls back to tracked sidecars/source retrieval where possible. It does not repair itself as a side effect.

## 20. Coverage health and sync health are separate

A large project may have a perfectly synchronized graph for all reviewed sidecars while historical coverage is still incomplete.

These are different dimensions.

Example:

```text
coverage
  eligible_sources      460
  reviewed              260
  unreviewed            200
  stale_sidecars          0

sync
  desired_relations     740
  graph_relations       740
  missing                 0
  extra                   0
  state                 current
```

The map is:

```text
sync-current
coverage-partial
```

That is useful and honest.

Do not label the entire feature `healthy` without exposing both dimensions.

## 21. Stale-source behavior

If a research Markdown changes after its sidecar review:

```text
sidecar.source.sha256 != live source SHA
```

that sidecar is stale.

A stale sidecar must not be silently restamped.

The desired graph state must no longer treat its old semantic relation as verified-current.

Until an explicit review/update occurs:

- coverage reports the stale source;
- graph sync health becomes stale if the DB still contains the old relation;
- query must not present the relation as verified current merely because Graphiti returns it;
- the exact Markdown remains authoritative and may be read directly.

## 22. Concurrency and stream interruption

The runtime needs two distinct write boundaries.

### Tracked semantic write

```text
research doc
sidecar
```

uses normal repository locking/hash-bound writes.

### Derived index write

```text
.soma/research-map/
```

uses a project-local research-map sync lock.

Recommended sync protocol:

```text
1. snapshot/validate manifest + sidecars + source SHAs
2. compute desired_state_sha256
3. acquire map sync lock
4. reconcile/build derived index against that exact desired state
5. read back relation identities/counts
6. recompute/check current desired state
7. if source changed during sync: do not publish current
8. otherwise atomically publish CURRENT.json
9. release lock
```

This mirrors the good part of Soma's wiki generation design: capture a source generation, do work, then verify that the source did not move before claiming freshness.

If the stream/process dies during index mutation:

- tracked sidecars survive;
- CURRENT does not advance;
- the next explicit sync can reconcile desired state idempotently;
- a full rebuild remains valid if backend state is corrupt.

## 23. Desired-state reconciliation remains required

Iteration 10's desired-state rule survives unchanged.

The local DB is a projection of all **currently valid reviewed sidecars**, not an append-only memory.

Sync compares:

```text
desired reviewed relation IDs
vs
actual Soma-owned derived relation IDs
```

and reconciles missing/removed/changed relations.

This is necessary for:

- branch switching;
- sidecar deletion;
- scoped supersession edits;
- source/sidecar repair;
- interrupted sync;
- backend recovery.

Do not adopt unknown graph content as reviewed scientific state.

## 24. Cross-project federation with per-repo DBs

The owner-preferred one-DB-per-repo model remains selected.

Cross-project relationships use portable external references in tracked sidecars.

At query time:

```text
Axon local DB
  -> returns external NSDN repository_uid + source path/SHA
  -> Soma resolves a currently attached trusted NSDN instance
  -> query/reopen NSDN map/source
  -> verify source SHA
  -> Sol reasons across both projects
```

No global graph merge is required.

This keeps:

- failure blast radius per repository;
- rebuild ownership per repository;
- coverage measurable per repository;
- cross-project evidence explicit rather than accidental semantic contamination.

## 25. Manifest must not become a new scientific authority

The tracked manifest is authoritative only for **portable Soma feature configuration/identity**.

It does not decide scientific truth.

Authority remains:

```text
research Markdown            scientific truth
reviewed sidecars             durable reviewed semantic projection
soma.project.json             project feature/configuration manifest
.soma/research-map/index      disposable retrieval projection
ProjectScope                  local runtime/write authority
continuation                  current re-entry state
```

These roles must stay distinct in documentation and APIs.

## 26. Security and leakage boundary

Repo-local semantic index state may contain derived text/embeddings from research.

Therefore `.soma/` must be excluded not only from Git history but from generic source packaging/indexing paths where practical.

Production review should check at minimum:

```text
Git add/status
repo_reader/list/search
repo_wiki scan + filesystem fallback
repo commit manifests
SSH/deployment packaging
archive/export tooling
secret scanners/backups if applicable
```

The research-map service itself may read/write `.soma/research-map/` through its dedicated internal API.

General repository tools should treat it as local runtime, not authored source.

## 27. Backend-neutrality survives the repo-local decision

The tracked manifest should not say:

```text
backend: graphiti
```

Graphiti is currently the selected retrieval candidate because the pilot achieved 100% Hit@5 on the 15-case NSDN benchmark.

But the portable contract is:

```text
reviewed semantic sidecars
  -> derived semantic retrieval index
```

not:

```text
repository format depends forever on Graphiti
```

Backend identity/version belongs in local runtime health/CURRENT state.

This preserves migration ability without changing research documents or reviewed sidecars.

## 28. Unresolved blocker — FalkorDB Lite persistence

Iteration 07 recorded an unresolved observation:

> one reopened FalkorDB Lite process appeared empty; cross-process persistence/flush needs deliberate testing.

The later sidecar benchmark proved deterministic graph reconstruction and idempotent duplicate writes **within the successful pilot workflow**, but it did not close the general cross-process persistence/crash-reopen question for a repo-local database.

Therefore this audit does **not** claim that:

```text
.soma/research-map/index = production-ready FalkorDB Lite database
```

That would be premature.

Before production backend acceptance, test:

1. clean close/reopen in a second process;
2. multiple sequential reopen cycles;
3. abrupt process termination after acknowledged writes;
4. stale/partial DB detection;
5. deterministic rebuild from tracked sidecars;
6. concurrent-reader/single-writer behavior;
7. database movement with repository path change;
8. measured startup/rebuild cost on an Axon-sized representative map.

Kuzu remains rejected/deprecated from the earlier Graphiti audit.

If FalkorDB Lite fails the durability gate, preserve the repo-local `index/` contract and change backend rather than changing the tracked research-map format.

## 29. Adversarial alternative — central global Soma DB

A central database under `D:\Services` or Soma's own runs directory could simplify process management.

It remains inferior for the current requirement because:

- project-local lifecycle becomes less obvious;
- backup/delete/rebuild blast radius grows;
- clones cannot self-describe their derived-state location;
- project isolation is weaker;
- cross-project contamination becomes easier;
- local cleanup becomes detached from repository cleanup.

Verdict:

**Reject central global semantic DB as the default.**

Central Soma may keep a lightweight registry mapping attached `repository_uid -> local repo instance/health`; it should not own the only semantic index.

## 30. Adversarial alternative — put sidecars inside ignored `.soma/`

This is attractive because all Soma files would be together.

It is rejected.

If sidecars live only inside `.soma/`, a fresh clone loses Sol's reviewed semantic judgments and must reinterpret historical research to rebuild them.

That violates the central recovery requirement.

Correct split:

```text
.soma/               disposable runtime only
tracked _soma_map/   reviewed rebuild material
```

## 31. Adversarial alternative — automatically rebuild on first query

This is convenient but recreates the architectural class of the Iteration-08 defect: a query that mutates state.

It also makes latency unpredictable and hides whether the user asked for a read or a rebuild.

Verdict:

**Reject automatic query-time repair/rebuild.**

A stale query may suggest/trigger a separate explicit action only when authorized.

## 32. Adversarial alternative — store local ProjectScope ID in manifest

This seems to make attachment easier but fails portability because ProjectScope identity currently derives from canonical absolute repository root.

Verdict:

**Reject.**

Use tracked `repository_uid` for portable logical identity and live ProjectScope for local authority.

## 33. Accepted attach lifecycle

Recommended future flow:

```text
NORMAL REPO DISCOVERY
  read-only
  no manifest write
  no DB build

EXPLICIT RESEARCH-MAP ADOPTION
  resolve trusted repo
  resolve/create local ProjectScope as required by its own action
  if soma.project.json absent:
      create reviewed/managed manifest with repository_uid
  validate research roots
  ensure /.soma/ in Git local exclude
  initialize .soma/research-map runtime
  compute coverage
  do not pretend historical bootstrap is complete

FIRST PROJECT BOOTSTRAP
  Sol reviews configured research corpus in staged batches
  write tracked sidecars
  explicit graph rebuild/sync
  verify desired state

EACH NEW RESEARCH ITERATION
  save authoritative research doc
  check exact source sidecar first
  Sol adjudicates carry-forward meaning
  write/update sidecar
  explicit incremental sync
  read-back verify
  advance CURRENT generation

FRESH CLONE / REBUILD
  attach
  validate manifest + sidecars
  explicit rebuild
  no scientific reinterpretation required
```

## 34. Generic per-repository architecture after this audit

```text
                         GIT-TRACKED / PORTABLE

                         soma.project.json
                    repository_uid + map roots
                                |
                                v
                     authoritative research docs
                                |
                      Sol semantic adjudication
                                |
                                v
                   reviewed _soma_map sidecars
            source SHA + facets + epistemic/qualifiers
        scientific + governance + provenance relationships
                                |
                        desired-state hash
                                |
                                v

                         LOCAL / IGNORED

                    .soma/research-map/
                 CURRENT + health + map lock
                                |
                                v
                    backend-private index
                     Graphiti candidate
                                |
                         semantic retrieval
                                |
                                v
                      exact source references
                                |
                                v
                     reopen tracked sources
                                |
                                v
                           Sol reasons

LOCAL AUTHORITY BESIDE THIS FLOW:
ProjectScope binds the current physical repository root.
It is not copied into the tracked manifest.
```

## 35. Required implementation gates

Before production activation, require explicit acceptance for:

### A. Manifest contract

- strict schema;
- portable `repository_uid`;
- safe research-root validation;
- no runtime/secret fields;
- clone/move behavior.

### B. Runtime namespace

- `.soma/` blocked from generic repo reads/writes/wiki fallback;
- local Git exclude idempotency;
- sidecars remain tracked/readable;
- `_soma_map` excluded from code wiki only.

### C. Query purity

- negative tests prove every research-map query is filesystem/DB read-only;
- stale queries never repair/rebuild.

### D. Desired-state synchronization

- deterministic relation IDs;
- idempotent repeated sync;
- deleted relation removal;
- source-sha stale rejection;
- source-change-during-sync detection;
- crash/resume behavior.

### E. Backend durability

- cross-process reopen;
- crash reopen/rebuild;
- single-writer locking;
- Axon-scale startup/rebuild timing.

### F. Portability

- clone to new root;
- move repo with old `.soma` present;
- branch switch;
- linked worktree;
- duplicate attached clones of same `repository_uid` fail closed when ambiguous.

## 36. Recommended next empirical research

The next test should combine the two remaining uncertainties rather than start production implementation.

Use the difficult Axon v2 slice proposed by Iteration 10 and place its derived index in a **disposable repo-local-style `.soma/research-map/` test root outside the real Axon worktree**.

Test:

1. portable manifest validation;
2. reviewed v2 sidecars for duplicate-number/composite-authority/cross-project cases;
3. fresh Graphiti/FalkorDB index build;
4. process close and reopen;
5. same adversarial natural-language queries after reopen;
6. simulated branch desired-state change;
7. interrupted/partial sync recovery;
8. deterministic full rebuild;
9. coverage/sync-health reporting.

Only after this passes should production Soma source implementation begin.

## 37. Final verdict

**ACCEPT THE OWNER'S ONE-LOCAL-DB-PER-REPOSITORY MODEL.**

The refined production boundary is:

```text
tracked repository manifest
  = portable research-map configuration + stable repository_uid

tracked research docs
  = scientific authority

tracked sidecars
  = reviewed rebuildable semantic mapping

repo-local .soma/research-map
  = disposable derived retrieval state

ProjectScope
  = current machine/root authority

Graphiti/FalkorDB
  = replaceable local retrieval backend, pending durability acceptance
```

The most important corrections are that `.soma/` must be protected in Soma itself, ordinary discovery must stay read-only, sidecars must not be hidden inside the ignored runtime directory, and no query may mutate/rebuild the map.

With those boundaries, the repo-local deployment model improves portability, failure isolation, clone recovery and project ownership without weakening the docs-as-authority architecture established in Iterations 09-10.
