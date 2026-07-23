# Trading Lab TL9 - Live-Readiness Review

Review date: 2026-07-23. Scope: whether any live-money execution
capability should exist in Soma Trading Lab. There is no automatic
promotion; this review records the decision and its evidence.

## Decision

**A live-execution tool must not exist.** Live-money execution remains
unavailable and out of scope. The `TradingConfig` model cannot express a
live environment (`account_environment` is the literal `"demo"`), the
demo execution adapter re-verifies the demo account before every order
API call, and no roadmap item may change this without a new explicit
roadmap decision, separate configuration and identity, human approval
boundaries, and independent acceptance evidence.

## Dimension review

- **Broker verification and residency requirements** — not evaluated
  with the broker. Unresolved; blocking on its own.
- **Deposit and withdrawal path** — never exercised; the account is a
  practice account. Unresolved.
- **Minimum practical position** — `BITCOIN_i` minimum volume is `0.01`
  lots (contract size `1.0`), roughly 660 USD notional at observed
  prices. The frozen experiment stakes `1.00 USD` normalized notional
  per trade; live sizing cannot honestly reproduce the tested strategy
  at this account scale. Structural mismatch; blocking.
- **Fees, spread, commission, swaps** — observed demo spread on
  `BITCOIN_i` ran roughly 126-130 points (about 0.19 percent per round
  trip); the TL7 live mirror round trip cost `-1.51 USD` on `0.01` lots
  including spread. Swap and commission schedules were not measured.
  Partially measured; unresolved for live.
- **Broker reliability** — demo-feed observations only (fresh
  sub-second ticks, one boundary-window gap where no developing H4
  candle existed for a short interval, handled fail-closed). No live
  SLA evidence.
- **Regulatory and tax implications** — not assessed; requires human
  counsel. Blocking.
- **Performance on a genuinely fresh paper sample** — none exists. All
  journalled trades to date are deterministic acceptance fixtures and
  live gate probes, not ChatGPT-analysed signals. The threshold
  experiment has produced zero strategy-performance evidence; TL6
  fresh-period reports are ready to measure it once real hourly
  operation accumulates signals. Blocking on its own.
- **Operational recovery evidence** — strong: TL5 restart recovery with
  exactly-once resolution, `AMBIGUOUS_DATA` honesty, TL7 duplicate-free
  broker reconciliation with lost-journal adoption, and the TL8 cycle
  guards (kill switch, disconnected terminal, stale data, packet
  validation) all hold under live and deterministic gates.
- **Should a live tool exist at all** — no. Beyond the unresolved
  items above, the experiment's purpose (confidence-threshold
  calibration) is fully served by virtual portfolios plus the demo
  mirror; a live tool adds risk with no evidentiary benefit.

## Standing requirements for any future reconsideration

1. A new explicit roadmap decision naming live execution.
2. Separate live configuration and account identity that cannot be
   reached from demo settings.
3. Human approval boundaries on every live order path.
4. A genuinely fresh paper sample with stable positive performance
   across neighbouring thresholds and fresh periods (TL6 reports).
5. Resolution of broker verification, residency, deposit/withdrawal,
   fee/swap, minimum-position, regulatory, and tax questions above.
