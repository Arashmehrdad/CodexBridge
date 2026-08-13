"""Production reasoning runtime wiring with an explicit owner activation gate."""

from __future__ import annotations

from pathlib import Path

from soma.config import AppConfig, resolve_repo
from soma.tasks.store import TaskStore

from .backends import ReasoningBackend
from .codex_repository_backend import CodexRepositoryReasoningBackend
from .codex_repository_backend_support import ClientFactory, Preflight
from .codex_repository_contract import make_repository_reasoning_spec
from .codex_repository_provider import (
    default_codex_repository_client_factory,
    default_codex_repository_preflight,
)
from .git_snapshot import GitCommitSourceLoader
from .models import ReasoningSpecV1
from .repository_assignment import (
    RepositoryReasoningAssignmentStore,
    RepositoryReasoningAssignmentV1,
)
from .store import ReasoningBackendStore


def repository_assignment_store(config: AppConfig) -> RepositoryReasoningAssignmentStore:
    return RepositoryReasoningAssignmentStore(config.resolve_runs_dir())


def create_repository_assignment(
    config: AppConfig,
    *,
    repo_name: str,
    objective: str,
    instructions: str = "",
) -> tuple[RepositoryReasoningAssignmentV1, str, str, bool]:
    """Freeze one objective against the repository's current committed HEAD."""
    repository_root = resolve_repo(config, repo_name)
    source = GitCommitSourceLoader(repository_root, "HEAD")
    assignment = RepositoryReasoningAssignmentV1(
        repo_name=repo_name,
        source_commit=source.source_commit,
        objective=objective,
        instructions=instructions,
    )
    ref, digest, created = repository_assignment_store(config).write(assignment)
    return assignment, ref, digest, created


def configured_repository_spec(
    config: AppConfig,
    *,
    assignment_ref: str,
    assignment_hash: str,
) -> ReasoningSpecV1:
    reasoning = config.reasoning
    return make_repository_reasoning_spec(
        assignment_ref=assignment_ref,
        assignment_hash=assignment_hash,
        model=reasoning.model,
        effort=reasoning.effort,
    )


def build_reasoning_backend(
    config: AppConfig,
    *,
    task_store: TaskStore | None = None,
    client_factory: ClientFactory | None = None,
    preflight: Preflight | None = None,
) -> ReasoningBackend | None:
    """Construct the configured backend only when the owner gate is enabled."""
    reasoning = config.reasoning
    if not reasoning.enabled:
        return None
    runs_dir = config.resolve_runs_dir()
    tasks = task_store or TaskStore(runs_dir)
    assignments = repository_assignment_store(config)
    service_root = Path(config.config_dir).resolve()

    def task_id_resolver(backend_ref: str) -> str:
        task = tasks.find_by_backend_ref("soma_reasoning", backend_ref)
        return task.task_id if task is not None else ""

    return CodexRepositoryReasoningBackend(
        ReasoningBackendStore(runs_dir),
        assignment_resolver=assignments.read,
        repository_root_resolver=lambda repo_name: resolve_repo(config, repo_name),
        task_id_resolver=task_id_resolver,
        client_factory=client_factory
        or default_codex_repository_client_factory(service_root),
        preflight=preflight
        or default_codex_repository_preflight(
            service_root,
            model=reasoning.model,
        ),
        model=reasoning.model,
        effort=reasoning.effort,
    )
