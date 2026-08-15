# Iteration 4 - Mode-Aware Chat vs Work Integration

Date: 2026-08-15
Status: research only
Track: Sol-centric durable agentic-loop realignment
Repository HEAD inspected: `938f1764dcab30a8bd8235ea2c822ba6d8c0826c`

## Scope

Iterations 1-3 established:

1. Chat and Work are distinct ChatGPT experiences.
2. Work already provides a native agentic multi-step surface.
3. Normal Chat should gain only the missing durable control-loop continuity around Sol.
4. Canonical Task should remain action/execution identity rather than overall cognitive-goal identity.
5. The likely normal-Chat add-on is a small loop/turn/observation layer, not another reasoning model and not a mandatory DAG.

Iteration 4 investigates how the same Soma installation should serve **normal Chat and Work without duplicating Work's native agentic layer or requiring fragile mode detection**.

This iteration also asks whether mode-awareness should live in:

- Soma runtime detection;
- explicit controller declaration;
- plugin/skill guidance;
- distinct public tools;
- or simply different use of the same shared substrate.

No implementation is authorized.

## Hard constraints

No runtime/service restart, Company activation, reasoning-provider activation, Codex use, provider generation, production config change, push, or modification of `docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` occurred.

Company remains frozen.

Wake-up/delivery remains a separate optional transport problem. Manual owner wake-up remains a valid baseline.

Classification labels:

- **DOCUMENTED FACT** - current official OpenAI documentation.
- **REPOSITORY FACT** - current Soma source/docs/history evidence.
- **OWNER REQUIREMENT** - explicit owner direction.
- **INFERENCE** - supported architectural conclusion, not yet implementation authority.
- **OPEN QUESTION** - intentionally unresolved.

---

# 1. OpenAI currently treats Chat and Work as separate experiences, not one hidden mode

## 1.1 Product distinction

**DOCUMENTED FACT**

OpenAI's current Help Center states that ChatGPT includes Chat and Work, with Codex as a separate software-development experience in the desktop app.

OpenAI describes:

- **Chat** as fast conversational assistance, questions, search, brainstorming, and everyday help;
- **Work** as an agent designed for longer, multi-step work and finished deliverables;
- **Codex** as the software-development/technical surface.

Source:

- OpenAI Help Center, `ChatGPT Work and Codex`, updated August 2026: https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex

## 1.2 Work owns native goal-to-work behavior

**DOCUMENTED FACT**

OpenAI's July 9, 2026 Work launch describes Work as an agent in ChatGPT that can:

- take action across apps/files;
- stay with a project for hours;
- break a goal into smaller steps;
- complete those steps independently;
- produce finished work.

OpenAI's Work product page further says Work:

- gathers context;
- plans an approach;
- takes actions across tools/files/apps;
- supports Plan mode;
- supports one-time and recurring tasks/monitoring;
- is powered by GPT-5.6.

Sources:

- OpenAI, `ChatGPT is now a partner for your most ambitious work`, 2026-07-09: https://openai.com/index/chatgpt-for-your-most-ambitious-work/
- OpenAI, `ChatGPT Work`: https://openai.com/chatgpt-work/

**OWNER REQUIREMENT**

This native Work layer is not something Soma should recreate underneath Work.

---

# 2. Plugins, Apps, and Skills do not establish a separate reasoning authority

## 2.1 Apps expose systems, data, and actions

**DOCUMENTED FACT**

Current OpenAI plugin documentation says:

- plugins are the discovery/package surface for workflow capabilities across ChatGPT and Codex;
- a plugin may contain Skills, Apps, and App Templates;
- Apps connect ChatGPT or Codex to external systems, data, and actions;
- underlying App permissions remain the authority boundary.

Source:

- OpenAI Help Center, `Plugins in ChatGPT and Codex`: https://help.openai.com/en/articles/20001256-plugins-in-codex

## 2.2 Skills are workflow guidance

