# EXTERNAL-CONSUMER-MEASUREMENT-1 — Result

**Date:** 2026-07-29
**Status:** closed **measurement-complete**.
**Authorisation:** [`EXTERNAL_CONSUMER_MEASUREMENT_1_GATE_2026-07-29.md`](EXTERNAL_CONSUMER_MEASUREMENT_1_GATE_2026-07-29.md)
**Matrix (authoritative for per-surface classification):** [`external-consumer-measurement-1-matrix-2026-07-29.json`](external-consumer-measurement-1-matrix-2026-07-29.json)
**Branch:** `lane/memory-integration-foundation-1` · **Commit:** `5f672db`

## Executive summary

Of the three blocked surfaces, **one is now decidable, one never can be without
new instrumentation, and one turned out not to be an evidence question at all.**

| Surface | Outcome | Recommendation |
|---|---|---|
| Exported `LocalAgentOrchestrator` / `classify_task` | no use found in a complete declared universe | `prepare_deprecation_gate` |
| Six generic `soma.knowledge` operations | operation-level use is structurally unobservable | `remain_unknown_blocked` |
| Legacy `schema_hash` | live comparison contract found | `keep_active` |

`measurement-complete` means complete for the declared universe. It does not mean
complete for the world, and nowhere below does "no consumer was found" become
"no consumer exists."

## The finding that governs everything else

Soma's service log records HTTP lines only:

```
INFO:     127.0.0.1:49267 - "POST /mcp HTTP/1.1" 200 OK
```

Every MCP operation is a `POST` to the same path. The operation name travels in
the JSON-RPC body, which is never logged. **There is no existing record anywhere
of which operations any client calls.**

That would be a tolerable gap if the server were mostly idle. It is not. In the
current log window, since the service started at 09:20:

- 270 `POST /mcp` requests total
- 6 from loopback
- **264 from outside this machine, through the public tunnel**

Roughly 98 percent of the traffic is external and completely opaque as to what it
asked for. Source addresses were counted and deliberately not recorded. The 48
distinct non-loopback sources are almost certainly Cloudflare edge nodes rather
than 48 clients, and must not be read as a client count.

This is why no MCP-operation surface in this lane can be upgraded to proven
non-use. It is not that the search was lazy. It is that the evidence does not
exist, and the gate forbids me from creating it.

## Surface B — the one that moved

`LocalAgentOrchestrator` and `classify_task` were `unknown_blocked` after
`LEGACY-RETIREMENT-AUDIT-1` for a specific and correct reason: external Python
import consumption had never been measured. It has now been measured.

Complete word-boundary searches across all eight registered non-Soma
repositories, the Hermes checkout, the Trading Lab checkout and its installed
distribution, and Claude Code's configuration and plugins found **no reference of
any kind** — not the symbols, not the module path, not a direct import of
`soma.local_agent.orchestrator`.

The installation topology adds an independent argument. Six virtual environments
exist under `D:/Github`. Exactly one contains Soma:

```
soma 0.1.0  →  direct_url.json: {"dir_info": {"editable": true}, "url": "file:///D:/Github/Soma"}
```

There is no independent installed copy of the package on this machine. An
out-of-repository program could only import these symbols by importing the
repository itself.

In-repo, the audit's conclusion holds exactly. Every production import from this
package targets a *sibling* module and never resolves through the package
`__getattr__`:

| Importer | Imports |
|---|---|
| `soma/jobs/models.py`, `job_profiles.py`, `long_run_manager.py` | `PermissionTier` from `.models` |
| `soma/memory/store.py`, `soma/jobs/long_run_manager.py` | `create_audit_event` from `.audit` |
| `soma/supervisor/supervisor_flow.py`, `soma/local_coding/local_coding_manager.py` | `.durable_command_runner` |

None of them load `orchestrator.py`.

