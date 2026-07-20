# CodexBridge Active Engineering Plan

## Purpose

CodexBridge is the durable control plane connecting this ChatGPT conversation to local machines, repositories, services, remote hosts, and external tool runtimes.

```text
ChatGPT conversation
  -> reasoning, user context, tool selection, and approvals
  -> CodexBridge MCP
      -> durable identity, policy, execution, cancellation, and evidence
      -> local and remote engineering substrates
      -> Hermes searchable tool runtime
          -> built-in tools, plugins, skills, and connected MCP tools
```

ChatGPT remains the reasoning agent. Hermes supplies tools; its Codex, Claude, or other model-agent loop is not part of this request path.

This file is an active decision document, not an engineering journal. The complete V2 implementation and validation history through commit `d1c43340af48c03ca31505ef64f4c6a60248f61c` is preserved in [`docs/roadmap-v2-achievements.md`](docs/roadmap-v2-achievements.md).

## Governing Decisions

### Durable before powerful

Every accepted asynchronous operation must persist launch intent, request identity, ownership and lease state, cancellation state, output locations, and terminal publication semantics before it is production-ready.

### ChatGPT remains the brain

- The live ChatGPT conversation owns reasoning, user context, planning, and tool selection.
- CodexBridge exposes governed capabilities to that conversation.
- Hermes is a tool runtime, not a delegated reasoning agent, for this integration.
- The design does not depend on exporting ChatGPT's private memory store. Relevant context stays in the conversation; only required tool arguments or explicit context are transmitted.

### Reuse Hermes rather than duplicate it

- Reuse Hermes registration, availability checks, toolsets, plugin discovery, MCP discovery, and searchable dispatch where feasible.
- Do not create one CodexBridge wrapper for every Hermes tool.
- New Hermes plugins or MCP tools should become discoverable without corresponding CodexBridge source changes.
- Pin and negotiate the supported Hermes interface so upstream changes fail explicitly.

### Existing execution decisions remain in force

- `permissive` is the only active execution profile.
- Unrestricted PowerShell remains the single arbitrary-command local gateway.
- Native remote Linux execution continues through the accepted R4 controller protocol.
- Remote PowerShell remains optional for hosts that already provide it.
- Existing human-only boundaries continue to apply to real-money, credential, destructive, and production-impacting actions.

### No paid infrastructure for validation

- Do not start, rent, or retain RunPod or any other paid remote/GPU host solely for CodexBridge testing, acceptance, or roadmap evidence.
- Prefer local Windows validation, deterministic mocks and replayed fixtures, existing free CI, or infrastructure already running for an actual user-requested workload.
- OS-, provider-, or hardware-specific execution evidence that cannot be obtained without new cost is non-blocking deferred evidence. Collect it opportunistically during real work rather than making it a roadmap gate.

### Evidence before Roadmap V3

After the Hermes integration reaches its bounded gate, architectural feature expansion pauses. CodexBridge will be exercised on real projects before another broad reliability roadmap is created.

## Current Baseline

Complete: D1-D5 durability; G0/G1 managed editing and executable closure; X1/X2 unrestricted local PowerShell; X2A parallel groups; C1 permissive-only cleanup; R3 managed transfer; R4 durable remote Linux ownership; and optional X4 remote PowerShell.

R5 absolute resource enforcement is complete. H1A has selected and pinned the Hermes companion-process architecture. H1B now includes the versioned companion, durable public gateway, policy-preserving built-in calls, plugin and MCP discovery, repository-owned Hermes-home binding, and successful public connected-MCP execution.

Known observations, not yet separate repair programs:

- occasional HTTP 502 responses from the ChatGPT connector path;
- external acceptance fixtures that may disappear independently of CodexBridge;
- increased complexity in durable state and reconciliation contracts.

Collect operational evidence before prescribing broad fixes for these observations.

## Active Sequence

1. Complete the already-scoped R5 boundary.
2. Perform the Hermes tool-runtime feasibility audit.
3. Implement the smallest durable ChatGPT-to-Hermes tool path satisfying the accepted architecture.
4. Freeze architectural expansion and exercise the combined system on representative real projects.
5. Build Roadmap V3 from observed frequency, severity, recovery cost, and violated invariants.
6. After the current OP1 observation period is reviewed, begin the separate Trading Lab roadmap at TL0; do not interleave it with H1 acceptance or OP1 evidence collection.

Do not resume the older broad R6, R7, or P2 sequence automatically. Only supporting work required by R5, Hermes integration, or a proven pilot defect is active.

## R5 - Absolute Resource Enforcement

Status: **complete**.

Implemented:

- deterministic cgroup-v2 absolute memory policy at conservative `40_000_000_000`, graceful `45_000_000_000`, and hard `48_000_000_000` bytes;
- policy and samples in authoritative R4 state and heartbeats;
- graceful and hard process-group enforcement with identity revalidation;
- persisted threshold, signal, identity, confirmation, and terminal evidence;
- a separate `16_384`-byte ceiling for internal encoded controllers;
- authoritative GPU temperature/memory, disk-capacity, controller-heartbeat, and bounded CUDA-OOM evidence while preserving absolute-memory-first enforcement;
- POSIX execution coverage for graceful exit, forced escalation, direct hard termination, identity refusal, and persisted evidence.

Acceptance evidence:

- `tests/test_remote_controller_state.py`: `8 passed`;
- `tests/test_ssh_watchdog.py`: `9 passed`;
- `tests/test_remote_resource_enforcement.py`: `7 passed`;
- `tests/test_ssh_watchdog_execution.py`: `4 skipped` on Windows as platform-gated;
- the actual generated controller completed all four process-group cases on the existing free Linux host: graceful, escalation, hard, and identity refusal;
- affected modules compiled and `git diff --check` passed.

R5 satisfies deterministic threshold paths, visible overrides, exact termination targeting, durable remaining-signal evidence, and real POSIX process-group validation without provisioning paid infrastructure.

## H1 - ChatGPT-Controlled Hermes Tool Runtime

Status: **complete**.

