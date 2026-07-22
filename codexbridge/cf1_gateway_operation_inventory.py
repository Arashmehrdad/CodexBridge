from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from codexbridge.public_gateway_inventory import PUBLIC_GATEWAY_NAMES
from codexbridge.public_projection_contract import DEFAULT_PUBLIC_BYTE_BUDGETS


CF1_GATEWAY_OPERATION_INVENTORY_VERSION: Final[str] = (
    "cf1.3.gateway-operations.v5"
)


class RequestEchoBehavior(str, Enum):
    NONE = "none"
    IDENTIFIERS_AND_FILTERS = "identifiers_and_filters"
    DURABLE_INPUT_RECORD = "durable_input_record"
    FULL_AUTHORITATIVE_ROW = "full_authoritative_row"


class JsonDecodeCost(str, Enum):
    NONE = "none"
    BOUNDED_OBJECT = "bounded_object"
    FULL_JSON_BLOBS = "full_json_blobs"


class PaginationBehavior(str, Enum):
    NONE = "none"
    LIMIT_ONLY = "limit_only"
    PAGE_NUMBER = "page_number"
    CURSOR = "cursor"
    CHUNK_CURSOR = "chunk_cursor"


class ConnectorRepresentation(str, Enum):
    INLINE_WITH_RESOURCE_FALLBACK = (
        "structured_content_plus_text_content_with_chunked_resource_fallback"
    )


@dataclass(frozen=True)
class PublicGatewayOperationInventoryEntry:
    gateway: str
    operation_names: tuple[str, ...]
    implementation_path: str
    response_path: str
    default_response_bytes: int | None
    maximum_response_bytes: int | None
    default_item_limit: int | None
    maximum_item_limit: int | None
    request_echo: RequestEchoBehavior
    json_decode_cost: JsonDecodeCost
    pagination: PaginationBehavior
    connector_representation: ConnectorRepresentation
    notes: str

    def __post_init__(self) -> None:
        if not self.gateway:
            raise ValueError("gateway must not be empty")
        if not self.operation_names:
            raise ValueError("operation_names must not be empty")
        if any(not name for name in self.operation_names):
            raise ValueError("operation_names must not contain empty values")
        if len(set(self.operation_names)) != len(self.operation_names):
            raise ValueError("operation_names must be unique within an entry")
        if not self.implementation_path:
            raise ValueError("implementation_path must not be empty")
        if not self.response_path:
            raise ValueError("response_path must not be empty")
        if not self.notes:
            raise ValueError("notes must not be empty")
        for field_name in (
            "default_response_bytes",
            "maximum_response_bytes",
            "default_item_limit",
            "maximum_item_limit",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
            ):
                raise ValueError(f"{field_name} must be a positive integer or None")
        if (
            self.default_response_bytes is not None
            and self.maximum_response_bytes is not None
            and self.default_response_bytes > self.maximum_response_bytes
        ):
            raise ValueError(
                "default_response_bytes must not exceed maximum_response_bytes"
            )
        if (
            self.default_item_limit is not None
            and self.maximum_item_limit is not None
            and self.default_item_limit > self.maximum_item_limit
        ):
            raise ValueError(
                "default_item_limit must not exceed maximum_item_limit"
            )


def _entry(
    gateway: str,
    operation_names: tuple[str, ...],
    implementation_path: str,
    response_path: str,
    *,
    request_echo: RequestEchoBehavior = RequestEchoBehavior.IDENTIFIERS_AND_FILTERS,
    json_decode_cost: JsonDecodeCost = JsonDecodeCost.NONE,
    pagination: PaginationBehavior = PaginationBehavior.NONE,
    default_response_bytes: int | None = None,
    maximum_response_bytes: int | None = None,
    default_item_limit: int | None = None,
    maximum_item_limit: int | None = None,
    notes: str,
) -> PublicGatewayOperationInventoryEntry:
    return PublicGatewayOperationInventoryEntry(
        gateway=gateway,
        operation_names=operation_names,
        implementation_path=implementation_path,
        response_path=response_path,
        default_response_bytes=default_response_bytes,
        maximum_response_bytes=maximum_response_bytes,
        default_item_limit=default_item_limit,
        maximum_item_limit=maximum_item_limit,
        request_echo=request_echo,
        json_decode_cost=json_decode_cost,
        pagination=pagination,
        connector_representation=(
            ConnectorRepresentation.INLINE_WITH_RESOURCE_FALLBACK
        ),
        notes=notes,
    )


