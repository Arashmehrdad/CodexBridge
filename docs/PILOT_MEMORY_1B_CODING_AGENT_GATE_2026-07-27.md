# PILOT-MEMORY-1B - Hardened Shadow Benchmark Coding-Agent Gate

**Date:** 2026-07-27
**Status:** active and owner-authorized. Coding-agent work may begin immediately.
**Authority:** shadow benchmark only; no production memory authority or integration.
**Starting HEAD:** `b1d604eb6eedaded5db541be12d220752e4ccf9a`
**Machine-readable gate:** [`pilot-memory-1b-coding-agent-gate-2026-07-27.json`](pilot-memory-1b-coding-agent-gate-2026-07-27.json)

## Why this lane exists

`PILOT-MEMORY-1` proved that a ten-note Markdown + Git corpus with Obsidian-native links can pass seven clean, substring-oriented questions. It did **not** prove that the baseline survives realistic supersession, paraphrased retrieval, metadata drift, or scale. Its index hash was `fcaa442c7d1a2c7d24cb18f8e565801c26365117c73a1256ebe2766aeaf729d4`.

ProjectScope is now live and enforced, so the next useful question is no longer whether memory *can eventually be scoped*. It is whether the smallest owner-readable baseline is actually good enough before Soma adopts or builds anything more complicated.

## Decision question

Can canonical Markdown + Git, Obsidian-compatible links, exact opaque project identity, and a fully rebuildable derived index reliably answer current-fact, temporal, semantic, relational, provenance, and project-isolation questions at realistic complexity and scale?

The pilot is successful when it produces trustworthy evidence, including an honest failure. It is not required to make the baseline pass.

## Authority and safety boundaries

- Canonical memory content remains ordinary Markdown files. Git provides history and external-edit provenance.
- Any index, SQLite database, embedding, cache, or generated relation structure is derived, disposable, and reproducible from canonical files.
- Every record carries an exact opaque `project_id`. Folder names, repository names, note paths, conversation context, and human-readable project names must never supply project identity implicitly.
- The fixed project identities are:
  - Soma: `proj_a144f759-1619-4276-9292-28704b6611f4`
  - confusing sibling project: `proj_0cf013d0-191b-57f4-a84b-7a43819a1578`
- Unscoped retrieval must fail closed. Cross-project relations must be explicit and typed or rejected.
- The live Soma store, ProjectScope tables, production MCP schemas, `.soma/wiki/`, repository knowledge, Hermes, and owner memory remain untouched.
- No production vault is created. No personal secrets or unredacted private history are used; the corpus is synthetic or sanitized.
- No Basic Memory, Graphiti, Cognee, Mem0, Letta, or other memory service is installed or evaluated in this lane.
- No network-dependent model or API may be required for reproducibility. A pilot-only local method is allowed only when it remains optional, derived, removable, and separately reported from the lexical baseline.
- Generated 1,000- and 10,000-note corpora live outside tracked repository paths and are removed after evidence is captured.
- Preserve the existing `PILOT-MEMORY-1` evidence. Do not rewrite its result to make the new benchmark look cleaner.
- Do not change unrelated architecture, delete owner work, rewrite history, or push.

## Required benchmark shape

The curated corpus contains **50-100 representative records** across the two deliberately similar projects. It must include facts, decisions, lessons, procedures/skills, source references, and typed relationships, with enough near-duplicate language to make accidental project leakage plausible.

The corpus and generated scale sets must exercise:

1. exact recall;
2. multi-hop full supersession such as `A <- B <- C`;
3. partial claim-level supersession where an old note remains partly current;
4. contradictions, duplicates, and current-fact precision;
5. paraphrased or meaning-based questions that do not repeat the note's key wording;
6. one-hop and multi-hop relation questions;
7. moved, renamed, deleted, stale, malformed, and missing sources/frontmatter;
8. edits made outside the benchmark tool and attributable through Git;
9. deletion and dangling-link detection;
10. deterministic full rebuild from canonical files only;
11. confusion-resistant project isolation and mandatory unscoped rejection;
12. cold rebuild, warm query, and resource measurements at roughly 100, 1,000, and 10,000 notes.

A deterministic seed, corpus manifest, golden answers, scoring rules, operational time budgets, and failure thresholds must be frozen **before the first measured run**. They may not be relaxed after results are visible. Large synthetic scale sets may share the same generator, but the curated 50-100 record set and question set must remain reviewable by a human.

The benchmark must report lexical-only performance separately from any additional local derived retrieval method. Query text and expected answers must not be copied into note bodies or otherwise leaked into the retrieval index as an oracle.

## Coding-agent sequence

### Agent 1 - implementer

Inspect the existing pilot evidence and repository conventions, then build the smallest coherent shadow benchmark that satisfies this gate. The agent owns the technical design and may choose files, data structures, indexing strategy, and test decomposition. It must freeze the benchmark contract before measured execution, run the full visible suite from a clean process/rebuild, preserve failures, document trade-offs, and commit locally without pushing.

