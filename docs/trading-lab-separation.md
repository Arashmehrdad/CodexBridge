# Trading Lab separation: achievement record and migration evidence

The Trading Lab was built inside Soma, matured there, and has now been
extracted into its own repository and Python package. Soma keeps the public
MCP gateways and the durable-execution machinery; the trading domain and its
state belong to `trading-lab`.

This document is the permanent record. It preserves what the in-tree Trading
Lab achieved, where each behavior went, and the evidence that justified
deleting the original implementation.

- **TradingLab repository:** `D:\Github\TradingLab` (`trading-lab`, namespace
  `trading_lab`, Apache-2.0)
- **Soma branch at cutover:** `feature/domain-tool-gateway-migration`
- **Historical evidence, unchanged:**
  [`trading-lab-tl0-evidence.md`](trading-lab-tl0-evidence.md),
  [`trading-lab-redesign-evidence.md`](trading-lab-redesign-evidence.md),
  [`trading-lab-tl9-live-readiness-review.md`](trading-lab-tl9-live-readiness-review.md)

## What the in-tree Trading Lab established

These are the design decisions the internal implementation proved out. All of
them moved intact; none were revisited during extraction.

| Achievement | Where it lives now |
| --- | --- |
| **Read-only MT5 access** with explicit broker-UTC offset handling, so raw broker epochs are always retained and normalization is never retroactive | `trading_lab.mt5_provider` |
| **Broker-time normalization**: offset detected from several fresh ticks on connect, H4 boundaries computed in broker time | `trading_lab.broker_time` |
| **Immutable, content-hashed market packets** — the model never supplies market facts, it references a stored packet | `trading_lab.market_packet`, `trading_lab.packet_store` |
| **Deterministic charts rendered from the packet alone**, with no provider access at render time | `trading_lab.market_chart` |
| **Packet-bound signal journal (v2)** with durable rejection records, idempotent submission, and content hashing | `trading_lab.signal_journal_v2` |
| **Independent outcome resolution** from retained ticks, per signal, rather than a running virtual portfolio | `trading_lab.outcome_resolver` |
| **Retained tick archive** with range hashing, gap detection, and daily archives | `trading_lab.tick_archive` |
| **Deterministic offline replay and threshold sweeps** — the decision to remove runtime threshold portfolios entirely | `trading_lab.replay_engine` |
| **Calibration and replay reports** versioned by the component that produced them | `trading_lab.lab_reports`, `trading_lab.versions` |
| **Capability roles separated from strategy policies**: the gateway exposes the full guarded surface, the policy decides what a strategy may use | `trading_lab.strategy_policy` |
| **Structurally impossible live execution** — `ExecutionMode` has only `internal_paper` and `broker_demo`, and no `live` member can be constructed | `trading_lab.strategy_policy` |
| **Guarded action gateway**: validation, policy, fresh price, normalization, risk, margin, `order_check`, idempotent durable submission, broker reconciliation | `trading_lab.action_gateway`, `trading_lab.executors` |
| **Kill switch and safety limits** as durable state, not process state | `trading_lab.safety` |
| **Supervised runtime** where each step runs in its own failure boundary | `trading_lab.trading_runtime` |

## Final architecture

```
Soma
  public MCP gateways (trading_query, trading_action_submit, trading_signal_*,
                       trading_runtime_control)
  durable execution, evidence, run identity
  configuration and provider identity
  compact public projection and response budgets
  soma/trading_lab_adapter.py   <-- the only seam
            |
            v
trading_lab package
  MT5 integration, domain models, journals and stores,
  signals and outcomes, runtime control, actions and executors,
  reports, charts, replay, packets
```

The dependency arrow is one-directional and enforced by a test:
`trading_lab` must never import `soma`; Soma reaches `trading_lab` only
through the adapter. There is no MCP hop between them — the boundary is an
ordinary in-process Python package boundary.

## What moved, and what stayed

**Removed from Soma** (`soma/trading/`, 17 modules): `action_gateway`,
`broker_time`, `executors`, `lab_reports`, `market_chart`, `market_packet`,
`mt5_provider`, `outcome_resolver`, `packet_store`, `replay_engine`, `safety`,
`signal_journal_v2`, `strategy_policy`, `tick_archive`, `trading_runtime`,
`versions`, and the package `__init__`.

**Kept in Soma**, because they are host concerns:

| Concern | Module |
| --- | --- |
| Public tool registration, compact projection, response budgets | `soma/server.py` |
| Request models, discriminated unions, flat input schemas | `soma/gateway_models.py` |
| `TradingConfig` and YAML loading | `soma/config.py` |
| Domain serialization for transport (`_trading_json`) | `soma/server.py` |
| The seam itself | `soma/trading_lab_adapter.py` |

## The adapter

`soma/trading_lab_adapter.py` does exactly four things:

1. maps `TradingConfig` + `resolve_runs_dir()` onto `TradingLabSettings` and
   `TradingLabPaths`;
