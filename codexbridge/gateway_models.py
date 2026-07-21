"""Strict request contracts for the public domain gateway tools.

The models intentionally describe routing and operation-specific inputs only.
They do not duplicate the established manager, repository, SSH, or cloud
validation that executes after a request is accepted.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

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


class SSHEnvironmentProbe(GatewayModel):
    operation: Literal["environment_probe"]
    host_id: str = Field(min_length=1, max_length=128)


class SSHGpuTelemetry(GatewayModel):
    operation: Literal["gpu_telemetry"]
    host_id: str = Field(min_length=1, max_length=128)


class SSHBoundedInspection(GatewayModel):
    operation: Literal["inspection"]
    host_id: str = Field(min_length=1, max_length=128)
    inspection: str = Field(min_length=1, max_length=128)
    path: str = Field(default="", max_length=1024)
    target: str = Field(default="", max_length=512)
    deployment_id: str = Field(default="", max_length=128)
    tail: int = Field(default=200, ge=1, le=20_000)


SSHInspectRequest = Annotated[
    SSHHostHealth | SSHEnvironmentProbe | SSHGpuTelemetry | SSHBoundedInspection,
    Field(discriminator="operation"),
]


class RunStatusQuery(GatewayModel):
    operation: Literal["status"]
    run_id: str = Field(min_length=1, max_length=128)
    cursor: str = Field(default="", max_length=2048)

    @model_validator(mode="after")
    def encode_chunk_reference(self) -> "RunStatusQuery":
        self.run_id = encode_run_reference(self.run_id, self.cursor)
        return self


class RunControlQuery(GatewayModel):
    operation: Literal["control"]
    run_id: str = Field(min_length=1, max_length=128)


class RunOutputQuery(GatewayModel):
    operation: Literal["output"]
    run_id: str = Field(min_length=1, max_length=128)
    stream: Literal["combined", "stdout", "stderr"] = "combined"
    tail_bytes: int = Field(default=20_000, ge=1, le=200_000)


class RunEventsQuery(GatewayModel):
    operation: Literal["events"]
    run_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=50, ge=1, le=500)
    after_id: int | None = Field(default=None, ge=0)


class RunResultQuery(GatewayModel):
    operation: Literal["result"]
    run_id: str = Field(min_length=1, max_length=128)
    cursor: str = Field(default="", max_length=2048)

    @model_validator(mode="after")
    def encode_chunk_reference(self) -> "RunResultQuery":
        self.run_id = encode_run_reference(self.run_id, self.cursor)
        return self


class PowerShellGroupStatusQuery(GatewayModel):
    operation: Literal["group_status"]
    group_id: str = Field(min_length=1, max_length=128)


class PowerShellGroupResultQuery(GatewayModel):
    operation: Literal["group_result"]
    group_id: str = Field(min_length=1, max_length=128)


class RunSummaryQuery(GatewayModel):
    operation: Literal["summary"]
    run_id: str = Field(min_length=1, max_length=128)


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


RunQueryRequest = Annotated[
    RunStatusQuery
    | RunControlQuery
    | RunOutputQuery
    | RunEventsQuery
    | RunResultQuery
    | PowerShellGroupStatusQuery
    | PowerShellGroupResultQuery
    | RunSummaryQuery
    | RunSummaryListQuery
    | RunListQuery
    | RunLocksQuery,
    Field(discriminator="operation"),
]


class WorkflowStatusQuery(GatewayModel):
    operation: Literal["status"]
    workflow_id: str = Field(min_length=1, max_length=128)


class WorkflowEventsQuery(GatewayModel):
    operation: Literal["events"]
    workflow_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=100, ge=1, le=500)


class WorkflowResultQuery(GatewayModel):
    operation: Literal["result"]
    workflow_id: str = Field(min_length=1, max_length=128)


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


WorkflowActionRequest = Annotated[
    WorkflowStartAction | WorkflowCancelAction, Field(discriminator="action")
]


class TradingHealthQuery(GatewayModel):
    operation: Literal["health"]


class TradingSymbolsQuery(GatewayModel):
    operation: Literal["symbols"]
    query: str = Field(default="", max_length=128)


class TradingSpecificationQuery(GatewayModel):
    operation: Literal["specification"]


class TradingTickQuery(GatewayModel):
    operation: Literal["tick"]


class TradingH4Query(GatewayModel):
    operation: Literal["h4_candles"]
    completed_count: int = Field(default=200, ge=1, le=2_000)


class TradingHistoricalTicksQuery(GatewayModel):
    operation: Literal["historical_ticks"]
    start_utc: datetime
    end_utc: datetime

    @model_validator(mode="after")
    def validate_range(self) -> "TradingHistoricalTicksQuery":
        if self.start_utc.tzinfo is None or self.end_utc.tzinfo is None:
            raise ValueError("Trading historical tick timestamps must be timezone-aware")
        if self.end_utc <= self.start_utc:
            raise ValueError("Trading historical tick end_utc must be after start_utc")
        return self


TradingQueryRequest = Annotated[
    TradingHealthQuery | TradingSymbolsQuery | TradingSpecificationQuery
    | TradingTickQuery | TradingH4Query | TradingHistoricalTicksQuery,
    Field(discriminator="operation"),
]


class TradingSignalSubmitRequest(GatewayModel):
    idempotency_key: str = Field(min_length=1, max_length=128)
    created_at_utc: datetime
    broker: Literal["alpari"]
    symbol: str = Field(min_length=1, max_length=64)
    analysis_timeframe: Literal["4H"]
    decision: Literal["LONG", "SHORT", "NO_TRADE"]
    confidence: int | None = Field(default=None, ge=50, le=99)
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    market_data_timestamp: datetime
    latest_completed_4h_candle: str = Field(min_length=1, max_length=256)
    developing_4h_candle: str = Field(min_length=1, max_length=256)
    entry_type: Literal["MARKET"]
    entry_reference_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reason: str = Field(min_length=1, max_length=4000)
    news_context: str = Field(default="", max_length=8000)
    market_snapshot_id: str = Field(min_length=1, max_length=64)
    market_packet_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")

    @model_validator(mode="after")
    def validate_timestamps(self) -> "TradingSignalSubmitRequest":
        if self.created_at_utc.tzinfo is None or self.market_data_timestamp.tzinfo is None:
            raise ValueError("Trading signal timestamps must be timezone-aware")
        return self


class TradingSignalGetRequest(GatewayModel):
    signal_id: str = Field(min_length=1, max_length=64)


class TradingSignalListRequest(GatewayModel):
    limit: int = Field(default=100, ge=1, le=1000)


class TradingSignalCancelRequest(GatewayModel):
    signal_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)


class SupervisorStatusQuery(GatewayModel):
    operation: Literal["status"]
    supervisor_id: str = Field(min_length=1, max_length=128)


class SupervisorResultQuery(GatewayModel):
    operation: Literal["result"]
    supervisor_id: str = Field(min_length=1, max_length=128)


class SupervisorResumePromptQuery(GatewayModel):
    operation: Literal["resume_prompt"]
    supervisor_id: str = Field(min_length=1, max_length=128)


class SupervisorEventsQuery(GatewayModel):
    operation: Literal["events"]
    supervisor_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=50, ge=1, le=500)


class SupervisorNotificationsQuery(GatewayModel):
    operation: Literal["notifications"]
    supervisor_id: str = Field(min_length=1, max_length=128)
    delivery_status: str = Field(default="", max_length=64)
    limit: int = Field(default=50, ge=1, le=500)


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


class SupervisorPauseAction(GatewayModel):
    action: Literal["pause"]
    supervisor_id: str = Field(min_length=1, max_length=128)


class SupervisorCancelAction(GatewayModel):
    action: Literal["cancel"]
    supervisor_id: str = Field(min_length=1, max_length=128)


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


class RepoCompactStatusQuery(GatewayModel):
    operation: Literal["compact_status"]
    repo_name: str = Field(min_length=1, max_length=128)


class RepoPatchStatusQuery(GatewayModel):
    operation: Literal["patch_status"]
    repo_name: str = Field(min_length=1, max_length=128)
    patch_id: str = Field(min_length=1, max_length=128)


class RepoListFilesQuery(GatewayModel):
    operation: Literal["list_files"]
    repo_name: str = Field(min_length=1, max_length=128)
    directory: str = Field(default="", max_length=1024)
    max_results: int = Field(default=500, ge=1, le=5_000)


class RepoReadFilesQuery(GatewayModel):
    operation: Literal["read_files"]
    repo_name: str = Field(min_length=1, max_length=128)
    requests: list[dict[str, Any]] = Field(min_length=1, max_length=20)


class RepoSearchTextQuery(GatewayModel):
    operation: Literal["search_text"]
    repo_name: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=10_000)
    directory: str = Field(default="", max_length=1024)
    max_results: int = Field(default=50, ge=1, le=500)
    case_sensitive: bool = False
    file_patterns: list[str] = Field(default_factory=list, max_length=20)
    budget_ms: int = Field(default=5_000, ge=100, le=30_000)


class RepoRecentFilesQuery(GatewayModel):
    operation: Literal["recent_files"]
    repo_name: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=50, ge=1, le=500)


class RepoDiffQuery(GatewayModel):
    operation: Literal["diff"]
    repo_name: str = Field(min_length=1, max_length=128)
    path: str = Field(default="", max_length=1024)
    staged: bool = False


class RepoLogQuery(GatewayModel):
    operation: Literal["log"]
    repo_name: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=20, ge=1, le=500)
    path: str = Field(default="", max_length=1024)


class RepoCommitRangeQuery(GatewayModel):
    operation: Literal["commit_range"]
    repo_name: str = Field(min_length=1, max_length=128)
    base_commit: str = Field(min_length=40, max_length=64)
    head_commit: str = Field(min_length=40, max_length=64)


RepoQueryRequest = Annotated[
    RepoStatusQuery | RepoCompactStatusQuery | RepoPatchStatusQuery | RepoListFilesQuery | RepoReadFilesQuery
    | RepoSearchTextQuery | RepoRecentFilesQuery | RepoDiffQuery | RepoLogQuery
    | RepoCommitRangeQuery,
    Field(discriminator="operation"),
]


class RepoPatchPreview(GatewayModel):
    operation: Literal["patch"]
    repo_name: str = Field(min_length=1, max_length=128)
    operations: list[dict[str, Any]] = Field(min_length=1, max_length=100)


class RepoCreateFilePreview(GatewayModel):
    operation: Literal["create_file"]
    repo_name: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=1024)
    content: str = Field(min_length=1, max_length=2_000_000)


class RepoRemoveFilePreview(GatewayModel):
    operation: Literal["remove_file"]
    repo_name: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=1024)
    expected_sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")


class RepoCleanupPreview(GatewayModel):
    operation: Literal["cleanup"]
    repo_name: str = Field(min_length=1, max_length=128)
    roots: list[str] = Field(default_factory=list, max_length=50)


RepoPreviewRequest = Annotated[
    RepoPatchPreview | RepoCreateFilePreview | RepoRemoveFilePreview | RepoCleanupPreview,
    Field(discriminator="operation"),
]


class RepoPreviewedChangeApply(GatewayModel):
    operation: Literal["previewed_change"]
    repo_name: str = Field(min_length=1, max_length=128)
    patch_id: str = Field(min_length=1, max_length=128)


class RepoCleanupApply(GatewayModel):
    operation: Literal["cleanup"]
    repo_name: str = Field(min_length=1, max_length=128)
    cleanup_id: str = Field(min_length=1, max_length=128)


class RepoRevertApply(GatewayModel):
    operation: Literal["revert"]
    repo_name: str = Field(min_length=1, max_length=128)
    patch_id: str = Field(min_length=1, max_length=128)


class RepoMoveFileApply(GatewayModel):
    operation: Literal["move_file"]
    repo_name: str = Field(min_length=1, max_length=128)
    source_path: str = Field(min_length=1, max_length=1024)
    destination_path: str = Field(min_length=1, max_length=1024)
    expected_sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")


RepoApplyRequest = Annotated[
    RepoPreviewedChangeApply | RepoCleanupApply | RepoRevertApply | RepoMoveFileApply,
    Field(discriminator="operation"),
]


class RepoCreateBranchCommit(GatewayModel):
    operation: Literal["create_branch"]
    repo_name: str = Field(min_length=1, max_length=128)
    branch_name: str = Field(min_length=1, max_length=255)


class RepoCommitSelected(GatewayModel):
    operation: Literal["commit_selected"]
    repo_name: str = Field(min_length=1, max_length=128)
    files: list[str] = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=10_000)


RepoCommitRequest = Annotated[
    RepoCreateBranchCommit | RepoCommitSelected, Field(discriminator="operation")
]


class PytestPathStart(GatewayModel):
    operation: Literal["pytest_path"]
    repo_name: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=1024)


class PyCompilePathStart(GatewayModel):
    operation: Literal["py_compile_path"]
    repo_name: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=1024)


class BashSyntaxPathStart(GatewayModel):
    operation: Literal["bash_syntax_path"]
    repo_name: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=1024)


class JsonValidationPathStart(GatewayModel):
    operation: Literal["json_validation_path"]
    repo_name: str = Field(min_length=1, max_length=128)
    path: str = Field(min_length=1, max_length=1024)


class GitReadonlyStart(GatewayModel):
    operation: Literal["git_readonly"]
    repo_name: str = Field(min_length=1, max_length=128)
    git_operation: Literal["status", "diff_check", "diff_name_only", "ls_files"]


class ExternalFixtureValidationStart(GatewayModel):
    operation: Literal["external_fixture_validation"]
    repo_name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=8, max_length=2_048, pattern=r"^https://")
    expected_sha256: str = Field(pattern=r"^[A-Fa-f0-9]{64}$")
    validation: Literal["none", "json", "text"] = "none"


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
    failure_policy: Literal["continue_all", "cancel_remaining_on_failure"] = "continue_all"


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

    @model_validator(mode="after")
    def validate_stdin_mode(self) -> "LocalPowerShellStart":
        if self.stdin_text is not None and self.stdin_base64 is not None:
            raise ValueError("Specify either stdin_text or stdin_base64, not both")
        return self


class HermesCompanionStart(GatewayModel):
    operation: Literal["hermes_companion"]
    repo_name: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(min_length=1, max_length=128)
    checkout: str = Field(min_length=1, max_length=32_768)
    hermes_home: str = Field(default="", max_length=32_768)
    companion_operation: Literal["handshake", "tool_search", "tool_describe", "tool_call"]
    payload: dict[str, Any] = Field(default_factory=dict, max_length=100)
    expected_registry_generation: int | None = Field(default=None, ge=0)
    expected_schema_hash: str = Field(default="", max_length=64)
    timeout_seconds: int = Field(default=120, ge=1, le=600)


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
    PytestPathStart | PyCompilePathStart | BashSyntaxPathStart
    | JsonValidationPathStart | GitReadonlyStart | ExternalFixtureValidationStart
    | LocalPowerShellStart | RemotePowerShellStart | ParallelPowerShellStart
    | HermesCompanionStart,
    Field(discriminator="operation"),
]


class DockerCapabilitiesQuery(GatewayModel):
    operation: Literal["capabilities"]
    repo_name: str = Field(default="", max_length=128)


class DockerHealthQuery(GatewayModel):
    operation: Literal["health"]


class DockerInspectQuery(GatewayModel):
    operation: Literal["inspect"]
    repo_name: str = Field(min_length=1, max_length=128)
    inspection: str = Field(min_length=1, max_length=128)
    target: str = Field(default="", max_length=512)
    service: str = Field(default="", max_length=256)
    tail: int = Field(default=200, ge=1, le=20_000)


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
    action: Literal["compose_build", "compose_up", "compose_down", "compose_start", "compose_stop", "compose_restart", "compose_pause", "compose_unpause", "compose_kill", "compose_pull", "compose_down_volumes", "compose_rm"]


class DockerExecAction(DockerActionBase):
    action: Literal["compose_exec", "container_exec"]
    command_id: str = Field(min_length=1, max_length=128)


class DockerImageAction(DockerActionBase):
    action: Literal["image_build", "image_pull", "image_tag", "image_push", "image_remove"]
    target: str = Field(min_length=1, max_length=512)


class DockerContainerAction(DockerActionBase):
    action: Literal["container_start", "container_stop", "container_restart", "container_pause", "container_unpause", "container_kill", "container_remove"]
    target: str = Field(min_length=1, max_length=512)


class DockerNetworkVolumeAction(DockerActionBase):
    action: Literal["network_create", "network_remove", "volume_create", "volume_remove"]
    target: str = Field(min_length=1, max_length=512)


class DockerPruneAction(DockerActionBase):
    action: Literal["builder_prune", "container_prune", "image_prune", "network_prune", "volume_prune", "system_prune", "system_prune_volumes"]


DockerActionRequest = Annotated[
    DockerComposeAction | DockerExecAction | DockerImageAction | DockerContainerAction
    | DockerNetworkVolumeAction | DockerPruneAction,
    Field(discriminator="action"),
]


class CloudflareCapabilitiesQuery(GatewayModel):
    operation: Literal["capabilities"]
    repo_name: str = Field(min_length=1, max_length=128)


class CloudflareHealthQuery(GatewayModel):
    operation: Literal["health"]
    repo_name: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(min_length=1, max_length=128)


class CloudflareInspectQuery(GatewayModel):
    operation: Literal["inspect"]
    repo_name: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(min_length=1, max_length=128)
    inspection: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(default="", max_length=256)
    name: str = Field(default="", max_length=256)
    record_type: str = Field(default="", max_length=32)
    since_minutes: int = Field(default=60, ge=1, le=43_200)
    page: int = Field(default=1, ge=1, le=10_000)
    per_page: int = Field(default=100, ge=1, le=100)


CloudflareQueryRequest = Annotated[
    CloudflareCapabilitiesQuery | CloudflareHealthQuery | CloudflareInspectQuery,
    Field(discriminator="operation"),
]


class CloudflareActionBase(GatewayModel):
    repo_name: str = Field(min_length=1, max_length=128)
    profile_id: str = Field(min_length=1, max_length=128)
    resource_id: str = Field(default="", max_length=256)
    payload: dict[str, Any] = Field(default_factory=dict)
    confirmation: str = Field(default="", max_length=128)


class CloudflareDnsAction(CloudflareActionBase):
    action: Literal["create_dns_record", "update_dns_record", "delete_dns_record", "dns_create", "dns_update", "dns_delete", "dns_batch"]


class CloudflareCacheAction(CloudflareActionBase):
    action: Literal["purge_cache", "cache_purge"]


class CloudflareZoneAction(CloudflareActionBase):
    action: Literal["update_ssl_settings", "zone_setting_update", "dnssec_enable", "dnssec_disable", "ssl_universal_update"]


class CloudflareRulesetAction(CloudflareActionBase):
    action: Literal["ruleset_create", "ruleset_update", "ruleset_delete", "ruleset_rule_add", "ruleset_rule_update", "ruleset_rule_delete"]


class CloudflareEdgeAction(CloudflareActionBase):
    action: Literal["turnstile_create", "turnstile_update", "turnstile_rotate_secret", "turnstile_delete", "update_turnstile_widget", "create_tunnel", "tunnel_create", "tunnel_config_update", "tunnel_delete", "tunnel_route_create", "tunnel_route_delete"]


CloudflareActionRequest = Annotated[
    CloudflareDnsAction | CloudflareCacheAction | CloudflareZoneAction
    | CloudflareRulesetAction | CloudflareEdgeAction,
    Field(discriminator="action"),
]


class SSHCapabilitiesQuery(GatewayModel):
    operation: Literal["capabilities"]


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
    """Hash-pinned request contract for the reviewed-script launch scaffold."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    action: Literal["reviewed_script"]
    execution_mode: Literal["reviewed_script"] = "reviewed_script"
    host_id: str = Field(min_length=1, max_length=128)
    interpreter: Literal["bash", "sh", "python3", "pwsh"]
    arguments: list[str] = Field(default_factory=list, max_length=MAX_REVIEWED_SSH_SCRIPT_ARGS)
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
                raise ValueError("Reviewed SSH script arguments must not contain control characters")
            if len(encoded_argument) > MAX_REVIEWED_SSH_SCRIPT_ARG_BYTES:
                raise ValueError("Reviewed SSH script argument exceeds the maximum UTF-8 byte length")
            total_argument_bytes += len(encoded_argument)
        if total_argument_bytes > MAX_REVIEWED_SSH_SCRIPT_ARGS_BYTES:
            raise ValueError("Reviewed SSH script arguments exceed the aggregate UTF-8 byte limit")
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
        raise ValueError(
            f"Invalid reviewed SSH script request: {messages}"
        ) from None


