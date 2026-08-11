# ChatGPT Normal-Chat Tool UX Modernization - Implementation Plan

Date: 2026-08-12  
Status: canonical execution plan; implementation not started  
Repository: `D:\Github\Soma`  
Branch at planning time: `lane/memory-integration-foundation-1`  
Planning HEAD: `24fa7774d97e8a04bed3ec79054ae9b66182fd39`

## 1. Objective

Modernize Soma's normal-Chat integration so that ChatGPT receives a truthful current Plugin/MCP contract and the interaction moves toward:

```text
understand
-> explain meaningful action
-> use Soma
-> validate
-> report coherently
```

rather than a stream of opaque generic tool calls.

The patch has four distinct concerns:

1. Human-facing MCP metadata: titles, trigger-first descriptions, invoking/invoked labels.
2. Contract truth: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`.
3. Descriptor observability: preserve `public_schema_hash`; add `public_descriptor_hash`.
4. Workflow behavior: Plugin/Skill only after metadata/topology A/B proves its value.

This work must not restore the retired Codex/Claude execution architecture, turn Hermes into a reasoning agent, redesign the task plane, rewrite MCP transport serialization, add UI widgets prematurely, or mix in the separate parallel-worker/subagent research.

## 2. Authoritative research inputs

The implementation must treat these as the evidence base:

```text
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

Research hierarchy:

- Iteration 5 is the latest candidate-contract authority.
- Earlier findings superseded by later iterations must not be reintroduced.
- `candidate-contract-c1.json` is the exact C1 topology/metadata authority.
- `golden-corpus-g01-g48.json` is the routing/safety evaluation authority.

## 3. Luna execution law

Every numbered micro-stage below is a separate Luna Max invocation.

Never give Luna `continue until finished`.

For every stage Luna must:

```text
READ specified evidence
VERIFY entry conditions
MAKE only stage-authorized changes
RUN exact validation
WRITE/RETURN acceptance report
STOP
```

Every stage has exactly one terminal state:

```text
ACCEPTED
BLOCKED
FAILED
```

If observed state differs from the plan, Luna must stop with `BLOCKED` and report:

```text
expected state
observed state
exact discrepancy
affected files/symbols
safest options
```

Luna must not resolve architectural discrepancies by improvisation.

Global prohibitions unless a stage explicitly authorizes them:

- no push;
- no connector refresh;
- no server restart;
- no Plugin installation;
- no dependency upgrade;
- no FastMCP `ToolTransform`;
- no FastMCP Tool Search;
- no unrelated refactor;
- no automatic wiki refresh;
- no canonical-memory mutation;
- no touching unrelated owner work;
- preserve unrelated work;
- never redefine an existing compatibility field to mean something new.

## 4. Phase P0 - Research baseline

### P0.1 - Normalize research evidence

Purpose: create an internally consistent implementation starting point before production code changes.

Entry state:

```text
repo:   D:\Github\Soma
branch: lane/memory-integration-foundation-1
HEAD:   24fa7774d97e8a04bed3ec79054ae9b66182fd39
```

Tasks:

1. Read Iterations 1-5 and the C1 contract/corpus.
2. Reconcile the final bug ledger.
3. Preserve these corrected conclusions:

```text
public_schema_hash
    not a bug
    retain exact existing input-contract semantics

public_descriptor_hash
    missing additive identity
    implementation target

DOC-001
    canonical-memory audit incorrectly says description changes move public_schema_hash
    correct that statement
```

No production Python change in this stage.

Endpoint:

- research bundle internally consistent;
- DOC-001 corrected;
- no tracked production source changed;
- acceptance report created;
- STOP.

### P0.2 - Preserve research baseline

Create one local commit containing only the tool-UX research artifacts and DOC-001 correction.

Do not include unrelated owner work such as:

```text
docs/CANONICAL_PROJECT_MEMORY_CONTRACT.md
```

No push.

Endpoint: one local research-baseline commit; STOP.

## 5. Phase B - 32-tool truthful metadata candidate

Candidate B preserves the current 32-tool topology. This isolates metadata/annotation behavior from topology changes.

