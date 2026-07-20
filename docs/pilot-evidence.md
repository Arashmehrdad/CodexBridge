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

## 2026-07-20 00:15 Europe/London - Repeated parallel capability rejection

- **Project:** CodexBridge.
- **Expected outcome:** run two genuinely independent focused Hermes test files concurrently through the public `powershell_group` gateway, with concurrency `2`, no repository lock, and continue-all failure policy.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; HEAD `1175b9cfd34bb8b79b647d39f4e2d01436c11047`; clean worktree; no running durable operations and no repository locks immediately before the attempt.
- **Live capability identity:** server build `b414c5c7261fa876dc22147fb34bdba5ee8852cd8e8655354dbb471320ed14bd`; schema `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`.
- **Attempted operation:** `tests/test_hermes_companion_protocol.py` and `tests/test_hermes_companion_client.py` requested as separate children of one `run_start(operation="powershell_group")` call.
- **Exact failure:** the public gateway rejected the request before durable-run creation with `Parallel PowerShell execution is disabled`.
- **Lost or duplicated work:** none. No child run was accepted, no test process started, and no repository mutation occurred.
- **Recovery:** serial durable PowerShell remains available; no cleanup or state repair was required.
- **Attribution:** repeated live capability/configuration unavailability. This is the second pilot reproduction and now demonstrates persistent operational friction, but it has not violated a durability or security invariant and does not block continuation through serial execution.
- **Reproduction frequency:** two attempts across separate connector sessions; two identical pre-acceptance rejections.
- **Artifacts:** connector rejection text retained in the initiating conversation; pre-attempt coordination evidence from completed runs `20260719T231446Z_executable_profile_86f12ff8` and `20260719T231526Z_executable_profile_a56b910d`.
- **Disposition:** continue observing and use serial execution. Promote only if parallel execution becomes required for a representative workflow, the configured capability is expected to be enabled, or recovery cost materially increases.

## 2026-07-20 01:23 Europe/London — Serial reversible-fixture regression workflow

- **Project:** CodexBridge.
- **Expected outcome:** exercise an ordinary serial durable validation of the repository-owned Hermes connected-MCP reversible-side-effect and lifecycle fixture without architectural change or tracked-file mutation.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; starting HEAD `8c4df77a2888272f1de1e90e9c71907305bebd70`; clean worktree; no running durable operations and no repository locks before launch.
- **Live capability identity:** server build `b414c5c7261fa876dc22147fb34bdba5ee8852cd8e8655354dbb471320ed14bd`; schema `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`.
- **Operation:** durable allowlisted pytest run `20260720T002321Z_project_command_e0b9a23b` executed `tests/test_hermes_mcp_fixture.py`.
- **Verified result:** `5 passed in 0.50s`; exit code `0`; empty stderr; no changed files; terminal result published with hash `a4507c139e07a4108f6abb36549a2ebe41e711be2ae6b53210885f7a7d93244f`.
- **Lost or duplicated work:** none. The durable worker claimed once, completed once, and published one terminal result.
- **Recovery:** none required.
- **Attribution:** successful ordinary serial operation through the current permissive durable gateway.
- **Reproduction frequency:** one additional successful pilot workflow in a separate automation session.
- **Artifacts:** durable run directory and published result for `20260720T002321Z_project_command_e0b9a23b`.
- **Disposition:** continue OP1 collection. This adds positive evidence for serial durability and reversible-fixture regression coverage; it does not justify Roadmap V3 expansion.

## 2026-07-20 02:01 Europe/London — Parallel capability configuration repair

