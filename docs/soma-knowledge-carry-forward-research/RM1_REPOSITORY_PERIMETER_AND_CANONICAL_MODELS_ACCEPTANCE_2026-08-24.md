# RM1 — Repository Perimeter and Canonical Research-Map Models Acceptance

**Date:** 2026-08-24  
**Programme:** Soma Hybrid Research Map  
**Stage:** RM1  
**Status:** ACCEPTED  
**Implementation authority:** `docs/SOMA_HYBRID_RESEARCH_MAP_IMPLEMENTATION_PLAN_2026-08-24.md`  
**Planning/implementation HEAD:** `7e7450e08331aeed744867be955feb42149b18f4`  
**Branch:** `rollback/pre-core-hardening-20260823`

## 1. Purpose

RM1 implements only the backend-independent foundation required by the hybrid research-map programme.

The accepted boundary is:

```text
repository perimeter
+ canonical portable text/JSON identity
+ strict research-map v2 models
+ deterministic record/relation identities
```

RM1 intentionally does **not** implement:

```text
Graphiti
FalkorDB / FalkorDB Lite
FastEmbed
manifest loading from live projects
sidecar source/anchor scanning
coverage engine
desired-state engine
public research_map_query
public research_map_action
repo adoption
map sync/rebuild
historical backfill
legacy research-system repair
```

Those remain later RM stages.

## 2. Owner and architecture invariants preserved

RM1 preserves all governing research-map rules:

1. research Markdown remains authoritative scientific truth;
2. reviewed sidecars are durable derived semantic projections, not a second truth store;
3. `.soma/` is local disposable Soma runtime state;
4. tracked `_soma_map/` files remain ordinary repository content available to explicit repository reads;
5. the generated code wiki must not index `.soma/` runtime or `_soma_map/` semantic sidecars;
6. research identity must not depend on human research numbers;
7. portable source freshness uses canonical UTF-8/LF text identity, not raw checkout bytes;
8. Graphiti/backend constraints do not shape the durable sidecar schema;
9. no Codex integration is introduced;
10. no continuation change is introduced.

## 3. Production source scope

Exactly these production files were changed or created for RM1.

### Existing files changed

```text
soma/tool_owned_paths.py
  final SHA-256:
  a76c36ea8c64e7cd0a39c3767eccd1c63eb4169ac4c7ad56af5d740fc62dceb8

soma/repo_reader.py
  final SHA-256:
  b6a3155a46c83c7f6836c4eacc04eb10e4d24502ecc29f45ea9cfd1e308e28e8

soma/repo_wiki.py
  final SHA-256:
  d92a5de02b5c39cb5de529dae7ce338823b50b1bdb39ae257ff99bb1915a4af7
```

### New backend-independent package

```text
soma/research_map/__init__.py
  final SHA-256:
  7ccf3a35f30821e16f617bb8e1570a40d825227cf42dd01c4b2df0ade86f8869

soma/research_map/canonical.py
  final SHA-256:
  e12b38d8d7e3e6dc2ff2429ad2187ee37c47d780e84170a700b302b659487d72

soma/research_map/models.py
  final SHA-256:
  3b92c011f111ab3aaee72d32786d56705956864d9ee99070bb70fdc139e90b91
```

`repo_writer.py` was **not** changed. Its generic write validation already delegates through `repo_reader._resolve_and_validate()`, so reserving `.soma` in the reader perimeter also blocks generic repository write paths.

## 4. Test scope

Existing tests changed:

```text
tests/test_tool_owned_paths.py
  SHA-256 3b983e569dd5f525b85681d3b60fa0b5f2b7634a4532a437eb22013c2f9847a3

tests/test_repo_reader.py
  SHA-256 f3ea46e62b4a806fc46cc4bfac2b81c038e79fb03f81e1472ecd143a2c409cdb

tests/test_repo_writer.py
  SHA-256 ae85a12206800a6b565bd6377712cd13a647931948576692464de33f0362fa5a

tests/test_repo_wiki.py
  SHA-256 58ba47ee6565380ec1b00582b2e515c8302f96842396ae8c82ebfeb486213e54
```

New tests:

