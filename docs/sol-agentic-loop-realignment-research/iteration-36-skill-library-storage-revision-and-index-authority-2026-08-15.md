# Iteration 36 - Skill Library Storage, Revision and Index Authority

Date: 2026-08-15
Status: research only; repo-backed storage direction
Track: Sol-centric agent interface + Soma Skill layer

## Question

Where should Soma's canonical Skill Library live, what exactly constitutes a Skill revision, and which record is authoritative versus merely an index/cache?

## External evidence

Agent Skills defines a Skill as a directory/package rooted at `SKILL.md`, with optional scripts, references, assets and other files. The package is intended to be portable and version-controlled.

The specification validates package shape and frontmatter but does not prescribe one universal distribution/storage backend for every agent implementation.

OpenAI also supports downloading/uploading Skills across supporting products, reinforcing that the package itself should remain portable rather than being trapped in one internal database representation.

Primary sources:

- https://github.com/agentskills/agentskills/blob/main/docs/specification.mdx
- https://github.com/agentskills/agentskills
- https://help.openai.com/en/articles/20001066-skills-in-chatgpt

## Current Soma repo evidence

Soma already distinguishes different durability classes.

`AppConfig.resolve_runs_dir()` provides a runtime/data root for Runs, Task/Company stores, approvals, local supervisor artifacts and similar operational state.

More importantly, `CanonicalMemoryConfig` explicitly documents that owner-readable canonical memory should have a production home in an externally configured private vault, outside code repositories and outside `runs/`. The old `runs/` location is retained only as a legacy fallback.

That is a strong architectural precedent for user-owned durable artifacts that need to remain independently accessible and portable.

## Classification of Skills

A Skill package is not:

- a Run artifact;
- a Task result;
- repository source code by default;
- canonical project memory;
- continuation state.

It is a reusable owner/user workflow artifact consumed by agents across tasks and potentially across products.

Therefore its canonical bytes should not be buried inside transient Run directories or implicitly tied to the Soma source checkout.

## Preferred storage model

### Canonical Skill content

Production intent should be an owner-configured private Skill root outside `runs/` and outside normal code repositories.

Conceptually:

```text
SkillLibraryConfig
  skill_library_root = absolute owner-configured directory
```

A legacy/development fallback under `runs/skills/` may be mechanically convenient during development, but should not be confused with the preferred owner-facing location.

This mirrors the canonical-memory external-vault lesson without making Skills part of canonical memory.

### Built-in/repo Skills

The Soma repository may contain built-in/default/read-only Skill packages such as `soma-engineering`.

Those should be treated as seed/source packages, not the sole canonical home of user-created Skills.

Conceptually:

```text
repo seed skills
    -> import/install into owner Skill Library
```

or exposed as read-only bundled Skills with explicit source provenance.

## What a Skill revision hashes

The revision identity must cover the entire portable package, not only `SKILL.md`.

Changing any of these may change behavior:

```text
SKILL.md
scripts/*
references/*
assets/*
other valid package files
```

Therefore:

```text
package_hash = deterministic hash(relative paths + exact file bytes)
```

with normalized path ordering and explicit exclusions only for non-package transport metadata if such metadata is introduced.

Do not use frontmatter `metadata.version` as the authoritative revision identity. It is user-supplied semantic metadata and may be missing, duplicated or inaccurate.

## Immutable revision + current pointer

Recommended mechanical model:

```text
skill identity
  stable name
  current_revision_ref

skill revision
  immutable package_hash
  package location/blob ref
  package metadata snapshot
  provenance/source
  created/imported timestamp
  parent revision ref if useful
```

Updating a Skill creates a new immutable revision and atomically moves the current pointer.

Old revisions remain retrievable.

This follows the useful mechanical pattern already present in Company Kernel immutable plan revisions, without inheriting Company semantics.

## Search/index authority

Search needs cheap metadata:

```text
name
description
current revision ref
optional compatibility/source labels
```

A database/catalog index may store these values for fast `skill_query.search`, but the index should not become the canonical semantic package body.

If the index disagrees with the immutable package bytes/hash, the package identity wins and the index should be rebuilt/reconciled.

Conceptually:

```text
canonical package bytes
      |
      v
validated immutable revision
      |
      +--> derived searchable catalog/index
```

## Import/update idempotency

Package import/update should be content-idempotent.

Conceptually:

```text
same skill + same package_hash
  -> return existing revision

same skill + new package_hash
  -> create new immutable revision
  -> optionally/currently move current pointer according to requested operation
```

Request-level idempotency may also be useful for mutation retries, but package identity remains content-derived.

## Name and path validation

The open standard requires the Skill name to match the parent directory name and restricts valid names.

Soma should validate package structure before indexing/activation.

At minimum the implementation must prevent:

```text
path traversal
absolute paths inside package manifests
resource escape outside package root
duplicate/case-colliding paths on Windows
symlink/reparse escape if archives/directories are imported
package hash ambiguity from path normalization
```

These are package-integrity concerns, not semantic reasoning checks.

## Native-product interoperability

Because the canonical artifact remains an Agent Skills package, Soma can later support:

```text
export exact revision -> upload/install in ChatGPT/Codex/other compatible client
import compatible package -> validate -> store immutable Soma revision
```

No semantic conversion layer should be required.

## Relationship to normal Chat

Normal Chat does not need filesystem paths.

It should receive opaque immutable refs through `skill_query`:

```text
search -> current skill_ref
get(skill_ref) -> SKILL.md
resource(skill_ref, relative_path) -> exact resource
```

This prevents the model from having to understand local storage layout.

## Relationship to continuation

No change to Iteration 34.

The Skill Library owns Skill revision history independently. Continuation does not gain Skill lifecycle fields.

## Verdict

**REPO-BACKED STORAGE DIRECTION.**

Canonical user Skill packages should live in an owner-configured external private Skill library, with immutable full-package revisions and a current pointer. A Soma catalog/database may index/search those revisions but must remain derivative of the validated package identity. Repo Skill folders are seeds/built-ins, not the only home for user workflows.

This iteration does not authorize implementation.
