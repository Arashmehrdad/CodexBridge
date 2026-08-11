# Canonical Project-Memory Workflow — Independent Audit

**Date:** 2026-08-04
**Auditor:** independent review (Claude Code). The audit prompt **supplied eight preliminary findings to verify or refute**; they were independently reproduced rather than accepted, and §2 records where they are wrong, understated, or misdiagnosed.
**Status:** audit only. No **pre-existing** source, documentation, canonical record, ProjectScope binding, or runtime state was changed. This audit report itself was created as a new file, and remains uncommitted.
**Revision:** 3 — corrected 2026-08-04 under owner review. See §17 and §18 for what changed and why.
**Live build audited:** `server_build_hash f55d37e7d65b…`, `public_schema_hash 84d0af8b66d7…`, `capability_epoch f55d37e7d65b-42bdb69d96fb`
**Repositories:** `D:\Github\Soma`, `D:\Github\Axon_modelling`, `D:\Github\andia_beauty`
**Vault:** `D:\SomaMemory`

---

## 1. Executive verdict

The reported behaviour is **reproducible, systemic, and correctly attributed to Soma — not to controller incompetence.**

A controller that behaves *correctly* — reads the repository's own documentation, calls the operation that documentation names, and verifies the result the way the documentation says to verify it — is led to a **zero-result dead end** and then to a repository file. The failure is designed into the current documentation and public schema.

The single most decisive piece of evidence is §3.1: the only search operation Soma's own memory documentation tells a controller to use returns **`memory_hits: []`** for a project that has **18 healthy canonical records**.

The preliminary assessment is **directionally right on 7 of 8 points but materially incomplete on two, and wrong in its characterisation of one.** Corrections are in §2.

**Classification:** architectural contract defect (primary) + stale documentation (primary) + weak discovery metadata (contributing) + lifecycle validation defect (independent, confirmed live). A **controller-environment namespace collision** aggravates one controller (§2.1(a)) but is external to Soma and is not required to explain the failure. It is **not** primarily controller misuse and **not** primarily owner-language ambiguity.

---

## 2. Adjudication of the preliminary findings

| # | Claim | Verdict | Correction |
|---|---|---|---|
| 1 | "Project memory" describes several surfaces | **Confirmed, understated** | **Four Soma-owned surfaces**, not three — the fourth (generic `save_knowledge`) has its own Markdown vault inside the repository, not "a SQLite store". A fifth, external, controller-environment surface aggravates one controller but is not Soma's. See §4. |
| 2 | Tool descriptions conceal canonical memory | **Confirmed verbatim** | Exact live strings in §5.1. |
| 3 | Documentation stale/inconsistent | **Confirmed, understated** | `docs/repository-knowledge.md` is not merely stale — it is **actively wrong** and its instructions **cause** the failure. README is worse than "emphasises older operations": it contains **zero** occurrences of any `memory_*` operation. |
| 4 | No unambiguous controller contract | **Confirmed** | Exhaustive search found no such statement in any repository. |
| 5 | Axon canonical records stale / mutually obsolete | **Confirmed but misdiagnosed** | Not drift-by-neglect. It is a **supersession fork** plus an **abandoned trunk** — a mechanical lifecycle defect that `memory_supersede` permits and `memory_health` cannot see. See §7. |
| 6 | Andiya not bound; `memory_bind_repository` undiscoverable | **Split verdict** | Unbound: **confirmed**. But the action itself is *low-friction* — it auto-derives `project_id`. The real defect is that **the refusal never names it**, and a test that claims to cover this does not. See §8. |
| 7 | Axon doc conflates `refresh_wiki` with memory mutation | **Confirmed, and sharper than stated** | The sentence's **verification clause is satisfiable by `refresh_wiki` alone**, so a diligent controller can fully discharge the instruction without ever touching canonical memory. See §6.1. |
| 8 | Which category is it? | **Combination, ranked** | See §9. |

### 2.1 What the preliminary assessment missed entirely

**(a) One controller environment has its own mandatory `MEMORY.md` system.**

**Scope of this finding: controller/environment-specific external evidence. It is _not_ a Soma surface and not universal.** It is recorded because it explains one observed failure mode on one controller, and because remediation wording must survive it — not because Soma owns or should model it.

Claude Code maintains per-project memory at `C:\Users\arash\.claude\projects\<slug>\memory\`, indexed by a file named `MEMORY.md`:

```text
C:\Users\arash\.claude\projects\D--Github-Soma\memory\MEMORY.md
C:\Users\arash\.claude\projects\D--Github-Axon-modelling\memory\
C:\Users\arash\.claude\projects\D--Github-CodexBridge\memory\
```

A Claude Code controller carries a standing, always-in-context instruction to write memories as files and append a pointer line to `MEMORY.md`. When the owner says "update project memory" **in that environment**, that instruction is already loaded and Soma's canonical workflow is not.

**Limits of this finding.** It does not apply to ChatGPT, Hermes, or any other controller; those exhibit the same reported failure for the reasons in RC1–RC4 alone, which are sufficient without it. Soma cannot detect, control, or depend on the presence of this external system. It must not be added to Soma's surface inventory, modelled in Soma's contract, or treated as a defect Soma owns. Its only remediation consequence is negative and narrow: contract wording must not assume the controller has *no* competing memory instruction (R2).

**(b) Generic repo-scoped knowledge is a distinct fourth surface**, still live and still writable via `remember_decision` / `save_knowledge`. The preliminary assessment folded this into the wiki. It is separate, it has its own on-disk vault (§4), and it is the one the stale documentation actively steers controllers toward.

---

## 3. Exact reproduction evidence

### 3.1 The documented path returns nothing (decisive)

`docs/repository-knowledge.md` — the **only** document `README.md:891` links for "wiki and memory behavior" — instructs:

> `knowledge_query` (`operation: "search"`) — Search both the generated wiki and repository-scoped memory.

Executed live against Axon:

```json
{"ok":true,"repo_name":"axon_modelling","query":"project memory handoff",
 "wiki_hits":[],"memory_hits":[],
 "stale":true,"indexed_head":"e3257c3…","source_generation":188,"indexed_source_generation":173}
```

**`memory_hits: []`.** Simultaneously, the canonical scope for the same repository reports:

```json
{"ok":true,"project_id":"proj_repo_23058ce41311b76c56303da0","repo_name":"axon_modelling",
 "canonical_health":"healthy","canonical_count":18,
 "vault_root":"D:\\SomaMemory\\projects\\proj_repo_23058ce41311b76c56303da0"}