- **Project:** CodexBridge.
- **Expected outcome:** investigate the two repeated public `powershell_group` pre-acceptance rejections, restore the completed X2A capability if the live profile was unintentionally disabled, and prove genuine concurrent execution without restarting the service or tunnel.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; starting HEAD `50e4312dbac6963c0597af4311be8e22f8a26b65`; clean tracked worktree; no running or queued durable operations and no repository locks before the repair.
- **Live capability identity:** server build `b414c5c7261fa876dc22147fb34bdba5ee8852cd8e8655354dbb471320ed14bd`; schema `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`.
- **Diagnosis:** the public `powershell_group` request schema remained exposed and `parallel_groups.py` rejected only when `config.parallel_execution.enabled` was false. The ignored live `config.yaml` parsed as `enabled: false`, while the completed X2A contract and acceptance record specify `enabled: true`. This was live configuration drift, not a missing implementation or durable-worker regression.
- **Repair:** changed only the ignored live flag from `false` to `true`; config SHA-256 changed from `a2b15bde55b8fa158cea11938a3251a01aec1a6178a4542fc91da02fa0c9416e` to `f31100ad58184e1603e076ed772d395c7a20780b70d67741530b7cfc6591da8a`. CodexBridge configuration validation passed, and the validated config was hot-reloaded at `2026-07-20T01:00:57Z` with no restart-required modules and no CodexBridge or Cloudflare restart.
- **Public acceptance:** group `20260720T010132Z_powershell_group_3da40097` was accepted with requested concurrency `2`, repository lock policy `none`, and failure policy `continue_all`. Child runs `20260720T010132Z_executable_profile_44747e2b` and `20260720T010132Z_executable_profile_51821250` both completed with exit code `0` and empty stderr.
- **Concurrency evidence:** child A's command window was `2026-07-20T01:01:40.4508122Z` through `2026-07-20T01:01:42.4933590Z`; child B's was `2026-07-20T01:01:41.8756995Z` through `2026-07-20T01:01:43.9248638Z`. The windows overlapped by approximately `0.618` seconds, proving concurrent execution rather than serial fallback.
- **Publication evidence:** child A published result hash `a6d4373ce060968d6ff7c657a9595021c0e8ce55379becff4d2f8bf202d17554`; child B published result hash `7814c5273171a5cfa43738a6bd1d2ae8e88f1b8598c5238a4b1559e95a0a7372`; the aggregate group published `status_counts: {completed: 2}` and `terminal_child_count: 2`.
- **Lost or duplicated work:** none. Each child was reserved once, claimed once, completed once, and appeared once in the aggregate result.
- **Recovery and attribution:** no source-code repair, service restart, tunnel restart, or repository cleanup was required. The problem was an unintentionally disabled live capability flag.
- **Reproduction frequency:** two prior identical rejections followed by one successful public concurrent group after the configuration repair.
- **Disposition:** resolved. Parallel execution is available again. Continue OP1 collection across representative workloads; this configuration repair does not itself justify Roadmap V3 architectural expansion.

## 2026-07-20 02:15 Europe/London — Representative parallel Hermes validation

- **Project:** CodexBridge.
- **Expected outcome:** use the repaired public `powershell_group` capability for a real concurrent validation workload covering the Hermes protocol and durable companion client.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; HEAD `d2de33ab16148dbe4ffc383080e9e6e0ab346edc`; clean worktree; no running or queued durable operations and no repository locks before launch.
- **Live capability identity:** server build `b414c5c7261fa876dc22147fb34bdba5ee8852cd8e8655354dbb471320ed14bd`; schema `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`.
- **Initial parallel operation:** group `20260720T011456Z_powershell_group_7495419b` launched `tests/test_hermes_companion_protocol.py` and `tests/test_hermes_companion_client.py` with requested concurrency `2`, repository lock policy `none`, and continue-all failure policy.
- **Initial result:** protocol child `20260720T011456Z_executable_profile_6a14e813` completed with `5 passed in 2.25s`. Client child `20260720T011456Z_executable_profile_56a0145e` reached pytest but failed fixture setup with `PermissionError: [WinError 5] Access is denied` on the shared global path `C:\Users\arash\AppData\Local\Temp\pytest-of-arash`; one test passed and five errored. The two child start times overlapped, proving the repaired group capability executed concurrently.
- **Recovery:** without deleting or modifying the inaccessible global temp directory, reran both tests through group `20260720T011531Z_powershell_group_a2161679` using separate repository-owned `--basetemp` paths under ignored `runs`.
- **Verified result:** protocol child `20260720T011531Z_executable_profile_f70034d7` completed with `5 passed in 1.18s`; client child `20260720T011531Z_executable_profile_3d9132c4` completed with `6 passed in 1.17s`; both exited `0`, and the aggregate published `status_counts: {completed: 2}` with two terminal children.
- **Lost or duplicated work:** none. Each accepted child was claimed and published once. The failed first client run made no tracked repository change, and the retry used distinct idempotency keys and isolated temp roots.
- **Attribution:** parallel execution itself is functioning. The first-group failure is the previously observed Windows pytest shared-temp permission friction, not a Hermes, test, or durable-group defect. Repository-owned isolated basetemps provide a safe operational workaround.
- **Reproduction frequency:** one failure on the shared global pytest temp root followed by one fully successful isolated parallel retry.
- **Disposition:** successful representative parallel pilot evidence. Continue OP1 across separate sessions and ordinary Hermes-backed work; do not promote the temp-path observation to a repair program unless it repeatedly blocks representative validation despite the isolated-basetemp path.

