@echo off
setlocal
chcp 65001 >nul
title Xiangqi - Camera intrinsics - NO ROBOT
cd /d "%~dp0"
set "height_calibration_python=%~dp0.venv312\Scripts\python.exe"
if not exist "%height_calibration_python%" (
    echo Project environment missing. Run SETUP_WINDOWS.bat first.
    if not "%XIANGQI_NO_PAUSE%"=="1" pause
    exit /b 1
)
echo Close RUN. Measure one printed checkerboard square when prompted.
echo You can also pass --square-mm VALUE and --camera INDEX.
"%height_calibration_python%" -X utf8 "%~dp0scripts\calibrate_camera_intrinsics.py" %*
set "RESULT=%ERRORLEVEL%"
if not "%XIANGQI_NO_PAUSE%"=="1" pause
exit /b %RESULT%
