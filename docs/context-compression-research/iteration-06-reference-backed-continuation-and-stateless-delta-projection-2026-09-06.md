# Context Compression Research — Iteration 06

## Reference-backed continuation and stateless delta projection

Date: 2026-09-06
Status: RESEARCH COMPLETE — architecture candidate not yet implemented or accepted
Branch during research: `experiment/context-compression-plane-bc-20260906`
Protected pre-experiment commit: `29767c8d9566ea8d28fd6a2a55b20f49acfdfa18`
Protected safety branch: `safety/context-compression-pre-plane-bc-20260906`
Continuation: `cont_20260905T204910Z_07a66dcb7a07`

---

## 1. Purpose

Iterations 01–05 established that Soma/ChatGPT context pressure has at least three distinct planes:

1. public MCP tool-definition/discovery context;
2. working-state/tool-result context;
3. exact evidence and historical result bodies.

Plane A tool-schema compression was deliberately parked after Iteration 05 because deterministic safe savings were only a few percent and the large theoretical gain depended on opaque ChatGPT host-side discovery behavior. That path would also approach the same OpenAI MCP lifecycle boundary that previously forced Soma to preserve stateless Streamable HTTP operation.

Iteration 06 therefore asks a different question:

> How much context can Soma remove from ordinary continuation and Run-monitoring responses while preserving every authoritative fact and keeping exact evidence deterministically reopenable?

The iteration is constrained by the owner-approved transport boundary:

```text
one ChatGPT app
one stateless Streamable HTTP /mcp endpoint
one canonical Soma backend
```

No connector refresh, app registration, endpoint, transport, service restart, public tool addition/removal, or source runtime change was performed in this iteration.

---

## 2. Safety boundary established before research

Before any Plane B/C experiment, a hard Git restore point was created and verified.

Known-good commit:

```text
29767c8d9566ea8d28fd6a2a55b20f49acfdfa18
```

Protected branches at that exact commit:

```text
safety/context-compression-pre-plane-bc-20260906
rollback/pre-core-hardening-20260823
```

The working research branch is:

```text
experiment/context-compression-plane-bc-20260906
```

The owner has an independent PowerShell recovery procedure that stashes dirty work, switches to the safety branch, verifies the exact hash, and restarts Soma. No destructive `reset --hard`, `clean`, rebase, amend, or history rewriting is required.

---

## 3. Major finding: continuation resume is currently the dominant result-payload amplifier

A live call to:

```text
continuation_query(operation="resume")
```

on the research continuation returned the current contract and latest Sol handoff, but also returned the default page of 20 associated effects.

Source inspection established the exact mechanism.

`ContinuationResumeQuery` currently declares:

```text
effect_limit default = 20
minimum = 1
maximum = 100
```

`ContinuationService.resume()` then:

1. retrieves the current continuation and contract revision;
2. retrieves the latest handoff;
3. calls `effect_history(..., limit=effect_limit)`;
4. places that complete page under `associated_effects`.

For linked Runs, `_effect_projection()` calls `_run_projection()`.

`_run_projection()` currently reads both:

- `RunStore.get_run_summary(run_id)`;
- `RunStore.get_public_result_snapshot(run_id)`.

It then embeds the Run summary plus the entire nested public-result snapshot inside the continuation response.

Therefore a resume can replay substantial historical Run output that already exists under canonical Run authority.

---

## 4. Exact current-workload measurement

Read-only measurement Run:

```text
20260905T221926Z_executable_profile_7a7ff249
```

It constructed the normal `ContinuationService` against the canonical `runs` store and measured the current research continuation with `effect_limit=20`.

Results:

| Measurement | Bytes |
|---|---:|
| Full current resume | 158,369 |
| `associated_effects` alone | 155,075 |
| Resume with no inline effect items, retaining history metadata | 3,837 |
| Sum of 20 nested `public_result` bodies | 60,425 |
| Reference-backed candidate that removes only nested `public_result` bodies | 99,844 |

The full associated-effect page therefore accounts for approximately 97.9% of the measured resume payload.

Removing only the duplicated public-result bodies saves:

```text
58,525 bytes
37.0%
```

but leaves the resume near 100 KiB, so public-result duplication is not the only dominant source.

---

## 5. Second dominant source: repeated Run summaries

A second read-only measurement decomposed the remaining effect payload.

Measurement Run:

```text
20260905T221952Z_executable_profile_24e9dd38
```

The 20 canonical Run `summary` strings alone occupied:

```text
68,523 bytes
```

This is particularly expensive in research-heavy workflows because many experiment Runs publish multi-kilobyte structured summaries.

Those summaries already belong to Run authority and can be fetched when the controller actually needs their content. Replaying every summary merely because the Run is linked to a continuation duplicates historical evidence in fresh model context.

---

## 6. Status-head candidate

