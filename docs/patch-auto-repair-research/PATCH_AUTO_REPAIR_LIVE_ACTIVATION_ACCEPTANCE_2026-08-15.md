# Patch Auto-Repair Live Activation Acceptance - 2026-08-15

Status: **LIVE FEATURE ACCEPTED**

## Scope

This record closes A1, the owner-authorized live activation gate, for Patch Auto-Repair after G8 source acceptance.

Source acceptance commit entering activation:

- `e54f9107c4ce0f04777486084bddca65ee7d6175` - `Accept Patch Auto-Repair G8 source release`

Implementation plan:

- `docs/patch-auto-repair-research/PATCH_AUTO_REPAIR_IMPLEMENTATION_PLAN_2026-08-12.md`
- plan SHA-256: `197e69d5f546744332de39549831f497a67495183e3df23aea6fb4f217b6e21a`

Owner authorization was explicitly provided for the Soma restart and the subsequent connector Refresh.

No push was authorized or performed.

## A1.1 - Pre-activation identity freeze

The pre-activation live identity was captured during G8 before the restart:

- running server build hash: `6a70a9a88cbff9a1cb1aea6259ea9ab80457340d55e23fefcac8d388e7755754`
- source server build hash: `25dff6c0e86fb789726bf4e692a500e5eb08e164b7ff16cdbbf54447b8459a41`
- schema hash: `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`
- running capability epoch: `6a70a9a88cbf-42bdb69d96fb`
- running operation inventory hash: `7b61ecc4ef565357483c11168e55f3fa962e767a295a720453af7ca86f7f731f`
- running public schema hash: `00afcf876e27fbc549c1510dd2e946e56c5531f55e13db6595c24a3feacf82a9`
- running public descriptor hash: `771b818449b3de0498a23ca987a606b9aeb08753ac9e27cf61a51460ad9cda0f`
- running discovery cache generation: `4152cefdc90375efed1109c72a34c46e19bff67941a10bafdaddc401fb28990b`
- running operation schema count: `263`
- running public gateway/tool count: `34`
- `repo_preview.resolve_patch`: absent from the old running operation set
- `restart_required = true`

This established the expected source/runtime divergence before activation.

## A1.2 - Owner-authorized activation

A config-only reload was first attempted through the validated reload gateway. It correctly reloaded only `config` and did not restart the process, so it was not treated as source activation.

The actual source activation then used the owner-authorized canonical service-manager restart path:

- durable run: `20260815T104453Z_executable_profile_83de2380`
- command path: `scripts/manage_soma_service.ps1 restart`
- terminal status: completed
- exit code: `0`
- classification: success
- duration: `60.708 s`

No unrelated runtime maintenance was combined with the restart.

## A1.3 - Post-activation served identity

After the restart and owner-performed connector Refresh, live `capability_identity` converged completely:

- `converged = true`
- source server build hash: `25dff6c0e86fb789726bf4e692a500e5eb08e164b7ff16cdbbf54447b8459a41`
- running server build hash: `25dff6c0e86fb789726bf4e692a500e5eb08e164b7ff16cdbbf54447b8459a41`
- schema hash: `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`
- capability epoch: `25dff6c0e86f-42bdb69d96fb`
- public schema hash: `ca028988d82f73a56d7524fd464bfdda53952b756a4835ac3ff8dc64e5dc0f42`
- public descriptor hash: `7acb65f1c6e3d4b85ea82296bd7d5cec281211c1b5bc00214d3b5b4860106273`
- operation inventory hash: `71fa4cd300e4ac6cb4cfbe15d8bc779149a2e2f523d84f28d7cf65154b440588`
- discovery cache generation: `8823241b8bdb1d2e08ef129a7e33eff5f1554b8ce4fc035425ba94bf004a773f`
- operation schema count: `264`
- public gateway/tool count: `34`
- mismatches: none
- `restart_required = false`
- `connector_refresh_required = false`
- `operation_contract_repair_required = false`
- recommended actions: none

The live operation set contains:

- `repo_preview.resolve_patch`
- operation schema hash: `2fdbe6ae4bb313cc6a406f66b0db46140ee0979fe04a2035a37de14b697a0213`

The live tool discovery metadata for `repo_preview` also advertises explicit managed-patch resolution.

`repo_apply` operation hashes remain unchanged across activation:

- `repo_apply.previewed_change`: `d7278b6dfe8d1384c97c6ba7f57bae29729891715831cae8c95cb27678fa93d5`
- `repo_apply.cleanup`: `5314ca1698120ba743992d4a303441d43af72a9453ea705c6c9dd4ccfc0c26ce`
- `repo_apply.revert`: `0d7f0a49019fa79f273ac302c5f7b9ef350889038e4512c9b7a87f5c5633d8ed`
- `repo_apply.move_file`: `0f9f9576ba2264073afe9f7f959c901680048e318c69d20ec5f55f49620f6697`

Therefore activation added the accepted `repo_preview.resolve_patch` input branch without changing the public `repo_apply` contract.

### Plan count drift

