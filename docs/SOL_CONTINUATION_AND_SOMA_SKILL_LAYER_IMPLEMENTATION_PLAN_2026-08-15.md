# Sol Semantic Continuation + Soma Portable Skill Layer - Implementation Plan

Date: 2026-08-15  
Status: FINAL IMPLEMENTATION AUTHORITY - final audit incorporated; implementation requires execution-thread authorization  
Repository: `D:\Github\Soma`  
Planning branch observed: `lane/memory-integration-foundation-1`  
Initial planning HEAD observed: `bb551744824fd7abbac02441f901b543bac33d7f`  
Final audit/consolidation HEAD observed: `3a078706c5dd86cab8576ba5e8c0e5feb4082b1c`  

## 1. Purpose

This plan converts the final research from the Sol-agentic-loop realignment track into a staged implementation programme.

It combines two related but independent capabilities:

1. **Sol semantic continuation** - let normal Sol/ChatGPT recover enough durable external context to continue its own reasoning after a fresh Chat, interruption, compaction, or surface change without making Soma a second reasoning agent.
2. **Soma portable Skill layer** - let normal Sol discover and load reusable Agent Skills from a durable Soma-owned library, while keeping Skill packages portable to native ChatGPT/Work/Codex Skill surfaces where available.

The implementation must preserve the central architecture:

```text
Sol / ChatGPT = reasoning agent
Soma          = tools + durable mechanical truth + execution + retrieval
```

Soma must not become a semantic planner, next-step engine, hidden Skill router, or owner of model reasoning.

---

# 2. Research authority

Implementation must follow the later conclusions, not earlier superseded candidates.

Primary continuation authority:

```text
docs/sol-agentic-loop-realignment-research/iteration-30-final-synthesis-minimal-sol-semantic-reentry-2026-08-15.md
docs/sol-agentic-loop-realignment-research/iteration-31-repository-proof-run-idempotency-and-effect-linking-2026-08-15.md
```

Primary Skill-layer authority:

```text
docs/sol-agentic-loop-realignment-research/iteration-32-soma-skill-layer-current-ecosystem-and-baseline-2026-08-15.md
docs/sol-agentic-loop-realignment-research/iteration-33-normal-chat-skill-discovery-progressive-loading-and-gateway-boundary-2026-08-15.md
docs/sol-agentic-loop-realignment-research/iteration-34-skill-revisions-vs-continuation-authority-boundary-2026-08-15.md
docs/sol-agentic-loop-realignment-research/iteration-35-skill-script-execution-and-authority-boundary-2026-08-15.md
docs/sol-agentic-loop-realignment-research/iteration-36-skill-library-storage-revision-and-index-authority-2026-08-15.md
docs/sol-agentic-loop-realignment-research/iteration-37-skill-public-gateway-lifecycle-and-normal-chat-plan-integration-2026-08-15.md
docs/sol-agentic-loop-realignment-research/iteration-38-adversarial-attack-skill-identity-drift-trust-and-public-semantics-2026-08-15.md
docs/sol-agentic-loop-realignment-research/iteration-39-real-workflow-pressure-test-soma-skill-layer-2026-08-15.md
```

Supporting repo-backed proof:

```text
TaskStore public/shared transaction seam
Task controller_request_id + request_hash replay pattern
Task durable-run backend reserved_run_id pattern
Workflow child-run pre-reservation pattern
RunStore / JobManager durable launch and recovery model
operation-lock ordering and duplicate-active behavior
ParallelGroupStore as a distinct group authority
current public gateway inventory + public tool metadata authority
current config external-root precedents
```

Final audit incorporated into this plan:

```text
docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_FINAL_AUDIT_2026-08-15.md
```

The audit remains preserved as evidence, but this updated plan is now the single implementation authority. Historical Iterations 16 and 18-23 remain research history only where contradicted by Iterations 24-31 and the final audit.

---

# 3. Non-negotiable architecture laws

## 3.1 Sol remains the only normal reasoning head

Do not introduce into the normal path:

```text
LocalAgent semantic routing
Supervisor semantic planning
second-model Skill classification
automatic next-step selection
reason / act / observe persisted reasoning phases
reasoning leases
single-writer reasoning locks
semantic workflow DAGs
```

Optional specialist/provider reasoning infrastructure may remain available only under its existing explicit boundaries. It is not part of this implementation.

## 3.2 Machine-owned facts may be structured; model semantics stay free-form

Structured mechanical facts are appropriate:

```text
run_id
task_id
controller_request_id
request_hash
contract_revision_id
skill_package_hash
state_version
status
timestamp
content hash
```

Do not require Sol to reliably serialize cognition into fields such as:

```text
decision_basis[]
next_reasoning_step
incorporated_evidence[]
source_frontier[]
reasoning_phase
pending_action
semantic source roles
```

## 3.3 Continuation is semantic re-entry, not exact hidden runtime resume

Soma does not own ChatGPT's internal sampling/session state. It therefore promises a durable re-entry bundle, not exact continuation of hidden model state.

## 3.4 Skills are guidance, not capability

A Skill may teach Sol how to work. It cannot grant repository, Task, Run, SSH, Cloudflare, Docker, provider, secret, deployment, or other authority.

Bundled scripts are inert package resources until Sol explicitly routes execution through an existing Soma execution authority.

## 3.5 Continuation and Skills are separate authorities

Continuation stores:

```text
owner/controller contract
Sol handoff
durable effect lineage
```

Skill library stores:

