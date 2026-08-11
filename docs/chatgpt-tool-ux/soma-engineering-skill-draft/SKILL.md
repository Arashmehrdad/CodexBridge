---
name: soma-engineering
description: Use when working on a software repository through Soma: inspect current state, make managed repository changes, run validation, inspect durable evidence, and report one coherent result without bypassing Soma's managed write boundaries.
---

# Soma Engineering

This is a workflow skill for ChatGPT. It teaches sequencing and reporting around Soma's MCP tools. It does not grant permissions, replace server authorization, or weaken the tool annotations and validation enforced by Soma.

## 1. Establish the target and intent

Resolve the repository, task, run, host, or project named by the user before acting. Prefer the narrow read surface when the request is only inspection.

For a continuation after interruption, first re-establish current repository/task/run state from Soma. Do not assume a previous patch, run, task, or external action is still current.

## 2. Repository changes use the managed lifecycle

For source changes:

1. Inspect repository state with the repository read tool.
2. Produce a managed change preview.
3. Inspect the preview and its exact identifiers/evidence.
4. Apply that exact preview only when the requested mutation is clear.
5. Validate with a durable command only when execution is requested or materially needed.
6. Read durable run evidence for the result.

Do not silently commit. Do not substitute a commit for a push. Do not claim push support when the public Soma surface does not provide it.

## 3. Durable execution and evidence

Use durable execution for tests, scripts, and configured commands. After launch, use the run/task read surfaces for status, terminal result, output, and evidence instead of repeating the command.

Cancellation is consequential. Target the exact durable run/task identity and report what was actually cancelled.

## 4. Canonical project memory

When the user says "project memory", "Soma project memory", or asks to update project memory, use Soma's canonical project-memory surfaces.

- Use the project-memory read tool for scope, search, exact retrieval, health, and stored packet retrieval.
- Use the context tool when the user needs a persisted canonical memory context packet.
- Use the memory action tool for canonical writes and lifecycle changes.
- Use supersede only when the predecessor lineage is unambiguous.

Repository wiki pages, `MEMORY.md`, controller-local memory, and legacy knowledge records are not substitutes for canonical project memory.

## 5. Infrastructure: inspect before mutate

For Docker, Cloudflare, SSH, and other infrastructure, inspect current state before mutation when the current state matters to the requested action.

Use a destructive-action surface only when the user's requested effect is deletion, removal, invalidation, pruning, destructive cleanup, or another hard-to-reverse operation. Do not turn a read or ordinary update into a destructive action.

For SSH:
- local capability/config/binding reads stay on the pure read tool;
- credential/profile preparation may persist local manifests and is not read-only;
- fresh capability/project validation probes may reach the remote host and persist snapshots;
- root shell and other administration actions remain externally consequential.

## 6. Trading surfaces stay distinct

Use local Trading Lab journal/status reads for stored outcomes, actions, reports, companion lists, and runtime status.

Use the live-market read surface for MT5/provider data such as ticks, candles, specifications, health, configuration, and broker exposure.

Use the companion-sync surface when refreshing one companion record; the current `sync=true` behavior updates authoritative journal links and is therefore stateful.

Use trading action/runtime-control surfaces only for explicit action intent. Do not route a status-only request to runtime control.

## 7. Explain meaningful actions, not every internal call

Before a meaningful mutation, briefly state the intended effect when that helps the user understand what will happen. Do not narrate every discovery/read call.

After the workflow, report:
- what was done;
- the actual result;
- the most useful durable identifier/evidence reference;
- any unresolved constraint, refusal, or next required user decision.

Keep the final report coherent rather than dumping a chronological tool transcript.

## Stop or ask instead of guessing when

Stop and resolve ambiguity when:
- the target repository, run, task, host, or destructive scope is ambiguous;
- a destructive external effect is broader than the user's request;
- commit or push intent is absent;
- a shared service restart, connector refresh, runtime-config change, or plugin install was not authorized;
- canonical memory supersession has more than one plausible predecessor;
- the current Soma surface does not support the requested capability.

This skill is guidance. Soma's MCP/server contract remains the authority for authorization, validation, idempotency, execution, and evidence.
