# MEMORY-DECISION-1 - Ready-Made Memory Provider Selection

**Date:** 2026-07-28
**Status:** superseded before provider-pilot execution by [`OBSIDIAN_MCP_DECISION_2026-07-28.md`](OBSIDIAN_MCP_DECISION_2026-07-28.md).
**Decision scope:** architecture selection only; no provider integration or active implementation lane.


## Supersession notice

This record is preserved as decision history. Its Basic Memory-first ordering was accepted before current Obsidian CLI, Bases, and native semantic MCP options were fully considered. No Basic Memory pilot execution or production integration occurred under this decision.

The current order is Obsidian-native first through MCP Connector, with Basic Memory retained only as a headless fallback after a named failure. The canonical-content and Soma-authority rules in this document remain valid.

## Historical decision

Use the following memory architecture for Soma/Cortana:

1. **Markdown + Git** remain the durable, owner-readable canonical content layer.
2. **Obsidian** is the owner-facing editor, browser, graph view, and manual workspace over those files.
3. **Basic Memory Local** is selected as the first ready-made AI memory provider behind a narrow Soma-owned process/MCP boundary.
4. **Soma** remains the sole authority for exact `project_id`, provider binding, routing, provenance, acceptance, continuity, and lifecycle decisions.

Basic Memory is selected for a future bounded compatibility pilot, not activated now. No installation, persistent provider state, production vault, MCP integration, or owner-memory import is authorized by this decision.

## Why Basic Memory is the selected provider

Basic Memory matches the established architecture with the least new machinery:

- knowledge remains ordinary Markdown rather than becoming opaque database-only memory;
- its database and embeddings are derived indexes rather than the canonical owner record;
- it exposes official MCP tools for reading, writing, searching, and building linked context;
- it supports local semantic and hybrid search without requiring a hosted embedding API;
- it supports explicit external project UUIDs and process-level single-project constraints;
- the same files can be opened directly in Obsidian and versioned with Git;
- it can remain an AGPL process boundary without making Soma a derivative implementation.

The intended boundary is:

```text
Soma project_id
  -> Soma-owned provider binding
  -> one project-constrained Basic Memory process
  -> Markdown project directory
  -> disposable provider index
  -> Obsidian opens the same directory
```

Soma must not trust Basic Memory's default-project fallback. Each provider process used by Soma must be constrained to one approved project, and the binding must record both Soma's opaque `project_id` and Basic Memory's external project UUID.

## Candidate disposition

### Obsidian alone - selected as UI, not as the AI provider

Obsidian is excellent for editing, links, properties, search, graph navigation, and direct ownership of local Markdown. It is not by itself a stable cross-agent MCP memory service with semantic retrieval and explicit Soma project routing. Therefore it is part of the chosen architecture, but not the provider boundary.

### Basic Memory Local - selected for the next bounded pilot

It is the closest fit to the file-first, owner-controlled, reversible architecture. It adds ready-made MCP and semantic retrieval while preserving Markdown as the durable source.

### Mem0 - not selected for this role

Mem0 is designed primarily as an application memory engine that extracts and resolves memories through an LLM and stores them in vector/history infrastructure. Its default and self-hosted paths introduce LLM, embedding, vector-store, and service configuration that is unnecessary for Soma's first durable project-memory layer. It remains a possible future candidate for automatic personal-preference or conversational fact extraction, not canonical project documentation.

### Cognee - deferred

Cognee combines relational, vector, and graph stores and normally uses an LLM plus embeddings to construct graph memory. That is useful when measured graph reasoning or large heterogeneous ingestion is required, but it is substantially heavier than the current need. It may be reconsidered only after Basic Memory fails a named relationship or reasoning requirement.

### PILOT-MEMORY-1B clarification

A custom Soma retrieval engine was **never an architecture candidate in the accepted plan**. `PILOT-MEMORY-1B` was supposed to benchmark the Markdown baseline and identify named gaps before comparing ready-made providers. Its custom package was an overbuilt benchmark artifact produced during execution, not a proposed production direction. It remains historical evidence only.

The original decision rule still applies: adopt or wrap a ready-made provider first, and add only the minimum custom component after a specific provider gap is demonstrated.

## Premature probe disposition

A disposable Basic Memory compatibility probe was started before this decision was properly documented. It was stopped and completely removed from `runs/pilots/basic-memory-1`.

The probe is **not acceptance evidence** and created no production state. It briefly confirmed that the official local package can expose project UUIDs, write Markdown, run local indexing, and perform project-specific commands. It also surfaced details that a future pilot must test deliberately: default-project behavior, maintenance commands using project names rather than UUIDs, and a Windows interpreter-shutdown warning after a batch of CLI writes.

No provider process, virtual environment, model cache, project folder, configuration, or generated index from that probe remains.

## Authority rules for any future pilot

- Soma owns `project_id`; no provider, folder, vault, repository, or conversation may infer or replace it.
- One constrained provider process serves one approved Soma project during automation.
- Markdown files are canonical; provider databases and embeddings are disposable and rebuildable.
- Obsidian edits the same canonical files; it is not a second memory authority.
- Cross-project access requires an explicit Soma-approved typed binding.
- Provider default-project fallback is disabled or ignored.
- Provider source modification, custom retrieval code, and a second canonical store are out of scope.
- No private conversation history or owner memory enters a pilot until the provider boundary is accepted.
- No push without explicit owner instruction.

## Next recommended lane

`PILOT-BASIC-MEMORY-1` may be prepared later as a single-controller, no-subagent compatibility trial using official tools only. It should answer a short pass/fail list:

- Windows process reliability;
- exact project constraint and external UUID binding;
- Markdown write/read and Obsidian compatibility;
- external edit detection;
- literal, semantic, and linked-context retrieval;
- strict sibling-project separation;
- index deletion and rebuild from files;
- clean removal with no loss of canonical content.

That pilot is **not active** after this decision. No implementation lane remains open.

## Official sources reviewed

- Basic Memory technical architecture, local MCP tools, project routing, semantic search, and configuration documentation.
- Obsidian official URI and local-vault documentation.
- Mem0 open-source architecture, self-hosting, and memory-operation documentation.
- Cognee architecture, local setup, MCP, and storage-backend documentation.
