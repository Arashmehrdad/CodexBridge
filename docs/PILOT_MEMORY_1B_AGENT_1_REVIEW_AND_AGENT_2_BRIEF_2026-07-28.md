# PILOT-MEMORY-1B - Agent 1 Review and Agent 2 Adversarial Brief

**Date:** 2026-07-28
**Status:** Agent 1 evidence reviewed; current implementation rejected pending bounded adversarial correction.
**Agent 1 commit:** `7bf955e859d74e76e340b3248bef27284e3b8498`
**Review evidence run:** `20260728T044759Z_executable_profile_ef9ef929`
**Authority:** shadow benchmark only; no production memory activation or provider comparison.

## Review verdict

Agent 1 successfully produced a substantial and useful benchmark. The named semantic gap is provisionally credible: lexical semantic-paraphrase F1 was `0.333` against `0.60`, and the corpus-only NPMI expansion did not improve it. Scale, supersession, source drift, deletion, rebuild, and the visible exact-recall classes also produced useful evidence.

The current commit is nevertheless **not acceptable under the gate** because a documented stop condition fired during controller review:

> an unscoped operation returned data, and project-scoped structural retrieval can disclose a sibling-project malformed record.

This is a benchmark authority defect, not evidence that production ProjectScope leaked. The pilot is shadow-only and the live store remains untouched.

## Confirmed boundary failures

A disposable review vault used the committed implementation without changing the repository.

1. `MemoryIndex.reachable("soma-relation-gate-c", "depends_on", 1)` returned `soma-relation-gate-b` with **no `project_id` argument**.
2. A synthetic Soma note with an explicit `depends_on` relation to `lab-runtime-port` returned that sibling-project target through the same unscoped relation API.
3. `_structural(index, "malformed_frontmatter", SOMA_PROJECT_ID)` returned both `soma-drift-malformed` and a synthetic sibling record `lab-review-malformed`.
4. `related`, `reachable`, and `referrers` therefore do not share the fail-closed project contract already enforced by lexical and claim retrieval.

The visible corpus happened not to contain an adversarial cross-project relation or a sibling malformed record. Consequently, the recorded zero-cross-project audit proves only the visible lexical/derived cases; it does not prove structural isolation across all benchmark retrieval surfaces.

## Benchmark chronology issue

The original fixed-top-5 scoring rule was genuinely inconsistent for single-answer questions, and replacing it with R-precision is technically reasonable. The evidence correctly preserves the pre-correction run and leaves thresholds unchanged.

However, the final freeze file and runner currently state `frozen_before_first_measured_run: true` for the **corrected** contract. Chronologically:

- the initial contract was frozen before the initial measured run;
- the corrected R-precision contract was frozen before the corrected measured run;
- the corrected contract was not the contract frozen before the first measured run.

Agent 2 must correct this provenance wording and preserve both contract identities. This is an evidence-integrity correction, not permission to tune thresholds or questions after seeing results.

## What remains valid from Agent 1

- the semantic-paraphrase failures remain named candidate baseline gaps;
- the NPMI non-improvement remains useful negative evidence;
- the fixed-top-5 pre-correction result remains preserved evidence;
- the visible lexical search path filters by exact project before ranking;
- no production memory, ProjectScope row, MCP schema, Hermes path, provider, or network service was touched;
- generated scale vaults were removed and the repository is clean;
- the two-day observation has correctly not been fabricated.

These findings are provisional until Agent 2 reproduces them after the authority correction.

## Agent 2 required sequence

### Phase A - reproduce and reject the current commit before editing

Start from clean commit `7bf955e859d74e76e340b3248bef27284e3b8498` and do not change retrieval logic first.

1. Reproduce the visible benchmark from canonical files and a fresh index.
2. Reproduce the controller review run's three boundary failures.
3. Add holdout attacks for:
   - an unscoped one-hop and multi-hop relation traversal;
   - unscoped referrer lookup;
   - a same-project anchor pointing to a sibling-project target;
   - a sibling malformed record queried from the Soma project;
   - a wrong-project anchor and an unknown-project anchor;
   - paraphrases that vary grammar and synonyms without copying note wording;
   - partial supersession and source/frontmatter drift not present in the visible set.
