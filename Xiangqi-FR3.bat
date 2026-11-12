@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Xiangqi-FR3
cd /d "%~dp0"
rem Xiangqi-FR3 start: check/install what is missing, then start the normal RUN flow.
rem   Xiangqi-FR3.bat                 check, install missing parts, start the game
rem   Xiangqi-FR3.bat --setup-only    check and install only
rem   Other arguments are passed to scripts\windows\RUN.bat unchanged (e.g. --help).
rem   XIANGQI_SETUP_MODE=yes or no    answer version questions automatically.
set "SETUP_ONLY="
if /I "%~1"=="--setup-only" set "SETUP_ONLY=1"
if not defined XIANGQI_SETUP_MODE set "XIANGQI_SETUP_MODE=ask"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\installer\install.ps1" -Root "%~dp0." -Mode "%XIANGQI_SETUP_MODE%"
if errorlevel 1 goto :SETUP_FAILED
if defined SETUP_ONLY (
    echo.
    echo  Setup complete. Start Xiangqi-FR3.bat to play.
    if not defined XIANGQI_NO_PAUSE pause
    exit /b 0
)
call "%~dp0scripts\windows\RUN.bat" %*
exit /b %ERRORLEVEL%
:SETUP_FAILED
echo.
echo  [ERROR] Setup did not finish. Read the messages above, fix the cause and start Xiangqi-FR3.bat again.
if not defined XIANGQI_NO_PAUSE pause
exit /b 1