A purely mechanical reference-backed effect projection was synthesized in memory. It kept all 20 effect links but replaced copied Run result bodies with current state and exact evidence identity.

For each effect, the outer lineage remains:

```text
link_id
effect_kind
effect_id
origin_contract_revision_id
linked_at
```

For a currently available Run, the candidate canonical head retains:

```text
projection_status
status
current_phase
state_version
exit_code
safety_failure
recovery_reason
```

and result identity:

```text
projection_status
publication_status
published_hash
public_result_status
public_result_source_sha256
public_result_error
```

plus an explicit deterministic retrieval recipe:

```json
{
  "tool": "run_query",
  "operation": "terminal",
  "run_id": "<effect_id>"
}
```

It does not inline:

- the Run summary body;
- the nested public-result body;
- duplicated terminal evidence content.

Exact evidence remains unchanged under RunStore authority.

Measured result:

| Projection | Bytes |
|---|---:|
| Current resume | 158,369 |
| Status-head resume | 20,734 |
| Status-head `associated_effects` | 17,440 |
| Non-effect resume material | ~3,294 |

Saving:

```text
137,635 bytes
86.9%
```

This is the first measured compression candidate in this programme with both large magnitude and no dependency on undocumented ChatGPT host behavior.

---

## 7. Why this is evidence-lossless rather than byte-resident lossless

The proposed projection does not claim that every original output byte remains simultaneously resident in ChatGPT's prompt.

Instead it satisfies the programme's stronger system-level requirement:

> Exact evidence may leave active model context only if it remains unchanged, canonically owned, uniquely identified, integrity-bound, and deterministically reopenable before reliance.

For linked Runs:

```text
continuation effect head
    ↓
effect_id / run_id
published_hash
public_result_source_sha256
    ↓
run_query(terminal)
    ↓
exact current public Run result / evidence references
```

Nothing is summarized semantically by Soma. Nothing is reconstructed from a lossy prose summary. The controller decides which exact evidence is worth reopening.

---

## 8. This matches the previously accepted continuation architecture

The authoritative final continuation research was reopened rather than inferred from memory:

`docs/sol-agentic-loop-realignment-research/iteration-30-final-synthesis-minimal-sol-semantic-reentry-2026-08-15.md`

That architecture explicitly says:

- Sol/ChatGPT remains the reasoning agent;
- Soma provides durable external truth, effect identity/recovery, and a **very small semantic re-entry layer**;
- effect links are retained because they provide mechanical discovery of durable effects launched after the latest handoff;
- the effect-link acceptance contract requires **no copied effect state** and requires current status to be resolved from canonical authority;
- fresh Chat should resume contract + handoff + linked effect status and inspect current world state as needed;
- a long-running scientific Run acceptance case requires fresh Chat to identify the linked Run/current result state and continue scientific reasoning.

This makes the current 158 KiB historical result replay look more like projection amplification than an architectural requirement.

C2 source acceptance was also reopened. It requires durable origin links, current canonical projection, bounded/cursor-retrievable history, and conservative missing/unavailable projection. It does not require every historical result body to live inline in resume.

---

## 9. Existing continuation tests are compatible with compact Run heads

The current continuation regression suite was inspected.

For a linked Run, `test_c2_resume_projects_current_canonical_run_truth_and_bounded_result` asserts:

```text
effect_kind == run
canonical.projection_status == available
canonical.status == completed
canonical.result.projection_status == available
result_json is not copied into canonical.result
```

Search across `tests/test_continuation*.py` found no assertion requiring:

- full `public_result` inline;
- Run `summary` inline.

Task continuation tests do require current Task state/recovery and should remain unchanged.

Therefore a compact Run effect projection can preserve the already-accepted semantic contract while reducing context amplification.

---

## 10. `effect_limit=1` is not an acceptable solution

The public input already allows reducing the effect page to one item, and this was tested live.

It substantially reduces payload, but the newest effect in the research continuation was a trivial validation Run with an empty output. The semantically important current boundary remained the latest handoff.

Therefore:

```text
default 20 → default 1
```

is rejected as a final architecture.

It would save bytes by arbitrarily hiding mechanical lineage rather than by projecting lineage efficiently.

The preferred design keeps bounded effect lineage but makes each linked effect cheap.

---

## 11. Major existing win: Soma already implements stateless conditional Run polling

Iteration 06 also investigated repeated monitoring payloads.

Two consecutive `run_query(status)` calls against completed Run:

```text
20260905T220455Z_executable_profile_7dbb3f2a
```

returned the full standard status projection each time:

```text
state_version = 11
payload_bytes = 1,851
```

The canonical state had not changed. Only time-derived observations such as heartbeat age changed.

Source inspection found that Soma already has the desired stateless delta mechanism under:

```text
run_query(operation="control", if_state_version=...)
```

