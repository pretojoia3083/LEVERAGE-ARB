@echo off
title LEVERAGE ARB - Parar
cd /d "%~dp0"
echo.
echo  Encerrando o LEVERAGE ARB...
echo.

REM 1) servidor na porta 8800
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8800 ^| findstr LISTENING') do (
    echo  Encerrando servidor PID %%p
    taskkill /PID %%p /T /F >nul 2>&1
)

REM 2) a rotina que reinicia sozinho (powershell) + as janelas do .bat
for /f "tokens=2" %%p in ('wmic process where "name='powershell.exe'" ^| findstr "rodar.ps1"') do (
    echo  Encerrando reinicio automatico PID %%p
    taskkill /PID %%p /T /F >nul 2>&1
)

taskkill /IM cmd.exe /FI "WINDOWTITLE eq LEVERAGE ARB*" /T /F >nul 2>&1

echo.
echo  Servidor parado.
echo.
timeout /t 3 >nul
exit
