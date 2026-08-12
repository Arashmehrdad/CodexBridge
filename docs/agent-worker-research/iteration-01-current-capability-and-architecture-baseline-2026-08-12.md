# Iteration 1 - Current Capability and Architecture Baseline

Date: 2026-08-12
Status: research only
Scope: capability and architecture baseline only; no production implementation

## Guardrails for this research track

This iteration does not authorize implementation. No Soma production source, Hermes configuration, connector state, service lifecycle, or model-worker configuration is to be changed. No commit or push is part of this iteration.

The following correction is treated as a hard research constraint:

- Soma's integrated Hermes runtime is intentionally headless. It exposes tool discovery and execution, not an independent reasoning mind.
- Parallel headless Hermes workers are execution concurrency (more hands), not reasoning subagents (more minds).
- A separately configured Hermes installation using a weak or cheap model could later be studied as a scout, but its interpretations would require stronger-model adjudication.
- `PINNED_HERMES_REVISION` must be compared with the configured Hermes checkout's own Git HEAD. Soma repository HEAD is a different repository identity and is not revision-drift evidence.

## Exact questions investigated in Iteration 1

1. What delegation, subagent, worker, plugin/skill, MCP, long-running, and parallelism primitives does OpenAI expose as of 2026-08-12?
2. Which of those primitives are available in normal ChatGPT, which belong to ChatGPT Work, which are API/Agents SDK capabilities, and which are Codex-specific?
3. What does Soma's current Hermes companion/service actually own, and how much concurrency exists today?
4. Does Soma already contain a provider-neutral durable worker substrate, or only Hermes-specific machinery?
5. Which major architectural options deserve comparison in later iterations?

## Source discipline

OpenAI capability claims in this iteration were checked against current official OpenAI documentation/help pages. Repository claims were checked against Soma repository source/configuration at repository HEAD `24fa7774d97e8a04bed3ec79054ae9b66182fd39` plus one read-only command that queried the configured Hermes checkout's own Git HEAD.

Facts, inferences, hypotheses, and rejected ideas are separated below. No production bug is recorded unless direct evidence confirms one.

---

# A. Current OpenAI capability baseline

## A1. Normal ChatGPT (the ordinary Chat surface)

### Facts

- OpenAI distinguishes Chat from Work. Chat is positioned as the conversational surface; Work is the longer, multi-step agent surface.
- Plugins are now the primary discovery/package surface for workflow capabilities in ChatGPT and Codex. A plugin may package Skills, Apps, and App Templates. App permissions remain the authority boundary for app-backed capabilities.
- Skills are reusable/shareable workflows containing instructions, examples, supporting resources, and optionally code. Skills are not themselves evidence of a second independent reasoning process.
- Apps/plugins can connect ChatGPT to external data and actions. MCP is part of the integration architecture, but an MCP tool endpoint is still a tool capability unless a separate reasoning model/loop exists behind it.
- Workspace Agents exist for supported Business/Enterprise surfaces. They are configured agent experiences with workspace tools and policies; they should not be conflated with a dynamic child-agent primitive in every ordinary Chat conversation.

### Surface boundary

Official subagent documentation currently names **ChatGPT Work and Codex** as the ChatGPT product surfaces that can spawn specialized agents in parallel and collect their results. I found no official source saying that every ordinary Chat conversation has that native spawn primitive. The current normal Chat conversation used for this research also exposes no native `spawn_agent`/agent-thread tool.

Therefore this research must not infer normal-Chat capability from a Work, Codex, API, or SDK feature.

## A2. ChatGPT Work (surface/account dependent)

### Facts

- Work is a distinct ChatGPT agent surface for longer multi-step work and finished deliverables.
- Current OpenAI subagent documentation says ChatGPT Work can spawn specialized agents in parallel and collect results into one response.
- Work subagents run in ChatGPT's hosted environment. The documentation explicitly recommends delegation for independent work and notes that subagents consume additional tokens.
- Work also supports long-running/scheduled work depending on account and rollout state.

