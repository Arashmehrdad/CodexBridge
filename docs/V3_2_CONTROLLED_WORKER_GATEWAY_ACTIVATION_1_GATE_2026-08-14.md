# V3-2-CONTROLLED-WORKER-GATEWAY-ACTIVATION-1 — Loopback Activation Gate

**Date:** 2026-08-14
**Status:** ACTIVE
**Parent:** V3-2 — Role-scoped capability broker
**Depends on:** accepted worker authority foundation `54bd9c92168a15cc863a55a668063099137895ad` / `33dbcf6b2d5c3df443a8af082a44bfe52925272e` and accepted isolated worker transport source `fd60ef48fa129ff1f280893e552be42741d81321` / `196943167be700bee06664345229b101ac3669d0`
**Owner/executive public MCP changes:** forbidden
**Cloudflare/tunnel/firewall/external access changes:** forbidden
**Real provider/Codex generation:** forbidden
**Protected external mutation:** forbidden
**Push/deployment:** forbidden

## 1. Objective

Prove the accepted V3-2 worker capability boundary against the live Soma durable store and a real HTTP transport without granting any external access or changing the current owner/executive MCP surface.

This is an outcome proof, not a permanent worker-daemon deployment. The worker HTTP listener must exist only for the bounded proof and must bind to `127.0.0.1` on an isolated high port. It must be stopped and verified absent before this gate closes.

## 2. Live-state boundary

The activation may perform only these live durable changes:

- take a consistent SQLite backup of the current live `runs/soma.sqlite3` before worker-authority migration;
- explicitly install the accepted additive `worker_authority` schema through `WorkerAuthorityStore.init_db()`;
- create one disposable local repository identity and ProjectScope binding;
- create one disposable canonical Run and Task and attach them through the accepted ProjectScope/Task/Run authorities;
- issue one disposable worker principal and one or more disposable positive grants required for the proof;
- record immutable grant/principal revocation evidence at proof completion;
- terminalize the disposable Task/Run so no activation work remains active.

The activation must not alter existing Company Kernel, reasoning, memory, trading, SSH, Cloudflare, Docker, tunnel, or owner/public MCP configuration.

## 3. Network isolation contract

The activation listener must:

- bind only to `127.0.0.1`;
- use a dynamically selected high TCP port;
- expose only the accepted separate worker FastMCP application;
- never mount into `soma.server.mcp`;
- never create or modify Cloudflare routes, tunnel configuration, firewall rules, DNS, reverse proxies, external permissions, or public URLs;
- be owned by one disposable child process whose identity is captured;
- be terminated at the end of the proof;
- leave no listener on the selected port after teardown.

Before and after the proof, `system_query -> capabilities` must still report exactly 34 owner/executive tools and public schema hash `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`.

## 4. Disposable capability proof

Use one activation-only reviewed query operation with:

- an opaque operation identity that is not a current owner/public gateway name;
- `operation_kind = query`;
- `requires_session = false` so no provider or fake provider-session binding is needed;
- canonical Task state `running` as its allowed state;
- an exact small parameter contract;
- one reviewed in-process handler that returns only bounded local proof data.

The proof must demonstrate over the real loopback HTTP endpoint:

1. unauthenticated or malformed authentication material is refused before worker tool execution;
2. valid authentication reaches `worker_capabilities` and returns only the exact active executable grant for the authenticated principal;
3. `worker_invoke` succeeds only for the exact grant and exact parameter contract;
4. wrong parameters or stale state fail before the handler executes;
5. grant revocation denies a subsequent invocation before the handler executes;
6. principal revocation denies subsequent authentication;
7. worker responses do not expose reusable credential or verifier material;
8. no protected mutation or owner/public gateway is reachable through the worker dispatch registry.

No real provider, model, browser, external API, or protected external effect belongs to this proof.

## 5. Migration and rollback evidence

Before migration:

- record worker-authority `schema_state`;
- create a consistent SQLite backup using SQLite's backup API rather than copying an open WAL database;
- record backup path, byte size and SHA-256;
- preserve the pre-activation owner public schema identity.

After migration:

- require worker-authority schema version `1` and no missing worker-authority tables/triggers;
- keep the accepted additive migration installed if the proof succeeds;
- preserve the backup as rollback evidence;
- on migration/proof failure, stop the worker listener and do not attempt ad-hoc schema deletion.

A successful activation does not require restoring the pre-migration database: the migration is additive, accepted, and required for future V3-2 authority. Rollback evidence is the consistent pre-migration backup plus complete listener teardown and disposable-authority revocation.

## 6. Required closure evidence

This gate cannot close without all of:

- pre-activation owner surface = 34 tools and accepted public schema hash;
- live SQLite backup evidence;
- worker-authority schema version 1 installed through the supported migration path;
- disposable ProjectScope/Task/Run created and attached through canonical APIs;
- real TCP listener proven on `127.0.0.1` only;
- authenticated discovery and exact invocation success;
- malformed authentication refusal;
- wrong-parameter/stale-state denial before handler execution;
- grant revocation denial before handler execution;
- principal revocation authentication denial;
- no credential/verifier leakage in public proof results;
- worker listener stopped and selected port confirmed closed;
- disposable Task/Run terminalized and authority revoked;
- post-activation owner surface still exactly 34 tools with the accepted public schema hash;
- `system_query -> self_check` remains green;
- repository remains clean except the six protected/unrelated documents already excluded from this lane.

## 7. Exit

If the proof passes, close V3-2: workers then have a proven separate positive-allowlist capability boundary without receiving the current owner MCP surface. The next roadmap lane is V3-3 — Interactive executive loop and bounded collaboration.

If any proof fails, keep V3-2 active, preserve evidence, stop the loopback listener, and repair only the failing V3-2 layer before retrying.
