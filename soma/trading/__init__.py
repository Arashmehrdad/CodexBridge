"""Trading Lab: packet-bound signals, independent outcome resolution,
deterministic offline replay, and the guarded demo action gateway.

Runtime threshold portfolios were removed: a model decision is stored
once in the immutable signal journal, each directional signal resolves
independently from retained ticks, and threshold/occupancy analysis
happens only through deterministic offline replay. Live execution does
not exist anywhere in this package.
"""

from .action_gateway import (
    ActionGateway,
    ActionRecord,
    ActionRequest,
    ActionState,
    TradingActionJournal,
)
from .broker_time import (
    BrokerOffsetDetection,
    OffsetSample,
    detect_broker_utc_offset,
)
from .executors import DemoExecutor, PaperExecutor
from .lab_reports import build_calibration_report, build_replay_report
from .market_packet import MarketPacket, MarketPacketBuilder
from .mt5_provider import (
    Candle,
    HistoricalTick,
    MT5Provider,
    ProviderHealth,
    ProviderTimestamp,
    SymbolSpecification,
    SymbolSummary,
    Tick,
)
from .outcome_resolver import (
    OutcomeStatus,
    SignalOutcome,
    SignalOutcomeJournal,
    resolve_from_ranges,
    resolve_from_ticks,
)
from .packet_store import MarketPacketStore, StoredMarketPacket
from .replay_engine import (
    CostModel,
    NotionalModel,
    OccupancyPolicy,
    ReplayConfig,
    replay_signals,
    sweep_thresholds,
)
from .safety import SafetyLimits, TradingSafetyController, redact_health
from .signal_journal_v2 import (
    SignalDecisionV2,
    SignalJournalV2,
    SignalRecordV2,
    SignalRejectedError,
    SignalStatusV2,
    SignalSubmissionV2,
)
from .strategy_policy import (
    ActionType,
    CapabilityRole,
    ExecutionMode,
    StrategyPolicy,
    resolve_policy,
)
from .tick_archive import TickArchive
from .trading_runtime import TradingRuntime

__all__ = [
    "ActionGateway",
    "ActionRecord",
    "ActionRequest",
    "ActionState",
    "ActionType",
    "BrokerOffsetDetection",
    "Candle",
    "CapabilityRole",
    "CostModel",
    "DemoExecutor",
    "ExecutionMode",
    "HistoricalTick",
    "MT5Provider",
    "MarketPacket",
    "MarketPacketBuilder",
    "MarketPacketStore",
    "NotionalModel",
    "OccupancyPolicy",
    "OffsetSample",
    "OutcomeStatus",
    "PaperExecutor",
    "ProviderHealth",
    "ProviderTimestamp",
    "ReplayConfig",
    "SafetyLimits",
    "SignalDecisionV2",
    "SignalJournalV2",
    "SignalOutcome",
    "SignalOutcomeJournal",
    "SignalRecordV2",
    "SignalRejectedError",
    "SignalStatusV2",
    "SignalSubmissionV2",
    "StoredMarketPacket",
    "StrategyPolicy",
    "SymbolSpecification",
    "SymbolSummary",
    "Tick",
    "TickArchive",
    "TradingActionJournal",
    "TradingRuntime",
    "TradingSafetyController",
    "build_calibration_report",
    "build_replay_report",
    "detect_broker_utc_offset",
    "redact_health",
    "replay_signals",
    "resolve_from_ranges",
    "resolve_from_ticks",
    "resolve_policy",
    "sweep_thresholds",
]
