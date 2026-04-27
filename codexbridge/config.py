from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field


class RepoConfig(BaseModel):
    path: str
    default_tests: List[str] = Field(default_factory=list)


class CodexConfig(BaseModel):
    executable: str = "codex"
    model: str = ""
    default_timeout_seconds: int = 1800


class GeminiConfig(BaseModel):
    enabled: bool = False


class AppConfig(BaseModel):
    repos: Dict[str, RepoConfig]
    runs_dir: str = "runs"
    codex: CodexConfig = Field(default_factory=CodexConfig)
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    config_dir: Path = Field(default_factory=lambda: Path.cwd(), exclude=True)

    def resolve_runs_dir(self) -> Path:
        runs = Path(self.runs_dir)
        if not runs.is_absolute():
            runs = self.config_dir / runs
        return runs.resolve()


def load_config(path: str | Path = "config.yaml", *, validate_repos: bool = True) -> AppConfig:
    config_path = Path(path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config = AppConfig(**data, config_dir=config_path.parent)

    if validate_repos:
        for name, repo in config.repos.items():
            repo_path = Path(repo.path).resolve()
            if not repo_path.exists():
                raise ValueError(f"Repo '{name}' path does not exist: {repo_path}")
            if not (repo_path / ".git").exists():
                raise ValueError(f"Repo '{name}' path does not contain .git: {repo_path}")

    return config


def resolve_repo(config: AppConfig, repo_name: str) -> Path:
    if repo_name not in config.repos:
        raise ValueError(f"Unknown repo_name: {repo_name}")
    repo_path = Path(config.repos[repo_name].path).resolve()
    if not repo_path.exists():
        raise ValueError(f"Repo path does not exist: {repo_path}")
    if not (repo_path / ".git").exists():
        raise ValueError(f"Repo path does not contain .git: {repo_path}")
    return repo_path
