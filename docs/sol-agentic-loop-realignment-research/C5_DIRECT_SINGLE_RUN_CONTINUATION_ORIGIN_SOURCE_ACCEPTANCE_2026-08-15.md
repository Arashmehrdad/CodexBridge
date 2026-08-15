# C5 Direct Single-Run Continuation Origin - Source Acceptance

Date: 2026-08-15
Status: SOURCE ACCEPTED - NOT LIVE ACTIVATED
Roadmap gate: C5
Base accepted gate: C4 at `c8ae1ad16ced068ce4bad61cd1c200549a8d1e93`
Implementation commit: `17d802b5447c520ede00c7a7bac9eadbe6d8122b`

## 1. Scope

C5 adds atomic, recoverable continuation-origin association to the F1 direct single-Run paths only:

- `run_start.powershell`
- `run_start.remote_powershell`
- `run_start.hermes_companion`

The following remain intentionally excluded in v1:

- `run_start.powershell_group`
- `run_start.hermes_service`

C5 does not add a gateway, operation, semantic planner, reasoning phase, model router, Skill router, or alternative Run authority.

The canonical Run remains the existing durable Run record. The continuation effect link records origin only.

## 2. Governing architectural rule

The Sol / ChatGPT controller remains the reasoning agent.

Soma remains mechanical infrastructure:

- durable Run identity
- idempotent admission
- repository locking where already required
- continuation context revision validation
- immutable origin association
- crash recovery
- retrieval and evidence

`continuation_context_ref` is revision identity and provenance context. It is not authorization, ownership, a reasoning lease, or permission to execute.

## 3. F1 identity remains general-purpose

C5 does not change the F1 logical Run request hash domain.

`logical_run_request_id + request_hash` continues to identify the general effect request.

Continuation origin is enforced separately through the immutable `continuation_effect_links` row.

This preserves the audited distinction:

- F1 request identity = effect identity / replay identity
- C5 effect link = immutable continuation origin

## 4. Association requires stable logical Run identity

C5 requires `logical_run_request_id` whenever `continuation_context_ref` is supplied.

Reason: the mandatory replay contract must distinguish all of the following for the same logical request:

1. same request + same origin -> replay
2. originally unassociated + retry adds origin -> conflict
3. originally associated + retry omits origin -> conflict
4. originally associated + retry changes origin -> conflict

Without a durable logical Run request identity, those retry semantics cannot be made recoverable without inventing a second Run identity mechanism.

Unkeyed Run starts remain unchanged when no continuation context is supplied.

Keyed F1 Run starts remain unchanged when no continuation context is supplied.

## 5. Atomic reservation contract

For a new keyed Run with `continuation_context_ref`, C5 extends the existing F1 `BEGIN IMMEDIATE` admission transaction.

The mechanical sequence is:

1. normalize the supplied context revision identity
2. validate the logical Run request and request hash
3. resolve the current continuation contract revision
4. require that revision to be current
5. require continuation lifecycle `open`
6. acquire the existing repository operation lock when that Run path requires one
7. reserve the canonical Run in `launch_pending`
8. bind existing repository-lock ownership when required
9. insert the immutable `continuation_effect_links` Run-origin row
10. commit the shared SQLite transaction
11. materialize existing F1 launch artifacts
12. launch through the existing JobManager worker path

No SQLite transaction is held while the executable runs.

## 6. Replay contract

Existing keyed Run replay is checked before attempting a new continuation write.

For an already accepted Run:

- same request hash + same stored continuation origin -> replay the same Run
- same request hash + Run originally unassociated + supplied origin -> `continuation_origin_conflict`
- same request hash + Run originally associated + omitted origin -> `continuation_origin_conflict`
- same request hash + different origin -> `continuation_origin_conflict`
- different F1 request hash -> existing F1 logical request hash conflict semantics

A same-origin replay remains valid after the continuation later closes because it is replay of an already accepted immutable effect, not authorization for a new write.

No origin can be attached after the fact.

## 7. Crash and rollback semantics

### Before transaction commit

If continuation validation fails, no Run is reserved and no repository lock is retained.

If effect-link insertion fails after Run reservation inside the transaction, the Run reservation and repository lock ownership roll back with the link.

### After transaction commit, before launch

The canonical Run and its immutable continuation origin are both already durable.

A synthetic hard-crash proof demonstrated:

- Run persisted as `launch_pending`
- one origin link persisted
- startup reconciliation reused the same Run
- lease generation advanced through existing F1 recovery
- no second Run was created

