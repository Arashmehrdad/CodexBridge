from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import ModuleType
from typing import Any, Callable, Protocol


UTC = timezone.utc
H4_SECONDS = 4 * 60 * 60


class MT5Binding(Protocol):
    TIMEFRAME_H4: int
    COPY_TICKS_ALL: int

    def initialize(self, *args: Any, **kwargs: Any) -> bool: ...
    def shutdown(self) -> None: ...
    def last_error(self) -> Any: ...
    def terminal_info(self) -> Any: ...
    def account_info(self) -> Any: ...
    def symbols_get(self, *args: Any, **kwargs: Any) -> Any: ...
    def symbol_select(self, symbol: str, enable: bool) -> bool: ...
    def symbol_info(self, symbol: str) -> Any: ...
    def symbol_info_tick(self, symbol: str) -> Any: ...
    def copy_rates_from_pos(self, symbol: str, timeframe: int, start: int, count: int) -> Any: ...
    def copy_ticks_range(self, symbol: str, start: datetime, end: datetime, flags: int) -> Any: ...


@dataclass(frozen=True)
class ProviderTimestamp:
    raw_epoch_seconds: int
    provider_utc_offset_seconds: int
    normalized_utc: datetime


@dataclass(frozen=True)
class ProviderHealth:
    initialized: bool
    connected: bool
    account_environment: str
    server: str
    login: int | None
    currency: str
    balance: float | None
    equity: float | None
    last_error: tuple[Any, ...]


@dataclass(frozen=True)
class SymbolSummary:
    name: str
    description: str
    path: str
    visible: bool


@dataclass(frozen=True)
class SymbolSpecification:
    symbol: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    contract_size: float
    minimum_volume: float
    maximum_volume: float
    volume_step: float
    trade_mode: int
    order_mode: int
    margin_initial: float
    margin_maintenance: float
    currency_base: str
    currency_profit: str
    currency_margin: str


@dataclass(frozen=True)
class Tick:
    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    timestamp: ProviderTimestamp
    age_seconds: float
    fresh: bool


@dataclass(frozen=True)
class Candle:
    symbol: str
    timeframe: str
    open_time: ProviderTimestamp
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    spread: int
    real_volume: int


@dataclass(frozen=True)
class HistoricalTick:
    symbol: str
    bid: float
    ask: float
    last: float
    volume: float
    flags: int
    timestamp: ProviderTimestamp


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    dtype = getattr(value, "dtype", None)
    names = getattr(dtype, "names", None)
    if names and name in names:
        return value[name]
    return getattr(value, name, default)


def _rows(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value)


