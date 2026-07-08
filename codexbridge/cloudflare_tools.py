from __future__ import annotations

import base64
import json
import os
import re
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import AppConfig, CloudflareProfileConfig, resolve_repo_config
from .safety import redact_secret_values


READ_ONLY_CLOUDFLARE_OPERATIONS = (
    "token_verify",
    "list_accounts",
    "list_zones",
    "get_zone",
    "zone_details",
    "list_dns_records",
    "dns_records",
    "dns_record",
    "zone_settings",
    "dnssec",
    "get_ssl_settings",
    "ssl_universal",
    "list_rulesets",
    "rulesets",
    "ruleset",
    "turnstile_widgets",
    "turnstile_widget",
    "list_turnstile_widgets",
    "list_tunnels",
    "tunnels",
    "tunnel",
    "tunnel_connections",
    "tunnel_configuration",
    "tunnel_routes",
    "analytics_http_summary",
)

CLOUDFLARE_ACTIONS = (
    "create_dns_record",
    "update_dns_record",
    "delete_dns_record",
    "dns_create",
    "dns_update",
    "dns_delete",
    "dns_batch",
    "purge_cache",
    "cache_purge",
    "update_ssl_settings",
    "zone_setting_update",
    "dnssec_enable",
    "dnssec_disable",
    "ssl_universal_update",
    "ruleset_create",
    "ruleset_update",
    "ruleset_delete",
    "ruleset_rule_add",
    "ruleset_rule_update",
    "ruleset_rule_delete",
    "turnstile_create",
    "turnstile_update",
    "turnstile_rotate_secret",
    "turnstile_delete",
    "update_turnstile_widget",
    "create_tunnel",
    "tunnel_create",
    "tunnel_config_update",
    "tunnel_delete",
    "tunnel_route_create",
    "tunnel_route_delete",
)

_CLOUDFLARE_INSPECTION_ALIASES = {
    "get_zone": "zone_details",
    "list_dns_records": "dns_records",
    "list_rulesets": "rulesets",
    "list_turnstile_widgets": "turnstile_widgets",
    "list_tunnels": "tunnels",
}
_CLOUDFLARE_ACTION_ALIASES = {
    "create_dns_record": "dns_create",
    "update_dns_record": "dns_update",
    "delete_dns_record": "dns_delete",
    "purge_cache": "cache_purge",
    "update_turnstile_widget": "turnstile_update",
    "create_tunnel": "tunnel_create",
}
_SSL_SETTING_IDS = frozenset(
    {
        "ssl",
        "min_tls_version",
        "tls_1_3",
        "automatic_https_rewrites",
        "always_use_https",
        "opportunistic_encryption",
        "ssl_recommender",
    }
)
_TURNSTILE_MODES = frozenset({"managed", "non-interactive", "invisible"})
_TURNSTILE_CLEARANCE_LEVELS = frozenset(
    {"no_clearance", "jschallenge", "managed", "interactive"}
)
_SECRET_DELIVERY_PENDING = ("get_tunnel_token",)

_DNS_TYPES = frozenset(
    {
        "A",
        "AAAA",
        "CAA",
        "CERT",
        "CNAME",
        "DNSKEY",
        "DS",
        "HTTPS",
        "LOC",
        "MX",
        "NAPTR",
        "NS",
        "OPENPGPKEY",
        "PTR",
        "SMIMEA",
        "SRV",
        "SSHFP",
        "SVCB",
        "TLSA",
        "TXT",
        "URI",
    }
)
_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_PROFILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SETTING_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_FORBIDDEN_PAYLOAD_KEYS = {
    "api_key",
    "api_token",
    "authorization",
    "credentials",
    "credentials_file",
    "password",
    "secret",
    "token",
    "tunnel_secret",
}
_REDACT_RESPONSE_KEYS = {
    "api_key",
    "api_token",
    "authorization",
    "credentials",
    "credentials_file",
    "password",
    "secret",
    "token",
    "tunnel_secret",
}
_MAX_PAYLOAD_BYTES = 100_000
_MAX_LIST_ITEMS = 100
_MAX_ENV_FILE_BYTES = 65_536
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_ANALYTICS_QUERY = """
query CodexBridgeHTTPAnalytics(
  $zoneTag: string!
  $datetimeStart: Time!
  $datetimeEnd: Time!
  $limit: Int!
) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      httpRequestsAdaptiveGroups(
        limit: $limit
        filter: {datetime_geq: $datetimeStart, datetime_leq: $datetimeEnd}
        orderBy: [datetime_ASC]
      ) {
        count
        dimensions { datetime }
        sum { edgeResponseBytes visits }
      }
    }
  }
}
""".strip()


@dataclass(frozen=True)
class CloudflareActionSpec:
    action: str
    method: str
    path: str
    payload: dict[str, Any] | None
    timeout_seconds: int
    high_risk: bool
    secret_response: bool = False
    writes_remote: bool = True
    description: str = "Bounded Cloudflare API action"


@dataclass(frozen=True)
class PreparedSecretDestination:
    path: Path
    temp_path: Path
    variable: str


def _git_path_is_ignored(repo_root: Path, path: Path) -> bool:
    relative = path.relative_to(repo_root).as_posix()
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "check-ignore", "-q", "--", relative],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def _validate_env_destination_file(path: Path, variable: str) -> None:
    if not path.exists():
        return
    if path.is_symlink() or not path.is_file():
        raise ValueError("Turnstile secret destination must be a regular file")
    if path.stat().st_size > _MAX_ENV_FILE_BYTES:
        raise ValueError("Turnstile secret destination exceeds 65536 bytes")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ValueError("Turnstile secret destination is not readable UTF-8") from exc
    assignment = re.compile(
        rf"^\s*(?:export\s+)?{re.escape(variable)}\s*=", re.MULTILINE
    )
    if len(assignment.findall(text)) > 1:
        raise ValueError("Turnstile secret destination contains duplicate variables")