**DOCUMENTED FACT**

OpenAI describes Skills as reusable workflows that tell ChatGPT how to perform a specific task more consistently. Skills may contain instructions, examples, supporting resources, and code, and ChatGPT can automatically use installed Skills when relevant.

Source:

- OpenAI Help Center, `Skills in ChatGPT`: https://help.openai.com/en/articles/20001066

**INFERENCE**

A Soma Skill can influence how ChatGPT uses Soma, but it is not a reliable runtime authority boundary and should not be the only thing preventing Work from entering a normal-Chat-specific control path.

The repository's own normal-Chat UX plan already reflects this principle: Skill guidance is not authorization; Soma remains authoritative for validation, execution, idempotency, evidence, and destructive boundaries.

---

# 3. No trustworthy inbound Chat-vs-Work marker has been established

## 3.1 Official-source search result

**OPEN QUESTION / NEGATIVE FINDING**

This iteration searched current official OpenAI Help Center and developer documentation for a documented Apps/MCP tool-call field that tells an external app/server whether a given invocation originated from:

```text
normal Chat
vs
ChatGPT Work
```

No such documented field was found in the sources inspected.

This is **not proof that no private/internal surface signal exists**. It means this research has no current official evidence authorizing Soma to depend on one.

## 3.2 Current Soma contract also has no surface field

**REPOSITORY FACT**

Current public Soma Task inputs carry fields such as:

- `controller_request_id`;
- project identity where relevant;
- Task/backend identity;
- action-specific parameters;
- state versions/idempotency keys.

They do not carry a canonical `chat`, `work`, or `surface_mode` field.

The public gateway inventory and public tool metadata likewise describe capability/risk/UX, not Chat-vs-Work provenance.

## 3.3 Architecture rule

**INFERENCE - STRONG**

Soma should **not infer Chat vs Work from behavior**.

It should not guess based on:

- how many tool calls occurred;
- whether a task looks long;
- whether parallel calls appear;
- model/provider names;
- conversation wording;
- presence of a plan;
- whether a Skill was used;
- timing or UI assumptions.

Those are brittle heuristics and could cause exactly the architecture drift this track is trying to remove.

---

# 4. The shared Soma substrate is naturally mode-neutral

## 4.1 Existing shared capabilities

**REPOSITORY FACT**

Soma's current public/control-plane foundations are already useful without knowing Chat or Work mode:

- canonical Task identity;
- durable Run/process execution;
- result/evidence publication;
- idempotency/replay;
- recovery/uncertainty;
- ProjectScope/resource ownership;
- repository tools;
- SSH/Cloudflare/Docker/external execution;
- long-running jobs;
- memory/knowledge;
- checkpoints;
- compact projections;
- return-loop artifacts.

None of those fundamentally requires the external caller to be Chat or Work.

## 4.2 Shared substrate principle

**INFERENCE**

The clean base architecture is therefore:

```text
                       SOMA SHARED SUBSTRATE

 canonical Task / Run / evidence / recovery / tools / memory / scope
                              ^
                              |
                +-------------+-------------+
                |                           |
          NORMAL CHAT                     WORK
```

Mode differences should affect **cognitive orchestration**, not execution truth.

This keeps one durable execution/evidence system rather than branching Soma into separate Chat and Work architectures.

---

# 5. Normal Chat needs an extra controller-loop capability

## 5.1 Missing capability

**OWNER REQUIREMENT**

Normal Chat should be able to behave agentically across repeated Sol turns:

```text
Sol reasons
 -> Soma action(s)
 -> durable observation(s)
 -> Sol reasons again
 -> ...
 -> Sol declares goal complete
```

Iteration 3 found that this likely requires a small loop/turn/observation identity above canonical Tasks.

## 5.2 This is an additive control capability, not a replacement Task system

**INFERENCE**

Normal Chat's architecture should look approximately like:

```text
NORMAL CHAT / SOL
       |
  optional lightweight
  Sol-loop control layer
       |
  +----+-------------------+
  |                        |
canonical Task(s)       memory/context refs
  |
Runs/tools/external effects
  |
observations/evidence
  |
Sol-loop continuation bundle
  |
NORMAL CHAT / SOL
```

Canonical Tasks stay exactly what they are good at: durable action/execution identity.

The new layer exists only to preserve cognitive continuity between Sol turns.

---

# 6. Work should usually bypass the normal-Chat loop driver

## 6.1 Why

**DOCUMENTED FACT**

Work already plans, takes actions across tools/files/apps, stays with complex projects for hours, and independently performs multiple steps toward a deliverable.

**OWNER REQUIREMENT**

Do not put another model-driven or planning-driven loop underneath Work.

## 6.2 Leading architecture

**INFERENCE**

Work can use the same Soma substrate directly:

```text
WORK NATIVE AGENTIC LOOP
       |
       +--> Soma canonical Task / external action
       |          |
       |       result/evidence
       |          |
       <----------+
       |
Work continues natively
```

The normal-Chat `loop_id / controller-turn / observation-cursor` machinery should **not be mandatory** for Work merely because it exists.

## 6.3 Important nuance

This does not mean Work can never use a durable higher-level Soma context.

There may be cases where Work benefits from:

- durable project objective identity shared across sessions;
- exact cross-restart external-action lineage;
- long-running Soma operation references;
- explicit owner-authored mission context.

But if such needs are proven, Work should consume those durable facts **without Soma becoming Work's planner/reasoner**.

Mode-aware integration means respecting Work's native control layer, not withholding useful persistence.

---

# 7. Explicit invocation is safer than automatic mode detection

Several integration patterns were compared.

## Option A - Soma auto-detects Chat vs Work

Example:

```text
inspect tool-call metadata / behavior
 -> guess calling surface
 -> automatically enable/disable Sol-loop driver
```

### Verdict

**REJECT AS CURRENT PREMISE.**

No documented reliable inbound surface marker has been established, and behavioral inference is fragile.

## Option B - require every Soma call to declare `mode=chat|work`

### Advantages

- explicit;
- deterministic;
- easy to audit.

### Problems

- pollutes every low-level tool call with a cognitive concern;
- duplicates a fact that often does not matter to execution;
- creates friction and token/schema overhead;
- risks mode becoming an authorization concept accidentally;
- requires changing many stable gateways.

### Verdict

**NOT PREFERRED for shared Task/execution tools.**

If an explicit surface/controller declaration is ever needed, it should live at the **loop/control boundary**, not every execution call.

## Option C - shared mode-neutral tools + explicit normal-Chat loop operations

Shape:

```text
shared Soma execution/evidence tools
    usable by Chat and Work

normal-Chat loop operations
    used only when Sol wants durable normal-Chat continuation
```

### Advantages

- no guessing;
- no duplicate execution stack;
- Work does not need special-case runtime behavior;
- normal Chat gets the missing capability explicitly;
- low-level tools remain clean and mode-neutral;
- compatible with a Skill/plugin that teaches normal Chat when to use the loop.

### Risk

A Work thread could technically invoke the loop operation if exposed there.

But this is not automatically harmful if the loop operation is simply a durable controller-context primitive and does not start a second reasoning model. Still, guidance should discourage unnecessary duplication.

### Verdict

**LEADING HYPOTHESIS.**

## Option D - separate Soma apps/plugins for Chat and Work

### Advantages

- explicit product separation;
- each surface can expose a tailored tool set/guidance.

### Problems

- duplicated packaging/discovery/configuration;
- likely unnecessary complexity;
- risks contract drift between two Soma installations;
- may be unsupported or awkward depending on plugin surface controls;
- execution truth should remain one system anyway.

### Verdict

**DEFER unless one-app ergonomics prove inadequate.**

---

# 8. Plugin/Skill guidance can improve routing without becoming architecture truth

