from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .market_packet import MarketPacket, MarketPacketBuilder
from .signal_journal import SignalDecision, SignalStatus
from .trade_supervisor import TradingLabSupervisor

UTC = timezone.utc
DEFAULT_RECOVERY_LOOKBACK = timedelta(hours=1)


@dataclass(frozen=True)
class CycleReport:
    started_at_utc: datetime
    proceeded: bool
    refusal_reason: str
    packet_id: str | None
    packet_hash: str | None
    entered_signal_ids: tuple[str, ...]
    skipped_signal_ids: tuple[str, ...]
    resolved_position_ids: tuple[str, ...]
    open_position_count: int


class HourlyOrchestrator:
    """TL8 hourly cycle scaffolding around the deterministic components.

    One cycle builds one immutable market packet, enters any submitted
    packet-bound trade signals through the TL5 supervisor, and runs one
    monitoring pass with downtime recovery. Analysis stays outside Soma:
    the cycle never invents a signal, and it refuses to trade — while
    still recovering existing open work — when trading is disabled, the
    terminal is disconnected, the account is not demo, market data is
    stale, or packet validation fails.
    """

    def __init__(
        self,
        *,
        supervisor: TradingLabSupervisor,
        packet_builder: MarketPacketBuilder | None = None,
    ) -> None:
        self.supervisor = supervisor
        self.packet_builder = packet_builder or MarketPacketBuilder()

    def run_cycle(
        self,
        provider,
        *,
        symbol: str,
        enabled: bool,
        now: datetime,
        recovery_lookback: timedelta = DEFAULT_RECOVERY_LOOKBACK,
        completed_count: int = 200,
    ) -> CycleReport:
        started = now.astimezone(UTC)
        refusal = ""
        packet: MarketPacket | None = None

        if not enabled:
            refusal = "trading is disabled by the kill switch"
        else:
            health = provider.health()
            if not health.initialized or not health.connected:
                refusal = "terminal is disconnected"
            elif health.account_environment != "demo":
                refusal = "account is not a demo account"
            else:
                try:
                    packet = self.packet_builder.build(
                        provider, symbol, completed_count=completed_count
                    )
                except Exception as exc:
                    refusal = f"market packet validation failed: {exc}"
                else:
                    if not packet.payload.latest_tick.fresh:
                        refusal = "market data is stale"
                        packet = None

        entered: list[str] = []
        skipped: list[str] = []
        if refusal == "" and packet is not None:
            for record in self.supervisor.signals.list(limit=1000):
                if record.status is not SignalStatus.SUBMITTED:
                    continue
                if record.draft.decision is SignalDecision.NO_TRADE:
                    skipped.append(record.signal_id)
                    continue
                if record.draft.symbol != symbol:
                    skipped.append(record.signal_id)
                    continue
                try:
                    report = self.supervisor.enter_signal(
                        record.signal_id, now=started
                    )
                except Exception:
                    skipped.append(record.signal_id)
                    continue
                if report.entered_thresholds:
                    entered.append(record.signal_id)
                else:
                    skipped.append(record.signal_id)

        # Monitoring and recovery always run for existing open work as
        # long as a connected demo provider is available; a refused cycle
        # must not strand open positions.
        resolved: list[str] = []
        can_monitor = refusal in (
            "",
            "market data is stale",
            "trading is disabled by the kill switch",
        )
        if can_monitor:
            health = provider.health()
            if (
                health.initialized
                and health.connected
                and health.account_environment == "demo"
                and self.supervisor.open_positions()
            ):
                recovered = self.supervisor.recover_from_provider(
                    provider,
                    symbol=symbol,
                    start_utc=started - recovery_lookback,
                    end_utc=started,
                )
                resolved.extend(p.position_id for p in recovered)
                tick = provider.latest_tick(symbol)
                for outcome in self.supervisor.observe_tick(
                    symbol=symbol,
                    bid=tick.bid,
                    ask=tick.ask,
                    observed_at_utc=started,
                ):
                    resolved.append(outcome.position_id)

        return CycleReport(
            started_at_utc=started,
            proceeded=refusal == "",
            refusal_reason=refusal,
            packet_id=packet.packet_id if packet else None,
            packet_hash=packet.content_hash if packet else None,
            entered_signal_ids=tuple(entered),
            skipped_signal_ids=tuple(skipped),
            resolved_position_ids=tuple(dict.fromkeys(resolved)),
            open_position_count=len(self.supervisor.open_positions()),
        )
