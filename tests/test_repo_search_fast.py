from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

from soma import repo_reader, server
from soma.config import AppConfig, RepoConfig
from soma.gateway_models import RepoQueryRequest
from soma.repo_reader import search_repo_fast


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _git(repo, "init", "-q").returncode == 0
    assert _git(repo, "config", "user.name", "Soma Test").returncode == 0
    assert _git(repo, "config", "user.email", "soma@example.test").returncode == 0
    for relative, text in files.items():
        _write(repo / relative, text)
    assert _git(repo, "add", "--all").returncode == 0
    assert _git(repo, "commit", "-q", "-m", "fixture").returncode == 0
    return repo


def _head(repo: Path) -> str:
    result = _git(repo, "rev-parse", "HEAD")
    assert result.returncode == 0
    return result.stdout.strip()


def test_fast_tracked_literal_excludes_untracked_and_blocked_paths(tmp_path: Path) -> None:
    repo = _make_repo(
        tmp_path,
        {
            "src/a.py": "Needle here\n",
            "src/b.py": "nothing\n",
            "secrets/key.txt": "needle must not escape\n",
        },
    )
    _write(repo / "src" / "untracked.py", "needle from untracked file\n")

    result = search_repo_fast(repo, "needle")

    assert result["ok"] is True
    assert result["scope"] == "tracked"
    assert result["engine"] == "git-grep"
    assert result["navigation_only"] is True
    assert result["git_head"] == _head(repo)
    assert [hit["path"] for hit in result["hits"]] == ["src/a.py"]
    assert "untracked.py" not in json.dumps(result)
    assert "secrets/key.txt" not in json.dumps(result)


def test_fast_search_regex_case_directory_and_glob_are_deterministic(tmp_path: Path) -> None:
    repo = _make_repo(
        tmp_path,
        {
            "src/a.py": "Alpha_123\n",
            "src/b.txt": "Alpha_456\n",
            "other/c.py": "Alpha_789\n",
        },
    )

    result = search_repo_fast(
        repo,
        r"Alpha_[0-9]+",
        match_mode="regex",
        case_sensitive=True,
        directory="src",
        file_patterns=["*.py"],
    )

    assert result["ok"] is True
    assert [(hit["path"], hit["line"]) for hit in result["hits"]] == [("src/a.py", 1)]
    assert result["files_matched"] == 1

    case_miss = search_repo_fast(
        repo,
        "alpha_123",
        case_sensitive=True,
        directory="src",
        file_patterns=["*.py"],
    )
    assert case_miss["count"] == 0


def test_fast_search_files_and_count_modes_report_exact_totals(tmp_path: Path) -> None:
    repo = _make_repo(
        tmp_path,
        {
            "a.py": "needle\nneedle\n",
            "b.py": "needle\n",
            "c.py": "other\n",
        },
    )

    counted = search_repo_fast(repo, "needle", result_mode="count")
    assert counted["count"] == 3
    assert counted["match_count"] == 3
    assert counted["files_matched"] == 2
    assert counted["files"] == []
    assert counted["hits"] == []

    files = search_repo_fast(repo, "needle", result_mode="files")
    assert files["files"] == ["a.py", "b.py"]
    assert files["count"] == 2
    assert files["match_count"] == 3
    assert files["files_matched"] == 2


def test_fast_search_truncation_context_and_column(tmp_path: Path) -> None:
    repo = _make_repo(
        tmp_path,
        {
            "a.py": "before\nneedle one\nmiddle\nneedle two\nafter\nneedle three\n",
        },
    )

    result = search_repo_fast(repo, "needle", max_results=2, context_lines=1)

    assert result["ok"] is True
    assert result["count"] == 2
    assert result["truncated"] is True
    assert result["has_more"] is True
    assert result["truncation_reason"] == "max_results"
    assert result["match_count_complete"] is False
    assert all(int(hit["column"]) >= 1 for hit in result["hits"])
    assert result["hits"][0]["context"] == [
        {"line": 1, "text": "before"},
        {"line": 2, "text": "needle one"},
        {"line": 3, "text": "middle"},
    ]


def test_fast_search_response_budget_is_hard_bounded(tmp_path: Path) -> None:
    repo = _make_repo(
        tmp_path,
        {
            "large.py": "".join(f"needle {'x' * 500} {index}\n" for index in range(40)),
        },
    )

    result = search_repo_fast(
        repo,
        "needle",
        max_results=40,
        context_lines=1,
        response_budget_bytes=4096,
    )

    assert result["response_bytes"] <= 4096
    assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 4096
    assert result["truncated"] is True
    assert result["truncation_reason"] == "response_budget"


