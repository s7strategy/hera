@echo off
REM Abre o painel do S7 Editor no navegador.
setlocal
cd /d "%~dp0"
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" (
  echo   Rode INSTALAR-WINDOWS.bat primeiro.
  pause
  exit /b 1
)
start "" http://127.0.0.1:8770
".venv\Scripts\python.exe" -m s7editor.cli ui --port 8770
pause