```text
tests/test_research_map_canonical.py
  SHA-256 57c32be0cd3fd00c37eafbd38b95188932dae2dd61b6df3f6f8561f71675d2a0

tests/test_research_map_models.py
  SHA-256 292e3e68bd117149b137e7bb0b0ac0618be4e7462bc657f652be2d69595d91ab
```

No public-gateway test file was changed because public research-map tools do not activate until RM3.

## 5. Repository perimeter accepted behavior

### 5.1 `.soma/` is centrally tool-owned

`TOOL_OWNED_PREFIXES` now includes:

```text
.soma/
```

Therefore paths such as:

```text
.soma/wiki/CURRENT.json
.soma/research-map/CURRENT.json
.soma/research-map/index/db.rdb
```

are classified as Soma/tool-owned runtime rather than owner-authored repository knowledge.

### 5.2 Generic repository reader refuses `.soma/`

`.soma` is now a blocked path component in the generic repository reader.

Direct generic reads/listing through that namespace fail closed.

This is intentional: future research-map runtime inspection must use the dedicated research-map service rather than general repository tools.

### 5.3 Generic repository writer refuses `.soma/`

Because the writer inherits the reader's path validation, generic create/preview/write operations cannot create or modify:

```text
.soma/...
```

A dedicated RM4+ runtime/adoption service will own those paths explicitly.

### 5.4 `_soma_map/` is not globally blocked

Tracked sidecars such as:

```text
docs/research/_soma_map/001_result.json
```

remain readable through ordinary authorized repository reads.

That is required because sidecars are durable repository content rather than disposable runtime.

### 5.5 Wiki excludes runtime and sidecars

The generated code wiki now excludes:

```text
.soma/
_soma_map/
```

The exclusion is proven for both:

```text
Git candidate discovery
filesystem fallback discovery
```

This prevents hundreds of future semantic sidecars from inflating or polluting the generated code wiki while preserving their availability to the research-map service and generic repository reads.

## 6. Canonical source/text contract accepted

`canonical.py` implements the Iteration-12 portability correction.

For research Markdown:

```text
strict UTF-8 decode
→ CRLF → LF
→ remaining CR → LF
→ UTF-8 encode
→ SHA-256
```

Therefore semantically identical UTF-8 Markdown checked out with LF, CRLF or CR line endings receives the same portable canonical text hash.

A substantive character change receives a different hash.

Invalid UTF-8 fails closed.

Unicode is preserved; it is not ASCII-normalized or case-folded.

## 7. Canonical JSON contract accepted

Canonical JSON uses:

```text
UTF-8
ensure_ascii = false
sorted object keys
compact deterministic separators
NaN/Infinity forbidden
Pydantic aliases honored
None omitted for canonical model projection
```

This gives deterministic backend-independent semantic serialization while preserving Unicode.

## 8. Repository-relative path contract accepted

Research-map paths are normalized to POSIX repository-relative form.

Rejected forms include:

```text
empty path
absolute path
UNC/leading slash
drive prefix
..
.
empty path segment
.git namespace
.soma namespace
```

Backslashes are normalized to `/` before identity calculation.

This contract is portable across Windows and POSIX-style repository representations.

## 9. Deterministic identity contract accepted

### Logical research record

```text
logical_record_id
= SHA-256(normalized repository-relative source path)
```

with prefix:

```text
rrec_
```

### Research record version

```text
record_version_id
= SHA-256(logical_record_id + canonical_text_sha256)
```

with prefix:

```text
rver_
```

### Reviewed semantic relation

```text
relation_id
= SHA-256(
    normalized source path
  + subject key
  + predicate
  + object key
)
```

with prefix:

```text
rel_
```

Display labels, statement wording, timestamps, rank and backend attributes are deliberately excluded from relation identity.

A semantic statement refinement therefore preserves the relation ID while changing future sidecar/desired-state identity, exactly as required by the Axon pilot.

## 10. Strict v2 model contract accepted

All research-map models use strict extra-field rejection.

### Sidecar schema

```text
soma.research-map.v2
```

### Portable project manifest schema

```text
soma.project.v1
```

External JSON retains the field name:

```json
"schema"
```

