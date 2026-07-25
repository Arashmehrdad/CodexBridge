from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from soma.public_gateway_inventory import PUBLIC_GATEWAY_NAMES
from soma.public_projection_contract import DEFAULT_PUBLIC_BYTE_BUDGETS


CF1_GATEWAY_OPERATION_INVENTORY_VERSION: Final[str] = (
    "cf1.3.gateway-operations.v10"
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
    "powershell",
    "remote_powershell",
    "powershell_group",
    "hermes_companion",
    "hermes_service",
)


PUBLIC_GATEWAY_OPERATION_INVENTORY: Final[
    tuple[PublicGatewayOperationInventoryEntry, ...]
] = (
    _entry(
        "ssh_inspect",
        ("host_health", "environment_probe", "gpu_telemetry"),
        "soma.server:ssh_inspect",
        "bounded compact SSH health and telemetry projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact SSH health and telemetry retain scalar host fields and collection counts under a UTF-8 budget; view=full remains explicit complete evidence access.",
    ),
    _entry(
        "ssh_inspect",
        ("inspection",),
        "soma.server:ssh_inspect -> soma.ssh_tools:inspection",
        "bounded SSH inspection object",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "Compact inspections retain bounded identifiers and tail counts under a "
            "serialized UTF-8 budget with truncation metadata; view=full preserves "
            "the complete provider result."
        ),
    ),
    _entry(
        "docker_query",
        ("capabilities",),
        "soma.server:docker_query",
        "bounded Docker capability projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact capability lists remain policy-shaped under a serialized UTF-8 budget with truncation metadata; view=full preserves complete capability evidence.",
    ),
    _entry(
        "docker_query",
        ("health",),
        "soma.server:docker_query",
        "bounded Docker health summary",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact Docker health remains a compatibility-shaped provider summary under a serialized UTF-8 budget; view=full preserves the complete provider payload.",
    ),
    _entry(
        "docker_query",
        ("inspect",),
        "soma.server:docker_query -> soma.docker_tools:inspect",
        "bounded command result with stdout and stderr",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        maximum_item_limit=20_000,
        notes=(
            "The tail field remains bounded to 20,000 units; the compact response is "
            "capped by a UTF-8 byte budget with truncation metadata, while view=full "
            "preserves complete inspection evidence."
        ),
    ),
    _entry(
        "docker_action",
        _DOCKER_ACTIONS,
        "soma.server:docker_action",
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
        "soma.server:cloudflare_query",
        "bounded Cloudflare capability projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact capability lists remain authorization-shaped under a serialized UTF-8 budget with truncation metadata; view=full preserves complete capability evidence.",
    ),
    _entry(
        "cloudflare_query",
        ("health",),
        "soma.server:cloudflare_query",
        "bounded Cloudflare health summary",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact Cloudflare health remains a compatibility-shaped provider summary under a serialized UTF-8 budget; view=full preserves the complete provider payload.",
    ),
    _entry(
        "cloudflare_query",
        ("inspect",),
        "soma.server:cloudflare_query -> soma.cloudflare_tools:inspect",
        "bounded Cloudflare provider projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.PAGE_NUMBER,
        default_item_limit=100,
        maximum_item_limit=100,
        notes=(
            "The request exposes page and per_page, with per_page fixed by a default "
            "and maximum of 100; compact responses use a serialized UTF-8 budget with "
            "explicit truncation metadata, while view=full preserves complete evidence "
            "for the selected provider page."
        ),
    ),
    _entry(
        "cloudflare_action",
        _CLOUDFLARE_ACTIONS,
        "soma.server:cloudflare_action",
        "durable run launch acknowledgement",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes=(
            "Action payloads are preserved in durable run input records and "
            "provider results are retrieved through the run path."
        ),
    ),
    _entry(
        "ssh_query",
        ("capabilities",),
        "soma.server:ssh_query",
        "bounded compact SSH capability projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact capabilities return host/command counts under a UTF-8 budget; view=full remains explicit complete capability access.",
    ),
    _entry(
        "ssh_query",
        (
            "credential_probe", "profile_preview", "profile_status",
            "capability_snapshot", "project_bindings",
            "project_binding_validation",
        ),
        "soma.server:ssh_query",
        "bounded compact SSH credential and profile lifecycle projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Credential probes expose source names, deterministic mappings, hygiene status, and public fingerprints without resolved values; profile reads retain lifecycle and hash identity; capability snapshots and project-binding operations use fixed read-only probes with bounded projections and explicit full evidence access.",
    ),
    _entry(
        "ssh_action",
        ("profile_apply",),
        "soma.server:ssh_action -> soma.ssh_tools:profile_apply",
        "bounded compact profile mutation result",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact profile mutation results retain change/status/activation scalars and counts under a UTF-8 budget; view=full remains explicit complete evidence access.",
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
        "soma.server:ssh_action -> soma.job_manager:JobManager",
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
        "soma.server:run_start -> soma.job_manager:JobManager",
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
        "soma.server:workflow_query",
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
        "soma.server:workflow_query",
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
        "soma.server:workflow_query",
        "bounded workflow event list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=100,
        maximum_item_limit=500,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact events remain ordered and limit bounded under a serialized UTF-8 budget with truncation metadata; view=full preserves the complete selected event list.",
    ),
    _entry(
        "workflow_action",
        ("start",),
        "soma.server:workflow_action",
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
        "soma.server:workflow_action",
        "bounded compact workflow cancellation projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact cancellation retains lifecycle and bounded step diagnostics; view=full remains explicit complete workflow evidence.",
    ),
    _entry(
        "cancel_run",
        ("invoke",),
        "soma.server:cancel_run",
        "bounded compact run cancellation acknowledgement",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact cancellation retains run/group identity and diagnostic counts under a UTF-8 budget; view=full remains explicit complete cancellation evidence.",
    ),
    _entry(
        "run_query",
        ("summary",),
        "soma.server:run_query -> soma.job_manager:JobManager.get_run_summary",
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
        "soma.server:run_query -> soma.job_manager:JobManager.list_run_summaries",
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
        "soma.server:run_query -> soma.job_manager:JobManager.list_runs",
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
        "soma.server:run_query -> soma.job_manager:JobManager.get_terminal_result",
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
        ("status",),
        "soma.server:run_query -> soma.job_manager:JobManager.get_lifecycle_status",
        "bounded lifecycle-only run status projection",
        request_echo=RequestEchoBehavior.IDENTIFIERS_AND_FILTERS,
        json_decode_cost=JsonDecodeCost.NONE,
        default_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.run_control,
        maximum_response_bytes=DEFAULT_PUBLIC_BYTE_BUDGETS.run_control,
        notes=(
            "Routine polling contains only lifecycle, process, cancellation, lock, "
            "publication, and bounded terminal-summary fields. Input, output, result, "
            "terminal, and event details are explicit operations."
        ),
    ),
    _entry(
        "run_query",
        ("input",),
        "soma.server:run_query -> soma.job_manager:JobManager.get_input",
        "bounded submitted-input metadata with explicit chunked full retrieval",
        request_echo=RequestEchoBehavior.IDENTIFIERS_AND_FILTERS,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.CHUNK_CURSOR,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "Compact input reports authoritative and redacted hashes, byte counts, "
            "field metadata, and truncation. view=full returns a cursor-paged, "
            "secret-redacted representation while exact input_json remains durable."
        ),
    ),
    _entry(
        "run_query",
        ("result",),
        "soma.server:run_query -> soma.job_manager:JobManager",
        "bounded terminal projection by default; explicit full result view",
        request_echo=RequestEchoBehavior.NONE,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.CHUNK_CURSOR,
        notes=(
            "Result defaults to the bounded source-hash-bound terminal projection; "
            "view=full or a cursor retains the authoritative chunked archive."
        ),
    ),
    _entry(
        "run_query",
        ("control",),
        "soma.server:run_query -> soma.job_manager:JobManager.get_control_status",
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
        "soma.server:run_query -> soma.job_manager:JobManager.get_output",
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
        "soma.server:run_query -> soma.job_manager:JobManager.get_event_page",
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
        "soma.server:run_query -> soma.parallel_runs:PowerShellGroupManager",
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
        "soma.server:run_query -> soma.parallel_runs:PowerShellGroupManager",
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
        "soma.server:run_query -> soma.job_manager:JobManager.list_locks",
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
        "soma.server:run_query -> soma.server:get_repository_preflight",
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
        ("capabilities", "local_model_health", "validate_config", "reload_status"),
        "soma.server:system_query",
        "bounded compact system summary projection",
        request_echo=RequestEchoBehavior.NONE,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact system summaries retain scalar health/configuration fields and counts under a UTF-8 budget; view=full remains explicit complete evidence access.",
    ),
    _entry(
        "system_query",
        ("capability_identity",),
        "soma.server:system_query",
        "bounded capability identity convergence check",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Reports source and running server/schema identities, operation-inventory hash, and caller-supplied connector identity mismatches under a bounded projection.",
    ),
    _entry(
        "system_query",
        ("self_check",),
        "soma.server:system_query -> soma.server:run_local_self_check",
        "bounded compact system self-check projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact self-check diagnostics retain per-check outcome fields under a UTF-8 budget; view=full remains explicit evidence access.",
    ),
    _entry(
        "system_action",
        ("reload",),
        "soma.server:system_action",
        "bounded compact service reload acknowledgement",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact reload acknowledgement bounds diagnostics and exposes lifecycle counts; view=full remains explicit evidence access.",
    ),
    _entry(
        "system_action",
        ("rollback",),
        "soma.server:system_action",
        "bounded compact service rollback acknowledgement",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact rollback acknowledgement bounds diagnostics and exposes lifecycle metadata; view=full remains explicit evidence access.",
    ),
    _entry(
        "supervisor_query",
        ("status",),
        "soma.server:supervisor_query",
        "bounded durable supervisor status projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact status omits nested plan/result payloads and bounds diagnostics; view=full remains explicit evidence access.",
    ),
    _entry(
        "supervisor_query",
        ("result",),
        "soma.server:supervisor_query",
        "bounded durable supervisor result projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact result omits nested plan/result payloads and bounds diagnostics; view=full remains explicit evidence access.",
    ),
    _entry(
        "supervisor_query",
        ("resume_prompt",),
        "soma.server:supervisor_query -> soma.supervisor_service:SupervisorService.get_resume_prompt",
        "bounded supervisor resume-prompt projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact prompt content is UTF-8 bounded with truncation and byte accounting; view=full remains explicit evidence access.",
    ),
    _entry(
        "supervisor_query",
        ("events",),
        "soma.server:supervisor_query",
        "bounded supervisor event list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=50,
        maximum_item_limit=500,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact events remain ordered and limit bounded under a serialized UTF-8 budget with truncation metadata; view=full preserves the complete selected event list.",
    ),
    _entry(
        "supervisor_query",
        ("notifications",),
        "soma.server:supervisor_query",
        "bounded compact supervisor notification list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=50,
        maximum_item_limit=500,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact notifications remain item limited and delivery-status filtered under a UTF-8 budget; view=full remains explicit complete notification evidence access.",
    ),
    _entry(
        "supervisor_action",
        ("start",),
        "soma.server:supervisor_action",
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
        "soma.server:supervisor_action",
        "bounded compact supervisor lifecycle projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact lifecycle mutations retain identity/status/publication metadata and bounded diagnostics; view=full remains explicit complete supervisor evidence.",
    ),
    _entry(
        "trading_query",
        ("health", "specification", "tick"),
        "soma.server:trading_query",
        "bounded compact scalar market-data projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact scalar market-data responses retain provider-safe scalar fields under a UTF-8 budget; view=full remains explicit complete adapter evidence.",
    ),
    _entry(
        "trading_query",
        ("symbols",),
        "soma.server:trading_query",
        "bounded symbol discovery list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        notes="Compact symbol discovery is capped by a serialized UTF-8 byte budget with truncation metadata; view=full preserves the complete provider symbol list.",
    ),
    _entry(
        "trading_query",
        ("h1_candles", "h4_candles"),
        "soma.server:trading_query",
        "bounded completed-candle series",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=200,
        maximum_item_limit=2_000,
        notes="Candle count remains request bounded; compact responses use a UTF-8 byte budget with truncation metadata, while view=full preserves the complete selected series.",
    ),
    _entry(
        "trading_query",
        ("historical_ticks",),
        "soma.server:trading_query",
        "bounded historical tick series",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "The time range remains validated; the compact tick series is capped by a "
            "UTF-8 byte budget with truncation metadata, while view=full preserves the "
            "complete selected provider series."
        ),
    ),
    _entry(
        "trading_query",
        ("open_virtual_positions", "portfolio_status", "threshold_report"),
        "soma.server:trading_query",
        "static deprecation notice",
        json_decode_cost=JsonDecodeCost.NONE,
        notes=(
            "Removed runtime virtual-portfolio reads: threshold and occupancy"
            " analysis moved to deterministic offline replay; the response is"
            " a fixed deprecation object pointing at replay_report,"
            " calibration_report, outcome_list, and action_list."
        ),
    ),
    _entry(
        "trading_query",
        ("market_packet_get", "outcome_get", "action_get", "runtime_status", "companion_get"),
        "soma.server:trading_query",
        "bounded durable trading record",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "Journal-backed single-record reads over the immutable packet,"
            " outcome, action, and runtime state stores; no provider"
            " connection is made and view=full preserves complete evidence"
            " including the stored packet payload."
        ),
    ),
    _entry(
        "trading_query",
        (
            "market_packet_list",
            "outcome_list",
            "rejection_list",
            "action_list",
            "reconciliation_report",
            "demo_performance",
            "companion_list",
        ),
        "soma.server:trading_query",
        "bounded paginated durable trading list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=100,
        maximum_item_limit=500,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "Offset-paginated reads over the complete durable journals with"
            " explicit totals instead of silent truncation; demo performance"
            " and reconciliation views redact credentials and expose broker"
            " reconciliation evidence."
        ),
    ),
    _entry(
        "trading_query",
        ("data_quality",),
        "soma.server:trading_query",
        "bounded tick retention quality report",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "Retained-tick coverage for an explicit window: tick count,"
            " deterministic range hash, and detected gaps against the"
            " configured gap threshold."
        ),
    ),
    _entry(
        "trading_query",
        ("calibration_report", "replay_report"),
        "soma.server:trading_query",
        "deterministic offline analysis report",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "The two Trading Lab reports: confidence calibration and"
            " threshold/occupancy replay, both deterministic over the"
            " immutable journals with canonical content hashes, explicit"
            " experiment selection, and resolution-basis period semantics;"
            " view=full preserves the complete report."
        ),
    ),
    _entry(
        "trading_signal_submit",
        ("invoke",),
        "soma.server:trading_signal_submit",
        "bounded trading journal submission result",
        request_echo=RequestEchoBehavior.FULL_AUTHORITATIVE_ROW,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Packet-bound v2 submission: market facts derive from the referenced stored packet, rejections persist as durable records, and view=full remains explicit complete record access.",
    ),
    _entry(
        "trading_signal_get",
        ("invoke",),
        "soma.server:trading_signal_get",
        "bounded trading journal record",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact signal retrieval bounds narrative fields and response bytes; view=full remains explicit complete record access.",
    ),
    _entry(
        "trading_signal_list",
        ("invoke",),
        "soma.server:trading_signal_list",
        "bounded trading journal list",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=100,
        maximum_item_limit=500,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Offset pagination with explicit totals over the complete journal replaces silent truncation; compact responses use a serialized UTF-8 budget with truncation metadata, while view=full preserves complete selected records.",
    ),
    _entry(
        "trading_signal_cancel_before_entry",
        ("invoke",),
        "soma.server:trading_signal_cancel_before_entry",
        "bounded updated trading journal record",
        request_echo=RequestEchoBehavior.FULL_AUTHORITATIVE_ROW,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact cancellation results bound narrative fields and response bytes; view=full remains explicit complete record access.",
    ),
    _entry(
        "trading_companion_action",
        ("start", "decide", "review", "execute"),
        "soma.server:trading_companion_action",
        "bounded durable companion-cycle transition",
        request_echo=RequestEchoBehavior.FULL_AUTHORITATIVE_ROW,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "The scheduled ChatGPT cycle binds research to an immutable market"
            " packet, stores one packet-bound decision, requires a model-owned"
            " second review before directional execution, and derives symbol,"
            " direction, policy, mode, experiment, and bracket from the approved"
            " signal. Compact responses are UTF-8 bounded; view=full preserves"
            " complete companion, signal, packet, and action evidence."
        ),
    ),
    _entry(
        "trading_action_submit",
        ("invoke",),
        "soma.server:trading_action_submit",
        "bounded durable action record",
        request_echo=RequestEchoBehavior.FULL_AUTHORITATIVE_ROW,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "One guarded model trading action through the full pipeline"
            " (schema, mode policy, strategy policy, fresh price,"
            " normalization, risk, margin, order_check, idempotent"
            " submission, durable REQUESTED..RECONCILED persistence, broker"
            " reconciliation); demo-only and raw order_send is unreachable."
        ),
    ),
    _entry(
        "trading_runtime_control",
        (
            "start",
            "stop",
            "status",
            "kill_switch_on",
            "kill_switch_off",
            "supervise_now",
            "analyze_now",
        ),
        "soma.server:trading_runtime_control",
        "bounded runtime state or pass report",
        request_echo=RequestEchoBehavior.IDENTIFIERS_AND_FILTERS,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "Durable runtime start/stop/status, the global kill switch, and"
            " manual supervision/analysis passes; supervision keeps running"
            " for existing positions when analysis fails and stop/kill"
            " actions require an explicit reason."
        ),
    ),
    _entry(
        "repo_query",
        ("status",),
        "soma.server:repo_query",
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
        "soma.server:repo_query",
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
        "soma.server:repo_query -> soma.repo_writer:get_patch_status",
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
        "soma.server:repo_query -> soma.repo_tools:list_repo_files",
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
        "soma.server:repo_query -> soma.repo_tools:read_repo_files",
        "bounded batch file-content projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=48 * 1024,
        maximum_response_bytes=128 * 1024,
        maximum_item_limit=20,
        notes=(
            "The request remains capped at 20 files; aggregate content is enforced "
            "under the caller budget with explicit payload/response byte accounting "
            "and continuation metadata."
        ),
    ),
    _entry(
        "repo_query",
        ("search_text",),
        "soma.server:repo_query -> soma.repo_tools:search_repo_text",
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
        "soma.server:repo_query -> soma.repo_tools:get_recent_files",
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
        "soma.server:repo_query -> soma.repo_tools:git_log",
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
        ("diff",),
        "soma.server:repo_query -> soma.repo_tools",
        "bounded immutable diff snapshot",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=16 * 1024,
        maximum_response_bytes=64 * 1024,
        notes="Diff statistics, hunk indexes, selected hunks, and explicit full retrieval share an immutable snapshot identity and UTF-8 budget.",
    ),
    _entry(
        "repo_query",
        ("commit_range",),
        "soma.server:repo_query -> soma.server:inspect_commit_range",
        "bounded compact commit-range projection",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "Compact commit-range responses retain commit identities, file counts, "
            "diff statistics, and diff byte size; view=full preserves complete range evidence."
        ),
    ),
    _entry(
        "repo_preview",
        ("patch", "remove_file", "cleanup"),
        "soma.server:repo_preview",
        "bounded compact opaque managed preview",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact previews retain patch/cleanup identity, statistics, and diagnostic counts under a UTF-8 budget; view=full preserves complete diff evidence.",
    ),
    _entry(
        "repo_preview",
        ("create_file",),
        "soma.server:repo_preview",
        "bounded compact opaque managed preview",
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes=(
            "Request content is capped at 2,000,000 characters; compact response "
            "metadata is UTF-8 bounded and view=full preserves complete diff evidence."
        ),
    ),
    _entry(
        "repo_apply",
        ("previewed_change", "cleanup", "revert", "move_file"),
        "soma.server:repo_apply -> soma.job_manager:JobManager.start_repo_apply",
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
        "soma.server:repo_commit",
        "bounded protected git mutation result",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact commit results retain operation, status, identity, and changed-file projection under a UTF-8 budget; view=full remains explicit complete mutation metadata access.",
    ),
    _entry(
        "knowledge_query",
        ("read_wiki",),
        "soma.knowledge_tools_integration:knowledge_query",
        "bounded repository wiki page content",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Compact wiki pages are capped by serialized UTF-8 budget with truncation metadata; view=full remains explicit complete-page access.",
    ),
    _entry(
        "knowledge_query",
        ("search",),
        "soma.knowledge_tools_integration:knowledge_query",
        "bounded wiki and memory search result",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        pagination=PaginationBehavior.LIMIT_ONLY,
        default_item_limit=10,
        maximum_item_limit=50,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        notes="Search results remain item limited; compact responses expose a caller-selected serialized UTF-8 budget with truncation metadata, while view=full preserves complete selected wiki and memory hits.",
    ),
    _entry(
        "knowledge_action",
        ("refresh_wiki",),
        "soma.knowledge_tools_integration:knowledge_action",
        "bounded compact wiki refresh acknowledgement",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes="Compact refresh acknowledgement returns lifecycle metadata and page/file counts under a UTF-8 budget; view=full remains explicit evidence access.",
    ),
    _entry(
        "knowledge_action",
        ("remember_decision",),
        "soma.knowledge_tools_integration:knowledge_action",
        "bounded compact decision acknowledgement",
        json_decode_cost=JsonDecodeCost.BOUNDED_OBJECT,
        default_response_bytes=12 * 1024,
        maximum_response_bytes=12 * 1024,
        request_echo=RequestEchoBehavior.DURABLE_INPUT_RECORD,
        notes="Compact decision acknowledgement bounds title/summary diagnostics; view=full remains explicit evidence access.",
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
