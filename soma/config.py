from __future__ import annotations

import subprocess
from pathlib import Path, PureWindowsPath
from typing import Dict, List, Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class ExecutableProfileConfig(BaseModel):
    profile_id: str
    enabled: bool = False
    executable_path: str
    expected_sha256: str = Field(default="", pattern=r"^[A-Fa-f0-9]{64}$|^$")
    expected_signer: str = ""
    expected_version: str = ""
    target: Literal["local", "remote"] = "local"
    working_directory_policy: Literal["service_default", "fixed", "arbitrary"] = (
        "service_default"
    )
    fixed_working_directory: str = ""
    environment_policy: Literal["inherit", "fixed", "arbitrary"] = "inherit"
    fixed_environment: Dict[str, str] = Field(default_factory=dict)
    stdin_mode: Literal["none", "text", "bytes", "file", "protected_reference"] = (
        "none"
    )
    stdout_mode: Literal["text", "bytes", "file", "protected_artifact"] = (
        "protected_artifact"
    )
    stderr_mode: Literal["text", "bytes", "file", "protected_artifact"] = (
        "protected_artifact"
    )
    timeout_seconds: int | None = Field(default=600, ge=1, le=604800)
    allow_no_timeout: bool = False
    cancellation_policy: Literal["process_only", "process_tree"] = "process_tree"
    public_output_max_bytes: int = Field(default=100000, ge=1024, le=5000000)
    preserve_protected_artifacts: bool = True
    autonomy_profile: Literal["permissive"] = "permissive"
    unrestricted_argv: bool = False
    unrestricted_paths: bool = False
    unrestricted_environment: bool = False
    unrestricted_network: bool = False
    unrestricted_child_processes: bool = False

    @model_validator(mode="after")
    def validate_profile(self) -> "ExecutableProfileConfig":
        allowed = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        if not self.profile_id or any(char not in allowed for char in self.profile_id):
            raise ValueError(
                "Executable profile_id must use letters, numbers, _ or -"
            )
        executable = Path(self.executable_path)
        if not (
            executable.is_absolute()
            or PureWindowsPath(self.executable_path).is_absolute()
        ):
            raise ValueError("Executable profile executable_path must be absolute")
        if self.working_directory_policy == "fixed":
            if not self.fixed_working_directory:
                raise ValueError(
                    "Fixed working-directory policy requires fixed_working_directory"
                )
            working_directory = Path(self.fixed_working_directory)
            if not (
                working_directory.is_absolute()
                or PureWindowsPath(self.fixed_working_directory).is_absolute()
            ):
                raise ValueError(
                    "Executable profile fixed_working_directory must be absolute"
                )
        elif self.fixed_working_directory:
            raise ValueError(
                "fixed_working_directory is only valid with fixed working-directory policy"
            )
        if self.timeout_seconds is None and not self.allow_no_timeout:
            raise ValueError(
                "No-timeout executable profiles require allow_no_timeout=true"
            )
        if self.expected_sha256:
            self.expected_sha256 = self.expected_sha256.lower()
        return self


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


ORDINARY_VALIDATION_COMMAND_IDS = frozenset(
    {"eslint", "typecheck", "vitest", "frontend_validate"}
)


def _powershell_literal(value: object) -> str:
    return "'" + str(value).replace("'", "''") + "'"


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

    def command_profile_migration_report(self, repo_name: str) -> dict[str, object]:
        candidates: list[dict[str, object]] = []
        for profile in self.command_profiles:
            command_id = str(profile.get("command_id", ""))
            if command_id not in ORDINARY_VALIDATION_COMMAND_IDS:
                continue
            argv = [str(value) for value in profile.get("argv", [])]
            invocation = "& " + " ".join(_powershell_literal(value) for value in argv)
            invocation += "; exit $LASTEXITCODE"
            candidates.append(
                {
                    "command_id": command_id,
                    "configured_profile": dict(profile),
                    "replacement": {
                        "operation": "powershell",
                        "repo_name": repo_name,
                        "working_directory": self.path,
                        "argv": [
                            "-NoLogo",
                            "-NoProfile",
                            "-NonInteractive",
                            "-Command",
                            invocation,
                        ],
                        "timeout_seconds": profile.get("timeout_seconds"),
                    },
                }
            )
        return {
            "migration_id": "ordinary_validation_command_profiles_v1",
            "migration_required": bool(candidates),
            "repo_name": repo_name,
            "candidate_command_ids": [
                str(candidate["command_id"]) for candidate in candidates
            ],
            "candidates": candidates,
            "rollback": {"command_profiles": [dict(item) for item in self.command_profiles]},
            "preserves_durable_history": True,
        }


