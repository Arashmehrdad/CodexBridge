# LEGACY-RETIREMENT-AUDIT-1 — Pre-V3 Compatibility and Retirement Map

**Date:** 2026-07-29
**Status:** prepared for owner review; not authorised or executed.
**Decision level:** repository-wide audit and retirement classification only.
**Follows:** [`PUBLIC_CAPABILITY_METADATA_1_RESULT_2026-07-29.md`](PUBLIC_CAPABILITY_METADATA_1_RESULT_2026-07-29.md) and [`lifecycle-authority-inventory-2026-07-26.md`](lifecycle-authority-inventory-2026-07-26.md).

## Purpose

Reduce accidental complexity before Roadmap V3 without deleting compatibility,
historical evidence, recovery paths, or still-live runtime dependencies.

The audit must answer four separate questions:

1. Which paths are live and should remain?
2. Which paths are no longer allowed to create new state but must remain readable?
3. Which paths may be retired only after a named migration or replacement?
4. Which paths are demonstrably dead and suitable for a later bounded removal lane?

This gate produces the map. It does **not** perform the removals.

## Governing rule

A path is not dead merely because no obvious import was found.

Retirement requires evidence across runtime registration, startup, public MCP
contracts, configuration, packaging, durable state, migrations, tests,
historical evidence, controller compatibility, and owner workflows. Unknown
external consumption is a blocker, not permission to guess.

## Authority granted when started

The executing controller may perform read-only repository inspection, bounded
static analysis, import and startup smoke checks, public discovery comparison,
live configuration inspection with secrets redacted, and read-only durable-state
inventory.

It may create only:

- `docs/LEGACY_RETIREMENT_AUDIT_1_RESULT_2026-07-29.md`;
- `docs/legacy-retirement-audit-1-manifest-2026-07-29.json`;
- the corresponding status update in `PLANS.md`.

No production source, test, schema, configuration, credential, connector,
database, vault, run record, artifact, or external service may be changed.

## Required classification

Every audited item must receive exactly one classification:

| Classification | Meaning |
|---|---|
| `keep_live` | Active authority or dependency; new use remains supported. |
| `keep_compatibility_read` | No new writes or activation, but historical data or public compatibility still requires reads. |
| `freeze_no_new_use` | Must remain temporarily, but new callers and new state are prohibited. |
| `migrate_then_retire` | Retirement is valid only after a named, testable migration or replacement. |
| `remove_candidate` | Proven to have no live runtime, public-contract, durable-state, migration, packaging, evidence, or external-consumer responsibility; removal still requires a separate implementation lane. |
| `defer_v3_consolidation` | Overlap is real, but retirement requires architectural consolidation that belongs in Roadmap V3. |
| `unknown_blocked` | Evidence is insufficient or contradictory; no retirement action is permitted. |

## Required inventory surfaces

The audit must cover, at minimum:

1. **Runtime and startup:** imports, lazy imports, dependency injection, service
   startup, background workers, registry population, CLI/module entry points and
   optional feature activation.
2. **Public contracts:** all 32 gateway registrations, operation variants,
   strict output schemas, compatibility aliases, public projections and
   controller-visible metadata.
3. **Durable state:** SQLite tables and migrations, run-directory formats,
   state files, checkpoints, artifacts, evidence references, old terminal values
   and read compatibility.
4. **Configuration and packaging:** config models, environment variables,
   dependency declarations, package exports, installation entry points and
   ignored live configuration.
5. **Tests and fixtures:** tests that protect current behaviour versus tests that
   only preserve a closed experiment. Test-only imports are not by themselves a
   reason to keep production code.
6. **Historical and owner-facing evidence:** committed result documents,
   machine-readable evidence, vault content, repository wiki references and
   owner workflows that still depend on a path or identifier.
7. **External consumption:** ChatGPT, Claude Code, Hermes, CodexBridge, Trading
   Lab and any documented external client or connector contract. Unknown use
   must be recorded explicitly.

## Minimum candidate set

The audit must classify at least these already-evidenced candidates without
pre-judging their outcome:

- `soma/pilot_memory_1b/` and `tests/test_pilot_memory_1b.py`;
- `soma/local_agent/orchestrator.py` separately from shared local-agent models,
  audit and durable-command primitives;
