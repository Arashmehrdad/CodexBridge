# C3 Public Continuation Gateway - Source Acceptance

Date: 2026-08-15
Programme: Sol semantic continuation + Soma portable Skill layer
Stage: C3 - public continuation gateway
Status: **SOURCE ACCEPTED - NOT LIVE ACTIVATED**

## 1. Acceptance verdict

C3 is source accepted.

The stage exposes the already accepted C1 persistence and C2 resume service through exactly two public Soma gateways:

- `continuation_query`
- `continuation_action`

The public capability remains mechanical semantic re-entry. Soma does not become a reasoning agent, does not choose the next action, does not interpret the meaning of Sol handoffs, and does not treat `continuation_context_ref` as authorization.

C3 is not live activated. No Soma process restart, connector refresh, or public runtime activation was performed as part of this stage.

## 2. Accepted source baseline

C3 began from accepted C2 HEAD:

`b20972970a0f734824e6e09537636cfae62c22fc`

C3 implementation ends at:

`6433c9cc31a652e950cf4a2c5e8b20376caeeb4e`

The implementation range contains two commits:

1. `b163120af0c0edc5df40c54b6c048d60f5b9ef51` - `Add C3 continuation query projections`
2. `6433c9cc31a652e950cf4a2c5e8b20376caeeb4e` - `Implement C3 public continuation gateways`

The first commit was created earlier than intended because the first managed `repo_apply` used its default automatic commit mode. The commit is valid, isolated, and preserved in history rather than rewritten or hidden. All subsequent applies explicitly used manual commit mode.

Full C2 -> C3 implementation range:

- 15 files changed
- 848 insertions
- 16 deletions

No unrelated `docs/soma-improvement-research/*` file is included.

## 3. Accepted public surface

Fresh source discovery reports:

- public gateways: **36**
- operation schemas: **275**
- operation schema error: empty
- discovery passes converged: true

This is the intended delta from C2:

- +2 gateways
- +11 operations

No other public gateway family was added or removed.

### `continuation_query`

Accepted operations:

- `capabilities`
- `list`
- `status`
- `resume`
- `handoffs`
- `effects`

### `continuation_action`

Accepted operations:

- `open`
- `update_contract`
- `checkpoint`
- `complete`
- `cancel`

## 4. Public identity

Final fresh-source identity:

Public schema hash:

`ad08c76809c96f404c62f372066724caaa678b6e71b28a5636b029f4010efb89`

Public descriptor hash:

`185533c7c95b6eb14a218822e932edb524df66f73007e33cabadd8f0ad9ca4a6`

Operation inventory hash:

`07724723b5bfd4ebc2d6cef405bd39d8d0dfeece70a61c42f0c9e297c0f80e30`

Public input-schema digest used by metadata-wiring tests:

`9895597fc20679f4227331ebe2ae05540824cd69cbdb033a10c87cd67d9bdc96`

Public output-schema digest:

`d482baa253584213a1922641c84664b1a079899b1bdd88f5231c1d043a890c63`

## 5. Exact new operation schema hashes

`continuation_query.capabilities`

`f9f8e2b0f0486a040399f88e3ac1f24e56518a6511847a167f93e4d5d280249b`

`continuation_query.list`

`9d4adbe306e9203c0ee8880b8c45ff1825885c1d8f4a377dd34da2360003cb19`

`continuation_query.status`

`295f7ee733a5e2dcdf6985b8200b3a2f5bf6aa4f39011970bb1a1509ed8523f4`

`continuation_query.resume`

`872c953486e3d782fb7af0331800642854e634864474ad3ad55810228b79251c`

`continuation_query.handoffs`

`bbb169c82206d57b554586a1ce9ba92ad962bf384a0de9f50da62338caa7224c`

`continuation_query.effects`

`4a85bdfbe2099653fca73aa5a10c5c707bf2137d8afa6de2e71a901d85072a48`

`continuation_action.open`

`efc9decc4290fdb66d13dfdeb538fc0ff362f74a0a3114930546e1f2eb53a32a`

`continuation_action.update_contract`

`2baed545545ec03de0d8ae348a382bba076d14d9dbd10d3198ed701cc112ba99`

`continuation_action.checkpoint`