## 2026-07-20 04:13 Europe/London — Schema-bound Hermes repository read

- **Project:** CodexBridge.
- **Expected outcome:** exercise an ordinary Hermes-backed repository read outside the disposable connected-MCP fixture path, binding the live catalog identity, exact `read_file` schema, accepted arguments, and returned OP1 content without tracked-file mutation.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; starting HEAD `2778fec2f8b931e05534cee15cb6b02a7842bb90`; clean worktree; no running durable operations and no repository locks before launch.
- **Coordination inspection:** active durable runs were empty and repository locks were absent. No supervisor or workflow list surface is exposed; those durable objects remain queryable only by known identity, and no matching active identity was present in the current handover.
- **Schema discovery:** durable run `20260720T031032Z_executable_profile_9ab379ca` completed with exit code `0`, registry generation `79`, effective schema hash `3d653132680587e2e4b5639a9b0dcf5a6d5443fdc4643af6f1ae4679073761a3`, `model_runtime_initialized: false`, and exact `read_file` tool-schema hash `265fc44e1ec436b2716993e33375040ac26ebae8fc87c770851089db21b93633`.
- **Caller correction:** run `20260720T031146Z_executable_profile_9739ef8d` omitted the prepared `arguments` and `tool_schema_hash` fields when constructing the request, so Hermes correctly attempted an empty path and returned `File not found`. No repository mutation occurred. The error was a caller-side harness construction mistake, not a gateway or Hermes defect.
- **Successful operation:** durable run `20260720T031343Z_executable_profile_64617d6e` invoked `read_file` with path `D:\\Github\\CodexBridge\\PLANS.md`, offset `287`, and limit `12`, bound to the exact live schema identity.
- **Verified result:** the returned content contained lines `287-298`, including `## OP1 - Evidence-Driven Real-Project Pilot`, the current in-progress status, and the pilot exercise list. The run completed in `4.729` seconds with exit code `0` and empty stderr.
- **Lost or duplicated work:** none. The malformed request was read-only and failed safely; the corrected request executed once and published one terminal result.
- **Artifacts:** successful protected stdout SHA-256 `9efb08bae34cb4f9d5c4dd8991800b6ac4e42e8738e34466a3dd1fa37a34519e`; empty protected stderr SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
- **Disposition:** successful ordinary Hermes-backed pilot evidence across another session. Continue OP1 collection; no security, durability, loss, duplication, corruption, or continuation-blocking threshold was crossed.

## 2026-07-20 04:48 Europe/London — Hermes reversible action and ambiguous-outcome recovery

