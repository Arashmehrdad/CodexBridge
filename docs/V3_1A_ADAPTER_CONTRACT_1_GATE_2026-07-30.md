# V3-1A-ADAPTER-CONTRACT-1 — Provider Adapter Contract and Protocol Fixtures

**Date:** 2026-07-30
**Status:** accepted and closed after independent audit corrections; no provider process was launched.
**Parent lane:** `V3-1A — INTERACTIVE-WORKER-SUBSTRATE-1`
**Depends on:** accepted [`V3_1A_FOUNDATION_1_ACCEPTANCE_AUDIT_2026-07-30.md`](V3_1A_FOUNDATION_1_ACCEPTANCE_AUDIT_2026-07-30.md)
**Repository baseline:** `c11919e7410faef7c351b318de396000845e8e5a`
**Acceptance:** [`V3_1A_ADAPTER_CONTRACT_1_ACCEPTANCE_AUDIT_2026-07-30.md`](V3_1A_ADAPTER_CONTRACT_1_ACCEPTANCE_AUDIT_2026-07-30.md)
**Push:** none; not authorised.

## 1. Objective

Define and prove one provider-neutral internal adapter contract for Claude Code and Codex using versioned recorded protocol fixtures only.

This gate converts provider stream and command-shape drift into deterministic tests before Soma launches any provider process. It may construct inert command specifications and parse stored fixture lines. It may not execute those commands, mutate a provider environment, or expose a worker operation publicly.

## 2. Required outcomes

### Provider-neutral contract

The internal contract must represent, without creating lifecycle authority:

- provider and adapter identity/version;
- supported and unsupported capabilities;
- inert start and explicit-resume command specifications;
- stdin or payload-reference handling that keeps prompts and secrets out of argv;
- exact native session-identity extraction;
- deterministic event parsing;
- protocol and fixture identity/version;
- raw usage extraction into the accepted worker-substrate fields;
- fail-closed classification for unknown, malformed, conflicting, or drifted events.

The implementation may choose its internal types and module structure after inspecting the live repository. It must not add a public gateway merely to expose the contract.

### Claude fixture contract

Using frozen recorded Claude stream-JSON fixtures, prove:

- exact case-sensitive native session identity is extracted;
- explicit-ID resume specification preserves that identity;
- steering is declared supported because the accepted pilot measured it;
- provider-reported `total_cost_usd` is preserved as raw cost evidence;
- token fields remain `None` when Claude does not report them;
- known completion/failure/input events map deterministically;
- a changed or unknown event cannot fabricate progress or success.

### Codex fixture contract

Using frozen recorded `codex exec --json` fixtures, prove:

- exact native thread/session identity is extracted;
- explicit-ID resume specification preserves that identity;
- steering is declared `unmeasured` or unsupported rather than inferred;
- `turn.completed.usage` token units map exactly;
- provider-reported USD remains `None` without a separate pricing authority;
- known completion/failure events map deterministically;
- a changed or unknown event cannot fabricate progress or success.

## 3. Fixture integrity

Every accepted fixture must include:

- provider and protocol identity/version;
- source/pilot provenance;
- stable content hash;
- redaction review;
- no credential, bearer token, private prompt, personal data, or unrelated repository content;
- expected parsed outcome asserted independently of parser implementation.

Fixtures are compatibility evidence, not canonical company or execution state.

## 4. Fail-closed rules

- Unknown top-level events remain unknown; they do not imply running, completion, success, failure, input wait, or usage.
- Missing required native identity refuses binding.
- Conflicting native identity within one stream becomes protocol uncertainty.
- Malformed JSON is preserved as bounded raw evidence and cannot fabricate a parsed event.
- Protocol-version mismatch fails closed until a reviewed fixture update is accepted.
- Duplicate usage events rely on the foundation's deterministic dedupe contract.
- Provider capability declarations are explicit; absence is never treated as support.

## 5. Required tests

- deterministic parse of every frozen Claude and Codex fixture;
- exact case preservation for provider-native identities;
- explicit-ID resume specification for both providers;
- prompt/content supplied through stdin or reference, never ordinary argv;
- Claude cost with absent token fields;
- Codex token fields with absent USD;
- unknown event, malformed event, missing identity, and conflicting identity fail closed;
- capability declarations report Claude steering supported and Codex steering unmeasured;
- fixture hashes and expected outcomes are pinned;
- no parser path publishes task state, run state, result success, or OutcomeAcceptance;
- focused foundation tests remain green;
- no public schema or gateway inventory changes.

## 6. Acceptance evidence

The gate closes only when:

- the internal contract and both provider fixture adapters are implemented;
- all required fixture and drift tests pass;
- the existing 43-test foundation suite remains green;
- adjacent public-contract checks prove no connector-visible surface changed;
- an authority audit confirms adapters only construct inert specifications, parse evidence, and call accepted subordinate persistence contracts;
- the worktree is clean and local commits are recorded;
- nothing is pushed.

## 7. Explicit exclusions

- real Claude or Codex process launch;
- environment sanitisation execution;
- executable discovery, installation, authentication, or subscription purchase;
- provider-child PID capture or cancellation;
- `STEER`, `SUPPLY_INPUT`, pause, resume, or checkpoint task commands;
- operational `AWAITING_CONTROLLER` continuation;
- public worker gateway or direct worker Soma MCP access;
- V3-1B Company/Mission/PlanRevision/WorkPackage/AcceptanceCommit work;
- workflow or supervisor migration;
- production database activation;
- unrelated cleanup, deployment, or push.

## 8. Stop conditions

Stop and return to architecture review if:

- parsing requires a provider-specific execution lifecycle;
- a provider event must be interpreted as success without a stable required marker;
- explicit resume cannot preserve exact native identity;
- fixture provenance or redaction cannot be established;
- prompts or secrets must enter argv;
- the contract requires server registration or a public gateway;
- implementation must launch a provider to prove basic parsing;
- Codex steering is represented as supported without measurement.

## 9. Downstream prerequisites

After this gate, real process work remains blocked until a separate process/security package proves:

- sanitised environment and provider-recursion removal;
- exact executable identity;
- provider-child PID/start identity;
- owned-tree cancellation and zero-descendant evidence;
- repair or explicit disposition of the pre-existing `test_cancel_run_marks_cancelled` failure.

`V3-1A-INTERACTION-COMMANDS-1` remains later and inactive. No provider launch or interactive task-command semantics are authorised by this gate.

## 10. Completion report

Report:

- internal contract chosen and alternatives rejected;
- fixture files, hashes, provenance, and redactions;
- provider capabilities actually proven;
- parser and command-specification behavior;
- tests and validation results;
- authority delta and public-contract impact;
- known protocol limitations;
- exact recommended next V3-1A package.
