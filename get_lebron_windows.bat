@echo off
setlocal
cd /d "%~dp0"
echo.
echo ===== Obter ou atualizar o repositorio LeBRON =====
where git >nul 2>nul
if errorlevel 1 (
  echo Git nao encontrado. Instale o Git para Windows e tente novamente.
  pause
  exit /b 1
)
if exist "..\Lebron\.git" (
  echo Repositorio encontrado. Tentando atualizar sem sobrescrever alteracoes locais...
  git -C "..\Lebron" pull --ff-only
  if errorlevel 1 (
    echo Nao foi possivel atualizar automaticamente. Suas alteracoes locais foram preservadas.
  )
) else (
  git clone https://github.com/guell11/Lebron.git "..\Lebron"
  if errorlevel 1 (
    echo Falha ao clonar o repositorio.
    pause
    exit /b 1
  )
)
echo.
echo Repositorio disponivel em: %~dp0..\Lebron
pause