- **Project:** CodexBridge.
- **Expected outcome:** exercise an approved repository-owned reversible action through the pinned Hermes connected-MCP path, intentionally produce an ambiguous post-commit response, reconcile the authoritative outcome, prove idempotent replay, reverse it, and verify final absence without changing tracked source or restarting CodexBridge or Cloudflare.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; starting HEAD `5765e093dd53ba81610e93dcf526fdeac3cec859`; clean worktree; no running or queued durable operations and no repository locks before each accepted attempt. The old CodexBridge supervisor `20260711T022528Z_supervisor_8530a6a1` remained dormant in `needs_input` with no active child and was left untouched; the newest inspected workflow was already terminal and reported.
- **Live capability identity:** server build `b414c5c7261fa876dc22147fb34bdba5ee8852cd8e8655354dbb471320ed14bd`; schema `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`.
- **Hermes identity:** protocol `1.0`; registry generation `89`; effective schema hash `8407c006a068f7a924040a1028a78fb564afff781399a5488ae069ab478b7fb5`; `model_runtime_initialized: false`.
- **Tool identity:** apply schema hash `4eff7674906c70b559b9255711bd10dd560326232299bf1fd4b5f4a2e117b90c`; reconcile schema hash `f90aeb57c02ddbb6d5ff171778eff7c890891ccfd117f483ebaa18ac4ffdac74`; revert schema hash `c71d240b1ec833b0bd797ef98b8264b4a4f04cefeeec97536f766c014f26b643`.
- **Mutation identity:** idempotency key `op1-reversible-6f1f2d93ee5245db8867f170b81af055`; value `op1-representative-reversible-action`; isolated repository-owned Hermes home `runs/op1-hermes-reversible-faae97f8c020492ba38e3b20da07a70e`.
- **Ambiguous operation:** durable run `20260720T033256Z_executable_profile_3646f324` committed the fixture mutation and returned the intentional post-commit error inside the Hermes tool-result envelope. The caller harness incorrectly expected the outer companion envelope to have `ok: false`, so the run terminated as failed after the mutation had been applied exactly once.
- **Recovery friction:** runs `20260720T033602Z_executable_profile_896c194b` and `20260720T033844Z_executable_profile_bdbbc6d2` each reached authoritative reconciliation and observed the correct value with `application_count: 1`, but caller-side decoders stopped at intermediate serialized MCP wrappers. Run `20260720T034123Z_executable_profile_0c3e2ef9` failed before any tool call because of a protocol-constant typo. One text-stdin request and one malformed base64 request were rejected before durable-run creation. None of these attempts replayed or altered the mutation.
- **Verified recovery:** durable run `20260720T034728Z_executable_profile_dbe77bd2` completed in `3.275` seconds with exit code `0`. Reconciliation returned `exists: true` and `application_count: 1`; replay with the same key and arguments returned `applied: false` while preserving `application_count: 1`; reversal returned `reverted: true`; final reconciliation returned `exists: false`.
- **Lost or duplicated work:** none. The mutation was applied once, never blindly duplicated, and was ultimately reversed. Every accepted durable run published one terminal result.
- **Attribution:** caller transport, envelope-shape, decoder, and typo errors while driving a working schema-bound Hermes path. No CodexBridge durability, policy, or Hermes execution defect was demonstrated.
- **Reproduction frequency:** one reversible pilot workflow, four accepted failed harness attempts, and one accepted successful recovery; two additional malformed requests were rejected before run creation.
- **Artifacts:** successful result publication hash `956d729511b41cd50f8211a7851ec17fce179f9370e8855bfcf0544029a98ae4`; protected stdout SHA-256 `944d5639fdf8b41f380a5da7a28a189448b1e1c66e57bac8f7c2fd81e0d09552`; empty protected stderr SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`. Failed attempts retained their own terminal publications and protected error artifacts.
- **Disposition:** successful representative reversible-action pilot evidence with realistic caller recovery friction. No durability or security invariant was violated, no work was lost or duplicated, and no Roadmap V3 promotion threshold was crossed.

## 2026-07-20 05:11 Europe/London — Windows parallel lifecycle acceptance regression

- **Project:** CodexBridge.
- **Expected outcome:** exercise the established Windows parallel PowerShell lifecycle through the ordinary durable validation gateway, covering capped and uncapped fan-out, pending-child refill, sibling continuation after failure, restart adoption without duplicate launch, whole-group cancellation, cancel-remaining behavior, and individual-child cancellation with slot refill.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; HEAD `cf6d8f631924d13c2c61c305754c251fb60c0ced`; clean worktree; no running durable operations and no repository locks before launch.
- **Live capability identity:** server build `b414c5c7261fa876dc22147fb34bdba5ee8852cd8e8655354dbb471320ed14bd`; schema `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`.
- **Operation:** durable allowlisted pytest run `20260720T041122Z_project_command_ae803c00` executed `tests/test_parallel_powershell_acceptance.py` using the repository-owned isolated pytest basetemp.
- **Verified result:** `7 passed in 30.75s`; exit code `0`; empty stderr; no changed files; one worker claim; one terminal result publication with hash `db7fbc62b8c6864c57510a2295a40559e66a3b98ccbfbaff610e84e1b7f5bbfc`.
- **Lost or duplicated work:** none. Restart reconciliation retained the existing worker identity and launch-attempt count, cancellation tests terminated the intended process trees, and pending siblings refilled exactly once.
- **Recovery:** none required.
- **Attribution:** successful regression evidence for the completed X2A lifecycle and durability contracts under the current permissive runtime.
- **Reproduction frequency:** one complete seven-test Windows lifecycle pass in this pilot session.
- **Artifacts:** durable run directory and published result for `20260720T041122Z_project_command_ae803c00`; isolated pytest basetemp under that run directory.
- **Disposition:** successful representative lifecycle evidence. Continue OP1 observation across ordinary project work; no Roadmap V3 promotion threshold was crossed.

## 2026-07-20 06:27 Europe/London — Live service self-check and bounded schema-contract repair

- **Project:** CodexBridge live service and repository.
- **Expected outcome:** exercise ordinary service health, configuration, dependency, store, transport, and full-suite validation through the public system self-check without architectural expansion.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; starting HEAD `c4424d60c4f684df9df9ecc370bf434bb5eb6e26`; clean worktree and no repository locks before inspection or writes.
- **Initial service result:** imports, configuration parsing, `pip check`, Git status, run-store WAL state, supervisor-store tables, and the temporary HTTP transport were healthy. The full suite reported `1 failed, 1193 passed, 5 skipped` because `tests/test_mcp_action_discovery.py` still asserted eight `run_start` variants while the public discriminated schema exposed ten.
- **Repair:** replaced the brittle numeric count with the exact supported operation set. The first focused run correctly exposed an expectation mismatch between internal `project_command` and public `remote_powershell`; the exact public set was corrected in follow-up commit `0a37cd712c1dbe44fc1868fdab1582a62a7f66f3` after initial commit `6876682db28b851d71f4656a4481891df1cdde8b`.
- **Focused validation:** durable run `20260720T052608Z_project_command_45edbaad` completed `tests/test_mcp_action_discovery.py` with `29 passed in 1.95s`, exit code `0`, no changed files, and terminal result hash `148da2b080c36bb733b79247668f6d61d789cc82ac18eb58e3141ae6a68b50c0`.
- **Full validation:** the repeated live system self-check passed completely: `1194 passed, 5 skipped in 200.44s`; `pip check` reported no broken requirements; imports, config, Git status, run store, supervisor store, and HTTP transport were healthy.
- **Lost or duplicated work:** none. The failed assertions were read-only validation failures; each managed change was committed once and the worktree remained clean.
- **Attribution and frequency:** confirmed stale test-contract assertion, previously listed as a known observation. One full-gate reproduction and one focused expectation correction were sufficient to isolate it.
- **Disposition:** resolved as a bounded pilot defect. Remove the stale assertion from current observations; no broader Roadmap V3 program is justified.

## 2026-07-20 07:22 Europe/London — Bounded external-service capability and availability check

- **Project:** CodexBridge external-service gateways.
- **Expected outcome:** exercise ordinary read-only service capability and health inspection without starting, changing, or provisioning infrastructure solely for pilot evidence.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; HEAD `1dcd51033125f5faf765f273c3ba3d0f7b59ac57`; clean worktree; no running or queued durable operations and no repository locks before inspection.
- **Live capability identity:** server build `b414c5c7261fa876dc22147fb34bdba5ee8852cd8e8655354dbb471320ed14bd`; schema `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`.
- **Cloudflare capability result:** the gateway was enabled and exposed its bounded read-only and gated action catalog, but `profiles` was empty. No account, zone, tunnel, DNS, or mutation request was attempted because no repository profile was bound.
- **Docker capability result:** the gateway was enabled with Docker client `29.3.1` and Docker Compose `v5.1.1` available. No compose files, project name, or exec profiles were configured for this repository.
- **Docker health result:** the client command executed normally, but the Docker Desktop Linux engine pipe `//./pipe/dockerDesktopLinuxEngine` was absent because the engine was not running. The gateway returned a bounded failed health result with exit code `1`; Compose version inspection still completed successfully.
- **Lost or duplicated work:** none. Both paths were read-only, no durable mutation was accepted, and no repository or external service state changed.
- **Recovery:** none attempted or required. Docker Desktop was deliberately not started solely to manufacture pilot evidence, and Cloudflare configuration was not expanded without a real workload.
- **Attribution:** current external-infrastructure availability and configuration, not a CodexBridge durability, policy, transport, or schema defect.
- **Reproduction frequency:** one Cloudflare capability inspection and one Docker capability/health inspection in this session.
- **Artifacts:** bounded public gateway responses retained by the initiating conversation; repository identity and capability build hashes recorded above.
- **Disposition:** successful negative-path service evidence. Continue OP1 with an actually configured non-CodexBridge project or service when one is naturally used; do not create infrastructure or broaden configuration solely to close the pilot.

