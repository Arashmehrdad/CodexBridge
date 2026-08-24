# RM0 — Hybrid Research Map Authority / Preflight Acceptance

Date: 2026-08-24  
Status: **ACCEPTED**  
Implementation authority: `docs/SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md`  
Research authority: Iterations 09–12 under `docs/soma-knowledge-carry-forward-research/`  

## 1. Purpose

RM0 is the mandatory read-only implementation preflight for the Soma Hybrid Research Map programme.

It verifies that the canonical implementation plan still matches the live repository before any production source implementation begins.

RM0 authorizes no Graphiti installation, no research-map source implementation, no historical sidecar backfill, and no legacy research-platform repair.

## 2. Live repository state

Authoritative preflight:

```text
Soma run_query(operation=preflight)
branch: rollback/pre-core-hardening-20260823
HEAD: 7e7450e08331aeed744867be955feb42149b18f4
locks: none
running runs: none
launch-pending runs: none
```

One unrelated old durable run from 2026-08-15 remains queued:

```text
20260815T222341Z_executable_profile_b78476ae
```

It owns no repository lock and is outside this programme. RM0 leaves it untouched.

## 3. Protected existing worktree

The worktree is intentionally not clean.

Preserved owner/research state:

```text
AGENTS.md                                  modified, pre-existing intended work
Iterations 01–12                          untracked durable research records
SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md
                                           untracked canonical plan
```

RM0 performed no reset, clean, checkout, rebase, amend, commit or push.

No unrelated work is an implementation input except where the canonical plan explicitly cites the research records.

## 4. Canonical plan status

The canonical implementation plan was previewed and applied in manual/no-commit mode:

```text
patch: 20260824T151350Z_patch_9c28d629
apply status: applied
changed files: 1
validation errors: 0
file: docs/SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md
```

The plan was 1,993 lines / 48,935 bytes at the original RM0 acceptance boundary.

Post-RM0 owner amendment:

```text
patch: 20260824T152721Z_patch_c050efe8
status: applied
scope: RM8 canonical arash-research workflow / research-map finishing touch only
current plan: 2,041 lines / 52,250 bytes
```

This authorized amendment does not change RM0/RM1 source seams, repository-perimeter assumptions, public gateway baseline, dependency ordering, or acceptance of the RM0 preflight. It strengthens the later RM8 workflow requirement so adopted-project research is closed with reviewed sidecar + explicit map sync/read-back verification, with explicit degraded/unavailable states when that finishing touch cannot complete.

## 5. Public gateway baseline

Live Soma capability inspection reports:

```text
public gateway/tool count: 38
operation inventory gateway count: 38
public_schema_hash:
5ef04e36efed1496ede40ffe3c51c8f8fe3de06255f0b9ecfda15905c4df8ebd

public_descriptor_hash:
e53780fa49bc31702e89601bd8f9b8db3844b15aeac5b77c0659a0e2171ebd60
```

The implementation plan expects exactly two new public names at activation:

```text
research_map_query
research_map_action
```

Expected eventual public name count after both are accepted:

```text
40
```

This is a target, not an RM1 mutation.

## 6. Source seams rechecked

RM0 re-read and reconciled the following current production seams.

### Repository read perimeter

`repo_reader.py` currently blocks runtime/cache namespaces such as `.git`, `.venv`, `runs`, `artifacts`, `models`, `credentials`, and `secrets`, but does **not** yet include `.soma` in `_BLOCKED_NAMES`.

This confirms the RM1 perimeter change remains required.

### Repository write perimeter

`repo_writer.py` extends the reader validation path and therefore can inherit `.soma` blocking once the reader perimeter is corrected.

It already contains canonical newline helpers used by repository patch mechanics, but research-map canonical scientific hashing remains a separate explicit contract in the new package.

### Repository wiki

`repo_wiki.py` currently uses:

```text
repo/.soma/wiki/
```

and immutable generation semantics.

It does not yet list `.soma` in `_BLOCKED_DIRS` and currently treats JSON as a source-text candidate.

Therefore RM1 must:

- block `.soma` in all wiki source enumeration paths;
- exclude tracked `_soma_map/` sidecars from generated code-wiki candidates;
- preserve ordinary authorized repository reads of those sidecars.

The wiki generation model remains a reliability precedent only; the research-map implementation remains separate.

### Tool-owned paths

