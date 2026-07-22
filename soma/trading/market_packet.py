from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Callable, Protocol

from .mt5_provider import Candle, ProviderHealth, SymbolSpecification, Tick


UTC = timezone.utc
MIN_COMPLETED_CANDLES = 100
MAX_COMPLETED_CANDLES = 200


class MarketPacketProvider(Protocol):
    def health(self) -> ProviderHealth: ...
    def symbol_specification(self, symbol: str) -> SymbolSpecification: ...
    def latest_tick(self, symbol: str) -> Tick: ...
    def h4_candles(
        self, symbol: str, *, completed_count: int = 200
    ) -> tuple[list[Candle], Candle | None]: ...


@dataclass(frozen=True)
class MarketPacketPayload:
    provider: str
    server: str
    account_environment: str
    symbol: str
    created_at_utc: datetime
    symbol_specification: SymbolSpecification
    latest_tick: Tick
    completed_4h_candles: tuple[Candle, ...]
    developing_4h_candle: Candle
    data_age_seconds: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class MarketPacket:
    packet_id: str
    content_hash: str
    payload: MarketPacketPayload


def _canonical_value(value: object) -> object:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Market packet timestamps must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_packet_bytes(payload: MarketPacketPayload) -> bytes:
    canonical = _canonical_value(asdict(payload))
    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def packet_content_hash(payload: MarketPacketPayload) -> str:
    return sha256(canonical_packet_bytes(payload)).hexdigest()


class MarketPacketBuilder:
    """Build one immutable packet from one connected provider snapshot."""

    def __init__(
        self,
        *,
        provider_name: str = "mt5",
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider_name = provider_name.strip().lower()
        if not self._provider_name:
            raise ValueError("provider_name must not be empty")
        self._now = now or (lambda: datetime.now(UTC))

    def build(
        self,
        provider: MarketPacketProvider,
        symbol: str,
        *,
        completed_count: int = MAX_COMPLETED_CANDLES,
    ) -> MarketPacket:
        if completed_count < MIN_COMPLETED_CANDLES or completed_count > MAX_COMPLETED_CANDLES:
            raise ValueError(
                f"completed_count must be between {MIN_COMPLETED_CANDLES} and {MAX_COMPLETED_CANDLES}"
            )
        created_at = self._now()
        if created_at.tzinfo is None:
            raise ValueError("Market packet creation time must be timezone-aware")
        created_at = created_at.astimezone(UTC)

        health = provider.health()
        if not health.initialized or not health.connected:
            raise RuntimeError("Cannot build market packet from a disconnected provider")
        if health.account_environment != "demo":
            raise RuntimeError("Market packets require a demo account environment")

        specification = provider.symbol_specification(symbol)
        tick = provider.latest_tick(symbol)
        if tick.symbol != symbol or specification.symbol != symbol:
            raise RuntimeError("Provider returned data for a different symbol")
        if not tick.fresh:
            raise RuntimeError("Cannot build market packet from a stale tick")

        completed, developing = provider.h4_candles(
            symbol, completed_count=completed_count
        )
        if len(completed) != completed_count:
            raise RuntimeError(
                f"Expected {completed_count} completed H4 candles; received {len(completed)}"
            )
        if developing is None:
            raise RuntimeError("Provider returned no developing H4 candle")
        if developing.symbol != symbol or any(candle.symbol != symbol for candle in completed):
            raise RuntimeError("Provider returned candle data for a different symbol")
        if any(candle.timeframe != "4H" for candle in (*completed, developing)):
            raise RuntimeError("Provider returned a non-H4 candle")
        completed_times = [candle.open_time.normalized_utc for candle in completed]
        if completed_times != sorted(completed_times) or len(set(completed_times)) != len(completed_times):
            raise RuntimeError("Completed H4 candles must be unique and chronologically ordered")
        if completed_times[-1] >= developing.open_time.normalized_utc:
            raise RuntimeError("Developing H4 candle must follow every completed candle")

        warnings: tuple[str, ...] = ()
        payload = MarketPacketPayload(
            provider=self._provider_name,
            server=health.server,
            account_environment=health.account_environment,
            symbol=symbol,
            created_at_utc=created_at,
            symbol_specification=specification,
            latest_tick=tick,
            completed_4h_candles=tuple(completed),
            developing_4h_candle=developing,
            data_age_seconds=tick.age_seconds,
            warnings=warnings,
        )
        content_hash = packet_content_hash(payload)
        return MarketPacket(
            packet_id=f"mp_{content_hash[:24]}",
            content_hash=content_hash,
            payload=payload,
        )