_DOCKER_ACTIONS: Final[tuple[str, ...]] = (
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
    "compose_exec",
    "container_exec",
    "image_build",
    "image_pull",
    "image_tag",
    "image_push",
    "image_remove",
    "container_start",
    "container_stop",
    "container_restart",
    "container_pause",
    "container_unpause",
    "container_kill",
    "container_remove",
    "network_create",
    "network_remove",
    "volume_create",
    "volume_remove",
    "builder_prune",
    "container_prune",
    "image_prune",
    "network_prune",
    "volume_prune",
    "system_prune",
    "system_prune_volumes",
)

_CLOUDFLARE_ACTIONS: Final[tuple[str, ...]] = (
    "create_dns_record",
    "update_dns_record",
    "delete_dns_record",
    "dns_create",
    "dns_update",
    "dns_delete",
    "dns_batch",
    "purge_cache",
    "cache_purge",
    "update_ssl_settings",
    "zone_setting_update",
    "dnssec_enable",
    "dnssec_disable",
    "ssl_universal_update",
    "ruleset_create",
    "ruleset_update",
    "ruleset_delete",
    "ruleset_rule_add",
    "ruleset_rule_update",
    "ruleset_rule_delete",
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
)

_RUN_START_OPERATIONS: Final[tuple[str, ...]] = (
    "pytest_path",
    "py_compile_path",
    "bash_syntax_path",
    "json_validation_path",
    "git_readonly",
    "external_fixture_validation",
    "powershell",
    "remote_powershell",
    "powershell_group",
    "hermes_companion",
)


