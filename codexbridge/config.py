from __future__ import annotations

from pathlib import Path, PureWindowsPath
from typing import Dict, List, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class DockerExecProfileConfig(BaseModel):
    command_id: str
    argv: List[str] = Field(default_factory=list, min_length=1, max_length=64)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    description: str = ""
    writes_files: bool = False

    @model_validator(mode="after")
    def validate_profile(self) -> "DockerExecProfileConfig":
        allowed = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        if not self.command_id or any(char not in allowed for char in self.command_id):
            raise ValueError("Docker exec command_id must use letters, numbers, _ or -")
        for argument in self.argv:
            if not argument or any(
                ord(char) < 32 or ord(char) == 127 for char in argument
            ):
                raise ValueError(
                    "Docker exec argv values must be non-empty and contain no control characters"
                )
            if any(token in argument for token in (";", "&&", "||", "|", "`", "$(")):
                raise ValueError("Docker exec argv must not contain shell operators")
        return self


class DockerConfig(BaseModel):
    enabled: bool = False
    executable: str = "docker"
    max_output_bytes: int = Field(default=100000, ge=1024, le=5000000)
    default_timeout_seconds: int = Field(default=600, ge=1, le=7200)
    allow_push: bool = False
    allow_prune: bool = False
    allow_remove: bool = False
    allow_compose_down_volumes: bool = False
    confirmation_token: str = Field(
        default="CONFIRM_DOCKER_HIGH_RISK", min_length=8, max_length=128
    )


class RepoConfig(BaseModel):
    path: str
    default_tests: List[str] = Field(default_factory=list)
    command_profiles: List[Dict] = Field(default_factory=list)
    wiki_exclude_paths: List[str] = Field(default_factory=list)
    commit_mode: Literal["explicit_only", "all_allowed"] = "explicit_only"
    allow_push: bool = False
    refuse_unrelated_staged_files: bool = True
    require_commit_report: bool = True
    docker_compose_files: List[str] = Field(default_factory=list)
    docker_project_name: str = ""
    docker_exec_profiles: List[DockerExecProfileConfig] = Field(default_factory=list)
    cloudflare_profiles: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_repository_capabilities(self) -> "RepoConfig":
        command_ids = [profile.command_id for profile in self.docker_exec_profiles]
        if len(command_ids) != len(set(command_ids)):
            raise ValueError(
                "Docker exec command_id values must be unique per repository"
            )
        normalized_profiles: list[str] = []
        for profile_id in self.cloudflare_profiles:
            value = str(profile_id or "").strip()
            if (
                not value
                or len(value) > 64
                or not value[0].isalnum()
                or any(not (char.isalnum() or char in "_-") for char in value)
            ):
                raise ValueError(
                    "Cloudflare profile IDs assigned to repositories are invalid"
                )
            normalized_profiles.append(value)
        if len(normalized_profiles) != len(set(normalized_profiles)):
            raise ValueError("Cloudflare profile IDs must be unique per repository")
        self.cloudflare_profiles = normalized_profiles
        return self


class SSHCommandProfileConfig(BaseModel):
    command_id: str
    argv: List[str] = Field(default_factory=list, min_length=1, max_length=64)
    timeout_seconds: int = Field(default=120, ge=1, le=3600)
    description: str = ""
    writes_remote: bool = False


class SSHDeploymentProfileConfig(BaseModel):
    repo_name: str
    remote_root: str
    local_subdir: str = "."
    compose_file: str = ""
    compose_project_name: str = ""
    compose_services: List[str] = Field(default_factory=list)
    compose_build: bool = True
    env_file: str = ""
    shared_files: Dict[str, str] = Field(default_factory=dict)
    service_name: str = ""
    health_command_id: str = ""
    exclude_paths: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_deployment_profile(self) -> "SSHDeploymentProfileConfig":
        if not self.repo_name.strip():
            raise ValueError("SSH deployment repo_name must not be empty")
        if not self.remote_root.startswith("/") or "\\" in self.remote_root:
            raise ValueError(
                "SSH deployment remote_root must be an absolute POSIX path"
            )
        if self.local_subdir.startswith(
            ("/", "\\")
        ) or ".." in self.local_subdir.replace("\\", "/").split("/"):
            raise ValueError("SSH deployment local_subdir must be repository-relative")
        if self.compose_file and (
            self.compose_file.startswith(("/", "\\"))
            or ".." in self.compose_file.replace("\\", "/").split("/")
        ):
            raise ValueError(
                "SSH deployment compose_file must be relative to remote_root"
            )
        if self.env_file and not self.env_file.startswith("/"):
            raise ValueError("SSH deployment env_file must be an absolute POSIX path")
        for remote_source, release_target in self.shared_files.items():
            if not remote_source.startswith("/") or "\\" in remote_source:
                raise ValueError(
                    "SSH deployment shared file sources must be absolute POSIX paths"
                )
            normalized_target = release_target.replace("\\", "/")
            if normalized_target.startswith("/") or ".." in normalized_target.split(
                "/"
            ):
                raise ValueError(
                    "SSH deployment shared file targets must be release-relative"
                )
        return self