### H1A - Feasibility audit

- Identify and pin the candidate Hermes revision.
- Confirm registry, toolset, search, schema, dispatch, result, cancellation, and approval interfaces.
- Prove whether `tool_search`, `tool_describe`, and `tool_call` work without a Hermes model-agent loop.
- Inspect how built-ins, plugins, skills, and connected MCP tools enter the effective registry.
- Identify required runtime state, credentials, browser state, and long-running ownership.
- Prefer a versioned process boundary: upstream server mode or a small Hermes companion adapter.
- Avoid direct in-process Hermes imports unless no stable boundary exists and the coupling is explicitly accepted.

The audit produces a compact decision and implementation scope; it must not silently expand into implementation.

H1A decision (2026-07-18):

- Pin `NousResearch/hermes-agent` revision `862b1b37bf0aadba3a98b3756c7d71779379b53b` as the initial compatibility target.
- Use a small versioned Hermes companion process over stdio; do not import Hermes into the CodexBridge service process and do not invoke a Hermes model-agent loop.
- The existing upstream `mcp_serve.py` is session/event/approval oriented and is not the required generic tool-runtime boundary.
- Hermes catalog search and schema description can execute as pure registry reads. Deferred `tool_call` can invoke the underlying tool without model inference while preserving the normal Hermes hook, guardrail, edit-approval, and approval path.
- Built-ins, plugins, and connected MCP tools converge in the effective registry. Skills remain instruction resources unless associated code registers an actual tool.
- Generic detached or long-running tools remain unsupported initially because the registry has no provider-neutral external ownership and cancellation contract.
- The accepted implementation scope and evidence are recorded in [`docs/hermes-tool-runtime-feasibility.md`](docs/hermes-tool-runtime-feasibility.md).

H1B protocol foundation completed on 2026-07-18:

- added a versioned companion handshake bound to Hermes revision `862b1b37bf0aadba3a98b3756c7d71779379b53b`;
- bound registry generation and deterministic effective-schema hash into handshake, search, and describe responses;
- added deterministic interface-drift failures for protocol, revision, registry-generation, and schema changes;
- added bounded `tool_search` summaries and exact `tool_describe` schema identity;
- added fail-closed evidence that no Hermes model-runtime module was initialized;
- focused validation: `tests/test_hermes_companion_protocol.py` reported `5 passed`, the protocol module compiled, and `git diff --check` passed.

Pinned companion executable adapter completed on 2026-07-18:

- added a JSON-lines stdio executable that verifies the exact Hermes Git revision before importing upstream code;
- imports only the pinned `tools.registry` discovery boundary and fails closed on registry interface drift;
- emits the accepted handshake and routes schema-bound read-only `tool_search` and `tool_describe` requests;
- bounds request and response sizes and emits deterministic error envelopes;
- rejects any observed Hermes model-runtime import before serving requests;
- focused validation: `tests/test_hermes_companion.py` reported `5 passed`, `tests/test_hermes_companion_protocol.py` reported `5 passed`, the adapter compiled, and `git diff --check` passed.

Durable companion client contract completed on 2026-07-19:

- added bounded one-request handshake/search/describe launch construction over the existing durable executable-profile lifecycle;
- persisted the pinned Hermes revision, checkout, operation, and expected registry/schema identity in the accepted client metadata;
- added exact one-response parsing with handshake and bound catalog-identity verification;
- focused validation: `tests/test_hermes_companion_client.py` reported `5 passed`, the client module compiled, and `git diff --check` passed.

Public gateway and terminal publication completed on 2026-07-19:

- added the `hermes_companion` public `run_start` operation for handshake, search, and describe;
- persisted pinned checkout, revision, operation, registry generation, and schema hash in the authoritative executable input;
- the worker now verifies the exact one-response protocol before terminal publication and includes the verified Hermes response beside protected stdout/stderr artifact metadata;
- malformed, failed, multiply emitted, operation-drifted, generation-drifted, or schema-drifted responses fail the durable run rather than publishing unverified catalog data;
- focused validation: `tests/test_hermes_companion_client.py` reported `5 passed`, `tests/test_tool_gateway_models.py` reported `32 passed`, and `tests/test_job_manager.py` reported `68 passed`.

Live public H1B gate completed on 2026-07-19:

- repaired the ignored live `config.yaml` profile boundary that had joined `unrestricted_child_processes: true` to `parallel_execution:`, causing every fresh durable worker to exit before lease claim;
- cancelled the abandoned queued validator, validated the repaired configuration, reloaded it without restarting the tunnel, and proved fresh PowerShell and allowlisted Git workers claim and complete normally;
- restored the ignored pinned checkout at Hermes revision `862b1b37bf0aadba3a98b3756c7d71779379b53b`;
- aligned the companion with the pinned registry interface by running explicit built-in discovery and reading the raw registered schemas without invoking availability checks or a Hermes model loop;
- `tests/test_hermes_companion.py` reported `6 passed`, the adapter compiled, and the compatibility fixes were committed as `620913c5b9a78e8741681d2d96f96c302486c82f` and `baa7354696ca841efd56070fb066d19aa36d8048`;
- the public MCP `run_start(operation="hermes_companion")` handshake completed as run `20260719T035330Z_executable_profile_9e38e2d0`, publishing registry generation `57`, effective schema hash `9489c958268618207783c6e4e31e2b93d37db06841c49657de4d194f78e71445`, pinned revision identity, and `model_runtime_initialized: false`;
- schema-bound public search completed as run `20260719T035421Z_executable_profile_d0111a56`, and exact describe completed as run `20260719T035424Z_executable_profile_c7ec0d5a`; both published verified `hermes_response` data, terminal result hashes, and protected stdout/stderr artifact hashes under the same catalog identity;
- the current CodexBridge environment initially lacked the pinned Hermes core dependency `requests==2.33.0`, so five built-in modules (`browser_tool`, `delegate_tool`, `terminal_tool`, `vision_tools`, and `x_search_tool`) were unavailable and emitted bounded protected warnings;
- installed that exact upstream-pinned dependency into the live companion environment, then reran the pinned handshake as run `20260719T051116Z_executable_profile_7cf66ac2`;
- the aligned handshake completed with empty stderr, registry generation `72`, effective schema hash `3c409ad2b545f2251550f22e5924d6af6c0fd1775cd4840f8c21fca6b5eab870`, and `model_runtime_initialized: false`; protected stdout hash `1613bdd8197cbe5e4e7c7602e7316bfb6f0803436cad4fa577458032c9c1808e` and empty-stderr hash `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` were durably published.