def _prepare_secret_destination(
    repo_root: Path | None, profile: CloudflareProfileConfig
) -> PreparedSecretDestination:
    destination = profile.turnstile.secret_destination
    if destination is None:
        raise ValueError("Turnstile secret destination is not configured")
    if repo_root is None:
        raise ValueError("Turnstile secret actions require an authorized repository root")
    root = Path(repo_root).resolve()
    unresolved = root / destination.path
    if unresolved.exists() and unresolved.is_symlink():
        raise ValueError("Turnstile secret destination must not be a symlink")
    path = unresolved.resolve(strict=False)
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError("Turnstile secret destination escapes the repository") from None
    if not path.parent.is_dir():
        raise ValueError("Turnstile secret destination parent directory does not exist")
    if not _git_path_is_ignored(root, path):
        raise ValueError("Turnstile secret destination must be Git-ignored")
    _validate_env_destination_file(path, destination.variable)

    temp_path = path.with_name(
        f".{path.name}.codexbridge-{secrets.token_hex(8)}.tmp"
    )
    if not _git_path_is_ignored(root, temp_path):
        raise ValueError("Turnstile secret destination temporary file must be Git-ignored")
    try:
        descriptor = os.open(
            temp_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        raise ValueError("Turnstile secret destination is not writable") from None
    return PreparedSecretDestination(
        path=path,
        temp_path=temp_path,
        variable=destination.variable,
    )


def _cleanup_secret_destination(prepared: PreparedSecretDestination) -> None:
    try:
        prepared.temp_path.unlink(missing_ok=True)
    except OSError:
        pass


def _write_env_secret(prepared: PreparedSecretDestination, secret: str) -> None:
    if (
        not isinstance(secret, str)
        or not secret
        or len(secret) > 4096
        or any(char in secret for char in "\x00\r\n")
    ):
        raise ValueError("Cloudflare returned an invalid Turnstile secret")
    try:
        text = (
            prepared.path.read_text(encoding="utf-8-sig")
            if prepared.path.exists()
            else ""
        )
        assignment = re.compile(
            rf"^\s*(?:export\s+)?{re.escape(prepared.variable)}\s*=.*$",
            re.MULTILINE,
        )
        quoted = '"' + secret.replace("\\", "\\\\").replace('"', '\\"') + '"'
        replacement = f"{prepared.variable}={quoted}"
        if assignment.search(text):
            updated = assignment.sub(replacement, text, count=1)
        else:
            separator = "" if not text or text.endswith("\n") else "\n"
            updated = f"{text}{separator}{replacement}\n"
        with prepared.temp_path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(updated)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            prepared.temp_path.chmod(0o600)
        except OSError:
            pass
        os.replace(prepared.temp_path, prepared.path)
        try:
            prepared.path.chmod(0o600)
        except OSError:
            pass
    except (OSError, UnicodeError):
        _cleanup_secret_destination(prepared)
        raise ValueError("Turnstile secret destination update failed") from None


def _require_enabled(config: AppConfig) -> None:
    if not config.cloudflare.enabled:
        raise ValueError("Cloudflare capability is disabled in config")


def _safe_profile_id(profile_id: str) -> str:
    value = str(profile_id or "").strip()
    if not _PROFILE_RE.fullmatch(value):
        raise ValueError(f"Invalid Cloudflare profile_id: {profile_id!r}")
    return value


def resolve_cloudflare_profile(
    config: AppConfig, profile_id: str
) -> CloudflareProfileConfig:
    _require_enabled(config)
    profile_id = _safe_profile_id(profile_id)
    profile = config.cloudflare.profiles.get(profile_id)
    if profile is None:
        raise ValueError(
            f"Unknown Cloudflare profile_id: {profile_id!r}. "
            f"Allowed: {sorted(config.cloudflare.profiles)}"
        )
    return profile


def authorize_cloudflare_profile(
    config: AppConfig, repo_name: str, profile_id: str
) -> tuple[str, CloudflareProfileConfig]:
    canonical_repo_name, repo = resolve_repo_config(config, repo_name)
    profile_id = _safe_profile_id(profile_id)
    if profile_id not in repo.cloudflare_profiles:
        raise ValueError(
            f"Repository {canonical_repo_name!r} is not authorized for "
            f"Cloudflare profile {profile_id!r}"
        )
    return canonical_repo_name, resolve_cloudflare_profile(config, profile_id)


def _dotenv_values(config: AppConfig) -> dict[str, str]:
    root = config.config_dir.resolve()
    path = (root / config.cloudflare.env_file).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise ValueError("Cloudflare env_file escapes the config directory") from None
    if not path.exists():
        return {}
    if not path.is_file():
        raise ValueError("Cloudflare env_file is not a regular file")
    if path.stat().st_size > _MAX_ENV_FILE_BYTES:
        raise ValueError("Cloudflare env_file exceeds 65536 bytes")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise ValueError("Cloudflare env_file could not be read as UTF-8") from exc

    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError("Cloudflare env_file contains an invalid assignment")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not _ENV_NAME_RE.fullmatch(key):
            raise ValueError("Cloudflare env_file contains an invalid variable name")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if "\x00" in value or "\r" in value or "\n" in value:
            raise ValueError("Cloudflare env_file contains an invalid value")
        values[key] = value
    return values


def _env_value(config: AppConfig, env_name: str) -> str:
    if env_name in os.environ:
        return str(os.environ[env_name])
    return _dotenv_values(config).get(env_name, "")


def _env_identifier(
    config: AppConfig, configured: str, env_name: str, field: str
) -> str:
    value = str(configured or "").strip().lower()
    if not value and env_name:
        value = _env_value(config, env_name).strip().lower()
    if not value:
        raise ValueError(f"Cloudflare {field} is not configured")
    if not _ID_RE.fullmatch(value):
        raise ValueError(f"Cloudflare {field} must be a 32-character hex ID")
    return value


def _account_id(config: AppConfig, profile: CloudflareProfileConfig) -> str:
    return _env_identifier(
        config, profile.account_id, profile.account_id_env, "account_id"
    )


def _token(config: AppConfig) -> str:
    value = _env_value(config, config.cloudflare.token_env).strip()
    if not value:
        raise ValueError(
            f"Cloudflare API token is missing from {config.cloudflare.env_file!r} "
            f"and environment variable {config.cloudflare.token_env!r}"
        )
    if any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise ValueError("Cloudflare API token contains invalid characters")
    return value


def _safe_resource_id(value: str, field: str = "resource_id") -> str:
    normalized = str(value or "").strip().lower()
    if not (_ID_RE.fullmatch(normalized) or _UUID_RE.fullmatch(normalized)):
        raise ValueError(f"Invalid Cloudflare {field}: {value!r}")
    return normalized


def _safe_setting_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not _SETTING_RE.fullmatch(normalized):
        raise ValueError(f"Invalid Cloudflare setting ID: {value!r}")
    return normalized


def _safe_dns_type(value: str, *, required: bool = False) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized and not required:
        return ""
    if normalized not in _DNS_TYPES:
        raise ValueError(f"Unsupported DNS record type: {value!r}")
    return normalized


def _safe_dns_name(
    profile: CloudflareProfileConfig, value: str, *, required: bool = True
) -> str:
    name = str(value or "").strip().lower().rstrip(".")
    if not name and not required:
        return ""
    if not name:
        raise ValueError("DNS record name is required")
    if len(name) > 253 or any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or any(not (char.isalnum() or char in "-_*_") for char in label)
        for label in name.split(".")
    ):
        raise ValueError(f"Invalid DNS record name: {value!r}")
    if (
        profile.zone_name
        and name != profile.zone_name
        and not name.endswith(f".{profile.zone_name}")
    ):
        raise ValueError("DNS record name is outside the configured Cloudflare zone")
    if profile.allowed_dns_names and name not in set(profile.allowed_dns_names):
        raise ValueError("DNS record name is not in allowed_dns_names")
    if not profile.zone_name and not profile.allowed_dns_names:
        raise ValueError("DNS operations require zone_name or allowed_dns_names")
    return name


