# G5 CDX-R1 Provider Selection Acceptance - 2026-08-12

## Gate

This record closes the executable G5 provider-pilot lane under the owner-approved CLI amendment and performs the G5.6 measured provider selection.

Canonical implementation plan:

`docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md`

Canonical plan SHA-256:

`fa2afb72e51e5cc4494f29b7470eb33cd8a951144a2bc78db5e65a6d8301bea2`

Active provider-route amendment:

`docs/agent-worker-research/G5_CLI_PROVIDER_ROUTE_AMENDMENT_2026-08-12.md`

Owner constraint and authorization:

- no OpenAI API key;
- no paid OpenAI API usage;
- use the existing ChatGPT-authenticated Codex CLI/App Server route;
- API spend ceiling: USD 0.00;
- maximum real Codex model turns: 4;
- no automatic replacement turn after ambiguous create acknowledgement;
- read-only only; no tools, mutations, broker actions, or provider-native subagents.

The four-turn ceiling is exhausted by this gate. No additional real model turn is authorized by this acceptance record.

## Accepted implementation checkpoints

- `496bbd24d836623fd369c832f90c7bb6c696cf0d` - bounded CDX-R1 App Server client, semantic bridge, fixture, and pilot harness.
- `d29912e4059861a35db923d8585ef750ff9bb60d` - reviewed same-version App Server protocol drift and refreshed canonical schema freeze.
- `bfdd5bc9e1f65668df9168ebb0ec81500f9b79f3` - Windows App Server EOF/graceful-reap repair.
- `ca071d74a67613dae0aab43b501db18cf149c168` - current `thread/start.sandbox = read-only` protocol alignment.
- `966f4fa3195afe53c94b90f3b95dc6a9faa651e9` - race-safe exact turn-start capture and pre-interrupt checkpoint.
- `4eeac7f27c648f95720c6f8c97e9db24a0d9773c` - accepted formatted cancellation harness.
- `ed9489b6c85ecc04c1063c04398e2fbd6073fecd` - cancellation restart reconciliation by already-known exact turn identity.

Focused post-repair client/semantic gate:

- 24 passed;
- Ruff lint clean;
- touched pilot script format clean.

A prior broader local gate across App Server client, semantic bridge, canonical reasoning store/Task recovery, and the existing Codex worker adapter passed 216 tests.

## Provider and protocol identity

Measured route:

`Soma -> Codex App Server stdio JSON-RPC -> ChatGPT-managed Codex authentication`

Installed provider identity during the real pilot:

- CLI: `codex-cli 0.145.0`;
- NPM package: `@openai/codex@0.145.0`;
- auth type: `chatgpt`;
- plan type: `plus`;
- model: `gpt-5.6-luna`;
- reasoning effort: `low`;
- API spend: `USD 0.00`.

Reviewed wrapper SHA-256:

`0c149db80ed0bf442c810146b0ad0163b74982fe4542d673f56c354d7b8229cb`

Current canonical App Server protocol-manifest SHA-256:

`dcc92e96e856b1d4f93548f7f8f73e26aa87766431a0e44ceb23049c58c0dcbc`

Schema files in the canonical manifest: 273.

The earlier `de45a8da...` protocol fingerprint is retained as historical drift evidence. Preflight stopped before provider work when the same reported CLI version generated the new protocol content. Two independent schema generations reproduced the current `dcc92e96...` hash before the freeze was updated.

## Real pilot evidence

### CDX-R1 normal/restart - PASS

Soma durable run:

`20260812T151401Z_executable_profile_1358def2`

Measured provider identities:

- thread: `019ff689-bdbf-77f3-9023-eaa8ca467b63`;
- turn: `019ff689-bf5b-78c1-b5ee-68c9d7afa555`;
- fork thread: `019ff68a-422c-7183-8c54-cbeae63c40f3`;
- fork parent: exact original thread.

Results:

- one real model turn;
- turn completed;
- client restart recovered the exact thread ID;
- resume returned the exact thread ID;
- persisted client message identity reconciled the exact completed turn ID;
- structured semantic validation passed;
- the contradictory `retry_limit = 3` / `retry_limit = 4` trap remained unresolved uncertainty rather than an invented winner;
- `EvidenceSubmissionV1` validation passed;
- evidence submission ID: `cdx_r1_submission_41264d6b15c99625a22ab2d6`;
- evidence submission SHA-256: `5f4ef13972dfa4d495b999674e56d5783fe2f6dd400e6a983ec49f6fbc8c4de0`;
- evidence submission bytes: 5127;
- provider event count: 604;
- provider event root SHA-256: `2844a10916ed50d89aaf78cd5902da5ce37b07d0233f3ab3373c2be82fbb31da`;
- provider server-request count: 0.

Measured usage:

- input tokens: 18203;
- output tokens: 733;
- reasoning output tokens: 145;
- cached input tokens: 0;
- total tokens: 18936.

A later metadata-only exact read (`20260812T152244Z_executable_profile_1b245073`) showed the completed turn contained only:

- one `userMessage` item;
- one `agentMessage` item.

No command-execution or file-change item was present.

### CDX-R1 create-ack loss - SAFE UNCERTAIN