### B1 - Create one public metadata authority

Create:

```text
soma/public_tool_metadata.py
```

This becomes the sole authoritative registry for public ChatGPT/MCP presentation metadata.

It must contain exactly one record for every existing name in `PUBLIC_GATEWAY_NAMES`.

Each record must contain:

```text
name
title
description
invoking
invoked
annotations:
    readOnlyHint
    destructiveHint
    idempotentHint
    openWorldHint
```

Rules:

- every description begins `Use this when`;
- invoking/invoked labels are <= 64 characters;
- all four annotation keys are explicit;
- metadata comes from the final Iteration-4/5 semantic audit, not generic old READ/WRITE assumptions.

Mandatory conservative B values for mixed gateways:

```text
knowledge_query   R=false D=false I=false O=false
knowledge_action  R=false D=true  I=false O=false
ssh_query         R=false D=false I=false O=true
docker_action     R=false D=true  I=false O=true
cloudflare_action R=false D=true  I=false O=true
trading_query     R=false D=false I=false O=true
```

Mandatory standalone corrections include:

```text
repo_preview R=false D=false I=false O=false
repo_apply   R=false D=true  I=false O=false
cancel_run   R=false D=true  I=false O=false
run_start    R=false D=true  I=false O=true
ssh_action   R=false D=true  I=false O=true
```

Create:

```text
tests/test_public_tool_metadata.py
```

Hard assertions:

```text
metadata keys == PUBLIC_GATEWAY_NAMES
count == 32
all titles non-empty
all descriptions start "Use this when"
all invoking/invoked <= 64 chars
all four annotation keys present
known defect cases have exact expected values
no unknown public tool exists
```

Do not wire metadata into FastMCP in B1.

Endpoint:

```text
metadata registry exists
32/32 records valid
live MCP unchanged
new tests pass
STOP
```

### B2 - Add exact descriptor identity

Keep existing `public_schema_hash` unchanged in meaning:

> deterministic identity of public tool names plus effective advertised input schemas.

Add:

```text
public_descriptor_hash
```

Definition:

> SHA-256 of the exact served MCP `tools/list` descriptor snapshot, sorted deterministically by tool name and JSON keys.

Descriptor source must be equivalent to:

```python
tool.to_mcp_tool().model_dump(
    mode="json",
    by_alias=True,
    exclude_none=False,
)
```

Do not normalize away FastMCP metadata. If the client receives/caches a field, descriptor identity should observe it.

Canonicalization:

```text
sort tools by name
JSON sort_keys=true
compact separators
ensure_ascii=false
SHA-256
```

Implementation seam:

- extend the existing discovery pass around `server.refresh_public_contract_hash()`;
- one discovery pass should populate both input-contract and descriptor identity;
- maintain separate caches;
- do not add another full discovery pass only for descriptor hashing.

Expose `public_descriptor_hash` through:

```text
system_query(operation="capabilities")
system_query(operation="capability_identity")
```

Add request field:

```text
expected_public_descriptor_hash
```

Descriptor mismatch must produce:

```text
connector_public_descriptor_hash
connector_refresh_required = true
```

Descriptor mismatch alone must not imply `restart_required=true`.

Add `public_descriptor_hash` to `discovery_cache_generation` input.

Do not redefine:

```text
server_build_hash
schema_hash
capability_epoch
public_schema_hash
```

Do not stamp `public_descriptor_hash` onto every normal Soma tool result. It is discovery/connection identity, not result-data compatibility.

Required tests:

```text
unchanged discovery -> same descriptor hash
title mutation -> descriptor hash moves
description mutation -> descriptor hash moves
annotation mutation -> descriptor hash moves
invocation meta mutation -> descriptor hash moves
input schema mutation -> public_schema_hash and public_descriptor_hash both move
metadata-only mutation -> public_schema_hash does not move
three fresh equivalent discovery passes -> identical descriptor hash
```

Endpoint: identity tests pass; public surface not yet metadata-activated; STOP.

### B3 - Wire registry metadata into FastMCP

Activate the registry in source, but do not restart the running service.

