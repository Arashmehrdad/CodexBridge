"""The single seam between Soma and the standalone Trading Lab package.

Soma owns invocation identity, durability, evidence, repository identity,
compact public projection, configuration, and client transport. The
``trading_lab`` package owns the trading domain and the trading domain's
durable state. This module is the only place the two meet.

It does three things and nothing else:

* maps Soma's ``TradingConfig`` and runs directory onto the package's
  ``TradingLabSettings`` / ``TradingLabPaths``, so the existing database
  files under ``<runs_dir>/trading`` keep being the ones used;
* constructs the package's services lazily, preserving the existing
  MT5 provider injection and the process-stable paper executor;
* re-exports the domain names Soma's gateways refer to, so no Soma module
  imports a trading implementation directly.

It deliberately holds no trading logic. If a behavior belongs to the
domain it belongs in ``trading_lab``; if it belongs to a public response
it belongs in the gateway.

A migration-time backend switch (``SOMA_TRADING_BACKEND``) selects
between the external package and Soma's superseded in-tree copy. It
exists so equivalence can be proven against the previous implementation
and so a cutover can be rolled back without a code change. It is
temporary and is removed once ``soma/trading`` is deleted.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Final

from .config import AppConfig, TradingConfig

# --------------------------------------------------------------------------
# Backend selection (temporary migration mechanism).
# --------------------------------------------------------------------------

PACKAGE_BACKEND: Final[str] = "package"
LEGACY_BACKEND: Final[str] = "legacy"
DEFAULT_BACKEND: Final[str] = PACKAGE_BACKEND
_BACKEND_ENV_VAR: Final[str] = "SOMA_TRADING_BACKEND"


def selected_backend() -> str:
    """Which trading implementation this process is wired to."""
    raw = os.getenv(_BACKEND_ENV_VAR, "").strip().lower()
    if raw in {PACKAGE_BACKEND, LEGACY_BACKEND}:
        return raw
    if raw:
        raise ValueError(
            f"{_BACKEND_ENV_VAR} must be {PACKAGE_BACKEND!r} or"
            f" {LEGACY_BACKEND!r}; got {raw!r}"
        )
    return DEFAULT_BACKEND


def _legacy_available() -> bool:
    from importlib.util import find_spec

    try:
        return find_spec("soma.trading") is not None
    except (ImportError, ValueError):
        return False


# The domain names below are resolved once, from the selected backend.
# Both backends expose an identical class surface, which is what makes
# the switch a genuine rollback rather than a second implementation.
if selected_backend() == LEGACY_BACKEND:  # pragma: no cover - rollback path
    if not _legacy_available():
        raise RuntimeError(
            "SOMA_TRADING_BACKEND=legacy was requested but the superseded"
            " soma.trading package has been removed. Unset the variable to"
            " use the standalone trading_lab package."
        )
    from .trading import (  # type: ignore[attr-defined]
        ActionGateway,
        ActionRecord,
        ActionRequest,
        ActionState,
        ActionType,
        CapabilityRole,
        CostModel,
        DemoExecutor,
        ExecutionMode,
        MarketPacketStore,
        MT5Provider,
        NotionalModel,
        OccupancyPolicy,
        OutcomeStatus,
        PaperExecutor,
        ReplayConfig,
        SafetyLimits,
        SignalDecisionV2,
        SignalJournalV2,
        SignalOutcomeJournal,
        SignalRecordV2,
        SignalRejectedError,
        SignalStatusV2,
        SignalSubmissionV2,
        TickArchive,
        TradingActionJournal,
        TradingRuntime,
        TradingSafetyController,
        build_calibration_report,
        build_replay_report,
        redact_health,
    )
    from .trading.action_gateway import Quote  # type: ignore[attr-defined]

    _TRADING_LAB_VERSION = "n/a (legacy in-tree implementation)"
else:
    from trading_lab import (
        ActionGateway,
        ActionRecord,
        ActionRequest,
        ActionState,
        ActionType,
        CapabilityRole,
        CostModel,
        DemoExecutor,
        ExecutionMode,
        MarketPacketStore,
        MT5Provider,
        NotionalModel,
        OccupancyPolicy,
        OutcomeStatus,
        PaperExecutor,
        ReplayConfig,
        SafetyLimits,
        SignalDecisionV2,
        SignalJournalV2,
        SignalOutcomeJournal,
        SignalRecordV2,
        SignalRejectedError,
        SignalStatusV2,
        SignalSubmissionV2,
        TickArchive,
        TradingActionJournal,
        TradingRuntime,
        TradingSafetyController,
        __version__ as _TRADING_LAB_VERSION,
        build_calibration_report,
        build_replay_report,
        redact_health,
    )
    from trading_lab.action_gateway import Quote

# The contract types below are the same regardless of which backend
# supplies the domain classes: the legacy shim builds them too, so the
# gateway sees one result shape either way.
from trading_lab.service import (  # noqa: E402
    ACTION_OPERATIONS,
    DEPRECATED_QUERY_NOTICE,
    DEPRECATED_QUERY_OPERATIONS,
    JOURNAL_QUERY_OPERATIONS,
    READ_OPERATIONS,
    RUNTIME_CONTROL_OPERATIONS,
    SIGNAL_OPERATIONS,
    TradingLabPaths,
    TradingLabSettings,
    TradingLabServices,
)


# --------------------------------------------------------------------------
# Configuration mapping.
# --------------------------------------------------------------------------


def trading_dir(config: AppConfig) -> Path:
    """The existing trading state directory. Unchanged by the migration."""
    return (config.resolve_runs_dir() / "trading").resolve()


def settings_from_config(config: AppConfig) -> TradingLabSettings:
    """Map Soma's ``TradingConfig`` onto the package's settings.

    Field-for-field, with no defaulting of its own: every value below is
    already validated by ``TradingConfig``.
    """
    trading: TradingConfig = config.trading
    return TradingLabSettings(
        paths=TradingLabPaths(trading_dir(config)),
        symbol=trading.symbol,
        terminal_path=trading.terminal_path or None,
        provider_utc_offset_seconds=trading.provider_utc_offset_seconds,
        maximum_tick_age_seconds=trading.maximum_tick_age_seconds,
    )


# --------------------------------------------------------------------------
# Service construction.
#
# Services are keyed by the resolved settings so that a configuration
# reload produces a fresh container while repeated calls under one
# configuration keep the single paper executor and its open positions.
# --------------------------------------------------------------------------


@lru_cache(maxsize=8)
def _services_for(settings: TradingLabSettings) -> TradingLabServices:
    if selected_backend() == LEGACY_BACKEND:  # pragma: no cover
        return _LegacyServices(settings)  # type: ignore[return-value]
    return TradingLabServices(settings)


def services(config: AppConfig) -> TradingLabServices:
    """The trading domain services bound to Soma's configuration."""
    return _services_for(settings_from_config(config))