## 8.1 Existing normal-Chat UX plan already anticipated this

**REPOSITORY FACT**

`docs/CHATGPT_NORMAL_CHAT_TOOL_UX_IMPLEMENTATION_PLAN_2026-08-12.md` defines the desired normal-Chat interaction as:

```text
understand
 -> explain meaningful action
 -> use Soma
 -> validate
 -> report coherently
```

It proposes a Plugin + `soma-engineering` Skill only after empirical A/B validation.

The Skill is explicitly guidance, not authorization.

## 8.2 Relevance to the Sol loop

**INFERENCE**

A future normal-Chat Soma Skill could teach patterns such as:

```text
For ordinary one-shot work:
    use Soma tools directly.

For a task that needs durable multi-turn continuation:
    establish/continue the lightweight Sol loop.

After observations arrive:
    query unconsumed observations and reason yourself.

Do not invoke a reasoning backend merely to continue the loop.

Declare goal completion explicitly when you, Sol, judge the objective complete.
```

This would help normal Chat use the new capability naturally.

However:

- Soma must still mechanically validate IDs/versions/action links;
- the Skill must not be the only enforcement that prevents duplicate execution;
- Work's native agent loop remains product-owned.

---

# 9. The add-on should be opt-in by task shape, not “always agent mode”

**OWNER REQUIREMENT**

The feature should help Sol rather than make every normal interaction more difficult.

**INFERENCE**

Normal Chat should not create a durable loop for every question.

Likely routing:

```text
simple answer / no Soma action
    -> ordinary Chat

one immediate Soma action and result in same turn
    -> ordinary Chat + direct Soma tool use

multi-step task where each observation changes next decision
    -> lightweight Sol loop

long-running action that may outlive Chat turn
    -> lightweight Sol loop + canonical Task

known deterministic batch with no fresh semantic judgment needed
    -> existing execution/workflow/programmatic machinery where appropriate

large structured mission
    -> optional higher-order mission/plan machinery only if explicitly justified
```

This is crucial: the presence of Soma does not mean every conversation becomes a durable agent run.

---

# 10. Current OpenAI model guidance supports direct model judgment between changing results

**DOCUMENTED FACT**

OpenAI's current GPT-5.6 model guidance says Programmatic Tool Calling is most appropriate for bounded, predictable, tool-heavy stages that do **not** require fresh model judgment between every step.

The same guidance says direct tool calls are preferable when each result may change the model's next decision.

Source:

- OpenAI API, `Model guidance`: https://developers.openai.com/api/docs/guides/latest-model

## Relevance

**INFERENCE**

This maps well to the owner-intended distinction:

```text
fresh semantic judgment after observation
    -> return to Sol

bounded deterministic processing
    -> Soma/tool/workflow machinery can continue without another Sol turn
```

This does not prove a specific Soma implementation, but it supports avoiding unnecessary model delegation for deterministic execution while preserving Sol turns where observations materially change the next decision.

---

# 11. Mode-aware responsibility matrix

This is a research synthesis, not an implementation contract.

| Capability | Normal Chat / Sol | ChatGPT Work | Soma |
|---|---|---|---|
| Understand user intent | primary | primary/native | no semantic ownership |
| Semantic reasoning | primary | primary/native | no core semantic reasoning |
| Decide next action after new evidence | Sol | Work native loop | expose facts only |
| Multi-step cognitive loop | add lightweight durable Sol continuation | already native | support, do not duplicate |
| Goal decomposition | Sol as needed | Work native | do not own by default |
| Native subagents | not assumed as ordinary-Chat primitive | native where available/useful | not a replacement layer |
| Durable external action identity | consume | consume | canonical Task |
| Process/run ownership | consume | consume | authoritative |
| Long-running external execution | request/review | request/review | authoritative |
| Idempotency/recovery | rely on | rely on | authoritative |
| Result/evidence preservation | interpret | interpret | authoritative references/data |
| Observation bookkeeping | lightweight Sol-loop add-on | usually unnecessary as separate cognitive driver | mechanical |
| Goal completion decision | Sol | Work native controller | never infer semantically |
| Memory/project facts | consume/write intentionally | consume/write intentionally | durable store |
| Wake-up delivery | owner/manual baseline; optional adapter | Work native/product mechanisms where available | optional external adapter only |