## 2026-07-20 08:01 Europe/London — Diff-stream and PowerShell stdin contract repair

- **Project:** CodexBridge public repository and executable gateways.
- **Expected outcome:** investigate two failures encountered during ordinary real-project work, preserve the successful final repository commit, apply only bounded compatibility repairs, activate them without disturbing Cloudflare, and verify the same public paths that failed.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; starting HEAD `537b27d2f703455ad46bbc2246018f90ef89c75b`; clean worktree; no running or queued durable operations and no repository locks before inspection, writes, or validation.
- **Reported diff failure:** combined and per-file `repo_query` diff reads raised `'NoneType' object has no attribute 'encode'`; native read-only `git diff` provided a successful workaround. The original workload completed without data loss and its final commit was unaffected.
- **Reported stdin failure:** the public PowerShell request schema exposed `stdin_text`, but the configured byte-capable `powershell` profile rejected it with `Executable profile is not configured for text stdin`; argv-based PowerShell operations provided a successful workaround.
- **Reproduction and attribution:** clean public combined and per-file diff calls did not reproduce the state-dependent crash, but source inspection found an unguarded `result.stdout.encode(...)` path and a regression fixture reproduced the exact `stdout=None` condition. The text-stdin rejection reproduced exactly through the public `run_start` gateway before durable-run creation. Both were bounded gateway contract defects rather than policy, durability, or user-workflow failures.
- **Repair commit:** `3858d7586bc4ce74818d77253d35018738c9d5e2`. Git text subprocess results now normalize missing stdout or stderr captures to empty strings at the shared boundary. Byte-capable executable profiles now accept advertised `stdin_text`, encode it as UTF-8, and preserve the existing byte staging and execution policy.
- **Regression validation:** run `20260720T064945Z_project_command_6cdadb39` passed the missing-stream diff regression; run `20260720T065021Z_project_command_6f7107de` passed the text-to-byte profile regression. Full adjacent suites passed: `tests/test_executable_profiles.py` reported `6 passed`, and `tests/test_git_tools.py` reported `34 passed`. Both modified source modules passed `py_compile`; durable `git diff --check` exited `0`.
- **Live activation:** hot reload could not safely rebind the directly imported diff helper and executable request builder, so durable run `20260720T065832Z_executable_profile_0d9dded3` used the dedicated server-only restart action. It completed with exit code `0`, one worker identity, one launch attempt, and one terminal publication hash `c6241bd85f398e4b56d38014ff7378fc5be70b28851a8d4b160b8fa694943513` after the replacement server adopted the active worker.
- **Process and capability identity:** server PID changed from `23160` to `12048`; configured Cloudflare tunnel PID remained exactly `28032`. The live build changed from `b414c5c7261fa876dc22147fb34bdba5ee8852cd8e8655354dbb471320ed14bd` to `f7292cb4f6a6e48e7ffe195330883f2874408ef8eda8d30831c27f49e268f53d`; public schema remained `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`.
- **Public stdin verification:** run `20260720T070049Z_executable_profile_a254fb48` accepted the formerly rejected `stdin_text`, staged 23 UTF-8 bytes under byte mode with input SHA-256 `13240b8354683a10b9875a6cd996ec2633de69fe1f9ff1b1415f554f36d26c07`, echoed `schema-text-stdin-probe` exactly, exited `0`, published once with hash `aca7b439ba1442ffa080c1a12f5701f1e08aac8b937bd6d07c36c0f4640b503c`, and produced empty stderr.
- **Public diff verification:** under the repaired live build, both combined and path-scoped `repo_query diff` calls returned structured successful empty results for the clean worktree rather than raising an encoding exception. The missing-stream edge is regression-locked independently of repository cleanliness.
- **Lost or duplicated work:** none. The original workload used safe workarounds; both pre-repair failures were non-mutating; the repair was committed once; the restart worker was adopted without duplicate launch; no repository or external-service state was lost.
- **Deployment state:** nothing was pushed or deployed. CodexBridge itself was restarted only because direct import bindings prevented safe hot activation; Cloudflare was neither restarted nor changed.
- **Disposition:** resolved as a bounded OP1 compatibility repair. No security, destructive-targeting, corruption, loss, duplication, or continuation-blocking threshold remains, and no Roadmap V3 promotion is justified.