class SSHCommandProfileConfig(BaseModel):
    command_id: str
    argv: List[str] = Field(default_factory=list, min_length=1, max_length=64)
    timeout_seconds: int = Field(default=120, ge=1, le=86400)
    description: str = ""
    writes_remote: bool = False
    watchdog_eligible: bool = False


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


class SSHProjectBindingConfig(SSHDeploymentProfileConfig):
    host_id: str
    required_capabilities: List[str] = Field(default_factory=list)
    allow_first_deployment: bool = False
    expected_writable_paths: List[str] = Field(default_factory=list)
    expected_read_only_paths: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_project_binding(self) -> "SSHProjectBindingConfig":
        allowed_id = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        self.host_id = self.host_id.strip()
        if not self.host_id or any(char not in allowed_id for char in self.host_id):
            raise ValueError(
                "SSH project binding host_id must use letters, numbers, _ or -"
            )
        capabilities: list[str] = []
        for raw_name in self.required_capabilities:
            name = str(raw_name or "").strip().lower()
            if (
                not name
                or len(name) > 64
                or not name[0].isalpha()
                or any(not (char.isalnum() or char == "_") for char in name)
            ):
                raise ValueError(
                    "SSH project binding required capabilities must use lowercase names"
                )
            capabilities.append(name)
        if len(capabilities) != len(set(capabilities)):
            raise ValueError(
                "SSH project binding required capabilities must be unique"
            )
        self.required_capabilities = capabilities
        for field_name in (
            "expected_writable_paths",
            "expected_read_only_paths",
        ):
            normalized: list[str] = []
            for raw_path in getattr(self, field_name):
                path = str(raw_path or "").strip().rstrip("/") or "/"
                if not path.startswith("/") or "\\" in path:
                    raise ValueError(
                        f"SSH project binding {field_name} must contain absolute POSIX paths"
                    )
                normalized.append(path)
            if len(normalized) != len(set(normalized)):
                raise ValueError(
                    f"SSH project binding {field_name} must contain unique paths"
                )
            setattr(self, field_name, normalized)
        return self


class SSHWatchdogConfig(BaseModel):
    enabled: bool = False
    enforcement_mode: Literal["observe_only", "terminate"] = "observe_only"
    allow_automatic_termination: bool = False
    poll_interval_seconds: int = Field(default=30, ge=5, le=300)
    consecutive_breaches: int = Field(default=2, ge=1, le=10)
    termination_grace_seconds: int = Field(default=5, ge=1, le=30)
    max_gpu_memory_percent: float = Field(default=95.0, gt=0, le=100)
    max_gpu_temperature_c: float = Field(default=90.0, gt=0, le=125)
    max_system_memory_percent: float = Field(default=95.0, gt=0, le=100)
    min_disk_free_percent: float = Field(default=5.0, ge=0, lt=100)


