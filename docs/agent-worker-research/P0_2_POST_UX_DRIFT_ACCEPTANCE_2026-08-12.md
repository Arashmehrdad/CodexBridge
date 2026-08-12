# P0.2 - Post-UX Architecture Drift Acceptance

Date: 2026-08-12
Status: ACCEPTED
Stage: P0.2 only - post-UX architecture drift audit
Repository: `D:\Github\Soma`
Branch: `lane/memory-integration-foundation-1`
Frozen research source: `b53404fa9600412a4b3dd0fafd664a856096257b`
Implementation audit HEAD: `93c206de67bce5fac7cecb9cbf23f2607c3e3398`

## 1. Acceptance decision

P0.2 is accepted.

No architecture-bearing source listed by the canonical implementation plan changed between the frozen research source `b53404f` and implementation HEAD `93c206d`.

No observed change:

- requires a plan adjustment;
- invalidates a research assumption;
- changes Company Kernel, Task, ProjectScope, lock, Hermes, Workflow, parallel-group, provider-adapter, worker-substrate, Run, or public-result authority semantics;
- authorizes production implementation beyond the next explicit implementation micro-stage.

The canonical implementation plan remains valid as the G1 entry authority.

## 2. Entry-state verification

Live repository inspection at P0.2 start verified:

```text
branch: lane/memory-integration-foundation-1
HEAD: 93c206de67bce5fac7cecb9cbf23f2607c3e3398
staged: none
unstaged tracked changes: none
untracked:
  docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md
```

The parked owner file `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` was not read for this audit, modified, staged, renamed, deleted, or incorporated.

P0.1 was independently rechecked. The range `59542898ddab797a6f3276f59f9075a8162f60b1..93c206de67bce5fac7cecb9cbf23f2607c3e3398` contains exactly the five agent/worker research journals: 5 files added, 5,394 insertions, no production source.

The canonical implementation plan is tracked from `e8f1a19db091f9b6293289857b9652809c523e52` and is unchanged in the worktree.

## 3. Exact post-freeze commit drift

The drift was decomposed by committed interval rather than inferred from the current worktree.

### `b53404f..e8f1a19`

Exactly one file was added:

```text
docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md
```

Classification: `compatible`.

This is the canonical implementation plan itself. No production source changed.

### `e8f1a19..5954289`

Candidate-B normal-Chat Tool UX changed 13 files:

```text
docs/CHATGPT_NORMAL_CHAT_TOOL_UX_B_SOURCE_ACCEPTANCE_2026-08-12.md
docs/CHATGPT_NORMAL_CHAT_TOOL_UX_IMPLEMENTATION_PLAN_2026-08-12.md
soma/knowledge_tools_integration.py
soma/public_tool_metadata.py
soma/server.py
tests/test_gateway_benchmark.py
tests/test_knowledge_tools_integration.py
tests/test_mcp_action_discovery.py
tests/test_memory_gateway_operations.py
tests/test_public_descriptor_identity.py
tests/test_public_metadata_wiring.py
tests/test_public_tool_metadata.py
tests/test_tool_gateway_models.py
```

Classification: `unrelated` to the agent/worker architecture contract audited by P0.2.

The Candidate-B production changes are confined to public MCP descriptor metadata, discovery identity/cache convergence, registration wiring, knowledge-tool descriptor wiring, and directly related tests/docs. They do not change the canonical agent/worker authority-bearing paths listed below.

One shared integration file, `soma/server.py`, changed, but the inspected diff is public tool presentation/discovery plumbing: descriptor hashing, registration metadata, capability identity, and discovery cache generation. It does not alter Company Kernel, Task lifecycle, ProjectScope, mutation lock ownership, Hermes execution semantics, workflow execution authority, worker adapters/substrate, Run lifecycle, or result-publication semantics.

Candidate B therefore remains a separate public-UX layer. The implementation plan's later rule that public/normal-Chat activation is a separate decision remains valid.

### `5954289..93c206d`

Exactly the five research journals were added.

Classification: `compatible`.

No production source changed.

## 4. Required architecture-path drift classification

