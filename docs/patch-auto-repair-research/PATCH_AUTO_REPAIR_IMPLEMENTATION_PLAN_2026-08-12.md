# Soma Patch Candidate Validation and Repair Resolution - Canonical Implementation Plan

Date: 2026-08-12
Status: HOLD - DO NOT IMPLEMENT WHILE THE AGENT/WORKER LANE HAS ACTIVE SHARED-WORKTREE CHANGES
Research basis: Iterations 1-4 under `docs/patch-auto-repair-research/`
Planning source point: `4fd5c327b57350c02a958a2d0f52cb73d8cffb43`
Primary implementation seam: `soma/repo_writer.py`

## 1. Purpose

This plan converts the completed Soma patch auto-repair research into a bounded implementation program.

The research began with a simple question:

```text
Can Soma automatically fix obvious model-generated patch payload mistakes?
```

The final answer is more precise.

Under the current public input contract, Soma cannot silently infer whether suspicious source bytes were accidental or intentional after request parsing has erased transport-origin provenance. Two identical `new_text` values are mechanically identical to deterministic downstream code.

Therefore the target is not silent semantic repair. The target is:

```text
model/controller patch request
        |
        v
Soma materializes complete candidate bytes in memory
        |
        v
bounded candidate-language validation
        |
        v
strong schema-bound transport-corruption detection
        |
        v
ONE deterministic repair proposal when mechanically justified
        |
        v
source preview remains non-applicable
        |
        +------------------------------+
        |                              |
 controller accepts repair      controller accepts original
        |                              |
        +---------------+--------------+
                        |
                        v
               new managed child preview
                        |
                        v
              existing repo_apply semantics
```

Soma proves mechanical properties. The controller decides intent. `repo_apply` remains an opaque deterministic executor of an already selected preview.

From the owner's perspective this may still behave like simple auto-correction: a controller that knows it accidentally leaked its own tool syntax may immediately select the deterministic repair proposal without asking the owner. The explicit resolution is between the controller and Soma; it is not inherently a new human-confirmation requirement.

---

# 2. Research conclusions that are implementation invariants

Every stage must preserve all of the following.

1. The two recovered patch incidents are implementation-friction evidence, not existing Soma contract bugs.
2. Candidate validation belongs after full candidate materialization and before managed preview applicability.
3. `repo_apply` does not detect, choose, synthesize, or re-run repairs.
4. Soma never uses an LLM/model to repair patch content.
5. Soma never treats `compile()` success alone as proof that a deletion repair preserves source semantics.
6. Python repair proposals require the researched logical-line `NEWLINE` boundary gate in addition to successful repaired-candidate compilation.
7. The `NEWLINE` gate is structural evidence for a proposal, not proof of caller intent.
8. Content-only downstream Soma cannot distinguish accidental from intentional identical bytes under the current request contract.
9. Therefore no silent automatic repair is allowed in v1.
10. A deterministic repair proposal requires explicit controller resolution.
11. `accept_repair` selects bytes already computed and preserved by the source preview. It never launches a second open-ended repair search.
12. `accept_original` overrides candidate-language validation only. It never bypasses repository binding, stale hashes, path restrictions, symlink/binary rules, operation overlap checks, size limits, authority, or any existing safety invariant.
13. The original malformed/source candidate remains preserved as durable evidence after resolution.
14. Resolution always creates a new managed preview identity; the source preview is never rewritten into the chosen child.
15. A source preview that requires resolution is never applicable.
16. A resolved source preview is never applicable.
17. The selected child preview is the only preview that may later be applied.
18. Existing rollback/revert semantics operate on the selected child preview and remain independent of repair reasoning.
19. Python is the first hard-validation and repair-proposal target.
20. `exact_text`, `line_range`, and `python_ast` are the first repair-proposal primitives.
21. `unified_diff` receives candidate validation but no repair synthesis in v1.
22. `create_file` has no baseline-validity proof and therefore does not receive the same modification hard-block policy in v1.
23. Candidate validation resource budgets are independent from changed-line/changed-byte patch limits.
24. Provider/tool-call-looking text is not automatically corruption merely because it looks suspicious.
25. Repair rules must be versioned, finite, testable, and tied to known transport/schema shapes.
26. If more than one repair is plausible, no repair proposal is emitted.
27. If a proposed deletion crosses or joins a Python logical statement, no repair proposal is emitted.
28. Candidate-valid Python is not rewritten merely because it contains suspicious text.
29. Existing public repository tool count must remain unchanged; this feature extends `repo_preview` rather than creating another public tool.
30. Any public input-schema change must go through the existing capability/schema identity and connector-refresh activation discipline.

If an implementation stage requires violating an invariant above, stop as `BLOCKED` and reconcile the design before touching more production code.

---

# 3. Current repository baseline and implementation seams

Planning HEAD:

```text
4fd5c327b57350c02a958a2d0f52cb73d8cffb43
```

At planning time the Agent/Worker lane has unrelated active worktree changes. Those changes are not inputs to this plan and must not be touched by this lane.

Relevant planning-point source identities:

```text
soma/repo_writer.py
  dc686e4889028cc5a9f426d4b5fcd6e745b1d0ebdb6b4358bc6d6b9dededc319

soma/gateway_models.py
  33ab828a585d1a00848eaa4bbefbda4398de3570f2e3bdf17c0f171aed9a634e

soma/server.py
  ee15e1729209beca0a63fcebed22daef40f6b67047c022af3e44ada2274bdbef
```

These are drift anchors, not permanent expected hashes. P0.2 must reconcile any later changes before implementation.

## 3.1 Current preview pipeline

Current `repo_preview(operation="patch")` flow is effectively:

```text
RepoPatchPreview public request
  -> server.repo_preview
  -> preview_repo_patch
  -> repo_writer._validate_operations
       read baseline bytes
       validate primitive
       apply edit in memory
       compose final per-file candidate
       calculate diff/stats/newline evidence
  -> _write_preview_bundle
       persist full selected payload bytes
       manifest bundle_version = 3
  -> return preview response
```

This is the correct validation seam. No second transaction system is required.

## 3.2 Current apply pipeline

`apply_previewed_repo_change` already:

- resolves one managed patch directory;
- rejects failed/reverted patches;
- validates repository fingerprint;
- enforces path uniqueness and write safety;
- rechecks Git HEAD where required;
- rechecks current file hashes;
- loads and hash-verifies opaque preview payloads;
- writes atomically;
- preserves rollback material;
- records apply result and supports idempotent replay.

This remains the authority boundary.

## 3.3 Current patch primitives

Public patch operation schema supports:

```text
exact_text
line_range
unified_diff
python_ast
```