```text
portable Skill package revisions
current library revision pointers
package provenance / identity
```

Do not add `continuation_skill_state` in v1.

## 3.6 Existing effect authorities remain canonical

Task state comes from TaskManager/TaskStore.
Run/process state comes from RunStore/JobManager.
Repository state comes from Git/repository inspection.
Remote state comes from the remote provider/host.
Continuation links do not copy or replace those truths.

---

# 4. Target architecture

```text
                         Sol / ChatGPT
                              |
         +--------------------+--------------------+
         |                    |                    |
         v                    v                    v
 continuation_query       skill_query        existing Soma tools
 continuation_action      skill_action       Task / Run / repo / SSH / ...
         |                    |
         v                    v
 continuation store      portable Skill library
         |                    |
         +---- mechanical ----+
               independence
```

Tracked durable effect path:

```text
Sol
 -> existing Task/Run start
    + optional continuation_context_ref
 -> validate current contract revision AND open continuation lifecycle
 -> reserve canonical effect identity
 -> persist continuation origin link durably
 -> commit
 -> launch through existing executor
```

Skill use path:

```text
Sol decides a reusable workflow may help
 -> skill_query.search(...)
 -> Sol chooses zero/one/many results
 -> skill_query.get(skill_ref)
 -> Sol follows free-form SKILL.md
 -> skill_query.resource(...) only if needed
 -> actual effects still use existing Soma tools
```

No Skill router sits between Sol and the library.

---

# 5. Delivery strategy

Use small independently accepted stages. Do not give one worker the whole plan as a single implementation task.

Each numbered implementation stage must end in exactly one state:

```text
ACCEPTED
BLOCKED
FAILED
```

If the repo differs materially from the assumptions recorded here, stop the stage and report the discrepancy. Do not silently redesign the architecture inside an implementation batch.

No push unless separately authorized.
No Codex/provider/subagent use is authorized by this plan; existing owner gates remain in force.
Never touch:

```text
docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md
```

unless the owner separately and explicitly authorizes that exact file.

---

# 6. Dependency graph

```text
F0 authority/preflight
 |
 v
F1 single-Run logical request idempotency
 |
 +-----------------------------+
 |                             |
 v                             v
C1 continuation persistence    S1 Skill library foundation
 |                             |
 v                             v
C2 continuation service        S2 skill_query
 |
 v                             v
C3 public continuation         S3 skill_action + replay/CAS
 |
 v                             |
C4 Task effect linking         |
 |
 v                             |
C5 direct single-Run effect linking |
 |                             |
 +--------------+--------------+
                |
                v
             I1 integrated normal-Chat acceptance
                |
                v
             I2 rollout / documentation

Optional only after measurement:
A1 native Skill/Plugin export adapter
A2 browser/manual Skill picker

Explicitly outside this programme:

```text
parallel-group logical request idempotency
project-local automatic Skill discovery/ingestion
native Skill synchronization
```

Skill implementation does not depend on continuation persistence.
Continuation correctness does not depend on Skills.
The recommended implementation order is still sequential to minimize worktree collisions.

---

# 7. Phase F0 - Authority freeze and implementation preflight

## Goal

Create a clean implementation starting point without rewriting research history.

## Required actions

1. Inspect current branch, HEAD, worktree, active durable runs, and repository locks.
2. Confirm no unrelated source work would be overwritten.
3. Read Iterations 30-31 and 32-39.
4. Record the observed current public gateway count/inventory rather than assuming the planning-time count.
5. Confirm current RunStore, JobManager, TaskStore, TaskManager, gateway model, public metadata, and migration seams still match the repo-backed research.
6. Protect all unrelated uncommitted research and owner files.

## Acceptance

- implementation assumptions reconciled against current source;
- no source mutation yet;
- no research file rewritten to hide superseded history;
- explicit list of files/symbols expected in F1;
- STOP.

---

# 8. Phase F1 - Single-Run logical request idempotency

This is general Soma infrastructure, not continuation-specific middleware.

## Scope

F1 applies only to public operations that create exactly one canonical Run row through the RunStore/JobManager durable launch path. At the audited HEAD this is:

```text
powershell
remote_powershell
hermes_companion
```

F0 must re-enumerate the exact participating set at implementation time.

Do not force this contract onto:

```text
powershell_group   # ParallelGroup identity + multiple child Runs
hermes_service     # service/session operation, not a RunStore launch
```

`powershell_group` has a legitimate future group-idempotency problem, but that requires a separate invariant:

```text
same logical group request -> same group + same child identities
```

It is not a continuation-v1 prerequisite.

## Goal

Make logical replay of a durable single-Run start converge on exactly one canonical Run.

Required behavior:

```text
new logical_run_request_id
    -> reserve/create one Run

same logical_run_request_id + same normalized request hash
    -> return the existing Run
    -> never launch a second effect

same logical_run_request_id + different normalized request hash
    -> hard conflict

concurrent identical requests
    -> one Run only

lost response then retry
    -> same Run
