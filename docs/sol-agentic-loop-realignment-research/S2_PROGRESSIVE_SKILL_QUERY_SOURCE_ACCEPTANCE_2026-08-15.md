# S2 Progressive Skill Query — Source Acceptance

Date: 2026-08-15
Status: SOURCE ACCEPTED — NOT LIVE ACTIVATED
Programme: Sol Semantic Continuation + Soma Portable Skill Layer
Stage: S2 — `skill_query` progressive-disclosure gateway
Accepted implementation commit: `1577ec529a86993ecb5f7e97c61d203dfc371967`
Parent accepted stage: S1 at `76e1c0dbfa156da323d962d9f383f160f9011df8`

## 1. Authority

S2 was implemented against:

- `docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_IMPLEMENTATION_PLAN_2026-08-15.md`
- `docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_FINAL_AUDIT_2026-08-15.md`
- the accepted S1 portable Skill library substrate.

The governing boundary remains:

```text
Sol / ChatGPT chooses whether and how to use a Skill.
Soma stores, validates, discovers, and retrieves immutable Skill packages.
Soma does not select a Skill semantically, reason over Skill instructions,
or execute package scripts through the Skill authority.
```

S2 adds one public read gateway only:

```text
skill_query
```

with exactly six operations:

```text
capabilities
list
search
get
history
resource
```

No Skill mutation gateway is part of S2. That remains S3.

---

## 2. Accepted public semantics

### 2.1 `capabilities`

Returns bounded mechanical metadata describing the read surface, including:

- progressive-disclosure model version;
- cursor version;
- supported operations;
- list/search limits;
- resource chunk limits;
- current-enabled discovery default;
- exact historical-ref retrieval support;
- explicit `executes_resources = false`;
- explicit `grants_permissions = false`;
- explicit `chooses_skill = false`;
- explicit `runs_reasoning = false`;
- whether the configured owner library is initialized.

It does not initialize an absent Skill library.

### 2.2 `list`

Normal list discovery returns only:

```text
current + enabled Skill revisions
```

It returns bounded metadata, not `SKILL.md` content.

Historical and disabled revisions do not pollute ordinary discovery.

Pagination uses an opaque checksum-bound cursor.

### 2.3 `search`

Search is deterministic mechanical retrieval over:

```text
name
description
```

Ranking is:

```text
0 exact name
1 name prefix
2 name substring
3 description substring
```

The model supplies the query and chooses the result.

There is no embedding model, LocalAgent classifier, Supervisor planner,
hidden LLM router, or semantic Skill-selection authority.

Search cursors are bound to the normalized query identity and cannot be reused
for a different query.

### 2.4 `get`

`get` requires exactly one of:

```text
skill_ref
name
```

`get(name=...)` resolves only the current enabled revision.

It does not guess from historical revisions when no current enabled revision
exists.

`get(skill_ref=...)` retrieves the exact immutable revision even when that
revision is historical or the Skill is disabled.

This supports exact re-fetch after prior Chat context or prior Skill tool output
is no longer assumed present.

The response includes:

- exact `skill_ref`;
- name and description;
- package hash;
- current/historical marker;
- enabled state and mechanical state version;
- parent revision ref;
- bounded provenance summary;
- bounded `SKILL.md` text;
- `SKILL.md` size and SHA256;
- bounded package manifest projection;
- package-root locator where allowed by local projection policy.

The package locator is explicitly not execution authority.

### 2.5 `history`

History is explicit, name-scoped, cursor-paged retrieval of immutable revisions.

It exposes current/historical identity mechanically and never rewrites old
revisions.

Historical revisions remain exact-ref retrievable.

### 2.6 `resource`

Resource retrieval requires:

```text
exact skill_ref
package-relative path
```

The path is normalized through the S1 portable-package path rules.

The immutable package identity is reverified before returning bytes.

Per call, source bytes are capped at 256 KiB.

Continuation uses a checksum-bound cursor tied to:

```text
skill_ref
relative_path
offset
```

UTF-8 resources return bounded text.
Binary resources return base64.

Reading a script returns its bytes/content only.
It does not execute the script.

Returned package/resource locators do not grant tool or process authority.

---

## 3. Read-only authority correction discovered during S2

An important implementation issue was found before acceptance.

The S1 `SkillLibrary(...)` constructor normally creates its root directories and
registry database. Using that normal constructor from a public read-only MCP
gateway would therefore have made an apparently read-only query capable of
creating durable state.

S2 corrected the substrate rather than weakening the annotation.

`SkillLibrary` now supports:

```text
read_only=True
```

Read-only mode:

- requires an already initialized library;
- does not create the root;
- does not create `registry.sqlite3`;
- opens SQLite using `mode=ro`;
- does not request WAL mutation;
- rejects transaction/mutation paths;
- rejects materialization before filesystem staging can occur.

