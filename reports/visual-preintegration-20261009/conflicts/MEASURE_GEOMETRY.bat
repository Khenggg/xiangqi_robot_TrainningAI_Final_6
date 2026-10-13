<<<<<<< D:\OJT\xiangqi_robot_TrainningAI_Final_6\reports\visual-preintegration-20261009\merge-inputs\ours
@echo off
chcp 65001 >nul
title Xiangqi - Guided Geometry Measurement
cd /d "%~dp0"
set "measure_python=python"
if exist "%~dp0.venv\Scripts\python.exe" set "measure_python=%~dp0.venv\Scripts\python.exe"
"%measure_python%" -c "import cv2, numpy, tkinter; from PIL import ImageTk" >nul 2>&1
if errorlevel 1 (
    set "measure_python=py"
)
echo Opening the step-by-step measurement client...
"%measure_python%" scripts\measure_geometry.py gui
if errorlevel 1 pause
||||||| D:\OJT\xiangqi_robot_TrainningAI_Final_6\reports\visual-preintegration-20261009\merge-inputs\base
=======
@echo off
chcp 65001 >nul
title Xiangqi - Guided Geometry Measurement
cd /d "%~dp0"
set "measure_python=python"
if exist "%~dp0.venv\Scripts\python.exe" set "measure_python=%~dp0.venv\Scripts\python.exe"
"%measure_python%" -c "import cv2, numpy, tkinter; from PIL import ImageTk" >nul 2>&1
if errorlevel 1 (
    set "measure_python=py"
)
echo Opening the step-by-step measurement client...
"%measure_python%" scripts\measure_geometry.py gui
if errorlevel 1 pause
>>>>>>> D:\OJT\xiangqi_robot_TrainningAI_Final_6\reports\visual-preintegration-20261009\merge-inputs\visual