Server-registered tools:

Use existing seam:

```text
server._register_public_tool()
```

Before normal FastMCP registration / `FlatGatewayTool.from_function(...)`, merge the metadata registry entry for the exact public tool name into FastMCP registration kwargs.

Do not alter:

```text
FlatGatewayTool
flatten_request_input_schema
argument normalization
result transport
handlers
execution paths
```

Knowledge tools bypass `server._register_public_tool`.

Therefore `knowledge_tools_integration.register_knowledge_tools()` must fetch the same central registry metadata for:

```text
knowledge_query
knowledge_action
```

There must not be a second copy of their human-facing metadata in that module.

Old generic annotation constants may remain for internal/non-public tools, but they must no longer decide the public descriptor where the central registry applies.

Hard regression requirements:

```text
tool count == 32
tool names exactly unchanged
operation inventory exactly unchanged
input schemas exactly unchanged
output schemas exactly unchanged
public_schema_hash unchanged from baseline
```

Expected baseline public schema hash:

```text
84d0af8b66d7df990320268ba905bf536cbb2722dfabf6cda30aaa5e93f9012c
```

If B changes this hash: `BLOCKED`. Do not update the expected value to make tests pass.

Descriptor assertions for all 32 tools:

```text
title != null
description == registry description
annotations == registry annotations
_meta["openai/toolInvocation/invoking"] exists
_meta["openai/toolInvocation/invoked"] exists
```

Endpoint: local discovery contract passes; STOP.

### B4 - Regression and compatibility gate

Run focused tests first:

```text
tests/test_public_tool_metadata.py
tests/test_capabilities.py
tests/test_mcp_action_discovery.py
tests/test_gateway_benchmark.py
```

Then all affected MCP/public-contract tests, then the full repository suite if focused tests pass.

Also run:

```text
scripts/research_chatgpt_tool_ux_eval.py
```

against C1 as a regression reference.

Hard rejection conditions:

```text
tool count != 32
public_schema_hash moves
input/output schema changes
FlatGatewayTool behavior changes
content[].text compatibility changes
structuredContent changes
public operation inventory changes
direct-call behavior changes
retired tool reappears
FastMCP dependency changes
```

Create:

```text
docs/CHATGPT_NORMAL_CHAT_TOOL_UX_B_SOURCE_ACCEPTANCE_2026-08-12.md
```

Record:

```text
source HEAD
server_build_hash
schema_hash
public_schema_hash
public_descriptor_hash
32 tool names
tests
exact changed files
no activation statement
```

Endpoint: Candidate B accepted at source level; STOP.

### B5 - Commit Candidate B

Create one local commit containing only validated Candidate-B implementation/test/docs files.

No C1 topology implementation.
No Plugin package.
No push.

Expected scope includes only files such as:

```text
soma/public_tool_metadata.py
soma/server.py
soma/gateway_models.py
soma/knowledge_tools_integration.py
relevant tests
B source-acceptance document
DOC-001 correction if not already committed
```

Endpoint: local B commit created; unrelated work preserved; STOP.

## 6. Live Gate A - Capture existing ChatGPT baseline

This is not a Luna stage.

Before activating B, normal ChatGPT must capture Variant-A behavior using a safe subset of G01-G48.

Do not execute destructive Cloudflare, broker/trading, SSH-root, Docker-prune, repository-delete, or other real high-consequence mutations merely for benchmarking.

Record:

```text
selected public tool
selected operation
unnecessary api_tool calls
unnecessary Soma calls
visible tool-card label
explanation before meaningful action
final coherent result
routing failures
no-tool correctness
latency
```

Freeze baseline evidence before changing the live connection.

## 7. B6 - Activate Candidate B on Soma

Requires explicit owner authorization.

This is one Luna stage.

Luna may only:

1. verify source HEAD equals the accepted B commit;
2. verify no unexpected running/queued work makes restart unsafe;
3. restart Soma exactly once using the established service procedure;
4. verify process/build identity;
5. perform local MCP discovery;
6. verify the public MCP endpoint advertises the same descriptor identity.