while internal Pydantic attributes use a non-conflicting alias-backed name. This removed Pydantic's BaseModel `schema` shadow warning without changing the portable JSON contract.

### Portable repository UID

Accepted form:

```text
srepo_<16-to-64 lowercase hex chars>
```

Local ProjectScope identities are not accepted as substitutes.

### Research roots

Roots must be repository-relative, bounded and non-overlapping.

Nested roots that could double-own one source are rejected.

### Source envelope

Source path must identify UTF-8 Markdown and must not point into `_soma_map/`.

`canonical_text_sha256` must be a valid SHA-256 digest.

### Review state

Accepted states:

```text
reviewed
  materiality = material | none

deferred
  materiality omitted
```

Semantics:

```text
reviewed + materiality=material
  requires at least one relation

reviewed + materiality=none
  requires zero relations

deferred
  requires zero relations
```

Missing sidecar remains distinct and will mean unreviewed in RM2.

## 11. Predicate registry accepted

### Scientific

```text
ALLOWS
CONSTRAINS
FALSIFIES
FORBIDS
LIMITS
MOTIVATES
NARROWS
PRESERVES
QUALIFIES
REQUIRES
SUPPORTS
```

### Governance / authority

```text
GOVERNS
AMENDS
AUDITS
ACCEPTS
SUPERSEDES
RECONCILES
CLOSES
REOPENS
AUTHORIZES
PARKS
```

### Provenance / transfer

```text
INFORMED_BY
IMPORTS_EVIDENCE_FROM
DERIVES_FROM
REPRODUCES
REPLAYS
```

Generic `RELATED_TO` is deliberately absent.

Unknown predicates fail schema validation.

Registry version:

```text
soma.research-map.predicates.v1
```

## 12. Epistemic registry accepted

```text
observed
inference
hypothesis
decision
requirement
constraint
interpretation
unknown
```

Unknown values fail closed.

This prevents future retrieval from erasing distinctions such as hypothesis versus observed result.

## 13. Relation lifecycle registry accepted

```text
current
superseded
disputed
archived
rejected
```

Unknown values fail closed.

Successor-owned supersession remains the governing architecture; a relation cannot supersede itself and duplicate supersession IDs are rejected.

## 14. Facet and qualifier contract accepted

Facets and qualifiers remain structured:

```text
dict[str, list[str]]
```

They are bounded and reject blank keys/values and duplicate values.

RM1 does not flatten them for a backend.

Backend projection belongs to RM5 and later.

## 15. Regression evidence

### Final RM1 regression

Durable run:

```text
20260824T160544Z_executable_profile_765ab85f
```

Command used the repository's exact virtual environment:

```text
.venv\Scripts\python.exe -m pytest
  tests/test_research_map_canonical.py
  tests/test_research_map_models.py
  tests/test_tool_owned_paths.py
  tests/test_repo_reader.py
  tests/test_repo_wiki.py
  tests/test_repo_writer.py
  -q
```

Result:

```text
249 passed in 45.09s
exit code 0
```

This is the final acceptance run against the final RM1 source bytes.

### Earlier full regression

Run:

```text
20260824T160157Z_executable_profile_e6fb7b3f
```

Result:

```text
249 passed in 48.89s
```

The earlier model version had two Pydantic warnings caused by using `schema` as an internal field name. The warning was removed before final acceptance by retaining `schema` only as the serialized alias.

### Environment-only failed launch

Run:

```text
20260824T155944Z_executable_profile_50b7eb14
```

PowerShell's bare `python` resolved to LibreOffice's bundled Python and failed before loading Soma because that interpreter had no pytest.

This was not an RM1 code failure.

Interpreter resolution then established:

```text
D:\Github\Soma\.venv\Scripts\python.exe
pytest 9.1.1
```

All acceptance tests were rerun with the repository virtual environment.

## 16. Lint and repository hygiene

Final hygiene run:

```text
20260824T160521Z_executable_profile_1dad5266
```

Validated:

```text
ruff check
  soma/research_map
  tests/test_research_map_canonical.py
  tests/test_research_map_models.py

result: All checks passed!

git diff --check
result: PASS
```

Git emitted only normal Windows working-copy LF/CRLF conversion warnings; no diff-check error occurred.

