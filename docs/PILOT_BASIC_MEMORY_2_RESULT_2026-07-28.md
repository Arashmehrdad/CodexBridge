# PILOT-BASIC-MEMORY-2 — Result

**Date:** 2026-07-28
**Status:** executed; all phases completed; no stop condition fired.
**Gate:** [`PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md`](PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md)
**Outcome:** **`accept_with_minimal_soma_health_and_binding_guard`**

Machine-readable evidence:
[`pilot-basic-memory-2-results-2026-07-28.json`](pilot-basic-memory-2-results-2026-07-28.json),
[`pilot-basic-memory-2-frozen-corpus-2026-07-28.json`](pilot-basic-memory-2-frozen-corpus-2026-07-28.json)

## Verdict in one paragraph

Basic Memory 0.22.1 **passes the two requirements that killed MCP Connector**, and it
passes them convincingly. Its semantic index rebuilds completely from canonical Markdown
in about five seconds with explicit `7 entities embedded, 0 skipped, 0 errors` telemetry,
and when its index is genuinely partial it **refuses to answer** rather than serving a
confident wrong result. Every one of the four bilingual directions works, sibling
isolation is perfect, and removal is clean. It is not accepted outright because project
identity **fails open**: with `default_project` explicitly null, omitting the project
still returned results, and an unknown project name falls back toward *cloud routing*
rather than refusal. Those are exactly the narrow gaps the gate's guard clause was
written for.

## The two decisive tests

### Complete rebuild from Markdown — pass

`memory.db` was deleted outright, canonical Markdown untouched.

| | before | after |
|---|---|---|
| lexical known-hits at rank 1 | 12/12 | **12/12** |
| semantic questions in top 3 | 9/9 | **9/9** |
| sibling leakage | 0 | **0** |
| entities re-embedded | — | **7/7 per project, 0 skipped, 0 errors** |
| rebuild time | — | ~5.5 s per project |

### No stale healthy success — pass

A rebuild was interrupted at 2.4 s, leaving a genuinely partial index of **6 of 14**
entities. With that partial index:

- `bm status` reported **3 pending changes** — not clean, not healthy;
- a lexical known-hit probe for a note that *must* exist returned **0 hits**;
- semantic search returned **0 hits**.

The provider failed closed. This is the precise inverse of MCP Connector, which reported
`status: ok` and answered confidently from a 1-of-7 index. Official recovery restored
14/14, lexical 12/12, semantic 9/9.

## Everything else that passed

| Requirement | Result |
|---|---|
| Lexical canary known-hits | **12/12** at rank 1; the 2 zero-content notes correctly returned 0 hits |
| Black-box completeness probe | threshold-0 nonsense query returned **all 7** notes per project, proving every file holds a live embedding |
| Bilingual matrix, all four directions | en→en, fa→fa (0.462), **fa→en (0.540)**, **en→fa (0.558)** — all rank 1 |
| Sibling isolation | **zero** cross-project results in every query, every phase |
| Safe abstention | nonsense query returned 0 results at both thresholds |
| Filesystem freshness | OS create / edit / rename / delete all correctly reflected |
| Restart stability | 3/3 cycles identical |
| Constrained MCP process | `bm mcp` starts a FastMCP stdio server bound by `BASIC_MEMORY_MCP_PROJECT` |
| Clean removal | no processes, no PATH change, nothing in Soma's `.venv`, no home-directory residue |

The bilingual result is worth dwelling on. This is the requirement MCP Connector could
not satisfy in **any** configuration. Here both cross-language directions work, and they
work on a 0.22 GB local model with no hosted API.

## What requires a Soma guard

### 1. Project omission fails open — the significant one

`default_project` was explicitly set to `null`. Omitting `--project` still returned
**3 results from `soma-pilot`** with exit code 0. The gate requires that omitted identity
cannot silently route. It routes.

### 2. An unknown project falls back toward cloud

An unresolvable project name produced:

> Cloud routing requested but no credentials found. Run `bm cloud api-key save <key>`…

It failed closed **only because no credentials exist on this host**. The fallback path
for an unknown project is cloud, not refusal. On a machine with credentials configured,
that is a very different outcome.

