# BASIC-MEMORY-GUARD-1 — Live-Provider Production-Readiness Confirmation

**Date:** 2026-07-28
**Status:** executed; **both open questions closed**; two implementation defects
found and fixed.
**Decision:** [`BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md`](BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md)
**Implementation:** [`BASIC_MEMORY_GUARD_1_IMPLEMENTATION_2026-07-28.md`](BASIC_MEMORY_GUARD_1_IMPLEMENTATION_2026-07-28.md)

## Result

**The canonical-integrity gate passes, and the guard works against the live
provider — but only after two fixes that unit tests could not have found.**

The decision's stop clause ("if the tested release cannot operate without
rewriting canonical files, integration stops") does **not** fire. A supported
setting does prevent the rewriting; it simply is not the one the decision named.

## Finding 1 — `ensure_frontmatter_on_sync` is the wrong control

The decision required disabling `ensure_frontmatter_on_sync` "or the exact
supported equivalent". Measured from a pristine corpus with zero derived state:

| Profile | Canonical files mutated |
|---|---|
| `ensure_frontmatter_on_sync: false` alone | **6 of 6** |
| `+ disable_permalinks: true` | **0 of 6** |

`disable_permalinks` is the control that actually works — the injected key was
`permalink:`, so it is the right lever. Lexical **and** semantic retrieval both
continue to work with it set, so nothing is traded away.

Full four-phase confirmation with the corrected profile:

| Phase | Drift |
|---|---|
| project registration + config | **none** |
| initial full index | **none** |
| repeated synchronisation (3×) | **none** |
| full derived-state deletion + rebuild | **none** |

Final state after every phase plus the end-to-end run: **6/6 byte-identical to
the pre-provider freeze.** Hashes were captured before the provider was ever
contacted.

`soma/memory_guard/profile.py` now requires **both** settings — `disable_permalinks`
as the working control, `ensure_frontmatter_on_sync` as defence in depth.

## Finding 2 — two defects in my own implementation

Both would have broken the guard in production. Both were invisible to the unit
suite because it drives an injected runner.

**`bm project info` takes a positional name, not `--project`.** The adapter
appended `--project` to every operation, so the coverage call always failed with
`No such option: --project`. Health would therefore have sat permanently at
`DEGRADED` and semantic retrieval would never have unlocked — the safe direction,
but useless. Fixed by encoding the positional form for that one operation.

**`ProviderProfile.env()` returned only the `BASIC_MEMORY_*` keys as the process's
entire environment** — no `PATH`, no `SystemRoot`. Every real subprocess was
crippled; the first live run scored 12/16 for this reason alone. `env()` now
inherits the ambient environment, applies the guard's keys last so they always
win, and strips forbidden cloud variables. Two regression tests lock both fixes in.

## Confirmed provider payload shapes

`bm project info <name> --json` returns `statistics.total_entities` — which the
guard's existing recursive reader already handles once invoked correctly:

```json
{"project_name": "guard-alpha",
 "default_project": null,
 "statistics": {"total_entities": 3, "total_observations": 0, ...}}
```

`bm status --json --project <name>` returns `total` for pending changes.

Also recorded: `bm tool list-projects` fails with `No default project configured`
under the required `default_project: null` profile, so it is not a usable
coverage source. The guard does not depend on it.

## Live guard verification — 16/16

Driven through the real `BasicMemoryGuard` against the installed provider, using
a real `ProjectScopeStore` schema on a disposable database (never the live store).

| Check | Result |
|---|---|
| binds both sibling projects exactly | pass |
| omitted identity refused before provider call | pass |
| unknown project refused | pass |
| mismatched claimed identity refused | pass |
| live coverage reconciliation | `entities 3/3, pending 0, proven_complete: true` → **healthy** |
| semantic retrieval via provider | `guard-alpha` → `service-endpoint.md`, no fallback |
| sibling isolation on the same query | `guard-beta` → `lab-service-endpoint.md`, **zero leakage** |
| `bm doctor` refused by allowlist | pass |
| `status --wait` refused | pass |
| rebuild plan described, then executed by a Soma-style runner | exit 0, `3 entities embedded, 0 skipped, 0 errors` |
| destroyed index blocks semantic retrieval | `degraded`, `semantic_permitted: false` |
| canonical Markdown fallback still answers | returned `service-endpoint.md` |
| read outside bound root refused | pass |

The fail-closed sequence is the important one: deleting `memory.db` moved health
to `degraded`, semantic use was blocked, and the guard answered from canonical
Markdown instead — no silence, no guess, no stale index.

## Decision acceptance items now closed

- exact ProjectScope binding for two deliberately similar sibling projects — **closed**
- omission, unknown and wrong-project requests fail before provider invocation — **closed**
- frozen environment installs reproducibly on Windows without global changes — **closed** (wheel hash verified, `litellm 1.91.4` pin, PATH unchanged at 35 entries)
- provider indexing and full rebuild leave canonical Markdown byte-identical — **closed** (6/6, four phases)
- partial or uncertain coverage blocks semantic retrieval — **closed**
- returned paths remain within the bound root, no sibling result — **closed**
- bounded direct Markdown fallback usable while the provider is unavailable — **closed**
- provider removal leaves canonical Markdown intact — **closed**
- focused regression gates pass — **closed** (42 guard + 60 ProjectScope = 102; 2211 collect clean)

## Still open

**No cloud-routing path is reachable — enforced, not empirically proven.** The
guard forces `FORCE_LOCAL`, blanks cloud key variables, strips forbidden env,
refuses `--cloud` and the `cloud` subcommand, and refuses any profile carrying a
credential. What was *not* done is configure a real credential and confirm the
provider still cannot reach cloud — that would mean introducing a live cloud
credential to this host, which the decision forbids. The control is structural;
the negative proof is not available without violating a boundary.

**Bilingual regression was not re-run through the guard.** The corpus used here
is 6 notes including Persian, and retrieval worked, but the full four-direction
matrix belongs to `PILOT-BASIC-MEMORY-2` and was not repeated.

## Boundaries

Disposable root `runs/pilots/basic-memory-guard-1/` only. Soma's `.venv`
untouched; provider absent from PATH and from Soma's environment afterwards; user
PATH unchanged at 35 entries; `claude_desktop_config.json` untouched since
2026-07-25; no `~/.basic-memory`; no processes left. Synthetic corpus only. Live
ProjectScope, Soma stores, `.soma/wiki/` and Hermes untouched — the ProjectScope
databases used were disposable copies of the schema. Provider source unmodified.
Not pushed.

## Cleanup

Provider venv, wheel cache, config, embeddings cache, disposable projects and the
disposable ProjectScope databases all removed after evidence hashes were
recorded. Only three evidence JSON files remain under the gitignored pilot root.