Git range evidence shows no committed diff from `b53404f` to `93c206d` under any of the required P0.2 architecture-bearing paths.

| Required path | Drift | Classification | P0.2 conclusion |
| --- | --- | --- | --- |
| `soma/company_kernel/` | none | `compatible` | Frozen Company Kernel assumptions remain applicable. |
| `soma/tasks/` | none | `compatible` | Canonical Task/backend authority assumptions remain applicable. |
| `soma/project_scope/` | none | `compatible` | Project/resource/scope-generation authority is unchanged. |
| `soma/operation_locks.py` | none | `compatible` | Existing repository lock semantics are unchanged. |
| `soma/hermes_companion_protocol.py` | none | `compatible` | Hermes remains pinned/headless under the same protocol contract. |
| `soma/hermes_service_supervisor.py` | none | `compatible` | Hermes worker-supervisor semantics are unchanged. |
| `soma/hermes_concurrency.py` | none | `compatible` | Existing resource/credential concurrency semantics are unchanged. |
| `soma/workflows/` | none | `compatible` | Legacy Workflow remains its existing lifecycle/one-active-child substrate. |
| `soma/parallel_groups.py` | none | `compatible` | Existing durable exact-command fan-out precedent is unchanged. |
| `soma/worker_adapters/` | none | `compatible` | Provider-neutral capability/adapter assumptions remain applicable. |
| `soma/worker_substrate/` | none | `compatible` | Persist-before-send/message-authority assumptions remain applicable. |
| `soma/run_store.py` | none | `compatible` | Run lifecycle/recovery/publication source semantics are unchanged. |
| `soma/run_public_result.py` | none | `compatible` | Public result identity/projection semantics are unchanged. |

There are zero `requires-plan-adjustment` entries and zero `invalidates-research-assumption` entries.

## 5. Current-source invariant spot checks

Because P0.2 is an architecture gate rather than only a filename audit, current HEAD was also inspected directly.

### Company Kernel remains inactive v1

Current source still reports:

```text
COMPANY_KERNEL_SCHEMA_VERSION = 1
active_capability = False
```

The models still state that execution state remains in canonical Task and Run planes.

Conclusion: G1 may proceed from the planned additive/inactive Company Kernel baseline. No hidden runtime activation occurred.

### Canonical Task remains single-kind/single-backend

Current `soma/tasks/models.py` still exposes only:

```text
TaskKind.DURABLE_COMMAND = "durable_command"
BackendKind.SOMA_DURABLE_RUN = "soma_durable_run"
```

Conclusion: the G2 plan to add provider-neutral reasoning behind canonical Task has not been pre-empted or made stale.

### Hermes remains headless and pinned

Current `soma/hermes_companion_protocol.py` still contains:

```text
PINNED_HERMES_REVISION = 862b1b37bf0aadba3a98b3756c7d71779379b53b
```

and still forbids model-runtime module prefixes including:

```text
hermes_agent
model_client
model_provider
agent_loop
inference
```

Conclusion: the architecture distinction remains valid: integrated Hermes supplies execution/tool concurrency, not independent reasoning minds.

### Workflow remains a separate one-active-child lifecycle

Current Workflow worker behavior still gates progress on the single `workflow.active_child_run_id`, reconciles that one active child, and starts the next pending step only after the active child is cleared.

Conclusion: research was correct not to promote Workflow directly into the new concurrent canonical worker manager.

## 6. Frozen-source checksum confirmation

A one-line read was used to obtain current whole-file SHA-256 values for 20 representative architecture files. The values match the frozen Iteration-5 benchmark/source identities for those exact files.

