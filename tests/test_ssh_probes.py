from __future__ import annotations

from codexbridge.config import (
    SSHCommandProfileConfig,
    SSHHostConfig,
    SSHWatchdogConfig,
)
from codexbridge.ssh_commands import validate_ssh_command_profile
from codexbridge.ssh_probes import (
    environment_probe_specs,
    evaluate_watchdog,
    gpu_probe_specs,
    parse_gpu_devices,
    parse_gpu_processes,
    parse_root_disk,
    parse_system_memory,
)


def test_probe_specs_are_fixed_argv_and_pass_shell_safety_validation() -> None:
    specs = (*environment_probe_specs(), *gpu_probe_specs())

    assert {spec.name for spec in specs} == {
        "os",
        "working_directory",
        "python_environment",
        "torch_environment",
        "cuda_compiler",
        "system_memory",
        "root_disk",
        "gpu_devices",
        "gpu_processes",
    }
    for spec in specs:
        validate_ssh_command_profile(
            SSHCommandProfileConfig(command_id=spec.name, argv=list(spec.argv))
        )
    python_expression = next(
        spec.argv[-1] for spec in specs if spec.name == "python_environment"
    )
    assert "environ.get('VIRTUAL_ENV'" in python_expression
    assert "dict(os.environ)" not in python_expression


def test_parse_system_memory_uses_available_memory_for_effective_usage() -> None:
    parsed = parse_system_memory(
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:     1000000000   600000000   100000000           0   300000000   400000000\n"
        "Swap:             0           0           0\n"
    )

    assert parsed["total_bytes"] == 1_000_000_000
    assert parsed["effective_used_bytes"] == 600_000_000
    assert parsed["used_percent"] == 60.0


def test_parse_root_disk_reports_free_percent() -> None:
    parsed = parse_root_disk(
        "Filesystem     1-blocks      Used Available Use% Mounted on\n"
        "/dev/root     1000000000 750000000 250000000  75% /\n"
    )

    assert parsed["filesystem"] == "/dev/root"
    assert parsed["mount_point"] == "/"
    assert parsed["free_percent"] == 25.0


def test_parse_gpu_devices_and_processes_adds_percentages() -> None:
    devices = parse_gpu_devices(
        "0, NVIDIA A40, GPU-abc, 550.54.15, 46068, 23034, 23034, 81, 52, 76, 184.5, 300.0\n"
        "1, NVIDIA A40, GPU-def, 550.54.15, 46068, 0, 46068, 0, 0, 41, N/A, 300.0\n"
    )
    processes = parse_gpu_processes(
        "1234, python3, GPU-abc, 22000\n"
        "4321, python3, GPU-def, 512\n"
    )

    assert devices[0]["index"] == 0
    assert devices[0]["memory_used_percent"] == 50.0
    assert devices[0]["power_used_percent"] == 61.5
    assert devices[1]["power_draw_w"] is None
    assert processes == [
        {
            "pid": 1234,
            "process_name": "python3",
            "gpu_uuid": "GPU-abc",
            "used_gpu_memory_mib": 22000.0,
        },
        {
            "pid": 4321,
            "process_name": "python3",
            "gpu_uuid": "GPU-def",
            "used_gpu_memory_mib": 512.0,
        },
    ]


def test_watchdog_reports_breaches_without_claiming_termination_capability() -> None:
    host = SSHHostConfig(
        ssh_alias="gpu-host",
        watchdog=SSHWatchdogConfig(
            enabled=True,
            max_gpu_memory_percent=80,
            max_gpu_temperature_c=75,
            max_system_memory_percent=90,
            min_disk_free_percent=10,
        ),
    )
    result = evaluate_watchdog(
        host,
        devices=[
            {
                "index": 0,
                "memory_used_percent": 91.0,
                "temperature_c": 78.0,
            }
        ],
        system_memory={"used_percent": 92.0},
        root_disk={"free_percent": 4.0},
    )

    assert result["status"] == "breached"
    assert result["can_terminate_remote_processes"] is False
    assert {item["metric"] for item in result["breaches"]} == {
        "gpu_memory_percent",
        "gpu_temperature_c",
        "system_memory_percent",
        "root_disk_free_percent",
    }
