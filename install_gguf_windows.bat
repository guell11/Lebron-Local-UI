@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Rode install_windows.bat primeiro.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
set CMAKE_ARGS=-DGGML_CUDA=on
set FORCE_CMAKE=1
pip install --upgrade --force-reinstall llama-cpp-python --no-cache-dir
python diagnose.py
pause
