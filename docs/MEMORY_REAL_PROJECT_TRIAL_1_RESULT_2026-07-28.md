# MEMORY-REAL-PROJECT-TRIAL-1 — Bounded Cross-Controller Trial Result

**Date:** 2026-07-28
**Status:** executed; real project memory is live and retrievable. Three
defects found that only real use could expose, the third only after the
restart. Cross-controller verification is **partial** — one controller proven,
two pending.
**Authorising decision:** [`SOMA_CANONICAL_MEMORY_VAULT_DECISION_2026-07-28.md`](SOMA_CANONICAL_MEMORY_VAULT_DECISION_2026-07-28.md) §Next permitted lane
**Foundation:** [`MEMORY_INTEGRATION_FOUNDATION_1_RESULT_2026-07-28.md`](MEMORY_INTEGRATION_FOUNDATION_1_RESULT_2026-07-28.md)
**Branch:** `lane/memory-integration-foundation-1` — not pushed.

## Result

Eight reviewed Soma project memories are canonical in `D:\SomaMemory`, and the
live MCP server retrieves them with full provenance. Canonical health is
`healthy` (8/8, zero malformed, zero unadopted); provider health is `degraded`
and retrieval mode is `catalog_lexical`, exactly as designed.

The trial found two defects that the synthetic suite could not, both of which
would have shipped.

## Seeded set

