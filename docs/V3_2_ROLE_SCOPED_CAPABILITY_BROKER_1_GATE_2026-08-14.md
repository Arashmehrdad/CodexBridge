# V3-2-ROLE-SCOPED-CAPABILITY-BROKER-1 — Worker Authority Boundary

**Date:** 2026-08-14
**Status:** ACTIVE
**Parent:** V3-2 — Role-scoped capability broker
**Depends on:** accepted/live V3-1B Kernel of One
**Real provider execution:** forbidden
**Codex/provider generation:** forbidden without a new explicit owner request
**Current owner/executive MCP changes:** forbidden unless a separately reviewed compatibility need is proven
**Worker-facing current Soma MCP access:** forbidden until this gate closes
**Push/deployment/external mutation:** forbidden

## 1. Objective

Add the smallest provider-neutral worker authorization substrate that can prove one unforgeable worker principal is entitled to one exact Soma intent/operation inside one exact ProjectScope, canonical Task/Run and provider-session binding.

The boundary is positive-allowlist and deny-by-default. Discovery filtering may improve ergonomics but is never authorization.

V3-2 must not create another Task/Run lifecycle, another ProjectScope authority, another protected-effect engine, or an organisational Role/Assignment model ahead of V3-4.

## 2. Current-state audit

The repository already contains strong reusable identity/effect mechanics:

- ProjectScope owns exact `project_id`, `resource_id`, `scope_generation`, lifecycle and Task/Run attachment;
- canonical Task/Run owns execution lifecycle and state/version/cancellation precedence;
- interactive worker substrate owns provider-neutral `session_binding_id` tied to exact ProjectScope, Task, Run, provider and native session;
- worker message contracts already carry exact sender/recipient, mandate reference/version, message class and command identity as evidence;
- command profiles and environment allowlists constrain execution shape but are not per-principal authorization;
- provider adapter capability declarations describe provider features and are not Soma authority;
- G4 `ProtectedToolBroker` already validates Task/Attempt/current-plan/ProjectScope/cancellation/payload/resource facts and requires a Soma-controlled resolver for exact mandate, capability, tool-operation, idempotency and approval facts;
- the current 34-tool public MCP surface is owner/executive-facing and must not be repurposed as a worker surface.

There is no existing generic worker principal/capability-grant authority. The only repository use of `principal` outside this lane is unrelated SSH ACL inspection. Therefore V3-2 needs additive worker authorization state rather than renaming an existing principal system.

## 3. Authority contract

A worker principal must be bound mechanically to all of:

- opaque principal identity;
- exact ProjectScope `project_id`, `resource_id`, `scope_generation`;
- exact canonical `task_id` and `run_id`;
- exact interactive `session_binding_id` when the route is interactive;
- an opaque `role_ref` context label;
- exact mandate reference/hash/version;
- expiry and revocation state.

`role_ref` is context only in V3-2. It is not an organisational Role record and cannot grant capability by itself. V3-4 may later replace/resolve it through real Role/Assignment authority without changing the worker principal identity contract.

The authentication credential for a principal must be unforgeable and secret-bearing. Its reusable secret material must never be stored in plaintext durable state, public projections, logs, audit text or MCP tool results. Durable state keeps only non-secret principal identity and verifier material. Exact cryptographic construction is an implementation choice, but the gate requires at least cryptographically strong random-equivalent unguessability and constant-time verifier comparison where applicable.

## 4. Positive capability grant

A principal possesses no Soma operation by default.

Every grant must immutably bind:

- principal identity;
- exact intent reference/hash;
- exact operation reference/hash from a reviewed Soma operation registry;
- exact ProjectScope/Task/Run/session authority ceiling inherited from the principal;
- mandate reference/hash/version;
- bounded resource/parameter contract where the operation needs one;
- issuance identity, expiry and content hash.

A worker cannot self-assert, widen, substitute or transfer a grant. Opaque provider/agent/thread/call IDs are provenance only and cannot mint authority.

