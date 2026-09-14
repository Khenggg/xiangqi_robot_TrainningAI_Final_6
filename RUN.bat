@echo off
chcp 65001 > nul
title Xiangqi Robot
color 0A

echo.
echo  ======================================================
echo    *** XIANGQI ROBOT - Khởi động hệ thống... ***
echo  ======================================================
echo.

REM Di chuyển đến thư mục chứa file RUN.bat
cd /d "%~dp0"

REM Kiểm tra main.py
if not exist "%~dp0main.py" (
    echo [LỖI] Không tìm thấy main.py tại %~dp0!
    pause
    exit /b 1
)

REM Tìm phiên bản Python phù hợp (ưu tiên môi trường có cài sẵn thư viện cv2, pygame, ultralytics)
set "PYTHON="

REM 1. Kiểm tra venv nội bộ trong project nếu có (.venv)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
    goto :FOUND_PYTHON
)

REM 2. Kiểm tra lệnh 'python' trong PATH
python -c "import cv2, pygame, ultralytics" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=python"
    goto :FOUND_PYTHON
)

REM 3. Kiểm tra lệnh 'py'
py -c "import cv2, pygame, ultralytics" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=py"
    goto :FOUND_PYTHON
)

REM 4. Fallback: Nếu cả 2 đều không có thư viện sẵn, chọn python rồi đến py
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=python"
) else (
    set "PYTHON=py"
)

:FOUND_PYTHON
echo  [OK] Đang sử dụng Python: %PYTHON%
"%PYTHON%" --version

REM Kiểm tra Moonfish Engine (Tùy chọn cho chế độ Offline)
if not exist "%~dp0moonfish\Windows\moonfish-avx2.exe" (
    echo.
    echo  [THÔNG BÁO] Không tìm thấy moonfish-avx2.exe offline.
    echo  - Hệ thống sẽ tự động sử dụng Cloud Engine API (tuongkydaisu.com).
    echo.
)

echo  [OK] Đang khởi động main.py...
echo  [OK] Để thoát: Đóng cửa sổ hoặc bấm phím Q trên cửa sổ Camera.
echo.

REM Chạy chương trình chính
"%PYTHON%" main.py

REM Dừng màn hình lại để xem log lỗi (nếu có) trước khi thoát
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [LỖI] Chương trình dừng lại với mã lỗi %ERRORLEVEL%! Hãy kiểm tra log ở trên.
    pause
)

REM Hiển thị khi thoát
echo.
echo  *** Chương trình đã kết thúc an toàn. ***
pause