Bound tool-call path completed on 2026-07-19:

- added a one-request `tool_call` companion operation bound to the accepted protocol version, pinned Hermes revision, registry generation, effective-schema hash, exact tool identity, exact tool-schema hash, and accepted argument object;
- replaced the lower-level registry dispatcher with pinned `model_tools.handle_function_call`, preserving request middleware, plugin pre-tool blocks, approval guards, execution middleware, and post-tool hooks against the real tool identity;
- exposed `tool_call` through the public durable Hermes gateway after the policy-path gate passed;
- proved a real bounded read-only `read_file` call against the pinned generation-72 catalog and schema hash `3c409ad2b545f2251550f22e5924d6af6c0fd1775cd4840f8c21fca6b5eab870` as run `20260719T072023Z_executable_profile_bccfab47`;
- the call read lines 1-5 of `PLANS.md`, published exact arguments and tool-schema hash `265fc44e1ec436b2716993e33375040ac26ebae8fc87c770851089db21b93633`, emitted empty stderr, and did not initialize a Hermes model-agent runtime;
- focused validation: `tests/test_hermes_companion.py` reported `6 passed` and `tests/test_tool_gateway_models.py` reported `32 passed`.

Plugin and MCP discovery alignment completed on 2026-07-19:

- companion startup now invokes the pinned Hermes `discover_plugins()` and `discover_mcp_tools()` entry points before freezing the effective registry snapshot;
- plugin and connected-MCP tools therefore enter the same schema-bound catalog and normal `model_tools.handle_function_call` execution path without tool-specific CodexBridge wrappers;
- pinned interface drift for either discovery entry point fails closed, while ordinary plugin/server discovery failures are retained as bounded handshake initialization warnings;
- synthetic connected-MCP registration coverage proves a newly discovered MCP tool appears in the catalog, contributes its dynamic toolset, and executes through the generic bound executor;
- focused validation: `tests/test_hermes_companion.py` reported `7 passed`, and the companion module compiled.

Disposable connected-MCP execution evidence completed on 2026-07-19:

- added a repository-owned stdio MCP fixture and a reusable acceptance harness using an isolated `HERMES_HOME` under ignored `runs`, leaving the user's real Hermes configuration untouched;
- the actual pinned Hermes checkout discovered `mcp__codexbridge_fixture__echo_fixture`, included it in registry generation `85`, and bound it to effective schema hash `8b43af99fe9ea6e41bfd82542f4f42764816bf36bf53156cd64c6fe6c59db160`;
- exact describe published tool-schema hash `87fb4050ba48900df327f896d8fcae53dfca0203e8eb6350352f016b380b2074`;
- the generic policy-preserving executor returned the fixture marker and value `durable-mcp-gate` with `model_runtime_initialized: false`;
- durable validation run `20260719T092053Z_executable_profile_616c1625` completed with empty stderr, both fixture scripts compiled, and `tests/test_hermes_companion.py` remained `7 passed`.

Repository-owned Hermes-home binding completed on 2026-07-19:

- added an optional `hermes_home` field to the public durable `hermes_companion` request;
- the client resolves and accepts only an existing non-symlink directory contained by the active repository, then injects only the exact `HERMES_HOME` environment key into the existing executable lifecycle;
- arbitrary companion environment injection remains unavailable;
- focused validation: `tests/test_hermes_companion_client.py` reported `6 passed` and `tests/test_tool_gateway_models.py` reported `32 passed`.

Public connected-MCP gateway acceptance completed on 2026-07-19:

- corrected the dedicated Hermes executable profile to use `environment_policy: arbitrary` with unrestricted environment delivery, while the public companion contract still injects only the validated repository-owned `HERMES_HOME` key;
- validated and reloaded the live configuration without restarting the service or tunnel;
- public handshake run `20260719T184837Z_executable_profile_e3d7d21e` published registry generation `85`, effective schema hash `8b43af99fe9ea6e41bfd82542f4f42764816bf36bf53156cd64c6fe6c59db160`, protected stdout SHA-256 `db40d703b817243b48e525ca413a58e0e7cced73f2b65085aba8298e6068d3e9`, and empty protected stderr;
- public search run `20260719T184845Z_executable_profile_00575f0e` discovered `mcp__codexbridge_fixture__echo_fixture` under the same catalog identity;
- public describe run `20260719T184849Z_executable_profile_82d878a9` bound tool-schema hash `87fb4050ba48900df327f896d8fcae53dfca0203e8eb6350352f016b380b2074`;
- public call run `20260719T184854Z_executable_profile_f5fd4fb2` returned source `codexbridge-disposable-mcp` and value `public-durable-mcp-gate`, with protected stdout SHA-256 `54c65db5b8c13717f273dcacb22901d7938ca5d3a5d3434d421e81ab62604dd9` and empty protected stderr;
- no Hermes model-agent loop or tool-specific CodexBridge wrapper participated in the path.

Repository-owned reversible side-effect fixture contract completed on 2026-07-19:

- extended the disposable connected-MCP fixture with caller-supplied idempotency keys, atomic repository-owned outcome state, exact argument-drift rejection, authoritative reconciliation, and explicit reversal;
- an intentional post-commit ambiguous response leaves the mutation durably visible for reconciliation;
- replay with the same key and arguments returns the original outcome with `applied: false`, preserving `application_count: 1` rather than applying the mutation twice;
- focused validation: `tests/test_hermes_mcp_fixture.py` reported `3 passed`, and adjacent `tests/test_hermes_companion.py` reported `7 passed`.

