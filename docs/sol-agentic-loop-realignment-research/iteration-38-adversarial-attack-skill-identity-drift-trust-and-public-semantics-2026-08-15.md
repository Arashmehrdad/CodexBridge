# Iteration 38 - Adversarial Attack: Skill Identity, Drift, Trust, and Public Semantics

Date: 2026-08-15
Status: research only; adversarial correction
Track: Sol-centric agent interface + Soma Skill layer

## Purpose

Attack Iterations 32-37 before producing a final Skill-layer synthesis.

The preferred candidate entering this iteration was:

```text
portable Agent Skills packages
external private Soma Skill Library
immutable full-package revisions
skill_query
skill_action
Sol selects Skills
Skill scripts execute only through existing Task/Run authority
no Skill activation state in continuation
```

This iteration tries to break that model.

## External semantics checked

The current MCP ToolAnnotations specification states:

- `readOnlyHint=true`: the tool does not modify its environment;
- `destructiveHint=true`: the tool may perform destructive updates;
- `destructiveHint=false`: the tool performs only additive updates;
- `idempotentHint=true`: repeated same-argument calls have no additional effect;
- `openWorldHint=false`: the tool acts within a closed domain rather than an open external world.

These are hints, not authorization controls.

Primary source:

- https://modelcontextprotocol.io/specification/2025-11-25/schema

The Agent Skills/OpenAI sources used in prior iterations remain authoritative for Skill package/loading behavior.

## Attack 1 - `skill_action` annotation was overstated

Iteration 37 proposed a candidate `destructiveHint=false` for a revision-preserving Skill mutation surface.

That is not yet justified.

Creating a new immutable revision is clearly additive.

But:

```text
set_current
rollback
enable/disable
```

change effective library state. Even if old revisions remain recoverable, they are not obviously "only additive updates" under the MCP wording.

### Correction

Do not freeze `destructiveHint=false` at research time.

The final implementation must either:

1. keep one `skill_action` and annotate it conservatively according to its broadest operation; or
2. split additive revision import from effective-state mutation if live UX measurement proves the conservative annotation materially harms normal use.

Do not create a third gateway merely to make the annotation prettier before measurement.

This is a correction to Iteration 37.

## Attack 2 - mutable canonical package folders break immutable refs

Suppose the canonical external library contains:

```text
skills/arash-research/SKILL.md
```

and `skill_ref=R7` hashes those bytes.

If the owner or another program edits the directory in place, R7 no longer identifies stable bytes.

### Correction

The canonical installed library must preserve immutable revision snapshots.

A mutable authoring/workspace copy may exist separately, but an installed `skill_ref` must resolve to immutable package bytes.

Out-of-band mutation of an installed snapshot is corruption/drift, not an in-place update.

On read, Soma should verify revision/package identity sufficiently to avoid silently serving changed bytes under the same immutable ref.

## Attack 3 - same Skill name from two sources

Agent Skills uses `name` as the portable Skill identity presented to the agent, but Soma also needs provenance.

Dangerous behavior:

```text
current arash-research from owner
import external arash-research from web
-> silently replaces current
```

### Correction

One current installed revision may exist per canonical Skill name in the Soma library, but importing another package with the same name must not silently change the current revision unless the mutation explicitly requests replacement/activation.

The new package may be recorded as a candidate/new revision with provenance.

`skill_ref`, not name alone, is the immutable revision identity.

## Attack 4 - native ChatGPT Skill and Soma Skill diverge

Because OpenAI Skills can be downloaded/uploaded separately and personal Skills may not sync automatically across surfaces, a native installed Skill and the Soma-managed copy can diverge.

### Correction

Accept this as two explicit installations/adapters.

Soma must not claim automatic synchronization with native ChatGPT/Codex Skill state.

Flow is explicit:

```text
Soma export -> native install
native export/download -> Soma import
```

If both copies exist with the same name but different content, no hidden merge occurs.

## Attack 5 - search index points to stale/corrupt package