### Implication

Work is now an important modern alternative/benchmark for Soma's proposed fan-out/fan-in behavior. It is not, however, evidence that Soma can invoke native Work subagents from this ordinary Chat surface or that Work's hosted lifecycle provides Soma's durable local ownership semantics.

## A3. API / Responses API

### Facts

- GPT-5.6 Responses API has a Multi-agent beta. A root model can spawn and coordinate subagents in parallel and synthesize the final response.
- OpenAI documents Multi-agent as appropriate for concrete independent workstreams (parallel research, codebase exploration, comparison, independent implementation/testing).
- OpenAI explicitly says Multi-agent is less suitable when work requires a single ordered chain, shared mutable-state contention, or a fixed deterministic execution graph.
- `max_concurrent_subagents` defaults to 3 and is the recommended default. The setting limits active subagent turns across the tree.
- In the current beta, agents in the tree use the request's model and have access to the tools configured for that request.
- Responses API function calling can issue multiple function calls in one model turn on supported models. `parallel_tool_calls=false` can force at most one function call. Parallel function calls are tool parallelism, not independent reasoning agents.
- Responses API background mode can run a response asynchronously, be polled by response ID, and continue if a streaming connection drops. This is useful execution continuity, but it is not by itself a durable application-level work DAG with mutation ownership/recovery semantics.
- Remote MCP servers/connectors can be used by Responses API. OpenAI documents approval controls for sensitive MCP actions.

### Important distinction

Responses Multi-agent is a genuine reasoning-subagent primitive, but it belongs to an API integration. Its existence does not make it callable from this normal ChatGPT conversation unless ChatGPT exposes a corresponding product/tool primitive.

## A4. OpenAI Agents SDK

### Facts

OpenAI documents two primary LLM-directed orchestration patterns:

1. **Manager / agents-as-tools** - one manager keeps ownership of the final response and invokes specialists for bounded subtasks.
2. **Handoffs** - control transfers to a specialist agent that becomes active.

The SDK also supports code-directed orchestration, including parallel runs implemented by application code. These patterns can be mixed.

### Relevance

The manager/agents-as-tools pattern is conceptually close to the proposed "Sol reasoning head -> bounded workers -> Sol synthesis" shape. But it is an application/API architecture, not proof that normal Chat exposes the same primitive.

## A5. Codex-specific subagents

### Facts

- Current Codex releases enable subagent workflows. The main thread can delegate independent parts of a coding task and collect summaries/results.
- Codex supports custom agent roles/configurations. OpenAI's guidance emphasizes keeping subagent jobs bounded and avoiding parallel write-heavy work where agents could interfere.
- Codex's subagent architecture is therefore a strong reference implementation for software-engineering delegation, but it is Codex-specific and should not become Soma's universal worker identity model by accident.

## A6. Plugins, Skills, MCP, and tools are not automatically agents

### Fact/terminology rule

A capability should be called a reasoning agent/subagent only when an independent model reasoning loop exists. A Skill is workflow guidance. A Plugin is a packaging/discovery unit. An App/MCP endpoint exposes tools/data/actions. Parallel function calling issues tools concurrently. None of those facts alone establish an independent reasoning mind.

This terminology rule is directly relevant to Soma's headless Hermes integration.

---

# B. Current Soma/Hermes architecture baseline

## B1. Hermes companion is intentionally headless

### Facts

`soma/hermes_companion_protocol.py` contains an explicit model-runtime prohibition:

- forbidden module prefixes include `hermes_agent`, `model_client`, `model_provider`, `agent_loop`, and `inference`;
- handshake construction calls `assert_no_model_runtime_initialized(...)`;
- the handshake publishes `model_runtime_initialized: false`;
- handshake verification rejects invalid model-runtime evidence.

