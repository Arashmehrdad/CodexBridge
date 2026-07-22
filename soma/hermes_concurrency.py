from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from hashlib import sha256
from threading import Condition, Lock
from time import monotonic
from typing import Any, Iterator

from .hermes_companion_protocol import HermesCompanionProtocolError
from .hermes_service import HermesServiceError


class HermesConcurrencyError(HermesServiceError):
    """Concurrency-policy acquisition failure."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HermesAdministrationLock:
    """One exclusive lock for Hermes administration only.

    Installation, upgrade, configuration editing, removal, and registry
    reload serialize here. Discovery, description, and tool calls never
    touch this lock, so administration cannot reduce read paths to a
    global queue. Holder evidence names the operation, never any secret.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._state_lock = Lock()
        self._holder: dict[str, Any] | None = None

    @contextmanager
    def acquire(
        self, operation: str, *, timeout_seconds: float = 60.0
    ) -> Iterator[None]:
        normalized = str(operation).strip()
        if not normalized:
            raise HermesCompanionProtocolError(
                "administration operation must not be empty"
            )
        acquired = self._lock.acquire(timeout=float(timeout_seconds))
        if not acquired:
            with self._state_lock:
                holder = dict(self._holder or {})
            raise HermesConcurrencyError(
                "Hermes administration lock is held by "
                f"{holder.get('operation', 'unknown')!r}"
            )
        with self._state_lock:
            self._holder = {
                "operation": normalized,
                "acquired_at": _utc_now(),
            }
        try:
            yield
        finally:
            with self._state_lock:
                self._holder = None
            self._lock.release()

    def holder(self) -> dict[str, Any] | None:
        with self._state_lock:
            return dict(self._holder) if self._holder else None


class CredentialLockRegistry:
    """Per-credential exclusive locks that never expose credential values.

    Locks are keyed and reported only by the SHA-256 of the credential
    name; neither names nor secret values reach public state.
    """

    def __init__(self) -> None:
        self._registry_lock = Lock()
        self._locks: dict[str, Lock] = {}
        self._holders: dict[str, str] = {}

    @staticmethod
    def _digest(credential_name: str) -> str:
        normalized = str(credential_name)
        if not normalized or normalized.isspace():
            raise HermesCompanionProtocolError(
                "credential name must not be empty"
            )
        return sha256(normalized.encode("utf-8")).hexdigest()

    @contextmanager
    def acquire(
        self, credential_name: str, *, timeout_seconds: float = 60.0
    ) -> Iterator[str]:
        digest = self._digest(credential_name)
        with self._registry_lock:
            lock = self._locks.setdefault(digest, Lock())
        if not lock.acquire(timeout=float(timeout_seconds)):
            raise HermesConcurrencyError(
                f"credential lock is busy: {digest[:16]}"
            )
        with self._registry_lock:
            self._holders[digest] = _utc_now()
        try:
            yield digest
        finally:
            with self._registry_lock:
                self._holders.pop(digest, None)
            lock.release()

    def held_digests(self) -> dict[str, str]:
        with self._registry_lock:
            return dict(self._holders)


@dataclass(frozen=True)
class ToolLimitRule:
    pattern: str
    max_concurrent: int | None = None
    min_interval_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not str(self.pattern).strip():
            raise HermesCompanionProtocolError(
                "tool limit pattern must not be empty"
            )
        if self.max_concurrent is not None and (
            isinstance(self.max_concurrent, bool)
            or not isinstance(self.max_concurrent, int)
            or self.max_concurrent < 1
        ):
            raise HermesCompanionProtocolError(
                "max_concurrent must be a positive integer"
            )
        if (
            float(self.min_interval_seconds) < 0
            or float(self.min_interval_seconds) > 3600
        ):
            raise HermesCompanionProtocolError(
                "min_interval_seconds must be between 0 and 3600"
            )


