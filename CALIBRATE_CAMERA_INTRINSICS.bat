@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "height_calibration_python=python"
if exist "%~dp0.venv312\Scripts\python.exe" set "height_calibration_python=%~dp0.venv312\Scripts\python.exe"
if exist "%~dp0.venv\Scripts\python.exe" set "height_calibration_python=%~dp0.venv\Scripts\python.exe"
"%height_calibration_python%" -c "import cv2, numpy" >nul 2>&1
if errorlevel 1 set "height_calibration_python=py"
echo Close RUN. Measure checkerboard squares and pass --square-mm VALUE.
echo Example: CALIBRATE_CAMERA_INTRINSICS.bat --square-mm 20
"%height_calibration_python%" -X utf8 scripts\calibrate_camera_intrinsics.py %*
pause