class SSHHostConfig(BaseModel):
    ssh_alias: str = ""
    connection_file: str = ""
    hostname: str = ""
    user: str = ""
    port: int = Field(default=22, ge=1, le=65535)
    identity_file: str = ""
    connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    force_pty: bool = False
    use_sudo: bool = False
    allowed_remote_roots: List[str] = Field(default_factory=list)
    allowed_executables: List[str] = Field(default_factory=list)
    deployment_profiles: Dict[str, SSHDeploymentProfileConfig] = Field(
        default_factory=dict
    )
    command_profiles: List[SSHCommandProfileConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_command_ids(self) -> "SSHHostConfig":
        self.ssh_alias = self.ssh_alias.strip()
        self.connection_file = self.connection_file.strip()
        self.hostname = self.hostname.strip()
        self.user = self.user.strip()
        self.identity_file = self.identity_file.strip()
        direct_values = (self.hostname, self.user, self.identity_file)
        configured_modes = sum(
            (
                bool(self.ssh_alias),
                bool(self.connection_file),
                any(direct_values) or self.port != 22,
            )
        )
        if configured_modes != 1:
            raise ValueError(
                "SSH host must use exactly one of ssh_alias, connection_file, or explicit hostname/user/identity_file"
            )
        if self.connection_file:
            if any(ord(char) < 32 or ord(char) == 127 for char in self.connection_file):
                raise ValueError("SSH connection_file must not contain control characters")
            if not (
                Path(self.connection_file).is_absolute()
                or PureWindowsPath(self.connection_file).is_absolute()
            ):
                raise ValueError("SSH connection_file must be an absolute path")
        elif self.ssh_alias:
            pass
        else:
            if not all(direct_values):
                raise ValueError(
                    "Explicit SSH host requires hostname, user, and identity_file"
                )
            host_allowed = set(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
            )
            user_allowed = set(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            )
            if any(char not in host_allowed for char in self.hostname):
                raise ValueError(
                    "SSH hostname must use letters, numbers, dots, or hyphens"
                )
            if any(char not in user_allowed for char in self.user):
                raise ValueError(
                    "SSH user must use letters, numbers, dots, underscores, or hyphens"
                )
            if any(ord(char) < 32 or ord(char) == 127 for char in self.identity_file):
                raise ValueError("SSH identity_file must not contain control characters")
            if not (
                Path(self.identity_file).is_absolute()
                or PureWindowsPath(self.identity_file).is_absolute()
            ):
                raise ValueError("SSH identity_file must be an absolute path")
        command_ids = [profile.command_id for profile in self.command_profiles]
        if len(command_ids) != len(set(command_ids)):
            raise ValueError("SSH command_id values must be unique per host")
        roots = [root.rstrip("/") or "/" for root in self.allowed_remote_roots]
        if any(not root.startswith("/") or "\\" in root for root in roots):
            raise ValueError("SSH allowed_remote_roots must be absolute POSIX paths")
        if len(roots) != len(set(roots)):
            raise ValueError("SSH allowed_remote_roots must be unique")
        self.allowed_remote_roots = roots
        executables = [value.strip() for value in self.allowed_executables]
        if any(not value for value in executables):
            raise ValueError("SSH allowed_executables must not contain empty values")
        if len(executables) != len(set(executables)):
            raise ValueError("SSH allowed_executables must be unique")
        self.allowed_executables = executables
        return self


class SSHConfig(BaseModel):
    enabled: bool = False
    executable: str = "ssh"
    scp_executable: str = "scp"
    max_output_bytes: int = Field(default=100000, ge=1024, le=5000000)
    max_transfer_bytes: int = Field(default=500000000, ge=1024, le=5000000000)
    transfer_timeout_seconds: int = Field(default=1800, ge=1, le=7200)
    allow_transfer: bool = False
    allow_deploy: bool = False
    allow_admin: bool = False
    allow_delete: bool = False
    allow_reboot: bool = False
    confirmation_token: str = Field(
        default="CONFIRM_SSH_HIGH_RISK", min_length=8, max_length=128
    )
    hosts: Dict[str, SSHHostConfig] = Field(default_factory=dict)


class CloudflareSecretDestinationConfig(BaseModel):
    type: Literal["env_file"] = "env_file"
    path: str
    variable: str

    @model_validator(mode="after")
    def validate_destination(self) -> "CloudflareSecretDestinationConfig":
        raw_path = str(self.path or "").strip().replace("\\", "/")
        windows_path = PureWindowsPath(raw_path)
        if (
            not raw_path
            or len(raw_path) > 512
            or windows_path.is_absolute()
            or windows_path.drive
            or raw_path.startswith("/")
            or ":" in raw_path
            or any(part == ".." for part in windows_path.parts)
            or any(ord(char) < 32 or ord(char) == 127 for char in raw_path)
        ):
            raise ValueError(
                "Cloudflare secret destination path must be a safe repository-relative path"
            )
        variable = str(self.variable or "").strip()
        if (
            not variable
            or len(variable) > 128
            or variable[0].isdigit()
            or any(not (char.isalnum() or char == "_") for char in variable)
        ):
            raise ValueError(
                "Cloudflare secret destination variable must be an environment variable name"
            )
        self.path = raw_path
        self.variable = variable
        return self


class CloudflareTurnstileConfig(BaseModel):
    secret_destination: CloudflareSecretDestinationConfig | None = None


class CloudflareProfileConfig(BaseModel):
    account_id: str = ""
    account_id_env: str = ""
    zone_id: str = ""
    zone_id_env: str = ""
    zone_name: str = ""
    allowed_dns_names: List[str] = Field(default_factory=list)
    allowed_ruleset_phases: List[str] = Field(default_factory=list)
    allowed_tunnel_ids: List[str] = Field(default_factory=list)
    allowed_turnstile_sitekeys: List[str] = Field(default_factory=list)
    turnstile: CloudflareTurnstileConfig = Field(
        default_factory=CloudflareTurnstileConfig
    )

    @model_validator(mode="after")
    def validate_profile(self) -> "CloudflareProfileConfig":
        hex_chars = set("0123456789abcdef")
        for field_name in ("account_id", "zone_id"):
            value = str(getattr(self, field_name) or "").strip().lower()
            if value and (
                len(value) != 32 or any(char not in hex_chars for char in value)
            ):
                raise ValueError(
                    f"Cloudflare {field_name} must be a 32-character hex ID"
                )
            setattr(self, field_name, value)
        env_chars = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
        )
        for field_name in ("account_id_env", "zone_id_env"):
            value = str(getattr(self, field_name) or "").strip()
            if value and (
                value[0].isdigit() or any(char not in env_chars for char in value)
            ):
                raise ValueError(
                    f"Cloudflare {field_name} must be an environment variable name"
                )
            setattr(self, field_name, value)
        zone_name = str(self.zone_name or "").strip().lower().rstrip(".")
        if zone_name and (
            len(zone_name) > 253
            or "." not in zone_name
            or any(
                not label
                or len(label) > 63
                or label.startswith("-")
                or label.endswith("-")
                or any(not (char.isalnum() or char == "-") for char in label)
                for label in zone_name.split(".")
            )
        ):
            raise ValueError("Cloudflare zone_name must be a valid DNS zone name")
        self.zone_name = zone_name
        normalized_names: list[str] = []
        for name in self.allowed_dns_names:
            value = str(name or "").strip().lower().rstrip(".")
            if not value:
                raise ValueError(
                    "Cloudflare allowed_dns_names must not contain empty values"
                )
            if zone_name and value != zone_name and not value.endswith(f".{zone_name}"):
                raise ValueError(
                    "Cloudflare allowed DNS names must remain inside zone_name"
                )
            normalized_names.append(value)
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("Cloudflare allowed_dns_names must be unique")
        self.allowed_dns_names = normalized_names
        phases = [str(value or "").strip() for value in self.allowed_ruleset_phases]
        if any(
            not value
            or len(value) > 128
            or any(not (char.isalnum() or char in "_-") for char in value)
            for value in phases
        ):
            raise ValueError("Cloudflare ruleset phases contain an invalid value")
        if len(phases) != len(set(phases)):
            raise ValueError("Cloudflare allowed_ruleset_phases must be unique")
        self.allowed_ruleset_phases = phases
        tunnel_ids = [
            str(value or "").strip().lower() for value in self.allowed_tunnel_ids
        ]
        for value in tunnel_ids:
            parts = value.split("-")
            if [len(part) for part in parts] != [8, 4, 4, 4, 12] or any(
                char not in hex_chars for part in parts for char in part
            ):
                raise ValueError("Cloudflare tunnel IDs must be UUID values")
        if len(tunnel_ids) != len(set(tunnel_ids)):
            raise ValueError("Cloudflare allowed_tunnel_ids must be unique")
        self.allowed_tunnel_ids = tunnel_ids
        turnstile_sitekeys = [
            str(value or "").strip() for value in self.allowed_turnstile_sitekeys
        ]
        if any(
            not value
            or len(value) > 64
            or any(not (char.isalnum() or char in "_-") for char in value)
            for value in turnstile_sitekeys
        ):
            raise ValueError(
                "Cloudflare allowed_turnstile_sitekeys contain an invalid value"
            )
        if len(turnstile_sitekeys) != len(set(turnstile_sitekeys)):
            raise ValueError("Cloudflare allowed_turnstile_sitekeys must be unique")
        self.allowed_turnstile_sitekeys = turnstile_sitekeys
        return self


