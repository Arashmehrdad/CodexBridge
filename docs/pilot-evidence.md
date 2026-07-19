# CodexBridge Real-Project Pilot Evidence

This log records representative post-H1 use before any broad Roadmap V3 redesign. Entries are factual observations, not automatic repair requests.

Each entry records the timestamp, project and expected outcome, repository or build identity, run or tool identities, exact failure, lost or duplicated work, recovery, attribution, reproduction frequency, and retained artifacts.

## 2026-07-19 22:35 Europe/London — OP1 pilot initialization and ordinary validation

- **Project:** CodexBridge.
- **Expected outcome:** exercise ordinary repository validation through the durable permissive connector, attempting the existing parallel PowerShell-group capability first and preserving a serial recovery path.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; starting HEAD `4cad24b6b64aaac568749451ad8e86b87519d6d3`; clean worktree; no active or queued CodexBridge runs; no repository locks.
- **Coordination inspection:** active durable runs and locks were empty. The public connector exposes supervisor and workflow status only by known identity, so no unidentified active supervisor or workflow was discovered through those surfaces.
- **Attempted operation:** two independent pytest commands requested through `run_start(operation="powershell_group")` with requested concurrency `2`, repository lock policy `none`, and continue-all failure policy.
- **Exact failure:** the public gateway rejected the request before durable-run creation with `Parallel PowerShell execution is disabled`.
- **Lost or duplicated work:** none. No run was accepted and no repository mutation occurred.
- **Recovery:** continued through the ordinary serial allowlisted pytest path. Durable run `20260719T213529Z_project_command_c0679d22` completed `tests/test_hermes_companion_client.py` with `6 passed in 1.06s`, empty stderr, no changed files, and a clean branch status.
- **Attribution:** current live configuration/capability availability, not a demonstrated durability defect. X2A implementation remains historical baseline; this observation does not yet prove a code regression.
- **Reproduction frequency:** one attempt in the pilot.
- **Artifacts:** the accepted serial run directory and published durable result for `20260719T213529Z_project_command_c0679d22`; connector rejection text retained in the initiating conversation.
- **Disposition:** observe. Do not repair or expand architecture unless this blocks representative work repeatedly or contradicts an intentionally enabled live profile.

## 2026-07-19 23:10 Europe/London — Hermes-backed connected-MCP pilot

- **Project:** CodexBridge.
- **Expected outcome:** exercise the pinned Hermes companion and repository-owned connected-MCP fixture through an ordinary durable permissive PowerShell run, without loading a Hermes model-agent loop or mutating tracked repository content.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; HEAD `9b734d0607d5e53ce581b783360441796bee64`; clean worktree; no active or queued runs and no repository locks before launch.
- **Initial invocation correction:** run `20260719T220955Z_executable_profile_03a77ef2` failed before Python execution because the PowerShell profile treated the executable path as a `-File` target and required a `.ps1` suffix. Exit code `64`; protected stdout was empty; protected stderr SHA-256 `a1d70a6491e3a12a824aa02011bcb24d347c46e92e91a06e6ec13fa795797abc`. No repository or external mutation occurred.
- **Successful operation:** durable run `20260719T221015Z_executable_profile_8851e78c` invoked the same harness through explicit `pwsh -Command` semantics and completed in `7.47` seconds with exit code `0`.
- **Hermes identity:** registry generation `89`; effective schema hash `a308c1820ae7e601a71cedc6ff27be866c5d40221070244b826ca657b7f2aa78`; `model_runtime_initialized: false`.
- **Tool identity:** `mcp__codexbridge_fixture__echo_fixture`; tool-schema hash `87fb4050ba48900df327f896d8fcae53dfca0203e8eb6350352f016b380b2074`.
- **Verified result:** source `codexbridge-disposable-mcp`; value `durable-mcp-gate`.
- **Lost or duplicated work:** none. The failed launch did not reach Python, and the corrected run executed once.
- **Recovery:** corrected only the PowerShell invocation shape; no code, configuration, service, or roadmap architecture change was required.
- **Attribution:** caller invocation error, not a CodexBridge durability or Hermes integration defect.
- **Reproduction frequency:** one malformed launch followed by one successful corrected launch.
- **Artifacts:** successful protected stdout SHA-256 `4bcd5867157c81e0396771d4421e36569e2f620655960255432cf2e921a007b7`; empty protected stderr SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; published result hash `ec94c7cd9c3547ab37a39ffb1a1d4a2654abbd7c615903e1e62c0186b94e2a0d`.
- **Disposition:** successful representative Hermes-backed pilot evidence. Continue collection across separate sessions and genuinely parallel workloads; no repair program is justified.