```text
soma/company_kernel/models.py
  180bf13fdb5c777d579a34d1e056cfc85345453ddac9ef1c6e2c6356b35eff89
soma/tasks/models.py
  d39aded14ca13647d2ed050b903eee53444d0b210b621db79a2c752c6521db63
soma/tasks/backends.py
  8e03377677eb72bf253a803cc18beeb516b570a89a63b689e9f0a5a21b57d522
soma/tasks/projections.py
  12755aa32b417025e52600bff3ca4afc39bd88d5a7365f6a1c19a246578187cb
soma/project_scope/store.py
  2b7ff63cf289612385bc591a1860657264163da194c0d76fd9929435bacd5a06
soma/operation_locks.py
  c5b4b2938ab407b71db65eba88a70ae82b06361de23d81d333655f38750ccb18
soma/hermes_companion_protocol.py
  17565bf31fb729b70ab2f7b460637168372570661c1712a7abd7731bc4d91259
soma/hermes_service_supervisor.py
  2a6c04546326edb84061091b55e4b91bfde7f341e2281d3acf78e0cf4c950c85
soma/hermes_concurrency.py
  20ad0f2ec31f4fe0530ee8992433692c12101c6b9981dfdec9457e5dd1ea9309
soma/workflows/models.py
  e8fbacf95d2af7e95209dff6ec6b332b7f487b1743f69a41b317a4a561085bb1
soma/workflows/worker.py
  1329b34caaadad5bbcb782bb2db1f5f0ea611a22febda264471d9241af66cf4d
soma/parallel_groups.py
  e36145491349ab9fc774c586530cbf0dd28b9d4dc8f7ee5e2f02c52e1182bbee
soma/worker_adapters/contract.py
  dc7b4d9c54dd4bbac8cb9c6469acf4f6bf2c38e2131d9f340bd02fa3ce133653
soma/worker_adapters/codex.py
  64f2f9e0f6ac588b9f4d4e78a6a1eb14f6d77696a78827c92431e9244fba7dcd
soma/worker_adapters/claude_code.py
  02173b0ad5643c601b0e484a339d8057d63c435ec6f210eb6b2c935a5c4cfd06
soma/worker_substrate/models.py
  bfbcc8c3b88a3065d846a72b01b375d9853bc1618cd4033563a1f4375c75fb64
soma/worker_substrate/coordinator.py
  62ca7ae5737009c324f45a6994cac5a10a8fe8d1a101b1502b219e43022f152f
soma/worker_substrate/dispatch.py
  d8134e563d1dfb21a67372233f3ba3f3f2a4a560dd76501427c09ff1c015b7f7
soma/run_store.py
  f2fb3407330e6247b89c620706cc431ce79e78222d17edbe913e0ca8917b550b
soma/run_public_result.py
  c1ee8dfad1be401f99a6ce535c1861d095f90adba75c89572e3b79fe14993be2
```

This checksum evidence independently corroborates the Git-range result for the architecture baseline used by the research.

## 7. Candidate-B organic UX observation

Known observation retained:

```text
classification: UX-observation / connector-cache oddity
```

One generic connector/plugin inventory path did not initially advertise Soma, while explicit Soma resource discovery exposed the expected 32-tool surface immediately. This did not block P0.1 or P0.2.

During P0.2, once the Soma surface was explicitly loaded, Candidate-B metadata routed repository inspection correctly to `repo_query`; no unnecessary confirmation, misleading action title, broad-tool ambiguity, or wrong mutation surface was observed.

No new Candidate-B defect is established by P0.2.

## 8. Research-instrument findings

Classification summary for implementation-observation duty:

```text
bug: none
implementation-friction: none material
research-assumption-invalidated: none
UX-observation: known connector/cache discoverability oddity retained
platform-change: none newly established by P0.2
unrelated: Candidate-B public descriptor/metadata changes and parked canonical-memory file
```

The audit therefore provides positive evidence that the research-to-implementation handoff did not cross an unnoticed architecture mutation.

## 9. G1 entry decision

P0.2 outcome:

```text
ACCEPTED
requires-plan-adjustment: 0
invalidates-research-assumption: 0
production architecture changed during P0.2: no
real provider/model work: no
service restart: no
connector refresh: no
push: no
wiki refresh: no
canonical-memory mutation: no
```

The next implementation stage is G1.1 - Pure graph and dependency contract models.

P0.2 does not itself authorize G1.1 to continue in the same execution step. The controller must issue a separate exact G1.1 instruction and retain the hard-stop discipline.
