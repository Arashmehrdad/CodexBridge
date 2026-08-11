# Soma Normal-Chat Tool UX — P0.1 Research Baseline Acceptance

Date: 2026-08-12
Stage: P0.1 - Freeze research evidence
Status: ACCEPTED
Scope: documentation/research baseline only

## 1. Scope

P0.1 reconciles the five historical normal-Chat Tool UX research iterations,
the Candidate C1 machine-readable contract, the G01-G48 corpus, the draft
`soma-engineering` Skill, the offline evaluator, the canonical implementation
plan, and the canonical-memory audit.

P0.1 does not authorize implementation. It creates a final research baseline,
corrects the one permitted DOC-001 statement in the canonical-memory audit,
and then stops. No live candidate is activated by this stage.

## 2. Starting repository, branch, and HEAD

```text
repository: D:\Github\Soma
branch:     lane/memory-integration-foundation-1
HEAD:       24fa7774d97e8a04bed3ec79054ae9b66182fd39
```

The observed repository, branch, and HEAD matched the required entry state.
The preflight found no merge/conflict state.

## 3. Files reviewed

All required inputs existed and were readable before editing:

- `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_IMPLEMENTATION_PLAN_2026-08-12.md`
- `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_1_2026-08-12.md`
- `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_2_2026-08-12.md`
- `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_3_2026-08-12.md`
- `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_4_2026-08-12.md`
- `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_5_2026-08-12.md`
- `docs/chatgpt-tool-ux/candidate-contract-c1.json`
- `docs/chatgpt-tool-ux/golden-corpus-g01-g48.json`
- `docs/chatgpt-tool-ux/soma-engineering-skill-draft/SKILL.md`
- `scripts/research_chatgpt_tool_ux_eval.py`
- `docs/CANONICAL_MEMORY_WORKFLOW_AUDIT_2026-08-04.md`

The plan and all five iterations agree that P0.1 is a research-baseline
stage and that no production implementation is authorized here. Candidate C1
and the evaluator are explicitly research-only, not live Soma behavior.

## 4. Final reconciled bug/risk ledger

### Confirmed

- **UX-001:** the current 32-tool live/research baseline has no human-readable
  titles.
- **UX-002:** OpenAI invocation status metadata is absent from the current
  public surface.
- **IDENTITY-001:** Soma lacks an exact full served-descriptor identity
  separate from `public_schema_hash`.
- **ROUTE-001:** current public descriptions are primarily
  implementation/control-plane language rather than modern user-trigger
  routing descriptions.
- **TEST-001:** existing tests do not fully protect human-facing descriptor
  metadata, descriptor identity, or model-routing behavior.
- **DEP-001:** FastMCP compatibility is proven by the research probes against
  3.4.2 while the dependency remains broadly/unboundedly declared. This is a
  reproducibility risk, not authority to upgrade or pin FastMCP in P0.1.
- **PLUGIN-001:** Soma has no repository-owned Plugin/Skill package that
  implements the researched normal-Chat workflow layer.
- **CACHE-001:** Soma cannot independently inspect ChatGPT's private cached
  connection snapshot. Explicit connection Refresh and fresh-conversation
  observation remain required for live acceptance.
- **ANNOT-001:** `repo_preview` is not truthfully read-only or idempotent
  because it creates durable preview/helper state.
- **ANNOT-002:** `knowledge_query` mixes pure reads with state-creating
  context-packet operations.
- **ANNOT-003:** `ssh_query` mixes pure local reads with state-creating
  preparation/probe operations.
- **ANNOT-004:** `trading_query` mixes local reads, provider-backed reads, and
  the stateful `companion_get(sync=true)` path.
- **SAFETY-001:** `docker_action` contains destructive operations while the
  generic historical annotation model advertises `destructiveHint=false`.
- **SAFETY-002:** `cloudflare_action` contains destructive/delete/secret-
  rotation operations while the generic historical annotation model
  advertises `destructiveHint=false`.
- `repo_apply` is destructive-capable.
- `cancel_run` is destructive lifecycle control.
- Unrestricted execution surfaces such as `run_start` and `ssh_action`
  cannot truthfully be assumed non-destructive or closed-world.

