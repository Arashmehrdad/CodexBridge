# Patch Auto-Repair Durability / Reliability Stress Audit - 2026-08-15

Status: **PASS - DURABILITY AND RELIABILITY VERIFIED UNDER BOUNDED CHAOS**

## Scope

This audit was performed after Patch Auto-Repair G8 source acceptance and A1 live activation.

Activation baseline:

- G8 source acceptance: `e54f9107c4ce0f04777486084bddca65ee7d6175`
- A1 live activation acceptance: `77c262e2e02a92cc4a9278764a3a3b59723d22f9`
- accepted/live public gateway count: `34`
- accepted/live operation schema count: `264`
- accepted `repo_preview.resolve_patch` schema: `2fdbe6ae4bb313cc6a406f66b0db46140ee0979fe04a2035a37de14b697a0213`

The campaign tested:

1. repeated real Soma restart survival;
2. Cloudflare tunnel ownership/singleton/protocol stability;
3. durability of active Soma runs across process replacement;
4. external network-loss recovery during the campaign;
5. sustained local/public MCP availability after chaos;
6. repeated live Patch Auto-Repair detection/resolution determinism;
7. resolution idempotency and conflicting-request rejection;
8. concurrent public-gateway use under repeated high-risk test load;
9. resolved patch bundle persistence across a later Soma restart;
10. self-check, lock-store, SQLite, worktree, and cleanup integrity.

No malformed patch was applied to owner source. No push was performed.

---

## 1. Baseline identity and lock freeze

Before destructive stress:

- source/runtime identity: converged
- server build: `25dff6c0e86fb789726bf4e692a500e5eb08e164b7ff16cdbbf54447b8459a41`
- schema hash: `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`
- public schema hash: `ca028988d82f73a56d7524fd464bfdda53952b756a4835ac3ff8dc64e5dc0f42`
- public descriptor hash: `7acb65f1c6e3d4b85ea82296bd7d5cec281211c1b5bc00214d3b5b4860106273`
- operation inventory hash: `71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588`
- public gateways/tools: `34`
- operation schemas: `264`
- restart required: `false`
- connector refresh required: `false`
- operation contract repair required: `false`
- pre-stress lock table: empty

---

## 2. Three-cycle restart + tunnel chaos campaign

Durable campaign run:

- `20260815T105147Z_executable_profile_dadbe55e`
- status: completed
- exit code: `0`
- duration: `218.346 s`
- terminal marker: `DURABILITY_RESTART_STRESS_OK`

The harness continuously sampled:

- local MCP readiness at `http://127.0.0.1:8000/mcp`;
- public MCP readiness at `https://mcp.spaceshipgames.win/mcp`;
- Soma tunnel `cloudflared` process count;
- `--protocol http2` command-line identity;
- recovery stability after each restart.

### Restart results

| Cycle | Restart exit | Stable recovery | Campaign recovery window |
| --- | ---: | --- | ---: |
| 1 | 0 | yes | 49,411 ms |
| 2 | 0 | yes | 67,385 ms |
| 3 | 0 | yes | 53,438 ms |

`recovery window` is the harness wall interval from restart launch through eight consecutive healthy local/public/tunnel samples. It is not a direct outage-duration measurement.

### Sample results

- total samples: `94`
- restart cycles passed: `3 / 3`
- local success over all samples: `76.6%`
- public success over all samples: `73.4%`
- local maximum consecutive failed samples: `8`
- public maximum consecutive failed samples: `11`
- local p50: `5.1 ms`
- local p95: `13.7 ms`
- local p99: `1020.5 ms`
- public p50: `294.5 ms`
- public p95: `542.4 ms`
- public p99: `857.5 ms`
- maximum Soma `cloudflared` count observed: `1`
- duplicate-tunnel samples: `0`
- wrong-protocol samples: `0`
- final local readiness: `true`
- final public readiness: `true`
- final tunnel count: `1`
- final tunnel protocol: `http2`

The local/public success percentages intentionally include the commanded restart outage windows and therefore are not steady-state availability figures.

### Durable worker survival across all three restarts

The stress run itself remained on:

- worker PID: `159876`
- lease generation: `1`
- launch attempts: `1`

Durable run events explicitly recorded `Active worker identity verified after server restart` after all three process replacements:

- event after restart 1: `2026-08-15T10:52:29Z`
- event after restart 2: `2026-08-15T10:53:24Z`
- event after restart 3: `2026-08-15T10:54:34Z`

No stale-worker transition, relaunch, safety failure, or recovery error occurred.

### Independent external network chaos

During this campaign the owner independently unplugged/reconnected the laptop modem/network connection while remaining in the session.

That introduced a real external network-loss event in addition to the commanded Soma restart windows. Because the manual network event was not timestamp-instrumented inside the harness, failed samples cannot be attributed exclusively between service restart and external network loss.

The important durability outcome is that the durable local worker survived, Soma/connector access returned without manual repair, and subsequent steady-state soak was perfect.

---

## 3. Post-chaos concurrent steady-state soak

Health-soak run:

- `20260815T105840Z_executable_profile_0cdf742a`
- status: completed
- exit code: `0`
- duration: `243.865 s`
- terminal marker: `CONCURRENT_HEALTH_SOAK_OK`

This child ran while Patch Auto-Repair test load and live gateway calls were also being exercised.

Results:

- samples: `120`
- local MCP success: `120 / 120` (`100%`)
- public MCP success: `120 / 120` (`100%`)
- local maximum observed response: `76.5 ms`
- public maximum observed response: `692.8 ms`
- duplicate-tunnel samples: `0`
- wrong-protocol samples: `0`
- final local readiness: `true`
- final public readiness: `true`
- final Soma `cloudflared` count: `1`
- final protocol: `http2`

The long wall duration came from deliberately expensive per-sample WMI process-identity checks, not HTTP request failures.

---

## 4. Live Patch Auto-Repair determinism stress

A disposable repository fixture was used under:

- `tests/_durability_patch_fixture/incident_b.py`
- `tests/_durability_patch_fixture/valid.py`

The files were never committed and were removed at campaign end.

Five identical live Incident-B-shaped malformed previews were issued through the public `repo_preview.patch` gateway.

Source patch IDs:

1. `20260815T105649Z_patch_9212cf30`
2. `20260815T105657Z_patch_50630194`
3. `20260815T105721Z_patch_9f9130a3`
4. `20260815T105734Z_patch_4be7c82c`
5. `20260815T105753Z_patch_f5231d99`

Every preview returned:

- `applicable = false`
- `candidate_validation_status = regression_detected`
- `resolution_required = true`
- `repair_available = true`
- exact same deterministic proposal: `repair_495d41552f6011ec`

This proves proposal identity is stable across separate source patch bundles for identical path/content/provenance input.

### Five independent explicit resolutions

All five source patches were resolved with distinct controller request IDs and exact proposal selection.

Resulting child patches:

1. `20260815T105649Z_patch_5481cc27`
2. `20260815T105657Z_patch_84894f5b`
3. `20260815T105721Z_patch_4d368bf8`
4. `20260815T105734Z_patch_64354825`
5. `20260815T105753Z_patch_ab8cea45`

Every child returned:

- `ok = true`
- `applicable = true`
- `candidate_validation_status = valid`
- `resolution_required = false`
- correct source/child linkage
- `idempotent_replay = false` on first creation

No child was applied.

### Idempotent replay

Replaying source `20260815T105649Z_patch_9212cf30` with the same request:

- request ID: `durability-cycle-1`
- decision: `accept_repair`
- proposal: `repair_495d41552f6011ec`

returned the exact existing child:

- `20260815T105649Z_patch_5481cc27`
- `idempotent_replay = true`

No duplicate child was created.

### Conflicting request reuse

Reusing the already-consumed `durability-cycle-1` identity with a different decision (`accept_original`) was rejected with:

`Patch 20260815T105649Z_patch_9212cf30 is already resolved by a different request`

Soma therefore does not silently reinterpret durable resolution history.

---

## 5. Public-gateway behavior under concurrent load

While the repeated high-risk test runner was active, additional live public previews were issued.

Valid preview:

- patch: `20260815T110014Z_patch_5d217043`
- result: `ok = true`
- `applicable = true`
- candidate validation: `valid`

Concurrent malformed preview:

- patch: `20260815T110022Z_patch_5ff9d79f`
- result: `applicable = false`
- candidate validation: `regression_detected`
- `resolution_required = true`
- `repair_available = true`
- proposal remained: `repair_495d41552f6011ec`

The detector remained deterministic under concurrent test/CPU/disk load.

