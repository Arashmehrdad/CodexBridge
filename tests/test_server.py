from __future__ import annotations

from contextlib import nullcontext

from codexbridge.config import AppConfig, RepoConfig
from codexbridge.git_tools import CommitMetadataError
from codexbridge.server import parse_args
import codexbridge.server as server


def test_server_cli_defaults_to_http_mcp_path() -> None:
    args = parse_args([])
    assert args.transport == "http"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.path == "/mcp"


def test_server_cli_supports_explicit_mcp_command() -> None:
    args = parse_args(
        [
            "--config",
            "config.yaml",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--path",
            "/mcp",
        ]
    )
    assert args.config == "config.yaml"
    assert args.transport == "http"
    assert args.host == "127.0.0.1"
    assert args.port == 8000
    assert args.path == "/mcp"


def test_server_cli_preserves_stdio_mode() -> None:
    args = parse_args(["--transport", "stdio"])
    assert args.transport == "stdio"


class FakeSupervisorService:
    def start_supervised_recovery_task(self, *args):
        return {"tool": "start", "args": args}

    def get_status(self, supervisor_id):
        return {"tool": "status", "supervisor_id": supervisor_id}

    def get_events(self, supervisor_id, limit):
        return [{"tool": "events", "limit": limit}]

    def get_result(self, supervisor_id):
        return {"tool": "result"}

    def resume(self, supervisor_id):
        return {"tool": "resume"}

    def pause(self, supervisor_id):
        return {"tool": "pause"}

    def cancel(self, supervisor_id):
        return {"tool": "cancel"}

    def get_notifications(self, supervisor_id, delivery_status, limit):
        return [
            {
                "tool": "notifications",
                "delivery_status": delivery_status,
                "limit": limit,
            }
        ]

    def get_resume_prompt(self, supervisor_id):
        return {"tool": "prompt"}


def test_server_supervisor_tool_functions_delegate(monkeypatch) -> None:
    monkeypatch.setattr(
        server, "get_supervisor_service", lambda: FakeSupervisorService()
    )
    supervisor_id = "20260428T120000Z_supervisor_abcdef12"
    assert (
        server.start_supervised_recovery_task("repo", "objective", "task")["tool"]
        == "start"
    )
    assert server.get_supervisor_status(supervisor_id)["tool"] == "status"
    assert server.get_supervisor_events(supervisor_id, 5)["events"][0]["limit"] == 5
    assert server.get_supervisor_result(supervisor_id)["tool"] == "result"
    assert server.resume_supervisor(supervisor_id)["tool"] == "resume"
    assert server.pause_supervisor(supervisor_id)["tool"] == "pause"
    assert server.cancel_supervisor(supervisor_id)["tool"] == "cancel"
    assert (
        server.get_supervisor_notifications(supervisor_id, "pending", 3)[
            "notifications"
        ][0]["delivery_status"]
        == "pending"
    )
    assert server.get_supervisor_resume_prompt(supervisor_id)["tool"] == "prompt"


def test_commit_tool_returns_structured_metadata_rejection(
    monkeypatch,
    tmp_path,
) -> None:
    config = AppConfig(repos={"repo": RepoConfig(path=str(tmp_path))})
    config.config_dir = tmp_path
    monkeypatch.setattr(server, "get_config", lambda: config)
    monkeypatch.setattr(
        server,
        "_repo_context",
        lambda _repo_name: ("repo", tmp_path, "repo"),
    )
    monkeypatch.setattr(
        server,
        "repository_operation_lock",
        lambda *_args, **_kwargs: nullcontext(),
    )

    def reject_metadata(*_args, **_kwargs):
        raise CommitMetadataError(
            "description",
            "too_long",
            "Commit description exceeds the configured limit",
            files_validated=True,
        )

    monkeypatch.setattr(server, "commit_files", reject_metadata)

    result = server.commit_selected_files(
        "repo",
        ["safe.txt"],
        "fix: metadata handling",
        "ordinary description",
    )

    expected = {
        "ok": False,
        "repo_name": "repo",
        "files_validated": True,
        "blocked_field": "description",
        "reason_code": "too_long",
        "reason": "Commit description exceeds the configured limit",
        "error": "Commit description exceeds the configured limit",
    }
    assert {key: result[key] for key in expected} == expected
    assert len(result["server_build_hash"]) == 64
    assert len(result["schema_hash"]) == 64
    assert result["capability_epoch"]