def test_fast_search_reads_dirty_tracked_content_without_mutating_git_state(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"tracked.py": "old value\n"})
    _write(repo / "tracked.py", "new needle value\n")
    before = _git(repo, "status", "--porcelain=v1").stdout

    result = search_repo_fast(repo, "needle")

    after = _git(repo, "status", "--porcelain=v1").stdout
    assert result["count"] == 1
    assert result["hits"][0]["path"] == "tracked.py"
    assert before == after


def test_fast_search_supports_spaces_and_unicode_paths(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"src/space café.py": "needle\n"})

    result = search_repo_fast(repo, "needle")

    assert result["count"] == 1
    assert result["hits"][0]["path"] == "src/space café.py"


def test_fast_search_non_git_repo_is_structured(tmp_path: Path) -> None:
    _write(tmp_path / "a.py", "needle\n")

    result = search_repo_fast(tmp_path, "needle")

    assert result["ok"] is False
    assert result["status"] == "not_git_repository"
    assert result["fresh"] is False
    assert result["hits"] == []


def test_fast_search_reads_packed_head_without_identity_subprocess(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"module.py": "needle\n"})
    symbolic = _git(repo, "symbolic-ref", "HEAD")
    assert symbolic.returncode == 0
    reference = symbolic.stdout.strip()
    assert _git(repo, "pack-refs", "--all", "--prune").returncode == 0
    assert not (repo / ".git" / Path(*reference.split("/"))).exists()

    result = search_repo_fast(repo, "needle")

    assert result["ok"] is True
    assert result["git_head"] == _head(repo)
    assert result["hits"][0]["path"] == "module.py"


def test_fast_search_supports_linked_worktree_git_marker(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"module.py": "needle\n"})
    linked = tmp_path / "linked-worktree"
    added = _git(repo, "worktree", "add", "--detach", str(linked), "HEAD")
    assert added.returncode == 0, added.stderr
    assert (linked / ".git").is_file()

    result = search_repo_fast(linked, "needle")

    assert result["ok"] is True
    assert result["git_head"] == _head(linked)
    assert result["hits"][0]["path"] == "module.py"


def test_fast_search_timeout_is_end_to_end_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path, {"module.py": "needle\n"})

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(["git", "grep"], 0.1)

    monkeypatch.setattr(repo_reader, "_run_fast_git", timeout)

    result = search_repo_fast(repo, "needle", budget_ms=100)

    assert result["ok"] is False
    assert result["status"] == "search_timeout"
    assert result["timeout"] is True
    assert result["fresh"] is False
    assert result["truncation_reason"] == "timeout"


def test_fast_search_never_walks_or_hashes_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path, {"module.py": "needle\n"})

    def forbidden(*args, **kwargs):
        raise AssertionError("fast search must not recursively walk or hash the corpus")

    monkeypatch.setattr(repo_reader.os, "walk", forbidden)
    monkeypatch.setattr(repo_reader, "_sha256_file", forbidden)

    result = search_repo_fast(repo, "needle")

    assert result["ok"] is True
    assert result["count"] == 1


def test_fast_working_tree_includes_untracked_and_excludes_ignored_heavy_roots(
    tmp_path: Path,
) -> None:
    repo = _make_repo(
        tmp_path,
        {
            ".gitignore": "ignored.py\n",
            "tracked.py": "needle tracked\n",
        },
    )
    _write(repo / "untracked.py", "needle untracked\n")
    _write(repo / "ignored.py", "needle ignored\n")
    _write(repo / "data" / "heavy.txt", "needle heavy\n")

    result = search_repo_fast(repo, "needle", scope="working_tree")

    assert result["ok"] is True
    assert result["engine"] == "ripgrep"
    assert [hit["path"] for hit in result["hits"]] == ["tracked.py", "untracked.py"]
    rendered = json.dumps(result)
    assert "ignored.py" not in rendered
    assert "data/heavy.txt" not in rendered
    assert "data" in result["excluded_roots"]


def test_fast_all_includes_ignored_safe_file_but_excludes_heavy_and_secret_roots(
    tmp_path: Path,
) -> None:
    repo = _make_repo(
        tmp_path,
        {
            ".gitignore": "ignored.py\n",
            "tracked.py": "needle tracked\n",
        },
    )
    _write(repo / "ignored.py", "needle ignored\n")
    _write(repo / "data" / "heavy.txt", "needle heavy\n")
    _write(repo / "secrets" / "private.txt", "needle secret\n")

    result = search_repo_fast(repo, "needle", scope="all")

    assert result["ok"] is True
    paths = [hit["path"] for hit in result["hits"]]
    assert paths == ["ignored.py", "tracked.py"]
    rendered = json.dumps(result)
    assert "data/heavy.txt" not in rendered
    assert "secrets/private.txt" not in rendered


