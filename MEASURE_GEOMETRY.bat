@echo off
setlocal
chcp 65001 >nul
title Xiangqi - Guided Geometry Measurement
cd /d "%~dp0"
set "measure_python=%~dp0.venv312\Scripts\python.exe"
if not exist "%measure_python%" (
    echo Project environment missing. Run SETUP_WINDOWS.bat first.
    if not "%XIANGQI_NO_PAUSE%"=="1" pause
    exit /b 1
)
echo Opening the step-by-step measurement client...
"%measure_python%" -X utf8 "%~dp0scripts\measure_geometry.py" gui %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" if not "%XIANGQI_NO_PAUSE%"=="1" pause
exit /b %RESULT%