def test_reload_service_delegates_and_refreshes_config(monkeypatch, tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("repos: {}\n", encoding="utf-8")
    refreshed = {"done": False}

    monkeypatch.setattr(server, "get_config_path", lambda: config_path)
    monkeypatch.setattr(
        server,
        "_reload_service",
        lambda *_args, **_kwargs: {
            "ok": True,
            "reloaded": ["config"],
            "requested_modules": ["config"],
            "resolved_modules": [],
            "restart_required": [],
            "message": "",
        },
    )
    monkeypatch.setattr(
        server,
        "apply_reloaded_config",
        lambda path: refreshed.update(done=path == config_path) or object(),
    )
    monkeypatch.setattr(server, "set_config", lambda *_args, **_kwargs: None)

    result = server.reload_service(["config"])

    assert result["ok"] is True
    assert refreshed["done"] is True


def test_repo_context_discovers_direct_child_repo_without_explicit_entry(
    tmp_path,
) -> None:
    root = tmp_path / "Github"
    known = root / "Known"
    known.mkdir(parents=True)
    (known / ".git").mkdir()
    wan_repo = root / "Wan2.2"
    wan_repo.mkdir(parents=True)
    (wan_repo / ".git").mkdir()
    config = AppConfig(
        repos={"known": RepoConfig(path=str(known))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")

    canonical_name, repo_root, requested_name = server._repo_context("Wan2.2")

    assert canonical_name == "wan2_2"
    assert repo_root == wan_repo.resolve()
    assert requested_name == "Wan2.2"


def test_run_project_command_accepts_case_insensitive_repo_name(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={
            "codexbridge": RepoConfig(
                path=str(tmp_path),
                command_profiles=[
                    {"command_id": "custom", "argv": ["python", "-c", "print(1)"]}
                ],
            )
        },
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "run_command_profile",
        lambda profile, repo_root: {
            "ok": True,
            "command_id": profile.command_id,
            "argv": list(profile.argv),
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": "",
            "stderr": "",
            "output_truncated": False,
            "error": "",
        },
    )

    result = server.run_project_command("CodexBridge", "custom")

    assert result["ok"] is True
    assert result["repo_name"] == "codexbridge"
    assert result["requested_repo_name"] == "CodexBridge"


def test_preview_tools_preserve_canonical_repo_name(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"codexbridge": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_repo_writer",
        type(
            "Writer",
            (),
            {
                "preview_repo_patch": staticmethod(
                    lambda repo_root, operations, runs_dir: {
                        "ok": True,
                        "patch_id": "patch_1",
                        "diff": "",
                        "changed_files": [],
                        "changed_lines": 0,
                        "changed_bytes": 0,
                        "git_head": "",
                        "validation_errors": [],
                        "error": "",
                    }
                )
            },
        ),
    )

    result = server.preview_repo_patch("CodexBridge", [])

    assert result["repo_name"] == "codexbridge"
    assert result["requested_repo_name"] == "CodexBridge"


def test_dry_run_stage_manifest_accepts_include_ignored(monkeypatch, tmp_path) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        server,
        "_dry_run_stage_manifest",
        lambda repo_root, include_ignored=False: captured.setdefault(
            "value",
            {
                "ok": True,
                "staged": [],
                "unstaged": [],
                "untracked": [],
                "deleted": [],
                "ignored": [".codexbridge/wiki/overview.md"] if include_ignored else [],
                "renamed": [],
                "tool_owned": [],
                "files": [],
                "git_status": "",
            },
        ),
    )

    result = server.dry_run_stage_manifest("repo", include_ignored=True)

    assert result["ignored"] == [".codexbridge/wiki/overview.md"]


def test_inspect_commit_range_uses_canonical_repo_context(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"codexbridge": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_inspect_commit_range",
        lambda repo_root, base_commit, head_commit: {
            "ok": True,
            "base_commit": base_commit,
            "head_commit": head_commit,
            "name_status": "M\tREADME.md\n",
            "diff_stat": " README.md | 1 +\n",
            "diff": "diff --git a/README.md b/README.md\n",
            "truncated": False,
            "error": "",
        },
    )

    result = server.inspect_commit_range("CodexBridge", "a" * 40, "b" * 40)

    assert result["repo_name"] == "codexbridge"
    assert result["requested_repo_name"] == "CodexBridge"


def test_inspect_repo_status_compact_normalizes_live_git_shapes(
    monkeypatch, tmp_path
) -> None:
    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"repo": RepoConfig(path=str(tmp_path))}, config_dir=tmp_path
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "inspect_status_compact",
        lambda repo_root: {
            "branch": "main",
            "recent_commits": "abc123 first\n\ndef456 second\n",
            "diff_stat": " 1 file changed\n",
            "complete_status_scan": True,
            "total_status_entry_count": 2,
            "returned_entry_count": 1,
            "collapsed_tool_owned_count": 1,
            "sampled_tool_owned_count": 1,
            "unsampled_tool_owned_count": 0,
            "files": [
                {
                    "path": "codexbridge/server.py",
                    "size_bytes": 1,
                    "line_count": 1,
                    "tool_owned": False,
                    "index_status": "M",
                    "worktree_status": " ",
                }
            ],
            "tool_owned_summary": {
                "total_bytes": 3,
                "root_group_counts": {".codex-tmp": 1},
                "sample": [
                    {
                        "path": ".codex-tmp/run.txt",
                        "size_bytes": 3,
                        "line_count": 1,
                        "tool_owned": True,
                        "index_status": "?",
                        "worktree_status": "?",
                    }
                ],
                "truncated": False,
            },
            "fallback_tool": "inspect_repo_status",
        },
    )

    result = server.inspect_repo_status_compact("repo")

    assert result["recent_commits"] == ["abc123 first", "def456 second"]
    assert "changed_files" not in result
    assert "git_status" not in result
    assert result["tool_owned_summary"]["sample"][0]["path"] == ".codex-tmp/run.txt"


def test_repo_status_compact_schema_uses_new_compact_fields() -> None:
    properties = server.REPO_STATUS_COMPACT_OUTPUT["properties"]

    assert "changed_files" not in properties
    assert "complete_status_scan" in properties
    assert "total_status_entry_count" in properties
    assert "returned_entry_count" in properties
    assert "collapsed_tool_owned_count" in properties
    assert "sampled_tool_owned_count" in properties
    assert "unsampled_tool_owned_count" in properties
    assert "complete_scan" not in properties
    assert "omitted_tool_owned_count" not in properties

    summary_properties = properties["tool_owned_summary"]["properties"]
    assert "count" not in summary_properties
    assert "total_known_line_count" not in summary_properties
