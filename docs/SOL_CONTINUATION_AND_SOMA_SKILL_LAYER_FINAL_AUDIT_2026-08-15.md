# Sol Semantic Continuation + Soma Portable Skill Layer - Final Audit

Date: 2026-08-15  
Status: FINAL AUDIT - PASS WITH MANDATORY AMENDMENTS  
Repository: `D:\Github\Soma`  
Audited plan: `docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_IMPLEMENTATION_PLAN_2026-08-15.md`  
Audited plan SHA256: `64134f182f379be45ab3d61692d14425071615520b61dc675747f9812f8a9df5`  
Repo HEAD observed during audit: `bb551744824fd7abbac02441f901b543bac33d7f`  
Implementation authorization: none; this document only corrects implementation authority.

## 1. Verdict

The architecture survives final audit.

The central model remains correct:

```text
Sol / ChatGPT = reasoning head
Soma continuation = durable semantic re-entry
Soma Skills = portable reusable guidance
Task / Run / repo / remote providers = canonical mechanical authorities
```

No finding requires restoring a semantic planner, local-model router, structured reasoning capsule, next-step engine, reasoning lock, or universal Task wrapper.

However, the implementation plan contains three material defects and several hardening gaps that must be corrected before implementation. This audit is therefore **normative**.

Implementation authority is:

```text
implementation plan
+ this final audit
```

Where they conflict, **this final audit wins**.

## 2. Evidence rechecked

### 2.1 Current Soma repository

The final audit re-read the live source around:

```text
soma/server.py
soma/gateway_models.py
soma/run_store.py
soma/job_manager.py
soma/operation_locks.py
soma/parallel_groups.py
soma/hermes_companion_client.py
soma/executable_profiles.py
soma/tasks/store.py
soma/tasks/manager.py
soma/config.py
soma/public_gateway_inventory.py
soma/public_tool_metadata.py
```

The repo still confirms:

- `RunStore` has canonical `run_id` identity but no generic persisted logical Run request ID/hash;
- `TaskStore` already has caller-owned transaction support and request-id/hash replay;
- ordinary `JobManager._create_and_launch()` creates a new Run identity unless a reserved ID is supplied;
- operation locks are active-resource locks, not durable logical-request idempotency;
- Skills do not yet have a live Soma registry/gateway;
- current external-root configuration patterns remain suitable precedents.

### 2.2 Current Agent Skills / OpenAI sources

Primary sources rechecked during audit:

```text
https://agentskills.io/specification
https://agentskills.io/client-implementation/adding-skills-support
https://help.openai.com/en/articles/20001066-skills-in-chatgpt/
https://openai.com/academy/skills/
```

Important current facts:

- Agent Skills require `SKILL.md` YAML frontmatter plus Markdown body;
- `name` and `description` are required;
- the `name` must match the directory immediately containing `SKILL.md`;
- Skills use progressive disclosure: metadata, then instructions, then resources;
- `scripts/`, `references/`, and `assets/` are conventional optional resources, while other files/directories are also permitted;
- `allowed-tools` is experimental and client-dependent;
- client guidance warns that project-local Skills may be untrusted instruction sources;
- client guidance recommends preserving activated Skill content across compaction where the host controls compaction;
- OpenAI Skills use the Agent Skills open standard and native availability/synchronization varies by product/surface.

These facts strengthen, rather than weaken, the overall Soma direction.

---

# 3. Mandatory Amendment A - F1 is single-Run idempotency, not all `run_start`

## Finding

The plan currently talks too broadly about one stable logical request identity across direct `run_start` variants.

At the audited HEAD, `run_start` contains materially different authorities:

```text
powershell
  -> one canonical durable Run

remote_powershell
  -> one canonical durable Run

hermes_companion
  -> one executable-profile canonical durable Run

powershell_group
  -> one ParallelGroup identity + multiple child Run identities

hermes_service
  -> Hermes service/session operation; not a canonical RunStore launch
```

`powershell_group` is implemented through `ParallelGroupStore` / `launch_powershell_group()` and reserves a group plus child Runs. `hermes_service` calls the Hermes service gateway directly.

