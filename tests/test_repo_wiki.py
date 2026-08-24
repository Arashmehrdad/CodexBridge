from __future__ import annotations

import json
import hashlib
import subprocess
import threading
from pathlib import Path

import pytest

from soma.repo_wiki import RepoWikiService


def _init_git_repo(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tests@example.com"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Soma Tests"],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _make_python_repo(root: Path) -> None:
    (root / "src" / "demo").mkdir(parents=True)
    (root / "src" / "demo" / "__init__.py").write_text(
        '"""Demo package."""\n', encoding="utf-8"
    )
    (root / "src" / "demo" / "service.py").write_text(
        '"""Service layer."""\n\n'
        "from demo import models\n\n"
        "class Worker:\n"
        "    pass\n\n"
        "def run_task():\n"
        "    return True\n",
        encoding="utf-8",
    )
    (root / "src" / "demo" / "models.py").write_text(
        "class Record:\n    pass\n",
        encoding="utf-8",
    )
    (root / "main.py").write_text(
        "from demo.service import run_task\n", encoding="utf-8"
    )
    (root / "README.md").write_text("# Demo\n\nA test repository.\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname='demo'\nversion='0.1.0'\n\n[tool.pytest.ini_options]\ntestpaths=['tests']\n",
        encoding="utf-8",
    )
    (root / ".env").write_text("API_KEY=do-not-index\n", encoding="utf-8")
    (root / "secrets").mkdir()
    (root / "secrets" / "token.txt").write_text("do-not-index\n", encoding="utf-8")
    (root / ".pulse-chrome-profile").mkdir()
    (root / ".pulse-chrome-profile" / "extension.js").write_text(
        "console.log('do-not-index');\n", encoding="utf-8"
    )
    (root / "demo.egg-info").mkdir()
    (root / "demo.egg-info" / "SOURCES.txt").write_text(
        "do-not-index\n", encoding="utf-8"
    )