Internal compatibility aliases exist. The new repair subsystem must key policy from the normalized primitive rather than duplicate aliases throughout the validator.

## 3.4 Current managed bundle

Current preview bundles use:

```text
bundle_version = 3
```

and preserve selected payload bytes/chunks plus payload SHA-256.

Current apply accepts bundle versions 2 and 3.

The feature planned here introduces new source-preview/child-preview provenance and resolution state. This plan deliberately chooses a new **bundle version 4** rather than silently redefining v3 semantics.

Versions 2 and 3 remain backward-compatible/applicable exactly as before.

## 3.5 Current public surfaces

No new public tool is needed.

Existing relevant surfaces:

```text
repo_preview
  patch
  create_file
  remove_file
  cleanup

repo_query
  patch_status

repo_apply
  previewed_change
  cleanup
  revert
  move_file
```

The new public input operation will be a `repo_preview` variant named `resolve_patch`.

`repo_apply` input schema does not gain a repair decision.

---

# 4. Final public contract decision

## 4.1 Keep one preview surface

Add:

```text
repo_preview(operation="resolve_patch")
```

Do not create:

```text
repo_repair
repo_fix
repo_autocorrect
```

Resolution is still preview construction, not repository mutation.

## 4.2 `RepoResolvePatchPreview`

Planned request model:

```text
operation = "resolve_patch"
repo_name
source_patch_id
resolution_request_id
decision
  accept_repair
  accept_original
proposal_id?          # required for accept_repair; forbidden for accept_original
view
response_budget_bytes
```

Validation:

- `source_patch_id` is mandatory and repository-bound;
- `resolution_request_id` is mandatory, caller-supplied, bounded, and idempotency-significant;
- `decision` is exactly one of the two values above;
- `accept_repair` requires exact `proposal_id`;
- `accept_original` must not carry a proposal ID;
- source preview must be in a resolvable v4 state;
- source preview must never already have been applied;
- stale repository/HEAD/file preconditions are rechecked before child preview creation;
- repeating the same normalized resolution request converges on the same child preview;
- same resolution request ID with different decision/proposal/material is a conflict.

## 4.3 Controller behavior

The public contract requires a controller decision, not necessarily a human confirmation.

A controller may do:

```text
repo_preview(patch)
-> resolution_required + one repair proposal
-> controller recognizes its own construction mistake
-> repo_preview(resolve_patch, accept_repair)
-> repo_apply(selected child later when authorized)
```

This is the intended low-friction path.

If the controller cannot establish its own intent, it must not guess. It can inspect the source preview or rebuild a new patch request.

## 4.4 Tool topology and metadata

Tool count remains 32.

At activation, update Candidate-B metadata for `repo_preview` so its goal-shaped description covers both preparing and resolving managed repository changes.

Expected identity effect:

- public tool count: unchanged;
- `repo_preview` input schema: intentionally changed;
- `public_schema_hash`: expected to change;
- `runtime_input_schema_hash` / `live_input_schema_hash`: expected to change with the same public input change;
- `public_descriptor_hash`: expected to change if metadata description changes;
- operation-inventory schema identity for `repo_preview`: expected to change;
- unrelated public tool schemas must remain byte/semantically unchanged.

Do not hard-code expected new hashes in advance. Compute and freeze them at the source acceptance gate.

---

# 5. Candidate validation contract

Create a dedicated pure module rather than growing every rule directly inside `repo_writer.py`.

Leading file:

```text
soma/repo_candidate_validation.py
```

The module is deterministic and receives already materialized bytes/text plus bounded edit provenance. It does not read the network, invoke models, mutate files, or access repository authority on its own.

## 5.1 `CandidateValidationV1`

Research-derived shape:

```text
schema_version = "repo_candidate_validation.v1"
path
language
  python
  json
  toml
  none
baseline_disposition
  valid
  invalid
  not_applicable
  not_checked
candidate_disposition
  valid
  invalid
  budget_skipped
  not_applicable
validator
validator_version
candidate_sha256
candidate_size_bytes
diagnostic?
  code
  message
  line?
  column?
  exception_type?
elapsed_ms
regression_detected
```

`elapsed_ms` is evidence/telemetry only and does not participate in candidate identity.

Do not copy giant parser exception bodies into public responses.

## 5.2 Python v1 policy

For modification previews whose path is Python-like (`.py`) and whose baseline/candidate fit validator budgets:

```text
baseline compiles + candidate compiles
  -> valid

baseline compiles + candidate fails
  -> validation regression
  -> source preview requires resolution

baseline fails
  -> warning / validation_not_authoritative
  -> do not hard-block merely because candidate also fails
  -> no v1 repair proposal based solely on syntax regression
```

This avoids converting an already-invalid fixture/scratch file into a mandatory repair workflow.

Candidate compilation must use the running Python parser without executing the source.

No import, module execution, test execution, or code evaluation belongs in candidate validation.

## 5.3 Candidate-valid suspicious text

If Python candidate compilation succeeds, v1 does not rewrite it merely because it resembles tool syntax.

This is deliberate. Valid Python can still be semantically wrong, and the research proved that downstream Soma lacks intent provenance.

## 5.4 Create-file policy

`create_file` has no baseline validity state.

Initial v1 behavior:

- Python create candidates may receive bounded diagnostics;
- invalid new Python is warning/diagnostic evidence, not a universal hard block;
- no `accept_original` ceremony is required solely because a brand-new file is syntactically invalid;
- no create-file transport repair proposal ships in the first activation.

Revisit only after telemetry or another real incident justifies it.

## 5.5 Unified-diff policy

`unified_diff` receives final candidate validation after diff application.

If a baseline-valid Python file becomes candidate-invalid:

- source preview becomes resolution-required;
- `accept_original` is available;
- no v1 transport repair proposal is synthesized from unified-diff authoring bytes.

The controller may instead issue a corrected diff or explicitly accept the invalid candidate.

---

# 6. Validator resource budgets

Research measured approximately:

```text
~10 KiB   compile + tokenize ~4 ms
~50 KiB   ~23 ms
~200 KiB  ~98 ms
~500 KiB  ~273 ms
~1 MiB    ~1.53 s
```

Changed bytes are not parser cost. Candidate file size is.

Initial implementation constants:

```text
MAX_CANDIDATE_VALIDATION_FILE_BYTES = 512 * 1024
MAX_CANDIDATE_VALIDATION_TOTAL_BYTES = 2 * 1024 * 1024
MAX_CANDIDATE_VALIDATION_FILES = 20
MAX_CANDIDATE_VALIDATION_WALL_SECONDS = 2.0
```

These are validator budgets, not patch-size limits.

Policy on budget exhaustion:

- never crash the preview service;
- stop additional language validation once aggregate budget is exhausted;
- record `budget_skipped` with reason;
- preserve existing repository safety validation;
- do not create a repair proposal for an unvalidated candidate;
- do not silently turn budget exhaustion into syntax validity;
- in v1, budget-skipped language validation is warning evidence rather than a new repository write prohibition.

Tests must monkeypatch/fake timing rather than depend on flaky wall-clock thresholds.

---

# 7. Repair proposal contract

## 7.1 Scope

A v1 repair proposal exists only for a baseline-valid Python modification that became candidate-invalid and for which one exact deletion-only correction passes every mechanical gate.

No insertion, comma synthesis, quote synthesis, indentation repair, formatting repair, AST rewrite, or test-driven repair is permitted.

## 7.2 Initial real-corpus rule set

Implementation begins only with detector families proven by the recovered incidents:

```text
repo_preview.patch.trailing_commit_title.v1
repo_preview.patch.trailing_view.v1
```

Do not generalize from field names such as `expected_sha256`, `commit_description`, or arbitrary JSON fragments until a test corpus/research correction justifies them.

A new detector rule is a reviewed/versioned policy change.

## 7.3 Schema-bound transport context

`server.repo_preview` may pass a small non-secret `PreviewTransportContextV1` into preview construction so detection can compare introduced suffix bytes with the actual parsed request shape/values.

Candidate context may include only fields relevant to deterministic detection, for example:

```text
public_operation
view
commit_title
commit_description present/absent
response_budget_bytes
known outer field vocabulary
```

This context strengthens proposal precision but **does not prove intent**.

Do not persist secrets or unrelated request content merely for repair detection.

## 7.4 Authored-byte provenance requirement

A deletion repair may target only bytes proven to have been introduced by one direct replacement primitive in the current request.

For v1 direct repair primitives:

```text
exact_text
line_range
python_ast
```

Validation/composition must retain bounded provenance sufficient to answer:

```text
which operation introduced this candidate byte span?
what source primitive produced it?
what exact replacement span contains the suspicious suffix?
```

A proposal is forbidden when:

- suspicious bytes pre-existed in baseline source;
- candidate mapping is ambiguous;
- multiple operations make ownership of the suffix ambiguous;
- more than one deletion cut is plausible;
- the repair would touch bytes outside one introduced replacement span.

## 7.5 Python structural gates

For one proposed suffix deletion:

1. original baseline must compile;
2. original candidate must fail compilation;
3. deletion must be exact and deletion-only;
4. repaired candidate must compile;
5. tokenize the repaired candidate;
6. no token may span across the deletion cut;
7. between cut and next token, only horizontal whitespace may occur;
8. the next Python token must be logical `NEWLINE`, not `NL`;
9. no additional repair search is performed after failure of any gate.

Incident A must fail the logical-line gate.

Incident B must pass the logical-line gate.

## 7.6 `PatchRepairProposalV1`

Patch-level proposal shape:

```text
schema_version = "repo_patch_repair_proposal.v1"
proposal_id
rule_id
rule_version
path
operation_index
primitive
original_candidate_sha256
repaired_candidate_sha256
replacement_span_hash
deletion_start_byte
deletion_end_byte
deleted_bytes_sha256
deleted_excerpt_bounded
python_validation_before
python_validation_after
logical_line_gate
repaired_payload_descriptor
created_at
```

Identity domain:

```text
soma.repo_patch.repair_proposal.v1
```

`proposal_id` is derived from stable mechanical material and excludes `created_at`/elapsed timing.

Only one proposal may be exposed by a v1 source preview.

If multiple candidate files or multiple candidate deletion rules would require independent choices, emit no repair proposal and keep `accept_original` or controller retry as the resolution path.

## 7.7 Preserve repaired bytes

The source v4 bundle stores the exact repaired payload bytes as proposal payload material at preview time.

`accept_repair` later copies/verifies those preserved bytes.

It must not recompute the repair from current source text or rerun an open-ended detector.

---

# 8. Bundle version 4 and lifecycle

## 8.1 Why v4

Bundle v3 proves selected payload consistency but has no first-class concept of:

- candidate-language validation;
- non-applicable resolution-required preview;
- repair proposal payload;
- source/child preview linkage;
- explicit candidate-validation override.

These are material semantics. Use bundle version 4.

## 8.2 v4 source preview states

Add explicit managed statuses:

```text
preview_ok
preview_resolution_required
resolved
applied
reverted
failed
rollback_failed
```

Legacy `preview_failed` remains readable for v2/v3 compatibility.

Rules:

```text
preview_ok
  -> applicable

preview_resolution_required
  -> never applicable
  -> resolve_patch allowed

resolved
  -> source preview never applicable
  -> exact child patch identity exposed

applied
  -> only an applicable preview/child may reach this
```

Apply must move from blacklist-style failure checks to an applicability whitelist:

```text
only status == preview_ok may begin a new apply
```

plus existing idempotent handling for `applied` and existing rejection of `reverted`.

This prevents a future unknown/non-applicable status from accidentally falling through to writes.

## 8.3 v4 manifest additions

Candidate shape:

```text
bundle_version = 4
candidate_validation
repair_proposal?
source_patch_id?          # child only
resolution?
  resolution_request_id
  resolution_request_hash
  decision
  proposal_id?
  source_candidate_sha256s
  child_patch_id?         # source after resolution
  resolved_at
```

Do not store full duplicated source bodies in manifest JSON. Continue using bounded payload files/chunks and hashes.

## 8.4 Provenance wording

Do not claim that current managed bundle hashes are an externally immutable cryptographic trust anchor.

They establish internal consistency against the managed manifest/payload set. Existing tests prove a coordinated payload+manifest rewrite can still be internally accepted.

The feature needs auditable provenance, not exaggerated immutability claims.

---

# 9. Resolution semantics and idempotency

## 9.1 Source preview is immutable as evidence

Resolution does not replace source payload bytes.

The source preview preserves:

- original candidate;
- validation evidence;
- proposal evidence if one exists;
- selected decision;
- selected child identity.

## 9.2 Deterministic child preview identity

Reuse the existing patch-ID namespace while making resolution replay converge.

Candidate algorithm:

```text
resolution_request_hash = SHA256(
  "soma.repo_patch.resolution_request.v1\0" +
  canonical_json(
    source_patch_id,
    resolution_request_id,
    decision,
    proposal_id_or_empty,
    source_manifest_identity_hash
  )
)

child_suffix = first 8 lowercase hex of SHA256(
  "soma.repo_patch.resolution_child.v1\0" +
  source_patch_id + "\0" + resolution_request_hash
)

child_patch_id =
  <timestamp prefix copied from source_patch_id> + "_patch_" + child_suffix
```

