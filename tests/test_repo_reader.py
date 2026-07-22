"""
Tests for codexbridge/repo_reader.py.

All tests use tmp_path; no real repos are touched.
No CodexRunner, Gemini, Ollama, or local-model calls are made.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from codexbridge import repo_reader
from codexbridge.repo_reader import (
    list_repo_files,
    read_repo_file,
    search_repo_text,
    get_recently_modified_files,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repo with a .git marker."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def write(path: Path, content: str = "hello\n") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# resolve_repo / unknown repo (server-level)
# ---------------------------------------------------------------------------


def test_unknown_repo_raises_in_server(tmp_path: Path) -> None:
    """Server calls resolve_repo before reaching repo_reader; confirm it raises."""
    from codexbridge.config import AppConfig, RepoConfig
    import codexbridge.server as server

    config = AppConfig(
        repos={"myrepo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    (tmp_path / ".git").mkdir(exist_ok=True)

    with pytest.raises(ValueError, match="Unknown repo_name"):
        server.list_repo_files("no_such_repo")


# ---------------------------------------------------------------------------
# Path rejection – absolute, UNC, drive, wildcard, traversal
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc/passwd",
        "C:\\Windows\\system32\\cmd.exe",
        "\\\\server\\share\\file.txt",
        "../outside.txt",
        "subdir/../../outside.txt",
        "*.py",
        "subdir/?.txt",
    ],
)
def test_read_repo_file_rejects_bad_paths(tmp_path: Path, bad_path: str) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(ValueError):
        read_repo_file(repo, bad_path)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc",
        "C:\\Windows",
        "../sibling",
        "*.py",
    ],
)
def test_list_repo_files_rejects_bad_directory(tmp_path: Path, bad_path: str) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(ValueError):
        list_repo_files(repo, directory=bad_path)


# ---------------------------------------------------------------------------
# Symlink escape – file symlink
# ---------------------------------------------------------------------------


def test_read_repo_file_rejects_symlink_to_outside(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = repo / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable on this platform")
    with pytest.raises(ValueError):
        read_repo_file(repo, "link.txt")


def test_list_repo_files_skips_symlink_files(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "real.txt", "content")
    outside = tmp_path.parent / "other.txt"
    outside.write_text("other", encoding="utf-8")
    link = repo / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable on this platform")
    result = list_repo_files(repo)
    assert "link.txt" not in result["files"]
    assert "real.txt" in result["files"]


def test_list_repo_files_skips_symlinked_directory(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    outside_dir = tmp_path.parent / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "secret.txt").write_text("s", encoding="utf-8")
    link_dir = repo / "linked_dir"
    try:
        link_dir.symlink_to(outside_dir)
    except OSError:
        pytest.skip("Symlinks unavailable on this platform")
    result = list_repo_files(repo)
    # linked_dir/secret.txt must not appear
    assert not any("secret.txt" in f for f in result["files"])


# ---------------------------------------------------------------------------
# Exclusions – blocked names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "blocked",
    [
        ".git/config",
        ".venv/lib/site.py",
        "venv/bin/python",
        "__pycache__/mod.cpython-311.pyc",
        ".pytest_cache/v/cache.json",
        "node_modules/lodash/index.js",
        "credentials/prod.json",
        "secrets/key.txt",
        "runs/generated.txt",
        ".codex-pytest-temp/pytest.txt",
    ],
)
def test_list_repo_files_excludes_blocked_names(tmp_path: Path, blocked: str) -> None:
    repo = make_repo(tmp_path)
    write(repo / Path(blocked))
    result = list_repo_files(repo)
    assert blocked not in result["files"]
    assert not any(p.startswith(blocked.split("/")[0]) for p in result["files"])


@pytest.mark.parametrize(
    "ext_file",
    ["build.pyc", "module.pyo", "cert.pem", "id_rsa.key", "store.p12", "bundle.pfx"],
)
def test_list_repo_files_excludes_blocked_extensions(
    tmp_path: Path, ext_file: str
) -> None:
    repo = make_repo(tmp_path)
    write(repo / ext_file, "data")
    result = list_repo_files(repo)
    assert ext_file not in result["files"]


# ---------------------------------------------------------------------------
# .env exceptions – only .env.example/.env.sample/.env.template are allowed
# ---------------------------------------------------------------------------


def test_real_env_file_is_excluded(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / ".env", "SECRET=abc")
    result = list_repo_files(repo)
    assert ".env" not in result["files"]


@pytest.mark.parametrize(
    "allowed_env",
    [".env.example", ".env.sample", ".env.template"],
)
def test_allowed_env_templates_are_included(tmp_path: Path, allowed_env: str) -> None:
    repo = make_repo(tmp_path)
    write(repo / allowed_env, "# example")
    result = list_repo_files(repo)
    assert allowed_env in result["files"]


# ---------------------------------------------------------------------------
# Binary file rejection
# ---------------------------------------------------------------------------


def test_read_repo_file_rejects_binary(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    binary = repo / "image.png"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
    with pytest.raises(ValueError, match="Binary"):
        read_repo_file(repo, "image.png")


def test_search_repo_text_skips_binary_files(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "binary.bin").write_bytes(b"\x00\x01\x02hello")
    write(repo / "text.txt", "hello world")
    result = search_repo_text(repo, "hello")
    paths = [h["path"] for h in result["hits"]]
    assert "text.txt" in paths
    assert "binary.bin" not in paths


def test_search_repo_text_supports_targeted_patterns(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "src" / "module.py", "needle\n")
    write(repo / "src" / "notes.txt", "needle\n")
    write(repo / "other.py", "needle\n")

    result = search_repo_text(
        repo,
        "needle",
        directory="src",
        file_patterns=["*.py"],
    )

    assert result["ok"] is True
    assert [hit["path"] for hit in result["hits"]] == ["src/module.py"]


def test_bounded_search_exact_file_continuation_is_snapshot_bound(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "target.txt", "\n".join(f"needle-{index}" for index in range(6)) + "\n")
    write(repo / "sibling.txt", "needle-sibling\n")

    first = search_repo_text(
        repo,
        "needle",
        file_path="target.txt",
        max_results=2,
        response_budget_bytes=4_096,
    )

    assert first["ok"] is True
    assert first["has_more"] is True
    assert first["next_cursor"]
    assert {hit["path"] for hit in first["hits"]} == {"target.txt"}
    assert first["response_bytes"] <= 4_096

    second = search_repo_text(
        repo,
        "needle",
        file_path="target.txt",
        max_results=2,
        cursor=first["next_cursor"],
        response_budget_bytes=4_096,
    )
    assert second["ok"] is True
    assert [hit["line"] for hit in second["hits"]] == [3, 4]

    write(repo / "target.txt", "needle-replaced\n")
    stale = search_repo_text(
        repo,
        "needle",
        file_path="target.txt",
        max_results=2,
        cursor=first["next_cursor"],
        response_budget_bytes=4_096,
    )
    assert stale["ok"] is False
    assert stale["status"] == "stale_content"
    assert stale["fresh"] is False


def test_bounded_search_rejects_tampered_cursor(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "target.txt", "needle\n")
    result = search_repo_text(
        repo, "needle", file_path="target.txt", response_budget_bytes=1_024
    )
    tampered = result["next_cursor"] or "bad.cursor"
    tampered = tampered[:-1] + ("0" if tampered[-1] != "0" else "1")
    invalid = search_repo_text(
        repo,
        "needle",
        file_path="target.txt",
        cursor=tampered,
        response_budget_bytes=1_024,
    )
    assert invalid["ok"] is False
    assert invalid["status"] == "invalid_cursor"


def test_search_repo_text_budget_exhaustion_is_structured(
    tmp_path: Path, monkeypatch
) -> None:
    repo = make_repo(tmp_path)
    write(repo / "module.py", "needle\n")
    monkeypatch.setattr(repo_reader.shutil, "which", lambda _: "rg")

    def timeout(*args, **kwargs):
        raise repo_reader.subprocess.TimeoutExpired(args[0], 0.1)

    monkeypatch.setattr(repo_reader.subprocess, "run", timeout)

    result = search_repo_text(repo, "needle", budget_ms=100)

    assert result["ok"] is False
    assert result["status"] == "interactive_search_budget_exceeded"
    assert result["fresh"] is False
    assert result["partial_results"] == []
    assert "durable" in result["recommended_action"]


# ---------------------------------------------------------------------------
# Oversized file streaming
# ---------------------------------------------------------------------------


def test_read_repo_file_streams_oversized_text(tmp_path: Path, monkeypatch) -> None:
    repo = make_repo(tmp_path)
    big = repo / "big.txt"
    big.write_text("one\ntwo\nthree\n", encoding="utf-8")
    monkeypatch.setattr(repo_reader, "MAX_FILE_BYTES", 5)

    result = read_repo_file(repo, "big.txt", content_budget_bytes=10)

    assert result["ok"] is True
    assert result["content"] == "one\ntwo\n"
    assert result["has_more"] is True
    assert result["next_cursor"]


# ---------------------------------------------------------------------------
# Line-range reading
# ---------------------------------------------------------------------------


def test_read_repo_file_line_range(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "lines.txt", "\n".join(f"line{i}" for i in range(1, 11)) + "\n")
    result = read_repo_file(repo, "lines.txt", start_line=3, end_line=5)
    assert result["content"].strip() == "line3\nline4\nline5"
    assert result["start_line"] == 3
    assert result["end_line"] == 5
    assert result["total_lines"] == 10
    assert result["truncated"] is True


def test_read_repo_file_full_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "full.txt", "a\nb\nc\n")
    result = read_repo_file(repo, "full.txt")
    assert result["content"] == "a\nb\nc\n"
    assert result["truncated"] is False
    assert result["total_lines"] == 3


def test_read_repo_file_start_line_equals_total(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "small.txt", "only\n")
    result = read_repo_file(repo, "small.txt", start_line=1, end_line=1)
    assert "only" in result["content"]


def test_read_repo_file_continuation_reconstructs_large_file(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    expected = "".join(f"line-{index:04d}\n" for index in range(700))
    write(repo / "large.txt", expected)

    parts: list[str] = []
    cursor = ""
    hashes: set[str] = set()
    for _ in range(10):
        result = read_repo_file(
            repo,
            "large.txt",
            continuation=cursor,
            content_budget_bytes=4_096,
        )
        parts.append(result["content"])
        hashes.add(result["content_sha256"])
        cursor = result["next_cursor"]
        if not cursor:
            break

    assert "".join(parts) == expected
    assert len(hashes) == 1
    assert cursor == ""


def test_read_repo_file_supports_byte_continuation(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "bytes.txt", "abcdefghij")

    first = read_repo_file(
        repo, "bytes.txt", start_byte=2, content_budget_bytes=4
    )
    second = read_repo_file(
        repo,
        "bytes.txt",
        continuation=first["next_cursor"],
        content_budget_bytes=4,
    )

    assert first["content"] == "cdef"
    assert first["start_byte"] == 2
    assert first["next_byte_offset"] == 6
    assert second["content"] == "ghij"
    assert second["has_more"] is False


def test_read_repo_file_rejects_stale_continuation(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    path = write(repo / "changing.txt", "first\nsecond\nthird\n")
    first = read_repo_file(
        repo, "changing.txt", content_budget_bytes=6
    )
    path.write_text("changed\ncontent\n", encoding="utf-8")

    stale = read_repo_file(
        repo,
        "changing.txt",
        continuation=first["next_cursor"],
        content_budget_bytes=6,
    )

    assert stale["ok"] is False
    assert stale["status"] == "stale_content"
    assert stale["fresh"] is False
    assert stale["content"] == ""
    assert "restart" in stale["error"].lower()


def test_read_repo_file_rejects_tampered_continuation(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "cursor.txt", "first\nsecond\n")
    first = read_repo_file(repo, "cursor.txt", content_budget_bytes=6)
    cursor = first["next_cursor"]
    tampered = cursor[:-1] + ("0" if cursor[-1] != "0" else "1")

    with pytest.raises(ValueError, match="Invalid file continuation"):
        read_repo_file(repo, "cursor.txt", continuation=tampered)


def test_read_repo_file_bounds_one_very_long_line(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "long-line.txt", "x" * 1_000_000)

    result = read_repo_file(
        repo, "long-line.txt", content_budget_bytes=4_096
    )

    assert len(result["content"].encode("utf-8")) <= 4_096
    assert result["end_byte"] <= 4_096
    assert result["has_more"] is True
    assert result["next_cursor"]


def test_read_repo_files_enforces_serialized_response_budget(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "large.txt", "x" * 100_000)

    result = repo_reader.read_repo_files(
        repo,
        [{"path": "large.txt"}],
        response_budget_bytes=48 * 1024,
    )

    assert len(repo_reader.json.dumps(result).encode("utf-8")) <= 48 * 1024
    assert result["payload_bytes"] <= 48 * 1024
    assert result["response_bytes"] == result["payload_bytes"]
    assert result["has_more"] is True
    assert result["results"][0]["has_more"] is True


# ---------------------------------------------------------------------------
# Search limits and redacted snippets
# ---------------------------------------------------------------------------


def test_search_repo_text_respects_max_results(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    # 20 lines each containing the query
    write(repo / "many.txt", "\n".join(["needle"] * 20) + "\n")
    result = search_repo_text(repo, "needle", max_results=5)
    assert result["count"] == 5
    assert result["truncated"] is True


def test_search_repo_text_returns_hits(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "code.py", "def hello():\n    pass\n")
    result = search_repo_text(repo, "def hello")
    assert result["count"] >= 1
    hit = result["hits"][0]
    assert hit["path"] == "code.py"
    assert hit["line"] == 1
    assert "def hello" in hit["snippet"]


def test_search_repo_text_case_insensitive_default(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "readme.md", "Hello World\n")
    result = search_repo_text(repo, "hello world", case_sensitive=False)
    assert result["count"] == 1


def test_search_repo_text_case_sensitive(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "readme.md", "Hello World\n")
    result = search_repo_text(repo, "hello world", case_sensitive=True)
    assert result["count"] == 0


def test_search_repo_text_snippet_is_redacted(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "cfg.py", "API_KEY=supersecret123\n")
    result = search_repo_text(repo, "API_KEY")
    assert result["count"] >= 1
    snippet = result["hits"][0]["snippet"]
    assert "supersecret123" not in snippet


def test_search_repo_text_empty_query_raises(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(ValueError):
        search_repo_text(repo, "")


# ---------------------------------------------------------------------------
# Modification-time ordering
# ---------------------------------------------------------------------------


def test_get_recently_modified_files_newest_first(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    old = repo / "old.txt"
    new = repo / "new.txt"
    old.write_text("old", encoding="utf-8")
    time.sleep(0.05)
    new.write_text("new", encoding="utf-8")

    result = get_recently_modified_files(repo, limit=10)
    paths = [f["path"] for f in result["files"]]
    assert "new.txt" in paths
    assert "old.txt" in paths
    assert paths.index("new.txt") < paths.index("old.txt")


def test_get_recently_modified_files_respects_limit(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    for i in range(10):
        write(repo / f"file{i}.txt")
    result = get_recently_modified_files(repo, limit=3)
    assert result["count"] == 3
    assert result["limit"] == 3


def test_get_recently_modified_files_includes_mtime(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "a.txt")
    result = get_recently_modified_files(repo, limit=5)
    assert result["count"] >= 1
    assert isinstance(result["files"][0]["mtime"], float)


# ---------------------------------------------------------------------------
# No absolute path leakage
# ---------------------------------------------------------------------------


def test_list_repo_files_returns_posix_relative_paths(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "subdir").mkdir()
    write(repo / "subdir" / "file.py")
    result = list_repo_files(repo)
    for f in result["files"]:
        assert not Path(f).is_absolute(), f"Absolute path leaked: {f}"
        assert str(tmp_path) not in f, f"Repo root leaked in path: {f}"
        assert "\\" not in f, f"Windows separator leaked: {f}"


def test_read_repo_file_no_absolute_path_in_result(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "hello.txt", "world\n")
    result = read_repo_file(repo, "hello.txt")
    assert str(tmp_path) not in result["path"]
    assert str(tmp_path) not in result["content"]


def test_search_repo_text_no_absolute_path_in_hits(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write(repo / "target.txt", "findme")
    result = search_repo_text(repo, "findme")
    for hit in result["hits"]:
        assert str(tmp_path) not in hit["path"]
        assert not Path(hit["path"]).is_absolute()


# ---------------------------------------------------------------------------
# Proof that no CodexRunner or local model is called
# ---------------------------------------------------------------------------


def test_list_repo_files_does_not_call_codex_runner(
    tmp_path: Path, monkeypatch
) -> None:
    """list_repo_files must never instantiate or call CodexRunner."""
    import codexbridge.runner as runner_mod

    def _fail(*args, **kwargs):
        raise AssertionError("CodexRunner must not be called from repo_reader")

    monkeypatch.setattr(runner_mod.CodexRunner, "plan_task", _fail)
    monkeypatch.setattr(runner_mod.CodexRunner, "implement_task", _fail)

    repo = make_repo(tmp_path)
    write(repo / "hello.txt")
    result = list_repo_files(repo)
    assert result["ok"] is True


def test_read_repo_file_does_not_import_ollama(tmp_path: Path) -> None:
    """repo_reader must not import or reference OllamaChatAdapter, CodexRunner, or any AI backend."""
    import codexbridge.repo_reader as rr
    import ast

    source = Path(rr.__file__).read_text(encoding="utf-8")
    # Parse the AST to find actual imports — docstring mentions are fine
    tree = ast.parse(source)
    import_names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            import_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            import_names.append(module)
            import_names.extend(alias.name for alias in node.names)
    for name in import_names:
        assert "ollama" not in name.lower(), f"Found ollama import: {name}"
        assert (
            "codex_runner" not in name.lower()
            and "runner" not in name.lower()
            or "repo_reader" in name.lower()
        ), f"Unexpected runner import: {name}"
        assert "gemini" not in name.lower(), f"Found gemini import: {name}"


# ---------------------------------------------------------------------------
# Server-level integration smoke tests
# ---------------------------------------------------------------------------


def test_server_list_repo_files_tool(tmp_path: Path, monkeypatch) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    (tmp_path / ".git").mkdir()
    write(tmp_path / "hello.py", "print('hi')\n")
    config = AppConfig(
        repos={"myrepo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")

    result = server.list_repo_files("myrepo")
    assert result["ok"] is True
    assert result["repo_name"] == "myrepo"
    assert "hello.py" in result["files"]


def test_server_read_repo_file_tool(tmp_path: Path) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    (tmp_path / ".git").mkdir()
    write(tmp_path / "readme.txt", "line one\nline two\n")
    config = AppConfig(
        repos={"myrepo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")

    result = server.read_repo_file("myrepo", "readme.txt")
    assert result["ok"] is True
    assert "line one" in result["content"]
    assert result["repo_name"] == "myrepo"


def test_server_search_repo_text_tool(tmp_path: Path) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    (tmp_path / ".git").mkdir()
    write(tmp_path / "module.py", "def greet():\n    return 'hello'\n")
    config = AppConfig(
        repos={"myrepo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")

    result = server.search_repo_text("myrepo", "def greet")
    assert result["ok"] is True
    assert result["count"] >= 1
    assert result["hits"][0]["path"] == "module.py"


def test_server_get_recently_modified_files_tool(tmp_path: Path) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    (tmp_path / ".git").mkdir()
    write(tmp_path / "touched.txt", "content")
    config = AppConfig(
        repos={"myrepo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")

    result = server.get_recently_modified_files("myrepo", limit=10)
    assert result["ok"] is True
    assert result["count"] >= 1


def test_server_repo_git_status_tool(tmp_path: Path, monkeypatch) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"myrepo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(server, "git_status", lambda root: "## main\n")

    result = server.repo_git_status("myrepo")
    assert result["ok"] is True
    assert result["repo_name"] == "myrepo"
    assert "main" in result["status"]


def test_server_repo_status_does_not_claim_success_after_live_failure(
    tmp_path: Path, monkeypatch
) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"myrepo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "inspect_status",
        lambda root: {
            "ok": False,
            "status": "timed_out",
            "fresh": False,
            "source": "live_git",
            "error": "timed out",
        },
    )

    result = server.inspect_repo_status("myrepo")

    assert result["ok"] is False
    assert result["fresh"] is False
    assert result["status"] == "timed_out"


def test_server_repo_git_diff_tool(tmp_path: Path, monkeypatch) -> None:
    import codexbridge.server as server
    from codexbridge.config import AppConfig, RepoConfig

    (tmp_path / ".git").mkdir()
    config = AppConfig(
        repos={"myrepo": RepoConfig(path=str(tmp_path))},
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    monkeypatch.setattr(
        server,
        "_git_diff_raw",
        lambda root, path="", staged=False: {
            "ok": True,
            "repo_name": "",
            "path": path,
            "staged": staged,
            "diff": "diff --git a/file b/file\n",
            "truncated": False,
            "error": "",
        },
    )

    result = server.repo_git_diff("myrepo")
    assert result["ok"] is True
    assert result["repo_name"] == "myrepo"
    assert "diff" in result["diff"]