def reset_services_cache() -> None:
    """Drop cached services. Used by configuration reload and by tests."""
    _services_for.cache_clear()


def configured_mt5_provider(config: AppConfig) -> MT5Provider:
    """A provider built from Soma's configuration, not yet connected."""
    trading = config.trading
    return MT5Provider(
        terminal_path=trading.terminal_path or None,
        provider_utc_offset_seconds=trading.provider_utc_offset_seconds,
        maximum_tick_age_seconds=trading.maximum_tick_age_seconds,
    )


def paper_quote_source(config: AppConfig) -> Callable[[str], Quote]:
    """Fresh bid/ask for the paper executor, from the configured provider."""

    def quote(symbol: str) -> Quote:
        provider = configured_mt5_provider(config)
        try:
            provider.connect()
            tick = provider.latest_tick(symbol)
            return Quote(
                bid=tick.bid, ask=tick.ask, age_seconds=tick.age_seconds
            )
        finally:
            provider.close()

    return quote


def paper_rules_source(config: AppConfig) -> Callable[[str], Any]:
    """Symbol specification for the paper executor."""

    def rules(symbol: str) -> Any:
        provider = configured_mt5_provider(config)
        try:
            provider.connect()
            return provider.symbol_specification(symbol)
        finally:
            provider.close()

    return rules


