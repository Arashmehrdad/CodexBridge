"""Strict request contracts for the public domain gateway tools.

The models intentionally describe routing and operation-specific inputs only.
They do not duplicate the established manager, repository, SSH, or cloud
validation that executes after a request is accepted.
"""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .company_kernel.dependencies import (
    EvidenceAvailableCandidateV1,
    PublishedSuccessCandidateV1,
)
from .reasoning.models import ReasoningSpecV1
from .run_query_chunks import encode_list_reference, encode_run_reference
from .ssh_policy import (
    AutonomyProfile,
    SSHExecutionMode,
    SSHPolicyRequest,
    evaluate_ssh_policy,
)


class GatewayModel(BaseModel):
    """Base contract: callers cannot smuggle fields from another operation."""

    model_config = ConfigDict(extra="forbid")


class SSHHostHealth(GatewayModel):
    operation: Literal["host_health"]
    host_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SSHEnvironmentProbe(GatewayModel):
    operation: Literal["environment_probe"]
    host_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SSHGpuTelemetry(GatewayModel):
    operation: Literal["gpu_telemetry"]
    host_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SSHBoundedInspection(GatewayModel):
    operation: Literal["inspection"]
    host_id: str = Field(min_length=1, max_length=128)
    inspection: str = Field(min_length=1, max_length=128)
    path: str = Field(default="", max_length=1024)
    target: str = Field(default="", max_length=512)
    deployment_id: str = Field(default="", max_length=128)
    tail: int = Field(default=200, ge=1, le=20_000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


SSHInspectRequest = Annotated[
    SSHHostHealth | SSHEnvironmentProbe | SSHGpuTelemetry | SSHBoundedInspection,
    Field(discriminator="operation"),
]


class RunStatusQuery(GatewayModel):
    operation: Literal["status"]
    run_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)


class RunInputQuery(GatewayModel):
    operation: Literal["input"]
    run_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    cursor: str = Field(default="", max_length=2048)
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=12 * 1024)

    @model_validator(mode="after")
    def promote_cursor_to_full(self) -> "RunInputQuery":
        if self.cursor:
            self.view = "full"
        return self


class RunControlQuery(GatewayModel):
    operation: Literal["control"]
    run_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    if_state_version: int | None = Field(default=None, ge=0)


class RunOutputQuery(GatewayModel):
    operation: Literal["output"]
    run_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    stream: Literal["combined", "stdout", "stderr"] = "combined"
    tail_bytes: int = Field(default=20_000, ge=1, le=200_000)
    view: Literal["compact", "full", "legacy"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=12 * 1024, le=12 * 1024)


class RunEventsQuery(GatewayModel):
    operation: Literal["events"]
    run_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    limit: int = Field(default=20, ge=1, le=500)
    after_id: int | None = Field(default=None, ge=0)
    cursor: str = Field(default="", max_length=2048)

    @model_validator(mode="after")
    def validate_cursor_selection(self) -> "RunEventsQuery":
        if self.cursor and self.after_id is not None:
            raise ValueError("cursor cannot be combined with after_id")
        return self


class RunTerminalQuery(GatewayModel):
    operation: Literal["terminal"]
    run_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)


class RunResultQuery(GatewayModel):
    operation: Literal["result"]
    run_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    cursor: str = Field(default="", max_length=2048)
    view: Literal["compact", "full"] = "compact"

    @model_validator(mode="after")
    def encode_chunk_reference(self) -> "RunResultQuery":
        if self.cursor and self.view == "compact":
            self.view = "full"
        self.run_id = encode_run_reference(self.run_id, self.cursor)
        return self


class PowerShellGroupStatusQuery(GatewayModel):
    operation: Literal["group_status"]
    group_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class PowerShellGroupResultQuery(GatewayModel):
    operation: Literal["group_result"]
    group_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RunSummaryQuery(GatewayModel):
    operation: Literal["summary"]
    run_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)


class RunSummaryListQuery(GatewayModel):
    operation: Literal["summary_list"]
    repo_name: str = Field(default="", max_length=128)
    status: str = Field(default="", max_length=64)
    tool: str = Field(default="", max_length=128)
    limit: int = Field(default=10, ge=1, le=100)
    cursor: str = Field(default="", max_length=2048)


class RunListQuery(GatewayModel):
    operation: Literal["list"]
    repo_name: str = Field(default="", max_length=128)
    status: str = Field(default="", max_length=64)
    limit: int = Field(default=20, ge=1, le=500)
    cursor: str = Field(default="", max_length=2048)

    @model_validator(mode="after")
    def encode_chunk_reference(self) -> "RunListQuery":
        self.repo_name = encode_list_reference(self.repo_name, self.cursor)
        return self


class RunLocksQuery(GatewayModel):
    operation: Literal["locks"]
    repo_name: str = Field(default="", max_length=128)
    include_stale: bool = True
    limit: int = Field(default=50, ge=1, le=500)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RunPreflightQuery(GatewayModel):
    operation: Literal["preflight"]
    repo_name: str = Field(min_length=1, max_length=128)
    include_stale: bool = False


RunQueryRequest = Annotated[
    RunStatusQuery
    | RunInputQuery
    | RunControlQuery
    | RunOutputQuery
    | RunEventsQuery
    | RunTerminalQuery
    | RunResultQuery
    | PowerShellGroupStatusQuery
    | PowerShellGroupResultQuery
    | RunSummaryQuery
    | RunSummaryListQuery
    | RunListQuery
    | RunLocksQuery
    | RunPreflightQuery,
    Field(discriminator="operation"),
]


class WorkflowStatusQuery(GatewayModel):
    operation: Literal["status"]
    workflow_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class WorkflowEventsQuery(GatewayModel):
    operation: Literal["events"]
    workflow_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=100, ge=1, le=500)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class WorkflowResultQuery(GatewayModel):
    operation: Literal["result"]
    workflow_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


WorkflowQueryRequest = Annotated[
    WorkflowStatusQuery | WorkflowEventsQuery | WorkflowResultQuery,
    Field(discriminator="operation"),
]


class WorkflowStartAction(GatewayModel):
    action: Literal["start"]
    repo_name: str = Field(min_length=1, max_length=128)
    objective: str = Field(min_length=1, max_length=10_000)
    steps: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class WorkflowCancelAction(GatewayModel):
    action: Literal["cancel"]
    workflow_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


WorkflowActionRequest = Annotated[
    WorkflowStartAction | WorkflowCancelAction, Field(discriminator="action")
]


