# Candidate-B Source Acceptance

## Status

- Status: `SOURCE ACCEPTED`
- Explicit boundary: `SOURCE ACCEPTED, NOT LIVE ACTIVATED`
- Batch: B4 regression and compatibility gate only
- B1-B3 remain uncommitted on top of the required source HEAD
- No Candidate-B production correction was required during B4

## Source identity

- Source HEAD: `e8f1a19db091f9b6293289857b9652809c523e52`
- Branch: `lane/memory-integration-foundation-1`
- `server_build_hash`: `a546bc9a0a0b3068e4948aca5ca2bf0ad5e720eb4488ce8a93b2494e70bc3c3b`
- `schema_hash`: `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`
- `public_schema_hash`: `84d0af8b66d7df990320268ba905bf536cbb272dfabf6cda30aaa5e93f9012c`
- `public_descriptor_hash`: `1d502b7e1f0f7d8feb3ccb6c00896c3ee0ef2346408dfccde1b7c1fdb4d871bb`
- FastMCP: `3.4.2`; `pyproject.toml` still declares the existing `fastmcp` dependency and has no diff

## Public surface

The source discovery surface contains exactly 32 tools. The exact names are:

```json
[
  "cancel_run",
  "cloudflare_action",
  "cloudflare_query",
  "docker_action",
  "docker_query",
  "knowledge_action",
  "knowledge_query",
  "repo_apply",
  "repo_commit",
  "repo_preview",
  "repo_query",
  "run_query",
  "run_start",
  "ssh_action",
  "ssh_inspect",
  "ssh_query",
  "supervisor_action",
  "supervisor_query",
  "system_action",
  "system_query",
  "task_action",
  "task_query",
  "trading_action_submit",
  "trading_companion_action",
  "trading_query",
  "trading_runtime_control",
  "trading_signal_cancel_before_entry",
  "trading_signal_get",
  "trading_signal_list",
  "trading_signal_submit",
  "workflow_action",
  "workflow_query"
]
```

The unchanged compatibility identities are:

- Operation inventory hash: `a6f31b3275f074d0660ba4aa48f3886cce2093bf5847cf0e3eae172afae92377`
- Name-sorted input-schema digest: `bb32b7c07dba1d71f90dda396ed11e92ddf1192e9c76460f6d0bc0ed3ea0b176`
- Name-sorted output-schema digest: `247aa7e6a7958ca51decb7f8e5a68119315ed949a54315e4b671a8e35ad91bde`
- Pre-B3 descriptor hash: `4480a27354c0f140ed2931904dfe1c786f3c8c30b01ca7e69384965ecaaa1c49`
- Candidate-B descriptor hash: `1d502b7e1f0f7d8feb3ccb6c00896c3ee0ef2346408dfccde1b7c1fdb4d871bb`

All 32 served descriptors match `PUBLIC_TOOL_METADATA` for title, description,
annotations, and both OpenAI invocation metadata fields. Titles are non-empty,
FastMCP-owned metadata is preserved, and no retired public tool reappeared.
Three fresh `.venv` processes each reported tool count `32`, the exact public
names, `public_schema_hash` `84d0af8b...`, the exact Candidate-B descriptor hash,
and metadata parity for all 32 records.

## Exact Candidate-B files

These are the changed Candidate-B implementation, test, and plan files present
on top of the source HEAD before this acceptance record was added:

- `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_IMPLEMENTATION_PLAN_2026-08-12.md`
- `soma/public_tool_metadata.py`
- `soma/server.py`
- `soma/knowledge_tools_integration.py`
- `tests/test_public_tool_metadata.py`
- `tests/test_public_descriptor_identity.py`
- `tests/test_public_metadata_wiring.py`
- `tests/test_mcp_action_discovery.py`
- `tests/test_gateway_benchmark.py`
- `tests/test_knowledge_tools_integration.py`
- `tests/test_memory_gateway_operations.py`
- `tests/test_tool_gateway_models.py`

This file is the B4 source acceptance record. No file was staged or committed.

## Validation results