def executor_for_mode(
    config: AppConfig, mode: str, provider: Any | None
) -> Any:
    """The executor for one execution mode, preserving provider injection."""
    return services(config).executor_for_mode(
        mode,
        provider,
        quote_source=paper_quote_source(config),
        rules_source=paper_rules_source(config),
    )


# --------------------------------------------------------------------------
# Diagnostics.
#
# Deliberately not attached to ordinary trading responses: this is
# answered by the system self-check surface, where build identity already
# lives.
# --------------------------------------------------------------------------


def package_identity() -> dict[str, Any]:
    """Which trading implementation this process actually resolved."""
    import trading_lab

    module_file = getattr(trading_lab, "__file__", "") or ""
    identity: dict[str, Any] = {
        "backend": selected_backend(),
        "package": "trading_lab",
        "version": _TRADING_LAB_VERSION,
        "module_path": str(Path(module_file).parent) if module_file else "",
        "installed_version": "",
        "source_commit": "",
        "editable": False,
    }
    try:
        from importlib.metadata import version as _distribution_version

        identity["installed_version"] = _distribution_version("trading-lab")
    except Exception:  # pragma: no cover - metadata is optional
        identity["installed_version"] = ""
    identity["editable"] = _looks_editable(module_file)
    identity["source_commit"] = _recorded_source_commit(module_file)
    return identity


def _looks_editable(module_file: str) -> bool:
    """An editable install resolves into a working tree, not site-packages."""
    if not module_file:
        return False
    return "site-packages" not in Path(module_file).parts


def _recorded_source_commit(module_file: str) -> str:
    """The commit a pinned install recorded, when one is present.

    Written by ``scripts/install_trading_lab_pinned.ps1``. Absent for a
    plain editable development install, which is expected and not an
    error.
    """
    if not module_file:
        return ""
    stamp = Path(module_file).parent / "_build_stamp.json"
    if not stamp.is_file():
        return ""
    try:
        import json

        return str(json.loads(stamp.read_text("utf-8")).get("commit", ""))
    except Exception:  # pragma: no cover - a bad stamp is not fatal
        return ""


# --------------------------------------------------------------------------
# Legacy rollback shim (temporary).
#
# Mirrors the package's services container over the superseded in-tree
# classes. It contains no trading logic of its own -- it only wires the
# same objects the gateway used before the cutover. Deleted together with
# soma/trading.
# --------------------------------------------------------------------------


