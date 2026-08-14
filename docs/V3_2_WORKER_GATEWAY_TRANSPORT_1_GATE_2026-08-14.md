# V3-2-WORKER-GATEWAY-TRANSPORT-1 — Isolated Worker MCP Source Gate

**Date:** 2026-08-14
**Status:** ACCEPTED / CLOSED
**Parent:** V3-2 — Role-scoped capability broker
**Parent status:** ACCEPTED / CLOSED — controlled loopback activation passed
**Depends on:** accepted `V3-2-AUTHORITY-FOUNDATION-1` at `54bd9c92168a15cc863a55a668063099137895ad` / `33dbcf6b2d5c3df443a8af082a44bfe52925272e`
**Live worker listener:** forbidden
**Live worker-authority migration:** forbidden
**Current owner/executive MCP changes:** forbidden
**Real provider/Codex generation:** forbidden without a new explicit owner request
**Protected external mutation:** forbidden
**Push/deployment:** forbidden

## 1. Objective

Build the provider-neutral worker-facing MCP **source** boundary without mounting or starting it.

The worker surface must remain a separate FastMCP application from the current owner/executive `soma.server.mcp`. It may expose transport-control tools for authenticated capability discovery and grant-bound invocation, but it must never register, mirror or pass through the current 34 owner/executive gateways.

The source package proves isolation and authorization mechanics only. A later live activation gate must separately install the worker-authority schema, bind an isolated listener/route, issue disposable authority and prove network/runtime isolation before any real worker receives Soma capabilities.

## 2. Authentication boundary

Use FastMCP 3.4.2 `TokenVerifier` on the isolated worker app.

A bearer token is transport authentication material, not capability authority. The token format may combine the non-secret `principal_id` with the one-time reusable credential so the verifier can locate the durable verifier record without storing or sending the credential in MCP tool arguments.

Required behavior:

- bearer credential material never appears in tool input models;
- verifier authenticates against the accepted worker-authority verifier using constant-time comparison through `WorkerAuthorityService.authenticate`;
- successful FastMCP `AccessToken` contains only non-secret subject/claims such as `principal_id`;
- invalid, malformed, expired or revoked principals cannot receive usable worker results;
- tool code derives authenticated principal identity from FastMCP auth context, never from caller-supplied `principal_id` fields;
- no reusable credential is returned in results, error details, projections or explicit Soma audit evidence.

The package must use FastMCP error masking / bounded error translation so authorization failures expose stable denial codes without reflecting bearer tokens or raw secret-bearing input.

## 3. Static transport tools vs dynamic capabilities

The isolated worker MCP may statically register exactly two transport-control tools:

- `worker_capabilities` — authenticated discovery of the caller's currently usable positive grants;
- `worker_invoke` — invoke one exact reviewed worker operation through one exact active grant.

These two transport tools are not themselves business/engineering capabilities and do not expand owner authority.

`worker_capabilities` must return only active grants belonging to the authenticated principal, filtered again against current principal/grant expiry/revocation and exact ProjectScope/Task/Run/session/Task-state/cancellation constraints. It must not reveal grants belonging to another principal or operations that are no longer mechanically usable.

Discovery output may identify grant/operation/intent/parameter-contract hashes and bounded non-secret contract material needed for invocation. It must not expose verifier hashes, credentials, provider-native secret material or unrelated principal records.

## 4. Invocation boundary

`worker_invoke` accepts only the minimal worker-controlled material required to execute an already-granted operation, such as:

- exact `grant_id`;
- exact bounded operation parameters;
- expected canonical Task state version;
- a caller request/idempotency identity where the operation contract requires one.

The worker does **not** submit role, mandate, intent or operation authority fields. The gateway resolves those facts from the authenticated principal and durable grant, constructs the exact internal `WorkerAuthorizationRequestV1`, and re-authorizes on every invocation.

Successful authorization is still not sufficient to call arbitrary Soma code. Invocation must pass through a separate reviewed `WorkerOperationDispatchRegistry` keyed by exact `operation_ref`. The dispatch registry:

- is positive allowlist only;
- rejects duplicate operation registrations;
- requires an operation to exist in the accepted `WorkerOperationRegistry`;
- has no fallback by tool name, Python import, public gateway name or shell command;
- cannot address the current owner/executive gateways merely by naming them;
- receives only the authorization decision, durable grant and bounded parameters needed by its exact handler.

No built-in protected external mutation handler belongs to this package. G4 protected-effect integration remains later and must continue to use `WorkerProtectedAuthorityResolver` + `ProtectedToolBroker` rather than bypassing them.

## 5. Error and secrecy contract

Worker-facing results/errors must be bounded and non-secret.

Required denial shape is conceptually:

```json
{
  "ok": false,
  "error": {
    "code": "grant_revoked",
    "detail": "capability grant is revoked"
  }
}
```

