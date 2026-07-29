# LEGACY-RETIREMENT-AUDIT-1 — Result

**Date:** 2026-07-29
**Status:** closed **audit-complete**.
**Authorisation:** [`LEGACY_RETIREMENT_AUDIT_1_GATE_2026-07-29.md`](LEGACY_RETIREMENT_AUDIT_1_GATE_2026-07-29.md)
**Manifest (authoritative for item classification):** [`legacy-retirement-audit-1-manifest-2026-07-29.json`](legacy-retirement-audit-1-manifest-2026-07-29.json)
**Branch:** `lane/memory-integration-foundation-1`

## Executive summary

**Nothing tracked in the repository is removable before V3.**

Of fourteen classified items, exactly one is `remove_candidate`, and it is an
untracked `__pycache__` directory that git does not follow. The honest answer to
"how much code can we delete before V3" is: none of it.

That is not a disappointing result. The audit's value is in the five items that
looked dead by import count and turned out to be load-bearing.

## What the import graph got wrong

**`soma/pilot_memory_1b/` has no production importer and must still stay.** It
is imported only by its own test, ships with no entry point and is never loaded
at startup — every static signal says remove it. But
`docs/pilot-memory-1b-frozen-benchmark-2026-07-28.json` publishes
`contract_hash`, `corpus_spec_hash` and `questions_hash`, and those hashes are
computed *from these modules*. I recomputed all three against current source:

| Hash | Recorded | Now |
|---|---|---|
| `contract_hash` | `abe1b318ae97…` | **match** |
| `corpus_spec_hash` | `78148f621578…` | **match** |
| `questions_hash` | `cff6f1d47bcb…` | **match** |

The package is the live attestation for a frozen benchmark that fed
`MEMORY_PROVIDER_DECISION_2026-07-28`. Delete it and three published hashes
become permanently unverifiable — the evidence would still exist as text and
would no longer be checkable against anything. Classified
`keep_compatibility_read`.

**`RepoWikiService.wiki_exclusions` is not the dead path the lifecycle inventory
recorded.** The *constructor parameter* is dead: all four production call sites
use the two-argument form and only a test passes it. But the field is serialised
into the persisted wiki manifest at [`repo_wiki.py:944`](../soma/repo_wiki.py:944).
Removing it changes a durable document shape, so it is `migrate_then_retire`,
not a deletion.

**The `codex` / `codex_router` config rejection guard looks like residue and is
active protection.** `soma/codex_router/` really is dead — untracked, containing
only `__pycache__` from deleted source. But
`reject_removed_runner_sections` in `config.py` still raises if an obsolete
section appears in an owner config file. That guard is precisely what stops a
retired subsystem being silently reintroduced. `keep_live`.

**The legacy memory store is already half-retired, and the halves need different
verdicts.** `ProjectMemoryRepository` freezes exactly four canonical writers
(`remember_project_fact`, `remember_decision`, `remember_validation_recipe(_model)`)
with `LegacyCanonicalWriteFrozen`, while operational run, job and artifact
recollection stays live and is read on a public path — `knowledge_query search`
returns `memory_hits` from this store. So `soma/memory/` splits: the canonical
writers are `freeze_no_new_use` (already enforced in code, nothing to do), the
operational store is `keep_live`.

That split raised a question worth chasing: `remember_decision` is *both* a
frozen repository method and a live public operation. I traced it —
`remember_repo_decision` is a compatibility alias that keeps the request and
response shape and redirects the destination to canonical Markdown. It never
calls the frozen method. No broken public path.

## Dynamic checks

A fresh process enumerating the public surface returned **30** tools against an
inventory of **32**, which I treated as a contradiction until resolved. It is
call ordering, not missing coverage: `refresh_public_contract_hash()` registers
the knowledge tools itself ([`server.py:224`](../soma/server.py:224)) before
listing, so the count is 32 and `public_schema_hash` is `b99de44a…` — matching
the value `PUBLIC-CAPABILITY-METADATA-1` measured live. Worth recording because
the naive reading was that the two knowledge gateways were absent from the
contract identity. They are not.

The repository was clean before the audit and is clean after, apart from this
document, the manifest and the `PLANS.md` status line.

## An export is a consumer you cannot see

I first classified `soma/local_agent/orchestrator.py` as `remove_candidate`, and
that was wrong. It has no production consumer, is registered on no gateway, and
is not loaded at startup — but `LocalAgentOrchestrator` is listed in
`soma/local_agent/__init__.py` `__all__` and resolved by the package-level PEP
562 `__getattr__`. `from soma.local_agent import LocalAgentOrchestrator` is a
supported import, and the package ships under `include = ["soma*"]`. That makes
it a **public Python package surface**, and the gate's governing rule applies
directly: unknown external consumption is a blocker, not permission to guess.
Reclassified `unknown_blocked`.

My reasoning had absorbed "not an MCP gateway" as "not public". Soma has two
public surfaces, and I audited only one of them.

