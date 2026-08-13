"""Production reasoning runtime wiring tests with zero provider execution."""

from __future__ import annotations

import subprocess
from pathlib import Path

from soma.config import load_config
from soma.reasoning import runtime
from soma.tasks.manager import TaskManager
from soma.tasks.store import TaskStore


def _config(tmp_path: Path, *, enabled: bool):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    runs = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                f'runs_dir: "{runs.as_posix()}"',
                "reasoning:",
                f"  enabled: {'true' if enabled else 'false'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return load_config(config_path, validate_repos=False), config_path, repo


def _init_git(repo: Path) -> str:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "soma-test@example.invalid"],
        cwd=repo,
        check=True,
    )
    subprocess.run(["git", "config", "user.name", "Soma Test"], cwd=repo, check=True)
    (repo / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "source.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip().lower()


def test_disabled_runtime_constructs_no_provider_backend(tmp_path: Path, monkeypatch) -> None:
    config, _config_path, _repo = _config(tmp_path, enabled=False)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("disabled runtime must not construct provider factories")

    monkeypatch.setattr(runtime, "default_codex_repository_client_factory", forbidden)
    monkeypatch.setattr(runtime, "default_codex_repository_preflight", forbidden)
    assert runtime.build_reasoning_backend(config) is None


def test_enabled_runtime_can_be_wired_without_running_provider(tmp_path: Path) -> None:
    config, config_path, _repo = _config(tmp_path, enabled=True)
    store = TaskStore(config.resolve_runs_dir())

    def forbidden_client():
        raise AssertionError("backend construction must not create a provider client")

    def forbidden_preflight():
        raise AssertionError("backend construction must not execute provider preflight")

    backend = runtime.build_reasoning_backend(
        config,
        task_store=store,
        client_factory=forbidden_client,
        preflight=forbidden_preflight,
    )
    assert backend is not None
    manager = TaskManager(
        config,
        config_path,
        reasoning_backend=backend,
        store=store,
    )
    capabilities = manager.capabilities()
    assert "reasoning" in capabilities["task_kinds"]
    assert "soma_reasoning" in {
        item["backend_kind"] for item in capabilities["backends"]
    }


def test_assignment_freezes_current_committed_head(tmp_path: Path) -> None:
    config, _config_path, repo = _config(tmp_path, enabled=False)
    head = _init_git(repo)

    assignment, ref, digest, created = runtime.create_repository_assignment(
        config,
        repo_name="sample",
        objective="Inspect the committed source.",
    )

    assert created is True
    assert assignment.source_commit == head
    assert assignment.assignment_ref == ref
    assert assignment.assignment_hash == digest

    (repo / "source.py").write_text("VALUE = 2\n", encoding="utf-8")
    replay, replay_ref, replay_hash, replay_created = runtime.create_repository_assignment(
        config,
        repo_name="sample",
        objective="Inspect the committed source.",
    )
    assert replay.source_commit == head
    assert replay_ref == ref
    assert replay_hash == digest
    assert replay_created is False