class _LegacyServices:  # pragma: no cover - rollback path only
    """The pre-cutover wiring, exposed through the package's method names."""

    def __init__(self, settings: TradingLabSettings) -> None:
        self.settings = settings
        self._paper_executor: Any = None

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(
            f"{name!r} is not available on the legacy trading backend;"
            " unset SOMA_TRADING_BACKEND to use the trading_lab package"
        )

    @property
    def paths(self) -> TradingLabPaths:
        return self.settings.paths

    @property
    def symbol(self) -> str:
        return self.settings.symbol

    def packet_store(self) -> Any:
        return MarketPacketStore(self.paths.packet_db)

    def signal_journal(self) -> Any:
        return SignalJournalV2(
            self.paths.signal_db,
            self.packet_store(),
            expected_symbol=self.symbol,
        )

    def outcome_journal(self) -> Any:
        return SignalOutcomeJournal(self.paths.outcome_db)

    def tick_archive(self) -> Any:
        return TickArchive(self.paths.tick_db, self.paths.tick_archive_dir)

    def action_journal(self) -> Any:
        return TradingActionJournal(self.paths.action_db)

    def safety(self) -> Any:
        return TradingSafetyController(self.paths.safety_db)

    def action_gateway(self) -> Any:
        return ActionGateway(
            journal=self.action_journal(), safety=self.safety()
        )

    def runtime(self) -> Any:
        return TradingRuntime(
            runtime_db_path=self.paths.runtime_db,
            packet_store=self.packet_store(),
            signal_journal=self.signal_journal(),
            outcome_journal=self.outcome_journal(),
            tick_archive=self.tick_archive(),
            action_journal=self.action_journal(),
            gateway=self.action_gateway(),
            symbol=self.symbol,
        )

    def paper_executor(self, *, quote_source: Any, rules_source: Any) -> Any:
        if self._paper_executor is None:
            self._paper_executor = PaperExecutor(
                quote_source=quote_source, rules_source=rules_source
            )
        return self._paper_executor

    def executor_for_mode(
        self,
        mode: Any,
        provider: Any | None,
        *,
        quote_source: Any,
        rules_source: Any,
    ) -> Any:
        if ExecutionMode(mode) is ExecutionMode.BROKER_DEMO:
            if provider is None:
                raise RuntimeError("broker_demo execution requires a provider")
            return DemoExecutor(provider=provider, binding=provider.binding)
        return self.paper_executor(
            quote_source=quote_source, rules_source=rules_source
        )

    # -- Journal queries -------------------------------------------------

    def market_packet_get(self, packet_id: str) -> Any:
        return self.packet_store().get(packet_id)

    def market_packet_list(self, *, limit: int, offset: int) -> Any:
        from trading_lab.service import PacketPage

        store = self.packet_store()
        return PacketPage(
            packets=tuple(store.list_packets(limit=limit, offset=offset)),
            total=store.count_packets(),
            offset=offset,
        )

    def outcome_get(self, signal_id: str) -> Any:
        return self.outcome_journal().get(signal_id)

    def outcome_list(
        self,
        *,
        limit: int,
        offset: int,
        status: Any = None,
        experiment_id: str | None = None,
    ) -> Any:
        from trading_lab.service import OutcomePage

        journal = self.outcome_journal()
        resolved = OutcomeStatus(status) if status else None
        return OutcomePage(
            outcomes=tuple(
                journal.list(
                    limit=limit,
                    offset=offset,
                    status=resolved,
                    experiment_id=experiment_id,
                )
            ),
            total=journal.count(experiment_id=experiment_id),
            offset=offset,
        )

    def rejection_list(self, *, limit: int, offset: int) -> Any:
        from trading_lab.service import RejectionPage

        return RejectionPage(
            rejections=tuple(
                self.signal_journal().list_rejections(
                    limit=limit, offset=offset
                )
            ),
            offset=offset,
        )

    def data_quality(
        self,
        *,
        start_utc: Any,
        end_utc: Any,
        max_gap_seconds: float,
        symbol: str | None = None,
    ) -> Any:
        from trading_lab.service import DataQualityReport

        archive = self.tick_archive()
        resolved_symbol = symbol or self.symbol
        range_hash, count = archive.range_hash(
            resolved_symbol, start_utc, end_utc
        )
        return DataQualityReport(
            symbol=resolved_symbol,
            tick_count=count,
            range_hash=range_hash,
            gaps=tuple(
                archive.detect_gaps(
                    resolved_symbol,
                    start_utc,
                    end_utc,
                    max_gap_seconds=max_gap_seconds,
                )
            ),
        )

    def all_signals(self) -> list[Any]:
        journal = self.signal_journal()
        records: list[Any] = []
        offset = 0
        while True:
            page = journal.list(limit=500, offset=offset)
            if not page:
                return records
            records.extend(page)
            offset += len(page)

    def all_outcomes(self) -> dict[str, Any]:
        journal = self.outcome_journal()
        outcomes: dict[str, Any] = {}
        offset = 0
        while True:
            page = journal.list(limit=500, offset=offset)
            if not page:
                return outcomes
            for outcome in page:
                outcomes[outcome.signal_id] = outcome
            offset += len(page)

    def calibration_report(
        self,
        *,
        experiment_id: str | None = None,
        period_start_utc: Any = None,
        period_end_utc: Any = None,
        period_basis: str = "entry",
        rejection_sample_limit: int = 500,
    ) -> dict[str, Any]:
        return build_calibration_report(
            self.all_signals(),
            self.all_outcomes(),
            experiment_id=experiment_id,
            rejection_count=len(
                self.signal_journal().list_rejections(
                    limit=rejection_sample_limit
                )
            ),
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            period_basis=period_basis,
        )

    def replay_report(
        self,
        *,
        experiment_id: str | None = None,
        threshold_start: int,
        threshold_end: int,
        allow_stacking: bool,
        fixed_notional_usd: float,
        per_trade_cost_usd: float,
        initial_equity_usd: float,
        minimum_sample: int,
        period_start_utc: Any = None,
        period_end_utc: Any = None,
        period_basis: str = "entry",
    ) -> dict[str, Any]:
        return build_replay_report(
            self.all_signals(),
            self.all_outcomes(),
            experiment_id=experiment_id,
            base_config=ReplayConfig(
                threshold=threshold_start,
                occupancy=OccupancyPolicy(allow_stacking=allow_stacking),
                notional=NotionalModel(fixed_notional_usd=fixed_notional_usd),
                cost=CostModel(per_trade_cost_usd=per_trade_cost_usd),
                initial_equity_usd=initial_equity_usd,
            ),
            thresholds=tuple(range(threshold_start, threshold_end + 1)),
            minimum_sample=minimum_sample,
            period_start_utc=period_start_utc,
            period_end_utc=period_end_utc,
            period_basis=period_basis,
        )

    def action_get(self, action_id: str) -> Any:
        return self.action_journal().get(action_id)

    def action_list(
        self,
        *,
        limit: int,
        offset: int,
        state: Any = None,
        symbol: str | None = None,
    ) -> Any:
        from trading_lab.service import ActionPage

        journal = self.action_journal()
        resolved = ActionState(state) if state else None
        return ActionPage(
            actions=tuple(
                journal.list(
                    limit=limit, offset=offset, state=resolved, symbol=symbol
                )
            ),
            total=journal.count(),
            offset=offset,
        )

    def runtime_status_report(self, *, event_limit: int = 20) -> Any:
        from trading_lab.service import RuntimeStatusReport

        runtime = self.runtime()
        return RuntimeStatusReport(
            status=runtime.status(),
            kill_switch=self.safety().kill_switch(),
            recent_events=tuple(runtime.events(limit=event_limit)),
        )

    def demo_performance(self, *, limit: int) -> Any:
        from trading_lab.service import DemoPerformance

        confirmed = tuple(
            record
            for record in self.action_journal().list(limit=limit)
            if record.execution_mode is ExecutionMode.BROKER_DEMO
            and record.state
            in (ActionState.BROKER_CONFIRMED, ActionState.RECONCILED)
        )
        return DemoPerformance(
            confirmed_demo_actions=confirmed, count=len(confirmed)
        )

    def reconciliation_report(self, *, limit: int, offset: int) -> Any:
        from trading_lab.service import (
            ReconciliationEntry,
            ReconciliationReport,
        )

        records = self.action_journal().list(limit=limit, offset=offset)
        return ReconciliationReport(
            reconciliations=tuple(
                ReconciliationEntry(
                    action_id=record.action_id,
                    action_type=record.action_type.value,
                    state=record.state.value,
                    broker_order_ticket=record.broker_order_ticket,
                    broker_position_ticket=record.broker_position_ticket,
                    reconciliation=record.reconciliation,
                    error=record.error,
                )
                for record in records
            ),
            offset=offset,
        )

    # -- Signals ---------------------------------------------------------

    def signal_submit(self, idempotency_key: str, submission: Any) -> Any:
        return self.signal_journal().submit(idempotency_key, submission)

    def signal_get(self, signal_id: str) -> Any:
        return self.signal_journal().get(signal_id)

    def signal_list(
        self,
        *,
        limit: int,
        offset: int,
        status: Any = None,
        experiment_id: str | None = None,
    ) -> Any:
        from trading_lab.service import SignalPage

        journal = self.signal_journal()
        resolved = SignalStatusV2(status) if status else None
        records = journal.list(
            limit=limit,
            offset=offset,
            status=resolved,
            experiment_id=experiment_id,
        )
        return SignalPage(
            signals=tuple(records),
            total=journal.count(
                status=resolved, experiment_id=experiment_id
            ),
            offset=offset,
        )

    def signal_cancel_before_entry(self, signal_id: str, reason: str) -> Any:
        return self.signal_journal().cancel_before_entry(signal_id, reason)

    # -- Actions and runtime control -------------------------------------

    def action_submit(self, request: Any, executor: Any) -> Any:
        return self.action_gateway().submit(request, executor)

    def runtime_start(self, *, now: Any = None) -> Any:
        return self.runtime().start(now=now)

    def runtime_stop(self, reason: str, *, now: Any = None) -> Any:
        return self.runtime().stop(reason, now=now)

    def runtime_status(self) -> Any:
        from trading_lab.service import RuntimeControlStatus

        return RuntimeControlStatus(
            status=self.runtime().status(),
            kill_switch=self.safety().kill_switch(),
        )

    def kill_switch_on(self, reason: str, *, at_utc: Any = None) -> Any:
        return self.safety().activate_kill_switch(reason, at_utc=at_utc)

    def kill_switch_off(self, reason: str, *, at_utc: Any = None) -> Any:
        return self.safety().release_kill_switch(reason, at_utc=at_utc)

    def supervise_now(
        self, provider: Any, executor: Any, *, now: Any = None
    ) -> Any:
        return self.runtime().supervision_pass(provider, executor, now=now)

    def analyze_now(
        self, provider: Any, executor: Any, *, now: Any = None
    ) -> Any:
        return self.runtime().analysis_pass(provider, executor, now=now)


