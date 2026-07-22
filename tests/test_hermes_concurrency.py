from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Any

import pytest

from codexbridge.hermes_concurrency import (
    CredentialLockRegistry,
    HermesAdministrationLock,
    HermesConcurrencyControls,
    HermesConcurrencyError,
    ResourceMutationLocks,
    ToolConcurrencyPolicy,
    ToolLimitRule,
)


class Overlap:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    def enter(self) -> None:
        self.active += 1
        self.max_active = max(self.max_active, self.active)

    def leave(self) -> None:
        self.active -= 1


def test_administration_lock_serializes_and_names_holder() -> None:
    lock = HermesAdministrationLock()
    entered = Event()
    proceed = Event()
    observed: dict[str, Any] = {}

    def hold() -> None:
        with lock.acquire("hermes_upgrade"):
            entered.set()
            proceed.wait(3)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(hold)
        assert entered.wait(3)
        observed["holder"] = lock.holder()
        with pytest.raises(
            HermesConcurrencyError, match="hermes_upgrade"
        ):
            with lock.acquire("registry_reload", timeout_seconds=0.05):
                pass
        proceed.set()
        future.result(timeout=5)

    assert observed["holder"]["operation"] == "hermes_upgrade"
    assert lock.holder() is None
    with lock.acquire("registry_reload"):
        assert lock.holder()["operation"] == "registry_reload"


def test_credential_locks_are_specific_and_never_expose_values() -> None:
    registry = CredentialLockRegistry()
    secret_name = "searchconsole-service-account"
    other_name = "cloudflare-api-token"

    with registry.acquire(secret_name) as digest:
        assert secret_name not in digest
        assert digest in registry.held_digests()
        for value in registry.held_digests():
            assert secret_name not in value
            assert other_name not in value
        # A different credential stays acquirable while this one is held.
        with registry.acquire(other_name) as other_digest:
            assert other_digest != digest
        with pytest.raises(HermesConcurrencyError):
            with registry.acquire(secret_name, timeout_seconds=0.05):
                pass
    assert registry.held_digests() == {}


def test_tool_limits_apply_only_to_matching_tools() -> None:
    policy = ToolConcurrencyPolicy(
        (ToolLimitRule(pattern="searchconsole*", max_concurrent=1),)
    )
    limited = Overlap()
    unlimited = Overlap()
    release = Event()

    def run_limited() -> None:
        with policy.acquire("searchconsole_search", timeout_seconds=5):
            limited.enter()
            release.wait(3)
            limited.leave()

    def run_unlimited() -> None:
        with policy.acquire("filesystem_read", timeout_seconds=5):
            unlimited.enter()
            release.wait(3)
            unlimited.leave()

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(run_limited) for _ in range(2)]
        futures += [executor.submit(run_unlimited) for _ in range(3)]
        time.sleep(0.3)
        assert limited.max_active == 1
        assert unlimited.max_active == 3
        release.set()
        for future in futures:
            future.result(timeout=5)

    assert limited.max_active == 1
    assert unlimited.max_active == 3


def test_tool_rate_limit_spaces_started_calls() -> None:
    policy = ToolConcurrencyPolicy(
        (
            ToolLimitRule(
                pattern="rate_limited_tool",
                min_interval_seconds=0.2,
            ),
        )
    )
    started: list[float] = []
    for _ in range(3):
        with policy.acquire("rate_limited_tool", timeout_seconds=5):
            started.append(time.monotonic())
    assert started[1] - started[0] >= 0.19
    assert started[2] - started[1] >= 0.19


def test_resource_mutations_serialize_only_same_resource() -> None:
    locks = ResourceMutationLocks()
    same = Overlap()
    other = Overlap()
    release = Event()

    def mutate(key: str, probe: Overlap) -> None:
        with locks.acquire(key, timeout_seconds=5):
            probe.enter()
            release.wait(3)
            probe.leave()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(mutate, "gsc:property:example.com", same)
            for _ in range(2)
        ]
        futures.append(
            executor.submit(mutate, "gsc:property:other.org", other)
        )
        time.sleep(0.3)
        assert same.max_active == 1
        assert other.max_active == 1
        release.set()
        for future in futures:
            future.result(timeout=5)
    assert same.max_active == 1


def test_controls_bundle_builds_from_rules() -> None:
    controls = HermesConcurrencyControls.from_rules(
        (ToolLimitRule(pattern="x*", max_concurrent=2),)
    )
    assert controls.administration.holder() is None
    assert controls.credentials.held_digests() == {}
    with controls.tool_policy.acquire("x-tool"):
        pass
    with controls.resource_locks.acquire("resource-1"):
        pass
