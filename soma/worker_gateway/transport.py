"""Isolated, source-only FastMCP worker transport for V3-2.

This module intentionally does not import or mutate ``soma.server.mcp``. The
factory returns a separate FastMCP application with two transport-control tools
and never binds a listener by itself.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final

from fastmcp import FastMCP
from fastmcp.server.auth import AccessToken, TokenVerifier
from fastmcp.server.dependencies import get_access_token
from pydantic import BaseModel

from soma.public_gateway_inventory import PUBLIC_GATEWAY_NAMES
from soma.worker_authority import (
    WorkerAuthorityService,
    WorkerAuthorizationDecisionV1,
    WorkerAuthorizationDenied,
    WorkerCapabilityGrantV1,
    WorkerOperationRegistry,
)

from .models import (
    WorkerCapabilitiesSuccessV1,
    WorkerCapabilityProjectionV1,
    WorkerGatewayErrorV1,
    WorkerGatewayFailureV1,
    WorkerInvokeRequestV1,
    WorkerInvokeSuccessV1,
)


WORKER_BEARER_PREFIX: Final[str] = "wab1"
WORKER_TRANSPORT_SCOPE: Final[str] = "soma:worker"
WORKER_RESULT_MAX_BYTES: Final[int] = 32768
WORKER_PARAMETER_MAX_BYTES: Final[int] = 32768
WORKER_DISCOVERY_MAX_CAPABILITIES: Final[int] = 256
_SENSITIVE_RESULT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "credential",
        "credentialonce",
        "secret",
        "clientsecret",
        "secretkey",
        "password",
        "passphrase",
        "verifierhash",
        "bearer",
        "authorization",
        "apikey",
        "accesstoken",
        "refreshtoken",
        "token",
        "idtoken",
        "authtoken",
        "sessiontoken",
        "privatekey",
        "cookie",
        "setcookie",
    }
)


class WorkerGatewayDispatchError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class WorkerDispatchContext:
    decision: WorkerAuthorizationDecisionV1
    grant: WorkerCapabilityGrantV1
    controller_request_id: str
    parameters: Mapping[str, Any]


WorkerOperationHandler = Callable[[WorkerDispatchContext], Any | Awaitable[Any]]


def make_worker_bearer(principal_id: str, credential: str) -> str:
    """Compose transport bearer material for a principal-issued credential."""
    if not principal_id or "." in principal_id or len(principal_id) > 128:
        raise ValueError("principal_id is not bearer-compatible")
    if not credential.startswith("wa1_") or "." in credential or len(credential) > 512:
        raise ValueError("credential is not worker-authority compatible")
    return f"{WORKER_BEARER_PREFIX}.{principal_id}.{credential}"


def _parse_worker_bearer(token: str) -> tuple[str, str] | None:
    if not isinstance(token, str) or len(token) > 768:
        return None
    parts = token.split(".", 2)
    if len(parts) != 3 or parts[0] != WORKER_BEARER_PREFIX:
        return None
    principal_id, credential = parts[1], parts[2]
    if not principal_id or not credential.startswith("wa1_"):
        return None
    if "." in principal_id or "." in credential:
        return None
    return principal_id, credential


class WorkerBearerTokenVerifier(TokenVerifier):
    """FastMCP verifier that leaves no reusable worker secret in AccessToken."""

    def __init__(
        self,
        authority: WorkerAuthorityService,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__()
        self.authority = authority
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    async def verify_token(self, token: str) -> AccessToken | None:
        parsed = _parse_worker_bearer(token)
        if parsed is None:
            return None
        principal_id, credential = parsed
        try:
            principal = self.authority.authenticate_active(
                principal_id,
                credential,
                now=self.clock(),
            )
        except (KeyError, ValueError, WorkerAuthorizationDenied):
            return None
        return AccessToken(
            token="[verified-worker-token]",
            client_id=f"soma-worker:{principal.principal_id}",
            scopes=[WORKER_TRANSPORT_SCOPE],
            expires_at=int(principal.expires_at.timestamp()),
            subject=principal.principal_id,
            claims={"principal_id": principal.principal_id},
        )


class WorkerOperationDispatchRegistry:
    """Explicit worker operation handlers with no name-based fallback."""

    def __init__(self, authority_registry: WorkerOperationRegistry) -> None:
        self.authority_registry = authority_registry
        self._handlers: dict[str, WorkerOperationHandler] = {}

    def register(self, operation_ref: str, handler: WorkerOperationHandler) -> None:
        if operation_ref in PUBLIC_GATEWAY_NAMES:
            raise ValueError("owner/executive gateway names are forbidden worker operations")
        spec = self.authority_registry.require(operation_ref)
        if spec.operation_kind == "protected_mutation":
            raise ValueError(
                "protected mutation dispatch is outside the source-only worker transport package"
            )
        if operation_ref in self._handlers:
            raise ValueError(f"duplicate worker operation handler: {operation_ref}")
        self._handlers[operation_ref] = handler

    def registered_operations(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))

    async def dispatch(self, context: WorkerDispatchContext) -> Any:
        handler = self._handlers.get(context.decision.operation_ref)
        if handler is None:
            raise WorkerGatewayDispatchError(
                "operation_not_executable",
                "worker operation has no reviewed transport handler",
            )
        try:
            result = handler(context)
            if inspect.isawaitable(result):
                result = await result
            return result
        except WorkerGatewayDispatchError:
            raise
        except Exception as exc:
            raise WorkerGatewayDispatchError(
                "handler_failed",
                "worker operation failed",
            ) from exc


def _normalized_result_key(value: Any) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _redact_result(value: Any, *, depth: int = 0) -> Any:
    if depth > 12:
        return "[truncated]"
    if isinstance(value, BaseModel):
        return _redact_result(value.model_dump(mode="json"), depth=depth + 1)
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if _normalized_result_key(text_key) in _SENSITIVE_RESULT_KEYS:
                output[text_key] = "[REDACTED]"
            else:
                output[text_key] = _redact_result(item, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple)):
        return [_redact_result(item, depth=depth + 1) for item in value[:256]]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"[binary:{len(value)} bytes]"
    if value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and len(value) > 8192:
            return value[:8192] + "...[truncated]"
        return value
    return f"[unsupported:{type(value).__name__}]"


def _json_size_bytes(value: Any) -> int:
    return len(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    )


def _parameter_contract_within_budget(parameters: Mapping[str, Any]) -> bool:
    try:
        return _json_size_bytes(parameters) <= WORKER_PARAMETER_MAX_BYTES
    except (TypeError, ValueError, RecursionError):
        return False


def _require_bounded_parameters(parameters: Mapping[str, Any]) -> None:
    try:
        size = _json_size_bytes(parameters)
    except (TypeError, ValueError, RecursionError) as exc:
        raise WorkerGatewayDispatchError(
            "parameter_contract_invalid",
            "worker parameters are not JSON-compatible",
        ) from exc
    if size > WORKER_PARAMETER_MAX_BYTES:
        raise WorkerGatewayDispatchError(
            "parameter_contract_too_large",
            "worker parameters exceeded the bounded transport limit",
        )


def _bounded_result(value: Any) -> Any:
    redacted = _redact_result(value)
    payload = json.dumps(
        redacted,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    if len(payload) > WORKER_RESULT_MAX_BYTES:
        raise WorkerGatewayDispatchError(
            "result_too_large",
            "worker operation result exceeded the bounded transport limit",
        )
    return redacted


def _failure(code: str, detail: str) -> dict[str, Any]:
    return WorkerGatewayFailureV1(
        error=WorkerGatewayErrorV1(code=code, detail=detail[:512])
    ).model_dump(mode="json")


def _authorization_failure(exc: WorkerAuthorizationDenied) -> dict[str, Any]:
    return _failure(exc.code, exc.detail)


def _authenticated_principal_id() -> str:
    access = get_access_token()
    if access is None or not access.subject:
        raise WorkerGatewayDispatchError(
            "authentication_required",
            "worker authentication is required",
        )
    return str(access.subject)


def build_worker_mcp(
    authority: WorkerAuthorityService,
    dispatch: WorkerOperationDispatchRegistry,
    *,
    clock: Callable[[], datetime] | None = None,
) -> FastMCP:
    """Build but do not run/mount the isolated worker MCP application."""
    if dispatch.authority_registry is not authority.registry:
        raise ValueError("dispatch and authority registries must be the same instance")
    current_time = clock or (lambda: datetime.now(timezone.utc))
    verifier = WorkerBearerTokenVerifier(authority, clock=current_time)
    app = FastMCP(
        "Soma Worker",
        auth=verifier,
        mask_error_details=True,
        strict_input_validation=True,
        instructions=(
            "Isolated worker transport. Use authenticated capability discovery and exact "
            "grant-bound invocation only. This is not the owner/executive Soma MCP surface."
        ),
    )

    @app.tool(
        name="worker_capabilities",
        description=(
            "Return only the authenticated worker principal's currently usable positive grants."
        ),
    )
    async def worker_capabilities() -> dict[str, Any]:
        try:
            principal_id = _authenticated_principal_id()
            usable = authority.usable_grants(principal_id, now=current_time())
            executable = frozenset(dispatch.registered_operations())
            capabilities: list[WorkerCapabilityProjectionV1] = []
            for grant, decision in usable:
                if len(capabilities) >= WORKER_DISCOVERY_MAX_CAPABILITIES:
                    break
                if grant.operation_ref not in executable:
                    continue
                if not _parameter_contract_within_budget(grant.parameter_contract):
                    continue
                capabilities.append(
                    WorkerCapabilityProjectionV1(
                        grant_id=grant.grant_id,
                        intent_ref=grant.intent_ref,
                        intent_hash=grant.intent_hash,
                        operation_ref=grant.operation_ref,
                        operation_hash=grant.operation_hash,
                        operation_kind=authority.registry.require(grant.operation_ref).operation_kind,
                        parameter_contract=_redact_result(grant.parameter_contract),
                        parameter_contract_hash=grant.parameter_contract_hash,
                        task_state=decision.task_state,
                        task_state_version=decision.task_state_version,
                        expires_at=grant.expires_at,
                    )
                )
            payload = WorkerCapabilitiesSuccessV1(
                principal_id=principal_id,
                capabilities=tuple(capabilities),
            ).model_dump(mode="json")
            return _bounded_result(payload)
        except WorkerAuthorizationDenied as exc:
            return _authorization_failure(exc)
        except WorkerGatewayDispatchError as exc:
            return _failure(exc.code, exc.detail)
        except Exception:
            return _failure("worker_gateway_error", "worker capability discovery failed")

    @app.tool(
        name="worker_invoke",
        description=(
            "Re-authorize and invoke one exact positive worker grant through its reviewed handler."
        ),
    )
    async def worker_invoke(
        grant_id: str,
        parameters: dict[str, Any],
        expected_task_state_version: int,
        controller_request_id: str,
    ) -> dict[str, Any]:
        try:
            request = WorkerInvokeRequestV1(
                grant_id=grant_id,
                parameters=parameters,
                expected_task_state_version=expected_task_state_version,
                controller_request_id=controller_request_id,
            )
            _require_bounded_parameters(request.parameters)
            principal_id = _authenticated_principal_id()
            decision = authority.authorize_authenticated(
                principal_id=principal_id,
                grant_id=request.grant_id,
                parameters=request.parameters,
                expected_task_state_version=request.expected_task_state_version,
                now=current_time(),
            )
            grant = authority.store.get_grant(decision.grant_id)
            result = await dispatch.dispatch(
                WorkerDispatchContext(
                    decision=decision,
                    grant=grant,
                    controller_request_id=request.controller_request_id,
                    parameters=request.parameters,
                )
            )
            bounded = _bounded_result(result)
            return WorkerInvokeSuccessV1(
                principal_id=principal_id,
                grant_id=grant.grant_id,
                operation_ref=grant.operation_ref,
                controller_request_id=request.controller_request_id,
                result=bounded,
            ).model_dump(mode="json")
        except WorkerAuthorizationDenied as exc:
            return _authorization_failure(exc)
        except WorkerGatewayDispatchError as exc:
            return _failure(exc.code, exc.detail)
        except (KeyError, ValueError):
            return _failure("worker_request_invalid", "worker invocation request is invalid")
        except Exception:
            return _failure("worker_gateway_error", "worker invocation failed")

    return app
