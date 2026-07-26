# LeBron Local UI – Guide for Kaggle Deployment

This repository provides an automated setup and deployment guide for running **LeBron Local UI** using the **J-Space-Deliberation** architecture on Kaggle's cloud environment.

---

## 🌟 Overview

The **LeBron Local UI** provides an intuitive interface for interacting with J-Space models. When deploying in cloud environments like Kaggle, specific configurations and dependencies are required to ensure optimal performance, proper artifact routing, and correct framework compatibility (including support for recent architectures such as `gemma4`).

---

## 🛠️ Architecture & Setup Workflow

The integration script automates the following steps:

1. **Environment Initialization**: Installs bleeding-edge ML libraries (`transformers` from source, `bitsandbytes`, `accelerate`).
2. **Artifact Management**: Downloads model artifacts from Hugging Face and structures the `stage2/final` directory required by the runtime.
3. **Runtime Patching**: Applies runtime parameter alignment directly to the `LeBRON` core engine to ensure smooth inference execution.
4. **Service Exposure**: Launches the FastAPI/Uvicorn backend and establishes a secure public tunnel via `pyngrok`.

---

## 🚀 One-Click Deployment Script

Paste and execute the following Python script inside a single Kaggle Notebook cell:

```python
import os
import sys
import time
import shutil
import subprocess
import threading
import urllib.request
from pathlib import Path

from pyngrok import ngrok

WORK_DIR = Path("/kaggle/working")
CORE_DIR = WORK_DIR / "LeBRON"
UI_DIR = WORK_DIR / "Lebron-Local-UI"

SURGERY_PATH = CORE_DIR / "lebron_jspace" / "surgery.py"

PORT = 7860

NGROK_TOKEN = "seu tolken"


# ============================================================
# PARAR SERVIDOR ANTIGO
# ============================================================

subprocess.run(
    ["pkill", "-f", "uvicorn app:app"],
    check=False,
)

subprocess.run(
    ["pkill", "-f", "ngrok"],
    check=False,
)

time.sleep(2)


# ============================================================
# CORRIGIR O BUG REAL
# ============================================================

if not SURGERY_PATH.is_file():
    raise FileNotFoundError(
        f"Arquivo não encontrado: {SURGERY_PATH}"
    )

codigo = SURGERY_PATH.read_text(encoding="utf-8")

trecho_quebrado = '''def reset_inference_state(model: nn.Module) -> None:
    """Prevent latent memory from leaking between independent generations."""
    for module in iter_reasoners(model):
        module.reset_inference_state()
    for module in iter_maintainers(model):
        module.set_supervision_positions(positions)
'''

trecho_corrigido = '''def reset_inference_state(model: nn.Module) -> None:
    """Prevent latent memory and training supervision from leaking between generations."""
    for module in iter_reasoners(model):
        module.reset_inference_state()
        module.set_supervision_positions(None)

    for module in iter_maintainers(model):
        module.set_supervision_positions(None)
        module.last_summary = None
        module.last_position_summary = None
        module.last_stats = {}
'''

if trecho_quebrado in codigo:
    codigo = codigo.replace(
        trecho_quebrado,
        trecho_corrigido,
        1,
    )

elif "module.set_supervision_positions(positions)" in codigo:
    codigo = codigo.replace(
        "module.set_supervision_positions(positions)",
        "module.set_supervision_positions(None)",
    )

elif trecho_corrigido in codigo:
    print("✓ surgery.py já estava corrigido.")

else:
    raise RuntimeError(
        "Não encontrei o trecho quebrado dentro de surgery.py."
    )

compile(
    codigo,
    str(SURGERY_PATH),
    "exec",
)

SURGERY_PATH.write_text(
    codigo,
    encoding="utf-8",
)

print("✓ Bug real de positions corrigido em surgery.py.")


# ============================================================
# REMOVER CACHE PYTHON
# ============================================================

for cache in CORE_DIR.rglob("__pycache__"):
    shutil.rmtree(cache, ignore_errors=True)

for arquivo in CORE_DIR.rglob("*.pyc"):
    try:
        arquivo.unlink()
    except OSError:
        pass

subprocess.run(
    [
        sys.executable,
        "-m",
        "compileall",
        "-q",
        str(CORE_DIR / "lebron_jspace"),
    ],
    check=True,
)

# Confirma que o erro foi removido.
codigo_final = SURGERY_PATH.read_text(encoding="utf-8")

if "module.set_supervision_positions(positions)" in codigo_final:
    raise RuntimeError(
        "A referência quebrada a positions ainda existe."
    )

print("✓ Nenhuma referência quebrada permaneceu.")


# ============================================================
# REINICIAR UVICORN
# ============================================================

ambiente = os.environ.copy()

ambiente["PYTHONUNBUFFERED"] = "1"
ambiente["TOKENIZERS_PARALLELISM"] = "false"
ambiente["PYTHONPATH"] = (
    str(CORE_DIR)
    + os.pathsep
    + ambiente.get("PYTHONPATH", "")
)

processo = subprocess.Popen(
    [
        sys.executable,
        "-m",
        "uvicorn",
        "app:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(PORT),
        "--log-level",
        "info",
    ],
    cwd=str(UI_DIR),
    env=ambiente,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)


def mostrar_logs():
    if processo.stdout is None:
        return

    for linha in iter(processo.stdout.readline, ""):
        if linha:
            print(linha.rstrip())


threading.Thread(
    target=mostrar_logs,
    daemon=True,
).start()


# ============================================================
# ESPERAR SERVIDOR
# ============================================================

health_url = f"http://127.0.0.1:{PORT}/api/health"

pronto = False

for _ in range(120):
    if processo.poll() is not None:
        raise RuntimeError(
            f"Uvicorn encerrou com código {processo.returncode}."
        )

    try:
        with urllib.request.urlopen(
            health_url,
            timeout=2,
        ) as resposta:
            if resposta.status == 200:
                pronto = True
                break

    except Exception:
        time.sleep(1)

if not pronto:
    processo.terminate()
    raise RuntimeError("O servidor não iniciou.")


# ============================================================
# NOVO NGROK
# ============================================================

ngrok.set_auth_token(NGROK_TOKEN)

tunel = ngrok.connect(
    PORT,
    proto="http",
    bind_tls=True,
)

globals()["LEBRON_PROCESS"] = processo
globals()["LEBRON_TUNNEL"] = tunel

print()
print("=" * 70)
print("CORREÇÃO REAL APLICADA")
print("=" * 70)
print(f"URL: {tunel.public_url}")
print("=" * 70)
print()
print("Abra a URL, carregue o modelo apenas uma vez e crie uma nova conversa.")
```

---

## ⚙️ Interface Configuration Reference

Upon accessing the public Ngrok URL, navigate to the **Settings** tab and input the absolute paths as specified below:

| UI Input Field | Absolute Path |
| --- | --- |
| **Pasta do repositório LeBRON** | `/kaggle/working/LeBRON` |
| **Dicionário J-Space (.pt)** | `/kaggle/working/J-Space-Deliberation/jspace_dictionary_v3.pt` |
| **Pasta do adapter final** | `/kaggle/working/J-Space-Deliberation/stage2/final` |

---

## 📌 Best Practices

* **Session Lifecycle**: Before running a new deployment cycle, reset the active session (**Session options** $\rightarrow$ **Restart Session**) to clear GPU memory and prevent port binding conflicts.
* **Paths Precision**: Ensure all path inputs use absolute Linux directory structures (`/kaggle/working/...`).