class CloudflareConfig(BaseModel):
    enabled: bool = False
    api_base_url: str = "https://api.cloudflare.com/client/v4"
    token_env: str = "CLOUDFLARE_API_TOKEN"
    env_file: str = ".env"
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_output_bytes: int = Field(default=500000, ge=1024, le=5000000)
    allow_dns_write: bool = False
    allow_cache_purge: bool = False
    allow_zone_settings: bool = False
    allow_rulesets: bool = False
    allow_tunnels: bool = False
    allow_turnstile: bool = False
    allow_turnstile_write: bool = False
    allow_turnstile_secret_rotation: bool = False
    allow_turnstile_delete: bool = False
    allow_delete: bool = False
    confirmation_token: str = Field(
        default="CONFIRM_CLOUDFLARE_HIGH_RISK", min_length=8, max_length=128
    )
    profiles: Dict[str, CloudflareProfileConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_cloudflare(self) -> "CloudflareConfig":
        self.api_base_url = self.api_base_url.rstrip("/")
        if self.api_base_url != "https://api.cloudflare.com/client/v4":
            raise ValueError(
                "Cloudflare api_base_url must use the official client v4 endpoint"
            )
        env_chars = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
        )
        if (
            not self.token_env
            or self.token_env[0].isdigit()
            or any(char not in env_chars for char in self.token_env)
        ):
            raise ValueError(
                "Cloudflare token_env must be an environment variable name"
            )
        env_file = str(self.env_file or "").strip().replace("\\", "/")
        env_parts = Path(env_file).parts
        if (
            not env_file
            or env_file.startswith("/")
            or ":" in env_file
            or ".." in env_parts
        ):
            raise ValueError(
                "Cloudflare env_file must be a safe path relative to config.yaml"
            )
        self.env_file = env_file
        return self