A previous attempt to lint the whole legacy repository-reader/writer surface exposed pre-existing Ruff findings in files such as `repo_reader.py` unrelated to the one-line RM1 change. RM1 did not rewrite unrelated legacy code to satisfy those historical style findings.

## 17. Dependency invariant

`pyproject.toml` remains unchanged at SHA-256:

```text
5ac61bde08905fe815535c92c00691a3bd51b09408d49d5ad9bcc87492825ab3
```

Core dependencies remain exactly:

```text
fastmcp
pydantic
pyyaml
```

No Graphiti, FalkorDB, FastEmbed, OpenAI, RAGFlow, embedding-provider or graph-provider dependency was added.

## 18. Public gateway invariant

Live Soma capability state after RM1 still reports:

```text
public gateway/tool count: 38
operation inventory gateway count: 38
```

The public input schema identity remains:

```text
5ef04e36efed1496ede40ffe3c51c8f8fe3de06255f0b9ecfda15905c4df8ebd
```

The public descriptor identity remains:

```text
e53780fa49bc31702e89601bd8f9b8db3844b15aeac5b77c0659a0e2171ebd60
```

These are the exact RM0 baselines.

Therefore RM1 introduced **zero public-tool/schema drift**.

The planned move from 38 to 40 public tools remains reserved for RM3/RM4 gateway activation.

## 19. Worktree preservation

Pre-existing project work remains preserved.

In particular:

```text
AGENTS.md
```

already had an intended tracked modification before RM1 and was not rewritten by RM1.

Iterations 01–12, the canonical implementation plan and RM0 acceptance remain uncommitted durable documentation and were not cleaned/reset/rebased away.

No reset, checkout, rebase, amend or destructive cleanup was used.

## 20. Explicit non-effects

RM1 did not:

```text
change pyproject dependencies
install Graphiti into Soma
install FalkorDB/FastEmbed into Soma
create soma.project.json in a live research repo
create project semantic sidecars
create .soma/research-map in a live project
add public research_map tools
change ProjectScope
change continuation
repair legacy search_research
activate RAGFlow
write context packets
modify NSDN
modify Axon
use Codex
commit
push
```

## 21. Acceptance matrix

| RM1 requirement | Result |
|---|---|
| generic reader blocks `.soma/` | PASS |
| generic writer blocks `.soma/` | PASS |
| `.soma/` centrally tool-owned | PASS |
| wiki Git discovery excludes `.soma/` | PASS |
| wiki filesystem fallback excludes `.soma/` | PASS |
| wiki excludes `_soma_map/*.json` | PASS |
| generic repo read still reads tracked `_soma_map/*.json` | PASS |
| LF/CRLF/CR equivalent UTF-8 has same canonical SHA | PASS |
| substantive source edit changes canonical SHA | PASS |
| strict invalid UTF-8 fails | PASS |
| Unicode survives canonical text/JSON/locator round trip | PASS |
| manifest/sidecar extra fields rejected | PASS |
| invalid predicate rejected | PASS |
| invalid epistemic class rejected | PASS |
| invalid lifecycle rejected | PASS |
| invalid schema rejected | PASS |
| reviewed material/no-material/deferred semantics enforced | PASS |
| duplicate relation IDs rejected | PASS |
| self-supersession rejected | PASS |
| deterministic record/version/relation IDs stable | PASS |
| overlapping research roots rejected | PASS |
| local runtime identity fields excluded from portable manifest | PASS |
| no backend dependency introduced | PASS |
| public gateway contract unchanged | PASS |
| final focused/broad regression | 249/249 PASS |
| new package/tests Ruff | PASS |
| `git diff --check` | PASS |
| unrelated work preserved | PASS |

## 22. Verdict

**RM1 ACCEPTED.**

The repository perimeter and backend-independent research-map contract are now implemented and regression-tested.

The programme may advance to:

```text
RM2 — manifest, sidecar validation, coverage and desired-state engine
```

RM2 must remain backend-independent. It should add deterministic repository scanning, sidecar/source/anchor validation, coverage classification, successor-owned supersession resolution and semantic desired-state hashing **without** adding Graphiti/FalkorDB yet.

No commit or push was performed as part of RM1 acceptance.
