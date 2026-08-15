# I1 Integrated Normal-Chat Acceptance

Date: 2026-08-15
Stage: I1 - integrated normal-Chat acceptance
Status: ACCEPTED
Branch: `lane/memory-integration-foundation-1`
Source baseline accepted before I1: `697aea70f3e96da4ae2dff0d7da9fa39329b4764`
Main continuation: `cont_20260815T163609Z_6ed6b4d86667`

## Owner scope at acceptance

During I1 the owner explicitly withdrew the additional normal-Chat agentic-reasoning-add-on objective and selected the already implemented capability as the desired programme end state:

- durable semantic continuation/re-entry for normal Chat;
- portable Soma Skill storage, discovery, retrieval, revisioning and explicit lifecycle mutation;
- existing Soma Task/Run/repository/SSH/etc. tools remain the action/execution substrate;
- no new reasoning redesign, semantic router, second model, automatic next-action engine, or agentic-loop driver is required by this programme.

The live continuation contract was revised to record that owner instruction before I1 was sealed. This acceptance therefore does not claim that continuation itself is a reasoning engine. It accepts continuation/re-entry and Skills as the owner-selected final scope.

## Architecture invariants

The accepted runtime remains:

```text
Sol / ChatGPT
  -> chooses semantics and any action
  -> continuation_query/action for durable re-entry when useful
  -> skill_query/action for reusable guidance when useful
  -> existing Soma tools for concrete inspection/execution
```

Soma does not choose the next semantic action, does not interpret handoff prose, and does not silently select or merge Skills.

## Live normal-Chat acceptance matrix

### A - interrupted repository implementation

PASS.

A fresh Chat was given only `@Soma continue`. It recovered the open I1 continuation without the owner supplying the continuation ID or reconstructing prior work, then independently inspected the live repository before continuing.

### B - long scientific Run

PASS.

Fresh Sol recovered linked Run `20260815T163651Z_executable_profile_f8e992eb`, observed the terminal `validation_score=0.873` result, and correctly kept `objective_complete=false`. Run terminality was treated as execution evidence rather than semantic objective completion.

### C - remote service repair

PASS.

Fresh Sol recovered prior Andiya evidence but independently revalidated the current remote state; `x-ui.service` was live-checked as active rather than trusting the historical handoff.

### D - contract change

PASS.

The fresh-Chat boundary recovered a current R4-equivalent contract while H3 belonged to the prior revision. `contract_changed_since_handoff=true` was recognized and H3 was not followed blindly. A new H4 checkpoint was written under the current contract.

### E - free-form variability

PASS.

Disposable science, operations and editorial continuations used materially different free-form handoff prose without adding domain-specific semantic fields. All fixtures were subsequently closed.

### F - explicit Skill use

PASS.

The owner explicitly requested `arash-research`. Sol fetched the current exact Skill before repository inspection and followed its evidence-first/adversarial-check guidance.

### G - implicit useful Skill

PASS.

For an evidence-backed Soma architecture audit that named no Skill, Sol chose to inspect the installed Skill library, selected applicable Skills, and loaded them. Soma itself did not semantically route the request.

### H - negative control

PASS.

The owner sent exactly:

```text
Reply with the word hello.
```

Sol replied `hello`. Zero `skill_query` calls occurred.

### I - multiple Skills

PASS.

For the implicit architecture audit, Sol loaded both `soma-evidence-audit` and `arash-research`, reconciled their guidance itself, and used ordinary Soma inspection tools. Soma neither selected nor merged their semantics.

### J - conflicting same-name source

PASS.

Live lifecycle acceptance established that a same-name revision from different provenance cannot silently replace the owner-selected current revision.

### K - Skill update mid-continuation

PASS.

The continuation remained open while `arash-research` moved from R7-I1 to R8-I1. Fresh Sol discovered current R8-I1 while exact historical R7-I1 remained retrievable.

Current at the fresh boundary:

`skill:arash-research@sha256:cb5a6a616ad9977eec78aae7aebad6e1f150cd53901d3ca7f4c09f869a1a8e4f`

Historical exact revision:

`skill:arash-research@sha256:d2138ef940bf408290b19778f70ed983732dc004648f54710733956c956eac87`

### L - bundled script

PASS.

Skill resource retrieval remained inert/read-only. Reading a bundled script did not execute it; execution authority remained an explicit existing Soma execution call.

### M - closed continuation admission

PASS.

Completed/cancelled continuation fixtures remained readable for history/resume while new continuation-sensitive writes and associated work admission were rejected.

### N - immutable origin replay

PASS.

Task/Run logical request replay could not change, add or omit a previously bound continuation origin without conflict; no relinking/detachment occurred.

### O - concurrent contract update

PASS.

Two writers using the same current contract revision produced one successful revision advance and one stale-contract result.

### P - Skill context-loss/compaction recovery

PASS.

The fresh-Chat boundary did not rely on prior Skill output remaining in context. Current/exact immutable Skill revisions were re-fetched as needed.

### Q - untrusted repo-local Skill

PASS.

Repository-local `.agents/skills/...` content is not silently ingested or activated. Source/runtime inspection found no active repository Skill scanner; import remains explicit.

## Skill discovery/recall corpus observations

Observed normal-Chat behavior:

- explicit Skill name -> exact/current retrieval occurred;
- clear implicit Skill use -> Skill search occurred;
- trivial request -> no Skill search;
- multiple applicable Skills -> Sol selected/reconciled them;
- exact historical revision -> retrievable;
- resource retrieval -> bounded/inert;
- no hidden semantic Skill router was introduced.

No optional browser/native adapter is justified by this acceptance corpus.

## Runtime identity observed during I1

The live public runtime converged to:

- public gateways: 38;
- operation schemas: 286;
- public schema hash: `5ef04e36efed1496ede40ffe3c51c8f8fe3de06255f0b9ecfda15905c4df8ebd`;
- public descriptor hash: `e53780fa49bc31702e89601bd8f9b8db3844b15aeac5b77c0659a0e2171ebd60`;
- operation inventory hash: `ffdcc0d5f7bb2d93316c3ce0b67de86b1d8f1dc35162316005b95a117417165b`.

## Durable evidence

Main acceptance continuation:

`cont_20260815T163609Z_6ed6b4d86667`

Key handoffs:

- setup H3: `conthandoff_20260815T163810Z_54548d91823c`;
- fresh-Chat H4: `conthandoff_20260815T165001Z_c55fe4ccfec2`;
- explicit Skill F: `conthandoff_20260815T165147Z_23d491df0779`;
- implicit/multiple Skill G/I: `conthandoff_20260815T165841Z_e0ca5f09fd43`;
- consolidated H negative-control checkpoint: `conthandoff_20260815T172133Z_b8caf5eb0076`.

## Repository safety

At the I1 seal boundary:

- no tracked/staged changes pre-existed;
- unrelated concurrent untracked research/audit files were preserved untouched;
- no Codex/provider subagent was used;
- no push occurred;
- no dormant legacy router cleanup was folded into I1;
- I2 had not yet been started during the behavioral corpus.

## I1 verdict

**ACCEPTED.**

The owner-selected continuation/re-entry + portable Skill capability passed the mandatory real normal-Chat corpus. Unit tests were supporting evidence only; the decisive cases used real normal-Chat/fresh-Chat behavior and live Soma state.

Next stage: I2 documentation, migration compatibility, public-capability reconciliation, final validation and programme closure.