4. Record the current commit's verdict as **reject** because the stop condition is confirmed.
5. Preserve the complete pre-fix holdout result in a committed evidence artifact.

### Phase B - bounded correction after rejection evidence is committed

The correction may change only benchmark authority, classification, and provenance mechanics required by the confirmed defects.

- Every relation and referrer operation must require an exact `project_id`.
- The anchor must belong to that project before traversal.
- Ordinary traversal must not return a target in another project. Cross-project relations must be explicitly represented and handled by a separate typed operation or rejected; they may not silently traverse.
- Malformed metadata whose project identity cannot be trusted must not appear in a project-scoped result. It must be surfaced through a separate unscoped maintenance/quarantine report or explicit trusted fixture metadata, without inferring identity from note name or folder.
- Split structural project-isolation assertions from within-project retrieval-quality scoring. Preserve the old combined class and result as historical evidence; do not rewrite them.
- Replace the misleading freeze chronology boolean with explicit initial-versus-corrected contract provenance, including both hashes and measurement ordering.
- Keep R-precision unless the reviewer demonstrates a separate mathematical defect. Do not change thresholds to make a result pass.
- Do not improve semantic retrieval in this correction. The paraphrase gap must be rerun unchanged against the corrected authority surface.

After the correction, rerun the visible set, the untouched holdout set, focused tests, proportional adjacent tests, and the full suite. Preserve every pre-fix artifact.

## Acceptance after Agent 2

Agent 2 returns one of:

- **accept with named semantic gap** - all authority/chronology defects are corrected, visible and holdout project isolation are fail-closed, and semantic paraphrase still fails honestly;
- **reject** - any unscoped or cross-project disclosure remains, correction alters thresholds/questions to improve the score, or evidence cannot be reproduced;
- **inconclusive** - the holdout or chronology cannot distinguish a benchmark defect from a baseline gap without broadening scope.

The two-day shadow observation begins only after an **accept** result. No provider comparison or production-memory proposal begins in this review.

## Copyable Agent 2 prompt

> Independently review `PILOT-MEMORY-1B` in `D:\Github\Soma` starting from clean commit `7bf955e859d74e76e340b3248bef27284e3b8498`. Read `docs/PILOT_MEMORY_1B_CODING_AGENT_GATE_2026-07-27.md`, `docs/PILOT_MEMORY_1B_AGENT_1_REVIEW_AND_AGENT_2_BRIEF_2026-07-28.md`, the Agent 1 benchmark evidence, and `PLANS.md` first. Before changing code, reproduce the visible suite and commit a separate pre-fix adversarial result proving or disproving: unscoped relation/referrer access, cross-project relation traversal, sibling malformed-metadata disclosure, paraphrase robustness, partial supersession, source drift, and the R-precision chronology. The current controller review already demonstrated that `reachable` returns data without project scope, a Soma relation can return `lab-runtime-port`, and a Soma malformed-metadata query can return a sibling malformed note; treat that as a documented stop condition, not as a production ProjectScope defect. After preserving the rejection evidence, make only the bounded authority/classification/provenance correction defined in the review brief, in a separate local commit. Require exact project scope on every relation/referrer path, prevent silent cross-project traversal, prevent malformed records with untrusted identity from entering project-scoped results, split structural isolation from within-project ranking quality while preserving the old evidence, and record initial versus corrected contract chronology honestly. Do not alter thresholds, tune questions after results, improve semantic retrieval, activate production memory, install a provider, touch live stores/MCP/Hermes/.soma/wiki, modify unrelated files, or push. Rerun visible and untouched holdout suites plus focused, adjacent, and full regression tests. Return accept with named semantic gap, reject, or inconclusive with exact commits and evidence.