class SSHRootShellAction(SSHExecutionPolicyGatewayRequest):
    """Hash-pinned unrestricted shell request available only to permissive mode."""

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
            raise ValueError("SSH root shell script must contain non-whitespace content")
        script_bytes = self.script.encode("utf-8")
        if b"\x00" in script_bytes:
            raise ValueError("SSH root shell script must not contain NUL bytes")
        if len(script_bytes) > MAX_REVIEWED_SSH_SCRIPT_BYTES:
            raise ValueError("SSH root shell script exceeds the maximum UTF-8 byte length")
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


class SSHProfilePreviewQuery(GatewayModel):
    operation: Literal["profile_preview"]
    action: str = Field(min_length=1, max_length=128)
    host_id: str = Field(min_length=1, max_length=128)
    host_config: dict[str, Any] = Field(default_factory=dict)
    command_id: str = Field(default="", max_length=128)
    command_profile: dict[str, Any] = Field(default_factory=dict)


class SSHProfileStatusQuery(GatewayModel):
    operation: Literal["profile_status"]
    change_id: str = Field(min_length=1, max_length=128)


SSHQueryRequest = Annotated[
    SSHCapabilitiesQuery | SSHProfilePreviewQuery | SSHProfileStatusQuery,
    Field(discriminator="operation"),
]


