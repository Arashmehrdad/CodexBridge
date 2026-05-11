from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field, model_validator


class RepoConfig(BaseModel):
    path: str
    default_tests: List[str] = Field(default_factory=list)


class CodexConfig(BaseModel):
    executable: str = "codex"
    model: str = ""
    windows_sandbox: str = ""
    sandbox_private_desktop: bool | None = None
    default_timeout_seconds: int = 1800


class GeminiConfig(BaseModel):
    enabled: bool = False


class LocalModelConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://localhost:11434/v1"
    model: str = "llama3.2"
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=32768)


class SupervisorAutonomyProfile(BaseModel):
    stop_on_requires_human: bool = True
    max_plan_tier: int = Field(default=1, ge=1, le=3)
    max_implementation_tier: int = Field(default=2, ge=1, le=3)
    require_tests_for_non_docs_changes: bool = False


class SupervisorFileNotificationSinkConfig(BaseModel):
    enabled: bool = False
    path: str = ""


class SupervisorWebhookNotificationSinkConfig(BaseModel):
    enabled: bool = False
    url_env: str = ""
    timeout_seconds: int = Field(default=5, ge=1, le=60)


class SupervisorWindowsToastNotificationSinkConfig(BaseModel):
    enabled: bool = False


class SupervisorNotificationsConfig(BaseModel):
    enabled: bool = True
    max_payload_chars: int = Field(default=4000, ge=200, le=20000)
    file: SupervisorFileNotificationSinkConfig = Field(default_factory=SupervisorFileNotificationSinkConfig)
    webhook: SupervisorWebhookNotificationSinkConfig = Field(default_factory=SupervisorWebhookNotificationSinkConfig)
    windows_toast: SupervisorWindowsToastNotificationSinkConfig = Field(default_factory=SupervisorWindowsToastNotificationSinkConfig)


class SupervisorsConfig(BaseModel):
    default_autonomy_profile: str = "balanced"
    autonomy_profiles: Dict[str, SupervisorAutonomyProfile] = Field(
        default_factory=lambda: {
            "balanced": SupervisorAutonomyProfile(),
            "conservative": SupervisorAutonomyProfile(max_implementation_tier=1, require_tests_for_non_docs_changes=True),
        }
    )
    notifications: SupervisorNotificationsConfig = Field(default_factory=SupervisorNotificationsConfig)

    @model_validator(mode="after")
    def validate_default_profile(self) -> "SupervisorsConfig":
        if self.default_autonomy_profile not in self.autonomy_profiles:
            raise ValueError(f"Unknown default_autonomy_profile: {self.default_autonomy_profile}")
        return self

    def effective_profile(self) -> SupervisorAutonomyProfile:
        return self.autonomy_profiles[self.default_autonomy_profile]


class AppConfig(BaseModel):
    repos: Dict[str, RepoConfig]
    runs_dir: str = "runs"
    codex: CodexConfig = Field(default_factory=CodexConfig)
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    local_model: LocalModelConfig = Field(default_factory=LocalModelConfig)
    supervisors: SupervisorsConfig = Field(default_factory=SupervisorsConfig)
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
