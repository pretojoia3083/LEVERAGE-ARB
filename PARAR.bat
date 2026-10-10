@echo off
title LEVERAGE ARB - Parar
echo.
echo  Encerrando o servidor LEVERAGE ARB...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8800 ^| findstr LISTENING') do (
    echo  Encerrando processo %%p
    taskkill /PID %%p /F >nul 2>&1
)
echo  Servidor parado com sucesso.
echo.
pause