Therefore the contract:

```text
same logical request -> same Run
```

cannot honestly be applied to every `run_start` variant.

## Corrected F1 scope

F1 applies only to public operations that create **exactly one canonical Run row** through the RunStore/JobManager durable launch path.

At the audited HEAD this includes:

```text
powershell
remote_powershell
hermes_companion
```

F0 must re-enumerate this set at implementation time rather than hard-code it forever.

F1 does **not** silently redefine:

```text
powershell_group
hermes_service
```

## Group path

`powershell_group` has a separate logical identity problem:

```text
same logical group request -> same group + same child identities
```

That is a worthwhile future Soma reliability improvement, but it is a **different idempotency authority** and is not a prerequisite for v1 continuation.

Do not force group semantics into RunStore single-Run idempotency.

## Hermes service path

`hermes_service` is not a RunStore launch and must not receive a fake Run idempotency contract merely because it shares the public `run_start` gateway.

Its replay/continuity semantics remain owned by its service/session contract.

## Public model rule

Add logical Run request identity only to operation models that actually participate in the single-Run contract.

Do not add a meaningless field to every `RunStartRequest` variant for schema symmetry.

---

# 4. Mandatory Amendment B - F1 must coexist correctly with operation locks

## Finding

Current `JobManager._create_and_launch()` acquires the applicable operation lock before creating the Run row.

Current lock acquisition can return:

```text
duplicate active task
repository busy
```

with the owner Run identity available in lock metadata.

A naive F1 implementation can therefore fail the intended invariant:

```text
N concurrent identical logical requests -> one canonical Run response
```

if the second request is merely rejected by the operation lock.

## Correct invariant

For lock-requiring single-Run paths:

1. an already persisted same logical request + same hash must replay before a new launch is attempted;
2. a concurrent active duplicate must converge to the existing logical Run rather than become a generic duplicate refusal;
3. an unrelated `repository busy` refusal must not permanently consume a logical request ID unless the implementation intentionally persists a durable terminal admission result and documents that retry contract;
4. request reservation, lock acquisition, Run materialization, and launch ordering must preserve exactly-one launch without holding a DB transaction while a worker executes.

The implementation may choose the precise ordering, but the tests must prove the externally visible invariants.

## Added F1 tests

```text
concurrent identical logical request while first owns repo lock -> same canonical run_id
concurrent different request while repo busy -> ordinary busy/refusal semantics preserved
busy refusal does not accidentally poison a future retry key
lock-free Hermes companion identical concurrency -> one Run
```

---

# 5. Mandatory Amendment C - Continuation context must be current AND open

## Finding

A completed/cancelled continuation may still have a mechanically current contract revision.

Therefore:

```text
context ref is current
```

is not sufficient admission for a new checkpoint, contract update, or continuation-associated effect.

## Correct guard

For new continuation-sensitive writes, the store/service must verify both:

```text
contract_revision_id == continuation.current_contract_revision_id
AND
continuation.lifecycle == open
```

Use a narrow mechanical primitive conceptually equivalent to:

```text
require_open_current_context_ref(...)
```

Reads/history/resume of completed/cancelled continuations remain allowed.

`complete` / `cancel` are lifecycle mutations and must themselves be idempotent.

## Affected operations

Require open + current context for:

```text
update_contract
checkpoint
Task effect association
Run effect association
```

A closed continuation must not block an ordinary Task/Run that omits continuation association.

## Added tests

```text
completed continuation rejects checkpoint
cancelled continuation rejects checkpoint
completed continuation rejects linked Task start before Task reservation
cancelled continuation rejects linked Run start before Run reservation
ordinary unassociated Task/Run still works
resume/history still works after close
```

---

# 6. Mandatory Amendment D - Continuation tables must share the main SQLite authority in v1

The plan says to use the existing durable SQLite domain where atomic composition requires it. This audit makes the requirement explicit.

For v1, the four continuation tables belong in the same main SQLite database used by canonical Task/Run state:

```text
runs/soma.sqlite3
```

