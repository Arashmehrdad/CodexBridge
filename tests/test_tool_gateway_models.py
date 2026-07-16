from hashlib import sha256

from pydantic import TypeAdapter, ValidationError
import pytest

from codexbridge.gateway_models import (
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
    WorkflowActionRequest,
    WorkflowQueryRequest,
)
import codexbridge.server as server


def test_ssh_inspection_models_are_discriminated_and_strict() -> None:
    adapter = TypeAdapter(SSHInspectRequest)
    assert adapter.validate_python({"operation": "host_health", "host_id": "dev"}).host_id == "dev"
    try:
        adapter.validate_python({"operation": "gpu_telemetry", "host_id": "dev", "tail": 10})
    except ValidationError:
        pass
    else:
        raise AssertionError("cross-operation field must be rejected")


def test_gateway_model_requires_operation_specific_fields() -> None:
    adapter = TypeAdapter(RunQueryRequest)
    assert adapter.validate_python({"operation": "events", "run_id": "run_1"}).limit == 50
    assert adapter.validate_python(
        {"operation": "group_status", "group_id": "group_1"}
    ).group_id == "group_1"
    assert adapter.validate_python(
        {"operation": "group_result", "group_id": "group_1"}
    ).group_id == "group_1"
    for payload in (
        {"operation": "events"},
        {"operation": "events", "run_id": "run_1", "stream": "stdout"},
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


def test_workflow_and_supervisor_models_are_operation_specific() -> None:
    workflow_query = TypeAdapter(WorkflowQueryRequest)
    workflow_action = TypeAdapter(WorkflowActionRequest)
    supervisor_query = TypeAdapter(SupervisorQueryRequest)
    supervisor_action = TypeAdapter(SupervisorActionRequest)

    assert workflow_query.validate_python({"operation": "events", "workflow_id": "wf_1"}).limit == 100
    assert workflow_action.validate_python(
        {"action": "start", "repo_name": "repo", "objective": "ship", "steps": [{"id": "one"}]}
    ).repo_name == "repo"
    assert supervisor_query.validate_python(
        {"operation": "notifications", "supervisor_id": "sup_1"}
    ).limit == 50
    assert supervisor_action.validate_python(
        {"action": "pause", "supervisor_id": "sup_1"}
    ).supervisor_id == "sup_1"

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
    monkeypatch.setattr(server, "_repo_context", lambda _repo_name: None)
    monkeypatch.setattr(server, "search_repo_text", lambda *args: {"operation": "search", "args": args})
    monkeypatch.setattr(server, "preview_repo_file_removal", lambda *args: {"operation": "remove", "args": args})
    monkeypatch.setattr(server, "apply_previewed_repo_change", lambda *args: {"operation": "apply", "args": args})
    monkeypatch.setattr(server, "commit_selected_files", lambda *args: {"operation": "commit", "args": args})

    assert server.repo_query(TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "search_text", "repo_name": "repo", "query": "needle"}
    ))["operation"] == "search"
    assert server.repo_preview(TypeAdapter(RepoPreviewRequest).validate_python(
        {"operation": "remove_file", "repo_name": "repo", "path": "x", "expected_sha256": "a" * 64}
    ))["operation"] == "remove"
    assert server.repo_apply(TypeAdapter(RepoApplyRequest).validate_python(
        {"operation": "previewed_change", "repo_name": "repo", "patch_id": "patch_1"}
    ))["operation"] == "apply"
    assert server.repo_commit(TypeAdapter(RepoCommitRequest).validate_python(
        {"operation": "commit_selected", "repo_name": "repo", "files": ["x"], "title": "fix: x"}
    ))["operation"] == "commit"


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


def test_run_start_models_reject_cross_operation_fields() -> None:
    adapter = TypeAdapter(RunStartRequest)
    assert adapter.validate_python(
        {"operation": "project_command", "repo_name": "repo", "command_id": "pytest"}
    ).command_id == "pytest"
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
        {"operation": "project_command", "repo_name": "repo", "command_id": "pytest", "path": "x"},
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
        ({"operation": "project_command", "repo_name": "repo", "command_id": "pytest"}, "start_project_command"),
        ({"operation": "pytest_path", "repo_name": "repo", "path": "tests"}, "start_pytest_path"),
        ({"operation": "py_compile_path", "repo_name": "repo", "path": "x.py"}, "start_py_compile_path"),
        ({"operation": "bash_syntax_path", "repo_name": "repo", "path": "x.sh"}, "start_bash_n_path"),
        ({"operation": "json_validation_path", "repo_name": "repo", "path": "x.json"}, "start_json_validation_path"),
        ({"operation": "git_readonly", "repo_name": "repo", "git_operation": "status"}, "start_git_readonly"),
        ({"operation": "external_fixture_validation", "repo_name": "repo", "url": "https://example.test/x", "expected_sha256": "a" * 64}, "start_external_fixture_validation"),
        ({"operation": "powershell", "repo_name": "repo", "argv": ["-Command", "git status"], "environment": {"X": "a b"}, "stdin_base64": "AAE=", "timeout_seconds": 60}, "start_executable_profile"),
        ({"operation": "powershell_group", "repo_name": "repo", "requested_concurrency": 2, "children": [{"idempotency_key": "one", "argv": ["-Command", "one"], "stdin_base64": "AAE="}]}, "start_powershell_group"),
    ):
        server.run_start(TypeAdapter(RunStartRequest).validate_python(payload))
        assert calls[-1][0] == expected
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


def test_phase7_system_and_knowledge_models_are_strict() -> None:
    assert TypeAdapter(SystemQueryRequest).validate_python(
        {"operation": "reload_status"}
    ).operation == "reload_status"
    assert TypeAdapter(SystemActionRequest).validate_python(
        {"action": "reload", "modules": ["config"]}
    ).modules == ["config"]
    assert TypeAdapter(KnowledgeQueryRequest).validate_python(
        {"operation": "search", "repo_name": "repo", "query": "locks"}
    ).query == "locks"
    assert TypeAdapter(KnowledgeActionRequest).validate_python(
        {"action": "remember_decision", "repo_name": "repo", "decision": "use locks"}
    ).decision == "use locks"
    with pytest.raises(ValidationError):
        TypeAdapter(SystemActionRequest).validate_python(
            {"action": "rollback", "modules": ["config"]}
        )
    with pytest.raises(ValidationError):
        TypeAdapter(KnowledgeQueryRequest).validate_python(
            {"operation": "read_wiki", "repo_name": "repo", "query": "wrong"}
        )
