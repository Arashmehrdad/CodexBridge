"""Pure V3-2 worker authentication and positive authorization engine.

This module never launches a provider, calls a worker tool, crosses a protected
effect boundary, or mutates canonical Task/Run/ProjectScope/session state. It
only issues bounded worker authority records and mechanically decides whether a
new action may be delegated.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

from soma.project_scope.store import ProjectScopeStore
from soma.protected_tools.broker import ProtectedAuthoritySnapshotV1
from soma.protected_tools.models import ProtectedToolCallV1
from soma.tasks.models import TERMINAL_TASK_STATES
from soma.tasks.store import TaskStore
from soma.worker_substrate import SessionBindingDisposition, WorkerSubstrateStore

from .models import (
    WORKER_CREDENTIAL_PREFIX,
    WORKER_GRANT_CAPABILITY_PREFIX,
    WorkerAuthorizationDecisionV1,
    WorkerAuthorizationDenied,
    WorkerAuthorizationRequestV1,
    WorkerAuthorityConflict,
    WorkerCapabilityGrantIssueV1,
    WorkerCapabilityGrantV1,
    WorkerOperationSpecV1,
    WorkerPrincipalIssueResultV1,
    WorkerPrincipalIssueV1,
    WorkerPrincipalV1,
    canonical_hash,
    make_authority_id,
)
from .store import WorkerAuthorityStore


class WorkerOperationRegistry:
    """Immutable reviewed operation identity registry.

    The registry describes which operations *could* be granted. Possession is
    still resolved from one exact durable grant on every authorization call.
    """

    def __init__(self, specs: Iterable[WorkerOperationSpecV1] = ()) -> None:
        mapping: dict[str, WorkerOperationSpecV1] = {}
        for spec in specs:
            if spec.operation_ref in mapping:
                raise ValueError(f"Duplicate worker operation_ref: {spec.operation_ref}")
            mapping[spec.operation_ref] = spec
        self._specs = mapping

    def require(self, operation_ref: str) -> WorkerOperationSpecV1:
        try:
            return self._specs[operation_ref]
        except KeyError as exc:
            raise WorkerAuthorizationDenied(
                "operation_not_registered",
                f"worker operation is not in reviewed registry: {operation_ref}",
            ) from exc

    def projection(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "operation_ref": spec.operation_ref,
                "operation_hash": spec.operation_hash,
                "operation_kind": spec.operation_kind,
                "requires_session": spec.requires_session,
                "allowed_task_states": list(spec.allowed_task_states),
                "approval_required": spec.approval_required,
            }
            for spec in sorted(self._specs.values(), key=lambda item: item.operation_ref)
        )


class WorkerAuthorityService:
    def __init__(
        self,
        runs_dir: Path,
        *,
        registry: WorkerOperationRegistry | None = None,
    ) -> None:
        self.runs_dir = Path(runs_dir)
        self.store = WorkerAuthorityStore(self.runs_dir)
        self.registry = registry or WorkerOperationRegistry()

    @staticmethod
    def _now(value: datetime | None = None) -> datetime:
        current = value or datetime.now(timezone.utc)
        if current.tzinfo is None or current.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        return current

    def _require_installed(self) -> None:
        if not self.store.is_installed():
            raise WorkerAuthorizationDenied(
                "authority_schema_inactive",
                "worker authority schema is not explicitly installed",
            )

    @staticmethod
    def _credential_hash(credential: str) -> str:
        return sha256(credential.encode("utf-8")).hexdigest()

    def _validate_scope_task_session(
        self,
        *,
        principal: WorkerPrincipalV1,
        require_session: bool,
    ) -> tuple[Any, Any]:
        scope_store = ProjectScopeStore(self.runs_dir)
        try:
            scope = scope_store.require_task_attempt(
                principal.project_id,
                principal.task_id,
                principal.run_id,
            )
        except (KeyError, ValueError) as exc:
            raise WorkerAuthorizationDenied(
                "project_scope_mismatch",
                "principal Task/Run is outside the current ProjectScope",
            ) from exc
        if (
            scope.resource_id != principal.resource_id
            or scope.scope_generation != principal.scope_generation
            or scope.binding_status != "attached"
            or scope.attempt_status != "attached"
        ):
            raise WorkerAuthorizationDenied(
                "project_scope_mismatch",
                "principal ProjectScope resource/generation/attachment is stale",
            )

        try:
            task = TaskStore(self.runs_dir).get_task(principal.task_id)
        except KeyError as exc:
            raise WorkerAuthorizationDenied(
                "task_missing", "canonical Task no longer exists"
            ) from exc
        if task.backend_ref != principal.run_id:
            raise WorkerAuthorizationDenied(
                "run_binding_mismatch", "Task backend_ref differs from principal run_id"
            )
        if task.state in TERMINAL_TASK_STATES:
            raise WorkerAuthorizationDenied(
                "task_terminal", f"canonical Task is terminal: {task.state.value}"
            )

        if require_session and not principal.session_binding_id:
            raise WorkerAuthorizationDenied(
                "session_required", "operation requires an interactive session binding"
            )
        if principal.session_binding_id:
            try:
                binding = WorkerSubstrateStore(self.runs_dir).get_binding(
                    principal.session_binding_id
                )
            except KeyError as exc:
                raise WorkerAuthorizationDenied(
                    "session_missing", "provider-session binding no longer exists"
                ) from exc
            if (
                binding.project_id != principal.project_id
                or binding.resource_id != principal.resource_id
                or binding.task_id != principal.task_id
                or binding.run_id != principal.run_id
            ):
                raise WorkerAuthorizationDenied(
                    "session_mismatch",
                    "provider-session binding differs from principal ceiling",
                )
            if binding.disposition is not SessionBindingDisposition.BOUND:
                raise WorkerAuthorizationDenied(
                    "session_not_bound",
                    f"provider-session disposition is {binding.disposition.value!r}",
                )
        return scope, task

    def _require_not_cancelled(self, task_id: str) -> None:
        with TaskStore(self.runs_dir)._read() as conn:
            row = conn.execute(
                "SELECT 1 FROM task_commands WHERE task_id = ? AND command_kind = 'cancel' "
                "AND status != 'rejected_stale_version' LIMIT 1",
                (task_id,),
            ).fetchone()
        if row is not None:
            raise WorkerAuthorizationDenied(
                "cancellation_precedence",
                "accepted Task cancellation intent denies new worker actions",
            )

    def _require_principal_active(
        self,
        principal: WorkerPrincipalV1,
        *,
        now: datetime,
        require_session: bool,
    ) -> Any:
        if self.store.revocation_for("principal", principal.principal_id) is not None:
            raise WorkerAuthorizationDenied(
                "principal_revoked", "worker principal is revoked"
            )
        if now >= principal.expires_at:
            raise WorkerAuthorizationDenied(
                "principal_expired", "worker principal has expired"
            )
        _scope, task = self._validate_scope_task_session(
            principal=principal,
            require_session=require_session,
        )
        self._require_not_cancelled(principal.task_id)
        return task

    def issue_principal(
        self,
        request: WorkerPrincipalIssueV1,
        *,
        now: datetime | None = None,
    ) -> WorkerPrincipalIssueResultV1:
        self._require_installed()
        existing = self.store.principal_for_request(request.controller_request_id)
        if existing is not None:
            if existing.request_hash != request.request_hash:
                raise WorkerAuthorityConflict(
                    "controller_request_id is already bound to different worker principal authority"
                )
            return WorkerPrincipalIssueResultV1(
                principal=existing,
                created=False,
                credential_once=None,
            )

        current = self._now(now)
        if request.expires_at <= current:
            raise WorkerAuthorizationDenied(
                "principal_expiry_invalid", "principal expiry must be in the future"
            )

        provisional = WorkerPrincipalV1(
            principal_id=make_authority_id("wprincipal"),
            verifier_hash="0" * 64,
            project_id=request.project_id,
            resource_id=request.resource_id,
            scope_generation=request.scope_generation,
            task_id=request.task_id,
            run_id=request.run_id,
            session_binding_id=request.session_binding_id,
            role_ref=request.role_ref,
            mandate_ref=request.mandate_ref,
            mandate_hash=request.mandate_hash,
            mandate_version=request.mandate_version,
            issuer_ref=request.issuer_ref,
            expires_at=request.expires_at,
            controller_request_id=request.controller_request_id,
            request_hash=request.request_hash,
            content_hash="0" * 64,
            created_at=current,
        )
        self._validate_scope_task_session(
            principal=provisional,
            require_session=bool(request.session_binding_id),
        )
        self._require_not_cancelled(request.task_id)

        credential = WORKER_CREDENTIAL_PREFIX + secrets.token_urlsafe(32)
        verifier_hash = self._credential_hash(credential)
        semantic = {
            **request.authority_material(),
            "verifier_hash": verifier_hash,
        }
        principal = provisional.model_copy(
            update={
                "verifier_hash": verifier_hash,
                "content_hash": canonical_hash(semantic),
            }
        )
        durable, created = self.store.reserve_principal(principal)
        return WorkerPrincipalIssueResultV1(
            principal=durable,
            created=created,
            credential_once=credential if created else None,
        )

    @staticmethod
    def _grant_semantic(
        principal: WorkerPrincipalV1,
        request: WorkerCapabilityGrantIssueV1,
    ) -> dict[str, Any]:
        return {
            "principal_id": principal.principal_id,
            "project_id": principal.project_id,
            "resource_id": principal.resource_id,
            "scope_generation": principal.scope_generation,
            "task_id": principal.task_id,
            "run_id": principal.run_id,
            "session_binding_id": principal.session_binding_id,
            "role_ref": principal.role_ref,
            "mandate_ref": principal.mandate_ref,
            "mandate_hash": principal.mandate_hash,
            "mandate_version": principal.mandate_version,
            "intent_ref": request.intent_ref,
            "intent_hash": request.intent_hash,
            "operation_ref": request.operation_ref,
            "operation_hash": request.operation_hash,
            "parameter_contract_hash": canonical_hash(request.parameter_contract),
            "issuer_ref": request.issuer_ref,
            "expires_at": request.expires_at.isoformat(),
        }

    def issue_grant(
        self,
        request: WorkerCapabilityGrantIssueV1,
        *,
        now: datetime | None = None,
    ) -> tuple[WorkerCapabilityGrantV1, bool]:
        self._require_installed()
        try:
            principal = self.store.get_principal(request.principal_id)
        except KeyError as exc:
            raise WorkerAuthorizationDenied(
                "principal_missing", "grant principal does not exist"
            ) from exc

        semantic = self._grant_semantic(principal, request)
        request_hash = canonical_hash(semantic)
        existing = self.store.grant_for_request(request.controller_request_id)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise WorkerAuthorityConflict(
                    "controller_request_id is already bound to different worker grant authority"
                )
            return existing, False

        current = self._now(now)
        task = self._require_principal_active(
            principal,
            now=current,
            require_session=bool(principal.session_binding_id),
        )
        if request.issuer_ref != principal.issuer_ref:
            raise WorkerAuthorizationDenied(
                "grant_issuer_mismatch", "grant issuer differs from principal issuer"
            )
        if request.expires_at <= current or request.expires_at > principal.expires_at:
            raise WorkerAuthorizationDenied(
                "grant_expiry_invalid",
                "grant expiry must be future and no later than principal expiry",
            )
        spec = self.registry.require(request.operation_ref)
        if request.operation_hash != spec.operation_hash:
            raise WorkerAuthorizationDenied(
                "operation_hash_mismatch", "grant operation hash is not registry-exact"
            )
        if task.state.value not in spec.allowed_task_states:
            raise WorkerAuthorizationDenied(
                "task_state_not_allowed",
                f"operation does not allow Task state {task.state.value!r}",
            )
        if spec.requires_session and not principal.session_binding_id:
            raise WorkerAuthorizationDenied(
                "session_required", "operation requires a session-bound principal"
            )

        parameter_hash = canonical_hash(request.parameter_contract)
        grant = WorkerCapabilityGrantV1(
            grant_id=make_authority_id("wgrant"),
            principal_id=principal.principal_id,
            project_id=principal.project_id,
            resource_id=principal.resource_id,
            scope_generation=principal.scope_generation,
            task_id=principal.task_id,
            run_id=principal.run_id,
            session_binding_id=principal.session_binding_id,
            role_ref=principal.role_ref,
            mandate_ref=principal.mandate_ref,
            mandate_hash=principal.mandate_hash,
            mandate_version=principal.mandate_version,
            intent_ref=request.intent_ref,
            intent_hash=request.intent_hash,
            operation_ref=request.operation_ref,
            operation_hash=request.operation_hash,
            parameter_contract=request.parameter_contract,
            parameter_contract_hash=parameter_hash,
            issuer_ref=request.issuer_ref,
            expires_at=request.expires_at,
            controller_request_id=request.controller_request_id,
            request_hash=request_hash,
            content_hash=canonical_hash(semantic),
            created_at=current,
        )
        return self.store.reserve_grant(grant)

    def authenticate(self, principal_id: str, credential: str) -> WorkerPrincipalV1:
        self._require_installed()
        try:
            principal = self.store.get_principal(principal_id)
        except KeyError as exc:
            raise WorkerAuthorizationDenied(
                "credential_invalid", "worker principal credential is invalid"
            ) from exc
        submitted = self._credential_hash(credential)
        if not hmac.compare_digest(submitted, principal.verifier_hash):
            raise WorkerAuthorizationDenied(
                "credential_invalid", "worker principal credential is invalid"
            )
        return principal

    def authenticate_active(
        self,
        principal_id: str,
        credential: str,
        *,
        now: datetime | None = None,
    ) -> WorkerPrincipalV1:
        current = self._now(now)
        principal = self.authenticate(principal_id, credential)
        self._require_principal_active(
            principal,
            now=current,
            require_session=False,
        )
        return principal

    def _authorize_loaded(
        self,
        *,
        principal: WorkerPrincipalV1,
        grant: WorkerCapabilityGrantV1,
        parameters: dict[str, Any],
        expected_task_state_version: int,
        current: datetime,
    ) -> WorkerAuthorizationDecisionV1:
        spec = self.registry.require(grant.operation_ref)
        task = self._require_principal_active(
            principal,
            now=current,
            require_session=spec.requires_session,
        )
        if self.store.revocation_for("grant", grant.grant_id) is not None:
            raise WorkerAuthorizationDenied("grant_revoked", "capability grant is revoked")
        if current >= grant.expires_at:
            raise WorkerAuthorizationDenied("grant_expired", "capability grant has expired")
        if grant.principal_id != principal.principal_id:
            raise WorkerAuthorizationDenied(
                "grant_principal_mismatch", "grant belongs to a different principal"
            )
        ceiling = (
            "project_id",
            "resource_id",
            "scope_generation",
            "task_id",
            "run_id",
            "session_binding_id",
            "role_ref",
            "mandate_ref",
            "mandate_hash",
            "mandate_version",
        )
        for field in ceiling:
            if getattr(grant, field) != getattr(principal, field):
                raise WorkerAuthorizationDenied(
                    "grant_ceiling_mismatch", f"grant {field} differs from principal"
                )
        if grant.operation_hash != spec.operation_hash:
            raise WorkerAuthorizationDenied(
                "operation_registry_drift", "grant operation no longer matches registry"
            )
        if task.state.value not in spec.allowed_task_states:
            raise WorkerAuthorizationDenied(
                "task_state_not_allowed",
                f"operation does not allow Task state {task.state.value!r}",
            )
        if task.state_version != expected_task_state_version:
            raise WorkerAuthorizationDenied(
                "stale_task_state_version", "Task state version differs from request"
            )
        if canonical_hash(parameters) != grant.parameter_contract_hash:
            raise WorkerAuthorizationDenied(
                "parameter_contract_mismatch",
                "submitted parameters exceed or differ from exact positive grant contract",
            )
        return WorkerAuthorizationDecisionV1(
            principal_id=principal.principal_id,
            grant_id=grant.grant_id,
            project_id=principal.project_id,
            resource_id=principal.resource_id,
            scope_generation=principal.scope_generation,
            task_id=principal.task_id,
            run_id=principal.run_id,
            session_binding_id=principal.session_binding_id,
            role_ref=principal.role_ref,
            mandate_ref=principal.mandate_ref,
            mandate_hash=principal.mandate_hash,
            mandate_version=principal.mandate_version,
            intent_ref=grant.intent_ref,
            intent_hash=grant.intent_hash,
            operation_ref=grant.operation_ref,
            operation_hash=grant.operation_hash,
            parameter_contract_hash=grant.parameter_contract_hash,
            task_state=task.state.value,
            task_state_version=task.state_version,
        )

    def authorize_authenticated(
        self,
        *,
        principal_id: str,
        grant_id: str,
        parameters: dict[str, Any],
        expected_task_state_version: int,
        now: datetime | None = None,
    ) -> WorkerAuthorizationDecisionV1:
        self._require_installed()
        current = self._now(now)
        try:
            principal = self.store.get_principal(principal_id)
            grant = self.store.get_grant(grant_id)
        except KeyError as exc:
            raise WorkerAuthorizationDenied(
                "grant_missing", "positive capability grant does not exist"
            ) from exc
        return self._authorize_loaded(
            principal=principal,
            grant=grant,
            parameters=parameters,
            expected_task_state_version=expected_task_state_version,
            current=current,
        )

    def usable_grants(
        self,
        principal_id: str,
        *,
        now: datetime | None = None,
    ) -> tuple[tuple[WorkerCapabilityGrantV1, WorkerAuthorizationDecisionV1], ...]:
        self._require_installed()
        current = self._now(now)
        try:
            principal = self.store.get_principal(principal_id)
        except KeyError as exc:
            raise WorkerAuthorizationDenied(
                "principal_missing", "worker principal does not exist"
            ) from exc
        self._require_principal_active(
            principal,
            now=current,
            require_session=False,
        )
        usable: list[tuple[WorkerCapabilityGrantV1, WorkerAuthorizationDecisionV1]] = []
        for grant in self.store.grants_for_principal(principal_id):
            try:
                task = TaskStore(self.runs_dir).get_task(principal.task_id)
                decision = self._authorize_loaded(
                    principal=principal,
                    grant=grant,
                    parameters=grant.parameter_contract,
                    expected_task_state_version=task.state_version,
                    current=current,
                )
            except (KeyError, WorkerAuthorizationDenied):
                continue
            usable.append((grant, decision))
        return tuple(usable)

    def authorize(
        self,
        request: WorkerAuthorizationRequestV1,
        *,
        now: datetime | None = None,
    ) -> WorkerAuthorizationDecisionV1:
        current = self._now(now)
        principal = self.authenticate(request.principal_id, request.credential)
        try:
            grant = self.store.get_grant(request.grant_id)
        except KeyError as exc:
            raise WorkerAuthorizationDenied(
                "grant_missing", "positive capability grant does not exist"
            ) from exc
        expected = {
            "role_ref": principal.role_ref,
            "mandate_ref": principal.mandate_ref,
            "mandate_hash": principal.mandate_hash,
            "mandate_version": principal.mandate_version,
            "intent_ref": grant.intent_ref,
            "intent_hash": grant.intent_hash,
            "operation_ref": grant.operation_ref,
            "operation_hash": grant.operation_hash,
        }
        for field, value in expected.items():
            if getattr(request, field) != value:
                raise WorkerAuthorizationDenied(
                    f"{field}_mismatch", f"submitted {field} is not grant-exact"
                )
        return self._authorize_loaded(
            principal=principal,
            grant=grant,
            parameters=request.parameters,
            expected_task_state_version=request.expected_task_state_version,
            current=current,
        )

    @staticmethod
    def protected_idempotency_key(grant: WorkerCapabilityGrantV1) -> str:
        digest = sha256(
            f"{grant.intent_hash}\0{grant.operation_hash}\0{grant.parameter_contract_hash}".encode(
                "utf-8"
            )
        ).hexdigest()[:32]
        return f"worker-authority:{grant.grant_id}:{digest}"


class WorkerProtectedAuthorityResolver:
    """Resolve an accepted worker grant into G4 mechanical authority facts only."""

    def __init__(
        self,
        service: WorkerAuthorityService,
        *,
        now: datetime | None = None,
    ) -> None:
        self.service = service
        self.now = now

    def resolve(self, call: ProtectedToolCallV1) -> ProtectedAuthoritySnapshotV1:
        if not call.capability_ref.startswith(WORKER_GRANT_CAPABILITY_PREFIX):
            raise WorkerAuthorizationDenied(
                "capability_ref_invalid", "protected call does not reference a worker grant"
            )
        grant_id = call.capability_ref.removeprefix(WORKER_GRANT_CAPABILITY_PREFIX)
        try:
            grant = self.service.store.get_grant(grant_id)
            principal = self.service.store.get_principal(grant.principal_id)
        except KeyError as exc:
            raise WorkerAuthorizationDenied(
                "capability_missing", "protected worker grant no longer exists"
            ) from exc
        current = self.service._now(self.now)
        spec = self.service.registry.require(grant.operation_ref)
        if spec.operation_kind != "protected_mutation":
            raise WorkerAuthorizationDenied(
                "operation_kind_mismatch", "worker grant is not a protected mutation"
            )
        task = self.service._require_principal_active(
            principal,
            now=current,
            require_session=spec.requires_session,
        )
        if self.service.store.revocation_for("grant", grant.grant_id) is not None:
            raise WorkerAuthorizationDenied("grant_revoked", "capability grant is revoked")
        if current >= grant.expires_at:
            raise WorkerAuthorizationDenied("grant_expired", "capability grant has expired")
        if task.state.value not in spec.allowed_task_states:
            raise WorkerAuthorizationDenied(
                "task_state_not_allowed", "protected operation is not valid in current Task state"
            )
        exact = {
            "task_id": grant.task_id,
            "backend_ref": grant.run_id,
            "mandate_ref": grant.mandate_ref,
            "mandate_hash": grant.mandate_hash,
            "mandate_version": grant.mandate_version,
            "project_id": grant.project_id,
            "resource_id": grant.resource_id,
            "scope_generation": grant.scope_generation,
            "capability_ref": grant.capability_ref,
            "capability_hash": grant.capability_hash,
            "tool_operation_ref": grant.operation_ref,
            "tool_operation_hash": grant.operation_hash,
        }
        for field, value in exact.items():
            if getattr(call, field) != value:
                raise WorkerAuthorizationDenied(
                    f"protected_{field}_mismatch",
                    f"protected call {field} differs from worker grant",
                )
        protected_parameters = {
            "resource_key": call.resource_key,
            "payload_hash": call.payload_hash,
            "mutation_class": call.mutation_class,
        }
        if canonical_hash(protected_parameters) != grant.parameter_contract_hash:
            raise WorkerAuthorizationDenied(
                "parameter_contract_mismatch",
                "protected call resource/payload/mutation contract differs from grant",
            )
        expected_idempotency = self.service.protected_idempotency_key(grant)
        return ProtectedAuthoritySnapshotV1(
            mandate_ref=grant.mandate_ref,
            mandate_hash=grant.mandate_hash,
            mandate_version=grant.mandate_version,
            mandate_active=True,
            capability_ref=grant.capability_ref,
            capability_hash=grant.capability_hash,
            capability_possessed=True,
            tool_operation_ref=grant.operation_ref,
            tool_operation_hash=grant.operation_hash,
            tool_operation_enabled=True,
            idempotency_key=expected_idempotency,
            idempotency_authorized=hmac.compare_digest(
                call.idempotency_key, expected_idempotency
            ),
            approval_required=spec.approval_required,
            approval_valid=False,
            approval_evidence_ref="",
            approval_evidence_hash="",
        )