PUBLIC_GATEWAY_OPERATION_INVENTORY: Final[
    tuple[PublicGatewayOperationInventoryEntry, ...]
] = (
    _entry(
        "ssh_inspect",
        ("host_health", "environment_probe", "gpu_telemetry"),
        "codexbridge.server:ssh_inspect",
        "direct SSH health and telemetry object",
        notes="Structured SSH health and telemetry responses remain compatibility-shaped.",
    ),
    _entry(
        "ssh_inspect",
        ("inspection",),
        "codexbridge.server:ssh_inspect -> codexbridge.ssh_tools:inspection",
        "bounded SSH inspection object",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "Inspection schemas retain bounded identifiers and tail counts, and the "
            "serialized response now has a UTF-8 budget with truncation metadata."
        ),
    ),
    _entry(
        "codex_plan",
        ("invoke",),
        "codexbridge.server:codex_plan",
        "durable run launch acknowledgement",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "The immediate acknowledgement is small; task and constraints are "
            "preserved in the durable run input record."
        ),
    ),
    _entry(
        "codex_implement",
        ("invoke",),
        "codexbridge.server:codex_implement",
        "durable run launch acknowledgement",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "The immediate acknowledgement is small; approved plan, file scope, "
            "and tests are preserved in the durable run input record."
        ),
    ),
    _entry(
        "docker_query",
        ("capabilities",),
        "codexbridge.server:docker_query",
        "bounded Docker capability projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Capability lists remain policy-shaped and are capped by a serialized UTF-8 budget with truncation metadata.",
    ),
    _entry(
        "docker_query",
        ("health",),
        "codexbridge.server:docker_query",
        "bounded Docker health summary",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Docker health remains a compatibility-shaped provider summary under a serialized UTF-8 budget.",
    ),
    _entry(
        "docker_query",
        ("inspect",),
        "codexbridge.server:docker_query -> codexbridge.docker_tools:inspect",
        "bounded command result with stdout and stderr",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        maximum_item_limit=20_000,
        notes=(
            "The tail field remains bounded to 20,000 units and the serialized "
            "response is capped by a UTF-8 byte budget with truncation metadata."
        ),
    ),
    _entry(
        "docker_action",
        _DOCKER_ACTIONS,
        "codexbridge.server:docker_action",
        "durable run launch acknowledgement",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "Action arguments are stored in the durable run input record; the "
            "terminal provider result is retrieved separately."
        ),
    ),
    _entry(
        "cloudflare_query",
        ("capabilities",),
        "codexbridge.server:cloudflare_query",
        "bounded Cloudflare capability projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Capability lists remain authorization-shaped and are capped by a serialized UTF-8 budget with truncation metadata.",
    ),
    _entry(
        "cloudflare_query",
        ("health",),
        "codexbridge.server:cloudflare_query",
        "bounded Cloudflare health summary",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Cloudflare health remains a compatibility-shaped provider summary under a serialized UTF-8 budget.",
    ),
    _entry(
        "cloudflare_query",
        ("inspect",),
        "codexbridge.server:cloudflare_query -> codexbridge.cloudflare_tools:inspect",
        "bounded Cloudflare provider projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.PAGE_NUMBER,
        default_item_limit=100,
        maximum_item_limit=100,
        notes=(
            "The request exposes page and per_page, with per_page fixed by a "
            "default and maximum of 100; the response is capped by a serialized "
            "UTF-8 budget with explicit truncation metadata."
        ),
    ),
    _entry(
        "cloudflare_action",
        _CLOUDFLARE_ACTIONS,
        "codexbridge.server:cloudflare_action",
        "durable run launch acknowledgement",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "Action payloads are preserved in durable run input records and "
            "provider results are retrieved through the run path."
        ),
    ),
    _entry(
        "ssh_query",
        ("capabilities", "profile_preview", "profile_status"),
        "codexbridge.server:ssh_query",
        "direct SSH capability or profile lifecycle object",
        notes=(
            "Profile previews can include configuration diffs; no public response "
            "byte ceiling is enforced."
        ),
    ),
    _entry(
        "ssh_action",
        ("profile_apply",),
        "codexbridge.server:ssh_action -> codexbridge.ssh_tools:profile_apply",
        "direct profile mutation result",
        notes="The response returns profile lifecycle metadata without pagination.",
    ),
    _entry(
        "ssh_action",
        (
            "command",
            "monitored_command",
            "reviewed_script",
            "root_shell",
            "administration",
            "transfer",
            "deployment",
        ),
        "codexbridge.server:ssh_action -> codexbridge.job_manager:JobManager",
        "durable run launch acknowledgement",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "Reviewed or root scripts, argv, and action arguments are durable "
            "inputs; protected evidence and terminal results remain separate."
        ),
    ),
    _entry(
        "run_start",
        _RUN_START_OPERATIONS,
        "codexbridge.server:run_start -> codexbridge.job_manager:JobManager",
        "durable run launch acknowledgement",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "Every operation records its validated request in input_json before "
            "the worker is launched."
        ),
    ),
    _entry(
        "workflow_query",
        ("status",),
        "codexbridge.server:workflow_query",
        "bounded durable workflow status projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        notes="Compact status bounds step diagnostics and omits objective, process, and artifact payloads; view=full remains explicit evidence access.",
    ),
    _entry(
        "workflow_query",
        ("result",),
        "codexbridge.server:workflow_query",
        "bounded durable workflow result projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        notes="Compact result bounds step diagnostics and omits objective, process, and artifact payloads; view=full remains explicit evidence access.",
    ),
    _entry(
        "workflow_query",
        ("events",),
        "codexbridge.server:workflow_query",
        "bounded workflow event list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=100,
        maximum_item_limit=500,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Events remain ordered and limit bounded, with a serialized UTF-8 budget and truncation metadata.",
    ),
    _entry(
        "workflow_action",
        ("start",),
        "codexbridge.server:workflow_action",
        "durable workflow creation result",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "Objective and up to 100 step definitions are preserved in workflow "
            "state and may be repeated in public snapshots."
        ),
    ),
    _entry(
        "workflow_action",
        ("cancel",),
        "codexbridge.server:workflow_action",
        "direct workflow cancellation result",
        notes="Cancellation returns the updated workflow lifecycle snapshot.",
    ),
    _entry(
        "cancel_run",
        ("invoke",),
        "codexbridge.server:cancel_run",
        "direct run cancellation result",
        notes="The result can include bounded process-tree diagnostics.",
    ),
    _entry(
        "run_query",
        ("summary",),
        "codexbridge.server:run_query -> codexbridge.job_manager:JobManager.get_run_summary",
        "bounded non-authoritative scalar run summary",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.run_summary,
        maximum_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.run_summary,
        notes=(
            "The explicit summary view omits authoritative JSON blobs, worker lease "
            "data, run_dir, and exact process identity; free-text fields are redacted "
            "and UTF-8 truncated to the 6 KiB serialized response ceiling."
        ),
    ),
    _entry(
        "run_query",
        ("summary_list",),
        "codexbridge.server:run_query -> codexbridge.job_manager:JobManager.list_run_summaries",
        "stable bounded page of non-authoritative scalar run summaries",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.CURSOR,
        default_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.run_list,
        maximum_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.run_list,
        default_item_limit=10,
        maximum_item_limit=100,
        notes=(
            "The explicit compact list uses keyset pagination and a row-ID snapshot "
            "watermark, may shorten a page to fit the 12 KiB serialized response "
            "ceiling, and preserves legacy list behavior unchanged."
        ),
    ),
    _entry(
        "run_query",
        ("list",),
        "codexbridge.server:run_query -> codexbridge.job_manager:JobManager.list_runs",
        "full run rows or chunked JSON resource",
        request_echo=RequestEchoBehavior.FULL_AUTHORITATIVE_ROW,
        json_decode_cost=JsonDecodeCost.FULL_JSON_BLOBS,
        pagination=PaginationBehavior.CHUNK_CURSOR,
        default_item_limit=20,
        maximum_item_limit=500,
        notes=(
            "Current list queries select full rows, including input_json, "
            "progress_json, result_json, worker lease data, and run_dir."
        ),
    ),
    _entry(
        "run_query",
        ("terminal",),
        "codexbridge.server:run_query -> codexbridge.job_manager:JobManager.get_terminal_result",
        "bounded source-hash-bound non-authoritative terminal projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result,
        maximum_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.terminal_result,
        notes=(
            "Current projections are served from bounded public_result_json without "
            "decoding authoritative result_json. Legacy or stale rows are rebuilt "
            "once through source-hash- and schema-bound compare-and-set materialization; "
            "the explicit result operation preserves the full chunked archive."
        ),
    ),
    _entry(
        "run_query",
        ("status", "result"),
        "codexbridge.server:run_query -> codexbridge.job_manager:JobManager",
        "bounded terminal projection by default; explicit full result view",
        request_echo=RequestEchoBehavior.NONE,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.CHUNK_CURSOR,
        notes=(
            "Status remains scalar control metadata. Result defaults to the bounded "
            "source-hash-bound terminal projection; view=full or a legacy cursor "
            "retains the authoritative chunked archive."
        ),
    ),
    _entry(
        "run_query",
        ("control",),
        "codexbridge.server:run_query -> codexbridge.job_manager:JobManager.get_control_status",
        "bounded scalar process and lock control object",
        request_echo=RequestEchoBehavior.IDENTIFIERS_AND_FILTERS,
        json_decode_cost=JsonDecodeCost.NONE,
        default_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.run_control,
        maximum_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.run_control,
        notes=(
            "The control path uses explicit scalar SQL with an 8 KiB serialized "
            "response ceiling. Matching if_state_version polls return a deterministic "
            "unchanged envelope below the 1 KiB unchanged-poll ceiling without "
            "process probes or lock lookup."
        ),
    ),
    _entry(
        "run_query",
        ("output",),
        "codexbridge.server:run_query -> codexbridge.job_manager:JobManager.get_output",
        "selected stdout and stderr tails",
        notes=(
            "tail_bytes defaults to 20,000 and is capped at 200,000 for the "
            "requested tail; envelope overhead and a combined two-stream response "
            "mean these are not complete response byte ceilings."
        ),
    ),
    _entry(
        "run_query",
        ("events",),
        "codexbridge.server:run_query -> codexbridge.job_manager:JobManager.get_event_page",
        "bounded forward-pollable run event page",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.CURSOR,
        default_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.events,
        maximum_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.events,
        default_item_limit=20,
        maximum_item_limit=500,
        notes=(
            "Legacy after_id remains supported. Opaque run-bound cursors expire after "
            "five minutes and return explicit malformed, checksum, run-mismatch, "
            "gap, ahead-of-latest, and expiry errors. Pages expose next_after_id, "
            "next_cursor, and has_more under a 12 KiB serialized ceiling."
        ),
    ),
    _entry(
        "run_query",
        ("group_status",),
        "codexbridge.server:run_query -> codexbridge.parallel_runs:PowerShellGroupManager",
        "bounded parallel-group status projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        notes="Compact status omits request and artifact payloads, bounds child summaries, and retains view=full for explicit evidence.",
    ),
    _entry(
        "run_query",
        ("group_result",),
        "codexbridge.server:run_query -> codexbridge.parallel_runs:PowerShellGroupManager",
        "bounded parallel-group result projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        notes="Compact result omits request and artifact payloads, bounds child summaries, and retains view=full for explicit evidence.",
    ),
    _entry(
        "run_query",
        ("locks",),
        "codexbridge.server:run_query -> codexbridge.job_manager:JobManager.list_locks",
        "bounded compact repository lock projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        default_item_limit=50,
        maximum_item_limit=500,
        notes=(
            "The default lock view is capped by item count and serialized UTF-8 "
            "budget; view=full remains an explicit compatibility/evidence path."
        ),
    ),
    _entry(
        "run_query",
        ("preflight",),
        "codexbridge.server:run_query -> codexbridge.server:get_repository_preflight",
        "single bounded repository/work preflight projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "Combines compact live worktree identity and cleanliness, active run states, "
            "repository locks, and capability epoch; individual operations remain the "
            "explicit detail and evidence paths."
        ),
    ),
    _entry(
        "system_query",
        (
            "capabilities",
            "self_check",
            "local_model_health",
            "validate_config",
            "reload_status",
        ),
        "codexbridge.server:system_query",
        "direct system summary object",
        request_echo=RequestEchoBehavior.NONE,
        notes="System query responses are direct and unpaginated.",
    ),
    _entry(
        "system_action",
        ("reload", "rollback"),
        "codexbridge.server:system_action",
        "direct service lifecycle result",
        notes=(
            "Reload diagnostics and capability metadata are returned inline with "
            "no public response byte ceiling."
        ),
    ),
    _entry(
        "supervisor_query",
        ("status", "result"),
        "codexbridge.server:supervisor_query",
        "direct durable supervisor snapshot",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        notes="Status and result preserve the existing durable supervisor compatibility shape.",
    ),
    _entry(
        "supervisor_query",
        ("resume_prompt",),
        "codexbridge.server:supervisor_query -> codexbridge.supervisor_service:SupervisorService.get_resume_prompt",
        "bounded supervisor resume-prompt projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact prompt content is UTF-8 bounded with truncation and byte accounting; view=full remains explicit evidence access.",
    ),
    _entry(
        "supervisor_query",
        ("events",),
        "codexbridge.server:supervisor_query",
        "bounded supervisor event list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=50,
        maximum_item_limit=500,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Events remain ordered and limit bounded, with a serialized UTF-8 budget and truncation metadata.",
    ),
    _entry(
        "supervisor_query",
        ("notifications",),
        "codexbridge.server:supervisor_query",
        "direct supervisor notification list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=50,
        maximum_item_limit=500,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Notifications remain item limited and delivery-status filtered, with a serialized UTF-8 budget and truncation metadata.",
    ),
    _entry(
        "supervisor_action",
        ("start",),
        "codexbridge.server:supervisor_action",
        "durable supervisor creation result",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "Objective, task, constraints, and source run identity are preserved "
            "in supervisor state."
        ),
    ),
    _entry(
        "supervisor_action",
        ("resume", "pause", "cancel"),
        "codexbridge.server:supervisor_action",
        "direct supervisor lifecycle result",
        notes="Lifecycle mutations return the updated supervisor state.",
    ),
    _entry(
        "trading_query",
        ("health", "specification", "tick"),
        "codexbridge.server:trading_query",
        "direct market-data adapter object",
        notes="Scalar market-data responses preserve direct adapter compatibility.",
    ),
    _entry(
        "trading_query",
        ("symbols",),
        "codexbridge.server:trading_query",
        "bounded symbol discovery list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        notes="Symbol discovery is capped by a serialized UTF-8 byte budget with truncation metadata.",
    ),
    _entry(
        "trading_query",
        ("h4_candles",),
        "codexbridge.server:trading_query",
        "bounded completed-candle series",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=200,
        maximum_item_limit=2_000,
        notes="Candle count remains bounded and the serialized response has a UTF-8 byte budget with truncation metadata.",
    ),
    _entry(
        "trading_query",
        ("historical_ticks",),
        "codexbridge.server:trading_query",
        "bounded historical tick series",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "The time range remains validated and the serialized tick series is "
            "capped by a UTF-8 byte budget with truncation metadata."
        ),
    ),
    _entry(
        "trading_signal_submit",
        ("invoke",),
        "codexbridge.server:trading_signal_submit",
        "direct trading journal record",
        request_echo=RequestEchoBehavior.FULL_AUTHORITATIVE_ROW,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        notes="The submitted signal fields are returned through the journal record.",
    ),
    _entry(
        "trading_signal_get",
        ("invoke",),
        "codexbridge.server:trading_signal_get",
        "direct trading journal record",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        notes="A complete signal record is returned without pagination.",
    ),
    _entry(
        "trading_signal_list",
        ("invoke",),
        "codexbridge.server:trading_signal_list",
        "bounded trading journal list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=100,
        maximum_item_limit=1_000,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="The list remains item limited and immutable, with a serialized UTF-8 budget and truncation metadata.",
    ),
    _entry(
        "trading_signal_cancel_before_entry",
        ("invoke",),
        "codexbridge.server:trading_signal_cancel_before_entry",
        "direct updated trading journal record",
        request_echo=RequestEchoBehavior.FULL_AUTHORITATIVE_ROW,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        notes="Cancellation returns the updated signal record.",
    ),
    _entry(
        "repo_query",
        ("status",),
        "codexbridge.server:repo_query",
        "bounded compact repository status projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "The default compact view is capped by serialized UTF-8 budget and keeps "
            "changed-file and status metadata; view=full preserves compatibility "
            "for complete repository-status evidence."
        ),
    ),
    _entry(
        "repo_query",
        ("compact_status",),
        "codexbridge.server:repo_query",
        "bounded compact repository status projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "The compact status fields remain compatibility-shaped but are capped by "
            "serialized UTF-8 budget with explicit truncation and byte accounting."
        ),
    ),
    _entry(
        "repo_query",
        ("patch_status",),
        "codexbridge.server:repo_query -> codexbridge.repo_writer:get_patch_status",
        "bounded compact managed-patch status projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "The default compact view exposes lifecycle identifiers, changed-file and "
            "error counts under a serialized UTF-8 budget; view=full preserves the "
            "complete patch manifest evidence path."
        ),
    ),
    _entry(
        "repo_query",
        ("list_files",),
        "codexbridge.server:repo_query -> codexbridge.repo_tools:list_repo_files",
        "bounded compact repository path list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=500,
        maximum_item_limit=5_000,
        notes=(
            "The default compact view is capped by serialized UTF-8 budget and keeps "
            "explicit count/truncation metadata; view=full preserves compatibility "
            "for complete path evidence."
        ),
    ),
    _entry(
        "repo_query",
        ("read_files",),
        "codexbridge.server:repo_query -> codexbridge.repo_tools:read_repo_files",
        "direct batch file-content result",
        maximum_item_limit=20,
        notes=(
            "The request is capped at 20 files; aggregate returned content has no "
            "public byte ceiling."
        ),
    ),
    _entry(
        "repo_query",
        ("search_text",),
        "codexbridge.server:repo_query -> codexbridge.repo_tools:search_repo_text",
        "bounded content-bound repository search result",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=16 * 1024,
        maximum_response_bytes=16 * 1024,
        pagination=PaginationBehavior.CURSOR,
        default_item_limit=50,
        maximum_item_limit=500,
        notes=(
            "Search preserves exact-file scope, snapshot/hash-bound continuation, and "
            "timeout/partial-result reporting under a fixed 16-KB serialized UTF-8 "
            "budget; the full evidence path remains explicit."
        ),
    ),
    _entry(
        "repo_query",
        ("recent_files",),
        "codexbridge.server:repo_query -> codexbridge.repo_tools:get_recent_files",
        "bounded compact recent-file list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=50,
        maximum_item_limit=500,
        notes=(
            "The default compact view is capped by serialized UTF-8 budget and keeps "
            "explicit count/truncation metadata; view=full preserves compatibility "
            "for complete recent-file evidence."
        ),
    ),
    _entry(
        "repo_query",
        ("log",),
        "codexbridge.server:repo_query -> codexbridge.repo_tools:git_log",
        "bounded compact commit list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=20,
        maximum_item_limit=500,
        notes=(
            "The default compact view is capped by serialized UTF-8 budget and keeps "
            "explicit count/truncation metadata; view=full preserves compatibility "
            "for complete commit-log evidence."
        ),
    ),
    _entry(
        "repo_query",
        ("diff", "commit_range"),
        "codexbridge.server:repo_query -> codexbridge.repo_tools",
        "direct diff content and metadata",
        notes=(
            "Diff helpers may mark content truncated, but the public contract does "
            "not expose a shared byte budget."
        ),
    ),
    _entry(
        "repo_preview",
        ("patch", "remove_file", "cleanup"),
        "codexbridge.server:repo_preview",
        "opaque managed preview with diff metadata",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes="Preview records preserve proposed changes outside tracked files.",
    ),
    _entry(
        "repo_preview",
        ("create_file",),
        "codexbridge.server:repo_preview",
        "opaque managed preview with diff metadata",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "Request content is capped at 2,000,000 characters; the preview "
            "response itself has no byte ceiling."
        ),
    ),
    _entry(
        "repo_apply",
        ("previewed_change", "cleanup", "revert", "move_file"),
        "codexbridge.server:repo_apply -> codexbridge.job_manager:JobManager.start_repo_apply",
        "durable compact managed-apply acknowledgement",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        json_decode_cost=JsonDecodeCost.NONE,
        default_response_bytes=4 * 1024,
        maximum_response_bytes=4 * 1024,
        notes=(
            "The gateway records the validated request and repository lock before "
            "returning a transaction/run identifier. Compact control polling and "
            "terminal/evidence retrieval preserve the existing full apply result."
        ),
    ),
    _entry(
        "repo_commit",
        ("create_branch", "commit_selected"),
        "codexbridge.server:repo_commit",
        "direct protected git mutation result",
        notes=(
            "Selected-file commits accept up to 200 file paths; response bytes are "
            "not explicitly capped."
        ),
    ),
    _entry(
        "knowledge_query",
        ("read_wiki",),
        "codexbridge.knowledge_tools_integration:knowledge_query",
        "direct repository wiki content",
        notes="Wiki content has no public response byte ceiling.",
    ),
    _entry(
        "knowledge_query",
        ("search",),
        "codexbridge.knowledge_tools_integration:knowledge_query",
        "direct wiki and memory search result",
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=10,
        maximum_item_limit=50,
        notes="Search results are item limited without a cursor.",
    ),
    _entry(
        "knowledge_action",
        ("refresh_wiki", "remember_decision"),
        "codexbridge.knowledge_tools_integration:knowledge_action",
        "direct knowledge mutation result",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "Repository wiki changes and decisions are persisted before the "
            "summary result is returned."
        ),
    ),
)


