from __future__ import annotations

from pathlib import Path

import pytest

from codexbridge.managed_artifacts import (
    MANAGED_ARTIFACT_ROOTS,
    apply_managed_artifact_cleanup,
    cleanup_new_managed_artifacts,
    preview_managed_artifact_cleanup,
    snapshot_managed_artifacts,
)


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    return repo


def test_cleanup_new_managed_artifacts_preserves_preexisting_files(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path)
    root = repo / ".codex-tmp"
    root.mkdir()
    existing = root / "existing.txt"
    existing.write_text("existing\n", encoding="utf-8")
    before = snapshot_managed_artifacts(repo)
    introduced = root / "introduced.txt"
    introduced.write_text("new\n", encoding="utf-8")

    removed = cleanup_new_managed_artifacts(repo, before)

    assert removed == [".codex-tmp/introduced.txt"]
    assert existing.exists()
    assert not introduced.exists()


def test_cleanup_preview_rejects_unregistered_root(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    with pytest.raises(ValueError, match="Unsupported managed artifact roots"):
        preview_managed_artifact_cleanup(repo, tmp_path / "runs", ["src"])


def test_cleanup_never_accepts_durable_run_evidence_root(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    assert "runs" not in MANAGED_ARTIFACT_ROOTS
    with pytest.raises(ValueError, match="Unsupported managed artifact roots"):
        preview_managed_artifact_cleanup(repo, tmp_path / "runs", ["runs"])


def test_cleanup_apply_is_hash_verified_and_idempotent(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    probe = repo / "tests" / "pytest_tmp_probe" / "a.tmp"
    probe.parent.mkdir(parents=True)
    probe.write_text("probe\n", encoding="utf-8")

    preview = preview_managed_artifact_cleanup(repo, runs, ["tests/pytest_tmp_probe"])
    first = apply_managed_artifact_cleanup(repo, runs, preview["cleanup_id"])
    second = apply_managed_artifact_cleanup(repo, runs, preview["cleanup_id"])

    assert first["removed_files"] == ["tests/pytest_tmp_probe/a.tmp"]
    assert first["idempotent_replay"] is False
    assert second["idempotent_replay"] is True
    assert not probe.exists()


def test_cleanup_apply_rejects_changed_artifact(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    runs = tmp_path / "runs"
    artifact = repo / ".ruff_cache" / "entry"
    artifact.parent.mkdir()
    artifact.write_text("one\n", encoding="utf-8")
    preview = preview_managed_artifact_cleanup(repo, runs, [".ruff_cache"])
    artifact.write_text("two\n", encoding="utf-8")

    with pytest.raises(ValueError, match="changed since preview"):
        apply_managed_artifact_cleanup(repo, runs, preview["cleanup_id"])