- `soma/local_coding/` and its approval dependency;
- `soma/policy/approval_store.py`, approval configuration and live
  `NEEDS_APPROVAL` compatibility;
- the legacy `soma/memory/` authority and all remaining read/import duties;
- generic `soma.knowledge` legacy operations versus the canonical memory and
  research authorities;
- `LEGACY_READ_ONLY_TOOLS`, historical terminal values and schema-migration
  readers;
- the dead `RepoWikiService.wiki_exclusions` constructor path recorded by the
  lifecycle inventory;
- workflows, supervisors, command groups and long-run jobs as possible
  `defer_v3_consolidation` items rather than deletion targets;
- stale source, cache or generated directories that may be artifacts rather
  than tracked product code.

The controller must add other candidates discovered during the inventory rather
than limiting the result to this seed list.

## Evidence required per item

The machine-readable manifest must record:

- stable item ID, path or symbol set and subsystem owner;
- current responsibility and whether it creates new state;
- all in-repository producers and consumers;
- public gateway, schema or projection exposure;
- durable tables, rows, files, migrations or historical identifiers involved;
- startup, packaging, configuration and service references;
- relevant tests and whether they protect live behaviour or historical evidence;
- known external consumers and unresolved external-consumer risk;
- selected classification and confidence;
- exact blockers or retirement prerequisites;
- recommended successor lane, if implementation is warranted.

Every `remove_candidate` must include affirmative proof for each required
surface. “No grep hit” is not sufficient evidence.

## Required dynamic checks

The audit must use the live repository and include bounded checks that prove:

- a fresh process can enumerate the current public tools and operation inventory;
- startup registration and optional-service imports are accounted for;
- current configuration fields map to a real consumer or are classified;
- historical stores and migrations remain readable;
- the repository is clean before and after the audit;
- no inspection step mutates durable state.

Where a dynamic check cannot be run safely, the item becomes `unknown_blocked`
and the missing evidence is recorded.

## Required outputs

The result document must provide:

1. an executive summary of how much code is genuinely removable before V3;
2. the complete classification matrix grouped by subsystem;
3. a proposed smallest first removal batch containing only
   `remove_candidate` items;
4. separate migration proposals for `migrate_then_retire` items;
5. a V3 input section for `defer_v3_consolidation` items;
6. explicit “do not remove” compatibility boundaries;
7. the exact next owner decision.

The JSON manifest is authoritative for the item-level classification. The
Markdown result explains the reasoning and successor sequence.

## Explicit exclusions

This gate does not authorise:

- deleting, moving, renaming or editing production source or tests;
- changing gateway names, operation schemas, response envelopes or public
  metadata;
- changing state vocabularies, task backends, lifecycle ownership, leases,
  publication paths or reconciliation contracts;
- migrating or deleting SQLite rows, run directories, evidence, artifacts,
  vault records or historical files;
- changing configuration, dependencies, credentials, connectors, services,
  deployment or startup behaviour;
- personal memory, conversation ingestion, provider work, code-intelligence
  activation, RAGFlow deployment or Cortana presence work;
- merging to main or performing unrelated cleanup.

## Stop conditions

Stop and publish `unknown_blocked` findings without implementation if:

- unrelated owner work appears in the worktree;
- a candidate has unresolved public or external consumers;
- historical state cannot be read or attributed safely;
- removal would require a public contract change, migration or architectural
  consolidation;
- static and dynamic evidence disagree;
- inspection would require credentials, production mutation or destructive
  commands;
- the audit expands into code modification or Roadmap V3 implementation.

## Acceptance outcome

The gate may close only as one of:

- **audit-complete** — every required surface and candidate is classified, the
  manifest and result agree, and no product state changed; or
- **audit-blocked** — exact evidence gaps are recorded and no retirement claim
  is made for blocked items.

A completed audit does not itself authorise deletion. The owner must approve a
separate, bounded implementation lane for the selected `remove_candidate`
batch.

## Owner start language

A sufficient start instruction is:

> Start LEGACY-RETIREMENT-AUDIT-1 exactly as prepared. Produce the repository-wide keep, compatibility-read, freeze, migrate, remove-candidate and V3-consolidation map using static and bounded dynamic evidence. Do not delete or edit product code, tests, schemas, configuration, durable state or external services. Treat unknown external use and contradictory evidence as blockers. Close with the Markdown result, machine-readable manifest and PLANS.md status only.