def operation_inventory_by_gateway() -> dict[
    str, tuple[PublicGatewayOperationInventoryEntry, ...]
]:
    grouped: dict[str, list[PublicGatewayOperationInventoryEntry]] = {}
    for entry in PUBLIC_GATEWAY_OPERATION_INVENTORY:
        grouped.setdefault(entry.gateway, []).append(entry)
    return {gateway: tuple(entries) for gateway, entries in grouped.items()}


def operation_names_by_gateway() -> dict[str, frozenset[str]]:
    return {
        gateway: frozenset(
            operation_name
            for entry in entries
            for operation_name in entry.operation_names
        )
        for gateway, entries in operation_inventory_by_gateway().items()
    }


def validate_gateway_operation_inventory() -> None:
    grouped = operation_inventory_by_gateway()
    if set(grouped) != set(PUBLIC_GATEWAY_NAMES):
        missing = sorted(set(PUBLIC_GATEWAY_NAMES) - set(grouped))
        extra = sorted(set(grouped) - set(PUBLIC_GATEWAY_NAMES))
        raise ValueError(
            f"gateway operation inventory mismatch: missing={missing}, extra={extra}"
        )
    for gateway, entries in grouped.items():
        operation_names = [
            operation_name
            for entry in entries
            for operation_name in entry.operation_names
        ]
        if len(operation_names) != len(set(operation_names)):
            raise ValueError(
                f"gateway {gateway!r} repeats an operation inventory name"
            )


validate_gateway_operation_inventory()