2. constructs `TradingLabServices` lazily, cached by resolved settings so the
   paper executor's in-memory positions stay stable within one configuration;
3. preserves MT5 provider injection and the paper quote/rules sources;
4. re-exports the domain names the gateways refer to.

It holds no trading logic and creates no parallel stores.

## State compatibility

The cutover did not fork state. Every database stays exactly where it was:

| File | Path |
| --- | --- |
| Market packets | `<runs_dir>/trading/packets.sqlite3` |
| Signals | `<runs_dir>/trading/signals.sqlite3` |
| Outcomes | `<runs_dir>/trading/outcomes.sqlite3` |
| Ticks | `<runs_dir>/trading/ticks.sqlite3` |
| Tick archives | `<runs_dir>/trading/tick_archives/` |
| Actions | `<runs_dir>/trading/actions.sqlite3` |
| Safety | `<runs_dir>/trading/safety.sqlite3` |
| Runtime | `<runs_dir>/trading/runtime.sqlite3` |

`TradingLabPaths` derives all of them from one root, and
`tests/test_trading_lab_gateway.py::TestStateCompatibility` asserts each path
matches the pre-migration layout.

## Configuration

`TradingConfig` is unchanged — no field was added, removed, or renamed, so
existing `config.yaml` files keep working untouched. The adapter maps it
field-for-field onto `TradingLabSettings`.

`trading-lab` is registered as a Soma-managed repository through the normal
repository configuration path. The absolute checkout path is owner-local
(`config.yaml`, which is git-ignored); `config.example.yaml` documents the
generic form with a relative sibling path.

If the package is missing or incompatible, `soma.server` fails to import with
the underlying error, and `system_query{"operation":"self_check"}` reports the
`trading_lab` check as not ok. There is no silent fallback: after this
migration there is nothing to fall back to.

## Equivalence evidence

The cutover was justified before it happened, by two independent proofs.

### 1. Domain equivalence

`tests/test_trading_lab_equivalence.py` ran every domain scenario twice —
once through `soma.trading`, once through `trading_lab` — against isolated
temporary databases, and compared the serialized results.

- **54 tests, all passing** at the time of cutover.
- Covered: provider models, redacted health, broker-offset detection, H4
  boundaries, packet build/store/list, chart bytes, signal submit/get/list/
  cancel/reject/idempotency, outcome resolution (TP, SL, data gap), the
  outcome journal, calibration and replay reports, the replay engine and
  threshold sweeps, tick ingest/range-hash/gap-detection/daily archives, the
  action gateway across **all 27 action types**, policy and role refusals, the
  kill switch, runtime start/status/stop, safety limits, strategy policies,
  and the version table.
- Comparison was exact byte equality on canonical JSON. The only exemptions
  were five wall-clock fields — `created_at_utc`, `inserted_at_utc`,
  `occurred_at_utc`, `requested_at_utc`, `updated_at_utc` — which were
  checked semantically (both sides must produce a well-formed UTC instant)
  and then normalized.
- It also asserted **source-level byte identity** for all 16 shared modules,
  so the two implementations could not silently diverge while the test
  existed.

This file was migration scaffolding: it cannot run once `soma/trading` is
gone. It is recoverable from the commit that introduced the adapter.

### 2. Gateway equivalence

`tests/test_trading_lab_gateway.py` drives Soma's real gateway functions
against isolated state and a deterministic fake MT5 provider. During the
migration the adapter carried a `SOMA_TRADING_BACKEND` switch (`legacy` |
`package`), and the whole trading gateway suite was run under both:

| Backend | Result |
| --- | --- |
| `legacy` (`soma.trading`) | 251 passed, 7 skipped |
| `package` (`trading_lab`) | 255 passed, 3 skipped |

The four-test difference is exactly `TestBackendIdentity`, which asserts the
resolved backend *is* the package and therefore skips under rollback. Every
behavioral test passed identically under both implementations.

The switch was removed together with `soma/trading`: with one implementation
there is nothing to select, and a permanent flag that can only take one value
is dead code.

## Tests

| Where | What |
| --- | --- |
| **TradingLab** | All domain detail: 224 tests covering models, stores, journals, resolution, replay, reports, the action gateway, the service contract, and the package boundary. Plus 3 MT5-marked tests that skip when the binding is absent. |
| **Soma** | `tests/test_trading_lab_gateway.py`: the public trading contract — operation inventories, envelopes, compact/full views, budgets, error classifications, deprecation responses, and state-path compatibility. |

The 14 detailed trading test modules and `trading_lab_fixtures.py` were
removed from Soma; their content lives in TradingLab, where the code they
test lives.

Completeness is gated, not assumed: the gateway tests iterate
`READ_OPERATIONS`, `JOURNAL_QUERY_OPERATIONS`, `SIGNAL_OPERATIONS`,
`RUNTIME_CONTROL_OPERATIONS`, `ACTION_OPERATIONS`, and
`DEPRECATED_QUERY_OPERATIONS` from `trading_lab.service`, so an operation that
exists but is not served fails the suite.

