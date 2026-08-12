# G5 CLI Provider Route Amendment - 2026-08-12

STATUS: ACTIVE_OWNER_DIRECTION

## Scope

This amendment changes only the executable G5 provider-pilot route. It does not rewrite the canonical G1-G4 architecture or invalidate their accepted evidence.

Canonical plan remains:

`docs/agent-worker-research/AGENT_WORKER_IMPLEMENTATION_PLAN_2026-08-12.md`

Canonical plan SHA-256 remains:

`fa2afb72e51e5cc4494f29b7470eb33cd8a951144a2bc78db5e65a6d8301bea2`

G4 accepted at:

`53b317f9b7e6c169a5d87e1418c2d34b5910f86d`

Original API preflight remains historical evidence at:

`docs/agent-worker-research/G5_OAI_R1_PROVIDER_PILOT_PREFLIGHT_2026-08-12.md`

## Owner constraint

On 2026-08-12 the owner stated that no OpenAI API credential is available and there is no intent to purchase API usage, while explicitly permitting use of the already-authenticated CLI route.

Therefore:

- no `OPENAI_API_KEY` is required or sought;
- no OpenAI API billing account or API credit is purchased;
- OAI-R1 Responses API, OAI-R2 Responses Multi-agent, and OAI-A1 API/SDK pilots are `NOT_APPLICABLE_OWNER_NO_API` in this implementation run;
- those pilots remain research references, not assumed capabilities;
- their unmeasured API-only properties must not be projected onto the selected CLI backend;
- CDX-R1 becomes the first executable real-provider gate.

This is an owner/environment constraint, not a failure of the frozen provider-neutral architecture.

## Real provider pilot selected

Pilot identity:

`CDX-R1`

Provider route:

`Soma -> local Codex App Server stdio JSON-RPC -> ChatGPT-managed Codex authentication`

Installed Codex CLI:

`codex-cli 0.145.0`

Resolved command observed through Soma:

`C:\Users\arash\AppData\Roaming\npm\codex.ps1`

Authentication observation:

`codex login status` -> `Logged in using ChatGPT`

Official App Server documentation confirms ChatGPT-managed authentication is a supported/recommended mode and exposes `account/read`, `account/rateLimits/read`, `thread/start`, `thread/resume`, `thread/read`, `thread/fork`, `turn/start`, and `turn/interrupt` over the App Server JSON-RPC surface.

## Spend and quota boundary

API spend ceiling:

`USD 0.00`

No API-key request is permitted.

Real Codex model-turn ceiling for CDX-R1:

`4 turns maximum`

The turn ceiling bounds subscription/Codex quota consumption even though no API-dollar accounting exists on this route.

Thread creation, local authentication inspection, schema generation, and read-only thread metadata operations that do not invoke a model do not consume the four-turn model budget.

No automatic retry may create another model turn merely because an acknowledgement or connection was lost.

## Read-only authority

CDX-R1 is read-only:

- App Server thread/turn sandbox policy: `readOnly`;
- approval policy: `never` where accepted by the installed protocol;
- no dynamic tools;
- no MCP;
- no apps/plugins;
- no shell/write permission grants;
- no protected broker access;
- no external mutation authority;
- synthetic committed assignment bytes only.

If Codex asks for a server-side approval despite the declared read-only contract, the pilot client declines/cancels the request and records the event.

## Protocol identity freeze

Installed `codex-cli 0.145.0` generated 273 JSON schema files through:

`codex app-server generate-json-schema`

Raw generated JSON bytes are not used as the protocol identity because repeated generation showed serialization-level raw-byte variance in at least one bundle despite the same installed CLI version.

The accepted drift identity canonicalizes every generated JSON file with sorted object keys and compact JSON serialization, hashes each canonical file, sorts by relative path, then hashes the complete `path=sha256` manifest.

Two independent generations produced the same canonical protocol-manifest SHA-256:

`de45a8da2cd3e32ed35a137609396cd9aa84190e40c4943d44f17ef7613c8bda`

