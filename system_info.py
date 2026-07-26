from __future__ import annotations

import platform
import subprocess
from typing import Any

import psutil


def gpu_snapshot() -> list[dict[str, Any]]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu,driver_version",
        "--format=csv,noheader,nounits",
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    rows = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 7:
            continue
        try:
            rows.append({
                "index": int(parts[0]),
                "name": parts[1],
                "memory_used_mb": float(parts[2]),
                "memory_total_mb": float(parts[3]),
                "utilization": float(parts[4]),
                "temperature_c": float(parts[5]),
                "driver": parts[6],
            })
        except ValueError:
            continue
    return rows


def system_snapshot() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_used_gib": round((memory.total - memory.available) / 1024**3, 2),
        "ram_total_gib": round(memory.total / 1024**3, 2),
        "gpus": gpu_snapshot(),
    }