def _validate_payload_value(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if key_text.strip().lower() in _FORBIDDEN_PAYLOAD_KEYS:
                raise ValueError(f"Cloudflare payload key is forbidden: {key_text}")
            if any(ord(char) < 32 or ord(char) == 127 for char in key_text):
                raise ValueError("Cloudflare payload keys contain control characters")
            _validate_payload_value(item, f"{path}.{key_text}")
        return
    if isinstance(value, list):
        if len(value) > _MAX_LIST_ITEMS:
            raise ValueError(f"{path} exceeds {_MAX_LIST_ITEMS} items")
        for index, item in enumerate(value):
            _validate_payload_value(item, f"{path}[{index}]")
        return
    if isinstance(value, str) and any(
        ord(char) < 32 and char not in "\r\n\t" for char in value
    ):
        raise ValueError(f"{path} contains control characters")
    if value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError(f"{path} contains an unsupported value type")


def _safe_payload(
    payload: dict[str, Any] | None,
    *,
    allowed_keys: set[str] | None = None,
) -> dict[str, Any]:
    if payload is None:
        normalized: dict[str, Any] = {}
    elif isinstance(payload, dict):
        normalized = json.loads(json.dumps(payload))
    else:
        raise ValueError("Cloudflare payload must be a JSON object")
    _validate_payload_value(normalized)
    encoded = json.dumps(normalized, separators=(",", ":")).encode("utf-8")
    if len(encoded) > _MAX_PAYLOAD_BYTES:
        raise ValueError("Cloudflare payload exceeds 100000 bytes")
    if allowed_keys is not None:
        unknown = sorted(set(normalized) - allowed_keys)
        if unknown:
            raise ValueError(f"Unsupported Cloudflare payload fields: {unknown}")
    return normalized


def _redact_response(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.strip().lower() in _REDACT_RESPONSE_KEYS or any(
                marker in key_text.strip().lower()
                for marker in ("token", "secret", "password", "credential")
            ):
                redacted[key_text] = "[REDACTED]"
            else:
                redacted[key_text] = _redact_response(item)
        return redacted
    if isinstance(value, list):
        return [_redact_response(item) for item in value]
    if isinstance(value, str):
        return redact_secret_values(value)
    return value


def _error_messages(body: Any) -> str:
    if isinstance(body, dict):
        errors = body.get("errors")
        if isinstance(errors, list):
            messages = []
            for item in errors:
                if isinstance(item, dict):
                    messages.append(
                        str(item.get("message") or item.get("code") or item)
                    )
                else:
                    messages.append(str(item))
            if messages:
                return "; ".join(messages)
        if body.get("message"):
            return str(body["message"])
    return "Cloudflare API request failed"


def _request(
    config: AppConfig,
    method: str,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _require_enabled(config)
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ValueError("Unsupported Cloudflare HTTP method")
    if not path.startswith("/") or ".." in path or "://" in path:
        raise ValueError("Invalid Cloudflare API path")
    token = _token(config)
    url = f"{config.cloudflare.api_base_url}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query, doseq=True)}"
    body = None
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CodexBridge/0.1",
        },
    )
    started = time.monotonic()
    status_code = 0
    try:
        with urllib.request.urlopen(
            request, timeout=config.cloudflare.timeout_seconds
        ) as response:
            status_code = int(getattr(response, "status", 200))
            raw = response.read(config.cloudflare.max_output_bytes + 1)
    except urllib.error.HTTPError as exc:
        status_code = int(exc.code)
        raw = exc.read(config.cloudflare.max_output_bytes + 1)
        try:
            parsed_error = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            parsed_error = {"message": "Cloudflare API returned an HTTP error"}
        raise ValueError(_error_messages(_redact_response(parsed_error))) from None
    except urllib.error.URLError as exc:
        reason = redact_secret_values(str(getattr(exc, "reason", exc)))
        raise ValueError(f"Cloudflare API connection failed: {reason}") from None
    except TimeoutError:
        raise ValueError("Cloudflare API request timed out") from None
    if len(raw) > config.cloudflare.max_output_bytes:
        raise ValueError("Cloudflare API response exceeded max_output_bytes")
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace")) if raw else {}
    except json.JSONDecodeError:
        raise ValueError("Cloudflare API returned invalid JSON") from None
    parsed = _redact_response(parsed)
    if isinstance(parsed, dict) and parsed.get("success") is False:
        raise ValueError(_error_messages(parsed))
    if path == "/graphql" and isinstance(parsed, dict) and parsed.get("errors"):
        raise ValueError(_error_messages(parsed))
    duration = round(time.monotonic() - started, 3)
    result = parsed.get("result") if isinstance(parsed, dict) else parsed
    result_info = parsed.get("result_info", {}) if isinstance(parsed, dict) else {}
    messages = parsed.get("messages", []) if isinstance(parsed, dict) else []
    response_object = {
        "ok": True,
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_seconds": duration,
        "result": result,
        "result_info": result_info,
        "messages": messages,
        "error": "",
    }
    serialized = json.dumps(response_object, ensure_ascii=False, default=str)
    if len(serialized.encode("utf-8")) > config.cloudflare.max_output_bytes:
        raise ValueError("Cloudflare API result exceeded max_output_bytes")
    response_object.update(
        {
            "exit_code": 0,
            "timed_out": False,
            "stdout": serialized,
            "stderr": "",
            "output_truncated": False,
        }
    )
    return response_object


def _safe_turnstile_metadata(
    result: dict[str, Any], *, requested_sitekey: str = ""
) -> tuple[str, str, list[str]]:
    sitekey = _safe_turnstile_sitekey(
        str(result.get("sitekey") or requested_sitekey or "")
    )
    if requested_sitekey and sitekey != requested_sitekey:
        raise ValueError("Cloudflare returned an unexpected Turnstile sitekey")
    widget_name = str(result.get("name") or "").strip()
    if len(widget_name) > 254 or any(
        ord(char) < 32 or ord(char) == 127 for char in widget_name
    ):
        raise ValueError("Cloudflare returned invalid Turnstile widget metadata")
    raw_domains = result.get("domains") or []
    if not isinstance(raw_domains, list) or len(raw_domains) > 100:
        raise ValueError("Cloudflare returned invalid Turnstile domain metadata")
    domains: list[str] = []
    for raw_domain in raw_domains:
        domain = str(raw_domain or "").strip().lower().rstrip(".")
        if (
            not domain
            or len(domain) > 253
            or any(ord(char) < 33 or ord(char) == 127 for char in domain)
        ):
            raise ValueError("Cloudflare returned invalid Turnstile domain metadata")
        domains.append(domain)
    return sitekey, widget_name, domains


def _request_turnstile_secret_action(
    config: AppConfig,
    spec: CloudflareActionSpec,
    prepared: PreparedSecretDestination,
    *,
    requested_sitekey: str = "",
) -> dict[str, Any]:
    _require_enabled(config)
    token = _token(config)
    body = json.dumps(spec.payload or {}, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        f"{config.cloudflare.api_base_url}{spec.path}",
        data=body,
        method=spec.method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "CodexBridge/0.1",
        },
    )
    started = time.monotonic()
    status_code = 0
    try:
        try:
            with urllib.request.urlopen(
                request, timeout=config.cloudflare.timeout_seconds
            ) as response:
                status_code = int(getattr(response, "status", 200))
                raw = response.read(config.cloudflare.max_output_bytes + 1)
        except urllib.error.HTTPError as exc:
            status_code = int(exc.code)
            raw = exc.read(config.cloudflare.max_output_bytes + 1)
            try:
                parsed_error = json.loads(raw.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                parsed_error = {"message": "Cloudflare API returned an HTTP error"}
            raise ValueError(_error_messages(_redact_response(parsed_error))) from None
        except urllib.error.URLError as exc:
            reason = redact_secret_values(str(getattr(exc, "reason", exc)))
            raise ValueError(f"Cloudflare API connection failed: {reason}") from None
        except TimeoutError:
            raise ValueError("Cloudflare API request timed out") from None
        if len(raw) > config.cloudflare.max_output_bytes:
            raise ValueError("Cloudflare API response exceeded max_output_bytes")
        try:
            parsed = json.loads(raw.decode("utf-8", errors="replace")) if raw else {}
        except json.JSONDecodeError:
            raise ValueError("Cloudflare API returned invalid JSON") from None
        if not isinstance(parsed, dict):
            raise ValueError("Cloudflare API returned an invalid Turnstile response")
        if parsed.get("success") is False:
            raise ValueError(_error_messages(_redact_response(parsed)))
        result = parsed.get("result")
        if not isinstance(result, dict):
            raise ValueError("Cloudflare API returned an invalid Turnstile result")
        secret = result.pop("secret", None)
        if not isinstance(secret, str) or not secret:
            raise ValueError("Cloudflare Turnstile response did not include a secret")
        sitekey, widget_name, domains = _safe_turnstile_metadata(
            result, requested_sitekey=requested_sitekey
        )
        _write_env_secret(prepared, secret)
        secret = ""
        result.clear()
        parsed.clear()
        raw = b""

        if spec.action == "turnstile_rotate_secret":
            safe_result = {
                "sitekey": sitekey,
                "widget_name": widget_name,
                "domains": domains,
                "rotated": True,
                "grace_period_hours": 2,
                "secret_destination_updated": True,
            }
        else:
            safe_result = {
                "sitekey": sitekey,
                "widget_name": widget_name,
                "domains": domains,
                "created": True,
                "secret_destination_updated": True,
            }
        duration = round(time.monotonic() - started, 3)
        response_object = {
            "ok": True,
            "method": spec.method,
            "path": spec.path,
            "status_code": status_code,
            "duration_seconds": duration,
            "result": safe_result,
            "result_info": {},
            "messages": [],
            "error": "",
            "exit_code": 0,
            "timed_out": False,
            "stderr": "",
            "output_truncated": False,
        }
        response_object["stdout"] = json.dumps(
            response_object, ensure_ascii=False, default=str
        )
        return response_object
    finally:
        token = ""
        _cleanup_secret_destination(prepared)


def _zone_id(config: AppConfig, profile: CloudflareProfileConfig) -> str:
    configured = str(profile.zone_id or "").strip().lower()
    if not configured and profile.zone_id_env:
        configured = _env_value(config, profile.zone_id_env).strip().lower()
    if configured:
        if not _ID_RE.fullmatch(configured):
            raise ValueError("Cloudflare zone_id must be a 32-character hex ID")
        return configured
    if not profile.zone_name:
        raise ValueError("Cloudflare zone_id or zone_name is required")
    response = _request(
        config,
        "GET",
        "/zones",
        query={"name": profile.zone_name, "status": "active", "per_page": 50},
    )
    matches = [
        item
        for item in (response.get("result") or [])
        if isinstance(item, dict)
        and str(item.get("name", "")).lower().rstrip(".") == profile.zone_name
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Cloudflare zone_name must resolve to exactly one active zone; found {len(matches)}"
        )
    zone_id = str(matches[0].get("id", "")).strip().lower()
    if not _ID_RE.fullmatch(zone_id):
        raise ValueError("Cloudflare zone lookup returned an invalid zone ID")
    return zone_id


def _require_tunnel_scope(profile: CloudflareProfileConfig, tunnel_id: str) -> str:
    tunnel_id = _safe_resource_id(tunnel_id, "tunnel_id")
    if not _UUID_RE.fullmatch(tunnel_id):
        raise ValueError("Cloudflare tunnel_id must be a UUID")
    if profile.allowed_tunnel_ids and tunnel_id not in set(profile.allowed_tunnel_ids):
        raise ValueError("Cloudflare tunnel_id is not in allowed_tunnel_ids")
    return tunnel_id


def _safe_turnstile_sitekey(value: str) -> str:
    sitekey = str(value or "").strip()
    if (
        not sitekey
        or len(sitekey) > 64
        or any(not (char.isalnum() or char in "_-") for char in sitekey)
    ):
        raise ValueError("Invalid Cloudflare Turnstile sitekey")
    return sitekey


def _require_turnstile_scope(profile: CloudflareProfileConfig, sitekey: str) -> str:
    sitekey = _safe_turnstile_sitekey(sitekey)
    allowed = set(profile.allowed_turnstile_sitekeys)
    if not allowed or sitekey not in allowed:
        raise ValueError(
            "Cloudflare Turnstile sitekey is not in allowed_turnstile_sitekeys"
        )
    return sitekey


def _validate_turnstile_update_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = _safe_payload(
        payload,
        allowed_keys={
            "domains",
            "mode",
            "name",
            "bot_fight_mode",
            "clearance_level",
            "ephemeral_id",
            "offlabel",
        },
    )
    if not payload:
        raise ValueError("Turnstile widget update requires at least one field")
    if "domains" in payload:
        domains = payload["domains"]
        if not isinstance(domains, list) or not domains or len(domains) > 15:
            raise ValueError("Turnstile domains must contain between 1 and 15 values")
        if any(
            not isinstance(domain, str)
            or not domain.strip()
            or len(domain.strip()) > 253
            or any(ord(char) < 33 or ord(char) == 127 for char in domain)
            for domain in domains
        ):
            raise ValueError("Turnstile domains must be bounded non-empty hostnames")
        payload["domains"] = [domain.strip().lower().rstrip(".") for domain in domains]
    if "mode" in payload and payload["mode"] not in _TURNSTILE_MODES:
        raise ValueError(f"Unsupported Turnstile mode: {payload['mode']!r}")
    if "clearance_level" in payload and (
        payload["clearance_level"] not in _TURNSTILE_CLEARANCE_LEVELS
    ):
        raise ValueError(
            f"Unsupported Turnstile clearance_level: {payload['clearance_level']!r}"
        )
    if "name" in payload and (
        not isinstance(payload["name"], str)
        or not payload["name"].strip()
        or len(payload["name"].strip()) > 254
    ):
        raise ValueError(
            "Turnstile name must be a non-empty string of at most 254 characters"
        )
    if "name" in payload:
        payload["name"] = payload["name"].strip()
    for field in ("bot_fight_mode", "ephemeral_id", "offlabel"):
        if field in payload and not isinstance(payload[field], bool):
            raise ValueError(f"Turnstile {field} must be boolean")
    return payload


def _validate_turnstile_create_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload = _validate_turnstile_update_payload(payload)
    missing = [field for field in ("name", "domains", "mode") if field not in payload]
    if missing:
        raise ValueError(f"Turnstile widget create requires fields: {missing}")
    return payload


def run_cloudflare_inspection(
    config: AppConfig,
    profile_id: str,
    operation: str,
    *,
    resource_id: str = "",
    name: str = "",
    record_type: str = "",
    since_minutes: int = 60,
    page: int = 1,
    per_page: int = 100,
) -> dict[str, Any]:
    profile = resolve_cloudflare_profile(config, profile_id)
    requested_operation = str(operation or "").strip()
    if requested_operation not in READ_ONLY_CLOUDFLARE_OPERATIONS:
        raise ValueError(
            f"Unsupported Cloudflare inspection operation: {requested_operation!r}. "
            f"Allowed: {list(READ_ONLY_CLOUDFLARE_OPERATIONS)}"
        )
    operation = _CLOUDFLARE_INSPECTION_ALIASES.get(
        requested_operation, requested_operation
    )
    if page < 1 or page > 10000:
        raise ValueError("page must be between 1 and 10000")
    if per_page < 1 or per_page > 500:
        raise ValueError("per_page must be between 1 and 500")
    if since_minutes < 1 or since_minutes > 43200:
        raise ValueError("since_minutes must be between 1 and 43200")

    if operation == "token_verify":
        response = _request(config, "GET", "/user/tokens/verify")
    elif operation == "list_accounts":
        account_id = _account_id(config, profile)
        response = _request(config, "GET", f"/accounts/{account_id}")
    elif operation == "list_zones":
        account_id = _account_id(config, profile)
        query: dict[str, Any] = {
            "account.id": account_id,
            "page": page,
            "per_page": per_page,
        }
        if name:
            zone_name = str(name).strip().lower().rstrip(".")
            if (
                not zone_name
                or len(zone_name) > 253
                or any(
                    not label
                    or len(label) > 63
                    or label.startswith("-")
                    or label.endswith("-")
                    or any(not (char.isalnum() or char == "-") for char in label)
                    for label in zone_name.split(".")
                )
            ):
                raise ValueError("Invalid Cloudflare zone name filter")
            query["name"] = zone_name
        response = _request(config, "GET", "/zones", query=query)
    elif operation in {
        "zone_details",
        "dns_records",
        "dns_record",
        "zone_settings",
        "dnssec",
        "get_ssl_settings",
        "ssl_universal",
        "rulesets",
        "ruleset",
        "analytics_http_summary",
    }:
        zone_id = _zone_id(config, profile)
        if operation == "zone_details":
            response = _request(config, "GET", f"/zones/{zone_id}")
        elif operation == "dns_records":
            query = {"page": page, "per_page": per_page}
            safe_name = _safe_dns_name(profile, name, required=False)
            safe_type = _safe_dns_type(record_type)
            if safe_name:
                query["name"] = safe_name
            if safe_type:
                query["type"] = safe_type
            response = _request(
                config, "GET", f"/zones/{zone_id}/dns_records", query=query
            )
        elif operation == "dns_record":
            record_id = _safe_resource_id(resource_id, "dns_record_id")
            response = _request(
                config, "GET", f"/zones/{zone_id}/dns_records/{record_id}"
            )
        elif operation == "zone_settings":
            response = _request(config, "GET", f"/zones/{zone_id}/settings")
        elif operation == "dnssec":
            response = _request(config, "GET", f"/zones/{zone_id}/dnssec")
        elif operation == "get_ssl_settings":
            setting_id = str(resource_id or "ssl").strip()
            if setting_id not in _SSL_SETTING_IDS:
                raise ValueError(
                    f"Unsupported Cloudflare SSL setting: {setting_id!r}. "
                    f"Allowed: {sorted(_SSL_SETTING_IDS)}"
                )
            response = _request(
                config, "GET", f"/zones/{zone_id}/settings/{setting_id}"
            )
        elif operation == "ssl_universal":
            response = _request(
                config, "GET", f"/zones/{zone_id}/ssl/universal/settings"
            )
        elif operation == "rulesets":
            response = _request(config, "GET", f"/zones/{zone_id}/rulesets")
        elif operation == "ruleset":
            ruleset_id = _safe_resource_id(resource_id, "ruleset_id")
            response = _request(
                config, "GET", f"/zones/{zone_id}/rulesets/{ruleset_id}"
            )
        else:
            now = datetime.now(timezone.utc).replace(microsecond=0)
            start = now - timedelta(minutes=since_minutes)
            variables = {
                "zoneTag": zone_id,
                "datetimeStart": start.isoformat().replace("+00:00", "Z"),
                "datetimeEnd": now.isoformat().replace("+00:00", "Z"),
                "limit": min(per_page, 500),
            }
            response = _request(
                config,
                "POST",
                "/graphql",
                payload={"query": _ANALYTICS_QUERY, "variables": variables},
            )
    else:
        account_id = _account_id(config, profile)
        if operation == "turnstile_widgets":
            response = _request(
                config,
                "GET",
                f"/accounts/{account_id}/challenges/widgets",
                query={"page": page, "per_page": per_page},
            )
        elif operation == "turnstile_widget":
            sitekey = _require_turnstile_scope(profile, resource_id)
            response = _request(
                config,
                "GET",
                f"/accounts/{account_id}/challenges/widgets/{sitekey}",
            )
        elif operation == "tunnels":
            response = _request(
                config,
                "GET",
                f"/accounts/{account_id}/cfd_tunnel",
                query={"page": page, "per_page": per_page, "is_deleted": "false"},
            )
        elif operation == "tunnel_routes":
            response = _request(
                config,
                "GET",
                f"/accounts/{account_id}/teamnet/routes",
                query={"page": page, "per_page": per_page},
            )
        else:
            tunnel_id = _require_tunnel_scope(profile, resource_id)
            suffix = {
                "tunnel": "",
                "tunnel_connections": "/connections",
                "tunnel_configuration": "/configurations",
            }[operation]
            response = _request(
                config,
                "GET",
                f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}{suffix}",
            )
    response.update(
        {
            "profile_id": _safe_profile_id(profile_id),
            "operation": requested_operation,
            "canonical_operation": operation,
            "writes_remote": False,
            "high_risk": False,
        }
    )
    return response