```

## F1.1 Schema migration

Extend durable Run persistence additively. Do not rewrite historical rows.

Conceptual fields:

```text
logical_run_request_id  nullable/empty for historical rows
request_hash            nullable/empty for historical rows
```

Add a unique partial index on non-empty `logical_run_request_id`.

Do not change `run_id` semantics:

```text
run_id                 = canonical execution/effect identity
logical_run_request_id = replay/idempotency identity
```

## F1.2 Normalized request hash

Build one canonical hash from effect-defining launch inputs.

The hash must include the effective operation and all inputs that can change the launched effect, including as applicable:

```text
operation / tool
repo or host identity
profile / executable identity
argv
working directory
environment
stdin identity/content digest
timeout
Hermes/provider launch parameters that affect the effect
```

Do not include response-only controls such as:

```text
return_when
wait_seconds
projection view
response byte budget
```

Two requests that would launch different work must never share the same normalized hash.

## F1.3 Connection-scoped reservation primitive

Add a narrow RunStore primitive that can reserve a Run row using a caller-owned SQLite connection.

Conceptual behavior:

```text
reserve_run_in_connection(conn, request_identity, normalized_input, ...)
 -> created + run
 -> replay + existing run
 -> conflict
```

The reservation must establish durable `launch_pending` identity before external worker launch.

Do not hold the transaction while the worker/process runs.

## F1.4 JobManager and operation-lock integration

Reuse the current executor, operation-lock, and recovery machinery.

Do not create a second Run launcher.

Adapt the current `_create_and_launch` / reserved-run path so it can consume a durably reserved Run without generating another identity.

Replay of an already-created logical request must return existing state and must not blindly launch again.

For lock-requiring single-Run paths, the ordering must also prove:

```text
persisted same logical request + same hash
 -> replay before a new launch attempt

concurrent active identical logical request
 -> converge on the existing canonical run_id
 -> not merely return generic duplicate-active refusal

unrelated repository busy
 -> preserve ordinary busy/refusal semantics
 -> must not permanently poison a logical request ID unless a durable admission-result contract explicitly says so
```

A crash-recovered `launch_pending` row must be handled conservatively by existing/new recovery evidence; the public retry itself must not assume that `launch_pending` means no external launch occurred.

Do not hold a DB transaction while a worker executes.

## F1.5 Public single-Run start contract

Add optional/required logical request identity only to operation models that participate in the single-Run contract.

Prefer one stable field name across participating variants. Do not add meaningless request-ID fields to `powershell_group` or `hermes_service` merely for schema symmetry, and do not overload child `idempotency_key` fields with a new meaning.

Backward compatibility may permit callers without the new field during migration, but the strong replay guarantee applies only when logical request identity is supplied.

## F1.6 Tests

Mandatory tests:

```text
new request creates exactly one Run
same ID + same payload replays same run_id
same ID + changed argv conflicts
same ID + changed stdin conflicts
same ID + changed response-only wait controls replays
N concurrent identical single-Run requests -> one Run row / one launch / same canonical run_id
concurrent identical request while first owns repo lock -> same canonical run_id
concurrent different request while repo busy -> ordinary busy/refusal semantics preserved
busy refusal does not accidentally poison a future retry key
lock-free Hermes companion identical concurrency -> one Run
lost-response simulation -> retry returns same Run
historical rows without logical request IDs remain readable
crash after reservation before launch leaves one recoverable Run
crash/retry never produces two Run IDs
powershell_group behavior remains unchanged in this programme
hermes_service behavior remains unchanged in this programme
```

## F1 acceptance

Do not proceed until participating single-Run logical request idempotency is mechanically proven.

---

# 9. Phase C1 - Continuation persistence foundation

## Goal

Implement exactly four continuation persistence concerns.

Target tables:

```text
controller_continuations
continuation_contract_revisions
continuation_handoffs
continuation_effect_links
```

All four continuation tables must live in the same main SQLite authority used by canonical Task/Run state in v1:

```text
runs/soma.sqlite3
```

This is required so Task/Run reservation plus `continuation_effect_link` can share one SQLite transaction. Do not place effect links in a second database and still claim atomic association. Migrations must be component-versioned, additive, transactional, and restart-safe.

## C1.1 `controller_continuations`

Purpose only:

```text
continuation identity
human label if useful
lifecycle: open / completed / cancelled
current contract revision pointer
created/updated timestamps
```

Do not add:

```text
next_step
reasoning_phase
pending_action
active_skill
source_frontier
state machine for model cognition
```

Lifecycle close/cancel does not automatically cancel linked Tasks/Runs.

## C1.2 `continuation_contract_revisions`

Immutable governing controller instruction snapshots.

Minimum mechanical data:

```text
contract_revision_id
continuation_id
parent_revision_id
free-form instruction/contract text or durable ref
content hash
honest provenance class/ref
controller_request_id
request_hash
created_at
```

`contract_revision_id` is also the model-facing:

```text
continuation_context_ref
```

Do not invent a second opaque handle unless implementation evidence proves one is necessary.

The current live user instruction always outranks stored old text. When the governing objective materially changes and durable continuation-associated work will continue, create a new revision first.

`update_contract` is a compare-and-set revision operation. The submitted `continuation_context_ref` is the expected current revision:

```text
expected R3 + current R3 -> create R4 and move current pointer
expected R3 + current R4 -> stale_continuation_contract
```

Do not use last-writer-wins for concurrent governing contract updates.

## C1.3 `continuation_handoffs`

Immutable bounded free-form text from prior Sol to future Sol.

Minimum mechanical data:

```text
handoff_id
continuation_id
contract_revision_id
sequence or monotonic creation identity
free-form handoff text
content hash
controller_request_id
request_hash
created_at
```

Do not parse or require semantic fields.

The handoff is not chain-of-thought, canonical world truth, or owner authority.

## C1.4 `continuation_effect_links`

Mechanical origin relation only.

Minimum data:

```text
continuation_id
contract_revision_id
effect_kind: task | run
effect_id
created_at
optional originating request relation
```

Do not copy effect status/result into this table.

Prefer uniqueness that prevents one canonical effect from acquiring two competing continuation origins. Referencing an existing effect from another continuation later is not the same as claiming a second origin.

## C1.5 Store API

Provide narrow connection-scoped operations needed for atomic composition:

```text
create/open continuation
append contract revision with expected-current CAS
append handoff
resolve context ref
require context ref is current AND continuation lifecycle is open
insert effect link in caller-owned connection
read latest handoff
read history
close/cancel lifecycle idempotently
```

New continuation-sensitive writes (`update_contract`, `checkpoint`, linked Task start, linked Run start) require both:

```text
contract_revision_id == continuation.current_contract_revision_id
AND
continuation.lifecycle == open
```

Reads/resume/history remain allowed after completion/cancellation. A closed continuation never blocks an ordinary unassociated Task/Run.

No semantic reconciliation methods.

## C1.6 Replay/idempotency

Immutable write operations must use stable request identity + normalized request hash.

Same request + same hash -> replay existing record.
Same request + different hash -> conflict.

Do not introduce a generic `continuation_commands` journal unless implementation evidence demonstrates a requirement not met by record-level idempotency.

## C1 tests

Mandatory:

```text
fresh DB migration
existing DB migration
migration replay
open continuation idempotency
contract revision replay/conflict
handoff replay/conflict
immutable historical revision retrieval
current contract pointer changes atomically
concurrent contract updates from same expected ref -> one wins, one stale conflict
completed/cancelled continuation rejects new checkpoint/contract update
resume/history still works after close
closing continuation does not mutate linked effects
```

---

# 10. Phase C2 - Continuation service and resume projection

## Goal

Create a small domain service over the persistence layer and existing canonical Task/Run readers.

## Resume bundle

A bounded resume response should include:

```text
continuation
  id / label / lifecycle