---

# 12. Shared substrate vs mode-specific control

## 12.1 Shared

**INFERENCE**

These should remain mode-neutral:

```text
Task
Run
ProjectScope
result/evidence
recovery/uncertainty
memory/knowledge
repo/SSH/Docker/Cloudflare/tool execution
long-running jobs
artifacts
```

## 12.2 Normal-Chat-specific or primarily normal-Chat-useful

```text
lightweight goal/loop identity
controller-turn grouping
new-observation cursor
explicit Sol completion declaration
compact continuation bundle
```

Even these records should use controller-neutral names/contracts where practical, because another external controller could theoretically use them later. But their first purpose is to fill normal Chat's durability gap.

## 12.3 Work-native

```text
semantic planning
multi-step initiative
native agent loop
native subagent orchestration
native Work deliverable lifecycle
```

Soma should not mirror these unless a concrete external-durability gap is demonstrated.

---

# 13. Subagents fit differently by surface

## 13.1 Work

**DOCUMENTED FACT / OWNER REQUIREMENT**

Work is already an agentic product surface and may use its own native delegation/subagent mechanisms.

Soma should treat those as part of Work's cognition unless an individual delegated action needs Soma-level durable external ownership.

## 13.2 Normal Chat

**OWNER REQUIREMENT**

The core normal-Chat Sol loop must work without Codex, Claude, Responses/API multi-agent, Hermes reasoning, or another provider.

**INFERENCE**

If normal Chat later gains a supported native subagent primitive directly, Sol may use it for bounded parallel inspection/research/verification.

That still does not change the durable core:

```text
Sol -> optional specialist delegation -> Sol synthesis
Sol -> Soma durable action -> observation -> Sol continuation
```

The provider-native child tree should not automatically become Soma's canonical goal identity.

---

# 14. `reasoning backend` is not a mode-switch mechanism

**REPOSITORY FACT**

Current Soma reasoning Task/backend code is provider-neutral at its canonical boundary but currently has a Codex repository provider/runtime implementation behind the owner gate.

**INFERENCE**

It would be an architectural mistake to say:

```text
Normal Chat detected
 -> enable Soma reasoning backend
```

That would recreate the drift.

The normal-Chat missing capability is **durable continuation of Sol's own reasoning**, not automatically selecting an external model.

Any retained reasoning backend should later be reclassified as optional specialist delegation independent of Chat-vs-Work mode.

---

# 15. Explicit controller identity may still be useful at the loop boundary

## 15.1 Surface mode and controller identity are different facts

**INFERENCE**

Even if Soma should not require `mode=chat|work`, a durable loop may need an explicit `controller_ref` or controller class to establish ownership of controller-authored turns.

For example:

```text
controller_ref = opaque ChatGPT/Sol controller identity
```

or a versioned controller contract.

This would answer:

- who is allowed to advance the observation cursor?
- who explicitly declared goal completion?
- which controller state/version produced the linked actions?

It need not say `Chat` or `Work`.

## 15.2 Why this is cleaner

A controller identity is about **authority/provenance**.

A product-surface label is about **UX/runtime context**.

Conflating them would create unnecessary coupling to OpenAI product names and future product changes.

**OPEN QUESTION**

Whether the loop needs a stable controller identity beyond existing request IDs remains to be proven in the next schema-minimization iteration.

---

# 16. Fresh Chat thread recovery

## 16.1 Normal Chat

**OWNER REQUIREMENT**

A browser refresh, new Chat, or lost context should not force the owner to reconstruct operational history manually.

**INFERENCE**

