from __future__ import annotations

import io
import json
from pathlib import Path
import urllib.error

import pytest

from codexbridge import cloudflare_tools
from codexbridge.config import (
    AppConfig,
    CloudflareConfig,
    CloudflareProfileConfig,
    RepoConfig,
)


ZONE_ID = "a" * 32
ACCOUNT_ID = "b" * 32
RECORD_ID = "c" * 32
RULESET_ID = "d" * 32
TUNNEL_ID = "12345678-1234-1234-1234-123456789abc"


class FakeResponse:
    def __init__(self, payload: object, status: int = 200):
        self.status = status
        self.body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, limit: int = -1) -> bytes:
        if limit < 0:
            return self.body
        return self.body[:limit]


def make_config(tmp_path: Path, **overrides) -> AppConfig:
    profile = CloudflareProfileConfig(
        account_id=ACCOUNT_ID,
        zone_id=ZONE_ID,
        zone_name="example.com",
        allowed_dns_names=["example.com", "api.example.com"],
        allowed_ruleset_phases=["http_request_firewall_custom"],
        allowed_tunnel_ids=[TUNNEL_ID],
    )
    values = {
        "enabled": True,
        "allow_dns_write": True,
        "allow_cache_purge": True,
        "allow_zone_settings": True,
        "allow_rulesets": True,
        "allow_tunnels": True,
        "allow_delete": True,
        "profiles": {"production": profile},
    }
    values.update(overrides)
    return AppConfig(
        repos={"sample": RepoConfig(path=str(tmp_path))},
        cloudflare=CloudflareConfig(**values),
        config_dir=tmp_path,
    )


def install_token(monkeypatch, config: AppConfig) -> None:
    monkeypatch.setenv(config.cloudflare.token_env, "test-cloudflare-token")


def test_token_must_come_from_environment_or_env_file(
    monkeypatch, tmp_path: Path
) -> None:
    config = make_config(tmp_path)
    monkeypatch.delenv(config.cloudflare.token_env, raising=False)

    with pytest.raises(ValueError, match="missing from '.env'"):
        cloudflare_tools.run_cloudflare_inspection(config, "production", "token_verify")


def test_env_file_supplies_token_and_ids_with_os_precedence(
    monkeypatch, tmp_path: Path
) -> None:
    config = make_config(tmp_path)
    profile = config.cloudflare.profiles["production"]
    profile.account_id = ""
    profile.zone_id = ""
    profile.account_id_env = "CLOUDFLARE_ACCOUNT_ID"
    profile.zone_id_env = "CLOUDFLARE_ZONE_ID"
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "# Cloudflare credentials",
                'CLOUDFLARE_API_TOKEN="file-token"',
                f"CLOUDFLARE_ACCOUNT_ID={ACCOUNT_ID}",
                f"CLOUDFLARE_ZONE_ID={ZONE_ID}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ZONE_ID", raising=False)

    assert cloudflare_tools._token(config) == "file-token"
    assert cloudflare_tools._account_id(config, profile) == ACCOUNT_ID
    assert cloudflare_tools._zone_id(config, profile) == ZONE_ID

    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "os-token")
    assert cloudflare_tools._token(config) == "os-token"


def test_token_verify_uses_fixed_official_endpoint(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path)
    install_token(monkeypatch, config)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return FakeResponse({"success": True, "result": {"status": "active"}})

    monkeypatch.setattr(cloudflare_tools.urllib.request, "urlopen", fake_urlopen)
    result = cloudflare_tools.run_cloudflare_inspection(
        config, "production", "token_verify"
    )

    assert result["ok"] is True
    assert captured["url"] == "https://api.cloudflare.com/client/v4/user/tokens/verify"
    assert captured["method"] == "GET"
    assert captured["headers"]["Authorization"] == "Bearer test-cloudflare-token"
    assert captured["timeout"] == config.cloudflare.timeout_seconds