continuation_context_ref
  current contract revision ID

controller_instruction
  current free-form contract text/ref
  provenance

sol_handoff
  newest free-form handoff
  contract revision used by that handoff
  timestamp

contract_changed_since_handoff
  deterministic boolean

associated_effects
  bounded Task/Run origin links
  current canonical status/result/recovery projection fetched now

retrieval
  pagination/history refs for deeper inspection
```

No `recommended_next_action` from Soma.

## Effect projection

For every linked effect:

- resolve Task status/result through Task authority;
- resolve Run status/result through Run authority;
- tolerate missing/corrupt historical targets conservatively;
- never reinterpret terminal Task as objective completion.

## Contract mismatch

If latest handoff was written under R3 and current contract is R4:

```text
contract_changed_since_handoff = true
```

Return both facts. Sol reconciles their semantics.

## Boundedness

Use current Soma pagination/projection conventions. Resume should remain compact by default and allow deeper history retrieval instead of dumping all handoffs/effects.

## C2 tests

```text
resume empty continuation
resume with handoff
resume with Task link
resume with Run link
contract changed since handoff
missing effect target
many effects -> bounded pagination
concurrent handoffs preserve both
no semantic next-action field appears
```

---

# 11. Phase C3 - Public continuation gateway

## Goal

Expose the continuation capability to normal Chat without creating a large tool family.

Preferred public shape:

```text
continuation_query
continuation_action
```

The exact operation union must be validated against the then-current public-gateway conventions before activation.

Candidate `continuation_query` operations:

```text
capabilities
list
status
resume
handoffs/history
effects/history
```

Candidate `continuation_action` operations:

```text
open
update_contract
checkpoint
complete
cancel
```

`checkpoint` accepts:

```text
continuation_context_ref
freeform_handoff_text
controller_request_id
```

`update_contract` creates a new immutable contract revision; it never edits the prior revision. It requires an open continuation and uses the supplied current `continuation_context_ref` as a compare-and-set guard.

## Public metadata

Update all current inventory, descriptor identity, annotation, and enumeration authorities exactly once.

Do not hard-code planning-time public tool counts. Derive the new expected count from the observed implementation baseline.

Tool descriptions must make clear:

- continuation is for durable semantic re-entry;
- it does not run reasoning;
- it does not choose the next action;
- `continuation_context_ref` is not an authorization token.

MCP annotations must reflect actual final operation semantics. Do not optimize annotations for prettier UX.

## C3 tests

```text
flat schema/discriminator integrity
public inventory completeness
metadata completeness
capability/descriptor hash movement is expected and exact
open -> checkpoint -> resume live gateway smoke
old context ref rejected for contract-sensitive mutation
read path does not mutate state
```

---

# 12. Phase C4 - Atomic Task effect association

## Goal

Allow an ordinary canonical Task start to optionally declare its continuation origin.

Add one optional scalar:

```text
continuation_context_ref
```

Do not create a continuation-specific Task wrapper.

## Algorithm

Where the Task backend can be durably reserved before launch:

```text
BEGIN shared transaction
  resolve contract_revision_id
  verify it is current AND continuation lifecycle is open
  reserve canonical Task using existing connection-scoped Task primitive
  insert continuation_effect_link(task_id, contract_revision_id)