`13b461dd7104b0e518922c83d67cb1baf631a55f88060cc28016bf9151822ca8`

`continuation_action.complete`

`60f9ff2dfc5985e134744fb949773623172a4105a46303a495f0eafc5ec1fd56`

`continuation_action.cancel`

`b6825b69d5ee159ddf594504ee3f78378c88be67c14935ffce0982aac96f6bdd`

## 6. Gateway semantics

### Query gateway

`continuation_query` is read-only and exposes bounded mechanical projections only.

It can:

- report continuation capability semantics;
- list continuation identities through an opaque cursor;
- report one continuation lifecycle/current-contract status;
- produce the C2 bounded resume bundle;
- page immutable handoff history;
- page continuation-origin effect links while resolving current canonical Task/Run truth.

It cannot:

- execute work;
- mutate continuation state;
- choose the next action;
- infer objective completion;
- interpret free-form handoff meaning;
- run semantic routing or reasoning.

### Action gateway

`continuation_action` can:

- atomically open a continuation with its first immutable contract revision;
- create one immutable contract revision using current-ref CAS;
- append a free-form immutable checkpoint/handoff;
- complete a continuation;
- cancel a continuation.

All mutations delegate to C1 persistence authority and inherit record-level replay/hash-conflict behavior.

No action executes a Task or Run.

## 7. `continuation_context_ref` contract

The public request models explicitly describe `continuation_context_ref` as current continuation contract revision identity and state that it is **not an authorization token**.

For continuation-sensitive writes:

- the referenced contract revision must exist;
- it must be the continuation's current revision;
- the continuation must remain open.

A stale context produces:

`stale_continuation_contract`

A closed continuation produces:

`continuation_closed`

These are mechanical lifecycle/revision errors, not claims that model reasoning is stale.

## 8. Public failure semantics

Accepted query error codes include:

- `continuation_not_found`
- `invalid_continuation_query`

Accepted action error codes include:

- `stale_continuation_contract`
- `continuation_closed`
- `continuation_request_hash_conflict`
- `continuation_lifecycle_conflict`
- `continuation_not_found`
- `invalid_continuation_request`

No reasoning-state error vocabulary was introduced.

## 9. Metadata and annotations

`continuation_query` metadata:

- readOnlyHint: true
- destructiveHint: false
- idempotentHint: true
- openWorldHint: false

Its description explicitly states that it is for durable semantic re-entry and does not reason or choose the next action.

`continuation_action` metadata:

- readOnlyHint: false
- destructiveHint: false
- idempotentHint: true
- openWorldHint: false

Its description explicitly states that `continuation_context_ref` is revision identity rather than authorization and that Soma does not reason.

The action is non-destructive because C3 creates immutable history/current-pointer/lifecycle records and does not delete history, execute effects, or contact an external system. Stable request identity provides replay semantics for its writes.

## 10. C3 gateway behavior proof

New `tests/test_continuation_gateway.py` proves:

- strict discriminated query/action unions;
- cross-operation fields are rejected;
- instruction text/ref exclusivity;
- context-ref schema explicitly states it is not authorization;
- public FastMCP schemas are flat rather than wrapped in a `request` envelope;
- operation inventory exactly matches the six query and five action operations;
- `open -> checkpoint -> resume` works;
- resume exposes the free-form handoff without a next-action field;
- contract update advances the current context ref;
- checkpoint under the old context ref is rejected as stale;
- resume deterministically reports `contract_changed_since_handoff=true` after contract revision;
- list cursor traverses all continuation identities without duplication;
- query paths do not mutate continuation records;
- completion preserves resume/history readability;
- a new checkpoint after completion is rejected;
- missing continuation queries return an honest mechanical error.

## 11. Targeted gate

Final targeted/public-contract verification run:

`20260815T131355Z_executable_profile_1bb8aab2`

Result:

- **55 passed**
- Ruff: pass
- `git diff --check`: pass

This run includes:

- C3 gateway tests;
- C2 continuation service tests;
- public metadata/inventory/descriptor tests;
- fixed MCP discovery output-schema fixture;
- worker application isolation/no-owner-gateway-overlap proof.

## 12. Final broad acceptance gate

Final acceptance run:

