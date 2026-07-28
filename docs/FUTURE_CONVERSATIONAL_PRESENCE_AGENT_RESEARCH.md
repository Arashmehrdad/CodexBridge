# FUTURE-CORTANA-PRESENCE-AGENT-RESEARCH — Two-Speed Conversation and Calls

**Date recorded:** 2026-07-28  
**Status:** parked future research; no active implementation lane.  
**Priority:** below the current memory-provider and code-intelligence work.  
**Decision authority:** none created by this note.

## Concept

Explore a mature Cortana/Jarvis-style interaction layer in which a fast, inexpensive **presence agent** maintains a natural live conversation while a stronger reasoning backend performs consequential work through Soma.

The presence agent is not a second brain. It provides immediate acknowledgement, clarification, interruption handling, truthful progress narration and spoken delivery. The reasoning backend owns research, judgment, tools and final answers. Soma owns identity, memory, task state, permissions, evidence and routing.

```text
User speech or text
        ↓
Presence agent
        ├─ acknowledges immediately
        ├─ paraphrases the request
        ├─ asks bounded clarification
        ├─ narrates verified progress events
        └─ manages interruption and delivery
                ↓
Soma conversation orchestrator
        ├─ project identity and memory
        ├─ tasks, runs and evidence
        ├─ permissions and escalation
        └─ backend routing
                ↓
Heavy reasoning backend
        ├─ research and analysis
        ├─ tool use
        ├─ decisions
        └─ final answer
                ↓
Presence agent presents the approved result
```

## Non-negotiable authority boundary

The presence agent may:

- acknowledge and paraphrase;
- ask a bounded missing-information question;
- react to interruption and manage turn-taking;
- convert verified Soma events into natural progress language;
- verbalize or shorten an approved answer without changing its meaning;
- answer low-risk social remarks when no project fact or commitment is involved.

The presence agent may not:

- invent progress, sources, findings or tool activity;
- make consequential decisions;
- modify durable memory or project state;
- execute privileged tools, commit code or push;
- create promises, prices, deadlines, admissions or contractual commitments;
- silently revise, contradict or embellish the heavy brain's answer;
- answer from stale context when Soma marks a result incomplete or uncertain.

## Truthful progress contract

Conversational filler must be derived from actual system events rather than fabricated activity. Future research should define a stable event vocabulary such as:

```text
request_received
project_resolved
memory_lookup_started
memory_lookup_completed
research_started
source_review_in_progress
tool_started
tool_waiting
clarification_required
candidate_comparison_started
draft_ready
owner_approval_required
execution_started
execution_completed
execution_failed
```

Each event should carry enough structured detail for safe phrasing, cancellation, UI display and audit. The presence agent should receive only the event and approved public metadata, not unrestricted hidden reasoning.

## Phone-call direction

The same architecture may later support prepared phone calls. The intended pattern follows Soma's packet-bound companion workflows:

1. **Start:** record the call objective, counterparty, constraints and desired close.
2. **Research:** the heavy brain gathers facts, policies, history and likely questions.
3. **Clarify:** the presence agent asks the owner only for missing information.
4. **Prepare:** Soma creates a frozen call packet containing verified facts, approved answers, questions, negotiation limits, forbidden commitments and escalation rules.
5. **Review:** the owner approves the packet before any real call.
6. **Execute:** the voice agent speaks only from the approved packet and verified live events.
7. **Escalate:** unexpected or consequential questions pause the call or route to the heavy brain/owner before commitment.
8. **Record:** transcript, decisions, promises, evidence and follow-ups return to Soma and the durable memory layer.

A future call packet should include at minimum:

- objective and success condition;
- identity and disclosure wording;
- verified facts with provenance;
- approved questions and answers;
- negotiation limits;
- forbidden statements or commitments;
- privacy and authentication rules;
- escalation and human-takeover rules;
- desired closing statement and follow-up channel.

## Candidate categories for later research

These are hypotheses, not selections. Availability, licensing, pricing, privacy and capabilities must be re-verified when this lane is activated.

- **Presence model:** a small local or low-cost model, with NVIDIA Nemotron-family models among the candidates.
- **Heavy brain:** ChatGPT/OpenAI, Claude, another frontier backend or a replaceable multi-provider route.
- **Backend access:** supported API first; browser-mediated ChatGPT access only as an explicitly reviewed experimental option.
- **Speech shell:** local speech recognition and synthesis, ElevenLabs-style speech infrastructure, or another replaceable streaming voice provider.
- **Telephony:** a provider that supports consent, call transfer, recording controls, interruption and regional compliance.

No candidate receives architectural authority merely by appearing in this list.

## Maturity path

### Stage 0 — parked research

Current state. Preserve the concept only. No prototype, vendor account, API spend, browser automation, microphone work or telephony integration.

### Stage 1 — event and authority design

Define the truthful progress-event contract, permissions, cancellation semantics, latency budgets, audit trail, failure language and heavy-brain handoff protocol.

### Stage 2 — text-only presence prototype

Use synthetic tasks to test immediate acknowledgements, real event narration, clarification, interruption and faithful delivery. No voice and no consequential execution.

### Stage 3 — local voice shell

Add streaming speech input/output, barge-in, echo handling and session recovery while keeping the same text/event contracts.

### Stage 4 — simulated calls

Run scripted and adversarial call simulations using frozen packets, unexpected questions, escalation and human takeover. No external calls.

### Stage 5 — bounded real calls

Permit narrowly scoped calls only after owner approval, legal/privacy review, reliable human takeover and complete evidence capture.

## Research questions to answer later

- What latency threshold makes the presence layer feel genuinely live rather than turn-based?
- Which responses should be deterministic templates rather than model-generated?
- Can the presence model run locally with acceptable quality, power use and multilingual performance?
- How should interruption cancel speech, generation and downstream tools without losing task state?
- How is the heavy backend selected, retried and replaced without changing the user-facing session?
- Can a supported API meet cost and continuity requirements, or is an experimental browser backend worth the fragility and policy risk?
- How should Soma expose progress without leaking private reasoning, credentials or unsafe intermediate conclusions?
- What consent, disclosure, recording and impersonation rules apply to automated calls in each jurisdiction?
- How are authentication, payment information, legal admissions and identity verification excluded or escalated?
- How should transcripts be redacted, retained, indexed and linked to project evidence?
- What failure phrase is used when memory, research or the heavy brain is unavailable?
- What quantitative gates measure latency, factual fidelity, interruption success, escalation correctness and cost?

## Activation prerequisites

Do not activate this lane until:

- the current project-memory provider decision is documentation-closed;
- the planned Codebase Memory comparison is closed, unless the owner explicitly reprioritizes;
- Soma has stable context assembly, event reporting, cancellation and permission contracts;
- the owner explicitly activates future conversational-presence research;
- current candidate capabilities, terms, licensing and prices are researched again from primary sources.

## Present disposition

The concept is worth preserving and should be developed as a mature, replaceable interface layer in the future. It is intentionally not part of the active roadmap sequence today. The immediate priority remains durable memory continuity and derived code intelligence.
