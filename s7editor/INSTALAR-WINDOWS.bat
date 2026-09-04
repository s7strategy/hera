@echo off
REM ===================================================================
REM  S7 Editor - instalacao no Windows. Rode UMA vez, com dois cliques.
REM ===================================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

echo.
echo   S7 Editor - instalando...
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo   [X] Python nao encontrado.
  echo.
  echo       Instale em https://python.org/downloads
  echo       IMPORTANTE: marque "Add Python to PATH" na primeira tela.
  echo       Depois rode este arquivo de novo.
  echo.
  pause
  exit /b 1
)

if not exist ".venv" (
  echo   - criando ambiente Python...
  python -m venv .venv || goto :erro
)

echo   - instalando as bibliotecas (demora um pouco na primeira vez)...
".venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
".venv\Scripts\python.exe" -m pip install -r requirements.txt --quiet || goto :erro

echo.
echo   - conferindo...
".venv\Scripts\python.exe" -m s7editor.cli doctor

echo.
echo   ===================================================================
echo    Pronto. Agora use:
echo.
echo      PAINEL.bat          abre o painel no navegador
echo      TROCAR-TEXTO.bat    troca o texto direto, sem painel
echo   ===================================================================
echo.
echo   OBS: para achar o texto sozinho (--de "ASSINE AGORA"), instale
echo   tambem o Tesseract: https://github.com/UB-Mannheim/tesseract/wiki
echo   (marque o idioma Portuguese na instalacao). Sem ele, use --papel cta.
echo.
pause
exit /b 0

:erro
echo.
echo   [X] Falhou. Copie a mensagem acima e me mande.
pause
exit /b 1