This preserves the existing patch-ID regex/shape and gives exact replay a deterministic child path.

If the deterministic child path already exists:

- exact matching resolution metadata returns it idempotently;
- differing metadata is a hard collision/conflict and must never be overwritten.

The current namespace already uses 8 hex suffixes; this design does not weaken that existing collision scale.

## 9.3 `accept_repair`

Preconditions:

- source is `preview_resolution_required`;
- exact proposal exists;
- request names exact proposal ID;
- source repository fingerprint still matches;
- source preview HEAD/file preconditions are still current enough to construct an applicable child;
- proposal payload hashes verify.

Child construction:

- copy unchanged source operations except the one exact selected repaired payload;
- preserve commit metadata;
- preserve/recompute diff/statistics from selected child payload;
- preserve candidate validation/proposal provenance;
- mark child `preview_ok` only after all ordinary repository preconditions and selected-payload checks pass;
- record parent/source linkage.

No repair detector is called during selection.

## 9.4 `accept_original`

Preconditions:

- source is `preview_resolution_required`;
- exact original payload still verifies;
- repository safety/preconditions still pass.

Child:

- carries byte-identical original source payload;
- records `candidate_validation_override = accept_original`;
- records resolution identity/source linkage;
- becomes `preview_ok` only because the controller explicitly overrode the candidate-language validation gate.

This override never suppresses other errors.

If stale hashes, path safety, repo binding, operation structure, payload integrity, or other existing checks fail, child creation fails regardless of `accept_original`.

## 9.5 Resolution after source drift

Do not create a child from stale source assumptions.

If Git HEAD/current file hashes required by the source preview no longer match, resolution returns stale/conflict evidence and the controller must build a fresh patch against current source.

Do not silently rebase the old repair proposal.

## 9.6 One source, one selected resolution

After one exact resolution child is durably selected, source status becomes `resolved`.

Exact replay returns the same child.

A conflicting later resolution request must fail rather than create a second competing selected child.

If future product needs multiple alternative children, that is a versioned expansion, not v1 behavior.

---

# 10. Public response and status ergonomics

## 10.1 Patch preview compact response

Extend bounded compact response with small scalar fields:

```text
applicable
candidate_validation_status
resolution_required
repair_available
repair_proposal_id
source_patch_id
selected_child_patch_id
```

Do not dump repaired/original source payloads into compact responses.

For a resolution-required source preview:

```text
ok = false
applicable = false
resolution_required = true
repair_available = true|false
patch_id = source preview ID
```

This preserves the existing intuition that `ok=false` means the preview is not directly applicable while giving the controller a precise recovery path.

## 10.2 Full response

Full preview/status may include bounded:

- validation diagnostic;
- repair rule/proposal ID;
- changed/deleted byte count;
- bounded escaped deleted excerpt;
- original/repaired candidate hashes;
- logical-line gate result;
- available resolution decisions;
- child linkage after resolution.

Never return giant payload bodies simply because repair metadata exists.

## 10.3 `patch_status`

Extend `repo_query(operation="patch_status")` to expose:

```text
bundle_version
applicable
resolution_required
repair_available
repair_proposal_id
source_patch_id
resolution_decision
selected_child_patch_id
candidate_validation_status
```

This allows a disconnected/restarted controller to recover the resolution flow without conversation replay.

---

# 11. Testing philosophy

The implementation is defensive infrastructure and needs adversarial tests, but the full repository suite is not the default validation mechanism.

Use:

- pure validator tests;
- repo-writer managed-bundle tests;
- gateway schema tests;
- public discovery/hash tests when public input changes;
- focused server/repo gateway regressions;
- real recovered incident fixtures;
- deterministic fuzz/property tests with bounded seed/count;
- newline-mode tests including LF and CRLF;
- apply/revert/idempotency tests on disposable repositories.

Run the complete repository suite only at the final source acceptance/activation boundary if targeted evidence cannot close cross-cutting uncertainty.

The historical Agent/Worker full-suite cost remains a reason not to use the full suite ceremonially.

---

# 12. HOLD-0 - Shared-worktree and owner gate

The patch-repair implementation lane is not active while the Agent/Worker implementation has live source/test changes in the same repository.

Entry requires:

1. owner explicitly opens the patch-auto-repair implementation lane;
2. Agent/Worker shared-worktree mutation is complete or at a deliberately stable boundary;
3. no unrelated staged files;
4. exact current HEAD recorded;
5. unrelated parked files identified and protected;
6. no live Soma restart/connector change is implied by opening source implementation.

At planning time protected unrelated content includes at least:

```text
docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md
```

and any then-current Agent/Worker source/test work that has not yet been committed/accepted.

Endpoint: implementation lane explicitly opened; STOP.

---

# 13. P0 - Preserve research and reconcile drift

## P0.1 - Preserve research and implementation plan

When the lane is opened and shared worktree is safe, preserve exactly:

```text
docs/patch-auto-repair-research/iteration-01-current-patch-pipeline-and-repair-feasibility-2026-08-12.md
docs/patch-auto-repair-research/iteration-02-real-failure-corpus-and-tier-a-boundary-2026-08-12.md
docs/patch-auto-repair-research/iteration-03-python-boundary-proof-create-policy-and-provenance-2026-08-12.md
docs/patch-auto-repair-research/iteration-04-fuzzing-impossibility-boundary-and-resolution-flow-2026-08-12.md
docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_IMPLEMENTATION_PLAN_2026-08-12.md
```

One clean local documentation commit only.

Verify:

- no production source enters the commit;
- no Agent/Worker files enter the commit;
- no canonical-memory file enters the commit;
- no push.

Endpoint: research/plan durability; STOP.

## P0.2 - Post-Agent/Worker patch-pipeline drift audit

Research/planning inspected the patch pipeline at `4fd5c327...`.

Before implementation compare current HEAD against that source point for at least:

```text
soma/repo_writer.py
soma/gateway_models.py
soma/server.py
soma/public_tool_metadata.py
soma/public_gateway_inventory.py
soma/cf1_gateway_operation_inventory.py
tests/ covering repo_writer / repo_preview / repo_apply / patch_status
```

Classify relevant differences:

```text
compatible
requires-plan-adjustment
invalidates-research-assumption
unrelated
```

Explicitly re-prove:

- `_validate_operations()` still materializes complete candidate content before bundle write;
- preview bundles still preserve selected payload bytes/hashes;
- `repo_apply` still consumes opaque selected bundle bytes rather than replaying semantic edit intent;
- bundle version/compatibility assumptions remain current;
- public repo preview/apply request topology remains compatible;
- patch status remains recoverable by patch ID;
- no later Agent/Worker work has introduced another candidate validation/repair layer.

