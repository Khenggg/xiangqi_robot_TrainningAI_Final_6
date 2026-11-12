@echo off
chcp 65001 >nul
title Xiangqi - Guided Geometry Measurement
for %%I in ("%~dp0..\..") do set "XQ_ROOT=%%~fI\"
cd /d "%XQ_ROOT%"
set "measure_python=python"
if exist "%XQ_ROOT%.venv\Scripts\python.exe" set "measure_python=%XQ_ROOT%.venv\Scripts\python.exe"
"%measure_python%" -c "import cv2, numpy, tkinter; from PIL import ImageTk" >nul 2>&1
if errorlevel 1 (
    set "measure_python=py"
)
echo Opening the step-by-step measurement client...
"%measure_python%" scripts\calibration\measure_geometry.py gui
if errorlevel 1 pause