class SSHProfileApplyAction(GatewayModel):
    action: Literal["profile_apply"]
    host_id: str = Field(default="", max_length=128)
    change_id: str = Field(min_length=1, max_length=128)


class SSHCommandAction(SSHStructuredExecutionGatewayRequest):
    action: Literal["command", "monitored_command"]
    host_id: str = Field(min_length=1, max_length=128)
    command_id: str = Field(min_length=1, max_length=128)


class SSHAdministrationAction(SSHStructuredExecutionGatewayRequest):
    action: Literal["administration"]
    host_id: str = Field(min_length=1, max_length=128)
    ssh_action: str = Field(min_length=1, max_length=128)
    target: str = Field(default="", max_length=512)
    source: str = Field(default="", max_length=1024)
    destination: str = Field(default="", max_length=1024)
    path: str = Field(default="", max_length=1024)
    deployment_id: str = Field(default="", max_length=128)
    command_id: str = Field(default="", max_length=128)
    packages: list[str] = Field(default_factory=list, max_length=100)
    executable: str = Field(default="", max_length=256)
    args: list[str] = Field(default_factory=list, max_length=100)
    force: bool = False
    confirmation: str = Field(default="", max_length=128)


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
    SSHProfileApplyAction | SSHCommandAction | SSHReviewedScriptAction
    | SSHRootShellAction | SSHAdministrationAction | SSHTransferAction
    | SSHDeploymentAction,
    Field(discriminator="action"),
]