def _require_gate(config: AppConfig, gate: str, action: str) -> None:
    if not bool(getattr(config.cloudflare, gate)):
        raise ValueError(
            f"Cloudflare action {action!r} is disabled by config gate {gate}"
        )


def _require_confirmation(config: AppConfig, action: str, confirmation: str) -> None:
    if confirmation != config.cloudflare.confirmation_token:
        raise ValueError(
            f"Cloudflare action {action!r} requires confirmation token "
            f"{config.cloudflare.confirmation_token!r}"
        )


def _validate_dns_record_payload(
    profile: CloudflareProfileConfig,
    payload: dict[str, Any],
    *,
    partial: bool,
) -> dict[str, Any]:
    allowed = {
        "type",
        "name",
        "content",
        "ttl",
        "proxied",
        "priority",
        "comment",
        "tags",
        "data",
        "settings",
    }
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise ValueError(f"Unsupported DNS payload fields: {unknown}")
    if not partial or "type" in payload:
        payload["type"] = _safe_dns_type(str(payload.get("type", "")), required=True)
    if not partial or "name" in payload:
        payload["name"] = _safe_dns_name(profile, str(payload.get("name", "")))
    if not partial and "content" not in payload and "data" not in payload:
        raise ValueError("DNS payload requires content or data")
    if "ttl" in payload:
        ttl = payload["ttl"]
        if (
            not isinstance(ttl, int)
            or isinstance(ttl, bool)
            or (ttl != 1 and not 60 <= ttl <= 86400)
        ):
            raise ValueError("DNS ttl must be 1 or between 60 and 86400")
    if "proxied" in payload and not isinstance(payload["proxied"], bool):
        raise ValueError("DNS proxied must be boolean")
    if "priority" in payload and (
        not isinstance(payload["priority"], int)
        or isinstance(payload["priority"], bool)
        or not 0 <= payload["priority"] <= 65535
    ):
        raise ValueError("DNS priority must be between 0 and 65535")
    return payload


