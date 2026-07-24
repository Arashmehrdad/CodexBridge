import json
from hashlib import sha256
from types import SimpleNamespace

from pydantic import TypeAdapter, ValidationError
import pytest

from soma.gateway_models import (
    RepoApplyRequest,
    RepoCommitRequest,
    RepoPreviewRequest,
    RepoQueryRequest,
    RunStartRequest,
    DockerActionRequest,
    DockerQueryRequest,
    CloudflareActionRequest,
    CloudflareQueryRequest,
    SSHActionRequest,
    SSHQueryRequest,
    SystemActionRequest,
    SystemQueryRequest,
    KnowledgeActionRequest,
    KnowledgeQueryRequest,
    RunQueryRequest,
    SSHEnvironmentProbe,
    SSHInspectRequest,
    SSHAdministrationAction,
    SSHCommandAction,
    SSHExecutionPolicyGatewayRequest,
    SSHReviewedScriptAction,
    SSHRootShellAction,
    MAX_REVIEWED_SSH_SCRIPT_BYTES,
    MAX_REVIEWED_SSH_SCRIPT_ARGS,
    MAX_REVIEWED_SSH_SCRIPT_ARG_BYTES,
    MAX_REVIEWED_SSH_SCRIPT_ARGS_BYTES,
    SupervisorActionRequest,
    SupervisorQueryRequest,
    TradingQueryRequest,
    TradingSignalCancelRequest,
    TradingSignalGetRequest,
    TradingSignalListRequest,
    TradingSignalSubmitRequest,
    WorkflowActionRequest,
    WorkflowQueryRequest,
)
import soma.server as server


def _assert_compact_envelope(result: dict) -> None:
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]


def test_ssh_inspection_models_are_discriminated_and_strict() -> None:
    adapter = TypeAdapter(SSHInspectRequest)
    assert adapter.validate_python({"operation": "host_health", "host_id": "dev"}).host_id == "dev"
    inspection = adapter.validate_python(
        {"operation": "inspection", "host_id": "dev", "inspection": "uptime"}
    )
    assert inspection.view == "compact"
    assert adapter.validate_python(
        {
            "operation": "inspection",
            "host_id": "dev",
            "inspection": "uptime",
            "view": "full",
        }
    ).view == "full"
    try:
        adapter.validate_python({"operation": "gpu_telemetry", "host_id": "dev", "tail": 10})
    except ValidationError:
        pass
    else:
        raise AssertionError("cross-operation field must be rejected")


def test_gateway_model_requires_operation_specific_fields() -> None:
    adapter = TypeAdapter(RunQueryRequest)
    events = adapter.validate_python({"operation": "events", "run_id": "run_1"})
    assert events.limit == 20
    assert events.cursor == ""
    assert adapter.validate_python(
        {"operation": "group_status", "group_id": "group_1"}
    ).group_id == "group_1"
    assert adapter.validate_python(
        {"operation": "group_result", "group_id": "group_1"}
    ).group_id == "group_1"
    locks = adapter.validate_python(
        {
            "operation": "locks",
            "limit": 7,
            "view": "full",
            "response_budget_bytes": 16384,
        }
    )
    assert locks.limit == 7
    assert locks.view == "full"
    assert locks.response_budget_bytes == 16384
    for payload in (
        {"operation": "events"},
        {"operation": "events", "run_id": "run_1", "stream": "stdout"},
        {
            "operation": "events",
            "run_id": "run_1",
            "after_id": 1,
            "cursor": "opaque",
        },
        {"operation": "group_status", "run_id": "run_1"},
        {"operation": "group_result", "group_id": "group_1", "limit": 1},
    ):
        try:
            adapter.validate_python(payload)
        except ValidationError:
            continue
        raise AssertionError("invalid payload was accepted")


def test_ssh_gateway_matches_internal_environment_probe(monkeypatch) -> None:
    monkeypatch.setattr(server, "ssh_environment_probe", lambda host_id: {"host_id": host_id, "ok": True})
    result = server.ssh_inspect(SSHEnvironmentProbe(operation="environment_probe", host_id="dev"))
    assert result["host_id"] == "dev"


def test_ssh_bounded_inspection_full_view_preserves_evidence(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_config", lambda: object())
    monkeypatch.setattr(
        server,
        "_run_ssh_inspection",
        lambda *args, **kwargs: {
            "ok": True,
            "stdout": "x" * 50_000,
            "stderr": "",
            "argv": ["inspect"],
        },
    )
    result = server.ssh_inspect(
        TypeAdapter(SSHInspectRequest).validate_python(
            {
                "operation": "inspection",
                "host_id": "dev",
                "inspection": "uptime",
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )
    assert len(result["stdout"]) == 50_000
    assert "truncated" not in result

    compact = server.ssh_inspect(
        TypeAdapter(SSHInspectRequest).validate_python(
            {
                "operation": "inspection",
                "host_id": "dev",
                "inspection": "uptime",
                "response_budget_bytes": 4096,
            }
        )
    )
    _assert_compact_envelope(compact)
    assert compact["response_bytes"] <= 4096


def test_ssh_health_projection_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "ssh_host_health",
        lambda host_id: {
            "host_id": host_id,
            "ok": True,
            "status": "healthy",
            "interfaces": [{"name": f"eth{index}"} for index in range(5000)],
            "diagnostic": "x" * 20_000,
        },
    )
    result = server.ssh_inspect(
        TypeAdapter(SSHInspectRequest).validate_python(
            {"operation": "host_health", "host_id": "dev", "response_budget_bytes": 4096}
        )
    )
    assert result["interfaces_count"] == 5000
    assert result["truncated"] is True
    assert result["response_bytes"] <= 4096


def test_ssh_profile_apply_projection_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "apply_ssh_profile_change",
        lambda change_id: {
            "ok": True,
            "change_id": change_id,
            "status": "applied",
            "activation": {
                "ok": True,
                "modules": [f"module_{index}" for index in range(5000)],
                "message": "x" * 20_000,
            },
        },
    )
    result = server.ssh_action(
        TypeAdapter(SSHActionRequest).validate_python(
            {"action": "profile_apply", "change_id": "change_1", "response_budget_bytes": 4096}
        )
    )
    assert result["change_id"] == "change_1"
    assert result["truncated"] is True
    assert result["response_bytes"] <= 4096
    full = server.ssh_action(
        TypeAdapter(SSHActionRequest).validate_python(
            {"action": "profile_apply", "change_id": "change_1", "view": "full"}
        )
    )
    assert len(full["activation"]["modules"]) == 5000


def test_trading_query_models_are_strict_and_require_aware_ranges() -> None:
    adapter = TypeAdapter(TradingQueryRequest)
    h4 = adapter.validate_python({"operation": "h4_candles"})
    assert h4.completed_count == 200
    assert h4.view == "compact"
    assert h4.response_budget_bytes == 12 * 1024
    symbols = adapter.validate_python({"operation": "symbols"})
    assert symbols.view == "compact"
    assert symbols.response_budget_bytes == 12 * 1024
    assert adapter.validate_python({"operation": "health"}).response_budget_bytes == 12 * 1024
    assert adapter.validate_python({"operation": "specification"}).response_budget_bytes == 12 * 1024
    assert adapter.validate_python({"operation": "tick"}).response_budget_bytes == 12 * 1024
    historical = adapter.validate_python({"operation": "historical_ticks", "start_utc": "2026-07-20T06:00:00+00:00", "end_utc": "2026-07-20T07:00:00+00:00"})
    assert historical.end_utc.hour == 7
    assert historical.view == "compact"
    assert historical.response_budget_bytes == 12 * 1024
    with pytest.raises(ValidationError):
        adapter.validate_python({"operation": "tick", "completed_count": 1})
    with pytest.raises(ValidationError):
        adapter.validate_python({"operation": "historical_ticks", "start_utc": "2026-07-20T08:00:00", "end_utc": "2026-07-20T07:00:00"})


def test_trading_query_dispatches_configured_demo_adapter(monkeypatch) -> None:
    calls = []

    class FakeProvider:
        def connect(self):
            return SimpleNamespace(connected=True, account_environment="demo")

        def close(self):
            calls.append("close")

        def latest_tick(self, symbol):
            calls.append(("tick", symbol))
            return {"symbol": symbol, "bid": 1.0, "ask": 2.0}

    monkeypatch.setattr(server, "get_config", lambda: SimpleNamespace(trading=SimpleNamespace(enabled=True, symbol="BITCOIN_i", terminal_path="", provider_utc_offset_seconds=10_800, maximum_tick_age_seconds=120)))
    monkeypatch.setattr(server, "_configured_mt5_provider", FakeProvider)
    request = TypeAdapter(TradingQueryRequest).validate_python({"operation": "tick"})
    result = server.trading_query(request)
    assert result["ok"] is True
    assert result["symbol"] == "BITCOIN_i"
    assert result["result"]["ask"] == 2.0
    assert calls == [("tick", "BITCOIN_i"), "close"]


def test_trading_scalar_query_projection_honors_response_budget(monkeypatch) -> None:
    class FakeProvider:
        def connect(self):
            return SimpleNamespace(connected=True, account_environment="demo")

        def close(self):
            pass

        def latest_tick(self, symbol):
            return {"symbol": symbol, "bid": 1.0, "ask": 2.0, "detail": "x" * 20_000}

    monkeypatch.setattr(server, "get_config", lambda: SimpleNamespace(trading=SimpleNamespace(enabled=True, symbol="BITCOIN_i")))
    monkeypatch.setattr(server, "_configured_mt5_provider", FakeProvider)
    result = server.trading_query(
        TypeAdapter(TradingQueryRequest).validate_python(
            {"operation": "tick", "response_budget_bytes": 4096}
        )
    )
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096


def test_run_query_group_projection_honors_response_budget(monkeypatch) -> None:
    class FakeJobs:
        def get_powershell_group(self, group_id: str) -> dict:
            return {
                "group_id": group_id,
                "repo_name": "soma",
                "status": "running",
                "mode": "powershell",
                "failure_policy": "continue_all",
                "repository_lock_policy": "none",
                "requested_concurrency": 4,
                "created_at": "2026-07-22T00:00:00Z",
                "children": [
                    {
                        "position": index,
                        "run_id": f"run_{index}",
                        "status": "completed",
                        "current_phase": "terminal",
                        "summary": "x" * 800,
                        "error": "e" * 800,
                        "exit_code": 0,
                        "started_at": "2026-07-22T00:00:00Z",
                        "ended_at": "2026-07-22T00:00:01Z",
                        "artifacts": {"stdout": "protected"},
                    }
                    for index in range(20)
                ],
            }

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())
    request = TypeAdapter(RunQueryRequest).validate_python(
        {"operation": "group_status", "group_id": "group_1", "response_budget_bytes": 4096}
    )
    result = server.run_query(request)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096
    assert "artifacts" not in result["children"][0]


def test_trading_symbols_query_honors_response_budget(monkeypatch) -> None:
    class FakeProvider:
        def connect(self):
            return SimpleNamespace(connected=True, account_environment="demo")

        def close(self):
            pass

        def list_symbols(self, query):
            return [f"SYMBOL_{index}_" + "x" * 120 for index in range(100)]

    monkeypatch.setattr(server, "get_config", lambda: SimpleNamespace(trading=SimpleNamespace(enabled=True, symbol="BITCOIN_i")))
    monkeypatch.setattr(server, "_configured_mt5_provider", FakeProvider)
    request = TypeAdapter(TradingQueryRequest).validate_python(
        {"operation": "symbols", "response_budget_bytes": 4096}
    )
    result = server.trading_query(request)
    _assert_compact_envelope(result)
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096


