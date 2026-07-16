from __future__ import annotations

from pathlib import Path
from typing import Any

from .run_store import RunStore, dumps, loads, utc_now, validate_run_id


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
            run_dir = Path(str(child.get("run_dir") or ""))
            if not str(run_dir):
                raise ValueError("Every parallel child requires a run_dir")
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
                    ) VALUES (?, ?, ?, 'launch_pending', ?, ?, ?, ?,
                              'launch_pending', ?, ?, ?)
                    """,
                    (
                        child["run_id"],
                        repo_name,
                        child["tool"],
                        child["risk_level"],
                        int(child["requires_human"]),
                        created_at,
                        str(child["run_dir"]),
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
