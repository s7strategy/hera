@echo off
REM ===================================================================
REM  Abre o painel do S7 Editor no navegador.
REM  O navegador abre sozinho DEPOIS que o servidor responder — abrir
REM  antes era corrida perdida e mostrava "nao foi possivel acessar".
REM ===================================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   Ambiente nao encontrado nesta pasta.
  echo   Rode INSTALAR-WINDOWS.bat primeiro ^(fica aqui do lado^).
  echo.
  pause
  exit /b 1
)

echo.
echo   Subindo o painel. O navegador abre sozinho em alguns segundos.
echo   Para parar: feche esta janela ou aperte Ctrl+C.
echo.

".venv\Scripts\python.exe" -m s7editor.cli ui --port 8770 --abrir

echo.
echo   O painel foi encerrado.
pause