def _validate_ruleset_phase(
    profile: CloudflareProfileConfig, payload: dict[str, Any], *, required: bool
) -> None:
    phase = str(payload.get("phase", "")).strip()
    if required and not phase:
        raise ValueError("Ruleset payload requires phase")
    if phase and (
        not profile.allowed_ruleset_phases
        or phase not in set(profile.allowed_ruleset_phases)
    ):
        raise ValueError("Ruleset phase is not in allowed_ruleset_phases")


def build_cloudflare_action(
    config: AppConfig,
    profile_id: str,
    action: str,
    *,
    resource_id: str = "",
    payload: dict[str, Any] | None = None,
    confirmation: str = "",
) -> CloudflareActionSpec:
    profile = resolve_cloudflare_profile(config, profile_id)
    requested_action = str(action or "").strip()
    if requested_action not in CLOUDFLARE_ACTIONS:
        raise ValueError(
            f"Unsupported Cloudflare action: {requested_action!r}. "
            f"Allowed: {list(CLOUDFLARE_ACTIONS)}"
        )
    action = _CLOUDFLARE_ACTION_ALIASES.get(requested_action, requested_action)
    data = _safe_payload(payload)
    timeout = config.cloudflare.timeout_seconds
    high_risk = False
    secret_response = False

    if action.startswith("dns_"):
        zone_id = _zone_id(config, profile)
        if action in {"dns_create", "dns_update"}:
            _require_gate(config, "allow_dns_write", action)
            data = _validate_dns_record_payload(
                profile, data, partial=action == "dns_update"
            )
            if action == "dns_create":
                method = "POST"
                path = f"/zones/{zone_id}/dns_records"
            else:
                method = "PATCH"
                record_id = _safe_resource_id(resource_id, "dns_record_id")
                path = f"/zones/{zone_id}/dns_records/{record_id}"
        elif action == "dns_delete":
            _require_gate(config, "allow_delete", action)
            _require_confirmation(config, action, confirmation)
            high_risk = True
            method = "DELETE"
            data = {}
            record_id = _safe_resource_id(resource_id, "dns_record_id")
            path = f"/zones/{zone_id}/dns_records/{record_id}"
        else:
            _require_gate(config, "allow_dns_write", action)
            _require_gate(config, "allow_delete", action)
            _require_confirmation(config, action, confirmation)
            high_risk = True
            allowed_batch = {"deletes", "patches", "posts", "puts"}
            unknown = sorted(set(data) - allowed_batch)
            if unknown or not data:
                raise ValueError(f"Unsupported or empty DNS batch fields: {unknown}")
            for record in data.get("posts", []):
                if not isinstance(record, dict):
                    raise ValueError("DNS batch posts entries must be objects")
                _validate_dns_record_payload(profile, record, partial=False)
            for key, partial in (("puts", False), ("patches", True)):
                for record in data.get(key, []):
                    if not isinstance(record, dict):
                        raise ValueError(f"DNS batch {key} entries must be objects")
                    record_id = record.get("id")
                    if not record_id:
                        raise ValueError(f"DNS batch {key} entries require id")
                    _safe_resource_id(str(record_id), "dns_record_id")
                    record_payload = {k: v for k, v in record.items() if k != "id"}
                    _validate_dns_record_payload(
                        profile, record_payload, partial=partial
                    )
            for record in data.get("deletes", []):
                if not isinstance(record, dict) or "id" not in record:
                    raise ValueError("DNS batch delete entries require id")
                _safe_resource_id(str(record["id"]), "dns_record_id")
            method = "POST"
            path = f"/zones/{zone_id}/dns_records/batch"
    elif action == "cache_purge":
        _require_gate(config, "allow_cache_purge", action)
        zone_id = _zone_id(config, profile)
        allowed = {"purge_everything", "files", "prefixes", "tags", "hosts"}
        unknown = sorted(set(data) - allowed)
        populated = [key for key in allowed if key in data]
        if unknown or len(populated) != 1:
            raise ValueError(
                "Cache purge requires exactly one supported purge selector"
            )
        selector = populated[0]
        if selector == "purge_everything":
            if data[selector] is not True:
                raise ValueError("purge_everything must be true")
            _require_confirmation(config, action, confirmation)
            high_risk = True
        else:
            values = data[selector]
            if not isinstance(values, list) or not values or len(values) > 30:
                raise ValueError(
                    "Cache purge lists must contain between 1 and 30 values"
                )
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError("Cache purge values must be non-empty strings")
        method = "POST"
        path = f"/zones/{zone_id}/purge_cache"
    elif action in {
        "update_ssl_settings",
        "zone_setting_update",
        "dnssec_enable",
        "dnssec_disable",
        "ssl_universal_update",
    }:
        _require_gate(config, "allow_zone_settings", action)
        _require_confirmation(config, action, confirmation)
        high_risk = True
        zone_id = _zone_id(config, profile)
        if action == "zone_setting_update":
            data = _safe_payload(data, allowed_keys={"value"})
            if "value" not in data:
                raise ValueError("Zone setting update requires value")
            setting_id = _safe_setting_id(resource_id)
            method = "PATCH"
            path = f"/zones/{zone_id}/settings/{setting_id}"
        elif action == "update_ssl_settings":
            setting_id = _safe_setting_id(resource_id)
            if setting_id not in _SSL_SETTING_IDS:
                raise ValueError(
                    f"Unsupported Cloudflare SSL setting: {setting_id!r}. "
                    f"Allowed: {sorted(_SSL_SETTING_IDS)}"
                )
            if setting_id == "ssl_recommender":
                data = _safe_payload(data, allowed_keys={"enabled"})
                if not isinstance(data.get("enabled"), bool):
                    raise ValueError("SSL recommender update requires boolean enabled")
            else:
                data = _safe_payload(data, allowed_keys={"value"})
                if "value" not in data:
                    raise ValueError("SSL setting update requires value")
            method = "PATCH"
            path = f"/zones/{zone_id}/settings/{setting_id}"
        elif action == "ssl_universal_update":
            data = _safe_payload(data, allowed_keys={"enabled"})
            if not isinstance(data.get("enabled"), bool):
                raise ValueError("Universal SSL update requires boolean enabled")
            method = "PATCH"
            path = f"/zones/{zone_id}/ssl/universal/settings"
        elif action == "dnssec_enable":
            method = "POST"
            data = {}
            path = f"/zones/{zone_id}/dnssec"
        else:
            method = "DELETE"
            data = {}
            path = f"/zones/{zone_id}/dnssec"
    elif action.startswith("ruleset_"):
        _require_gate(config, "allow_rulesets", action)
        _require_confirmation(config, action, confirmation)
        high_risk = True
        zone_id = _zone_id(config, profile)
        if action == "ruleset_create":
            data = _safe_payload(
                data, allowed_keys={"name", "description", "kind", "phase", "rules"}
            )
            _validate_ruleset_phase(profile, data, required=True)
            method = "POST"
            path = f"/zones/{zone_id}/rulesets"
        else:
            ruleset_id = _safe_resource_id(resource_id, "ruleset_id")
            if action == "ruleset_update":
                data = _safe_payload(
                    data, allowed_keys={"description", "name", "kind", "phase", "rules"}
                )
                _validate_ruleset_phase(profile, data, required=False)
                method = "PUT"
                path = f"/zones/{zone_id}/rulesets/{ruleset_id}"
            elif action == "ruleset_delete":
                _require_gate(config, "allow_delete", action)
                method = "DELETE"
                data = {}
                path = f"/zones/{zone_id}/rulesets/{ruleset_id}"
            elif action == "ruleset_rule_add":
                data = _safe_payload(
                    data,
                    allowed_keys={
                        "action",
                        "action_parameters",
                        "description",
                        "enabled",
                        "expression",
                        "logging",
                        "ratelimit",
                        "ref",
                    },
                )
                method = "POST"
                path = f"/zones/{zone_id}/rulesets/{ruleset_id}/rules"
            else:
                rule_id = _safe_resource_id(str(data.pop("rule_id", "")), "rule_id")
                if action == "ruleset_rule_update":
                    data = _safe_payload(
                        data,
                        allowed_keys={
                            "action",
                            "action_parameters",
                            "description",
                            "enabled",
                            "expression",
                            "logging",
                            "ratelimit",
                            "ref",
                        },
                    )
                    method = "PATCH"
                else:
                    _require_gate(config, "allow_delete", action)
                    method = "DELETE"
                    data = {}
                path = f"/zones/{zone_id}/rulesets/{ruleset_id}/rules/{rule_id}"
    elif action.startswith("turnstile_"):
        account_id = _account_id(config, profile)
        if action == "turnstile_create":
            _require_gate(config, "allow_turnstile_write", action)
            if profile.turnstile.secret_destination is None:
                raise ValueError("Turnstile secret destination is not configured")
            data = _validate_turnstile_create_payload(data)
            method = "POST"
            path = f"/accounts/{account_id}/challenges/widgets"
            secret_response = True
        elif action == "turnstile_update":
            _require_gate(config, "allow_turnstile_write", action)
            sitekey = _require_turnstile_scope(profile, resource_id)
            data = _validate_turnstile_update_payload(data)
            method = "PUT"
            path = f"/accounts/{account_id}/challenges/widgets/{sitekey}"
        elif action == "turnstile_rotate_secret":
            _require_gate(config, "allow_turnstile_write", action)
            _require_gate(config, "allow_turnstile_secret_rotation", action)
            _require_confirmation(config, action, confirmation)
            if profile.turnstile.secret_destination is None:
                raise ValueError("Turnstile secret destination is not configured")
            if data:
                raise ValueError("Turnstile secret rotation payload is fixed by policy")
            sitekey = _require_turnstile_scope(profile, resource_id)
            data = {"invalidate_immediately": False}
            method = "POST"
            path = (
                f"/accounts/{account_id}/challenges/widgets/{sitekey}/rotate_secret"
            )
            high_risk = True
            secret_response = True
        else:
            _require_gate(config, "allow_turnstile_delete", action)
            _require_confirmation(config, action, confirmation)
            if data:
                raise ValueError("Turnstile delete does not accept a payload")
            sitekey = _require_turnstile_scope(profile, resource_id)
            data = {}
            method = "DELETE"
            path = f"/accounts/{account_id}/challenges/widgets/{sitekey}"
            high_risk = True
    else:
        _require_gate(config, "allow_tunnels", action)
        _require_confirmation(config, action, confirmation)
        high_risk = True
        account_id = _account_id(config, profile)
        if action == "tunnel_create":
            data = _safe_payload(data, allowed_keys={"name", "config_src"})
            name = str(data.get("name", "")).strip()
            if not name or len(name) > 128:
                raise ValueError(
                    "Tunnel create requires a name of at most 128 characters"
                )
            data["config_src"] = str(data.get("config_src") or "cloudflare")
            if data["config_src"] != "cloudflare":
                raise ValueError("Tunnel config_src must be cloudflare")
            data["tunnel_secret"] = base64.b64encode(secrets.token_bytes(32)).decode(
                "ascii"
            )
            method = "POST"
            path = f"/accounts/{account_id}/cfd_tunnel"
        elif action == "tunnel_route_create":
            data = _safe_payload(
                data,
                allowed_keys={"network", "tunnel_id", "comment", "virtual_network_id"},
            )
            network = str(data.get("network", "")).strip()
            if not network or "/" not in network or len(network) > 64:
                raise ValueError("Tunnel route requires a CIDR network")
            data["tunnel_id"] = _require_tunnel_scope(
                profile, str(data.get("tunnel_id", ""))
            )
            method = "POST"
            path = f"/accounts/{account_id}/teamnet/routes"
        elif action == "tunnel_route_delete":
            _require_gate(config, "allow_delete", action)
            route_id = _safe_resource_id(resource_id, "route_id")
            method = "DELETE"
            data = {}
            path = f"/accounts/{account_id}/teamnet/routes/{route_id}"
        else:
            tunnel_id = _require_tunnel_scope(profile, resource_id)
            if action == "tunnel_config_update":
                data = _safe_payload(data, allowed_keys={"config"})
                if not isinstance(data.get("config"), dict):
                    raise ValueError(
                        "Tunnel configuration update requires config object"
                    )
                method = "PUT"
                path = f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations"
            else:
                _require_gate(config, "allow_delete", action)
                method = "DELETE"
                data = {}
                path = f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}"

    return CloudflareActionSpec(
        action=requested_action,
        method=method,
        path=path,
        payload=data or None,
        timeout_seconds=timeout,
        high_risk=high_risk,
        secret_response=secret_response,
    )


