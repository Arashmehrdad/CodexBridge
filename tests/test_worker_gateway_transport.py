"""V3-2 isolated worker MCP transport source proofs."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from fastmcp.client.transports import StreamableHttpTransport

from soma.project_scope import ProjectScopeStore
from soma.public_gateway_inventory import PUBLIC_GATEWAY_NAMES
from soma.run_store import RunStore
from soma.tasks.models import (
    BackendKind,
    TaskKind,
    TaskPhase,
    normalize_durable_command_request,
    normalized_request_hash,
)
from soma.tasks.store import TaskStore
from soma.worker_authority import (
    WorkerAuthorityService,
    WorkerAuthorizationDenied,
    WorkerCapabilityGrantIssueV1,
    WorkerOperationRegistry,
    WorkerOperationSpecV1,
    WorkerPrincipalIssueV1,
)
from soma.worker_gateway import (
    WORKER_PARAMETER_MAX_BYTES,
    WorkerBearerTokenVerifier,
    WorkerDispatchContext,
    WorkerOperationDispatchRegistry,
    build_worker_mcp,
    make_worker_bearer,
)
from soma.worker_substrate import SessionBindingDisposition, WorkerSubstrateStore


PROJECT_ID = "Project_Worker_Gateway"
RESOURCE_ID = "Resource_Worker_Gateway"
TASK_ID = "task_20260814T170000Z_cccccccccccc"
RUN_ID = "20260814T170000Z_worker_cccccccc"
OWNER = "owner-controller:worker-gateway"
ROLE = "role-context:gateway-worker"
MANDATE_REF = "mandate:worker-gateway-fixture"
MANDATE_HASH = "c" * 64
NOW = datetime.now(timezone.utc).replace(microsecond=0)


class _SecretObject:
    def __init__(self, value: str) -> None:
        self.value = value

    def __str__(self) -> str:
        return self.value


ECHO_SPEC = WorkerOperationSpecV1(
    operation_ref="worker-operation:echo",
    operation_kind="query",
    requires_session=True,
    allowed_task_states=("running",),
    description="Echo bounded fixture input.",
)
HIDDEN_SPEC = WorkerOperationSpecV1(
    operation_ref="worker-operation:hidden",
    operation_kind="query",
    requires_session=True,
    allowed_task_states=("running",),
    description="Granted but not executable in this transport fixture.",
)
FAIL_SPEC = WorkerOperationSpecV1(
    operation_ref="worker-operation:fail",
    operation_kind="action",
    requires_session=True,
    allowed_task_states=("running",),
    description="Raise one fixture handler failure.",
)
PROTECTED_SPEC = WorkerOperationSpecV1(
    operation_ref="worker-operation:protected",
    operation_kind="protected_mutation",
    requires_session=True,
    allowed_task_states=("running",),
    description="Protected fixture operation that must not dispatch here.",
)


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _prepare(tmp_path: Path):
    runs = tmp_path / "runs"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    authority_store = None
    registry = WorkerOperationRegistry((ECHO_SPEC, HIDDEN_SPEC, FAIL_SPEC, PROTECTED_SPEC))
    service = WorkerAuthorityService(runs, registry=registry)
    authority_store = service.store
    assert authority_store.init_db() == [1]

    scope = ProjectScopeStore(runs)
    scope.apply_bootstrap(
        project_id=PROJECT_ID,
        project_key="worker-gateway",
        resource_id=RESOURCE_ID,
        repo_name="sample",
        repository_root=repo,
        access_mode="exclusive",
    )

    RunStore(runs).create_run(
        run_id=RUN_ID,
        repo_name="sample",
        tool="fixture",
        run_dir=runs / RUN_ID,
        input_data={"fixture": True},
        status="running",
    )
    task_store = TaskStore(runs)
    normalized = normalize_durable_command_request(
        repo_name="sample",
        profile_id="fixture",
        argv=["fixture"],
    )
    task_store.reserve_task(
        task_id=TASK_ID,
        task_kind=TaskKind.DURABLE_COMMAND.value,
        controller_request_id="worker-gateway-task",
        request_hash=normalized_request_hash(normalized),
        backend_kind=BackendKind.SOMA_DURABLE_RUN.value,
        backend_executor="fixture",
        backend_ref=RUN_ID,
        backend_identity={"run_id": RUN_ID},
    )
    running = task_store.conditional_update(
        TASK_ID,
        fields={
            "state": "running",
            "phase": TaskPhase.BACKEND_RUNNING.value,
            "started_at": NOW.isoformat(),
        },
        expected_state_version=0,
        expected_states=("accepted",),
    )
    assert running is not None
    assert running.state_version == 1

    with scope.connect() as conn:
        conn.execute(
            "INSERT INTO project_task_reservations("
            "task_id, project_id, scope_generation, status, created_at, updated_at) "
            "VALUES (?, ?, 1, 'attached', ?, ?)",
            (TASK_ID, PROJECT_ID, NOW.isoformat(), NOW.isoformat()),
        )
        conn.execute(
            "INSERT INTO project_run_attempts("
            "run_id, project_id, task_id, resource_id, scope_generation, status, "
            "recovery_reason, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 1, 'attached', '', ?, ?)",
            (RUN_ID, PROJECT_ID, TASK_ID, RESOURCE_ID, NOW.isoformat(), NOW.isoformat()),
        )

    substrate = WorkerSubstrateStore(runs)
    binding, created = substrate.bind_provider_session(
        project_id=PROJECT_ID,
        resource_id=RESOURCE_ID,
        task_id=TASK_ID,
        run_id=RUN_ID,
        provider="fixture_provider",
        native_session_id="Provider-Native-Gateway-Session-001",
        adapter_id="soma.adapter.fixture",
        adapter_version="1",
        protocol_id="fixture.protocol",
        protocol_version="1",
    )
    assert created is True
    assert binding.disposition is SessionBindingDisposition.BOUND

    dispatch = WorkerOperationDispatchRegistry(registry)
    calls: list[Any] = []
    leaked: dict[str, str] = {"credential": ""}

    async def echo_handler(context):
        calls.append(context)
        return {
            "echo": dict(context.parameters),
            "credential": leaked["credential"],
            "verifier_hash": "should-never-cross-transport",
            "token": leaked["credential"],
            "client_secret": leaked["credential"],
            "nested": {"private-key": leaked["credential"]},
            "opaque": _SecretObject(leaked["credential"]),
        }

    async def fail_handler(context):
        calls.append(context)
        raise RuntimeError(f"fixture failure containing {leaked['credential']}")

    dispatch.register(ECHO_SPEC.operation_ref, echo_handler)
    dispatch.register(FAIL_SPEC.operation_ref, fail_handler)
    clock = [NOW]
    app = build_worker_mcp(service, dispatch, clock=lambda: clock[0])

    return {
        "runs": runs,
        "service": service,
        "scope": scope,
        "task_store": task_store,
        "substrate": substrate,
        "binding": binding,
        "registry": registry,
        "dispatch": dispatch,
        "calls": calls,
        "leaked": leaked,
        "clock": clock,
        "app": app,
    }


def _issue_principal(fixture, suffix: str):
    result = fixture["service"].issue_principal(
        WorkerPrincipalIssueV1(
            controller_request_id=f"worker-gateway-principal-{suffix}",
            project_id=PROJECT_ID,
            resource_id=RESOURCE_ID,
            scope_generation=1,
            task_id=TASK_ID,
            run_id=RUN_ID,
            session_binding_id=fixture["binding"].session_binding_id,
            role_ref=ROLE,
            mandate_ref=MANDATE_REF,
            mandate_hash=MANDATE_HASH,
            mandate_version="v1",
            issuer_ref=OWNER,
            expires_at=NOW + timedelta(hours=2),
        ),
        now=NOW,
    )
    assert result.created is True
    assert result.credential_once is not None
    return result


def _issue_grant(
    fixture,
    principal_id: str,
    *,
    suffix: str,
    spec: WorkerOperationSpecV1 = ECHO_SPEC,
    parameters: dict[str, Any] | None = None,
    expires_at: datetime | None = None,
):
    params = parameters or {"value": suffix}
    grant, created = fixture["service"].issue_grant(
        WorkerCapabilityGrantIssueV1(
            controller_request_id=f"worker-gateway-grant-{suffix}",
            principal_id=principal_id,
            intent_ref=f"intent:worker-gateway:{suffix}",
            intent_hash=_digest(f"intent:{suffix}"),
            operation_ref=spec.operation_ref,
            operation_hash=spec.operation_hash,
            parameter_contract=params,
            issuer_ref=OWNER,
            expires_at=expires_at or (NOW + timedelta(hours=1)),
        ),
        now=NOW,
    )
    assert created is True
    return grant


def _bearer(issue) -> str:
    assert issue.credential_once is not None
    return make_worker_bearer(issue.principal.principal_id, issue.credential_once)


@asynccontextmanager
async def _http_client(app, bearer: str):
    asgi = app.http_app(path="/mcp", stateless_http=True)

    def factory(headers=None, timeout=None, auth=None, **kwargs):
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=asgi),
            base_url="http://worker.test",
            headers=headers,
            timeout=timeout,
            auth=auth,
            follow_redirects=kwargs.get("follow_redirects", False),
        )

    transport = StreamableHttpTransport(
        "http://worker.test/mcp",
        auth=BearerAuth(bearer),
        httpx_client_factory=factory,
    )
    async with asgi.router.lifespan_context(asgi):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=asgi),
            base_url="http://worker.test",
        ) as probe:
            response = await probe.post(
                "/mcp",
                headers={
                    "Authorization": f"Bearer {bearer}",
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": "auth-probe",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "soma-auth-probe", "version": "1"},
                    },
                },
            )
            if response.status_code == 401:
                response.raise_for_status()
        async with Client(transport, mode="legacy") as client:
            yield client


def _http_status_codes(exc: BaseException) -> set[int]:
    codes: set[int] = set()
    pending = [exc]
    visited: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        response = getattr(current, "response", None)
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            codes.add(status_code)
        pending.extend(
            nested
            for nested in getattr(current, "exceptions", ())
            if isinstance(nested, BaseException)
        )
        for nested in (current.__cause__, current.__context__):
            if isinstance(nested, BaseException):
                pending.append(nested)
    return codes


@pytest.mark.anyio
async def test_worker_app_construction_is_inert_and_isolated(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    registry = WorkerOperationRegistry((ECHO_SPEC,))
    service = WorkerAuthorityService(runs, registry=registry)
    dispatch = WorkerOperationDispatchRegistry(registry)
    dispatch.register(ECHO_SPEC.operation_ref, lambda _context: {"ok": True})
    assert service.store.is_installed() is False
    assert (runs / "soma.sqlite3").exists() is False

    app = build_worker_mcp(service, dispatch, clock=lambda: NOW)
    tools = await app.list_tools()
    tool_names = {tool.name for tool in tools}
    assert tool_names == {"worker_capabilities", "worker_invoke"}
    assert tool_names.isdisjoint(PUBLIC_GATEWAY_NAMES)
    assert len(PUBLIC_GATEWAY_NAMES) == 40
    assert service.store.is_installed() is False
    assert (runs / "soma.sqlite3").exists() is False


@pytest.mark.anyio
async def test_worker_tool_schemas_contain_no_credential_or_principal_assertion(tmp_path: Path) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    _issue_grant(fixture, issue.principal.principal_id, suffix="one")
    async with _http_client(fixture["app"], _bearer(issue)) as client:
        tools = await client.list_tools()
    by_name = {tool.name: tool.model_dump(mode="json") for tool in tools}
    assert set(by_name) == {"worker_capabilities", "worker_invoke"}
    schema_text = json.dumps(by_name, sort_keys=True)
    assert '"credential"' not in schema_text
    assert '"principal_id"' not in schema_text
    for owner_name in PUBLIC_GATEWAY_NAMES:
        assert owner_name not in by_name


@pytest.mark.anyio
async def test_token_verifier_redacts_transport_secret_from_access_context(tmp_path: Path) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    bearer = _bearer(issue)
    verifier = WorkerBearerTokenVerifier(
        fixture["service"],
        clock=lambda: fixture["clock"][0],
    )
    verified = await verifier.verify_token(bearer)
    assert verified is not None
    assert verified.subject == issue.principal.principal_id
    assert verified.token == "[verified-worker-token]"
    assert issue.credential_once not in str(verified)
    assert bearer not in str(verified)
    assert await verifier.verify_token("malformed") is None
    assert await verifier.verify_token(
        make_worker_bearer(issue.principal.principal_id, "wa1_wrong")
    ) is None


@pytest.mark.anyio
async def test_invalid_bearer_is_rejected_by_http_auth_before_worker_tools(tmp_path: Path) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    bad = make_worker_bearer(issue.principal.principal_id, "wa1_wrong")
    with pytest.raises(Exception) as excinfo:
        async with _http_client(fixture["app"], bad):
            raise AssertionError("invalid bearer unexpectedly connected")
    assert _http_status_codes(excinfo.value) == {401}
    assert issue.credential_once not in str(excinfo.value)
    assert fixture["calls"] == []


@pytest.mark.anyio
async def test_discovery_returns_only_authenticated_principal_active_executable_grants(
    tmp_path: Path,
) -> None:
    fixture = _prepare(tmp_path)
    first = _issue_principal(fixture, "first")
    second = _issue_principal(fixture, "second")
    active = _issue_grant(
        fixture,
        first.principal.principal_id,
        suffix="active",
        parameters={"value": "active"},
    )
    _issue_grant(
        fixture,
        first.principal.principal_id,
        suffix="hidden",
        spec=HIDDEN_SPEC,
        parameters={"value": "hidden"},
    )
    expired = _issue_grant(
        fixture,
        first.principal.principal_id,
        suffix="expires",
        parameters={"value": "expires"},
        expires_at=NOW + timedelta(minutes=10),
    )
    revoked = _issue_grant(
        fixture,
        first.principal.principal_id,
        suffix="revoked",
        parameters={"value": "revoked"},
    )
    other = _issue_grant(
        fixture,
        second.principal.principal_id,
        suffix="other",
        parameters={"value": "other"},
    )
    oversized = _issue_grant(
        fixture,
        first.principal.principal_id,
        suffix="oversized",
        parameters={"value": "x" * (WORKER_PARAMETER_MAX_BYTES + 1)},
    )
    fixture["service"].store.revoke(
        target_kind="grant",
        target_id=revoked.grant_id,
        controller_request_id="worker-gateway-revoke-grant",
        reason_ref="reason:test",
        reason_hash=_digest("revoked"),
        issuer_ref=OWNER,
        revoked_at=NOW,
    )
    fixture["clock"][0] = NOW + timedelta(minutes=15)

    async with _http_client(fixture["app"], _bearer(first)) as client:
        response = await client.call_tool("worker_capabilities", {})
    payload = response.structured_content
    assert payload["ok"] is True
    assert payload["principal_id"] == first.principal.principal_id
    grant_ids = {entry["grant_id"] for entry in payload["capabilities"]}
    assert grant_ids == {active.grant_id}
    assert expired.grant_id not in grant_ids
    assert revoked.grant_id not in grant_ids
    assert other.grant_id not in grant_ids
    assert oversized.grant_id not in grant_ids
    assert all(entry["operation_ref"] == ECHO_SPEC.operation_ref for entry in payload["capabilities"])
    text = json.dumps(payload, sort_keys=True)
    assert first.credential_once not in text
    assert first.principal.verifier_hash not in text


@pytest.mark.anyio
async def test_stale_session_scope_and_cancelled_task_deny_transport_auth(tmp_path: Path) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    _issue_grant(fixture, issue.principal.principal_id, suffix="one")
    bearer = _bearer(issue)

    fixture["substrate"].set_binding_disposition(
        fixture["binding"].session_binding_id,
        disposition=SessionBindingDisposition.MISMATCH_DETECTED,
        reason="fixture mismatch",
    )
    with pytest.raises(Exception) as session_exc:
        async with _http_client(fixture["app"], bearer):
            pass
    assert _http_status_codes(session_exc.value) == {401}

    fixture["substrate"].set_binding_disposition(
        fixture["binding"].session_binding_id,
        disposition=SessionBindingDisposition.BOUND,
        reason="fixture restored",
    )
    with fixture["scope"].connect() as conn:
        conn.execute(
            "UPDATE projects SET scope_generation = 2, updated_at = ? WHERE project_id = ?",
            (NOW.isoformat(), PROJECT_ID),
        )
    with pytest.raises(Exception) as scope_exc:
        async with _http_client(fixture["app"], bearer):
            pass
    assert _http_status_codes(scope_exc.value) == {401}

    with fixture["scope"].connect() as conn:
        conn.execute(
            "UPDATE projects SET scope_generation = 1, updated_at = ? WHERE project_id = ?",
            (NOW.isoformat(), PROJECT_ID),
        )
        conn.execute(
            "INSERT INTO task_commands("
            "command_id, task_id, command_kind, controller_request_id, "
            "requested_state_version, observed_state_version, status, reason, created_at) "
            "VALUES ('taskcmd_20260814T170000Z_dddddddddddd', ?, 'cancel', "
            "'worker-gateway-cancel', 1, 1, 'accepted', 'fixture', ?)",
            (TASK_ID, NOW.isoformat()),
        )
    with pytest.raises(Exception) as cancel_exc:
        async with _http_client(fixture["app"], bearer):
            pass
    assert _http_status_codes(cancel_exc.value) == {401}


@pytest.mark.anyio
async def test_revoked_principal_is_rejected_before_tool_execution(tmp_path: Path) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    fixture["service"].store.revoke(
        target_kind="principal",
        target_id=issue.principal.principal_id,
        controller_request_id="worker-gateway-revoke-principal",
        reason_ref="reason:test",
        reason_hash=_digest("principal revoked"),
        issuer_ref=OWNER,
        revoked_at=NOW,
    )
    with pytest.raises(Exception) as excinfo:
        async with _http_client(fixture["app"], _bearer(issue)):
            pass
    assert _http_status_codes(excinfo.value) == {401}
    assert fixture["calls"] == []


@pytest.mark.anyio
async def test_successful_invoke_reauthorizes_and_handler_receives_no_transport_secret(
    tmp_path: Path,
) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    fixture["leaked"]["credential"] = issue.credential_once
    grant = _issue_grant(
        fixture,
        issue.principal.principal_id,
        suffix="echo",
        parameters={"value": "hello"},
    )
    async with _http_client(fixture["app"], _bearer(issue)) as client:
        response = await client.call_tool(
            "worker_invoke",
            {
                "grant_id": grant.grant_id,
                "parameters": {"value": "hello"},
                "expected_task_state_version": 1,
                "controller_request_id": "worker-invoke-1",
            },
        )
    payload = response.structured_content
    assert payload["ok"] is True
    assert payload["principal_id"] == issue.principal.principal_id
    assert payload["grant_id"] == grant.grant_id
    assert payload["result"]["echo"] == {"value": "hello"}
    assert payload["result"]["credential"] == "[REDACTED]"
    assert payload["result"]["verifier_hash"] == "[REDACTED]"
    assert payload["result"]["token"] == "[REDACTED]"
    assert payload["result"]["client_secret"] == "[REDACTED]"
    assert payload["result"]["nested"]["private-key"] == "[REDACTED]"
    assert payload["result"]["opaque"] == "[unsupported:_SecretObject]"
    assert len(fixture["calls"]) == 1
    context = fixture["calls"][0]
    assert not hasattr(context, "credential")
    assert not hasattr(context, "bearer")
    assert context.decision.principal_id == issue.principal.principal_id
    text = json.dumps(payload, sort_keys=True)
    assert issue.credential_once not in text
    assert _bearer(issue) not in text
    assert issue.principal.verifier_hash not in text


@pytest.mark.anyio
async def test_wrong_principal_parameters_state_and_revocation_fail_before_handler(
    tmp_path: Path,
) -> None:
    fixture = _prepare(tmp_path)
    first = _issue_principal(fixture, "first")
    second = _issue_principal(fixture, "second")
    grant = _issue_grant(
        fixture,
        first.principal.principal_id,
        suffix="echo",
        parameters={"value": "hello"},
    )

    async with _http_client(fixture["app"], _bearer(second)) as client:
        wrong_principal = await client.call_tool(
            "worker_invoke",
            {
                "grant_id": grant.grant_id,
                "parameters": {"value": "hello"},
                "expected_task_state_version": 1,
                "controller_request_id": "wrong-principal",
            },
        )
    assert wrong_principal.structured_content["error"]["code"] == "grant_principal_mismatch"
    assert fixture["calls"] == []

    async with _http_client(fixture["app"], _bearer(first)) as client:
        wrong_params = await client.call_tool(
            "worker_invoke",
            {
                "grant_id": grant.grant_id,
                "parameters": {"value": "different"},
                "expected_task_state_version": 1,
                "controller_request_id": "wrong-params",
            },
        )
        stale = await client.call_tool(
            "worker_invoke",
            {
                "grant_id": grant.grant_id,
                "parameters": {"value": "hello"},
                "expected_task_state_version": 999,
                "controller_request_id": "stale-state",
            },
        )
    assert wrong_params.structured_content["error"]["code"] == "parameter_contract_mismatch"
    assert stale.structured_content["error"]["code"] == "stale_task_state_version"
    assert fixture["calls"] == []

    fixture["service"].store.revoke(
        target_kind="grant",
        target_id=grant.grant_id,
        controller_request_id="revoke-before-invoke",
        reason_ref="reason:test",
        reason_hash=_digest("revoke invoke"),
        issuer_ref=OWNER,
        revoked_at=NOW,
    )
    async with _http_client(fixture["app"], _bearer(first)) as client:
        revoked = await client.call_tool(
            "worker_invoke",
            {
                "grant_id": grant.grant_id,
                "parameters": {"value": "hello"},
                "expected_task_state_version": 1,
                "controller_request_id": "revoked-invoke",
            },
        )
    assert revoked.structured_content["error"]["code"] == "grant_revoked"
    assert fixture["calls"] == []


@pytest.mark.anyio
async def test_oversized_worker_parameters_fail_before_handler(tmp_path: Path) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    grant = _issue_grant(
        fixture,
        issue.principal.principal_id,
        suffix="bounded",
        parameters={"value": "bounded"},
    )
    oversized = {"value": "x" * (WORKER_PARAMETER_MAX_BYTES + 1)}
    async with _http_client(fixture["app"], _bearer(issue)) as client:
        response = await client.call_tool(
            "worker_invoke",
            {
                "grant_id": grant.grant_id,
                "parameters": oversized,
                "expected_task_state_version": 1,
                "controller_request_id": "oversized-parameters",
            },
        )
    assert response.structured_content["error"]["code"] == "parameter_contract_too_large"
    assert fixture["calls"] == []


@pytest.mark.anyio
async def test_expired_grant_fails_before_handler(tmp_path: Path) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    grant = _issue_grant(
        fixture,
        issue.principal.principal_id,
        suffix="expires",
        parameters={"value": "hello"},
        expires_at=NOW + timedelta(minutes=10),
    )
    fixture["clock"][0] = NOW + timedelta(minutes=15)
    async with _http_client(fixture["app"], _bearer(issue)) as client:
        response = await client.call_tool(
            "worker_invoke",
            {
                "grant_id": grant.grant_id,
                "parameters": {"value": "hello"},
                "expected_task_state_version": 1,
                "controller_request_id": "expired-invoke",
            },
        )
    assert response.structured_content["error"]["code"] == "grant_expired"
    assert fixture["calls"] == []


@pytest.mark.anyio
async def test_grant_without_transport_handler_is_not_discovered_and_cannot_execute(
    tmp_path: Path,
) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    hidden = _issue_grant(
        fixture,
        issue.principal.principal_id,
        suffix="hidden",
        spec=HIDDEN_SPEC,
        parameters={"value": "hidden"},
    )
    async with _http_client(fixture["app"], _bearer(issue)) as client:
        discovered = await client.call_tool("worker_capabilities", {})
        invoked = await client.call_tool(
            "worker_invoke",
            {
                "grant_id": hidden.grant_id,
                "parameters": {"value": "hidden"},
                "expected_task_state_version": 1,
                "controller_request_id": "hidden-invoke",
            },
        )
    assert discovered.structured_content["capabilities"] == []
    assert invoked.structured_content["error"]["code"] == "operation_not_executable"
    assert fixture["calls"] == []


@pytest.mark.anyio
async def test_dispatch_propagates_cancellation(tmp_path: Path) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    grant = _issue_grant(
        fixture,
        issue.principal.principal_id,
        suffix="cancel",
        parameters={"value": "cancel"},
    )
    decision = fixture["service"].authorize_authenticated(
        principal_id=issue.principal.principal_id,
        grant_id=grant.grant_id,
        parameters={"value": "cancel"},
        expected_task_state_version=1,
        now=NOW,
    )
    dispatch = WorkerOperationDispatchRegistry(fixture["registry"])

    async def cancel_handler(_context):
        raise asyncio.CancelledError

    dispatch.register(ECHO_SPEC.operation_ref, cancel_handler)
    with pytest.raises(asyncio.CancelledError):
        await dispatch.dispatch(
            WorkerDispatchContext(
                decision=decision,
                grant=grant,
                controller_request_id="cancel-propagation",
                parameters={"value": "cancel"},
            )
        )


def test_dispatch_registry_blocks_owner_names_protected_ops_unknowns_and_duplicates() -> None:
    owner_spec = WorkerOperationSpecV1(
        operation_ref="repo_apply",
        operation_kind="action",
        requires_session=True,
        allowed_task_states=("running",),
    )
    registry = WorkerOperationRegistry((ECHO_SPEC, PROTECTED_SPEC, owner_spec))
    dispatch = WorkerOperationDispatchRegistry(registry)

    def handler(_context):
        return {"ok": True}
    with pytest.raises(ValueError, match="owner/executive"):
        dispatch.register("repo_apply", handler)
    with pytest.raises(ValueError, match="protected mutation"):
        dispatch.register(PROTECTED_SPEC.operation_ref, handler)
    with pytest.raises(WorkerAuthorizationDenied) as excinfo:
        dispatch.register("worker-operation:not-registered", handler)
    assert excinfo.value.code == "operation_not_registered"
    dispatch.register(ECHO_SPEC.operation_ref, handler)
    with pytest.raises(ValueError, match="duplicate"):
        dispatch.register(ECHO_SPEC.operation_ref, handler)


@pytest.mark.anyio
async def test_handler_failure_is_bounded_and_does_not_reflect_secret(tmp_path: Path) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    fixture["leaked"]["credential"] = issue.credential_once
    grant = _issue_grant(
        fixture,
        issue.principal.principal_id,
        suffix="fail",
        spec=FAIL_SPEC,
        parameters={"value": "fail"},
    )
    async with _http_client(fixture["app"], _bearer(issue)) as client:
        response = await client.call_tool(
            "worker_invoke",
            {
                "grant_id": grant.grant_id,
                "parameters": {"value": "fail"},
                "expected_task_state_version": 1,
                "controller_request_id": "fail-invoke",
            },
        )
    payload = response.structured_content
    assert payload == {
        "ok": False,
        "error": {"code": "handler_failed", "detail": "worker operation failed"},
    }
    text = json.dumps(payload, sort_keys=True)
    assert issue.credential_once not in text
    assert "fixture failure" not in text
    assert len(fixture["calls"]) == 1


@pytest.mark.anyio
async def test_strict_worker_invoke_schema_rejects_authority_claim_injection(tmp_path: Path) -> None:
    fixture = _prepare(tmp_path)
    issue = _issue_principal(fixture, "one")
    grant = _issue_grant(fixture, issue.principal.principal_id, suffix="one")
    async with _http_client(fixture["app"], _bearer(issue)) as client:
        with pytest.raises(Exception) as excinfo:
            await client.call_tool(
                "worker_invoke",
                {
                    "grant_id": grant.grant_id,
                    "parameters": {"value": "one"},
                    "expected_task_state_version": 1,
                    "controller_request_id": "inject-authority",
                    "principal_id": "forged-principal",
                    "mandate_ref": "forged-mandate",
                    "operation_ref": "repo_apply",
                },
            )
    assert fixture["calls"] == []
    text = str(excinfo.value)
    assert issue.credential_once not in text
    assert _bearer(issue) not in text


def test_source_file_has_no_live_server_registration_or_listener_wiring() -> None:
    transport_path = Path(__file__).parents[1] / "soma" / "worker_gateway" / "transport.py"
    source = transport_path.read_text(encoding="utf-8")
    assert "import soma.server" not in source
    assert "from soma.server" not in source
    assert ".run(" not in source
    assert ".mount(" not in source
    assert "Cloudflare" not in source
