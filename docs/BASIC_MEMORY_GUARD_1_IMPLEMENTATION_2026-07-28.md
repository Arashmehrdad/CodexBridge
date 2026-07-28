# BASIC-MEMORY-GUARD-1 — Implementation Record

**Date:** 2026-07-28
**Status:** guard implemented and unit-accepted. The bounded production-readiness
confirmation **has since been run** and closed both open questions, finding two
defects in this implementation which are now fixed — see
[`BASIC_MEMORY_GUARD_1_CONFIRMATION_2026-07-28.md`](BASIC_MEMORY_GUARD_1_CONFIRMATION_2026-07-28.md).
The "What is NOT yet proven" section below is superseded by that record.
**Decision:** [`BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md`](BASIC_MEMORY_MINIMAL_GUARD_DECISION_2026-07-28.md)
**Evidence:** [`PILOT_BASIC_MEMORY_2_RESULT_2026-07-28.md`](PILOT_BASIC_MEMORY_2_RESULT_2026-07-28.md)

## What was built

`soma/memory_guard/` — a new package, deliberately separate from `soma/memory/`,
which it does not import. It is **not wired into any MCP schema, controller
surface or production path**; no production integration is authorised by the
decision, so the package stands alone until a later lane connects it.

| Module | Role |
|---|---|
| `models.py` | typed refusal reasons, health states, binding and coverage records |
| `binding.py` | exact `project_id` → provider project → root resolution, or refusal |
| `profile.py` | the accepted local-only profile; cloud made unreachable |
| `provider.py` | bounded CLI adapter with an exact five-operation allowlist |
| `health.py` | OS manifest versus provider coverage; honest health disposition |
| `fallback.py` | bounded literal Markdown read/search, path-confined |
| `guard.py` | the facade enforcing order: identity → profile → health → paths |

`tests/test_basic_memory_guard.py` — **39 tests, all passing.** They exercise the
guard through an injected runner, so the guard's refusals are proven **without
depending on provider behaviour**, which is the point.

## How the pilot's findings became controls

Each control below exists because the pilot measured a specific failure.

| Pilot finding | Control |
|---|---|
| Omitted project still returned results with `default_project: null` | `project_id` is mandatory; there is no inference path. Omission raises `IdentityRefused` before any provider call. |
| Unknown project fell back toward **cloud routing** | `BASIC_MEMORY_FORCE_LOCAL=1`, `BASIC_MEMORY_CLOUD_MODE=0`, blanked cloud key vars, `--cloud` refused, `cloud` subcommand refused, and any configured `cloud_api_key`/`default_workspace` refuses the whole profile. Absence of credentials is explicitly **not** accepted as the control. |
| `bm status --wait` livelocked | `--wait` is a refused argument. `bm reindex` is the only synchronisation path. |
| `bm doctor` passed while projects were 6-of-14 indexed | `doctor` is not in the allowlist at all. Health comes from OS-manifest reconciliation. |
| First sync rewrote all 14 notes | `ensure_frontmatter_on_sync: false` is a required setting; `true` refuses the profile with `mutating_profile`. |
| Threshold mis-calibrated for the multilingual model | The measured `0.30` is recorded as `PILOT_SIMILARITY_THRESHOLD` and explicitly documented as corpus-specific, not a default. |
| Provider reported `ok` from a partial index | Coverage is proven, never assumed. An unrecognised provider payload yields `provider_entities = None`, which is **unproven** — never zero, never complete. |

## Fail-closed by construction

Three places where the easy implementation would have been wrong:

1. **Unparsed is not empty.** `parse_results` returns `None`, not `[]`, when the
   provider's response shape isn't understood. A caller cannot read a parse
   failure as "no matches".
2. **Unproven is not complete.** `CoverageReport.proven_complete` requires a
   known entity count, zero pending changes, and coverage ≥ the OS manifest.
   Missing any of those yields `DEGRADED`, and semantic retrieval is blocked.
3. **Path escape is a refusal, not a filter.** A result outside the bound root or
   carrying a sibling project's permalink raises `PathRefused` rather than being
   silently dropped — silent dropping is the Silent Omission Hazard again.

## Rebuild delegation

`rebuild_plan()` returns the argv, environment and working directory for Soma's
**existing** task and run authority to execute. The guard never runs a long
rebuild itself and creates no task, lease, cancellation or recovery plane — the
decision's "no second lifecycle authority" constraint.

## Non-goals honoured

No storage, embeddings, ranking, semantic search or graph traversal. A test
parses every module's imports and fails if the package imports `soma.memory`,
`numpy`, `fastembed`, `onnxruntime`, `torch`, `sentence_transformers`,
`sqlite_vec`, `litellm` or `openai`. The fallback returns results in stable path
order precisely so it cannot be mistaken for a ranking engine.

## What is NOT yet proven — read this before integrating

The decision's implementation-acceptance list has items that **cannot** be closed
without the live provider, which this lane deliberately did not reinstall.

1. **`bm project info --json` output shape is unverified.** `_entity_count()`
   accepts several plausible key names and otherwise reports unproven. Against
   the real provider this may mean **health is always `DEGRADED` and semantic
   retrieval never unlocks**. That is the safe direction, but it is not the
   working state. Confirming the real payload shape is the first task of the
   confirmation lane.
2. **The no-mutation profile is unproven.** The pilot ran with
   `ensure_frontmatter_on_sync: true` and the provider rewrote all 14 notes. That
   the setting actually prevents rewriting — across initial index, repeated sync,
   full deletion and rebuild — is required evidence and has not been produced. If
   the provider still mutates, the decision says stop for owner disposition.
3. **Not re-proven under the guard:** two-sibling ProjectScope binding against a
   live provider, unreachable cloud routing observed empirically, full
   rebuild/interruption accounting, the bilingual regression, and provider-free
   cleanup. All were proven in `PILOT-BASIC-MEMORY-2`, none re-run through this
   code path.

## Regression status

- `tests/test_basic_memory_guard.py` — 39 passed.
- `tests/test_project_scope_foundation.py`, `tests/test_project_scope_quarantine_adjudication.py`, `tests/test_tool_owned_paths.py` — 60 passed.
- Whole suite collects cleanly: 2208 tests, no import breakage.

## Boundaries

No provider installed or run. No production memory, owner memory, `.soma/wiki/`,
Hermes or conversation history touched. No MCP schema change, no controller
wiring, no client configuration. Live ProjectScope untouched — the tests use an
in-memory stand-in exposing only `connect()`. Not pushed.
