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
import os, sys, time, shutil, subprocess, threading

REPO = "https://github.com/guell11/Lebron-Local-UI"
WORK_DIR = "/kaggle/working"
DIR = os.path.join(WORK_DIR, "Lebron-Local-UI")
MODEL_DIR = os.path.join(WORK_DIR, "J-Space-Deliberation")
NGROK_TOKEN = "YOUR_NGROK_TOKEN_HERE"

# 1. Environment Directory Setup
os.chdir(WORK_DIR)
if os.path.exists(DIR): 
    shutil.rmtree(DIR)

# 2. Dependency Management
print("Installing dependencies and latest framework core...")
subprocess.run(
    "pip install -q pyngrok gradio fastapi uvicorn git+https://github.com/huggingface/transformers.git accelerate bitsandbytes huggingface_hub psutil", 
    shell=True
)

# 3. Model Artifact Synchronization
print("Downloading model artifacts...")
from huggingface_hub import snapshot_download
snapshot_download(repo_id="guell00/J-Space-Deliberation", local_dir=MODEL_DIR)

# 4. Directory Structure Optimization
stage2_dir = os.path.join(MODEL_DIR, "stage2", "final")
os.makedirs(stage2_dir, exist_ok=True)

required_files = ["jreasoner_adapter.pt", "jreasoner_config.json", "manifest.json"]
for file in required_files:
    src = os.path.join(MODEL_DIR, file)
    if os.path.exists(src):
        shutil.move(src, os.path.join(stage2_dir, file))

# 5. Repository Cloning & Interface Installation
subprocess.run(["git", "clone", REPO, DIR], check=True)
os.chdir(DIR)

if os.path.exists("requirements.txt"):
    subprocess.run("pip install -q -r requirements.txt", shell=True)

# 6. Core Module Alignment
reasoner_path = os.path.join(WORK_DIR, "LeBRON", "lebron_jspace", "reasoner.py")
if os.path.exists(reasoner_path):
    with open(reasoner_path, "r") as f:
        code = f.read()
    
    target_statement = "if self.supervision_positions is None:"
    updated_statement = "if self.supervision_positions is None:\n            positions = torch.tensor([seq - 1], device=slots.device)"
    
    if target_statement in code:
        code = code.replace(target_statement, updated_statement)
        with open(reasoner_path, "w") as f:
            f.write(code)
        print("-> Core module configuration successfully updated.")

# 7. Web Server Startup
process = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
)

def stream_logs():
    for line in iter(process.stdout.readline, ''):
        if line: print(line.strip())

threading.Thread(target=stream_logs, daemon=True).start()
time.sleep(5)

# 8. Secure Tunnel Establishment
from pyngrok import ngrok
if NGROK_TOKEN: 
    ngrok.set_auth_token(NGROK_TOKEN)

try:
    public_url = ngrok.connect(7860)
    print("\n==========================================")
    print(f" ONLINE ACCESS: {public_url}")
    print("==========================================\n")
except Exception as e:
    print(f"\nTunneling error: {e}")

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