class SSHCredentialSourceConfig(BaseModel):
    type: Literal[
        "env_file",
        "process_environment",
        "openssh_config",
        "connection_file",
        "key_file",
    ]
    path: str = ""
    alias: str = ""
    hostname: str = ""
    user: str = ""
    port: int = Field(default=22, ge=1, le=65535)
    expected_host_key: str = ""

    @model_validator(mode="after")
    def validate_source(self) -> "SSHCredentialSourceConfig":
        self.path = self.path.strip()
        self.alias = self.alias.strip()
        self.hostname = self.hostname.strip()
        self.user = self.user.strip()
        self.expected_host_key = self.expected_host_key.strip()
        if self.type == "process_environment":
            if self.path or self.alias or self.hostname or self.user or self.port != 22:
                raise ValueError(
                    "process_environment SSH credential sources cannot store endpoint values"
                )
            return self
        if not self.path:
            raise ValueError(f"{self.type} SSH credential source requires path")
        if not (
            Path(self.path).is_absolute()
            or PureWindowsPath(self.path).is_absolute()
        ):
            raise ValueError("SSH credential source path must be absolute")
        if any(ord(char) < 32 or ord(char) == 127 for char in self.path):
            raise ValueError("SSH credential source path contains control characters")
        if self.type == "openssh_config":
            if not self.alias:
                raise ValueError("openssh_config SSH credential source requires alias")
        elif self.alias:
            raise ValueError("SSH credential source alias is valid only for openssh_config")
        if self.type == "key_file":
            if not self.hostname or not self.user:
                raise ValueError(
                    "key_file SSH credential source requires non-secret hostname and user"
                )
        elif self.hostname or self.user or self.port != 22:
            raise ValueError(
                "SSH credential source endpoint values are valid only for key_file"
            )
        return self


class SSHCredentialBindingConfig(BaseModel):
    source_id: str
    host_key_policy: Literal["pinned", "tofu", "rotation"] = "pinned"
    hostname: str = ""
    user: str = ""
    port: str = ""
    identity_file: str = ""
    expected_host_key: str = ""

    @model_validator(mode="after")
    def validate_binding(self) -> "SSHCredentialBindingConfig":
        allowed = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        self.source_id = self.source_id.strip()
        if not self.source_id or any(char not in allowed for char in self.source_id):
            raise ValueError(
                "SSH credential source_id must use letters, numbers, _ or -"
            )
        for field_name in (
            "hostname",
            "user",
            "port",
            "identity_file",
            "expected_host_key",
        ):
            value = str(getattr(self, field_name) or "").strip()
            if value and (
                not (value[0].isalpha() or value[0] == "_")
                or any(not (char.isalnum() or char == "_") for char in value)
            ):
                raise ValueError(
                    f"SSH credential binding {field_name} must name one environment variable"
                )
            setattr(self, field_name, value)
        return self