class MT5Provider:
    """Read-only MetaTrader 5 provider adapter.

    ``provider_utc_offset_seconds`` is explicit because some broker feeds expose
    wall-clock epochs in broker time. Raw epochs are always retained, while
    normalized UTC subtracts the configured offset.
    """

    def __init__(
        self,
        *,
        binding: MT5Binding | ModuleType | None = None,
        terminal_path: str | None = None,
        provider_utc_offset_seconds: int = 0,
        now: Callable[[], datetime] | None = None,
        maximum_tick_age_seconds: int = 120,
    ) -> None:
        if binding is None:
            import MetaTrader5 as binding  # type: ignore[import-not-found,no-redef]
        if maximum_tick_age_seconds < 1:
            raise ValueError("maximum_tick_age_seconds must be positive")
        self._mt5 = binding
        self._terminal_path = terminal_path
        self._offset = int(provider_utc_offset_seconds)
        self._now = now or (lambda: datetime.now(UTC))
        self._maximum_tick_age_seconds = maximum_tick_age_seconds
        self._initialized = False

    def __enter__(self) -> "MT5Provider":
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def connect(self) -> ProviderHealth:
        initialized = (
            self._mt5.initialize(self._terminal_path)
            if self._terminal_path
            else self._mt5.initialize()
        )
        self._initialized = bool(initialized)
        return self.health()

    def close(self) -> None:
        if self._initialized:
            self._mt5.shutdown()
            self._initialized = False

    def normalize_timestamp(self, raw_epoch_seconds: int) -> ProviderTimestamp:
        raw = int(raw_epoch_seconds)
        normalized = datetime.fromtimestamp(raw - self._offset, tz=UTC)
        return ProviderTimestamp(raw, self._offset, normalized)

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError("MT5 provider is not initialized")

    def _last_error(self) -> tuple[Any, ...]:
        error = self._mt5.last_error()
        if isinstance(error, tuple):
            return error
        if isinstance(error, list):
            return tuple(error)
        return (error,)

    def health(self) -> ProviderHealth:
        terminal = self._mt5.terminal_info() if self._initialized else None
        account = self._mt5.account_info() if self._initialized else None
        trade_mode = _field(account, "trade_mode")
        demo_mode = getattr(self._mt5, "ACCOUNT_TRADE_MODE_DEMO", 0)
        environment = "demo" if account is not None and trade_mode == demo_mode else "unknown"
        return ProviderHealth(
            initialized=self._initialized,
            connected=bool(_field(terminal, "connected", False)),
            account_environment=environment,
            server=str(_field(account, "server", "") or ""),
            login=int(_field(account, "login")) if _field(account, "login") is not None else None,
            currency=str(_field(account, "currency", "") or ""),
            balance=float(_field(account, "balance")) if _field(account, "balance") is not None else None,
            equity=float(_field(account, "equity")) if _field(account, "equity") is not None else None,
            last_error=self._last_error(),
        )

    def list_symbols(self, query: str = "") -> list[SymbolSummary]:
        self._require_initialized()
        symbols = _rows(self._mt5.symbols_get())
        needle = query.strip().casefold()
        result = []
        for item in symbols:
            name = str(_field(item, "name", ""))
            description = str(_field(item, "description", "") or "")
            path = str(_field(item, "path", "") or "")
            if needle and needle not in name.casefold() and needle not in description.casefold():
                continue
            result.append(
                SymbolSummary(
                    name=name,
                    description=description,
                    path=path,
                    visible=bool(_field(item, "visible", False)),
                )
            )
        return sorted(result, key=lambda symbol: symbol.name.casefold())

    def resolve_exact_symbol(self, requested_name: str) -> SymbolSummary:
        target = requested_name.strip().casefold()
        matches = [symbol for symbol in self.list_symbols() if symbol.name.casefold() == target]
        if len(matches) != 1:
            raise LookupError(f"Expected exactly one MT5 symbol named {requested_name!r}; found {len(matches)}")
        return matches[0]

    def symbol_specification(self, symbol: str) -> SymbolSpecification:
        self._require_initialized()
        self.resolve_exact_symbol(symbol)
        if not self._mt5.symbol_select(symbol, True):
            raise RuntimeError(f"MT5 could not select symbol {symbol!r}: {self._last_error()}")
        info = self._mt5.symbol_info(symbol)
        if info is None:
            raise RuntimeError(f"MT5 returned no specification for {symbol!r}: {self._last_error()}")
        return SymbolSpecification(
            symbol=symbol,
            digits=int(_field(info, "digits", 0)),
            point=float(_field(info, "point", 0.0)),
            tick_size=float(_field(info, "trade_tick_size", 0.0)),
            tick_value=float(_field(info, "trade_tick_value", 0.0)),
            contract_size=float(_field(info, "trade_contract_size", 0.0)),
            minimum_volume=float(_field(info, "volume_min", 0.0)),
            maximum_volume=float(_field(info, "volume_max", 0.0)),
            volume_step=float(_field(info, "volume_step", 0.0)),
            trade_mode=int(_field(info, "trade_mode", 0)),
            order_mode=int(_field(info, "order_mode", 0)),
            margin_initial=float(_field(info, "margin_initial", 0.0)),
            margin_maintenance=float(_field(info, "margin_maintenance", 0.0)),
            currency_base=str(_field(info, "currency_base", "") or ""),
            currency_profit=str(_field(info, "currency_profit", "") or ""),
            currency_margin=str(_field(info, "currency_margin", "") or ""),
        )

    def latest_tick(self, symbol: str) -> Tick:
        self._require_initialized()
        self.resolve_exact_symbol(symbol)
        raw = self._mt5.symbol_info_tick(symbol)
        if raw is None:
            raise RuntimeError(f"MT5 returned no tick for {symbol!r}: {self._last_error()}")
        timestamp = self.normalize_timestamp(int(_field(raw, "time", 0)))
        age = max(0.0, (self._now().astimezone(UTC) - timestamp.normalized_utc).total_seconds())
        return Tick(
            symbol=symbol,
            bid=float(_field(raw, "bid", 0.0)),
            ask=float(_field(raw, "ask", 0.0)),
            last=float(_field(raw, "last", 0.0)),
            volume=float(_field(raw, "volume_real", _field(raw, "volume", 0.0))),
            timestamp=timestamp,
            age_seconds=age,
            fresh=age <= self._maximum_tick_age_seconds,
        )

    def h4_candles(self, symbol: str, *, completed_count: int = 200) -> tuple[list[Candle], Candle | None]:
        self._require_initialized()
        if completed_count < 1 or completed_count > 2000:
            raise ValueError("completed_count must be between 1 and 2000")
        self.resolve_exact_symbol(symbol)
        raw_rows = _rows(
            self._mt5.copy_rates_from_pos(symbol, self._mt5.TIMEFRAME_H4, 0, completed_count + 1)
        )
        candles = [self._candle(symbol, row) for row in raw_rows]
        candles.sort(key=lambda candle: candle.open_time.raw_epoch_seconds)
        now = self._now().astimezone(UTC)
        developing = None
        if candles and candles[-1].open_time.normalized_utc + timedelta(seconds=H4_SECONDS) > now:
            developing = candles.pop()
        return candles[-completed_count:], developing

    def historical_ticks(self, symbol: str, start_utc: datetime, end_utc: datetime) -> list[HistoricalTick]:
        self._require_initialized()
        self.resolve_exact_symbol(symbol)
        start = self._provider_datetime(start_utc)
        end = self._provider_datetime(end_utc)
        if end <= start:
            raise ValueError("end_utc must be after start_utc")
        rows = _rows(self._mt5.copy_ticks_range(symbol, start, end, self._mt5.COPY_TICKS_ALL))
        return [
            HistoricalTick(
                symbol=symbol,
                bid=float(_field(row, "bid", 0.0)),
                ask=float(_field(row, "ask", 0.0)),
                last=float(_field(row, "last", 0.0)),
                volume=float(_field(row, "volume_real", _field(row, "volume", 0.0))),
                flags=int(_field(row, "flags", 0)),
                timestamp=self.normalize_timestamp(int(_field(row, "time", 0))),
            )
            for row in rows
        ]

    def _provider_datetime(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC) + timedelta(seconds=self._offset)

    def _candle(self, symbol: str, row: Any) -> Candle:
        return Candle(
            symbol=symbol,
            timeframe="4H",
            open_time=self.normalize_timestamp(int(_field(row, "time", 0))),
            open=float(_field(row, "open", 0.0)),
            high=float(_field(row, "high", 0.0)),
            low=float(_field(row, "low", 0.0)),
            close=float(_field(row, "close", 0.0)),
            tick_volume=int(_field(row, "tick_volume", 0)),
            spread=int(_field(row, "spread", 0)),
            real_volume=int(_field(row, "real_volume", 0)),
        )
