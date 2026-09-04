@echo off
REM ===================================================================
REM  Troca um texto em todas as imagens de uma pasta.
REM  Onde o texto nao existir, escreve embaixo do preco.
REM ===================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

if not exist ".venv\Scripts\python.exe" (
  echo   Rode INSTALAR-WINDOWS.bat primeiro.
  pause
  exit /b 1
)

echo.
echo   S7 Editor - troca de texto em lote
echo.
set /p PASTA=  Pasta com as imagens (arraste a pasta aqui e de Enter): 
set PASTA=!PASTA:"=!
if not exist "!PASTA!" (
  echo   [X] Nao achei a pasta: !PASTA!
  pause
  exit /b 1
)

set /p DE=  Texto ATUAL (ex.: ASSINE AGORA) - deixe vazio para usar o CTA: 
set /p PARA=  Texto NOVO  (ex.: TESTE GRATIS): 
if "!PARA!"=="" (
  echo   [X] Preciso do texto novo.
  pause
  exit /b 1
)
set /p NOME=  Nome da pasta de saida [EDITADA TESTE GRATIS]: 
if "!NOME!"=="" set NOME=EDITADA TESTE GRATIS
set /p QTD=  Quantas imagens? (Enter = todas, 1 = so provar): 

set ARGS=--para "!PARA!" --senao-abaixo-de price --out "!PASTA!\!NOME!" --force
if "!DE!"=="" (set ARGS=!ARGS! --papel cta) else (set ARGS=!ARGS! --de "!DE!")
if not "!QTD!"=="" set ARGS=!ARGS! --limite !QTD!

echo.
".venv\Scripts\python.exe" -m s7editor.cli trocar-texto "!PASTA!" !ARGS!

echo.
echo   As imagens editadas estao em: !PASTA!\!NOME!
echo.
pause
