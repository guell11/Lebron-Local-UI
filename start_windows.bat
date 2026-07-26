@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\activate.bat (
  echo Ambiente nao instalado. Rode install_windows.bat.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python start.py
pause