If an assumption is invalidated, update the plan reconciliation first and STOP.

Acceptance artifact:

```text
docs/patch-auto-repair-research/P0_2_PATCH_PIPELINE_DRIFT_ACCEPTANCE_<date>.md
```

No production change in this stage.

Endpoint: implementation seams reconciled; STOP.

---

# 14. G1 - Candidate validation foundation

Gate 1 adds deterministic candidate-language evidence only. No repair proposal and no new public input operation yet.

## G1.1 - Pure validation contracts and Python validator

Create:

```text
soma/repo_candidate_validation.py
tests/test_repo_candidate_validation.py
```

Implement:

```text
CandidateValidationV1
CandidateDiagnosticV1
CandidateValidationBudget
validate_python_candidate(...)
```

Freeze v1 schema/version strings and budget constants from this plan.

Tests:

- baseline valid / candidate valid;
- baseline valid / candidate invalid;
- baseline invalid / candidate invalid;
- syntax diagnostic boundedness;
- Unicode;
- LF/CRLF;
- EOF without newline;
- 512 KiB boundary;
- per-preview file/byte budget accounting;
- deterministic budget-skipped results;
- no source execution/import;
- no repository writes.

Endpoint: pure validator proven; repo_writer unchanged; STOP.

## G1.2 - Integrate candidate validation into patch materialization

Modify only the minimum patch-validation seam.

Likely files:

```text
soma/repo_writer.py
tests/test_repo_writer.py or existing focused repo-writer suites
```

After final per-file `new_content` is materialized, attach candidate validation evidence to the validated record.

Do not change applicability yet except in tests behind an internal feature path if necessary.

Prove:

- existing patch diff/newline/hash results unchanged for valid candidates;
- candidate validation sees final composed candidate, not one intermediate op;
- mixed same-file operations are validated once on final candidate;
- budget exhaustion does not affect existing safety checks;
- no worktree mutation occurs during preview validation.

Endpoint: internal validation evidence exists; behavior still compatibility-safe; STOP.

## G1.3 - Bundle v4 validation metadata

Extend `_write_preview_bundle` to write v4 for new feature-aware previews while keeping v2/v3 read/apply compatibility.

Store bounded candidate validation metadata alongside selected payload descriptors.

Do not add repair proposal or resolution yet.

Update bundle/read/status tests to prove:

- v2/v3 old bundles remain readable/applicable;
- v4 preview payload hash checks equal v3 strength;
- validation metadata cannot alter selected payload identity;
- candidate validation diagnostics are bounded;
- coordinated manifest/payload consistency semantics are described accurately, not overstated.

Endpoint: v4 foundation proven; no repair behavior; STOP.

## G1.4 - Gate 1 acceptance

Run focused candidate-validator, repo-writer preview/bundle, apply/revert compatibility suites plus Ruff/format/EOL diagnostics for touched files.

Write:

```text
docs/patch-auto-repair-research/G1_CANDIDATE_VALIDATION_ACCEPTANCE_<date>.md
```

No public schema change, restart, connector refresh, or push.

Endpoint: candidate validation foundation accepted; STOP.

---

# 15. G2 - Deterministic transport repair proposal

Gate 2 detects the real transport-leak family and stores one mechanically proven proposal. It still does not allow the source preview to apply.

## G2.1 - Authored-span provenance

Extend patch composition metadata so direct replacement primitives retain bounded authored-span provenance sufficient for deletion ownership.

Supported in v1:

```text
exact_text
line_range
python_ast
```

Do not expose internal compatibility aliases as separate policies.

Tests must prove suspicious bytes cannot be deleted when they:

- existed in baseline;
- came from an ambiguous multi-operation composition;
- cross an authored replacement boundary;
- cannot be mapped exactly to one operation.

Endpoint: provenance only; no detector; STOP.

## G2.2 - Versioned detector rules for the two recovered incidents

Add pure detector logic in the candidate-validation module or a small sibling module if separation is clearer.

Implement only:

```text
repo_preview.patch.trailing_commit_title.v1
repo_preview.patch.trailing_view.v1
```

Use the recovered incidents from Iteration 2 as exact positive fixtures.

Add intentional-lookalike negative/ambiguity fixtures.

A detector hit alone never creates applicable repaired bytes.

Endpoint: exact corruption candidates detected; STOP.

## G2.3 - Deletion candidate + Python logical-line proof

Implement the research gate exactly:

```text
original candidate fails
-> exact one deletion
-> repaired candidate compiles
-> token does not span cut
-> horizontal whitespace only until next token
-> next token == NEWLINE
```

Required tests:

- Incident B accepted as repair-proposal candidate;
- Incident A rejected because newline is `NL`/logical statement remains open;
- adjacent implicit string concatenation trap;
- function call continuation;
- list/dict/set/tuple continuation;
- comprehensions;
- operators;
- attributes/subscripts;
- explicit backslash continuation;
- comments/semicolon boundaries;
- f-strings;
- Unicode;
- CRLF;
- EOF variants.

Carry forward the deterministic fuzz/adversarial corpus with a fixed seed and bounded runtime suitable for CI.

Endpoint: repair structural proof exists; no preview selection; STOP.

## G2.4 - `PatchRepairProposalV1` and proposal payload preservation

Create one patch-level proposal only when every v1 condition is met.

Persist:

- proposal identity and rule version;
- original/repaired hashes;
- bounded deletion evidence;
- exact repaired payload bytes/chunks;
- structural gate results.

If proposal creation fails at any stage, preserve the original validation failure and emit no proposal.

No source preview becomes applicable merely because a proposal exists.

Endpoint: proposal is durable evidence; STOP.

## G2.5 - Resolution-required source preview state

When a baseline-valid Python modification becomes invalid:

```text
status = preview_resolution_required
applicable = false
```

If a repair proposal exists, expose it.

If no repair proposal exists, `accept_original` will be the only future resolution choice.

Strengthen apply to whitelist fresh `preview_ok` only, while preserving idempotent `applied` handling and legacy bundle compatibility.

Tests must prove direct apply of a resolution-required source preview is impossible.

Endpoint: unsafe candidate is mechanically stopped before worktree mutation; STOP.

## G2.6 - Gate 2 acceptance

Run focused validator/proposal/fuzz/bundle/apply-negative suites.

Write:

```text
docs/patch-auto-repair-research/G2_REPAIR_PROPOSAL_ACCEPTANCE_<date>.md
```

No public input-schema change yet if resolution remains internal/unwired at this gate.

Endpoint: detection/proposal accepted; STOP.

---

# 16. G3 - Explicit resolution and child previews