class SystemCapabilitiesQuery(GatewayModel):
    operation: Literal["capabilities"]


class SystemSelfCheckQuery(GatewayModel):
    operation: Literal["self_check"]


class SystemLocalModelHealthQuery(GatewayModel):
    operation: Literal["local_model_health"]


class SystemValidateConfigQuery(GatewayModel):
    operation: Literal["validate_config"]


class SystemReloadStatusQuery(GatewayModel):
    operation: Literal["reload_status"]


SystemQueryRequest = Annotated[
    SystemCapabilitiesQuery | SystemSelfCheckQuery | SystemLocalModelHealthQuery
    | SystemValidateConfigQuery | SystemReloadStatusQuery,
    Field(discriminator="operation"),
]


class SystemReloadAction(GatewayModel):
    action: Literal["reload"]
    modules: list[str] = Field(default_factory=list, max_length=20)


class SystemRollbackAction(GatewayModel):
    action: Literal["rollback"]


SystemActionRequest = Annotated[
    SystemReloadAction | SystemRollbackAction, Field(discriminator="action")
]


class KnowledgeReadWikiQuery(GatewayModel):
    operation: Literal["read_wiki"]
    repo_name: str = Field(min_length=1, max_length=128)
    page: str = Field(default="overview.md", min_length=1, max_length=512)