COMMIT
launch through existing Task backend path
```

The normalized `continuation_context_ref` must participate in the Task-start request hash whenever association is requested. Replaying the same `controller_request_id` with a different/missing continuation origin must conflict; it must never silently relink or detach the existing Task.

The transaction must not include worker execution.

If context ref is stale:

```text
stale_continuation_contract
```

This means only that governing instruction revision changed. It must not say the model's reasoning is stale.

If context ref is omitted:

- Task starts normally;
- no continuation link is created;
- Soma does not guess association.

## C4 tests

```text
Task start without context unchanged
Task start with current open context creates one atomic link
stale or closed context rejected before Task reservation/launch
same Task request replayed with same context -> same Task + same link
same Task request replayed with different/missing context -> request conflict, no relink
concurrent same Task request -> one Task + one link
crash after transaction before backend launch -> Task/link both recoverable
link insertion failure -> no orphan Task reservation escapes transaction
Task status later changes -> link row remains unchanged
```

---

# 13. Phase C5 - Atomic/recoverable direct single-Run effect association

Requires F1.

## Scope

C5 applies only to the F1 single-Run operation set re-confirmed by F0. It does not attach continuation origin semantics to `powershell_group` or `hermes_service` in v1.

## Goal

Give direct durable single-Run starts the same strong origin-link property where `continuation_context_ref` is supplied.

## Algorithm

```text
BEGIN shared SQLite transaction
  resolve continuation contract
  verify context ref is current AND continuation lifecycle is open
  validate logical Run request replay/conflict
  validate immutable continuation-origin replay semantics
  reserve canonical Run in launch_pending
  insert continuation_effect_link(run_id, contract_revision_id)
COMMIT
launch through existing JobManager path
```

Replay of the same logical Run request returns the same Run and existing link only when origin association also matches.

Required origin behavior:

```text
same logical request + same context ref -> replay same Run/link
originally unassociated + retry adds context -> conflict
originally associated + retry omits context -> conflict
same logical request + different context ref -> conflict
```

Do not attach continuation origin after the fact and do not create a Task wrapper around the Run solely to obtain continuation association.

## Recovery

Mandatory crash cases:

```text
before transaction -> nothing durable
after Run reservation but link insert fails -> transaction rollback
after commit before launch -> Run + link both durable
lost public response after launch -> retry returns same Run/link
restart during execution -> existing Run recovery remains authority
```

## C5 acceptance

No claim of atomic Run association is allowed until the shared-connection reservation path is proven by tests.

---

# 14. Phase S1 - Portable Skill library foundation

## Goal

Create a user-owned portable Agent Skills library without inventing a second semantic Skill format.

Canonical package format remains:

```text
<skill>/
  SKILL.md
  scripts/       optional
  references/    optional
  assets/        optional
```

The semantic body remains opaque/free-form to Soma beyond standards-level metadata validation.

## S1.1 Configuration

Add a Skill library config section with an owner-configurable **external private root**.

Do not make `runs/` the production-intent canonical Skill package location.

A compatibility/default development location may exist only if its status is explicit.

The resolver must follow the same absolute-path honesty used by canonical external memory roots.

## S1.2 Library layout

Implementation may choose exact directory names, but the authority model must support immutable whole-package revisions.

Required conceptual layout:

```text
<skill_library_root>/
  revisions/
    <package-hash>/
      <skill-name>/
        SKILL.md
        scripts/...
        references/...
        assets/...
        ... any other package files ...
```

The exact package root is:

```text
<skill_library_root>/revisions/<package-hash>/<skill-name>/
```

This preserves the Agent Skills invariant that the immediate parent directory containing `SKILL.md` matches the Skill `name`.

A mechanical registry maps Skill name -> current package hash/current state. Do not put the historical revision tree directly under a native scanner root such as `~/.agents/skills/`; Phase A exports only the selected/current standard package to such a root.

## S1.3 Package hash

Hash the **whole effective package**, not only `SKILL.md`.

The deterministic package identity must include every regular package file, not only conventional Skill directories:

```text
sorted normalized package-relative paths using `/`
raw SHA256 of each file's bytes
```

Hash the deterministic manifest to obtain `package_hash`. Do not include mutable filesystem metadata such as mtimes.

Changing any regular package file must produce a new revision identity even if `SKILL.md` is unchanged.

## S1.4 Package validation

Mechanical validation only:

```text
required SKILL.md exists
required Agent Skills name/description metadata is valid
relative paths remain inside package root
no path traversal
reject all symlinks in canonical v1 packages
bounded file count / total bytes / single-file bytes
stable deterministic manifest
Skill frontmatter `name` matches the immediate package-root directory
```

Do not validate whether the Skill's advice is intelligent or correct.

## S1.5 Source/provenance

Record enough mechanical provenance to distinguish:

```text
owner/local import
repo built-in seed
native/exported copy if later supported
other imported source/ref
```

A duplicate Skill name from a conflicting source must never silently replace the current package.

Either reject with an explicit identity/provenance conflict or require an explicit owner/library action that establishes revision lineage.

## S1.6 External drift detection

Before returning a supposedly immutable revision, verify package identity against the stored manifest/hash where practical.

If bytes changed out-of-band:

```text
package_integrity_mismatch
```

Do not silently recompute the hash and pretend the same revision changed.

## S1 tests

```text
valid minimal SKILL.md import
package with references/assets/scripts
whole-package hash changes when any file changes
path traversal rejected
any symlink rejected in v1
oversized package rejected
duplicate same bytes converges
same name conflicting source does not silently replace
out-of-band edit detected
historical revision remains immutable
```

---

# 15. Phase S2 - `skill_query` progressive-disclosure gateway

## Goal

Let normal Sol discover and retrieve Skills without injecting the entire library into every Chat context.

One public read gateway:

```text
skill_query
```

Candidate operations:

```text
capabilities
list
search
get
history
resource
```

## Discovery result

Return bounded mechanical metadata only:

```text
skill_ref
name
description
package_hash
current/historical marker
provenance summary
compatibility summary if mechanically available
```

Do not return full SKILL.md in `search`/`list`.

## Search

Normal `list`/`search` defaults to **current enabled revisions only**. Historical revisions are retrieved through explicit `history` or `get(exact skill_ref)`. Disabled Skills are excluded from normal discovery but may remain retrievable by exact immutable ref for provenance/debugging.

Search may deterministically index:

```text
name
description
optionally standards-level metadata
```

No embedding model, LocalAgent classifier, Supervisor, or hidden LLM router is required.

The model supplies the query and chooses the result.

If deterministic ranking is added, it remains retrieval ranking, not semantic authority.

## Get

Return exact immutable revision identity + SKILL.md content + bounded package manifest.

Where same-host resource execution needs it, the response may also include a bounded mechanical locator such as:

```text
package_root
resource_path
```

subject to normal path projection/redaction policy. This is location, not execution authority.

Do not parse the body into workflow steps.

## Resource

Retrieve one exact package-relative resource.

Reading a script must return content/identity only. It must not execute it.

Large/binary resources should use existing Soma bounded/chunked resource projection conventions rather than unbounded inline payloads.

## Public metadata

Description should make the boundary unmistakable, conceptually:

> Use this when you need to discover or read reusable Soma Skills and their referenced resources. It does not execute Skill scripts or grant permissions described by a Skill.

## S2 tests

```text
search returns metadata only
explicit name lookup
ambiguous name/provenance does not silently choose
get exact current revision
get exact historical revision
resource path bounded to package
script retrieval does not execute
large resource uses bounded projection
search/list pagination
public descriptor/inventory tests
```

---

# 16. Phase S3 - `skill_action` revision lifecycle

## Goal

Provide a small library-management surface without turning Skills into an execution authority.

One public mutation gateway:

```text
skill_action
```

Recommended v1 operations:

```text
import_revision
set_current
rollback
enable
disable
```

Permanent purge/deletion is deliberately out of v1 unless a measured requirement justifies the extra destructive semantics.

## Import behavior

V1 must support a bounded direct normal-Chat ingestion contract suitable for Chat-authored Skills, conceptually:

```text
files[]:
  relative_path
  text OR base64 bytes