def test_refresh_generates_repository_wiki(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")

    result = service.refresh()

    assert result["ok"] is True
    assert result["status"] == "generated"
    assert result["source_file_count"] >= 6
    assert result["scan_truncated"] is False
    assert result["stale"] is False
    assert result["indexed_head"] == ""
    current_path = tmp_path / ".soma" / "wiki" / "CURRENT.json"
    current = json.loads(current_path.read_text(encoding="utf-8"))
    generation = (
        tmp_path / ".soma" / "wiki" / "generations" / current["generation_id"]
    )
    assert (generation / "index.md").is_file()
    assert (generation / "overview.md").is_file()
    assert (generation / "architecture.md").is_file()
    assert (generation / "modules.md").is_file()
    assert (generation / "validation.md").is_file()
    manifest = json.loads(
        (generation / "machine" / "manifest.json").read_text(encoding="utf-8")
    )
    source_index = json.loads(
        (generation / "machine" / "source-index.json").read_text(encoding="utf-8")
    )
    indexed_paths = set(source_index)
    assert ".env" not in indexed_paths
    assert "secrets/token.txt" not in indexed_paths
    assert ".pulse-chrome-profile/extension.js" not in indexed_paths
    assert "demo.egg-info/SOURCES.txt" not in indexed_paths
    assert "src/demo/service.py" in indexed_paths
    assert manifest["version"] == 2
    assert manifest["generation_id"] == current["generation_id"]
    assert current["manifest_sha256"]
    assert "index.md" in manifest["pages"]
    assert "indexed_head" in manifest
    assert "indexed_branch" in manifest
    assert "index_configuration_fingerprint" in manifest


def test_mark_stale_does_not_refresh_or_change_pages(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.refresh()
    current_before = json.loads(service.current_path.read_text(encoding="utf-8"))
    generation = service.generations_root / current_before["generation_id"]
    overview_before = (generation / "overview.md").read_text(encoding="utf-8")
    manifest_before = (generation / "machine" / "manifest.json").read_bytes()

    result = service.mark_stale(reason="test repository write")
    current_after = json.loads(service.current_path.read_text(encoding="utf-8"))

    assert result["stale"] is True
    assert current_after["stale"] is True
    assert current_after["stale_reason"] == "test repository write"
    assert current_after["source_generation"] == current_before["source_generation"] + 1
    assert (generation / "overview.md").read_text(encoding="utf-8") == overview_before
    assert (generation / "machine" / "manifest.json").read_bytes() == manifest_before


def test_version_one_manifest_is_readable_and_upgraded(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.wiki_root.mkdir(parents=True)
    for page in ("overview.md", "architecture.md", "modules.md", "validation.md"):
        (service.wiki_root / page).write_text(f"# legacy {page}\n", encoding="utf-8")
    legacy_manifest = {"version": 1, "source_files": [], "pages": []}
    service.manifest_path.write_text(
        json.dumps(legacy_manifest),
        encoding="utf-8",
    )

    result = service.refresh()

    assert result["ok"] is True
    assert result["status"] == "migrated"
    assert service.current_path.is_file()
    assert json.loads(service.manifest_path.read_text(encoding="utf-8")) == legacy_manifest


def test_refresh_is_incremental_and_detects_changes(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")

    first = service.refresh()
    second = service.refresh()
    (tmp_path / "src" / "demo" / "service.py").write_text(
        "def changed_behavior():\n    return 42\n",
        encoding="utf-8",
    )
    third = service.refresh()

    assert first["status"] == "generated"
    assert second["status"] == "unchanged"
    assert second["changed_source_files"] == []
    assert third["status"] == "refreshed"
    assert "src/demo/service.py" in third["changed_source_files"]


def test_read_and_search_wiki(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.refresh()

    page = service.read_page("modules.md")
    hits = service.search("Worker", limit=10)

    assert page["ok"] is True
    assert "src/demo/service.py" in page["content"]
    assert any(
        hit["page"] == "modules.md" and "Worker" in hit["snippet"] for hit in hits
    )


def test_search_ignores_inactive_or_unlisted_markdown(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.refresh()
    nested = service.wiki_root / "guides" / "knowledge.md"
    nested.parent.mkdir(parents=True)
    nested.write_text(
        "Repository-scoped curiosity_scoring guidance.\n", encoding="utf-8"
    )

    hits = service.search("curiosity scoring", limit=10)

    assert not any(hit["page"] == "guides/knowledge.md" for hit in hits)


def test_read_page_rejects_traversal(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.refresh()

    with pytest.raises(ValueError, match="Invalid wiki page"):
        service.read_page("../README.md")


def test_refresh_applies_custom_wiki_exclusions(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "draft.md").write_text("skip me\n", encoding="utf-8")
    service = RepoWikiService(tmp_path, "demo", wiki_exclusions=["notes"])

    service.refresh()

    current = json.loads(
        (tmp_path / ".soma" / "wiki" / "CURRENT.json").read_text(
            encoding="utf-8"
        )
    )
    generation = tmp_path / ".soma" / "wiki" / "generations" / current["generation_id"]
    source_index = json.loads(
        (generation / "machine" / "source-index.json").read_text(encoding="utf-8")
    )
    indexed_paths = set(source_index)
    assert "notes/draft.md" not in indexed_paths


def test_refresh_falls_back_to_filesystem_when_git_discovery_fails(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / ".git").mkdir()
    _make_python_repo(tmp_path)
    runtime_file = tmp_path / ".soma" / "research-map" / "index" / "state.json"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text('{"must_not_index":true}\n', encoding="utf-8")
    service = RepoWikiService(tmp_path, "demo")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 128, "", "not a git repo"
        ),
    )

    result = service.refresh()

    assert result["ok"] is True
    current = json.loads(
        (tmp_path / ".soma" / "wiki" / "CURRENT.json").read_text(
            encoding="utf-8"
        )
    )
    generation = tmp_path / ".soma" / "wiki" / "generations" / current["generation_id"]
    source_index = json.loads(
        (generation / "machine" / "source-index.json").read_text(encoding="utf-8")
    )
    indexed_paths = set(source_index)
    assert "src/demo/service.py" in indexed_paths
    assert ".pulse-chrome-profile/extension.js" not in indexed_paths
    assert "demo.egg-info/SOURCES.txt" not in indexed_paths
    assert ".soma/research-map/index/state.json" not in indexed_paths


def test_refresh_excludes_tracked_research_map_sidecars_from_code_wiki(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    source = tmp_path / "docs" / "research" / "001_result.md"
    sidecar = tmp_path / "docs" / "research" / "_soma_map" / "001_result.json"
    source.parent.mkdir(parents=True)
    sidecar.parent.mkdir(parents=True)
    source.write_text("# Research 001\n", encoding="utf-8")
    sidecar.write_text('{"schema_version":"soma.research-map.v2"}\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True, capture_output=True)

    service = RepoWikiService(tmp_path, "demo")
    service.refresh()
    current = json.loads(service.current_path.read_text(encoding="utf-8"))
    source_index = json.loads(
        (service.generations_root / current["generation_id"] / "machine" / "source-index.json").read_text(
            encoding="utf-8"
        )
    )

    assert "docs/research/001_result.md" in source_index
    assert "docs/research/_soma_map/001_result.json" not in source_index


def _legacy_wiki(service: RepoWikiService, marker: str = "legacy marker") -> None:
    service.wiki_root.mkdir(parents=True, exist_ok=True)
    for page in ("overview.md", "architecture.md", "modules.md", "validation.md"):
        (service.wiki_root / page).write_text(f"# {page}\n{marker}\n", encoding="utf-8")
    service.manifest_path.write_text(
        json.dumps({"version": 1, "pages": ["overview.md"]}), encoding="utf-8"
    )


def test_generation_manifest_and_current_hashes_match(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.refresh()

    current = json.loads(service.current_path.read_text(encoding="utf-8"))
    generation = service.generations_root / current["generation_id"]
    manifest_path = generation / "machine" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert current["manifest_sha256"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    for page, metadata in manifest["pages"].items():
        data = (generation / page).read_bytes()
        assert metadata == {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        }


def test_refresh_publishes_new_generation_without_mutating_previous(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.refresh()
    first_current = json.loads(service.current_path.read_text(encoding="utf-8"))
    first_generation = service.generations_root / first_current["generation_id"]
    first_overview = (first_generation / "overview.md").read_bytes()

    (tmp_path / "README.md").write_text("# Changed\n", encoding="utf-8")
    result = service.refresh(force=True)
    second_current = json.loads(service.current_path.read_text(encoding="utf-8"))

    assert result["ok"] is True
    assert second_current["generation_id"] != first_current["generation_id"]
    assert (first_generation / "overview.md").read_bytes() == first_overview
    assert len(list(service.generations_root.iterdir())) >= 2


def test_reader_and_search_use_only_the_active_generation(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.refresh()
    first_current = json.loads(service.current_path.read_text(encoding="utf-8"))
    first_generation = service.generations_root / first_current["generation_id"]
    (tmp_path / "README.md").write_text("# New generation\n", encoding="utf-8")
    service.refresh(force=True)

    (first_generation / "overview.md").write_text(
        "inactive-only sentinel\n", encoding="utf-8"
    )
    page = service.read_page("overview.md")
    hits = service.search("inactive-only sentinel")

    assert "inactive-only sentinel" not in page["content"]
    assert hits == []


def test_failed_refresh_keeps_previous_current(tmp_path: Path, monkeypatch) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.refresh()
    before = service.current_path.read_bytes()

    def fail(*args, **kwargs):
        raise RuntimeError("render failed")

    monkeypatch.setattr(service, "_render_overview", fail)
    result = service.refresh(force=True)

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert service.current_path.read_bytes() == before


def test_legacy_flat_wiki_is_readable_and_searchable(tmp_path: Path) -> None:
    service = RepoWikiService(tmp_path, "demo")
    _legacy_wiki(service, "legacy-search-token")

    page = service.read_page("overview.md")
    hits = service.search("legacy search token")

    assert page["generation_id"] == ""
    assert "legacy-search-token" in page["content"]
    assert hits and hits[0]["page"] == "overview.md"


def test_legacy_refresh_migrates_without_deleting_flat_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    _legacy_wiki(service)
    legacy_bytes = {
        page: (service.wiki_root / page).read_bytes()
        for page in ("overview.md", "architecture.md", "modules.md", "validation.md")
    }

    result = service.refresh()

    assert result["status"] == "migrated"
    assert all((service.wiki_root / page).read_bytes() == data for page, data in legacy_bytes.items())
    assert service.current_path.is_file()


def test_invalid_current_returns_structured_corruption_at_gateway(tmp_path: Path) -> None:
    service = RepoWikiService(tmp_path, "demo")
    service.wiki_root.mkdir(parents=True)
    service.current_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="CURRENT.json"):
        service.read_page("overview.md")


def test_stale_marking_without_generation_is_safe(tmp_path: Path) -> None:
    service = RepoWikiService(tmp_path, "demo")

    result = service.mark_stale(reason="write before first refresh")

    assert result["ok"] is True
    assert result["status"] == "no_generation"
    assert not service.current_path.exists()


def test_duplicate_refresh_returns_structured_in_progress(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    started = threading.Event()
    release = threading.Event()
    original = service._refresh_locked

    def blocking(*, operation_id: str, force: bool):
        started.set()
        assert release.wait(10)
        return original(operation_id=operation_id, force=force)

    service._refresh_locked = blocking
    worker = threading.Thread(target=service.refresh)
    worker.start()
    assert started.wait(10)
    duplicate = service.refresh()
    release.set()
    worker.join(timeout=10)

    assert duplicate["ok"] is False
    assert duplicate["status"] == "wiki_refresh_in_progress"


def test_different_repository_refreshes_use_independent_locks(tmp_path: Path) -> None:
    roots = [tmp_path / "one", tmp_path / "two"]
    services = []
    for root in roots:
        root.mkdir()
        _init_git_repo(root)
        _make_python_repo(root)
        services.append(RepoWikiService(root, root.name))
    started = [threading.Event(), threading.Event()]
    release = threading.Event()
    originals = [service._refresh_locked for service in services]

    for index, service in enumerate(services):
        def blocking(*, operation_id: str, force: bool, index=index):
            started[index].set()
            assert release.wait(10)
            return originals[index](operation_id=operation_id, force=force)

        service._refresh_locked = blocking
    workers = [threading.Thread(target=service.refresh) for service in services]
    for worker in workers:
        worker.start()
    assert all(event.wait(10) for event in started)
    release.set()
    for worker in workers:
        worker.join(timeout=10)

    assert all(not worker.is_alive() for worker in workers)
    assert all(service.current_path.is_file() for service in services)


def test_source_change_during_refresh_publishes_stale_generation(tmp_path: Path, monkeypatch) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    original = service._analyse

    def analyse(*args, **kwargs):
        result = original(*args, **kwargs)
        (tmp_path / "README.md").write_text("changed during refresh\n", encoding="utf-8")
        return result

    monkeypatch.setattr(service, "_analyse", analyse)
    result = service.refresh()
    current = json.loads(service.current_path.read_text(encoding="utf-8"))
    generation = service.generations_root / current["generation_id"]
    overview = (generation / "overview.md").read_text(encoding="utf-8")
    manifest = json.loads(
        (generation / "machine" / "manifest.json").read_text(encoding="utf-8")
    )

    assert result["ok"] is True
    assert result["stale"] is True
    assert current["stale"] is True
    assert current["stale_reason"]
    assert "- stale: true" in overview
    assert manifest["stale"] is True
    assert manifest["stale"] == current["stale"]


def test_search_reports_the_active_generation_and_new_marker(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    marker = "Current implementation status: pending work marker"
    (tmp_path / "src" / "demo" / "status.py").write_text(
        f'"""{marker}"""\n', encoding="utf-8"
    )
    service = RepoWikiService(tmp_path, "demo")
    refresh = service.refresh()

    page = service.read_page("modules.md")
    search = service.search_with_metadata(marker)

    assert refresh["ok"] is True
    assert page["generation_id"] == refresh["generation_id"]
    assert search["generation_id"] == refresh["generation_id"]
    assert search["stale"] is False
    assert any(marker in hit["snippet"] for hit in search["hits"])


def test_source_index_tracks_added_deleted_and_renamed_files(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.refresh()
    (tmp_path / "src" / "demo" / "models.py").unlink()
    (tmp_path / "src" / "demo" / "renamed.py").write_text("class Renamed: pass\n", encoding="utf-8")
    (tmp_path / "added.py").write_text("def added(): return True\n", encoding="utf-8")

    service.refresh()
    current = json.loads(service.current_path.read_text(encoding="utf-8"))
    source_index = json.loads(
        (service.generations_root / current["generation_id"] / "machine" / "source-index.json").read_text(
            encoding="utf-8"
        )
    )

    assert "src/demo/models.py" not in source_index
    assert "src/demo/renamed.py" in source_index
    assert "added.py" in source_index