`docs/hermes-tool-runtime-feasibility.md` likewise defines the intended boundary: Soma uses a pinned Hermes companion for registry/tool mechanics and does not initialize the Hermes agent loop/model runtime for this path.

**Conclusion (fact): integrated Hermes workers are execution workers, not reasoning subagents.**

## B2. Hermes revision identity was verified correctly

### Facts

- Soma protocol pin: `862b1b37bf0aadba3a98b3756c7d71779379b53b`.
- Configured checkout: `D:/Github/Soma/runs/hermes-pinned-validation` (resolved from `hermes_service.checkout`).
- Read-only command executed: `git -C 'D:/Github/Soma/runs/hermes-pinned-validation' rev-parse HEAD`.
- Observed configured checkout HEAD: `862b1b37bf0aadba3a98b3756c7d71779379b53b`.
- Read-only Soma run evidence: `20260811T233535Z_executable_profile_6f1ee838`; exit code 0; no changed files.

**Conclusion (fact): no Hermes revision drift was found in Iteration 1.**

Soma repository HEAD `24fa7774d97e8a04bed3ec79054ae9b66182fd39` is not part of this comparison because it identifies a different repository.

## B3. Shared Hermes worker ownership model

### Facts

`PersistentHermesWorker` owns one companion process. Requests are serialized within that process. Service-level concurrency is obtained by having multiple worker processes.

`HermesServiceRuntime` / its generation pool:

- tracks a set of worker slots;
- leases one free ready slot to one exact `request_id`;
- prevents duplicate active request IDs;
- binds request identity to `run_id`, `request_id`, and `session_id`;
- releases the slot after the request finishes;
- validates registry generation/schema identity before dispatch.

`HermesServiceGateway` gives each call a distinct durable Soma run ID and Hermes request ID, records the request as a durable run, and keeps session-scoped ownership for result/cancellation operations.

### Cancellation fact

Hermes cancellation validates the owning request/session/run identity. If the request owns a worker, cancellation is delegated only to that worker; the persistent worker implementation terminates the owned process tree for that exact active request. A dead worker can later be replaced by the supervisor.

Cancellation cannot prove reversal of an already-issued external side effect. That remains an external-action reconciliation problem.

## B4. Current Hermes concurrency and hard limits

### Facts

Current configuration uses:

- `hermes_service.worker_count: 2`
- worker wait timeout: 30 seconds
- shared persistent service enabled

Therefore, **today's configured shared Hermes service can execute at most two Hermes requests concurrently before any narrower tool/resource/credential limit applies**, assuming both workers are healthy.

Implementation-level worker-count validation permits 1 through 32 persistent Hermes workers, but 32 is an implementation ceiling, not a recommendation for Soma's future worker fan-out.

Additional concurrency controls are intentionally narrow:

- a global administration lock covers Hermes install/upgrade/config/removal/reload operations;
- per-tool rules can impose `max_concurrent` and minimum intervals;
- per-credential locks serialize credential-sensitive work without exposing secret values;
- resource mutation locks serialize calls that declare the same resource key;
- unrelated tools/resources remain concurrent.

## B5. Soma already has a separate durable parallel execution primitive

### Facts

The existing PowerShell group substrate is not Hermes-specific:

- it durably reserves a parent command group and child run identities in SQLite;
- child `run_id` and idempotency keys are unique;
- child worker lease tokens are persisted;
- all children are reserved before eligible children are launched;
- pending children can be refilled as concurrency slots become available;
- group cancellation walks non-terminal children;
- `cancel_remaining_on_failure` can terminate remaining work after a failed/timed-out child.

Current configuration enables parallel execution and has no configured numeric `max_concurrent_powershell` cap. The public schema permits an explicit `requested_concurrency`, but the currently implemented group mode is lock-free (`repository_lock_policy = none`). This is a capability/limitation, not evidence that arbitrary high parallel mutation is safe.

**Conclusion (fact): Soma already has durable fan-out mechanics for homogeneous exact command work, but not yet a general heterogeneous worker DAG.**