Public reversible side-effect acceptance completed on 2026-07-19:

- fresh public handshake run `20260719T201034Z_executable_profile_6130c7ba` bound registry generation `88` and effective schema hash `d6c2814409cad1c28c075bd134d4ea1806617154f3b7206b10173ec8e5cdfc39`, with `model_runtime_initialized: false`, protected stdout SHA-256 `f898728d1a176770ba0939294754a4a2de2f59fc5873a076e5d8b91af468b125`, and empty protected stderr;
- public search run `20260719T201113Z_executable_profile_fd0f7afd` bound `mcp__codexbridge_fixture__apply_reversible_fixture` to tool-schema hash `4eff7674906c70b559b9255711bd10dd560326232299bf1fd4b5f4a2e117b90c`;
- ambiguous apply run `20260719T201158Z_executable_profile_5291aff8` committed idempotency key `h1-public-side-effect-20260719-2012` and then returned the intentional post-commit error, with protected stdout SHA-256 `150ac9686f4cc112cc0d5e4c28893cc841fd95851f2c8fa5e61d250516cbc7dc` and empty stderr;
- reconciliation run `20260719T201203Z_executable_profile_a17bc66e` verified the authoritative outcome existed with value `public-durable-side-effect` and `application_count: 1`;
- replay run `20260719T201207Z_executable_profile_60006013` returned `applied: false` while preserving the same single application, proving the ambiguous result was not blindly duplicated;
- reversal run `20260719T201211Z_executable_profile_7c752b60` returned `reverted: true`, and final reconciliation run `20260719T201216Z_executable_profile_51e57bc3` verified `exists: false`;
- the acceptance exposed that the fixture MCP child did not inherit the companion-only `HERMES_HOME`; the fixture now fails closed without an explicit home and the generated MCP server configuration passes the repository-owned home directly;
- isolation regression validation: `tests/test_hermes_mcp_fixture.py` reported `4 passed`.

Lifecycle acceptance completed on 2026-07-19:

- added a bounded, side-effect-free `mcp__codexbridge_fixture__wait_fixture` tool for deterministic lifecycle testing;
- fresh public handshake run `20260719T211753Z_executable_profile_56f93e9f` bound registry generation `89` and effective schema hash `a308c1820ae7e601a71cedc6ff27be866c5d40221070244b826ca657b7f2aa78`, with `model_runtime_initialized: false` and empty protected stderr;
- exact describe run `20260719T211801Z_executable_profile_7213674c` bound tool-schema hash `012082dc6fb140f730f2e93f1add7934e895517f0b4123ebab6096a9c8c74104`;
- cancellable call run `20260719T211806Z_executable_profile_94dcc96d` reached verified `running` ownership with result publication still `not_published`, then `cancel_run` confirmed process-tree termination for the child and worker and published one terminal `cancelled` result;
- the cancelled run returned empty public stdout/stderr and no `hermes_response`, proving an interrupted call cannot publish an unverified tool result;
- startup reconciliation regression coverage proves a persisted active Hermes worker with verified process identity is adopted with exact companion catalog metadata intact, its repository lock retained, and result publication left `not_published` until the worker finishes;
- focused validation: `tests/test_hermes_mcp_fixture.py` reported `5 passed`, and `tests/test_job_manager.py` reported `69 passed`.

H1 acceptance is complete. The next executable unit is OP1: begin the evidence-driven real-project pilot with a repository-owned pilot evidence log and record representative ordinary CodexBridge/Hermes work without architectural expansion.

### H1B - Minimal external surface

The preferred ChatGPT-facing capability can search enabled tools, describe one exact schema, invoke it with validated arguments, inspect long-running status/results, and cancel through authoritative ownership.

The contract must preserve Hermes version, registry generation or schema hash, tool identity, selected toolset, accepted arguments, result classification, and artifact references. Exact public tool names are chosen during implementation.

### H1C - Execution and policy

- ChatGPT plans and chooses the tool; Hermes must not reinterpret the task through a second model.
- CodexBridge remains authoritative for request identity, durability, cancellation, bounded output, protected evidence, and applicable locks.
- Search and description are read-only.
- Side effects include communications, bookings, purchases, refunds, credential changes, destructive actions, and real-money operations.
- Ambiguous transport failure must never cause blind replay of a mutation.
- Automatic mutation retry requires provider-appropriate idempotency or outcome reconciliation.
- Secrets use the narrowest safe existing channel and never appear in public events or summaries.
- Long-running tools use an accepted durable owner or are explicitly unsupported.

R6 secret-reference work is conditional supporting scope: implement only the minimum required if existing protected input and environment mechanisms cannot safely launch Hermes.

### H1D - Acceptance

- ChatGPT searches Hermes without loading every deferred schema into the connector.
- ChatGPT inspects and invokes one read-only built-in or plugin tool.
- ChatGPT invokes one Hermes-connected MCP tool without tool-specific CodexBridge code.
- Evidence proves no Hermes model-agent invocation occurred.
- Exact tool/schema identity and arguments are durable.
- One approved reversible side effect executes once and its external outcome is verified.
- Ambiguous responses reconcile without duplicate mutation.
- Accepted asynchronous calls have deterministic restart and cancellation behavior.
- Credentials and protected results stay out of bounded public output.

No real-money purchase, booking, cancellation, or refund is used as an acceptance test.

## H2 - Shared Multi-Session Hermes Service

Status: **deferred until Trading Lab is complete and the subsequent CodexBridge reliability audit has passed**.

The completed H1 path remains the safe compatibility baseline: each ChatGPT request launches one durable, schema-bound Hermes companion process. Commit `9bb17f0452fe9419138b6f99a606a885bbe3a664` removes the incorrect repository-wide serialization from new Hermes companion runs, so independent discovery and tool calls can execute concurrently without taking a CodexBridge repository operation lock. This fixes the immediate multi-chat blocker but does not turn the one-request companion into the final shared service.