## 2026-07-20 08:18 Europe/London — Formal OP1 observation review and closure

- **Review scope:** twelve evidence entries spanning ordinary durable repository validation, repeated connector sessions, genuine parallel work, Windows restart and cancellation behavior, Hermes-backed reads, a reversible idempotent action with ambiguous-outcome reconciliation, full live-service validation, bounded external-service availability, and defects encountered during ordinary real-project work.
- **Durability outcome:** no accepted operation lost work or applied work twice. Restart adoption retained worker identity and single publication; cancellation targeted the intended process trees; ambiguous mutation outcome reconciled to exactly one application before reversal.
- **Security and targeting outcome:** no credential exposure, destructive mis-targeting, unrecoverable corruption, or unintended external mutation was observed. Paid or unavailable infrastructure was not started solely to manufacture evidence.
- **Operational friction reviewed:** live parallel configuration drift was repaired; the shared Windows pytest-temp path remains avoidable through repository-owned basetemps; Cloudflare lacked repository profiles; Docker Desktop's Linux engine was stopped; several caller request-shape mistakes failed safely without mutation.
- **Confirmed defects repaired:** the stale public action-schema assertion, missing Git capture-stream normalization, and advertised text-stdin compatibility for byte-capable PowerShell profiles were corrected with focused and adjacent regression coverage. The complete live self-check ended at `1194 passed, 5 skipped` with healthy dependencies, configuration, stores, Git state, and HTTP transport.
- **Roadmap V3 decision:** do not create Roadmap V3. The repaired defects were bounded compatibility issues, and the remaining observations do not show a repeated architectural failure, violated durability/security invariant, or material recovery burden.
- **Closure decision:** OP1 is complete. Preserve this log as the observation record and continue ordinary evidence collection only opportunistically; it is no longer a roadmap gate.
- **Next executable unit:** TL0, beginning with the user-established Alpari MetaTrader 5 practice environment and live acceptance evidence. No Trading Lab source file may be created before TL0 passes.

