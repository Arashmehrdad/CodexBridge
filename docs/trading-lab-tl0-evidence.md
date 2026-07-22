# Trading Lab TL0 Alpari/MT5 Acceptance Evidence

Status: **complete; accepted on 2026-07-20**.

## Scope and safety

TL0 was executed against the user-established Alpari MetaTrader 5 **demo** account only. The terminal and every Python probe failed closed unless `ACCOUNT_TRADE_MODE_DEMO` was active. No live account, live-money order, credential export, Trading Lab source file, Soma service restart, or Cloudflare restart was used.

The official `MetaTrader5` package was installed only into the repository-owned ignored environment `runs/tl0-mt5-venv`. The tracked worktree remained clean throughout the live spike. No pre-existing `BITCOIN_i` order or position existed before the demo-order gate, and all TL0 positions were closed before terminal restart validation.

## Environment identity

- Repository branch: `feature/domain-tool-gateway-migration`.
- Repository HEAD during the live gate: `1386d5b56b1a865b4d50167a38396fccbb2a7841`.
- Soma server build: `22bf15602aeb0a661666794ab15db66d3427601bc695fe09215d98a550ff4acc`.
- Public schema: `42bdb69d96fb0a4cd66c3d023ce95decfbaa9b4907781041e49f0495248f9888`.
- MT5 terminal executable: `C:\Program Files\MetaTrader 5\terminal64.exe`.
- MT5 terminal build: `5660`.
- Official Python package: `MetaTrader5 5.0.5735` on Python 3.12, with isolated `numpy 2.5.1`.
- Broker server: `Alpari-MT5-Demo`.
- Account mode: demo (`trade_mode = 0`).
- Account margin mode: hedge (`margin_mode = 2`).
- Account currency: `USD`.
- Account leverage: `500`.
- Terminal state: connected, algorithmic trading allowed, external Python API enabled.

The account login was masked in protected output; no password or credential was transmitted through Soma.

## Symbol discovery and contract

A broad Bitcoin discovery query returned both `BITCOIN CASH_i` and `BITCOIN_i`. The first generic probe selected Bitcoin Cash by lexical order, without mutation. The corrected gate selected `BITCOIN_i` explicitly because its broker description is `1 LOT = 1 BITCOIN`.

This is an acceptance finding for TL1: provider discovery must disambiguate Bitcoin from Bitcoin Cash and must not select the first symbol containing `BITCOIN`.

Accepted broker symbol and specification:

- symbol: `BITCOIN_i`;
- path: `Crypto CFD_i\BITCOIN_i`;
- description: `1 LOT = 1 BITCOIN`;
- trade mode: full (`4`), supporting buy and sell;
- order mode: `63`;
- filling capability: `1`; FOK order checks and executions passed;
- digits: `2`;
- point and tick size: `0.01`;
- tick value, profit tick value, and loss tick value: `0.01 USD`;
- contract size: `1 BTC` per lot;
- minimum volume: `0.01` lot;
- volume step: `0.01` lot;
- maximum volume and volume limit: `300` lots;
- stops level: `0`;
- freeze level: `0`;
- base, profit, and margin currency: `USD`;
- swap mode: `5`;
- long swap: `-12.0`;
- short swap: `0.0`.

## Market-data evidence

Read-only gate run `20260720T080543Z_executable_profile_5d3c0879` completed with exit code `0`.

- bid: `64204.67`;
- ask: `64268.91`;
- observed spread: `64.24 USD`;
- retrieved H4 bars: `201`;
- latest completed H4 raw timestamp: `1784520000`;
- latest completed H4 OHLC: `64461.03 / 64953.29 / 64388.46 / 64444.98`;
- developing H4 raw timestamp: `1784534400`;
- developing H4 OHLC at capture: `64444.78 / 64489.03 / 63674.34 / 64204.32`.

The order-check probe measured the raw broker tick timestamp about `10,799.815` seconds ahead of host UTC. TL1 must retain raw provider timestamps and implement explicit provider-time normalization rather than treating every MT5 timestamp representation as identical UTC without validation.

## Buy and sell order checks

Read-only `order_check` run `20260720T080702Z_executable_profile_de6697ba` completed with exit code `0` and accepted both directions at the minimum `0.01` lot.

Buy check:

- price `64226.87`;
- stop-loss `63584.60`;
- take-profit `64869.14`;
- filling `FOK`;
- retcode `0`, comment `Done`;
- calculated margin `1.28 USD`;
- calculated stop outcome `-6.42 USD`;
- calculated target outcome `+6.42 USD`.