The test inventory was also wrong. **Ten** files reference the orchestrator, not
seven — my search was truncated by a result limit and I did not notice, which is
the silent-omission hazard operating on the audit itself rather than on the code.
The three I missed are not simply more of the same:

| Files | Kind | Disposition |
|---|---|---|
| `test_local_agent_orchestrator.py`, `test_local_agent_runner.py`, `test_jobs_orchestrator.py`, `test_dashboard_local_agent.py`, `test_external_coder_local_agent.py`, `test_local_coding_local_agent.py`, `test_supervisor_upgrade_local_agent.py` | orchestrator-only routing tests | would follow the orchestrator |
| `test_local_agent_local_model.py` | **mixed** — 7 of 10 tests cover live local-model adapter behaviour that `server.py`'s `local_model_health` depends on, plus a safety invariant that local-model modules execute no commands | **must remain** |
| `test_memory_repository_orchestrator.py` | **mixed** — legacy-memory decision validation, repo profile memory, latest-job-run coverage, plus a memory-module safety invariant | **must remain** |
| `test_policy_local_agent.py` | **mixed** — carries a live invariant that policy modules call no forbidden systems | **must remain** |

So even if the package-surface question were resolved, "delete the orchestrator
and its tests" would have deleted live local-model, legacy-memory and policy
coverage along with it.

## Proposed first removal batch

One item:

1. **`soma/codex_router/`** — untracked build residue containing only
   `__pycache__` from deleted source. Removing it is not a tracked-repository
   change at all.

Sequencing note for any later lane: the orchestrator is the sole in-repo consumer
of `soma/local_coding` and of `soma.memory.importers.import_runs`, so those three
would have to be planned together rather than removed independently.

## Migration proposals

- **`soma/local_coding/`** — `migrate_then_retire`. The dashboard reads
  `runs/local_coding/*/proposal.json`, and eighteen `LocalCodingConfig` fields
  would have to go together. Retirement means dropping the dashboard panel and
  the config block in one bounded step; config removal is itself a compatibility
  event for any existing owner config file.
- **`RepoWikiService.wiki_exclusions`** — retire the constructor parameter while
  keeping the manifest key, or migrate manifest readers first.

## V3 consolidation input

`soma/workflows/`, `soma/supervisor*`, `soma/jobs/`, `soma/job_manager.py` and
`soma/tasks/` genuinely overlap, but consolidating them changes lifecycle
ownership and public contracts — excluded by this gate and by the standing
constraints. `defer_v3_consolidation`, not deletion targets.

## Do not remove

`soma/pilot_memory_1b/` (evidence attestation) · `soma/memory/` operational
recollection and reads (live public path) · `soma/policy/approval_store.py`
(live, with `runs/approvals/` on disk) · `LEGACY_READ_ONLY_TOOLS` (historical run
records still carry those tool names) · the codex config rejection guard ·
`schema_hash` (`keep_live`).

`schema_hash` was first recorded as `keep_compatibility_read` because the field
is legacy and informational — it describes an unrelated repo-patch schema and
never moves with the contract. That was the wrong category. The gate defines
`keep_compatibility_read` as no new writes or activation, and `schema_hash` is
actively emitted on every response, which is an active dependency. **Legacy in
meaning is not the same as inactive in behaviour**, and the classification has to
follow behaviour. Corrected to `keep_live`. Both dispositions forbid removal and
share the same measurement prerequisite, so this changes the label rather than
the outcome.

## Blocked

**`soma/local_agent/orchestrator.py`** — `unknown_blocked` on external Python
import consumption, as set out above.

**Generic `soma.knowledge` operations** (`save_knowledge`, `supersede_knowledge`,
`rebuild_knowledge`, `get_knowledge`, `search_knowledge`, `knowledge_health`)
overlap the canonical `memory_*` family in intent. Classified `unknown_blocked`:
removal is a public contract change and there is no measured evidence of which
controllers still call them. This is the same missing-consumer-inventory gap that
blocked `schema_hash` deprecation in the previous lane — the same gap, now
appearing for a second surface.

## The exact next owner decision

Approve or decline deleting the untracked `soma/codex_router/` cache directory.
Nothing else in this audit is cleared for removal, and that item is not a tracked
repository change — so there is, in practice, no implementation lane worth
opening on the strength of this audit alone.

The real decision is therefore whether to fund a **measurement** lane. Three
separate retirement questions are now blocked on the same missing evidence:

- the generic `soma.knowledge` operations (unknown MCP controller usage);
- `soma/local_agent/orchestrator.py` (unknown external Python import usage);
- `schema_hash` deprecation, deferred by `PUBLIC-CAPABILITY-METADATA-1`.

One measurement lane covering external MCP operation usage and external package
imports would unblock all three. Without it, each is permanently `unknown_blocked`
and the codebase cannot shrink before V3.

A completed audit does not authorise deletion. Nothing was removed or modified.