So the classification moves from *unmeasured* to *measured and empty*. That is a
real change in the owner's position: it converts a question that could not be
asked into a decision that can be made. It is emphatically not proof of global
non-use. The package ships under `include = ["soma*"]`, and nothing about this
machine constrains what a copy elsewhere imports. Deprecation therefore needs the
owner to accept that residual risk explicitly.

**Named blind spots:** `D:/Github/llm-council`, discovered during the environment
sweep, is not registered with Soma and was not scanned — new roots require
approval. Anything outside `D:/Github`. Any other machine. And a caller that
assembles the symbol name at runtime would not match a literal search.

## Surface A — not aliases, and not orphaned either

I expected to find that the six generic operations were a dead parallel of the
canonical `memory_*` family. Both halves of that expectation were wrong.

**The reads are live over canonical content.** Probing `search_knowledge`
returned the canonical records `kn_36cb4a66…`, `kn_9ec857ec…`, `kn_0c9c4de1…` —
the same identities, the same `vault_path` values that the canonical family
serves. `knowledge_health` reports `canonical_count: 10`, the same 10.
These are not orphaned endpoints pointing at an empty store. They are a **second
live read surface over canonical memory**.

`memory_health` additionally returns `canonical_health`, `provider_health` and
`retrieval_mode`; `knowledge_health` returns none of those. The canonical
operation is a superset, so it replaces the generic read but is not a rename of
it.

**The writes are where the families genuinely diverge**, and this is the finding
worth carrying forward. The two context builders resolve different vault roots:

| | vault root | scope authority |
|---|---|---|
| generic `save_knowledge` | `runs/knowledge/projects/<pid>/vault` (inside the repo) | none — takes `project_id` + `repo_name` directly |
| canonical `memory_save` | `D:/SomaMemory` (external private vault) | explicit `MemoryScope` |

They share **one** catalog, `runs/knowledge/knowledge.sqlite3`, and bind the same
`project_id`. A generic write would therefore register a canonical-looking record
in the shared index whose file lives outside the canonical vault — a second
memory location under one index. Retiring these operations is consequently a
**data question, not a routing rename**.

I did not test that. Confirming it would require writing into memory, which the
gate forbids and which would be exactly the divergence I am describing.

**One runtime trace exists, and it is weaker than it first looks.** The directory
`runs/knowledge/projects/proj_a144f759…/vault` exists, is empty, and predates
this lane (mtime `2026-07-29T03:04:25`). `MarkdownVault.__init__` creates its root
unconditionally, and `_project_knowledge_context` is called from exactly three
places — all six generic operations and nothing else. So at least one of the six
was invoked at least once on this machine.

That is all it proves. Not which operation, not which controller, not whether it
was an external client rather than an owner session earlier that same day. The
directory being empty means no generic write ever landed a file. I am recording
this as level-1 observed use precisely because it is the only runtime trace that
exists, and level-1-but-unattributed is an honest description of it.

## Surface C — an evidence question that dissolved

`schema_hash` is emitted on every response. That was never in doubt and was never
evidence of anything: a server can observe that it sent a field, not that anyone
read it.

What I did not expect to find is that **the field has a designed comparison
contract**. `system_query.capability_identity` accepts `expected_schema_hash` and
compares it. Two probes:

| supplied | result |
|---|---|
| 64 zeros | `ok:false`, `converged:false`, `mismatches:["connector_schema_hash"]` |
| `42bdb69d96fb…` | `ok:true`, `converged:true`, `mismatches:[]` |

The mismatch label names the connector explicitly. So `schema_hash` is not a
vestigial field that happens to still be emitted — it is actively **offered for
comparison** to external controllers. Whether any controller currently supplies
it is unobservable for the same reason as surface A.

The reachability is narrower than the source suggested, and worth recording:
`self_check` rejects `expected_schema_hash` with `extra_forbidden`. The assertion
exists on `capability_identity` alone.

### A false consumer I nearly reported

