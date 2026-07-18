# Hermes Tool-Runtime Feasibility Audit

Date: 2026-07-18

Candidate upstream: `NousResearch/hermes-agent`

Pinned revision: `862b1b37bf0aadba3a98b3756c7d71779379b53b`

## Decision

Proceed with H1 through a small, versioned Hermes companion process. Do not import Hermes directly into the CodexBridge service process, and do not use the existing Hermes agent loop as an intermediary.

The companion should run from a pinned Hermes checkout and environment, initialize the effective Hermes tool registry, and expose a narrow machine protocol over stdio. CodexBridge remains authoritative for durable request identity, accepted arguments, cancellation state, bounded output, protected artifacts, retry policy, and terminal publication.

The existing upstream `mcp_serve.py` is not the required boundary. It exposes Hermes session, event, and approval controls to MCP clients; it does not expose the generic registry search, schema, and dispatch contract needed by H1.

## Feasibility Findings

### Registry, schemas, and dispatch

The pinned revision has a central `ToolRegistry` in `tools/registry.py`. It supports registration, deregistration, toolset aliases, generation-based cache invalidation, exact definition retrieval through `get_definitions`, and dispatch through `dispatch`. Registry entries identify asynchronous handlers explicitly.

The registry is sufficient to produce an effective tool catalog and invoke a selected handler, but raw `registry.dispatch` is not the correct public H1 call path because some policy, hook, approval, and edit-approval behavior is applied above it.

### Search, describe, and call without a model loop

`tools/tool_search.py` defines `tool_search`, `tool_describe`, and `tool_call` as ordinary bridge operations over the effective catalog. Search and describe are pure catalog reads. `tool_call` validates and unwraps the selected deferred tool.

`model_tools.py` handles these bridge operations before normal model-facing dispatch. Search and describe execute inline. A valid `tool_call` is converted to the underlying tool invocation and re-enters the normal execution path so pre/post hooks, edit approval, guardrails, and approval handling observe the real tool identity.

No model inference is required for these operations once the caller supplies the exact operation and arguments. Therefore ChatGPT can remain the only reasoning agent.

### Toolsets, built-ins, plugins, MCP, and skills

Built-in tool modules self-register into the central registry. Toolsets select subsets and aliases of that registry rather than defining a separate execution system.

Hermes plugin discovery can register tools and toolsets before effective definitions are assembled. Connected MCP servers are discovered and their tools are registered into the same effective catalog, with server-scoped dynamic toolsets. Tool Search can defer non-core plugin and MCP tools while keeping the small bridge surface visible.

Skills are instruction and workflow resources, not automatically callable registry handlers. H1 should expose callable tools contributed by built-ins, plugins, and MCP discovery. A skill affects the runtime only when its associated code or plugin registers an actual tool; CodexBridge should not reinterpret skill prose as executable schema.

### Results and errors

Handlers may return structured objects or JSON/text results. The companion must normalize every response into a versioned envelope rather than expose upstream return-shape differences directly. The envelope must distinguish success, provider/tool error, validation error, approval required, cancellation, timeout, ambiguous transport failure, and companion/runtime failure.

### Approval and mutation safety

Direct registry dispatch can bypass behavior implemented in `model_tools.py`. The companion must use the same underlying invocation path that preserves upstream pre-tool, post-tool, edit-approval, guardrail, and approval behavior, or explicitly reproduce and test those semantics.

CodexBridge policy remains an outer boundary. Hermes approval does not replace CodexBridge classification, human-only boundaries, idempotency requirements, or ambiguous-mutation reconciliation.

### Cancellation and long-running ownership

The pinned runtime can cancel pending asynchronous work inside its own event-loop/thread bridge, but the registry does not expose a stable provider-neutral external job identity and cancellation protocol for arbitrary tools.

Initial H1 calls must therefore be bounded synchronous companion requests. CodexBridge may terminate the companion request process on cancellation, but that alone cannot prove reversal of an already-started external mutation. Generic long-running or detached tools remain unsupported until they provide durable external ownership or an adapter-specific reconciliation contract.

### Runtime state and credentials

The companion needs an explicit Hermes home/configuration location, enabled toolsets, plugin discovery state, MCP server configuration, environment or protected credential delivery, and any provider-specific browser or OAuth state required by selected tools.

Secrets must enter through existing protected input, environment, or file mechanisms and must not be copied into public events, summaries, command lines, schema hashes, or durable plain-text arguments. H1 does not require broad R6 work unless the first selected Hermes tools cannot be launched safely with existing protected mechanisms.

## Accepted Companion Contract

The first companion protocol should provide:

- `handshake`: pinned Hermes revision, adapter protocol version, Python/runtime identity, registry generation, effective schema hash, active toolsets, and initialization warnings;
- `tool_search`: bounded query and result count over the currently enabled effective catalog;
- `tool_describe`: the exact current schema and identity for one available tool;
- `tool_call`: one validated bounded invocation using the normal Hermes policy/hook/approval path;
- deterministic response envelopes with protected artifact references when output exceeds the public bound.

Every call must include or verify the handshake identity. Registry generation or schema-hash drift between describe and call must fail explicitly instead of silently invoking a changed schema.

The adapter must not initialize a Hermes model client, agent loop, autonomous planner, delegated task loop, session conversation, cron loop, or memory-driven reasoning path.

## Minimal H1B Scope

1. Add a pinned companion configuration and handshake contract.
2. Launch the companion through the existing durable executable lifecycle with protected stdout/stderr and exact process identity.
3. Implement read-only `tool_search` and `tool_describe` first.
4. Add one bounded read-only `tool_call` using the same upstream execution path as direct Hermes tools.
5. Prove one connected MCP tool appears without tool-specific CodexBridge source code.
6. Add mutation support only after exact-once, approval, idempotency, and ambiguous-result reconciliation are defined for the selected reversible action.

## Explicitly Deferred

- Hermes model or agent invocation;
- generic detached or indefinitely running tools;
- automatic retry of external mutations;
- real-money, booking, refund, destructive, credential-changing, or production-impacting acceptance actions;
- broad secret-reference expansion unrelated to the selected companion launch;
- exposing every Hermes schema through the ChatGPT connector at startup.

## Next Executable Unit

Define and test the versioned companion handshake plus read-only search/describe protocol, including revision pinning, registry-generation/schema-hash binding, proof that no model client is initialized, bounded output, and deterministic failure on interface drift.