### 3. The similarity threshold is not calibrated per model

`semantic_min_similarity` defaults to `0.55`, tuned for the default English
`bge-small-en-v1.5`. With the required multilingual model, correct answers score
**0.311–0.558**, so only **1 of 9** questions returned anything at the default. Calibrated
against the measured nonsense-query noise ceiling (0.238 → threshold 0.30), **9 of 9**
returned the intended note at rank 1.

Basic Memory offers no per-model calibration and no documented recommended threshold.
Crucially this is **fail-closed** — empty results, never a confident wrong answer — which
is the tolerable failure direction.

### 4. `bm status --wait` livelocks

It polls `get_project_status` roughly every 0.6 s, and **each poll restarts a "First sync…
full scan"** that finds the same 7 new files and never applies them. With no indexer
process running it never converges: 124 s of CPU burned before I stopped it, and it would
have spun to its full timeout. `bm reindex` is the working sync path.

### 5. The provider modifies canonical Markdown

On first sync it rewrote all 14 notes, adding a `permalink:` frontmatter key and
unquoting `title`. **0 of 14 files are byte-identical to the frozen corpus.**

This is human-readable, Git-compatible and non-destructive to note bodies — a mutation,
not corruption. But it corrects something I reported earlier in this lane: Phase C's
"canonical Markdown byte-identical: true" was measured against the *already-mutated*
state. It proves rebuild stability — repeated rebuilds change nothing further — but it
does **not** show the provider never writes to canonical files. It does.

### 6. `bm doctor` is not a completeness oracle

It reported "Doctor checks passed" **while both pilot projects held a partial 6-of-14
index**. It validates the write/sync/search mechanism using its own scratch project
rather than auditing existing project completeness. It also left a `doctor-fbb52e2a`
project directory behind. Any Soma health check must reconcile an OS manifest against
provider counts; `doctor` will not do that job.

### 7. Windows install needs a dependency pin

Default resolution selects `litellm 1.93.0`, which publishes **only manylinux wheels**.
On Windows pip must build its sdist, which requires Rust and fails. Pinned to
`litellm 1.91.4` — the newest stable version inside basic-memory's own declared range
`>=1.60.0,<2.0.0` that ships a pure-Python wheel. That is dependency resolution, not a
source patch. No Rust toolchain was installed; the pre-existing `.cargo` and `.rustup`
directories were not touched.

## The guard this result authorises

Narrow, and strictly within the gate's allowed roles:

- exact `project_id → provider project → constrained process → Markdown root` binding;
- rejection of omitted, unknown or wrong project identity **before** the provider call;
- OS-manifest-versus-provider-coverage health check;
- semantic fail-closed when completeness cannot be proven;
- exact tool allowlist and returned-path validation.

It must not implement storage, embeddings, ranking, semantic search, graph traversal or
provider repair. Nothing observed here requires any of those — the provider's retrieval
is good, its rebuild is trustworthy, and its failure mode is silence rather than fiction.

## Boundaries

Installed only into a disposable venv under `runs/pilots/basic-memory-2/`. Soma's `.venv`
untouched, PATH unchanged (35 entries before and after), no global or client
configuration modified, `claude_desktop_config.json` untouched since 2026-07-25. No
cloud, no remote sync, no hosted embeddings, no telemetry. Provider source unmodified.
Synthetic corpus only. Live ProjectScope, Soma stores, `.soma/wiki/` and Hermes untouched.
Not pushed.

## Cleanup

Provider runtime, databases, embeddings, caches and configuration removed; both
disposable projects deleted after evidence hashes were recorded; zero processes remain;
no residue outside the approved root. The empty `C:\Users\arash\basic-memory` directory
predates this pilot (created 06:11 by an earlier removed probe) and was left as found.

## After this gate

No production integration begins automatically. The permitted next step is preparation of
a **minimal Soma adapter and health-guard decision** — not an implementation lane, and not
a second provider pilot. `PILOT-CODE-INTELLIGENCE-1` remains inactive until this result is
documentation-closed.