`hermes_companion_client.py`, `hermes_companion.py` and
`hermes_companion_protocol.py` all carry fields named `schema_hash` and
`expected_schema_hash` — and `HermesServiceStart` *requires* it,
`min_length=64`. Counted naively, Hermes is a mandatory live consumer of the
legacy field.

It is not. Those values come from `effective_schema_hash()` in
`hermes_companion_protocol.py`, computed over Hermes **tool definitions** — a
different field that happens to share a name. Reporting the collision as a
consumer would have made `schema_hash` look permanently unretirable for entirely
the wrong reason.

This confirms the correction made at the close of `LEGACY-RETIREMENT-AUDIT-1`.
`schema_hash` is `keep_live`, and the justification is now measured rather than
argued: there is a live path that returns a different answer depending on what
the caller supplies.

## Two defects in my own searching

Both were caught by controls rather than by luck, and both would have produced a
confident wrong answer.

**Gitignore filtering.** My first sweep used ripgrep's defaults, which honour
`.gitignore`. Re-running with `--no-ignore --hidden` surfaced a match the first
pass had silently skipped. Every count in the matrix comes from the unfiltered
pass.

**A substring false positive.** The pattern `search_knowledge` matched
`re`**`search_knowledge`**`_store` in SeedMind's pytest node ids. All patterns
were re-run with word boundaries, which also dropped the surface C control from
49 files to 32 — `public_schema_hash` had been matching as bare `schema_hash`.

The positive control is what makes the zeros meaningful at all. The same patterns
run against Soma's own source return 9, 28 and 32 matching files. A search that
returns zero everywhere is worthless until it is shown to return non-zero where
matches are known to exist.

## Coverage gaps, stated plainly

| Source | Status | Cost |
|---|---|---|
| CodexBridge checkout | `not_present` | none — CodexBridge is this repository's former identity; the only trace is stale `codexbridge.egg-info` residue |
| Trading Lab scheduled tasks | `not_present` | none — no scheduled task matches soma, trading or codex |
| Claude Code transcripts | `owner_excluded` | **real** — this is the one local record of which operations controllers actually chose, excluded by the gate's chat-history rule |
| `D:/Github/llm-council` | `owner_excluded` | small — one approval would close it |
| ChatGPT connector behaviour | `not_observable` | **decisive** — see the governing finding above |

## Privacy and retention

No telemetry, warning, callback or logging was added. No request arguments,
response bodies or prompts were recorded. Traffic was counted; addresses were
not written into either output. No credentials were read. No raw external source
content was copied — only relative locators, line numbers and paraphrase. Chat
history and private vault content were not scanned; `D:/SomaMemory` was touched
only as a file count and as record metadata already served on the public read
path.

All probes were read-only. `knowledge_records` is still 10 and `generation` is
still 1. One acknowledged side effect: the read-only generic probes construct
`MarkdownVault`, which creates its root directory if absent. That directory
already existed and was already empty, and its pre-probe state was recorded
before any probe was issued. No file was created.

## The exact next owner decision

**One decision is ready.** Approve or decline a bounded gate to retire
`soma/local_agent/orchestrator.py` and its export, accepting the residual
external-import risk in writing. That gate must sequence `soma/local_coding` and
`soma.memory.importers.import_runs` — the orchestrator is their only in-repo
consumer — and must not delete the three mixed test files identified by the
retirement audit.

**One decision is upstream of everything else.** Whether to open a separate,
owner-reviewed instrumentation gate that records MCP **operation names and
nothing else** for a bounded window. That single missing capability is what
blocks surface A, and it is what would let any future retirement question about a
public operation be answered rather than deferred. This lane was explicitly
forbidden from adding it, and did not.

**One decision needs nothing further.** `schema_hash` stays. It is `keep_active`
with a live comparison contract, and its deprecation is a public contract change
to be argued on its own merits — not a consumer-evidence question.

**One optional item:** approve scanning `D:/Github/llm-council` to close the last
local blind spot for surface B.

Nothing was deprecated, removed, renamed or redirected. No measured surface was
changed.