## Installation

Development (editable, immediate):

```
pwsh -File scripts/install_trading_lab_dev.ps1
```

Reproducible (commit-verified, hash-pinned wheel):

```
pwsh -File scripts/install_trading_lab_pinned.ps1 -ExpectedCommit <sha> -ExpectedSha256 <hash>
```

The pinned script refuses to build from a dirty or unexpected checkout,
records version/commit/wheel SHA-256, installs the exact wheel with
`--no-deps`, and stamps the installed package so
`system_query{"operation":"self_check"}` can report the source commit.

Neither script contains an absolute path: both default to a TradingLab
checkout sitting next to the Soma checkout.

## Live verification

Performed against the running service after restart, with no active runs and
no repository locks. Build identity moved `26b9669c` → `7dca2da1`, and the
public contract hashes did not move at all:

| Hash | Before | After |
| --- | --- | --- |
| `public_schema_hash` | `51ef7e47414c…` | `51ef7e47414c…` |
| `live_input_schema_hash` | `e41306ade572…` | `e41306ade572…` |
| `operation_inventory_hash` | `695c6780f854…` | `695c6780f854…` |
| `operation_schema_count` | 194 | 194 |
| `operation_inventory_gateway_count` | 29 | 29 |

That is the direct evidence that the migration changed no public schema.

`trading-lab` resolves as a managed repository independently of Soma:
`run_query{"operation":"preflight","repo_name":"trading-lab"}` and
`repo_query{"operation":"status","repo_name":"trading-lab"}` both return
`available`, on branch `main`, with its own commit history.

Trading is disabled in owner-local configuration. It was enabled temporarily
for this verification and then restored exactly, along with removing the empty
first-use databases it created. With it enabled, against the real Alpari MT5
demo account:

| Operation | Live result |
| --- | --- |
| `health` | connected, `account_environment: demo` |
| `symbols` | `BITCOIN_i`, "1 LOT = 1 BITCOIN" |
| `specification` | digits 2, volume step 0.01, min 0.01, max 300 |
| `tick` | live bid/ask with normalized UTC and `fresh: true` |
| `h4_candles` | three completed broker-time H4 candles |
| `historical_ticks` | real ticks, budget enforced (`truncated: true` at 2048 bytes) |
| `runtime_status`, `action_list`, `market_packet_list`, `outcome_list`, `rejection_list`, `calibration_report`, `replay_report`, `demo_performance`, `reconciliation_report` | all served from the package |
| `trading_signal_list`, `trading_runtime_control{status}` | served |
| `portfolio_status` | deprecation notice preserved verbatim |

Transport equivalence was checked live across all seven trading tools and
eighteen calls:

- every tool advertises a flat public input schema — `trading_query` with 20
  discriminated branches — and **no branch exposes a `request` property**;
- `content[0].text` is non-empty JSON on every call;
- `json.loads(content[0].text) == structuredContent` on every call;
- **no `soma.trading` module was loaded at runtime**; 18 `trading_lab`
  modules were;
- `soma/trading` does not exist on disk.

No financial trade was executed. Every live call was a read or a
journal query.

One transient result is worth recording: two journal reads issued
concurrently against a brand-new trading directory returned
`{"status": "journal_error", "error": "database is locked"}` while several
SQLite schemas were being created at once, and succeeded immediately on
retry. This is a property of the per-call store construction, which the
migration preserved unchanged; it is not a regression.

### Installation, verified

```
pwsh -File scripts/install_trading_lab_dev.ps1
```
→ `editable: true`, module resolved to `D:\Github\TradingLab\src\trading_lab`.

```
pwsh -File scripts/install_trading_lab_pinned.ps1
```
→ built from commit `46f89bba88cf1e286ef29f804dd12d1f741869b9`, wheel
`trading_lab-0.2.0-py3-none-any.whl`, SHA-256
`fab4796380b3d67dbaec82dafbdeea9fd3732d9fcd1fa1530302bbe194672d8b`,
installed with `--no-deps`, diagnostics reporting `editable: false` and the
source commit. The full gateway suite passed against that non-editable
install (117 passed, 3 skipped). Passing a wrong `-ExpectedSha256` is
refused before installation.

## Known pre-existing failures

Two Soma test failures predate this work and are unrelated to it. Both were
confirmed to fail identically at `756c98f`, the commit this migration started
from:

- `tests/test_mcp_flat_input_contract.py::test_invalid_flat_payloads_are_rejected`
  — 8 parametrizations for `run_query`, `repo_query`, and `repo_apply`, where
  a Pydantic validation error still carries the internal `request.` prefix.
  No trading gateway is involved.
- `tests/test_chat_footprint_acceptance.py::test_projection_overhead_and_full_retrieval_performance`
  — a wall-clock timing comparison that is sensitive to machine load.

They are recorded here so they are not mistaken for migration damage.
