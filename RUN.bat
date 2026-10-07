@echo off
chcp 65001 > nul
title Xiangqi Robot
color 0A

echo.
echo  ======================================================
echo    *** XIANGQI ROBOT - Khoi dong he thong... ***
echo  ======================================================
echo.

REM Di chuyen den thu muc chua file RUN.bat
cd /d "%~dp0"

REM Kiem tra main.py
if not exist "%~dp0main.py" (
    echo [LOI] Khong tim thay main.py tai %~dp0!
    pause
    exit /b 1
)

REM Tim phien ban Python phu hop (uu tien moi truong co cai san thu vien cv2, pygame, ultralytics)
set "PYTHON="

if exist "%~dp0.venv312\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv312\Scripts\python.exe"
    goto :FOUND_PYTHON
)

REM 1. Kiem tra venv noi bo trong project neu co (.venv)
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON=%~dp0.venv\Scripts\python.exe"
    goto :FOUND_PYTHON
)

REM 2. Kiem tra lenh 'python' trong PATH
python -c "import cv2, pygame, ultralytics" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=python"
    goto :FOUND_PYTHON
)

REM 3. Kiem tra lenh 'py'
py -c "import cv2, pygame, ultralytics" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=py"
    goto :FOUND_PYTHON
)

REM 4. Fallback: Neu ca 2 deu khong co thu vien san, chon python roi den py
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=python"
) else (
    set "PYTHON=py"
)

:FOUND_PYTHON
echo  [OK] Dang su dung Python: %PYTHON%
"%PYTHON%" --version

REM Kiem tra Moonfish Engine (Tuy chon cho che do Offline)
if not exist "%~dp0moonfish\Windows\moonfish-avx2.exe" (
    echo.
    echo  [THONG BAO] Khong tim thay moonfish-avx2.exe offline.
    echo  - He thong se tu dong su dung Cloud Engine API ^(tuongkydaisu.com^).
    echo.
)

echo  [OK] Dang khoi dong main.py...
echo  [OK] De thoat: Dong cua so hoac bam phim Q tren cua so Camera.
echo.

REM Chay chuong trinh chinh
"%PYTHON%" main.py

REM Dung man hinh lai de xem log loi (neu co) truoc khi thoat
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [LOI] Chuong trinh dung lai voi ma loi %ERRORLEVEL%! Hay kiem tra log o tren.
    pause
)

REM Hien thi khi thoat
echo.
echo  *** Chuong trinh da ket thuc an toan. ***
pause