class ExternalFixturesConfig(BaseModel):
    enabled: bool = False
    allowed_hosts: List[str] = Field(default_factory=list)
    max_bytes: int = Field(default=20_000_000, ge=1, le=500_000_000)
    timeout_seconds: int = Field(default=60, ge=1, le=600)

    @model_validator(mode="after")
    def validate_allowed_hosts(self) -> "ExternalFixturesConfig":
        normalized: list[str] = []
        for host in self.allowed_hosts:
            value = host.strip().lower().rstrip(".")
            if not value or any(character in value for character in "/:@*?"):
                raise ValueError(f"Invalid external fixture host: {host!r}")
            normalized.append(value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("External fixture hosts must be unique")
        self.allowed_hosts = normalized
        return self


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
    codex_router_default_validation_commands: list[str] = Field(
        default_factory=lambda: ["pytest", "pip_check"]
    )
    codex_router_packet_dir: str | None = None
    codex_router_use_local_model_summary: bool = True
    codex_router_redact_sensitive: bool = True
    codex_router_block_sensitive: bool = True
    codex_router_require_policy_approval: bool = True


class LocalSupervisorConfig(BaseModel):
    supervisor_enabled: bool = True
    supervisor_runs_dir: str | None = None
    supervisor_default_validation_commands: list[str] = Field(
        default_factory=lambda: ["git_status", "pytest", "pip_check"]
    )
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
    local_coding_allowed_path_globs: list[str] = Field(
        default_factory=lambda: [
            "README.md",
            "README.*",
            "docs/**/*.md",
            "AGENTS.md",
            "PLANS.md",
        ]
    )
    local_coding_allowed_extensions: list[str] = Field(
        default_factory=lambda: [".md", ".txt", ".json"]
    )
    local_coding_block_source_code: bool = True
    local_coding_block_tests: bool = True
    local_coding_max_file_bytes: int = Field(default=20000, ge=1, le=1000000)
    local_coding_max_patch_bytes: int = Field(default=4000, ge=1, le=1000000)
    local_coding_max_changed_lines: int = Field(default=20, ge=1, le=10000)
    local_coding_max_operations: int = Field(default=3, ge=1, le=100)
    local_coding_require_approval: bool = True
    local_coding_auto_rollback_on_validation_failure: bool = False
    local_coding_default_validation_commands: list[str] = Field(
        default_factory=lambda: ["git_status"]
    )
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
    file: SupervisorFileNotificationSinkConfig = Field(
        default_factory=SupervisorFileNotificationSinkConfig
    )
    webhook: SupervisorWebhookNotificationSinkConfig = Field(
        default_factory=SupervisorWebhookNotificationSinkConfig
    )
    windows_toast: SupervisorWindowsToastNotificationSinkConfig = Field(
        default_factory=SupervisorWindowsToastNotificationSinkConfig
    )


class SupervisorsConfig(BaseModel):
    default_autonomy_profile: str = "balanced"
    autonomy_profiles: Dict[str, SupervisorAutonomyProfile] = Field(
        default_factory=lambda: {
            "balanced": SupervisorAutonomyProfile(),
            "conservative": SupervisorAutonomyProfile(
                max_implementation_tier=1, require_tests_for_non_docs_changes=True
            ),
        }
    )
    notifications: SupervisorNotificationsConfig = Field(
        default_factory=SupervisorNotificationsConfig
    )

    @model_validator(mode="after")
    def validate_default_profile(self) -> "SupervisorsConfig":
        if self.default_autonomy_profile not in self.autonomy_profiles:
            raise ValueError(
                f"Unknown default_autonomy_profile: {self.default_autonomy_profile}"
            )
        return self

    def effective_profile(self) -> SupervisorAutonomyProfile:
        return self.autonomy_profiles[self.default_autonomy_profile]


class AppConfig(BaseModel):
    repos: Dict[str, RepoConfig]
    runs_dir: str = "runs"
    ssh: SSHConfig = Field(default_factory=SSHConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)
    external_fixtures: ExternalFixturesConfig = Field(
        default_factory=ExternalFixturesConfig
    )
    codex: CodexConfig = Field(default_factory=CodexConfig)
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    local_model: LocalModelConfig = Field(default_factory=LocalModelConfig)
    return_loop: ReturnLoopConfig = Field(default_factory=ReturnLoopConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    autonomy: AutonomyConfig = Field(default_factory=AutonomyConfig)
    codex_router: CodexRouterConfig = Field(default_factory=CodexRouterConfig)
    local_supervisor: LocalSupervisorConfig = Field(
        default_factory=LocalSupervisorConfig
    )
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


def load_config(
    path: str | Path = "config.yaml", *, validate_repos: bool = True
) -> AppConfig:
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
                raise ValueError(
                    f"Repo '{name}' path does not contain .git: {repo_path}"
                )

    return config


def resolve_repo(config: AppConfig, repo_name: str) -> Path:
    _, repo_path, _ = resolve_repo_identity(config, repo_name)
    return repo_path


def resolve_repo_config(config: AppConfig, repo_name: str) -> tuple[str, RepoConfig]:
    if repo_name in config.repos:
        return repo_name, config.repos[repo_name]

    folded_lookup = {name.casefold(): name for name in config.repos}
    matched_name = folded_lookup.get(repo_name.casefold())
    if matched_name is None:
        raise ValueError(f"Unknown repo_name: {repo_name}")
    return matched_name, config.repos[matched_name]


def resolve_repo_identity(
    config: AppConfig, repo_name: str
) -> tuple[str, Path, RepoConfig]:
    """Resolve one canonical repository identity for every tool family."""
    canonical_name, repo = resolve_repo_config(config, repo_name)
    repo_path = Path(repo.path).resolve()
    if not repo_path.exists():
        raise ValueError(f"Repo path does not exist: {repo_path}")
    if not (repo_path / ".git").exists():
        raise ValueError(f"Repo path does not contain .git: {repo_path}")
    return canonical_name, repo_path, repo
