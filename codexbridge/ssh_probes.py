from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Iterable

from .config import SSHHostConfig


@dataclass(frozen=True)
class SSHProbeSpec:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: int = 60
    required: bool = False


_PYTHON_ENVIRONMENT_EXPRESSION = (
    "print(__import__('json').dumps({"
    "'executable':__import__('sys').executable,"
    "'version':__import__('sys').version.split()[0],"
    "'prefix':__import__('sys').prefix,"
    "'base_prefix':__import__('sys').base_prefix,"
    "'virtual_env':__import__('os').environ.get('VIRTUAL_ENV',''),"
    "'platform':__import__('platform').platform(),"
    "'machine':__import__('platform').machine()"
    "}))"
)

_TORCH_ENVIRONMENT_EXPRESSION = (
    "print(__import__('json').dumps({"
    "'version':__import__('torch').__version__,"
    "'cuda_available':__import__('torch').cuda.is_available(),"
    "'cuda_version':__import__('torch').version.cuda,"
    "'device_count':__import__('torch').cuda.device_count()"
    "}))"
)

_GPU_QUERY_FIELDS: tuple[tuple[str, str], ...] = (
    ("index", "int"),
    ("name", "str"),
    ("uuid", "str"),
    ("driver_version", "str"),
    ("memory_total_mib", "float"),
    ("memory_used_mib", "float"),
    ("memory_free_mib", "float"),
    ("gpu_utilization_percent", "float"),
    ("memory_utilization_percent", "float"),
    ("temperature_c", "float"),
    ("power_draw_w", "float"),
    ("power_limit_w", "float"),
)

_GPU_PROCESS_FIELDS: tuple[tuple[str, str], ...] = (
    ("pid", "int"),
    ("process_name", "str"),
    ("gpu_uuid", "str"),
    ("used_gpu_memory_mib", "float"),
)


def environment_probe_specs() -> tuple[SSHProbeSpec, ...]:
    return (
        SSHProbeSpec("os", ("uname", "-srm"), required=True),
        SSHProbeSpec("working_directory", ("pwd",), required=True),
        SSHProbeSpec(
            "python_environment",
            ("python3", "-c", _PYTHON_ENVIRONMENT_EXPRESSION),
        ),
        SSHProbeSpec(
            "torch_environment",
            ("python3", "-c", _TORCH_ENVIRONMENT_EXPRESSION),
        ),
        SSHProbeSpec("cuda_compiler", ("nvcc", "--version")),
        SSHProbeSpec("system_memory", ("free", "-b"), required=True),
        SSHProbeSpec("root_disk", ("df", "-P", "-B1", "/"), required=True),
    )


def gpu_probe_specs() -> tuple[SSHProbeSpec, ...]:
    return (
        SSHProbeSpec(
            "gpu_devices",
            (
                "nvidia-smi",
                "--query-gpu=index,name,uuid,driver_version,memory.total,memory.used,memory.free,utilization.gpu,utilization.memory,temperature.gpu,power.draw,power.limit",
                "--format=csv,noheader,nounits",
            ),
        ),
        SSHProbeSpec(
            "gpu_processes",
            (
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,gpu_uuid,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ),
        ),
    )


def summarize_probe_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": bool(result.get("ok")),
        "exit_code": int(result.get("exit_code", 1)),
        "timed_out": bool(result.get("timed_out")),
        "duration_seconds": float(result.get("duration_seconds", 0.0)),
        "output_truncated": bool(result.get("output_truncated")),
        "error": str(result.get("error", "")),
    }


def parse_json_object(output: str) -> dict[str, Any]:
    value = json.loads(str(output or "").strip())
    if not isinstance(value, dict):
        raise ValueError("Probe output was not a JSON object")
    return value