---

## 6. Repeated high-risk core-suite stress

Canonical corrected stress run:

- `20260815T105941Z_executable_profile_e9ab087c`
- exact interpreter: `C:\Users\arash\AppData\Local\Programs\Python\Python311\python.exe`
- exact required `PYTHONPATH`: `D:\Github\TradingLab\src;D:\Github\Soma`
- status: completed
- exit code: `0`
- lease generation: `1`
- launch attempts: `1`

Suites repeated five consecutive times:

- `tests/test_repo_patch_repair.py`
- `tests/test_repo_patch_resolution_service.py`
- `tests/test_repo_patch_evidence_g7.py`
- `tests/test_repo_patch_resolution_public_gateway.py`

Results:

| Pass | Result | Duration |
| --- | --- | ---: |
| 1 | 84 passed | 35.04 s |
| 2 | 84 passed | 35.22 s |
| 3 | 84 passed | 43.83 s |
| 4 | 84 passed | 37.42 s |
| 5 | 84 passed | 30.69 s |

Aggregate: **420 / 420 tests passed**.

No code change was made between repetitions.

---

## 7. Harness-environment audit findings

Three harness/setup problems occurred during the campaign. They are recorded explicitly because reliability audits must distinguish product failures from test-driver failures.

### 7.1 Fixture writer quoting error

Run:

- `20260815T105621Z_executable_profile_286d0127`

The initial PowerShell fixture writer failed before valid fixture creation because quoting caused `Set-Content` argument parsing to fail.

The corrected byte-safe fixture writer:

- `20260815T105637Z_executable_profile_16a0cdd6`
- exit code: `0`

confirmed expected SHA-256 values and was used for all live tests.

### 7.2 Wrong Python selected by ad-hoc fallback

The first concurrent test child:

- `20260815T105840Z_executable_profile_a14f8b20`

fell back to LibreOffice's bundled Python 3.12 and failed with:

`No module named pytest`

No Soma test was executed far enough to produce a product result.

### 7.3 Python 3.11 without repository PYTHONPATH

Replacement run:

- `20260815T105900Z_executable_profile_18c302b2`

used Python 3.11 but omitted the repository's TradingLab import path and failed collection with:

`ModuleNotFoundError: No module named 'trading_lab'`

The audit then retrieved the exact environment from the already-successful 599-test G8 run and reran with the canonical interpreter + `PYTHONPATH`. That corrected run passed 420/420 as recorded above.

### Non-blocking infrastructure recommendation

The repository should eventually expose one canonical test-runner script/profile that fixes:

- Python executable identity;
- repository `PYTHONPATH` requirements;
- standard pytest/Ruff invocation environment.

This would eliminate operator ambiguity and prevent unrelated installed Python distributions from contaminating future audits.

This recommendation does not block Patch Auto-Repair acceptance; the accepted/canonical environment passes consistently.

---

## 8. Fourth restart - durable patch-bundle persistence

After resolved Patch Auto-Repair bundles existed, Soma was restarted again specifically to test persistence across process replacement.

Restart run:

- `20260815T110354Z_executable_profile_1be0e865`
- status: completed
- exit code: `0`
- duration: `69.195 s`
- lease generation: `1`

The connector produced expected transient 502 responses during process replacement and recovered autonomously.

After restart, the pre-existing source patch still reported:

- patch: `20260815T105649Z_patch_9212cf30`
- bundle version: `4`
- status: `resolved`
- role: source
- candidate validation: `regression_detected`
- decision: `accept_repair`
- selected child: `20260815T105649Z_patch_5481cc27`
- applied timestamp: empty
- reverted timestamp: empty

The pre-existing child still reported:

- patch: `20260815T105649Z_patch_5481cc27`
- bundle version: `4`
- status: `preview_ok`
- role: child
- candidate validation: `valid`
- `applicable = true`
- source: `20260815T105649Z_patch_9212cf30`
- decision: `accept_repair`
- applied timestamp: empty
- reverted timestamp: empty

This proves source/child resolution continuity survives Soma process replacement and is not merely in-memory state.

---

## 9. Self-check and lock-store audits

`system_query.self_check` was executed under load and again after the final restart.

All 10 domains passed:

- imports
- packages
- trading_lab
- config
- run_store
- startup_reconciliation
- supervisor_store
- supervisor_config
- service_identity
- comprehensive_validation

