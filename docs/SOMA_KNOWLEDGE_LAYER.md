# Soma Knowledge Layer

**Status:** production architecture accepted; first implementation batch active by explicit owner instruction on 2026-07-28.

## Purpose

Soma's knowledge layer preserves project facts, decisions, documents, research notes, lessons, relationships, sources, and historical context across ChatGPT, Claude Code, Hermes, and later compatible controllers.

It is designed for the owner's practical workflow: substantial research and architecture reasoning can be saved from a conversation, found in a later session, inspected in Obsidian, and traced back to its source.

## Authority boundary

Soma owns:

- exact opaque `project_id` selection and project access;
- stable knowledge identity, lifecycle, provenance, health, and continuity;
- the public save, search, retrieval, supersession, health, and rebuild contract;
- validation that returned paths and records belong to the requested project.

Ordinary Markdown is the durable, human-readable content representation. Obsidian is an editor and browser over that content, not a second authority. `KnowledgeCatalog` is a rebuildable SQLite projection used for scoped literal retrieval and continuity checks. Its loss must reduce convenience, not destroy the Markdown knowledge.

No external memory or vector provider is authoritative. A later provider may supply a replaceable derived index only after passing the same project-isolation, rebuild, health, provenance, and bilingual acceptance contract.

## First production slice

The first slice uses these implementation concepts:

- `KnowledgeInput` (also exposed as `ResearchNoteInput`) describes a requested save.
- `KnowledgeRecord` is the stable, source-grounded public record.
- `SourceReference` and `SourceLocator` preserve where information came from.
- `MarkdownVault` owns safe, atomic Markdown materialization beneath the bound project root.
- `KnowledgeCatalog` owns the rebuildable SQLite projection and literal full-text retrieval.
- `KnowledgeService` is the sole consistency boundary for save, search, get, supersede, health, and rebuild.
- `KnowledgeSearchPage`, `KnowledgeHealth`, and `RebuildResult` provide bounded, typed results.

Supported knowledge kinds are facts, decisions, documents, research, lessons, and questions. Relationships and richer distinctions may be represented in typed metadata in this slice; they are not yet a general evidence-graph engine.

Every record must retain:

- exact `project_id` and stable `knowledge_id`;
- kind, title, original content, language, tags, and status;
- canonical Markdown path and content hash;
- source references and exact locators when supplied;
- creation and update identity and timestamps;
- an explicit supersession link and reason when replaced.

Saving the same idempotent request must return the same logical result. Updating knowledge creates preserved historical context rather than silently erasing the prior statement. Superseded and disputed information remains retrievable when explicitly requested, while default search favours current active knowledge.

## Public workflow

The service contract comprises:

1. `save` — validate exact project scope, normalize a typed input, preserve provenance, write Markdown atomically, and update the catalog projection.
2. `search` — perform bounded, project-scoped literal retrieval with filters and a stable continuation cursor.
3. `get` — retrieve one exact record and its provenance without relying on ranking.
4. `supersede` — link an old record to its replacement and preserve both records.
5. `health` — compare canonical files with catalog generations and report healthy, degraded, or rebuilding state honestly.
6. `rebuild` — recreate derived catalog state from canonical Markdown without changing the Markdown.

All controller integrations must use this same Soma-owned service boundary. Provider defaults, active Obsidian vault state, repository names, working directories, and conversation identity must never infer `project_id`.

## Markdown and Obsidian contract

Knowledge files use stable physical filenames based on Soma identity. Editable titles and aliases belong in frontmatter. External edits made through Obsidian remain ordinary Markdown changes and are incorporated through a controlled rebuild or reconciliation path.

The first slice must not promise automatic live filesystem watching or link-aware rename behaviour. A physical rename outside Soma may be treated as remove-plus-add unless stable identity remains present and valid in frontmatter. Conflicting or malformed external edits must produce degraded health or a quarantine-style diagnostic; they must not be silently accepted as another project's knowledge.

Git may preserve additional owner-visible history, but runtime correctness and recovery must not depend on an automatic commit for every save.

## Retrieval and language limits

The first production slice provides literal and full-text retrieval only. It does **not** claim semantic search, embeddings, cross-language retrieval, or a working memory provider.

English and Persian content must round-trip without alteration. Search normalization may account for Unicode and common Persian/Arabic character variants, but stored source text remains unchanged. Same-language literal Persian retrieval is required where the indexed terms are present.

English-to-Persian, Persian-to-English, and paraphrase retrieval remain named limitations until a replaceable multilingual semantic index passes a frozen bilingual benchmark. Semantic health must be proven through complete manifest accounting and known-hit tests; an incomplete index may never present itself as healthy.

## Recovery model

Canonical Markdown and its stable identities are sufficient to rebuild the catalog projection. Rebuild must:

- remain strictly project-scoped;
- account for every eligible canonical file;
- reject or report duplicate identities, invalid paths, malformed provenance, and hash drift;
- publish a new derived generation only after the generation is complete;
- leave the prior healthy generation available, or report degraded state, after interruption;
- never modify canonical Markdown merely to make indexing succeed.

The first slice does not yet provide an immutable content-addressed raw-source archive, a normalized multi-table evidence graph, automatic database-to-vault disaster reconstruction, or a remote backup policy. Source URLs, repository paths, document locators, and supplied excerpts are preserved, but complete external documents must be retained separately when reproducibility requires them.

## Security and isolation

- Every public operation requires an exact active `project_id`.
- Storage and retrieval enforce scope; filtering only after an unscoped query is insufficient.
- Unknown, archived, suspended, omitted, or mismatched project identity fails closed.
- Vault-relative paths must remain beneath the approved project root and reject traversal and unsafe links.
- Secrets are rejected or redacted under Soma's existing memory policy and must not enter Markdown, catalog rows, events, or returned context.
- Cross-project relationships and sharing are out of scope until Soma has an explicit typed, revocable binding contract.

## Acceptance for the first slice

Production acceptance requires evidence for:

- atomic save and exact get across restart;
- idempotent repeated save;
- facts, decisions, documents, research, lessons, and questions;
- exact source references and locators;
- explicit supersession with preserved historical retrieval;
- strict sibling-project isolation for save, get, search, relationships, health, and rebuild;
- English and Persian round-trip plus same-language literal retrieval;
- external Markdown edit detection through rebuild or reconciliation;
- complete deletion and rebuild of the catalog from unchanged Markdown;
- interrupted or malformed rebuild reporting degraded rather than false healthy state;
- path traversal, symlink escape, malformed identity, duplicate identity, and secret rejection;
- bounded search results with stable continuation;
- existing repository knowledge and memory behaviour remaining compatible.

## Deferred work

The following are deliberate later batches:

- a multilingual semantic provider or in-process semantic adapter;
- automated claim extraction, deduplication, merging, or truth adjudication;
- normalized source-version, evidence, contradiction, relationship, and immutable revision tables;
- a content-addressed raw document archive and capture pipeline;
- graph traversal, advanced temporal/as-of reasoning, and cross-project sharing;
- filesystem watchers, cloud synchronization, OCR, web crawling, and automatic Obsidian link rewrites;
- importing private conversation history or existing owner vaults.

These may be added only from measured gaps. They must remain replaceable projections or bounded services beneath Soma's authority.