The desired sequence is:

```text
owner: continue <project/task>
Sol: query Soma for active/recent loop context
Soma: compact objective + active actions + new observations + uncertainty
Sol: reason from that durable context
```

Soma does not need the complete previous transcript if the controller intentionally persisted the objective/constraints/plan summary/evidence references needed for continuation.

## 16.2 Work

Work has its own project/conversation/agent continuity mechanisms.

Soma should still preserve external action truth so Work can recover external effects after reconnect, but should not try to reconstruct Work's entire internal planning state.

---

# 17. Why one public Soma tool surface is still plausible

**REPOSITORY FACT**

Soma currently presents one public MCP/tool surface with 34 gateways and one metadata authority.

The normal-Chat UX plan already focuses on making that shared public surface understandable and truthful rather than multiplying tools unnecessarily.

**INFERENCE**

The corrected architecture does not currently justify separate Chat and Work Soma servers.

A plausible eventual public addition is one compact loop family, conceptually something like:

```text
loop_query
loop_action
```

or equivalent operations integrated into an existing controller-plane gateway.

That is **not an implementation proposal yet**. The point is that mode awareness may require only an optional high-level capability, not a duplicated public surface.

The exact topology belongs to later implementation planning after research synthesis.

---

# 18. Failure modes to avoid

## 18.1 Guessing the surface

Bad:

```text
many tool calls => probably Work
short conversation => probably Chat
```

Reason: unreliable and invisible.

## 18.2 Enabling external reasoning because caller is Chat

Bad:

```text
normal Chat -> Soma reasoning provider
```

Reason: confuses missing continuity with missing intelligence.

## 18.3 Forcing Work through the normal-Chat loop

Bad:

```text
Work native agent loop
 -> Soma second goal/plan loop
 -> Tasks
```

Reason: duplicate orchestration, more tokens/context, conflicting ownership.

## 18.4 Splitting execution truth by mode

Bad:

```text
ChatTask vs WorkTask
ChatRun vs WorkRun
```

Reason: external effects are the same regardless of product surface.

## 18.5 Using Skills as safety/authority enforcement

Bad:

```text
Skill says don't do X, therefore runtime permits X
```

Reason: Skills are guidance; Soma must enforce its own durable/authority contracts.

## 18.6 Turning every Chat task into a loop

Bad:

```text
hello -> create loop
simple file read -> create mission/turn/task graph
```

Reason: harms UX and adds bookkeeping with no benefit.

---

# 19. Leading mode-aware architecture after Iteration 4

```text
                               USER
                                 |
                 +---------------+---------------+
                 |                               |
           NORMAL CHAT                         WORK
                 |                               |
                SOL                      WORK NATIVE AGENT LOOP
                 |                               |
       when durable multi-turn                   |
       continuation is needed                    |
                 |                               |
       lightweight Sol-loop                      |
       controller context                        |
                 |                               |
                 +---------------+---------------+
                                 |
                         SOMA SHARED SUBSTRATE
                                 |
                canonical Task / Run / evidence
                recovery / scope / tools / memory
                                 |
                         external environment
                                 |
                             observations
                                 |
                 +---------------+---------------+
                 |                               |
       Sol-loop observation return        Work native continuation
                 |                               |
                SOL                          Work/Sol
```

Optional specialist models/agents sit to the side of Sol/Work as deliberately invoked capabilities. They do not sit permanently between ChatGPT and Soma.

---

# 20. What changed in our understanding

## Before Iteration 4

We knew Chat and Work should behave differently, but it was plausible Soma might need a runtime `mode` concept to select behavior.

## After Iteration 4

**INFERENCE**

The cleaner design is **mode-neutral substrate + mode-specific orchestration usage**, not mode-dependent execution truth.

There is currently no evidence requiring Soma to detect Chat vs Work on every call.

Normal Chat explicitly uses the lightweight Sol-loop capability when needed.