class SSHHostConfig(BaseModel):
    ssh_alias: str = ""
    connection_file: str = ""
    hostname: str = ""
    user: str = ""
    port: int = Field(default=22, ge=1, le=65535)
    identity_file: str = ""
    credential_binding: SSHCredentialBindingConfig | None = None
    connect_timeout_seconds: int = Field(default=10, ge=1, le=60)
    force_pty: bool = False
    use_sudo: bool = False
    allowed_remote_roots: List[str] = Field(default_factory=list)
    allowed_executables: List[str] = Field(default_factory=list)
    deployment_profiles: Dict[str, SSHDeploymentProfileConfig] = Field(
        default_factory=dict
    )
    command_profiles: List[SSHCommandProfileConfig] = Field(default_factory=list)
    watchdog: SSHWatchdogConfig = Field(default_factory=SSHWatchdogConfig)

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
                self.credential_binding is not None,
            )
        )
        if configured_modes != 1:
            raise ValueError(
                "SSH host must use exactly one of ssh_alias, connection_file, explicit hostname/user/identity_file, or credential_binding"
            )
        if self.connection_file:
            if any(ord(char) < 32 or ord(char) == 127 for char in self.connection_file):
                raise ValueError(
                    "SSH connection_file must not contain control characters"
                )
            if not (
                Path(self.connection_file).is_absolute()
                or PureWindowsPath(self.connection_file).is_absolute()
            ):
                raise ValueError("SSH connection_file must be an absolute path")
        elif self.ssh_alias or self.credential_binding is not None:
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
                raise ValueError(
                    "SSH identity_file must not contain control characters"
                )
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
    active_autonomy_profiles: List[Literal["permissive"]] = Field(
        default_factory=lambda: ["permissive"],
        min_length=1,
        max_length=1,
    )
    allow_transfer: bool = False
    allow_deploy: bool = False
    allow_admin: bool = False
    allow_delete: bool = False
    allow_reboot: bool = False
    confirmation_token: str = Field(
        default="CONFIRM_SSH_HIGH_RISK", min_length=8, max_length=128
    )
    credential_sources: Dict[str, SSHCredentialSourceConfig] = Field(
        default_factory=dict
    )
    hosts: Dict[str, SSHHostConfig] = Field(default_factory=dict)
    project_bindings: Dict[str, SSHProjectBindingConfig] = Field(
        default_factory=dict
    )

    @model_validator(mode="after")
    def validate_credential_bindings(self) -> "SSHConfig":
        allowed = set(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        )
        for source_id in self.credential_sources:
            if not source_id or any(char not in allowed for char in source_id):
                raise ValueError(
                    "SSH credential source mapping keys must use letters, numbers, _ or -"
                )
        for host_id, host in self.hosts.items():
            binding = host.credential_binding
            if binding is None:
                continue
            source = self.credential_sources.get(binding.source_id)
            if source is None:
                raise ValueError(
                    f"SSH host {host_id!r} references unknown credential source {binding.source_id!r}"
                )
            references = {
                "hostname": binding.hostname,
                "user": binding.user,
                "port": binding.port,
                "identity_file": binding.identity_file,
                "expected_host_key": binding.expected_host_key,
            }
            populated = {name for name, value in references.items() if value}
            if source.type in {"env_file", "process_environment"}:
                required = {"hostname", "user", "identity_file"}
                missing = sorted(required - populated)
                if missing:
                    raise ValueError(
                        f"SSH host {host_id!r} credential binding is missing references: {missing}"
                    )
            elif populated:
                raise ValueError(
                    f"SSH host {host_id!r} uses field references with non-environment source {source.type!r}"
                )
        for binding_id, project_binding in self.project_bindings.items():
            if not binding_id or any(char not in allowed for char in binding_id):
                raise ValueError(
                    "SSH project binding IDs must use letters, numbers, _ or -"
                )
            host = self.hosts.get(project_binding.host_id)
            if host is None:
                raise ValueError(
                    f"SSH project binding {binding_id!r} references unknown host {project_binding.host_id!r}"
                )
            normalized_root = project_binding.remote_root.rstrip("/") or "/"
            if not any(
                normalized_root == root
                or normalized_root.startswith(root.rstrip("/") + "/")
                for root in host.allowed_remote_roots
            ):
                raise ValueError(
                    f"SSH project binding {binding_id!r} remote_root is outside host allowed_remote_roots"
                )
            if project_binding.health_command_id:
                command_ids = {
                    profile.command_id for profile in host.command_profiles
                }
                if project_binding.health_command_id not in command_ids:
                    raise ValueError(
                        f"SSH project binding {binding_id!r} references unknown health_command_id"
                    )
        return self

    def autonomy_profile_migration_report(self) -> dict[str, object]:
        configured = list(self.active_autonomy_profiles)
        target = ["permissive"]
        return {
            "migration_id": "ssh_active_autonomy_profiles_v1",
            "migration_required": False,
            "configured_profiles": configured,
            "legacy_profiles": [],
            "target_profiles": target,
            "rollback": {"active_autonomy_profiles": configured},
            "replacement": {"active_autonomy_profiles": target},
            "preserves_durable_history": True,
        }


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


class GeminiConfig(BaseModel):
    enabled: bool = False


class LocalModelConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://localhost:11434/v1"
    model: str = "llama3.2"
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=32768)


class HermesToolLimitConfig(BaseModel):
    pattern: str = Field(min_length=1, max_length=256)
    max_concurrent: int | None = Field(default=None, ge=1, le=1000)
    min_interval_seconds: float = Field(default=0.0, ge=0.0, le=3600.0)


