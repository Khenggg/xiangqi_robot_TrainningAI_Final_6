@echo off
chcp 65001 >nul
for %%I in ("%~dp0..\..") do set "XQ_ROOT=%%~fI\"
cd /d "%XQ_ROOT%"
set "height_calibration_python="
if exist "%XQ_ROOT%.venv312\Scripts\python.exe" (
    set "height_calibration_python=%XQ_ROOT%.venv312\Scripts\python.exe"
    goto :python_selected
)
if exist "%XQ_ROOT%.venv\Scripts\python.exe" (
    set "height_calibration_python=%XQ_ROOT%.venv\Scripts\python.exe"
    goto :python_selected
)
python -c "import cv2, numpy" >nul 2>&1
if not errorlevel 1 set "height_calibration_python=python"
if defined height_calibration_python goto :python_selected
py -c "import cv2, numpy" >nul 2>&1
if not errorlevel 1 set "height_calibration_python=py"
if defined height_calibration_python goto :python_selected
where python >nul 2>&1
if not errorlevel 1 (set "height_calibration_python=python") else set "height_calibration_python=py"
:python_selected
echo Close RUN. Measure checkerboard squares and pass --square-mm VALUE.
echo Example: CALIBRATE_CAMERA_INTRINSICS.bat --square-mm 20
"%height_calibration_python%" -X utf8 scripts\calibration\calibrate_camera_intrinsics.py %*
pause