class TradingHealthQuery(GatewayModel):
    operation: Literal["health"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingConfigurationQuery(GatewayModel):
    """The effective resolved Trading Lab runtime settings.

    Answers "what will an omitted field actually use?" in one call, so a
    scheduled controller never has to guess a timeframe from its own
    schedule or carry a private copy of the configured analysis depth.
    Every value is read back from the live resolved settings object, not
    from a constant in this module.
    """

    operation: Literal["configuration"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingSymbolsQuery(GatewayModel):
    operation: Literal["symbols"]
    query: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingSpecificationQuery(GatewayModel):
    operation: Literal["specification"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingTickQuery(GatewayModel):
    operation: Literal["tick"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


# The chart period is a bounded string rather than an enumeration: the
# set of MetaTrader 5 periods belongs to the trading domain, and copying
# it into this schema would be a second place to keep it correct. An
# unknown value is refused by the domain with a message naming every
# period it does accept. ``None`` means the configured timeframe.
_TIMEFRAME_FIELD = Field(default=None, min_length=1, max_length=16)

# ``None`` on any of the following means "use the active Trading Lab
# configuration". They are deliberately not given a literal default here:
# a number baked into this schema is a second source of truth that stops
# tracking the configuration the moment the configuration changes, and the
# drift is silent because both values are individually valid. The upper
# bounds match ``TradingConfig.candle_count`` so a configured depth can
# never exceed what the public schema will accept.
_CONFIGURED_CANDLE_COUNT_FIELD = Field(default=None, ge=1, le=5_000)
_CONFIGURED_PROBE_BARS_FIELD = Field(default=None, ge=2, le=50)
_CONFIGURED_EXECUTION_MODE_FIELD = Field(default=None)
_CONFIGURED_POLICY_FIELD = Field(default=None)
_CONFIGURED_CAPABILITY_ROLE_FIELD = Field(default=None)

TradingExecutionModeName = Literal["internal_paper", "broker_demo"]
TradingPolicyName = Literal["hourly_fixed_bracket_v1", "agentic_demo_v1"]
TradingCapabilityRoleName = Literal["internal_paper_agent", "broker_demo_agent"]


class TradingBrokerExposureQuery(GatewayModel):
    """Everything currently open on the configured execution backend.

    The counterpart to the action gateway: it answers "what is open right
    now" from the backend itself, never from the action journal, so a
    position an earlier cycle left behind is as visible as one this cycle
    opened. Omitting the symbol reads the whole account.
    """

    operation: Literal["broker_exposure"]
    symbol: str = Field(default="", max_length=64)
    execution_mode: TradingExecutionModeName | None = _CONFIGURED_EXECUTION_MODE_FIELD
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingCandlesQuery(GatewayModel):
    """Completed candles plus the developing one, for any MT5 period."""

    operation: Literal["candles"]
    timeframe: str | None = _TIMEFRAME_FIELD
    completed_count: int | None = _CONFIGURED_CANDLE_COUNT_FIELD
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingCandleBoundaryQuery(GatewayModel):
    """The live decision boundary: newest tick plus the newest few bars.

    Deliberately not a window read. It answers where the current candle
    starts and which one just closed, cheaply enough to repeat, and
    reports a series that is behind the tick feed instead of failing.
    """

    operation: Literal["candle_boundary"]
    timeframe: str | None = _TIMEFRAME_FIELD
    probe_bars: int | None = _CONFIGURED_PROBE_BARS_FIELD
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingHistoricalCandlesQuery(GatewayModel):
    """The bulk analysis window, with expected session closures named."""

    operation: Literal["historical_candles"]
    timeframe: str | None = _TIMEFRAME_FIELD
    count: int | None = _CONFIGURED_CANDLE_COUNT_FIELD
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingH1Query(GatewayModel):
    """Compatibility alias for ``candles`` on the H1 period."""

    operation: Literal["h1_candles"]
    completed_count: int = Field(default=200, ge=1, le=2_000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingH4Query(GatewayModel):
    """Compatibility alias for ``candles`` on the H4 period."""

    operation: Literal["h4_candles"]
    completed_count: int = Field(default=200, ge=1, le=2_000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingHistoricalTicksQuery(GatewayModel):
    operation: Literal["historical_ticks"]
    start_utc: datetime
    end_utc: datetime
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_range(self) -> "TradingHistoricalTicksQuery":
        if self.start_utc.tzinfo is None or self.end_utc.tzinfo is None:
            raise ValueError(
                "Trading historical tick timestamps must be timezone-aware"
            )
        if self.end_utc <= self.start_utc:
            raise ValueError("Trading historical tick end_utc must be after start_utc")
        return self


class TradingDeprecatedPortfolioQuery(GatewayModel):
    """Removed runtime virtual-portfolio reads kept only for an explicit
    deprecation response pointing at the offline replay reports."""

    operation: Literal["open_virtual_positions", "portfolio_status", "threshold_report"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


def _validate_period(model: Any) -> Any:
    for name in ("period_start_utc", "period_end_utc"):
        value = getattr(model, name, None)
        if value is not None and value.tzinfo is None:
            raise ValueError(f"Trading report {name} must be timezone-aware")
    start = getattr(model, "period_start_utc", None)
    end = getattr(model, "period_end_utc", None)
    if start is not None and end is not None and end <= start:
        raise ValueError("Trading report period_end_utc must be after period_start_utc")
    return model


class TradingPacketGetQuery(GatewayModel):
    operation: Literal["market_packet_get"]
    packet_id: str = Field(min_length=1, max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingPacketListQuery(GatewayModel):
    operation: Literal["market_packet_list"]
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingOutcomeGetQuery(GatewayModel):
    operation: Literal["outcome_get"]
    signal_id: str = Field(min_length=1, max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingOutcomeListQuery(GatewayModel):
    operation: Literal["outcome_list"]
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    status: (
        Literal[
            "RESOLVED_TP",
            "RESOLVED_SL",
            "UNRESOLVED_DATA_GAP",
            "AMBIGUOUS_WITHOUT_TICKS",
        ]
        | None
    ) = None
    experiment_id: str | None = Field(default=None, min_length=1, max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingRejectionListQuery(GatewayModel):
    operation: Literal["rejection_list"]
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingDataQualityQuery(GatewayModel):
    operation: Literal["data_quality"]
    start_utc: datetime
    end_utc: datetime
    max_gap_seconds: float = Field(default=300.0, gt=0, le=86_400)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_range(self) -> "TradingDataQualityQuery":
        if self.start_utc.tzinfo is None or self.end_utc.tzinfo is None:
            raise ValueError("Trading data-quality timestamps must be timezone-aware")
        if self.end_utc <= self.start_utc:
            raise ValueError("Trading data-quality end_utc must be after start_utc")
        return self


class TradingCalibrationReportQuery(GatewayModel):
    operation: Literal["calibration_report"]
    experiment_id: str | None = Field(default=None, min_length=1, max_length=64)
    period_start_utc: datetime | None = None
    period_end_utc: datetime | None = None
    period_basis: Literal["entry", "resolution"] = "resolution"
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_period(self) -> "TradingCalibrationReportQuery":
        return _validate_period(self)


class TradingReplayReportQuery(GatewayModel):
    operation: Literal["replay_report"]
    experiment_id: str | None = Field(default=None, min_length=1, max_length=64)
    threshold_start: int = Field(default=50, ge=50, le=99)
    threshold_end: int = Field(default=99, ge=50, le=99)
    minimum_sample: int = Field(default=30, ge=1, le=10_000)
    allow_stacking: bool = False
    fixed_notional_usd: float = Field(default=1.0, gt=0, le=1_000_000)
    per_trade_cost_usd: float = Field(default=0.0, ge=0, le=1_000)
    initial_equity_usd: float = Field(default=1_000.0, gt=0, le=100_000_000)
    period_start_utc: datetime | None = None
    period_end_utc: datetime | None = None
    period_basis: Literal["entry", "resolution"] = "resolution"
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_report(self) -> "TradingReplayReportQuery":
        if self.threshold_end < self.threshold_start:
            raise ValueError("threshold_end must be at least threshold_start")
        return _validate_period(self)


class TradingActionGetQuery(GatewayModel):
    operation: Literal["action_get"]
    action_id: str = Field(min_length=1, max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingActionListQuery(GatewayModel):
    operation: Literal["action_list"]
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    state: (
        Literal[
            "REQUESTED",
            "VALIDATED",
            "REJECTED",
            "SUBMITTING",
            "SUBMITTED",
            "BROKER_CONFIRMED",
            "FAILED",
            "RECONCILED",
        ]
        | None
    ) = None
    symbol: str | None = Field(default=None, min_length=1, max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingRuntimeStatusQuery(GatewayModel):
    operation: Literal["runtime_status"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingDemoPerformanceQuery(GatewayModel):
    operation: Literal["demo_performance"]
    limit: int = Field(default=50, ge=1, le=500)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingReconciliationQuery(GatewayModel):
    operation: Literal["reconciliation_report"]
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingCompanionGetQuery(GatewayModel):
    operation: Literal["companion_get"]
    companion_run_id: str = Field(min_length=1, max_length=64)
    sync: bool = True
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingCompanionListQuery(GatewayModel):
    operation: Literal["companion_list"]
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


TradingQueryRequest = Annotated[
    TradingHealthQuery
    | TradingConfigurationQuery
    | TradingBrokerExposureQuery
    | TradingSymbolsQuery
    | TradingSpecificationQuery
    | TradingTickQuery
    | TradingCandlesQuery
    | TradingCandleBoundaryQuery
    | TradingHistoricalCandlesQuery
    | TradingH1Query
    | TradingH4Query
    | TradingHistoricalTicksQuery
    | TradingDeprecatedPortfolioQuery
    | TradingPacketGetQuery
    | TradingPacketListQuery
    | TradingOutcomeGetQuery
    | TradingOutcomeListQuery
    | TradingRejectionListQuery
    | TradingDataQualityQuery
    | TradingCalibrationReportQuery
    | TradingReplayReportQuery
    | TradingActionGetQuery
    | TradingActionListQuery
    | TradingRuntimeStatusQuery
    | TradingDemoPerformanceQuery
    | TradingReconciliationQuery
    | TradingCompanionGetQuery
    | TradingCompanionListQuery,
    Field(discriminator="operation"),
]


class TradingSignalSubmitRequest(GatewayModel):
    """Packet-bound v2 signal submission: market facts are derived from
    the referenced stored packet, never supplied by the caller."""

    idempotency_key: str = Field(min_length=1, max_length=128)
    packet_id: str = Field(min_length=1, max_length=64)
    decision: Literal["LONG", "SHORT", "NO_TRADE"]
    confidence: int | None = Field(default=None, ge=50, le=99)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    reason: str = Field(min_length=1, max_length=4000)
    news_context: str = Field(default="", max_length=8000)
    model_version: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    policy_id: TradingPolicyName | None = _CONFIGURED_POLICY_FIELD
    execution_mode: TradingExecutionModeName | None = _CONFIGURED_EXECUTION_MODE_FIELD
    experiment_id: str = Field(default="exp1", min_length=1, max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingSignalGetRequest(GatewayModel):
    signal_id: str = Field(min_length=1, max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingSignalListRequest(GatewayModel):
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    status: Literal["submitted", "cancelled", "entered"] | None = None
    experiment_id: str | None = Field(default=None, min_length=1, max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingSignalCancelRequest(GatewayModel):
    signal_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TradingResearchSourceInput(GatewayModel):
    title: str = Field(min_length=1, max_length=500)
    reference: str = Field(min_length=1, max_length=2048)
    published_at_utc: datetime | None = None

    @model_validator(mode="after")
    def validate_published_at(self) -> "TradingResearchSourceInput":
        if self.published_at_utc is not None and self.published_at_utc.tzinfo is None:
            raise ValueError("published_at_utc must be timezone-aware")
        return self


class TradingCompanionStartRequest(GatewayModel):
    action: Literal["start"]
    idempotency_key: str = Field(min_length=1, max_length=128)
    task_invocation_id: str = Field(min_length=1, max_length=256)
    research_summary: str = Field(min_length=1, max_length=20_000)
    research_sources: list[TradingResearchSourceInput] = Field(
        default_factory=list, max_length=50
    )
    scheduled_for_utc: datetime | None = None
    completed_count: int | None = _CONFIGURED_CANDLE_COUNT_FIELD
    timeframe: str | None = _TIMEFRAME_FIELD
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_schedule(self) -> "TradingCompanionStartRequest":
        if self.scheduled_for_utc is not None and self.scheduled_for_utc.tzinfo is None:
            raise ValueError("scheduled_for_utc must be timezone-aware")
        return self


class TradingCompanionDecideRequest(GatewayModel):
    action: Literal["decide"]
    companion_run_id: str = Field(min_length=1, max_length=64)
    signal_idempotency_key: str = Field(min_length=1, max_length=128)
    decision: Literal["LONG", "SHORT", "NO_TRADE"]
    confidence: int | None = Field(default=None, ge=50, le=99)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    reason: str = Field(min_length=1, max_length=4000)
    news_context: str = Field(default="", max_length=8000)
    model_version: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    policy_id: TradingPolicyName | None = _CONFIGURED_POLICY_FIELD
    execution_mode: TradingExecutionModeName | None = _CONFIGURED_EXECUTION_MODE_FIELD
    experiment_id: str = Field(default="exp1", min_length=1, max_length=64)
    submitted_at_utc: datetime | None = None
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_decision(self) -> "TradingCompanionDecideRequest":
        values = (self.confidence, self.stop_loss, self.take_profit)
        if self.decision == "NO_TRADE" and any(value is not None for value in values):
            raise ValueError("NO_TRADE must not include confidence or bracket prices")
        if self.decision != "NO_TRADE" and any(value is None for value in values):
            raise ValueError(
                "Directional decisions require confidence, stop_loss, and take_profit"
            )
        if self.submitted_at_utc is not None and self.submitted_at_utc.tzinfo is None:
            raise ValueError("submitted_at_utc must be timezone-aware")
        return self


class TradingCompanionReviewRequest(GatewayModel):
    action: Literal["review"]
    companion_run_id: str = Field(min_length=1, max_length=64)
    approval_idempotency_key: str = Field(min_length=1, max_length=128)
    decision: Literal["APPROVED", "REJECTED"]
    reason: str = Field(min_length=1, max_length=4000)
    model_version: str = Field(min_length=1, max_length=128)
    prompt_version: str = Field(min_length=1, max_length=128)
    approved_at_utc: datetime | None = None
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_approved_at(self) -> "TradingCompanionReviewRequest":
        if self.approved_at_utc is not None and self.approved_at_utc.tzinfo is None:
            raise ValueError("approved_at_utc must be timezone-aware")
        return self


class TradingCompanionExecuteRequest(GatewayModel):
    action: Literal["execute"]
    companion_run_id: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)
    volume_lots: float = Field(gt=0, le=1_000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


TradingCompanionActionRequest = Annotated[
    TradingCompanionStartRequest
    | TradingCompanionDecideRequest
    | TradingCompanionReviewRequest
    | TradingCompanionExecuteRequest,
    Field(discriminator="action"),
]


_TRADING_ACTION_TYPES = Literal[
    "market_entry",
    "pending_limit_entry",
    "pending_stop_entry",
    "pending_stop_limit_entry",
    "cancel_pending",
    "replace_pending",
    "close_full",
    "close_partial",
    "scale_in",
    "scale_out",
    "set_sltp",
    "modify_sltp",
    "remove_sltp",
    "break_even",
    "lock_profit",
    "set_multiple_targets",
    "reverse",
    "hedge_open",
    "hedge_close",
    "time_exit",
    "condition_exit",
    "news_exit",
    "trailing_stop_set",
    "trailing_stop_cancel",
    "flatten_symbol",
    "flatten_account",
    "emergency_close_all",
]


class TradingActionSubmitRequest(GatewayModel):
    """One guarded model action; origin is always recorded as model."""

    idempotency_key: str = Field(min_length=1, max_length=128)
    action_type: _TRADING_ACTION_TYPES
    capability_role: TradingCapabilityRoleName | None = (
        _CONFIGURED_CAPABILITY_ROLE_FIELD
    )
    execution_mode: TradingExecutionModeName | None = _CONFIGURED_EXECUTION_MODE_FIELD
    policy_id: TradingPolicyName | None = _CONFIGURED_POLICY_FIELD
    experiment_id: str = Field(default="exp1", min_length=1, max_length=64)
    symbol: str = Field(default="", max_length=64)
    signal_id: str | None = Field(default=None, min_length=1, max_length=64)
    direction: Literal["LONG", "SHORT"] | None = None
    volume_lots: float | None = Field(default=None, gt=0, le=1_000)
    price: float | None = Field(default=None, gt=0)
    stop_loss: float | None = Field(default=None, gt=0)
    take_profit: float | None = Field(default=None, gt=0)
    position_ticket: int | None = Field(default=None, ge=1)
    order_ticket: int | None = Field(default=None, ge=1)
    params: dict[str, Any] = Field(default_factory=dict)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_capability_role(self) -> "TradingActionSubmitRequest":
        """A stated role must agree with a stated mode.

        Either may be omitted and resolved from configuration, but a caller
        that spells out both and contradicts itself is refused rather than
        silently corrected: which of the two it meant is not knowable here,
        and guessing would decide where a real order goes.
        """
        expected = {
            "internal_paper": "internal_paper_agent",
            "broker_demo": "broker_demo_agent",
        }
        if (
            self.execution_mode is not None
            and self.capability_role is not None
            and self.capability_role != expected[self.execution_mode]
        ):
            raise ValueError(
                f"capability_role {self.capability_role!r} contradicts "
                f"execution_mode {self.execution_mode!r}; omit one or "
                f"use {expected[self.execution_mode]!r}"
            )
        return self


class TradingRuntimeControlRequest(GatewayModel):
    action: Literal[
        "start",
        "stop",
        "status",
        "kill_switch_on",
        "kill_switch_off",
        "supervise_now",
        "analyze_now",
    ]
    reason: str = Field(default="", max_length=1000)
    execution_mode: TradingExecutionModeName | None = _CONFIGURED_EXECUTION_MODE_FIELD
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_reason(self) -> "TradingRuntimeControlRequest":
        if self.action in {"stop", "kill_switch_on", "kill_switch_off"} and (
            not self.reason.strip()
        ):
            raise ValueError(f"Trading runtime {self.action} requires a reason")
        return self


class SupervisorStatusQuery(GatewayModel):
    operation: Literal["status"]
    supervisor_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SupervisorResultQuery(GatewayModel):
    operation: Literal["result"]
    supervisor_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SupervisorResumePromptQuery(GatewayModel):
    operation: Literal["resume_prompt"]
    supervisor_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SupervisorEventsQuery(GatewayModel):
    operation: Literal["events"]
    supervisor_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=50, ge=1, le=500)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SupervisorNotificationsQuery(GatewayModel):
    operation: Literal["notifications"]
    supervisor_id: str = Field(min_length=1, max_length=128)
    delivery_status: str = Field(default="", max_length=64)
    limit: int = Field(default=50, ge=1, le=500)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


SupervisorQueryRequest = Annotated[
    SupervisorStatusQuery
    | SupervisorResultQuery
    | SupervisorResumePromptQuery
    | SupervisorEventsQuery
    | SupervisorNotificationsQuery,
    Field(discriminator="operation"),
]


class SupervisorStartAction(GatewayModel):
    action: Literal["start"]
    repo_name: str = Field(min_length=1, max_length=128)
    objective: str = Field(min_length=1, max_length=10_000)
    task: str = Field(min_length=1, max_length=20_000)
    constraints: str = Field(default="", max_length=20_000)
    source_run_id: str = Field(default="", max_length=128)
    autonomy_profile: Literal["permissive"] = "permissive"


class SupervisorResumeAction(GatewayModel):
    action: Literal["resume"]
    supervisor_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SupervisorPauseAction(GatewayModel):
    action: Literal["pause"]
    supervisor_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SupervisorCancelAction(GatewayModel):
    action: Literal["cancel"]
    supervisor_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


SupervisorActionRequest = Annotated[
    SupervisorStartAction
    | SupervisorResumeAction
    | SupervisorPauseAction
    | SupervisorCancelAction,
    Field(discriminator="action"),
]


class RepoStatusQuery(GatewayModel):
    operation: Literal["status"]
    repo_name: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RepoCompactStatusQuery(GatewayModel):
    operation: Literal["compact_status"]
    repo_name: str = Field(min_length=1, max_length=128)
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RepoPatchStatusQuery(GatewayModel):
    operation: Literal["patch_status"]
    repo_name: str = Field(min_length=1, max_length=128)
    patch_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RepoListFilesQuery(GatewayModel):
    operation: Literal["list_files"]
    repo_name: str = Field(min_length=1, max_length=128)
    directory: str = Field(default="", max_length=1024)
    max_results: int = Field(default=500, ge=1, le=5_000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RepoReadFilesQuery(GatewayModel):
    operation: Literal["read_files"]
    repo_name: str = Field(min_length=1, max_length=128)
    requests: list[dict[str, Any]] = Field(min_length=1, max_length=20)
    response_budget_bytes: int = Field(default=48 * 1024, ge=48 * 1024, le=128 * 1024)


class RepoSearchTextQuery(GatewayModel):
    operation: Literal["search_text"]
    repo_name: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=10_000)
    directory: str = Field(default="", max_length=1024)
    file_path: str = Field(default="", max_length=1024)
    max_results: int = Field(default=50, ge=1, le=500)
    case_sensitive: bool = False
    file_patterns: list[str] = Field(default_factory=list, max_length=20)
    budget_ms: int = Field(default=5_000, ge=100, le=30_000)
    cursor: str = Field(default="", max_length=4096)
    response_budget_bytes: int = Field(default=16 * 1024, ge=16 * 1024, le=16 * 1024)

    @model_validator(mode="after")
    def validate_scope(self) -> "RepoSearchTextQuery":
        if self.file_path and (self.directory or self.file_patterns):
            raise ValueError(
                "file_path cannot be combined with directory or file_patterns"
            )
        return self


class RepoRecentFilesQuery(GatewayModel):
    operation: Literal["recent_files"]
    repo_name: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=50, ge=1, le=500)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RepoDiffQuery(GatewayModel):
    operation: Literal["diff"]
    repo_name: str = Field(min_length=1, max_length=128)
    path: str = Field(default="", max_length=1024)
    staged: bool = False
    view: Literal["summary", "hunk", "full", "legacy"] = "summary"
    snapshot_id: str = Field(default="", max_length=128)
    hunk_id: str = Field(default="", max_length=64)
    response_budget_bytes: int = Field(default=32 * 1024, ge=32 * 1024, le=32 * 1024)

    @model_validator(mode="after")
    def validate_diff_view(self) -> "RepoDiffQuery":
        if self.view == "hunk" and (not self.snapshot_id or not self.hunk_id):
            raise ValueError("hunk view requires snapshot_id and hunk_id")
        if self.view == "full" and not self.snapshot_id:
            raise ValueError("full view requires snapshot_id")
        if self.view == "legacy" and (self.snapshot_id or self.hunk_id):
            raise ValueError("legacy view cannot use snapshot-bound retrieval")
        return self


class RepoLogQuery(GatewayModel):
    operation: Literal["log"]
    repo_name: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=20, ge=1, le=500)
    path: str = Field(default="", max_length=1024)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RepoCommitRangeQuery(GatewayModel):
    operation: Literal["commit_range"]
    repo_name: str = Field(min_length=1, max_length=128)
    base_commit: str = Field(min_length=40, max_length=64)
    head_commit: str = Field(min_length=40, max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


RepoQueryRequest = Annotated[
    RepoStatusQuery
    | RepoCompactStatusQuery
    | RepoPatchStatusQuery
    | RepoListFilesQuery
    | RepoReadFilesQuery
    | RepoSearchTextQuery
    | RepoRecentFilesQuery
    | RepoDiffQuery
    | RepoLogQuery
    | RepoCommitRangeQuery,
    Field(discriminator="operation"),
]


class RepoPatchPreview(GatewayModel):
    operation: Literal["patch"]
    repo_name: str = Field(min_length=1, max_length=128)
    operations: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    commit_title: str = Field(default="", max_length=512)
    commit_description: str = Field(default="", max_length=10_000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RepoCreateFilePreview(GatewayModel):
    operation: Literal["create_file"]
    repo_name: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(min_length=1, max_length=2_000_000)
    commit_title: str = Field(default="", max_length=512)
    commit_description: str = Field(default="", max_length=10_000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RepoRemoveFilePreview(GatewayModel):
    operation: Literal["remove_file"]
    repo_name: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=1024)
    expected_sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    commit_title: str = Field(default="", max_length=512)
    commit_description: str = Field(default="", max_length=10_000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RepoCleanupPreview(GatewayModel):
    operation: Literal["cleanup"]
    repo_name: str = Field(min_length=1, max_length=128)
    roots: list[str] = Field(default_factory=list, max_length=50)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


RepoPreviewRequest = Annotated[
    RepoPatchPreview
    | RepoCreateFilePreview
    | RepoRemoveFilePreview
    | RepoCleanupPreview,
    Field(discriminator="operation"),
]


class RepoPreviewedChangeApply(GatewayModel):
    operation: Literal["previewed_change"]
    repo_name: str = Field(min_length=1, max_length=128)
    patch_id: str = Field(min_length=1, max_length=128)
    commit_mode: Literal["auto", "manual"] = "auto"


class RepoCleanupApply(GatewayModel):
    operation: Literal["cleanup"]
    repo_name: str = Field(min_length=1, max_length=128)
    cleanup_id: str = Field(min_length=1, max_length=128)
    commit_mode: Literal["auto", "manual"] = "auto"
    commit_title: str = Field(default="", max_length=512)
    commit_description: str = Field(default="", max_length=10_000)


class RepoRevertApply(GatewayModel):
    operation: Literal["revert"]
    repo_name: str = Field(min_length=1, max_length=128)
    patch_id: str = Field(min_length=1, max_length=128)
    commit_mode: Literal["auto", "manual"] = "auto"
    commit_title: str = Field(default="", max_length=512)
    commit_description: str = Field(default="", max_length=10_000)


class RepoMoveFileApply(GatewayModel):
    operation: Literal["move_file"]
    repo_name: str = Field(min_length=1, max_length=128)
    source_path: str = Field(min_length=1, max_length=1024)
    destination_path: str = Field(min_length=1, max_length=1024)
    expected_sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    commit_mode: Literal["auto", "manual"] = "auto"
    commit_title: str = Field(default="", max_length=512)
    commit_description: str = Field(default="", max_length=10_000)


RepoApplyRequest = Annotated[
    RepoPreviewedChangeApply | RepoCleanupApply | RepoRevertApply | RepoMoveFileApply,
    Field(discriminator="operation"),
]


class RepoCreateBranchCommit(GatewayModel):
    operation: Literal["create_branch"]
    repo_name: str = Field(min_length=1, max_length=128)
    branch_name: str = Field(min_length=1, max_length=255)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class RepoCommitSelected(GatewayModel):
    operation: Literal["commit_selected"]
    repo_name: str = Field(min_length=1, max_length=128)
    files: list[str] = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=10_000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


RepoCommitRequest = Annotated[
    RepoCreateBranchCommit | RepoCommitSelected, Field(discriminator="operation")
]


class ParallelPowerShellChild(GatewayModel):
    idempotency_key: str = Field(default="", max_length=128)
    profile_id: str = Field(default="powershell", min_length=1, max_length=128)
    argv: list[str] = Field(default_factory=list, max_length=10_000)
    working_directory: str = Field(default="", max_length=32_768)
    environment: dict[str, str] = Field(default_factory=dict, max_length=10_000)
    stdin_text: str | None = Field(default=None, max_length=2_000_000)
    stdin_base64: str | None = Field(default=None, max_length=2_700_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=604_800)

    @model_validator(mode="after")
    def validate_stdin_mode(self) -> "ParallelPowerShellChild":
        if self.stdin_text is not None and self.stdin_base64 is not None:
            raise ValueError("Specify either stdin_text or stdin_base64, not both")
        return self


class ParallelPowerShellStart(GatewayModel):
    operation: Literal["powershell_group"]
    repo_name: str = Field(min_length=1, max_length=128)
    children: list[ParallelPowerShellChild] = Field(min_length=1, max_length=1_000)
    requested_concurrency: int | None = Field(default=None, ge=1, le=1_000)
    repository_lock_policy: Literal["none"] = "none"
    failure_policy: Literal["continue_all", "cancel_remaining_on_failure"] = (
        "continue_all"
    )


class LocalPowerShellStart(GatewayModel):
    operation: Literal["powershell"]
    repo_name: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(default="powershell", min_length=1, max_length=128)
    argv: list[str] = Field(default_factory=list, max_length=10_000)
    working_directory: str = Field(default="", max_length=32_768)
    environment: dict[str, str] = Field(default_factory=dict, max_length=10_000)
    stdin_text: str | None = Field(default=None, max_length=2_000_000)
    stdin_base64: str | None = Field(default=None, max_length=2_700_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=604_800)
    return_when: Literal["accepted", "terminal_or_timeout"] = "accepted"
    wait_seconds: float = Field(default=0.0, ge=0.0, le=20.0)

    @model_validator(mode="after")
    def validate_stdin_mode(self) -> "LocalPowerShellStart":
        if self.stdin_text is not None and self.stdin_base64 is not None:
            raise ValueError("Specify either stdin_text or stdin_base64, not both")
        return self


class HermesCompanionStart(GatewayModel):
    operation: Literal["hermes_companion"]
    repo_name: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(default="", max_length=128)
    checkout: str = Field(min_length=1, max_length=32_768)
    hermes_home: str = Field(default="", max_length=32_768)
    companion_operation: Literal[
        "handshake", "tool_search", "tool_describe", "tool_call"
    ]
    payload: dict[str, Any] = Field(default_factory=dict, max_length=100)
    expected_registry_generation: int | None = Field(default=None, ge=0)
    expected_schema_hash: str = Field(default="", max_length=64)
    timeout_seconds: int = Field(default=120, ge=1, le=600)


class HermesServiceStart(GatewayModel):
    operation: Literal["hermes_service"]
    session_id: str = Field(min_length=1, max_length=256)
    service_operation: Literal["tool_search", "tool_describe", "tool_call"]
    payload: dict[str, Any] = Field(default_factory=dict, max_length=100)
    expected_registry_generation: int = Field(ge=0)
    expected_schema_hash: str = Field(min_length=64, max_length=64)
    worker_wait_timeout_seconds: float = Field(default=30.0, gt=0, le=600)


class RemotePowerShellStart(GatewayModel):
    operation: Literal["remote_powershell"]
    host_id: str = Field(min_length=1, max_length=128)
    executable_path: str = Field(min_length=1, max_length=32_768)
    argv: list[str] = Field(default_factory=list, max_length=10_000)
    working_directory: str = Field(default="", max_length=32_768)
    environment: dict[str, str] = Field(default_factory=dict, max_length=10_000)
    stdin_base64: str | None = Field(default=None, max_length=2_700_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=604_800)


RunStartRequest = Annotated[
    LocalPowerShellStart
    | RemotePowerShellStart
    | ParallelPowerShellStart
    | HermesCompanionStart
    | HermesServiceStart,
    Field(discriminator="operation"),
]


class TaskCapabilitiesQuery(GatewayModel):
    operation: Literal["capabilities"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TaskStatusQuery(GatewayModel):
    operation: Literal["status"]
    task_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TaskResultQuery(GatewayModel):
    operation: Literal["result"]
    task_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TaskEvidenceQuery(GatewayModel):
    """Retrieve one complete bounded EvidenceSubmission from a reasoning Task."""

    operation: Literal["evidence"]
    task_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=64 * 1024, ge=1024, le=64 * 1024)


class TaskEventsQuery(GatewayModel):
    operation: Literal["events"]
    task_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    limit: int = Field(default=20, ge=1, le=500)
    after_id: int | None = Field(default=None, ge=0)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TaskLinksQuery(GatewayModel):
    operation: Literal["links"]
    task_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    limit: int = Field(default=50, ge=1, le=200)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TaskQuarantineQuery(GatewayModel):
    """Owner-facing quarantine evidence. Project scope is mandatory here."""

    operation: Literal["quarantine"]
    project_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=50, ge=1, le=200)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


TaskQueryRequest = Annotated[
    TaskCapabilitiesQuery
    | TaskStatusQuery
    | TaskResultQuery
    | TaskEvidenceQuery
    | TaskEventsQuery
    | TaskLinksQuery
    | TaskQuarantineQuery,
    Field(discriminator="operation"),
]


class TaskDurableCommandStart(GatewayModel):
    """Start one canonical task backed by the existing durable run engine."""

    operation: Literal["start"]
    controller_request_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    task_kind: Literal["durable_command"] = "durable_command"
    backend_kind: Literal["soma_durable_run"] = "soma_durable_run"
    repo_name: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(default="powershell", min_length=1, max_length=128)
    argv: list[str] = Field(default_factory=list, max_length=10_000)
    working_directory: str = Field(default="", max_length=32_768)
    environment: dict[str, str] = Field(default_factory=dict, max_length=10_000)
    stdin_text: str | None = Field(default=None, max_length=2_000_000)
    stdin_base64: str | None = Field(default=None, max_length=2_700_000)
    timeout_seconds: int | None = Field(default=None, ge=1, le=604_800)
    parent_task_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_stdin_mode(self) -> "TaskDurableCommandStart":
        if self.stdin_text is not None and self.stdin_base64 is not None:
            raise ValueError("Specify either stdin_text or stdin_base64, not both")
        return self


class TaskReasoningStart(GatewayModel):
    """Start one owner-activated read-only repository reasoning task."""

    operation: Literal["start_reasoning"]
    controller_request_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    task_kind: Literal["reasoning"] = "reasoning"
    backend_kind: Literal["soma_reasoning"] = "soma_reasoning"
    repo_name: str = Field(min_length=1, max_length=128)
    objective: str = Field(min_length=1, max_length=16_384)
    instructions: str = Field(default="", max_length=16_384)
    parent_task_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TaskCancelCommand(GatewayModel):
    """State-version-guarded cancellation delegated to the backend authority."""

    operation: Literal["cancel"]
    task_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    if_state_version: int = Field(ge=0)
    reason: str = Field(default="", max_length=512)
    controller_request_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TaskSteerCommand(GatewayModel):
    """Version-guarded steering for one exact bound provider session."""

    operation: Literal["steer"]
    project_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    if_state_version: int = Field(ge=0)
    session_binding_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    sender_ref: str = Field(min_length=1, max_length=512)
    recipient_ref: str = Field(min_length=1, max_length=512)
    payload: str = Field(min_length=1, max_length=1_000_000)
    checkpoint_id: str = Field(default="", max_length=128)
    mandate_ref: str = Field(default="", max_length=512)
    mandate_version: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TaskSupplyInputCommand(GatewayModel):
    """Exact acknowledged input for one open controller checkpoint."""

    operation: Literal["supply_input"]
    project_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    if_state_version: int = Field(ge=0)
    session_binding_id: str = Field(min_length=1, max_length=128)
    checkpoint_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    sender_ref: str = Field(min_length=1, max_length=512)
    recipient_ref: str = Field(min_length=1, max_length=512)
    payload: str = Field(min_length=1, max_length=1_000_000)
    mandate_ref: str = Field(default="", max_length=512)
    mandate_version: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TaskRecoveryResolve(GatewayModel):
    """Owner-only terminal resolution for one unresolved scoped task."""

    operation: Literal["resolve_recovery"]
    project_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    if_state_version: int = Field(ge=0)
    successor_task_id: str = Field(min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class TaskQuarantineAdjudicate(GatewayModel):
    """Owner-only disposition recorded beside a preserved quarantine record.

    This never returns a quarantined record to an active state. `project_id`,
    the exact quarantined identity, a reason, and an idempotency key are all
    mandatory, so the operation cannot be issued speculatively.
    """

    operation: Literal["adjudicate_quarantine"]
    project_id: str = Field(min_length=1, max_length=128)
    record_kind: Literal["task_reservation", "run_attempt"]
    record_id: str = Field(min_length=1, max_length=128)
    disposition: Literal["acknowledged", "superseded"]
    reason: str = Field(min_length=1, max_length=512)
    idempotency_key: str = Field(min_length=1, max_length=128)
    successor_task_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_successor(self) -> "TaskQuarantineAdjudicate":
        if self.disposition == "superseded" and not self.successor_task_id:
            raise ValueError(
                "successor_task_id is required for disposition 'superseded'"
            )
        if self.disposition == "acknowledged" and self.successor_task_id:
            raise ValueError(
                "successor_task_id is only valid with disposition 'superseded'"
            )
        return self


TaskActionRequest = Annotated[
    TaskDurableCommandStart
    | TaskReasoningStart
    | TaskCancelCommand
    | TaskSteerCommand
    | TaskSupplyInputCommand
    | TaskRecoveryResolve
    | TaskQuarantineAdjudicate,
    Field(discriminator="operation"),
]


class CompanyCapabilitiesQuery(GatewayModel):
    operation: Literal["capabilities"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class CompanyScopedQuery(GatewayModel):
    company_id: str = Field(min_length=1, max_length=128)
    mission_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class CompanyMissionStatusQuery(CompanyScopedQuery):
    operation: Literal["mission_status"]


class CompanyCurrentPlanQuery(CompanyScopedQuery):
    operation: Literal["current_plan"]


class CompanyWorkPackageQuery(CompanyScopedQuery):
    operation: Literal["work_package"]
    work_package_id: str = Field(min_length=1, max_length=128)


class CompanyOutcomeStatusQuery(CompanyScopedQuery):
    operation: Literal["outcome_status"]
    outcome_id: str = Field(min_length=1, max_length=128)


class CompanyAcceptanceCommitQuery(CompanyScopedQuery):
    operation: Literal["acceptance_commit"]
    acceptance_commit_id: str = Field(min_length=1, max_length=128)


class CompanyReconciliationReceiptQuery(CompanyScopedQuery):
    operation: Literal["reconciliation_receipt"]
    reconciliation_id: str = Field(min_length=1, max_length=128)


CompanyQueryRequest = Annotated[
    CompanyCapabilitiesQuery
    | CompanyMissionStatusQuery
    | CompanyCurrentPlanQuery
    | CompanyWorkPackageQuery
    | CompanyOutcomeStatusQuery
    | CompanyAcceptanceCommitQuery
    | CompanyReconciliationReceiptQuery,
    Field(discriminator="operation"),
]


class _CompanyWriteBase(GatewayModel):
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class CompanyBootstrapAction(_CompanyWriteBase):
    operation: Literal["bootstrap_kernel"]
    controller_request_id: str = Field(min_length=1, max_length=128)
    company_key: str = Field(min_length=1, max_length=128)
    company_display_name: str = Field(min_length=1, max_length=500)
    mission_key: str = Field(min_length=1, max_length=128)
    mission_contract: dict[str, Any]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    executive_authority_ref: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _bound_mission_contract(self) -> "CompanyBootstrapAction":
        encoded = json.dumps(
            self.mission_contract,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        if len(encoded) > 200_000:
            raise ValueError("mission_contract exceeds 200000 UTF-8 bytes")
        return self


class CompanyAcceptPlanRevisionAction(_CompanyWriteBase):
    operation: Literal["accept_plan_revision"]
    company_id: str = Field(min_length=1, max_length=128)
    mission_id: str = Field(min_length=1, max_length=128)
    expected_current_plan_revision_id: str | None = Field(default=None, max_length=128)
    expected_plan_state_version: int = Field(ge=0)
    expected_kernel_state_version: int = Field(ge=0)
    project_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    controller_request_id: str = Field(min_length=1, max_length=128)
    accepted_by_ref: str = Field(min_length=1, max_length=128)
    acceptance_basis_ref: str = Field(min_length=1, max_length=2048)
    plan_contract_base: dict[str, Any]
    graph_manifest: dict[str, Any]
    work_package_contracts: dict[str, dict[str, Any]] = Field(max_length=32)
    deliberation_ref: str = Field(default="", max_length=2048)
    deliberation_hash: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def _bound_plan_payload(self) -> "CompanyAcceptPlanRevisionAction":
        for name in ("plan_contract_base", "graph_manifest", "work_package_contracts"):
            encoded = json.dumps(
                getattr(self, name),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            if len(encoded) > 500_000:
                raise ValueError(f"{name} exceeds 500000 UTF-8 bytes")
        return self


class CompanyReserveAttemptAction(_CompanyWriteBase):
    operation: Literal["reserve_attempt"]
    company_id: str = Field(min_length=1, max_length=128)
    mission_id: str = Field(min_length=1, max_length=128)
    work_package_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    executive_authority_ref: str = Field(min_length=1, max_length=128)
    controller_request_id: str = Field(min_length=1, max_length=128)
    expected_plan_revision_id: str | None = Field(default=None, max_length=128)
    expected_plan_state_version: int | None = Field(default=None, ge=0)
    repo_name: str = Field(min_length=1, max_length=128)
    # Frozen legacy wire field only. The public reserve_attempt route is disabled;
    # this field does not define the corrected provider-neutral Company architecture.
    reasoning_spec: ReasoningSpecV1
    supersedes_attempt_id: str | None = Field(default=None, max_length=128)
    evidence_candidates: dict[str, EvidenceAvailableCandidateV1] = Field(
        default_factory=dict, max_length=128
    )
    published_success_candidates: dict[str, PublishedSuccessCandidateV1] = Field(
        default_factory=dict, max_length=128
    )


class CompanyAcceptOutcomeAction(_CompanyWriteBase):
    operation: Literal["accept_outcome"]
    controller_request_id: str = Field(min_length=1, max_length=128)
    company_id: str = Field(min_length=1, max_length=128)
    mission_id: str = Field(min_length=1, max_length=128)
    plan_revision_id: str = Field(min_length=1, max_length=128)
    work_package_id: str = Field(min_length=1, max_length=128)
    outcome_id: str = Field(min_length=1, max_length=128)
    attempt_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    backend_kind: Literal["soma_durable_run", "soma_reasoning"]
    backend_ref: str = Field(min_length=1, max_length=256)
    project_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    expected_kernel_state_version: int = Field(ge=0)
    result_published_hash: str = Field(min_length=64, max_length=64)
    public_result_source_sha256: str = Field(min_length=64, max_length=64)
    acceptance_authority_ref: str = Field(min_length=1, max_length=128)
    acceptance_basis_ref: str = Field(min_length=1, max_length=2048)
    acceptance_basis_hash: str = Field(min_length=64, max_length=64)


class CompanyReconcileOneAction(_CompanyWriteBase):
    operation: Literal["reconcile_one"]
    company_id: str = Field(min_length=1, max_length=128)
    mission_id: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(min_length=1, max_length=128)
    scope_generation: int = Field(ge=1)
    executive_authority_ref: str = Field(min_length=1, max_length=128)
    trigger_kind: Literal["owner_turn", "package_completion"]
    trigger_ref: str = Field(min_length=1, max_length=2048)
    expected_kernel_state_version: int = Field(ge=0)
    selected_transition: Literal["no_op", "acceptance_candidate_ready"]
    target_ref: str = Field(default="", max_length=2048)
    target_hash: str = Field(default="", max_length=64)


CompanyActionRequest = Annotated[
    CompanyBootstrapAction
    | CompanyAcceptPlanRevisionAction
    | CompanyReserveAttemptAction
    | CompanyAcceptOutcomeAction
    | CompanyReconcileOneAction,
    Field(discriminator="operation"),
]


class DockerCapabilitiesQuery(GatewayModel):
    operation: Literal["capabilities"]
    repo_name: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class DockerHealthQuery(GatewayModel):
    operation: Literal["health"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class DockerInspectQuery(GatewayModel):
    operation: Literal["inspect"]
    repo_name: str = Field(min_length=1, max_length=128)
    inspection: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    target: str = Field(default="", max_length=512)
    service: str = Field(default="", max_length=256)
    tail: int = Field(default=200, ge=1, le=20_000)
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


DockerQueryRequest = Annotated[
    DockerCapabilitiesQuery | DockerHealthQuery | DockerInspectQuery,
    Field(discriminator="operation"),
]


class DockerActionBase(GatewayModel):
    repo_name: str = Field(min_length=1, max_length=128)
    target: str = Field(default="", max_length=512)
    destination: str = Field(default="", max_length=1024)
    services: list[str] = Field(default_factory=list, max_length=50)
    command_id: str = Field(default="", max_length=128)
    context: str = Field(default=".", max_length=1024)
    dockerfile: str = Field(default="", max_length=1024)
    build: bool = False
    force: bool = False
    confirmation: str = Field(default="", max_length=128)


class DockerComposeAction(DockerActionBase):
    action: Literal[
        "compose_build",
        "compose_up",
        "compose_down",
        "compose_start",
        "compose_stop",
        "compose_restart",
        "compose_pause",
        "compose_unpause",
        "compose_kill",
        "compose_pull",
        "compose_down_volumes",
        "compose_rm",
    ]


class DockerExecAction(DockerActionBase):
    action: Literal["compose_exec", "container_exec"]
    command_id: str = Field(min_length=1, max_length=128)


class DockerImageAction(DockerActionBase):
    action: Literal[
        "image_build", "image_pull", "image_tag", "image_push", "image_remove"
    ]
    target: str = Field(min_length=1, max_length=512)


class DockerContainerAction(DockerActionBase):
    action: Literal[
        "container_start",
        "container_stop",
        "container_restart",
        "container_pause",
        "container_unpause",
        "container_kill",
        "container_remove",
    ]
    target: str = Field(min_length=1, max_length=512)


class DockerNetworkVolumeAction(DockerActionBase):
    action: Literal[
        "network_create", "network_remove", "volume_create", "volume_remove"
    ]
    target: str = Field(min_length=1, max_length=512)


class DockerPruneAction(DockerActionBase):
    action: Literal[
        "builder_prune",
        "container_prune",
        "image_prune",
        "network_prune",
        "volume_prune",
        "system_prune",
        "system_prune_volumes",
    ]


DockerActionRequest = Annotated[
    DockerComposeAction
    | DockerExecAction
    | DockerImageAction
    | DockerContainerAction
    | DockerNetworkVolumeAction
    | DockerPruneAction,
    Field(discriminator="action"),
]


class CloudflareCapabilitiesQuery(GatewayModel):
    operation: Literal["capabilities"]
    repo_name: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class CloudflareHealthQuery(GatewayModel):
    operation: Literal["health"]
    repo_name: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class CloudflareInspectQuery(GatewayModel):
    operation: Literal["inspect"]
    repo_name: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(min_length=1, max_length=128)
    inspection: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    resource_id: str = Field(default="", max_length=256)
    name: str = Field(default="", max_length=256)
    record_type: str = Field(default="", max_length=32)
    zone_id: str = Field(default="", max_length=64)
    zone_name: str = Field(default="", max_length=253)
    since_minutes: int = Field(default=60, ge=1, le=43_200)
    page: int = Field(default=1, ge=1, le=10_000)
    per_page: int = Field(default=100, ge=1, le=100)
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


CloudflareQueryRequest = Annotated[
    CloudflareCapabilitiesQuery | CloudflareHealthQuery | CloudflareInspectQuery,
    Field(discriminator="operation"),
]


class CloudflareActionBase(GatewayModel):
    repo_name: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(default="", max_length=256)
    zone_id: str = Field(default="", max_length=64)
    zone_name: str = Field(default="", max_length=253)
    payload: dict[str, Any] = Field(default_factory=dict)
    confirmation: str = Field(default="", max_length=128)


class CloudflareDnsAction(CloudflareActionBase):
    action: Literal[
        "create_dns_record",
        "update_dns_record",
        "delete_dns_record",
        "dns_create",
        "dns_update",
        "dns_delete",
        "dns_batch",
    ]


class CloudflareCacheAction(CloudflareActionBase):
    action: Literal["purge_cache", "cache_purge"]


class CloudflareZoneAction(CloudflareActionBase):
    action: Literal[
        "update_ssl_settings",
        "zone_setting_update",
        "dnssec_enable",
        "dnssec_disable",
        "ssl_universal_update",
    ]


class CloudflareRulesetAction(CloudflareActionBase):
    action: Literal[
        "ruleset_create",
        "ruleset_update",
        "ruleset_delete",
        "ruleset_rule_add",
        "ruleset_rule_update",
        "ruleset_rule_delete",
    ]


class CloudflareEdgeAction(CloudflareActionBase):
    action: Literal[
        "turnstile_create",
        "turnstile_update",
        "turnstile_rotate_secret",
        "turnstile_delete",
        "update_turnstile_widget",
        "create_tunnel",
        "tunnel_create",
        "tunnel_config_update",
        "tunnel_delete",
        "tunnel_route_create",
        "tunnel_route_delete",
    ]


CloudflareActionRequest = Annotated[
    CloudflareDnsAction
    | CloudflareCacheAction
    | CloudflareZoneAction
    | CloudflareRulesetAction
    | CloudflareEdgeAction,
    Field(discriminator="action"),
]


class SSHCapabilitiesQuery(GatewayModel):
    operation: Literal["capabilities"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SSHExecutionPolicyGatewayRequest(GatewayModel):
    """Strict reusable contract for selecting an SSH execution policy."""

    model_config = ConfigDict(extra="forbid", strict=True)

    execution_mode: SSHExecutionMode = "structured"
    autonomy_profile: AutonomyProfile = "permissive"


SSHPolicyGatewayRequest = SSHExecutionPolicyGatewayRequest
SSHExecutionPolicyRequest = SSHExecutionPolicyGatewayRequest

MAX_REVIEWED_SSH_SCRIPT_BYTES = 64 * 1024
MAX_REVIEWED_SSH_SCRIPT_ARGS = 32
MAX_REVIEWED_SSH_SCRIPT_ARG_BYTES = 1024
MAX_REVIEWED_SSH_SCRIPT_ARGS_BYTES = 8192


class SSHStructuredExecutionGatewayRequest(SSHExecutionPolicyGatewayRequest):
    """Policy selection for the currently implemented structured SSH paths."""

    execution_mode: Literal["structured"] = "structured"


class SSHReviewedScriptAction(SSHExecutionPolicyGatewayRequest):
    """Hash-pinned script fallback only when structured administration cannot express the intent."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    action: Literal["reviewed_script"]
    execution_mode: Literal["reviewed_script"] = "reviewed_script"
    host_id: str = Field(min_length=1, max_length=128)
    interpreter: Literal["bash", "sh", "python3", "pwsh"]
    arguments: list[str] = Field(
        default_factory=list, max_length=MAX_REVIEWED_SSH_SCRIPT_ARGS
    )
    script: str = Field(min_length=1, max_length=MAX_REVIEWED_SSH_SCRIPT_BYTES)
    script_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    timeout_seconds: int = Field(default=3600, ge=1, le=86_400)
    writes_remote: bool = True
    high_risk: bool = False

    @model_validator(mode="after")
    def validate_reviewed_script(self) -> "SSHReviewedScriptAction":
        if not self.script.strip():
            raise ValueError("Reviewed SSH script must contain non-whitespace content")
        script_bytes = self.script.encode("utf-8")
        if b"\x00" in script_bytes:
            raise ValueError("Reviewed SSH script must not contain NUL bytes")
        if len(script_bytes) > MAX_REVIEWED_SSH_SCRIPT_BYTES:
            raise ValueError(
                "Reviewed SSH script exceeds the maximum UTF-8 byte length"
            )
        if sha256(script_bytes).hexdigest() != self.script_sha256:
            raise ValueError("Reviewed SSH script SHA-256 does not match its content")
        total_argument_bytes = 0
        for argument in self.arguments:
            encoded_argument = argument.encode("utf-8")
            if any(byte < 32 or byte == 127 for byte in encoded_argument):
                raise ValueError(
                    "Reviewed SSH script arguments must not contain control characters"
                )
            if len(encoded_argument) > MAX_REVIEWED_SSH_SCRIPT_ARG_BYTES:
                raise ValueError(
                    "Reviewed SSH script argument exceeds the maximum UTF-8 byte length"
                )
            total_argument_bytes += len(encoded_argument)
        if total_argument_bytes > MAX_REVIEWED_SSH_SCRIPT_ARGS_BYTES:
            raise ValueError(
                "Reviewed SSH script arguments exceed the aggregate UTF-8 byte limit"
            )
        policy = evaluate_ssh_policy(
            SSHPolicyRequest(
                autonomy_profile=self.autonomy_profile,
                execution_mode=self.execution_mode,
            )
        )
        if not policy.allowed:
            raise ValueError(
                "SSH execution policy denied profile/mode combination: "
                f"{self.autonomy_profile}/{self.execution_mode}"
            )
        return self


def canonicalize_hash_pinned_ssh_script(
    interpreter: str,
    script: str,
    script_sha256: str,
) -> tuple[str, str, bool]:
    """Verify the submitted hash and canonicalize POSIX-shell line endings."""

    submitted_bytes = script.encode("utf-8")
    if sha256(submitted_bytes).hexdigest() != script_sha256:
        raise ValueError("SSH script SHA-256 does not match its content")
    if interpreter not in {"bash", "sh"}:
        return script, script_sha256, False
    canonical_script = script.replace("\r\n", "\n").replace("\r", "\n")
    canonical_sha256 = sha256(canonical_script.encode("utf-8")).hexdigest()
    return canonical_script, canonical_sha256, canonical_script != script


def validate_reviewed_ssh_script_request(
    payload: dict[str, Any],
) -> SSHReviewedScriptAction:
    """Run the shared reviewed-script validator without echoing script content."""

    try:
        return SSHReviewedScriptAction.model_validate(payload)
    except ValidationError as exc:
        messages = "; ".join(
            str(error.get("msg", "invalid value"))
            for error in exc.errors(include_input=False)
        )
        raise ValueError(f"Invalid reviewed SSH script request: {messages}") from None


class SSHRootShellAction(SSHExecutionPolicyGatewayRequest):
    """Last-resort unrestricted shell; use structured administration for supported remote mutations."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    action: Literal["root_shell"]
    execution_mode: Literal["root_shell"] = "root_shell"
    autonomy_profile: Literal["permissive"] = "permissive"
    host_id: str = Field(min_length=1, max_length=128)
    script: str = Field(min_length=1, max_length=MAX_REVIEWED_SSH_SCRIPT_BYTES)
    script_sha256: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
    )
    timeout_seconds: int = Field(default=3600, ge=1, le=86_400)
    writes_remote: Literal[True] = True
    high_risk: Literal[True] = True

    @model_validator(mode="after")
    def validate_root_shell(self) -> "SSHRootShellAction":
        if not self.script.strip():
            raise ValueError(
                "SSH root shell script must contain non-whitespace content"
            )
        script_bytes = self.script.encode("utf-8")
        if b"\x00" in script_bytes:
            raise ValueError("SSH root shell script must not contain NUL bytes")
        if len(script_bytes) > MAX_REVIEWED_SSH_SCRIPT_BYTES:
            raise ValueError(
                "SSH root shell script exceeds the maximum UTF-8 byte length"
            )
        if sha256(script_bytes).hexdigest() != self.script_sha256:
            raise ValueError("SSH root shell script SHA-256 does not match its content")
        policy = evaluate_ssh_policy(
            SSHPolicyRequest(
                autonomy_profile=self.autonomy_profile,
                execution_mode=self.execution_mode,
            )
        )
        if not policy.allowed:
            raise ValueError("SSH root shell policy denied the requested profile")
        return self


def validate_root_ssh_shell_request(payload: dict[str, Any]) -> SSHRootShellAction:
    """Run the shared root-shell validator without echoing script content."""

    try:
        return SSHRootShellAction.model_validate(payload)
    except ValidationError as exc:
        messages = "; ".join(
            str(error.get("msg", "invalid value"))
            for error in exc.errors(include_input=False)
        )
        raise ValueError(f"Invalid SSH root shell request: {messages}") from None


class SSHCredentialProbeQuery(GatewayModel):
    operation: Literal["credential_probe"]
    source_path: str = Field(default="", max_length=2048)
    source_type: Literal[
        "auto",
        "env_file",
        "process_environment",
        "openssh_config",
        "connection_file",
        "key_file",
    ] = "auto"
    host_hint: str = Field(default="", max_length=128)
    field_overrides: dict[str, str] = Field(default_factory=dict, max_length=5)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_credential_probe(self) -> "SSHCredentialProbeQuery":
        if self.source_type == "process_environment":
            if self.source_path:
                raise ValueError("process_environment does not accept source_path")
        elif not self.source_path:
            raise ValueError("source_path is required for file-based credential probes")
        allowed_fields = {
            "hostname",
            "user",
            "port",
            "identity_file",
            "expected_host_key",
        }
        extras = sorted(set(self.field_overrides) - allowed_fields)
        if extras:
            raise ValueError(f"Unsupported SSH credential field overrides: {extras}")
        return self


class SSHProfilePreviewQuery(GatewayModel):
    operation: Literal["profile_preview"]
    action: str = Field(min_length=1, max_length=128)
    host_id: str = Field(min_length=1, max_length=128)
    host_config: dict[str, Any] = Field(default_factory=dict)
    command_id: str = Field(default="", max_length=128)
    command_profile: dict[str, Any] = Field(default_factory=dict)
    credential_source_id: str = Field(default="", max_length=128)
    credential_source: dict[str, Any] = Field(default_factory=dict)
    project_bindings: dict[str, Any] = Field(default_factory=dict, max_length=100)
    activation_intent: Literal["new_host", "existing_host", "rotation"] = (
        "existing_host"
    )
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_profile_preview(self) -> "SSHProfilePreviewQuery":
        if self.action == "configure_host":
            if not self.host_config:
                raise ValueError("configure_host requires host_config")
            if not self.credential_source_id or not self.credential_source:
                raise ValueError(
                    "configure_host requires credential_source_id and credential_source"
                )
        elif (
            self.credential_source_id or self.credential_source or self.project_bindings
        ):
            raise ValueError(
                "Credential-source and project-binding fields require action=configure_host"
            )
        return self


class SSHProfileStatusQuery(GatewayModel):
    operation: Literal["profile_status"]
    change_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SSHCapabilitySnapshotQuery(GatewayModel):
    operation: Literal["capability_snapshot"]
    host_id: str = Field(min_length=1, max_length=128)
    snapshot_id: str = Field(default="", max_length=128)
    required_capabilities: list[str] = Field(default_factory=list, max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_capability_snapshot(self) -> "SSHCapabilitySnapshotQuery":
        if self.snapshot_id and self.required_capabilities:
            raise ValueError(
                "required_capabilities are valid only when collecting a new snapshot"
            )
        return self


class SSHProjectBindingsQuery(GatewayModel):
    operation: Literal["project_bindings"]
    host_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SSHProjectBindingValidationQuery(GatewayModel):
    operation: Literal["project_binding_validation"]
    binding_id: str = Field(min_length=1, max_length=128)
    host_id: str = Field(default="", max_length=128)
    capability_snapshot_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


SSHQueryRequest = Annotated[
    SSHCapabilitiesQuery
    | SSHCredentialProbeQuery
    | SSHProfilePreviewQuery
    | SSHProfileStatusQuery
    | SSHCapabilitySnapshotQuery
    | SSHProjectBindingsQuery
    | SSHProjectBindingValidationQuery,
    Field(discriminator="operation"),
]


class SSHProfileApplyAction(GatewayModel):
    action: Literal["profile_apply"]
    host_id: str = Field(default="", max_length=128)
    change_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SSHCommandAction(SSHStructuredExecutionGatewayRequest):
    action: Literal["command", "monitored_command"]
    host_id: str = Field(min_length=1, max_length=128)
    command_id: str = Field(min_length=1, max_length=128)


SSHAdministrationOperation = Literal[
    "exec_profile",
    "service_start",
    "service_stop",
    "service_restart",
    "service_reload",
    "service_enable",
    "service_disable",
    "docker_compose_pull",
    "docker_compose_build",
    "docker_compose_up",
    "docker_compose_down",
    "docker_compose_restart",
    "git_fetch",
    "git_pull_ff",
    "create_directory",
    "copy_path",
    "service_binary_promote",
    "move_path",
    "remove_file",
    "remove_directory",
    "package_update",
    "package_upgrade",
    "package_install",
    "package_remove",
    "reboot",
    "shutdown",
    "run_argv",
]


class SSHAdministrationAction(SSHStructuredExecutionGatewayRequest):
    action: Literal["administration"] = Field(
        description=(
            "Canonical structured route for supported remote administration; "
            "prefer this over reviewed_script or root_shell when it can express the intent."
        )
    )
    host_id: str = Field(min_length=1, max_length=128)
    ssh_action: SSHAdministrationOperation = Field(
        description=(
            "Canonical structured SSH operation. Use service_* for systemd state and "
            "service_binary_promote for a hash-pinned binary replacement with rollback."
        )
    )
    target: str = Field(
        default="",
        max_length=512,
        description="Systemd service name for service_* and service_binary_promote.",
    )
    source: str = Field(
        default="",
        max_length=1024,
        description="Source path; for service_binary_promote this is the staged binary.",
    )
    destination: str = Field(
        default="",
        max_length=1024,
        description="Destination path; for service_binary_promote this is the live binary.",
    )
    path: str = Field(
        default="",
        max_length=1024,
        description="Primary path; for service_binary_promote this is the rollback copy.",
    )
    deployment_id: str = Field(default="", max_length=128)
    command_id: str = Field(default="", max_length=128)
    packages: list[str] = Field(default_factory=list, max_length=100)
    executable: str = Field(default="", max_length=256)
    args: list[str] = Field(
        default_factory=list,
        max_length=100,
        description=(
            "Operation arguments; service_binary_promote requires exactly "
            "[expected_new_sha256, expected_current_sha256]."
        ),
    )
    force: bool = False
    confirmation: str = Field(
        default="",
        max_length=128,
        description=(
            "High-risk confirmation token published by ssh_query capabilities when required."
        ),
    )

    @model_validator(mode="after")
    def validate_administration_contract(self) -> "SSHAdministrationAction":
        if self.ssh_action == "service_binary_promote":
            missing = [
                name
                for name, value in (
                    ("target", self.target),
                    ("source", self.source),
                    ("destination", self.destination),
                    ("path", self.path),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "service_binary_promote requires " + ", ".join(missing)
                )
            if len(self.args) != 2:
                raise ValueError(
                    "service_binary_promote requires args=[expected_new_sha256, expected_current_sha256]"
                )
        return self


class SSHTransferAction(SSHStructuredExecutionGatewayRequest):
    action: Literal["transfer"]
    host_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    direction: Literal["upload", "download"]
    local_path: str = Field(min_length=1, max_length=1024)
    remote_path: str = Field(min_length=1, max_length=1024)
    recursive: bool = False
    overwrite: bool = False
    confirmation: str = Field(default="", max_length=128)


class SSHDeploymentAction(SSHStructuredExecutionGatewayRequest):
    action: Literal["deployment"]
    host_id: str = Field(min_length=1, max_length=128)
    deployment_id: str = Field(min_length=1, max_length=128)
    confirmation: str = Field(min_length=1, max_length=128)


SSHActionRequest = Annotated[
    SSHProfileApplyAction
    | SSHCommandAction
    | SSHReviewedScriptAction
    | SSHRootShellAction
    | SSHAdministrationAction
    | SSHTransferAction
    | SSHDeploymentAction,
    Field(discriminator="action"),
]


class SystemCapabilitiesQuery(GatewayModel):
    operation: Literal["capabilities"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SystemSelfCheckQuery(GatewayModel):
    operation: Literal["self_check"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SystemCapabilityIdentityQuery(GatewayModel):
    operation: Literal["capability_identity"]
    expected_server_build_hash: str = Field(default="", max_length=64)
    expected_schema_hash: str = Field(default="", max_length=64)
    expected_connector_schema_hash: str = Field(default="", max_length=64)
    expected_capability_epoch: str = Field(default="", max_length=128)
    expected_operation_inventory_hash: str = Field(default="", max_length=64)
    expected_operation_schema_hashes: dict[str, str] = Field(
        default_factory=dict, max_length=2048
    )
    expected_live_input_schema_hash: str = Field(default="", max_length=64)
    expected_public_schema_hash: str = Field(default="", max_length=64)
    expected_discovery_cache_generation: str = Field(default="", max_length=64)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SystemLocalModelHealthQuery(GatewayModel):
    operation: Literal["local_model_health"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SystemValidateConfigQuery(GatewayModel):
    operation: Literal["validate_config"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SystemReloadStatusQuery(GatewayModel):
    operation: Literal["reload_status"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


SystemQueryRequest = Annotated[
    SystemCapabilitiesQuery
    | SystemSelfCheckQuery
    | SystemCapabilityIdentityQuery
    | SystemLocalModelHealthQuery
    | SystemValidateConfigQuery
    | SystemReloadStatusQuery,
    Field(discriminator="operation"),
]


class SystemReloadAction(GatewayModel):
    action: Literal["reload"]
    modules: list[str] = Field(default_factory=list, max_length=20)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class SystemRollbackAction(GatewayModel):
    action: Literal["rollback"]
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


SystemActionRequest = Annotated[
    SystemReloadAction | SystemRollbackAction, Field(discriminator="action")
]


class KnowledgeReadWikiQuery(GatewayModel):
    operation: Literal["read_wiki"]
    repo_name: str = Field(min_length=1, max_length=128)
    page: str = Field(default="overview.md", min_length=1, max_length=512)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class KnowledgeSearchQuery(GatewayModel):
    operation: Literal["search"]
    repo_name: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=10, ge=1, le=50)
    include_global_memory: bool = False
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class ProjectKnowledgeSearchQuery(GatewayModel):
    operation: Literal["search_knowledge"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=10, ge=1, le=50)
    current_only: bool = True
    cursor: str | None = Field(default=None, max_length=512)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class ProjectKnowledgeGetQuery(GatewayModel):
    operation: Literal["get_knowledge"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    knowledge_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class ProjectKnowledgeHealthQuery(GatewayModel):
    operation: Literal["knowledge_health"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class ResearchSourceQuery(GatewayModel):
    operation: Literal["get_research_source"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    source_id: str = Field(default="", max_length=128)
    source_version_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_source_identity(self) -> "ResearchSourceQuery":
        if bool(self.source_id) == bool(self.source_version_id):
            raise ValueError("exactly one source_id or source_version_id is required")
        return self


class ResearchClaimEvidenceQuery(GatewayModel):
    operation: Literal["get_claim_evidence"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    claim_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class ResearchListQuery(GatewayModel):
    operation: Literal["list_research_questions", "list_research_decisions"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=20, ge=1, le=100)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class ResearchContextQuery(GatewayModel):
    operation: Literal["search_research", "build_context_packet"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=12, ge=1, le=50)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class ResearchHealthQuery(GatewayModel):
    operation: Literal["research_health"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemoryScopeInput(GatewayModel):
    """Exactly-named memory scope. There is no default and no inference path.

    `personal` is accepted by the schema and refused by the resolver, so
    activating personal memory later is a resolver change rather than a public
    contract change.
    """

    kind: Literal["project", "personal"] = "project"
    project_id: str = Field(default="", max_length=128)
    repo_name: str = Field(default="", max_length=128)
    owner_id: str = Field(default="", max_length=128)

    @model_validator(mode="after")
    def validate_scope_identity(self) -> "MemoryScopeInput":
        if self.kind == "project":
            if not self.project_id or not self.repo_name:
                raise ValueError(
                    "project memory scope requires both project_id and repo_name"
                )
        elif not self.owner_id:
            raise ValueError("personal memory scope requires owner_id")
        return self

    def to_request(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class MemoryScopeQuery(GatewayModel):
    """Resolve a repository to the exact scope its memory calls must carry.

    Every memory operation needs an opaque `project_id`, and until now the only
    ways to obtain one were to already know it or to read it out of a decision
    document. A fresh controller could reach the gateway and still be unable to
    address its own project.

    This resolves and *returns* the scope; it deliberately does not become an
    inference path at call time. `MemoryScopeInput` still requires the scope to
    be named exactly on every call, so discovery stays a separate, visible step
    and a memory operation can never silently guess which project it addressed.
    """

    operation: Literal["memory_scope"]
    repo_name: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemorySearchQuery(GatewayModel):
    operation: Literal["memory_search"]
    scope: MemoryScopeInput
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=10, ge=1, le=50)
    include_non_authoritative: bool = False
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemoryGetQuery(GatewayModel):
    operation: Literal["memory_get"]
    scope: MemoryScopeInput
    knowledge_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemoryHealthQuery(GatewayModel):
    operation: Literal["memory_health"]
    scope: MemoryScopeInput
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemoryContextQuery(GatewayModel):
    operation: Literal["memory_context"]
    scope: MemoryScopeInput
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=10, ge=1, le=50)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemoryPacketGetQuery(GatewayModel):
    """Retrieve the exact stored packet that a bounded projection came from."""

    operation: Literal["memory_packet_get"]
    scope: MemoryScopeInput
    packet_id: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


KnowledgeQueryRequest = Annotated[
    KnowledgeReadWikiQuery
    | KnowledgeSearchQuery
    | ProjectKnowledgeSearchQuery
    | ProjectKnowledgeGetQuery
    | ProjectKnowledgeHealthQuery
    | MemoryScopeQuery
    | MemorySearchQuery
    | MemoryGetQuery
    | MemoryHealthQuery
    | MemoryContextQuery
    | MemoryPacketGetQuery
    | ResearchSourceQuery
    | ResearchClaimEvidenceQuery
    | ResearchListQuery
    | ResearchContextQuery
    | ResearchHealthQuery,
    Field(discriminator="operation"),
]


class KnowledgeRefreshWikiAction(GatewayModel):
    action: Literal["refresh_wiki"]
    repo_name: str = Field(min_length=1, max_length=128)
    force: bool = False
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class KnowledgeRememberDecisionAction(GatewayModel):
    action: Literal["remember_decision"]
    repo_name: str = Field(min_length=1, max_length=128)
    decision: str = Field(min_length=1, max_length=20_000)
    accepted_by: str = Field(default="chatgpt", max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class KnowledgeSourceInput(GatewayModel):
    source_id: str = Field(min_length=1, max_length=128)
    uri: str = Field(default="", max_length=2048)
    title: str = Field(default="", max_length=500)
    version: str = Field(default="", max_length=256)
    content_hash: str = Field(default="", max_length=128)


class KnowledgeLocatorInput(GatewayModel):
    source_id: str = Field(min_length=1, max_length=128)
    locator: str = Field(min_length=1, max_length=2000)
    relationship: Literal["supports", "contradicts", "qualifies"] = "supports"


class KnowledgeSaveAction(GatewayModel):
    action: Literal["save_knowledge"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    vault_path: str = Field(min_length=3, max_length=512)
    kind: Literal[
        "fact",
        "decision",
        "document",
        "research",
        "research_note",
        "lesson",
        "question",
    ]
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=4000)
    body: str = Field(min_length=1, max_length=200_000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    language: str = Field(default="", max_length=32)
    review_state: str = Field(default="unreviewed", max_length=64)
    idempotency_key: str = Field(default="", max_length=256)
    sources: list[KnowledgeSourceInput] = Field(default_factory=list, max_length=50)
    locators: list[KnowledgeLocatorInput] = Field(default_factory=list, max_length=100)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class KnowledgeSupersedeAction(KnowledgeSaveAction):
    action: Literal["supersede_knowledge"]
    supersedes_ids: list[str] = Field(min_length=1, max_length=50)


class KnowledgeRebuildAction(GatewayModel):
    action: Literal["rebuild_knowledge"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class ResearchImportSourceAction(GatewayModel):
    action: Literal["import_research_source"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    canonical_uri: str = Field(min_length=1, max_length=4096)
    title: str = Field(min_length=1, max_length=1000)
    source_type: str = Field(default="document", min_length=1, max_length=128)
    retrieved_at: str = Field(min_length=1, max_length=128)
    origin_namespace: Literal[
        "manual_url", "local_file", "research_packet", "captured_artifact"
    ] = "local_file"
    origin_key: str = Field(default="", max_length=4096)
    original_name: str = Field(default="", max_length=1000)
    media_type: str = Field(default="", max_length=256)
    local_path: str = Field(default="", max_length=32_768)
    captured_artifact_path: str = Field(default="", max_length=32_768)
    content_text: str = Field(default="", max_length=1_000_000)
    expected_sha256: str = Field(default="", pattern=r"^[a-fA-F0-9]{64}$|^$")
    index: bool = True
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def validate_source_material(self) -> "ResearchImportSourceAction":
        supplied = sum(
            bool(value)
            for value in (
                self.local_path,
                self.captured_artifact_path,
                self.content_text,
            )
        )
        if supplied != 1:
            raise ValueError(
                "exactly one of local_path, captured_artifact_path, or content_text is required"
            )
        if self.content_text and not self.original_name:
            raise ValueError("content_text requires original_name")
        return self


class ResearchPreservePacketAction(GatewayModel):
    action: Literal["preserve_research_packet"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    packet: dict[str, Any] = Field(min_length=1, max_length=100)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class ResearchRebuildIndexAction(GatewayModel):
    action: Literal["rebuild_research_index"]
    project_id: str = Field(min_length=1, max_length=128)
    repo_name: str = Field(min_length=1, max_length=128)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemoryBindRepositoryAction(GatewayModel):
    """Explicitly onboard one trusted repository into ProjectScope.

    Repository discovery is read-only and may not silently create authority.
    This separate write action resolves the exact trusted repository root,
    returns an existing active binding when one already exists, or creates one
    idempotently using stable identities derived from that root.
    """

    action: Literal["memory_bind_repository"]
    repo_name: str = Field(min_length=1, max_length=128)
    project_id: str = Field(default="", max_length=128)
    project_key: str = Field(default="", max_length=128)
    access_mode: Literal["exclusive", "shared"] = "exclusive"
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemoryArchiveRepositoryAction(GatewayModel):
    """Archive one empty exact ProjectScope repository binding.

    The operation preserves every identity and binding row, increments scope
    generation, and refuses projects with task/run scope history. It is not a
    delete or a general project lifecycle control.
    """

    action: Literal["memory_archive_repository"]
    repo_name: str = Field(min_length=1, max_length=128)
    project_id: str = Field(min_length=1, max_length=128)
    expected_scope_generation: int = Field(ge=1)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemorySaveAction(GatewayModel):
    """Write one canonical record.

    `vault_path` is optional: when omitted it is derived from `kind` and
    `title`, which removes the one thing every caller previously had to invent
    per write. The derivation is deterministic and the resolved path is always
    echoed in the acknowledgement, so a caller never has to guess where its own
    record landed. An explicit path still wins, because the owner's own filing
    of their vault outranks a generated name.
    """

    action: Literal["memory_save"]
    scope: MemoryScopeInput
    vault_path: str = Field(default="", max_length=512)
    kind: Literal[
        "fact", "decision", "document", "lesson", "question", "handoff", "preference"
    ]
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(default="", max_length=4000)
    body: str = Field(min_length=1, max_length=200_000)
    tags: list[str] = Field(default_factory=list, max_length=50)
    review_state: str = Field(default="unreviewed", max_length=64)
    valid_from: str = Field(default="", max_length=64)
    valid_until: str = Field(default="", max_length=64)
    controller: str = Field(default="", max_length=128)
    task_id: str = Field(default="", max_length=128)
    run_id: str = Field(default="", max_length=128)
    idempotency_key: str = Field(default="", max_length=256)
    sources: list[KnowledgeSourceInput] = Field(default_factory=list, max_length=50)
    locators: list[KnowledgeLocatorInput] = Field(default_factory=list, max_length=100)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)

    @model_validator(mode="after")
    def resolve_vault_path(self) -> "MemorySaveAction":
        if self.vault_path.strip():
            return self
        from .knowledge.vault import derive_vault_path

        derived = derive_vault_path(self.kind, self.title)
        if not derived:
            raise ValueError(
                "vault_path could not be derived from this title, so it must be "
                "given explicitly; a generated placeholder would put an "
                "unfindable record in the vault"
            )
        self.vault_path = derived
        return self


class MemorySupersedeAction(MemorySaveAction):
    action: Literal["memory_supersede"]
    supersedes_ids: list[str] = Field(min_length=1, max_length=50)


class MemoryLifecycleAction(GatewayModel):
    """Move one record to a non-authoritative state under compare-and-swap.

    `superseded` is absent by design: it is derived from a successor's link, so
    setting it directly would let a caller assert a lifecycle no record backs.
    """

    action: Literal["memory_mark_disputed", "memory_archive", "memory_reject"]
    scope: MemoryScopeInput
    knowledge_id: str = Field(min_length=1, max_length=128)
    expected_sha256: str = Field(min_length=64, max_length=64)
    reason: str = Field(default="", max_length=4000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemoryAcceptDriftAction(GatewayModel):
    """Adopt a drifted record's current content as canonical, deliberately.

    Separate from `MemoryLifecycleAction` because it is not a lifecycle move and
    its precondition is the opposite one: a lifecycle action names the hash it
    expects to still hold, while this names the *new* hash being adopted. It is
    deliberately not folded into `memory_rebuild_index`, because a rebuild that
    repaired drift on its own would launder an out-of-band edit into canon.
    """

    action: Literal["memory_accept_drift"]
    scope: MemoryScopeInput
    knowledge_id: str = Field(min_length=1, max_length=128)
    #: The hash of the content as it stands, which the caller is adopting.
    accepted_sha256: str = Field(min_length=64, max_length=64)
    reason: str = Field(default="", max_length=4000)
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemoryRebuildIndexAction(GatewayModel):
    """Request a provider rebuild through the durable task authority."""

    action: Literal["memory_rebuild_index"]
    scope: MemoryScopeInput
    controller_request_id: str = Field(min_length=1, max_length=128)
    full: bool = True
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


class MemorySyncProviderAction(GatewayModel):
    """Reconcile the canonical catalog after out-of-band Obsidian edits."""

    action: Literal["memory_sync_provider"]
    scope: MemoryScopeInput
    view: Literal["compact", "full"] = "compact"
    response_budget_bytes: int = Field(default=12 * 1024, ge=1024, le=64 * 1024)


KnowledgeActionRequest = Annotated[
    KnowledgeRefreshWikiAction
    | KnowledgeRememberDecisionAction
    | KnowledgeSaveAction
    | KnowledgeSupersedeAction
    | KnowledgeRebuildAction
    | MemoryBindRepositoryAction
    | MemoryArchiveRepositoryAction
    | MemorySaveAction
    | MemorySupersedeAction
    | MemoryLifecycleAction
    | MemoryAcceptDriftAction
    | MemoryRebuildIndexAction
    | MemorySyncProviderAction
    | ResearchImportSourceAction
    | ResearchPreservePacketAction
    | ResearchRebuildIndexAction,
    Field(discriminator="action"),
]