```

A controller that follows the documentation concludes **"this project has no memory"** and creates one. The conclusion is *correct reasoning from the evidence Soma gave it*.

### 3.2 The canonical path is never named where a controller looks

| Surface | `memory_save` | `memory_scope` | `memory_supersede` | `D:\SomaMemory` |
|---|---|---|---|---|
| `knowledge_query` tool description | ✗ | ✗ | ✗ | ✗ |
| `knowledge_action` tool description | ✗ | ✗ | ✗ | ✗ |
| `README.md` (46 KB) | ✗ | ✗ | ✗ | ✗ |
| `AGENTS.md` | ✗ | ✗ | ✗ | ✗ |
| `docs/repository-knowledge.md` | ✗ | ✗ | ✗ | ✗ |

`README.md` contains exactly five occurrences of "memory", all describing the **retired** model:

```text
20:  - repository wiki and scoped decision memory;
52:  +-- repository wiki, scoped memory and source-grounded research
462: - `search` — search generated wiki content and repository-scoped memory.
780:  memory/                      scoped memory and search
891: - docs/repository-knowledge.md — wiki and memory behavior.
```

`AGENTS.md` mentions project memory once, as an unexplained bullet:

```text
137:- project memory
```

### 3.3 Andiya: discovered, wiki-generated, memory-unbound

```json
{"ok":false,"repo_name":"andia_beauty","operation":"memory_scope",
 "error":"canonical memory for 'andia_beauty' requires an exact active ProjectScope binding,
          which could not be resolved: No active repository binding matches 'andia_beauty'"}
```

Yet `D:\Github\andia_beauty\.soma\wiki\generations\` holds seven generations through `20260803T184823846923Z`. The repository is fully known to Soma's discovery and wiki layers and invisible to its memory layer. The error states the problem and **never names `memory_bind_repository`** — the one action that fixes it.

### 3.4 Documentation contradicted by architecture

`docs/repository-knowledge.md` states:

> "All memory records remain in one SQLite database, but retrieval can be scoped by `repo_name` or `project_key`."

`docs/SOMA_CANONICAL_MEMORY_VAULT_DECISION_2026-07-28.md:55-58` states the opposite:

> "Owner-readable Markdown under this root is canonical. […] SQLite catalogs and provider indexes remain **disposable projections outside canonical authority**."

`repository-knowledge.md` also documents "Global memory stores deliberately shared preferences and cross-project policy" — while the accepted architecture **refuses** personal scope at the resolver and `D:\SomaMemory\shared\` and `personal\` are both empty.

---

## 4. Verified current architecture — five surfaces, one canonical

| # | Surface | Location | Authority | Lifecycle | Written by |
|---|---|---|---|---|---|
| 1 | **Canonical project memory** | `D:\SomaMemory\projects\<project_id>\<kind>\*.md` | **Canonical.** Owner-readable Markdown with YAML front-matter (`knowledge_id`, `status`, `supersedes_ids`, `content_sha256`). | Managed: current → superseded/archived/disputed | `memory_save`, `memory_supersede` |
| 2 | Repository handoff document | `<repo>\docs\PROJECT_MEMORY.md` | Repository content. Git-versioned. | Manual, overwrite-in-place | Ordinary file edit / `repo_apply` |
| 3 | Generated wiki cache | `<repo>\.soma\wiki\` | Disposable cache. **Gitignored** in Soma (`.gitignore:16`), untracked in Axon (0 tracked files). | Regenerated; reports `stale` | `refresh_wiki` |
| 4 | Generic repo-scoped knowledge | **`runs/knowledge/projects/<project_id>/vault`** — Markdown, **inside the repository** | Legacy, non-canonical. Takes `project_id` + `repo_name` directly; **no `MemoryScope` authority**. | Ad hoc | `remember_decision`, `save_knowledge` |
| 5 | Controller-environment auto-memory *(external; not a Soma surface)* | e.g. `C:\Users\arash\.claude\projects\<slug>\memory\MEMORY.md` | Outside Soma entirely. Environment-specific — see §2.1(a). | Controller-managed | The controller's own built-in instruction |

Only #1 is canonical project memory. Surfaces #2, #3 and #4 are Soma-owned and each reachable by a plausible reading of "update project memory". Surface #5 is **external** and present only in some controller environments; it is listed for completeness of the failure analysis, not as something Soma owns.

**Correction (Rev 2) — #4 is not "a SQLite store".** Per `docs/EXTERNAL_CONSUMER_MEASUREMENT_1_RESULT_2026-07-29.md:117-126`, generic and canonical writes are two Markdown vaults with **different roots** that **share one catalog**:

| | vault root | scope authority |
|---|---|---|
| generic `save_knowledge` | `runs/knowledge/projects/<pid>/vault` (inside the repo) | none — takes `project_id` + `repo_name` directly |
| canonical `memory_save` | `D:/SomaMemory` (external private vault) | explicit `MemoryScope` |

Shared catalog: `runs/knowledge/knowledge.sqlite3`. Both bind the same identities and the same `vault_path` values. Confirmed live — two such vaults exist on disk:

```text
runs/knowledge/projects/proj_a144f759-1619-4276-9292-28704b6611f4/vault
runs/knowledge/projects/proj_repo_23058ce41311b76c56303da0/vault
```

This makes surface #4 **materially more dangerous than the earlier description implied**: a controller reaching for `save_knowledge` writes real Markdown, to a real vault, under the same identity and possibly the same `vault_path` as the canonical record — but **inside the repository**, outside canonical authority, while appearing in the shared index. It is the closest possible near-miss to doing the right thing, which is precisely why the stale documentation steering controllers to it (§3.1, §6) is severe.

### 4.1 Verified canonical lifecycle

```text
repository discovery (dynamic; creates .soma/wiki, registers repo_name)
  → ProjectScope binding            memory_bind_repository        ← MISSING for andia_beauty
  → scope discovery                 memory_scope(repo_name)       → returns exact {kind,project_id,repo_name}
  → current-record retrieval        memory_search / memory_context
  → save vs supersede selection     ← UNGOVERNED (§7)
  → canonical Markdown mutation     memory_save | memory_supersede
  → catalog/index projection        automatic; disposable
  → verification                    memory_get   (structural)
  → verification                    memory_health (structural only — §7.3)
  ─────────────────────────────────────────────────────────────
  → refresh_wiki                    SEPARATE. Not memory. Not required. Not sufficient.
```

Scope is never inferred. `MemoryScopeInput` requires the exact scope on every call; a call without it is refused (`test_discovery_does_not_become_a_silent_default`). This is correct and should not be relaxed — the fix must be discovery and contract, never inference.

---

## 5. Public-schema and discoverability defects

### 5.1 The two descriptions (live, verbatim)

```text
knowledge_query : "Read-only gateway for repository wiki pages and isolated knowledge search."
knowledge_action: "Write gateway for repository wiki refresh and repository-scoped decisions."
```

Source: `soma/knowledge_tools_integration.py:1361` and `:1821`.

Both are **factually incomplete descriptions of their own operation sets**. `knowledge_query` exposes 18 operations, 6 of them canonical memory; `knowledge_action` exposes 18, 9 of them canonical memory. Neither description contains the words "project memory", and `knowledge_action`'s description names only the two *legacy* write paths.

For a controller doing tool selection on descriptions — which is what tool selection is — canonical project memory **does not exist**.

**And it is worse at enrollment.** Archived connector-enrollment runs show the descriptions truncated to ~55–70 characters in the discovery surface (`runs/20260729T001630Z_executable_profile_40ac0660/result.json:52`):

```text
knowledge_query    Read-only gateway for repository wiki pages and isolate...
knowledge_action   Write gateway for repository wiki refresh and repositor...
```

Both are cut off before their final clause. The only words a controller sees at enrollment are "repository wiki". This constrains the fix — see R3.

### 5.2 There is no per-operation description surface at all

`soma/cf1_gateway_operation_inventory.py` governs response budgets, pagination and projection contracts. It carries no controller-facing semantics. The two docstrings above are the **entire** natural-language public metadata for 36 operations. This is the structural reason discovery fails; adding text to the two docstrings is necessary but not sufficient.

### 5.3 Flat-schema leakage: `current_only`

The flat public schema advertises `current_only: boolean` at top level. Applied to the operation it most obviously belongs to:

```text
knowledge_query(operation="memory_search", scope=…, query=…, current_only=true)
→ ValidationError: memory_search.current_only — Extra inputs are not permitted
```

`current_only` belongs to the **legacy** `search_knowledge` variant (`gateway_models.py:2197`). Canonical `memory_search` spells the same concept inversely as `include_non_authoritative`. A controller reading the public schema is invited to make a call that cannot work, using a flag whose canonical twin is named the opposite way.

### 5.4 Incidental live defect (outside the memory workflow)

```text
repo_query(operation="compact_status", repo_name="andia_beauty")
→ Error calling tool 'repo_query': 'changed_files'
```

Reproduces on `andia_beauty`; `Soma` and `Axon_modelling` both succeed. An unhandled `KeyError` reaching the public gateway. This degrades the *first* step of the onboarding path for the very repository that most needs onboarding. Filed separately in §12.

---

## 6. Documentation contradictions

| Location | Claim | Contradicted by |
|---|---|---|
| `docs/repository-knowledge.md` | "All memory records remain in one SQLite database" | `SOMA_CANONICAL_MEMORY_VAULT_DECISION:55-58` — Markdown is canonical, SQLite is a disposable projection |
| `docs/repository-knowledge.md` | Documents `search` as the memory read path | Live: returns `memory_hits: []` for an 18-record project (§3.1) |
| `docs/repository-knowledge.md` | "Global memory stores deliberately shared preferences" | Personal/shared scope is **refused** at the resolver; both directories empty |
| `docs/repository-knowledge.md` "MCP tools" | Lists 4 operations | Live gateways expose 36; all 15 canonical memory operations absent |
| `README.md:462, 780, 891` | Repo-scoped memory model | Superseded 2026-07-28 |
| `AGENTS.md:137` | "project memory" (bare bullet) | No surface, no operation, no contract |

`docs/repository-knowledge.md` has **no supersession banner** and is linked from the README as current. It is the highest-severity document in the repository.

### 6.1 Axon's instruction — precise defect

`D:\Github\Axon_modelling\docs\PROJECT_MEMORY.md:1003`:

> "After every accepted slice, roadmap transition or material owner decision, update the authoritative repository documents, commit the selected files locally, **refresh Soma's canonical repository wiki/memory**, and **verify that the indexed branch and HEAD are current with no stale marker** before continuing."

Two distinct faults, and the second is the one that bites:

1. `wiki/memory` merges a cache regeneration with a canonical lifecycle mutation.
2. **The verification clause is wiki-only.** `indexed branch`, `HEAD`, and `stale marker` are all `refresh_wiki` outputs (visible in §3.1's response). A controller that runs `refresh_wiki`, sees `stale: false`, and moves on has **fully and verifiably discharged the written instruction** while writing nothing to canonical memory.

This instruction has been in force across 81 commits to `docs/PROJECT_MEMORY.md`. It is a sufficient mechanical explanation for Axon's canonical drift on its own.

---

## 7. Lifecycle defects — confirmed live, and worse than reported

### 7.1 Axon's four `current` records

18 records, `canonical_health: healthy`, `0 malformed / 0 drifted / 0 unadopted`. Four are `current`:

| `knowledge_id` | Path | Updated | Reality |
|---|---|---|---|
| `kn_84c7c3917a97312d663a110d97294ff3` | `handoffs/axon-bus-project-memory-phase4-complete.md` | 08-01 17:18 | **Obsolete.** Says "Phase 4 remains open… begin Phase 4B". Repo is at Research 104. |
| `kn_a627f3d979d8ed78d39976f874f14d9b` | `handoffs/axon-bus-spatiallite-fold0.md` | 08-01 22:22 | **Orphaned fork.** |
| `kn_b2ba7376c39c01db04813833eda44a73` | `handoffs/axon-bus-spatial-lite-fold2.md` | 08-02 10:27 | Real chain head. Still 2 days and dozens of slices behind. |
| *(preference)* | `preferences/fresh-memory-and-resource-efficient-implementation.md` | 08-04 10:04 | Legitimate. Different kind. |

Three mutually-contradictory `handoff` records claim to be current simultaneously. A fresh controller calling `memory_context` receives all three and has **no contract-level basis to choose**.

### 7.2 Root mechanism — a supersession fork

```text
kn_a05d24dc2a899baf477bfd0bf0ba7573  (parent)
   ├── superseded by kn_a627f3d9… → handoffs/axon-bus-spatiallite-fold0.md    status: current    (22:22)
   └── superseded by kn_37cb5efc… → handoffs/axon-bus-spatial-lite-fold0.md   status: superseded (23:44)
                                        └── kn_7fd5d014… fold1 → kn_b2ba7376… fold2 (current)
```

**The same parent was superseded twice.** The chain continued through only one branch; the other is permanently `current` and unreachable by any successor. The near-identical slugs (`spatiallite` vs `spatial-lite`) show the human cause — a re-slug on retry — but the *system* cause is in `soma/knowledge/service.py:121-155`:

```python
old_records = [
    self.catalog.get(note.project_id, knowledge_id)
    for knowledge_id in supersedes_ids
]
```

Predecessors are resolved for **existence only**. There is no check that a predecessor is still `current`. Superseding an already-superseded record is silently permitted, and it silently forks the chain. Separately, the Phase-4 handoff line and the Stage-1 handoff line are two chains that were **never joined**, so `kn_84c7c3…` stays current forever.

`test_supersession_replaces_the_current_answer` covers exactly one linear hop. There is **no test** for superseding an already-superseded record or for two successors sharing a parent. More than one `current` record of the same `kind` is not itself a defect; `kind` does not define a replacement lineage.

### 7.3 Structural health is correct but insufficient for lifecycle verification

`soma/knowledge/service.py:256-296` computes health exclusively from `canonical_count`, `indexed_count`, `malformed_count`, `unadopted_count`, and `drifted_count`. It is a **file-and-catalog integrity check**. Under that accepted contract, Axon is correctly reported as structurally `healthy`: its canonical files are readable, indexed, and free of integrity drift.

The defect is not a false implementation result from `memory_health`. The defect is that Soma exposes **no separate lifecycle-coherence dimension** for forked supersession topology or unresolved continuity, while current documentation and controller guidance allow structural `healthy` to be treated as sufficient verification of overall project-memory correctness.

Consequently, a controller can complete the documented verification step without learning that Axon contains a supersession fork and several unresolved current handoffs. This is a **missing dimension plus completion-contract gap**. Structural health must retain its existing meaning; lifecycle coherence and repository freshness require separately designed signals.

---

## 8. Onboarding defects

`memory_bind_repository` is **better than the preliminary assessment assumes**. Per `MEMORY_REPOSITORY_ONBOARDING_1_RESULT_2026-08-01.md` and `knowledge_tools_integration.py:1539-1640`, it derives stable project/resource identity from the canonical repository identity hash, is idempotent, returns an existing binding without mutation, and returns the exact `scope` for subsequent calls. The controller supplies only `repo_name`.

**The defect is entirely in discovery, not in ergonomics:**

1. The refusal (§3.3) states the problem and omits the remedy.
2. `test_unknown_repository_is_refused_with_an_actionable_reason` **does not test actionability**:
   ```python
   refused = query(mcp, {"operation": "memory_scope", "repo_name": "not-a-repo"})
   assert refused["ok"] is False
   assert refused["error"]          # ← only asserts the string is non-empty
   ```
   The test name asserts a property the assertions do not check. This is how the gap survived review.
3. No document anywhere describes an onboarding path for a new repository.
4. `repo_query compact_status` — the natural first probe — crashes on `andia_beauty` (§5.4).

---

## 9. Root causes, ranked

| Rank | Root cause | Category | Evidence |
|---|---|---|---|
| **RC1** | The documented memory read path returns empty for a healthy 18-record project | Architectural contract + stale doc | §3.1 |
| **RC2** | `memory_health` certifies `healthy` while canonical memory is forked, contradictory and stale — a **false verification signal** | Architectural contract | §7.3 |
| **RC3** | Five surfaces named "memory"; no contract ranks them or forbids substitution | Architectural contract | §4, §2.1 |
| **RC4** | Public tool descriptions omit canonical memory entirely; no per-operation description surface exists | Weak discovery metadata | §5.1, §5.2 |
| **RC5** | *(aggravating, not causal — external)* In the Claude Code environment specifically, the controller carries a standing built-in instruction to write `MEMORY.md`, while Soma's workflow is not in context by default | Controller-environment namespace collision. **External to Soma**; RC1–RC4 are sufficient to explain the failure without it | §2.1(a) |
| **RC6** | `memory_supersede` performs no lifecycle validation on predecessors → silent forks | Lifecycle defect | §7.2 |
| **RC7** | Binding refusal names the problem, never the remedy; the test that should catch this asserts nothing | Missing onboarding | §8 |
| **RC8** | Axon's own instruction merges wiki refresh with memory mutation and its verification clause is wiki-only | Ambiguous project instruction | §6.1 |
| RC9 | `docs/repository-knowledge.md` is presented as current while contradicting the accepted architecture | Stale documentation | §6 |
| RC10 | Flat-schema leakage (`current_only`) and inverse-polarity twin flags | Public-schema defect | §5.3 |

**Not root causes.** *Controller misuse*: a controller following the documentation exactly still fails; the fault is upstream. *Owner terminology*: "update Soma project memory" is unambiguous English — it names the system and the surface. The ambiguity is Soma's, not the owner's.

---

## 10. Severity and reliability classification

| ID | Finding | Severity | Class |
|---|---|---|---|
| **M-01** | *(reclassified Rev 2)* **No dimension exists** that reports lifecycle incoherence, while documentation and controller expectation treat structural `memory_health: healthy` as sufficient verification of a memory update | **Critical** | Missing dimension + verification-contract gap. **Not** a defect in `memory_health`, which correctly reports structural health |
| **M-02** | Documented memory read path returns `memory_hits: []` for a live project | **Critical** | Contract defect, causes the reported bug |
| **M-03** | No controller contract; repository-file substitution never forbidden | **High** | Contract gap |
| **M-04** | `memory_supersede` permits forks; Axon has one live | **High** | Lifecycle defect + live data defect |
| **M-05** | Tool descriptions conceal 15 canonical operations | **High** | Discoverability |
| **M-06** | `repository-knowledge.md` actively wrong, linked as current | **High** | Stale documentation |
| **M-07** | Axon: 3 contradictory `current` handoffs, 2-day drift | **High** | Live data defect |
| **M-08** | Andiya unbound; refusal omits remedy; test asserts nothing | **Medium** | Onboarding |
| **M-09** | Host `MEMORY.md` collision | **Medium** | Namespace, external |
| **M-10** | `current_only` flat-schema leakage / inverse twin | **Low** | Schema hygiene |
| **M-11** | `repo_query compact_status` KeyError on `andia_beauty` | **Medium** | Unhandled exception at public gateway |

**Not tracked today.** `docs/RELIABILITY_1_GATE_AND_BUG_LEDGER_2026-08-01.md` contains **no entry** matching "project memory", "PROJECT_MEMORY", "MEMORY.md", or "memory surface". This class of failure has no owner in the reliability process — which is itself a finding.

---

## 11. Do existing canonical records require repair?

**Yes — Axon only. Repair by supersession, never by deletion or edit.**

| Record | Disposition |
|---|---|
| `kn_84c7c3917a97312d663a110d97294ff3` (phase4-complete) | Must **not** remain `current`. Abandoned trunk. |
| `kn_a627f3d979d8ed78d39976f874f14d9b` (spatiallite-fold0) | Must **not** remain `current`. Forked orphan. |
| `kn_b2ba7376c39c01db04813833eda44a73` (spatial-lite-fold2) | Genuine head; superseded by the repair record. |
| `preferences/fresh-memory-…` | **No action.** Different kind, legitimately current. |

**Recommended repair:** one `memory_supersede` writing a current Axon handoff reflecting real state through Research 104, with `supersedes_ids` listing **all three** stale handoff ids. This collapses trunk and fork in one operation and leaves an auditable record of the repair. Requires owner authorisation — it is a live canonical mutation on a real project.

Soma's own scope (`proj_a144f759…`, 19 records) and the other five projects show no comparable defect. **Andiya has no records to repair** — it has no binding.

---

## 12. Recommended remediation — project-neutral

Ordered by (severity × independence). Every item is project-neutral; none hard-codes Axon, Andiya, or Soma.

### R1 — Expose lifecycle coherence as a *separate dimension* (M-01, RC2)

**Corrected in Rev 2. The earlier version of R1 proposed redefining `memory_health` to include lineage, record age, and repository commit lag. That was wrong on three counts and is withdrawn.**

**R1.1 — Do not redefine canonical vault health.**
`memory_health` is, by accepted contract, **structural file/catalog health**: `canonical_count`, `indexed_count`, `malformed`, `unadopted`, `drifted` (`soma/knowledge/service.py:256-296`). Folding lineage or freshness into it would silently change the meaning of an accepted public signal and make an existing `healthy` answer mean something different than it did. Structural health stays exactly as it is.

**M-01 is reclassified accordingly.** The defect is **not** "`memory_health` is broken" — it correctly reports structural health, and Axon *is* structurally healthy. The defect is that **no dimension exists that would report lifecycle incoherence**, combined with documentation and controller expectation treating a structural `healthy` as sufficient verification of a memory update. It is a **missing dimension plus a verification-contract gap**, not a wrong implementation. Severity is retained (see §10) because the consequence — false assurance — is unchanged; ownership moves from "fix health" to "add a dimension and fix what completion must verify."

**R1.2 — Lineage coherence requires a missing contract, and a decision before any check.**

The only defect this audit **proved** mechanically is the **supersession fork** (§7.2): `kn_a05d24dc…` appears in the `supersedes_ids` of two distinct records. That is contract-free and objectively wrong under any lineage model — a record cannot be replaced twice — and is safe to detect as `forked_chains`.

**`multiple_current_by_kind` is withdrawn as a global invariant.** Multiple concurrent `fact`, `decision`, `lesson`, and `preference` records are legitimate, and so are independent parallel handoffs. `kind` does **not** establish a single logical replacement lineage.

This is demonstrable, not theoretical. Soma's own scope (`proj_a144f759…`, `canonical_health: healthy`) contains:

```text
current  fact      × 3      current  decision  × 4      current  lesson  × 2
current  handoff   × 1      superseded handoff × 8
```

The proposed check would have flagged **the healthiest scope in the vault** as incoherent, on nine legitimate records. Axon differs not because it has several current handoffs, but because two of them are a **fork** and an **abandoned lineage** — a property of chain topology, not of `kind`.

**The missing contract.** Soma has no notion of a *lineage* (or continuity series): a declared set of records that constitute one replacement chain, within which exactly one record is current. `supersedes_ids` expresses individual edges; nothing declares that two records belong to the same series, and nothing distinguishes "a new parallel record" from "a continuation that failed to supersede its predecessor." Without that, "too many current records" is undecidable.

**Required before implementation:** a separate owner-approved architecture decision defining lineage/continuity — whether it is explicit (a declared `lineage_id` or series key), inferred from an unbroken `supersedes_ids` chain, or scoped by an explicit `supersedes`-or-`parallel` intent on write; and what the one-current-per-lineage rule is. **No lineage-based check may be implemented before that decision exists.** `forked_chains` may proceed independently of it.

**R1.3 — Freshness is an observation, never an automatic failure.**
`current_record_age_days` and `repository_commits_since_newest_current` must be reported as **observations**, or at most as warnings under an explicit owner-set policy threshold. They must not, on their own, move any status to a failing value. A project can be legitimately quiet; an old current record is not a defect, and a canonical store must not degrade itself because a repository moved. Freshness belongs in a **separate dimension** from both structural health and lineage coherence.

**Net R1 scope after correction:**

| Item | Status |
|---|---|
| `forked_chains` detection | Proceed — contract-free, proven defect |
| Lineage / one-current-per-series | **Blocked** on a separate architecture decision |
| Freshness observations | Report-only; no automatic failure; separate dimension |
| Redefining `memory_health` | **Withdrawn** |

Rationale is unchanged for the part that survives: fork detection converts one silent, proven failure into a loud one for every project, retroactively, without controller cooperation. It would have caught Axon's fork on 2026-08-01. The broader coherence claim now correctly depends on a contract that does not yet exist.

### R2 — Publish the contract (M-03, RC3, RC5)

A single normative document, `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md`, stating in the owner's own words:

> When the owner says **project memory**, **Soma project memory**, or **update project memory**, the canonical surface is `D:\SomaMemory\projects\<project_id>\`, mutated **only** through `memory_save` / `memory_supersede`.
>
> Creating or updating `MEMORY.md`, `docs/PROJECT_MEMORY.md`, `.soma/wiki/`, or any repository file **does not satisfy that request**. Neither does `refresh_wiki`, `remember_decision`, or `save_knowledge`.
>
> A repository handoff document may be updated **in addition**, never **instead**.
>
> `refresh_wiki` is a separate operation. It is neither required by nor sufficient for a memory update.

It must **name the host-controller collision explicitly** (RC5) — that a controller's own built-in `MEMORY.md` memory is a different system and does not satisfy the request — or Claude Code sessions will keep failing.

Then reference it from `README.md`, `AGENTS.md`, and both gateway descriptions.

**Correction — the `soma-operator` skill is not a viable distribution channel.** An earlier draft of this recommendation proposed carrying the contract in the skill. Verification shows that would not work:

- **It is a harness-injected inline skill**, registered as `pluginUsage: "soma-agent@inline"`. It is **not** repository-owned, not marketplace-installed, and not a locally editable `SKILL.md`. It is therefore not an artifact the owner can edit, version, or ship a contract in. *This is a settled disposition, not an open question — no filesystem source is expected to exist, and neither the audit nor its implementation depends on locating one.*
- Consistent with that: `~/.claude/plugins/installed_plugins.json` lists only `scroll-world@scroll-world`; `~/.claude/plugins/cache/` contains only `scroll-world`; `~/.claude/skills/`, `D:\Github\Soma\.claude\skills\`, and `.agents\` are absent or empty.
- **Usage is decisive.** Recorded telemetry:

  ```text
  pluginUsage  soma-agent@inline           usageCount: 137   last 2026-08-04 16:46 UTC
  skillUsage   soma-agent:soma-operator    usageCount:   1   last 2026-07-27 19:25 UTC
  ```

  The Soma tools have been used **137 times**; the skill has been invoked **once, eight days ago**. In practice controllers reach the gateways with the skill **not loaded** in ~99% of sessions.
- Its own description — *"Use Soma as the owner's execution runtime for repository work, durable tasks, host operations, Hermes capabilities, and evidence retrieval"* — **does not mention project memory**, so it would not trigger on "update project memory" even when available.

This **strengthens RC4 and RC5** rather than mitigating them: the one context-loaded surface that could have carried the contract omits memory entirely and is almost never active. The contract must therefore live where the controller *always* looks — the **tool descriptions** (R3) and the repository documents — never in an optional skill.

### R3 — Fix the public descriptions (M-05, RC4) — **front-load, do not append**

**Constraint discovered in archived connector-enrollment evidence.** Descriptions are **truncated to ~55–70 characters** in the connector discovery/enrollment surface. `runs/20260729T001630Z_executable_profile_40ac0660/result.json:52` and `runs/20260729T004727Z_executable_profile_c2dbf30d/result.json:52` capture what a controller actually sees when enrolling the Soma server:

```text
knowledge_query    Read-only gateway for repository wiki pages and isolate...
knowledge_action   Write gateway for repository wiki refresh and repositor...
```

Both are cut off **before their final clause**. The words a controller sees at enrollment are literally "repository wiki pages" and "repository wiki refresh".

**Consequence: appending canonical-memory text to the existing descriptions would be truncated away and achieve nothing in this surface.** The canonical-memory signal must occupy the **first ~50 characters**:

```text
knowledge_query : "Canonical Soma project memory (memory_scope, memory_search, memory_get,
                   memory_health, memory_context) plus read-only repository wiki pages and
                   isolated knowledge search. For 'project memory', call memory_scope first."