`20260815T131429Z_executable_profile_309b4b9d`

Result:

- **255 passed** in the C3/shared/public suite;
- **1 passed** worker-MCP isolation proof;
- Ruff: pass;
- `git diff --check`: pass;
- `C3_WORKER_AUTH_SOURCE_UNCHANGED`.

The suite covers:

- C1 continuation persistence;
- C2 continuation service;
- C3 public gateway;
- RunStore;
- canonical Task plane;
- ProjectScope;
- general gateway models;
- public gateway inventory;
- public operation inventory;
- public metadata wiring;
- public descriptor identity;
- MCP action discovery;
- worker MCP isolation from owner public gateways.

## 13. Exploratory broad-run failures and classification

Earlier exploratory broad run:

`20260815T130754Z_executable_profile_21c8b804`

Result:

- 264 passed;
- 8 failed.

One failure was C3-specific fixture churn:

`tests/test_mcp_action_discovery.py::test_realistic_outputs_validate_against_public_action_output_schemas`

Cause:

The existing test's gateway skip set had not yet included the two newly introduced continuation gateways. The fixture was updated to include `continuation_query` and `continuation_action`, then passed in the targeted and final acceptance runs.

The remaining seven failures were in existing worker-auth transport behavior. Evidence included the current FastMCP `AccessToken` object lacking the `.subject` attribute expected by those tests while carrying `principal_id` in claims, causing downstream worker-auth expectations to collapse into `worker_gateway_error`.

C3 does not modify worker authentication, token verification, grant authorization, worker invocation handling, or worker runtime source. The final acceptance gate explicitly verified the C3 range leaves the checked worker-auth/runtime source paths unchanged and independently passed the worker application isolation test.

Accordingly those seven failures are recorded as an unrelated environment/dependency compatibility issue, not repaired or absorbed into C3.

## 14. Public contract test evolution

C3 intentionally updates:

- public gateway inventory version `cf1.0.v2` -> `cf1.0.v3`;
- CF1 gateway-operation inventory version `v23` -> `v24`;
- public count fixtures 34 -> 36;
- public schema/descriptor/inventory identity fixtures to measured fresh-source values;
- public family coverage to include `continuations`.

No planning-time count was copied blindly. All final values were measured from fresh source discovery.

## 15. No-second-brain audit

Final source audit run:

`20260815T131824Z_executable_profile_98e2fcde`

Result:

`C3_NO_SECOND_BRAIN_SCAN_OK`

The continuation package contains no:

- `recommended_next_action`
- `next_step`
- `reasoning_phase`
- `pending_action`

C3 does not introduce semantic routing, model selection, Skill routing, automatic next-action selection, or structured model cognition.

## 16. Read/write authority boundaries

C3 preserves the existing authority graph:

- continuation persistence owns continuation identity, contract revisions, handoffs, lifecycle, and origin links;
- TaskStore remains canonical for Task state/result/recovery;
- RunStore remains canonical for Run status/result/recovery;
- C2/C3 read those authorities at projection time rather than copying their lifecycle truth;
- ordinary Task/Run operations remain usable without a continuation;
- continuation does not acquire execution authority.

C4 and C5 origin association are not implemented by this stage.

## 17. Worktree and concurrent owner work

At implementation commit completion:

- tracked/staged C3 worktree: clean;
- unrelated untracked `docs/soma-improvement-research` files: preserved;
- concurrent improvement research had reached Iteration 15;
- no unrelated research file was staged or committed by C3.

## 18. Activation boundary

C3 is **source accepted only**.

The running Soma process and current connector remain on the pre-F1/C1/C2/C3 runtime until an explicitly authorized activation/restart step occurs.

C3 acceptance therefore does not claim:

- the live connector currently exposes `continuation_query` or `continuation_action`;
- the live connector currently serves the 36/275 source identity;
- a Chat refresh has occurred;
- a Soma restart has occurred.

No restart or connector refresh was performed.

## 19. Final classification

**C3 PUBLIC CONTINUATION GATEWAY: SOURCE ACCEPTED**

**LIVE ACTIVATION: NOT PERFORMED**

**NEXT DEPENDENCY: C4 TASK ORIGIN ASSOCIATION - NOT STARTED**