A1.3 in the frozen implementation plan says to verify exactly `32` public tools. That count is stale relative to the repository state accepted before activation.

Both the G4/G8 accepted source baseline and the pre-activation running connector already had `34` public gateways/tools. Patch Auto-Repair adds an operation under the existing `repo_preview` gateway, not a new public gateway.

The correct activation criterion is therefore identity with the accepted source baseline, which is `34` public gateways/tools and `264` operation schemas after activation. Live identity matches that accepted source exactly.

No runtime change was made to force an obsolete count.

## A1.4 - Connector Refresh

The owner performed the connector Refresh after the Soma restart.

Post-Refresh verification proves:

- source/runtime identity convergence;
- live input schema hash equals runtime input schema hash;
- discovery passes converged;
- no restart recommendation remains;
- no connector Refresh recommendation remains;
- no operation-contract repair recommendation remains.

The connector is therefore serving the accepted Patch Auto-Repair public contract.

## A1.5 - Soma and Cloudflare health after restart

Post-restart service/tunnel inspection run:

- `20260815T104654Z_executable_profile_81b05897`
- status: completed
- exit code: `0`

Soma server:

- URL: `http://127.0.0.1:8000/mcp`
- ready: `True`
- readiness HTTP: `406` (route-ready response)
- listener PID: `51352`

Cloudflare tunnel:

- URL: `https://mcp.spaceshipgames.win/mcp`
- ready: `True`
- readiness HTTP: `406`
- protocol: `http2`
- PID: `95312`
- config: `C:\Users\arash\.cloudflared\soma-mcp.yml`
- durable ownership record: `runs/service_logs/soma-mcp-tunnel.identity.json`
- `cloudflared` process count: exactly `1`
- command line includes `tunnel --protocol http2 --config C:\Users\arash\.cloudflared\soma-mcp.yml run`

The source activation did not recreate the prior duplicate-tunnel condition.

## A1.6 - Safe live feature smoke

The smoke used disposable synthetic fixture content only. No Patch Auto-Repair smoke candidate was applied to owner source.

An initial attempt under `runs/...` was rejected by the public repository path policy with `Path is not allowed`. This changed no repository content and confirmed the blocked-path boundary remains active.

A disposable allowed fixture was then created under:

- `tests/_a1_live_smoke_fixture/valid.py`
- `tests/_a1_live_smoke_fixture/incident_b.py`

The fixture was not committed and was deleted after the smoke.

### Normal valid preview

Live preview:

- patch: `20260815T104843Z_patch_0a563f71`
- result: `ok = true`
- `applicable = true`
- candidate validation: `valid`
- `resolution_required = false`
- `repair_available = false`

This proves normal preview behavior remains intact.

### Frozen Incident-B shape

Live malformed preview:

- source patch: `20260815T104851Z_patch_e40ab9e7`
- candidate validation: `regression_detected`
- `applicable = false`
- `resolution_required = true`
- `repair_available = true`
- proposal: `repair_3a943d159bc87408`

The malformed candidate was not applied.

### Live `resolve_patch`

Resolution request:

- `resolution_request_id = a1-live-smoke-20260815-104851`
- decision: `accept_repair`
- exact proposal: `repair_3a943d159bc87408`

Live child result:

- child patch: `20260815T104851Z_patch_eb273037`
- `ok = true`
- `applicable = true`
- candidate validation: `valid`
- `resolution_required = false`
- source patch linkage: `20260815T104851Z_patch_e40ab9e7`
- selected child linkage: `20260815T104851Z_patch_eb273037`
- idempotent replay: `false`

### Source/child status continuity

Source `patch_status` reports:

- status: `resolved`
- role: `source`
- decision: `accept_repair`
- original candidate validation: `regression_detected`
- selected child: `20260815T104851Z_patch_eb273037`

Child `patch_status` reports:

- status: `preview_ok`
- role: `child`
- `applicable = true`
- candidate validation: `valid`
- source patch: `20260815T104851Z_patch_e40ab9e7`
- decision: `accept_repair`

No `repo_apply` call was made. The smoke stopped at the applicable child preview as required for a non-mutating activation proof.

Fixture cleanup run:

- `20260815T104914Z_executable_profile_eed32412`
- exit code: `0`
- marker: `A1_FIXTURE_CLEANUP_OK`

Final worktree inspection confirms the disposable fixture is gone and the pre-existing 43 unrelated untracked canonical-memory/Sol research files remain untouched.

## Final verdict

**LIVE FEATURE ACCEPTED**

Patch Auto-Repair is live and verified.

The served source/runtime identities converge, `repo_preview.resolve_patch` is discoverable with the accepted schema, the connector Refresh is complete, no restart/refresh/repair recommendation remains, normal preview behavior remains intact, Incident B produces a bounded repair proposal, explicit live resolution produces a valid linked child preview, and neither the smoke nor activation applied malformed content to owner source.

Soma and the public Cloudflare route are healthy after restart with exactly one HTTP/2 tunnel process.

Endpoint: live feature accepted; STOP.
