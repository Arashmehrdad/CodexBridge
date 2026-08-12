# G5 OAI-R1 Provider Pilot Preflight - 2026-08-12

STATUS: READY_FOR_OWNER_AUTHORIZATION

No provider call was made by this preflight.

## Authority

- Canonical implementation plan: `docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md`
- Canonical plan SHA-256: `fa2afb72e51e5cc4494f29b7470eb33cd8a951144a2bc78db5e65a6d8301bea2`
- G4 acceptance: `53b317f9b7e6c169a5d87e1418c2d34b5910f86d`
- Branch: `lane/memory-integration-foundation-1`

Per G5, real provider execution is forbidden until the owner explicitly authorizes this exact named pilot and spend ceiling.

## Current official documentation refresh

Documentation was refreshed on 2026-08-12 from current OpenAI primary sources before selecting the pilot.

Observed current contract facts:

- OpenAI recommends the Responses API for reasoning/tool-calling/multi-turn workflows.
- Current GPT-5.6 model family exposes `gpt-5.6-sol`, `gpt-5.6-terra`, and `gpt-5.6-luna`; Luna is the cost-sensitive tier.
- `gpt-5.6-luna` supports the Responses API, streaming, function calling, and Structured Outputs.
- Current documented Luna token prices are USD 1.00 / 1M input tokens, USD 0.10 / 1M cached input tokens, and USD 6.00 / 1M output tokens; explicit cache writes, when used, are billed above normal input rate. This pilot does not enable explicit prompt-cache writes.
- Responses expose durable status values including `queued`, `in_progress`, `completed`, `failed`, `cancelled`, and `incomplete`.
- Responses usage exposes input, cached-input, output, reasoning-token, and total-token counts.
- Background Responses are retrievable and cancellable through the official Python client.
- The official Python client exposes `responses.create`, `responses.retrieve`, and `responses.cancel` and exposes the HTTP `x-request-id` as `_request_id`.
- Responses use application-state storage by default; background mode requires provider-side application state. The pilot packet therefore contains only synthetic disposable text and no repository/source secrets.

Primary documentation consulted:

- OpenAI API model catalog / GPT-5.6 guidance;
- GPT-5.6 Luna model page;
- Responses API/streaming reference;
- OpenAI platform data controls;
- official `openai-python` repository and generated Responses API surface.

This file records the selected pilot contract, not a permanent provider capability assumption. G5.1 must capture returned model/status/schema evidence and treat drift as evidence.

## Exact pilot identity

Pilot name:

`OAI-R1`

Purpose:

Single-agent durable OpenAI Responses pilot proving real provider identity capture, restart retrieval, cancellation behavior, structured evidence output, usage/cost evidence, and safe create-ack uncertainty handling beneath the already accepted provider-neutral Soma reasoning backend.

Provider/backend path:

`OpenAI Responses API -> Soma OAI-R1 adapter -> existing ReasoningBackendStore -> canonical reasoning Task`

SDK:

`openai==2.45.0`

The dependency must be isolated to the provider adapter path. Existing fake reasoning behavior and local-model/Ollama paths remain unchanged.

Model:

`gpt-5.6-luna`

Reasoning:

`reasoning.effort = low`

Execution mode:

- `background = true`;
- `store = true`;
- no conversation object;
- no `previous_response_id`;
- no provider-native subagents;
- no built-in tools;
- no MCP;
- no web/file search;
- no code interpreter/shell/apply-patch/computer use;
- `tool_choice` effectively none because the tools array is empty;
- read-only synthetic input only.

## Credential source

Exact credential source:

`OPENAI_API_KEY` process environment variable.

Rules:

- key value is never written to repository files, run artifacts, SQLite evidence, logs, exception strings, or acceptance records;
- G5.1 may check only whether the variable is present/non-empty before attempting a provider call;
- no key discovery from browser/session/config history;
- no credential creation/rotation in this lane.