Sell check:

- price `64162.67`;
- stop-loss `64804.30`;
- take-profit `63521.04`;
- filling `FOK`;
- retcode `0`, comment `Done`;
- calculated margin `1.28 USD`;
- calculated stop outcome `-6.42 USD`;
- calculated target outcome `+6.42 USD`.

## Demo-order and history evidence

Demo round-trip run `20260720T080902Z_executable_profile_aab32f9c` used magic `72026001`. It verified no pre-existing Bitcoin exposure before mutation, performed one minimum-volume buy and one minimum-volume sell sequentially, closed each immediately, and reconciled position, order, deal, and history surfaces.

Buy lifecycle:

- open order/position `355622662`, deal `314238927`;
- open price `64239.07`;
- stop-loss `63596.68` and take-profit `64881.46` attached to the opening order;
- close order `355622663`, deal `314238928`;
- close price `64174.83`;
- realized P&L `-0.64 USD`.

Sell lifecycle:

- open order/position `355622664`, deal `314238929`;
- open price `64174.85`;
- stop-loss `64816.58` and take-profit `63533.08` attached to the opening order;
- close order `355622665`, deal `314238930`;
- close price `64239.06`;
- realized P&L `-0.64 USD`.

All four sends returned retcode `10009` with `Request executed`. Four matching history orders and four matching history deals were retrieved. Final active `BITCOIN_i` positions and orders were empty, and no cleanup action was required.

The account began the live gate at balance/equity `1000.00 USD` and ended at `998.72 USD`; the `1.28 USD` reduction is the two immediate spread losses. The later experiment cohort must read the actual account equity and currency again at its own start. Neither `1000.00` nor `998.72` may be hard-coded as a permanent baseline.

## Terminal restart and reconnection

Evidence-preserving restart run `20260720T081158Z_executable_profile_aad51a00` completed with exit code `0`.

- old terminal PID: `37432`;
- new terminal PID: `4468`;
- the old process accepted a normal termination signal; force was not required;
- the exact configured terminal executable was relaunched;
- Python reinitialized successfully on the first attempt;
- the same `Alpari-MT5-Demo` account returned automatically;
- balance/equity remained `998.72 USD`;
- post-restart bid/ask: `64170.60 / 64234.81`;
- terminal connected and trading allowed;
- external Python API remained enabled;
- active Bitcoin positions and orders remained zero.

## Durable artifacts

- Isolated package installation: `20260720T080328Z_executable_profile_4a0493b5`; protected stdout SHA-256 `69ce71548ccda5af4049682abaae7514a36fc6c6aa6d3b704c765a2c0ae4040d`; terminal publication hash `260c83e5139d53c419aacf9ac619745a7d00626d63f144477e08bd30174545b9`.
- Corrected symbol/data probe: `20260720T080543Z_executable_profile_5d3c0879`; protected stdout SHA-256 `42290e8c2159be76c00257fc5a0766933fc5f6e21b5d77d8ac783777d81d3c2e`; terminal publication hash `d95bd11d2d5b0ff81134c114edb681e71188aeef2723f1004467a0f6b299d540`.
- Buy/sell order checks: `20260720T080702Z_executable_profile_de6697ba`; protected stdout SHA-256 `ca87e0a250b0201176828831e3860f7c3e6dc079040e88a036abb23d9249fe6f`.
- Demo buy/sell round trip: `20260720T080902Z_executable_profile_aab32f9c`; protected stdout SHA-256 `5aa3f2dfd3886d3e4c342fb30c43d2b47149d46008cabdcda011ca2a0b454df5`.
- Restart/reconnection: `20260720T081158Z_executable_profile_aad51a00`; protected stdout SHA-256 `a1fb7a6311472eb45da3f4285b98d98bb56ad5f15ccda04476d66c28a6644881`; terminal publication hash `c2bfb860a523cfd546643ee5fa7508b5393b81731f4848de0c6d04f78d3504ce`.
- Every listed successful gate emitted empty protected stderr with SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

## Gate decision

TL0 passes. The Alpari demo terminal, official Python integration, exact Bitcoin contract, live bid/ask, H4 history, bidirectional order validation, minimum demo executions, position/order/deal/history retrieval, and restart reconnection have all been proven.

The next roadmap unit is TL1: implement the read-only MT5 adapter with deterministic tests and a live demo-account smoke test. Trading source creation is now permitted, but live-money execution remains unavailable and out of scope.
