@echo off
setlocal
cd /d "%~dp0"
py -3.12 --version
if errorlevel 1 exit /b 1
if not exist ".venv312\Scripts\python.exe" (
    py -3.12 -m venv .venv312
    if errorlevel 1 exit /b 1
)
rem Combined project dependencies. Donor workstation pins are reference only.
".venv312\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 exit /b 1
".venv312\Scripts\python.exe" -c "import cv2,pygame,numpy,requests,torch,ultralytics,onnxruntime,pybullet,websockets; import src.hardware.hardware_manager,src.core.launch_options; print('Vision + simulation dependencies OK')"
if errorlevel 1 exit /b 1
rem Install the pinned local Three.js modules used by the web viewer.
where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js/npm missing. Install Node.js LTS, reopen terminal and rerun setup.
    exit /b 1
)
call npm.cmd ci --include=dev --no-audit --no-fund
if errorlevel 1 exit /b 1
".venv312\Scripts\python.exe" -c "from src.core.launch_options import check_viewer_assets; check_viewer_assets('.'); print('Local viewer assets OK')"
if errorlevel 1 exit /b 1
echo Setup complete. RUN.bat starts the default virtual backend.
exit /b 0
