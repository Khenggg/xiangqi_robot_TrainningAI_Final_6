@echo off
cd /d "%~dp0"
set "measure_python=python"
if exist "%~dp0.venv\Scripts\python.exe" set "measure_python=%~dp0.venv\Scripts\python.exe"
"%measure_python%" -c "import cv2, numpy" >nul 2>&1
if errorlevel 1 (
    set "measure_python=py"
)
echo 1. Camera to grid: click printed intersections
echo 2. Grid to robot: supervised motion at SAFE_Z, no gripper commands
echo 3. Grid to robot: read-only plan
set /p "measure_choice=Choose 1, 2 or 3: "
if "%measure_choice%"=="1" "%measure_python%" scripts\measure_geometry.py camera
if "%measure_choice%"=="2" "%measure_python%" scripts\measure_geometry.py robot --move
if "%measure_choice%"=="3" "%measure_python%" scripts\measure_geometry.py robot
pause
