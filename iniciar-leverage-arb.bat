@echo off
title LEVERAGE ARB - Arbitragem 24/7 (PC)
cd /d "%~dp0"
echo ============================================
echo   LEVERAGE ARB - Iniciando no seu PC
echo   Dashboard: http://localhost:8800
echo   Para parar: feche esta janela ou rode PARAR.bat
echo ============================================
echo.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

:loop
echo [LEVERAGE ARB] iniciando servidor...
py -m uvicorn server:app --host 0.0.0.0 --port 8800 --timeout-keep-alive 30
echo.
echo [LEVERAGE ARB] o servidor parou. Reiniciando em 10 segundos...
timeout /t 10 /nobreak >nul
goto loop