### Lost response / later replay

The same logical request and same origin returns the existing Run/link.

This remains true if the continuation has since been completed, because the replay does not create a new effect or mutate origin.

## 8. Public input contract

`continuation_context_ref` is added only to:

- `LocalPowerShellStart`
- `RemotePowerShellStart`
- `HermesCompanionStart`

Each model requires `logical_run_request_id` when continuation origin is supplied.

The field description explicitly states that it records immutable mechanical origin and is not an authorization token.

Strict model tests prove that `continuation_context_ref` is rejected on:

- `powershell_group`
- `hermes_service`

The Hermes companion path remains lock-free exactly as before; C5 adds only the continuation-origin row.

## 9. Continuation store addition

C5 adds one connection-scoped mechanical lookup:

`ContinuationStore.find_effect_link_in_connection(...)`

Properties:

- returns the immutable Task/Run origin when present
- does not create continuation state
- returns `None` if continuation tables do not exist
- allows ordinary F1 replay to remain independent from continuation initialization

No new continuation table or migration is introduced by C5.

## 10. Public topology and identity

Fresh source discovery after registering the dynamic knowledge gateways converged cleanly.

Tool count: `36`

Operation schema count: `275`

Public schema hash:

`d0f8937730423a528e11dd6ad3a434402974f7aacb64e33a181ec3a28b5f64ec`

Public descriptor hash:

`2041e44b4eb1ffb4f03a15f99a29521f0e8ad52e64e299b23e3c58255e6ac3bd`

Operation inventory hash:

`07724723b5bfd4ebc2d6cef405bd39d8d0dfeece70a61c42f0c9e297c0f80e30`

Aggregate public input-schema digest:

`c5b2db1add23790ece8b208fa6263f047369601d5fd87b844b68507a9031a121`

Changed C5 single-Run operation schema hashes:

- `run_start.powershell`: `72660cbb255664cc1aa6e6825da0436761728d7d62beff74178e8f6e507f9a5f`
- `run_start.remote_powershell`: `56414bda30c2d8624b0b1c4f249854137cf3951eecf8fc3d59fcfb718dd0f591`
- `run_start.hermes_companion`: `bb2aeaeb72b5ce23b401b5840c7827b5c5a0d4e5e9bf91b6879bedc9dbe946e0`

Explicitly unchanged excluded operation hashes:

- `run_start.powershell_group`: `683c294968eb5719b5d19411d6928f7e407be0596cd389a7dc51219276cc753a`
- `run_start.hermes_service`: `17ffb09310432c11e6666ad3a0c7bb23d014dd9263b03fc31d8945668c10265a`

Therefore C5 changes no gateway count and no operation count. Only the three authorized single-Run input schemas move.

## 11. Test evidence

### 11.1 Exploratory import-cycle failure

Run:

`20260815T141114Z_executable_profile_fb9d2ec4`

The first compatibility run failed during collection before behavioral tests executed.

Cause:

A top-level `JobManager -> soma.continuations.store` import traversed `soma.continuations.__init__ -> service -> tasks -> TaskManager -> JobManager`, producing a circular import.

Resolution:

Continuation persistence imports were made lazy:

- `TYPE_CHECKING` type import only
- runtime `ContinuationStore` import inside the lazy property
- continuation exception/store imports local to the keyed Run admission function

No semantic or persistence contract changed in the fix.

### 11.2 F1 backward-compatibility checkpoint

Run:

`20260815T141203Z_executable_profile_28702db6`

Result:

- `8 passed`
- Ruff PASS
- `git diff --check` PASS

This proves the existing F1 keyed-Run behaviors remained intact after the import-cycle correction.

### 11.3 C5 focused mechanical gate

Run:

`20260815T141423Z_executable_profile_f4fffa2e`

Result:

- `11 passed`
- Ruff PASS
- `git diff --check` PASS

Focused cases include:

- context requires logical Run request identity
- same local request/context replays one Run/link
- unassociated Run cannot gain origin later
- associated Run cannot omit origin later
- associated Run cannot change origin later
- stale context rejected before Run/lock
- closed context rejected before Run/lock
- six-way concurrent identical start -> one Run/link/launch
- link insertion failure rolls back Run and repository lock
- post-commit crash preserves Run/link and existing startup recovery
- remote PowerShell replay/origin
- Hermes companion lock-free replay/origin