`tool_owned_paths.py` currently does not classify `.soma/` as a tool-owned repository-local runtime prefix.

RM1 must add it so status/knowledge classification cannot drift from repository readers/wiki again.

### ProjectScope

`repository_identity_hash()` still derives local attachment identity from the canonical absolute repository root path.

This confirms the tracked research-map `repository_uid` must remain separate from local ProjectScope authority.

No ProjectScope schema redesign is needed by RM1.

### Legacy knowledge/research gateway

`knowledge_query` still contains the legacy operations:

```text
get_research_source
get_claim_evidence
list_research_questions
list_research_decisions
search_research
build_context_packet
research_health
```

The new research map must not be routed through these operations.

No legacy RAGFlow/context-packet repair is part of this implementation programme.

### Public gateway registration

Public contracts continue to be governed through:

```text
gateway_models.py
server.py
public_tool_metadata.py
public_gateway_inventory.py
cf1_gateway_operation_inventory.py
```

New research-map tools can therefore be registered as a separate gateway family without modifying the legacy knowledge request union.

## 7. Dependency baseline

Current unconditional package dependencies remain:

```text
fastmcp
pydantic
pyyaml
```

No Graphiti/FastEmbed/FalkorDB dependency has been added.

RM1 must remain backend-independent and must not change this fact.

Optional backend dependency work belongs only to RM5 after earlier stages are accepted.

## 8. Test surface rechecked

The current test suite already has direct seams suitable for RM1 regression protection:

```text
tests/test_repo_reader.py
tests/test_repo_writer.py
tests/test_repo_wiki.py
tests/test_tool_owned_paths.py
tests/test_safety.py
tests/test_public_gateway_inventory.py
tests/test_public_tool_metadata.py
tests/test_cf1_gateway_operation_inventory.py
tests/test_capabilities.py
```

RM1 should add focused research-map model/canonicalization tests rather than place those semantics into the legacy research tests.

Recommended new RM1 test file(s):

```text
tests/test_research_map_models.py
tests/test_research_map_canonical.py
```

Public gateway tests are not required until RM3.

## 9. RM1 exact intended source scope

RM1 implementation is limited to:

```text
soma/tool_owned_paths.py
soma/repo_reader.py
soma/repo_writer.py          only if a direct perimeter regression requires it
soma/repo_wiki.py
soma/research_map/__init__.py
soma/research_map/models.py
soma/research_map/canonical.py

tests/test_tool_owned_paths.py
tests/test_repo_reader.py
tests/test_repo_writer.py    only if needed for inherited `.soma` blocking proof
tests/test_repo_wiki.py
tests/test_research_map_models.py
tests/test_research_map_canonical.py
```

No other production file should be edited during RM1 unless a concrete test/source dependency proves it necessary and the implementation thread stops to reconcile the scope first.

## 10. RM1 acceptance target

RM1 must prove all of the following without Graphiti:

1. `.soma/` is inaccessible through generic repo reader paths;
2. generic repo writes cannot mutate `.soma/`;
3. `.soma/` is always excluded from wiki scans including filesystem fallback;
4. `_soma_map/*.json` is excluded from the code wiki but remains readable via ordinary authorized repo reads;
5. `.soma/` is centrally classified tool-owned;
6. UTF-8 LF/CRLF-equivalent research Markdown produces the same canonical text SHA-256;
7. substantive source changes produce a different canonical hash;
8. Unicode survives canonicalization and locator model round trips;
9. strict research-map v2 models reject malformed paths, predicates, lifecycle and epistemic values;
10. deterministic relation/record identity is stable across repeated calls;
11. current unrelated worktree state remains untouched;
12. no optional backend/provider dependency is introduced.

## 11. Explicitly unchanged by RM0

RM0 changed no production source and did not:

```text
install Graphiti
install FalkorDB Lite
install FastEmbed
create soma.project.json in any project
create project sidecars
create .soma/research-map in any live research repository
repair legacy search_research
change continuation
change ProjectScope identity
use Codex
commit
push
```

## 12. Verdict

**ACCEPTED — RM0 AUTHORITY/PREFLIGHT IS COMPLETE.**

The live Soma repository still matches the implementation programme closely enough to begin RM1 without architectural reconciliation.

The next permitted implementation stage is:

```text
RM1 — repository perimeter + canonical research-map models
```

RM1 is the first production source implementation stage and requires explicit continuation/authorization from the owner thread.