Lock audits showed:

- only the legitimate active test-run lease while the stress runner was running;
- lease generation `1` with fresh heartbeat;
- no stale/orphan lock;
- final lock table: empty.

---

## 10. Final service/tunnel/database forensic audit

Run:

- `20260815T110552Z_executable_profile_63cbda4c`
- status: completed
- exit code: `0`
- marker: `FINAL_FORENSIC_AUDIT_OK`

### Soma service

- local MCP ready: `true` (`HTTP 406` route-ready response)
- listener PID: `127808`
- listener count on `127.0.0.1:8000`: `1`

### Cloudflare tunnel

- public MCP ready: `true` (`HTTP 406`)
- protocol: `http2`
- PID: `95312`
- process count: `1`
- config: `C:\Users\arash\.cloudflared\soma-mcp.yml`
- durable ownership record: `runs/service_logs/soma-mcp-tunnel.identity.json`
- command line still contains `tunnel --protocol http2 ...`

No duplicate tunnel was present after four actual Soma restart cycles plus the external network event.

### SQLite durability

Database: `runs/soma.sqlite3`

- `PRAGMA integrity_check`: `ok`
- `PRAGMA quick_check`: `ok`
- `PRAGMA foreign_key_check`: `0` violations
- journal mode: `wal`
- table count: `52`

---

## 11. Fixture cleanup and final worktree integrity

The generic managed cleanup planner correctly refused an arbitrary repo path root, so no cleanup-policy boundary was weakened.

The two fixture files were then removed through exact SHA-bound managed `remove_file` previews and manual applies:

Incident fixture:

- removal preview: `20260815T110632Z_patch_e4f25a15`
- apply run: `20260815T110637Z_repo_apply_cf2bf7d5`
- apply exit code: `0`

Valid fixture:

- removal preview: `20260815T110659Z_patch_3085d2f3`
- apply run: `20260815T110704Z_repo_apply_1edc2b9f`
- apply exit code: `0`

Final repository status returned to exactly `43` untracked entries: the same pre-existing canonical-memory/Sol research set present before this campaign.

Final state:

- staged tracked files: none
- unstaged tracked files: none
- durability fixture residue: none
- unrelated research modified: none

The durable source patch bundle remained readable through `patch_status` even after its disposable fixture file was removed, further confirming that patch evidence is self-contained in the managed bundle/evidence store.

---

## 12. Final live identity

Final `capability_identity`:

- converged: `true`
- source/running build: `25dff6c0e86fb789726bf4e692a500e5eb08e164b7ff16cdbbf54447b8459a41`
- schema hash: `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`
- public schema hash: `ca028988d82f73a56d7524fd464bfdda53952b756a4835ac3ff8dc64e5dc0f42`
- public descriptor hash: `7acb65f1c6e3d4b85ea82296bd7d5cec281211c1b5bc00214d3b5b4860106273`
- operation inventory hash: `71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588`
- public gateways/tools: `34`
- operation schemas: `264`
- mismatches: none
- restart required: `false`
- connector refresh required: `false`
- operation contract repair required: `false`
- recommended actions: none

---

# Final verdict

**PASS - DURABILITY AND RELIABILITY VERIFIED UNDER BOUNDED CHAOS**

The live Patch Auto-Repair system and the hardened Soma/Cloudflare lifecycle survived:

- four actual Soma process restart cycles;
- repeated transient connector outages during those restarts;
- an independent owner-induced modem/network disconnect/reconnect;
- a durable worker running across three consecutive Soma restarts without lease replacement;
- 120/120 local and 120/120 public steady-state health probes after chaos;
- five deterministic live Incident-B proposal generations;
- five explicit source-to-child resolutions;
- idempotent replay and conflicting-request rejection;
- 420/420 repeated high-risk core tests;
- concurrent public-gateway calls under test load;
- resolved patch state persisted across another Soma restart;
- SQLite integrity/quick/FK checks;
- final single-process HTTP/2 tunnel ownership;
- exact worktree restoration after disposable fixture cleanup.

No durability/reliability defect was found in the accepted Patch Auto-Repair or hardened tunnel lifecycle during this bounded campaign.

The only actionable finding is test-harness environment ambiguity; canonicalizing the repo test runner is recommended but is not a product/runtime blocker.

No push performed.