Reason:

```text
Task reservation + continuation link
Run reservation + continuation link
```

must be capable of sharing one SQLite transaction.

Do not place `continuation_effect_links` in a second database and then claim atomic association.

Continuation transactions remain short and local. They never span model reasoning, remote calls, worker execution, or owner wait time.

---

# 7. Mandatory Amendment E - Origin association is immutable under replay

## Task starts

When an optional `continuation_context_ref` is supplied on Task start, it must participate in the Task start idempotency contract.

A replay using the same `controller_request_id` but a different continuation origin must conflict rather than silently return/relink the old Task.

The cleanest implementation is to include the normalized continuation context ref in the canonical Task-start request hash.

## Direct single-Run starts

F1 logical Run request hashing remains a general effect-identity mechanism and should not become continuation-only machinery.

C5 must separately enforce immutable origin association:

```text
same logical Run request + same context ref -> replay same Run/link
same logical Run request originally unassociated + retry adds context -> conflict; do not attach after the fact
same logical Run request originally associated + retry omits context -> conflict
same logical Run request + different context ref -> conflict
```

The existing effect-link row/presence can supply the mechanical origin evidence; do not invent semantic inference.

This preserves the meaning of `continuation_effect_links` as **origin**, not arbitrary later attachment.

---

# 8. Mandatory Amendment F - Contract update is a revision CAS

`update_contract` must use the caller's current `continuation_context_ref` as a compare-and-set guard.

Conceptual behavior:

```text
expected current R3 + current is R3 -> create R4, move current pointer
expected current R3 + current is already R4 -> stale_continuation_contract
```

Do not allow two concurrent writers to create competing governing revisions and silently use last-writer-wins current-pointer behavior.

Handoffs may remain concurrent/immutable; governing contract revision is different because it is the current controller instruction authority.

---

# 9. Mandatory Amendment G - Skill revision storage layout must remain Agent-Skills-valid

## Finding

The plan's conceptual layout:

```text
<skill-name>/
  revisions/
    <package-hash>/
      SKILL.md
```

places `SKILL.md` immediately under `<package-hash>`.

The current Agent Skills specification requires the Skill `name` to match the parent directory containing `SKILL.md`.

Therefore the conceptual layout is not itself a valid portable Skill package.

## Corrected storage shape

The immutable revision store may be content-addressed, but every materialized package root must preserve the Skill-name directory:

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

The exact package root for that revision is:

```text
<skill_library_root>/revisions/<package-hash>/<skill-name>/
```

`SKILL.md` therefore has the correct parent directory.

A registry/index maps:

```text
skill name -> current package hash
```

Historical revisions remain immutable.

## Do not use a native scanner root as the revision store

Do not place the historical revision tree directly beneath a broadly scanned path such as:

```text
~/.agents/skills/
```

because a generic Agent Skills client may recursively discover duplicate historical packages.

If Phase A later exports to a native scanner root, materialize only the selected/current package in standard form:

```text
~/.agents/skills/<skill-name>/SKILL.md
```

That export remains an adapter/copy, not canonical Soma revision authority.

---

# 10. Mandatory Amendment H - Whole-package hash rules must be exact

For deterministic Skill revision identity, the package manifest/hash must include **all regular package files**, not only conventional `scripts/`, `references/`, and `assets/` directories.

Use deterministic inputs such as:

```text
sorted normalized package-relative paths using `/`
raw file-byte SHA256 for each file
```

Do not include mutable filesystem metadata such as mtimes.

The resulting manifest is then hashed to obtain `package_hash`.

For v1, reject symlinks entirely inside imported canonical packages. This is simpler and more portable than trying to distinguish safe internal symlinks from escaping symlinks across Windows/Linux clients.

Out-of-band mutation of canonical revision bytes remains:

```text
package_integrity_mismatch
```

not an implicit new revision.

---

# 11. Mandatory Amendment I - Skill mutation operations need replay + CAS

The Skill layer must use the same mechanical reliability standards as the rest of Soma.

## Immutable import

`import_revision` requires a stable controller/mutation request identity and normalized request hash.