---

# C. Does Soma already have a provider-neutral durable worker substrate?

## Facts supporting "yes, at the control-plane layer"

### Canonical task plane

`soma/tasks/models.py` and `soma/tasks/store.py` deliberately avoid controller-vendor identity. The task state vocabulary includes accepted, queued, running, awaiting-controller, paused, cancellation-pending, recovery-pending, completed, failed, cancelled, and uncertain.

Task records already carry:

- canonical task identity;
- parent/child/related/supersedes link vocabulary;
- backend kind/executor/reference;
- checkpoint/result/evidence references;
- recovery state/reason;
- state version and timestamps.

The task store explicitly says it is **not** authoritative for process/lease/lock/evidence/result bodies. Those remain in the durable run store and are referenced by opaque identity. Ownership-sensitive changes use compare-and-set state versions.

### Backend seam

`soma/tasks/backends.py` already defines an `ExecutionBackend` protocol with:

- reserve
- start
- query
- cancel
- result_reference

The default backend adapts the existing durable-run engine rather than duplicating execution logic. Backend identity is persisted at task creation and is not silently changed while a task is active.

The backend observation/result APIs intentionally expose bounded scalar/reference information rather than copying giant result bodies into the task plane.

### Provider-neutral interaction transport

`soma/worker_substrate` already contains a provider-neutral transport port for session interactions. Its dispatcher uses persist-before-send semantics and durable transport-attempt claims. If delivery outcome becomes unknown after a claim, automatic resend is forbidden rather than risking a duplicate effect.

## Facts limiting "yes"

The current canonical model is still narrow:

- `TaskKind` currently has only `durable_command`;
- `BackendKind` currently has only `soma_durable_run`;
- there is no first-class `worker_class` taxonomy;
- there is no general work-unit dependency/DAG schema;
- there is no heterogeneous worker scheduler/admission layer;
- there is no fan-in evidence envelope designed for multiple worker interpretations;
- there is no production reasoning-worker transport/backend;
- the production interaction transport is deliberately unavailable until a reviewed provider transport exists.

### Iteration 1 assessment

**Inference:** Soma already has much of the lower control-plane substrate required for a provider-neutral worker architecture - durable identity, backend references, lifecycle states, cancellation/recovery semantics, evidence-by-reference, idempotency/lease concepts, exact interaction dispatch, and a proven parallel command-group mechanism.

It does **not** yet have the upper orchestration semantics required by this research objective: work decomposition, heterogeneous worker classes, dependency scheduling, fan-in evidence contracts, reasoning backend adapters, and conflict adjudication.

A useful shorthand is: **Soma has much of the durable foundation, not yet the worker architecture.**

---

# D. Major architectural options worth comparing

These are candidates, not a decision.

## Option 1 - Keep orchestration entirely in normal ChatGPT/Sol

Shape: Sol decomposes and directly calls individual Soma tools; Soma remains execution-only.

Advantages:
- simplest mental model;
- no additional orchestration state in Soma;
- Sol retains all semantic decisions.

Risks/questions:
- decomposition state is weak across disconnect/reconnect;
- many low-level tool calls remain visible/noisy;
- recovery after partial fan-out is harder to make deterministic;
- Sol must manually rediscover which work completed.

Status: retain as baseline/control architecture for benchmarking.

## Option 2 - Soma deterministic orchestrator owns decomposition and synthesis

Shape: Soma owns the whole work graph, worker selection, and aggregation.

Advantages:
- maximum durable continuity;
- deterministic scheduling/recovery can be centralized.

Risks/questions:
- duplicates semantic planning logic that a strong Sol head already performs well;
- risks turning Soma into another reasoning agent/controller;
- requires a model in Soma if decomposition is semantic rather than rule-based.

Status: compare, but not preferred by default.

## Option 3 - Hybrid: Sol chooses/decomposes; Soma owns the durable graph; Sol adjudicates