Work uses shared Soma action/evidence capabilities under Work's native agent loop and simply does not need the extra loop driver in the common case.

This substantially reduces architecture complexity and avoids coupling Soma to undocumented ChatGPT invocation metadata.

---

# 21. Decisions/hypotheses carried forward

## Strong research conclusions

1. Do not infer Chat vs Work from tool-call behavior.
2. Keep canonical Task/Run/evidence execution truth mode-neutral.
3. Normal Chat gets the lightweight Sol-loop add-on only when durable multi-turn continuation is useful.
4. Work keeps its native agentic reasoning/planning loop.
5. Do not automatically activate a Soma reasoning backend for normal Chat.
6. Skills/plugins may guide normal Chat toward the right pattern but are not authority boundaries.
7. Do not require a mode field on every existing Soma gateway.
8. If explicit controller identity is needed, separate it from product-surface naming.
9. One shared Soma app/tool surface remains the preferred baseline unless later UX testing disproves it.
10. Wake-up/delivery remains separable and optional.

## Open questions

1. What is the smallest durable loop schema that supports the Iteration 3 model?
2. Does a loop need explicit `controller_ref`, or are request identities sufficient?
3. How should a new Chat thread discover the correct active loop without ambiguity?
4. Can multiple loops be active per project/conversation/user, and how should selection work?
5. Should normal-Chat loop operations be a new public gateway family or fit inside Task/another existing gateway without semantic pollution?
6. How should loop operation metadata/Skill guidance keep usage lightweight and intuitive?
7. Is there any future official Apps/MCP surface metadata that could be safely used as an optimization, while keeping architecture correct without it?
8. Which Work cases genuinely need extra Soma goal-level persistence beyond shared external-action truth?

---

# 22. Next iteration

Iteration 5 should minimize and pressure-test the proposed durable Sol-loop contract.

It should answer:

- exact identities/records required;
- event-ledger vs projection-row design;
- turn/cycle idempotency;
- observation sequencing/consumption;
- goal completion/cancellation authority;
- zero/one/many Task linkage;
- fresh-chat discovery;
- multiple active loops;
- relationship to existing Task links/events/checkpoints;
- whether any new public operation is actually necessary.

The goal is to **delete fields/concepts from the hypothesis**, not expand it.

No implementation plan should be produced yet.

---

# Sources consulted

## Official OpenAI sources

- OpenAI Help Center, `ChatGPT Work and Codex`: https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex
- OpenAI, `ChatGPT is now a partner for your most ambitious work`: https://openai.com/index/chatgpt-for-your-most-ambitious-work/
- OpenAI, `ChatGPT Work`: https://openai.com/chatgpt-work/
- OpenAI Help Center, `Plugins in ChatGPT and Codex`: https://help.openai.com/en/articles/20001256-plugins-in-codex
- OpenAI Help Center, `Skills in ChatGPT`: https://help.openai.com/en/articles/20001066
- OpenAI API, `Model guidance`: https://developers.openai.com/api/docs/guides/latest-model
- OpenAI Developers homepage/product surface descriptions: https://developers.openai.com/

Official OpenAI documentation was also searched for Apps/MCP invocation metadata exposing a trustworthy Chat-vs-Work source marker. None was found in the inspected sources; this remains an open question, not a claim of impossibility.

## Soma repository

- `soma/gateway_models.py`
- `soma/public_gateway_inventory.py`
- `soma/public_tool_metadata.py`
- `soma/tasks/models.py`
- `soma/tasks/store.py`
- `soma/tasks/projections.py`
- `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_IMPLEMENTATION_PLAN_2026-08-12.md`
- `docs/sol-agentic-loop-realignment-research/iteration-01-current-chatgpt-work-native-agent-reality-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-02-original-intent-drift-and-normal-chat-addon-boundary-2026-08-15.md`
- `docs/sol-agentic-loop-realignment-research/iteration-03-minimal-durable-sol-control-loop-state-2026-08-15.md`