```text
same request ID + same package manifest/hash -> replay
same request ID + different package -> conflict
```

## Mutable library pointer/state

Per-Skill current/enabled state needs a mechanical version or expected-current guard.

Conceptually:

```text
state_version
```

or an equivalent expected current ref.

`set_current`, `enable`, and `disable` must compare-and-set rather than silently lose concurrent updates.

`rollback` does not need to be a separate authority. It is semantically:

```text
set_current(historical_skill_ref)
```

It may remain a UI/convenience alias only if useful.

## Added tests

```text
concurrent set_current from same expected version -> one wins, one stale conflict
lost response after set_current -> replay does not create another transition
concurrent enable/disable does not silently last-write-win
```

---

# 12. Mandatory Amendment J - `import_revision` needs a real normal-Chat ingestion contract

The original plan specifies lifecycle semantics but leaves the actual package submission mechanism too open.

Normal Sol must be able to author/update a Skill without first writing it into the Soma Git repo.

V1 must support at least one bounded direct package-ingestion shape suitable for Chat-authored Skills, conceptually:

```text
files[]:
  relative_path
  text OR base64 bytes
```

with strict package/file/total-byte limits.

The implementation may additionally support a staged local path/archive import for large packages, but large-file support must not be required for the basic normal-Chat update flow.

If archive import is supported, protect against:

```text
path traversal
absolute paths
symlink entries
archive expansion beyond configured bounds
```

---

# 13. Mandatory Amendment K - Skill discovery defaults to current enabled revisions

Normal `skill_query.list/search` should expose **current enabled Skill revisions only** by default.

Historical revisions are retrieved through explicit:

```text
history
get(exact skill_ref)
```

This prevents historical versions from polluting automatic discovery and ranking.

A disabled Skill may remain retrievable by exact immutable ref for provenance/debugging, but it should be excluded from normal list/search discovery.

---

# 14. Mandatory Amendment L - Project-local Skill auto-discovery is out of v1

The Agent Skills client guide commonly scans both user-level and project-level Skill directories and warns that project-local Skills can be untrusted instruction sources.

Soma v1 should **not automatically ingest or activate repository-local `.agents/skills` packages** merely because a repository was cloned or opened.

V1 sources remain:

```text
explicit owner/Sol-authorized import
reviewed built-in seed packages
```

A later project-Skill discovery feature may be added, but it must define:

```text
trusted-project gate
source precedence
collision behavior
explicit provenance
```

This keeps an untrusted repository from silently becoming model instruction authority.

---

# 15. Mandatory Amendment M - Normal-Chat Skill compaction limit must stay honest

The Agent Skills client guide recommends that hosts preserve activated Skill instructions across context compaction.

Soma does not own normal ChatGPT's hidden context compactor.

Therefore Soma v1 cannot promise:

```text
an activated Skill will remain in hidden Chat context forever
```

Correct promise:

```text
Soma can always return the exact immutable Skill revision again.
```

If exact Skill provenance matters to a long objective, Sol may naturally mention the `skill_ref` in its free-form handoff. Do not add a mandatory structured `continuation_skill_state` field.

Add a real acceptance case where earlier Skill tool output is no longer assumed present and fresh Sol re-fetches an explicit/current Skill when needed.

Native hosts that preserve Skill content internally remain free to do so; Soma does not duplicate that runner state.

---

# 16. Mandatory Amendment N - Skill resource location may be mechanical; execution stays external to Skill authority

The Agent Skills client guidance carries a Skill location/directory so relative resource references can be resolved.

`skill_query.get/resource` may therefore return a bounded mechanical locator for the exact immutable package/resource when same-host execution needs it, for example:

```text
package_root
resource_path
```

subject to normal path redaction/projection policy.

This does not grant execution authority.

A script still runs only through an existing Task/Run/domain execution surface.

Do not create:

```text
skill_execute
SkillRuntime
hidden subprocess launch from skill_query
```

Execution should use the exact immutable script path where appropriate while keeping the canonical package write-once at the Soma API layer. Out-of-band modification remains detectable by package hash verification.