No traceback, bearer token, reusable credential, verifier hash or entire input envelope may be reflected.

Malformed Pydantic/FastMCP requests must remain bounded by strict `extra='forbid'` request models. FastMCP application configuration should mask internal exception details.

## 6. Isolation contract

The package must prove:

- `soma.server.mcp` remains exactly the accepted 34-tool owner/executive surface;
- the worker app factory is importable without importing/registering it into `soma.server`;
- a constructed worker app contains only the two worker transport tools plus any framework metadata routes that FastMCP necessarily owns;
- no owner/executive public gateway callable is present in the worker app registry;
- building a worker app does not install the worker-authority schema, bind a socket, start a service, or mutate runtime configuration;
- no current Cloudflare/connector route changes occur.

## 7. Required source proof

The source package cannot close without tests proving at least:

- invalid/malformed bearer authentication is denied before tool execution;
- valid bearer authentication establishes only the exact principal subject;
- capability discovery returns only that principal's active exact grants;
- discovery removes expired/revoked/stale-scope/stale-session/cancelled-Task grants;
- invocation derives authority from the durable grant, not caller-supplied authority claims;
- wrong grant/principal/parameters/state version/revocation/expiry fails before handler execution;
- handler registry cannot dispatch an unregistered operation or owner gateway name;
- handler executes exactly once after successful re-authorization and receives no bearer credential;
- handler exceptions are translated to bounded non-secret worker errors;
- worker transport response bodies contain no reusable credential/verifier material;
- worker app construction is inert with respect to schema/runtime/listener state;
- owner public tool count/schema hash and public discovery tests remain unchanged;
- accepted worker-authority, ProjectScope, Task, WorkerSubstrate and G4 tests remain green.

## 8. Acceptance evidence

The isolated worker MCP source boundary is **ACCEPTED / CLOSED** at implementation commit:

- `fd60ef48fa129ff1f280893e552be42741d81321` — `Implement V3-2 isolated worker gateway transport`.

Accepted source behavior:

- separate FastMCP worker application factory; it does not import, register into, mount, start, or mutate `soma.server.mcp`;
- exactly two static worker transport tools: `worker_capabilities` and `worker_invoke`;
- transport authentication occurs before usable worker tool execution and resolves only the durable worker principal identity into request context;
- capability discovery is grant-shaped, principal-specific, revalidates current ProjectScope/Task/Run/session/cancellation/expiry/revocation state, suppresses grants without reviewed handlers, and is bounded in count and parameter-contract size;
- invocation derives authority from the authenticated principal plus durable grant and re-authorizes every call rather than accepting caller-supplied role/mandate/intent/operation claims;
- `WorkerOperationDispatchRegistry` is a positive allowlist with no fallback by Python import, shell command, public gateway name, or arbitrary tool name;
- current owner/executive gateway names are explicitly forbidden as worker dispatch operation names;
- protected-mutation handlers are excluded from this source package; future protected effects must continue through the accepted G4 boundary;
- handler cancellation propagates rather than being converted into an ordinary worker failure;
- worker parameter payloads, discovery projection size, and handler results are bounded;
- secret-shaped result keys are redacted, binary/unsupported values are projected without arbitrary object stringification, and worker-facing failures remain bounded;
- app construction remains inert: no worker-authority live migration, socket binding, service start, runtime configuration mutation, provider execution, deployment, or push occurs.

Final validation on the accepted source:

- Ruff run `20260814T192602Z_executable_profile_2106be56`: `All checks passed!`;
- focused worker transport run `20260814T192602Z_executable_profile_f2695dd7`: `17 passed`;
- focused integration run `20260814T192637Z_executable_profile_812c6ef8`: `398 passed, 26 skipped`, exit code `0`;
- definitive full repository run `20260814T192807Z_executable_profile_609c8bb6`: `3203 passed, 35 skipped, 1 xfailed, 0 failed`, pytest duration `931.95s`, durable run duration `933.676s`, exit code `0`.

The accepted owner/executive public surface remained unchanged at 34 tools with public schema hash `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`. The six protected canonical-memory / patch-auto-repair documents remained excluded from the package and untouched.

## 9. Exit / parent closure

`V3-2-WORKER-GATEWAY-TRANSPORT-1` is **ACCEPTED / CLOSED**. Its separate controlled activation gate also passed and overall V3-2 is now **ACCEPTED / CLOSED**.

Controlled activation used a disposable loopback-only worker endpoint, installed the accepted worker-authority schema v1, proved authenticated grant-shaped discovery and per-call re-authorization, revoked all disposable authority, removed the listener, and left the owner/executive 34-tool public surface unchanged.

The next roadmap lane is V3-3 and remains inactive pending explicit owner activation.