def run_cloudflare_action(
    config: AppConfig,
    profile_id: str,
    action: str,
    *,
    resource_id: str = "",
    payload: dict[str, Any] | None = None,
    confirmation: str = "",
    repo_root: Path | None = None,
) -> dict[str, Any]:
    profile = resolve_cloudflare_profile(config, profile_id)
    spec = build_cloudflare_action(
        config,
        profile_id,
        action,
        resource_id=resource_id,
        payload=payload,
        confirmation=confirmation,
    )
    if spec.secret_response:
        prepared = _prepare_secret_destination(repo_root, profile)
        requested_sitekey = (
            _safe_turnstile_sitekey(resource_id)
            if spec.action == "turnstile_rotate_secret"
            else ""
        )
        result = _request_turnstile_secret_action(
            config,
            spec,
            prepared,
            requested_sitekey=requested_sitekey,
        )
    else:
        result = _request(
            config,
            spec.method,
            spec.path,
            payload=spec.payload,
        )
    result.update(
        {
            "profile_id": _safe_profile_id(profile_id),
            "action": action,
            "writes_remote": True,
            "high_risk": spec.high_risk,
            "remote_state_verified": False,
        }
    )
    return result


def cloudflare_health(config: AppConfig, profile_id: str) -> dict[str, Any]:
    profile = resolve_cloudflare_profile(config, profile_id)
    token_status = _request(config, "GET", "/user/tokens/verify")
    zone_id = ""
    account_id = ""
    if profile.zone_id or profile.zone_id_env or profile.zone_name:
        zone_id = _zone_id(config, profile)
    if profile.account_id or profile.account_id_env:
        account_id = _account_id(config, profile)
    return {
        "ok": True,
        "profile_id": _safe_profile_id(profile_id),
        "token_status": token_status.get("result"),
        "zone_id_configured": bool(zone_id),
        "account_id_configured": bool(account_id),
        "zone_name": profile.zone_name,
        "error": "",
    }