The following mutation authorities all explicitly refuse a read-only library:

```text
import_revision
import_directory
set_current
set_enabled
materialization path
```

The public `skill_query` gateway opens only this read-only form.

If the configured owner library does not yet exist:

- `capabilities` reports uninitialized;
- `list` and `search` return empty bounded pages;
- exact retrieval reports `skill_not_found`;
- no owner root or runs directory is created by the read call.

This makes the public `readOnlyHint=true` contract truthful by construction.

---

## 4. Response-bound hardening discovered during final audit

The first green S2 implementation bounded `get` by manifest item count, but the
final audit identified that item count alone was not a sufficient serialized
response bound when package paths are long and provenance sources carry large
source references.

S2 was hardened before acceptance.

Final `get` behavior now uses:

```text
SKILL.md source bytes: at most 48 KiB inline
manifest items: at most 100
manifest serialized projection: at most 16 KiB
provenance: bounded summary only
```

The provenance projection contains only:

```text
source_count
source_kinds
```

It does not echo potentially large source refs in normal `get` output.

A pathological acceptance package proves the bound with:

- 121 manifest files;
- three provenance sources;
- one provenance source ref at the S1 32,768-character maximum.

The returned manifest is correctly truncated by byte budget and the serialized
`get` response remains below the declared 384 KiB public ceiling.

The CF1 operation inventory now records explicit response ceilings for:

- capabilities;
- get;
- list/search/history;
- resource chunks.

---

## 5. Public metadata boundary

The public tool metadata description is:

> Use this when you need to discover or read reusable Soma Skills and their referenced resources. It does not execute Skill scripts, choose a Skill for you, or grant permissions described by a Skill.

Annotations are:

```text
readOnlyHint=true
destructiveHint=false
idempotentHint=true
openWorldHint=false
```

The read-only annotation is backed by the read-only library implementation above.

---

## 6. Public topology and identity

S2 intentionally expands the public topology by exactly one gateway and six
operations.

Final fresh-source discovery:

```text
public gateways: 37
operation schemas: 281
discovery converged: true
```

Public input schema hash:

```text
026aecea8830371c0525bd5d2991ce14887aa8a7625af23c3b1215c99e39e944
```

Public descriptor hash:

```text
5238cb3549a8444c0990f32e50fc101575d8fda9f0ced8d4ea71b6c6bc090454
```

Operation inventory hash:

```text
d88463538eb6602ea140c200cdcce2a7d7fc95cccf7fb6b4505997688309de5d
```

Exact S2 operation-schema hashes:

```text
skill_query.capabilities
f9f8e2b0f0486a040399f88e3ac1f24e56518a6511847a167f93e4d5d280249b

skill_query.list
9d4adbe306e9203c0ee8880b8c45ff1825885c1d8f4a377dd34da2360003cb19

skill_query.search
d86788600bf3ed7b06e49793a4c157befb5dca7b7179129299bd1081b3deb620

skill_query.get
d264b20d718de044e9947d0d2bd48cf4b6129db1d40535ba4d6dbf734c1e36fd

skill_query.history
883a570a2d479e607d816c31159ce0cffbecec0e34e4f308476f26f49e38706e

skill_query.resource
4e1bb7c4ab58f03d9ce7b307ed65899fa262df096a84d935d515a8e93e18d4c0
```

The aggregate input/output schema fixture identities are:

```text
input schema digest:
c2bbaa43b7a3d20e11715894266283e089ba2e081da3474a7bb5a67ac8ebd3cd

output schema digest:
f73fbf432d0eb71ea7e9a82f816b01aa578bd6b35e1a6f348eb54330294c773e
```

Public gateway inventory version:

```text
cf1.0.v4
```

CF1 gateway-operation inventory version:

```text
cf1.3.gateway-operations.v25
```

---

## 7. Test evidence

### 7.1 Pre-public service gate

Run:

```text
20260815T145900Z_executable_profile_a5703a44
```

Result:

```text
39 passed
Ruff PASS
git diff --check PASS
```

This established the S1/S2 service contract before MCP topology changes.

### 7.2 Initial public gate and classified failures

Run:

```text
20260815T150929Z_executable_profile_83bd44b0
```

Result:

```text
383 passed
3 failed
```

All three failures were test/fixture maintenance rather than runtime defects:

1. missing `SkillNotFound` import in the new S1 read-only test;
2. missing `SkillLibraryError` import in the same test file;
3. the pre-S2 gateway-union realistic-output allowlist did not yet include
   `skill_query`.

The fixtures were corrected without changing runtime semantics.

### 7.3 Corrected public-contract gate