Gate 3 makes the deterministic repair ergonomic for controllers while preserving intent authority.

## G3.1 - Internal resolution service

Implement an internal `resolve_patch_preview(...)` service in `repo_writer.py` or a small dedicated helper module.

Inputs follow the planned public contract but remain internal initially.

Implement deterministic resolution request hash and deterministic child patch ID.

Tests:

- exact replay -> same child;
- request-ID/content conflict -> fail;
- deterministic child collision with different content -> fail closed;
- unknown source patch -> fail;
- wrong repository -> fail;
- stale source -> fail;
- source not resolution-required -> fail;
- source already resolved -> exact replay only.

Endpoint: internal resolution lifecycle proven; STOP.

## G3.2 - `accept_repair`

Implement selection of exact stored proposal payload.

Prove with instrumentation/mocking that selection does **not** call the repair search/detector again.

Child must preserve:

- parent/source patch ID;
- proposal ID;
- resolution request ID/hash;
- selected repaired payload hash;
- commit metadata;
- ordinary repo/hash/newline/diff evidence.

Child is applicable only after all ordinary preconditions pass.

Endpoint: deterministic repair can become a normal child preview; STOP.

## G3.3 - `accept_original`

Implement exact original-payload child selection with candidate-validation override evidence.

Negative tests prove it cannot bypass:

- stale expected file hash;
- changed Git HEAD where current preview rules require matching;
- wrong repo fingerprint;
- path escape;
- symlink/binary restrictions;
- malformed operation;
- payload hash mismatch;
- patch file/count/size limits;
- any other incumbent safety check.

Endpoint: intentional-invalid-source escape hatch proven narrow; STOP.

## G3.4 - Source/child lifecycle and patch-status recovery

Extend `get_patch_status` / internal status evidence for v4 source and child previews.

Prove restart/reconnect recovery from managed files alone:

- source resolution-required -> proposal/choices discoverable;
- resolved source -> child discoverable;
- child -> source/decision discoverable;
- child apply/revert lifecycle independent and coherent;
- source never appears applied because child was applied.

Endpoint: durable resolution continuity proven; STOP.

## G3.5 - Gate 3 acceptance

Run focused source/child/idempotency/staleness/apply/revert/status tests.

Write:

```text
docs/patch-auto-repair-research/G3_RESOLUTION_PREVIEW_ACCEPTANCE_<date>.md
```

Keep public `resolve_patch` unwired until the next gate so internal semantics are accepted before public schema changes.

Endpoint: internal resolution accepted; STOP.

---

# 17. G4 - Public gateway integration without topology growth

## G4.1 - Add `RepoResolvePatchPreview`

Modify:

```text
soma/gateway_models.py
```

Add the exact discriminated request variant specified in section 4.

Add it to `RepoPreviewRequest`.

Do not change `RepoApplyRequest`.

Schema tests must prove all cross-field rules and reject extra fields under existing GatewayModel policy.

Endpoint: model contract exists; server not yet wired if micro-stage separation is useful; STOP.

## G4.2 - Wire `repo_preview(resolve_patch)`

Modify the minimum server/wrapper path.

Expected files may include:

```text
soma/server.py
soma/repo_writer.py
```

Wire to the already accepted internal resolution service.

Extend bounded preview response with the scalar resolution fields from section 10.

No new public tool.

Endpoint: public source path wired; no runtime restart; STOP.

## G4.3 - Patch-status public projection

Extend `repo_query(patch_status)` compact/full projections with bounded resolution continuity fields.

Do not expose giant original/repaired payload bodies.

Endpoint: controller can recover resolution state through existing read surface; STOP.

## G4.4 - Candidate-B metadata and inventory identity

Update only the human-facing `repo_preview` metadata necessary to describe the broadened preview purpose.

Do not alter unrelated tool descriptions.

Update operation inventory/schema tests required by the `repo_preview` input change.

Expected topology:

```text
32 public tools before
32 public tools after
```

Expected schema identity change is isolated to the `repo_preview` operation/tool input surface plus descriptor metadata.

Endpoint: source descriptor/schema identity coherent; STOP.

## G4.5 - Gate 4 acceptance

Run:

- gateway model tests;
- repo preview/apply/status gateway tests;
- public discovery/schema identity tests;
- operation inventory tests;
- Candidate-B metadata parity tests;
- direct repo-writer regression tests.

Capture exact new:

```text
public_schema_hash
public_descriptor_hash
operation_inventory_hash
repo_preview operation schema hash
```

and prove unrelated tool input schema hashes unchanged.

Write:

```text
docs/patch-auto-repair-research/G4_PUBLIC_GATEWAY_SOURCE_ACCEPTANCE_<date>.md
```

No restart or connector Refresh.

Endpoint: public source accepted, not live; STOP.

---

# 18. G5 - Apply/revert compatibility hardening

This gate exists specifically to prove the new preview intelligence did not leak into apply authority.

## G5.1 - Repair-blind apply proof

Tests/instrumentation must prove `apply_previewed_repo_change`:

- does not import/call repair detectors;
- does not tokenize/compile source;
- does not choose between original/repaired candidates;
- accepts only selected `preview_ok` bundle payload;
- still verifies repo fingerprint, HEAD/file hashes, path safety, payload hash, limits and rollback evidence.

## G5.2 - Legacy bundle compatibility

Test actual fixture bundles for versions 2 and 3.

Prove:

- old `preview_ok` bundles remain applicable under their existing semantics;
- old `preview_failed` remains rejected;
- v4 source resolution states are rejected by apply;
- v4 selected child is applicable;
- unsupported future bundle version fails closed.

## G5.3 - Revert/rollback

Prove:

- applied repaired child can revert normally;
- applied accept-original child can revert normally;
- source preview is not itself revertable as an applied change;
- rollback on write failure remains byte-correct;
- source/child provenance survives child revert.

## G5.4 - Gate 5 acceptance

Write:

```text
docs/patch-auto-repair-research/G5_APPLY_COMPATIBILITY_ACCEPTANCE_<date>.md
```

Endpoint: authority separation accepted; STOP.

---

# 19. G6 - Format expansion and intentionally deferred formats

Do not broaden repair synthesis merely because parser libraries exist.

## G6.1 - JSON complete-document validator

Add JSON candidate validation for complete `.json` documents.

Policy:

- baseline valid -> candidate invalid can become resolution-required;
- no transport auto-repair proposal initially unless a dedicated rule is separately justified;
- `accept_original` remains the explicit validation override;
- create-file remains diagnostic-first.

Tests cover encoding, duplicate-key policy documentation, large files, and parser diagnostics.

## G6.2 - TOML capability gate

