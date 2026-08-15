# Soma Active Engineering Plan

## Purpose

This file is the concise active implementation queue. Detailed completed implementation history belongs under `docs/legacy/` or in its original acceptance/evidence documents, not in the active roadmap.

The pre-cleanup V3 planning record is preserved at [`docs/legacy/Soma_Roadmap_V3_Implementation_Record_2026-08-15.md`](docs/legacy/Soma_Roadmap_V3_Implementation_Record_2026-08-15.md).

## Owner correction - 2026-08-15

The Autonomous Company roadmap is **FROZEN**. Do not infer implementation authority from a generated gate, an acceptance document, a previous agent's statement that a package is "next authorised", or a generic `continue`.

The current owner correction is:

- the Agent/Worker core implementation is a separate completed implementation track;
- the preserved uncommitted patch auto-repair research/plan was the intended next implementation work after Agent/Worker;
- V3-1B and V3-2 implementation exist in the repository, but their owner-activation provenance is disputed and they do not authorise any later Company lane;
- V3-3 and every later Autonomous Company lane remain inactive;
- existing Company implementation is preserved as historical repository state unless the owner separately asks for review, reclassification, amendment, or rollback.

No Company implementation resumes without a new explicit owner instruction naming the Company lane to reopen.

## Completed lane - Sol semantic continuation + portable Skills

**Status:** COMPLETED / ACCEPTED on 2026-08-15.

**Authority and evidence:**

- [`docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_IMPLEMENTATION_PLAN_2026-08-15.md`](docs/SOL_CONTINUATION_AND_SOMA_SKILL_LAYER_IMPLEMENTATION_PLAN_2026-08-15.md)
- [`docs/sol-agentic-loop-realignment-research/I1_INTEGRATED_NORMAL_CHAT_ACCEPTANCE_2026-08-15.md`](docs/sol-agentic-loop-realignment-research/I1_INTEGRATED_NORMAL_CHAT_ACCEPTANCE_2026-08-15.md)
- [`docs/semantic-continuation-and-skills.md`](docs/semantic-continuation-and-skills.md)

Owner-selected final scope: durable semantic continuation/re-entry plus the portable Skill layer and existing Soma tools. The previously discussed additional normal-Chat agentic-reasoning add-on was explicitly withdrawn by the owner before final acceptance and is not an unfinished requirement of this programme.

The accepted public runtime has 38 consolidated gateways. Continuation does not choose next actions; Skills do not semantically route requests or execute bundled scripts. Repository-local `.agents/skills` content is not automatically ingested.

## Next intended implementation lane - Patch Auto-Repair

**Status:** READY / NOT STARTED.

**Authoritative plan:** [`docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_IMPLEMENTATION_PLAN_2026-08-12.md`](docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_IMPLEMENTATION_PLAN_2026-08-12.md)

**Research basis:**

- [`iteration-01-current-patch-pipeline-and-repair-feasibility-2026-08-12.md`](docs/patch-auto-repair-research/iteration-01-current-patch-pipeline-and-repair-feasibility-2026-08-12.md)
- [`iteration-02-real-failure-corpus-and-tier-a-boundary-2026-08-12.md`](docs/patch-auto-repair-research/iteration-02-real-failure-corpus-and-tier-a-boundary-2026-08-12.md)
- [`iteration-03-python-boundary-proof-create-policy-and-provenance-2026-08-12.md`](docs/patch-auto-repair-research/iteration-03-python-boundary-proof-create-policy-and-provenance-2026-08-12.md)
- [`iteration-04-fuzzing-impossibility-boundary-and-resolution-flow-2026-08-12.md`](docs/patch-auto-repair-research/iteration-04-fuzzing-impossibility-boundary-and-resolution-flow-2026-08-12.md)

The original hold was: do not implement while the Agent/Worker lane has active shared-worktree changes. That blocking condition is no longer the active reason to hold the work, because the Agent/Worker core is closed. The patch auto-repair lane still requires its own owner opening instruction before product implementation begins.

### Planned sequence

```text
P0.1  preserve the four research journals plus implementation plan
P0.2  post-Agent/Worker patch-pipeline drift audit
G1    candidate validation foundation + bundle v4
G2    real-corpus detector + deletion proof + durable proposal
G3    accept_repair / accept_original -> deterministic child preview
G4    public repo_preview(resolve_patch) + patch_status + schema identity
G5    prove repo_apply/revert compatibility and repair blindness
G6    JSON validation + TOML capability decision; XML/YAML deferred
G7    bounded evidence/telemetry policy
G8    source release acceptance + selected-file local commit
A1    separately owner-authorised runtime activation + connector refresh + live smoke
```

No stage silently authorises a different implementation lane. No LLM/model performs patch repair. `repo_apply` remains a blind deterministic executor of the selected preview bytes.

## Preserved uncommitted planning artifact

[`docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md`](docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md) is a pre-existing Soma planning artifact. It is intentionally preserved and is **not** automatically part of the patch auto-repair lane.

## Agent/Worker core

**Status:** COMPLETED / ACCEPTED AS A SEPARATE TRACK.