def test_zone_name_resolution_and_dns_filters(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.cloudflare.profiles["production"].zone_id = ""
    install_token(monkeypatch, config)
    requests = []
    responses = iter(
        [
            FakeResponse(
                {
                    "success": True,
                    "result": [{"id": ZONE_ID, "name": "example.com"}],
                }
            ),
            FakeResponse(
                {
                    "success": True,
                    "result": [{"id": RECORD_ID, "name": "api.example.com"}],
                    "result_info": {"count": 1},
                }
            ),
        ]
    )

    def fake_urlopen(request, timeout):
        requests.append(request.full_url)
        return next(responses)

    monkeypatch.setattr(cloudflare_tools.urllib.request, "urlopen", fake_urlopen)
    result = cloudflare_tools.run_cloudflare_inspection(
        config,
        "production",
        "dns_records",
        name="api.example.com",
        record_type="A",
        page=2,
        per_page=25,
    )

    assert "zones?" in requests[0]
    assert "name=example.com" in requests[0]
    assert requests[1].startswith(
        f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records?"
    )
    assert "name=api.example.com" in requests[1]
    assert "type=A" in requests[1]
    assert result["result_info"]["count"] == 1


def test_analytics_uses_fixed_graphql_query(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path)
    install_token(monkeypatch, config)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"data": {"viewer": {"zones": []}}})

    monkeypatch.setattr(cloudflare_tools.urllib.request, "urlopen", fake_urlopen)
    result = cloudflare_tools.run_cloudflare_inspection(
        config,
        "production",
        "analytics_http_summary",
        since_minutes=120,
        per_page=50,
    )

    assert captured["url"].endswith("/graphql")
    assert "httpRequestsAdaptiveGroups" in captured["body"]["query"]
    assert captured["body"]["variables"]["zoneTag"] == ZONE_ID
    assert captured["body"]["variables"]["limit"] == 50
    assert result["ok"] is True


def test_dns_writes_are_zone_scoped_and_gated(tmp_path: Path) -> None:
    config = make_config(tmp_path, allow_dns_write=False)
    payload = {
        "type": "A",
        "name": "api.example.com",
        "content": "192.0.2.10",
        "ttl": 1,
        "proxied": True,
    }

    with pytest.raises(ValueError, match="allow_dns_write"):
        cloudflare_tools.build_cloudflare_action(
            config, "production", "dns_create", payload=payload
        )

    config.cloudflare.allow_dns_write = True
    spec = cloudflare_tools.build_cloudflare_action(
        config, "production", "dns_create", payload=payload
    )
    assert spec.method == "POST"
    assert spec.path == f"/zones/{ZONE_ID}/dns_records"
    assert spec.payload["name"] == "api.example.com"

    with pytest.raises(ValueError, match="outside the configured"):
        cloudflare_tools.build_cloudflare_action(
            config,
            "production",
            "dns_create",
            payload={**payload, "name": "outside.test"},
        )