class HermesServiceConfig(BaseModel):
    enabled: bool = False
    checkout: str = ""
    python_executable: str = ""
    hermes_home: str = ""
    worker_count: int = Field(default=2, ge=1, le=32)
    max_output_bytes: int | None = Field(default=None, ge=256, le=1_000_000)
    startup_timeout_seconds: int = Field(default=120, ge=1, le=600)
    state_path: str = ""
    fallback_enabled: bool = True
    fallback_profile_id: str = "hermes_python"
    fallback_repo_name: str = ""
    tool_limits: list[HermesToolLimitConfig] = Field(default_factory=list)


class ReturnLoopConfig(BaseModel):
    return_loop_enabled: bool = True
    max_resume_prompt_bytes: int = Field(default=20000, ge=1, le=1000000)
    max_report_bytes: int = Field(default=100000, ge=1, le=5000000)
    manifest_schema_version: str = "1"
    conversation_target: str = "soma_gpt"
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
    autonomy_default_profile: str = "balanced"
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


class ExternalCoderConfig(BaseModel):
    """Bounded, provider-neutral handoff artifact generation.

    Handoffs are inert export artifacts only. Neither Soma nor its controller
    invokes an external coding agent; a human may use the artifact outside
    Soma without creating a run, worker, fallback, or PowerShell launch path.
    """

    external_coder_handoff_enabled: bool = True
    external_coder_max_context_bytes: int = Field(default=60000, ge=1000, le=1000000)
    external_coder_max_file_bytes: int = Field(default=20000, ge=1, le=500000)
    external_coder_max_log_bytes: int = Field(default=12000, ge=1, le=500000)
    external_coder_max_worktree_status_bytes: int = Field(
        default=8000, ge=1, le=500000
    )
    external_coder_default_validation_commands: list[str] = Field(
        default_factory=lambda: ["pytest", "pip_check"]
    )
    external_coder_handoff_dir: str | None = None
    external_coder_use_local_model_summary: bool = True
    external_coder_redact_sensitive: bool = True
    external_coder_block_sensitive: bool = True
    external_coder_require_policy_approval: bool = True