Shape:

```
owner request
   -> Sol semantic work plan
   -> Soma persists bounded work units/dependencies/authority
   -> heterogeneous worker backends execute/retrieve concurrently where safe
   -> Soma publishes bounded structured evidence/references
   -> Sol adjudicates conflicts and synthesizes
```

Advantages:
- preserves one strong user-facing reasoning head;
- gives disconnect/reconnect continuity to a deterministic local control plane;
- cleanly separates reasoning from durable execution ownership;
- maps naturally onto Soma's existing canonical Task/backend/evidence concepts;
- can potentially add a native OpenAI reasoning-worker backend later without changing task identity/recovery semantics.

Risks/questions:
- needs a new work-unit/DAG layer or extension;
- needs a strict evidence contract;
- must prevent fan-out from multiplying mutation authority;
- must define how Sol submits/revises a graph without making duplicate work.

Status: **leading hypothesis after Iteration 1, not accepted architecture.** Later iterations must try to falsify it.

## Option 4 - Use Responses API Multi-agent / Agents SDK as the agent manager

Advantages:
- native strong reasoning subagents exist today in API form;
- OpenAI already supplies spawning/messaging/wait/synthesis primitives;
- manager/agents-as-tools is close to the desired semantic pattern.

Risks/questions:
- API capability is not the same as normal Chat product capability;
- current Multi-agent beta intentionally favors model-directed graphs, while Soma needs deterministic durable identity/recovery for external effects;
- all agents currently receive the request's tool set, so Soma still needs its own authority boundaries for mutations;
- introducing an API-side reasoning head could duplicate/compete with the normal ChatGPT head;
- account, cost, credential, and product-boundary implications are materially different.

Status: serious comparison target and possible future `reasoning_worker` backend, not an automatic replacement for Soma's durable task plane.

## Option 5 - ChatGPT Work native subagents

Advantages:
- native OpenAI product behavior already matches bounded parallel delegation plus consolidated synthesis;
- likely lower orchestration burden where the hosted Work surface is acceptable.

Risks/questions:
- separate product surface and rollout/account dependency;
- cannot assume ordinary Chat can spawn Work subagents programmatically;
- hosted Work lifecycle/permission semantics may not map one-to-one to Soma's local durable ownership or external mutation reconciliation.

Status: important UX/quality benchmark; integration feasibility remains open.

## Option 6 - Codex subagents as Soma's universal agent plane

Advantages:
- mature software-engineering subagent UX and configurable specialist roles;
- excellent reference for codebase exploration and independent coding tasks.

Risks/questions:
- Codex-specific;
- software-centric assumptions could distort retrieval/non-code worker design;
- tying canonical worker identity to Codex would make future OpenAI/native/other backends harder.

Status: reference/backend candidate, rejected as the universal architectural identity in Iteration 1.

## Option 7 - Parallel function calls / Programmatic Tool Calling for non-reasoning work

These primitives can reduce model/tool round trips for bounded tool-heavy workflows and are useful alternatives to spawning reasoning agents when the work needs more execution bandwidth rather than independent judgment.

Status: retain for later comparison under execution/retrieval worker optimization.

---

# E. Facts, inferences, hypotheses, and rejected ideas

## Confirmed facts

1. Integrated Hermes is headless and explicitly rejects model-runtime initialization.
2. Current configured Hermes service has two persistent workers; each worker serializes its own requests.
3. The configured Hermes checkout HEAD exactly matches `PINNED_HERMES_REVISION`.
4. Soma has durable exact-command parallel groups in addition to Hermes worker parallelism.
5. Soma canonical tasks already separate controller-neutral task identity from backend execution/evidence authority.
6. Soma already has an execution-backend protocol and provider-neutral interaction transport concepts.
7. OpenAI currently exposes genuine reasoning subagents in ChatGPT Work, Codex, and GPT-5.6 Responses API Multi-agent; the availability/contract differs by surface.
8. OpenAI explicitly distinguishes parallel tool calls from multi-agent delegation in its API architecture.