`job_manager.py` contains `_build_unchanged_control_response()`, and `public_projection_contract.py` gives unchanged polling a 1 KiB budget.

Live proof with the same Run:

### Matching version

```text
if_state_version = 11
unchanged = true
payload_bytes = 410
```

Reduction versus ordinary status:

```text
1,851 → 410 bytes
77.8% smaller
```

### Stale version

```text
if_state_version = 10
unchanged = false
state_version = 11
payload_bytes = 1,852
```

Soma correctly returned the full current state when the client's known version was stale.

This is exactly the required architecture for safe monitoring compression:

```text
client/controller carries last canonical state_version
        ↓
stateless conditional query
        ↓
unchanged → tiny receipt
changed   → full current state + new version
```

No MCP session continuity is required.

---

## 12. Transport safety

The two strongest Iteration 06 mechanisms are both compatible with the rollback lesson from OpenAI MCP issue #201.

### Reference-backed continuation

Requires no server-side client session. Every resume remains an ordinary stateless request.

### Conditional Run polling

The previous state version is explicit request data. Soma does not need to remember which ChatGPT request came before it.

Therefore both mechanisms survive a client that repeatedly initializes MCP or drops `Mcp-Session-Id` between batches.

---

## 13. Connector-refresh risk is substantially lower than Plane A

`continuation_query` is registered as:

```text
output_schema = GENERIC_OBJECT_OUTPUT
annotations = READ_ONLY_ANNOTATIONS
```

Its public gateway delegates `resume` to `ContinuationService.resume()`.

A future implementation that changes only the shape/content of the returned generic object can preserve:

- tool name;
- tool description;
- input schema;
- tool annotations;
- generic output schema;
- single `/mcp` endpoint;
- stateless transport.

Therefore the likely prototype path does **not** require a ChatGPT app action refresh or connector re-registration.

This must still be proven by comparing public schema/descriptor hashes before and after any source implementation.

---

## 14. Candidate architecture after Iteration 06

The strongest current candidate is now layered:

```text
CHATGPT ACTIVE CONTEXT

contract revision
+ exact latest handoff
+ bounded effect status heads
+ exact evidence identities / hashes / retrieval recipes
+ current state deltas

              │
              ▼ on demand

SOMA DURABLE AUTHORITIES

RunStore / TaskStore / repository / Research Map / artifacts
full exact result bodies
full summaries
logs
source evidence
history pages
```

This is conceptually similar to the successful interface discipline identified in the original continuation research: keep machine truth behind stable identities and bring only the working set into the reasoning context.

---

## 15. What is not yet accepted

Iteration 06 does **not** authorize or establish that:

- `_run_projection()` should definitely be changed directly;
- `effect_history()` and `resume()` should necessarily use the same compact projection;
- the exact candidate field set is final;
- 20 should remain the default effect count forever;
- all Run summaries should always be omitted;
- every other Soma public projection should use references;
- a live ChatGPT freeze is proven solved by this mechanism.

Those require adversarial implementation/prototype testing.

---

## 16. Proposed next research iteration

Iteration 07 should build a **source-level, connector-neutral prototype on the experiment branch only**.

The prototype should be restricted to the continuation Run projection seam and prove all of the following before any live server activation:

1. current Run status/result availability remains visible in resume;
2. Task continuation behavior is unchanged;
3. missing/unavailable effect behavior is unchanged;
4. all historical links/cursors remain unchanged;
5. exact Run evidence remains reopenable via `run_query(terminal)`;
6. public tool name/input schema/annotations/output schema and public descriptor hash remain unchanged;
7. measured resume size on the real research continuation falls from ~158 KiB toward the ~21 KiB offline candidate;
8. targeted continuation tests and related public-contract tests pass;
9. no connector refresh is performed;
10. activation, if later attempted, uses only the existing Soma server restart and can be rolled back by switching to the protected safety branch.

A separate small guidance follow-up should evaluate whether normal Run monitoring can preferentially use the already-existing `control + if_state_version` path without changing the public connector descriptor.

---

## 17. Iteration 06 conclusion

Plane B/C is now the strongest direction in the research programme.

The measured continuation payload is not dominated by unique semantic continuity information. It is dominated by mechanically copied historical Run summaries and public-result bodies that remain available under canonical Run authority.

A reference-backed status-head projection reduced the measured resume by **86.9%** while retaining all 20 linked effects and exact retrieval identity.

Separately, Soma already contains a proven stateless conditional Run-poll path that reduces unchanged polling by **77.8%** and automatically returns full state when the known version is stale.

These mechanisms provide materially larger, more deterministic context reduction than the Plane A schema-consolidation candidates and do so without adding MCP endpoints, client sessions, apps, or opaque host dependencies.

Architecture remains open pending the controlled Iteration 07 prototype.