### 11.4 First broad public checkpoint

Run:

`20260815T141535Z_executable_profile_dc45bfed`

Result before expected fixture updates:

- `400 passed`
- `3 failed`

The three failures were classified as C5 public-contract fixture movement only:

1. remote PowerShell dispatch expectation lacked default `continuation_context_ref: ""`
2. public schema fixture still contained the C4 hash
3. metadata schema fixture still contained the C4 hash

No C5 mechanical behavior failed.

The run measured the new public schema hash:

`d0f8937730423a528e11dd6ad3a434402974f7aacb64e33a181ec3a28b5f64ec`

### 11.5 Independent aggregate input digest measurement

Run:

`20260815T142010Z_executable_profile_eedd4588`

Result:

- `18 passed`
- `1 failed`

The sole failure was the intentionally stale aggregate input-schema digest fixture and measured:

`c5b2db1add23790ece8b208fa6263f047369601d5fd87b844b68507a9031a121`

### 11.6 Targeted public gate after fixture update

Run:

`20260815T142127Z_executable_profile_348d04e4`

Result:

- `308 passed in 170.51s`
- Ruff PASS
- `git diff --check` PASS

### 11.7 Final cross-authority acceptance

Run:

`20260815T142443Z_executable_profile_ab58857c`

Result:

- `536 passed in 218.63s`
- Ruff PASS
- `git diff --check` PASS

Coverage included:

- RunStore
- JobManager
- continuation persistence
- continuation schema coexistence
- continuation service
- continuation public gateway
- canonical Task plane
- ProjectScope foundation
- Hermes companion
- Hermes concurrency
- public gateway models
- public descriptor identity
- public metadata identity
- public gateway inventory
- CF1 operation inventory
- flat MCP input contract

No worker recovery, stale lease, or launch churn occurred during the final acceptance run.

## 12. Identity-probe correction

A preliminary read-only identity probe sampled `server.mcp` before the two dynamically registered knowledge gateways were added, so its aggregate tool count/schema/descriptor represented only 34 tools.

That aggregate was rejected as acceptance evidence.

The final identity probe explicitly called `register_knowledge_tools(server.mcp)` before enumerating actions.

Authoritative C5 source identity evidence run:

`20260815T142911Z_executable_profile_9c8859be`

It reported:

- 36 tools
- 275 operation schemas
- converged discovery
- empty operation-schema error
- the hashes recorded in section 10

## 13. No-second-brain proof

Run:

`20260815T142937Z_executable_profile_19760829`

Result:

`C5_NO_SECOND_BRAIN_SCAN_OK`

The added C5 source contains none of the forbidden semantic machinery scanned for, including:

- recommended next action
- next-step state
- reasoning phase
- active Skill routing
- semantic planner
- reasoning lease
- semantic workflow DAG

C5 is mechanical provenance and idempotency only.

## 14. Commit-scope proof

Implementation commit:

`17d802b5447c520ede00c7a7bac9eadbe6d8122b`

C4 -> C5 implementation range:

- exactly 10 files
- 567 insertions
- 4 deletions

Files:

1. `soma/continuations/store.py`
2. `soma/gateway_models.py`
3. `soma/hermes_companion_client.py`
4. `soma/job_manager.py`
5. `soma/server.py`
6. `tests/test_hermes_companion_client.py`
7. `tests/test_job_manager.py`
8. `tests/test_public_descriptor_identity.py`
9. `tests/test_public_metadata_wiring.py`
10. `tests/test_tool_gateway_models.py`

No concurrent `docs/soma-improvement-research/*` file entered the implementation commit.

## 15. Live-activation boundary

C5 is accepted as source only.

This gate did not:

- restart Soma
- reload Soma modules
- refresh the connector
- repair the operation contract
- push Git
- invoke Codex
- invoke a model subagent
- invoke a secondary reasoning model

The running Soma service remains on its earlier pre-F1 public runtime until a later rollout gate explicitly activates the accumulated source changes.

## 16. Acceptance verdict

C5 satisfies the audited implementation contract.

Direct F1 keyed single-Run effects can now carry one immutable continuation origin with atomic Run/link reservation, deterministic replay/conflict semantics, rollback before commit, durable recovery after commit, and no semantic authority added to Soma.

Verdict: **C5 SOURCE ACCEPTED - NOT LIVE ACTIVATED**

Next mandatory gate: **S1 - portable Skill persistence foundation**.

S1 is not started by this acceptance.
