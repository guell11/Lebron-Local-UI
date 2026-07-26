from __future__ import annotations

import gc
import json
import math
import os
import re
import sys
import time
import traceback
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any, Generator

from settings import SettingsStore
from system_info import gpu_snapshot


class RuntimeManager:
    def __init__(self, app_root: Path, settings_store: SettingsStore):
        self.app_root = app_root.resolve()
        self.settings_store = settings_store
        self._state_lock = Lock()
        self._generation_lock = Lock()
        self._stop = Event()
        self._runtime: Any = None
        self._session_token: str | None = None
        self._status: dict[str, Any] = {
            "state": "unloaded",
            "engine": None,
            "message": "Modelo não carregado.",
            "model": None,
            "warning": None,
            "error": None,
            "loaded_at": None,
        }

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            return dict(self._status)

    def set_token(self, token: str | None) -> None:
        self._session_token = (token or "").strip() or None

    def load_async(self, settings: dict[str, Any], hf_token: str | None = None) -> dict[str, Any]:
        with self._state_lock:
            if self._status["state"] in {"loading", "unloading"}:
                raise RuntimeError("Já existe uma operação de modelo em andamento.")
            if self._status["state"] == "loaded":
                raise RuntimeError("Descarregue o modelo atual antes de carregar outro.")
            self._status = {
                "state": "loading",
                "engine": settings.get("engine"),
                "message": "Validando arquivos e carregando o modelo…",
                "model": settings.get("model_label") or settings.get("base_model"),
                "warning": None,
                "error": None,
                "loaded_at": None,
            }
        self.set_token(hf_token)
        Thread(target=self._load_worker, args=(settings,), daemon=True).start()
        return self.status()

    def _load_worker(self, settings: dict[str, Any]) -> None:
        try:
            engine = settings.get("engine", "jspace_nf4")
            if engine == "jspace_nf4":
                runtime = JSpaceNF4Runtime(self.app_root, self.settings_store, settings, self._session_token)
            elif engine == "gguf":
                runtime = GGUFRuntime(settings)
            else:
                raise ValueError(f"Engine desconhecido: {engine}")
            runtime.load()
            with self._state_lock:
                self._runtime = runtime
                self._status.update({
                    "state": "loaded",
                    "message": "Modelo pronto para conversar.",
                    "warning": runtime.warning,
                    "loaded_at": time.time(),
                    "error": None,
                })
        except Exception as exc:  # noqa: BLE001
            with self._state_lock:
                self._runtime = None
                self._status.update({
                    "state": "error",
                    "message": "Falha ao carregar o modelo.",
                    "error": f"{exc}\n{traceback.format_exc()}",
                })

    def unload(self) -> dict[str, Any]:
        with self._state_lock:
            if self._status["state"] == "loading":
                raise RuntimeError("O modelo ainda está carregando.")
            self._status["state"] = "unloading"
            self._status["message"] = "Liberando memória…"
        self.stop()
        with self._generation_lock:
            runtime = self._runtime
            self._runtime = None
            if runtime is not None:
                runtime.unload()
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    torch.cuda.ipc_collect()
            except (ImportError, RuntimeError):
                pass
        with self._state_lock:
            self._status = {
                "state": "unloaded",
                "engine": None,
                "message": "Modelo descarregado.",
                "model": None,
                "warning": None,
                "error": None,
                "loaded_at": None,
            }
        return self.status()

    def stop(self) -> None:
        self._stop.set()
        runtime = self._runtime
        if runtime is not None:
            runtime.stop()

    def generate_stream(self, messages: list[dict[str, str]], generation: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
        with self._generation_lock:
            with self._state_lock:
                if self._status["state"] != "loaded" or self._runtime is None:
                    raise RuntimeError("Carregue o modelo antes de enviar mensagens.")
                runtime = self._runtime
            self._stop.clear()
            yield from runtime.generate_stream(messages, generation, self._stop)


class JSpaceNF4Runtime:
    warning = None

    def __init__(self, app_root: Path, store: SettingsStore, settings: dict[str, Any], hf_token: str | None):
        self.app_root = app_root
        self.store = store
        self.settings = settings
        self.hf_token = hf_token
        self.model = None
        self.tokenizer = None
        self.reasoners: list[Any] = []
        self._stop = Event()

    def _resolve_artifacts(self) -> tuple[Path, Path, Path]:
        repo = self.store.resolve(self.settings.get("lebron_repo"), base=self.app_root)
        if repo is None or not (repo / "lebron_jspace").is_dir():
            raise FileNotFoundError("Repositório LeBRON não encontrado. Selecione a pasta que contém lebron_jspace/.")
        dictionary = self.store.resolve(self.settings.get("dictionary_path"), base=repo)
        adapter = self.store.resolve(self.settings.get("adapter_dir"), base=repo)
        if dictionary is None:
            candidates = list(repo.glob("artifacts/**/jspace_dictionary_v3.pt"))
            if len(candidates) == 1:
                dictionary = candidates[0]
        if adapter is None:
            candidates = list(repo.glob("**/stage2/final/jreasoner_adapter.pt"))
            if len(candidates) == 1:
                adapter = candidates[0].parent
        if dictionary is None or not dictionary.is_file():
            raise FileNotFoundError("Dicionário J-Space não encontrado. Informe jspace_dictionary_v3.pt.")
        if adapter is None or not (adapter / "jreasoner_adapter.pt").is_file():
            raise FileNotFoundError("Adapter final não encontrado. Selecione a pasta stage2/final.")
        if not (adapter / "jreasoner_config.json").is_file():
            raise FileNotFoundError("jreasoner_config.json não encontrado dentro do adapter.")
        return repo, dictionary, adapter

    def load(self) -> None:
        repo, dictionary_path, adapter_dir = self._resolve_artifacts()
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        if self.hf_token:
            os.environ["HF_TOKEN"] = self.hf_token
            os.environ["HUGGING_FACE_HUB_TOKEN"] = self.hf_token
        import torch
        from transformers import AutoTokenizer, BitsAndBytesConfig
        from lebron_jspace.config import JReasonerConfig
        from lebron_jspace.lens_utils import load_language_model
        from lebron_jspace.surgery import (
            inject_jreasoner,
            iter_reasoners,
            load_and_validate_manifest,
            load_architecture_adapter,
            validate_artifact_identity,
        )
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA não está disponível. Instale o PyTorch com CUDA e confirme o driver NVIDIA.")
        base_model = str(self.settings.get("base_model") or "").strip()
        revision = str(self.settings.get("model_revision") or "").strip() or None
        manifest = load_and_validate_manifest(adapter_dir, base_model, revision)
        effective_revision = revision or manifest.get("model_revision")
        hub_kwargs: dict[str, Any] = {}
        if effective_revision:
            hub_kwargs["revision"] = effective_revision
        if self.hf_token:
            hub_kwargs["token"] = self.hf_token
        quant = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        gpu_rows = gpu_snapshot()
        memory_cfg = self.settings.get("memory") or {}
        max_memory = None
        if gpu_rows:
            total_gib = gpu_rows[0]["memory_total_mb"] / 1024
            reserve = float(memory_cfg.get("gpu_reserve_gib", 0.75))
            usable = max(2.5, total_gib - reserve)
            max_memory = {0: f"{usable:.1f}GiB", "cpu": f"{int(memory_cfg.get('cpu_max_gib', 32))}GiB"}
        offload_raw = str(memory_cfg.get("offload_folder") or "offload")
        offload = self.store.resolve(offload_raw, base=self.app_root) or (self.app_root / "offload")
        offload.mkdir(parents=True, exist_ok=True)
        self.tokenizer = AutoTokenizer.from_pretrained(base_model, use_fast=True, **hub_kwargs)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        kwargs: dict[str, Any] = {
            "quantization_config": quant,
            "dtype": torch.float16,
            "device_map": "auto",
            "low_cpu_mem_usage": True,
            "offload_folder": str(offload),
            **hub_kwargs,
        }
        if max_memory:
            kwargs["max_memory"] = max_memory
        self.model = load_language_model(base_model, **kwargs)
        cfg = JReasonerConfig.load(adapter_dir / "jreasoner_config.json")
        dictionary = torch.load(dictionary_path, map_location="cpu", weights_only=True)
        validate_artifact_identity(dictionary, base_model, effective_revision)
        inject_jreasoner(self.model, dictionary, cfg)
        load_architecture_adapter(self.model, adapter_dir / "jreasoner_adapter.pt")
        self.model.config.use_cache = True
        self.model.eval()
        self.reasoners = list(iter_reasoners(self.model))

    def unload(self) -> None:
        self.model = None
        self.tokenizer = None
        self.reasoners = []

    def stop(self) -> None:
        self._stop.set()

    def _telemetry(self) -> tuple[list[dict[str, Any]], float | None, str | None]:
        stats = [dict(reasoner.last_stats) for reasoner in self.reasoners]
        confidences = []
        for reasoner, item in zip(self.reasoners, stats):
            entropy = item.get("mean_branch_entropy")
            change = item.get("mean_relative_change")
            if entropy is None:
                continue
            max_entropy = math.log(max(2, reasoner.config.branches))
            agreement = 1.0 - min(1.0, max(0.0, float(entropy) / max_entropy))
            stability = 1.0 / (1.0 + max(0.0, float(change or 0.0)))
            confidences.append(agreement * stability)
        confidence = sum(confidences) / len(confidences) if confidences else None
        warning = "Sinal interno de baixa confiança; confira fatos e resultados." if confidence is not None and confidence < 0.25 else None
        return stats, confidence, warning

    def generate_stream(self, messages: list[dict[str, str]], generation: dict[str, Any], external_stop: Event):
        import torch
        from transformers import StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer
        from lebron_jspace.surgery import reset_inference_state
        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Modelo não carregado.")
        self._stop.clear()
        loops = max(2, min(16, int(generation.get("loops", 8))))
        previous = [reasoner.config.max_infer_loops for reasoner in self.reasoners]
        for reasoner in self.reasoners:
            reasoner.config.max_infer_loops = loops
        reset_inference_state(self.model)
        template_kwargs = {
            "tokenize": True,
            "add_generation_prompt": True,
            "return_tensors": "pt",
            "return_dict": True,
            "enable_thinking": False,
        }
        try:
            model_inputs = self.tokenizer.apply_chat_template(messages, **template_kwargs)
        except TypeError:
            template_kwargs.pop("return_dict", None)
            template_kwargs.pop("enable_thinking", None)
            ids = self.tokenizer.apply_chat_template(messages, **template_kwargs)
            model_inputs = {"input_ids": ids, "attention_mask": torch.ones_like(ids)}
        if torch.is_tensor(model_inputs):
            model_inputs = {"input_ids": model_inputs, "attention_mask": torch.ones_like(model_inputs)}
        device = self.model.get_input_embeddings().weight.device
        model_inputs = {k: v.to(device) if torch.is_tensor(v) else v for k, v in dict(model_inputs).items()}
        context_limit = int(generation.get("context_size", 4096))
        max_new = max(1, min(2048, int(generation.get("max_new_tokens", 512))))
        max_input = max(64, context_limit - max_new)
        for key in ("input_ids", "attention_mask", "token_type_ids"):
            value = model_inputs.get(key)
            if torch.is_tensor(value) and value.ndim >= 2 and value.shape[-1] > max_input:
                model_inputs[key] = value[:, -max_input:]
        temperature = float(generation.get("temperature", 0.2))
        top_p = float(generation.get("top_p", 0.9))
        kwargs: dict[str, Any] = {
            "max_new_tokens": max_new,
            "do_sample": temperature > 0,
            "use_cache": True,
            "pad_token_id": self.tokenizer.pad_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
            "repetition_penalty": float(generation.get("repetition_penalty", 1.05)),
        }
        if temperature > 0:
            kwargs.update({"temperature": max(0.05, min(2.0, temperature)), "top_p": max(0.1, min(1.0, top_p))})

        local_stop = self._stop
        class StopCriteria(StoppingCriteria):
            def __call__(self, input_ids, scores, **_kwargs):
                stopped = local_stop.is_set() or external_stop.is_set()
                return torch.full((input_ids.shape[0],), stopped, dtype=torch.bool, device=input_ids.device)

        streamer = TextIteratorStreamer(self.tokenizer, skip_prompt=True, skip_special_tokens=True)
        kwargs["streamer"] = streamer
        kwargs["stopping_criteria"] = StoppingCriteriaList([StopCriteria()])
        errors: list[BaseException] = []
        def worker():
            try:
                with torch.inference_mode():
                    self.model.generate(**model_inputs, **kwargs)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)
                streamer.on_finalized_text("", stream_end=True)
        started = time.perf_counter()
        thread = Thread(target=worker, daemon=True)
        thread.start()
        fragments: list[str] = []
        try:
            for fragment in streamer:
                fragments.append(fragment)
                yield {"event": "token", "text": fragment}
            thread.join()
            if errors:
                raise RuntimeError(str(errors[0])) from errors[0]
            elapsed = time.perf_counter() - started
            text = "".join(fragments).strip()
            text = re.sub(r"<(?:think|analysis)>.*?</(?:think|analysis)>", "", text, flags=re.I | re.S).strip() or text
            tokens = len(self.tokenizer.encode(text, add_special_tokens=False))
            stats, confidence, warning = self._telemetry()
            yield {
                "event": "done",
                "text": text,
                "elapsed_seconds": elapsed,
                "generated_tokens": tokens,
                "tokens_per_second": tokens / elapsed if elapsed else None,
                "reasoner": stats,
                "confidence": confidence,
                "warning": warning,
                "stopped": local_stop.is_set() or external_stop.is_set(),
                "engine": "jspace_nf4",
            }
        finally:
            local_stop.set()
            while thread.is_alive():
                thread.join(timeout=1)
            for reasoner, old in zip(self.reasoners, previous):
                reasoner.config.max_infer_loops = old