def test_trading_h4_query_honors_response_budget(monkeypatch) -> None:
    class FakeProvider:
        def connect(self):
            return SimpleNamespace(connected=True, account_environment="demo")

        def close(self):
            pass

        def h4_candles(self, symbol, completed_count):
            return ([{"time": index, "close": "x" * 160} for index in range(completed_count)], {"close": "y" * 200})

    monkeypatch.setattr(server, "get_config", lambda: SimpleNamespace(trading=SimpleNamespace(enabled=True, symbol="BITCOIN_i")))
    monkeypatch.setattr(server, "_configured_mt5_provider", FakeProvider)
    request = TypeAdapter(TradingQueryRequest).validate_python(
        {"operation": "h4_candles", "completed_count": 100, "response_budget_bytes": 4096}
    )
    result = server.trading_query(request)
    _assert_compact_envelope(result)
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096


def test_trading_historical_ticks_honors_response_budget(monkeypatch) -> None:
    class FakeProvider:
        def connect(self):
            return SimpleNamespace(connected=True, account_environment="demo")

        def close(self):
            pass

        def historical_ticks(self, symbol, start_utc, end_utc):
            return [{"time": index, "bid": "x" * 160} for index in range(100)]

    monkeypatch.setattr(server, "get_config", lambda: SimpleNamespace(trading=SimpleNamespace(enabled=True, symbol="BITCOIN_i")))
    monkeypatch.setattr(server, "_configured_mt5_provider", FakeProvider)
    request = TypeAdapter(TradingQueryRequest).validate_python(
        {
            "operation": "historical_ticks",
            "start_utc": "2026-07-20T06:00:00+00:00",
            "end_utc": "2026-07-20T07:00:00+00:00",
            "response_budget_bytes": 4096,
        }
    )
    result = server.trading_query(request)
    _assert_compact_envelope(result)
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096


