# MEMORY-INTEGRATION-FOUNDATION-1 Step 2 — Exact Coverage Capability Measurement

**Date:** 2026-07-28
**Status:** executed; the gate's negative branch fires.
**Decision:** [`SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md`](SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md) §Exact semantic-coverage gate
**Machine-readable evidence:** `runs/pilots/memory-foundation-1/coverage-capability.json`, `runs/pilots/memory-foundation-1/membership-cap.json` (gitignored run state)

## Question

Can the accepted provider interface expose enough information to reconcile
exact canonical relative paths against an indexed generation — or only a count?

The decision makes this measurement decisive: exact reconciliation permits
semantic mode to report healthy; its absence means canonical lexical retrieval
ships and semantic mode stays disabled.

## Result

**Exact membership is not achievable through the accepted interface for Basic
Memory `0.22.1`. The negative branch fires. Semantic mode is disabled.**

## Measurement

Live provider, frozen stack (`basic-memory 0.22.1`, `fastembed 0.8.0`,
`litellm 1.91.4`), disposable vault under `runs/pilots/memory-foundation-1/`,
accepted local-only profile, `bm reindex --full` to a clean index.

Every allowlisted operation was probed for path enumeration:

| Operation | Exit | Enumerates the indexed set? |
|---|---|---|
| `project info <name> --json` | 0 | **No** — see below |
| `status --json --project <name>` | 0 | No — reports pending deltas only; all lists empty when synchronised |
| `status --project <name>` | 0 | No — renders "No changes" |
| `tool search-notes "the" --page-size 100` | 0 | No — threshold-gated matches, 2 of 4 files |
| `tool search-notes "CANARY" --page-size 100` | 0 | No — 0 results; the term is sub-threshold |
| `tool search-notes "*"` | 2 | Rejected argument |

### The near-miss that matters

On a **4-file** corpus, `project info --json` appeared to enumerate everything:
its `activity.recently_created[]` rows each carry `file_path`, and all four
files were present. Read naively, that is complete membership.

It is not. `activity` is a **recency feed with a fixed ten-row cap**. Re-measured
against a **34-file** corpus:

| Signal | Value |
|---|---|
| `statistics.total_entities` | 34 |
| canonical files on disk | 34 |
| distinct `file_path` values in the entire payload | **10** |
| complete membership | **false** |
| files unaccounted for | **24** |

Cardinality agreed perfectly while 24 of 34 files were unenumerable. A small
corpus reads as "complete" purely because it fits under the cap — precisely the
false positive that would have shipped a health claim the evidence cannot
support.

## Consequences implemented

- `PROVIDER_MEMBERSHIP_AVAILABLE = False` in `soma/memory_guard/health.py`,
  carrying the measurement in its docstring.
- `BasicMemoryGuard(membership_supported=...)` defaults to that constant, so the
  production guard makes no membership call. Health reports `degraded` with
  reason `coverage_membership_unavailable` even when counts agree and pending
  changes are zero.
- `ACTIVITY_FEED_KEYS` names the feed keys explicitly and `indexed_paths()`
  never reads them, so a later change cannot quietly promote a feed to a set.
- Retrieval falls back to canonical lexical/literal Markdown and says so through
  `used_fallback` and the published health state.
- The reconciliation mechanism (`missing_paths`, `extra_paths`,
  `cardinality_agrees`, `proven_complete`) is fully implemented and tested. A
  provider release that enumerates its indexed set flips one flag; nothing else
  changes.

## What this costs, stated plainly

Semantic and bilingual retrieval measured in `PILOT-BASIC-MEMORY-2` is real and
still works. What cannot be established is that any given index is *complete*,
and the pilot's own decisive finding was a provider serving confident answers
from a partial index. Soma therefore ships lexical canonical retrieval, which is
complete by construction, rather than semantic retrieval whose completeness
cannot be proven.

## Reopening conditions

Semantic mode becomes available when any of these is measured true:

- a provider release exposes a complete entity/path listing through an accepted
  read-only operation;
- an accepted operation gains a documented, uncapped enumeration parameter;
- a different provider passes the same black-box contract *and* enumerates.

Reading the provider's SQLite index directly is **not** an accepted path: it
would make Soma depend on provider internals, which the decision forbids.

## Boundaries

Disposable root only. Synthetic 34-note corpus. No owner memory. No canonical
vault touched. Provider installed inside the disposable root, absent from PATH
and from Soma's `.venv`. Provider source unmodified. Not pushed.