class LocalSupervisorConfig(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def reject_removed_supervisor_runner_flag(cls, data):
        if isinstance(data, dict) and "supervisor_codex_invocation_enabled" in data:
            raise ValueError(
                "Removed configuration key 'supervisor_codex_invocation_enabled': "
                "no supervisor model-agent invocation exists; remove the key."
            )
        return data

    supervisor_enabled: bool = True
    supervisor_runs_dir: str | None = None
    supervisor_default_validation_commands: list[str] = Field(
        default_factory=lambda: ["git_status", "pytest", "pip_check"]
    )
    supervisor_max_retries: int = 0
    supervisor_use_local_model_plan: bool = True
    supervisor_use_memory_context: bool = True
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
    default_autonomy_profile: str = "permissive"
    autonomy_profiles: Dict[str, SupervisorAutonomyProfile] = Field(
        default_factory=lambda: {
            "permissive": SupervisorAutonomyProfile(
                max_plan_tier=3, max_implementation_tier=3
            ),
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


class ParallelExecutionConfig(BaseModel):
    enabled: bool = False
    autonomy_profile: Literal["permissive"] = "permissive"
    default_mode: Literal["all_at_once"] = "all_at_once"
    max_concurrent_powershell: int | None = Field(default=None, ge=1)
    return_after: Literal["launch_accepted"] = "launch_accepted"
    repository_lock_policy: Literal["caller_selected"] = "caller_selected"


class TradingConfig(BaseModel):
    enabled: bool = False
    provider: Literal["mt5"] = "mt5"
    account_environment: Literal["demo"] = "demo"
    terminal_path: str = ""
    symbol: str = "BITCOIN_i"
    provider_utc_offset_seconds: int = Field(default=0, ge=-86_400, le=86_400)
    maximum_tick_age_seconds: int = Field(default=120, ge=1, le=3_600)
    # The chart period, analysis depth, and expected-closure calendar are
    # named here but defined by the trading domain. They stay plain bounded
    # strings so Soma never carries its own copy of the timeframe registry
    # or the session calendars: TradingLabSettings resolves and validates
    # them when trading_lab_adapter maps this config onto it.
    timeframe: str = Field(default="H1", min_length=1, max_length=16)
    candle_count: int = Field(default=200, ge=10, le=5_000)
    session_calendar: str = Field(
        default="crypto_weekend_maintenance", min_length=1, max_length=64
    )
    boundary_probe_bars: int = Field(default=3, ge=2, le=50)
    # The execution mode and policy a public request inherits when it omits
    # them. One authoritative pair: before this existed, an omitted field
    # meant different things on different gateways — the companion decision
    # defaulted to internal_paper/hourly_fixed_bracket_v1 while a guarded
    # action defaulted to internal_paper/agentic_demo_v1. Changing the
    # operating mode is now one configuration edit that every public path
    # observes, rather than an argument each caller must remember to repeat
    # identically on every call.
    default_execution_mode: Literal["internal_paper", "broker_demo"] = "internal_paper"
    default_policy_id: Literal["hourly_fixed_bracket_v1", "agentic_demo_v1"] = (
        "agentic_demo_v1"
    )
    # Whether the mutating runtime-control operations are reachable at all.
    # This is an owner-set capability switch on one domain provider, the same
    # shape as ``enabled`` above; it is not a per-command approval, a
    # permission tier, or an autonomy gate. Runtime reads stay available
    # either way, so an unattended companion cycle can always observe runtime
    # state without being able to start it, stop it, or lift the kill switch.
    runtime_control_mutations_enabled: bool = True

    @model_validator(mode="after")
    def validate_terminal_path(self) -> "TradingConfig":
        if self.terminal_path:
            terminal = Path(self.terminal_path)
            if not (
                terminal.is_absolute()
                or PureWindowsPath(self.terminal_path).is_absolute()
            ):
                raise ValueError("Trading terminal_path must be absolute")
        if not self.symbol.strip():
            raise ValueError("Trading symbol must not be empty")
        self.symbol = self.symbol.strip()
        # Trimmed, not interpreted. Whether "1H" or "crypto_weekend_maintenance"
        # names anything real is the trading domain's question to answer.
        self.timeframe = self.timeframe.strip()
        self.session_calendar = self.session_calendar.strip()
        if not self.timeframe or not self.session_calendar:
            raise ValueError(
                "Trading timeframe and session_calendar must not be empty"
            )
        return self


class AppConfig(BaseModel):
    repos: Dict[str, RepoConfig]
    runs_dir: str = "runs"
    executable_profiles: Dict[str, ExecutableProfileConfig] = Field(
        default_factory=dict
    )
    parallel_execution: ParallelExecutionConfig = Field(
        default_factory=ParallelExecutionConfig
    )
    trading: TradingConfig = Field(default_factory=TradingConfig)
    ssh: SSHConfig = Field(default_factory=SSHConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    cloudflare: CloudflareConfig = Field(default_factory=CloudflareConfig)
    external_fixtures: ExternalFixturesConfig = Field(
        default_factory=ExternalFixturesConfig
    )
    gemini: GeminiConfig = Field(default_factory=GeminiConfig)
    local_model: LocalModelConfig = Field(default_factory=LocalModelConfig)
    hermes_service: HermesServiceConfig = Field(
        default_factory=HermesServiceConfig
    )
    return_loop: ReturnLoopConfig = Field(default_factory=ReturnLoopConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    autonomy: AutonomyConfig = Field(default_factory=AutonomyConfig)
    external_coder: ExternalCoderConfig = Field(default_factory=ExternalCoderConfig)
    local_supervisor: LocalSupervisorConfig = Field(
        default_factory=LocalSupervisorConfig
    )
    local_coding: LocalCodingConfig = Field(default_factory=LocalCodingConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    supervisors: SupervisorsConfig = Field(default_factory=SupervisorsConfig)
    config_dir: Path = Field(default_factory=lambda: Path.cwd(), exclude=True)

    @model_validator(mode="before")
    @classmethod
    def reject_removed_runner_sections(cls, data):
        if isinstance(data, dict):
            present = sorted(
                key for key in ("codex", "codex_router") if key in data
            )
            if present:
                raise ValueError(
                    "Obsolete configuration section(s) "
                    + ", ".join(repr(key) for key in present)
                    + ": no model-agent integration or execution route exists. "
                    "Remove them; inert handoff artifact generation is configured "
                    "under 'external_coder'."
                )
        return data

    @model_validator(mode="after")
    def validate_executable_profiles(self) -> "AppConfig":
        for profile_id, profile in self.executable_profiles.items():
            if profile_id != profile.profile_id:
                raise ValueError(
                    "Executable profile mapping key must match profile_id: "
                    f"{profile_id!r} != {profile.profile_id!r}"
                )
        return self

    @model_validator(mode="after")
    def validate_ssh_project_binding_repositories(self) -> "AppConfig":
        for binding_id, binding in self.ssh.project_bindings.items():
            if binding.repo_name not in self.repos:
                raise ValueError(
                    f"SSH project binding {binding_id!r} references unknown repository {binding.repo_name!r}"
                )
        return self

    def resolve_runs_dir(self) -> Path:
        runs = Path(self.runs_dir)
        if not runs.is_absolute():
            runs = self.config_dir / runs
        return runs.resolve()

    def resolve_hermes_service_state_path(self) -> Path:
        if self.hermes_service.state_path:
            path = Path(self.hermes_service.state_path)
            if not path.is_absolute():
                path = self.config_dir / path
            return path.resolve()
        return self.resolve_runs_dir() / "hermes-service-state.json"

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

    def resolve_external_coder_handoff_dir(self) -> Path:
        if self.external_coder.external_coder_handoff_dir:
            path = Path(self.external_coder.external_coder_handoff_dir)
            if not path.is_absolute():
                path = self.config_dir / path
            return path.resolve()
        return self.resolve_runs_dir() / "external_coder_handoffs"

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


def _configured_parent_repo(
    config: AppConfig, repo_name: str, repo_path: Path
) -> tuple[str, Path] | None:
    """Return the configured repository that contains ``repo_path``, if any."""
    for candidate_name, candidate in config.repos.items():
        if candidate_name == repo_name:
            continue
        candidate_path = Path(candidate.path).resolve()
        if candidate_path == repo_path:
            continue
        try:
            repo_path.relative_to(candidate_path)
        except ValueError:
            continue
        return candidate_name, candidate_path
    return None


def _git_worktree_root(repo_path: Path) -> Path | None:
    """Return Git's worktree root, or ``None`` for lightweight fixtures."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip()).resolve()


def _validate_repo_path(config: AppConfig, repo_name: str, repo_path: Path) -> None:
    if not repo_path.exists():
        raise ValueError(f"Repo '{repo_name}' path does not exist: {repo_path}")
    if not repo_path.is_dir():
        raise ValueError(f"Repo '{repo_name}' path is not a directory: {repo_path}")
    if not (repo_path / ".git").exists():
        raise ValueError(f"Repo '{repo_name}' path does not contain .git: {repo_path}")

    parent = _configured_parent_repo(config, repo_name, repo_path)
    if parent is not None and _git_worktree_root(repo_path) != repo_path:
        parent_name, parent_path = parent
        raise ValueError(
            f"Repo '{repo_name}' path is nested under configured repo "
            f"'{parent_name}' ({parent_path}) but is not an independent Git "
            f"repository: {repo_path}"
        )


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
    _validate_repo_path(config, canonical_name, repo_path)
    return canonical_name, repo_path, repo