## Inferences

1. The existing canonical task/backend boundary is a plausible attachment point for future worker backends.
2. Soma probably does not need a second copy of worker process/evidence state; future orchestration should continue referencing authoritative backend evidence.
3. A hybrid manager location (Sol semantic decomposition + Soma durable execution graph + Sol adjudication) best matches the current separation of strengths, but this remains unproven.
4. The future worker abstraction should likely describe **capability and authority**, not provider identity. `Hermes` should be a backend implementation detail rather than the canonical definition of a worker.
5. Native OpenAI reasoning subagents are best treated as one possible backend/manager capability, not as the identity of the durable task graph.

## Hypotheses to test later

1. A small provider-neutral worker-class taxonomy (`execution`, `retrieval`, `scout`, `reasoning`) is useful enough to justify its complexity.
2. A compact evidence envelope with evidence separated from interpretation materially reduces synthesis burden without harming answer quality.
3. Four workers will often outperform one/two on separable research/inspection tasks, but eight may produce diminishing returns, duplication, and synthesis overhead.
4. Persisting the work graph in Soma will materially improve recovery after Chat disconnects compared with Sol-only orchestration.
5. Mutation-capable work should have stricter concurrency/authority admission than read/retrieval work, potentially including a single-writer rule per resource.

## Rejected ideas in Iteration 1

Rejected means "do not use as a research premise", not "never implement".

- **Calling parallel headless Hermes workers subagents.** Rejected: they have no independent reasoning model.
- **Comparing Soma HEAD with the Hermes pin to detect revision drift.** Rejected: different repository identities. Correct comparison was performed and matched.
- **Assuming Responses/Agents SDK Multi-agent is available inside this normal Chat conversation.** Rejected: product/API surface boundaries are explicit.
- **Making Codex agent identity the universal Soma worker identity.** Rejected as an architectural premise because it creates provider coupling.
- **Assuming more concurrency is automatically better.** Rejected. OpenAI's own current guidance warns against subagents for ordered chains and shared mutable-state contention.
- **Moving external mutation authority into every spawned worker by default.** Rejected as unsafe architecture; later iterations must define explicit authority grants and ambiguous-outcome handling.

## Confirmed bugs

None recorded in Iteration 1.

Observed limitations (not bugs):

- current task/backend enums are single-kind/single-backend;
- current PowerShell parallel-group implementation is lock-free only;
- current production provider interaction transport is intentionally unavailable;
- current Hermes service configuration has only two worker slots.

---

# F. Iteration 1 baseline answer

The original architecture hypothesis is **not disproved**, but it must be updated for the August 2026 capability landscape.

The important update is that genuine OpenAI subagents now exist on multiple surfaces. Therefore Soma should not invent a provider-specific pseudo-agent architecture merely to simulate a capability OpenAI may later expose directly to normal Chat.

At the same time, OpenAI's native multi-agent mechanisms do not eliminate Soma's durable-control-plane problem. OpenAI explicitly positions model-directed Multi-agent away from fixed deterministic graphs and shared mutable-state contention, while Soma's value is precisely durable ownership, local/external execution control, cancellation, recovery, evidence, and mutation safety.

The strongest Iteration 1 candidate is therefore the **hybrid** architecture:

- Sol remains the user-facing semantic reasoning head and chooses decomposition.
- Soma owns durable work-unit identity, dependencies, execution admission, cancellation, recovery, evidence references, and mutation authority.
- Headless Hermes is one execution backend, not an agent.
- Retrieval and future scout/reasoning backends can be added behind provider-neutral contracts.
- Sol receives bounded structured fan-in and performs conflict adjudication/final synthesis.

This is a provisional research direction only. It is not an implementation decision.

---

# G. Next research questions (Iteration 2 candidates)

