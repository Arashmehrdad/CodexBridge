# Iteration 37 - Skill Public Gateway, Lifecycle, and Normal-Chat Plan Integration

Date: 2026-08-15
Status: research only; repo-backed public-surface candidate
Track: Sol-centric agent interface + Soma Skill layer

## Question

What is the smallest truthful Soma public surface for discovering, reading, creating/updating, and rolling back Skills, and how should it interact with the existing normal-Chat tool-UX plan?

## External evidence

Current OpenAI Skills behavior supports both automatic/native use and manual creation/upload/install on eligible surfaces. OpenAI Skills use the Agent Skills open format and can be moved between supporting products.

The Agent Skills standard makes package discovery and activation a client/runtime concern while keeping the package format portable.

Primary sources:

- https://help.openai.com/en/articles/20001066-skills-in-chatgpt
- https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx
- https://openai.com/academy/skills/

## Current Soma repo evidence

Current `PUBLIC_GATEWAY_INVENTORY` contains 34 public Soma gateways.

The normal-Chat tool-UX architecture already prefers:

- narrow, truthful public gateway identities;
- trigger-first descriptions;
- explicit read/write/destructive/open-world annotations;
- avoiding mixed semantic gateways where practical;
- measuring public catalog cost rather than assuming more tools are free.

The old implementation plan's Phase D assumed:

```text
winning MCP surface
+ repo-owned Plugin package
+ one soma-engineering Skill
```

Iterations 32-36 show that this is now too narrow because the desired capability is a reusable Soma Skill Library independent of one native ChatGPT surface.

## Rejected public shapes

### One MCP tool per Skill

Rejected.

It would make public tool count scale with library size, force descriptor refresh on Skill changes, and mix workflow discovery into MCP capability topology.

### Put Skill operations into `knowledge_query/action`

Rejected.

Skills have independent package/revision/resource/execution semantics and should not broaden an already distinct Knowledge authority.

### Put Skill operations into `repo_query/apply`

Rejected as canonical public UX.

Repo tools may inspect built-in Skill source during development, but installed/private portable Skills should not require filesystem/repository knowledge.

### Native Plugin/Skill packaging as the only route

Rejected as core architecture.

Native packaging is valuable where available, but eligibility and surface behavior vary. Soma's canonical library should remain usable from normal Chat through Soma itself.

## Preferred public surface

Exactly two conceptual gateways:

```text
skill_query
skill_action
```

Library size does not change the MCP tool count.

## `skill_query`

Pure read/retrieval surface.

Conceptual operations:

```text
capabilities
list
search
get
history
resource
```

### `list/search`

Return bounded discovery metadata only:

```text
skill_ref
name
description
current flag
package_hash
source/provenance summary
compatibility summary if present
```

Do not return all SKILL.md bodies.

### `get`

Return exact immutable revision metadata + SKILL.md + bounded manifest.

### `history`

Return immutable revision refs/hashes/timestamps/provenance, not package bodies unless requested.

### `resource`

Return one exact relative-path resource from one immutable revision with its resource hash.

Reading a script does not execute it.

### Candidate public annotations

Conceptually:

```text
readOnlyHint   true
destructiveHint false
idempotentHint true
openWorldHint false
```

The library is local/private Soma state, not an external provider.

## `skill_action`

Local Skill-library mutation surface.

V1 should stay revision-preserving and reversible.

Conceptual operations:

```text
import/create_revision
set_current
rollback
set_enabled   optional if enable/disable is actually needed
```

Do not include permanent purge/delete in the first mixed action surface unless a measured need justifies a separate destructive operation.

### Update semantics

Recommended update pattern:

```text
current R7
new package bytes
  -> validate open Skill format
  -> compute package hash
  -> same hash? replay existing R7/Rx
  -> new hash? create immutable R8
  -> atomically move current pointer when requested
  -> retain R7
```

Rollback is pointer movement to an existing immutable revision, not destructive rewrite.

### Request idempotency

Mutation requests should use normal Soma request-id/hash replay semantics where appropriate so lost responses do not create duplicate revision records or ambiguous pointer moves.

Content hash remains the canonical package identity.

### Candidate public annotations

Conservative conceptual values:

```text
readOnlyHint    false
destructiveHint false    # v1 excludes permanent purge
aidempotentHint false     # unless every operation is formally replay-safe at gateway contract
openWorldHint   false
```

The implementation plan must use the actual current MCP annotation semantics when finalizing these values.

## Skill creation/editing UX

Normal Chat can support:

```text
owner: update my arash-research Skill with what we learned
Sol:
  skill_query.search/get current
  drafts/constructs updated Agent Skills package
  skill_action creates immutable revision + activates it
  reports old ref -> new ref
```

Soma does not need to understand the Skill's semantic body to persist it.

The model authors the free-form Skill package; Soma validates package shape, paths, hashes and revision mechanics.

## Do we need preview/apply for every Skill edit?

Not as a core architectural requirement.

Unlike an in-place source-code rewrite, a Skill update can be inherently reversible if every update creates an immutable revision and preserves the predecessor.

The UI/Skill action may still return a diff/summary before activation, and an implementation may separate `create_revision` from `set_current`, but the architecture does not require a heavyweight repo-style patch lifecycle simply to achieve rollback safety.

If user experience later shows accidental activation is a problem, activation can become a separate explicit operation without changing package authority.

## Browser add-on

Remain optional.

A client add-on may provide:

- Skill picker;
- active/manual selection display;
- one-click insertion of Skill name/ref;
- library management UI.

But it should call/use the same Soma Skill Library and not own package bytes or semantic routing.

## Native ChatGPT/Work/Codex adapter

Native Skills/Plugins become an adapter/export route:

```text
Soma immutable Skill revision
   -> exact Agent Skills package export
   -> install/upload/package in native compatible product
```

Native product state is not the canonical Soma Skill registry.

Likewise, an exported Skill changing inside another product does not silently mutate Soma. It must be explicitly re-imported/synchronized if desired.

## Correction to old normal-Chat Phase D

For future planning authority, reinterpret the old Phase D as superseded by this research lane.

Old:

```text
Phase D = package one soma-engineering Skill into a Plugin
```

New candidate:

```text
Phase D1 = Soma Skill Library + skill_query
Phase D2 = Skill revision mutation lifecycle via skill_action
Phase D3 = native Plugin/Skill export/install adapter where useful
Phase D4 = optional browser/client UX adapter only if it adds measurable value
```

This does not alter the separate MCP metadata/topology A/B evidence; it changes what the workflow-Skill phase should mean after that work.

## Relationship to Sol continuation

No new continuation table or activation state.

Skills remain reusable guidance.

If a Skill-derived action creates a canonical Task/Run, normal continuation effect linking applies to that Task/Run when a context ref is supplied.

## Verdict

**REPO-BACKED PUBLIC-SURFACE CANDIDATE.**

Use one read-only `skill_query` and one revision-preserving `skill_action`. Do not expose one tool per Skill. Native Plugin/Skill packaging and a browser add-on are adapters, not the canonical architecture.

The old normal-Chat Phase D should be superseded for future planning by the Soma Skill Library research once this lane finishes adversarial review.

This iteration does not authorize implementation.
