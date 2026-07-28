# MEMORY-INTEGRATION-FOUNDATION-1 — Implementation Result

**Date:** 2026-07-28
**Status:** all nine required steps executed; one acceptance item closed by
refusal rather than by capability.
**Decision:** [`SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md`](SOMA_SHARED_MEMORY_ARCHITECTURE_DECISION_2026-07-28.md)
**Coverage measurement:** [`MEMORY_INTEGRATION_FOUNDATION_1_COVERAGE_MEASUREMENT_2026-07-28.md`](MEMORY_INTEGRATION_FOUNDATION_1_COVERAGE_MEASUREMENT_2026-07-28.md)
**Branch:** `lane/memory-integration-foundation-1` — not pushed.

## Headline

Canonical memory is live behind one authority, one write path and one public
partition. **Semantic retrieval is disabled**, because step 2 measured that the
accepted provider interface cannot prove which files an index contains. Soma
ships lexical canonical retrieval, which is complete by construction, and says
so in every response.

## Required sequence

| Step | Outcome |
|---|---|
| 1. repair verified defects | all seven repaired, each with a regression test |
| 2. measure exact coverage capability | **negative branch fires** — membership unprovable |
| 3. disposable canonical vault root | `CanonicalMemoryConfig`, default unchanged |
| 4. `CanonicalMemoryService` | wraps `KnowledgeService`; adds scope, CAS, lifecycle, packets |
| 5. named memory operations | 5 query + 7 action on the existing gateway pair |
| 6. legacy writer freeze | all writers, not only the public operation |
| 7. rebuild through task authority | delegated; currently refuses with its reason |
| 8. exact context packets | persisted before bounding; exact retrieval |
| 9. synthetic end-to-end proof | 11 gateway tests over two sibling projects |

## The decisive measurement

`bm project info --json` reports `statistics.total_entities` and an `activity`
block whose rows carry `file_path`. On a four-file corpus that reads as complete
membership. It is not: `activity` is a ten-row recency feed.

| Corpus | `total_entities` | files on disk | enumerable paths |
|---|---|---|---|
| 4 files | 4 | 4 | 4 — *false positive* |
| 34 files | 34 | 34 | **10** |

Cardinality agreed perfectly while 24 of 34 files were invisible. `status --json`
reports pending deltas only; `tool search-notes` is threshold-gated. No accepted
operation enumerates the set.

Consequence, per the decision's own negative branch: `PROVIDER_MEMBERSHIP_AVAILABLE
= False`, health reports `degraded` with `coverage_membership_unavailable` even
when every other signal is perfect, and retrieval falls back to canonical
Markdown. The full reconciliation mechanism is implemented and tested; a provider
release that enumerates its set flips one flag.

## Defects repaired

| # | Defect | Repair |
|---|---|---|
| 1 | coverage proved cardinality only | membership required; `missing_paths`/`extra_paths` derived |
| 2 | provider stdout parsed without checking exit code | `parse_json` requires `call.ok` |
| 3 | frozen stack documented, not enforced | `runtime.py` verifies version, model, threshold; new `INCOMPATIBLE` state |
| 4 | absent scope store resolved as ACTIVE | refuses; the branch no test covered |
| 5 | provider inherited all of `os.environ` | named `INHERITED_ENV` allowlist |
| 6 | supersession not crash-safe | effective state derived from the successor's link |
| 7 | integrity hash covered content only | covers scope, lifecycle, temporal validity, provenance |
| 8 | vault under ignored `runs/` | `CanonicalMemoryConfig` makes the root a choice |
| 9 | owner notes counted as corruption | `UnadoptedNote` separates unadopted from malformed |
| 10 | multiple legacy writers | all frozen; `remember_decision` redirected |

Defect 5 is worth naming precisely: both extremes were real. Passing only the
`BASIC_MEMORY_*` keys left the child with no `PATH`, and passing all of
`os.environ` hands the provider every credential in Soma's process. The repair is
a named allowlist, neither.

## Legacy retirement

`remember_project_fact`, `remember_decision` and the validation-recipe writers
refuse. The local agent's in-loop memory actions refuse. `remember_decision`
keeps its name, request and response shape and now writes canonical Markdown —
which means it requires an exact active ProjectScope binding, and refuses
without one. Reads, operational run/job/artifact recollection and migration
remain open.

## What a controller sees

```json
{"ok": true, "operation": "memory_search",
 "retrieval_mode": "catalog_lexical",
 "canonical_health": "healthy", "provider_health": "degraded",
 "records": [{"knowledge_id": "kn_...", "status": "current",
              "vault_path": "decisions/listener-port.md",
              "content_sha256": "...", "revision": 1}],
 "warnings": [], "omitted_count": 0}
```

A lexical answer is never presented as a semantic one, and `omitted_count`
plus `memory_packet_get` keep truncation distinguishable from absence.

## Regression

Full suite **2227 passed, 35 skipped**. New: 11 gateway end-to-end, 21 canonical
memory service, 8 guard defect regressions, 6 canonical lifecycle regressions.

One note on honesty: during one full-suite run
`test_projection_overhead_and_full_retrieval_performance` failed on a timing
threshold (2.05 ms against a 0.5 ms limit). It passes standalone and at file
scope both with and without these changes, and the test documents machine-load
outliers as a known effect. The final full run passed.

## Still open

- **Semantic retrieval is disabled.** Reopening requires a provider release that
  enumerates its indexed set. Reading the provider's SQLite directly is not an
  accepted path.
- **The production vault root is not yet chosen.** The default still points
  under `runs/`; the tests prove the external-vault path works. This is the
  owner decision the architecture flagged.
- **Personal memory is modelled and refused**, per the lane's exclusions.
- **Bulk legacy migration** is deliberately not done; the old store is readable.
- `memory_rebuild_index` is wired but unreachable while membership is unprovable.

## Boundaries

Synthetic corpora only. No owner memory imported. No personal scope. No push.
Provider installed in a disposable root and removed after measurement — absent
from PATH, from Soma's `.venv`, and no `~/.basic-memory`. Two evidence JSON
files remain under the gitignored pilot root. Provider source unmodified.