H2 will replace per-call companion startup as the primary path with one persistent Hermes service that is independent of any repository and supports concurrent, isolated sessions from multiple ChatGPT conversations. Repository identity is optional context supplied only to tools that genuinely need it; Trading Lab work, repository writes, and ordinary Search Console or other read-only calls must not block one another merely because they pass through the same CodexBridge instance.

### H2A - Shared service and session contract

- Run one version-pinned, supervised Hermes service with explicit health, build, protocol, registry-generation, and effective-schema identity.
- Give every invocation a durable CodexBridge run ID plus a distinct Hermes request/session ID; one chat must never consume, cancel, or publish another chat's result.
- Preserve current exact tool identity, tool-schema hash, accepted arguments, bounded output, protected evidence, cancellation, restart recovery, and no-model-runtime guarantees.
- Keep the current one-request companion as a bounded fallback and compatibility path until persistent-service acceptance is complete.
- Permit multiple read-only discovery, description, and tool-call requests to overlap without a repository lock or one global Hermes execution lock.

### H2B - Narrow concurrency controls

Serialize only the resource that can actually conflict:

- Hermes installation, removal, upgrade, configuration editing, and registry reload use one Hermes-administration lock.
- Shared credential changes use a credential-specific lock and never expose secret values in public state.
- Providers and individual tools may declare concurrency and rate limits without reducing unrelated tools to one global queue.
- Mutations targeting the same external resource require provider-appropriate idempotency, reconciliation, or a resource-scoped mutation lock.
- Read-only calls remain concurrent unless the provider itself requires a narrower limit.

### H2C - Acceptance

- Five independent ChatGPT sessions can concurrently search, describe, or invoke bounded read-only Hermes tools and receive isolated durable results.
- A long Trading Lab or repository run can overlap with a Search Console read without either acquiring or waiting on the other's repository lock.
- Cancelling one long Hermes call terminates only its owned execution and does not interrupt other sessions or the shared service.
- Registry reload is serialized, publishes one new generation atomically, and causes stale schema-bound requests to fail closed rather than execute against drifted tools.
- Two unrelated providers can run concurrently, while two mutations against the same external resource are serialized or safely reconciled.
- Service restart adoption, health recovery, output bounds, protected evidence, and fallback to the one-request companion are demonstrated under live acceptance.

Do not begin H2 implementation during TL1 or later Trading Lab units. First complete Trading Lab, perform its defect pass, then complete the planned whole-Bridge reliability audit and stabilisation gate. H2 becomes eligible only from that fresh audited baseline.

## OP1 - Evidence-Driven Real-Project Pilot

Status: **complete; observation review closed on 2026-07-20**.

The repository-owned evidence log is [`docs/pilot-evidence.md`](docs/pilot-evidence.md). Its first entry records ordinary durable validation, one pre-acceptance rejection because parallel PowerShell execution was disabled in the live capability configuration, and successful serial recovery with no lost or duplicated work. A second entry records a successful durable Hermes-backed connected-MCP call under registry generation `89`, with exact tool/schema identity, no model runtime, empty protected stderr, and no lost or duplicated work after correcting one caller-side PowerShell invocation mistake. A third entry records a second pre-acceptance parallel rejection under the same live build during a genuinely independent two-test workload. A fourth entry records a clean durable serial regression of the reversible-side-effect and lifecycle fixture with five passing tests, one worker claim, one terminal publication, and no repository mutation. A fifth entry proves the repeated parallel rejection was live configuration drift rather than a code defect: `parallel_execution.enabled` remained `false` despite the completed X2A contract. The ignored config was changed to `true`, validated, and hot-reloaded without restarting CodexBridge or Cloudflare; public group `20260720T010132Z_powershell_group_3da40097` then completed two overlapping child runs successfully. A sixth entry exercises the repaired capability on a real two-test workload: the first group exposed the known shared Windows pytest-temp permission problem, while an immediate retry with isolated repository-owned basetemps completed both children concurrently with `5 passed` and `6 passed`. A seventh entry records a successful schema-bound Hermes `read_file` call against the live OP1 section of `PLANS.md` under registry generation `79`, with the exact tool schema, accepted arguments, no model runtime, empty protected stderr, and no repository mutation after correcting one caller-side request-construction mistake. An eighth entry exercises a Hermes-connected reversible action under registry generation `89`: an intentionally ambiguous post-commit response was authoritatively reconciled at exactly one application, replay returned `applied: false`, reversal succeeded, and final reconciliation proved absence. Several caller-harness and transport mistakes caused bounded failed attempts but no lost or duplicated work. A ninth entry reruns the complete seven-test Windows parallel lifecycle acceptance suite through the durable validation gateway, covering fan-out, restart adoption, exact cancellation, and pending-child refill with no lost or duplicated work. A tenth entry exercises the complete live service self-check, promotes the known stale `run_start` schema assertion from observation to a bounded repair, and restores the full gate to `1194 passed, 5 skipped` with healthy imports, configuration, dependencies, stores, and HTTP transport. An eleventh entry exercises bounded real-service capability and health paths: Cloudflare correctly reports no configured repository profiles, while Docker reports an installed Windows client and Compose runtime but an unavailable Docker Desktop Linux engine. Neither condition caused mutation, lost work, duplicate work, or a CodexBridge defect, and no service was started solely for evidence. A twelfth entry repairs two real-workflow contract defects: `repo_query diff` no longer crashes if a Git capture stream is absent, and the advertised `stdin_text` field now UTF-8 encodes safely for byte-capable PowerShell profiles. Focused and adjacent suites passed, a server-only durable restart adopted its worker and published once, the Cloudflare PID remained unchanged, and both public paths were verified under the new build. Parallel execution is available and usable for representative validation. The formal review found no unresolved security, destructive-targeting, corruption, lost-work, duplicate-work, or continuation-blocking defect. Bounded contract defects discovered during real use were repaired and regression-locked; configuration and infrastructure availability observations remain operational evidence rather than architectural programs. OP1 is complete, no Roadmap V3 promotion threshold was crossed, and the next roadmap unit is TL0.