CDX-R1 must record both CLI version and this canonical schema-manifest hash before any model turn. A mismatch is protocol drift and stops promotion until reviewed.

### Reviewed same-version protocol drift before first real turn

After the later Soma restart/connector refresh and before any CDX-R1 model turn, the pilot preflight correctly stopped on protocol drift. The installed package still reported `@openai/codex@0.145.0`, but fresh App Server schema generation produced a different canonical manifest.

Observed installed wrapper:

`C:\\Users\\arash\\AppData\\Roaming\\npm\\codex.ps1`

Observed wrapper SHA-256:

`0c149db80ed0bf442c810146b0ad0163b74982fe4542d673f56c354d7b8229cb`

Two additional independent 273-file schema generations produced the same new canonical protocol-manifest SHA-256:

`dcc92e96e856b1d4f93548f7f8f73e26aa87766431a0e44ceb23049c58c0dcbc`

The failed pilot attempt stopped in preflight before thread/turn creation, so it consumed zero model turns. The new hash is therefore the reviewed executable CDX-R1 protocol freeze for the first real provider turn. The earlier `de45a8da...` value remains historical drift evidence and is not treated as current.

## CDX-R1 measurements

The pilot measures:

1. App Server initialize/auth identity without exposing auth tokens;
2. exact root thread ID returned by `thread/start`;
3. exact turn ID returned by `turn/start`;
4. `clientUserMessageId` correlation when supplied;
5. `turn/started`, item lifecycle, `turn/completed`, raw status and token-usage evidence;
6. strict turn `outputSchema` behavior;
7. restart reconstruction using a new App Server process plus `thread/read`/`thread/resume` on the exact known thread ID;
8. provider-local fork/thread lineage where exposed;
9. cancellation with `turn/interrupt` and final interrupted/completed race evidence;
10. create/ack uncertainty: a sent thread/turn request never causes blind duplicate creation when its provider identity was not durably captured;
11. compact provider provenance refs/hashes suitable for Soma evidence;
12. whether exact provider-native child lineage is available without granting canonical authority to provider children.

## Recovery rules

Known thread ID:

- restart App Server client/process;
- read/resume the exact recorded thread ID;
- never use `resume --last` or fuzzy lookup;
- recover exact turn/history evidence from the provider-local thread.

Unknown `thread/start` outcome:

- mark provider create outcome uncertain;
- do not start a replacement thread automatically;
- do not guess identity from timestamps/content.

Known thread ID but unknown `turn/start` acknowledgement:

- use the exact deterministic `clientUserMessageId` plus provider thread history to reconcile when possible;
- if exact reconciliation is impossible, remain uncertain;
- never issue another model turn automatically.

Cancellation:

- interrupt only an exact `(threadId, turnId)` pair;
- replay of the same canonical cancel must not require a second provider side effect after terminal evidence is known;
- completion winning the interrupt race is measured, not rewritten as cancellation.

## Downstream plan effect

G5 sequence for this run is:

1. G5.0 original API preflight - historical/superseded by owner constraint;
2. G5 CLI amendment - this document;
3. CDX-R1 App Server durability/provenance/read-only pilot;
4. G5.6 provider selection using measured CDX-R1 evidence;
5. G6 frozen C1/C2/C4/C8 benchmark if CDX-R1 is promoted;
6. G7 provider-native subagent benchmark only to the extent the selected Codex route exposes measurable native child topology.

OAI-R3 combined Responses Multi-agent/background remains `UNMEASURED_NOT_APPLICABLE_OWNER_NO_API` and must not be assumed by production recovery logic.

The definition-of-done requirement for a real reasoning backend remains unchanged: one real backend must pass measured durability, evidence, cancellation, read-only isolation, and uncertainty handling before G6.

## Authorization

The owner's instruction to use the CLI route is the authorization for this bounded CDX-R1 pilot under:

- ChatGPT-managed existing login only;
- USD 0.00 API spend;
- at most four real Codex model turns;
- read-only synthetic input;
- no external/protected mutation.

Any API-key route, paid API use, higher turn ceiling, or mutation/tool authority requires new explicit owner direction.
