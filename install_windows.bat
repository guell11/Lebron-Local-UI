
@echo off

python -m venv .venv

call .venv\Scripts\activate

python -m pip install --upgrade pip

pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu128

pip install transformers accelerate bitsandbytes huggingface_hub fastapi uvicorn psutil

echo Instalacao concluida.
pause
