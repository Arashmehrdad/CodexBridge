# Iteration 33 - Normal-Chat Skill Discovery, Progressive Loading, and Gateway Boundary

Date: 2026-08-15
Status: research only; provisional recommendation
Track: Sol-centric agent interface + Soma Skill layer

## Question

How can normal Sol/Chat discover and load Soma Skills without a second semantic router, without loading every Skill into every Chat context, and without making a browser add-on mandatory?

## External evidence

The Agent Skills standard uses progressive disclosure:

```text
1. discovery metadata: name + description
2. full SKILL.md after activation
3. referenced resources only when needed
```

The standard recommends keeping the main Skill compact and loading references/scripts/assets on demand.

OpenAI likewise states that installed Skills can be selected automatically by ChatGPT or explicitly by mention when the native Skill surface is available.

Primary sources:

- https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx
- https://agentskills.io/client-implementation/adding-skills-support
- https://openai.com/academy/skills/

## Constraint unique to normal Chat + Soma

Soma does not own ChatGPT's system/context initialization. Therefore it cannot guarantee that every normal Chat starts with the full Soma Skill catalog in model context.

Trying to emulate native startup injection by placing every Skill description into every Soma public tool descriptor would:

- grow the public descriptor continuously with the Skill library;
- couple Skill-library size to MCP routing cost;
- require descriptor refresh whenever a Skill changes;
- mix workflow content with tool capability metadata.

That is the wrong boundary.

## Candidate routes

### A. Browser add-on injects Skill content

Useful for UI convenience, but rejected as a core dependency.

Reasons:

- browser DOM/product behavior can change;
- does not naturally cover desktop/mobile/other clients;
- would make a client extension the required authority for Skill delivery;
- duplicates capability already available through Soma's connected tool surface.

Keep only as an optional adapter later.

### B. Put Skills inside `knowledge_query`

Rejected.

Skills are executable/procedural guidance packages with open-standard package identity and optional bundled resources. Canonical project memory/wiki/knowledge have different authority and lifecycle semantics.

Merging the two would blur an existing public boundary and recreate a broad mixed gateway.

### C. Read Skills through `repo_query`

Rejected as the canonical path.

It can inspect repo-owned Skill files during development, but it requires the model to know repository paths, cannot represent installed/personal packages cleanly, and turns a package abstraction into filesystem trivia.

### D. One dedicated read-only `skill_query`

Best current candidate.

Conceptual operations:

```text
capabilities
list
search
get
resource
```

The tool itself is small and stable even if the Skill library grows.

## Selection authority

**Sol selects the Skill.**

Soma must not run a second model, LocalAgent classifier, Supervisor router, or hidden planner to choose Skills.

A normal path becomes:

```text
Sol decides a stored workflow may help
  -> skill_query.search(task terms)
  -> Soma returns bounded name/description/revision refs
  -> Sol chooses zero/one/many Skills
  -> skill_query.get(skill_ref)
  -> Sol follows the free-form instructions
  -> skill_query.resource(...) only when referenced material is needed
```

Soma search may be deterministic over mechanically indexed metadata such as name and description. Search ranking is retrieval, not semantic authority. The model supplies the query and chooses the result.

## Why pull-on-demand is better for Soma

The open standard normally assumes a client can load all Skill names/descriptions at session start.

Normal Chat + Soma does not own that session-start boundary.

Therefore Soma should use a compatible **pull form of progressive disclosure**:

```text
native Skill host:
  metadata automatically present -> activate body -> load resource

Soma normal Chat:
  one visible skill_query capability -> search metadata -> get body -> load resource
```

The semantic package remains identical. Only discovery transport differs.

## Repo fit

Current Soma public tool topology already uses narrow public gateway identities plus an authoritative human-facing metadata registry.

Current inspected facts:

- `PUBLIC_GATEWAY_INVENTORY` contains 34 public tools.
- `public_tool_metadata.py` requires one explicit metadata record per public gateway.
- the normal-Chat tool-UX work explicitly values trigger-first descriptions and truthful read/write annotations.

Therefore one new pure-read `skill_query` is architecturally cleaner than overloading `knowledge_query`, `repo_query`, or `system_query`.

If implemented, the tool should be described narrowly, conceptually:

> Use this when you need to discover or read reusable Soma Skills and their referenced resources. It does not execute Skill scripts or grant the permissions described by a Skill.

The additional tool still needs the normal public-descriptor/routing evaluation; this iteration does not assume a 35th tool is free of catalog cost.

## Candidate result shapes

### Search/list result

Only mechanical discovery fields:

```text
skill_ref
name
description
package_hash
provenance summary
compatibility summary if present
```

Do not return the entire SKILL.md for search/list.

### Get result

Return:

```text
skill_ref
package_hash
frontmatter
SKILL.md body
bounded package manifest
```

Do not parse the body into workflow steps.

### Resource result

Return the exact referenced file identity/content through Soma's existing bounded/chunked projection conventions where necessary.

A resource read must not execute a script.

## Multiple Skills

OpenAI documents that multiple Skills may be combined for multi-phase work.

Soma should not create a merge engine.

Sol may load multiple immutable Skill revisions and reconcile their instructions in context under normal instruction precedence. If two Skills conflict, Soma has no semantic basis to choose the winner.

## Manual use

The simplest reliable manual UX in normal Chat is:

```text
owner: use the arash-research skill for this
Sol: skill_query.search/get -> applies it
```

An optional browser add-on can later expose a picker and insert the selected Skill name/ref into the user's message. It does not need hidden prompt injection and does not become required for correctness.

## Rejected guarantees

Soma cannot honestly promise:

```text
I automatically selected the best Skill.
I know this task requires a Skill.
I merged conflicting Skill instructions correctly.
I executed bundled scripts because the Skill asked me to.
```

It can promise:

```text
I can discover packages by mechanically indexed metadata.
I can return an exact immutable Skill revision.
I can return referenced files on demand.
I can identify package provenance and content hashes.
```

## Verdict

**REPO-BACKED RECOMMENDATION:** use one dedicated read-only `skill_query` as the normal-Chat retrieval adapter, with Sol owning Skill selection and the open Skill package remaining opaque/free-form to Soma.

The browser add-on remains optional convenience, not architecture-critical transport.

Next research question: Skill revision identity, package provenance/trust, bundled scripts, and whether active Skill refs should be pinned into the continuation contract.

This iteration does not authorize implementation.
