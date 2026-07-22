from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from pydantic import TypeAdapter

import soma.server as server
from soma.config import AppConfig, RepoConfig, resolve_repo
from soma.gateway_models import RepoQueryRequest
from soma.knowledge_tools_integration import _active_server_config


class FakeMCP:
    pass


def init_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)


def test_active_server_config_refreshes_cached_config(
    tmp_path: Path, monkeypatch
) -> None:
    first = AppConfig(
        repos={"first": RepoConfig(path=str(tmp_path / "first"))}
    )
    second = AppConfig(
        repos={"second": RepoConfig(path=str(tmp_path / "second"))}
    )
    active = {"config": first}
    mcp = FakeMCP()
    runtime_module = ModuleType("soma_test_reloaded_server")
    runtime_module.mcp = mcp
    runtime_module.get_config = lambda: active["config"]
    monkeypatch.setitem(sys.modules, runtime_module.__name__, runtime_module)

    assert _active_server_config(mcp) is first

    active["config"] = second

    assert _active_server_config(mcp) is second
    assert getattr(mcp, "_soma_runtime_config") is second


def test_resolve_repo_rejects_nested_path_without_independent_git_root(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    init_repo(parent)
    child = parent / "child"
    child.mkdir()
    (child / ".git").mkdir()
    config = AppConfig(
        repos={
            "parent": RepoConfig(path=str(parent)),
            "child": RepoConfig(path=str(child)),
        },
        config_dir=tmp_path,
    )

    with pytest.raises(ValueError, match="not an independent Git repository"):
        resolve_repo(config, "child")


def test_resolve_repo_allows_independent_nested_git_root(tmp_path: Path) -> None:
    parent = tmp_path / "parent"
    init_repo(parent)
    child = parent / "child"
    init_repo(child)
    config = AppConfig(
        repos={
            "parent": RepoConfig(path=str(parent)),
            "child": RepoConfig(path=str(child)),
        },
        config_dir=tmp_path,
    )

    assert resolve_repo(config, "child") == child.resolve()


def test_repo_query_returns_structured_error_for_invalid_resolution(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    init_repo(parent)
    child = parent / "child"
    child.mkdir()
    (child / ".git").mkdir()
    server.set_config(
        AppConfig(
            repos={
                "parent": RepoConfig(path=str(parent)),
                "child": RepoConfig(path=str(child)),
            },
            config_dir=tmp_path,
        ),
        tmp_path / "config.yaml",
    )

    request = TypeAdapter(RepoQueryRequest).validate_python(
        {"operation": "list_files", "repo_name": "child"}
    )
    result = server.repo_query(request)

    assert result["ok"] is False
    assert result["status"] == "invalid_repo_resolution"
    assert "not an independent Git repository" in result["error"]


def test_repository_scoped_reads_ignore_cwd(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / "expected.md").write_text("expected repository content\n", encoding="utf-8")
    other = tmp_path / "other"
    other.mkdir()
    (other / "wrong.md").write_text("wrong cwd content\n", encoding="utf-8")
    server.set_config(
        AppConfig(repos={"repo": RepoConfig(path=str(repo))}, config_dir=tmp_path),
        tmp_path / "config.yaml",
    )

    monkeypatch.chdir(other)
    listing = server.list_repo_files("repo")
    read = server.read_repo_file("repo", "expected.md")

    assert listing["files"] == ["expected.md"]
    assert read["ok"] is True
    assert "expected repository content" in read["content"]
    assert "wrong.md" not in listing["files"]


def test_explicit_repositories_do_not_cross_resolve(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    init_repo(first)
    init_repo(second)
    (first / "first.md").write_text("first\n", encoding="utf-8")
    (second / "second.md").write_text("second\n", encoding="utf-8")
    config = AppConfig(
        repos={
            "wan2gp": RepoConfig(path=str(first)),
            "wan2_2": RepoConfig(path=str(second)),
        },
        config_dir=tmp_path,
    )

    assert resolve_repo(config, "wan2gp") == first.resolve()
    assert resolve_repo(config, "wan2_2") == second.resolve()