Soma project compatibility currently includes Python versions where stdlib `tomllib` may not be universally present.

Do not add a new runtime dependency casually.

At implementation time choose one of:

```text
A. enable TOML validation only when supported runtime parser exists;
B. use an already-declared dependency if one exists after drift audit;
C. defer TOML until minimum Python/runtime policy changes.
```

Record the decision in Gate 6 acceptance.

## G6.3 - XML/YAML remain deferred

Do not ship XML/YAML hard validation in this lane unless a targeted follow-up explicitly proves parser/security/resource policy.

YAML especially must not become a broad dependency/loader surface merely for patch ergonomics.

## G6.4 - Gate 6 acceptance

Write:

```text
docs/patch-auto-repair-research/G6_FORMAT_VALIDATION_ACCEPTANCE_<date>.md
```

Endpoint: bounded format policy accepted; STOP.

---

# 20. G7 - Evidence and telemetry period

The goal is evidence for future refinement, not surveillance or transcript logging.

## G7.1 - What to count

Use existing managed preview/status evidence where possible; no database migration is required merely for counters.

Useful aggregate fields/events:

```text
candidate validations attempted
candidate validation valid/invalid/budget-skipped
repair proposals emitted by rule_id
accept_repair decisions
accept_original decisions
source previews abandoned without resolution
resolution conflicts/stale failures
validation elapsed buckets
candidate size buckets
```

Do not store full user/model source bodies in telemetry beyond the managed patch payload already required for repository preview semantics.

## G7.2 - False-positive evidence

`accept_original` after a repair proposal is a useful signal that a proposed corruption shape may have been intentional.

It is not automatically proof that the detector was wrong; record it as a review signal.

A future detector-rule expansion requires real evidence, not intuition.

## G7.3 - Future silent/proven automatic resolution

Do not add silent Soma auto-repair after this telemetry period unless the **input contract itself changes** to preserve trusted transport origin/provenance before parsing ambiguity is lost.

No amount of downstream regex confidence replaces missing provenance.

If a future transport provides trusted origin metadata, research that exact contract separately before changing the invariant.

Endpoint: observability policy accepted; STOP.

---

# 21. G8 - Source release acceptance

Before any live activation:

1. run all focused patch validator/repo-writer/gateway/bundle/revert/status suites;
2. run the fixed real-incident corpus;
3. run bounded deterministic fuzz/adversarial Python tests;
4. run public schema/descriptor/inventory identity checks;
5. run Ruff/format/type checks used by the repo for touched files;
6. run `git diff --check`;
7. inspect newline diagnostics on every touched existing file;
8. verify no Agent/Worker/canonical-memory files entered the patch-repair commit accidentally;
9. independently inspect the exact commit range before acceptance.

Run the full repository suite only if focused coverage cannot establish compatibility or if the controller decides the public-schema release gate requires that final confidence. Do not run it ceremonially.

Create final source acceptance:

```text
docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_SOURCE_ACCEPTANCE_<date>.md
```

Then one local selected-file commit containing only the accepted lane.

No push.

Source verdict vocabulary:

```text
SOURCE ACCEPTED, NOT LIVE ACTIVATED
BLOCKED
FAILED
```

Endpoint: accepted local source commit; STOP.

---

# 22. A1 - Live activation gate (owner authorization required)

Source acceptance does not authorize runtime activation.

Before activation require explicit owner authorization for:

- Soma restart/reload method chosen for this source change;
- connector Refresh after the served public input schema changes.

## A1.1 - Pre-activation identity freeze

Record old live:

```text
server_build_hash
schema_hash
capability_epoch
operation_inventory_hash
public_schema_hash
public_descriptor_hash
discovery_cache_generation
repo_preview operation schema hash
public tool count
```

## A1.2 - Activate Soma source

Use only the owner-authorized restart/reload path.

Do not combine with unrelated runtime maintenance.

## A1.3 - Post-activation served-descriptor verification

Before connector Refresh verify live Soma serves:

- exactly 32 public tools;
- `repo_preview` includes `resolve_patch` with exact accepted schema;
- `repo_apply` public input remains unchanged;
- Candidate-B metadata for `repo_preview` matches source;
- unrelated tool input schemas remain unchanged;
- new public/schema/descriptor identities match source acceptance.

## A1.4 - Connector Refresh

Because public input schema intentionally changed, perform one owner-authorized connector Refresh after server identity is correct.

Then verify `capability_identity` convergence and no restart/repair recommendation remains.

## A1.5 - Safe live smoke

Use a disposable/non-owner-content test repository or another explicitly safe fixture path.

Smoke sequence:

```text
valid patch -> normal preview still works
malformed Incident-B-shaped patch -> resolution_required + proposal
resolve accept_repair -> child preview
patch_status -> source/child linkage
apply only if fixture mutation is explicitly authorized
```

Do not manufacture malformed source in the real Soma repository merely to prove the feature live.

Endpoint: live feature accepted; STOP.

---

# 23. Acceptance criteria for the whole implementation

The lane is complete only when all of the following are proven.

## Functional

- baseline-valid Python candidate regression is detected before apply;
- Incident B produces one deterministic repair proposal;
- Incident A does not produce an unsafe repair proposal;
- controller can select exact proposal with one resolution call;
- controller can explicitly accept original invalid candidate;
- source preview cannot apply;
- selected child can use normal apply/revert lifecycle;
- exact resolution replay converges;
- stale/conflicting resolution fails closed.

## Authority

- Soma never decides caller intent from suspicious bytes alone;
- no model/LLM exists in repair path;
- `accept_original` bypasses only candidate-language validation;
- `repo_apply` stays repair-blind;
- provider/control-like text is never deleted from an applicable preview without explicit resolution.

## Durability

- original candidate evidence survives resolution;
- proposal evidence survives resolution;
- source -> child linkage survives restart/reconnect;
- applied/reverted child remains traceable to source decision;
- old v2/v3 bundles remain compatible.

## Resource safety

- validator budgets are enforced independently of changed-byte limits;
- budget exhaustion is bounded and observable;
- parser failures never crash the service;
- no source code is executed during validation.

## Public UX

- no new public tool is added;
- `repo_preview` clearly advertises resolution capability;
- compact responses make `resolution_required` and `repair_available` obvious;
- patch status allows recovery without chat transcript dependence;
- controller can make repair selection without owner ceremony when its intent is already known.

## Compatibility

- unrelated repo preview/apply/remove/create/cleanup behavior remains intact;
- public tool count stays 32;
- only intended repo-preview schema/metadata identity moves;
- no hidden connector/runtime activation happens during source implementation.

---

# 24. Required negative tests

The feature is not accepted without explicit tests proving it refuses these cases.

