# PILOT-MEMORY-1B — Hardened Shadow Benchmark, Agent 1 Implementation

**Date:** 2026-07-28
**Status:** implemented, frozen, executed. Shadow-only; no production authority.
**Gate:** [`PILOT_MEMORY_1B_CODING_AGENT_GATE_2026-07-27.md`](PILOT_MEMORY_1B_CODING_AGENT_GATE_2026-07-27.md)
**Conclusion:** **baseline has named measured gaps**

Machine-readable evidence:
[`pilot-memory-1b-frozen-benchmark-2026-07-28.json`](pilot-memory-1b-frozen-benchmark-2026-07-28.json),
[`pilot-memory-1b-results-2026-07-28.json`](pilot-memory-1b-results-2026-07-28.json),
[`pilot-memory-1b-results-precorrection-2026-07-28.json`](pilot-memory-1b-results-precorrection-2026-07-28.json).

## Conclusion

The Markdown + Git baseline is **strong on structure and weak on meaning**.

It handled multi-hop supersession, partial claim-level supersession,
contradiction and current-fact precision, relations, source and frontmatter
drift, deletion, dangling links, external-edit attribution, and deterministic
rebuild — every one at F1 `1.000`. It scaled to 10,000 notes inside every
predeclared budget.

It failed on paraphrase. Four of six meaning-based questions did not surface
the correct note **anywhere in the ranked results**. That is the named measured
gap `PILOT-MEMORY-1` predicted but could not produce.

## What was built

`soma/pilot_memory_1b/`, deliberately separate from `soma/memory/`, which is the
real durable store. A test parses every module's imports and fails if this lane
imports `soma.memory`, `soma.project_scope`, `soma.tasks`, or any network
module.

| Module | Role |
|---|---|
| `contract.py` | frozen seed, exact project IDs, thresholds, budgets, scoring |
| `corpus.py` | 62-record curated fixture across two similar projects |
| `vault.py` | canonical Markdown render/parse; strict frontmatter reader |
| `index.py` | derived index, supersession resolution, fail-closed retrieval |
| `derived.py` | optional corpus-only NPMI expansion, reported separately |
| `questions.py` | 34 golden questions with expected answers |
| `scoring.py` | set precision/recall/F1 |
| `generator.py` | deterministic 1k/10k scale corpora |
| `runner.py` | freeze, measure, emit evidence |

## Frozen contract

Frozen before the first measured run and verified at the start of every run;
the runner refuses to record a result if the freeze has drifted.

| Item | Value |
|---|---|
| contract hash | `abe1b318ae971b83ae2c950dfca57729c40ed206605405495384a8b8c97a1812` |
| corpus spec hash | `78148f621578a4b4e27372ef3c4f6cba10cc205cef0145a960b20108fa02ddc1` |
| questions hash | `cff6f1d47bcb23774cf13e193f883ba27b8d402797692b038f439b9e8b33c109` |
| canonical corpus bytes | `b257dbe078b2a21bb7f567171c2ee7c46762fe5e1c469ed00a3c9cd7d6e8652b` |
| rebuild fingerprint | `b47b658cb0a871c7a23a3e990f8fe8af390424555b7358355095fd4af8202ff0` |
| seed | `20260727` |
| curated notes | 62 (36 Soma, 26 sibling) |
| questions | 34 |

Exact project identities, never inferred:
`proj_a144f759-1619-4276-9292-28704b6611f4` and
`proj_0cf013d0-191b-57f4-a84b-7a43819a1578`.

## Measured results, lexical baseline

| Class | F1 | Threshold | |
|---|---|---|---|
| exact_recall | 1.000 | 0.95 | pass |
| multi_hop_full_supersession | 1.000 | 0.90 | pass |
| partial_claim_supersession | 1.000 | 0.90 | pass |
| contradiction_and_current_fact_precision | 1.000 | 0.90 | pass |
| one_and_multi_hop_relations | 1.000 | 0.85 | pass |
| source_and_frontmatter_drift | 1.000 | 0.95 | pass |
| deletion_and_dangling_links | 1.000 | 0.95 | pass |
| external_edit_attribution | 1.000 | 1.00 | pass |
| deterministic_rebuild | 1.000 | 1.00 | pass |
| **project_isolation_and_unscoped_rejection** | **0.750** | 1.00 | **fail** |
| **semantic_paraphrase** | **0.333** | 0.60 | **fail** |

### The two failures, precisely

**`semantic_paraphrase` — a real baseline gap.** Two of six passed (`sp-02`,
`sp-06`). Four missed entirely:

| Question | Expected | Lexical returned |
|---|---|---|
| `sp-01` how many jobs may execute at the same moment before the machine is overloaded | `soma-paraphrase-throttle` | `soma-worker-profile-v1` |
| `sp-03` why is hiding skipped items from a reviewer dangerous | `soma-paraphrase-quiet-failure` | `soma-paraphrase-throttle` |
| `sp-04` which socket number does the service accept connections on | `soma-runtime-port` | `soma-dangling-reference` |
| `sp-05` can a query stall the process that is saving data | `soma-journal-mode` | `soma-decision-fail-closed` |

These are the exact cases to hand to a later single-provider comparison.

**`project_isolation_and_unscoped_rejection` — misnamed, not an isolation
failure.** The isolation property itself held perfectly:

- `pi-01` (Soma) and `pi-02` (sibling) each returned their own project's note
  for identical query text;
- `pi-04` unscoped query raised rather than returning data;
- an audit across every question in both retrieval methods found **zero
  cross-project results**. Scoping is structural: the search filters to the
  project's note set before ranking.

The class fails only because `pi-03` returned `lab-source-runbook` instead of
`lab-worker-profile-v1` — the **wrong note inside the correct project**. That is
the same vocabulary-mismatch weakness as the paraphrase gap, not leakage. The
class name conflates two properties and should be split by the reviewer.

