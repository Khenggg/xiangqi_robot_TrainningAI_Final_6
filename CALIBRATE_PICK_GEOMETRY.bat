@echo off
setlocal
chcp 65001 >nul
title Xiangqi - New top-face camera calibration - NO ROBOT
cd /d "%~dp0"
set "pick_geometry_python=%~dp0.venv312\Scripts\python.exe"
if not exist "%pick_geometry_python%" (
    echo Project environment missing. Run SETUP_WINDOWS.bat first.
    if not "%XIANGQI_NO_PAUSE%"=="1" pause
    exit /b 1
)
echo Close RUN.bat before using this camera-only wizard.
echo Print assets\calibration\checkerboard-20mm.svg at Actual Size and MEASURE its square.
"%pick_geometry_python%" -X utf8 "%~dp0scripts\calibrate_pick_geometry.py" %*
set "RESULT=%ERRORLEVEL%"
if not "%XIANGQI_NO_PAUSE%"=="1" pause
exit /b %RESULT%