```

with strict per-file, file-count, and total-package limits. A staged local path/archive import may be added for larger packages but is not required for the basic Chat update flow; any archive path must reject traversal, absolute paths, symlink entries, and expansion beyond configured bounds.

Use a crash-safe pattern:

```text
stage package in temporary location
validate
compute whole-package manifest/hash
materialize immutable revision atomically
record/update registry metadata
optionally change current pointer only when requested
```

Importing bytes must not execute bundled scripts.

`import_revision` requires stable mutation request identity + normalized request hash:

```text
same request ID + same package manifest/hash -> replay
same request ID + different package -> conflict
```

## Current pointer and library-state CAS

Changing the current Skill revision affects future retrieval only.

Per-Skill mutable state (`current`, `enabled`) must expose a mechanical version/expected-current guard. `set_current`, `enable`, and `disable` use compare-and-set; concurrent updates must never silently last-write-win.

`rollback` is mechanically equivalent to `set_current(historical_skill_ref)` and may remain only as a convenience alias.

It does not:

```text
rewrite old packages
rewrite continuation records
mutate existing Task/Run effects
silently change a historical skill_ref
```

## Rollback

Rollback means switch the current pointer to an existing immutable revision.

Do not create a copied duplicate package merely to roll back.

## Enable/disable

This controls normal library discovery/availability only. It is not authorization for any tool the Skill mentions.

## MCP annotations

Do not predeclare `destructiveHint=false` merely because rollback exists.

Set public annotations from the actual final operation semantics and the current MCP definition. If mixed operations make one annotation misleading, revisit the operation split based on measured UX rather than lying in metadata.

## S3 tests

```text
import new revision
replay same import
conflicting replay
set current
rollback
old exact ref still retrieves old bytes
disable removes normal discovery but historical exact retrieval policy remains explicit
script never executes during import/update
crash during staging leaves no half-current revision
crash after immutable materialization before registry update is recoverable/orphan-safe
concurrent set_current from same expected version -> one wins, one stale conflict
lost response after set_current -> replay is stable
concurrent enable/disable does not silently last-write-win
public annotations match final semantics
```

---

# 17. Phase S4 - Built-in/seed Skill packaging

Only after S1-S3 are accepted.

## Goal

Promote useful repo-owned Skill drafts into standards-compliant seed packages without making the source repo the owner library.

First candidate:

```text
soma-engineering
```

Source research draft:

```text
docs/chatgpt-tool-ux/soma-engineering-skill-draft/SKILL.md
```

That research directory name does not match the Skill frontmatter name and therefore is not itself the final standards-valid package. S4 must materialize the seed under:

```text
soma-engineering/
  SKILL.md