def test_dns_batch_supports_post_put_patch_and_delete_entries(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    spec = cloudflare_tools.build_cloudflare_action(
        config,
        "production",
        "dns_batch",
        payload={
            "posts": [
                {
                    "type": "A",
                    "name": "api.example.com",
                    "content": "192.0.2.10",
                    "ttl": 1,
                }
            ],
            "puts": [
                {
                    "id": RECORD_ID,
                    "type": "A",
                    "name": "api.example.com",
                    "content": "192.0.2.11",
                    "ttl": 300,
                }
            ],
            "patches": [{"id": RECORD_ID, "content": "192.0.2.12", "proxied": True}],
            "deletes": [{"id": RECORD_ID}],
        },
        confirmation=config.cloudflare.confirmation_token,
    )

    assert spec.method == "POST"
    assert spec.path == f"/zones/{ZONE_ID}/dns_records/batch"
    assert spec.high_risk is True
    assert spec.payload["patches"][0]["id"] == RECORD_ID


def test_destructive_actions_require_confirmation(tmp_path: Path) -> None:
    config = make_config(tmp_path)

    with pytest.raises(ValueError, match="requires confirmation token"):
        cloudflare_tools.build_cloudflare_action(
            config,
            "production",
            "dns_delete",
            resource_id=RECORD_ID,
        )

    spec = cloudflare_tools.build_cloudflare_action(
        config,
        "production",
        "dns_delete",
        resource_id=RECORD_ID,
        confirmation=config.cloudflare.confirmation_token,
    )
    assert spec.method == "DELETE"
    assert spec.high_risk is True

    with pytest.raises(ValueError, match="requires confirmation token"):
        cloudflare_tools.build_cloudflare_action(
            config,
            "production",
            "cache_purge",
            payload={"purge_everything": True},
        )


def test_ruleset_phase_and_tunnel_scope_are_enforced(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    confirmation = config.cloudflare.confirmation_token

    with pytest.raises(ValueError, match="allowed_ruleset_phases"):
        cloudflare_tools.build_cloudflare_action(
            config,
            "production",
            "ruleset_create",
            payload={
                "name": "bad",
                "kind": "zone",
                "phase": "http_request_transform",
                "rules": [],
            },
            confirmation=confirmation,
        )

    spec = cloudflare_tools.build_cloudflare_action(
        config,
        "production",
        "ruleset_create",
        payload={
            "name": "custom",
            "kind": "zone",
            "phase": "http_request_firewall_custom",
            "rules": [],
        },
        confirmation=confirmation,
    )
    assert spec.path == f"/zones/{ZONE_ID}/rulesets"

    with pytest.raises(ValueError, match="allowed_tunnel_ids"):
        cloudflare_tools.build_cloudflare_action(
            config,
            "production",
            "tunnel_delete",
            resource_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            confirmation=confirmation,
        )


def test_tunnel_secret_is_generated_internally_and_response_is_redacted(
    monkeypatch, tmp_path: Path
) -> None:
    config = make_config(tmp_path)
    install_token(monkeypatch, config)
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse(
            {
                "success": True,
                "result": {
                    "id": TUNNEL_ID,
                    "token": "secret-token",
                    "credentials_file": {"TunnelSecret": "secret-value"},
                },
            }
        )

    monkeypatch.setattr(cloudflare_tools.urllib.request, "urlopen", fake_urlopen)
    result = cloudflare_tools.run_cloudflare_action(
        config,
        "production",
        "tunnel_create",
        payload={"name": "andia-tunnel"},
        confirmation=config.cloudflare.confirmation_token,
    )

    assert len(captured["body"]["tunnel_secret"]) >= 40
    assert result["result"]["token"] == "[REDACTED]"
    assert result["result"]["credentials_file"] == "[REDACTED]"
    assert "secret-token" not in result["stdout"]

    with pytest.raises(ValueError, match="forbidden"):
        cloudflare_tools.build_cloudflare_action(
            config,
            "production",
            "tunnel_create",
            payload={"name": "bad", "tunnel_secret": "caller-secret"},
            confirmation=config.cloudflare.confirmation_token,
        )


def test_api_errors_are_safe(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path)
    install_token(monkeypatch, config)

    def fake_urlopen(request, timeout):
        body = io.BytesIO(
            json.dumps(
                {
                    "success": False,
                    "errors": [{"code": 10000, "message": "Authentication error"}],
                }
            ).encode("utf-8")
        )
        raise urllib.error.HTTPError(
            request.full_url, 403, "Forbidden", hdrs=None, fp=body
        )

    monkeypatch.setattr(cloudflare_tools.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(ValueError, match="Authentication error") as exc:
        cloudflare_tools.run_cloudflare_inspection(config, "production", "token_verify")
    assert "test-cloudflare-token" not in str(exc.value)


def test_response_limit_and_capability_listing(monkeypatch, tmp_path: Path) -> None:
    config = make_config(tmp_path, max_output_bytes=1024)
    install_token(monkeypatch, config)

    class OversizedResponse(FakeResponse):
        def __init__(self):
            self.status = 200
            self.body = b"x" * 1025

    monkeypatch.setattr(
        cloudflare_tools.urllib.request,
        "urlopen",
        lambda request, timeout: OversizedResponse(),
    )
    with pytest.raises(ValueError, match="exceeded max_output_bytes"):
        cloudflare_tools.run_cloudflare_inspection(config, "production", "token_verify")

    capabilities = cloudflare_tools.list_cloudflare_capabilities(config)
    assert capabilities["enabled"] is True
    assert "dns_records" in capabilities["read_only_operations"]
    assert "tunnel_config_update" in capabilities["actions"]
    assert capabilities["arbitrary_http_supported"] is False
    assert capabilities["raw_graphql_supported"] is False
