# PILOT-OBSIDIAN-MCP-1 — Result

**Date:** 2026-07-28
**Status:** executed; stopped on a documented stop condition.
**Gate:** [`PILOT_OBSIDIAN_MCP_1_GATE_2026-07-28.md`](PILOT_OBSIDIAN_MCP_1_GATE_2026-07-28.md)
**Outcome:** **`reject_mcp_connector_activate_basic_memory_comparison`**

Machine-readable evidence:
[`pilot-obsidian-mcp-1-results-2026-07-28.json`](pilot-obsidian-mcp-1-results-2026-07-28.json),
[`pilot-obsidian-mcp-1-frozen-corpus-2026-07-28.json`](pilot-obsidian-mcp-1-frozen-corpus-2026-07-28.json),
[`pilot-obsidian-mcp-1-preflight-2026-07-28.json`](pilot-obsidian-mcp-1-preflight-2026-07-28.json)

## Verdict in one paragraph

MCP Connector is a **well-built, genuinely secure-by-default provider with excellent
semantic retrieval** that fails three named reliability requirements, two of them
reproducibly after a clean rerun. It closes the exact paraphrase gap that
`PILOT-MEMORY-1B` recorded against Markdown + Git, and its project isolation is the
strongest evidence in this pilot — zero cross-vault results anywhere. But its semantic
index cannot be reliably rebuilt from the vault, it reports success while answering
from an index containing one seventh of the corpus, and link-aware rename both hangs
and silently breaks backlinks. Canonical Markdown was never corrupted, so nothing was
lost — but a memory layer that confidently answers from an incomplete index is the
precise failure mode Soma's own corpus calls the Silent Omission Hazard.

## What passed, and it is a lot

| Requirement | Result |
|---|---|
| Loopback-only binding | one listener on `127.0.0.1` per vault, no LAN interface |
| Bearer authentication | missing / wrong / empty tokens **all** rejected `401` |
| Per-vault token isolation | distinct tokens; cross-token rejected `401` **both directions** |
| Sibling isolation | **zero** cross-vault results across all 20 questions, both methods |
| Source integrity | installed bytes match the frozen release exactly |
| Core profile restricts surface | 52 → 16 tools; `fetch` and `execute_*` removed |
| Semantic paraphrase | **6/6** intended notes in top 3 |
| Persian paraphrase | **3/3** intended notes in top 3 |
| Literal search | 2/2, with path + line + context grounding |
| Structured / `.base` queries | 2/2; Bases returned filtered structured CSV |
| Backlinks | exactly the 3 expected referrers, including the Persian note |
| External manual edit | detected and searchable after reload |
| Deletion | explicit, correctly produced a dangling reference |
| Markdown integrity | **21/25 byte-identical**; survived two forced kills with zero drift |
| No client auto-configuration | `claude_desktop_config.json` untouched since 2026-07-25 |
| Clean removal | plugin, index, listeners and residue all gone |

The paraphrase result deserves emphasis. `PILOT-MEMORY-1B` measured the Markdown + Git
baseline missing **4 of 6** paraphrase questions entirely — not ranked low, absent. The
same six questions against this provider returned the intended note in the top three
**every time**, four of them at rank 1. That is a real capability gain, and it is why
this rejection is narrow rather than a dismissal.

## What failed

### 1. The Core surface is not static — `activate_tool` is always present

The gate requires that the Core surface "cannot self-activate additional tools." It can.

`tool_catalog`, `activate_tool` and `activate_tools` are hard-coded into every non-`all`
profile. Any holder of the bearer token can enumerate all **52** tools and promote any
of the **36** inactive ones — including `fetch` (open-world), `execute_obsidian_command`,
`delete_vault_file` and `search_and_replace`. Demonstrated: the advertised surface grew
**16 → 18** with two MCP calls.

The sharpest part is that `persist` defaults to `false`, so the expansion **leaves no
trace in `data.json`**. A configuration audit after the fact shows `promoted: []` and a
clean Core profile while the live session is running an expanded surface. Restricting
the profile constrains the default, not the ceiling.

### 2. The semantic index cannot be rebuilt from the vault

`soma-lab-pilot-vault` indexed **1 of 7** notes — `embeddings.meta.json` recorded
`recordCount: 1`, and the segment file was 1,536 bytes, exactly one 384-dimension
vector. `soma-pilot-vault` indexed 17/17 under identical settings.

It survived every documented remedy: deleting the index directory and reloading the
plugin, bringing the vault to the foreground, and touching every file's mtime. The
official CLI registers **no** plugin commands, so there is no reindex trigger to invoke.