def test_trading_collection_full_views_preserve_authoritative_payloads(
    monkeypatch,
) -> None:
    class FakeProvider:
        def connect(self):
            return SimpleNamespace(connected=True, account_environment="demo")

        def close(self):
            pass

        def list_symbols(self, query):
            return [f"SYMBOL_{index}_" + "x" * 120 for index in range(100)]

        def h4_candles(self, symbol, completed_count):
            return (
                [{"time": index, "close": "x" * 160} for index in range(completed_count)],
                {"close": "y" * 200},
            )

        def historical_ticks(self, symbol, start_utc, end_utc):
            return [{"time": index, "bid": "x" * 160} for index in range(100)]

    monkeypatch.setattr(
        server,
        "get_config",
        lambda: SimpleNamespace(
            trading=SimpleNamespace(enabled=True, symbol="BITCOIN_i")
        ),
    )
    monkeypatch.setattr(server, "_configured_mt5_provider", FakeProvider)

    symbols = server.trading_query(
        TypeAdapter(TradingQueryRequest).validate_python(
            {
                "operation": "symbols",
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )
    assert len(symbols["result"]) == 100
    assert "truncated" not in symbols

    candles = server.trading_query(
        TypeAdapter(TradingQueryRequest).validate_python(
            {
                "operation": "h4_candles",
                "completed_count": 100,
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )
    assert len(candles["result"]["completed"]) == 100
    assert len(candles["result"]["developing"]["close"]) == 200
    assert "truncated" not in candles

    ticks = server.trading_query(
        TypeAdapter(TradingQueryRequest).validate_python(
            {
                "operation": "historical_ticks",
                "start_utc": "2026-07-20T06:00:00+00:00",
                "end_utc": "2026-07-20T07:00:00+00:00",
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )
    assert len(ticks["result"]) == 100
    assert "truncated" not in ticks


class _FakeTradingLab:
    """A stand-in for the trading_lab services container.

    Only the signal surface the gateway calls is implemented; the point of
    these tests is Soma's response shaping, not domain behavior.
    """

    def __init__(self, count: int = 10) -> None:
        self._count = count

    def signal_list(self, *, limit, offset, status=None, experiment_id=None):
        from trading_lab.service import SignalPage

        remaining = max(0, self._count - offset)
        return SignalPage(
            signals=tuple(object() for _ in range(min(limit, remaining))),
            total=self._count,
            offset=offset,
        )

    def signal_get(self, signal_id):
        return object()

    def signal_submit(self, idempotency_key, submission):
        return object()

    def signal_cancel_before_entry(self, signal_id, reason):
        return object()


def test_trading_signal_list_full_view_preserves_records(monkeypatch) -> None:
    monkeypatch.setattr(
        server, "_trading_services", lambda: _FakeTradingLab()
    )
    monkeypatch.setattr(
        server,
        "_signal_record_json",
        lambda record: {"signal_id": "sig", "detail": "x" * 4000},
    )
    result = server.trading_signal_list(
        TradingSignalListRequest(limit=10, view="full", response_budget_bytes=1024)
    )
    assert len(result["signals"]) == 10
    assert result["total"] == 10
    assert len(result["signals"][0]["detail"]) == 4000
    assert "truncated" not in result

    compact = server.trading_signal_list(
        TradingSignalListRequest(limit=10, response_budget_bytes=4096)
    )
    _assert_compact_envelope(compact)
    assert compact["response_bytes"] <= 4096


def _signal_request_payload() -> dict:
    return {
        "idempotency_key": "signal-gateway-1",
        "packet_id": "mp_" + "a" * 24,
        "decision": "LONG",
        "confidence": 73,
        "stop_loss": 63500.0,
        "take_profit": 65192.0,
        "reason": "Defined continuation setup.",
        "news_context": "",
        "model_version": "gpt-test-1",
        "prompt_version": "prompt-v1",
        "policy_id": "hourly_fixed_bracket_v1",
        "execution_mode": "internal_paper",
        "experiment_id": "exp1",
    }


def test_trading_signal_models_are_strict() -> None:
    submit = TypeAdapter(TradingSignalSubmitRequest)
    request = submit.validate_python(_signal_request_payload())
    assert request.confidence == 73
    assert request.response_budget_bytes == 12 * 1024
    assert request.policy_id == "hourly_fixed_bracket_v1"
    signal_get = TypeAdapter(TradingSignalGetRequest).validate_python({"signal_id": "sig_1"})
    assert signal_get.signal_id == "sig_1"
    assert signal_get.response_budget_bytes == 12 * 1024
    signal_list = TypeAdapter(TradingSignalListRequest).validate_python({})
    assert signal_list.limit == 100
    assert signal_list.offset == 0
    assert signal_list.response_budget_bytes == 12 * 1024
    cancel = TypeAdapter(TradingSignalCancelRequest).validate_python({"signal_id": "sig_1", "reason": "wrong premise"})
    assert cancel.reason == "wrong premise"
    assert cancel.response_budget_bytes == 12 * 1024
    # Live execution and caller-supplied market facts cannot be expressed.
    with pytest.raises(ValidationError):
        submit.validate_python({**_signal_request_payload(), "execution_mode": "live"})
    with pytest.raises(ValidationError):
        submit.validate_python({**_signal_request_payload(), "bid": 64_000.0})
    with pytest.raises(ValidationError):
        submit.validate_python({**_signal_request_payload(), "confidence": 49})


def _enable_trading(monkeypatch, tmp_path) -> None:
    """Enable trading against isolated state.

    A real ``AppConfig`` is used rather than a namespace double: the
    Trading Lab adapter maps configuration onto the package's settings, so
    it needs the genuine ``resolve_runs_dir`` and ``TradingConfig``.
    """
    from soma import trading_lab_adapter
    from soma.config import AppConfig, RepoConfig

    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    (repo / ".git").mkdir(exist_ok=True)
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(repo))},
        runs_dir=str(tmp_path / "runs"),
        trading={"enabled": True, "symbol": "BITCOIN_i"},
        config_dir=tmp_path,
    )
    monkeypatch.setattr(server, "get_config", lambda: config)
    # The services cache is keyed by settings, so a fresh temp root already
    # yields a fresh container; clearing keeps the cache from growing across
    # the suite and guarantees isolation if a root is ever reused.
    trading_lab_adapter.reset_services_cache()


def test_trading_signal_gateways_share_repository_owned_journal(
    tmp_path, monkeypatch
) -> None:
    from datetime import datetime, timezone

    from trading_lab.market_packet import MarketPacketBuilder

    from tests.test_trading_lab_gateway import SYMBOL, FakeProvider

    _enable_trading(monkeypatch, tmp_path)
    now = datetime.now(timezone.utc)
    built = MarketPacketBuilder(now=lambda: now).build(
        FakeProvider(now=now), SYMBOL, completed_count=100
    )
    packet = server._trading_services().packet_store().store(built)

    payload = {**_signal_request_payload(), "packet_id": packet.packet_id}
    submit = TypeAdapter(TradingSignalSubmitRequest).validate_python(payload)
    first = server.trading_signal_submit(submit)
    replay = server.trading_signal_submit(submit)
    signal_id = first["signal"]["signal_id"]
    assert first == replay
    assert first["signal"]["packet_hash"] == packet.content_hash
    assert first["signal"]["bid"] == packet.bid
    assert server.trading_signal_get(TradingSignalGetRequest(signal_id=signal_id))["signal"] == first["signal"]
    assert server.trading_signal_list(TradingSignalListRequest())["signals"] == [first["signal"]]
    cancelled = server.trading_signal_cancel_before_entry(
        TradingSignalCancelRequest(signal_id=signal_id, reason="wrong premise")
    )
    assert cancelled["signal"]["status"] == "cancelled"
    assert cancelled["signal"]["content_hash"] == first["signal"]["content_hash"]

    # An unknown packet is rejected with a durable record, not accepted.
    rejected = server.trading_signal_submit(
        TypeAdapter(TradingSignalSubmitRequest).validate_python(
            {
                **_signal_request_payload(),
                "idempotency_key": "signal-gateway-2",
                "packet_id": "mp_" + "b" * 24,
            }
        )
    )
    assert rejected["ok"] is False
    assert rejected["status"] == "rejected"
    assert "stored market packet" in rejected["rejection"]["rejection_reason"]


def test_trading_signal_get_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        server, "_trading_services", lambda: _FakeTradingLab()
    )
    monkeypatch.setattr(
        server,
        "_signal_record_json",
        lambda record: {
            "signal_id": "sig_1",
            "reason": "r" * 4000,
            "news_context": "n" * 4000,
        },
    )
    result = server.trading_signal_get(
        TradingSignalGetRequest(signal_id="sig_1", response_budget_bytes=1024)
    )
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 1024


def test_trading_signal_submit_honors_response_budget(monkeypatch, tmp_path) -> None:
    _enable_trading(monkeypatch, tmp_path)
    monkeypatch.setattr(
        server, "_trading_services", lambda: _FakeTradingLab()
    )
    monkeypatch.setattr(
        server,
        "_signal_record_json",
        lambda record: {
            "signal_id": "sig_1",
            "reason": "r" * 4000,
            "news_context": "n" * 4000,
        },
    )
    payload = _signal_request_payload()
    payload["response_budget_bytes"] = 1024
    result = server.trading_signal_submit(
        TypeAdapter(TradingSignalSubmitRequest).validate_python(payload)
    )
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 1024


def test_trading_signal_cancel_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        server, "_trading_services", lambda: _FakeTradingLab()
    )
    monkeypatch.setattr(
        server,
        "_signal_record_json",
        lambda record: {
            "signal_id": "sig_1",
            "reason": "r" * 4000,
            "news_context": "n" * 4000,
            "status": "cancelled",
        },
    )
    result = server.trading_signal_cancel_before_entry(
        TradingSignalCancelRequest(
            signal_id="sig_1", reason="wrong premise", response_budget_bytes=1024
        )
    )
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 1024


def test_trading_deprecated_portfolio_operations_return_pointer(monkeypatch, tmp_path) -> None:
    _enable_trading(monkeypatch, tmp_path)
    for operation in ("open_virtual_positions", "portfolio_status", "threshold_report"):
        result = server.trading_query(
            TypeAdapter(TradingQueryRequest).validate_python(
                {"operation": operation}
            )
        )
        assert result["ok"] is False
        assert result["status"] == "deprecated"
        assert "replay_report" in result["error"]


def test_workflow_and_supervisor_models_are_operation_specific() -> None:
    workflow_query = TypeAdapter(WorkflowQueryRequest)
    workflow_action = TypeAdapter(WorkflowActionRequest)
    supervisor_query = TypeAdapter(SupervisorQueryRequest)
    supervisor_action = TypeAdapter(SupervisorActionRequest)

    workflow_events = workflow_query.validate_python({"operation": "events", "workflow_id": "wf_1"})
    assert workflow_events.limit == 100
    assert workflow_events.view == "compact"
    assert workflow_events.response_budget_bytes == 12 * 1024
    assert workflow_query.validate_python(
        {"operation": "events", "workflow_id": "wf_1", "view": "full"}
    ).view == "full"
    assert workflow_query.validate_python(
        {"operation": "status", "workflow_id": "wf_1"}
    ).response_budget_bytes == 12 * 1024
    assert workflow_query.validate_python(
        {"operation": "result", "workflow_id": "wf_1"}
    ).response_budget_bytes == 12 * 1024
    assert workflow_action.validate_python(
        {"action": "start", "repo_name": "repo", "objective": "ship", "steps": [{"id": "one"}]}
    ).repo_name == "repo"
    assert workflow_action.validate_python(
        {"action": "cancel", "workflow_id": "wf_1"}
    ).response_budget_bytes == 12 * 1024
    assert supervisor_query.validate_python(
        {"operation": "notifications", "supervisor_id": "sup_1"}
    ).response_budget_bytes == 12 * 1024
    assert supervisor_query.validate_python(
        {"operation": "notifications", "supervisor_id": "sup_1", "view": "full"}
    ).view == "full"
    assert supervisor_query.validate_python(
        {"operation": "events", "supervisor_id": "sup_1", "view": "full"}
    ).view == "full"
    assert supervisor_query.validate_python(
        {"operation": "status", "supervisor_id": "sup_1"}
    ).response_budget_bytes == 12 * 1024
    assert supervisor_query.validate_python(
        {"operation": "result", "supervisor_id": "sup_1"}
    ).response_budget_bytes == 12 * 1024
    assert supervisor_query.validate_python(
        {"operation": "resume_prompt", "supervisor_id": "sup_1"}
    ).response_budget_bytes == 12 * 1024
    assert supervisor_action.validate_python(
        {"action": "pause", "supervisor_id": "sup_1"}
    ).supervisor_id == "sup_1"
    assert supervisor_action.validate_python(
        {"action": "cancel", "supervisor_id": "sup_1"}
    ).response_budget_bytes == 12 * 1024
    invalid_payloads = (
        (workflow_query, {"operation": "status", "workflow_id": "wf_1", "limit": 1}),
        (workflow_action, {"action": "cancel"}),
        (supervisor_query, {"operation": "resume_prompt", "supervisor_id": "sup_1", "limit": 1}),
        (supervisor_action, {"action": "resume", "supervisor_id": "sup_1", "task": "wrong"}),
    )
    for adapter, payload in invalid_payloads:
        try:
            adapter.validate_python(payload)
        except ValidationError:
            continue
        raise AssertionError(f"invalid payload was accepted: {payload}")


def test_workflow_and_supervisor_event_full_views_preserve_evidence(
    monkeypatch,
) -> None:
    class WorkflowManager:
        def get_events(self, workflow_id, limit):
            return [
                {"id": index, "message": "w" * 1000}
                for index in range(limit)
            ]

    class SupervisorService:
        def get_events(self, supervisor_id, limit):
            return [
                {"id": index, "message": "s" * 1000}
                for index in range(limit)
            ]

    monkeypatch.setattr(server, "get_workflow_manager", lambda: WorkflowManager())
    workflow = server.workflow_query(
        TypeAdapter(WorkflowQueryRequest).validate_python(
            {
                "operation": "events",
                "workflow_id": "wf_1",
                "limit": 20,
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )
    assert len(workflow["events"]) == 20
    assert len(workflow["events"][0]["message"]) == 1000
    assert "truncated" not in workflow
    workflow_compact = server.workflow_query(
        TypeAdapter(WorkflowQueryRequest).validate_python(
            {
                "operation": "events",
                "workflow_id": "wf_1",
                "limit": 20,
                "response_budget_bytes": 4096,
            }
        )
    )
    _assert_compact_envelope(workflow_compact)
    assert workflow_compact["response_bytes"] <= 4096

    monkeypatch.setattr(server, "get_supervisor_service", lambda: SupervisorService())
    supervisor = server.supervisor_query(
        TypeAdapter(SupervisorQueryRequest).validate_python(
            {
                "operation": "events",
                "supervisor_id": "sup_1",
                "limit": 20,
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )
    assert len(supervisor["events"]) == 20
    assert len(supervisor["events"][0]["message"]) == 1000
    assert "truncated" not in supervisor
    supervisor_compact = server.supervisor_query(
        TypeAdapter(SupervisorQueryRequest).validate_python(
            {
                "operation": "events",
                "supervisor_id": "sup_1",
                "limit": 20,
                "response_budget_bytes": 4096,
            }
        )
    )
    _assert_compact_envelope(supervisor_compact)
    assert supervisor_compact["response_bytes"] <= 4096


def test_supervisor_notifications_full_view_preserves_evidence(monkeypatch) -> None:
    class FakeService:
        def get_notifications(self, supervisor_id, delivery_status, limit):
            return [{"id": index, "message": "x" * 1000} for index in range(limit)]

    monkeypatch.setattr(server, "get_supervisor_service", lambda: FakeService())
    result = server.supervisor_query(
        TypeAdapter(SupervisorQueryRequest).validate_python(
            {"operation": "notifications", "supervisor_id": "sup_1", "view": "full", "limit": 3}
        )
    )
    assert len(result["notifications"]) == 3
    assert len(result["notifications"][0]["message"]) == 1000
    compact = server.supervisor_query(
        TypeAdapter(SupervisorQueryRequest).validate_python(
            {
                "operation": "notifications",
                "supervisor_id": "sup_1",
                "limit": 3,
                "response_budget_bytes": 4096,
            }
        )
    )
    _assert_compact_envelope(compact)
    assert compact["response_bytes"] <= 4096


def test_workflow_and_supervisor_gateways_dispatch_to_existing_implementations(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_workflow_status", lambda workflow_id: {"workflow_id": workflow_id, "ok": True})
    monkeypatch.setattr(server, "cancel_workflow", lambda workflow_id: {"workflow_id": workflow_id, "status": "cancelled"})
    monkeypatch.setattr(server, "get_supervisor_resume_prompt", lambda supervisor_id: {"supervisor_id": supervisor_id, "ok": True})
    monkeypatch.setattr(server, "pause_supervisor", lambda supervisor_id: {"supervisor_id": supervisor_id, "status": "paused"})

    workflow_result = server.workflow_query(
        TypeAdapter(WorkflowQueryRequest).validate_python(
            {"operation": "status", "workflow_id": "wf_1"}
        )
    )
    assert workflow_result["workflow_id"] == "wf_1"
    assert workflow_result["ok"] is True
    assert server.workflow_action(
        TypeAdapter(WorkflowActionRequest).validate_python(
            {"action": "cancel", "workflow_id": "wf_1"}
        )
    )["status"] == "cancelled"
    assert server.supervisor_query(
        TypeAdapter(SupervisorQueryRequest).validate_python(
            {"operation": "resume_prompt", "supervisor_id": "sup_1"}
        )
    )["supervisor_id"] == "sup_1"
    assert server.supervisor_action(
        TypeAdapter(SupervisorActionRequest).validate_python(
            {"action": "pause", "supervisor_id": "sup_1"}
        )
    )["status"] == "paused"


def test_supervisor_lifecycle_projection_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "pause_supervisor",
        lambda supervisor_id: {
            "ok": True,
            "supervisor_id": supervisor_id,
            "status": "paused",
            "summary": "s" * 20_000,
            "failure_summary": "f" * 20_000,
            "recommended_next_action": "n" * 20_000,
            "run_links": [{"run_id": str(index)} for index in range(5000)],
        },
    )
    request = TypeAdapter(SupervisorActionRequest).validate_python(
        {"action": "pause", "supervisor_id": "sup_1", "response_budget_bytes": 4096}
    )
    result = server.supervisor_action(request)
    assert result["response_bytes"] <= 4096
    assert result["supervisor_id"] == "sup_1"
    assert result["run_link_count"] == 5000


def test_workflow_query_projection_honors_response_budget(monkeypatch) -> None:
    class Manager:
        def get_status(self, workflow_id):
            return {
                "ok": True,
                "workflow_id": workflow_id,
                "repo_name": "soma",
                "status": "running",
                "terminal_status": "",
                "created_at": "2026-07-22T00:00:00Z",
                "steps": [
                    {
                        "id": str(index),
                        "type": "powershell",
                        "status": "completed",
                        "depends_on": [],
                        "child_run_id": f"run_{index}",
                        "summary": "s" * 900,
                        "error": "e" * 900,
                    }
                    for index in range(20)
                ],
            }

    monkeypatch.setattr(server, "get_workflow_manager", lambda: Manager())
    request = TypeAdapter(WorkflowQueryRequest).validate_python(
        {"operation": "status", "workflow_id": "wf_1", "response_budget_bytes": 4096}
    )
    result = server.workflow_query(request)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096


def test_supervisor_resume_prompt_honors_response_budget(monkeypatch) -> None:
    class Service:
        def get_resume_prompt(self, supervisor_id):
            return {
                "supervisor_id": supervisor_id,
                "exists": True,
                "path": "protected/resume_prompt.txt",
                "content": "resume " + "x" * 20_000,
            }

    monkeypatch.setattr(server, "get_supervisor_service", lambda: Service())
    request = TypeAdapter(SupervisorQueryRequest).validate_python(
        {
            "operation": "resume_prompt",
            "supervisor_id": "sup_1",
            "response_budget_bytes": 4096,
        }
    )
    result = server.supervisor_query(request)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096
    assert "path" not in result


def test_supervisor_snapshot_projection_honors_response_budget(monkeypatch) -> None:
    snapshot = {
        "ok": True,
        "supervisor_id": "sup_1",
        "repo_name": "repo",
        "status": "completed",
        "summary": "s" * 20_000,
        "failure_summary": "f" * 20_000,
        "recommended_next_action": "n" * 20_000,
        "run_links": [{"run_id": str(index)} for index in range(100)],
        "plan_result": {"content": "x" * 20_000},
        "implementation_result": {"content": "y" * 20_000},
    }
    monkeypatch.setattr(server, "get_supervisor_status", lambda supervisor_id: snapshot)
    request = TypeAdapter(SupervisorQueryRequest).validate_python(
        {"operation": "status", "supervisor_id": "sup_1", "response_budget_bytes": 4096}
    )
    result = server.supervisor_query(request)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["response_bytes"] <= 4096
    assert result["run_link_count"] == 100
    assert "plan_result" not in result


def test_repo_gateway_models_are_discriminated_and_strict() -> None:
    adapters = {
        "query": TypeAdapter(RepoQueryRequest),
        "preview": TypeAdapter(RepoPreviewRequest),
        "apply": TypeAdapter(RepoApplyRequest),
        "commit": TypeAdapter(RepoCommitRequest),
    }
    assert adapters["query"].validate_python(
        {"operation": "search_text", "repo_name": "repo", "query": "needle"}
    ).query == "needle"
    output_query = TypeAdapter(RunQueryRequest).validate_python(
        {"operation": "output", "run_id": "run_1"}
    )
    assert output_query.view == "compact"
    assert output_query.response_budget_bytes == 12 * 1024
    preflight_query = TypeAdapter(RunQueryRequest).validate_python(
        {"operation": "preflight", "repo_name": "repo"}
    )
    assert preflight_query.include_stale is False
    diff_query = adapters["query"].validate_python(
        {"operation": "diff", "repo_name": "repo"}
    )
    assert diff_query.view == "summary"
    with pytest.raises(ValidationError):
        adapters["query"].validate_python(
            {"operation": "diff", "repo_name": "repo", "view": "full"}
        )
    read_query = adapters["query"].validate_python(
        {"operation": "read_files", "repo_name": "repo", "requests": [{"path": "x.py"}]}
    )
    assert read_query.response_budget_bytes == 48 * 1024
    with pytest.raises(ValidationError):
        adapters["query"].validate_python(
            {
                "operation": "read_files",
                "repo_name": "repo",
                "requests": [{"path": "x.py"}],
                "response_budget_bytes": 48 * 1024 - 1,
            }
        )
    assert adapters["preview"].validate_python(
        {"operation": "remove_file", "repo_name": "repo", "path": "x.py", "expected_sha256": "a" * 64}
    ).path == "x.py"
    assert adapters["apply"].validate_python(
        {"operation": "previewed_change", "repo_name": "repo", "patch_id": "patch_1"}
    ).patch_id == "patch_1"
    assert adapters["commit"].validate_python(
        {"operation": "commit_selected", "repo_name": "repo", "files": ["x.py"], "title": "fix: x"}
    ).title == "fix: x"

    invalid = (
        (adapters["query"], {"operation": "status", "repo_name": "repo", "path": "x.py"}),
        (adapters["preview"], {"operation": "create_file", "repo_name": "repo", "path": "x.py"}),
        (adapters["apply"], {"operation": "move_file", "repo_name": "repo", "source_path": "a", "destination_path": "b"}),
        (adapters["commit"], {"operation": "create_branch", "repo_name": "repo", "branch_name": "x", "files": ["x.py"]}),
    )
    for adapter, payload in invalid:
        with pytest.raises(ValidationError):
            adapter.validate_python(payload)


def test_repo_gateways_dispatch_to_existing_safe_wrappers(monkeypatch) -> None:
    class FakeJobs:
        def start_repo_apply(self, repo_name, operation, payload):
            assert (repo_name, operation, payload) == (
                "repo",
                "previewed_change",
                {"patch_id": "patch_1"},
            )
            return {
                "accepted": True,
                "status": "queued",
                "run_id": "run_apply_1",
                "repo_name": "repo",
            }

    monkeypatch.setattr(server, "_repo_context", lambda _repo_name: None)
    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())
    monkeypatch.setattr(server, "search_repo_text", lambda *args: {"operation": "search", "args": args})
    monkeypatch.setattr(server, "read_repo_files", lambda *args: {"operation": "read", "args": args})
    monkeypatch.setattr(server, "preview_repo_file_removal", lambda *args: {"operation": "remove", "args": args})
    monkeypatch.setattr(server, "apply_previewed_repo_change", lambda *args: {"operation": "apply", "args": args})
    monkeypatch.setattr(server, "commit_selected_files", lambda *args: {"operation": "commit", "args": args})

    assert server.repo_query(TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "search_text", "repo_name": "repo", "query": "needle"}
    ))["operation"] == "search"
    read_result = server.repo_query(TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "read_files", "repo_name": "repo", "requests": [{"path": "x.py"}]}
    ))
    assert read_result["operation"] == "read"
    assert read_result["args"] == ("repo", [{"path": "x.py"}], 48 * 1024)
    assert server.repo_preview(TypeAdapter(RepoPreviewRequest).validate_python(
        {"operation": "remove_file", "repo_name": "repo", "path": "x", "expected_sha256": "a" * 64}
    ))["operation"] == "remove"
    assert TypeAdapter(RepoPreviewRequest).validate_python(
        {"operation": "patch", "repo_name": "repo", "operations": [{"action": "modify", "path": "x"}]}
    ).response_budget_bytes == 12 * 1024
    assert TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "commit_range", "repo_name": "repo", "base_commit": "a" * 40, "head_commit": "b" * 40}
    ).response_budget_bytes == 12 * 1024
    apply_result = server.repo_apply(TypeAdapter(RepoApplyRequest).validate_python(
        {"operation": "previewed_change", "repo_name": "repo", "patch_id": "patch_1"}
    ))
    assert apply_result["operation"] == "previewed_change"
    assert apply_result["accepted"] is True
    assert apply_result["transaction_id"] == "run_apply_1"
    assert server.repo_commit(TypeAdapter(RepoCommitRequest).validate_python(
        {"operation": "commit_selected", "repo_name": "repo", "files": ["x"], "title": "fix: x"}
    ))["operation"] == "commit"
    assert TypeAdapter(RepoCommitRequest).validate_python(
        {"operation": "commit_selected", "repo_name": "repo", "files": ["x"], "title": "fix: x"}
    ).response_budget_bytes == 12 * 1024


