@echo off
chcp 65001 >nul
title Xiangqi - New top-face camera calibration - NO ROBOT
for %%I in ("%~dp0..\..") do set "XQ_ROOT=%%~fI\"
cd /d "%XQ_ROOT%"
set "pick_geometry_python="
if exist "%XQ_ROOT%.venv312\Scripts\python.exe" (
    set "pick_geometry_python=%XQ_ROOT%.venv312\Scripts\python.exe"
    goto :python_selected
)
if exist "%XQ_ROOT%.venv\Scripts\python.exe" (
    set "pick_geometry_python=%XQ_ROOT%.venv\Scripts\python.exe"
    goto :python_selected
)
python -c "import cv2, numpy" >nul 2>&1
if not errorlevel 1 set "pick_geometry_python=python"
if defined pick_geometry_python goto :python_selected
py -c "import cv2, numpy" >nul 2>&1
if not errorlevel 1 set "pick_geometry_python=py"
if defined pick_geometry_python goto :python_selected
where python >nul 2>&1
if not errorlevel 1 (set "pick_geometry_python=python") else set "pick_geometry_python=py"
:python_selected
echo Close RUN.bat before using this camera-only wizard.
echo Print assets\calibration\checkerboard-20mm.svg at Actual Size and MEASURE its square.
"%pick_geometry_python%" -X utf8 scripts\calibration\calibrate_pick_geometry.py %*
pause
