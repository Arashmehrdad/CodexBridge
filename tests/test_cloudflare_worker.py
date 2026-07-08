from __future__ import annotations

import json
import secrets
from pathlib import Path

from codexbridge import cloudflare_tools
from codexbridge.job_worker import JobWorker
from codexbridge.run_store import RunStore


def test_cloudflare_action_worker_persists_result(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                "    cloudflare_profiles: [production]",
                "cloudflare:",
                "  enabled: true",
                "  allow_dns_write: true",
                "  profiles:",
                "    production:",
                f"      account_id: {'b' * 32}",
                f"      zone_id: {'a' * 32}",
                "      zone_name: example.com",
                "      allowed_dns_names: [api.example.com]",
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_id = "20260708T000000Z_cloudflare_action_deadbeef"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    store.create_run(
        run_id=run_id,
        repo_name="cloudflare:sample:production",
        tool="cloudflare_action",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "profile_id": "production",
            "action": "dns_create",
            "resource_id": "",
            "payload": {
                "type": "A",
                "name": "api.example.com",
                "content": "192.0.2.10",
                "ttl": 1,
                "proxied": True,
            },
            "confirmation": "",
        },
    )
    monkeypatch.setattr(
        "codexbridge.job_worker.run_cloudflare_action",
        lambda config, profile_id, action, **kwargs: {
            "ok": True,
            "profile_id": profile_id,
            "action": action,
            "method": "POST",
            "path": f"/zones/{'a' * 32}/dns_records",
            "writes_remote": True,
            "high_risk": False,
            "remote_state_verified": False,
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 0.1,
            "stdout": '{"ok": true}',
            "stderr": "",
            "output_truncated": False,
            "error": "",
            "result": {"id": "c" * 32},
        },
    )

    assert JobWorker(config_path, run_id).execute() == 0
    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert persisted["status"] == "completed"
    assert result["tool"] == "cloudflare_action"
    assert result["repo_name"] == "sample"
    assert result["cloudflare_profile_id"] == "production"
    assert result["profile_id"] == "production"
    assert result["action"] == "dns_create"
    assert result["method"] == "POST"
    assert result["high_risk"] is False
    assert result["remote_state_verified"] is False
    assert result["changed_files"] == []
    assert (run_dir / "cloudflare_result.json").is_file()
    assert (run_dir / "stdout.txt").read_text(encoding="utf-8") == '{"ok": true}'


def test_turnstile_rotation_worker_never_persists_secret(
    monkeypatch, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    runs_dir = tmp_path / "runs"
    config_path = tmp_path / "config.yaml"
    sitekey = "0x" + ("a" * 30)
    config_path.write_text(
        "\n".join(
            [
                "repos:",
                "  sample:",
                f'    path: "{repo.as_posix()}"',
                "    cloudflare_profiles: [production]",
                "cloudflare:",
                "  enabled: true",
                "  allow_turnstile_write: true",
                "  allow_turnstile_secret_rotation: true",
                "  profiles:",
                "    production:",
                f"      account_id: {'b' * 32}",
                f"      allowed_turnstile_sitekeys: [{sitekey}]",
                "      turnstile:",
                "        secret_destination:",
                "          type: env_file",
                "          path: .env.production",
                "          variable: TURNSTILE_SECRET_KEY",
                f'runs_dir: "{runs_dir.as_posix()}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    generated_secret = "worker-" + secrets.token_hex(24)
    run_id = "20260708T000001Z_cloudflare_action_feedface"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    store = RunStore(runs_dir)
    confirmation = "CONFIRM_CLOUDFLARE_HIGH_RISK"
    store.create_run(
        run_id=run_id,
        repo_name="cloudflare:sample:production",
        tool="cloudflare_action",
        run_dir=run_dir,
        input_data={
            "repo_name": "sample",
            "profile_id": "production",
            "action": "turnstile_rotate_secret",
            "resource_id": sitekey,
            "payload": {},
            "confirmation": confirmation,
        },
    )
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "unit-test-token")
    monkeypatch.setattr(
        cloudflare_tools, "_git_path_is_ignored", lambda repo_root, path: True
    )

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, limit=-1):
            return json.dumps(
                {
                    "success": True,
                    "result": {
                        "sitekey": sitekey,
                        "name": "Andia Clinic",
                        "domains": ["andiyaclinic.ir", "www.andiyaclinic.ir"],
                        "secret": generated_secret,
                    },
                }
            ).encode("utf-8")

    monkeypatch.setattr(
        cloudflare_tools.urllib.request,
        "urlopen",
        lambda request, timeout: FakeResponse(),
    )

    assert JobWorker(config_path, run_id).execute() == 0
    persisted = store.get_run(run_id)
    result = persisted["result"]
    assert result["action"] == "turnstile_rotate_secret"
    assert result["cloudflare_result"]["result"] == {
        "sitekey": sitekey,
        "widget_name": "Andia Clinic",
        "domains": ["andiyaclinic.ir", "www.andiyaclinic.ir"],
        "rotated": True,
        "grace_period_hours": 2,
        "secret_destination_updated": True,
    }
    env_text = (repo / ".env.production").read_text(encoding="utf-8")
    if generated_secret not in env_text:
        raise AssertionError("secret destination was not updated")

    persisted_bytes = json.dumps(persisted, sort_keys=True).encode("utf-8")
    run_artifact_bytes = b"".join(
        path.read_bytes() for path in run_dir.rglob("*") if path.is_file()
    )
    database_bytes = b"".join(
        path.read_bytes()
        for path in runs_dir.glob("codexbridge.sqlite3*")
        if path.is_file()
    )
    if any(
        generated_secret.encode("utf-8") in data
        for data in (persisted_bytes, run_artifact_bytes, database_bytes)
    ):
        raise AssertionError("Turnstile secret leaked into durable run storage")
