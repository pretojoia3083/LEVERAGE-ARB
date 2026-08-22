@echo off
title LEVERAGE ARB - Scanner de Arbitragem
cd /d "%~dp0"
echo.
echo  ============================================
echo   LEVERAGE ARB - Iniciando sistema...
echo   Dashboard: http://localhost:8800
echo  ============================================
echo.
set PYTHONUTF8=1
py -m uvicorn server:app --host 0.0.0.0 --port 8800
pause
