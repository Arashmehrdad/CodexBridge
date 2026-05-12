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


class ReturnLoopConfig(BaseModel):
    return_loop_enabled: bool = True
    max_resume_prompt_bytes: int = Field(default=20000, ge=1, le=1000000)
    max_report_bytes: int = Field(default=100000, ge=1, le=5000000)
    manifest_schema_version: str = "1"
    conversation_target: str = "codexbridge_gpt"
    require_stable_file_check: bool = True


class MemoryConfig(BaseModel):
    memory_enabled: bool = True
    memory_db_path: str | None = None
    memory_max_content_bytes: int = Field(default=20000, ge=1, le=1000000)
    memory_search_limit: int = Field(default=20, ge=1, le=200)
    memory_import_max_files: int = Field(default=200, ge=1, le=10000)
    memory_redact_sensitive: bool = True
    memory_block_sensitive: bool = True


class AutonomyConfig(BaseModel):
    autonomy_enabled: bool = True
    autonomy_default_profile: str = "chatgpt_delegated"
    autonomy_approval_store_path: str | None = None
    autonomy_whitelisted_repos: list[str] = Field(default_factory=list)
    autonomy_allow_private_branch_push: bool = True
    autonomy_allow_main_push: bool = False
    autonomy_allow_public_repo_push: bool = False
    autonomy_allow_release_tag: bool = False
    autonomy_allow_deployment_branch_push: bool = False
    autonomy_block_secret_like_content: bool = True
    autonomy_require_human_for_production: bool = True
    autonomy_require_human_for_external_access: bool = True


class CodexRouterConfig(BaseModel):
    codex_router_enabled: bool = True
    codex_router_invoke_enabled: bool = False
    codex_router_max_context_bytes: int = Field(default=60000, ge=1000, le=1000000)
    codex_router_max_file_bytes: int = Field(default=20000, ge=1, le=500000)
    codex_router_max_log_bytes: int = Field(default=12000, ge=1, le=500000)
    codex_router_default_validation_commands: list[str] = Field(default_factory=lambda: ["pytest", "pip_check"])
    codex_router_packet_dir: str | None = None
    codex_router_use_local_model_summary: bool = True
    codex_router_redact_sensitive: bool = True
    codex_router_block_sensitive: bool = True
    codex_router_require_policy_approval: bool = True


class LocalSupervisorConfig(BaseModel):
    supervisor_enabled: bool = True
    supervisor_runs_dir: str | None = None
    supervisor_default_validation_commands: list[str] = Field(default_factory=lambda: ["git_status", "pytest", "pip_check"])
    supervisor_max_retries: int = 0
    supervisor_use_local_model_plan: bool = True
    supervisor_use_memory_context: bool = True
    supervisor_codex_invocation_enabled: bool = False
    supervisor_generate_pulse_manifest: bool = True
    supervisor_max_report_bytes: int = Field(default=100000, ge=1, le=5000000)
    supervisor_max_resume_prompt_bytes: int = Field(default=20000, ge=1, le=1000000)
    supervisor_block_sensitive: bool = True
    supervisor_redact_sensitive: bool = True


class LocalCodingConfig(BaseModel):
    local_coding_enabled: bool = False
    local_coding_preview_enabled: bool = True
    local_coding_apply_enabled: bool = False
    local_coding_runs_dir: str | None = None
    local_coding_allowed_path_globs: list[str] = Field(default_factory=lambda: ["README.md", "README.*", "docs/**/*.md", "AGENTS.md", "PLANS.md"])
    local_coding_allowed_extensions: list[str] = Field(default_factory=lambda: [".md", ".txt", ".json"])
    local_coding_block_source_code: bool = True
    local_coding_block_tests: bool = True
    local_coding_max_file_bytes: int = Field(default=20000, ge=1, le=1000000)
    local_coding_max_patch_bytes: int = Field(default=4000, ge=1, le=1000000)
    local_coding_max_changed_lines: int = Field(default=20, ge=1, le=10000)
    local_coding_max_operations: int = Field(default=3, ge=1, le=100)
    local_coding_require_approval: bool = True
    local_coding_auto_rollback_on_validation_failure: bool = False
    local_coding_default_validation_commands: list[str] = Field(default_factory=lambda: ["git_status"])
    local_coding_use_local_model: bool = False
    local_coding_block_sensitive: bool = True
    local_coding_redact_sensitive: bool = True


class DashboardConfig(BaseModel):
    dashboard_enabled: bool = True
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = Field(default=8765, ge=1, le=65535)
    dashboard_runs_dir: str | None = None
    dashboard_max_items: int = Field(default=50, ge=1, le=500)
    dashboard_max_file_bytes: int = Field(default=200000, ge=1, le=5000000)
    dashboard_include_memory: bool = True
    dashboard_include_repo_status: bool = True
    dashboard_artifact_only_repo_status: bool = True
    dashboard_read_only: bool = True


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
    return_loop: ReturnLoopConfig = Field(default_factory=ReturnLoopConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    autonomy: AutonomyConfig = Field(default_factory=AutonomyConfig)
    codex_router: CodexRouterConfig = Field(default_factory=CodexRouterConfig)
    local_supervisor: LocalSupervisorConfig = Field(default_factory=LocalSupervisorConfig)
    local_coding: LocalCodingConfig = Field(default_factory=LocalCodingConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    supervisors: SupervisorsConfig = Field(default_factory=SupervisorsConfig)
    config_dir: Path = Field(default_factory=lambda: Path.cwd(), exclude=True)

    def resolve_runs_dir(self) -> Path:
        runs = Path(self.runs_dir)
        if not runs.is_absolute():
            runs = self.config_dir / runs
        return runs.resolve()

    def resolve_memory_db_path(self) -> Path:
        if self.memory.memory_db_path:
            path = Path(self.memory.memory_db_path)
            if not path.is_absolute():
                path = self.config_dir / path
            return path.resolve()
        return self.resolve_runs_dir() / "memory" / "project_memory.sqlite3"

    def resolve_approval_store_path(self) -> Path:
        if self.autonomy.autonomy_approval_store_path:
            path = Path(self.autonomy.autonomy_approval_store_path)
            if not path.is_absolute():
                path = self.config_dir / path
            return path.resolve()
        return self.resolve_runs_dir() / "approvals"

    def resolve_codex_router_packet_dir(self) -> Path:
        if self.codex_router.codex_router_packet_dir:
            path = Path(self.codex_router.codex_router_packet_dir)
            if not path.is_absolute():
                path = self.config_dir / path
            return path.resolve()
        return self.resolve_runs_dir() / "codex_escalations"

    def resolve_local_supervisor_runs_dir(self) -> Path:
        if self.local_supervisor.supervisor_runs_dir:
            path = Path(self.local_supervisor.supervisor_runs_dir)
            if not path.is_absolute():
                path = self.config_dir / path
            return path.resolve()
        return self.resolve_runs_dir() / "supervisors"

    def resolve_local_coding_runs_dir(self) -> Path:
        if self.local_coding.local_coding_runs_dir:
            path = Path(self.local_coding.local_coding_runs_dir)
            if not path.is_absolute():
                path = self.config_dir / path
            return path.resolve()
        return self.resolve_runs_dir() / "local_coding"

    def resolve_dashboard_runs_dir(self) -> Path:
        if self.dashboard.dashboard_runs_dir:
            path = Path(self.dashboard.dashboard_runs_dir)
            if not path.is_absolute():
                path = self.config_dir / path
            return path.resolve()
        return self.resolve_runs_dir()


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
