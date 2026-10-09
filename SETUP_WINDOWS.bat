@echo off
setlocal
chcp 65001 >nul
title Xiangqi Robot - Windows Setup
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows_bootstrap.ps1" -Mode Setup
set "RESULT=%ERRORLEVEL%"
echo.
if not "%XIANGQI_NO_PAUSE%"=="1" pause
exit /b %RESULT%