Operation discovery is shaped from active grants only after authentication, but an operation must repeat the same authorization check at execution time. A stale discovery result never authorizes a call.

## 5. Revocation and precedence

New worker actions must fail before side effects when any of the following is true:

- principal credential invalid;
- principal revoked/expired;
- grant missing/revoked/expired;
- ProjectScope generation/lifecycle changed;
- Task/Run identity or state no longer matches the principal ceiling;
- accepted Task cancellation intent takes precedence;
- interactive session binding is absent, mismatched or no longer durably `bound` where required;
- mandate ref/hash/version differs;
- intent or operation identity differs;
- operation parameters exceed the grant's bounded contract.

Revocation is deny-new-action authority. It must not fabricate reversal of an effect that has already crossed an existing protected-effect boundary.

## 6. Reuse of the G4 protected broker

V3-2 does not add another mutation path.

For protected mutations, the capability broker must provide the trusted mechanical facts expected by `ProtectedAuthorityResolver` and then delegate the effect boundary to the accepted `ProtectedToolBroker`. G4 remains authoritative for:

- current Task/Attempt/Plan/ProjectScope validation;
- cancellation precedence;
- payload hash;
- resource lease/serialization;
- effect idempotency;
- external-effect evidence and `outcome_unknown` containment.

V3-2 owns worker authentication, grant resolution and operation authorization. It must not duplicate G4 effect lifecycle tables or adapters.

## 7. Worker-facing transport boundary

The eventual worker-facing capability surface must be physically/logically separate from the current owner/executive MCP authority boundary.

Requirements before live worker exposure:

- authenticate the worker principal before usable capability discovery;
- expose only positively granted operations;
- authorize every invocation independently of discovery;
- no generic pass-through to arbitrary current public gateways;
- no operation can invoke an owner/executive mutation merely by naming it;
- credential material is stripped from logs/results/evidence;
- malformed, extra-field, wrong-scope, stale-state and wrong-operation requests fail before delegation;
- current owner/executive MCP tool inventory and behavior remain unchanged.

The first source package may implement the durable principal/grant authority and pure authorization engine without opening a live worker listener. A separate activation package will prove the transport boundary before any real worker receives Soma capabilities.

## 8. Initial package — V3-2-AUTHORITY-FOUNDATION-1

Implement only the provider-neutral authority substrate:

- additive schema/models/store for worker principals, verifier material, immutable grants and revocation evidence;
- reviewed operation identity registry contract;
- pure authorize/resolve path that revalidates ProjectScope, Task/Run, session, mandate, intent, operation, expiry and revocation;
- exact replay/idempotency/content-hash behavior;
- adapter from accepted grants into G4 `ProtectedAuthoritySnapshotV1` facts without executing a protected effect;
- bounded non-secret projections for tests/future worker discovery.

No public MCP operation, live worker listener, provider launch, protected external mutation or owner-surface change belongs to this package.

## 9. Required proof

The authority foundation cannot close without focused proof that:

- principal credentials are unforgeable/verified without durable plaintext secret storage;
- exact issue replay converges and changed identity/authority material conflicts;
- no grant means no operation;
- exact grants authorize only their exact intent/operation and bounded contract;
- wrong principal, ProjectScope, Task, Run, session, role context, mandate, intent, operation, expiry or state fails before delegation;
- Task cancellation and principal/grant revocation deny new actions;
- provider-local IDs never participate in authority identity;
- protected-mutation resolution yields only the exact G4 authority snapshot and never calls an adapter/effect boundary;
- repository restart/reopen preserves the same authority result;
- existing ProjectScope, Task, worker substrate, protected broker, Company Kernel and public gateway tests remain green;
- no owner/public schema identity changes in the foundation package.

## 10. Exit / next package

Close `V3-2-AUTHORITY-FOUNDATION-1` only after the durable positive-allowlist authority is proven. Then proceed to a separately bounded worker-facing gateway/transport package that consumes this authority and remains inactive until its own live isolation proof passes.