---

# 17. Built-in seed correction

The current research draft path:

```text
docs/chatgpt-tool-ux/soma-engineering-skill-draft/SKILL.md
```

has a parent directory named `soma-engineering-skill-draft` while its frontmatter `name` is `soma-engineering`.

That is acceptable as a **research draft**, but it is not the final standards-valid package location.

S4 must materialize the actual built-in seed under a parent directory named exactly:

```text
soma-engineering/
  SKILL.md
```

before claiming Agent Skills validation success.

---

# 18. Added integrated acceptance cases

Add these to I1 before programme acceptance:

## Continuation

```text
closed continuation + old/current context ref cannot create new associated work
same Task request replayed with different continuation ref conflicts
same Run request replayed with changed/missing continuation ref conflicts without relinking
concurrent contract update from same current ref -> one revision wins; other gets stale contract
```

## Direct Run substrate

```text
single-Run idempotency tests do not accidentally assert group semantics
powershell_group remains behaviorally unchanged in this programme
hermes_service remains behaviorally unchanged in this programme
```

## Skills

```text
stored revision package validates with name == immediate parent directory
all regular package files affect package hash
symlink package rejected in v1
list/search excludes historical and disabled revisions by default
concurrent current-pointer mutations use CAS
normal Chat can import a small Skill package without Git/repo staging
activated Skill loss from assumed context can be recovered by exact/current re-fetch
repo-local untrusted Skill is not silently ingested
```

---

# 19. Separate repo-backed improvement discovered by final audit

`powershell_group` has its own durable logical-request problem after a lost public response because the public group start does not currently expose a stable top-level group replay identity, even though children carry local idempotency keys internally.

This is a legitimate **future Soma reliability improvement**:

```text
parallel group request idempotency
```

It is not required to implement Sol continuation v1 and must not be smuggled into F1 as if a group were one Run.

Record it for a later infrastructure lane rather than expanding the current programme.

---

# 20. Final implementation dependency graph after audit

The high-level stage order does not change:

```text
F0 live preflight / exact authority enumeration
 |
 v
F1 single-Run logical request idempotency
 |
 +-------------------------------+
 |                               |
 v                               v
C1 continuation persistence      S1 Skill library foundation
 |                               |
 v                               v
C2 resume service                S2 skill_query
 |                               |
 v                               v
C3 continuation gateways         S3 skill_action + replay/CAS
 |
 v
C4 Task origin association
 |
 v
C5 direct single-Run origin association
 |
 +-------------------------------+
                 |
                 v
        I1 integrated acceptance
                 |
                 v
        I2 rollout/documentation
```

Explicitly outside the current dependency graph:

```text
parallel-group idempotency
project-local automatic Skill discovery
native Skill synchronization
browser picker
```

---

# 21. Final architecture verdict

After applying the amendments above, the implementation plan is **IMPLEMENTATION-READY THEORY**.

The final audit found no reason to add:

```text
second reasoning model
semantic Skill router
structured reasoning state
reasoning lock
source registry
effect intent table
Skill runtime executor
mandatory browser extension
mandatory native Skill dependency
```

The strongest remaining uncertainty is product behavior, not architecture:

```text
Will normal Sol call skill_query often enough when an implicit Skill is useful,
without over-calling it on ordinary requests?
```

That remains correctly assigned to the I1 discovery-recall corpus rather than a hidden router.

Final promise boundary:

```text
Soma can preserve durable controller contracts and Sol handoffs.
Soma can correlate associated canonical Tasks/Runs when context refs are supplied.
Soma can provide safe logical replay for single canonical Run starts once F1 is implemented.
Soma can store and retrieve exact immutable Agent Skill revisions.
Soma can expose current reusable Skills to normal Chat on demand.

Soma does not become the thinker.
Soma does not know the best next action.
Soma does not know the best Skill.
Soma does not preserve hidden ChatGPT runtime state.
```

**FINAL AUDIT VERDICT: PASS WITH THE MANDATORY AMENDMENTS IN THIS DOCUMENT.**
