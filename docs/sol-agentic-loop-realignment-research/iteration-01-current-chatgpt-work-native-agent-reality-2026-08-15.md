# Iteration 1 - Current ChatGPT Chat / Work / Native-Agent Reality

Date: 2026-08-15
Status: research only
Track: Sol-centric durable agentic-loop realignment
Repository HEAD inspected: `79632dc9dcd7cbe055570163183a3556677de309`

## Scope and hard constraints

This iteration establishes the current factual OpenAI product model for ChatGPT Chat, ChatGPT Work, native subagents, Codex, and adjacent agent surfaces, then compares that model with Soma's current architecture.

No implementation is authorized by this document. No runtime/service restart, Company activation, reasoning-provider activation, Codex use, Codex App Server/API/CLI use, provider generation, push, production config change, or modification of `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` occurred.

The Company programme remains frozen. Company-related files are inspected only as architecture evidence.

Classification labels used below:

- **DOCUMENTED FACT** - current official OpenAI documentation.
- **REPOSITORY FACT** - current Soma source/config/history evidence.
- **OWNER REQUIREMENT** - explicit owner direction for this research track.
- **INFERENCE** - conclusion supported by facts but not itself directly documented.
- **OPEN QUESTION** - deliberately unresolved pending later iterations.

---

## 1. Current OpenAI product surface model

### 1.1 Chat and Work are distinct ChatGPT experiences

**DOCUMENTED FACT**

OpenAI currently describes ChatGPT as containing Chat and Work, with Codex as a separate software-development view in the desktop app.

The official Help Center distinction is:

- **Chat**: fast conversational assistance, questions, search, brainstorming, everyday help.
- **Work**: an agent for longer, multi-step work and finished deliverables.
- **Codex**: a separate software-development surface for writing/debugging code, tests/commands, diffs, repositories, and developer tooling.

Source:

- OpenAI Help Center, `ChatGPT Work and Codex`, updated August 2026: https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex

**DOCUMENTED FACT**

Work is available as a ChatGPT surface on eligible web/mobile accounts and in the desktop app. Work can run in cloud mode, and desktop Work can use local files and desktop apps when permitted. Chat remains available independently of Work/Codex enablement.

**INFERENCE**

Soma should not model `ChatGPT` and `Work` as separate independent reasoning providers. Work is a product operating surface inside ChatGPT, while Codex is a distinct specialized development surface.

### 1.2 Work is already an agentic control surface

**DOCUMENTED FACT**

OpenAI's current product page states that ChatGPT Work is powered by GPT-5.6. It says Work gathers context, plans the approach, and takes actions across tools, files, and desktop apps. OpenAI also exposes configurable starting model and reasoning level for Work where workspace controls permit it.

Sources:

- OpenAI, `ChatGPT Work for every team`: https://openai.com/chatgpt-work/
- OpenAI Help Center, `ChatGPT Work and Codex`: https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex

**DOCUMENTED FACT**

Work can run once, repeat on a schedule or trigger, and monitor changes through Scheduled Tasks. Users can review progress, answer questions, redirect the work, and approve important actions.

**INFERENCE**

A second always-on model-driven planning/reasoning loop underneath Work would duplicate native product behavior unless Soma can demonstrate a missing capability that Work does not provide. Soma's default role under Work should therefore be evaluated as durability/execution/state/tool extension, not as replacement cognition.

### 1.3 Native subagents exist in Work

**DOCUMENTED FACT**

OpenAI's current Subagents documentation explicitly says:

- ChatGPT Work and Codex can run subagent workflows;
- specialized agents can be spawned in parallel;
- their results are collected into one response;
- Work exposes subagent activity on eligible accounts;
- in Work, the user can ask ChatGPT to delegate independent work to subagents;
- the subagents run in ChatGPT's hosted environment;
- at most intelligence levels delegation is explicit, while Ultra can proactively delegate when parallel agents materially improve speed or quality;
- each subagent does its own model and tool work, so subagents consume additional tokens.

Source:

- OpenAI / ChatGPT Learn, `Subagents`: https://learn.chatgpt.com/docs/agent-configuration/subagents

**DOCUMENTED FACT**

OpenAI recommends subagents primarily for separable parallel work such as exploration, tests, triage, log analysis, summarization, and other bounded independent tasks. It warns that parallel write-heavy work can increase conflicts and coordination overhead.

**OWNER REQUIREMENT**