Run:

```text
20260815T151355Z_executable_profile_722d4324
```

Result:

```text
386 passed in 180.06s
Ruff PASS
git diff --check PASS
```

### 7.4 First cross-authority proof

Run:

```text
20260815T151734Z_executable_profile_d7249954
```

Result:

```text
636 passed in 228.20s
Ruff PASS
git diff --check PASS
```

This proved coexistence across:

- S1 portable Skill library;
- S2 query service/gateway;
- C1-C5 continuation stack;
- RunStore / JobManager;
- canonical Task plane;
- ProjectScope;
- Hermes companion path;
- public gateway/inventory/descriptor/discovery contracts.

### 7.5 Response-bound hardening gate

Run:

```text
20260815T152530Z_executable_profile_8992dd31
```

Result:

```text
57 passed in 8.02s
Ruff PASS
git diff --check PASS
```

This includes the pathological manifest/provenance response-bound case.

### 7.6 Final hardened cross-authority acceptance

Run:

```text
20260815T152601Z_executable_profile_d74c431a
```

Result:

```text
637 passed in 222.85s
Ruff PASS
git diff --check PASS
```

Execution stayed on one process worker and lease generation 1.
There was no recovery, relaunch, cancellation, or stale-worker event.

This is the source accepted by S2.

---

## 8. Additional implementation incidents

The following non-semantic incidents occurred and are recorded for completeness.

### 8.1 Managed apply safety refusal

One managed apply for the new service-test file was refused by the repository
safety classifier before any write occurred.

The same hash-bound canonical apply was retried and succeeded.

No raw filesystem/Git bypass was used.

### 8.2 Discovery probe serialization mistake

One read-only identity probe attempted to JSON-serialize an internal `frozenset`
of operation names.

Discovery itself had succeeded; only the probe formatting failed.

The probe was rerun with the operation set normalized to a sorted list.

### 8.3 Ambiguous patch anchor

The first response-hardening preview used one generic CF1 anchor that occurred
three times.

`repo_preview` refused the ambiguous patch and made zero changes.

The patch was split into uniquely anchored edits.

### 8.4 Short repository-busy interval

Immediately after a completed long test run, one managed apply was refused as
`repository busy` while the canonical repository lease was still clearing.

The same canonical apply was retried after lease release and succeeded.

No lock bypass was used.

---

## 9. Explicit negative architecture proof

Final source scans over `soma/skills` found no implementation of:

```text
skill_execute
subprocess execution
LocalAgent Skill routing
Supervisor Skill routing
project-local .agents auto-scanning
```

There is no hidden semantic Skill router.

There is no second-model Skill classifier.

There is no SkillRuntime.

There is no automatic project-local Skill ingestion.

There is no automatic Skill activation.

There is no execution authority granted by Skill metadata, instructions,
scripts, package roots, or resource locators.

Soma remains retrieval/mechanical authority; Sol remains semantic reasoning
and choice authority.

---

## 10. Source-only rollout boundary

S2 acceptance is explicitly:

```text
SOURCE ACCEPTED
NOT LIVE ACTIVATED
```

This stage performed no:

- Soma service restart;
- connector Refresh;
- live public activation;
- deployment;
- Git push;
- Codex invocation;
- subagent invocation;
- secondary reasoning-model invocation.

The currently running Soma service therefore does not yet expose this new
source-level `skill_query` gateway merely because S2 source is accepted.

---

## 11. Implementation commit contamination audit

Implementation commit:

```text
1577ec529a86993ecb5f7e97c61d203dfc371967
```

Range from accepted S1:

```text
76e1c0dbfa156da323d962d9f383f160f9011df8
..
1577ec529a86993ecb5f7e97c61d203dfc371967
```

Result:

```text
18 files changed
1422 insertions
16 deletions
```

The range contains only S2 implementation/public-contract/test files.

Concurrent `docs/soma-improvement-research/*` work was not included.

---

## 12. Acceptance verdict

S2 satisfies the planned progressive-disclosure read layer:

- current enabled Skills are discoverable without full-body injection;
- search remains deterministic retrieval rather than semantic routing;
- exact immutable historical revisions are retrievable;
- disabled revisions remain exact-ref accessible without normal discovery pollution;
- resource reads are path/ref bound and chunked;
- scripts are data, not execution;
- exact Skill provenance can be recovered after Chat context loss by re-fetching the immutable ref;
- public reads are mechanically read-only;
- public response growth is explicitly bounded;
- no project-local untrusted Skill is auto-ingested;
- no semantic Skill authority was added to Soma.

**Verdict: S2 SOURCE ACCEPTED.**

Next mandatory stage is S3 — `skill_action` revision lifecycle.
S3 is not started by this acceptance.