If `OPENAI_API_KEY` is absent, G5.1 stops before provider execution.

## Proposed spend and request ceilings

OWNER APPROVAL REQUIRED before any create call.

Proposed total OAI-R1 spend ceiling:

`USD 0.25`

Hard local request bounds for the accepted pilot:

- maximum real Responses create calls: 4;
- maximum input tokens allowed by pilot packet per create: 8,192;
- `max_output_tokens`: 2,048 per create, including reasoning tokens according to the Responses contract;
- provider-native concurrency: 1;
- no paid built-in tool calls;
- no automatic provider-create retry after crossing Soma's send boundary;
- stop immediately if cumulative measured/upper-bound cost would exceed USD 0.25.

At the currently documented Luna rates, the declared token maxima are comfortably below the proposed ceiling even across four bounded creates; the USD 0.25 limit remains the authoritative spend boundary.

## Disposable read-only assignment packet

G5.1 uses a committed synthetic fixture, not live repository content.

Packet goals:

- six short synthetic fact records with stable line/record locators;
- three explicit fact keys the worker must recover;
- one deliberately contradictory pair the worker must represent as uncertainty/conflict rather than silently resolve;
- no personal data;
- no secrets;
- no external URLs;
- no instructions to execute tools;
- byte-identical replay from committed fixture bytes.

The assignment asks the provider only to analyze the supplied packet and return the bounded semantic evidence payload.

The packet SHA-256 and exact bytes must be committed before the first provider call and recorded in the pilot evidence.

## Output contract

The provider does not author canonical Soma identity or provenance.

Provider structured output contains only bounded semantic fields needed to construct an `EvidenceSubmissionV1`:

- `submission_disposition`;
- `executive_summary`;
- claims with provider-local `claim_id`, claim class, optional subject/fact key, statement, and exact supporting/opposing evidence IDs;
- evidence records referring only to the supplied synthetic packet locators/fact keys/values;
- uncertainties and blockers when present.

The Responses request uses strict Structured Outputs JSON Schema.

Soma mechanically injects and validates:

- `submission_id`;
- canonical Mission/PlanRevision/WorkPackage/Outcome/Attempt/Task/backend identity;
- assignment ref/hash;
- producer backend/provider/model/adapter identity;
- source refs/hashes tied to committed packet bytes;
- usage/cost;
- provider provenance refs/hashes;
- raw provider evidence refs/hashes;
- byte accounting.

The final object must validate as the existing `EvidenceSubmissionV1` without weakening that schema. Provider output is rejected as invalid if it invents unsupported locators/fact keys, violates the strict semantic schema, or cannot be mechanically wrapped into valid `EvidenceSubmissionV1`.

## Provider event/evidence capture

Persist bounded exact evidence for each real request:

- Soma backend ref and start-attempt/request hash;
- provider `response.id` when captured;
- HTTP/OpenAI request ID (`x-request-id` / SDK `_request_id`) when available;
- returned `model`;
- raw provider status;
- response `created_at` and `completed_at` when present;
- error and incomplete-detail codes/messages in bounded redacted form;
- output item IDs/types;
- streaming event type and `sequence_number` if the optional stream-resume branch is exercised;
- last safe stream cursor/sequence if supported;
- input tokens;
- cached input tokens;
- output tokens;
- reasoning tokens;
- total tokens;
- mechanically calculated cost using the frozen pilot price table;
- cancellation request ID/status/evidence;
- exact structured-output bytes/hash;
- raw provider response/evidence root ref/hash without transcript duplication into canonical Task state.

Provider IDs remain evidence/provenance only and never become canonical WorkPackage identity.

## Timeout and polling

Per-create provider wall-time ceiling:

`180 seconds`

Polling procedure after a captured response ID:

