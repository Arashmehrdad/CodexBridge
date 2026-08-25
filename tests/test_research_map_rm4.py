from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from soma import server
from soma.config import AppConfig, RepoConfig
from soma.gateway_models import ResearchMapActionRequest
from soma.project_scope import ProjectScopeStore
from soma.research_map.adoption import ResearchMapAdoptionError, adopt_research_map


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-q", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )


def _git_exclude_path(repo: Path) -> Path:
    completed = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-path", "info/exclude"],
        capture_output=True,
        text=True,
        check=True,
    )
    path = Path(completed.stdout.strip())
    return path if path.is_absolute() else repo / path


def _git_status(repo: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def _adopt(repo: Path, *, roots: list[dict] | None = None) -> dict:
    return adopt_research_map(
        repo,
        project_id="proj_rm4",
        repo_name="repo",
        roots=[{"path": "docs/research"}] if roots is None else roots,
    )


def test_rm4_first_adoption_creates_only_portable_manifest_and_local_runtime(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)

    result = _adopt(repo)

    assert result["ok"] is True
    assert result["status"] == "adopted"
    assert result["manifest_created"] is True
    assert result["database_state"] == "missing"
    assert result["sidecars_generated"] is False
    assert result["index_built"] is False
    assert re.fullmatch(r"srepo_[0-9a-f]{32}", result["repository_uid"])

    manifest_path = repo / "soma.project.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(payload) == {"schema", "repository_uid", "research_map"}
    assert payload["repository_uid"] == result["repository_uid"]
    assert payload["research_map"]["roots"] == [
        {"path": "docs/research", "sidecar_dir": "_soma_map", "include": ["*.md"]}
    ]
    encoded = manifest_path.read_text(encoding="utf-8")
    assert "proj_rm4" not in encoded
    assert str(repo) not in encoded
    assert "project_id" not in encoded
    assert "resource_id" not in encoded
    assert "repository_root" not in encoded

    runtime = repo / ".soma/research-map"
    assert (runtime / "generations").is_dir()
    assert [path for path in runtime.rglob("*") if path.is_file()] == []
    assert list(repo.rglob("_soma_map")) == []

    exclude = _git_exclude_path(repo).read_text(encoding="utf-8")
    assert sum(line.strip() == "/.soma/" for line in exclude.splitlines()) == 1
    assert _git_status(repo) == ["?? soma.project.json"]


def test_rm4_adoption_acknowledgement_is_bounded_for_maximal_roots(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    roots = [
        {"path": f"docs/research-{index:02d}-" + ("x" * 240)} for index in range(64)
    ]

    result = _adopt(repo, roots=roots)
    encoded = json.dumps(result, sort_keys=True).encode("utf-8")

    assert result["root_count"] == 64
    assert re.fullmatch(r"[0-9a-f]{64}", result["roots_sha256"])
    assert "roots" not in result
    assert len(encoded) <= 12 * 1024


def test_rm4_second_identical_adoption_is_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    first = _adopt(repo)
    manifest_before = (repo / "soma.project.json").read_bytes()
    exclude_path = _git_exclude_path(repo)
    exclude_before = exclude_path.read_bytes()

    second = _adopt(repo)

    assert second["status"] == "attached"
    assert second["repository_uid"] == first["repository_uid"]
    assert second["manifest_created"] is False
    assert second["git_exclude_changed"] is False
    assert second["runtime_initialized"] is False
    assert (repo / "soma.project.json").read_bytes() == manifest_before
    assert exclude_path.read_bytes() == exclude_before
    assert second["sidecars_generated"] is False
    assert second["index_built"] is False


def test_rm4_first_adoption_requires_explicit_roots_without_side_effects(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    exclude_path = _git_exclude_path(repo)
    exclude_before = exclude_path.read_bytes()

    with pytest.raises(ResearchMapAdoptionError) as caught:
        _adopt(repo, roots=[])

    assert caught.value.code == "roots_required"
    assert not (repo / "soma.project.json").exists()
    assert not (repo / ".soma").exists()
    assert exclude_path.read_bytes() == exclude_before
    assert _git_status(repo) == []


def test_rm4_conflicting_roots_fail_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    _adopt(repo)
    manifest_before = (repo / "soma.project.json").read_bytes()
    exclude_path = _git_exclude_path(repo)
    exclude_before = exclude_path.read_bytes()

    with pytest.raises(ResearchMapAdoptionError) as caught:
        _adopt(repo, roots=[{"path": "docs/other"}])

    assert caught.value.code == "root_conflict"
    assert (repo / "soma.project.json").read_bytes() == manifest_before
    assert exclude_path.read_bytes() == exclude_before
    assert [path for path in (repo / ".soma/research-map").rglob("*") if path.is_file()] == []


def test_rm4_clone_attach_preserves_portable_repository_uid(tmp_path: Path) -> None:
    source = tmp_path / "source"
    clone = tmp_path / "clone"
    _init_repo(source)
    _init_repo(clone)
    first = _adopt(source)
    shutil.copyfile(source / "soma.project.json", clone / "soma.project.json")

    attached = _adopt(clone, roots=[])

    assert attached["status"] == "attached"
    assert attached["repository_uid"] == first["repository_uid"]
    assert attached["manifest_created"] is False
    assert attached["database_state"] == "missing"
    assert (clone / ".soma/research-map/generations").is_dir()
    assert _git_status(clone) == ["?? soma.project.json"]


def test_rm4_existing_current_is_reported_stale_not_rebuilt(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    first = _adopt(repo)
    current = repo / ".soma/research-map/CURRENT.json"
    current.write_text('{"generation":"old"}\n', encoding="utf-8")

    attached = _adopt(repo, roots=[])

    assert attached["repository_uid"] == first["repository_uid"]
    assert attached["database_state"] == "stale_unverified"
    assert attached["sync_state"] == "stale"
    assert attached["index_built"] is False
    assert current.read_text(encoding="utf-8") == '{"generation":"old"}\n'


def test_rm4_malformed_manifest_fails_without_local_runtime_changes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "soma.project.json").write_text("{broken", encoding="utf-8")
    exclude_path = _git_exclude_path(repo)
    exclude_before = exclude_path.read_bytes()

    with pytest.raises(ResearchMapAdoptionError) as caught:
        _adopt(repo, roots=[])

    assert caught.value.code == "manifest_invalid_json"
    assert not (repo / ".soma").exists()
    assert exclude_path.read_bytes() == exclude_before


def test_rm4_server_scope_does_not_auto_resolve_duplicate_clone_uid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    _init_repo(repo_a)
    _init_repo(repo_b)
    first = _adopt(repo_a)
    shutil.copyfile(repo_a / "soma.project.json", repo_b / "soma.project.json")

    runs = tmp_path / "runs"
    config = AppConfig(
        repos={
            "repo_a": RepoConfig(path=str(repo_a)),
            "repo_b": RepoConfig(path=str(repo_b)),
        },
        runs_dir=str(runs),
        config_dir=tmp_path,
    )
    server.set_config(config, tmp_path / "config.yaml")
    scope = ProjectScopeStore(runs)
    scope.init_db()
    scope.apply_bootstrap(
        project_id="proj_a",
        project_key="project-a",
        resource_id="res_a",
        repo_name="repo_a",
        repository_root=repo_a,
    )
    scope.apply_bootstrap(
        project_id="proj_b",
        project_key="project-b",
        resource_id="res_b",
        repo_name="repo_b",
        repository_root=repo_b,
    )
    monkeypatch.setattr(server, "get_project_scope_store", lambda: scope)

    adapter = TypeAdapter(ResearchMapActionRequest)
    accepted = server.research_map_action(
        adapter.validate_python(
            {"action": "adopt", "project_id": "proj_b", "repo_name": "repo_b"}
        )
    )
    assert accepted["ok"] is True
    assert accepted["status"] == "attached"
    assert accepted["repository_uid"] == first["repository_uid"]
    assert accepted["resource_id"] == "res_b"

    refused = server.research_map_action(
        adapter.validate_python(
            {"action": "adopt", "project_id": "proj_a", "repo_name": "repo_b"}
        )
    )
    assert refused["ok"] is False
    assert refused["status"] == "scope_mismatch"
    assert refused["project_id"] == "proj_a"