knowledge_action: "Canonical Soma project memory writes (memory_save, memory_supersede,
                   memory_bind_repository, …) plus repository wiki refresh and legacy
                   repository-scoped decisions. 'Update project memory' means
                   memory_save/memory_supersede — never a repository file, never refresh_wiki."
```

Truncated at 55 characters these now read `Canonical Soma project memory (memory_scope, memory_se…` and `Canonical Soma project memory writes (memory_save, mem…` — the signal survives.

**Acceptance for R3 must be measured on a truncated rendering**, not on the full string. Add a test asserting `description[:55]` contains `"project memory"` for both gateways.

Note: a description/metadata-only change does not change `public_schema_hash`, which tracks the effective public input contract. It can still require server activation and a ChatGPT connector Refresh because the client caches advertised descriptor metadata; the future additive `public_descriptor_hash` is intended to identify exact served descriptor changes (§14).

**Single source confirmed.** A full-tree search (including `runs/`, `.venv`, and all cached artifacts) found the description strings defined in exactly one place — `soma/knowledge_tools_integration.py:1361` and `:1821`. There is **no duplicate or stale description authority**; every other occurrence is a captured run transcript. The fix has one site per gateway.

### R4 — Retire the wrong document (M-06, RC9)

`docs/repository-knowledge.md`: add a supersession banner at the top; correct the SQLite-authority and global-memory claims; replace the four-operation MCP list with the canonical lifecycle; link R2. Correct `README.md:20, 52, 462, 780, 891` and expand `AGENTS.md:137`.

### R5 — Validate supersession (M-04, RC6)

In `KnowledgeService.supersede`, refuse when a predecessor's `effective_status` is not `current`, with an error naming the successor that already superseded it. This makes the Axon fork **unreproducible** rather than merely repaired.

**Corrected in Rev 2 — no public `force` escape.** The earlier version proposed a `force` flag for deliberate chain repair. That is withdrawn: a broad public escape re-admits exactly the state R5 exists to prevent, and would make fork creation a one-parameter operation rather than an impossible one. A repair path that can recreate the defect is not a repair path.

Chain repair is a **governed exception**, and needs its own contract before it has an interface. Until that exists, R5 ships as a **plain refusal with no bypass**. If a legitimate repair need arises (as it does for Axon, §11), it is handled as an explicitly authorised operation under owner approval — not by a flag any controller can set. Defining that repair contract is a **separate decision**, and is a prerequisite for any future bypass, not a detail of R5.

### R6 — Make refusals actionable (M-08, RC7)

Binding refusal becomes:

```text
canonical memory for 'andia_beauty' requires an exact active ProjectScope binding.
No active repository binding matches 'andia_beauty'.
Remedy: knowledge_action(action="memory_bind_repository", repo_name="andia_beauty")
```

For every refusal that has a supported remedial action, **state the problem and name the exact operation that resolves it**. Refusals without an authorised remedy must remain explicit rather than inventing one.

### R6b — Auto-bind discovered repositories (owner direction, 2026-08-04)

**Owner direction:** every Git-initialised repository under `D:\Github` should be bound automatically rather than requiring an explicit `memory_bind_repository` call.

**⛔ CORRECTED IN REV 2 — the previous version of R6b was wrong and is withdrawn.**

The earlier draft asserted that auto-binding "does not violate the architecture," reasoning that the invariant only forbids **scope inference at call time**. That reasoning was incomplete and the conclusion was false. Auto-binding from `memory_scope` **directly contradicts the accepted architecture**:

> "preserves read-only discovery: `memory_scope` still **never creates authority silently**"
> — `docs/MEMORY_REPOSITORY_ONBOARDING_1_RESULT_2026-08-01.md:29`

> "**discovery returns a scope, it does not become one.** […] Discovery stays a separate, visible step."
> — `docs/MEMORY_CONTROLLER_ERGONOMICS_1_RESULT_2026-07-29.md`

These are explicit, and they are about **exactly** the proposed change: `memory_scope` creating durable ProjectScope authority. The accepted design deliberately separates a read-only discovery operation from `memory_bind_repository`, the **write action** that creates authority. `MEMORY_REPOSITORY_ONBOARDING_1` exists precisely to provide that write path *without* weakening discovery — auto-binding would undo its central design property.

Three independent reasons the earlier reasoning fails:

1. **It contradicts a stated invariant**, not merely an inferred one. The audit quoted `MEMORY_REPOSITORY_ONBOARDING_1_RESULT` elsewhere and failed to apply line 29.
2. **It would make a declared read-only tool perform durable writes.** `knowledge_query` is registered with `READ_ONLY_ANNOTATIONS` (`knowledge_tools_integration.py:1359`). Creating a ProjectScope binding inside it makes that annotation false — a public-contract violation independent of the memory architecture, and one that misleads every consumer relying on the annotation.
3. **"Creates the exact identity rather than inferring it" is not a defence.** The invariant governs *whether a read operation may create authority at all*, not the determinism of the identity it creates.

**Disposition:** auto-binding may be proposed **only as a new owner-approved architecture change** that explicitly amends `MEMORY_REPOSITORY_ONBOARDING_1_RESULT` and `MEMORY_CONTROLLER_ERGONOMICS_1_RESULT`. It **must not** be presented as compatible with, or an extension of, the accepted architecture. It is **not** part of the approved remediation direction and is not scheduled in §15.

**If the owner chooses to pursue it later, the decision must address at minimum:**

- which operation may create a binding, given that `memory_scope` may not (a distinct write operation, or an explicit opt-in parameter, is the likely shape);
- how the `READ_ONLY_ANNOTATIONS` contract is preserved;
- the eager-vs-lazy question and exclusions (below), which remain valid inputs;
- the sequencing hazard (below), which remains valid and is arguably the strongest argument for deferral.

**Retained observation for any future decision:** eager scanning is the wrong shape. Twenty-one of twenty-five directories under `D:\Github` are Git repositories, at least four are disposable reliability artifacts, and four of the seven existing project scopes in `D:\SomaMemory` are reliability-test canaries. Because the owner opens this vault directly in Obsidian, any future binding-creation policy must explicitly handle exclusions for probes, vendored trees, and `SOMA_REPO_EXCLUDES` rather than binding every discovered directory.

*The sequencing hazard is real and argues for deferral.* Today the binding refusal is the **only** signal that anything is wrong. Auto-binding removes it: `memory_scope` would start succeeding against an empty vault. A controller that never learned canonical memory exists (RC1–RC4) would still write a repository file — and nothing anywhere would error. The failure becomes fully silent. Any future auto-bind decision must therefore land **after** R2 (contract) and R3 (descriptions), never before.

**R6 is not superseded.** The earlier draft claimed R6b supersedes R6 for the bound case. With R6b withdrawn, **R6 stands in full**: actionable refusal naming `memory_bind_repository` is the approved remedy for the unbound case, and it is the correct one — it preserves read-only discovery exactly as the architecture requires while removing the discoverability defect that actually causes the reported failure. R6 delivers most of R6b's practical benefit at none of its architectural cost.

### R6c — Legacy `search` must not mislead when canonical memory exists (M-02, RC1)

**Stated as an outcome, not a mechanism.** The defect (§3.1) is that `knowledge_query(operation="search")` returns a bare `memory_hits: []` for a repository holding 18 canonical records, and a controller correctly reads that as "no project memory exists."

**Required outcome:** legacy `search` must not return a result that a reasonable controller would read as "this project has no memory" when canonical memory exists for that repository.

**Explicitly not prescribed:** routing legacy search into canonical memory is **one** candidate, not the assumed solution, and it carries its own risks — it would blur an authority boundary the architecture deliberately separates, and could let a generic-surface caller receive canonical records without a `MemoryScope`.

Other candidates that satisfy the same outcome without that risk:

- return an explicit **pointer** rather than results — a field indicating canonical memory exists for this repository and naming `memory_scope`, leaving retrieval to the canonical operations;
- **deprecate** `search` for memory, returning a refusal or deprecation notice that names the canonical path;
- keep `search` wiki-only and rename/redocument it so it no longer claims to cover memory at all (which is what `repository-knowledge.md` currently promises and the implementation does not deliver).

The last is arguably closest to the architecture's intent, since the "repository-scoped memory" this operation was built for is the retired model. **Selecting among these is a design decision to be made during implementation of R4**, informed by whether legacy `search` is retained at all. The acceptance criterion is the outcome above, not any particular mechanism.

### R7 — Correct the Axon instruction (RC8)

Split `PROJECT_MEMORY.md:1003` into two numbered steps with **separate verification clauses**. A canonical-memory mutation is verified by retrieving the exact written record with `memory_get` and confirming structural vault/catalog integrity with `memory_health`; that verification does **not** resolve lineage ambiguity or prove repository freshness. Wiki refresh is verified separately through indexed branch, HEAD, generation, and stale state. Project-neutral wording belongs in R2 so other repositories inherit it.

### R8 — Schema hygiene (M-10)

Either accept `current_only` on `memory_search` as an alias, or remove it from the flat public schema surface for canonical operations. Do not leave an advertised flag that cannot be used where it is most obviously meant.

### R9 — Repair Axon's records (M-07) — *owner authorisation required*

Per §11.

### R10 — `repo_query` KeyError (M-11)

Fix the unhandled `'changed_files'` KeyError; add a regression case for a repository with the shape of `andia_beauty`.

---

## 13. Test changes required

| Test | Asserts |
|---|---|
| `test_forked_supersession_chain_is_reported` | Two successors of one parent → both ids in `forked_chains` **in the new lineage dimension**; structural `memory_health` is unchanged |
| `test_structural_health_semantics_are_unchanged` | A structurally sound but lineage-forked scope still reports structural `healthy` — pins R1.1 against silent redefinition |
| `test_concurrent_current_records_of_one_kind_are_not_a_defect` | 3 current `fact` + 4 current `decision` + 2 current `lesson` (the real Soma scope shape) report **no** coherence defect — pins R1.2 against the withdrawn invariant |
| `test_freshness_is_reported_without_failing` | Old current record + advanced repository → freshness observation present, no status moved to a failing value (R1.3) |
| `test_supersede_refuses_an_already_superseded_predecessor` | Second supersede of the same parent is refused and names the existing successor |
| `test_supersede_has_no_public_bypass` | No public parameter permits superseding a non-current predecessor — pins R5 against reintroducing forks |
| `test_unknown_repository_refusal_names_the_binding_action` | **Replaces** the current test — asserts `"memory_bind_repository" in error` |
| `test_new_repository_onboarding_end_to_end` | discover → bind → scope → save → get → health, from zero |
| `test_gateway_descriptions_name_canonical_memory` | Both docstrings contain `memory_save` / `memory_scope` — pins RC4 against regression |
| `test_truncated_gateway_descriptions_still_name_project_memory` | `description[:55]` contains `"project memory"` for both gateways — pins the connector-truncation constraint (§R3) |
| `test_legacy_search_does_not_imply_absent_memory` | R6c — `search` on a repo with canonical records does not return a result readable as "no memory exists". Asserts the **outcome**; mechanism-agnostic |
| `test_memory_scope_creates_no_authority` | Pins the read-only discovery invariant: `memory_scope` against an unbound repository leaves **no** ProjectScope binding and **no** vault directory behind |

`test_legacy_search_does_not_imply_absent_memory` and `test_gateway_descriptions_name_canonical_memory` are the two regressions that would have prevented this audit's primary finding.

`test_memory_scope_creates_no_authority` is the one that would have caught the withdrawn R6b proposal before it reached the owner, and should exist regardless of whether auto-binding is ever revisited.

---

## 14. Migration, compatibility, and activation

**Migration:** the recommended documentation and discovery corrections require no stored-data migration. Existing canonical records already carry the fields needed for later analysis, but no lineage/coherence migration or status change is authorised by this audit. Any future Axon repair would be a separately authorised canonical mutation, not part of these corrections.

**Compatibility:**
- R2 and R4 are Soma documentation-only changes. R7 is a separate Axon repository-document correction and must follow that repository's own preflight and ownership rules.
- R3 changes published tool discovery metadata, not operation input or output shapes. Its actual effect on `public_schema_hash`, operation hashes, and discovery-cache generation must be measured after activation rather than assumed.
- R6 changes a runtime refusal message, not the public input schema. It should remain shape-compatible while becoming actionable.
- R5 would be behaviour-changing because a second supersession that currently succeeds would begin failing. R5 and any governed repair path remain unapproved; no public bypass is recommended.
- Structural `memory_health` semantics remain unchanged. Any future lifecycle-coherence surface is additive in concept but has no approved schema or compatibility contract yet.

**Activation:** documentation-only Soma changes require no restart. R3 requires a Soma process restart and connector refresh before a fresh controller can observe the new tool descriptions. R6 requires the updated server process but does not inherently require connector refresh because its public schema is unchanged. When runtime stages are eventually approved, record the observed build, public discovery identities, and fresh-session behaviour rather than assuming which hashes move. Current live build for comparison: `f55d37e7d65b… / 84d0af8b66d7…`.

---

## 15. Revised staged plan (Rev 3)

### 15.1 Recommended immediate direction pending explicit execution approval

The audit recommends **contract, documentation, discovery descriptions, and actionable refusal behaviour**. Correcting this audit file does not itself authorise those implementation stages.

| Stage | Contents | Gate | Restart |
|---|---|---|---|
| **A1 — Soma contract & documentation** | R2 (normative contract) and R4 (correct or supersession-banner `docs/repository-knowledge.md`; correct `README.md` and `AGENTS.md`) | Contract states the four Soma-owned surfaces, canonical operations, and what does **not** satisfy a memory request; stale claims corrected or explicitly historical; only Soma documentation touched | No |
| **A2 — Axon instruction correction** | R7 in `D:\Github\Axon_modelling\docs\PROJECT_MEMORY.md` only | Before editing: verify Axon branch/HEAD, worktree, active runs, locks, and concurrent ownership. If any ownership is ambiguous, leave A2 to the Axon workflow. Canonical-memory and wiki steps receive separate, accurately bounded verification language | No |
| **B — Discovery descriptions** | R3 plus `test_gateway_descriptions_name_canonical_memory` and `test_truncated_gateway_descriptions_still_name_project_memory` | Both descriptions name canonical project memory within the first ~55 characters; actual public discovery identity changes measured | Yes + connector refresh — separate approval required |
| **C — Actionable refusal** | R6 plus an assertion that the refusal names `memory_bind_repository`; add `test_memory_scope_creates_no_authority` | Refusal names the remedy; discovery remains read-only and creates no authority; focused and full validation green | Yes; connector refresh only if published discovery metadata also changes — separate approval required |

A1 is the lowest-risk implementation stage. A2 is intentionally independent so an active scientific repository is never edited as a side effect of Soma documentation work.

### 15.2 Withheld pending explicit execution approval or a separate architecture decision

| Item | Why held |
|---|---|
| **Auto-binding** (withdrawn R6b) | Contradicts accepted architecture (§R6b). Requires a **new architecture decision** amending `MEMORY_REPOSITORY_ONBOARDING_1_RESULT` and `MEMORY_CONTROLLER_ERGONOMICS_1_RESULT` |
| **Any `memory_health` status change** | R1.1 — structural health semantics must not be redefined |
| **Lineage / coherence checks** | R1.2 — blocked on a **lineage/continuity architecture decision** that does not yet exist. `forked_chains` is contract-free but still ships only under approval |
| **Freshness signals** | R1.3 — observation-only design not yet approved |
| **Lifecycle changes** (R5 supersede refusal) | Behaviour-changing; and the governed **repair contract** it implies is a separate decision |
| **Axon record repair** (R9) | Live canonical mutation on a real project |
| **Andiya binding** | Live authority creation |
| **Restart / connector refresh** | B requires both; C requires the updated server and needs connector refresh only if discovery metadata changes. Approval is per event, not implied by approving source changes |
| **Push** | Not authorised |
| **R6c** (legacy `search`) | Outcome agreed; **mechanism undecided** (§R6c). Requires a design decision during R4 |
| R8 (schema hygiene), R10 (`repo_query` KeyError) | Not in the approved direction; hold or handle under the reliability ledger |

### 15.3 Acceptance criteria for the recommended stages

Narrower than the earlier programme-wide criterion, because the recommended direction deliberately excludes lifecycle, health, binding, and live-record repair changes.

A genuinely fresh controller session, given only "update Soma project memory" for a **bound** repository and no other briefing, must:

1. reach `memory_scope` from the tool descriptions alone — including when those descriptions are **truncated** by the connector;
2. be told, **by name**, to call `memory_bind_repository` if the repository is unbound;
3. find a published contract stating that a repository file, the generated wiki, generic `save_knowledge`, and `refresh_wiki` **do not satisfy** the request;
4. treat `refresh_wiki` as separate, optional, and non-substitutive;
5. not create `MEMORY.md` or `docs/PROJECT_MEMORY.md` as a substitute.

**Out of scope for this acceptance** — and deliberately so: unambiguous current-record retrieval and `memory_supersede`-versus-`memory_save` selection both depend on a lineage contract that does not exist. **The recommended stages fix discovery and instructions, not lifecycle.** After A1–C, a controller will know where canonical memory is and how to reach it; it may still face several current handoffs on Axon with no contractual basis to choose between them. That residual gap remains open under M-04/M-07.

When A1–C are eventually implemented and activated, test on both ChatGPT and Claude Code. Claude Code is the harder audited environment for the reasons in §2.1(a), but its controller-local memory system must not be treated as universal.

---

## 16. Scope of this audit

Read-only. Two live write-capable gateways were exercised **only** through read operations (`memory_scope`, `memory_health`, `memory_search`, `search`, `repo_query`, `system_query`). No canonical record, binding, wiki, schema, or source file was mutated. This report is the only file created, and it is **uncommitted**.

Not covered: the research authority (`soma.research.v1`), personal/shared scope (refused by design), semantic retrieval (disabled by design), and the four non-Axon/non-Soma project scopes beyond confirming they show no comparable lifecycle defect.

---

## 17. Revision 2 — corrections under owner review (2026-08-04)

Ten corrections were directed by the owner after Rev 1. Three corrected **factual or reasoning errors** in the audit; the rest tightened claims that overreached. Recorded here because an audit used as implementation authority must show where it was wrong.

| # | Correction | Class | Where |
|---|---|---|---|
| 1 | Removed "unbriefed by the preliminary assessment" — the prompt **supplied** eight findings to verify or refute | **Factual error** | Header |
| 2 | Mutation statement qualified: no **pre-existing** state changed; this report was itself created | Accuracy | Header, §16 |
| 3 | `multiple_current_by_kind` **withdrawn** as a global invariant; missing lineage/continuity contract identified; check blocked on a separate architecture decision | **Reasoning error** | R1.2 |
| 4 | `memory_health` **not** redefined to include age, commit lag, or continuity; separate dimensions proposed; **M-01 reclassified** from "health is broken" to "missing dimension + verification-contract gap" | **Reasoning error** | R1.1, §10 |
| 5 | Freshness signals are observations or policy warnings, never automatic failures | Overreach | R1.3 |
| 6 | **R6b auto-binding withdrawn.** It contradicts `MEMORY_REPOSITORY_ONBOARDING_1_RESULT:29`, `MEMORY_CONTROLLER_ERGONOMICS_1_RESULT`, and PLANS.md, and would make a `READ_ONLY_ANNOTATIONS` tool perform durable writes. Proposable only as a new owner-approved architecture change. R6 is **not** superseded | **Factual error** | R6b, §15.2 |
| 7 | Generic knowledge surface corrected: `runs/knowledge/projects/<pid>/vault` (Markdown, **inside the repo**) sharing catalog `runs/knowledge/knowledge.sqlite3` — not "a SQLite store" | **Factual error** | §4 |
| 8 | Public `force` bypass for supersession **removed**; chain repair requires a separately governed repair contract | Overreach | R5 |
| 9 | Legacy-search recommendation restated in **outcome** terms; routing into canonical memory is one candidate, not the assumed solution | Overreach | R6c |
| 10 | Claude Code `MEMORY.md` collision marked **controller/environment-specific external evidence**, not a universal Soma surface | Scope | §2.1(a), §4 |

### What Rev 2 does not change

The primary finding is untouched and was not challenged: the documented memory read path returns `memory_hits: []` for a repository holding 18 healthy canonical records (§3.1), while no surface a controller consults names canonical memory (§3.2). The supersession fork (§7.2) remains proven and contract-free. The connector truncation constraint (§5.1, R3) is unaffected.

### Standing of this document

Rev 3 is suitable as **planning and audit authority**, not as execution approval. Section 15.1 defines the recommended bounded stages and their gates; implementation, cross-repository edits, restart, connector refresh, canonical mutation, binding, commit, and push each remain subject to their normal explicit authority. Every other recommendation is either blocked on a named architecture decision or withheld pending separate approval (§15.2). Where a recommendation depends on a contract that does not yet exist, this document says so rather than assuming one.

---

## 18. Revision 3 — internal-consistency corrections (2026-08-04)

Rev 3 removes stale Rev 1 language that survived the substantive Rev 2 correction and tightens execution boundaries:

1. §7.3 now distinguishes correct structural `memory_health` from the missing lifecycle-coherence dimension and completion-contract gap.
2. §14 no longer claims an approved `incoherent` status, R1 output fields, or a public supersession `force` escape.
3. Activation requirements distinguish discovery-description changes from runtime refusal-message changes and require observed identity evidence rather than assumed hash movement.
4. Stage A is split into **A1 Soma documentation** and **A2 Axon instruction correction**, with independent Axon preflight and ownership checks.
5. The plan is explicitly recommended pending execution approval; the audit no longer manufactures owner authorisation.
6. The duplicated eager-scan argument is consolidated.
7. Refusal guidance names supported remedies only, and R7 no longer presents structural health as lineage verification.

This revision changes only the audit report. It does not implement A1, A2, B, or C.