These confirmations are limited to findings supported by Iterations 1-5,
the machine-readable artifacts, or the reviewed audit. Other operation-name
suspicions remain review/A-B questions and are not promoted to confirmed
defects by P0.1.

### Corrected or superseded

- The earlier broad framing that `public_schema_hash` is itself a descriptor
  metadata bug is superseded. Its accepted meaning is the deterministic
  identity of the effective public input contract: public tool names and
  advertised input schemas.
- **DOC-001** is corrected in the canonical-memory audit. A description or
  metadata-only change does not move `public_schema_hash`; it may still
  require server activation and ChatGPT connector Refresh because advertised
  descriptor metadata is cached. The future/additive `public_descriptor_hash`
  is the intended identity for exact served descriptor changes.
- The Iteration-4 provisional two-way trading query split was corrected by
  Iteration 5: `companion_get(sync=true)` is stateful, so C1 has the separate
  `trading_companion_sync` surface and 43 tools rather than 42.
- The maximal 46-tool selective split remains historical research. C1 is the
  narrower 43-tool candidate with the measured +21.8% descriptor increase.
- Iteration-3's `HOST-01` correction remains in force: raw full-catalog bytes
  are not proven to equal per-turn ChatGPT context because the observed host
  dynamically loads relevant schemas.
- The 43/43 lexical diagnostic is only a lexical diagnostic. It is not a
  ChatGPT routing-accuracy result.

Historical iteration documents remain unchanged; superseded findings are
reconciled here rather than rewritten.

### Deferred or experimental

- Candidate C1 remains research-only and not live.
- FastMCP `ToolTransform` remains rejected for the tested form because it
  destroyed the flattened discriminated-union operation schema.
- FastMCP Tool Search remains rejected for the tested normal public form
  because it collapsed the catalog behind `search_tools`/`call_tool` and lost
  per-tool annotation semantics. These are research conclusions about the
  tested forms, not permanent prohibitions on every future implementation.
- Optional inline UI is deferred; current evidence does not justify it in the
  first patch.
- Focused modular MCP views are technically promising but deferred until a
  live A/B test shows a real reason to change topology for that purpose.
- A repo-owned Plugin plus `soma-engineering` Skill is a strong later
  candidate, but it must be evaluated after the MCP contract winner is known
  and must not replace Soma authorization or safety.
- Further lifecycle/safety splits, including conservative broad execution
  surfaces, remain live A/B/design work rather than P0.1 implementation.

### External or host boundaries

- ChatGPT owns the outer `api_tool` presentation and final tool-card
  rendering; Soma metadata cannot guarantee removal of host-owned cards.
- ChatGPT's private connector cache is not independently observable by Soma;
  Refresh plus a new conversation is required for live metadata acceptance.
- Plugin/Skill availability and installation depend on the target ChatGPT
  surface, account, plan, and workspace state and were not activated here.
- FastMCP 3.4.2 behavior is the tested compatibility point; the broad
  dependency declaration remains an unresolved reproducibility risk.

## 5. Confirmed Candidate-B research assumptions

Candidate B is the same 32-tool public topology with metadata and annotation
changes only. It is the first proposed live A/B candidate because it isolates
the value of truthful titles, trigger-first descriptions, invocation labels,
and conservative annotations from topology changes.

The research baseline supports these assumptions:

- FastMCP 3.4.2 and the existing `FlatGatewayTool` path preserve titles,
  annotations, arbitrary metadata, and the flattened input contract in the
  isolated probes.
- B must preserve the existing input-contract identity and must not change
  the current baseline `public_schema_hash`:
  `84d0af8b66d7df990320268ba905bf536cbb2722dfabf6cda30aaa5e93f9012c`.
- Metadata-only changes may move the future descriptor identity but do not
  move `public_schema_hash`.
- Broad mixed gateways require truthful conservative metadata in B:
  `knowledge_query` R=false/D=false/I=false/O=false;
  `knowledge_action` R=false/D=true/I=false/O=false;
  `ssh_query` R=false/D=false/I=false/O=true;
  `docker_action` R=false/D=true/I=false/O=true;
  `cloudflare_action` R=false/D=true/I=false/O=true;
  `trading_query` R=false/D=false/I=false/O=true.
- If B causes excessive confirmation or framing for harmless variants, that
  is evidence to evaluate C1, not permission to make annotations dishonest.