A derived search index may say current revision is R8 while package bytes are missing/corrupt or the current pointer changed.

### Correction

Search/list is discovery only.

`get(skill_ref)` must resolve and verify the exact immutable revision rather than trusting search metadata as package authority.

If index/current-pointer reconciliation is needed, rebuild/reconcile mechanically. Do not silently substitute a different revision under the requested ref.

## Attack 6 - malicious Skill body/description

A Skill is intentionally instructions for the agent, so ordinary prompt-injection language inside an installed Skill cannot be treated exactly like inert web content. But externally sourced Skills can be malicious or over-broad.

OpenAI itself scans uploaded Skills and still tells users to review/trust the source.

### Boundary

Soma should preserve provenance and package identity, but should not pretend to semantically certify the Skill body.

Critical guarantees remain mechanical:

- a Skill does not grant Soma tool authority;
- scripts are inert until routed through existing execution authority;
- a Skill cannot install/update another Skill merely because its text requests it;
- external import/update remains an explicit Skill-library mutation;
- normal instruction hierarchy remains the model/runtime's responsibility.

A future static scanner may add value, but correctness must not depend on perfect malicious-instruction classification.

## Attack 7 - Skill self-modification loop

Dangerous pattern:

```text
loaded Skill says "update me from URL X"
Sol automatically skill_action.import(...)
new Skill says repeat
```

### Correction

Skill content alone is not sufficient authority to mutate the Skill Library.

Skill-library changes must come from the user's current request or another legitimate controller decision, not merely from instructions contained inside the package being changed.

This is analogous to the rule that Skill content cannot grant execution authority.

## Attack 8 - two Skills conflict

Example:

```text
soma-engineering says inspect before mutation
fast-edit says edit immediately
```

### Result

No Soma merge/conflict-resolution engine.

Sol receives exact Skill bodies and reasons under normal instruction precedence/current user intent.

Soma can report which exact revisions were retrieved, but cannot decide semantic precedence between them.

## Attack 9 - browser/native adapter becomes hidden authority

If an optional browser add-on or native plugin holds its own mutable copy of the Skill library, the architecture splits.

### Correction

Adapters may cache/display/export, but Soma-managed workflows use the canonical Soma Skill Library when operating through Soma.

Any imported external/native change must become an explicit Soma revision before `skill_query` serves it as a Soma Skill.

## Attack 10 - continuation pressure

Could exact Skill revision retrieval be mistaken for "active reasoning state" and pull us back toward `continuation_skill_links`?

No.

Mechanical retrieval provenance may be useful for audit, but no default continuation activation state is required.

Fresh Sol should normally use the current applicable Skill.

## Attack 11 - package provenance becomes semantic trust score

Avoid fields like:

```text
trust_score = 0.82
safe = true
approved_reasoning = true
```

unless backed by a real external authority with defined semantics.

Mechanical provenance is enough for v1:

```text
source kind
source location/ref if appropriate
imported_by/request identity
package hash
created/imported time
current/not-current
```

## What survives

The core candidate survives:

```text
Agent Skills package format
external private canonical library
immutable full-package revisions
one skill_query
one skill_action candidate
Sol chooses Skills
progressive pull loading for normal Chat
scripts use existing Task/Run execution authority
native/browser routes are adapters
no Skill state in continuation
```

## Corrections made

1. Retract the frozen `skill_action destructiveHint=false` claim.
2. Installed Skill revisions must be immutable snapshots, not mutable current folders.
3. Same-name imports cannot silently replace current revision.
4. Native/Soma copies do not auto-sync.
5. Skill content cannot self-authorize Skill-library mutation.
6. Search/index metadata is not package authority.

## Verdict

**ADVERSARIAL PASS WITH MATERIAL CORRECTIONS; CORE ARCHITECTURE SURVIVES.**

The remaining questions are mostly real-workflow/product acceptance questions rather than unresolved authority contradictions.

Next iteration should pressure-test the candidate against actual Soma/Arash workflows before final synthesis.

This iteration does not authorize implementation.