The implementation agent must leave a concise handover containing the commit, changed files, frozen corpus/query hashes, exact commands, measured results, known limitations, and confirmation that no live memory surface was touched.

### Agent 2 - independent adversarial reviewer

Begin only after Agent 1 has committed and the worktree is clean. Do not run a parallel implementation. Review authority boundaries and benchmark integrity, reproduce the visible suite from a fresh derived index, and add a separate holdout/attack set that tests paraphrase, partial supersession, source drift, malformed metadata, and cross-project confusion without changing retrieval logic first.

Record the pre-fix result. Corrections, when justified, occur in a separate commit and rerun both visible and holdout sets without deleting the original failure evidence. The reviewer returns **accept**, **reject**, or **inconclusive**, with the exact reason.

Claude Code and Codex are interchangeable for these roles. The roles are sequential; use a different coding agent for the independent review when practical.

## Acceptance evidence

The coding-agent phase is complete only when the repository contains:

- a frozen machine-readable benchmark definition with seeds, exact project IDs, corpus/query hashes, scoring, and predeclared operational budgets;
- a human-reviewable 50-100 record curated corpus or deterministic fixture source;
- deterministic generation for the 1,000- and 10,000-note scale cases without committing the generated bulk corpus;
- per-question expected answers and per-class precision/recall or equivalent correctness evidence, including false positives and false negatives;
- separate lexical and optional local-derived retrieval results;
- supersession-chain and partial-supersession evidence that identifies which claims remain current;
- source/frontmatter drift, deletion, external-edit, relation, rebuild, and project-isolation evidence;
- cold/warm timings and resource measurements at each scale;
- an independent holdout/adversarial review with reproducible commands;
- focused tests and proportional adjacent regression tests;
- proof that the index can be deleted and rebuilt without losing canonical information;
- proof that all disposable generated data was removed, the worktree is clean, and nothing was pushed.

The coding-agent conclusion must be exactly one of:

1. **baseline candidate passes** - evidence is strong enough to begin a separate production-lane proposal;
2. **baseline has named measured gaps** - preserve the exact failing cases for a later single-provider comparison;
3. **benchmark inconclusive** - identify the defect in the benchmark and permit at most one bounded correction cycle.

No provider recommendation is accepted without a named baseline failure from this gate.

## Two-day shadow observation

Coding agents may prepare the observation harness and protocol, but they may not fabricate elapsed usage. Final pilot acceptance waits for two ordinary usage days using sanitized shadow records outside production authority. The observation must record retrieval misses, incorrect current facts, editing friction, source drift, rebuild behaviour, project leakage attempts, and owner maintenance burden.

This observation proceeds after the coding-agent review without another approval ceremony. A documented stop condition still halts the lane.

## Stop conditions

Stop and report rather than widening scope when:

- project identity is inferred or an unscoped operation returns data;
- any cross-project leakage occurs;
- canonical information exists only in a derived index or external service;
- a production store, live MCP contract, owner vault, `.soma/wiki/`, or Hermes path must be changed;
- reproducibility depends on a network API or opaque hosted model;
- benchmark answers leak into indexed note content;
- thresholds are changed after results are known;
- generated bulk data cannot be cleaned safely;
- the lane needs a second canonical authority or a memory provider to continue;
- unrelated repository changes appear;
- the implementation budget exceeds one focused coding-agent day without a clearly bounded remaining problem;
- the independent reviewer cannot reproduce the evidence from canonical files.

A stop is useful evidence. It does not authorize a provider, production integration, or a broad memory redesign.

## Copyable Agent 1 brief

> Implement the active `PILOT-MEMORY-1B` coding-agent gate in `D:\Github\Soma`. Read `PLANS.md`, `docs/PILOT_MEMORY_1B_CODING_AGENT_GATE_2026-07-27.md`, and the existing `PILOT-MEMORY-1` evidence first. Build and execute the smallest shadow-only hardened benchmark that meets the recorded outcomes and boundaries. Preserve coding freedom; do not pre-assume that the baseline must pass. Freeze the benchmark contract before measured execution, keep all indexes derived and rebuildable, use the exact two project IDs, fail closed on unscoped access, and preserve honest failures. Do not touch production memory, live ProjectScope data, MCP schemas, `.soma/wiki/`, Hermes, unrelated files, or push. Commit locally and provide a concise evidence handover for an independent coding-agent review.

## Copyable Agent 2 brief

> Independently review the committed `PILOT-MEMORY-1B` implementation in `D:\Github\Soma` against `docs/PILOT_MEMORY_1B_CODING_AGENT_GATE_2026-07-27.md`. Start from a clean worktree after Agent 1. Reproduce the visible benchmark from canonical files and a fresh derived index, then add a separate holdout/attack set for paraphrase, partial supersession, source/frontmatter drift, malformed metadata, and project-confusion resistance without changing retrieval logic first. Preserve the pre-fix result. Any correction must be a separate local commit followed by reruns of visible and holdout suites. Return accept, reject, or inconclusive with exact evidence. Do not activate production memory, install a memory provider, broaden architecture, alter unrelated work, or push.