1. persist the provider response ID/binding before relying on further provider progress;
2. release/reconstruct the adapter object to simulate controller/client restart;
3. call `responses.retrieve(response_id)` using the same environment credential;
4. poll at a bounded 1-2 second cadence only while status is `queued` or `in_progress` and until the local wall-time ceiling;
5. map terminal raw provider status to subordinate ReasoningBackend observation evidence;
6. never create a replacement response merely because polling/retrieval failed.

Stream cursor continuation is supplementary. If the current SDK/API supports resuming a background stream by response ID and cursor/sequence, exercise one bounded continuation; otherwise record it as unsupported/unmeasured rather than inferring semantics.

## Cancellation procedure

Cancellation is tested only after a provider response ID has been captured and durably bound.

Procedure:

1. create one synthetic background response intended to remain active long enough for cancellation;
2. persist response ID and current raw status;
3. call `client.responses.cancel(response_id)` exactly once from the canonical cancellation path;
4. persist cancellation request/evidence;
5. retrieve/poll the same response ID until provider status converges to a terminal value or the local wall-time ceiling expires;
6. replay the same Soma cancellation request and prove no second provider cancellation side effect is required for canonical convergence;
7. never map a provider cancellation acknowledgement directly into Task success/failure without the existing TaskManager reconciliation rules.

If the response completes before cancellation wins the race, record the measured race and retry only if another bounded create remains inside the owner-approved create/spend ceiling.

## Create-ack ambiguity design

The critical failure is after Soma crosses its durable send boundary but before a provider response ID is durably captured.

G5.1 must include an injected adapter fault at exactly this point around one real create attempt:

- Soma reserves backend identity and claims the start attempt;
- Soma enters the existing send boundary, making the start conservatively `outcome_unknown`;
- one real `responses.create` request is issued;
- test injection discards/interrupts provider binding persistence before the returned response ID is committed to Soma;
- restart reconstructs the backend from SQLite;
- the backend remains `outcome_unknown` / provider binding `uncertain`;
- automatic `responses.create` replay is forbidden;
- no attempt is made to guess provider identity from timestamps/content;
- the ambiguous provider operation may finish orphaned, but canonical authority remains safe.

A separate known-ID path proves that when response ID capture succeeded, restart retrieval is exact.

This intentionally distinguishes:

`known provider ID recovery` from `unknown create outcome containment`.

## G5.1 implementation scope after approval

Expected source/test additions are internal only, for example:

- `soma/reasoning/openai_responses.py`;
- provider pilot fixture/contracts under `tests/fixtures` or `docs/agent-worker-research/fixtures`;
- deterministic fake OpenAI client tests for all transitions before real calls;
- one bounded real-pilot harness/evidence writer;
- tests covering exact ID binding, restart retrieval, cancellation replay, structured-output validation, usage/cost accounting, provider error mapping, and create-ack uncertainty.

No public gateway operation is added. Existing public schema/inventory remains unchanged.

## Promotion criteria for OAI-R1

OAI-R1 passes only if measured evidence demonstrates all of:

1. provider response ID is captured and durably bound before normal recovery depends on it;
2. a new adapter/process object retrieves the same known response after restart;
3. cancellation semantics and races are measured and canonical replay is idempotent;
4. structured provider output mechanically validates into `EvidenceSubmissionV1`;
5. usage and cost evidence are captured and remain under the owner-approved ceiling;
6. no tool/protected mutation capability is exposed;
7. send-boundary create ambiguity with no captured response ID remains `outcome_unknown` and never triggers blind duplicate create;
8. fake reasoning backend remains green;
9. affected reasoning/Task/Company Kernel/worker evidence tests remain green.

Failure of any item prevents promotion and prevents G5.2 from inheriting an assumed durability contract.

## Owner authorization gate

No provider execution is authorized by this document.

To authorize G5.1 exactly as specified, owner approval must name both the pilot and ceiling, for example:

`Approve OAI-R1 with a USD 0.25 total spend ceiling.`

Any different model, provider route, tool access, create-count limit, or spend ceiling requires a revised preflight or explicit amended authorization before execution.
