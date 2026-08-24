# Soma Knowledge Carry-Forward Research — Iteration 01

**Date:** 2026-08-24  
**Status:** research baseline complete  
**Programme scope:** Soma knowledge retention, consolidation, indexing, retrieval, and wiki behavior  
**Symptom source:** NSDN was used only as a reproducible example of a Soma knowledge carry-forward failure. NSDN is not the subject of this research programme.

## 1. Research question

Why can a later ChatGPT/Soma research turn fail to carry forward important project knowledge that still exists in the repository, and why did the repository wiki not prevent that failure?

The concrete symptom was a later NSDN repo review rediscovering previously established results such as the Research 035 dendritic/context-gating outcome and constraints that should already have been available to subsequent reasoning.

## 2. Method

This iteration followed the enabled `arash-research` Skill, revision `R8-I1` / package `cb5a6a616ad9977eec78aae7aebad6e1f150cd53901d3ca7f4c09f869a1a8e4f`:

1. inspect authoritative repository/runtime evidence before drawing conclusions;
2. separate observed evidence from inference;
3. prefer exact repo/runtime state over memory;
4. test an adversarial alternative that could change the conclusion;
5. preserve uncertainty rather than invent missing facts.

No source implementation was changed as part of the research conclusion. The only policy edit made in this thread is the owner-requested `AGENTS.md` rule that future Soma research must be persisted under `docs/` before being treated as complete or reported.

## 3. Observed evidence

### 3.1 The source knowledge still exists in the project repository

Direct NSDN repository search found Research 038 carrying forward the relevant Research 035 result:

- `docs/research/038_end_to_end_associative_geometry_attribution_preregistration.md`, line 98: Research 035 directly tested an upstream dendritic/context-gating formulation and did not earn dendritic-specificity credit on final REPORT.
- line 100: Research 038 explicitly forbids relabelling generic upstream dendritic gating as a new solution and narrows any later routing candidate to memory/preconditioner admission, head-state routing, or information-dependent state allocation at the associative substrate.

Therefore the underlying research record was not deleted.

### 3.2 Canonical NSDN project memory exists and is internally healthy

Live `memory_scope` / `memory_health` for NSDN reported:

- project ID: `proj_repo_ee86415665bff49a2063068e`;
- canonical health: `healthy`;
- canonical record count: `31`;
- indexed count: `31`;
- malformed count: `0`;
- drifted count: `0`.

This rejects the simple explanation that the canonical project-memory vault itself is corrupt or empty.

### 3.3 The active memory provider is degraded and retrieval has fallen back to lexical mode

The same live `memory_health` reported:

- provider health: `degraded`;
- retrieval mode: `catalog_lexical`.

A direct memory query containing the exact research concepts — `Research 035`, upstream dendritic/context gating, branch contribution, association age, binding distance, RNG/data identity, and dynamic spectral routing — returned zero records.

The gateway warning was explicit: canonical lexical retrieval matches literal terms rather than natural-language questions and no record contained every query term.

This is direct evidence that stored project memory can be present while retrieval still fails for a semantically relevant later question.

### 3.4 The research knowledge plane is largely unpopulated semantically

Live `research_health` for NSDN reported:

- archive objects: `7`;
- sources: `7`;
- source versions: `7`;
- claims: `0`;
- evidence links: `0`;
- research questions: `0`;
- design decisions: `0`;
- relationships: `0`;
- context packets: `3`;
- research index status: `not_configured` with `7` eligible items.

Therefore Soma currently has source objects but no structured claim/decision/relationship layer for this project and no configured research semantic index.

### 3.5 The repository wiki is explicitly a structural cache, not a research-state ledger

Soma source `soma/repo_wiki.py` defines the generated wiki as a deterministic repository-local wiki and its rendered index states:

> This wiki is a structural cache generated from one repository snapshot.

The generated pages are limited to:

- Overview;
- Architecture;
- Modules;
- Validation.

The code's verification guidance says the wiki is for orientation, system relationships, implementation navigation, and checks, while exact claims should be verified against live Git/source.

