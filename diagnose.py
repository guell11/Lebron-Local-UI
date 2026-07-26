from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from settings import SettingsStore
from system_info import system_snapshot

ROOT = Path(__file__).resolve().parent


def check(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


report = {
    "python": sys.version,
    "system": system_snapshot(),
    "packages": {name: check(name) for name in ["fastapi", "uvicorn", "torch", "transformers", "bitsandbytes", "accelerate", "llama_cpp"]},
    "settings": SettingsStore(ROOT).load(),
}
try:
    import torch
    report["torch"] = {"version": torch.__version__, "cuda_available": torch.cuda.is_available(), "cuda_version": torch.version.cuda}
except Exception as exc:
    report["torch_error"] = str(exc)
print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