After H1, freeze architectural expansion and exercise:

- ordinary local repository and service work that requires no newly rented infrastructure;
- parallel build or test work;
- repeated connector use across separate ChatGPT sessions;
- Hermes-backed reads and approved reversible external actions;
- optional remote or GPU-host work only when that infrastructure is already running for an actual user-requested workload, never provisioned solely for the pilot.

Create a separate pilot evidence log. Each entry records timestamp, project, expected outcome, HEAD/build identity, relevant run/tool identities, exact failure, lost or duplicated work, recovery, attribution, reproduction frequency, and artifacts.

Record normal friction before redesign. Repair immediately only for security violations, destructive targeting, lost or duplicated work, unrecoverable corruption, or a blocker preventing continuation.

## TL - CodexBridge Trading Lab

Status: **active at TL1; TL0 accepted on 2026-07-20**.

This is a separate product roadmap. OP1 evidence has been reviewed and closed. TL0 passed against the user-established Alpari MT5 demo environment, with the retained acceptance bundle in [`docs/trading-lab-tl0-evidence.md`](docs/trading-lab-tl0-evidence.md). Trading source creation is now permitted only for the TL1 read-only adapter. Live-money execution remains unavailable and out of scope.

### Core architecture

Do not build broker connectivity from scratch.

```text
Alpari
  <->
MetaTrader 5 terminal
  <->
Official MetaTrader5 Python integration
  <->
CodexBridge Trading Lab
  <->
ChatGPT
```

The official MetaTrader 5 Python package is the broker-platform boundary for account details, symbol specifications, live bid/ask ticks, historical candles and ticks, active orders and positions, margin and profit calculations, order validation, order submission with one stop-loss and one take-profit, and completed-order/deal history.

Python communicates locally with a running MT5 terminal rather than a cloud REST API. The terminal is therefore a supervised Windows runtime dependency with explicit health, reconnect, and stale-data handling.

### Relationship with Hermes

Do not force MT5 through Hermes merely because Hermes exposes tools.

```text
CodexBridge Trading domain
  |- MT5 adapter
  |    prices, candles, account, orders, positions
  |- Trading Lab
  |    signals, threshold portfolios, simulation, results
  `- Hermes gateway
       news, economic events, and optional external research tools
```

CodexBridge owns durable trading state, account and terminal identity, signals, portfolios, positions, orders, reconciliation, and lifecycle evidence. Hermes may supply external context, but it must not own balances, positions, orders, or trade lifecycle.

### Frozen v1 experiment

```yaml
broker: Alpari
platform: MetaTrader 5
broker_environment: practice/demo

instrument: discovered from the connected Alpari MT5 terminal
analysis_timeframe: 4H
analysis_frequency: once per hour

decisions:
  - LONG
  - SHORT
  - NO_TRADE

confidence_range: 50-99

virtual_portfolios:
  thresholds: T50 through T99
  baseline_source: actual Alpari MT5 account equity and currency captured at experiment start
  example_baseline: 1000 USD for the current practice account
  initialization: each threshold portfolio is an independent clone of the captured baseline
  allocation_per_trade: 1 USD normalized virtual notional
  maximum_combined_allocation: 20 percent of each portfolio's own current equity
  cohort_boundary: deposit, withdrawal, account reset, or intentional baseline change starts a new experiment cohort

trade_structure:
  entry: one market entry
  stop_loss: one fixed price
  take_profit: one fixed price

excluded:
  - trailing stops
  - multiple take-profits
  - partial exits
  - scaling in or out
  - fixed holding deadline
  - confidence-based position sizing
  - leverage optimisation
  - real-money execution
```

For v1, remove entry zones and pending-order logic. When the current executable price is unsuitable, ChatGPT returns `NO_TRADE`. Pending limit and stop entries are a later leaf after the market-entry trunk is stable.

### Exact signal contract

```yaml
signal_id:
created_at_utc:
broker: alpari
symbol:
analysis_timeframe: 4H

decision: LONG | SHORT | NO_TRADE
confidence: 50-99 | null

bid:
ask:
spread:
market_data_timestamp:
latest_completed_4h_candle:
developing_4h_candle:

entry_type: MARKET
entry_reference_price:
stop_loss:
take_profit:
risk_reward:

reason:
news_context:
market_snapshot_id:
```

Validation is deliberately narrow:

- `LONG`: `stop_loss < executable entry < take_profit`;
- `SHORT`: `take_profit < executable entry < stop_loss`;
- the bridge calculates risk/reward but does not impose an arbitrary minimum or relocate ChatGPT's stop-loss or take-profit;
- `NO_TRADE` has no executable entry, stop-loss, take-profit, or confidence-driven allocation.

### Confidence behaviour

One signal receives one score. For a `SHORT` signal with confidence `73`, portfolios `T50` through `T73` are eligible and `T74` through `T99` do not trade.

Each threshold portfolio is independent. A portfolio already holding the symbol skips the signal while another eligible portfolio may still enter.

### Honest execution-price rules

The simulator must not use midpoint prices.

- open long at ask;
- close long at bid;
- open short at bid;
- close short at ask.

This naturally includes broker spread.

A trade ends only when its take-profit or stop-loss is reached. The 4H interval is the analysis candle timeframe, not a four-hour holding deadline.

After connectivity loss, CodexBridge retrieves missed ticks where available. If both stop-loss and take-profit appear inside the same historical candle and reliable tick ordering cannot be recovered, the outcome is `AMBIGUOUS_DATA`; the system must never choose the favourable result silently.

### Main components

#### 1. MT5 provider adapter

Responsibilities:

- connect and authenticate to the local MT5 terminal;
- discover broker-specific symbols rather than hardcoding names such as `BTCUSD`;
- read complete symbol specifications;
- retrieve fresh bid/ask ticks;
- retrieve completed and developing 4H candles;
- retrieve historical ticks after downtime;
- inspect account, connection, and terminal health;
- later, submit demo orders and inspect positions, orders, deals, and history.

#### 2. Immutable market-packet builder

Every hourly analysis receives one immutable packet:

```yaml
packet_id:
provider:
server:
account_environment: demo
symbol:
created_at_utc:

symbol_specification:
  digits:
  tick_size:
  tick_value:
  contract_size:
  minimum_volume:
  volume_step:
  margin_information:

latest_tick:
  bid:
  ask:
  timestamp:

completed_4h_candles: 100-200
developing_4h_candle:
data_age:
warnings:
content_hash:
```

The packet builder also produces a simple candlestick PNG from exactly the same data. Structured values remain authoritative; the chart is interpretive assistance only.

#### 3. Immutable signal journal

After submission, direction, confidence, entry, stop-loss, take-profit, reason, market snapshot, and timestamp cannot change. A mistaken signal may be marked invalid before execution, but it must never be edited after later market movement becomes visible.

#### 4. Threshold portfolio engine

Maintain 50 independent portfolios, `T50` through `T99`, each storing:

- experiment cohort identity;
- baseline equity and currency captured from the Alpari MT5 account at experiment start;
- current equity;
- available allocation;
- open position;
- completed trades;
- net P&L;
- maximum drawdown.

Every threshold portfolio begins as an independent clone of the same captured account equity and currency. For the current practice account, the example baseline is 1,000 USD. The portfolios do not share or divide the broker balance. After initialization, each evolves independently from its own trades and must not be continuously resynchronised to the broker account.

A deposit, withdrawal, account reset, or intentional baseline change closes the current baseline definition and starts a new experiment cohort; it must not rewrite the history or current equity of an existing cohort.

The 1 USD experiment allocation means normalized virtual notional at 1x exposure. It is not an MT5 lot and not leveraged broker margin, preventing broker minimum volume and leverage from contaminating confidence-threshold testing. Maximum combined active allocation remains capped at 20 percent of each portfolio's own current equity.

#### 5. Deterministic trade supervisor

This component performs no analysis. It only:

- watches bid/ask;
- opens eligible virtual positions;
- detects the first stop-loss or take-profit event;
- calculates P&L and recorded costs;
- updates threshold portfolios;
- recovers open trades after service restart;
- resolves every position exactly once.

It must reuse CodexBridge durable workers, leases, heartbeats, protected evidence, process ownership, cancellation, and restart reconciliation rather than creating another durability subsystem.

#### 6. Evaluation engine

Report per threshold:

- signal count;
- entered-trade count;
- win rate;
- net P&L;
- average return;
- profit factor;
- maximum drawdown;
- longest losing streak;
- average stop-loss distance;
- average take-profit distance;
- average risk/reward;
- monthly results;
- results by confidence band.

Do not select the single highest-profit threshold. Prefer positive performance with enough trades, acceptable drawdown, stability across neighbouring thresholds, and persistence across genuinely fresh periods.

### CodexBridge tool surface

Read tools:

- `trading_provider_health`;
- `trading_list_symbols`;
- `trading_symbol_specification`;
- `trading_market_packet`;
- `trading_open_virtual_positions`;
- `trading_signal_get`;
- `trading_signal_list`;
- `trading_threshold_report`;
- `trading_portfolio_status`.

Write tools:

- `trading_signal_submit`;
- `trading_signal_cancel_before_entry`;
- `trading_lab_start`;
- `trading_lab_stop`;
- `trading_lab_reset`.

Separately gated demo-execution tools may later include:

- `trading_demo_order_submit`;
- `trading_demo_order_close`;
- `trading_demo_order_cancel`;
- `trading_demo_reconcile`.

There is no live-order tool in v1.

### Safety model

Trading environment and autonomy remain separate axes. The current CodexBridge deployment remains permissive-only; any future restoration of additional autonomy profiles must never change trading execution mode implicitly.

```yaml
execution_mode:
  - internal_paper
  - broker_demo
  - live