This directly contradicts the assumption that the current wiki is intended to function as an authoritative semantic history of research claims, falsifications, supersession, and negative knowledge.

### 3.6 The NSDN wiki was stale at the time of this audit

Live `read_wiki` for NSDN returned:

- wiki generation: `20260823T215228590611Z-9a3fb96-7fe8dc8`;
- indexed HEAD: `9a3fb96028269520396bdab80748ca970de4a850`;
- indexed source generation: `77`;
- current source generation: `100`;
- outer gateway stale status: `true`.

The rendered page itself still contains the older snapshot's `stale: false`, which is historical content from the indexed generation; the live gateway correctly reports the current mismatch as stale.

Staleness therefore increased the chance that the wiki would omit newer repository state, but it is not the whole explanation because the wiki's design is structural even when fresh.

## 4. Adversarial alternatives

### Alternative A — The repository actually forgot the result

**Rejected.** Direct repo search found the relevant result and the later Research 038 carry-forward restriction.

### Alternative B — Canonical memory corruption caused the failure

**Not supported by current evidence.** Canonical health is healthy, all 31 records are indexed, and there are no malformed or drifted records. Retrieval/provider quality remains a separate failure surface.

### Alternative C — Wiki staleness alone caused the failure

**Rejected as a complete explanation.** The wiki is currently stale, but Soma source explicitly defines it as a structural cache with architecture/module/validation pages. Even a freshly generated wiki is not presently a claim/falsification/decision graph.

### Alternative D — This is classic model catastrophic forgetting

**Rejected for this incident.** The relevant knowledge remains available in durable project source. The observed failure occurs between durable source, consolidation/indexing, retrieval, and later reasoning context. The more precise name is **knowledge carry-forward failure**.

## 5. Inference

The reproduced failure path is currently best described as:

```text
research/source document retains result
        ↓
insufficient semantic consolidation into canonical/research knowledge
        ↓
research claim/decision/relationship layer mostly empty
        ↓
semantic research index not configured
        ↓
project memory provider degraded → lexical fallback
        ↓
semantic query fails to retrieve the relevant prior result
        ↓
structural wiki does not supply the missing scientific state
        ↓
later reasoning proceeds without an inherited constraint
        ↓
full repository review rediscovers the knowledge
```

The repository is therefore functioning as the ultimate durable scientific truth, but Soma is not yet reliably converting that truth into a robust carry-forward representation that later reasoning can retrieve.

## 6. Current conclusion

A wiki-only redesign is **not yet justified** as the fix.

The evidence points to a broader architectural problem involving at least four layers:

1. **consolidation** — important research outcomes must become explicit durable claims/decisions, including negative results and falsifications;
2. **relationships/temporal state** — later knowledge must be able to say that an earlier hypothesis was tested, rejected, narrowed, superseded, or remains unresolved;
3. **retrieval** — semantic retrieval needs a reliable path and a useful degraded-mode fallback;
4. **presentation** — the wiki can then become a human-readable projection of this semantic knowledge rather than being expected to be the knowledge authority itself.

## 7. Design requirement emerging from Iteration 01

Future research work should investigate a **knowledge preflight** before a new research iteration proceeds. The controller should be able to recover, at minimum:

- relevant prior falsifications and failed approaches;
- mandatory protocol invariants;
- accepted architecture decisions;
- unresolved hypotheses;
- claims that remain hypotheses rather than established findings;
- provenance linking each carried-forward statement to the authoritative source.

A known-answer retrieval failure should be observable as a knowledge-layer defect instead of silently allowing later reasoning to proceed as if the prior result did not exist.

## 8. Next research question

Iteration 02 will compare the main architecture options without implementation:

1. enhanced generated wiki;
2. structural wiki plus a structured claim/decision/falsification ledger;
3. temporal research knowledge graph plus hybrid retrieval and a wiki projection.

The comparison must include degraded-provider behavior, negative-knowledge retention, temporal/supersession semantics, provenance, maintenance cost, retrieval accuracy, and how much complexity is actually justified for Soma.

No wiki or memory architecture rework is approved by this iteration alone.