class KnowledgeSearchQuery(GatewayModel):
    operation: Literal["search"]
    repo_name: str = Field(min_length=1, max_length=128)
    query: str = Field(min_length=1, max_length=10_000)
    limit: int = Field(default=10, ge=1, le=50)
    include_global_memory: bool = False


KnowledgeQueryRequest = Annotated[
    KnowledgeReadWikiQuery | KnowledgeSearchQuery, Field(discriminator="operation")
]


class KnowledgeRefreshWikiAction(GatewayModel):
    action: Literal["refresh_wiki"]
    repo_name: str = Field(min_length=1, max_length=128)
    force: bool = False


class KnowledgeRememberDecisionAction(GatewayModel):
    action: Literal["remember_decision"]
    repo_name: str = Field(min_length=1, max_length=128)
    decision: str = Field(min_length=1, max_length=20_000)
    accepted_by: str = Field(default="chatgpt", max_length=128)


KnowledgeActionRequest = Annotated[
    KnowledgeRefreshWikiAction | KnowledgeRememberDecisionAction,
    Field(discriminator="action"),
]


class CodexPlanRequest(GatewayModel):
    repo_name: str = Field(min_length=1, max_length=128)
    task: str = Field(min_length=1, max_length=20_000)
    constraints: str = Field(default="", max_length=20_000)


class CodexImplementRequest(GatewayModel):
    repo_name: str = Field(min_length=1, max_length=128)
    approved_plan: str = Field(min_length=1, max_length=100_000)
    allowed_files: list[str] = Field(min_length=1, max_length=500)
    tests: list[str] = Field(default_factory=list, max_length=100)