```text
candidate compiles successfully but contains suspicious transport-looking text
-> no repair

baseline-invalid Python
-> no syntax-regression repair assumption

Incident A adjacent-string trap
-> no repair proposal

more than one possible deletion cut
-> no repair proposal

suspicious bytes existed in baseline
-> no repair proposal

suspicious bytes cross replacement ownership boundary
-> no repair proposal

multiple ambiguous operations contribute to suffix
-> no repair proposal

unified_diff candidate invalid
-> no repair proposal in v1

create_file invalid Python
-> diagnostic only in initial v1 policy

accept_repair with wrong proposal_id
-> reject

accept_repair when no proposal exists
-> reject

accept_original carrying proposal_id
-> reject

resolution request replay with changed decision
-> conflict

source HEAD/hash stale before resolution
-> reject

source preview direct apply while resolution_required/resolved
-> reject

accept_original against wrong repo/path/symlink/stale hash
-> reject

unsupported bundle version
-> fail closed
```

---

# 25. Real incident regression fixtures

Preserve both recovered incidents as first-class regression cases rather than rewriting them into generic toy examples only.

## Incident A

Source:

```text
soma/company_kernel/__init__.py
```

Observed leak family:

```text
commit_title
```

Required regression:

- original malformed candidate fails Python compilation;
- obvious suffix deletion can compile;
- logical-line proof rejects the repair because deletion cut is not at a Python logical `NEWLINE` boundary;
- no repair proposal emitted.

This permanently guards the research counterexample.

## Incident B

Source:

```text
tests/test_company_kernel_schema_models.py
```

Observed leak family:

```text
view
```

Required regression:

- malformed candidate fails;
- exact deletion-only repaired candidate compiles;
- deletion cut passes logical `NEWLINE` gate;
- exactly one proposal emitted;
- proposal bytes/hash are stable;
- no worktree write occurs before resolution/apply.

The fixtures may use minimized source excerpts if exact repository historical bytes are separately preserved in research evidence, but the structural conditions must remain faithful.

---

# 26. Implementation-agent micro-stage discipline

Use the same discipline as the Agent/Worker lane.

For Luna Max or any coding agent:

```text
Execute <exact stage ID and title> only.
Verify starting HEAD/worktree first.
Read the required source/research set.
Modify only authorized paths.
Run only exact stage validation.
Report observations as:
  bug
  implementation-friction
  research-assumption-invalidated
  platform-change
  unrelated
STOP before the next stage.
```

Never send a generic `continue` instruction.

If source reality contradicts this plan:

```text
STATUS: BLOCKED
expected
observed
affected invariant
minimal evidence
safest options
STOP
```

Do not weaken a safety gate or expected hash merely to make a test pass.

---

# 27. Global prohibitions

Unless an exact later stage explicitly authorizes it:

- no push;
- no Soma restart;
- no connector Refresh;
- no wiki refresh;
- no canonical-memory changes;
- no Agent/Worker changes;
- no database migration solely for repair telemetry;
- no LLM/model repair service inside Soma;
- no automatic syntax/logic synthesis;
- no test-driven source mutation by the repair layer;
- no auto-formatting as repair;
- no silent deletion of suspicious source bytes;
- no new public repair tool;
- no broad XML/YAML parser dependency;
- no global line-ending normalization;
- no full repository suite by default;
- no claim that managed preview hashes are an external immutable trust anchor.

---

# 28. Deferred ideas

The following are deliberately outside v1.

## Trusted upstream provenance and truly silent repair

If a future tool transport preserves cryptographically/trust-bound provenance that proves exact characters originated from outer control serialization rather than authored source content, research that input contract separately.

Only such a boundary could justify reconsidering silent automatic repair without semantic guessing.

## Semantic code repair

Wrong logic, failing tests, wrong API use, type errors, missing commas, bad architecture, formatting preferences and similar issues remain controller/coding-agent responsibilities.

## General unified-diff repair

Deferred until real evidence justifies mapping candidate corruption back into diff-authored bytes.

## Create-file auto-repair

Deferred because there is no baseline-validity comparator and intentionally invalid files are legitimate.

## Multiple simultaneous repair proposals

V1 exposes at most one deterministic proposal. Multi-proposal resolution would need a more complex selection contract and is not justified by the two-incident corpus.

## XML/YAML hard validation

Deferred until parser/resource/security policy is explicitly designed.

---

# 29. Expected implementation sequence

```text
HOLD-0
  shared-worktree + owner opening gate

P0.1
  preserve 4 journals + this plan

P0.2
  post-Agent/Worker patch-pipeline drift audit

G1
  candidate validation foundation + bundle v4

G2
  real-corpus detector + deletion proof + durable proposal

G3
  accept_repair / accept_original -> deterministic child preview

G4
  public repo_preview(resolve_patch) + patch_status + metadata/schema identity

G5
  prove repo_apply/revert compatibility and repair blindness

G6
  JSON validation + TOML capability decision; XML/YAML deferred

G7
  bounded evidence/telemetry policy

G8
  source release acceptance + local selected-file commit

A1
  owner-authorized runtime activation + connector Refresh + safe live smoke
```

No stage automatically authorizes the next one.

---

# 30. Final architecture

The completed feature should look like this:

```text
ChatGPT / controller
      |
      | repo_preview(patch)
      v
Soma repository preview authority
      |
      +-- existing repo/path/hash/edit validation
      |
      +-- materialize exact candidate bytes
      |
      +-- bounded language validation
      |
      +-- exact transport-shaped detector
      |
      +-- deterministic deletion proposal
      |      only when structural proof passes
      |
      +------ source preview -----------------------+
      |                                             |
      | preview_ok                                  | preview_resolution_required
      |                                             |
      |                                             v
      |                                      controller decides intent
      |                                      /                    \
      |                              accept_repair          accept_original
      |                                      \                    /
      |                                       new child preview
      |                                              |
      +----------------------------------------------+
                                                     |
                                                     v
                                              repo_apply
                                           opaque selected bytes
                                                     |
                                                     v
                                             atomic worktree write
                                                     |
                                                     v
                                               rollback/revert
```

The key property is not that Soma becomes clever enough to guess what the model meant.

The key property is that Soma becomes good enough to catch a predictable mechanical mistake, prove one safe candidate correction where possible, preserve both possibilities, and let the controller resolve intent before any repository mutation occurs.

That is the intended boundary:

```text
Soma detects and proves mechanics.
The controller owns intent.
repo_apply executes selected bytes.
```

Status after plan synthesis:

```text
IMPLEMENTATION PLAN READY
HOLD until owner opens the lane and the shared Agent/Worker worktree is at a safe boundary.
```