def test_repo_commit_projection_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "commit_selected_files",
        lambda *args: {
            "ok": True,
            "operation": "commit",
            "changed_files": [f"file-{index}-" + "x" * 200 for index in range(100)],
            "message": "m" * 1000,
        },
    )
    request = TypeAdapter(RepoCommitRequest).validate_python(
        {
            "operation": "commit_selected",
            "repo_name": "repo",
            "files": ["x.py"],
            "title": "fix: x",
            "response_budget_bytes": 4096,
        }
    )
    result = server.repo_commit(request)
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096


def test_repo_preview_projection_honors_response_budget(monkeypatch) -> None:
    preview = {
        "ok": True,
        "patch_id": "patch_1",
        "repo_name": "repo",
        "diff": "d" * 50_000,
        "changed_files": [f"file_{index}.py" for index in range(5000)],
        "validation_errors": ["e" * 500 for _ in range(20)],
        "warnings": ["w" * 500 for _ in range(20)],
        "newline_diagnostics": [{"path": f"file_{index}.py"} for index in range(20)],
    }
    monkeypatch.setattr(server, "preview_repo_patch", lambda *args: dict(preview))
    result = server.repo_preview(
        TypeAdapter(RepoPreviewRequest).validate_python(
            {
                "operation": "patch",
                "repo_name": "repo",
                "operations": [{"action": "modify", "path": "x"}],
                "response_budget_bytes": 4096,
            }
        )
    )
    assert result["patch_id"] == "patch_1"
    assert result["changed_file_count"] == 5000
    assert result["truncated"] is True
    assert result["response_bytes"] <= 4096
    full = server.repo_preview(
        TypeAdapter(RepoPreviewRequest).validate_python(
            {
                "operation": "patch",
                "repo_name": "repo",
                "operations": [{"action": "modify", "path": "x"}],
                "view": "full",
            }
        )
    )
    assert len(full["diff"]) == 50_000


def test_commit_range_projection_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(server, "_repo_context", lambda _repo_name: ("repo", None, "repo"))
    monkeypatch.setattr(
        server,
        "inspect_commit_range",
        lambda *args: {
            "ok": True,
            "repo_name": "repo",
            "base_commit": "a" * 40,
            "head_commit": "b" * 40,
            "name_status": "M\tfile.py\n" * 5000,
            "diff_stat": "file.py | 1 +\n" * 500,
            "diff": "d" * 50_000,
            "error": "",
        },
    )
    result = server.repo_query(
        TypeAdapter(RepoQueryRequest).validate_python(
            {
                "operation": "commit_range",
                "repo_name": "repo",
                "base_commit": "a" * 40,
                "head_commit": "b" * 40,
                "response_budget_bytes": 4096,
            }
        )
    )
    assert result["name_status_count"] == 5000
    assert result["truncated"] is True
    assert result["response_bytes"] <= 4096
    full = server.repo_query(
        TypeAdapter(RepoQueryRequest).validate_python(
            {
                "operation": "commit_range",
                "repo_name": "repo",
                "base_commit": "a" * 40,
                "head_commit": "b" * 40,
                "view": "full",
            }
        )
    )
    assert len(full["diff"]) == 50_000


def test_repo_list_files_model_exposes_compact_and_full_views() -> None:
    compact = TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "list_files", "repo_name": "repo", "max_results": 7}
    )
    assert compact.view == "compact"
    assert compact.response_budget_bytes == 12 * 1024

    full = TypeAdapter(RepoQueryRequest).validate_python(
        {
            "operation": "list_files",
            "repo_name": "repo",
            "view": "full",
            "response_budget_bytes": 4096,
        }
    )
    assert full.view == "full"


def test_repo_recent_files_model_exposes_compact_and_full_views() -> None:
    compact = TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "recent_files", "repo_name": "repo", "limit": 7}
    )
    assert compact.view == "compact"
    assert compact.response_budget_bytes == 12 * 1024

    full = TypeAdapter(RepoQueryRequest).validate_python(
        {
            "operation": "recent_files",
            "repo_name": "repo",
            "view": "full",
            "response_budget_bytes": 4096,
        }
    )
    assert full.view == "full"


def test_repo_log_model_exposes_compact_and_full_views() -> None:
    compact = TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "log", "repo_name": "repo", "limit": 7}
    )
    assert compact.view == "compact"
    assert compact.response_budget_bytes == 12 * 1024

    full = TypeAdapter(RepoQueryRequest).validate_python(
        {
            "operation": "log",
            "repo_name": "repo",
            "view": "full",
            "response_budget_bytes": 4096,
        }
    )
    assert full.view == "full"


def test_repo_status_model_exposes_compact_and_full_views() -> None:
    compact = TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "status", "repo_name": "repo"}
    )
    assert compact.view == "compact"
    assert compact.response_budget_bytes == 12 * 1024

    full = TypeAdapter(RepoQueryRequest).validate_python(
        {
            "operation": "status",
            "repo_name": "repo",
            "view": "full",
            "response_budget_bytes": 4096,
        }
    )
    assert full.view == "full"


def test_repo_patch_status_model_exposes_compact_and_full_views() -> None:
    compact = TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "patch_status", "repo_name": "repo", "patch_id": "patch_1"}
    )
    assert compact.view == "compact"
    assert compact.response_budget_bytes == 12 * 1024

    full = TypeAdapter(RepoQueryRequest).validate_python(
        {
            "operation": "patch_status",
            "repo_name": "repo",
            "patch_id": "patch_1",
            "view": "full",
            "response_budget_bytes": 4096,
        }
    )
    assert full.view == "full"


def test_repo_compact_status_model_exposes_response_budget() -> None:
    request = TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "compact_status", "repo_name": "repo"}
    )
    assert request.response_budget_bytes == 12 * 1024


def test_docker_inspect_model_exposes_response_budget() -> None:
    request = TypeAdapter(DockerQueryRequest).validate_python(
        {
            "operation": "inspect",
            "repo_name": "repo",
            "inspection": "compose_ps",
        }
    )
    assert request.response_budget_bytes == 12 * 1024


def test_docker_capabilities_model_exposes_response_budget() -> None:
    request = TypeAdapter(DockerQueryRequest).validate_python(
        {"operation": "capabilities"}
    )
    assert request.response_budget_bytes == 12 * 1024