Subagents are not intended to become the primary reasoning brain for Soma. Their appropriate future role, if used, is bounded delegated work whose results return to the main ChatGPT/Sol decision process.

**INFERENCE**

The owner's proposed use of native subagents for bounded parallel inspection or verification is consistent with OpenAI's current product guidance. Building a mandatory Soma-level `reasoning_worker` merely to obtain parallel cognition would now duplicate a capability Work already exposes.

### 1.4 Ordinary Chat is not documented as having the same native subagent spawn primitive

**DOCUMENTED FACT**

The current official Subagents page names **ChatGPT Work and Codex** as the product surfaces that expose subagent workflows. The current `ChatGPT Work and Codex` article positions ordinary Chat separately as the fast conversational surface.

**DOCUMENTED FACT**

I found no current official OpenAI source stating that every ordinary Chat conversation exposes the same native subagent-spawn workflow as Work.

**INFERENCE**

Soma must be mode-aware enough not to assume a Work-native delegation primitive exists in ordinary Chat. Chat can still remain the Sol reasoning/controller surface and use Soma tools directly; native subagent delegation should be treated as capability-dependent rather than universal.

### 1.5 What remains the reasoning head when subagents are used?

**DOCUMENTED FACT**

OpenAI documents Work as the ChatGPT agent surface, powered by GPT-5.6, and documents subagents as delegated workers whose results are collected back into the Work response. The subagents each perform their own model/tool work.

**DOCUMENTED FACT**

For Codex, OpenAI explicitly describes the main thread as collecting subagent results into its final response. For Work, the same documentation says Work spawns specialized agents and collects their results in one response.

**OPEN QUESTION**

OpenAI does not publicly document enough internal scheduler/model topology to prove that every hidden internal reasoning step is always performed by one particular parent model instance. We therefore must not encode an undocumented internal implementation claim into Soma.

**INFERENCE**

The architecture-relevant public contract is sufficient: the user-facing Work thread remains the coordinating/synthesis surface and subordinate agents return bounded work to it. That supports the owner's requirement that the main ChatGPT/Sol surface remains the architectural decision head even though delegated subagents may perform independent model work.

### 1.6 Voice can coordinate multiple agents, but this is not a Soma reasoning backend

**DOCUMENTED FACT**

Current ChatGPT Voice in Work/Codex can start, prioritize, interrupt, redirect, and coordinate multiple agents across active conversations/projects while work continues in the background.

Source:

- OpenAI Help Center, `ChatGPT Voice`: https://help.openai.com/en/articles/20001274

**INFERENCE**

This reinforces that agent coordination is increasingly native to the ChatGPT product layer. It is evidence against reproducing a general-purpose semantic agent manager inside Soma without a demonstrated gap.

### 1.7 Codex subagents are real but Codex remains optional

**DOCUMENTED FACT**

Codex has its own multi-agent workflows, isolated agent threads/worktrees, and software-engineering specialization. OpenAI also documents smaller models being used as Codex subagents for narrower work while a larger model can retain planning/coordination/final judgment.

Sources:

- OpenAI, `Codex`: https://openai.com/codex/
- OpenAI, `Introducing GPT-5.4 mini and nano`: https://openai.com/index/introducing-gpt-5-4-mini-and-nano/
- OpenAI / ChatGPT Learn, `Subagents`: https://learn.chatgpt.com/docs/agent-configuration/subagents

**OWNER REQUIREMENT**

Codex is optional and may be used only after explicit owner authorization. It is not the foundation of the Soma/ChatGPT architecture.

**INFERENCE**

Codex can remain a future specialist execution/delegation route without owning canonical task identity or the Sol control loop.

### 1.8 Workspace Agents are a separate concept

**DOCUMENTED FACT**

OpenAI also provides Workspace Agents for eligible Business/Enterprise workspaces. These are configurable/shared agents for repeatable workflows with selected models, tools/apps, schedules, and governance.

Source:

- OpenAI Help Center, `ChatGPT Workspace Agents for Enterprise and Business`: https://help.openai.com/en/articles/20001143/

**INFERENCE**

Workspace Agents should not be conflated with Work subagents, ordinary Chat, or Soma's own durable task records. They are another product-level agent surface.

---

## 2. Current Soma assumptions at repository HEAD

### 2.1 Canonical Task now has a first-class reasoning kind/backend

**REPOSITORY FACT**

At current HEAD, `soma/tasks/models.py` defines:

- `TaskKind.DURABLE_COMMAND`
- `TaskKind.REASONING`
- `BackendKind.SOMA_DURABLE_RUN`
- `BackendKind.SOMA_REASONING`

This is no longer merely a future research term; reasoning is represented as a first-class canonical Task kind and backend category.

Relevant file:

- `soma/tasks/models.py`

### 2.2 The generic backend seam is useful, but the current production reasoning runtime is Codex-specific

**REPOSITORY FACT**

`soma/tasks/backends.py` contains an `ExecutionBackend` protocol and a `ReasoningTaskBackendAdapter`. This is structurally useful because canonical Task identity is separated from backend execution identity.

**REPOSITORY FACT**

However, `soma/reasoning/runtime.py` currently constructs `CodexRepositoryReasoningBackend` when reasoning is enabled. The example configuration describes this as `Production repository reasoning workers` and defaults to:

- provider: `codex_app_server_repository`
- model: `gpt-5.6-luna`
- effort: `low`

Relevant files:

- `soma/tasks/backends.py`
- `soma/reasoning/runtime.py`
- `config.example.yaml`

**INFERENCE**

The abstract task/backend seam is potentially reusable infrastructure. The current `reasoning` lane, however, has become conceptually stronger than the owner's intended optional-specialist role because it is modeled as a peer first-class Task kind and currently binds to a Codex repository reasoning implementation.

This is a realignment candidate, not yet a deletion decision.

### 2.3 Production reasoning is currently disabled

**REPOSITORY FACT**

Current `config.yaml` contains no `reasoning:` override. The accepted `V3_1B_OUTCOME_ACCEPTANCE_1_RESULT_2026-08-14.md` records that fresh Task capabilities still advertise only `durable_command` with backend `soma_durable_run`; production reasoning is not active.

Relevant files:

- `config.yaml`
- `docs/V3_1B_OUTCOME_ACCEPTANCE_1_RESULT_2026-08-14.md`

**REPOSITORY FACT**

Therefore this research is not correcting an active production model takeover. It is correcting architectural direction before an optional reasoning lane is normalized into the core design.

### 2.4 Company acceptance already understands `soma_reasoning`

**REPOSITORY FACT**

The current Company/OutcomeAcceptance work can validate terminal evidence from either `soma_durable_run` or `soma_reasoning`, with reasoning publication represented as subordinate backend evidence under a canonical Task.

Relevant files:

- `soma/company_kernel/acceptance.py`
- `docs/V3_1B_OUTCOME_ACCEPTANCE_1_RESULT_2026-08-14.md`

**INFERENCE**

This provider-neutral acceptance/evidence work may remain useful even if `reasoning backend` is later repositioned as optional specialist infrastructure. Its existence does not prove that a separate reasoning worker belongs in the normal Sol control path.

### 2.5 Existing documents contain both the correct Sol-centric idea and the later worker expansion

**REPOSITORY FACT**

`docs/CHATGPT_NORMAL_CHAT_TOOL_UX_IMPLEMENTATION_PLAN_2026-08-12.md` explicitly describes a separate follow-on shape:

`Sol / ChatGPT reasoning head -> bounded parallel workers -> structured evidence -> Sol synthesis`

It also states that Hermes is a tool/execution layer, not an independent reasoning head.

**REPOSITORY FACT**

The previous `docs/agent-worker-research/` track correctly recognized many of the same facts, including Work subagents and a hybrid Sol-head architecture, but then expanded into a general worker taxonomy including `reasoning_worker`, a durable graph, heterogeneous worker scheduling, and future reasoning backend adapters.

**INFERENCE**

The likely drift is not that the prior research completely misunderstood the owner. It began from a substantially correct Sol-head premise, then increasingly treated generic worker orchestration and a reasoning backend as architecture Soma itself should own. Later iterations must identify the exact commits/doc transitions where that provisional comparison target became implemented/core structure.

---

## 3. Direct comparison: current OpenAI reality vs current Soma direction

