# Soma External Research Knowledge Platform

**Status:** corrected production foundation implemented after commit `df83a6a`.

## Purpose

Soma preserves completed, owner-requested research so ChatGPT, Claude Code, and
Hermes can recover the same source-grounded project understanding across
conversations. Soma does not crawl, schedule research, discover sources
autonomously, or decide that a conversation should be saved.

The operating workflow is explicit:

1. Arash asks a controller to research a subject.
2. The controller researches normally.
3. Arash explicitly asks to preserve the result.
4. The controller manually imports source captures and submits a structured
   research packet.
5. Soma archives original artifacts, records reviewed research state, and
   optionally projects the artifacts into RAGFlow.
6. A later controller retrieves citations, claims, contradictory evidence,
   questions, candidates, and decisions through the same Soma contract.

## Ownership

```text
explicit URL capture / local file / ChatGPT packet
                         |
                         v
               canonical manual importer
                         |
             +-----------+-----------+
             v                       v
  content-addressed archive   SQLite research overlay
  immutable original bytes    provenance and reviewed state
             |                       |
             +-----------+-----------+
                         |
                         v
                replaceable RAGFlow
       parsing, OCR, chunks, embeddings, retrieval
                         |
                         v
              reproducible context packet
```

- The content-addressed raw archive is canonical for original PDFs, webpage
  captures, documents, datasets, and research-packet artifacts.
- The project-scoped SQLite overlay is canonical for source identity and
  versions, provenance, claims, evidence, questions, candidates, decisions,
  generated summaries, relationships, analysis records, audit events, and
  supersession.
- RAGFlow is disposable. It owns parsing, OCR, chunks, embeddings, retrieval,
  reranking, and derived citations.
- Markdown and Obsidian are optional owner-readable projections. They do not
  rebuild or override the research overlay.
- Soma owns exact ProjectScope identity, routing, lifecycle, health, bounded
  public gateways, and controller access.

The earlier `soma.knowledge` Markdown catalog remains a compatible legacy
projection for generic notes and existing clients. It is not the authoritative
research platform.

## Raw archive

Each project receives an isolated archive beneath Soma's ignored run state:

```text
runs/research/projects/<project-id-hash>/raw/
├── objects/
│   └── <sha-prefix>/<sha256>
└── staging/
```

Imports stream into staging, calculate SHA-256, flush and fsync, verify any
existing object, and atomically replace the final digest-only path. Identical
bytes reuse one object even when filenames differ. Original name, media type,
size, URI, retrieval time, and version lineage live in the overlay; source
bytes never enter SQLite or Git.

Supported manual inputs are:

- a local file;
- an already captured artifact;
- caller-supplied captured text associated with a URL;
- an artifact referenced by a completed research packet.

Supplying a URL does not authorize Soma to crawl or silently fetch it.

## Structured research overlay

The overlay stores these project-scoped entities:

- logical `sources` and immutable `source_versions`;
- `research_packets` and packet idempotency;
- reviewed or proposed `claims`;
- `evidence_links` with support, contradiction, qualification, replication,
  and failed-replication roles;
- exact quote, quote hash, archive hash, locator, page range, chunk
  fingerprint, and optional disposable RAGFlow chunk identity;
- `research_questions` and missing evidence;
- `design_candidates`;
- accepted, rejected, deferred, under-review, and superseded
  `design_decisions`;
- bounded `experiment_proposals` that remain separate from external results and
  accepted decisions;
- non-authoritative `generated_summaries` with review state;
- typed `relationships`;
- `analysis_runs`, audit events, and reproducible context-packet manifests.

Packet preservation validates every project and reference before one SQLite
transaction. Repeating the packet idempotency key returns the same packet and
entity identities. Supporting and contradictory evidence coexist; neither is
silently overwritten.

## RAGFlow boundary

`RagFlowGateway` is a replaceable typed interface. Source versions may progress
through stored, uploaded, parsing, indexed, failed, and retry states. RAGFlow
credentials, dataset configuration, and live deployment remain external to the
canonical archive and overlay.

Rebuild verifies every raw object before upload, recreates only derived
documents/chunks, and updates disposable mappings. It must not change reviewed
claims, evidence, questions, candidates, decisions, or audit history. Live
long-running rebuilds must use Soma's existing task/run controller rather than
introducing another worker or lease authority.

An unconfigured RAGFlow adapter is reported as `not_configured`; this does not
mean canonical research has been lost.

## Public controller contract

The existing `knowledge_action` and `knowledge_query` MCP gateways remain the
only public knowledge tools.

Research write operations:

- `import_research_source`
- `preserve_research_packet`
- `rebuild_research_index`

Research read operations:

- `get_research_source`
- `get_claim_evidence`
- `list_research_questions`
- `list_research_decisions`
- `search_research`
- `build_context_packet`
- `research_health`

Every operation requires the exact active `project_id` and bound `repo_name`.
ChatGPT, Claude Code, and Hermes use the same request models; controller identity
is audit metadata, not a different storage path.

Legacy wiki and Markdown operations remain compatible and are explicitly
separate from the research archive.

## Context packets

A context packet joins:

- ordered RAGFlow passages;
- exact source and source-version citations;
- archive SHA-256 and durable chunk fingerprints;
- reviewed claims;
- supporting, contradictory, qualifying, replication, and failed-replication
  evidence;
- unresolved questions and missing evidence;
- related candidates;
- previous decisions and supersession;
- stable entity identities and a canonical packet SHA-256.

Retrieved text and generated summaries are derived material. They do not become
reviewed claims merely because they appear in a packet.

## Layered health and recovery

Health is reported independently:

- archive: empty, healthy, or corrupt after size/hash verification;
- overlay: schema/count/ingestion health;
- index: not configured, empty, healthy, partial, or degraded;
- Markdown projection: legacy-compatible and non-authoritative.

The overlay supports checksummed JSONL export and all-or-nothing restore into an
empty project database. Raw artifacts are backed up and restored separately
using their archive paths and hashes. Deleting RAGFlow reduces retrieval
convenience only; archive and reviewed overlay state remain intact.

## Deliberate non-goals

- autonomous crawling or discovery;
- scheduled research or mass ingestion;
- custom PDF parsing, OCR, embeddings, vector storage, or reranking;
- automatic claim extraction or truth adjudication;
- automatic promotion of generated content to reviewed knowledge;
- a second task, worker, lease, cancellation, or repository-lock authority;
- storing original source blobs in SQLite, Markdown, or Git.

## Acceptance evidence

Focused acceptance proves:

- idempotent repeated imports;
- changed bytes create a traceable successor version;
- immutable SHA-256-verifiable raw artifacts;
- no source blobs in SQLite;
- exact evidence with support and contradiction;
- restart-safe questions, candidates, decisions, and review state;
- sibling-project isolation;
- one explicit ChatGPT preservation workflow;
- one reproducible later context packet;
- deletion and rebuild of a replaceable fake RAGFlow index without canonical
  overlay loss;
- checksummed overlay export and restore;
- compatibility with the existing knowledge gateway and ProjectScope contract.
