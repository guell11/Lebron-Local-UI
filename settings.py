from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any

DEFAULT_SETTINGS: dict[str, Any] = {
    "engine": "jspace_nf4",
    "lebron_repo": "../Lebron",
    "base_model": "google/gemma-4-E4B-it",
    "model_revision": "fee6332c1abaafb77f6f9624236c63aa2f1d0187",
    "dictionary_path": "",
    "adapter_dir": "",
    "gguf_path": "",
    "model_label": "LeBRON J-Space E4B",
    "system_prompt": "Você é LeBRON, um assistente útil, preciso e direto. Responda no idioma do usuário.",
    "generation": {
        "max_new_tokens": 512,
        "temperature": 0.2,
        "top_p": 0.9,
        "loops": 8,
        "context_size": 4096,
        "repetition_penalty": 1.05,
    },
    "memory": {
        "gpu_reserve_gib": 0.75,
        "cpu_max_gib": 32,
        "offload_folder": "offload",
    },
    "ui": {
        "accent": "amber",
        "show_suggestions": True,
        "compact_sidebar": False,
    },
}


class SettingsStore:
    def __init__(self, app_root: Path):
        self.app_root = app_root.resolve()
        self.path = self.app_root / "data" / "settings.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        if not self.path.exists():
            self.save(DEFAULT_SETTINGS)

    def load(self) -> dict[str, Any]:
        with self._lock:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = {}
            return _deep_merge(deepcopy(DEFAULT_SETTINGS), raw)

    def save(self, value: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            merged = _deep_merge(deepcopy(DEFAULT_SETTINGS), value or {})
            # Tokens are deliberately never persisted in plaintext.
            merged.pop("hf_token", None)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp, self.path)
            return merged

    def resolve(self, raw: str | None, *, base: Path | None = None) -> Path | None:
        text = (raw or "").strip()
        if not text:
            return None
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            candidate = (base or self.app_root) / candidate
        return candidate.resolve()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(base[key], value)
        else:
            base[key] = value
    return base