Focused Candidate-B and affected MCP/public-contract suite:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q tests/test_public_tool_metadata.py tests/test_public_descriptor_identity.py tests/test_public_metadata_wiring.py tests/test_capabilities.py tests/test_mcp_action_discovery.py tests/test_gateway_benchmark.py tests/test_knowledge_tools_integration.py tests/test_memory_gateway_operations.py tests/test_tool_gateway_models.py tests/test_mcp_flat_input_contract.py
```

Result: `351 passed in 289.20s (0:04:49)`.
This includes the full `tests/test_tool_gateway_models.py` run.

Complete repository suite:

```powershell
& .\.venv\Scripts\python.exe -m pytest -q
```

Result: `2707 passed, 35 skipped, 1 xfailed in 1091.48s (0:18:11)`.
The run terminated cleanly. No material warning summary was emitted, and no
unexpected xpass was reported.

Offline C1 research/reference evaluator (C1 was not activated or implemented):

```powershell
& .\.venv\Scripts\python.exe scripts/research_chatgpt_tool_ux_eval.py
```

Result: exit code `0`; `failed_checks: []`; golden corpus count `48`;
baseline tool count `32`, descriptor bytes `146854`, input-schema bytes
`112720`; frozen C1 tool count `43`, descriptor bytes `169548`, input-schema
bytes `118718`; C1 candidate descriptor SHA-256
`63e1ff6c3a3f85a83713f614720229757b8a82747708ffd3f1b1f8440ad400d7`.

Supplemental checks:

- `ruff check` on all changed Python files: passed.
- `ruff format --check` on the four new Candidate-B Python files: passed.
- `python -m pip check`: `No broken requirements found.`
- `git diff --check`: passed; Git emitted only existing LF-to-CRLF conversion warnings.
- Protected-file diff check: empty; no protected file was modified, staged,
  deleted, renamed, or incorporated.

## Compatibility gate evidence

- Public tool count: pass, exactly `32`.
- Public names: pass, exact match to `PUBLIC_GATEWAY_NAMES`.
- Public operation inventory: pass; hash unchanged at
  `a6f31b3275f074d0660ba4aa48f3886cce2093bf5847cf0e3eae172afae92377`.
- `public_schema_hash`: pass; unchanged at
  `84d0af8b66d7df990320268ba905bf536cbb2722dfabf6cda30aaa5e93f9012c`.
- Input and output schemas: pass; both name-sorted digests unchanged.
- `FlatGatewayTool` behavior: pass; all previously flattened gateways remain
  flattened and `cancel_run` remains the already-flat exception.
- Request flattening: pass; the advertised schemas remain flat, while the
  legacy wrapped call remains accepted by the existing regression tests.
- Direct Python-call behavior: pass.
- `structuredContent` behavior: pass.
- `content[].text` compatibility: pass; serialized text decodes to the same
  structured payload.
- Retired public tools: pass; none reappeared.
- FastMCP dependency/version: pass; unchanged at `3.4.2`.
- Served descriptor identity: pass for all 32 records; the exact current
  Candidate-B descriptor hash is deterministic across three fresh processes.

## Newline diagnostics

The existing per-file conventions were preserved; no global normalization was
performed.

| File | CRLF | lone LF | bare CR |
| --- | ---: | ---: | ---: |
| `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_IMPLEMENTATION_PLAN_2026-08-12.md` | 0 | 966 | 0 |
| `soma/server.py` | 6979 | 0 | 0 |
| `soma/knowledge_tools_integration.py` | 0 | 1910 | 0 |
| `soma/public_tool_metadata.py` | 0 | 637 | 0 |
| `tests/test_public_tool_metadata.py` | 0 | 96 | 0 |
| `tests/test_public_descriptor_identity.py` | 0 | 307 | 0 |
| `tests/test_public_metadata_wiring.py` | 0 | 130 | 0 |
| `tests/test_mcp_action_discovery.py` | 0 | 1996 | 0 |
| `tests/test_gateway_benchmark.py` | 0 | 114 | 0 |
| `tests/test_knowledge_tools_integration.py` | 0 | 655 | 0 |
| `tests/test_memory_gateway_operations.py` | 0 | 689 | 0 |
| `tests/test_tool_gateway_models.py` | 3130 | 0 | 0 |
| `docs/CHATGPT_NORMAL_CHAT_TOOL_UX_B_SOURCE_ACCEPTANCE_2026-08-12.md` | 0 | 208 | 0 |

## Runtime and connector boundary

- Source implementation state: Candidate B is present in the uncommitted
  source tree above the required HEAD and has passed this source gate.
- Currently running Soma service state: the existing service was not restarted.
  The observed service processes are PID `30428` (with child PID `196`), started
  on 2026-08-10; they are not treated as Candidate-B evidence. No claim is made
  that the running service has Candidate B.
- ChatGPT connector state: no connector refresh or public endpoint activation
  occurred. The connector was not treated as having Candidate-B metadata.

## Unresolved risks and rollback boundary

- The intentional source/runtime/connector split remains unresolved until an
  owner-authorized later activation step; this is not a B4 source failure.
- A full changed-file Ruff format check reports seven pre-existing files would
  be reformatted. No formatting pass was applied because it would create broad
  unrelated churn and risk newline normalization; lint and the new Candidate-B
  files' format checks pass.
- No rollback was performed. If later authorized, the rollback boundary is the
  Candidate-B implementation, test, plan, and acceptance files listed here,
  without resetting, cleaning, amending, or changing HEAD and without touching
  the protected concurrent-work files.

No B5 commit, C1 implementation, server restart, endpoint activation, connector
refresh, push, wiki refresh, plugin/skill work, or canonical-memory mutation was
performed.
