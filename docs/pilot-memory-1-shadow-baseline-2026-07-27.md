# PILOT-MEMORY-1 — Shadow Baseline and Fixed Benchmark

**Date:** 2026-07-27
**Status:** started in shadow mode. Not activated, not integrated, holds no
authority.
**Machine-readable results:**
[`pilot-memory-1-shadow-benchmark-2026-07-27.json`](pilot-memory-1-shadow-benchmark-2026-07-27.json)

---

## 1. What "shadow mode" means here

The pilot is running **beside** Soma, wired to nothing:

- the vault lives in a disposable temporary directory and is removed after each
  run;
- Soma does not read it, no MCP operation exposes it, and no Soma record depends
  on it;
- it is not `.soma/wiki/`, it is not the repository wiki, and it does not touch
  repository knowledge;
- no Obsidian vault was created in the owner's filesystem;
- nothing in `runs/` or the live store was read or written.

The durable output is not the corpus. It is the **fixed benchmark** below, which
is the artifact PLANS.md actually requires: *"a more complex memory provider
advances only after a fixed benchmark demonstrates a real failure of the
baseline."*

## 2. Baseline under test

The deliberately least-complex thing that could work:

- **Markdown files** with a small frontmatter block — `project`, `source`,
  `created`, and optionally `supersedes`.
- **Git** as the durability, history, and external-edit-detection layer.
- **Obsidian-native `[[wikilinks]]`** for relations, so the owner-facing
  workspace needs no custom tooling.
- **No database.** The index is derived from files on every read, so the files
  are the only authority. This is what makes "rebuild" meaningful rather than
  circular.

Structured Soma metadata is the frontmatter: the fields Soma would index if this
ever became integrated. Critically, `project` is one of them, and the retrieval
function **refuses an unscoped query** rather than returning everything — the
same fail-closed posture ProjectScope takes.

## 3. The fixed benchmark

Seven question classes, drawn directly from the PLANS.md requirement. The corpus
is ten notes across **two deliberately similar projects** (`soma` and
`soma-lab`) with near-identical vocabulary, mirroring PILOT-SCOPE-1's
confusion-resistance premise.

| # | Class | Question |
|---|---|---|
| 1 | exact-recall | Can an exact fact be recalled verbatim? |
| 2 | current-vs-superseded | Does a corrected fact win over the fact it replaced? |
| 3 | source-resolution | Does every fact carry a source that still resolves? |
| 4 | external-edits | Is an edit made outside the tool visible and attributable? |
| 5 | deletion | After a deletion, are the references to it detectable? |
| 6 | rebuild | Does a full rebuild reproduce the index exactly? |
| 7 | project-isolation | Do two near-identical projects stay separated, and does an unscoped query fail closed? |

## 4. Result: 7 / 7 passed

| Class | Outcome |
|---|---|
| exact-recall | 1 hit, `soma-runtime-port`, no false positives from the sibling project |
| current-vs-superseded | current = `soma-db-size`; `soma-db-size-old` correctly marked superseded, not deleted |
| source-resolution | every note's `source` resolves to a real path in the Soma repository |
| external-edits | an out-of-band edit was visible on reindex and attributed by `git status` as `M soma-transport.md` |
| deletion | the note vanished and the dangling reference `soma-dangling → soma-removed-note` was reported |
| rebuild | rebuilt index hash identical to baseline (`fcaa442c7d1a2c7d…`) |
| project-isolation | `soma` and `soma-lab` each returned exactly their own note; zero leakage; unscoped query rejected |

**The baseline did not fail any question class.** Under the plan's own rule,
that means a graph or memory service has **not** earned its complexity yet.

## 5. What this result does and does not license

It does **not** mean the baseline is sufficient. It means the benchmark, as
currently specified, does not yet discriminate. The honest reading is that the
questions are correct but the corpus is small and synthetic — ten notes written
in one sitting, with clean frontmatter, by the same author.

The classes most likely to break first at real scale, and where the benchmark
should be hardened before it is trusted as a gate:

1. **Superseding chains.** The corpus tests one hop. Real memory accumulates
   `A ← B ← C`, plus partial supersession where a note replaces one claim from a
   predecessor rather than all of it. A single `supersedes` field will not carry
   that.
2. **Retrieval by meaning.** Every probe here is a substring match. The moment a
   question is phrased differently from the note, plain grep fails and the
   result says nothing about whether a graph or embedding layer would help.
3. **Frontmatter drift.** Sources resolve because the notes were written
   correctly minutes ago. The interesting measurement is what fraction of
   sources still resolve after months of repository movement.
4. **Scale.** Derive-on-read is fine for 10 notes. The rebuild class should
   record a time budget and be re-run at 10³ and 10⁴ notes.

## 6. Relationship to ProjectScope

Project isolation is the one class where the baseline and Soma's production work
already agree: the shadow retrieval function makes `project` mandatory and
rejects an unscoped query. That is the same invariant `SCOPE-FOUNDATION-1`
enforces for writes.

This is a design echo, not an integration. Memory remains an explicit exclusion
of Gate B and Gate C, and nothing in this pilot changes that.

## 7. Next step, when selected

The useful next move is **not** to adopt this baseline or to evaluate a memory
service. It is to harden the benchmark on the four axes in §5 — especially
superseding chains and meaning-based retrieval — so that it can produce a real
failure if one exists. A benchmark that passes everything is not yet evidence.

This pilot remains inactive. It is not integrated, and it does not advance on a
generic `continue`.