## 2026-07-20 08:46 Europe/London — Post-closure SSH payload newline transport repair

- **Project:** CodexBridge reviewed-SSH deployment path during a real frontend release attempt.
- **Expected outcome:** execute a hash-pinned Bash deployment script that would create frontend release `bf7930e` and promote it only after its guarded deployment checks passed.
- **Repository identity:** branch `feature/domain-tool-gateway-migration`; starting HEAD `46514a695558b2d434fffcc5d9531fed4f474eeb`; clean worktree; no running or queued durable operations and no repository locks before inspection, writes, validation, or activation.
- **Observed failure:** the reviewed script exited before any production mutation with `bash: line 1: set: pipefail\r: invalid option name` and exit code `2`. The accepted run reported `line_endings_normalized: false`.
- **Root cause:** manager-side canonicalization already normalizes submitted CRLF for `bash` and `sh`. The later shared SSH subprocess runner passed canonical text to Windows `ssh.exe` with `text=True`; Windows text-stream newline translation could therefore convert LF back to CRLF during stdin delivery. This explains the apparently contradictory metadata: no manager normalization was needed for the accepted canonical text, but the transport subsequently reintroduced carriage returns.
- **Production state:** active frontend release remained `6b997f7`; release directory `bf7930e` was not created; no files were uploaded; Nginx was neither edited nor reloaded. Backend, API, database, Directus, Docker, TLS, DNS, and Xray were untouched, and the live site remained available.
- **Repair commit:** `08c614e025845b6297d2f54996b35621b5d2d093`. SSH invocations that carry stdin now encode the exact accepted text once as UTF-8 bytes and run the subprocess in binary mode. No-stdin SSH commands retain their existing text-mode behavior. Stdout, stderr, and timeout partial output are decoded explicitly after execution.
- **Regression validation:** run `20260720T073928Z_project_command_d2f1d679` passed the exact `set -euo pipefail` LF-only byte-transport regression; run `20260720T074022Z_project_command_50a46b79` completed the full SSH command suite with `30 passed`; run `20260720T074056Z_project_command_06839664` completed the SSH worker suite with `39 passed`; run `20260720T074140Z_project_command_665f6cfe` passed both manager-side `bash` and `sh` CRLF canonicalization cases. `codexbridge/ssh_commands.py` passed `py_compile`, and durable `git diff --check` exited `0`.
- **Live activation:** durable server-only restart `20260720T074502Z_executable_profile_875a04eb` completed with exit code `0`, one worker identity, one launch attempt, and one terminal publication hash `d7c586344315becf117977807b540a66dc40cdac47d8bde9d09927fa4e4c0dde` after the replacement server adopted the active worker.
- **Process and capability identity:** server PID changed from `12048` to `23624`; configured Cloudflare tunnel PID remained exactly `28032`. The live build changed from `f7292cb4f6a6e48e7ffe195330883f2874408ef8eda8d30831c27f49e268f53d` to `22bf15602aeb0a661666794ab15db66d3427601bc695fe09215d98a550ff4acc`; public schema remained `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`.
- **Lost or duplicated work:** none. The failed deployment exited before mutation, the code repair was committed once, and the restart worker was adopted without duplicate launch or publication.
- **Deployment state:** nothing was pushed and the website deployment was not retried as part of the repair. CodexBridge alone was restarted; Cloudflare and production infrastructure were unchanged.
- **Disposition:** resolved as bounded post-OP1 operational evidence. OP1 remains closed, TL0 remains the active roadmap unit, and no Roadmap V3 promotion threshold is crossed.