class _RuleState:
    def __init__(self, rule: ToolLimitRule) -> None:
        self.rule = rule
        self.condition = Condition()
        self.active = 0
        self.last_started_at: float | None = None


class ToolConcurrencyPolicy:
    """Provider/tool-scoped concurrency and rate limits.

    Each rule matches tool names with a glob pattern and constrains only
    those tools; a tool matching no rule runs without any policy wait, so
    unrelated tools and providers stay fully concurrent.
    """

    def __init__(self, rules: tuple[ToolLimitRule, ...] = ()) -> None:
        self._states = tuple(_RuleState(rule) for rule in rules)

    def _matching_states(self, tool_name: str) -> tuple[_RuleState, ...]:
        return tuple(
            state
            for state in self._states
            if fnmatchcase(str(tool_name), state.rule.pattern)
        )

    @contextmanager
    def acquire(
        self, tool_name: str, *, timeout_seconds: float = 60.0
    ) -> Iterator[None]:
        states = self._matching_states(tool_name)
        acquired: list[_RuleState] = []
        try:
            for state in states:
                self._enter(state, tool_name, timeout_seconds)
                acquired.append(state)
            yield
        finally:
            for state in reversed(acquired):
                with state.condition:
                    state.active -= 1
                    state.condition.notify_all()

    @staticmethod
    def _enter(
        state: _RuleState, tool_name: str, timeout_seconds: float
    ) -> None:
        deadline = monotonic() + float(timeout_seconds)
        with state.condition:
            while True:
                now = monotonic()
                interval = float(state.rule.min_interval_seconds)
                interval_wait = 0.0
                if interval > 0 and state.last_started_at is not None:
                    interval_wait = max(
                        0.0, state.last_started_at + interval - now
                    )
                over_capacity = (
                    state.rule.max_concurrent is not None
                    and state.active >= state.rule.max_concurrent
                )
                if not over_capacity and interval_wait <= 0:
                    state.active += 1
                    state.last_started_at = monotonic()
                    return
                remaining = deadline - now
                if remaining <= 0:
                    raise HermesConcurrencyError(
                        f"tool concurrency limit timed out for "
                        f"{tool_name!r} under pattern "
                        f"{state.rule.pattern!r}"
                    )
                state.condition.wait(
                    timeout=min(
                        remaining,
                        interval_wait if interval_wait > 0 else remaining,
                    )
                )


class ResourceMutationLocks:
    """Resource-scoped serialization for conflicting external mutations.

    Mutations declaring the same resource key run one at a time; distinct
    resources and undeclared (read-only) calls stay concurrent.
    """

    def __init__(self) -> None:
        self._registry_lock = Lock()
        self._locks: dict[str, Lock] = {}

    @contextmanager
    def acquire(
        self, resource_key: str, *, timeout_seconds: float = 60.0
    ) -> Iterator[None]:
        normalized = str(resource_key).strip()
        if not normalized:
            raise HermesCompanionProtocolError(
                "resource_key must not be empty"
            )
        with self._registry_lock:
            lock = self._locks.setdefault(normalized, Lock())
        if not lock.acquire(timeout=float(timeout_seconds)):
            raise HermesConcurrencyError(
                f"resource mutation lock is busy: {normalized}"
            )
        try:
            yield
        finally:
            lock.release()


@dataclass(frozen=True)
class HermesConcurrencyControls:
    administration: HermesAdministrationLock
    credentials: CredentialLockRegistry
    tool_policy: ToolConcurrencyPolicy
    resource_locks: ResourceMutationLocks

    @classmethod
    def from_rules(
        cls, rules: tuple[ToolLimitRule, ...] = ()
    ) -> "HermesConcurrencyControls":
        return cls(
            administration=HermesAdministrationLock(),
            credentials=CredentialLockRegistry(),
            tool_policy=ToolConcurrencyPolicy(rules),
            resource_locks=ResourceMutationLocks(),
        )