### 3. Stale success — confident answers from a one-note index

With that 1-of-7 index the provider reported `status: ok` and answered every query,
returning the same single note each time — including for a query it scored at
**−0.065**, a negative similarity. No warning, no completeness signal, no error.

Separately, setting the gate-mandated `multilingual-e5-base` produced **0 results for
every query** with `errorCode: null` and `isError: false`. The E5 index directory was
never created. Status still `ok`.

Two different silent failures, both presenting as success.

### 4. Link-aware rename hangs and breaks backlinks

`rename` returned nothing for **45 s**, then for **150 s** on a clean rerun against a
different note. In both cases the file was renamed on disk and the referring wikilinks
were **not** rewritten — 3 dangling references from 2 renames. The gate requires rename
to preserve wikilinks and backlinks; it does neither, and it hangs while not doing it.

### 5. Cross-language retrieval

0/2 under the only working model (`native-minilm-l6-v2`, English-only, 384-dim). Since
the mandated multilingual model yields an empty surface, there is no configuration in
this release that satisfies the bilingual requirement.

## Stop condition

> Windows hangs, stale-success behavior or Markdown corruption repeats after one clean rerun

Fired twice independently: the rename hang reproduced on a second note, and
stale-success on an incomplete index reproduced after index deletion and rebuild.

## Harness defect, disclosed

My first corpus revision named files by slug while wikilinks used frontmatter titles.
Obsidian resolves `[[X]]` against the **file name**, not a `title` property, so all 13
wikilinks dangled and `file=` lookups missed. A `.base` view also used a bare filter
list instead of an `and` key. My own dangling-link precheck used the wrong resolution
model and reported "none", so the provider's `unresolved` count of 13 was the first
honest signal.

Corrected by renaming files so filename equals title and fixing the filter syntax, then
re-freezing the corpus **before** rerunning the affected checks. This touched only the
link, backlink and `.base` results. Every provider failure above was observed after the
correction and is independent of it. It did not change the outcome.

## Boundaries

Obsidian was installed by the owner, not the controller. The controller enabled the
CLI via the global `obsidian.json` flag — equivalent to the Settings toggle — in a file
that did not pre-exist and was deleted at cleanup.

Not used: BRAT, `.mcpb`, auto-client-configuration, Adaptive or All profiles, command
execution, web fetch, cloud, remote sync, hosted models. Not touched: live ProjectScope,
Soma stores, MCP schemas, `.soma/wiki/`, Hermes, production vaults, repository source.
No bearer token appears in any committed file — tokens are referenced by truncated
SHA-256 only. Not pushed.

## Cleanup

Plugin uninstalled from both vaults, embeddings indexes removed, no listeners remain, no
residue outside approved locations, both disposable vaults deleted after hashes were
recorded, controller-created `obsidian.json` removed. The Obsidian application itself is
left installed — the owner installed it and it is theirs to keep.

## Post-pilot interpretation and next gate

The raw observations and outcome above remain unchanged. Subsequent solution discovery
classified them more precisely:

- incomplete rebuild and stale healthy success are the decisive blockers;
- silent multilingual-model failure is a hard bilingual requirement failure;
- the rename path is unsafe as observed, but the root cause is not proven because the
  Obsidian **Automatically update internal links** setting was not recorded;
- Core tool expansion is a manageable integration weakness on the owner's single-user,
  loopback-only laptop and can be contained by a Soma allowlist; it is not independently
  a provider-selection blocker.

Basic Memory must focus on complete rebuild, fail-closed health, bilingual retrieval and
filesystem freshness. However, MCP Connector's provider-specific authentication,
isolation and Markdown results do not transfer to Basic Memory. The successor gate keeps
small provider-specific project-constraint, sibling-isolation, Markdown-integrity and
clean-removal checks without repeating the old broad benchmark.

The accepted follow-up decision is
[`MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md`](MEMORY_PROVIDER_SOLUTION_DISCOVERY_2026-07-28.md).
The only executable memory gate is
[`PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md`](PILOT_BASIC_MEMORY_2_GATE_2026-07-28.md).

A materially changed MCP Connector release remains worth a later bounded re-test because
its retrieval, isolation, authentication and canonical-file behavior were strong. That
re-test must freeze the shipped artifact, verify index accounting and stale-success
behavior first, and record the Obsidian automatic-link-update setting before rename.

`PILOT-CODE-INTELLIGENCE-1` remains planned and inactive. No production memory
integration begins without a separate acceptance decision.
