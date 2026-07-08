from __future__ import annotations

import base64
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import AppConfig, CloudflareProfileConfig
from .safety import redact_secret_values


READ_ONLY_CLOUDFLARE_OPERATIONS = (
    "token_verify",
    "zone_details",
    "dns_records",
    "dns_record",
    "zone_settings",
    "dnssec",
    "ssl_universal",
    "rulesets",
    "ruleset",
    "tunnels",
    "tunnel",
    "tunnel_connections",
    "tunnel_configuration",
    "tunnel_routes",
    "analytics_http_summary",
)

CLOUDFLARE_ACTIONS = (
    "dns_create",
    "dns_update",
    "dns_delete",
    "dns_batch",
    "cache_purge",
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
    "tunnel_create",
    "tunnel_config_update",
    "tunnel_delete",
    "tunnel_route_create",
    "tunnel_route_delete",
)

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
    writes_remote: bool = True
    description: str = "Bounded Cloudflare API action"


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
    operation = str(operation or "").strip()
    if operation not in READ_ONLY_CLOUDFLARE_OPERATIONS:
        raise ValueError(
            f"Unsupported Cloudflare inspection operation: {operation!r}. "
            f"Allowed: {list(READ_ONLY_CLOUDFLARE_OPERATIONS)}"
        )
    if page < 1 or page > 10000:
        raise ValueError("page must be between 1 and 10000")
    if per_page < 1 or per_page > 500:
        raise ValueError("per_page must be between 1 and 500")
    if since_minutes < 1 or since_minutes > 43200:
        raise ValueError("since_minutes must be between 1 and 43200")

    if operation == "token_verify":
        response = _request(config, "GET", "/user/tokens/verify")
    elif operation in {
        "zone_details",
        "dns_records",
        "dns_record",
        "zone_settings",
        "dnssec",
        "ssl_universal",
        "rulesets",
        "ruleset",
        "analytics_http_summary",
    }:
        zone_id = _zone_id(config, profile)
        if operation == "zone_details":
            response = _request(config, "GET", f"/zones/{zone_id}")
        elif operation == "dns_records":
            query: dict[str, Any] = {"page": page, "per_page": per_page}
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
        if operation == "tunnels":
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
            "operation": operation,
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
    action = str(action or "").strip()
    if action not in CLOUDFLARE_ACTIONS:
        raise ValueError(
            f"Unsupported Cloudflare action: {action!r}. Allowed: {list(CLOUDFLARE_ACTIONS)}"
        )
    data = _safe_payload(payload)
    timeout = config.cloudflare.timeout_seconds
    high_risk = False

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
            method = "PATCH"
            path = f"/zones/{zone_id}/settings/{_safe_setting_id(resource_id)}"
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
        action=action,
        method=method,
        path=path,
        payload=data or None,
        timeout_seconds=timeout,
        high_risk=high_risk,
    )


def run_cloudflare_action(
    config: AppConfig,
    profile_id: str,
    action: str,
    *,
    resource_id: str = "",
    payload: dict[str, Any] | None = None,
    confirmation: str = "",
) -> dict[str, Any]:
    spec = build_cloudflare_action(
        config,
        profile_id,
        action,
        resource_id=resource_id,
        payload=payload,
        confirmation=confirmation,
    )
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


def list_cloudflare_capabilities(config: AppConfig) -> dict[str, Any]:
    profiles = []
    for profile_id, profile in sorted(config.cloudflare.profiles.items()):
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
            }
        )
    return {
        "ok": True,
        "enabled": config.cloudflare.enabled,
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
            "allow_delete": config.cloudflare.allow_delete,
        },
        "confirmation_token": config.cloudflare.confirmation_token,
        "profiles": profiles,
        "arbitrary_http_supported": False,
        "raw_graphql_supported": False,
        "error": "",
    }