def parse_system_memory(output: str) -> dict[str, Any]:
    for raw_line in str(output or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("Mem:"):
            continue
        parts = line.split()
        if len(parts) < 4:
            break
        total = int(parts[1])
        used = int(parts[2])
        free = int(parts[3])
        available = int(parts[6]) if len(parts) > 6 else max(0, total - used)
        used_effective = max(0, total - available)
        used_percent = round((used_effective / total) * 100, 3) if total else None
        return {
            "total_bytes": total,
            "used_bytes": used,
            "free_bytes": free,
            "available_bytes": available,
            "effective_used_bytes": used_effective,
            "used_percent": used_percent,
        }
    raise ValueError("Unable to parse free -b output")


def parse_root_disk(output: str) -> dict[str, Any]:
    lines = [line.strip() for line in str(output or "").splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("Unable to parse df output")
    parts = lines[-1].split()
    if len(parts) < 6:
        raise ValueError("Unable to parse df output")
    total = int(parts[-5])
    used = int(parts[-4])
    free = int(parts[-3])
    used_percent = float(parts[-2].rstrip("%"))
    return {
        "filesystem": " ".join(parts[:-5]),
        "mount_point": parts[-1],
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "used_percent": used_percent,
        "free_percent": round(max(0.0, 100.0 - used_percent), 3),
    }


def _coerce_csv_value(value: str, kind: str) -> Any:
    normalized = value.strip()
    if normalized in {"", "N/A", "[N/A]", "Not Supported"}:
        return None
    if kind == "int":
        return int(float(normalized))
    if kind == "float":
        return float(normalized)
    return normalized


def parse_csv_records(
    output: str, fields: Iterable[tuple[str, str]]
) -> list[dict[str, Any]]:
    normalized_fields = tuple(fields)
    records: list[dict[str, Any]] = []
    reader = csv.reader(io.StringIO(str(output or "")), skipinitialspace=True)
    for row in reader:
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) != len(normalized_fields):
            raise ValueError(
                f"Expected {len(normalized_fields)} CSV fields, received {len(row)}"
            )
        record = {
            name: _coerce_csv_value(value, kind)
            for (name, kind), value in zip(normalized_fields, row, strict=True)
        }
        records.append(record)
    return records


def parse_gpu_devices(output: str) -> list[dict[str, Any]]:
    devices = parse_csv_records(output, _GPU_QUERY_FIELDS)
    for device in devices:
        total = device.get("memory_total_mib")
        used = device.get("memory_used_mib")
        power_draw = device.get("power_draw_w")
        power_limit = device.get("power_limit_w")
        device["memory_used_percent"] = (
            round((float(used) / float(total)) * 100, 3)
            if total not in {None, 0} and used is not None
            else None
        )
        device["power_used_percent"] = (
            round((float(power_draw) / float(power_limit)) * 100, 3)
            if power_limit not in {None, 0} and power_draw is not None
            else None
        )
    return devices


def parse_gpu_processes(output: str) -> list[dict[str, Any]]:
    return parse_csv_records(output, _GPU_PROCESS_FIELDS)


def evaluate_watchdog(
    host: SSHHostConfig,
    *,
    devices: list[dict[str, Any]],
    system_memory: dict[str, Any] | None = None,
    root_disk: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config = host.watchdog
    breaches: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    def record(
        metric: str,
        observed: float | None,
        threshold: float,
        comparison: str,
        subject: str,
    ) -> None:
        breached = False
        if observed is not None:
            breached = (
                float(observed) > float(threshold)
                if comparison == "max"
                else float(observed) < float(threshold)
            )
        item = {
            "metric": metric,
            "subject": subject,
            "observed": observed,
            "threshold": threshold,
            "comparison": comparison,
            "available": observed is not None,
            "breached": breached,
        }
        checks.append(item)
        if breached:
            breaches.append(item)

    for device in devices:
        subject = f"gpu:{device.get('index', 'unknown')}"
        record(
            "gpu_memory_percent",
            device.get("memory_used_percent"),
            config.max_gpu_memory_percent,
            "max",
            subject,
        )
        record(
            "gpu_temperature_c",
            device.get("temperature_c"),
            config.max_gpu_temperature_c,
            "max",
            subject,
        )

    record(
        "system_memory_percent",
        (system_memory or {}).get("used_percent"),
        config.max_system_memory_percent,
        "max",
        "host",
    )
    record(
        "root_disk_free_percent",
        (root_disk or {}).get("free_percent"),
        config.min_disk_free_percent,
        "min",
        "host",
    )

    available_checks = [item for item in checks if item["available"]]
    status = "disabled"
    if config.enabled:
        if breaches:
            status = "breached"
        elif available_checks:
            status = "ok"
        else:
            status = "unknown"
    return {
        "enabled": config.enabled,
        "enforcement_mode": config.enforcement_mode,
        "status": status,
        "can_terminate_remote_processes": False,
        "checks": checks,
        "breaches": breaches,
        "thresholds": {
            "max_gpu_memory_percent": config.max_gpu_memory_percent,
            "max_gpu_temperature_c": config.max_gpu_temperature_c,
            "max_system_memory_percent": config.max_system_memory_percent,
            "min_disk_free_percent": config.min_disk_free_percent,
        },
    }
