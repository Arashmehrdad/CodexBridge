from __future__ import annotations

import json
from pathlib import Path

import pytest

from codexbridge.repo_wiki import RepoWikiService


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


def test_refresh_generates_repository_wiki(tmp_path: Path) -> None:
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")

    result = service.refresh()

    assert result["ok"] is True
    assert result["status"] == "generated"
    assert result["source_file_count"] >= 6
    assert result["scan_truncated"] is False
    assert (tmp_path / ".codexbridge" / "wiki" / "overview.md").is_file()
    assert (tmp_path / ".codexbridge" / "wiki" / "architecture.md").is_file()
    assert (tmp_path / ".codexbridge" / "wiki" / "modules.md").is_file()
    assert (tmp_path / ".codexbridge" / "wiki" / "validation.md").is_file()

    manifest = json.loads(
        (tmp_path / ".codexbridge" / "wiki" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    indexed_paths = {item["path"] for item in manifest["source_files"]}
    assert ".env" not in indexed_paths
    assert "secrets/token.txt" not in indexed_paths
    assert "src/demo/service.py" in indexed_paths


def test_refresh_is_incremental_and_detects_changes(tmp_path: Path) -> None:
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


def test_read_page_rejects_traversal(tmp_path: Path) -> None:
    _make_python_repo(tmp_path)
    service = RepoWikiService(tmp_path, "demo")
    service.refresh()

    with pytest.raises(ValueError, match="Invalid wiki page"):
        service.read_page("../README.md")