Luna may not refresh ChatGPT.

Expected local state:

```text
tool count = 32
public_schema_hash =
84d0af8b66d7df990320268ba905bf536cbb2722dfabf6cda30aaa5e93f9012c

public_descriptor_hash = new Candidate-B value
32 titles non-null
32 invocation metadata pairs present
annotations == Candidate-B registry
```

Hard requirement:

```text
localhost public_descriptor_hash
==
public transport public_descriptor_hash
```

If not: `BLOCKED`; do not refresh ChatGPT.

Endpoint: source -> running Soma -> public transport converged; STOP.

## 8. Live Gate B - ChatGPT Refresh

Owner/ChatGPT-side only; not Luna.

1. Perform one explicit connection Refresh.
2. Verify refreshed connection metadata.
3. Start a new conversation.
4. Do not judge B from an old conversation that may retain cached connection state.

## 9. B7 - Live Candidate-B evaluation

Run the same safe corpus subset used for A.

B must not win merely because it is newer.

Hard non-regression requirements:

```text
no-tool correctness
read vs mutation routing
argument correctness
canonical-memory routing
unsupported-push behavior
answer completeness
```

B should improve at least one meaningful UX dimension:

```text
meaningful visible titles/status
fewer pointless discovery/tool calls
better routing
less generic host presentation where metadata is honored
better explain -> act -> report behavior
```

Expected B weakness:

Broad mixed gateways remain conservative. If this creates excessive confirmation/framing for harmless operations, record it as evidence for C1. Do not make the annotations dishonest again.

Terminal decision only:

```text
B_ACCEPT
B_ACCEPT_WITH_C1_REQUIRED
B_REJECT
```

STOP.

## 10. Phase C1 - 43-tool selective semantic split

Do not execute C1 unless B evidence justifies it or a confirmed contract contradiction cannot be acceptably represented in B.

Authoritative contract:

```text
docs/chatgpt-tool-ux/candidate-contract-c1.json
contract version: chatgpt-tool-ux.c1.v1
tool count: 43
```

Do not redesign C1 from memory.

### C1.1 - Define typed subset contracts

Reuse existing underlying operation models.

Create dedicated typed subset unions/wrappers only for these six proven mixed source gateways:

```text
knowledge_query
knowledge_action
ssh_query
docker_action
cloudflare_action
trading_query
```

Preserve:

```text
same discriminator
same field constraints
same defaults
same validators
same handler payload shape
```

Continue using `FlatGatewayTool` as the flattening mechanism.

Hard proof:

```text
no public request wrapper reappears
subset operation enum exact
no source operation lost
no source operation duplicated
```

STOP.

### C1.2 - Add the C1 public boundaries

Implement exactly the operation membership in `candidate-contract-c1.json`.

Key additional/narrowed surfaces include:

```text
memory_query
memory_context
research_query
research_context
memory_action
ssh_prepare
ssh_probe
docker_destructive_action
cloudflare_destructive_action
trading_journal_query
trading_market_query
trading_companion_sync
```

Some old broad names remain as narrowed surfaces, so final public count must be exactly 43.

Do not invent another split.

Each wrapper delegates to the existing implementation path.

No duplicated execution/service implementations.

STOP.

### C1.3 - Update inventories and deterministic tests

Update public inventories and explicit enumeration tests, including:

```text
soma/public_gateway_inventory.py
soma/cf1_gateway_operation_inventory.py
tests/test_mcp_action_discovery.py
tests/test_gateway_benchmark.py
```

and any other intentional complete-surface assertions.

Required:

```text
43 unique public tool names
every source operation covered exactly once
zero missing operations
zero duplicated operations
all schemas Draft 2020-12 valid
all C1 metadata exact
```

Run:

```text
scripts/research_chatgpt_tool_ux_eval.py
```

Reference measurements:

```text
tool_count             43
descriptor_bytes       approximately 169,548
input_schema_bytes     approximately 118,718
```

Do not fail solely because legitimate serialization changes move raw byte count slightly. Do fail on semantic/schema partition differences.

STOP.

### C1.4 - C1 source acceptance

