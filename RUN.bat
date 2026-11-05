@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Xiangqi Robot
cd /d "%~dp0"

echo.
echo  ======================================================
echo    *** XIANGQI ROBOT - Khởi động hệ thống... ***
echo  ======================================================
echo.

if not exist "%~dp0main.py" goto :NO_MAIN

set "PYTHON="
if exist "%~dp0.venv312\Scripts\python.exe" set "PYTHON=%~dp0.venv312\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0.venv\Scripts\python.exe" set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not defined PYTHON (
    where python >nul 2>&1 && set "PYTHON=python"
)
if not defined PYTHON (
    where py >nul 2>&1 && set "PYTHON=py"
)
if not defined PYTHON goto :NO_PYTHON

echo  [OK] Python: %PYTHON%
"%PYTHON%" --version >nul 2>&1
if errorlevel 1 goto :NO_PYTHON

REM Check the modules required by the game/simulation before launching. Keep
REM this as find_spec so startup does not load torch/ultralytics.
"%PYTHON%" -c "import importlib.util as u; mods=('pygame','numpy','cv2','pybullet','websockets'); missing=[m for m in mods if u.find_spec(m) is None]; print('Missing: '+', '.join(missing)) if missing else None; raise SystemExit(1 if missing else 0)"
if errorlevel 1 goto :NO_DEPS

"%PYTHON%" -c "import importlib.util as u; raise SystemExit(0 if u.find_spec('ultralytics') else 1)"
if errorlevel 1 echo  [WARN] Thiếu ultralytics: camera/YOLO sẽ không hoạt động.

if not exist "%~dp0moonfish\moonfish_ucci.py" (
    echo.
    echo  [THÔNG BÁO] Không tìm thấy moonfish\moonfish_ucci.py.
    echo  - Kiểm tra config.MOONFISH_EXE; Cloud chỉ dùng khi ENGINE_TYPE cho phép.
    echo.
)

if not exist "%~dp0node_modules\three\build\three.module.js" (
    echo  [WARN] Thiếu node_modules/three; viewer 3D sẽ không mở được.
    echo         Chạy SETUP_WINDOWS.bat hoặc npm ci --include=dev.
)

echo  [OK] Đang khởi động main.py...
echo  [OK] Để thoát: đóng cửa sổ game hoặc Ctrl+C trên terminal.
echo.

"%PYTHON%" main.py %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" goto :RUN_FAILED

echo.
echo  *** Chương trình đã kết thúc an toàn. ***
if "%~1"=="" if not defined XIANGQI_NO_PAUSE pause
exit /b 0

:RUN_FAILED
echo.
echo  [LỖI] Chương trình dừng với mã lỗi %RC%. Kiểm tra log ở trên.
if not defined XIANGQI_NO_PAUSE pause
exit /b %RC%

:NO_MAIN
echo [LỖI] Không tìm thấy main.py tại %~dp0
if not defined XIANGQI_NO_PAUSE pause
exit /b 1

:NO_PYTHON
echo [LỖI] Không tìm thấy Python. Chạy SETUP_WINDOWS.bat trước.
if not defined XIANGQI_NO_PAUSE pause
exit /b 1

:NO_DEPS
echo [LỖI] Môi trường Python thiếu thư viện bắt buộc. Chạy SETUP_WINDOWS.bat.
if not defined XIANGQI_NO_PAUSE pause
exit /b 1