```

Implementation should package/copy/promote it through a reviewed built-in location or import fixture; do not silently redefine the user's personal library copy.

User Skills such as `arash-research` remain owner library content and should be imported through the library lifecycle rather than hard-coded into Soma source.

## Acceptance

- built-in seed is standards-valid;
- seed can be imported into a fresh Skill library;
- subsequent owner revision creates a normal immutable revision;
- built-in source does not overwrite personal current revision automatically.

---

# 18. Phase I1 - Integrated normal-Chat acceptance

This phase is mandatory. Unit tests alone are not enough.

## 18.1 Continuation scenarios

### A. Interrupted repository implementation

1. Sol opens continuation.
2. Sol starts linked Task/Run work.
3. conversation is replaced by a fresh Chat.
4. owner says `continue`.
5. fresh Sol obtains resume bundle, inspects live repo, and continues without owner reconstructing history.

Pass condition: no semantic next-step engine is required.

### B. Long scientific Run

Fresh Sol resumes, sees linked Run/current canonical result, and continues scientific reasoning.

Pass condition: Run terminality is not mistaken for objective completion.

### C. Remote service repair

Fresh Sol sees prior effect lineage, then independently verifies current remote state.

Pass condition: handoff is treated as a hint, not current world truth.

### D. Contract change

Handoff H3 belongs to R3; current owner contract is R4.

Pass condition:

```text
contract_changed_since_handoff = true
```

and fresh Sol does not blindly follow H3.

### E. Free-form variability

Use multiple domains with radically different handoff prose.

Failure condition:

> a new domain requires adding semantic handoff fields.

## 18.2 Skill scenarios

### F. Explicit Skill use

Owner says:

```text
use arash-research for this
```

Sol finds/loads the exact Skill and follows it.

### G. Implicit useful Skill

A request clearly matches an installed Skill without naming it.

Measure whether Sol calls `skill_query.search` and selects sensibly.

### H. Negative control

A simple request does not need a Skill.

Measure unnecessary `skill_query` calls.

### I. Multiple Skills

Sol may load two applicable Skills.

Pass condition: Soma does not merge/resolve their semantics. Sol handles instruction reconciliation under normal model instruction precedence.

### J. Conflicting same-name source

Import same name from a different provenance.

Pass condition: no silent replacement.

### K. Skill update mid-continuation

Continuation remains open while Skill current revision changes R7 -> R8.

Pass condition:

- continuation record is unchanged;
- fresh Sol normally discovers current R8;
- exact R7 remains retrievable when historical reproduction is requested.

### L. Bundled script

Skill tells Sol to run `scripts/foo.py`.

Pass condition:

- `skill_query.resource` only reads it and may return the exact immutable resource locator;
- execution requires an explicit existing Soma execution call;
- the Skill cannot bypass existing authority.

### M. Closed continuation admission

A completed/cancelled continuation still has an old/current ref.

Pass condition: no new checkpoint, contract update, associated Task, or associated Run can be created; resume/history still works; ordinary unassociated effects still work.

### N. Immutable origin replay

Replay the same Task/Run logical request while changing, adding, or omitting its continuation origin.

Pass condition: conflict; no relink/detach.

### O. Concurrent contract update

Two writers use the same current contract ref.

Pass condition: exactly one revision advances current; the other receives `stale_continuation_contract`.

### P. Skill context loss/compaction recovery

Do not assume earlier Skill tool output is still in normal Chat context.

Pass condition: Sol can re-fetch the exact/current immutable Skill when needed. Soma does not claim to control ChatGPT's hidden compactor.

### Q. Untrusted repo-local Skill

Open a repository containing `.agents/skills/...`.

Pass condition: Soma v1 does not silently ingest or activate it. Project-local auto-discovery remains a future feature with an explicit trust gate.

## 18.3 Discovery-recall corpus

Extend the existing normal-Chat tool-UX golden-corpus methodology with Skill-specific cases.

Measure at least:

```text
should search Skill -> did search?
should not search -> unnecessary search?
explicit Skill name -> exact retrieval?
selected correct current/historical revision?
unnecessary full Skill loads?
resource overfetch?
multiple Skill choice quality?
latency / extra call count
```

Do not add a hidden semantic router solely because recall is imperfect.

If recall is weak, evaluate the optional native/manual adapters in Phase A rather than moving semantic choice into Soma.

---

# 19. Phase I2 - Documentation, migration, and rollout

## Documentation updates

Update the active architecture/runbooks to state:

```text
Sol is the reasoning head.
Continuation is semantic re-entry.
Skills are portable guidance packages.
Skill scripts are inert until explicitly executed through Soma.
Company remains separate.
Reasoning workers remain optional specialists only.
```

Do not rewrite historical research to make earlier candidates disappear.

## Public capability inventory

Update:

```text
public gateway inventory
public operation inventory
human-facing metadata
schema/descriptor hashes
capability discovery
associated enumeration tests
```

from the actual final tool set.

## Migration compatibility

Required:

- historical Runs without logical request identity remain readable;
- existing Task API still works without continuation context;
- all existing normal Soma effect tools work without continuation;
- system starts with Skill layer disabled/unconfigured if no external library root is configured, unless implementation explicitly establishes a safe default;
- repository-local `.agents/skills` packages are not automatically ingested/activated in v1;
- no existing repository or memory authority is redefined.

## Rollout order

Recommended:

```text
1. single-Run logical request idempotency live
2. continuation internal persistence/service
3. continuation public read/action
4. Task link path
5. Run link path
6. Skill library internal
7. skill_query
8. skill_action
9. built-in seed
10. integrated normal-Chat corpus
11. optional adapters only if measured value exists
```

Each public-surface activation should be independently reversible.

---

# 20. Optional Phase A - Delivery adapters only after measurement

These are not core v1 dependencies.

## A1 Native ChatGPT/Work/Codex Skill export/package adapter

Purpose:

- expose the same canonical Agent Skill package through native supporting surfaces;
- avoid maintaining two semantic Skill formats.

Rules:

- export/copy does not become canonical authority;
- native copy drift is detectable as differing package identity;
- no automatic two-way synchronization in v1;
- Soma library remains the owner-selected canonical local copy when using Soma.

## A2 Browser/manual picker

Only if normal-Chat discovery recall materially benefits.

The add-on should be convenience UI only:

```text
show installed Skills
let owner choose
insert Skill name/ref into the Chat request
```

It must not:

```text
be required for correctness
inject hidden authority
run a second reasoning model
execute Skill scripts
own canonical Skill state
```

---

# 21. Explicitly out of scope

Do not implement in this programme:

```text
exact hidden ChatGPT runtime/session resume
model chain-of-thought storage
structured reasoning-state capsules
continuation source registry
semantic evidence incorporation tracking
semantic next-step scheduler
reasoning locks
continuation effect intents
one MCP tool per Skill
Skill body -> workflow DAG compiler
LLM/embedding Skill auto-router
Skill scripts with direct execution privileges
Skill-defined authorization
mandatory browser extension
native-Skill auto-sync
automatic Skill pinning into every continuation
Company/Mission replacement
Task-wrapper-for-every-Run
parallel-group idempotency folded into single-Run F1
project-local Skill auto-ingestion without an explicit trust design
```

---

# 22. Failure semantics that must stay honest

Use mechanical language only.

Good:

```text
stale_continuation_contract
package_integrity_mismatch
logical_run_request_hash_conflict
skill_name_provenance_conflict
effect_target_missing
```

Avoid semantic overclaim such as:

```text
reasoning_stale
Skill_is_correct
all_relevant_evidence_consumed
best_Skill_selected
objective_complete
```

---

# 23. Final acceptance contract

The programme is accepted only when all of the following are true.

## Run substrate

- direct durable **single-Run** retry with stable request identity cannot duplicate launch;
- participating single-Run operations are explicitly enumerated; group/service semantics are not faked;
- identical concurrency converges even when the first request owns an operation lock;
- conflicting request reuse is detected;
- connection-scoped Run reservation exists and is proven where atomic link composition needs it.

## Continuation

- exactly four continuation persistence concerns are sufficient;
- free-form contract and handoff text remain opaque to Soma;
- current contract revision ID is the continuation context ref;
- new continuation-sensitive writes require current context **and open lifecycle**;
- governing contract update is revision CAS, not last-writer-wins;
- resume returns current durable facts without choosing next action;
- Task/Run origin association is immutable under replay;
- Task/Run origin links are durable before associated launch where the architecture claims that guarantee;
- omission of context ref does not break ordinary tools and is never guessed.

## Skills

- standard Agent Skill packages are canonical semantic artifacts;
- whole-package immutable revision identity covers all regular files and uses Agent-Skills-valid package roots;
- symlinks are rejected in canonical v1 packages;
- normal Chat can directly import a bounded small Skill package without Git staging;
- normal Chat can search/get/resource through one read gateway, with current-enabled-only default discovery;
- library lifecycle uses one mutation gateway with request replay + CAS;
- bundled code cannot bypass existing execution authority;
- update/rollback does not mutate historical revisions;
- Skills are not inserted into continuation state by default;
- native/browser adapters are optional.

## Integrated behavior

- fresh Chat can resume a real multi-step objective;
- fresh Sol independently re-checks live state where required;
- useful Skills can be loaded without a second semantic router;
- normal requests are not forced through continuation or Skills;
- Work/Sol can continue using existing Soma tools directly;
- no old Agent/Worker semantic-planner architecture is resurrected.

---

# 24. Implementation-thread reporting template

Every stage acceptance report should contain:

```text
Stage:
Status: ACCEPTED | BLOCKED | FAILED
Branch / HEAD:
Files changed:
Schema/migration impact:
Public contract impact:
Tests run:
Durable evidence IDs:
Compatibility result:
Architecture invariants checked:
Known limitations:
Unrelated owner/concurrent work preserved:
Commit created: yes/no
Push: no unless separately authorized
Next authorized stage:
```

Do not hide deviations from this plan. A clean `BLOCKED` result is preferable to an implementation that silently changes the architecture.

---

# 25. Final implementation order

The recommended sequence for the implementation thread is:

```text
F0  authority freeze + live preflight
F1  single-Run logical request idempotency
C1  continuation schema/store
C2  continuation service/resume projection
C3  continuation public gateways
C4  Task continuation-effect association
C5  direct single-Run continuation-effect association
S1  external portable Skill library + immutable revisions
S2  skill_query progressive retrieval
S3  skill_action revision lifecycle + replay/CAS
S4  built-in/seed Skill packaging
I1  real normal-Chat + Skill + continuation acceptance corpus
I2  rollout/docs/public capability reconciliation
A1/A2 only if measured need exists
```

The implementation thread may split any stage into smaller commits/tests, but it must not reorder dependencies in a way that creates stronger guarantees before their substrate exists.

---

# 26. Owner-visible end state

After the programme, normal Chat should feel like this:

```text
owner: continue

Sol
 -> continuation_query.resume(...)
 -> sees current instruction + prior handoff + current Task/Run facts
 -> optionally skill_query.search/get(...) when a reusable workflow helps
 -> independently inspects live repo/service/world where needed
 -> reasons
 -> uses ordinary Soma tools
 -> checkpoints a free-form handoff only when continuity risk justifies it
```

And ordinary work should still be:

```text
owner: check the repo status
Sol -> repo_query -> answer
```

No continuation ceremony.
No Skill ceremony.
No second brain.

That is the target.
