# Iteration 34 - Skill Revisions vs Continuation Authority Boundary

Date: 2026-08-15
Status: research only; corrective architecture result
Track: Sol-centric agent interface + Soma Skill layer

## Question

If Sol is using one Skill revision during an active objective and the Skill is later updated, should the active Skill revision become part of Soma's continuation state?

## External evidence

Current OpenAI Skills and Agent Skills behavior supports several important boundaries:

- Skills are reusable workflows/instructions/resources, not user objectives or external world truth.
- OpenAI Skills use the Agent Skills open standard and can be downloaded/reinstalled across supporting products.
- ChatGPT can automatically use one or more installed Skills when helpful, which means activation is an agent/runtime decision rather than a property of the Skill package itself.
- Agent Skills defines the package format and progressive loading, but does not require a portable cross-runtime activation-state contract.
- The Skill body is intentionally free-form; the standard constrains package metadata, not a machine-readable cognitive state.
- OpenAI surfaces Created/Updated metadata and can download/upload Skills, so Skill lifecycle is naturally separate from conversation lifecycle.

Primary sources:

- https://help.openai.com/en/articles/20001066-skills-in-chatgpt
- https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx
- https://openai.com/academy/skills/

## Existing continuation authority

Iteration 30 converged on four continuation concerns only:

```text
controller_continuations
continuation_contract_revisions
continuation_handoffs
continuation_effect_links
```

The continuation exists to preserve:

```text
owner/controller instruction
Sol free-form handoff
durable Task/Run effect lineage
```

It deliberately does not preserve the complete model environment, tool catalog, world snapshot, or exact ChatGPT runner state.

## Candidate approaches

### A. Pin active Skill revisions into every continuation

Conceptually:

```text
continuation_skill_links
  continuation_id
  skill_revision_id
  active_from
  active_until
```

Rejected as the default.

Why:

- it makes Skill activation look more authoritative than it is;
- it creates another continuation authority;
- it introduces lifecycle semantics for `active` that Soma cannot observe reliably in normal Chat;
- normal Chat has no trustworthy session event saying exactly when Sol cognitively activated/deactivated a Skill;
- it risks rebuilding the discarded semantic source/decision-state machinery under a different name.

### B. Put Skill revisions into controller contract revisions

Rejected.

The controller contract is what the owner currently requires. A Skill is guidance available to Sol for carrying out that contract.

Changing a Skill should not mechanically mean the owner's objective changed.

### C. Put required Skill refs into every handoff

Rejected as a correctness requirement.

A handoff may naturally mention a Skill when useful, but requiring Sol to serialize `active_skill_refs[]` at every checkpoint reintroduces model-authored bookkeeping.

### D. Keep Skill revision history inside the Skill Library; do not pin by default

Preferred.

```text
Skill Library
  skill identity
  immutable package revisions
  current revision pointer

Continuation
  unchanged four-authority model
```

Fresh Sol resumes the objective, then discovers/loads the current applicable Skill as needed.

## Why current Skill should normally win

Consider:

```text
objective started under arash-research R7
R8 fixes a weak research rule
fresh Chat resumes tomorrow
```

For normal continuation, future Sol should generally benefit from R8 rather than being silently forced back to R7 merely because R7 happened to be available earlier.

The owner contract remains the governing authority.

A Skill update is analogous to improving a reusable playbook/tooling layer, not revising the objective.

## Exact historical reproducibility

There are legitimate cases where an old Skill revision matters:

- debugging why a prior result differed;
- audit/provenance;
- scientific or benchmark reproducibility;
- comparing old vs new workflow behavior;
- verifying that a prior durable effect followed a specific procedure.

For those cases, the Skill Library should retain immutable content-addressed revisions and allow exact retrieval by `skill_ref`.

This does not require making the Skill part of continuation correctness.

Conceptually:

```text
skill_ref = immutable package revision identity
```

A handoff, audit record, benchmark artifact, Task/Run provenance record, or explicit user note may reference that immutable ref when exact provenance matters.

## Repo alignment

Iteration 30 already separates reusable Knowledge/tooling from continuation state and explicitly preserves only the owner contract, handoff, and durable effects.

Soma's Company Kernel also provides a useful mechanical precedent for immutable revisions plus a current pointer:

```text
plan_revisions
missions.current_plan_revision_id
```

The Skill Library can reuse the *mechanical revision pattern* without borrowing Company semantics.

That means:

```text
immutable Skill package revision
content/package hash
parent revision if useful
current revision pointer
```

but no Mission/Plan/acceptance semantics.

## Update race

If a Skill changes between discovery and retrieval:

```text
search -> R7 description
update -> R8 current
get(R7 ref)
```

`get` should retrieve the exact immutable R7 that search returned, not silently substitute R8.

If Sol wants the newest revision, it can search/get current again.

This is a normal identity/revision invariant, not a reasoning-state invariant.

## Relationship to continuation_context_ref

Do not overload the continuation context ref with Skill revision identity.

The continuation context ref is the current controller contract revision identity.

Skill refs remain separate immutable library references.

This keeps the meaning of the continuation context ref stable.

## Resume behavior

Recommended normal resume:

```text
1. resume current owner contract + Sol handoff + durable effect status
2. Sol reasons about the current task
3. if a reusable workflow is useful, skill_query.search(...)
4. Sol selects and loads the current Skill revision
5. continue reasoning/action
```

No automatic injection of all previously used Skills is required.

## Rejected guarantee

Soma must not claim:

```text
this Skill was cognitively active when Sol made decision X
```

unless a future runtime gives Soma a trustworthy activation event.

At most Soma may say:

```text
this immutable Skill revision was retrieved/referenced/executed as provenance
```

when it has mechanical evidence for that statement.

## Verdict

**REPO-ALIGNED CORRECTIVE RESULT.**

Do not add Skill activation state to the core continuation model.

Keep Skill revision history in the independent Soma Skill Library. Future Sol normally loads the current applicable Skill; old immutable revisions remain retrievable for explicit provenance/reproducibility needs.

The four-authority continuation design remains unchanged.

This iteration does not authorize implementation.