## Local derived method, reported separately

Corpus-only NPMI co-occurrence query expansion. No network, no hosted model,
nothing learned from the question set.

| Class | Lexical | Derived |
|---|---|---|
| exact_recall | 1.000 | 1.000 |
| project_isolation | 0.750 | **1.000** |
| semantic_paraphrase | 0.333 | 0.333 |

It repaired `pi-03` and did **not** move paraphrase at all. A purely local
association model built from 62 notes has no signal to connect "socket" to
"listener" when they never co-occur. This is useful negative evidence: the
paraphrase gap is not closable by cheap local tricks.

## Scale and resources

| Notes | Cold rebuild | Budget | Warm p95 | Budget | Peak alloc | Budget | Needle found | Removed |
|---|---|---|---|---|---|---|---|---|
| 62 | 0.016 s | 2.0 s | — | — | 0.30 MB | 25 MB | — | yes |
| 1,000 | 9.53 s | 15 s | 0.49 ms | 250 ms | 3.48 MB | 250 MB | yes | yes |
| 10,000 | 89.59 s | 150 s | 11.90 ms | 2.5 s | 34.61 MB | 1500 MB | yes | yes |

Every budget met. Cold rebuild is roughly linear and is the cost that will bite
first: 90 seconds at 10k notes is tolerable for a disposable index but not for
an interactive one. Warm queries stay comfortably sub-second.

## Structural evidence

- **Multi-hop supersession** `A ← B ← C`: only `soma-store-size-v3` current;
  v1 and v2 retained and marked superseded, never deleted.
- **Partial supersession**: `soma-worker-profile-v2` replaced only
  `lease_seconds`; `retry_limit` correctly remains current on v1.
- **External edit**: an out-of-band append was attributed by Git as
  `M soma-external-edit.md` and visible after reindex.
- **Deletion**: the removed note vanished and produced a new dangling
  reference `soma-deletion-referrer → soma-deletion-target`.
- **Rebuild**: identical fingerprint across repeat builds and after discarding
  the index; canonical bytes unchanged by rebuilding.
- **Drift**: moved and deleted sources reported `unresolved`, absent source
  reported `missing`, broken frontmatter surfaced without dropping the note.

## Benchmark integrity: one correction cycle, disclosed

The first frozen revision set a fixed retrieval cutoff of `k = 5` while most
questions expect exactly one note. That capped F1 at `0.333` for any
single-answer question — **below its own 0.95 threshold no matter how good
retrieval was**. The contract was internally inconsistent.

The pre-correction run is preserved in
[`pilot-memory-1b-results-precorrection-2026-07-28.json`](pilot-memory-1b-results-precorrection-2026-07-28.json):
`exact_recall` 0.367, `project_isolation` 0.500, `semantic_paraphrase` 0.111.
Inspection showed the correct note was at **rank 1 in all five** `exact_recall`
questions.

One bounded correction was applied: scoring changed to R-precision, `k =
max(1, len(expected))`. **No threshold was altered.** After the correction
`exact_recall` reaches 1.000 and the paraphrase gap remains, which is the
outcome that distinguishes a scoring artifact from a real failure.

A separate, earlier defect was caught by the leakage guard before any
measurement existed: four project-isolation questions reused note titles
verbatim. The questions were reworded; the rule was not relaxed.

## Authority confirmation

- no live memory surface touched — `soma/memory/`, `.soma/wiki/`, and the prior
  `PILOT-MEMORY-1` evidence are unmodified;
- `runs/soma.sqlite3` was never opened by this lane; live ProjectScope remains
  settings `[1, 1]`, 1 project, 1 binding, integrity `ok`;
- no MCP schema, Hermes path, or production vault involved;
- no memory provider installed or evaluated;
- every vault lived in a disposable temp directory and was removed
  (`workdir_removed: true`, `vault_removed: true` at both scales);
- generated 1k/10k corpora were never written inside a tracked path and are not
  committed;
- no network dependency; no push.

## Known limitations

1. **Paraphrase questions are few.** Six questions is enough to expose the gap,
   not to size it. A reviewer should widen this class before any provider
   comparison quotes a number.
2. **`project_isolation_and_unscoped_rejection` conflates** structural scoping
   with retrieval quality. It should be split; as scored, one retrieval miss
   masks a perfect isolation record.
3. **Peak allocation, not RSS.** `tracemalloc` measures Python allocation, which
   is reproducible across hosts; it understates true process footprint.
4. **Cold rebuild is single-threaded and unoptimised.** 90 s at 10k notes is a
   property of a naive derive-on-read index, not a floor.
5. **Synthetic corpus.** 62 notes written in one sitting still under-represents
   the frontmatter chaos of a vault maintained for months.
6. **The scale corpus is shallower than the curated one**, so scale timings do
   not exercise partial supersession or relation depth as heavily.
7. **Two-day shadow observation is not started.** The harness exists; elapsed
   usage cannot be fabricated.

## Reproduction

```
python -m soma.pilot_memory_1b.runner freeze
python -m soma.pilot_memory_1b.runner run --scale --json docs/pilot-memory-1b-results-2026-07-28.json
python -m pytest tests/test_pilot_memory_1b.py -q
```

## Handover to Agent 2

Start from a clean worktree. Reproduce the visible suite from canonical files
and a fresh derived index, then add a holdout/attack set for paraphrase,
partial supersession, source drift, malformed metadata, and cross-project
confusion **before** changing any retrieval logic. Record the pre-fix result.

The specific claims worth attacking: that scoping is structural rather than
incidental; that the paraphrase failures are genuine rather than artifacts of
question wording; and that the R-precision correction did not quietly make a
failing class passable.
