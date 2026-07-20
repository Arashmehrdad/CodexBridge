from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .config import AppConfig, resolve_repo, resolve_repo_config
from .events import ArtifactWriter
from .executable_profiles import build_local_executable_run_request
from .process_control import terminate_process_tree
from .run_store import TERMINAL_STATUSES, RunStore, dumps, loads, utc_now, validate_run_id


def _make_group_run_id(tool: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_tool = "".join(char if char.isalnum() else "_" for char in tool.lower())
    return f"{timestamp}_{safe_tool}_{uuid4().hex[:8]}"


def repository_lock_required_for_run(run: dict[str, Any], runs_dir: Path) -> bool:
    """Resolve the durable repository-lock policy for one standalone or group run."""

    input_data = run.get("input")
    if isinstance(input_data, dict) and "repository_lock_required" in input_data:
        required = input_data["repository_lock_required"]
        if not isinstance(required, bool):
            raise ValueError("Persisted repository_lock_required must be boolean")
        if not required and not (
            str(run.get("tool") or "") == "executable_profile"
            and isinstance(input_data.get("hermes_companion"), dict)
        ):
            raise ValueError(
                "Only persisted Hermes companion executable runs may disable the repository lock"
            )
        return required
    return ParallelGroupStore(runs_dir).repository_lock_required_for_child(
        str(run["run_id"])
    )


class ParallelGroupStore:
    """Durable parent/child reservation for parallel PowerShell command groups."""

    @staticmethod
    def _child_payload(row) -> dict[str, Any]:
        payload = dict(row)
        result = loads(payload.pop("result_json", "{}"))
        artifacts = {
            key: result[key]
            for key in ("stdout_artifact", "stderr_artifact", "transcript_artifact")
            if result.get(key)
        }
        if isinstance(result.get("artifacts"), dict):
            artifacts.update(result["artifacts"])
        payload["artifacts"] = artifacts
        return payload

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
                    ended_at TEXT,
                    input_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}'
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
            self.store._ensure_column(conn, "command_groups", "ended_at", "TEXT")
            self.store._ensure_column(
                conn,
                "command_groups",
                "result_json",
                "TEXT NOT NULL DEFAULT '{}'",
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
                SELECT child.position, child.run_id, child.idempotency_key,
                       run.status, run.current_phase, run.summary, run.error,
                       run.exit_code, run.started_at, run.ended_at, run.result_json
                FROM command_group_children AS child
                JOIN runs AS run ON run.run_id = child.run_id
                WHERE child.group_id = ?
                ORDER BY child.position ASC
                """,
                (group_id,),
            ).fetchall()
        payload = dict(group)
        payload["input"] = loads(payload.pop("input_json"))
        payload["result"] = loads(payload.pop("result_json"))
        payload["children"] = [self._child_payload(child) for child in children]
        payload["child_run_ids"] = [child["run_id"] for child in payload["children"]]
        return payload

    def get_group_for_child(self, run_id: str) -> dict[str, Any]:
        validate_run_id(run_id)
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT group_id FROM command_group_children WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Parallel child is not attached to a command group: {run_id}")
        return self.get_group(str(row["group_id"]))

    def repository_lock_required_for_child(self, run_id: str) -> bool:
        """Return whether a child run must own the repository operation lock."""
        validate_run_id(run_id)
        with self.store.connect() as conn:
            row = conn.execute(
                """
                SELECT groups.repository_lock_policy
                FROM command_group_children AS child
                JOIN command_groups AS groups ON groups.group_id = child.group_id
                WHERE child.run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return True
        return str(row["repository_lock_policy"]) != "none"

    def refresh_group(self, group_id: str) -> dict[str, Any]:
        """Publish an aggregate snapshot derived only from durable child state."""
        validate_run_id(group_id)
        terminal_statuses = tuple(sorted(TERMINAL_STATUSES))
        now = utc_now()
        conn = self.store.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            group = conn.execute(
                "SELECT * FROM command_groups WHERE group_id = ?", (group_id,)
            ).fetchone()
            if group is None:
                raise KeyError(f"Command group not found: {group_id}")
            children = conn.execute(
                """
                SELECT child.position, child.run_id, child.idempotency_key,
                       run.status, run.current_phase, run.summary, run.error,
                       run.exit_code, run.started_at, run.ended_at, run.result_json
                FROM command_group_children AS child
                JOIN runs AS run ON run.run_id = child.run_id
                WHERE child.group_id = ?
                ORDER BY child.position ASC
                """,
                (group_id,),
            ).fetchall()
            child_payloads = [self._child_payload(child) for child in children]
            statuses = [str(child["status"]) for child in child_payloads]
            counts = {status: statuses.count(status) for status in sorted(set(statuses))}
            terminal_count = sum(status in terminal_statuses for status in statuses)
            total = len(statuses)
            if total and terminal_count == total:
                if all(status == "completed" for status in statuses):
                    aggregate_status = "completed"
                elif all(status == "cancelled" for status in statuses):
                    aggregate_status = "cancelled"
                elif any(status in {"failed", "timed_out"} for status in statuses):
                    aggregate_status = "failed"
                else:
                    aggregate_status = "partial"
                ended_at = max(
                    (str(child.get("ended_at") or "") for child in child_payloads),
                    default=now,
                ) or now
            elif any(
                status in {
                    "queued",
                    "running",
                    "cancellation_pending",
                    "recovery_pending",
                }
                for status in statuses
            ):
                aggregate_status = "running"
                ended_at = None
            else:
                aggregate_status = "launch_pending"
                ended_at = None
            result = {
                "group_id": group_id,
                "repo_name": str(group["repo_name"]),
                "status": aggregate_status,
                "child_count": total,
                "terminal_child_count": terminal_count,
                "status_counts": counts,
                "children": child_payloads,
            }
            conn.execute(
                """
                UPDATE command_groups
                SET status = ?, ended_at = ?, result_json = ?
                WHERE group_id = ?
                """,
                (aggregate_status, ended_at, dumps(result), group_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return self.get_group(group_id)

    def refresh_all_groups(self) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            group_ids = [
                str(row["group_id"])
                for row in conn.execute(
                    "SELECT group_id FROM command_groups ORDER BY created_at ASC"
                ).fetchall()
            ]
        return [self.refresh_group(group_id) for group_id in group_ids]

    def claim_pending_launches(
        self,
        *,
        max_concurrent_powershell: int | None,
    ) -> list[dict[str, Any]]:
        """Atomically promote pending children without exceeding global/group limits."""
        active_statuses = (
            "launch_pending",
            "queued",
            "running",
            "cancellation_pending",
            "recovery_pending",
        )
        claimed_run_ids: list[str] = []
        now = utc_now()
        conn = self.store.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            active_total = int(
                conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM command_group_children AS child
                    JOIN runs AS run ON run.run_id = child.run_id
                    WHERE run.status IN (?, ?, ?, ?, ?)
                    """,
                    active_statuses,
                ).fetchone()[0]
            )
            global_slots = (
                None
                if max_concurrent_powershell is None
                else max(0, int(max_concurrent_powershell) - active_total)
            )
            groups = conn.execute(
                """
                SELECT group_id, requested_concurrency
                FROM command_groups
                WHERE EXISTS (
                    SELECT 1
                    FROM command_group_children AS child
                    JOIN runs AS run ON run.run_id = child.run_id
                    WHERE child.group_id = command_groups.group_id
                      AND run.status = 'pending'
                )
                ORDER BY created_at ASC, group_id ASC
                """
            ).fetchall()
            for group in groups:
                if global_slots == 0:
                    break
                group_id = str(group["group_id"])
                requested = group["requested_concurrency"]
                active_group = int(
                    conn.execute(
                        """
                        SELECT COUNT(*)
                        FROM command_group_children AS child
                        JOIN runs AS run ON run.run_id = child.run_id
                        WHERE child.group_id = ?
                          AND run.status IN (?, ?, ?, ?, ?)
                        """,
                        (group_id, *active_statuses),
                    ).fetchone()[0]
                )
                group_slots = (
                    None
                    if requested is None
                    else max(0, int(requested) - active_group)
                )
                slots = group_slots
                if global_slots is not None:
                    slots = global_slots if slots is None else min(slots, global_slots)
                if slots == 0:
                    continue
                query = """
                    SELECT run.run_id
                    FROM command_group_children AS child
                    JOIN runs AS run ON run.run_id = child.run_id
                    WHERE child.group_id = ? AND run.status = 'pending'
                    ORDER BY child.position ASC
                """
                params: list[Any] = [group_id]
                if slots is not None:
                    query += " LIMIT ?"
                    params.append(int(slots))
                candidates = conn.execute(query, params).fetchall()
                for candidate in candidates:
                    run_id = str(candidate["run_id"])
                    updated = conn.execute(
                        """
                        UPDATE runs
                        SET status = 'launch_pending',
                            current_phase = 'launch_pending',
                            heartbeat_at = ?,
                            state_version = state_version + 1
                        WHERE run_id = ? AND status = 'pending'
                        """,
                        (now, run_id),
                    )
                    if int(updated.rowcount) != 1:
                        continue
                    claimed_run_ids.append(run_id)
                    if global_slots is not None:
                        global_slots -= 1
                        if global_slots == 0:
                            break
                if global_slots == 0:
                    break
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return [self.store.get_run(run_id) for run_id in claimed_run_ids]


def _launch_claimed_child(
    *,
    store: ParallelGroupStore,
    group_id: str,
    run: dict[str, Any],
    spawn_worker: Callable[[str, str], Any],
) -> bool:
    run_id = str(run["run_id"])
    lease_token = str(run.get("worker_lease_token") or "")
    run_dir = Path(run["run_dir"])
    try:
        process = spawn_worker(run_id, lease_token)
        launched = store.store.record_worker_launch(
            run_id,
            process.pid,
            expected_state_version=int(run["state_version"]),
            expected_lease_token=lease_token,
            expected_lease_generation=int(run["lease_generation"]),
        )
        current = launched or store.store.get_run(run_id)
        if not (
            str(current.get("worker_lease_token") or "") == lease_token
            and current["status"] in {"queued", "running"}
        ):
            terminate_process_tree(process.pid)
            raise RuntimeError("Parallel child launch lost durable lease ownership")
        event = store.store.append_event(
            run_id,
            level="info",
            stage="worker",
            message="Parallel child worker launcher started",
            data={"group_id": group_id, "launcher_pid": process.pid},
        )
        ArtifactWriter(run_dir).append_event(event)
        return True
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
                data={"group_id": group_id},
                update_run_metadata=False,
            )
            ArtifactWriter(run_dir).append_event(event)
        return False


def refill_powershell_groups(
    *,
    config: AppConfig,
    spawn_worker: Callable[[str, str], Any],
) -> list[str]:
    """Claim and launch available durable PowerShell slots exactly once."""
    parallel = config.parallel_execution
    if not parallel.enabled:
        return []
    store = ParallelGroupStore(config.resolve_runs_dir())
    store.refresh_all_groups()
    claimed = store.claim_pending_launches(
        max_concurrent_powershell=parallel.max_concurrent_powershell
    )
    launched: list[str] = []
    with store.store.connect() as conn:
        memberships = {
            str(row["run_id"]): str(row["group_id"])
            for row in conn.execute(
                """
                SELECT group_id, run_id
                FROM command_group_children
                WHERE run_id IN (
                    SELECT run_id FROM runs WHERE status = 'launch_pending'
                )
                """
            ).fetchall()
        }
    for run in claimed:
        run_id = str(run["run_id"])
        group_id = memberships.get(run_id)
        if not group_id:
            continue
        if _launch_claimed_child(
            store=store,
            group_id=group_id,
            run=run,
            spawn_worker=spawn_worker,
        ):
            launched.append(run_id)
    store.refresh_all_groups()
    return launched


def launch_powershell_group(
    *,
    config: AppConfig,
    repo_name: str,
    children: list[dict[str, Any]],
    spawn_worker: Callable[[str, str], Any],
    group_id: str | None = None,
    requested_concurrency: int | None = None,
    repository_lock_policy: str = "none",
    failure_policy: str = "continue_all",
) -> dict[str, Any]:
    """Validate, reserve, materialize, then launch a parallel PowerShell group."""
    parallel = config.parallel_execution
    if not parallel.enabled:
        raise ValueError("Parallel PowerShell execution is disabled")
    if parallel.autonomy_profile != "permissive":
        raise ValueError("Parallel PowerShell execution requires permissive autonomy")
    if repository_lock_policy != "none":
        raise ValueError("Only lock-free parallel launch is implemented in this batch")
    if failure_policy not in {"continue_all", "cancel_remaining_on_failure"}:
        raise ValueError("Unsupported parallel PowerShell failure policy")
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
        failure_policy=failure_policy,
        input_data={
            "autonomy_profile": "permissive",
            "requested_repo_name": repo_name,
            "child_count": len(reserved_children),
            "failure_policy": failure_policy,
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