__all__ = [
    "ACTION_OPERATIONS",
    "ActionGateway",
    "ActionRecord",
    "ActionRequest",
    "ActionState",
    "ActionType",
    "CapabilityRole",
    "CostModel",
    "DEFAULT_BACKEND",
    "DEPRECATED_QUERY_NOTICE",
    "DEPRECATED_QUERY_OPERATIONS",
    "DemoExecutor",
    "ExecutionMode",
    "JOURNAL_QUERY_OPERATIONS",
    "LEGACY_BACKEND",
    "MT5Provider",
    "MarketPacketStore",
    "NotionalModel",
    "OccupancyPolicy",
    "OutcomeStatus",
    "PACKAGE_BACKEND",
    "PaperExecutor",
    "Quote",
    "READ_OPERATIONS",
    "RUNTIME_CONTROL_OPERATIONS",
    "ReplayConfig",
    "SIGNAL_OPERATIONS",
    "SafetyLimits",
    "SignalDecisionV2",
    "SignalJournalV2",
    "SignalOutcomeJournal",
    "SignalRecordV2",
    "SignalRejectedError",
    "SignalStatusV2",
    "SignalSubmissionV2",
    "TickArchive",
    "TradingActionJournal",
    "TradingLabPaths",
    "TradingLabServices",
    "TradingLabSettings",
    "TradingRuntime",
    "TradingSafetyController",
    "build_calibration_report",
    "build_replay_report",
    "configured_mt5_provider",
    "executor_for_mode",
    "package_identity",
    "paper_quote_source",
    "paper_rules_source",
    "redact_health",
    "reset_services_cache",
    "selected_backend",
    "services",
    "settings_from_config",
    "trading_dir",
]