```

Selecting `permissive` must never promote `internal_paper` or `broker_demo` to `live`.

Hard controls:

- credentials never appear in logs, events, summaries, or public tool output;
- demo and live accounts use separate configuration and identity;
- global trading kill switch;
- idempotency key on every signal and order;
- one active position per symbol per threshold;
- 20 percent combined allocation cap;
- duplicate-order detection;
- broker-ticket reconciliation;
- stale-data rejection;
- disconnected-terminal rejection;
- explicit environment identity on every packet, signal, position, and order;
- no automatic promotion to live execution.

### Roadmap

#### TL0 - Alpari/MT5 acceptance spike

Status: **complete**.

Acceptance completed on 2026-07-20. The exact broker symbol is `BITCOIN_i`; the demo account, contract specification, live bid/ask, completed and developing H4 candles, minimum-volume buy and sell checks, minimum demo buy and sell round trips, order/position/deal/history retrieval, and terminal restart/reconnection all passed. The account baseline was read from MT5 as `1000.00 USD` before the acceptance trades and ended at `998.72 USD` after two immediate spread losses; future experiment cohorts must recapture current equity and currency rather than hard-code either value. Full evidence and durable artifact identities are preserved in [`docs/trading-lab-tl0-evidence.md`](docs/trading-lab-tl0-evidence.md).

Before repository implementation:

- create an Alpari MT5 practice account;
- install and log into MT5;
- discover the exact BTC symbol;
- read its complete contract specification;
- confirm fresh bid and ask;
- retrieve completed and developing 4H candles;
- confirm both buy and sell are supported;
- run `order_check` for buy and sell with one stop-loss and one take-profit;
- place the smallest demo buy and sell;
- confirm account, position, order, deal, and history retrieval;
- capture the practice account's actual equity and currency as the candidate experiment baseline;
- restart MT5 and test reconnection.

Gate: a written evidence bundle containing symbol name, minimum volume, contract size, spread, account mode, captured account equity and currency, order-check and demo-order results, reconnection evidence, and screenshots or protected logs. The evidence must show that the baseline is read from MT5 rather than hard-coded; the current practice-account example is 1,000 USD.

No CodexBridge trading source file may be created before TL0 passes.

#### TL1 - Read-only MT5 adapter

Status: **in progress**.

The first read-only provider slice is complete: `codexbridge.trading.MT5Provider` now supports injectable MT5 bindings, connection and demo-account health, exact symbol discovery that distinguishes `BITCOIN_i` from `BITCOIN CASH_i`, complete contract specification, freshness-aware bid/ask ticks, completed/developing H4 separation, historical tick recovery, raw provider timestamps, and explicit broker-offset normalization. Deterministic validation run `20260720T093152Z_project_command_e980f180` reported `4 passed`.

The repository-scoped MT5 configuration boundary is also complete: trading is disabled by default, fixed to the `mt5` provider and `demo` account environment, accepts only an absolute optional terminal path, trims and validates the exact symbol, bounds provider UTC offset and tick freshness, and cannot express live execution. Validation runs `20260720T094235Z_project_command_acb39e57` and `20260720T094249Z_project_command_8e2754a6` reported `26 passed` and `4 passed`; diff-check run `20260720T094300Z_project_command_ead08d42` passed.

Remaining TL1 work: expose the configured read-only adapter through the public trading query surface, add adjacent gateway tests, then run the live Alpari demo-account smoke test before promoting TL2.

Gate: deterministic tests plus a live demo-account smoke test.

#### TL2 - Market packet and chart

Normalize broker data and produce immutable hourly packets and a chart from identical source data.

Gate: completed candles are never confused with the developing candle; timestamp, hash, and freshness tests pass.

#### TL3 - Signal journal

Implement the exact `LONG | SHORT | NO_TRADE` contract.

Gate: signals are immutable, validated, idempotent, and tied to a market-packet hash.

#### TL4 - Threshold simulator

Create `T50` through `T99` and normalized 1 USD trades.

Gate: initialize all 50 portfolios as independent clones of the captured MT5 equity and currency, then prove one confidence-73 signal enters exactly `T50` through `T73` when all are free. Eligible and ineligible portfolios must diverge independently without sharing balance or being resynchronised to subsequent broker-account equity. Simulated deposit, withdrawal, account reset, and intentional baseline change events must start a new experiment cohort while preserving the prior cohort unchanged.

#### TL5 - Durable supervisor

Track bid/ask and resolve exactly one stop-loss or one take-profit event.

Gate: restart during an open trade, recover it, and resolve it exactly once; ambiguous candle ordering becomes `AMBIGUOUS_DATA`.

#### TL6 - Reports and calibration

Add threshold, confidence, drawdown, stability, and fresh-period reports.

Gate: reports reproduce exactly from the append-only event journal.

#### TL7 - Alpari demo mirror

Mirror one selected reference threshold into the actual demo account while retaining all 50 virtual portfolios.

Gate: internal and broker fills, spreads, tickets, and outcomes reconcile without duplicate orders.

#### TL8 - Hourly orchestration

Only after manual operation is trustworthy:

```text
hourly market packet
  -> ChatGPT analysis
  -> immutable signal
  -> threshold decisions
  -> deterministic monitoring
```

No forced trade is generated when the signal is `NO_TRADE`, market data is stale, the terminal is disconnected, or validation fails.

#### TL9 - Live-readiness review

There is no automatic promotion.

Review:

- broker verification and residency requirements;
- deposit and withdrawal path;
- minimum practical position;
- fees, spread, commission, and swaps;
- broker reliability;
- regulatory and tax implications;
- performance on a genuinely fresh paper sample;
- operational recovery evidence;
- whether a live tool should exist at all.

Any live-execution implementation requires a new explicit roadmap decision, separate configuration, human approval boundaries, and independent acceptance evidence.

### Build/reuse boundary

Reuse:

- MT5 terminal;
- official MetaTrader5 Python package;
- Alpari price feed and demo execution;
- CodexBridge durability, policy, artifact, cancellation, and reconciliation infrastructure;
- Hermes external research tools.

Build:

- provider-neutral trading domain;
- immutable market packets and signal journal;
- `T50` through `T99` virtual portfolios;
- deterministic stop-loss/take-profit supervisor;
- confidence calibration and reporting;
- demo-order reconciliation.

Do not build a broker, general charting platform, discretionary strategy engine, or another Stream Alpha.

The immediate Trading Lab gate is TL1: implement the read-only MT5 adapter for provider health, exact symbol discovery, contract specification, fresh bid/ask ticks, completed and developing H4 candles, and historical tick recovery. TL1 must disambiguate `BITCOIN_i` from `BITCOIN CASH_i`, preserve raw provider timestamps, and normalize provider time explicitly. Deterministic tests and a live demo-account smoke test are required before TL2.

## Roadmap V3 Promotion Rules

Promote an observation when it violates a durability/security invariant, can lose or duplicate work, blocks a representative workflow, repeatedly requires manual recovery, reveals a repeated architectural pattern, or carries sufficient expected impact.

Attribute connector 502s before repair. Treat external fixture loss as infrastructure unavailability unless CodexBridge mishandles it. Write Roadmap V3 only after representative pilot evidence is reviewed.

## Deferred Work

- paid RunPod or other paid remote/GPU validation; evidence may be collected only opportunistically during actual user-requested workloads;
- broad environment and secret-reference expansion beyond H1 needs;
- a large provider-neutral synthetic acceptance matrix;
- project-memory and local-model expansion;
- supervisor, workflow, optional coding, and dashboard expansion;
- Codex re-enablement.

Historical R6, R7, P2, gate, commit, and validation specifications remain in the V2 achievement record.

## Validation and Commit Policy

For code: run focused then proportional adjacent tests, `git diff --check`, milestone-level full checks where justified, and real process/host tests when OS behavior is the subject. Commit every completed batch locally and never push without explicit instruction.

For documentation only: inspect the exact diff, run `git diff --check`, confirm only intended documentation changed, commit locally, confirm a clean worktree, and do not run the full suite.

Before every write or validation, inspect active durable runs and repository locks. Preserve unrelated work and never reset, clean, restore, discard, stash, amend, rebase, or rewrite history.