class GGUFRuntime:
    warning = "Modo GGUF executa o modelo-base. O sidecar J-Space não é aplicado pelo llama.cpp padrão."

    def __init__(self, settings: dict[str, Any]):
        self.settings = settings
        self.llm = None
        self._stop = Event()

    def load(self) -> None:
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise RuntimeError("llama-cpp-python não está instalado. Rode install_gguf_windows.bat.") from exc
        path = Path(str(self.settings.get("gguf_path") or "")).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() != ".gguf":
            raise FileNotFoundError("Selecione um arquivo .gguf válido.")
        generation = self.settings.get("generation") or {}
        self.llm = Llama(
            model_path=str(path),
            n_ctx=int(generation.get("context_size", 4096)),
            n_gpu_layers=-1,
            n_batch=512,
            flash_attn=True,
            verbose=False,
        )

    def unload(self) -> None:
        self.llm = None

    def stop(self) -> None:
        self._stop.set()

    def generate_stream(self, messages: list[dict[str, str]], generation: dict[str, Any], external_stop: Event):
        if self.llm is None:
            raise RuntimeError("Modelo GGUF não carregado.")
        self._stop.clear()
        started = time.perf_counter()
        fragments: list[str] = []
        stream = self.llm.create_chat_completion(
            messages=messages,
            max_tokens=max(1, min(2048, int(generation.get("max_new_tokens", 512)))),
            temperature=max(0.0, min(2.0, float(generation.get("temperature", 0.2)))),
            top_p=max(0.1, min(1.0, float(generation.get("top_p", 0.9)))),
            repeat_penalty=float(generation.get("repetition_penalty", 1.05)),
            stream=True,
        )
        for chunk in stream:
            if self._stop.is_set() or external_stop.is_set():
                break
            text = chunk.get("choices", [{}])[0].get("delta", {}).get("content") or ""
            if text:
                fragments.append(text)
                yield {"event": "token", "text": text}
        elapsed = time.perf_counter() - started
        text = "".join(fragments).strip()
        usage_tokens = max(1, len(text.split()))
        yield {
            "event": "done",
            "text": text,
            "elapsed_seconds": elapsed,
            "generated_tokens": usage_tokens,
            "tokens_per_second": usage_tokens / elapsed if elapsed else None,
            "warning": self.warning,
            "stopped": self._stop.is_set() or external_stop.is_set(),
            "engine": "gguf",
        }