def test_docker_capabilities_compact_envelope(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_config", lambda: object())
    monkeypatch.setattr(
        server,
        "_list_docker_capabilities",
        lambda config, repo_config=None: {
            "ok": True,
            "actions": [f"action-{index}" for index in range(5000)],
            "exec_profiles": [],
            "read_only_operations": [],
        },
    )
    result = server.list_docker_capabilities(response_budget_bytes=4096)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["truncated"] is True
    assert result["response_bytes"] <= 4096


def test_docker_health_model_exposes_response_budget() -> None:
    request = TypeAdapter(DockerQueryRequest).validate_python({"operation": "health"})
    assert request.view == "compact"
    assert request.response_budget_bytes == 12 * 1024


def test_docker_health_compact_envelope(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_config", lambda: object())
    monkeypatch.setattr(
        server,
        "_docker_health",
        lambda config: {"ok": True, "engine": {"status": "ok"}, "compose": {}},
    )
    result = server.docker_health(response_budget_bytes=4096)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["response_bytes"] <= 4096


def test_cloudflare_inspect_model_exposes_response_budget() -> None:
    request = TypeAdapter(CloudflareQueryRequest).validate_python(
        {
            "operation": "inspect",
            "repo_name": "repo",
            "profile_id": "production",
            "inspection": "dns_records",
        }
    )
    assert request.response_budget_bytes == 12 * 1024


def test_cloudflare_capabilities_model_exposes_response_budget() -> None:
    request = TypeAdapter(CloudflareQueryRequest).validate_python(
        {"operation": "capabilities", "repo_name": "repo"}
    )
    assert request.response_budget_bytes == 12 * 1024


def test_cloudflare_capabilities_compact_envelope(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_config", lambda: object())
    monkeypatch.setattr(
        server,
        "_list_cloudflare_capabilities",
        lambda config, repo_name: {
            "ok": True,
            "repo_name": repo_name,
            "actions": [f"action-{index}" for index in range(5000)],
            "profiles": [],
            "zones": [],
            "resources": [],
        },
    )
    result = server.list_cloudflare_capabilities("repo", response_budget_bytes=4096)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["truncated"] is True
    assert result["response_bytes"] <= 4096


def test_cloudflare_health_model_exposes_response_budget() -> None:
    request = TypeAdapter(CloudflareQueryRequest).validate_python(
        {"operation": "health", "repo_name": "repo", "profile_id": "production"}
    )
    assert request.view == "compact"
    assert request.response_budget_bytes == 12 * 1024


def test_docker_query_full_views_preserve_authoritative_payloads(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_config", lambda: object())
    monkeypatch.setattr(
        server,
        "_list_docker_capabilities",
        lambda config, repo_config=None: {
            "ok": True,
            "actions": [f"action-{index}" for index in range(5000)],
        },
    )
    capabilities = server.docker_query(
        TypeAdapter(DockerQueryRequest).validate_python(
            {"operation": "capabilities", "view": "full", "response_budget_bytes": 1024}
        )
    )
    assert len(capabilities["actions"]) == 5000
    assert "projection_version" not in capabilities

    monkeypatch.setattr(
        server,
        "_docker_health",
        lambda config: {"ok": True, "details": "h" * 50_000},
    )
    health = server.docker_query(
        TypeAdapter(DockerQueryRequest).validate_python(
            {"operation": "health", "view": "full", "response_budget_bytes": 1024}
        )
    )
    assert len(health["details"]) == 50_000

    monkeypatch.setattr(
        server, "_repo_context", lambda repo_name: (repo_name, object(), repo_name)
    )
    monkeypatch.setattr(
        server, "resolve_repo_config", lambda config, repo_name: (repo_name, object())
    )
    monkeypatch.setattr(
        server,
        "_run_docker_inspection",
        lambda *args, **kwargs: {"ok": True, "stdout": "x" * 50_000},
    )
    inspection = server.docker_query(
        TypeAdapter(DockerQueryRequest).validate_python(
            {
                "operation": "inspect",
                "repo_name": "repo",
                "inspection": "compose_ps",
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )
    assert len(inspection["stdout"]) == 50_000


def test_cloudflare_query_full_views_preserve_authoritative_payloads(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_config", lambda: object())
    monkeypatch.setattr(
        server,
        "_list_cloudflare_capabilities",
        lambda config, repo_name: {
            "ok": True,
            "actions": [f"action-{index}" for index in range(5000)],
        },
    )
    capabilities = server.cloudflare_query(
        TypeAdapter(CloudflareQueryRequest).validate_python(
            {
                "operation": "capabilities",
                "repo_name": "repo",
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )
    assert len(capabilities["actions"]) == 5000
    assert "projection_version" not in capabilities

    monkeypatch.setattr(
        server,
        "authorize_cloudflare_profile",
        lambda config, repo_name, profile_id: (repo_name, object()),
    )
    monkeypatch.setattr(
        server,
        "_cloudflare_health",
        lambda config, profile_id: {"ok": True, "details": "h" * 50_000},
    )
    health = server.cloudflare_query(
        TypeAdapter(CloudflareQueryRequest).validate_python(
            {
                "operation": "health",
                "repo_name": "repo",
                "profile_id": "production",
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )
    assert len(health["details"]) == 50_000

    monkeypatch.setattr(
        server,
        "_run_cloudflare_inspection",
        lambda *args, **kwargs: {"ok": True, "result": ["x" * 5000] * 20},
    )
    inspection = server.cloudflare_query(
        TypeAdapter(CloudflareQueryRequest).validate_python(
            {
                "operation": "inspect",
                "repo_name": "repo",
                "profile_id": "production",
                "inspection": "dns_records",
                "view": "full",
                "response_budget_bytes": 1024,
            }
        )
    )
    assert len(inspection["result"]) == 20
    assert len(inspection["result"][0]) == 5000


def test_cloudflare_health_compact_envelope(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_config", lambda: object())
    monkeypatch.setattr(
        server,
        "authorize_cloudflare_profile",
        lambda config, repo_name, profile_id: (repo_name, object()),
    )
    monkeypatch.setattr(
        server,
        "_cloudflare_health",
        lambda config, profile_id: {
            "ok": True,
            "engine": {"status": "ok"},
            "token": {"present": True},
        },
    )
    result = server.cloudflare_health("repo", "profile", response_budget_bytes=4096)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["response_bytes"] <= 4096


def test_supervisor_events_model_exposes_response_budget() -> None:
    request = TypeAdapter(SupervisorQueryRequest).validate_python(
        {"operation": "events", "supervisor_id": "sup_1"}
    )
    assert request.response_budget_bytes == 12 * 1024


def test_run_start_accepts_and_dispatches_remote_powershell(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeJobs:
        def start_remote_powershell(self, host_id, executable_path, argv, **kwargs):
            calls.append(
                {
                    "host_id": host_id,
                    "executable_path": executable_path,
                    "argv": argv,
                    **kwargs,
                }
            )
            return {"accepted": True, "run_id": "remote_run"}

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())
    request = TypeAdapter(RunStartRequest).validate_python(
        {
            "operation": "remote_powershell",
            "host_id": "remote_windows",
            "executable_path": "/opt/microsoft/powershell/7/pwsh",
            "argv": ["-NoProfile", "-Command", "Write-Output ok"],
            "working_directory": "/tmp/a b",
            "environment": {"VALUE": "a=b c"},
            "stdin_base64": "AP8=",
            "timeout_seconds": None,
        }
    )

    result = server.run_start(request)

    assert result["run_id"] == "remote_run"
    assert calls == [
        {
            "host_id": "remote_windows",
            "executable_path": "/opt/microsoft/powershell/7/pwsh",
            "argv": ["-NoProfile", "-Command", "Write-Output ok"],
            "working_directory": "/tmp/a b",
            "environment": {"VALUE": "a=b c"},
            "stdin_bytes": b"\x00\xff",
            "timeout_seconds": None,
        }
    ]


def test_run_start_dispatches_bound_hermes_companion_request(tmp_path, monkeypatch) -> None:
    checkout = tmp_path / "hermes"
    checkout.mkdir()
    calls = []

    class FakeJobs:
        def start_executable_profile(self, repo_name, profile_id, argv, **kwargs):
            calls.append(
                {
                    "repo_name": repo_name,
                    "profile_id": profile_id,
                    "argv": argv,
                    **kwargs,
                }
            )
            return {"accepted": True, "run_id": "hermes_run"}

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())
    request = TypeAdapter(RunStartRequest).validate_python(
        {
            "operation": "hermes_companion",
            "repo_name": "sample",
            "profile_id": "python",
            "checkout": str(checkout),
            "companion_operation": "tool_search",
            "payload": {"query": "github", "limit": 5},
            "expected_registry_generation": 7,
            "expected_schema_hash": "a" * 64,
        }
    )

    result = server.run_start(request)

    assert result["run_id"] == "hermes_run"
    assert result["hermes_companion"]["operation"] == "tool_search"
    assert calls[0]["hermes_companion"]["expected_registry_generation"] == 7
    assert calls[0]["hermes_companion"]["expected_schema_hash"] == "a" * 64
    assert calls[0]["stdin_text"].endswith("\n")

    call_request = TypeAdapter(RunStartRequest).validate_python(
        {
            "operation": "hermes_companion",
            "repo_name": "sample",
            "profile_id": "python",
            "checkout": str(checkout),
            "companion_operation": "tool_call",
            "payload": {
                "tool_name": "read_file",
                "arguments": {"path": "PLANS.md", "offset": 1, "limit": 5},
            },
            "expected_registry_generation": 72,
            "expected_schema_hash": "b" * 64,
        }
    )
    call_result = server.run_start(call_request)

    assert call_result["hermes_companion"]["operation"] == "tool_call"
    assert json.loads(calls[1]["stdin_text"])["tool_name"] == "read_file"
    assert json.loads(calls[1]["stdin_text"])["arguments"]["limit"] == 5


def test_run_start_rejects_invalid_remote_powershell_binary_input() -> None:
    request = TypeAdapter(RunStartRequest).validate_python(
        {
            "operation": "remote_powershell",
            "host_id": "remote_windows",
            "executable_path": "/usr/bin/pwsh",
            "stdin_base64": "not-base64",
        }
    )
    with pytest.raises(ValueError, match="valid base64"):
        server.run_start(request)


def test_run_query_dispatches_powershell_group_operations(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeJobs:
        def get_powershell_group(self, group_id: str) -> dict:
            calls.append(("get", group_id))
            return {"ok": True, "group_id": group_id, "status": "running"}

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())
    adapter = TypeAdapter(RunQueryRequest)
    for operation in ("group_status", "group_result"):
        result = server.run_query(
            adapter.validate_python({"operation": operation, "group_id": "group_1"})
        )
        assert result["group_id"] == "group_1"
        assert result["response_budget_bytes"] == 12 * 1024
    assert calls == [("get", "group_1"), ("get", "group_1")]


def test_cancel_run_routes_powershell_groups(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class FakeJobs:
        def cancel_run(self, run_id: str) -> dict:
            calls.append(("run", run_id))
            return {"run_id": run_id}

        def cancel_powershell_group(self, group_id: str) -> dict:
            calls.append(("group", group_id))
            return {"group_id": group_id}

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())
    assert server.cancel_run("20260716T000000Z_powershell_group_deadbeef")["group_id"]
    assert server.cancel_run("20260716T000000Z_executable_profile_deadbeef")["run_id"]
    assert calls == [
        ("group", "20260716T000000Z_powershell_group_deadbeef"),
        ("run", "20260716T000000Z_executable_profile_deadbeef"),
    ]


def test_cancel_run_projection_honors_response_budget(monkeypatch) -> None:
    class Manager:
        def cancel_run(self, run_id: str) -> dict:
            return {
                "ok": True,
                "run_id": run_id,
                "status": "cancellation_requested",
                "process_tree": [{"pid": index} for index in range(5000)],
                "message": "m" * 20_000,
            }

    monkeypatch.setattr(server, "get_job_manager", lambda: Manager())
    result = server.cancel_run("run_1", response_budget_bytes=4096)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["response_bytes"] <= 4096
    assert result["process_tree_count"] == 5000
    assert result["has_more"] is True


def test_run_start_models_reject_cross_operation_fields() -> None:
    adapter = TypeAdapter(RunStartRequest)
    assert adapter.validate_python(
        {"operation": "git_readonly", "repo_name": "repo", "git_operation": "status"}
    ).git_operation == "status"
    assert adapter.validate_python(
        {
            "operation": "external_fixture_validation",
            "repo_name": "repo",
            "url": "https://example.test/f.json",
            "expected_sha256": "a" * 64,
        }
    ).validation == "none"
    powershell = adapter.validate_python(
        {
            "operation": "powershell",
            "repo_name": "repo",
            "argv": ["-NoProfile", "-Command", "Write-Output 'a b'"],
            "working_directory": "C:/work",
            "environment": {"ARBITRARY_VALUE": "a=b c"},
            "stdin_base64": "AAEC",
            "timeout_seconds": 90,
        }
    )
    assert powershell.profile_id == "powershell"
    assert powershell.argv[-1] == "Write-Output 'a b'"
    powershell_group = adapter.validate_python(
        {
            "operation": "powershell_group",
            "repo_name": "repo",
            "requested_concurrency": 2,
            "children": [
                {"idempotency_key": "one", "argv": ["-Command", "one"]},
                {"idempotency_key": "two", "argv": ["-Command", "two"]},
            ],
        }
    )
    assert powershell_group.requested_concurrency == 2
    assert [child.idempotency_key for child in powershell_group.children] == [
        "one",
        "two",
    ]
    invalid = (
        {"operation": "project_command", "repo_name": "repo", "command_id": "pytest"},
        {"operation": "pytest_path", "repo_name": "repo", "path": "x", "command_id": "pytest"},
        {"operation": "git_readonly", "repo_name": "repo", "git_operation": "shell"},
        {"operation": "external_fixture_validation", "repo_name": "repo", "url": "http://example.test", "expected_sha256": "a" * 64},
        {"operation": "powershell", "repo_name": "repo", "argv": [], "stdin_text": "x", "stdin_base64": "eA=="},
        {"operation": "powershell", "repo_name": "repo", "argv": [], "command_id": "blocked"},
        {"operation": "powershell_group", "repo_name": "repo", "children": []},
        {"operation": "powershell_group", "repo_name": "repo", "children": [{"argv": [], "stdin_text": "x", "stdin_base64": "eA=="}]},
        {"operation": "powershell_group", "repo_name": "repo", "children": [{"argv": []}], "repository_lock_policy": "exclusive"},
    )
    for payload in invalid:
        with pytest.raises(ValidationError):
            adapter.validate_python(payload)


def test_run_start_dispatches_to_allowlisted_job_manager_methods(monkeypatch) -> None:
    calls = []

    class FakeJobs:
        def __getattr__(self, name):
            def invoke(*args, **kwargs):
                calls.append((name, args, kwargs))
                return {"ok": True, "run_id": name}

            return invoke

    monkeypatch.setattr(server, "get_job_manager", lambda: FakeJobs())
    for payload, expected in (
        ({"operation": "pytest_path", "repo_name": "repo", "path": "tests"}, "start_pytest_path"),
        ({"operation": "py_compile_path", "repo_name": "repo", "path": "x.py"}, "start_py_compile_path"),
        ({"operation": "bash_syntax_path", "repo_name": "repo", "path": "x.sh"}, "start_bash_n_path"),
        ({"operation": "json_validation_path", "repo_name": "repo", "path": "x.json", "timeout_seconds": 17}, "start_json_validation_path"),
        ({"operation": "git_readonly", "repo_name": "repo", "git_operation": "status"}, "start_git_readonly"),
        ({"operation": "external_fixture_validation", "repo_name": "repo", "url": "https://example.test/x", "expected_sha256": "a" * 64}, "start_external_fixture_validation"),
        ({"operation": "powershell", "repo_name": "repo", "argv": ["-Command", "git status"], "environment": {"X": "a b"}, "stdin_base64": "AAE=", "timeout_seconds": 60}, "start_executable_profile"),
        ({"operation": "powershell_group", "repo_name": "repo", "requested_concurrency": 2, "children": [{"idempotency_key": "one", "argv": ["-Command", "one"], "stdin_base64": "AAE="}]}, "start_powershell_group"),
    ):
        server.run_start(TypeAdapter(RunStartRequest).validate_python(payload))
        assert calls[-1][0] == expected
    validator_call = next(call for call in calls if call[0] == "start_json_validation_path")
    assert validator_call[2]["timeout_seconds"] == 17
    powershell_group_call = calls[-1]
    assert powershell_group_call[1][0] == "repo"
    assert powershell_group_call[1][1][0]["idempotency_key"] == "one"
    assert powershell_group_call[1][1][0]["stdin_bytes"] == b"\x00\x01"
    assert powershell_group_call[2]["requested_concurrency"] == 2
    powershell_payload = TypeAdapter(RunStartRequest).validate_python(
        {"operation": "powershell", "repo_name": "repo", "argv": ["-Command", "git status"], "environment": {"X": "a b"}, "stdin_base64": "AAE=", "timeout_seconds": 60}
    )
    server.run_start(powershell_payload)
    powershell_call = calls[-1]
    assert powershell_call[1] == ("repo", "powershell", ["-Command", "git status"])
    assert powershell_call[2]["environment"] == {"X": "a b"}
    assert powershell_call[2]["stdin_bytes"] == b"\x00\x01"
    assert powershell_call[2]["timeout_seconds"] == 60


def test_run_start_rejects_invalid_parallel_powershell_binary_stdin(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_job_manager", lambda: object())
    request = TypeAdapter(RunStartRequest).validate_python(
        {
            "operation": "powershell_group",
            "repo_name": "repo",
            "children": [{"argv": [], "stdin_base64": "not-base64"}],
        }
    )
    with pytest.raises(ValueError, match="valid base64"):
        server.run_start(request)


def test_run_start_rejects_invalid_powershell_binary_stdin(monkeypatch) -> None:
    monkeypatch.setattr(server, "get_job_manager", lambda: object())
    request = TypeAdapter(RunStartRequest).validate_python(
        {"operation": "powershell", "repo_name": "repo", "stdin_base64": "not-base64"}
    )
    with pytest.raises(ValueError, match="valid base64"):
        server.run_start(request)


def test_phase6_domain_models_reject_cross_domain_fields() -> None:
    assert TypeAdapter(DockerQueryRequest).validate_python(
        {"operation": "inspect", "repo_name": "repo", "inspection": "containers"}
    ).inspection == "containers"
    assert TypeAdapter(CloudflareQueryRequest).validate_python(
        {"operation": "health", "repo_name": "repo", "profile_id": "cf"}
    ).profile_id == "cf"
    assert TypeAdapter(SSHQueryRequest).validate_python(
        {"operation": "profile_status", "change_id": "change_1"}
    ).change_id == "change_1"
    assert TypeAdapter(SSHQueryRequest).validate_python(
        {"operation": "capabilities"}
    ).response_budget_bytes == 12 * 1024
    ssh_inspection = TypeAdapter(SSHInspectRequest).validate_python(
        {"operation": "inspection", "host_id": "dev", "inspection": "uptime"}
    )
    assert ssh_inspection.response_budget_bytes == 12 * 1024
    assert TypeAdapter(SSHActionRequest).validate_python(
        {"action": "command", "host_id": "dev", "command_id": "uptime"}
    ).command_id == "uptime"
    assert TypeAdapter(DockerActionRequest).validate_python(
        {"action": "compose_up", "repo_name": "repo"}
    ).action == "compose_up"
    assert TypeAdapter(CloudflareActionRequest).validate_python(
        {"action": "dns_create", "repo_name": "repo", "profile_id": "cf"}
    ).action == "dns_create"
    with pytest.raises(ValidationError):
        TypeAdapter(SSHActionRequest).validate_python(
            {"action": "command", "host_id": "dev", "command_id": "uptime", "remote_path": "/srv"}
        )


def test_ssh_execution_policy_gateway_defaults_and_strictness() -> None:
    request = SSHExecutionPolicyGatewayRequest()
    assert request.autonomy_profile == "permissive"
    assert request.execution_mode == "structured"
    with pytest.raises(ValidationError):
        SSHExecutionPolicyGatewayRequest.model_validate(
            {"execution_mode": "unknown"}
        )
    with pytest.raises(ValidationError):
        SSHExecutionPolicyGatewayRequest.model_validate(
            {"autonomy_profile": "permissive", "unexpected": True}
        )
    command = SSHCommandAction.model_validate(
        {"action": "command", "host_id": "dev", "command_id": "uptime"}
    )
    administration = SSHAdministrationAction.model_validate(
        {
            "action": "administration",
            "host_id": "dev",
            "ssh_action": "service_restart",
            "autonomy_profile": "permissive",
            "execution_mode": "structured",
        }
    )
    transfer = TypeAdapter(SSHActionRequest).validate_python(
        {
            "action": "transfer",
            "host_id": "dev",
            "repo_name": "repo",
            "direction": "upload",
            "local_path": "artifact.bin",
            "remote_path": "/srv/artifact.bin",
            "autonomy_profile": "permissive",
        }
    )
    deployment = TypeAdapter(SSHActionRequest).validate_python(
        {
            "action": "deployment",
            "host_id": "dev",
            "deployment_id": "app",
            "confirmation": "confirm",
        }
    )
    assert command.autonomy_profile == "permissive"
    assert command.execution_mode == "structured"
    assert administration.autonomy_profile == "permissive"
    assert administration.execution_mode == "structured"
    assert transfer.autonomy_profile == "permissive"
    assert transfer.execution_mode == "structured"
    assert deployment.autonomy_profile == "permissive"
    assert deployment.execution_mode == "structured"


@pytest.mark.parametrize(
    "payload",
    [
        {
            "action": "command",
            "host_id": "dev",
            "command_id": "uptime",
            "execution_mode": "reviewed_script",
        },
        {
            "action": "administration",
            "host_id": "dev",
            "ssh_action": "service_restart",
            "execution_mode": "root_shell",
        },
        {
            "action": "transfer",
            "host_id": "dev",
            "repo_name": "repo",
            "direction": "upload",
            "local_path": "artifact.bin",
            "remote_path": "/srv/artifact.bin",
            "execution_mode": "reviewed_script",
        },
        {
            "action": "deployment",
            "host_id": "dev",
            "deployment_id": "app",
            "confirmation": "confirm",
            "execution_mode": "root_shell",
        },
    ],
)
def test_structured_ssh_actions_reject_non_structured_modes(payload: dict) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(SSHActionRequest).validate_python(payload)


def test_reviewed_script_contract_is_hash_pinned_and_policy_scoped() -> None:
    script = "set -euo pipefail\nuptime\n"
    digest = sha256(script.encode("utf-8")).hexdigest()
    request = SSHReviewedScriptAction.model_validate(
        {
            "action": "reviewed_script",
            "host_id": "dev",
            "interpreter": "pwsh",
            "arguments": ["--mode", "safe value"],
            "script": script,
            "script_sha256": digest,
            "autonomy_profile": "permissive",
        }
    )
    assert request.execution_mode == "reviewed_script"
    assert request.script_sha256 == digest
    assert request.interpreter == "pwsh"
    assert request.arguments == ["--mode", "safe value"]
    assert request.writes_remote is True
    assert request.high_risk is False

    permissive = request.model_copy(update={"autonomy_profile": "permissive"})
    assert SSHReviewedScriptAction.model_validate(
        permissive.model_dump(mode="python")
    ).autonomy_profile == "permissive"

    for autonomy_profile in ("balanced", "conservative"):
        with pytest.raises(ValidationError, match="Input should be 'permissive'"):
            SSHReviewedScriptAction.model_validate(
                {
                    **request.model_dump(mode="python"),
                    "autonomy_profile": autonomy_profile,
                }
            )

    with pytest.raises(ValidationError, match="SHA-256"):
        SSHReviewedScriptAction.model_validate(
            {**request.model_dump(mode="python"), "script_sha256": "0" * 64}
        )
    with pytest.raises(ValidationError, match="NUL"):
        nul_script = "echo ok\x00"
        SSHReviewedScriptAction.model_validate(
            {
                **request.model_dump(mode="python"),
                "script": nul_script,
                "script_sha256": sha256(nul_script.encode("utf-8")).hexdigest(),
            }
        )
    with pytest.raises(ValidationError, match="UTF-8 byte length"):
        oversized_script = "é" * ((MAX_REVIEWED_SSH_SCRIPT_BYTES // 2) + 1)
        SSHReviewedScriptAction.model_validate(
            {
                **request.model_dump(mode="python"),
                "script": oversized_script,
                "script_sha256": sha256(
                    oversized_script.encode("utf-8")
                ).hexdigest(),
            }
        )


def test_reviewed_script_arguments_are_bounded_and_control_free() -> None:
    script = "uptime\n"
    base = {
        "action": "reviewed_script",
        "host_id": "dev",
        "interpreter": "bash",
        "script": script,
        "script_sha256": sha256(script.encode("utf-8")).hexdigest(),
        "autonomy_profile": "permissive",
    }

    with pytest.raises(ValidationError, match="control characters"):
        SSHReviewedScriptAction.model_validate(
            {**base, "arguments": ["safe", "bad\x00value"]}
        )

    oversized_argument = "é" * ((MAX_REVIEWED_SSH_SCRIPT_ARG_BYTES // 2) + 1)
    with pytest.raises(ValidationError, match="argument exceeds"):
        SSHReviewedScriptAction.model_validate(
            {**base, "arguments": [oversized_argument]}
        )

    aggregate_arguments = [
        "x" * MAX_REVIEWED_SSH_SCRIPT_ARG_BYTES
        for _ in range(
            (MAX_REVIEWED_SSH_SCRIPT_ARGS_BYTES // MAX_REVIEWED_SSH_SCRIPT_ARG_BYTES)
            + 1
        )
    ]
    with pytest.raises(ValidationError, match="aggregate"):
        SSHReviewedScriptAction.model_validate(
            {**base, "arguments": aggregate_arguments}
        )

    with pytest.raises(ValidationError):
        SSHReviewedScriptAction.model_validate(
            {**base, "arguments": ["x"] * (MAX_REVIEWED_SSH_SCRIPT_ARGS + 1)}
        )


def test_reviewed_script_is_a_dedicated_public_ssh_action() -> None:
    script = "uptime\n"
    request = TypeAdapter(SSHActionRequest).validate_python(
        {
            "action": "reviewed_script",
            "host_id": "dev",
            "interpreter": "sh",
            "script": script,
            "script_sha256": sha256(script.encode("utf-8")).hexdigest(),
        }
    )

    assert isinstance(request, SSHReviewedScriptAction)
    assert request.execution_mode == "reviewed_script"
    with pytest.raises(ValidationError):
        TypeAdapter(SSHActionRequest).validate_python(
            {
                **request.model_dump(mode="python"),
                "command": "whoami",
            }
        )


def test_reviewed_script_gateway_forwards_only_the_dedicated_variant(
    monkeypatch,
) -> None:
    script = "set -euo pipefail\nuptime\n"
    digest = sha256(script.encode("utf-8")).hexdigest()
    captured: dict = {}

    def start(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return {"accepted": True, "run_id": "reviewed_run"}

    monkeypatch.setattr(server, "start_ssh_reviewed_script_async", start)
    request = TypeAdapter(SSHActionRequest).validate_python(
        {
            "action": "reviewed_script",
            "host_id": "dev",
            "interpreter": "bash",
            "script": script,
            "script_sha256": digest,
            "arguments": ["--mode", "safe value"],
            "autonomy_profile": "permissive",
        }
    )

    result = server.ssh_action(request)

    assert result["run_id"] == "reviewed_run"
    assert captured["args"] == ("dev", "bash", script, digest)
    assert captured["kwargs"] == {
        "arguments": ["--mode", "safe value"],
        "timeout_seconds": 3600,
        "writes_remote": True,
        "high_risk": False,
        "autonomy_profile": "permissive",
        "execution_mode": "reviewed_script",
    }


def test_reviewed_script_async_forwards_arguments_to_job_manager(monkeypatch) -> None:
    script = "printf '%s\\n' \"$1\"\n"
    digest = sha256(script.encode("utf-8")).hexdigest()
    captured: dict = {}

    class Manager:
        def start_ssh_reviewed_script(self, *args, **kwargs):
            captured.update(args=args, kwargs=kwargs)
            return {"accepted": True, "run_id": "reviewed_run"}

    monkeypatch.setattr(server, "get_job_manager", lambda: Manager())

    result = server.start_ssh_reviewed_script_async(
        "dev",
        "bash",
        script,
        digest,
        arguments=["first", "safe value"],
        autonomy_profile="permissive",
    )

    assert result["run_id"] == "reviewed_run"
    assert captured["args"] == ("dev", "bash", script, digest)
    assert captured["kwargs"]["arguments"] == ["first", "safe value"]
    assert captured["kwargs"]["autonomy_profile"] == "permissive"
    assert captured["kwargs"]["execution_mode"] == "reviewed_script"


def test_permissive_pwsh_gateway_forwards_reviewed_script_arguments(
    monkeypatch,
) -> None:
    script = "Write-Output $args[0]\n"
    digest = sha256(script.encode("utf-8")).hexdigest()
    captured: dict = {}

    def start(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return {"accepted": True, "run_id": "permissive_pwsh_run"}

    monkeypatch.setattr(server, "start_ssh_reviewed_script_async", start)
    request = TypeAdapter(SSHActionRequest).validate_python(
        {
            "action": "reviewed_script",
            "host_id": "dev",
            "interpreter": "pwsh",
            "arguments": ["safe value", "--mode=test"],
            "script": script,
            "script_sha256": digest,
            "autonomy_profile": "permissive",
        }
    )

    result = server.ssh_action(request)

    assert result["run_id"] == "permissive_pwsh_run"
    assert captured["args"] == ("dev", "pwsh", script, digest)
    assert captured["kwargs"]["arguments"] == ["safe value", "--mode=test"]
    assert captured["kwargs"]["autonomy_profile"] == "permissive"
    assert captured["kwargs"]["execution_mode"] == "reviewed_script"


def test_root_shell_contract_is_hash_pinned_and_permissive_only() -> None:
    script = "id -u\n"
    digest = sha256(script.encode("utf-8")).hexdigest()
    request = TypeAdapter(SSHActionRequest).validate_python(
        {
            "action": "root_shell",
            "host_id": "dev",
            "script": script,
            "script_sha256": digest,
        }
    )

    assert isinstance(request, SSHRootShellAction)
    assert request.autonomy_profile == "permissive"
    assert request.execution_mode == "root_shell"
    assert request.writes_remote is True
    assert request.high_risk is True

    with pytest.raises(ValidationError):
        TypeAdapter(SSHActionRequest).validate_python(
            {
                **request.model_dump(mode="python"),
                "autonomy_profile": "balanced",
            }
        )
    with pytest.raises(ValidationError, match="SHA-256"):
        TypeAdapter(SSHActionRequest).validate_python(
            {
                **request.model_dump(mode="python"),
                "script_sha256": "0" * 64,
            }
        )
    with pytest.raises(ValidationError):
        TypeAdapter(SSHActionRequest).validate_python(
            {
                **request.model_dump(mode="python"),
                "command": "whoami",
            }
        )


def test_root_shell_gateway_forwards_only_the_dedicated_variant(monkeypatch) -> None:
    script = "id -u\n"
    digest = sha256(script.encode("utf-8")).hexdigest()
    captured: dict = {}

    def start(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs)
        return {"accepted": True, "run_id": "root_run"}

    monkeypatch.setattr(server, "start_ssh_root_shell_async", start)
    request = TypeAdapter(SSHActionRequest).validate_python(
        {
            "action": "root_shell",
            "host_id": "dev",
            "script": script,
            "script_sha256": digest,
        }
    )

    result = server.ssh_action(request)

    assert result["run_id"] == "root_run"
    assert captured["args"] == ("dev", script, digest)
    assert captured["kwargs"] == {
        "timeout_seconds": 3600,
        "autonomy_profile": "permissive",
        "execution_mode": "root_shell",
    }


def test_ssh_transfer_and_deployment_gateway_forward_execution_policy(
    monkeypatch,
) -> None:
    calls: list[tuple[str, tuple, dict]] = []

    monkeypatch.setattr(
        server,
        "start_ssh_transfer_async",
        lambda *args, **kwargs: calls.append(("transfer", args, kwargs)) or {"ok": True},
    )
    monkeypatch.setattr(
        server,
        "start_ssh_deployment_async",
        lambda *args, **kwargs: calls.append(("deployment", args, kwargs)) or {"ok": True},
    )

    server.ssh_action(
        TypeAdapter(SSHActionRequest).validate_python(
            {
                "action": "transfer",
                "host_id": "dev",
                "repo_name": "repo",
                "direction": "upload",
                "local_path": "artifact.bin",
                "remote_path": "/srv/artifact.bin",
                "autonomy_profile": "permissive",
                "execution_mode": "structured",
            }
        )
    )
    server.ssh_action(
        TypeAdapter(SSHActionRequest).validate_python(
            {
                "action": "deployment",
                "host_id": "dev",
                "deployment_id": "app",
                "confirmation": "confirm",
                "autonomy_profile": "permissive",
                "execution_mode": "structured",
            }
        )
    )

    assert calls[0][2] == {
        "autonomy_profile": "permissive",
        "execution_mode": "structured",
    }
    assert calls[1][2] == {
        "autonomy_profile": "permissive",
        "execution_mode": "structured",
    }


def test_system_self_check_projection_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "run_local_self_check",
        lambda: {
            "ok": False,
            "checks": {
                f"check_{index}": {
                    "ok": False,
                    "error": "diagnostic " + "x" * 1000,
                    "stdout": "protected " + "y" * 1000,
                }
                for index in range(20)
            },
        },
    )
    request = TypeAdapter(SystemQueryRequest).validate_python(
        {"operation": "self_check", "response_budget_bytes": 4096}
    )
    result = server.system_query(request)
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096
    assert "stdout" not in result["checks"]["check_0"]


def test_system_capabilities_resolves_live_async_discovery(monkeypatch) -> None:
    async def fake_list_tools():
        return [
            SimpleNamespace(
                to_mcp_tool=lambda: SimpleNamespace(
                    model_dump=lambda mode: {"name": "demo_gateway"}
                )
            )
        ]

    monkeypatch.setattr(server.mcp, "list_tools", fake_list_tools)
    result = server.system_query(
        TypeAdapter(SystemQueryRequest).validate_python(
            {"operation": "capabilities", "response_budget_bytes": 4096}
        )
    )
    assert result["action_names_count"] == 1
    assert result["response_bytes"] <= 4096
    full = server.system_query(
        TypeAdapter(SystemQueryRequest).validate_python(
            {"operation": "capabilities", "view": "full"}
        )
    )
    assert full["action_names"] == ["demo_gateway"]
    assert len(full["operation_inventory_hash"]) == 64
    assert len(full["public_schema_hash"]) == 64
    assert len(full["discovery_cache_generation"]) == 64
    assert len(full["live_input_schema_hash"]) == 64


def test_capability_identity_reports_connector_convergence(monkeypatch) -> None:
    request = TypeAdapter(SystemQueryRequest).validate_python(
        {
            "operation": "capability_identity",
            "expected_server_build_hash": "f" * 64,
            "expected_schema_hash": "e" * 64,
            "expected_capability_epoch": "stale",
            "expected_operation_inventory_hash": "d" * 64,
            "expected_live_input_schema_hash": "f" * 64,
            "response_budget_bytes": 4096,
        }
    )
    result = server.system_query(request)
    assert result["converged"] is False
    assert "connector_server_build_hash" in result["mismatches"]
    assert "connector_schema_hash" in result["mismatches"]
    assert "connector_operation_inventory_hash" in result["mismatches"]
    assert "connector_live_input_schema_hash" in result["mismatches"]
    assert result["operation_inventory_gateway_count"] > 0
    assert result["response_bytes"] <= 4096


def test_capability_identity_binds_public_schema_and_discovery_cache() -> None:
    baseline = server.system_query(
        TypeAdapter(SystemQueryRequest).validate_python(
            {"operation": "capability_identity", "view": "full"}
        )
    )
    request = TypeAdapter(SystemQueryRequest).validate_python(
        {
            "operation": "capability_identity",
            "expected_connector_schema_hash": baseline["public_schema_hash"],
            "expected_public_schema_hash": baseline["public_schema_hash"],
            "expected_live_input_schema_hash": baseline["live_input_schema_hash"],
            "expected_operation_inventory_hash": baseline["operation_inventory_hash"],
            "expected_discovery_cache_generation": baseline[
                "discovery_cache_generation"
            ],
            "response_budget_bytes": 4096,
        }
    )
    result = server.system_query(request)
    assert result["converged"] is True
    assert result["connector_schema_hash"] == baseline["public_schema_hash"]
    stale = TypeAdapter(SystemQueryRequest).validate_python(
        {
            "operation": "capability_identity",
            "expected_discovery_cache_generation": "0" * 64,
            "response_budget_bytes": 4096,
        }
    )
    stale_result = server.system_query(stale)
    assert stale_result["converged"] is False
    assert "connector_discovery_cache_generation" in stale_result["mismatches"]


def test_capability_identity_reports_operation_schema_drift() -> None:
    baseline = server.system_query(
        TypeAdapter(SystemQueryRequest).validate_python(
            {"operation": "capability_identity", "view": "full"}
        )
    )
    operation_hashes = baseline["operation_schema_hashes"]
    assert operation_hashes["system_query.capabilities"]
    assert "capabilities" not in operation_hashes
    result = server.system_query(
        TypeAdapter(SystemQueryRequest).validate_python(
            {
                "operation": "capability_identity",
                "expected_operation_schema_hashes": {
                    "system_query.capabilities": operation_hashes[
                        "system_query.capabilities"
                    ],
                    "system_query.missing_from_connector": "0" * 64,
                },
                "response_budget_bytes": 4096,
            }
        )
    )
    assert result["converged"] is False
    assert (
        "connector_operation_missing:system_query.missing_from_connector"
        in result["mismatches"]
    )
    assert result["operation_schema_key_format"] == "gateway.operation"
    assert result["operation_schema_count"] == len(operation_hashes)
    assert "refresh connector schema" in result["refresh_guidance"]
    assert result["discovery_pass_count"] == 2
    assert result["discovery_passes_converged"] is True


def test_live_operation_schema_hashes_are_gateway_qualified(monkeypatch) -> None:
    def fake_tool(name: str, marker: str):
        return SimpleNamespace(
            to_mcp_tool=lambda: SimpleNamespace(
                model_dump=lambda mode: {
                    "name": name,
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "request": {
                                "oneOf": [
                                    {
                                        "type": "object",
                                        "properties": {
                                            "operation": {"const": "status"},
                                            "marker": {"const": marker},
                                        },
                                    }
                                ]
                            }
                        },
                    },
                }
            )
        )

    async def fake_list_tools():
        return [fake_tool("alpha_query", "alpha"), fake_tool("beta_query", "beta")]

    monkeypatch.setattr(server.mcp, "list_tools", fake_list_tools)
    hashes, error, converged, input_schema_hash = (
        server._live_operation_schema_hashes_sync()
    )
    assert error == ""
    assert converged is True
    assert len(input_schema_hash) == 64
    assert set(hashes) == {"alpha_query.status", "beta_query.status"}
    assert hashes["alpha_query.status"] != hashes["beta_query.status"]


def test_live_operation_schema_hashes_reject_conflicting_qualified_keys(
    monkeypatch,
) -> None:
    def fake_tool(marker: str):
        return SimpleNamespace(
            to_mcp_tool=lambda: SimpleNamespace(
                model_dump=lambda mode: {
                    "name": "alpha_query",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "request": {
                                "oneOf": [
                                    {
                                        "type": "object",
                                        "properties": {
                                            "operation": {"const": "status"},
                                            "marker": {"const": marker},
                                        },
                                    }
                                ]
                            }
                        },
                    },
                }
            )
        )

    async def fake_list_tools():
        return [fake_tool("first"), fake_tool("second")]

    monkeypatch.setattr(server.mcp, "list_tools", fake_list_tools)
    hashes, error, converged, _ = server._live_operation_schema_hashes_sync()
    assert set(hashes) == {"alpha_query.status"}
    assert error == "live operation-schema collisions: alpha_query.status"
    assert converged is False


def test_capability_identity_accepts_complete_schema_expectations() -> None:
    expected = {f"gateway_{index}.operation": "0" * 64 for index in range(256)}
    request = TypeAdapter(SystemQueryRequest).validate_python(
        {
            "operation": "capability_identity",
            "expected_operation_schema_hashes": expected,
        }
    )
    assert request.expected_operation_schema_hashes == expected


def test_capability_identity_rejects_disagreeing_discovery_passes(monkeypatch) -> None:
    calls = 0

    async def fake_list_tools():
        nonlocal calls
        calls += 1
        operation = "demo_first" if calls == 1 else "demo_second"
        return [
            SimpleNamespace(
                to_mcp_tool=lambda: SimpleNamespace(
                    model_dump=lambda mode: {
                        "name": "demo_gateway",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "request": {
                                    "oneOf": [
                                        {
                                            "type": "object",
                                            "properties": {
                                                "operation": {"const": operation}
                                            },
                                        }
                                    ]
                                }
                            },
                        },
                    }
                )
            )
        ]

    monkeypatch.setattr(server.mcp, "list_tools", fake_list_tools)
    result = server.system_query(
        TypeAdapter(SystemQueryRequest).validate_python(
            {"operation": "capability_identity", "response_budget_bytes": 4096}
        )
    )
    assert calls == 2
    assert result["discovery_passes_converged"] is False
    assert "live_operation_schema_discovery_pass_mismatch" in result["mismatches"]


def test_system_action_projection_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "reload_service",
        lambda modules: {
            "ok": True,
            "reloaded": [f"soma.module_{index}" for index in range(5000)],
            "resolved_modules": [f"soma.module_{index}" for index in range(5000)],
            "restart_required": [f"soma.restart_{index}" for index in range(5000)],
            "message": "m" * 20_000,
            "config_lifecycle": {"last_status": "reloaded", "last_error": "e" * 20_000},
        },
    )
    request = TypeAdapter(SystemActionRequest).validate_python(
        {"action": "reload", "response_budget_bytes": 4096}
    )
    result = server.system_action(request)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096
    assert result["reloaded_count"] == 5000


def test_ssh_query_projection_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "list_ssh_capabilities",
        lambda: {
            "ok": True,
            "enabled": True,
            "hosts": [
                {"host_id": f"host-{index}", "commands": [{"command_id": "run"}]}
                for index in range(5000)
            ],
            "error": "e" * 20_000,
        },
    )
    request = TypeAdapter(SSHQueryRequest).validate_python(
        {"operation": "capabilities", "response_budget_bytes": 4096}
    )
    result = server.ssh_query(request)
    assert result["view"] == "compact"
    assert result["projection_version"] == "cf1.v1"
    assert result["non_authoritative"] is True
    assert "authoritative" in result["notice"]
    assert result["response_bytes"] <= 4096
    assert result["host_count"] == 5000
    assert result["command_count"] == 5000
    assert "hosts" not in result


def test_workflow_cancel_projection_honors_response_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "cancel_workflow",
        lambda workflow_id: {
            "ok": True,
            "workflow_id": workflow_id,
            "status": "cancelled",
            "steps": [
                {"id": str(index), "summary": "s" * 20_000, "error": "e" * 20_000}
                for index in range(5000)
            ],
        },
    )
    request = TypeAdapter(WorkflowActionRequest).validate_python(
        {"action": "cancel", "workflow_id": "wf_1", "response_budget_bytes": 4096}
    )
    result = server.workflow_action(request)
    assert result["response_bytes"] <= 4096
    assert result["truncated"] is True
    assert result["has_more"] is True



def test_phase7_system_and_knowledge_models_are_strict() -> None:
    self_check = TypeAdapter(SystemQueryRequest).validate_python(
        {"operation": "self_check"}
    )
    assert self_check.response_budget_bytes == 12 * 1024
    for operation in ("capabilities", "local_model_health", "validate_config", "reload_status"):
        assert TypeAdapter(SystemQueryRequest).validate_python(
            {"operation": operation}
        ).response_budget_bytes == 12 * 1024
    assert TypeAdapter(SystemQueryRequest).validate_python(
        {"operation": "reload_status"}
    ).operation == "reload_status"
    assert TypeAdapter(SystemActionRequest).validate_python(
        {"action": "reload", "modules": ["config"]}
    ).modules == ["config"]
    assert TypeAdapter(SystemActionRequest).validate_python(
        {"action": "rollback"}
    ).response_budget_bytes == 12 * 1024
    knowledge_search = TypeAdapter(KnowledgeQueryRequest).validate_python(
        {"operation": "search", "repo_name": "repo", "query": "locks"}
    )
    assert knowledge_search.query == "locks"
    assert knowledge_search.view == "compact"
    assert knowledge_search.response_budget_bytes == 12 * 1024
    assert TypeAdapter(KnowledgeQueryRequest).validate_python(
        {
            "operation": "search",
            "repo_name": "repo",
            "query": "locks",
            "view": "full",
        }
    ).view == "full"
    wiki_query = TypeAdapter(KnowledgeQueryRequest).validate_python(
        {"operation": "read_wiki", "repo_name": "repo"}
    )
    assert wiki_query.response_budget_bytes == 12 * 1024
    assert TypeAdapter(KnowledgeActionRequest).validate_python(
        {"action": "remember_decision", "repo_name": "repo", "decision": "use locks"}
    ).decision == "use locks"
    assert TypeAdapter(KnowledgeActionRequest).validate_python(
        {"action": "refresh_wiki", "repo_name": "repo"}
    ).response_budget_bytes == 12 * 1024
    with pytest.raises(ValidationError):
        TypeAdapter(SystemActionRequest).validate_python(
            {"action": "rollback", "modules": ["config"]}
        )
    with pytest.raises(ValidationError):
        TypeAdapter(KnowledgeQueryRequest).validate_python(
            {"operation": "read_wiki", "repo_name": "repo", "query": "wrong"}
        )


def test_system_scalar_queries_use_bounded_compact_projection(monkeypatch) -> None:
    monkeypatch.setattr(
        server,
        "list_capabilities",
        lambda: {
            "ok": True,
            "capability_epoch": "epoch-1",
            "tools": [{"name": f"tool-{index}"} for index in range(5000)],
            "diagnostic": "x" * 20_000,
        },
    )
    result = server.system_query(
        TypeAdapter(SystemQueryRequest).validate_python(
            {"operation": "capabilities", "response_budget_bytes": 4096}
        )
    )
    assert result["tools_count"] == 5000
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["response_bytes"] <= 4096
    full = server.system_query(
        TypeAdapter(SystemQueryRequest).validate_python(
            {"operation": "capabilities", "view": "full"}
        )
    )
    assert len(full["tools"]) == 5000