| Topic | Current OpenAI reality | Soma evidence | Iteration 1 assessment |
|---|---|---|---|
| Primary user-facing reasoning | Chat and Work are ChatGPT surfaces; Work is powered by GPT-5.6 | Sol-head language exists in normal-chat plan | **Aligned principle** |
| Long multi-step agency | Native Work capability | Separate Soma reasoning/worker architecture exists in source/research | **Potential duplication under Work** |
| Subagents | Native in Work; bounded parallel delegation; token cost | Prior research proposed future `reasoning_worker` | **Do not reproduce by default** |
| Ordinary Chat subagent spawn | Not documented as universal | Prior research sometimes compared future native adapters | **Capability-dependent; do not assume** |
| Coding specialization | Codex is separate dedicated surface; Work has broader agentic file/tool behavior | Current reasoning runtime binds to Codex repository backend | **Codex must remain optional** |
| Durable execution identity | OpenAI product docs do not define Soma-style local canonical Task/Run ownership | Canonical Task/backend/idempotency/recovery already exist | **Strong Soma value; likely keep** |
| Evidence/provenance | Product agents return results; details vary by surface | Soma has bounded refs, hashes, acceptance evidence | **Strong Soma value; likely keep** |
| Scheduling/background | Work supports Scheduled Tasks and long-running work | Soma has durable runs/workflows/supervisors | **Overlap exists; distinguish product scheduling from local execution durability** |
| External machine/service effects | Work/Codex act through granted tools/permissions | Soma has machine/SSH/Cloudflare/Docker/Hermes execution ownership | **Core Soma extension area** |

---

## 4. What Iteration 1 changes in our understanding

### 4.1 Work is not merely a nicer chat mode

**DOCUMENTED FACT**

Work is explicitly an agent for long, multi-step work, with planning, action, background/scheduled operation, local/cloud modes, and native subagents.

**INFERENCE**

Any corrected architecture must treat Work as an already-agentic ChatGPT surface. Adding an always-on Soma reasoning loop under Work is presumptively redundant until proven otherwise.

### 4.2 Native subagents support the owner's bounded-delegation idea

**DOCUMENTED FACT**

OpenAI's recommended use cases strongly match bounded parallel inspection/research/testing rather than replacing the main coordinating thread.

**INFERENCE**

The owner's rule `subagents are not the reasoning brain` is compatible with the product's documented main-thread/subagent shape.

### 4.3 The missing problem is increasingly durability/continuity, not raw agentic reasoning

**OWNER REQUIREMENT**

The desired loop is `Sol reasons -> acts -> Soma preserves state/evidence -> environment responds -> Sol observes -> Sol reasons again`.

**INFERENCE**

OpenAI already supplies much of the semantic agentic machinery in Work, and ChatGPT remains the user-facing cognitive surface. The more plausible missing layer is durable local/external control-loop continuity: exact action identity, state, observations, evidence, ambiguous outcomes, recovery, resumability, and return-to-Sol semantics.

This is only a research direction. Iterations 2-5 must prove exactly which durable state is missing and whether existing canonical Task infrastructure already covers most of it.

### 4.4 `reasoning backend` should not yet be accepted as a core architectural noun

**INFERENCE**

Given current Work capabilities, `reasoning backend` is at minimum overloaded terminology. It may eventually mean:

- optional specialist cognition;
- an external provider adapter;
- a benchmark/test backend;
- or obsolete architecture that should be isolated.

It should not be assumed to mean the normal source of Soma's intelligence.

**OPEN QUESTION**

Whether to keep, rename, move lower, make optional, deprecate, or remove that concept requires the later implementation audit. No decision is made here.

---

## 5. Preliminary responsibility boundary - not yet final architecture

### ChatGPT / Sol

**OWNER REQUIREMENT + DOCUMENTED SUPPORT**

- user-facing reasoning and judgment;
- semantic plan/decision ownership;
- choose actions/tools;
- interpret observations;
- synthesize delegated evidence;
- decide whether another reasoning turn is needed;
- decide completion/stop conditions.

### ChatGPT Work

**DOCUMENTED FACT**

- longer multi-step agentic work;
- planning and action across available tools/files/apps;
- background/scheduled work where supported;
- native subagent delegation for independent parallel tasks;
- progress, redirection, approval, and final deliverables.

### Soma

**INFERENCE TO TEST**

- durable action/task identity;
- durable local/external execution ownership;
- idempotency/replay protection;
- observations/evidence/provenance;
- recovery and uncertainty state;
- long-running process continuity;
- machine/service/tool access;
- project continuity and memory;
- exact hand-back/return-to-Sol signals.

### Optional specialists

**OWNER REQUIREMENT**

- Codex, Claude, Hermes-model mode, Responses/API agents, or other model workers may exist only as optional specialist routes;
- Codex requires explicit owner authorization;
- none of them becomes the default brain.

---

## 6. Open questions carried to later iterations

