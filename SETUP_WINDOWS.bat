@echo off
setlocal
cd /d "%~dp0"
py -3.12 --version
if errorlevel 1 exit /b 1
if not exist ".venv312\Scripts\python.exe" (
    py -3.12 -m venv .venv312
    if errorlevel 1 exit /b 1
)
".venv312\Scripts\python.exe" -m pip install -r requirements-lock-win-py312.txt
if errorlevel 1 exit /b 1
".venv312\Scripts\python.exe" -c "import cv2,pygame,numpy,requests,torch,ultralytics,onnxruntime; print('Dependencies OK')"
if errorlevel 1 exit /b 1
echo Setup complete. Connect camera and robot, then open RUN.bat.
exit /b 0