Authoritative implementation and acceptance records remain under [`docs/agent-worker-research/`](docs/agent-worker-research/), including [`AGENT_WORKER_CORE_ACCEPTANCE_2026-08-14.md`](docs/agent-worker-research/AGENT_WORKER_CORE_ACCEPTANCE_2026-08-14.md).

The provider-expensive optimisation/native-agent work (including deferred G6.4/G7-style experiments) remains disabled unless the owner explicitly requests it. Codex/provider subagents are not authorised by a generic `continue`.

## Autonomous Company roadmap - FROZEN

**Architecture:** [`docs/SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md`](docs/SOMA_ROADMAP_V3_AUTONOMOUS_COMPANY_ARCHITECTURE_2026-07-30.md)

**Organisational contract:** [`docs/SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md`](docs/SOMA_V3_HIERARCHICAL_INTELLIGENCE_ORGANISATIONAL_CONTRACT_2026-07-31.md)

The Company destination is preserved. Freezing implementation does not delete or redesign the Company architecture.

### Existing Company-related implementation

- `V3-1A - Interactive worker substrate`: implementation/evidence exists and remains preserved.
- `V3-1B - Kernel of One`: implementation/evidence exists; later owner review identified disputed activation provenance.
- `V3-2 - Role-scoped capability broker`: implementation/evidence exists; later owner review identified disputed activation provenance.

These are historical/current repository facts, not authority to continue the Company roadmap.

### Future Company sequence - preserved but inactive

#### V3-3 - Interactive executive loop and bounded collaboration

Package-completion-driven executive advancement, structured proposals, challenges, dependency requests, deliberation, dissent, and owner escalation over the kernel-of-one.

#### V3-4 - Temporary organisation formation

Smallest-sufficient-organisation gate, temporary Roles and Assignments, organisation revision, and bounded cross-role collaboration. A one-executive configuration remains valid.

#### V3-5 - Organisation observation and reconciliation

Desired-versus-observed organisation behaviour justified by measured worker reconstruction, provider health, and collaboration needs, without creating a second process/task authority.

#### V3-6 - Cortana and company dashboard

Owner-facing company experience over canonical projections, beginning with text, owner decisions, and live status. Voice and richer presence remain replaceable presentation capabilities.

#### V3-7 - Business-system binding and safe mutations

Generic external-system references and policy-governed mutation execution, reusing domain-specific authorities instead of duplicating them.

#### V3-8 - Bounded provider pilots

CRM, finance/accounting, billing, workspace, creative production, live customer interaction, analytics, and support pilots only when a real Company workflow requires them.

#### V3-9 - Autonomous company trial

One bounded real objective proving planning, execution, review, launch preparation, and outcome measurement with limited owner intervention.

#### V3-10 - Organisational optimisation and genuine learning

Compare the kernel-of-one against larger organisation forms and promote measured playbooks/routing improvements only through explicit evaluation gates.

### Company reopening rule

Only a new explicit owner instruction naming a Company lane may unfreeze Company implementation. Existing source code, historical acceptance text, generated roadmap transitions, or a generic `continue` cannot provide that authority.

## Parked future work

### Code intelligence

`CODEBASE_MEMORY_MCP_DECISION_2026-07-28` remains planned but inactive. Any `PILOT-CODE-INTELLIGENCE-1` requires separate owner selection.

### Cortana presence research

[`docs/FUTURE_CONVERSATIONAL_PRESENCE_AGENT_RESEARCH.md`](docs/FUTURE_CONVERSATIONAL_PRESENCE_AGENT_RESEARCH.md) remains parked. It does not activate voice, telephony, browser automation, provider spend, or a second companion architecture.

### Legacy/public-surface retirement

Prior retirement and measurement work remains historical evidence. No compatibility path is removed from a generic `continue`; any actual retirement requires a separately reviewed owner-approved change.

## Governing operating rules

- Preserve unrelated and concurrent work. Do not reset, clean, stash, or absorb it into another lane.
- Do not push or deploy unless the owner explicitly requests it.
- Do not use Codex or provider subagents unless the owner explicitly authorises that use.
- A generic `continue` may continue the already-open bounded lane; it does not open a different product lane or provider route.
- Generated plans, gates, and acceptance records are project memory and engineering evidence, not substitutes for owner authority where owner activation is required.
- Soma remains the durable project-aware control plane. One authority owns each concern.
- Failures and uncertainty must be recorded honestly rather than converted into apparent success.
- Keep the owner/executive public MCP surface at the accepted 38-gateway boundary unless a separately reviewed compatibility change requires otherwise.
- Public schema changes require explicit schema identity and connector/runtime convergence evidence.

## Legacy and evidence

Completed implementation details were intentionally removed from this active plan. They remain available through:

- [`docs/legacy/Soma_Roadmap_V3_Implementation_Record_2026-08-15.md`](docs/legacy/Soma_Roadmap_V3_Implementation_Record_2026-08-15.md) - full pre-cleanup V3 active-plan snapshot;
- [`docs/legacy/`](docs/legacy/) - completed/superseded roadmap records;
- individual gate, result, acceptance, and research documents under `docs/`;
- Git history and durable Soma run evidence.

The active plan should remain short. When a lane closes, its detailed implementation narrative belongs in evidence/legacy records and this file should retain only the current status, next intended work, frozen strategic lanes, and owner-relevant boundaries.