Soma durable run:

`20260812T151528Z_executable_profile_a16ed33c`

Exact behavior:

- one `turn/start` request crossed the provider-send boundary;
- acknowledgement was deliberately not awaited;
- no automatic replacement turn was created;
- automatic turn retry count: 0;
- durable outcome remained `uncertain` because no exact provider turn ID was captured.

Thread:

`019ff68b-0817-7072-8802-eea80ac4bcc7`

Client message ID:

`soma-cdx-r1-lost-ack-v1`

A later metadata-only exact thread read (`20260812T151637Z_executable_profile_f921bd9d`) found one persisted interrupted turn, but the provider history did not expose the supplied client message ID in a form that allowed exact matching.

Therefore Soma MUST NOT infer provider create identity from cardinality, time, content, or the fact that only one interrupted turn exists. This measured limitation freezes the production rule:

`unknown create acknowledgement without exact provider turn identity -> outcome_unknown; never blind resubmit`

### CDX-R1 first cancellation race - HARNESS DEFECT, TURN CONSUMED

Soma durable run:

`20260812T151659Z_executable_profile_a18bce31`

The provider turn had started, but the original harness awaited the `turn/start` response before interrupting. The tiny assignment could complete during that wait and the provider returned:

`no active turn to interrupt`

This consumed one authorized model turn. No second replacement was launched. The defect led directly to the race-safe `turn/started` checkpoint repair.

### CDX-R1 repaired exact cancellation - PASS

Soma durable run:

`20260812T152030Z_executable_profile_b9aa3c78`

Before the interrupt side effect, the harness durably emitted:

- thread: `019ff68f-b62b-7520-9355-cbdcba6100c2`;
- turn: `019ff68f-b726-71d1-8ce4-280b9a65e48a`;
- turn-start request ID: 3;
- client message ID: `soma-cdx-r1-cancel-v1`.

Measured result:

- exactly one interrupt request;
- interrupt outcome: `requested`;
- automatic turn retry count: 0;
- provider terminal turn status: `interrupted`;
- provider event count: 11;
- provider event root SHA-256: `c6d1d4e370c40ca1bce7bb1a50669ca85616104374288685a723409d8b70df60`;
- provider server-request count: 0.

Metadata-only restart verification:

`20260812T152124Z_executable_profile_c68747f1`

proved:

- exact thread identity matched;
- exact known turn identity was present;
- exact persisted turn status was `interrupted`;
- thread contained one turn.

The harness was then corrected to reconcile cancellation using the already-known exact turn ID rather than a weaker client-message lookup.

## G5.6 measured comparison

Only CDX-R1 is executable under the owner's no-API constraint. API-only OAI-R1/OAI-R2/OAI-A1 are not candidates for selection in this environment. No provider is selected by reputation.

| Criterion | CDX-R1 evidence |
| --- | --- |
| Durable operation identity | PASS when exact thread/turn IDs are captured; unknown create remains explicit uncertainty |
| Restart recovery | PASS for known thread/turn identity |
| Cancellation | PASS after exact `turn/started` checkpoint repair |
| Structured output | PASS |
| Bounded EvidenceSubmission | PASS |
| Provenance | PASS for root thread, turn, fork, parent lineage, event root |
| Protocol drift detection | PASS; detected same-version schema drift before provider work |
| API cost | PASS; USD 0.00 API spend, ChatGPT subscription quota used |
| Latency | Measured, not generalized; normal/restart pilot durable run was 47.483 s |
| Native subagents | UNMEASURED here; reserved for G7 |
| Read-only isolation | PASS in measured pilot; no provider command/file-change items or approval requests |
| Protected broker compatibility | NOT MEASURED with real provider; deliberately outside read-only G5 |
| Create-ack uncertainty | PASS safety rule; exact recovery is not guaranteed, but no blind duplicate create occurs |

## G5.6 verdict

```text
PROMOTE_CDX_R1
```

Promotion meaning is deliberately narrow:

- CDX-R1 is the first selected real read-only reasoning-provider route for the frozen G6 canonical benchmark and subsequent internal adapter work;
- canonical Soma backend/task identity remains authoritative;
- Codex thread/turn IDs remain subordinate provider provenance;
- exact known provider IDs may be recovered after restart;
- unknown create acknowledgement remains `outcome_unknown` and is never automatically resubmitted;
- provider-native subagents remain disabled/unmeasured until G7;
- no protected mutation authority is granted;
- no public MCP/runtime activation is implied;
- fake reasoning backend remains the deterministic regression baseline.

## Quota boundary

Exactly four authorized real Codex model turns were consumed:

1. normal/restart - passed;
2. deliberate lost-ack - safe uncertain/no retry;
3. original cancellation race - harness failure after turn creation;
4. repaired exact cancellation - passed.

The authorized model-turn budget is therefore exhausted.

No G6 model turn may start until a new explicit owner authorization sets the G6 provider-turn/quota ceiling.

## Gate result

`G5 ACCEPTED - PROMOTE_CDX_R1 FOR INTERNAL READ-ONLY G6 USE`

No push, no API spend, no external mutation, no public activation, and no provider-native subagent experiment occurred in this gate.