1. Where exactly in Git history did the provisional `reasoning_worker` comparison become a first-class `TaskKind.REASONING` / `soma_reasoning` implementation?
2. Which original owner/legacy documents establish the earlier `ChatGPT decides / local execution preserves and acts` contract?
3. Can the canonical Task plane represent the durable Sol control loop without creating a second cognitive lifecycle?
4. What state must survive between Sol turns: objective, plan, observations, next action, unresolved questions, completion criteria, controller version, or something smaller?
5. How should Soma signal `new observation available / Sol turn required` without making the semantic decision itself?
6. Which existing Evidence/FanIn/recovery/backend mechanisms are directly reusable?
7. Should the current reasoning Task/backend be repositioned as optional specialist execution, or retired from the core path?
8. How should ordinary Chat and Work differ operationally when Work already supplies native multi-step planning and subagents?
9. Which workflow/supervisor functions remain valuable execution machinery versus duplicated agentic planning?
10. How do Company/Mission/Plan concepts complement long-horizon organizational state without duplicating Work's planning? Company remains frozen while this is researched.

---

## 7. Iteration 1 conclusion

**DOCUMENTED FACT**

As of 2026-08-15, ChatGPT Work is a GPT-5.6-powered agentic surface for long, multi-step work and supports native subagent workflows. Ordinary Chat remains a distinct conversational surface. Codex remains a separate software-development surface with its own multi-agent workflows.

**REPOSITORY FACT**

Soma already contains strong durable infrastructure that is independent of a reasoning provider: canonical Task identity, backend references, versioned state, cancellation/recovery concepts, result/evidence references, and external execution tools. At the same time, source now includes a first-class `REASONING` Task kind, `SOMA_REASONING` backend, and a currently Codex-backed production reasoning runtime, although that runtime is disabled.

**OWNER REQUIREMENT**

Sol/ChatGPT must remain the brain. Soma extends ChatGPT with durability, state, memory, evidence, recovery, and execution rather than replacing ChatGPT's agentic layer.

**INFERENCE**

Iteration 1 therefore strengthens the case for realignment. The cleanup target should not be `delete Agent/Worker`; it should be to separate genuinely useful durable execution/control-plane infrastructure from the redundant or mispositioned idea that Soma needs its own routine reasoning-worker brain beneath ChatGPT Work.

No implementation plan is authorized yet.

---

## 8. Sources consulted

### Official OpenAI sources

1. OpenAI Help Center - `ChatGPT Work and Codex`
   - https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex
   - accessed 2026-08-15

2. OpenAI - `ChatGPT Work for every team`
   - https://openai.com/chatgpt-work/
   - accessed 2026-08-15

3. OpenAI / ChatGPT Learn - `Subagents`
   - https://learn.chatgpt.com/docs/agent-configuration/subagents
   - accessed 2026-08-15

4. OpenAI Help Center - `ChatGPT Voice`
   - https://help.openai.com/en/articles/20001274
   - accessed 2026-08-15

5. OpenAI - `Codex`
   - https://openai.com/codex/
   - accessed 2026-08-15

6. OpenAI - `Introducing GPT-5.4 mini and nano`
   - https://openai.com/index/introducing-gpt-5-4-mini-and-nano/
   - accessed 2026-08-15

7. OpenAI Help Center - `ChatGPT Workspace Agents for Enterprise and Business`
   - https://help.openai.com/en/articles/20001143/
   - accessed 2026-08-15

### Soma repository evidence

- `soma/tasks/models.py`
- `soma/tasks/backends.py`
- `soma/reasoning/runtime.py`
- `config.example.yaml`
- `config.yaml`
- `soma/company_kernel/acceptance.py`
- `docs/V3_1B_OUTCOME_ACCEPTANCE_1_RESULT_2026-08-14.md`
- `docs/V3_1B_CONTROLLED_LIVE_KERNEL_OF_ONE_ACTIVATION_1_GATE_2026-08-14.md`
- `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_IMPLEMENTATION_PLAN_2026-08-12.md`
- `docs/agent-worker-research/iteration-01-current-capability-and-architecture-baseline-2026-08-12.md`
- `docs/agent-worker-research/iteration-02-worker-contract-dag-and-evidence-baseline-2026-08-12.md`

Historical context to be examined more deeply in Iteration 2: `CodexBridge Local Agent Expansion Roadmap v2`, whose core direction already separated ChatGPT strategic/final-decision authority from local operational execution and optional Codex escalation.