Run affected tests and the full suite.

Create source acceptance evidence.

No restart in this stage.

Create one local C1 commit.

No push.

STOP.

### C1.5 - Activate and compare B vs C1

Use the same convergence ladder:

```text
source
-> running local MCP
-> public MCP transport
-> owner-approved ChatGPT Refresh
-> new conversation
```

Run paired B/C1 corpus.

C1 must justify its +21.8% raw descriptor increase through measurable benefit.

Pay special attention to:

```text
canonical memory routing
context-packet statefulness
SSH read vs preparation vs external probe
Docker ordinary vs destructive
Cloudflare update vs destructive
Trading local vs provider vs companion-sync
confirmation false positives
confirmation false negatives
```

Terminal decision only:

```text
KEEP_B
PROMOTE_C1
```

STOP.

## 11. Phase D - Plugin + soma-engineering Skill

Only after the winning MCP surface is known.

This phase addresses conversational sequencing, not safety authority.

Before implementation, re-verify the then-current official OpenAI Plugin/Skill packaging contract.

Candidate package shape:

```text
.codex-plugin/plugin.json
.app.json
.mcp.json
skills/
  soma-engineering/
    SKILL.md
```

Seed Skill source:

```text
docs/chatgpt-tool-ux/soma-engineering-skill-draft/SKILL.md
```

The Skill should teach:

```text
establish current state
briefly explain meaningful intended action
inspect first when state matters
preview/apply where required
never invent commit/push authority
validate mutations
retrieve durable run evidence
use canonical project memory correctly
report one coherent result
stop on unresolved ambiguity
```

The Skill is guidance, not authorization.

Soma remains authoritative for:

```text
validation
authorization
idempotency
execution
evidence
destructive boundaries
```

Run live comparison:

```text
winning MCP surface without Skill
vs
same MCP surface with Skill
```

If the Skill does not materially improve:

```text
explain -> act -> validate -> report
```

then do not ship it merely because Plugin packaging is newer.

## 12. Phase E - Optional escalation only

Not part of the initial patch.

Investigate only if B/C1/D leave a measured defect.

Possible routes:

```text
focused modular MCP views
compact engineering status/result UI
transport modernization
```

FastMCP Tool Search remains rejected for the normal Soma surface unless its semantics materially change, because the tested version collapses tool-level safety annotations behind generic proxy tools.

Generic FastMCP `ToolTransform` remains rejected unless its flat discriminated-union behavior changes, because the tested version destroyed Soma's operation branches.

## 13. Separate follow-on research: single-head parallel workers

Track separately from this patch:

```text
Sol / ChatGPT reasoning head
-> bounded parallel workers
-> structured evidence
-> Sol synthesis
```

Do not mix this into the normal-chat tool UX implementation. Otherwise A/B attribution becomes impossible.

Potential later worker classes:

```text
execution_worker
retrieval_worker
scout_worker
future reasoning_worker
```

Hermes remains a tool/execution layer in the current architecture, not an independent reasoning head.

## 14. Final definition of done

This project ends when one promoted normal-Chat architecture has:

```text
truthful MCP descriptors
stable public_schema_hash semantics
exact public_descriptor_hash
deterministic regression coverage
validated normal-Chat routing
validated no-tool behavior
safe destructive/external framing
correct canonical-memory routing
coherent explain -> act -> validate -> report behavior
documented source/runtime/public/ChatGPT convergence
rollback evidence
no unapproved push
```

Promotion ladder has hard endpoints:

```text
B good enough
    -> STOP

B insufficient
    -> C1

C1 wins
    -> STOP unless workflow behavior still needs D

D improves workflow materially
    -> promote D and STOP

D does not
    -> keep winning B/C1 and STOP

E
    -> only from a newly measured defect
```

Do not continue into later phases merely because they exist.

## 15. First execution handoff

The first Luna Max prompt must cover **P0.1 only**.

Do not give Luna this full plan as an instruction to execute end-to-end.

The full plan is reference authority; each Luna invocation must receive one bounded micro-stage with its exact entry conditions, allowed changes, validation, and hard stop.