def test_fast_directory_scope_searches_explicit_ignored_safe_subtree(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {".gitignore": "scratch/\n", "tracked.py": "other\n"})
    _write(repo / "scratch" / "note.txt", "needle explicit directory\n")

    result = search_repo_fast(repo, "needle", scope="directory", directory="scratch")

    assert result["ok"] is True
    assert result["engine"] == "ripgrep"
    assert [hit["path"] for hit in result["hits"]] == ["scratch/note.txt"]

    with pytest.raises(ValueError):
        search_repo_fast(repo, "needle", scope="directory")
    with pytest.raises(ValueError):
        search_repo_fast(repo, "needle", scope="directory", directory="../outside")


def test_fast_working_tree_files_and_count_modes_are_exact(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"a.py": "needle\nneedle\n"})
    _write(repo / "b.py", "needle\n")

    counted = search_repo_fast(repo, "needle", scope="working_tree", result_mode="count")
    files = search_repo_fast(repo, "needle", scope="working_tree", result_mode="files")

    assert counted["ok"] is True
    assert counted["count"] == 3
    assert counted["match_count"] == 3
    assert counted["files_matched"] == 2
    assert files["files"] == ["a.py", "b.py"]
    assert files["count"] == 2
    assert files["files_matched"] == 2


def test_fast_rg_timeout_and_unavailable_are_structured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _make_repo(tmp_path, {"module.py": "needle\n"})

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(["rg"], 0.1)

    monkeypatch.setattr(repo_reader, "_run_fast_rg", timeout)
    timed = search_repo_fast(repo, "needle", scope="working_tree", budget_ms=100)
    assert timed["ok"] is False
    assert timed["status"] == "search_timeout"
    assert timed["timeout"] is True

    monkeypatch.undo()
    monkeypatch.setattr(repo_reader, "_fast_rg_executable", lambda: "")
    unavailable = search_repo_fast(repo, "needle", scope="working_tree")
    assert unavailable["ok"] is False
    assert unavailable["status"] == "rg_unavailable"


def test_fast_rg_discovery_uses_bounded_vscode_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(repo_reader.shutil, "which", lambda _name: None)
    local = tmp_path / "local"
    candidate = (
        local
        / "Programs"
        / "Microsoft VS Code"
        / "versioned"
        / "resources"
        / "app"
        / "node_modules.asar.unpacked"
        / "@vscode"
        / "ripgrep-universal"
        / "bin"
        / "win32-x64"
        / "rg.exe"
    )
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(b"fixture")
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.delenv("ProgramFiles", raising=False)
    monkeypatch.delenv("ProgramFiles(x86)", raising=False)

    assert repo_reader._fast_rg_executable() == str(candidate)


def test_fast_search_scope_and_gateway_model_are_strict() -> None:
    adapter = TypeAdapter(RepoQueryRequest)
    request = adapter.validate_python(
        {
            "operation": "search_fast",
            "repo_name": "repo",
            "query": "needle",
        }
    )
    assert request.scope == "tracked"
    assert request.match_mode == "literal"
    assert request.max_results == 100
    assert request.result_mode == "matches"
    assert request.context_lines == 0
    assert request.response_budget_bytes == 16 * 1024

    assert adapter.validate_python(
        {
            "operation": "search_fast",
            "repo_name": "repo",
            "query": "needle",
            "scope": "working_tree",
        }
    ).scope == "working_tree"
    assert adapter.validate_python(
        {
            "operation": "search_fast",
            "repo_name": "repo",
            "query": "needle",
            "scope": "all",
        }
    ).scope == "all"
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "operation": "search_fast",
                "repo_name": "repo",
                "query": "needle",
                "scope": "directory",
            }
        )
    assert adapter.validate_python(
        {
            "operation": "search_fast",
            "repo_name": "repo",
            "query": "needle",
            "scope": "directory",
            "directory": "src",
        }
    ).directory == "src"
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {
                "operation": "search_fast",
                "repo_name": "repo",
                "query": "needle",
                "context_lines": 6,
            }
        )


def test_repo_query_dispatches_fast_search_without_new_public_tool(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"module.py": "needle\n"})
    config = AppConfig(
        repos={"fixture": RepoConfig(path=str(repo))},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    request = TypeAdapter(RepoQueryRequest).validate_python(
        {
            "operation": "search_fast",
            "repo_name": "fixture",
            "query": "needle",
        }
    )

    result = server.repo_query(request)

    assert result["ok"] is True
    assert result["repo_name"] == "fixture"
    assert result["hits"][0]["path"] == "module.py"
    assert result["engine"] == "git-grep"
