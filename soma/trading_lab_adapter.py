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

There is no fallback. Soma once carried its own copy of the trading
domain under ``soma/trading``; that copy was removed once equivalence was
proven, so if ``trading_lab`` is missing or incompatible this module
fails to import with the underlying error rather than degrading to stale
duplicated code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

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
    ModelApprovalDecision,
    MT5Provider,
    NotionalModel,
    OccupancyPolicy,
    OutcomeStatus,
    PaperExecutor,
    ReplayConfig,
    ResearchSource,
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
from trading_lab.service import (
    ACTION_OPERATIONS,
    COMPANION_OPERATIONS,
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

from .config import AppConfig, TradingConfig


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
        "backend": "package",
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

__all__ = [
    "ACTION_OPERATIONS",
    "ActionGateway",
    "ActionRecord",
    "ActionRequest",
    "ActionState",
    "ActionType",
    "CapabilityRole",
    "COMPANION_OPERATIONS",
    "CostModel",
    "DEPRECATED_QUERY_NOTICE",
    "DEPRECATED_QUERY_OPERATIONS",
    "DemoExecutor",
    "ExecutionMode",
    "JOURNAL_QUERY_OPERATIONS",
    "MT5Provider",
    "MarketPacketStore",
    "ModelApprovalDecision",
    "NotionalModel",
    "OccupancyPolicy",
    "OutcomeStatus",
    "PaperExecutor",
    "Quote",
    "READ_OPERATIONS",
    "RUNTIME_CONTROL_OPERATIONS",
    "ReplayConfig",
    "ResearchSource",
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
    "services",
    "settings_from_config",
    "trading_dir",
]
