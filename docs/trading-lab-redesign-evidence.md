# Trading Lab Redesign Acceptance Evidence

Status: **accepted on 2026-07-23**. Demo-only; zero broker orders were sent
during acceptance and live execution is structurally impossible.

## Scope

This bundle covers the Trading Lab redesign migration that replaced the
runtime T50–T99 threshold portfolios with an immutable packet-bound signal
journal, independent per-signal outcome resolution from retained ticks,
deterministic offline replay, a guarded action gateway, and a durable
runtime with decoupled supervision.

## Migration commits

| Commit | Batch |
| --- | --- |
| `cda2479` | Broker-time detection and the immutable market-packet store |
| `b062436` | Packet-bound immutable v2 signal journal with rejection records |
| `8d5a4ca` | Durable tick retention and independent outcome resolution |
| `80b1d46` | Deterministic offline replay engine and the two lab reports |
| `d48c781` | Strategy policies, safety controls, and the guarded action gateway |
| `abbd91d` | Durable trading runtime with decoupled supervision |
| `84e42c7` | Public Trading Lab gateway surface migration |
| `9e1f888` | Removal of the legacy runtime threshold-portfolio code |

## Audit defects and their regressions

1. **Packet-bound submission** — signals derive symbol, bid/ask,
   timestamps, packet hash, and parent H4 identity from the stored packet;
   unknown/stale/tampered packet bindings are rejected with durable
   records, and the hourly cycle enters only signals bound to their exact
   packet inside the age window
   (`tests/test_signal_journal_v2.py`, `tests/test_trading_runtime.py::test_entry_is_bound_to_the_exact_packet_and_age_window`).
2. **No pre-entry observations** — resolution excludes every tick/candle
   earlier than the signal entry time and processes chronologically
   (`tests/test_outcome_resolver.py::test_pre_entry_observations_are_never_used`,
   `test_range_fallback_is_conservative`).
3. **Supervision decoupled from analysis** — tick ingestion, outcome
   resolution, reconciliation, and standing-policy supervision continue
   when H4/specification/packet construction fail
   (`tests/test_trading_runtime.py::test_supervision_continues_when_analysis_and_h4_fail`).
4. **Duplicate exposure** — entry actions for an already-exposed symbol are
   refused unless the strategy allows stacking; experiment transitions
   cannot bypass the rule
   (`tests/test_action_gateway.py::test_duplicate_exposure_is_refused_across_experiments`).
5. **Report semantics** — resolution-basis periods include positions opened
   before but resolved within the period; experiments are selected
   explicitly; journals paginate with explicit totals instead of a silent
   1,000-record cap
   (`tests/test_lab_reports.py`, `tests/test_signal_journal_v2.py::test_paginated_listing_and_parent_h4_grouping`).
6. **Runtime wiring** — durable start/stop/status/recovery, crash-window
   action reconciliation, restart-surviving trailing supervisors, and the
   public `trading_runtime_control`/`trading_action_submit` tools replace
   library-only acceptance
   (`tests/test_trading_runtime.py`, `tests/test_mcp_action_discovery.py`).

## Deterministic validation

- Focused suites: broker time (5), packet store (5), signal journal v2
  (10), tick archive (6), outcome resolver (8), replay engine (7), lab
  reports (5), action gateway (12), demo executor (5), safety (4),
  trading runtime (7) — all passing.
- Full suite after legacy removal: **1,567 tests, 0 failures** (3 initial
  failures were one stale legacy-journal fake and a pre-existing editable
  install still pointing at the pre-rename repository path; both
  repaired in `9e1f888`).
- `git diff --check`: clean.

## Live demo acceptance (read-only, 2026-07-23T17:06Z)

Run through the repository-owned `.venv\Scripts\python.exe`
(`MetaTrader5 5.0.5735`) against the auto-launched Alpari MT5 demo
terminal. Full JSON retained beside this document's history in the
migration branch; summary:

- Connected demo account `Alpari-MT5-Demo`, balance/equity `997.21 USD`,
  login redacted in all output.
- Broker UTC offset **detected** from 4 fresh ticks as `+10800 s` with
  `2.0 s` maximum deviation — never hard-coded; the first launch attempt
  correctly failed closed on a stale warming-up feed.
- `BITCOIN_i` rules re-read live via `symbol_info()`: digits 2, tick size
  0.01, contract 1.0, minimum volume 0.01, step 0.01.
- Immutable packet `mp_9b247d3c16842178e6710abb` stored with raw tick
  epoch `1784837202`, offset `10800`, normalized `17:06:42Z`, and parent
  H4 broker boundary `1784836800` (broker 20:00 → `17:00:00Z`).
- Packet-bound LONG derived its entry from the stored packet ask
  `64773.87`; NO_TRADE accepted; a submission naming an unknown packet was
  rejected and persisted as `sigrej_2a0d2421401559052e29edba`.
- Runtime `analysis_pass` entered the LONG through the guarded gateway in
  `internal_paper` mode and skipped NO_TRADE; `supervision_pass` ran all
  seven steps green (offset detection, symbol-rule refresh, tick
  ingestion, outcome resolution, action reconciliation, trailing and
  standing-exit supervision).
- Tick retention: **3,471 live ticks** over the 30-minute window, range
  hash `a86067e6…bffc383`, zero coverage gaps.
- The entered signal's outcome is honestly `UNRESOLVED_DATA_GAP`
  (`coverage_ended_without_boundary`) with entry-tick evidence at
  `64772.37` — no favourable guess was made.
- `broker_orders_sent: 0`.

## Explicit safety confirmation

- `ExecutionMode` contains only `internal_paper` and `broker_demo`;
  constructing `live` raises. No configuration field, gateway model
  literal, policy, or tool can express live execution.
- The demo executor re-verifies `ACCOUNT_TRADE_MODE_DEMO` before every
  call; the model can never reach `MetaTrader5.order_send()` — only
  gateway-owned executors touch broker APIs after the full pipeline.
- The durable kill switch, allowed-symbol set, stale-price, spread,
  exposure, volume, action-rate, and daily-loss limits gate every action;
  emergency close-all remains available while paused.

## Known limitations / remaining blockers

- No live broker-demo **order** has been sent through the new
  `DemoExecutor` yet (acceptance was deliberately read-only + paper). The
  first guarded demo order through `trading_action_submit` should be a
  supervised, explicitly requested step.
- The replay and calibration reports have no genuinely fresh analysed
  sample yet — every journalled signal so far is acceptance evidence.
- `condition_exit`/`news_exit` supervision evaluates price conditions and
  deadlines; a real news feed integration does not exist and is recorded
  honestly as out of scope.
- The paper executor's open positions are per-process; restart recovery
  for paper mode records crash-window actions as FAILED honestly rather
  than adopting them.