All under `D:\SomaMemory\projects\proj_a144f759-…\`, `review_state: reviewed`,
each carrying `sources` and `locators` pointing at the committed decision docs.

| Path | Kind |
|---|---|
| `architecture/canonical-memory-authority.md` | decision |
| `architecture/semantic-retrieval-disabled.md` | decision |
| `architecture/basic-memory-provider-profile.md` | fact |
| `architecture/legacy-memory-store-retired.md` | decision |
| `architecture/project-scope-is-the-identity-authority.md` | fact |
| `architecture/single-task-authority.md` | fact |
| `architecture/research-authority-is-separate.md` | fact |
| `lessons/counts-are-not-membership.md` | lesson |

No personal memory, no legacy import, no conversation ingestion.

## Defect 1 — a successful write reported as a failure

The very first live `memory_save` returned:

```
Output validation error: Additional properties are not allowed
('content_sha256', 'operation', 'project_id', 'revision' were unexpected)
```

**The canonical Markdown had already been written.** The caller was told its
write failed when it had succeeded — the worst available failure mode, because
the natural response is to retry and the natural conclusion is that memory is
broken.

The suite missed it because tests invoke the dispatch function directly; only
the MCP surface validates output. `CANONICAL_MEMORY_ACTION_OUTPUT` now declares
the acknowledgement, every action response in the gateway test is validated
against the published schema, and the composite moved from `oneOf` to `anyOf`
because all variants share one minimal failure shape, so a refusal legitimately
satisfies more than one and `oneOf` rejected correct responses for being too
conformant.

## Defect 2 — the production retrieval path was unusable

Catalog search was a single `LIKE %<whole normalised query>%`.

| Query | Records |
|---|---|
| `semantic` | 2, correct, full provenance |
| `semantic retrieval disabled` | **0**, `omitted_count: 0`, no warning |

Semantic retrieval is disabled, so **lexical is the production path** — and it
was unreachable by the way a controller actually asks. An empty answer was
indistinguishable from "no such memory exists": the Silent Omission Hazard in a
new place.

Two changes, both deliberately short of building a retriever:

- search matches **every term**, in any order and position. No scoring, no
  stemming, no proximity, no ranking; ordering stays stable by recency.
- a multi-term query returning nothing now says why, so a controller retries its
  phrasing rather than concluding the memory was never recorded. A single-term
  miss stays a plain absence, because that is what it is.

## The honest limit that remains

Term-AND retrieval answers **keyword** queries, not natural-language questions.
Measured against the live vault after the fix:

| Question | Hits |
|---|---|
| `semantic retrieval disabled` | 1 ✓ |
| `counts membership` | 1 ✓ |
| `why is semantic search off` | 0 |
| `who owns rebuild execution` | 0 |
| `does a note become a research claim` | 0 |

The failures are function words: `why`, `off`, `who`, `does` appear in no
record. Closing that gap requires semantic retrieval, which stays disabled until
index membership can be proven. Building stopword handling, scoring or ranking
here would be the custom retrieval engine the architecture explicitly forbids,
so it was not done.

**This is the real, current cost of the membership measurement, and controllers
should be told to search with keywords.**

## Verified live

| Check | Result |
|---|---|
| canonical health through live MCP | `healthy`, 8/8, 0 malformed, 0 unadopted |
| retrieval names its mode | `catalog_lexical`, provider `degraded` |
| records carry provenance | `sources`, `locators`, `content_sha256`, `revision` |
| context packet assembled and stored | `pkt_e6ee865c…`, `packet_sha256` present |
| exact packet retrieval | same `packet_id` **and** same `packet_sha256` |
| bounded projection stays identifiable | at 2 KiB: `truncated: true`, `has_more: true`, hash unchanged |
| memory and research stay separate | research operations return no memory record |

## Cross-controller status — partial

- **Claude Code — verified.** This session read the seeded memories through the
  live MCP server, a separate process that never performed the writes.
- **ChatGPT — not verified.** Cannot be driven from here.
- **Hermes — not verified.** Cannot be driven from here.

The lane asks for all three. Two remain outstanding and are **not** claimed.

## After the restart — both fixes confirmed, and a third defect found

The owner restarted the service. Verified live on the restarted build:

| Check | Result |
|---|---|
| `memory_search` `semantic retrieval disabled` | 1 record, correct, full provenance |
| `memory_save` of a real ninth memory | `ok: true`, no validation error |
| canonical health after the write | `healthy`, 9/9 |

Writing that ninth memory then exposed **defect 3**, which only a real write
followed by a real read could show.

## Defect 3 — the integrity hash proved nothing

The write acknowledged `content_sha256: f71d50ef…`. Every subsequent read of
the same record reported `8606ab5e…`. Two defects were stacked so that neither
was visible on its own.

**A body ending in a newline could never round-trip.** The vault writer
terminates a body with a newline and the reader strips every trailing one, so
the hash was computed over a string the file could not read back. The
acknowledged hash is also the compare-and-swap token, so the caller was handed
a precondition that could never be satisfied — corrections to that record were
impossible.

**`read()` recomputed the hash instead of comparing it.** That made the field
self-fulfilling: any disagreement between the bytes on disk and the hash the
writer recorded was overwritten on the way out, so a drifted record and an
intact one were indistinguishable. The v2 hash exists specifically to protect
lifecycle and provenance from out-of-band edits; recomputing silently undid it.
An existing acceptance test asserted the recompute *as* external-edit
detection — detection that changed the hash to match the edit and told nobody.

Fixes: body normalisation moved to the model, where writer and reader are
guaranteed to agree; `read()` leaves the stored hash alone; drift is reported
through `rebuild` and `health` (`drifted_count`, `drifted_paths`, status
`dirty`) and warned about in search results.

Drift is **never repaired implicitly**. A stored hash that disagrees with its
file can mean the writer was wrong or that the file was edited afterwards, and
nothing in the record distinguishes the two. Restamping would absorb an
out-of-band edit exactly as silently as it absorbed this bug.

## Live vault state

Measured against `D:\SomaMemory` with the fixed code:

| | |
|---|---|
| indexed | 9 |
| malformed | 0 |
| unadopted | 0 |
| **drifted** | **2** |
| status | `dirty` |

The two are `architecture/canonical-memory-authority.md` and
`lessons/gateway-output-schema-must-cover-every-response.md`, both from defect
1's trailing newline. The other seven round-trip exactly. Their content is
intact and retrievable; what is unproven is that it is the content the writer
recorded.

## Repair — `memory_accept_drift`, used on exactly those two

The owner authorised the repair, so drift acceptance became a named public
action rather than a manual restamp. It is the **only** path that rewrites a
record's integrity hash, and it is narrow on purpose:

- the record must actually be drifted, so it cannot double as a way to rewrite
  an intact record's hash;
- `accepted_sha256` must equal the hash of the content *as it stands*, so the
  caller names the exact bytes it adopts. A file that changes between reading
  and accepting is a refusal, not a race;
- it is deliberately **not** part of `memory_rebuild_index`. A rebuild that
  repaired drift on its own would launder an out-of-band edit into canon.

Note the inverted precondition against the lifecycle actions: those name the
hash they expect to still hold, this names the new hash being adopted — hence a
separate request model rather than another `expected_sha256` branch.

Using it exposed one more gap: nothing on the read path carried the recomputed
hash, so repairing a record meant computing it out of band and the gateway was
insufficient for the operation it had just gained. `memory_get` and
`memory_search` now report `integrity_drift` and, when drifted, `actual_sha256`
— the decision and the token it needs arrive together.

**Acceptance was justified by evidence, not convenience.** For both records,
hashing the body *with* its trailing newline reproduces the stored hash exactly,
which proves the content was never edited and only the normalisation boundary
moved. Had that not held, the correct response would have been to leave them
drifted.

| Record | Stored | Adopted |
|---|---|---|
| `architecture/canonical-memory-authority.md` | `589e94e5…` | `854e812f…` |
| `lessons/gateway-output-schema-…md` | `f71d50ef…` | `8606ab5e…` |

Both moved to revision 2 with content untouched. Verified live afterwards:

| Check | Result |
|---|---|
| canonical health | `healthy`, 9/9, **0 drifted** |
| independent recheck outside the gateway | 9 consistent, 0 drifted |
| re-accepting an intact record | refused: "is not drifted; there is nothing to accept" |
| record content after acceptance | unchanged, `revision: 2`, retrievable |

## Still open

- **ChatGPT and Hermes remain unverified.** Only Claude Code is proven.

## Boundaries

Real project memory only, in the owner-decided vault. No personal scope, no
legacy import, no conversation ingestion, no semantic activation, no Git init or
cloud sync in the vault, no deployment, no push. The seeded records are small,
reviewed and individually traceable to committed decision documents.