def list_cloudflare_capabilities(
    config: AppConfig, repo_name: str = ""
) -> dict[str, Any]:
    canonical_repo_name = ""
    authorized_profile_ids: set[str] | None = None
    if repo_name:
        canonical_repo_name, repo = resolve_repo_config(config, repo_name)
        authorized_profile_ids = set(repo.cloudflare_profiles)
    profiles = []
    for profile_id, profile in sorted(config.cloudflare.profiles.items()):
        if (
            authorized_profile_ids is not None
            and profile_id not in authorized_profile_ids
        ):
            continue
        profiles.append(
            {
                "profile_id": profile_id,
                "zone_name": profile.zone_name,
                "zone_id_configured": bool(profile.zone_id or profile.zone_id_env),
                "account_id_configured": bool(
                    profile.account_id or profile.account_id_env
                ),
                "allowed_dns_names": list(profile.allowed_dns_names),
                "allowed_ruleset_phases": list(profile.allowed_ruleset_phases),
                "allowed_tunnel_ids": list(profile.allowed_tunnel_ids),
                "allowed_turnstile_sitekeys": list(profile.allowed_turnstile_sitekeys),
                "turnstile_secret_destination": {
                    "configured": profile.turnstile.secret_destination is not None,
                    "type": (
                        profile.turnstile.secret_destination.type
                        if profile.turnstile.secret_destination is not None
                        else ""
                    ),
                    "path": (
                        profile.turnstile.secret_destination.path
                        if profile.turnstile.secret_destination is not None
                        else ""
                    ),
                    "variable": (
                        profile.turnstile.secret_destination.variable
                        if profile.turnstile.secret_destination is not None
                        else ""
                    ),
                },
            }
        )
    return {
        "ok": True,
        "enabled": config.cloudflare.enabled,
        "repo_name": canonical_repo_name,
        "api_base_url": config.cloudflare.api_base_url,
        "token_env": config.cloudflare.token_env,
        "read_only_operations": list(READ_ONLY_CLOUDFLARE_OPERATIONS),
        "actions": list(CLOUDFLARE_ACTIONS),
        "gates": {
            "allow_dns_write": config.cloudflare.allow_dns_write,
            "allow_cache_purge": config.cloudflare.allow_cache_purge,
            "allow_zone_settings": config.cloudflare.allow_zone_settings,
            "allow_rulesets": config.cloudflare.allow_rulesets,
            "allow_tunnels": config.cloudflare.allow_tunnels,
            "allow_turnstile": config.cloudflare.allow_turnstile,
            "allow_turnstile_write": config.cloudflare.allow_turnstile_write,
            "allow_turnstile_secret_rotation": (
                config.cloudflare.allow_turnstile_secret_rotation
            ),
            "allow_turnstile_delete": config.cloudflare.allow_turnstile_delete,
            "allow_delete": config.cloudflare.allow_delete,
        },
        "secret_delivery_pending": list(_SECRET_DELIVERY_PENDING),
        "confirmation_token": config.cloudflare.confirmation_token,
        "profiles": profiles,
        "arbitrary_http_supported": False,
        "raw_graphql_supported": False,
        "error": "",
    }
