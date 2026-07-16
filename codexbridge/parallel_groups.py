from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .config import AppConfig, resolve_repo, resolve_repo_config
from .events import ArtifactWriter
from .executable_profiles import build_local_executable_run_request
from .process_control import terminate_process_tree
from .run_store import RunStore, dumps, loads, utc_now, validate_run_id


def _make_group_run_id(tool: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_tool = "".join(char if char.isalnum() else "_" for char in tool.lower())
    return f"{timestamp}_{safe_tool}_{uuid4().hex[:8]}"


class ParallelGroupStore:
    """Durable parent/child reservation for parallel PowerShell command groups."""

    def __init__(self, runs_dir: Path):
        self.store = RunStore(runs_dir)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.store.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS command_groups (
                    group_id TEXT PRIMARY KEY,
                    repo_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    failure_policy TEXT NOT NULL,
                    repository_lock_policy TEXT NOT NULL,
                    requested_concurrency INTEGER,
                    created_at TEXT NOT NULL,
                    input_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS command_group_children (
                    group_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    run_id TEXT NOT NULL UNIQUE,
                    idempotency_key TEXT NOT NULL,
                    PRIMARY KEY (group_id, position),
                    UNIQUE (group_id, idempotency_key),
                    FOREIGN KEY(group_id) REFERENCES command_groups(group_id)
                        ON DELETE CASCADE,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                        ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_command_group_children_group "
                "ON command_group_children(group_id, position)"
            )

    def reserve_group(
        self,
        *,
        group_id: str,
        repo_name: str,
        children: list[dict[str, Any]],
        mode: str = "all_at_once",
        failure_policy: str = "continue_all",
        repository_lock_policy: str = "none",
        requested_concurrency: int | None = None,
        input_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        validate_run_id(group_id)
        if not children:
            raise ValueError("Parallel command group requires at least one child")
        if requested_concurrency is not None and int(requested_concurrency) < 1:
            raise ValueError("requested_concurrency must be positive or null")

        normalized_children: list[dict[str, Any]] = []
        seen_run_ids: set[str] = set()
        seen_keys: set[str] = set()
        for position, child in enumerate(children):
            run_id = str(child.get("run_id") or "")
            validate_run_id(run_id)
            idempotency_key = str(child.get("idempotency_key") or "").strip()
            if not idempotency_key:
                raise ValueError("Every parallel child requires an idempotency_key")
            if run_id in seen_run_ids:
                raise ValueError(f"Duplicate child run_id: {run_id}")
            if idempotency_key in seen_keys:
                raise ValueError(
                    f"Duplicate child idempotency_key: {idempotency_key}"
                )
            seen_run_ids.add(run_id)
            seen_keys.add(idempotency_key)
            lease_token = str(child.get("worker_lease_token") or "")
            if not lease_token:
                raise ValueError("Every parallel child requires a worker lease token")
            raw_run_dir = child.get("run_dir")
            if raw_run_dir is None or not str(raw_run_dir).strip():
                raise ValueError("Every parallel child requires a run_dir")
            run_dir = Path(str(raw_run_dir))
            initial_status = str(child.get("initial_status") or "launch_pending")
            if initial_status not in {"pending", "launch_pending"}:
                raise ValueError(
                    "Parallel child initial_status must be pending or launch_pending"
                )
            normalized_children.append(
                {
                    "position": position,
                    "run_id": run_id,
                    "idempotency_key": idempotency_key,
                    "tool": str(child.get("tool") or "executable_profile"),
                    "run_dir": run_dir,
                    "input_data": dict(child.get("input_data") or {}),
                    "risk_level": str(child.get("risk_level") or "high"),
                    "requires_human": bool(child.get("requires_human", False)),
                    "worker_lease_token": lease_token,
                    "initial_status": initial_status,
                }
            )

        created_at = utc_now()
        conn = self.store.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO command_groups (
                    group_id, repo_name, status, mode, failure_policy,
                    repository_lock_policy, requested_concurrency,
                    created_at, input_json
                ) VALUES (?, ?, 'launch_pending', ?, ?, ?, ?, ?, ?)
                """,
                (
                    group_id,
                    repo_name,
                    mode,
                    failure_policy,
                    repository_lock_policy,
                    requested_concurrency,
                    created_at,
                    dumps(input_data or {}),
                ),
            )
            for child in normalized_children:
                conn.execute(
                    """
                    INSERT INTO runs (
                        run_id, repo_name, tool, status, risk_level,
                        requires_human, created_at, run_dir, current_phase,
                        heartbeat_at, input_json, worker_lease_token
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        child["run_id"],
                        repo_name,
                        child["tool"],
                        child["initial_status"],
                        child["risk_level"],
                        int(child["requires_human"]),
                        created_at,
                        str(child["run_dir"]),
                        child["initial_status"],
                        created_at,
                        dumps(child["input_data"]),
                        child["worker_lease_token"],
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO command_group_children (
                        group_id, position, run_id, idempotency_key
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        group_id,
                        child["position"],
                        child["run_id"],
                        child["idempotency_key"],
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_group(group_id)

    def get_group(self, group_id: str) -> dict[str, Any]:
        validate_run_id(group_id)
        with self.store.connect() as conn:
            group = conn.execute(
                "SELECT * FROM command_groups WHERE group_id = ?", (group_id,)
            ).fetchone()
            if group is None:
                raise KeyError(f"Command group not found: {group_id}")
            children = conn.execute(
                """
                SELECT position, run_id, idempotency_key
                FROM command_group_children
                WHERE group_id = ?
                ORDER BY position ASC
                """,
                (group_id,),
            ).fetchall()
        payload = dict(group)
        payload["input"] = loads(payload.pop("input_json"))
        payload["children"] = [dict(child) for child in children]
        payload["child_run_ids"] = [child["run_id"] for child in payload["children"]]
        return payload


def launch_powershell_group(
    *,
    config: AppConfig,
    repo_name: str,
    children: list[dict[str, Any]],
    spawn_worker: Callable[[str, str], Any],
    group_id: str | None = None,
    requested_concurrency: int | None = None,
    repository_lock_policy: str = "none",
) -> dict[str, Any]:
    """Validate, reserve, materialize, then launch a parallel PowerShell group."""
    parallel = config.parallel_execution
    if not parallel.enabled:
        raise ValueError("Parallel PowerShell execution is disabled")
    if parallel.autonomy_profile != "permissive":
        raise ValueError("Parallel PowerShell execution requires permissive autonomy")
    if repository_lock_policy != "none":
        raise ValueError("Only lock-free parallel launch is implemented in this batch")
    if not children:
        raise ValueError("Parallel PowerShell group requires at least one child")

    resolve_repo(config, repo_name)
    canonical_repo_name, _ = resolve_repo_config(config, repo_name)
    configured_limit = parallel.max_concurrent_powershell
    if requested_concurrency is not None:
        requested_concurrency = int(requested_concurrency)
        if requested_concurrency < 1:
            raise ValueError("requested_concurrency must be positive or null")
        if configured_limit is not None and requested_concurrency > configured_limit:
            raise ValueError(
                "requested_concurrency exceeds max_concurrent_powershell"
            )
    effective_limit = requested_concurrency
    if effective_limit is None:
        effective_limit = configured_limit

    runs_dir = config.resolve_runs_dir()
    store = ParallelGroupStore(runs_dir)
    eligible_count = len(children) if effective_limit is None else effective_limit
    reserved_children: list[dict[str, Any]] = []
    for index, child in enumerate(children):
        profile_id = str(child.get("profile_id") or "powershell")
        argv = child.get("argv")
        if not isinstance(argv, list):
            raise ValueError("Every parallel PowerShell child requires argv")
        request = build_local_executable_run_request(
            config,
            profile_id,
            argv,
            working_directory=str(child.get("working_directory") or ""),
            environment=dict(child.get("environment") or {}),
            stdin_text=child.get("stdin_text"),
            stdin_bytes=child.get("stdin_bytes"),
            timeout_seconds=child.get("timeout_seconds"),
        )
        run_id = str(child.get("run_id") or _make_group_run_id("executable_profile"))
        lease_token = uuid4().hex
        input_data = {
            "repo_name": canonical_repo_name,
            "requested_repo_name": repo_name,
            **request,
        }
        reserved_children.append(
            {
                "run_id": run_id,
                "idempotency_key": str(
                    child.get("idempotency_key") or uuid4().hex
                ),
                "run_dir": runs_dir / run_id,
                "worker_lease_token": lease_token,
                "input_data": input_data,
                "risk_level": "high",
                "requires_human": False,
                "initial_status": (
                    "launch_pending" if index < eligible_count else "pending"
                ),
            }
        )

    selected_group_id = group_id or _make_group_run_id("powershell_group")
    group = store.reserve_group(
        group_id=selected_group_id,
        repo_name=canonical_repo_name,
        children=reserved_children,
        requested_concurrency=requested_concurrency,
        repository_lock_policy=repository_lock_policy,
        input_data={
            "autonomy_profile": "permissive",
            "requested_repo_name": repo_name,
            "child_count": len(reserved_children),
        },
    )

    for child in reserved_children:
        run_dir = Path(child["run_dir"])
        run_dir.mkdir(parents=True, exist_ok=False)
        artifacts = ArtifactWriter(run_dir)
        artifacts.write_json("input.json", child["input_data"])
        initial_status = child["initial_status"]
        event = store.store.append_event(
            child["run_id"],
            level="info",
            stage=initial_status,
            message=(
                "Parallel child launch intent recorded"
                if initial_status == "launch_pending"
                else "Parallel child reserved pending a concurrency slot"
            ),
            data={"group_id": selected_group_id},
        )
        artifacts.append_event(event)

    launched_run_ids: list[str] = []
    pending_run_ids: list[str] = []
    eligible_count = len(reserved_children) if effective_limit is None else effective_limit
    for index, child in enumerate(reserved_children):
        run_id = child["run_id"]
        if index >= eligible_count:
            pending_run_ids.append(run_id)
            continue
        run_dir = Path(child["run_dir"])
        try:
            launch_intent = store.store.get_run(run_id)
            process = spawn_worker(run_id, child["worker_lease_token"])
            launched = store.store.record_worker_launch(
                run_id,
                process.pid,
                expected_state_version=int(launch_intent["state_version"]),
                expected_lease_token=child["worker_lease_token"],
                expected_lease_generation=int(launch_intent["lease_generation"]),
            )
            current = launched or store.store.get_run(run_id)
            if not (
                str(current.get("worker_lease_token") or "")
                == child["worker_lease_token"]
                and current["status"] in {"queued", "running"}
            ):
                terminate_process_tree(process.pid)
                raise RuntimeError("Parallel child launch lost durable lease ownership")
            event = store.store.append_event(
                run_id,
                level="info",
                stage="worker",
                message="Parallel child worker launcher started",
                data={"group_id": selected_group_id, "launcher_pid": process.pid},
            )
            ArtifactWriter(run_dir).append_event(event)
            launched_run_ids.append(run_id)
        except Exception as exc:
            current = store.store.get_run(run_id)
            reason = f"Parallel child worker launch failed: {exc}"
            failed = store.store.fail_infrastructure(
                run_id,
                reason,
                expected_statuses=(str(current["status"]),),
                expected_state_version=int(current["state_version"]),
                expected_lease_token=str(current.get("worker_lease_token") or ""),
                expected_lease_generation=int(current.get("lease_generation") or 1),
                expected_heartbeat_at=current.get("heartbeat_at"),
            )
            if failed is not None:
                event = store.store.append_event(
                    run_id,
                    level="error",
                    stage="launch_failed",
                    message=reason,
                    data={"group_id": selected_group_id},
                    update_run_metadata=False,
                )
                ArtifactWriter(run_dir).append_event(event)

    result = store.get_group(selected_group_id)
    result.update(
        {
            "accepted": True,
            "launched_run_ids": launched_run_ids,
            "pending_run_ids": pending_run_ids,
        }
    )
    return result