1. **Worker taxonomy:** Is `execution_worker / retrieval_worker / scout_worker / reasoning_worker` the right contract, or should capability flags replace nominal classes?
2. **Work-unit schema:** What is the minimum durable work-unit record needed above canonical Task? Can Task itself be extended without creating a second orchestration identity?
3. **DAG semantics:** How should dependencies, readiness, timeouts, retries, partial completion, duplicate prevention, and cancellation propagation work?
4. **Evidence contract:** What minimum structure separates factual evidence/provenance from worker interpretation while bounding result size?
5. **Mutation authority:** Should mutating workers use resource-scoped single-writer admission, capability tokens/mandates, or another exact authority contract?
6. **Native OpenAI adapter:** Could Responses Multi-agent or a future normal-Chat native agent map to `reasoning_worker` without owning Soma's canonical task identity?
7. **Work benchmark:** Can ChatGPT Work native subagents serve as an external quality/latency benchmark even if Soma cannot invoke them from ordinary Chat?
8. **Parallelism benchmark design:** Which separable repo/web/test/adversarial tasks produce a fair 1/2/4/8 worker comparison, and how should duplicate work/synthesis burden be measured?
9. **Recovery:** What state must Soma persist so a reconnected Sol can deterministically continue without replaying completed or ambiguous work?
10. **Normal-Chat UX integration:** Could one future high-level Soma action start a durable internal fan-out and return one structured fan-in result without exposing low-level worker calls to the user?

Iteration 1 ends here. No Iteration 2 experiments were launched.

---

# Sources consulted

## Current official OpenAI primary sources

- OpenAI Help Center, **ChatGPT Work and Codex**: https://help.openai.com/en/articles/20001275/
- OpenAI ChatGPT/Codex docs, **Subagents**: https://developers.openai.com/codex/agent-configuration/subagents
- OpenAI API docs, **Multi-agent**: https://developers.openai.com/api/docs/guides/responses-multi-agent
- OpenAI API docs, **Function calling**: https://developers.openai.com/api/docs/guides/function-calling
- OpenAI API docs, **Background mode**: https://developers.openai.com/api/docs/guides/background
- OpenAI API docs, **MCP and Connectors**: https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- OpenAI Agents SDK, **Agent orchestration**: https://openai.github.io/openai-agents-python/multi_agent/
- OpenAI Agents SDK, **Agents**: https://openai.github.io/openai-agents-python/agents/
- OpenAI Help Center, **Skills in ChatGPT**: https://help.openai.com/en/articles/20001066
- OpenAI Help Center, **Plugins in ChatGPT and Codex**: https://help.openai.com/en/articles/20001256
- OpenAI Help Center, **ChatGPT Workspace Agents for Enterprise and Business**: https://help.openai.com/en/articles/20001143-chatgpt-workspace-agents-for-enterprise-and-business

## Soma repository evidence

Primary files inspected:

- `soma/hermes_companion.py`
- `soma/hermes_companion_client.py`
- `soma/hermes_companion_protocol.py`
- `soma/hermes_service.py`
- `soma/hermes_service_gateway.py`
- `soma/hermes_service_process.py`
- `soma/hermes_service_supervisor.py`
- `soma/hermes_concurrency.py`
- `docs/hermes-tool-runtime-feasibility.md`
- `soma/tasks/models.py`
- `soma/tasks/store.py`
- `soma/tasks/backends.py`
- `soma/tasks/manager.py`
- `soma/worker_substrate/transport.py`
- `soma/worker_substrate/dispatch.py`
- `soma/parallel_groups.py`
- `soma/job_manager.py`
- `config.yaml`

Legacy architecture context was also compared with **CodexBridge Local Agent Expansion Roadmap v2**. It already established the useful separation "ChatGPT decides / local agent operates / durable jobs persist / Codex handles high-value coding"; this iteration updates that older framing for Soma's current task plane and OpenAI's August 2026 native subagent capabilities.
