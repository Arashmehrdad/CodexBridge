"""Run one bounded real CDX-R1 Codex App Server pilot case.

This script is intentionally not a public Soma gateway. It is an acceptance
harness for the owner-approved G5 CLI provider pilot. It uses ChatGPT-managed
Codex authentication, synthetic committed input, a read-only sandbox, no tools,
and at most one model turn per invocation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from soma.reasoning.codex_app_server import (
    CodexAppServerClient,
    CodexAppServerRpcError,
    StdioCodexTransport,
    canonical_schema_manifest_hash,
    find_turn_by_client_user_message_id,
    resolve_codex_executable,
)
from soma.reasoning.codex_pilot import (
    build_evidence_submission,
    extract_usage,
    load_packet_bytes,
    packet_hash,
    parse_semantic_output,
    semantic_output_schema,
    semantic_payload_hash,
    semantic_prompt,
    sha256_hex,
    validate_semantic_against_packet,
)


DEFAULT_MODEL = "gpt-5.6-luna"
DEFAULT_EFFORT = "low"
DEFAULT_PROTOCOL_HASH = (
    "dcc92e96e856b1d4f93548f7f8f73e26aa87766431a0e44ceb23049c58c0dcbc"
)
PILOT_SCHEMA = "soma.cdx_r1.real_pilot.v1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _command_argv(executable: str, *args: str) -> list[str]:
    path = Path(executable)
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat"}:
        comspec = os.environ.get("COMSPEC") or r"C:\Windows\System32\cmd.exe"
        return [comspec, "/d", "/s", "/c", str(path), *args]
    return [str(path), *args]


def _cli_version(executable: str) -> str:
    completed = subprocess.run(
        _command_argv(executable, "--version"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return completed.stdout.strip()


def _protocol_fingerprint(executable: str) -> tuple[str, int]:
    with tempfile.TemporaryDirectory(prefix="soma-cdx-r1-schema-") as directory:
        completed = subprocess.run(
            _command_argv(
                executable,
                "app-server",
                "generate-json-schema",
                "--out",
                directory,
            ),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Codex App Server schema generation failed before model execution"
            )
        return canonical_schema_manifest_hash(Path(directory))


def _client(executable: str, cwd: str) -> CodexAppServerClient:
    transport = StdioCodexTransport(
        codex_executable=executable,
        working_directory=cwd,
    )
    client = CodexAppServerClient(transport, request_timeout_seconds=30)
    client.initialize()
    return client


def _extract_thread_id(result: dict[str, Any]) -> str:
    thread = result.get("thread")
    value = thread.get("id") if isinstance(thread, dict) else None
    if not isinstance(value, str) or not value:
        raise RuntimeError("Codex thread response did not contain an exact thread ID")
    return value


def _extract_turn_id(result: dict[str, Any]) -> str:
    turn = result.get("turn")
    value = turn.get("id") if isinstance(turn, dict) else None
    if not isinstance(value, str) or not value:
        raise RuntimeError("Codex turn response did not contain an exact turn ID")
    return value


def _thread_turn_status(thread: dict[str, Any], turn_id: str) -> str:
    turns = thread.get("turns")
    if not isinstance(turns, list):
        return ""
    for turn in turns:
        if isinstance(turn, dict) and turn.get("id") == turn_id:
            status = turn.get("status")
            return status if isinstance(status, str) else ""
    return ""


def _preflight(
    *,
    executable: str,
    expected_protocol_hash: str,
    model: str,
) -> dict[str, Any]:
    version = _cli_version(executable)
    protocol_hash, schema_count = _protocol_fingerprint(executable)
    if protocol_hash != expected_protocol_hash:
        raise RuntimeError(
            "Codex App Server canonical protocol schema drifted: "
            f"expected {expected_protocol_hash}, observed {protocol_hash}"
        )

    with tempfile.TemporaryDirectory(prefix="soma-cdx-r1-meta-") as directory:
        client = _client(executable, directory)
        try:
            account = client.account_read()
            models = client.model_list()
            limits = client.rate_limits_read()
        finally:
            client.close()

    account_value = account.get("account")
    account_value = account_value if isinstance(account_value, dict) else {}
    auth_type = str(account_value.get("type") or "")
    plan_type = str(account_value.get("planType") or "")
    if auth_type != "chatgpt":
        raise RuntimeError(
            f"CDX-R1 requires ChatGPT-managed Codex auth, observed {auth_type!r}"
        )

    data = models.get("data") or models.get("models") or []
    model_ids = {
        str(item.get("id") or item.get("model") or item.get("slug") or "")
        for item in data
        if isinstance(item, dict)
    }
    if model not in model_ids:
        raise RuntimeError(f"CDX-R1 model {model!r} is absent from current model/list")

    return {
        "cli_version": version,
        "protocol_manifest_sha256": protocol_hash,
        "protocol_schema_file_count": schema_count,
        "auth_type": auth_type,
        "plan_type": plan_type,
        "requires_openai_auth": bool(account.get("requiresOpenaiAuth")),
        "model_count": len(model_ids),
        "rate_limit_snapshot_sha256": _hash_json(limits),
    }


def _base_summary(
    *,
    mode: str,
    preflight: dict[str, Any],
    packet_bytes: bytes,
    model: str,
    effort: str,
) -> dict[str, Any]:
    return {
        "schema_version": PILOT_SCHEMA,
        "pilot": "CDX-R1",
        "mode": mode,
        "api_spend_usd": "0.00",
        "model_turns_used": 1,
        "model": model,
        "reasoning_effort": effort,
        "packet_sha256": packet_hash(packet_bytes),
        **preflight,
    }


def run_normal(
    *,
    executable: str,
    packet_bytes: bytes,
    preflight: dict[str, Any],
    model: str,
    effort: str,
) -> dict[str, Any]:
    prompt = semantic_prompt(packet_bytes)
    client_message_id = "soma-cdx-r1-normal-v1"
    started_at = time.monotonic()

    with tempfile.TemporaryDirectory(prefix="soma-cdx-r1-normal-") as directory:
        client = _client(executable, directory)
        try:
            thread_id = _extract_thread_id(
                client.start_thread(working_directory=directory, model=model)
            )
            turn_id = _extract_turn_id(
                client.start_turn(
                    thread_id=thread_id,
                    prompt=prompt,
                    client_user_message_id=client_message_id,
                    output_schema=semantic_output_schema(),
                    model=model,
                    effort=effort,
                )
            )
            turn_evidence = client.wait_for_turn_completed(
                thread_id=thread_id,
                turn_id=turn_id,
                timeout_seconds=180,
            )
            server_request_count = len(client.server_requests)
        finally:
            client.close()

        payload = parse_semantic_output(turn_evidence.agent_message)
        validate_semantic_against_packet(payload, packet_bytes)
        usage = extract_usage(turn_evidence.token_usage_events)
        raw_events_hash = _hash_json(turn_evidence.events)
        semantic_hash = semantic_payload_hash(payload)
        submission = build_evidence_submission(
            payload=payload,
            packet_bytes=packet_bytes,
            task_id="task_cdx_r1_real_normal",
            backend_ref="reasoning_cdx_r1_real_normal",
            assignment_ref="assignment:cdx-r1-synthetic-packet",
            provider_model=model,
            provider_thread_id=thread_id,
            usage=usage,
            wall_time_seconds=time.monotonic() - started_at,
            provenance_refs=(
                (
                    f"codex:thread:{thread_id}",
                    sha256_hex(thread_id.encode("utf-8")),
                ),
                (
                    f"codex:turn:{turn_id}",
                    sha256_hex(turn_id.encode("utf-8")),
                ),
            ),
            raw_provider_ref=f"codex:event-root:{raw_events_hash}",
            raw_provider_hash=raw_events_hash,
        )
        submission_json = submission.model_dump(mode="json")

        restarted = _client(executable, directory)
        try:
            read_result = restarted.read_thread(thread_id, include_turns=True)
            recovered_thread = read_result.get("thread")
            if not isinstance(recovered_thread, dict):
                raise RuntimeError("thread/read did not return a thread object")
            reconciled_turn = find_turn_by_client_user_message_id(
                recovered_thread,
                client_message_id,
            )
            resumed_id = _extract_thread_id(restarted.resume_thread(thread_id))
            fork_result = restarted.fork_thread(thread_id, last_turn_id=turn_id)
            fork_thread = fork_result.get("thread")
            fork_thread = fork_thread if isinstance(fork_thread, dict) else {}
        finally:
            restarted.close()

    if reconciled_turn != turn_id:
        raise RuntimeError(
            "Exact clientUserMessageId recovery did not resolve the original turn ID"
        )
    if resumed_id != thread_id:
        raise RuntimeError("thread/resume changed the exact provider thread identity")

    summary = _base_summary(
        mode="normal",
        preflight=preflight,
        packet_bytes=packet_bytes,
        model=model,
        effort=effort,
    )
    summary.update(
        {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "client_user_message_id": client_message_id,
            "turn_status": turn_evidence.status,
            "recovered_thread_id": str(recovered_thread.get("id") or ""),
            "reconciled_turn_id": reconciled_turn,
            "resumed_thread_id": resumed_id,
            "fork_thread_id": str(fork_thread.get("id") or ""),
            "fork_parent_thread_id": str(
                fork_thread.get("parentThreadId")
                or fork_thread.get("forkedFromId")
                or ""
            ),
            "semantic_payload_sha256": semantic_hash,
            "evidence_submission_id": submission.submission_id,
            "evidence_submission_sha256": _hash_json(submission_json),
            "evidence_submission_bytes": submission.serialized_bytes,
            "usage": usage.model_dump(mode="json"),
            "provider_event_count": len(turn_evidence.events),
            "provider_event_root_sha256": raw_events_hash,
            "server_request_count": server_request_count,
            "semantic_validation": "passed",
            "evidence_submission_validation": "passed",
        }
    )
    return summary


def run_lost_ack(
    *,
    executable: str,
    packet_bytes: bytes,
    preflight: dict[str, Any],
    model: str,
    effort: str,
) -> dict[str, Any]:
    prompt = semantic_prompt(packet_bytes)
    client_message_id = "soma-cdx-r1-lost-ack-v1"

    with tempfile.TemporaryDirectory(prefix="soma-cdx-r1-lost-ack-") as directory:
        client = _client(executable, directory)
        try:
            thread_id = _extract_thread_id(
                client.start_thread(working_directory=directory, model=model)
            )
            sent_request_id = client.begin_turn(
                thread_id=thread_id,
                prompt=prompt,
                client_user_message_id=client_message_id,
                output_schema=semantic_output_schema(),
                model=model,
                effort=effort,
            )
            # Intentionally do not call await_response. Give App Server a bounded
            # moment to accept/persist the request, then discard the connection.
            time.sleep(0.5)
        finally:
            client.close()

        restarted = _client(executable, directory)
        try:
            deadline = time.monotonic() + 20
            recovered_thread: dict[str, Any] = {}
            reconciled_turn_id: str | None = None
            while time.monotonic() < deadline:
                read_result = restarted.read_thread(thread_id, include_turns=True)
                candidate = read_result.get("thread")
                if isinstance(candidate, dict):
                    recovered_thread = candidate
                    reconciled_turn_id = find_turn_by_client_user_message_id(
                        recovered_thread,
                        client_message_id,
                    )
                    if reconciled_turn_id is not None:
                        break
                time.sleep(0.5)
            turn_status = (
                _thread_turn_status(recovered_thread, reconciled_turn_id)
                if reconciled_turn_id
                else ""
            )
        finally:
            restarted.close()

    summary = _base_summary(
        mode="lost_ack",
        preflight=preflight,
        packet_bytes=packet_bytes,
        model=model,
        effort=effort,
    )
    summary.update(
        {
            "thread_id": thread_id,
            "sent_request_id": sent_request_id,
            "client_user_message_id": client_message_id,
            "ack_awaited": False,
            "automatic_turn_retry_count": 0,
            "reconciled_turn_id": reconciled_turn_id or "",
            "reconciliation": "resolved" if reconciled_turn_id else "uncertain",
            "turn_status": turn_status,
        }
    )
    return summary


def run_cancel(
    *,
    executable: str,
    packet_bytes: bytes,
    preflight: dict[str, Any],
    model: str,
    effort: str,
) -> dict[str, Any]:
    prompt = semantic_prompt(packet_bytes)
    client_message_id = "soma-cdx-r1-cancel-v1"

    with tempfile.TemporaryDirectory(prefix="soma-cdx-r1-cancel-") as directory:
        client = _client(executable, directory)
        try:
            thread_id = _extract_thread_id(
                client.start_thread(working_directory=directory, model=model)
            )
            turn_start_request_id = client.begin_turn(
                thread_id=thread_id,
                prompt=prompt,
                client_user_message_id=client_message_id,
                output_schema=semantic_output_schema(),
                model=model,
                effort=effort,
            )
            turn_id = client.wait_for_turn_started(
                thread_id=thread_id,
                timeout_seconds=30,
            )
            print(
                json.dumps(
                    {
                        "schema_version": PILOT_SCHEMA,
                        "pilot": "CDX-R1",
                        "mode": "cancel_checkpoint",
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "turn_start_request_id": turn_start_request_id,
                        "client_user_message_id": client_message_id,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ),
                flush=True,
            )
            interrupt_outcome = "requested"
            try:
                interrupt_result = client.interrupt_turn(
                    thread_id=thread_id,
                    turn_id=turn_id,
                )
            except CodexAppServerRpcError as exc:
                error_message = (
                    str(exc.error.get("message") or "")
                    if isinstance(exc.error, dict)
                    else str(exc.error)
                )
                if (
                    exc.method != "turn/interrupt"
                    or "no active turn to interrupt" not in error_message
                ):
                    raise
                interrupt_outcome = "completion_won_race"
                interrupt_result = {"error": exc.error}
            evidence = client.wait_for_turn_completed(
                thread_id=thread_id,
                turn_id=turn_id,
                timeout_seconds=60,
            )
            server_request_count = len(client.server_requests)
        finally:
            client.close()

        restarted = _client(executable, directory)
        try:
            read_result = restarted.read_thread(thread_id, include_turns=True)
            recovered = read_result.get("thread")
            recovered = recovered if isinstance(recovered, dict) else {}
            reconciled_turn = find_turn_by_client_user_message_id(
                recovered,
                client_message_id,
            )
            persisted_status = (
                _thread_turn_status(recovered, reconciled_turn)
                if reconciled_turn
                else ""
            )
        finally:
            restarted.close()

    summary = _base_summary(
        mode="cancel",
        preflight=preflight,
        packet_bytes=packet_bytes,
        model=model,
        effort=effort,
    )
    summary.update(
        {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "client_user_message_id": client_message_id,
            "turn_start_request_id": turn_start_request_id,
            "interrupt_outcome": interrupt_outcome,
            "interrupt_result_sha256": _hash_json(interrupt_result),
            "turn_status": evidence.status,
            "persisted_turn_status": persisted_status,
            "reconciled_turn_id": reconciled_turn or "",
            "interrupt_request_count": 1,
            "automatic_turn_retry_count": 0,
            "provider_event_count": len(evidence.events),
            "provider_event_root_sha256": _hash_json(evidence.events),
            "server_request_count": server_request_count,
        }
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("normal", "lost_ack", "cancel"), required=True
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default=DEFAULT_EFFORT)
    parser.add_argument("--expected-protocol-hash", default=DEFAULT_PROTOCOL_HASH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    executable = resolve_codex_executable()
    packet_bytes = load_packet_bytes(args.fixture)
    preflight = _preflight(
        executable=executable,
        expected_protocol_hash=args.expected_protocol_hash,
        model=args.model,
    )

    runner = {
        "normal": run_normal,
        "lost_ack": run_lost_ack,
        "cancel": run_cancel,
    }[args.mode]
    summary = runner(
        executable=executable,
        packet_bytes=packet_bytes,
        preflight=preflight,
        model=args.model,
        effort=args.effort,
    )
    print(json.dumps(summary, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