No B metadata was wired into the live server during P0.1.

## 6. Confirmed C1 research reference and metrics

Canonical research source:
`docs/chatgpt-tool-ux/candidate-contract-c1.json`

```text
contract version:                    chatgpt-tool-ux.c1.v1
status:                              research_candidate_not_live
source HEAD:                         24fa7774d97e8a04bed3ec79054ae9b66182fd39
FastMCP tested:                      3.4.2
tool count:                          43
descriptor bytes:                    169,548
input-schema bytes:                  118,718
candidate descriptor SHA-256:        63e1ff6c3a3f85a83713f614720229757b8a82747708ffd3f1b1f8440ad400d7
G01-G48 structural/golden checks:    48 / 48 passed
```

The offline evaluator is research-only. Its final lexical diagnostic was
43/43, but that result is not ChatGPT routing accuracy. A live A/B evaluation
of no-tool behavior, routing, arguments, safety framing, explanation, and
final reporting remains mandatory before selecting a winner.

## 7. Deferred architecture items

The next implementation decision may compare B and C1 only after their
research assumptions are reviewed and the required live gates are authorized.
The following are not part of P0.1:

- production metadata registry or FastMCP registration changes;
- `public_descriptor_hash` runtime implementation;
- C1 typed subset-union registration or public topology changes;
- Plugin packaging or Skill installation;
- optional UI/resource work;
- modular MCP server views;
- FastMCP dependency upgrades or pinning;
- server restart, public transport activation, ChatGPT Refresh, or live A/B.

## 8. DOC-001 correction made

The false statement in
`docs/CANONICAL_MEMORY_WORKFLOW_AUDIT_2026-08-04.md` said, in substance,
that changing gateway descriptions changes `public_schema_hash`.

Only that identity claim was corrected. The audit now states that:

- `public_schema_hash` tracks the effective public input contract;
- a description/metadata-only change does not move `public_schema_hash`;
- descriptor metadata changes can still require server activation and ChatGPT
  connector Refresh because the client caches advertised descriptor metadata;
- the future/additive `public_descriptor_hash` is intended to identify exact
  served descriptor changes.

No unrelated audit section or project-memory architecture conclusion was
rewritten.

## 9. Explicit non-actions

P0.1 performed no:

- production Python change;
- MCP registration change;
- public tool topology change;
- server restart;
- connector refresh;
- Plugin installation;
- runtime configuration change;
- canonical-memory mutation;
- commit;
- push.

P0.1 also did not execute P0.2 or any later stage, launch an agent, or alter
the historical research input files.

## 10. Git/worktree preservation evidence

Preflight status recorded the expected branch and HEAD and these pre-existing
untracked files, all of which were preserved:

```text
docs/CANONICAL_MEMORY_WORKFLOW_AUDIT_2026-08-04.md
docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md
docs/CHATGPT_NORMAL_CHAT_TOOL_UX_IMPLEMENTATION_PLAN_2026-08-12.md
docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_1_2026-08-12.md
docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_2_2026-08-12.md
docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_3_2026-08-12.md
docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_4_2026-08-12.md
docs/CHATGPT_NORMAL_CHAT_TOOL_UX_RESEARCH_ITERATION_5_2026-08-12.md
docs/chatgpt-tool-ux/candidate-contract-c1.json
docs/chatgpt-tool-ux/golden-corpus-g01-g48.json
docs/chatgpt-tool-ux/soma-engineering-skill-draft/SKILL.md
scripts/research_chatgpt_tool_ux_eval.py
```

The acceptance document and the narrow audit correction are the only paths
authorized by P0.1. The pre-existing SHA-256 values of the plan, all five
iterations, both JSON artifacts, the Skill draft, the evaluator, and
`docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md` were unchanged after the stage.
No file under `soma/` or `tests/` changed. No unexpected file was created or
modified by this stage.

## 11. P0.1 acceptance verdict

**ACCEPTED.** The required research bundle and implementation plan existed and
were readable; the historical findings were reconciled without rewriting
history; DOC-001 was corrected narrowly; this acceptance baseline was created;
and post-edit validation proved the write boundary stayed within the two
authorized documentation paths. P0.1 does not authorize implementation and
the stage stops here.

## 12. Next stage

P0.2 - Preserve research bundle
