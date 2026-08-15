# Iteration 32 - Soma Skill Layer: Current Ecosystem and Baseline

Date: 2026-08-15
Status: research only; provisional architecture baseline
Track: Sol-centric agent interface + Soma Skill layer

## Question

How should reusable Skills become a first-class Soma capability alongside the minimal Sol semantic re-entry architecture, without creating another planner/router or making Soma interpret model reasoning?

## External evidence

Current OpenAI and Agent Skills documentation establishes:

- Skills are reusable workflows and may contain instructions, examples, code and supporting resources.
- OpenAI Skills follow the Agent Skills open standard and are portable across supporting products.
- A Plugin can package one or more Skills together with Apps and app templates.
- Skill availability/invocation depends on plan, workspace, role and surface; therefore Soma should not make one native ChatGPT surface its only delivery path.
- The Agent Skills standard defines a directory containing at minimum `SKILL.md`, with optional `scripts/`, `references/` and `assets/`.
- `SKILL.md` requires only `name` and `description` metadata; the Markdown body is intentionally free-form.

Primary sources:

- https://help.openai.com/en/articles/20001066-skills-in-chatgpt
- https://help.openai.com/en/articles/20001256
- https://openai.com/academy/skills/
- https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx

## Current Soma repo evidence

Soma already contains a research-only Skill draft:

```text
docs/chatgpt-tool-ux/soma-engineering-skill-draft/SKILL.md
```

That draft correctly treats the Skill as workflow guidance around existing Soma MCP tools and explicitly states that the Skill does not grant permissions or replace Soma authorization.

The existing normal-Chat tool-UX plan also contains a Phase D for a Plugin + `soma-engineering` Skill, but it assumes a single packaged workflow after the MCP metadata/topology A/B test.

At this iteration, no live Soma runtime Skill registry, Skill query gateway, package loader, or canonical `skills/` authority exists in the inspected repo.

## Correction to the old Phase D assumption

The old target:

```text
winning MCP surface
  + one repo-owned Plugin
  + one soma-engineering Skill
```

is now too narrow.

The stronger target is:

```text
                 canonical Soma Skill Library
                          |
          +---------------+---------------+
          |               |               |
          v               v               v
 native ChatGPT/     Soma read surface   optional client
 Work/Codex export   for normal Chat     add-on / UI
```

The Skill package itself should remain portable. Delivery should be replaceable.

## Candidate authority split

### 1. Skill package

Use the Agent Skills package unchanged as the semantic artifact:

```text
skill-name/
  SKILL.md
  scripts/       optional
  references/    optional
  assets/        optional
```

Do not invent a `SomaSkillV1` semantic schema.

### 2. Soma Skill Registry

Soma may own only mechanical metadata required to safely identify and retrieve packages, conceptually:

```text
skill_name
package_hash / revision identity
description copied from frontmatter
source/provenance
storage location
installed/enabled state if such lifecycle is later required
```

The registry must not parse the Skill body into model-semantic fields such as steps, decisions, reasoning phases, evidence roles, or routing rules.

### 3. Skill read surface

A future narrow read surface can expose package discovery/retrieval to Sol, e.g. conceptually:

```text
capabilities
list
search
get
resource
```

This is a retrieval capability, not a semantic router.

### 4. Delivery adapters

The same canonical package may later be delivered through more than one adapter:

- native ChatGPT/Work/Codex Skill or Plugin packaging where supported;
- Soma MCP retrieval for normal Chat;
- an optional browser/client add-on for manual selection and convenience.

No adapter becomes the canonical Skill authority.

## Authority boundary

Skills are guidance, not capability.

They may teach Sol how to use Soma, but they cannot grant:

```text
repository authority
Task/Run authority
Cloudflare/SSH authority
approval
authorization
idempotency
execution rights
```

Existing Soma gateways and underlying authorities remain decisive.

## Why the open standard should be canonical

Using Agent Skills directly gives Soma:

- portability;
- no duplicate semantic format;
- compatibility with native ChatGPT/Codex support where available;
- easy export/import;
- a natural progressive-disclosure shape;
- separation of free-form model guidance from machine-owned metadata.

This directly matches the lesson from Iterations 24-31: do not force model-semantic content into rigid Soma schemas when the machine does not own that meaning.

## Rejected in this iteration

Do not make core Soma Skill architecture depend on:

```text
native ChatGPT Skill availability on one plan/surface
a browser extension
a second model that classifies which Skill to use
LocalAgent semantic routing
Supervisor semantic routing
Skill body parsing into a workflow DAG
Skill scripts bypassing normal Soma execution authority
```

## Questions for the next iterations

1. How should normal Sol discover/select a Skill without another semantic router?
2. How should full Skill content and resources be progressively loaded without bloating every tool descriptor or Chat turn?
3. Should active Skill revision(s) be mechanically associated with a continuation, or is that unnecessary?
4. How should Skill revisions be content-addressed and updated without silently changing an in-progress continuation?
5. What is the correct treatment of bundled executable scripts?
6. Can a browser add-on remain purely optional convenience rather than a required transport?

## Verdict

**EXTERNALLY SUPPORTED + REPO-ALIGNED BASELINE.**

The best current direction is a portable Agent Skills library owned mechanically by Soma, with multiple delivery adapters. The Skill body remains free-form guidance for Sol; Soma owns identity, provenance and retrieval only.

This iteration does not authorize implementation.
